"""
Migration: Add content_sources and user_source_subscriptions tables

This enables database-backed news/video sources with per-user subscriptions.
System sources are seeded from the default list; users can add custom sources
and choose which sources they want to see.
"""

import sqlite3
from pathlib import Path


def run_migration():
    """Add content sources tables and seed default sources"""
    db_path = Path(__file__).parent.parent / "trading.db"

    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='content_sources'")
        if cursor.fetchone():
            print("Table content_sources already exists - checking for new sources to add")
        else:
            # Create content_sources table
            cursor.execute("""
                CREATE TABLE content_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    url TEXT NOT NULL,
                    website TEXT,
                    description TEXT,
                    channel_id TEXT,
                    is_system BOOLEAN DEFAULT 1,
                    is_enabled BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_content_sources_type ON content_sources(type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_content_sources_is_enabled ON content_sources(is_enabled)")
            print("   - Created content_sources table")

        # Check if subscriptions table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_source_subscriptions'")
        if cursor.fetchone():
            print("Table user_source_subscriptions already exists")
        else:
            # Create user_source_subscriptions table
            cursor.execute("""
                CREATE TABLE user_source_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    source_id INTEGER NOT NULL,
                    is_subscribed BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (source_id) REFERENCES content_sources(id) ON DELETE CASCADE,
                    UNIQUE(user_id, source_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_user_source_subscriptions_user_id ON user_source_subscriptions(user_id)")
            print("   - Created user_source_subscriptions table")

        # Seed default sources (INSERT OR IGNORE to avoid duplicates)
        default_sources = [
            # News sources
            ('bitcoin_magazine', 'Bitcoin Magazine', 'news', 'https://bitcoinmagazine.com/feed', 'https://bitcoinmagazine.com', 'Bitcoin news, analysis & culture', None),
            ('beincrypto', 'BeInCrypto', 'news', 'https://beincrypto.com/feed/', 'https://beincrypto.com', 'Crypto news, guides & price analysis', None),
            ('coindesk', 'CoinDesk', 'news', 'https://www.coindesk.com/arc/outboundfeeds/rss/', 'https://www.coindesk.com', 'Crypto news & analysis', None),
            ('cointelegraph', 'CoinTelegraph', 'news', 'https://cointelegraph.com/rss', 'https://cointelegraph.com', 'Blockchain & crypto news', None),
            ('decrypt', 'Decrypt', 'news', 'https://decrypt.co/feed', 'https://decrypt.co', 'Web3 news & guides', None),
            ('theblock', 'The Block', 'news', 'https://www.theblock.co/rss.xml', 'https://www.theblock.co', 'Institutional crypto news', None),
            ('cryptoslate', 'CryptoSlate', 'news', 'https://cryptoslate.com/feed/', 'https://cryptoslate.com', 'Crypto news & data', None),
            # Video sources
            ('coin_bureau', 'Coin Bureau', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCqK_GSMbpiV8spgD3ZGloSw', 'https://www.youtube.com/@CoinBureau', 'Educational crypto content & analysis', 'UCqK_GSMbpiV8spgD3ZGloSw'),
            ('benjamin_cowen', 'Benjamin Cowen', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCRvqjQPSeaWn-uEx-w0XOIg', 'https://www.youtube.com/@intothecryptoverse', 'Technical analysis & market cycles', 'UCRvqjQPSeaWn-uEx-w0XOIg'),
            ('altcoin_daily', 'Altcoin Daily', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCbLhGKVY-bJPcawebgtNfbw', 'https://www.youtube.com/@AltcoinDaily', 'Daily crypto news & updates', 'UCbLhGKVY-bJPcawebgtNfbw'),
            ('bankless', 'Bankless', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCAl9Ld79qaZxp9JzEOwd3aA', 'https://www.youtube.com/@Bankless', 'Ethereum & DeFi ecosystem', 'UCAl9Ld79qaZxp9JzEOwd3aA'),
            ('the_defiant', 'The Defiant', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCL0J4MLEdLP0-UyLu0hCktg', 'https://www.youtube.com/@TheDefiant', 'DeFi news & interviews', 'UCL0J4MLEdLP0-UyLu0hCktg'),
            ('crypto_banter', 'Crypto Banter', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCN9Nj4tjXbVTLYWN0EKly_Q', 'https://www.youtube.com/@CryptoBanter', 'Live crypto shows & trading', 'UCN9Nj4tjXbVTLYWN0EKly_Q'),
            ('datadash', 'DataDash', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCCatR7nWbYrkVXdxXb4cGXw', 'https://www.youtube.com/@DataDash', 'Macro markets & crypto analysis', 'UCCatR7nWbYrkVXdxXb4cGXw'),
            ('cryptosrus', 'CryptosRUs', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCI7M65p3A-D3P4v5qW8POxQ', 'https://www.youtube.com/@CryptosRUs', 'Market analysis & project reviews', 'UCI7M65p3A-D3P4v5qW8POxQ'),
            ('the_moon', 'The Moon', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCc4Rz_T9Sb1w5rqqo9pL1Og', 'https://www.youtube.com/@TheMoonCarl', 'Daily Bitcoin analysis & news', 'UCc4Rz_T9Sb1w5rqqo9pL1Og'),
            ('digital_asset_news', 'Digital Asset News', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCJgHxpqfhWEEjYH9cLXqhIQ', 'https://www.youtube.com/@DigitalAssetNews', 'Bite-sized crypto news updates', 'UCJgHxpqfhWEEjYH9cLXqhIQ'),
            ('paul_barron', 'Paul Barron Network', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UC4VPa7EOvObpyCRI4YKRQRw', 'https://www.youtube.com/@paulbarronnetwork', 'Tech, AI & crypto intersection', 'UC4VPa7EOvObpyCRI4YKRQRw'),
            ('lark_davis', 'Lark Davis', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCl2oCaw8hdR_kbqyqd2klIA', 'https://www.youtube.com/@TheCryptoLark', 'Altcoin analysis & opportunities', 'UCl2oCaw8hdR_kbqyqd2klIA'),
        ]

        added_count = 0
        for source in default_sources:
            cursor.execute("""
                INSERT OR IGNORE INTO content_sources (source_key, name, type, url, website, description, channel_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, source)
            if cursor.rowcount > 0:
                added_count += 1

        conn.commit()
        print(f"Migration completed successfully!")
        print(f"   - Seeded {added_count} new content sources ({len(default_sources)} total available)")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
