"""URL normalization utilities for feed deduplication."""

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
