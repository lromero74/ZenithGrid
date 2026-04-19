# PRP: AI Analyst Upgrade — From Calculator to Agent

**Version:** 1.0
**Feature Branch:** `feature/ai-analyst-upgrade`
**Confidence Score:** 8/10

---

## Overview

Today the AI indicator (`AISpotOpinionEvaluator`) is effectively a fancy calculator: it takes 7 pre-computed technical metrics, calls an LLM once, and returns buy/sell/hold + confidence. With `temperature=0` and such a narrow input, most of what it outputs is replicable by carefully-tuned grouped conditions — so the AI isn't really earning its cost.

This PRP reshapes it into a real **agentic analyst** that fetches its own context through tools and reasons over information the rule-based condition engine structurally cannot express.

Five upgrades, ranked by leverage:

1. **Tool use** — switch from one-shot `messages.create` to Anthropic tool-calling loop
2. **Position + portfolio context** — let the AI see entry price, time held, unrealized PnL, other open positions, and account exposure
3. **Regime / cross-asset context** — BTC trend, dominance, correlated asset state
4. **Prior-signal memory** — recent AI signals on this pair and how they turned out
5. **Raw candle window** — last N candles as compact JSON, so it can see patterns summary stats flatten

**Phase 1 (this PRP's scope)**: ship #1 and #2. Tool-calling plumbing + two real tools. This is the smallest surface area that moves the AI from "replicable by rules" to "genuinely doing something rules can't."

**Phase 2 (future)**: #3, #4, #5. Adding more tools is additive — the Phase 1 registry and loop are reused. Sketched at the bottom of this doc for continuity.

---

## Architectural Shape

### Today

```
indicator_based._calculate_ai_indicators(...)
  → AISpotOpinionEvaluator.evaluate(candles, current_price, product_id, db, user_id, params, is_sell_check)
    → _calculate_metrics(candles)                   # 7 numbers
    → _check_buy_prefilter(metrics, params)         # rejects early
    → _call_llm(db, user_id, product_id, metrics, ai_model, is_sell_check)
      → single messages.create with big string prompt
      → parse JSON response
    → return {signal, confidence, reasoning, prefilter_passed, metrics}
```

### After Phase 1

```
indicator_based._calculate_ai_indicators(...)
  → AISpotOpinionEvaluator.evaluate(
        candles, current_price, product_id, db, user_id,
        bot, position, account_id,         # NEW
        params, is_sell_check)
    → _calculate_metrics(candles)                   # unchanged
    → _check_buy_prefilter(metrics, params)         # unchanged
    → _call_llm_with_tools(…) if ai_model == "claude"  # NEW
        ├─ initial messages.create with tools=[…]
        ├─ loop: while stop_reason == "tool_use":
        │    execute each tool_use block via ToolRegistry
        │    append tool_result, call messages.create again
        └─ parse final JSON (same shape as today)
      else _call_llm(…)                              # fallback for GPT/Gemini
    → return {signal, confidence, reasoning, tool_calls, …}
```

The tool registry lives in `backend/app/indicators/ai_tools/`. Each tool is a small async module that takes a `ToolContext` (db session, user_id, product_id, bot, position, account_id, current_price) and returns a JSON-serializable dict. The registry exposes:

- `REGISTRY: Dict[str, Tool]` — name → callable + schema
- `get_schemas_for(names: list[str]) -> list[dict]` — Anthropic-format `tools=` list
- `execute(name, input, ctx) -> dict`

Keeping tools as tiny independent modules (not methods on the evaluator) makes Phase 2 additive — each new tool is a file, not an edit to a 500-line god class.

### Why tool use, not just "more context in the prompt"

We *could* dump position and portfolio state into the prompt directly. That works for #2 but not for #3–5: news and candle windows are large, and we don't want to pay to send them on every call when most calls don't need them. Tool use lets the model decide what to pull. Today the model uses zero tools most ticks; on interesting ticks it pulls 1–2. That's the scaling property we want as we add more tools in Phase 2.

---

## Research Findings

### Existing call path

`backend/app/trading_engine/signal_processor.py:1245`

```python
signal_data = await strategy.analyze_signal(
    candles, current_price, position=position, action_context=action_context,
    db=db, user_id=bot.user_id
)
```

`backend/app/strategies/indicator_based.py:696`

```python
await self._calculate_ai_indicators(
    needs, current_indicators, candles, current_price, position, **kwargs
)
```

Inside `_calculate_ai_indicators` (line 309), `kwargs` already carries `db`, `user_id`, `product_id`. We need to also pipe through `bot` (for account/strategy context) and `account_id` (for portfolio queries). `signal_processor` has `bot` in scope at the analyze_signal call site, so this is a one-line add.

### Position data available to tools

`backend/app/models/trading.py:411` — `Position` is rich:

- Entry: `average_buy_price`, `entry_price`, `opened_at`, `total_quote_spent`, `total_base_acquired`
- Highs/lows since entry: `highest_price_since_entry`, `highest_price_since_tp`
- Trailing state: `trailing_tp_active`, `trailing_stop_loss_active`, `trailing_stop_loss_price`
- Bull-flag fields: `entry_stop_loss`, `entry_take_profit_target`, `pattern_data`
- Snapshot: `strategy_config_snapshot` (frozen at open)

DCA count is derivable from `Trade` (`backend/app/models/trading.py:560`) by filtering `position_id == pos.id AND trade_type == "dca"`.

### Portfolio data available

`Account` at line 23 carries user ownership, exchange, rebalance targets. Open positions on the same account: `SELECT Position WHERE account_id = :aid AND status = 'open'`. The quote currency for grouping comes from `app.currency_utils.get_quote_currency(product_id)` (line 28) — already exists.

### Anthropic tool use — key shape (minimal)

```python
tools = [{
    "name": "get_position_context",
    "description": "Return entry, time held, unrealized PnL, DCA count for the current position.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}]

resp = await client.messages.create(model="claude-sonnet-4-20250514", max_tokens=2048,
                                    tools=tools, messages=messages)

while resp.stop_reason == "tool_use":
    # Append assistant's tool_use blocks, execute tools, append user tool_result blocks.
    tool_results = []
    for block in resp.content:
        if block.type == "tool_use":
            out = await REGISTRY.execute(block.name, block.input, ctx)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id,
                                 "content": json.dumps(out)})
    messages += [{"role": "assistant", "content": resp.content},
                 {"role": "user", "content": tool_results}]
    resp = await client.messages.create(model=..., max_tokens=2048, tools=tools, messages=messages)

# Final text block contains the JSON we parse today.
```

Cap the loop at `MAX_TOOL_TURNS = 4` to bound cost and latency. On cap-reached, force a final response without tools.

### Failure modes to handle

- Tool call raises → return `{"error": "…"}` as tool_result; model continues.
- Model emits malformed JSON on final response → fall back to `hold`/0/"LLM parse error" as today (`_call_llm` line 311).
- Tool loop exceeds cap → drop `tools=` on the next call to force a conclusion.
- User has no Claude API key → current `ValueError` still raised; strategy returns hold (existing behavior at `indicator_based.py:359` unchanged).

### Cost and latency

- One-shot today: ~1 LLM call, ~1–2s.
- Tool use with 1 tool: ~2 calls, ~2–5s.
- Tool use with 2 tools (one turn each): ~3 calls, ~3–8s.
- Existing candle-close time gate (`_should_check_now`, line 87) still caps call frequency to one per candle — so worst case is one tool-use session per 15m per product. Acceptable.

### Existing test scaffold

`backend/tests/indicators/test_ai_spot_opinion.py` uses `importlib.util.spec_from_file_location` to bypass `app.indicators.__init__.py` circular imports. New tests for `ai_tools/` should follow the same pattern or get their own lightweight conftest.

---

## TDD Requirement

Write failing tests FIRST for every new tool and for the tool-use loop. Follow red → green → refactor. No feature code ships without a corresponding failing test.

---

## Implementation Tasks (Phase 1 — in order)

### Task 1: Create `ai_tools/` package skeleton

**Files** (all new):

- `backend/app/indicators/ai_tools/__init__.py` — exposes `REGISTRY`, `ToolContext`, `get_schemas_for`, `execute`.
- `backend/app/indicators/ai_tools/base.py` — `ToolContext` dataclass, `Tool` protocol, registry helpers.

```python
# base.py
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ToolContext:
    db: AsyncSession
    user_id: int
    product_id: str
    current_price: float
    bot: Optional[Any] = None
    position: Optional[Any] = None
    account_id: Optional[int] = None
    is_sell_check: bool = False


class Tool(Protocol):
    name: str
    description: str
    input_schema: Dict[str, Any]

    async def __call__(self, input: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]: ...


REGISTRY: Dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    if tool.name in REGISTRY:
        raise ValueError(f"Duplicate tool: {tool.name}")
    REGISTRY[tool.name] = tool
    return tool


def get_schemas_for(names: List[str]) -> List[Dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for n in names
        if (t := REGISTRY.get(n)) is not None
    ]


async def execute(name: str, input: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    tool = REGISTRY.get(name)
    if not tool:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await tool(input, ctx)
    except Exception as e:  # fail-open: model continues, we log
        return {"error": f"{type(e).__name__}: {e}"}
```

### Task 2: Implement `get_position_context` tool

**File**: `backend/app/indicators/ai_tools/position_context.py` (NEW)

Returns (only meaningful when `ctx.position` is set and `is_sell_check=True`):
- `product_id`
- `entry_price`, `average_buy_price`, `total_quote_spent`, `total_base_acquired`
- `opened_at_iso`, `minutes_held`
- `current_price`, `unrealized_pnl_pct`, `unrealized_pnl_quote`
- `highest_price_since_entry`, `drawdown_from_high_pct`
- `dca_count` — `SELECT COUNT(*) FROM trades WHERE position_id=... AND trade_type='dca'`
- `exit_targets`: `{"stop_loss": position.entry_stop_loss, "take_profit": position.entry_take_profit_target, "trailing_tp_active": ..., "trailing_sl_price": ...}`

When `ctx.position is None`, return `{"note": "No open position — position context is only meaningful during sell checks."}`.

### Task 3: Implement `get_portfolio_context` tool

**File**: `backend/app/indicators/ai_tools/portfolio_context.py` (NEW)

Returns (requires `ctx.account_id`):
- `other_open_positions`: list of `{product_id, quote_currency, unrealized_pnl_pct, minutes_held}` — **excluding** the current position id
- `open_position_count_total`, `open_position_count_same_quote`
- `same_quote_total_exposure` — sum of `total_quote_spent` across positions in same quote currency
- `current_quote_currency` — from `get_quote_currency(ctx.product_id)`
- `concentration_flag` — `"high"` if >3 positions in same base asset family (e.g., 4 ETH-* pairs)

Query pattern:
```python
from app.currency_utils import get_quote_currency
from app.models import Position

stmt = select(Position).where(
    Position.account_id == ctx.account_id,
    Position.status == "open",
    Position.id != (ctx.position.id if ctx.position else -1),
)
open_positions = (await ctx.db.execute(stmt)).scalars().all()
```

Price lookups for PnL% on *other* positions are out of scope for this tool — use `average_buy_price` vs. `position.highest_price_since_entry` as a rough proxy, or simply return `minutes_held` and entry prices and let the model reason about it. **KISS: return entry + time held only for now, not live PnL on other positions.** (Live prices for every other position would require N exchange calls per tool invocation; that's a Phase 2 problem.)

### Task 4: Wire tool-use loop into `AISpotOpinionEvaluator`

**File**: `backend/app/indicators/ai_spot_opinion.py` (MODIFY)

Changes:
1. Import the registry: `from app.indicators.ai_tools import REGISTRY, ToolContext, get_schemas_for, execute`.
2. Import tools so they self-register: `from app.indicators.ai_tools import position_context, portfolio_context  # noqa: F401`.
3. Add `evaluate()` params: `bot=None`, `account_id=None`. Pass through unchanged behavior when not provided.
4. Add `_call_claude_with_tools(ctx, prompt, api_key)` — implements the loop sketched in Research Findings above. `MAX_TOOL_TURNS = 4`.
5. In `_call_llm`, branch: if `ai_model == "claude"` and at least one tool is available, call `_call_claude_with_tools`. Otherwise existing `_call_claude` / `_call_openai` / `_call_gemini`.
6. Tool list selected for this call:
   - Always include `get_portfolio_context`.
   - Include `get_position_context` when `is_sell_check` or `ctx.position is not None`.
7. Prompt addition (inside the existing prompt string): a short `Available tools:` section that briefly describes each enabled tool, so the model knows it can reach for them. Also add a line: *"Call tools only if the information would change your decision. Do not call tools redundantly."*
8. Response shape: add `"tool_calls": [{"name": ..., "input": ..., "output_summary": "..."}]` so the frontend can optionally show what the AI looked at. Truncate output_summary to 200 chars.

### Task 5: Pass `bot` and `account_id` through the call chain

**File**: `backend/app/strategies/indicator_based.py` (MODIFY)

Around line 352 in `_calculate_ai_indicators`:
```python
bot = kwargs.get("bot")
account_id = kwargs.get("account_id")
ai_result = await self.ai_evaluator.evaluate(
    candles=candles,
    current_price=current_price,
    product_id=product_id,
    db=db,
    user_id=user_id,
    bot=bot,
    account_id=account_id,
    params=ai_params,
    is_sell_check=is_sell_check,
)
```

**File**: `backend/app/trading_engine/signal_processor.py` (MODIFY)

Around line 1245, extend the `analyze_signal` kwargs:
```python
signal_data = await strategy.analyze_signal(
    candles, current_price, position=position, action_context=action_context,
    db=db, user_id=bot.user_id,
    bot=bot, account_id=bot.account_id,    # NEW
)
```

### Task 6: Tests (TDD — write FIRST)

**File**: `backend/tests/indicators/ai_tools/__init__.py` (CREATE empty)

**File**: `backend/tests/indicators/ai_tools/test_position_context.py` (NEW)

```python
# Happy path — open long position with 2 DCAs
async def test_returns_entry_time_held_and_dca_count(db_session): ...

# Edge — no position
async def test_no_position_returns_note(db_session): ...

# Edge — recently opened (minutes_held < 1)
async def test_sub_minute_hold_returns_zero_minutes(db_session): ...

# Failure — position with no trades yet
async def test_position_no_dca_returns_zero_count(db_session): ...
```

**File**: `backend/tests/indicators/ai_tools/test_portfolio_context.py` (NEW)

```python
# Happy path — 3 other open positions, 2 same quote currency
async def test_returns_other_open_positions_grouped_by_quote(db_session): ...

# Edge — no other positions
async def test_solo_position_returns_empty_list(db_session): ...

# Edge — excludes current position
async def test_excludes_current_position_from_list(db_session): ...

# Failure — missing account_id returns note
async def test_no_account_id_returns_note(db_session): ...

# Concentration flag
async def test_concentration_flag_high_when_four_same_base(db_session): ...
```

**File**: `backend/tests/indicators/test_ai_spot_opinion_tool_use.py` (NEW)

```python
# Tool loop: model requests one tool, gets result, returns JSON
async def test_single_tool_turn_parses_final_response(): ...

# Tool loop: model requests two tools in one turn, then responds
async def test_multi_tool_single_turn(): ...

# Cap reached: tools dropped, final response forced
async def test_tool_loop_cap_forces_final_response(): ...

# Tool raises: tool_result contains error, model continues
async def test_tool_error_returned_to_model_as_tool_result(): ...

# Non-Claude model: falls back to single-shot _call_llm
async def test_gpt_model_does_not_use_tool_loop(): ...
```

Reuse the `importlib.util.spec_from_file_location` pattern from the existing `test_ai_spot_opinion.py` to dodge the `app.indicators/__init__.py` import chain.

Mock `AsyncAnthropic` and have `messages.create` return a scripted sequence of responses (tool_use → tool_use → text) so the loop is deterministic.

### Task 7: Lint + smoke

- `flake8 --max-line-length=120` on all new files
- `tsc --noEmit` (no frontend changes, so this should be no-op, but confirm)
- Start the backend in dev mode (`./bot.sh restart --dev --back-end`), create a paper bot with an `ai_opinion == "buy"` base-order condition, run on a short timeframe, tail logs for `AI Opinion for` and any tool-call log lines.

---

## Files to Create / Modify (Phase 1)

| File | Action |
|---|---|
| `backend/app/indicators/ai_tools/__init__.py` | CREATE |
| `backend/app/indicators/ai_tools/base.py` | CREATE |
| `backend/app/indicators/ai_tools/position_context.py` | CREATE |
| `backend/app/indicators/ai_tools/portfolio_context.py` | CREATE |
| `backend/app/indicators/ai_spot_opinion.py` | MODIFY — add `_call_claude_with_tools`, extend `evaluate()` sig |
| `backend/app/strategies/indicator_based.py` | MODIFY — pipe `bot`, `account_id` into evaluator |
| `backend/app/trading_engine/signal_processor.py` | MODIFY — pass `bot`, `account_id` to `analyze_signal` |
| `backend/tests/indicators/ai_tools/__init__.py` | CREATE (empty) |
| `backend/tests/indicators/ai_tools/test_position_context.py` | CREATE |
| `backend/tests/indicators/ai_tools/test_portfolio_context.py` | CREATE |
| `backend/tests/indicators/test_ai_spot_opinion_tool_use.py` | CREATE |

No frontend changes in Phase 1. The `tool_calls` field in the response is a silent addition — if the frontend doesn't read it, nothing breaks.

---

## Validation Gates

```bash
cd /home/ec2-user/ZenithGrid/backend

# TDD red state (before implementation)
./venv/bin/python3 -m pytest tests/indicators/ai_tools/ tests/indicators/test_ai_spot_opinion_tool_use.py -v

# After implementation — green
./venv/bin/python3 -m pytest tests/indicators/ -v

# Regression — existing AI test still passes
./venv/bin/python3 -m pytest tests/indicators/test_ai_spot_opinion.py -v

# Regression — indicator_based + signal_processor tests still pass
./venv/bin/python3 -m pytest tests/strategies/ tests/trading_engine/ -v

# Lint
./venv/bin/python3 -m flake8 \
  app/indicators/ai_spot_opinion.py \
  app/indicators/ai_tools/ \
  app/strategies/indicator_based.py \
  app/trading_engine/signal_processor.py \
  --max-line-length=120
```

---

## Phase 2 (Deferred — Sketched for Continuity)

Each item below is a single new file in `ai_tools/` plus its test, plus one-line registration. No changes to the loop or the evaluator.

### #3 — `get_market_regime`

Returns BTC 1h trend (bullish/bearish/neutral based on BTC vs BTC-MA20), BTC dominance if we can pull it from a free source, and the 24h change on BTC so the model can detect "crypto-wide risk-off." Data source: reuse existing `CoinbaseAdapter.get_current_price` for BTC-USD and cached candles. Dominance requires a new feed (e.g., CoinGecko free tier); gate behind a feature flag if we don't want the external dependency yet.

### #4 — `get_recent_news`

Queries the existing `news_articles` table (already present per `backend/app/models/content.py`) for the last 5 articles whose `symbols` or title matches the base currency of `ctx.product_id`. No external fetch — we already store news. Add a small helper that matches "ETH-BTC" → tags containing "ETH" or "ethereum."

### #5 — `get_prior_signals`

Returns the last N `Signal` rows for this product where `signal_type` starts with `ai_`, plus the eventual outcome (win/loss) derived from the parent position. Gives the model a "recent track record" on this pair.

### #6 — `get_candle_window`

Returns the last 50 candles on the AI's configured timeframe as a compact JSON list `[{t, o, h, l, c, v}, …]`. Lets the model see shapes — compression, failed breakouts, wicks — that summary RSI/MACD flatten out. Largest payload, so the model should only call it when the summary metrics are ambiguous.

### #7 — Frontend surfacing (optional)

Add a small "AI reasoning" expand panel on the position card showing the latest `tool_calls[]` so users can see *why* the AI decided what it decided. Trust-building more than decision-driving.

---

## Gotchas

### Circular imports in `app.indicators.__init__.py`

The existing `test_ai_spot_opinion.py` already sidesteps this with `importlib.util.spec_from_file_location`. Don't add `ai_tools` imports to `app/indicators/__init__.py` — import them directly where needed (`ai_spot_opinion.py` imports the registry; tests import tools via direct spec load). That keeps the circular-import surface unchanged.

### `configure_mappers()` + PostgreSQL schema qualification

Per project memory: all `ForeignKey()` strings must be schema-qualified (`"trading.positions.id"` not `"positions.id"`). Tool queries use model attributes directly (`Position.account_id == ...`), so this isn't a new concern — but any raw SQL would need `trading.` / `auth.` prefixes.

### `bot.account_id` nullability

`Bot.account_id` may be nullable in the schema. If it's None at the analyze_signal call site, `get_portfolio_context` should return the "no account context" note rather than query with None. Defensive check in the tool, not in the caller.

### `is_sell_check` semantics

Today `is_sell_check` is derived in `indicator_based.py` line 347 as `position is not None AND (needs["ai_sell"] OR "ai_opinion" in str(take_profit_conditions))`. That same flag gates whether `get_position_context` is registered for the current call. Do not register position tools during buy checks with no position — the model will call them and get a "no position" note, which wastes a turn.

### Tool-use response `content` type mismatch

Anthropic SDK returns `content` as a list of block objects. When appending the assistant message back into `messages` for the next turn, pass the list as-is — do not stringify. The SDK re-serializes correctly.

### Model parameter already hardcoded

`_call_claude` uses `model="claude-sonnet-4-20250514"`. Per memory's Anthropic model policy, we should default to a current Claude 4.x model when building new AI features. For Phase 1, keep the existing model to minimize blast radius; a follow-up can bump it to `claude-sonnet-4-6` or `claude-opus-4-7` once tool-use is stable.

### Time-gate cache and tool calls

Existing `_should_check_now` (line 87) caches per `product_id:timeframe`. Tool use doesn't change this — if we skip the candle, we skip the entire evaluation (tools included). No new cache layer needed.

### Cost on fallback path

GPT and Gemini continue single-shot in Phase 1. If a user configures `ai_model="gpt"` they get no tool use. Document this in the `ai_model` parameter help text so expectations are set. Adding tool use for OpenAI and Gemini is straightforward but different protocols — defer.

---

## PRP Score

**8/10** — Well-bounded. Existing patterns (evaluator class, test scaffolding, pass-through kwargs) are all in place; the main novelty is the tool-use loop itself, which follows Anthropic's documented pattern directly. The biggest unknown is how often Claude will actually choose to invoke tools at `temperature=0` — if it ignores them, we gain nothing. Mitigation: explicit prompt nudges ("Call tools only when the information would change your decision") plus a monitoring hook on `tool_calls[]` in logs to verify real usage after shipping. If adoption is low, a follow-up PRP can move to "always call get_position_context when is_sell_check=True" by pre-invoking the tool and prepending the result to the prompt — effectively a hybrid of tool use and context injection.
