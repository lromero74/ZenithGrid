"""URL normalization utilities for feed deduplication."""

from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def normalize_feed_url(url: str) -> str:
    """Normalize a feed URL for deduplication.

    Lowercase scheme/host, strip trailing slash, sort query params.
    """
    parsed = urlparse(url.strip())
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
