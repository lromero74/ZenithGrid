"""
Tests for backend/app/exchange_clients/factory.py

Tests the exchange client factory functions that create exchange clients
based on configuration. Uses mocks for all exchange client constructors
to avoid importing real exchange libraries or hitting real APIs.

Note: The factory uses lazy imports inside function bodies, so we must
patch the source modules (e.g., app.coinbase_unified_client.CoinbaseClient)
rather than app.exchange_clients.factory.CoinbaseClient.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.exchange_clients.factory import (
    create_exchange_client,
    create_exchange_client_from_bot_config,
)


# =========================================================
# create_exchange_client
# =========================================================


class TestCreateExchangeClient:
    """Tests for create_exchange_client()"""

    @patch("app.exchange_clients.coinbase_adapter.CoinbaseAdapter")
    @patch("app.coinbase_unified_client.CoinbaseClient")
    def test_coinbase_client_with_valid_creds(self, mock_cb_client, mock_cb_adapter):
        """Happy path: creates Coinbase client with valid credentials."""
        mock_cb_client.return_value = MagicMock()
        mock_adapter_instance = MagicMock()
        mock_cb_adapter.return_value = mock_adapter_instance

        result = create_exchange_client(
            exchange_type="cex",
            exchange_name="coinbase",
            coinbase_key_name="test-key",
            coinbase_private_key="test-secret",
        )

        assert result is not None
        mock_cb_client.assert_called_once_with(
            key_name="test-key",
            private_key="test-secret",
            account_id=None,
        )

    def test_coinbase_client_missing_creds_returns_none(self):
        """Failure case: missing Coinbase credentials returns None."""
        result = create_exchange_client(
            exchange_type="cex",
            exchange_name="coinbase",
            coinbase_key_name=None,
            coinbase_private_key=None,
        )
        assert result is None

    def test_coinbase_client_missing_key_returns_none(self):
        """Edge case: only key_name provided, missing private_key."""
        result = create_exchange_client(
            exchange_type="cex",
            exchange_name="coinbase",
            coinbase_key_name="test-key",
            coinbase_private_key=None,
        )
        assert result is None

    @patch("app.exchange_clients.bybit_adapter.ByBitAdapter")
    @patch("app.exchange_clients.bybit_client.ByBitClient")
    def test_bybit_client_with_valid_creds(self, mock_bb_client, mock_bb_adapter):
        """Happy path: creates ByBit client with valid credentials."""
        mock_bb_client.return_value = MagicMock()
        mock_adapter_instance = MagicMock()
        mock_bb_adapter.return_value = mock_adapter_instance

        result = create_exchange_client(
            exchange_type="cex",
            exchange_name="bybit",
            bybit_api_key="bb-key",
            bybit_api_secret="bb-secret",
        )

        assert result is not None
        mock_bb_client.assert_called_once_with(
            api_key="bb-key",
            api_secret="bb-secret",
            testnet=False,
        )

    def test_bybit_client_missing_creds_returns_none(self):
        """Failure case: missing ByBit credentials returns None."""
        result = create_exchange_client(
            exchange_type="cex",
            exchange_name="bybit",
            bybit_api_key=None,
            bybit_api_secret=None,
        )
        assert result is None

    @patch("app.exchange_clients.mt5_bridge_client.MT5BridgeClient")
    def test_mt5_bridge_client_with_valid_url(self, mock_mt5):
        """Happy path: creates MT5 bridge client."""
        mock_mt5_instance = MagicMock()
        mock_mt5.return_value = mock_mt5_instance

        result = create_exchange_client(
            exchange_type="cex",
            exchange_name="mt5_bridge",
            mt5_bridge_url="http://localhost:5000",
            mt5_magic_number=99999,
            mt5_account_balance=50000.0,
        )

        assert result is not None
        mock_mt5.assert_called_once_with(
            bridge_url="http://localhost:5000",
            magic_number=99999,
            account_balance=50000.0,
        )

    def test_mt5_bridge_missing_url_returns_none(self):
        """Failure case: missing MT5 bridge URL returns None."""
        result = create_exchange_client(
            exchange_type="cex",
            exchange_name="mt5_bridge",
            mt5_bridge_url=None,
        )
        assert result is None

    @patch("app.exchange_clients.dex_client.DEXClient")
    def test_dex_client_with_valid_config(self, mock_dex):
        """Happy path: creates DEX client with valid config."""
        mock_dex_instance = MagicMock()
        mock_dex.return_value = mock_dex_instance

        result = create_exchange_client(
            exchange_type="dex",
            chain_id=1,
            private_key="0xabc123",
            rpc_url="https://mainnet.infura.io/v3/key",
            dex_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
        )

        assert result is not None
        mock_dex.assert_called_once_with(
            chain_id=1,
            rpc_url="https://mainnet.infura.io/v3/key",
            wallet_private_key="0xabc123",
            dex_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
        )

    def test_dex_client_missing_config_raises(self):
        """Failure case: missing DEX config raises ValueError."""
        with pytest.raises(ValueError, match="DEX requires chain_id"):
            create_exchange_client(
                exchange_type="dex",
                chain_id=None,
                private_key=None,
                rpc_url=None,
                dex_router=None,
            )

    def test_invalid_exchange_type_raises(self):
        """Failure case: unknown exchange type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown exchange type: forex"):
            create_exchange_client(exchange_type="forex")

    @patch("app.exchange_clients.coinbase_adapter.CoinbaseAdapter")
    @patch("app.coinbase_unified_client.CoinbaseClient")
    def test_default_exchange_name_is_coinbase(self, mock_cb_client, mock_cb_adapter):
        """Edge case: default exchange_name is 'coinbase' for CEX."""
        mock_cb_client.return_value = MagicMock()
        mock_cb_adapter.return_value = MagicMock()

        result = create_exchange_client(
            exchange_type="cex",
            coinbase_key_name="key",
            coinbase_private_key="secret",
        )

        assert result is not None
        mock_cb_client.assert_called_once()

    @patch("app.exchange_clients.coinbase_adapter.CoinbaseAdapter")
    @patch("app.coinbase_unified_client.CoinbaseClient")
    def test_account_id_passed_to_coinbase(self, mock_cb_client, mock_cb_adapter):
        """Happy path: account_id is forwarded to CoinbaseClient."""
        mock_cb_client.return_value = MagicMock()
        mock_cb_adapter.return_value = MagicMock()

        create_exchange_client(
            exchange_type="cex",
            exchange_name="coinbase",
            coinbase_key_name="key",
            coinbase_private_key="secret",
            account_id=42,
        )

        mock_cb_client.assert_called_once_with(
            key_name="key",
            private_key="secret",
            account_id=42,
        )


# =========================================================
# create_exchange_client_from_bot_config
# =========================================================


class TestCreateExchangeClientFromBotConfig:
    """Tests for create_exchange_client_from_bot_config()"""

    @patch("app.exchange_clients.coinbase_adapter.CoinbaseAdapter")
    @patch("app.coinbase_unified_client.CoinbaseClient")
    def test_coinbase_bot_config(self, mock_cb_client, mock_cb_adapter):
        """Happy path: creates Coinbase client from bot config dict."""
        mock_cb_client.return_value = MagicMock()
        mock_cb_adapter.return_value = MagicMock()

        config = {
            "exchange_type": "cex",
            "exchange_name": "coinbase",
            "coinbase_key_name": "key",
            "coinbase_private_key": "secret",
            "account_id": 5,
        }

        result = create_exchange_client_from_bot_config(config)
        assert result is not None
        mock_cb_client.assert_called_once()

    @patch("app.exchange_clients.bybit_adapter.ByBitAdapter")
    @patch("app.exchange_clients.bybit_client.ByBitClient")
    def test_bybit_bot_config(self, mock_bb_client, mock_bb_adapter):
        """Happy path: creates ByBit client from bot config dict."""
        mock_bb_client.return_value = MagicMock()
        mock_bb_adapter.return_value = MagicMock()

        config = {
            "exchange_type": "cex",
            "exchange_name": "bybit",
            "bybit_api_key": "bb-key",
            "bybit_api_secret": "bb-secret",
        }

        result = create_exchange_client_from_bot_config(config)
        assert result is not None

    @patch("app.exchange_clients.dex_client.DEXClient")
    def test_dex_bot_config(self, mock_dex):
        """Happy path: creates DEX client from bot config dict."""
        mock_dex.return_value = MagicMock()

        config = {
            "exchange_type": "dex",
            "chain_id": 1,
            "wallet_private_key": "0xabc",
            "rpc_url": "https://rpc.example.com",
            "dex_router": "0xrouter",
        }

        result = create_exchange_client_from_bot_config(config)
        assert result is not None

    def test_unknown_exchange_type_in_config_raises(self):
        """Failure case: unknown exchange_type in config raises ValueError."""
        config = {"exchange_type": "p2p"}
        with pytest.raises(ValueError, match="Unknown exchange type in bot config"):
            create_exchange_client_from_bot_config(config)

    @patch("app.exchange_clients.coinbase_adapter.CoinbaseAdapter")
    @patch("app.coinbase_unified_client.CoinbaseClient")
    def test_defaults_to_cex_coinbase(self, mock_cb_client, mock_cb_adapter):
        """Edge case: missing exchange_type defaults to 'cex', missing exchange_name defaults to 'coinbase'."""
        mock_cb_client.return_value = MagicMock()
        mock_cb_adapter.return_value = MagicMock()

        config = {
            "coinbase_key_name": "key",
            "coinbase_private_key": "secret",
        }

        result = create_exchange_client_from_bot_config(config)
        assert result is not None
        mock_cb_client.assert_called_once()

    @patch("app.exchange_clients.mt5_bridge_client.MT5BridgeClient")
    def test_mt5_bridge_bot_config(self, mock_mt5):
        """Happy path: creates MT5 bridge client from bot config dict."""
        mock_mt5.return_value = MagicMock()

        config = {
            "exchange_type": "cex",
            "exchange_name": "mt5_bridge",
            "mt5_bridge_url": "http://localhost:5000",
        }

        result = create_exchange_client_from_bot_config(config)
        assert result is not None
        mock_mt5.assert_called_once()
