"""Market data and signal-related Pydantic schemas"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SignalResponse(BaseModel):
    id: int
    timestamp: datetime
    signal_type: str
    macd_value: float
    macd_signal: float
    macd_histogram: float
    price: float
    action_taken: Optional[str]
    reason: Optional[str]

    class Config:
        from_attributes = True


class MarketDataResponse(BaseModel):
    id: int
    timestamp: datetime
    price: float
    macd_value: Optional[float]
    macd_signal: Optional[float]
    macd_histogram: Optional[float]

    class Config:
        from_attributes = True
