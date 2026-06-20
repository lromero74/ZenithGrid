from types import SimpleNamespace
from unittest.mock import patch

from app.services.exit_provenance import record_exit_provenance


def test_records_automatic_exit_origin_and_order():
    position = SimpleNamespace(exit_reason=None)
    with patch("app.services.exit_provenance.socket.gethostname", return_value="zenithgrid"):
        unexpected = record_exit_provenance(
            position, trigger_reason="Take profit conditions met", order_id="order-1", process_role="trader",
        )
    assert position.exit_reason == "take_profit"
    assert position.exit_source == "automatic"
    assert position.exit_process_role == "trader"
    assert position.exit_hostname == "zenithgrid"
    assert position.exit_order_id == "order-1"
    assert unexpected is False


def test_manual_exit_is_preserved():
    position = SimpleNamespace(exit_reason="manual")
    record_exit_provenance(position, trigger_reason="Manual close", order_id="order-2", process_role="web")
    assert position.exit_reason == "manual"
    assert position.exit_source == "manual"
    assert position.exit_trigger_reason == "Manual close"


def test_automatic_exit_from_web_role_is_unexpected():
    position = SimpleNamespace(exit_reason=None)
    assert record_exit_provenance(position, trigger_reason="Stop loss", order_id="x", process_role="web") is True
