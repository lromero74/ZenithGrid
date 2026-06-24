"""
Portfolio Calculations — pure, side-effect-free helpers for building
portfolio holdings, PnL, and balance breakdowns.

Extracted from portfolio_service.py. No DB, cache, or API calls here.
"""

from dataclasses import dataclass


def _build_portfolio_holdings(
    spot_positions: list, btc_usd_price: float, open_positions: list = None
) -> tuple:
    """
    Build portfolio holdings list from Coinbase breakdown data.

    Args:
        spot_positions: Raw spot positions from Coinbase portfolio breakdown
        btc_usd_price: Current BTC-USD price
        open_positions: Open bot positions (for calculating "in deals" amounts)

    Returns:
        Tuple of (holdings, total_usd, total_btc, actual_usd, actual_usdc,
                  actual_btc, breakdown_prices)
    """
    # Pre-compute amount of each base currency held in open bot positions
    positions_by_base = {}
    if open_positions:
        for pos in open_positions:
            if pos.direction == "long":
                base = pos.get_base_currency()
                positions_by_base[base] = (
                    positions_by_base.get(base, 0.0) + (pos.total_base_acquired or 0.0)
                )

    portfolio_holdings = []
    total_usd_value = 0.0
    total_btc_value = 0.0
    actual_usd_balance = 0.0
    actual_usdc_balance = 0.0
    actual_btc_balance = 0.0

    # Price lookup derived from breakdown (for position PnL)
    breakdown_prices = {}

    for position in spot_positions:
        asset = position.get("asset", "")
        total_balance = float(position.get("total_balance_crypto", 0))
        in_positions = positions_by_base.get(asset, 0.0)
        available = max(0.0, total_balance - in_positions)
        hold = total_balance - float(position.get("available_to_trade_crypto", 0))

        if total_balance == 0:
            continue

        # Use Coinbase's pre-calculated fiat value
        usd_value = float(position.get("total_balance_fiat", 0))

        # Derive current price from fiat/crypto ratio
        if total_balance > 0 and usd_value > 0:
            current_price_usd = usd_value / total_balance
        elif asset == "USD":
            current_price_usd = 1.0
            usd_value = total_balance
        elif asset == "USDC":
            current_price_usd = 1.0
            usd_value = total_balance
        elif asset == "BTC":
            current_price_usd = btc_usd_price
            usd_value = total_balance * btc_usd_price
        else:
            current_price_usd = 0.0

        # Track actual quote currency balances
        if asset == "USD":
            actual_usd_balance += total_balance
        elif asset == "USDC":
            actual_usdc_balance += total_balance
        elif asset == "BTC":
            actual_btc_balance += total_balance

        # Store derived price for position PnL calculations
        if current_price_usd > 0:
            breakdown_prices[asset] = current_price_usd

        btc_value = usd_value / btc_usd_price if btc_usd_price > 0 else 0

        # Skip dust (< $0.01)
        if usd_value < 0.01 and current_price_usd > 0:
            continue

        total_usd_value += usd_value
        total_btc_value += btc_value

        portfolio_holdings.append({
            "asset": asset,
            "total_balance": total_balance,
            "available": available,
            "in_positions": in_positions,
            "hold": hold,
            "current_price_usd": current_price_usd,
            "usd_value": usd_value,
            "btc_value": btc_value,
            "percentage": 0.0,
            "unrealized_pnl_usd": 0.0,
            "unrealized_pnl_percentage": 0.0,
        })

    # Calculate percentages
    for holding in portfolio_holdings:
        if total_usd_value > 0:
            holding["percentage"] = (holding["usd_value"] / total_usd_value) * 100

    return (
        portfolio_holdings, total_usd_value, total_btc_value,
        actual_usd_balance, actual_usdc_balance, actual_btc_balance,
        breakdown_prices,
    )


def _compute_position_pnl(
    open_positions: list, breakdown_prices: dict, btc_usd_price: float
) -> dict:
    """
    Calculate unrealized PnL per asset from open positions.

    Uses prices derived from the portfolio breakdown — no additional API calls.

    Returns:
        Dict mapping asset name to {"pnl_usd": float, "cost_usd": float}.
    """
    asset_pnl = {}
    for position in open_positions:
        base = position.get_base_currency()
        quote = position.get_quote_currency()

        if quote == "USD":
            current_price = breakdown_prices.get(base)
        elif quote == "BTC":
            base_usd = breakdown_prices.get(base)
            if base_usd and btc_usd_price > 0:
                current_price = base_usd / btc_usd_price
            else:
                current_price = None
        else:
            current_price = None

        if current_price is None:
            continue

        current_value_quote = position.total_base_acquired * current_price
        profit_quote = current_value_quote - position.total_quote_spent

        if quote == "USD":
            profit_usd = profit_quote
            cost_usd = position.total_quote_spent
        elif quote == "BTC":
            profit_usd = profit_quote * btc_usd_price
            cost_usd = position.total_quote_spent * btc_usd_price
        else:
            continue

        if base not in asset_pnl:
            asset_pnl[base] = {"pnl_usd": 0.0, "cost_usd": 0.0}

        asset_pnl[base]["pnl_usd"] += profit_usd
        asset_pnl[base]["cost_usd"] += cost_usd

    return asset_pnl


@dataclass
class BalanceBreakdownParams:
    """Parameters for computing balance breakdown."""
    account_bots: list
    open_positions: list
    actual_btc: float
    actual_usd: float
    actual_usdc: float
    total_reserved_btc: float
    total_reserved_usd: float
    breakdown_prices: dict
    btc_usd_price: float


def _compute_balance_breakdown(params: BalanceBreakdownParams) -> dict:
    """
    Compute balance breakdown (total, reserved, in-positions, free) per quote currency.

    Returns:
        Dict with "btc", "usd", and "usdc" breakdown entries.
    """
    total_in_positions_btc = 0.0
    total_in_positions_usd = 0.0
    total_in_positions_usdc = 0.0

    for position in params.open_positions:
        quote = position.get_quote_currency()
        base = position.get_base_currency()

        # Derive position price from breakdown data
        if quote == "USD" or quote == "USDC":
            pos_price = params.breakdown_prices.get(base)
        elif quote == "BTC":
            base_usd = params.breakdown_prices.get(base)
            pos_price = (base_usd / params.btc_usd_price
                         if base_usd and params.btc_usd_price > 0 else None)
        else:
            pos_price = None

        if pos_price is not None:
            current_value = position.total_base_acquired * pos_price
        else:
            current_value = position.total_quote_spent

        if quote == "USD":
            total_in_positions_usd += current_value
        elif quote == "USDC":
            total_in_positions_usdc += current_value
        else:
            total_in_positions_btc += current_value

    total_btc_portfolio = params.actual_btc + total_in_positions_btc
    total_usd_portfolio = params.actual_usd + total_in_positions_usd
    total_usdc_portfolio = params.actual_usdc + total_in_positions_usdc

    free_btc = max(0.0, total_btc_portfolio - (params.total_reserved_btc + total_in_positions_btc))
    free_usd = max(0.0, total_usd_portfolio - (params.total_reserved_usd + total_in_positions_usd))
    free_usdc = max(0.0, total_usdc_portfolio - total_in_positions_usdc)

    return {
        "btc": {
            "total": total_btc_portfolio,
            "reserved_by_bots": params.total_reserved_btc,
            "in_open_positions": total_in_positions_btc,
            "free": free_btc,
        },
        "usd": {
            "total": total_usd_portfolio,
            "reserved_by_bots": params.total_reserved_usd,
            "in_open_positions": total_in_positions_usd,
            "free": free_usd,
        },
        "usdc": {
            "total": total_usdc_portfolio,
            "reserved_by_bots": 0.0,
            "in_open_positions": total_in_positions_usdc,
            "free": free_usdc,
        },
    }


# Currencies that already have their own row in the Balances table (shown as
# Budget / In Pos. / In Grids / Available). Coins outside this set that sit in the
# wallet without backing an open position are "untracked".
_BALANCE_TABLE_ROWS = frozenset({"BTC", "ETH", "USD", "USDC", "USDT"})


def compute_untracked_usd(holdings: list) -> float:
    """USD value of wallet coins not backed by an open position.

    These are holdings (excluding the BTC/ETH/stablecoin rows the Balances table
    already shows) whose wallet balance exceeds what open positions account for —
    e.g. leftovers from a closed/partial sell or pre-existing coins. This is the
    surplus that makes Account Value exceed cost-basis "In Pos." + Available, so
    surfacing it lets the Balances panel reconcile.

    Each holding is expected to have ``asset``, ``total_balance``, ``in_positions``
    (base units already in open positions), and ``usd_value`` (market value).
    """
    total = 0.0
    for h in holdings:
        if h.get("asset") in _BALANCE_TABLE_ROWS:
            continue
        balance = h.get("total_balance") or 0.0
        if balance <= 0:
            continue
        in_positions = h.get("in_positions") or 0.0
        surplus_fraction = max(0.0, (balance - in_positions) / balance)
        total += (h.get("usd_value") or 0.0) * surplus_fraction
    return total


def aggregate_pnl_rows(rows) -> tuple:
    """
    Bucket pre-aggregated closed-PnL sums into usd/btc/usdc.

    ``rows`` come from a ``GROUP BY product_id`` SQL aggregate, so each row is
    ``(product_id, all_time_sum, today_sum)`` — one row per distinct trading pair,
    NOT one per closed position. This keeps the cost proportional to the number of
    pairs an account trades rather than its entire (unbounded) trade history.

    The quote-currency derivation mirrors ``Position.get_quote_currency()``
    (quote = the part after '-', default 'BTC'); unknown quotes bucket into "usd".

    Returns:
        Tuple of (pnl_all_time, pnl_today) dicts, each with "usd", "btc", "usdc" keys.
    """
    pnl_all_time = {"usd": 0.0, "btc": 0.0, "usdc": 0.0}
    pnl_today = {"usd": 0.0, "btc": 0.0, "usdc": 0.0}

    for product_id, all_time_sum, today_sum in rows:
        quote = product_id.split("-")[1] if product_id and "-" in product_id else "BTC"
        quote_key = quote.lower() if quote in ("USD", "BTC", "USDC") else "usd"
        pnl_all_time[quote_key] += float(all_time_sum or 0.0)
        pnl_today[quote_key] += float(today_sum or 0.0)

    return pnl_all_time, pnl_today


def _apply_asset_pnl_to_holdings(holdings: list, asset_pnl: dict) -> None:
    """Apply a pre-computed asset_pnl dict (from _compute_position_pnl) to holdings, in place.

    Both callers in portfolio_service used the same inline loop; this factors it out so the
    two call paths stay in lock-step.
    """
    for holding in holdings:
        asset = holding["asset"]
        if asset in asset_pnl:
            pnl_data = asset_pnl[asset]
            holding["unrealized_pnl_usd"] = pnl_data["pnl_usd"]
            if pnl_data["cost_usd"] > 0:
                holding["unrealized_pnl_percentage"] = (
                    pnl_data["pnl_usd"] / pnl_data["cost_usd"]
                ) * 100
