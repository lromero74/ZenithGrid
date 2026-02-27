"""
Tests for PRP: Full-Article Sources for Politics, Nation, Entertainment, Sports.

Verifies:
- CBS/PBS sources reclassified to scrape=True
- New sources added with correct categories
- Migration idempotency
"""

import pytest


# ===========================================================================
# Phase 1: CBS/PBS reclassification in SOURCE_SCRAPE_POLICIES
# ===========================================================================


class TestCBSPBSReclassification:
    """Verify CBS/PBS sources are reclassified from scrape=False to scrape=True."""

    def test_cbs_sports_scrape_allowed(self):
        from app.database_seeds import SOURCE_SCRAPE_POLICIES
        policy = SOURCE_SCRAPE_POLICIES.get('cbs_sports', {})
        assert policy.get('scrape', True) is True

    def test_cbs_news_politics_scrape_allowed(self):
        from app.database_seeds import SOURCE_SCRAPE_POLICIES
        policy = SOURCE_SCRAPE_POLICIES.get('cbs_news_politics', {})
        assert policy.get('scrape', True) is True

    def test_cbs_news_us_scrape_allowed(self):
        from app.database_seeds import SOURCE_SCRAPE_POLICIES
        policy = SOURCE_SCRAPE_POLICIES.get('cbs_news_us', {})
        assert policy.get('scrape', True) is True

    def test_cbs_news_entertainment_scrape_allowed(self):
        from app.database_seeds import SOURCE_SCRAPE_POLICIES
        policy = SOURCE_SCRAPE_POLICIES.get('cbs_news_entertainment', {})
        assert policy.get('scrape', True) is True

    def test_pbs_newshour_scrape_allowed_with_delay(self):
        from app.database_seeds import SOURCE_SCRAPE_POLICIES
        policy = SOURCE_SCRAPE_POLICIES.get('pbs_newshour', {})
        assert policy.get('scrape', True) is True
        assert policy.get('delay', 0) == 1

    def test_pbs_politics_scrape_allowed_with_delay(self):
        from app.database_seeds import SOURCE_SCRAPE_POLICIES
        policy = SOURCE_SCRAPE_POLICIES.get('pbs_politics', {})
        assert policy.get('scrape', True) is True
        assert policy.get('delay', 0) == 1

    def test_pbs_arts_scrape_allowed_with_delay(self):
        from app.database_seeds import SOURCE_SCRAPE_POLICIES
        policy = SOURCE_SCRAPE_POLICIES.get('pbs_arts', {})
        assert policy.get('scrape', True) is True
        assert policy.get('delay', 0) == 1


# ===========================================================================
# Phase 2: New sources in DEFAULT_CONTENT_SOURCES
# ===========================================================================


class TestNewSourcesAdded:
    """Verify new full-article sources are added with correct categories."""

    @pytest.fixture(autouse=True)
    def _load_sources(self):
        from app.database_seeds import DEFAULT_CONTENT_SOURCES
        # Build lookup: source_key -> (name, type, url, website, desc, channel_id, category)
        self.sources = {}
        for row in DEFAULT_CONTENT_SOURCES:
            key = row[0]
            self.sources[key] = {
                'name': row[1], 'type': row[2], 'url': row[3],
                'website': row[4], 'description': row[5],
                'channel_id': row[6], 'category': row[7],
            }

    # --- Salon ---
    def test_salon_politics_exists(self):
        assert 'salon_politics' in self.sources
        assert self.sources['salon_politics']['category'] == 'Politics'
        assert 'salon.com' in self.sources['salon_politics']['url']

    def test_salon_entertainment_exists(self):
        assert 'salon_entertainment' in self.sources
        assert self.sources['salon_entertainment']['category'] == 'Entertainment'

    def test_salon_nation_exists(self):
        assert 'salon' in self.sources
        assert self.sources['salon']['category'] == 'Nation'

    # --- ProPublica ---
    def test_propublica_exists(self):
        assert 'propublica' in self.sources
        s = self.sources['propublica']
        assert s['category'] in ('Politics', 'Nation')
        assert 'propublica' in s['url']

    # --- Sports Illustrated ---
    def test_sports_illustrated_exists(self):
        assert 'sports_illustrated' in self.sources
        assert self.sources['sports_illustrated']['category'] == 'Sports'
        assert 'si.com' in self.sources['sports_illustrated']['url']

    def test_sports_illustrated_not_dead(self):
        """SI must be removed from DEAD_SOURCES to be active."""
        from app.database_seeds import DEAD_SOURCES
        assert 'sports_illustrated' not in DEAD_SOURCES

    # --- ET Online ---
    def test_et_online_exists(self):
        assert 'et_online' in self.sources
        assert self.sources['et_online']['category'] == 'Entertainment'
        assert 'etonline.com' in self.sources['et_online']['url']

    # --- Democracy Now ---
    def test_democracy_now_exists(self):
        assert 'democracy_now' in self.sources
        s = self.sources['democracy_now']
        assert s['category'] in ('Politics', 'Nation')
        assert 'democracynow.org' in s['url']

    def test_democracy_now_crawl_delay(self):
        from app.database_seeds import SOURCE_SCRAPE_POLICIES
        policy = SOURCE_SCRAPE_POLICIES.get('democracy_now', {})
        assert policy.get('delay', 0) == 10

    # --- The Independent ---
    def test_independent_politics_exists(self):
        assert 'independent_politics' in self.sources
        assert self.sources['independent_politics']['category'] == 'Politics'
        assert 'independent.co.uk' in self.sources['independent_politics']['url']

    def test_independent_nation_exists(self):
        assert 'independent_nation' in self.sources
        assert self.sources['independent_nation']['category'] == 'Nation'

    def test_independent_entertainment_exists(self):
        assert 'independent_entertainment' in self.sources
        assert self.sources['independent_entertainment']['category'] == 'Entertainment'

    def test_independent_sports_exists(self):
        assert 'independent_sports' in self.sources
        assert self.sources['independent_sports']['category'] == 'Sports'

    # --- Common Dreams ---
    def test_common_dreams_exists(self):
        assert 'common_dreams' in self.sources
        s = self.sources['common_dreams']
        assert s['category'] in ('Politics', 'Nation')
        assert 'commondreams.org' in s['url']


# ===========================================================================
# Category coverage: each of the 4 categories has at least 1 full-article source
# ===========================================================================


class TestCategoryCoverage:
    """After implementation, each of the 4 categories must have full-article sources."""

    @pytest.fixture(autouse=True)
    def _load(self):
        from app.database_seeds import DEFAULT_CONTENT_SOURCES, SOURCE_SCRAPE_POLICIES
        self.full_article_by_category = {}
        for row in DEFAULT_CONTENT_SOURCES:
            key, category = row[0], row[7]
            if row[2] != 'news':
                continue
            policy = SOURCE_SCRAPE_POLICIES.get(key, {})
            if policy.get('scrape', True) is True:
                self.full_article_by_category.setdefault(category, []).append(key)

    def test_politics_has_full_article_sources(self):
        sources = self.full_article_by_category.get('Politics', [])
        assert len(sources) >= 3, f"Politics only has {len(sources)} full-article sources: {sources}"

    def test_nation_has_full_article_sources(self):
        sources = self.full_article_by_category.get('Nation', [])
        assert len(sources) >= 3, f"Nation only has {len(sources)} full-article sources: {sources}"

    def test_entertainment_has_full_article_sources(self):
        sources = self.full_article_by_category.get('Entertainment', [])
        assert len(sources) >= 2, f"Entertainment only has {len(sources)} full-article sources: {sources}"

    def test_sports_has_full_article_sources(self):
        sources = self.full_article_by_category.get('Sports', [])
        assert len(sources) >= 2, f"Sports only has {len(sources)} full-article sources: {sources}"


# ===========================================================================
# Domain alias handling (The Independent uses redirect domain in RSS)
# ===========================================================================


class TestDomainAliases:
    """Verify domain aliases are applied for sources with redirect/CDN domains."""

    def test_independent_alias_in_allowed_domains(self):
        """the-independent.com must be allowed since independent.co.uk is a source."""
        from app.routers.news_router import DOMAIN_ALIASES
        aliases = DOMAIN_ALIASES.get("independent.co.uk", [])
        assert "the-independent.com" in aliases

    @pytest.mark.asyncio
    async def test_allowed_domains_includes_alias(self):
        """get_allowed_article_domains should include the-independent.com."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_source = MagicMock()
        mock_source.website = "https://www.independent.co.uk"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            "https://www.independent.co.uk",
        ]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.news_router.async_session_maker", return_value=mock_session):
            from app.routers.news_router import get_allowed_article_domains
            domains = await get_allowed_article_domains()
            assert "the-independent.com" in domains
            assert "www.the-independent.com" in domains
            assert "independent.co.uk" in domains
            assert "www.independent.co.uk" in domains


# ===========================================================================
# Migration idempotency
# ===========================================================================


class TestMigrationIdempotent:
    """Verify migration can run twice without errors."""

    def test_migration_runs_twice(self, tmp_path):
        """Migration must be idempotent — running twice should not error."""
        import sqlite3
        import importlib.util
        import os

        # Create a test DB with content_sources table
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE content_sources (
                id INTEGER PRIMARY KEY,
                source_key TEXT UNIQUE,
                name TEXT,
                type TEXT,
                url TEXT,
                website TEXT,
                description TEXT,
                channel_id TEXT,
                is_system INTEGER DEFAULT 1,
                is_enabled INTEGER DEFAULT 1,
                category TEXT,
                content_scrape_allowed INTEGER DEFAULT 1,
                crawl_delay_seconds INTEGER DEFAULT 0
            )
        """)
        # Insert a source that should be reclassified
        conn.execute(
            "INSERT INTO content_sources (source_key, name, type, category, content_scrape_allowed) "
            "VALUES ('cbs_sports', 'CBS Sports', 'news', 'Sports', 0)"
        )
        conn.commit()
        conn.close()

        # Load migration module from file path
        migration_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "migrations", "reclassify_and_add_full_article_sources.py",
        )
        spec = importlib.util.spec_from_file_location("migration", migration_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Run once
        mod.migrate(db_path)

        # Verify reclassification
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT content_scrape_allowed FROM content_sources WHERE source_key = 'cbs_sports'"
        ).fetchone()
        assert row[0] == 1

        # Verify new sources were inserted
        new_count = conn.execute(
            "SELECT COUNT(*) FROM content_sources WHERE source_key = 'salon_politics'"
        ).fetchone()[0]
        assert new_count == 1
        conn.close()

        # Run again — must not error
        mod.migrate(db_path)

        # Verify idempotency — still correct values
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT content_scrape_allowed FROM content_sources WHERE source_key = 'cbs_sports'"
        ).fetchone()
        assert row[0] == 1
        new_count = conn.execute(
            "SELECT COUNT(*) FROM content_sources WHERE source_key = 'salon_politics'"
        ).fetchone()[0]
        assert new_count == 1  # Not duplicated
        conn.close()
