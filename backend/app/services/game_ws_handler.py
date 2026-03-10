"""
Game WebSocket message handler.

Routes game:* messages from the WebSocket endpoint to the GameRoomManager
and broadcasts state changes to room participants.
"""

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
        "game:leave": _handle_leave,
        "game:ready": _handle_ready,
        "game:start": _handle_start,
        "game:action": _handle_action,
        "game:state": _handle_state_update,
        "game:invite": _handle_invite,
    }

    handler = handlers.get(msg_type)
    if not handler:
        await websocket.send_json({"type": "game:error", "error": f"Unknown message type: {msg_type}"})
        return

    # RBAC: create/join/mid_join require games:multiplayer permission
    if msg_type in ("game:create", "game:join", "game:mid_join"):
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


async def _handle_create(ws_manager, websocket, user_id, msg, display_name):
    game_id = msg.get("gameId")
    mode = msg.get("mode", "vs")
    config = msg.get("config", {})

    if not game_id:
        await websocket.send_json({"type": "game:error", "error": "gameId required"})
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

    room = game_room_manager.join_room(room_id, user_id)
    room.player_names[user_id] = display_name

    # Notify the joiner
    await websocket.send_json({
        "type": "game:joined",
        "roomId": room.room_id,
        "gameId": room.game_id,
        "players": list(room.players),
        "playerNames": _build_player_names(room),
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


async def _handle_leave(ws_manager, websocket, user_id, msg, display_name):
    room_id = msg.get("roomId")
    if not room_id:
        return

    room = game_room_manager.get_room(room_id)
    if not room:
        return

    players_before = set(room.players)
    is_host = user_id == room.host_user_id
    game_room_manager.leave_room(room_id, user_id)

    await websocket.send_json({"type": "game:left", "roomId": room_id})

    if is_host:
        # Room was closed — notify all remaining players
        await ws_manager.send_to_room(
            players_before - {user_id},
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
            "players": list(room.players),
            "playerNames": _build_player_names(room),
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
        return

    room = game_room_manager.get_room(room_id)
    if not room or room.status != "playing":
        return

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
