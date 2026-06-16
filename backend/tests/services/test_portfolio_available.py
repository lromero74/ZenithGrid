"""Math tests for available_from_wallet — the authoritative 'available to deploy' calc.

Regression guard for the Overall-stats balance bug where open-position spend was
subtracted from the live wallet a second time (the wallet already reflects the spend),
understating available funds.
"""
import pytest

from app.services.portfolio_service import available_from_wallet


def test_available_is_wallet_minus_pending_only():
    # Wallet $29.43, nothing pending -> all of it is available (the real-account case
    # that displayed $12.85 before the fix).
    assert available_from_wallet(29.42883893, 0.0) == pytest.approx(29.42883893)


def test_pending_orders_are_subtracted():
    # $100 wallet, $10 committed to an unfilled limit buy -> $90 available.
    assert available_from_wallet(100.0, 10.0) == pytest.approx(90.0)


def test_open_position_spend_is_not_a_parameter():
    # The signature has no position-reserve input by design: position spend can never
    # be subtracted here. Same wallet+pending -> same answer regardless of any open
    # position cost basis.
    assert available_from_wallet(100.0, 10.0) == available_from_wallet(100.0, 10.0)


def test_floors_at_zero_when_pending_exceeds_wallet():
    assert available_from_wallet(5.0, 10.0) == 0.0


def test_zero_wallet_zero_pending_is_zero():
    assert available_from_wallet(0.0, 0.0) == 0.0
