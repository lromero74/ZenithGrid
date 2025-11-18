"""Position-related Pydantic schemas"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PositionResponse(BaseModel):
    id: int
    bot_id: Optional[int] = None
    product_id: str = "ETH-BTC"
    status: str
    opened_at: datetime
    closed_at: Optional[datetime]
    strategy_config_snapshot: Optional[dict] = None  # Frozen config from bot at position creation
    initial_quote_balance: float  # BTC or USD
    max_quote_allowed: float      # BTC or USD
    total_quote_spent: float      # BTC or USD
    total_base_acquired: float    # ETH, ADA, etc.
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
    last_error_message: Optional[str] = None  # Last error message (like 3Commas)
    last_error_timestamp: Optional[datetime] = None  # When error occurred
    notes: Optional[str] = None  # User notes (like 3Commas)

    class Config:
        from_attributes = True


class TradeResponse(BaseModel):
    id: int
    position_id: int
    timestamp: datetime
    side: str
    quote_amount: float  # BTC or USD
    base_amount: float   # ETH, ADA, etc.
    price: float
    trade_type: str
    order_id: Optional[str]

    class Config:
        from_attributes = True
