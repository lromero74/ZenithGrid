"""
Bot Router Pydantic Schemas

Shared request/response models for all bot router modules.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class BotCreate(BaseModel):
    name: str
    description: Optional[str] = None
    account_id: Optional[int] = None  # Link bot to an account
    strategy_type: str
    strategy_config: dict
    product_id: str = "ETH-BTC"  # Legacy - kept for backward compatibility
    product_ids: Optional[List[str]] = None  # Multi-pair support
    split_budget_across_pairs: bool = False  # Budget splitting toggle
    reserved_btc_balance: float = 0.0  # BTC allocated to this bot (legacy)
    reserved_usd_balance: float = 0.0  # USD allocated to this bot (legacy)
    budget_percentage: float = 0.0  # % of aggregate portfolio value (preferred)


class BotUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    account_id: Optional[int] = None
    strategy_config: Optional[dict] = None
    product_id: Optional[str] = None
    product_ids: Optional[List[str]] = None
    split_budget_across_pairs: Optional[bool] = None
    reserved_btc_balance: Optional[float] = None
    reserved_usd_balance: Optional[float] = None
    budget_percentage: Optional[float] = None


class BotResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    strategy_type: str
    strategy_config: dict
    product_id: Optional[str] = None  # Optional for multi-pair strategies like bull_flag
    product_ids: Optional[List[str]] = None
    split_budget_across_pairs: bool = False
    reserved_btc_balance: float = 0.0
    reserved_usd_balance: float = 0.0
    budget_percentage: float = 0.0
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_signal_check: Optional[datetime]
    open_positions_count: int = 0
    total_positions_count: int = 0
    closed_positions_count: int = 0
    trades_per_day: float = 0.0
    total_pnl_usd: float = 0.0
    total_pnl_btc: float = 0.0
    total_pnl_percentage: float = 0.0
    avg_daily_pnl_usd: float = 0.0
    avg_daily_pnl_btc: float = 0.0
    insufficient_funds: bool = False
    budget_utilization_percentage: float = 0.0
    win_rate: float = 0.0  # Percentage of profitable closed positions
    account_id: Optional[int] = None  # For multi-account support
    exchange_type: Optional[str] = None  # 'cex' or 'dex'

    class Config:
        from_attributes = True


class BotStats(BaseModel):
    total_positions: int
    open_positions: int
    closed_positions: int
    max_concurrent_deals: int  # Max deals allowed simultaneously
    total_profit_btc: float  # Legacy field name
    total_profit_quote: float  # Profit in quote currency (BTC for BTC pairs, USD for USD pairs)
    win_rate: float
    insufficient_funds: bool
    budget_utilization_percentage: float = 0.0  # % of allocated budget in open positions


class AIBotLogCreate(BaseModel):
    thinking: str
    decision: str
    confidence: Optional[float] = None
    current_price: Optional[float] = None
    position_status: Optional[str] = None
    context: Optional[dict] = None


class AIBotLogResponse(BaseModel):
    id: int
    bot_id: int
    timestamp: datetime
    thinking: str
    decision: str
    confidence: Optional[float]
    current_price: Optional[float]
    position_status: Optional[str]
    product_id: Optional[str]
    context: Optional[dict]

    class Config:
        from_attributes = True


class ScannerLogCreate(BaseModel):
    product_id: str
    scan_type: str  # "volume_check", "pattern_check", "entry_signal", "exit_signal"
    decision: str  # "passed", "rejected", "triggered", "hold"
    reason: str
    current_price: Optional[float] = None
    volume_ratio: Optional[float] = None
    pattern_data: Optional[dict] = None


class ScannerLogResponse(BaseModel):
    id: int
    bot_id: int
    timestamp: datetime
    product_id: str
    scan_type: str
    decision: str
    reason: str
    current_price: Optional[float]
    volume_ratio: Optional[float]
    pattern_data: Optional[dict]

    class Config:
        from_attributes = True


class IndicatorLogResponse(BaseModel):
    """Response schema for indicator condition evaluation logs."""
    id: int
    bot_id: int
    timestamp: datetime
    product_id: str
    phase: str  # "base_order", "safety_order", "take_profit"
    conditions_met: bool
    conditions_detail: List[dict]
    indicators_snapshot: Optional[dict]
    current_price: Optional[float]

    class Config:
        from_attributes = True


class ValidateBotConfigRequest(BaseModel):
    product_ids: List[str]
    strategy_config: dict
    quote_balance: Optional[float] = None  # Will use actual balance if not provided


class ValidationWarning(BaseModel):
    product_id: str
    issue: str
    suggested_minimum_pct: float
    current_pct: float


class ValidateBotConfigResponse(BaseModel):
    is_valid: bool
    warnings: List[ValidationWarning]
    message: str
