"""
Server Resource Plan

Auto-derives DB pool sizes and concurrency caps from pg_max_connections.
The only value you ever need to change manually is MONITOR_RESOURCE_SHARE —
everything else recalculates when you bump hardware.
"""

import logging
import math

logger = logging.getLogger(__name__)

# ── Tunable knobs ────────────────────────────────────────────────────────────
# Fraction of usable PG connections reserved for the bot monitor.
# Raise this to be more aggressive (faster bots, API may queue under load).
# Lower it to favour API responsiveness over bot throughput.
MONITOR_RESOURCE_SHARE = 0.60

# Connections always reserved for superuser / DBA emergency access.
PG_SUPERUSER_RESERVED = 3

# Fraction reserved for the read-only analytics pool (reports, account values).
READ_POOL_SHARE = 0.12
# ─────────────────────────────────────────────────────────────────────────────


def _get_pg_max_connections() -> int:
    """Query PostgreSQL max_connections synchronously. Returns 25 on SQLite or error."""
    try:
        from app.config import settings
        if not settings.is_postgres:
            return 25  # SQLite — use conservative baseline
        import psycopg2
        sync_url = settings.database_url.replace('+asyncpg', '')
        with psycopg2.connect(sync_url) as conn:
            with conn.cursor() as cur:
                cur.execute('SHOW max_connections')
                return int(cur.fetchone()[0])
    except Exception as e:
        logger.warning(f'Could not query pg max_connections ({e}). Defaulting to 25.')
        return 25


class ResourcePlan:
    """Computed resource allocation derived from pg max_connections.

    Allocation logic:
      usable = pg_max - PG_SUPERUSER_RESERVED
      monitor_slots = floor(usable * MONITOR_RESOURCE_SHARE)
      read_slots   = max(3, floor(usable * READ_POOL_SHARE))
      api_slots    = usable - monitor_slots - read_slots

    Write pool covers both monitor and API slots.
    Concurrency maxes are derived from monitor_slots:
      pair_max = floor(sqrt(monitor_slots)) - 1
      bot_max  = floor(monitor_slots / (1 + pair_max))
    """

    __slots__ = (
        'pg_max_connections', 'usable',
        'monitor_slots', 'api_slots', 'read_slots',
        'write_pool_size', 'write_pool_overflow',
        'read_pool_size', 'read_pool_overflow',
        'bot_concurrency_max', 'pair_concurrency_max',
    )

    def __init__(self) -> None:
        pg_max = _get_pg_max_connections()
        usable = max(10, pg_max - PG_SUPERUSER_RESERVED)
        monitor = max(3, math.floor(usable * MONITOR_RESOURCE_SHARE))
        read = max(3, math.floor(usable * READ_POOL_SHARE))
        api = max(3, usable - monitor - read)

        write_total = monitor + api
        self.pg_max_connections = pg_max
        self.usable = usable
        self.monitor_slots = monitor
        self.api_slots = api
        self.read_slots = read

        # ~2:1 base:overflow split so burst capacity doesn't exhaust the pool
        self.write_pool_size = max(5, math.floor(write_total * 0.67))
        self.write_pool_overflow = max(2, write_total - self.write_pool_size)

        self.read_pool_size = max(2, math.floor(read * 0.75))
        self.read_pool_overflow = max(1, read - self.read_pool_size)

        # Concurrency: balance depth (pair parallelism) vs breadth (bot parallelism)
        # sqrt heuristic: pair_max ≈ sqrt(monitor_slots) - 1
        self.pair_concurrency_max = max(1, math.floor(math.sqrt(monitor)) - 1)
        self.bot_concurrency_max = max(1, math.floor(monitor / (1 + self.pair_concurrency_max)))

        logger.info(
            'ResourcePlan: pg_max=%d usable=%d | '
            'write_pool=%d+%d  read_pool=%d+%d | '
            'monitor_slots=%d (bot_max=%d pair_max=%d)  api_slots=%d',
            pg_max, usable,
            self.write_pool_size, self.write_pool_overflow,
            self.read_pool_size, self.read_pool_overflow,
            monitor, self.bot_concurrency_max, self.pair_concurrency_max, api,
        )


_plan: ResourcePlan | None = None


def get_resource_plan() -> ResourcePlan:
    """Return the singleton ResourcePlan, computing it on first call."""
    global _plan
    if _plan is None:
        _plan = ResourcePlan()
    return _plan
