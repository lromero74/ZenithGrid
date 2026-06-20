"""
Telegram Router

Endpoints for managing per-user Telegram notification settings
and receiving Telegram webhook updates (for bot commands).
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import TelegramSettings, User
from app.auth.dependencies import get_current_user
from app.services.telegram_service import (
    get_telegram_settings,
    save_telegram_settings,
    delete_telegram_settings,
    send_telegram_message,
    handle_telegram_command,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TelegramSettingsUpdate(BaseModel):
    bot_token: str
    chat_id: str
    notify_order_filled: bool = True
    notify_position_opened: bool = True
    notify_position_closed: bool = True
    notify_bot_started: bool = True
    notify_bot_stopped: bool = True
    commands_enabled: bool = False


class TelegramSettingsResponse(BaseModel):
    bot_token: str
    chat_id: str
    notify_order_filled: bool
    notify_position_opened: bool
    notify_position_closed: bool
    notify_bot_started: bool
    notify_bot_stopped: bool
    commands_enabled: bool


class TestNotificationRequest(BaseModel):
    bot_token: str
    chat_id: str


class TelegramWebhookUpdate(BaseModel):
    """Telegram webhook payload format (Update object)."""
    update_id: int
    message: Optional[Dict[str, Any]] = None
    callback_query: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Settings CRUD
# ---------------------------------------------------------------------------

@router.get("/settings", response_model=Optional[TelegramSettingsResponse])
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's Telegram notification settings."""
    settings = await get_telegram_settings(db, current_user.id)
    if not settings:
        return None
    return TelegramSettingsResponse(
        bot_token=settings.bot_token,
        chat_id=settings.chat_id,
        notify_order_filled=settings.notify_order_filled,
        notify_position_opened=settings.notify_position_opened,
        notify_position_closed=settings.notify_position_closed,
        notify_bot_started=settings.notify_bot_started,
        notify_bot_stopped=settings.notify_bot_stopped,
        commands_enabled=settings.commands_enabled,
    )


@router.put("/settings", response_model=TelegramSettingsResponse)
async def update_settings(
    update: TelegramSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update Telegram notification settings."""
    settings = await save_telegram_settings(
        db, current_user.id,
        bot_token=update.bot_token,
        chat_id=update.chat_id,
        notify_order_filled=update.notify_order_filled,
        notify_position_opened=update.notify_position_opened,
        notify_position_closed=update.notify_position_closed,
        notify_bot_started=update.notify_bot_started,
        notify_bot_stopped=update.notify_bot_stopped,
        commands_enabled=update.commands_enabled,
    )
    return TelegramSettingsResponse(
        bot_token=settings.bot_token,
        chat_id=settings.chat_id,
        notify_order_filled=settings.notify_order_filled,
        notify_position_opened=settings.notify_position_opened,
        notify_position_closed=settings.notify_position_closed,
        notify_bot_started=settings.notify_bot_started,
        notify_bot_stopped=settings.notify_bot_stopped,
        commands_enabled=settings.commands_enabled,
    )


@router.delete("/settings")
async def remove_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete Telegram notification settings."""
    deleted = await delete_telegram_settings(db, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Telegram settings not found")
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Test notification
# ---------------------------------------------------------------------------

@router.post("/test")
async def send_test_notification(
    request: TestNotificationRequest,
    current_user: User = Depends(get_current_user),
):
    """Send a test notification to verify the Telegram bot token and chat ID."""
    text = (
        "✅ <b>ZenithGrid Telegram Integration</b>\n"
        "Test notification successful! "
        "You will receive trade and bot notifications here."
    )
    success = await send_telegram_message(request.bot_token, request.chat_id, text)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to send test message. Check your bot token and chat ID.",
        )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Telegram webhook (for receiving commands)
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def telegram_webhook(
    update: TelegramWebhookUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Receive Telegram webhook updates and process commands.

    This endpoint is called by Telegram when a user sends a message to the bot.
    The bot token is passed in the URL path by Telegram's webhook configuration,
    but since we configure the webhook URL per-user, we look up the user by
    matching the bot_token from the settings table.
    """
    if not update.message:
        return {"status": "ignored"}

    message = update.message
    text = message.get("text", "")
    chat_id = str(message.get("chat", {}).get("id", ""))

    if not text.startswith("/"):
        return {"status": "ignored"}

    # Find the user by matching the chat_id (each user has unique chat_id)
    # The bot_token is not in the Telegram update payload, so we match by chat_id.
    result = await db.execute(
        select(TelegramSettings).where(
            TelegramSettings.chat_id == chat_id,
            TelegramSettings.commands_enabled.is_(True),
        )
    )
    settings = result.scalars().first()
    if not settings:
        return {"status": "ignored"}

    response_text = await handle_telegram_command(
        settings.bot_token, settings.chat_id, text,
    )

    if response_text:
        await send_telegram_message(settings.bot_token, settings.chat_id, response_text)

    return {"status": "ok"}
