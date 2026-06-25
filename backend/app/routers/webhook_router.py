"""
TradingView Webhook Router

Accepts TradingView alert webhooks authenticated by per-bot webhook tokens.
Translates incoming alert JSON into trade actions via the existing
signal_processor pipeline.

TradingView alert JSON format (user-customizable in TradingView):
    {
        "token": "<bot webhook token>",
        "side": "buy" | "sell",
        "symbol": "BTC-USDT",
        "price": 100000.0,       // optional
        "quantity": 0.01,         // optional
        "message": "Custom text"  // optional, ignored
    }

The router looks up the bot by token, verifies the bot is active,
fetches candles + current price, builds a pre-analyzed signal, and
feeds it through process_signal() — the same pipeline the monitor
uses on every cycle.
"""

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# ---------------------------------------------------------------------------
# Rate limiting (in-process, per-token)
# ---------------------------------------------------------------------------

_MAX_REQUESTS_PER_MINUTE = 10            # per bot webhook token
_MAX_REQUESTS_PER_MINUTE_PER_IP = 30    # per source IP (bounds token scanning)
_rate_limit_store: dict[str, list[float]] = {}     # token -> [timestamps]
_ip_rate_limit_store: dict[str, list[float]] = {}  # ip -> [timestamps]


def _within_limit(store: dict[str, list[float]], key: str, limit: int) -> bool:
    """Sliding-window (1 min) limiter. Returns True if allowed (recording the
    hit), False if the key is over its limit."""
    now = time.time()
    cutoff = now - 60.0
    # Bound the store: token/IP scanning would otherwise grow it without limit.
    # When it gets large, evict keys whose entire window has expired.
    if len(store) > 5000:
        for _k in [k for k, ts in list(store.items()) if all(t <= cutoff for t in ts)]:
            del store[_k]
    timestamps = [ts for ts in store.get(key, []) if ts > cutoff]
    if len(timestamps) >= limit:
        store[key] = timestamps
        return False
    timestamps.append(now)
    store[key] = timestamps
    return True


def _check_rate_limit(token: str) -> bool:
    """Per-token rate limit. Return True if allowed, False if rate-limited."""
    return _within_limit(_rate_limit_store, token, _MAX_REQUESTS_PER_MINUTE)


def _check_ip_rate_limit(ip: str) -> bool:
    """Per-IP rate limit — caps how fast a single source can probe tokens.
    Without it the per-token limit lets one caller scan many tokens unbounded."""
    return _within_limit(_ip_rate_limit_store, ip, _MAX_REQUESTS_PER_MINUTE_PER_IP)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TradingViewAlert(BaseModel):
    """TradingView webhook alert payload.

    The user configures this JSON in their TradingView alert settings.
    The only required fields are `token` and `side`. `symbol` is optional
    (defaults to the bot's first trading pair).
    """
    token: str
    side: str  # "buy" or "sell"
    symbol: Optional[str] = None  # Trading pair, e.g. "BTC-USDT"
    price: Optional[float] = None  # Optional price from alert
    quantity: Optional[float] = None  # Optional quantity (informational)
    message: Optional[str] = None  # Optional free-text from TradingView


class WebhookResponse(BaseModel):
    status: str
    action: str = "none"
    reason: str = ""


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@router.post("/tradingview", response_model=WebhookResponse)
async def tradingview_webhook(
    alert: TradingViewAlert,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    """Process a TradingView alert webhook.

    Authenticated by the per-bot webhook token in the payload (no JWT).
    The bot must be active and have a configured webhook_token.
    """
    # 1. Rate limit — per source IP first (bounds token scanning), then per token.
    client_ip = request.client.host if (request and request.client) else None
    if client_ip and not _check_ip_rate_limit(client_ip):
        logger.warning(f"Webhook IP rate-limited: {client_ip}")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    if not _check_rate_limit(alert.token):
        logger.warning(f"Webhook rate-limited for token prefix {alert.token[:8]}...")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # 2. Look up bot by webhook token
    result = await db.execute(
        select(Bot).where(Bot.webhook_token == alert.token)
    )
    bot = result.scalars().first()
    if not bot:
        logger.warning(f"Webhook rejected: unknown token prefix {alert.token[:8]}...")
        raise HTTPException(status_code=404, detail="Not found")

    logger.info(f"Webhook received for bot '{bot.name}' (id={bot.id}): side={alert.side}")

    # 3. Verify bot is active
    if not bot.is_active:
        logger.info(f"Webhook for stopped bot '{bot.name}' — rejected")
        return WebhookResponse(
            status="rejected",
            action="none",
            reason="Bot is not active",
        )

    # 4. Resolve the trading pair
    product_id = alert.symbol or bot.get_trading_pairs()[0]
    # Normalize: TradingView uses spaces or no separator; we use dashes
    product_id = product_id.replace(" ", "-").replace("/", "-").upper()

    # Validate the product is in the bot's configured pairs (or allow if single-pair)
    bot_pairs = bot.get_trading_pairs()
    if bot_pairs and product_id not in bot_pairs:
        logger.warning(
            f"Webhook symbol {product_id} not in bot '{bot.name}' pairs {bot_pairs}"
        )
        return WebhookResponse(
            status="rejected",
            action="none",
            reason=f"Symbol {product_id} not configured on this bot",
        )

    # 5. Build exchange client + strategy + engine, then run process_signal
    from app.services.exchange_service import get_exchange_client_for_account
    from app.strategies import StrategyRegistry
    from app.trading_engine_v2 import StrategyTradingEngine

    exchange = await get_exchange_client_for_account(db, bot.account_id)
    if not exchange:
        logger.error(f"No exchange client for account {bot.account_id}")
        return WebhookResponse(
            status="error",
            action="none",
            reason="Exchange client unavailable",
        )

    strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)

    # Fetch current price
    try:
        current_price = alert.price or await exchange.get_current_price(product_id)
    except Exception as e:
        logger.error(f"Webhook: failed to get price for {product_id}: {e}")
        return WebhookResponse(
            status="error",
            action="none",
            reason=f"Price fetch failed: {e}",
        )

    # Fetch candles for the strategy (same as the monitor loop does)
    import time as _time
    end = int(_time.time())
    start = end - 3600  # 1 hour of candles
    candles: list[dict[str, Any]] = []
    try:
        candles = await exchange.get_candles(product_id, start, end, "FIVE_MINUTE")
    except Exception as e:
        logger.warning(f"Webhook: failed to fetch candles for {product_id}: {e}")

    # 6. Build pre-analyzed signal from the webhook alert
    side_lower = alert.side.lower().strip()
    signal_data: dict[str, Any] = {
        "signal_type": side_lower,  # "buy" or "sell"
        "confidence": 100,  # Webhook signals are explicit — full confidence
        "reasoning": f"TradingView webhook: {alert.message or side_lower}",
        "indicators": {},
        "_already_logged": True,  # Skip AI log — this is a webhook, not an AI decision
    }

    # 7. Run through the signal processor
    engine = StrategyTradingEngine(
        db=db, exchange=exchange, bot=bot, strategy=strategy, product_id=product_id,
    )

    try:
        result = await engine.process_signal(
            candles=candles,
            current_price=current_price,
            pre_analyzed_signal=signal_data,
        )
    except Exception as e:
        logger.error(f"Webhook: process_signal failed for bot '{bot.name}': {e}", exc_info=True)
        return WebhookResponse(
            status="error",
            action="none",
            reason=f"Signal processing failed: {e}",
        )

    action = result.get("action", "none")
    reason = result.get("reason", "")
    logger.info(f"Webhook result for bot '{bot.name}': action={action}, reason={reason}")

    return WebhookResponse(
        status="ok",
        action=action,
        reason=reason,
    )
