#!/usr/bin/env python3
"""Backfill exchange fees and fee-net P&L for one account. Dry-run by default."""

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


async def main(account_id: int, commit: bool) -> None:
    from app.database import async_session_maker
    from app.models import Position, Trade
    from app.services.exchange_service import get_exchange_client_for_account
    from app.services.pnl_service import calculate_realized_spot_profit

    async with async_session_maker() as db:
        client = await get_exchange_client_for_account(db, account_id, use_cache=False)
        positions = (await db.execute(select(Position).where(
            Position.account_id == account_id,
            Position.product_type == "spot",
            Position.direction == "long",
        ))).scalars().all()
        position_ids = [position.id for position in positions]
        trades = (await db.execute(select(Trade).where(
            Trade.position_id.in_(position_ids),
            Trade.order_id.isnot(None),
            Trade.order_id != "",
        ))).scalars().all() if position_ids else []

        by_order = {}
        for trade in trades:
            by_order.setdefault(trade.order_id, []).append(trade)

        for order_id, order_trades in by_order.items():
            order = await client.get_order(order_id)
            filled_size = float(order.get("filled_size", 0) or 0)
            total_fees = float(order.get("total_fees", 0) or 0)
            if filled_size <= 0:
                continue
            for trade in order_trades:
                trade.fee_quote = total_fees * (trade.base_amount / filled_size)

        trades_by_position = {}
        for trade in trades:
            trades_by_position.setdefault(trade.position_id, []).append(trade)

        for position in positions:
            position_trades = trades_by_position.get(position.id, [])
            position.entry_fees_quote = sum(t.fee_quote or 0.0 for t in position_trades if t.side == "buy")
            position.exit_fees_quote = sum(t.fee_quote or 0.0 for t in position_trades if t.side == "sell")
            if position.status != "closed":
                continue
            position.total_quote_received = sum(t.quote_amount for t in position_trades if t.side == "sell")
            position.profit_quote, position.profit_percentage = calculate_realized_spot_profit(
                position.total_quote_spent, position.total_quote_received,
                position.entry_fees_quote, position.exit_fees_quote,
            )
            quote_currency = position.product_id.rsplit("-", 1)[-1]
            if quote_currency in {"USD", "USDC", "USDT"}:
                position.profit_usd = position.profit_quote
            elif position.btc_usd_price_at_close:
                position.profit_usd = position.profit_quote * position.btc_usd_price_at_close

        print(f"Account {account_id}: {len(trades)} trades, {len(positions)} positions")
        if commit:
            await db.commit()
            print("Committed fee backfill")
        else:
            await db.rollback()
            print("Dry run only; pass --yes to commit")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("account_id", type=int)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.account_id, args.yes))
