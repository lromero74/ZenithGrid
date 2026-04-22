"""Sell-side decision + execution for the signal processor.

Internal module — consumers should import through app.trading_engine.signal_processor.
Split out of the original monolithic signal_processor.py as part of
code-quality Phase 5.1.
"""

import logging
from typing import Any, Dict, List, Optional

from app.models import Position
from app.trading_engine.book_depth_guard import check_sell_slippage
from app.trading_engine.buy_executor import execute_buy_close_short
from app.trading_engine.order_logger import save_ai_log
from app.trading_engine.perps_executor import execute_perps_close
from app.trading_engine.sell_executor import execute_sell
from app.trading_engine.signal_processor._shared import (
    _calculate_market_context_with_indicators,
    _previous_market_context,
    _record_signal,
)
from app.trading_engine.trade_context import TradeContext

logger = logging.getLogger(__name__)


async def _decide_and_execute_sell(
    ctx: TradeContext, position: Position,
    signal_data: Dict[str, Any],
    candles: List[Dict[str, Any]],
    candles_by_timeframe: Optional[Dict[str, List[Dict[str, Any]]]],
) -> Optional[Dict[str, Any]]:
    """Decide whether to sell and execute the sell if conditions are met.

    Returns a result dict if sell/hold action taken, None if no position.
    """
    db, exchange, trading_client = ctx.db, ctx.exchange, ctx.trading_client
    bot, strategy = ctx.bot, ctx.strategy
    product_id, current_price = ctx.product_id, ctx.current_price
    # Debug: Log timeframes available in candles_by_timeframe
    if candles_by_timeframe:
        for tf, tf_candles in candles_by_timeframe.items():
            logger.debug(f"  📊 candles_by_timeframe[{tf}]: {len(tf_candles) if tf_candles else 0} candles")
    else:
        logger.debug("  📊 candles_by_timeframe is None or empty")

    # Calculate market context with indicators for custom sell conditions
    # E4: Reuse indicators from signal_data if already calculated (avoids duplicate work on sell check)
    if signal_data and "indicators" in signal_data:
        market_context = {
            "price": current_price,
            "rsi": 50.0, "rsi_14": 50.0,
            "macd": 0.0, "macd_signal": 0.0, "macd_histogram": 0.0,
            "macd_12_26_9": 0.0, "macd_signal_12_26_9": 0.0, "macd_histogram_12_26_9": 0.0,
            "bb_percent": 50.0,
        }
        # Copy indicator values that overlap with market_context keys
        ind = signal_data["indicators"]
        for key in ("rsi_14", "macd_12_26_9", "macd_signal_12_26_9", "macd_histogram_12_26_9"):
            if key in ind:
                market_context[key] = ind[key]
        if "rsi_14" in ind:
            market_context["rsi"] = ind["rsi_14"]
        for mk in ("macd", "macd_signal", "macd_histogram"):
            k = f"{mk}_12_26_9" if mk != "macd" else "macd_12_26_9"
            if k in ind:
                market_context[mk] = ind[k]
        # Copy timeframe-prefixed keys (bb_percent, bb_upper, etc.)
        for key, val in ind.items():
            if "_bb_" in key or key.endswith("_price"):
                market_context[key] = val
        # Set non-prefixed BB values from first available timeframe
        for key, val in ind.items():
            if key.endswith("_bb_percent") and market_context["bb_percent"] == 50.0:
                market_context["bb_percent"] = val
            if key.endswith("_bb_upper_20_2") and "bb_upper_20_2" not in market_context:
                market_context["bb_upper_20_2"] = val
            if key.endswith("_bb_lower_20_2") and "bb_lower_20_2" not in market_context:
                market_context["bb_lower_20_2"] = val
            if key.endswith("_bb_middle_20_2") and "bb_middle_20_2" not in market_context:
                market_context["bb_middle_20_2"] = val
    else:
        market_context = _calculate_market_context_with_indicators(candles, current_price, candles_by_timeframe)

    # Add previous indicators for crossing detection
    cache_key = f"{bot.id}_{product_id}"
    previous_context = _previous_market_context.get(cache_key)
    market_context["_previous"] = previous_context
    # Update cache with current context (copy to avoid mutation issues)
    _previous_market_context[cache_key] = {k: v for k, v in market_context.items() if k != "_previous"}

    should_sell, sell_reason = await strategy.should_sell(signal_data, position, current_price, market_context)

    if should_sell:
        # CRITICAL FIX: For limit orders, verify profit at MARK PRICE meets threshold
        # should_sell checked profit at current_price (candle close), but limit orders
        # are placed at mark price (bid/ask midpoint) which can be significantly lower
        config = position.strategy_config_snapshot or {}
        take_profit_order_type = config.get("take_profit_order_type", "market")
        take_profit_mode = config.get("take_profit_mode")
        if take_profit_mode is None:
            # Legacy inference
            if config.get("trailing_take_profit", False):
                take_profit_mode = "trailing"
            elif config.get("min_profit_for_conditions") is not None:
                take_profit_mode = "minimum"
            else:
                take_profit_mode = "fixed"

        # For limit orders, verify profit at mark price meets threshold
        if take_profit_order_type == "limit":
            tp_pct = config.get("take_profit_percentage", 3.0)
            try:
                ticker = await exchange.get_ticker(product_id)
                best_bid = float(ticker.get("best_bid", 0))
                best_ask = float(ticker.get("best_ask", 0))
                mark_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else current_price

                mark_value = position.total_base_acquired * mark_price
                mark_profit = mark_value - position.total_quote_spent
                mark_profit_pct = (mark_profit / position.total_quote_spent) * 100

                if mark_profit_pct < tp_pct:
                    logger.info(
                        f"  ⚠️ Sell conditions met BUT mark price profit ({mark_profit_pct:.2f}%) "
                        f"< take_profit ({tp_pct}%) - HOLDING"
                    )
                    hold_reason = f"Conditions met but mark profit {mark_profit_pct:.2f}% < {tp_pct}%"
                    await _record_signal(
                        db, position, "hold", "hold", hold_reason,
                        current_price, signal_data,
                    )
                    return {
                        "action": "hold",
                        "reason": f"Sell blocked: mark profit {mark_profit_pct:.2f}% < {tp_pct}%",
                        "signal": signal_data,
                        "position": position,
                    }
                else:
                    logger.info(
                        f"  ✓ Mark price profit ({mark_profit_pct:.2f}%)"
                        f" >= take_profit ({tp_pct}%)"
                        " - proceeding"
                    )
            except Exception as e:
                logger.warning(f"Could not verify mark price profit, proceeding with sell: {e}")

        # Slippage guard for market sell orders
        if take_profit_order_type == "market" and config.get("slippage_guard", False):
            proceed, guard_reason = await check_sell_slippage(
                exchange, product_id, position, config
            )
            if not proceed:
                logger.info(f"  🛡️ Slippage guard blocked sell: {guard_reason}")
                await _record_signal(
                    db, position, "hold", "hold",
                    f"Slippage guard: {guard_reason}", current_price, signal_data,
                )
                return {
                    "action": "hold",
                    "reason": f"Slippage guard: {guard_reason}",
                    "signal": signal_data,
                    "position": position,
                }

        # Stop loss / trailing stop always execute at market (no limit orders)
        sell_reason_lower = sell_reason.lower()
        is_stop_loss = "stop loss" in sell_reason_lower or "tsl triggered" in sell_reason_lower

        # Check if limit close order already pending
        if position.closing_via_limit:
            logger.warning(
                f"  ⚠️ Position #{position.id} already has a pending limit close order, skipping sell signal"
            )
            await _record_signal(
                db, position, "hold", "hold",
                f"Limit close order already pending (order_id: {position.limit_close_order_id})",
                current_price, signal_data,
            )
            return {
                "action": "hold",
                "reason": "Limit close order already pending",
                "signal": signal_data,
                "position": position,
            }

        # Execute close order (direction-aware)
        # Route perps positions to perps executor
        if getattr(position, 'product_type', 'spot') == 'future':
            coinbase_client = getattr(exchange, '_client', None) or getattr(exchange, 'client', None)
            if coinbase_client is None:
                logger.error("Cannot get CoinbaseClient for perps close")
                raise RuntimeError("Perps trading requires CoinbaseClient")

            success, profit_quote, profit_pct = await execute_perps_close(
                db=db,
                client=coinbase_client,
                position=position,
                current_price=current_price,
                reason="signal",
            )
            if not success:
                raise RuntimeError("Perps close order failed")
            trade = None  # Trade record created inside execute_perps_close

        # For long positions: sell the BTC we bought
        # For short positions: buy back the BTC we sold
        elif position.direction == "short":
            # CLOSE SHORT: Buy back BTC (opposite of opening short)

            trade, profit_quote, profit_pct = await execute_buy_close_short(
                db=db,
                exchange=exchange,
                trading_client=trading_client,
                bot=bot,
                product_id=product_id,
                position=position,
                current_price=current_price,
                signal_data=signal_data,
            )
        else:
            # CLOSE LONG: Sell the BTC we bought (existing logic)
            trade, profit_quote, profit_pct = await execute_sell(
                db=db,
                exchange=exchange,
                trading_client=trading_client,
                bot=bot,
                product_id=product_id,
                position=position,
                current_price=current_price,
                signal_data=signal_data,
                force_market=is_stop_loss,
            )

        # If trade is None, either a limit order was placed or dust close happened
        if trade is None:
            if position.status == "closed":
                # Dust close — position was closed without an exchange order
                logger.warning(f"  ⚠️ Position #{position.id} dust-closed (profit: {profit_pct:.2f}%)")
                await _record_signal(
                    db, position, signal_data.get("signal_type", "sell"), "sell",
                    f"Dust close: {sell_reason}", current_price, signal_data,
                )
                return {
                    "action": "sell",
                    "reason": f"Dust close: {sell_reason}",
                    "profit_pct": profit_pct,
                    "position_id": position.id,
                }
            logger.info(f"  📊 Limit close order placed for position #{position.id}, waiting for fill")
            return {
                "action": "limit_close_pending",
                "reason": sell_reason,
                "limit_order_placed": True,
                "position_id": position.id,
            }

        # Record signal for market sell
        await _record_signal(
            db, position, signal_data.get("signal_type", "sell"), "sell",
            sell_reason, current_price, signal_data,
        )

        # Log the SELL decision to AI logs (even if AI recommended something else)
        # This captures what the trading engine actually did, not just what AI suggested
        await save_ai_log(
            db=db,
            bot=bot,
            product_id=product_id,
            signal_data={
                **signal_data,
                "signal_type": "sell",
                "reasoning": f"SELL EXECUTED: {sell_reason}",
                "confidence": 100,  # Trading engine decision, not AI suggestion
            },
            decision="sell",
            current_price=current_price,
            position=position,
        )

        return {
            "action": "sell",
            "reason": sell_reason,
            "signal": signal_data,
            "trade": trade,
            "position": position,
            "profit_quote": profit_quote,
            "profit_percentage": profit_pct,
        }
    else:
        # Hold - record signal with no action
        await _record_signal(
            db, position, signal_data.get("signal_type", "hold"), "hold",
            sell_reason, current_price, signal_data,
        )

        return {"action": "hold", "reason": sell_reason, "signal": signal_data, "position": position}
