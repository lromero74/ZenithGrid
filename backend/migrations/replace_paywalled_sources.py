"""
Migration: Replace paywalled news sources with free alternatives

Removes sources that require subscriptions (FT, Bloomberg, WSJ, Economist, MarketWatch)
and adds free alternatives (Yahoo Finance, Kiplinger, Business Insider).
"""

import sqlite3
from pathlib import Path


def get_db_path():
    """Get database path relative to script location"""
    backend_dir = Path(__file__).parent.parent
    return backend_dir / "trading.db"


# Sources to remove (paywalled or JS-rendered with no extractable content)
SOURCES_TO_REMOVE = [
    'reuters_finance',   # Bloomberg Markets - paywalled
    'ft_markets',        # Financial Times - paywalled
    'the_economist_finance',  # The Economist - paywalled
    'wsj_markets',       # Wall Street Journal - paywalled
    'marketwatch',       # MarketWatch - JS-rendered, no extraction
]

# New free sources to add
SOURCES_TO_ADD = [
    ('yahoo_finance_news', 'Yahoo Finance', 'news', 'https://finance.yahoo.com/news/rssindex',
     'https://finance.yahoo.com', 'Financial news & market analysis', None, 'Finance'),
    ('kiplinger', 'Kiplinger', 'news', 'https://www.kiplinger.com/feed/all',
     'https://www.kiplinger.com', 'Personal finance & investing advice', None, 'Finance'),
    ('business_insider', 'Business Insider', 'news', 'https://www.businessinsider.com/rss',
     'https://www.businessinsider.com', 'Business & tech news', None, 'Business'),
]


def run_migration():
    """Replace paywalled sources with free ones"""
    db_path = get_db_path()

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Remove paywalled sources
        for source_key in SOURCES_TO_REMOVE:
            cursor.execute("SELECT source_key FROM content_sources WHERE source_key = ?", (source_key,))
            if cursor.fetchone():
                cursor.execute("DELETE FROM content_sources WHERE source_key = ?", (source_key,))
                print(f"  Removed paywalled source: {source_key}")
            else:
                print(f"  Source not found (already removed): {source_key}")

        # Add new free sources
        for source in SOURCES_TO_ADD:
            source_key = source[0]
            cursor.execute("SELECT source_key FROM content_sources WHERE source_key = ?", (source_key,))
            if cursor.fetchone():
                print(f"  Source already exists: {source_key}")
            else:
                cursor.execute("""
                    INSERT INTO content_sources (source_key, name, type, url, website, description, channel_id, category, is_enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, source)
                print(f"  Added free source: {source_key} ({source[1]})")

        conn.commit()
        print("\nMigration complete: paywalled sources replaced with free alternatives")
        return True

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
