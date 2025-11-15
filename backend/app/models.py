from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
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

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_signal_check = Column(DateTime, nullable=True)  # Last time signal was checked

    # Relationships
    positions = relationship("Position", back_populates="bot", cascade="all, delete-orphan")

    def get_trading_pairs(self):
        """Get list of trading pairs for this bot (backward compatible)"""
        if self.product_ids and len(self.product_ids) > 0:
            return self.product_ids
        elif self.product_id:
            return [self.product_id]
        else:
            return ["ETH-BTC"]  # Default fallback


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

    # Initial balance tracking
    initial_btc_balance = Column(Float)
    max_btc_allowed = Column(Float)  # 25% of initial balance (configurable)

    # Position totals
    total_btc_spent = Column(Float, default=0.0)
    total_eth_acquired = Column(Float, default=0.0)
    average_buy_price = Column(Float, default=0.0)

    # Closing metrics
    sell_price = Column(Float, nullable=True)
    total_btc_received = Column(Float, nullable=True)
    profit_btc = Column(Float, nullable=True)
    profit_percentage = Column(Float, nullable=True)

    # USD tracking
    btc_usd_price_at_open = Column(Float, nullable=True)  # BTC/USD price when position opened
    btc_usd_price_at_close = Column(Float, nullable=True)  # BTC/USD price when position closed
    profit_usd = Column(Float, nullable=True)  # Profit in USD

    # Relationships
    bot = relationship("Bot", back_populates="positions")
    trades = relationship("Trade", back_populates="position", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="position", cascade="all, delete-orphan")

    def update_averages(self):
        """Recalculate average buy price and totals from trades"""
        buy_trades = [t for t in self.trades if t.side == "buy"]
        if buy_trades:
            total_btc = sum(t.btc_amount for t in buy_trades)
            total_eth = sum(t.eth_amount for t in buy_trades)
            self.total_btc_spent = total_btc
            self.total_eth_acquired = total_eth
            self.average_buy_price = total_btc / total_eth if total_eth > 0 else 0.0


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)

    side = Column(String)  # buy, sell
    btc_amount = Column(Float)
    eth_amount = Column(Float)
    price = Column(Float)  # ETH/BTC price

    # Trade context
    trade_type = Column(String)  # initial, dca, sell
    order_id = Column(String, nullable=True)  # 3Commas order ID

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
