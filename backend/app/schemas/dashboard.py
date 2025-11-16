"""Dashboard-related Pydantic schemas"""
from pydantic import BaseModel
from typing import Optional
from .position import PositionResponse


class DashboardStats(BaseModel):
    current_position: Optional[PositionResponse]
    total_positions: int
    total_profit_btc: float
    win_rate: float
    current_price: float
    btc_balance: float
    eth_balance: float
    monitor_running: bool
