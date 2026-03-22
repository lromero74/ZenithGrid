# PRP: Phase 1.5 — Dedicated Thread Pool for TTS Processing

**Feature**: Offload blocking TTS file I/O to a bounded `ThreadPoolExecutor` on `app.state`
**Created**: 2026-03-21
**One-Pass Confidence Score**: 9/10

> Focused, low-risk change. Two files modified: `main.py` (executor lifecycle) and `news_tts_router.py` (wrap blocking file I/O). No new dependencies, no schema changes, no API contract changes. Tests written first per TDD requirement.

---

## Context & Goal

### Problem

`news_tts_router.py` performs synchronous blocking file I/O on the async event loop:

- `cache_path.read_bytes()` — reads MP3 files (can be several MB) synchronously
- `(TTS_CACHE_DIR / audio_path).write_bytes(audio_data)` — writes generated TTS to disk synchronously
- `hashlib.md5(text.encode())` — CPU-bound (negligible, but on the loop)

From `docs/SCALABILITY_ROADMAP.md` section 1.5:
> TTS generation is CPU-bound (or waits on an external TTS API). It currently runs on the async event loop, blocking other requests during generation.
> Fix: Move TTS generation calls inside `run_in_executor(thread_pool)` with a bounded `ThreadPoolExecutor(max_workers=2)` dedicated to TTS.

**Why this matters on t2.micro**: The server has 1 vCPU and 1GB RAM. A blocking file read/write (even 50–200ms for a large MP3) freezes the entire event loop, stalling all concurrent requests — including trading API calls, bot monitor responses, and WebSocket messages.

### Important Technical Note: edge_tts is Already Async

`edge_tts.Communicate.stream()` is an **async generator** — it already runs non-blocking on the event loop (it's network I/O over asyncio). You cannot run async functions in a thread pool executor. Therefore:

- `_generate_tts()` (uses `async for chunk in communicate.stream()`) stays async — no executor needed
- The **blocking file I/O** in `_get_or_create_tts()` is what needs offloading

### Solution

1. Create a `ThreadPoolExecutor(max_workers=2)` dedicated to TTS at app startup, stored as `app.state.tts_executor`
2. Wrap the two blocking file operations in `_get_or_create_tts()` with `loop.run_in_executor(app.state.tts_executor, ...)`
3. Shut down the executor cleanly in the shutdown event
4. Make the executor accessible to the router via a FastAPI dependency or by importing `app` directly

### Who Benefits

All users — slow TTS file operations no longer stall trading API responses, bot monitoring, or WebSocket messages.

### Scope

- **In**: Wrap blocking file I/O in `_get_or_create_tts()` with the thread pool executor
- **Out**: Rewriting `_generate_tts()` (already async), changing TTS caching logic, APScheduler migration, other Phase 1 items

---

## Architecture

```
POST /tts-sync arrives
  ↓
text_to_speech_with_sync (async, event loop)
  ↓
_get_or_create_tts (async, event loop)
  ├── DB query (async — already non-blocking)
  ├── cache_path.read_bytes()          ← BLOCKING — wrap with run_in_executor
  ├── _generate_tts()                  ← STAYS ASYNC (edge_tts is async)
  ├── article_dir.mkdir()              ← BLOCKING — wrap with run_in_executor
  └── write_bytes(audio_data)          ← BLOCKING — wrap with run_in_executor
```

```
app startup → ThreadPoolExecutor(max_workers=2) → app.state.tts_executor
app shutdown → app.state.tts_executor.shutdown(wait=True)
```

---

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/main.py` | Create executor on startup, attach to `app.state`, shut down on shutdown |
| `backend/app/routers/news_tts_router.py` | Import `app`, wrap blocking file ops in `run_in_executor` |

**File to create (tests first):**

| File | Purpose |
|------|---------|
| `backend/tests/routers/test_tts_thread_pool.py` | Tests for executor lifecycle, bounded workers, file I/O offloading, error handling |

---

## TDD Plan — Write These Tests BEFORE Implementation

### Test file: `backend/tests/routers/test_tts_thread_pool.py`

All tests must **fail** before implementation, then pass after. Run with:
```bash
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/routers/test_tts_thread_pool.py -v
```

#### Test Class 1: `TestTTSExecutorLifecycle`

**Purpose**: Verify executor is created at startup, bounded to 2 workers, and shuts down cleanly.

```python
class TestTTSExecutorLifecycle:

    def test_executor_created_on_startup(self):
        """Happy path: app.state.tts_executor exists and is a ThreadPoolExecutor."""
        # FAILS before impl: app.state has no tts_executor attribute
        from concurrent.futures import ThreadPoolExecutor
        from app.main import app
        assert hasattr(app.state, 'tts_executor')
        assert isinstance(app.state.tts_executor, ThreadPoolExecutor)

    def test_executor_bounded_to_two_workers(self):
        """Edge case: executor has max_workers=2 (not unbounded)."""
        # FAILS before impl: no executor exists
        from app.main import app
        assert app.state.tts_executor._max_workers == 2

    @pytest.mark.asyncio
    async def test_executor_accepts_callable(self):
        """Happy path: executor can run a synchronous callable."""
        # FAILS before impl: no executor exists
        import asyncio
        from app.main import app
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            app.state.tts_executor, lambda: 42
        )
        assert result == 42

    def test_executor_not_shutdown_while_running(self):
        """Edge case: executor is not prematurely shut down."""
        # FAILS before impl: no executor exists
        from app.main import app
        # A ThreadPoolExecutor that's been shut down raises RuntimeError on submit
        import concurrent.futures
        future = app.state.tts_executor.submit(lambda: "alive")
        assert future.result(timeout=2) == "alive"
```

#### Test Class 2: `TestGetOrCreateTTSUsesExecutor`

**Purpose**: Verify blocking file operations use `run_in_executor`, not direct calls.

```python
class TestGetOrCreateTTSUsesExecutor:

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router.asyncio.get_event_loop")
    @patch("app.routers.news_tts_router.async_session_maker")
    async def test_file_read_uses_run_in_executor(
        self, mock_session_maker, mock_get_loop
    ):
        """Happy path: cache hit reads file via run_in_executor, not blocking read_bytes()."""
        # FAILS before impl: _get_or_create_tts calls read_bytes() directly on event loop
        # After impl: should call loop.run_in_executor(..., path.read_bytes)
        mock_loop = AsyncMock()
        mock_loop.run_in_executor = AsyncMock(return_value=b"fake_audio")
        mock_get_loop.return_value = mock_loop

        mock_cached = MagicMock()
        mock_cached.content_hash = "abc12345"
        mock_cached.audio_path = "1/aria.mp3"
        mock_cached.word_timings = json.dumps([{"text": "hello", "startTime": 0.0, "endTime": 0.5}])

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_cached
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("app.routers.news_tts_router.TTS_CACHE_DIR") as mock_cache_dir:
            mock_filepath = MagicMock()
            mock_filepath.exists.return_value = True
            mock_cache_dir.__truediv__ = MagicMock(return_value=mock_filepath)

            from app.routers.news_tts_router import _get_or_create_tts
            audio, words = await _get_or_create_tts(
                article_id=1, voice="aria", text="hello world",
                rate="+0%", user_id=1, audio_needed=True,
            )

        # run_in_executor should have been called for the file read
        mock_loop.run_in_executor.assert_called()
        assert audio == b"fake_audio"

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router._generate_tts", new_callable=AsyncMock)
    @patch("app.routers.news_tts_router.asyncio.get_event_loop")
    @patch("app.routers.news_tts_router.async_session_maker")
    async def test_file_write_uses_run_in_executor(
        self, mock_session_maker, mock_get_loop, mock_gen_tts
    ):
        """Happy path: cache miss triggers generation and writes file via run_in_executor."""
        # FAILS before impl: write_bytes() called directly on event loop
        mock_gen_tts.return_value = (b"generated_audio", [])

        mock_loop = AsyncMock()
        mock_loop.run_in_executor = AsyncMock(return_value=None)
        mock_get_loop.return_value = mock_loop

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None  # Cache miss
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("app.routers.news_tts_router.TTS_CACHE_DIR") as mock_cache_dir:
            mock_dir = MagicMock()
            mock_dir.mkdir = MagicMock()
            mock_file = MagicMock()
            mock_file.write_bytes = MagicMock()
            mock_cache_dir.__truediv__ = MagicMock(side_effect=[mock_dir, mock_file, mock_file])
            mock_cache_dir.__str__ = MagicMock(return_value="/fake/cache")

            from app.routers.news_tts_router import _get_or_create_tts
            await _get_or_create_tts(
                article_id=2, voice="aria", text="test text",
                rate="+0%", user_id=1, audio_needed=False,
            )

        # run_in_executor should have been called for the file write
        mock_loop.run_in_executor.assert_called()
```

#### Test Class 3: `TestTTSExecutorBounded`

**Purpose**: Verify the executor doesn't grow beyond max_workers=2, protecting server memory.

```python
class TestTTSExecutorBounded:

    @pytest.mark.asyncio
    async def test_executor_queues_when_workers_busy(self):
        """Edge case: third TTS task queues rather than spawning a third thread."""
        import asyncio
        import time
        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=2)

        started = []
        gate = asyncio.Event()

        def slow_task(task_id):
            started.append(task_id)
            time.sleep(0.05)
            return task_id

        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(executor, slow_task, i)
            for i in range(3)
        ]
        results = await asyncio.gather(*tasks)
        assert sorted(results) == [0, 1, 2]  # All complete, just queued
        executor.shutdown(wait=False)

    def test_executor_max_workers_is_two(self):
        """Edge case: ensure production executor has exactly 2 workers."""
        from app.main import app
        assert app.state.tts_executor._max_workers == 2
```

#### Test Class 4: `TestTTSExecutorShutdown`

**Purpose**: Verify graceful shutdown.

```python
class TestTTSExecutorShutdown:

    def test_shutdown_waits_for_in_flight_work(self):
        """Happy path: shutdown(wait=True) waits for active tasks to complete."""
        import time
        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=1)
        results = []

        def slow_task():
            time.sleep(0.05)
            results.append("done")

        executor.submit(slow_task)
        executor.shutdown(wait=True)
        assert results == ["done"]  # Task completed before shutdown returned

    @pytest.mark.asyncio
    async def test_shutdown_event_calls_executor_shutdown(self):
        """Happy path: app shutdown event shuts down the tts_executor."""
        # FAILS before impl: shutdown_event doesn't reference tts_executor
        from unittest.mock import patch, MagicMock
        from app.main import app, shutdown_event

        mock_executor = MagicMock()
        app.state.tts_executor = mock_executor

        # Patch all the monitors/tasks that shutdown_event also calls
        with patch("app.main.shutdown_manager") as mock_sm, \
             patch("app.main.price_monitor"), \
             patch("app.main.content_refresh_service"), \
             patch("app.main.domain_blacklist_service"), \
             patch("app.main.debt_ceiling_monitor"), \
             patch("app.main.auto_buy_monitor"), \
             patch("app.main.rebalance_monitor"), \
             patch("app.main.perps_monitor"), \
             patch("app.main.stop_prop_guard_monitor", new_callable=AsyncMock), \
             patch("app.main.trading_pair_monitor"), \
             patch("app.main.clear_exchange_client_cache"):
            mock_sm.prepare_shutdown = AsyncMock(return_value={"ready": True, "message": "OK"})
            await shutdown_event()

        mock_executor.shutdown.assert_called_once_with(wait=True)
```

#### Test Class 5: `TestTTSEndpointErrorHandling`

**Purpose**: Verify errors in executor tasks don't crash the endpoint.

```python
class TestTTSEndpointErrorHandling:

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router._get_or_create_tts", new_callable=AsyncMock)
    async def test_tts_executor_error_returns_500(self, mock_tts, test_user):
        """Failure case: executor task raising an exception returns 500, not a crash."""
        mock_tts.side_effect = OSError("Disk write failed")

        from app.routers.news_tts_router import (
            text_to_speech_with_sync, TTSSyncRequest,
        )
        body = TTSSyncRequest(text="Hello world", voice="aria", article_id=1)
        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await text_to_speech_with_sync(
                body=body, request=mock_request, current_user=test_user,
            )
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router._generate_tts", new_callable=AsyncMock)
    async def test_generate_tts_error_propagates_as_500(self, mock_gen, test_user):
        """Failure case: edge_tts failure propagates as 500, not unhandled exception."""
        mock_gen.side_effect = Exception("edge_tts network error")

        from app.routers.news_tts_router import (
            text_to_speech_with_sync, TTSSyncRequest,
        )
        body = TTSSyncRequest(text="Hello world", voice="aria")
        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await text_to_speech_with_sync(
                body=body, request=mock_request, current_user=test_user,
            )
        assert exc_info.value.status_code == 500
```

---

## Implementation Blueprint

### Step 1: Write failing tests (TDD — do this first)

Create `backend/tests/routers/test_tts_thread_pool.py` with all test classes above. Run to confirm they fail:

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest tests/routers/test_tts_thread_pool.py -v
# Expected: most tests FAIL (AttributeError: module 'app.main.app.state' has no attribute 'tts_executor')
```

### Step 2: Add executor to `main.py`

**In the module-level globals section** (around line 139–154), no new global variable needed — `app.state` is the storage.

**In `startup_event()`** (at the end, before the final log lines), add:

```python
# TTS thread pool — offloads blocking file I/O from the async event loop
import concurrent.futures
app.state.tts_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="tts-worker"
)
logger.info("TTS thread pool started — max_workers=2")
```

**In `shutdown_event()`** (after `clear_exchange_client_cache()`), add:

```python
# Shut down TTS thread pool — wait for any in-flight file I/O to complete
if hasattr(app.state, 'tts_executor'):
    app.state.tts_executor.shutdown(wait=True)
    logger.info("TTS thread pool shut down")
```

### Step 3: Wrap blocking file I/O in `_get_or_create_tts()`

**Target function**: `_get_or_create_tts()` in `backend/app/routers/news_tts_router.py`

Import at module level (add to existing imports):

```python
import asyncio
from app.main import app  # for app.state.tts_executor
```

Wait — there is a **circular import risk** here: `news_tts_router.py` is imported by `news_router.py` which is imported by `main.py`. Importing `app` from `main.py` inside the router creates a circular import.

**Solution**: Get the executor via `asyncio.get_event_loop()` and pass it from the request context, OR use a module-level accessor that defers the import. The cleanest approach is a **lazy accessor**:

```python
def _get_tts_executor():
    """Lazily get the TTS executor from app.state. Deferred to avoid circular import."""
    from app.main import app as _app  # deferred import — safe, main is fully loaded by request time
    return getattr(_app.state, 'tts_executor', None)
```

Then in `_get_or_create_tts()`, replace the two blocking file operations:

**Before (blocking):**
```python
audio_data = cache_path.read_bytes()
return audio_data, words
```

**After (non-blocking):**
```python
loop = asyncio.get_event_loop()
executor = _get_tts_executor()
audio_data = await loop.run_in_executor(executor, cache_path.read_bytes)
return audio_data, words
```

**Before (blocking write):**
```python
article_dir.mkdir(parents=True, exist_ok=True)
(TTS_CACHE_DIR / audio_path).write_bytes(audio_data)
```

**After (non-blocking):**
```python
loop = asyncio.get_event_loop()
executor = _get_tts_executor()
await loop.run_in_executor(
    executor,
    lambda: (
        article_dir.mkdir(parents=True, exist_ok=True) or
        (TTS_CACHE_DIR / audio_path).write_bytes(audio_data)
    )
)
```

Or more readably, define a small sync helper:

```python
def _write_tts_file(article_dir, tts_cache_dir, audio_path, audio_data):
    """Sync helper: create directory and write TTS audio file."""
    article_dir.mkdir(parents=True, exist_ok=True)
    (tts_cache_dir / audio_path).write_bytes(audio_data)

# In _get_or_create_tts:
loop = asyncio.get_event_loop()
executor = _get_tts_executor()
await loop.run_in_executor(
    executor, _write_tts_file,
    article_dir, TTS_CACHE_DIR, audio_path, audio_data,
)
```

**Graceful fallback**: If `executor` is `None` (e.g., in tests that don't set `app.state`), `run_in_executor(None, ...)` uses the default thread pool — still non-blocking, just not the dedicated pool. This is safe.

### Step 4: Run tests — they should now pass

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest tests/routers/test_tts_thread_pool.py -v
```

### Step 5: Run existing TTS tests to confirm no regression

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest tests/routers/test_news_tts_router.py -v
```

---

## Implementation Tasks (in order)

1. **Create `backend/tests/routers/test_tts_thread_pool.py`** with all 5 test classes (failing tests first — TDD)
2. **Run tests, confirm failures** — validates the tests are actually testing something
3. **Modify `backend/app/main.py`** — add `app.state.tts_executor` in startup and shutdown
4. **Add `_get_tts_executor()` lazy accessor** in `news_tts_router.py`
5. **Add `_write_tts_file()` sync helper** in `news_tts_router.py`
6. **Wrap `cache_path.read_bytes()`** with `run_in_executor` in `_get_or_create_tts()`
7. **Wrap `write_bytes()`** with `run_in_executor` in `_get_or_create_tts()` (cache miss path)
8. **Run failing tests** — confirm they now pass
9. **Run existing TTS tests** — confirm no regression
10. **Lint both files**

---

## Gotchas & Pitfalls

### 1. Circular import — do NOT import `app` at module level in the router

`news_tts_router.py` → `news_router.py` → `main.py`. Importing `app` at the top of the router creates a circular import chain at module load time. **Always import inside a function** (deferred import). Python caches module imports, so this is fine at runtime — by the time any request arrives, `main.py` is fully loaded.

### 2. `asyncio.get_event_loop()` deprecation in Python 3.10+

In Python 3.10+, `asyncio.get_event_loop()` emits a DeprecationWarning inside coroutines if there's no running loop. **Use `asyncio.get_running_loop()` instead** — it raises `RuntimeError` if there's no running loop (correct behavior inside an async function). Use this pattern:

```python
loop = asyncio.get_running_loop()
await loop.run_in_executor(executor, blocking_func)
```

### 3. `run_in_executor(None, ...)` is safe as a fallback

If `_get_tts_executor()` returns `None`, Python uses the default `ThreadPoolExecutor` (bounded to `min(32, os.cpu_count() + 4)` workers). This is always safe — it just doesn't use the dedicated TTS pool. Works correctly in tests that don't go through the full app startup.

### 4. Lambda in `run_in_executor` captures variables by reference

```python
# WRONG — 'audio_data' might change
await loop.run_in_executor(executor, lambda: write_bytes(audio_data))

# RIGHT — use a named function with explicit parameters
await loop.run_in_executor(executor, _write_tts_file, article_dir, TTS_CACHE_DIR, audio_path, audio_data)
```

Pass all needed variables as positional arguments to `run_in_executor`. They are evaluated immediately when the call is made, not when the thread executes.

### 5. `edge_tts` is ALREADY async — don't try to executor-wrap it

`_generate_tts()` uses `async for chunk in communicate.stream()`. This is async network I/O — it already yields back to the event loop between chunks. Wrapping it in `run_in_executor` would fail because you cannot run a coroutine in a thread pool. Leave `_generate_tts` as-is.

### 6. `app.state.tts_executor` only exists after startup

In tests that don't go through the full FastAPI startup lifecycle (which is most unit tests), `app.state.tts_executor` won't exist. The `_get_tts_executor()` accessor uses `getattr(app.state, 'tts_executor', None)` to handle this gracefully — `run_in_executor(None, ...)` uses the default pool.

### 7. `thread_name_prefix` makes debugging easier

```python
ThreadPoolExecutor(max_workers=2, thread_name_prefix="tts-worker")
```

Threads appear as `tts-worker_0`, `tts-worker_1` in `ps` output and profilers. Makes it obvious when TTS threads are active.

### 8. Executor shutdown order in `shutdown_event()`

The executor shutdown should happen **after** cancelling background asyncio tasks (so any in-flight TTS requests have already been cancelled) but the `wait=True` ensures any currently executing thread finishes its file write before the process exits. This ordering is already handled by the existing shutdown sequence.

---

## Code Reference

### Existing pattern for accessing app state (FastAPI docs approach)

```python
# In an endpoint:
@router.post("/something")
async def endpoint(request: Request):
    executor = request.app.state.tts_executor
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(executor, blocking_func)
```

However, `_get_or_create_tts()` is a helper, not an endpoint handler, and doesn't receive `request`. The deferred module-level import approach is cleaner for this case.

### Location of blocking file I/O in `_get_or_create_tts()`

From `backend/app/routers/news_tts_router.py`:

- **Line ~300**: `audio_data = cache_path.read_bytes()` — cache hit read
- **Line ~311–314**: `article_dir.mkdir(...)` + `(TTS_CACHE_DIR / audio_path).write_bytes(audio_data)` — cache miss write

### Existing `run_in_executor` pattern in the codebase

Search for existing uses:
```bash
grep -r "run_in_executor" /home/ec2-user/ZenithGrid/backend/app/ --include="*.py"
```

### Python docs reference

- `loop.run_in_executor`: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_in_executor
- `ThreadPoolExecutor`: https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ThreadPoolExecutor
- `asyncio.get_running_loop()`: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.get_running_loop

---

## Validation Gates

### 1. Run new failing tests first (TDD gate — must fail before implementation)

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest tests/routers/test_tts_thread_pool.py -v 2>&1 | tail -20
# Expected: FAILED (AttributeError or AssertionError on missing executor)
```

### 2. After implementation — new tests must pass

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest tests/routers/test_tts_thread_pool.py -v
# Expected: All PASSED
```

### 3. Regression — existing TTS tests must still pass

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest tests/routers/test_news_tts_router.py -v
# Expected: All PASSED (no regression)
```

### 4. Python lint

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m flake8 --max-line-length=120 \
    app/main.py \
    app/routers/news_tts_router.py
# Expected: no output (clean)
```

### 5. Import check (circular import detection)

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -c "import app.routers.news_tts_router; print('Import OK')"
# Expected: "Import OK" — no circular import error
```

### 6. Full test suite for changed modules

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest tests/routers/test_tts_thread_pool.py tests/routers/test_news_tts_router.py -v
# Expected: All PASSED
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Circular import when importing `app` in router | Use deferred import inside `_get_tts_executor()` — Python module cache makes this safe at request time |
| `app.state.tts_executor` not set in unit tests | `getattr(app.state, 'tts_executor', None)` falls back to default thread pool via `run_in_executor(None, ...)` |
| `edge_tts` still blocks loop if network is slow | Out of scope — `edge_tts` is async; it yields between chunks. Network latency shows as multiple small yields, not a single block. |
| Executor thread count grows unbounded | `max_workers=2` is fixed at construction — ThreadPoolExecutor enforces this |
| File write fails in executor thread | Exception propagates through `await run_in_executor(...)` — caught by the existing `except Exception` in `text_to_speech_with_sync` → returns 500 |
| Executor not shut down (resource leak) | `shutdown_event()` explicitly calls `app.state.tts_executor.shutdown(wait=True)` |
| Lambda captures by reference in executor call | Use named helper function `_write_tts_file()` with explicit parameters instead of lambda |

---

## Quality Checklist

- [x] All necessary context included (TTS router code, main.py lifecycle, existing test patterns)
- [x] Validation gates are executable
- [x] References existing patterns (app.state, shutdown_event pattern, existing TTS tests)
- [x] Clear implementation path (10 tasks in order)
- [x] Error handling documented (executor fallback, circular import, exception propagation)
- [x] TDD requirement met — failing tests written before implementation
- [x] edge_tts async nature explained (critical gotcha — can't executor-wrap async functions)
- [x] Circular import risk identified and mitigated
