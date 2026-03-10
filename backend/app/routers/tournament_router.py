"""
Tournament API Router

Endpoints for creating, joining, starting, and managing multiplayer tournaments.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_permission, Perm
from app.database import get_db
from app.models import User
from app.models.social import (
    Tournament,
    TournamentDeleteVote,
    TournamentPlayer,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tournaments", tags=["tournaments"])


# ----- Pydantic Schemas -----


class TournamentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    game_ids: list[str] = Field(..., min_length=1)
    config: Optional[dict] = None


# ----- Endpoints -----


@router.post("")
async def create_tournament(
    body: TournamentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Create a new tournament. Creator is automatically enrolled."""
    tournament = Tournament(
        name=body.name,
        creator_id=current_user.id,
        game_ids=body.game_ids,
        config=body.config,
        status="pending",
    )
    db.add(tournament)
    await db.commit()

    # Auto-enroll creator
    db.add(TournamentPlayer(tournament_id=tournament.id, user_id=current_user.id))
    await db.commit()

    return {
        "id": tournament.id,
        "name": tournament.name,
        "creator_id": tournament.creator_id,
        "game_ids": tournament.game_ids,
        "config": tournament.config,
        "status": tournament.status,
        "created_at": tournament.created_at.isoformat() if tournament.created_at else None,
    }


@router.get("")
async def list_tournaments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List tournaments the current user has joined (excludes archived)."""
    # Join with creator User to get creator_name
    result = await db.execute(
        select(Tournament, User.display_name)
        .join(User, Tournament.creator_id == User.id)
        .join(TournamentPlayer, TournamentPlayer.tournament_id == Tournament.id)
        .where(
            TournamentPlayer.user_id == current_user.id,
            TournamentPlayer.archived.is_(False),
        )
        .order_by(desc(Tournament.created_at))
    )
    rows = result.all()

    items = []
    for t, creator_name in rows:
        # Get player count
        count_q = await db.execute(
            select(func.count(TournamentPlayer.id)).where(
                TournamentPlayer.tournament_id == t.id
            )
        )
        player_count = count_q.scalar() or 0

        items.append({
            "id": t.id,
            "name": t.name,
            "creator_id": t.creator_id,
            "creator_name": creator_name,
            "game_ids": t.game_ids,
            "status": t.status,
            "player_count": player_count,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "started_at": t.started_at.isoformat() if t.started_at else None,
        })

    return items


@router.get("/{tournament_id}")
async def get_tournament_detail(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get tournament details including player list. Must be a participant."""
    result = await db.execute(
        select(Tournament, User.display_name)
        .join(User, Tournament.creator_id == User.id)
        .where(Tournament.id == tournament_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Tournament not found")
    tournament, creator_name = row

    # Verify current user is a participant
    participant_check = await db.execute(
        select(TournamentPlayer.id).where(
            TournamentPlayer.tournament_id == tournament_id,
            TournamentPlayer.user_id == current_user.id,
        )
    )
    if participant_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a participant in this tournament")

    # Fetch players
    players_q = await db.execute(
        select(TournamentPlayer, User)
        .join(User, TournamentPlayer.user_id == User.id)
        .where(TournamentPlayer.tournament_id == tournament_id)
        .order_by(desc(TournamentPlayer.total_score))
    )
    players = [
        {
            "user_id": player.user_id,
            "display_name": user.display_name,
            "total_score": player.total_score,
            "placement": player.placement,
            "joined_at": player.joined_at.isoformat() if player.joined_at else None,
        }
        for player, user in players_q.all()
    ]

    return {
        "id": tournament.id,
        "name": tournament.name,
        "creator_id": tournament.creator_id,
        "creator_name": creator_name,
        "game_ids": tournament.game_ids,
        "config": tournament.config,
        "status": tournament.status,
        "player_count": len(players),
        "created_at": tournament.created_at.isoformat() if tournament.created_at else None,
        "started_at": tournament.started_at.isoformat() if tournament.started_at else None,
        "finished_at": tournament.finished_at.isoformat() if tournament.finished_at else None,
        "players": players,
    }


@router.post("/{tournament_id}/join")
async def join_tournament(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Join a pending tournament."""
    result = await db.execute(
        select(Tournament).where(Tournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if tournament.status != "pending":
        raise HTTPException(status_code=400, detail="Cannot join a tournament that has already started")

    # Check if already joined
    existing = await db.execute(
        select(TournamentPlayer.id).where(
            TournamentPlayer.tournament_id == tournament_id,
            TournamentPlayer.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Already joined this tournament")

    db.add(TournamentPlayer(tournament_id=tournament_id, user_id=current_user.id))
    await db.commit()
    return {"status": "joined", "tournament_id": tournament_id}


@router.post("/{tournament_id}/leave")
async def leave_tournament(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Leave a tournament (only if it hasn't started yet)."""
    result = await db.execute(
        select(Tournament).where(Tournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if tournament.status != "pending":
        raise HTTPException(status_code=400, detail="Cannot leave a tournament that has already started")

    # Find player entry
    player_result = await db.execute(
        select(TournamentPlayer).where(
            TournamentPlayer.tournament_id == tournament_id,
            TournamentPlayer.user_id == current_user.id,
        )
    )
    player = player_result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Not joined in this tournament")

    await db.delete(player)
    await db.commit()
    return {"status": "left", "tournament_id": tournament_id}


@router.post("/{tournament_id}/start")
async def start_tournament(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Start a tournament. Only the creator can start it."""
    result = await db.execute(
        select(Tournament).where(Tournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if tournament.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the tournament creator can start it")

    if tournament.status != "pending":
        raise HTTPException(status_code=400, detail="Tournament is not in pending state")

    # Need at least 2 players
    player_count = await db.execute(
        select(func.count(TournamentPlayer.id)).where(
            TournamentPlayer.tournament_id == tournament_id
        )
    )
    count = player_count.scalar() or 0
    if count < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 players to start")

    tournament.status = "active"
    tournament.started_at = datetime.utcnow()
    await db.commit()

    return {
        "id": tournament.id,
        "status": tournament.status,
        "started_at": tournament.started_at.isoformat(),
    }


@router.post("/{tournament_id}/archive")
async def archive_tournament(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Archive a tournament for the current user (hides from list)."""
    result = await db.execute(
        select(TournamentPlayer).where(
            TournamentPlayer.tournament_id == tournament_id,
            TournamentPlayer.user_id == current_user.id,
        )
    )
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Not a participant in this tournament")

    player.archived = True
    await db.commit()
    return {"status": "archived", "tournament_id": tournament_id}


@router.post("/{tournament_id}/vote-delete")
async def vote_delete_tournament(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Vote to delete a tournament. Requires majority of players to vote
    before the tournament is actually deleted.
    """
    # Check tournament exists
    result = await db.execute(
        select(Tournament).where(Tournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Check user is a participant
    player_check = await db.execute(
        select(TournamentPlayer.id).where(
            TournamentPlayer.tournament_id == tournament_id,
            TournamentPlayer.user_id == current_user.id,
        )
    )
    if player_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Not a participant in this tournament")

    # Check for duplicate vote
    existing_vote = await db.execute(
        select(TournamentDeleteVote.id).where(
            TournamentDeleteVote.tournament_id == tournament_id,
            TournamentDeleteVote.user_id == current_user.id,
        )
    )
    if existing_vote.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Already voted to delete")

    # Cast vote
    db.add(TournamentDeleteVote(tournament_id=tournament_id, user_id=current_user.id))
    await db.commit()

    # Count votes and players
    vote_count_q = await db.execute(
        select(func.count(TournamentDeleteVote.id)).where(
            TournamentDeleteVote.tournament_id == tournament_id
        )
    )
    vote_count = vote_count_q.scalar() or 0

    player_count_q = await db.execute(
        select(func.count(TournamentPlayer.id)).where(
            TournamentPlayer.tournament_id == tournament_id
        )
    )
    player_count = player_count_q.scalar() or 0

    # Majority check: more than half must vote
    majority_needed = (player_count // 2) + 1
    if vote_count >= majority_needed:
        # Delete the tournament (cascades to players and votes)
        await db.execute(
            delete(TournamentDeleteVote).where(
                TournamentDeleteVote.tournament_id == tournament_id
            )
        )
        await db.execute(
            delete(TournamentPlayer).where(
                TournamentPlayer.tournament_id == tournament_id
            )
        )
        await db.delete(tournament)
        await db.commit()
        return {"votes": vote_count, "needed": majority_needed, "deleted": True}

    return {
        "votes": vote_count,
        "needed": majority_needed,
        "deleted": False,
    }


@router.get("/{tournament_id}/standings")
async def get_tournament_standings(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Get tournament standings sorted by total score descending. Must be a participant."""
    # Check tournament exists
    result = await db.execute(
        select(Tournament.id).where(Tournament.id == tournament_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Verify current user is a participant
    participant_check = await db.execute(
        select(TournamentPlayer.id).where(
            TournamentPlayer.tournament_id == tournament_id,
            TournamentPlayer.user_id == current_user.id,
        )
    )
    if participant_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a participant in this tournament")

    players_q = await db.execute(
        select(TournamentPlayer, User)
        .join(User, TournamentPlayer.user_id == User.id)
        .where(TournamentPlayer.tournament_id == tournament_id)
        .order_by(desc(TournamentPlayer.total_score))
    )

    return [
        {
            "rank": idx + 1,
            "user_id": player.user_id,
            "display_name": user.display_name,
            "total_score": player.total_score,
            "placement": player.placement,
        }
        for idx, (player, user) in enumerate(players_q.all())
    ]
