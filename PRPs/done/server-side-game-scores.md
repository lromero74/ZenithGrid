# PRP: Server-Side Game Scores & Achievements

**Feature**: Extend existing GameHighScore system with score types, metadata, and display on game cards
**Created**: 2026-03-14
**One-Pass Confidence Score**: 8/10

> The core infrastructure already exists (GameHighScore model, useGameScores hook, API endpoints). This PRP extends it with score type metadata and better display. Low risk.

---

## Context & Goal

### Problem
Game scores are partially server-side (`GameHighScore` model exists, sync works) but lack metadata. All scores are treated as plain integers — no distinction between "points", "time", "level". Scores don't show on game cards in the hub. Shalas has no fastest-time tracking.

### Solution
1. **Extend GameHighScore** with `score_type` and `difficulty` columns
2. **Extend API** to accept/return score metadata
3. **Show scores on game cards** with appropriate formatting (points, time, level)
4. **Track Shalas fastest win time** from GameResult data (VS game duration)
5. **Define score types per game** in the game registry

### Scope
- **In**: Model extension, migration, API update, hook update, card display, Shalas time tracking
- **Out**: Leaderboards, cross-user score comparison, achievements system

---

## Existing Infrastructure

### GameHighScore Model (`backend/app/models/social.py` lines 123-137)
```python
class GameHighScore(Base):
    __tablename__ = "game_high_scores"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    game_id = Column(String, nullable=False)
    score = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint('user_id', 'game_id', name='uq_user_game_score'),)
```

**Limitation**: Single integer score, no type distinction. `game_id` includes difficulty suffix (e.g., `minesweeper-beginner`).

### useGameScores Hook (`frontend/src/pages/games/hooks/useGameScores.ts`)
- `getHighScore(gameId)` → number | null
- `saveScore(gameId, score)` → fire-and-forget PUT to server + localStorage
- Merges localStorage + server on mount
- Already syncs bidirectionally

### Backend Endpoints (`backend/app/routers/game_history_router.py` lines 264-317)
- `GET /api/game-history/scores` → `{gameId: score}` dict
- `PUT /api/game-history/scores/{gameId}` → update if new > existing

### Games Using Scores (7 games)
| Game | Score Type | Game ID Pattern |
|------|-----------|-----------------|
| Snake | Points | `snake` |
| 2048 | Points | `twenty-forty-eight` |
| Centipede | Points | `centipede` |
| Dino Runner | Points | `dino-runner` |
| Space Invaders | Points | `space-invaders` |
| Lode Runner | Score | `lode-runner` |
| Minesweeper | Time (seconds) | `minesweeper-{difficulty}` |

### Shalas Game Results (`backend/app/models/social.py` lines 77-108)
`GameResult` already tracks `started_at` and `finished_at` for VS games. Fastest win time = `finished_at - started_at` for games where the user won.

---

## Implementation Tasks

### Backend

#### 1. Migration — extend game_high_scores table
**File**: `backend/migrations/extend_game_high_scores.py`

```sql
ALTER TABLE game_high_scores ADD COLUMN score_type VARCHAR(20) DEFAULT 'high_score';
ALTER TABLE game_high_scores ADD COLUMN difficulty VARCHAR(20);
```

Also drop the unique constraint and recreate with score_type included:
```sql
-- Allow multiple score types per game (e.g., high_score + fastest_time)
ALTER TABLE game_high_scores DROP CONSTRAINT IF EXISTS uq_user_game_score;
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_game_score_type
  ON game_high_scores(user_id, game_id, score_type);
```

#### 2. Update GameHighScore model (`backend/app/models/social.py`)
```python
class GameHighScore(Base):
    # ... existing fields ...
    score_type = Column(String(20), nullable=False, default="high_score")
    difficulty = Column(String(20), nullable=True)
    # Update unique constraint to include score_type
    __table_args__ = (
        UniqueConstraint('user_id', 'game_id', 'score_type', name='uq_user_game_score_type'),
    )
```

#### 3. Update API endpoints (`backend/app/routers/game_history_router.py`)

Extend `GET /api/game-history/scores` to return score_type:
```python
# Return: {gameId: {score, score_type}} instead of {gameId: score}
# Keep backwards-compatible: if old format expected, flatten
```

Extend `PUT /api/game-history/scores/{gameId}` to accept score_type:
```python
class ScoreUpdate(BaseModel):
    score: int
    score_type: str = "high_score"  # "high_score", "fastest_time", "level_reached"
```

For `fastest_time`: lower is better, so comparison logic inverts (new < existing → update).

Add new endpoint for Shalas fastest win time:
```python
@router.get("/scores/fastest-win/{game_id}")
# Queries GameResult + GameResultPlayer for fastest completed game where user won
```

#### 4. Shalas fastest win query
```sql
SELECT MIN(EXTRACT(EPOCH FROM (gr.finished_at - gr.started_at))) as fastest_seconds
FROM game_results gr
JOIN game_result_players grp ON grp.game_result_id = gr.id
WHERE grp.user_id = :user_id
  AND gr.game_id = 'shalas'
  AND grp.is_winner = true
  AND gr.finished_at IS NOT NULL
```

### Frontend

#### 5. Extend useGameScores hook
- `saveScore(gameId, score, scoreType?)` — pass score_type to PUT
- `getScore(gameId, scoreType?)` — return score for specific type
- Handle `fastest_time` comparison (lower is better)

#### 6. Add score_type to GameInfo (`frontend/src/pages/games/types.ts`)
```typescript
export interface GameInfo {
  // ... existing fields ...
  scoreType?: 'high_score' | 'fastest_time' | 'level_reached'
  scoreLabel?: string  // "Points", "Time", "Level", "Best Time"
}
```

#### 7. Update game constants (`frontend/src/pages/games/constants.ts`)
Add `scoreType` and `scoreLabel` to the 7 games that track scores:
```typescript
{ id: 'snake', scoreType: 'high_score', scoreLabel: 'Points', ... }
{ id: 'minesweeper', scoreType: 'fastest_time', scoreLabel: 'Best Time', ... }
{ id: 'shalas', scoreType: 'fastest_time', scoreLabel: 'Fastest Win', ... }
```

#### 8. Update GameCard display (`frontend/src/pages/games/components/GameCard.tsx`)
Format score based on score_type:
- `high_score`: `"1,234"` (number with commas)
- `fastest_time`: `"2m 45s"` or `"45s"` (formatted duration)
- `level_reached`: `"Level 12"`

#### 9. Update GameHub to pass score data
Pass scores from `useGameScores()` to each `GameCard`, matching by game.id + game.scoreType.

### Tests

#### 10. Backend tests (`backend/tests/routers/test_game_scores.py`)
- `test_save_score_with_type`
- `test_fastest_time_lower_wins`
- `test_high_score_higher_wins`
- `test_get_scores_returns_types`
- `test_shalas_fastest_win_query`

---

## Score Formatting Helper

```typescript
function formatScore(score: number, type?: string): string {
  if (type === 'fastest_time') {
    if (score >= 60) return `${Math.floor(score / 60)}m ${score % 60}s`
    return `${score}s`
  }
  if (type === 'level_reached') return `Level ${score}`
  return score.toLocaleString()
}
```

---

## Validation Gates

```bash
# Python lint
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m flake8 --max-line-length=120 \
  app/models/social.py \
  app/routers/game_history_router.py

# TypeScript
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Tests
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/routers/test_game_scores.py -v

# Migration
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -c "
import asyncio
from app.database import async_session_maker
from migrations.extend_game_high_scores import run_migration
async def main():
    async with async_session_maker() as db:
        await run_migration(db)
        await db.commit()
asyncio.run(main())
"
```

---

## Quality Checklist

- [x] All necessary context included (existing model, hook, endpoints, games list)
- [x] Validation gates are executable
- [x] References existing patterns (GameHighScore, useGameScores, migration pattern)
- [x] Clear implementation path (10 ordered tasks)
- [x] Error handling documented (backwards compatibility, comparison logic)
- [x] Score formatting documented
