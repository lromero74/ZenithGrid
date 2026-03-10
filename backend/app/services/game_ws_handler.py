"""
Game WebSocket message handler.

Routes game:* messages from the WebSocket endpoint to the GameRoomManager
and broadcasts state changes to room participants.
"""

import logging

from fastapi import WebSocket

from app.services.game_room_manager import game_room_manager

logger = logging.getLogger(__name__)


async def handle_game_message(ws_manager, websocket: WebSocket, user_id: int, msg: dict):
    """Route a game message to the appropriate handler."""
    msg_type = msg.get("type", "")
    handlers = {
        "game:create": _handle_create,
        "game:join": _handle_join,
        "game:leave": _handle_leave,
        "game:ready": _handle_ready,
        "game:start": _handle_start,
        "game:action": _handle_action,
        "game:state": _handle_state_update,
    }

    handler = handlers.get(msg_type)
    if not handler:
        await websocket.send_json({"type": "game:error", "error": f"Unknown message type: {msg_type}"})
        return

    try:
        await handler(ws_manager, websocket, user_id, msg)
    except ValueError as e:
        await websocket.send_json({"type": "game:error", "error": str(e)})
    except Exception as e:
        logger.error(f"Game message error: {e}", exc_info=True)
        await websocket.send_json({"type": "game:error", "error": "Internal error"})


async def _handle_create(ws_manager, websocket, user_id, msg):
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
    await websocket.send_json({
        "type": "game:created",
        "roomId": room.room_id,
        "gameId": room.game_id,
        "mode": room.mode,
        "players": list(room.players),
    })


async def _handle_join(ws_manager, websocket, user_id, msg):
    room_id = msg.get("roomId")
    if not room_id:
        await websocket.send_json({"type": "game:error", "error": "roomId required"})
        return

    room = game_room_manager.join_room(room_id, user_id)

    # Notify the joiner
    await websocket.send_json({
        "type": "game:joined",
        "roomId": room.room_id,
        "gameId": room.game_id,
        "players": list(room.players),
    })

    # Notify existing players
    await ws_manager.send_to_room(
        room.players,
        {
            "type": "game:player_joined",
            "roomId": room.room_id,
            "playerId": user_id,
            "players": list(room.players),
        },
        exclude_user=user_id,
    )


async def _handle_leave(ws_manager, websocket, user_id, msg):
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
            },
        )


async def _handle_ready(ws_manager, websocket, user_id, msg):
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


async def _handle_start(ws_manager, websocket, user_id, msg):
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
        },
    )


async def _handle_action(ws_manager, websocket, user_id, msg):
    room_id = msg.get("roomId")
    action = msg.get("action", {})
    if not room_id:
        return

    seq = game_room_manager.record_action(room_id, user_id, action)
    room = game_room_manager.get_room(room_id)

    # Broadcast action to all players (including sender for confirmation)
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


async def _handle_state_update(ws_manager, websocket, user_id, msg):
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
