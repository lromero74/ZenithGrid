from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # User-defined bot name
    description = Column(Text, nullable=True)  # Optional description

    # Strategy configuration
    strategy_type = Column(String, index=True)  # e.g., "macd_dca", "rsi", "bollinger_bands"
    strategy_config = Column(JSON)  # JSON object with strategy-specific parameters

    # Trading pairs (support for multi-pair bots)
    product_id = Column(String, default="ETH-BTC", nullable=True)  # Legacy single pair (deprecated)
    product_ids = Column(JSON, default=list)  # List of trading pairs e.g., ["ETH-BTC", "SOL-USD", "BTC-USD"]
    split_budget_across_pairs = Column(Boolean, default=False)  # Whether to divide budget by number of pairs

    # Status
    is_active = Column(Boolean, default=False)  # Whether bot is currently running

    # Check interval (seconds between signal checks)
    # Default varies by AI provider: Gemini=10800s (3h), Claude=300s (5min)
    check_interval_seconds = Column(Integer, default=300, nullable=True)

    # Balance Reservations (prevents bots from borrowing from each other)
    # Each bot has its own allocated balance that it can use
    reserved_btc_balance = Column(Float, default=0.0)  # BTC reserved for this bot (legacy)
    reserved_usd_balance = Column(Float, default=0.0)  # USD reserved for this bot (legacy)
    budget_percentage = Column(Float, default=0.0)  # % of aggregate BTC value (preferred method)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_signal_check = Column(DateTime, nullable=True)  # Last time signal was checked

    # Relationships
    positions = relationship("Position", back_populates="bot", cascade="all, delete-orphan")
    pending_orders = relationship("PendingOrder", back_populates="bot", cascade="all, delete-orphan")

    def get_trading_pairs(self):
        """Get list of trading pairs for this bot (backward compatible)"""
        if self.product_ids and len(self.product_ids) > 0:
            return self.product_ids
        elif self.product_id:
            return [self.product_id]
        else:
            return ["ETH-BTC"]  # Default fallback

    def get_quote_currency(self):
        """Get the quote currency for this bot's trading pairs (BTC or USD)"""
        pairs = self.get_trading_pairs()
        if pairs and len(pairs) > 0:
            # All pairs should have same quote currency (enforced in validation)
            first_pair = pairs[0]
            if '-' in first_pair:
                return first_pair.split('-')[1]
        return "BTC"  # Default

    def get_reserved_balance(self, aggregate_value: float = None):
        """
        Get the reserved balance for this bot's quote currency

        Args:
            aggregate_value: Total value of portfolio in bot's quote currency.
                            For BTC bots: total BTC value (BTC + all pairs as BTC)
                            For USD bots: total USD value (USD + all pairs as USD)
                            If provided and budget_percentage is set, calculates from percentage.

        Returns:
            Total reserved balance in quote currency (BTC or USD) for the entire bot, not per-deal
        """
        quote = self.get_quote_currency()

        # If budget_percentage is set and aggregate_value provided, calculate from percentage
        if self.budget_percentage > 0 and aggregate_value is not None:
            # Bot gets budget_percentage of aggregate value
            # This is the TOTAL budget for the bot, not divided by max_concurrent_deals
            bot_budget = aggregate_value * (self.budget_percentage / 100.0)
            return bot_budget

        # Fallback to legacy reserved balances
        if quote == "USD":
            return self.reserved_usd_balance
        else:
            return self.reserved_btc_balance


class BotTemplate(Base):
    __tablename__ = "bot_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # Template name
    description = Column(Text, nullable=True)  # Optional description

    # Strategy configuration (copied from Bot)
    strategy_type = Column(String, index=True)
    strategy_config = Column(JSON)

    # Default trading pairs (optional)
    product_ids = Column(JSON, default=list)
    split_budget_across_pairs = Column(Boolean, default=False)

    # Template metadata
    is_default = Column(Boolean, default=False)  # System preset vs user-created
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=True)  # Link to bot (nullable for backwards compatibility)
    product_id = Column(String, default="ETH-BTC")  # Trading pair (e.g., "ETH-BTC", "SOL-USD")
    status = Column(String, default="open")  # open, closed
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    # Strategy config snapshot (frozen at position creation - like 3Commas)
    strategy_config_snapshot = Column(JSON, nullable=True)  # Bot's strategy_config at time of position creation

    # Initial balance tracking (quote currency = BTC for BTC pairs, USD for USD pairs)
    initial_quote_balance = Column(Float)
    max_quote_allowed = Column(Float)  # 25% of initial balance (configurable)

    # Position totals
    total_quote_spent = Column(Float, default=0.0)  # Amount of quote currency spent (BTC or USD)
    total_base_acquired = Column(Float, default=0.0)  # Amount of base currency acquired (ETH, ADA, etc.)
    average_buy_price = Column(Float, default=0.0)  # Average price paid (quote/base)

    # Closing metrics
    sell_price = Column(Float, nullable=True)
    total_quote_received = Column(Float, nullable=True)  # Amount of quote currency received from selling
    profit_quote = Column(Float, nullable=True)  # Profit in quote currency
    profit_percentage = Column(Float, nullable=True)

    # USD tracking
    btc_usd_price_at_open = Column(Float, nullable=True)  # BTC/USD price when position opened
    btc_usd_price_at_close = Column(Float, nullable=True)  # BTC/USD price when position closed
    profit_usd = Column(Float, nullable=True)  # Profit in USD

    # Trailing Take Profit tracking
    highest_price_since_tp = Column(Float, nullable=True)  # Highest price after hitting TP target
    trailing_tp_active = Column(Boolean, default=False)  # Whether we've entered trailing TP zone

    # Trailing Stop Loss tracking
    highest_price_since_entry = Column(Float, nullable=True)  # Highest price since position opened (for trailing SL)

    # Error tracking (like 3Commas - show errors in UI with tooltips)
    last_error_message = Column(String, nullable=True)  # Last error message (e.g., from failed DCA)
    last_error_timestamp = Column(DateTime, nullable=True)  # When the error occurred

    # Notes (like 3Commas - user can add notes to positions)
    notes = Column(Text, nullable=True)  # User notes for this position

    # Relationships
    bot = relationship("Bot", back_populates="positions")
    trades = relationship("Trade", back_populates="position", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="position", cascade="all, delete-orphan")
    pending_orders = relationship("PendingOrder", back_populates="position", cascade="all, delete-orphan")

    def get_quote_currency(self) -> str:
        """Get the quote currency from product_id (e.g., 'BTC' from 'ETH-BTC', 'USD' from 'ADA-USD')"""
        if self.product_id and '-' in self.product_id:
            return self.product_id.split('-')[1]
        return 'BTC'  # Default fallback

    def update_averages(self):
        """Recalculate average buy price and totals from trades"""
        buy_trades = [t for t in self.trades if t.side == "buy"]
        if buy_trades:
            total_quote = sum(t.quote_amount for t in buy_trades)
            total_base = sum(t.base_amount for t in buy_trades)
            self.total_quote_spent = total_quote
            self.total_base_acquired = total_base
            self.average_buy_price = total_quote / total_base if total_base > 0 else 0.0


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)

    side = Column(String)  # buy, sell
    quote_amount = Column(Float)  # Amount of quote currency (BTC or USD)
    base_amount = Column(Float)  # Amount of base currency (ETH, ADA, etc.)
    price = Column(Float)  # Price (base/quote, e.g., ETH/BTC or ADA/USD)

    # Trade context
    trade_type = Column(String)  # initial, dca, sell
    order_id = Column(String, nullable=True)  # Coinbase order ID

    # MACD values at time of trade
    macd_value = Column(Float, nullable=True)
    macd_signal = Column(Float, nullable=True)
    macd_histogram = Column(Float, nullable=True)

    position = relationship("Position", back_populates="trades")


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    signal_type = Column(String)  # macd_cross_up, macd_cross_down
    macd_value = Column(Float)
    macd_signal = Column(Float)
    macd_histogram = Column(Float)
    price = Column(Float)

    action_taken = Column(String, nullable=True)  # buy, sell, hold, none
    reason = Column(Text, nullable=True)  # Why action was or wasn't taken

    position = relationship("Position", back_populates="signals")


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(String)
    value_type = Column(String)  # float, int, string, bool
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    price = Column(Float)

    # MACD indicators
    macd_value = Column(Float, nullable=True)
    macd_signal = Column(Float, nullable=True)
    macd_histogram = Column(Float, nullable=True)

    # For potential future use
    volume = Column(Float, nullable=True)


class AIBotLog(Base):
    __tablename__ = "ai_bot_logs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True, index=True)  # Link to position
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

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


class PendingOrder(Base):
    """
    Pending limit orders that haven't been filled yet.
    Used by DCA strategies to track safety order limit orders.
    """
    __tablename__ = "pending_orders"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=False)

    # Order details
    order_id = Column(String, nullable=False, unique=True, index=True)  # Coinbase order ID
    product_id = Column(String, nullable=False)  # e.g., "ETH-BTC"
    side = Column(String, nullable=False)  # "BUY" or "SELL"
    order_type = Column(String, nullable=False)  # "LIMIT", "STOP_LOSS", etc.

    # Amounts
    limit_price = Column(Float, nullable=False)  # Target price for limit order
    quote_amount = Column(Float, nullable=False)  # Amount of quote currency (BTC/USD)
    base_amount = Column(Float, nullable=True)  # Amount of base currency (ETH, etc.) - may be null until filled

    # Order purpose
    trade_type = Column(String, nullable=False)  # "safety_order_1", "safety_order_2", etc.

    # Status tracking
    status = Column(String, nullable=False, default="pending")  # "pending", "filled", "canceled", "expired"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    filled_at = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)

    # Filled details (populated when order fills)
    filled_price = Column(Float, nullable=True)  # Actual fill price
    filled_quote_amount = Column(Float, nullable=True)  # Actual quote spent
    filled_base_amount = Column(Float, nullable=True)  # Actual base acquired

    # Relationships
    position = relationship("Position", back_populates="pending_orders")
    bot = relationship("Bot", back_populates="pending_orders")


class OrderHistory(Base):
    """
    Tracks all order attempts (successful and failed) for audit trail and debugging.
    Similar to 3Commas order history.
    """
    __tablename__ = "order_history"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Bot and position references
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)  # NULL for failed base orders

    # Order details
    product_id = Column(String, nullable=False)  # e.g., "ETH-BTC"
    side = Column(String, nullable=False)  # "BUY" or "SELL"
    order_type = Column(String, nullable=False)  # "MARKET", "LIMIT", etc.
    trade_type = Column(String, nullable=False)  # "initial", "dca", "safety_order_1", etc.

    # Amounts
    quote_amount = Column(Float, nullable=False)  # Amount attempted
    base_amount = Column(Float, nullable=True)  # Amount acquired (NULL for failed orders)
    price = Column(Float, nullable=True)  # Price at time of order

    # Status and result
    status = Column(String, nullable=False, index=True)  # "success", "failed", "canceled"
    order_id = Column(String, nullable=True)  # Coinbase order ID (NULL for failed orders)
    error_message = Column(Text, nullable=True)  # Error details if failed

    # Relationships
    bot = relationship("Bot")
    position = relationship("Position")
