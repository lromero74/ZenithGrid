# PRP: Multi-Provider AI Tool Use — Parity Across Claude, GPT, and Gemini

**Version:** 1.0
**Parent:** `PRPs/ai-analyst-upgrade.md` (Phase 1 shipped the Claude-only tool loop)
**Feature Branches:** proposed `feature/ai-provider-adapters`, then `feature/ai-argument-tools`, etc.
**Confidence Score:** 7/10 — well-understood capability, but three SDK surfaces to keep in sync

---

## Why This Exists

Phase 1 of `ai-analyst-upgrade` wired a Claude-specific tool-use loop into `AISpotOpinionEvaluator`. The bot editor lets users pick `claude`, `gpt`, or `gemini` as the `ai_model`. Today only Claude users benefit from portfolio + position context; GPT/Gemini users get the old one-shot prompt.

That's a product inconsistency. It also blocks Phase 2 of the original PRP (news, regime, candle window, prior signals) from being universally useful, because the moment a tool takes model-chosen arguments, simple prompt injection stops being equivalent to real tool use.

This PRP plans the full end-state: **every supported AI provider runs through the same tool loop, with the same registry, and the same observable tool-call log.**

---

## End State (the picture we're building toward)

```
AISpotOpinionEvaluator.evaluate(...)
  → build prompt
  → provider = get_provider(ai_model)       # Anthropic | OpenAI | Gemini
  → provider.call_with_tools(prompt, tools=[...], ctx)
      └── loops natively in each provider's tool protocol
           emits normalized ToolCall events → REGISTRY.execute
           returns (text, List[NormalizedToolCall])
  → parse text → {signal, confidence, reasoning, tool_calls}
```

- One abstract `LLMProvider` interface; three concrete implementations.
- Tool registry (`ai_tools/`) unchanged — tools stay provider-agnostic.
- Response shape (including the `tool_calls[]` audit field) identical across providers.
- Rich toolset: portfolio + position (done), plus candles, news, regime, prior signals, similar setups.
- UI surfaces the tool-call log so users can see *what the AI looked at before deciding*.

---

## Phase Plan

Each phase is shippable on its own. Phase order is chosen so that any phase can be the last phase without leaving the product broken.

### Phase A — Unified Context for All Providers *(next ship; ~half day)*

**Problem solved**: GPT/Gemini users currently see no position or portfolio context. The Claude tool loop exists but the other models run a single-shot prompt.

**Strategy**: For the two current tools (`get_portfolio_context`, `get_position_context`), neither takes model-chosen arguments. Pre-compute both on every AI call and inject the JSON into the prompt as a `## Context` block. All three providers see identical data. Claude's tool loop stays wired for argument-taking tools later, but for these two static tools it's skipped (avoids duplicate fetches).

**Changes**:
- New helper `_build_context_block(ctx) -> str` in `ai_spot_opinion.py` — calls the registry tools directly and returns a formatted string.
- Prepend that block to the prompt body in `_build_prompt()`.
- Gate the Claude tool loop to *only* run when there is at least one argument-taking tool in `enabled_tools`. For Phase A there are none → everyone runs single-shot with injected context.
- Routing logic simplifies: no more `use_tools = (ai_model == "claude" and account_id)`. Tool loop activation is keyed on "is there an argument tool?" not provider.

**Tests**:
- Context block includes portfolio + position JSON for all three providers.
- Context block omits position section when `position is None`.
- Context block omits portfolio section when `account_id is None`.
- Existing tool-loop tests still pass (the loop path is reachable via a test-only fake argument tool).

**Risk**: Prompt size grows by a few hundred tokens on every call. Measure: log prompt char count before/after on a sample of live calls. If it pushes cost meaningfully, gate per-tool inclusion on relevance flags (e.g., skip portfolio when bot is solo).

---

### Phase B — Provider Adapter Layer *(~1–2 days)*

**Problem solved**: Prepare the codebase to share tool-use machinery across providers. Without this, each new argument-taking tool would require three parallel implementations of the same loop.

**New module**: `backend/app/indicators/ai_providers/`

```
ai_providers/
  __init__.py          # re-exports get_provider(name)
  base.py              # LLMProvider ABC + NormalizedToolCall dataclass
  anthropic_provider.py
  openai_provider.py
  gemini_provider.py
```

**Interface**:

```python
@dataclass
class NormalizedToolCall:
    name: str
    input: Dict[str, Any]
    output: Dict[str, Any]
    output_summary: str          # truncated to 200 chars for logging
    turn: int                    # 0-indexed turn this call happened on


class LLMProvider(Protocol):
    name: str                    # "claude" | "gpt" | "gemini"
    model: str                   # SDK model string

    async def call_with_tools(
        self,
        system: str,
        user: str,
        tools: List[Dict[str, Any]],    # registry schema (Anthropic-style, canonical)
        tool_ctx: ToolContext,
        max_turns: int = 4,
    ) -> Tuple[str, List[NormalizedToolCall]]:
        """Run the provider's native tool-use loop. Returns (final_text, tool_calls)."""
```

Each implementation:
- Translates the canonical Anthropic-style schema into its own (OpenAI's `{"type": "function", "function": {...}}`, Gemini's `FunctionDeclaration`).
- Drives its own loop until the provider emits a final text response or `max_turns` is hit.
- Produces `NormalizedToolCall` records that the evaluator can log and return uniformly.

**Evaluator changes**:
- `_call_claude_with_tools` deleted; `_call_claude_tools_path` replaced with generic `_call_provider_tools_path(provider_name, ...)`.
- `get_provider(name)` chooses the implementation based on `params.ai_model`.
- Tool-path activation: any enabled tool that accepts arguments OR any time `params.ai_tools_enabled` is true (new param, default true).

**Tests**:
- Unit test each provider with mocked SDK: single-tool turn, multi-tool turn, cap reached, tool error.
- Integration test: registry + provider + real tool execution against in-memory SQLite (no network).
- Contract test: all three providers handed the same prompt + tools produce the same `NormalizedToolCall` shape.

**SDK facts to pin down**:
- OpenAI: `chat.completions.create(tools=[...])` → `choices[0].message.tool_calls[]`. Feed results back as role=`tool` messages referencing `tool_call_id`. Loop terminates when `finish_reason="stop"`.
- Gemini: `generate_content(tools=[...])` → `candidates[0].content.parts` contains either `text` or `function_call`. Respond with a `function_response` part. Loop terminates when only `text` parts come back. (Note: Gemini's function calling currently requires a slightly different schema format — we convert on the way in.)

---

### Phase C — First Argument-Taking Tools *(~1 day, builds on B)*

**Why now**: This is where tool use actually pays off. Without argument-taking tools, Phase A's context injection is equivalent to tool use at lower cost.

**Tools** (each = one file in `ai_tools/` + one test file):

1. **`get_candle_window(timeframe, count)`** — returns compact OHLCV list. `timeframe` ∈ {"5m","15m","1h","4h","1d"}, `count` 10–100. Lets the model zoom in/out without us sending a 4kB block every call.

2. **`get_recent_news(max_age_hours, limit)`** — queries `news_articles` table (already populated). Filters by base-asset tag derived from `ctx.product_id`. Arguments let the model ask for "news in the last 2 hours" vs "last 24 hours" based on urgency.

3. **`get_similar_past_setups(rsi_min, rsi_max, min_volume_ratio, lookback_days)`** — queries historical `Signal` rows that matched the given metric range and returns the outcome distribution. Gives the model empirical base rates: "of 50 past setups with RSI 35–45 and 1.5x volume, 68% were net positive over 4h."

**Prompt nudge**: each tool gets a line in the system prompt explaining when to use it. Example: *"Call `get_recent_news` when RSI and volume look tradeable but you want to rule out a recent catalyst. Prefer 6h max_age for intraday setups."*

**Cost guard**: hard-cap total tool output size per call (e.g., 8kB). Each tool declares a `max_output_bytes` and the registry truncates with a `"[truncated]"` marker so the model knows.

**Tests**:
- Happy path for each tool + at least one failure path (bad args, empty DB, etc.).
- Integration with each provider from Phase B — confirm OpenAI and Gemini actually call the tools and respect arg constraints.

---

### Phase D — Memory / Outcome-Aware Tools *(~1 day)*

Once Phase C exists, we can add tools that aren't just "read current state" but "look at recent history and what happened after":

4. **`get_prior_ai_signals(product_id, days)`** — the last N AI decisions on this pair, with the outcome column derived from the parent position's closed PnL. Gives the model real feedback on its own past calls.

5. **`get_trade_history(product_id, n)`** — recent closed positions for this product (any bot, same user) with entry/exit, hold time, and realized PnL%. Complements #4 by showing rule-based trades too.

**Data backfill**: `get_prior_ai_signals` depends on `ai_spot_opinion_log` (or wherever we persist signals) actually being written with tool_calls + outcome. Part of this phase is ensuring that table exists and is populated by `ai_spot_opinion.py` on every decision. (Today `tool_calls` is returned in the response but not persisted.)

**Migration**:
- `ai_opinion_log` table if it doesn't exist: id, user_id, account_id, bot_id, position_id (nullable), product_id, is_sell_check, signal, confidence, reasoning, tool_calls (JSONB), created_at, outcome (nullable — backfilled when position closes), realized_pnl_pct (nullable).
- Writer in the evaluator after every successful call.
- Outcome backfill: existing position-close hook looks up any logs for that position_id and updates outcome fields.

---

### Phase E — UI Surface for Tool-Call Transparency *(~half day)*

**Goal**: Show the user what the AI actually looked at. Builds trust, helps debug bad decisions, and is a feature bots built around rules can't offer.

**Changes**:
- New backend endpoint: `GET /api/positions/{id}/ai-log` — returns the last AI decision for this position with its `tool_calls[]`.
- Position card (`frontend/src/pages/Positions.tsx` and `components/positions/...`): small "AI reasoning" expander. Shows:
  - Signal + confidence + reasoning
  - Tools called: name, input args, and a collapsible "what the AI saw" (output_summary expanded to full output on click)
  - Timestamp

**Design intent**: this is audit UI, not dashboard chrome. Default collapsed. Users who don't care never see it.

**Tests**:
- Endpoint returns most recent log, 404 when none.
- Permission: only the position owner can read its AI log.
- Frontend component renders nothing when `tool_calls[]` is empty (single-shot fallback).

---

### Phase F — Per-Provider Model Selection + Cost Dashboard *(~half day; optional)*

At this point users are routing to three different providers, each with their own model string and pricing. Worth giving them:
- A **model override** per bot (not just provider): user can pick `claude-opus-4-7` vs `claude-haiku-4-5` etc. for their speed/cost tradeoff.
- A **cost log**: each AI call writes estimated tokens and USD cost into `ai_opinion_log`. Aggregate view in Settings → AI shows "last 7 days: 1,243 calls, $4.82 across Claude / GPT / Gemini."

Nice to have, not required. Mention here so it's not forgotten.

---

## Cross-Phase Architectural Notes

### Provider schema translation

Keep the **canonical tool schema** in Anthropic's format (it's the most faithful JSON Schema shape). Translate in each provider adapter:

| Provider | Our canonical | Their format |
|---|---|---|
| Anthropic | `{name, description, input_schema}` | identical (pass through) |
| OpenAI | same | `{"type":"function","function":{"name","description","parameters":input_schema}}` |
| Gemini | same | `FunctionDeclaration(name=..., description=..., parameters=input_schema)` |

Translation is pure and testable — keep it in its own function per adapter.

### Loop termination rules (shared across providers)

1. Stop when the provider emits a pure-text response.
2. Stop when `max_turns` is hit — on the last turn, call without tools to force a text response.
3. Stop when a tool returns `{"error": "max_output_bytes_exceeded"}` — log and continue one more turn, then force text.
4. Stop when the prompt+history exceeds a per-call budget (e.g., 20k tokens). Return a hold/0 response with reasoning "context budget exceeded."

### What stays in `ai_tools/`

The registry (`base.py`, `__init__.py`) and every concrete tool remain provider-agnostic. Tools take a `ToolContext`, return a dict. Adapters translate; tools don't know about providers. This is the property that makes Phase C and D cheap — one file per tool, no provider code changes.

### What doesn't move

- `AISpotOpinionParams` — the user-facing config stays the same (ai_model, timeframe, min_confidence).
- Prefilter logic — still runs before the tool path.
- Time-gating cache — still caps call frequency per candle.
- Response contract — `{signal, confidence, reasoning, prefilter_passed, metrics, tool_calls}`. New fields (like `cost_usd` in Phase F) are additive.

---

## Rollout Order & Kill Switches

Each phase ships behind a config flag so we can ramp safely:

- `ai_tools_enabled` (per-bot, default `true` after Phase A ships) — master switch for the whole tool path. Falls back to the old single-shot when off.
- `ai_tools_providers` (global, default all three) — lets us cut a specific provider's tool loop off if its adapter has issues in prod.
- Per-tool feature gates are overkill; rely on `enabled_tools` list built per-call.

Log every tool call with provider, tool name, latency, output size, and whether it errored. After each phase's deploy, watch the log for 24h before calling it stable.

---

## Validation Strategy

### Unit (mocked SDKs)

- Each provider adapter: tool loop correctness, turn cap, error handling, schema translation.
- Each tool: happy + edge + failure.
- Schema translation round-trips a representative tool to all three provider formats without loss.

### Integration (in-memory SQLite, mocked network)

- Evaluator end-to-end: given a scripted provider response, produces correct signal + tool_calls.
- Registry + tools against real DB fixtures — provider-agnostic.

### Live smoke (real API calls, paper account)

Per phase, one canary run against a real account with each provider. Assert `tool_calls[]` non-empty when argument-taking tools are present (Phase C+). Pre-flight costs: budget $2–5 per smoke run, not more.

### Regression

- Existing `test_ai_spot_opinion.py` suite stays green through every phase.
- Sweep of `tests/strategies/` and `tests/trading_engine/` after each merge — catch any kwargs drift.

---

## Gotchas

### Phase A: Context injection cost

Pre-computing both tools on every call means two DB queries per AI tick per product, whether the model would have asked for them or not. That's fine for the tick rate (1 per 15m per product), but flag for review if tick rate ever drops.

### Phase B: SDK version drift

Each SDK gets updated independently. Pin versions in `requirements.txt` and have a single "upgrade SDK" ritual where we re-run the adapter contract tests before bumping.

### Phase B: Gemini quirks

Gemini's function calling has historically had stricter schema limits (e.g., no `anyOf`, no `$ref`) than OpenAI or Anthropic. Validate our canonical schemas against Gemini's validator at startup — fail loud if an added tool uses an unsupported JSON Schema feature.

### Phase C: Argument validation

Each tool must validate its own arguments (model hallucinations are real — "count": -5 or "timeframe": "2m" happen). Fail with a structured error the model can read: `{"error": "invalid timeframe '2m'; valid: 5m, 15m, 1h, 4h, 1d"}`. The model usually corrects on the next turn.

### Phase D: `ai_opinion_log` retention

This table will grow fast. Add a scheduled cleanup (e.g., keep 90 days of per-call rows, aggregate older ones into daily summaries). Don't ship Phase D without the retention job.

### Phase E: Per-user permission on AI log

Only the position owner — not just any logged-in user — can read it. Use the same `require_owner` dependency our other position endpoints use. Audit added by `multiuser-security` agent after the endpoint lands.

### Multi-account per-user

User may have multiple accounts (paper/live/test). `account_id` is already threaded through; verify the AI log endpoint scopes by both user_id and account_id so switching accounts doesn't show cross-account logs.

---

## Open Questions

1. **Do we want per-bot provider selection, or per-user?** Today it's per-bot (set in strategy config). That's fine, but if a user runs 20 bots we end up hitting three APIs. Leaving as-is unless a user complains.

2. **Cost attribution — per-user or per-bot?** Phase F logs cost per call with bot_id and user_id — both queries are cheap. Decide UX later.

3. **Streaming responses?** None of this PRP depends on streaming. If we ever want live "AI is thinking..." UI, that's a separate effort and would require SSE on the API side. Not in scope.

4. **Function-calling vs structured output?** OpenAI and Gemini both support "structured output" as a separate feature from function calling. For our final JSON parse (`{signal, confidence, reasoning}`), structured output would be cleaner than regex-matching a text block. Defer to a follow-up; Phase A–F all still work with the current JSON-in-text approach.

---

## PRP Score

**7/10** — Architecturally sound, but three SDKs × per-SDK idiosyncrasies creates more "real-world surprises" surface area than a single-provider feature. Mitigations: adapter contract tests, live canary per phase, feature-flagged rollout. Phase A alone is low-risk and delivers most of the product value (context parity across providers). Phases B+ are higher-leverage but higher-touch; only commit to them after Phase A validates in prod.
