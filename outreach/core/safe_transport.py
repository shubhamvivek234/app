"""
Safe Egress Transport with DNS Rebinding and SSRF Defense.
Pins outgoing TCP connections to pre-validated public IP addresses,
preventing Time-Of-Check to Time-Of-Use (TOCTOU) DNS rebinding attacks.
"""
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse
import httpcore
from httpcore._backends.anyio import AnyIOBackend
import httpx

logger = logging.getLogger(__name__)


class SSRFSecurityError(ValueError):
    """Raised when an outbound URL or IP violates egress security boundaries."""
    pass


# Blocked IPv4 and IPv6 networks (RFC 1918 + loopback + link-local + cloud metadata)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),     # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local / Cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),     # Private
    ipaddress.ip_network("192.0.0.0/24"),      # IETF Protocol
    ipaddress.ip_network("192.0.2.0/24"),      # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),    # Private
    ipaddress.ip_network("198.18.0.0/15"),     # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),   # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),    # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),       # Multicast
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved
    # IPv6
    ipaddress.ip_network("::/128"),            # Unspecified
    ipaddress.ip_network("::1/128"),           # Loopback
    ipaddress.ip_network("fc00::/7"),          # Unique local
    ipaddress.ip_network("fe80::/10"),         # Link-local
    ipaddress.ip_network("2001:db8::/32"),     # Documentation
]

_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
    "instance-data",
    "metadata",
    "fd00:ec2::254",
}


def is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address belongs to any blocked or private network range."""
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
        return True
    for blocked_net in _BLOCKED_NETWORKS:
        if ip in blocked_net:
            return True
    return False


def validate_webhook_url(url: str, *, allow_http: bool = False) -> None:
    """
    Validate that a user-supplied webhook destination is well-formed, uses HTTPS,
    contains no embedded credentials, and does not target metadata hostnames.
    """
    if not url or len(url) > 2048:
        raise SSRFSecurityError("Webhook URL must be between 1 and 2048 characters")

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise SSRFSecurityError(f"Malformed webhook URL: {exc}") from exc

    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if parsed.scheme not in allowed_schemes:
        raise SSRFSecurityError(f"Webhook URL must use HTTPS (received '{parsed.scheme}')")

    if parsed.username or parsed.password:
        raise SSRFSecurityError("Webhook URL must not include embedded credentials or userinfo")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise SSRFSecurityError("Webhook URL must contain a valid hostname")

    if hostname in _BLOCKED_HOSTNAMES:
        raise SSRFSecurityError(f"Blocked destination hostname: '{hostname}'")

    # If hostname is an IP literal, validate directly
    try:
        ip = ipaddress.ip_address(hostname)
        if is_ip_blocked(ip):
            raise SSRFSecurityError(f"Target IP {ip} is in a blocked/private range")
    except ValueError:
        # Not an IP literal, domain name will be resolved during connection pinning
        pass


class PinnedAsyncNetworkBackend(httpcore.AsyncNetworkBackend):
    """
    Custom httpcore network backend that resolves DNS once, validates all
    resolved IP addresses against SSRF blacklists, and binds the TCP socket
    directly to a pre-validated public IP address.
    """

    def __init__(self, *, allow_private_for_tests: bool = False) -> None:
        self.allow_private_for_tests = allow_private_for_tests
        self._anyio_backend = AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        hostname_clean = host.strip().lower()
        if hostname_clean in _BLOCKED_HOSTNAMES and not self.allow_private_for_tests:
            raise SSRFSecurityError(f"Connection blocked to metadata host: {hostname_clean}")

        # Resolve host to all available address infos
        try:
            addr_infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise SSRFSecurityError(f"DNS resolution failed for '{host}': {exc}") from exc

        if not addr_infos:
            raise SSRFSecurityError(f"No IP addresses resolved for '{host}'")

        validated_ips: list[str] = []
        for info in addr_infos:
            ip_str = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError as exc:
                raise SSRFSecurityError(f"Invalid IP address resolved: '{ip_str}'") from exc

            if not self.allow_private_for_tests and is_ip_blocked(ip):
                raise SSRFSecurityError(f"SSRF blocked: host '{host}' resolved to restricted IP {ip_str}")
            validated_ips.append(ip_str)

        # Pin the TCP socket directly to the first validated IP
        pinned_ip = validated_ips[0]
        return await self._anyio_backend.connect_tcp(
            pinned_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class SafeAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """
    httpx transport that enforces connection pinning to eliminate DNS rebinding.
    """

    def __init__(self, *args, allow_private_for_tests: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pool._network_backend = PinnedAsyncNetworkBackend(
            allow_private_for_tests=allow_private_for_tests
        )


def create_safe_client(
    *,
    timeout: float = 10.0,
    allow_private_for_tests: bool = False,
) -> httpx.AsyncClient:
    """
    Returns an httpx.AsyncClient equipped with:
    - DNS-pinned transport
    - Redirects disabled (follow_redirects=False)
    - Strict timeouts (connect/read/write)
    """
    transport = SafeAsyncHTTPTransport(allow_private_for_tests=allow_private_for_tests)
    client_timeout = httpx.Timeout(timeout, connect=5.0, read=timeout, write=5.0)
    return httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
        timeout=client_timeout,
    )
