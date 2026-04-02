"""
Seasonality Service — business logic for seasonality-based bot management.

Extracted from seasonality_router.py. Contains:
- auto_manage_bots: disable/enable bots based on market cycle mode
- build_seasonality_response: assemble response dict from status + settings
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from app.services.season_detector import SeasonalityStatus

logger = logging.getLogger(__name__)


async def auto_manage_bots(
    bots: list,
    status: "SeasonalityStatus",
) -> Dict[str, int]:
    """
    Determine which bots to disable based on seasonality mode.

    Risk-Off mode: Disable BTC bots, keep USD bots
    Risk-On mode: Disable USD bots, keep BTC bots
    Grid bots are always exempt.

    Args:
        bots: List of active Bot objects to evaluate.
        status: Current SeasonalityStatus with mode field.

    Returns:
        Dict with disabled_btc and disabled_usd counts.
    """
    disabled_btc = 0
    disabled_usd = 0

    for bot in bots:
        # Grid bots are exempt from seasonality restrictions
        if bot.strategy_type == "grid_trading":
            continue

        quote_currency = bot.get_quote_currency()

        if status.mode == "risk_off" and quote_currency == "BTC":
            bot.is_active = False
            bot.updated_at = datetime.utcnow()
            disabled_btc += 1
            logger.info(f"Seasonality: Auto-disabled BTC bot '{bot.name}' (ID: {bot.id}) - Risk-Off mode")

        elif status.mode == "risk_on" and quote_currency == "USD":
            bot.is_active = False
            bot.updated_at = datetime.utcnow()
            disabled_usd += 1
            logger.info(f"Seasonality: Auto-disabled USD bot '{bot.name}' (ID: {bot.id}) - Risk-On mode")

    return {"disabled_btc": disabled_btc, "disabled_usd": disabled_usd}


def build_seasonality_response(
    status: "SeasonalityStatus",
    enabled: bool,
    last_transition: Optional[str],
) -> Dict[str, Any]:
    """Build the seasonality response dict from status and settings."""
    return {
        "enabled": enabled,
        "season": status.season_info.season,
        "season_name": status.season_info.name,
        "subtitle": status.season_info.subtitle,
        "description": status.season_info.description,
        "progress": status.season_info.progress,
        "confidence": status.season_info.confidence,
        "signals": status.season_info.signals,
        "mode": status.mode,
        "btc_bots_allowed": status.btc_bots_allowed if enabled else True,
        "usd_bots_allowed": status.usd_bots_allowed if enabled else True,
        "threshold_crossed": status.threshold_crossed,
        "last_transition": last_transition,
        "halving_days": status.season_info.halving_days,
        "cycle_position": status.season_info.cycle_position,
    }
