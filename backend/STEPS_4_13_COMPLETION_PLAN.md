# STEPs 4-13: Remaining Refactoring Completion Plan

**Purpose:** Detailed step-by-step instructions for completing the remaining 10 file refactorings
**Current Status:** STEP 3 complete, beginning STEP 4
**Files Remaining:** 10 files (500-874 lines each)

---

## STEP 4: coinbase_unified_client.py (874 lines)

### Analysis:
The file contains 5 logical groupings:
1. **Authentication** (init + CDP JWT + HMAC methods)
2. **Account/Balance APIs** (accounts, portfolios, balances, aggregates)
3. **Product/Market Data APIs** (products, candles, ticker, prices)
4. **Order APIs** (create, get, cancel, list orders)
5. **Main client wrapper** (coordinates all modules)

### Proposed Module Structure:

```
backend/app/coinbase_api/
├── __init__.py
├── auth.py                 (~180 lines) - Authentication logic
├── account_api.py          (~200 lines) - Accounts, balances, aggregates
├── market_data_api.py      (~150 lines) - Products, candles, prices
├── order_api.py            (~180 lines) - Order creation/management
└── client.py               (~150 lines) - Main CoinbaseClient wrapper
```

### 4.1: Create coinbase_api/ directory and __init__.py

```bash
mkdir -p app/coinbase_api
touch app/coinbase_api/__init__.py
```

### 4.2: Extract auth.py (~180 lines)

**Lines to extract:** 42-244 (from `__init__` to end of `_request` method)

**Create:** `backend/app/coinbase_api/auth.py`

```python
"""
Authentication for Coinbase Advanced Trade API
Supports both CDP (JWT) and HMAC methods
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional

import httpx
import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coinbase.com"


def load_cdp_credentials_from_file(file_path: str) -> tuple[str, str]:
    """Load CDP credentials from JSON key file"""
    with open(file_path, 'r') as f:
        data = json.load(f)
    return data['name'], data['privateKey']


def generate_jwt(key_name: str, private_key: str, request_method: str, request_path: str) -> str:
    """
    Generate JWT token for CDP API request

    Args:
        key_name: CDP API key name
        private_key: CDP EC private key PEM string
        request_method: HTTP method (GET, POST, etc.)
        request_path: API endpoint path

    Returns:
        JWT token string
    """
    # Load the EC private key
    private_key_obj = serialization.load_pem_private_key(
        private_key.encode('utf-8'),
        password=None,
        backend=default_backend()
    )

    # Create JWT payload - URI must include hostname per Coinbase spec
    uri = f"{request_method} api.coinbase.com{request_path}"
    current_time = int(time.time())

    payload = {
        "sub": key_name,
        "iss": "cdp",  # Coinbase Developer Platform
        "nbf": current_time,
        "exp": current_time + 120,  # Expires in 2 minutes
        "uri": uri
    }

    # Sign JWT with ES256 algorithm (ECDSA with P-256 curve)
    token = jwt.encode(
        payload,
        private_key_obj,
        algorithm="ES256",
        headers={"kid": key_name, "nonce": str(current_time)}
    )

    print(f"DEBUG: Generated JWT for {uri}")
    print(f"DEBUG: Payload: {payload}")
    print(f"DEBUG: Token: {token[:50]}...")

    return token


def generate_hmac_signature(
    api_secret: str,
    timestamp: str,
    method: str,
    request_path: str,
    body: str = ""
) -> str:
    """Generate HMAC-SHA256 signature for API request"""
    message = timestamp + method + request_path + body
    signature = hmac.new(
        api_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return signature


async def authenticated_request(
    method: str,
    endpoint: str,
    auth_type: str,
    # CDP params
    key_name: Optional[str] = None,
    private_key: Optional[str] = None,
    # HMAC params
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    # Request params
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Make authenticated request to Coinbase API

    Uses either CDP (JWT) or HMAC authentication based on auth_type
    """
    url = f"{BASE_URL}{endpoint}"

    if auth_type == "cdp":
        # CDP/JWT Authentication
        jwt_token = generate_jwt(key_name, private_key, method, endpoint)
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json"
        }
    else:
        # HMAC Authentication
        timestamp = str(int(time.time()))
        body = ""
        if data:
            body = json.dumps(data)

        signature = generate_hmac_signature(api_secret, timestamp, method, endpoint, body)
        headers = {
            "CB-ACCESS-KEY": api_key,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json"
        }

    async with httpx.AsyncClient(timeout=30.0) as client:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if method == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method == "POST":
                    response = await client.post(url, headers=headers, json=data)
                elif method == "DELETE":
                    response = await client.delete(url, headers=headers, params=params)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Too Many Requests
                    if attempt < max_retries - 1:
                        # Exponential backoff: 1s, 2s, 4s
                        wait_time = 2 ** attempt
                        logger.warning(f"⚠️  Rate limited (429) on {method} {endpoint}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"❌ Rate limit exceeded after {max_retries} attempts on {method} {endpoint}")
                        raise
                else:
                    # Non-429 error, raise immediately
                    raise
```

**Commands:**
```bash
cd /Users/louis/ZenithGrid/backend
python3 -m py_compile app/coinbase_api/auth.py
git add app/coinbase_api/
git commit -m "STEP 4.1: Extract coinbase_api/auth.py (~180 lines)

- Extracted CDP JWT authentication
- Extracted HMAC authentication
- Converted to standalone functions
- Part of STEP 4: Split coinbase_unified_client.py"
```

### 4.3: Extract account_api.py (~200 lines)

**Methods to extract:**
- `get_accounts()`
- `get_account()`
- `get_portfolios()`
- `get_portfolio_breakdown()`
- `get_btc_balance()`
- `get_eth_balance()`
- `get_usd_balance()`
- `invalidate_balance_cache()`
- `calculate_aggregate_btc_value()`
- `calculate_aggregate_usd_value()`

Convert to standalone async functions that accept auth credentials as parameters.

### 4.4: Extract market_data_api.py (~150 lines)

**Methods to extract:**
- `list_products()`
- `get_product()`
- `get_ticker()`
- `get_current_price()`
- `get_btc_usd_price()`
- `get_product_stats()`
- `get_candles()`

### 4.5: Extract order_api.py (~180 lines)

**Methods to extract:**
- `create_market_order()`
- `create_limit_order()`
- `get_order()`
- `cancel_order()`
- `list_orders()`
- `buy_eth_with_btc()`
- `sell_eth_for_btc()`
- `buy_with_usd()`
- `sell_for_usd()`

### 4.6: Create refactored client.py (~150 lines)

**Create:** New `coinbase_unified_client.py` that imports and delegates

```python
"""
Unified Coinbase Advanced Trade API Client (Refactored)

Wrapper class that coordinates all Coinbase API modules.
Maintains backward compatibility with existing code.
"""

from typing import Any, Dict, List, Optional

from app.coinbase_api import auth
from app.coinbase_api import account_api
from app.coinbase_api import market_data_api
from app.coinbase_api import order_api


class CoinbaseClient:
    """
    Unified Coinbase Advanced Trade API Client

    Supports both CDP (JWT) and HMAC authentication methods.
    Auto-detects which method to use based on provided credentials.
    """

    BASE_URL = "https://api.coinbase.com"

    def __init__(
        self,
        # CDP/JWT auth params
        key_name: Optional[str] = None,
        private_key: Optional[str] = None,
        key_file_path: Optional[str] = None,
        # HMAC auth params
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ):
        # Auto-detect authentication method
        if key_name and private_key:
            self.auth_type = "cdp"
            self.key_name = key_name
            self.private_key = private_key
        elif key_file_path:
            self.auth_type = "cdp"
            self.key_name, self.private_key = auth.load_cdp_credentials_from_file(key_file_path)
        elif api_key and api_secret:
            self.auth_type = "hmac"
            self.api_key = api_key
            self.api_secret = api_secret
        else:
            # Fallback to settings
            from app.config import settings
            if hasattr(settings, 'coinbase_cdp_key_name') and settings.coinbase_cdp_key_name:
                self.auth_type = "cdp"
                self.key_name = settings.coinbase_cdp_key_name
                self.private_key = settings.coinbase_cdp_private_key
            else:
                self.auth_type = "hmac"
                self.api_key = settings.coinbase_api_key
                self.api_secret = settings.coinbase_api_secret

    async def _request(self, method: str, endpoint: str, params=None, data=None):
        """Make authenticated request"""
        return await auth.authenticated_request(
            method, endpoint, self.auth_type,
            key_name=getattr(self, 'key_name', None),
            private_key=getattr(self, 'private_key', None),
            api_key=getattr(self, 'api_key', None),
            api_secret=getattr(self, 'api_secret', None),
            params=params, data=data
        )

    # Account APIs
    async def get_accounts(self, force_fresh: bool = False):
        return await account_api.get_accounts(self._request, force_fresh)

    # ... (delegate all other methods similarly)
```

**Commands:**
```bash
mv app/coinbase_unified_client.py app/coinbase_unified_client_OLD_BACKUP.py
# Create new coinbase_unified_client.py with wrapper
python3 -m py_compile app/coinbase_unified_client.py
git add app/coinbase_unified_client.py app/coinbase_unified_client_OLD_BACKUP.py
git commit -m "STEP 4.6: Refactor coinbase_unified_client.py into wrapper (~150 lines)

- Created new wrapper that delegates to coinbase_api modules
- Preserved public API (100% backward compatible)
- Original file moved to _OLD_BACKUP.py (874 lines)
- STEP 4 COMPLETE: 874 lines → 5 focused modules"
```

---

## STEP 5: multi_bot_monitor.py (801 lines)

### Proposed Split:
1. **bot_processor.py** (~300 lines) - Process individual bot logic
2. **monitor_loop.py** (~250 lines) - Main monitoring loop
3. **multi_bot_monitor.py** (~250 lines) - Coordinator class

Follow same pattern: extract, verify, commit each module.

---

## STEP 6-13: Remaining Files

Follow the same refactoring pattern for each:

### STEP 6: bots.py router (760 lines)
Split into endpoint groups (similar to main.py refactor in STEP 2)

### STEP 7: order_history.py router (598 lines)
Split by functionality groups

### STEP 8: models.py (692 lines)
Split by model categories (User models, Bot models, Trading models, etc.)

### STEP 9: schemas.py (566 lines)
Split to match models.py structure

### STEP 10: trading_client.py (557 lines)
Split into buy operations, sell operations, balance operations

### STEP 11: order_monitor.py (542 lines)
Split into monitoring logic and execution logic

### STEP 12: templates.py router (512 lines)
Split by endpoint groups

### STEP 13: database.py (503 lines)
Split into connection management, session management, utilities

---

## General Refactoring Pattern (For ALL Steps)

1. **Read the file** - Understand structure and dependencies
2. **Identify logical groupings** - Find cohesive modules
3. **Create directory if needed** - For multi-module splits
4. **Extract first module** - Convert methods to standalone functions
5. **Verify syntax** - `python3 -m py_compile`
6. **Commit** - Detailed commit message
7. **Repeat** for each module
8. **Create wrapper class** - Maintains backward compatibility
9. **Move original to _OLD_BACKUP.py**
10. **Final commit** - Mark step complete

---

## Success Criteria (All Steps)

- ✅ All modules under 500 lines
- ✅ Python syntax validation passes
- ✅ Public API preserved (backward compatible)
- ✅ Original files preserved as _OLD_BACKUP.py
- ✅ Clear, detailed commit messages
- ✅ No functionality dropped (verify with git diff)

---

## Estimated Work Remaining

- STEP 4: ~4-5 modules (~2-3 hours)
- STEPs 5-13: 9 files (~12-18 hours)
- **Total: 14-21 hours of focused refactoring work**

---

**Next Action:** Continue with STEP 4.2 - Extract auth.py from coinbase_unified_client.py
