"""
Database Models

Defines SQLAlchemy ORM models for the trading bot application:
- Account: CEX and DEX account configurations
- Bot: Trading bot configuration and state
- Position: Active and historical trading positions
- Trade: Individual buy/sell trades within positions
- OrderHistory: Order execution history
- MarketData: Historical candlestick data
- Template: Reusable bot configuration templates
- BotAILog: AI strategy decision logs
"""

from datetime import datetime
from typing import Optional

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
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """
    User model for authentication and multi-tenancy.

    Each user has their own:
    - Exchange accounts (CEX/DEX)
    - Bots and trading configurations
    - Positions and trade history
    - Templates and blacklisted coins
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)  # Admin privileges

    # Profile info
    display_name = Column(String, nullable=True)  # Optional display name

    # UI preferences
    last_seen_history_count = Column(Integer, default=0)  # For "new items" badge in History tab (closed positions)
    last_seen_failed_count = Column(Integer, default=0)  # For "new items" badge in Failed tab

    # Terms and conditions acceptance
    terms_accepted_at = Column(DateTime, nullable=True)  # NULL = not accepted, timestamp = when accepted

    # MFA (Two-Factor Authentication)
    totp_secret = Column(String, nullable=True)  # Fernet-encrypted TOTP secret key
    mfa_enabled = Column(Boolean, default=False)  # Whether MFA is active

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    # Relationships
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    bots = relationship("Bot", back_populates="user", cascade="all, delete-orphan")
    bot_templates = relationship("BotTemplate", back_populates="user", cascade="all, delete-orphan")
    blacklisted_coins = relationship("BlacklistedCoin", back_populates="user", cascade="all, delete-orphan")
    ai_provider_credentials = relationship("AIProviderCredential", back_populates="user", cascade="all, delete-orphan")
    source_subscriptions = relationship("UserSourceSubscription", back_populates="user", cascade="all, delete-orphan")
    trusted_devices = relationship("TrustedDevice", back_populates="user", cascade="all, delete-orphan")


class TrustedDevice(Base):
    """
    Trusted device for MFA bypass (30-day remember device).

    When a user checks "Remember this device", a record is created here.
    The device_id is embedded in a JWT token stored on the client.
    Users can view and revoke trusted devices from Settings.
    """
    __tablename__ = "trusted_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    device_id = Column(String, unique=True, nullable=False, index=True)  # UUID in the JWT
    device_name = Column(String, nullable=True)  # Parsed from User-Agent
    ip_address = Column(String, nullable=True)
    location = Column(String, nullable=True)  # City, State, Country from IP geolocation
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    # Relationships
    user = relationship("User", back_populates="trusted_devices")


class Account(Base):
    """
    Account model for managing CEX and DEX connections.

    Supports:
    - CEX accounts (Coinbase) with API credentials
    - DEX wallets (MetaMask, WalletConnect) with wallet addresses

    Each bot is linked to an account, enabling multi-account trading
    and account-based UI filtering.
    """
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # Owner (nullable for migration)
    name = Column(String, nullable=False)  # User-friendly account name
    type = Column(String, nullable=False)  # "cex" or "dex"
    is_default = Column(Boolean, default=False)  # Default account for UI
    is_active = Column(Boolean, default=True)  # Can be disabled without deletion

    # CEX-specific fields (e.g., Coinbase)
    exchange = Column(String, nullable=True)  # "coinbase"
    api_key_name = Column(String, nullable=True)  # API key name/ID
    api_private_key = Column(String, nullable=True)  # Encrypted API secret

    # DEX-specific fields
    chain_id = Column(Integer, nullable=True)  # 1=Ethereum, 56=BSC, 137=Polygon, 42161=Arbitrum
    wallet_address = Column(String, nullable=True)  # Public wallet address
    wallet_private_key = Column(String, nullable=True)  # Encrypted private key (optional)
    rpc_url = Column(String, nullable=True)  # RPC endpoint URL
    wallet_type = Column(String, nullable=True)  # "metamask", "walletconnect", "private_key"

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    # Auto-buy BTC settings
    auto_buy_enabled = Column(Boolean, default=False)  # Master toggle
    auto_buy_check_interval_minutes = Column(Integer, default=5)  # Shared check interval
    auto_buy_order_type = Column(String, default="market")  # "market" or "limit"

    # Per-stablecoin auto-buy settings
    auto_buy_usd_enabled = Column(Boolean, default=False)
    auto_buy_usd_min = Column(Float, default=10.0)

    auto_buy_usdc_enabled = Column(Boolean, default=False)
    auto_buy_usdc_min = Column(Float, default=10.0)

    auto_buy_usdt_enabled = Column(Boolean, default=False)
    auto_buy_usdt_min = Column(Float, default=10.0)

    # Paper Trading
    is_paper_trading = Column(Boolean, default=False)  # True for simulated trading accounts
    paper_balances = Column(String, nullable=True)  # JSON: {"BTC": 1.0, "ETH": 10.0, "USD": 100000.0, ...}

    # Perpetual futures (INTX) configuration
    perps_portfolio_uuid = Column(String, nullable=True)  # INTX perpetuals portfolio UUID
    default_leverage = Column(Integer, default=1)  # Default leverage for new perps positions (1-10)
    margin_type = Column(String, default="CROSS")  # "CROSS" or "ISOLATED"

    # Prop firm fields (nullable — non-prop accounts leave these NULL)
    prop_firm = Column(String, nullable=True)  # "hyrotrader" | "ftmo" | None
    prop_firm_config = Column(JSON, nullable=True)  # Firm-specific JSON blob
    prop_daily_drawdown_pct = Column(Float, nullable=True)  # e.g. 4.5
    prop_total_drawdown_pct = Column(Float, nullable=True)  # e.g. 9.0
    prop_initial_deposit = Column(Float, nullable=True)  # e.g. 100000.0 USD

    # Relationships
    user = relationship("User", back_populates="accounts")
    bots = relationship("Bot", back_populates="account")

    def get_display_name(self) -> str:
        """Get display name with type indicator"""
        type_label = "CEX" if self.type == "cex" else "DEX"
        return f"{self.name} ({type_label})"

    def get_short_address(self) -> str:
        """Get shortened wallet address for DEX accounts"""
        if self.wallet_address and len(self.wallet_address) > 10:
            return f"{self.wallet_address[:6]}...{self.wallet_address[-4:]}"
        return self.wallet_address or ""


class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # Owner (nullable for migration)
    name = Column(String, unique=True, index=True)  # User-defined bot name
    description = Column(Text, nullable=True)  # Optional description

    # Account reference (links bot to CEX or DEX account)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)  # Nullable for backwards compatibility

    # Exchange configuration (CEX or DEX)
    exchange_type = Column(String, default="cex", nullable=False)  # "cex" or "dex"
    chain_id = Column(Integer, nullable=True)  # Blockchain chain ID (1=Ethereum, 56=BSC, 137=Polygon, 42161=Arbitrum)
    dex_router = Column(String, nullable=True)  # DEX router address (Uniswap, PancakeSwap, SushiSwap)
    wallet_private_key = Column(String, nullable=True)  # Encrypted wallet private key for DEX trading (sensitive!)
    rpc_url = Column(String, nullable=True)  # RPC endpoint URL for blockchain connection
    wallet_address = Column(String, nullable=True)  # Derived wallet address (computed from private key)

    # Market type (spot or perpetual futures)
    market_type = Column(String, default="spot")  # "spot" or "perps"

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

    # Bidirectional DCA Grid Bot - Budget Reservations
    # These track RESERVED amounts for bidirectional bots (even with 0 open positions)
    # DCA bots wait for signals, so capital must be reserved upfront
    reserved_usd_for_longs = Column(Float, default=0.0)  # USD reserved for long positions
    reserved_btc_for_shorts = Column(Float, default=0.0)  # BTC reserved for short positions

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Last time signal was checked (technical conditions + positions)
    last_signal_check = Column(DateTime, nullable=True)
    # Last time AI analysis was performed (expensive operation)
    last_ai_check = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="bots")
    account = relationship("Account", back_populates="bots")
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
            if "-" in first_pair:
                return first_pair.split("-")[1]
        return "BTC"  # Default

    def get_reserved_balance(self, aggregate_value: Optional[float] = None):
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

    def get_total_reserved_usd(self, current_btc_price: float = None) -> float:
        """
        Get total USD reserved by this bot (for bidirectional bots).

        Includes:
        - Initial USD reserved for longs
        - USD value of BTC acquired from long positions (needs to be sold later)
        - USD received from short positions (needs to buy back BTC)

        Args:
            current_btc_price: Current BTC/USD price for valuation

        Returns:
            Total USD that should be considered "locked" by this bot
        """
        total_usd = self.reserved_usd_for_longs or 0.0

        # Add USD from short positions (sold BTC, got USD, need to buy back)
        for position in self.positions:
            if position.status == "open" and position.direction == "short":
                # Short position: we received USD, it's locked until we buy back BTC
                total_usd += position.short_total_sold_quote or 0.0

        # Add USD value of BTC in long positions (bought BTC, need to sell it)
        if current_btc_price:
            for position in self.positions:
                if position.status == "open" and position.direction == "long":
                    # Long position: BTC we own, valued in USD
                    btc_amount = position.total_base_acquired or 0.0
                    total_usd += btc_amount * current_btc_price

        return total_usd

    def get_total_reserved_btc(self, current_btc_price: float = None) -> float:
        """
        Get total BTC reserved by this bot (for bidirectional bots).

        Includes:
        - Initial BTC reserved for shorts
        - BTC acquired from long positions (bought BTC, need to sell it)
        - BTC value of USD from short positions (got USD, need to buy back BTC)

        Args:
            current_btc_price: Current BTC/USD price for valuation

        Returns:
            Total BTC that should be considered "locked" by this bot
        """
        total_btc = self.reserved_btc_for_shorts or 0.0

        # Add BTC from long positions (bought BTC, need to sell it)
        for position in self.positions:
            if position.status == "open" and position.direction == "long":
                total_btc += position.total_base_acquired or 0.0

        # Add BTC value of USD from short positions
        if current_btc_price and current_btc_price > 0:
            for position in self.positions:
                if position.status == "open" and position.direction == "short":
                    # Short: we have USD, need to convert to BTC equivalent
                    usd_amount = position.short_total_sold_quote or 0.0
                    total_btc += usd_amount / current_btc_price

        return total_btc


class BotTemplate(Base):
    __tablename__ = "bot_templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # Owner (nullable for system presets)
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

    # Relationships
    user = relationship("User", back_populates="bot_templates")


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    # Link to bot (nullable for backwards compatibility)
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=True)
    # Link to account (for filtering)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    # Owner (for user-specific deal numbers)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # Sequential attempt number (ALL positions: success + failed)
    user_attempt_number = Column(Integer, nullable=True, index=True)
    # User-specific deal number (SUCCESSFUL deals only, like 3Commas)
    user_deal_number = Column(Integer, nullable=True, index=True)
    product_id = Column(String, default="ETH-BTC")  # Trading pair (e.g., "ETH-BTC", "SOL-USD")
    status = Column(String, default="open")  # open, closed
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    # Bidirectional DCA Grid Bot - Direction Tracking
    # Indicates whether position is long (buying) or short (selling)
    direction = Column(String, default="long")  # "long" or "short"

    # Exchange configuration (frozen at position creation)
    exchange_type = Column(String, default="cex", nullable=False)  # "cex" or "dex"
    chain_id = Column(Integer, nullable=True)  # Blockchain chain ID (for DEX positions)
    dex_router = Column(String, nullable=True)  # DEX router address (for DEX positions)
    wallet_address = Column(String, nullable=True)  # Wallet address used (for DEX positions)

    # Strategy config snapshot (frozen at position creation - like 3Commas)
    strategy_config_snapshot = Column(JSON, nullable=True)  # Bot's strategy_config at time of position creation

    # Initial balance tracking (quote currency = BTC for BTC pairs, USD for USD pairs)
    initial_quote_balance = Column(Float)
    max_quote_allowed = Column(Float)  # 25% of initial balance (configurable)

    # Position totals (LONG positions)
    total_quote_spent = Column(Float, default=0.0)  # Amount of quote currency spent (BTC or USD)
    total_base_acquired = Column(Float, default=0.0)  # Amount of base currency acquired (ETH, ADA, etc.)
    average_buy_price = Column(Float, default=0.0)  # Average price paid (quote/base)

    # Bidirectional DCA Grid Bot - Short Position Tracking
    # For short positions: we SELL base currency (e.g., BTC) to get quote currency (e.g., USD)
    # Then we buy back later at lower price to profit
    entry_price = Column(Float, nullable=True)  # Initial entry price (used for both long and short)
    short_entry_price = Column(Float, nullable=True)  # Price at first short (for short positions)
    short_average_sell_price = Column(Float, nullable=True)  # Average price of all short sells
    short_total_sold_quote = Column(Float, nullable=True)  # Total USD received from selling BTC
    short_total_sold_base = Column(Float, nullable=True)  # Total BTC sold

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

    # Limit close tracking
    closing_via_limit = Column(Boolean, default=False)  # Whether position is closing via limit order
    limit_close_order_id = Column(String, nullable=True)  # Coinbase order ID for limit close order

    # Bull Flag Strategy - Trailing Stop Loss tracking
    trailing_stop_loss_price = Column(Float, nullable=True)  # Current trailing stop loss price
    trailing_stop_loss_active = Column(Boolean, default=False)  # Whether TSL is active (disabled when TTP activates)

    # Bull Flag Strategy - Entry-time targets (set at position open)
    entry_stop_loss = Column(Float, nullable=True)  # Initial stop loss (pullback low)
    entry_take_profit_target = Column(Float, nullable=True)  # TTP activation target (2x risk)

    # Bull Flag Strategy - Pattern data (JSON)
    pattern_data = Column(Text, nullable=True)  # JSON: pole_high, pole_low, pullback_low, etc.

    # Exit reason tracking
    exit_reason = Column(String, nullable=True)  # "trailing_stop_loss", "trailing_take_profit", "manual", etc.

    # Perpetual futures fields
    product_type = Column(String, default="spot")  # "spot" or "future"
    leverage = Column(Integer, nullable=True)  # Leverage used (1-10x)
    perps_margin_type = Column(String, nullable=True)  # "CROSS" or "ISOLATED"
    liquidation_price = Column(Float, nullable=True)
    funding_fees_total = Column(Float, default=0.0)  # Accumulated funding fees (USDC)
    tp_order_id = Column(String, nullable=True)  # Take profit bracket order ID
    sl_order_id = Column(String, nullable=True)  # Stop loss bracket order ID
    tp_price = Column(Float, nullable=True)  # Take profit trigger price
    sl_price = Column(Float, nullable=True)  # Stop loss trigger price
    unrealized_pnl = Column(Float, nullable=True)  # Latest unrealized PnL from exchange

    # Crossing detection - store previous indicators for crossing_above/crossing_below operators
    previous_indicators = Column(JSON, nullable=True)  # JSON: Previous check's indicator values

    # Relationships
    bot = relationship("Bot", back_populates="positions")
    trades = relationship("Trade", back_populates="position", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="position", cascade="all, delete-orphan")
    pending_orders = relationship("PendingOrder", back_populates="position", cascade="all, delete-orphan")

    def get_quote_currency(self) -> str:
        """Get the quote currency from product_id (e.g., 'BTC' from 'ETH-BTC', 'USD' from 'ADA-USD')"""
        if self.product_id and "-" in self.product_id:
            return self.product_id.split("-")[1]
        return "BTC"  # Default fallback

    def get_base_currency(self) -> str:
        """Get the base currency from product_id (e.g., 'ETH' from 'ETH-BTC', 'ADA' from 'ADA-USD')"""
        if self.product_id and "-" in self.product_id:
            return self.product_id.split("-")[0]
        return "ETH"  # Default fallback

    def update_averages(self):
        """Recalculate average buy/sell price and totals from trades (direction-aware)"""
        if self.direction == "long":
            # LONG: Track buy trades
            buy_trades = [t for t in self.trades if t.side == "buy"]
            if buy_trades:
                total_quote = sum(t.quote_amount for t in buy_trades)
                total_base = sum(t.base_amount for t in buy_trades)
                self.total_quote_spent = total_quote
                self.total_base_acquired = total_base
                self.average_buy_price = total_quote / total_base if total_base > 0 else 0.0
        else:
            # SHORT: Track sell trades
            sell_trades = [t for t in self.trades if t.side == "sell"]
            if sell_trades:
                total_quote = sum(t.quote_amount for t in sell_trades)  # USD received
                total_base = sum(t.base_amount for t in sell_trades)  # BTC sold
                self.short_total_sold_quote = total_quote
                self.short_total_sold_base = total_base
                self.short_average_sell_price = total_quote / total_base if total_base > 0 else 0.0

    def calculate_profit(self, current_price: float) -> dict:
        """
        Calculate P&L for both long and short positions.

        Args:
            current_price: Current market price

        Returns:
            Dict with profit_quote, profit_pct, unrealized_value
        """
        if self.direction == "long":
            # LONG: Profit when price goes UP
            # We bought BTC, current value is what we could sell it for now
            unrealized_value = self.total_base_acquired * current_price
            profit_quote = unrealized_value - self.total_quote_spent
            profit_pct = (profit_quote / self.total_quote_spent) * 100 if self.total_quote_spent > 0 else 0.0

        else:
            # SHORT: Profit when price goes DOWN
            # We sold BTC high, need to buy back low
            # Cost to cover = how much USD we'd need to buy back the BTC we sold
            cost_to_cover = (self.short_total_sold_base or 0.0) * current_price
            # Profit = USD we received from selling - USD needed to buy back
            profit_quote = (self.short_total_sold_quote or 0.0) - cost_to_cover
            profit_pct = (profit_quote / (self.short_total_sold_quote or 1.0)) * 100
            unrealized_value = cost_to_cover

        return {
            "profit_quote": profit_quote,
            "profit_pct": profit_pct,
            "unrealized_value": unrealized_value
        }


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


class ScannerLog(Base):
    """
    Scanner/Monitor logs for non-AI strategies like bull flag.
    Captures pattern detection decisions, volume checks, and reasoning.
    """
    __tablename__ = "scanner_logs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

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

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

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
    status = Column(
        String, nullable=False, default="pending"
    )  # "pending", "partially_filled", "filled", "canceled", "expired"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    filled_at = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)

    # Filled details (populated when order fills)
    filled_price = Column(Float, nullable=True)  # Actual fill price (average if multiple fills)
    filled_quote_amount = Column(Float, nullable=True)  # Actual quote spent (cumulative)
    filled_base_amount = Column(Float, nullable=True)  # Actual base acquired (cumulative)

    # Partial fill tracking
    fills = Column(JSON, nullable=True)  # Array of fill records: [{price, base_amount, quote_amount, timestamp}, ...]
    remaining_base_amount = Column(Float, nullable=True)  # Unfilled base amount for partial fills

    # Capital Reservation (for grid trading bots)
    # These fields track capital locked in pending orders (not yet filled)
    # Buy orders: reserved_amount_quote = size * limit_price (capital needed to fill)
    # Sell orders: reserved_amount_base = size (base currency needed)
    reserved_amount_quote = Column(Float, nullable=False, default=0.0)
    reserved_amount_base = Column(Float, nullable=False, default=0.0)

    # Time-in-force settings (for honoring GTC/GTD on manual orders)
    time_in_force = Column(String, nullable=False, default="gtc")  # "gtc" or "gtd"
    end_time = Column(DateTime, nullable=True)  # For GTD orders - when order expires
    is_manual = Column(Boolean, nullable=False, default=False)  # True for manual limit close, False for automated

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


class BlacklistedCoin(Base):
    """
    Blacklisted coins that bots should not open new positions for.
    Existing positions in blacklisted coins continue to work normally.
    """

    __tablename__ = "blacklisted_coins"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # Owner (nullable for migration)
    symbol = Column(String, index=True)  # e.g., "ICP", "EOS", "DOGE" - unique per user, not globally
    reason = Column(Text, nullable=True)  # Why the coin is blacklisted
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="blacklisted_coins")


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

    # Metadata
    fetched_at = Column(DateTime, default=datetime.utcnow, index=True)  # When we fetched it
    created_at = Column(DateTime, default=datetime.utcnow)


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
    created_at = Column(DateTime, default=datetime.utcnow)

    # Unique constraint
    __table_args__ = (UniqueConstraint("user_id", "source_id", name="uq_user_source"),)

    # Relationships
    user = relationship("User", back_populates="source_subscriptions")
    source = relationship("ContentSource", back_populates="subscriptions")


class AccountValueSnapshot(Base):
    """
    Daily snapshot of account value for historical tracking.

    Stores total account value in both BTC and USD for charting over time.
    Captured once daily by scheduled task.
    """
    __tablename__ = "account_value_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date = Column(DateTime, nullable=False, index=True)
    total_value_btc = Column(Float, nullable=False, default=0.0)
    total_value_usd = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Unique constraint: one snapshot per account per day
    __table_args__ = (UniqueConstraint("account_id", "snapshot_date", name="uq_account_snapshot_date"),)

    # Relationships
    account = relationship("Account")
    user = relationship("User")


class MetricSnapshot(Base):
    """
    Rolling history of market metric values for sparkline charts.

    Records a snapshot each time a metric is fetched (~every 15 min).
    Pruned to 90 days to keep the table small.
    """
    __tablename__ = "metric_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    metric_name = Column(String, nullable=False, index=True)
    value = Column(Float, nullable=False)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class PropFirmState(Base):
    """
    Tracks equity state for prop firm accounts across restarts.

    Persists kill switch status, daily/total drawdown tracking, and
    equity snapshots needed by PropGuard safety middleware.
    One row per prop firm account.
    """
    __tablename__ = "prop_firm_state"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )

    # Starting capital for total drawdown calculation
    initial_deposit = Column(Float, nullable=False, default=0.0)

    # Daily reset tracking (resets at 17:00 EST)
    daily_start_equity = Column(Float, nullable=True)
    daily_start_timestamp = Column(DateTime, nullable=True)

    # Current equity tracking
    current_equity = Column(Float, nullable=True)
    current_equity_timestamp = Column(DateTime, nullable=True)

    # Kill switch state
    is_killed = Column(Boolean, default=False)
    kill_reason = Column(String, nullable=True)
    kill_timestamp = Column(DateTime, nullable=True)

    # Running P&L totals
    daily_pnl = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    account = relationship("Account")


class PropFirmEquitySnapshot(Base):
    """
    Time-series equity snapshots for prop firm accounts.

    Recorded every monitor cycle (~30s) to allow charting
    equity trajectory and drawdown history over time.
    """
    __tablename__ = "prop_firm_equity_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    equity = Column(Float, nullable=False)
    daily_drawdown_pct = Column(Float, default=0.0)
    total_drawdown_pct = Column(Float, default=0.0)
    daily_pnl = Column(Float, default=0.0)
    is_killed = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
