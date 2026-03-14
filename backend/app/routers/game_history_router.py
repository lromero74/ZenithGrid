"""
Game History API Router

Endpoints for viewing game history, game result details, and managing
game history visibility/privacy settings.
"""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_permission, Perm
from app.database import get_db
from app.models import User
from app.models.social import (
    Friendship,
    GameHighScore,
    GameHistoryVisibility,
    GameResult,
    GameResultPlayer,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/game-history", tags=["game-history"])


# ----- Pydantic Schemas -----


class VisibilityOption(StrEnum):
    ALL_FRIENDS = "all_friends"
    OPPONENTS_ONLY = "opponents_only"
    PRIVATE = "private"


class VisibilityUpdate(BaseModel):
    default_visibility: VisibilityOption
    game_overrides: Optional[dict[str, VisibilityOption]] = None


class VisibilityOut(BaseModel):
    default_visibility: str
    game_overrides: Optional[dict] = None


# ----- Helpers -----


async def _check_visibility_access(
    db: AsyncSession,
    viewer_id: int,
    target_user_id: int,
) -> None:
    """
    Check if viewer is allowed to see target_user's game history.
    Raises HTTPException(403) if not allowed.
    """
    # Look up target's visibility setting
    result = await db.execute(
        select(GameHistoryVisibility).where(
            GameHistoryVisibility.user_id == target_user_id
        )
    )
    vis = result.scalar_one_or_none()
    visibility = vis.default_visibility if vis else "all_friends"

    if visibility == "private":
        raise HTTPException(status_code=403, detail="This user's game history is private")

    if visibility == "all_friends":
        # Check if viewer is a friend
        friend_check = await db.execute(
            select(Friendship.id).where(
                Friendship.user_id == viewer_id,
                Friendship.friend_id == target_user_id,
            )
        )
        if friend_check.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=403,
                detail="You must be friends to view this user's game history",
            )

    elif visibility == "opponents_only":
        # Check if viewer has ever played against target
        opponent_check = await db.execute(
            select(GameResultPlayer.id).where(
                GameResultPlayer.user_id == viewer_id,
                GameResultPlayer.game_result_id.in_(
                    select(GameResultPlayer.game_result_id).where(
                        GameResultPlayer.user_id == target_user_id
                    )
                ),
            )
        )
        if opponent_check.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=403,
                detail="You must have played against this user to view their history",
            )


async def _build_game_history_response(
    db: AsyncSession,
    user_id: int,
    game_id: Optional[str],
    limit: int,
    offset: int,
) -> dict:
    """Build paginated game history response for a user.

    Returns user-centric computed fields: result, score, opponent_names,
    duration_seconds — so the frontend doesn't need to recompute from players[].
    """
    # Base query: games where user participated
    base_filter = GameResult.id.in_(
        select(GameResultPlayer.game_result_id).where(
            GameResultPlayer.user_id == user_id
        )
    )
    filters = [base_filter]
    if game_id:
        filters.append(GameResult.game_id == game_id)

    # Count total
    count_q = select(func.count(GameResult.id)).where(and_(*filters))
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch page — eagerly load players to avoid N+1
    from sqlalchemy.orm import selectinload
    items_q = (
        select(GameResult)
        .options(selectinload(GameResult.players).joinedload(GameResultPlayer.user))
        .where(and_(*filters))
        .order_by(desc(GameResult.finished_at), desc(GameResult.id))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(items_q)
    games = result.scalars().unique().all()

    items = []
    for g in games:
        # Compute user-centric fields from players
        my_result = "draw"
        my_score = None
        opponent_names = []
        for p in g.players:
            if p.user_id == user_id:
                my_score = p.score
                if p.is_winner:
                    my_result = "win"
            else:
                opponent_names.append(p.user.display_name if p.user else f"User {p.user_id}")
                if p.is_winner:
                    my_result = "loss"

        # Compute duration
        duration_seconds = None
        if g.started_at and g.finished_at:
            duration_seconds = int((g.finished_at - g.started_at).total_seconds())

        items.append({
            "id": g.id,
            "game_id": g.game_id,
            "mode": g.mode,
            "result": my_result,
            "score": my_score,
            "opponent_names": opponent_names,
            "finished_at": g.finished_at.isoformat() if g.finished_at else None,
            "duration_seconds": duration_seconds,
            "tournament_id": g.tournament_id,
        })

    page_num = (offset // limit) + 1 if limit > 0 else 1
    total_pages = max(1, (total + limit - 1) // limit) if limit > 0 else 1

    return {
        "items": items,
        "total": total,
        "page": page_num,
        "page_size": limit,
        "total_pages": total_pages,
    }


# ----- Endpoints -----


@router.get("")
async def list_own_game_history(
    game_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """List current user's game history (paginated, optional game_id filter)."""
    return await _build_game_history_response(db, current_user.id, game_id, limit, offset)


@router.get("/user/{user_id}")
async def view_user_game_history(
    user_id: int,
    game_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """View another user's game history (respecting their privacy settings)."""
    # Verify target user exists
    target = await db.execute(select(User.id).where(User.id == user_id, User.is_active.is_(True)))
    if target.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="User not found")

    # If viewing own history, no privacy check needed
    if user_id != current_user.id:
        await _check_visibility_access(db, current_user.id, user_id)

    return await _build_game_history_response(db, user_id, game_id, limit, offset)


@router.put("/visibility")
async def update_visibility(
    body: VisibilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Update current user's game history visibility settings."""
    result = await db.execute(
        select(GameHistoryVisibility).where(
            GameHistoryVisibility.user_id == current_user.id
        )
    )
    vis = result.scalar_one_or_none()

    if vis:
        vis.default_visibility = body.default_visibility
        vis.game_overrides = body.game_overrides
    else:
        vis = GameHistoryVisibility(
            user_id=current_user.id,
            default_visibility=body.default_visibility,
            game_overrides=body.game_overrides,
        )
        db.add(vis)

    await db.commit()

    return {
        "default_visibility": vis.default_visibility,
        "game_overrides": vis.game_overrides,
    }


# ----- Game High Scores -----


@router.get("/scores")
async def get_game_scores(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all high scores for the current user, keyed by game_id."""
    result = await db.execute(
        select(GameHighScore).where(GameHighScore.user_id == current_user.id)
    )
    scores = result.scalars().all()
    # Return dict keyed by game_id with score and score_type
    out: dict[str, dict] = {}
    for row in scores:
        key = row.game_id
        out[key] = {
            "score": row.score,
            "score_type": row.score_type,
        }
    return out


@router.put("/scores/{game_id}")
async def update_game_score(
    game_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update high score for a game. For fastest_time, lower is better."""
    score = body.get("score")
    if score is None or not isinstance(score, (int, float)):
        raise HTTPException(400, "score required")
    score = int(score)
    score_type = body.get("score_type", "high_score")

    result = await db.execute(
        select(GameHighScore).where(
            GameHighScore.user_id == current_user.id,
            GameHighScore.game_id == game_id,
            GameHighScore.score_type == score_type,
        )
    )
    existing = result.scalar_one_or_none()

    # For fastest_time, lower is better
    is_better = (
        score < existing.score if score_type == "fastest_time" and existing
        else score > existing.score if existing
        else True
    )

    if existing:
        if is_better:
            existing.score = score
            existing.updated_at = datetime.utcnow()
            await db.commit()
            return {"game_id": game_id, "score": score, "updated": True}
        return {"game_id": game_id, "score": existing.score, "updated": False}
    else:
        new_score = GameHighScore(
            user_id=current_user.id,
            game_id=game_id,
            score=score,
            score_type=score_type,
        )
        db.add(new_score)
        await db.commit()
        return {"game_id": game_id, "score": score, "updated": True}


# ----- Game Result Detail (must be AFTER /scores and /visibility to avoid path capture) -----


@router.get("/{game_result_id}")
async def get_game_result_detail(
    game_result_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Get detailed game result. Only participants can view."""
    result = await db.execute(
        select(GameResult).where(GameResult.id == game_result_id)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game result not found")

    # Check that current user was a participant
    participant_check = await db.execute(
        select(GameResultPlayer.id).where(
            GameResultPlayer.game_result_id == game_result_id,
            GameResultPlayer.user_id == current_user.id,
        )
    )
    if participant_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Game result not found")

    # Fetch players
    players_q = await db.execute(
        select(GameResultPlayer, User)
        .join(User, GameResultPlayer.user_id == User.id)
        .where(GameResultPlayer.game_result_id == game_result_id)
        .order_by(GameResultPlayer.placement)
    )
    players = [
        {
            "user_id": player.user_id,
            "display_name": user.display_name,
            "placement": player.placement,
            "score": player.score,
            "is_winner": player.is_winner,
            "stats": player.stats,
        }
        for player, user in players_q.all()
    ]

    return {
        "id": game.id,
        "room_id": game.room_id,
        "game_id": game.game_id,
        "mode": game.mode,
        "started_at": game.started_at.isoformat() if game.started_at else None,
        "finished_at": game.finished_at.isoformat() if game.finished_at else None,
        "result_data": game.result_data,
        "tournament_id": game.tournament_id,
        "players": players,
    }
