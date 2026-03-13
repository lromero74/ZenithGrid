"""
Game WebSocket message handler.

Routes game:* messages from the WebSocket endpoint to the GameRoomManager
and broadcasts state changes to room participants.
"""

import asyncio
import logging

from fastapi import WebSocket

from app.services.game_room_manager import game_room_manager

logger = logging.getLogger(__name__)

MULTIPLAYER_PERMISSION = "games:multiplayer"


async def handle_game_message(
    ws_manager, websocket: WebSocket, user_id: int, msg: dict,
    user_permissions: set[str] | None = None,
    display_name: str | None = None,
):
    """Route a game message to the appropriate handler."""
    msg_type = msg.get("type", "")
    handlers = {
        "game:create": _handle_create,
        "game:join": _handle_join,
        "game:mid_join": _handle_mid_join,
        "game:rejoin": _handle_rejoin,
        "game:leave": _handle_leave,
        "game:forfeit": _handle_forfeit,
        "game:ready": _handle_ready,
        "game:start": _handle_start,
        "game:action": _handle_action,
        "game:state": _handle_state_update,
        "game:invite": _handle_invite,
        "game:join_friend": _handle_join_friend,
        "game:check_room": _handle_check_room,
        "game:update_config": _handle_update_config,
        "game:chat": _handle_chat,
        "game:back_to_lobby": _handle_back_to_lobby,
    }

    handler = handlers.get(msg_type)
    if not handler:
        await websocket.send_json({"type": "game:error", "error": f"Unknown message type: {msg_type}"})
        return

    # RBAC: create/join/mid_join require games:multiplayer permission
    if msg_type in ("game:create", "game:join", "game:mid_join", "game:rejoin", "game:join_friend"):
        perms = user_permissions or set()
        if MULTIPLAYER_PERMISSION not in perms:
            await websocket.send_json({
                "type": "game:error",
                "error": "You do not have permission to play multiplayer games",
            })
            return

    try:
        await handler(ws_manager, websocket, user_id, msg, display_name or f"Player {user_id}")
    except ValueError as e:
        await websocket.send_json({"type": "game:error", "error": str(e)})
    except Exception as e:
        logger.error(f"Game message error: {e}", exc_info=True)
        await websocket.send_json({"type": "game:error", "error": "Internal error"})


def _build_player_names(room) -> dict[int, str]:
    """Build a player_id -> display_name mapping for the room."""
    return {pid: room.player_names.get(pid, f"Player {pid}") for pid in room.players}


async def _send_existing_room(websocket, user_id, room):
    """Send existing room info when user is already in a room."""
    is_host = user_id == room.host_user_id
    await websocket.send_json({
        "type": "game:already_in_room",
        "roomId": room.room_id,
        "gameId": room.game_id,
        "mode": room.mode,
        "status": room.status,
        "players": sorted(room.players),
        "playerNames": _build_player_names(room),
        "config": room.config,
        "hostUserId": room.host_user_id,
        "isHost": is_host,
        "readyPlayers": sorted(room.ready_players),
    })


def _clean_stale_user_room(user_id: int, target_game_id: str | None = None) -> bool:
    """Remove stale/finished/different-game room reference. Returns True if cleaned.

    If target_game_id is provided and the user is in a *waiting* room for a
    different game, auto-leave that room so they can join the new one.
    """
    existing_room_id = game_room_manager.get_user_room(user_id)
    if not existing_room_id:
        return False
    existing_room = game_room_manager.get_room(existing_room_id)
    if existing_room is None:
        # Stale reference — room was cleaned up but user mapping remained
        game_room_manager._user_rooms.pop(user_id, None)
        return True
    if existing_room.status == "finished":
        # Game is over — clean up so user can join/create a new room
        game_room_manager.leave_room(existing_room_id, user_id)
        return True
    # If user is in a room for a different game, auto-leave it.
    # They've navigated away and are trying to start something new.
    if (target_game_id and existing_room.game_id != target_game_id):
        game_room_manager.leave_room(existing_room_id, user_id)
        logger.info(
            f"Auto-left room {existing_room_id} ({existing_room.game_id}, "
            f"status={existing_room.status}) for user {user_id} "
            f"switching to {target_game_id}"
        )
        return True
    return False


async def _handle_create(ws_manager, websocket, user_id, msg, display_name):
    game_id = msg.get("gameId")
    mode = msg.get("mode", "vs")
    config = msg.get("config", {})

    if not game_id:
        await websocket.send_json({"type": "game:error", "error": "gameId required"})
        return

    # If user is already in a room, handle gracefully
    existing_room_id = game_room_manager.get_user_room(user_id)
    if existing_room_id:
        if not _clean_stale_user_room(user_id, target_game_id=game_id):
            # Room is still active (waiting/playing) — show it
            existing_room = game_room_manager.get_room(existing_room_id)
            if existing_room:
                await _send_existing_room(websocket, user_id, existing_room)
                return

    room = game_room_manager.create_room(
        host_user_id=user_id,
        game_id=game_id,
        mode=mode,
        config=config,
    )
    room.player_names[user_id] = display_name
    await websocket.send_json({
        "type": "game:created",
        "roomId": room.room_id,
        "gameId": room.game_id,
        "mode": room.mode,
        "players": list(room.players),
        "playerNames": _build_player_names(room),
    })


async def _handle_join(ws_manager, websocket, user_id, msg, display_name):
    room_id = msg.get("roomId")
    if not room_id:
        await websocket.send_json({"type": "game:error", "error": "roomId required"})
        return

    # Look up target room's game_id for stale room cleanup
    target_room = game_room_manager.get_room(room_id)
    target_game_id = target_room.game_id if target_room else None

    # If user is already in a room, handle gracefully
    existing_room_id = game_room_manager.get_user_room(user_id)
    if existing_room_id:
        if existing_room_id == room_id:
            # Already in the target room — just resend the join info
            existing_room = game_room_manager.get_room(existing_room_id)
            if existing_room:
                await _send_existing_room(websocket, user_id, existing_room)
                return
        # In a different room — auto-leave it so they can join the target
        if not _clean_stale_user_room(user_id, target_game_id=target_game_id):
            # Stale cleanup didn't help (same game, active room) — force leave
            game_room_manager.leave_room(existing_room_id, user_id)
            logger.info(
                f"Force-left room {existing_room_id} for user {user_id} "
                f"to join invited room {room_id}"
            )

    room = game_room_manager.join_room(room_id, user_id)
    room.player_names[user_id] = display_name

    # Notify the joiner
    await websocket.send_json({
        "type": "game:joined",
        "roomId": room.room_id,
        "gameId": room.game_id,
        "players": list(room.players),
        "playerNames": _build_player_names(room),
        "config": {**room.config, "mode": room.mode},
    })

    # Notify existing players
    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:player_joined",
            "roomId": room.room_id,
            "playerId": user_id,
            "playerName": display_name,
            "players": list(room.players),
            "playerNames": _build_player_names(room),
        },
        exclude_user=user_id,
    )


async def _handle_mid_join(ws_manager, websocket, user_id, msg, display_name):
    """Join an in-progress game (replaces an AI seat)."""
    room_id = msg.get("roomId")
    if not room_id:
        await websocket.send_json({"type": "game:error", "error": "roomId required"})
        return

    # Look up target room's game_id for stale room cleanup
    target_room = game_room_manager.get_room(room_id)
    target_game_id = target_room.game_id if target_room else None

    # If user is already in a room, handle gracefully
    existing_room_id = game_room_manager.get_user_room(user_id)
    if existing_room_id:
        if existing_room_id == room_id:
            existing_room = game_room_manager.get_room(existing_room_id)
            if existing_room:
                await _send_existing_room(websocket, user_id, existing_room)
                return
        if not _clean_stale_user_room(user_id, target_game_id=target_game_id):
            game_room_manager.leave_room(existing_room_id, user_id)
            logger.info(
                f"Force-left room {existing_room_id} for user {user_id} "
                f"to mid-join room {room_id}"
            )

    room = game_room_manager.mid_join_room(room_id, user_id)
    room.player_names[user_id] = display_name

    # Notify the joiner
    await websocket.send_json({
        "type": "game:mid_joined",
        "roomId": room.room_id,
        "gameId": room.game_id,
        "players": list(room.players),
        "playerNames": _build_player_names(room),
    })

    # Notify existing players that a new human joined mid-game
    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:mid_player_joined",
            "roomId": room.room_id,
            "playerId": user_id,
            "playerName": display_name,
            "players": list(room.players),
            "playerNames": _build_player_names(room),
        },
        exclude_user=user_id,
    )


async def _handle_rejoin(ws_manager, websocket, user_id, msg, display_name):
    """Reconnect a disconnected player to their in-progress game."""
    room_id = msg.get("roomId")
    if not room_id:
        # Auto-detect: check if user has a pending rejoin
        room = game_room_manager.get_pending_rejoin(user_id)
        if not room:
            await websocket.send_json({"type": "game:rejoin_failed", "error": "No game to rejoin"})
            return
        room_id = room.room_id

    room = game_room_manager.reconnect_player(room_id, user_id)
    if not room:
        await websocket.send_json({"type": "game:rejoin_failed", "error": "Reconnect window expired"})
        return

    room.player_names[user_id] = display_name

    # Send full game state to reconnected player
    await websocket.send_json({
        "type": "game:rejoin_success",
        "roomId": room.room_id,
        "gameId": room.game_id,
        "mode": room.mode,
        "players": list(room.players),
        "playerNames": _build_player_names(room),
        "config": room.config,
    })

    # Notify other players that the disconnected player is back
    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:player_reconnected",
            "roomId": room.room_id,
            "playerId": user_id,
            "playerName": display_name,
        },
        exclude_user=user_id,
    )


async def _handle_leave(ws_manager, websocket, user_id, msg, display_name):
    room_id = msg.get("roomId")
    if not room_id:
        return

    room = game_room_manager.get_room(room_id)
    if not room:
        return

    players_before = set(room.players)
    is_host = user_id == room.host_user_id
    remaining = players_before - {user_id}

    # If host leaves during an active game with remaining players,
    # transfer host instead of closing the room (avoids disrupting
    # a still-playing opponent in spectator/survival mode).
    if is_host and room.status == "playing" and remaining:
        new_host = min(remaining)  # deterministic pick
        room.host_user_id = new_host
        room.players.discard(user_id)
        room.ready_players.discard(user_id)
        game_room_manager._user_rooms.pop(user_id, None)
        await websocket.send_json({"type": "game:left", "roomId": room_id})
        await ws_manager.send_to_room(
            room.players,
            {
                "type": "game:player_left",
                "roomId": room_id,
                "playerId": user_id,
                "players": list(room.players),
                "playerNames": _build_player_names(room),
                "hostUserId": new_host,
            },
        )
        return

    game_room_manager.leave_room(room_id, user_id)
    await websocket.send_json({"type": "game:left", "roomId": room_id})

    if is_host:
        # Room was closed — notify all remaining players
        await ws_manager.send_to_room(
            remaining,
            {"type": "game:room_closed", "roomId": room_id, "reason": "Host left"},
        )
    else:
        await ws_manager.send_to_room(
            room.players,
            {
                "type": "game:player_left",
                "roomId": room_id,
                "playerId": user_id,
                "players": list(room.players),
                "playerNames": _build_player_names(room),
            },
        )


async def _handle_forfeit(ws_manager, websocket, user_id, msg, display_name):
    """Player intentionally forfeits — counts as a loss in scoring/tournaments."""
    room_id = msg.get("roomId")
    if not room_id:
        return

    room = game_room_manager.get_room(room_id)
    if not room or room.status != "playing":
        return

    if user_id not in room.players:
        return

    player_name = room.player_names.get(user_id, display_name)

    # Broadcast forfeit to all players (game:action with type forfeit)
    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:action",
            "roomId": room_id,
            "playerId": user_id,
            "action": {"type": "race_forfeit", "playerName": player_name},
            "sequence": game_room_manager.record_action(room_id, user_id, {"type": "race_forfeit"}),
        },
    )

    # Notify with a dedicated message for UI handling
    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:player_forfeit",
            "roomId": room_id,
            "playerId": user_id,
            "playerName": player_name,
            "exit_type": "forfeit",
        },
    )


async def handle_player_disconnect(ws_manager, user_id: int):
    """Called when a WebSocket disconnects — mark player as disconnected.

    Connection loss is NOT a loss — the player is given a reconnect window
    (RECONNECT_WINDOW_SECONDS) to rejoin. The game is paused for remaining players.
    """
    from app.services.game_room_manager import RECONNECT_WINDOW_SECONDS

    for room in game_room_manager.get_rooms_for_player(user_id):
        if room.status != "playing":
            continue

        player_name = room.player_names.get(user_id, f"Player {user_id}")

        # Mark as disconnected (keep in room for reconnect window)
        game_room_manager.mark_disconnected(room.room_id, user_id)

        # Broadcast pause notification to remaining players
        await ws_manager.send_to_room(
            room.players,
            {
                "type": "game:player_disconnect",
                "roomId": room.room_id,
                "playerId": user_id,
                "playerName": player_name,
                "exit_type": "abend",
                "reconnectWindowSeconds": RECONNECT_WINDOW_SECONDS,
            },
            exclude_user=user_id,
        )


async def _handle_ready(ws_manager, websocket, user_id, msg, display_name):
    room_id = msg.get("roomId")
    if not room_id:
        return

    game_room_manager.set_ready(room_id, user_id)
    room = game_room_manager.get_room(room_id)

    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:player_ready",
            "roomId": room_id,
            "playerId": user_id,
            "readyPlayers": list(room.ready_players),
            "allReady": room.all_ready(),
        },
    )


async def _handle_start(ws_manager, websocket, user_id, msg, display_name):
    room_id = msg.get("roomId")
    if not room_id:
        return

    room = game_room_manager.start_game(room_id, user_id)

    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:started",
            "roomId": room_id,
            "gameId": room.game_id,
            "mode": room.mode,
            "players": list(room.players),
            "playerNames": _build_player_names(room),
            "config": {**room.config, "mode": room.mode},
        },
    )


async def _handle_action(ws_manager, websocket, user_id, msg, display_name):
    room_id = msg.get("roomId")
    action = msg.get("action", {})
    if not room_id:
        return

    # W2 fix: Strip any spoofed 'player' field from the action —
    # the server always uses the authenticated user_id as the source.
    # Clients should use msg.playerId (set by server) to identify the sender.

    seq = game_room_manager.record_action(room_id, user_id, action)
    room = game_room_manager.get_room(room_id)

    # Broadcast action to all players with server-authoritative playerId
    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:action",
            "roomId": room_id,
            "playerId": user_id,
            "action": action,
            "sequence": seq,
        },
    )


async def _handle_state_update(ws_manager, websocket, user_id, msg, display_name):
    """Handle state updates — used by race mode where clients report their state."""
    room_id = msg.get("roomId")
    state = msg.get("state", {})
    if not room_id:
        logger.debug(f"game:state from user {user_id}: no roomId")
        return

    room = game_room_manager.get_room(room_id)
    if not room or room.status != "playing":
        status = room.status if room else "N/A"
        logger.debug(f"game:state from user {user_id}: room={room_id} not playing (status={status})")
        return

    targets = room.players - {user_id}
    logger.info(f"game:state relay: user {user_id} → {targets} (room {room_id}, {len(str(state))} chars)")

    # In race mode, broadcast player's state to others
    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:player_state",
            "roomId": room_id,
            "playerId": user_id,
            "state": state,
        },
        exclude_user=user_id,
    )


async def _handle_invite(ws_manager, websocket, user_id, msg, display_name):
    """Send a game invite to a friend — delivers via their WS connection."""
    room_id = msg.get("roomId")
    target_user_id = msg.get("targetUserId")
    if not room_id or not target_user_id:
        return

    room = game_room_manager.get_room(room_id)
    if not room:
        await websocket.send_json({"type": "game:error", "error": "Room not found"})
        return

    if user_id != room.host_user_id:
        await websocket.send_json({"type": "game:error", "error": "Only the host can send invites"})
        return

    if room.status == "finished":
        await websocket.send_json({"type": "game:error", "error": "Game has already finished"})
        return

    if len(room.players) >= room.max_players:
        await websocket.send_json({"type": "game:error", "error": "Room is full"})
        return

    mid_game = room.status == "playing"

    # Send invite notification to the target user
    await ws_manager.send_to_user(target_user_id, {
        "type": "game:invite",
        "roomId": room_id,
        "gameId": room.game_id,
        "mode": room.mode,
        "fromUserId": user_id,
        "fromDisplayName": display_name,
        "midGame": mid_game,
    })

    await websocket.send_json({
        "type": "game:invite_sent",
        "roomId": room_id,
        "targetUserId": target_user_id,
    })


async def _handle_join_friend(ws_manager, websocket, user_id, msg, display_name):
    """Join a friend's game room without an invite.

    The user specifies the friend's user ID. Backend looks up their room,
    validates friendship, and joins them. Host gets a toast notification.
    """
    from app.database import async_session_maker
    from app.models.social import Friendship
    from sqlalchemy import or_, and_, select

    friend_user_id = msg.get("friendUserId")
    if not friend_user_id:
        await websocket.send_json({"type": "game:error", "error": "Missing friendUserId"})
        return

    # Look up target game from friend's room for stale room cleanup
    friend_room_id = game_room_manager.get_user_room(friend_user_id)
    friend_room = game_room_manager.get_room(friend_room_id) if friend_room_id else None
    target_game_id = friend_room.game_id if friend_room else None

    # If user is already in a room, handle gracefully
    existing_room_id = game_room_manager.get_user_room(user_id)
    if existing_room_id:
        if not _clean_stale_user_room(user_id, target_game_id=target_game_id):
            # Still in an active room — if it's the friend's room, send existing info.
            # If it's a different room (same game), leave it to join the friend.
            if existing_room_id == friend_room_id:
                existing_room = game_room_manager.get_room(existing_room_id)
                if existing_room:
                    await _send_existing_room(websocket, user_id, existing_room)
                    return
            else:
                # Leave old room so we can join the friend's room
                game_room_manager.leave_room(existing_room_id, user_id)
                logger.info(
                    f"Auto-left room {existing_room_id} for user {user_id} "
                    f"to join friend's room {friend_room_id}"
                )

    # Validate friendship
    async with async_session_maker() as db:
        result = await db.execute(
            select(Friendship).where(
                or_(
                    and_(Friendship.user_id == user_id, Friendship.friend_id == friend_user_id),
                    and_(Friendship.user_id == friend_user_id, Friendship.friend_id == user_id),
                )
            )
        )
        if not result.scalars().first():
            await websocket.send_json({"type": "game:error", "error": "You can only join a friend's game"})
            return

    # Find friend's room
    room_id = game_room_manager.get_user_room(friend_user_id)
    if not room_id:
        await websocket.send_json({"type": "game:error", "error": "Friend is not in a game room"})
        return

    room = game_room_manager.get_room(room_id)
    if not room:
        await websocket.send_json({"type": "game:error", "error": "Room not found"})
        return

    if room.status == "finished":
        await websocket.send_json({"type": "game:error", "error": "Game has already finished"})
        return

    if len(room.players) >= room.max_players:
        await websocket.send_json({"type": "game:error", "error": "Room is full"})
        return

    # Join the room (waiting or mid-game)
    if room.status == "playing":
        room = game_room_manager.mid_join_room(room_id, user_id)
    else:
        room = game_room_manager.join_room(room_id, user_id)

    room.player_names[user_id] = display_name

    # Notify the joiner
    await websocket.send_json({
        "type": "game:joined",
        "roomId": room_id,
        "players": sorted(room.players),
        "playerNames": room.player_names,
        "config": {**room.config, "mode": room.mode},
    })

    # Notify other players in the room
    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:player_joined",
            "roomId": room_id,
            "players": sorted(room.players),
            "playerNames": room.player_names,
        },
        exclude_user=user_id,
    )

    # Send toast notification to the host
    await ws_manager.send_to_user(room.host_user_id, {
        "type": "game:friend_joined",
        "roomId": room_id,
        "userId": user_id,
        "displayName": display_name,
    })
    logger.info(f"User {user_id} ({display_name}) joined friend {friend_user_id}'s room {room_id}")


async def _handle_check_room(ws_manager, websocket, user_id, msg, display_name):
    """Check if the user is currently in a game room (lobby or playing).

    Returns room info so the frontend can restore lobby state after navigation.
    No permission check needed — this is a read-only query about the user's own state.
    """
    room_id = game_room_manager.get_user_room(user_id)
    if not room_id:
        await websocket.send_json({"type": "game:no_room"})
        return

    room = game_room_manager.get_room(room_id)
    if not room:
        await websocket.send_json({"type": "game:no_room"})
        return

    await websocket.send_json({
        "type": "game:room_info",
        "roomId": room.room_id,
        "gameId": room.game_id,
        "status": room.status,
        "mode": room.mode,
        "players": sorted(room.players),
        "playerNames": _build_player_names(room),
        "config": {**room.config, "mode": room.mode},
    })


async def _handle_update_config(ws_manager, websocket, user_id, msg, display_name):
    """Host updates room config (e.g. difficulty) while in lobby."""
    room_id = msg.get("roomId")
    updates = msg.get("config", {})
    if not room_id or not updates:
        return

    room = game_room_manager.get_room(room_id)
    if not room or room.status != "waiting":
        return
    if room.host_user_id != user_id:
        await websocket.send_json({"type": "game:error", "error": "Only the host can change settings"})
        return

    # Handle mode change (updates room.mode + config)
    if "mode" in updates:
        new_mode = updates.pop("mode")
        if new_mode in ("vs", "race"):
            room.mode = new_mode
    if "race_type" in updates:
        room.config["race_type"] = updates.pop("race_type")

    # Merge remaining updates into room config
    room.config.update(updates)

    # Broadcast updated config to all players
    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:config_updated",
            "roomId": room_id,
            "config": {**room.config, "mode": room.mode},
        },
    )


async def _handle_chat(ws_manager, websocket, user_id, msg, display_name):
    """Relay a chat message to all players in the room (works in any room status)."""
    room_id = msg.get("roomId")
    text = msg.get("text", "").strip()
    if not room_id or not text:
        return

    room = game_room_manager.get_room(room_id)
    if not room or user_id not in room.players:
        return

    # Truncate to prevent abuse
    text = text[:500]

    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:chat",
            "roomId": room_id,
            "playerId": user_id,
            "playerName": display_name,
            "text": text,
        },
    )


async def _handle_back_to_lobby(ws_manager, websocket, user_id, msg, display_name):
    """Reset the room back to lobby state so players can play again.

    Any player in the room can trigger this. All players are notified
    so their frontends transition from 'playing' back to 'lobby'.
    """
    room_id = game_room_manager.get_user_room(user_id)
    if not room_id:
        await websocket.send_json({"type": "game:error", "error": "Not in a room"})
        return

    room = game_room_manager.get_room(room_id)
    if not room:
        await websocket.send_json({"type": "game:error", "error": "Room not found"})
        return

    try:
        game_room_manager.reset_to_lobby(room_id)
    except ValueError as e:
        await websocket.send_json({"type": "game:error", "error": str(e)})
        return

    broadcast = {
        "type": "game:lobby_reset",
        "roomId": room.room_id,
        "hostUserId": room.host_user_id,
        "players": sorted(room.players),
        "playerNames": _build_player_names(room),
        "config": {**room.config, "mode": room.mode},
    }
    await asyncio.gather(*(
        ws_manager.send_to_user(pid, broadcast) for pid in room.players
    ))
