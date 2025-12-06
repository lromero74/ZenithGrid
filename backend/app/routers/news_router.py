"""
Crypto News Router

Fetches and caches crypto news from multiple sources.
Cache behavior:
- Checks for new content every 15 minutes
- Merges new items with existing cache (new items at top)
- Prunes items older than 7 days

Sources:
- Reddit r/cryptocurrency and r/bitcoin (JSON API)
- CoinDesk (RSS)
- CoinTelegraph (RSS)
- Decrypt (RSS)
- The Block (RSS)
- CryptoSlate (RSS)

Video Sources (YouTube RSS):
- Coin Bureau - Educational crypto content
- Benjamin Cowen - Technical analysis
- Altcoin Daily - Daily crypto news
- Bankless - Ethereum/DeFi focused
- The Defiant - DeFi news

Note: TikTok doesn't have a public API for content, so we focus on
established crypto news sources with RSS feeds or public APIs.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import feedparser
import trafilatura
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlparse

from app.database import async_session_maker
from app.models import NewsArticle
from app.services.news_image_cache import download_image_as_base64

logger = logging.getLogger(__name__)

# Track when we last refreshed news (in-memory for this process)
_last_news_refresh: Optional[datetime] = None

router = APIRouter(prefix="/api/news", tags=["news"])

# Cache configuration
CACHE_FILE = Path(__file__).parent.parent.parent / "news_cache.json"
VIDEO_CACHE_FILE = Path(__file__).parent.parent.parent / "video_cache.json"
FEAR_GREED_CACHE_FILE = Path(__file__).parent.parent.parent / "fear_greed_cache.json"
BLOCK_HEIGHT_CACHE_FILE = Path(__file__).parent.parent.parent / "block_height_cache.json"
US_DEBT_CACHE_FILE = Path(__file__).parent.parent.parent / "us_debt_cache.json"
# News/video: check for new content every 15 mins, keep items for 7 days
NEWS_CACHE_CHECK_MINUTES = 15  # How often to check for new articles/videos
NEWS_ITEM_MAX_AGE_DAYS = 7  # Prune items older than this
FEAR_GREED_CACHE_MINUTES = 15  # Update fear/greed every 15 minutes
BLOCK_HEIGHT_CACHE_MINUTES = 10  # Update block height every 10 minutes
US_DEBT_CACHE_HOURS = 24  # Update US debt once per day

# News sources configuration
NEWS_SOURCES = {
    "reddit_crypto": {
        "name": "Reddit r/CryptoCurrency",
        "url": "https://www.reddit.com/r/CryptoCurrency/hot.json?limit=15",
        "type": "reddit",
        "website": "https://www.reddit.com/r/CryptoCurrency",
    },
    "reddit_bitcoin": {
        "name": "Reddit r/Bitcoin",
        "url": "https://www.reddit.com/r/Bitcoin/hot.json?limit=10",
        "type": "reddit",
        "website": "https://www.reddit.com/r/Bitcoin",
    },
    "coindesk": {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "type": "rss",
        "website": "https://www.coindesk.com",
    },
    "cointelegraph": {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
        "type": "rss",
        "website": "https://cointelegraph.com",
    },
    "decrypt": {
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
        "type": "rss",
        "website": "https://decrypt.co",
    },
    "theblock": {
        "name": "The Block",
        "url": "https://www.theblock.co/rss.xml",
        "type": "rss",
        "website": "https://www.theblock.co",
    },
    "cryptoslate": {
        "name": "CryptoSlate",
        "url": "https://cryptoslate.com/feed/",
        "type": "rss",
        "website": "https://cryptoslate.com",
    },
}

# YouTube video sources - most reputable crypto channels
VIDEO_SOURCES = {
    "coin_bureau": {
        "name": "Coin Bureau",
        "channel_id": "UCqK_GSMbpiV8spgD3ZGloSw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCqK_GSMbpiV8spgD3ZGloSw",
        "website": "https://www.youtube.com/@CoinBureau",
        "description": "Educational crypto content & analysis",
    },
    "benjamin_cowen": {
        "name": "Benjamin Cowen",
        "channel_id": "UCRvqjQPSeaWn-uEx-w0XOIg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCRvqjQPSeaWn-uEx-w0XOIg",
        "website": "https://www.youtube.com/@intothecryptoverse",
        "description": "Technical analysis & market cycles",
    },
    "altcoin_daily": {
        "name": "Altcoin Daily",
        "channel_id": "UCbLhGKVY-bJPcawebgtNfbw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCbLhGKVY-bJPcawebgtNfbw",
        "website": "https://www.youtube.com/@AltcoinDaily",
        "description": "Daily crypto news & updates",
    },
    "bankless": {
        "name": "Bankless",
        "channel_id": "UCAl9Ld79qaZxp9JzEOwd3aA",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCAl9Ld79qaZxp9JzEOwd3aA",
        "website": "https://www.youtube.com/@Bankless",
        "description": "Ethereum & DeFi ecosystem",
    },
    "the_defiant": {
        "name": "The Defiant",
        "channel_id": "UCL0J4MLEdLP0-UyLu0hCktg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCL0J4MLEdLP0-UyLu0hCktg",
        "website": "https://www.youtube.com/@TheDefiant",
        "description": "DeFi news & interviews",
    },
    "crypto_banter": {
        "name": "Crypto Banter",
        "channel_id": "UCN9Nj4tjXbVTLYWN0EKly_Q",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCN9Nj4tjXbVTLYWN0EKly_Q",
        "website": "https://www.youtube.com/@CryptoBanter",
        "description": "Live crypto shows & trading",
    },
}


class NewsItem(BaseModel):
    """Individual news item"""
    title: str
    url: str
    source: str
    source_name: str
    published: Optional[str] = None
    summary: Optional[str] = None
    thumbnail: Optional[str] = None


class VideoItem(BaseModel):
    """Individual video item from YouTube"""
    title: str
    url: str
    video_id: str
    source: str
    source_name: str
    channel_name: str
    published: Optional[str] = None
    thumbnail: Optional[str] = None
    description: Optional[str] = None


class NewsResponse(BaseModel):
    """News API response"""
    news: List[NewsItem]
    sources: List[Dict[str, str]]
    cached_at: str
    cache_expires_at: str
    total_items: int


class VideoResponse(BaseModel):
    """Video API response"""
    videos: List[VideoItem]
    sources: List[Dict[str, str]]
    cached_at: str
    cache_expires_at: str
    total_items: int


class FearGreedData(BaseModel):
    """Fear & Greed Index data"""
    value: int  # 0-100
    value_classification: str  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    timestamp: str
    time_until_update: Optional[str] = None


class FearGreedResponse(BaseModel):
    """Fear & Greed API response"""
    data: FearGreedData
    cached_at: str
    cache_expires_at: str


class BlockHeightResponse(BaseModel):
    """BTC block height API response"""
    height: int
    timestamp: str


class USDebtResponse(BaseModel):
    """US National Debt API response"""
    total_debt: float  # Total public debt in dollars
    debt_per_second: float  # Rate of change per second (for animation)
    gdp: float  # US GDP in dollars
    debt_to_gdp_ratio: float  # Debt as percentage of GDP
    record_date: str  # Date of the debt record
    cached_at: str
    cache_expires_at: str


class ArticleContentResponse(BaseModel):
    """Article content extraction response"""
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    success: bool
    error: Optional[str] = None


class DebtCeilingEvent(BaseModel):
    """Individual debt ceiling event"""
    date: str  # ISO format date
    amount_trillion: Optional[float]  # Amount in trillions (None if suspended)
    suspended: bool  # True if ceiling was suspended
    suspension_end: Optional[str]  # When suspension ends (if applicable)
    note: str  # Description of the event
    legislation: Optional[str]  # Name of the bill/act
    political_context: Optional[str]  # Political circumstances and key facts
    source_url: Optional[str]  # URL to source/reference for this event


class DebtCeilingHistoryResponse(BaseModel):
    """Debt ceiling history API response"""
    events: List[DebtCeilingEvent]
    total_events: int
    last_updated: str  # When this data was last verified


# Historical debt ceiling events (most recent first)
# Source: Congressional Research Service (RL31967), Treasury, Congress.gov
# This data changes only when Congress passes new legislation (~1-2 years)
# Complete history from 1939 (first statutory limit) to present
DEBT_CEILING_HISTORY: List[Dict[str, Any]] = [
    # 2025 - Present
    {
        "date": "2025-01-02",
        "amount_trillion": 36.1,
        "suspended": False,
        "suspension_end": None,
        "note": "Reset after suspension ended",
        "legislation": "Fiscal Responsibility Act of 2023",
        "political_context": "Automatic reset per the 2023 deal. Debt ceiling reinstated at actual debt level. New Republican House expected to demand spending cuts for next increase.",
        "source_url": "https://www.congress.gov/bill/118th-congress/house-bill/3746",
    },
    # 2023
    {
        "date": "2023-06-03",
        "amount_trillion": None,
        "suspended": True,
        "suspension_end": "2025-01-01",
        "note": "Suspended until January 1, 2025",
        "legislation": "Fiscal Responsibility Act of 2023",
        "political_context": "Result of tense 2023 debt ceiling standoff. Biden vs. McCarthy negotiations. Republicans demanded spending caps in exchange for raising limit. Deal included work requirements for some benefits and clawback of COVID funds.",
        "source_url": "https://www.congress.gov/bill/118th-congress/house-bill/3746",
    },
    # 2021
    {
        "date": "2021-12-16",
        "amount_trillion": 31.4,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $2.5T",
        "legislation": "P.L. 117-73",
        "political_context": "Democrats used reconciliation to pass without Republican votes. McConnell agreed to procedural workaround after threatening default. Avoided filibuster through special expedited process.",
        "source_url": "https://www.congress.gov/bill/117th-congress/senate-bill/3273",
    },
    {
        "date": "2021-10-14",
        "amount_trillion": 28.9,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $480B (short-term)",
        "legislation": "P.L. 117-50",
        "political_context": "Emergency short-term fix after summer 2021 standoff. Republicans initially refused to cooperate. Treasury used extraordinary measures. McConnell eventually allowed 11 Republicans to break filibuster.",
        "source_url": "https://www.congress.gov/bill/117th-congress/senate-bill/1301",
    },
    {
        "date": "2021-08-01",
        "amount_trillion": 28.4,
        "suspended": False,
        "suspension_end": None,
        "note": "Reset after suspension ended",
        "legislation": "Bipartisan Budget Act of 2019",
        "political_context": "Automatic reset when 2019 suspension expired. Treasury immediately began extraordinary measures. Set stage for fall 2021 debt ceiling crisis.",
        "source_url": "https://www.congress.gov/bill/116th-congress/house-bill/3877",
    },
    # 2019
    {
        "date": "2019-08-02",
        "amount_trillion": None,
        "suspended": True,
        "suspension_end": "2021-07-31",
        "note": "Suspended until July 31, 2021",
        "legislation": "Bipartisan Budget Act of 2019",
        "political_context": "Bipartisan deal between Trump administration and Democratic House. Pelosi negotiated with Mnuchin. Suspended ceiling through 2021 election cycle to avoid political volatility.",
        "source_url": "https://www.congress.gov/bill/116th-congress/house-bill/3877",
    },
    {
        "date": "2019-03-02",
        "amount_trillion": 22.0,
        "suspended": False,
        "suspension_end": None,
        "note": "Reset after suspension ended",
        "legislation": "Bipartisan Budget Act of 2018",
        "political_context": "Automatic reset from 2018 suspension. Treasury began extraordinary measures immediately while Congress negotiated new deal.",
        "source_url": "https://www.congress.gov/bill/115th-congress/house-bill/1892",
    },
    # 2018
    {
        "date": "2018-02-09",
        "amount_trillion": None,
        "suspended": True,
        "suspension_end": "2019-03-01",
        "note": "Suspended until March 1, 2019",
        "legislation": "Bipartisan Budget Act of 2018",
        "political_context": "Part of deal ending brief government shutdown. Trump era with Republican Congress. Increased defense and domestic spending. Rand Paul objected, causing temporary lapse.",
        "source_url": "https://www.congress.gov/bill/115th-congress/house-bill/1892",
    },
    # 2017
    {
        "date": "2017-12-08",
        "amount_trillion": None,
        "suspended": True,
        "suspension_end": "2018-01-31",
        "note": "Suspended until January 31, 2018",
        "legislation": "P.L. 115-96",
        "political_context": "Short-term suspension tied to continuing resolution. Part of year-end budget negotiations. First Trump-era ceiling suspension.",
        "source_url": "https://www.congress.gov/bill/115th-congress/house-bill/1370",
    },
    {
        "date": "2017-09-08",
        "amount_trillion": None,
        "suspended": True,
        "suspension_end": "2017-12-08",
        "note": "Suspended until December 8, 2017",
        "legislation": "P.L. 115-56",
        "political_context": "Trump shocked Republicans by cutting deal with Pelosi and Schumer. Harvey disaster relief attached. Ryan and McConnell blindsided by bipartisan approach.",
        "source_url": "https://www.congress.gov/bill/115th-congress/house-bill/601",
    },
    {
        "date": "2017-03-16",
        "amount_trillion": 19.8,
        "suspended": False,
        "suspension_end": None,
        "note": "Reset after suspension ended",
        "legislation": "Bipartisan Budget Act of 2015",
        "political_context": "Automatic reset from Obama-era suspension. Trump inherited debt ceiling issue. Republicans controlled both chambers but struggled to raise limit they had previously opposed under Obama.",
        "source_url": "https://www.congress.gov/bill/114th-congress/house-bill/1314",
    },
    # 2015
    {
        "date": "2015-11-02",
        "amount_trillion": None,
        "suspended": True,
        "suspension_end": "2017-03-15",
        "note": "Suspended until March 15, 2017",
        "legislation": "Bipartisan Budget Act of 2015",
        "political_context": "Boehner's final major act as Speaker. Negotiated with Obama before resigning. Passed with mostly Democratic votes. Cleared debt ceiling issue through 2016 election.",
        "source_url": "https://www.congress.gov/bill/114th-congress/house-bill/1314",
    },
    {
        "date": "2015-03-16",
        "amount_trillion": 18.1,
        "suspended": False,
        "suspension_end": None,
        "note": "Reset after suspension ended",
        "legislation": "Temporary Debt Limit Extension Act",
        "political_context": "Automatic reset from 2014 suspension. Treasury began extraordinary measures while Congress debated.",
        "source_url": "https://www.congress.gov/bill/113th-congress/senate-bill/540",
    },
    # 2014
    {
        "date": "2014-02-15",
        "amount_trillion": None,
        "suspended": True,
        "suspension_end": "2015-03-15",
        "note": "Suspended until March 15, 2015",
        "legislation": "Temporary Debt Limit Extension Act",
        "political_context": "Clean debt ceiling increase with no conditions. House Republicans allowed vote without majority support from their caucus. Boehner faced Tea Party backlash.",
        "source_url": "https://www.congress.gov/bill/113th-congress/senate-bill/540",
    },
    # 2013
    {
        "date": "2013-10-17",
        "amount_trillion": None,
        "suspended": True,
        "suspension_end": "2014-02-07",
        "note": "Suspended until February 7, 2014",
        "legislation": "Continuing Appropriations Act, 2014",
        "political_context": "Ended 16-day government shutdown. Cruz-led effort to defund Obamacare failed. Republicans suffered political damage. Clean increase with no conditions attached.",
        "source_url": "https://www.congress.gov/bill/113th-congress/house-bill/2775",
    },
    {
        "date": "2013-05-19",
        "amount_trillion": 16.7,
        "suspended": False,
        "suspension_end": None,
        "note": "Reset after suspension ended",
        "legislation": "No Budget, No Pay Act of 2013",
        "political_context": "Automatic reset when suspension expired. Set stage for fall 2013 shutdown crisis.",
        "source_url": "https://www.congress.gov/bill/113th-congress/house-bill/325",
    },
    {
        "date": "2013-02-04",
        "amount_trillion": None,
        "suspended": True,
        "suspension_end": "2013-05-18",
        "note": "Suspended until May 18, 2013",
        "legislation": "No Budget, No Pay Act of 2013",
        "political_context": "Novel approach: suspended ceiling but withheld congressional pay if no budget passed. Attempt to force budget process. First use of suspension mechanism.",
        "source_url": "https://www.congress.gov/bill/113th-congress/house-bill/325",
    },
    # 2012
    {
        "date": "2012-01-30",
        "amount_trillion": 16.4,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $1.2T (final tranche)",
        "legislation": "Budget Control Act of 2011",
        "political_context": "Final automatic increase under 2011 deal. Congress could have blocked via disapproval resolution but didn't have votes to override veto.",
        "source_url": "https://www.congress.gov/bill/112th-congress/senate-bill/365",
    },
    # 2011
    {
        "date": "2011-09-22",
        "amount_trillion": 15.2,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $500B (second tranche)",
        "legislation": "Budget Control Act of 2011",
        "political_context": "Automatic increase per BCA. Part of staged increases. House voted to disapprove but Senate did not take up resolution.",
        "source_url": "https://www.congress.gov/bill/112th-congress/senate-bill/365",
    },
    {
        "date": "2011-08-02",
        "amount_trillion": 14.7,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $400B (first tranche)",
        "legislation": "Budget Control Act of 2011",
        "political_context": "HISTORIC CRISIS: Resolved hours before X-date. Tea Party Republicans demanded spending cuts. S&P downgraded US credit for first time ever. Created sequester mechanism. Obama called it 'manufactured crisis.'",
        "source_url": "https://www.congress.gov/bill/112th-congress/senate-bill/365",
    },
    # 2010
    {
        "date": "2010-02-12",
        "amount_trillion": 14.3,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $1.9T",
        "legislation": "P.L. 111-139",
        "political_context": "Passed with only Democratic votes. Republicans uniformly opposed despite voting for increases under Bush. First Obama-era increase. Used PAYGO rules.",
        "source_url": "https://www.congress.gov/bill/111th-congress/house-joint-resolution/45",
    },
    # 2009
    {
        "date": "2009-12-28",
        "amount_trillion": 12.4,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $290B (short-term)",
        "legislation": "P.L. 111-123",
        "political_context": "Emergency increase during financial crisis recovery. Democratic Congress, Obama administration. Passed quietly to avoid political fight.",
        "source_url": "https://www.congress.gov/bill/111th-congress/house-joint-resolution/64",
    },
    {
        "date": "2009-02-17",
        "amount_trillion": 12.1,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $789B (ARRA)",
        "legislation": "American Recovery and Reinvestment Act",
        "political_context": "Included in Obama's stimulus package responding to 2008 financial crisis. Largest fiscal stimulus in US history at the time. Passed with minimal Republican support.",
        "source_url": "https://www.congress.gov/bill/111th-congress/house-bill/1",
    },
    # 2008
    {
        "date": "2008-10-03",
        "amount_trillion": 11.3,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $700B (TARP)",
        "legislation": "Emergency Economic Stabilization Act",
        "political_context": "FINANCIAL CRISIS: Attached to TARP bank bailout. First House vote failed, markets crashed. Bush/Paulson scrambled for votes. Eventually passed after adding sweeteners.",
        "source_url": "https://www.congress.gov/bill/110th-congress/house-bill/1424",
    },
    {
        "date": "2008-07-30",
        "amount_trillion": 10.6,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $800B",
        "legislation": "Housing and Economic Recovery Act",
        "political_context": "Attached to housing rescue bill during subprime crisis. Created Fannie/Freddie conservatorship authority. Passed with bipartisan support as crisis deepened.",
        "source_url": "https://www.congress.gov/bill/110th-congress/house-bill/3221",
    },
    # 2007
    {
        "date": "2007-09-29",
        "amount_trillion": 9.8,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $850B",
        "legislation": "P.L. 110-91",
        "political_context": "Democratic Congress, Bush administration. Routine increase but tension building over Iraq war spending and deficit concerns.",
        "source_url": "https://www.congress.gov/bill/110th-congress/house-joint-resolution/43",
    },
    # 2006
    {
        "date": "2006-03-20",
        "amount_trillion": 8.97,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $781B",
        "legislation": "P.L. 109-182",
        "political_context": "Republican Congress, Bush administration. Democrats opposed, calling it 'fiscal irresponsibility.' Every Senate Democrat voted no. Passed on party-line vote.",
        "source_url": "https://www.congress.gov/bill/109th-congress/house-joint-resolution/47",
    },
    # 2004
    {
        "date": "2004-11-19",
        "amount_trillion": 8.18,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $800B",
        "legislation": "P.L. 108-415",
        "political_context": "Republican Congress, Bush administration. Third major increase under Bush. Democrats criticized Iraq war costs and tax cuts for wealthy.",
        "source_url": "https://www.congress.gov/bill/108th-congress/senate-bill/2986",
    },
    # 2003
    {
        "date": "2003-05-27",
        "amount_trillion": 7.38,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $984B",
        "legislation": "P.L. 108-24",
        "political_context": "Republican Congress, Bush administration. Second increase in two years. Iraq War begun two months earlier. Economy still recovering from dot-com bust.",
        "source_url": "https://www.congress.gov/bill/108th-congress/house-joint-resolution/51",
    },
    # 2002
    {
        "date": "2002-06-28",
        "amount_trillion": 6.4,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $450B",
        "legislation": "P.L. 107-199",
        "political_context": "Post-9/11 era, Bush administration. War on Terror began. First Bush-era increase after inheriting Clinton surpluses. Bipartisan support given national security context.",
        "source_url": "https://www.congress.gov/bill/107th-congress/house-joint-resolution/111",
    },
    # 1997
    {
        "date": "1997-08-05",
        "amount_trillion": 5.95,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $450B",
        "legislation": "Balanced Budget Act of 1997",
        "political_context": "Clinton-Gingrich balanced budget deal. Economy booming, deficits shrinking toward surplus. Bipartisan agreement after 1995-96 shutdown battles.",
        "source_url": "https://www.congress.gov/bill/105th-congress/house-bill/2015",
    },
    # 1996
    {
        "date": "1996-03-29",
        "amount_trillion": 5.5,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $600B",
        "legislation": "Contract With America Advancement Act",
        "political_context": "Resolved 1995-96 debt ceiling crisis and government shutdowns. Gingrich vs. Clinton battles. Republicans eventually backed down after public blamed them for shutdowns.",
        "source_url": "https://www.congress.gov/bill/104th-congress/house-bill/3136",
    },
    # 1993
    {
        "date": "1993-08-10",
        "amount_trillion": 4.9,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $530B",
        "legislation": "Omnibus Budget Reconciliation Act of 1993",
        "political_context": "Clinton's deficit reduction package. Passed without a single Republican vote. Raised taxes on wealthy, cut spending. Set stage for late-90s balanced budgets.",
        "source_url": "https://www.congress.gov/bill/103rd-congress/house-bill/2264",
    },
    # 1990
    {
        "date": "1990-11-05",
        "amount_trillion": 4.15,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $915B",
        "legislation": "Omnibus Budget Reconciliation Act of 1990",
        "political_context": "Bush Sr. broke 'read my lips, no new taxes' pledge. Bipartisan budget deal with tax increases and spending cuts. Cost Bush politically but reduced deficit.",
        "source_url": "https://www.congress.gov/bill/101st-congress/house-bill/5835",
    },
    # 1989
    {
        "date": "1989-11-08",
        "amount_trillion": 3.23,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $203B",
        "legislation": "P.L. 101-140",
        "political_context": "Bush Sr. first year. Routine increase. Gramm-Rudman-Hollings deficit targets still in effect.",
        "source_url": "https://www.congress.gov/bill/101st-congress/house-joint-resolution/280",
    },
    # 1987
    {
        "date": "1987-09-29",
        "amount_trillion": 2.8,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $520B",
        "legislation": "P.L. 100-119",
        "political_context": "Reagan era. Black Monday stock market crash occurred weeks later. Revised Gramm-Rudman deficit targets. Iran-Contra scandal ongoing.",
        "source_url": "https://www.congress.gov/bill/100th-congress/house-joint-resolution/324",
    },
    # 1986
    {
        "date": "1986-08-21",
        "amount_trillion": 2.11,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $189B",
        "legislation": "P.L. 99-384",
        "political_context": "Reagan administration, Democratic House. Deficits rising despite Gramm-Rudman. Tax Reform Act of 1986 passed same year.",
        "source_url": "https://www.congress.gov/bill/99th-congress/house-joint-resolution/668",
    },
    # 1985
    {
        "date": "1985-12-12",
        "amount_trillion": 2.08,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $80B",
        "legislation": "Gramm-Rudman-Hollings Balanced Budget Act",
        "political_context": "Historic deficit control legislation. Automatic spending cuts (sequester) if targets missed. Attempt to force balanced budgets. Supreme Court later struck down key provisions.",
        "source_url": "https://www.congress.gov/bill/99th-congress/house-joint-resolution/372",
    },
    {
        "date": "1985-11-14",
        "amount_trillion": 1.82,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised temporarily",
        "legislation": "P.L. 99-155",
        "political_context": "Short-term increase while Congress debated Gramm-Rudman.",
        "source_url": "https://www.congress.gov/bill/99th-congress/house-joint-resolution/442",
    },
    # 1984
    {
        "date": "1984-07-06",
        "amount_trillion": 1.57,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $171B",
        "legislation": "Deficit Reduction Act of 1984",
        "political_context": "Reagan's 'Morning in America' re-election year. Deficits controversial but economy booming. Democrats controlled House.",
        "source_url": "https://www.congress.gov/bill/98th-congress/house-bill/4170",
    },
    # 1983
    {
        "date": "1983-11-21",
        "amount_trillion": 1.49,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $101B",
        "legislation": "P.L. 98-161",
        "political_context": "Economy recovering from 1981-82 recession. Reagan tax cuts increasing deficits. Social Security rescue legislation passed earlier in year.",
        "source_url": "https://www.congress.gov/bill/98th-congress/house-joint-resolution/308",
    },
    {
        "date": "1983-05-26",
        "amount_trillion": 1.39,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $99B",
        "legislation": "P.L. 98-34",
        "political_context": "Continued Reagan-era deficit expansion. Supply-side economics tested. Unemployment still high from recession.",
        "source_url": "https://www.congress.gov/bill/98th-congress/house-joint-resolution/190",
    },
    # 1982
    {
        "date": "1982-09-30",
        "amount_trillion": 1.29,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $98B",
        "legislation": "P.L. 97-270",
        "political_context": "Deep recession. Volcker fighting inflation with high interest rates. Reagan's deficits growing. TEFRA tax increase passed to offset some revenue loss.",
        "source_url": "https://www.congress.gov/bill/97th-congress/house-joint-resolution/520",
    },
    {
        "date": "1982-06-28",
        "amount_trillion": 1.14,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $400M",
        "legislation": "P.L. 97-204",
        "political_context": "Minimal increase during economic turmoil. Recession deepening.",
        "source_url": "https://www.congress.gov/bill/97th-congress/house-joint-resolution/308",
    },
    # 1981
    {
        "date": "1981-09-30",
        "amount_trillion": 1.08,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $79B",
        "legislation": "P.L. 97-49",
        "political_context": "Reagan's first major budget. Economic Recovery Tax Act cut taxes dramatically. Deficits projected to rise significantly.",
        "source_url": "https://www.congress.gov/bill/97th-congress/house-joint-resolution/266",
    },
    {
        "date": "1981-02-07",
        "amount_trillion": 0.985,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $50B",
        "legislation": "P.L. 97-2",
        "political_context": "Reagan's first days in office. Inherited Carter-era ceiling. Routine increase.",
        "source_url": "https://www.congress.gov/bill/97th-congress/house-joint-resolution/74",
    },
    # 1980
    {
        "date": "1980-06-28",
        "amount_trillion": 0.925,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $45B",
        "legislation": "P.L. 96-286",
        "political_context": "Carter administration, election year. Stagflation crisis. Iran hostage crisis ongoing. Fed fighting inflation.",
        "source_url": "https://www.congress.gov/bill/96th-congress/house-bill/7428",
    },
    # 1979
    {
        "date": "1979-09-29",
        "amount_trillion": 0.879,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $49B",
        "legislation": "P.L. 96-78",
        "political_context": "Carter administration. Energy crisis, 'malaise' speech. Volcker appointed Fed chair to fight inflation.",
        "source_url": "https://www.congress.gov/bill/96th-congress/house-joint-resolution/375",
    },
    {
        "date": "1979-04-02",
        "amount_trillion": 0.83,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $29B",
        "legislation": "P.L. 96-5",
        "political_context": "Three Mile Island nuclear accident occurred same week. Carter struggling with energy policy.",
        "source_url": "https://www.congress.gov/bill/96th-congress/house-joint-resolution/214",
    },
    # 1978
    {
        "date": "1978-10-03",
        "amount_trillion": 0.798,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $46B",
        "legislation": "P.L. 95-435",
        "political_context": "Carter administration. Camp David Accords signed. Economy facing inflation pressure.",
        "source_url": "https://www.congress.gov/bill/95th-congress/house-joint-resolution/1139",
    },
    {
        "date": "1978-08-03",
        "amount_trillion": 0.752,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised (temporary)",
        "legislation": "P.L. 95-333",
        "political_context": "Short-term increase. Budget process reforms being implemented.",
        "source_url": "https://www.congress.gov/bill/95th-congress/house-joint-resolution/914",
    },
    # 1977
    {
        "date": "1977-10-04",
        "amount_trillion": 0.752,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $52B",
        "legislation": "P.L. 95-120",
        "political_context": "Carter's first year. Democratic Congress. New budget process from 1974 reform still being implemented.",
        "source_url": "https://www.congress.gov/bill/95th-congress/house-joint-resolution/487",
    },
    # 1976
    {
        "date": "1976-06-30",
        "amount_trillion": 0.7,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $95B",
        "legislation": "P.L. 94-334",
        "political_context": "Ford administration, bicentennial year. Post-Watergate era. First budget under reformed budget process.",
        "source_url": "https://www.congress.gov/bill/94th-congress/house-joint-resolution/803",
    },
    # 1975
    {
        "date": "1975-11-14",
        "amount_trillion": 0.595,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $38B",
        "legislation": "P.L. 94-132",
        "political_context": "Ford administration. Recession ending. New York City fiscal crisis. Congressional Budget Act of 1974 restructuring budget process.",
        "source_url": "https://www.congress.gov/bill/94th-congress/house-joint-resolution/662",
    },
    {
        "date": "1975-06-30",
        "amount_trillion": 0.577,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $45B",
        "legislation": "P.L. 94-47",
        "political_context": "Ford dealing with recession and aftermath of Nixon resignation. Vietnam War ending.",
        "source_url": "https://www.congress.gov/bill/94th-congress/house-joint-resolution/453",
    },
    {
        "date": "1975-02-19",
        "amount_trillion": 0.531,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $24B",
        "legislation": "P.L. 94-3",
        "political_context": "Ford administration. Deep recession (worst since 1930s at the time). Tax cuts to stimulate economy.",
        "source_url": "https://www.congress.gov/bill/94th-congress/house-joint-resolution/79",
    },
    # 1974
    {
        "date": "1974-06-30",
        "amount_trillion": 0.495,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $18B",
        "legislation": "P.L. 93-325",
        "political_context": "Nixon's final months before resignation. Watergate crisis. Congress passed landmark budget reform act same year.",
        "source_url": "https://www.congress.gov/bill/93rd-congress/house-joint-resolution/981",
    },
    # 1973
    {
        "date": "1973-12-03",
        "amount_trillion": 0.475,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $10B",
        "legislation": "P.L. 93-173",
        "political_context": "Nixon administration. Arab oil embargo causing energy crisis. Watergate hearings ongoing.",
        "source_url": "https://www.congress.gov/bill/93rd-congress/house-joint-resolution/763",
    },
    {
        "date": "1973-07-01",
        "amount_trillion": 0.465,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $15B",
        "legislation": "P.L. 93-53",
        "political_context": "Watergate scandal deepening. Saturday Night Massacre months away. Economy still strong but inflation rising.",
        "source_url": "https://www.congress.gov/bill/93rd-congress/house-joint-resolution/523",
    },
    # 1972
    {
        "date": "1972-10-27",
        "amount_trillion": 0.465,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised (temporary extension)",
        "legislation": "P.L. 92-599",
        "political_context": "Nixon landslide election. Vietnam War winding down. Détente with Soviet Union.",
        "source_url": "https://www.congress.gov/bill/92nd-congress/house-joint-resolution/1262",
    },
    {
        "date": "1972-06-30",
        "amount_trillion": 0.45,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $20B",
        "legislation": "P.L. 92-336",
        "political_context": "Nixon administration. Watergate break-in occurred two weeks earlier (not yet public scandal). Price controls in effect.",
        "source_url": "https://www.congress.gov/bill/92nd-congress/house-bill/12910",
    },
    # 1971
    {
        "date": "1971-03-17",
        "amount_trillion": 0.43,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $30B",
        "legislation": "P.L. 92-5",
        "political_context": "Nixon administration. Vietnam War costs mounting. Gold standard about to end (August). Budget moving toward deficit.",
        "source_url": "https://www.congress.gov/bill/92nd-congress/house-resolution/287",
    },
    # 1970
    {
        "date": "1970-06-30",
        "amount_trillion": 0.395,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $18B",
        "legislation": "P.L. 91-301",
        "political_context": "Nixon administration. Vietnam War escalation (Cambodia). Student protests. Recession beginning.",
        "source_url": "https://www.congress.gov/bill/91st-congress/house-bill/17889",
    },
    # 1969
    {
        "date": "1969-04-07",
        "amount_trillion": 0.377,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $12B",
        "legislation": "P.L. 91-8",
        "political_context": "Nixon's first months in office. Vietnam War ongoing. Inherited LBJ's 'guns and butter' deficit spending.",
        "source_url": "https://www.congress.gov/bill/91st-congress/house-resolution/328",
    },
    # 1967
    {
        "date": "1967-06-30",
        "amount_trillion": 0.358,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $22B",
        "legislation": "P.L. 90-39",
        "political_context": "LBJ administration. Vietnam War escalation. Great Society spending. 'Guns and butter' deficit spending began.",
        "source_url": "https://www.congress.gov/bill/90th-congress/house-joint-resolution/510",
    },
    # 1965
    {
        "date": "1965-06-28",
        "amount_trillion": 0.328,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $4B",
        "legislation": "P.L. 89-49",
        "political_context": "LBJ's Great Society in full swing. Medicare/Medicaid passed. Vietnam War buildup beginning. Economy booming.",
        "source_url": "https://www.congress.gov/bill/89th-congress/house-bill/8467",
    },
    # 1963
    {
        "date": "1963-05-29",
        "amount_trillion": 0.309,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $4B (temporary)",
        "legislation": "P.L. 88-30",
        "political_context": "JFK administration. Civil rights movement growing. Kennedy tax cuts being debated. Assassination months away.",
        "source_url": "https://www.congress.gov/bill/88th-congress/house-joint-resolution/383",
    },
    # 1962
    {
        "date": "1962-07-01",
        "amount_trillion": 0.308,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $10B",
        "legislation": "P.L. 87-512",
        "political_context": "JFK administration. Cuban Missile Crisis months away. Space race with Soviets. Economy recovering from 1960-61 recession.",
        "source_url": "https://www.congress.gov/bill/87th-congress/house-joint-resolution/767",
    },
    # 1961
    {
        "date": "1961-06-30",
        "amount_trillion": 0.298,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $5B (temporary)",
        "legislation": "P.L. 87-69",
        "political_context": "JFK's first months in office. Bay of Pigs fiasco. Berlin Wall built months later. Recession inherited from Eisenhower.",
        "source_url": "https://www.congress.gov/bill/87th-congress/house-joint-resolution/396",
    },
    # 1959
    {
        "date": "1959-06-30",
        "amount_trillion": 0.295,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $10B",
        "legislation": "P.L. 86-74",
        "political_context": "Eisenhower administration. Post-Sputnik spending. Alaska and Hawaii becoming states. Recession recovery.",
        "source_url": "https://www.congress.gov/bill/86th-congress/house-joint-resolution/390",
    },
    # 1958
    {
        "date": "1958-09-02",
        "amount_trillion": 0.288,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $8B",
        "legislation": "P.L. 85-912",
        "political_context": "Eisenhower administration. Post-Sputnik panic. Defense spending surge. Recession underway.",
        "source_url": "https://www.congress.gov/bill/85th-congress/house-joint-resolution/688",
    },
    {
        "date": "1958-02-26",
        "amount_trillion": 0.28,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $5B (temporary)",
        "legislation": "P.L. 85-336",
        "political_context": "Sputnik launched months earlier. Space race begun. Emergency defense spending.",
        "source_url": "https://www.congress.gov/bill/85th-congress/house-joint-resolution/502",
    },
    # 1956
    {
        "date": "1956-07-09",
        "amount_trillion": 0.278,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $3B",
        "legislation": "P.L. 84-678",
        "political_context": "Eisenhower re-election year. Interstate Highway System authorized. Suez Crisis months away. Economy prosperous.",
        "source_url": "https://www.congress.gov/bill/84th-congress/house-joint-resolution/580",
    },
    # 1954
    {
        "date": "1954-08-28",
        "amount_trillion": 0.281,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised by $6B",
        "legislation": "P.L. 83-686",
        "political_context": "Eisenhower administration. Korean War ended. McCarthy hearings. Post-war economic adjustment.",
        "source_url": "https://www.congress.gov/bill/83rd-congress/house-joint-resolution/506",
    },
    # 1946
    {
        "date": "1946-06-26",
        "amount_trillion": 0.275,
        "suspended": False,
        "suspension_end": None,
        "note": "Reduced from wartime peak",
        "legislation": "P.L. 79-472",
        "political_context": "Post-WWII demobilization. Ceiling actually lowered as war debt being paid down. Truman administration. Economy transitioning to peacetime.",
        "source_url": None,
    },
    # 1945
    {
        "date": "1945-04-03",
        "amount_trillion": 0.3,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised for final war push",
        "legislation": "P.L. 79-28",
        "political_context": "WWII final months. FDR died weeks later. Germany surrendered May 8. Japan surrendered in August after atomic bombs.",
        "source_url": None,
    },
    # 1944
    {
        "date": "1944-06-09",
        "amount_trillion": 0.26,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised for D-Day campaign",
        "legislation": "P.L. 78-333",
        "political_context": "D-Day invasion (June 6) days earlier. Massive war spending. FDR's fourth term campaign. War bonds heavily promoted.",
        "source_url": None,
    },
    # 1943
    {
        "date": "1943-04-11",
        "amount_trillion": 0.21,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised for war production",
        "legislation": "P.L. 78-34",
        "political_context": "Peak of WWII production. Stalingrad victory. North Africa campaign. War mobilization in full swing.",
        "source_url": None,
    },
    # 1942
    {
        "date": "1942-03-28",
        "amount_trillion": 0.125,
        "suspended": False,
        "suspension_end": None,
        "note": "Massive wartime increase",
        "legislation": "P.L. 77-510",
        "political_context": "WWII after Pearl Harbor. Massive war mobilization. Debt ceiling raised dramatically to fund war. Rationing began.",
        "source_url": None,
    },
    # 1941
    {
        "date": "1941-02-19",
        "amount_trillion": 0.065,
        "suspended": False,
        "suspension_end": None,
        "note": "Pre-war defense buildup",
        "legislation": "P.L. 77-3",
        "political_context": "Defense spending increasing before Pearl Harbor. Lend-Lease to Britain. FDR's third term began.",
        "source_url": None,
    },
    # 1940
    {
        "date": "1940-06-25",
        "amount_trillion": 0.049,
        "suspended": False,
        "suspension_end": None,
        "note": "Raised for defense",
        "legislation": "P.L. 76-672",
        "political_context": "France had just fallen to Germany. War in Europe. FDR beginning defense buildup. Still officially neutral.",
        "source_url": None,
    },
    # 1939 - First aggregate statutory debt limit
    {
        "date": "1939-07-01",
        "amount_trillion": 0.045,
        "suspended": False,
        "suspension_end": None,
        "note": "First aggregate debt limit",
        "legislation": "P.L. 76-201",
        "political_context": "HISTORIC: First statutory debt ceiling. Combined all previous separate debt categories. WWII began in Europe two months later. Depression ending.",
        "source_url": None,
    },
]


def load_cache(for_merge: bool = False) -> Optional[Dict[str, Any]]:
    """Load news cache from file.

    Args:
        for_merge: If True, return cache even if expired (for merging new items)
    """
    if not CACHE_FILE.exists():
        return None

    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache needs refresh (15 minutes)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        cache_age = datetime.now() - cached_at

        if for_merge:
            # For merging, return cache regardless of age
            return cache

        if cache_age > timedelta(minutes=NEWS_CACHE_CHECK_MINUTES):
            logger.info(f"News cache needs refresh (age: {cache_age})")
            return None

        return cache
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load news cache: {e}")
        return None


def prune_old_items(items: List[Dict], max_age_days: int = NEWS_ITEM_MAX_AGE_DAYS) -> List[Dict]:
    """Remove items older than max_age_days based on published date."""
    cutoff = datetime.now() - timedelta(days=max_age_days)
    pruned = []
    removed_count = 0

    for item in items:
        published = item.get("published")
        if not published:
            # Keep items without published date (rare edge case)
            pruned.append(item)
            continue

        try:
            # Handle both with and without Z suffix
            pub_str = published.rstrip("Z")
            pub_date = datetime.fromisoformat(pub_str)

            if pub_date >= cutoff:
                pruned.append(item)
            else:
                removed_count += 1
        except (ValueError, TypeError):
            # If we can't parse date, keep the item
            pruned.append(item)

    if removed_count > 0:
        logger.info(f"Pruned {removed_count} items older than {max_age_days} days")

    return pruned


def merge_news_items(existing: List[Dict], new_items: List[Dict]) -> List[Dict]:
    """Merge new items with existing cache. New items go to top, deduped by URL."""
    # Create set of existing URLs for fast lookup
    existing_urls = {item.get("url") for item in existing if item.get("url")}

    # Find truly new items
    truly_new = [item for item in new_items if item.get("url") not in existing_urls]

    if truly_new:
        logger.info(f"Found {len(truly_new)} new news items to add")

    # New items at top, then existing (already sorted by date)
    merged = truly_new + existing

    # Sort by published date (most recent first)
    merged.sort(
        key=lambda x: x.get("published") or "1970-01-01",
        reverse=True
    )

    return merged


def save_cache(data: Dict[str, Any]) -> None:
    """Save news cache to file"""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("News cache saved")
    except Exception as e:
        logger.error(f"Failed to save news cache: {e}")


# =============================================================================
# Database Functions for News Articles
# =============================================================================


async def get_articles_from_db(db: AsyncSession, limit: int = 100) -> List[NewsArticle]:
    """Get recent news articles from database, sorted by published date."""
    cutoff = datetime.utcnow() - timedelta(days=NEWS_ITEM_MAX_AGE_DAYS)
    result = await db.execute(
        select(NewsArticle)
        .where(NewsArticle.published_at >= cutoff)
        .order_by(desc(NewsArticle.published_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def store_article_in_db(
    db: AsyncSession,
    item: NewsItem,
    image_data: Optional[str] = None
) -> Optional[NewsArticle]:
    """Store a news article in the database. Returns None if already exists."""
    # Check if article already exists by URL
    result = await db.execute(
        select(NewsArticle).where(NewsArticle.url == item.url)
    )
    existing = result.scalars().first()
    if existing:
        return None  # Already exists

    # Parse published date
    published_at = None
    if item.published:
        try:
            pub_str = item.published.rstrip("Z")
            published_at = datetime.fromisoformat(pub_str)
        except (ValueError, TypeError):
            pass

    article = NewsArticle(
        title=item.title,
        url=item.url,
        source=item.source,
        published_at=published_at,
        summary=item.summary,
        original_thumbnail_url=item.thumbnail,
        image_data=image_data,  # Base64 data URI
        fetched_at=datetime.utcnow(),
    )
    db.add(article)
    return article


async def cleanup_old_articles(db: AsyncSession, max_age_days: int = NEWS_ITEM_MAX_AGE_DAYS) -> int:
    """Delete articles older than max_age_days. Returns count deleted."""
    from sqlalchemy import delete
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    result = await db.execute(
        delete(NewsArticle).where(NewsArticle.fetched_at < cutoff)
    )
    await db.commit()
    deleted_count = result.rowcount
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} old news articles from database")
    return deleted_count


def article_to_news_item(article: NewsArticle) -> Dict[str, Any]:
    """Convert a NewsArticle database object to a NewsItem dict for API response."""
    # Use base64 image data if available, otherwise fall back to original URL
    thumbnail = article.image_data or article.original_thumbnail_url
    return {
        "title": article.title,
        "url": article.url,
        "source": article.source,
        "source_name": NEWS_SOURCES.get(article.source, {}).get("name", article.source),
        "published": article.published_at.isoformat() + "Z" if article.published_at else None,
        "summary": article.summary,
        "thumbnail": thumbnail,
    }


def load_video_cache(for_merge: bool = False) -> Optional[Dict[str, Any]]:
    """Load video cache from file.

    Args:
        for_merge: If True, return cache even if expired (for merging new items)
    """
    if not VIDEO_CACHE_FILE.exists():
        return None

    try:
        with open(VIDEO_CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache needs refresh (15 minutes)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        cache_age = datetime.now() - cached_at

        if for_merge:
            # For merging, return cache regardless of age
            return cache

        if cache_age > timedelta(minutes=NEWS_CACHE_CHECK_MINUTES):
            logger.info(f"Video cache needs refresh (age: {cache_age})")
            return None

        return cache
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load video cache: {e}")
        return None


def save_video_cache(data: Dict[str, Any]) -> None:
    """Save video cache to file"""
    try:
        with open(VIDEO_CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Video cache saved")
    except Exception as e:
        logger.error(f"Failed to save video cache: {e}")


def load_fear_greed_cache() -> Optional[Dict[str, Any]]:
    """Load fear/greed cache from file (15 minute cache)"""
    if not FEAR_GREED_CACHE_FILE.exists():
        return None

    try:
        with open(FEAR_GREED_CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache is expired (15 minutes)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(minutes=FEAR_GREED_CACHE_MINUTES):
            logger.info("Fear/Greed cache expired")
            return None

        return cache
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load fear/greed cache: {e}")
        return None


def save_fear_greed_cache(data: Dict[str, Any]) -> None:
    """Save fear/greed cache to file"""
    try:
        with open(FEAR_GREED_CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Fear/Greed cache saved")
    except Exception as e:
        logger.error(f"Failed to save fear/greed cache: {e}")


def load_block_height_cache() -> Optional[Dict[str, Any]]:
    """Load block height cache from file (10 minute cache)"""
    if not BLOCK_HEIGHT_CACHE_FILE.exists():
        return None

    try:
        with open(BLOCK_HEIGHT_CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache is expired (10 minutes)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(minutes=BLOCK_HEIGHT_CACHE_MINUTES):
            logger.info("Block height cache expired")
            return None

        return cache
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load block height cache: {e}")
        return None


def save_block_height_cache(data: Dict[str, Any]) -> None:
    """Save block height cache to file"""
    try:
        with open(BLOCK_HEIGHT_CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Block height cache saved")
    except Exception as e:
        logger.error(f"Failed to save block height cache: {e}")


async def fetch_btc_block_height() -> Dict[str, Any]:
    """Fetch current BTC block height from blockchain.info API"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}
            async with session.get(
                "https://blockchain.info/q/getblockcount",
                headers=headers,
                timeout=10
            ) as response:
                if response.status != 200:
                    logger.warning(f"Blockchain.info API returned {response.status}")
                    raise HTTPException(status_code=503, detail="Block height API unavailable")

                height_text = await response.text()
                height = int(height_text.strip())

                now = datetime.now()
                cache_data = {
                    "height": height,
                    "timestamp": now.isoformat(),
                    "cached_at": now.isoformat(),
                }

                # Save to cache
                save_block_height_cache(cache_data)

                return cache_data
    except asyncio.TimeoutError:
        logger.warning("Timeout fetching BTC block height")
        raise HTTPException(status_code=503, detail="Block height API timeout")
    except ValueError as e:
        logger.error(f"Invalid block height response: {e}")
        raise HTTPException(status_code=503, detail="Invalid block height response")
    except Exception as e:
        logger.error(f"Error fetching BTC block height: {e}")
        raise HTTPException(status_code=503, detail=f"Block height API error: {str(e)}")


def load_us_debt_cache() -> Optional[Dict[str, Any]]:
    """Load US debt cache from file (24-hour cache)"""
    if not US_DEBT_CACHE_FILE.exists():
        return None

    try:
        with open(US_DEBT_CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache is expired (24 hours)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(hours=US_DEBT_CACHE_HOURS):
            logger.info("US debt cache expired")
            return None

        return cache
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load US debt cache: {e}")
        return None


def save_us_debt_cache(data: Dict[str, Any]) -> None:
    """Save US debt cache to file"""
    try:
        with open(US_DEBT_CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("US debt cache saved")
    except Exception as e:
        logger.error(f"Failed to save US debt cache: {e}")


async def fetch_us_debt() -> Dict[str, Any]:
    """Fetch US National Debt from Treasury Fiscal Data API and GDP from FRED"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            # Get most recent debt data (last 2 records to calculate rate)
            debt_url = (
                "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
                "v2/accounting/od/debt_to_penny"
                "?sort=-record_date&page[size]=2"
            )

            # Fetch debt data
            async with session.get(debt_url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"Treasury API returned {response.status}")
                    raise HTTPException(status_code=503, detail="Treasury API unavailable")

                data = await response.json()
                records = data.get("data", [])

                if len(records) < 1:
                    raise HTTPException(status_code=503, detail="No debt data available")

                # Get current debt
                latest = records[0]
                total_debt = float(latest.get("tot_pub_debt_out_amt", 0))
                record_date = latest.get("record_date", "")

                # Calculate rate of change per second
                # Default: ~$1T/year = ~$31,710/second (debt always grows long-term)
                default_rate = 31710.0
                debt_per_second = default_rate

                if len(records) >= 2:
                    prev = records[1]
                    prev_debt = float(prev.get("tot_pub_debt_out_amt", 0))
                    prev_date = prev.get("record_date", "")

                    if prev_date and record_date:
                        date1 = datetime.strptime(record_date, "%Y-%m-%d")
                        date2 = datetime.strptime(prev_date, "%Y-%m-%d")
                        days_diff = (date1 - date2).days

                        if days_diff > 0:
                            debt_change = total_debt - prev_debt
                            seconds_diff = days_diff * 24 * 60 * 60
                            calculated_rate = debt_change / seconds_diff
                            # Only use calculated rate if positive (debt normally grows)
                            # Negative rates can occur due to temporary accounting adjustments
                            if calculated_rate > 0:
                                debt_per_second = calculated_rate
                            else:
                                logger.info("Treasury data shows temporary debt decrease, using default rate")
                                debt_per_second = default_rate

            # Fetch GDP from FRED (Federal Reserve) - no API key needed for this endpoint
            gdp = 28_000_000_000_000.0  # Default ~$28T fallback
            try:
                gdp_url = (
                    "https://api.stlouisfed.org/fred/series/observations"
                    "?series_id=GDP&api_key=DEMO_KEY&file_type=json"
                    "&sort_order=desc&limit=1"
                )
                async with session.get(gdp_url, headers=headers, timeout=10) as gdp_response:
                    if gdp_response.status == 200:
                        gdp_data = await gdp_response.json()
                        observations = gdp_data.get("observations", [])
                        if observations:
                            # FRED GDP is in billions, convert to dollars
                            gdp_billions = float(observations[0].get("value", 28000))
                            gdp = gdp_billions * 1_000_000_000
                    else:
                        logger.warning(f"FRED GDP API returned {gdp_response.status}, using fallback")
            except Exception as e:
                logger.warning(f"Failed to fetch GDP: {e}, using fallback")

            # Calculate debt-to-GDP ratio
            debt_to_gdp_ratio = (total_debt / gdp * 100) if gdp > 0 else 0

            now = datetime.now()
            cache_data = {
                "total_debt": total_debt,
                "debt_per_second": debt_per_second,
                "gdp": gdp,
                "debt_to_gdp_ratio": round(debt_to_gdp_ratio, 2),
                "record_date": record_date,
                "cached_at": now.isoformat(),
                "cache_expires_at": (now + timedelta(hours=US_DEBT_CACHE_HOURS)).isoformat(),
            }

            # Save to cache
            save_us_debt_cache(cache_data)

            return cache_data
    except asyncio.TimeoutError:
        logger.warning("Timeout fetching US debt")
        raise HTTPException(status_code=503, detail="Treasury API timeout")
    except Exception as e:
        logger.error(f"Error fetching US debt: {e}")
        raise HTTPException(status_code=503, detail=f"Treasury API error: {str(e)}")


async def fetch_fear_greed_index() -> Dict[str, Any]:
    """Fetch Fear & Greed Index from Alternative.me API"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}
            async with session.get(
                "https://api.alternative.me/fng/",
                headers=headers,
                timeout=10
            ) as response:
                if response.status != 200:
                    logger.warning(f"Fear/Greed API returned {response.status}")
                    raise HTTPException(status_code=503, detail="Fear/Greed API unavailable")

                data = await response.json()
                fng_data = data.get("data", [{}])[0]

                now = datetime.now()
                cache_data = {
                    "data": {
                        "value": int(fng_data.get("value", 50)),
                        "value_classification": fng_data.get("value_classification", "Neutral"),
                        "timestamp": datetime.fromtimestamp(int(fng_data.get("timestamp", 0))).isoformat(),
                        "time_until_update": fng_data.get("time_until_update"),
                    },
                    "cached_at": now.isoformat(),
                    "cache_expires_at": (now + timedelta(minutes=FEAR_GREED_CACHE_MINUTES)).isoformat(),
                }

                # Save to cache
                save_fear_greed_cache(cache_data)

                return cache_data
    except asyncio.TimeoutError:
        logger.warning("Timeout fetching Fear/Greed index")
        raise HTTPException(status_code=503, detail="Fear/Greed API timeout")
    except Exception as e:
        logger.error(f"Error fetching Fear/Greed index: {e}")
        raise HTTPException(status_code=503, detail=f"Fear/Greed API error: {str(e)}")


async def fetch_youtube_videos(session: aiohttp.ClientSession, source_id: str, config: Dict) -> List[VideoItem]:
    """Fetch videos from YouTube RSS feed"""
    items = []
    try:
        headers = {"User-Agent": "ZenithGrid/1.0"}
        async with session.get(config["url"], headers=headers, timeout=15) as response:
            if response.status != 200:
                logger.warning(f"YouTube RSS returned {response.status} for {source_id}")
                return items

            content = await response.text()
            feed = feedparser.parse(content)

            for entry in feed.entries[:8]:  # Get latest 8 videos per channel
                # Parse published date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        # Add Z suffix to indicate UTC timezone
                        published = datetime(*entry.published_parsed[:6]).isoformat() + "Z"
                    except (ValueError, TypeError):
                        pass

                # Extract video ID from link (supports regular videos and Shorts)
                video_id = ""
                link = entry.get("link", "")
                if "watch?v=" in link:
                    video_id = link.split("watch?v=")[-1].split("&")[0]
                elif "/shorts/" in link:
                    # YouTube Shorts: https://www.youtube.com/shorts/VIDEO_ID
                    video_id = link.split("/shorts/")[-1].split("?")[0]

                # Get thumbnail (YouTube provides standard thumbnails)
                thumbnail = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg" if video_id else None

                # Get description/summary
                description = None
                if hasattr(entry, "media_group") and entry.media_group:
                    desc = entry.media_group.get("media_description", "")
                    if desc:
                        description = desc[:200] if len(desc) > 200 else desc
                elif hasattr(entry, "summary"):
                    description = entry.summary[:200] if len(entry.summary) > 200 else entry.summary

                items.append(VideoItem(
                    title=entry.get("title", ""),
                    url=link,
                    video_id=video_id,
                    source=source_id,
                    source_name=config["name"],
                    channel_name=config["name"],
                    published=published,
                    thumbnail=thumbnail,
                    description=description,
                ))
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching videos from {source_id}")
    except Exception as e:
        logger.error(f"Error fetching videos from {source_id}: {e}")

    return items


async def fetch_all_videos() -> Dict[str, Any]:
    """Fetch videos from all YouTube sources and merge with existing cache.

    Strategy:
    - Fetch fresh videos from all sources
    - Merge with existing cached videos (new items at top, dedupe by URL)
    - Prune videos older than 7 days
    - Save merged cache
    """
    fresh_items: List[VideoItem] = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        for source_id, config in VIDEO_SOURCES.items():
            tasks.append(fetch_youtube_videos(session, source_id, config))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                fresh_items.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Video fetch task failed: {result}")

    # Convert to dicts for merge
    fresh_dicts = [item.model_dump() for item in fresh_items]

    # Load existing cache for merge (even if "expired")
    existing_cache = load_video_cache(for_merge=True)
    existing_items = existing_cache.get("videos", []) if existing_cache else []

    # Merge: add new items to existing, dedupe by URL
    merged_items = merge_news_items(existing_items, fresh_dicts)

    # Prune videos older than 7 days
    merged_items = prune_old_items(merged_items)

    # Build sources list for UI
    sources_list = [
        {"id": sid, "name": cfg["name"], "website": cfg["website"], "description": cfg["description"]}
        for sid, cfg in VIDEO_SOURCES.items()
    ]

    now = datetime.now()
    cache_data = {
        "videos": merged_items,
        "sources": sources_list,
        "cached_at": now.isoformat(),
        "cache_expires_at": (now + timedelta(minutes=NEWS_CACHE_CHECK_MINUTES)).isoformat(),
        "total_items": len(merged_items),
    }

    # Save to cache
    save_video_cache(cache_data)

    return cache_data


async def fetch_reddit_news(session: aiohttp.ClientSession, source_id: str, config: Dict) -> List[NewsItem]:
    """Fetch news from Reddit JSON API"""
    items = []
    try:
        # Reddit requires a descriptive user-agent per their API rules
        headers = {
            "User-Agent": "ZenithGrid:v1.0 (by /u/zenithgrid_bot)",
            "Accept": "application/json",
        }
        async with session.get(config["url"], headers=headers, timeout=15) as response:
            if response.status != 200:
                logger.warning(f"Reddit API returned {response.status} for {source_id}")
                return items

            data = await response.json()
            posts = data.get("data", {}).get("children", [])

            for post in posts[:15]:
                post_data = post.get("data", {})
                if post_data.get("stickied"):
                    continue

                # Get thumbnail if available
                thumbnail = post_data.get("thumbnail")
                if thumbnail in ["self", "default", "nsfw", "spoiler", ""]:
                    thumbnail = None

                items.append(NewsItem(
                    title=post_data.get("title", ""),
                    url=f"https://reddit.com{post_data.get('permalink', '')}",
                    source=source_id,
                    source_name=config["name"],
                    # Add Z suffix to indicate UTC timezone (created_utc is Unix UTC timestamp)
                    published=datetime.utcfromtimestamp(post_data.get("created_utc", 0)).isoformat() + "Z",
                    summary=post_data.get("selftext", "")[:200] if post_data.get("selftext") else None,
                    thumbnail=thumbnail,
                ))
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {source_id}")
    except Exception as e:
        logger.error(f"Error fetching {source_id}: {e}")

    return items


async def fetch_rss_news(session: aiohttp.ClientSession, source_id: str, config: Dict) -> List[NewsItem]:
    """Fetch news from RSS feed"""
    items = []
    try:
        headers = {"User-Agent": "ZenithGrid/1.0"}
        async with session.get(config["url"], headers=headers, timeout=15) as response:
            if response.status != 200:
                logger.warning(f"RSS feed returned {response.status} for {source_id}")
                return items

            content = await response.text()
            feed = feedparser.parse(content)

            for entry in feed.entries[:10]:
                # Parse published date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        # Add Z suffix to indicate UTC timezone
                        published = datetime(*entry.published_parsed[:6]).isoformat() + "Z"
                    except (ValueError, TypeError):
                        pass

                # Get summary
                summary = None
                if hasattr(entry, "summary"):
                    # Strip HTML tags (simple approach)
                    summary = entry.summary
                    if "<" in summary:
                        import re
                        summary = re.sub(r"<[^>]+>", "", summary)
                    summary = summary[:200] if len(summary) > 200 else summary

                # Get thumbnail
                thumbnail = None
                if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                    thumbnail = entry.media_thumbnail[0].get("url")
                elif hasattr(entry, "media_content") and entry.media_content:
                    thumbnail = entry.media_content[0].get("url")

                items.append(NewsItem(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    source=source_id,
                    source_name=config["name"],
                    published=published,
                    summary=summary,
                    thumbnail=thumbnail,
                ))
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {source_id}")
    except Exception as e:
        logger.error(f"Error fetching {source_id}: {e}")

    return items


async def fetch_all_news() -> None:
    """Fetch news from all sources, cache images, and store in database.

    Strategy:
    - Fetch fresh items from all sources
    - Download and cache thumbnail images locally
    - Store new articles in database (deduped by URL)
    - Skip articles that already exist
    """
    global _last_news_refresh
    fresh_items: List[NewsItem] = []

    async with aiohttp.ClientSession() as session:
        # Fetch news from all sources
        tasks = []
        for source_id, config in NEWS_SOURCES.items():
            if config["type"] == "reddit":
                tasks.append(fetch_reddit_news(session, source_id, config))
            elif config["type"] == "rss":
                tasks.append(fetch_rss_news(session, source_id, config))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                fresh_items.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Task failed: {result}")

        # Download images as base64 and store articles in database
        new_articles_count = 0
        async with async_session_maker() as db:
            for item in fresh_items:
                # Download thumbnail as base64 data URI if present
                image_data = None
                if item.thumbnail:
                    image_data = await download_image_as_base64(session, item.thumbnail)

                # Store in database (returns None if already exists)
                article = await store_article_in_db(db, item, image_data)
                if article:
                    new_articles_count += 1

            await db.commit()

        if new_articles_count > 0:
            logger.info(f"Added {new_articles_count} new news articles to database")

    _last_news_refresh = datetime.utcnow()


async def get_news_from_db() -> Dict[str, Any]:
    """Get news articles from database and format for API response."""
    async with async_session_maker() as db:
        articles = await get_articles_from_db(db, limit=100)

    # Convert to API response format
    news_items = [article_to_news_item(article) for article in articles]

    # Build sources list for UI
    sources_list = [
        {"id": sid, "name": cfg["name"], "website": cfg["website"]}
        for sid, cfg in NEWS_SOURCES.items()
    ]

    now = datetime.utcnow()
    return {
        "news": news_items,
        "sources": sources_list,
        "cached_at": now.isoformat() + "Z",
        "cache_expires_at": (now + timedelta(minutes=NEWS_CACHE_CHECK_MINUTES)).isoformat() + "Z",
        "total_items": len(news_items),
    }


@router.get("/", response_model=NewsResponse)
async def get_news(force_refresh: bool = False):
    """
    Get crypto news from database cache.

    News is fetched from multiple sources and stored in the database.
    Checks for new content every 15 minutes, keeps articles for 7 days.
    Use force_refresh=true to bypass cache timing and fetch fresh data.
    """
    global _last_news_refresh

    # Determine if we need to refresh from sources
    needs_refresh = force_refresh
    if not needs_refresh and _last_news_refresh:
        cache_age = datetime.utcnow() - _last_news_refresh
        if cache_age > timedelta(minutes=NEWS_CACHE_CHECK_MINUTES):
            needs_refresh = True
            logger.info(f"News cache needs refresh (age: {cache_age})")
    elif not _last_news_refresh:
        # First request since server start - check if we have recent data
        needs_refresh = True

    # Fetch fresh news if needed
    if needs_refresh:
        logger.info("Fetching fresh news from all sources...")
        try:
            await fetch_all_news()
        except Exception as e:
            logger.error(f"Failed to fetch news: {e}")
            # Continue to serve from database even if fetch fails

    # Get news from database
    try:
        data = await get_news_from_db()
        if data["news"]:
            logger.info(f"Serving {len(data['news'])} news articles from database")
            return NewsResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get news from database: {e}")

    # Fall back to old JSON cache if database is empty or fails
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                stale_cache = json.load(f)
            logger.warning("Serving from JSON cache (database empty or failed)")
            return NewsResponse(**stale_cache)
        except Exception:
            pass

    raise HTTPException(status_code=503, detail="No news available")


@router.get("/sources")
async def get_sources():
    """Get list of news sources with links"""
    return {
        "sources": [
            {"id": sid, "name": cfg["name"], "website": cfg["website"], "type": cfg["type"]}
            for sid, cfg in NEWS_SOURCES.items()
        ],
        "note": "TikTok is not included as it lacks a public API for content. "
                "These sources provide reliable crypto news via RSS feeds or public APIs."
    }


@router.get("/cache-stats")
async def get_cache_stats():
    """Get news cache statistics including database article count."""
    # Get article count and articles with images from database
    async with async_session_maker() as db:
        from sqlalchemy import func
        result = await db.execute(select(func.count(NewsArticle.id)))
        article_count = result.scalar() or 0

        # Count articles with embedded images
        result = await db.execute(
            select(func.count(NewsArticle.id)).where(NewsArticle.image_data.isnot(None))
        )
        articles_with_images = result.scalar() or 0

    return {
        "database": {
            "article_count": article_count,
            "articles_with_images": articles_with_images,
        },
        "last_refresh": _last_news_refresh.isoformat() + "Z" if _last_news_refresh else None,
        "cache_check_interval_minutes": NEWS_CACHE_CHECK_MINUTES,
        "max_age_days": NEWS_ITEM_MAX_AGE_DAYS,
    }


@router.post("/cleanup")
async def cleanup_cache():
    """Manually trigger cleanup of old news articles (older than 7 days)."""
    # Cleanup old articles from database (images are stored inline, so they're deleted with articles)
    async with async_session_maker() as db:
        articles_deleted = await cleanup_old_articles(db)

    return {
        "articles_deleted": articles_deleted,
        "message": f"Cleaned up {articles_deleted} articles older than {NEWS_ITEM_MAX_AGE_DAYS} days"
    }


@router.get("/videos", response_model=VideoResponse)
async def get_videos(force_refresh: bool = False):
    """
    Get cached crypto video news from YouTube channels.

    Videos are fetched from reputable crypto YouTube channels and cached for 24 hours.
    Use force_refresh=true to bypass cache and fetch fresh data.
    """
    # Try to load from cache first
    if not force_refresh:
        cache = load_video_cache()
        if cache:
            logger.info("Serving videos from cache")
            return VideoResponse(**cache)

    # Fetch fresh videos
    logger.info("Fetching fresh videos from YouTube channels...")
    try:
        data = await fetch_all_videos()
        return VideoResponse(**data)
    except Exception as e:
        logger.error(f"Failed to fetch videos: {e}")

        # Try to serve stale cache if available
        if VIDEO_CACHE_FILE.exists():
            try:
                with open(VIDEO_CACHE_FILE, "r") as f:
                    stale_cache = json.load(f)
                logger.warning("Serving stale video cache due to fetch failure")
                return VideoResponse(**stale_cache)
            except Exception:
                pass

        raise HTTPException(status_code=503, detail="Unable to fetch videos")


@router.get("/video-sources")
async def get_video_sources():
    """Get list of video sources (YouTube channels) with links"""
    return {
        "sources": [
            {
                "id": sid,
                "name": cfg["name"],
                "website": cfg["website"],
                "description": cfg["description"],
            }
            for sid, cfg in VIDEO_SOURCES.items()
        ],
        "note": "These are reputable crypto YouTube channels providing educational content, "
                "market analysis, and news coverage."
    }


@router.get("/fear-greed", response_model=FearGreedResponse)
async def get_fear_greed():
    """
    Get the Crypto Fear & Greed Index.

    The index ranges from 0 (Extreme Fear) to 100 (Extreme Greed).
    Data is cached for 15 minutes.

    Source: Alternative.me Crypto Fear & Greed Index
    """
    # Try to load from cache first
    cache = load_fear_greed_cache()
    if cache:
        logger.info("Serving Fear/Greed from cache")
        return FearGreedResponse(**cache)

    # Fetch fresh data
    logger.info("Fetching fresh Fear/Greed index...")
    data = await fetch_fear_greed_index()
    return FearGreedResponse(**data)


@router.get("/btc-block-height", response_model=BlockHeightResponse)
async def get_btc_block_height():
    """
    Get the current Bitcoin block height.

    Used for BTC halving countdown calculations.
    Data is cached for 10 minutes.

    Source: blockchain.info
    """
    # Try to load from cache first
    cache = load_block_height_cache()
    if cache:
        logger.info("Serving BTC block height from cache")
        return BlockHeightResponse(**cache)

    # Fetch fresh data
    logger.info("Fetching fresh BTC block height...")
    data = await fetch_btc_block_height()
    return BlockHeightResponse(**data)


@router.get("/us-debt", response_model=USDebtResponse)
async def get_us_debt():
    """
    Get the current US National Debt with rate of change.

    Returns total debt, debt per second (for animation), GDP, and debt-to-GDP ratio.
    Data is cached for 24 hours.

    Sources:
    - Treasury Fiscal Data API (debt)
    - FRED Federal Reserve API (GDP)
    """
    # Try to load from cache first
    cache = load_us_debt_cache()
    if cache:
        logger.info("Serving US debt from cache")
        return USDebtResponse(**cache)

    # Fetch fresh data
    logger.info("Fetching fresh US debt data...")
    data = await fetch_us_debt()
    return USDebtResponse(**data)


@router.get("/debt-ceiling-history", response_model=DebtCeilingHistoryResponse)
async def get_debt_ceiling_history(limit: int = 100):
    """
    Get historical debt ceiling changes/suspensions.

    Returns debt ceiling legislation events from 1939 (first statutory limit) to present.
    Data is sourced from Congressional Research Service (RL31967) and Treasury records.

    Note: Debt ceiling changes require Congressional action and happen infrequently
    (typically every 1-2 years). This data is updated when new legislation passes.

    Query params:
    - limit: Number of events to return (default: 100, max: 100 to get all events)
    """
    # Clamp limit to reasonable range
    limit = max(1, min(limit, 100))

    events = DEBT_CEILING_HISTORY[:limit]

    return DebtCeilingHistoryResponse(
        events=[DebtCeilingEvent(**e) for e in events],
        total_events=len(DEBT_CEILING_HISTORY),
        last_updated="2025-11-29",  # Update this when adding new ceiling events
    )


# Allowed domains for article content extraction (security measure)
ALLOWED_ARTICLE_DOMAINS = {
    "coindesk.com",
    "www.coindesk.com",
    "cointelegraph.com",
    "www.cointelegraph.com",
    "decrypt.co",
    "www.decrypt.co",
    "theblock.co",
    "www.theblock.co",
    "cryptoslate.com",
    "www.cryptoslate.com",
    "reddit.com",
    "www.reddit.com",
    "old.reddit.com",
}


@router.get("/article-content", response_model=ArticleContentResponse)
async def get_article_content(url: str):
    """
    Extract article content from a news URL.

    Uses trafilatura to extract the main article text, title, and metadata.
    Only allows fetching from trusted crypto news domains for security.

    Returns clean, readable article content like browser reader mode.
    """
    # Validate URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ArticleContentResponse(
                url=url,
                success=False,
                error="Invalid URL format"
            )

        # Security check: only allow known news domains
        domain = parsed.netloc.lower()
        if domain not in ALLOWED_ARTICLE_DOMAINS:
            logger.warning(f"Attempted to fetch article from non-allowed domain: {domain}")
            return ArticleContentResponse(
                url=url,
                success=False,
                error=f"Domain not allowed. Supported: {', '.join(sorted(ALLOWED_ARTICLE_DOMAINS))}"
            )
    except Exception as e:
        return ArticleContentResponse(
            url=url,
            success=False,
            error=f"URL validation failed: {str(e)}"
        )

    try:
        # Fetch the page content with browser-like headers to avoid 403 blocks
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"macOS"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
            async with session.get(url, headers=headers, timeout=15, allow_redirects=True) as response:
                if response.status != 200:
                    return ArticleContentResponse(
                        url=url,
                        success=False,
                        error=f"Failed to fetch article: HTTP {response.status}"
                    )

                html_content = await response.text()

        # Extract article content using trafilatura
        # Run in executor since trafilatura is synchronous
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            extracted = await asyncio.get_event_loop().run_in_executor(
                executor,
                lambda: trafilatura.extract(
                    html_content,
                    include_comments=False,
                    include_tables=True,  # Include tables for structure
                    no_fallback=False,
                    favor_precision=True,
                    output_format="markdown"  # Use markdown to preserve headings, lists, etc.
                )
            )

            # Also extract metadata
            metadata = await asyncio.get_event_loop().run_in_executor(
                executor,
                lambda: trafilatura.extract_metadata(html_content)
            )

        if not extracted:
            return ArticleContentResponse(
                url=url,
                success=False,
                error="Could not extract article content. The page may be paywalled or use dynamic loading."
            )

        # Build response with metadata if available
        title = None
        author = None
        date = None

        if metadata:
            title = metadata.title
            author = metadata.author
            if metadata.date:
                date = metadata.date

        logger.info(f"Successfully extracted article from {domain}: {len(extracted)} chars")

        return ArticleContentResponse(
            url=url,
            title=title,
            content=extracted,
            author=author,
            date=date,
            success=True
        )

    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching article: {url}")
        return ArticleContentResponse(
            url=url,
            success=False,
            error="Request timed out. The website may be slow or unavailable."
        )
    except Exception as e:
        logger.error(f"Error extracting article content: {e}")
        return ArticleContentResponse(
            url=url,
            success=False,
            error=f"Failed to extract content: {str(e)}"
        )
