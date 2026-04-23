"""
End-to-end: alert fires → proposal is created → apply endpoint persists
it → scorer picks up the new per-user weights on the next eval.

Exercises the full chain that proposal-mode auto-calibration adds —
the tuner, cache, monitor extension, email/apply URL, and apply endpoint
all need to line up for this to pass.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.indicators.speculative_signals import (
    DEFAULT_WEIGHTS,
    score_speculative_setup,
)
from app.models import Account, Bot, SpeculativeWeightsProposal, User
from app.routers.accounts_mutation_router import (
    apply_speculative_weights_proposal,
)
from app.services import speculative_calibration_monitor as monitor
from app.services.speculative_calibration_apply_token import (
    create_apply_proposal_token,
)
from app.services.speculative_weights_cache import (
    get_effective_weights,
    invalidate_weights_cache,
)


async def _user(db, email="e2e@t.com"):
    u = User(email=email, hashed_password="h", is_active=True, display_name="U")
    db.add(u)
    await db.flush()
    return u


async def _account(db, user):
    a = Account(
        user_id=user.id, name="A", type="cex",
        is_active=True, is_default=True, speculative_allocation_pct=5.0,
    )
    db.add(a)
    await db.flush()
    return a


async def _bot(db, user, account):
    b = Bot(
        user_id=user.id, account_id=account.id, name="B",
        strategy_type="indicator_based",
        strategy_config={"is_speculative": "true"}, is_active=True,
    )
    db.add(b)
    await db.flush()
    return b


class _OneShotSession:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


ANALYSIS = {
    "total_closed": 800,
    "wins": 120, "losses": 680,
    "overall_win_rate_pct": 15.0,
    "overall_realized_pnl_usd": -500.0,
    "components": [
        {"name": "volume_surge", "fires": 250, "win_rate_pct": 40.0},
        {"name": "compression_breakout", "fires": 180, "win_rate_pct": 22.0},
        {"name": "momentum_accelerating", "fires": 170, "win_rate_pct": 15.0},
        {"name": "micro_mid_cap", "fires": 110, "win_rate_pct": 11.0},
        {"name": "correlation_break", "fires": 90, "win_rate_pct": 4.0},
        {"name": "volume_vs_mcap", "fires": 200, "win_rate_pct": 18.0},
    ],
    "top_component": "volume_surge", "top_win_rate_pct": 40.0,
    "bottom_component": "correlation_break", "bottom_win_rate_pct": 4.0,
    "divergence_pp": 36.0,
}


class TestE2E:
    @pytest.mark.asyncio
    async def test_full_flow(self, db_session):
        invalidate_weights_cache()
        user = await _user(db_session)
        account = await _account(db_session, user)
        await _bot(db_session, user, account)

        # Score on a setup where volume_surge + compression_breakout fire —
        # captures the default-weights baseline score.
        fixed_metrics = {
            "volume_30d_ratio": 5.0,
            "compression_ratio": 4.0,
            "momentum_1h": 3.0,
            "momentum_acceleration": 0.5,
            "turnover_ratio_24h": 0.08,
            "is_major_cap": False,
        }
        baseline = score_speculative_setup(
            fixed_metrics, None, "HYPE-USD", weights=DEFAULT_WEIGHTS,
        )
        baseline_score = baseline["score"]

        # Run the monitor pass — generates a proposal (sample_size=800 >= 500).
        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=ANALYSIS),
        ), patch.object(
            monitor, "send_speculative_calibration_email", return_value=True,
        ), patch.object(
            monitor.ws_manager, "broadcast", new=AsyncMock(),
        ), patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        # A pending proposal now exists for this user.
        proposals = (await db_session.execute(
            __import__("sqlalchemy").select(SpeculativeWeightsProposal)
            .where(SpeculativeWeightsProposal.user_id == user.id)
        )).scalars().all()
        assert len(proposals) == 1
        proposal = proposals[0]
        assert proposal.status == "pending"
        assert proposal.proposed_weights != dict(DEFAULT_WEIGHTS)

        # Apply the proposal via the endpoint — mirrors the email link click.
        token = create_apply_proposal_token(
            user_id=user.id, account_id=account.id, proposal_id=proposal.id,
        )
        result = await apply_speculative_weights_proposal(
            account_id=account.id, apply_token=token, proposal_id=proposal.id,
            db=db_session, current_user=user,
        )
        assert result["applied"] is True
        await db_session.refresh(proposal)
        assert proposal.status == "applied"

        # Cache was invalidated by the apply endpoint — next lookup returns
        # the freshly-applied weights, NOT the defaults.
        effective = await get_effective_weights(db_session, user.id)
        assert effective == proposal.proposed_weights
        assert effective != dict(DEFAULT_WEIGHTS)

        # Scoring with the new weights on the same metrics produces a
        # different score — demonstrating the whole pipeline actually
        # changed scorer behavior end-to-end.
        post_apply = score_speculative_setup(
            fixed_metrics, None, "HYPE-USD", weights=effective,
        )
        assert post_apply["score"] != baseline_score
