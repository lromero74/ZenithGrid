"""
Migration: Extract bot product_ids JSON to bot_products junction table

Creates a bot_products junction table and populates it from existing
bots.product_ids JSON arrays. This normalizes the schema (1NF fix)
and enables SQL queries like "find all bots trading ETH-BTC" without
JSON parsing.

The original product_ids column is kept for backwards compatibility
during the transition period.
"""

import json
import sqlite3
from pathlib import Path


def get_db_path():
    """Get database path relative to script location"""
    backend_dir = Path(__file__).parent.parent
    return backend_dir / "trading.db"


def run_migration():
    """Create bot_products table and populate from existing bots"""
    db_path = get_db_path()

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Create bot_products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bot_id, product_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bot_products_bot_id
            ON bot_products(bot_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bot_products_product_id
            ON bot_products(product_id)
        """)
        print("Created bot_products table with indexes")

        # Create bot_template_products table (same pattern for templates)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_template_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL REFERENCES bot_templates(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(template_id, product_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bot_template_products_template_id
            ON bot_template_products(template_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bot_template_products_product_id
            ON bot_template_products(product_id)
        """)
        print("Created bot_template_products table with indexes")

        # Populate bot_products from existing bots
        cursor.execute("SELECT id, product_id, product_ids FROM bots")
        bots = cursor.fetchall()
        bot_products_count = 0

        for bot_id, product_id_single, product_ids_json in bots:
            # Parse product_ids JSON
            product_ids = []
            if product_ids_json:
                try:
                    parsed = json.loads(product_ids_json)
                    if isinstance(parsed, list):
                        product_ids = parsed
                except (json.JSONDecodeError, TypeError):
                    pass

            # Fall back to single product_id if no list
            if not product_ids and product_id_single:
                product_ids = [product_id_single]

            for pid in product_ids:
                if pid:  # Skip empty strings
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO bot_products(bot_id, product_id) VALUES (?, ?)",
                            (bot_id, pid)
                        )
                        bot_products_count += 1
                    except sqlite3.IntegrityError:
                        pass  # Already exists

        print(f"Populated {bot_products_count} bot_products rows from {len(bots)} bots")

        # Populate bot_template_products from existing templates
        cursor.execute("SELECT id, product_ids FROM bot_templates")
        templates = cursor.fetchall()
        template_products_count = 0

        for template_id, product_ids_json in templates:
            product_ids = []
            if product_ids_json:
                try:
                    parsed = json.loads(product_ids_json)
                    if isinstance(parsed, list):
                        product_ids = parsed
                except (json.JSONDecodeError, TypeError):
                    pass

            for pid in product_ids:
                if pid:
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO bot_template_products(template_id, product_id) VALUES (?, ?)",
                            (template_id, pid)
                        )
                        template_products_count += 1
                    except sqlite3.IntegrityError:
                        pass

        print(f"Populated {template_products_count} bot_template_products rows from {len(templates)} templates")

        conn.commit()
        print("Migration completed successfully")
        return True

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    print("Running migration: extract_bot_products")
    success = run_migration()
    exit(0 if success else 1)
