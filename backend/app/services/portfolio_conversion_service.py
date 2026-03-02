"""
Portfolio conversion service with progress tracking and execution.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from app.services.exchange_service import get_exchange_client_for_account

logger = logging.getLogger(__name__)

# In-memory storage for conversion progress
# Key: task_id, Value: progress dict
_conversion_tasks: Dict[str, Dict] = {}


def get_task_progress(task_id: str) -> Optional[Dict]:
    """Get progress for a conversion task"""
    return _conversion_tasks.get(task_id)


def update_task_progress(
    task_id: str,
    total: int = None,
    current: int = None,
    status: str = None,
    message: str = None,
    sold_count: int = None,
    failed_count: int = None,
    errors: List[str] = None,
):
    """Update progress for a conversion task"""
    if task_id not in _conversion_tasks:
        _conversion_tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "total": 0,
            "current": 0,
            "sold_count": 0,
            "failed_count": 0,
            "errors": [],
            "message": "",
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
        }

    task = _conversion_tasks[task_id]

    if total is not None:
        task["total"] = total
    if current is not None:
        task["current"] = current
    if status is not None:
        task["status"] = status
    if message is not None:
        task["message"] = message
    if sold_count is not None:
        task["sold_count"] = sold_count
    if failed_count is not None:
        task["failed_count"] = failed_count
    if errors is not None:
        task["errors"] = errors

    if status == "completed" or status == "failed":
        task["completed_at"] = datetime.utcnow().isoformat()

    # Calculate progress percentage
    if task["total"] > 0:
        task["progress_pct"] = int((task["current"] / task["total"]) * 100)
    else:
        task["progress_pct"] = 0


def cleanup_old_tasks():
    """Clean up tasks older than 1 hour"""
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(hours=1)
    to_remove = []

    for task_id, task in _conversion_tasks.items():
        if task.get("completed_at"):
            completed = datetime.fromisoformat(task["completed_at"])
            if completed < cutoff:
                to_remove.append(task_id)

    for task_id in to_remove:
        del _conversion_tasks[task_id]
        logger.info(f"Cleaned up old conversion task: {task_id}")


async def _sell_currency_with_fallback(
    exchange, currency: str, available: float,
    target_currency: str,
) -> str:
    """Sell a currency to target, falling back to intermediate pair if direct fails.

    Returns:
        "direct" if sold directly, "intermediate" if sold via fallback pair.

    Raises:
        Exception if both direct and fallback fail.
    """
    if target_currency == "BTC":
        primary_pair = f"{currency}-BTC"
        fallback_pair = f"{currency}-USD"
    else:
        primary_pair = f"{currency}-USD"
        fallback_pair = f"{currency}-BTC"

    try:
        await exchange.create_market_order(
            product_id=primary_pair, side="SELL", size=str(available),
        )
        await asyncio.sleep(0.2)
        return "direct"
    except Exception as direct_error:
        if "403" in str(direct_error) or "400" in str(direct_error):
            await exchange.create_market_order(
                product_id=fallback_pair, side="SELL", size=str(available),
            )
            await asyncio.sleep(0.2)
            return "intermediate"
        raise


async def _convert_intermediate_currency(
    exchange, from_currency: str, to_currency: str,
    errors: List[str],
) -> None:
    """Convert accumulated intermediate currency to the final target."""
    await asyncio.sleep(1.0)
    try:
        accounts = await exchange.get_accounts(force_fresh=True)
        account = next(
            (acc for acc in accounts if acc.get("currency") == from_currency),
            None,
        )
        if not account:
            return

        available = float(
            account.get("available_balance", {}).get("value", "0")
        )
        min_amounts = {"USD": 1.0, "BTC": 0.00001}
        if available <= min_amounts.get(from_currency, 0):
            return

        if from_currency == "USD":
            spend_amount = round(available * 0.99, 2)
            await exchange.create_market_order(
                product_id="BTC-USD", side="BUY", funds=str(spend_amount),
            )
        else:
            await exchange.create_market_order(
                product_id="BTC-USD", side="SELL", size=str(available),
            )
    except Exception as e:
        logger.error(f"Failed to convert {from_currency} to {to_currency}: {e}")
        errors.append(f"{from_currency}-to-{to_currency} conversion: {str(e)}")


async def run_portfolio_conversion(
    task_id: str,
    account_id: int,
    target_currency: str,
    user_id: int,
):
    """Background task to convert portfolio to target currency."""
    from app.database import get_db

    try:
        update_task_progress(task_id, status="running", message="Initializing conversion...")

        async for db in get_db():
            exchange = await get_exchange_client_for_account(db, account_id)
            if not exchange:
                update_task_progress(
                    task_id, status="failed",
                    message=f"No exchange client for account {account_id}"
                )
                return

            update_task_progress(task_id, message="Fetching account balances...")
            try:
                all_accounts = await exchange.get_accounts(force_fresh=True)
            except Exception as e:
                update_task_progress(
                    task_id, status="failed",
                    message=f"Failed to fetch account balances: {str(e)}"
                )
                return

            currencies_to_sell = []
            for acc in all_accounts:
                currency = acc.get("currency")
                available_str = acc.get("available_balance", {}).get("value", "0")
                available = float(available_str)

                if currency == target_currency or available <= 0:
                    continue
                if currency == "USD" and available < 0.50:
                    continue
                if currency == "BTC" and available < 0.00001:
                    continue

                currencies_to_sell.append({
                    "currency": currency,
                    "available": available,
                })

            if not currencies_to_sell:
                update_task_progress(
                    task_id, status="completed",
                    message=f"Portfolio already in {target_currency}",
                    total=0, current=0
                )
                return

            total_to_process = len(currencies_to_sell)
            update_task_progress(
                task_id, total=total_to_process, current=0,
                message=f"Converting {total_to_process} currencies..."
            )

            sold_count = 0
            failed_count = 0
            errors = []
            used_intermediate = {"USD": [], "BTC": []}

            logger.info(
                f"Task {task_id}: Starting portfolio conversion: "
                f"{total_to_process} currencies to process"
            )

            for idx, item in enumerate(currencies_to_sell, 1):
                currency = item["currency"]
                available = item["available"]

                try:
                    result = await _sell_currency_with_fallback(
                        exchange, currency, available, target_currency,
                    )
                    sold_count += 1
                    if result == "intermediate":
                        # Track which intermediate currency was used
                        if target_currency == "BTC":
                            used_intermediate["USD"].append(currency)
                        else:
                            used_intermediate["BTC"].append(currency)
                except Exception as e:
                    failed_count += 1
                    errors.append(f"{currency} ({available:.8f}): {str(e)}")
                    logger.error(f"[{idx}/{total_to_process}] Failed to sell {currency}: {e}")

                update_task_progress(
                    task_id, current=idx, sold_count=sold_count,
                    failed_count=failed_count, errors=errors,
                    message=f"Processing {idx}/{total_to_process} currencies..."
                )

            # Convert intermediate currency to final target
            if target_currency == "BTC" and used_intermediate["USD"]:
                update_task_progress(task_id, message="Converting USD to BTC...")
                await _convert_intermediate_currency(exchange, "USD", "BTC", errors)

            if target_currency == "USD" and used_intermediate["BTC"]:
                update_task_progress(task_id, message="Converting BTC to USD...")
                await _convert_intermediate_currency(exchange, "BTC", "USD", errors)

            success_rate = (
                f"{int((sold_count / total_to_process) * 100)}%"
                if total_to_process > 0 else "0%"
            )
            update_task_progress(
                task_id, status="completed",
                message=f"Conversion complete: {sold_count}/{total_to_process} sold ({success_rate})",
                sold_count=sold_count, failed_count=failed_count, errors=errors
            )

            logger.warning(
                f"Task {task_id}: PORTFOLIO CONVERSION completed: "
                f"{sold_count}/{total_to_process} sold, {failed_count} failed"
            )
            break

    except Exception as e:
        logger.error(f"Task {task_id} failed with error: {e}")
        update_task_progress(
            task_id, status="failed",
            message=f"Conversion failed: {str(e)}"
        )
