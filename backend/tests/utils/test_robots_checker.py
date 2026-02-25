"""
Tests for backend/app/utils/robots_checker.py

Covers helper functions and the main check_robots_txt() coroutine.
All HTTP calls are mocked — no real network access.
"""

import ssl

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.utils.robots_checker import (
    RobotsPolicy,
    _friendly_error,
    _extract_robots_url,
    _extract_domain,
    _parse_crawl_delay,
    _check_paths,
    _build_summary,
    check_robots_txt,
)


# ---------------------------------------------------------------------------
# _friendly_error
# ---------------------------------------------------------------------------


class TestFriendlyError:
    """Tests for _friendly_error()"""

    def test_ssl_error_returns_ssl_message(self):
        """SSL errors produce user-friendly SSL message."""
        exc = ssl.SSLError("certificate verify failed")
        assert "SSL/TLS connection failed" in _friendly_error(exc)

    def test_dns_error_returns_domain_not_found(self):
        """DNS failures produce domain-not-found message."""
        exc = OSError("Name or service not known")
        assert "Domain not found" in _friendly_error(exc)

    def test_getaddrinfo_error(self):
        """getaddrinfo failures produce domain-not-found message."""
        exc = OSError("getaddrinfo failed")
        assert "Domain not found" in _friendly_error(exc)

    def test_no_address_error(self):
        """No address produces no-DNS-records message."""
        exc = OSError("No address associated with hostname")
        assert "no DNS records" in _friendly_error(exc)

    def test_connection_refused(self):
        """Connection refused returns server-down message."""
        exc = OSError("Connection refused")
        assert "Connection refused" in _friendly_error(exc)

    def test_connection_reset(self):
        """Connection reset returns reset message."""
        exc = OSError("Connection reset by peer")
        assert "Connection reset" in _friendly_error(exc)

    def test_httpx_connect_error_recurses_to_cause(self):
        """httpx.ConnectError delegates to its __cause__."""
        inner = OSError("Name or service not known")
        outer = httpx.ConnectError("connect error")
        outer.__cause__ = inner
        result = _friendly_error(outer)
        assert "Domain not found" in result

    def test_httpx_connect_error_no_cause(self):
        """httpx.ConnectError without __cause__ gives generic message."""
        exc = httpx.ConnectError("connect error")
        exc.__cause__ = None
        assert _friendly_error(exc) == "Could not connect to domain"

    def test_long_message_truncated(self):
        """Messages over 120 chars get truncated with ellipsis."""
        exc = Exception("x" * 200)
        result = _friendly_error(exc)
        assert len(result) == 120
        assert result.endswith("...")

    def test_short_message_returned_as_is(self):
        """Short messages are returned unchanged."""
        exc = Exception("some error")
        assert _friendly_error(exc) == "some error"


# ---------------------------------------------------------------------------
# _extract_robots_url / _extract_domain
# ---------------------------------------------------------------------------


class TestExtractRobotsUrl:
    """Tests for _extract_robots_url()"""

    def test_full_url(self):
        """Extracts robots.txt URL from a full URL."""
        result = _extract_robots_url("https://example.com/some/page")
        assert result == "https://example.com/robots.txt"

    def test_with_port(self):
        """Preserves port in robots.txt URL."""
        result = _extract_robots_url("http://example.com:8080/page")
        assert result == "http://example.com:8080/robots.txt"

    def test_bare_domain_with_scheme(self):
        """Works with domain + scheme, no path."""
        result = _extract_robots_url("https://example.com")
        assert result == "https://example.com/robots.txt"


class TestExtractDomain:
    """Tests for _extract_domain()"""

    def test_full_url(self):
        """Extracts domain from a full URL."""
        assert _extract_domain("https://example.com/path") == "example.com"

    def test_with_port(self):
        """Preserves port in domain extraction."""
        assert _extract_domain("https://example.com:443/path") == "example.com:443"

    def test_bare_domain_no_scheme(self):
        """Bare domain (no scheme) falls back to path splitting."""
        assert _extract_domain("example.com") == "example.com"


# ---------------------------------------------------------------------------
# _parse_crawl_delay
# ---------------------------------------------------------------------------


class TestParseCrawlDelay:
    """Tests for _parse_crawl_delay()"""

    def test_wildcard_delay(self):
        """Picks up crawl-delay for wildcard user-agent."""
        robots = "User-agent: *\nCrawl-delay: 5\n"
        assert _parse_crawl_delay(robots) == 5

    def test_specific_agent_preferred_over_wildcard(self):
        """Our specific agent delay takes priority over wildcard."""
        robots = (
            "User-agent: *\nCrawl-delay: 10\n\n"
            "User-agent: ZenithGrid/1.0\nCrawl-delay: 2\n"
        )
        assert _parse_crawl_delay(robots) == 2

    def test_no_crawl_delay_returns_zero(self):
        """Missing crawl-delay returns 0."""
        robots = "User-agent: *\nDisallow: /private\n"
        assert _parse_crawl_delay(robots) == 0

    def test_float_delay_truncated_to_int(self):
        """Float crawl-delay values are truncated to int."""
        robots = "User-agent: *\nCrawl-delay: 3.7\n"
        assert _parse_crawl_delay(robots) == 3

    def test_invalid_delay_value_ignored(self):
        """Non-numeric crawl-delay is silently ignored."""
        robots = "User-agent: *\nCrawl-delay: abc\n"
        assert _parse_crawl_delay(robots) == 0

    def test_case_insensitive(self):
        """Parsing is case-insensitive for directives."""
        robots = "User-Agent: *\nCrawl-Delay: 7\n"
        assert _parse_crawl_delay(robots) == 7

    def test_empty_string_returns_zero(self):
        """Empty robots.txt string returns 0."""
        assert _parse_crawl_delay("") == 0

    def test_crawl_delay_without_user_agent_ignored(self):
        """Crawl-delay line without preceding user-agent is ignored."""
        robots = "Crawl-delay: 5\n"
        assert _parse_crawl_delay(robots) == 0

    def test_multiple_agents_with_delays(self):
        """Multiple user-agents: only our agent and wildcard matter."""
        robots = (
            "User-agent: Googlebot\nCrawl-delay: 99\n\n"
            "User-agent: *\nCrawl-delay: 3\n"
        )
        # Googlebot's delay is irrelevant; wildcard = 3
        assert _parse_crawl_delay(robots) == 3


# ---------------------------------------------------------------------------
# _check_paths
# ---------------------------------------------------------------------------


class TestCheckPaths:
    """Tests for _check_paths()"""

    def test_all_allowed(self):
        """Returns True when all paths are allowed."""
        from urllib.robotparser import RobotFileParser
        parser = RobotFileParser()
        parser.parse(["User-agent: *", "Allow: /"])
        assert _check_paths(parser, ["/feed", "/rss"]) is True

    def test_all_blocked(self):
        """Returns False when all paths are disallowed."""
        from urllib.robotparser import RobotFileParser
        parser = RobotFileParser()
        parser.parse([
            "User-agent: *",
            "Disallow: /feed",
            "Disallow: /rss",
        ])
        assert _check_paths(parser, ["/feed", "/rss"]) is False

    def test_partial_allowed(self):
        """Returns True if at least one path is allowed."""
        from urllib.robotparser import RobotFileParser
        parser = RobotFileParser()
        parser.parse([
            "User-agent: *",
            "Disallow: /feed",
            "Allow: /rss",
        ])
        assert _check_paths(parser, ["/feed", "/rss"]) is True

    def test_empty_paths_list_returns_false(self):
        """Empty paths list always returns False (no paths to check)."""
        from urllib.robotparser import RobotFileParser
        parser = RobotFileParser()
        parser.parse(["User-agent: *", "Allow: /"])
        assert _check_paths(parser, []) is False


# ---------------------------------------------------------------------------
# _build_summary
# ---------------------------------------------------------------------------


class TestBuildSummary:
    """Tests for _build_summary()"""

    def test_rss_and_scraping_allowed(self):
        """Both RSS and scraping allowed shows combined message."""
        result = _build_summary(True, True, 0, None)
        assert result == "RSS and article scraping allowed"

    def test_rss_only(self):
        """RSS allowed but scraping blocked shows partial message."""
        result = _build_summary(True, False, 0, None)
        assert "RSS allowed" in result
        assert "scraping blocked" in result

    def test_all_blocked(self):
        """Neither RSS nor scraping shows blocked message."""
        result = _build_summary(False, False, 0, None)
        assert result == "Bot access blocked"

    def test_crawl_delay_appended(self):
        """Crawl delay is appended to summary when > 0."""
        result = _build_summary(True, True, 5, None)
        assert "5s crawl delay" in result

    def test_error_message(self):
        """Error overrides normal summary."""
        result = _build_summary(True, True, 0, "Connection timed out")
        assert "Could not fetch robots.txt" in result
        assert "Connection timed out" in result

    def test_rss_only_with_crawl_delay(self):
        """RSS allowed + scraping blocked + crawl delay shows both parts."""
        result = _build_summary(True, False, 10, None)
        assert "RSS allowed" in result
        assert "scraping blocked" in result
        assert "10s crawl delay" in result

    def test_zero_crawl_delay_not_shown(self):
        """Zero crawl delay is not appended to the summary."""
        result = _build_summary(True, True, 0, None)
        assert "crawl delay" not in result


# ---------------------------------------------------------------------------
# check_robots_txt (async, mocked HTTP)
# ---------------------------------------------------------------------------


class TestCheckRobotsTxt:
    """Tests for check_robots_txt() — the main async function."""

    @pytest.mark.asyncio
    async def test_valid_robots_txt_all_allowed(self):
        """Happy path: robots.txt exists and allows everything."""
        robots_body = "User-agent: *\nAllow: /\n"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = robots_body

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://example.com")

        assert isinstance(policy, RobotsPolicy)
        assert policy.domain == "example.com"
        assert policy.robots_found is True
        assert policy.rss_allowed is True
        assert policy.scraping_allowed is True
        assert policy.robots_fetch_error is None

    @pytest.mark.asyncio
    async def test_robots_404_all_permitted(self):
        """robots.txt returning 404 means all access is permitted."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://example.com")

        assert policy.robots_found is False
        assert policy.rss_allowed is True
        assert policy.scraping_allowed is True
        assert "No robots.txt found" in policy.summary

    @pytest.mark.asyncio
    async def test_robots_server_error(self):
        """HTTP 500 returns permissive policy with error noted."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://example.com")

        assert policy.robots_found is False
        assert policy.robots_fetch_error == "HTTP 500"
        assert policy.rss_allowed is True

    @pytest.mark.asyncio
    async def test_oversized_robots_txt(self):
        """robots.txt exceeding 512KB returns error policy."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "x" * (513 * 1024)  # > 512KB

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://example.com")

        assert policy.robots_found is False
        assert "512KB" in policy.robots_fetch_error

    @pytest.mark.asyncio
    async def test_timeout_returns_permissive_with_warning(self):
        """Timeout returns permissive policy (domain might work later)."""
        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://slow-domain.com")

        assert policy.robots_found is False
        assert policy.robots_fetch_error == "Connection timed out"
        assert policy.rss_allowed is True
        assert policy.scraping_allowed is True

    @pytest.mark.asyncio
    async def test_connect_error_blocks_access(self):
        """ConnectError (DNS/SSL failure) blocks RSS and scraping."""
        exc = httpx.ConnectError("Name or service not known")
        exc.__cause__ = OSError("Name or service not known")

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(side_effect=exc)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://nonexistent.invalid")

        assert policy.rss_allowed is False
        assert policy.scraping_allowed is False
        assert "Domain not found" in policy.robots_fetch_error

    @pytest.mark.asyncio
    async def test_generic_exception_with_connection_keyword_blocks(self):
        """Generic exception containing connection keywords blocks access."""
        exc = Exception("SSL certificate verification failed")

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(side_effect=exc)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://bad-cert.example.com")

        assert policy.rss_allowed is False
        assert policy.scraping_allowed is False

    @pytest.mark.asyncio
    async def test_generic_exception_without_connection_keyword_allows(self):
        """Generic exception without connection keywords allows access."""
        exc = Exception("unexpected parse error")

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(side_effect=exc)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://example.com")

        assert policy.rss_allowed is True
        assert policy.scraping_allowed is True

    @pytest.mark.asyncio
    async def test_robots_with_crawl_delay(self):
        """Crawl delay is parsed from robots.txt content."""
        robots_body = "User-agent: *\nAllow: /\nCrawl-delay: 10\n"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = robots_body

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://example.com")

        assert policy.crawl_delay_seconds == 10

    @pytest.mark.asyncio
    async def test_bare_domain_handled(self):
        """Bare domain (no scheme) is handled by ensure_url_scheme."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("example.com")

        assert policy.domain == "example.com"
        assert policy.rss_allowed is True

    @pytest.mark.asyncio
    async def test_robots_blocks_rss_allows_scraping(self):
        """robots.txt that blocks RSS paths but allows article scraping."""
        robots_body = (
            "User-agent: *\n"
            "Disallow: /feed\n"
            "Disallow: /rss\n"
            "Disallow: /atom.xml\n"
            "Disallow: /feeds/\n"
            "Disallow: /feed/\n"
            "Allow: /\n"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = robots_body

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://example.com")

        assert policy.robots_found is True
        assert policy.rss_allowed is False
        assert policy.scraping_allowed is True

    @pytest.mark.asyncio
    async def test_robots_disallow_all(self):
        """robots.txt that disallows everything blocks both RSS and scraping."""
        robots_body = "User-agent: *\nDisallow: /\n"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = robots_body

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://strict-site.com")

        assert policy.robots_found is True
        assert policy.rss_allowed is False
        assert policy.scraping_allowed is False
        assert "Bot access blocked" in policy.summary

    @pytest.mark.asyncio
    async def test_http_403_returns_permissive_with_error(self):
        """HTTP 403 is treated as >=400 error, returns permissive policy."""
        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("app.utils.robots_checker.httpx.AsyncClient") as MockClient:
            ctx = AsyncMock()
            ctx.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            policy = await check_robots_txt("https://example.com")

        assert policy.robots_found is False
        assert policy.robots_fetch_error == "HTTP 403"
        assert policy.rss_allowed is True
        assert policy.scraping_allowed is True
