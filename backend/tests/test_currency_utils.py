"""Tests for app/currency_utils.py"""

from app.currency_utils import (
    format_base_amount,
    format_price,
    format_quote_amount,
    format_with_usd,
    get_base_currency,
    get_base_decimals,
    get_currencies_from_pair,
    get_quote_currency,
    get_quote_decimals,
)


class TestGetCurrenciesFromPair:
    def test_btc_pair(self):
        assert get_currencies_from_pair("ETH-BTC") == ("ETH", "BTC")

    def test_usd_pair(self):
        assert get_currencies_from_pair("BTC-USD") == ("BTC", "USD")

    def test_no_separator_returns_default(self):
        assert get_currencies_from_pair("ETHBTC") == ("ETH", "BTC")

    def test_multi_segment_pair(self):
        base, quote = get_currencies_from_pair("BTC-PERP-INTX")
        assert base == "BTC"
        assert quote == "PERP"


class TestGetQuoteCurrency:
    def test_btc_pair(self):
        assert get_quote_currency("ADA-BTC") == "BTC"

    def test_usd_pair(self):
        assert get_quote_currency("ETH-USD") == "USD"


class TestGetBaseCurrency:
    def test_returns_base(self):
        assert get_base_currency("DASH-BTC") == "DASH"


class TestFormatQuoteAmount:
    def test_usd_formatting(self):
        assert format_quote_amount(15.42, "BTC-USD") == "$15.42"

    def test_btc_formatting(self):
        result = format_quote_amount(0.00057, "ETH-BTC")
        assert "0.00057000" in result
        assert "BTC" in result


class TestFormatBaseAmount:
    def test_formats_with_8_decimals(self):
        result = format_base_amount(1.5, "ETH-BTC")
        assert "1.50000000" in result
        assert "ETH" in result


class TestFormatPrice:
    def test_usd_price(self):
        assert format_price(50000.0, "BTC-USD") == "$50000.00"

    def test_btc_price(self):
        result = format_price(0.05, "ETH-BTC")
        assert "0.05000000" in result
        assert "BTC" in result


class TestFormatWithUsd:
    def test_usd_pair_no_conversion(self):
        assert format_with_usd(100.0, "BTC-USD") == "$100.00"

    def test_btc_pair_with_usd_price(self):
        result = format_with_usd(0.001, "ETH-BTC", btc_usd_price=50000.0)
        assert "0.00100000 BTC" in result
        assert "$50.00 USD" in result

    def test_btc_pair_without_usd_price(self):
        result = format_with_usd(0.001, "ETH-BTC", btc_usd_price=None)
        assert "0.00100000 BTC" in result
        assert "USD" not in result


class TestGetDecimals:
    def test_usd_quote_decimals(self):
        assert get_quote_decimals("BTC-USD") == 2

    def test_btc_quote_decimals(self):
        assert get_quote_decimals("ETH-BTC") == 8

    def test_base_decimals_always_8(self):
        assert get_base_decimals("ETH-BTC") == 8
        assert get_base_decimals("BTC-USD") == 8
