import ipaddress
import socket
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpcore
from httpcore._backends.sync import SyncBackend
import httpx


class SSRFProtectionError(Exception):
    """Raised when an outbound URL violates SSRF security policies."""
    pass


# Specific cloud metadata and prohibited CIDR ranges
PROHIBITED_CIDRS = [
    # IPv4 loopback
    ipaddress.ip_network("127.0.0.0/8"),
    # IPv4 RFC 1918 private
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # IPv4 link-local & cloud metadata
    ipaddress.ip_network("169.254.0.0/16"),
    # Carrier grade NAT
    ipaddress.ip_network("100.64.0.0/10"),
    # Unspecified / broadcast / reserved
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved
    ipaddress.ip_network("255.255.255.255/32"),
    # Documentation / Test nets
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    # IPv6 loopback, link-local, unique local, multicast, unspecified
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fc00::/7"),  # ULA
    ipaddress.ip_network("fe80::/10"),  # Link-local
    ipaddress.ip_network("ff00::/8"),  # Multicast
    ipaddress.ip_network("2001:db8::/32"),  # Documentation
]

PROHIBITED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
}

MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MB limit
MAX_REDIRECTS = 3
DEFAULT_TIMEOUT_MS = 10000
MAX_TIMEOUT_MS = 30000


def validate_url_syntax_and_scheme(url_str: str) -> urllib.parse.ParseResult:
    """Validate URL format, scheme, and absence of userinfo credentials."""
    if not url_str or not isinstance(url_str, str):
        raise SSRFProtectionError("A valid URL string is required.")

    parsed = urllib.parse.urlparse(url_str)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SSRFProtectionError(f"Prohibited URL scheme '{scheme}'. Only HTTP and HTTPS are permitted.")

    if not parsed.hostname:
        raise SSRFProtectionError("URL must contain a valid host name.")

    if parsed.username or parsed.password:
        raise SSRFProtectionError("URL credentials (userinfo) are not permitted.")

    hostname_lower = parsed.hostname.lower()
    if hostname_lower in PROHIBITED_HOSTNAMES:
        raise SSRFProtectionError(f"Target host '{parsed.hostname}' is prohibited.")

    if hostname_lower.endswith(".local") or hostname_lower.endswith(".internal"):
        raise SSRFProtectionError(f"Target host '{parsed.hostname}' is within a private internal domain.")

    return parsed


def is_ip_prohibited(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address falls into any loopback, private, or prohibited range."""
    # If IPv4-mapped IPv6 address (e.g. ::ffff:127.0.0.1, ::ffff:169.254.169.254), evaluate underlying IPv4
    if getattr(ip, "ipv4_mapped", None):
        return is_ip_prohibited(ip.ipv4_mapped)

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    for net in PROHIBITED_CIDRS:
        if net.version == ip.version and ip in net:
            return True

    return False



def resolve_and_validate_host(hostname: str, port: int) -> List[str]:
    """Resolve DNS for host and ensure ALL returned IP addresses are public and safe."""
    # Check if hostname is already an IP address
    try:
        ip = ipaddress.ip_address(hostname.strip("[]"))
        if is_ip_prohibited(ip):
            raise SSRFProtectionError(f"Destination IP address {ip} is prohibited.")
        return [str(ip)]
    except ValueError:
        pass  # It is a domain name, proceed to DNS resolution

    try:
        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise SSRFProtectionError(f"DNS resolution failed for '{hostname}': {e}")

    if not addr_info:
        raise SSRFProtectionError(f"No IP addresses resolved for '{hostname}'.")

    resolved_ips: List[str] = []
    for entry in addr_info:
        ip_str = entry[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFProtectionError(f"Malformed IP '{ip_str}' resolved from '{hostname}'.")

        if is_ip_prohibited(ip_obj):
            raise SSRFProtectionError(
                f"Resolved destination address {ip_str} for '{hostname}' is within a prohibited private or link-local range."
            )
        if ip_str not in resolved_ips:
            resolved_ips.append(ip_str)

    if not resolved_ips:
        raise SSRFProtectionError(f"No valid public IP addresses found for '{hostname}'.")

    return resolved_ips


class SSRFSafeBackend(SyncBackend):
    """Custom network backend that validates IPs and pins socket connection to the validated IP.
    
    This ensures that the IP validated during SSRF checks is the exact IP used for the connection,
    defeating DNS rebinding attacks while allowing TLS SNI to retain the original hostname.
    """
    def __init__(self) -> None:
        super().__init__()
        self.validated_ip: Optional[str] = None

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        # Resolve and validate host to public IP
        valid_ips = resolve_and_validate_host(host, port)
        # Pin connection directly to the first validated IP
        target_ip = valid_ips[0]
        self.validated_ip = target_ip
        # Connect socket to (target_ip, port). TLS wrap will still use host for SNI / cert check.
        return super().connect_tcp(
            target_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class SSRFSafeTransport(httpx.HTTPTransport):
    """Transport that uses SSRFSafeBackend to pin connection IP and reject forbidden destinations."""
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.backend = SSRFSafeBackend()
        self._pool = httpcore.ConnectionPool(
            ssl_context=self._pool._ssl_context,
            max_connections=self._pool._max_connections,
            max_keepalive_connections=self._pool._max_keepalive_connections,
            keepalive_expiry=self._pool._keepalive_expiry,
            http1=self._pool._http1,
            http2=self._pool._http2,
            retries=0,
            network_backend=self.backend,
        )


def execute_safe_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    body: Optional[str] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Tuple[int, Dict[str, str], str, float]:
    """Execute an outbound HTTP request with strict SSRF protection and bounded limits.
    
    Returns: (status_code, response_headers, response_body, latency_ms)
    """
    clean_timeout_ms = min(max(timeout_ms, 500), MAX_TIMEOUT_MS)
    timeout_sec = clean_timeout_ms / 1000.0

    current_url = url
    current_method = method.upper()
    redirect_count = 0

    # Ensure internal sensitive cookies or headers are never forwarded
    sanitized_headers = {
        k: v for k, v in (headers or {}).items()
        if k.lower() not in ("cookie", "host")
    }

    start_time = time.perf_counter()

    while True:
        # 1. Validate URL syntax and scheme
        parsed = validate_url_syntax_and_scheme(current_url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # 2. Pre-validate DNS/IP before initiating connection
        resolve_and_validate_host(parsed.hostname, port)

        # 3. Create fresh transport with SSRF-safe connection pinning
        transport = SSRFSafeTransport(verify=True)
        with httpx.Client(transport=transport, follow_redirects=False) as client:
            try:
                request = client.build_request(
                    method=current_method,
                    url=current_url,
                    headers=sanitized_headers,
                    params=params if redirect_count == 0 else None,
                    content=body.encode("utf-8") if body and current_method in ("POST", "PUT", "PATCH") else None,
                    timeout=httpx.Timeout(timeout_sec, connect=timeout_sec / 2),
                )
                response = client.send(request, stream=True)
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                raise TimeoutError(f"Request timed out after {clean_timeout_ms}ms: {exc}")
            except (SSRFProtectionError, Exception) as exc:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                if isinstance(exc, SSRFProtectionError):
                    raise
                # Check if underlying cause is SSRFProtectionError
                cause = getattr(exc, "__cause__", None)
                if isinstance(cause, SSRFProtectionError):
                    raise cause
                raise IOError(f"Network connection failed: {exc}")

            # Check for redirect
            if response.status_code in (301, 302, 303, 307, 308) and "location" in response.headers:
                redirect_count += 1
                if redirect_count > MAX_REDIRECTS:
                    raise SSRFProtectionError(f"Exceeded maximum allowed redirects ({MAX_REDIRECTS}).")

                new_location = response.headers["location"]
                current_url = urllib.parse.urljoin(current_url, new_location)

                # 303 forces GET; 301/302 typically change POST to GET
                if response.status_code == 303 or (response.status_code in (301, 302) and current_method == "POST"):
                    current_method = "GET"
                    body = None

                response.close()
                continue

            # Read response with byte limit
            content_chunks = []
            total_bytes = 0
            for chunk in response.iter_bytes():
                total_bytes += len(chunk)
                if total_bytes > MAX_RESPONSE_BYTES:
                    # Truncate content at limit and stop reading
                    allowed_remaining = MAX_RESPONSE_BYTES - (total_bytes - len(chunk))
                    if allowed_remaining > 0:
                        content_chunks.append(chunk[:allowed_remaining])
                    break
                content_chunks.append(chunk)

            response.close()
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            raw_body = b"".join(content_chunks).decode("utf-8", errors="replace")
            resp_headers = {k: v for k, v in response.headers.items()}

            return response.status_code, resp_headers, raw_body, elapsed_ms
