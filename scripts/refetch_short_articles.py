#!/usr/bin/env python3
"""
One-off script: Re-fetch full content for articles with suspiciously short TTS cache.

These are articles where the TTS was generated from the ~200 char RSS summary
instead of the full article content. This script:
1. Finds articles with TTS audio < 100KB (summary-length)
2. Attempts to re-fetch full content via trafilatura with exponential backoff
3. On success: deletes stale TTS cache (audio files + DB records) so next
   playback regenerates from full content; clears has_issue flag
4. Reports results
"""

import asyncio
import os
import sys
import time

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import sqlite3
import shutil
import trafilatura


DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'backend', 'trading.db')
TTS_CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend', 'tts_cache')
BACKOFF_DELAYS = [0, 2, 5, 10]  # seconds between attempts
SIZE_THRESHOLD = 100_000  # bytes — TTS files under this are likely summary-only


def fetch_with_backoff(url: str) -> str | None:
    """Fetch article content with exponential backoff retries."""
    for attempt, delay in enumerate(BACKOFF_DELAYS):
        if delay > 0:
            print(f"    Retry {attempt + 1}/{len(BACKOFF_DELAYS)}, waiting {delay}s...")
            time.sleep(delay)

        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                print(f"    Attempt {attempt + 1}: fetch returned None")
                continue

            content = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                favor_recall=True,
                output_format='txt',
            )
            if content and len(content) > 300:
                return content
            elif content:
                print(f"    Attempt {attempt + 1}: content too short ({len(content)} chars)")
            else:
                print(f"    Attempt {attempt + 1}: extraction returned None")
        except Exception as e:
            print(f"    Attempt {attempt + 1}: error - {e}")

    return None


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Find articles with small TTS cache
    c.execute('''
        SELECT DISTINCT at.article_id, na.title, na.url, na.has_issue,
               MIN(at.file_size_bytes) as min_size
        FROM article_tts at
        JOIN news_articles na ON at.article_id = na.id
        WHERE at.file_size_bytes < ?
        GROUP BY at.article_id
        ORDER BY min_size ASC
    ''', (SIZE_THRESHOLD,))
    articles = c.fetchall()

    print(f"Found {len(articles)} articles with TTS cache < {SIZE_THRESHOLD // 1000}KB\n")

    success = 0
    failed = 0
    already_ok = 0

    for article_id, title, url, has_issue, min_size in articles:
        print(f"[{article_id}] {title[:70]}")
        print(f"  URL: {url}")
        print(f"  Current TTS size: {min_size:,}b | has_issue: {has_issue}")

        content = fetch_with_backoff(url)

        if content:
            print(f"  SUCCESS: Got {len(content):,} chars of content")

            # Delete stale TTS cache files
            tts_dir = os.path.join(TTS_CACHE_DIR, str(article_id))
            if os.path.isdir(tts_dir):
                file_count = len(os.listdir(tts_dir))
                shutil.rmtree(tts_dir)
                print(f"  Deleted TTS cache dir ({file_count} files)")

            # Delete DB records for this article's TTS
            c.execute('DELETE FROM article_tts WHERE article_id = ?', (article_id,))
            deleted = c.rowcount
            print(f"  Deleted {deleted} TTS DB records")

            # Clear has_issue flag if set
            if has_issue:
                c.execute('UPDATE news_articles SET has_issue = 0 WHERE id = ?', (article_id,))
                print(f"  Cleared has_issue flag")

            conn.commit()
            success += 1
        else:
            print(f"  FAILED: Could not fetch full content after {len(BACKOFF_DELAYS)} attempts")
            # Flag as has_issue so the frontend knows
            if not has_issue:
                c.execute('UPDATE news_articles SET has_issue = 1 WHERE id = ?', (article_id,))
                conn.commit()
                print(f"  Set has_issue=1")
            failed += 1

        print()

    print("=" * 60)
    print(f"Results: {success} refetched, {failed} failed, {already_ok} already ok")
    print(f"Total: {len(articles)} articles processed")

    conn.close()


if __name__ == '__main__':
    main()
