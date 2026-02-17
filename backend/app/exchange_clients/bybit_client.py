"""
ByBit V5 Client

Thin wrapper around pybit's HTTP client with:
- Testnet toggle
- Response normalization to match ZenithGrid conventions
- Product ID translation (BTC-USD <-> BTCUSDT)
- Granularity mapping (ONE_MINUTE -> "1")
- asyncio.to_thread() wrappers for blocking pybit calls
- Error handling with meaningful exceptions
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ByBit rate limiting: 120 requests per second for most endpoints,
# but order endpoints are stricter (10/s). Use 100ms min spacing as
# a safe default to avoid 10006 rate limit errors.
_BYBIT_MIN_INTERVAL = 0.10  # 100ms between requests

# Product ID translation maps
# ZenithGrid uses "BTC-USD" format; ByBit uses "BTCUSDT"
_QUOTE_MAP = {
    "USD": "USDT",
    "USDT": "USDT",
    "USDC": "USDC",
    "BTC": "BTC",
    "ETH": "ETH",
}

# Granularity mapping: ZenithGrid -> ByBit
_GRANULARITY_MAP = {
    "ONE_MINUTE": "1",
    "FIVE_MINUTE": "5",
    "FIFTEEN_MINUTE": "15",
    "THIRTY_MINUTE": "30",
    "ONE_HOUR": "60",
    "TWO_HOUR": "120",
    "FOUR_HOUR": "240",
    "SIX_HOUR": "360",
    "TWELVE_HOUR": "720",
    "ONE_DAY": "D",
    "ONE_WEEK": "W",
    "ONE_MONTH": "M",
}


class ByBitError(Exception):
    """ByBit API error with error code"""
    def __init__(self, message: str, code: int = 0):
        self.code = code
        super().__init__(message)


def to_bybit_symbol(product_id: str) -> str:
    """Convert ZenithGrid product_id to ByBit symbol.

    Examples:
        BTC-USD  -> BTCUSDT
        ETH-BTC  -> ETHBTC
        SOL-USDT -> SOLUSDT
        BTC-USDC -> BTCUSDC
    """
    if "-" not in product_id:
        return product_id
    base, quote = product_id.split("-", 1)
    bybit_quote = _QUOTE_MAP.get(quote, quote)
    return f"{base}{bybit_quote}"


def from_bybit_symbol(symbol: str) -> str:
    """Convert ByBit symbol back to ZenithGrid product_id.

    Maps USDT→USD so ByBit products appear as standard -USD pairs
    to the rest of the system (TradingClient, currency_utils, etc.).
    The to_bybit_symbol() function maps USD→USDT on the reverse path.

    Examples:
        BTCUSDT -> BTC-USD
        ETHBTC  -> ETH-BTC
        SOLUSDC -> SOL-USDC
    """
    # Reverse quote mapping: ByBit quote -> ZenithGrid quote
    _REVERSE_QUOTE = {
        "USDT": "USD",   # Map USDT to USD for system compatibility
        "USDC": "USDC",
        "BTC": "BTC",
        "ETH": "ETH",
    }
    # Try common suffixes longest-first
    for suffix in ("USDT", "USDC", "BTC", "ETH"):
        if symbol.endswith(suffix):
            base = symbol[:-len(suffix)]
            if base:
                mapped = _REVERSE_QUOTE.get(suffix, suffix)
                return f"{base}-{mapped}"
    return symbol


def _check_response(resp: dict) -> dict:
    """Check ByBit response for errors and raise if needed."""
    ret_code = resp.get("retCode", -1)
    if ret_code != 0:
        msg = resp.get("retMsg", "Unknown ByBit error")
        # Sanitize: don't leak internal details
        safe_msg = msg[:200] if msg else "Unknown error"
        raise ByBitError(f"ByBit API error ({ret_code}): {safe_msg}", ret_code)
    return resp


class ByBitClient:
    """
    Low-level wrapper around pybit HTTP client.

    All methods are async via asyncio.to_thread() since pybit is synchronous.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
    ):
        from pybit.unified_trading import HTTP

        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet
        self._http = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
        )
        # Per-instance rate limiting (avoids cross-user interference)
        self._rate_lock = asyncio.Lock()
        self._last_request_time: float = 0.0
        logger.info(
            f"ByBitClient initialized (testnet={testnet})"
        )

    async def _rate_limited_call(self, func, **kwargs):
        """Execute a pybit call with per-instance rate limiting."""
        async with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < _BYBIT_MIN_INTERVAL:
                await asyncio.sleep(_BYBIT_MIN_INTERVAL - elapsed)
            self._last_request_time = time.monotonic()
        return await asyncio.to_thread(func, **kwargs)

    # ----------------------------------------------------------
    # Account / Balance
    # ----------------------------------------------------------

    async def get_wallet_balance(
        self, account_type: str = "UNIFIED"
    ) -> dict:
        """Get wallet balance for unified account."""
        resp = await self._rate_limited_call(
            self._http.get_wallet_balance, accountType=account_type
        )
        return _check_response(resp)

    async def get_coin_balance(
        self, coin: str, account_type: str = "UNIFIED"
    ) -> dict:
        """Get balance for a specific coin."""
        resp = await self._rate_limited_call(
            self._http.get_wallet_balance,
            accountType=account_type,
            coin=coin,
        )
        return _check_response(resp)

    # ----------------------------------------------------------
    # Market Data
    # ----------------------------------------------------------

    async def get_tickers(
        self, category: str = "linear", symbol: Optional[str] = None
    ) -> dict:
        """Get ticker data."""
        kwargs: Dict[str, Any] = {"category": category}
        if symbol:
            kwargs["symbol"] = symbol
        resp = await self._rate_limited_call(
            self._http.get_tickers, **kwargs
        )
        return _check_response(resp)

    async def get_kline(
        self,
        symbol: str,
        interval: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 200,
        category: str = "linear",
    ) -> dict:
        """Get kline/candlestick data."""
        kwargs: Dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start:
            kwargs["start"] = start * 1000  # ByBit uses milliseconds
        if end:
            kwargs["end"] = end * 1000
        resp = await self._rate_limited_call(
            self._http.get_kline, **kwargs
        )
        return _check_response(resp)

    async def get_instruments_info(
        self, category: str = "linear", symbol: Optional[str] = None
    ) -> dict:
        """Get instrument/product details."""
        kwargs: Dict[str, Any] = {"category": category}
        if symbol:
            kwargs["symbol"] = symbol
        resp = await self._rate_limited_call(
            self._http.get_instruments_info, **kwargs
        )
        return _check_response(resp)

    # ----------------------------------------------------------
    # Orders
    # ----------------------------------------------------------

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        category: str = "linear",
        price: Optional[str] = None,
        take_profit: Optional[str] = None,
        stop_loss: Optional[str] = None,
        close_on_trigger: bool = False,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
    ) -> dict:
        """Place an order on ByBit."""
        kwargs: Dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),  # "Buy" or "Sell"
            "orderType": order_type,  # "Market" or "Limit"
            "qty": qty,
            "timeInForce": time_in_force,
        }
        if price:
            kwargs["price"] = price
        if take_profit:
            kwargs["takeProfit"] = take_profit
        if stop_loss:
            kwargs["stopLoss"] = stop_loss
        if close_on_trigger:
            kwargs["closeOnTrigger"] = True
        if reduce_only:
            kwargs["reduceOnly"] = True

        resp = await self._rate_limited_call(
            self._http.place_order, **kwargs
        )
        return _check_response(resp)

    async def get_open_orders(
        self, category: str = "linear", symbol: Optional[str] = None
    ) -> dict:
        """Get open orders."""
        kwargs: Dict[str, Any] = {"category": category}
        if symbol:
            kwargs["symbol"] = symbol
        resp = await self._rate_limited_call(
            self._http.get_open_orders, **kwargs
        )
        return _check_response(resp)

    async def get_order_history(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
        order_id: Optional[str] = None,
        limit: int = 50,
    ) -> dict:
        """Get order history."""
        kwargs: Dict[str, Any] = {
            "category": category,
            "limit": limit,
        }
        if symbol:
            kwargs["symbol"] = symbol
        if order_id:
            kwargs["orderId"] = order_id
        resp = await self._rate_limited_call(
            self._http.get_order_history, **kwargs
        )
        return _check_response(resp)

    async def amend_order(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Amend (edit) an existing order's price or qty."""
        params: dict = {"category": category}
        if symbol:
            params["symbol"] = symbol
        params.update(kwargs)
        resp = await self._rate_limited_call(
            self._http.amend_order, **params
        )
        return _check_response(resp)

    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
        category: str = "linear",
    ) -> dict:
        """Cancel an order."""
        resp = await self._rate_limited_call(
            self._http.cancel_order,
            category=category,
            symbol=symbol,
            orderId=order_id,
        )
        return _check_response(resp)

    async def cancel_all_orders(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
        settle_coin: Optional[str] = None,
    ) -> dict:
        """Cancel all open orders.

        For linear category, at least one of symbol, baseCoin, or
        settleCoin is required by ByBit V5 API.
        """
        kwargs: Dict[str, Any] = {"category": category}
        if symbol:
            kwargs["symbol"] = symbol
        if settle_coin:
            kwargs["settleCoin"] = settle_coin
        # For linear without symbol, default settleCoin to USDT
        if category == "linear" and not symbol and not settle_coin:
            kwargs["settleCoin"] = "USDT"
        resp = await self._rate_limited_call(
            self._http.cancel_all_orders, **kwargs
        )
        return _check_response(resp)

    # ----------------------------------------------------------
    # Positions
    # ----------------------------------------------------------

    async def get_positions(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
    ) -> dict:
        """Get open positions."""
        kwargs: Dict[str, Any] = {"category": category}
        if symbol:
            kwargs["symbol"] = symbol
        resp = await self._rate_limited_call(
            self._http.get_positions, **kwargs
        )
        return _check_response(resp)

    async def set_leverage(
        self,
        symbol: str,
        buy_leverage: str,
        sell_leverage: str,
        category: str = "linear",
    ) -> dict:
        """Set leverage for a symbol."""
        resp = await self._rate_limited_call(
            self._http.set_leverage,
            category=category,
            symbol=symbol,
            buyLeverage=buy_leverage,
            sellLeverage=sell_leverage,
        )
        return _check_response(resp)

    async def set_trading_stop(
        self,
        symbol: str,
        category: str = "linear",
        take_profit: Optional[str] = None,
        stop_loss: Optional[str] = None,
        position_idx: int = 0,
    ) -> dict:
        """Set TP/SL on existing position."""
        kwargs: Dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "positionIdx": position_idx,
        }
        if take_profit:
            kwargs["takeProfit"] = take_profit
        if stop_loss:
            kwargs["stopLoss"] = stop_loss
        resp = await self._rate_limited_call(
            self._http.set_trading_stop, **kwargs
        )
        return _check_response(resp)

    async def switch_margin_mode(
        self, category: str = "linear", mode: str = "REGULAR_MARGIN"
    ) -> dict:
        """Switch margin mode (REGULAR_MARGIN or PORTFOLIO_MARGIN)."""
        try:
            resp = await self._rate_limited_call(
                self._http.switch_margin_mode,
                category=category,
                tradeMode=0 if mode == "REGULAR_MARGIN" else 1,
            )
            return _check_response(resp)
        except ByBitError as e:
            # 110026 = already in requested mode
            if e.code == 110026:
                logger.info(f"Already in margin mode {mode}")
                return {"retCode": 0, "retMsg": "OK"}
            raise

    async def switch_position_mode(
        self,
        category: str = "linear",
        mode: int = 0,  # 0=one-way, 3=hedge
        symbol: Optional[str] = None,
    ) -> dict:
        """Switch position mode."""
        kwargs: Dict[str, Any] = {
            "category": category,
            "mode": mode,
        }
        if symbol:
            kwargs["symbol"] = symbol
        try:
            resp = await self._rate_limited_call(
                self._http.switch_position_mode, **kwargs
            )
            return _check_response(resp)
        except ByBitError as e:
            # 110025 = already in requested mode
            if e.code == 110025:
                logger.info("Already in requested position mode")
                return {"retCode": 0, "retMsg": "OK"}
            raise

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def map_granularity(self, granularity: str) -> str:
        """Map ZenithGrid granularity to ByBit interval string."""
        result = _GRANULARITY_MAP.get(granularity)
        if not result:
            raise ValueError(
                f"Unsupported granularity: {granularity}. "
                f"Supported: {list(_GRANULARITY_MAP.keys())}"
            )
        return result

    def normalize_candles(self, raw_list: List) -> List[Dict[str, Any]]:
        """
        Normalize ByBit kline data to ZenithGrid candle format.

        ByBit returns: [startTime, open, high, low, close, volume, turnover]
        sorted newest-first (reverse chronological).
        ZenithGrid expects: {start, open, high, low, close, volume}
        sorted oldest-first (chronological).
        """
        candles = []
        for item in raw_list:
            candles.append({
                "start": str(int(item[0]) // 1000),  # ms -> seconds
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5],
            })
        # ByBit returns newest-first; reverse to chronological order
        candles.reverse()
        return candles
