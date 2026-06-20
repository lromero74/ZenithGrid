# Changelog

All notable changes to BTC-Bot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v3.8.0] - 2026-06-19

### Added
- Custom DSL scripting strategy (`dsl_trading`): write your own trading logic in a small, sandboxed mini-language — e.g. `if rsi(14) < 30: limit('buy', 'ETH-USD', 0.05)` or `if price('BTC-USD') > 100000: market('sell', 'BTC-USD', all)`. Supports `price()`, `rsi()`, `macd()`, Bollinger `%B`, and `limit`/`market` order actions with an optional `price='-1%'` offset. The script is parsed and validated when you save the bot (clear errors with line/column), and runs in a strict sandbox that cannot import modules, read files, reach the network, or access attributes — only the whitelisted market-data and order functions.

## [v3.7.0] - 2026-06-19

### Added
- TradingView webhook integration: bots can now receive alert webhooks from TradingView to trigger buy/sell actions. Each bot gets a unique webhook token (generated on creation with `webhook_enabled=True` or via the `POST /api/bots/{bot_id}/webhook-token` endpoint). Webhooks are rate-limited to 10 requests/minute per token and rejected for stopped bots.
- Telegram notification integration: users can configure a Telegram bot token and chat ID in settings to receive trade fill, position opened/closed, and bot started/stopped notifications. Supports commands via Telegram webhook: `/status`, `/positions`, `/pnl`, `/start <bot>`, `/stop <bot>`, `/help`. Notification types are individually toggleable.
- Fear & Greed Index indicator: adds FEAR_GREED as a tradeable aggregate indicator in the condition builder (e.g., `FEAR_GREED <= 25` to buy in extreme fear). Fetches from the alternative.me API with a 1-hour process-level cache and graceful fallback to the last known value on API failure.
- Backtesting engine: replay historical candle data through any strategy and get a performance report (total return, win rate, max drawdown, Sharpe ratio, profit factor, equity curve, trade list). Available via `POST /api/backtesting/run`. Uses a SimulatedBroker that handles buys, DCA, sells, and fee deduction.
- Automation rules: user-configurable if-then rules with trigger types (price threshold, holding threshold, profitability threshold, period check) and action types (cancel open orders, sell all positions, stop all bots, stop specific bots, start bot, send Telegram notification). Rules are account-scoped. CRUD via `/api/automation/rules`, manual trigger test via `/api/automation/rules/{id}/test`.
- Crypto basket / index trading strategy: a new `basket_trading` strategy that maintains a weighted basket of cryptocurrencies and auto-rebalances when allocations drift beyond a configurable threshold. Supports JSON string or list composition, weight normalization, drift computation, and generates buy/sell rebalance signals.
- Strategy optimizer / parameter sweep: sweep parameter permutations through the backtesting engine and rank results by fitness metrics (total return, Sharpe ratio, profit factor, win rate, max drawdown inverse). Generates all combinations from parameter ranges, runs a backtest for each, and returns a ranked report with the best configurations. Exposed via `POST /api/backtesting/optimize`.
- Market making strategy: a new `market_making` strategy that provides liquidity by placing symmetric buy/sell limit orders around a reference (order-book mid) price, profiting from the spread. Supports configurable spread (bps), order size, max inventory, recenter threshold, and inventory-skew that biases quotes to mean-revert holdings. Account-scoped; created stopped.

## [v3.6.0] - 2026-06-19

### Changed
- Take-profit targets are now honored **net of trading fees**. A bot no longer sells the instant gross profit reaches your target if round-trip fees would drop the net below it — every take-profit path (fixed, trailing activation, condition/minimum, the limit-order and order-book profit guards, and the market-order fallback) now requires your configured target to clear *after* fees, calibrated from the fee rate each position was actually charged.

## [v3.5.0] - 2026-06-19

### Added
- Closed deals now show whether the exit was manual or automatic, the triggering reason, exchange order ID, process role, and host that executed it.
- Automatic exits from an unexpected production process display a persistent warning, making stale-host activity immediately visible.

### Changed
- Bidirectional short trades now record actual entry and cover fees and report fee-net realized P&L; the account-scoped fee backfill supports both long and short spot history.

## [v3.4.12] - 2026-06-19

### Fixed
- The account-scoped spot-fee backfill now runs correctly from its documented repository location.

## [v3.4.11] - 2026-06-19

### Changed
- Spot trade P&L now uses actual exchange fees from both entries and exits, with a safe account-scoped backfill for existing Coinbase history.

## [v3.4.10] - 2026-06-19

### Fixed
- Final safety orders now tolerate only product-specific fill-rounding drift and round down to the exchange's quote increment, allowing the remaining position allocation to be used without exceeding its hard budget cap.

## [v3.4.9] - 2026-06-19

### Changed
- Production can now run the public web API separately from the exclusive trading worker, keeping page requests isolated from trading-loop load.
- The canonical deploy script detects split mode, restarts both services, and verifies each process reports its expected role.

### Added
- A self-verifying Lightsail cutover script installs the web/trader systemd units and automatically restores the combined service if either role fails health checks; `--rollback` restores combined mode explicitly.

## [v3.4.8] - 2026-06-19

### Added
- Web and trader process roles can now be staged independently, while the default combined role preserves the current deployment.
- Trading startup is protected by a renewable Redis leader lease; a second trader is rejected, and lease loss terminates the trader fail-closed before another process can take over.

## [v3.4.7] - 2026-06-19

### Changed
- Open-position loading now returns trade counts, safety-order totals, first/last buy data, and pending-order counts in the account-scoped position query, eliminating four database round-trips per refresh.

## [v3.4.6] - 2026-06-18

### Added
- Privacy-safe in-memory p50/p95/max timing summaries for backend route templates and browser startup milestones, available only to superusers at `/api/performance/summary`.

### Fixed
- The atomic Lightsail deploy now waits up to 60 seconds for application readiness instead of failing while systemd is active but Uvicorn is still starting.

## [v3.4.5] - 2026-06-18

### Changed
- Production frontend releases are now built off-host, uploaded as immutable versioned artifacts, and activated with an atomic symlink switch instead of rebuilding the live `dist` directory on the trading server.
- The canonical Lightsail deploy command now validates a clean tagged checkout, verifies production health, and supports immediate frontend rollback to the previous artifact.

## [v3.4.4] - 2026-06-18

### Changed
- Hard refresh metadata no longer waits for a remote `git fetch`; the app bootstrap endpoint now uses short-lived local version caches while explicit changelog refreshes retain remote update checks.

### Fixed
- Backend rebalance, TTS, and news-image tests no longer escape their fixtures and attempt live Coinbase, Bing, or DNS requests.

## [v3.4.3] - 2026-06-18

### Added
- Hard refreshes can paint a two-minute, user- and account-scoped tab cache immediately while revalidating every restored value against production.
- Browser startup milestones and API `Server-Timing` headers make authentication, account, route, and page-data latency visible in performance tooling.

### Changed
- The Positions page now loads completed-trade statistics, realized P&L, and balances through one account-scoped startup request instead of three HTTP round trips.
- Realized P&L native-currency totals are fully aggregated by product in SQL, eliminating row-by-row closed-position materialization.

## [v3.4.2] - 2026-06-18

### Changed
- Route-specific Lucide icons no longer inflate the blocking framework bundle, reducing the shared compressed startup payload by about 32 KB.

## [v3.4.1] - 2026-06-18

### Changed
- Hard refreshes restore valid authentication immediately instead of flashing a full-screen login loader.
- Positions and Bots begin loading against the saved account in parallel with account metadata, without first issuing duplicate unscoped requests.
- Direct-route bundles preload during startup.

## [v3.4.0] - 2026-06-18

### Changed
- Optimized Positions and Pages page load times:
  - **Backend**: `/positions/realized-pnl` now uses SQL conditional aggregation (`CASE WHEN` inside `SUM`) instead of fetching all closed positions and bucketing them in Python, reducing response time from O(n) Python iteration to a single indexed SQL query for USD profit sums.
  - **Frontend**: Position polling interval reduced from 5s to 10s, batch price polling from 5s to 15s, reducing API call frequency by ~60%.
  - **Frontend**: Combined four independent `usePosLfilter` loops (markets, bots, pairs, categories) into a single O(n) pass, reducing client-side recalculation work.
  - **Frontend**: Prior stats, realized-PnL, and balances queries retain their 120s interval; bots list retains 30s interval.

## [v3.3.9] - 2026-06-18

### Fixed
- Trading safety guards now fail CLOSED instead of fail-open: when the exchange API is unreachable, the bot HOLDS rather than executing market orders with zero slippage protection, unverified balance, or unverified profit thresholds.
- Limit order fill processing errors now re-raise instead of silently rolling back, preventing positions from staying "open" after the exchange has already sold the coins.
- Cancel-and-replace limit orders abort the replacement if the cancelled order's fill state can't be verified, preventing potential double-sells.
- Safety order (DCA) reconciliation errors now re-raise and isolate per-order, preventing stale average entry prices and infinite retry loops.
- Rebalance monitor no longer sets failed balance fetches to 0.0 (which caused unnecessary buy trades); the currency is skipped entirely instead.
- Perps bracket order cancel failures now abort the close instead of continuing, preventing double-close scenarios.
- Position budget bar no longer shows "Infinity%" when max_quote_allowed is zero.
- Loss amounts in the Position card now show a minus sign instead of relying on color alone.
- WebSocket no longer disconnects/reconnects when toggling audio notifications.
- Toast messages for friend online/offline and account invitations no longer show "undefined" when backend payload fields are missing.
- Add Funds modal no longer propagates NaN when aggregate value fields are missing from the API response.
- Limit Close modal now cancels in-flight API requests on unmount via AbortController.
- Bot toggle in Position card reads fresh state from the query cache to prevent double-toggle on stale memoized renders.
- Bots list is now filtered server-side by account instead of fetching all accounts' bots and filtering client-side.

## [v3.3.8] - 2026-06-18

### Fixed
- The Bots-page P&L chart now keeps a guaranteed mobile height without shrinking the full-height desktop chart.

## [v3.3.7] - 2026-06-18

### Fixed
- The Bots-page P&L chart keeps its intended height instead of collapsing out of view in responsive layouts.

## [v3.3.6] - 2026-06-17

### Fixed
- Clicking Link or Unlink in the Bot Budget Rebalancer no longer also toggles the bot details drawer.

## [v3.3.5] - 2026-06-17

### Changed
- Bot Budget Rebalancer max total allocation raised from 200% to 300%.

## [v3.3.4] - 2026-06-17

### Fixed
- The bot editor's "Current effective ceiling" no longer shows `calculating…`; it starts from the known exchange floor for the quote currency and refines when the live worst-case minimum loads.

## [v3.3.3] - 2026-06-16

### Changed
- Bot Budget Rebalancer sliders now behave more intuitively: dragging one slider down leaves the others alone, and dragging one slider up only redistributes when it would exceed the group's max total allocation. When redistribution is needed, it takes from the unlocked bot with the most allocation first.
- Bot Budget Rebalancer max total allocation raised from 150% to 200%.

### Added
- Backend validation test for the 200% rebalancer cap and account ownership checks.
- Pure frontend unit tests covering the rebalancer slider redistribution rules (lock, bound, max-cap, and 200% mode).

## [v3.3.2] - 2026-06-16

### Fixed
- The account-value chart no longer shows deposits, withdrawals, and trades from before you started tracking. Activity markers are now bounded to your tracking start (the first snapshot — e.g. right after an account reset), so months-old fiat transfers and card spends no longer get crammed onto a freshly-reset chart. Accounts that haven't started tracking yet are unaffected (still use the normal rolling window).

## [v3.3.1] - 2026-06-16

### Fixed
- The Overall-stats balances panel understated available funds. It subtracted the cash an open position had already spent buying its coin a second time — but that money already left the wallet, so the available figure was double-reduced (e.g. it showed $12.85 available when the real wallet balance was $29.43, matching the Portfolio view). Available now equals the live wallet balance minus only what's committed to unfilled limit buy orders, and matches the Portfolio breakdown. The same fix applies to every currency row (BTC/ETH/USD/USDC/USDT).

## [v3.3.0] - 2026-06-15

### Added
- A background safety audit that hourly checks every real trading account's open positions against the live exchange wallet and warns (in the real-money audit log) if a position no longer holds enough of its coin to sell the full size. This catches the kind of balance drift that previously surfaced only as a failed sell (`INSUFFICIENT_FUND`) — now it's flagged proactively, before you try to exit.

## [v3.2.2] - 2026-06-15

### Fixed
- Fixed the foreign-key cleanup migration so it correctly relaxes the order-history bot link before unlinking orphaned rows (the previous build tried to unlink first and stopped partway). Added guard tests that keep the migration's policy table from ever drifting out of sync with the models.

## [v3.2.1] - 2026-06-15

### Changed
- Order-history rows are now preserved when the bot that created them is deleted (the link is unlinked rather than the row blocking the delete) — an order audit trail should outlive the bot it belonged to. This makes both order-history links behave the same way.

### Fixed
- Applying the new foreign-key policy to the live database also cleans up years of accumulated orphaned rows left over from before these rules were enforced: dead (already-cancelled) order references are removed, stranded audit/analysis rows are unlinked from the records they could no longer reach, and millions of context-less leftover signal rows (whose position was long gone) are cleared out. The cleanup refuses to run and stops safely if it ever finds an orphaned order that isn't already finished, so a live exchange order can never be dropped.

## [v3.2.0] - 2026-06-15

### Changed
- Made every trading-record foreign key declare its delete behavior explicitly and consistently, so deleting a parent row can never silently erase financial history. Trades, positions, and pending orders now refuse the delete (RESTRICT); analysis and audit records (signals, order history, AI-opinion logs) keep their row and simply unlink when the thing they referenced is removed (SET NULL); derived value snapshots still clean themselves up (CASCADE). A guard test now fails if any future foreign key is added without the correct policy.

### Fixed
- Corrected the fresh-install database script, which had defined the trades→position link to cascade-delete — meaning a position delete would have wiped its trade ledger. It now uses the same protective RESTRICT policy as every other install path.

## [v3.1.0] - 2026-06-15

### Added
- A single, tested account-purge path (`app.services.account_purge.purge_account_history` + `scripts/purge_account.py`) that wipes one account's trade/order/position/value history in the correct foreign-key order, in one transaction, while preserving the account and its bots. Replaces ad-hoc reset scripts. Documented the trading-record foreign-key delete policy (RESTRICT on financial tables, SET NULL on analysis links, CASCADE on derived snapshots).

## [v3.0.2] - 2026-06-15

### Changed
- Hardened the paper-notification bridge so a future provider-wiring mistake can no longer blank the whole screen: it now reads its contexts through non-throwing accessors and degrades silently if mounted in the wrong place. Added a regression test that renders it with no providers and asserts it never throws.

## [v3.0.1] - 2026-06-15

### Fixed
- Fixed a blank/dark screen on load introduced in v3.0.0: the paper-notification bridge was mounted outside the notification provider and threw on render. Moved it inside the provider.

## [v3.0.0] - 2026-06-15

### Added
- A notification preference (Settings → Notifications) to **hide paper-trading trade pop-ups while a real account is selected**. When you're focused on a real account, paper-account trade notifications (and their sounds) are muted; switch back to a paper account and they reappear. Off by default.

### Changed
- Version numbering: the minor number now caps at 99 and rolls the major instead (so this release is v3.0.0, not v2.171.0). A major bump on this project no longer implies a breaking change.

## [v2.170.0] - 2026-06-15

### Added
- A dedicated real-money trade audit trail. Every buy or sell placed against a real exchange account is now recorded as one structured line — what was traded, the amount, the resulting order id, success/failure (including the exchange error on failure), and crucially **which subsystem initiated it** (a specific bot, the dust sweep, the portfolio rebalancer, a panic sell, or a manual operation). It also records when a position close has to be clamped because the wallet holds less than the position recorded — the exact signal behind the "stuck, can't sell" problem — so that class of issue is greppable after the fact. The trail lives in `backend/logs/real_money_trades.log` and also appears in the normal application log. Paper accounts are never recorded.

## [v2.169.4] - 2026-06-15

### Fixed
- Positions could get permanently stuck, unable to sell, with a repeating `INSUFFICIENT_FUND` error when the coins actually held on the exchange had drifted below what the position recorded (from fees, earlier rebalances/dust sweeps, or partial fills). Closing a position now sells what the wallet actually holds (with a tiny safety haircut) instead of blindly trying the full recorded size — so a drifted position closes for its real proceeds and stops retrying forever. If the remaining amount is below the exchange minimum, the position is closed as dust.

### Changed
- Added protective regression tests proving neither the dust sweep nor the portfolio rebalancer will ever sell coins that are held in an open bot position.

## [v2.169.3] - 2026-06-15

### Changed
- The Account Value figure in the header now shows cents (e.g. `$58.42` instead of `$58`), so small balances and intraday changes are no longer rounded away.

## [v2.169.2] - 2026-06-14

### Fixed
- The page can no longer be dragged sideways in portrait, exposing a blank strip on the right. A deal's price-bar edge labels could overhang past the screen edge and make the whole page scroll horizontally; that overflow is now clipped at the app level (without affecting the sticky header).

## [v2.169.1] - 2026-06-14

### Fixed
- Landscape phones now use the compact header and icon-only navigation instead of the dense desktop versions, which overflowed the screen — the header no longer spills past the edge, and the navigation bar no longer has to be side-scrolled to reach every tab. The full multi-column header and labeled tabs now appear once the screen is genuinely wide enough (≈1024px).
- The Active Deals **Grid** view now tiles two cards across on a landscape phone or small tablet (previously it only tiled on a laptop-width screen and showed a single column on a phone), so the toggle's grid layout is honored on the screen sizes where it matters.

## [v2.169.0] - 2026-06-14

### Added
- Active Deals now has a view-mode switch (Table / Cards / Grid) in the top-right of the page. **Table** keeps the compact sortable rows; **Cards** shows the full rich deal card one-per-row at every width; **Grid** tiles the rich cards side by side — two across on a laptop, three on a wide monitor. Your choice is remembered.

### Fixed
- Rotating your phone to landscape (or using a small tablet) now actually uses the extra width. The whole app was previously pinned to a fixed narrow width on those screen sizes, leaving large empty margins; it now fills the available width up to large-desktop size. This also un-cramps the Active Deals page.

## [v2.168.21] - 2026-06-14

### Changed
- The dust sweep now clears everything that's actually sellable: it sweeps free, non-reserved, non-target coins down to the exchange minimum (~$1) instead of a flat $5 floor. The per-coin "dust threshold" setting now acts only as an optional *higher* floor — set it above the minimum to deliberately keep some small holdings. New accounts default to sweeping everything sellable.

### Fixed
- The dust sweep now respects minimum-balance reserves — a coin held back as a reserve (e.g. a USDT spending float) is never swept.
- The "raise min_balance_usd so the rebalancer doesn't drain cash" warning no longer fires on accounts targeting ~100% USD, where the rebalancer can only move money *into* USD and can't drain it.

## [v2.168.20] - 2026-06-14

### Fixed
- Minimum balance reserves are now always honored, even when the shortfall is tiny. If a reserve (e.g. "keep 5 USDC") is just under target, the rebalancer buys the exchange's smallest allowed order to reach it — slightly overshooting rather than leaving you below the reserve — and that small surplus isn't sold back off. Top-ups are sourced from your largest free balance first so each order clears the exchange minimum, and nothing is bought if you can't afford even one minimum order.

## [v2.168.19] - 2026-06-14

### Fixed
- The portfolio rebalancer now sells small non-USD holdings it previously left stuck. It was using a flat $10 minimum order size (actually Coinbase's *perpetual-futures* minimum) for spot trades, so a few dollars of BTC/USDC/ETH could never be converted toward a 100%-USD target. It now uses each market's real minimum (with a $1 safety floor) and validates each order against it before sending.

### Changed
- The rebalancer's default "minimum trade size" guard dropped from 5% to 2% of the portfolio, so smaller allocations rebalance too. (Existing accounts keep their saved setting; adjust it under Rebalance settings.)

## [v2.168.18] - 2026-06-14

### Changed
- Syncing deposits/withdrawals from Coinbase is now much faster for accounts that hold many coins: the per-currency lookups run in parallel (bounded) and duplicates are checked in a single query instead of one per currency.
- Internal cleanup: income- and expense-goal progress now share one realized-income calculation instead of two copies of the same logic. No change to reported numbers.

## [v2.168.17] - 2026-06-14

### Changed
- Portfolio loads stay fast as trading history grows: realized profit/loss is now totaled by the database directly instead of loading every closed position into memory on each refresh. A new index keeps that lookup quick.
- The portfolio rebalancer's "dust" cleanup prices leftover coins in parallel (bounded) instead of one slow lookup at a time, so a rebalance check with many tiny balances finishes much faster.

### Added
- Developer tooling: a live symbol registry (`scripts/symbol_registry.py`) that scans the backend and flags duplicate function definitions, to keep the codebase DRY.

## [v2.168.16] - 2026-06-14

### Changed
- Pages that show charts now load a little leaner: the two charting libraries are bundled separately, so a page only downloads the one it actually uses instead of both.
- Internal cleanup: replaced a deprecated asyncio call across several backend services with its supported equivalent. No change to behavior.

## [v2.168.15] - 2026-06-14

### Changed
- Internal/test tooling only: updated the `pytest-asyncio` test dependency to clear a spurious "unclosed event loop" warning during the test run. No change to application behavior; production runtime is unaffected.

## [v2.168.14] - 2026-06-14

### Fixed
- The backend now shuts down cleanly. A restart previously logged "Application shutdown failed" because the Redis notification listener, when stopped, raised a timeout that aborted the orderly shutdown sequence; the shutdown path now handles that case and closes the listener's connection gracefully.
- Fixed an internal resource leak where the secondary background task loop did not fully release its database connections and event loop when stopped, accumulating across restarts.

## [v2.168.13] - 2026-06-14

### Changed
- Internal code cleanup: consolidated several copy-pasted pieces of logic into single shared helpers, with no change to behavior in most places. The session-maker plumbing shared by five background services (rebalancer, auto-buy, perps, delisted-pair, content-refresh) now lives in one place, as does USD currency formatting (Dashboard, Portfolio, prop-firm status) and quote-currency price precision (slippage, limit-close, and depth-chart views).

### Fixed
- Prices quoted in USDT or USDC now display with 2 decimals (matching USD) instead of 8 in the slippage-warning dialog and the order-book depth chart — previously only plain "USD" pairs got the 2-decimal treatment.
- Negative dollar amounts in the prop-firm drawdown panel now render in the standard `-$1,234.56` form instead of `$-1,234.56`.

## [v2.168.12] - 2026-06-13

### Fixed
- **The portfolio rebalancer no longer sells coins held inside open bot positions.** Coins a bot buys (e.g. BTC bought by a USD bot on BTC-USD) sit in the spot wallet as ordinary spendable balance, so the rebalancer counted them as free and — with a target like 100% USD — would sell them out from under the open position (leaving the position with nothing to take profit on). The rebalancer now subtracts coins committed to open positions before deciding what to sell, so it only ever trades genuinely-free funds. Each position's deployed capital still counts toward its quote currency at cost (BTC-bought-with-USD counts as USD, BTC-bought-with-ETH as ETH, ETH-bought-with-USDC as USDC), which also removes a double-count in drift detection. (The bot soft-ceiling/budget calculation already accounted for positions correctly and is unchanged.)

## [v2.168.11] - 2026-06-13

### Changed
- The auto-calculated base-order sizing now derives its DCA multiplier from the single authoritative full-cycle formula instead of re-deriving the same geometric series inline. No change to the sizes any bot produces — it removes a second copy of the math that could have drifted from the soft-ceiling calculation over time.

### Fixed
- A degenerate bot configuration (e.g. a negative volume scale that collapses the DCA multiplier to zero) no longer crashes auto-calculated order sizing; it now returns a finite fallback size instead.

## [v2.168.10] - 2026-06-13

### Fixed
- **Shared-account members can now see transfer history on accounts shared with them.** Deposit/withdrawal history, the transfer summary totals, and the dashboard's recent-transfers widget were owner-only, so a manager or view-only member who could already see an account's positions, bots, and order history saw an empty transfer list for it. Members now see the transfer history, summary, and recent-transfers for any account shared with them, consistent with the rest of that account's data. No data crosses the account boundary — passing an account ID you don't have access to still returns nothing.

## [v2.168.9] - 2026-06-13

### Fixed
- **Shared-account managers can now market-sell on accounts shared with them.** The manual market-sell action was owner-only, so a manager who could already cancel orders, force-close positions, and add funds on a managed account couldn't market-sell on it. Managers can now market-sell when they specify the managed account; view-only members and non-members still cannot, and the no-account convenience default remains owner-only. The order always executes against the owning account's exchange credentials.

## [v2.168.8] - 2026-06-13

### Fixed
- **Portfolio data could leak between a user's own accounts.** The persistent (restart-surviving) portfolio cache was keyed by user instead of by account, so a user with multiple accounts (e.g. a live exchange + a paper account) could be served one account's balances/positions for another after a restart. It's now keyed per account.
- **Short bots now count their safety orders correctly.** The DCA engine counted only buy trades, so a short position — which adds via sells — reported zero safety orders, corrupting safety-order numbering, size scaling, and trigger spacing. It now counts the direction-correct entry side and uses the short average entry price as the DCA reference. (Long bots were unaffected.)
- **The bot editor's auto-calculated order sizes now respect the soft ceiling.** When a soft ceiling reduced the effective deal count (e.g. 20 → 5), the budget calculator still sized base/safety orders for the raw configured max, under-sizing them. It now uses the same effective deal count the engine and the on-screen breakdown use.
- **Shared-account access gaps closed.** Shared-account managers can now see and act on perpetual-futures positions, and view order history, on accounts shared with them (these previously returned empty or errored for non-owners); bot AI/scanner log writes now match their read permissions.

### Added
- Parity tests pinning the frontend DCA-multiplier math to the authoritative backend formula, to catch soft-ceiling sizing drift between the two.

## [v2.168.7] - 2026-06-13

### Fixed
- **Bot edit modal: condition rows now wrap on mobile instead of being clipped.** The previous attempt stopped the sideways scroll by clipping horizontal overflow, which hid the right side of the condition builder's dropdowns so they couldn't be reached. This removes the clipping and instead wraps each condition's controls onto multiple lines on small screens (with the builder scrolling horizontally as a fallback), so the controls fit *and* stay reachable.

## [v2.168.6] - 2026-06-13

### Fixed
- **The bot create/edit modal no longer scrolls sideways on phones.** The advanced condition builder lays out its conditions with fixed-width dropdowns that are wider than a phone screen; because the whole modal shared one scroll area, that width stretched every section, clipping all the form fields off the right edge. The condition builder now scrolls horizontally on its own, and the modal panel contains horizontal overflow — so every other section (basic info, market type, budget, etc.) fits the screen, and only the condition rows scroll sideways when needed.

## [v2.168.5] - 2026-06-13

### Fixed
- **The price bar and deal chart no longer show a phantom safety-order marker after a cascade.** v2.168.4 corrected the "Completed" count, but the price-bar pip and the deal chart still derived their "safety orders triggered" count from trade rows — so a fully-deployed two-level cascade still drew a pending "SO2" marker. They now use the same authoritative deployed count.

## [v2.168.4] - 2026-06-13

### Added
- **Safety orders are numbered in Trade History, with combined labels for cascades.** Each safety order now shows its level number (e.g. "Safety Order #1"). When several levels filled together in one cascade order, they're labelled as a group — "Safety Order #1 & #2" or "Safety Order #1, #2, & #3".

### Fixed
- **The position card and price bar now reflect cascaded safety orders correctly.** After the v2.168.3 engine fix, the UI still under-reported cascades — showing "Completed: 1" and a phantom pending safety-order marker on the price bar when both levels were already filled — because it counted DCA trade rows. The backend now reports an authoritative count of safety-order levels deployed, and the "Completed" count and price-bar markers use it.

## [v2.168.3] - 2026-06-13

### Fixed
- **Cascaded safety orders now count every level they deployed.** When price drops past several safety-order trigger levels between checks, the bot correctly combines them into a single "cascade" order (one real exchange order). But it counted completed safety orders by trade rows, so a 2-level cascade was counted as 1 — under-reporting progress (e.g. showing "1 of 2" when both were done) and, on bots with remaining budget, letting it re-place an already-deployed level instead of moving to the next one. Trades now record how many safety-order levels they cover, and the completed count sums those levels. (Adds migration 086. Past cascades aren't retroactively recounted; new ones are accurate.)

## [v2.168.2] - 2026-06-13

### Fixed
- **Bot edit modal no longer scrolls sideways on phones.** The remaining horizontal overflow came from the form *sections* the bot modal renders — strategy config (preset thresholds), budget, and DEX config — which still used fixed multi-column grids on the smallest screens. These now stack to a single column on mobile and expand at the `sm` breakpoint, like the rest of the modal. The responsiveness regression guard was widened to cover modal form sections (not just files named `*Modal*`), since that gap let this overflow ship; game boards and other intentional fixed-geometry grids are deliberately out of scope.

## [v2.168.1] - 2026-06-13

### Fixed
- **Modals no longer overflow sideways on phones.** Several modals (Add Account, Create/Edit Bot, Limit Close, News Source Subscriptions, Donation) laid out form fields and value pairs in fixed two-column grids at every screen size, which crammed content and forced horizontal scrolling on narrow mobile screens. Those grids now stack to a single column on small screens and expand to two columns from the `sm` breakpoint up, so everything fits without sideways scrolling. Desktop layout is unchanged.

## [v2.168.0] - 2026-06-12

### Added
- **Limit orders for short safety orders.** Short bots set to limit DCA now place their safety orders as resting limit sells that *add* to the position when they fill, instead of silently falling back to a market order. This gives short DCA the same maker-style, price-controlled entries that long bots already had.

### Fixed
- **Filled limit DCA safety orders are now applied to the position.** Previously a limit safety order could be placed but its fill was never reconciled back into the position (it would show up only as a "stuck pending order"). A new reconciler now detects safety-order fills — for both long and short bots — and grows the position correctly (updating size and average entry), records the trade in your order history, and sends a fill notification. It never closes the position on a safety fill and is safe against partial fills and duplicates.

## [v2.167.12] - 2026-06-12

### Fixed
- **Transient Coinbase auth rejections (HTTP 401) are now retried with fresh credentials.** Authenticated requests regenerate their JWT/HMAC signature on each attempt and retry 401s (alongside the existing 429 handling) with exponential backoff, instead of failing immediately. This smooths over short-lived clock-skew / token-timing rejections that previously surfaced as spurious errors. Persistent 401s still raise after the retries are exhausted.
- **`service.sh status` no longer errors on older Bash.** Replaced a Bash 4+ uppercase expansion with a portable equivalent so the status command works on stock macOS Bash 3.2.

## [v2.167.11] - 2026-06-12

### Fixed
- **Bidirectional bots with auto-calc + soft ceiling now size their base orders correctly.** When the soft ceiling was active, bidirectional (long/short) bots split their budget across the *configured* max deals (e.g. 20) instead of the *effective* soft-ceiling count, under-sizing every base order (often flooring it to the exchange minimum) even though only a few deals could actually open. They now divide by the same effective ceiling the engine uses to gate new deals — matching the long-only path. Long-only bots were already correct.

## [v2.167.10] - 2026-06-12

### Fixed
- **Bot editor's "Current effective ceiling" now matches the bots page and the trading engine.** The editor recomputed the soft ceiling with its own copy of the formula, which divided by the per-deal cost before the exchange minimum had loaded — yielding a divide-by-zero that silently defaulted the ceiling to your configured maximum (e.g. showing "20" when the real cap was 1). It now uses the same shared calculation as the bots-page badge, falls back to the backend's authoritative value when the live estimate isn't ready, and shows "calculating…" instead of a wrong number.
- **Auto-calculated base order in the editor now matches actual deal sizes.** The same divide-by-zero made the editor split your budget across the configured max deals (e.g. 20) and floor the base order to the exchange minimum (showing "$1"), while the engine correctly split by the real soft ceiling (giving, e.g., "$1.83"). The editor now sizes orders against the same effective ceiling the engine uses.

### Changed
- The soft-ceiling helper now reports "not computable" (rather than a misleading number) when the exchange minimum is unavailable, so callers fall back to the authoritative backend value.

## [v2.167.9] - 2026-06-12

### Fixed
- **Bot budgets and soft ceilings no longer count other accounts' positions.** A bot's budget base (and therefore its DCA order sizes and soft-ceiling deal cap) is now calculated strictly from its own account's balance and open positions. Previously the market-budget calculation ran unscoped — summing the value of every position in the matching quote currency across *all* of your accounts (including paper accounts) and even other users — which could inflate a small account's budget enormously and let the soft ceiling allow far more concurrent deals than the account could fund. Budgets and ceilings now reflect reality.
- **Account budget views show the selected account.** The bots page and the "add funds" dialog now request budget figures for the specific account being viewed, instead of always showing the first connected exchange account. Multi-account users (and anyone viewing a paper-account bot) now see the correct per-account numbers.
- **Incomplete-candle aggregation test corrected.** A stale test was updated to match the shipped behavior where the still-forming final candle is kept and flagged as partial rather than dropped.

### Security
- **Per-account isolation for budget and balance calculations.** Exchange clients are now always scoped to a single account, and the aggregate-value endpoint authorizes account ownership before returning data. This closes a path where one account's (or user's) position values could bleed into another's budget math, and adds a loud warning if any future code path requests an unscoped calculation.

## [v2.167.8] - 2026-06-12

### Fixed
- **USD-equivalent stable valuation pairs no longer hit Coinbase tickers.** `USDC-USD`, `USDT-USD`, and other USD-pegged stable-to-stable valuation pairs now resolve locally to `1.0` in both authenticated and public Coinbase price helpers, preventing noisy ticker 404s while preserving USDC/USDT as separate quote-currency budget buckets.

## [v2.167.7] - 2026-06-12

### Fixed
- **Aggregate USD valuation no longer calls tickers for delisted products.** Whole-portfolio USD valuation now checks Coinbase's cached product catalog before pricing nonzero alt balances, uses catalog prices when available, and skips missing `{currency}-USD` products instead of generating ticker 404s for delisted assets.

## [v2.167.6] - 2026-06-12

### Fixed
- **Bot soft-ceiling displays now use the same quote-currency bucket as trading execution.** The account aggregate API now exposes a dynamic `market_values` map for Coinbase quote buckets discovered from the product catalog, and the bot UI uses the selected quote's bucket for soft-ceiling fallback math. USD, BTC, ETH, USDC, USDT, EUR, and any other Coinbase-supported quote market are treated as distinct deployable buckets instead of folding stablecoin markets into whole-account USD.
- **Soft-ceiling enablement now reads from a compatibility helper.** Runtime paths share one helper for the soft-ceiling flag so persisted effective caps are computed consistently across signal and batch flows.

## [v2.167.5] - 2026-06-12

### Fixed
- **Soft-ceiling enforcement now matches the GUI for percentage-budget bots.** The execution path now calculates soft ceiling from the real aggregate quote balance instead of `0`, and batch analysis splits budgets by the effective soft ceiling rather than the raw configured max deals. This fixes bots showing `1 / 2 (SC: Max 20)` while the backend still blocked second deals as if the ceiling were `1`.

## [v2.167.4] - 2026-06-12

### Fixed
- **The delisted-pair pruning job now cleans normalized bot pairs too.** Bots using the `bot_products` junction table now have delisted pairs removed from that table, not only from legacy JSON `product_ids`, so the startup/manual cleanup job matches the scanner's active pair source.

## [v2.167.3] - 2026-06-12

### Fixed
- **Configured delisted pairs are skipped before candle scans.** The multi-bot monitor now filters configured trading pairs through the cached Coinbase product list before pair processing, while still preserving pairs that have open positions so they can be managed or exited. The daily pair-pruning job also runs shortly after startup.
- **Bug-created sub-minimum failed orders can be purged from history.** Added a targeted cleanup for failed order-history rows whose error matches `Order size ... is below minimum ...`, leaving successful orders and unrelated failures intact.

## [v2.167.2] - 2026-06-12

### Fixed
- **Bots with legacy JSON trading-pair lists scan their configured pairs again.** Some production bots had their pair list stored in `bots.product_ids` but no `bot_products` junction rows, causing the monitor helper to fall back to `ETH-BTC` and miss new deal opportunities even when the UI showed capacity remaining. The helper now supports both storage formats, with regression coverage.
- **The version badge no longer reports an older tag as an available update.** The backend now checks git ancestry before setting `update_available`, so an untagged commit ahead of the latest tag does not show as "latest tag available." Release checks now verify `CHANGELOG.md`, `docs/architecture/index.json`, and git tags stay aligned.
- **Production runbooks now point at `fedora.local`.** Stale `testbot` and EC2-era commands were replaced with the current `zenithgrid.service` / distrobox production flow.

## [v2.167.1] - 2026-06-12

### Fixed
- **Candle API calls no longer hammer delisted products every cycle.** When Coinbase returns 404 for a product's candles (delisted pairs like WLUNA-USD, USDC-USD, etc.), the result is now negative-cached so subsequent requests skip the API call entirely for the cache TTL. Previously, every 10-second monitor cycle re-fetched candles for ~20 delisted products — wasting hundreds of API calls and slowing the loop.
- **QFL base_timeframe now correctly extracted in all code paths.** The `base_timeframe` key (used by QFL's multi-timeframe mode to fetch the ONE_HOUR base candle) was missing from the `indicators` dict loop in `get_timeframes_for_phases` and `calculate_bot_check_interval`. Bots using the `indicators` config format could miss base candles the same way the conditions-format path did before v2.167.0.
- **`aggregate_candles` no longer drops the most recent (forming) candle.** When aggregating smaller candles into larger timeframes (e.g., 3x ONE_MINUTE → ONE THREE_MINUTE), a trailing partial group was silently discarded. This meant the current forming candle — the most price-relevant one — was invisible to strategies. Partial groups are now included and marked with `_partial=True` so strategies can decide whether to use them.
- **Refresh token expiry message now says "Refresh token expired" instead of generic "Invalid or expired token".** Previously, when a user's refresh token expired, the API returned the same vague error as an invalid access token, making users think their session was broken rather than just needing to re-login.
- **Panic sell now clears rebalancer gate state when disabling rebalancing.** The panic sell flow sets `rebalance_enabled = False` but was missing the in-memory cache invalidation that the normal settings endpoint does (added in v2.167.0). Bots could remain stuck with a "Rebalancer paused" badge after a panic sell until the backend restarted.
- **Concurrent pair tasks can no longer exceed max_concurrent_deals.** When a bot was below its max-deal capacity, multiple pair tasks running concurrently shared a stale `open_positions_count` snapshot, allowing them to collectively open more positions than the configured limit. A per-bot lock now serializes the position-count check so each task sees the updated count.
- **Budget re-validated at order execution to prevent overspend.** The quote balance computed during budget calculation could be stale by the time the order hits the exchange (another concurrent pair task may have consumed part of it). Available balance is now re-checked just before order placement.
- **Position re-fetched before sell decision to prevent double-sells.** A position fetched at the start of signal processing could be closed by a concurrent task or limit order fill before the sell decision runs. The position is now re-fetched from the DB immediately before executing a sell, and the AI failsafe path does the same.
- **USD↔USDC two-leg rebalance now attempts rollback on partial failure.** The USD→USDC and USDC→USD conversions execute as two separate market orders (via BTC as intermediary). If the second leg fails, the first leg is now reversed to restore the original portfolio allocation instead of leaving the account in an intermediate state.
- **Silent exception swallowing replaced with logged warnings.** Several error handlers that silently discarded exceptions (`except Exception: pass`, bare `return None`) now log warnings with stack traces so failures in AI review provider queries, BTC/USD price lookups, and OG meta fetching are visible in logs.
- **Monitor loop errors now preserve stack traces.** Five background monitor loops (limit order, order reconciliation, missing order detector, startup reconciliation, PropGuard) were logging errors without `exc_info=True`, making root-cause diagnosis impossible. All now include full tracebacks.

## [v2.167.0] - 2026-06-11

### Fixed
- **Turning off portfolio rebalancing no longer leaves bots stuck "Rebalancer paused".** When you disable rebalancing on an account, the account's in-memory rebalancer gate cache is now invalidated and any bots currently in the gate/overweight sets are released, so they resume normal trading on the next monitor cycle. Previously, a stale 6-hour cache could keep showing the "Rebalancer paused" badge on bots that should have been un-paused, with a backend restart being the only way to clear it.

## [v2.166.19] - 2026-06-10

### Fixed
- **Fresh installs work on Python 3.13/3.14 again.** The pinned dependency versions (FastAPI, pydantic, uvicorn) had fallen behind what production actually runs; the old pydantic pin had no prebuilt packages for newer Python versions, so a fresh `pip install -r requirements.txt` failed trying to compile from source. Pins now match the production-proven versions (fastapi 0.136.3, pydantic 2.13.4, pydantic-settings 2.14.1, uvicorn 0.49.0), verified with a clean install and full test run on Python 3.14.

### Changed
- Test suite stays at zero warnings on Python 3.14 as well (replaced a deprecated asyncio helper in two tests; added the `httpx2` test dependency that newer Starlette's test client prefers).

## [v2.166.18] - 2026-06-10

### Fixed
- **Blank white screen after an update (seen on mobile).** The app's HTML page was served without cache headers, so browsers could keep a stale copy that pointed at JavaScript files deleted by the next deploy — the app then failed to boot. The HTML is now always revalidated (`no-cache`), and the versioned JavaScript/CSS files are cached as immutable for a year, which also makes repeat visits faster. If you currently see a blank screen, one hard refresh fixes it permanently.
- **News article dates from non-UTC feeds are now read correctly.** Published timestamps like `14:30+05:00` had their timezone stripped instead of converted, shifting them by up to several hours — which could prune fresh articles or keep stale ones.

### Changed
- **Test suite now runs with zero warnings** (down from 129): the backend migrated from FastAPI's deprecated `on_event` startup/shutdown hooks to the lifespan API, a deprecated SQLAlchemy union query pattern was modernized, dropped fire-and-forget coroutines are now closed properly, and dozens of test mocks were corrected (several were silently patching the wrong target or running real code unintentionally).
- Internal: migration files no longer hack `sys.path` (the migration runner provides the import path since v2.166.13).

### Security
- Upgraded `python-jose` (JWT library) from 3.3.0 to 3.5.0, picking up the fixes for CVE-2024-33663 and CVE-2024-33664.

## [v2.166.17] - 2026-06-10

### Fixed
- **The backend test suite now passes in a bare environment** — a fresh checkout with no Redis server, no `.env`, and no local secrets runs `pytest tests/` fully green, in any timezone:
  - The Redis integration test now skips cleanly (with a reason) when no Redis server is reachable, instead of failing.
  - The encrypted-credential masking test generates an ephemeral key instead of requiring `ENCRYPTION_KEY` in `.env`.
  - Seven tests that called `asyncio.get_event_loop()` (deprecated, and broken under newer pytest-asyncio) now use `asyncio.run()`.
  - Tests that built timestamps with local time (`datetime.now()`) or converted naive UTC datetimes with `.timestamp()` were timezone-dependent — they failed on any machine not set to UTC. They now build timestamps in UTC, matching the code under test.

### Added
- The `redis` Python package is now declared in `requirements.txt` — the backend imports it at runtime (rate limiting, broadcasts), but fresh installs previously had to install it by hand.

## [v2.166.16] - 2026-06-10

### Changed
- **Pages load faster: the charting library now loads only when you open a chart.** The Portfolio, Positions, and Charts pages no longer download and parse the charting engine up front — it is fetched the first time a chart actually appears (opening an asset chart, expanding a position, or landing on the Charts page). The Portfolio holdings table and the positions list now render without waiting for it.
- **The open-positions list stays smooth with 100 positions per page.** The list is now virtualized, so only the position cards on screen are rendered instead of all 100 at once — scrolling no longer lags on large pages. Grouping headers, card expansion, charts, notes, and pagination all work exactly as before.

## [v2.166.15] - 2026-06-10

### Changed
- Internal: replaced the deprecated `datetime.utcnow()` / `datetime.utcfromtimestamp()` calls throughout the backend with a small naive-UTC helper, clearing ~970 Python deprecation warnings from the test suite. Behavior is unchanged — timestamps are computed exactly as before — this just future-proofs the code against Python removing those APIs.

## [v2.166.14] - 2026-06-10

### Fixed
- **Stopping or restarting ZenithGrid now only ever touches ZenithGrid.** The previous release's clean-restart fix matched its shutdown signal too broadly, so on a server hosting several apps it could also signal another app's process. The shutdown now targets ZenithGrid's own listener (port 8100) specifically, leaving every other app on the host untouched.

## [v2.166.13] - 2026-06-10

### Fixed
- **Your accounts screens keep working even if bot records can't be read.** If the database's bot table becomes temporarily unreadable (for example during a storage-corruption event), the Accounts list and detail pages now still load and simply show a bot count of zero, instead of failing the whole page with an error.
- **Database migrations now apply correctly on PostgreSQL installs.** The migration runner was missing the PostgreSQL driver and didn't make migrations importable or point them at the right schema, so newer migrations could silently fail to apply on PostgreSQL. They now run correctly.
- **The backend service restarts cleanly.** On the containerized production host, stopping the service used to leave the old process holding its network port, so the next start crash-looped with "address already in use." The service now shuts its in-container process down on stop, so restarts and upgrades come up correctly the first time.

### Added
- PostgreSQL drivers (asyncpg, psycopg2) are now declared as project dependencies, so fresh installs on PostgreSQL work without installing those packages by hand.

## [v2.166.12] - 2026-06-10

### Changed
- **Performance pass across the platform — fewer API calls, faster pages.** Every change either reduces or leaves unchanged the number of requests to Coinbase and other third parties; nothing new bursts against exchange rate limits.
  - **Trading engine**: identical candle requests made at the same time now share one exchange call instead of each hitting the API; the seven chart timeframes per pair are fetched in parallel (capped at three in flight) instead of one after another; the limit-order checker connects once per account instead of once per position.
  - **Database**: added indexes for the position-detail and pending-order lookups that run constantly (pending-order lookups previously scanned the whole table), and several screens now ask the database for exactly what they need instead of loading every row — most visibly the AI cost summary, which no longer loads every logged AI call to add up totals.
  - **Web app**: the Portfolio, Bots, and Charts pages now share one portfolio refresh instead of each polling separately; invitation checks ride the existing real-time push with only a slow safety-net poll (previously every user polled every 60 seconds plus on every tab focus, forever); Dashboard widgets refresh on staggered timers so returning to the tab no longer fires five requests at once.

## [v2.166.11] - 2026-06-10

### Fixed
- **Corruption recovery now actually keeps the monitor cycle alive** — when a database read failed due to a bad storage block, the recovery path left the database transaction in an aborted state, so the very next read in the same cycle failed anyway and the whole cycle was lost. The transaction is now rolled back after a corruption error, so the remaining reads in the cycle (and your other bots) genuinely keep working.
- **Startup order reconciliation no longer logs a duplicate error during storage corruption** — a corruption event during the startup pass now produces the single concise warning it was supposed to, instead of also emitting the full startup error line.
- **Fewer false corruption alarms** — file-permission problems and missing database files are no longer mistaken for storage corruption; they surface immediately as real errors instead of being silently retried, so genuine misconfiguration gets noticed right away.

## [v2.166.10] - 2026-06-06

### Fixed
- **Trading keeps running through database storage corruption** — if the database develops a bad block, the background monitor loops now skip only the affected read and keep managing your other bots and open positions, instead of stalling the whole cycle. During such an event the logs show a single clear warning per cycle rather than a flood of repeated error tracebacks. Genuine (non-corruption) database errors still surface immediately.

### Changed
- Internal housekeeping: finished migrating leftover hardcoded host paths to the current production environment. No user-facing change.

## [v2.166.9] - 2026-04-24

### Fixed
- **Frontend test suite: 339 pre-existing `localStorage` failures resolved** — `jsdom@28` ships `window.localStorage` / `sessionStorage` as empty plain objects rather than `Storage` instances, so any test that called `localStorage.clear()` / `getItem()` / `setItem()` crashed with `TypeError: ... is not a function`. Added an in-memory Web Storage polyfill in `src/test/setup.ts` that installs real `getItem` / `setItem` / `removeItem` / `clear` / `key` / `length` when jsdom's slot is missing them. Suite goes from 2326 passed / 339 failed → **2669 passed / 0 failed (108 files)**. No product code touched.

## [v2.166.8] - 2026-04-24

### Changed
- **PWA icons updated to front-view neon truck** — swapped the tab/home-screen icons (16/32/180/192/512) to a dedicated square front-view of the neon truck with glowing headlights. Much more recognizable at small favicon sizes than the previous three-quarter view cropped from the login hero.

## [v2.166.7] - 2026-04-24

### Added
- **PWA icon + home-screen support** — neon truck icons (16/32/180/192/512) cropped from the login hero image, plus `site.webmanifest`, `apple-touch-icon`, and theme color so the app installs with a branded Zenith Grid icon on iOS and Android.

### Changed
- **Initial `<title>` is "Zenith Grid"** instead of the generic "Trading Platform" for a cleaner pre-load tab label. The brand-driven runtime title (`${shortName} - ${tagline}`) continues to override it once `BrandContext` resolves.

## [v2.166.6] - 2026-04-23

### Security
- **Order book endpoint no longer borrows other users' API credentials** — The `/api/orderbook/{product_id}` endpoint had a last-resort fallback that would grab any active CEX account in the system when the caller had no CEX account of their own. Even though the order-book data is public, this consumed the unrelated user's Coinbase API rate budget for strangers' requests. The fallback is removed — users without their own CEX account now get a 503 with a clear message to add one in Settings.

### Fixed
- **Bot-log endpoints no longer hide owner-bots when the user has shared accounts** — The bot access filter on AI logs, scanner logs, and indicator logs routers used a ternary (`Bot.account_id.in_(account_ids) if account_ids else Bot.user_id == current_user.id`) that silently excluded bots the user OWNS but which have no `account_id` set once the user accepted any shared-account invitation. Switched to `or_(Bot.user_id == current_user.id, Bot.account_id.in_(account_ids))` across all five affected sites. Not a security issue (over-restricted, never granted extra access), but a visible UX bug for users with both owned and shared bots.
- **Cumulative-profit chart query now correctly filters closed positions** — `Position.closed_at is not None` was Python `is not`, evaluating to `True` at query-build time (the Column object's identity) and never reaching SQL. Same for `Position.profit_usd`. Replaced with `.isnot(None)` so the filters actually apply. No security impact — the separate `account_id` filter still scopes correctly — but the PnL chart was pulling unclosed rows that happened to have `status = 'closed'` flipped without a `closed_at` or `profit_usd`.

## [v2.166.5] - 2026-04-23

### Security
- **Shared-account managers' order actions now correctly route to the owner's broker** — Four position-mutating endpoints (`limit-close`, `cancel-limit-close`, `update-limit-close`, `add-funds`) were using a FastAPI dependency that built a Coinbase client from the **caller's** default CEX account, even when the caller was a shared-account manager acting on a position that lives on someone else's account. The result was cross-account mis-routing: a manager clicking "close limit order" on your position would place the sell against **their** broker (selling their ETH); clicking "add funds" would spend **their** USD while the PnL accrued on your position. All four endpoints now resolve the exchange client from `position.account_id` instead, matching the pattern already used correctly in `force_close_position` and `sell_all_positions`. The `slippage-check` endpoint was also moved over for consistency since it reads ticker prices from the same broker. Regression tests pin the fix: the exchange resolver must be called with the position's account_id, not the caller's id, otherwise the vulnerability is re-introduced.

## [v2.166.4] - 2026-04-23

### Changed
- **Bots-list endpoint ~6x faster on cold cache** — `GET /api/bots/` was spending up to 18s on the first request every 5 minutes pricing each of the user's ~75 position products one-by-one through an authenticated ticker endpoint that has a 150ms global rate-limit lock. Now uses a single cached (1-hour TTL) public bulk-product fetch that returns all ~600 Coinbase product prices at once, falling back to the per-product path only for products the bulk response didn't cover (delisted, bulk endpoint failure). Cold-path wall clock measured 18.0s → 3.2s in production. Same fix also benefits `calculate_market_budget` (aggregate BTC/USD budget values), which propagates to every caller of that function — trading signal processor, bot validation, account snapshots, bull-flag processor, batch analyzer.

## [v2.166.3] - 2026-04-23

### Changed
- **Auto-calibration test coverage tightened** — internal test sweep found five previously-unexercised branches in the code shipped in v2.166.0–v2.166.2: the DB-exception fallback path in the per-user weights cache (trading keeps working when a query fails), the SQLite JSON-string parse branch (values coerced back to int), the apply endpoint's token-sub-mismatch rejection (forged token with wrong subject), the integer-rounding shave-down path, and the tuner's public-API ValueError propagation on impossible clamp constraints. No behavior changes — just more confident that regressions stay caught.

## [v2.166.2] - 2026-04-23

### Changed
- **Proposal status values consolidated** — the five status strings (`pending`, `applied`, `rejected`, `superseded`, `reverted`) are now defined once in a `ProposalStatus` class in the models module and imported everywhere, replacing ~10 scattered hardcoded string literals. A typo at any call site would have been silent before.
- **Calibration email link TTL now has one source of truth** — dismiss-token and apply-token modules both derive their 30-day TTL from a single `CALIBRATION_EMAIL_LINK_TTL_DAYS` constant, so they can no longer drift apart on a future tweak.
- **Proposals-list row cap pulled to a named constant** — the implicit 200-row ceiling on the history endpoint now lives as `_MAX_PROPOSAL_HISTORY_ROWS`. No behavior change.

## [v2.166.1] - 2026-04-23

### Fixed
- **Weight proposals list now scopes to the requested account** — `GET /api/accounts/{id}/speculative-weights/proposals` was filtering only by `user_id`, so users with multiple speculative-hosting accounts saw a merged list regardless of which account they queried. Now correctly filters by `account_id` too. Same-user only, so not a privacy leak — but confusing UX in the Settings → Weight Calibration History panel. Also switched the endpoint's auth from `get_current_user` to `require_permission(Perm.ACCOUNTS_READ)` for parity with the other account endpoints.

## [v2.166.0] - 2026-04-23

### Added
- **Auto-calibration pipeline for speculative scorer weights (Phase 1 — proposal mode)** — The Phase F calibration email that previously said "open Claude and paste this prompt" now ALSO runs a built-in tuner and appends a one-click "Apply proposed weights" link alongside the existing Claude block. The tuner (proportional-to-alpha algorithm) looks at per-component win rates, nudges high performers up and low performers down, respects floor/ceiling and a ±5 per-cycle change cap, and produces a new weights dict that always sums to 100. Kicks in once you've accumulated ≥500 closed speculative positions — below that, only the standard email with the Claude prompt fires.
- **Per-user scorer weights with full history** — New `trading.speculative_weights_proposals` table stores every proposal + its state machine (`pending` → `applied` / `rejected` / `superseded`). The scorer now resolves each user's effective weights from the latest `applied` row, falling back to the built-in defaults when none exists. Applied proposals take effect on the next AI evaluation (60-second cache, invalidated immediately on apply). One user's tuning never bleeds into another's.
- **One-click apply endpoint + dismiss flow** — `POST /api/accounts/{id}/speculative-weights/apply-proposal` behind a short-lived JWT (30-day TTL, scoped to user_id + account_id + proposal_id). Clicking the email link lands on Settings, the page transparently POSTs the token, shows a success/failure toast, and scrubs the URL so a reload can't double-apply.
- **Weight calibration history in Settings** — The Speculative Bucket card now renders a compact proposal history per account: status badges (applied / pending / superseded / reverted), the per-component deltas of each change (+3 volume_surge, −3 correlation_break, etc.), sample size, and date. Hidden on accounts with no history yet.

### Changed
- **`speculative_signals.WEIGHTS` renamed to `DEFAULT_WEIGHTS`** — The module constant now signals "these are the defaults used when a user has no applied proposal". A back-compat `WEIGHTS` alias stays in place so any external consumers still work. `score_speculative_setup()` gained an optional `weights` kwarg; existing callers behave identically.

## [v2.165.4] - 2026-04-22

### Fixed
- **Speculative sample + template: use ai_buy instead of ai_opinion** — Copying the Speculative Catalyst Hunter sample (or loading the DB template) filled the form with an `ai_opinion` / `"buy"` condition. The condition-builder widget renders the value into a number input, so the string `"buy"` triggered a browser "cannot be parsed, or is out of range" warning loop. Both the sample and the DB template now use `ai_buy` with numeric value `1`, matching the existing AI-Autonomous sample's convention.

## [v2.165.3] - 2026-04-22

### Added
- **Speculative Catalyst Hunter (USD) sample bot** — The "Sample Bots" section on the Bots page (the bots users see front-and-center, before clicking Create Bot) now includes a ready-to-copy speculative catalyst hunter alongside BB-Recovery, RSI-Runner, AI-Autonomous, and MACD. Click Copy to pre-fill the Create Bot form with the full catalyst-hunt configuration: AI entry across all USD pairs, 2x target in 24h, tight stop-loss, trailing take-profit, 24h max-hold, and the `is_speculative` bucket tag. Still requires a non-zero Speculative Allocation on the target account (Settings → Speculative Bucket) before save.

## [v2.165.2] - 2026-04-22

### Added
- **"Speculative Catalyst Hunter" starter template** — A new built-in default bot template for the speculative preset. Pick it from the template list in the "+ Add Bot" modal to copy a ready-made high-risk catalyst-hunter bot: `indicator_based` strategy with an AI-opinion buy condition, `ai_risk_preset: "speculative"` set, and a 1% base-order size. The preset-defaults merger fills in the tight stop-loss, trailing take-profit, 24h max-hold, and catalyst-mode prefilter on create. You still need a non-zero Speculative Allocation on the target account (Settings → Speculative Bucket) before the bot can open positions.
- **`/api/templates/seed-defaults` adds only missing defaults** — Instances that already seeded the older three-template set (Conservative/Balanced/Aggressive DCA) can now re-run seed-defaults to pick up the new Speculative Catalyst Hunter without duplicating the existing three. Previously the endpoint was all-or-nothing and would no-op on any pre-existing defaults.

## [v2.165.1] - 2026-04-22

### Added
- **Speculative Bucket card warns when rebalance floor is too low** — If Portfolio Rebalancing is enabled on an account and its `min_balance_usd` floor is less than 2× the speculative per-slot budget, the Dashboard bucket card now shows an amber "Rebalance USD floor is $X but per-slot budget is $Y — raise min_balance_usd to at least $Z" warning. This catches the case where the rebalancer would silently drain free cash out from under the speculative bot between entries, even though the bucket still shows headroom.

### Fixed
- **Bot form hides the Speculative preset UI when the strategy can't honor it** — The "+ Add Bot" modal was rendering the Risk Preset panel for every strategy type, which misled users into thinking Grid Trading or Arbitrage bots could be made speculative. In practice only `indicator_based` bots get the full package (bucket cap + catalyst-mode AI prompt + time-based forced exit), so the panel is now hidden on other strategies. Picking Speculative on an unsupported strategy no longer wedges the save button either — blocking state is cleared when the panel is hidden.

## [v2.165.0] - 2026-04-22

### Added
- **Speculative preset for catalyst-hunt trading** — A new "speculative" risk preset turns an AI bot into a 2x-in-24h catalyst hunter on microcap and midcap pairs. Picking it from the bot form's Risk Preset dropdown automatically fills in a tight stop-loss, trailing take-profit, a 24-hour max-hold timer, and a prefilter that welcomes already-up setups while still blocking crashers and too-late entries. The LLM is also switched into catalyst mode: its question becomes "is this likely to double?" and it's asked to return a 0-100 doubling-probability score alongside the usual signal.
- **Account-level speculative bucket with a hard cap** — Each account now has a Speculative Allocation setting (0-100% of portfolio USD) in Settings. All bots tagged with the speculative preset on that account share that pool; once committed cost-basis fills the bucket, new speculative entries are blocked until something closes. Winners do NOT expand headroom — cost-basis accounting keeps the "5% of portfolio" promise honest. A new Dashboard card shows bucket usage, available headroom, and the separate realized PnL from speculative closed positions.
- **Speculative signal breakdown on the AI reasoning view** — When the bot ran in catalyst mode, the Position AI Reasoning expander now surfaces the LLM's doubling-probability score plus a per-component fire breakdown (volume surge, compression breakout, momentum acceleration, micro/mid cap, correlation break, volume-vs-marketcap) so you can see exactly which signals scored the entry.
- **Calibration alert when real outcomes diverge from the initial weights** — A background monitor watches closed speculative positions and, once 50+ have accumulated and component win rates meaningfully diverge, emails the account owner a report plus a copy-paste prompt that a fresh Claude Code session can act on to re-tune the signal weights. You'll also see an in-app toast. The email has a one-click "dismiss" link that silences the alert for another 30 days.
- **Bracket exit discipline** — Indicator-based bots now honor a `speculative_max_hold_hours` setting: if a speculative deal doesn't pay off in time, it force-exits so the bucket slot releases on schedule instead of turning into a long-term bag.

### Changed
- **AI opinion log persists the full speculative scorer breakdown** — Every speculative-mode AI evaluation now records its doubling-probability score and per-component fire list alongside the usual signal/confidence/tool-call audit. This is what makes the calibration alert's per-component win-rate analysis possible.

## [v2.164.13] - 2026-04-22

### Changed
- **Open deals rows shed a few more fields the live list never reads** — The hot `GET /api/positions?status=open` path now omits several optional values that matter for detail or closed-position views but not for the active-deals list: `account_id`, `user_attempt_number`, close/profit-at-close fields, and `limit_close_order_id`. That trims each row a bit further on the 5-second open-deals refresh without changing the open positions UI.
- **Closed and detail views keep their full data** — The trimming only applies to the open positions list route. Closed/history views and single-position detail fetches still return those fields where they’re actually used.

## [v2.164.12] - 2026-04-22

### Changed
- **Open positions list stops carrying the full frozen strategy config on every poll** — The hot `GET /api/positions` list route now trims each row’s `strategy_config_snapshot` down to just the keys the open-positions UI actually reads for its cards and list-level affordances. That reduces per-row payload size on the 5-second open-deals refresh without changing the card behavior.
- **Full strategy snapshots still come back when a single deal is fetched** — `GET /api/positions/{id}` still returns the complete frozen strategy config, so chart, modal, and edit flows keep full-fidelity position detail when they need it. The optimization only applies to the list route.

## [v2.164.11] - 2026-04-22

### Changed
- **Open positions refreshes keep more of their backend work on the list-safe path** — The hot `GET /api/positions` list now reuses the aggregated first-buy quote amount when it needs to compute resize-budget hints for snapshot-less positions, instead of needing a trade-backed fallback path. That keeps the 5-second open-deals polling route leaner while preserving the “Resize budget” affordance on affected deals.
- **Active limit-close rows stop expanding fill-by-fill history on every poll** — The Positions list only shows summary limit-close status such as price and fill percentage, so the hot list endpoint no longer JSON-parses and serializes the full `fills[]` history for those rows. The response keeps the summary fields the card view actually uses and drops avoidable per-poll payload and CPU work.

## [v2.164.10] - 2026-04-22

### Changed
- **Open positions polling now spends its hottest refresh budget only where it matters** — The Positions page now polls open deals adaptively: active deals stay on a 5-second cadence, but accounts with no open positions back off to 30 seconds. Bot metadata on that page is no longer kept on its own 10-second polling loop, and the `/prices/batch` refresh is now driven by React Query instead of a separate manual timer. The page also slowed its secondary summary widgets (completed stats, realized PnL, balances) to a 2-minute cadence and only polls the currently visible tab on the Closed Positions page.
- **Each `GET /api/positions` refresh does less backend work** — The hot list endpoint no longer hydrates every position’s full `trades` and `pending_orders` collections just to build the list view. It now uses aggregate queries for trade counts, first/last buy prices, and pending-order counts, and only looks up the specific limit-close orders needed for rows that are actively closing via limit. The route also scopes blacklist lookups to just the symbols on the current page and only loads bot configs for positions that cannot compute resize budgets from their frozen strategy snapshot alone.

## [v2.164.9] - 2026-04-22

### Changed
- **Account-scoped bot views stop overfetching cross-account data** — The Dashboard, Closed Positions page, and open positions hook were still loading the full bot list and filtering it client-side when an account was selected. `GET /api/bots/` now accepts `account_id`, verifies that the caller can access that account, and returns only the relevant bots. Those frontend views now pass the selected account through, which trims response payloads and removes a chunk of wasted work on account-specific screens.
- **Positions page stops background batch-price polling in hidden tabs** — Even after the React Query polling cleanup in `v2.164.8`, the positions page still had a manual `setInterval(..., 5000)` loop for `/prices/batch` that kept running while the tab was hidden. That custom price-refresh loop now pauses when the document is hidden, cutting unnecessary frontend and backend churn when users switch away from the tab.

## [v2.164.8] - 2026-04-22

### Changed
- **Dashboard first paint is lighter after the Account Value fast-path work** — The Dashboard still kicked off a burst of non-critical requests on mount even after v2.164.6 fixed the slow account-value summary path. Reservations, transfer summary, PropGuard status, and per-bot stats are now deferred for 2 seconds after first paint, so the initial render can show the core totals, bot list, and deal counts sooner. Open and closed position summary queries are also now scoped by `account_id` at the API call instead of fetching broader result sets and filtering in the browser, and those polling queries stop while the tab is hidden.
- **Market price fetch policy is now shared instead of duplicated** — BTC/USD and ETH/USD price fetches were being managed independently in multiple places (`App`, `ClosedPositions`, positions hooks), which made polling/staleness behavior easy to drift over time. A shared `useMarketPrice()` hook plus `marketDataApi.getPrice()` helper now centralizes that path so those views reuse the same query behavior and cache shape.
- **Positions batch-price requests stop sending duplicate markets** — When multiple open positions shared the same product, the positions page still sent repeated symbols to `/prices/batch`. The request now deduplicates product IDs first, cutting a little unnecessary payload and backend work on every polling cycle.

## [v2.164.7] - 2026-04-22

### Changed
- **Product precision cache is no longer committed to git** — `backend/app/product_precision.json` auto-grows at runtime whenever the bot encounters a trading pair it hasn't seen before (that's been the case since v2.148.1). The file was still tracked in git, so every new coin showed up as a dirty working tree forever and the `.gitignore` entry for it never did anything on existing clones. The tracked baseline has been moved to `product_precision.seed.json` (read-only snapshot) and the runtime file is now properly untracked. Both loaders prefer the runtime file when present and fall back to the seed, so fresh clones start with precision data instead of an empty dict. No user-visible change — just no more spurious "modified" entries in `git status` after the bot runs.

## [v2.164.6] - 2026-04-22

### Changed
- **Account Value appears almost immediately on first login** — On paper accounts with lots of non-stable assets (the worst case on `testbot` was a paper account with 135 assets taking ~27 seconds on a cold cache), the Dashboard header used to sit on a spinner while the backend valued every holding one by one through Coinbase's public price API — USD lookup first, BTC fallback second, serial, no concurrency cap. The header now calls a new lightweight endpoint, `GET /api/accounts/{id}/account-value-summary`, that returns just `total_usd_value`, `total_btc_value`, and `btc_usd_price`. The summary is cached for 60 seconds, refreshed in the background when stale, and — for paper accounts — built through a shared valuation helper with bounded concurrency (max 5 in-flight price lookups) so we stay friendly to Coinbase rate limits. The Portfolio page still gets full holdings detail on demand via a new `include_details` flag on the portfolio endpoint. Net effect: the header shows a number in well under a second on first login instead of hanging on a cold-cache burst, without trading latency for throttling.
- **Dashboard startup is lighter** — The Dashboard page now code-splits its `AccountValueChart` and `MarketSentimentCards` widgets with `React.lazy` / `Suspense`, so the first render doesn't block on chart libraries it doesn't need yet. Also trims a little redundant work on the live portfolio warm-up path.

## [v2.164.5] - 2026-04-22

### Fixed
- **Positions page no longer spams the browser console with AI-opinion 404s** — The Positions page renders an "AI reasoning" expander for every row, which pre-fetches `GET /api/positions/{id}/ai-opinion` on mount so the widget can hide itself when no tool-use detail exists. For the common case of a freshly opened position with no opinion logged yet, the endpoint was raising `HTTPException(404, "No AI opinion logged for this position")`. The React component already swallowed the error in UI, but browsers still log every 4xx response to the devtools console — opening Positions with 20+ rows produced a wall of red "404 (Not Found)" entries. A missing opinion is a legitimate "no data" case, not a "not found" case. The endpoint now returns `200` with a `null` body when no opinion exists, and only returns `404` for the actual not-found cases (nonexistent position, or a position on an account the caller cannot access). No user-visible change on the page itself; the devtools console just stays quiet.

## [v2.164.4] - 2026-04-22

### Changed
- **Shared-account members can now see bot indicator logs** — `GET /api/bots/{bot_id}/indicator-logs` and `/indicator-logs/summary` previously filtered strictly by `Bot.user_id == current_user.id`, which meant a friend you shared an account with could see the bot and its trades but hit a 404 on the logs explaining *why* each trade fired. Both endpoints now use the same `accessible_account_ids` pattern the scanner-log and AI-log endpoints already use, so any role (owner, manager, shadow) can read the reasoning for bots on accounts they have access to.
- **Bot rebalancer view now reflects the shared account, not just your own bots** — The GET side of `/api/bots/rebalancer` verified account access via `accessible_accounts_filter` (correct) but then re-filtered the bot list by `Bot.user_id == current_user.id`, so a shared member always saw an empty rebalancer page even though the bots existed. The inner filter is removed; the bot list now comes straight from the account. The PUT side remains strictly owner-only since saving rebalancer settings can move real money.
- **Shared-account reports: PDF download opens up; delete stays owner-only** — `GET /api/reports/{report_id}/pdf` previously required `Report.user_id == current_user.id`, blocking managers and observers of a shared account from downloading the PDF of a report they could already read on the web. It now goes through the same `_get_accessible_report` helper the `get_report` endpoint uses, so any member with read access to the owning account can download. `DELETE /api/reports/{report_id}` and the bulk-delete endpoint remain owner-only — report deletion is irreversible and there's no undo.

### Security
- **`list_members` redacts peer emails for non-owners** — `GET /api/accounts/{id}/sharing/members` previously returned every other member's full email address to anyone with at least shadow access. If an owner shared one account with three friends, each friend got the other two's emails as a side-effect of opening the sharing panel. The service now takes the caller's account role; only the account owner sees the raw `email` field. For non-owner callers, `email` is null and `invited_by` falls back to the inviter's display_name rather than their email. Display name alone is enough to identify who's on the account without leaking a contact address.

## [v2.164.3] - 2026-04-22

### Changed
- **Portfolio calculations deduplicated** — `portfolio_calculations.py` previously carried four near-identical helpers that shadowed four others: `_process_cex_holdings` (shadow of `_build_portfolio_holdings` without bot-held-position tracking), `_apply_unrealized_pnl` (shadow of `_compute_position_pnl` + the inline apply loop), `_calculate_balance_breakdown` (positional-arg shadow of the `BalanceBreakdownParams`-dataclass `_compute_balance_breakdown`), and `_calculate_realized_pnl` (dict-shaped shadow of the tuple-returning `_compute_closed_pnl`). The four shadows have been deleted. The aggregated cross-account portfolio view (`get_account_portfolio_data`) now uses the same four canonical helpers as the single-account view (`get_cex_portfolio`) so the two paths stay in lock-step. A tiny behavior improvement comes along for free: the aggregated view now tracks bot-held base-currency amounts when computing each holding's `available` figure (previously it used Coinbase's `available_to_trade_crypto` as-is, which doesn't know about our open bot positions). The inline "apply asset_pnl to holdings" loop that was duplicated in both callers was also factored into `_apply_asset_pnl_to_holdings`. 189 lines of duplicate code removed; 62 portfolio-adjacent tests still pass.

## [v2.164.2] - 2026-04-22

### Changed
- **Accounts routers decoupled: schemas and TTL caches moved to shared modules** — `accounts_mutation_router.py` previously reached across the router layer with `from app.routers.accounts_query_router import AccountCreate, AccountResponse, AccountUpdate, AutoBuySettings, AutoBuySettingsUpdate, DustSweepSettingsUpdate, RebalanceSettingsUpdate, _TTL_REBALANCE_STATUS`, a classic router-imports-from-router anti-pattern that made the two files impossible to reason about independently. The eight Pydantic request/response classes now live in `app/schemas/accounts.py` (joining the existing `schemas/` package alongside `dashboard.py`, `market.py`, `position.py`, and `settings.py`), and the two per-account TTL caches (`_TTL_REBALANCE_STATUS`, `_TTL_DUST_SWEEP`) plus their interval constants now live in `app/services/account_cache.py`. Both routers import from the new shared modules; the cross-router import is gone. Test imports that had been reaching for the schemas via the query router were also retargeted at `app.schemas.accounts`. No behavior change — same endpoints, same responses, same TTLs. 171 affected tests pass.

## [v2.164.1] - 2026-04-22

### Changed
- **Silent exception swallows now log** — Twelve call sites that previously caught an exception and silently continued (bare `except: pass`) now emit a log line with full stack trace via `exc_info=True`. Targets: paper-portfolio coin pricing fall-through (3 sites in `portfolio_service.py` and `account_service.py`, plus the paper-trading client's own BTC/USD fallback), AI provider / broadcast failures (admin friend-notification push, invitation WebSocket push), cleanup paths that can't fail the caller (PIL image close in news-image cache, DB rollback after pair-processor error, ByBit WebSocket shutdown, last-error persistence after sell failure), and malformed-data parsing (content-source website URLs, CoinGecko ATH date). No behavior change — the same fallbacks still fire, but failures are now diagnosable from the logs. Bulk and top-level dust-sweep exceptions were also upgraded from plain `logger.warning(str(e))` to structured `logger.warning(msg, exc_info=True)` so stack traces are captured.

## [v2.164.0] - 2026-04-22

### Security
- **MFA lockout after repeated failures** — The shared `verify_mfa` helper (used by panic-sell, account deletion, account conversion, and anything else that gates on a fresh code) now counts failed attempts per user and returns HTTP 429 after 5 invalid codes within 15 minutes. A successful verification clears the counter, so legitimate users who mistype once are never locked out in practice. Previously an attacker who had session access could brute-force the 6-digit TOTP window indefinitely.
- **Invitation endpoints now rate-limited per user** — Invitation actions are capped by an in-memory sliding-window limiter keyed by user ID (not just IP). Inviting: 10/hr per account owner per specific account and 30/hr total across all an owner's accounts (the global cap is new; the per-account cap existed but ran as a DB query on every call — the new limiter is 0-RTT). Token actions (preview / accept / decline): 30/hr per authenticated user. Legit users never notice; enumeration / spray tooling hits 429 quickly.
- **Invitation-token errors no longer leak token state** — Previously the preview / accept / decline endpoints returned distinct error text for "token does not exist" vs. "already accepted" vs. "already declined" vs. "expired" vs. "invited email does not match your account," which let anyone with one valid-looking token probe for state transitions. All five failures now collapse to a single generic "Invalid or expired invitation." The service layer still raises descriptive errors for internal tests and logging.
- **Perps-portfolio endpoints no longer leak account existence** — `GET /accounts/{id}/perps-portfolio` and `POST /accounts/{id}/link-perps-portfolio` previously responded with 403 "Not authorized" when an authenticated user queried an account they could not access, which disclosed that the account existed. Both endpoints now uniformly return 404 "Account not found" for any inaccessible account ID. The GET endpoint additionally honors account-sharing membership (accessible to owners, managers, and shadows) rather than strict ownership; linking remains owner-only.

### Added
- **`services/user_rate_limit.py`** — Small in-memory per-user sliding-window limiter module. `check_user_rate_limit` counts allowed requests, `record_user_failure` / `clear_user_failures` handle brute-force-sensitive counters, and `prune_stale` returns memory. Drop-in: swap the module-level dict for a Redis store if the deployment ever goes multi-process.

## [v2.163.4] - 2026-04-22

### Changed
- **Code-quality quick-wins batch** — Four trivial cleanups flagged by the post-v2.163.3 audit: (1) the `_accessible_accounts_filter` wrapper in `accounts_query_router.py` was a pass-through to `account_access.accessible_accounts_filter` and has been removed; all eight call sites now use the shared function directly, and a redundant inline import in `get_bots_for_account` was also deleted. (2) `_ACTIVE_MEMBERSHIP = lambda uid: (...)` in `account_access.py` (which required a `# noqa: E731`) was promoted to a proper `def _active_membership_clauses(uid)` with a real docstring. (3) Migration 081's `cost_usd` column default was `DEFAULT 0` on a `DOUBLE PRECISION` / `REAL` column — corrected to `DEFAULT 0.0` to match the column type. (4) `docs/architecture/backend.json` claimed `portfolio_service.py` was 777 LOC after Phase 5; actual was 786 — corrected. No behavior change; all 166 account-related tests pass.

## [v2.163.3] - 2026-04-22

### Changed
- **Coverage gap cleanup for multi_bot_monitor and news_router** — Eleven new tests (four + seven) fill the two paths the prior sweep explicitly deferred. `news_router.get_videos_for_user` now has tests for both the PostgreSQL SQL-retention branch (mocked dialect) and the SQLite Python-side retention fallback, pushing router coverage from 75% to 85%. `multi_bot_monitor.monitor_loop` now has tests for empty bot-list handling, due vs. not-due bot scheduling, first-iteration 5-per-2s staggering, dynamic concurrency adjustment when memory capacity changes, per-bot scheduling errors being contained to that bot, stale cache pruning across indicators/schedule/candles, and outer-exception recovery — lifting monitor coverage from 67% to 82%. No production code was modified.

## [v2.163.2] - 2026-04-22

### Changed
- **Test coverage sweep for five historically-thin modules** — 80 new tests (1,735 lines) added across `multi_bot_monitor.py` (0% → 67% line coverage; 17 new tests covering cache cleanup, active-bot filtering, rebalancer-group logic, status reporting, pair-category filtering, and per-bot processing), `sources_router.py` (→ 96%; 11 new tests covering subscribed-source listing, dedup on custom-source add, and helper utilities), `blacklist_router.py` (→ 98%; 17 new tests covering AI provider settings, single-add, reason updates, blacklist checks, tenant isolation, user-override edge cases, and category settings shape), `accounts_query_router.py` (→ 82%) + `accounts_mutation_router.py` (→ 80%; 13 new tests covering default-account selection, perps portfolio status, and dust-sweep settings/execution — the Phase-5.3 split is now fully exercised), and `news_router.py` (44% → 75%; 22 new tests covering article image serving with path-traversal defense, cache stats/cleanup, video sources/feeds, article content, fallbacks, and DB-backed video retrieval). All 256 tests in these files pass, flake8 is clean, and no production code was modified. Remaining gaps are PostgreSQL-dialect-only SQL paths (not reachable from SQLite tests) and time-dependent asyncio scheduler loops that need a fuller orchestration harness.

## [v2.163.1] - 2026-04-22

### Changed
- **Architecture documentation drift fixes** — Two service modules that were never recorded in `docs/architecture/backend.json` are now listed: `services/account_access.py` (shared multi-user access filter helpers) and `services/account_sharing_service.py` (invitation and membership business logic). Four stale frontend component paths in `docs/architecture/frontend.json` were corrected to reflect their actual locations after Phase 5.4: `DCABudgetConfigForm`, `AdvancedConditionBuilder`, and `AccountValueChart` now point at `components/trading/`, and `BlacklistManager` points at `components/settings/`. No code changes.

## [v2.163.0] - 2026-04-21

### Changed
- **Code-quality sweep Phase 5 — modularization** — Six backend files that exceeded the 1200 LOC cap were split into focused modules, four frontend components followed the same treatment, and long functions inside the grid trading engine were decomposed into named helpers. No behavior change — identical public contracts, same tests, same routes. Backend splits: `database_seeds.py` → `app/seeds/` package, `signal_processor.py` → `app/strategies/signal_processor/` package with buy/sell decision submodules, `expense_builder.py` → three report modules, 470 LOC of pure math extracted from `portfolio_service.py` into `portfolio_calculations.py`, 255 LOC of SVG chart helpers moved out of `html_builder.py` into `html_charts.py`, and `indicator_based.py` helpers split out. Three cross-router private helpers were promoted to proper service modules — `_get_*_goal` / `_report_to_dict` moved from `reports_crud_router.py` to a new `report_access.py`, `_build_rebalance_response` moved from `accounts_query_router.py` to `account_responses.py` (taking its pydantic DTO with it so the service stays self-contained), and `_verify_mfa` moved from `panic_sell_router.py` to a new `auth/mfa_verification.py` and is now shared by the account conversion and account deletion flows. Frontend splits: `ExpenseItemsEditor.tsx` extracted `SortableExpenseRow` plus frequency/date helpers, `Settings.tsx` extracted `ActiveSessions` and `AdminDisplayNameField` plus device/time helpers, `DCABudgetConfigForm.tsx` extracted the DCA ladder calculator and condition normalization, and `PortfolioManagement.tsx` extracted currency/mode constants and cache helpers. All 11 touched files now sit under 1200 LOC. Architecture documentation (`docs/architecture/backend.json` and `frontend.json`) was synced; the long-missing `account_sharing_router.py` entry was also added.

## [v2.162.1] - 2026-04-21

### Changed
- **Code-quality sweep Phase 4 — silent failures now logged, dead code removed** — Six code paths that previously swallowed exceptions with a bare `pass` (perps monitor broadcast, background presence-update JSON parsing, offline presence broadcast, paper-trading USD/BTC price lookups, MFA email attribute parsing, multi-bot-monitor stale-client close) now log at warning/debug with `exc_info=True` so real failures are visible in the logs. Exception catches were also narrowed from bare `except Exception` to the specific errors each branch actually expects. Twelve unused-local and one unused-import site were deleted outright (not just silenced with `# noqa`) across the indicator calculator, bot/template routers, grid services, bull-flag / spatial-arbitrage strategies, the buy/sell executors, and `ai_spot_opinion`. No behavior change; flake8 `F401` + `F841` now reports zero findings under `backend/app/` and `backend/tests/`.
- **Ethereum RPC URL is now configurable via env** — A stray `ETHEREUM_RPC_URL = "https://mainnet.infura.io/v3/"` partial-URL constant in `dex_constants.py` was never read by any caller and was replaced with a proper `ethereum_rpc_url` setting in `config.py`. When set, `DexWalletService` uses it as the chain-1 RPC endpoint in preference to the public-node fallback; when empty (the default), the public RPC continues to be used.

## [v2.162.0] - 2026-04-21

### Added
- **AI usage & cost dashboard** (Settings → AI section) — A new panel summarizes your bots' AI activity over a selectable window (7 / 30 / 90 days) and shows total calls, input/output tokens, and estimated USD cost. Breakdowns are rendered by provider and by model so you can see which Claude / GPT / Gemini model family is driving spend. Scoped to the current user — other users' activity is never visible. Pre-Phase-F rows that predate per-call cost tracking appear under a "(legacy)" model bucket so historical activity stays visible.
- **Per-bot AI model override** — A new "AI Model Override" dropdown on the bot editor lets you pick a specific SDK model ID (e.g. `claude-haiku-4-5` for speed/cost, `gpt-4o-mini` for cheap prefilter, `gemini-1.5-pro` for long context) independently from the provider selector. Leaving it as "(provider default)" preserves the old behavior where the adapter's default model is used.
- **Per-call cost accounting in the audit log** — Every AI spot-opinion call now records `model_used`, `input_tokens`, `output_tokens`, and `cost_usd` on its `ai_opinion_log` row. The cost is computed from a built-in pricing table matched longest-prefix against the provider's reported model string, so dated snapshot IDs resolve to their base family's price. Unknown models fall through to zero cost rather than fabricating a number.

### Changed
- **AI adapters now report token usage** — The Anthropic, OpenAI, and Gemini providers all return a `TokenUsage` record alongside the response text and normalized tool calls. Usage is summed across every turn of a tool-use loop so multi-turn calls bill the complete token count, not just the final turn.

## [v2.161.1] - 2026-04-21

### Changed
- **Auth router test coverage expanded** — Added focused test coverage for four previously under-tested auth modules: `password_router` (forgot-password generic success / repeat-clears-old / reset-bumps-tokens-valid-after / cross-user token isolation), `email_verify_router` (valid token / forged / expired / used / cross-user isolation for both link-click and 6-digit code flows, plus the 3-per-hour resend rate limit), `device_trust_router` (list / revoke / revoke-all with expired-device filtering and cross-user isolation on every path), and `helpers.get_client_ip` + `_create_device_trust`. 33 new tests, all green. Also repaired two pre-existing broken account-member tests that the v2.160.5 goal-create fix had left with unresolved forward-reference imports.

## [v2.161.0] - 2026-04-21

### Security
- **Writes to global settings are now superuser-only** — The "update blacklist categories", "update AI provider setting", "update settings" (bulk), and "update setting by key" endpoints all wrote to the single global `Settings` row. They previously only required the `settings:write` / `blacklist:write` permission, which meant any permitted user could overwrite platform-wide trading configuration, the Coinbase API key, and blacklist taxonomy for every other user on the instance. These endpoints are now gated on superuser status. Non-superusers with the permission receive 403. Reads are unchanged.
- **Template name-uniqueness no longer leaks other users' template names** — Creating or renaming a bot template previously ran a global name-lookup and returned "Template with name 'X' already exists" if ANY user in the system already had one by that name — disclosing the existence of another account's private template. The uniqueness check now only considers the caller's own templates plus the globally-visible default presets. If a cross-user collision still trips the database's legacy unique constraint, a generic "could not be created" error is returned instead of leaking the name.
- **AI API key preview shortened from 8 to 4 plaintext characters** — The last four characters are enough to recognize a key in the Settings UI while minimizing what is shown on screen or in logs if a screenshot is shared.
- **Public market-data endpoints are rate-limited per IP** — Ticker, batch prices, candles, product precision, coin lists, and the BTC/ETH USD price helpers route through the existing `PublicEndpointRateLimiter` middleware (120 requests / 60 seconds / IP). Regression tests were added so the coverage list and the enforcement behavior stay pinned — previously there were none.

## [v2.160.5] - 2026-04-21

### Security
- **`resize_all_budgets` no longer falls through to a global rewrite when the caller has no writable accounts** — A code-quality sweep found that the bulk position-budget endpoint skipped its account filter entirely when a user with the `positions:write` permission had zero writable accounts AND supplied no `account_id` parameter. The query collapsed to `WHERE status = 'open'` across every user on the platform, rewriting `max_quote_allowed` on every open position. The filter is now always applied — empty writable-accounts lists match nothing instead of everything.
- **JWT signing key can no longer silently ship with its public default value in production** — The `jwt_secret_key` setting defaulted to the literal string `"jwt-secret-key-change-in-production"`. If `.env` was missing or the env var was unset, the bot booted with a publicly-known signing key. The config now refuses to instantiate when the default secret is used and `environment=production`, and logs a loud warning in development.

### Fixed
- **Creating a Reports goal no longer crashes with `AttributeError`** — `create_goal` read `body.minimap_threshold_days`, but the `GoalCreate` schema did not declare that field, so any real POST to `/api/reports/goals` raised `AttributeError` before the goal could be persisted. The field is now declared on both `GoalCreate` (default 90) and `GoalUpdate`, and end-to-end create tests pin the round-trip.

## [v2.160.4] - 2026-04-21

### Fixed
- **Canasta hands no longer freeze the browser when the AI cannot meet the initial meld threshold** — The AI's melding loop detected progress via a reference check, but the meld function returns a new state object (with an error message) even on rejected attempts. When the AI held three low-point cards and owed an initial 50-point meld, the loop kept retrying the same rejected meld and never advanced to discard. The loop now measures progress by whether cards actually left the hand.

### Changed
- **Frontend test-suite maintenance (round two)** — Fixed 86 further pre-existing test failures that had been masked by the Canasta engine hang. Covers AuthContext (wrapped renders in `QueryClientProvider` after the provider began reading from React Query), `computeEffectiveAggregateValues` import moved to `components/bots`, user-scoped storage keys in game-state tests, the new `cards` game category, score entries now storing `{score, score_type}` objects, updated `positionsApi` default limit, and corrected mock paths in the accounts management test. Full frontend suite now runs green (2606/2606) in under three minutes.

## [v2.160.3] - 2026-04-21

### Fixed
- **Expense categories dropdown in Reports now loads correctly** — The "Expenses" target editor was showing an empty category list, making it impossible to pick a category when adding or editing an expense item. The `/api/reports/expense-categories` endpoint was being shadowed by the `/api/reports/{report_id}` int-typed catch-all route because the CRUD router was registered before the generation router, so the backend returned a 422 before the intended handler could run. Fixed by reordering router registration so the specific endpoint matches first, and added regression tests that assert the route resolution order.

### Changed
- **Frontend test-suite maintenance** — Fixed 22 pre-existing test failures that had accumulated as games, audio catalogs, and components evolved past their original assertions: PanicSellModal, NotificationContext, songRegistry, sfxRegistry, dinoRunnerEngine, and EuchreEngine test files now pass. Mock paths corrected where the system-under-test import moved, hardcoded game/song counts replaced with dynamic assertions, and Euchre's `ordering up` flow updated to reflect the `goAlonePrompt` phase that now sits between order-up and dealer discard.



### Changed
- **Internal cleanup: frontend ESLint errors zeroed out** — Resolved all 58 remaining ESLint errors across 28 frontend files. Fixes include renaming a shadowed `Infinity` identifier in the games icon map, combining `let` + destructure-and-reassign patterns into `const` destructuring across the card/arcade game engines, replacing deprecated `Function` types with explicit signatures in a chart test, hoisting several `useCallback`s above conditional early returns in multiplayer lobbies (Crazy Eights, Gin Rummy, Go Fish, and the race overlay) to comply with React's rules of hooks, and adding explicit ignore comments to intentional empty catch blocks. No user-facing behavior change.

## [v2.160.1] - 2026-04-21

### Changed
- **Internal cleanup: Pydantic V2 + React hook deps** — Migrated 19 deprecated `class Config:` blocks across 10 schema/router modules to Pydantic V2's `model_config = ConfigDict(...)` form, silencing all Pydantic deprecation warnings on startup. Also fixed a React `exhaustive-deps` warning in the positions filter hook by stabilizing `getGroupKey` with `useCallback`. No user-facing behavior change.

## [v2.160.0] - 2026-04-21

### Added
- **"AI reasoning" expander on position cards** — Every open position that was evaluated with tool use now shows a small collapsible "AI reasoning" row under its notes. Expanding it reveals the AI's signal (buy/sell/hold), its confidence, the model it used, the reasoning text, and the list of tools it called (portfolio, recent prior signals, etc.) with an expandable "what the AI actually saw" summary for each tool. Single-shot evaluations (no tool use) stay hidden to keep the card uncluttered.

### Changed
- **Type cleanup around position P&L cache** — Introduced named types (`CachedPnL`, `PositionWithPnL`, `SlippageCheckResult`) to replace scattered `any` usages in the positions module. No behavior change, but future errors around cached P&L shape will be caught at compile time.

## [v2.159.0] - 2026-04-21

### Added
- **AI analyst now learns from its own track record** — Every time an AI bot decides to buy or sell, its full reasoning (signal, confidence, reasoning, and any tool calls it made) is saved. When the trade eventually closes, the outcome (win/loss/breakeven and realized P&L) is stitched back onto the original opinion. A new tool `get_prior_ai_signals` exposes this history to future evaluations, so the AI can see how its recent calls on the same product have actually played out before giving a new opinion. Logs are kept for 90 days and then pruned automatically.
- **Multi-provider AI tool use** — The AI analyst now supports tool calls across every provider (Anthropic, OpenAI, Gemini, Grok, DeepSeek). A unified provider adapter layer normalizes the tool-call loop so all providers receive the same portfolio + position context and the same set of tools, regardless of their native API shape.
- **Portfolio + position context tools** — AI evaluators can now ask for the user's current portfolio breakdown, open-position status, and recent outcomes as structured tool results instead of fixed prompt text. Tools can take arguments (e.g. lookback window), so the AI pulls only the context it actually needs for each decision.

### Fixed
- **Chat unread-counts query no longer runs for users without chat permission** — The frontend was querying unread counts unconditionally on page load, triggering a noisy 403 for users whose group lacks `social:chat`. The query is now gated on the permission check.


### Fixed
- **WebSocket reconnect no longer spams console errors when the access token is expired** — After a 30-minute session without a page reload, the JWT in the WebSocket URL could expire (e.g. if the browser tab was throttled or the auto-refresh timer fired late). The reconnect now checks token expiry first and silently refreshes it before opening the socket. If the refresh fails the socket is simply not reopened until the user logs back in.

## [v2.158.13] - 2026-04-03

### Added
- **Caps Lock warning on all password fields** — All password inputs (sign-in, sign-up, reset password, and all three fields in the Settings change-password form plus the MFA confirmation fields) now show an amber "⇪ Caps Lock is on" hint whenever Caps Lock is active. The warning disappears automatically when Caps Lock is turned off. The sign-in field suppresses the warning when the "show password" eye toggle is active (since the characters are already visible).

## [v2.158.12] - 2026-04-03

### Changed
- **Settings: Change Password now enforces the same complexity rules as account creation** — The "Change Password" form now shows the password strength meter (4-segment bar + requirements checklist) and requires the new password to meet the same rules: at least 8 characters with uppercase, lowercase, and a number. The submit button stays disabled until all requirements are met.

## [v2.158.11] - 2026-04-03

### Fixed
- **Bots page: 500 error on products for shared/paper accounts** — The `/api/products` endpoint was wrapping its entire body in a broad `try/except` that swallowed the 404 `HTTPException` from the account ownership check and re-raised it as a 500. Fixed by moving the access check outside the try block. Also updated the check to use the `accessible_accounts_filter` so member accounts (including Demo BTC Paper) work correctly.
- **Bots page: 404 on rebalancer for shared accounts** — The rebalancer endpoint (`GET /api/bots/rebalancer`) used a strict owner-only query, rejecting accounts accessible via membership. Updated to use `accessible_accounts_filter` so managers and account members can view the rebalancer state.
- **Bot form: "worst case minimum" always 405** — Frontend was calling `POST /api/bot-validation/get-worst-case-minimum` but the endpoint is mounted at `/api/bots/get-worst-case-minimum`. Fixed the URL in `api.ts`.

## [v2.158.10] - 2026-04-03

### Fixed
- **Dashboard market metric cards no longer show 503 when data sources are unavailable** — All metric endpoints (Fear/Greed, BTC block height, US debt, BTC dominance, altseason index, stablecoin market cap, total market cap, mempool, hash rate, Lightning, ATH, BTC RSI) now fall back to stale cached data if the upstream API is unreachable. Previously any cache miss during an outage returned a 503; now the last known value is served with a warning log, and 503 is only raised if no cache exists at all.
- **US National Debt card: duplicate projected milestone** — When current debt is just below a round trillion that is also a round 5-trillion boundary (e.g. $39.xT → next $1T and next $5T both land at $40T), the second milestone row now advances to the next $10T boundary instead of repeating the same value.

## [v2.158.9] - 2026-04-03

### Fixed
- **README accuracy corrections** — Fixed several stale or incorrect claims: strategy count corrected from 6 to 5 (Bull Flag and AI Spot Opinion are sub-modes of Indicator-Based, not separate strategies; Grid Trading added to the list); indicator card count corrected from "16+" to 14; replaced "Never Sells at a Loss" promise language with accurate "profit-target enforcement" framing; Python version recommendation updated from 3.13 to 3.11+; troubleshooting log command updated from stale `.pids/backend.log` to `journalctl`; Twitter/Reddit "Sentiment Ready" claim clarified as planned rather than implemented.

## [v2.158.8] - 2026-04-03

### Fixed
- **Dashboard sparkline width(-1)/height(-1) warning fully eliminated** — The previous fix deferred chart rendering by two animation frames, but Recharts' `ResponsiveContainer` always initializes its internal state to -1 before its own ResizeObserver fires, so the warning still appeared on first render. Replaced `ResponsiveContainer` with direct container measurement: a `ResizeObserver` on the wrapper div passes explicit pixel dimensions to `AreaChart`, so the chart only renders when a real measured width is available.

## [v2.158.7] - 2026-04-03

### Fixed
- **Dashboard sparklines no longer log width(-1)/height(-1) warnings** — Recharts was measuring carousel cards the moment sparkline data arrived from the API, before the browser had laid out off-screen cards. The render deferral now triggers from when data first becomes available (not from component mount), so the chart waits two animation frames for layout to settle before measuring.

## [v2.158.6] - 2026-04-03

### Security
- **npm dependency security update** — Updated frontend dependencies to address flagged vulnerabilities: `react-router-dom` 7.10.1 → 7.14.0 (CSRF/XSS patches), `rollup` 4.53.3 → 4.60.1 (path traversal fix), `undici` 7.22.0 → 7.24.7 (WebSocket/HTTP smuggling fixes), `axios` 1.13.2 → 1.14.0 (safe upgrade away from the supply-chain-compromised 1.14.1). None of these vulnerabilities were directly exploitable in our deployment, but the updates are clean and non-breaking.

## [v2.158.5] - 2026-04-03

### Fixed
- **Dust sweep and rebalance status endpoints no longer time out** — The v2.158.2 parallel-fetch fix used `asyncio.gather()` over individual ticker calls, but those calls go through a 200ms rate-limiter lock that serializes them regardless of concurrency. An account with 40 altcoins would still wait 8+ seconds minimum. Both endpoints now use a single bulk `list_products()` call (cached 1 hour, returns all ~500 products with current prices) — pricing 40 coins now takes milliseconds instead of up to 45 seconds.

## [v2.158.4] - 2026-04-03

### Fixed
- **Delisted pairs in paper accounts no longer spam 404 errors** — Coins that were once traded but are no longer listed on Coinbase (e.g. RONIN after its delisting) would cause repeated failed price lookups on every bot cycle. The daily pair-sync job now identifies these coins and the paper trading client skips pricing attempts for them. Balances are preserved exactly as on a real exchange — you can't remove worthless coins from your wallet, and neither can we.
- **Single-pair bots with a delisted pair are now auto-deactivated** — The daily pair-sync previously only scanned the multi-pair list (`product_ids`) but ignored the legacy single-pair field (`product_id`). A bot whose sole trading pair was delisted would keep running and firing 404s indefinitely. It is now detected, deactivated, and its pair cleared automatically.

## [v2.158.3] - 2026-04-02

### Fixed
- **Rebalancing toggle reverts on page refresh** — Turning rebalancing on or off now survives a page refresh within the same browser session. The session storage cache was not being updated after a mode change, so a fresh page load within 5 minutes would restore the old state from cache instead of showing the current setting.

## [v2.158.2] - 2026-04-02

### Fixed
- **Rebalance status timeout** — The portfolio rebalance status endpoint no longer times out when an account has many open positions. Price lookups for all open positions are now fetched in parallel instead of one at a time.
- **Dust sweep settings timeout** — The dust sweep settings endpoint no longer times out for accounts with many altcoin balances. Altcoin USD price lookups are now fetched in parallel instead of sequentially.

## [v2.158.1] - 2026-04-02

### Fixed
- **Frontend component path cleanup** — Removed stale import path references after component folder reorganization in v2.158.0.

## [v2.158.0] - 2026-04-02

### Security
- **MFA required to delete accounts** — Deleting an account now requires MFA verification (TOTP or email code) before the deletion proceeds.
- **MFA required to sell portfolio to base currency** — The "Sell Portfolio to Base" action now requires MFA verification.
- **TOTP required to disable email MFA** — If you have TOTP (authenticator app) active, disabling email MFA now requires your TOTP code as a second confirmation.
- **Task ownership enforcement** — Panic sell status and portfolio conversion status can no longer be read by users other than the one who initiated the task.
- **Shared-account access fixed** — Managers on shared accounts can now correctly place, cancel, and update limit close orders and perform manual position operations (add funds, update notes). Previously only the account owner could do these.
- **Rate limiting on auth endpoints** — `/auth/refresh` is now limited to 60 requests/hour. `/auth/change-password` is limited to 5 requests per 15 minutes.
- **Email MFA resend rate limiting** — Resending a login email code is now rate-limited to 5 attempts per 5 minutes.

### Fixed
- **Rebalancing toggle: 400 error** — Turning portfolio rebalancing off no longer returns a 400 "percentages must sum to 100%" error. Percentage validation is now skipped when only toggling the enabled flag.

### Changed
- **Internal: service layer extracted** — Business logic for portfolio rebalancing, P&L calculations, news querying, and seasonality management has been moved from routers into dedicated service classes. No user-visible behavior change.
- **Internal: router files split** — The accounts and reports routers have each been split into separate query and mutation files for better maintainability. No user-visible behavior change.

## [v2.157.2] - 2026-04-02

### Added
- **Portfolio: Hide Dust toggle** — The Holdings table now has a "Dust hidden" / "Show all" button in the header. When enabled (default), holdings worth less than $1 USD are hidden. The count of hidden dust entries is shown in the button. The setting is remembered across page refreshes and navigation.

## [v2.157.1] - 2026-04-02

### Fixed
- **Panic Sell: force market orders** — Panic sell now always forces a market order for each position, bypassing the bot's limit-order preference and profit-floor checks. Positions that had a pending limit close order are reset before selling so they are not skipped.
- **Panic Sell: rebalancers disabled before sells** — Rebalancers, auto-buy, and minimum balance reserves are now disabled in a phase that runs *before* position selling begins, preventing the rebalancer from buying into other bases while sells are in progress.
- **Manual force-close: slippage override** — When a bot's VWAP profit is below its take-profit floor, force-closing a position now shows a "Sell Below Target?" confirmation dialog instead of a dead-end error toast, letting you proceed or cancel.

## [v2.157.0] - 2026-04-02

### Added
- **Panic Sell — Emergency Liquidation**: A new "🚨 Panic Sell" button on the Positions page lets you immediately cancel or market-sell all open positions across every bot on your account in one action. Options include: converting all freed balances to a target currency (USD / USDC / USDT / BTC / ETH) using automatic intermediate-pair routing if a direct pair doesn't exist; stopping all active bots; disabling the portfolio rebalancer and bot rebalancer groups; disabling auto-buy BTC; and zeroing all minimum balance reserves so conversion can proceed fully. The operation runs as a background task with a live per-phase progress meter. Protected by MFA — requires your authenticator code (TOTP) or a one-time email code before execution.
- **Portfolio Conversion: USDC, USDT, ETH targets**: The "Convert Portfolio" feature now supports USDC, USDT, and ETH as target currencies in addition to BTC and USD. Coins without a direct pair to the target are automatically routed through USD as an intermediate.

## [v2.156.1] - 2026-04-02

### Changed
- **Performance: Database Indexes** — Added 3 missing indexes that were causing full table scans: `signals` by position ID (used by position detail view), `order_history` by bot + timestamp (used by paginated order history), and `account_value_snapshots` by user + date (used by snapshot aggregation).
- **Performance: Filter Counts** — Position filter dropdowns (market, bot, pair, category) now compute option counts in a single pass over positions instead of re-scanning the list for each unique value. No visible change; just faster on large position sets.
- **Performance: Indicator Extraction** — Candle OHLCV arrays are now built in one loop instead of four separate passes.
- **Performance: Background Polling** — Position and bot data no longer refetch every 5–10 seconds while the browser tab is hidden, reducing unnecessary network traffic.

## [v2.156.0] - 2026-04-02

### Added
- **Report Schedule Retention Policy**: Each report schedule can now set a retention policy — keep only the last N reports, delete reports older than N days, or both. When both limits are set, a report is deleted only if it exceeds both (more permissive). Old reports are cleaned up automatically after each scheduled run. All 6 existing schedules default to keeping the last 4 reports.

## [v2.155.0] - 2026-04-02

### Added
- **Self-Sustaining Recurring Savings**: Recurring savings targets now compute a minimum "hold" seed — the amount that, when kept after each withdrawal, compounds back to cover the next cycle's withdrawal (including tax) without any further contributions. The savings report breakdown now shows `Spend · Tax · Hold → accumulate` so you can see exactly what you're building toward.
- **"Ready" Badge for Savings**: Savings targets that have accumulated enough to make their full withdrawal right now display a "Ready" badge instead of "On Track".

### Fixed
- **Missing Trading Pairs**: Hundreds of USDT and ETH trading pairs were disappearing from the bot edit modal due to a `bypass_cache` parameter that was not forwarded through the adapter layer — causing a fallback to a tiny default list. All pairs are restored.
- **Savings Report Breakdown**: The spend line now correctly breaks out Tax and Hold components alongside the Spend amount.
- **Coin Category Tooltip Clipping**: The coin categorization hover tooltip on deal cards was being clipped by the card frame. It now renders in front of the card.
- **Product List Cache**: Removed a hardcoded `force_refresh=true` that was bypassing the product cache on every page load.
- **Test Isolation**: Fixed `TestGeminiClientWrapperKwargs` tests that failed when run after other tests that had already imported `google.generativeai`.

## [v2.154.7] - 2026-03-31

### Added
- **Full USDT & ETH Market Access**: Unlocked hundreds of USDT and ETH trading pairs in the backend by expanding `_TRADEABLE_QUOTES`.
- **Cache Refresh**: Added `force_refresh` capability to the product listing endpoint to ensure new market pairs appear immediately without waiting for the 1-hour cache expiry.

### Fixed
- **Soft Ceiling Logic Expansion**: Expanded all budgeting and soft ceiling calculations to fully support ETH as a quote currency (including exchange minimums and aggregate portfolio values).

## [v2.154.6] - 2026-03-31

### Added
- **USDT and ETH Pair Selection**: Added "USDT All" and "ETH All" quick-filter buttons to the bot creation/edit modal. These pairs are now correctly grouped and available for all strategies.
- **Improved Pair Filtering**: Updated backend to include USDT and ETH in the list of tradeable quote currencies, enabling hundreds of new trading pairs.

### Fixed
- **Bot Form Summary (Soft Ceiling)**: The summary block at the bottom of the edit modal now correctly bases its capital calculations on the clamped "Soft Ceiling" value instead of the unconstrained "Max Concurrent Deals" when enabled.

## [v2.154.5] - 2026-03-31

### Added
- **Expanded Trading Pairs**: Added official support for USDT and ETH quote currency trading pairs in bot configuration.
- **ETH Rebalancing Budget**: The budget calculator now includes aggregate ETH portfolio value for bots trading ETH pairs.

### Fixed
- **Bot Edit Modal Summary**: The DCA Budget Calculator summary in the bot edit modal now uses the "Soft Ceiling" (clamped max deals) for its calculations when enabled. This ensures the summary matches the actual trading limits and prevents false "Over-Allocation" warnings when the soft ceiling is active.
- **Unified Calculation Logic (ETH/USDT)**: Updated shared calculation utilities to correctly handle exchange minimums and aggregate values for ETH and USDT quote currencies.

## [v2.154.4] - 2026-03-31

### Added
- **Separate USDT Rebalancing**: USDT is now treated as a first-class citizen in the rebalancing system, separate from USDC. Users can now set independent target percentages and minimum balance reserves for both USDC and USDT.

### Fixed
- **Active Trades Column**: The "Active trades" column on the Bots page now correctly shows the Soft Ceiling (SC) preview (e.g., "13/24 (SC: Max 50)") even before the backend has performed its first evaluation cycle. It now uses the same calculation logic as the bot edit modal.
- **Unified Calculation Logic**: Centralized DCA multiplier and budget calculations into a shared utility to ensure consistency between the bot list, edit modal, and strategy configuration sections.

## [v2.154.3] - 2026-04-01

### Fixed
- **Bot Budget Rebalancer rounding (again)**: Slider values now stay on exact 0.5% boundaries throughout — redistribution rounds to the nearest 0.5 instead of 0.01, so dragging one bot to 32.5% no longer causes adjacent bots to drift to 32.49%/15.01%. Saving also normalizes any legacy sub-step values already in the database to the nearest 0.5%.

## [v2.154.2] - 2026-04-01

### Fixed
- **Soft Ceiling display**: SC effective max now shows the correct number on the bot list. The budget calculation was silently ignoring the value of all open positions (returning only the free cash balance) because the raw SQL queries used unqualified table names that PostgreSQL couldn't resolve. Fixed by qualifying all table references with the `trading.` schema.
- **Bot Budget Rebalancer rounding**: Sliders no longer save slightly off values (e.g. 32.53%/32.47% instead of 32.5%/32.5%). The distribution algorithm now corrects floating-point rounding error by assigning any remainder to the last adjusted slot.

## [v2.154.1] - 2026-03-31

### Changed
- **Active Trades column — SC computation**: Soft ceiling effective max is now computed client-side using the same formula as the bot edit modal, so the correct number is always visible immediately — no waiting for a background monitor cycle.

### Fixed
- **Active Trades column — SC warmup**: Removed the broken backend warmup that was returning incorrect values (used free balance instead of full account aggregate). Client-side computation matches what the edit modal shows.

## [v2.154.0] - 2026-03-31

### Changed
- **Active Trades column — SC format**: Soft ceiling now displays inline as `14/22 (SC: Max 50)` — current open / SC-computed cap / configured max — all on one line. Before the first cycle the denominator shows the configured max with `(SC)` as placeholder.

### Fixed
- **Soft ceiling warmup**: The SC-computed effective max is now computed on the first monitor cycle after restart (when the stored value is missing), so the correct number appears without waiting for a natural buy-signal evaluation.

## [v2.153.0] - 2026-03-31

### Changed
- **Active Trades column**: When Soft Ceiling is enabled, the column now shows the SC-computed effective cap as the denominator (e.g. `14/22`) with a `SC: Max 50` sub-label showing the configured hard max. Before the first signal cycle the column shows `SC` as a placeholder.
- **Budget column**: Removed the redundant `N/M deals SC` line — deal slot info is now shown exclusively in the Active Trades column.

## [v2.152.0] - 2026-03-31

### Added
- **Rebalancer slider lock**: Pin individual bot allocations in the Bot Budget Rebalancer so they stay fixed while you slide others. Locked bots show a blue border and lock icon; unlocked bots absorb the redistribution proportionally.

### Fixed
- **Rebalancer auth**: The rebalancer API was using axios without auth headers, causing 401 errors. Switched to `authFetch`.
- **Rebalancer number inputs**: Backspace now works correctly in the Max Total Allocation and Overweight Tolerance fields — values are parsed and clamped only when you leave the field.

## [v2.151.0] - 2026-03-31

### Added
- **Bot Budget Rebalancer**: New panel on the Bots page that lets you distribute your total budget allocation across bots in each currency group (USDC, BTC, etc.) using sliders. Set each bot's target allocation percentage, configure a max total cap (up to 150%), and save — the rebalancer writes the budget percentage directly onto each participating bot.
- **Overweight gating**: Bots whose deployed capital exceeds their target allocation (plus a configurable tolerance) are automatically soft-blocked from opening new base orders until they come back within range. Overweight bots display a badge in the bot list.

## [v2.150.4] - 2026-03-31

### Fixed
- **Account invitation toast**: The real-time notification for incoming account invitations now includes a "Review" button that takes the user directly to the invitation acceptance page.

## [v2.150.3] - 2026-03-31

### Fixed
- **QFL Indicator — Base TF selector in basic condition builder**: The "Base Timeframe" dropdown for multi-timeframe QFL setup was only available in the advanced condition builder. It is now also present in the standard condition builder, matching the advanced builder's feature set.
- **QFL Indicator — Silent fallback on missing base candles**: When the configured Base Timeframe candles are not yet available, the system now logs a warning rather than silently falling back, making misconfigured setups easier to diagnose.
- **QFL Indicator — Lint and code quality**: Removed trailing whitespace and fixed a line length violation in the QFL implementation introduced in v2.150.2.
- **Dead configuration removed**: Removed the `vwap_bounce_timeframe` strategy config parameter, which was registered but had no effect — VWAP bounce timeframe is correctly controlled by the per-condition timeframe selector.
- **ConditionBuilder type safety**: Added missing VWAP, VWAP Bounce, and QFL entries to the indicator metadata map in `ConditionBuilder.tsx`, resolving a TypeScript type error.

### Added
- **QFL multi-timeframe tests**: Added 5 new tests covering the `base_candles` code path, the invalid-setup rejection (base TF < crack TF), and fallback behavior.

## [v2.150.2] - 2026-03-31

### Added
- **Multi-Timeframe QFL Support**: The QFL (Quick Fingers Luke) indicator now supports separate timeframes for **Base Identification** and **Crack Detection**. This allows "pro" setups like finding strong support on 1h/4h candles while triggering entries on 5m/15m candles for faster execution.
- **QFL Validation**: Added backend enforcement to ensure the Base timeframe is greater than or equal to the Crack timeframe.

## [v2.150.1] - 2026-03-31

### Fixed
- **Bot Form → Indicator Selection**: Fixed a bug where newly added VWAP, VWAP Bounce, and QFL indicators were not selectable in the indicator-based strategy condition builder. Added support for these indicators and their specific parameters (lookback, bounce %, crack %) to the advanced condition builder.
- **Bot Form → UI Consistency**: Synced `Volume RSI` and `Gap Fill %` indicators across all condition builder components to ensure consistent availability.

## [v2.150.0] - 2026-03-31

### Added
- **VWAP indicator** in the bot condition builder. Select "VWAP" as a condition type and use operators like "Above", "Below", "Crossing Above", or "Crossing Below" — works exactly like EMA/SMA cross conditions.
- **VWAP Bounce Up** pattern indicator: fires when the penultimate closed candle's wick touched or crossed below VWAP, and the most recent closed candle closed back above it (bullish retest confirmation).
- **VWAP Bounce Down** pattern indicator: fires when the penultimate closed candle's wick touched or crossed above VWAP, and the most recent closed candle closed back below it (bearish retest confirmation).
- **QFL Crack (Quick Fingers Luke)** indicator: scans historical candles to identify validated support bases (pivot lows followed by a significant bounce), then signals when price cracks below a base. Configurable lookback candles, minimum bounce %, and crack % — displayed live in the condition builder.

### Fixed
- **Portfolio Management → Current Allocation**: reserved amount now correctly reflects the actual balance available to reserve. Previously, setting a $100 reserve while only having $50 would show "$100 reserved" immediately — now it shows the actual $50 in effect. The chart updates immediately after saving instead of requiring a manual refresh.

## [v2.149.9] - 2026-03-31

### Changed
- TV Chart controls overhaul: replaced TradingView's built-in top toolbar with our own persistent header bar. Interval (1m–1M), chart type (Candles, Heikin-Ashi, Bars, Line, Area, Baseline, HLC Area, Renko, Line Break, Kagi, P&F), and indicators (18 built-in studies across Trend/Momentum/Volume categories) are all saved to localStorage and restored on every open. TradingView's side toolbar (drawing tools) is preserved.

## [v2.149.8] - 2026-03-31

### Added
- TV Chart (click a pair in Deals) now has interval buttons (1m → 1W) and a Heikin-Ashi toggle in the header. Both settings persist across all pairs via localStorage — whatever you chose last is restored when you reopen any chart.

## [v2.149.7] - 2026-03-31

### Fixed
- Budget column now shows deal slot usage (`current/max deals`) alongside `% in use`, turning amber when all slots are full. Bots with Soft Ceiling enabled show a purple **SC** badge.
- `update.py --changelog` no longer shows duplicate entries when a merge commit and feature commit share the same message.

## [v2.149.6] - 2026-03-31

### Added
- Sample Bot cards now show an **Edit** button for superusers — opens the form in fully editable mode without the "(Copy)" name suffix, making it easy to tweak and test configs.
- Superusers can now update and delete default/system bot templates via the API.

### Fixed
- Chart settings (timeframe, chart type, Heikin-Ashi) are now remembered across opens — no more resetting to defaults every time you open a pair chart.

## [v2.149.5] - 2026-03-31

### Fixed
- Win rate no longer counts manually force-closed deals — only bot-driven closes (take profit, stop loss, trailing stops) factor into win rate. Manual closes are now tagged with `exit_reason = "manual"` and excluded from the denominator and numerator across all win rate calculations (bots list, bot detail, positions stats, dashboard).

## [v2.149.4] - 2026-03-31

### Fixed
- **Deal chart Safety Order lines now respect the configured DCA target reference** — the SO trigger price lines now honor the bot's "DCA Target Reference" setting (Base Order, Average Price, or Last Buy Price), matching exactly how the engine decides when to place the next safety order. For "Base Order" bots all remaining SO levels are drawn since they're fixed at open time; for "Average Price" and "Last Buy" bots only the immediately-next SO is shown (since the reference shifts after each fill). This option is already available in the bot edit form under Safety Orders.

## [v2.149.3] - 2026-03-31

### Fixed
- **Deal chart Stop Loss line no longer shows for deals without stop loss configured** — the SL line was hardcoded to always appear at −2% from average buy price. It now only appears when stop loss is actually enabled in the bot's strategy, and at the correct percentage.
- **Deal chart Safety Order lines now use the correct base price and skip triggered SOs** — SO levels were calculated from the average buy price (which shifts as SOs fill), causing them to appear at wrong levels or off-chart entirely. They now use the initial base order price as the anchor (matching how the engine triggers them) and skip any SOs that have already been executed.

## [v2.149.2] - 2026-03-30

### Fixed
- **Admins and account owners now see paper trading / demo accounts in the Accounts dropdown** — the account switcher previously hid all paper trading accounts from the dropdown regardless of who was looking. Superusers now see demo accounts they manage (via membership) in the "Shared With You" section. Account owners see their own paper trading accounts in a dedicated "Paper Trading" section. The switcher also no longer disappears when an admin or owner has a paper trading account selected.

## [v2.149.1] - 2026-03-30

### Fixed
- **Market Sentiment carousel removed from News page** — it was mistakenly left on the News page after being moved to Dashboard. It now lives exclusively on the Dashboard.

## [v2.149.0] - 2026-03-30

### Added
- **Market Sentiment carousel moved to Dashboard** — the full sentiment carousel (Fear & Greed, BTC Dominance, Altseason index, etc.) now appears at the top of the Dashboard page. It has been removed from the News page.

### Changed
- **Projection basis is now remembered across pages and reloads** — the time-range selector on the Portfolio Totals section (Dashboard) and the PnL chart (Bots page) now share and persist the same preference in localStorage. Navigating between pages no longer resets it to "All-time"; the chart also initializes from the stored value instead of always defaulting to "All-time".
- **Bots table Projected PnL cal/active toggle is now remembered** — the "cal" / "active" rate toggle on each bot's projected PnL column persists across page reloads and navigation. All bots share the same preference.

### Fixed
- **Settings → Paper Trading "Virtual Balances" is now collapsible** — the balance grid can be collapsed to save screen space. The expanded/collapsed state is remembered across reloads and navigation.

## [v2.148.2] - 2026-03-30

### Fixed
- **Max Simultaneous Capital now respects reserves and rebalancer target allocations** — the DCA budget summary in the bot edit form previously computed capital against the raw total portfolio value, ignoring any configured reserve amounts and rebalancer currency targets. It now uses the deployable value (total minus all reserves) sliced by the target allocation percentage for the bot's quote currency. If the rebalance target hasn't been reached yet, it caps at the current allocation so the display never overstates available capital; if the portfolio is overweight, it caps at the target so smaller deals help rebalance it back down.

### Added
- Unit tests for `computeEffectiveAggregateValues` covering rebalancer enabled/disabled, reserves, at-target, not-yet-reached, and overweight scenarios (15 frontend tests).
- Unit tests for `ensure_product_precision` covering happy path, fetch error handling, missing base_increment, and integer increments (5 backend tests).

## [v2.148.1] - 2026-03-30

### Fixed
- **JUPITER sell orders no longer fail with INVALID_SIZE_PRECISION** — JUPITER-USD/USDC requires at most 1 decimal place (`base_increment=0.1`), but the precision cache didn't have an entry for it and defaulted to 8. Added JUPITER-USD, JUPITER-USDC, RAY-USD, RAY-USDC, BOBBOB-USD, and BIRB-USD to the precision table.
- **New coins auto-populate precision on first sell** — the sell executor now calls `ensure_product_precision()` before rounding any order size. If a product is missing from the local precision cache, it fetches the correct `base_increment` from the Coinbase public API, uses it immediately, and writes it back to disk so future restarts don't need to re-fetch.

## [v2.148.0] - 2026-03-30

### Added
- **Superuser (admin) has manager access to all demo accounts** — the platform admin account now has manager-level access to the Observer/demo paper-trading accounts, allowing bots, goals, expense items, and report schedules to be configured on those accounts without requiring a separate login.

### Changed
- **Account sharing role renamed from "Observer" to "Shadow"** — to avoid confusion with the "Observers" RBAC group used for demo users, the read-only account-sharing role is now called "Shadow". Existing shadow members and pending invitations have been updated automatically. The banner now reads "Shadow Mode" when viewing a shared account with read-only access.

## [v2.147.3] - 2026-03-30

### Fixed
- **Reserved balances now show in their currency's color in all rebalancer charts** — the current and target bars and the pie chart now include a per-currency dashed segment for any reserved balance (e.g., a USD minimum balance reserve shows as a dashed green segment alongside the solid green deployable USD). Previously v2.147.2 made the reserve disappear entirely from the charts. The dashed border visually distinguishes reserved from deployable for the same currency. The pie chart legend also shows the reserve as a faded slice of the same color.

## [v2.147.2] - 2026-03-30

### Changed
- **Rebalancer sliders now show effective portfolio percentage** — when minimum balance reserves are configured, each slider's label shows the real portfolio impact (e.g., "47.5%") alongside the stored target ratio (50%) in grey, so you can see exactly what percentage of your total portfolio will be in each currency after reserves are accounted for. Previously, the label only showed the stored ratio, which could never actually be reached when a reserve was in place.
- **Allocation bar reflects the reserve** — the colored target allocation bar now scales the currency segments to the deployable portion of your portfolio, with a grey segment representing the reserved balance at the right end. This makes it visually clear that the currency targets fill only the deployable fraction, not the full bar.
- **Current allocation in rebalancer status uses deployable pool** — the current allocation percentages shown in the rebalancer status view (pie chart and progress bars) now compare against the deployable pool rather than the full portfolio, so current and target percentages are in the same frame and can actually converge.

## [v2.147.1] - 2026-03-30

### Fixed
- **Rebalancer badge no longer disappears between rebalancer check cycles** — the gate's in-memory state was being cleared every time the per-bot cycle ran and the allocation cache had expired (90 s TTL vs. 15–240 min rebalancer intervals). The badge would flash off on the next bot tick even though the portfolio was still overweight. Fixed by: (1) extending the cache TTL to 6 hours, and (2) only clearing the gated state when fresh allocation data from the rebalancer explicitly confirms the currency is back within target — stale or missing cache no longer resets the gate.

## [v2.147.0] - 2026-03-30

### Added
- **Rebalancer gate for bot base orders** — when an account's rebalancer is active and a bot's quote currency is overweight (above target + drift threshold), the bot is restricted to managing existing positions only (DCA safety orders and take-profits still run). New base orders are blocked until the currency rebalances back to within the target range. Grid bots are exempt since their full range is planned at creation time.
- **"⏸ Rebalancer" badge on bot cards** — bots currently gated by the rebalancer show a small orange badge next to their name so you can see at a glance which bots are waiting for rebalancing to complete.
- **Scanner log entries for rebalancer gate events** — each time a bot is gated, a scanner log entry is written showing which quote currency is overweight and that new base orders are being held back.
- **Deployable pool context on rebalancer sliders** — when minimum balance reserves are configured, a note appears under the target allocation sliders explaining that percentages apply to the deployable balance (total portfolio minus reserves), with the exact dollar amounts shown.

### Fixed
- **Rebalancer drift detection now ignores reserve balances** — previously, a reserve held in a currency with a 0% target (e.g., a $50 USD buffer when USD target is 0%) could trigger a false-positive drift and cause unnecessary rebalance trades. Drift is now measured against the deployable portfolio (after subtracting reserves), matching how the rebalancer actually executes trades.

## [v2.146.2] - 2026-03-30

### Changed
- **Savings target line items now show your actual spend target alongside the accumulation total** — when tax withholding or principal preservation (recurring targets) inflate the amount you need to accumulate, line items in the expense editor and the emailed report now display "Spend: $X → accumulate: $Y" so you can always see exactly what you planned to spend vs. what needs to be in the account.

## [v2.146.1] - 2026-03-30

### Fixed
- **Days Active no longer resets to 0 after stopping and restarting a bot** — bots that were running when the tracking columns were first added had no recorded start time, so when stopped, zero elapsed time was accumulated and the counter reset to 0 on the next start/stop cycle. A one-time migration backfills the start time for all currently-active bots so the counter continues correctly from here.

## [v2.146.0] - 2026-03-30

### Fixed
- **Market filter on Positions page now shows your actual markets** — the filter dropdown was hardcoded to only show "USD" and "BTC" options. It now derives options dynamically from your open positions, so USDC (and any other quote currency) appears automatically. The same fix applies to Trade History.
- **Market filter options no longer show as disabled** — USD and BTC were showing as greyed-out and unclickable when you only had USDC positions, because they had a count of zero. Now only markets that actually have positions appear.
- **Missing positions on Positions page** — if you had open positions spread across many accounts, only the 100 most recently-opened were being fetched (across all accounts combined), which could silently drop older positions from the view. The page now fetches positions for the selected account specifically, so all your positions for that account are always shown.

## [v2.145.3] - 2026-03-29

### Fixed
- **Soft ceiling preview now uses real exchange minimums** — the bot editor's "Current effective ceiling" display was using a hardcoded fallback (0.0001 BTC / $1 USD) instead of the actual exchange minimum order size for your selected pairs. It now fetches the real worst-case minimum from the exchange so the soft ceiling preview reflects accurate numbers.
- **Auto-correct no longer re-runs on every form keystroke** — the automatic correction that clamps `Max Concurrent Deals` to the effective ceiling was subscribing to all form data changes, causing it to re-evaluate on every field edit. It now only runs when the effective ceiling itself changes.
- **Auto-correct also fixes `Max Simultaneous Deals (Same Pair)` if needed** — when the auto-correct reduces `Max Concurrent Deals`, it now also reduces `Max Simultaneous Deals (Same Pair)` if that value would exceed the new limit.

## [v2.145.2] - 2026-03-29

### Changed
- **Renamed `calculate_aggregate_quote_value` → `calculate_market_budget`** across the entire codebase (17 source files, 12 test files). The old name implied a portfolio-wide aggregate, but the function computes the bot budget for one specific quote-currency market (free balance + capital deployed in open positions for that market's pairs). The new name makes the distinction clear and prevents misuse like the v2.141.3 rebalancer regression.
- **Fixed pre-existing test mocks** in `test_account_balance_api.py` — tests were patching `sqlite3.connect` but the implementation uses SQLAlchemy's `get_sync_engine()`. Updated all 9 affected tests; the two "with-positions" tests now actually verify position values are included.

## [v2.145.1] - 2026-03-29

### Fixed
- **Rebalancer direction bug** — fixed a critical regression where the portfolio rebalancer was computing allocations using the wrong data source, causing it to see BTC as severely underweight (~17%) when it was actually overweight (~58%). The root cause was using the Coinbase accounts-API available balance (~$59) instead of the portfolio-breakdown view (~$411), which includes all assets. The rebalancer now builds its allocation view the same way the UI does: free balances plus capital locked in open bot positions. This also fixes the reserve math so that 50%/50% targets correctly apply to the investable balance (portfolio minus reserves), not the full portfolio total.

## [v2.145.0] - 2026-03-27

### Added
- **Deal Count Soft Ceiling** — introduced a new "Soft Ceiling" feature that dynamically limits concurrent deals based on your current budget and the minimum order size requirements of your selected coins. 
    - This allows a bot to be configured with a large list of coins but only open as many positions as it can actually afford to fully fund (including all safety orders).
    - As your portfolio balance grows from earnings or deposits, the soft ceiling automatically "unlocks" more concurrent deals until it reaches your specified maximum.
    - Provides real-time feedback in the Bot Editor showing the current effective ceiling based on your settings.

## [v2.144.9] - 2026-03-27

### Added
- **Over-allocation Warning** — added a prominent visual warning in the Bot Editor when the budget percentage exceeds 100%. This ensures users are aware of the intentional over-allocation of capital while still allowing it up to the 150% limit.

## [v2.144.8] - 2026-03-27

### Added
- **Unit tests for Max Deals Clamping** — added automated test cases to verify the intelligent clamping logic for "Max Concurrent Deals", ensuring it correctly calculates and enforces limits based on selected pairs, categories, and simultaneous deal settings.

## [v2.144.7] - 2026-03-27

### Added
- **Intelligent Max Deals Clamping** — the Bot Editor now automatically corrects "Max Concurrent Deals" to a sensible maximum based on the specific coins and categories selected for the bot. The limit is calculated as: `(Coins in Allowed Categories) * (Max Simultaneous Deals per Pair)`. This prevents "insane" values that would otherwise cause validation timeouts.

## [v2.144.6] - 2026-03-27

### Fixed
- **Bot Editor crash** — fixed "Minified React error #310" (Rendered more hooks than during the previous render) by moving hook calls above early return statements in the Bot Form Modal.

## [v2.144.5] - 2026-03-27

### Fixed
- **Exhaustive wiring check** — performed a full TypeScript compilation check across the entire frontend to ensure all new features (dynamic filters, enhanced toasts, and timezone detection) are correctly imported and wired.

## [v2.144.4] - 2026-03-27

### Fixed
- **Bots Page crash** — resolved a persistent `ReferenceError` in the bot editor by cleaning up unused imports and verifying the entire frontend with the TypeScript compiler.

## [v2.144.3] - 2026-03-27

### Fixed
- **Bots Page crash** — fixed a `ReferenceError: useMemo is not defined` in the bot editor strategy configuration section caused by a missing import from React.

## [v2.144.2] - 2026-03-27

### Fixed
- **Bots Page crash** — fixed a `ReferenceError: useMemo is not defined` in the bot editor modal caused by a missing import from React.

## [v2.144.1] - 2026-03-27

### Fixed
- **Bot Editor market detection** — further improved the "Active Market" detection logic to use a frequency map of all selected pairs. This prevents USDC-based bots from occasionally defaulting back to USD (causing "mixed coins" errors) when being edited.

## [v2.144.0] - 2026-03-27

### Added
- **Dynamic Max Deals calculation** — the Max Concurrent Deals limit in the bot editor is now calculated dynamically based on the number of selected trading pairs and the allowed simultaneous deals per pair (up to a system maximum of 1000).
- **Over-allocation support** — bots can now be configured with up to 150% budget allocation, allowing for intentional over-allocation of portfolio capital.

### Fixed
- **Market selection accuracy** — improved the logic for detecting the active market (USD vs USDC) in the bot editor. The modal now correctly identifies the primary market based on all selected pairs, preventing accidental resets to USD when USDC was intended.
- **Safety Order limits** — increased the maximum number of allowed DCA safety orders from 20 to 100.

## [v2.143.1] - 2026-03-27

### Fixed
- **Positions Page crash** — fixed a `ReferenceError` where dynamic filters were being used before being properly destructured from their hook.

## [v2.143.0] - 2026-03-27

### Added
- **Bot names in trade toasts** — WebSocket fill notifications (Buy, DCA, Close) now display the name of the bot that executed the trade, making it easier to track multi-bot activity.
- **Dynamic filter counts on Positions & History** — filter dropdowns (Market, Bot, Pair, Category) now show the number of matching items in parentheses. Counts update dynamically based on other active selections.
- **Improved filter sorting** — filter items are now sorted alphabetically. Trading pairs are sorted by quote currency (USD, then BTC) and then by base currency.
- **Automatic timezone detection** — the app now detects your browser's timezone and translates all date/time entries (especially on the History page) to your local time automatically.

### Changed
- **Linger duration for trade toasts** — trade-related notification toasts now stay on screen for 16 seconds (2x longer than before) to give you more time to review the details.

## [v2.142.0] - 2026-03-25## [v2.141.2] - 2026-03-25

### Fixed
- **Portfolio rebalancer now correctly executes USD↔USDC trades** — the Coinbase convert endpoint was returning 400 errors for fiat-to-stablecoin conversions, silently blocking all USD→USDC rebalancing every hour. The rebalancer now routes USD↔USDC via BTC as an intermediary (USD→BTC→USDC and USDC→BTC→USD), which uses proven market-order paths available on all account types.

## [v2.141.1] - 2026-03-25

### Fixed
- **Paper trading allocation now sums to 100%** — the previous fix double-counted deployed capital: open positions were added to the BTC/USD bucket AND the same coins appeared in the altcoin total used as the denominator. The allocation now folds each free altcoin into its quote-currency bucket (BTC for BTC-pair trades, USD for USD-pair trades) without using open position values separately, so percentages always sum to 100%.
- **Dust sweep settings no longer times out** — loading the Settings page for accounts with many altcoin balances could exceed the 45-second browser timeout because the endpoint was making one sequential Coinbase price API call per altcoin. Now caps at 40 price lookups (sorted by balance descending) to keep the response fast.
- **Coin icon 429 errors on pages with many positions** — nginx was rate-limiting `/api/coin-icons/` requests under the general `/api/` zone (30 req/s burst=50). A dedicated location block now exempts coin icons from rate limiting entirely, since they are served from disk cache and do not touch the database.

## [v2.141.0] - 2026-03-25

### Added
- **Positions — filter by coin category** — the Positions page now has a "Coin Category" filter dropdown (APPROVED, MEME, BORDERLINE, etc.). Categories are derived dynamically from the blacklist database — only categories actually present in your positions appear. No hard-coded lists.
- **Positions — group by** — positions can be grouped by Category, Market, Bot, or Pair. Group headers appear inline in the list. Grouping persists across page navigation (saved to localStorage).
- **Positions — pagination** — positions now default to 10 per page with a toggle for 100 per page. Previous/next navigation and a "X–Y of N" counter are shown at the bottom.
- **Reports PDF — savings targets section** — generated PDF reports now include a "Savings Targets" section for each expense goal, showing each target's name, goal amount with deadline, and funding status (reserved ✓, % funded, or blocked). Previously only regular expense items appeared in PDFs.

### Fixed
- **Portfolio allocation includes open position values** — live CEX accounts now correctly show allocated capital in the rebalancing chart. Previously, only free (uninvested) balances were counted, making e.g. a BTC bot with all capital in positions show 0% BTC allocation. The fix mirrors how paper trading accounts already calculated this.
- **Expense goals endpoint 500 error** — fixed a `ResponseValidationError` where FastAPI rejected the `/api/reports/goals/{id}/expenses` response because the return type annotation was `List[dict]` but the function returns an envelope `{items, coverage_summary}`. Guarded with regression tests.

## [v2.140.0] - 2026-03-25

### Added
- **"# today" in Bots Trade Stats column** — each bot now shows how many positions it closed today (UTC) in parentheses next to the all-time closed count. Only shown when at least one trade was closed today.

### Fixed
- **Coin icon 429 errors eliminated** — coin icons are served from a local disk cache and no longer pass through the public IP rate limiter. Pages with many positions (or many different coins) were triggering the 120 req/min limit, causing icons to fail to load with "429 Too Many Requests". Icons now load unconditionally.

## [v2.139.5] - 2026-03-25

### Added
- **Deposit coaching for savings goals** — "Manage Expenses & Savings" now shows a deposit coaching bar when a savings target in the middle of your priority list is underfunded. It tells you exactly how much to deposit to fund the savings goal, and how much more to also cover the next blocked expense below it. Previously, coaching was only shown for income-shortage situations; savings capital gaps were silently ignored.

### Fixed
- **Deposit coaching no longer breaks when a savings goal sits between expenses** — expenses blocked by an underfunded savings target now correctly show coaching, instead of coaching disappearing entirely.

## [v2.139.4] - 2026-03-25

### Fixed
- **Expense goal metrics now scoped to the goal's linked account** — account balance and growth rate calculations for savings targets and expense coverage now use only the account that the goal is tied to (shown in the account selector). Previously, paper trading accounts and any other accounts were included, which inflated the available balance and diluted the growth rate. A paper trading account with a large simulated balance would make every savings target appear funded (false ✓) while also suppressing the displayed growth rate. Now each goal uses only its own account's real balance and real trading history.

## [v2.139.3] - 2026-03-25

### Fixed
- **Expense goal target now computed dynamically from items** — the "$X/monthly" total shown on each Expenses goal card is now always recalculated live from the current active items instead of reading a potentially stale cached value. Goals that were stuck showing "$1/mo" will now display the correct sum.
- **500 error on Manage Items fixed** — a math overflow crash (`OverflowError: math range error`) could occur when the account snapshot query returned an inflated value, causing the savings target capital-required calculation to receive an astronomically large growth rate. The snapshot query now correctly sums the latest per-account values (one row per account, not multiple snapshots), and an explicit overflow guard returns 0 for any rate that would exceed float range.

## [v2.139.2] - 2026-03-25

### Added
- **Projected Monthly & Annual Return in Key Metrics** — the HTML, PDF, and email report Key Metrics section now shows the projected monthly return (%) and compound-annualized return (%) derived from your 30-day trading history. This is the same growth rate used to project savings target funding, tithe amounts, and income coverage.

### Fixed
- **Savings targets no longer show partial funding when higher-priority expenses are uncovered** — a savings goal will now be marked "Blocked" (indigo badge) when any expense ranked above it in your priority list is uncovered or only partially covered. The system correctly recognises that uncovered expenses have first claim on all resources, so the savings target should not reserve capital until those obligations can be met.
- **Growth rate for savings targets was stuck at a stale value** — the Goals page was computing the account return rate using a sum of recent daily snapshots instead of the latest single snapshot. This inflated the denominator and produced an artificially low rate (e.g. 6.9% when the true compound rate was much higher). Now the most recent snapshot is used, matching the Dashboard Portfolio Totals calculation.

## [v2.139.1] - 2026-03-25

### Fixed
- **Expenses goal tabs no longer bleed between goals** — when you have two or more Expenses goals, clicking the Coverage/Upcoming/Projections tabs in one goal was activating the wrong tab in the other. Each goal now gets its own unique CSS IDs so their tab controls are fully independent.
- **Savings targets shown in priority order within the coverage table** — savings goals now appear interleaved with expense rows at their correct position in the sort order. Each savings row shows what percentage of the capital reservation is currently funded (e.g. "63% funded ($619 / $980)") so you can see at a glance where the funding pipeline stands.
- **Tithes and percent-of-income items no longer show $0** — items calculated as a percentage of projected income were displaying $0 in the Manage Expenses panel because the normalized amount was being re-computed outside the waterfall. Now the waterfall-computed amount (which has access to projected income) is used consistently.
- **Account Value Over Time chart timeframe buttons stay enabled** — selecting a short time range (e.g. 7D) was graying out longer ranges like 30D and 3M even when the account has 90+ days of data. The chart now remembers the widest data span it has ever loaded for the current account, so timeframe buttons stay enabled correctly.
- **Paper trading allocation now includes open positions** — the rebalance status panel was counting only free (uninvested) balances, making allocations look like they didn't add up to 100%. Open long positions are now valued at current market prices and added to their quote-currency bucket.

## [v2.139.0] - 2026-03-25

### Changed
- **Savings targets are now capital reservations, not monthly contributions** — the system now shows how much of your account balance needs to be set aside today ("capital required") so compound growth reaches your goal by the target date. If your current balance already covers the required reservation, it shows "Reserved: $X ✓ — funded by growth" with zero income claim. Only when the balance is insufficient does it calculate a monthly income contribution for the shortfall.
- **Sort order determines savings priority** — placing a savings target above expenses in your list means it has first claim on your account balance. The income available for expenses below it is reduced by the income that the reserved capital would have generated. Move a target lower and it gets whatever balance remains after higher-priority items.
- **Growth rate uses compound annualization** — the savings growth rate is now calculated as `(1 + daily_rate)^365 − 1`, matching the "Compounded" row on the Dashboard Portfolio Totals, rather than the simpler linear annualization used previously.
- **Recurring + tax gross-up** — recurring savings targets now correctly gross up the withdrawal for taxes and preserve the rollover principal so the next cycle can restart. For example, if you need $30k after taxes every 2 years and want to keep $500 in the account to restart, the system targets `($30k / (1 − tax%)) + $500` as the FV.
- **"Currently Saved" field renamed** to "Recurring rollover reserve" with a note clarifying its purpose: it sets the principal to preserve after withdrawal for recurring goals. Actual reservation is determined dynamically by position in the list.

### Added
- **Savings targets in HTML reports** — the Coverage tab now includes a Savings Targets section below the expense table with per-target reservation status, growth rate (with "auto" badge when using live account return), and on-track/behind badges. Summary stats gain a Total Claims row and a Surplus/Shortfall line when savings targets are present.
- **"Blocked" status for expenses** — if an underfunded savings target sits above an expense in your list, that expense is now marked "Blocked" (indigo badge) in both the editor and the HTML report, making the priority chain visible.

## [v2.138.1] - 2026-03-24

### Changed
- **Savings target growth rate is now driven by your account's live projected return** — since savings sit in the trading account and earn through trading, the required monthly contribution is automatically calculated using your account's annualized daily return rate (the same figure used to project income in your expenses goal). No manual entry needed.
- **Growth rate override still available** — if you want to model a specific rate (e.g. a HYSA at 4.5% or a fixed-income assumption), you can enter it in the optional "Annual Growth Rate" field on the savings target. Leave it blank to use the live account projection.

### Fixed
- **Goals 500 error after v2.138.0 deploy** — migration 071 added the savings target columns to the model but failed to execute against PostgreSQL because the migration file had no `if __name__ == '__main__'` entrypoint. Columns are now applied and the goals endpoint is restored.

## [v2.138.0] - 2026-03-24

### Added
- **Savings targets in expense goals** — you can now add "save up for" items alongside regular expenses in any expenses goal. Create a savings target with a goal amount (e.g. $5,000 for a cruise), a target date, how much you've already saved, and an assumed annual growth rate. The system uses the PMT formula to calculate the required monthly contribution and shows it in the same coverage waterfall as your expenses — so you can see at a glance whether your income covers both your bills and your savings goals.
- **Savings target progress tracking** — each target shows a progress bar, percentage saved, months remaining, and an on-track indicator. Recurring targets (e.g. vacation fund that replenishes every 24 months) are supported.
- **Expense editor redesigned as unified items editor** — the "Manage Expenses" panel now has an Expense / Savings Target toggle at the top when adding a new item. Savings targets display with a green piggy-bank badge and show "Goal: $X by [date] · Y% saved" instead of amount/frequency.
- **Goal cards show item type counts** — the expenses goal card now shows separate counts for expenses and savings targets (e.g. "3 expenses, 2 savings targets").

## [v2.137.0] - 2026-03-24

### Added
- **Observer mode banner shows account owner's name** — the purple observer banner now reads "Viewing [Owner]'s account '[Account Name]' (Read-Only)" so it's always clear whose account you're viewing.
- **7 new TTS voices** — added Davis, Nancy, and Tony (high-quality US Neural voices), plus four Multilingual Neural variants (ava-multi, emma-multi, brian-multi, andrew-multi) which use Microsoft's higher-fidelity model tier.

### Fixed
- **Portfolio auto-refreshes without manual intervention** — the portfolio now fetches live exchange data on every 60-second poll instead of serving backend-cached results. Manual "Refresh" button is no longer needed to see current balances.
- **Portfolio refreshes immediately after completed trades** — any buy or sell order fill (from bots or manual trades) triggers an instant portfolio refresh via WebSocket notification.

## [v2.136.8] - 2026-03-24

### Added
- **Manager role is now fully functional** — account managers can start/stop/force-run bots, create and delete bots, edit bot configuration, cancel and force-close positions, and update position settings on accounts they manage. Previously the manager role had the same read-only access as observer.
- Manager access applies to bot cloning, copy-to-account, cancel-all-positions, and sell-all-positions as well.

### Fixed
- **Security: invite rate limit** — account owners are now capped at 10 invitations per account per hour to prevent invite spam.
- **Security: rebalance and dust-sweep pages cache live API calls** — member requests no longer directly trigger repeated Coinbase API calls using the account owner's credentials. Responses are cached per account (30s for rebalance status, 60s for dust sweep).
- Account bots list (`/api/accounts/{id}/bots`) now correctly returns bots for observers and managers, not just the account owner.

## [v2.136.7] - 2026-03-24

### Fixed
- **Observer: Coin Categories shows account owner's overrides** — when viewing a shared account, the Coin Categories page now displays the account owner's personal category overrides instead of the observer's own. The override column is read-only in this context.

## [v2.136.6] - 2026-03-24

### Fixed
- **Observer: Portfolio Management settings blank in Settings** — auto-buy, rebalance, minimum balance reserves, and dust sweep settings for shared accounts were returning 404 for observers. All four read endpoints now allow access via account membership.
- **Observer: rebalance/auto-buy/dust controls not disabled** — write controls in Portfolio Management (mode selector, sliders, save buttons, dust sweep) are now disabled per-account when the account is observed.
- **Observer: "Observer — Read-Only" badge in Portfolio Management** — each shared account section in Settings now shows the role badge next to the account name.

## [v2.136.5] - 2026-03-24

### Fixed
- **Observer: bot AI logs 404** — observers can now view bot decision logs and scanner logs for shared accounts (was returning 404 because the endpoint enforced ownership instead of account membership).
- **Observer: account balances 503** — the balances endpoint was fetching exchange credentials using the observer's user ID (who has no credentials) instead of the account owner's. Now correctly uses the resolved account owner.

## [v2.136.4] - 2026-03-24

### Added
- **Observer mode banner** — when viewing a shared account as an observer, a persistent violet banner displays at the top of every page indicating the account name and read-only status.

### Fixed
- **Observer: sell buttons visible in Portfolio** — sell-to-USD and sell-to-BTC buttons are now hidden for observers on shared accounts.
- **Observer: write actions accessible in Positions** — add funds, edit notes, edit settings, and resize all budgets are now disabled for observers.
- **Observer: account sharing panel shown to observers** — the sharing/invite panel in Account Settings is now hidden for observers (it's an owner/manager feature only).
- **Observer: bot modal missing read-only indicator** — the bot detail modal now shows a "Read-Only — observer access" label when opened by an observer.
- **Charts: account name and observer badge** — the Charts page now shows the selected account name and an "(Observer)" label under the heading when in observer mode.

## [v2.136.3] - 2026-03-24

### Fixed
- **Observer: expense items and report details returning 404** — viewing an expense goal's items (`/reports/goals/{id}/expenses`) and opening a specific report from history (`/reports/{id}`) both returned 404 for observers on shared accounts. Both endpoints now check membership in addition to ownership when authorizing access.

## [v2.136.2] - 2026-03-24

### Fixed
- **Observer access to shared account data** — observers and managers could accept an invitation but then see blank pages everywhere (bots, positions, portfolio, dashboard, reports). All account-scoped read endpoints now correctly resolve membership: balance, portfolio, bot list, bot details & stats, positions, account value history, dashboard, and report goals/schedules/history all return the account owner's data for members with active memberships.
- **Account value chart blank for observers** — the history and activity endpoints were querying snapshots by the current user's ID rather than the account owner's ID. Fixed via owner-ID resolution when an `account_id` is supplied.
- **Report Goals/Schedules/History blank for observers** — same root cause as above; all three list endpoints now resolve the account owner's user ID when filtering by a specific account.
- **Bot modal shows Edit for observers** — observers on shared accounts now see "View Bot" (read-only modal) instead of "Edit Bot". The bot list item shows an eye icon instead of a pencil for observer accounts.
- **Reports page shows edit/delete controls to observers** — pencil icons on Goals and Schedules, and trash icons on Report History, are now hidden for observers on shared accounts.

## [v2.136.1] - 2026-03-24

### Security
- **Email MFA on by default** — all new accounts now have email MFA enabled automatically. Existing verified accounts were backfilled. MFA activates at login once email address is verified; the signup verification email doubles as the first MFA step. Users can still add an authenticator app; only one method needs to pass.
- **Disposable email jail** — IPs that attempt to sign up with throwaway email addresses twice within 24 hours are rate-limited for the remainder of that window. First attempt is still allowed through; the second is blocked with a neutral error message.

### Fixed
- USDC-based bots could open deals against DAI and other stablecoins because the stable-pair check only matched an explicit list. Now any pair where both sides are known stablecoins (e.g. `DAI-USDC`, `USDT-USDC`) is blocked regardless of whether it appears in the list.

## [v2.136.0] - 2026-03-23

### Added
- **Account sharing / co-management** — account owners can now invite other users to collaborate on a CEX account, Google Docs-style. Two access levels are available:
  - **Manager** — can manage bots, view positions, run reports, and place orders on the account.
  - **Observer** — read-only access to balances, bots, positions, and order history.
- **Invite by email** — owners send a one-time, 7-day expiring invitation link to any email address. The recipient must authenticate as the invited address before they can accept, preventing accidental or malicious membership.
- **Real-time invitation notification** — if the invitee is currently logged in, they receive an instant in-app notification via WebSocket push in addition to the invitation email.
- **Inbound invitation bell** — a bell icon in the header shows a badge when pending invitations are waiting. Clicking it reveals a popover to review, accept, or decline each invitation without leaving the current page.
- **Shared accounts section in account switcher** — accounts shared with you appear in a separate "Shared With You" section in the account dropdown, each labelled with your role and the owner's name.
- **Sharing panel in Settings** — each CEX account in Settings now has an Account Sharing section. Owners can invite members, change roles, remove members, and revoke pending invitations. Members see their current role and a "Leave Account" button.
- **Accept Invite page** — deep-link at `/accept-invite?token=…` handles the full accept/decline flow with auth-gate redirect for unauthenticated users and a clear error screen for email-mismatch cases.
- **Audit trail** — all membership events (invited, accepted, declined, role changed, removed, left, revoke) are recorded in an append-only event log for each account.

## [v2.135.11] - 2026-03-23

### Fixed
- **Rebalance status timeout** — the portfolio allocation endpoint was making 7 Coinbase API calls sequentially, each with a 30-second timeout. If any one call stalled, the total response time blew past the frontend's 45-second limit. All balance and price fetches are now parallelised with `asyncio.gather()`, cutting response time by ~6× and eliminating cascading timeouts.

## [v2.135.10] - 2026-03-23

### Added
- **Meme coin category** — meme coins (DOGE, SHIB, PEPE, WIF, etc.) now have their own distinct category, shown in purple throughout the coin manager. Previously they were mixed in with blacklisted coins, making it hard to tell community-driven speculative coins apart from proven rugpulls and dead projects. Meme coins that are also confirmed rugpulls or abandoned projects continue to be classified as Blacklisted.

### Changed
- **AI coin review distinguishes meme from blacklisted more precisely** — the AI is now instructed that a meme coin's community origin does not protect it from being blacklisted if it is also a proven scam, rugpull, or dead project.
- **One extra PostgreSQL connection slot reserved for external access** — ad-hoc psql connections and maintenance scripts no longer hit the "remaining connection slots reserved for superuser" error during normal operation.

### Fixed
- **Coin review service tests** — four tests were patching a module attribute that no longer existed after an import rename. Tests now correctly pass the session factory as a parameter, matching how the function actually works.

## [v2.135.9] - 2026-03-23

### Fixed
- **Backend shuts down cleanly on restart** — the monitor loop previously blocked SIGTERM for up to 20+ seconds while finishing the current cycle (reconciliation, exchange API calls). The monitor task is now cancelled immediately on shutdown and exits within a second. Fixes 502 errors that appeared during service restarts.

## [v2.135.8] - 2026-03-23

### Fixed
- **Admin Bans grouping sort** — when grouping bans by country, ISP, or jail, the list now sorts by group key first so all members of a group are contiguous across pagination pages. Previously, group headers could show a count that disagreed with the visible rows because items from the same group were spread across different pages.

### Changed
- **Bot monitor concurrency now scales with available RAM** — instead of hardcoded limits, bot and pair concurrency are derived each monitor cycle using a sigmoid curve over available system memory. Concurrency rises smoothly from a safe minimum at low memory to its carrying capacity at comfortable memory levels, then plateaus regardless of how much RAM is free. The sigmoid midpoint scales with total RAM so the curve stays meaningful after a hardware upgrade.
- **Database pool sizes now auto-derive from PostgreSQL's `max_connections`** — on startup the backend queries `max_connections`, subtracts superuser-reserved slots, and allocates the remainder across the write pool, read pool, and API connections using a configurable resource share ratio. The only value that needs manual tuning when switching hardware is `MONITOR_RESOURCE_SHARE` in `server_resources.py`.

## [v2.135.7] - 2026-03-23

### Fixed
- **Concurrent pair processing connection pool exhaustion** — the initial concurrent implementation created up to 25 simultaneous database sessions against an 8-connection pool, causing widespread 500 errors. Fixed by: bumping the write pool to 15 connections (pool_size=10, max_overflow=5), reducing bot concurrency to 3 (from 5), and setting pair concurrency to 2 — giving a safe budget of 3 × (1+2) = 9 monitor sessions plus 6 for API requests, staying within the PostgreSQL max_connections=25 limit.

## [v2.135.6] - 2026-03-23

### Changed
- **Bot pair processing is now concurrent** — the monitor now processes up to 5 trading pairs simultaneously per bot (using an asyncio semaphore with per-pair database sessions) instead of sequentially. A bot with 20 pairs now completes a monitoring cycle in ~6 seconds instead of ~30 seconds. The per-pair API throttle delay is preserved to keep things t2.micro friendly.
- **DCA price bar calculation optimised** — the position price bar now uses an O(n) closed-form formula for remaining DCA level prices instead of an O(n²) nested loop. The helper `calculateDCAPrices` is now a reusable, tested utility in `positionUtils`.
- **Safety order chart lines are cheaper to render** — the deal chart now uses lightweight price lines for safety order levels instead of creating full time-series line data (one data point per candle per level). This eliminates redundant O(levels × candles) chart work on every position update.

## [v2.135.5] - 2026-03-23

### Changed
- Architecture documentation split from a single monolithic `architecture.json` into three focused files (`docs/architecture/index.json`, `backend.json`, `frontend.json`) for faster, more targeted access. Also corrected several stale entries in the process (middleware headers, ban monitor geo-IP, models package structure, missing contexts and services).

## [v2.135.4] - 2026-03-23

### Fixed
- **Child voice content filter restored and significantly expanded** — Ana (en-US-AnaNeural) has been restored to the voice list. The existing content-filtering system (which automatically swaps child voices to an adult voice for inappropriate content) was always the correct mechanism; the voice was incorrectly removed entirely in v2.135.2. The adult-content keyword list has been substantially expanded to cover categories that were missing: death and fatal events (death, died, killed, fatal, fatality, victim, house fire, building fire), drowning, choking, asphyxiation, suffocation, strangulation, cardiac arrest, hit-and-run, war crimes, airstrikes, civilian casualties, hate crimes, extremism, abortion, miscarriage, stillbirth, self-harm, autopsy, morgue, animal cruelty, neglect, and starvation. The filter now covers 200+ keywords across 8 categories.

## [v2.135.3] - 2026-03-23

### Fixed
- **Orphaned order monitor no longer creates phantom positions** — the auto-reconciliation added in v2.135.2 used a net-balance calculation from the exchange API, but the API hard-caps responses at 1000 orders, meaning older sell orders could be missing from the result. This made it appear that untracked buy orders left a larger net holding than actually existed, leading to phantom positions with inflated quantities. The reconciler now logs newly-detected orphaned orders once at WARNING (so the issue is visible) and silently suppresses all future detections of the same orders — no phantom positions are created.

## [v2.135.2] - 2026-03-23

### Fixed
- **Orphaned orders from cancelled positions now auto-reconcile** — when the order monitor detects filled exchange orders that have no matching trade records (e.g., from positions that were deleted), it now computes the net holding per product. Products with a net positive balance get a tracking position created automatically (with full trade history linked), so the portfolio reflects the real holdings and the log warnings stop permanently. Products that net to zero (fully closed) are silently acknowledged.
- **Child voice removed from TTS** — `en-US-AnaNeural` (a Microsoft Azure child voice) has been removed from the available TTS voices. Any article previously assigned this voice will fall back to the default (Aria). A child's voice reading news about deaths, disasters, or other serious topics was clearly inappropriate.

## [v2.135.1] - 2026-03-22

### Fixed
- **TradingView chart restored** — the app-level Content-Security-Policy added in v2.135.0 was stacking with nginx's CSP and the browser was applying the most restrictive intersection, blocking `s3.tradingview.com`. CSP and HSTS are now owned exclusively by nginx (which already had the correct complete policy); the app-level fallback has been removed.
- **Ban report now shows country names and ISP** — geo lookups were returning empty results because ipinfo.io was rate-limiting unauthenticated requests. Switched to ip-api.com batch endpoint (no API key required, returns full country names and ISP directly, 100 IPs per request).

### Security
- **RBAC sweep — all `require_superuser` gates replaced with specific permissions** — endpoints now use fine-grained RBAC permissions instead of the blunt superuser check: blacklist write operations use `BLACKLIST_WRITE`, settings reads use `SETTINGS_READ`, settings writes use `SETTINGS_WRITE`, monitor start/stop use `SYSTEM_RESTART`, shutdown use `SYSTEM_SHUTDOWN`, pair monitor status uses `SYSTEM_MONITOR`, user registration uses `ADMIN_USERS`, news write operations use `NEWS_WRITE`, and template seeding uses `TEMPLATES_WRITE`. The `require_permission` dependency already has a built-in superuser bypass, so superusers retain full access.

### Changed
- **Removed `pycountry` dependency** — full country names are now returned directly by ip-api.com; there is no longer any local country code mapping to maintain.

## [v2.135.0] - 2026-03-22

### Security
- **Auth rate limiting now correctly keys on real client IP** — requests were previously bucketed on `127.0.0.1` (the nginx proxy address) instead of the actual client IP, meaning all users shared a single rate limit slot. Login, forgot-password, and device trust lookups now read `X-Forwarded-For` correctly.
- **Admin ban/unban endpoints validate IP format** — inputs are now validated as proper IP addresses before being passed to fail2ban or firewalld subprocesses.
- **Log grep uses fixed-string matching** — the ban detail endpoint now uses `grep -F` to treat the IP as a literal string rather than a regex pattern.
- **Session terminate endpoint verifies ownership** — terminating a session now confirms the session belongs to the requesting user before ending it.
- **News cleanup restricted to superusers** — the manual article/video cleanup endpoint previously accepted any authenticated user; it now requires superuser privileges.
- **Session policy endpoints accept typed input** — replaced the unvalidated `dict` body with a typed model enforcing field ranges.
- **Article domain error no longer reveals allowed domains** — the error message for unsupported article sources is now generic.
- **Content-Security-Policy and HSTS headers added** — applied at the application layer as a fallback alongside the existing nginx-level headers. Deprecated `X-XSS-Protection` header removed.
- **Refresh bans endpoint rate-limited** — the admin ban snapshot refresh is now limited to once per 10 seconds to prevent rapid subprocess spawning.

### Added
- **Full country names in Security ban reports** — the admin security panel now shows full country names (e.g., "United States", "Russian Federation") instead of 2-letter ISO codes. Powered by `pycountry`; country data is maintained externally.

### Fixed
- **Test suite SQLite/PostgreSQL compatibility** — router tests were crashing since the v2.132.0 domain schema migration because in-memory SQLite doesn't support PostgreSQL named schemas. The test engine now uses `schema_translate_map` to flatten schemas for SQLite. Tests also print which database backend they are running against.

### Changed
- **Admin geo-lookup parallelized** — observer IP geolocation lookups in the user list now run concurrently instead of serially, improving load time when many observer sessions are active.
- **Git version endpoint cached** — `/api/version` and `/api/health` now cache the git tag result for 30 seconds instead of spawning a subprocess on every poll.
- **Architecture documentation updated** — docs now reflect the current 33 routers, 65 models across 6 PostgreSQL schemas, APScheduler tiered background task architecture, and all Phase 3 seam modules.

## [v2.134.4] - 2026-03-22

### Added
- **Picture-in-Picture for video player on iOS** — videos now float as a PiP window automatically when you switch to Maps or another app. Enabled by adding `playsinline=1` to the YouTube embed URL, which combined with the existing `allow="picture-in-picture"` iframe attribute triggers iOS's automatic PiP on app switch.

## [v2.134.3] - 2026-03-22

### Fixed
- **Video player starts unmuted on iOS** — previously forced to muted autoplay; now lets iOS handle autoplay policy naturally (video starts paused, plays with sound when you tap play).
- **Volume slider hidden in video player on iOS** — consistent with TTS player; use hardware volume buttons.
- **`playsinline` added to YouTube iframe** — improves background audio continuation when switching apps on iOS.

## [v2.134.2] - 2026-03-22

### Changed
- **Volume slider hidden on iOS** — iOS ignores software volume control (`audio.volume`); the slider has been removed on iOS devices to avoid confusion. Use hardware volume buttons as usual.

## [v2.134.1] - 2026-03-22

### Fixed
- **TTS continues playing while in other apps (iOS)** — the Web Audio API GainNode was permanently connected to the audio element via `createMediaElementSource`, which iOS suspends when the app is backgrounded, stopping playback. Removed the GainNode routing entirely; audio now plays through the standard `<audio>` element which iOS allows to continue in background. Volume slider continues working on desktop and Android. iOS users control volume with hardware buttons as usual.

## [v2.134.0] - 2026-03-22

### Added
- **TTS background audio recovery** — audio resumes immediately when returning from another app. Handles AudioContext interruptions from phone calls, navigation prompts, and app switches. The keepalive audio session is also restored on return so there are no gaps between articles.

## [v2.133.2] - 2026-03-22

### Fixed
- **APScheduler startup crash** — reverted Redis jobstore back to the default in-memory store. `RedisJobStore` pickles the full job object including bound-method targets; monitor objects hold `threading.Lock` attributes that cannot be pickled, causing `TypeError: cannot pickle '_thread.lock' object` on every startup. The in-memory store requires no pickling and interval-based jobs tolerate missing one cycle at restart.

## [v2.133.1] - 2026-03-22

### Fixed
- **`SimpleCache.get_or_fetch` cross-loop safety** — `_in_flight` futures are now keyed by `(loop_id, cache_key)` instead of a plain string. Previously, if the main event loop put a Future in-flight for key `X` and the secondary event loop checked the same key, it would `await` the wrong loop's Future and raise `RuntimeError: Task got Future attached to a different loop`. The fix gives each event loop its own in-flight slot; the single-flight guarantee within a loop is preserved.
- **`PersistentPortfolioCache` lock type** — `asyncio.Lock` replaced with `threading.Lock`. The lock-guarded blocks contain only sync file I/O (no `await`), so `asyncio.Lock` was both incorrect (raised `TypeError` on `with` usage) and unnecessary.

## [v2.133.0] - 2026-03-22

### Added
- **Redis rate limiting** — login, signup, MFA, and password-reset rate limit attempts now persist to Redis (INCR + TTL fixed window) instead of PostgreSQL, reducing DB load and enabling cross-process consistency. In-memory fast path is preserved; Redis is used for warming the cache after restart.
- **Redis WebSocket broadcast** — `RedisBroadcast` backend publishes WebSocket fan-out messages (`send_to_user`, `send_to_room`, `broadcast_order_fill`) to Redis pub/sub channels (`ws:user:*`, `ws:broadcast`, `ws:room`). A per-process subscriber loop dispatches incoming messages to the local `WebSocketManager`. Enables multi-process fan-out in Phase 3 with no call-site changes.
- **Full broadcast backend migration** — all remaining call sites (`sell_executor`, `buy_executor`, `limit_order_monitor`, `perps_monitor`, `friend_notifications`, `game_ws_handler`, `chat_ws_handler`) now use `broadcast_backend` instead of calling `ws_manager` directly for fan-out. Connection registry calls (`connect`, `disconnect`, `get_connected_user_ids`) remain on `ws_manager`.

## [v2.132.1] - 2026-03-22

### Added
- **Health check endpoint** (`GET /api/health`) — returns `{status, version, started_at}` as JSON. Used for service monitoring and deploy verification.

## [v2.132.0] - 2026-03-22

### Changed
- **Domain-scoped PostgreSQL schemas** — all 63 database tables are now organized into six named schemas (`auth`, `trading`, `reporting`, `social`, `content`, `system`), replacing the flat `public` schema. Zero behavior change for the running app. Each schema groups related tables by domain, laying the groundwork for future service extraction where each schema can become an independent database with no additional data migration. Cross-schema foreign keys are preserved and enforced by PostgreSQL.

## [v2.131.0] - 2026-03-22

### Added
- **ServiceRegistry** (`app/registry.py`) — single injection point for all four service backend abstractions: `event_bus`, `broadcast`, `rate_limiter`, and `credentials`. Expose via `Depends(get_registry)` so routers can receive all backends through one object instead of importing singletons directly. The registry is the Phase 3 swap point: replacing `_default_registry` at startup switches all four backends (NATS, Redis, remote credentials service) simultaneously with no router changes. All fields hold today's in-process / local implementations — zero behavior change.

## [v2.130.0] - 2026-03-22

### Added
- **CredentialsProvider abstraction** (`app/services/credentials_provider.py`) — `CredentialsProvider` protocol and `LocalCredentialsProvider` implementation wrap `get_exchange_client_for_account()`. Callers can pass an existing DB session (`db=`) or a session factory (`session_maker=`); when neither is provided, the default pool is used automatically. Zero behavior change today. The seam enables a future `RemoteCredentialsProvider` swap for a credentials microservice with no call-site changes. `RemoteCredentialsProvider` stub documents the Phase 3 HTTP API architecture.

## [v2.129.0] - 2026-03-22

### Added
- **Rate limit backend abstraction** (`app/auth_routers/rate_limit_backend.py`) — `RateLimitBackend` protocol and `PostgresRateLimitBackend` implementation wrap the three PostgreSQL persistence helpers in the rate limiter (`record_attempt`, `count_recent`, `cleanup`). Zero behavior change today. The seam enables a future `RedisRateLimitBackend` swap for atomic cross-process rate limiting (`INCR` + `EXPIRE` per key) with no changes to call-site code. `RedisRateLimitBackend` stub documents the Phase 3 Redis key pattern and raises `NotImplementedError` until implemented.

## [v2.128.0] - 2026-03-22

### Added
- **WebSocket broadcast abstraction** (`app/services/broadcast_backend.py`) — `BroadcastBackend` protocol and `InProcessBroadcast` implementation wrap the existing WebSocket manager's fan-out methods (`broadcast`, `send_to_user`, `send_to_room`, `broadcast_order_fill`). Zero behavior change today. The seam enables a future `RedisBroadcast` swap for multi-process WebSocket fan-out with no changes to call-site code. `RedisBroadcast` stub documents the Phase 3 architecture and raises `NotImplementedError` until implemented.

## [v2.127.0] - 2026-03-22

### Added
- **In-process event bus** (`app/event_bus.py`) — lightweight pub/sub layer for domain events. Publishers fire `order.filled` events on every buy, sell, partial fill, and limit-order close; `bot.started` and `bot.stopped` on bot control actions. On each fill, the `auto_buy_monitor` and `rebalance_monitor` APScheduler jobs are triggered immediately (via `job.modify(next_run_time=now)`) instead of waiting up to 10–30 seconds for their next scheduled tick. Polling fallback stays intact — events are an additive latency optimization, not a replacement. Interface-swappable for NATS/Redis Streams when multi-process scale demands it.

## [v2.126.1] - 2026-03-22

### Fixed
- **TTS shutdown test** — updated test to match the APScheduler refactor: removed patches for services that no longer exist as module-level names in `main.py` after the v2.126.0 background task migration.

## [v2.126.0] - 2026-03-22

### Changed
- **APScheduler replaces hand-rolled background loops** — all Tier 2 and Tier 3 background tasks (auto-buy monitor, rebalance monitor, transfer sync, account snapshot, ban monitor, report scheduler, content refresh, domain blacklist, debt ceiling monitor, coin review, trading pair monitor) and all 8 database/memory cleanup jobs now run under APScheduler's `AsyncIOScheduler`. Each job function runs once per call; scheduling intervals and staggered startup delays are configured centrally in `app/scheduler.py`. Eliminates `while True: await asyncio.sleep(N)` loops and the secondary event loop's `schedule()` calls.
- **Service singletons relocated** — `auto_buy_monitor`, `rebalance_monitor`, and `trading_pair_monitor` singletons moved from `main.py` into their respective service modules to eliminate circular imports with the scheduler.

## [v2.125.14] - 2026-03-22

### Fixed
- **PaperTradingClient cross-loop crash** — `_reload_balances`, `_save_balances`, and `calculate_aggregate_quote_value` were importing and using `async_session_maker` (the main event loop's connection pool) directly. When `RebalanceMonitor` on the secondary loop called these methods for paper trading accounts (3, 9, 11), the secondary loop tried to `await main_pool_queue.get()` and crashed with "Queue is bound to a different event loop". Fixed by adding a `session_maker` parameter to `PaperTradingClient.__init__` and using it in all three methods (falls back to global for non-injected callers). `exchange_service.py` now passes `session_maker` when constructing `PaperTradingClient` so the correct pool is used.

## [v2.125.13] - 2026-03-22

### Fixed
- **SimpleCache threading.Lock** — `api_cache._lock` was an `asyncio.Lock` that would bind to the main event loop on first use. Any secondary-loop task calling `calculate_aggregate_quote_value()` (which reads from `api_cache`) would crash with "Future attached to a different loop". All internal operations in `SimpleCache` are pure dict reads/writes with no `await` inside the lock, so converting to `threading.Lock` is safe and loop-agnostic.
- **ByBitClient rate-limit lock** — `_rate_lock` converted from `asyncio.Lock` to `threading.Lock` using the slot-reserve pattern: compute wait and advance `_last_request_time` inside the lock, then `await asyncio.sleep(wait)` outside it. ByBit client is now callable from either event loop.
- **PropGuardClient per-account lock** — replaced a fixed `asyncio.Lock` stored at construction time (bound to the creation loop) with a lazy lookup keyed by `(id(current_loop), account_id)`. Each event loop gets its own lock per account; no cross-loop sharing.
- **PaperTradingClient per-account balance lock** — same loop-aware `(id(loop), account_id)` key pattern as PropGuardClient.
- **Test fixes** — updated pre-existing tests that asserted `_rate_lock` was `asyncio.Lock` (now correctly checks for `threading.Lock`); updated `TestAccountLock` tests to run inside an event loop (required since `_get_account_lock` calls `asyncio.get_running_loop()`). Added 8 new tests for `SimpleCache` lock thread safety and 6 new tests for `ByBitClient` rate lock.
- **pybit package** — was listed in `requirements.txt` but not installed. Installed via pip.

## [v2.125.12] - 2026-03-22

### Fixed
- **Completed background monitor loop migration** — auto-buy, rebalance, trading-pair, account snapshot, and transfer sync monitors have been moved to the secondary event loop. This was previously blocked by two module-level `asyncio.Lock` objects (`_rate_lock` in the public market data module and `_exchange_client_lock` in the exchange client service) that would bind to whichever loop first acquired them and then crash when called from a different loop. Both locks have been converted to `threading.Lock`, making them loop-agnostic. Async work (DB queries, HTTP requests) continues to happen outside the lock using `asyncio.sleep`, so timing and behaviour are unchanged.
- **PropGuardClient now uses the correct DB pool when called from the secondary loop** — the session maker is now threaded through the exchange client factory so prop firm accounts' drawdown checks run against the secondary loop's connection pool rather than the main pool.

## [v2.125.11] - 2026-03-22

### Fixed
- **Background monitor cross-loop crash** — auto-buy, rebalance, trading-pair, account snapshot, and transfer sync monitors have been moved back to the main event loop. Moving them to the secondary loop caused `RuntimeError: Future attached to a different loop` and `asyncio.Lock is bound to a different event loop` crashes because helper functions they call deep in the stack (aggregate value calculation, exchange client cache, public price fetch) share module-level asyncio locks that bind to whichever loop first acquires them. These monitors will be fully migrated in a future phase once all shared asyncio primitives in their call chains are converted to threading-safe equivalents.
- **Content refresh service remains on secondary loop** — it does not call the affected helpers and continues to run on the dedicated secondary event loop with its own DB pool.

## [v2.125.10] - 2026-03-22

### Fixed
- **Connection pool exhaustion** — reduced PostgreSQL connection pool sizes across all three pools (main 12→8, read 6→4, secondary 5→3 max connections) to comfortably fit within the server's `max_connections=25` limit. The previous budget of 23 max connections plus superuser reserved slots caused sporadic `TooManyConnectionsError` errors.
- **Leaked idle-in-transaction connections** — set `idle_in_transaction_session_timeout=15min` at the PostgreSQL level so connections left open by service restarts are automatically terminated rather than accumulating until they exhaust the connection limit.

## [v2.125.9] - 2026-03-22

### Changed
- **Exchange client rate limiter is now loop-agnostic** — the per-client rate limit lock was changed from `asyncio.Lock` to `threading.Lock`. This eliminates a subtle crash where a cached Coinbase client (whose lock was acquired first by the main loop) would raise `RuntimeError: is bound to a different event loop` if a secondary-loop task tried to use it. The actual rate-limiting sleep still uses `await asyncio.sleep()` so the 150 ms request spacing is unchanged.
- **5 more background services moved to the secondary event loop** — auto-buy monitor, portfolio rebalance monitor, trading pair monitor, account snapshot capture, and transfer sync now run on the dedicated secondary asyncio loop (with its own DB pool) instead of the main trading loop. This was unblocked by the threading.Lock fix above. Content refresh service (news and video fetching) also moves to the secondary loop now that its database calls use the secondary session maker.
- **Thread-safe in-memory timer maps** — auto-buy and rebalance monitors now protect their `_account_timers` dict with a `threading.Lock`. The main-loop cleanup job and the secondary-loop monitors accessed this dict from different threads without synchronization.

## [v2.125.8] - 2026-03-21

### Changed
- **Batch cleanup jobs now run on a dedicated secondary event loop** — 12 background tasks (all 8 database cleanup jobs, ban monitor, report scheduler, coin review scheduler, domain blacklist, and debt ceiling monitor) have been moved off the main trading event loop onto a separate secondary loop running in a daemon thread. The secondary loop has its own smaller DB connection pool (`size=3, overflow=2 = 5 max connections`), so cleanup queries no longer compete with order fills and bot monitoring for connection slots. The remaining 15 tasks stay on the main loop because they use the shared exchange client cache (whose asyncio locks are bound to the main loop).

## [v2.125.7] - 2026-03-21

### Changed
- **Report and account value reads now use a dedicated connection pool** — analytics queries (report history, goal trends, account value charts, daily activity) are routed to a separate read-only connection pool (`size=4, overflow=2 = 6 max connections`) instead of competing with trading writes for the shared pool (`size=8, overflow=4 = 12 max connections`). Market metrics history queries also use the read pool. No infrastructure change — both pools point at the same database.

## [v2.125.6] - 2026-03-21

### Changed
- **Banned IP geo lookups now run concurrently** — when the ban monitor refreshes and has many uncached IPs, geolocation requests (country, ISP, city) are now fired in parallel (up to 10 at a time) instead of one at a time. This makes the first load after a restart roughly 10× faster. Subsequent refreshes are instant due to the existing per-process cache.

## [v2.125.5] - 2026-03-21

### Changed
- **TTS file I/O offloaded to a dedicated thread pool** — reading and writing audio files (MP3 cache) no longer blocks the async event loop. A bounded 2-worker `ThreadPoolExecutor` handles all disk operations, preventing slow file writes from stalling trading API responses or bot monitoring. Note: audio generation itself (`edge_tts`) was already async and unaffected.

## [v2.125.4] - 2026-03-21

### Fixed
- **Bot config fields no longer auto-fill defaults when you backspace** — clearing any numeric field (Max Concurrent Deals, Safety Orders, Price Deviation, Take Profit %, Slippage Guard, etc.) now leaves the field empty so you can type the value you want. The default is only applied when you leave the field blank and move focus away. All 14 numeric inputs in the bot editing modal were updated.
- **Banned IP country and ISP/provider data no longer shows as "Unknown"** — geo lookups (via ipinfo.io) are now cached per IP for the lifetime of the process. Previously, every monitor refresh re-queried all IPs at once, hitting ipinfo.io's rate limit and causing most entries to return empty. Data is now looked up once and reused on subsequent refreshes.
- **Banned IP list: group by ISP/Provider** — added "ISP" as a grouping option alongside Country and Jail.

## [v2.125.3] - 2026-03-21

### Fixed
- **Bot save no longer times out when many pairs are active** — database connection pool increased from 8 to 12 connections. When the multi-pair bot monitor ran at the same time as an HTTP request, the pool would exhaust and cause a 30-second timeout. Also reduced the wait time before a connection request fails from 30s to 10s for faster error feedback.

## [v2.125.2] - 2026-03-21

### Added
- **Banned IP list: search, sort, and group** — search box filters across IP, country, org, jail, city, and hostname in real time and shows a result count. Column headers are clickable to sort asc/desc. Group by Country or Jail adds section headers with member counts. All controls operate across the full dataset before pagination.

## [v2.125.1] - 2026-03-21

### Fixed
- **Banned IP pagination no longer shows all page numbers** — replaced the full page list with a windowed control showing first/last pages, current page ±2, and `…` gaps. Much cleaner on mobile.

## [v2.125.0] - 2026-03-21

### Added
- **Disposable email warning at registration** — the signup form now detects known throwaway/disposable email providers and auto-generated-looking addresses. Users are shown a clear warning that accounts registered with throwaway emails are likely to be banned along with their IP, and must explicitly acknowledge before proceeding. Detection uses both a curated list of known disposable mail services and a local-part entropy heuristic for obviously bot-generated addresses (e.g. `1qe9k827b1@gmail.com`). Legitimate addresses like `james194@gmail.com` are never flagged.

## [v2.124.2] - 2026-03-21

### Fixed
- **Indicator logs now load correctly for all bots** — fetching logs with a time filter crashed with a timezone mismatch error, causing the indicator logs tab to show nothing even when logs existed

## [v2.124.1] - 2026-03-21

### Added
- **Admin Security chart toggle** — ban type and country distribution charts now support a bar/pie view toggle

## [v2.124.0] - 2026-03-21

### Fixed
- **Safety order chart lines now accurate** — lines previously used wrong config fields and ignored `dca_target_reference`, causing visible SOs at wrong prices. Now mirrors backend calculation exactly: geometric step scale, correct reference price (average/base_order/last_buy), and skips already-filled SOs
- **Portfolio Management total value includes altcoins** — paper trading accounts with altcoin balances (AMP, IOTX, SOL, etc.) now show the correct total instead of only counting USD/BTC/ETH/USDC
- **Portfolio Management balance chart shows physical holdings** — live accounts previously showed 99% USD for users who physically hold 99% BTC (the old view showed market-deployment allocation, not actual asset holdings)
- **Account Value Over Time BTC portion no longer shrinks** — the By Quote Currency chart previously only tracked free BTC balance, which decreases as bots deploy capital into positions. Now tracks aggregate quote value (free balance + open position values), keeping the BTC portion stable as bots work
- **Admin nav icons corrected** — Users tab now shows a single-person icon; Groups tab shows a multi-person icon

## [v2.123.1] - 2026-03-15

### Security
- **Intrusion detector now scans GET query strings** — previously only POST/PUT/PATCH bodies were scanned, leaving GET-based SQL injection and XSS undetected
- **Fail2ban nginx-exploit filter catches all HTTP methods** — HEAD, PUT, DELETE, PATCH, OPTIONS now detected (previously only GET/POST)
- **Instant ban on first exploit probe** — lowered nginx-exploit threshold from 3 attempts to 1 (these patterns are never legitimate)
- **New fail2ban jail for malformed requests** — repeated 400 errors (protocol abuse, host header probing) now trigger a ban
- **Unknown hostnames rejected** — nginx default server block drops connections to unrecognized domains with no response (444)

### Fixed
- **SSRF false positive log spam** — image downloader no longer warns on `undefined` or empty URLs every 30 minutes; quietly skips them instead

## [v2.123.0] - 2026-03-15

### Added
- **450 new unit tests** across 14 test files covering previously untested modules: auth rate limiters, auth helpers, indicator params, convert API, public rate limiting, article content service, ban monitor, chat WebSocket handler, ByBit WebSocket, price feed base/DEX, templates router, strategies router, and PDF generator
- **Navigation bar separators** — added visual dividers between Reports/Games and Social/Settings for clearer menu grouping

### Fixed
- **BS card game facedown cards** — opponent cards now render at proper mini-card size instead of appearing as thin lines
- **Zero-quantity order book crash** — `OrderBook.get_execution_price()` now returns `None` instead of raising `ZeroDivisionError` when called with zero quantity
- **Strategy parameter metadata loss** — `paper_trading_only` field on `simulate_slippage` param is now preserved in the `StrategyParameter` model instead of being silently dropped

## [v2.122.3] - 2026-03-14

### Fixed
- **Paper trading sell quantity drift** — multiple bots sharing an account could deplete the simulated wallet, causing sells to be capped below the position's actual holdings; the sell executor now tops up the paper wallet to ensure full position sells
- **RSI Runner missing take-profit** — both RSI Runner bots (BTC and USD) now have a 2% minimum take-profit target to prevent conditional TP from triggering at a net loss

## [v2.122.2] - 2026-03-14

### Added
- **Ban detail modal** — click any banned IP to see attack categories with percentage bars, total request count, and sample request log entries

## [v2.122.1] - 2026-03-14

### Added
- **Security report tab** — visual breakdown of bans by jail type (bar chart), country distribution, and top ISPs with summary stats
- **Banned IP pagination** — 10 per page with page navigation

### Changed
- **Color-coded jail badges** — SSH (amber), nginx-exploit (red), intrusion detection (purple) throughout the Security tab
- **Replaced misleading "Total Failed" stat** with "Jails Active" count

## [v2.122.0] - 2026-03-14

### Security
- **Application-level intrusion detection** — new ASGI middleware scans POST/PUT/PATCH request bodies for injection attacks (SQL, XSS, NoSQL, LDAP, SSRF, template injection, XXE, shell commands, encoded variants); 2 attempts in 1 hour triggers automatic 2-year IP ban via fail2ban
- **Expanded nginx exploit filter** — added detection for .env file enumeration, WordPress deep scans, backup file probes, admin panel discovery, API framework scanners, Docker registry access
- **24 malicious IPs banned** — SSH brute-force (8), web exploit scanning (16), including Azure/DigitalOcean/Contabo-hosted botnets

## [v2.121.0] - 2026-03-14

### Added
- **Chat-to-game lobby** — game controller icon in the chat input bar lets you start a multiplayer game with everyone in the channel; pick a game from the searchable list, a lobby is created, and all channel members get an invite notification

## [v2.120.0] - 2026-03-14

### Added
- **Server-side game score types** — scores now support types (high_score, fastest_time, level_reached) with per-type comparison logic (fastest_time: lower wins)
- **Score display on game cards** — hub shows formatted scores with appropriate icons (Trophy for points, Timer for time) and labels per game
- **Shalas fastest win tracking** — game card shows fastest VS win time
- **9 games tagged with score types** — Snake, 2048, Centipede, Dino Runner, Space Invaders, Lode Runner, Plinko (high_score); Minesweeper, Shalas (fastest_time)

### Fixed
- **Shalas 7 card not working in 2-player** — missing `choose_seven_action` UI; game would enter dead state after playing a 7
- **Shalas top row touch targets** — overlapping card layers intercepted touch events; increased hit areas and disabled pointer events on covered cards

## [v2.119.1] - 2026-03-14

### Fixed
- **Plinko bet exploit** — bet amount is now locked to each ball at drop time; changing the bet while balls are in flight no longer affects their payout

## [v2.119.0] - 2026-03-14

### Added
- **Lode Runner spectator mode** — watch your opponent's game live after being eliminated in race mode, with full canvas rendering and spectate navigation
- **Lode Runner state broadcasting** — game state now broadcasts to opponents during multiplayer (was declared but never called)

### Fixed
- **Giphy search returning no results** — chat GIF search was hitting `/api/api/chat/giphy/` (double prefix); fixed to use correct path
- **Lode Runner mobile controls too tight** — wider spacing between d-pad buttons and dig controls to prevent accidental presses

## [v2.118.0] - 2026-03-14

### Added
- **Multiplayer final scores** — race result modal now shows both players' scores side-by-side with color-coded win/loss indicators across all 40 multiplayer games
- **Chat auto-open** — admin messaging from the Users tab now navigates to the Chat page and automatically opens the conversation

### Fixed
- **Dino Runner spectator crash** — fixed React error #300 (max update depth exceeded) caused by `setDisplayScore` firing at 60fps inside the requestAnimationFrame loop; now only updates on actual score changes
- **Observer login locations** — admin user list uses RBAC group membership (Observers) instead of email prefix for identifying shared accounts

## [v2.117.0] - 2026-03-14

### Added
- **Admin messaging** — admins can message any user directly from the Users tab, creating official admin DM channels that don't require friendship
- **Admin display name** — admins can set a separate display name for official communications (e.g., "Louis" instead of "Louis Romero"), configurable in Settings
- **Admin badge** — verified shield icon on admin messages and members, server-provided and impossible to spoof via display names
- **Observer login tracking** — admin Users tab shows active login locations (IP + city/region/country/ISP) for shared accounts (Observers group) with support for multiple simultaneous sessions
- **Last login timestamp** — shown for all users in the admin Users tab

### Fixed
- **Dashboard chart markers** — win/loss arrows no longer disappear after portfolio PnL calculations finish loading

## [v2.116.0] - 2026-03-14

### Added
- **Admin Security tab** — view all fail2ban banned IPs with full geolocation (city, region, country, ISP, hostname) sourced from ipinfo.io
- **Ban monitor background job** — queries fail2ban daily and caches results; admin can force-refresh anytime
- **Admin unban** — unban individual IPs directly from the Security tab with confirmation dialog
- **Admin user filter** — "Show Offline" toggle on the Users tab (off by default, showing only online users)
- **Responsive admin tabs** — icons-only on mobile, labels on larger screens

### Changed
- **Donation goal is now quarterly** ($300/quarter instead of $100/month) — popup shows once per quarter
- **Donation self-report auto-dismisses** — submitting a donation report suppresses the popup for the rest of the quarter

## [v2.115.0] - 2026-03-14

### Added
- **Donation support system** — monthly donation goal meter with progress bar, self-report workflow (user reports → admin confirms), and admin management tab
- **Donation modal** — polite popup for logged-in users showing crypto addresses with QR codes (BTC, USDC), payment app links (PayPal, Venmo, CashApp), and self-report form
- **Admin donations tab** — manage monthly goal target, confirm/reject self-reported donations, manually add donations, filter by status
- **QR codes for crypto donations** — Bitcoin and USDC addresses render scannable QR codes in the donation modal
- **Venmo and CashApp** donation options added alongside existing BTC, USDC, and PayPal

## [v2.114.1] - 2026-03-14

### Added
- **Live admin user presence** — admin users list updates online/offline status in real-time without page refresh

### Changed
- **Admin presence broadcasts use proper RBAC** — live online/offline updates sent only to users with the `admin:users` permission via the full RBAC chain (groups → roles → permissions), not just superusers

## [v2.114.0] - 2026-03-14

### Added
- **Friend online toast notifications** — real-time toast when a friend comes online, pushed via WebSocket instead of polling
- **Friend request accepted toast** — notifies you instantly when someone accepts your friend request
- **Admin online indicator** — user list in the admin panel now shows a green dot for online users and gray for offline
- **Social toast type** — new cyan-themed toast style for friend/social notifications

## [v2.113.0] - 2026-03-13

### Added
- **Cheat (aka BS) card game** — Classic bluffing card game with 1 human vs 3 AI opponents, full challenge/reveal system, and strategic AI that bluffs and calls BS based on hand analysis
- **Cheat multiplayer VS mode** — 2-4 player real-time matches via WebSocket with host-authoritative game state, plus first-to-win race mode
- **Cheat engine test suite** — 21 unit tests covering game creation, card play, BS calls, challenge resolution, AI behavior, and win conditions

## [v2.112.0] - 2026-03-13

### Added
- **SSRF protection** — URL fetching for news images and article content now validates targets, blocking internal IPs, localhost, and AWS metadata endpoints
- **Exchange API circuit breaker** — Coinbase API calls now use a circuit breaker pattern (5-failure threshold, 60s recovery) to stop hammering the API during outages
- **Public endpoint rate limiting** — Unauthenticated API endpoints (ticker, candles, coin icons, brand, etc.) are now rate-limited to 120 requests/min per IP
- **Game WebSocket rate limiting** — Game message handler now enforces per-user rate limiting (30 msgs/5 sec), mirroring existing chat rate limiting
- **Encryption key rotation** — Switched from Fernet to MultiFernet, supporting comma-separated keys in ENCRYPTION_KEY for zero-downtime key rotation
- **Coin icon cache protection** — Disk cache capped at 5,000 icons to prevent fill attacks from symbol enumeration

### Fixed
- **Memory leak: monitor account timers** — Auto-buy and rebalance monitors now prune `_account_timers` entries for deleted/deactivated accounts during the 5-minute sweep
- **Memory leak: orphaned pending orders** — Auto-buy monitor pending orders older than 30 minutes are now cleaned up automatically
- **Memory leak: friend request rate limiter** — Expired entries from the friend request rate limiter dict are now pruned by the periodic sweep
- **Memory leak: portfolio conversion tasks** — `cleanup_old_tasks()` is now called by the periodic sweep (was defined but never invoked)

### Changed
- Documentation updated to reflect PostgreSQL migration, new middleware, resilience patterns, and current model/migration counts

## [v2.111.1] - 2026-03-13

### Fixed
- **Memory leak: fire-and-forget async tasks** — Rate limiter and market metrics DB writes now use bounded task tracking (max 100/50 pending) with automatic backpressure, preventing task pile-up during slow database periods
- **Memory leak: rate limiter tracking sets** — `_warmed` set capped at 10,000 entries and cleared when exceeded; stale empty dict keys now pruned during periodic cleanup
- **Memory leak: exchange client cache** — Monitor exchange cache now capped at 20 clients with overflow eviction
- **Memory leak: PIL image objects** — News image compression now explicitly closes PIL Image and BytesIO objects instead of relying on garbage collection
- **Memory leak: refresh token subscribers** — Frontend token refresh subscriber array capped at 50 to prevent unbounded growth during concurrent 401 responses
- **Periodic rate limiter pruning** — Rate limiter in-memory entries now pruned by the 5-minute cache sweep job even when no auth requests are incoming

## [v2.111.0] - 2026-03-13

### Added
- **Blackjack insurance and even money**: When the dealer shows an Ace, players can take insurance (half bet, pays 2:1 if dealer has blackjack) or even money (guaranteed 1:1 payout on natural blackjack)
- **Blackjack dealer peek**: Dealer checks for blackjack before players act on 10-value or Ace up cards, preventing splits/doubles into dealer blackjack
- **Plinko physics improvements**: Enhanced ball physics with variable bounce behavior, realistic pin interactions, and configurable risk levels

### Changed
- **Euchre multiplayer**: Improved trick evaluation logic and multiplayer state sync for more reliable 4-player games
- **Canasta multiplayer**: Better meld validation and multiplayer hand synchronization
- **Spades multiplayer**: Improved bid tracking and score display in VS mode

### Fixed
- **Memory leak: unbounded in-memory caches** — Added periodic 5-minute sweep of all in-memory caches (token prices, candle data, indicator history, game rooms, chat rate-limit tracking) to prevent RAM exhaustion on the 1GB server
- **Memory leak: stale WebSocket connections** — Added automatic detection and cleanup of WebSocket connections that silently disconnected without triggering cleanup handlers
- **Memory leak: frontend timer leaks** — Fixed uncancelled setTimeout chains in article reader auto-advance and version check notifications that accumulated on navigation
- **Memory leak: unbounded voice cache** — Capped article voice preference cache at 200 entries to prevent unbounded localStorage and state growth

### Security
- **Rate limiting hardened**: Authentication rate limiter rewritten with hybrid in-memory + database persistence — failed login tracking now survives app restarts
- **API docs disabled**: Swagger/ReDoc/OpenAPI endpoints removed from production
- **Backend bound to localhost**: uvicorn now listens on 127.0.0.1 only (nginx handles external traffic)
- **Error sanitization**: Trading endpoint no longer leaks raw exception details to clients
- **fail2ban protection**: Automated brute-force detection with incremental bans (1h → 4h → 24h → 2 years)
- **Journal log cap**: systemd journal capped at 200MB to prevent disk exhaustion

## [v2.110.0] - 2026-03-13

### Added
- **VS mode for 11 card games**: Gin Rummy, Crazy Eights, Go Fish, War, Cribbage, Speed, Hearts, Spades, Euchre, Bridge, and Canasta now support real-time VS multiplayer — 21 games total with VS mode
- **4-player VS with AI partners**: Hearts, Spades, Euchre, Bridge, and Canasta run as 2 humans + 2 AI opponents with host-authoritative state sync
- **Real-time Speed VS**: Speed multiplayer runs in real-time (not turn-based) — both players play simultaneously
- **GIF support in chat**: Send GIFs in group chat via built-in Giphy search and trending picker — GIF button next to send, with search, trending view, and inline rendering
- **Giphy proxy endpoints**: Backend proxies Giphy API calls to keep the API key server-side (`/api/chat/giphy/search`, `/api/chat/giphy/trending`)
- **Memory VS mode**: Host-authoritative card matching with synchronized flips and turn-based scoring
- **Lobby chat**: Players can chat while waiting in the game lobby
- **Lobby configuration**: Host can change game difficulty and multiplayer mode from within the lobby
- **Ghost room cleanup**: Stale rooms from server restarts are automatically detected and cleared

### Fixed
- **Memory card flip race condition**: Rapid clicks can no longer sneak in extra card flips during match/mismatch resolution — refs update synchronously with state
- **Mode propagation**: Multiplayer mode now correctly propagated in all room messages so guests render the right game variant

## [v2.109.0] - 2026-03-12

### Added
- **Simultaneous start**: Multiplayer race/survival games now require both players to ready up before a 3-2-1 countdown begins — prevents one player from gaining an advantage by starting early
- **Shared seed for identical courses**: Dino Runner multiplayer uses a seeded PRNG so both players face the same procedurally-generated obstacles, weather, and biomes
- **Countdown overlay**: Animated Ready/Waiting/3-2-1-GO! overlay for multiplayer sync-start games

### Fixed
- **Dino Runner spectator bug**: Loser can now properly spectate the winner in survival mode — self-echo of `race_finished` message no longer bypasses the skull dismiss flow

### Changed
- **Framework-level sync-start**: Dino Runner, Centipede, and Space Invaders all use the new `syncStart` option from `useRaceMode` — any future race/survival game gets it automatically
- **Dino Runner engine**: All randomness now routes through a pluggable RNG function, enabling deterministic replay and shared multiplayer courses

## [v2.108.0] - 2026-03-12

### Added
- **Blackjack VS Mode**: Two human players sit at the same table with a shared dealer and shoe — host-authoritative turn-based play with simultaneous betting, split, double down, and real-time state sync
- **Friends' Lobbies**: Game Hub now shows friends' open lobbies at the top — one click to join their game
- **Room reconnection**: Navigating away from a game and returning automatically rejoins your active room
- **Back to Lobby**: After a multiplayer game ends, players can return to the lobby together for a rematch without recreating the room
- **Room check on mount**: Multiplayer games detect and restore existing room state on page load

### Changed
- **Multiplayer infrastructure**: Stale room cleanup, auto-leave when switching games, buffered join results that survive page navigation
- **WebSocket hardening**: Duplicate connection prevention, stale socket cleanup, oversized message type logging
- **RaceOverlay**: Debounced disconnect overlay (1.5s delay prevents flash), survival spectator timing fixes
- **Game history endpoint**: Moved detail endpoint after `/scores` and `/visibility` to prevent path capture conflicts

### Fixed
- **Survival spectator race condition**: Guard prevents 'won' result from being overwritten by near-simultaneous opponent death
- **WebSocket reconnect**: Stale socket handlers no longer fire after a new connection replaces them

## [v2.107.0] - 2026-03-11

### Added
- **Social:chat permission**: Chat and friends features now use a dedicated `social:chat` permission, separate from `games:multiplayer` — users can message friends without needing game permissions
- **WebSocket RBAC enforcement**: Chat WebSocket messages now require `social:chat` permission, closing a bypass where observers could send messages via WebSocket
- **Chat send rate limiting**: WebSocket message sends are throttled (10 per 5 seconds) to prevent flooding
- **Friend request rate limiting**: Limited to 20 friend requests per hour to prevent spam
- **Blocked user message filtering**: Messages from blocked users are no longer delivered in group channels

### Changed
- **ChatPanel modularized**: Split from 1142-line monolith into 5 focused components (MessageBubble, ChatInput, MembersPanel, NewChatDialog, ChatPanel) — net reduction of ~300 lines
- **WebSocket manager optimized**: Replaced list-based connection tracking with dict-based O(1) lookups for connect, disconnect, and broadcast operations
- **Chat queries optimized**: Batch reaction loading, single-query DM lookup, joined unread counts — eliminates N+1 query patterns across 5 hot paths
- **User search includes superusers**: Superusers now appear in friend search results regardless of RBAC chain

### Fixed
- **Observer lock modals**: Chat and Social pages show proper "account required" lock modal for unauthorized users; floating social button is hidden entirely
- **WebSocket input validation**: All channelId/messageId fields are now type-validated to prevent type confusion attacks
- **Friends endpoint tests**: Fixed 23 pre-existing test failures caused by detached SQLAlchemy instances in RBAC dependency chain

### Security
- Chat WebSocket handler validates `social:chat` permission on every message (was previously unchecked)
- WebSocket message fields are coerced to expected types before processing
- Content validation added to WebSocket send/edit paths (defense-in-depth)
- ILIKE wildcards properly escaped in chat message search

## [v2.106.1] - 2026-03-11

### Added
- **Dedicated Chat page**: Chat now has its own top-level page in the navigation with a MessageSquare icon and unread badge, separate from the Social page

### Changed
- Social page now focuses on friends, game history, and tournaments — chat has been moved to its own page

## [v2.106.0] - 2026-03-11

### Added
- **Emoji reactions**: React to messages with 16 common emojis — see who reacted, toggle your own reactions on/off
- **Reply/quote messages**: Reply to a specific message with a quoted preview, keeping group conversations organized
- **Message search**: Search messages across all your channels or within a specific channel
- **@Mentions**: Type @ in the compose box for autocomplete of channel members — mentioned names are highlighted in blue
- **Pinned messages**: Admins and owners can pin important messages — view all pinned messages from the pin icon in the channel header
- **Online presence in chat**: Green dot next to online members in the members panel

## [v2.105.1] - 2026-03-11

### Added
- **Group of one**: Create group chats with no additional members — add friends later when ready
- **Delete group**: Group owners can permanently delete a group chat with confirmation dialog
- **Role delegation**: Group owners can promote members to admin or demote admins back to member
- **Self-leave**: Group members can leave a group chat at any time

## [v2.105.0] - 2026-03-11

### Added
- **Chat system**: Full real-time chat with DMs, group chats, and channels — send messages to friends, create group conversations, edit and delete messages, with typing indicators and read tracking
- **Toast notifications for chat**: Incoming messages show a notification with sender name and message preview, displayed for a duration proportional to message length
- **Unread badges**: Social nav icon shows total unread message count; individual channels show their own unread counts
- **Channel management**: Create/rename groups, add/remove members, leave channels — with owner/admin role-based permissions
- **Chat message history**: Infinite scroll to load older messages, with 2000-character message limit (Discord standard)
- **Admin chat retention setting**: Configurable message retention period (default: keep forever)

### Changed
- Social page now features Chat panel at the top, above friends, game history, and tournaments

## [v2.104.0] - 2026-03-11

### Added
- **Spectator framework**: Eliminated players in race mode can now choose to spectate remaining players or return to the lobby — with left/right paging through multiple active players
- **Loser result flow**: Losers see a skull "You Lost!" overlay first, then choose between spectating or leaving — more satisfying UX
- **Friend lobby joining without invite**: See what game your friends are in and join their lobby directly from the Social page or floating friends panel — no invite needed. Lobby host gets a non-blocking toast notification
- **Social page**: New dedicated page (between Games and Settings in the nav bar) for friends, game history, and tournaments — all expanded by default
- **Shalas 2-player card powers**: 7 now offers a choice between picking a table card or pushing the entire discard pile to the opponent; 3 blocks the push; wildcards (2) and four-of-a-kind can act as either 7 or 3 in multiplayer — contributed by David Greene
- **Multiplayer race support for all games**: Every game with race mode now properly suppresses the game-over modal in multiplayer and passes leave/dismiss callbacks through the race overlay

### Changed
- Friends online endpoint now returns game room info (game ID, room status) so the UI can show what friends are playing
- Race overlay upgraded from z-40 to z-[110] to always render above game-over modals
- Social panels (friends, history, tournaments) moved from Games hub to dedicated Social page

### Fixed
- Invite acceptance race condition: accepting a game invite now reliably brings you to the friend's lobby even when the join response arrives before the lobby component mounts
- Sessions router crash on startup: fixed incorrect import (`get_current_active_user` → `get_current_user`)

*Thanks to David Greene for alpha testing the social gaming features and Shalas refinements.*

## [v2.103.0] - 2026-03-10

### Added
- **Shalas VS multiplayer**: Play Shalas head-to-head with a friend — both players see the same board but only their own hand, with Player 2 dealt an extra hand from the draw stack
- **Shalas 2-player engine**: Engine now supports full 2-player turn-based gameplay including the 7-Selector penalty (opponent takes 10 cards) and 3-Blocker defense

## [v2.102.0] - 2026-03-10

### Added
- **Multiplayer for 20 more games**: Hearts, Gin Rummy, Crazy Eights, Cribbage, Euchre, Go Fish, Blackjack, Bridge, Canasta, War, Spades, Memory, Centipede, Space Invaders, Lode Runner, Minesweeper, Sudoku, Wordle, Hangman, and Mahjong now all support race mode multiplayer
- **Reconnection framework**: Disconnected players get a 60-second window to rejoin their game automatically — game pauses with countdown for remaining players
- **Session management**: View and terminate other active sessions from Settings; required before entering multiplayer to prevent multi-device play
- **Forfeit and disconnect handling**: Players can gracefully forfeit (counts as loss) or disconnect (game suspended, no result recorded) — distinct from each other in tournaments and scoring
- **Play-on mode**: In Memory, Minesweeper, Sudoku, Wordle, Hangman, and Mahjong races, the loser can keep playing after the winner finishes while the winner spectates
- **Spectator state broadcasting framework**: All 28 multiplayer games support the `onStateChange` interface for sharing visual game state with spectators; arcade games use throttled broadcasts to minimize data
- **Multiplayer badges and hub filter**: Game cards show multiplayer badges; hub filter lets users browse multiplayer-enabled games

### Changed
- Disconnection no longer immediately removes players from in-progress games — they stay in the room during the reconnect window
- Race overlay now shows pause screen with countdown timer when opponent disconnects

## [v2.101.0] - 2026-03-10

### Added
- **Multiplayer mid-game join**: Host can invite friends to replace AI players during active games (Texas Hold'em first)
- **Game invite notifications**: Global toast overlay for incoming game invites with Accept/Decline buttons
- **Floating Social button**: Access friends panel and social features from within any game, not just the hub
- **Race mode level announcements**: Multiplayer race opponents see a toast when a player reaches a new level
- **Sent friend requests tab**: View and cancel pending friend requests you've sent
- **Display names in Connect Four multiplayer**: Player names shown instead of generic "You"/"Opponent"
- **Tournaments panel**: Browse, create, join, and manage game tournaments (with defensive loading)

### Fixed
- **Texas Hold'em blind overflow**: Blinds no longer show astronomical numbers on resumed saved games; replaced exponential scaling with a capped 10-level blind schedule
- **Texas Hold'em multiplayer routing**: Fixed broken condition that always routed to VS mode instead of Race
- **Tournaments blank page crash**: Added Array.isArray guard to prevent crash when tournament API returns non-array data
- **Mobile game filters**: Category filter pills now wrap on mobile instead of requiring horizontal scroll

## [v2.100.0] - 2026-03-10

### Added
- **Connect Four physics engine**: Discs fall with real gravity and bounce with plastic-on-plastic coefficient of restitution via requestAnimationFrame physics simulation
- **Connect Four realistic board proportions**: Blue frame has proper rib thickness between holes, thicker border, bottom shelf, and 3D molded-plastic gradient
- **Connect Four board details**: Vertical column divider ridges, horizontal row divider ridges, raised rim highlights, and inner shadow rings around each hole matching real injection-molded board
- **Connect Four track clearance**: Holes are 88% of disc diameter (disc rim hides behind frame); discs settle with small random horizontal offset simulating loose fit in track

### Fixed
- **Dashboard bot profit currency**: USD-based bots on the Dashboard now correctly show profit in USD instead of BTC

## [v2.99.0] - 2026-03-10

### Added
- **Connect Four gravity drop**: Discs now fall under gravity with a realistic bounce and settle animation, just like the real game
- **Connect Four drop toggle**: Switch between instant "Snap" placement and natural "Drop" with gravity animation (Drop is default)
- **Connect Four new game button**: Quick-start a fresh game without changing difficulty
- **Connect Four realistic discs**: 3D-styled discs with radial gradients, highlights, and inner rings matching real Connect Four pieces

### Changed
- **Bot profit display**: USD bots now show profit in USD as the primary value (BTC as secondary), and vice versa for BTC bots
- **Connect Four AI timing**: AI opponent now pauses briefly before making a move for a more natural feel
- **Connect Four mobile layout**: Controls split into two rows on mobile to prevent crowding; hover indicators hidden on touch devices
- **Texas Hold'em mobile**: Bid and raise buttons now fit properly on mobile screens
- **Admin page mobile**: User management page now uses a card-based layout on mobile for easy group editing
- **Centipede mobile**: Game map now fits within the mobile viewport

### Fixed
- **Minesweeper mobile unflag**: Long-pressing a flagged cell now correctly removes the flag instead of revealing the cell
- **Snake mobile input lag**: Swipe controls now respond instantly via touchmove instead of waiting for finger lift
- **Snake mobile fit**: Game board and D-pad controls now fit on screen without scrolling
- **Snake pause bug**: Pausing and unpausing no longer restarts the game

## [v2.98.2] - 2026-03-10

### Fixed
- **Coin icon 429 errors**: Fallback SVGs for unknown coin symbols are now cached on disk, preventing repeated requests to CoinCap that trigger rate limiting

## [v2.98.1] - 2026-03-10

### Changed
- **Mobile nav icons**: Navigation icons now distribute evenly across the screen instead of overflowing
- **Shalas status message**: Game instructions moved to bottom of play area for cleaner layout

### Removed
- **Shalas timer & leaderboard**: Removed due to mobile layout issues — may revisit in a future release

### Fixed
- **Shalas card selection double outline**: Fixed duplicate ring effect when selecting cards from hand
- **Shalas mobile layout**: Wrapped game content in vertical flex container to prevent horizontal overflow

## [v2.98.0] - 2026-03-10

### Added
- **Shalas game timer & leaderboard**: Tracks solve time per game with an arcade-style top 3 leaderboard — enter 3-letter initials on fastest wins (contributed by David Greene)
- **Shalas consecutive run plays**: Select and play consecutive cards from your hand in one move (e.g., 4-5-6-7) — special card effects don't trigger in runs
- **Crossword themed backgrounds**: Each puzzle displays a subtle themed background with large emoji behind the grid matching the daily theme (snowmen for winter, rockets for space, etc.)

### Changed
- **Shalas wildcard 2 mimics specials**: Choosing 7 triggers Selector ability, choosing 10 triggers Destroyer ability
- **Shalas 4-of-a-kind Wild Set**: Now works like wildcard 2 — player chooses any rank including special abilities; also supports cross-discard counting (hand cards + matching discard pile top)
- **Shalas hover highlights**: Playable hand cards show a yellow ring on hover
- **Shalas face-down card confirmation**: Blind plays now require a "Flip & Play" button press instead of immediate play
- **Crossword grid padding**: Added spacing between outermost cells and the grid border
- **Crossword clues spacing**: Clues panel now stacks below the grid on mobile with proper padding

## [v2.97.1] - 2026-03-09

### Fixed
- **Version update toast timing**: Toast no longer appears before the backend has restarted — now requires both a version change and a confirmed server restart before prompting users to reload

## [v2.97.0] - 2026-03-09

### Added
- **Daily Crossword puzzle**: Themed crossword puzzles with Easy, Medium, and Hard difficulty — one puzzle per difficulty per day, algorithmically generated from 100+ themed word banks (contributed by Shantina Jackson-Romero)
- **How to Play help modals**: Every game now has a blue "?" button with rules, controls, strategy tips, and game-specific details — 40 games covered
- **Live account restrictions**: Non-privileged users see a friendly notice explaining paper trading access, with links to self-host or use commercial platforms

### Fixed
- **Session limit enforcement**: Login session limit and cooldown errors are no longer swallowed by the catch-all error handler — they now correctly block login as intended

## [v2.96.0] - 2026-03-09

### Added
- **Shalas card game**: New original card game invented by David Damir Greene — special card mechanics (Destroyer, Wildcard, Selector, Blocker, 4-of-a-kind Wild Set), Ace dual-rank rule, staggered hand fan layout, undo support, and circular discard fan (contributed by David Greene)
- **Speed difficulty selection**: Choose Easy, Normal, or Adept AI difficulty before starting a game of Speed (contributed by Shantina Jackson-Romero)
- **Speed face-down deal**: Cards dealt face-down with simultaneous center card flip to start the game (contributed by Shantina Jackson-Romero)
- **Spoons game modes**: Turn-based and Real-time modes with Easy/Normal/Adept AI difficulty (contributed by Shantina Jackson-Romero)
- **Blackjack animated dealer**: Step-by-step dealer card reveals with AI-narrated commentary (contributed by David Greene)
- **GameLayout subtitle support**: Shared game wrapper now accepts an optional subtitle displayed beneath the title

### Changed
- **Blackjack card size**: Player and dealer cards use standard size instead of compact for better readability (contributed by David Greene)
- **Texas Hold'em larger player cards**: Player hole cards now use the large card size for easier viewing (contributed by David Greene)
- **Texas Hold'em touch-friendly raise slider**: Drag-based vertical raise slider with touch support (contributed by David Greene)

## [v2.95.2] - 2026-03-09

### Added
- **Texas Hold'em flop bonus**: +1,000 chips added to pot when the flop shows three of a kind, a run (consecutive ranks), or all same suit (contributed by David Greene)
- **Texas Hold'em J/2 bonus hand**: Winners holding J/2 now earn a 1,000 chip bonus alongside J/J, 2/3, and Q/7 (contributed by David Greene)

### Changed
- **Texas Hold'em raise slider**: Taller vertical slider now spans the full player card area for easier adjustment (contributed by David Greene)

## [v2.95.1] - 2026-03-09

### Added
- **Texas Hold'em bonus hands**: Winners holding J/J, 2/3, or Q/7 earn a 1,000 chip bonus (contributed by David Greene)
- **Texas Hold'em winning card highlights**: Winning 5-card hand highlighted with blue ring and lifted on both hole cards and community cards (contributed by David Greene)
- **Texas Hold'em vertical raise slider**: Raise slider moved to a vertical orientation beside action buttons, low-to-high bottom-to-top (contributed by David Greene)

### Changed
- **Texas Hold'em smarter AI**: AI uses Sklansky-inspired pre-flop evaluation, flush/straight draw awareness, pot odds, occasional slow-plays and bluffs (contributed by David Greene)
- **Texas Hold'em auto all-in**: AI goes all-in after 3+ re-raises in a single betting round (contributed by David Greene)
- **Mini card layout**: Small opponent cards in Texas Hold'em now show only rank + suit centered for better readability at small sizes

## [v2.95.0] - 2026-03-08

### Added
- **Speed card game**: Real-time 2-player race to empty your hand — play cards ±1 rank on center piles (contributed by Shantina Jackson-Romero)
- **Spoons card game**: 3-player grab game — collect 4-of-a-kind and race to grab a spoon before opponents (contributed by Shantina Jackson-Romero)
- **Card back branding**: Neon blue truck logo overlay on all playing card backs
- **Subcategory subgrouping**: Games hub "All" view now groups card games by subcategory (Casino, Classic, Rummy, etc.)

### Changed
- **Texas Hold'em betting rounds**: Fixed community cards dealing — flop, turn, and river now each require a full betting round before advancing (contributed by David Greene)
- **Texas Hold'em blind display**: Small blind and big blind badges shown on each player, rotating correctly between hands (contributed by David Greene)
- **Texas Hold'em AI pacing**: AI opponents take 2 seconds per decision with visible action text so players can follow the action (contributed by David Greene)
- **Texas Hold'em blind levels**: Blinds double every 10 minutes (10/20 → 20/40 → 40/80, etc.) for tournament-style pressure (contributed by David Greene)
- **Texas Hold'em new game**: Added always-visible New Game button to restart the tournament at any time (contributed by David Greene)
- **Card size standardization**: All 16 card games now use shared size constants from PlayingCard.tsx — no more per-game hardcoded sizes
- **Game category pills alphabetized**: Category and subcategory filter pills sorted alphabetically

## [v2.94.2] - 2026-03-08

### Fixed
- **News/video page 503 error**: SQL retention filter used PostgreSQL-only syntax that crashed at runtime; now uses dialect-aware approach
- **Changelog version history**: Commits were incorrectly attributed to the wrong version; fixed parsing logic
- **Order reconciliation**: API fetch limit now scales with number of active products instead of a fixed 200

### Added
- **News pagination tests**: Unit tests for `get_articles_for_user` covering retention filtering, pagination, and page_size=0

## [v2.94.1] - 2026-03-08

### Changed
- **Performance optimizations across backend and frontend**: Reduced database queries, API calls, and computation complexity in 16 modules
- **Order reconciliation**: Single API call to check all products instead of one call per product
- **Coin review service**: Batch database lookup instead of per-coin individual queries
- **News/video feeds**: Retention filtering and pagination now handled in SQL instead of Python
- **Volume analysis**: Concurrent API calls for market stats instead of serial fetching
- **Grid order cancellation**: Single batch cancel API call instead of individual cancels per order
- **Trade stats and PnL**: SQL aggregation instead of loading all closed positions into memory
- **Dashboard win rate**: SQL count instead of materializing all positions
- **Changelog cache**: Single git subprocess instead of two per version tag
- **Frontend indicators**: O(N) running sums and monotonic deques replace O(N×P) slice operations for SMA, Bollinger Bands, and Stochastic calculations
- **Bot detail queries**: SQL COUNT replaces loading all positions; clone name check uses single LIKE query
- **Report bulk delete**: Single SQL DELETE instead of per-row deletion loop
- **Candle cache**: Evicts data for inactive trading pairs to bound memory usage

## [v2.94.0] - 2026-03-08

### Changed
- **Portfolio holdings table**: "Avail" and "Hold" columns replaced with **"Free"** (balance not in any deal) and **"In Deals"** (amount tied up in active bot positions). Balance column remains unchanged as the total
- **Portfolio Management allocation bar chart**: Fixed invisible segments — colors are now visible instead of showing only a percentage number

### Fixed
- **Rebalance status endpoint**: 0% allocation targets displayed as defaults (34/33/33) due to same `or` falsy-zero bug fixed in v2.93.1

## [v2.93.1] - 2026-03-08

### Fixed
- **Rebalancer ignored 0% allocation targets**: Setting a currency target to 0% was silently treated as the default (34% USD, 33% BTC, 33% ETH) due to Python's `or` operator treating `0.0` as falsy. Now correctly uses `is not None` checks for all target percentages, drift threshold, and minimum trade size

## [v2.93.0] - 2026-03-08

### Added
- **USD↔USDC conversion for rebalancing**: Uses Coinbase's 1:1 convert endpoint instead of market orders (no spread, no fees). Deposited USD now flows directly to USDC allocations in a single rebalance cycle
- **Paper trading convert support**: Paper accounts simulate USD↔USDC conversions with instant 1:1 balance swaps

### Changed
- **USD is now a valid donor for USDC reserves**: USD can top up USDC minimum balances directly via conversion, no longer stuck or routing through BTC/ETH

## [v2.92.4] - 2026-03-08

### Changed
- **Portfolio Management cache survives page reloads**: Settings are now persisted in sessionStorage so refreshing the page shows data instantly without re-fetching

## [v2.92.3] - 2026-03-08

### Fixed
- **Dust sweep shows success and failure feedback**: Sweep results now clearly report which coins were sold and which failed (with reason), instead of silently dropping failures

## [v2.92.2] - 2026-03-08

### Fixed
- **Dust sweep now works on live accounts**: Fixed "Insufficient balance" errors by properly formatting sell amounts with correct product precision and a small safety margin

### Changed
- **Portfolio Management loads instantly**: Settings are cached so navigating away and back shows data immediately instead of re-fetching every time
- **Loading spinner**: Shows a spinner while portfolio settings are loading on first visit
- **Dust sweep section remembers state**: Collapse/expand preference is saved per account in the browser; defaults to expanded when dust sweep is enabled

## [v2.92.0] - 2026-03-08

### Added
- **Dust sweeper**: Automatically sells non-target altcoin dust (ADA, SOL, UNI, etc.) into the most underweight portfolio currency to help rebalancing
- **Position-aware sweeping**: Coins locked in active bot deals are excluded from dust sweeps — only truly free balances are swept
- **Monthly auto-sweep**: Optional toggle to sweep dust automatically every 30 days
- **On-demand sweep**: "Sweep Now" button in the Portfolio Management panel for immediate dust cleanup
- **Configurable threshold**: Set a minimum USD value for dust positions to avoid sweeping trivially small amounts (default $5)
- **RBAC-controlled**: Observers can view dust positions but only users with write access can execute sweeps

## [v2.91.2] - 2026-03-08

### Fixed
- **Portfolio allocation loads automatically**: Current allocation percentages now display on page load for accounts with rebalancing enabled, instead of requiring a manual Refresh click

## [v2.91.1] - 2026-03-08

### Fixed
- **Portfolio rebalancing now works for paper trading accounts**: Current allocation display reads simulated balances instead of requiring live exchange credentials
- **Settings sections no longer hidden by paper trading mode**: RBAC is now the sole mechanism controlling feature visibility — Portfolio Management and Accounts Management are visible to all users with appropriate permissions

## [v2.91.0] - 2026-03-08

### Added
- **USDC portfolio rebalancing**: USDC is now a 4th rebalanceable asset alongside USD, BTC, and ETH with its own target allocation percentage
- **Minimum balance reserves**: Set a floor per currency (e.g., keep at least $500 USDC for debit card spending) — the rebalancer will top up from other currencies proportionally if a balance falls below its reserve
- **Unified Portfolio Management settings**: Auto-Buy BTC and Portfolio Rebalancing are now grouped together in a single settings card with a clear mode selector

### Changed
- **Auto-Buy BTC and Portfolio Rebalancing are now mutually exclusive**: Enabling one automatically disables the other to prevent conflicting trade loops

## [v2.90.9] - 2026-03-08

### Changed
- **Dino Runner rhythm mode — beat-locked timing** (inspired by Alexa Adams, who heard what the rest of us were only seeing): Obstacles now arrive exactly on musical beats using frame-based countdown locked to the BPM grid, not pixel distances that drift with speed changes
- **Dino Runner rhythm energy matching**: Obstacle phrases now mirror the music's intensity — gentle quarter-note patterns when only drums and bass are playing, rapid double-time sequences when the full band kicks in
- **Dino Runner ground specks**: Particles re-enter at random positions instead of wrapping to fixed spots, eliminating the repeating pattern

## [v2.90.8] - 2026-03-08

### Changed
- **Dino Runner rhythm mode reimagined** (Alexa Adams): Obstacles now arrive in musical phrase patterns — call-and-response, quick-quick-steady, triple hits with breathers — instead of random spacing, creating a true rhythm game feel
- **Dino Runner AI improved for rhythm mode**: Auto-play AI now handles rapid obstacle sequences much better with extended look-ahead and smarter landing-zone planning

## [v2.90.7] - 2026-03-07

### Changed
- **Dino Runner ground detail**: Ground specks now move with parallax across 3 depth layers — bright surface highlights and deeper dirt particles create a richer scrolling ground effect

## [v2.90.6] - 2026-03-07

### Fixed
- **Dino Runner seamless terrain**: Parallax scrolling landscape no longer has abrupt visual cuts — terrain layers now tile seamlessly using whole-cycle wave frequencies

## [v2.90.5] - 2026-03-07

### Added
- **Dino Runner variable-height jump on mobile**: Hold your finger down to jump higher, quick tap for a short hop — matches keyboard spacebar behavior

## [v2.90.4] - 2026-03-07

### Fixed
- **Dino Runner mobile controls**: Tap to jump and swipe-down to duck both work correctly — quick taps jump immediately, swipe-down ducks without triggering a jump

## [v2.90.3] - 2026-03-07

### Fixed
- **Dino Runner mobile duck**: Swiping down on mobile now correctly ducks instead of jumping — touch input waits briefly to detect swipe direction before committing to a jump

## [v2.90.2] - 2026-03-07

### Fixed
- **Live version reporting**: Backend now reports the current git tag without requiring a restart — frontend-only deploys via `./bot.sh build` immediately trigger the "new version" toast
- **Blank page after deploy**: Navigating to an unvisited page after a deploy no longer shows a blank page — stale chunk references now auto-reload

## [v2.90.1] - 2026-03-07

### Added
- **Dino Runner ground particles**: 3 layers of pixel dirt particles scroll beneath the ground line with parallax depth — surface particles match ground speed, deeper layers move progressively faster

## [v2.90.0] - 2026-03-07

### Added
- **Game state persistence**: All puzzle and board games now preserve state when navigating away and back — Nonogram, Sudoku, Minesweeper, Connect Four, Tic-Tac-Toe, 2048, Ultimate Tic-Tac-Toe, Hangman, Mahjong, Wordle, and Snake settings

### Fixed
- **Portfolio allocation double-counting**: ETH (or BTC) held as base currency in positions for other markets was counted in both the position's quote aggregate and the free balance aggregate — now correctly deducted to prevent inflated allocation percentages

## [v2.89.5] - 2026-03-07

### Added
- **Allocation charts**: Current allocation display now offers pie chart and stacked bar views — toggle between them to compare current vs target allocations visually

## [v2.89.4] - 2026-03-07

### Fixed
- **Rebalance allocation scoping**: Current allocation now correctly shows only the selected account's positions — was previously summing positions from all accounts including paper trading, inflating the reported value

## [v2.89.2] - 2026-03-07

### Added
- **Min trade size setting**: Configurable minimum trade size (1-25% of portfolio) in rebalance settings — prevents micro-trades that barely move the allocation needle

### Changed
- **Trade sizing**: Sells are now capped to available free balance — never tries to sell more than you have, eliminating failed order errors
- **Trade failure logging**: Downgraded from error to warning — expected when free capital is limited, not a system failure

### Fixed
- **Rebalance allocation display**: Current allocation now correctly shows aggregate portfolio value (free balance + open position values per currency) instead of showing 0% for all currencies
- **Rebalance monitor**: Drift detection uses aggregate allocation; trades execute against free balances only

## [v2.89.0] - 2026-03-07

### Added
- **Portfolio rebalancing**: Set target allocation percentages for USD, BTC, and ETH per exchange account — system automatically rebalances free capital when drift exceeds configurable threshold
- **Rebalance settings UI**: Per-account linked sliders (always sum to 100%), drift threshold control, check interval selection, and live allocation status display in Settings
- **Rebalance status endpoint**: View current vs target allocation percentages and total free capital value

### Fixed
- **Bot budget calculation**: USD bots no longer see BTC/ETH balances as part of their budget — now correctly uses only free quote currency plus open position values in that currency's pairs

## [v2.88.0] - 2026-03-07

### Added
- **Procedural music engine**: Every game now has unique synthesized background music with adaptive BPM, intensity layers, and ambient weather effects — all generated in real-time via Web Audio API
- **Procedural SFX system**: 53 sound effect recipes across 8 categories (UI, cards, board pieces, tonal feedback, arcade, word games, ambient, and game-over jingles) with natural variation
- **Music toggle control**: Per-game mute button with persistent preference for both music and SFX
- **Smooth game-over transitions**: Music fades out over 800ms, game-over jingle plays (win/lose/draw), and the modal animates in with backdrop fade + card scale-in
- **Game hub categories**: Games are now organized into categories (Card, Board, Puzzle, Arcade, Word) with filter pills for easier browsing

### Changed
- Game-over modal now orchestrates audio transitions centrally — individual games no longer manage music stop/start on game end

## [v2.87.0] - 2026-03-04

### Added
- **Dino Runner game**: Pixel-art endless runner with variable-height jumping, ducking, day/night cycle, progressive speed, pterodactyls, and high score tracking — 43 engine tests included

## [v2.86.0] - 2026-03-04

### Added
- **8 new card games**: War, Go Fish, Rummy 500, Cribbage, Euchre, Texas Hold'em, Bridge, and Canasta — each with full rule implementations, AI opponents, and test coverage
- **Card game subcategories**: Card games are now organized into Trick-Taking, Rummy, Casino, Solitaire, and Classic subcategories with filter pills
- **22 new regression tests**: Coverage for dust close profit calculation, NULL profit_quote fallback, signal processor dust close handling, login resilience under DB lock, currency label in order validation, and datetime timezone parsing

### Fixed
- **Dust close positions now calculate actual profit**: Positions too small to sell (dust) are now closed with accurate profit at current price instead of being written off at -100%
- **Signal processor distinguishes dust closes from limit orders**: When a sell returns no trade, the system now checks if the position was dust-closed vs. a limit order pending
- **NULL profit_quote fallback for USD pairs**: Realized PnL stats now fall back to profit_usd when profit_quote is NULL on USD-like pairs, fixing mismatches between per-quote and overall totals
- **Win rate display shows breakevens**: Stats panel now shows breakeven count (e.g., "56W / 0L / 1B") so the math adds up with total trades
- **Chart markers skip sub-penny trades**: Trades with less than $0.01 profit/loss no longer show misleading win/loss arrows on the account value chart
- **Playing card bottom-right position**: The inverted rank/suit on playing cards now correctly appears on the right side

## [v2.85.0] - 2026-03-04

### Added
- **Chess threefold repetition draw**: Repeated positions are now tracked and the game correctly ends in a draw after three occurrences of the same position
- **Sudoku unique solution enforcement**: Generated puzzles are now guaranteed to have exactly one solution across all difficulty levels
- **Spades blind nil bidding**: Players can now bid blind nil for higher stakes (+/-200 instead of +/-100)

### Fixed
- **Gin Rummy knock skipping discard**: Knocking now correctly discards the worst deadwood card first (matching AI behavior) instead of resolving with 11 cards
- **Gin Rummy knock button accuracy**: The "Knock" option now correctly evaluates whether discarding the worst card brings deadwood to 10 or below
- **Card sizing in Spades, Hearts, Crazy Eights, and Gin Rummy**: Face-up cards now use consistent dimensions matching Solitaire, fixing suit/rank content overflow on smaller cards

## [v2.84.11] - 2026-03-04

### Fixed
- **Backgammon click targeting**: Moving to a point that already has your checkers no longer re-selects it as a source — the move executes correctly
- **Backgammon dice obligation rules**: Must now use both dice if possible; if only one can be played, must use the larger die (standard backgammon rules)

## [v2.84.10] - 2026-03-04

### Fixed
- **Negative cache for delisted product 404s**: Price lookups for delisted coins (e.g., TON-BTC, PNG-BTC) that return 404 are now cached for 5 minutes, eliminating ~68 redundant API calls per 15-minute cycle and reducing log noise

## [v2.84.9] - 2026-03-04

### Fixed
- **Suppressed "Future exception was never retrieved" asyncio warnings**: Single-flight cache futures for failed price fetches (delisted coins returning 404) now properly mark exceptions as handled when no concurrent waiters exist

## [v2.84.8] - 2026-03-04

### Changed
- **Remaining 97 print() calls converted to structured logging**: Cleaned up phase_conditions (13), auto_buy_monitor (19), batch_analyzer (2), and main.py (63) — all hot-path and startup console output now routes through Python logging with proper severity levels
- **Transfer categorization reduced from O(N²) to O(N)**: Replaced list membership check (`if tr not in staking`) with single-pass partition in report AI service
- **Blacklist global+user query merged into single SELECT**: Combined two sequential blacklist queries into one using OR condition
- **Seasonality settings fetched in single query**: Added batch settings helper to retrieve multiple config keys in one WHERE IN query instead of sequential lookups
- **News content seen-status uses bulk insert**: Replaced serial db.add() loop with db.add_all() batch for marking content as seen
- **Frontend .find() lookups replaced with O(1) Maps**: Pre-computed bot/strategy/account lookup Maps via useMemo in ClosedPositions, Positions, Bots, and PairSelector — eliminates O(N) linear scans per render/filter iteration

## [v2.84.7] - 2026-03-04

### Changed
- **Trading engine hot loop 50+ print() calls eliminated**: Converted all console print statements to structured logger.debug() calls across the monitor, signal processor, and pair processor — removes unnecessary I/O from every bot cycle
- **Blacklist check uses single query**: Merged two sequential blacklist database queries (user-specific + global) into one combined OR query per trading pair
- **Open position count threaded through call chain**: Position count computed once per bot cycle and passed through instead of re-querying the database for each trading pair
- **Safety order prices computed in O(1)**: Replaced iterative loop with closed-form geometric series formula for safety order deviation calculation
- **Indicator calculation avoids redundant recomputation**: Sell-side checks reuse indicators already computed during buy analysis; recursive previous-period calculation skipped when monitor cache is available
- **Strategy instances cached per config snapshot**: Reuses strategy objects when position config matches bot config instead of reinstantiating per position
- **Account snapshot prices fetched in parallel**: Serial per-position price API calls replaced with deduplicated asyncio.gather() batch fetch
- **Bot statistics computed in single pass**: Merged 6 separate iterations over closed positions into one loop computing all PnL, win rate, and capital metrics
- **Transfer duplicate check uses bulk query**: Replaced per-transfer SELECT with single WHERE IN batch lookup
- **Order reconciliation uses bulk queries**: Replaced per-product-group trade/pending-order queries with two batch WHERE IN queries
- **Balance lookup uses cache by default**: get_balance() no longer forces a fresh API call on every invocation — uses cached accounts with opt-in refresh
- **Sell-all endpoint fetches prices in parallel**: Deduplicated product IDs and batch-fetched via asyncio.gather() before sell loop
- **Frontend components memoized**: Added useMemo/useCallback across Positions, Portfolio, Bots, Charts, News, and Reports pages — prevents unnecessary recalculations on every render
- **Polling intervals reduced**: AI sentiment polling increased from 30s to 120s; portfolio polling increased from 30s to 60s
- **Stochastic %D avoids redundant window computation**: Reuses already-computed K value for the final iteration instead of recalculating max/min over the same window

### Fixed
- **Flaky indicator log test**: Fixed test isolation issue where async DB session leaked across event loops in test suite
- **Account snapshot test missing mock**: Added explicit get_current_price mock to prevent MagicMock arithmetic contaminating snapshot values
- **Trend chart PNG test wrong import path**: Updated import after function moved from html_builder to chart_renderer module

## [v2.84.6] - 2026-03-04

### Changed
- **MACD indicator calculation 10x faster**: Replaced O(n²) nested EMA recomputation with incremental single-pass O(n) algorithm — identical results, dramatically less CPU work per bot cycle
- **Database queries optimized**: Added 5 composite indexes on hot-path columns (positions, trades, bots) and replaced 6 N+1 query patterns with batch aggregation queries — fewer round-trips to PostgreSQL per API call
- **Order statistics use SQL aggregation**: Stats endpoint now computes counts in the database instead of loading all rows into Python
- **Signal processor budget check uses SUM query**: Open position budget calculation now runs a single SQL SUM instead of loading all position objects
- **Duplicate database query eliminated**: Multi-bot monitor was running the same open-positions query twice per cycle — removed the redundant call
- **Dashboard and Closed Positions pages render faster**: Memoized all derived values, wrapped list components in React.memo, and reduced closed-positions polling from 5s to 60s (data doesn't change that frequently)
- **React context re-renders reduced**: Auth, Account, and Notification context values are now memoized, preventing unnecessary re-renders of the entire component tree on every state change
- **TTS playback no longer triggers 4Hz re-renders**: Removed high-frequency currentTime/duration from ArticleReader context dependencies — playback progress updates no longer cascade through the whole app
- **Grid percentile lookup uses binary search**: Replaced linear scan with bisect for O(log n) percentile bucket finding
- **Report generation pre-groups data**: Win rate and transfer calculations now use single-pass dictionary grouping instead of nested loops

## [v2.84.5] - 2026-03-03

### Fixed
- **Misleading order validation error messages**: Failed order errors showed "BTC" as the currency even for USD pairs (e.g., "0.038 BTC is below minimum 1 BTC for IOTX-USD"). Coinbase API returns `quote_currency_id`/`base_currency_id` but validation was reading the non-existent `quote_currency` key and defaulting to "BTC". Now reads the correct API field with proper fallback
- **Missing currency labels in fallback validation**: When product API lookup fails entirely, the fallback defaults now include correct currency labels derived from the product ID instead of omitting them

## [v2.84.4] - 2026-03-03

### Fixed
- **502 errors on History page preferences endpoint**: The nginx `location /api/auth/preferences/` block was pointing to the Vite dev server (port 5173) instead of the backend (port 8100), causing persistent 502 Bad Gateway in prod mode. The `bot.sh` mode switch now normalizes all `/api/` location blocks to the backend port on every switch, preventing this class of bug

## [v2.84.3] - 2026-03-03

### Fixed
- **News/video/metrics loading after PostgreSQL migration**: Fixed timezone-aware vs naive datetime mismatches that broke all cache expiry checks and content refresh after migrating to PostgreSQL. Standardized all datetime operations to naive UTC across 6 backend files
- **Stale timezone-aware cache files**: Old JSON cache files (news, video, market metrics) contained timezone-aware timestamps from pre-migration code. Cache loaders now strip timezone info when parsing, preventing "can't subtract offset-naive and offset-aware datetimes" crashes
- **Demo account snapshot accuracy**: Corrected March 1st and 2nd snapshots for all three demo paper trading accounts where price-fetch failures during snapshot capture caused account values to be underreported

## [v2.84.0] - 2026-03-03

### Added
- **PostgreSQL database backend**: Migrated production from SQLite to PostgreSQL, eliminating all "database is locked" errors from concurrent bot operations. SQLite's single-writer lock was causing ~18 lock errors/min with 23 active bots — PostgreSQL's MVCC handles concurrent writes natively
- **Dual database support in setup wizard**: New installs can choose between SQLite (simple, default) or PostgreSQL (recommended for production) during setup
- **SQLite-to-PostgreSQL migration script**: One-command data migration (`scripts/migrate_sqlite_to_postgres.py`) transfers all tables with row count verification
- **Dual-mode migration helpers**: New `migrations/db_utils.py` provides `column_exists()` and `safe_add_column()` for both SQLite and PostgreSQL, enabling future migrations to work with either backend

### Changed
- **Database engine configuration**: PostgreSQL connections use pooling (`pool_size=5, max_overflow=3`) tuned for t2.micro; SQLite retains single-threaded mode
- **Balance and coin review queries**: Replaced raw `sqlite3.connect()` calls with SQLAlchemy sync engine helper for database-agnostic operation
- **News retention filtering**: Per-user retention days now computed in Python instead of SQLite-specific `datetime()` functions, making it portable across databases
- **Content seen/unseen tracking**: Replaced SQLite-dialect `INSERT OR IGNORE` with check-then-insert pattern for cross-database compatibility

### Fixed
- **LodeRunner game crash from corrupted save state**: Game crashed with "Cannot read properties of undefined" when localStorage contained stale/incomplete saved state missing required array fields — now validates all required arrays exist before loading, and clears corrupted saves automatically
- **PostgreSQL JSON DISTINCT error**: Fixed "could not identify an equality operator for type json" when querying inactive bots with open positions by using ID subquery instead of full-model DISTINCT

## [v2.83.1] - 2026-03-03

### Fixed
- **Paper trade execution failures from DB lock cascade**: Indicator log writes now use an isolated database session, so a "database is locked" error on diagnostic logging can no longer poison the trading session and kill subsequent trade execution
- **Redundant mid-cycle DB commit removed**: Eliminated an unnecessary commit per open position per cycle that was competing for SQLite's write lock

## [v2.83.0] - 2026-03-02

### Added
- **Paper trading slippage simulation**: Paper trade fills now walk the real order book (VWAP) instead of using mid-price, producing realistic fill prices that account for spread and depth — toggle per bot in Slippage Guard settings
- **"Simulate Slippage" parameter**: New paper-trading-only toggle in bot config; enabled by default for all paper bots via migration
- **Last-seen badge counts in user profile**: Closed/failed position badge counts are now returned in the user profile response, eliminating a separate API call on every page load

### Changed
- **Paper portfolio valuation**: Altcoin prices now fetched as USD pairs first (with BTC fallback), improving accuracy for coins with direct USD markets
- **Account snapshot service**: USD/BTC portion calculation simplified — everything non-BTC is now the USD portion, avoiding double-counting from open positions

### Fixed
- **SQLite "database is locked" errors**: Indicator log writes reduced ~80-85% by skipping non-actionable evaluations (no signal fired, no open position) — the common case that was generating thousands of unnecessary commits per cycle

## [v2.82.10] - 2026-03-02

### Fixed
- **Dashboard chart blank after switching users**: Stale account ID in localStorage caused chart to show "No historical data" when logging in as a different user — now validates stored account belongs to current user and re-selects default if not
- **Logout clears account selection**: Prevents stale account ID from carrying over between user sessions

## [v2.82.9] - 2026-03-02

### Fixed
- **Login crash under DB contention**: Login failed with 500 when SQLite was busy because ORM attributes expired after rollback, triggering MissingGreenlet errors — now all user data is resolved before any writes
- **Demo user Dashboard chart blank**: Chart showed "No historical data available yet" because login/API requests were crashing under DB contention (same root cause as above)

## [v2.82.8] - 2026-03-02

### Added
- **All 150 classic Lode Runner levels**: Complete set of original Apple II (1983) levels, up from 10

### Fixed
- **Dig input sometimes requires double-press**: Dig key press was being consumed even when the player was mid-step or falling, so the input was lost before the engine could process it — now buffered until aligned

## [v2.82.7] - 2026-03-02

### Added
- **Classic Lode Runner levels**: Replaced custom levels with authentic Apple II (1983) levels 1-10 with original layouts, including trap bricks and escape ladders
- **Trap brick tile**: New tile type that looks like a normal brick but entities fall through — faithful to the original game's false brick mechanic
- **Post-respawn invincibility**: Player gets 2 seconds of invincibility after dying (with blink effect) instead of instant game over

### Fixed
- **Lode Runner guard bar pathing**: Guards can now drop from monkey bars instead of getting stuck when hanging
- **Lode Runner diagonal guard fall**: Guards now fall vertically like the player instead of moving diagonally during pathfinding
- **Dust position sell failure**: Positions where the sell amount rounds to zero (e.g., missing paper balance) are now closed gracefully as dust instead of sending a zero-amount order to the exchange

## [v2.82.6] - 2026-03-02

### Fixed
- **Dashboard chart missing for paper trading accounts**: Account value chart was querying before the selected account loaded, causing paper trading accounts to show "No historical data available yet" despite having snapshots

## [v2.82.5] - 2026-03-02

### Fixed
- **Login crash under database contention**: Fixed crash where login would fail completely when SQLite is locked — user attributes are now pre-loaded before any database write, so login succeeds even if the last-login timestamp update fails

## [v2.82.4] - 2026-03-02

### Changed
- **Lode Runner guard AI**: Guards now use BFS pathfinding to navigate across platforms, ladders, and bars to reach the player — no more standing directly above without pursuing
- **Lode Runner guard speed**: Guards are slower (55 px/s vs player's 100 px/s) for better gameplay balance
- **Lode Runner escape ladder**: Only a single hidden ladder column at the escape route instead of the entire top row

### Fixed
- **Lode Runner player in holes**: Player passes through open brick holes freely and only dies if caught when the brick fully regenerates — not trapped like enemies
- **Lode Runner guard gold drop**: Guards now drop carried gold above the hole immediately when trapped, not only when killed by brick regeneration

## [v2.82.2] - 2026-03-02

### Fixed
- **Lode Runner bar position**: Raised monkey bar line to top of cell so player hands align correctly when hanging
- **Lode Runner escape ladder**: Hidden escape ladders now extend down from row 0 through column 2 to connect with the topmost reachable platform — previously unreachable from any level

## [v2.82.1] - 2026-03-02

### Fixed
- **Login error on database contention**: Fixed PendingRollbackError crash when updating last_login_at during SQLite lock — login now succeeds gracefully even under heavy write load

## [v2.82.0] - 2026-03-02

### Added
- **Skip stable/pegged pairs**: New bot setting to automatically skip stablecoin pairs (USDC-USD, DAI-USD) and wrapped token pairs (WBTC-BTC, CBETH-ETH) that rarely move in price — enabled by default
- **Dynamic stable pair detection**: Daily background job analyzes trading pair prices to automatically detect new stablecoins and pegged assets, logging discoveries for review
- **Lode Runner dig projectile**: Visible yellow beam from player's hand to target brick during digging, with gradual brick dissolution effect
- **Lode Runner game state persistence**: Game progress auto-saves and restores when navigating away and back
- **Lode Runner drop from bar**: Press down while hanging on a bar to drop to the cell below
- **Lode Runner escape ladder**: Player can now reach hidden escape ladders from the row below (grab from underneath)

### Changed
- **Lode Runner sprite polish**: Running sprites now lean into their direction (C64 style), idle hanging sprites hold still, feet touch ground, brick refill time increased from 0.6s to 1.5s

### Fixed
- **Trading category filter**: Bot buy decisions now use the bot's own allowed categories instead of global settings, preventing questionable coins from slipping through
- **Missing MEME category**: Coins tagged as [MEME] are now properly categorized instead of defaulting to BLACKLISTED
- **Auto-add pairs ignoring categories**: New pairs added by the daily sync now respect the bot's allowed category and stable pair filters
- **SQLite lock retries**: Paper trading balance saves now use exponential backoff with jitter (5 attempts) to better handle write contention

## [v2.81.0] - 2026-03-02

### Added
- **Lode Runner C64 brick visuals**: Bricks now render with classic C64-style offset brick pattern with mortar lines and highlights
- **Lode Runner dig blast effect**: Digging a brick shows a spark/zap animation at the dig site
- **Lode Runner brick refill animation**: Bricks refill with a V-shaped stepped pixel-art pattern instead of a flat slide-up
- **Lode Runner falling sprites**: Player and guard fall sprites now show arms raised above head, matching classic arcade pose

### Fixed
- **Paper trading bot can't sell**: Fixed greenlet_spawn error that prevented paper trading bots from executing sell orders — balance operations now use fresh database sessions instead of the shared session from initialization
- **Lode Runner levels**: Fixed row-length inconsistencies across all 10 levels (padded/trimmed to exactly 28 columns), fixed unreachable gold in Levels 1 and 2

## [v2.80.1] - 2026-03-02

### Fixed
- **Lode Runner edge running**: Player and guards can now run off platform edges and fall, matching classic Lode Runner behavior — entities finish their horizontal step before gravity kicks in
- **SQLite lock storms**: Indicator log writes now batch into a single commit instead of committing individually, dramatically reducing "database is locked" errors during bot scan cycles
- **SQLite busy timeout**: Increased from 15s to 30s and enabled synchronous=NORMAL for WAL mode to further reduce write contention

## [v2.80.0] - 2026-03-02

### Added
- **Lode Runner C64 sprites**: Player and guard sprites replaced with classic C64-style pixel-art with animation sequences (running, climbing, hanging, falling, digging)

### Fixed
- **Lode Runner movement**: Player can now climb ladders and step onto platforms above — ladders extend through brick floors matching classic arcade behavior
- **Positions page stale data**: Switching between demo users no longer shows the previous user's overall stats — React Query cache now clears on logout

## [v2.79.0] - 2026-03-02

### Added
- **Lode Runner**: Classic puzzle-platformer with 10 hand-crafted levels — collect all gold, dig holes to trap guards, then escape via hidden ladders at the top
- **Centipede engine improvements**: Smoother grid-stepping movement for centipede chains

## [v2.78.0] - 2026-03-02

### Added
- **Centipede**: Classic arcade shooter — blast a centipede winding through mushroom fields, dodge spiders, level up as speed increases
- **Space Invaders**: Defend Earth from 5 rows of marching aliens with destructible bunkers, UFO fly-overs, and escalating waves

### Fixed
- **Plinko double-drop on mobile**: Tapping on a phone no longer drops 2 balls — replaced separate click/touch handlers with a single pointer event handler

## [v2.77.0] - 2026-03-02

### Added
- **7 new card games**: Blackjack, Video Poker, Hearts, Spades, Crazy Eights, Gin Rummy, and Freecell join the Games Hub with full AI opponents, game state persistence, and undo support
- **Cards category filter**: New "Cards" category in the Games Hub groups all 8 card games (including Solitaire) for easy discovery
- **Shared card infrastructure**: Reusable card rendering components and deck utilities power all card games with consistent visuals
- **24 new Nonogram puzzles**: Expanded from 11 to 35 total puzzles across all difficulty sizes (5x5, 10x10, 15x15)

### Fixed
- **Portfolio balances update faster**: Reduced backend cache TTL from 60s to 25s so portfolio data refreshes reliably on each 30-second poll cycle
- **"In Grids" column header alignment**: The header in the Positions balances table is now right-aligned to match the other column headers

## [v2.76.19] - 2026-03-02

### Fixed
- **Successful logins no longer count toward rate limit**: Only failed login attempts (wrong email/password) are recorded. Logging in and out of multiple accounts from the same IP no longer triggers a 429 lockout

## [v2.76.18] - 2026-03-02

### Fixed
- **Login no longer fails when bots are writing to the database**: The `last_login_at` update and session creation are now non-blocking — if SQLite is locked by bot activity, login still succeeds
- **Demo account no longer gets rate-limited across multiple visitors**: Per-username rate limiting is now skipped for Observers group (shared demo accounts), using RBAC group membership instead of hardcoded username checks. Per-IP rate limiting still applies

### Added
- **Account value chart shows live current value**: The "Account Value Over Time" chart now appends a real-time data point for today using the current portfolio value, so the chart extends to "right now" instead of ending at the last midnight snapshot

## [v2.76.17] - 2026-03-02

### Fixed
- **Reduced login failures after restart**: Bots now stagger their first signal checks over ~8 seconds instead of all firing at once, preventing SQLite lock contention that caused transient 500 errors on login
- **Increased SQLite busy timeout**: Raised from 5s to 15s so queries wait longer for locks instead of failing

## [v2.76.16] - 2026-03-02

### Fixed
- **Paper trading growth goals now show actual values**: Goals linked to paper/demo accounts were always showing $0 current value and "behind target" because the snapshot system excluded paper trading accounts. Goals now use per-account snapshot values so demo accounts see their real balances and profits
- **Goal backfill includes paper account data**: When viewing a goal's trend chart for the first time, the backfill now correctly includes paper account snapshots instead of returning empty data

## [v2.76.15] - 2026-03-02

### Fixed
- **No more 429 errors on History page**: Moved preferences endpoint out of strict auth rate-limit zone (5r/min → 30r/s) and removed redundant 30-second refetch loop
- **Paper trading accounts can now view depth charts and ticker data**: Orderbook and ticker endpoints now fall back gracefully for paper-only accounts instead of returning 503 errors

### Changed
- **Reduced 4 oversized backend files below 1200-line limit**:
  - `signal_processor.py`: Extracted `_record_signal()` helper, moved inline imports to top-level
  - `html_builder.py`: Extracted chart rendering to `chart_renderer.py`
  - `pdf_generator.py`: Extracted PDF chart rendering to `chart_pdf_renderer.py`
  - `indicator_based.py`: Extracted order sizing math to `safety_order_calculator.py`

## [v2.76.14] - 2026-03-02

### Fixed
- **Paper trading bot stats now display**: Bots list page now shows win rate, PnL, and projections for paper-only accounts (demo users). Previously these fields were blank because the stats calculation required a real CEX account
- **Scheduled report emails now deliver**: Fixed missing SES sender email configuration that caused all scheduled report emails to fail silently since the last server migration
- **Cleaned up stale recipient data**: Removed obsolete `level` field from report schedule recipients, replaced with correct `color_scheme` field

## [v2.76.13] - 2026-03-02

### Changed
- **Decomposed report builder god functions**: Broke down 4 oversized report-building functions into focused orchestrators with helpers
  - `_build_expenses_goal_card()`: 484→~40 line orchestrator + 7 helpers
  - `_build_pdf_expense_goal()`: 408→~60 line orchestrator + 4 helpers
  - `_build_summary_prompt()`: 307→~100 line orchestrator + 3 helpers
  - `gather_report_data()`: 254→~88 line orchestrator + 4 helpers
- **Decomposed complex control flow functions**: Extracted focused methods from high-complexity functions
  - `shutdown_event()`: Replaced 10 cancel blocks + 6 monitor stops with loop + `_cancel_task()` helper
  - `_evaluate_single_condition()`: Extracted `_evaluate_crossing()` and `_evaluate_direction_change()` dispatch methods
  - `get_cex_portfolio()`: Extracted 4 helpers for holdings, PnL, balance breakdown, and closed PnL
  - `run_portfolio_conversion()`: Extracted `_sell_currency_with_fallback()` and `_convert_intermediate_currency()`
- **Extracted BudgetSection component**: Split out the 247-line budget configuration section from BotFormModal (1362→1115 lines)

### Fixed
- **Paper trading partial-sell bug**: Fixed stale balance reads in paper trading that caused positions to sell less than they bought, turning profitable trades into losses. The root cause was SQLite WAL transaction snapshot isolation — `get_balance()` now forces a fresh DB read with `expire_all()` before returning balances
- **Retroactively corrected 4 affected paper deals**: Fixed historical P&L data for deals incorrectly recorded as losses due to the stale balance bug

## [v2.76.12] - 2026-03-02

### Changed
- **Extracted strategy parameter definitions**: The 190-line parameter data constant was moved from `indicator_based.py` to its own `indicator_params.py` module, bringing the strategy file under the size limit (1424→1232 lines)
- **Centralized AI provider settings**: Deduplicated AI provider constants and lookup functions that were duplicated between `blacklist_router` and `coin_review_service` into a single source of truth in `settings_service`
- **Moved API key masking to encryption module**: The `mask_api_key` utility (formerly `_mask_key_name`) now lives in `encryption.py` alongside the decrypt/encrypt functions it depends on
- **Fixed TTS hook import direction**: Moved `useTTSSync` from page-specific hooks to shared hooks directory, correcting a context→page import violation

### Fixed
- **4 RBAC tests now pass**: Fixed pre-existing test failures where non-admin permission tests bypassed FastAPI's dependency injection. Tests now properly validate the `require_superuser` security chain

## [v2.76.11] - 2026-03-02

### Changed
- **Split models.py into domain sub-modules**: The 1672-line monolithic models file was reorganized into 5 focused domain modules (auth, trading, content, reporting, system) — all existing imports continue to work unchanged
- **Fixed bull_flag circular import**: Resolved a circular dependency chain (indicators → strategies → indicators) that caused 900+ test collection errors when running the full test suite. The `sys.modules` hack in the test file was removed in favor of a proper lazy import

## [v2.76.10] - 2026-03-02

### Changed
- **Decomposed 4 oversized functions**: Broke down the largest functions in the trading engine and monitoring system into focused, single-responsibility helpers while preserving exact behavior
  - `process_bot_pair()`: 489→104 lines orchestrator + 11 helpers
  - `get_account_portfolio_data()`: 358→~50 lines orchestrator + 5 helpers
  - `process_bot_batch()`: 463→~45 lines orchestrator + 7 helpers
- **Trading engine TradeContext dataclass**: Internal signal processor functions now use a shared `TradeContext` instead of threading 8-13 individual parameters through every call

## [v2.76.9] - 2026-03-01

### Changed
- **Article content extraction moved to service layer**: The 290-line `get_article_content` function (caching, fetching, rate limiting, content extraction) was extracted from news_router into `article_content_service.py`, improving separation of concerns
- **Session service no longer depends on FastAPI**: Session limit checks now raise domain exceptions (`RateLimitError`, `SessionLimitError`) instead of `HTTPException`, properly decoupling the service layer from the web framework
- **Removed duplicate exchange client helper**: `get_coinbase_from_db()` in bot CRUD router was a duplicate of the portfolio_service version — consolidated to single source of truth

## [v2.76.8] - 2026-03-01

### Fixed
- **Auto-calculate bots with percentage-of-base safety orders used 3x the base order**: When `split_budget_across_pairs` was enabled, the pair processor divided `safety_order_percentage` by `max_concurrent_deals`, double-counting the budget split already done per-position. This corrupted the order sizing multiplier (4.0 became 1.3), causing base orders to consume 77% of budget instead of 25%. Only affected bots using `percentage_of_base` safety order type with auto-calculate enabled (e.g., RSI Runner). Fixed 7 open positions with inflated budgets.

## [v2.76.7] - 2026-03-01

### Fixed
- **Logout now properly ends server-side sessions**: The logout request was missing the Authorization header, so the server never received the token needed to end the session. This caused session slots to remain occupied after logout, blocking re-login for demo users with per-IP session limits.

## [v2.76.6] - 2026-03-01

### Fixed
- **PnL breakdown color mismatch**: USD-like currencies in the PnL breakdown now correctly show green for gains and red for losses. Previously, `Math.abs()` stripped the minus sign while the color still reflected the negative value, making losses appear as positive numbers in red. Also fixed dollar-sign placement to show `-$0.92` instead of `$-0.92`.

## [v2.76.5] - 2026-03-01

### Changed
- **Session limit errors show when to retry**: When login is denied due to max sessions (total or per-IP), the error message now tells the user when the earliest session slot will free up (e.g., "A session slot will free up in about 10 minutes").

## [v2.76.4] - 2026-03-01

### Fixed
- **Login error after logout**: Fixed crash when server returns non-JSON error responses (e.g., nginx HTML error pages). All 15 auth error handlers in AuthContext now gracefully handle non-JSON responses instead of throwing "Unexpected token '<'" parse errors.

## [v2.76.3] - 2026-03-01

### Fixed
- **Plinko energy conservation**: Peg collision biases no longer inject energy. Lateral spread now redistributes existing velocity from vertical to horizontal instead of adding a fixed speed floor — slow balls get proportionally small deflections, fast balls get larger ones, but total energy never increases.

## [v2.76.2] - 2026-03-01

### Changed
- **Plinko gravity reduced**: Halved gravitational acceleration so balls fall more slowly and interact with pegs more naturally.

## [v2.76.1] - 2026-03-01

### Fixed
- **Add Account button RBAC**: The "Add Account" button in the account switcher (both empty-state and dropdown) is now disabled for users without `accounts:write` permission.

## [v2.76.0] - 2026-03-01

### Security
- **Portfolio sell endpoint RBAC**: `POST /trading/market-sell` now requires `accounts:write` permission. Previously any authenticated user could execute sell orders.

### Changed
- **Eliminated all hardcoded demo account checks**: Replaced every `isDemoAccount` email-pattern check across the frontend with proper RBAC permission hooks (`usePermission`). Affected: Settings page (password/MFA sections), AI Providers manager (key management buttons).
- **Seasonality toggle uses RBAC**: Backend changed from superuser-only to `settings:write` permission; frontend uses `usePermission` instead of `is_superuser` check.
- **Portfolio sell buttons**: Disabled for users without `accounts:write` permission (visible but grayed out with "Read-only account" tooltip).
- **Auto-buy stablecoin inputs**: All sub-controls (checkboxes, min-value inputs) now properly disabled for read-only users. Previously only the Save button was disabled.
- **Position modals defense-in-depth**: Edit Position Settings and Add Funds modals now accept a `readOnly` prop and hide their submit buttons when the user lacks `positions:write`.

## [v2.75.9] - 2026-03-01

### Fixed
- **MFA setup prompt skipped for demo accounts**: Demo and observer users are no longer shown the MFA encouragement screen on login, since they lack security settings permissions and don't need MFA.

## [v2.75.8] - 2026-03-01

### Added
- **Demo account quick-login buttons**: Login page now shows three demo account buttons (USD Demo, BTC Demo, Both Demo) below the sign-in form for easy one-click access to demo trading accounts.

## [v2.75.7] - 2026-03-01

### Added
- **Session expiry countdown**: A red banner appears 30 seconds before session expiry with a live countdown ("Session expires in 15s — you will be logged out automatically").

### Fixed
- **Game over "Games" button**: Clicking the "Games" button in the game over modal now correctly returns to the games hub instead of redirecting back to the same game.

## [v2.75.6] - 2026-03-01

### Fixed
- **Session cooldown false positives**: Expired sessions were recording `ended_at = now` (cleanup time) instead of `ended_at = expires_at` (actual expiry time). This caused relogin cooldowns to trigger incorrectly — even hours after a session expired, logging in would hit the cooldown because the system thought the session just ended.

## [v2.75.5] - 2026-03-01

### Changed
- **Reports page uses RBAC permissions**: Replaced hardcoded `isDemoAccount` email check with proper `reports:write` and `reports:delete` RBAC permission checks for all create/edit/delete controls.
- **Dashboard bot controls respect RBAC**: Start/Stop buttons on dashboard bot cards are disabled for users without `bots:write` permission.
- **Read-only icons**: Goal and schedule edit buttons show an Eye icon (instead of Pencil) for read-only users.
- **Demo bot max deals**: USD-based demo bots now allow 10 concurrent deals (was 5), matching BTC-based demo bots.

### Fixed
- **History shows only completed trades**: Reverted inclusion of failed positions (which never traded) in the closed positions list — only fully executed trades appear in History now.

## [v2.75.4] - 2026-03-01

### Fixed
- **Paper trading portfolio crash**: Portfolio page returned 500 for demo users with altcoins that lack BTC trading pairs (TON, BAND, HBAR, etc.). Now falls back to USD pair pricing, so all holdings show accurate values.
- **Plinko ball drop animation**: Balls now drop from just off-screen instead of appearing mid-board — a natural gravity-drop entrance.

## [v2.75.0] - 2026-03-01

### Added
- **Read-only bot modal for demo users**: Demo users can now view bot configurations via "View Bot" in the actions menu — all fields visible but disabled, no save/create button.
- **Read-only goal modal for demo users**: Demo users can click goals to view their full configuration in a read-only modal with all fields visible but disabled.
- **Read-only schedule modal for demo users**: Demo users can click schedules to view their full configuration in a read-only modal with all fields visible but disabled.
- **Games navigation persistence**: Navigating away from a game and back to the Games hub automatically resumes the last game you were playing. Explicitly clicking "Back to Games" returns to the hub.

### Changed
- **Plinko bounce physics restored**: Ball drops now use reflection-based bounce physics with Galton rotation (matching the v2.70.5 feel) instead of pure deflection. Minimum speed floors prevent ball death at lower rows while preserving the bell-curve distribution.
- **Coin badge tooltips**: Status badges (Approved, Borderline, etc.) on position cards now use custom CSS tooltips with a 250ms delay instead of the native browser tooltip (~1 second delay). Added support for Meme coin category (purple badge).
- **Session relogin cooldown reduced**: Demo account relogin cooldown reduced from 5 minutes to 1 minute.

## [v2.74.0] - 2026-03-01

### Added
- **Paper Traders role**: New default role for registered users — full trading access but cannot add or manage exchange accounts. Platform is paper-trading entertainment only; only admins and traders can manage real accounts.
- **Auto-assign group on registration**: New users (both admin-created and self-signup) are automatically assigned to the Paper Traders group.
- **Limit close modal view-only mode**: Observers can open the limit close interface to explore pricing, depth charts, and order details, but cannot submit orders. Submit button shows "View Only" when read-only.

### Changed
- **Account management gated by RBAC**: Add Account, Delete, Convert Portfolio, Link Perps, paper trading deposit/withdraw/reset, and auto-buy settings now check `accounts:write` permission instead of just demo account detection. Controls remain visible but disabled for users without permission.
- **Position card read-only for observers**: Notes show as plain text (no edit prompt), market close/cancel/add funds/edit deal/resize budget buttons hidden, while "Close at limit" remains accessible in view-only mode.

### Fixed
- **Bot menu dropdown positioning**: Action menu no longer pins to top of screen when space is tight — now stays near the button and scrolls within available viewport space.

## [v2.73.2] - 2026-03-01

### Fixed
- **Expense items viewable by demo users**: "View Expenses" button now visible on expense goals for demo users (was completely hidden). Opens the expense list in read-only mode — no add, edit, delete, or reorder controls.

## [v2.73.1] - 2026-03-01

### Added
- **Expense-covering goals for demo users**: Each demo account now has a realistic household expense goal with 25% tax withholding — renter lifestyle (demo_usd, 18 items), urban minimalist (demo_btc, 15 items), family household (demo_both, 23 items).
- **Semi-monthly expense schedule**: Each demo user gets a semi-monthly schedule (1st & 15th, MTD) linked to all goals, matching Louis's scheduling pattern.

## [v2.73.0] - 2026-03-01

### Added
- **Session limits system**: Per-group and per-user session policies with configurable timeout, max simultaneous sessions, max sessions per IP, re-login cooldown, and auto-logout. Policies resolve most-restrictive across all user groups with optional per-user overrides.
- **Session limits admin UI**: Group and user session policy editors in the admin panel, with effective policy viewer and active session management (view/force-end).
- **Session limits popup**: Full-screen notice shown after login when session limits are active, listing all applicable restrictions in plain language.
- **Auto-logout timer**: Frontend automatically logs out users when their session expires (if auto_logout is enabled in their policy).
- **Demo login shortcuts**: `/demo_usd`, `/demo_btc`, `/demo_both` URL paths auto-login to the corresponding demo account with full session limits enforcement.
- **Demo user goals and reports**: Each demo account seeded with 2 balance goals, 1 expense goal with items, and 2 report schedules (weekly + monthly) linked to their paper trading accounts.
- **Demo AI provider configuration**: Demo accounts pre-configured with Gemini AI credentials for report generation.
- **Session cleanup job**: Daily background task expires stale sessions and purges old inactive sessions (>30 days).

### Changed
- **Deal/position RBAC**: All 12 position write endpoints (close, force-close, edit settings, resize budget, add funds, notes, limit orders, perps TP/SL) now require `positions:write` permission. Read endpoints unchanged.
- **Account RBAC**: All 6 account write endpoints (create, update, delete, set-default, link-perps, auto-buy settings) and 3 paper trading endpoints (deposit, withdraw, reset) now require `accounts:write` permission.
- **AI provider RBAC**: Create, update, and delete AI credentials now require `settings:write` permission. Demo users see providers read-only.
- **Reports RBAC**: Goal/schedule/expense create/update require `reports:write`, delete operations require `reports:delete`. Demo users see reports read-only.
- **Database maintenance**: Settings page DB maintenance section now restricted to admin-level users (was superuser-only).
- **Demo account lockdown**: Demo users see all features but cannot modify accounts, paper trading balances, AI providers, goals, schedules, or reports. Controls are visible but disabled with appropriate styling.
- **Login error messages**: Session limit errors (max sessions, cooldown) now show user-friendly messages with specific details instead of generic errors.

### Security
- **24 write endpoints gated**: Comprehensive RBAC enforcement across positions, accounts, paper trading, AI credentials, and reports — observers/demo users cannot modify data.
- **Session tracking**: All sessions tracked in database with IP, user agent, and expiry. Stale sessions automatically reclaimed.

## [v2.72.0] - 2026-03-01

### Added
- **Role-based access control (RBAC)**: Full Users → Groups → Roles → Permissions hierarchy replaces the single `is_superuser` flag. Includes 4 built-in groups (System Owners, Administrators, Traders, Observers), 4 roles (super_admin, admin, trader, viewer), and 29 granular permissions.
- **Admin management page**: New `/admin` page with Users, Groups, and Roles tabs for managing RBAC assignments. Admins can enable/disable users, assign group memberships, create custom groups and roles, and configure permission sets.
- **Permission-gated dependencies**: New `require_permission()` and `require_role()` FastAPI dependency factories for endpoint-level access control. Superusers bypass all checks for backward compatibility.
- **Frontend permission hooks**: `usePermission`, `useHasPermission`, and `useIsAdmin` hooks for conditional UI rendering based on RBAC permissions.
- **Admin nav link**: Yellow shield icon in the navigation bar, visible only to users with admin-level permissions.

### Changed
- **Admin endpoint protection**: All 6 blacklist admin endpoints, the user registration endpoint, and template seeding now use `require_superuser` dependency instead of inline checks.
- **Seasonality toggle scope**: Added `scope` parameter (`all` or `own`) to the seasonality toggle endpoint.
- **User login response**: Now includes `groups` and `permissions` arrays resolved from the RBAC chain.
- **Config defaults**: `ses_sender_email` and `frontend_url` default to empty strings instead of hardcoded operator-specific values.

### Fixed
- **Dead code branches**: Removed 4 instances of `current_user.id if current_user else None` (user is always present when authenticated).

### Security
- **MFA enforcement on admin groups**: Users cannot be assigned to groups containing MFA-requiring roles unless they have MFA enabled.
- **System entity protection**: Built-in groups and roles cannot be deleted through the admin interface.

## [v2.71.0] - 2026-02-28

### Added
- **Comprehensive test coverage sweep**: 48+ new test files covering backend monitors, routers, services, indicators, price feeds, news data, and frontend contexts, hooks, and pages. Over 700 new tests total.

### Fixed
- **Bull flag position creation**: Fixed 3 production bugs in `bull_flag_processor.py` — position creation used non-existent `total_quantity` column (now `total_base_acquired`), exit sell orders read wrong field, and invalid `strategy_type` kwarg was passed to Position constructor.
- **Sell executor limit order tests**: Mock exchange was incorrectly detected as paper trading, causing limit sell path to be skipped in tests.
- **API test assertions**: Fixed frontend API test assertions that didn't match actual call signatures for `positionsApi.close`, `reportsApi.getGoals`, and `reportsApi.getSchedules`.

## [v2.70.5] - 2026-02-28

### Added
- **Solitaire hint button**: New "Hint" button highlights the best available move with amber pulse animation. Prioritizes foundation moves, then tableau moves that expose hidden cards, then waste plays. Detects and displays "No more moves available" when the game is stuck.

### Changed
- **Plinko peg alignment**: Classic layout pegs now align with slot positions — bottom row has a peg centered above each slot opening for proper 50/50 deflection. Even vertical spacing between all peg rows including the gap to the slot dividers.
- **Plinko center bias**: Peg collisions now use a Galton board 50/50 coin flip for left vs right deflection with random magnitude (9°–30°), matching the binomial distribution used by real Plinko boards. Balls always deflect meaningfully to one side instead of occasionally going straight through.

## [v2.70.4] - 2026-02-28

### Fixed
- **Plinko Pyramid/Diamond layouts**: Layouts now render correct shapes — pyramid widens from 3 pegs at top to 12 at bottom, diamond narrows at top and bottom with 12 pegs in the middle. Pegs use consistent spacing and centering instead of stretching every row to full width.
- **Solitaire black card text**: Clubs and spades are now dark text on the white card face (was nearly invisible light gray).
- **Solitaire face-down cards**: Tableau face-down cards now render with proper card height instead of collapsing to thin blue lines.

## [v2.70.3] - 2026-02-28

### Fixed
- **Plinko physics**: Peg collisions no longer inject energy into the ball. Randomness now comes from rotating the bounce angle (±15°) rather than adding lateral velocity, so balls always leave a peg slower than they arrived — matching real-world peg board behavior.

## [v2.70.2] - 2026-02-28

### Fixed
- **Plinko board not updating**: Changing the board layout (Classic/Pyramid/Diamond) or risk level now immediately redraws the board instead of waiting for a ball drop.
- **Plinko controls during play**: Risk and Board layout buttons are now disabled while balls are still falling, preventing mid-game configuration changes.

### Changed
- **Plinko bet input**: Replaced preset bet buttons with a freeform number input plus ½×, 2×, and Max multiplier buttons for more flexible betting.

## [v2.70.1] - 2026-02-28

### Fixed
- **Chess piece visibility**: Pieces now use filled glyphs with CSS color and outline — white pieces are bright with a dark edge, black pieces are solid dark with a subtle light edge. Both stand out clearly on light and dark squares.

## [v2.70.0] - 2026-02-28

### Added
- **Chess game**: Full chess implementation with AI opponent (minimax + alpha-beta pruning). Supports all rules including castling, en passant, and pawn promotion. Three difficulty levels with piece-square table evaluation.
- **Solitaire game**: Classic Klondike solitaire with click-to-move, undo, and auto-complete. Seven tableau piles, four foundation piles, stock/waste draw.
- **Memory game**: Card-matching game with CSS 3D flip animations. Three grid sizes (4×3, 4×4, 6×4) across easy/medium/hard difficulties. Move counter and timer.
- **Backgammon game**: Full backgammon vs AI with dice rolling, bar/bearing-off rules, and heuristic AI opponent. Three difficulty levels with pip-count and positional evaluation.
- **Plinko ball-to-ball collision**: Balls now collide with each other using elastic collision physics, adding realistic multi-ball interactions.
- **Plinko slot landing animation**: Winning slot flashes and springs downward when a ball lands, giving satisfying visual feedback.
- **Plinko slot separator pegs**: Pegs now line the borders between slots so balls are cleanly guided into a single slot.

### Changed
- All games now show a visible "New Game" button in the controls bar (previously some only offered restart from the game-over modal).
- Games Hub now includes 17 total games (up from 13).

## [v2.69.0] - 2026-02-28

### Added
- **Checkers game**: Classic checkers vs AI with three difficulty levels (easy/medium/hard), mandatory captures, multi-jump chains, and king promotion. Game state persists across page reloads.
- **Plinko game**: Physics-based arcade game — drop balls through a peg board to land in multiplier slots. Features three risk levels, configurable bets, and balance tracking that persists across sessions.
- **Game state persistence**: New `useGameState` hook saves game progress to localStorage so games survive page reloads and navigation.

## [v2.68.9] - 2026-02-28

### Fixed
- **Mahjong blocked tile visibility**: Blocked (unclickable) tiles now appear subtly shadowed instead of a different yellow color, making it clearer which tiles are free to click.

## [v2.68.3] - 2026-02-28

### Added
- **Mahjong tile theme toggle**: Switch between "Classic" (Unicode/emoji characters with high-contrast colors) and "Kanji" (CJK two-line labels) tile styles using the toggle button in the controls bar.

## [v2.68.2] - 2026-02-28

### Fixed
- **Mahjong tiles more readable**: Replaced hard-to-distinguish Unicode mahjong characters with clear two-line labels (suit symbol + number) color-coded by suit. Winds, dragons, flowers, and seasons now show distinct CJK characters.

## [v2.68.1] - 2026-02-28

### Changed
- **Deal editing auto-resizes budget**: When changing max safety orders on a deal, the position's budget (max_quote_allowed) is automatically recalculated to reflect the new order count. Previously, users had to manually resize the budget after editing.

## [v2.68.0] - 2026-02-28

### Added
- **11 playable browser games**: All games in the Games Hub are now fully implemented and playable:
  - **Tic-Tac-Toe**: Classic 3x3 with AI opponent (easy/medium/hard)
  - **Hangman**: Random word guessing with on-screen QWERTY keyboard
  - **Snake**: Canvas-based with arrow/WASD/swipe/D-pad controls, speed levels
  - **2048**: Slide-to-merge puzzle with arrow/WASD/swipe, undo, score tracking
  - **Connect Four**: Drop-disc strategy with minimax AI (3 difficulty levels)
  - **Minesweeper**: Classic mine-clearing with beginner/intermediate/expert, first-click safety, long-press flagging on mobile
  - **Wordle**: Daily and random modes, hard mode, share results, color-coded keyboard
  - **Nonogram (Picross)**: Logic puzzles at 5x5, 10x10, and 15x15 with validation feedback
  - **Sudoku**: Backtracking-generated puzzles with 4 difficulty levels, notes mode, conflict highlighting, hints
  - **Ultimate Tic-Tac-Toe**: Meta-board strategy game with AI opponent and active-board highlighting
  - **Mahjong Solitaire**: Tile matching with two layouts (pyramid/turtle), shuffle, hint, undo
- **246 game engine unit tests**: TDD test coverage across all 11 game engines

### Fixed
- **Deal editing not persisting**: Editing deal settings (e.g., max safety orders) showed a success message but changes were silently lost. Root cause was SQLAlchemy not detecting in-place mutations on JSON columns. Added `flag_modified()` to ensure changes are committed to the database.

## [v2.67.0] - 2026-02-28

### Added
- **Games Hub**: New "Games" section in the navigation bar with a hub page displaying 11 available browser games organized by category (Puzzle, Strategy, Word, Arcade). Games include Tic-Tac-Toe, Connect Four, 2048, Minesweeper, Hangman, Sudoku, Wordle, Snake, Ultimate Tic-Tac-Toe, Mahjong Solitaire, and Nonogram.
- **Game scaffolding**: Shared components (game layout wrapper, game cards, difficulty selector, game over modal), localStorage-based high score tracking, game timer hook, and keyboard input hook. Individual games will be implemented in subsequent releases.

## [v2.66.6] - 2026-02-27

### Fixed
- **Balances table fills full width on mobile**: Value columns now use flex-grow to distribute available space evenly instead of fixed widths that left a gap on the right.

## [v2.66.5] - 2026-02-27

### Fixed
- **Balances table compact on mobile**: Currency column narrowed from flexible-width to a tight fixed width, eliminating wasted space between the currency name and value columns. All columns now sit in a flat row with consistent spacing.

## [v2.66.4] - 2026-02-27

### Fixed
- **Form inputs accept finer granularity**: All percentage and scale inputs on the bot strategy form now accept values with 2 decimal places (e.g., 1.55% take profit, 2.75% deviation, 1.05x scale). Previously only exact tenths were valid.
- **Safety order scale max raised to 10x**: Volume scale and step scale max increased from 5.0 to 10.0 to support more aggressive DCA strategies.
- **Overall stats panel responsive on mobile**: PnL rows and balances wrap gracefully on narrow screens instead of overflowing. Reduced padding on small viewports.

## [v2.66.3] - 2026-02-27

### Fixed
- **Slippage guard rejected valid values**: Max slippage inputs only accepted values in 0.1 increments (e.g. 0.1, 0.2, 0.3). Values like 0.45 from sample bots triggered a browser validation error. Now accepts any value with up to 2 decimal places.

## [v2.66.2] - 2026-02-27

### Fixed
- **Bot budget now uses only quote-currency assets**: Budget percentage calculation was based on total portfolio value across all markets. A USD bot with 20% budget was getting 20% of the entire portfolio (including BTC holdings converted to USD). Now each bot's budget is calculated from only its native market's assets — USD bots use USD assets, BTC bots use BTC assets, USDC bots use USDC assets, etc.
- **Stablecoin balances no longer conflated**: USDC and USDT balances were being aliased to USD. Each currency is now treated as its own independent market, matching how Coinbase handles them.

## [v2.66.1] - 2026-02-27

### Fixed
- **Consistent currency order in PnL breakdown**: Quote currencies now sort alphabetically (BTC, USD, USDC) across all rows instead of varying by insertion order.

## [v2.66.0] - 2026-02-27

### Changed
- **Realized PnL broken down by quote currency**: All realized PnL rows (today, yesterday, historical, to-date, cumulative, net) now show per-currency amounts instead of converting everything to a single BTC number. USD-quoted trade profits display as native USD, BTC-quoted as BTC. Backend endpoint returns `_profit_by_quote` breakdown for each time period.

### Fixed
- **Realized BTC total was inflated by USD→BTC conversion**: Previously, closing a BTC-USD deal with $228 profit added a fake `0.00338 BTC` to the BTC total. Now `_profit_btc` only contains native BTC-quoted profits.

## [v2.65.4] - 2026-02-27

### Changed
- **Independent colors for all PnL values**: Every BTC and USD amount across all PnL rows (uPnL, Realized today, historical, to-date, cumulative/net) is now colored green or red based on its own sign. Previously the entire line used one color.
- **Pipe divider for PnL values**: Replaced `/` with `|` between BTC and USD amounts for cleaner readability.

## [v2.65.3] - 2026-02-27

### Fixed
- **uPnL per-currency colors**: Each currency in the uPnL breakdown is now colored independently — a positive BTC amount shows green even if the USD amount is negative, and vice versa.

## [v2.65.2] - 2026-02-27

### Fixed
- **Wildly inflated unrealized PnL when mixing quote currencies**: Paper trading showed "+$6M" when BTC-USD and ETH-BTC deals were open simultaneously. The USD-quoted profit was being multiplied by the BTC/USD price again. Now correctly handles USD, USDC, USDT (pass through), BTC (convert with live price), and other quote currencies. uPnL display shows per-currency breakdown with accurate USD total.

## [v2.65.1] - 2026-02-27

### Fixed
- **The Independent articles returning summary only**: Article content fetcher was blocking The Independent Entertainment articles because their RSS feed uses a redirect domain (`the-independent.com`) that differed from the source's registered domain (`independent.co.uk`). Added domain alias support so redirect/CDN domains are recognized.

## [v2.65.0] - 2026-02-27

### Added
- **Full-article news sources for 4 categories**: Politics, Nation, Entertainment, and Sports now have full-article sources. Added 12 new robots.txt-verified sources (Salon, ProPublica, Democracy Now, The Independent, Common Dreams, ET Online, Sports Illustrated) and reclassified 7 existing CBS/PBS sources whose robots.txt allows our user-agent. The "Full Articles Only" filter now returns results in all categories.

### Fixed
- **Slippage guard toast showing $0.00 for altcoins**: The VWAP and price values in slippage guard notifications now use adaptive decimal formatting (2-8 decimals based on price magnitude) instead of always showing 2 decimals. Sub-penny altcoins like SHIB now show meaningful prices instead of "$0.00".

## [v2.64.3] - 2026-02-26

### Fixed
- **Depth chart missing from limit close modal**: The order book depth chart on the right side of the "Close at Limit" modal was not rendering. The orderbook API endpoint was falling back to an unauthenticated client that cannot fetch order book data. Now uses the user's authenticated exchange client.
- **Force-close at market crash**: Closing a deal at market from the Positions page returned a 500 error when the position's strategy used conditions-based take profit (take_profit_percentage was null in the config snapshot). Slippage guard now correctly falls back to defaults.

## [v2.64.1] - 2026-02-26

### Fixed
- **Architecture documentation sync**: Updated architecture.json and ARCHITECTURE.md to reflect all 40 models, 53 migrations, 25 routers, 41 services, 24 core modules, and 20 background tasks in the actual codebase.

## [v2.64.0] - 2026-02-26

### Added
- **Mobile sort on Positions page**: Deals can now be sorted on mobile via a dropdown menu (by Date, PnL, Volume, Pair, or Bot) with ascending/descending toggle, visible below the desktop breakpoint.
- **Background audio playback**: Article reader TTS now continues playing when you switch apps on mobile. Lock screen shows article title, source, and play/pause/next/previous controls via the Media Session API.
- **Safety order cascade execution**: When price drops past multiple safety order trigger levels at once and a DCA condition fires, all eligible safety orders now execute in a single cycle instead of requiring one evaluation per level. Budget-aware — stops when balance is exhausted.

### Fixed
- **Mobile chart modal accessibility**: Chart popup on Positions page now dismisses with Escape key or tapping outside the modal. Improved header wrapping and added bottom padding so the MiniPlayer doesn't overlap chart controls.
- **Bot sort not working**: Sorting deals by "Bot" on the Positions page was silently doing nothing due to a missing switch case.

## [v2.63.3] - 2026-02-26

### Changed
- **Minimap shows only when needed**: The overview minimap now appears only when the main chart doesn't extend to the target date, instead of using a fixed days-from-target threshold. No minimap clutter when the full timeline is already visible.
- **Minimap toggle moved to schedule settings**: The minimap on/off checkbox is now in the schedule's "Chart Display" section alongside horizon and multiplier, instead of being on each individual goal. Simplifies configuration — one place for all chart display options.

### Removed
- **Goal-level chart display section**: Removed the collapsible "Chart Display" section from the goal form (minimap toggle + threshold). All chart display options are now on the schedule.
- **Minimap threshold setting**: Removed the configurable days-from-target threshold — no longer needed since minimap visibility is automatic based on whether the chart reaches the target.

## [v2.63.2] - 2026-02-26

### Fixed
- **Chart clipping not working**: Main trend chart still showed the full timeline to the target date even with a short horizon setting. The clipping function was keeping the original ideal-line endpoint at the target date, which stretched the x-axis. Now creates a synthetic endpoint at the horizon date with an interpolated ideal value.
- **Multiplier precision too coarse**: Look-ahead multiplier input only accepted increments of 0.1 (e.g., 0.33 was rejected). Changed step to 0.01 and minimum to 0.01.

## [v2.63.0] - 2026-02-26

### Added
- **Schedule-level chart horizon**: Chart horizon settings (Auto, Elapsed, Full, Custom) are now configured per schedule instead of per goal, letting you use different zoom levels for the same goal across different report schedules.
- **Period-aware auto horizon**: Auto mode calculates look-ahead as schedule period days multiplied by a configurable multiplier. For example, a quarterly schedule with multiplier 0.33 shows ~1 month ahead.
- **Elapsed fraction horizon**: New "Elapsed" mode sets look-ahead as a fraction of the days elapsed since the goal started. For example, 12 days into a goal with fraction 0.33 shows ~4 days ahead.
- **Look-ahead multiplier in schedule form**: New "Chart Display" section in the schedule modal with horizon mode select and multiplier/fraction input, including computed look-ahead preview text.

### Changed
- **Chart horizon moved from goal to schedule**: The chart horizon select has been removed from the goal form. Minimap settings (toggle + threshold) remain on the goal. A note in the goal form's chart settings directs users to the schedule settings.

### Fixed
- **PDF report generation crash**: Fixed crash when generating PDF reports with trend chart minimaps. The `set_alpha()` method doesn't exist in fpdf2 v2.8.6 — replaced with `local_context(fill_opacity=...)`.

## [v2.62.0] - 2026-02-26

### Added
- **Configurable chart horizon**: Goal trend charts now zoom into the relevant data range instead of showing mostly empty future space. Auto mode keeps data filling ~2/3 of the chart width with a smart look-ahead. Per-goal overrides available: "Full Timeline", "Auto", or custom days.
- **Minimap overview**: A compact full-timeline chart appears below the main trend chart when the goal is far from its target date, with a viewport indicator showing the zoomed region. Rendered in all formats: web preview, email, PDF, and the interactive frontend chart.
- **Chart display settings in goal form**: New collapsible "Chart Display" section lets you configure horizon mode, enable/disable the minimap, and set the minimap visibility threshold (days from target).

## [v2.61.1] - 2026-02-26

### Fixed
- **Report generation crash on expense trend charts**: Fixed TypeError when generating reports with expense goal trend charts. The target endpoint data point (used to extend the ideal line to the goal date) had null values that crashed the SVG, PNG, and PDF chart renderers.
- **Trend chart x-axis dog-leg**: Goal trend charts now space the x-axis proportionally by date instead of by data point index. Previously, a few days of data plus a far-future target endpoint would look flat then spike — now the ideal line slopes smoothly across the full timeline.
- **PDF not generated for reports with expense goals**: The PDF renderer crashed on the same null values as the HTML renderer, resulting in reports stored without a PDF attachment.

## [v2.61.0] - 2026-02-26

### Added
- **Expense goal trend charts**: Expense coverage goals now show interactive progress trend charts in the UI and in emailed reports. The chart plots your actual projected income against the ideal path to full coverage by your target date.

### Changed
- **Expense goal on-track calculation**: "On Track" / "Behind" status for expense goals now compares coverage progress against time elapsed toward the target date, matching how balance and profit goals work. Previously it only showed "On Track" at 100% coverage.

### Fixed
- **Missing on-track indicator for expense goals**: The HTML report now shows "On Track" or "Behind" next to the coverage percentage for expense goals, matching the status badges already shown on balance and profit goals.

## [v2.60.5] - 2026-02-26

### Fixed
- **Child voice reading adult content**: Added missing keywords to the TTS child voice content filter. Standalone words like "sex", "drug", "drugs", "illicit", and phrases like "sexual affair", "extramarital", "adultery" were not in the filter, allowing child voices (Ana, Maisie) to read articles about sensitive topics instead of automatically switching to an adult voice.

## [v2.60.4] - 2026-02-26

### Fixed
- **Report email delivery failure**: Fixed a serialization bug where updating a report schedule corrupted recipient email addresses, causing all email deliveries to fail with "Email delivery failed" status.

## [v2.60.3] - 2026-02-26

### Fixed
- **Expense coverage chart mixing accounts**: Goal progress snapshots for expense and profit goals now correctly filter by the goal's assigned account. Previously, paper trading profits leaked into live account goal charts (and vice versa), inflating the coverage values shown in the trend chart.

### Added
- **Email report color scheme toggle**: Each email recipient can now be set to receive reports in "Dark" (default) or "Clean" (white background, dark text) theme. The clean theme is easier to read on paper or in email clients that struggle with dark backgrounds.

## [v2.60.2] - 2026-02-26

### Fixed
- **Media player UI text in articles**: Stripped "Select Voice", "Select Speed", "1.00x" and other audio player control labels that some news websites embed in their HTML and were being extracted as article text.

## [v2.60.1] - 2026-02-26

### Fixed
- **Volume slider stutter during drag**: The TTS volume slider in the Article Reader now drags smoothly on both desktop and iOS. Previously, frequent time-position updates caused the entire player to re-render during drag, causing visible jank.

## [v2.60.0] - 2026-02-26

### Changed
- **Major structural refactoring**: Eliminated all spaghetti-check findings — 1 CRITICAL bidirectional dependency, 137 HIGH, and 230 MEDIUM structural issues resolved across the entire codebase.
- **auth_router.py split into sub-routers**: 2151-line monolith decomposed into 9 focused modules under `auth_routers/` (core auth, email verification, password reset, TOTP MFA, email MFA, device trust, preferences, shared helpers, rate limiters).
- **multi_bot_monitor.py split into monitor package**: 2039-line file decomposed into focused modules (`batch_analyzer`, `pair_processor`, `bull_flag_processor`) with the core class trimmed to 861 lines.
- **Business logic extracted from routers to services**: `account_router` (1035→176 lines), `news_metrics_router` (1105→323 lines), `accounts_router` (1132→893 lines), `reports_router` (1262→1065 lines) — all now thin endpoint wrappers.
- **news_router ↔ news_fetch_service circular dependency eliminated**: Moved 12 business logic functions from router to service layer, fixing the only CRITICAL finding.
- **God functions decomposed**: `process_signal()` (951 lines, CC=86) broken into 7 focused helpers; `execute_buy()`/`execute_sell()` decomposed with shared `fill_reconciler` module.
- **Strategy definitions made data-driven**: `get_definition()` methods in `indicator_based.py` and `grid_trading.py` converted from 400+ lines of constructor calls to compact parameter config lists.
- **Domain exceptions replace HTTPException in services**: New `exceptions.py` with `AppError`, `ValidationError`, `ExchangeUnavailableError`, `NotFoundError` — services no longer coupled to FastAPI.
- **Parameter dataclasses for heavy-param functions**: `create_exchange_client()`, `log_order_to_history()`, `broadcast_order_fill()` now use typed dataclass parameters instead of 10-15 positional args.
- **Frontend components extracted**: `News.tsx` (1586→477 lines) split into `ArticleSection`, `VideoSection`, `NewsFilterBar`, `ArticlePreviewModal`. `BotFormModal.tsx` (1540→1362 lines) with `useBotForm` hook, `CoinCategorySelector`, `StrategyConfigSection` extracted.

## [v2.59.4] - 2026-02-25

### Fixed
- **TTS generation timeout on long articles**: Increased backend TTS timeout from 60s to 90s and frontend timeout from 45s to 90s to handle long uncached articles on t2.micro.
- **TTS resource waste on disconnect**: Backend now detects client disconnects during TTS generation and cancels early instead of finishing unused audio.
- **TTS prefetch blocking**: Prefetch endpoint no longer blocks when user already has TTS in flight, preventing queue stalls.

### Changed
- **TTS loading indicator**: Play button now shows "Loading..." or "Generating..." status text under the spinner so users can see what's happening.

## [v2.59.3] - 2026-02-25

### Added
- **Test coverage sweep**: Added 374 unit tests across 11 previously untested modules including trading engine, exchange clients, AI service, URL utilities, robots checker, brand service, and several routers (transfers, seasonality, account value, order history).

## [v2.59.2] - 2026-02-25

### Fixed
- **Paper trading balance race condition**: Multiple paper bots running concurrently on the same account could silently overwrite each other's balance changes (last writer wins). Balance operations are now serialized with per-account locks and always re-read from the database before modifying.
- **Paper balance data repair**: Restored lost balances for UNI, BCH, and ATOM on the paper trading account by reconciling with open position holdings. Cleared the "Insufficient UNI balance" error on deal #212.
- **Dashboard transfer note on paper accounts**: The deposit/withdrawal note no longer shows for paper trading accounts, which have no real deposits.

### Added
- **Database VACUUM on startup**: SQLite VACUUM runs automatically at startup to reclaim space and optimize page layout.

## [v2.59.1] - 2026-02-25

### Fixed
- **Dashboard chart crash on account toggle**: Clicking the "Showing: paper trading" / "Showing: All Accounts" button threw "Object is disposed" errors because chart series refs weren't cleared when the chart was recreated. Series refs are now properly nulled on disposal.
- **"All Accounts" toggle hidden for paper trading**: When a paper trading account is selected, the "Showing: All Accounts" button is no longer shown since mixing real and paper trading data in one chart is meaningless.

## [v2.59.0] - 2026-02-25

### Added
- **Expense changes tracking in reports**: Reports now show what changed since the prior report — items that increased, decreased, were added, or were removed, with color-coded deltas in both HTML emails and PDF exports.
- **Orphaned pending order sweep**: The limit order monitor now automatically cleans up stale pending order records whose positions are already closed, running every 5 minutes.
- **Paper order auto-resolution**: Paper trading orders stuck as "pending" are now automatically detected and resolved as filled by the limit order monitor.

### Fixed
- **Paper trading limit orders permanently stuck**: Paper trading accounts that used limit sell orders would create phantom "pending" records that could never be resolved, blocking all future sell evaluation for those positions. Paper accounts now correctly skip the limit order path and execute as market orders.
- **Case-insensitive order status matching**: The limit order monitor now normalizes status strings to uppercase before comparison, preventing mismatches between exchange clients that return different cases (e.g., "filled" vs "FILLED").
- **Trailing mode slippage guard too restrictive**: Trailing take-profit exits were blocked by the same raw slippage check as fixed mode, which asks the wrong question for a trailing exit. Trailing mode now uses the VWAP profit floor check (like minimum mode), allowing profitable exits even when the order book is thin.
- **Silent failures in limit order monitor**: Unrecognized order statuses now log a warning instead of silently doing nothing.

### Changed
- **Order fill sound effects**: Buy orders now play a descending tone (money spent) and sell orders play an ascending chime (money made), swapping the previous assignment.

## [v2.58.2] - 2026-02-25

### Fixed
- **Chart labels overlapping recent candles**: Added right-edge padding to all chart panels so price labels and last-value markers don't crowd the most recent candles.

## [v2.58.1] - 2026-02-25

### Fixed
- **Chart zoom shrinks past data bounds**: The actively-scrolled chart could zoom out beyond its data edges while synced charts stopped at their bounds, creating visual gaps. All charts now anchor to their data edges so zoom and pan stay consistent across panels.

## [v2.58.0] - 2026-02-25

### Added
- **Market selector with search**: Charts page now has a searchable pair dropdown with market tabs (USD, USDC, BTC, etc.) replacing the basic select element. Portfolio pairs are highlighted with a green dot and sorted first.

### Fixed
- **Chart controls require page refresh**: Changing chart type, time interval, or indicators now takes effect immediately without needing to refresh the page. Only Heikin-Ashi toggle worked before — now all controls update the chart in real-time.
- **Indicator charts not syncing with main chart**: Zooming or panning the main price chart now correctly syncs RSI, MACD, and Stochastic panels, and vice versa.
- **MACD chart missing Y-axis values**: The MACD oscillator panel now displays price scale values on the right axis.
- **Unnecessary API re-fetches**: Changing display-only settings (chart type, HA toggle, indicators) no longer triggers a data re-fetch — only pair or interval changes fetch new candle data.

## [v2.57.0] - 2026-02-25

### Added
- **Expense coverage goal trend charts**: Expense goals now display actual-vs-ideal progress charts showing income after tax trending toward full expense coverage over time. Charts appear in web reports (SVG), emailed reports (PNG), and PDF reports — matching the visual style of existing balance/profit goal charts.
- **Expense goal daily snapshots**: The daily snapshot cycle now captures progress for expense goals, enabling historical trend tracking and chart rendering.
- **Expense goal backfill**: When generating a report for a goal with no prior snapshots, historical data is automatically backfilled from closed-position profit history.

## [v2.56.4] - 2026-02-25

### Fixed
- **AI summary incorrectly reporting withdrawals**: When no deposit/withdrawal records exist (e.g. paper trading), the AI summary was misinterpreting an accounting residual as "net withdrawals" — attributing BTC price drops to money being withdrawn. The prompt now clearly separates confirmed transfers from valuation reconciliation and instructs the AI to never use deposit/withdrawal language when no transfer records exist.

## [v2.56.3] - 2026-02-25

### Fixed
- **Paper trading portfolio missing altcoin values**: Account value in the header and portfolio page only counted BTC, ETH, and USD balances — all other altcoins (LTC, AAVE, ADA, GRT, COMP, etc.) were valued at $0. Now fetches live BTC prices for every held altcoin so both the BTC and USD totals accurately reflect the full portfolio.

## [v2.56.2] - 2026-02-25

### Fixed
- **Crossing detection missing rapid threshold crossings**: When an indicator (BB%, RSI, etc.) moved through a threshold within 1-2 candle periods, the crossing was missed because the candle-based previous value was already on the same side of the threshold. Now also checks the cycle-based previous (from the last bot check) to catch these rapid crossings. Affects all crossing_above/crossing_below conditions for both live and paper trading bots.

## [v2.56.1] - 2026-02-25

### Fixed
- **Force-close on paper trading positions**: Manual close button now correctly uses the paper trading client instead of the real exchange client, which was causing a 500 error

## [v2.56.0] - 2026-02-25

### Changed
- **Report generator modularized**: Split the monolithic report generator (2900+ lines) into three focused modules — `expense_builder`, `html_builder`, and `pdf_generator` — improving maintainability with zero changes to report output

## [v2.55.6] - 2026-02-25

### Fixed
- **PDF table borders crossing page breaks**: All bordered tables (expense coverage, upcoming, lookahead, transfers) now check remaining page space and break to a new page before rendering if needed, preventing split borders
- **PDF expense summary label**: Changed "Total:" to "Total Required:" so users don't confuse expense target with income

### Changed
- **PDF deposit guidance text**: The "Finish covering / Then cover / Cover all" deposit hints below expense tables now use a smaller centered font with spacing to visually associate them with the table above
- **PDF section spacing**: Added vertical gaps before "Next Month Preview" and "Projections" headers for clearer visual separation

## [v2.55.5] - 2026-02-25

### Changed
- **PDF transfers table styled to match other tables**: Individual transfer rows now use the same inset table style with header row, zebra striping, border outline, and measured column widths as expense coverage tables

## [v2.55.4] - 2026-02-25

### Fixed
- **PDF report section ordering**: Goals and expense coverage now appear above Capital Movements in PDF reports (matching the email/web fix in v2.55.3)

## [v2.55.3] - 2026-02-25

### Fixed
- **Goal trend charts now display in emailed reports**: Charts are rendered as PNG images and embedded via CID inline attachments, since email clients strip SVG tags
- **Report section ordering improved**: Goals and expense coverage now appear above Capital Movements in email and web report views

## [v2.55.2] - 2026-02-25

### Fixed
- **Native-currency accounting works on historical snapshots**: BTC price is now derived from existing snapshot data when not stored directly, so reports covering periods before v2.55.0 also get accurate market value effect and deposit calculations

## [v2.55.1] - 2026-02-25

### Fixed
- **AI report summaries now explain market context**: AI summaries include BTC start/end prices, open position value changes (e.g. ETH price movement), and clear instructions to separate market conditions from trading performance and capital movements

## [v2.55.0] - 2026-02-25

### Added
- **Market Value Effect metric**: Reports now show how much of the account's USD value change is attributable to BTC price movement alone, separate from trading performance and deposits
- **Native-currency accounting for deposits/withdrawals**: Report deposit calculations now work per-currency in native units (BTC in BTC, USD in USD) before combining, eliminating phantom deposits/withdrawals caused by BTC price swings
- **Unrealized PnL tracking in snapshots**: Daily account snapshots now capture unrealized profit/loss from open positions and the current BTC/USD price, enabling more accurate deposit isolation

### Fixed
- **All accounts (not just paper) showing phantom withdrawals**: BTC price drops were misattributed as large withdrawals in any account holding BTC — native-currency accounting now correctly separates market movement from actual capital flows

### Removed
- Paper trading workaround for implied deposits — replaced by the universal native-currency accounting fix

## [v2.54.3] - 2026-02-25

### Fixed
- **Orphan image cleanup**: News article cleanup now deletes the exact articles it collected file paths for, preventing image and TTS files from being left on disk when their DB records are removed

### Removed
- Eliminated redundant `cleanup_old_articles()` function that duplicated deletion logic and caused the orphan file leak

## [v2.54.2] - 2026-02-25

### Fixed
- **Paper trading reports showing phantom withdrawals**: BTC price drops were being misattributed as large withdrawals in paper trading account reports — paper accounts now correctly skip the implied deposit/withdrawal calculation

## [v2.54.1] - 2026-02-25

### Fixed
- **Reports missing today's trades**: Month-to-date, week-to-date, and other "to-date" reports now include trades closed today — previously the period end was truncated to midnight, excluding anything after 00:00 UTC

## [v2.54.0] - 2026-02-25

### Added
- **Donations expense category**: New built-in category for tracking charitable giving and tithes
- **Percent-of-income expenses**: Donation items can be set as a percentage of pre-tax or post-tax income instead of a fixed dollar amount — the calculated amount updates dynamically with income projections
- **Amount mode toggle**: When adding a Donations expense, choose between "Fixed Amount" or "% of Income" modes with a pre/post tax selector

### Fixed
- **PDF report crash**: Fixed encoding error when generating PDF reports with expense coverage titles (Unicode em-dash in title string was incompatible with Helvetica font)

## [v2.53.6] - 2026-02-25

### Changed
- **PDF expense coverage table**: Reordered columns to Category | Name | Amount | Status for better readability
- **PDF expense coverage title**: Now reads "Returns Cover X% of Monthly Expenses" instead of the redundant "(Expenses/Monthly) - X% Covered"

## [v2.53.5] - 2026-02-25

### Changed
- **PDF expense tables**: Tables are now slightly narrower than page content with a light outline border, header separator line, and zebra-striped rows for easier horizontal scanning
- **PDF expense tables**: Column widths now auto-size to fit the widest value in each column instead of using fixed widths — Upcoming and Next Month Preview tables share consistent column sizing

## [v2.53.4] - 2026-02-25

### Fixed
- **PDF expense coverage table**: Widened Category column so long names like "Marriage Settlement Agreement" no longer bleed into adjacent columns
- **PDF upcoming and next month preview tables**: Same Category column width fix to prevent text overlap with Name column

## [v2.53.3] - 2026-02-25

### Fixed
- **PDF expense coverage table**: Reduced Name column width so Category and Amount fields no longer overlap
- **PDF next month preview table**: Now matches the Upcoming table layout with Category and color-coded Status columns

## [v2.53.2] - 2026-02-25

### Added
- **Slippage guard on manual close**: "Close at market" on deal cards now checks order book depth before selling — warns the user if slippage will erode profit, with options to proceed anyway or switch to a limit order
- **Stop loss helper text**: Stop loss field now shows a % suffix and explains the value (e.g. "-10 = sell at a 10% loss")

### Fixed
- **Stop loss always sells at market**: Stop loss and trailing stop loss now force market orders regardless of take-profit order type configuration — previously a limit TP config could cause stop losses to place limit orders instead of executing immediately

## [v2.53.1] - 2026-02-25

### Changed
- **Slippage guard enabled on all sample bots**: New bots created from templates now have slippage guard on by default
- **README updated**: Added slippage guard to safety features and strategy features documentation

## [v2.53.0] - 2026-02-25

### Added
- **Slippage Guard**: New toggleable order book depth check before market orders — blocks execution if estimated slippage exceeds the configured threshold (buy and sell sides)
- **Per-phase order execution type**: Base orders and DCA orders can now independently be set to market or limit execution

### Changed
- **Take Profit mode redesign**: Replaced legacy trailing/condition fields with a clear three-mode selector — Fixed (sell at TP%), Trailing (trail from peak after TP%), Minimum (TP% is floor, conditions trigger exit)
- **Default exit order type changed to market**: New bots default to market exit orders instead of limit
- **Coverage items table in PDF reports**: Improved formatting with color-coded status badges and columnar layout

## [v2.52.9] - 2026-02-25

### Fixed
- **Expense reorder endpoint unreachable**: Fixed route ordering so the reorder endpoint is matched before the parameterized expense item routes (was returning 422)

## [v2.52.8] - 2026-02-25

### Fixed
- **Expense order persists to waterfall**: Reordering items in Manage Expenses now saves and reflects in the coverage waterfall; list and waterfall always use user-defined sort order

## [v2.52.7] - 2026-02-25

### Fixed
- **Header pills uniform height**: All three header pills (market season, account switcher, paper trading toggle) now share the same fixed height; removed multi-line subtitle from account switcher button

## [v2.52.6] - 2026-02-25

### Fixed
- **Edit expense overlay too transparent**: Darkened the overlay behind the edit form in the Manage Expenses modal

## [v2.52.5] - 2026-02-24

### Changed
- **Expense sort moved to Manage Expenses modal**: Quick-sort buttons (Low→High, High→Low) now live in the expense editor header; removed waterfall order selector from goal creation form
- **Waterfall always uses user-defined order**: Expense coverage waterfall respects the manual item order set in the editor

## [v2.52.4] - 2026-02-24

### Fixed
- **Expense reorder always available**: Drag-to-reorder, move-to-top/bottom, and move-to-position controls now work in the Manage Expenses modal regardless of waterfall sort mode

## [v2.52.3] - 2026-02-24

### Fixed
- **Uniform header pill heights**: Account switcher and paper trading toggle now match the market season indicator height; reverted unnecessary width constraints

## [v2.52.2] - 2026-02-24

### Changed
- **Uniform header pill widths**: Market season indicator, account switcher, and paper trading toggle now share a consistent minimum width and centered content for a polished header layout

## [v2.52.1] - 2026-02-24

### Fixed
- **News source filter toggle**: Clicking a selected source pill now deselects it (showing all other sources) instead of making it the only selected source — matches category pill behavior

## [v2.52.0] - 2026-02-24

### Added
- **Expense waterfall sort order**: Choose how expenses are prioritized for coverage — smallest first, largest first, or custom drag-to-reorder with move-to-top, move-to-bottom, and move-to-position controls
- **Account name in report headers**: Reports now show the account name (e.g., "Paper Trading") next to the user name in HTML and PDF headers

## [v2.51.2] - 2026-02-24

### Fixed
- **AI report summaries for zero-trade periods**: No longer mentions "0% win rate" or implies poor performance when no trades closed — focuses on account value and capital movements instead

## [v2.51.1] - 2026-02-24

### Fixed
- **Paper trading reports showing live income**: Income and expense goal calculations now filter by account, so paper trading reports only show paper trading profits and vice versa

## [v2.51.0] - 2026-02-24

### Added
- **Bot actions menu on deal cards**: Click the bot name on any position card to stop/start the bot or open it for editing in the Bots page
- **Persistent deal chart settings**: Chart type, timeframe, Heikin-Ashi toggle, and indicators now persist across deal cards — change settings once and they apply to every chart you open

## [v2.50.1] - 2026-02-24

### Changed
- **Goal form clarity**: Renamed "Time Horizon" to "Goal Deadline" with hint "When you want to reach this goal by". Updated Expense Period hint to "How often to compare income vs expenses"

## [v2.50.0] - 2026-02-24

### Added
- **Paper/Live trading badges on notifications**: Order fill toast notifications now show an amber "PAPER" or green "LIVE" badge so you can immediately tell which account triggered the alert

### Fixed
- **Deal chart Y-axis label duplication**: Fixed a bug where entry, TP, SL, and SO price labels on the expanded deal chart would duplicate every few seconds until the axis was unreadable
- **Position card notes click region**: Narrowed the clickable area for the notes placeholder to just the icon and text, instead of spanning the full card width
- **setup.py schema sync**: Added 3 missing tables (email_verification_tokens, prop_firm_state, prop_firm_equity_snapshots), 6 missing columns, fixed 2 wrong defaults, and synced seed data (151 content sources, 352 coins) to match the current database schema
- **update.py color constant**: Fixed undefined `Colors.FAIL` reference (now `Colors.RED`)

### Changed
- **De-branded documentation and code**: Replaced all competitor-specific references with neutral language across README, docs, and code comments. Renamed `ThreeCommasStyleForm` component to `DCABudgetConfigForm`

## [v2.49.1] - 2026-02-24

### Changed
- **README comprehensive update**: Added missing feature descriptions for reports & goal tracking, account value charts, transfer tracking, closed positions page, paper trading details, in-app version history, and account-scoped isolation. Updated comparison table, safety features, roadmap, and database stores sections to reflect v2.30–v2.49 features.

## [v2.49.0] - 2026-02-24

### Added
- **News filter toggle behavior**: ALL button now toggles between all and none for both categories and sources (articles and videos). Categories can be fully deselected for empty results. Source selection memory persists across category changes.

### Fixed
- **Paper trading products page error**: Fixed 500 on `/api/products` for paper trading accounts — was calling non-existent `get_products()` instead of `list_products()` on the exchange adapter
- **Paper trading snapshot capture error**: Fixed `'CoinbaseAdapter' has no attribute 'get_price'` by using the correct `get_current_price()` method
- **Paper trading session persistence**: Paper balance saves now use `db.merge()` to re-attach Account objects that may have become detached, preventing "not persistent within this Session" errors
- **History page rate limiting**: Reduced last-seen-history polling from every 2 seconds to every 30 seconds, preventing 429 Too Many Requests errors

## [v2.48.0] - 2026-02-24

### Added
- **Account value chart split view**: New "By Quote Currency" toggle on the Dashboard chart shows where capital is deployed — USD Portion (free USD/USDC/USDT + USD-quoted positions) and BTC Portion (free BTC + BTC-quoted positions) as separate lines
- **Account-scoped reports and goals**: Reports and goals can now be linked to a specific exchange account instead of always aggregating across all accounts

### Changed
- **SQLite foreign keys enforcement**: `PRAGMA foreign_keys = ON` now enabled on all connections, preventing orphaned records from accumulating
- **Paper trading resilience**: Paper balance saves now retry on SQLite lock contention instead of failing immediately

## [v2.47.0] - 2026-02-24

### Added
- **Bulk delete for report history**: Select multiple reports with checkboxes and delete them all at once — email-app-style multi-select with select-all, bulk action bar, and confirmation dialog
- **AI summary toggle per schedule**: New toggle switch in schedule settings to enable/disable AI-powered insights — skips AI provider calls entirely when off, useful when credits are exhausted or summaries aren't needed
- Toggle switches for all schedule boolean settings (Enabled, AI Insights, Expense Preview) — consistent, modern UI replacing old checkboxes

### Fixed
- **AI credential error message**: Reports now show "AI insights temporarily unavailable — provider rate-limited or credits exhausted" instead of the misleading "Add AI provider credentials" when providers exist but calls fail
- **Stray delimiter artifacts in AI summaries**: AI-generated `---DELIMITER---` text no longer leaks into rendered report content
- **Maintenance page CSP compliance**: Nginx maintenance page now uses external script instead of inline (blocked by CSP)

## [v2.46.0] - 2026-02-24

### Added
- **Expense goal lookahead**: xTD reports now show a greyed-out "Next Month Preview" (or Next Week/Quarter/Year) section beneath Upcoming Expenses, displaying bills due in the first 15 days of the next period — no more surprise rent on the 1st
- **Togglable per schedule**: New "Show next-period expense preview" checkbox in schedule settings (enabled by default), only visible when an expenses goal is linked
- **Auto-prior suppression**: Lookahead automatically hides on period-start days (1st of month, Monday) when reports auto-switch to full prior period view

## [v2.45.3] - 2026-02-24

### Fixed
- **TradingView chart loading**: Fixed Content Security Policy blocking TradingView widget scripts and iframes — charts now load correctly in deal view

### Added
- **CSP audit script**: New `scripts/audit_csp.sh` detects mismatches between frontend external URLs and nginx CSP headers before they reach production
- **Spaghetti check command**: New `/spaghetti-check` command audits code length, modularity, and separation of concerns across the codebase
- **220 new unit tests**: Comprehensive test coverage for grid trading strategy (19%→92%), AI grid optimizer (10%→100%), email service (33%→100%), report data service (0%→tested), report scheduler (0%→tested), and security headers middleware

### Changed
- **Nginx config template synced**: `deployment/nginx-trading-bot.conf` now matches the live production config including CSP, HSTS, rate limiting, and SSL

## [v2.45.2] - 2026-02-24

### Fixed
- **Show all period transfers**: Removed top-10 transfer limit that was hiding activity before mid-month in reports

## [v2.45.1] - 2026-02-24

### Fixed
- **Staking rewards row visual separation**: Added thicker border under staking rewards summary row to visually separate it from individual transfers below

## [v2.45.0] - 2026-02-24

### Changed
- **Staking rewards aggregated in reports**: Staking reward deposits are now shown as a single summary row (e.g. "Staking Rewards — 12 deposits, +$0.85") in HTML, PDF, and AI reports instead of cluttering the table with individual penny-sized entries

## [v2.44.2] - 2026-02-24

### Added
- **BTC accumulation context for AI**: AI reports now understand the crypto-maximalist thesis behind BTC-pair trading — that alt/BTC trades are a BTC accumulation strategy, not traditional trading with "capital lockup" risk

### Fixed
- **AI strategy context accuracy**: Restructured strategy notes to clearly separate DCA mechanics from investment philosophy, preventing generic risk warnings that miss the point of the strategy

## [v2.44.1] - 2026-02-24

### Fixed
- **AI strategy context accuracy**: AI now receives safety order step scale and volume scale parameters, and understands that safety orders require both a minimum price drop (increasing with each order) AND momentum signals — preventing incorrect claims about premature DCA entries

## [v2.44.0] - 2026-02-24

### Added
- **Bot strategy context in AI reports**: AI summaries now receive actual bot configurations — indicator entry/exit conditions (BB%, RSI, Volume RSI), take profit targets, safety order settings, and DCA mechanics — for bots that had trades in the period, so the AI can accurately interpret win rates and trading patterns

## [v2.43.1] - 2026-02-24

### Fixed
- **PDF generation crash**: Fixed "Not enough horizontal space" error when AI summary had bullet points followed by paragraph text
- **PDF error logging**: PDF errors now include full stack traces

## [v2.43.0] - 2026-02-24

### Changed
- **Two-tier AI report summaries**: Report AI analysis simplified from three tiers (Beginner/Comfortable/Experienced) to two — "Summary" (plain language, encouraging) and "Detailed Analysis" (expert depth, opinionated, may include extra sections like Risk Assessment or Strategy Notes)
- **Expense Coverage section placement**: Expense-type goals now appear immediately after Capital Movements in reports, before other goal types, for better visual flow

### Removed
- **Per-recipient experience level**: Recipients no longer have an experience level setting — all recipients receive the same report with both Summary and Detailed tiers available

## [v2.42.0] - 2026-02-24

### Added
- **Card spend itemization on reports**: Coinbase Card transactions now show as "Card Spend (BTC)" or "Card Spend (USD)" instead of generic "Withdrawal" in HTML, PDF, and AI report summaries
- **Transfer type labels**: All transfers now display descriptive labels — "Bank Deposit", "Bank Withdrawal", "Crypto Transfer", "Exchange Transfer" — across reports and AI narratives
- **Card spend on USD chart line**: Coinbase Card spend markers now appear on the USD line of the Dashboard Account Value chart (previously appeared on BTC line since the currency is BTC)

## [v2.41.1] - 2026-02-24

### Added
- **Marker visibility toggles**: Chart legend items are now clickable — show/hide trade wins, losses, deposits, and withdrawals independently

### Fixed
- **Staking rewards shown as deposits**: Coinbase staking/earn rewards (sub-$1 micro-transfers) no longer appear as deposit markers on the chart
- **AI omitting withdrawals in report narrative**: Strengthened AI prompt to require mentioning both deposits and withdrawals when both occurred, so the math always adds up

## [v2.41.0] - 2026-02-24

### Added
- **Chart activity markers**: Account Value chart now shows categorized markers — trade wins (green), trade losses (red), deposits (blue), withdrawals (amber) — placed on the correct BTC or USD line based on the trading pair or currency
- **Chart activity endpoint**: New `GET /api/account-value/activity` endpoint aggregates closed trades and transfers by day for chart markers
- **Trading summary in reports**: Capital Movements section in HTML, PDF, and AI reports now shows a trading activity summary row ("X trades (YW/ZL), net P&L: +$Z.ZZ") above individual deposit/withdrawal rows
- **Individual transfer table in reports**: HTML, PDF, and AI summaries now show a "Capital Movements" table listing the most recent deposits and withdrawals with dates, types, and amounts

### Changed
- **Adaptive coverage precision**: Expense coverage percentages now use adaptive decimal places — small values like 0.31% no longer misleadingly round to 0%. Applies to HTML badges, PDF badges, goal headers, and AI prompts
- **Deposit metrics always visible**: HTML report Key Metrics section now always shows the Net Deposits and Adjusted Growth row, even when deposits are zero (previously hidden when net deposits were exactly 0)

## [v2.40.16] - 2026-02-23

### Fixed
- **Transfer sync never ran**: CoinbaseAdapter was missing the `get_deposit_withdrawals` method, so the daily transfer sync silently failed — deposits and withdrawals were never recorded. Reports now have accurate deposit/withdrawal data from Coinbase

## [v2.40.15] - 2026-02-23

### Fixed
- **Report AI conflates deposits with trading profit**: AI summaries now always receive capital movement/reconciliation data (account change, trading profit, net deposits) and are instructed to never present account value growth as trading performance
- **Implied net deposits when no transfer records**: When the Coinbase transfer sync has no records, reports now compute implied net deposits from the accounting identity (account change - trading profit) instead of showing $0
- **PDF report crashes on AI bullet rendering**: Fixed fpdf2 "Not enough horizontal space" error when rendering bulleted lists in AI summaries by using explicit width calculation instead of implicit remaining width
- **PDF report missing capital movement metrics**: Period start value, net deposits, and adjusted growth are now always shown in the PDF Key Metrics section (previously only shown when deposits were non-zero)

## [v2.40.14] - 2026-02-23

### Fixed
- **News article thumbnails blocked by CSP**: Broadened `img-src` to allow HTTPS images from any news source domain (previously only YouTube CDN was whitelisted)
- **TTS silence init blocked by CSP**: Added `data:` to `media-src` so the silent WAV used for AudioContext initialization isn't rejected
- **PnL chart console warnings**: Added mount guard to defer Recharts rendering until container has valid dimensions, eliminating repeated "width(-1) and height(-1)" warnings

## [v2.40.13] - 2026-02-23

### Fixed
- **Report AI summaries broken for Gemini**: GeminiClientWrapper didn't forward kwargs (like `system_instruction`) to the underlying Google AI library, causing a silent TypeError that made all Gemini-powered report summaries fail
- **Report AI provider has no fallback**: When a specific AI provider was configured for a report schedule but failed (expired key, service down), the system gave up immediately. Now tries the preferred provider first, then falls back to other available providers

### Added
- **Comprehensive test coverage**: Expanded from 433 tests / 11% coverage to 3,101 tests / 55% backend coverage across 3 rounds of parallel test-writing agents
- **Backend test coverage**: 2,516 tests covering services, routers, strategies, trading engine, exchange clients, Coinbase API, and core logic modules
- **Frontend test coverage**: 585 tests covering contexts, hooks, utilities, helpers, and API service layer

## [v2.40.12] - 2026-02-23

### Fixed
- **Smooth volume slider on mobile**: Slider is now uncontrolled during drag — volume changes go directly to GainNode/audio element with zero React re-renders, then state syncs on release

## [v2.40.11] - 2026-02-23

### Fixed
- **Volume control works on iOS**: GainNode now initialized synchronously during the user gesture (in `stop()`) before any async gaps — fixes iOS AudioContext suspension that caused complete silence

## [v2.40.10] - 2026-02-23

### Fixed
- **Volume control works on iOS**: Added Web Audio API GainNode for volume control — iOS WebKit (used by all iOS browsers including Chrome) ignores `audio.volume`, so GainNode handles actual amplitude. Lazily initialized on first user gesture to avoid iOS AudioContext suspension.

## [v2.40.9] - 2026-02-23

### Fixed
- **Volume slider restored to original smooth behavior**: Removed unnecessary Web Audio API / GainNode complexity that caused stuttering and silence — reverted to simple direct `audio.volume` control which works correctly on Chrome iOS

## [v2.40.8] - 2026-02-23

### Fixed
- **Volume slider draggable on iOS**: Enlarged touch target from 14px to 28px and added `touch-action: none` to prevent iOS from hijacking horizontal drags as scroll gestures

## [v2.40.7] - 2026-02-23

### Fixed
- **Smooth volume slider on mobile**: Volume slider no longer stutters during drag — audio volume changes instantly via direct GainNode/audio element access while React state only updates on release

## [v2.40.6] - 2026-02-23

### Fixed
- **Volume control works on iOS**: Rewrote audio volume to use Web Audio API GainNode with lazy initialization on first user gesture — iOS Safari ignores `audio.volume` entirely
- **Volume slider no longer jittery on mobile**: Changed to uncontrolled input with `step="any"` and `onInput` to prevent React re-render conflicts with touch dragging

## [v2.40.5] - 2026-02-23

### Fixed
- **Article reader volume control on iOS**: Volume slider now works on iPhone/iPad using Web Audio API GainNode (iOS Safari ignores the standard audio.volume property)
- **Volume slider smoothness**: Changed slider step from 5% to 1% for smooth, fine-grained volume control

## [v2.40.4] - 2026-02-23

### Fixed
- **Article reader volume control**: Volume slider in the mini player now immediately changes audio volume instead of being delayed or unresponsive

## [v2.40.3] - 2026-02-23

### Changed
- **Codebase structure cleanup**: Extracted seed data from database.py (1319 → 55 lines), moved bot stats and validation logic into dedicated services, relocated shared frontend types and helpers out of pages/
- **Eliminated dependency violations**: Fixed service→router inversion in news fetch, removed cross-router imports for TTS cache path and position budget helper, fixed 4 frontend component→page import inversions
- **Reduced file sizes**: database.py (-96%), bot_crud_router.py (-33%), accounts_router.py (-15%) — moved business logic to proper service layer

## [v2.40.2] - 2026-02-23

### Added
- **Comprehensive unit test coverage**: Added 333 new tests across backend and frontend, nearly doubling the test suite from 336 to 669 total tests
- **Trading engine tests**: Order logger, trailing stops, position manager budget calculations
- **Auth & security tests**: JWT token handling, encryption roundtrips, token revocation, RequireAuth component
- **Strategy tests**: Grid trading arithmetic/geometric level calculations, condition mirroring for bidirectional bots
- **Business logic tests**: Currency formatting, precision handling, order validation, portfolio conversion service
- **Router helper tests**: Account key masking, SSRF protection for prop firm bridge URLs
- **Frontend utility tests**: Bot indicator detection, position PnL calculations, chart data transforms, news filtering/pagination, markdown-to-text conversion

## [v2.40.1] - 2026-02-23

### Fixed
- **Duplicate version history entries**: The About modal was showing each commit twice because `--no-ff` merges create a merge commit with the same subject as the feature commit — now deduplicated

## [v2.40.0] - 2026-02-23

### Added
- **Structured AI summaries**: AI report summaries now use markdown with consistent section headers (Performance Overview, Goal Progress, Capital Movements, Outlook & Action Items) across all tiers, with styled rendering in both HTML and PDF
- **Expense projection table**: Expenses goal card now shows income projections (daily avg, linear, compound after tax), deposit needed (both models), and trade basis — matching the projection math already available on income goals
- **System message for AI providers**: All three AI providers (Claude, OpenAI, Gemini) now receive a system message that enforces structured output format

### Changed
- **AI summary token limit**: Increased from 2048 to 4096 tokens to support richer structured content across three tiers
- **AI summary HTML rendering**: Switched from plain paragraph splitting to full markdown rendering with dark-theme styled headers, bold, bullets, and italic text
- **PDF AI rendering**: Summaries now render markdown headers in brand color, bullets as indented items, and bold text via fpdf2's built-in markdown support
- **PDF emoji handling**: Emoji characters are now stripped from PDF output (Helvetica lacks emoji glyphs) while preserved in HTML

## [v2.39.7] - 2026-02-23

### Fixed
- **PDF upcoming expenses**: PDF report now uses the same upcoming logic as HTML — correct anchor-aware dates, bill amounts, and current-month scoping
- **DRY upcoming logic**: Extracted shared `_get_upcoming_items` helper used by both HTML and PDF report generators, eliminating duplicated code that was drifting out of sync

## [v2.39.6] - 2026-02-23

### Fixed
- **Upcoming scoped to current month**: Weekly, biweekly, and every-N-days expenses no longer spill into next month in the upcoming tab — only shows what's due the rest of this month

## [v2.39.5] - 2026-02-23

### Changed
- **Upcoming due labels**: Due dates now include the month (e.g., "Fri Feb 27th" instead of "Fri 27th", "Feb 15th" instead of "15th")

## [v2.39.4] - 2026-02-23

### Fixed
- **Upcoming expense amounts**: Upcoming tab now shows the actual bill amount due on that date instead of the monthly-normalized amount

## [v2.39.3] - 2026-02-23

### Fixed
- **Biweekly due dates**: Biweekly expenses with different anchor dates now show correct next due dates instead of both landing on the same week
- **Every-N-days in reports**: Expenses with custom day intervals now appear in the Upcoming tab and show their computed next due date
- **Every-N-days anchor date**: Custom interval expenses can now set a start date in the expense editor so the system knows when to count from

### Added
- **Frontend test infrastructure**: Vitest setup with React Testing Library for frontend unit testing

## [v2.39.2] - 2026-02-23

### Fixed
- **Email reports missing expense data**: Coverage and Upcoming expense sections were hidden in email reports because CSS-only tabs don't work in email clients — now rendered as stacked inline sections
- **PDF reports missing upcoming expenses**: PDF reports only showed expense coverage items but completely omitted the Upcoming expenses section
- **Weekly expense due labels**: Upcoming expense due dates for weekly/biweekly items now show day-of-week and day-of-month (e.g., "Fri 27th") instead of just the day name

## [v2.39.1] - 2026-02-23

### Changed
- **Styled confirmation dialogs**: All native browser confirm/alert popups replaced with themed modal dialogs matching the app's dark trading UI
- **Toast notifications**: Error and success alerts now appear as styled toast notifications instead of browser popups

### Fixed
- **Expense fields not saved on create**: Due day, due month, and login URL were not being saved when creating new expense items (only when editing existing ones)

## [v2.39.0] - 2026-02-23

### Added
- **Expense due month**: Quarterly, semi-annual, and yearly expenses now support a due month selector so you can specify exactly when they're due (e.g., March 15th for annual insurance)
- **Day-of-week selector**: Weekly and biweekly expenses now show pill buttons to pick which day of the week they're due (Mon–Sun)
- **Biweekly start date**: Biweekly expenses can set a calendar anchor date so the "upcoming" tab knows which weeks they fall on
- **Expense login URLs**: Add an optional login URL to any expense — clicking the expense name in the HTML report opens the payment/login page in a new tab
- **Smart upcoming tab**: Upcoming expenses tab now handles weekly, biweekly, and multi-month frequencies correctly — not just monthly

## [v2.38.0] - 2026-02-22

### Added
- **Expense due days**: Set the day of month (1-31 or last day) when each expense is due
- **Upcoming expenses tab**: Report expense cards now have two tabs — "Coverage" (existing waterfall) and "Upcoming" (bills remaining this month sorted by due date)
- **Due day badges**: Expense list in the editor shows a compact "Due 15th" or "Due last" badge next to each item

## [v2.37.1] - 2026-02-22

### Fixed
- **AI summaries now visible in report viewer**: All three AI summary tiers (Simplified, Analysis, Technical) now display correctly when viewing reports in the app — CSS specificity issue prevented tab panels from appearing

### Added
- **`/code-quality` command**: New slash command to run comprehensive code quality sweeps across security, testing, architecture, dead code, and documentation
- **`code-hygiene` agent**: Audits dead code, modularization violations, hardcoded values, documentation gaps, and error handling anti-patterns
- **`regression-check` agent**: Diffs changes before shipping to flag deleted code, changed API contracts, and behavioral side effects

## [v2.37.0] - 2026-02-22

### Added
- **Semi-monthly and semi-annual expense frequencies**: Two new options for expenses that occur twice a month or twice a year
- **Pill-based frequency selector**: Expense editor now uses a clean pill button UI instead of a dropdown, making all frequency options visible at a glance
- **Custom frequency option**: "Custom" pill reveals an inline "Every ___ days" input for non-standard intervals

### Changed
- **Expense editor opens as overlay**: Add/edit expense form now appears as a centered overlay on top of the list, so you don't lose your scroll position with long expense lists
- **Deposit guidance shows incremental amount**: "Cover all listed expenses" line now includes the additional deposit beyond individually mentioned items, e.g. "~$12,345 total (+$3,456)"

### Fixed
- **Report AI summary tabs now work reliably**: Tab switching in report viewer no longer breaks intermittently
- **Custom expense categories available immediately**: Adding an expense with a custom category now shows it in the dropdown right away for the next expense

## [v2.36.4] - 2026-02-22

### Fixed
- **Report AI summary tabs now clickable**: Tabs were blocked by Content Security Policy; switched to blob URL rendering which bypasses CSP restrictions
- **Deposit calculation accounts for taxes**: Deposit suggestions now factor in tax withholding — shows how much trading capital to add so that after-tax returns cover expenses
- **Per-item deposit amounts**: Each uncovered expense shows the specific deposit needed, e.g. "Finish covering Insurance: deposit ~$2,400" and "Then cover Rent: deposit ~$21,800 more"

## [v2.36.3] - 2026-02-22

### Changed
- **Granular deposit guidance**: Expense reports now show targeted suggestions like "Finish covering Insurance: $165 more needed" and "Next: Rent ($1,500)" instead of just a total deposit figure
- Deposit guidance appears in HTML reports, PDFs, and AI summaries

## [v2.36.2] - 2026-02-22

### Changed
- **Tabbed AI summaries in reports**: The three AI analysis tiers (Simplified, Performance Analysis, Technical) now appear as clickable tabs instead of stacked sections
- **Email reports show single tier**: Emails display only the recipient's preferred analysis tier for a cleaner reading experience

### Fixed
- **Report delivery status**: Reports generated from schedules with no email recipients now correctly show "Manual" instead of getting stuck on "Pending"

## [v2.36.1] - 2026-02-22

### Fixed
- **Expenses goal creation**: Goal form no longer stays open after creating an expenses goal (async lazy-load crash)
- **Expense editor auto-opens**: After creating an expenses goal, the expense items editor opens automatically so you can start adding items right away

## [v2.36.0] - 2026-02-22

### Added
- **Expenses goal type**: New goal type that tracks itemized living expenses and measures how close your trading income is to covering them
- **Expense items management**: Add, edit, and delete individual expense items with flexible frequencies (daily, weekly, biweekly, every N days, monthly, quarterly, yearly)
- **Coverage waterfall**: Reports show which expenses are covered, partially covered, or uncovered by your income — sorted from cheapest to most expensive
- **Tax withholding**: Optional tax percentage deducted from income before expense coverage comparison
- **Automatic normalization**: All expense items normalized to your chosen period (weekly, monthly, quarterly, yearly) regardless of individual billing frequency
- **12 default expense categories**: Housing, Utilities, Transportation, Food, Insurance, Healthcare, Subscriptions, Entertainment, Education, Debt, Personal, Other — plus custom categories
- **Expense coverage in reports**: HTML and PDF reports include a detailed expense card with coverage progress bar, itemized waterfall table, and deposit-to-go suggestion
- **AI summary integration**: AI analysis now includes expense coverage data when summarizing reports with expenses goals

## [v2.35.1] - 2026-02-22

### Changed
- **Goal trend charts now appear in generated reports**: Trend line visualizations (actual vs ideal trajectory) are embedded directly in HTML and PDF reports instead of the Goals tab
- **Goals tab simplified**: Removed interactive trend chart from the Goals tab — goals are now clean and focused on targets

## [v2.35.0] - 2026-02-22

### Added
- **Goal trend line chart**: Visual progress tracking for financial goals — shows actual portfolio value vs. ideal trajectory over time with an interactive chart
- **Daily goal progress snapshots**: Automatic daily capture of goal progress during the account snapshot cycle for historical trend data
- **Auto-backfill on first view**: Existing goals automatically reconstruct historical progress from account value snapshots when you first view their trend
- **Smart on-track detection**: Chart shows whether you're ahead or behind your target trajectory with color-coded status badges

## [v2.34.1] - 2026-02-22

### Added
- **Development workflow commands**: New slash commands `/primer`, `/generate-prp`, `/execute-prp`, and `/fix-github-issue` for structured development workflows
- **Validation and documentation agents**: Automated code quality gating and architecture documentation sync
- **Domain knowledge reference**: Trading domain specifics (budget calculation, AI allocation flow) now in a dedicated reference doc

### Changed
- **Restructured project guide**: Cleaner, more focused development instructions with clear philosophy, rules, and architecture reference

## [v2.34.0] - 2026-02-22

### Added
- **Password visibility toggle on login**: Eye icon to show/hide password while typing, auto-hides after 5 seconds
- **TradingView chart loading indicator**: Spinner overlay while the chart widget downloads and initializes
- **Max Synthetic Candles % setting**: New bot-level filter to skip pairs with too many gap-filled candles during analysis
- **Broken articles "Retry All"**: When filtering to Broken articles, "Read All" becomes "Retry All" and re-attempts TTS instead of skipping

### Fixed
- **Modal buttons hidden behind mini player**: Modals now render above the article reader mini player
- **Number input snapping to 0**: Editing deal settings (take profit, safety orders, etc.) no longer snaps to 0 when clearing the field
- **Category filter resetting source selection**: Changing news/video categories no longer clears your source filter
- **"All" category button toggling confusingly**: "All" now always selects all categories instead of toggling to a single category

### Changed
- **Indicator logs responsive on mobile**: Filters wrap, condition details stack vertically, modal uses full viewport width
- **Bot config modal responsive on mobile**: Capped to viewport width, reduced padding, action buttons wrap
- **Balance columns readable on mobile**: Narrower columns, smaller text, BTC values show 6 decimals instead of 8

## [v2.33.0] - 2026-02-22

### Added
- **Video tab pagination**: Videos now load 50 at a time instead of all ~4000 at once, dramatically reducing thumbnail requests and page load time. Pagination controls match the article tab style. "Play All" and the playlist dropdown still use the full filtered list.

## [v2.32.8] - 2026-02-20

### Fixed
- **YouTube videos and news cleanup working again**: A timezone mismatch caused the video/article cleanup to crash, which broke the entire refresh cycle. Videos and news articles now refresh normally.

## [v2.32.7] - 2026-02-20

### Fixed
- **Crossing detection now uses candle data instead of stale cache**: Crossing above/below conditions (e.g., "MACD cross above 0") were comparing against cached values from a previous check cycle, which could be stale after service restarts or long gaps. Now compares the two most recent closed candles — a crossing only fires when it actually happened on the latest candle close.

## [v2.32.6] - 2026-02-20

### Fixed
- **Increasing/Decreasing conditions now work**: These operators were available in the condition builder but silently ignored at runtime — they always returned false. Now properly compares current vs previous closed candle values.
- Condition logs now show both previous and current values for increasing/decreasing checks (e.g., "48.2 → 52.3 ↑") instead of just one number

## [v2.32.5] - 2026-02-20

### Fixed
- Editing an existing bot no longer fails with "Please select an account" — the bot's existing account is preserved during updates

## [v2.32.4] - 2026-02-20

### Added
- Report title (schedule name) now appears in generated HTML reports, PDFs, and email subject lines instead of generic "Performance Report"

## [v2.32.3] - 2026-02-20

### Fixed
- Report viewer (eye icon) was broken — clicking it did nothing due to missing eager-load on schedule relationship

## [v2.32.2] - 2026-02-20

### Changed
- Report history table now shows the report name alongside frequency for easier identification

## [v2.32.0] - 2026-02-20

### Added
- **Auto wrap-up for period-start days**: When a report runs on the 1st of the month (MTD) or Monday (WTD), it automatically wraps up the full prior period instead of covering just one day. Solves the "missed last-day trades" problem in 24/7 crypto markets.
- **Three-state day toggle**: Period-start days (1st, Monday) cycle through amber (wrap-up), blue (standard), and deselected. Other days remain the normal two-state toggle.
- **Day picker legend**: Color key appears below the day picker explaining amber (wraps up prior period) vs blue (standard) when relevant

## [v2.31.3] - 2026-02-20

### Changed
- Report history "Created" column now shows the time in your local timezone (e.g., "Feb 20, 2026 11:53 PM")

## [v2.31.2] - 2026-02-20

### Fixed
- **PDF generation failing on Unicode characters**: AI summaries containing en-dashes, smart quotes, or other Unicode characters would crash PDF generation — now sanitized to Latin-1 equivalents

## [v2.31.1] - 2026-02-20

### Fixed
- **Goal lookback controlled by schedule**: Income goal projections now use the report schedule's period window (WTD, MTD, trailing N days, etc.) instead of a separate lookback setting on each goal — one place to control how far back reports look

### Removed
- Lookback Window dropdown from goal form (redundant with schedule-level period window)
- Lookback badge from goal cards on Reports page

## [v2.31.0] - 2026-02-20

### Added
- **Flexible report scheduling**: Replace the rigid frequency dropdown with two independent controls — pick exactly when reports run (specific weekdays, days of month, quarterly/yearly dates) and how far back they look (full prior period, WTD, MTD, QTD, YTD, or trailing N days/weeks/months/years)
- **Multi-day schedules**: Weekly schedules can run on multiple days (e.g., Mon + Wed), monthly on multiple dates (e.g., 1st & 15th), with "Last day" option for month-end reports
- **Ad-hoc reports don't affect schedule**: Manually generating a report no longer advances the schedule's next run time — your scheduled cadence stays intact

### Changed
- Schedule cards now display a human-readable description (e.g., "Every Mon, Wed - full prior period") instead of a single word

## [v2.30.0] - 2026-02-19

### Added
- **Goal date picker**: Set a specific target date for goals instead of just month presets — custom date input with prominent blue badge display on goal cards
- **Deposit/withdrawal tracking**: Automatically fetches deposits and withdrawals from Coinbase and stores them locally for accurate performance analysis
- **True PnL in reports**: Reports now show net deposits, adjusted account growth (excluding capital injections), and transfer counts — so you can see real trading performance separate from money added/removed
- **AI summary awareness**: AI-generated report summaries now factor in deposits and withdrawals, explicitly noting when account growth includes capital movements
- **Dashboard deposit note**: When deposits occurred in the last 30 days, a subtle info bar appears below the projection table explaining the capital context
- **Account value chart markers**: Deposit and withdrawal events appear as arrow markers on the account value chart so you can see exactly when capital was added or removed
- **Transfer management API**: Full REST API for syncing, listing, and manually entering transfers — with automatic daily background sync from Coinbase
- **Manual transfer entry**: Add transfers manually for deposits/withdrawals the API can't see

### Changed
- **Report trade count label**: Now shows "Total Trades (last Nd)" with the actual period length for clarity

## [v2.29.0] - 2026-02-19

### Added
- **Experience-level reports**: Each email recipient can be tagged as Beginner, Comfortable, or Experienced — the AI generates three summary tiers in a single call, and each recipient's email highlights their level's analysis with the others still accessible
- **Report delete**: Delete reports from the history tab with a confirmation prompt
- **Coin review scheduler**: Weekly AI-powered coin categorization now runs automatically inside the backend (no more external timer)

### Changed
- **Email branding**: Report emails now use the brand accent color instead of hardcoded blue for headers and AI section highlights
- **Tab persistence**: Active tab on the Reports page now survives page refresh and navigation
- **Gemini model updated**: Switched from deprecated `gemini-1.5-pro` to `gemini-2.0-flash` across all AI services (reports, coin review, grid optimizer)

### Fixed
- **AI report summaries not generating**: Gemini provider was failing silently due to deprecated model name — now uses `gemini-2.0-flash` and logs provider errors at warning level instead of debug

## [v2.28.1] - 2026-02-19

### Added
- **Performance disclaimer**: Income goal projections now include a professional disclaimer that past performance does not guarantee future results, both in the HTML report card and in AI-generated summaries

## [v2.28.0] - 2026-02-19

### Added
- **Income Goals**: New goal type that tracks your earning rate — set a target like "$1,000/month" and reports project your current income both linearly and with compounding, plus advise how much additional capital to deposit to reach the goal
- Configurable lookback window for income calculations (7/14/30/90/365 days or all-time)
- Income goal cards in reports show daily average, linear/compound projections, and deposit-needed estimates

### Fixed
- **Report account value**: Performance reports no longer include paper trading or inactive accounts when calculating total account value — previously inflated values by counting simulated accounts

## [v2.27.0] - 2026-02-19

### Added
- **Performance Reports & Goals**: Full reporting system with customizable financial goals (balance, profit, or both targets in USD/BTC), scheduled report generation (daily through yearly), AI-powered analysis summaries using your own AI provider credentials, and email delivery with PDF attachments
- **Report History**: View and download past reports in-app with HTML preview and PDF download
- **Goal Progress Tracking**: Visual progress bars showing on-track status relative to time elapsed, integrated into reports
- **Period-on-Period Comparison**: Reports automatically include prior period data for trend analysis
- **GitHub link on login page**: "Zenith Grid" text on the login page now links to the open source repository

## [v2.26.9] - 2026-02-19

### Fixed
- **Auto-buy BTC now actually executes**: Fixed three layered bugs preventing auto-buy from converting USD to BTC:
  1. Logs were invisible (uvicorn suppressed logger output)
  2. Coinbase order responses were parsed incorrectly — order_id was always None, failures were silently ignored
  3. Sending 100% of available balance failed because Coinbase needs room for taker fees (~0.6%)
- **Portfolio sell now returns real order details**: Manual "Sell to USD/BTC" was silently swallowing Coinbase errors and returning null order IDs
- **Account consolidation fee buffer**: USD-to-BTC consolidation now reserves 1% for exchange fees

## [v2.26.7] - 2026-02-19

### Fixed
- **Auto-buy logging now visible**: Auto-buy monitor messages (balance checks, triggers, order placements) now appear in production logs — previously invisible due to uvicorn logger configuration

## [v2.26.6] - 2026-02-19

### Fixed
- **Portfolio sell buttons now work**: Fixed "Sell to BTC" and "Sell to USD" failing with "Failed to execute market sell" — Coinbase API requires uppercase side parameter
- **Auto-buy BTC now executes**: Fixed auto-buy monitor silently failing when open USD positions existed due to referencing a nonexistent field; added visible logging so auto-buy activity shows in logs
- **Sell uses selected account**: Portfolio sell now targets the currently selected account instead of always using the default

## [v2.26.5] - 2026-02-19

### Fixed
- **Portfolio balances now match Coinbase**: Refresh button bypasses all backend caches and fetches live data directly from Coinbase
- **Faster portfolio updates**: Auto-refresh interval reduced from 60s to 30s, data refreshes on tab focus and page navigation
- **Bot action menu cut off**: Fixed dropdown menu on the Bots page overflowing off-screen — "Cancel All Deals", "Sell All at Market", and "Delete" options were hidden when many accounts existed

## [v2.26.4] - 2026-02-19

### Fixed
- **Bot action menu cut off**: Fixed dropdown menu on the Bots page overflowing off-screen — "Cancel All Deals", "Sell All at Market", and "Delete" options were hidden when many accounts existed. Menu now scrolls and positions correctly on all screen sizes.

## [v2.26.3] - 2026-02-19

### Fixed
- **News page loading**: Fixed regression where news articles failed to load — page_size=0 (return all) was incorrectly rejected as invalid
- **TTS audio playback**: Fixed Content-Security-Policy blocking blob: audio URLs used by the article reader

### Security
- **Server-side token revocation**: Logout now invalidates the token server-side — stolen tokens can no longer be reused
- **Password change invalidates all sessions**: Changing or resetting your password immediately logs out all other devices
- **WebSocket connection limits**: Each user is now limited to 5 concurrent WebSocket connections, with 4KB message size limit and 5-minute idle timeout
- **Image path traversal guard**: Added defense-in-depth path validation on the article thumbnail endpoint

## [v2.26.2] - 2026-02-19

### Security
- **Login timing attack fixed**: Response time is now identical whether an email exists or not, preventing username enumeration
- **MFA brute-force protection**: TOTP and email MFA verification endpoints now rate-limit to 5 attempts per token within 5 minutes
- **Nginx security headers**: Added HSTS (Strict-Transport-Security) and Content-Security-Policy headers
- **Nginx rate limiting**: Auth endpoints limited to 5 req/min, API endpoints to 30 req/s per IP — floods are blocked before reaching the application
- **Request size limit**: Added 10MB max body size in nginx to prevent memory exhaustion from oversized POST bodies
- **Unbounded page_size fixed**: News endpoint now clamps page_size to 200 max, preventing full-table dumps
- **Settings endpoint restricted**: Individual settings lookup now requires superuser access
- **Article flagging restricted**: Mark-article-issue endpoint now requires superuser access
- **Per-user article fetch rate limit**: External article content extraction limited to 30 per user per hour
- **Per-username login rate limiting**: Login attempts now tracked by both IP and email — rotating IPs can't bypass the limit
- **Per-email forgot-password rate limiting**: Password reset requests limited to 3 per email per hour
- **WebSocket timeout reduced**: Idle WebSocket connections now timeout after 5 minutes instead of 24 hours

## [v2.26.1] - 2026-02-19

### Changed
- **Architecture documentation overhaul**: Updated architecture.json, ARCHITECTURE.md, and README.md to reflect the current state of the application — added 13 missing migrations, 7 missing services, 5 missing models, 16 sentiment card components, multi-exchange support, MFA/email features, and TTS article reader
- **README modernized**: Added Security & Multi-User section, Multi-Exchange Support section, expanded features comparison table, updated roadmap with completed milestones, fixed stale URLs and descriptions

## [v2.26.0] - 2026-02-19

### Added
- **Parallel bot processing**: Bots now process concurrently (up to 5 at a time) instead of sequentially — 3-5x faster cycle times for multi-bot setups
- **Thundering herd prevention**: When cached prices/products expire, only one request fetches fresh data while others wait for the result — eliminates redundant API calls under load
- **Candle chart caching**: The charting endpoint now caches candle data with per-timeframe TTLs — multiple users viewing the same chart no longer trigger duplicate API calls
- **Rate limiter self-cleaning**: Login/signup/password-reset rate limiters now prune stale entries hourly to prevent slow memory growth

### Fixed
- **Exchange client cache race condition**: Added async locking to prevent duplicate client creation when multiple requests hit the same account concurrently
- **Monitor exchange cache race condition**: Same double-checked locking pattern applied to the bot monitor's per-account exchange cache
- **Candle cache shared across users**: Candle data (which is public/identical for all users) no longer includes account ID in cache keys — with 5 users trading the same pair, candle fetches drop from 5x to 1x
- **Unbounded cache growth**: Indicator and scheduling caches now prune entries for deleted/deactivated bots each cycle

## [v2.25.3] - 2026-02-19

### Fixed
- **"Full articles" filter now works**: The `content_scrape_allowed` field was being stripped from API responses by the Pydantic response model, so the frontend filter had no data to filter on — added the field to the response schema

## [v2.25.2] - 2026-02-19

### Changed
- **"Summary only" badge on article cards**: Renamed from "RSS" to "Summary only" with amber styling to clearly indicate articles that only have a summary (source blocks full content scraping)
- **Filter tooltip updated**: "Full articles" button tooltip now describes hiding summary-only articles instead of referencing RSS

## [v2.25.1] - 2026-02-19

### Changed
- **Source badge colors now driven by API category**: Source badges on articles, videos, and mini-players derive their color from the backend category field instead of a hardcoded frontend mapping — new and custom sources automatically get correct category colors

### Removed
- **Hardcoded source-to-category dictionaries**: Deleted ~100 lines of duplicated frontend mappings (SOURCE_CATEGORY, VIDEO_SOURCE_CATEGORY) that had to be manually kept in sync with the database

## [v2.25.0] - 2026-02-19

### Added
- **47 mainstream news sources**: BBC, NPR, CBS News, NBC News, ABC News, PBS NewsHour, The Hill, and Politico across World, Politics, Nation, Business, Technology, Entertainment, Sports, Science, and Health categories
- **RSS badge on article cards**: Articles from RSS-only sources (no in-app reader/TTS) now show a muted "RSS" badge next to the source name
- **"Full articles" filter toggle**: Button in the filter bar hides RSS-only articles so users can browse only sources that support full in-app reading and TTS; persists to localStorage

### Changed
- **Replaced frozen CNN feeds**: CNN RSS feeds (stale since Aug 2024) replaced with active feeds from BBC, NPR, CBS, NBC, ABC, PBS, The Hill, and Politico

### Removed
- **CNN RSS feeds**: 7 CNN category feeds dropped (rss.cnn.com returns stale content frozen since August 2024)

## [v2.24.0] - 2026-02-19

### Added
- **7 CNN RSS feeds**: CNN World, CNN Politics, CNN US, CNN Business, CNN Tech, CNN Entertainment, CNN Health — each mapped to its matching category
- **Politics category**: New news category slotted between World and Nation

### Changed
- **Equidistant category colors**: Rebalanced the 12-category color spectrum — Health moved from emerald to teal, Politics uses sky — so hues are evenly spaced across the Tailwind palette

## [v2.23.2] - 2026-02-19

### Fixed
- **URL scheme normalization for custom sources**: Bare domains like `cnn.com` are now automatically prefixed with `https://` before robots.txt checks, deduplication, and storage. Applies to `add_custom_source`, `check_robots`, and `normalize_feed_url`

## [v2.23.1] - 2026-02-19

### Fixed
- **robots.txt check: unreachable domains no longer show green checkmarks**: Connection-level failures (SSL errors, DNS failures, connection refused) now correctly block adding the source instead of defaulting to "all allowed"
- **Friendly error messages**: Raw SSL/DNS exception text replaced with human-readable messages (e.g., "SSL/TLS connection failed" instead of `[SSL: TLSV1_UNRECOGNIZED_NAME]...`)

## [v2.23.0] - 2026-02-19

### Added
- **robots.txt validation for custom sources**: When adding a custom news source, the system now fetches and parses the domain's robots.txt to determine RSS feed access, article scraping permissions, and crawl delay
- **"Check Source" button** in Add Custom Source form: Users can preview the robots.txt policy before adding — shows green (full access), amber (RSS-only), or red (blocked) status panel
- **Backend enforcement**: Custom news sources that block RSS access are rejected at the API level. Permitted sources automatically get `content_scrape_allowed` and `crawl_delay_seconds` set from robots.txt
- **New `/api/sources/check-robots` endpoint**: Authenticated POST endpoint that returns parsed robots.txt policy for any URL

## [v2.22.0] - 2026-02-19

### Added
- **Per-source content scraping policies**: robots.txt audit of all 47 news sources. Sources that block AI bots/scrapers are now marked RSS-only (`content_scrape_allowed=0`) — RSS feeds still work, but article body scraping is blocked. 26 sources marked RSS-only
- **Per-domain crawl delays**: Sources with specific crawl-delay in robots.txt are respected (e.g., Bitcoin Magazine 5s, SCMP 10s). Module-level tracking prevents hammering
- **20 new permissive sources**: 9 crypto (NewsBTC, CryptoPotato, Bitcoinist, U.Today, CoinJournal, The Crypto Basic, Crypto Briefing, Watcher Guru, Blockchain.News), 5 world (VOA News, Global Voices, RFE/RL, Africanews, SCMP), 6 science (Quanta Magazine, ScienceAlert, Futurism, Live Science, Space.com, Smithsonian Magazine)
- **SOURCE_SCRAPE_POLICIES dict** in database.py: Centralized policy definitions that seed function syncs to DB on every startup

### Removed
- **8 dropped sources**: Reddit r/CryptoCurrency, Reddit r/Bitcoin, Reddit r/artificial (ToS prohibit scraping), BBC World, The Guardian World, Al Jazeera (explicit legal prohibitions), New Scientist (aggressive anti-bot), The Block (broken feed + anti-scrape)

### Fixed
- **Stale frontend category map entries**: Removed leftover `ft_markets`, `marketwatch`, `reuters_finance`, `techcrunch` entries from newsUtils.tsx

## [v2.21.1] - 2026-02-19

### Changed
- **Video filter labels**: News Videos tab now shows "Watched/Unwatched" instead of "Read/Unread" for filter pills, bulk action buttons, and per-video eye button tooltips

## [v2.21.0] - 2026-02-19

### Added
- **Fetch once, never re-fetch**: Backend now persists `content_fetch_failed` flag on articles when external content extraction fails. Subsequent requests return instant failure from cache — no external network call. Prevents hammering failing sources
- **content_fetch_failed migration**: Backfills existing broken articles (`has_issue=1 AND content IS NULL`) so they're never re-fetched

### Changed
- **Retry button → Regenerate audio**: The "Retry full article" button now says "Regenerate audio" and regenerates TTS from existing text (content or summary) without any external fetch
- **Single fetch replaces exponential backoff**: Frontend no longer retries content fetch 4 times with increasing delays. One fetch attempt is sufficient since failures are now persisted server-side

### Removed
- **medicalxpress.com source**: Removed from all source lists, seed data, and category maps. Cleanup migration deletes existing articles, TTS cache, and source record. medicalxpress blocked our EC2 IP after repeated fetch attempts

## [v2.20.4] - 2026-02-19

### Fixed
- **TTS cache falsely invalidated for old records**: v2.20.2 content_hash check treated NULL hash (all pre-existing TTS) as a mismatch, causing regeneration on first play. For articles where the source site now blocks our server, this replaced full-content audio with summary-only audio. Fix: only invalidate when a hash exists AND differs

## [v2.20.3] - 2026-02-19

### Fixed
- **Broken articles skip instead of showing retry button**: Clicking a `has_issue` article auto-skipped to the next article before the mini-player could mount, making the retry button unreachable. Auto-skip now only fires during playlist auto-advance — user-initiated clicks always show the mini-player with the retry button visible. Also clears `has_issue` if the content fetch succeeds on open (not just on explicit retry)

## [v2.20.2] - 2026-02-19

### Fixed
- **TTS cache ignores text changes**: `_get_or_create_tts()` cached audio by `(article_id, voice)` only. When article content changed (e.g., retry fetched full text after initial summary-only), stale summary audio was returned. Cache now stores a `content_hash` (MD5-8) and invalidates on mismatch — deletes old audio file + DB record, regenerates from new text

## [v2.20.1] - 2026-02-19

### Fixed
- **TTS audio cache-buster**: Browser was serving stale (short) audio after article content was re-extracted. Audio URLs now include `?v={content_hash}` so the browser fetches fresh audio when the underlying text changes

## [v2.20.0] - 2026-02-19

### Added
- **Retry button for broken articles**: Articles flagged as `has_issue` or playing summary-only now show a blue "Retry" button in the mini-player (both expanded and collapsed modes). Clicking re-attempts full content extraction; on success, clears the broken flag and plays the full article
- **Persistent article content cache**: Extracted article text is now stored in the database (`news_articles.content` column). All users share the same cache — content is fetched once via trafilatura, then served from DB on all subsequent requests. Eliminates redundant fetches and survives backend restarts
- **TTS cleanup on article deletion**: When articles age out (>7 days), their TTS audio cache directories and DB records are now deleted alongside image files. Prevents orphaned files from accumulating on disk

### Fixed
- **setup.py lint cleanup**: Fixed all 154 flake8 violations (E302, E501, E128) — formatting only, no logic changes

## [v2.19.0] - 2026-02-18

### Added
- **Summary-only indicator**: Amber "Summary only" badge in mini-player (expanded + collapsed) when content extraction fails and falls back to RSS summary
- **Content fetch retry with backoff**: Article content now retries 4 times with exponential backoff (0s, 1.5s, 3s, 6s) before falling back to summary

### Changed
- Articles that fall back to summary are now auto-flagged as `has_issue` (appear in Broken filter)

### Fixed
- **Flake8 lint cleanup**: Fixed all 145 E501 (line too long) violations and 1 F401 (unused import) across 28 backend files. Formatting only — no logic changes

## [v2.18.9] - 2026-02-18

### Fixed
- **Version reporting accuracy**: Backend now snapshots the git version at startup and serves it from memory. Previously, `git describe --tags` ran on every API call, so pushing a new tag caused the old (still-running) backend to report the new version before being restarted — triggering premature update toasts

## [v2.18.8] - 2026-02-18

### Fixed
- **Version toast stability**: Now verifies the server is fully stable before showing the update notification. Performs 3 health checks over 20 seconds — all must return the same new version before prompting the user to reload

## [v2.18.7] - 2026-02-18

### Fixed
- **Resume from where you left off**: Session now saves playback position (every 5s), voice, and speed. On resume, restores the same voice and seeks to the saved position instead of starting the article over from the beginning

## [v2.18.6] - 2026-02-18

### Fixed
- **Version update toast timing**: Toast now waits 5 seconds and re-verifies the server is responding before prompting. Prevents showing "New Version Available" while the backend is still restarting

## [v2.18.5] - 2026-02-18

### Added
- **"Broken" filter pill**: New filter option alongside All/Unread/Read to show articles flagged with playback issues. Amber-tinted when active. Articles tab only

### Fixed
- **Issue badge always visible**: Amber AlertCircle badge now shows on flagged articles regardless of read/unread status (was hidden on read articles). Takes visual priority over the seen checkmark

## [v2.18.4] - 2026-02-18

### Fixed
- **Resume prompt after refresh**: Session was silently failing to save because the full 12k+ article playlist exceeded localStorage's 5MB quota. Now saves only a 50-article window ahead of current position (~25KB)

## [v2.18.3] - 2026-02-18

### Fixed
- **Article card click during playback**: Clicking an article that's already playing now expands the mini-player instead of restarting the article from the beginning

## [v2.18.2] - 2026-02-18

### Fixed
- **Optimistic mark-as-read**: Clicking the eye button now updates the UI instantly instead of waiting for a full data refetch (was re-downloading ~6MB of articles on every click). Reverts automatically if the API call fails
- **Nginx gzip compression**: Enabled gzip for JSON, JS, CSS, and other text types. News API response compressed from 6.5MB to 1.8MB (72% reduction)

## [v2.18.1] - 2026-02-18

### Added
- **"Powered by Zenith Grid" branding**: Subtle footer text on Login page, About modal, main app footer, and maintenance page

### Fixed
- **TTS retry before flagging**: Articles now get one retry before being flagged as having issues. First TTS error retries after 3s; only flags and skips on second failure (4s delay). Content fetch also retries once (1.5s) before giving up
- **Maintenance page branding**: Updated and synced `maintenance.html` to nginx server root

## [v2.18.0] - 2026-02-18

### Added
- **Continuous play toggle**: ON by default for "Read All", OFF for single article clicks. Repeat icon button in mini-player controls. When OFF, playback stops after each article but mini-player stays visible for manual control
- **Resume-on-refresh prompt**: Instead of silently auto-resuming TTS after page refresh, shows "Continue where you left off?" banner with Resume/Dismiss buttons
- **Article issue tracking**: `has_issue` flag on news articles for TTS failures. Amber AlertCircle badge on affected cards and playlist items. Backend `POST /api/news/article-issue` endpoint
- **Auto-skip failed articles**: TTS errors auto-flag the article and skip after 2s delay. Content fetch failures (no content AND no summary) skip after 1s. Known-bad articles skipped instantly (300ms) on future plays
- **Full retention period in News**: Removed 500-article cap — users now see all articles within their retention window (14 days default or custom override). Backend `page_size=0` returns all articles; client-side filtering + pagination handles display

### Fixed
- Mini-player now stays visible when article finishes with continuous play OFF (was disappearing)
- Missing `id` field in 2 of 4 ArticleItem construction points in News.tsx (article dropdown, text body click)
- `togglePlayPause` now handles stopped-but-visible state (replays current article)

## [v2.17.0] - 2026-02-18

### Added
- **Read/seen tracking for news articles and videos**: Per-user tracking of which articles and videos have been consumed. Polymorphic `user_content_seen_status` table with `content_type` discriminator scoped by `user_id`
- **Seen filter pills**: Three-state toggle (All / Unread / Read) above the news grid, with separate state for articles and videos tabs. Filter state persisted to localStorage
- **Seen indicators on cards**: Subtle check badge (top-left corner) and dimmed title on read articles/videos. Full card remains clickable
- **Per-card seen toggle**: Eye/EyeOff button on each article and video card to manually mark as read/unread
- **Bulk mark read/unread**: "Mark all read" / "Mark all unread" button operates on all currently filtered and visible items
- **Auto-mark on TTS completion**: Articles automatically marked as read when TTS finishes playing them
- **Auto-mark on reader open**: Articles marked as read when opened in the article reader
- **Auto-mark on video end**: Videos marked as read when YouTube player reaches the end
- **Backend API endpoints**: `POST /api/news/seen` (single) and `POST /api/news/seen/bulk` for marking content seen/unseen, with SQLite upsert-on-conflict handling
- **Video ID in API response**: `video_to_item()` now includes `id` field for seen tracking

## [v2.16.0] - 2026-02-18

### Added
- **Full rebrand to BTC-Bot**: "Big Truckin' Crypto Bot" identity across login, header, emails, maintenance page, favicon, about modal, and all auth screens. Truck icon replaces Activity icon throughout
- **Dynamic branding system**: All brand values (name, tagline, colors, images) loaded from `branding/custom/brand.json` — no hardcoded strings. New users copy `branding/template/` to get started. Backend serves `/api/brand` (public) and `/api/brand/images/` endpoints
- **Theme toggle**: Electric Blue Neon (`#00d4ff`) and Classic Blue (`#3b82f6`) themes via CSS custom properties. Toggle in Settings > Appearance, persists to localStorage. Brand config sets default theme for new users
- **BrandContext + ThemeContext**: React contexts provide `useBrand()` and `useTheme()` hooks to all components. Brand config fetched once from API, theme applied via CSS class on document root
- **Branding folder structure**: `branding/template/` (tracked, Zenith Grid defaults) + `branding/custom/` (gitignored, user's brand). README with full setup instructions

### Changed
- Email templates now use brand service for name, tagline, and copyright instead of hardcoded values
- FastAPI title, API root message, and TOTP issuer all read from brand config dynamically
- Tailwind extended with `theme-*` color utilities mapped to CSS variables and `neon`/`neon-sm` box shadows

## [v2.15.0] - 2026-02-18

### Added
- **"New Version Available" reload notification**: After a deployment, users with the app already open see a persistent amber toast prompting them to reload. Detected via WebSocket reconnect (fires ~5s after backend restart) and periodic 5-minute polling. Dismissing the toast allows it to reappear on the next check until the user actually reloads. Extends the Toast system with `persistent` flag, action buttons, and `'update'` type styling

## [v2.14.1] - 2026-02-18

### Fixed
- **TTS fails on long articles**: Increased TTS text limit from 15,000 to 50,000 characters — long review articles (e.g. drone roundups) no longer return 422 Unprocessable Entity
- **Maintenance page 403**: Moved `maintenance.html` to `/usr/share/nginx/html/` so nginx can serve it without traversing the user's home directory (was getting 403 Forbidden due to `700` perms on `/home/ec2-user`)

### Changed
- **Maintenance page auto-retry**: Page now counts down from 60 seconds and auto-reloads, in addition to the manual Retry button

## [v2.14.0] - 2026-02-18

### Added
- **Sample bots section**: Bots page now shows 8 pre-built bot templates (4 BTC + 4 USD) between the P&L chart and bot list — BB% Recovery, RSI Runner, AI Autonomous, and MACD Crossover strategies with real configs. View opens read-only modal, Copy pre-fills the create form. Collapsible with state saved in localStorage
- **Read-only modal mode**: BotFormModal now supports `readOnly` prop — disables all inputs via fieldset, hides validation, changes submit to "Close"

### Fixed
- **Changelog 401 error**: AboutModal used raw `fetch()` without JWT token to hit the auth-protected `/api/changelog` endpoint. Replaced with authenticated `api.get()` — changelog now loads correctly
- **Ship-it tag placement**: Tags were placed on dev branch commits before merging, causing `git describe` to show `vX.Y.Z-1-g<hash>` on main. Moved tag step to after merge so it lands on the merge commit. Fixed existing v2.13.0 tag

## [v2.13.0] - 2026-02-18

### Added
- **TTS volume slider**: Volume control in the TTS player settings dropdown — slider from 0-100% with mute/unmute toggle, persists across sessions via localStorage
- **Article playlist hover-to-scroll**: Hovering over articles in the TTS reading queue now scrolls to and highlights the article in the news list, automatically navigating to the correct pagination page if needed (matches video player behavior)
- **Persistent portfolio cache**: Portfolio data survives backend restarts via JSON file cache at `backend/.portfolio_cache/` — loads in ~1ms instead of re-fetching from Coinbase

### Changed
- **40x portfolio speed improvement**: Portfolio endpoint now uses Coinbase breakdown's built-in `total_balance_fiat` instead of making 30+ individual price API calls. Fresh fetch dropped from ~25s to ~0.6-1.4s
- **Sparkline charts 50% taller**: Dashboard carousel sparklines increased from 36px to 54px height, now pinned to card bottom with consistent positioning so eyes don't scan up and down when scrolling through cards

### Fixed
- **Dashboard/Bots portfolio skeleton stuck**: App header and Dashboard showed infinite pulsing grey boxes because the portfolio query was gated on `selectedAccount` (null during initial render). Added fallback to singular endpoint like Positions/Bots pages already use
- **Sparkline charts not rendering in PROD**: ResizeObserver never fired in production builds; replaced with `requestAnimationFrame` deferred mount

## [v2.12.5] - 2026-02-17

### Fixed
- **MFA mobile page eviction**: Switching to authenticator app on mobile caused the browser to evict the page from memory, losing MFA state and trapping users in a login loop. MFA challenge state now persists to `sessionStorage` (survives page reload, cleared on browser close)
- **News "1/500" on fresh mobile browsers**: Default category filter was `CryptoCurrency` only, so fresh browsers with no saved preferences saw nearly no articles. Default now selects all categories
- **Tab badges showed unfiltered count**: Article/video tab badges showed raw API total instead of filtered count, creating a confusing mismatch (e.g., badge "500" but only 1 article visible)

### Added
- **News retention info visible**: Pagination footer now shows "(last 14 days, min 5 per source)" so users understand the article retention policy. Backend includes `retention_days` in API response

## [v2.12.4] - 2026-02-17

### Fixed
- **Balances 500 error with multiple accounts**: `scalar_one_or_none()` crashed when a user had multiple active CEX accounts ("Multiple rows were found when one or none was required"). Added `.limit(1)` to 9 queries across 7 files — fixes "In Pos.", "In Grids", and "Available" columns showing "..." on the Active Deals page
- **Portfolio loading skeleton condition**: Changed from `isLoading && !portfolio` to `!portfolio` — React Query sets `isLoading=false` for disabled queries, so the skeleton never appeared when waiting for account selection

## [v2.12.3] - 2026-02-17

### Added
- **Service qualifier for bot.sh restart**: `--dev` restart now requires `--back-end`, `--front-end`, or `--both` to specify which service(s) to restart. Prevents unnecessary frontend restarts when only backend Python changed

### Fixed
- **Account Value loading skeleton**: Dashboard header and Account Value card now show animated pulse placeholders while portfolio data loads, instead of displaying misleading zeros
- **Rate limit messages include retry time**: All 4 rate limiters (login, signup, forgot-password, resend verification) now tell users exactly when they can try again ("Try again in X minutes") with standard `Retry-After` HTTP header

### Changed
- **Updated all documentation**: README.md, QUICKSTART.md, DEVELOPMENT_GUIDELINES.md, CLAUDE.md, and slash commands updated to reflect new `--back-end`/`--front-end`/`--both` syntax

## [v2.12.2] - 2026-02-17

### Fixed
- **"No accounts configured" on first login**: AccountProvider was mounted outside AuthProvider, so the accounts query fired before authentication completed. Moved AccountProvider inside the auth-gated content so accounts only fetch after login is confirmed
- **Account value slow to appear after login**: Portfolio query fired immediately with no selected account, hitting a legacy fallback endpoint, then re-fetching once accounts loaded. Added `enabled: !!selectedAccount` so portfolio only fetches after account selection — removes one wasted round-trip

## [v2.12.1] - 2026-02-17

### Fixed
- **Firefox silent WAV decode error**: Replaced 44-byte empty WAV (header only) with 844-byte WAV containing actual audio samples. Firefox requires real sample data to decode without `NS_ERROR_DOM_MEDIA_METADATA_ERR`
- **blob: ERR_FILE_NOT_FOUND on page refresh**: Delayed keepalive audio `src` assignment via `setTimeout(0)` so React Strict Mode cleanup can cancel it before the browser starts loading a blob URL that gets immediately revoked
- **WebSocket "closed before established" warning**: Delayed initial WebSocket connect via `setTimeout(0)` so React Strict Mode's immediate cleanup cancels the first attempt, preventing a connection that would be immediately closed

## [v2.12.0] - 2026-02-17

### Added
- **Mode-aware bot.sh restart**: `./bot.sh restart` now requires `--dev` or `--prod` flag. Manages nginx routing, frontend service, and backend as a single atomic operation
- **Mode-switch guard**: Warns when switching between dev/prod modes and requires `--force` to prevent accidental deployment changes ("Did you mean to switch to PROD deployment?")
- **Mixed-mode detection**: Detects inconsistent infrastructure state (e.g., nginx in dev but frontend service stopped) and warns on `restart` and `status`
- **Dynamic nginx discovery**: `bot.sh` searches standard nginx directories (`conf.d`, `sites-enabled`, `sites-available`) for the app's config — no hardcoded paths
- **Status enhancements**: `./bot.sh status` now shows current mode (DEV/PROD), nginx config path, and mixed-mode warnings

### Changed
- **All restart references in CLAUDE.md**: Replaced direct `systemctl` calls with `./bot.sh restart --dev/--prod`. The script is now the single source of truth for service management
- **`.gitignore` updated**: Added SQLite WAL files (`*.db-shm`, `*.db-wal`) and root-level cache files (`*_cache.json`)

## [v2.11.1] - 2026-02-17

### Fixed
- **Settings page slow to draw**: SQLite was using `delete` journal mode — reads blocked on writes from bot trading cycles. Switched to WAL mode (concurrent reads during writes). API response times dropped from 5-7s to sub-second
- **Coins endpoint hitting Coinbase API on every page load**: Added 10-minute cache for `/api/market-data/coins` — product listings rarely change. First hit from external API, subsequent hits from cache (5.3s → 4ms)
- **BlacklistManager blocking on slowest API call**: Split `Promise.all` into two phases — essential data (blacklist + categories) loads first and renders immediately, supplementary data (coins list + AI provider) loads in background. UI draws in ~0.2s instead of waiting 7.5s
- **database.py lint**: Reformatted all `DEFAULT_CONTENT_SOURCES` tuples to comply with 120-char line limit

## [v2.11.0] - 2026-02-17

### Added
- **Admin-only UI guards**: "AI Review" button (system-wide AI categorization) and "System Key" badges on AI providers are now hidden from non-superuser accounts. Regular users still see all providers and can manage their own API keys
- **Auth dependencies package** (`app/auth/`): Canonical home for `get_current_user`, `require_superuser`, `decode_token`, `get_user_by_id` — eliminates 57-module cascade load from router-level imports
- **Service layer extractions**: `ai_credential_service`, `settings_service`, `portfolio_service`, `news_fetch_service` — utility functions moved from routers to proper service layer
- **News data package** (`app/news_data/`): News models, sources, cache utilities, and debt ceiling data moved out of routers into dedicated data package
- **Paper trading validation**: Bot config validation now works for paper trading accounts using public market data

### Fixed
- **Settings 403 for non-admin users**: `GET /settings/{key}` was gated to superusers only — regular users couldn't load `decision_log_retention_days` on the Settings page. Changed to `get_current_user` (read access for all authenticated users, write remains admin-only)

### Changed
- **Import architecture overhaul**: Zero service→router imports remaining. All cross-package dependencies flow downward (auth → services → routers). ~3000 lines net reduction
- **`routers/__init__.py` gutted**: No longer eagerly imports 8+ routers — `main.py` imports each router directly
- **`main.py` cleanup**: All `noqa: E402` inline imports moved to top-level import section
- **Paper trading balance lookups**: `account_router.py` uses public market data API instead of requiring authenticated client for paper accounts
- **CLAUDE.md & whitebox command**: Added "do the right thing" and "no spaghetti code" architecture rules

### Removed
- **`routers/auth_dependencies.py`**: Replaced by `app/auth/dependencies.py` (all 30 consumers updated)
- **`routers/accounts/` subpackage**: Portfolio utils moved to `services/portfolio_service.py`
- **`routers/news/` subpackage**: Data files moved to `app/news_data/`

## [v2.10.1] - 2026-02-17

### Fixed
- **Empty article bodies (Yahoo Finance, etc.)**: aiohttp's default 8KB header limit rejected responses with large Set-Cookie headers (~27KB). Increased `max_field_size` to 32KB in article-content endpoint
- **"Invalid URI" console errors (Firefox)**: Replaced `audio.src = ''` and `removeAttribute('src')+load()` with a tiny silent WAV data URI to properly clear the audio element without triggering browser console errors
- **Keepalive audio cleanup**: Removed unnecessary `audio.src = ''` on unmount that triggered spurious errors

## [v2.10.0] - 2026-02-17

### Added
- **Gap Fill % condition type**: New bot condition that detects the percentage of synthetic/filler candles in a timeframe (0-100). Lets users block trades when data quality is poor (e.g., illiquid pairs where 50-80% of candles are synthetic)
- **Synthetic candle tagging**: `fill_candle_gaps()` now marks gap-filled candles with `_synthetic: True`; `aggregate_candles()` propagates synthetic counts through higher timeframes
- **Portfolio chart UX**: Escape key closes chart modal; click outside modal to close; resize observer keeps chart responsive

### Fixed
- **TEN_MINUTE timeframe extraction**: Added missing `"TEN"` prefix to indicator timeframe parsing — TEN_MINUTE conditions now work correctly
- **Paper trading candle order**: `PaperTradingClient.get_candles()` now reverses Coinbase API results to chronological order, matching `CoinbaseAdapter` behavior
- **Portfolio N+1 query**: Batch-fetch all position prices in parallel instead of sequential per-position API calls
- **News retention NULL handling**: `SQLite printf('-%d days', NULL)` returns `'-0 days'` not NULL — replaced `coalesce` with explicit `case()` for correct per-user retention
- **Deprecated `datetime.utcnow()`**: Replaced all remaining calls in news_router with `datetime.now(timezone.utc)`
- **Portfolio TypeScript**: Removed `as any` casts by adding `unrealized_pnl_usd` and `unrealized_pnl_percentage` to `Holding` interface
- **Account portfolio valuation**: Use public market data API (cached) instead of instantiating authenticated CoinbaseClient

### Changed
- **WebSocket routing in dev/prod commands**: `/ws` routes directly to backend (port 8100) instead of through Vite dev server — fixes fragile WebSocket proxying
- **Whitebox audit command**: Added "clean up dead code" rule
- **News article image endpoint**: Removed unnecessary auth requirement from `/api/news/image/{article_id}`

## [v2.9.6] - 2026-02-17

### Changed
- **Track `.claude/commands/`**: Removed blanket `.claude/` gitignore so slash command definitions (shipit, setdev, setprod, whitebox) are shared with other users
- **Updated `/shipit` command**: Added frontend deployment mode detection step and mode-aware deploy instructions

### Added
- **Coin icon cache gitignore**: `backend/coin_icons_cache/` now ignored (runtime-downloaded assets)
- **Whitebox audit command**: `.claude/commands/whitebox.md` — reusable slash command for structured security/performance audits

## [v2.9.5] - 2026-02-17

### Fixed
- **Carousel re-render storm**: Moved `liveDebt` (100ms) and `liveCountdown` (1s) timer state from parent into `USDebtCard` and `HalvingCard` — eliminates ~11 unnecessary re-renders/sec across all 14 cards
- **Deprecated `datetime.utcnow()`**: Replaced 3 calls with `datetime.now(timezone.utc)` in metric snapshot recording, pruning, and history queries
- **Prune on every read**: Metric snapshot pruning now guarded by 1-hour timestamp — no longer fires on every `/metric-history` request

### Changed
- **Monolith split**: `MarketSentimentCards.tsx` (1,948 lines) split into 17 individual card components in `components/cards/` with barrel export
- **Season detection extracted**: `determineMarketSeason` moved to `utils/seasonDetection.ts`; `useMarketSeason` hook updated to import from utility
- **Shared aiohttp session**: All 11 external API fetch functions now share a single `aiohttp.ClientSession` instead of creating per-request sessions
- **React.memo on all cards**: All 14 carousel card components wrapped in `React.memo` to prevent unnecessary re-renders
- **Resize debounce**: Carousel resize handler debounced with 150ms timeout
- **Fear/Greed color caching**: `getFearGreedColor()` result cached in variable instead of recalculated

### Added
- **Error states**: All cards accept `isError` prop and render `CardError` fallback when data fetch fails
- **Escape key handler**: `DebtCeilingModal` now closes on Escape key press

### Removed
- **Dead `funding_rates` code**: Removed `fetch_funding_rates()`, `/funding-rates` endpoint, and cache functions (CoinGlass API was non-functional)
- **Dead `exchange_flows` cache**: Removed `EXCHANGE_FLOWS_CACHE_FILE` and load/save functions (never used)

## [v2.9.4] - 2026-02-17

### Fixed
- **TTS memory leak**: Per-user semaphore dict now bounded (100 max, 1hr TTL) — prevents unbounded growth in multi-user environments
- **TTS duplicate generation**: Per-key dedup locks prevent concurrent requests from running edge-tts twice for the same article+voice
- **TTS bandwidth waste**: `/tts-sync` returns `audio_url` instead of base64 when `article_id` is provided — saves ~33% bandwidth and ~5MB peak RAM per request
- **Frontend memory triple-allocation**: Base64 audio decode now uses `atob()` + `Uint8Array` instead of `fetch(data:...)` which tripled peak memory
- **Stale word refs**: `wordRefs` array now reset at top of `renderedContent` useMemo — prevents stale DOM ref retention across article switches
- **Redundant import**: Removed duplicate `from sqlalchemy import delete` in TTS cleanup function

### Changed
- **Word click performance**: Replaced ~2000 per-word `onClick` closures with single event delegation handler via `data-tts-idx` attributes
- **TTS prefetch**: Next article's TTS is prefetched 5 seconds after playback starts, eliminating loading gaps between articles
- **New `/tts/prepare` endpoint**: Warms TTS cache without returning audio payload — used by frontend prefetch

### Added
- **`/whitebox` custom command**: Reusable audit command that bakes in standing assumptions about multi-user, security, performance, and code quality

## [v2.9.3] - 2026-02-17

### Fixed
- **Recharts width/height warnings (proper fix)**: Sparkline defers `ResponsiveContainer` render via `ResizeObserver` until parent has real dimensions — eliminates all 24 width(-1)/height(-1) warnings from off-screen cards in horizontal scroll

## [v2.9.2] - 2026-02-17

### Fixed
- **Recharts width(-1) warning**: Added `minWidth={1}` alongside `minHeight={1}` on all `ResponsiveContainer` components — both dimensions needed to suppress the warning during initial render

## [v2.9.1] - 2026-02-17

### Fixed
- **Recharts width/height -1 warnings**: PnLChart container changed from `min-h-[300px]` to explicit `h-[300px]`; added `minHeight={1}` to all `ResponsiveContainer` components in PnLChart and Sparkline

### Added
- **Debt ceiling countdown**: US National Debt card now shows countdown to when debt hits the ceiling, or time since exceeded if already past

## [v2.9.0] - 2026-02-17

### Added
- **TTS caching system**: Article TTS audio cached to disk and DB (`article_tts` table), shared across users — no re-generation for same article+voice
- **TTS history tracking**: `user_article_tts_history` table records last-used voice per article per user for auto-resume
- **Voice subscription preferences**: `user_voice_subscriptions` table for per-user voice enable/disable
- **TTS serve endpoint**: `GET /tts/audio/{article_id}/{voice_id}` serves cached MP3 files directly
- **Article source_id FK**: `news_articles` and `video_articles` now have `source_id` FK to `content_sources` for proper relational lookups (backfilled on migration)
- **Source subscription enhancements**: `user_category` (per-user category override) and `retention_days` (visibility filter) columns on `user_source_subscriptions`
- **Domain blacklist service**: New `domain_blacklist_service.py` for URL domain filtering
- **URL utilities**: New `url_utils.py` for URL normalization and validation
- **Custom commands**: `/shipit` (full release process), `/setdev` (switch to Vite dev mode), `/setprod` (switch to production dist/ mode)

### Fixed
- **S1: Voice path traversal**: Voice parameter validated against `TTS_VOICES` keys before filesystem use — rejects unknown voices with 400
- **S2: Path containment escape**: `serve_tts_audio` verifies resolved path stays within `TTS_CACHE_DIR` — blocks DB-driven path traversal
- **R1: TTS race condition**: `IntegrityError` caught in `_get_or_create_tts` — concurrent requests for same article+voice no longer cause 500 errors
- **R2: Rate parameter injection**: Strict regex validation (`^[+-]\d{1,3}%$`) rejects malformed rate strings like `+abc%`
- **Q1: Deprecated datetime**: `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` in TTS history

### Changed
- **O(1) word highlighting (MiniPlayer)**: Removed `currentWordIndex` from `renderedContent` useMemo deps; highlighting via direct DOM class toggle instead of rebuilding 1000+ spans per word
- **O(1) word highlighting (ArticleContent)**: Same DOM-based pattern — `useEffect` toggles highlight classes on prev/current word refs
- **Source subscriptions modal**: Enhanced with category/retention controls
- **News router**: Extended with source_id-aware queries and domain blacklist integration
- **Sources router**: Enhanced subscription management with category and retention support

## [v2.8.0] - 2026-02-17

### Fixed
- **Article cache race condition**: Added `asyncio.Lock` to prevent `KeyError` during concurrent cache eviction
- **Auto-buy monitor broken**: `PendingOrder` usage had wrong field names and missing columns — replaced with in-memory `AutoBuyPendingOrder` dataclass so repricing actually works
- **Broadcast crash**: `sell_executor`/`buy_executor` called non-existent `broadcast_position_update()` — fixed
- **Gemini AI race condition**: Fixed in AI service credential lookup

### Added
- **Auth on all news endpoints**: All 23 previously unprotected news/metrics endpoints now require authentication — unauthenticated scraping no longer possible
- **Per-user TTS semaphore**: TTS concurrency limited to 1 per user (nested inside global limit of 3) — one user can no longer starve others
- **Admin-gated endpoints**: Settings, seasonality, blacklist categories, template seed-defaults, strategy, monitor/shutdown/pair-sync all require superuser
- **ContentSource ownership**: Added `user_id` column + ownership check on delete
- **Per-user AI credentials**: AI service looks up credentials per-user via `AIProviderCredential`
- **Migration: content_source_user_id**: Adds `user_id` column to `content_sources`

### Changed
- **news_router modularized**: Split 2700-line `news_router.py` into 3 files — `news_router.py` (articles/videos), `news_metrics_router.py` (market metrics), `news_tts_router.py` (TTS)
- **Frontend auth enforcement**: 23 `fetch()` calls switched to `authFetch()` across MarketSentimentCards, useNewsData, useMarketSeason
- **Context memoization**: `ArticleReaderContext` value wrapped in `useMemo` — eliminates unnecessary 4Hz re-renders
- **MiniPlayer performance**: Constants moved to module scope; progress bar uses ref pattern for stable `useEffect` deps
- **Order reconciliation scoped**: `OrderReconciliationMonitor` and `MissingOrderDetector` scoped by `account_id`
- **Balance API scoped**: `account_id` passed to all `get_accounts()`/`get_btc_balance()` calls
- **Per-instance rate limiter**: No more cross-user API throttling
- **Market data**: Prefers system/public credentials over random user account
- **Bull flag scanner**: `BlacklistedCoin` query scoped to global + user

### Removed
- Dead `order_monitor.py` (231 lines), `SyncedArticleReader` component, `useTTS` hook, dead `calculate_available_balance`, dead `limit_order_monitor` methods

## [v2.7.0] - 2026-02-17

### Fixed
- **Order history data leak**: All 4 endpoints now filter by `Bot.user_id == current_user.id` — previously any user could see all orders
- **Perps position ownership**: `modify_tp_sl()` and `close_perps_position()` now verify position belongs to current user via account ownership chain — previously any user could modify/close any position by ID
- **Scanner logs data leak**: All 3 scanner log endpoints now filter by bot ownership
- **Signals data leak**: `GET /api/signals` now scoped to current user's positions via account chain — previously returned all users' signals
- **News cleanup unauthenticated**: `POST /api/news/cleanup` now requires authentication — previously anyone could purge the news cache
- **Account balance data leak**: `GET /account/balances` now filters by `Account.user_id` in both specified and default account branches
- **Bot name uniqueness**: Changed from global unique to per-user unique via composite constraint `(user_id, name)` — different users can now have bots with the same name
- **Delisted pair monitor hardcoded account**: Replaced `Account.id == 1` with dynamic query for any active CEX account

### Added
- **Migration: bot_name_per_user_unique**: Drops global unique index on `bots.name`, creates composite unique index on `(user_id, name)`

### Changed
- **Architecture docs**: Documented multi-user hardening patterns and ownership chain

## [v2.6.0] - 2026-02-17

### Changed
- **bot_products junction table**: Extracted `bots.product_ids` JSON array into a normalized `bot_products` table with proper indexes; enables SQL queries like "find all bots trading ETH-BTC" without JSON parsing
- **bot_template_products junction table**: Same normalization for bot templates
- **Bot.get_trading_pairs()**: Now reads from junction table instead of JSON column
- **News images moved to filesystem**: Article thumbnails stored as WebP files in `backend/news_images/` instead of base64 blobs in the database; reduces DB bloat by ~50MB
- **News image serving**: `/api/news/image/{id}` now serves from filesystem; cleanup also deletes orphaned image files
- **Bot CRUD operations**: Create, update, clone, and copy-to-account all sync `bot_products` junction table rows

### Added
- **Migration: extract_bot_products**: Creates `bot_products` and `bot_template_products` tables, populates from existing JSON data
- **Migration: move_news_images_to_filesystem**: Extracts base64 `image_data` from `news_articles` to `backend/news_images/` directory

## [v2.5.0] - 2026-02-17

### Added
- **Per-user coin category overrides**: Users can override the global AI-generated coin category (APPROVED/BORDERLINE/QUESTIONABLE/BLACKLISTED) for themselves; overrides are marked with an asterisk (*) in the UI
- **Override API endpoints**: `GET/PUT/DELETE /api/blacklist/overrides/{symbol}` for managing per-user overrides
- **Public market data fallback**: Paper trading and market data endpoints now fall back to Coinbase public API (no auth required) when no user credentials are available
- **Multi-user audit plan**: Comprehensive audit document (`MULTI_USER_AUDIT_PLAN.md`) tracking all data isolation work across 5 phases

### Changed
- **Multi-user data isolation (Phases 1-5)**: All user-facing queries now scoped by `user_id` or `account_id` — positions, trades, portfolio, dashboard stats, bots, WebSocket notifications, and balance caches are fully isolated between users
- **Balance cache keys scoped by account_id**: Cache keys like `balance_eth`, `aggregate_btc_value` now include account_id suffix (e.g., `balance_eth_3`) to prevent cross-user cache pollution
- **Aggregate BTC position query scoped**: `calculate_aggregate_btc_value()` now JOINs through bots table to scope positions to the correct account
- **Hardcoded DB path removed**: `account_balance_api.py` now uses `os.path.dirname` instead of `/home/ec2-user/...`
- **WebSocket manager user-scoped**: Connections stored as `(websocket, user_id)` tuples; `broadcast_order_fill` routes notifications only to the owning user
- **Portfolio/account queries strictly scoped**: Removed legacy `account_id IS NULL` fallbacks in `portfolio_utils.py` and `accounts_router.py`
- **Signal processor override-aware**: Buy decisions check per-user coin category overrides before falling back to global entries
- **Bot monitor category filtering**: `filter_pairs_by_allowed_categories()` now respects per-user overrides via `user_id` parameter
- **Paper trading client**: All 10 fallback methods now use public API instead of system credentials
- **Blacklist list endpoint**: Returns `user_override_category` field when current user has an override

### Fixed
- **Cross-user balance cache pollution**: User A's cached balances could be returned for User B (critical multi-user bug)
- **Unscoped position queries**: Dashboard stats, trades, portfolio PnL, and bot budget pre-fetch now filtered to current user's accounts
- **`get_coinbase_from_db()` not user-scoped**: Bot CRUD and validation routers now pass `user_id` to get the correct user's exchange client

## [v2.4.0] - 2026-02-16

### Added
- **Multi-method MFA**: Users can now choose between authenticator app (TOTP), email verification code, and email verification link for two-factor authentication
- **Email MFA login flow**: Login sends a styled HTML email with both a 6-digit code and a clickable "Verify Login" link; either completes the MFA challenge
- **Tabbed MFA UI on login**: When multiple MFA methods are enabled, login shows Authenticator / Email Code / Email Link tabs — only one method needs to succeed
- **Email MFA settings toggle**: Enable/disable email MFA independently from TOTP in Settings, with password confirmation and mutual-exclusion guard (can't disable your last MFA method)
- **MFA email resend**: "Resend code" button with 60-second cooldown during login MFA challenge
- **`/mfa-email-verify` route**: Handles email link clicks — auto-verifies and redirects to dashboard
- **Resend MFA email endpoint**: `POST /api/auth/mfa/resend-email` invalidates old tokens and sends fresh code+link
- **MFA encouragement updated**: Now mentions both authenticator app and email verification as options

### Changed
- **Login response**: Now includes `mfa_methods` list (e.g. `["totp", "email_code", "email_link"]`) so frontend knows which tabs to show
- **Device trust helper extracted**: `_create_device_trust()` shared across all MFA verify endpoints (DRY)
- **Trusted devices section**: Now visible when any MFA method is enabled (not just TOTP)
- **MFA encouragement gate**: Checks both `mfa_enabled` and `mfa_email_enabled` before showing encouragement screen

## [v2.3.0] - 2026-02-16

### Added
- **HTTPS domain access**: App publicly accessible at `https://tradebot.romerotechsolutions.com` via Nginx reverse proxy with Let's Encrypt SSL (auto-renewing)
- **TOTP MFA (Two-Factor Authentication)**: Authenticator app support (Google Authenticator, Authy, etc.) with QR code setup, manual key entry, and encrypted secret storage (Fernet)
- **MFA login flow**: Two-step login — password then 6-digit TOTP code — with auto-focus, numeric input, and "Back to login" escape
- **Remember device for 30 days**: Optional checkbox during MFA login stores a device trust token, skipping MFA on subsequent logins from the same browser
- **Trusted device management**: Settings page shows all trusted devices with browser/OS name, IP geolocation (city, state, country), and date added; individual or bulk revocation
- **Login page branding**: Subtle gradient accents, feature highlights (Automated Trading, AI Analysis, Grid Strategies), and polished card styling
- **Public signup disabled**: Registration locked down; new users created by admin only via `POST /api/auth/register`

### Infrastructure
- **Route53 DNS**: A record `tradebot.romerotechsolutions.com` -> EC2 (54.226.70.55)
- **EC2 security group**: Ports 80 and 443 opened for HTTP/HTTPS
- **Nginx**: Installed and configured as reverse proxy to localhost:8100, with WebSocket upgrade support
- **Certbot**: SSL certificate obtained and auto-renewal configured

## [v2.2.0] - 2026-02-16

### Added
- **Production frontend build**: Frontend now built with `vite build` and served by FastAPI backend — eliminates React dev-mode overhead that caused `DataCloneError: out of memory` (tab crashes on iPad/mobile during overnight TTS playback)
- **TTS session resilience**: Wake Lock API keeps screen awake during playback, silent audio keepalive prevents browser from discarding tab, session auto-resumes from localStorage after tab kill
- **Article reader UI improvements**: Full-screen mode on mobile, pinned image with blurred background fill (YouTube-style), pinned article info section with gradient separator, fade-out edges on scrollable text
- **Child voice content filter**: Expanded adult content keywords from ~25 to ~90+ covering sexuality, guns/weapons, alcohol, smoking/tobacco, drugs, and violence

### Changed
- **Single-service deployment**: Backend serves the production frontend bundle — `trading-bot-frontend` systemd service no longer needed
- **`bot.sh` production awareness**: Detects production build (`frontend/dist/index.html`) and skips frontend service operations
- **`update.py` builds frontend**: Automatically runs `vite build` when frontend changes are detected during updates
- **Badge polling reduced**: Closed/failed position badge queries reduced from 10s to 60s
- **News page size reduced**: Article fetch reduced from 10,000 to 500 per request
- **Slider-vertical fix**: MiniPlayer volume slider uses `direction: 'rtl'` instead of deprecated `-webkit-appearance: slider-vertical`
- **WebSocket cleanup fix**: NotificationContext properly detaches handlers before closing to prevent StrictMode reconnection cascade

### Removed
- **Vite client strip plugin**: No longer needed — production build doesn't include `/@vite/client`
- **HMR disable setting**: No longer needed — production build has no HMR
- **Page reload diagnostics**: Investigation scaffolding removed (DIAG_KEY, logDiag, /api/diag endpoint)
- **Root health check route**: Moved from `/` to `/api/` only, so SPA catch-all can serve frontend at root

## [v2.1.1] - 2026-02-16

### Fixed
- **TTS article reading interrupted by auth logout**: The 401 interceptor immediately cleared all tokens (including refresh token) and forced logout on any expired access token. Now attempts a token refresh first, with a mutex to prevent concurrent refresh races. This was the primary cause of "page refreshes" during long listening sessions.
- **TTS article reading interrupted by refetch cascades**: MarketSentimentCards had 23 React Query hooks refetching every 5-15 minutes regardless of user engagement, causing re-render cascades that disrupted TTS playback. All refetch intervals now pause when the user is actively listening to articles.

### Changed
- **Mobile header redesign**: Separate mobile/desktop header layouts for a cleaner design
  - Row 1: Brand + version (left), Account Value (right)
  - Row 2: Season indicator, Live/Paper toggle, Account Switcher, Logout — all equal-height pills with consistent styling
  - BTC/ETH prices hidden on mobile, version link visible and tappable
- **Consistent header control sizing**: Season badge, Paper Trading toggle, Account Switcher, and Logout button now share matching border-radius (`rounded-lg`), padding, and icon sizes across mobile and desktop
- **Season indicator visible on all screen sizes**: Previously hidden below `lg` breakpoint, now shown on mobile (in controls row) and tablet (in right-side controls)

## [v2.1.0] - 2026-02-16

### Added
- **Mobile-responsive layouts**: Full mobile-friendly UI across all pages and components (21 files updated)
  - **App shell**: Header hides Paper Trading toggle and Account Switcher on mobile; nav separator hidden on small screens
  - **Dashboard**: Projection table columns hidden on mobile, PropGuard grid stacks to single column, recent deals wrapped in overflow scroll
  - **Positions**: Balance panel tightens column widths and hides "In Grids" on mobile; action buttons wrap
  - **Bots**: Bot table hides non-essential columns on mobile; header buttons wrap
  - **Portfolio**: Hides Balance and Price columns on mobile for clean 4-column layout
  - **Charts**: Toolbar separators hidden on mobile; chart type and time interval buttons wrap
  - **History**: Trade history grid wraps on mobile; pagination controls wrap
  - **News**: Article and video grids transition to 2-column at smaller breakpoint
  - **Mini players**: Both article reader and video mini players now stack progress bar above centered buttons on mobile with auto-height; expanded mode stacks controls vertically
  - **Market sentiment carousel**: Responsive card count (1 on mobile, 2 on tablet, 3 on desktop) with resize listener
  - **Modals**: All modals use full-width on mobile with proper margin; internal grids stack to single column
  - **Charts**: PnL chart stats stack above chart on mobile; Account Value chart header and time buttons wrap

## [v2.0.1] - 2026-02-16

### Fixed
- **PropGuard fail-safe on DB unavailability**: `_load_state()` and `_snapshot_daily_start()` now raise RuntimeError on database failures, blocking all orders rather than silently allowing them through
- **WS equity staleness detection**: PropGuard now rejects WebSocket equity data older than 60 seconds and falls back to REST, with NaN/Inf guard on equity values
- **WS staleness check in monitor**: PropGuard background monitor now applies the same 60-second staleness check as the order preflight path
- **Exchange client cache cleanup**: Shutdown handler now properly closes all cached exchange clients (fixes httpx connection leak for MT5), and `clear_exchange_client_cache(None)` now closes clients before clearing
- **Missing null checks on exchange client**: Added null checks for `get_exchange_client_for_account()` in `bot_control_router` and `account_router` portfolio conversion
- **API key encryption for all exchanges**: `api_key_name` is now encrypted at rest for Coinbase accounts (was only encrypted for ByBit), decrypted on use, and masked in API responses
- **Frontend account validation**: Bot form now validates account selection before submission; AddAccountModal validates required credentials for ByBit, MT5, and Coinbase
- **PropGuardStatus 404 handling**: Frontend now treats 404 as "not initialized" instead of showing an error state
- **TradingView ByBit symbol mapping**: Correctly maps internal `-USD` suffix back to `-USDT` for ByBit charts on TradingView

## [v2.0.0] - 2026-02-16

### Added
- **Multi-Exchange Architecture**: ByBit V5 (HyroTrader) and FTMO MT5 Bridge exchange adapters implementing the ExchangeClient interface — ZenithGrid is no longer Coinbase-only
- **PropGuard Safety Middleware**: Real-time drawdown monitoring decorator that wraps any exchange client with pre-flight safety checks (daily/total drawdown limits, spread guard, volatility buffer, kill switch)
- **ByBit WebSocket Manager**: Real-time position, order, wallet, and ticker streams via pybit for sub-second equity monitoring
- **PropGuard Background Monitor**: Async service running every 30s to check all prop firm accounts, update equity state, and trigger kill switch on drawdown breach
- **PropGuard API Endpoints**: GET status, POST reset kill switch, POST manual emergency kill, GET history (`/api/propguard/{account_id}/...`)
- **PropGuard Status Widget**: Frontend dashboard card with live equity, color-coded daily/total drawdown progress bars, and manual kill/reset controls
- **Prop firm badges** on account cards in Settings showing firm name (HyroTrader/FTMO)
- **Database schema**: `prop_firm_state` table and 5 new columns on `accounts` (prop_firm, prop_firm_config, prop_daily_drawdown_pct, prop_total_drawdown_pct, prop_initial_deposit)
- **Account creation UI**: Exchange dropdown (Coinbase/ByBit/MT5 Bridge) with conditional fields per exchange type, prop firm dropdown, drawdown configuration with input validation
- **ByBit global rate limiter**: 100ms minimum spacing between ByBit API calls via async lock to prevent rate limit violations
- Added `pybit>=5.8.0` dependency for ByBit V5 API integration

### Changed
- Exchange factory now accepts `exchange_name` parameter to route to ByBit/MT5 adapters (backwards-compatible, defaults to Coinbase)
- Exchange service wraps clients with PropGuard decorator when `account.prop_firm` is set
- ByBitAdapter wraps order responses in Coinbase-compatible `success_response` format for consistent parsing by buy/sell executors
- ByBit `from_bybit_symbol()` maps USDT→USD so products appear as standard `-USD` pairs system-wide
- ByBitAdapter `calculate_aggregate_btc_value()` and `calculate_aggregate_usd_value()` use `totalEquity` (includes unrealized PnL)
- TradingClient buy/sell/get_balance now support USDT and USDC quote currencies alongside USD and BTC
- Order validation parameter renamed from `coinbase_client` to `exchange` for exchange-agnostic clarity
- Candle data reversal moved into each adapter's `get_candles()` — each adapter returns chronological (oldest-first) order
- Multi-bot monitor candle cache now keyed by account_id to prevent cross-account data bleed
- Missing order detector now checks all active accounts instead of only account_id=1
- Order reconciliation monitor iterates all active accounts for startup reconciliation
- Bot creation/update budget validation now uses `get_exchange_client_for_account()` instead of Coinbase-only factory calls
- Grid order fill handler uses bot's `account_id` to get correct exchange client
- Account creation validates exchange names, prop firm names, and bridge URLs (SSRF prevention)
- ByBit API keys encrypted at rest during account creation and update
- Exchange config changes trigger client cache invalidation (including monitor cache)
- Indicator-based strategy removes hardcoded 0.0001 BTC minimum floor — exchange-specific minimums enforced by order_validation at execution time
- ByBitAdapter `cancel_order()` falls back to order history when order not found in open orders
- ByBitAdapter `list_products()` and `get_product()` return Coinbase-compatible field aliases (`base_currency_id`, `quote_currency_id`, `display_name`) and normalized `"online"` status
- TradingView chart modal uses exchange-specific symbol prefix
- Frontend `authFetch()` used for all account management API calls (update, delete, setDefault)
- INTX perps section hidden for non-Coinbase accounts
- Fee-adjusted profit multiplier accepts optional `exchange` parameter
- Replaced Coinbase-specific error messages in buy/sell executors with exchange-agnostic wording

### Fixed
- **CRITICAL**: Infinite recursion in ByBit rate limiter — `_rate_limited_call()` was calling itself instead of `asyncio.to_thread()`
- **CRITICAL**: Bot creation/update called `create_exchange_client(db, account_id)` with wrong signature — would crash for all exchanges
- **CRITICAL**: ByBit buy orders treated as failures because buy_executor expected Coinbase's nested `success_response.order_id` format
- **CRITICAL**: ByBit `get_order()` missing `total_fees` field — fee calculation defaulted to zero
- **CRITICAL**: PropGuard safety blocks not detected by trading engine — now raise clear `PropGuard blocked:` errors
- **CRITICAL**: ByBit `cancel_all_orders()` failed for linear category — now passes `settleCoin="USDT"` as required by ByBit V5 API
- Fixed wrong Trade model field names in `execute_sell_short()` and `execute_buy_close_short()` — used nonexistent `size`/`filled_value`/`commission`/`executed_at` instead of `base_amount`/`quote_amount`/`timestamp`
- Fixed `sell_executor.execute_sell_short()` calling `validate_order_size()` without `await` and with wrong argument order
- Fixed grid order fill handler querying random active account instead of using bot's `account_id`
- Fixed limit order monitor `list_orders()` expecting dict wrapper instead of direct list return
- Fixed missing order detector removing unsupported `start_date` kwarg from `list_orders()` call
- Added USDT/USDC to order validation `DEFAULT_MINIMUMS` fallback (10 USDT min notional)
- Added `quote_min_size` (from ByBit `minNotionalValue`) to ByBitAdapter product responses
- Removed unused variable warnings from sell_executor and order_reconciliation_monitor

## [v1.31.13] - 2026-02-15

### Changed
- Moved Perpetual Futures portfolio linking from standalone Settings card into expandable per-account row in Centralized Exchanges section — each CEX account now shows its own perps status inline
- Perps portfolio fields (UUID, leverage, margin type) now included in accounts API response, eliminating extra API calls

### Fixed
- Fixed `link-perps-portfolio` endpoint passing wrong arguments to `get_coinbase_for_account()`

## [v1.31.12] - 2026-02-15

### Added
- Budget rejection events (insufficient funds, below exchange minimum) now appear on the History page's Failed Orders tab, not just in indicator logs
- Deduplication prevents repeated identical failed order entries for the same deal — a new entry is only logged when the error message changes

## [v1.31.11] - 2026-02-15

### Fixed
- Fixed `max_quote_allowed` set to raw per-position budget ceiling instead of actual expected deal cost when `auto_calculate_order_sizes=True`, causing misleading budget utilization percentages (e.g., 87% instead of ~100%)
- Fixed `calculate_max_deal_cost()` not accounting for `auto_calculate_order_sizes` flag — when enabled with fixed safety order type, safety orders now correctly equal base order size (matching actual trading logic in `indicator_based.py`)

## [v1.31.10] - 2026-02-15

### Fixed
- Fixed crossing conditions (bb_percent, MACD, etc.) being detected but not triggering trades — `analyze_signal()` results were discarded and conditions re-evaluated after previous indicators had already been updated, causing crossing events to be consumed before `process_signal()` could act on them

## [v1.31.9] - 2026-02-15

### Fixed
- Fixed safety order "Insufficient balance" errors caused by negative available balance calculation — when a position already exists, budget is now calculated from the position's own `max_quote_allowed` instead of pair-level budget which could over-subtract across multiple positions

## [v1.31.8] - 2026-02-15

### Fixed
- Updated `docs/architecture.json` version from v1.31.4 to v1.31.8
- Added missing `routers/auth_dependencies.py` to architecture.json routers section
- Added missing `components/news/newsUtils.tsx` to architecture.json sub_components section

## [v1.31.7] - 2026-02-15

### Fixed
- Fixed circular import in `routers/__init__.py` that prevented backend startup after `__pycache__` cleanup

### Removed
- Deleted 7 stale docs/ files (ARBITRAGE_PLATFORM_HANDOFF, CANDLE_FETCH_OPTIMIZATION_PLAN, COMPLETE_DOCUMENTATION, DEVELOPMENT_ROADMAP, LIMIT_ORDERS_TODO, PROJECT_OVERVIEW, TODO_MIN_PROFIT_GUI_DISPLAY)

### Changed
- Rewrote `docs/CONDITIONAL_STRATEGY.md` — reflects completed system with all operators (INCREASING/DECREASING), all indicators (AI_BUY/AI_SELL/BULL_FLAG/VOLUME_RSI), phase-based conditions
- Rewrote `docs/USER_GUIDE_CONDITIONAL_STRATEGY.md` — updated strategy name, phase-based conditions, correct JSON format, new operators and indicators
- Rewrote `docs/QUICKSTART.md` — correct ports, systemd instructions, setup.py workflow, removed MACD-centric content
- Rewrote `docs/DEVELOPMENT_GUIDELINES.md` — correct file paths, current architecture patterns, removed stale TODOs
- Updated `docs/FEATURE_CHECKLIST.md` — marked 50+ completed features (grid trading, paper trading, bidirectional, AI providers, notifications, security hardening, etc.)
- Updated `README.md` — fixed broken doc links, corrected strategy listing
- Updated `COMMERCIALIZATION.md` — marked Phase 1 items as complete

## [v1.31.6] - 2026-02-15

### Removed
- Deleted 18 stale root-level markdown files (completed migration plans, session handoffs, status reports) — all preserved in git history

### Changed
- Moved `AUTO_CALCULATE_BUDGET_LOGIC.md` and `SECURITY_AUDIT_v1.31.0.md` to `docs/` folder

## [v1.31.5] - 2026-02-15

### Added
- `docs/architecture.json` — Machine-readable catalog of all backend and frontend modules
- `docs/ARCHITECTURE.md` — Mermaid diagrams (system overview, backend layers, frontend layers, trading flow, data model) plus prose on auth, multi-tenancy, and background tasks

## [v1.31.4] - 2026-02-15

### Changed
- Removed dead commented-out code: `AuthTokens` interface in AuthContext.tsx, GALA mapping in dex_wallet_service.py
- Updated news_router.py docstring to reference dynamic news_sources.py config instead of hardcoded source list
- Fixed stale TODO comments in buy_executor.py and sell_executor.py (limit order tracking is implemented)
- Clarified TODO comments for short order limit logic (buy_executor, sell_executor)
- Removed obsolete `TODO: Support multiple exchange accounts per user` from order_monitor.py (Account model exists)
- Fixed inconsistent section numbering in BotFormModal.tsx (dropped numbers, kept descriptive names)
- Added explanatory comment for 3Commas-style DCA ladder calculation in ThreeCommasStyleForm.tsx
- Added explanatory comment for PnL carousel infinite-scroll pattern in BotListItem.tsx
- Added BUG comment flagging broken user credential lookup in ai_service.py (uses nonexistent User attrs)
- No behavioral changes — all fixes are comment/docstring only

## [v1.31.3] - 2026-02-15

### Changed
- Fixed all 175+ Python flake8 lint issues across 50 files (zero remaining)
- Fixed all 7 frontend TypeScript errors (zero remaining)
- Sorted imports with isort on all modified files
- Removed dead code: shadowed method definitions in PaperTradingClient, unused variables, unused imports
- Replaced bare `except:` with `except Exception:` (E722)
- Changed SQLAlchemy `== True/False` comparisons to idiomatic `.is_(True)/.is_(False)` (E712)
- Fixed f-strings without placeholders, ambiguous variable names, whitespace formatting
- Removed unused `global` declarations that only read (never assigned) module-level variables
- Added `logger` definition to exchange_clients/base.py (was undefined)
- Fixed PnLChart.tsx to use correct field names (`cumulative_pnl_usd` instead of `cumulative_pnl`)
- No behavioral changes — all fixes are mechanical/cosmetic

## [v1.31.2] - 2026-02-15

### Changed
- Codebase housekeeping: deleted 16 stale markdown docs, 17 duplicate/obsolete scripts from backend
- Removed unused arbitrage package (stat_arb_analyzer, triangular_detector) and empty bot_monitoring module
- Removed unused FundingRatesResponse type from frontend
- Replaced duplicate SELL_FEE_RATE constant in TradingViewChartModal with import from positionUtils
- Removed ~20 debug console.log statements from frontend (useIndicators, DealChart, Charts, ClosedPositions)
- Downgraded WebSocket lifecycle logs from console.log to console.debug in NotificationContext
- Moved 4 useful scripts (clean_slate, sell_all_simple, check_all_accounts, update_trade_fills) to backend/scripts/

### Fixed
- get_coinbase() in dependencies.py, settings_router.py, and system_router.py now filters by authenticated user's account (was grabbing first account in DB regardless of user — critical for multi-user support)
- Removed stale "TODO: Once authentication is wired up" comments (auth has been wired up since v1.31.0)

## [v1.31.1] - 2026-02-15

### Changed
- Remove dead `get_current_user_optional` from auth_dependencies.py and auth_router.py
- Add Query bounds (ge/le) on all paginated limit parameters to prevent abuse
- Sanitize remaining `str(e)` in error responses across templates, news, and trading routers

### Fixed
- Removed console.log that leaked wallet_private_key in BotFormModal
- Sanitized WebSocket console.log to not expose JWT token or message payloads
- Fixed broken slippage-check fetch in helpers.ts (wrong env var → authFetch)
- Closed positions page now correctly fetches up to 500 results (was broken by undefined base URL)

### Security
- Added security headers middleware (X-Frame-Options: DENY, X-Content-Type-Options: nosniff, X-XSS-Protection, Referrer-Policy)
- File permissions hardened: .env, trading.db, and backups set to 600
- Added DB-level unique index migration for bot names to prevent race conditions
- All query limit parameters now bounded to prevent DoS via unbounded result sets

## [v1.31.0] - 2026-02-15

### Added
- Fernet encryption for API keys at rest (exchange credentials + AI provider keys)
- `authFetch()` helper and exported `api` instance for centralized authenticated HTTP calls
- WebSocket authentication via JWT query parameter
- Login rate limiting (5 attempts per 15 minutes per IP)
- Password strength requirements (min 8 chars, uppercase, lowercase, digit)
- JWT secret startup validation (refuses to start with default/empty secret)
- Auto-generate `JWT_SECRET_KEY` and `ENCRYPTION_KEY` in `setup.py`

### Changed
- Enforce authentication on all protected API endpoints (100% coverage)
  - Backend: all bot, position, settings, system, order history, strategies, scanner logs, validation, and limit order endpoints now require JWT
  - Only intentionally public endpoints remain unauthenticated (market data, candles, news, coin icons, auth)
- Frontend: eliminate all bare `axios` imports in favor of auth-enabled `api` instance
  - Fixed 13 frontend files using raw `fetch()` or bare `axios` that bypassed auth headers
  - Affects: LimitCloseModal, PositionCard, usePositionMutations, PerpsPortfolioPanel, Portfolio, Settings, useValidation, useBotsData, useChartsData, usePositionsData, DealChart, DepthChart, useChartData
- Tighten CORS (explicit methods/headers instead of wildcards)
- Sanitize error responses (generic messages instead of leaking internal exceptions)

### Fixed
- Portfolio page "Failed to fetch portfolio" error caused by missing auth headers on auto-refresh
- PnL chart showing "No closed positions yet" due to unauthenticated `/api/positions/pnl-timeseries` call
- AISentimentIcon causing continuous 401 errors every 30 seconds
- Path traversal vulnerability in coin icons endpoint
- Debug print statements leaking JWT tokens in `coinbase_api/auth.py`

### Security
- Every non-public endpoint now returns 401 without valid JWT token
- API keys encrypted at rest using Fernet symmetric encryption
- Credential decryption at all read points (exchange client, AI service, settings)
- `.env.bak*` patterns added to `.gitignore` to prevent accidental secret commits

## [v1.30.1] - 2026-02-15

### Fixed
- Widen bot edit modal (max-w-2xl → max-w-4xl) to fit volume/RSI indicator fields without horizontal scrolling

## [v1.30.0] - 2026-02-15

### Added
- Coinbase INTX perpetual futures support: API layer, bracket TP/SL orders, position monitoring
- Futures bot configuration: leverage (1-10x), margin type (Cross/Isolated), TP/SL percentages, direction
- Perps portfolio linking in Settings (discovers INTX portfolio UUID)
- Futures position display: leverage badge, liquidation price, TP/SL, unrealized PnL, funding fees
- Perps portfolio panel: margin balance, open positions summary
- Backend endpoints for perps products, portfolio, positions, modify TP/SL, close position
- Database migration for perpetual futures fields (accounts, bots, positions)

## [v1.29.0] - 2026-02-14

### Added
- CHANGELOG.md
- Min volume filter UI for bot configuration
- Increasing/decreasing operators for indicators

## [v1.28.2] - 2026-02-14

- Remove 6 PnL cards from Portfolio page

## [v1.28.1] - 2026-02-14

- Remove Portfolio Totals from Bots page (moved to Dashboard)

## [v1.28.0] - 2026-02-14

- Fix bot toggle switch, add Portfolio Totals to Dashboard, add same-pair deals config

## [v1.27.0] - 2026-02-14

- Fix indicator logs crash, add 7d projection basis, persist UI state

## [v1.26.3] - 2026-02-14

- Add compounded projected PnL row to Portfolio Totals

## [v1.26.2] - 2026-02-14

- Fix sparkline width by adding w-full to wrapper div

## [v1.26.1] - 2026-02-14

- Add show-stopped toggle, smart resize button, resize-all improvements

## [v1.26.0] - 2026-02-14

- Add all-time PnL, sparkline time labels, bot PnL %, fix PnL/day calc

## [v1.25.7] - 2026-02-14

- Add cascading filters to History page

## [v1.25.6] - 2026-02-14

- Add bot, market, and pair filters to History page

## [v1.25.5] - 2026-02-14

- Drive progress bar at 60fps via direct DOM updates, bypass React state

## [v1.25.4] - 2026-02-14

- Sort article and video source chips by category order

## [v1.25.3] - 2026-02-14

- Fix timeline progress bar getting stuck during TTS playback

## [v1.25.2] - 2026-02-14

- Remove all window.location.reload() calls to prevent TTS interruption

## [v1.25.1] - 2026-02-14

- Filter adult content from child TTS voices

## [v1.25.0] - 2026-02-14

- Add simultaneous deals for same pair (max_simultaneous_same_pair)

## [v1.24.3] - 2026-02-14

- Add missing source color mappings, suppress reconnect refetch when engaged
- Add missing article sources to category color map

## [v1.24.2] - 2026-02-13

- Assign rainbow-ordered colors to category filters (red→violet)

## [v1.24.1] - 2026-02-13

- Fix news source color mappings, sort categories, suppress refetch when engaged

## [v1.24.0] - 2026-02-13

- Add Volume RSI indicator and 10m/4h timeframes for bot conditions

## [v1.23.0] - 2026-02-13

- Add deal cooldown per pair to prevent immediate re-entry after close

## [v1.22.15] - 2026-02-13

- Fix MACD crossing detection: pass indicator cache for all strategies + noise filter

## [v1.22.14] - 2026-02-08

- Add Total Budget column to Positions page overall stats

## [v1.22.13] - 2026-02-08

- Fix TTS tracking drift, source filter colors, drop paywalled news sources

## [v1.22.12] - 2026-02-08

- Fix news sources missing summaries: replace title-only feeds, add og:description fallback

## [v1.22.11] - 2026-02-08

- Fix crossing detection re-firing bug & improve position decision history UX

## [v1.22.10] - 2026-02-08

- Fix AI/Finance news: correct RSS URLs and YouTube channel IDs

## [v1.22.9] - 2026-02-08

- Add AI and Finance as distinct news categories

## [v1.22.8] - 2026-02-08

- Show relative PnL delta on non-All timeframes in summary chart

## [v1.22.7] - 2026-02-08

- Add news router enhancements, sentiment card updates, and coin icons
- Add multi-select for news sources, matching category filter behavior
- Add resize deal budget feature to recalculate max_quote_allowed

## [v1.22.6] - 2026-02-08

- Respect bot reservations in auto-buy, remove force-run button from bot actions

## [v1.22.5] - 2026-02-08

- Exempt grid bots from seasonality, smooth sparkline data to 30 averaged points

## [v1.22.4] - 2026-02-08

- Refine carousel animation with realistic archery-inspired draw timing

## [v1.22.3] - 2026-02-08

- Enhance carousel bowstring animation with longer tension hold

## [v1.22.2] - 2026-02-08

- Clarify UI labels for AI analysis interval and cycle-based bot management

## [v1.22.1] - 2026-02-08

- Fix Portfolio Today PnL bug, persist news filters, remove article cap

## [v1.22.0] - 2026-02-08

- Add sparkline charts, replace dead feeds, add YouTube sources for all categories

## [v1.21.4] - 2026-02-07

- Restore projected debt milestones to US National Debt card

## [v1.21.3] - 2026-02-07

- Consolidate TTS voices into single shared constants file

## [v1.21.2] - 2026-02-07

- Fix Find Reading to navigate across pagination pages

## [v1.21.1] - 2026-02-07

- Fix bot actions menu clipped by overflow-hidden container

## [v1.21.0] - 2026-02-07

- Add multi-category news system with 50 sources across 9 categories

## [v1.20.41] - 2026-02-06

- Add pip dependency installation to update.py

## [v1.20.40] - 2026-02-03

- Implement seasonality auto-management for bots (Phase 4)

## [v1.20.39] - 2026-02-03

- Fix spurious error from audio.onerror when clearing src

## [v1.20.38] - 2026-02-03

- Fix race condition causing red button during TTS load

## [v1.20.37] - 2026-02-03

- Fix red button showing during article load

## [v1.20.36] - 2026-02-03

- Fix TTS button colors: grey spinner during loading

## [v1.20.35] - 2026-02-03

- Fix TTS auto-retry and error state handling

## [v1.20.34] - 2026-02-03

- Add 50+ TTS voices from all English locales

## [v1.20.33] - 2026-02-03

- Fix TTS article navigation state sync issues

## [v1.20.32] - 2026-02-03

- Sync frontend season wheel with halving-anchored backend logic

## [v1.20.31] - 2026-02-03

- Enhance season detector with halving cycle anchoring

## [v1.20.30] - 2026-02-03

- Add seasonality toggle to Bots page

## [v1.20.29] - 2026-02-03

- Fix clone bot, update season colors, position wheel icons

## [v1.20.28] - 2026-02-02

- Add margin-right to season badge for spacing

## [v1.20.27] - 2026-02-02

- Fix season badge spacing in header

## [v1.20.26] - 2026-02-02

- Move season indicator to site header

## [v1.20.25] - 2026-02-02

- Rename market seasons to Winter/Spring/Summer/Fall

## [v1.20.24] - 2026-02-02

- Fix market season algorithm: better bear vs accumulation detection

## [v1.20.23] - 2026-02-02

- Add market season card and info tooltips to carousel
- Add 6 new market metrics cards to carousel

## [v1.20.22] - 2026-02-02

- Reset auto-cycle timer on manual carousel interaction

## [v1.20.21] - 2026-02-02

- Fix carousel transform calculation for infinite scroll

## [v1.20.20] - 2026-02-02

- Add infinite carousel with swipe/touch support

## [v1.20.19] - 2026-02-02

- Add spring animation to market sentiment carousel

## [v1.20.18] - 2026-02-02

- Add market metrics carousel with BTC dominance, altseason index, and stablecoin supply

## [v1.20.17] - 2026-02-02

- Add debt ceiling display and weekly AI monitoring

## [v1.20.16] - 2026-02-02

- Fix synthetic chart timeframes and stabilize debt rate calculation

## [v1.20.15] - 2026-02-02

- Reorder mini player controls: volume before replay, queue before close
- Revert "Reorder mini player controls: volume before replay, queue before close"

## [v1.20.14] - 2026-02-02

- Reorder mini player controls: volume before replay, queue before close

## [v1.20.13] - 2026-02-02

- Update article reader controls to match YouTube pattern

## [v1.20.12] - 2026-02-02

- Improve word highlighting for TTS sync

## [v1.20.11] - 2026-02-02

- Mini player thumbnail click navigates to News and finds article

## [v1.20.10] - 2026-02-01

- Add missing news sources to setup.py defaults

## [v1.20.9] - 2026-02-01

- Revert Playwright implementation
- Skip Playwright for bot-blocked sites like The Block
- Add Playwright support for JS-heavy sites like The Block

## [v1.20.8] - 2026-02-01

- Make video and article players mutually exclusive

## [v1.20.7] - 2026-02-01

- Use migration flag for voice cycling localStorage fix
- Force clear stale voice cycling localStorage value

## [v1.20.6] - 2026-02-01

- Restore voice cycling toggle with proper localStorage handling
- Debug: Force voice cycling always on to isolate issue
- Use persistent Audio element to fix autoplay between articles

## [v1.20.5] - 2026-02-01

- Change progress bar to word-based instead of time-based

## [v1.20.4] - 2026-02-01

- Fix word highlighting for en-dash separated words

## [v1.20.3] - 2026-02-01

- Fix word highlighting for em-dash separated words
- Add TODO for Playwright support for JS-rendered articles

## [v1.20.2] - 2026-01-31

- Fix word highlighting for hyphenated words and end-of-playback

## [v1.20.1] - 2026-01-31

- Fix voice cycling and improve word highlighting sync

## [v1.20.0] - 2026-01-31

- Add article reader with mini-player and voice cycling TTS
- Add synchronized TTS with word highlighting and auto-scroll

## [v1.19.1] - 2026-01-27

- Revert "Add acronym expansion for consistent TTS pronunciation"
- Add acronym expansion for consistent TTS pronunciation
- Strip markdown formatting from article text before TTS
- Fix TTS autoplay blocked by browser policy

## [v1.19.0] - 2026-01-27

- Add text-to-speech for reading news articles aloud

## [v1.18.4] - 2026-01-27

- Add missing dependencies for complete fresh install

## [v1.18.3] - 2026-01-27

- Sync setup.py schema defaults with production database

## [v1.18.2] - 2026-01-27

- Add polished toast notification for clipboard copy

## [v1.18.1] - 2026-01-27

- Improve bot import/export UX

## [v1.18.0] - 2026-01-27

- Add bot import/export functionality

## [v1.17.9] - 2026-01-27

- Fix Charts page not rendering data after loading

## [v1.17.8] - 2026-01-27

- Fix JSON field parsing for AI/Indicator logs
- Optimize AI/Indicator log loading with SQL UNION query

## [v1.17.7] - 2026-01-26

- Add pulse/glow notification effect for new AI and Indicator logs

## [v1.17.6] - 2026-01-26

- Add infinite loop scrolling to PnL carousel (Price is Right wheel effect)
- Fix number clipping in Projected PnL carousel
- Fix toggle overlap and add smooth vertical scrolling to PnL carousel
- Add auto-scrolling carousel for Projected PnL with expand/collapse toggle
- Add tasteful boxes around each Projected PnL timeframe for better grouping
- Add whitespace-nowrap and width constraints to prevent PnL text wrapping
- Further reduce Active trades column padding to free up space
- Reduce table column padding to prevent PnL text wrapping

## [v1.17.5] - 2026-01-26

- Add dual-currency (BTC/USD) display to bot PnL and Projected PnL columns

## [v1.17.4] - 2026-01-26

- Fix missing closing parenthesis in PnLChart.tsx ternary operator
- Add dual-currency display to PnL by day and by pair bar charts

## [v1.17.3] - 2026-01-26

- Increase news article thumbnail resolution by 50%

## [v1.17.2] - 2026-01-26

- Improve Portfolio table readability and reduce width
- Fix profit_btc calculation - compute dynamically from existing fields
- Fix linting warnings in PnLChart.tsx
- Add dual-currency (BTC/USD) display to Bots PnL chart with toggle

## [v1.17.1] - 2026-01-26

- Add chart panning constraints to Account Value chart

## [v1.17.0] - 2026-01-26

- Add Last Year to historical period selector

## [v1.16.0] - 2026-01-26

- Add WTD (Week To Date) and improve font consistency

## [v1.15.0] - 2026-01-26

- Reorganize realized PnL into logical groups

## [v1.14.0] - 2026-01-26

- Add selectable realized PnL periods with Last Month and Last Quarter

## [v1.13.0] - 2026-01-26

- Add MTD/QTD/YTD selector for realized PnL

## [v1.12.0] - 2026-01-26

- Add 4-week and YTD realized PnL tracking
- Add realized PnL stats (daily/weekly) to Positions page

## [v1.11.1] - 2026-01-26

- Fix: Handle nested condition groups in interval calculation

## [v1.11.0] - 2026-01-26

- Phase 3: Lazy fetching - only fetch timeframes for current trading phase
- Phase 2: Smart check scheduling based on indicator timeframes

## [v1.10.0] - 2026-01-26

- Phase 1: Smart candle caching with per-timeframe TTL

## [v1.9.9] - 2026-01-26

- Add image compression for news article thumbnails

## [v1.9.8] - 2026-01-26

- Add automated cleanup job for old failed orders

## [v1.9.7] - 2026-01-26

- Add automated cleanup job for failed condition logs

## [v1.9.6] - 2026-01-26

- Add detailed budget logging to indicator logs for GUI visibility

## [v1.9.5] - 2026-01-26

- Fix technical checks to evaluate conditions and execute trades

## [v1.9.4] - 2026-01-25

- Fix frontend N/A display for indicator condition details
- Fix AI indicator evaluation: pass product_id to analyze_signal
- Fix AI indicator evaluation: pass db and user_id to analyze_signal
- Fix syntax error in AIBotLogs.tsx (extra closing paren)
- Fix AI Bot Reasoning logs for indicator-based bots with AI indicators

## [v1.9.3] - 2026-01-25

- Add no-cache headers to positions API to prevent browser HTTP caching
- Fix stale cache showing incorrect positions/gains on page load

## [v1.9.2] - 2026-01-23

- Fix aggregate cache causing incorrect budget allocation after deposits
- Smart video muting: only mute on iOS devices
- Fix iPad video autoplay issue by starting videos muted

## [v1.9.1] - 2026-01-19

- Fix budget calculator to match order execution logic

## [v1.9.0] - 2026-01-19

- Add automatic paper trading account creation

## [v1.8.7] - 2026-01-19

- Improve Indicator Logs UI with better filter labels and stats
- Enable indicator logging for ALL evaluations, not just matches
- Stop tracking CLAUDE.md in git (add to .gitignore)
- Fix all TypeScript compilation errors

## [v1.8.6] - 2026-01-19

- Fix budget calculator: divide by max deals, not number of pairs
- Fix TypeScript linting errors: unused imports and type mismatches
- Fix bot config DCA budget validation math errors
- Fix trading router exchange client import

## [v1.8.5] - 2026-01-18

- Fix trading router import and disable sell when positions are open

## [v1.8.4] - 2026-01-18

- Add quick sell buttons to Portfolio page

## [v1.8.3] - 2026-01-18

- Fix TypeScript types for bidirectional trading and multi-currency balances

## [v1.8.2] - 2026-01-18

- Setup: Offer existing values as defaults when re-running

## [v1.8.1] - 2026-01-18

- Make setup.py safe to run multiple times (idempotent)

## [v1.8.0] - 2026-01-18

- Add migration to convert coin categorizations to global entries
- Fix setup.py to seed coin categorizations as global entries
- Add copy-to-account feature for bots

## [v1.7.3] - 2026-01-18

- Add smooth curved lines to chart (like 3Commas)

## [v1.7.2] - 2026-01-18

- Remove horizontal dashed current price lines from chart
- Remove rightOffset and barSpacing that were hiding data
- Add chart padding and margins to separate price lines from opposite axes
- Fix BTC y-axis to always show 8 decimal places
- Change BTC line color to solid orange (#ff8800)
- Fix chart default time range to 'all' instead of disabled '30d'

## [v1.7.1] - 2026-01-18

- Add account filter toggle to value chart - show selected account or all accounts

## [v1.7.0] - 2026-01-18

- Comprehensive macOS setup.py fixes for seamless installation

## [v1.6.3] - 2026-01-18

- Fix setup.py to properly install Homebrew and npm on macOS
- Fix account value snapshots to match portfolio display
- Fix account value chart to use authenticated API instance
- Fix account value chart authentication and paper trading toggle

## [v1.6.2] - 2026-01-17

- Complete paper trading snapshot implementation
- Fix account snapshot service SQLAlchemy async issues

## [v1.6.1] - 2026-01-17

- Update CLAUDE.md: Use systemctl for both backend and frontend services
- Add comprehensive plan verification document
- Complete bidirectional DCA grid bot implementation
- Final verification against implementation plan
- Phase 5: Add reservation display to Dashboard
- Add implementation summary and progress documentation
- Phase 3-4: Short order execution and bot validation
- Document per-account (per-CEX) reservation isolation
- Separate live and paper trading reservations
- Add asset conversion tracking for bidirectional bots
- Add bidirectional DCA grid bot foundation

## [v1.5.2] - 2026-01-16

- Fix import error: get_current_user from auth_dependencies

## [v1.5.1] - 2026-01-16

- Exclude paper trading accounts from account value chart by default

## [v1.5.0] - 2026-01-16

- Add account value history chart with daily snapshots

## [v1.4.0] - 2026-01-16

- Add ETH/USD price display next to BTC price in header

## [v1.3.1] - 2026-01-16

- Fix BTC/USD price display in header for paper trading

## [v1.3.0] - 2026-01-16

- Fix paper trading history isolation and update setup.py schema

## [v1.2.0] - 2026-01-14

- Restore AccountSwitcher dropdown, exclude paper trading from list
- Remove AccountSwitcher dropdown, keep only Paper Trading toggle
- Remove temporary debugging code
- Fix black screen: Add missing botsFetching destructuring
- CRITICAL FIX: Exclude paper trading accounts from get_coinbase_from_db
- Add temporary debug logging for bots page filtering issue
- Improve Bots page empty state message for account switching
- Fix: Reduce bot list refetch interval from 5s to 30s
- Add production-ready enhancements: rebalancing cooldown and exchange minimum validation
- Change paper trading toggle to orange when enabled
- Fix paper trading portfolio format to match frontend expectations
- Fix paper trading portfolio and balance queries
- Fix paper trading portfolio display in header
- Fix paper trading balances to show virtual balances
- Add Paper Trading balance management UI
- Fix import path for get_current_user in paper trading router
- Add paper trading functionality
- Update grid trading status documentation - ALL PHASES COMPLETE
- Phase 4: Complete Hybrid AI range mode
- Phase 7: Implement time-based grid rotation
- Phase 6: Implement volume-weighted grid levels
- Phase 5: Implement AI-Dynamic Grid optimization
- Add comprehensive grid trading implementation status document
- Fix unit test expectations for grid calculations
- Add strategies API endpoint and wire frontend to use it
- Phase 8: Enhanced frontend balance display with 3-column layout
- Phase 3: Dynamic breakout detection and grid rebalancing
- Phase 1-2: Grid order placement and neutral/long grid execution
- Phase 1: Implement GridTradingStrategy with core calculations
- Phase 0: Add capital reservation tracking for grid trading bots

## [v1.0.0] - 2026-01-13

- Show ALL quote currency balances (BTC, ETH, USD, USDC, USDT)
- Show reserved and available balances for all quote currencies
- Track BTC profit for all positions and show available balance
- Implement completed trades profit statistics on Positions page
- Fix backspace delete functionality for all numeric input fields

## [v0.134.2] - 2026-01-11

- Emphasize coin categorization is a critical safety feature

## [v0.134.1] - 2026-01-11

- Remove unused get_api_key_for_provider() fallback function

## [v0.134.0] - 2026-01-11

- Separate user and system AI API keys: users must configure their own

## [v0.133.13] - 2026-01-11

- Remove unused config variables: secret_key and ticker_interval

## [v0.133.12] - 2026-01-11

- Add missing video_articles table to setup.py database initialization

## [v0.133.11] - 2026-01-11

- Clarify AI Bot Quick Start is entirely GUI-based

## [v0.133.10] - 2026-01-11

- Remove auto-deployment comment from README

## [v0.133.9] - 2026-01-11

- Remove Recent Updates section from README

## [v0.133.8] - 2026-01-11

- Add update.py usage documentation to README

## [v0.133.7] - 2026-01-11

- Update README to accurately reflect setup ease and current capabilities

## [v0.133.6] - 2026-01-11

- Fix: Always monitor existing positions regardless of category filter

## [v0.133.5] - 2026-01-11

- Add category badges to pairs list and counts to category checkboxes

## [v0.133.4] - 2026-01-11

- Remove category permissions UI from Settings page
- Add bot-level category filtering for trading pairs
- Add dedicated MEME category for coin review
- Add auto-add new pairs option to bot configuration
- Reduce log noise from delisted pairs and fix port reference

## [v0.133.3] - 2026-01-09

- Fix portfolio conversion ImportError crash preventing sell orders

## [v0.133.2] - 2026-01-09

- Fix auto-buy BTC toggle not persisting on page refresh

## [v0.133.1] - 2026-01-09

- Make portfolio conversion per-account instead of global

## [v0.133.0] - 2026-01-09

- Restore Portfolio Conversion UI to Settings page

## [v0.132.0] - 2026-01-08

- Rename repository from GetRidOf3CommasBecauseTheyGoDownTooOften to ZenithGrid

## [v0.131.3] - 2026-01-08

- Clean up test files
- Add donation addresses to README

## [v0.131.2] - 2026-01-08

- Add donation addresses to LICENSE file

## [v0.131.1] - 2026-01-08

- Major refactoring: Modularize all large components and update licensing
- Fix setup.py: Add missing user_attempt_number column to positions table

## [v0.131.0] - 2026-01-08

- Major refactoring: Modularize all large components + fix auto-calculate budget

## [v0.130.1] - 2026-01-03

- Fix auto-buy USD conversion bugs

## [v0.130.0] - 2026-01-03

- Fix percentage placeholders appearing during portfolio refetch
- Fix loading screen when changing timeframes - use keepPreviousData
- Fix absurd projection calculations by using linear extrapolation
- Fix loading spinner appearing when changing timeframes
- Show full timeframe window in chart including zero-profit days
- Fix projections not updating when changing timeframes
- Prevent loading spinner when changing timeframes in Bots page
- Fix timeframe selector requiring double-click by adding explicit button type

## [v0.129.2] - 2026-01-03

- Fix auto-calculate safety order sizing bugs
- Archive all migration files - not needed for fresh installs
- Fix deal number migration to not assign numbers to failed positions

## [v0.129.1] - 2026-01-02

- Fix auto-calculate budget bug and UI deal number display
- Use Edit Order API for bid fallback instead of cancel-and-replace
- Implement Coinbase native Edit Order API for limit price updates

## [v0.129.0] - 2026-01-02

- Keep order type when enabling auto-calculate, compute optimal values
- Only auto-calculate base order size when toggle is enabled
- Auto-calculate base order size to fit budget with safety orders
- Use print() instead of logger for startup reconciliation messages
- Fix: Integrate startup reconciliation into main limit order monitor

## [v0.127.5] - 2026-01-02

- Add startup reconciliation for limit orders

## [v0.127.4] - 2026-01-02

- Fix base order sizing to reserve budget for safety orders

## [v0.127.3] - 2026-01-02

- Add rate limiting to Coinbase API calls to prevent 403 errors

## [v0.127.2] - 2026-01-02

- Add safety check: Prevent market order fallback below minimum profit target

## [v0.127.1] - 2026-01-02

- Fix: Round buy amounts to exchange increment to prevent profit loss on sell
- Fix model import: Setting -> Settings (plural)

## [v0.128.0] - 2026-01-01

- Add configurable cleanup for old decision logs

## [v0.127.0] - 2026-01-01

- Add unified decision logs (AI + Indicators)

## [v0.126.2] - 2026-01-01

- Fix all strategy parameter number inputs (including take profit)

## [v0.126.1] - 2026-01-01

- Fix number input fields allowing proper backspace/deletion

## [v0.126.0] - 2026-01-01

- Add clickable deal numbers with trade history popup

## [v0.125.0] - 2025-12-31

- Implement dual numbering system and 3Commas-style deal tracking

## [v0.124.1] - 2025-12-31

- Fix changelog cache not auto-refreshing when new tags created

## [v0.124.0] - 2025-12-31

- Add auto-buy BTC with stablecoins feature

## [v0.123.0] - 2025-12-31

- Add explicit auto-calculate toggle for DCA budget calculator

## [v0.122.2] - 2025-12-31

- Enforce exchange minimums in budget calculator with warnings

## [v0.122.1] - 2025-12-31

- Make order size fields read-only when budget calculator active

## [v0.122.0] - 2025-12-31

- Add DCA budget calculator with auto-sizing breakdown

## [v0.121.0] - 2025-12-31

- Make PnL projections configurable by chart timeframe

## [v0.120.0] - 2025-12-31

- Replace AI indicators with unified AI Spot Opinion system

## [v0.119.1] - 2025-12-31

- Fix Dashboard metrics to show accurate profit and win rate stats

## [v0.119.0] - 2025-12-26

- Frontend: Add real-time progress tracking for portfolio conversion
- Backend: Add real-time progress tracking for portfolio conversion

## [v0.118.0] - 2025-12-26

- Add detailed progress tracking to portfolio conversion
- Complete symmetric portfolio conversion logic + dust filtering

## [v0.117.0] - 2025-12-26

- Add rate limit delays to portfolio conversion (0.2s between orders)
- Add detailed error logging for Coinbase API failures
- Add error handling for Coinbase API failures in sell-portfolio endpoint
- Improve sell-portfolio-to-base: handle missing trading pairs via USD route
- Fix sell-portfolio-to-base endpoint - correct create_market_order call

## [v0.116.0] - 2025-12-25

- Enhance MissingOrderDetector to catch sell orders and stuck pending orders

## [v0.115.3] - 2025-12-25

- Fix critical duplicate limit order bug and position data inconsistencies

## [v0.115.2] - 2025-12-21

- Fix changelog Load More being slow - remove repeated git fetch

## [v0.115.1] - 2025-12-21

- Improve changelog loading performance

## [v0.115.0] - 2025-12-21

- Add About page with paginated changelog, fix stopped bots monitoring

## [v0.114.0] - 2025-12-18

- Add bidirectional chart synchronization for indicator panels

## [v0.113.4] - 2025-12-15

- Revert speculative bar spacing change - data is correct, label thinning is normal

## [v0.113.3] - 2025-12-15

- Adjust chart time scale spacing for better label visibility
- Add debug logging for PnL chart date range issue

## [v0.113.2] - 2025-12-15

- Fix PnL chart date range using string comparison

## [v0.113.1] - 2025-12-15

- Fix PnL chart not showing dates up to today

## [v0.113.0] - 2025-12-15

- Add >= and <= operators to phase condition selector

## [v0.112.16] - 2025-12-14

- Update cleanup documentation and fix setup.py service template
- Update cleanup script with comprehensive retention policies
- Add daily database cleanup script

## [v0.112.15] - 2025-12-14

- Add coin icon proxy to avoid CORS issues

## [v0.112.14] - 2025-12-14

- Fix recharts negative dimension warning by setting minimum chart height
- Fix greenlet SQLAlchemy error by eager loading Position.trades

## [v0.112.13] - 2025-12-14

- Add 14 days time range option

## [v0.112.12] - 2025-12-14

- Fix time range button logic - enable up to first covering timeframe

## [v0.112.11] - 2025-12-14

- Disable time range buttons that wouldn't show additional data

## [v0.112.10] - 2025-12-14

- Add 1 year time range filter to Bot Management PnL chart

## [v0.112.9] - 2025-12-14

- Fix AI coin review providers and model names

## [v0.112.8] - 2025-12-14

- Fix greenlet conflict by using sync SQLite for AI provider lookup

## [v0.112.7] - 2025-12-14

- Add AI provider selection for coin review

## [v0.112.6] - 2025-12-14

- Fix HTML entity encoding in og:image URLs (e.g., &amp; -> &)

## [v0.112.5] - 2025-12-14

- Add image proxy endpoint for cached thumbnails

## [v0.112.4] - 2025-12-14

- Add og:image fallback for feeds without thumbnails (Blockworks)

## [v0.112.3] - 2025-12-14

- Fix news loading performance by using URL thumbnails instead of base64

## [v0.112.2] - 2025-12-14

- Switch articles to client-side pagination for instant page changes

## [v0.112.1] - 2025-12-14

- Fix indicator logging: respect bot capacity and DCA slots

## [v0.112.0] - 2025-12-14

- Add pagination for news articles, remove video limit

## [v0.111.2] - 2025-12-14

- Fix: Use only closed candles for indicator calculations

## [v0.111.1] - 2025-12-13

- Skip entry indicator logging when position already exists

## [v0.111.0] - 2025-12-13

- Fix dropdown to float but start at button position
- Fix playlist dropdown to anchor below button instead of fixed position
- Extend news/video max age from 7 to 14 days

## [v0.110.0] - 2025-12-13

- Add new crypto news and YouTube sources

## [v0.109.5] - 2025-12-13

- Tone down pulse animation - subtler outline and fewer pulses

## [v0.109.4] - 2025-12-13

- Fix pulse animation using outline instead of box-shadow to avoid conflict with ring classes

## [v0.109.3] - 2025-12-13

- Reorganize MiniPlayer layout with stacked rows and enhance pulse effect

## [v0.109.2] - 2025-12-13

- Add pulsing red halo effect when clicking Find Playing button

## [v0.109.1] - 2025-12-13

- Fix time scrubber not updating on video autoplay
- Add db backup files to gitignore
- Add hover-to-scroll to News page 'Start from video' dropdown

## [v0.109.0] - 2025-12-13

- Fix VIDEO_CACHE_CHECK_MINUTES import and add MiniPlayer enhancements

## [v0.108.0] - 2025-12-13

- Add background content refresh and video database storage
- Fix video autoplay skipping every other video

## [v0.107.0] - 2025-12-13

- Add scroll-to-playing button for video list
- Add halo effect to currently playing video in News page
- Add database cleanup service creation to setup.py wizard

## [v0.106.2] - 2025-12-13

- Fix PnL chart to prevent zooming beyond data bounds

## [v0.106.1] - 2025-12-13

- Fix stopped bots to properly manage open positions

## [v0.106.0] - 2025-12-13

- Add database cleanup maintenance script with systemd timer

## [v0.105.2] - 2025-12-13

- Fix Active Deals showing empty due to failed position flood
- Increase throttling delays to allow API requests during bot monitoring
- Add throttling constants for t2.micro CPU optimization
- Add processing delays to reduce CPU burst on t2.micro
- Optimize API call frequency with increased cache TTLs

## [v0.105.1] - 2025-12-12

- Add percentage field validation against exchange minimums
- Add price_drop as visible DCA condition in indicator logs
- Fix: Remove redundant max_concurrent_deals division in calculate_base_order_size
- Fix: Respect split_budget_across_pairs toggle
- Fix budget_percentage: 0 means 0, 100 means 100
- Fix: budget_percentage=0 now means 100% (All) as UI indicates
- Fix MACD display: show 8 decimals, scientific notation for tiny values
- Fix USD-based bot form: dynamic currency labels
- Fix indicator precision: use 8 decimals for MACD values
- Fix indicator value display precision in logs
- Fix indicator logging and add higher timeframe support
- Add ONE_HOUR candle fetching for hourly MACD/RSI conditions
- Fix crossing detection for BB% and other indicators
- Skip logging DCA/Exit conditions for pairs without positions
- Fix crossing detection for indicator_based entry conditions
- Fix crossing detection for entry conditions (MACD Bot fix)

## [v0.105.0] - 2025-12-12

- Add daily trading pair monitor to sync delisted/new pairs
- Add deal age display to position cards

## [v0.104.1] - 2025-12-12

- Fix playlist double-advance bug: prevent nextVideo from being called twice
- Revert MiniPlayer to before background playback changes
- Fix YouTube player controls and background playback
- Keep YouTube video playing when tab loses focus

## [v0.104.0] - 2025-12-11

- Add bot creation fixes, optimistic updates, and schema sync
- Add npm dependency handling to update.py
- Upgrade all npm dependencies to latest major versions
- Update npm dependencies and CLAUDE.md environment detection

## [v0.103.2] - 2025-12-11

- Add rate limiting between order executions to prevent Coinbase 403 throttling

## [v0.103.1] - 2025-12-11

- Fix playlist auto-advance: subscribe to YouTube iframe events
- Increase video hover size to 6x (672x384px)
- Fix video hover: use overflow-visible and explicit size change
- Add hover-to-enlarge effect on mini player video

## [v0.103.0] - 2025-12-10

- Fix limit order UI: CoinbaseAdapter time_in_force and price step arrows
- Fix: Edit Limit Price now properly preselects current limit price
- Update setup.py schema for pending_orders GTD fields

## [v0.102.0] - 2025-12-10

- Add GTD (Good 'til Date) order type support for limit close orders

## [v0.101.0] - 2025-12-10

- Show Deal # and pair in limit close modal title
- Make depth chart rows dynamically fill available space
- Round mark price UP to valid precision for sell orders
- Add quick-select buttons for Bid, Mark, Ask prices in limit close modal
- Enhance limit close modal: clickable depth chart, extended slider range
- Highlight limit price in depth chart with light grey outline

## [v0.100.16] - 2025-12-10

- Add /api/market/btc-usd-price endpoint
- Add today's USD value for closed BTC positions (HODL tracker)
- Show USD profit value for closed BTC pair positions

## [v0.100.15] - 2025-12-09

- Add ESC key handler to LimitCloseModal
- Extend slider range when limit price is outside bid-ask
- Fix Coinbase orderbook API endpoint
- Fix: Add get_product_book to CoinbaseAdapter

## [v0.100.14] - 2025-12-09

- Add Level 2 order book depth chart to limit close modal
- Fix slider resetting: remove price reset from fetchTicker

## [v0.100.13] - 2025-12-09

- Fix slider resetting to mark on ticker updates

## [v0.100.12] - 2025-12-09

- Add tick marks on slider to show valid price levels

## [v0.100.11] - 2025-12-09

- Slider snaps to valid precision steps for each coin

## [v0.100.10] - 2025-12-09

- Add breakeven tick mark to limit close slider

## [v0.100.9] - 2025-12-09

- Improve visual loss indicators in limit close modal

## [v0.100.8] - 2025-12-09

- Add loss confirmation alert for limit close orders

## [v0.100.7] - 2025-12-09

- Fix: Handle whole number base_increment in get_base_precision()
- Fix crossing detection for indicator-based strategies
- Add database seeding for fresh installs

## [v0.100.6] - 2025-12-09

- Extract thumbnails from RSS description HTML as fallback
- Derive allowed article domains from database instead of hardcoded list
- Add Bitcoin Magazine and BeInCrypto to allowed article domains
- Replace Reddit sources with Bitcoin Magazine and BeInCrypto
- Fix: Correct Reddit source names in migration
- Fix: Add auth headers to sources API calls
- Fix: Replace get_async_db with get_db in sources_router

## [v0.100.5] - 2025-12-09

- Add user source subscription UI and migrate news to DB sources

## [v0.100.4] - 2025-12-09

- Add database-backed content sources with user subscriptions

## [v0.100.3] - 2025-12-09

- Sync setup.py with production schema

## [v0.100.2] - 2025-12-09

- Add 6 new crypto YouTube channels to video news

## [v0.100.1] - 2025-12-09

- Unify video playback: individual videos open in expanded modal

## [v0.100.0] - 2025-12-09

- Add play/pause controls to mini-player
- Refactor: Single morphing player that transforms between mini-bar and modal
- Fix: Collapse mini-player when full modal opens to prevent duplicate playback
- Fix: Remove duplicate video iframe from mini-player thumbnail area

## [v0.99.0] - 2025-12-09

- Feature: Add persistent mini-player for video playlist

## [v0.98.0] - 2025-12-09

- Add video player modal for Play All in Crypto News
- Add alias support to update.py completion
- Add bash completion script for update.py

## [v0.97.1] - 2025-12-09

- Feature: Add longer timeframes (2d, 3d, 1w, 2w, 1M)

## [v0.97.0] - 2025-12-09

- Fix: Verify profit at mark price before placing limit sell orders

## [v0.96.9] - 2025-12-09

- Add indicator condition logging for non-AI bots

## [v0.96.8] - 2025-12-09

- Fix AI indicator detection to prioritize type field over legacy indicator field

## [v0.96.7] - 2025-12-09

- Fix update_ai_bots_with_dca migration to detect already applied state
- Fix migration idempotency detection for table creation migrations

## [v0.96.5] - 2025-12-09

- Fix: AI min confluence score default from 65 to 40 (moderate preset)

## [v0.96.4] - 2025-12-09

- Add graceful shutdown to wait for in-flight orders before stopping

## [v0.96.3] - 2025-12-09

- UI: Hide Safety Orders/Take Profit for pattern-based entries

## [v0.96.2] - 2025-12-09

- Bull Flag: Use pattern-calculated TSL/TTP instead of percentage-based config

## [v0.96.1] - 2025-12-09

- Add toggleable Safety Orders option to bot form
- Fix: Bull flag params not reading migrated config values

## [v0.96.0] - 2025-12-09

- Fix: AI log only shows SELL for pairs with positions

## [v0.95.9] - 2025-12-09

- Fix: Condition exits now require Take Profit % as minimum

## [v0.95.8] - 2025-12-08

- Fix: Add 'equal' and 'not_equal' operators to phase condition evaluator

## [v0.95.7] - 2025-12-08

- Fix: Add ai_buy/ai_sell/bull_flag handler in phase_conditions

## [v0.95.6] - 2025-12-08

- Fix BB indicator key format mismatch (2.0 vs 2)

## [v0.95.5] - 2025-12-08

- Fix THREE_MINUTE timeframe detection and BB% lower band requirement

## [v0.95.4] - 2025-12-08

- Fix TypeError in should_sell() when take_profit_percentage is None

## [v0.95.3] - 2025-12-08

- Fix: Recalibrate AI confluence thresholds to match scoring reality

## [v0.95.2] - 2025-12-07

- Fix: Don't migrate blacklisted_coins user_id in multi-user migration

## [v0.95.1] - 2025-12-07

- Fix: Bot AI icon detection for grouped condition format

## [v0.95.0] - 2025-12-07

- Fix: Remove Position model properties that cause async greenlet errors
- Feature: Accurate DCA tick marks based on reference price setting
- UI: Show all DCA target levels as tick marks on position cards

## [v0.94.0] - 2025-12-07

- Feature: DCA target improvements

## [v0.93.0] - 2025-12-07

- Lint: Fix remaining lint errors (E712, F541, F841, E741)
- Lint: Remove unused imports (F401) - 14 errors fixed

## [v0.92.2] - 2025-12-07

- UI: Show time in changelog version dates

## [v0.92.1] - 2025-12-07

- Fix: Handle fixed_btc order type and show position ID in failed orders
- Backend: Use condition-level AI risk presets and handle grouped conditions
- UI: Add risk preset and AI provider selectors for AI Buy/Sell indicators
- Feature: Advanced condition builder with grouping and NOT support

## [v0.92.0] - 2025-12-07

- Fix: Allow full BTC precision (8 decimals) in order amount inputs
- Fix: Enforce max_safety_orders limit in indicator_based strategy
- UI: Add funds modal with slider for percentage of available balance
- Fix: Handle null profit in WebSocket order fill handler
- Fix: Apply candle gap-filling to all timeframes, not just THREE_MINUTE
- Fix: Show clear BUY/SELL/HOLD decisions in AI bot logs for indicator_based strategy
- Fix: Handle NaN values in ThreeCommasStyleForm number inputs
- Fix: Handle AI logging for indicator_based strategy
- Fix: Add AI logging to process_bot_pair for non-batch strategies
- Add Max Concurrent Deals field to ThreeCommasStyleForm
- UI: Make Safety Order Volume/Step Scale always visible
- Fix: Add missing db.commit() calls for scanner logs
- Fix: Handle None aggregate_value in debug print statements
- Fix condition type normalization for bot edit form
- Fix Strategy Parameters section for indicator_based bots
- Fix: Strip query params from JWT URI to fix 401 errors
- Fix: Add market_context parameter to IndicatorBasedStrategy.should_sell()
- Fix: Add **kwargs to IndicatorBasedStrategy.should_buy()
- Fix: Initialize candles variable before use in process_single_bot
- Fix: Move prepare_market_context to candle_utils
- Refactor: Replace pre-baked strategies with unified indicator-based bot builder

## [v0.91.0] - 2025-12-06

- Refactor: Extract indicator modals from DealChart.tsx
- Refactor: Extract types and utils from MarketSentimentCards.tsx
- Refactor: Remove duplicate CandleData interface from Portfolio.tsx
- Refactor: Extract DEX constants and ABIs to dedicated module
- Refactor: Extract portfolio utilities from accounts_router.py
- Refactor: Remove duplicate utilities from LightweightChartModal
- Refactor: Extract news utilities from News.tsx
- Refactor: Extract IndicatorSettingsModal from Charts.tsx
- Refactor: Extract candle utilities from multi_bot_monitor.py
- Refactor: Extract bot utilities from Bots.tsx
- Refactor: Extract DealChart component from Positions.tsx
- Refactor: Extract utilities and AISentimentIcon from Positions.tsx
- Refactor: Extract models, sources, and cache from news_router.py
- Refactor: Extract debt ceiling data from news_router.py
- Docs: Add housekeeping file splitting plan

## [v0.90.0] - 2025-12-06

- Enhance AI providers UI to use API data directly
- Add AI provider credentials UI to Settings page

## [v0.89.0] - 2025-12-06

- Wire up AI providers to use database credentials with .env fallback
- Add per-user AI provider credentials storage in database
- Add Groq AI provider support (14,400 RPD free tier)

## [v0.88.2] - 2025-12-06

- Fix: Store news images as base64 in database instead of filesystem

## [v0.88.1] - 2025-12-06

- Fix: Proxy /static route to backend for cached news images

## [v0.88.0] - 2025-12-06

- Feat: Database-backed news caching with local image storage

## [v0.87.10] - 2025-12-06

- Feat: Add update available indicator in header

## [v0.87.9] - 2025-12-06

- Fix: Expose version in root endpoint for reliable frontend access

## [v0.87.8] - 2025-12-06

- Fix: Use dynamic path resolution for git version detection

## [v0.87.7] - 2025-12-06

- Fix: Fetch app version from backend API instead of Vite build-time

## [v0.87.6] - 2025-12-06

- Fix: Extend price bar range to always show next DCA level

## [v0.87.5] - 2025-12-06

- Fix: Color version number instead of 'Installed:' label

## [v0.87.4] - 2025-12-06

- Color 'Installed:' label based on how far behind

## [v0.87.3] - 2025-12-06

- Fix: Show only next DCA tick on position bar

## [v0.87.2] - 2025-12-06

- Simplify changelog header to show Latest/Installed only

## [v0.87.1] - 2025-12-06

- Fix: Show DCA tick marks for AI bots with manual DCA targets

## [v0.87.0] - 2025-12-06

- Feat: Add 3Commas-style deal editing for open positions

## [v0.86.7] - 2025-12-06

- Fix changelog wording: use 'Installed' instead of 'Current version'

## [v0.86.6] - 2025-12-06

- Enhance changelog to show current version and unpulled updates

## [v0.86.5] - 2025-12-06

- Smart service restart detection in update.py

## [v0.86.4] - 2025-12-06

- Add --changelog flag to update.py

## [v0.86.3] - 2025-12-06

- Fix insufficient_funds calculation to use current position values

## [v0.86.2] - 2025-12-06

- Make order recording atomic to prevent missed trades
- Add missing order detector service to prevent untracked trades

## [v0.86.1] - 2025-12-06

- Fix: History page missing recently closed positions

## [v0.86.0] - 2025-12-06

- Fix: Profit target now uses bot config with sell-side fee adjustment
- Fix: Account for trading fees in base amount for BTC pairs
- Fix: product-precision endpoint URL in LimitCloseModal
- Add video playlist auto-play feature to News page
- Fix: Bull flag pullback detection now finds red candles within window
- Add --preview flag to update.py to view incoming changes

## [v0.85.1] - 2025-12-05

- Fix: History badge not persisting viewed state

## [v0.85.0] - 2025-12-05

- Fix budget percentage calculation for manual sizing mode

## [v0.84.6] - 2025-12-05

- Fix coin categorization showing all as approved + add --skip-pull flag

## [v0.84.5] - 2025-12-04

- Add idempotency checks to migrations

## [v0.84.4] - 2025-12-04

- Fix History badge to track closed/failed counts separately

## [v0.84.3] - 2025-12-04

- Fix migrations to use relative paths instead of hardcoded paths

## [v0.84.2] - 2025-12-04

- Skip service restart in update.py when already up to date

## [v0.84.1] - 2025-12-04

- Add user_id and user_deal_number columns to setup.py schema

## [v0.84.0] - 2025-12-04

- Add user-specific deal numbers for positions

## [v0.83.0] - 2025-12-04

- Add git check to setup.py for version display

## [v0.82.0] - 2025-12-04

- Auto-inject git version into app at build time
- Add version display to header

## [v0.81.0] - 2025-12-04

- Update: Add frontend service support to update.py
- Add update.py script for automated production updates
- Add EULA/risk disclaimer acceptance flow for users
- Add license agreement acceptance to setup wizard
- Fix: Persist failed orders seen count across sessions

## [v0.80.0] - 2025-12-04

- Setup: Make Gemini default AI provider, add PEM key format handling
- Fix: Rename limit order monitor method to match main.py call
- Refactor: Make coin categorization admin-only with global visibility
- Fix: Update bot routers and coin review service to get Coinbase client from database
- Fix: Update all routers to get Coinbase client from database
- Fix: Position router dependencies now get Coinbase client from database
- Fix: Update account_router to get exchange client from database
- Fix: Use _current_exchange to avoid property conflict
- Fix: Set exchange client per-bot in monitoring loop
- Fix: Guard against None order_monitor in start/stop
- Multi-user Coinbase credentials from database
- Add setup introduction with step overview and confirmation prompt
- Fix bcrypt import error in setup wizard
- Add multi-provider AI support for coin categorization
- Clarify system vs per-user AI API keys in setup wizard
- Protect git-tracked deployment scripts during cleanup
- Auto-restart setup with Python 3.11 after installation
- Add animated spinner for long-running operations
- Offer to install Homebrew on Mac if not present
- Auto-install Python 3.11 when version too old
- Require Python 3.10+ and pin exact dependency versions
- Use flexible version constraints in requirements.txt
- Add --cleanup flag to setup wizard
- Remove setup.sh wrapper - users run python3 setup.py directly
- Add --uninstall-services flag to setup wizard
- Add --services-only flag to setup wizard
- Improve setup wizard to auto-detect and install dependencies
- Add setup wizard for initial application configuration
- Store history badge count in database per user
- Add confirmation dialog for sign out button
- Add password change UI to Settings page
- Add public signup with comprehensive EULA and risk disclosure
- Add user filtering to all routers and frontend auth interceptors
- Add multi-user support with JWT authentication
- Fix: Set account_id when creating positions
- Fix: Clear stale position errors when market data fetch succeeds
- Add ONE_MINUTE option to bull flag scanner timeframe
- Clean up debug logging after verifying gap-fill works
- Switch gap-fill debug logging to print() for guaranteed visibility
- Add entry-point debug logging to gap-fill function
- Add always-on gap-fill debug logging with max_gap info
- Add detailed gap-fill debug logging
- Add info-level logging for candle gap-filling to debug THREE_MINUTE issues
- Add candle gap-filling for sparse BTC pairs like charting platforms
- Fix Coinbase API 400 error from exceeding 300 candle limit
- Fix THREE_MINUTE BB% conditions failing on low-volume pairs
- Add Polyform Noncommercial 1.0.0 license
- Feat: Close article modal with ESC key
- Feat: Use compound interest for PnL projections
- Fix: Extract video_id from YouTube Shorts URLs
- Fix: Video playback affecting multiple videos in News page
- Cleanup: Remove verbose debug print statements from candle caching
- Fix: Request 300 ONE_MINUTE candles upfront for THREE_MINUTE cache
- Debug: Add print statements for candle caching visibility
- Change cache debug to logger.info to be visible
- Add debug logging for candle cache hits/misses
- Update handoff doc - mark both issues as fixed
- Fix BB% THREE_MINUTE indicator not populating for AI bots
- Fix force-close 500 error and add BB% debug logging
- Add detailed rejection reasons to bull flag pattern detection

## [v0.79.0] - 2025-11-30

- Fix PnL charts to show all dates, including days with no trades
- Feature: Add pagination to History page

## [v0.78.3] - 2025-11-30

- Fix: Add account_id to order history API response

## [v0.78.2] - 2025-11-30

- Fix: Show loading indicator for projected PnL percentages

## [v0.78.1] - 2025-11-30

- Fix: Trust initial AI buy signal for DCA, don't let secondary AI block it
- Fix: AI bots require buy signal for DCA, price drop is safeguard
- Fix: DCA no longer requires signal_type=buy
- debug: Add detailed logging to DCA decision flow
- debug: Add DCA decision logging to diagnose why DCAs aren't executing
- Perf: Increase cache TTLs and skip dust balances for faster API
- Perf: Parallelize API calls in aggregate value calculations
- Fix: DCA Completed count showing 0 instead of actual count

## [v0.78.0] - 2025-11-30

- Add Win Rate column to Bots table
- Add batched concurrency to bull flag scanner for rate limiting
- Fix: Bull flag scanner now scans all approved coins (was limited to 50)
- Fix volume detection and bull flag pattern validation
- Revert: Re-enable redirect_slashes to fix 404 errors
- Fix: Increase refetch intervals to prevent constant reload loop
- Fix: Disable redirect_slashes to prevent 307 redirects
- Fix: Batch position price fetches to avoid Coinbase rate limits
- Fix: Use get_product() for volume detection in bull flag scanner
- Fix: Optimize list_bots endpoint - pre-fetch aggregate values and batch price requests
- Fix: Add batched price fetching to accounts_router to prevent rate limits
- Speed up portfolio loading with batched price fetching
- Fix portfolio pagination and add debugging logs
- Add scanner logs feature for bull flag strategy
- Fix: Add aggregate_value parameter to bull_flag should_buy
- Add volume confirmation to bull flag pattern detection
- Fix: Bull flag scanner get_candles API compatibility
- Fix: Frontend Active Trades display for bull_flag strategy
- Fix: Bot stats max_concurrent_positions and portfolio missing assets
- Fix: Render bull_flag strategy parameter groups in frontend
- Fix: Make product_id Optional in BotResponse for multi-pair strategies
- Fix circular import in bull_flag_scanner
- Add bull flag USD trading strategy with TSL/TTP

## [v0.77.0] - 2025-11-30

- Fix: Add account_id to API response schemas for multi-account filtering
- Extract market sentiment cards into reusable component
- Reorganize nav: group account-specific vs general pages
- Add account filtering to PnLChart and pnl-timeseries API
- Simplify account filtering after DB migration
- Fix account filtering: DEX accounts now show only their own data
- Make History and Dashboard pages account-specific
- Fix header Account Value to use account-specific portfolio
- Fix Portfolio CEX/DEX account switching regression
- Fix all TypeScript errors in frontend codebase
- Add coin icons to Settings page coin categories list
- Add real-time order fill notifications with audio and visual alerts
- Improve news caching: 15-min refresh, 7-day retention, merge strategy
- Add 15-minute auto-refresh for news articles and videos
- Fix debt ceiling display: show values under $1T in billions
- Add complete US debt ceiling history from 1939 to present
- Add political context and source links to debt ceiling history
- Move debt ceiling history to modal, rename Milestones to Projected Milestones
- Move debt ceiling history to backend API
- Add debt ceiling history section showing last 7 increases/suspensions
- Add debt milestone countdowns for $1T and $5T markers
- Show specific estimated date for BTC halving countdown
- Fix Max safety orders display for AI autonomous bots
- Move commercialization roadmap to separate file
- Add commercialization roadmap for Zenith Grid
- Remove brotli from Accept-Encoding (not installed)
- Add full browser headers to article fetcher to fix 403 errors
- Default to reader mode when opening articles, always show thumbnail
- Fix duplicate title in reader mode with fuzzy matching
- Enhance reader mode with markdown formatting support
- Fix paragraph preservation in reader mode article content
- Add Reader Mode for news articles
- Add article preview modal to News page
- Add prominent open-in-new-tab button for videos
- Add inline YouTube video playback to News page
- Move News link to between Dashboard and Bots in nav
- Fix news timestamps: add UTC timezone indicator (Z suffix)
- Add periodic refresh for news article timestamps
- Add cache files and db backup patterns to gitignore
- Fix US debt counter to always count up
- Add US National Debt counter and halving countdown format toggle
- Fix BTC halving countdown timer - use stable dependency
- Add Fear/Greed Index and BTC Halving countdown to News page
- Add video news section with YouTube crypto channels
- Add feedparser dependency for news aggregation
- Fix Dashboard bot cards: profit and deals display
- Add crypto news aggregation tab with 24-hour caching

## [v0.76.0] - 2025-11-29

- Fix: Summary PnL chart shows relative profit for time range
- Fix: Most profitable bot card respects time range filter
- Fix: PnL by pair chart respects time range filter
- Fix: PnL stat should sum profits within selected time range
- Fix: PnL stat also showing $0 on by_pair tab
- Fix: Closed trades count incorrectly showing days instead of trades
- Optimize startup: lazy load pages and defer non-critical API calls
- Fix Portfolio page showing different values than header
- Fix AI Reasoning modal missing initial buy log
- Fix Dashboard showing different Account Value than header
- Fix order validation to use correct aggregate BTC value from balance_breakdown
- Fix section numbering: Strategy Parameters shows as 6 for AI, 7 for others
- Add validation to block save when manual order values are below exchange minimum
- Fix NaN warning in strategy parameter inputs
- Frontend: Budget settings only show in AI mode, not Manual mode
- Frontend: Add Max Concurrent Positions to Bot Budget Allocation section
- Frontend: Move Budget Allocation into Strategy Parameters for AI bots
- Fix aggregate BTC calculation: use current prices, not cost basis
- Frontend: Reorganize AI bot settings with conditional budget display
- Manual order sizing: use aggregate value for percentage calculations
- Add Manual Order Sizing group to frontend display order
- Optimize portfolio API: parallel price fetches + fix balance breakdown
- Fix portfolio balance breakdown for legacy positions
- Add 3Commas-style manual order sizing override
- Add MINIMUM PERCENTAGE to AI prompts to prevent below-minimum orders
- Update Claude API link to billing page
- Fix position_status in AI bot logs to show actual status
- Increase AI review timeout to 3 minutes
- Update AI review to scan all Coinbase coins in batches
- Extend tracked coins to include USD and USDC markets
- Redesign BlacklistManager with single table and category dropdowns
- Fix route order: Move /categories before /{symbol} to prevent conflicts
- Revert trailing slashes - endpoint works without them
- Fix: Add trailing slashes to category API endpoints
- Add category trading permissions with toggle UI
- Add weekly AI coin review service
- Add APPROVED coin category with green badges
- Add color-coded blacklist badges: BORDERLINE (yellow), QUESTIONABLE (orange), BLACKLISTED (red)
- Fix blacklist API trailing slash redirect issue
- Add coin blacklist feature
- Add THREE_MINUTE* synthetic candle support via 1-min aggregation
- Fix: Use ONE_MINUTE candles (THREE_MINUTE not supported by Coinbase)
- Support multi-timeframe BB% and faster technical checks
- Add debug logging for BB% take profit condition evaluation
- Add configurable DCA drop settings for AI bots
- Fix broken take profit conditions and add BB% support for AI bots
- Fix volume filter to always analyze pairs with open positions
- Fix deprecated token pricing - don't show misleading values
- Add legacy token price mapping for deprecated tokens
- Fix CoinGecko price fetching for free tier limits
- Add CoinGecko price fetching for DEX token valuations
- Fix DEX portfolio to show all tokens regardless of USD pricing
- Add old GALA token address (v1) for migration compatibility
- Switch to PublicNode RPC endpoints
- Add rate limiting delays and switch to Ankr RPC
- Switch to Cloudflare Ethereum RPC for better rate limits
- Add cUSDC, GALA, MANA tokens to DEX wallet service
- Fix corrupted DAI contract address
- Fix DEX portfolio rendering with optional chaining
- Integrate account filtering across all main pages
- Add account-specific portfolio endpoint with DEX support
- Fix accounts dropdown menu visibility
- Remove unused legacy Trading/MACD parameters from Settings
- Remove legacy Coinbase API credentials section from Settings
- Phase 9: Complete UI account switching integration
- Update handoff document with implementation status
- Phases 6-8: Complete Arbitrage Strategy Implementation
- Phase 5: Account Management & Context Switching
- Fix web3.py v6+ compatibility: Update middleware import
- Phase 4: Complete DEX frontend UI integration
- Phase 3: Complete Uniswap V3 integration with swap execution
- Phase 3: Add DEX client skeleton for Ethereum + Uniswap V3
- Fix order reconciliation monitor to use exchange_client
- Fix settings attribute names in main.py
- Phase 2: Add DEX fields to database schema
- Refactor: Complete exchange abstraction layer (Phase 1)
- Add exchange abstraction layer (Phase 1 foundation)
- Fix MP line to use bot's min_profit_percentage instead of hardcoded 2%
- Implement DCA budget protection to prevent insufficient DCA funds
- Fix AI budget calculation to use per-position budget
- Add Grok AI provider support to client validation
- Skip logging technical-only HOLD checks to reduce UI noise
- Implement two-tier bot checking architecture for efficient monitoring
- Fix Bollinger Band % crossing threshold input and add 3m timeframe
- Add exchange minimum order size requirement to AI prompts
- Add PhaseConditionSelector UI handler to AI Autonomous custom sell conditions
- Fix import error: use IndicatorCalculator class instead of standalone functions
- Add custom technical sell conditions to AI Autonomous strategy
- Replace hardcoded USDC PnL with dynamic API calculations
- Add USDC PnL placeholder cards to match BTC/USD column layout
- Add separate USDC Balance Breakdown column
- Fix budget availability check - add actual BTC balance verification
- Fix Dashboard Edit button to properly navigate and open bot edit modal
- Reorder bot config sections: group all AI-related settings together
- Improve Risk Tolerance UX with Manual option and preset visibility
- Add Duration column to closed positions table
- Sort History page tables by most recent first
- Fix limit order price precision: use product-specific decimals
- Implement product minimum fetching from product_precision.json
- AI aware of product minimums: inform AI and validate before execution
- Fix orphaned positions: mark as failed instead of expunging
- Add hard constraint: DCA only on meaningful drops below cost basis
- Add AI failsafe: auto-sell profitable positions when AI analysis fails
- Remove strict mode - AI bots are now purely AI-directed
- Improve control mode description to clarify AI vs user control
- Add toggle switch for AI bot control mode with conditional parameter display
- Fix AI autonomous strategy parameter handling and reorganization
- Update CLAUDE.md with production notes
- Add unrealized PnL sorting to Holdings table
- Fix USD Balance Breakdown to show only USD-denominated assets
- CRITICAL FIX: DCA failures should not abort entire bot cycle
- Add adaptive limit order with bid fallback
- Fix budget calculation: divide by max_concurrent_deals for fair per-position budget
- Sort closed positions by closure date (most recent first)
- Simplify sell order precision handling to match buy orders
- Add automatic order reconciliation monitor
- Fix market order fill tracking to handle slow fills properly
- Add precision rounding to all sell orders and enable OrderMonitor
- Fix get_order() unwrapping and add precision to strategy limit sells
- Fix limit order precision - use product_precision.json instead of Coinbase API
- Add enhanced error logging for limit order failures
- Fix limit close order size precision
- Implement proper partial fill handling for limit close orders
- Fix History sorting: closed positions now sort by closed_at desc
- Update Phase 5 bug report with Bugs #6 and #7
- Fix Bug #7: AIAutonomousStrategy missing _prepare_market_context
- Add logging to debug Coinbase limit order response format
- Bug #6: Add error logging to limit-close endpoint
- Fix Vite proxy IPv6 issue - use 127.0.0.1 instead of localhost
- Fix syntax error in strategy signatures
- Fix all 5 bugs identified in Phase 5 investigation
- Phase 5: Bug investigation report (no fixes applied)
- Phase 4: Code cleanup - unused variables and imports
- Phase 3: Type hint improvements
- Add HouseKeeping 1.1 progress report
- Phase 2: Code style improvements (PEP 8 compliance)
- Phase 1: Code formatting and documentation improvements
- Fix PEP 8 indentation and spacing issues (E129, E131, E302)
- Update bug investigation - all clear to proceed
- Add detailed potential bugs investigation report
- Add comprehensive code quality analysis for HouseKeeping_1.1
- Add handoff summary section - refactoring complete and ready for merge
- Update verification doc with post-deployment fixes summary
- CRITICAL FIX v5: Remove OLD_BACKUP files from repository
- CRITICAL FIX v4: Correct dependency overrides in main.py
- CRITICAL FIX v3: Change empty path endpoints from "" to "/"
- CRITICAL FIX v2: Remove prefix parameter entirely from sub-routers
- Add router include verification to API signature document
- CRITICAL FIX: Add explicit empty prefix to all sub-routers
- Add deployment instructions for HouseKeeping_1.0 production testing
- HOUSEKEEPING: Refactoring Complete - 7 Major Files Under 500 Lines
- STEP 7: Refactor positions_router.py (804 → 6 modules)
- STEP 6: Refactor bots.py router (760 → 5 modules)
- STEP 5: Add extraction plan for multi_bot_monitor.py
- Add session summary (4/13 files complete)
- Update progress: STEP 4 complete (coinbase_unified_client.py)
- STEP 4.5: Refactor coinbase_unified_client.py into wrapper (~260 lines)
- STEP 4.4: Extract coinbase_api/order_api.py (~300 lines)
- STEP 4.3: Extract coinbase_api/market_data_api.py (~150 lines)
- STEP 4.2: Extract coinbase_api/account_balance_api.py (~300 lines)
- Add STEP 4 detailed status tracking
- STEP 4.1: Extract coinbase_api/auth.py (~220 lines)
- Update progress: STEP 3 complete (trading_engine_v2.py)
- Add detailed completion plan for STEPs 4-13
- STEP 3.6: Refactor trading_engine_v2.py into wrapper class (~180 lines)
- STEP 3.5: Extract signal_processor.py from trading_engine_v2.py (~325 lines)
- STEP 3.4: Extract sell_executor.py from trading_engine_v2.py (~235 lines)
- STEP 3.3: Extract buy_executor.py from trading_engine_v2.py (~330 lines)
- Add comprehensive housekeeping progress tracker
- Document STEP 3 completion plan for trading_engine_v2.py refactoring
- STEP 3.2: Extract order_logger.py from trading_engine_v2.py (119 lines)
- STEP 3.1: Extract position_manager.py from trading_engine_v2.py (99 lines)
- STEP 2.FINAL: Refactor main.py - split into 5 routers (1658 → 133 lines)
- STEP 2.5: Extract system_router.py from main.py (207 lines)
- STEP 2.4: Extract settings_router.py from main.py (159 lines)
- STEP 2.3: Extract market_data_router.py from main.py (196 lines)
- STEP 2.2: Extract account_router.py from main.py (371 lines)
- STEP 2.1: Extract positions_router.py from main.py (769 lines)
- STEP 1.9: Rename original ai_autonomous.py to _OLD_BACKUP.py
- STEP 1.8b: Create main __init__.py to wire all extracted modules together
- STEP 1.8a: Extract strategy_definition.py (230 lines) from ai_autonomous.py
- STEP 1.7: Extract trading_decisions.py module (buy/sell/DCA logic)
- STEP 1.6: Extract market_analysis.py module (market context, web search, caching)
- STEP 1.5: Extract Grok API provider module
- STEP 1.4: Extract Gemini API provider module
- STEP 1.3: Extract Claude API provider module
- STEP 1.2: Extract prompts.py module with all prompt templates
- STEP 1.1: Create ai_autonomous/ directory structure
- Add detailed refactoring plan with 13 steps and risk assessment
- Add HOUSEKEEPING.md documentation for refactoring work
- Fix Portfolio BTC Balance Breakdown calculation
- Add trade statistics columns to Bots table
- Phase 3.1: Add overall PnL to Holdings table
- Phase 2.3 (Part 2): Complete bot limit order close execution logic
- Phase 2.3 (Part 1): Add bot limit order close configuration
- Add AI bot API credit indicators
- Add market close slippage warnings
- Fix: Move Pydantic model definitions before endpoint usage
- Add budget utilization percentage to bot cards
- Add deployment notes for v1.5.0 database migration

## [v0.75.0] - 2025-11-23

- Add limit order monitoring background service
- Add limit order status display and edit/cancel UI
- Add limit close modal UI with bid/ask slider
- Add limit order position closing - backend implementation
- Fix Portfolio BTC Balance Breakdown calculations

## [v0.74.3] - 2025-11-22

- Add cryptocurrency icons to Positions page

## [v0.74.2] - 2025-11-22

- Add sub-badges to Closed and Failed tabs in History page
- Rewrite badge logic to use simple count delta
- Add 1ms to most recent timestamp to properly clear badge
- Fix badge clear to use most recent position timestamp
- Add debug logging for badge count calculation
- Fix History tab badge timer infinite loop

## [v0.74.1] - 2025-11-22

- Suppress React Router v7 future flag warnings
- Add 2% minimum drop requirement for DCA safety orders
- updated to ignore yet another naming convention for db backups :-/

## [v0.74.0] - 2025-11-22

- Add USD value display next to BTC volume in Positions page

## [v0.73.0] - 2025-11-22

- Fix closed positions main table timestamps to use local timezone
- Convert History page timestamps to local timezone

## [v0.72.0] - 2025-11-22

- Add URL-based routing with React Router
- Add BTC/USD price display to header with 2-minute updates
- Show AI reasoning from most recent buy decision onwards
- Add position_id filter to AI bot logs API endpoint
- Link AI decision logs to positions after position creation

## [v0.71.0] - 2025-11-22

- Fix session corruption in batch AI decision logging by expunging failed positions instead of rollback
- Fix duplicate timestamp error in P&L chart by deduplicating data points
- Fix SQLAlchemy async session corruption in AI decision logging
- Fix budget calculation bug preventing bots from scanning for new opportunities
- Fix aggregate BTC calculation to include positions from database

## [v0.70.0] - 2025-11-22

- Use portfolio breakdown for aggregate BTC calculation to include all positions (even those in open trades)
- Fix aggregate BTC calculation by forcing fresh account data + document BTC bot budget rules in CLAUDE.md
- Make aggregate BTC calculation logs visible by changing to logger.warning()
- Add CRITICAL budget calculation documentation to CLAUDE.md
- Fix budget calculation logging visibility - change INFO to WARNING level
- Add Force Run feature for bots
- Use bot's actual budget_percentage in logs instead of hardcoded 90%
- Fix budget calculation: aggregate should be total account BTC value, not just available balance
- Fix double-subtraction bug in budget calculation - available balance already excludes positions
- Remove caching from get_btc_balance() to always fetch fresh balance
- Add Python bytecode cache clearing to bot.sh start/restart commands
- Simplify calculate_aggregate_btc_value to return actual BTC balance
- Fix aggregate BTC calculation to include BTC + BTC pairs only
- Simplify aggregate BTC calculation to use actual BTC balance
- Temporarily disable aggregate BTC cache to debug balance calculation
- Add debug logging to aggregate BTC value calculation
- Fix Coinbase API rate limiting (429 errors) with caching and retries
- Add fallback to get_accounts() when portfolio endpoint returns 403
- Fix budget calculation and config refresh bugs
- Add fallback to get_accounts() when portfolio endpoint returns 403
- Add debugging for History page badge auto-clear timer
- Create backend/scripts folder for one-off helper scripts
- Add auto-clearing timer to History page notification badge
- Trigger immediate re-analysis after position closes
- Fix order fill race condition with retry mechanism
- Fix double budget division bug in trading engine
- Fix critical database session bug preventing batch trades
- Fix double budget division causing orders below Coinbase minimum
- Add debug prints to _get_confidence_threshold_for_action to diagnose threshold issue
- Add debug prints for Grok batch analysis
- Add debug prints to see signal_data in should_buy()
- Add debug prints for budget calculation and should_buy logic
- Add debug prints for result processing loop to find exact hang point
- Add detailed debug prints in process_bot and process_bot_batch to find hang location
- Add debug prints in bot processing loop to find where it hangs
- Add comprehensive debug prints throughout monitor loop
- Use print() instead of logger for debugging - logger not showing in journalctl
- Add debug logging to diagnose why monitor loop isn't running
- Handle 403 rate limit errors gracefully with budget fallback
- Remove debug prints - monitor loop now working correctly
- Add debug prints throughout monitor loop
- Add more debug prints in monitor_loop
- Add debug prints to diagnose monitor loop not starting
- Fix multi-bot monitor not starting - AI bots now trade
- Remove unused bot-level AI Analysis Interval field
- Allow AI Analysis Interval range of 1-1440 minutes instead of 5-120
- Add database backups and temporary test scripts to .gitignore
- Fix execute_buy() to use actual filled amounts from Coinbase
- Reduce sell amount to 99% to handle discrepancy between tracked and actual balances
- Adjust bar chart margins to prevent top-squishing
- Restructure layout to match 3Commas time filter and chart tabs
- Make chart height match sidebar cards height
- Fix chart disposal error when navigating away from Bots page
- Add 'Most profitable bot' card and active trades count
- Improve bar chart tooltips to match 3Commas style
- Restructure P&L chart with sidebar stats like 3Commas
- Fix Summary PnL chart not displaying after switching tabs
- Add daily P&L bar chart for 'PnL by day' tab
- Replace P&L by pair table with bar chart
- Fix P&L endpoint route order - move before {position_id} route
- Add 3Commas-style P&L chart with comprehensive analytics
- Add professional loading spinners to improve UX
- Fix budget allocation to use max_concurrent_deals instead of pair count
- Fix force-close position to use profit_quote instead of profit_btc
- Add automatic deployment system
- Test backend auto-restart
- Test auto-deployment system
- Add deployment script for pulling from git on EC2
- Add percentage gains to Portfolio Totals on Bots page
- Add budget-aware bot monitoring and insufficient funds indicator
- Add red badge to History tab showing new closed positions
- Make site mobile-friendly with responsive layouts
- Add projected PnL display to Bots page
- Update risk tolerance confidence thresholds
- Fix React controlled input warnings in Bots.tsx
- Fix bot stats 500 error and frontend format crash
- Add OpenAI library and document AI strategy dependencies
- Upgrade Anthropic SDK to 0.74.0 to fix AsyncClient initialization error
- Add adaptive AI evaluation intervals and risk-based confidence thresholds
- Pass position and action context to strategy for intelligent web search
- Add DCA arrows to position chart and synthetic candles for entry timing
- Fix bot-macos.sh to only kill server processes, not browser connections
- Create unified AI prompt templates and add bot PnL tracking
- Give AI full control over sell decisions for autonomous bots
- Fix trade type labels: show 'Take Profit' for sell orders instead of 'DCA'
- Add macOS-compatible bot manager script
- Extend AI log time window to include 30s after position close
- Add backfill script to link existing AI logs to positions
- Add expandable closed positions with trade details, duration, and AI reasoning history
- Add failed order tracking and fix portfolio accuracy
- Add batch price endpoint and optimize frontend price fetching
- Add 10 second timeout to Vite API proxy
- Revert to simple f-string formatting that worked for base orders
- Fix API connection by using Vite proxy instead of direct backend URL
- Configure backend to use port 8100, frontend stays on 5173
- Revert frontend to use backend on port 8000
- Update frontend to use backend port 8100
- Fix Coinbase precision - use fixed-width decimal formatting
- Fix limit_price precision and remove hardcoded dev paths
- Consolidate Coinbase API clients into unified implementation
- Apply precision formatting to legacy CoinbaseClient as well
- Fix PREVIEW_INVALID_QUOTE_SIZE_PRECISION error by applying proper precision formatting
- Add retry logic and error tracking for market data failures
- Fix DCA order precision to avoid Coinbase PREVIEW_INVALID_QUOTE_SIZE_PRECISION error
- Fix DCA order size calculation to use position's initial balance
- Update bot.sh to use systemctl for service management
- Fix sell order execution by properly handling Coinbase API response
- Add minimum order size validation warnings to bot creation modal
- Fix import error - use CoinbaseClient directly
- Add minimum order size validation
- Add detailed branch workflow and cleanup instructions
- Add comprehensive development roadmap
- Consolidate documentation into /docs folder
- Fix Coinbase quote size precision error
- Fix TypeScript linting errors
- Improve Coinbase error message extraction
- Add notes and error fields to PositionResponse schema
- Add position notes feature (like 3Commas)
- Add position error tracking and display (like 3Commas)
- Add detailed Coinbase error logging for failed orders
- Fix DCA not triggering due to missing current_price in batch mode
- Fix duplicate AI log entries for batch analysis
- Add comprehensive debug logging to track duplicate AI opinion source
- Fix REAL cause of duplicate AI opinions - double monitor loop start
- Document duplicate AI opinions race condition fix in HANDOFF.md
- Fix duplicate AI opinions race condition
- Extract API_BASE_URL to centralized config
- Add 3Commas-style manual vs automatic DCA tracking
- Document DCA greenlet fix and API rate limit optimization
- Fix greenlet error preventing DCA order evaluation
- Add close position confirmation modal with proper warnings
- Document pending frontend work and known issues in HANDOFF
- Wire up position action buttons with proper handlers
- Improve bot monitoring responsiveness and database stability
- Sell 99.99% to prevent precision/rounding rejections
- Fix critical bug: Require order_id for buy/sell trades
- Integrate order monitor into MultiBotMonitor
- Fix duplicate AI log entries for batch analysis
- Add AI sentiment indicators and DCA visualization, fix bugs
- Add ESC key handler to close bot config modal
- Only show 'All' buttons for markets with available pairs
- Hide unavailable markets instead of graying them out
- Implement 3Commas-style single-market constraint for pair selection
- Reorganize bot configuration form into numbered sections
- Add 3Commas-style pair selection and interval configuration
- Fix Dashboard BotCard profit display error
- Add comprehensive PnL stats broken down by USD/BTC
- Refactor charts: separate oscillator panes with synchronized time scales
- Improve chart indicators: add priceScaleId and MACD/RSI enhancements
- Fix duplicate Entry/Target labels when changing chart type
- Fix price axis disappearing when switching to Heikin-Ashi
- Re-add indicator rendering functionality
- Fix chart: remove stop loss line and use actual profit target from config
- Use actual profit target from bot config instead of hardcoded 2%
- Remove stop loss reference line from chart (not used in strategy)
- Implement full indicator rendering system for TradingView charts
- Fix chart not displaying: use correct 'time' field from API
- Fix chart NaN error by filtering invalid candle data
- Adjust sell confidence threshold to 65%
- Lower AI sell confidence threshold to 50%
- Raise AI confidence threshold to 80% for all trades
- Fix AI ambivalence by adding temperature=0 to all AI calls
- Add order monitoring service for limit orders
- Add limit order support to trading engine
- Add pending_orders_count to API and frontend (Part 3 - Final)
- Add safety_order_type configuration parameter (Part 2)
- Add pending_orders system for limit order tracking (Part 1)
- Fix averaging orders (Avg. O) display to match 3Commas logic
- Add lightweight chart modal option with full programmatic control
- Add position reference prices to chart modal header
- Prevent background page scroll when chart modal is open
- Fix TradingView widget cleanup error on modal close
- Fix TradingView widget initialization error
- Add TradingView chart integration to Active Deals page
- Feature: Add clickable sorting to table column headers
- UX: Add 3Commas-style overall stats panel and simplified filters
- UX: Add 3Commas-style column headers to deals table
- Fix: Display base currency correctly in Volume column
- UX: Remove redundant coin amount from Filled percentage line
- UX: Add smart collision detection for price bar labels
- UX: Redesign price bar to match 3Commas with vertical tick marks
- Fix: Close unclosed Active Deals Section div and fix ternary operator
- Fix: Remove duplicate JSX code causing TypeScript compilation errors
- Major UX: Transform deal cards to 3Commas-style horizontal layout
- Feature: Add 3Commas-style tick marks with labels on Price Movement bar
- Feature: Add 3Commas-style dynamic labels to Price Movement bar
- Fix: Dynamic range for Price Movement bar visualization
- Fix: Use get_current_price() for ticker endpoint
- Fix: Align chart P&L calculation with main position P&L display
- Fix: Resolve greenlet async error (xd2s) in AIBotLog database operations
- Fix: Resolve AIBotLog SQLAlchemy error (7s2a) by fixing context field duplication
- Lint: Fix final architectural errors (E402, F401)
- Lint: Fix all remaining linting errors (E712, F841, F821, E722)
- Lint: Apply Python best practices and fix linting errors
- Fix: Move formatPrice utility to top level to fix DealChart scope error
- Refactor: Migrate to StrategyTradingEngine and remove old TradingEngine
- cleanup: Remove unused price_monitor.py file
- Refactor: Extract middleware to separate module
- docs: Update HANDOFF.md with Step 2 (schema extraction) completion
- Refactor: Extract Pydantic schemas to centralized schemas module
- docs: Update HANDOFF.md with Phase 1 modularization progress
- Refactor: Extract shared indicator utilities to eliminate code duplication
- Restore full Positions.tsx with all features lost in merge
- Restore Gain/Loss metadata line to position charts
- Housekeeping: Clean up old files and improve gitignore
- Fix: Replace totalProfitBTC with totalProfitQuote in Dashboard
- Fix: Update Positions.tsx field names for multi-currency support
- Fix: Re-apply timezone-aware date formatting to Positions page after merge
- Complete bot balance isolation system and fix portfolio/timezone issues
- Add modular multi-quote currency support (BTC + USD) - Phase 1
- Move closed positions to separate History page
- Update price indicator label from 'Entry' to 'Avg Entry'
- Add visual price movement indicator to position cards
- Fix Current Profit showing 0% in compact position view
- Fix USD currency display in positions/deals
- Fix frontend display of USD prices in AI Bot Logs
- Fix USD price display formatting in AI logs
- Fix Grok model name and implement Claude batch analysis
- Use candle data for current price instead of unreliable ticker API
- Fix AI bot logging to only process pairs with valid market data
- Fix AI Bot price data collection for batch analysis
- Enhance DealChart with full Charts page functionality
- Add bot name display to position details
- Fix hardcoded currency symbols in position details
- Fix crypto price precision for AI analysis
- Fix KeyError when candles are empty
- Add Grok support + optimize batch analysis for position quota
- Add Grok AI support with batch analysis
- WIP: Add batch AI analysis for multi-pair bots
- Add per-bot check_interval with AI provider-specific defaults
- Add position-specific AI logs modal
- Fix API quota issues - increase monitor interval to 10min and fix middleware
- Fix price display in AI logs and add product_id to positions
- Fix critical trade execution bug - trades now execute successfully
- Add transaction rollback: positions only persist if trade succeeds
- Update handoff: Monitor likely not starting - key hypothesis identified
- Add comprehensive handoff document for trade execution bug investigation
- Add debug logging to trace trade execution failure
- Fix critical database transaction conflicts preventing trades
- Add product_id to AI bot logs API response
- Add profit calculation method option (cost_basis vs base_order)
- Fix product_id bug and implement parallel batch processing
- Fix division by zero error in AI autonomous strategy
- Fix AI logs to show AI's actual recommendation, not bot's action
- Change hold icon from Minus to CircleDot for better clarity
- Add trading pair to AI logs + UI improvements
- Fix AI autonomous bot analysis and reasoning logs
- Implement smart budget division by max concurrent deals
- Add max concurrent deals and AI provider display
- Update checklist: Mark AI features and 3Commas UI as complete
- Add AI provider API key fields to Settings config
- Add AI provider selection, dynamic trading pairs, and 3Commas-style UI
- Final session update: Mark all completed features in checklist
- Add AI bot reasoning logs and custom instructions
- Update checklist: mark clone bots and AI log infrastructure as complete
- Add Clone Bots and AI Reasoning Log features
- Fix: Stopped bots now continue managing existing positions
- Update checklist: mark trailing TP/SL as complete
- Add proper trailing take profit and trailing stop loss
- Add .claude/ and .pids/ to gitignore
- Update README with AI bot and all new features
- Add comprehensive handoff document for laptop migration
- Add AI Autonomous Trading Bot powered by Claude AI
- Update checklist: mark bot templates as complete
- Add bot templates system with default presets
- Update checklist: mark multi-pair bots and budget splitting as complete
- Add budget splitting option for multi-pair bots
- Add multi-pair bot UI - frontend implementation
- WIP: Multi-pair bots backend implementation
- Update checklist with recent completed features
- Fix bot Edit button not working on Dashboard
- Add real-time price updates to Deals page
- Add safety order price level visualization to deal charts
- Add Take Profit and Stop Loss lines to deal charts
- Update settings
- Add multi-pair bots to roadmap as critical 3Commas feature
- Update checklist with dashboard overhaul completion
- Overhaul Dashboard with 3Commas-style metrics and recent deals
- Add product_id tracking to positions for accurate chart display
- Implement 3Commas-style DCA bot platform with full deal management
- Add crossing above/below operators to all applicable indicators
- Refactor to true 3Commas-style phase-based conditions
- Add comprehensive user guide for conditional strategy builder
- Implement 3Commas-style conditional DCA strategy system
- Add Heikin-Ashi candle option to Charts page
- Implement advanced charting with TradingView-style indicators
- Fix chart error handling and port management
- Fix lightweight-charts v5 API - use correct method names
- Add comprehensive documentation
- Fix lightweight-charts v5 API compatibility
- Initial commit: ETH/BTC trading bot with TradingView-style charts
