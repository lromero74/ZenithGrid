"""Content models: news, videos, sources, TTS, subscriptions."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class AIProviderCredential(Base):
    """
    AI provider API credentials for trading bots.

    Stores API keys for AI providers (Claude, Gemini, Grok, Groq, OpenAI)
    that bots use for market analysis and trading decisions.
    Each user has their own set of AI credentials.
    """

    __tablename__ = "ai_provider_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Provider identification
    provider = Column(String, nullable=False, index=True)  # "claude", "gemini", "grok", "groq", "openai"

    # Credentials
    api_key = Column(String, nullable=False)  # The actual API key (encrypted in production)

    # Metadata
    is_active = Column(Boolean, default=True)  # Can disable without deleting
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="ai_provider_credentials")


class NewsArticle(Base):
    """
    Cached news articles from various crypto news sources.

    Articles are fetched periodically and cached in the database.
    Images are downloaded and stored locally in static/news_images/.
    Articles older than 7 days are automatically cleaned up.
    """

    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, index=True)

    # Article content
    title = Column(String, nullable=False)
    url = Column(String, unique=True, index=True, nullable=False)  # Unique constraint for deduplication
    source = Column(String, nullable=False)  # e.g., "cointelegraph", "coindesk", "reddit"
    published_at = Column(DateTime, nullable=True, index=True)  # When the article was published

    # Optional fields
    summary = Column(Text, nullable=True)  # Article excerpt/summary
    author = Column(String, nullable=True)

    # Image caching - stored as base64 data URI in database
    original_thumbnail_url = Column(String, nullable=True)  # Original external URL
    cached_thumbnail_path = Column(String, nullable=True)  # Deprecated: was local path
    image_data = Column(Text, nullable=True)  # Base64 data URI (e.g., "data:image/jpeg;base64,...")

    # Category for filtering (like Newsmap: World, Nation, Business, Technology, etc.)
    category = Column(String, nullable=False, default="CryptoCurrency", index=True)

    # FK to content_sources for proper relational lookups
    source_id = Column(Integer, ForeignKey("content_sources.id"), nullable=True, index=True)

    # Metadata
    fetched_at = Column(DateTime, default=datetime.utcnow, index=True)  # When we fetched it
    created_at = Column(DateTime, default=datetime.utcnow)

    # Cached full article content (extracted via trafilatura, markdown format)
    content = Column(Text, nullable=True)
    content_fetched_at = Column(DateTime, nullable=True)  # When content was last extracted

    # Content fetch tracking
    content_fetch_failed = Column(Boolean, default=False)  # True if content extraction failed — never re-fetch

    # TTS issue flag (article failed to load/play)
    has_issue = Column(Boolean, default=False)


class VideoArticle(Base):
    """
    Cached video articles from YouTube crypto channels.

    Videos are fetched periodically and cached in the database.
    Thumbnail URLs point to YouTube CDN (no local caching needed).
    Videos older than 7 days are automatically cleaned up.
    """

    __tablename__ = "video_articles"

    id = Column(Integer, primary_key=True, index=True)

    # Video content
    title = Column(String, nullable=False)
    url = Column(String, unique=True, index=True, nullable=False)  # YouTube URL for deduplication
    video_id = Column(String, nullable=False, index=True)  # YouTube video ID
    source = Column(String, nullable=False, index=True)  # e.g., "coin_bureau", "bankless"
    channel_name = Column(String, nullable=False)  # Display name

    # Optional fields
    published_at = Column(DateTime, nullable=True, index=True)  # When the video was published
    description = Column(Text, nullable=True)  # Video description/summary
    thumbnail_url = Column(String, nullable=True)  # YouTube thumbnail URL (CDN)

    # Category for filtering (like Newsmap: World, Nation, Business, Technology, etc.)
    category = Column(String, nullable=False, default="CryptoCurrency", index=True)

    # FK to content_sources for proper relational lookups
    source_id = Column(Integer, ForeignKey("content_sources.id"), nullable=True, index=True)

    # Metadata
    fetched_at = Column(DateTime, default=datetime.utcnow, index=True)  # When we fetched it
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentSource(Base):
    """
    News and video content sources that users can subscribe to.

    System sources (is_system=True) are provided by default and cannot be deleted.
    Users can add custom sources (is_system=False) which they can delete.
    """

    __tablename__ = "content_sources"

    id = Column(Integer, primary_key=True, index=True)
    source_key = Column(String, unique=True, nullable=False)  # e.g., "coin_bureau", "coindesk"
    name = Column(String, nullable=False)  # Display name
    type = Column(String, nullable=False, index=True)  # "news" or "video"
    url = Column(String, nullable=False)  # RSS/YouTube feed URL
    website = Column(String, nullable=True)  # Main website URL
    description = Column(String, nullable=True)
    channel_id = Column(String, nullable=True)  # YouTube channel ID (null for news)
    is_system = Column(Boolean, default=True)  # System sources can't be deleted
    is_enabled = Column(Boolean, default=True, index=True)  # Globally enabled
    category = Column(String, nullable=False, default="CryptoCurrency", index=True)  # News category
    content_scrape_allowed = Column(Boolean, default=True)   # False = RSS-only, no article scraping
    crawl_delay_seconds = Column(Integer, default=0)          # robots.txt crawl-delay
    # Owner for custom sources (null for system)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    subscriptions = relationship("UserSourceSubscription", back_populates="source", cascade="all, delete-orphan")


class UserSourceSubscription(Base):
    """
    Per-user subscription preferences for content sources.

    Users can subscribe/unsubscribe from any source without deleting it.
    By default, users are subscribed to all enabled system sources.
    """

    __tablename__ = "user_source_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(Integer, ForeignKey("content_sources.id", ondelete="CASCADE"), nullable=False)
    is_subscribed = Column(Boolean, default=True)
    user_category = Column(String, nullable=True)  # Per-user category override
    retention_days = Column(Integer, nullable=True)  # Per-user visibility filter (days)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Unique constraint
    __table_args__ = (UniqueConstraint("user_id", "source_id", name="uq_user_source"),)

    # Relationships
    user = relationship("User", back_populates="source_subscriptions")
    source = relationship("ContentSource", back_populates="subscriptions")


class ArticleTTS(Base):
    """Cached TTS audio per article and voice. Shared across users."""

    __tablename__ = "article_tts"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(
        Integer, ForeignKey("news_articles.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    voice_id = Column(String, nullable=False)
    audio_path = Column(String, nullable=False)
    word_timings = Column(Text, nullable=True)  # JSON array
    file_size_bytes = Column(Integer, nullable=True)
    content_hash = Column(String(8), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("article_id", "voice_id", name="uq_article_voice"),
    )


class UserVoiceSubscription(Base):
    """Per-user voice preferences (which voices are enabled)."""

    __tablename__ = "user_voice_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    voice_id = Column(String, nullable=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "voice_id", name="uq_user_voice"),
    )


class UserArticleTTSHistory(Base):
    """Per-user last-played voice per article (for auto-resume)."""

    __tablename__ = "user_article_tts_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    article_id = Column(
        Integer, ForeignKey("news_articles.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    last_voice_id = Column(String, nullable=False)
    last_played_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "article_id", name="uq_user_article_tts"
        ),
    )


class UserContentSeenStatus(Base):
    """Per-user seen/read tracking for articles and videos."""

    __tablename__ = "user_content_seen_status"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_type = Column(String, nullable=False)   # "article" | "video"
    content_id = Column(Integer, nullable=False)     # news_articles.id or video_articles.id
    seen_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "content_type", "content_id",
            name="uq_user_content_seen",
        ),
        Index(
            "ix_user_content_seen_lookup",
            "user_id", "content_type",
        ),
    )
