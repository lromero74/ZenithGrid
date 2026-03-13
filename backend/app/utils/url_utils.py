"""URL normalization and security utilities for feed deduplication and SSRF protection."""

import ipaddress
import socket
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def ensure_url_scheme(url: str) -> str:
    """Ensure a URL has a scheme. Adds https:// if missing.

    Handles bare domains (cnn.com), scheme-relative (//cnn.com),
    and URLs that already have a scheme.
    """
    url = url.strip()
    if not url:
        return url
    if url.startswith("//"):
        return "https:" + url
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
    return url


def normalize_feed_url(url: str) -> str:
    """Normalize a feed URL for deduplication.

    Lowercase scheme/host, strip trailing slash, sort query params.
    """
    parsed = urlparse(ensure_url_scheme(url))
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    # Sort query params for consistent comparison
    params = parse_qs(parsed.query, keep_blank_values=True)
    sorted_query = urlencode(
        sorted(
            (k, v[0] if len(v) == 1 else v)
            for k, v in params.items()
        ),
        doseq=True,
    )
    return urlunparse((scheme, netloc, path, "", sorted_query, ""))


# SSRF-blocked hostnames (case-insensitive, checked after lowering)
_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}


def validate_url_not_internal(url: str) -> None:
    """Raise ValueError if URL targets an internal/private/loopback address.

    Resolves the hostname to detect DNS rebinding to private IPs.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Blocked scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("No hostname in URL")

    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Blocked hostname: {hostname}")

    # Resolve hostname and check all returned IPs
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError(f"DNS resolution failed for: {hostname}")

    for family, _type, _proto, _canonname, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError(f"Blocked internal IP {ip_str} for hostname {hostname}")
        # AWS metadata endpoint (link-local but explicit for clarity)
        if ip_str == "169.254.169.254":
            raise ValueError(f"Blocked AWS metadata endpoint for hostname {hostname}")
