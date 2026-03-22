"""
CredentialsProvider abstraction — Phase 2.4 of the scalability roadmap.

Wraps get_exchange_client_for_account() behind a protocol so that Phase 3
(portfolio service extraction) can swap LocalCredentialsProvider for
RemoteCredentialsProvider without touching any call-site code.

exchange_service.py remains completely unchanged — this is addition-only.

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


# ---------------------------------------------------------------------------
# Protocol — the interface any backend must satisfy
# ---------------------------------------------------------------------------

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
    ) -> Optional[object]:
        """Return an ExchangeClient for account_id, or None if not found/unavailable.

        Args:
            account_id:    The account to fetch credentials for.
            db:            Optional open AsyncSession. If provided, used directly.
                           If None, a session is opened from session_maker.
            session_maker: Session factory for PropGuardClient DB work and for
                           opening a session when db is None. Pass the secondary
                           loop's session_maker when calling from secondary loop.
            use_cache:     Whether to use the in-process client cache (default True).
        """
        ...


# ---------------------------------------------------------------------------
# Local implementation — delegates to exchange_service, zero behavior change
# ---------------------------------------------------------------------------

class LocalCredentialsProvider:
    """CredentialsProvider backed by the local database.

    Delegates to get_exchange_client_for_account(). If a db session is
    provided it is used directly; otherwise a session is opened from
    session_maker (falls back to async_session_maker if not provided).

    Deferred imports in method bodies prevent circular imports at module
    load time (credentials_provider.py is in the same package as
    exchange_service.py and database.py).
    """

    async def get_exchange_client(  # Optional[ExchangeClient]
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
        # No session provided — open one from the supplied or default session_maker
        if session_maker is None:
            from app.database import async_session_maker
            session_maker = async_session_maker
        async with session_maker() as _db:
            return await get_exchange_client_for_account(
                _db, account_id, use_cache=use_cache, session_maker=session_maker,
            )


# ---------------------------------------------------------------------------
# Remote stub — documented seam for Phase 3 microservice deployment
# ---------------------------------------------------------------------------

class RemoteCredentialsProvider:
    """CredentialsProvider backed by a credentials microservice (Phase 3).

    In a multi-service deployment, the portfolio service does not have direct
    DB access to Account credentials. Instead it calls a hardened credentials
    microservice that holds decrypted API keys and returns the data needed to
    build an ExchangeClient locally.

    Architecture (Phase 3):
        GET /internal/credentials/{account_id}
        Response: { exchange_type, api_key, api_secret, ... }
        → build ExchangeClient locally from response

    Security consideration: the credentials service should be internal-only
    (no public exposure), use mTLS or a shared secret, and issue short-lived
    tokens. See COMMERCIALIZATION.md for the full multi-tenant security roadmap.

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


# ---------------------------------------------------------------------------
# Module-level singleton — same pattern as broadcast_backend, rate_limit_backend
# ---------------------------------------------------------------------------

credentials_provider: CredentialsProvider = LocalCredentialsProvider()
