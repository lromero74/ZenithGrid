"""
Tests for backend/app/services/game_room_manager.py

Covers room lifecycle, player management, message routing,
and game state management.
"""

import pytest
from unittest.mock import AsyncMock

from app.services.game_room_manager import GameRoomManager, GameRoom


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
