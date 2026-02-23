"""
Tests for backend/app/coinbase_api/auth.py

Covers CDP (JWT) and HMAC authentication utilities,
as well as the authenticated_request function with retry logic.
"""

import hashlib
import hmac as hmac_mod
import json

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.coinbase_api.auth import (
    authenticated_request,
    generate_hmac_signature,
    generate_jwt,
    load_cdp_credentials_from_file,
)


# ---------------------------------------------------------------------------
# load_cdp_credentials_from_file
# ---------------------------------------------------------------------------


class TestLoadCdpCredentialsFromFile:
    """Tests for load_cdp_credentials_from_file()"""

    def test_loads_valid_json_file(self, tmp_path):
        """Happy path: reads name and privateKey from a JSON file."""
        creds = {"name": "my-key", "privateKey": "-----BEGIN EC PRIVATE KEY-----\nfake\n-----END EC PRIVATE KEY-----"}
        cred_file = tmp_path / "cdp_api_key.json"
        cred_file.write_text(json.dumps(creds))

        name, pk = load_cdp_credentials_from_file(str(cred_file))
        assert name == "my-key"
        assert "BEGIN EC PRIVATE KEY" in pk

    def test_raises_on_missing_file(self):
        """Failure: non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_cdp_credentials_from_file("/nonexistent/path.json")

    def test_raises_on_missing_key(self, tmp_path):
        """Failure: JSON missing required keys raises KeyError."""
        cred_file = tmp_path / "bad.json"
        cred_file.write_text(json.dumps({"name": "ok"}))  # missing privateKey

        with pytest.raises(KeyError):
            load_cdp_credentials_from_file(str(cred_file))


# ---------------------------------------------------------------------------
# generate_jwt
# ---------------------------------------------------------------------------


class TestGenerateJwt:
    """Tests for generate_jwt()"""

    # A real EC P-256 key for test purposes (not used in production)
    _TEST_EC_KEY = (
        "-----BEGIN EC PRIVATE KEY-----\n"
        "MHQCAQEEIODsVwQDBHBOT1MXIeR2JzfCPYlgkGp/OOq2xq+tjbvRoAcGBSuBBAAI\n"
        "-----END EC PRIVATE KEY-----"
    )

    @patch("app.coinbase_api.auth.serialization.load_pem_private_key")
    @patch("app.coinbase_api.auth.jwt.encode", return_value="fake.jwt.token")
    @patch("app.coinbase_api.auth.time.time", return_value=1700000000)
    def test_generates_valid_jwt(self, mock_time, mock_encode, mock_load_key):
        """Happy path: generates a JWT with correct payload structure."""
        mock_key_obj = MagicMock()
        mock_load_key.return_value = mock_key_obj

        token = generate_jwt("key-name", "fake-pem", "GET", "/api/v3/brokerage/accounts")

        assert token == "fake.jwt.token"
        mock_encode.assert_called_once()
        call_args = mock_encode.call_args
        payload = call_args[0][0]
        assert payload["sub"] == "key-name"
        assert payload["iss"] == "cdp"
        assert payload["uri"] == "GET api.coinbase.com/api/v3/brokerage/accounts"
        assert payload["exp"] == 1700000000 + 120

    @patch("app.coinbase_api.auth.serialization.load_pem_private_key")
    @patch("app.coinbase_api.auth.jwt.encode", return_value="fake.jwt.token")
    @patch("app.coinbase_api.auth.time.time", return_value=1700000000)
    def test_strips_query_params_from_uri(self, mock_time, mock_encode, mock_load_key):
        """Edge case: query parameters are stripped from the signed URI."""
        mock_load_key.return_value = MagicMock()

        generate_jwt("key-name", "fake-pem", "GET", "/api/v3/brokerage/accounts?limit=250&cursor=abc")

        payload = mock_encode.call_args[0][0]
        assert payload["uri"] == "GET api.coinbase.com/api/v3/brokerage/accounts"

    @patch("app.coinbase_api.auth.serialization.load_pem_private_key", side_effect=ValueError("bad key"))
    def test_raises_on_invalid_key(self, mock_load_key):
        """Failure: invalid PEM key raises ValueError."""
        with pytest.raises(ValueError, match="bad key"):
            generate_jwt("key-name", "bad-pem-data", "GET", "/api/v3/brokerage/accounts")


# ---------------------------------------------------------------------------
# generate_hmac_signature
# ---------------------------------------------------------------------------


class TestGenerateHmacSignature:
    """Tests for generate_hmac_signature()"""

    def test_produces_correct_hmac(self):
        """Happy path: signature matches expected HMAC-SHA256."""
        secret = "my-secret"
        timestamp = "1700000000"
        method = "GET"
        path = "/api/v3/brokerage/accounts"
        body = ""

        result = generate_hmac_signature(secret, timestamp, method, path, body)

        # Manually compute expected
        message = timestamp + method + path + body
        expected = hmac_mod.new(
            secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert result == expected

    def test_includes_body_in_signature(self):
        """Edge case: POST body is included in the signed message."""
        body = '{"order_id": "123"}'
        sig_with_body = generate_hmac_signature("secret", "123", "POST", "/orders", body)
        sig_without_body = generate_hmac_signature("secret", "123", "POST", "/orders", "")
        assert sig_with_body != sig_without_body

    def test_different_secrets_produce_different_signatures(self):
        """Edge case: different secrets produce different results."""
        sig1 = generate_hmac_signature("secret-a", "123", "GET", "/path")
        sig2 = generate_hmac_signature("secret-b", "123", "GET", "/path")
        assert sig1 != sig2


# ---------------------------------------------------------------------------
# authenticated_request
# ---------------------------------------------------------------------------


class TestAuthenticatedRequest:
    """Tests for authenticated_request()"""

    @pytest.mark.asyncio
    @patch("app.coinbase_api.auth.generate_hmac_signature", return_value="fake-sig")
    @patch("app.coinbase_api.auth.time.time", return_value=1700000000)
    async def test_hmac_get_request_success(self, mock_time, mock_sig):
        """Happy path: HMAC GET request returns JSON response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"accounts": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.coinbase_api.auth.httpx.AsyncClient", return_value=mock_client):
            result = await authenticated_request(
                "GET",
                "/api/v3/brokerage/accounts",
                auth_type="hmac",
                api_key="my-key",
                api_secret="my-secret",
            )

        assert result == {"accounts": []}
        mock_client.get.assert_called_once()
        # Verify correct headers were passed
        call_kwargs = mock_client.get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["CB-ACCESS-KEY"] == "my-key"
        assert headers["CB-ACCESS-SIGN"] == "fake-sig"

    @pytest.mark.asyncio
    @patch("app.coinbase_api.auth.generate_jwt", return_value="jwt-token")
    async def test_cdp_post_request_success(self, mock_jwt):
        """Happy path: CDP POST request sends JWT bearer token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.coinbase_api.auth.httpx.AsyncClient", return_value=mock_client):
            result = await authenticated_request(
                "POST",
                "/api/v3/brokerage/orders",
                auth_type="cdp",
                key_name="cdp-key",
                private_key="fake-pem",
                data={"product_id": "ETH-BTC"},
            )

        assert result == {"success": True}
        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["Authorization"] == "Bearer jwt-token"

    @pytest.mark.asyncio
    @patch("app.coinbase_api.auth.generate_hmac_signature", return_value="sig")
    @patch("app.coinbase_api.auth.time.time", return_value=1700000000)
    @patch("app.coinbase_api.auth.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_on_429_rate_limit(self, mock_sleep, mock_time, mock_sig):
        """Edge case: retries with exponential backoff on 429 Too Many Requests."""
        # First call: 429, second call: success
        error_response = MagicMock()
        error_response.status_code = 429
        error_response.json.return_value = {"error": "rate limited"}
        error_response.text = "rate limited"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"data": "ok"}
        success_response.raise_for_status = MagicMock()

        http_error = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=error_response
        )
        error_response.raise_for_status = MagicMock(side_effect=http_error)

        mock_client = AsyncMock()
        mock_client.get.side_effect = [error_response, success_response]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.coinbase_api.auth.httpx.AsyncClient", return_value=mock_client):
            result = await authenticated_request(
                "GET", "/api/v3/test", auth_type="hmac",
                api_key="k", api_secret="s",
            )

        assert result == {"data": "ok"}
        assert mock_client.get.call_count == 2
        mock_sleep.assert_called_once_with(1)  # 2^0 = 1 second backoff

    @pytest.mark.asyncio
    @patch("app.coinbase_api.auth.generate_hmac_signature", return_value="sig")
    @patch("app.coinbase_api.auth.time.time", return_value=1700000000)
    async def test_raises_on_non_429_http_error(self, mock_time, mock_sig):
        """Failure: non-429 HTTP errors are raised immediately without retry."""
        error_response = MagicMock()
        error_response.status_code = 403
        error_response.json.return_value = {"error": "forbidden"}
        error_response.text = "forbidden"

        http_error = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=error_response
        )
        error_response.raise_for_status = MagicMock(side_effect=http_error)

        mock_client = AsyncMock()
        mock_client.get.return_value = error_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.coinbase_api.auth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                await authenticated_request(
                    "GET", "/api/v3/test", auth_type="hmac",
                    api_key="k", api_secret="s",
                )

        # Should not retry on 403
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    @patch("app.coinbase_api.auth.generate_hmac_signature", return_value="sig")
    @patch("app.coinbase_api.auth.time.time", return_value=1700000000)
    async def test_unsupported_method_raises(self, mock_time, mock_sig):
        """Failure: unsupported HTTP method raises ValueError."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.coinbase_api.auth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="Unsupported method: PATCH"):
                await authenticated_request(
                    "PATCH", "/api/v3/test", auth_type="hmac",
                    api_key="k", api_secret="s",
                )

    @pytest.mark.asyncio
    @patch("app.coinbase_api.auth.generate_hmac_signature", return_value="sig")
    @patch("app.coinbase_api.auth.time.time", return_value=1700000000)
    async def test_delete_request_uses_correct_method(self, mock_time, mock_sig):
        """Happy path: DELETE method calls client.delete()."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deleted": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.delete.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.coinbase_api.auth.httpx.AsyncClient", return_value=mock_client):
            result = await authenticated_request(
                "DELETE", "/api/v3/test", auth_type="hmac",
                api_key="k", api_secret="s",
            )

        assert result == {"deleted": True}
        mock_client.delete.assert_called_once()
