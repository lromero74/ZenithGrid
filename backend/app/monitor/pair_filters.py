"""Trading-pair availability and category filtering.

Pure-ish DB helpers used by the monitor to decide which pairs a bot may trade:
which products are currently listed, and which pass the per-user/global coin
category filter. Extracted from multi_bot_monitor to keep that module under the
size limit.
"""

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_available_trading_products(db: AsyncSession) -> set[str]:
    """Return currently listed products, using the delisted-pair monitor cache."""
    from app.services.delisted_pair_monitor import trading_pair_monitor

    cached = getattr(trading_pair_monitor, "_available_products", set()) or set()
    if cached:
        return set(cached)
    return await trading_pair_monitor.get_available_products(db)


async def filter_pairs_by_allowed_categories(
    db: AsyncSession,
    trading_pairs: List[str],
    allowed_categories: Optional[List[str]] = None,
    user_id: Optional[int] = None,
) -> List[str]:
    """
    Filter trading pairs based on allowed coin categories from blacklist table.

    Args:
        db: Database session
        trading_pairs: List of pairs to filter (e.g., ["ETH-BTC", "ADA-BTC"])
        allowed_categories: List of allowed categories (e.g., ["APPROVED", "BORDERLINE"])
                          If None or empty, no filtering is applied.
        user_id: Optional user ID. If provided, per-user overrides take precedence
                 over global entries.

    Returns:
        Filtered list of trading pairs that match allowed categories
    """
    if not allowed_categories or len(allowed_categories) == 0:
        # No filtering - allow all pairs
        return trading_pairs

    from app.models import BlacklistedCoin

    # Extract base currencies from pairs
    base_currencies = set()
    pair_to_base = {}
    for pair in trading_pairs:
        if "-" in pair:
            base = pair.split("-")[0]
            base_currencies.add(base.upper())
            pair_to_base[pair] = base.upper()

    # Query blacklist table for these currencies (user_id IS NULL = global entries)
    query = select(BlacklistedCoin).where(
        BlacklistedCoin.symbol.in_(base_currencies),
        BlacklistedCoin.user_id.is_(None)
    )
    result = await db.execute(query)
    blacklist_entries = result.scalars().all()

    def _category_from_reason(reason: str) -> str:
        if reason.startswith("[APPROVED]"):
            return "APPROVED"
        elif reason.startswith("[BORDERLINE]"):
            return "BORDERLINE"
        elif reason.startswith("[QUESTIONABLE]"):
            return "QUESTIONABLE"
        elif reason.startswith("[MEME]"):
            return "MEME"
        return "BLACKLISTED"

    # Build map of currency -> category (global entries first)
    currency_categories = {}
    for entry in blacklist_entries:
        reason = entry.reason or ""
        currency_categories[entry.symbol] = _category_from_reason(reason)

    # Apply per-user overrides if user_id is provided
    if user_id is not None:
        override_query = select(BlacklistedCoin).where(
            BlacklistedCoin.symbol.in_(base_currencies),
            BlacklistedCoin.user_id == user_id,
        )
        override_result = await db.execute(override_query)
        for entry in override_result.scalars().all():
            reason = entry.reason or ""
            currency_categories[entry.symbol] = _category_from_reason(reason)

    # Filter pairs based on allowed categories
    filtered_pairs = []
    for pair in trading_pairs:
        base = pair_to_base.get(pair)
        if not base:
            continue

        category = currency_categories.get(base, "APPROVED")  # Default to APPROVED if not in blacklist
        if category in allowed_categories:
            filtered_pairs.append(pair)
        else:
            logger.debug(f"  Filtered out {pair}: {base} is {category}, not in allowed {allowed_categories}")

    if len(filtered_pairs) < len(trading_pairs):
        logger.info(
            f"  Category filter: {len(trading_pairs)} pairs → {len(filtered_pairs)} pairs "
            f"(allowed: {', '.join(allowed_categories)})"
        )

    return filtered_pairs
