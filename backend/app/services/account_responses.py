"""Shared response schemas and builders for account endpoints.

Used by both accounts_query_router and accounts_mutation_router. Moved here
from accounts_query_router to stop mutation_router from reaching into
another router's private helpers.
"""
from pydantic import BaseModel

from app.models import Account


class RebalanceSettingsResponse(BaseModel):
    """Portfolio rebalance settings for an account."""
    enabled: bool
    target_usd_pct: float
    target_btc_pct: float
    target_eth_pct: float
    target_usdc_pct: float
    target_usdt_pct: float
    drift_threshold_pct: float
    check_interval_minutes: int
    min_trade_pct: float
    min_balance_usd: float
    min_balance_btc: float
    min_balance_eth: float
    min_balance_usdc: float
    min_balance_usdt: float


def build_rebalance_response(account: Account) -> RebalanceSettingsResponse:
    """Build RebalanceSettingsResponse from an Account model instance."""
    return RebalanceSettingsResponse(
        enabled=account.rebalance_enabled or False,
        target_usd_pct=account.rebalance_target_usd_pct if account.rebalance_target_usd_pct is not None else 34.0,
        target_btc_pct=account.rebalance_target_btc_pct if account.rebalance_target_btc_pct is not None else 33.0,
        target_eth_pct=account.rebalance_target_eth_pct if account.rebalance_target_eth_pct is not None else 33.0,
        target_usdc_pct=account.rebalance_target_usdc_pct if account.rebalance_target_usdc_pct is not None else 0.0,
        target_usdt_pct=account.rebalance_target_usdt_pct if account.rebalance_target_usdt_pct is not None else 0.0,
        drift_threshold_pct=account.rebalance_drift_threshold_pct or 5.0,
        check_interval_minutes=account.rebalance_check_interval_minutes or 60,
        min_trade_pct=account.rebalance_min_trade_pct if account.rebalance_min_trade_pct is not None else 5.0,
        min_balance_usd=account.min_balance_usd or 0.0,
        min_balance_btc=account.min_balance_btc or 0.0,
        min_balance_eth=account.min_balance_eth or 0.0,
        min_balance_usdc=account.min_balance_usdc or 0.0,
        min_balance_usdt=account.min_balance_usdt or 0.0,
    )
