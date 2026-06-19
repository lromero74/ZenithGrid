"""
Telegram Notification Service

Sends trade and bot notifications via the Telegram Bot API.
Handles commands received from Telegram webhooks.

Event bus integration:
- ORDER_FILLED: sends a message with trade details
- POSITION_OPENED: sends a message when a new position is created
- POSITION_CLOSED: sends a message with P&L when a position closes
- BOT_STARTED: sends a message when a bot starts
- BOT_STOPPED: sends a message when a bot stops

Command handling (via Telegram webhook):
- /status: summary of all bots
- /positions: open positions
- /pnl: today's P&L
- /start <bot_name>: start a bot
- /stop <bot_name>: stop a bot
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import Bot, Position, TelegramSettings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Telegram Bot API client
# ---------------------------------------------------------------------------

async def send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
) -> bool:
    """Send a message via the Telegram Bot API.

    Returns True on success, False on failure.
    """
    import aiohttp

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"Telegram API error {resp.status}: {body[:200]}")
                    return False
                return True
    except Exception as e:
        logger.warning(f"Telegram message send failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

async def get_telegram_settings(db: AsyncSession, user_id: int) -> Optional[TelegramSettings]:
    """Get a user's Telegram settings, or None if not configured."""
    result = await db.execute(
        select(TelegramSettings).where(TelegramSettings.user_id == user_id)
    )
    return result.scalars().first()


async def save_telegram_settings(
    db: AsyncSession,
    user_id: int,
    bot_token: str,
    chat_id: str,
    notify_order_filled: bool = True,
    notify_position_opened: bool = True,
    notify_position_closed: bool = True,
    notify_bot_started: bool = True,
    notify_bot_stopped: bool = True,
    commands_enabled: bool = False,
) -> TelegramSettings:
    """Create or update a user's Telegram settings."""
    existing = await get_telegram_settings(db, user_id)
    if existing:
        existing.bot_token = bot_token
        existing.chat_id = chat_id
        existing.notify_order_filled = notify_order_filled
        existing.notify_position_opened = notify_position_opened
        existing.notify_position_closed = notify_position_closed
        existing.notify_bot_started = notify_bot_started
        existing.notify_bot_stopped = notify_bot_stopped
        existing.commands_enabled = commands_enabled
        await db.commit()
        await db.refresh(existing)
        return existing

    settings = TelegramSettings(
        user_id=user_id,
        bot_token=bot_token,
        chat_id=chat_id,
        notify_order_filled=notify_order_filled,
        notify_position_opened=notify_position_opened,
        notify_position_closed=notify_position_closed,
        notify_bot_started=notify_bot_started,
        notify_bot_stopped=notify_bot_stopped,
        commands_enabled=commands_enabled,
    )
    db.add(settings)
    await db.commit()
    await db.refresh(settings)
    return settings


async def delete_telegram_settings(db: AsyncSession, user_id: int) -> bool:
    """Delete a user's Telegram settings. Returns True if deleted."""
    existing = await get_telegram_settings(db, user_id)
    if not existing:
        return False
    await db.delete(existing)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Notification dispatch
# ---------------------------------------------------------------------------

async def _notify_user(user_id: int, text: str, event_type: str) -> None:
    """Send a notification to a user if they have Telegram configured and the
    event type is enabled."""
    async with async_session_maker() as db:
        settings = await get_telegram_settings(db, user_id)
        if not settings:
            return

        # Check if this event type is enabled
        enabled_map = {
            "order_filled": settings.notify_order_filled,
            "position_opened": settings.notify_position_opened,
            "position_closed": settings.notify_position_closed,
            "bot_started": settings.notify_bot_started,
            "bot_stopped": settings.notify_bot_stopped,
        }
        if not enabled_map.get(event_type, True):
            return

        await send_telegram_message(settings.bot_token, settings.chat_id, text)


async def notify_order_filled(payload) -> None:
    """Event bus handler for ORDER_FILLED events."""

    profit_text = ""
    if payload.profit is not None and payload.profit_percentage is not None:
        profit_text = f" | P&L: {payload.profit:.4f} ({payload.profit_percentage:.2f}%)"

    paper_tag = " [PAPER]" if payload.is_paper_trading else ""
    text = (
        f"📊 <b>Order Filled</b>{paper_tag}\n"
        f"Pair: {payload.product_id}\n"
        f"Type: {payload.fill_type}\n"
        f"Amount: {payload.quote_amount:.4f} @ {payload.price:.4f}"
        f"{profit_text}"
    )
    await _notify_user(payload.user_id, text, "order_filled")


async def notify_position_opened(payload) -> None:
    """Event bus handler for POSITION_OPENED events."""
    text = (
        f"🟢 <b>Position Opened</b>\n"
        f"Pair: {payload.product_id}\n"
        f"Amount: {payload.quote_amount:.4f}"
    )
    await _notify_user(payload.user_id, text, "position_opened")


async def notify_position_closed(payload) -> None:
    """Event bus handler for POSITION_CLOSED events."""
    profit_text = ""
    if payload.profit_quote is not None and payload.profit_percentage is not None:
        emoji = "✅" if payload.profit_quote >= 0 else "❌"
        profit_text = f"\n{emoji} P&L: {payload.profit_quote:.4f} ({payload.profit_percentage:.2f}%)"

    text = (
        f"🔴 <b>Position Closed</b>\n"
        f"Pair: {payload.product_id}"
        f"{profit_text}"
    )
    await _notify_user(payload.user_id, text, "position_closed")


async def notify_bot_started(payload) -> None:
    """Event bus handler for BOT_STARTED events."""
    async with async_session_maker() as db:
        bot_result = await db.execute(select(Bot).where(Bot.id == payload.bot_id))
        bot = bot_result.scalars().first()
        bot_name = bot.name if bot else f"Bot #{payload.bot_id}"

    text = f"▶️ <b>Bot Started</b>\nName: {bot_name}"
    await _notify_user(payload.user_id, text, "bot_started")


async def notify_bot_stopped(payload) -> None:
    """Event bus handler for BOT_STOPPED events."""
    async with async_session_maker() as db:
        bot_result = await db.execute(select(Bot).where(Bot.id == payload.bot_id))
        bot = bot_result.scalars().first()
        bot_name = bot.name if bot else f"Bot #{payload.bot_id}"

    text = f"⏹️ <b>Bot Stopped</b>\nName: {bot_name}"
    await _notify_user(payload.user_id, text, "bot_stopped")


# ---------------------------------------------------------------------------
# Command handling
# ---------------------------------------------------------------------------

async def handle_telegram_command(
    bot_token: str,
    chat_id: str,
    text: str,
) -> Optional[str]:
    """Process a Telegram command and return the response text.

    Returns None if the command is not recognized.
    """
    parts = text.strip().split(maxsplit=1)
    command = parts[0].lower() if parts else ""
    arg = parts[1].strip() if len(parts) > 1 else ""

    # Look up the user by their Telegram settings
    async with async_session_maker() as db:
        settings_result = await db.execute(
            select(TelegramSettings).where(
                TelegramSettings.bot_token == bot_token,
                TelegramSettings.chat_id == chat_id,
            )
        )
        settings = settings_result.scalars().first()
        if not settings:
            return "❌ No ZenithGrid account linked to this Telegram bot."

        user_id = settings.user_id

        if command == "/status":
            return await _cmd_status(db, user_id)
        elif command == "/positions":
            return await _cmd_positions(db, user_id)
        elif command == "/pnl":
            return await _cmd_pnl(db, user_id)
        elif command == "/start":
            return await _cmd_start_bot(db, user_id, arg)
        elif command == "/stop":
            return await _cmd_stop_bot(db, user_id, arg)
        elif command == "/help":
            return (
                "ZenithGrid Bot Commands:\n"
                "/status — Summary of all bots\n"
                "/positions — Open positions\n"
                "/pnl — Today's P&L\n"
                "/start <bot_name> — Start a bot\n"
                "/stop <bot_name> — Stop a bot\n"
                "/help — Show this help"
            )
        else:
            return None


async def _cmd_status(db: AsyncSession, user_id: int) -> str:
    """Return a summary of all the user's bots."""
    result = await db.execute(
        select(Bot).where(Bot.user_id == user_id)
    )
    bots = result.scalars().all()

    if not bots:
        return "No bots configured."

    active = sum(1 for b in bots if b.is_active)
    lines = [f"🤖 <b>Bots: {len(bots)}</b> ({active} active)"]
    for bot in bots:
        status = "▶️" if bot.is_active else "⏹️"
        pairs = ", ".join(bot.get_trading_pairs()[:3])
        lines.append(f"{status} {bot.name} [{pairs}]")
    return "\n".join(lines)


async def _cmd_positions(db: AsyncSession, user_id: int) -> str:
    """Return the user's open positions."""
    result = await db.execute(
        select(Position).where(
            Position.user_id == user_id,
            Position.status == "open",
        )
    )
    positions = result.scalars().all()

    if not positions:
        return "No open positions."

    lines = [f"📂 <b>Open Positions: {len(positions)}</b>"]
    for pos in positions[:10]:
        profit_text = ""
        if pos.profit_percentage is not None:
            profit_text = f" ({pos.profit_percentage:.2f}%)"
        lines.append(f"  {pos.product_id} — {pos.total_quote_spent:.4f}{profit_text}")
    if len(positions) > 10:
        lines.append(f"  ... and {len(positions) - 10} more")
    return "\n".join(lines)


async def _cmd_pnl(db: AsyncSession, user_id: int) -> str:
    """Return today's P&L summary."""
    from app.utils.timeutil import utcnow

    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(Position).where(
            Position.user_id == user_id,
            Position.status == "closed",
            Position.closed_at >= today_start,
        )
    )
    closed_today = result.scalars().all()

    total_profit = sum(p.profit_quote or 0.0 for p in closed_today)
    wins = sum(1 for p in closed_today if (p.profit_quote or 0) > 0)
    losses = len(closed_today) - wins

    return (
        f"💰 <b>Today's P&L</b>\n"
        f"Closed: {len(closed_today)} ({wins}W / {losses}L)\n"
        f"Profit: {total_profit:.4f}"
    )


async def _cmd_start_bot(db: AsyncSession, user_id: int, bot_name: str) -> str:
    """Start a bot by name."""
    if not bot_name:
        return "Usage: /start <bot_name>"

    result = await db.execute(
        select(Bot).where(Bot.user_id == user_id, Bot.name == bot_name)
    )
    bot = result.scalars().first()
    if not bot:
        return f"❌ Bot '{bot_name}' not found."

    if bot.is_active:
        return f"⏭️ '{bot_name}' is already running."

    bot.is_active = True
    from app.utils.timeutil import utcnow
    bot.last_started_at = utcnow()
    await db.commit()

    return f"▶️ Started '{bot_name}'"


async def _cmd_stop_bot(db: AsyncSession, user_id: int, bot_name: str) -> str:
    """Stop a bot by name."""
    if not bot_name:
        return "Usage: /stop <bot_name>"

    result = await db.execute(
        select(Bot).where(Bot.user_id == user_id, Bot.name == bot_name)
    )
    bot = result.scalars().first()
    if not bot:
        return f"❌ Bot '{bot_name}' not found."

    if not bot.is_active:
        return f"⏭️ '{bot_name}' is already stopped."

    bot.is_active = False
    await db.commit()

    return f"⏹️ Stopped '{bot_name}'"
