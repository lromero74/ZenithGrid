"""Settings-related Pydantic schemas"""
from pydantic import BaseModel
from typing import Optional


class SettingsUpdate(BaseModel):
    coinbase_api_key: Optional[str] = None
    coinbase_api_secret: Optional[str] = None
    initial_btc_percentage: Optional[float] = None
    dca_percentage: Optional[float] = None
    max_btc_usage_percentage: Optional[float] = None
    min_profit_percentage: Optional[float] = None
    macd_fast_period: Optional[int] = None
    macd_slow_period: Optional[int] = None
    macd_signal_period: Optional[int] = None
    candle_interval: Optional[str] = None


class TestConnectionRequest(BaseModel):
    coinbase_api_key: str
    coinbase_api_secret: str
