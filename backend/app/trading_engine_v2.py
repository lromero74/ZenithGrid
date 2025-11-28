"""
Strategy-Based Trading Engine (Refactored)

Wrapper class that coordinates all trading engine modules.
Maintains backward compatibility with existing code.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.currency_utils import get_quote_currency
from app.exchange_clients.base import ExchangeClient
from app.models import Bot, PendingOrder, Position, Trade
from app.strategies import TradingStrategy
from app.trading_client import TradingClient

# Import extracted modules
from app.trading_engine import position_manager
from app.trading_engine import order_logger
from app.trading_engine import buy_executor
from app.trading_engine import sell_executor
from app.trading_engine import signal_processor

logger = logging.getLogger(__name__)


class StrategyTradingEngine:
    """
    Strategy-agnostic trading engine - wrapper for modular functions

    Works with any TradingStrategy implementation to execute trades.
    This class maintains the original public API for backward compatibility,
    but delegates all work to focused modules.
    """

    def __init__(
        self,
        db: AsyncSession,
        exchange: ExchangeClient,
        bot: Bot,
        strategy: TradingStrategy,
        product_id: Optional[str] = None,
    ):
        """
        Initialize engine for a specific bot with its strategy

        Args:
            db: Database session
            exchange: Exchange client instance (CEX or DEX)
            bot: Bot instance to trade for
            strategy: Strategy instance with bot's configuration
            product_id: Trading pair to use (defaults to bot's first pair for backward compatibility)
        """
        self.db = db
        self.exchange = exchange
        self.trading_client = TradingClient(exchange)  # Currency-agnostic wrapper
        self.bot = bot
        self.strategy = strategy
        # Use provided product_id, or fallback to bot's first pair
        self.product_id = product_id or (
            bot.get_trading_pairs()[0] if hasattr(bot, "get_trading_pairs") else bot.product_id
        )
        self.quote_currency = get_quote_currency(self.product_id)

    async def save_ai_log(
        self, signal_data: Dict[str, Any], decision: str, current_price: float, position: Optional[Position]
    ):
        """Delegate to order_logger module"""
        await order_logger.save_ai_log(
            self.db, self.bot, self.product_id, signal_data, decision, current_price, position
        )

    async def get_active_position(self) -> Optional[Position]:
        """Delegate to position_manager module"""
        return await position_manager.get_active_position(self.db, self.bot, self.product_id)

    async def get_open_positions_count(self) -> int:
        """Delegate to position_manager module"""
        return await position_manager.get_open_positions_count(self.db, self.bot)

    async def create_position(self, quote_balance: float, quote_amount: float) -> Position:
        """Delegate to position_manager module"""
        return await position_manager.create_position(
            self.db, self.exchange, self.bot, self.product_id, quote_balance, quote_amount
        )

    async def log_order_to_history(
        self,
        position: Optional[Position],
        side: str,
        order_type: str,
        trade_type: str,
        quote_amount: float,
        price: float,
        status: str,
        **kwargs
    ):
        """Delegate to order_logger module"""
        await order_logger.log_order_to_history(
            self.db,
            self.bot,
            self.product_id,
            position,
            side,
            order_type,
            trade_type,
            quote_amount,
            price,
            status,
            **kwargs
        )

    async def execute_buy(
        self,
        position: Position,
        quote_amount: float,
        current_price: float,
        trade_type: str,
        signal_data: Optional[Dict[str, Any]] = None,
        commit_on_error: bool = True,
    ) -> Optional[Trade]:
        """Delegate to buy_executor module"""
        return await buy_executor.execute_buy(
            self.db,
            self.exchange,
            self.trading_client,
            self.bot,
            self.product_id,
            position,
            quote_amount,
            current_price,
            trade_type,
            signal_data,
            commit_on_error,
        )

    async def execute_limit_buy(
        self,
        position: Position,
        quote_amount: float,
        limit_price: float,
        trade_type: str,
        signal_data: Optional[Dict[str, Any]] = None,
    ) -> PendingOrder:
        """Delegate to buy_executor module"""
        return await buy_executor.execute_limit_buy(
            self.db,
            self.exchange,
            self.trading_client,
            self.bot,
            self.product_id,
            position,
            quote_amount,
            limit_price,
            trade_type,
            signal_data,
        )

    async def execute_sell(
        self, position: Position, current_price: float, signal_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[Trade], float, float]:
        """Delegate to sell_executor module"""
        return await sell_executor.execute_sell(
            self.db, self.exchange, self.trading_client, self.bot, self.product_id, position, current_price, signal_data
        )

    async def execute_limit_sell(
        self, position: Position, base_amount: float, limit_price: float, signal_data: Optional[Dict[str, Any]] = None
    ) -> PendingOrder:
        """Delegate to sell_executor module"""
        return await sell_executor.execute_limit_sell(
            self.db,
            self.exchange,
            self.trading_client,
            self.bot,
            self.product_id,
            position,
            base_amount,
            limit_price,
            signal_data,
        )

    async def process_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        pre_analyzed_signal: Optional[Dict[str, Any]] = None,
        candles_by_timeframe: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """Delegate to signal_processor module"""
        return await signal_processor.process_signal(
            self.db,
            self.exchange,
            self.trading_client,
            self.bot,
            self.strategy,
            self.product_id,
            candles,
            current_price,
            pre_analyzed_signal,
            candles_by_timeframe,
        )
