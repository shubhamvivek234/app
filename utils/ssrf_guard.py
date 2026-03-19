"""
Phase 0.12 — SSRF Guard.
Call is_safe_url() before ANY worker HTTP request to a user-supplied URL.
Blocks all private IP ranges, IPv6 loopback, and cloud metadata endpoints.
"""
import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Blocked network ranges (RFC 1918 + link-local + loopback + cloud metadata)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("169.254.0.0/16"),    # link-local (cloud metadata)
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),     # CGNAT
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("240.0.0.0/4"),
    # IPv6
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]

_ALLOWED_SCHEMES = {"https", "http"}
_MAX_URL_LENGTH = 2048


def is_safe_url(url: str) -> bool:
    """
    Returns True only if the URL is safe to fetch (no SSRF risk).
    Must return False for any private/internal IP, metadata endpoint,
    disallowed scheme, or malformed URL.
    """
    if not url or len(url) > _MAX_URL_LENGTH:
        logger.warning("SSRF guard: URL rejected (empty or too long)")
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        logger.warning("SSRF guard: URL parse failed: %s", url[:100])
        return False

    if parsed.scheme not in _ALLOWED_SCHEMES:
        logger.warning("SSRF guard: disallowed scheme '%s'", parsed.scheme)
        return False

    hostname = parsed.hostname
    if not hostname:
        logger.warning("SSRF guard: no hostname in URL")
        return False

    # Block cloud metadata endpoints explicitly
    if hostname in ("metadata.google.internal", "169.254.169.254", "fd00:ec2::254"):
        logger.warning("SSRF guard: cloud metadata endpoint blocked")
        return False

    # Resolve hostname to IPs and check each
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        logger.warning("SSRF guard: DNS resolution failed for '%s'", hostname)
        return False

    for addr_info in addr_infos:
        ip_str = addr_info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            logger.warning("SSRF guard: invalid IP '%s'", ip_str)
            return False

        for blocked_net in _BLOCKED_NETWORKS:
            if ip in blocked_net:
                logger.warning("SSRF guard: IP %s is in blocked range %s", ip, blocked_net)
                return False

    return True


def assert_safe_url(url: str) -> None:
    """Raises ValueError if the URL is not safe. Use in worker code."""
    if not is_safe_url(url):
        raise ValueError(f"SSRF guard blocked URL: {url[:100]}")
