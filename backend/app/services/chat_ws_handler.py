"""
Chat WebSocket message handler.

Routes chat:* messages for real-time messaging, typing indicators,
read receipts, and message editing/deletion.
"""

import logging
import time

from fastapi import WebSocket

from app.database import async_session_maker
from app.services import chat_service

logger = logging.getLogger(__name__)

# Typing indicator cooldown per user per channel (seconds)
_typing_cooldowns: dict[tuple[int, int], float] = {}
TYPING_COOLDOWN_SECONDS = 2.0


async def handle_chat_message(
    ws_manager, websocket: WebSocket, user_id: int, msg: dict,
    display_name: str | None = None,
):
    """Route a chat:* message to the appropriate handler."""
    msg_type = msg.get("type", "")
    handlers = {
        "chat:send": _handle_send,
        "chat:typing": _handle_typing,
        "chat:read": _handle_read,
        "chat:edit": _handle_edit,
        "chat:delete": _handle_delete,
    }

    handler = handlers.get(msg_type)
    if not handler:
        await websocket.send_json({
            "type": "chat:error",
            "error": f"Unknown chat message type: {msg_type}",
        })
        return

    try:
        await handler(ws_manager, websocket, user_id, msg, display_name or f"User {user_id}")
    except ValueError as e:
        await websocket.send_json({"type": "chat:error", "error": str(e)})
    except Exception as e:
        logger.error(f"Chat message error: {e}", exc_info=True)
        await websocket.send_json({"type": "chat:error", "error": "Internal error"})


async def _handle_send(ws_manager, websocket, user_id, msg, display_name):
    """Handle chat:send — persist message and broadcast to channel members."""
    channel_id = msg.get("channelId")
    content = msg.get("content", "")

    if not channel_id:
        await websocket.send_json({"type": "chat:error", "error": "channelId required"})
        return

    async with async_session_maker() as db:
        message_data = await chat_service.send_message(db, channel_id, user_id, content)
        member_ids = await chat_service.get_channel_member_ids(db, channel_id)

    # Broadcast to all channel members (including sender for confirmation)
    broadcast = {
        "type": "chat:message",
        **message_data,
    }
    for mid in member_ids:
        await ws_manager.send_to_user(mid, broadcast)


async def _handle_typing(ws_manager, websocket, user_id, msg, display_name):
    """Handle chat:typing — broadcast typing indicator to other channel members."""
    channel_id = msg.get("channelId")
    if not channel_id:
        return

    # Debounce: skip if we sent typing for this channel recently
    key = (user_id, channel_id)
    now = time.monotonic()
    last = _typing_cooldowns.get(key, 0)
    if now - last < TYPING_COOLDOWN_SECONDS:
        return
    _typing_cooldowns[key] = now

    async with async_session_maker() as db:
        member_ids = await chat_service.get_channel_member_ids(db, channel_id)

    broadcast = {
        "type": "chat:typing",
        "channelId": channel_id,
        "userId": user_id,
        "displayName": display_name,
    }
    for mid in member_ids:
        if mid != user_id:
            await ws_manager.send_to_user(mid, broadcast)


async def _handle_read(ws_manager, websocket, user_id, msg, display_name):
    """Handle chat:read — mark channel as read and broadcast receipt."""
    channel_id = msg.get("channelId")
    if not channel_id:
        return

    async with async_session_maker() as db:
        await chat_service.mark_read(db, channel_id, user_id)
        member_ids = await chat_service.get_channel_member_ids(db, channel_id)

    broadcast = {
        "type": "chat:read_receipt",
        "channelId": channel_id,
        "userId": user_id,
    }
    for mid in member_ids:
        if mid != user_id:
            await ws_manager.send_to_user(mid, broadcast)


async def _handle_edit(ws_manager, websocket, user_id, msg, display_name):
    """Handle chat:edit — edit a message and broadcast update."""
    message_id = msg.get("messageId")
    content = msg.get("content", "")

    if not message_id:
        await websocket.send_json({"type": "chat:error", "error": "messageId required"})
        return

    async with async_session_maker() as db:
        message_data = await chat_service.edit_message(db, message_id, user_id, content)
        member_ids = await chat_service.get_channel_member_ids(db, message_data["channel_id"])

    broadcast = {
        "type": "chat:message_edited",
        **message_data,
    }
    for mid in member_ids:
        await ws_manager.send_to_user(mid, broadcast)


async def _handle_delete(ws_manager, websocket, user_id, msg, display_name):
    """Handle chat:delete — soft-delete a message and broadcast."""
    message_id = msg.get("messageId")
    if not message_id:
        await websocket.send_json({"type": "chat:error", "error": "messageId required"})
        return

    async with async_session_maker() as db:
        result = await chat_service.delete_message(db, message_id, user_id)
        member_ids = await chat_service.get_channel_member_ids(db, result["channel_id"])

    broadcast = {
        "type": "chat:message_deleted",
        "messageId": result["id"],
        "channelId": result["channel_id"],
    }
    for mid in member_ids:
        await ws_manager.send_to_user(mid, broadcast)
