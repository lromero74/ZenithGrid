# PRP: Platform Expansion Roadmap

**Date:** 2026-06-19
**Base branch:** `main` (v3.4.12)
**Feature branch:** `feature/platform-expansion`
**Confidence Score:** 7/10

---

## TL;DR

ZenithGrid has a solid DCA/grid/indicator-based trading engine, multi-account scoping, AI spot opinions, paper trading, and a real-time web UI. What it lacks is the broader platform surface that mature trading-bot systems offer: backtesting, strategy optimization, automation rules, social/sentiment indicators, webhook-driven trading, portfolio rebalancing strategies, market making, multi-exchange coverage, and notification channels.

This PRP defines 14 features grouped into three tiers (quick wins, medium, large) with concrete implementation plans, architecture notes, and dependencies. Each feature is independently shippable.

---

## Current State (What ZenithGrid Already Has)

- **Strategies:** Grid trading (arithmetic/geometric/neutral/long), indicator-based (unified condition builder with RSI, MACD, BB%, BULL_FLAG, VWAP_BOUNCE, QFL, AI_BUY/AI_SELL), spatial arbitrage, statistical arbitrage, triangular arbitrage
- **Indicators:** AI spot opinion (single LLM call), bull flag, VWAP bounce, QFL, speculative signals, risk presets
- **Exchange clients:** Coinbase, Bybit, DEX, paper trading, MT5 bridge
- **AI:** Single-call LLM spot opinions, AI grid optimizer (analyzes grid performance, suggests parameter changes)
- **Services:** Rebalance display, paper valuation, news service, seasonality, debt ceiling monitor, bot monitoring, P&L, portfolio, reports
- **Frontend:** Dashboard, positions, bots, charts, news, portfolio, reports, settings, social, games, chat
- **Infrastructure:** PostgreSQL, Redis, multi-account scoping, account sharing, paper trading

---

## Feature Catalog

### Tier 1: Quick Wins (1-2 days each)

#### 1. TradingView Webhook Receiver

**Goal:** Accept TradingView alert webhooks and translate them into bot actions (buy/sell/exit) via the existing indicator_based condition system.

**Architecture:**
- New router: `POST /api/webhooks/tradingview` — public endpoint authenticated by per-bot webhook secret token
- Webhook payload parser: extracts symbol, side, price, quantity from TradingView JSON alert
- Signal translator: maps incoming alert to the existing `SignalProcessor` buy/sell pipeline
- Per-bot webhook token: stored on `Bot` model (new column `webhook_token`), generated on bot creation, shown in bot settings UI
- Rate limiting: per-token, 10 requests/minute

**Frontend:** Bot settings page gets a "Webhook URL" field showing the full URL with token, plus a "TradingView Alert JSON template" copy button.

**Tests:**
- Valid webhook triggers buy on correct bot
- Invalid token returns 404
- Rate limit enforcement
- Webhook for stopped bot is rejected
- Account scoping: webhook only acts on the bot's account

**Migration:** Add `webhook_token` column to `bots` table.

---

#### 2. Telegram Notifications & Control

**Goal:** Send trade notifications (fills, DCA entries, take-profit, stop-loss, bot started/stopped) via Telegram, and accept basic commands (/status, /positions, /stop <bot>, /start <bot>).

**Architecture:**
- `backend/app/services/telegram_service.py` — bot token stored in user settings (encrypted), chat_id per user
- Event bus subscriber: listens to `trade_filled`, `bot_started`, `bot_stopped` events from existing `event_bus.py`
- Command handler: `POST /api/telegram/webhook` — Telegram webhook endpoint
- Commands: `/status` (summary of all bots), `/positions` (open positions), `/stop <bot_name>`, `/start <bot_name>`, `/pnl` (today's P&L)
- Notification formatting: markdown messages with emoji, inline keyboard for stop/start confirmations

**Frontend:** Settings page gets a "Telegram" section: bot token input, chat ID input, "Test notification" button, toggle which events to notify on.

**Tests:**
- Trade fill triggers Telegram message
- /status command returns correct bot summary
- /stop command stops the named bot
- Invalid bot token rejected
- Account scoping: commands only affect the authenticated user's bots

---

#### 3. Fear & Greed Index Indicator

**Goal:** Add the Fear & Greed Index (alternative.me API) as a tradeable indicator usable in the indicator_based condition builder, e.g., `FEAR_GREED < 25` as a buy condition.

**Architecture:**
- `backend/app/indicators/fear_greed_indicator.py` — fetches from `https://api.alternative.me/fng/`, caches 1 hour
- Returns: `{value: 0-100, classification: "Extreme Fear"|"Fear"|"Neutral"|"Greed"|"Extreme Greed"}`
- Register as aggregate indicator in `indicator_based.py` condition builder
- Cache key: `fear_greed_index` in Redis with 1-hour TTL

**Frontend:** Show Fear & Greed value on Dashboard as a widget. In bot condition builder, add `FEAR_GREED` to the indicator dropdown.

**Tests:**
- Indicator returns correct value from cached API response
- `FEAR_GREED < 25` condition evaluates true when index is 20
- Cache TTL respected (stale data not served)
- API failure returns last known value or "not computable"

---

### Tier 2: Medium Effort (3-7 days each)

#### 4. Backtesting Engine

**Goal:** Replay historical candle data through any strategy class and produce a performance report (P&L, win rate, max drawdown, Sharpe ratio, trade list).

**Architecture:**
- `backend/app/backtesting/` module:
  - `data_collector.py` — fetches historical candles from exchange APIs (Coinbase, Bybit) and stores as parquet/CSV
  - `backtest_runner.py` — instantiates a strategy, feeds candles one-by-one through the existing `evaluate()` method, tracks simulated fills, balances, and P&L
  - `backtest_report.py` — computes metrics: total return, annualized return, win rate, max drawdown, Sharpe, trade count, avg trade duration, profit factor
  - `backtest_models.py` — DB models for `BacktestRun` (id, bot_config_snapshot, start_date, end_date, initial_capital, result_json)
- Router: `POST /api/backtesting/run` — accepts bot config + date range + pair, returns run ID; `GET /api/backtesting/run/{id}` — returns report
- Runs async (background task), status polled via `GET /api/backtesting/run/{id}/status`
- Reuses existing `TradingStrategy` base class — strategies don't need modification, just a different feed source (historical replay instead of live websocket)

**Frontend:** New "Backtesting" page:
- Bot config selector (copy from existing bot or custom)
- Pair + date range picker
- "Run Backtest" button
- Results: equity curve chart, trade markers on price chart, metrics table, trade list table

**Dependencies:** Historical data storage (parquet files or DB table).

**Tests:**
- Grid strategy backtest on 30 days of BTC-USD produces correct trade count
- P&L calculation matches manual calculation on a small dataset
- Insufficient data returns error, not NaN
- Backtest run is account-scoped (can't backtest another user's bot config)

---

#### 5. Automation Trigger/Action System

**Goal:** User-configurable if-then rules: "When BTC price crosses $100k, sell all BTC positions" or "When profitability drops 5% in 1 hour, stop all bots."

**Architecture:**
- `backend/app/automation/` module:
  - `trigger_events/` — pluggable trigger types: `PriceThreshold` (symbol + target price + direction), `ProfitabilityThreshold` (percent change over time window), `VolatilityThreshold` (ATR-based), `HoldingThreshold` (position held > N hours), `PeriodCheck` (every N minutes/hours)
  - `actions/` — pluggable action types: `CancelOpenOrders` (per bot or per account), `SellAllPositions` (market sell everything), `StopTrading` (stop all bots), `StopStrategies` (stop specific strategy), `SendNotification` (Telegram/email), `StartBot` (start a specific bot)
  - `automation_engine.py` — evaluates triggers on each price tick / schedule, fires actions
  - `automation_rules.py` — DB model: `AutomationRule(user_id, account_id, trigger_type, trigger_config, action_type, action_config, enabled, last_fired_at)`
- Router: CRUD for automation rules
- Rules are account-scoped (HARD RULE from AGENTS.md)

**Frontend:** New "Automation" page:
- List of rules with enable/disable toggle
- Rule builder: select trigger type → configure params → select action → configure params
- Rule execution history (last fired, result)

**Tests:**
- Price threshold trigger fires action when price crosses
- Profitability threshold fires after time window
- Rule scoped to account A doesn't fire for account B
- Disabled rule never fires
- Action executes against the correct account

---

#### 6. Crypto Basket / Index Trading Strategy

**Goal:** A bot strategy that maintains a weighted basket of cryptocurrencies and auto-rebalances when allocations drift beyond a threshold.

**Architecture:**
- `backend/app/strategies/basket_trading.py` — new `TradingStrategy` subclass
- Config: basket composition (list of `{symbol, target_weight}`), rebalance threshold (e.g., 5% drift), rebalance interval (min time between rebalances), quote currency
- On each evaluation cycle: compute current weights from balances + prices, compare to target, if any asset drifts > threshold, execute rebalancing trades (sell overweight, buy underweight)
- Reuses existing `rebalance_service.py` allocation computation
- Integrates with existing bot model (strategy_id = "basket_trading")

**Frontend:** In bot creation, "Basket Trading" strategy option with:
- Basket composition editor (add/remove coins, set weights, weights must sum to 100%)
- Rebalance threshold slider
- Current vs target allocation visualization

**Tests:**
- Basket with 3 coins at 33% each, when one pumps 10%, rebalance fires
- Rebalance respects minimum trade sizes
- Weights must sum to 100% (validation)
- Account scoping: basket only includes assets on the bot's account

---

#### 7. Strategy Optimizer / Parameter Sweep

**Goal:** Given a backtest-able strategy, sweep parameter permutations and rank results by fitness metrics to find the best configuration.

**Dependencies:** Backtesting engine (feature 4).

**Architecture:**
- `backend/app/backtesting/strategy_optimizer.py`:
  - Accepts: strategy class, parameter ranges (e.g., `num_grid_levels: [5, 10, 15, 20]`, `geometric_factor: [1.01, 1.02, 1.03]`), date range, fitness metric (Sharpe, total return, max drawdown inverse)
  - Runs backtest for each permutation (parallel where possible via asyncio)
  - Scores and ranks results
  - Returns top N configurations with full metrics
- Router: `POST /api/backtesting/optimize` — async job, poll for results
- DB model: `OptimizationRun` (id, strategy_class, parameter_space_json, status, results_json)

**Frontend:** Backtesting page gets an "Optimize" tab:
- Select strategy + parameters to sweep (ranges, not fixed values)
- Select fitness metric
- Run optimization → results table with sortable columns, "Apply to bot" button for any result

**Tests:**
- 3×3 parameter grid produces 9 backtest results
- Results ranked correctly by selected fitness metric
- Optimization run is account-scoped
- Large parameter space doesn't OOM (batching/limits)

---

### Tier 3: Larger Efforts (1-3 weeks each)

#### 8. Multi-Agent AI Trading Team

**Goal:** Replace the single-call `ai_spot_opinion.py` with an orchestrated team of specialized LLM agents that debate before a trade decision.

**Architecture:**
- `backend/app/ai_team/` module:
  - `signal_agent.py` — analyzes price/volume/order flow, outputs structured signal assessment
  - `bull_research_agent.py` — constructs bullish case from metrics, news, on-chain data
  - `bear_research_agent.py` — constructs bearish case
  - `risk_judge_agent.py` — evaluates bull vs bear arguments, outputs final risk score (0-100) and action recommendation (buy/sell/hold/size)
  - `distribution_agent.py` — given the risk judge output, computes portfolio allocation changes (increase/decrease exposure, add/remove from basket)
  - `team_orchestrator.py` — runs agents in DAG: Signal → (Bull || Bear) → Risk Judge → Distribution
  - `agent_memory.py` — stores agent outputs and market insights for long-term context (DB-backed, per account)
- Each agent uses the existing `ai_service.py` / `get_ai_client()` infrastructure
- Agents output structured JSON with schema validation
- Orchestrator collects all intermediate outputs for audit trail (stored in DB, viewable in UI)

**Frontend:** Bot config with "AI Team" strategy:
- View agent team execution history (which agents fired, what they said, final decision)
- Agent configuration: model selection per agent, prompt customization

**Tests:**
- Signal agent produces valid JSON with required fields
- Risk judge receives outputs from bull and bear agents
- Distribution agent output respects portfolio budget limits
- Agent memory is account-scoped
- Full pipeline completes within timeout (e.g., 60s)

---

#### 9. CCXT Multi-Exchange Support

**Goal:** Add support for 10+ exchanges via the CCXT library, dramatically expanding market access beyond Coinbase + Bybit.

**Architecture:**
- `backend/app/exchange_clients/ccxt_adapter.py` — generic adapter implementing `ExchangeClient` base using CCXT's unified API
- Per-exchange config in `exchange_clients/ccxt_config.py` — maps exchange-specific quirks (pagination, rate limits, symbol formats, websocket endpoints)
- `factory.py` updated to route unknown exchange types through CCXT adapter
- Account model gains `exchange_name` field (if not already present) to select CCXT exchange
- WebSocket feeds via CCXT's watch methods where available; REST polling fallback

**Priority exchanges:** Binance, OKX, Kucoin, MEXC, Kraken, Hyperliquid

**Frontend:** Account creation supports selecting from a dropdown of CCXT exchanges. Exchange-specific credential fields.

**Tests:**
- CCXT adapter fetches balances correctly for mocked exchange
- Order placement works for market + limit orders
- Symbol mapping (CCXT format ↔ internal format) is correct
- Rate limit handling
- Account scoping: CCXT client built with `account_id`

---

#### 10. Market Making Strategy

**Goal:** A bot strategy that provides liquidity by placing simultaneous buy and sell limit orders around a reference price, profiting from the spread.

**Architecture:**
- `backend/app/strategies/market_making.py` — new `TradingStrategy` subclass
- Components:
  - `reference_price.py` — mid-price from order book, optionally weighted by recent trades (VWAP) or external price feed
  - `order_book_distribution.py` — computes optimal order placement based on spread, depth, inventory skew
  - `market_making.py` — places buy/sell orders at `reference ± spread/2`, cancels and replaces when price moves, manages inventory (skew orders when holding too much of one side)
- Config: spread (bps), order size, max inventory, recenter threshold, order refresh interval
- Integrates with existing order validation and position management

**Frontend:** "Market Making" strategy in bot creation with spread/inventory config and a live order book depth visualization.

**Tests:**
- Orders placed symmetrically around reference price
- Orders cancelled and replaced when price moves beyond threshold
- Inventory skew adjusts order sizes correctly
- Budget/balance checks prevent overcommitment
- Account scoping

---

#### 11. Copy Trading / Signal Subscriptions

**Goal:** Allow users to publish their bot performance as a signal and other users to subscribe, automatically mirroring trades.

**Architecture:**
- `backend/app/services/signal_provider_service.py` — publishes trade events from a source bot to a signal channel
- `backend/app/strategies/copy_trading.py` — subscribes to a signal channel, replicates trades on the subscriber's account with configurable sizing (fixed amount, percentage of portfolio, mirror source exactly)
- `backend/app/models/social.py` — `SignalProvider` (user_id, bot_id, public/private, subscriber_count) and `SignalSubscription` (subscriber_user_id, provider_id, sizing_config)
- Router: CRUD for providers and subscriptions, performance stats
- Latency: WebSocket-based signal delivery for near-real-time mirroring

**Frontend:** "Social" page expansion:
- Browse signal providers (public), see performance stats
- Subscribe/unsubscribe
- Copy trading config: sizing method, max positions, allowed pairs

**Tests:**
- Source bot trade triggers subscriber bot trade within 2s
- Sizing config respected (fixed amount vs percentage)
- Subscriber can stop copying at any time
- Private provider not visible to non-subscribers
- Account scoping: copy trades execute on subscriber's account

---

#### 12. DSL Scripting Mode

**Goal:** Let advanced users write custom trading logic in a simple domain-specific language, executed as a bot strategy.

**Architecture:**
- `backend/app/strategies/dsl_trading.py` — parses and executes DSL scripts
- DSL syntax examples:
  ```
  limit('buy', 'BTC-USDT', 0.01, price='-1%')
  if rsi(14) < 30: limit('buy', 'ETH-USDT', 0.05)
  if price('BTC-USDT') > 100000: market('sell', 'BTC-USDT', all)
  ```
- `dsl_interpreter.py` — tokenizes, parses, and evaluates DSL expressions against current market state
- Sandboxed execution: no Python eval, no file access, no network — pure expression evaluation against injected market data
- Config: DSL script text, execution trigger (on candle close, on price tick, scheduled)

**Frontend:** Bot creation gets "Custom Script" strategy with a code editor (Monaco), syntax highlighting, examples library, and a "Dry run" button that backtests the script.

**Tests:**
- Valid DSL script executes correct orders
- Invalid syntax rejected with line/col error
- Sandbox cannot access filesystem or network
- `all` keyword sells entire position
- Account scoping

---

#### 13. Blockchain Wallet Integration

**Goal:** Trade directly from Bitcoin and EVM-compatible wallets (MetaMask, Ledger) without depositing to an exchange first.

**Architecture:**
- `backend/app/exchange_clients/wallet_client.py` — implements `ExchangeClient` using on-chain transactions
- Bitcoin: `bitcoin_blockchain_client.py` — UTXO management, fee estimation, PSBT signing
- EVM: `evm_blockchain_client.py` — wallet balance queries, DEX swap routing (Uniswap/1inch), gas estimation, transaction signing
- Wallet connection: read-only via public key / xpub; signing via hardware wallet or keystore file
- Integrates with existing DEX client for swap execution

**Frontend:** Account creation gets "Wallet" type:
- Connect wallet (public address for read-only, MetaMask/ WalletConnect for signing)
- Display on-chain balances
- Trade via DEX routing with slippage and gas config

**Tests:**
- Wallet balance query returns correct amounts
- DEX swap executes with correct slippage
- Insufficient gas/balance rejected
- Account scoping

---

#### 14. Mobile Companion App

**Goal:** A React Native mobile app for monitoring bots, viewing positions, receiving push notifications, and basic bot control (start/stop).

**Architecture:**
- React Native (Expo) app, shares API types with frontend
- Features: dashboard summary, bot list with start/stop, positions list, P&L charts, push notifications (trade fills, bot alerts), biometric auth
- API: existing REST endpoints + WebSocket for real-time updates
- Push notifications: Firebase Cloud Messaging (Android) + APNs (iOS), triggered by backend event bus

**Tests:**
- Login flow works
- Bot start/stop calls correct endpoints
- Push notification received on trade fill
- Account scoping (can't see other users' bots)

---

## Implementation Order

Recommended sequence (respecting dependencies):

1. **TradingView Webhook** (1) — standalone, immediate value
2. **Telegram Notifications** (2) — standalone, immediate value
3. **Fear & Greed Indicator** (3) — standalone, immediate value
4. **Backtesting Engine** (4) — foundational for optimizer
5. **Crypto Basket Strategy** (6) — standalone, builds on rebalance_service
6. **Automation Triggers/Actions** (5) — standalone
7. **Strategy Optimizer** (7) — depends on backtesting (4)
8. **Multi-Agent AI Team** (8) — standalone, builds on ai_service
9. **CCXT Multi-Exchange** (9) — standalone, large effort
10. **Market Making** (10) — standalone
11. **Copy Trading** (11) — depends on social model + WebSocket
12. **DSL Scripting** (12) — standalone
13. **Blockchain Wallet** (13) — standalone, large effort
14. **Mobile App** (14) — last, depends on stable API surface

---

## Constraints (Cross-Cutting)

- **Account scoping (HARD RULE):** Every feature — backtesting, automation rules, copy trading, AI team memory, optimization runs — must scope by `account_id`, never just `user_id`. Write the multi-account test for each feature.
- **One source of truth:** Financial calculations (backtest P&L, optimization fitness, market making P&L) must reuse existing `pnl_service.py`, `budget_calculator.py`, and `rebalance_service.py` — no inline re-derivations.
- **Symbol registry:** Check `scripts/symbol_registry.py --check <name>` before adding any new function. Regenerate snapshot after additions.
- **TDD:** Write the failing test before the implementation for every feature.
- **CHANGELOG:** Update `CHANGELOG.md` for every shipped feature.
- **No bot auto-start:** Bots created during development must be created stopped.