"""In-memory TTL caches for per-account live-exchange endpoints.

Shared by accounts_query_router (read path, populates + serves) and
accounts_mutation_router (write path, invalidates on settings change).

Both caches are keyed by account_id. They exist to protect the account
owner's Coinbase API rate quota when multiple members of a shared account
hit the same live endpoint — every call would otherwise reach through to
Coinbase and multiply the owner's quota spend.
"""

from typing import Any, Dict, Tuple


# {account_id: (monotonic_time, cached_response)}
_TTL_REBALANCE_STATUS: Dict[int, Tuple[float, Any]] = {}
_TTL_DUST_SWEEP: Dict[int, Tuple[float, Any]] = {}

_TTL_REBALANCE_SECONDS = 30
_TTL_DUST_SWEEP_SECONDS = 60
