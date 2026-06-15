"""Tests for the real-money order/trace audit trail."""
import json
import logging

import pytest

from app.services.realmoney_audit import (
    record_order, record_event, subsystem, set_subsystem, current_subsystem,
    audit_logger,
)


class TestSubsystemContext:
    def test_default_is_unknown(self):
        # Outside any scope the subsystem is "unknown" (never blank).
        assert current_subsystem() == "unknown"

    def test_context_manager_sets_and_resets(self):
        assert current_subsystem() == "unknown"
        with subsystem("dust_sweep"):
            assert current_subsystem() == "dust_sweep"
        assert current_subsystem() == "unknown"

    def test_blank_name_falls_back_to_unknown(self):
        with subsystem(""):
            assert current_subsystem() == "unknown"

    def test_set_subsystem_token_resets(self):
        token = set_subsystem("rebalancer")
        try:
            assert current_subsystem() == "rebalancer"
        finally:
            from app.services import realmoney_audit
            realmoney_audit._subsystem_var.reset(token)
        assert current_subsystem() == "unknown"


class TestRecordOrder:
    def test_success_order_captures_id_and_fields(self):
        with subsystem("bot:rsi:39"):
            rec = record_order(
                account_id=1, side="sell", product_id="FOX-USD",
                order_type="market", size="296.4",
                result={"success_response": {"order_id": "abc-123"}},
            )
        assert rec["status"] == "success"
        assert rec["order_id"] == "abc-123"
        assert rec["subsystem"] == "bot:rsi:39"
        assert rec["account_id"] == 1
        assert rec["side"] == "SELL"
        assert rec["product_id"] == "FOX-USD"
        assert rec["size"] == "296.4"
        assert rec["ts"]  # timestamp present

    def test_failed_order_captures_error(self):
        rec = record_order(
            account_id=1, side="SELL", product_id="JTO-USD",
            result={"error_response": {"error": "INSUFFICIENT_FUND",
                                       "message": "Insufficient balance"}},
        )
        assert rec["status"] == "failed"
        assert rec["order_id"] == ""
        assert rec["error"]["error"] == "INSUFFICIENT_FUND"

    def test_blocked_order_status(self):
        rec = record_order(
            account_id=1, side="BUY", product_id="BTC-USD",
            result={"blocked_by": "propguard", "error": "limit hit"},
        )
        assert rec["status"] == "blocked:propguard"
        assert rec["error"] == "limit hit"

    def test_buy_with_funds_only(self):
        rec = record_order(
            account_id=2, side="buy", product_id="ETH-USD",
            funds="50.00", result={"order_id": "xyz"},
        )
        assert rec["side"] == "BUY"
        assert rec["funds"] == "50.00"
        assert rec["size"] is None
        assert rec["order_id"] == "xyz"

    def test_emits_one_json_line_to_audit_logger(self):
        seen = []

        class _Cap(logging.Handler):
            def emit(self, record):
                seen.append(record.getMessage())

        h = _Cap()
        audit_logger.addHandler(h)
        try:
            record_order(account_id=1, side="SELL", product_id="FOX-USD",
                         result={"success_response": {"order_id": "o1"}})
        finally:
            audit_logger.removeHandler(h)
        assert len(seen) == 1
        parsed = json.loads(seen[0])  # must be valid JSON
        assert parsed["order_id"] == "o1"

    def test_never_raises_on_garbage_result(self):
        # Defensive: a non-dict result must not blow up the trading path.
        rec = record_order(
            account_id=1, side="SELL", product_id="X-USD", result="not-a-dict")
        assert rec["status"] == "unknown"


class TestRecordEvent:
    def test_clamp_event_has_subsystem_and_fields(self):
        with subsystem("bot:rsi:39"):
            rec = record_event(
                "sell_clamped", account_id=1, position_id=100,
                product_id="FOX-USD", recorded=865.8, available=296.7,
                clamped_to=296.4,
            )
        assert rec["event"] == "sell_clamped"
        assert rec["subsystem"] == "bot:rsi:39"
        assert rec["recorded"] == 865.8
        assert rec["available"] == 296.7
        assert rec["clamped_to"] == 296.4
        assert rec["ts"]


@pytest.mark.asyncio
class TestClientAuditWiring:
    async def test_create_market_order_audits_without_raising(self):
        # The client wrapper must tag the order and return the raw result intact.
        from app.coinbase_unified_client import CoinbaseClient
        client = CoinbaseClient.__new__(CoinbaseClient)
        client.account_id = 7

        async def _fake_request(*a, **k):
            return {"success_response": {"order_id": "real-1"}}

        client._request = _fake_request

        seen = []

        class _Cap(logging.Handler):
            def emit(self, record):
                seen.append(record.getMessage())

        h = _Cap()
        audit_logger.addHandler(h)
        try:
            with subsystem("manual_liquidation"):
                result = await client.create_market_order(
                    product_id="FOX-USD", side="SELL", size="296.4",
                )
        finally:
            audit_logger.removeHandler(h)

        assert result == {"success_response": {"order_id": "real-1"}}
        rec = json.loads(seen[-1])
        assert rec["account_id"] == 7
        assert rec["subsystem"] == "manual_liquidation"
        assert rec["product_id"] == "FOX-USD"
        assert rec["order_id"] == "real-1"
