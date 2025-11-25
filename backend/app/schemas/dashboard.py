"""Dashboard-related Pydantic schemas"""

from typing import Optional

from pydantic import BaseModel

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
