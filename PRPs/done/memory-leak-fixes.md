# PRP: Memory Leak Fixes — Make ZenithGrid Memory-Safe

**Feature**: Fix all identified unbounded caches, leaked listeners, missing cleanup handlers
**Created**: 2026-03-13
**One-Pass Confidence Score**: 9/10

> This is a focused maintenance task — each fix is independent, well-scoped, and follows existing patterns already in the codebase. High confidence because every fix is either adding cleanup to an existing cache, or adding a `return` cleanup to a React `useEffect`.

---

## Context & Goal

### Problem
ZenithGrid runs on a 1GB RAM t2.micro EC2 instance. The backend process reaches **1GB RSS within 12 minutes** of startup and gets OOM-killed repeatedly (4 kills in 33 minutes observed). Multiple in-memory caches and tracking dicts grow without bound, and some frontend components leak timers and blob URLs.

### Solution
Add bounded caching, periodic cleanup, and proper resource disposal across all identified leak sites. Follow existing patterns already in the codebase (`cleanup_jobs.py` for backend periodic tasks, `useEffect` return functions for frontend).

### Who Benefits
All users — the site stays up instead of crashing every few hours.

### Scope
- **In**: Fix all identified memory leaks in backend and frontend
- **Out**: Performance optimization, architectural refactoring, adding new features

---

## Implementation Tasks (in order)

### Phase 1: Backend — Critical Cache Leaks (Priority 1)

#### Task 1.1: Add periodic in-memory cache cleanup job

Create a single new cleanup function in `cleanup_jobs.py` that periodically purges stale entries from ALL in-memory caches. This consolidates cleanup rather than scattering it.

**File**: `backend/app/cleanup_jobs.py`

**Pattern to follow** (existing in same file, e.g. `cleanup_old_rate_limit_attempts` at line ~336):
```python
async def cleanup_something():
    await asyncio.sleep(INITIAL_DELAY)
    while True:
        try:
            # ... cleanup logic ...
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
        await asyncio.sleep(INTERVAL)
```

**New function**: `cleanup_in_memory_caches()`
- Initial delay: 120 seconds (let app warm up)
- Interval: 300 seconds (every 5 minutes)
- Calls cleanup helpers on each module's caches:
  1. `dex_wallet_service.prune_price_cache()` — remove entries older than `PRICE_CACHE_TTL` (60s)
  2. `chat_ws_handler.prune_all_stale()` — call existing `_prune_typing_cooldowns()` and `_prune_send_timestamps()`
  3. `game_room_manager.cleanup_stale_rooms()` — already exists, just call it periodically
  4. Monitor cache cleanup (see Task 1.3)
- Log cache sizes before/after for observability

#### Task 1.2: Fix `dex_wallet_service.py` — unbounded `_price_cache`

**File**: `backend/app/services/dex_wallet_service.py`
**Line 29**: `_price_cache: Dict[str, tuple] = {}`

**Current state**: Cache checked for TTL on read (lines 187-195) but expired entries are NEVER removed.

**Fix**: Add a `prune_price_cache()` function that removes entries older than `PRICE_CACHE_TTL`:
```python
def prune_price_cache() -> int:
    """Remove expired entries from the token price cache."""
    if not _price_cache:
        return 0
    now = time.time()
    stale = [k for k, (_, ts) in _price_cache.items() if now - ts > PRICE_CACHE_TTL]
    for k in stale:
        del _price_cache[k]
    return len(stale)
```

Also add a max size cap (e.g., 500 entries). If cache exceeds cap after insertion, evict oldest entries.

#### Task 1.3: Fix `multi_bot_monitor.py` — unbounded `_candle_cache` and `_previous_indicators_cache`

**File**: `backend/app/multi_bot_monitor.py`
**Line 194**: `self._candle_cache: Dict[str, tuple] = {}`
**Line 204**: `self._previous_indicators_cache: Dict[tuple, Dict] = {}`
**Line 209**: `self._bot_next_check: Dict[int, int] = {}`

**Current state**:
- `_candle_cache` checks TTL on read (lines 318-333) but never evicts expired entries
- `_previous_indicators_cache` has no cleanup at all
- `_bot_next_check` has no cleanup

**Fix**: Add a `cleanup_caches()` method to the monitor class:
```python
def cleanup_caches(self) -> dict:
    """Evict expired entries from all in-memory caches. Returns counts."""
    now = datetime.utcnow().timestamp()

    # Candle cache — remove expired entries
    stale_candles = [k for k, (ts, _) in self._candle_cache.items()
                     if now - ts > CANDLE_CACHE_DEFAULT_TTL]
    for k in stale_candles:
        del self._candle_cache[k]

    # Previous indicators — remove entries for bots that no longer exist
    # (compare against active bot IDs from last monitor run)
    active_bot_ids = set(self._bot_next_check.keys())
    stale_indicators = [k for k in self._previous_indicators_cache
                        if k[0] not in active_bot_ids]
    for k in stale_indicators:
        del self._previous_indicators_cache[k]

    # Bot next check — remove entries for deleted bots (same set)
    # This one self-cleans via active_bot_ids, but cap it

    return {"candles": len(stale_candles), "indicators": len(stale_indicators)}
```

Expose this for the periodic cleanup job to call.

#### Task 1.4: Fix `chat_ws_handler.py` — expose cleanup for periodic calling

**File**: `backend/app/services/chat_ws_handler.py`
**Line 24**: `_typing_cooldowns: dict[tuple[int, int], float] = {}`
**Line 29**: `_send_timestamps: dict[int, list[float]] = {}`

**Current state**: `_prune_typing_cooldowns()` (line 35) and `_prune_send_timestamps()` (line 65) exist but are only called on-demand when messages arrive.

**Fix**: Add a public `prune_all_stale()` function that calls both pruning functions:
```python
def prune_all_stale() -> None:
    """Prune all stale rate-limiting entries. Called periodically by cleanup job."""
    _prune_typing_cooldowns()
    _prune_send_timestamps()
```

The existing prune functions already handle the logic correctly — we just need to call them on a schedule.

#### Task 1.5: Wire up the periodic cleanup in `main.py`

**File**: `backend/app/main.py`

**Pattern** (existing, lines 133-146 for globals, ~577 for task creation, ~657 for cancellation):

1. Add global: `memory_cache_cleanup_task = None`
2. In `startup_event()`:
   ```python
   from app.cleanup_jobs import cleanup_in_memory_caches
   global memory_cache_cleanup_task
   memory_cache_cleanup_task = asyncio.create_task(cleanup_in_memory_caches())
   logger.info("In-memory cache cleanup job started — cleaning every 5 minutes")
   ```
3. In `shutdown_event()`:
   ```python
   await _cancel_task(memory_cache_cleanup_task)
   ```

### Phase 2: Backend — WebSocket & Connection Tracking (Priority 2)

#### Task 2.1: Add periodic stale WebSocket connection sweep to `websocket_manager.py`

**File**: `backend/app/services/websocket_manager.py`
**Lines 52-54**: `_user_connections`, `_socket_owners`

**Current state**: Cleanup only on explicit disconnect. Abnormal drops can leave orphans.

**Fix**: Add a `sweep_stale_connections()` method that tests each tracked WebSocket:
```python
async def sweep_stale_connections(self) -> int:
    """Remove WebSocket connections that are no longer open. Returns count removed."""
    stale = []
    async with self._lock:
        for ws, uid in list(self._socket_owners.items()):
            if ws.client_state.name != "CONNECTED":
                stale.append(ws)

    for ws in stale:
        await self.disconnect(ws)

    return len(stale)
```

Call this from the periodic cleanup job (every 5 minutes).

#### Task 2.2: Add max-size cap to `exchange_service.py` cache

**File**: `backend/app/services/exchange_service.py`
**Line 32**: `_exchange_client_cache: dict[int, ExchangeClient] = {}`

**Current state**: Cleaned on shutdown or credential change, but can grow if many accounts are active.

**Fix**: This cache is bounded by number of accounts (typically <10), so it's low risk. Add logging of cache size in the periodic cleanup job for observability. No structural change needed.

### Phase 3: Frontend — Timer and Resource Leaks (Priority 3)

#### Task 3.1: Fix `ArticleReaderContext.tsx` — uncancelled setTimeout chains

**File**: `frontend/src/contexts/ArticleReaderContext.tsx`

**Leak sites** (setTimeout created without cleanup):
- **Lines 278-290**: Auto-skip broken articles
- **Lines 323-335**: Skip articles with no content
- **Lines 754-762**: Error retry timeout
- **Lines 770-779**: Skip to next article timeout

**Fix**: Use a ref to track active timeouts and clear them on unmount and on `stopPlaylist()`:
```typescript
const autoAdvanceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

// Helper to set timeout with tracking
const setAutoAdvanceTimer = useCallback((fn: () => void, ms: number) => {
  if (autoAdvanceTimerRef.current) clearTimeout(autoAdvanceTimerRef.current);
  autoAdvanceTimerRef.current = setTimeout(() => {
    autoAdvanceTimerRef.current = null;
    fn();
  }, ms);
}, []);
```

Replace all bare `setTimeout(...)` calls in auto-advance logic with `setAutoAdvanceTimer(...)`.

In `stopPlaylist()` (around line 600), add:
```typescript
if (autoAdvanceTimerRef.current) {
  clearTimeout(autoAdvanceTimerRef.current);
  autoAdvanceTimerRef.current = null;
}
```

In the cleanup useEffect, add the same clearTimeout.

#### Task 3.2: Fix `ArticleReaderContext.tsx` — unbounded voice cache

**File**: `frontend/src/contexts/ArticleReaderContext.tsx`
**Lines 144, 360-363**: `voiceCache` state grows with every article URL

**Fix**: Cap the voice cache at 200 entries. When exceeded, drop oldest entries:
```typescript
const saveVoiceCache = useCallback((article: Article, voice: string) => {
  setVoiceCache(prev => {
    const next = { ...prev, [article.url]: voice };
    const keys = Object.keys(next);
    if (keys.length > 200) {
      // Remove oldest 50 entries
      keys.slice(0, 50).forEach(k => delete next[k]);
    }
    return next;
  });
}, []);
```

#### Task 3.3: Fix `NotificationContext.tsx` — version check timeout chain

**File**: `frontend/src/contexts/NotificationContext.tsx`
**Lines 128-152**: Recursive `setTimeout` chain with no cleanup

**Fix**: Track the verification timeout with a ref and clear on unmount:
```typescript
const versionVerifyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
```

Wrap the `setTimeout` calls at lines 135 and 152 to store the timer ID:
```typescript
versionVerifyTimerRef.current = setTimeout(() => verifyVersion(checksRemaining - 1), 5000);
```

In the cleanup effect (lines 304-307), clear it:
```typescript
if (versionVerifyTimerRef.current) {
  clearTimeout(versionVerifyTimerRef.current);
  versionVerifyTimerRef.current = null;
}
```

### Phase 4: Observability (Priority 4)

#### Task 4.1: Add memory usage logging

In the periodic cleanup job, log process RSS after each cleanup cycle:
```python
import resource
rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KB → MB
logger.info(f"Process RSS: {rss_mb:.0f}MB | Caches: price={len(_price_cache)}, "
            f"candle={len(monitor._candle_cache)}, rooms={len(game_room_manager._rooms)}")
```

This gives us visibility into whether the fixes are working without needing to SSH in.

---

## Files to Modify

| File | Changes |
|------|---------|
| `backend/app/cleanup_jobs.py` | Add `cleanup_in_memory_caches()` function |
| `backend/app/services/dex_wallet_service.py` | Add `prune_price_cache()` with max-size cap |
| `backend/app/services/chat_ws_handler.py` | Add `prune_all_stale()` public function |
| `backend/app/services/game_room_manager.py` | No changes needed — `cleanup_stale_rooms()` already exists |
| `backend/app/multi_bot_monitor.py` | Add `cleanup_caches()` method |
| `backend/app/services/websocket_manager.py` | Add `sweep_stale_connections()` method |
| `backend/app/services/exchange_service.py` | Logging only (in cleanup job) |
| `backend/app/main.py` | Wire up `memory_cache_cleanup_task` in startup/shutdown |
| `frontend/src/contexts/ArticleReaderContext.tsx` | Track/clear auto-advance timeouts, cap voice cache |
| `frontend/src/contexts/NotificationContext.tsx` | Track/clear version verify timeout chain |

---

## Files NOT Modified (Research Confirmed Clean)

These were originally suspected but research confirmed proper cleanup:
- `frontend/src/pages/games/components/multiplayer/GameLobby.tsx` — Has proper `return () => unsubs.forEach(fn => fn())` at line 171
- `frontend/src/hooks/useTTSSync.ts` — Excellent cleanup: blob URLs revoked (lines 487-492, 312-315), AudioContext closed (lines 321-325), animation frames cancelled (lines 165-168, 210-212)
- `frontend/src/pages/games/hooks/useChatSocket.ts` — Typing map properly bounded with 1s interval cleanup (lines 103-119), all listeners return unsub
- `frontend/src/pages/positions/hooks/usePositionsData.ts` — `currentPrices` is REPLACED each fetch (not accumulated), proper interval/abort cleanup

---

## Validation Gates

### Backend
```bash
# Lint
cd /home/ec2-user/ZenithGrid/backend && flake8 app/cleanup_jobs.py app/services/dex_wallet_service.py app/services/chat_ws_handler.py app/multi_bot_monitor.py app/services/websocket_manager.py app/main.py --max-line-length=120

# Type check (focused)
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -c "import app.cleanup_jobs; import app.services.dex_wallet_service; import app.services.chat_ws_handler; import app.multi_bot_monitor; import app.services.websocket_manager; print('All imports OK')"

# Run affected tests
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/ -v -k "cleanup or cache or websocket or chat" --timeout=30
```

### Frontend
```bash
# TypeScript check
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit --pretty 2>&1 | grep -E "(ArticleReaderContext|NotificationContext)" || echo "No TS errors in changed files"
```

### Memory verification (post-deploy)
```bash
# Monitor RSS over 30 minutes after restart
watch -n 60 'ps aux | grep uvicorn | grep -v grep | awk "{print \$6/1024 \" MB\"}"'
```

---

## Gotchas & Considerations

1. **Other Eli is working concurrently** on security hardening — avoid touching files he's modifying. Check `git status` before each edit.
2. **`multi_bot_monitor.py` is huge (~2000 lines)** — make surgical edits only, don't refactor.
3. **`cleanup_in_memory_caches()` must import lazily** — the monitor and game room manager are singletons initialized at startup. Import them inside the function body, not at module level, to avoid circular imports.
4. **WebSocket `client_state` check** — `starlette.websockets.WebSocketState` enum values are `CONNECTING`, `CONNECTED`, `DISCONNECTED`. Check for `!= WebSocketState.CONNECTED` (not string comparison).
5. **Frontend setTimeout tracking** — multiple auto-advance paths can fire in sequence. Using a single ref means only the latest timeout is tracked. This is correct behavior (only one auto-advance should be active at a time).
6. **Voice cache pruning** — `Object.keys()` order is insertion order in modern JS, so slicing the first N keys removes the oldest entries. This is correct.
7. **Don't restart the backend unnecessarily** during implementation — batch all backend changes and restart once at the end.

---

## References

- Existing cleanup pattern: `backend/app/cleanup_jobs.py` (all functions follow same async loop pattern)
- Existing task wiring: `backend/app/main.py` lines 133-146 (globals), 577-579 (create_task), 622-630 (_cancel_task), 657-665 (shutdown cancellation)
- WebSocket state: [Starlette WebSocket docs](https://www.starlette.io/websockets/)
- React cleanup: [React useEffect cleanup docs](https://react.dev/learn/synchronizing-with-effects#how-to-handle-the-effect-firing-twice-in-development)
