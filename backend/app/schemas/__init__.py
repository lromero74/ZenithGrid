"""Centralized Pydantic schemas for API requests/responses"""

from .dashboard import DashboardStats
from .market import MarketDataResponse, SignalResponse
from .position import AIBotLogResponse, PositionResponse, TradeResponse
from .settings import SettingsUpdate, TestConnectionRequest

__all__ = [
    # Position schemas
    "PositionResponse",
    "TradeResponse",
    "AIBotLogResponse",
    # Market schemas
    "SignalResponse",
    "MarketDataResponse",
    # Settings schemas
    "SettingsUpdate",
    "TestConnectionRequest",
    # Dashboard schemas
    "DashboardStats",
]
