# PRP: Code Quality Sweep — Security, Testing, Hygiene (v2.160.4 baseline)

**Version:** 1.0
**Source sweep:** `/code-quality general` run at v2.160.4 (2026-04-21)
**Feature Branch(es):** one per phase — `fix/quality-critical-security`, `fix/quality-known-bugs`, `feat/quality-auth-test-coverage`, `refactor/quality-modularization`, etc.
**Confidence Score:** 8/10 — every item is grounded in a specific file:line surfaced by the sweep agents.

---

## Overview

A full read-only `/code-quality general` sweep at v2.160.4 surfaced **45 findings** across security, testing, hygiene, and validation, plus one latent production bug. Code on the whole is healthy: `backend/app/` and the frontend both pass lint and typecheck cleanly, and the routers/services/strategies directories have broad test coverage. The gaps that remain are concentrated in a handful of areas: two critical security/config issues, a known `AttributeError` sitting in the reports flow, an entire untested auth-router group, and a small set of files that have grown past the 1200-line modularization cap.

This PRP bundles every finding from the sweep into a staged execution plan. Each phase can ship as its own patch/minor release; the phases are ordered by blast radius (stop the bleeding first, then prevent broken deploys, then pay down debt).

### Out of scope
- New features. This PRP is exclusively remediation and debt paydown.
- Rewriting any subsystem from scratch. Refactoring is limited to extracting helpers out of files that exceed the 1200-line cap.
- Frontend state-machine tests (`ArticleReaderContext`, `App.tsx`) — deferred; different harness, separate PRP later.

---

## TDD Requirement

Every fix in this PRP must follow the project's TDD cycle (red → green → refactor).

- **Bug fixes**: write a failing test that reproduces the bug, then fix, then watch it turn green.
- **Security fixes**: write a test that exercises the vulnerable path as a non-privileged user and asserts 403/404, then apply the guard.
- **Refactors**: the existing test suite must stay green through every extraction. If an extracted helper has no existing coverage, add a direct test before moving it.

No phase of this PRP ships without tests.

---

## Phase 1 — Critical Security & Config Guards

**Branch:** `fix/quality-critical-security`
**Target version:** v2.160.5 (patch)
**Estimated effort:** 1–2 hours

### 1.1 Fix global budget overwrite in `resize_all_budgets` (CRITICAL)

**File:** `backend/app/position_routers/position_actions_router.py:349-374`

**Current behavior:** when a caller has `Perm.POSITIONS_WRITE` but an empty `writable_ids` list and supplies no `account_id` param, the `else: if writable_ids: query = query.where(...)` branch silently no-ops. The query collapses to `select(Position).where(Position.status == "open")` and rewrites `max_quote_allowed` on every open position across every user.

**Fix:** always apply the `account_id IN (...)` filter unconditionally, using `writable_ids or [-1]` so an empty list reduces to an impossible match instead of no filter. Alternatively, raise HTTP 403 when `writable_ids` is empty and no `account_id` was provided.

**Tests required (write first):**
- `test_resize_all_budgets_empty_writable_ids_returns_403` — a user with `POSITIONS_WRITE` but zero writable accounts cannot mutate any position.
- `test_resize_all_budgets_no_account_id_limits_to_user_scope` — passing no `account_id` still scopes the update to writable accounts only.
- `test_resize_all_budgets_other_users_positions_untouched` — create two users with open positions, verify user A's resize does not touch user B's `max_quote_allowed`.

### 1.2 JWT secret startup guard (CRITICAL)

**File:** `backend/app/config.py:62`

**Current behavior:** `jwt_secret_key` defaults to the literal string `"jwt-secret-key-change-in-production"`. If `.env` is missing or the env var is not set, the bot boots with a publicly-known signing key.

**Fix options (pick one):**
- **A. Pydantic validator (preferred):** add a `@field_validator("jwt_secret_key")` that raises `ValueError` when the value equals the default and `ENVIRONMENT == "production"`.
- **B. Startup assertion:** add a guard in `main.py` startup that calls `sys.exit(1)` with a loud log if the default is still in place under production.

Either way, also emit a `WARNING` log in dev/test when the default is used so it is visible locally.

**Tests required (write first):**
- `test_jwt_secret_default_rejected_in_production` — instantiating `Settings(ENVIRONMENT="production")` with no override raises.
- `test_jwt_secret_default_allowed_in_development` — same call with `ENVIRONMENT="development"` succeeds but logs a warning.
- `test_jwt_secret_override_accepted` — explicit override is respected in all environments.

### 1.3 Known bug: `create_goal` schema mismatch

**File:** `backend/app/routers/reports_crud_router.py:614` and the `GoalCreate` Pydantic schema

**Current behavior:** `create_goal` reads `body.minimap_threshold_days`, but `GoalCreate` does not declare that field. Any real POST to `/api/reports/goals` raises `AttributeError`. The test-writer already pinned this as `TestKnownBugs::test_goal_create_schema_missing_minimap_threshold_days` in `tests/routers/test_reports_crud_router.py`.

**Fix:** add `minimap_threshold_days: int | None = None` (or the correct type — check the model column) to `GoalCreate`.

**Test update required:** replace the `TestKnownBugs` pin test with a proper happy-path create test that exercises the new field and asserts round-trip persistence.

---

## Phase 2 — High-Priority Security Hardening

**Branch:** `fix/quality-global-settings-isolation`
**Target version:** v2.161.0 (minor — changes user-visible permission requirements)
**Estimated effort:** 2–4 hours

### 2.1 Blacklist categories — global mutation under per-user perm (HIGH)

**File:** `backend/app/routers/blacklist_router.py:116-162`

**Current behavior:** `update_category_settings` writes to a global `Settings` row (`key="blacklist_categories"`). The `Settings` model has no `user_id` column, so any user with `Perm.BLACKLIST_WRITE` edits the allowed blacklist categories for every user on the platform.

**Fix (preferred):** gate the endpoint on `require_superuser`. Longer-term, if per-user blacklist categories are needed, introduce a `user_id` column on `Settings` and scope reads/writes — but that is a bigger migration and a separate PRP candidate.

### 2.2 `update_settings` and `update_setting_by_key` (HIGH)

**File:** `backend/app/routers/settings_router.py:138-178, 242-275`

**Current behavior:** both endpoints write to `.env` and the global `Settings` table under `Perm.SETTINGS_WRITE`. `coinbase_api_key`, `coinbase_api_secret`, and every DB setting are mutated for the whole instance.

**Fix:** gate both on `require_superuser`. Same migration-scale caveat as 2.1 applies if per-user settings are ever needed.

### 2.3 Template name-uniqueness leak (MEDIUM)

**File:** `backend/app/routers/templates.py:77, 177`

**Current behavior:** both uniqueness checks query `BotTemplate` globally. A 400 "already exists" response discloses the existence of another user's template by name.

**Fix:** add `BotTemplate.user_id == current_user.id` to both queries. If `is_default == True` templates should remain globally unique, add that branch explicitly.

### 2.4 API key preview length (MEDIUM)

**File:** `backend/app/routers/ai_credentials_router.py:82-87`

**Current behavior:** `_api_key_preview` returns the last 8 plaintext characters of the decrypted API key. Most platforms use 4.

**Fix:** change slice to `plaintext[-4:]`.

### 2.5 Public `market_data` rate limiting (LOW)

**File:** `backend/app/routers/market_data_router.py`

**Current behavior:** public ticker / candles / batch-price endpoints have no auth and no rate limiting. A single anonymous caller can exhaust the shared Coinbase rate budget.

**Fix:** add an IP-keyed rate limit middleware (reuse the pattern from the nginx `auth 5r/m + API 30r/s` hardening already documented in `index.json`). Consider wiring it at the FastAPI level so dev mode also enforces it.

### Tests required for Phase 2

For every endpoint changed:
- Non-superuser call returns 403 (where superuser-gated).
- Superuser call still succeeds.
- For templates: user A's template with name "X" + user B's template with name "X" both succeed; user B gets no uniqueness error referencing user A's template.
- For the API key preview: assert length == 4 for a known plaintext key.

---

## Phase 3 — Known Bug Tail + Test Coverage for Auth Routers

**Branch:** `feat/quality-auth-test-coverage`
**Target version:** v2.161.1 (patch — no behavior change, just tests)
**Estimated effort:** 1 day

### 3.1 Fix the 2 F821 broken tests

**File:** `backend/tests/routers/test_account_member_access.py:340, 409`

`ReportGoal` and `Report` are undefined. Either the imports were dropped during a refactor or the symbol names changed. Investigate:
1. Run `./venv/bin/python3 -m pytest tests/routers/test_account_member_access.py -v` — does it collect? Does it pass? If lint is catching F821 it is likely the tests also don't run.
2. Add the correct imports (likely `from app.models.reporting import Report, Goal as ReportGoal` or similar — check `app/models/`).
3. Re-run and confirm the tests now exercise the intended behavior. If they were always dead, delete them and replace with meaningful coverage.

### 3.2 Write tests for auth router group (HIGH coverage gap)

The coverage scan flagged these as untested critical paths:

| File | LOC | Surface |
|---|---|---|
| `auth_routers/password_router.py` | 148 | Change/reset password flow |
| `auth_routers/email_verify_router.py` | 191 | Email verification tokens |
| `auth_routers/device_trust_router.py` | 112 | Trusted-device MFA bypass |
| `auth_routers/helpers.py` | 335 | Shared token/session helpers |

For each, cover:
- **Happy path** per endpoint.
- **Token/email validation** — expired, replayed, forged, wrong user.
- **Multi-user isolation** — user A cannot trigger password reset / email verification for user B.
- **Rate-limit integration** — the MFA brute-force protection added in v2.26.2 must fire (5 attempts / 5 min per token) — write a test that asserts 429 after the threshold.
- **Device trust**: a trusted device cookie issued to user A cannot bypass MFA for user B on the same browser.
- **Password change side effects**: `tokens_valid_after` is bumped (from the v2.26.3 JTI revocation work) so old JWTs stop working.

Use the fixture patterns from `conftest.py` and the test-writer's work in `test_reports_crud_router.py` (direct endpoint calls with a synthesized `User` + `db_session`).

### 3.3 Known bug test upgrade

Once Phase 1.3 ships the `minimap_threshold_days` schema fix, replace `TestKnownBugs::test_goal_create_schema_missing_minimap_threshold_days` in `test_reports_crud_router.py` with a real happy-path create test that persists the field.

---

## Phase 4 — Error Handling & Quick Hygiene Wins

**Branch:** `fix/quality-error-handling`
**Target version:** v2.161.2 (patch)
**Estimated effort:** 2–3 hours

### 4.1 Silent exception swallows

| File:Line | Current | Fix |
|---|---|---|
| `services/perps_monitor.py:252-253` | `except Exception: pass` around WebSocket broadcast | `logger.warning("perps broadcast failed", exc_info=True)` before `pass` — user-facing notification loss |
| `main.py:799-800` | `except Exception: pass` around `broadcast_user_presence` on disconnect | `logger.warning(...)` before `pass` |
| `main.py:719-720` | `except Exception: pass` around JSON parse for oversized WS messages | Narrow to `except (ValueError, TypeError):` and leave silent (expected case) |
| `exchange_clients/paper_trading_client.py:593,601` | Two `except Exception: pass` in price fallback chain | `logger.debug("paper_trading price fallback failed for %s", currency, exc_info=True)` for each attempt |
| `auth_routers/mfa_email_router.py:273-274` | `except Exception: pass` — context unclear | Read the block, then log or narrow |
| `multi_bot_monitor.py:301-302` | `except RuntimeError: pass` — narrow already but no log | Add debug log |

### 4.2 Dead code removal

Remove in a single commit — all small:
- `backend/app/ai_service.py:74` — unused `import google.generativeai as genai` (no noqa).
- `backend/app/indicator_calculator.py:122,136` — unused `_band_type`, `_line_type`.
- `backend/app/routers/templates.py:66`, `bot_crud_router.py:82` — unused `_strategy_def`.
- `backend/app/services/grid_rotation_service.py:109` — unused `_trades`.
- `backend/app/services/grid_trading_service.py:573` — unused `_total_investment`.
- `backend/app/strategies/bull_flag_scanner.py:380` — unused `_pole_start_idx`.
- `backend/app/strategies/spatial_arbitrage.py:241` — unused `_min_size_usd`.
- `backend/app/bot_routers/bot_crud_router.py:623,751` — unused `_source_account`, `_`.
- `backend/app/trading_engine/buy_executor.py:347` and `sell_executor.py:85` — unused `_pending_order`.
- `backend/app/indicators/ai_spot_opinion.py:217,218` — unused `_highs`, `_lows`.

Also review the 8 `# TODO:` markers across `dex_client.py`, `indicator_based.py`, `grid_trading_service.py`, `buy/sell_executor.py` — either convert to GitHub issues or resolve inline.

### 4.3 Test-suite lint cleanup

Run `autoflake --remove-all-unused-imports --in-place --recursive backend/tests/` to clear the 64 F401 + 16 F841 unused-import/local findings. Spot-check the diff before committing — autoflake has been known to strip imports used only for side effects. Then re-run `flake8 backend/tests/ --max-line-length=120` and fix the remaining ~30 style issues manually (E127/E128/E306/E261 — cosmetic, not urgent).

### 4.4 Hardcoded config

- `backend/app/exchange_clients/dex_constants.py:9` — `ETHEREUM_RPC_URL = "https://mainnet.infura.io/v3/"` is a partial URL with no API key. Move to `settings.ethereum_rpc_url` with no default; require the env var at runtime if DEX features are enabled.

---

## Phase 5 — Modularization (6 backend + 4 frontend files over 1200 lines)

**Branch:** `refactor/quality-modularization`
**Target version:** v2.162.0 (minor — no behavior change, but big refactor)
**Estimated effort:** 2–3 days

Do this **last** because it touches many files and the tests from Phase 3 increase confidence that nothing silently breaks. Split each file along its natural seams. Keep public imports stable — re-export from the original file if any consumer reaches into private helpers, but prefer actually updating consumers per CLAUDE.md's "Do the Right Thing" rule.

### 5.1 Backend files over 1200 LOC

| File | LOC | Split strategy |
|---|---|---|
| `app/database_seeds.py` | 1337 | One submodule per seed type (users, accounts, bots, templates, sources, etc.) under `app/seeds/`. Keep `database_seeds.py` as a thin orchestrator that calls each. |
| `app/trading_engine/signal_processor.py` | 1308 | Extract `_decide_buy` (272L) into `signal_processor/buy_decision.py`, `_decide_and_execute_sell` (273L) into `signal_processor/sell_decision.py`. Keep the entrypoint in `signal_processor/__init__.py`. |
| `app/services/report_generator_service/expense_builder.py` | 1245 | Split per report section (goal cards, changes, category rollups, etc.). |
| `app/services/portfolio_service.py` | 1241 | Extract `get_generic_cex_portfolio` (194L), `get_account_balances` (130L), plus the paper/DEX helpers into `portfolio_service/` subpackage. |
| `app/services/report_generator_service/html_builder.py` | 1228 | Split per-section HTML builders. |
| `app/strategies/indicator_based.py` | 1218 | Extract calculation helpers, config validators, and signal helpers into sibling modules. |

### 5.2 Long functions inside `trading_engine/`

- `signal_processor._decide_and_execute_sell` (273L at :905) → split into `validate` / `build_context` / `execute` phases.
- `signal_processor._decide_buy` (272L at :424) → same pattern.
- `sell_executor.execute_sell` (264L at :861) and `execute_sell_short` (165L) → extract pre/post-execution helpers.
- `buy_executor.execute_buy` (256L at :276) → further decompose beyond the existing `_post_buy_operations` helper.
- `report_scheduler.generate_report_for_schedule` (264L at :105) → split into data-fetch / render / deliver stages.
- `grid_trading_service.initialize_grid` (250L at :26) and `handle_grid_order_fill` (182L at :344) → decompose into grid-setup / order-tracking / fill-handling helpers.

### 5.3 Cross-router private-helper reaches

| Consumer | Source | Symbol(s) | New home |
|---|---|---|---|
| `routers/reports_generation_router.py` | `routers/reports_crud_router.py` | `_get_accessible_goal`, `_get_writable_goal`, `_get_writable_schedule`, `_report_to_dict` | `services/report_access.py` |
| `routers/accounts_mutation_router.py` | `routers/accounts_query_router.py` | `_build_rebalance_response`, etc. | `services/account_responses.py` |
| `routers/accounts_mutation_router.py` | `position_routers/panic_sell_router.py` | `_verify_mfa` | `auth/mfa_verification.py` |

Move each helper to the new module, update all consumers, delete the old location (no re-export shims per CLAUDE.md).

### 5.4 Frontend files over 1200 LOC

| File | LOC | Split strategy |
|---|---|---|
| `components/reports/ExpenseItemsEditor.tsx` | 1338 | Split per tab/section — one component per editor mode. |
| `pages/Settings.tsx` | 1250 | One component per settings panel; keep `Settings.tsx` as the tab chrome only. |
| `components/trading/DCABudgetConfigForm.tsx` | 1238 | Extract each subform (schedule, amount config, etc.) as its own component. |
| `components/account/PortfolioManagement.tsx` | 1228 | Split by tab + modal; move modals into sibling files. |

Run `npx tsc --noEmit` after every extraction.

### 5.5 Docs drift

`backend/app/routers/account_sharing_router.py` exists but is missing from `docs/architecture/backend.json`. Run the `architecture-sync` agent once at the end of this phase to catch this plus any drift introduced by the refactors.

---

## Phase 6 — Deferred Coverage (optional, separate PRP later)

Not part of this PRP's scope, but noted so nothing is forgotten:

| File | LOC | Why deferred |
|---|---|---|
| `frontend/src/contexts/ArticleReaderContext.tsx` | 1044 | Complex TTS + iOS audio state machine; needs a thoughtful Vitest + RTL harness plus audio mocks. |
| `frontend/src/App.tsx` | 935 | Top-level routing + auth gating; most-valuable test would be a smoke "renders without crashing under each auth state" — write separately. |
| `backend/app/database_seeds.py` | 1337 | Coverage will come naturally after Phase 5.1 splits it into testable submodules. |
| `backend/app/main.py` | 827 | Middleware/exception handler wiring. Partial coverage via integration tests in existing suite; a dedicated harness is heavier lift. |
| `backend/app/news_data/{debt_ceiling_data,news_sources}.py` | 1122 + 830 | Financial data parsing + source registry. Most lines are data, not logic. |
| `backend/app/services/report_generator_service/chart_{pdf,}renderer.py` | 201 + 197 | Chart rendering is visual — hard to unit test meaningfully; rely on PDF diff in integration tests. |
| `backend/app/routers/reports_generation_router.py` | 608 | Heavy service wrapper; meaningful tests need 4+ service mocks. Flagged by the test-writer as "good next sitting." |

---

## Implementation Strategy

Ship each phase as its own dev branch → PR → `/shipit`. Phases 1–4 are small enough to ship rapidly; Phase 5 is a larger refactor that benefits from the expanded test coverage delivered in Phase 3.

### Suggested ordering

1. **Phase 1 (same day)** — critical security + the AttributeError. Do not delay. Ship as v2.160.5.
2. **Phase 2** — Permission gating on the three global-mutation endpoints. Ship as v2.161.0 (minor — breaking perm changes).
3. **Phase 3** — Fix the 2 broken tests, then write the auth-router test suite. Ship as v2.161.1.
4. **Phase 4** — Error handling + dead code + lint cleanup. Ship as v2.161.2.
5. **Phase 5** — Modularization. Ship as v2.162.0 after the other phases are green. Run the full regression suite + a manual smoke test of trading_engine/reports/portfolio on the dev instance before merging.

### Per-phase checklist

Before tagging each phase:
- [ ] All new tests pass (`pytest tests/<touched_dirs>/ -v`).
- [ ] Lint clean on every changed file (`flake8 <files> --max-line-length=120`).
- [ ] `npx tsc --noEmit` passes.
- [ ] `CHANGELOG.md` updated with a user-facing entry (Security / Fixed / Changed).
- [ ] `docs/architecture/index.json` version bumped.
- [ ] If routers/services/models changed: run `architecture-sync` agent.
- [ ] No silent deletions — `git diff` reviewed before staging.

---

## Files Touched (summary)

**Backend:**
- `app/position_routers/position_actions_router.py` (Phase 1)
- `app/config.py` + `app/main.py` (Phase 1)
- `app/routers/reports_crud_router.py` + schema file (Phase 1)
- `app/routers/blacklist_router.py`, `settings_router.py`, `templates.py`, `ai_credentials_router.py`, `market_data_router.py` (Phase 2)
- `app/auth_routers/*.py` + new test files (Phase 3)
- `app/services/perps_monitor.py`, `main.py`, `exchange_clients/paper_trading_client.py`, `auth_routers/mfa_email_router.py`, `multi_bot_monitor.py` (Phase 4)
- `app/ai_service.py` + ~10 other small unused-var files (Phase 4)
- `app/exchange_clients/dex_constants.py` (Phase 4)
- Everything in §5.1–§5.3 (Phase 5)

**Tests:**
- `tests/position_routers/test_position_actions_router.py` (new or existing — resize_all_budgets tests)
- `tests/test_config.py` (JWT secret validator)
- `tests/routers/test_reports_crud_router.py` (minimap_threshold_days happy path)
- `tests/routers/test_account_member_access.py` (fix F821)
- `tests/auth_routers/test_{password,email_verify,device_trust,helpers}_router.py` (new)

**Docs:**
- `CHANGELOG.md` — entry per phase
- `docs/architecture/index.json` — version bump per phase
- `docs/architecture/backend.json` — router/service updates via `architecture-sync`

---

## Success Criteria

- All 45 findings from the v2.160.4 sweep are either resolved or explicitly deferred with a recorded reason.
- A re-run of `/code-quality general` on the final branch surfaces zero critical and zero high findings (or, where new items surface, they are expected and tracked).
- No regressions in the full backend test suite.
- `flake8 app/ --max-line-length=120` stays at 0 errors.
- `npx tsc --noEmit` stays at 0 errors.
- Every file in `backend/app/` is at or below the 1200-line cap.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Phase 2 permission changes break existing superusers' workflows | Test with a dev account first; document the new superuser requirement in CHANGELOG. |
| Phase 5 refactor silently drops logic during extraction | Run the full test suite after every file split; use `git diff --stat` to verify net line-count change matches expectation. |
| `autoflake` in Phase 4.3 strips imports that only exist for side effects | Spot-review the diff before committing; known side-effect imports should have `# noqa: F401` already. |
| JWT secret validator (Phase 1.2) breaks local dev for other contributors | Emit a clear `WARNING` log, not an error, in `development` mode. Raise only in `production`. |
| Template uniqueness change (Phase 2.3) surfaces existing duplicate names between users | Not a real risk — the new behavior *allows* cross-user duplicates; it never retroactively rejects existing data. |

---

## References

- Sweep run: `/code-quality general` at v2.160.4 (2026-04-21)
- Agents: `multiuser-security`, `test-auditor` (read-only + write), `code-hygiene` (full), `validation-gates`
- Source findings: see the consolidated report in the session log that produced this PRP.
- Related history:
  - `index.json.multi_user_data_isolation.hardened_in_v2_7_*` — prior isolation rounds
  - `SECURITY_AUDIT_v1.31.0.md` — application-level hardening status
  - `index.json.security_audit_v2_26_{2,3}` — internet-facing + token-revocation hardening
