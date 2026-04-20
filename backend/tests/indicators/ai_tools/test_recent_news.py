"""Tests for the get_recent_news tool.

Covers:
- Happy path — returns news articles matching the base currency, newest first
- Filter — articles outside max_age_hours are excluded
- Filter — limit is respected and clamped
- Match — base ticker expanded to full-name aliases (BTC → Bitcoin, etc.)
- Edge — no matches returns empty list
"""

from datetime import datetime, timedelta

from app.indicators.ai_tools import REGISTRY, ToolContext, execute
from app.models import NewsArticle


async def _make_article(db, *, title, summary=None, hours_ago=1, source="cointelegraph"):
    published = datetime.utcnow() - timedelta(hours=hours_ago)
    article = NewsArticle(
        title=title,
        summary=summary,
        url=f"https://example.com/{title.replace(' ', '-').lower()}-{hours_ago}",
        source=source,
        published_at=published,
        category="CryptoCurrency",
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article


class TestGetRecentNews:
    async def test_happy_path_matches_base_ticker(self, db_session):
        await _make_article(db_session, title="ETH hits new all-time high", hours_ago=2)
        await _make_article(db_session, title="Random DOGE update", hours_ago=2)
        await _make_article(db_session, title="ETH devs push upgrade", hours_ago=1)

        ctx = ToolContext(
            db=db_session, user_id=1, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_recent_news", {"max_age_hours": 24, "limit": 5}, ctx,
        )
        titles = [a["title"] for a in result["articles"]]
        assert "ETH hits new all-time high" in titles
        assert "ETH devs push upgrade" in titles
        assert "Random DOGE update" not in titles
        # Newest first
        assert titles.index("ETH devs push upgrade") < titles.index("ETH hits new all-time high")
        assert result["base_currency"] == "ETH"

    async def test_max_age_hours_filters_old_articles(self, db_session):
        await _make_article(db_session, title="ETH old news", hours_ago=48)
        await _make_article(db_session, title="ETH recent news", hours_ago=2)

        ctx = ToolContext(
            db=db_session, user_id=1, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_recent_news", {"max_age_hours": 6, "limit": 10}, ctx,
        )
        titles = [a["title"] for a in result["articles"]]
        assert "ETH recent news" in titles
        assert "ETH old news" not in titles

    async def test_limit_is_respected(self, db_session):
        for i in range(10):
            await _make_article(db_session, title=f"ETH update {i}", hours_ago=1)

        ctx = ToolContext(
            db=db_session, user_id=1, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_recent_news", {"max_age_hours": 24, "limit": 3}, ctx,
        )
        assert len(result["articles"]) == 3

    async def test_limit_clamped_to_max(self, db_session):
        for i in range(25):
            await _make_article(db_session, title=f"ETH post {i}", hours_ago=1)

        ctx = ToolContext(
            db=db_session, user_id=1, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_recent_news", {"max_age_hours": 24, "limit": 100}, ctx,
        )
        assert len(result["articles"]) <= 20

    async def test_base_alias_matches_full_name(self, db_session):
        """BTC product should also match articles mentioning 'Bitcoin'."""
        await _make_article(db_session, title="Bitcoin ETF approved", hours_ago=3)
        await _make_article(db_session, title="Ethereum merge anniversary", hours_ago=3)

        ctx = ToolContext(
            db=db_session, user_id=1, product_id="BTC-USD", current_price=100.0,
        )
        result = await execute(
            "get_recent_news", {"max_age_hours": 24, "limit": 5}, ctx,
        )
        titles = [a["title"] for a in result["articles"]]
        assert "Bitcoin ETF approved" in titles
        assert "Ethereum merge anniversary" not in titles

    async def test_matches_summary_when_title_misses(self, db_session):
        await _make_article(
            db_session,
            title="Weekly market roundup",
            summary="ETH led the majors with a 5% rally...",
            hours_ago=2,
        )
        ctx = ToolContext(
            db=db_session, user_id=1, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_recent_news", {"max_age_hours": 24, "limit": 5}, ctx,
        )
        titles = [a["title"] for a in result["articles"]]
        assert "Weekly market roundup" in titles

    async def test_no_matches_returns_empty_list(self, db_session):
        await _make_article(db_session, title="BTC pumps", hours_ago=1)

        ctx = ToolContext(
            db=db_session, user_id=1, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_recent_news", {"max_age_hours": 24, "limit": 5}, ctx,
        )
        assert result["articles"] == []
        assert result["base_currency"] == "ETH"


class TestRegistry:
    def test_tool_is_registered(self):
        assert "get_recent_news" in REGISTRY
