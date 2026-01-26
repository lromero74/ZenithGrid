#!/usr/bin/env python3
"""
Analyze database to show what's taking up space.
Shows table sizes, row counts, and storage breakdown.
"""
import sqlite3
from pathlib import Path

# Database path
db_path = Path(__file__).parent.parent / "backend" / "trading.db"

def analyze_database():
    """Analyze database tables and storage"""

    print("=" * 80)
    print("DATABASE ANALYSIS REPORT")
    print("=" * 80)
    print(f"Database: {db_path}")

    # Get file size
    file_size_bytes = db_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    print(f"Total File Size: {file_size_mb:.2f} MB ({file_size_bytes:,} bytes)")
    print()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]

        # Analyze each table
        table_stats = []
        for table in tables:
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cursor.fetchone()[0]

            # Get table size (approximate)
            cursor.execute(f"SELECT SUM(pgsize) FROM dbstat WHERE name='{table}'")
            result = cursor.fetchone()
            size_bytes = result[0] if result[0] else 0
            size_mb = size_bytes / (1024 * 1024)

            table_stats.append({
                'name': table,
                'rows': row_count,
                'size_bytes': size_bytes,
                'size_mb': size_mb
            })

        # Sort by size (largest first)
        table_stats.sort(key=lambda x: x['size_bytes'], reverse=True)

        # Print table breakdown
        print("TABLE BREAKDOWN (sorted by size):")
        print("-" * 80)
        print(f"{'Table Name':<30} {'Rows':>15} {'Size (MB)':>15} {'% of Total':>15}")
        print("-" * 80)

        for stat in table_stats:
            pct = (stat['size_mb'] / file_size_mb * 100) if file_size_mb > 0 else 0
            print(f"{stat['name']:<30} {stat['rows']:>15,} {stat['size_mb']:>15.2f} {pct:>14.1f}%")

        print("-" * 80)
        print()

        # Summary by category
        print("SUMMARY BY CATEGORY:")
        print("-" * 80)

        # Log tables
        log_tables = ['ai_bot_logs', 'indicator_logs', 'order_history']
        log_size = sum(s['size_mb'] for s in table_stats if s['name'] in log_tables)
        log_rows = sum(s['rows'] for s in table_stats if s['name'] in log_tables)

        # Position/trading tables
        trading_tables = ['positions', 'bots', 'pending_orders']
        trading_size = sum(s['size_mb'] for s in table_stats if s['name'] in trading_tables)
        trading_rows = sum(s['rows'] for s in table_stats if s['name'] in trading_tables)

        # Market data
        market_tables = ['trading_pairs', 'candle_cache']
        market_size = sum(s['size_mb'] for s in table_stats if s['name'] in market_tables)
        market_rows = sum(s['rows'] for s in table_stats if s['name'] in market_tables)

        # Content tables
        content_tables = ['news_articles', 'youtube_videos', 'content_sources']
        content_size = sum(s['size_mb'] for s in table_stats if s['name'] in content_tables)
        content_rows = sum(s['rows'] for s in table_stats if s['name'] in content_tables)

        # Other
        other_size = file_size_mb - (log_size + trading_size + market_size + content_size)
        other_rows = sum(s['rows'] for s in table_stats) - (log_rows + trading_rows + market_rows + content_rows)

        categories = [
            ('Logs (AI, Indicator, Order History)', log_size, log_rows),
            ('Trading (Positions, Bots, Pending Orders)', trading_size, trading_rows),
            ('Market Data (Pairs, Candle Cache)', market_size, market_rows),
            ('Content (News, Videos, Sources)', content_size, content_rows),
            ('Other (Settings, Users, etc.)', other_size, other_rows),
        ]

        print(f"{'Category':<45} {'Size (MB)':>15} {'Rows':>15}")
        print("-" * 80)
        for name, size, rows in categories:
            pct = (size / file_size_mb * 100) if file_size_mb > 0 else 0
            print(f"{name:<45} {size:>15.2f} {rows:>15,}")
        print("-" * 80)
        print()

        # Top 5 largest tables detail
        print("TOP 5 LARGEST TABLES (detailed):")
        print("-" * 80)
        for i, stat in enumerate(table_stats[:5], 1):
            print(f"\n{i}. {stat['name']}")
            print(f"   Rows: {stat['rows']:,}")
            print(f"   Size: {stat['size_mb']:.2f} MB ({stat['size_bytes']:,} bytes)")

            # Get sample row for context
            if stat['rows'] > 0:
                cursor.execute(f"SELECT * FROM {stat['name']} LIMIT 1")
                columns = [desc[0] for desc in cursor.description]
                print(f"   Columns ({len(columns)}): {', '.join(columns[:10])}" + ("..." if len(columns) > 10 else ""))

        print()
        print("=" * 80)

    finally:
        conn.close()


if __name__ == "__main__":
    print("\n📊 Database Storage Analysis\n")
    analyze_database()
