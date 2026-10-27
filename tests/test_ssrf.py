import socket
from unittest.mock import MagicMock, patch
import pytest

from app.core.ssrf import (
    SSRFProtectionError,
    execute_safe_request,
    resolve_and_validate_host,
    validate_url_syntax_and_scheme,
)


def test_scheme_validation():
    """Only HTTP and HTTPS schemes are permitted; all others are rejected."""
    # Permitted schemes
    validate_url_syntax_and_scheme("http://api.stripe.com/v1")
    validate_url_syntax_and_scheme("https://api.github.com/events")

    # Prohibited schemes
    with pytest.raises(SSRFProtectionError, match="Prohibited URL scheme 'file'"):
        validate_url_syntax_and_scheme("file:///etc/passwd")

    with pytest.raises(SSRFProtectionError, match="Prohibited URL scheme 'ftp'"):
        validate_url_syntax_and_scheme("ftp://ftp.example.com/data")

    with pytest.raises(SSRFProtectionError, match="Prohibited URL scheme 'gopher'"):
        validate_url_syntax_and_scheme("gopher://127.0.0.1:70")


def test_url_credentials_rejected():
    """URLs embedding userinfo credentials must be rejected."""
    with pytest.raises(SSRFProtectionError, match="URL credentials"):
        validate_url_syntax_and_scheme("http://admin:secret@api.example.com/v1")


def test_prohibited_hostnames_rejected():
    """Metadata and local internal hostnames are rejected at pre-flight check."""
    for host in ["localhost", "metadata.google.internal", "instance-data", "service.internal", "node.local"]:
        with pytest.raises(SSRFProtectionError):
            validate_url_syntax_and_scheme(f"http://{host}/api")


def test_loopback_and_private_ips_rejected():
    """Direct IP loopback and private addresses are rejected."""
    prohibited_ips = [
        "127.0.0.1",
        "127.0.0.2",
        "10.0.0.1",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",  # AWS/GCP/Azure metadata
        "0.0.0.0",
        "224.0.0.1",        # Multicast
        "::1",              # IPv6 loopback
        "fe80::1",          # IPv6 link-local
    ]
    for ip in prohibited_ips:
        with pytest.raises(SSRFProtectionError):
            resolve_and_validate_host(ip, 80)


def test_dns_resolution_to_prohibited_ip_rejected():
    """Hostnames that resolve to private or loopback IP addresses are blocked."""
    def fake_getaddrinfo(host, port, proto=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with pytest.raises(SSRFProtectionError, match="prohibited private or link-local range"):
            resolve_and_validate_host("evil-rebinding.example.com", 80)


def test_dns_resolution_to_metadata_ip_rejected():
    """Hostnames resolving to 169.254.169.254 cloud metadata are blocked."""
    def fake_getaddrinfo(host, port, proto=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))]

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with pytest.raises(SSRFProtectionError, match="prohibited private or link-local range"):
            resolve_and_validate_host("cloud-metadata-alias.com", 80)


def test_public_host_accepted():
    """Legitimate public domains resolving to public IPs pass validation."""
    def fake_getaddrinfo(host, port, proto=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        ips = resolve_and_validate_host("example.com", 80)
        assert "93.184.216.34" in ips


def test_redirect_to_loopback_prohibited():
    """Manual redirect validation catches and blocks redirects to private/loopback IPs."""
    # Mocking httpx send to return a 302 redirecting to http://127.0.0.1:8080/admin
    mock_resp_1 = MagicMock()
    mock_resp_1.status_code = 302
    mock_resp_1.headers = {"location": "http://127.0.0.1:8080/admin"}
    mock_resp_1.close = MagicMock()

    with patch("app.core.ssrf.resolve_and_validate_host") as mock_resolve:
        mock_resolve.return_value = ["93.184.216.34"]
        with patch("httpx.Client.send", return_value=mock_resp_1):
            with pytest.raises(SSRFProtectionError):
                execute_safe_request("http://api.example.com/start")


def test_oversized_response_body_truncated():
    """Response bodies exceeding MAX_RESPONSE_BYTES are truncated safely."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/plain"}
    mock_resp.close = MagicMock()
    # 2MB of chunks
    large_chunk = b"A" * 512 * 1024
    mock_resp.iter_bytes.return_value = [large_chunk, large_chunk, large_chunk, large_chunk]

    with patch("app.core.ssrf.resolve_and_validate_host", return_value=["93.184.216.34"]):
        with patch("httpx.Client.send", return_value=mock_resp):
            status_code, headers, body, latency = execute_safe_request("http://api.example.com/large")
            assert status_code == 200
            # Must not exceed 1MB (1,048,576 bytes)
            assert len(body.encode("utf-8")) <= 1024 * 1024


# ==============================================================================
# FOCUSED SSRF REGRESSION TESTS
# ==============================================================================

def test_ipv4_mapped_ipv6_addresses_rejected():
    """IPv4-mapped IPv6 addresses mapping to loopback, private, metadata, and CGNAT must be rejected."""
    prohibited_mapped_urls = [
        "http://[::ffff:127.0.0.1]/",        # loopback
        "http://[::ffff:7f00:1]/",          # loopback hex
        "http://[::ffff:10.0.0.1]/",         # RFC1918 10/8
        "http://[::ffff:a00:1]/",           # RFC1918 10/8 hex
        "http://[::ffff:172.16.0.1]/",      # RFC1918 172.16/12
        "http://[::ffff:192.168.1.1]/",     # RFC1918 192.168/16
        "http://[::ffff:169.254.169.254]/", # link-local / metadata
        "http://[::ffff:a9fe:a9fe]/",       # metadata hex
        "http://[::ffff:100.64.0.1]/",      # Carrier-grade NAT
        "http://[::ffff:0.0.0.0]/",         # unspecified
    ]

    for url in prohibited_mapped_urls:
        parsed = validate_url_syntax_and_scheme(url)
        port = parsed.port or 80
        with pytest.raises(SSRFProtectionError, match="prohibited"):
            resolve_and_validate_host(parsed.hostname, port)

    # Also verify DNS resolution returning an IPv4-mapped IPv6 address is caught
    def fake_getaddrinfo(host, port, proto=None):
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 80, 0, 0))]

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with pytest.raises(SSRFProtectionError, match="prohibited private or link-local range"):
            resolve_and_validate_host("mapped-domain.com", 80)


def test_mixed_public_and_prohibited_ips_rejected():
    """A hostname resolving to a mixture of public and prohibited IPv4/IPv6 addresses must be rejected."""
    # Scenario A: Public IPv4 + IPv4 loopback
    def dns_mixture_a(host, port, proto=None):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
        ]

    with patch("socket.getaddrinfo", side_effect=dns_mixture_a):
        with pytest.raises(SSRFProtectionError, match="prohibited private or link-local range"):
            resolve_and_validate_host("mixed-a.example.com", 80)

    # Scenario B: Public IPv4 + IPv6 loopback
    def dns_mixture_b(host, port, proto=None):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 80, 0, 0)),
        ]

    with patch("socket.getaddrinfo", side_effect=dns_mixture_b):
        with pytest.raises(SSRFProtectionError, match="prohibited private or link-local range"):
            resolve_and_validate_host("mixed-b.example.com", 80)

    # Scenario C: Public IPv6 + IPv4 metadata
    def dns_mixture_c(host, port, proto=None):
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 80, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80)),
        ]

    with patch("socket.getaddrinfo", side_effect=dns_mixture_c):
        with pytest.raises(SSRFProtectionError, match="prohibited private or link-local range"):
            resolve_and_validate_host("mixed-c.example.com", 80)


def test_redirect_to_private_ipv6_and_unsupported_schemes():
    """Redirects to private IPv4, IPv6 loopback, and unsupported schemes are rejected."""
    # 1. Redirect to private IPv4 (192.168.1.1)
    resp_private_v4 = MagicMock()
    resp_private_v4.status_code = 302
    resp_private_v4.headers = {"location": "http://192.168.1.1/admin"}
    resp_private_v4.close = MagicMock()

    with patch("app.core.ssrf.resolve_and_validate_host", side_effect=[["93.184.216.34"], SSRFProtectionError("Destination IP address 192.168.1.1 is prohibited.")]):
        with patch("httpx.Client.send", return_value=resp_private_v4):
            with pytest.raises(SSRFProtectionError, match="192.168.1.1 is prohibited"):
                execute_safe_request("http://api.example.com/step1")

    # 2. Redirect to IPv6 loopback ([::1])
    resp_loopback_v6 = MagicMock()
    resp_loopback_v6.status_code = 302
    resp_loopback_v6.headers = {"location": "http://[::1]:8080/metrics"}
    resp_loopback_v6.close = MagicMock()

    with patch("app.core.ssrf.resolve_and_validate_host", side_effect=[["93.184.216.34"], SSRFProtectionError("Destination IP address ::1 is prohibited.")]):
        with patch("httpx.Client.send", return_value=resp_loopback_v6):
            with pytest.raises(SSRFProtectionError, match="::1 is prohibited"):
                execute_safe_request("http://api.example.com/step1")

    # 3. Redirect to unsupported scheme: file://
    resp_file = MagicMock()
    resp_file.status_code = 302
    resp_file.headers = {"location": "file:///etc/shadow"}
    resp_file.close = MagicMock()

    with patch("app.core.ssrf.resolve_and_validate_host", return_value=["93.184.216.34"]):
        with patch("httpx.Client.send", return_value=resp_file):
            with pytest.raises(SSRFProtectionError, match="Prohibited URL scheme 'file'"):
                execute_safe_request("http://api.example.com/step1")

    # 4. Redirect to unsupported scheme: gopher://
    resp_gopher = MagicMock()
    resp_gopher.status_code = 307
    resp_gopher.headers = {"location": "gopher://127.0.0.1:6379/_INFO"}
    resp_gopher.close = MagicMock()

    with patch("app.core.ssrf.resolve_and_validate_host", return_value=["93.184.216.34"]):
        with patch("httpx.Client.send", return_value=resp_gopher):
            with pytest.raises(SSRFProtectionError, match="Prohibited URL scheme 'gopher'"):
                execute_safe_request("http://api.example.com/step1")


def test_alternate_ipv4_representations_windows():
    """Test and document alternate IPv4 representations on Windows environment and mock defense-in-depth."""
    # Actual Windows Winsock resolver behavior:
    # Winsock rejects non-canonical IP formats with [Errno 11001] getaddrinfo failed
    alternate_candidates = [
        "2130706433",      # Decimal integer for 127.0.0.1
        "0177.0.0.1",      # Octal for 127.0.0.1
        "0x7f.0.0.1",      # Hex dotted
        "0x7f000001",      # Hex dword
        "127.000.000.001", # Dotted with leading zeros
        "127.1",           # Truncated class A
        "127.0.1",         # Truncated class B
    ]

    for candidate in alternate_candidates:
        with pytest.raises(SSRFProtectionError) as exc_info:
            resolve_and_validate_host(candidate, 80)
        # On Windows, Winsock treats these as unresolvable hostnames
        assert "DNS resolution failed" in str(exc_info.value) or "prohibited" in str(exc_info.value)

    # Defense-in-depth verification:
    # If a POSIX resolver or custom nameserver expands an alternate representation (e.g. 0177.0.0.1)
    # into a canonical loopback IP ('127.0.0.1'), verify that SSRF validation catches it immediately.
    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]):
        with pytest.raises(SSRFProtectionError, match="prohibited private or link-local range"):
            resolve_and_validate_host("0177.0.0.1", 80)


def test_dns_rebinding_connection_pinned_to_validated_ip():
    """Verify that DNS rebinding is mitigated by ensuring the socket connects ONLY to the validated IP."""
    from app.core.ssrf import SSRFSafeBackend

    backend = SSRFSafeBackend()

    # Scenario 1: Rebinding during connect_tcp is trapped if DNS changes to private IP
    with patch("app.core.ssrf.resolve_and_validate_host", side_effect=SSRFProtectionError("Resolved address 127.0.0.1 is prohibited")):
        with pytest.raises(SSRFProtectionError, match="127.0.0.1 is prohibited"):
            backend.connect_tcp("rebind.evil.com", 80)

    # Scenario 2: Verify socket.create_connection is passed the validated IP, NOT the hostname
    with patch("app.core.ssrf.resolve_and_validate_host", return_value=["93.184.216.34"]):
        with patch("socket.create_connection") as mock_create_conn:
            mock_sock = MagicMock()
            mock_create_conn.return_value = mock_sock

            backend.connect_tcp("api.stripe.com", 443)

            # Assert connection target is pinned directly to the IP
            mock_create_conn.assert_called_once()
            called_address = mock_create_conn.call_args[0][0]
            assert called_address == ("93.184.216.34", 443), (
                f"Socket connected to {called_address} instead of validated IP!"
            )


def test_tls_hostname_verification_and_connection_isolation():
    """Verify that TLS wraps the pinned socket with the original hostname for SNI and cert check."""
    from app.core.ssrf import SSRFSafeBackend, SSRFSafeTransport

    backend = SSRFSafeBackend()

    # 1. TLS verification uses original hostname
    with patch("app.core.ssrf.resolve_and_validate_host", return_value=["93.184.216.34"]):
        with patch("socket.create_connection") as mock_create_conn:
            mock_sock = MagicMock()
            mock_create_conn.return_value = mock_sock

            stream = backend.connect_tcp("api.stripe.com", 443)

            # Now test TLS negotiation on the stream
            mock_ssl_context = MagicMock()
            stream.start_tls(ssl_context=mock_ssl_context, server_hostname="api.stripe.com")

            mock_ssl_context.wrap_socket.assert_called_once()
            wrap_kwargs = mock_ssl_context.wrap_socket.call_args[1]
            assert wrap_kwargs.get("server_hostname") == "api.stripe.com"

    # 2. Connection isolation & zero retries
    transport = SSRFSafeTransport()
    assert transport._pool._retries == 0, "Transport pool must have 0 retries to prevent unvalidated retry SSRF"


# ==============================================================================
# NAT64 / DNS64 (RFC 6052) REGRESSION TESTS
# ==============================================================================

def test_nat64_public_ipv4_embedded_accepted():
    """NAT64 addresses embedding public IPv4 addresses must be accepted."""
    from app.core.ssrf import is_ip_prohibited
    import ipaddress

    # 64:ff9b::3d3:6ae8 embeds 3.211.106.232 (public AWS IPv4)
    ip_pub1 = ipaddress.ip_address("64:ff9b::3d3:6ae8")
    assert not is_ip_prohibited(ip_pub1), "Public IPv4 embedded in NAT64 must not be prohibited"

    # 64:ff9b::5db8:d822 embeds 93.184.216.34 (public example.com IPv4)
    ip_pub2 = ipaddress.ip_address("64:ff9b::5db8:d822")
    assert not is_ip_prohibited(ip_pub2), "Public IPv4 embedded in NAT64 must not be prohibited"

    # Direct URL with public NAT64 IPv6
    parsed = validate_url_syntax_and_scheme("http://[64:ff9b::5db8:d822]/status")
    ips = resolve_and_validate_host(parsed.hostname, 80)
    assert "64:ff9b::5db8:d822" in ips

    # DNS resolution returning public NAT64 address
    def fake_dns(host, port, proto=None):
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("64:ff9b::3d3:6ae8", 80, 0, 0))]

    with patch("socket.getaddrinfo", side_effect=fake_dns):
        resolved = resolve_and_validate_host("nat64-public.example.com", 80)
        assert "64:ff9b::3d3:6ae8" in resolved


def test_nat64_prohibited_ipv4_embedded_rejected():
    """NAT64 addresses embedding loopback, private, link-local, or CGNAT addresses must be rejected."""
    from app.core.ssrf import is_ip_prohibited
    import ipaddress

    prohibited_nat64_cases = [
        ("64:ff9b::7f00:1", "127.0.0.1 (loopback)"),
        ("64:ff9b::7f00:2", "127.0.0.2 (loopback)"),
        ("64:ff9b::a00:1", "10.0.0.1 (RFC 1918 private)"),
        ("64:ff9b::ac10:1", "172.16.0.1 (RFC 1918 private)"),
        ("64:ff9b::c0a8:101", "192.168.1.1 (RFC 1918 private)"),
        ("64:ff9b::a9fe:a9fe", "169.254.169.254 (cloud metadata)"),
        ("64:ff9b::6440:1", "100.64.0.1 (CGNAT)"),
        ("64:ff9b::0", "0.0.0.0 (unspecified)"),
        ("64:ff9b::ffff:ffff", "255.255.255.255 (broadcast)"),
        ("64:ff9b::e000:1", "224.0.0.1 (multicast)"),
    ]

    for ip_str, desc in prohibited_nat64_cases:
        ip = ipaddress.ip_address(ip_str)
        assert is_ip_prohibited(ip), f"NAT64 embedding {desc} should be prohibited"

        parsed = validate_url_syntax_and_scheme(f"http://[{ip_str}]/admin")
        with pytest.raises(SSRFProtectionError, match="prohibited"):
            resolve_and_validate_host(parsed.hostname, 80)

        # Also verify rejection via DNS resolution
        def fake_dns(host, port, proto=None, target=ip_str):
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (target, 80, 0, 0))]

        with patch("socket.getaddrinfo", side_effect=fake_dns):
            with pytest.raises(SSRFProtectionError, match="prohibited"):
                resolve_and_validate_host("nat64-prohibited.example.com", 80)


def test_ordinary_public_ipv4_and_ipv6_accepted():
    """Ordinary public IPv4 and native IPv6 addresses must be accepted."""
    from app.core.ssrf import is_ip_prohibited
    import ipaddress

    public_ips = [
        "93.184.216.34",
        "104.21.59.19",
        "2606:2800:220:1:248:1893:25c8:1946",
        "2606:4700:3037::ac43:a797",
    ]

    for ip_str in public_ips:
        ip = ipaddress.ip_address(ip_str)
        assert not is_ip_prohibited(ip), f"{ip_str} should be allowed as public"

        parsed = validate_url_syntax_and_scheme(f"http://[{ip_str}]/" if ":" in ip_str else f"http://{ip_str}/")
        ips = resolve_and_validate_host(parsed.hostname, 80)
        assert ip_str in ips


def test_mixed_dns_nat64_answers():
    """Mixed DNS answers combining public IPv4 with valid NAT64 vs prohibited NAT64."""
    # Scenario A: Public IPv4 + Public NAT64 IPv6 -> Allowed
    def dns_valid_mix(host, port, proto=None):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("64:ff9b::3d3:6ae8", 80, 0, 0)),
        ]

    with patch("socket.getaddrinfo", side_effect=dns_valid_mix):
        resolved = resolve_and_validate_host("valid-dual-stack.example.com", 80)
        assert "93.184.216.34" in resolved
        assert "64:ff9b::3d3:6ae8" in resolved

    # Scenario B: Public IPv4 + Prohibited NAT64 (embedding 127.0.0.1) -> Rejected
    def dns_evil_nat64_mix(host, port, proto=None):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("64:ff9b::7f00:1", 80, 0, 0)),
        ]

    with patch("socket.getaddrinfo", side_effect=dns_evil_nat64_mix):
        with pytest.raises(SSRFProtectionError, match="prohibited private or link-local range"):
            resolve_and_validate_host("evil-nat64-mix.example.com", 80)


def test_ssrf_safe_backend_multi_ip_fallback():
    """SSRFSafeBackend falls back to subsequent validated IPs when first route is unreachable."""
    from app.core.ssrf import SSRFSafeBackend

    backend = SSRFSafeBackend()
    validated_ips = ["64:ff9b::3d3:6ae8", "34.201.225.204"]

    with patch("app.core.ssrf.resolve_and_validate_host", return_value=validated_ips):
        with patch("httpcore._backends.sync.SyncBackend.connect_tcp") as mock_connect:
            # First IP raises network unreachable, second succeeds
            mock_stream = MagicMock()
            mock_connect.side_effect = [
                OSError(101, "Network is unreachable"),
                mock_stream,
            ]

            stream = backend.connect_tcp("httpbin.org", 443)
            assert stream == mock_stream
            assert backend.validated_ip == "34.201.225.204"
            assert mock_connect.call_count == 2
