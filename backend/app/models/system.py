"""System models: settings, market data, bot/scanner/indicator logs, notifications."""

from app.utils.timeutil import utcnow

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Settings(Base):
    __tablename__ = "settings"
    __table_args__ = {'schema': 'system'}

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(String)
    value_type = Column(String)  # float, int, string, bool
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class MarketData(Base):
    __tablename__ = "market_data"
    __table_args__ = {'schema': 'system'}

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=utcnow, index=True)
    price = Column(Float)

    # MACD indicators
    macd_value = Column(Float, nullable=True)
    macd_signal = Column(Float, nullable=True)
    macd_histogram = Column(Float, nullable=True)

    # For potential future use
    volume = Column(Float, nullable=True)


class AIBotLog(Base):
    __tablename__ = "ai_bot_logs"
    __table_args__ = {'schema': 'system'}

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("trading.bots.id"), index=True)
    position_id = Column(Integer, ForeignKey("trading.positions.id"), nullable=True, index=True)  # Link to position
    timestamp = Column(DateTime, default=utcnow, index=True)

    # AI thinking/reasoning content
    thinking = Column(Text)  # The AI's reasoning process
    decision = Column(String)  # buy, sell, hold, etc.
    confidence = Column(Float, nullable=True)  # 0-100 confidence level

    # Market context at time of decision
    current_price = Column(Float, nullable=True)
    position_status = Column(String, nullable=True)  # open, closed, none
    product_id = Column(String, nullable=True)  # Trading pair (e.g., "AAVE-BTC")

    # Additional context (JSON for flexibility)
    context = Column(JSON, nullable=True)  # Market conditions, indicators, etc.

    # Relationships
    position = relationship("Position", foreign_keys=[position_id])


class ScannerLog(Base):
    """
    Scanner/Monitor logs for non-AI strategies like bull flag.
    Captures pattern detection decisions, volume checks, and reasoning.
    """
    __tablename__ = "scanner_logs"
    __table_args__ = {'schema': 'system'}

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("trading.bots.id"), index=True)
    timestamp = Column(DateTime, default=utcnow, index=True)

    # What was scanned
    product_id = Column(String, nullable=False)  # Trading pair (e.g., "BTC-USD")
    scan_type = Column(String, nullable=False)  # "volume_check", "pattern_check", "entry_signal", "exit_signal"

    # Decision made
    decision = Column(String, nullable=False)  # "passed", "rejected", "triggered", "hold"
    reason = Column(Text)  # Detailed explanation of why

    # Numeric data for the check
    current_price = Column(Float, nullable=True)
    volume_ratio = Column(Float, nullable=True)  # Current volume / average volume
    pattern_data = Column(JSON, nullable=True)  # Pattern details if detected

    # Relationships
    bot = relationship("Bot", foreign_keys=[bot_id])


class IndicatorLog(Base):
    """
    Indicator condition evaluation logs for non-AI indicator-based bots.
    Captures which conditions were checked, their values, and results.
    """
    __tablename__ = "indicator_logs"
    __table_args__ = {'schema': 'system'}

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("trading.bots.id"), index=True)
    timestamp = Column(DateTime, default=utcnow, index=True)

    # What was evaluated
    product_id = Column(String, nullable=False)  # Trading pair (e.g., "ETH-BTC")
    phase = Column(String, nullable=False)  # "base_order", "safety_order", "take_profit"

    # Overall result
    conditions_met = Column(Boolean, nullable=False)  # Did all conditions pass?

    # Detailed condition results (JSON array)
    # Each entry: { type, timeframe, operator, threshold, actual_value, result }
    conditions_detail = Column(JSON, nullable=False)

    # Indicator snapshot at evaluation time (JSON dict)
    # All indicator values that were available
    indicators_snapshot = Column(JSON, nullable=True)

    # Current price at evaluation
    current_price = Column(Float, nullable=True)

    # Relationships
    bot = relationship("Bot", foreign_keys=[bot_id])


class TelegramSettings(Base):
    """Per-user Telegram notification configuration.

    Stores the bot token and chat ID for sending trade notifications
    and receiving commands via Telegram.
    """
    __tablename__ = "telegram_settings"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_telegram_settings_user"),
        {'schema': 'system'},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Telegram bot token (from @BotFather)
    bot_token = Column(String, nullable=False)

    # Chat ID to send notifications to (user's chat with the bot)
    chat_id = Column(String, nullable=False)

    # Notification toggles
    notify_order_filled = Column(Boolean, default=True)
    notify_position_opened = Column(Boolean, default=True)
    notify_position_closed = Column(Boolean, default=True)
    notify_bot_started = Column(Boolean, default=True)
    notify_bot_stopped = Column(Boolean, default=True)

    # Whether the Telegram webhook is active for receiving commands
    commands_enabled = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    user = relationship("User")
