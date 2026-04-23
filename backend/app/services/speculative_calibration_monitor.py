"""
Speculative Calibration Alert Monitor (Phase F).

Background async task that runs once per day and emails the account owner
when their speculative bot preset has accumulated enough closed positions
to warrant re-tuning the signal weights in
`app/indicators/speculative_signals.py`.

Design rationale (see PRPs/high-risk-doubling-preset.md §Phase F):

- The weights in speculative_signals.WEIGHTS are educated guesses at ship
  time. Without empirical outcomes we cannot know which components are
  actually predictive. Rather than requiring the user to notice and act,
  this monitor watches for "enough data + meaningful divergence" and
  proactively alerts.

- The alert body is self-sufficient: it carries a copy-paste prompt that
  a future Claude Code session can act on with no prior context. This is
  important because the alert may fire months after the preset shipped,
  by which time the original conversation is long gone.

- 30-day cooldown per user prevents alert fatigue. Set at the moment of
  a successful send (email + toast both succeeded). Email failure leaves
  the cooldown unchanged so the next pass retries.

- Follows the start_*/stop_* pattern used by prop_guard_monitor.py. Wired
  into main.py startup alongside other Tier 1 monitors.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update

from app.config import settings
from app.models import Account, Bot, SpeculativeWeightsProposal, User
from app.services.email_service import send_speculative_calibration_email
from app.services.speculative_bucket_service import (
    _speculative_bot_filter,
    analyze_speculative_calibration,
)
from app.services.speculative_calibration_apply_token import (
    build_apply_proposal_url,
)
from app.services.speculative_calibration_token import build_dismiss_url
from app.services.speculative_weights_cache import get_effective_weights
from app.services.speculative_weights_tuner import (
    ALGORITHM_NAME,
    PROPOSAL_MIN_SAMPLE_SIZE,
    propose_weights,
)
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


CHECK_INTERVAL_SECONDS = 24 * 3600   # once per day
COOLDOWN_DAYS = 30                    # don't re-alert more often than this
# Delay before the first pass on startup. Longer than prop_guard_monitor
# because this is a low-urgency task and we don't want to pile work on
# cold-start (which often coincides with a deploy).
STARTUP_DELAY_SECONDS = 5 * 60


_monitor_task: Optional[asyncio.Task] = None
_running = False


def _session_factory():
    """Return a fresh async DB session context manager.

    Extracted as a module-level callable so tests can swap it for one
    that yields the test's transactional db_session.
    """
    from app.database import async_session_maker
    return async_session_maker()


async def _run_one_pass() -> None:
    """One pass: iterate users with at least one speculative-tagged bot and
    check each against the cooldown + analysis thresholds."""
    async with _session_factory() as db:
        user_ids = await _users_with_speculative_bots(db)
        if not user_ids:
            return
        for user_id in user_ids:
            try:
                await _check_user(db, user_id)
            except Exception:
                logger.exception(
                    "speculative_calibration_monitor: check failed for user %s",
                    user_id,
                )


async def _users_with_speculative_bots(db) -> list[int]:
    """Return the distinct user_ids that own at least one speculative bot.

    Uses the same JSON-extract filter as speculative_bucket_service so the
    PostgreSQL vs. SQLite semantics stay aligned."""
    stmt = (
        select(Bot.user_id)
        .where(_speculative_bot_filter(), Bot.user_id.isnot(None))
        .distinct()
    )
    rows = await db.execute(stmt)
    return [uid for (uid,) in rows.all() if uid is not None]


async def _check_user(db, user_id: int) -> None:
    """Pick the user's speculative-hosting account, check cooldown, analyze,
    and if all conditions hold, send + stamp the timestamp.

    One user may have multiple accounts with speculative bots. In practice
    that's rare (speculative allocation is an account-level setting), so
    we pick the first one that has a speculative bot and enough allocation
    configured. The cooldown is tracked on that specific account.
    """
    account = await _account_for_speculative_user(db, user_id)
    if account is None:
        return

    # Cooldown check.
    last_alerted = account.speculative_calibration_last_alerted_at
    if last_alerted is not None:
        age = datetime.utcnow() - last_alerted
        if age < timedelta(days=COOLDOWN_DAYS):
            return

    analysis = await analyze_speculative_calibration(db, user_id)
    if analysis is None:
        return

    # Resolve the owner's email + display name for the email body.
    user = await db.get(User, user_id)
    if user is None or not user.email:
        logger.warning(
            "speculative_calibration_monitor: user %s missing email, skipping",
            user_id,
        )
        return

    first_name = (user.display_name or user.email).split()[0].split("@")[0]
    base_url = settings.frontend_url or ""
    dismiss_url = build_dismiss_url(
        user_id=user_id, account_id=account.id, base_url=base_url,
    )

    # OPTIONAL: if the sample size is also past the auto-proposal threshold,
    # compute a weight-adjustment proposal and include a one-click apply URL
    # in the email alongside the existing Claude copy-paste block. Failure
    # here MUST NOT block the alert — fall through with proposal=None.
    proposal: Optional[SpeculativeWeightsProposal] = None
    apply_url: Optional[str] = None
    if analysis["total_closed"] >= PROPOSAL_MIN_SAMPLE_SIZE:
        try:
            proposal = await _create_proposal(db, user_id, account.id, analysis)
            if proposal is not None:
                apply_url = build_apply_proposal_url(
                    user_id=user_id, account_id=account.id,
                    proposal_id=proposal.id, base_url=base_url,
                )
        except Exception:
            logger.exception(
                "speculative_calibration_monitor: proposal generation "
                "failed for user %s — sending alert without auto-proposal",
                user_id,
            )

    email_ok = False
    try:
        email_ok = send_speculative_calibration_email(
            to=user.email, analysis=analysis,
            user_first_name=first_name, user_id=user_id,
            dismiss_url=dismiss_url,
            proposal=proposal,
            apply_url=apply_url,
        )
    except Exception:
        logger.exception(
            "speculative_calibration_monitor: email send raised for user %s",
            user_id,
        )
    if not email_ok:
        logger.warning(
            "speculative_calibration_monitor: email send failed for user %s"
            " — leaving cooldown unchanged for retry", user_id,
        )
        return

    # Toast broadcast. A failure here means the cooldown is NOT advanced —
    # the retry keeps the two notification surfaces in lockstep.
    try:
        await ws_manager.broadcast(
            {
                "type": "speculative_calibration_alert",
                "payload": {
                    "total_closed": analysis["total_closed"],
                    "overall_win_rate_pct": analysis["overall_win_rate_pct"],
                    "divergence_pp": analysis["divergence_pp"],
                    "dismiss_url": dismiss_url,
                },
            },
            user_id=user_id,
        )
    except Exception:
        logger.exception(
            "speculative_calibration_monitor: broadcast failed for user %s"
            " — leaving cooldown unchanged for retry", user_id,
        )
        return

    # Both surfaces succeeded — stamp the cooldown.
    account.speculative_calibration_last_alerted_at = datetime.utcnow()
    await db.commit()
    logger.info(
        "speculative_calibration_monitor: alerted user %s (account %s) —"
        " total_closed=%s divergence=%.1fpp",
        user_id, account.id, analysis["total_closed"], analysis["divergence_pp"],
    )


async def _account_for_speculative_user(db, user_id: int) -> Optional[Account]:
    """Pick the first account owned by `user_id` that hosts a speculative bot."""
    stmt = (
        select(Account)
        .join(Bot, Bot.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            _speculative_bot_filter(),
        )
        .order_by(Account.created_at.asc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def _monitor_loop() -> None:
    global _running
    _running = True
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    while _running:
        try:
            await _run_one_pass()
        except Exception:
            logger.exception("speculative_calibration_monitor pass failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def start_speculative_calibration_monitor() -> None:
    """Start the background monitor. Idempotent — no-op if already running."""
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        logger.warning("speculative_calibration_monitor already running")
        return
    _monitor_task = asyncio.create_task(_monitor_loop())
    logger.info(
        "speculative_calibration_monitor started (interval=%ss, cooldown=%sd)",
        CHECK_INTERVAL_SECONDS, COOLDOWN_DAYS,
    )


async def _create_proposal(
    db, user_id: int, account_id: int, analysis: dict,
) -> Optional[SpeculativeWeightsProposal]:
    """Run the tuner and persist a pending proposal row.

    Returns None (and logs) when:
    - the algorithm refuses (impossible clamp constraints), or
    - the proposed weights are identical to current (no signal).

    Supersedes any prior pending proposal for this user so inboxes
    don't accumulate stale apply-links.
    """
    current = await get_effective_weights(db, user_id)
    try:
        proposed = propose_weights(
            current_weights=current,
            component_stats=analysis["components"],
            overall_win_rate_pct=analysis["overall_win_rate_pct"],
        )
    except ValueError as exc:
        logger.warning(
            "speculative_weights_tuner refused to propose for user %s: %s",
            user_id, exc,
        )
        return None

    if proposed == current:
        logger.info(
            "speculative_calibration_monitor: tuner produced no change for "
            "user %s — skipping proposal creation", user_id,
        )
        return None

    # Supersede any prior pending proposals so the user only has one
    # actionable proposal at a time.
    await db.execute(
        update(SpeculativeWeightsProposal)
        .where(
            SpeculativeWeightsProposal.user_id == user_id,
            SpeculativeWeightsProposal.status == "pending",
        )
        .values(status="superseded", decided_at=datetime.utcnow())
    )

    row = SpeculativeWeightsProposal(
        user_id=user_id,
        account_id=account_id,
        status="pending",
        algorithm=ALGORITHM_NAME,
        sample_size=analysis["total_closed"],
        overall_win_rate_pct=analysis["overall_win_rate_pct"],
        baseline_weights=current,
        proposed_weights=proposed,
        divergence_pp=analysis.get("divergence_pp"),
        reason=(
            f"Auto-generated from {analysis['total_closed']} closed positions "
            f"(top={analysis.get('top_component')}, "
            f"bottom={analysis.get('bottom_component')}, "
            f"divergence={analysis.get('divergence_pp', 0):.1f}pp)"
        ),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def stop_speculative_calibration_monitor() -> None:
    """Cancel the monitor task."""
    global _running, _monitor_task
    _running = False
    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
        _monitor_task = None
    logger.info("speculative_calibration_monitor stopped")
