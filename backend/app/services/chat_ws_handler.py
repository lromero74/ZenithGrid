"""
Chat WebSocket message handler.

Routes chat:* messages for real-time messaging, typing indicators,
read receipts, and message editing/deletion.

All chat:* actions require the 'social:chat' permission (W1 RBAC enforcement).
"""

import asyncio
import logging
import time

from fastapi import WebSocket

from app.database import async_session_maker
from app.services import chat_service

logger = logging.getLogger(__name__)

CHAT_PERMISSION = "social:chat"

# Typing indicator cooldown per user per channel (seconds)
_typing_cooldowns: dict[tuple[int, int], float] = {}
TYPING_COOLDOWN_SECONDS = 2.0
_TYPING_STALE_SECONDS = 30.0  # Prune entries older than this

# Send rate limiting — max messages per window per user (W3)
_send_timestamps: dict[int, list[float]] = {}
_SEND_RATE_MAX = 10  # max messages
_SEND_RATE_WINDOW = 5.0  # per 5 seconds
_SEND_STALE_SECONDS = 30.0  # Prune user entries older than this


def _prune_typing_cooldowns() -> None:
    """Remove stale entries from the typing cooldown dict to prevent unbounded growth."""
    if not _typing_cooldowns:
        return
    now = time.monotonic()
    stale_keys = [k for k, v in _typing_cooldowns.items()
                  if now - v > _TYPING_STALE_SECONDS]
    for k in stale_keys:
        del _typing_cooldowns[k]


def _check_send_rate(user_id: int) -> bool:
    """Check if user is within send rate limit. Returns True if allowed, False if throttled."""
    now = time.monotonic()
    timestamps = _send_timestamps.get(user_id)
    if timestamps is None:
        _send_timestamps[user_id] = [now]
        return True

    # Prune old timestamps
    cutoff = now - _SEND_RATE_WINDOW
    timestamps[:] = [t for t in timestamps if t > cutoff]

    if len(timestamps) >= _SEND_RATE_MAX:
        return False

    timestamps.append(now)
    return True


def _prune_send_timestamps() -> None:
    """Remove stale user entries from the send rate limit dict."""
    if not _send_timestamps:
        return
    now = time.monotonic()
    stale_users = [uid for uid, ts in _send_timestamps.items()
                   if not ts or now - ts[-1] > _SEND_STALE_SECONDS]
    for uid in stale_users:
        del _send_timestamps[uid]


def prune_all_stale() -> None:
    """Prune all stale rate-limiting entries. Called periodically by cleanup job."""
    _prune_typing_cooldowns()
    _prune_send_timestamps()


def _parse_int_field(msg: dict, field: str) -> int | None:
    """Safely extract an integer field from a WS message dict. Returns None on invalid type."""
    val = msg.get(field)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


async def _broadcast_to_members(ws_manager, member_ids: list[int], message: dict) -> None:
    """Broadcast a message to all channel members concurrently (W8)."""
    if not member_ids:
        return
    await asyncio.gather(
        *(ws_manager.send_to_user(mid, message) for mid in member_ids),
        return_exceptions=True,
    )


async def handle_chat_message(
    ws_manager, websocket: WebSocket, user_id: int, msg: dict,
    user_permissions: set[str] | None = None,
    display_name: str | None = None,
):
    """Route a chat:* message to the appropriate handler.

    Requires 'social:chat' permission (W1). All ValueError messages raised by
    chat_service are designed to be user-safe strings — do not add internal
    details to ValueError messages in chat_service (W7).
    """
    # W1: RBAC enforcement — reject if user lacks social:chat permission
    if not user_permissions or CHAT_PERMISSION not in user_permissions:
        await websocket.send_json({
            "type": "chat:error",
            "error": "You do not have permission to use chat",
        })
        return

    msg_type = msg.get("type", "")
    handlers = {
        "chat:send": _handle_send,
        "chat:typing": _handle_typing,
        "chat:read": _handle_read,
        "chat:edit": _handle_edit,
        "chat:delete": _handle_delete,
        "chat:react": _handle_react,
        "chat:pin": _handle_pin,
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
    # W2: Type-safe extraction
    channel_id = _parse_int_field(msg, "channelId")
    if channel_id is None:
        await websocket.send_json({"type": "chat:error", "error": "Valid channelId required"})
        return

    # W4: Content validation (defense-in-depth — service also validates)
    content = msg.get("content", "")
    if isinstance(content, str):
        content = content.strip()
    if not content or not isinstance(content, str):
        await websocket.send_json({"type": "chat:error", "error": "Message cannot be empty"})
        return

    reply_to_id = _parse_int_field(msg, "replyToId")  # None is valid (no reply)

    # W3: Rate limiting
    _prune_send_timestamps()
    if not _check_send_rate(user_id):
        await websocket.send_json({
            "type": "chat:error",
            "error": "Sending too fast, please slow down",
        })
        return

    async with async_session_maker() as db:
        message_data = await chat_service.send_message(
            db, channel_id, user_id, content, reply_to_id=reply_to_id
        )
        # W5: Exclude members who have blocked the sender
        member_ids = await chat_service.get_channel_member_ids_excluding_blockers(
            db, channel_id, user_id
        )

    broadcast = {"type": "chat:message", **message_data}
    await _broadcast_to_members(ws_manager, member_ids, broadcast)


async def _handle_typing(ws_manager, websocket, user_id, msg, display_name):
    """Handle chat:typing — broadcast typing indicator to other channel members."""
    channel_id = _parse_int_field(msg, "channelId")
    if channel_id is None:
        return

    # Prune stale entries to prevent unbounded growth
    _prune_typing_cooldowns()

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
    others = [mid for mid in member_ids if mid != user_id]
    await _broadcast_to_members(ws_manager, others, broadcast)


async def _handle_read(ws_manager, websocket, user_id, msg, display_name):
    """Handle chat:read — mark channel as read and broadcast receipt."""
    channel_id = _parse_int_field(msg, "channelId")
    if channel_id is None:
        return

    async with async_session_maker() as db:
        await chat_service.mark_read(db, channel_id, user_id)
        member_ids = await chat_service.get_channel_member_ids(db, channel_id)

    broadcast = {
        "type": "chat:read_receipt",
        "channelId": channel_id,
        "userId": user_id,
    }
    others = [mid for mid in member_ids if mid != user_id]
    await _broadcast_to_members(ws_manager, others, broadcast)


async def _handle_edit(ws_manager, websocket, user_id, msg, display_name):
    """Handle chat:edit — edit a message and broadcast update."""
    message_id = _parse_int_field(msg, "messageId")
    if message_id is None:
        await websocket.send_json({"type": "chat:error", "error": "Valid messageId required"})
        return

    # W4: Content validation
    content = msg.get("content", "")
    if isinstance(content, str):
        content = content.strip()
    if not content or not isinstance(content, str):
        await websocket.send_json({"type": "chat:error", "error": "Message cannot be empty"})
        return

    async with async_session_maker() as db:
        message_data = await chat_service.edit_message(db, message_id, user_id, content)
        member_ids = await chat_service.get_channel_member_ids(db, message_data["channel_id"])

    broadcast = {"type": "chat:message_edited", **message_data}
    await _broadcast_to_members(ws_manager, member_ids, broadcast)


async def _handle_delete(ws_manager, websocket, user_id, msg, display_name):
    """Handle chat:delete — soft-delete a message and broadcast."""
    message_id = _parse_int_field(msg, "messageId")
    if message_id is None:
        await websocket.send_json({"type": "chat:error", "error": "Valid messageId required"})
        return

    async with async_session_maker() as db:
        result = await chat_service.delete_message(db, message_id, user_id)
        member_ids = await chat_service.get_channel_member_ids(db, result["channel_id"])

    broadcast = {
        "type": "chat:message_deleted",
        "messageId": result["id"],
        "channelId": result["channel_id"],
    }
    await _broadcast_to_members(ws_manager, member_ids, broadcast)


async def _handle_react(ws_manager, websocket, user_id, msg, display_name):
    """Handle chat:react — toggle reaction and broadcast update."""
    message_id = _parse_int_field(msg, "messageId")
    emoji = msg.get("emoji", "")

    if message_id is None or not emoji or not isinstance(emoji, str):
        await websocket.send_json({"type": "chat:error", "error": "Valid messageId and emoji required"})
        return

    async with async_session_maker() as db:
        result = await chat_service.toggle_reaction(db, message_id, user_id, emoji)
        member_ids = await chat_service.get_channel_member_ids(db, result["channel_id"])

    broadcast = {
        "type": "chat:reaction_updated",
        "messageId": result["message_id"],
        "channelId": result["channel_id"],
        "reactions": result["reactions"],
    }
    await _broadcast_to_members(ws_manager, member_ids, broadcast)


async def _handle_pin(ws_manager, websocket, user_id, msg, display_name):
    """Handle chat:pin — toggle pin and broadcast update."""
    message_id = _parse_int_field(msg, "messageId")
    if message_id is None:
        await websocket.send_json({"type": "chat:error", "error": "Valid messageId required"})
        return

    async with async_session_maker() as db:
        result = await chat_service.toggle_pin(db, message_id, user_id)
        member_ids = await chat_service.get_channel_member_ids(db, result["channel_id"])

    broadcast = {
        "type": "chat:pin_updated",
        "messageId": result["message_id"],
        "channelId": result["channel_id"],
        "isPinned": result["is_pinned"],
    }
    await _broadcast_to_members(ws_manager, member_ids, broadcast)
