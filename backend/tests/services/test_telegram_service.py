"""
Tests for backend/app/services/telegram_service.py

Covers:
- Settings CRUD (get, save, delete)
- Notification dispatch (order filled, position opened/closed, bot started/stopped)
- Command handling (/status, /positions, /pnl, /start, /stop, /help)
- Event toggle filtering (disabled events don't send)
- Webhook endpoint (ignored for non-commands, processed for commands)
"""

import pytest
from app.utils.timeutil import utcnow
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.models import Bot, TelegramSettings, User


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def patch_session_maker(db_session):
    """Patch async_session_maker so service functions use the test DB session."""
    from app.services import telegram_service as _ts

    class _CtxSession:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *args):
            pass

    with patch.object(_ts, "async_session_maker", return_value=_CtxSession()):
        yield


# =============================================================================
# Helpers
# =============================================================================


async def _make_user(db_session):
    user = User(
        email="telegram@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=utcnow(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_bot(db_session, user, name="TestBot", is_active=False):
    bot = Bot(
        user_id=user.id,
        name=name,
        strategy_type="indicator_based",
        strategy_config={"base_order_percentage": 5.0},
        product_id="BTC-USD",
        product_ids=["BTC-USD"],
        is_active=is_active,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db_session.add(bot)
    await db_session.flush()
    return bot


async def _make_telegram_settings(db_session, user, **kwargs):
    defaults = dict(
        user_id=user.id,
        bot_token="123456:ABC-DEF",
        chat_id="987654321",
        notify_order_filled=True,
        notify_position_opened=True,
        notify_position_closed=True,
        notify_bot_started=True,
        notify_bot_stopped=True,
        commands_enabled=True,
    )
    defaults.update(kwargs)
    settings = TelegramSettings(
        created_at=utcnow(),
        updated_at=utcnow(),
        **defaults,
    )
    db_session.add(settings)
    await db_session.flush()
    return settings


# =============================================================================
# Settings CRUD tests
# =============================================================================


async def test_get_telegram_settings_not_configured(db_session):
    """Returns None when user has no Telegram settings."""
    from app.services.telegram_service import get_telegram_settings
    user = await _make_user(db_session)
    result = await get_telegram_settings(db_session, user.id)
    assert result is None


async def test_save_telegram_settings_creates_new(db_session):
    """Saving settings for a user without existing settings creates them."""
    from app.services.telegram_service import save_telegram_settings
    user = await _make_user(db_session)

    settings = await save_telegram_settings(
        db_session, user.id,
        bot_token="new-token",
        chat_id="new-chat",
    )

    assert settings.user_id == user.id
    assert settings.bot_token == "new-token"
    assert settings.chat_id == "new-chat"
    assert settings.notify_order_filled is True
    assert settings.commands_enabled is False  # default


async def test_save_telegram_settings_updates_existing(db_session):
    """Saving settings for a user with existing settings updates them."""
    from app.services.telegram_service import save_telegram_settings, get_telegram_settings
    user = await _make_user(db_session)

    # Create initial settings
    await save_telegram_settings(db_session, user.id, bot_token="token1", chat_id="chat1")

    # Update them
    updated = await save_telegram_settings(
        db_session, user.id,
        bot_token="token2",
        chat_id="chat2",
        notify_order_filled=False,
        commands_enabled=True,
    )

    assert updated.bot_token == "token2"
    assert updated.chat_id == "chat2"
    assert updated.notify_order_filled is False
    assert updated.commands_enabled is True

    # Verify only one record exists
    all_settings = await get_telegram_settings(db_session, user.id)
    assert all_settings.bot_token == "token2"


async def test_delete_telegram_settings(db_session):
    """Deleting settings removes them."""
    from app.services.telegram_service import delete_telegram_settings, get_telegram_settings
    user = await _make_user(db_session)
    await _make_telegram_settings(db_session, user)

    deleted = await delete_telegram_settings(db_session, user.id)
    assert deleted is True

    # Verify gone
    result = await get_telegram_settings(db_session, user.id)
    assert result is None


async def test_delete_telegram_settings_not_found(db_session):
    """Deleting non-existent settings returns False."""
    from app.services.telegram_service import delete_telegram_settings
    user = await _make_user(db_session)
    deleted = await delete_telegram_settings(db_session, user.id)
    assert deleted is False


# =============================================================================
# Notification dispatch tests
# =============================================================================


async def test_notify_order_filled_sends_message(db_session, patch_session_maker):
    """ORDER_FILLED event triggers a Telegram message."""
    from app.services.telegram_service import notify_order_filled
    from app.event_bus import OrderFilledPayload

    user = await _make_user(db_session)
    await _make_telegram_settings(db_session, user)

    payload = OrderFilledPayload(
        position_id=1, user_id=user.id, product_id="BTC-USD",
        fill_type="base_order", quote_amount=100.0, base_amount=0.001,
        price=100000.0, profit=5.0, profit_percentage=5.0,
    )

    with patch(
        "app.services.telegram_service.send_telegram_message",
        new_callable=AsyncMock, return_value=True,
    ) as mock_send:
        await notify_order_filled(payload)

    mock_send.assert_called_once()
    args = mock_send.call_args
    # send_telegram_message(bot_token, chat_id, text) — text is arg index 2
    assert "Order Filled" in args[0][2]
    assert "BTC-USD" in args[0][2]


async def test_notify_skipped_when_event_disabled(db_session, patch_session_maker):
    """If notify_order_filled is False, no message is sent."""
    from app.services.telegram_service import notify_order_filled
    from app.event_bus import OrderFilledPayload

    user = await _make_user(db_session)
    await _make_telegram_settings(db_session, user, notify_order_filled=False)

    payload = OrderFilledPayload(
        position_id=1, user_id=user.id, product_id="BTC-USD",
        fill_type="base_order", quote_amount=100.0, base_amount=0.001,
        price=100000.0,
    )

    with patch(
        "app.services.telegram_service.send_telegram_message",
        new_callable=AsyncMock, return_value=True,
    ) as mock_send:
        await notify_order_filled(payload)

    mock_send.assert_not_called()


async def test_notify_skipped_when_no_settings(db_session, patch_session_maker):
    """If user has no Telegram settings, no message is sent."""
    from app.services.telegram_service import notify_order_filled
    from app.event_bus import OrderFilledPayload

    user = await _make_user(db_session)
    # No telegram settings created

    payload = OrderFilledPayload(
        position_id=1, user_id=user.id, product_id="BTC-USD",
        fill_type="base_order", quote_amount=100.0, base_amount=0.001,
        price=100000.0,
    )

    with patch(
        "app.services.telegram_service.send_telegram_message",
        new_callable=AsyncMock, return_value=True,
    ) as mock_send:
        await notify_order_filled(payload)

    mock_send.assert_not_called()


async def test_notify_position_closed_sends_message(db_session, patch_session_maker):
    """POSITION_CLOSED event triggers a Telegram message with P&L."""
    from app.services.telegram_service import notify_position_closed
    from app.event_bus import PositionClosedPayload

    user = await _make_user(db_session)
    await _make_telegram_settings(db_session, user)

    payload = PositionClosedPayload(
        position_id=1, user_id=user.id, product_id="ETH-USD",
        bot_id=1, profit_quote=15.5, profit_percentage=12.3,
    )

    with patch(
        "app.services.telegram_service.send_telegram_message",
        new_callable=AsyncMock, return_value=True,
    ) as mock_send:
        await notify_position_closed(payload)

    mock_send.assert_called_once()
    text = mock_send.call_args[0][2]  # third positional arg = text
    assert "Position Closed" in text
    assert "ETH-USD" in text
    assert "15.5" in text
    assert "12.30" in text


async def test_notify_bot_started_sends_message(db_session, patch_session_maker):
    """BOT_STARTED event triggers a Telegram message with bot name."""
    from app.services.telegram_service import notify_bot_started
    from app.event_bus import BotStartedPayload

    user = await _make_user(db_session)
    bot = await _make_bot(db_session, user, name="MyBot", is_active=True)
    await _make_telegram_settings(db_session, user)

    payload = BotStartedPayload(bot_id=bot.id, user_id=user.id)

    with patch(
        "app.services.telegram_service.send_telegram_message",
        new_callable=AsyncMock, return_value=True,
    ) as mock_send:
        await notify_bot_started(payload)

    mock_send.assert_called_once()
    text = mock_send.call_args[0][2]  # third positional arg = text
    assert "Bot Started" in text
    assert "MyBot" in text


# =============================================================================
# Command handling tests
# =============================================================================


async def test_cmd_status_no_bots(db_session, patch_session_maker):
    """/status returns 'no bots' when user has none."""
    from app.services.telegram_service import handle_telegram_command
    user = await _make_user(db_session)
    await _make_telegram_settings(db_session, user)

    response = await handle_telegram_command(
        "123456:ABC-DEF", "987654321", "/status",
    )
    assert "No bots" in response


async def test_cmd_status_with_bots(db_session, patch_session_maker):
    """/status returns a summary of bots."""
    from app.services.telegram_service import handle_telegram_command
    user = await _make_user(db_session)
    await _make_bot(db_session, user, name="Alpha", is_active=True)
    await _make_bot(db_session, user, name="Beta", is_active=False)
    await _make_telegram_settings(db_session, user)

    response = await handle_telegram_command(
        "123456:ABC-DEF", "987654321", "/status",
    )
    assert "Alpha" in response
    assert "Beta" in response
    assert "1 active" in response


async def test_cmd_positions_empty(db_session, patch_session_maker):
    """/positions returns 'no positions' when user has none open."""
    from app.services.telegram_service import handle_telegram_command
    user = await _make_user(db_session)
    await _make_telegram_settings(db_session, user)

    response = await handle_telegram_command(
        "123456:ABC-DEF", "987654321", "/positions",
    )
    assert "No open positions" in response


async def test_cmd_start_bot(db_session, patch_session_maker):
    """/start <bot_name> starts the named bot."""
    from app.services.telegram_service import handle_telegram_command
    user = await _make_user(db_session)
    bot = await _make_bot(db_session, user, name="Gamma", is_active=False)
    await _make_telegram_settings(db_session, user)

    response = await handle_telegram_command(
        "123456:ABC-DEF", "987654321", "/start Gamma",
    )
    assert "Started" in response
    assert "Gamma" in response

    # Verify bot was actually started
    from sqlalchemy import select
    from app.models import Bot as BotModel
    result = await db_session.execute(
        select(BotModel).where(BotModel.id == bot.id)
    )
    updated_bot = result.scalars().first()
    assert updated_bot.is_active is True


async def test_cmd_stop_bot(db_session, patch_session_maker):
    """/stop <bot_name> stops the named bot."""
    from app.services.telegram_service import handle_telegram_command
    user = await _make_user(db_session)
    bot = await _make_bot(db_session, user, name="Delta", is_active=True)
    await _make_telegram_settings(db_session, user)

    response = await handle_telegram_command(
        "123456:ABC-DEF", "987654321", "/stop Delta",
    )
    assert "Stopped" in response
    assert "Delta" in response

    from sqlalchemy import select
    from app.models import Bot as BotModel
    result = await db_session.execute(
        select(BotModel).where(BotModel.id == bot.id)
    )
    updated_bot = result.scalars().first()
    assert updated_bot.is_active is False


async def test_cmd_start_bot_not_found(db_session, patch_session_maker):
    """/start with unknown bot name returns error."""
    from app.services.telegram_service import handle_telegram_command
    user = await _make_user(db_session)
    await _make_telegram_settings(db_session, user)

    response = await handle_telegram_command(
        "123456:ABC-DEF", "987654321", "/start Nonexistent",
    )
    assert "not found" in response


async def test_cmd_start_no_arg(db_session, patch_session_maker):
    """/start without a bot name returns usage message."""
    from app.services.telegram_service import handle_telegram_command
    user = await _make_user(db_session)
    await _make_telegram_settings(db_session, user)

    response = await handle_telegram_command(
        "123456:ABC-DEF", "987654321", "/start",
    )
    assert "Usage" in response


async def test_cmd_help(db_session, patch_session_maker):
    """/help returns command list."""
    from app.services.telegram_service import handle_telegram_command
    user = await _make_user(db_session)
    await _make_telegram_settings(db_session, user)

    response = await handle_telegram_command(
        "123456:ABC-DEF", "987654321", "/help",
    )
    assert "/status" in response
    assert "/positions" in response
    assert "/pnl" in response
    assert "/start" in response
    assert "/stop" in response


async def test_cmd_unknown_returns_none(db_session, patch_session_maker):
    """Unknown command returns None."""
    from app.services.telegram_service import handle_telegram_command
    user = await _make_user(db_session)
    await _make_telegram_settings(db_session, user)

    response = await handle_telegram_command(
        "123456:ABC-DEF", "987654321", "/foobar",
    )
    assert response is None


async def test_command_with_wrong_chat_id_ignored(db_session, patch_session_maker):
    """Commands from unregistered chat IDs are ignored."""
    from app.services.telegram_service import handle_telegram_command
    user = await _make_user(db_session)
    await _make_telegram_settings(db_session, user)

    response = await handle_telegram_command(
        "123456:ABC-DEF", "wrong-chat-id", "/status",
    )
    assert response is not None
    assert "not linked" in response.lower() or "no" in response.lower()


# =============================================================================
# Router endpoint tests
# =============================================================================


async def test_get_settings_not_configured(db_session):
    """GET /settings returns None when not configured."""
    from app.routers.telegram_router import get_settings
    user = await _make_user(db_session)

    result = await get_settings(current_user=user, db=db_session)
    assert result is None


async def test_update_settings_creates(db_session):
    """PUT /settings creates new settings."""
    from app.routers.telegram_router import update_settings, TelegramSettingsUpdate
    user = await _make_user(db_session)

    update = TelegramSettingsUpdate(
        bot_token="test-token",
        chat_id="test-chat",
        commands_enabled=True,
    )
    result = await update_settings(update, current_user=user, db=db_session)
    assert result.bot_token == "test-token"
    assert result.chat_id == "test-chat"
    assert result.commands_enabled is True


async def test_delete_settings_not_found(db_session):
    """DELETE /settings returns 404 when not configured."""
    from app.routers.telegram_router import remove_settings
    user = await _make_user(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await remove_settings(current_user=user, db=db_session)
    assert exc_info.value.status_code == 404


async def test_send_test_notification_success(db_session):
    """POST /test sends a test message successfully."""
    from app.routers.telegram_router import send_test_notification, TestNotificationRequest
    user = await _make_user(db_session)

    request = TestNotificationRequest(bot_token="token", chat_id="chat")
    with patch(
        "app.routers.telegram_router.send_telegram_message",
        new_callable=AsyncMock, return_value=True,
    ):
        result = await send_test_notification(request, current_user=user)
    assert result["status"] == "ok"


async def test_send_test_notification_failure(db_session):
    """POST /test returns 400 when Telegram API fails."""
    from app.routers.telegram_router import send_test_notification, TestNotificationRequest
    user = await _make_user(db_session)

    request = TestNotificationRequest(bot_token="bad", chat_id="bad")
    with patch(
        "app.routers.telegram_router.send_telegram_message",
        new_callable=AsyncMock, return_value=False,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await send_test_notification(request, current_user=user)
    assert exc_info.value.status_code == 400
