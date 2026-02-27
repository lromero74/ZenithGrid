"""
MT5 Bridge Client

ExchangeClient implementation for FTMO / MT5 prop firms.
Sends JSON payloads via HTTP to an MT5 EA listener on a Windows VPS.

- Uses httpx.AsyncClient for HTTP (no new dependency)
- Heartbeat check before every trade
- Symbol mapping: BTC-USD -> BTCUSD (MetaTrader format)
- Volume calculation uses FTMO account balance
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.exchange_clients.base import ExchangeClient

logger = logging.getLogger(__name__)


def to_mt5_symbol(product_id: str) -> str:
    """Convert ZenithGrid product_id to MT5 symbol.

    BTC-USD -> BTCUSD, ETH-USD -> ETHUSD, etc.
    """
    return product_id.replace("-", "")


def from_mt5_symbol(symbol: str) -> str:
    """Convert MT5 symbol back to ZenithGrid product_id.

    BTCUSD -> BTC-USD (best effort)
    """
    # Common forex / crypto patterns
    for suffix in ("USD", "EUR", "GBP", "JPY", "USDT"):
        if symbol.endswith(suffix) and len(symbol) > len(suffix):
            base = symbol[:-len(suffix)]
            return f"{base}-{suffix}"
    return symbol


class MT5BridgeClient(ExchangeClient):
    """
    ExchangeClient for MT5 EA bridge (FTMO prop firm).

    Communicates with a MetaTrader 5 Expert Advisor running on a
    Windows VPS that exposes a simple HTTP JSON API.

    Endpoints expected on the bridge:
      GET  /heartbeat          - Check EA is alive
      GET  /status             - Balance, equity, margin info
      GET  /positions          - Open positions
      POST /order              - Place new order
      POST /close              - Close position
      POST /close-all          - Emergency close all
      GET  /history            - Recent trade history
    """

    def __init__(
        self,
        bridge_url: str,
        magic_number: int = 12345,
        account_balance: float = 100000.0,
        timeout: float = 10.0,
    ):
        self._bridge_url = bridge_url.rstrip("/")
        self._magic_number = magic_number
        self._account_balance = account_balance
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
        self._last_equity: float = account_balance
        logger.info(
            f"MT5BridgeClient initialized "
            f"(bridge={bridge_url}, magic={magic_number})"
        )

    async def close(self):
        """Close the underlying httpx client to release connections."""
        if self._client:
            await self._client.aclose()

    async def _request(
        self, method: str, path: str, **kwargs
    ) -> dict:
        """Make HTTP request to bridge.

        Raises:
            ConnectionError: Bridge is unreachable or timed out.
            ValueError: Bridge returned an HTTP client error (4xx)
                indicating bad request data.
            RuntimeError: Bridge returned an HTTP server error (5xx)
                indicating EA-side failure.
        """
        url = f"{self._bridge_url}{path}"
        try:
            resp = await self._client.request(
                method, url, **kwargs
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            logger.error(f"MT5 bridge timeout: {method} {path}")
            raise ConnectionError("MT5 bridge timeout")
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            body = ""
            try:
                body = e.response.text[:200]
            except Exception:
                pass
            logger.error(
                f"MT5 bridge HTTP {status}: {method} {path} - {body}"
            )
            if 400 <= status < 500:
                raise ValueError(
                    f"MT5 bridge rejected request ({status}): {body}"
                )
            raise RuntimeError(
                f"MT5 bridge server error ({status}): {body}"
            )
        except (httpx.ConnectError, httpx.ReadError, OSError) as e:
            logger.error(
                f"MT5 bridge connection failed: {method} {path}: {e}"
            )
            raise ConnectionError(f"MT5 bridge unavailable: {e}")
        except Exception as e:
            logger.error(f"MT5 bridge request failed: {e}")
            raise ConnectionError(f"MT5 bridge unavailable: {e}")

    async def _heartbeat(self) -> bool:
        """Check if EA is alive."""
        try:
            resp = await self._request("GET", "/heartbeat")
            return resp.get("alive", False)
        except Exception:
            return False

    async def _get_status(self) -> dict:
        """Get account status from bridge."""
        return await self._request("GET", "/status")

    # ==========================================================
    # ACCOUNT & BALANCE
    # ==========================================================

    async def get_accounts(
        self, force_fresh: bool = False
    ) -> List[Dict[str, Any]]:
        try:
            status = await self._get_status()
            equity = float(status.get("equity", self._account_balance))
            self._last_equity = equity
            return [{
                "uuid": f"mt5-{self._magic_number}",
                "currency": "USD",
                "available_balance": {
                    "value": str(status.get("free_margin", equity)),
                    "currency": "USD",
                },
            }]
        except (ConnectionError, ValueError, RuntimeError):
            # Use last known equity (updated on successful requests)
            # rather than initial deposit for more accurate fallback
            return [{
                "uuid": f"mt5-{self._magic_number}",
                "currency": "USD",
                "available_balance": {
                    "value": str(self._last_equity),
                    "currency": "USD",
                },
            }]

    async def get_account(self, account_id: str) -> Dict[str, Any]:
        accounts = await self.get_accounts()
        return accounts[0] if accounts else {}

    async def get_btc_balance(self) -> float:
        return 0.0  # MT5 bridge doesn't hold BTC

    async def get_eth_balance(self) -> float:
        return 0.0

    async def get_usd_balance(self) -> float:
        try:
            status = await self._get_status()
            return float(status.get("free_margin", 0))
        except (ConnectionError, ValueError, RuntimeError):
            return 0.0

    async def get_balance(self, currency: str) -> Dict[str, Any]:
        if currency.upper() == "USD":
            bal = await self.get_usd_balance()
            return {
                "currency": "USD",
                "available": str(bal),
                "hold": "0.00",
            }
        return {
            "currency": currency,
            "available": "0",
            "hold": "0",
        }

    async def invalidate_balance_cache(self):
        pass  # No caching for MT5 bridge

    async def calculate_aggregate_btc_value(
        self, bypass_cache: bool = False
    ) -> float:
        return 0.0  # MT5 operates in USD only

    async def calculate_aggregate_usd_value(self) -> float:
        try:
            status = await self._get_status()
            equity = float(status.get("equity", self._last_equity))
            self._last_equity = equity
            return equity
        except (ConnectionError, ValueError, RuntimeError):
            return self._last_equity

    async def calculate_aggregate_quote_value(
        self, quote_currency: str, bypass_cache: bool = False
    ) -> float:
        """MT5 operates in USD only — return equity for USD, 0 otherwise."""
        if quote_currency == "USD":
            return await self.get_usd_balance()
        return 0.0

    # ==========================================================
    # MARKET DATA
    # ==========================================================

    async def list_products(self) -> List[Dict[str, Any]]:
        """Return a sensible default list for MT5 forex/crypto."""
        return [
            {
                "product_id": "BTC-USD",
                "base_currency": "BTC",
                "quote_currency": "USD",
                "base_min_size": "0.01",
                "base_max_size": "100",
            },
            {
                "product_id": "ETH-USD",
                "base_currency": "ETH",
                "quote_currency": "USD",
                "base_min_size": "0.01",
                "base_max_size": "1000",
            },
        ]

    async def get_product(
        self, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        return {
            "product_id": product_id,
            "base_currency": product_id.split("-")[0],
            "quote_currency": product_id.split("-")[-1],
            "base_min_size": "0.01",
        }

    async def get_ticker(
        self, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        """Get ticker from bridge if available."""
        try:
            symbol = to_mt5_symbol(product_id)
            resp = await self._request(
                "GET", f"/ticker?symbol={symbol}"
            )
            bid = str(resp.get("bid", 0))
            ask = str(resp.get("ask", 0))
            return {
                "product_id": product_id,
                "price": bid,
                "bid": bid,
                "ask": ask,
                "best_bid": bid,
                "best_ask": ask,
                "volume": str(resp.get("volume", 0)),
            }
        except (ConnectionError, ValueError, RuntimeError):
            return {"product_id": product_id, "price": "0"}

    async def get_current_price(
        self, product_id: str = "ETH-BTC"
    ) -> float:
        ticker = await self.get_ticker(product_id)
        return float(ticker.get("price", 0))

    async def get_btc_usd_price(self) -> float:
        return await self.get_current_price("BTC-USD")

    async def get_eth_usd_price(self) -> float:
        return await self.get_current_price("ETH-USD")

    async def get_product_stats(
        self, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        ticker = await self.get_ticker(product_id)
        return {
            "open": ticker.get("price", "0"),
            "high": ticker.get("price", "0"),
            "low": ticker.get("price", "0"),
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
        """Get candles from bridge if supported, else empty."""
        try:
            symbol = to_mt5_symbol(product_id)
            resp = await self._request(
                "GET",
                f"/candles?symbol={symbol}"
                f"&start={start}&end={end}"
                f"&timeframe={granularity}",
            )
            candles = resp.get("candles", [])
            return [
                {
                    "start": str(c.get("time", 0)),
                    "open": str(c.get("open", 0)),
                    "high": str(c.get("high", 0)),
                    "low": str(c.get("low", 0)),
                    "close": str(c.get("close", 0)),
                    "volume": str(c.get("volume", 0)),
                }
                for c in candles
            ]
        except (ConnectionError, ValueError, RuntimeError):
            return []

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
        # Heartbeat check — block if EA down
        if not await self._heartbeat():
            raise ConnectionError(
                "MT5 bridge not responding — order blocked"
            )

        symbol = to_mt5_symbol(product_id)

        # Calculate volume (lots)
        volume = float(size) if size else 0.01
        if funds and not size:
            price = await self.get_current_price(product_id)
            if price > 0:
                volume = float(funds) / price

        payload = {
            "symbol": symbol,
            "action": side.upper(),
            "volume": volume,
            "magic_number": self._magic_number,
        }

        resp = await self._request("POST", "/order", json=payload)

        # Validate the bridge reported success
        if not resp.get("success", False):
            error_msg = resp.get("error", "Unknown MT5 bridge error")
            logger.error(f"MT5 order rejected: {error_msg}")
            return {
                "success": False,
                "error_response": {
                    "message": error_msg,
                    "error": "MT5_ORDER_REJECTED",
                },
            }

        order_id = str(resp.get("ticket", ""))
        exec_price = float(resp.get("price", 0))
        filled_value = volume * exec_price

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
            "filled_size": str(volume),
            "filled_value": str(filled_value),
            "average_filled_price": str(exec_price),
        }

    async def create_limit_order(
        self,
        product_id: str,
        side: str,
        limit_price: float,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not await self._heartbeat():
            raise ConnectionError(
                "MT5 bridge not responding — order blocked"
            )

        symbol = to_mt5_symbol(product_id)
        volume = float(size) if size else 0.01
        if funds and not size:
            volume = float(funds) / limit_price

        payload = {
            "symbol": symbol,
            "action": f"{side.upper()}_LIMIT",
            "volume": volume,
            "price": limit_price,
            "magic_number": self._magic_number,
        }

        resp = await self._request("POST", "/order", json=payload)

        # Validate the bridge reported success
        if not resp.get("success", False):
            error_msg = resp.get("error", "Unknown MT5 bridge error")
            logger.error(f"MT5 limit order rejected: {error_msg}")
            return {
                "success": False,
                "error_response": {
                    "message": error_msg,
                    "error": "MT5_ORDER_REJECTED",
                },
            }

        order_id = str(resp.get("ticket", ""))

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
            "size": str(volume),
        }

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        try:
            resp = await self._request(
                "GET", f"/order?ticket={order_id}"
            )
            volume = float(resp.get("volume", 0))
            price = float(resp.get("price", 0))
            return {
                "order_id": order_id,
                "status": resp.get("status", "UNKNOWN"),
                "filled_size": str(volume),
                "filled_value": str(volume * price),
                "average_filled_price": str(price),
                "total_fees": str(resp.get("commission", 0)),
            }
        except (ConnectionError, ValueError, RuntimeError):
            return {"order_id": order_id, "status": "UNKNOWN"}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        try:
            resp = await self._request(
                "POST",
                "/close",
                json={"ticket": int(order_id)},
            )
            return {"success": resp.get("success", False)}
        except (ConnectionError, ValueError, RuntimeError):
            return {"success": False, "error": "Bridge unavailable"}

    async def list_orders(
        self,
        product_id: Optional[str] = None,
        order_status: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        try:
            resp = await self._request("GET", "/positions")
            positions = resp.get("positions", [])
            orders = []
            for pos in positions:
                p_symbol = from_mt5_symbol(
                    pos.get("symbol", "")
                )
                if product_id and p_symbol != product_id:
                    continue
                orders.append({
                    "order_id": str(pos.get("ticket", "")),
                    "product_id": p_symbol,
                    "side": pos.get("type", "BUY").upper(),
                    "type": "MARKET",
                    "status": "OPEN",
                    "size": str(pos.get("volume", 0)),
                    "price": str(pos.get("open_price", 0)),
                })
            return orders[:limit]
        except (ConnectionError, ValueError, RuntimeError):
            return []

    # ==========================================================
    # CONVENIENCE METHODS
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
    # METADATA
    # ==========================================================

    def get_exchange_type(self) -> str:
        return "cex"  # Behaves like a CEX from adapter perspective

    async def test_connection(self) -> bool:
        return await self._heartbeat()

    # ==========================================================
    # MT5-SPECIFIC
    # ==========================================================

    async def get_equity(self) -> float:
        """Get current account equity (for PropGuard)."""
        try:
            status = await self._get_status()
            equity = float(status.get("equity", 0))
            self._last_equity = equity
            return equity
        except (ConnectionError, ValueError, RuntimeError):
            return self._last_equity

    async def close_all_positions(self):
        """Emergency close all positions (for PropGuard)."""
        try:
            await self._request("POST", "/close-all", json={
                "magic_number": self._magic_number,
            })
            logger.critical(
                "PROPGUARD: MT5 bridge close-all sent"
            )
        except ConnectionError as e:
            logger.critical(
                f"PROPGUARD: MT5 close-all FAILED: {e}"
            )
