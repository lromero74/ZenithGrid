# PRP: Phase 2.4 — CredentialsProvider Interface

## Feature Summary

Add a `CredentialsProvider` protocol in front of `get_exchange_client_for_account()` in
`app/services/exchange_service.py`. Zero behavior change today — `LocalCredentialsProvider`
delegates to the existing function. `RemoteCredentialsProvider` stub documents the future
credentials microservice architecture.

- `exchange_service.py` stays **completely unchanged**
- Single new file: `app/services/credentials_provider.py`
- Single new test file: `tests/services/test_credentials_provider.py` (TDD — written first)

**Motivation** (from `docs/SCALABILITY_ROADMAP.md` Phase 2.4): `get_exchange_client_for_account`
decrypts account credentials inline from the DB and builds exchange clients. This logic is
referenced in 45 files across the codebase. When the portfolio service is extracted in Phase 3,
it needs to get exchange clients without importing the monolith's DB. A `CredentialsProvider`
makes that swap a one-line config change.

---

## Architecture

```
Bot control router / trading engine / monitors
        │
        ▼ (today — unchanged)
exchange_service.get_exchange_client_for_account(db, account_id, ...)
        │
        └── decrypts credentials, creates ExchangeClient, wraps with PropGuardClient
                │
                ▼ (abstraction lives here)
        CredentialsProvider protocol
                │
        LocalCredentialsProvider   →  get_exchange_client_for_account(...)  (today)
        RemoteCredentialsProvider  →  HTTP call to credentials microservice  (Phase 3)
```

**Key constraint**: The in-memory cache (`_exchange_client_cache` in exchange_service.py),
credential decryption, PropGuard wrapping — ALL of that stays in `exchange_service.py` unchanged.
`LocalCredentialsProvider` is a pure delegation wrapper.

---

## Existing Function Signature (from `app/services/exchange_service.py`)

```python
async def get_exchange_client_for_account(
    db: AsyncSession,
    account_id: int,
    use_cache: bool = True,
    session_maker=None,
) -> Optional[ExchangeClient]:
    """
    Get an exchange client for a specific account.
    - Checks in-memory cache first (threading.Lock, safe cross-loop)
    - Fetches Account from DB
    - Paper trading → PaperTradingClient (not cached; holds DB session)
    - CEX (Coinbase / ByBit / MT5) → decrypted credentials → ExchangeClient
    - DEX → wallet key → ExchangeClient
    - prop_firm → PropGuardClient wrapper
    - session_maker: pass secondary loop's sm so PropGuardClient uses correct pool
    Returns None if account not found or credentials missing.
    """
```

**Critical**: The function takes a live `AsyncSession` as first arg. The Protocol method must
work for both callers that already have a session (pass `db=`) AND callers that don't
(pass `session_maker=` to open one internally). The `RemoteCredentialsProvider` needs
neither — it calls an HTTP API.

---

## Protocol Method Design

```python
async def get_exchange_client(
    self,
    account_id: int,
    db=None,              # Optional[AsyncSession] — pass if caller has one open
    session_maker=None,   # pass secondary loop's sm for correct pool
    use_cache: bool = True,
) -> Optional[ExchangeClient]:
```

**`LocalCredentialsProvider` behavior**:
1. If `db` is provided → call `get_exchange_client_for_account(db, account_id, ...)`
2. If `db` is None → open own session via `session_maker` (defaults to `async_session_maker`)
   then call `get_exchange_client_for_account(opened_db, account_id, ...)`

This matches the existing call-site diversity: some callers have `db` from a `Depends(get_db)`,
others (monitors, secondary loop) open their own sessions.

---

## Reference Files

| File | Purpose |
|------|---------|
| `backend/app/services/exchange_service.py` | The function being wrapped — read in full above |
| `backend/app/services/broadcast_backend.py` | **Primary pattern**: Protocol + Local + Remote stub + singleton |
| `backend/app/auth_routers/rate_limit_backend.py` | **Secondary pattern**: deferred imports, no-arg constructor |
| `backend/app/exchange_clients/base.py` | `ExchangeClient` ABC — the return type |
| `backend/tests/services/test_broadcast_backend.py` | TDD test pattern to mirror |
| `backend/tests/services/test_exchange_service.py` | Existing exchange service tests — shows how to mock `get_exchange_client_for_account` |

---

## Implementation Blueprint

### File: `backend/app/services/credentials_provider.py`

```python
"""
CredentialsProvider abstraction — Phase 2.4 of the scalability roadmap.

Wraps get_exchange_client_for_account() behind a protocol so that Phase 3
(portfolio service extraction) can swap LocalCredentialsProvider for
RemoteCredentialsProvider without touching any call-site code.

Usage (when migrating call sites in Phase 3):
    from app.services.credentials_provider import credentials_provider
    client = await credentials_provider.get_exchange_client(account_id, db=db)
    # or, from a monitor with its own session_maker:
    client = await credentials_provider.get_exchange_client(account_id, session_maker=sm)
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class CredentialsProvider(Protocol):
    """Exchange client factory abstraction.

    Implementations:
    - LocalCredentialsProvider:  delegates to get_exchange_client_for_account (today)
    - RemoteCredentialsProvider: calls a credentials microservice HTTP API (Phase 3)
    """

    async def get_exchange_client(
        self,
        account_id: int,
        db=None,
        session_maker=None,
        use_cache: bool = True,
    ) -> Optional[object]:  # Optional[ExchangeClient] — object avoids heavy ABC import in Protocol
        """Return an ExchangeClient for account_id, or None if not found/unavailable."""
        ...


class LocalCredentialsProvider:
    """CredentialsProvider backed by the local database.

    Delegates to get_exchange_client_for_account(). If a db session is
    provided it is used directly; otherwise a session is opened from
    session_maker (defaults to async_session_maker).

    Deferred imports prevent circular imports at module load time.
    """

    async def get_exchange_client(
        self,
        account_id: int,
        db=None,
        session_maker=None,
        use_cache: bool = True,
    ) -> Optional[object]:
        from app.services.exchange_service import get_exchange_client_for_account
        if db is not None:
            return await get_exchange_client_for_account(
                db, account_id, use_cache=use_cache, session_maker=session_maker,
            )
        # No session provided — open one
        if session_maker is None:
            from app.database import async_session_maker
            session_maker = async_session_maker
        async with session_maker() as _db:
            return await get_exchange_client_for_account(
                _db, account_id, use_cache=use_cache, session_maker=session_maker,
            )


class RemoteCredentialsProvider:
    """CredentialsProvider backed by a credentials microservice (Phase 3).

    In a multi-service deployment, the portfolio service does not have direct
    DB access to Account credentials. Instead it calls a hardened credentials
    microservice that holds decrypted API keys and returns short-lived signed
    exchange clients (or just the credentials to build one locally).

    Architecture (Phase 3):
        GET /internal/credentials/{account_id}
        → { exchange_type, api_key, api_secret, ... }
        → build ExchangeClient locally from response

    NOT IMPLEMENTED — raises NotImplementedError. Implement when Phase 3
    extracts the portfolio/trading service from the monolith.
    """

    async def get_exchange_client(
        self,
        account_id: int,
        db=None,
        session_maker=None,
        use_cache: bool = True,
    ) -> Optional[object]:
        raise NotImplementedError("RemoteCredentialsProvider not yet implemented (Phase 3)")


# Module-level singleton — same pattern as broadcast_backend and rate_limit_backend
credentials_provider: CredentialsProvider = LocalCredentialsProvider()
```

---

## TDD Test File: `backend/tests/services/test_credentials_provider.py`

Write FIRST — all tests must initially fail with `ModuleNotFoundError`.

### Test cases

```
1.  LocalCredentialsProvider.get_exchange_client with db provided → delegates to
    get_exchange_client_for_account(db, account_id, use_cache=True, session_maker=None)

2.  LocalCredentialsProvider.get_exchange_client with session_maker (no db) →
    opens session via session_maker, calls get_exchange_client_for_account with opened db

3.  LocalCredentialsProvider.get_exchange_client with no db, no session_maker →
    falls back to async_session_maker, opens session, delegates correctly

4.  LocalCredentialsProvider passes use_cache=False through to underlying function

5.  LocalCredentialsProvider returns None when underlying function returns None

6.  Module-level singleton exists and is LocalCredentialsProvider

7.  credentials_provider satisfies CredentialsProvider Protocol (isinstance)

8.  RemoteCredentialsProvider is importable

9.  RemoteCredentialsProvider.get_exchange_client raises NotImplementedError

10. RemoteCredentialsProvider satisfies CredentialsProvider Protocol (isinstance)
```

### Key mock patterns

```python
from unittest.mock import AsyncMock, MagicMock, patch

# Test 1: db provided — patch the underlying function
@patch('app.services.exchange_service.get_exchange_client_for_account', new_callable=AsyncMock)
async def test_delegates_with_db(self, mock_fn):
    mock_db = AsyncMock()
    mock_client = MagicMock()
    mock_fn.return_value = mock_client

    from app.services.credentials_provider import LocalCredentialsProvider
    provider = LocalCredentialsProvider()
    result = await provider.get_exchange_client(42, db=mock_db)

    assert result is mock_client
    mock_fn.assert_awaited_once_with(mock_db, 42, use_cache=True, session_maker=None)

# Test 2: session_maker provided, no db — must mock session_maker as async context manager
@patch('app.services.exchange_service.get_exchange_client_for_account', new_callable=AsyncMock)
async def test_delegates_with_session_maker(self, mock_fn):
    mock_db = AsyncMock()
    mock_sm = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_sm.return_value = mock_cm
    mock_fn.return_value = MagicMock()

    provider = LocalCredentialsProvider()
    await provider.get_exchange_client(42, session_maker=mock_sm)

    # Verify it opened a session from the provided session_maker
    mock_sm.assert_called_once()
    mock_fn.assert_awaited_once_with(mock_db, 42, use_cache=True, session_maker=mock_sm)

# Test 3: neither db nor session_maker — falls back to async_session_maker
@patch('app.services.exchange_service.get_exchange_client_for_account', new_callable=AsyncMock)
@patch('app.database.async_session_maker')
async def test_fallback_to_default_session_maker(self, mock_default_sm, mock_fn):
    mock_db = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_default_sm.return_value = mock_cm
    mock_fn.return_value = None

    provider = LocalCredentialsProvider()
    result = await provider.get_exchange_client(99)
    assert result is None
    mock_default_sm.assert_called_once()
```

---

## Gotchas

- **`@runtime_checkable` is required** — same as broadcast_backend and rate_limit_backend.
- **Return type in Protocol is `Optional[object]`** — using `Optional[ExchangeClient]` would import the ABC at module level, creating a potentially heavy import chain. Using `object` in the Protocol is equivalent at runtime (isinstance only checks method existence) and avoids the import. `LocalCredentialsProvider` and `RemoteCredentialsProvider` implementations can use a comment `# Optional[ExchangeClient]`.
- **Deferred imports in method bodies** — `LocalCredentialsProvider.get_exchange_client` uses `from app.services.exchange_service import get_exchange_client_for_account` inside the method (not at module level). This avoids a potential circular import: `credentials_provider.py` is in `app/services/`, same package as `exchange_service.py`. Also matches `rate_limit_backend.py` pattern.
- **session_maker fallback import location** — `from app.database import async_session_maker` is inside the `if session_maker is None:` branch (deferred), not at class/module level. This avoids importing the DB engine at test time.
- **Patch target for deferred imports** — always patch at the SOURCE module:
  - `patch('app.services.exchange_service.get_exchange_client_for_account')` ✓
  - `patch('app.database.async_session_maker')` ✓
  - NOT `patch('app.services.credentials_provider.get_exchange_client_for_account')` ✗
- **session_maker mock must be async context manager** — `async with session_maker() as db:` requires the mock to support `__aenter__` and `__aexit__`. See test pattern above.
- **No changes to existing call sites** — this is addition-only. The 45 files calling `get_exchange_client_for_account` are untouched. Migration happens in Phase 3.
- **Test file location**: `tests/services/test_credentials_provider.py` — matches the source location `app/services/credentials_provider.py`.

---

## Tasks (in order)

1. **Write failing tests** in `backend/tests/services/test_credentials_provider.py`
2. **Run tests** — confirm all fail with `ModuleNotFoundError: No module named 'app.services.credentials_provider'`
3. **Write implementation** in `backend/app/services/credentials_provider.py`
4. **Run tests** — confirm all pass
5. **Lint**: `flake8 app/services/credentials_provider.py --max-line-length=120`
6. **Verify existing exchange service tests unbroken**: `pytest tests/services/test_exchange_service.py -q`
7. **Import check**: `python3 -c "from app.services.credentials_provider import credentials_provider, CredentialsProvider, LocalCredentialsProvider, RemoteCredentialsProvider; print('OK')"`

---

## Validation Gates

```bash
# Run from: /home/ec2-user/ZenithGrid/backend

# 1. New tests pass
./venv/bin/python3 -m pytest tests/services/test_credentials_provider.py -v

# 2. Lint
./venv/bin/python3 -m flake8 app/services/credentials_provider.py --max-line-length=120

# 3. Existing exchange service tests unbroken
./venv/bin/python3 -m pytest tests/services/test_exchange_service.py -q

# 4. Import check
./venv/bin/python3 -c "from app.services.credentials_provider import credentials_provider, CredentialsProvider, LocalCredentialsProvider, RemoteCredentialsProvider; print('imports OK')"
```

---

## Quality Checklist

- [ ] Tests written before implementation (TDD)
- [ ] All 10 tests pass
- [ ] `@runtime_checkable` on Protocol
- [ ] `RemoteCredentialsProvider` docstring documents Phase 3 HTTP API architecture
- [ ] Deferred imports in method bodies (no top-level circular import risk)
- [ ] Module-level singleton follows `broadcast_backend` / `rate_limit_backend` pattern
- [ ] Zero changes to `exchange_service.py` or any existing call site
- [ ] Lint passes (flake8 --max-line-length=120)
- [ ] Existing `test_exchange_service.py` still passes

---

**Confidence score: 9/10** — Single new file, thin delegation layer, clear existing patterns to follow. The one complexity above prior seam PRPs is the `db` vs `session_maker` branching in `LocalCredentialsProvider`, and the async context manager mock in tests — both are fully documented above.
