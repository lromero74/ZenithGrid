"""
Pydantic models for the news router API.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel


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
    """News API response with pagination"""
    news: List[NewsItem]
    sources: List[Dict[str, str]]
    cached_at: str
    cache_expires_at: str
    total_items: int
    # Pagination fields
    page: int = 1
    page_size: int = 50
    total_pages: int = 1


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
    # Debt ceiling info
    debt_ceiling: Optional[float] = None  # Current ceiling in dollars (None if suspended)
    debt_ceiling_suspended: bool = False  # True if ceiling is currently suspended
    debt_ceiling_note: Optional[str] = None  # Brief description of current ceiling status
    headroom: Optional[float] = None  # How much room before hitting ceiling (debt_ceiling - total_debt)


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
