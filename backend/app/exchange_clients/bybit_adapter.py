"""
ByBit Adapter

Implements the ExchangeClient ABC for ByBit V5 (HyroTrader / prop firms).
All orders go as linear perpetual (category="linear") - USDT perps.
Wraps ByBitClient and normalizes responses to match ZenithGrid conventions.
"""

import logging
from typing import Any, Dict, List, Optional

from app.exchange_clients.base import ExchangeClient
from app.exchange_clients.bybit_client import (
    ByBitClient,
    from_bybit_symbol,
    to_bybit_symbol,
)

logger = logging.getLogger(__name__)


class ByBitAdapter(ExchangeClient):
    """
    ExchangeClient implementation for ByBit V5 (unified account).

    - All trades use category="linear" (USDT linear perpetuals)
    - closeOnTrigger=True on stop-loss orders
    - Position mode: one-way by default (configurable)
    """

    def __init__(
        self,
        client: ByBitClient,
        position_mode: str = "one_way",
    ):
        self._client = client
        self._position_mode = position_mode
        self._balance_cache: Optional[dict] = None

    # ==========================================================
    # ACCOUNT & BALANCE
    # ==========================================================

    async def get_accounts(
        self, force_fresh: bool = False
    ) -> List[Dict[str, Any]]:
        if force_fresh:
            self._balance_cache = None

        resp = await self._client.get_wallet_balance()
        accounts = []
        result = resp.get("result", {})
        for acct in result.get("list", []):
            for coin_info in acct.get("coin", []):
                accounts.append({
                    "uuid": f"bybit-{coin_info.get('coin', '')}",
                    "currency": coin_info.get("coin", ""),
                    "available_balance": {
                        "value": coin_info.get(
                            "availableToWithdraw", "0"
                        ),
                        "currency": coin_info.get("coin", ""),
                    },
                    "hold": {
                        "value": coin_info.get("locked", "0"),
                        "currency": coin_info.get("coin", ""),
                    },
                })
        self._balance_cache = accounts
        return accounts

    async def get_account(self, account_id: str) -> Dict[str, Any]:
        accounts = await self.get_accounts()
        for acct in accounts:
            if acct["uuid"] == account_id:
                return acct
        return {}

    async def _get_coin_available(self, coin: str) -> float:
        """Get available balance for a specific coin."""
        resp = await self._client.get_coin_balance(coin)
        result = resp.get("result", {})
        for acct in result.get("list", []):
            for coin_info in acct.get("coin", []):
                if coin_info.get("coin", "").upper() == coin.upper():
                    return float(
                        coin_info.get("availableToWithdraw", "0")
                    )
        return 0.0

    async def get_btc_balance(self) -> float:
        return await self._get_coin_available("BTC")

    async def get_eth_balance(self) -> float:
        return await self._get_coin_available("ETH")

    async def get_usd_balance(self) -> float:
        return await self._get_coin_available("USDT")

    async def get_balance(self, currency: str) -> Dict[str, Any]:
        available = await self._get_coin_available(currency)
        return {
            "currency": currency,
            "available": str(available),
            "hold": "0.00",
        }

    async def invalidate_balance_cache(self):
        self._balance_cache = None

    async def calculate_aggregate_btc_value(
        self, bypass_cache: bool = False
    ) -> float:
        """Calculate total portfolio value in BTC.

        Uses ByBit's totalEquity (includes unrealized PnL from
        open positions) converted to BTC via current price.
        """
        if bypass_cache:
            self._balance_cache = None

        # totalEquity is in USD and includes unrealized PnL
        total_equity_usd = await self.get_equity()
        if total_equity_usd > 0:
            btc_price = await self.get_btc_usd_price()
            if btc_price > 0:
                return total_equity_usd / btc_price
        return 0.0

    async def calculate_aggregate_usd_value(self) -> float:
        """Calculate total portfolio value in USD.

        Uses ByBit's totalEquity which already includes all coin
        balances plus unrealized PnL from open positions.
        """
        return await self.get_equity()

    async def calculate_aggregate_quote_value(
        self, quote_currency: str, bypass_cache: bool = False
    ) -> float:
        """Bybit is USDT-settled — return equity for USDT, 0 otherwise."""
        if quote_currency == "USDT":
            return await self.get_equity()
        return 0.0

    # ==========================================================
    # MARKET DATA
    # ==========================================================

    async def list_products(self) -> List[Dict[str, Any]]:
        resp = await self._client.get_instruments_info(category="linear")
        result = resp.get("result", {})
        products = []
        for item in result.get("list", []):
            symbol = item.get("symbol", "")
            product_id = from_bybit_symbol(symbol)
            lot_filter = item.get("lotSizeFilter", {})
            price_filter = item.get("priceFilter", {})
            # Normalize quote currency: USDT→USD for system compat
            raw_quote = item.get("quoteCoin", "")
            quote_currency = "USD" if raw_quote == "USDT" else raw_quote
            base_coin = item.get("baseCoin", "")
            raw_status = item.get("status", "")
            # Normalize status: ByBit uses "Trading", Coinbase uses "online"
            status = "online" if raw_status == "Trading" else raw_status
            products.append({
                "product_id": product_id,
                "base_currency": base_coin,
                "base_currency_id": base_coin,  # Alias for Coinbase compat
                "quote_currency": quote_currency,
                "quote_currency_id": quote_currency,  # Alias
                "base_min_size": lot_filter.get("minOrderQty", "0"),
                "base_max_size": lot_filter.get("maxOrderQty", "0"),
                "quote_min_size": price_filter.get(
                    "minNotionalValue", "10"
                ),
                "base_increment": lot_filter.get("qtyStep", "0"),
                "quote_increment": price_filter.get(
                    "tickSize", "0.01"
                ),
                "status": status,
                "display_name": product_id,
            })
        return products

    async def get_product(
        self, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        symbol = to_bybit_symbol(product_id)
        resp = await self._client.get_instruments_info(
            category="linear", symbol=symbol
        )
        result = resp.get("result", {})
        items = result.get("list", [])
        if items:
            item = items[0]
            lot_filter = item.get("lotSizeFilter", {})
            price_filter = item.get("priceFilter", {})
            raw_quote = item.get("quoteCoin", "")
            quote_currency = "USD" if raw_quote == "USDT" else raw_quote
            base_coin = item.get("baseCoin", "")
            raw_status = item.get("status", "")
            status = "online" if raw_status == "Trading" else raw_status
            return {
                "product_id": product_id,
                "base_currency": base_coin,
                "base_currency_id": base_coin,
                "quote_currency": quote_currency,
                "quote_currency_id": quote_currency,
                "base_min_size": lot_filter.get("minOrderQty", "0"),
                "base_max_size": lot_filter.get("maxOrderQty", "0"),
                "quote_min_size": price_filter.get(
                    "minNotionalValue", "10"
                ),
                "base_increment": lot_filter.get("qtyStep", "0"),
                "quote_increment": price_filter.get(
                    "tickSize", "0.01"
                ),
                "status": status,
                "display_name": product_id,
            }
        return {"product_id": product_id}

    async def get_ticker(
        self, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        symbol = to_bybit_symbol(product_id)
        resp = await self._client.get_tickers(
            category="linear", symbol=symbol
        )
        result = resp.get("result", {})
        items = result.get("list", [])
        if items:
            t = items[0]
            bid = t.get("bid1Price", "0")
            ask = t.get("ask1Price", "0")
            return {
                "product_id": product_id,
                "price": t.get("lastPrice", "0"),
                "bid": bid,
                "ask": ask,
                "best_bid": bid,
                "best_ask": ask,
                "volume": t.get("volume24h", "0"),
                "high_24h": t.get("highPrice24h", "0"),
                "low_24h": t.get("lowPrice24h", "0"),
                "open": t.get("prevPrice24h", "0"),
            }
        return {"product_id": product_id, "price": "0"}

    async def get_current_price(
        self, product_id: str = "ETH-BTC"
    ) -> float:
        ticker = await self.get_ticker(product_id)
        return float(ticker.get("price", 0))

    async def get_btc_usd_price(self) -> float:
        # Uses BTC-USD which to_bybit_symbol maps to BTCUSDT
        return await self.get_current_price("BTC-USD")

    async def get_eth_usd_price(self) -> float:
        # Uses ETH-USD which to_bybit_symbol maps to ETHUSDT
        return await self.get_current_price("ETH-USD")

    async def get_product_stats(
        self, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        ticker = await self.get_ticker(product_id)
        return {
            "open": ticker.get("open", ticker.get("price", "0")),
            "high": ticker.get("high_24h", "0"),
            "low": ticker.get("low_24h", "0"),
            "last": ticker.get("price", "0"),
            "volume": ticker.get("volume", "0"),
        }

    async def get_candles(
        self,
        product_id: str,
        start: int,
        end: int,
        granularity: str,
    ) -> List[Dict[str, Any]]:
        symbol = to_bybit_symbol(product_id)
        interval = self._client.map_granularity(granularity)
        resp = await self._client.get_kline(
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            category="linear",
        )
        result = resp.get("result", {})
        raw = result.get("list", [])
        return self._client.normalize_candles(raw)

    # ==========================================================
    # ORDER EXECUTION
    # ==========================================================

    async def create_market_order(
        self,
        product_id: str,
        side: str,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        symbol = to_bybit_symbol(product_id)

        # For market orders, ByBit needs qty (base amount)
        qty = size
        if not qty and funds:
            # Convert funds (quote) to size (base) using current price
            price = await self.get_current_price(product_id)
            if price > 0:
                qty = str(float(funds) / price)
            else:
                raise ValueError(
                    f"Cannot determine qty: price is 0 for {product_id}"
                )

        if not qty:
            raise ValueError("Either size or funds must be provided")

        resp = await self._client.place_order(
            symbol=symbol,
            side=side.upper(),
            order_type="Market",
            qty=qty,
            category="linear",
        )

        result = resp.get("result", {})
        order_id = result.get("orderId", "")

        # Fetch order details for fill info
        fill_info = await self._get_order_fill_info(
            symbol, order_id
        )

        # Don't use qty as fallback for filled_size — that would
        # hide partial fills.  The executors will fetch actual fill
        # data via get_order() with retries.
        filled_size = fill_info.get("filled_size", "0")
        filled_value = fill_info.get("filled_value", "0")
        avg_price = fill_info.get("avg_price", "0")

        # Wrap in standard format so buy/sell executors can read
        # success_response.order_id consistently
        return {
            "success": True,
            "success_response": {
                "order_id": order_id,
                "product_id": product_id,
                "side": side.upper(),
            },
            "order_id": order_id,
            "product_id": product_id,
            "side": side.upper(),
            "filled_size": filled_size,
            "filled_value": filled_value,
            "average_filled_price": avg_price,
        }

    async def create_limit_order(
        self,
        product_id: str,
        side: str,
        limit_price: float,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        symbol = to_bybit_symbol(product_id)

        qty = size
        if not qty and funds:
            qty = str(float(funds) / limit_price)

        if not qty:
            raise ValueError("Either size or funds must be provided")

        resp = await self._client.place_order(
            symbol=symbol,
            side=side.upper(),
            order_type="Limit",
            qty=qty,
            price=str(limit_price),
            category="linear",
        )

        result = resp.get("result", {})
        order_id = result.get("orderId", "")

        # Wrap in Coinbase-compatible format for executor consistency
        return {
            "success": True,
            "success_response": {
                "order_id": order_id,
                "product_id": product_id,
                "side": side.upper(),
            },
            "order_id": order_id,
            "product_id": product_id,
            "side": side.upper(),
            "type": "limit",
            "limit_price": str(limit_price),
            "size": qty,
        }

    async def _get_order_fill_info(
        self, symbol: str, order_id: str
    ) -> dict:
        """Get fill details for a completed order.

        Returns dict with filled_size, filled_value, avg_price, status.
        On error, returns a dict with explicit "0" values so callers
        can distinguish "no data" from "zero fill".
        """
        empty = {
            "filled_size": "0",
            "filled_value": "0",
            "avg_price": "0",
            "status": "UNKNOWN",
            "fill_fetch_failed": True,
        }
        try:
            resp = await self._client.get_order_history(
                category="linear",
                symbol=symbol,
                order_id=order_id,
            )
            result = resp.get("result", {})
            orders = result.get("list", [])
            if orders:
                order = orders[0]
                return {
                    "filled_size": order.get("cumExecQty", "0"),
                    "filled_value": order.get("cumExecValue", "0"),
                    "avg_price": order.get("avgPrice", "0"),
                    "status": order.get("orderStatus", ""),
                }
            logger.warning(
                f"No order found in history for {order_id}"
            )
            return empty
        except Exception as e:
            logger.warning(
                f"Failed to get fill info for {order_id}: {e}"
            )
            return empty

    @staticmethod
    def _normalize_order_status(bybit_status: str) -> str:
        """Map ByBit PascalCase order statuses to uppercase.

        ByBit V5 returns: New, PartiallyFilled, Filled, Cancelled,
        Rejected, Deactivated, Untriggered, Triggered.
        """
        mapping = {
            "New": "OPEN",
            "PartiallyFilled": "OPEN",
            "Filled": "FILLED",
            "Cancelled": "CANCELLED",
            "Rejected": "FAILED",
            "Deactivated": "CANCELLED",
            "Untriggered": "PENDING",
            "Triggered": "OPEN",
        }
        return mapping.get(bybit_status, bybit_status.upper())

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        resp = await self._client.get_order_history(
            category="linear", order_id=order_id
        )
        result = resp.get("result", {})
        orders = result.get("list", [])
        if orders:
            order = orders[0]
            # Extract fees: ByBit V5 uses cumExecFee for linear
            # (cumFeeDetail is newer but cumExecFee still works)
            total_fees = order.get("cumExecFee", "0")
            return {
                "order_id": order.get("orderId", ""),
                "product_id": from_bybit_symbol(
                    order.get("symbol", "")
                ),
                "side": order.get("side", "").upper(),
                "type": order.get("orderType", ""),
                "status": self._normalize_order_status(
                    order.get("orderStatus", "")
                ),
                "filled_size": order.get("cumExecQty", "0"),
                "filled_value": order.get("cumExecValue", "0"),
                "average_filled_price": order.get("avgPrice", "0"),
                "total_fees": total_fees,
                "created_time": order.get("createdTime", ""),
            }
        return {"order_id": order_id, "status": "UNKNOWN"}

    async def edit_order(
        self,
        order_id: str,
        price: Optional[str] = None,
        size: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Edit order via ByBit's amend_order API."""
        # Find symbol from open orders
        open_resp = await self._client.get_open_orders(
            category="linear"
        )
        result = open_resp.get("result", {})
        symbol = None
        for order in result.get("list", []):
            if order.get("orderId") == order_id:
                symbol = order.get("symbol")
                break

        if not symbol:
            raise ValueError(
                f"Order {order_id} not found in open orders"
            )

        kwargs: Dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "orderId": order_id,
        }
        if price is not None:
            kwargs["price"] = price
        if size is not None:
            kwargs["qty"] = size

        resp = await self._client.amend_order(**kwargs)
        ret_code = resp.get("retCode", -1)
        if ret_code != 0:
            return {
                "error_response": {
                    "message": resp.get("retMsg", "Unknown error"),
                    "code": ret_code,
                }
            }

        return {
            "success": True,
            "order_id": order_id,
        }

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        # Need symbol to cancel — try to find it from open orders
        open_resp = await self._client.get_open_orders(
            category="linear"
        )
        result = open_resp.get("result", {})
        symbol = None
        for order in result.get("list", []):
            if order.get("orderId") == order_id:
                symbol = order.get("symbol")
                break

        # Fallback: check order history if not in open orders
        if not symbol:
            hist_resp = await self._client.get_order_history(
                category="linear", order_id=order_id
            )
            hist_result = hist_resp.get("result", {})
            for order in hist_result.get("list", []):
                if order.get("orderId") == order_id:
                    symbol = order.get("symbol")
                    break

        if not symbol:
            return {
                "success": False,
                "error": f"Order {order_id} not found",
            }

        resp = await self._client.cancel_order(
            symbol=symbol, order_id=order_id
        )
        return {
            "success": True,
            "order_id": order_id,
            "result": resp.get("result", {}),
        }

    async def list_orders(
        self,
        product_id: Optional[str] = None,
        order_status: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        symbol = to_bybit_symbol(product_id) if product_id else None

        # Check open orders first
        if not order_status or "OPEN" in order_status:
            resp = await self._client.get_open_orders(
                category="linear", symbol=symbol
            )
        else:
            resp = await self._client.get_order_history(
                category="linear", symbol=symbol, limit=limit
            )

        result = resp.get("result", {})
        orders = []
        for order in result.get("list", []):
            orders.append({
                "order_id": order.get("orderId", ""),
                "product_id": from_bybit_symbol(
                    order.get("symbol", "")
                ),
                "side": order.get("side", "").upper(),
                "type": order.get("orderType", ""),
                "status": self._normalize_order_status(
                    order.get("orderStatus", "")
                ),
                "size": order.get("qty", "0"),
                "price": order.get("price", "0"),
                "filled_size": order.get("cumExecQty", "0"),
                "filled_value": order.get("cumExecValue", "0"),
                "created_time": order.get("createdTime", ""),
            })
        return orders

    # ==========================================================
    # CONVENIENCE TRADING METHODS
    # ==========================================================

    async def buy_eth_with_btc(
        self, btc_amount: float, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        return await self.create_market_order(
            product_id=product_id,
            side="BUY",
            funds=str(btc_amount),
        )

    async def sell_eth_for_btc(
        self, eth_amount: float, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        return await self.create_market_order(
            product_id=product_id,
            side="SELL",
            size=str(eth_amount),
        )

    async def buy_with_usd(
        self, usd_amount: float, product_id: str
    ) -> Dict[str, Any]:
        return await self.create_market_order(
            product_id=product_id,
            side="BUY",
            funds=str(usd_amount),
        )

    async def sell_for_usd(
        self, base_amount: float, product_id: str
    ) -> Dict[str, Any]:
        return await self.create_market_order(
            product_id=product_id,
            side="SELL",
            size=str(base_amount),
        )

    # ==========================================================
    # EXCHANGE METADATA
    # ==========================================================

    def get_exchange_type(self) -> str:
        return "cex"

    async def test_connection(self) -> bool:
        try:
            await self._client.get_wallet_balance()
            return True
        except Exception as e:
            logger.error(f"ByBit connection test failed: {e}")
            return False

    # ==========================================================
    # BYBIT-SPECIFIC METHODS
    # ==========================================================

    async def get_positions_info(
        self, symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get open positions (ByBit-specific)."""
        bybit_symbol = to_bybit_symbol(symbol) if symbol else None
        resp = await self._client.get_positions(
            category="linear", symbol=bybit_symbol
        )
        result = resp.get("result", {})
        positions = []
        for pos in result.get("list", []):
            if float(pos.get("size", "0")) > 0:
                positions.append({
                    "symbol": from_bybit_symbol(
                        pos.get("symbol", "")
                    ),
                    "side": pos.get("side", ""),
                    "size": pos.get("size", "0"),
                    "entry_price": pos.get("avgPrice", "0"),
                    "mark_price": pos.get("markPrice", "0"),
                    "unrealized_pnl": pos.get("unrealisedPnl", "0"),
                    "leverage": pos.get("leverage", "1"),
                    "liq_price": pos.get("liqPrice", "0"),
                    "take_profit": pos.get("takeProfit", ""),
                    "stop_loss": pos.get("stopLoss", ""),
                })
        return positions

    async def get_equity(self) -> float:
        """Get total account equity in USDT (for PropGuard)."""
        resp = await self._client.get_wallet_balance()
        result = resp.get("result", {})
        for acct in result.get("list", []):
            equity = acct.get("totalEquity", "0")
            return float(equity)
        return 0.0

    async def close_all_positions(self):
        """Emergency close all positions (for PropGuard kill switch)."""
        positions = await self.get_positions_info()
        for pos in positions:
            symbol = to_bybit_symbol(pos["symbol"])
            side = "Sell" if pos["side"] == "Buy" else "Buy"
            try:
                await self._client.place_order(
                    symbol=symbol,
                    side=side,
                    order_type="Market",
                    qty=pos["size"],
                    category="linear",
                    reduce_only=True,
                )
                logger.critical(
                    f"PROPGUARD: Closed position {pos['symbol']} "
                    f"{pos['side']} {pos['size']}"
                )
            except Exception as e:
                logger.critical(
                    f"PROPGUARD: FAILED to close {pos['symbol']}: {e}"
                )

        # Cancel all open orders
        try:
            await self._client.cancel_all_orders(category="linear")
            logger.critical("PROPGUARD: Cancelled all open orders")
        except Exception as e:
            logger.critical(
                f"PROPGUARD: FAILED to cancel orders: {e}"
            )
