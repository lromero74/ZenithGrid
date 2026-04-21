"""Seed data loaded by database.init_db() on startup.

Split per seed type as part of the code-quality Phase 5.1 modularization.
"""

from app.seeds.coin_categories import DEFAULT_COIN_CATEGORIES, seed_default_coins
from app.seeds.content_sources import (
    DEAD_SOURCES,
    DEFAULT_CONTENT_SOURCES,
    SOURCE_SCRAPE_POLICIES,
    seed_default_sources,
)

__all__ = [
    "DEAD_SOURCES",
    "DEFAULT_CONTENT_SOURCES",
    "DEFAULT_COIN_CATEGORIES",
    "SOURCE_SCRAPE_POLICIES",
    "seed_default_coins",
    "seed_default_sources",
]
