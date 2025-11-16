"""
Strategy-Based Trading Engine

Refactored to support multiple strategies and bots.
Works with any TradingStrategy implementation.
"""

import logging
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Position, Trade, Signal, Bot, AIBotLog
from app.coinbase_client import CoinbaseClient
from app.strategies import TradingStrategy

logger = logging.getLogger(__name__)


def format_btc_with_usd(btc_amount: float, btc_usd_price: Optional[float] = None) -> str:
    """
    Format BTC amount with USD equivalent for better readability in logs

    Args:
        btc_amount: Amount in BTC
        btc_usd_price: Current BTC/USD price (if known)

    Returns:
        Formatted string like "0.00057000 BTC ($54.15 USD)" or "0.00057000 BTC" if price unknown
    """
    btc_str = f"{btc_amount:.8f} BTC"
    if btc_usd_price:
        usd_value = btc_amount * btc_usd_price
        return f"{btc_str} (${usd_value:.2f} USD)"
    return btc_str


class StrategyTradingEngine:
    """
    Strategy-agnostic trading engine.

    Works with any TradingStrategy implementation to execute trades.
    """

    def __init__(
        self,
        db: AsyncSession,
        coinbase: CoinbaseClient,
        bot: Bot,
        strategy: TradingStrategy,
        product_id: Optional[str] = None
    ):
        """
        Initialize engine for a specific bot with its strategy

        Args:
            db: Database session
            coinbase: Coinbase API client
            bot: Bot instance to trade for
            strategy: Strategy instance with bot's configuration
            product_id: Trading pair to use (defaults to bot's first pair for backward compatibility)
        """
        self.db = db
        self.coinbase = coinbase
        self.bot = bot
        self.strategy = strategy
        # Use provided product_id, or fallback to bot's first pair
        self.product_id = product_id or (bot.get_trading_pairs()[0] if hasattr(bot, 'get_trading_pairs') else bot.product_id)

    async def save_ai_log(
        self,
        signal_data: Dict[str, Any],
        decision: str,
        current_price: float,
        position: Optional[Position]
    ):
        """Save AI bot reasoning log if this is an AI autonomous bot"""
        # Only save logs for AI autonomous strategy
        if self.bot.strategy_type != "ai_autonomous":
            return

        # Extract AI thinking/reasoning from signal_data
        thinking = signal_data.get("reasoning", "No reasoning provided")
        confidence = signal_data.get("confidence", None)

        # Determine position status
        position_status = "none"
        if position:
            position_status = position.status

        # Save log (don't commit - let caller handle transaction)
        ai_log = AIBotLog(
            bot_id=self.bot.id,
            thinking=thinking,
            decision=decision,
            confidence=confidence,
            current_price=current_price,
            position_status=position_status,
            product_id=self.product_id,  # Track which pair this analysis is for
            context=signal_data,  # Store full signal data for reference
            timestamp=datetime.utcnow()
        )

        self.db.add(ai_log)
        # Don't commit here - let the main process_signal flow commit everything together

    async def get_active_position(self) -> Optional[Position]:
        """Get currently active position for this bot/pair combination"""
        query = select(Position).where(
            Position.bot_id == self.bot.id,
            Position.product_id == self.product_id,  # Filter by pair for multi-pair support
            Position.status == "open"
        ).order_by(desc(Position.opened_at))

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_open_positions_count(self) -> int:
        """Get count of all open positions for this bot (across all pairs)"""
        from sqlalchemy import func
        query = select(func.count(Position.id)).where(
            Position.bot_id == self.bot.id,
            Position.status == "open"
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def create_position(self, btc_balance: float, btc_amount: float) -> Position:
        """
        Create a new position for this bot

        Args:
            btc_balance: Current total BTC balance
            btc_amount: Amount of BTC being spent on initial buy
        """
        # Get BTC/USD price for tracking
        try:
            btc_usd_price = await self.coinbase.get_btc_usd_price()
        except:
            btc_usd_price = None

        position = Position(
            bot_id=self.bot.id,
            product_id=self.product_id,  # Use the engine's product_id (specific pair being traded)
            status="open",
            opened_at=datetime.utcnow(),
            initial_btc_balance=btc_balance,
            max_btc_allowed=btc_balance,  # Strategy determines actual limits
            total_btc_spent=0.0,
            total_eth_acquired=0.0,
            average_buy_price=0.0,
            btc_usd_price_at_open=btc_usd_price
        )

        self.db.add(position)
        # Don't commit here - let caller commit after trade succeeds
        # This ensures position only persists if trade is successful
        await self.db.flush()  # Flush to get position.id but don't commit

        return position

    async def execute_buy(
        self,
        position: Position,
        btc_amount: float,
        current_price: float,
        trade_type: str,
        signal_data: Optional[Dict[str, Any]] = None
    ) -> Trade:
        """
        Execute a buy order

        Args:
            position: Current position
            btc_amount: Amount of BTC to spend
            current_price: Current market price
            trade_type: 'initial' or 'dca' or strategy-specific type
            signal_data: Optional signal metadata
        """
        # Calculate amount to buy
        eth_amount = btc_amount / current_price

        # Execute order via Coinbase
        order_id = None
        try:
            order_response = await self.coinbase.buy_eth_with_btc(
                btc_amount=btc_amount,
                product_id=self.product_id
            )
            success_response = order_response.get("success_response", {})
            order_id = success_response.get("order_id", "")
        except Exception as e:
            print(f"Error executing buy order: {e}")

        # Record trade
        trade = Trade(
            position_id=position.id,
            timestamp=datetime.utcnow(),
            side="buy",
            btc_amount=btc_amount,
            eth_amount=eth_amount,
            price=current_price,
            trade_type=trade_type,
            order_id=order_id,
            macd_value=signal_data.get("macd_value") if signal_data else None,
            macd_signal=signal_data.get("macd_signal") if signal_data else None,
            macd_histogram=signal_data.get("macd_histogram") if signal_data else None
        )

        self.db.add(trade)

        # Update position totals
        position.total_btc_spent += btc_amount
        position.total_eth_acquired += eth_amount
        # Update average buy price manually (don't use update_averages() - it triggers lazy loading)
        if position.total_eth_acquired > 0:
            position.average_buy_price = position.total_btc_spent / position.total_eth_acquired
        else:
            position.average_buy_price = 0.0

        await self.db.commit()
        await self.db.refresh(trade)

        # Invalidate balance cache after trade
        await self.coinbase.invalidate_balance_cache()

        return trade

    async def execute_sell(
        self,
        position: Position,
        current_price: float,
        signal_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[Trade, float, float]:
        """
        Execute a sell order for entire position

        Returns:
            Tuple of (trade, profit_btc, profit_percentage)
        """
        eth_amount = position.total_eth_acquired
        btc_received = eth_amount * current_price

        # Execute order via Coinbase
        order_id = None
        try:
            order_response = await self.coinbase.sell_eth_for_btc(
                eth_amount=eth_amount,
                product_id=self.product_id
            )
            success_response = order_response.get("success_response", {})
            order_id = success_response.get("order_id", "")
        except Exception as e:
            print(f"Error executing sell order: {e}")

        # Calculate profit
        profit_btc = btc_received - position.total_btc_spent
        profit_percentage = (profit_btc / position.total_btc_spent) * 100

        # Get BTC/USD price for USD profit tracking
        try:
            btc_usd_price_at_close = await self.coinbase.get_btc_usd_price()
            profit_usd = profit_btc * btc_usd_price_at_close
        except:
            btc_usd_price_at_close = None
            profit_usd = None

        # Record trade
        trade = Trade(
            position_id=position.id,
            timestamp=datetime.utcnow(),
            side="sell",
            btc_amount=btc_received,
            eth_amount=eth_amount,
            price=current_price,
            trade_type="sell",
            order_id=order_id,
            macd_value=signal_data.get("macd_value") if signal_data else None,
            macd_signal=signal_data.get("macd_signal") if signal_data else None,
            macd_histogram=signal_data.get("macd_histogram") if signal_data else None
        )

        self.db.add(trade)

        # Close position
        position.status = "closed"
        position.closed_at = datetime.utcnow()
        position.sell_price = current_price
        position.total_btc_received = btc_received
        position.profit_btc = profit_btc
        position.profit_percentage = profit_percentage
        position.btc_usd_price_at_close = btc_usd_price_at_close
        position.profit_usd = profit_usd

        await self.db.commit()
        await self.db.refresh(trade)

        # Invalidate balance cache after trade
        await self.coinbase.invalidate_balance_cache()

        return trade, profit_btc, profit_percentage

    async def process_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float
    ) -> Dict[str, Any]:
        """
        Process market data with bot's strategy

        Args:
            candles: Recent candle data
            current_price: Current market price

        Returns:
            Dict with action taken and details
        """
        # Analyze signal using strategy
        signal_data = await self.strategy.analyze_signal(candles, current_price)

        if not signal_data:
            return {
                "action": "none",
                "reason": "No signal detected",
                "signal": None
            }

        # Get current state
        position = await self.get_active_position()
        btc_balance = await self.coinbase.get_btc_balance()

        # Log AI thinking immediately after analysis (if AI bot)
        if self.bot.strategy_type == "ai_autonomous":
            # Log what the AI thinks, not what the bot will do
            ai_signal = signal_data.get("signal_type", "none")
            if ai_signal == "buy":
                decision = "buy"
            elif ai_signal == "sell":
                decision = "sell"
            else:
                decision = "hold"
            await self.save_ai_log(signal_data, decision, current_price, position)

        # Check if we should buy (only if bot is active)
        should_buy = False
        btc_amount = 0
        buy_reason = ""

        logger.info(f"  🤖 Bot active: {self.bot.is_active}, Position exists: {position is not None}")

        if self.bot.is_active:
            # Check max concurrent deals limit (3Commas style)
            if position is None:  # Only check when considering opening a NEW position
                open_positions_count = await self.get_open_positions_count()
                max_deals = self.strategy.config.get("max_concurrent_deals", 1)

                if open_positions_count >= max_deals:
                    should_buy = False
                    buy_reason = f"Max concurrent deals limit reached ({open_positions_count}/{max_deals})"
                else:
                    should_buy, btc_amount, buy_reason = await self.strategy.should_buy(
                        signal_data, position, btc_balance
                    )
            else:
                # Position already exists for this pair - check for DCA
                should_buy, btc_amount, buy_reason = await self.strategy.should_buy(
                    signal_data, position, btc_balance
                )
        else:
            # Bot is stopped - don't open new positions
            if position is None:
                buy_reason = "Bot is stopped - not opening new positions"
            else:
                buy_reason = "Bot is stopped - managing existing position only"

        if should_buy:
            # Get BTC/USD price for logging
            try:
                btc_usd_price = await self.coinbase.get_btc_usd_price()
            except:
                btc_usd_price = None

            btc_formatted = format_btc_with_usd(btc_amount, btc_usd_price)
            logger.info(f"  💰 BUY DECISION: will buy {btc_formatted} worth of {self.product_id}")

            # Determine trade type
            is_new_position = position is None
            trade_type = "initial" if is_new_position else "dca"

            if is_new_position:
                logger.info(f"  🔨 Executing {trade_type} buy order FIRST (position will be created after success)...")
            else:
                logger.info(f"  🔨 Executing {trade_type} buy order for existing position...")

            # Execute buy FIRST - don't create position until we know trade succeeds
            try:
                # For new positions, we need to create position for the trade to reference
                # BUT we do it in a transaction that will rollback if trade fails
                if is_new_position:
                    logger.info(f"  📝 Creating position (will commit only if trade succeeds)...")
                    position = await self.create_position(btc_balance, btc_amount)
                    logger.info(f"  ✅ Position created: ID={position.id} (pending trade execution)")

                # Execute the actual trade
                trade = await self.execute_buy(
                    position=position,
                    btc_amount=btc_amount,
                    current_price=current_price,
                    trade_type=trade_type,
                    signal_data=signal_data
                )
                logger.info(f"  ✅ Trade executed: ID={trade.id}, Order={trade.order_id}")

            except Exception as e:
                logger.error(f"  ❌ Trade execution failed: {e}")
                # If this was a new position and trade failed, rollback the position
                if is_new_position and position:
                    logger.warning(f"  🗑️ Rolling back position {position.id} due to failed trade")
                    await self.db.rollback()
                    return {
                        "action": "none",
                        "reason": f"Buy failed: {str(e)}",
                        "signal": signal_data
                    }
                raise  # Re-raise for existing positions (DCA failures)

            # Record signal
            signal = Signal(
                position_id=position.id,
                timestamp=datetime.utcnow(),
                signal_type=signal_data.get("signal_type", "buy"),
                macd_value=signal_data.get("macd_value", 0),
                macd_signal=signal_data.get("macd_signal", 0),
                macd_histogram=signal_data.get("macd_histogram", 0),
                price=current_price,
                action_taken="buy",
                reason=buy_reason
            )
            self.db.add(signal)
            await self.db.commit()

            return {
                "action": "buy",
                "reason": buy_reason,
                "signal": signal_data,
                "trade": trade,
                "position": position
            }

        # Check if we should sell
        if position is not None:
            should_sell, sell_reason = await self.strategy.should_sell(
                signal_data, position, current_price
            )

            if should_sell:
                # Execute sell
                trade, profit_btc, profit_pct = await self.execute_sell(
                    position=position,
                    current_price=current_price,
                    signal_data=signal_data
                )

                # Record signal
                signal = Signal(
                    position_id=position.id,
                    timestamp=datetime.utcnow(),
                    signal_type=signal_data.get("signal_type", "sell"),
                    macd_value=signal_data.get("macd_value", 0),
                    macd_signal=signal_data.get("macd_signal", 0),
                    macd_histogram=signal_data.get("macd_histogram", 0),
                    price=current_price,
                    action_taken="sell",
                    reason=sell_reason
                )
                self.db.add(signal)
                await self.db.commit()

                return {
                    "action": "sell",
                    "reason": sell_reason,
                    "signal": signal_data,
                    "trade": trade,
                    "position": position,
                    "profit_btc": profit_btc,
                    "profit_percentage": profit_pct
                }
            else:
                # Hold - record signal with no action
                signal = Signal(
                    position_id=position.id,
                    timestamp=datetime.utcnow(),
                    signal_type=signal_data.get("signal_type", "hold"),
                    macd_value=signal_data.get("macd_value", 0),
                    macd_signal=signal_data.get("macd_signal", 0),
                    macd_histogram=signal_data.get("macd_histogram", 0),
                    price=current_price,
                    action_taken="hold",
                    reason=sell_reason
                )
                self.db.add(signal)
                await self.db.commit()

                return {
                    "action": "hold",
                    "reason": sell_reason,
                    "signal": signal_data,
                    "position": position
                }

        # Commit any pending changes (like AI logs)
        await self.db.commit()

        return {
            "action": "none",
            "reason": "Signal detected but no action criteria met",
            "signal": signal_data
        }
