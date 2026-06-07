"""
Detection of PostgreSQL physical data-corruption errors.

When the underlying storage develops bad blocks, Postgres raises errors like
``could not read block N in file ...: Input/output error`` or ``invalid page in
block ...``. asyncpg surfaces these as DataCorruptedError / PostgresIOError,
which SQLAlchemy wraps in a ``DBAPIError`` subclass (usually OperationalError).

Background loops already survive these via broad ``except Exception`` handlers,
but treating them generically means a corrupt block aborts a whole monitor
cycle and floods the logs with full tracebacks every iteration. This detector
lets callers degrade gracefully (skip the affected query, log one clear
warning) while ordinary query errors still propagate and fail fast.

Detection is by message signature rather than by asyncpg exception class:
asyncpg is not importable in every environment (the SQLite dev venv has no
asyncpg), so importing its classes would break imports outside production.
"""

from sqlalchemy.exc import DBAPIError

# Substrings found in PostgreSQL physical-corruption / storage I/O errors.
# Compared case-insensitively.
_CORRUPTION_SIGNATURES = (
    "could not read block",
    "invalid page",
    "missing chunk number",
    "could not open file",
    "input/output error",
)


def is_db_corruption_error(exc: BaseException) -> bool:
    """Return True if ``exc`` looks like a PostgreSQL physical data-corruption error.

    Only SQLAlchemy DB-API errors whose message contains a known corruption
    signature qualify. Non-database exceptions and ordinary query errors return
    False so callers never accidentally swallow genuine bugs.
    """
    if not isinstance(exc, DBAPIError):
        return False
    message = str(exc).lower()
    return any(signature in message for signature in _CORRUPTION_SIGNATURES)
