"""
Tests for backend/app/product_precision.py

Covers:
- get_precision_data (loading and caching)
- get_quote_precision (for different product types)
- get_base_precision
- format_quote_amount_for_product
- format_base_amount_for_product

Note: These tests are for the product_precision module (product-specific precision
using JSON lookup), NOT the generic precision.py module (already tested in test_precision.py).
"""

import json
import pytest
from unittest.mock import patch, mock_open

import app.product_precision as pp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset the module-level cache before each test."""
    pp._PRECISION_CACHE = None
    yield
    pp._PRECISION_CACHE = None


SAMPLE_PRECISION_DATA = {
    "DASH-BTC": {
        "quote_increment": "0.000001",
        "quote_decimals": 6,
        "base_increment": "0.001"
    },
    "ETH-USD": {
        "quote_increment": "0.01",
        "quote_decimals": 2,
        "base_increment": "0.00000001"
    },
    "XLM-BTC": {
        "quote_increment": "0.00000001",
        "quote_decimals": 8,
        "base_increment": "1"
    },
}


# ---------------------------------------------------------------------------
# get_precision_data
# ---------------------------------------------------------------------------


class TestGetPrecisionData:
    """Tests for get_precision_data()."""

    def test_loads_from_json_file(self):
        """Happy path: loads data from JSON file."""
        mock_json = json.dumps(SAMPLE_PRECISION_DATA)
        with patch("builtins.open", mock_open(read_data=mock_json)):
            with patch("os.path.exists", return_value=True):
                data = pp.get_precision_data()
                assert "DASH-BTC" in data
                assert data["DASH-BTC"]["quote_decimals"] == 6

    def test_caches_data_after_first_load(self):
        """Happy path: second call returns cached data without re-reading file."""
        mock_json = json.dumps(SAMPLE_PRECISION_DATA)
        with patch("builtins.open", mock_open(read_data=mock_json)):
            with patch("os.path.exists", return_value=True):
                data1 = pp.get_precision_data()

        # Second call should use cache even without file mock
        data2 = pp.get_precision_data()
        assert data1 is data2

    def test_missing_file_returns_empty_dict(self):
        """Edge case: missing JSON file returns empty dict."""
        with patch("os.path.exists", return_value=False):
            data = pp.get_precision_data()
            assert data == {}


# ---------------------------------------------------------------------------
# get_quote_precision
# ---------------------------------------------------------------------------


class TestGetQuotePrecision:
    """Tests for get_quote_precision()."""

    def test_usd_always_returns_2(self):
        """Happy path: USD pairs always return 2 decimal places."""
        # Don't even need precision data for USD
        with patch("os.path.exists", return_value=False):
            assert pp.get_quote_precision("BTC-USD") == 2
            assert pp.get_quote_precision("ETH-USD") == 2
            assert pp.get_quote_precision("DOGE-USD") == 2

    def test_known_product_from_data(self):
        """Happy path: known product returns precision from data."""
        pp._PRECISION_CACHE = SAMPLE_PRECISION_DATA
        assert pp.get_quote_precision("DASH-BTC") == 6

    def test_unknown_btc_pair_defaults_to_6(self):
        """Edge case: unknown BTC pair defaults to 6."""
        pp._PRECISION_CACHE = {}
        assert pp.get_quote_precision("NEWCOIN-BTC") == 6

    def test_unknown_other_currency_defaults_to_8(self):
        """Edge case: unknown non-USD/non-BTC pair defaults to 8."""
        pp._PRECISION_CACHE = {}
        assert pp.get_quote_precision("BTC-ETH") == 8

    def test_no_hyphen_in_product_id(self):
        """Edge case: product_id without hyphen uses BTC fallback for quote currency."""
        pp._PRECISION_CACHE = {}
        # No hyphen -> quote_currency defaults to "BTC" -> returns 6
        assert pp.get_quote_precision("BTCUSD") == 6


# ---------------------------------------------------------------------------
# get_base_precision
# ---------------------------------------------------------------------------


class TestGetBasePrecision:
    """Tests for get_base_precision()."""

    def test_known_product_with_decimal(self):
        """Happy path: base_increment with decimals."""
        pp._PRECISION_CACHE = SAMPLE_PRECISION_DATA
        # DASH-BTC: base_increment="0.001" -> 3 decimal places
        assert pp.get_base_precision("DASH-BTC") == 3

    def test_known_product_whole_numbers(self):
        """Happy path: base_increment="1" -> 0 decimal places."""
        pp._PRECISION_CACHE = SAMPLE_PRECISION_DATA
        assert pp.get_base_precision("XLM-BTC") == 0

    def test_known_product_many_decimals(self):
        """Happy path: base_increment with many decimals."""
        pp._PRECISION_CACHE = SAMPLE_PRECISION_DATA
        # ETH-USD: base_increment="0.00000001" -> 8 decimal places
        assert pp.get_base_precision("ETH-USD") == 8

    def test_unknown_product_defaults_to_8(self):
        """Edge case: unknown product defaults to 8."""
        pp._PRECISION_CACHE = {}
        assert pp.get_base_precision("UNKNOWN-USD") == 8

    def test_trailing_zeros_stripped(self):
        """Edge case: trailing zeros in base_increment are stripped."""
        pp._PRECISION_CACHE = {"TEST-USD": {"base_increment": "0.01000"}}
        assert pp.get_base_precision("TEST-USD") == 2

    def test_empty_base_increment_defaults_to_8(self):
        """Edge case: empty base_increment string defaults to 8."""
        pp._PRECISION_CACHE = {"TEST-USD": {"base_increment": ""}}
        assert pp.get_base_precision("TEST-USD") == 8


# ---------------------------------------------------------------------------
# format_quote_amount_for_product
# ---------------------------------------------------------------------------


class TestFormatQuoteAmountForProduct:
    """Tests for format_quote_amount_for_product()."""

    def test_btc_pair_rounds_to_precision(self):
        """Happy path: BTC pair rounds to quote precision."""
        pp._PRECISION_CACHE = SAMPLE_PRECISION_DATA
        # DASH-BTC: quote_decimals=6
        result = pp.format_quote_amount_for_product(0.00010174, "DASH-BTC")
        assert result == "0.00010200"

    def test_usd_pair_rounds_to_2(self):
        """Happy path: USD pair rounds to 2 decimals then formats to 8."""
        pp._PRECISION_CACHE = SAMPLE_PRECISION_DATA
        result = pp.format_quote_amount_for_product(10.5678, "ETH-USD")
        assert result == "10.57000000"

    def test_zero_amount(self):
        """Edge case: zero amount formatted correctly."""
        pp._PRECISION_CACHE = SAMPLE_PRECISION_DATA
        result = pp.format_quote_amount_for_product(0.0, "ETH-USD")
        assert result == "0.00000000"

    def test_very_small_amount(self):
        """Edge case: very small BTC amount."""
        pp._PRECISION_CACHE = SAMPLE_PRECISION_DATA
        result = pp.format_quote_amount_for_product(0.000001, "DASH-BTC")
        assert result == "0.00000100"


# ---------------------------------------------------------------------------
# format_base_amount_for_product
# ---------------------------------------------------------------------------


class TestFormatBaseAmountForProduct:
    """Tests for format_base_amount_for_product()."""

    def test_decimal_precision(self):
        """Happy path: formats with correct base precision."""
        pp._PRECISION_CACHE = SAMPLE_PRECISION_DATA
        # DASH-BTC: base_increment="0.001" -> 3 decimals
        result = pp.format_base_amount_for_product(1.23456, "DASH-BTC")
        assert result == "1.23500000"

    def test_whole_numbers_only(self):
        """Happy path: base_increment=1 rounds to whole numbers."""
        pp._PRECISION_CACHE = SAMPLE_PRECISION_DATA
        # XLM-BTC: base_increment="1" -> 0 decimals
        result = pp.format_base_amount_for_product(42.789, "XLM-BTC")
        assert result == "43.00000000"

    def test_unknown_product_8_decimals(self):
        """Edge case: unknown product uses 8 decimal precision."""
        pp._PRECISION_CACHE = {}
        result = pp.format_base_amount_for_product(1.123456789, "UNKNOWN-USD")
        assert result == "1.12345679"

    def test_zero_amount(self):
        """Edge case: zero amount."""
        pp._PRECISION_CACHE = SAMPLE_PRECISION_DATA
        result = pp.format_base_amount_for_product(0.0, "DASH-BTC")
        assert result == "0.00000000"
