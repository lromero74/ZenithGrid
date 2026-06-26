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

## 🟠 Batch B — reliability cluster (deferred, next release)

- [ ] **`shutdown_manager.prepare_shutdown` TOCTOU** — flag set + in-flight count read outside
  the lock; a narrow window can let an order increment after "ready," exiting mid-order.
- [ ] **`perps_executor`** — close booked at the pre-trade `current_price` estimate, not the
  confirmed fill price; and a post-order DB failure returns `(None,None)` (indistinguishable
  from rejection) → live position on the exchange with no DB record.
- [ ] **`prop_guard_monitor`** — kill-switch flag can be committed even when liquidation fails
  (account marked killed, positions still open); also one DB session spans all accounts.
- [ ] **Observability** — close-short BTC-price fetch swallowed with no log (`buy_executor`);
  `multi_bot_monitor._process_single_bot` logs without `exc_info`.
- [ ] **`speculative_calibration_monitor`** — one shared session across all users; a PG error
  mid-loop leaves the session failed and silently skips the rest. (Per-user session.)
- [~] **`rebalance_monitor._processing`** / **`auto_buy_monitor._pending_orders`** /
  **`multi_bot_monitor` caches** — in-asyncio single-thread these can't tear, but a few
  logical TOCTOU/ordering windows exist around the admin-triggered `cleanup_caches`. Low
  urgency; revisit with the lifecycle batch.

## ⚪ Dismissed / won't-fix (verified)

- **`/api/news/image/{id}` unauthenticated** — by design: browser `<img>` tags can't send the
  JWT header, the data is public news thumbnails, and path traversal is already guarded.
- **DEX swap-output placeholder, ByBit `get_order` symbol/limit, `start=0` falsy,
  `_rebalancer_group_cache` redundant fetch** — DEX/ByBit not in production; latent. Noted.
- **`get_perps_portfolio` owner-only vs `list_perps_positions` accessible** — functional
  asymmetry, not a data leak.
