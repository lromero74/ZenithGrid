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

from app.coinbase_unified_client import CoinbaseClient
from app.currency_utils import format_with_usd, get_quote_currency
from app.models import AIBotLog, Bot, OrderHistory, PendingOrder, Position, Signal, Trade
from app.strategies import TradingStrategy
from app.trading_client import TradingClient
from app.order_validation import validate_order_size

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
            position_id=position.id if position else None,  # Link to position for historical review
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

    async def log_order_to_history(
        self,
        position: Optional[Position],
        side: str,
        order_type: str,
        trade_type: str,
        quote_amount: float,
        price: float,
        status: str,
        order_id: Optional[str] = None,
        base_amount: Optional[float] = None,
        error_message: Optional[str] = None
    ):
        """
        Log order attempt to order_history table for audit trail.
        Similar to 3Commas order history.

        Args:
            position: Position (None for failed base orders)
            side: "BUY" or "SELL"
            order_type: "MARKET", "LIMIT", etc.
            trade_type: "initial", "dca", "safety_order_1", etc.
            quote_amount: Amount of quote currency attempted
            price: Price at time of order
            status: "success", "failed", "canceled"
            order_id: Coinbase order ID (None for failed orders)
            base_amount: Amount of base currency acquired (None for failed orders)
            error_message: Error details if failed
        """
        try:
            order_history = OrderHistory(
                timestamp=datetime.utcnow(),
                bot_id=self.bot.id,
                position_id=position.id if position else None,
                product_id=self.product_id,
                side=side,
                order_type=order_type,
                trade_type=trade_type,
                quote_amount=quote_amount,
                base_amount=base_amount,
                price=price,
                status=status,
                order_id=order_id,
                error_message=error_message
            )
            self.db.add(order_history)
            # Note: Don't commit here - let caller handle commits
        except Exception as e:
            logger.error(f"Failed to log order to history: {e}")
            # Don't fail the entire operation if logging fails

    async def execute_buy(
        self,
        position: Position,
        quote_amount: float,
        current_price: float,
        trade_type: str,
        signal_data: Optional[Dict[str, Any]] = None,
        commit_on_error: bool = True
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
            commit_on_error: If True, commit errors to DB (for DCA orders).
                           If False, don't commit errors (for base orders - let rollback work)

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
        # Validate order meets minimum size requirements
        is_valid, error_msg = await validate_order_size(
            self.coinbase,
            self.product_id,
            quote_amount=quote_amount
        )

        if not is_valid:
            logger.warning(f"Order validation failed: {error_msg}")

            # Log failed order to history
            await self.log_order_to_history(
                position=position,
                side="BUY",
                order_type="MARKET",
                trade_type=trade_type,
                quote_amount=quote_amount,
                price=current_price,
                status="failed",
                error_message=error_msg
            )

            # Save error to position for UI display (only for DCA orders)
            if commit_on_error:
                position.last_error_message = error_msg
                position.last_error_timestamp = datetime.utcnow()
                await self.db.commit()
            raise ValueError(error_msg)

        # Execute order via TradingClient (currency-agnostic)
        # Actual fill amounts will be fetched from Coinbase after order executes
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
                if error_response:
                    # Try multiple possible error field names from Coinbase
                    error_msg = error_response.get("message") or error_response.get("error") or "Unknown error"
                    error_details = error_response.get("error_details", "")
                    failure_reason = error_response.get("failure_reason", "")
                    preview_failure_reason = error_response.get("preview_failure_reason", "")

                    # Build comprehensive error message
                    error_parts = [error_msg]
                    if error_details:
                        error_parts.append(error_details)
                    if failure_reason:
                        error_parts.append(f"Reason: {failure_reason}")
                    if preview_failure_reason:
                        error_parts.append(f"Preview: {preview_failure_reason}")

                    full_error = " - ".join(error_parts)

                    # If still no useful error, show the entire error_response as JSON
                    if full_error == "Unknown error":
                        import json
                        full_error = f"Coinbase error: {json.dumps(error_response)}"

                    logger.error(f"Coinbase error details: {full_error}")
                else:
                    full_error = "No order_id returned from Coinbase (no error_response provided)"

                # Log failed order to history
                await self.log_order_to_history(
                    position=position,
                    side="BUY",
                    order_type="MARKET",
                    trade_type=trade_type,
                    quote_amount=quote_amount,
                    price=current_price,
                    status="failed",
                    error_message=full_error
                )

                # Record error on position (only for DCA orders)
                if commit_on_error:
                    position.last_error_message = full_error
                    position.last_error_timestamp = datetime.utcnow()
                    await self.db.commit()

                raise ValueError(f"Coinbase order failed: {full_error}")

            # Fetch actual fill data from Coinbase
            logger.info(f"Fetching order details for order_id: {order_id}")
            order_details = await self.coinbase.get_order(order_id)

            # Extract actual fills from nested order object
            order_obj = order_details.get("order", {})
            filled_size_str = order_obj.get("filled_size", "0")
            filled_value_str = order_obj.get("filled_value", "0")
            avg_price_str = order_obj.get("average_filled_price", "0")

            # Convert to floats
            actual_base_amount = float(filled_size_str)
            actual_quote_amount = float(filled_value_str)
            actual_price = float(avg_price_str)

            logger.info(f"Order filled - Base: {actual_base_amount}, Quote: {actual_quote_amount}, Avg Price: {actual_price}")

        except Exception as e:
            logger.error(f"Error executing buy order: {e}")

            # Log failed order to history (only if not already logged)
            # ValueError exceptions were already logged above, so skip those
            if not isinstance(e, ValueError):
                await self.log_order_to_history(
                    position=position,
                    side="BUY",
                    order_type="MARKET",
                    trade_type=trade_type,
                    quote_amount=quote_amount,
                    price=current_price,
                    status="failed",
                    error_message=str(e)
                )

            # Record error on position if it's not already recorded (only for DCA orders)
            if commit_on_error and position and not position.last_error_message:
                position.last_error_message = str(e)
                position.last_error_timestamp = datetime.utcnow()
                await self.db.commit()
            raise

        # Record trade with ACTUAL filled amounts from Coinbase
        trade = Trade(
            position_id=position.id,
            timestamp=datetime.utcnow(),
            side="buy",
            quote_amount=actual_quote_amount,  # Use actual filled value
            base_amount=actual_base_amount,     # Use actual filled size
            price=actual_price,                 # Use actual average price
            trade_type=trade_type,
            order_id=order_id,
            macd_value=signal_data.get("macd_value") if signal_data else None,
            macd_signal=signal_data.get("macd_signal") if signal_data else None,
            macd_histogram=signal_data.get("macd_histogram") if signal_data else None
        )

        self.db.add(trade)

        # Log successful order to history
        await self.log_order_to_history(
            position=position,
            side="BUY",
            order_type="MARKET",
            trade_type=trade_type,
            quote_amount=actual_quote_amount,
            price=actual_price,
            status="success",
            order_id=order_id,
            base_amount=actual_base_amount
        )

        # Clear any previous errors on successful trade
        position.last_error_message = None
        position.last_error_timestamp = None

        # Update position totals with ACTUAL filled amounts
        position.total_quote_spent += actual_quote_amount
        position.total_base_acquired += actual_base_amount
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
        # Sell 99% to prevent precision/rounding rejections from Coinbase
        # Leaves 1% "dust" amount but ensures sell executes successfully
        # The 1% dust can be cleaned up later
        # Using 0.99 instead of 0.9999 because our tracked amounts may be slightly
        # higher than actual Coinbase balances due to calculation vs actual fills
        base_amount = position.total_base_acquired * 0.99
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

            # Log the full response for debugging
            logger.info(f"Coinbase sell order response: {order_response}")

            # Check success flag first
            if not order_response.get("success", False):
                # Order failed - check error response
                error_response = order_response.get("error_response", {})
                if error_response:
                    error_msg = error_response.get("message", "Unknown error")
                    error_details = error_response.get("error_details", "")
                    error_code = error_response.get("error", "UNKNOWN")
                    raise ValueError(f"Coinbase sell order failed [{error_code}]: {error_msg}. Details: {error_details}")
                else:
                    raise ValueError(f"Coinbase sell order failed with no error details. Full response: {order_response}")

            # Extract order_id from success_response (documented format)
            success_response = order_response.get("success_response", {})
            order_id = success_response.get("order_id", "")

            # Fallback: try top-level order_id
            if not order_id:
                order_id = order_response.get("order_id", "")

            # CRITICAL: Validate order_id is present
            if not order_id:
                logger.error(f"Full Coinbase response: {order_response}")
                raise ValueError(f"No order_id found in successful Coinbase response. Response keys: {list(order_response.keys())}")

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
        # Get current state FIRST (needed for web search context)
        position = await self.get_active_position()

        # Determine action context for web search
        action_context = "hold"  # Default for positions that exist
        if position is None:
            action_context = "open"  # Considering opening a new position
        # (We'll update to "close" or "dca" later based on actual decision)

        # Use pre-analyzed signal if provided (from batch mode), otherwise analyze now
        if pre_analyzed_signal:
            signal_data = pre_analyzed_signal
            logger.info(f"  Using pre-analyzed signal from batch mode (confidence: {signal_data.get('confidence')}%)")
        else:
            # Analyze signal using strategy (with position and context for web search)
            signal_data = await self.strategy.analyze_signal(
                candles,
                current_price,
                position=position,
                action_context=action_context
            )

        if not signal_data:
            return {
                "action": "none",
                "reason": "No signal detected",
                "signal": None
            }

        # Get bot's available balance (budget-based or total portfolio)
        # Calculate aggregate portfolio value for bot budgeting
        print(f"🔍 Bot budget_percentage: {self.bot.budget_percentage}%, quote_currency: {self.quote_currency}")
        aggregate_value = None
        if self.bot.budget_percentage > 0:
            # Bot uses percentage-based budgeting - calculate aggregate value
            if self.quote_currency == "USD":
                aggregate_value = await self.coinbase.calculate_aggregate_usd_value()
                print(f"🔍 Aggregate USD value: ${aggregate_value:.2f}")
                logger.info(f"  💰 Aggregate USD value: ${aggregate_value:.2f}")
            else:
                aggregate_value = await self.coinbase.calculate_aggregate_btc_value()
                print(f"🔍 Aggregate BTC value: {aggregate_value:.8f} BTC")
                logger.info(f"  💰 Aggregate BTC value: {aggregate_value:.8f} BTC")

        reserved_balance = self.bot.get_reserved_balance(aggregate_value)
        print(f"🔍 Reserved balance (per-position): {reserved_balance:.8f}")
        if reserved_balance > 0:
            # Bot has reserved balance - get_reserved_balance() already divides by max_concurrent_deals
            # so reserved_balance IS the per-position budget
            max_concurrent_deals = max(self.bot.strategy_config.get('max_concurrent_deals', 1), 1)
            per_position_budget = reserved_balance  # Already per-position, don't divide again!

            # Calculate how much is available for THIS position (per-position budget - already spent in this position)
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
            quote_balance = per_position_budget - total_in_positions

            if self.bot.budget_percentage > 0:
                logger.info(f"  💰 Bot budget: {self.bot.budget_percentage}% of aggregate ({reserved_balance:.8f}), Max deals: {max_concurrent_deals}, Per-position: {per_position_budget:.8f}, In positions: {total_in_positions:.8f}, Available: {quote_balance:.8f}")
            else:
                logger.info(f"  💰 Bot reserved balance: {reserved_balance}, Max deals: {max_concurrent_deals}, Per-position: {per_position_budget:.8f}, In positions: {total_in_positions}, Available: {quote_balance}")
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

        print(f"🔍 Bot active: {self.bot.is_active}, Position exists: {position is not None}")
        logger.info(f"  🤖 Bot active: {self.bot.is_active}, Position exists: {position is not None}")

        if self.bot.is_active:
            # Check max concurrent deals limit (3Commas style)
            if position is None:  # Only check when considering opening a NEW position
                open_positions_count = await self.get_open_positions_count()
                max_deals = self.strategy.config.get("max_concurrent_deals", 1)
                print(f"🔍 Open positions: {open_positions_count}/{max_deals}")

                if open_positions_count >= max_deals:
                    should_buy = False
                    buy_reason = f"Max concurrent deals limit reached ({open_positions_count}/{max_deals})"
                    print(f"🔍 Should buy: FALSE - {buy_reason}")
                else:
                    print(f"🔍 Calling strategy.should_buy() with quote_balance={quote_balance:.8f}")
                    should_buy, quote_amount, buy_reason = await self.strategy.should_buy(
                        signal_data, position, quote_balance
                    )
                    print(f"🔍 Should buy result: {should_buy}, amount: {quote_amount:.8f}, reason: {buy_reason}")
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
                    signal_data=signal_data,
                    commit_on_error=not is_new_position  # Don't commit errors for base orders
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

                # Log the SELL decision to AI logs (even if AI recommended something else)
                # This captures what the trading engine actually did, not just what AI suggested
                await self.save_ai_log(
                    signal_data={
                        **signal_data,
                        "signal_type": "sell",
                        "reasoning": f"SELL EXECUTED: {sell_reason}",
                        "confidence": 100,  # Trading engine decision, not AI suggestion
                    },
                    decision="sell",
                    current_price=current_price,
                    position=position
                )

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
