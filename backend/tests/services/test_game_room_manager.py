"""
Tests for backend/app/services/game_room_manager.py

Covers room lifecycle, player management, message routing,
game state management, TTL cleanup, and room ID format.
"""

from datetime import datetime, timedelta

import pytest
from unittest.mock import AsyncMock

from app.services.game_room_manager import (
    GameRoomManager, GameRoom, ROOM_TTL_SECONDS, RECONNECT_WINDOW_SECONDS,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def manager():
    return GameRoomManager()


def make_ws(user_id):
    """Create a mock WebSocket with user_id attached."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.user_id = user_id
    return ws


# =============================================================================
# Room Creation
# =============================================================================


class TestRoomCreation:
    """Tests for creating game rooms."""

    def test_create_room_returns_room(self, manager):
        room = manager.create_room(
            host_user_id=1,
            game_id="connect-four",
            mode="vs",
            config={"time_limit": 30},
        )
        assert isinstance(room, GameRoom)
        assert room.game_id == "connect-four"
        assert room.mode == "vs"
        assert room.host_user_id == 1
        assert room.status == "waiting"

    def test_create_room_generates_unique_id(self, manager):
        r1 = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        r2 = manager.create_room(host_user_id=2, game_id="chess", mode="vs")
        assert r1.room_id != r2.room_id

    def test_create_room_registers_in_manager(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        assert manager.get_room(room.room_id) is room

    def test_create_room_tracks_user(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        assert manager.get_user_room(1) == room.room_id

    def test_user_cannot_create_two_rooms(self, manager):
        manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        with pytest.raises(ValueError, match="already in a room"):
            manager.create_room(host_user_id=1, game_id="checkers", mode="vs")


# =============================================================================
# Join / Leave
# =============================================================================


class TestJoinLeave:
    """Tests for joining and leaving rooms."""

    def test_join_room_adds_player(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        assert 2 in room.players
        assert manager.get_user_room(2) == room.room_id

    def test_join_nonexistent_room_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.join_room("fake-room", user_id=2)

    def test_join_full_room_raises(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs", config={"max_players": 2})
        manager.join_room(room.room_id, user_id=2)
        with pytest.raises(ValueError, match="full"):
            manager.join_room(room.room_id, user_id=3)

    def test_join_playing_room_raises(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        room.status = "playing"
        with pytest.raises(ValueError, match="already started"):
            manager.join_room(room.room_id, user_id=2)

    def test_leave_room_removes_player(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        manager.leave_room(room.room_id, user_id=2)
        assert 2 not in room.players
        assert manager.get_user_room(2) is None

    def test_host_leaving_closes_room(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        manager.leave_room(room.room_id, user_id=1)
        assert manager.get_room(room.room_id) is None
        assert manager.get_user_room(1) is None
        assert manager.get_user_room(2) is None

    def test_user_already_in_room_cannot_join_another(self, manager):
        manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        room2 = manager.create_room(host_user_id=2, game_id="checkers", mode="vs")
        manager.join_room(room2.room_id, user_id=3)
        with pytest.raises(ValueError, match="already in a room"):
            manager.join_room(room2.room_id, user_id=1)


# =============================================================================
# Ready / Start
# =============================================================================


class TestReadyStart:
    """Tests for readying up and starting games."""

    def test_set_ready(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        manager.set_ready(room.room_id, user_id=1)
        assert room.ready_players == {1}

    def test_all_ready_check(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        assert not room.all_ready()
        manager.set_ready(room.room_id, user_id=1)
        assert not room.all_ready()
        manager.set_ready(room.room_id, user_id=2)
        assert room.all_ready()

    def test_start_game_changes_status(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        manager.set_ready(room.room_id, user_id=1)
        manager.set_ready(room.room_id, user_id=2)
        manager.start_game(room.room_id, user_id=1)
        assert room.status == "playing"

    def test_non_host_cannot_start(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        manager.set_ready(room.room_id, user_id=1)
        manager.set_ready(room.room_id, user_id=2)
        with pytest.raises(ValueError, match="Only the host"):
            manager.start_game(room.room_id, user_id=2)

    def test_cannot_start_without_all_ready(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        manager.set_ready(room.room_id, user_id=1)
        with pytest.raises(ValueError, match="not all players ready"):
            manager.start_game(room.room_id, user_id=1)

    def test_need_at_least_two_players(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.set_ready(room.room_id, user_id=1)
        with pytest.raises(ValueError, match="at least 2"):
            manager.start_game(room.room_id, user_id=1)


# =============================================================================
# Game Actions
# =============================================================================


class TestGameActions:
    """Tests for recording game actions and state."""

    def test_record_action_increments_sequence(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        manager.set_ready(room.room_id, user_id=1)
        manager.set_ready(room.room_id, user_id=2)
        manager.start_game(room.room_id, user_id=1)

        seq = manager.record_action(room.room_id, user_id=1, action={"type": "move", "col": 3})
        assert seq == 1
        seq2 = manager.record_action(room.room_id, user_id=2, action={"type": "move", "col": 4})
        assert seq2 == 2

    def test_cannot_act_in_waiting_room(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        with pytest.raises(ValueError, match="not in progress"):
            manager.record_action(room.room_id, user_id=1, action={"type": "move"})

    def test_update_game_state(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        manager.set_ready(room.room_id, user_id=1)
        manager.set_ready(room.room_id, user_id=2)
        manager.start_game(room.room_id, user_id=1)

        manager.update_state(room.room_id, {"board": [[0]*7]*6, "turn": 1})
        assert room.state["turn"] == 1


# =============================================================================
# Room Cleanup
# =============================================================================


class TestRoomCleanup:
    """Tests for finishing and cleaning up rooms."""

    def test_finish_game(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        manager.set_ready(room.room_id, user_id=1)
        manager.set_ready(room.room_id, user_id=2)
        manager.start_game(room.room_id, user_id=1)

        result = manager.finish_game(room.room_id, result={"winner": 1})
        assert result["winner"] == 1
        assert room.status == "finished"

    def test_close_room_cleans_up(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, user_id=2)
        room_id = room.room_id

        manager.close_room(room_id)
        assert manager.get_room(room_id) is None
        assert manager.get_user_room(1) is None
        assert manager.get_user_room(2) is None

    def test_get_room_nonexistent_returns_none(self, manager):
        assert manager.get_room("does-not-exist") is None

    def test_list_rooms(self, manager):
        manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.create_room(host_user_id=2, game_id="checkers", mode="race")
        rooms = manager.list_rooms()
        assert len(rooms) == 2

    def test_list_rooms_by_game(self, manager):
        manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.create_room(host_user_id=2, game_id="checkers", mode="race")
        rooms = manager.list_rooms(game_id="chess")
        assert len(rooms) == 1
        assert rooms[0].game_id == "chess"


# =============================================================================
# W16: Room ID length
# =============================================================================


class TestRoomIdFormat:
    """W16: Room IDs should be 16 hex characters."""

    def test_room_id_is_16_hex_chars(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        assert len(room.room_id) == 16
        # Should be valid hexadecimal
        int(room.room_id, 16)

    def test_room_ids_are_unique(self, manager):
        ids = set()
        for i in range(10):
            room = manager.create_room(host_user_id=i + 1, game_id="chess", mode="vs")
            ids.add(room.room_id)
        assert len(ids) == 10


# =============================================================================
# Mid-game join
# =============================================================================


class TestMidGameJoin:
    """Tests for mid_join_room — joining an already-playing game."""

    def test_mid_join_playing_room(self, manager):
        room = manager.create_room(host_user_id=1, game_id="holdem", mode="vs",
                                   config={"max_players": 4})
        manager.join_room(room.room_id, user_id=2)
        manager.set_ready(room.room_id, user_id=1)
        manager.set_ready(room.room_id, user_id=2)
        manager.start_game(room.room_id, user_id=1)

        room = manager.mid_join_room(room.room_id, user_id=3)
        assert 3 in room.players
        assert manager.get_user_room(3) == room.room_id

    def test_mid_join_waiting_room_raises(self, manager):
        room = manager.create_room(host_user_id=1, game_id="holdem", mode="vs",
                                   config={"max_players": 4})
        with pytest.raises(ValueError, match="not in progress"):
            manager.mid_join_room(room.room_id, user_id=2)

    def test_mid_join_nonexistent_room_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.mid_join_room("fake-room", user_id=1)

    def test_mid_join_full_room_raises(self, manager):
        room = manager.create_room(host_user_id=1, game_id="holdem", mode="vs",
                                   config={"max_players": 2})
        manager.join_room(room.room_id, user_id=2)
        manager.set_ready(room.room_id, user_id=1)
        manager.set_ready(room.room_id, user_id=2)
        manager.start_game(room.room_id, user_id=1)

        with pytest.raises(ValueError, match="full"):
            manager.mid_join_room(room.room_id, user_id=3)

    def test_mid_join_user_already_in_room_raises(self, manager):
        room = manager.create_room(host_user_id=1, game_id="holdem", mode="vs",
                                   config={"max_players": 4})
        manager.join_room(room.room_id, user_id=2)
        manager.set_ready(room.room_id, user_id=1)
        manager.set_ready(room.room_id, user_id=2)
        manager.start_game(room.room_id, user_id=1)

        with pytest.raises(ValueError, match="already in a room"):
            manager.mid_join_room(room.room_id, user_id=2)

    def test_mid_join_preserves_game_status(self, manager):
        room = manager.create_room(host_user_id=1, game_id="holdem", mode="vs",
                                   config={"max_players": 4})
        manager.join_room(room.room_id, user_id=2)
        manager.set_ready(room.room_id, user_id=1)
        manager.set_ready(room.room_id, user_id=2)
        manager.start_game(room.room_id, user_id=1)

        manager.mid_join_room(room.room_id, user_id=3)
        assert room.status == "playing"


# =============================================================================
# W11: TTL cleanup for stale rooms
# =============================================================================


class TestStaleRoomCleanup:
    """W11: Cleanup rooms older than TTL."""

    def test_fresh_rooms_not_cleaned(self, manager):
        manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        cleaned = manager.cleanup_stale_rooms()
        assert cleaned == 0
        assert len(manager.list_rooms()) == 1

    def test_stale_room_cleaned_up(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        room.created_at = datetime.utcnow() - timedelta(seconds=ROOM_TTL_SECONDS + 1)

        cleaned = manager.cleanup_stale_rooms()
        assert cleaned == 1
        assert len(manager.list_rooms()) == 0
        assert manager.get_user_room(1) is None

    def test_cleanup_preserves_fresh_rooms(self, manager):
        stale = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        stale.created_at = datetime.utcnow() - timedelta(seconds=ROOM_TTL_SECONDS + 1)
        manager.create_room(host_user_id=2, game_id="chess", mode="vs")  # fresh

        cleaned = manager.cleanup_stale_rooms()
        assert cleaned == 1
        rooms = manager.list_rooms()
        assert len(rooms) == 1
        assert manager.get_user_room(2) is not None

    def test_cleanup_frees_all_players_in_stale_room(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        manager.join_room(room.room_id, 2)
        room.created_at = datetime.utcnow() - timedelta(seconds=ROOM_TTL_SECONDS + 1)

        manager.cleanup_stale_rooms()
        assert manager.get_user_room(1) is None
        assert manager.get_user_room(2) is None


# =============================================================================
# Player names tracking
# =============================================================================


class TestPlayerNames:
    """Room tracks display names for each player."""

    def test_player_names_dict_exists(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        assert isinstance(room.player_names, dict)

    def test_player_names_set_externally(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        room.player_names[1] = "Alice"
        manager.join_room(room.room_id, user_id=2)
        room.player_names[2] = "Bob"
        assert room.player_names == {1: "Alice", 2: "Bob"}

    def test_mid_join_updates_player_names(self, manager):
        room = manager.create_room(host_user_id=1, game_id="holdem", mode="vs",
                                   config={"max_players": 4})
        manager.join_room(room.room_id, user_id=2)
        room.player_names[1] = "Alice"
        room.player_names[2] = "Bob"
        manager.set_ready(room.room_id, user_id=1)
        manager.set_ready(room.room_id, user_id=2)
        manager.start_game(room.room_id, user_id=1)
        # Mid-game join
        manager.mid_join_room(room.room_id, user_id=3)
        room.player_names[3] = "Charlie"
        assert room.player_names == {1: "Alice", 2: "Bob", 3: "Charlie"}
        assert 3 in room.players

    def test_close_room_cleans_player_names(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="vs")
        room.player_names[1] = "Alice"
        room_id = room.room_id
        manager.close_room(room_id)
        assert manager.get_room(room_id) is None


# =============================================================================
# Disconnect and Reconnect
# =============================================================================


def _make_playing_room(manager):
    """Helper: create a 2-player room in 'playing' status."""
    room = manager.create_room(host_user_id=1, game_id="chess", mode="race")
    manager.join_room(room.room_id, user_id=2)
    manager.set_ready(room.room_id, 1)
    manager.set_ready(room.room_id, 2)
    manager.start_game(room.room_id, 1)
    return room


class TestDisconnectReconnect:
    """Tests for disconnect marking, reconnect windows, and expiry."""

    def test_mark_disconnected_playing_room(self, manager):
        room = _make_playing_room(manager)
        result = manager.mark_disconnected(room.room_id, 2)
        assert result is True
        assert 2 in room.disconnected_players
        assert 2 in room.disconnect_times
        assert 2 in room.players  # still in room

    def test_mark_disconnected_waiting_room_fails(self, manager):
        room = manager.create_room(host_user_id=1, game_id="chess", mode="race")
        result = manager.mark_disconnected(room.room_id, 1)
        assert result is False

    def test_mark_disconnected_nonexistent_room(self, manager):
        result = manager.mark_disconnected("fake-room", 1)
        assert result is False

    def test_mark_disconnected_player_not_in_room(self, manager):
        room = _make_playing_room(manager)
        result = manager.mark_disconnected(room.room_id, 99)
        assert result is False

    def test_reconnect_player_success(self, manager):
        room = _make_playing_room(manager)
        manager.mark_disconnected(room.room_id, 2)
        reconnected = manager.reconnect_player(room.room_id, 2)
        assert reconnected is room
        assert 2 not in room.disconnected_players
        assert 2 not in room.disconnect_times
        assert 2 in room.players

    def test_reconnect_player_not_disconnected(self, manager):
        room = _make_playing_room(manager)
        result = manager.reconnect_player(room.room_id, 2)
        assert result is None

    def test_reconnect_player_nonexistent_room(self, manager):
        result = manager.reconnect_player("fake-room", 2)
        assert result is None

    def test_reconnect_window_expired(self, manager):
        room = _make_playing_room(manager)
        manager.mark_disconnected(room.room_id, 2)
        # Push disconnect time past the window
        room.disconnect_times[2] = (
            datetime.utcnow() - timedelta(seconds=RECONNECT_WINDOW_SECONDS + 10)
        )
        result = manager.reconnect_player(room.room_id, 2)
        assert result is None

    def test_reconnect_within_window(self, manager):
        room = _make_playing_room(manager)
        manager.mark_disconnected(room.room_id, 2)
        # Still within window
        room.disconnect_times[2] = (
            datetime.utcnow() - timedelta(seconds=RECONNECT_WINDOW_SECONDS - 10)
        )
        result = manager.reconnect_player(room.room_id, 2)
        assert result is room

    def test_get_pending_rejoin_found(self, manager):
        room = _make_playing_room(manager)
        manager.mark_disconnected(room.room_id, 2)
        pending = manager.get_pending_rejoin(2)
        assert pending is room

    def test_get_pending_rejoin_no_disconnect(self, manager):
        _make_playing_room(manager)
        pending = manager.get_pending_rejoin(2)
        assert pending is None

    def test_get_pending_rejoin_expired_cleans_up(self, manager):
        room = _make_playing_room(manager)
        manager.mark_disconnected(room.room_id, 2)
        room.disconnect_times[2] = (
            datetime.utcnow() - timedelta(seconds=RECONNECT_WINDOW_SECONDS + 10)
        )
        pending = manager.get_pending_rejoin(2)
        assert pending is None
        # Player should be removed from room
        assert 2 not in room.players
        assert manager.get_user_room(2) is None

    def test_get_pending_rejoin_unknown_user(self, manager):
        assert manager.get_pending_rejoin(999) is None

    def test_expire_disconnected_players_removes_expired(self, manager):
        room = _make_playing_room(manager)
        manager.mark_disconnected(room.room_id, 2)
        room.disconnect_times[2] = (
            datetime.utcnow() - timedelta(seconds=RECONNECT_WINDOW_SECONDS + 10)
        )
        expired = manager.expire_disconnected_players(room.room_id)
        assert expired == [2]
        assert 2 not in room.players
        assert 2 not in room.disconnected_players
        assert manager.get_user_room(2) is None

    def test_expire_disconnected_nobody_expired(self, manager):
        room = _make_playing_room(manager)
        manager.mark_disconnected(room.room_id, 2)
        # Just disconnected — not expired yet
        expired = manager.expire_disconnected_players(room.room_id)
        assert expired == []
        assert 2 in room.players

    def test_expire_disconnected_nonexistent_room(self, manager):
        expired = manager.expire_disconnected_players("nonexistent")
        assert expired == []

    def test_reconnect_preserves_room_state(self, manager):
        room = _make_playing_room(manager)
        room.player_names[2] = "Bob"
        manager.mark_disconnected(room.room_id, 2)
        reconnected = manager.reconnect_player(room.room_id, 2)
        assert reconnected.player_names[2] == "Bob"
        assert reconnected.status == "playing"

    def test_get_rooms_for_disconnected_player(self, manager):
        room = _make_playing_room(manager)
        manager.mark_disconnected(room.room_id, 2)
        # Player is still in the room
        rooms = manager.get_rooms_for_player(2)
        assert len(rooms) == 1
        assert rooms[0].room_id == room.room_id
