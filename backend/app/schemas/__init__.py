"""Centralized Pydantic schemas for API requests/responses"""

from .position import PositionResponse, TradeResponse
from .market import SignalResponse, MarketDataResponse
from .settings import SettingsUpdate, TestConnectionRequest
from .dashboard import DashboardStats

__all__ = [
    # Position schemas
    "PositionResponse",
    "TradeResponse",
    # Market schemas
    "SignalResponse",
    "MarketDataResponse",
    # Settings schemas
    "SettingsUpdate",
    "TestConnectionRequest",
    # Dashboard schemas
    "DashboardStats",
]
