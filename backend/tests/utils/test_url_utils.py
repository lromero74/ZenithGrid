"""
Tests for backend/app/utils/url_utils.py

Covers ensure_url_scheme() and normalize_feed_url().
"""

from app.utils.url_utils import ensure_url_scheme, normalize_feed_url


class TestEnsureUrlScheme:
    """Tests for ensure_url_scheme()"""

    def test_bare_domain_gets_https(self):
        """Happy path: bare domain gets https:// prepended."""
        assert ensure_url_scheme("example.com") == "https://example.com"

    def test_scheme_relative_url_gets_https(self):
        """Scheme-relative URL (//domain) gets https: prefix."""
        assert ensure_url_scheme("//example.com/path") == "https://example.com/path"

    def test_existing_https_unchanged(self):
        """URL with https:// is returned as-is."""
        assert ensure_url_scheme("https://example.com") == "https://example.com"

    def test_existing_http_unchanged(self):
        """URL with http:// is returned as-is."""
        assert ensure_url_scheme("http://example.com") == "http://example.com"

    def test_empty_string_returns_empty(self):
        """Edge case: empty string returns empty string."""
        assert ensure_url_scheme("") == ""

    def test_whitespace_only_returns_empty(self):
        """Edge case: whitespace-only string is stripped to empty."""
        assert ensure_url_scheme("   ") == ""

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped before processing."""
        assert ensure_url_scheme("  example.com  ") == "https://example.com"

    def test_bare_domain_with_path(self):
        """Bare domain with path gets https:// prepended."""
        assert ensure_url_scheme("example.com/feed/rss") == "https://example.com/feed/rss"

    def test_bare_domain_with_port_urlparse_quirk(self):
        """Edge case: urlparse treats 'example.com:8080/path' as having
        scheme='example.com', so ensure_url_scheme does NOT add https://.
        This is a known urllib.parse limitation with bare domain:port URLs.
        """
        result = ensure_url_scheme("example.com:8080/path")
        # urlparse sees 'example.com' as the scheme — input returned as-is
        assert result == "example.com:8080/path"


class TestNormalizeFeedUrl:
    """Tests for normalize_feed_url()"""

    def test_basic_normalization(self):
        """Happy path: scheme and host are lowercased."""
        result = normalize_feed_url("HTTPS://Example.COM/feed")
        assert result == "https://example.com/feed"

    def test_trailing_slash_stripped(self):
        """Trailing slash on path is stripped."""
        result = normalize_feed_url("https://example.com/feed/")
        assert result == "https://example.com/feed"

    def test_root_path_preserved(self):
        """Root path (/) is preserved when there's no other path."""
        result = normalize_feed_url("https://example.com/")
        assert result == "https://example.com/"

    def test_query_params_sorted(self):
        """Query parameters are sorted alphabetically by key."""
        result = normalize_feed_url("https://example.com/feed?z=1&a=2&m=3")
        assert result == "https://example.com/feed?a=2&m=3&z=1"

    def test_bare_domain_normalized(self):
        """Bare domain without scheme gets https:// and normalized."""
        result = normalize_feed_url("Example.COM")
        assert result == "https://example.com/"

    def test_fragment_removed(self):
        """Fragment (#section) is removed during normalization."""
        result = normalize_feed_url("https://example.com/feed#section")
        assert result == "https://example.com/feed"

    def test_identical_urls_different_case_normalize_same(self):
        """Two URLs differing only by case normalize to the same value."""
        url1 = normalize_feed_url("https://CNN.com/RSS")
        url2 = normalize_feed_url("https://cnn.com/RSS")
        assert url1 == url2

    def test_identical_urls_different_param_order_normalize_same(self):
        """Two URLs with same params in different order normalize to same value."""
        url1 = normalize_feed_url("https://example.com/feed?b=2&a=1")
        url2 = normalize_feed_url("https://example.com/feed?a=1&b=2")
        assert url1 == url2

    def test_http_scheme_preserved(self):
        """HTTP scheme is preserved (not upgraded to HTTPS)."""
        result = normalize_feed_url("http://example.com/feed")
        assert result == "http://example.com/feed"

    def test_blank_query_values_preserved(self):
        """Blank query values are preserved during normalization."""
        result = normalize_feed_url("https://example.com/feed?key=&other=val")
        assert "key=" in result
        assert "other=val" in result

    def test_multi_value_query_params(self):
        """Edge case: repeated query key (tag=a&tag=b) is preserved."""
        result = normalize_feed_url("https://example.com/feed?tag=b&tag=a")
        assert "tag=a" in result
        assert "tag=b" in result

    def test_empty_string_input(self):
        """Edge case: empty string produces a minimal normalized URL."""
        # ensure_url_scheme("") returns "", urlparse("") gives empty parts
        result = normalize_feed_url("")
        # With empty input, scheme defaults to "https", path becomes "/"
        assert result == "https:///"

    def test_url_with_userinfo(self):
        """Edge case: URL with user:pass@ is preserved through normalization."""
        result = normalize_feed_url("https://user:pass@example.com/feed")
        assert "user:pass@example.com" in result
        assert result.startswith("https://")

    def test_url_with_port_preserved(self):
        """Edge case: port number is preserved after normalization."""
        result = normalize_feed_url("https://example.com:8080/feed/")
        assert "example.com:8080" in result
        assert result.endswith("/feed")

    def test_path_case_preserved(self):
        """Path casing is preserved (only scheme/host lowercased)."""
        result = normalize_feed_url("https://Example.COM/MyFeed/RSS")
        assert "/MyFeed/RSS" in result
        assert result.startswith("https://example.com")
