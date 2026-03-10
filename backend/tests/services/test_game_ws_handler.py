"""
Tests for backend/app/services/game_ws_handler.py

Covers message routing, display name propagation, RBAC checks,
and game invite functionality.
"""

import pytest
from unittest.mock import AsyncMock

from app.services.game_ws_handler import handle_game_message
from app.services.game_room_manager import game_room_manager


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_rooms():
    """Clear all rooms before/after each test."""
    game_room_manager._rooms.clear()
    game_room_manager._user_rooms.clear()
    yield
    game_room_manager._rooms.clear()
    game_room_manager._user_rooms.clear()


def make_ws_manager():
    """Create a mock WebSocket manager."""
    mgr = AsyncMock()
    mgr.send_to_room = AsyncMock()
    mgr.send_to_user = AsyncMock()
    return mgr


def make_ws():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


# =============================================================================
# Message routing
# =============================================================================


class TestMessageRouting:
    """Tests for game message type routing."""

    @pytest.mark.asyncio
    async def test_unknown_message_type_returns_error(self):
        ws = make_ws()
        await handle_game_message(
            make_ws_manager(), ws, 1,
            {"type": "game:unknown"},
            {"games:multiplayer"},
        )
        ws.send_json.assert_called_once()
        assert "Unknown message type" in ws.send_json.call_args[0][0]["error"]

    @pytest.mark.asyncio
    async def test_create_without_permission_denied(self):
        ws = make_ws()
        await handle_game_message(
            make_ws_manager(), ws, 1,
            {"type": "game:create", "gameId": "chess", "mode": "vs"},
            set(),  # no permissions
        )
        ws.send_json.assert_called_once()
        assert "permission" in ws.send_json.call_args[0][0]["error"].lower()

    @pytest.mark.asyncio
    async def test_join_without_permission_denied(self):
        ws = make_ws()
        await handle_game_message(
            make_ws_manager(), ws, 1,
            {"type": "game:join", "roomId": "fake"},
            set(),
        )
        ws.send_json.assert_called_once()
        assert "permission" in ws.send_json.call_args[0][0]["error"].lower()


# =============================================================================
# Display name propagation
# =============================================================================


class TestDisplayNamePropagation:
    """Tests for player display names in WS payloads."""

    @pytest.mark.asyncio
    async def test_create_room_includes_player_names(self):
        ws = make_ws()
        mgr = make_ws_manager()
        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:create", "gameId": "chess", "mode": "vs"},
            {"games:multiplayer"},
            "Alice",
        )
        response = ws.send_json.call_args[0][0]
        assert response["type"] == "game:created"
        assert response["playerNames"][1] == "Alice"

    @pytest.mark.asyncio
    async def test_join_room_includes_all_player_names(self):
        # Host creates
        ws_host = make_ws()
        mgr = make_ws_manager()
        await handle_game_message(
            mgr, ws_host, 1,
            {"type": "game:create", "gameId": "chess", "mode": "vs"},
            {"games:multiplayer"},
            "Alice",
        )
        room_id = ws_host.send_json.call_args[0][0]["roomId"]

        # Guest joins
        ws_guest = make_ws()
        await handle_game_message(
            mgr, ws_guest, 2,
            {"type": "game:join", "roomId": room_id},
            {"games:multiplayer"},
            "Bob",
        )
        response = ws_guest.send_json.call_args[0][0]
        assert response["type"] == "game:joined"
        assert response["playerNames"][1] == "Alice"
        assert response["playerNames"][2] == "Bob"

    @pytest.mark.asyncio
    async def test_started_includes_player_names(self):
        ws = make_ws()
        mgr = make_ws_manager()

        # Create + join + ready both + start
        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:create", "gameId": "chess", "mode": "vs"},
            {"games:multiplayer"}, "Alice",
        )
        room_id = ws.send_json.call_args[0][0]["roomId"]

        ws2 = make_ws()
        await handle_game_message(
            mgr, ws2, 2,
            {"type": "game:join", "roomId": room_id},
            {"games:multiplayer"}, "Bob",
        )
        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:ready", "roomId": room_id},
            None, "Alice",
        )
        await handle_game_message(
            mgr, ws2, 2,
            {"type": "game:ready", "roomId": room_id},
            None, "Bob",
        )
        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:start", "roomId": room_id},
            None, "Alice",
        )

        # Check started broadcast includes playerNames
        started_call = mgr.send_to_room.call_args_list[-1]
        msg = started_call[0][1]
        assert msg["type"] == "game:started"
        assert msg["playerNames"][1] == "Alice"
        assert msg["playerNames"][2] == "Bob"

    @pytest.mark.asyncio
    async def test_default_display_name_fallback(self):
        ws = make_ws()
        mgr = make_ws_manager()
        # No display_name provided — should fallback
        await handle_game_message(
            mgr, ws, 42,
            {"type": "game:create", "gameId": "chess", "mode": "vs"},
            {"games:multiplayer"},
            None,
        )
        response = ws.send_json.call_args[0][0]
        assert response["playerNames"][42] == "Player 42"


# =============================================================================
# Game invites
# =============================================================================


class TestGameInvites:
    """Tests for game invite functionality."""

    @pytest.mark.asyncio
    async def test_invite_sends_notification_to_target(self):
        ws = make_ws()
        mgr = make_ws_manager()

        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:create", "gameId": "chess", "mode": "vs"},
            {"games:multiplayer"}, "Alice",
        )
        room_id = ws.send_json.call_args[0][0]["roomId"]

        # Send invite
        ws.send_json.reset_mock()
        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:invite", "roomId": room_id, "targetUserId": 99},
            {"games:multiplayer"}, "Alice",
        )

        # Target should receive invite
        mgr.send_to_user.assert_called_once()
        invite_msg = mgr.send_to_user.call_args[0][1]
        assert invite_msg["type"] == "game:invite"
        assert invite_msg["roomId"] == room_id
        assert invite_msg["fromDisplayName"] == "Alice"
        assert invite_msg["gameId"] == "chess"

        # Sender should receive confirmation
        ws.send_json.assert_called_once()
        confirm = ws.send_json.call_args[0][0]
        assert confirm["type"] == "game:invite_sent"

    @pytest.mark.asyncio
    async def test_non_host_cannot_invite(self):
        ws_host = make_ws()
        ws_guest = make_ws()
        mgr = make_ws_manager()

        await handle_game_message(
            mgr, ws_host, 1,
            {"type": "game:create", "gameId": "chess", "mode": "vs",
             "config": {"max_players": 4}},
            {"games:multiplayer"}, "Alice",
        )
        room_id = ws_host.send_json.call_args[0][0]["roomId"]

        await handle_game_message(
            mgr, ws_guest, 2,
            {"type": "game:join", "roomId": room_id},
            {"games:multiplayer"}, "Bob",
        )

        # Non-host tries to invite
        ws_guest.send_json.reset_mock()
        await handle_game_message(
            mgr, ws_guest, 2,
            {"type": "game:invite", "roomId": room_id, "targetUserId": 99},
            None, "Bob",
        )
        error = ws_guest.send_json.call_args[0][0]
        assert "host" in error["error"].lower()

    @pytest.mark.asyncio
    async def test_invite_to_nonexistent_room(self):
        ws = make_ws()
        mgr = make_ws_manager()
        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:invite", "roomId": "doesnotexist", "targetUserId": 99},
            None, "Alice",
        )
        assert "not found" in ws.send_json.call_args[0][0]["error"].lower()

    @pytest.mark.asyncio
    async def test_mid_game_invite_allowed_with_open_seats(self):
        """Invites during 'playing' status are allowed when seats remain."""
        ws = make_ws()
        mgr = make_ws_manager()

        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:create", "gameId": "holdem", "mode": "vs",
             "config": {"max_players": 4}},
            {"games:multiplayer"}, "Alice",
        )
        room_id = ws.send_json.call_args[0][0]["roomId"]

        ws2 = make_ws()
        await handle_game_message(
            mgr, ws2, 2,
            {"type": "game:join", "roomId": room_id},
            {"games:multiplayer"}, "Bob",
        )
        await handle_game_message(mgr, ws, 1, {"type": "game:ready", "roomId": room_id}, None, "Alice")
        await handle_game_message(mgr, ws2, 2, {"type": "game:ready", "roomId": room_id}, None, "Bob")
        await handle_game_message(mgr, ws, 1, {"type": "game:start", "roomId": room_id}, None, "Alice")

        # Mid-game invite should succeed (room has 4 seats, only 2 filled)
        ws.send_json.reset_mock()
        mgr.send_to_user.reset_mock()
        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:invite", "roomId": room_id, "targetUserId": 99},
            None, "Alice",
        )
        # Target receives invite with midGame flag
        mgr.send_to_user.assert_called_once()
        invite_msg = mgr.send_to_user.call_args[0][1]
        assert invite_msg["type"] == "game:invite"
        assert invite_msg["midGame"] is True

        # Sender gets confirmation
        ws.send_json.assert_called_once()
        assert ws.send_json.call_args[0][0]["type"] == "game:invite_sent"

    @pytest.mark.asyncio
    async def test_invite_full_room_denied(self):
        """Invites denied when room is already at max capacity."""
        ws = make_ws()
        mgr = make_ws_manager()

        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:create", "gameId": "chess", "mode": "vs"},
            {"games:multiplayer"}, "Alice",
        )
        room_id = ws.send_json.call_args[0][0]["roomId"]

        ws2 = make_ws()
        await handle_game_message(
            mgr, ws2, 2,
            {"type": "game:join", "roomId": room_id},
            {"games:multiplayer"}, "Bob",
        )

        # Room is full (default 2 players)
        ws.send_json.reset_mock()
        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:invite", "roomId": room_id, "targetUserId": 99},
            None, "Alice",
        )
        assert "full" in ws.send_json.call_args[0][0]["error"].lower()


# =============================================================================
# Mid-game join via WS
# =============================================================================


class TestMidGameJoinWS:
    """Tests for game:mid_join message handling."""

    @pytest.mark.asyncio
    async def test_mid_join_succeeds(self):
        ws = make_ws()
        mgr = make_ws_manager()

        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:create", "gameId": "holdem", "mode": "vs",
             "config": {"max_players": 4}},
            {"games:multiplayer"}, "Alice",
        )
        room_id = ws.send_json.call_args[0][0]["roomId"]

        ws2 = make_ws()
        await handle_game_message(
            mgr, ws2, 2,
            {"type": "game:join", "roomId": room_id},
            {"games:multiplayer"}, "Bob",
        )
        await handle_game_message(mgr, ws, 1, {"type": "game:ready", "roomId": room_id}, None, "Alice")
        await handle_game_message(mgr, ws2, 2, {"type": "game:ready", "roomId": room_id}, None, "Bob")
        await handle_game_message(mgr, ws, 1, {"type": "game:start", "roomId": room_id}, None, "Alice")

        # Mid-game join
        ws3 = make_ws()
        await handle_game_message(
            mgr, ws3, 3,
            {"type": "game:mid_join", "roomId": room_id},
            {"games:multiplayer"}, "Charlie",
        )

        # Joiner gets mid_joined response
        response = ws3.send_json.call_args[0][0]
        assert response["type"] == "game:mid_joined"
        assert 3 in response["players"]
        assert response["playerNames"][3] == "Charlie"

        # Existing players notified
        broadcast = mgr.send_to_room.call_args[0][1]
        assert broadcast["type"] == "game:mid_player_joined"
        assert broadcast["playerId"] == 3
        assert broadcast["playerName"] == "Charlie"

    @pytest.mark.asyncio
    async def test_mid_join_without_permission_denied(self):
        ws = make_ws()
        await handle_game_message(
            make_ws_manager(), ws, 1,
            {"type": "game:mid_join", "roomId": "fake"},
            set(),
        )
        ws.send_json.assert_called_once()
        assert "permission" in ws.send_json.call_args[0][0]["error"].lower()

    @pytest.mark.asyncio
    async def test_mid_join_waiting_room_denied(self):
        ws = make_ws()
        mgr = make_ws_manager()

        await handle_game_message(
            mgr, ws, 1,
            {"type": "game:create", "gameId": "holdem", "mode": "vs",
             "config": {"max_players": 4}},
            {"games:multiplayer"}, "Alice",
        )
        room_id = ws.send_json.call_args[0][0]["roomId"]

        ws2 = make_ws()
        await handle_game_message(
            mgr, ws2, 2,
            {"type": "game:mid_join", "roomId": room_id},
            {"games:multiplayer"}, "Bob",
        )
        error = ws2.send_json.call_args[0][0]
        assert error["type"] == "game:error"
        assert "not in progress" in error["error"].lower()
