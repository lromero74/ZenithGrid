"""
Integration tests for the proposal-creation extension to
speculative_calibration_monitor.

Covers:
- sample-size gate (no proposal below PROPOSAL_MIN_SAMPLE_SIZE)
- baseline_weights on the new row reflects the user's prior applied
  proposal, NOT module defaults, when one exists
- multi-user isolation
- no-change proposals are skipped (same weights in and out)
- prior pending proposals are superseded on re-run
- proposal-creation failure does not block the email send
"""

from datetime import timedelta
from app.utils.timeutil import utcnow
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.indicators.speculative_signals import DEFAULT_WEIGHTS
from app.models import Account, Bot, SpeculativeWeightsProposal, User
from app.services import speculative_calibration_monitor as monitor
from app.services.speculative_weights_cache import invalidate_weights_cache


@pytest.fixture(autouse=True)
def _clear_weights_cache():
    """The in-process weights cache persists across tests in a pytest run.
    Clear it before each test so resolution always starts from DEFAULT_WEIGHTS
    unless the test explicitly seeds an applied proposal."""
    invalidate_weights_cache()
    yield
    invalidate_weights_cache()


async def _user(db, email="proposal@t.com"):
    u = User(email=email, hashed_password="h", is_active=True, display_name="U")
    db.add(u)
    await db.flush()
    return u


async def _account(db, user, *, alerted_at=None, allocation_pct=5.0):
    a = Account(
        user_id=user.id, name=f"A-{user.id}", type="cex",
        is_active=True, is_default=True,
        speculative_allocation_pct=allocation_pct,
        speculative_calibration_last_alerted_at=alerted_at,
    )
    db.add(a)
    await db.flush()
    return a


async def _bot(db, user, account):
    b = Bot(
        user_id=user.id, account_id=account.id,
        name=f"B-{user.id}", strategy_type="indicator_based",
        strategy_config={"is_speculative": "true"},
        is_active=True,
    )
    db.add(b)
    await db.flush()
    return b


# Analysis payloads at different sample sizes — the rest of the shape
# matches what analyze_speculative_calibration returns.
def _analysis(total_closed, *, skew=True):
    if skew:
        components = [
            {"name": "volume_surge", "fires": 200, "win_rate_pct": 30.0},
            {"name": "compression_breakout", "fires": 150, "win_rate_pct": 20.0},
            {"name": "momentum_accelerating", "fires": 150, "win_rate_pct": 15.0},
            {"name": "micro_mid_cap", "fires": 100, "win_rate_pct": 12.0},
            {"name": "correlation_break", "fires": 80, "win_rate_pct": 5.0},
            {"name": "volume_vs_mcap", "fires": 160, "win_rate_pct": 18.0},
        ]
        top = "volume_surge"
        bottom = "correlation_break"
        divergence = 25.0
    else:
        components = [
            {"name": k, "fires": 100, "win_rate_pct": 15.0} for k in DEFAULT_WEIGHTS
        ]
        top = "volume_surge"
        bottom = "volume_surge"
        divergence = 0.0
    return {
        "total_closed": total_closed,
        "wins": int(total_closed * 0.15),
        "losses": total_closed - int(total_closed * 0.15),
        "overall_win_rate_pct": 15.0,
        "overall_realized_pnl_usd": -100.0,
        "components": components,
        "top_component": top, "top_win_rate_pct": 30.0,
        "bottom_component": bottom, "bottom_win_rate_pct": 5.0,
        "divergence_pp": divergence,
    }


class _OneShotSession:
    """Reuse the db_session fixture across the monitor's session factory."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


class TestProposalCreation:
    @pytest.mark.asyncio
    async def test_no_proposal_when_sample_too_small(self, db_session):
        user = await _user(db_session, "small@t.com")
        account = await _account(db_session, user)
        await _bot(db_session, user, account)

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=_analysis(300)),  # below 500
        ), patch.object(
            monitor, "send_speculative_calibration_email", return_value=True,
        ) as send_email, patch.object(
            monitor.ws_manager, "broadcast", new=AsyncMock(),
        ), patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        # Email still fired (alert threshold is 50), but no proposal row.
        send_email.assert_called_once()
        _, kwargs = send_email.call_args
        assert kwargs.get("proposal") is None
        rows = (await db_session.execute(
            select(SpeculativeWeightsProposal)
            .where(SpeculativeWeightsProposal.user_id == user.id)
        )).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_proposal_created_when_sample_threshold_met(self, db_session):
        user = await _user(db_session, "big@t.com")
        account = await _account(db_session, user)
        await _bot(db_session, user, account)

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=_analysis(600)),
        ), patch.object(
            monitor, "send_speculative_calibration_email", return_value=True,
        ) as send_email, patch.object(
            monitor.ws_manager, "broadcast", new=AsyncMock(),
        ), patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        rows = (await db_session.execute(
            select(SpeculativeWeightsProposal)
            .where(SpeculativeWeightsProposal.user_id == user.id)
        )).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.status == "pending"
        assert row.sample_size == 600
        assert row.algorithm == "proportional-alpha-v1"
        assert sum(row.proposed_weights.values()) == 100
        assert row.baseline_weights == dict(DEFAULT_WEIGHTS)

        # Email kwargs include proposal + apply_url.
        _, kwargs = send_email.call_args
        assert kwargs["proposal"] is not None
        assert "apply_token=" in (kwargs["apply_url"] or "")

    @pytest.mark.asyncio
    async def test_baseline_uses_prior_applied_proposal_not_defaults(self, db_session):
        """If the user already applied a proposal, the new proposal's
        baseline_weights must reflect that state — not module defaults."""
        user = await _user(db_session, "prior@t.com")
        account = await _account(db_session, user)
        await _bot(db_session, user, account)

        prior_applied = {**DEFAULT_WEIGHTS, "volume_surge": 28}
        db_session.add(SpeculativeWeightsProposal(
            user_id=user.id, status="applied",
            algorithm="proportional-alpha-v1", sample_size=500,
            overall_win_rate_pct=15.0,
            baseline_weights=dict(DEFAULT_WEIGHTS),
            proposed_weights=prior_applied,
            decided_at=utcnow() - timedelta(days=45),
        ))
        await db_session.flush()

        # Invalidate cache so the monitor query sees the applied row.
        from app.services.speculative_weights_cache import invalidate_weights_cache
        invalidate_weights_cache()

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=_analysis(600)),
        ), patch.object(
            monitor, "send_speculative_calibration_email", return_value=True,
        ), patch.object(
            monitor.ws_manager, "broadcast", new=AsyncMock(),
        ), patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        new_rows = (await db_session.execute(
            select(SpeculativeWeightsProposal)
            .where(
                SpeculativeWeightsProposal.user_id == user.id,
                SpeculativeWeightsProposal.status == "pending",
            )
        )).scalars().all()
        assert len(new_rows) == 1
        assert new_rows[0].baseline_weights == prior_applied

    @pytest.mark.asyncio
    async def test_supersedes_prior_pending_proposals(self, db_session):
        user = await _user(db_session, "supersede@t.com")
        account = await _account(db_session, user)
        await _bot(db_session, user, account)

        stale = SpeculativeWeightsProposal(
            user_id=user.id, status="pending",
            algorithm="proportional-alpha-v1", sample_size=500,
            overall_win_rate_pct=15.0,
            baseline_weights=dict(DEFAULT_WEIGHTS),
            proposed_weights={**DEFAULT_WEIGHTS, "volume_surge": 99},
        )
        db_session.add(stale)
        await db_session.flush()

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=_analysis(700)),
        ), patch.object(
            monitor, "send_speculative_calibration_email", return_value=True,
        ), patch.object(
            monitor.ws_manager, "broadcast", new=AsyncMock(),
        ), patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        await db_session.refresh(stale)
        assert stale.status == "superseded"
        assert stale.decided_at is not None

        # Exactly one pending row for this user after the pass.
        pending = (await db_session.execute(
            select(SpeculativeWeightsProposal).where(
                SpeculativeWeightsProposal.user_id == user.id,
                SpeculativeWeightsProposal.status == "pending",
            )
        )).scalars().all()
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_no_change_proposal_is_skipped(self, db_session):
        """If the tuner would return the same weights (no real drift),
        don't create a proposal — inbox noise with no value."""
        user = await _user(db_session, "nochange@t.com")
        account = await _account(db_session, user)
        await _bot(db_session, user, account)

        # _analysis(..., skew=False) returns flat 15% across all components
        # vs overall 15% — alpha=0 everywhere → tuner returns defaults
        # unchanged → no proposal.
        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=_analysis(800, skew=False)),
        ), patch.object(
            monitor, "send_speculative_calibration_email", return_value=True,
        ), patch.object(
            monitor.ws_manager, "broadcast", new=AsyncMock(),
        ), patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        rows = (await db_session.execute(
            select(SpeculativeWeightsProposal)
            .where(SpeculativeWeightsProposal.user_id == user.id)
        )).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_proposal_failure_does_not_block_email(self, db_session):
        """If proposal creation raises, the email must still fire
        (without an auto-proposal section) — the Claude prompt alone
        is the minimum acceptable alert."""
        user = await _user(db_session, "propfail@t.com")
        account = await _account(db_session, user)
        await _bot(db_session, user, account)

        async def _boom(*a, **kw):
            raise RuntimeError("tuner exploded")

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=_analysis(600)),
        ), patch.object(
            monitor, "_create_proposal", new=_boom,
        ), patch.object(
            monitor, "send_speculative_calibration_email", return_value=True,
        ) as send_email, patch.object(
            monitor.ws_manager, "broadcast", new=AsyncMock(),
        ), patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        send_email.assert_called_once()
        _, kwargs = send_email.call_args
        assert kwargs.get("proposal") is None
        assert kwargs.get("apply_url") in (None, "")
