"""Position-related Pydantic schemas"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PositionResponse(BaseModel):
    id: int
    bot_id: Optional[int] = None
    account_id: Optional[int] = None  # For multi-account support
    product_id: str = "ETH-BTC"
    status: str
    opened_at: datetime
    closed_at: Optional[datetime]
    strategy_config_snapshot: Optional[dict] = None  # Frozen config from bot at position creation
    initial_quote_balance: float  # BTC or USD
    max_quote_allowed: float  # BTC or USD
    total_quote_spent: float  # BTC or USD
    total_base_acquired: float  # ETH, ADA, etc.
    average_buy_price: float
    sell_price: Optional[float]
    total_quote_received: Optional[float]  # BTC or USD
    profit_quote: Optional[float]  # BTC or USD
    profit_percentage: Optional[float]
    btc_usd_price_at_open: Optional[float]
    btc_usd_price_at_close: Optional[float]
    profit_usd: Optional[float]
    trade_count: int = 0
    pending_orders_count: int = 0  # Count of unfilled limit orders
    first_buy_price: Optional[float] = None  # Price of first (base order) buy trade
    last_buy_price: Optional[float] = None  # Price of most recent buy trade
    last_error_message: Optional[str] = None  # Last error message (like 3Commas)
    last_error_timestamp: Optional[datetime] = None  # When error occurred
    notes: Optional[str] = None  # User notes (like 3Commas)
    closing_via_limit: bool = False  # Whether position is closing via limit order
    limit_close_order_id: Optional[str] = None  # Coinbase order ID for limit close
    limit_order_details: Optional["LimitOrderDetails"] = None  # Details of limit close order
    is_blacklisted: bool = False  # Whether the coin is in the blacklist
    blacklist_reason: Optional[str] = None  # Reason the coin is blacklisted (if applicable)

    class Config:
        from_attributes = True


class LimitOrderFill(BaseModel):
    price: float
    base_amount: float
    quote_amount: float
    timestamp: datetime


class LimitOrderDetails(BaseModel):
    limit_price: float
    remaining_amount: float
    filled_amount: float
    fill_percentage: float
    fills: List[LimitOrderFill]
    status: str  # "pending", "partially_filled", "filled", "canceled"


class TradeResponse(BaseModel):
    id: int
    position_id: int
    timestamp: datetime
    side: str
    quote_amount: float  # BTC or USD
    base_amount: float  # ETH, ADA, etc.
    price: float
    trade_type: str
    order_id: Optional[str]

    class Config:
        from_attributes = True


class AIBotLogResponse(BaseModel):
    id: int
    bot_id: int
    position_id: Optional[int]
    timestamp: datetime
    thinking: str
    decision: str
    confidence: Optional[float]
    current_price: Optional[float]
    position_status: Optional[str]
    product_id: Optional[str]
    context: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True


class UpdatePositionSettingsRequest(BaseModel):
    """
    Request model for updating position settings (like 3Commas deal editing).

    Only certain fields are safe to modify on an open position:
    - take_profit_percentage: Target profit % from average buy price
    - max_safety_orders: Maximum number of safety orders allowed
    - trailing_take_profit: Enable/disable trailing take profit
    - trailing_tp_deviation: Trailing TP deviation percentage
    - stop_loss_enabled: Enable/disable stop loss
    - stop_loss_percentage: Stop loss percentage
    """
    take_profit_percentage: Optional[float] = None
    max_safety_orders: Optional[int] = None
    trailing_take_profit: Optional[bool] = None
    trailing_tp_deviation: Optional[float] = None
    stop_loss_enabled: Optional[bool] = None
    stop_loss_percentage: Optional[float] = None
