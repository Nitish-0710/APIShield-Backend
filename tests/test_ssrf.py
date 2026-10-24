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
