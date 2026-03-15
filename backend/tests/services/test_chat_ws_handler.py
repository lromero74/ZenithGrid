"""
Tests for backend/app/services/chat_ws_handler.py

Covers RBAC enforcement, message routing, typing indicators with debouncing,
read receipts, message editing/deletion, reactions, pinning, rate limiting,
and helper functions. All DB calls and WebSocket sends are mocked.
"""

import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.chat_ws_handler as ws_mod
from app.services.chat_ws_handler import (
    _check_send_rate,
    _parse_int_field,
    _prune_typing_cooldowns,
    _prune_send_timestamps,
    _broadcast_to_members,
    handle_chat_message,
    prune_all_stale,
    CHAT_PERMISSION,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level rate limiting state between tests."""
    ws_mod._typing_cooldowns.clear()
    ws_mod._send_timestamps.clear()
    yield
    ws_mod._typing_cooldowns.clear()
    ws_mod._send_timestamps.clear()


@pytest.fixture
def mock_ws():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def mock_ws_manager():
    """Create a mock WebSocket manager."""
    mgr = MagicMock()
    mgr.send_to_user = AsyncMock()
    return mgr


@pytest.fixture
def mock_db_context():
    """Create a mock async_session_maker context manager."""
    mock_db = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_db, mock_cm


# ===========================================================================
# _parse_int_field
# ===========================================================================


class TestParseIntField:
    """Tests for _parse_int_field() — safe integer extraction."""

    def test_valid_integer(self):
        """Happy path: integer value returned as-is."""
        assert _parse_int_field({"id": 42}, "id") == 42

    def test_string_integer(self):
        """Edge case: string '42' converted to int."""
        assert _parse_int_field({"id": "42"}, "id") == 42

    def test_missing_field_returns_none(self):
        """Edge case: missing field returns None."""
        assert _parse_int_field({}, "id") is None

    def test_none_value_returns_none(self):
        """Edge case: explicit None value returns None."""
        assert _parse_int_field({"id": None}, "id") is None

    def test_invalid_string_returns_none(self):
        """Failure: non-numeric string returns None."""
        assert _parse_int_field({"id": "abc"}, "id") is None

    def test_float_value_truncated(self):
        """Edge case: float is truncated to int."""
        assert _parse_int_field({"id": 3.9}, "id") == 3

    def test_empty_string_returns_none(self):
        """Failure: empty string returns None."""
        assert _parse_int_field({"id": ""}, "id") is None


# ===========================================================================
# _check_send_rate
# ===========================================================================


class TestCheckSendRate:
    """Tests for _check_send_rate() — per-user message rate limiting."""

    def test_first_message_allowed(self):
        """Happy path: first message from a user is always allowed."""
        assert _check_send_rate(user_id=1) is True

    def test_within_limit_allowed(self):
        """Happy path: messages within rate limit are allowed."""
        for _ in range(9):
            _check_send_rate(user_id=2)
        assert _check_send_rate(user_id=2) is True

    def test_exceeding_limit_blocked(self):
        """Failure: 11th message within window is blocked."""
        for _ in range(10):
            assert _check_send_rate(user_id=3) is True
        assert _check_send_rate(user_id=3) is False

    def test_old_timestamps_pruned(self):
        """Edge case: timestamps older than the window are pruned, freeing capacity."""
        user_id = 4
        old_time = time.monotonic() - ws_mod._SEND_RATE_WINDOW - 1
        ws_mod._send_timestamps[user_id] = [old_time] * 10

        # Should be allowed because old timestamps will be pruned
        assert _check_send_rate(user_id) is True

    def test_different_users_independent(self):
        """Edge case: rate limits are per-user, not global."""
        for _ in range(10):
            _check_send_rate(user_id=5)
        # User 5 is at limit
        assert _check_send_rate(user_id=5) is False
        # User 6 is fresh
        assert _check_send_rate(user_id=6) is True


# ===========================================================================
# _prune_typing_cooldowns
# ===========================================================================


class TestPruneTypingCooldowns:
    """Tests for _prune_typing_cooldowns()."""

    def test_empty_dict_no_error(self):
        """Edge case: pruning empty dict does not raise."""
        _prune_typing_cooldowns()
        assert ws_mod._typing_cooldowns == {}

    def test_stale_entries_removed(self):
        """Happy path: entries older than threshold are removed."""
        stale_time = time.monotonic() - ws_mod._TYPING_STALE_SECONDS - 10
        ws_mod._typing_cooldowns[(1, 1)] = stale_time
        ws_mod._typing_cooldowns[(2, 1)] = time.monotonic()  # fresh

        _prune_typing_cooldowns()

        assert (1, 1) not in ws_mod._typing_cooldowns
        assert (2, 1) in ws_mod._typing_cooldowns

    def test_fresh_entries_retained(self):
        """Edge case: recent entries are not pruned."""
        now = time.monotonic()
        ws_mod._typing_cooldowns[(1, 1)] = now
        ws_mod._typing_cooldowns[(1, 2)] = now

        _prune_typing_cooldowns()

        assert len(ws_mod._typing_cooldowns) == 2


# ===========================================================================
# _prune_send_timestamps
# ===========================================================================


class TestPruneSendTimestamps:
    """Tests for _prune_send_timestamps()."""

    def test_empty_dict_no_error(self):
        """Edge case: pruning empty dict does not raise."""
        _prune_send_timestamps()

    def test_stale_user_removed(self):
        """Happy path: users with no recent timestamps are removed."""
        stale_time = time.monotonic() - ws_mod._SEND_STALE_SECONDS - 10
        ws_mod._send_timestamps[1] = [stale_time]
        ws_mod._send_timestamps[2] = [time.monotonic()]

        _prune_send_timestamps()

        assert 1 not in ws_mod._send_timestamps
        assert 2 in ws_mod._send_timestamps

    def test_user_with_empty_list_removed(self):
        """Edge case: user with empty timestamp list is pruned."""
        ws_mod._send_timestamps[1] = []

        _prune_send_timestamps()

        assert 1 not in ws_mod._send_timestamps


# ===========================================================================
# prune_all_stale
# ===========================================================================


class TestPruneAllStale:
    """Tests for prune_all_stale()."""

    def test_prunes_both_dicts(self):
        """Happy path: both typing and send dicts are pruned."""
        stale = time.monotonic() - 60
        ws_mod._typing_cooldowns[(1, 1)] = stale
        ws_mod._send_timestamps[1] = [stale]

        prune_all_stale()

        assert (1, 1) not in ws_mod._typing_cooldowns
        assert 1 not in ws_mod._send_timestamps


# ===========================================================================
# _broadcast_to_members
# ===========================================================================


class TestBroadcastToMembers:
    """Tests for _broadcast_to_members()."""

    @pytest.mark.asyncio
    async def test_broadcasts_to_all_members(self, mock_ws_manager):
        """Happy path: message sent to each member."""
        await _broadcast_to_members(mock_ws_manager, [1, 2, 3], {"type": "test"})

        assert mock_ws_manager.send_to_user.call_count == 3

    @pytest.mark.asyncio
    async def test_empty_member_list_no_broadcast(self, mock_ws_manager):
        """Edge case: empty member list sends nothing."""
        await _broadcast_to_members(mock_ws_manager, [], {"type": "test"})

        mock_ws_manager.send_to_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_exceptions_suppressed(self, mock_ws_manager):
        """Failure: exceptions from individual sends don't break broadcast."""
        mock_ws_manager.send_to_user = AsyncMock(side_effect=Exception("conn closed"))

        # Should not raise
        await _broadcast_to_members(mock_ws_manager, [1, 2], {"type": "test"})


# ===========================================================================
# handle_chat_message — RBAC (W1)
# ===========================================================================


class TestHandleChatMessageRBAC:
    """Tests for RBAC enforcement in handle_chat_message()."""

    @pytest.mark.asyncio
    async def test_no_permissions_rejected(self, mock_ws_manager, mock_ws):
        """Failure: user with no permissions gets error."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:send"}, user_permissions=None,
        )

        mock_ws.send_json.assert_called_once()
        sent = mock_ws.send_json.call_args[0][0]
        assert sent["type"] == "chat:error"
        assert "permission" in sent["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_chat_permission_rejected(self, mock_ws_manager, mock_ws):
        """Failure: user with other permissions but not social:chat is rejected."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:send"}, user_permissions={"admin:read"},
        )

        sent = mock_ws.send_json.call_args[0][0]
        assert sent["type"] == "chat:error"

    @pytest.mark.asyncio
    async def test_unknown_message_type_returns_error(self, mock_ws_manager, mock_ws):
        """Failure: unknown chat message type returns error."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:unknown_action"},
            user_permissions={CHAT_PERMISSION},
        )

        sent = mock_ws.send_json.call_args[0][0]
        assert sent["type"] == "chat:error"
        assert "Unknown" in sent["error"]


# ===========================================================================
# handle_chat_message — chat:send
# ===========================================================================


class TestHandleSend:
    """Tests for the chat:send handler."""

    @pytest.mark.asyncio
    async def test_send_message_success(self, mock_ws_manager, mock_ws, mock_db_context):
        """Happy path: message sent and broadcast to channel members."""
        mock_db, mock_cm = mock_db_context

        message_data = {"id": 1, "content": "Hello!", "channel_id": 10, "user_id": 1}

        with patch.object(ws_mod, 'async_session_maker', return_value=mock_cm), \
             patch.object(ws_mod.chat_service, 'send_message', new_callable=AsyncMock,
                          return_value=message_data), \
             patch.object(ws_mod.chat_service, 'get_channel_member_ids_excluding_blockers',
                          new_callable=AsyncMock, return_value=[1, 2, 3]):
            await handle_chat_message(
                mock_ws_manager, mock_ws, user_id=1,
                msg={"type": "chat:send", "channelId": 10, "content": "Hello!"},
                user_permissions={CHAT_PERMISSION},
            )

        # Broadcast should be sent to members
        assert mock_ws_manager.send_to_user.call_count == 3

    @pytest.mark.asyncio
    async def test_send_missing_channel_id_error(self, mock_ws_manager, mock_ws):
        """Failure: missing channelId returns error."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:send", "content": "Hello!"},
            user_permissions={CHAT_PERMISSION},
        )

        sent = mock_ws.send_json.call_args[0][0]
        assert sent["type"] == "chat:error"
        assert "channelId" in sent["error"]

    @pytest.mark.asyncio
    async def test_send_empty_content_error(self, mock_ws_manager, mock_ws):
        """Failure: empty content returns error."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:send", "channelId": 10, "content": "   "},
            user_permissions={CHAT_PERMISSION},
        )

        sent = mock_ws.send_json.call_args[0][0]
        assert sent["type"] == "chat:error"
        assert "empty" in sent["error"].lower()

    @pytest.mark.asyncio
    async def test_send_rate_limited(self, mock_ws_manager, mock_ws):
        """Failure: sending too fast triggers rate limit."""
        # Fill up rate limit
        now = time.monotonic()
        ws_mod._send_timestamps[1] = [now] * 10

        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:send", "channelId": 10, "content": "spam"},
            user_permissions={CHAT_PERMISSION},
        )

        sent = mock_ws.send_json.call_args[0][0]
        assert sent["type"] == "chat:error"
        assert "too fast" in sent["error"].lower()

    @pytest.mark.asyncio
    async def test_send_service_value_error_forwarded(self, mock_ws_manager, mock_ws, mock_db_context):
        """Failure: ValueError from chat_service sent back as chat:error."""
        mock_db, mock_cm = mock_db_context

        with patch.object(ws_mod, 'async_session_maker', return_value=mock_cm), \
             patch.object(ws_mod.chat_service, 'send_message', new_callable=AsyncMock,
                          side_effect=ValueError("You are not a member of this channel")):
            await handle_chat_message(
                mock_ws_manager, mock_ws, user_id=1,
                msg={"type": "chat:send", "channelId": 10, "content": "Hello!"},
                user_permissions={CHAT_PERMISSION},
            )

        sent = mock_ws.send_json.call_args[0][0]
        assert sent["type"] == "chat:error"
        assert "not a member" in sent["error"]


# ===========================================================================
# handle_chat_message — chat:typing
# ===========================================================================


class TestHandleTyping:
    """Tests for the chat:typing handler."""

    @pytest.mark.asyncio
    async def test_typing_broadcast_to_others(self, mock_ws_manager, mock_ws, mock_db_context):
        """Happy path: typing indicator sent to other members (not sender)."""
        mock_db, mock_cm = mock_db_context

        with patch.object(ws_mod, 'async_session_maker', return_value=mock_cm), \
             patch.object(ws_mod.chat_service, 'get_channel_member_ids',
                          new_callable=AsyncMock, return_value=[1, 2, 3]):
            await handle_chat_message(
                mock_ws_manager, mock_ws, user_id=1,
                msg={"type": "chat:typing", "channelId": 5},
                user_permissions={CHAT_PERMISSION},
                display_name="Alice",
            )

        # Should only send to users 2 and 3 (not user 1)
        assert mock_ws_manager.send_to_user.call_count == 2

    @pytest.mark.asyncio
    async def test_typing_debounced(self, mock_ws_manager, mock_ws, mock_db_context):
        """Edge case: rapid typing within cooldown is debounced (not re-broadcast)."""
        mock_db, mock_cm = mock_db_context

        # Set recent cooldown for this user+channel
        ws_mod._typing_cooldowns[(1, 5)] = time.monotonic()

        with patch.object(ws_mod, 'async_session_maker', return_value=mock_cm):
            await handle_chat_message(
                mock_ws_manager, mock_ws, user_id=1,
                msg={"type": "chat:typing", "channelId": 5},
                user_permissions={CHAT_PERMISSION},
            )

        # Should not broadcast (debounced)
        mock_ws_manager.send_to_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_typing_missing_channel_id_ignored(self, mock_ws_manager, mock_ws):
        """Edge case: missing channelId silently ignored (no error sent)."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:typing"},
            user_permissions={CHAT_PERMISSION},
        )

        # No error sent, no broadcast
        mock_ws.send_json.assert_not_called()
        mock_ws_manager.send_to_user.assert_not_called()


# ===========================================================================
# handle_chat_message — chat:edit
# ===========================================================================


class TestHandleEdit:
    """Tests for the chat:edit handler."""

    @pytest.mark.asyncio
    async def test_edit_message_success(self, mock_ws_manager, mock_ws, mock_db_context):
        """Happy path: message edited and broadcast to members."""
        mock_db, mock_cm = mock_db_context

        edit_result = {"id": 5, "channel_id": 10, "content": "Edited content"}

        with patch.object(ws_mod, 'async_session_maker', return_value=mock_cm), \
             patch.object(ws_mod.chat_service, 'edit_message', new_callable=AsyncMock,
                          return_value=edit_result), \
             patch.object(ws_mod.chat_service, 'get_channel_member_ids',
                          new_callable=AsyncMock, return_value=[1, 2]):
            await handle_chat_message(
                mock_ws_manager, mock_ws, user_id=1,
                msg={"type": "chat:edit", "messageId": 5, "content": "Edited content"},
                user_permissions={CHAT_PERMISSION},
            )

        assert mock_ws_manager.send_to_user.call_count == 2

    @pytest.mark.asyncio
    async def test_edit_missing_message_id_error(self, mock_ws_manager, mock_ws):
        """Failure: missing messageId returns error."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:edit", "content": "Updated"},
            user_permissions={CHAT_PERMISSION},
        )

        sent = mock_ws.send_json.call_args[0][0]
        assert sent["type"] == "chat:error"
        assert "messageId" in sent["error"]

    @pytest.mark.asyncio
    async def test_edit_empty_content_error(self, mock_ws_manager, mock_ws):
        """Failure: empty edit content returns error."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:edit", "messageId": 5, "content": ""},
            user_permissions={CHAT_PERMISSION},
        )

        sent = mock_ws.send_json.call_args[0][0]
        assert "empty" in sent["error"].lower()


# ===========================================================================
# handle_chat_message — chat:delete
# ===========================================================================


class TestHandleDelete:
    """Tests for the chat:delete handler."""

    @pytest.mark.asyncio
    async def test_delete_message_success(self, mock_ws_manager, mock_ws, mock_db_context):
        """Happy path: message deleted and broadcast to members."""
        mock_db, mock_cm = mock_db_context

        delete_result = {"id": 5, "channel_id": 10}

        with patch.object(ws_mod, 'async_session_maker', return_value=mock_cm), \
             patch.object(ws_mod.chat_service, 'delete_message', new_callable=AsyncMock,
                          return_value=delete_result), \
             patch.object(ws_mod.chat_service, 'get_channel_member_ids',
                          new_callable=AsyncMock, return_value=[1, 2]):
            await handle_chat_message(
                mock_ws_manager, mock_ws, user_id=1,
                msg={"type": "chat:delete", "messageId": 5},
                user_permissions={CHAT_PERMISSION},
            )

        assert mock_ws_manager.send_to_user.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_missing_message_id_error(self, mock_ws_manager, mock_ws):
        """Failure: missing messageId returns error."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:delete"},
            user_permissions={CHAT_PERMISSION},
        )

        sent = mock_ws.send_json.call_args[0][0]
        assert "messageId" in sent["error"]


# ===========================================================================
# handle_chat_message — chat:react
# ===========================================================================


class TestHandleReact:
    """Tests for the chat:react handler."""

    @pytest.mark.asyncio
    async def test_react_success(self, mock_ws_manager, mock_ws, mock_db_context):
        """Happy path: reaction toggled and broadcast."""
        mock_db, mock_cm = mock_db_context

        react_result = {"message_id": 5, "channel_id": 10, "reactions": {"thumbsup": [1]}}

        with patch.object(ws_mod, 'async_session_maker', return_value=mock_cm), \
             patch.object(ws_mod.chat_service, 'toggle_reaction', new_callable=AsyncMock,
                          return_value=react_result), \
             patch.object(ws_mod.chat_service, 'get_channel_member_ids',
                          new_callable=AsyncMock, return_value=[1, 2]):
            await handle_chat_message(
                mock_ws_manager, mock_ws, user_id=1,
                msg={"type": "chat:react", "messageId": 5, "emoji": "thumbsup"},
                user_permissions={CHAT_PERMISSION},
            )

        assert mock_ws_manager.send_to_user.call_count == 2

    @pytest.mark.asyncio
    async def test_react_missing_emoji_error(self, mock_ws_manager, mock_ws):
        """Failure: missing emoji returns error."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:react", "messageId": 5},
            user_permissions={CHAT_PERMISSION},
        )

        sent = mock_ws.send_json.call_args[0][0]
        assert "emoji" in sent["error"].lower()

    @pytest.mark.asyncio
    async def test_react_missing_message_id_error(self, mock_ws_manager, mock_ws):
        """Failure: missing messageId returns error."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:react", "emoji": "thumbsup"},
            user_permissions={CHAT_PERMISSION},
        )

        sent = mock_ws.send_json.call_args[0][0]
        assert "messageId" in sent["error"]


# ===========================================================================
# handle_chat_message — chat:pin
# ===========================================================================


class TestHandlePin:
    """Tests for the chat:pin handler."""

    @pytest.mark.asyncio
    async def test_pin_success(self, mock_ws_manager, mock_ws, mock_db_context):
        """Happy path: pin toggled and broadcast."""
        mock_db, mock_cm = mock_db_context

        pin_result = {"message_id": 5, "channel_id": 10, "is_pinned": True}

        with patch.object(ws_mod, 'async_session_maker', return_value=mock_cm), \
             patch.object(ws_mod.chat_service, 'toggle_pin', new_callable=AsyncMock,
                          return_value=pin_result), \
             patch.object(ws_mod.chat_service, 'get_channel_member_ids',
                          new_callable=AsyncMock, return_value=[1, 2]):
            await handle_chat_message(
                mock_ws_manager, mock_ws, user_id=1,
                msg={"type": "chat:pin", "messageId": 5},
                user_permissions={CHAT_PERMISSION},
            )

        assert mock_ws_manager.send_to_user.call_count == 2

    @pytest.mark.asyncio
    async def test_pin_missing_message_id_error(self, mock_ws_manager, mock_ws):
        """Failure: missing messageId returns error."""
        await handle_chat_message(
            mock_ws_manager, mock_ws, user_id=1,
            msg={"type": "chat:pin"},
            user_permissions={CHAT_PERMISSION},
        )

        sent = mock_ws.send_json.call_args[0][0]
        assert "messageId" in sent["error"]


# ===========================================================================
# handle_chat_message — internal error handling
# ===========================================================================


class TestHandleChatMessageErrorHandling:
    """Tests for generic error handling in handle_chat_message()."""

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_internal_error(
        self, mock_ws_manager, mock_ws, mock_db_context
    ):
        """Failure: unexpected exception returns generic 'Internal error'."""
        mock_db, mock_cm = mock_db_context

        with patch.object(ws_mod, 'async_session_maker', return_value=mock_cm), \
             patch.object(ws_mod.chat_service, 'send_message', new_callable=AsyncMock,
                          side_effect=RuntimeError("DB connection lost")):
            await handle_chat_message(
                mock_ws_manager, mock_ws, user_id=1,
                msg={"type": "chat:send", "channelId": 10, "content": "Hello"},
                user_permissions={CHAT_PERMISSION},
            )

        sent = mock_ws.send_json.call_args[0][0]
        assert sent["type"] == "chat:error"
        assert sent["error"] == "Internal error"
        # Internal details not leaked
        assert "DB connection" not in sent["error"]
