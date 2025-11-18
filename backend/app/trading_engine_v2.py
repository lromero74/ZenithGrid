"""
Strategy-Based Trading Engine

Refactored to support multiple strategies and bots.
Works with any TradingStrategy implementation.
Supports both BTC and USD quote currencies.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_client import CoinbaseClient
from app.currency_utils import format_with_usd, get_quote_currency
from app.models import AIBotLog, Bot, PendingOrder, Position, Signal, Trade
from app.strategies import TradingStrategy
from app.trading_client import TradingClient

logger = logging.getLogger(__name__)


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
        self.trading_client = TradingClient(coinbase)  # Currency-agnostic wrapper
        self.bot = bot
        self.strategy = strategy
        # Use provided product_id, or fallback to bot's first pair
        self.product_id = product_id or (bot.get_trading_pairs()[0] if hasattr(bot, 'get_trading_pairs') else bot.product_id)
        self.quote_currency = get_quote_currency(self.product_id)

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
        from sqlalchemy.orm import selectinload

        query = select(Position).options(
            selectinload(Position.trades)  # Eager load trades to avoid greenlet errors in should_buy()
        ).where(
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

    async def create_position(self, quote_balance: float, quote_amount: float) -> Position:
        """
        Create a new position for this bot

        Args:
            quote_balance: Current total quote currency balance (BTC or USD)
            quote_amount: Amount of quote currency being spent on initial buy
        """
        # Get BTC/USD price for USD tracking
        try:
            btc_usd_price = await self.coinbase.get_btc_usd_price()
        except Exception:
            btc_usd_price = None

        position = Position(
            bot_id=self.bot.id,
            product_id=self.product_id,  # Use the engine's product_id (specific pair being traded)
            status="open",
            opened_at=datetime.utcnow(),
            initial_quote_balance=quote_balance,
            max_quote_allowed=quote_balance,  # Strategy determines actual limits
            total_quote_spent=0.0,
            total_base_acquired=0.0,
            average_buy_price=0.0,
            btc_usd_price_at_open=btc_usd_price,
            strategy_config_snapshot=self.bot.strategy_config  # Freeze config at position creation (like 3Commas)
        )

        self.db.add(position)
        # Don't commit here - let caller commit after trade succeeds
        # This ensures position only persists if trade is successful
        await self.db.flush()  # Flush to get position.id but don't commit

        return position

    async def execute_buy(
        self,
        position: Position,
        quote_amount: float,
        current_price: float,
        trade_type: str,
        signal_data: Optional[Dict[str, Any]] = None
    ) -> Trade:
        """
        Execute a buy order (market or limit based on configuration)

        For safety orders, checks position's strategy_config_snapshot for safety_order_type.
        If "limit", places a limit order instead of executing immediately.

        Args:
            position: Current position
            quote_amount: Amount of quote currency to spend (BTC or USD)
            current_price: Current market price
            trade_type: 'initial' or 'dca' or strategy-specific type
            signal_data: Optional signal metadata

        Returns:
            Trade record (for market orders only; limit orders return None)
        """
        # Check if this is a safety order that should use limit orders
        is_safety_order = trade_type.startswith("safety_order")
        config = position.strategy_config_snapshot or {}
        safety_order_type = config.get("safety_order_type", "market")

        if is_safety_order and safety_order_type == "limit":
            # Place limit order instead of market order
            # Calculate limit price (use current price as-is for now)
            # Note: In the future, this could apply a discount or use strategy-specific logic
            limit_price = current_price

            logger.info(f"  📋 Placing limit buy order: {quote_amount:.8f} {self.quote_currency} @ {limit_price:.8f}")

            pending_order = await self.execute_limit_buy(
                position=position,
                quote_amount=quote_amount,
                limit_price=limit_price,
                trade_type=trade_type,
                signal_data=signal_data
            )

            # Return None for limit orders (no Trade created yet)
            # The order monitoring service will create the Trade when filled
            return None

        # Execute market order (immediate execution)
        # Calculate amount of base currency to buy
        base_amount = quote_amount / current_price

        # Execute order via TradingClient (currency-agnostic)
        order_id = None
        try:
            order_response = await self.trading_client.buy(
                product_id=self.product_id,
                quote_amount=quote_amount
            )
            success_response = order_response.get("success_response", {})
            error_response = order_response.get("error_response", {})
            order_id = success_response.get("order_id", "")

            # CRITICAL: Validate order_id is present
            if not order_id:
                # Log the full Coinbase response to understand why order failed
                logger.error(f"Coinbase order failed - Full response: {order_response}")

                # Save error to position for UI display (like 3Commas)
                error_msg = "Order failed"
                if error_response:
                    error_msg = error_response.get("message", "Unknown error")
                    error_details = error_response.get("error_details", "")
                    logger.error(f"Coinbase error: {error_msg} - {error_details}")
                    full_error = f"{error_msg}: {error_details}" if error_details else error_msg
                else:
                    full_error = "No order_id returned from Coinbase"

                # Record error on position
                position.last_error_message = full_error
                position.last_error_timestamp = datetime.utcnow()
                await self.db.commit()

                raise ValueError(f"Coinbase order failed: {full_error}")

        except Exception as e:
            logger.error(f"Error executing buy order: {e}")
            # Record error on position if it's not already recorded
            if position and not position.last_error_message:
                position.last_error_message = str(e)
                position.last_error_timestamp = datetime.utcnow()
                await self.db.commit()
            raise

        # Record trade
        trade = Trade(
            position_id=position.id,
            timestamp=datetime.utcnow(),
            side="buy",
            quote_amount=quote_amount,
            base_amount=base_amount,
            price=current_price,
            trade_type=trade_type,
            order_id=order_id,
            macd_value=signal_data.get("macd_value") if signal_data else None,
            macd_signal=signal_data.get("macd_signal") if signal_data else None,
            macd_histogram=signal_data.get("macd_histogram") if signal_data else None
        )

        self.db.add(trade)

        # Clear any previous errors on successful trade
        position.last_error_message = None
        position.last_error_timestamp = None

        # Update position totals
        position.total_quote_spent += quote_amount
        position.total_base_acquired += base_amount
        # Update average buy price manually (don't use update_averages() - it triggers lazy loading)
        if position.total_base_acquired > 0:
            position.average_buy_price = position.total_quote_spent / position.total_base_acquired
        else:
            position.average_buy_price = 0.0

        await self.db.commit()
        await self.db.refresh(trade)

        # Invalidate balance cache after trade
        await self.trading_client.invalidate_balance_cache()

        return trade

    async def execute_limit_buy(
        self,
        position: Position,
        quote_amount: float,
        limit_price: float,
        trade_type: str,
        signal_data: Optional[Dict[str, Any]] = None
    ) -> PendingOrder:
        """
        Place a limit buy order and track it in pending_orders table

        Args:
            position: Current position
            quote_amount: Amount of quote currency to spend (BTC or USD)
            limit_price: Target price for the limit order
            trade_type: 'safety_order_1', 'safety_order_2', etc.
            signal_data: Optional signal metadata

        Returns:
            PendingOrder record
        """
        # Calculate base amount at limit price
        base_amount = quote_amount / limit_price

        # Place limit order via TradingClient
        order_id = None
        try:
            order_response = await self.trading_client.buy_limit(
                product_id=self.product_id,
                limit_price=limit_price,
                quote_amount=quote_amount
            )
            success_response = order_response.get("success_response", {})
            order_id = success_response.get("order_id", "")

            if not order_id:
                raise ValueError("No order_id returned from Coinbase")

        except Exception as e:
            logger.error(f"Error placing limit buy order: {e}")
            raise

        # Create PendingOrder record
        pending_order = PendingOrder(
            position_id=position.id,
            bot_id=self.bot.id,
            order_id=order_id,
            product_id=self.product_id,
            side="BUY",
            order_type="LIMIT",
            limit_price=limit_price,
            quote_amount=quote_amount,
            base_amount=base_amount,
            trade_type=trade_type,
            status="pending",
            created_at=datetime.utcnow()
        )

        self.db.add(pending_order)
        await self.db.commit()
        await self.db.refresh(pending_order)

        logger.info(f"✅ Placed limit buy order: {quote_amount:.8f} {self.quote_currency} @ {limit_price:.8f} (Order ID: {order_id})")

        return pending_order

    async def execute_sell(
        self,
        position: Position,
        current_price: float,
        signal_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[Trade, float, float]:
        """
        Execute a sell order for entire position

        Returns:
            Tuple of (trade, profit_quote, profit_percentage)
        """
        # Sell 99.99% to prevent precision/rounding rejections from Coinbase
        # Leaves tiny "dust" amount but ensures sell executes successfully
        # The 0.01% dust can be cleaned up later
        base_amount = position.total_base_acquired * 0.9999
        quote_received = base_amount * current_price

        # Log the dust amount
        dust_amount = position.total_base_acquired - base_amount
        logger.info(f"  💰 Selling {base_amount:.8f} {self.product_id.split('-')[0]} (leaving {dust_amount:.8f} dust)")

        # Execute order via TradingClient (currency-agnostic)
        order_id = None
        try:
            order_response = await self.trading_client.sell(
                product_id=self.product_id,
                base_amount=base_amount
            )
            success_response = order_response.get("success_response", {})
            order_id = success_response.get("order_id", "")

            # CRITICAL: Validate order_id is present
            if not order_id:
                raise ValueError("No order_id returned from Coinbase - sell order may have failed")

        except Exception as e:
            logger.error(f"Error executing sell order: {e}")
            raise

        # Calculate profit
        profit_quote = quote_received - position.total_quote_spent
        profit_percentage = (profit_quote / position.total_quote_spent) * 100

        # Get BTC/USD price for USD profit tracking
        try:
            btc_usd_price_at_close = await self.coinbase.get_btc_usd_price()
            # Convert profit to USD if quote is BTC
            if self.quote_currency == "BTC":
                profit_usd = profit_quote * btc_usd_price_at_close
            else:  # quote is USD
                profit_usd = profit_quote
        except Exception:
            btc_usd_price_at_close = None
            profit_usd = None

        # Record trade
        trade = Trade(
            position_id=position.id,
            timestamp=datetime.utcnow(),
            side="sell",
            quote_amount=quote_received,
            base_amount=base_amount,
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
        position.total_quote_received = quote_received
        position.profit_quote = profit_quote
        position.profit_percentage = profit_percentage
        position.btc_usd_price_at_close = btc_usd_price_at_close
        position.profit_usd = profit_usd

        await self.db.commit()
        await self.db.refresh(trade)

        # Invalidate balance cache after trade
        await self.trading_client.invalidate_balance_cache()

        return trade, profit_quote, profit_percentage

    async def process_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        pre_analyzed_signal: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process market data with bot's strategy

        Args:
            candles: Recent candle data
            current_price: Current market price
            pre_analyzed_signal: Optional pre-analyzed signal from batch mode (prevents duplicate AI calls)

        Returns:
            Dict with action taken and details
        """
        # Use pre-analyzed signal if provided (from batch mode), otherwise analyze now
        if pre_analyzed_signal:
            signal_data = pre_analyzed_signal
            logger.info(f"  Using pre-analyzed signal from batch mode (confidence: {signal_data.get('confidence')}%)")
        else:
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

        # Get bot's available balance (reserved balance or total portfolio)
        reserved_balance = self.bot.get_reserved_balance()
        if reserved_balance > 0:
            # Bot has reserved balance - use it instead of total portfolio
            # Calculate how much is available (reserved - already in positions)
            quote_balance = reserved_balance

            # Subtract amount already in open positions for this bot
            from sqlalchemy import select

            from app.models import Position
            query = select(Position).where(
                Position.bot_id == self.bot.id,
                Position.status == "open",
                Position.product_id == self.product_id
            )
            result = await self.db.execute(query)
            open_positions = result.scalars().all()

            total_in_positions = sum(p.total_quote_spent for p in open_positions)
            quote_balance -= total_in_positions

            logger.info(f"  💰 Bot reserved balance: {reserved_balance}, In positions: {total_in_positions}, Available: {quote_balance}")
        else:
            # No reserved balance - use total portfolio balance (backward compatibility)
            quote_balance = await self.trading_client.get_quote_balance(self.product_id)
            logger.info(f"  💰 Using total portfolio balance: {quote_balance}")

        # Log AI thinking immediately after analysis (if AI bot and not already logged in batch mode)
        if self.bot.strategy_type == "ai_autonomous" and not signal_data.get("_already_logged", False):
            # DEBUG: This should NOT be called in batch mode!
            import traceback
            stack = ''.join(traceback.format_stack()[-5:-1])
            logger.warning(f"  ⚠️ save_ai_log called despite _already_logged check! Bot #{self.bot.id} {self.product_id}")
            logger.warning(f"  _already_logged={signal_data.get('_already_logged')}")
            logger.warning(f"  Call stack:\n{stack}")

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
        quote_amount = 0
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
                    should_buy, quote_amount, buy_reason = await self.strategy.should_buy(
                        signal_data, position, quote_balance
                    )
            else:
                # Position already exists for this pair - check for DCA
                should_buy, quote_amount, buy_reason = await self.strategy.should_buy(
                    signal_data, position, quote_balance
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
            except Exception:
                btc_usd_price = None

            quote_formatted = format_with_usd(quote_amount, self.product_id, btc_usd_price)
            logger.info(f"  💰 BUY DECISION: will buy {quote_formatted} worth of {self.product_id}")

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
                    logger.info("  📝 Creating position (will commit only if trade succeeds)...")
                    position = await self.create_position(quote_balance, quote_amount)
                    logger.info(f"  ✅ Position created: ID={position.id} (pending trade execution)")

                # Execute the actual trade
                trade = await self.execute_buy(
                    position=position,
                    quote_amount=quote_amount,
                    current_price=current_price,
                    trade_type=trade_type,
                    signal_data=signal_data
                )

                if trade is None:
                    # Limit order was placed instead
                    logger.info(f"  ✅ Limit order placed (pending fill)")
                else:
                    # Market order executed immediately
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
                trade, profit_quote, profit_pct = await self.execute_sell(
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
                    "profit_quote": profit_quote,
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
