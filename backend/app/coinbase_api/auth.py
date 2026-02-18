"""
Authentication utilities for Coinbase Advanced Trade API
Supports both CDP (JWT) and HMAC methods
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

import httpx
import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coinbase.com"


def load_cdp_credentials_from_file(file_path: str) -> Tuple[str, str]:
    """
    Load CDP credentials from JSON key file

    Args:
        file_path: Path to cdp_api_key.json file

    Returns:
        Tuple of (key_name, private_key)
    """
    with open(file_path, "r") as f:
        data = json.load(f)

    return data["name"], data["privateKey"]


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
        private_key.encode("utf-8"), password=None, backend=default_backend()
    )

    # Strip query parameters from path for JWT signing
    # Per Coinbase CDP spec, query params should NOT be in the signed URI
    path_without_query = request_path.split("?")[0]

    # Create JWT payload - URI must include hostname per Coinbase spec
    uri = f"{request_method} api.coinbase.com{path_without_query}"
    current_time = int(time.time())

    payload = {
        "sub": key_name,
        "iss": "cdp",  # Coinbase Developer Platform
        "nbf": current_time,
        "exp": current_time + 120,  # Expires in 2 minutes
        "uri": uri,
    }

    # Sign JWT with ES256 algorithm (ECDSA with P-256 curve)
    token = jwt.encode(
        payload, private_key_obj, algorithm="ES256", headers={"kid": key_name, "nonce": str(current_time)}
    )

    return token


def generate_hmac_signature(api_secret: str, timestamp: str, method: str, request_path: str, body: str = "") -> str:
    """
    Generate HMAC-SHA256 signature for API request

    Args:
        api_secret: HMAC API secret
        timestamp: Unix timestamp string
        method: HTTP method
        request_path: API endpoint path
        body: Request body (empty for GET requests)

    Returns:
        HMAC signature hex string
    """
    message = timestamp + method + request_path + body
    signature = hmac.new(api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
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
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Make authenticated request to Coinbase API

    Uses either CDP (JWT) or HMAC authentication based on auth_type

    Args:
        method: HTTP method (GET, POST, DELETE)
        endpoint: API endpoint path
        auth_type: Either "cdp" or "hmac"
        key_name: CDP API key name (for CDP auth)
        private_key: CDP EC private key (for CDP auth)
        api_key: HMAC API key (for HMAC auth)
        api_secret: HMAC API secret (for HMAC auth)
        params: Query parameters (for GET requests)
        data: JSON body data (for POST requests)

    Returns:
        JSON response from API
    """
    url = f"{BASE_URL}{endpoint}"

    if auth_type == "cdp":
        # CDP/JWT Authentication
        jwt_token = generate_jwt(key_name, private_key, method, endpoint)
        headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
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
            "Content-Type": "application/json",
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
                        wait_time = 2**attempt
                        logger.warning(
                            f"⚠️  Rate limited (429) on {method} {endpoint}, "
                            f"retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"❌ Rate limit exceeded after {max_retries} attempts on {method} {endpoint}")
                        raise
                else:
                    # Non-429 error, log detailed error and raise
                    try:
                        error_body = e.response.json()
                        logger.error(
                            f"❌ Coinbase API error {e.response.status_code} on "
                            f"{method} {endpoint}: {error_body}"
                        )
                    except Exception:
                        logger.error(
                            f"❌ Coinbase API error {e.response.status_code} on "
                            f"{method} {endpoint}: {e.response.text}"
                        )
                    raise

    # Should never reach here (all paths return or raise)
    raise RuntimeError(f"Unexpected: No response after {max_retries} attempts")
