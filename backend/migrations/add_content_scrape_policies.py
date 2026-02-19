"""
Add per-source content scraping policies to content_sources.

- content_scrape_allowed: False means RSS-only (no article body scraping)
- crawl_delay_seconds: robots.txt crawl-delay to respect between fetches

Backfills policies based on robots.txt audit of all 47 sources.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")

# Sources whose robots.txt blocks AI bots / scrapers — RSS-only
RSS_ONLY_SOURCES = [
    'coindesk', 'mit_tech_ai', 'the_ai_beat', 'yahoo_finance_news',
    'npr_news', 'npr_health', 'ap_news', 'cnbc_business', 'engadget',
    'ars_technica', 'the_verge', 'wired', 'variety', 'hollywood_reporter',
    'deadline', 'espn', 'yahoo_sports', 'stat_news', 'the_lancet',
    'nature_medicine', 'self_wellness', 'business_insider',
    'genetic_engineering_news', 'who_news', 'pbs_newshour', 'cbs_sports',
]

# Sources with specific crawl-delay in robots.txt
CRAWL_DELAYS = {
    'bitcoin_magazine': 5,
    'genetic_engineering_news': 10,
    'pbs_newshour': 1,
    'the_lancet': 1,
    'global_voices': 10,
    'scmp': 10,
    'blockchain_news': 1,
}


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Add content_scrape_allowed column (idempotent)
        try:
            cursor.execute(
                "ALTER TABLE content_sources "
                "ADD COLUMN content_scrape_allowed BOOLEAN DEFAULT 1"
            )
            logger.info("Added content_scrape_allowed column to content_sources")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("content_scrape_allowed column already exists")
            else:
                raise

        # Add crawl_delay_seconds column (idempotent)
        try:
            cursor.execute(
                "ALTER TABLE content_sources "
                "ADD COLUMN crawl_delay_seconds INTEGER DEFAULT 0"
            )
            logger.info("Added crawl_delay_seconds column to content_sources")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("crawl_delay_seconds column already exists")
            else:
                raise

        # Backfill: mark RSS-only sources
        placeholders = ','.join('?' for _ in RSS_ONLY_SOURCES)
        cursor.execute(
            f"UPDATE content_sources SET content_scrape_allowed = 0 "
            f"WHERE source_key IN ({placeholders})",
            RSS_ONLY_SOURCES,
        )
        rss_only_count = cursor.rowcount
        if rss_only_count:
            logger.info(
                f"Set content_scrape_allowed=0 for {rss_only_count} RSS-only sources"
            )

        # Backfill: set crawl delays
        for source_key, delay in CRAWL_DELAYS.items():
            cursor.execute(
                "UPDATE content_sources SET crawl_delay_seconds = ? "
                "WHERE source_key = ?",
                (delay, source_key),
            )

        delayed_count = sum(
            1 for _ in CRAWL_DELAYS
            if cursor.execute(
                "SELECT 1 FROM content_sources WHERE source_key = ?", (_, )
            ).fetchone()
        )
        logger.info(f"Set crawl_delay_seconds for {delayed_count} sources")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
