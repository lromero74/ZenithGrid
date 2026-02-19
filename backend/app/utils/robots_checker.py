"""
robots.txt checker for custom news source validation.

Uses urllib.robotparser (stdlib) for parsing and httpx for async fetching.
Returns a RobotsPolicy with RSS/scraping permissions and crawl delay.
"""

import logging
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "ZenithGrid/1.0"
MAX_ROBOTS_SIZE = 512 * 1024  # 512KB
FETCH_TIMEOUT = 10  # seconds

# Common RSS feed paths to check
RSS_PATHS = ["/feed", "/rss", "/atom.xml", "/feeds/", "/feed/"]

# Common article/content paths to check
SCRAPE_PATHS = ["/", "/article/", "/news/", "/blog/", "/posts/"]


@dataclass
class RobotsPolicy:
    domain: str
    robots_found: bool
    robots_fetch_error: str | None
    rss_allowed: bool
    scraping_allowed: bool
    crawl_delay_seconds: int
    summary: str


def _extract_robots_url(url: str) -> str:
    """Extract the robots.txt URL from any URL on the domain."""
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path.split("/")[0]
    return f"{scheme}://{netloc}/robots.txt"


def _extract_domain(url: str) -> str:
    """Extract domain from a URL."""
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/")[0]


def _parse_crawl_delay(robots_text: str) -> int:
    """Extract crawl-delay for our agent or * from raw robots.txt text.

    RobotFileParser.crawl_delay() only works if there's a matching
    user-agent entry, so we parse manually as a fallback.
    """
    lines = robots_text.lower().splitlines()
    current_agent = None
    our_delay = None
    wildcard_delay = None

    for line in lines:
        line = line.strip()
        if line.startswith("user-agent:"):
            current_agent = line.split(":", 1)[1].strip()
        elif line.startswith("crawl-delay:"):
            try:
                delay = int(float(line.split(":", 1)[1].strip()))
            except (ValueError, IndexError):
                continue
            if current_agent == "zenithgrid/1.0":
                our_delay = delay
            elif current_agent == "*":
                wildcard_delay = delay

    if our_delay is not None:
        return our_delay
    if wildcard_delay is not None:
        return wildcard_delay
    return 0


def _check_paths(parser: RobotFileParser, paths: list[str]) -> bool:
    """Check if any of the given paths are allowed."""
    for path in paths:
        if parser.can_fetch(USER_AGENT, path):
            return True
    return False


def _build_summary(policy_rss: bool, policy_scrape: bool,
                   crawl_delay: int, error: str | None) -> str:
    """Build a human-readable one-line summary."""
    if error:
        return f"Could not fetch robots.txt ({error}); defaults applied"

    parts = []
    if policy_rss and policy_scrape:
        parts.append("RSS and article scraping allowed")
    elif policy_rss:
        parts.append("RSS allowed; article scraping blocked")
    else:
        parts.append("Bot access blocked")

    if crawl_delay > 0:
        parts.append(f"{crawl_delay}s crawl delay")

    return "; ".join(parts)


async def check_robots_txt(url: str) -> RobotsPolicy:
    """Fetch and parse robots.txt for the given URL's domain.

    Returns a RobotsPolicy with RSS/scraping permissions and crawl delay.

    Edge cases:
    - robots.txt 404 → permissive (all allowed)
    - Fetch timeout/error → warn but allow with defaults
    - Content > 512KB → reject as invalid
    """
    domain = _extract_domain(url)
    robots_url = _extract_robots_url(url)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=FETCH_TIMEOUT,
        ) as client:
            response = await client.get(robots_url)

        if response.status_code == 404:
            return RobotsPolicy(
                domain=domain,
                robots_found=False,
                robots_fetch_error=None,
                rss_allowed=True,
                scraping_allowed=True,
                crawl_delay_seconds=0,
                summary="No robots.txt found; all access permitted",
            )

        if response.status_code >= 400:
            return RobotsPolicy(
                domain=domain,
                robots_found=False,
                robots_fetch_error=f"HTTP {response.status_code}",
                rss_allowed=True,
                scraping_allowed=True,
                crawl_delay_seconds=0,
                summary=_build_summary(
                    True, True, 0, f"HTTP {response.status_code}"
                ),
            )

        content = response.text
        if len(content.encode("utf-8", errors="replace")) > MAX_ROBOTS_SIZE:
            return RobotsPolicy(
                domain=domain,
                robots_found=False,
                robots_fetch_error="robots.txt exceeds 512KB size limit",
                rss_allowed=True,
                scraping_allowed=True,
                crawl_delay_seconds=0,
                summary=_build_summary(
                    True, True, 0, "robots.txt too large"
                ),
            )

        # Parse with RobotFileParser
        parser = RobotFileParser()
        parser.parse(content.splitlines())

        rss_allowed = _check_paths(parser, RSS_PATHS)
        scraping_allowed = _check_paths(parser, SCRAPE_PATHS)
        crawl_delay = _parse_crawl_delay(content)

        return RobotsPolicy(
            domain=domain,
            robots_found=True,
            robots_fetch_error=None,
            rss_allowed=rss_allowed,
            scraping_allowed=scraping_allowed,
            crawl_delay_seconds=crawl_delay,
            summary=_build_summary(
                rss_allowed, scraping_allowed, crawl_delay, None
            ),
        )

    except httpx.TimeoutException:
        logger.warning(f"Timeout fetching robots.txt for {domain}")
        return RobotsPolicy(
            domain=domain,
            robots_found=False,
            robots_fetch_error="Connection timed out",
            rss_allowed=True,
            scraping_allowed=True,
            crawl_delay_seconds=0,
            summary=_build_summary(True, True, 0, "Connection timed out"),
        )
    except Exception as exc:
        logger.warning(f"Error fetching robots.txt for {domain}: {exc}")
        return RobotsPolicy(
            domain=domain,
            robots_found=False,
            robots_fetch_error=str(exc),
            rss_allowed=True,
            scraping_allowed=True,
            crawl_delay_seconds=0,
            summary=_build_summary(True, True, 0, str(exc)),
        )
