"""
Tests for backend/app/services/speculative_calibration_monitor.py

The monitor loops once per day and:
- Finds users with at least one speculative-tagged bot.
- For each user, enforces the 30-day cooldown via
  Account.speculative_calibration_last_alerted_at.
- Runs analyze_speculative_calibration; if it returns a payload, sends
  email + toast and stamps the cooldown timestamp.

Covers cooldown math, skip-when-no-speculative-bots, partial-failure
rollback (email failure must not advance the cooldown), and the happy
path.
"""

from datetime import timedelta
from app.utils.timeutil import utcnow
from unittest.mock import AsyncMock, patch

import pytest

from app.models import Account, Bot, User
from app.services import speculative_calibration_monitor as monitor


async def _user(db, email="u@t.com"):
    u = User(email=email, hashed_password="h", is_active=True,
             display_name="Louis")
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


async def _bot(db, user, account, *, is_speculative=True):
    cfg = {"is_speculative": "true" if is_speculative else "false"}
    b = Bot(user_id=user.id, account_id=account.id,
            name=f"B-{user.id}", strategy_type="indicator_based",
            strategy_config=cfg, is_active=True)
    db.add(b)
    await db.flush()
    return b


ANALYSIS = {
    "total_closed": 67,
    "wins": 9,
    "losses": 58,
    "overall_win_rate_pct": 13.4,
    "overall_realized_pnl_usd": -127.4,
    "components": [
        {"name": "volume_surge", "fires": 52, "win_rate_pct": 19.2},
        {"name": "correlation_break", "fires": 33, "win_rate_pct": 4.0},
    ],
    "top_component": "volume_surge",
    "top_win_rate_pct": 19.2,
    "bottom_component": "correlation_break",
    "bottom_win_rate_pct": 4.0,
    "divergence_pp": 15.2,
}


class TestRunOnePass:
    @pytest.mark.asyncio
    async def test_happy_path_sends_email_and_toast_and_sets_timestamp(self, db_session):
        user = await _user(db_session)
        account = await _account(db_session, user)
        await _bot(db_session, user, account)

        broadcasted = []

        async def _fake_broadcast(message, user_id=None):
            broadcasted.append((message, user_id))

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=ANALYSIS),
        ), patch.object(
            monitor, "send_speculative_calibration_email",
            return_value=True,
        ) as send_email, patch.object(
            monitor.ws_manager, "broadcast",
            new=_fake_broadcast,
        ), patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        send_email.assert_called_once()
        assert len(broadcasted) == 1
        message, user_id = broadcasted[0]
        assert user_id == user.id
        assert message["type"] == "speculative_calibration_alert"
        assert message["payload"]["total_closed"] == 67
        assert message["payload"]["divergence_pp"] == 15.2
        assert "dismiss_url" in message["payload"]

        await db_session.refresh(account)
        assert account.speculative_calibration_last_alerted_at is not None

    @pytest.mark.asyncio
    async def test_cooldown_respected_for_recent_alert(self, db_session):
        """User alerted 10 days ago is skipped without running analysis."""
        user = await _user(db_session)
        account = await _account(
            db_session, user,
            alerted_at=utcnow() - timedelta(days=10),
        )
        await _bot(db_session, user, account)

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=ANALYSIS),
        ) as analyze, patch.object(
            monitor, "send_speculative_calibration_email", return_value=True,
        ) as send_email, patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        analyze.assert_not_called()
        send_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_cooldown_expired_allows_fresh_run(self, db_session):
        """Alerted 40 days ago — past the 30-day cooldown — the monitor
        re-runs the analysis."""
        user = await _user(db_session)
        account = await _account(
            db_session, user,
            alerted_at=utcnow() - timedelta(days=40),
        )
        await _bot(db_session, user, account)

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=ANALYSIS),
        ) as analyze, patch.object(
            monitor, "send_speculative_calibration_email", return_value=True,
        ), patch.object(
            monitor.ws_manager, "broadcast", new=AsyncMock(),
        ), patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_users_without_speculative_bots(self, db_session):
        """A user with only non-speculative bots should never trigger analysis."""
        user = await _user(db_session)
        account = await _account(db_session, user)
        await _bot(db_session, user, account, is_speculative=False)

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=ANALYSIS),
        ) as analyze, patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_failure_does_not_advance_cooldown(self, db_session):
        """If the email send fails, the cooldown timestamp must NOT advance —
        the next pass needs to retry."""
        user = await _user(db_session)
        account = await _account(db_session, user, alerted_at=None)
        await _bot(db_session, user, account)

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=ANALYSIS),
        ), patch.object(
            monitor, "send_speculative_calibration_email", return_value=False,
        ), patch.object(
            monitor.ws_manager, "broadcast", new=AsyncMock(),
        ), patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        await db_session.refresh(account)
        assert account.speculative_calibration_last_alerted_at is None

    @pytest.mark.asyncio
    async def test_broadcast_failure_does_not_advance_cooldown(self, db_session):
        """Same principle — if the toast broadcast fails, retry next pass."""
        user = await _user(db_session)
        account = await _account(db_session, user, alerted_at=None)
        await _bot(db_session, user, account)

        broken = AsyncMock(side_effect=RuntimeError("ws gone"))

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=ANALYSIS),
        ), patch.object(
            monitor, "send_speculative_calibration_email", return_value=True,
        ), patch.object(
            monitor.ws_manager, "broadcast", new=broken,
        ), patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        await db_session.refresh(account)
        assert account.speculative_calibration_last_alerted_at is None

    @pytest.mark.asyncio
    async def test_none_analysis_does_not_alert(self, db_session):
        """analyze_ returning None means thresholds aren't met — no email,
        no timestamp change."""
        user = await _user(db_session)
        account = await _account(db_session, user, alerted_at=None)
        await _bot(db_session, user, account)

        with patch.object(
            monitor, "analyze_speculative_calibration",
            new=AsyncMock(return_value=None),
        ), patch.object(
            monitor, "send_speculative_calibration_email", return_value=True,
        ) as send_email, patch.object(
            monitor, "_session_factory",
            lambda: _OneShotSession(db_session),
        ):
            await monitor._run_one_pass()

        send_email.assert_not_called()
        await db_session.refresh(account)
        assert account.speculative_calibration_last_alerted_at is None


class _OneShotSession:
    """Async context manager wrapper that yields an existing db session.

    The monitor opens fresh sessions via `async with _session_factory() as db`;
    in tests we want to reuse the transactional db_session so assertions see
    the same rows. Commit is a no-op; rollback on the inner session would
    break test isolation — pytest handles that.
    """

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False
