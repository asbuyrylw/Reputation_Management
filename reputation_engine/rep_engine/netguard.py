"""
Reputation Crowding-Out Engine -- SSRF / domain-safety guard
===========================================================
One reusable check run before ANY outbound crawl fetch (page fetch, robots.txt,
Firecrawl scrape, the Lighthouse subprocess target, and the crawl seed derived
from a business's stored domain).

What it blocks:
  1. Non-web schemes -- only http/https are allowed (no file://, gopher://, etc.).
  2. Hosts whose resolved IPs are not publicly routable: if ANY A/AAAA record is
     private / loopback / link-local / reserved / multicast / unspecified, the URL
     is rejected (defends DNS-rebinding-style internal pivots).
  3. Known cloud metadata endpoints (169.254.169.254 and friends).

Gated by env CRAWL_SSRF_GUARD (default '1'). Set CRAWL_SSRF_GUARD=0 to disable
(e.g. local dev against an internal staging host, or deterministic offline tests).
The env var is read at CALL TIME, not import time, so it can be toggled per-test.

Usage:
    from . import netguard
    netguard.assert_url_allowed(url)        # raises UnsafeURLError on rejection
    if netguard.is_safe_url(url): ...        # bool form
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

log = logging.getLogger("netguard")

ALLOWED_SCHEMES = {"http", "https"}

# Hostnames that map to cloud instance-metadata services. IP-literal metadata
# targets (169.254.169.254, fd00:ec2::254) are already covered by the link-local /
# reserved IP checks, but we name them explicitly for defense in depth and clearer
# rejection messages.
BLOCKED_HOSTNAMES = {
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
    "instance-data.ec2.internal",
}
BLOCKED_LITERAL_IPS = {
    "169.254.169.254",   # AWS / GCP / Azure / OpenStack IMDS
    "fd00:ec2::254",      # AWS IMDS over IPv6
    "100.100.100.200",    # Alibaba Cloud metadata
}


class UnsafeURLError(ValueError):
    """Raised when a URL is rejected by the SSRF guard. Subclasses ValueError so
    existing broad `except ValueError` handlers degrade gracefully."""


def _guard_enabled() -> bool:
    return os.getenv("CRAWL_SSRF_GUARD", "1") != "0"


def _ip_is_blocked(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        # Unparseable -> treat as unsafe (fail closed).
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
        # IPv4-mapped / 6to4 wrappers can smuggle private v4 space; unwrap & re-check.
        or (getattr(addr, "ipv4_mapped", None) is not None and _ip_is_blocked(str(addr.ipv4_mapped)))
    )


def _resolve(host: str) -> list[str]:
    """Resolve a hostname to the list of IP strings it maps to. Raises
    UnsafeURLError if resolution fails (fail closed)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeURLError(f"could not resolve host {host!r}: {e}")
    ips = []
    for fam, _type, _proto, _canon, sockaddr in infos:
        ips.append(sockaddr[0])
    return ips


def is_safe_url(url: str) -> bool:
    try:
        assert_url_allowed(url)
        return True
    except UnsafeURLError:
        return False


def assert_url_allowed(url: str) -> None:
    """Raise UnsafeURLError if `url` must not be fetched. No-op when the guard is
    disabled via CRAWL_SSRF_GUARD=0."""
    if not _guard_enabled():
        return
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme {scheme!r} not allowed (only http/https)")
    host = parsed.hostname  # already lowercased, strips brackets from IPv6 literals
    if not host:
        raise UnsafeURLError("URL has no host")
    host_l = host.lower()
    if host_l in BLOCKED_HOSTNAMES:
        raise UnsafeURLError(f"host {host_l!r} is a blocked metadata endpoint")
    if host_l in BLOCKED_LITERAL_IPS:
        raise UnsafeURLError(f"host {host_l!r} is a blocked metadata IP")
    # If the host is already an IP literal, check it directly (no DNS).
    try:
        ipaddress.ip_address(host_l)
        candidates = [host_l]
    except ValueError:
        candidates = _resolve(host_l)
    for ip in candidates:
        if ip in BLOCKED_LITERAL_IPS or _ip_is_blocked(ip):
            raise UnsafeURLError(
                f"host {host_l!r} resolves to disallowed address {ip}")
