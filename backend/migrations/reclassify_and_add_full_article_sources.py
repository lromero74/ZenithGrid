"""
Reclassify CBS/PBS sources and add new full-article sources.

Phase 1: Flip content_scrape_allowed from 0 to 1 for 7 CBS/PBS sources
         whose robots.txt doesn't actually block our ZenithGrid/1.0 user-agent.

Phase 2: Insert 13 new source rows for full-article coverage in
         Politics, Nation, Entertainment, and Sports.

All operations are idempotent (UPDATE + INSERT OR IGNORE).
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")

# Phase 1: Sources to reclassify from scrape=False to scrape=True
RECLASSIFY_SOURCES = [
    'cbs_sports',
    'cbs_news_politics',
    'cbs_news_us',
    'cbs_news_entertainment',
    'pbs_newshour',
    'pbs_politics',
    'pbs_arts',
]

# Phase 2: New full-article sources to add
# Format: (source_key, name, type, url, website, description, channel_id, category,
#          content_scrape_allowed, crawl_delay_seconds)
NEW_SOURCES = [
    # Politics
    (
        'salon_politics', 'Salon Politics', 'news',
        'https://www.salon.com/category/politics/feed',
        'https://www.salon.com', 'Progressive news & commentary',
        None, 'Politics', 1, 0,
    ),
    (
        'propublica', 'ProPublica', 'news',
        'https://feeds.propublica.org/propublica/main',
        'https://www.propublica.org', 'Pulitzer-winning investigative journalism',
        None, 'Politics', 1, 0,
    ),
    (
        'democracy_now', 'Democracy Now!', 'news',
        'https://www.democracynow.org/democracynow.rss',
        'https://www.democracynow.org', 'Independent news & analysis',
        None, 'Politics', 1, 10,
    ),
    (
        'independent_politics', 'The Independent Politics', 'news',
        'https://www.independent.co.uk/news/world/americas/us-politics/rss',
        'https://www.independent.co.uk', 'UK perspective on US politics',
        None, 'Politics', 1, 0,
    ),
    # Nation
    (
        'salon', 'Salon', 'news',
        'https://www.salon.com/feed/',
        'https://www.salon.com', 'News, politics & culture',
        None, 'Nation', 1, 0,
    ),
    (
        'independent_nation', 'The Independent US', 'news',
        'https://www.independent.co.uk/news/rss',
        'https://www.independent.co.uk', 'UK perspective on US & world news',
        None, 'Nation', 1, 0,
    ),
    (
        'common_dreams', 'Common Dreams', 'news',
        'https://www.commondreams.org/rss.xml',
        'https://www.commondreams.org', 'Progressive US news',
        None, 'Nation', 1, 0,
    ),
    # Entertainment
    (
        'salon_entertainment', 'Salon Entertainment', 'news',
        'https://www.salon.com/category/entertainment/feed',
        'https://www.salon.com', 'Entertainment news & culture',
        None, 'Entertainment', 1, 0,
    ),
    (
        'et_online', 'ET Online', 'news',
        'https://www.etonline.com/news/rss',
        'https://www.etonline.com', 'Celebrity & entertainment news',
        None, 'Entertainment', 1, 0,
    ),
    (
        'independent_entertainment', 'The Independent Entertainment', 'news',
        'https://www.independent.co.uk/arts-entertainment/rss',
        'https://www.independent.co.uk', 'Arts & entertainment coverage',
        None, 'Entertainment', 1, 0,
    ),
    # Sports
    (
        'sports_illustrated', 'Sports Illustrated', 'news',
        'https://www.si.com/feed',
        'https://www.si.com', 'Iconic sports journalism',
        None, 'Sports', 1, 0,
    ),
    (
        'independent_sports', 'The Independent Sports', 'news',
        'https://www.independent.co.uk/sport/rss',
        'https://www.independent.co.uk', 'UK sports coverage',
        None, 'Sports', 1, 0,
    ),
]


def migrate(db_path=None):
    if db_path is None:
        db_path = DB_PATH

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Phase 1: Reclassify CBS/PBS sources
        placeholders = ','.join('?' for _ in RECLASSIFY_SOURCES)
        cursor.execute(
            f"UPDATE content_sources SET content_scrape_allowed = 1 "
            f"WHERE source_key IN ({placeholders})",
            RECLASSIFY_SOURCES,
        )
        reclassified = cursor.rowcount
        if reclassified:
            logger.info(f"Reclassified {reclassified} sources to content_scrape_allowed=1")

        # Set crawl_delay for PBS sources
        cursor.execute(
            "UPDATE content_sources SET crawl_delay_seconds = 1 "
            "WHERE source_key IN ('pbs_newshour', 'pbs_politics', 'pbs_arts')"
        )

        # Phase 2: Insert new sources (idempotent via INSERT OR IGNORE)
        inserted = 0
        for src in NEW_SOURCES:
            cursor.execute(
                "INSERT OR IGNORE INTO content_sources "
                "(source_key, name, type, url, website, description, channel_id, "
                "category, is_system, is_enabled, content_scrape_allowed, crawl_delay_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)",
                src,
            )
            if cursor.rowcount > 0:
                inserted += 1

        if inserted:
            logger.info(f"Inserted {inserted} new full-article content sources")

        # Remove sports_illustrated from dead if it was previously deleted
        # (it's being re-added as a working source)
        cursor.execute(
            "UPDATE content_sources SET is_enabled = 1 "
            "WHERE source_key = 'sports_illustrated' AND is_enabled = 0"
        )

        conn.commit()
        logger.info("Full-article sources migration completed successfully")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
