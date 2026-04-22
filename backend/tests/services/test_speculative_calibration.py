"""
Tests for analyze_speculative_calibration in speculative_bucket_service.

Called by speculative_calibration_monitor to decide whether a user has
accumulated enough signal for a weight-recalibration alert. All queries
are scoped by user_id — one user's closed-position data must not spill
into another's analysis.

Thresholds (all must hold to return a non-None result):
- >=50 closed positions from speculative-tagged bots with
  non-null doubling_probability_score in ai_opinion_log
- at least one component with >=30 fires
- top_component.win_rate - bottom_component.win_rate >= 20pp
"""

from datetime import datetime

import pytest

from app.models import Account, AIOpinionLog, Bot, Position, User
from app.services.speculative_bucket_service import (
    analyze_speculative_calibration,
)


# Weight-component order from speculative_signals.WEIGHTS — keeps the test
# fixtures synchronized with the scorer even if weights change later.
_ALL_COMPONENTS = (
    "volume_surge",
    "compression_breakout",
    "momentum_accelerating",
    "micro_mid_cap",
    "correlation_break",
    "volume_vs_mcap",
)


async def _make_user(db, email):
    u = User(email=email, hashed_password="h", is_active=True)
    db.add(u)
    await db.flush()
    return u


async def _make_account(db, user):
    a = Account(user_id=user.id, name=f"A-{user.id}", type="cex",
                is_active=True, is_default=True,
                speculative_allocation_pct=5.0)
    db.add(a)
    await db.flush()
    return a


async def _make_bot(db, user, account, *, is_speculative=True):
    cfg = {"is_speculative": "true" if is_speculative else "false"}
    b = Bot(user_id=user.id, account_id=account.id,
            name=f"Bot-{user.id}", strategy_type="indicator_based",
            strategy_config=cfg, is_active=True)
    db.add(b)
    await db.flush()
    return b


async def _make_closed_position(db, bot, *, profit_pct):
    pos = Position(
        bot_id=bot.id, account_id=bot.account_id, user_id=bot.user_id,
        product_id="HYPE-USD", status="closed",
        opened_at=datetime.utcnow(), closed_at=datetime.utcnow(),
        average_buy_price=1.0, total_quote_spent=50.0, total_base_acquired=50.0,
        profit_percentage=profit_pct,
    )
    db.add(pos)
    await db.flush()
    return pos


def _components(fired_set):
    """Shortcut — builds the [(name, fired, contribution)] list for a log row.

    `fired_set` is a set of component names that fired; everything else is
    marked not-fired with contribution=0. Contributions are intentionally
    not WEIGHTS-accurate (the analysis function only cares about the
    `fired` boolean for per-component fire counting).
    """
    return [
        [name, name in fired_set, (1 if name in fired_set else 0)]
        for name in _ALL_COMPONENTS
    ]


async def _seed_log(db, *, user, account, bot, position, fired_set,
                    score=50):
    row = AIOpinionLog(
        user_id=user.id, account_id=account.id, bot_id=bot.id,
        position_id=position.id, product_id="HYPE-USD",
        is_sell_check=False, signal="buy", confidence=60,
        reasoning="spec", ai_model="claude",
        doubling_probability_score=score,
        speculative_score=score,
        speculative_components=_components(fired_set),
    )
    db.add(row)
    await db.flush()
    return row


class TestAnalyzeSpeculativeCalibration:
    """Phase F Task F2 — the gate that fires the recalibration email."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_analysis(self, db_session):
        """50+ closed positions, a fire-heavy component, and >=20pp divergence
        between its win rate and the bottom component's win rate. The helper
        must return an analysis dict with the shape documented in the PRP."""
        user = await _make_user(db_session, "happy@t.com")
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, user, account)

        # 40 positions where volume_surge fires + wins 80% (32W/8L)
        for i in range(40):
            pos = await _make_closed_position(
                db_session, bot, profit_pct=(5.0 if i < 32 else -3.0),
            )
            await _seed_log(
                db_session, user=user, account=account, bot=bot,
                position=pos, fired_set={"volume_surge", "correlation_break"},
            )

        # 30 positions where correlation_break fires on its own + loses 90%
        for i in range(30):
            pos = await _make_closed_position(
                db_session, bot, profit_pct=(5.0 if i < 3 else -3.0),
            )
            await _seed_log(
                db_session, user=user, account=account, bot=bot,
                position=pos, fired_set={"correlation_break"},
            )

        result = await analyze_speculative_calibration(db_session, user.id)

        assert result is not None
        # 70 rows total, 35 wins (32 + 3), 35 losses
        assert result["total_closed"] == 70
        assert result["wins"] == 35
        assert result["losses"] == 35
        assert result["overall_win_rate_pct"] == pytest.approx(50.0, abs=0.01)

        # volume_surge: 40 fires, 32/40 wins = 80%
        # correlation_break: 70 fires, 35/70 wins = 50%
        names = {c["name"]: c for c in result["components"]}
        assert names["volume_surge"]["fires"] == 40
        assert names["volume_surge"]["win_rate_pct"] == pytest.approx(80.0, abs=0.01)
        assert names["correlation_break"]["fires"] == 70
        assert names["correlation_break"]["win_rate_pct"] == pytest.approx(50.0, abs=0.01)

        assert result["top_component"] == "volume_surge"
        assert result["bottom_component"] == "correlation_break"
        assert result["divergence_pp"] == pytest.approx(30.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_under_sample_threshold_returns_none(self, db_session):
        """Fewer than 50 closed speculative positions → not enough signal yet."""
        user = await _make_user(db_session, "few@t.com")
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, user, account)

        for i in range(40):
            pos = await _make_closed_position(
                db_session, bot, profit_pct=(5.0 if i < 20 else -3.0),
            )
            await _seed_log(
                db_session, user=user, account=account, bot=bot,
                position=pos, fired_set={"volume_surge"},
            )

        assert await analyze_speculative_calibration(db_session, user.id) is None

    @pytest.mark.asyncio
    async def test_flat_components_returns_none(self, db_session):
        """Enough rows, plenty of fires, but all components within 5pp of each
        other → nothing to calibrate, no alert."""
        user = await _make_user(db_session, "flat@t.com")
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, user, account)

        # 60 positions, every row has all components fired, outcome split
        # 30/30 so every component's win rate is ~50%.
        for i in range(60):
            pos = await _make_closed_position(
                db_session, bot, profit_pct=(5.0 if i < 30 else -3.0),
            )
            await _seed_log(
                db_session, user=user, account=account, bot=bot,
                position=pos, fired_set=set(_ALL_COMPONENTS),
            )

        assert await analyze_speculative_calibration(db_session, user.id) is None

    @pytest.mark.asyncio
    async def test_ignores_non_speculative_bots(self, db_session):
        """Positions from bots not tagged is_speculative must not count."""
        user = await _make_user(db_session, "mixed@t.com")
        account = await _make_account(db_session, user)
        non_spec_bot = await _make_bot(
            db_session, user, account, is_speculative=False,
        )

        for i in range(60):
            pos = await _make_closed_position(
                db_session, non_spec_bot, profit_pct=(5.0 if i < 50 else -3.0),
            )
            await _seed_log(
                db_session, user=user, account=account, bot=non_spec_bot,
                position=pos, fired_set={"volume_surge"},
            )

        assert await analyze_speculative_calibration(db_session, user.id) is None

    @pytest.mark.asyncio
    async def test_multi_user_isolation(self, db_session):
        """User A's activity must not change user B's analysis result."""
        user_a = await _make_user(db_session, "a@t.com")
        account_a = await _make_account(db_session, user_a)
        bot_a = await _make_bot(db_session, user_a, account_a)

        user_b = await _make_user(db_session, "b@t.com")
        account_b = await _make_account(db_session, user_b)
        await _make_bot(db_session, user_b, account_b)

        # User A has enough data + divergence → would alert.
        for i in range(40):
            pos = await _make_closed_position(
                db_session, bot_a, profit_pct=(5.0 if i < 32 else -3.0),
            )
            await _seed_log(
                db_session, user=user_a, account=account_a, bot=bot_a,
                position=pos, fired_set={"volume_surge", "correlation_break"},
            )
        for i in range(30):
            pos = await _make_closed_position(
                db_session, bot_a, profit_pct=(5.0 if i < 3 else -3.0),
            )
            await _seed_log(
                db_session, user=user_a, account=account_a, bot=bot_a,
                position=pos, fired_set={"correlation_break"},
            )

        # Must return a real result for user A, None for user B.
        assert await analyze_speculative_calibration(db_session, user_a.id) is not None
        assert await analyze_speculative_calibration(db_session, user_b.id) is None

    @pytest.mark.asyncio
    async def test_skips_rows_with_null_doubling_score(self, db_session):
        """Rows missing doubling_probability_score (e.g. classic-mode fallback
        on a speculative bot) don't count toward the threshold."""
        user = await _make_user(db_session, "null@t.com")
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, user, account)

        for i in range(60):
            pos = await _make_closed_position(
                db_session, bot, profit_pct=(5.0 if i < 40 else -3.0),
            )
            row = AIOpinionLog(
                user_id=user.id, account_id=account.id, bot_id=bot.id,
                position_id=pos.id, product_id="HYPE-USD",
                is_sell_check=False, signal="buy", confidence=60,
                reasoning="r", ai_model="claude",
                doubling_probability_score=None,  # explicitly null
                speculative_score=50,
                speculative_components=_components({"volume_surge"}),
            )
            db_session.add(row)
        await db_session.flush()

        assert await analyze_speculative_calibration(db_session, user.id) is None
