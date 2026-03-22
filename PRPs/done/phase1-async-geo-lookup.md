# PRP: Phase 1.4 — Async Concurrent Geo Lookups in Ban Monitor

**Feature**: Parallelise IP geo lookups in `ban_monitor._query_fail2ban()` using `concurrent.futures.ThreadPoolExecutor`
**Created**: 2026-03-21
**One-Pass Confidence Score**: 9/10

> Isolated change to a single service file. All subprocess and HTTP behaviour is already tested and mocked. The only new surface is the concurrent dispatch path and its interaction with the existing `_geo_cache`. High confidence because the fix follows a well-understood pattern (thread pool with a bounded worker count), tests are straightforward to write with mocks, and no external interfaces change.

---

## Context & Goal

### Problem

`ban_monitor._query_fail2ban()` runs in a `ThreadPoolExecutor` via `loop.run_in_executor()`. Inside that function, `_lookup_ip_geo()` is called serially for every banned IP — one HTTP request at a time with a 5-second timeout. With 200+ banned IPs on a fresh process start (empty `_geo_cache`), the first refresh takes **200 × 5s worst-case = ~16 minutes** before any data appears in the admin panel.

The geo cache added in v2.125.4 correctly prevents repeated lookups across refreshes — but it does nothing to speed up the cold-start case where the cache is empty.

### Solution

Keep `_query_fail2ban()` synchronous (it still runs in the existing `run_in_executor` call). Inside it, after collecting all banned IPs from fail2ban output, split them into:

1. **Cache hits** — geo data already in `_geo_cache`, resolved instantly with no I/O.
2. **Cache misses** — IPs that need a network call.

For cache misses, dispatch all lookups concurrently using `concurrent.futures.ThreadPoolExecutor` with a bounded worker count of 10. This limits concurrent connections to ipinfo.io (polite rate), while still reducing a 200-IP cold start from ~16 minutes to ~(200/10) × 5s worst-case = ~100 seconds, and typically much less on a fast connection.

The `_geo_cache` contract is preserved exactly: successful lookups are cached, failures are not (so transient errors are retried next cycle).

### Who Benefits

Admins — the ban monitor panel populates within seconds of a restart instead of taking minutes.

### Scope

- **In**: Parallelise uncached geo lookups inside `_query_fail2ban()`; add a new internal helper `_lookup_ip_geo_bulk()`
- **Out**: Changing the async/sync boundary (`refresh_ban_snapshot` stays async, `_query_fail2ban` stays sync), replacing urllib with aiohttp, changing `_geo_cache` semantics, adding new API endpoints

---

## TDD Plan — Write Tests FIRST

### Step 1: Write failing tests (before touching `ban_monitor.py`)

Add a new test class `TestLookupIpGeoBulk` and extend `TestQueryFail2ban` in
`backend/tests/services/test_ban_monitor.py`. All tests must **fail** at this stage because `_lookup_ip_geo_bulk` does not yet exist.

#### Test class: `TestLookupIpGeoBulk`

These tests drive the new `_lookup_ip_geo_bulk(ips: list[str]) -> dict[str, dict]` helper directly.

**Test 1 — happy path: all uncached IPs are looked up and returned**
```python
def test_bulk_lookup_returns_geo_for_all_ips(self):
    """Happy path: N uncached IPs each get a geo result."""
    ips = ["1.1.1.1", "2.2.2.2", "3.3.3.3"]
    payload = {"city": "X", "country": "US", "org": "AS1 Test", "region": "CA", "hostname": None}

    with patch('urllib.request.urlopen', return_value=self._make_urlopen_mock(payload)) as mock_open:
        result = _lookup_ip_geo_bulk(ips)

    assert set(result.keys()) == set(ips)
    assert mock_open.call_count == 3
    assert result["1.1.1.1"]["country"] == "US"
```

**Test 2 — cache hits skip the network**
```python
def test_bulk_lookup_skips_cached_ips(self):
    """Cached IPs are returned from cache; only uncached IPs hit the network."""
    ban_mod._geo_cache["1.1.1.1"] = {"city": "Cached", "country": "CA", "org": "X", "region": "Y", "hostname": None}
    ips = ["1.1.1.1", "2.2.2.2"]
    payload = {"city": "Fresh", "country": "DE", "org": "AS2 Ex", "region": "Z", "hostname": None}

    with patch('urllib.request.urlopen', return_value=self._make_urlopen_mock(payload)) as mock_open:
        result = _lookup_ip_geo_bulk(ips)

    assert mock_open.call_count == 1          # Only "2.2.2.2" needed a network call
    assert result["1.1.1.1"]["country"] == "CA"   # From cache
    assert result["2.2.2.2"]["country"] == "DE"   # From network
```

**Test 3 — error in one lookup does not abort others**
```python
def test_bulk_lookup_error_in_one_does_not_abort_others(self):
    """A network error on one IP returns {} for that IP; others succeed."""
    def urlopen_side_effect(req, timeout):
        if "2.2.2.2" in req.full_url:
            raise Exception("Connection refused")
        mock = MagicMock()
        mock.read.return_value = json.dumps({
            "city": "Good", "country": "JP", "org": "AS4713 NTT", "region": "TK", "hostname": None
        }).encode()
        mock.__enter__ = MagicMock(return_value=mock)
        mock.__exit__ = MagicMock(return_value=False)
        return mock

    ips = ["1.1.1.1", "2.2.2.2", "3.3.3.3"]
    with patch('urllib.request.urlopen', side_effect=urlopen_side_effect):
        result = _lookup_ip_geo_bulk(ips)

    assert result["1.1.1.1"]["country"] == "JP"
    assert result["2.2.2.2"] == {}            # Error → empty dict
    assert result["3.3.3.3"]["country"] == "JP"
```

**Test 4 — semaphore limits peak concurrency to MAX_GEO_WORKERS**
```python
def test_bulk_lookup_concurrency_bounded_by_worker_count(self):
    """At most MAX_GEO_WORKERS threads are active simultaneously."""
    import threading
    import time as time_mod

    peak_concurrent = [0]
    current_concurrent = [0]
    lock = threading.Lock()

    def slow_urlopen(req, timeout):
        with lock:
            current_concurrent[0] += 1
            if current_concurrent[0] > peak_concurrent[0]:
                peak_concurrent[0] = current_concurrent[0]
        time_mod.sleep(0.05)  # Simulate network latency
        with lock:
            current_concurrent[0] -= 1
        mock = MagicMock()
        mock.read.return_value = json.dumps(
            {"city": "X", "country": "US", "org": "A", "region": "B", "hostname": None}
        ).encode()
        mock.__enter__ = MagicMock(return_value=mock)
        mock.__exit__ = MagicMock(return_value=False)
        return mock

    ips = [f"10.0.{i}.1" for i in range(30)]  # 30 IPs > MAX_GEO_WORKERS

    with patch('urllib.request.urlopen', side_effect=slow_urlopen):
        _lookup_ip_geo_bulk(ips)

    assert peak_concurrent[0] <= ban_mod.MAX_GEO_WORKERS
```

**Test 5 — empty list returns empty dict immediately**
```python
def test_bulk_lookup_empty_list_returns_empty_dict(self):
    """Edge case: no IPs → empty result, no network calls."""
    with patch('urllib.request.urlopen') as mock_open:
        result = _lookup_ip_geo_bulk([])
    assert result == {}
    mock_open.assert_not_called()
```

**Test 6 — all IPs cached returns results without any network call**
```python
def test_bulk_lookup_all_cached_makes_no_network_calls(self):
    """All IPs already in cache → zero HTTP requests."""
    ips = ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
    for ip in ips:
        ban_mod._geo_cache[ip] = {"city": "C", "country": "CN", "org": "X", "region": "Y", "hostname": None}

    with patch('urllib.request.urlopen') as mock_open:
        result = _lookup_ip_geo_bulk(ips)

    mock_open.assert_not_called()
    assert all(result[ip]["country"] == "CN" for ip in ips)
```

**Test 7 — failed lookups are not cached (retried next cycle)**
```python
def test_bulk_lookup_failed_ips_not_stored_in_cache(self):
    """IPs whose lookup fails must not be stored in _geo_cache."""
    with patch('urllib.request.urlopen', side_effect=Exception("Timeout")):
        _lookup_ip_geo_bulk(["10.0.0.99"])
    assert "10.0.0.99" not in ban_mod._geo_cache
```

#### Extension: `TestQueryFail2ban` — verify bulk path is used

**Test 8 — _query_fail2ban calls _lookup_ip_geo_bulk not _lookup_ip_geo for multiple IPs**
```python
def test_query_fail2ban_uses_bulk_lookup(self):
    """_query_fail2ban must delegate to _lookup_ip_geo_bulk (not serial _lookup_ip_geo)."""
    status_output = "Status\n`- Jail list:\tsshd\n"
    jail_output = (
        "Status for the jail: sshd\n"
        "|- Currently banned:\t3\n"
        "|- Total banned:\t3\n"
        "|- Total failed:\t10\n"
        "`- Banned IP list:\t1.1.1.1 2.2.2.2 3.3.3.3\n"
    )

    def mock_run(cmd, **kwargs):
        r = MagicMock(); r.returncode = 0
        r.stdout = status_output if len(cmd) == 3 else jail_output
        return r

    bulk_result = {"1.1.1.1": {"country": "US"}, "2.2.2.2": {"country": "DE"}, "3.3.3.3": {"country": "JP"}}

    with patch('subprocess.run', side_effect=mock_run), \
         patch.object(ban_mod, '_lookup_ip_geo_bulk', return_value=bulk_result) as mock_bulk, \
         patch.object(ban_mod, '_lookup_ip_geo') as mock_serial:
        snapshot = _query_fail2ban()

    mock_bulk.assert_called_once()
    mock_serial.assert_not_called()
    assert snapshot.banned_ips[0].country == "US"
    assert snapshot.banned_ips[1].country == "DE"
    assert snapshot.banned_ips[2].country == "JP"
```

### Step 2: Run tests — confirm they all fail

```bash
cd /home/ec2-user/ZenithGrid/backend && \
  ./venv/bin/python3 -m pytest tests/services/test_ban_monitor.py \
    -v -k "bulk or uses_bulk" 2>&1 | tail -30
```

All 8 new tests must show `FAILED` (ImportError or AttributeError on `_lookup_ip_geo_bulk` / `MAX_GEO_WORKERS`). If any pass without implementation, the test is not testing anything useful — fix it before proceeding.

---

## Implementation Tasks

### Task 1: Add `MAX_GEO_WORKERS` constant and `_lookup_ip_geo_bulk()` to `ban_monitor.py`

**File**: `backend/app/services/ban_monitor.py`

**Changes**:

1. Add import at the top of the file (alongside existing imports):
   ```python
   from concurrent.futures import ThreadPoolExecutor, as_completed
   ```

2. Add module-level constant after the `_geo_cache` definition:
   ```python
   # Maximum concurrent threads for geo lookups — polite to ipinfo.io.
   MAX_GEO_WORKERS = 10
   ```

3. Add the new helper function after `_lookup_ip_geo()`:
   ```python
   def _lookup_ip_geo_bulk(ips: list[str]) -> dict[str, dict]:
       """Look up geo data for multiple IPs concurrently.

       Cache hits are resolved instantly. Uncached IPs are dispatched in parallel
       using a bounded ThreadPoolExecutor (MAX_GEO_WORKERS concurrent requests).
       Results are merged and returned as {ip: geo_dict}.

       A failure on any individual IP returns {} for that IP and does not affect
       others. The _geo_cache contract is preserved: only successful lookups are stored.
       """
       if not ips:
           return {}

       result: dict[str, dict] = {}
       uncached: list[str] = []

       for ip in ips:
           if ip in _geo_cache:
               result[ip] = _geo_cache[ip]
           else:
               uncached.append(ip)

       if not uncached:
           return result

       with ThreadPoolExecutor(max_workers=MAX_GEO_WORKERS) as pool:
           future_to_ip = {pool.submit(_lookup_ip_geo, ip): ip for ip in uncached}
           for future in as_completed(future_to_ip):
               ip = future_to_ip[future]
               try:
                   result[ip] = future.result()
               except Exception as e:
                   logger.debug(f"Bulk geo lookup future error for {ip}: {e}")
                   result[ip] = {}

       return result
   ```

   Note: `_lookup_ip_geo()` already handles its own exceptions and returns `{}` on failure, so the `except` branch in the future handler is a belt-and-suspenders guard for unexpected executor errors only.

### Task 2: Update `_query_fail2ban()` to collect all IPs first, then call `_lookup_ip_geo_bulk()`

**File**: `backend/app/services/ban_monitor.py`

**Current logic** (inside the jail loop, lines 135-147):
```python
elif "Banned IP list:" in line:
    ips = line.split(":", 1)[1].strip().split()
    for ip in ips:
        ip = ip.strip()
        if ip:
            geo = _lookup_ip_geo(ip)
            snapshot.banned_ips.append(BannedIP(
                ip=ip, jail=jail,
                ...
            ))
```

**New logic** — two-pass approach:

Pass 1: parse fail2ban output and collect `(ip, jail)` pairs into a staging list. No geo lookups yet.

Pass 2: after all jails are parsed, extract unique IPs, call `_lookup_ip_geo_bulk()` once, then build the `BannedIP` list.

Replace the relevant section with:
```python
# Collect all (ip, jail) pairs from fail2ban output — no geo lookups yet
_pending: list[tuple[str, str]] = []  # declared before the jail loop

# Inside the jail loop, replace the geo-lookup block:
elif "Banned IP list:" in line:
    raw_ips = line.split(":", 1)[1].strip().split()
    for raw_ip in raw_ips:
        raw_ip = raw_ip.strip()
        if raw_ip:
            _pending.append((raw_ip, jail))

# After the jail loop (outside the try/except that wraps jail iteration):
all_ips = list({ip for ip, _ in _pending})  # deduplicate
geo_map = _lookup_ip_geo_bulk(all_ips)

for ip, jail in _pending:
    geo = geo_map.get(ip, {})
    snapshot.banned_ips.append(BannedIP(
        ip=ip, jail=jail,
        city=geo.get("city"),
        region=geo.get("region"),
        country=geo.get("country"),
        org=geo.get("org"),
        hostname=geo.get("hostname"),
    ))
```

The full restructured `_query_fail2ban()` becomes:

```python
def _query_fail2ban() -> BanSnapshot:
    """Query fail2ban-client for current ban status. Runs synchronously (subprocess).

    Geo lookups for uncached IPs are parallelised via _lookup_ip_geo_bulk().
    """
    snapshot = BanSnapshot(last_updated=time.time())
    pending: list[tuple[str, str]] = []  # (ip, jail)

    try:
        result = subprocess.run(
            ["sudo", "fail2ban-client", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.warning(f"fail2ban-client status failed: {result.stderr}")
            return snapshot

        jails = []
        for line in result.stdout.splitlines():
            if "Jail list:" in line:
                jails = [j.strip() for j in line.split(":", 1)[1].split(",") if j.strip()]

        for jail in jails:
            jail_result = subprocess.run(
                ["sudo", "fail2ban-client", "status", jail],
                capture_output=True, text=True, timeout=10,
            )
            if jail_result.returncode != 0:
                continue

            for line in jail_result.stdout.splitlines():
                line = line.strip()
                if "Currently banned:" in line:
                    try:
                        snapshot.currently_banned += int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                elif "Total banned:" in line:
                    try:
                        snapshot.total_banned += int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                elif "Total failed:" in line:
                    try:
                        snapshot.total_failed += int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                elif "Banned IP list:" in line:
                    raw_ips = line.split(":", 1)[1].strip().split()
                    for raw_ip in raw_ips:
                        raw_ip = raw_ip.strip()
                        if raw_ip:
                            pending.append((raw_ip, jail))

    except subprocess.TimeoutExpired:
        logger.warning("fail2ban-client timed out")
    except FileNotFoundError:
        logger.info("fail2ban-client not found — ban monitor disabled")
    except Exception as e:
        logger.error(f"Ban monitor error: {e}")

    # Bulk geo lookup — concurrent for uncached IPs only
    all_ips = list({ip for ip, _ in pending})
    geo_map = _lookup_ip_geo_bulk(all_ips)

    for ip, jail in pending:
        geo = geo_map.get(ip, {})
        snapshot.banned_ips.append(BannedIP(
            ip=ip, jail=jail,
            city=geo.get("city"),
            region=geo.get("region"),
            country=geo.get("country"),
            org=geo.get("org"),
            hostname=geo.get("hostname"),
        ))

    return snapshot
```

### Task 3: Update test import in `test_ban_monitor.py`

Add `_lookup_ip_geo_bulk` to the import block (already written in the failing tests above):
```python
from app.services.ban_monitor import (
    BannedIP,
    BanSnapshot,
    get_ban_snapshot,
    refresh_ban_snapshot,
    _lookup_ip_geo,
    _lookup_ip_geo_bulk,
    _query_fail2ban,
)
```

Also import `MAX_GEO_WORKERS` where needed by the concurrency test:
```python
import app.services.ban_monitor as ban_mod
# ban_mod.MAX_GEO_WORKERS used in test_bulk_lookup_concurrency_bounded_by_worker_count
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `backend/app/services/ban_monitor.py` | Add `MAX_GEO_WORKERS`, `_lookup_ip_geo_bulk()`, refactor `_query_fail2ban()` to two-pass with bulk lookup |
| `backend/tests/services/test_ban_monitor.py` | Add `TestLookupIpGeoBulk` (7 tests) + 1 test in `TestQueryFail2ban`; update import |

**No other files change.** The `ban_monitor_loop()`, `refresh_ban_snapshot()`, `get_ban_snapshot()`, and `BanSnapshot`/`BannedIP` dataclasses are untouched. The `AdminSecurity.tsx` frontend component is untouched.

---

## Validation Gates

### Step 1: Confirm tests fail before implementation

```bash
cd /home/ec2-user/ZenithGrid/backend && \
  ./venv/bin/python3 -m pytest tests/services/test_ban_monitor.py \
    -v -k "bulk or uses_bulk" 2>&1 | tail -20
# Expected: all 8 tests FAILED (ImportError or AttributeError)
```

### Step 2: Implement (Tasks 1 and 2 above)

### Step 3: All new tests pass

```bash
cd /home/ec2-user/ZenithGrid/backend && \
  ./venv/bin/python3 -m pytest tests/services/test_ban_monitor.py -v 2>&1 | tail -40
# Expected: all tests PASSED (new + existing)
```

### Step 4: No existing tests broken

```bash
cd /home/ec2-user/ZenithGrid/backend && \
  ./venv/bin/python3 -m pytest tests/services/test_ban_monitor.py -v 2>&1 | grep -E "(PASSED|FAILED|ERROR)"
# Expected: zero FAILED or ERROR lines
```

### Step 5: Lint

```bash
cd /home/ec2-user/ZenithGrid/backend && \
  ./venv/bin/python3 -m flake8 app/services/ban_monitor.py --max-line-length=120
# Expected: no output (zero lint errors)
```

### Step 6: Import smoke test

```bash
cd /home/ec2-user/ZenithGrid/backend && \
  ./venv/bin/python3 -c "
from app.services.ban_monitor import (
    _lookup_ip_geo_bulk, _query_fail2ban, MAX_GEO_WORKERS, BanSnapshot
)
print(f'MAX_GEO_WORKERS={MAX_GEO_WORKERS}')
print('All imports OK')
"
```

---

## Gotchas & Considerations

1. **`_lookup_ip_geo` is still kept** — it is tested directly in `TestLookupIpGeoCache` and used as the per-IP worker inside `_lookup_ip_geo_bulk`. Do not remove it.

2. **`_geo_cache` is a plain dict, not thread-safe** — CPython's GIL makes individual dict key reads/writes effectively atomic for simple get/set, but you should not rely on this for correctness. The `ThreadPoolExecutor` workers each call `_lookup_ip_geo()` which checks `_geo_cache` and writes to it. Because each future handles a distinct IP (deduplicated in the bulk caller), there are no concurrent writes to the same key. This is safe under the GIL without additional locking.

3. **Deduplication matters** — an IP can appear in multiple jails (e.g., `sshd` and `nginx-http-auth`). The `all_ips = list({ip for ip, _ in pending})` set comprehension ensures each IP is looked up only once, even if it appears in multiple jails. The `geo_map.get(ip, {})` lookup in the final loop handles this correctly.

4. **The `ThreadPoolExecutor` is local to each call** — it is not a module-level singleton. This avoids state leakage between test runs and between the 24-hour refresh cycles. The overhead of creating a pool is negligible compared to the I/O time.

5. **Test 4 (concurrency bound) uses real threads with sleep** — it is inherently timing-dependent. The `0.05s` sleep gives enough overlap that 30 tasks queued to a 10-worker pool will show measurable concurrency. If this test proves flaky in CI, replace it with a `threading.Semaphore` mock that tracks max concurrent acquisitions without real sleep.

6. **`as_completed` vs `map`** — `as_completed` is used so that results are processed as they arrive, and so that an exception in one future does not suppress others. `executor.map()` would raise on the first exception and cancel remaining work.

7. **No restart needed for test runs** — the service is not running during test execution. A backend restart is only needed after deploying to the running EC2 instance.

8. **Do not patch `concurrent.futures.ThreadPoolExecutor` in most tests** — tests 1–3 and 5–7 mock at the `urllib.request.urlopen` level, which is the correct seam. Only test 4 (concurrency bound) needs to observe threading behaviour, and it does so via a side-effect counter in the mock, not by mocking the executor itself.

---

## Expected Performance Outcome

| Scenario | Before | After |
|----------|--------|-------|
| Cold start, 200 banned IPs, 5s timeout each | ~1000s worst case (serial) | ~100s worst case (10 workers) |
| Cold start, 200 banned IPs, 0.3s avg response | ~60s | ~6s |
| Warm cache (any refresh after first) | <1s (cache hits) | <1s (unchanged) |
| 0 banned IPs | Instant | Instant |

The geo cache from v2.125.4 remains the primary defence against rate-limiting — the concurrent lookups only fire for IPs not yet in the cache.

---

## References

- Roadmap context: `docs/SCALABILITY_ROADMAP.md` § 1.4
- Source file: `backend/app/services/ban_monitor.py`
- Existing tests: `backend/tests/services/test_ban_monitor.py`
- `concurrent.futures` docs: https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.as_completed
- GIL dict safety: dict get/set on distinct keys from multiple threads is safe under CPython's GIL (each bytecode operation is atomic)
