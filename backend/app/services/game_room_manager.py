"""
Game Room Manager — in-memory game room lifecycle management.

Manages creation, joining, leaving, readiness, starting, actions, and cleanup
of game rooms for multiplayer games. Rooms are ephemeral (in-memory only);
game results are persisted separately via game_result_service.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

DEFAULT_MAX_PLAYERS = 2
ROOM_TTL_SECONDS = 3600  # 1 hour — rooms older than this are cleaned up
RECONNECT_WINDOW_SECONDS = 60  # seconds to wait for disconnected player to rejoin


@dataclass
class GameRoom:
    """A single game room instance."""
    room_id: str
    game_id: str
    mode: str  # "vs" or "race"
    host_user_id: int
    config: Dict[str, Any] = field(default_factory=dict)
    players: Set[int] = field(default_factory=set)
    player_names: Dict[int, str] = field(default_factory=dict)
    ready_players: Set[int] = field(default_factory=set)
    state: Dict[str, Any] = field(default_factory=dict)
    sequence: int = 0
    status: str = "waiting"  # "waiting", "playing", "finished"
    disconnected_players: Set[int] = field(default_factory=set)
    disconnect_times: Dict[int, datetime] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None

    @property
    def max_players(self) -> int:
        return self.config.get("max_players", DEFAULT_MAX_PLAYERS)

    def all_ready(self) -> bool:
        return len(self.players) >= 2 and self.players == self.ready_players


class GameRoomManager:
    """Manages in-memory game rooms."""

    def __init__(self):
        self._rooms: Dict[str, GameRoom] = {}
        self._user_rooms: Dict[int, str] = {}  # user_id -> room_id

    def create_room(
        self,
        host_user_id: int,
        game_id: str,
        mode: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> GameRoom:
        """Create a new game room. Host is auto-added as a player."""
        if host_user_id in self._user_rooms:
            raise ValueError("User is already in a room")

        room_id = uuid.uuid4().hex[:16]
        room = GameRoom(
            room_id=room_id,
            game_id=game_id,
            mode=mode,
            host_user_id=host_user_id,
            config=config or {},
            players={host_user_id},
        )
        self._rooms[room_id] = room
        self._user_rooms[host_user_id] = room_id
        logger.info(f"Room {room_id} created by user {host_user_id} for {game_id} ({mode})")
        return room

    def get_room(self, room_id: str) -> Optional[GameRoom]:
        return self._rooms.get(room_id)

    def get_user_room(self, user_id: int) -> Optional[str]:
        return self._user_rooms.get(user_id)

    def get_rooms_for_player(self, user_id: int) -> List[GameRoom]:
        """Return all rooms the player is currently in."""
        room_id = self._user_rooms.get(user_id)
        if room_id and room_id in self._rooms:
            return [self._rooms[room_id]]
        return []

    def join_room(self, room_id: str, user_id: int) -> GameRoom:
        """Add a player to an existing room."""
        room = self._rooms.get(room_id)
        if not room:
            raise ValueError("Room not found")
        if room.status != "waiting":
            raise ValueError("Game has already started")
        if user_id in self._user_rooms:
            raise ValueError("User is already in a room")
        if len(room.players) >= room.max_players:
            raise ValueError("Room is full")

        room.players.add(user_id)
        self._user_rooms[user_id] = room_id
        logger.info(f"User {user_id} joined room {room_id}")
        return room

    def mid_join_room(self, room_id: str, user_id: int) -> GameRoom:
        """Join a room that is already playing (mid-game join to replace AI)."""
        room = self._rooms.get(room_id)
        if not room:
            raise ValueError("Room not found")
        if room.status != "playing":
            raise ValueError("Room is not in progress — use regular join")
        if user_id in self._user_rooms:
            raise ValueError("User is already in a room")
        if len(room.players) >= room.max_players:
            raise ValueError("Room is full")

        room.players.add(user_id)
        self._user_rooms[user_id] = room_id
        logger.info(f"User {user_id} mid-game joined room {room_id}")
        return room

    def mark_disconnected(self, room_id: str, user_id: int) -> bool:
        """Mark a player as disconnected (not removed) during an in-progress game.

        Returns True if marked, False if room not found or not playing.
        The player stays in the room and has RECONNECT_WINDOW_SECONDS to rejoin.
        """
        room = self._rooms.get(room_id)
        if not room or room.status != "playing":
            return False
        if user_id not in room.players:
            return False

        room.disconnected_players.add(user_id)
        room.disconnect_times[user_id] = datetime.utcnow()
        logger.info(f"User {user_id} marked disconnected in room {room_id}")
        return True

    def reconnect_player(self, room_id: str, user_id: int) -> Optional[GameRoom]:
        """Reconnect a disconnected player to their room.

        Returns the room if reconnection succeeded, None otherwise.
        """
        room = self._rooms.get(room_id)
        if not room:
            return None
        if user_id not in room.players:
            return None
        if user_id not in room.disconnected_players:
            return None

        # Check if reconnect window has expired
        dc_time = room.disconnect_times.get(user_id)
        if dc_time:
            elapsed = (datetime.utcnow() - dc_time).total_seconds()
            if elapsed > RECONNECT_WINDOW_SECONDS:
                logger.info(f"Reconnect window expired for user {user_id} in room {room_id}")
                return None

        room.disconnected_players.discard(user_id)
        room.disconnect_times.pop(user_id, None)
        logger.info(f"User {user_id} reconnected to room {room_id}")
        return room

    def get_pending_rejoin(self, user_id: int) -> Optional[GameRoom]:
        """Check if a user has a room they can rejoin after disconnect.

        Returns the room if found and reconnect window is still open.
        """
        room_id = self._user_rooms.get(user_id)
        if not room_id:
            return None
        room = self._rooms.get(room_id)
        if not room or room.status != "playing":
            return None
        if user_id not in room.disconnected_players:
            return None

        # Check window
        dc_time = room.disconnect_times.get(user_id)
        if dc_time:
            elapsed = (datetime.utcnow() - dc_time).total_seconds()
            if elapsed > RECONNECT_WINDOW_SECONDS:
                # Window expired — clean up
                self.leave_room(room_id, user_id)
                return None

        return room

    def expire_disconnected_players(self, room_id: str) -> List[int]:
        """Remove players whose reconnect window has expired. Returns expired user IDs."""
        room = self._rooms.get(room_id)
        if not room:
            return []

        now = datetime.utcnow()
        expired = []
        for uid in list(room.disconnected_players):
            dc_time = room.disconnect_times.get(uid)
            if dc_time and (now - dc_time).total_seconds() > RECONNECT_WINDOW_SECONDS:
                expired.append(uid)
                room.disconnected_players.discard(uid)
                room.disconnect_times.pop(uid, None)
                room.players.discard(uid)
                self._user_rooms.pop(uid, None)
                logger.info(f"Reconnect window expired — removed user {uid} from room {room_id}")

        return expired

    def leave_room(self, room_id: str, user_id: int) -> None:
        """Remove a player from a room. If host leaves, room is closed."""
        room = self._rooms.get(room_id)
        if not room:
            return

        if user_id == room.host_user_id:
            # Host leaving closes the room
            self.close_room(room_id)
            return

        room.players.discard(user_id)
        room.ready_players.discard(user_id)
        self._user_rooms.pop(user_id, None)
        logger.info(f"User {user_id} left room {room_id}")

    def set_ready(self, room_id: str, user_id: int) -> None:
        """Mark a player as ready."""
        room = self._rooms.get(room_id)
        if not room:
            raise ValueError("Room not found")
        if user_id not in room.players:
            raise ValueError("User not in room")
        room.ready_players.add(user_id)

    def start_game(self, room_id: str, user_id: int) -> GameRoom:
        """Start the game. Only the host can start, and all players must be ready."""
        room = self._rooms.get(room_id)
        if not room:
            raise ValueError("Room not found")
        if user_id != room.host_user_id:
            raise ValueError("Only the host can start the game")
        if len(room.players) < 2:
            raise ValueError("Need at least 2 players to start")
        if not room.all_ready():
            raise ValueError("Cannot start: not all players ready")

        room.status = "playing"
        room.started_at = datetime.utcnow()
        logger.info(f"Game started in room {room_id}")
        return room

    def record_action(self, room_id: str, user_id: int, action: Dict[str, Any]) -> int:
        """Record a game action. Returns the sequence number."""
        room = self._rooms.get(room_id)
        if not room:
            raise ValueError("Room not found")
        if room.status != "playing":
            raise ValueError("Game is not in progress")
        if user_id not in room.players:
            raise ValueError("User not in room")

        room.sequence += 1
        return room.sequence

    def update_state(self, room_id: str, state: Dict[str, Any]) -> None:
        """Update the authoritative game state."""
        room = self._rooms.get(room_id)
        if not room:
            raise ValueError("Room not found")
        room.state = state

    def finish_game(self, room_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Mark a game as finished with results."""
        room = self._rooms.get(room_id)
        if not room:
            raise ValueError("Room not found")

        room.status = "finished"
        room.finished_at = datetime.utcnow()
        room.result = result
        logger.info(f"Game finished in room {room_id}")
        return result

    def close_room(self, room_id: str) -> None:
        """Remove a room and clean up all player references."""
        room = self._rooms.pop(room_id, None)
        if not room:
            return

        for player_id in room.players:
            self._user_rooms.pop(player_id, None)
        logger.info(f"Room {room_id} closed")

    def list_rooms(self, game_id: Optional[str] = None) -> List[GameRoom]:
        """List all rooms, optionally filtered by game_id."""
        rooms = list(self._rooms.values())
        if game_id:
            rooms = [r for r in rooms if r.game_id == game_id]
        return rooms

    def cleanup_stale_rooms(self) -> int:
        """Remove rooms older than ROOM_TTL_SECONDS. Returns count of cleaned rooms."""
        now = datetime.utcnow()
        stale_ids = [
            room_id for room_id, room in self._rooms.items()
            if (now - room.created_at).total_seconds() > ROOM_TTL_SECONDS
        ]
        for room_id in stale_ids:
            self.close_room(room_id)
        if stale_ids:
            logger.info(f"Cleaned up {len(stale_ids)} stale game rooms")
        return len(stale_ids)


# Global singleton
game_room_manager = GameRoomManager()
