"""Tests for app/precision.py"""

from app.precision import format_base_amount, format_quote_amount


class TestFormatQuoteAmount:
    def test_btc_rounds_to_8_decimals(self):
        result = format_quote_amount(0.00012345678, "BTC")
        # Rounds DOWN to 8 decimals
        assert result == "0.00012345"

    def test_usd_rounds_to_2_decimals(self):
        result = format_quote_amount(10.5678, "USD")
        # Rounds DOWN to 2 decimals
        assert result == "10.56"

    def test_rounds_down_not_up(self):
        result = format_quote_amount(0.99999999, "USD")
        assert result == "0.99"

    def test_zero(self):
        result = format_quote_amount(0.0, "BTC")
        assert result == "0E-8"

    def test_small_btc_amount(self):
        result = format_quote_amount(0.000001, "BTC")
        assert result == "0.00000100"

    def test_preserves_trailing_zeros(self):
        """Coinbase requires fixed precision format"""
        result = format_quote_amount(1.5, "BTC")
        assert result == "1.50000000"


class TestFormatBaseAmount:
    def test_crypto_8_decimals(self):
        result = format_base_amount(1.23456789, "ETH")
        assert result == "1.23456789"

    def test_rounds_down(self):
        result = format_base_amount(0.999999999, "ETH")
        assert result == "0.99999999"

    def test_zero(self):
        result = format_base_amount(0.0, "DASH")
        assert result == "0E-8"

    def test_large_amount(self):
        result = format_base_amount(12345.6789, "XRP")
        assert result == "12345.67890000"
