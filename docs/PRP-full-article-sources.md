# PRP: Full-Article Sources for Politics, Nation, Entertainment, Sports

**Status**: Implemented — pending deploy
**Created**: 2026-02-26
**Implemented**: 2026-02-27

## Problem

All news sources in Politics, Nation, Entertainment, and Sports have `content_scrape_allowed = 0` (RSS summaries only). When users enable the "Full Articles Only" filter, these 4 categories show zero results. TTS also can't read full content for these articles.

## Research Findings

### New Sources to Add (robots.txt verified)

| Priority | Source | Categories | Why |
|----------|--------|-----------|-----|
| 1 | **Salon** (salon.com) | Politics, Nation, Entertainment | Explicitly allows ALL AI bots. Full `content:encoded` in RSS. Category-specific feeds. |
| 2 | **ProPublica** (propublica.org) | Politics, Nation | Fully open robots.txt (`Disallow:` empty). Pulitzer-winning nonprofit. Full RSS content. |
| 3 | **Sports Illustrated** (si.com) | Sports | Fully permissive (`Allow: /`). Iconic brand. Working RSS feed. |
| 4 | **ET Online** (etonline.com) | Entertainment | No AI bot blocks. Multiple category RSS feeds (news, TV, movies, music). |
| 5 | **Democracy Now!** (democracynow.org) | Politics, Nation | CC BY-NC-ND 3.0 license. Full RSS content. 10s crawl delay required. |
| 6 | **The Independent** (independent.co.uk) | Politics, Nation, Entertainment, Sports | Very permissive (only blocks Nutch bot). Category-specific RSS feeds. UK perspective. |
| 7 | **Common Dreams** (commondreams.org) | Politics, Nation | Permissive robots.txt. US progressive news. Large full-content feed. |

### RSS Feed URLs

```
# Salon
https://www.salon.com/category/politics/feed
https://www.salon.com/category/entertainment/feed
https://www.salon.com/feed/  (main — covers Nation)

# ProPublica
https://feeds.propublica.org/propublica/main

# Sports Illustrated
https://www.si.com/feed

# ET Online
https://www.etonline.com/news/rss
https://www.etonline.com/tv/rss
https://www.etonline.com/movies/rss
https://www.etonline.com/music/rss

# Democracy Now!
https://www.democracynow.org/democracynow.rss  (crawl_delay: 10)

# The Independent
https://www.independent.co.uk/news/world/americas/us-politics/rss  (Politics)
https://www.independent.co.uk/news/rss  (Nation)
https://www.independent.co.uk/arts-entertainment/rss  (Entertainment)
https://www.independent.co.uk/sport/rss  (Sports)

# Common Dreams
https://www.commondreams.org/rss.xml
```

### Existing Sources to Reclassify

These are currently `content_scrape_allowed = 0` but their robots.txt only blocks GPTBot (not our `ZenithGrid/1.0` user-agent):

| Source Key | Category | robots.txt Blocks | Recommendation |
|------------|----------|-------------------|----------------|
| `cbs_sports` | Sports | GPTBot only | Reclassify to `scrape: True` |
| `cbs_news_politics` | Politics | GPTBot, MAZBot, panscient, proximic | Reclassify to `scrape: True` |
| `cbs_news_us` | Nation | Same as above | Reclassify to `scrape: True` |
| `cbs_news_entertainment` | Entertainment | Same as above | Reclassify to `scrape: True` |
| `pbs_newshour` | Nation | No AI bot blocks. 1s crawl-delay. | Reclassify to `scrape: True`, keep `delay: 1` |
| `pbs_politics` | Politics | Same as PBS | Reclassify to `scrape: True`, keep `delay: 1` |
| `pbs_arts` | Entertainment | Same as PBS | Reclassify to `scrape: True`, keep `delay: 1` |

**Caveat**: CBS/PBS may block by ToS even without robots.txt rules. Test with a single fetch before enabling at scale. If they start returning 403s or blocking our IP, revert immediately.

## Implementation Plan

### Phase 1: Quick Win — Reclassify CBS + PBS (low risk, immediate coverage)

**File: `backend/app/database_seeds.py`** (~line 727, `SOURCE_SCRAPE_POLICIES`)
- Flip 7 existing sources from `False` to `True`
- Add `crawl_delay_seconds: 1` for PBS sources

**File: `backend/migrations/reclassify_scrape_sources.py`** (NEW)
- UPDATE `content_sources` SET `content_scrape_allowed = 1` WHERE `source_key` IN (...)
- UPDATE `content_sources` SET `crawl_delay_seconds = 1` WHERE `source_key` LIKE 'pbs%'

**Verification**:
- Fetch one article from each reclassified source manually
- Confirm content comes back, no 403/block
- If blocked, revert that source immediately

### Phase 2: Add New Sources

For each new source (Salon, ProPublica, SI, ET Online, Democracy Now, The Independent, Common Dreams):

**File: `backend/app/database_seeds.py`** (content_sources seed data)
- Add source definitions with: source_key, name, type="rss", url, website, category, content_scrape_allowed=True, crawl_delay_seconds (if needed)

**File: `backend/migrations/add_full_article_sources.py`** (NEW)
- INSERT INTO `content_sources` for each new source (idempotent — ON CONFLICT DO NOTHING)

**File: `backend/app/services/news_service.py`** (RSS fetcher)
- Verify the RSS parser handles `content:encoded` fields for full-content RSS feeds
- If Salon/ProPublica/Democracy Now deliver full content in RSS, no scraping needed at all — just store the RSS content directly
- For sources with summary-only RSS (SI, ET Online, The Independent), scraping pipeline handles them

**Test for each source**:
1. Add source to DB
2. Run RSS fetch cycle
3. Verify articles are stored with correct category
4. Click an article — verify full content loads (either from RSS `content:encoded` or scraper)
5. Test TTS on an article from each source

### Phase 3: Verify & Monitor

- Check article counts per category after 24 hours
- Verify "Full Articles Only" filter shows results for all 4 categories
- Monitor for any IP blocks or 403 responses in logs
- Add any blocked sources to the scrape-blocked list

## Category Coverage After Implementation

| Category | Current Full-Article Sources | After Phase 1 | After Phase 2 |
|----------|-----------------------------|---------------|---------------|
| Politics | 0 | 3 (CBS, PBS x2) | 6+ (+ Salon, ProPublica, Democracy Now, Independent) |
| Nation | 0 | 3 (CBS, PBS, NPR*) | 6+ (+ ProPublica, Salon, Common Dreams, Independent) |
| Entertainment | 0 | 2 (CBS, PBS) | 5+ (+ Salon, ET Online, Independent) |
| Sports | 0 | 1 (CBS) | 3+ (+ SI, Independent) |

## Files Modified (Summary)

| File | Change |
|------|--------|
| `backend/app/database_seeds.py` | Reclassify 7 sources + add ~10 new sources |
| `backend/migrations/reclassify_scrape_sources.py` | NEW — flip scrape flag for CBS/PBS |
| `backend/migrations/add_full_article_sources.py` | NEW — insert new source rows |
| `backend/app/services/news_service.py` | Verify `content:encoded` RSS handling (may need no changes) |

## Risks

- CBS/PBS could start blocking our IP if they notice increased scraping
- New sources may change their robots.txt policies
- Some RSS feeds may go stale or change URLs
- Democracy Now requires 10s crawl delay — must enforce in scraper

## Not in Scope

- Changing the "Full Articles Only" UX (filter works correctly as-is)
- Adding video sources (separate effort)
- Paid/licensed news content (AP, Reuters wire services)
