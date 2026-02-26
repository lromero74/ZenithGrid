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
            converted_via_usd = []
            converted_via_btc = []

            logger.info(
                f"Task {task_id}: Starting portfolio conversion: "
                f"{total_to_process} currencies to process"
            )

            for idx, item in enumerate(currencies_to_sell, 1):
                currency = item["currency"]
                available = item["available"]

                try:
                    if target_currency == "BTC":
                        product_id = f"{currency}-BTC"
                        try:
                            await exchange.create_market_order(
                                product_id=product_id, side="SELL",
                                size=str(available),
                            )
                            sold_count += 1
                            await asyncio.sleep(0.2)
                        except Exception as direct_error:
                            if "403" in str(direct_error) or "400" in str(direct_error):
                                usd_product_id = f"{currency}-USD"
                                await exchange.create_market_order(
                                    product_id=usd_product_id, side="SELL",
                                    size=str(available),
                                )
                                converted_via_usd.append(currency)
                                sold_count += 1
                                await asyncio.sleep(0.2)
                            else:
                                raise direct_error
                    else:
                        product_id = f"{currency}-USD"
                        try:
                            await exchange.create_market_order(
                                product_id=product_id, side="SELL",
                                size=str(available),
                            )
                            sold_count += 1
                            await asyncio.sleep(0.2)
                        except Exception as direct_error:
                            if "403" in str(direct_error) or "400" in str(direct_error):
                                btc_product_id = f"{currency}-BTC"
                                await exchange.create_market_order(
                                    product_id=btc_product_id, side="SELL",
                                    size=str(available),
                                )
                                converted_via_btc.append(currency)
                                sold_count += 1
                                await asyncio.sleep(0.2)
                            else:
                                raise direct_error

                except Exception as e:
                    failed_count += 1
                    errors.append(f"{currency} ({available:.8f}): {str(e)}")
                    logger.error(f"[{idx}/{total_to_process}] Failed to sell {currency}: {e}")

                update_task_progress(
                    task_id, current=idx, sold_count=sold_count,
                    failed_count=failed_count, errors=errors,
                    message=f"Processing {idx}/{total_to_process} currencies..."
                )

            # Convert intermediate currency
            if target_currency == "BTC" and converted_via_usd:
                update_task_progress(task_id, message="Converting USD to BTC...")
                await asyncio.sleep(1.0)
                try:
                    accounts = await exchange.get_accounts(force_fresh=True)
                    usd_account = next(
                        (acc for acc in accounts if acc.get("currency") == "USD"), None
                    )
                    if usd_account:
                        usd_available = float(
                            usd_account.get("available_balance", {}).get("value", "0")
                        )
                        if usd_available > 1.0:
                            spend_amount = round(usd_available * 0.99, 2)
                            await exchange.create_market_order(
                                product_id="BTC-USD", side="BUY",
                                funds=str(spend_amount),
                            )
                except Exception as e:
                    logger.error(f"Failed to convert USD to BTC: {e}")
                    errors.append(f"USD-to-BTC conversion: {str(e)}")

            if target_currency == "USD" and converted_via_btc:
                update_task_progress(task_id, message="Converting BTC to USD...")
                await asyncio.sleep(1.0)
                try:
                    accounts = await exchange.get_accounts(force_fresh=True)
                    btc_account = next(
                        (acc for acc in accounts if acc.get("currency") == "BTC"), None
                    )
                    if btc_account:
                        btc_available = float(
                            btc_account.get("available_balance", {}).get("value", "0")
                        )
                        if btc_available > 0.00001:
                            await exchange.create_market_order(
                                product_id="BTC-USD", side="SELL",
                                size=str(btc_available),
                            )
                except Exception as e:
                    logger.error(f"Failed to convert BTC to USD: {e}")
                    errors.append(f"BTC-to-USD conversion: {str(e)}")

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
