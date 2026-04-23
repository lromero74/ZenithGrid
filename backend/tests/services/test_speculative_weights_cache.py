"""
Tests for app.services.speculative_weights_cache.

Resolves a user's currently-effective scorer weights. Falls back through:
  in-process cache → latest applied proposal → DEFAULT_WEIGHTS.
"""

from datetime import datetime, timedelta

import pytest

from app.indicators.speculative_signals import DEFAULT_WEIGHTS
from app.models import SpeculativeWeightsProposal, User
from app.services.speculative_weights_cache import (
    get_effective_weights,
    invalidate_weights_cache,
)


async def _user(db, email="cache@t.com"):
    u = User(email=email, hashed_password="h", is_active=True)
    db.add(u)
    await db.flush()
    return u


class TestGetEffectiveWeights:
    @pytest.mark.asyncio
    async def test_returns_defaults_when_no_applied_proposal(self, db_session):
        invalidate_weights_cache()
        user = await _user(db_session)
        weights = await get_effective_weights(db_session, user.id)
        assert weights == DEFAULT_WEIGHTS

    @pytest.mark.asyncio
    async def test_returns_latest_applied_for_user(self, db_session):
        invalidate_weights_cache()
        user = await _user(db_session, email="applied@t.com")
        # Older applied proposal
        older = SpeculativeWeightsProposal(
            user_id=user.id, status="applied",
            algorithm="proportional-alpha-v1", sample_size=500,
            overall_win_rate_pct=15.0,
            baseline_weights=dict(DEFAULT_WEIGHTS),
            proposed_weights={**DEFAULT_WEIGHTS, "volume_surge": 22},
            decided_at=datetime.utcnow() - timedelta(days=2),
        )
        db_session.add(older)
        await db_session.flush()
        # Newer applied proposal
        newer = SpeculativeWeightsProposal(
            user_id=user.id, status="applied",
            algorithm="proportional-alpha-v1", sample_size=600,
            overall_win_rate_pct=16.0,
            baseline_weights={**DEFAULT_WEIGHTS, "volume_surge": 22},
            proposed_weights={**DEFAULT_WEIGHTS, "volume_surge": 28},
            decided_at=datetime.utcnow(),
        )
        db_session.add(newer)
        await db_session.flush()

        weights = await get_effective_weights(db_session, user.id)
        assert weights["volume_surge"] == 28  # newer row wins

    @pytest.mark.asyncio
    async def test_ignores_pending_proposals(self, db_session):
        invalidate_weights_cache()
        user = await _user(db_session, email="pending@t.com")
        # Pending proposal exists but not applied.
        pending = SpeculativeWeightsProposal(
            user_id=user.id, status="pending",
            algorithm="proportional-alpha-v1", sample_size=500,
            overall_win_rate_pct=15.0,
            baseline_weights=dict(DEFAULT_WEIGHTS),
            proposed_weights={**DEFAULT_WEIGHTS, "volume_surge": 99},
        )
        db_session.add(pending)
        await db_session.flush()

        weights = await get_effective_weights(db_session, user.id)
        assert weights == DEFAULT_WEIGHTS  # pending doesn't take effect

    @pytest.mark.asyncio
    async def test_per_user_isolation(self, db_session):
        invalidate_weights_cache()
        user_a = await _user(db_session, email="a-isolation@t.com")
        user_b = await _user(db_session, email="b-isolation@t.com")
        # Only user A has a proposal.
        db_session.add(SpeculativeWeightsProposal(
            user_id=user_a.id, status="applied",
            algorithm="proportional-alpha-v1", sample_size=500,
            overall_win_rate_pct=15.0,
            baseline_weights=dict(DEFAULT_WEIGHTS),
            proposed_weights={**DEFAULT_WEIGHTS, "volume_surge": 30},
            decided_at=datetime.utcnow(),
        ))
        await db_session.flush()

        weights_a = await get_effective_weights(db_session, user_a.id)
        weights_b = await get_effective_weights(db_session, user_b.id)

        assert weights_a["volume_surge"] == 30
        assert weights_b == DEFAULT_WEIGHTS  # user B unaffected


class TestCacheBehavior:
    @pytest.mark.asyncio
    async def test_second_call_within_ttl_does_not_requery(self, db_session, monkeypatch):
        invalidate_weights_cache()
        user = await _user(db_session, email="cache-hit@t.com")

        # Prime the cache with the current (default) state.
        await get_effective_weights(db_session, user.id)

        # Now insert an applied proposal directly. Because the cache is
        # still fresh, the next call must return the CACHED defaults, not
        # the new DB row.
        db_session.add(SpeculativeWeightsProposal(
            user_id=user.id, status="applied",
            algorithm="proportional-alpha-v1", sample_size=500,
            overall_win_rate_pct=15.0,
            baseline_weights=dict(DEFAULT_WEIGHTS),
            proposed_weights={**DEFAULT_WEIGHTS, "volume_surge": 40},
            decided_at=datetime.utcnow(),
        ))
        await db_session.flush()

        weights = await get_effective_weights(db_session, user.id)
        assert weights == DEFAULT_WEIGHTS  # still the cached value

    @pytest.mark.asyncio
    async def test_db_exception_falls_back_to_defaults_and_logs(self, db_session, caplog):
        """If the DB hiccups mid-scorer-eval we must NOT break trading —
        the scorer falls back to DEFAULT_WEIGHTS and logs the exception.
        Regression guard against anyone narrowing the `except Exception`
        to a more specific exception class and accidentally letting a
        new error propagate."""
        import logging as _logging
        invalidate_weights_cache()

        class _Exploding:
            async def execute(self, _stmt):
                raise RuntimeError("DB is on fire")

        with caplog.at_level(_logging.ERROR):
            weights = await get_effective_weights(_Exploding(), user_id=123)

        assert weights == DEFAULT_WEIGHTS
        # Logger must record the failure so ops can find it.
        assert any("get_effective_weights" in r.message for r in caplog.records)


class TestParseWeights:
    """The JSON-column round-trip. PG JSONB gives us a dict; SQLite TEXT
    can give us a JSON-encoded string. Both paths must decode to the
    same int-valued dict so the scorer sees consistent types."""

    def test_parses_dict_input(self):
        from app.services.speculative_weights_cache import _parse_weights
        raw = {"volume_surge": 25, "correlation_break": 10}
        assert _parse_weights(raw) == {"volume_surge": 25, "correlation_break": 10}

    def test_parses_json_string_input_and_coerces_to_int(self):
        """SQLite TEXT fallback: the column stores the JSON as a string.
        String values inside the JSON (e.g. from a migration quirk) must
        be coerced to int so the scorer's arithmetic stays pure-int."""
        from app.services.speculative_weights_cache import _parse_weights
        raw = '{"volume_surge": "25", "correlation_break": 10}'
        result = _parse_weights(raw)
        assert result == {"volume_surge": 25, "correlation_break": 10}
        assert all(isinstance(v, int) for v in result.values())

    def test_none_input_returns_defaults(self):
        from app.services.speculative_weights_cache import _parse_weights
        assert _parse_weights(None) == DEFAULT_WEIGHTS


class TestInvalidation:
    @pytest.mark.asyncio
    async def test_invalidate_clears_cache(self, db_session):
        invalidate_weights_cache()
        user = await _user(db_session, email="invalidate@t.com")

        # Prime cache.
        await get_effective_weights(db_session, user.id)

        # Insert applied proposal.
        db_session.add(SpeculativeWeightsProposal(
            user_id=user.id, status="applied",
            algorithm="proportional-alpha-v1", sample_size=500,
            overall_win_rate_pct=15.0,
            baseline_weights=dict(DEFAULT_WEIGHTS),
            proposed_weights={**DEFAULT_WEIGHTS, "volume_surge": 35},
            decided_at=datetime.utcnow(),
        ))
        await db_session.flush()

        # Explicit invalidation → next call requeries.
        invalidate_weights_cache(user.id)
        weights = await get_effective_weights(db_session, user.id)
        assert weights["volume_surge"] == 35
