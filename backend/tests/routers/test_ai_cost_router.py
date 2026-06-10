"""Tests for GET /api/ai/cost-summary (Phase F).

Aggregates AIOpinionLog rows scoped to the current user into per-(provider,
model) totals: call count, input/output tokens, cost_usd. The time window is
controlled by the `days` query parameter (default 7, min 1, max 365).

These tests exercise the router handler directly with a real AsyncSession from
the shared `db_session` fixture (in-memory SQLite), bypassing the FastAPI
dependency wiring — same pattern used by test_ai_credentials_router.py.
"""

from datetime import datetime, timedelta

import pytest

from app.models import AIOpinionLog, User


@pytest.fixture
async def current_user(db_session):
    user = User(
        id=1, email="owner@test.com",
        hashed_password="x", is_active=True, is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def other_user(db_session):
    other = User(
        id=2, email="stranger@test.com",
        hashed_password="x", is_active=True, is_superuser=False,
    )
    db_session.add(other)
    await db_session.flush()
    return other


async def _add_log(db, **kwargs):
    defaults = dict(
        user_id=1,
        product_id="BTC-USD",
        is_sell_check=False,
        signal="hold",
        confidence=0,
        reasoning="",
        ai_model="claude",
        model_used="claude-opus-4-7",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.003,
        tool_calls=[],
        created_at=datetime.utcnow(),
    )
    defaults.update(kwargs)
    row = AIOpinionLog(**defaults)
    db.add(row)
    await db.flush()
    return row


class TestCostSummaryScope:
    async def test_scoped_to_current_user(self, db_session, current_user, other_user):
        """Rows from other users are excluded."""
        from app.routers.ai_cost_router import cost_summary

        await _add_log(db_session, user_id=current_user.id, cost_usd=0.01)
        await _add_log(db_session, user_id=other_user.id, cost_usd=999.0)
        await db_session.commit()

        result = await cost_summary(days=7, db=db_session, current_user=current_user)
        assert result.total_cost_usd == pytest.approx(0.01)
        assert result.total_calls == 1
        # The foreign user's huge-cost row must not appear anywhere.
        assert all("999" not in str(b.cost_usd) for b in result.by_model)

    async def test_empty_for_user_with_no_calls(self, db_session, current_user):
        from app.routers.ai_cost_router import cost_summary

        result = await cost_summary(days=7, db=db_session, current_user=current_user)
        assert result.total_cost_usd == 0.0
        assert result.total_calls == 0
        assert result.by_model == []
        assert result.by_provider == []


class TestCostSummaryAggregation:
    async def test_groups_by_provider_and_model(self, db_session, current_user):
        from app.routers.ai_cost_router import cost_summary

        # Three Claude calls + two GPT calls, with varying token counts.
        await _add_log(db_session, ai_model="claude", model_used="claude-opus-4-7",
                       input_tokens=100, output_tokens=50, cost_usd=0.01)
        await _add_log(db_session, ai_model="claude", model_used="claude-opus-4-7",
                       input_tokens=200, output_tokens=100, cost_usd=0.02)
        await _add_log(db_session, ai_model="claude", model_used="claude-sonnet-4-5",
                       input_tokens=50, output_tokens=25, cost_usd=0.001)
        await _add_log(db_session, ai_model="gpt", model_used="gpt-4o",
                       input_tokens=1000, output_tokens=500, cost_usd=0.03)
        await _add_log(db_session, ai_model="gpt", model_used="gpt-4o",
                       input_tokens=500, output_tokens=250, cost_usd=0.015)
        await db_session.commit()

        result = await cost_summary(days=7, db=db_session, current_user=current_user)

        assert result.total_calls == 5
        assert result.total_cost_usd == pytest.approx(0.076, rel=1e-6)
        assert result.total_input_tokens == 1850
        assert result.total_output_tokens == 925

        # by_model: one row per (provider, model) pair.
        by_model = {(b.provider, b.model_used): b for b in result.by_model}
        assert (by_model[("claude", "claude-opus-4-7")].calls) == 2
        assert by_model[("claude", "claude-opus-4-7")].cost_usd == pytest.approx(0.03)
        assert by_model[("claude", "claude-opus-4-7")].input_tokens == 300
        assert by_model[("claude", "claude-opus-4-7")].output_tokens == 150

        assert by_model[("claude", "claude-sonnet-4-5")].calls == 1
        assert by_model[("gpt", "gpt-4o")].calls == 2
        assert by_model[("gpt", "gpt-4o")].cost_usd == pytest.approx(0.045)

        # by_provider: one row per provider.
        by_provider = {b.provider: b for b in result.by_provider}
        assert by_provider["claude"].calls == 3
        assert by_provider["claude"].cost_usd == pytest.approx(0.031)
        assert by_provider["gpt"].calls == 2
        assert by_provider["gpt"].cost_usd == pytest.approx(0.045)


class TestCostSummaryWindow:
    async def test_days_filters_old_rows(self, db_session, current_user):
        """Rows older than `days` must not count."""
        from app.routers.ai_cost_router import cost_summary

        now = datetime.utcnow()
        await _add_log(db_session, created_at=now - timedelta(days=2), cost_usd=0.01)
        await _add_log(db_session, created_at=now - timedelta(days=10), cost_usd=0.99)
        await db_session.commit()

        result = await cost_summary(days=7, db=db_session, current_user=current_user)
        assert result.total_calls == 1
        assert result.total_cost_usd == pytest.approx(0.01)

    async def test_days_default_is_seven(self, db_session, current_user):
        """Omitting the `days` kwarg must look back exactly seven days."""
        from app.routers.ai_cost_router import cost_summary

        now = datetime.utcnow()
        await _add_log(db_session, created_at=now - timedelta(days=5), cost_usd=0.01)
        await _add_log(db_session, created_at=now - timedelta(days=8), cost_usd=0.99)
        await db_session.commit()

        result = await cost_summary(db=db_session, current_user=current_user)
        assert result.days == 7
        assert result.total_calls == 1
        assert result.total_cost_usd == pytest.approx(0.01)

    async def test_larger_window_includes_older_rows(self, db_session, current_user):
        from app.routers.ai_cost_router import cost_summary

        now = datetime.utcnow()
        await _add_log(db_session, created_at=now - timedelta(days=20), cost_usd=0.05)
        await db_session.commit()

        r7 = await cost_summary(days=7, db=db_session, current_user=current_user)
        r30 = await cost_summary(days=30, db=db_session, current_user=current_user)
        assert r7.total_calls == 0
        assert r30.total_calls == 1
        assert r30.total_cost_usd == pytest.approx(0.05)


class TestCostSummaryLegacyRows:
    async def test_rows_without_model_used_grouped_by_provider(
        self, db_session, current_user,
    ):
        """Pre-Phase-F rows have `ai_model` but no `model_used`. They should
        still show up under the `provider` bucket so legacy activity is visible."""
        from app.routers.ai_cost_router import cost_summary

        await _add_log(
            db_session, ai_model="claude", model_used=None,
            input_tokens=0, output_tokens=0, cost_usd=0.0,
        )
        await db_session.commit()

        result = await cost_summary(days=7, db=db_session, current_user=current_user)
        assert result.total_calls == 1
        by_provider = {b.provider: b for b in result.by_provider}
        assert by_provider["claude"].calls == 1


class TestCostSummaryProviderNormalization:
    async def test_openai_and_gpt_rows_merge_into_one_bucket(self, db_session, current_user):
        """'openai' normalizes to 'gpt' — rows stored under either raw value
        must merge into a single (gpt, model) bucket, not two."""
        from app.routers.ai_cost_router import cost_summary

        await _add_log(db_session, ai_model="openai", model_used="gpt-4o",
                       input_tokens=10, output_tokens=5, cost_usd=0.01)
        await _add_log(db_session, ai_model="gpt", model_used="gpt-4o",
                       input_tokens=20, output_tokens=10, cost_usd=0.02)
        await db_session.commit()

        result = await cost_summary(days=7, db=db_session, current_user=current_user)

        assert len(result.by_model) == 1
        bucket = result.by_model[0]
        assert (bucket.provider, bucket.model_used) == ("gpt", "gpt-4o")
        assert bucket.calls == 2
        assert bucket.input_tokens == 30
        assert bucket.output_tokens == 15
        assert bucket.cost_usd == pytest.approx(0.03)

        by_provider = {b.provider: b for b in result.by_provider}
        assert list(by_provider) == ["gpt"]
        assert by_provider["gpt"].calls == 2

    async def test_null_tokens_and_cost_counted_as_zero(self, db_session, current_user):
        """Rows with NULL token/cost fields count as calls but contribute zero
        to the sums (SQL SUM must not turn the whole bucket NULL)."""
        from app.routers.ai_cost_router import cost_summary

        await _add_log(db_session, input_tokens=None, output_tokens=None, cost_usd=None)
        await _add_log(db_session, input_tokens=100, output_tokens=50, cost_usd=0.01)
        await db_session.commit()

        result = await cost_summary(days=7, db=db_session, current_user=current_user)
        assert result.total_calls == 2
        assert result.total_input_tokens == 100
        assert result.total_output_tokens == 50
        assert result.total_cost_usd == pytest.approx(0.01)


class TestCostSummaryInputValidation:
    async def test_rejects_zero_or_negative_days(self, db_session, current_user):
        from fastapi import HTTPException
        from app.routers.ai_cost_router import cost_summary

        with pytest.raises(HTTPException) as exc:
            await cost_summary(days=0, db=db_session, current_user=current_user)
        assert exc.value.status_code == 400

        with pytest.raises(HTTPException) as exc:
            await cost_summary(days=-5, db=db_session, current_user=current_user)
        assert exc.value.status_code == 400

    async def test_rejects_excessive_days(self, db_session, current_user):
        from fastapi import HTTPException
        from app.routers.ai_cost_router import cost_summary

        with pytest.raises(HTTPException) as exc:
            await cost_summary(days=10_000, db=db_session, current_user=current_user)
        assert exc.value.status_code == 400
