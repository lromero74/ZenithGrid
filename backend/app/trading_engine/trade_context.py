"""
Trade context dataclass — bundles the common parameters threaded through
signal processing and order execution functions.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.exchange_clients.base import ExchangeClient
from app.models import Bot
from app.strategies import TradingStrategy
from app.trading_client import TradingClient


@dataclass
class TradeContext:
    """Common parameters for trading engine operations."""
    db: AsyncSession
    exchange: ExchangeClient
    trading_client: TradingClient
    bot: Bot
    product_id: str
    current_price: float
    strategy: Optional[TradingStrategy] = None
