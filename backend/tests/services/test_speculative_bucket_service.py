"""
Tests for backend/app/services/speculative_bucket_service.py

Cost-basis accounting for the account-level speculative bucket. Follows
the query+fixture pattern used in test_budget_calculator.py.
"""

import pytest

from app.models import Account, Bot, Position, User
from app.services.speculative_bucket_service import (
    get_speculative_bucket_info,
    validate_speculative_entry,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


async def _make_user_account(db_session, *, email="spec@test.com",
                             allocation_pct=5.0, name="SpecAcct",
                             rebalance_enabled=False, min_balance_usd=0.0):
    user = User(email=email, hashed_password="hash", is_active=True)
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id, name=name, type="cex",
        is_active=True, is_default=True,
        speculative_allocation_pct=allocation_pct,
        rebalance_enabled=rebalance_enabled,
        min_balance_usd=min_balance_usd,
    )
    db_session.add(account)
    await db_session.flush()
    return user, account


async def _make_bot(db_session, *, user, account, name="SpecBot",
                    is_speculative=True, extra_config=None):
    # Store as JSON string "true"/"false" to match the enable_bidirectional
    # convention — PG vs SQLite extract JSON bools differently (see
    # speculative_bucket_service._speculative_bot_filter docstring).
    cfg = {"is_speculative": "true" if is_speculative else "false"}
    if extra_config:
        cfg.update(extra_config)
    bot = Bot(
        user_id=user.id, account_id=account.id,
        name=name, strategy_type="indicator_based",
        strategy_config=cfg,
        is_active=True,
    )
    db_session.add(bot)
    await db_session.flush()
    return bot


async def _make_position(db_session, *, bot, product_id="HYPE-USD",
                         total_quote_spent=50.0, status="open",
                         average_buy_price=1.0, total_base_acquired=None):
    pos = Position(
        bot_id=bot.id,
        account_id=bot.account_id,
        product_id=product_id,
        status=status,
        initial_quote_balance=total_quote_spent,
        max_quote_allowed=total_quote_spent,
        total_quote_spent=total_quote_spent,
        total_base_acquired=(total_base_acquired if total_base_acquired is not None
                             else total_quote_spent / max(average_buy_price, 1e-9)),
        average_buy_price=average_buy_price,
    )
    db_session.add(pos)
    await db_session.flush()
    return pos


# ---------------------------------------------------------------------------
# get_speculative_bucket_info
# ---------------------------------------------------------------------------


class TestGetSpeculativeBucketInfo:
    """Bucket snapshot math — cost-basis only, account-scoped."""

    @pytest.mark.asyncio
    async def test_empty_account_returns_full_headroom(self, db_session):
        """Happy path: no speculative bots yet → bucket is fully available."""
        user, account = await _make_user_account(db_session, allocation_pct=5.0)

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        assert info["bucket_pct"] == 5.0
        assert info["bucket_usd"] == 500.0
        assert info["deployed_cost_basis_usd"] == 0.0
        assert info["available_usd"] == 500.0
        assert info["active_bot_count"] == 0
        assert info["open_position_count"] == 0

    @pytest.mark.asyncio
    async def test_one_bot_one_position_deducts_cost_basis(self, db_session):
        """Happy path: a single open position reduces headroom by its cost basis."""
        user, account = await _make_user_account(db_session, allocation_pct=5.0)
        bot = await _make_bot(db_session, user=user, account=account)
        await _make_position(db_session, bot=bot, total_quote_spent=50.0)

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        assert info["bucket_usd"] == 500.0
        assert info["deployed_cost_basis_usd"] == 50.0
        assert info["available_usd"] == 450.0
        assert info["active_bot_count"] == 1
        assert info["open_position_count"] == 1

    @pytest.mark.asyncio
    async def test_winner_does_not_expand_headroom(self, db_session):
        """Cost-basis semantics: a 2x winner still counts its original cost,
        NOT its mark-to-market value. This is the whole point of the bucket."""
        user, account = await _make_user_account(db_session, allocation_pct=5.0)
        bot = await _make_bot(db_session, user=user, account=account)
        # Cost basis = 100; current price doubled (average_buy_price=1.0,
        # base_acquired=100 → notional value at 2x = 200). But bucket math
        # should still say 100 is deployed.
        await _make_position(
            db_session, bot=bot, total_quote_spent=100.0,
            average_buy_price=1.0, total_base_acquired=100.0,
        )

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        assert info["deployed_cost_basis_usd"] == 100.0  # not 200
        assert info["available_usd"] == 400.0  # 500 - 100, not 500 - 200

    @pytest.mark.asyncio
    async def test_multi_bot_aggregates_cost_basis(self, db_session):
        """Two speculative bots on the same account → their cost bases sum."""
        user, account = await _make_user_account(db_session, allocation_pct=5.0)
        bot_a = await _make_bot(db_session, user=user, account=account, name="A")
        bot_b = await _make_bot(db_session, user=user, account=account, name="B")

        await _make_position(db_session, bot=bot_a, total_quote_spent=75.0)
        await _make_position(db_session, bot=bot_a, total_quote_spent=25.0,
                             product_id="DOGE-USD")
        await _make_position(db_session, bot=bot_b, total_quote_spent=150.0,
                             product_id="SOL-USD")

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        assert info["deployed_cost_basis_usd"] == 250.0  # 75 + 25 + 150
        assert info["available_usd"] == 250.0  # 500 - 250
        assert info["active_bot_count"] == 2
        assert info["open_position_count"] == 3

    @pytest.mark.asyncio
    async def test_non_speculative_bots_excluded(self, db_session):
        """A bot without is_speculative=true must not contribute to the bucket."""
        user, account = await _make_user_account(db_session, allocation_pct=5.0)
        spec_bot = await _make_bot(db_session, user=user, account=account,
                                   name="Spec", is_speculative=True)
        plain_bot = await _make_bot(db_session, user=user, account=account,
                                    name="Plain", is_speculative=False)

        await _make_position(db_session, bot=spec_bot, total_quote_spent=50.0)
        await _make_position(db_session, bot=plain_bot, total_quote_spent=500.0,
                             product_id="BTC-USD")

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        assert info["deployed_cost_basis_usd"] == 50.0
        assert info["active_bot_count"] == 1
        assert info["open_position_count"] == 1

    @pytest.mark.asyncio
    async def test_closed_positions_excluded(self, db_session):
        """Only open positions count toward deployed cost basis."""
        user, account = await _make_user_account(db_session, allocation_pct=5.0)
        bot = await _make_bot(db_session, user=user, account=account)
        await _make_position(db_session, bot=bot, total_quote_spent=50.0, status="open")
        await _make_position(db_session, bot=bot, total_quote_spent=1000.0,
                             status="closed", product_id="OLD-USD")

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        assert info["deployed_cost_basis_usd"] == 50.0
        assert info["open_position_count"] == 1

    @pytest.mark.asyncio
    async def test_account_isolation(self, db_session):
        """A speculative bot on account B must not affect account A's bucket."""
        user_a, account_a = await _make_user_account(
            db_session, email="a@test.com", allocation_pct=5.0, name="A",
        )
        user_b, account_b = await _make_user_account(
            db_session, email="b@test.com", allocation_pct=5.0, name="B",
        )
        bot_a = await _make_bot(db_session, user=user_a, account=account_a, name="BotA")
        bot_b = await _make_bot(db_session, user=user_b, account=account_b, name="BotB")

        await _make_position(db_session, bot=bot_a, total_quote_spent=100.0)
        await _make_position(db_session, bot=bot_b, total_quote_spent=400.0,
                             product_id="SOL-USD")

        info_a = await get_speculative_bucket_info(
            db_session, account_a.id, aggregate_usd_value=10_000.0,
        )
        info_b = await get_speculative_bucket_info(
            db_session, account_b.id, aggregate_usd_value=10_000.0,
        )

        assert info_a["deployed_cost_basis_usd"] == 100.0
        assert info_b["deployed_cost_basis_usd"] == 400.0

    @pytest.mark.asyncio
    async def test_zero_allocation_gives_zero_bucket(self, db_session):
        """Edge case: user hasn't configured an allocation — bucket is 0."""
        user, account = await _make_user_account(db_session, allocation_pct=0.0)

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        assert info["bucket_pct"] == 0.0
        assert info["bucket_usd"] == 0.0
        assert info["available_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_btc_quote_cost_basis_converted_to_usd(self, db_session):
        """A BTC-quote bot's cost basis must be multiplied by btc_usd_price."""
        user, account = await _make_user_account(db_session, allocation_pct=5.0)
        bot = await _make_bot(db_session, user=user, account=account)
        # 0.001 BTC cost basis; at $100k/BTC → $100 USD
        await _make_position(db_session, bot=bot, product_id="ETH-BTC",
                             total_quote_spent=0.001, average_buy_price=0.05)

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
            btc_usd_price=100_000.0,
        )

        assert info["deployed_cost_basis_usd"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# validate_speculative_entry
# ---------------------------------------------------------------------------


class TestValidateSpeculativeEntry:
    @pytest.mark.asyncio
    async def test_allowed_when_bucket_has_room(self, db_session):
        user, account = await _make_user_account(db_session, allocation_pct=5.0)
        bot = await _make_bot(db_session, user=user, account=account)

        allowed, reason = await validate_speculative_entry(
            db_session, bot, intended_cost_basis_usd=50.0,
            aggregate_usd_value=10_000.0,
        )

        assert allowed is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_blocked_when_bucket_full(self, db_session):
        """500 bucket - 450 deployed = 50 available; requesting 100 must fail."""
        user, account = await _make_user_account(db_session, allocation_pct=5.0)
        bot = await _make_bot(db_session, user=user, account=account)
        await _make_position(db_session, bot=bot, total_quote_spent=450.0)

        allowed, reason = await validate_speculative_entry(
            db_session, bot, intended_cost_basis_usd=100.0,
            aggregate_usd_value=10_000.0,
        )

        assert allowed is False
        assert "Speculative bucket full" in reason
        assert "100.00" in reason
        assert "50.00" in reason  # available

    @pytest.mark.asyncio
    async def test_blocked_when_no_bucket_configured(self, db_session):
        """allocation_pct=0 → always blocked with an actionable message."""
        user, account = await _make_user_account(db_session, allocation_pct=0.0)
        bot = await _make_bot(db_session, user=user, account=account)

        allowed, reason = await validate_speculative_entry(
            db_session, bot, intended_cost_basis_usd=10.0,
            aggregate_usd_value=10_000.0,
        )

        assert allowed is False
        assert "not configured" in reason.lower()

    @pytest.mark.asyncio
    async def test_allowed_when_intended_is_zero(self, db_session):
        """Edge case: a zero-cost-basis request is trivially allowed —
        downstream budget checks decide on the real order size."""
        user, account = await _make_user_account(db_session, allocation_pct=5.0)
        bot = await _make_bot(db_session, user=user, account=account)

        allowed, reason = await validate_speculative_entry(
            db_session, bot, intended_cost_basis_usd=0.0,
            aggregate_usd_value=10_000.0,
        )

        assert allowed is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_exact_headroom_allowed(self, db_session):
        """Boundary: intended == available must be allowed (<=, not <)."""
        user, account = await _make_user_account(db_session, allocation_pct=5.0)
        bot = await _make_bot(db_session, user=user, account=account)

        allowed, reason = await validate_speculative_entry(
            db_session, bot, intended_cost_basis_usd=500.0,  # exactly matches bucket
            aggregate_usd_value=10_000.0,
        )

        assert allowed is True


class TestRebalanceFloorWarning:
    """The bucket card surfaces a warning when the rebalancer's USD floor is
    set too low relative to the per-slot budget. If it is, the rebalancer can
    drain free cash out from under the speculative bot between entries, even
    though the bucket itself still shows headroom.

    Threshold: min_balance_usd must be at least 2x per_slot_budget_usd. That
    multiple is a rule of thumb — one slot's worth plus a cushion for fees
    and the next candidate entry. See accounts settings + PRP §F.
    """

    @pytest.mark.asyncio
    async def test_no_warning_when_rebalance_disabled(self, db_session):
        """If rebalance is off, min_balance_usd doesn't kick in → no warning
        regardless of its value."""
        user, account = await _make_user_account(
            db_session, allocation_pct=5.0,
            rebalance_enabled=False, min_balance_usd=0.0,
        )
        await _make_bot(db_session, user=user, account=account)

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        codes = {w["code"] for w in info["warnings"]}
        assert "rebalance_floor_too_low" not in codes

    @pytest.mark.asyncio
    async def test_warning_when_floor_below_two_slots(self, db_session):
        """Rebalance on, per-slot=500, floor=100 → warn."""
        user, account = await _make_user_account(
            db_session, allocation_pct=5.0,
            rebalance_enabled=True, min_balance_usd=100.0,
        )
        # One bot with max_concurrent_deals=1 → per_slot_budget = bucket_usd.
        await _make_bot(db_session, user=user, account=account)

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        codes = {w["code"] for w in info["warnings"]}
        assert "rebalance_floor_too_low" in codes
        warn = next(w for w in info["warnings"]
                    if w["code"] == "rebalance_floor_too_low")
        # Message must tell the user what the floor IS and what it SHOULD be.
        assert "100" in warn["message"]
        assert "1000" in warn["message"]  # 2x per-slot of 500

    @pytest.mark.asyncio
    async def test_no_warning_when_floor_meets_threshold(self, db_session):
        """Rebalance on, per-slot=500, floor=1000 → no warning (exactly 2x)."""
        user, account = await _make_user_account(
            db_session, allocation_pct=5.0,
            rebalance_enabled=True, min_balance_usd=1000.0,
        )
        await _make_bot(db_session, user=user, account=account)

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        codes = {w["code"] for w in info["warnings"]}
        assert "rebalance_floor_too_low" not in codes

    @pytest.mark.asyncio
    async def test_no_warning_when_no_bucket_configured(self, db_session):
        """If bucket_pct is 0 there are no speculative entries to protect,
        so do not pester the user about their rebalance floor."""
        user, account = await _make_user_account(
            db_session, allocation_pct=0.0,
            rebalance_enabled=True, min_balance_usd=0.0,
        )

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        codes = {w["code"] for w in info["warnings"]}
        assert "rebalance_floor_too_low" not in codes

    @pytest.mark.asyncio
    async def test_warnings_field_is_always_a_list(self, db_session):
        """Shape contract: warnings is always a list, never missing or null."""
        user, account = await _make_user_account(db_session, allocation_pct=5.0)

        info = await get_speculative_bucket_info(
            db_session, account.id, aggregate_usd_value=10_000.0,
        )

        assert "warnings" in info
        assert isinstance(info["warnings"], list)
