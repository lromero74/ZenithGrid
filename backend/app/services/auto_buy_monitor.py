"""
Auto-Buy BTC Monitor Service

Automatically converts stablecoins (USD, USDC, USDT) to BTC when balances
exceed configured minimums. Supports both market and limit orders with
automatic re-pricing for unfilled limit orders.

IMPORTANT: Respects bot reservations - only converts funds that are truly free
(not reserved by any bot's budget or tied up in open positions).
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import Account, Bot, Position
from app.services.exchange_service import get_exchange_client_for_account

logger = logging.getLogger(__name__)


@dataclass
class AutoBuyPendingOrder:
    """In-memory tracking for auto-buy limit orders (not stored in DB)."""
    order_id: str
    account_id: int
    product_id: str
    side: str
    size: float        # base currency amount (BTC)
    price: float       # limit price
    placed_at: datetime


class AutoBuyMonitor:
    """
    Background service that monitors accounts and auto-buys BTC with stablecoins.

    Features:
    - Per-account check intervals
    - Market or limit order placement
    - Automatic limit order re-pricing after 2 minutes
    - Tracks pending orders to avoid duplicates
    """

    def __init__(self):
        self.running = False
        self.task = None
        self._account_timers: Dict[int, datetime] = {}  # account_id -> last_check_time
        self._pending_orders: Dict[str, AutoBuyPendingOrder] = {}  # order_id -> order info

    async def start(self):
        """Start the auto-buy monitor"""
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._monitor_loop())
            logger.info("✅ Auto-Buy Monitor started")

    async def stop(self):
        """Stop the auto-buy monitor"""
        self.running = False
        if self.task:
            await self.task
        logger.info("🛑 Auto-Buy Monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop - checks every 10 seconds"""
        while self.running:
            try:
                await self._check_accounts()
                await self._check_pending_orders()
            except Exception as e:
                logger.error(f"Error in auto-buy monitor loop: {e}", exc_info=True)

            await asyncio.sleep(10)  # Check every 10 seconds

    async def _check_accounts(self):
        """Check which accounts need processing based on their intervals"""
        async with async_session_maker() as db:
            # Get all accounts with auto_buy_enabled=True
            query = select(Account).where(Account.auto_buy_enabled.is_(True))
            result = await db.execute(query)
            accounts = result.scalars().all()

            for account in accounts:
                if self._should_check_account(account):
                    await self._process_account(account, db)

    def _should_check_account(self, account: Account) -> bool:
        """Check if enough time has passed to process this account"""
        now = datetime.utcnow()
        last_check = self._account_timers.get(account.id)

        if not last_check:
            return True  # Never checked before

        interval_seconds = (account.auto_buy_check_interval_minutes or 5) * 60
        elapsed_seconds = (now - last_check).total_seconds()

        return elapsed_seconds >= interval_seconds

    async def _process_account(self, account: Account, db: AsyncSession):
        """Process one account - check balances and buy BTC if needed"""
        try:
            logger.info(f"Auto-buy: checking account '{account.name}' (id={account.id})")
            client = await get_exchange_client_for_account(db, account.id)
            if not client:
                logger.warning(f"Auto-buy: no exchange client for account {account.id}")
                return

            # Check each enabled stablecoin
            stablecoins = []
            if account.auto_buy_usd_enabled:
                stablecoins.append(("USD", account.auto_buy_usd_min, "BTC-USD"))
            if account.auto_buy_usdc_enabled:
                stablecoins.append(("USDC", account.auto_buy_usdc_min, "BTC-USDC"))
            if account.auto_buy_usdt_enabled:
                stablecoins.append(("USDT", account.auto_buy_usdt_min, "BTC-USDT"))

            for currency, min_amount, product_id in stablecoins:
                await self._check_and_buy(
                    client,
                    account,
                    currency,
                    min_amount,
                    product_id,
                    db
                )

            # Update timer for this account
            self._account_timers[account.id] = datetime.utcnow()

        except Exception as e:
            logger.error(f"Auto-buy failed for account {account.id}: {e}", exc_info=True)

    async def _calculate_reserved_usd(self, db: AsyncSession, account_id: int) -> float:
        """
        Calculate total USD reserved by bots and open positions for an account.
        This amount must NOT be auto-converted.
        """
        # Sum bot reservations (legacy fixed amounts)
        bots_result = await db.execute(
            select(Bot).where(Bot.account_id == account_id, Bot.is_active.is_(True))
        )
        active_bots = bots_result.scalars().all()

        reserved = 0.0
        for bot in active_bots:
            quote = bot.get_quote_currency()
            if quote == "USD":
                # Budget percentage-based or legacy fixed reservation
                reserved += bot.reserved_usd_balance or 0.0
            # Bidirectional bot long-side USD reservation
            reserved += bot.reserved_usd_for_longs or 0.0

        # Sum open position values in USD
        positions_result = await db.execute(
            select(Position).where(
                Position.status == "open",
                Position.account_id == account_id,
            )
        )
        open_positions = positions_result.scalars().all()

        for position in open_positions:
            pos_quote = position.get_quote_currency()
            if pos_quote in ("USD", "USDC", "USDT"):
                reserved += position.total_quote_spent or 0.0

        return reserved

    async def _check_and_buy(
        self,
        client,
        account: Account,
        currency: str,
        min_amount: float,
        product_id: str,
        db: AsyncSession
    ):
        """Check balance and buy BTC if above minimum, respecting bot reservations"""
        try:
            # Get available balance
            balance_data = await client.get_balance(currency)
            raw_available = float(balance_data.get('available', 0))

            # Subtract bot reservations and open position values
            reserved = await self._calculate_reserved_usd(db, account.id)
            available = max(0.0, raw_available - reserved)

            if available < min_amount:
                logger.info(
                    f"Auto-buy: {account.name} {currency} free={available:.2f} "
                    f"(raw={raw_available:.2f}, reserved={reserved:.2f}) < min {min_amount}"
                )
                return

            logger.info(
                f"🎯 Auto-buy triggered for {account.name}: {available:.2f} {currency} → BTC "
                f"(raw: {raw_available:.2f}, reserved: {reserved:.2f})"
            )

            # Determine order type
            order_type = account.auto_buy_order_type or "market"

            if order_type == "market":
                # Place market order
                result = await client.buy_with_usd(available, product_id)
                order_id = result.get('order_id')

                logger.info(
                    f"✅ Auto-buy market order placed: {available} {currency} → BTC "
                    f"(Account: {account.name}, Order: {order_id})"
                )

            else:  # limit order
                # Get current market price for limit order
                ticker = await client.get_product(product_id)
                current_price = float(ticker.get('price', 0))

                if current_price == 0:
                    logger.error(f"Could not get price for {product_id}")
                    return

                # Calculate BTC size
                btc_size = available / current_price

                # Place limit order at current market price
                result = await client.create_limit_order(
                    product_id=product_id,
                    side="BUY",
                    size=str(btc_size),
                    price=str(current_price)
                )

                order_id = result.get('order_id')

                # Track pending order in memory for re-pricing
                self._pending_orders[order_id] = AutoBuyPendingOrder(
                    order_id=order_id,
                    account_id=account.id,
                    product_id=product_id,
                    side="BUY",
                    size=btc_size,
                    price=current_price,
                    placed_at=datetime.utcnow(),
                )

                logger.info(
                    f"✅ Auto-buy limit order placed: {btc_size:.8f} BTC @ ${current_price:.2f} "
                    f"(Account: {account.name}, Order: {order_id})"
                )

        except Exception as e:
            logger.error(
                f"Error placing auto-buy order for {currency} on account {account.name}: {e}",
                exc_info=True
            )

    async def _check_pending_orders(self):
        """Check pending limit orders and re-price if needed (after 2 minutes)"""
        if not self._pending_orders:
            return

        async with async_session_maker() as db:
            now = datetime.utcnow()
            orders_to_remove = []

            for order_id, pending in list(self._pending_orders.items()):
                elapsed = (now - pending.placed_at).total_seconds()

                # Re-price after 2 minutes
                if elapsed >= 120:  # 2 minutes
                    await self._reprice_order(pending, db)
                    orders_to_remove.append(order_id)

            # Clean up processed orders
            for order_id in orders_to_remove:
                del self._pending_orders[order_id]

    async def _reprice_order(self, pending: AutoBuyPendingOrder, db: AsyncSession):
        """Cancel and replace a limit order at current market price"""
        try:
            # Get exchange client
            client = await get_exchange_client_for_account(db, pending.account_id)
            if not client:
                return

            # Check if order is still open
            order_status = await client.get_order(pending.order_id)
            if order_status.get('status') in ['FILLED', 'CANCELLED']:
                logger.debug(f"Order {pending.order_id} already {order_status.get('status')}")
                return

            # Cancel old order
            await client.cancel_order(pending.order_id)
            logger.info(f"🔄 Re-pricing auto-buy order {pending.order_id} (after 2 minutes)")

            # Get current market price
            ticker = await client.get_product(pending.product_id)
            new_price = float(ticker.get('price', 0))

            if new_price == 0:
                logger.error(f"Could not get price for {pending.product_id}")
                return

            # Place new limit order at current price
            result = await client.create_limit_order(
                product_id=pending.product_id,
                side=pending.side,
                size=str(pending.size),
                price=str(new_price)
            )

            new_order_id = result.get('order_id')

            # Track new order in memory
            self._pending_orders[new_order_id] = AutoBuyPendingOrder(
                order_id=new_order_id,
                account_id=pending.account_id,
                product_id=pending.product_id,
                side=pending.side,
                size=pending.size,
                price=new_price,
                placed_at=datetime.utcnow(),
            )

            logger.info(
                f"✅ Re-priced order: {pending.size:.8f} BTC @ ${new_price:.2f} "
                f"(Old: ${pending.price:.2f}, New Order: {new_order_id})"
            )

        except Exception as e:
            logger.error(f"Error re-pricing order {pending.order_id}: {e}", exc_info=True)
