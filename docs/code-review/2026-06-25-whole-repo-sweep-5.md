# Whole-repo code review sweep #5 — 2026-06-25

Fifth sweep (5 parallel Sonnet reviewers) after v3.13.5, with **fresh lenses** since the
codebase had already been swept four times: concurrency/races, exchange-client edge
cases, silent failures, monitor/lifecycle, and a security re-pass on the newest code.
Each reviewer read sweeps #3–#4 first; every item below was **re-verified against
current source** by the orchestrator. Status: `[ ]` open · `[x]` fixed · `~` deferred.

## 🟢 Batch A — security + clear correctness (shipped v3.13.6)

- [x] **SSRF (T1 security)** — `fetch_article_content` gated the fetch URL only against an
  allowlist built from user-supplied `ContentSource.website` values (poisonable), never
  calling the existing `validate_url_not_internal()`. A user could register a source with
  `website=http://169.254.169.254` (or `127.0.0.1:<port>`) and then fetch internal/metadata
  endpoints server-side. Fixed: the article fetcher now validates the URL is not internal
  even when allow-listed, and `add_custom_source` rejects internal url/website at the door.
  +3 tests (IP-literal, network-free).
- [x] **`order_api.py` `client_order_id` collision (T2)** — was `int(time.time()*1000)`; two
  concurrent orders in the same ms collided and Coinbase silently replayed the first
  (dropping the second). Now `…ms-{uuid4().hex}`. +1 test.
- [x] **`product_precision.py` `round()` → ROUND_DOWN (T2)** — the live-order formatters used
  banker's rounding, which can round a size UP and trigger INSUFFICIENT_FUND / invalid-
  precision rejects. Now `Decimal.quantize(ROUND_DOWN)`. +4 tests; 5 existing tests that had
  pinned the round-up values corrected.
- [x] **`batch_analyzer.py` `0.001 BTC` fallback (T2)** — a failed aggregate-balance fetch
  returned `0.001` (while the sibling available-balance fetch returns `0.0`), so the budget
  was computed off invented data during an API outage. Now returns `0.0` + `logger.error`.

## 🟠 Batch B — reliability cluster (shipped v3.13.7, except A)

- [~] **`shutdown_manager.prepare_shutdown` TOCTOU** — **dismissed on verification.** In a
  single-threaded asyncio loop there is no `await` between setting `_shutting_down=True` and
  reading `_in_flight_count`, so the read is atomic; and `increment_in_flight` re-checks the
  flag under the lock and fails closed. No real race. (The reviewer applied threading
  reasoning that doesn't hold in asyncio.)
- [x] **`perps_executor`** — close now books P&L at the confirmed `average_filled_price`
  (fetched via `get_order`), not the pre-trade estimate; and a DB failure *after* the order is
  placed now logs CRITICAL + `realmoney_audit("perps_open_orphaned")` with the order_id
  instead of returning a rejection-shaped `(None,None)` silently. +2 tests.
- [x] **`prop_guard_monitor`** — `_kill_account` commits the kill state **before** liquidation
  (durable even if liquidation fails); the account loop commits per-account with rollback on
  error so one account can't discard another's snapshot.
- [x] **Observability** — close-short BTC-price fetch now `logger.warning(exc_info=True)`;
  `multi_bot_monitor._process_single_bot` now logs with `exc_info=True`.
- [x] **`speculative_calibration_monitor`** — now opens a fresh session per user, so a
  PostgreSQL error on one user can't poison the rest of the pass.
- [~] **`rebalance_monitor._processing`** / **`auto_buy_monitor._pending_orders`** /
  **`multi_bot_monitor` caches** — **left as-is.** Single-threaded asyncio means no torn
  writes; the only windows are logical ordering around the admin-triggered `cleanup_caches`,
  which is not on a money path. Not worth the lock churn.

## ⚪ Dismissed / won't-fix (verified)

- **`/api/news/image/{id}` unauthenticated** — by design: browser `<img>` tags can't send the
  JWT header, the data is public news thumbnails, and path traversal is already guarded.
- **DEX swap-output placeholder, ByBit `get_order` symbol/limit, `start=0` falsy,
  `_rebalancer_group_cache` redundant fetch** — DEX/ByBit not in production; latent. Noted.
- **`get_perps_portfolio` owner-only vs `list_perps_positions` accessible** — functional
  asymmetry, not a data leak.
