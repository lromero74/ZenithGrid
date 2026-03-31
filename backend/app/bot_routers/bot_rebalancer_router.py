"""
Bot Budget Rebalancer Router

GET  /api/bots/rebalancer?account_id=...
    Returns all currency groups for the account, each with participating bots.

PUT  /api/bots/rebalancer
    Saves the rebalancer state: updates group settings + writes budget_percentage
    to all participating bots.
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.bot_routers.schemas import BotResponse, BotRebalancerSaveRequest
from app.database import get_db
from app.models import Account, Bot, User
from app.models.trading import BotRebalancerGroup
from app.multi_bot_monitor import is_rebalancer_gated, is_rebalancer_bot_overweight

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bot-rebalancer"])


@router.get("/rebalancer")
async def get_rebalancer_state(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Returns all bots for the account grouped by quote currency,
    with existing rebalancer group settings merged in.
    """
    # Verify account ownership
    acc_q = await db.execute(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == current_user.id,
        )
    )
    if not acc_q.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Account not found")

    # Load bots for this account owned by current user
    bots_q = await db.execute(
        select(Bot).where(
            Bot.account_id == account_id,
            Bot.user_id == current_user.id,
        )
    )
    bots = bots_q.scalars().all()

    # Load existing rebalancer groups for this account
    groups_q = await db.execute(
        select(BotRebalancerGroup).where(BotRebalancerGroup.account_id == account_id)
    )
    groups = {g.base_currency: g for g in groups_q.scalars().all()}

    # Group bots by quote currency
    by_currency: dict = defaultdict(list)
    for bot in bots:
        by_currency[bot.get_quote_currency()].append(bot)

    result = []
    for currency, currency_bots in sorted(by_currency.items()):
        group = groups.get(currency)
        bot_list = []
        for b in currency_bots:
            bot_resp = BotResponse.model_validate(b)
            bot_resp.rebalancer_gated = is_rebalancer_gated(b.id)
            bot_resp.rebalancer_bot_overweight = is_rebalancer_bot_overweight(b.id)
            bot_resp.quote_currency = b.get_quote_currency()
            bot_list.append(bot_resp.model_dump())

        result.append({
            "base_currency": currency,
            "max_total_pct": group.max_total_pct if group else 100.0,
            "overweight_tolerance_pct": group.overweight_tolerance_pct if group else 5.0,
            "enabled": group.enabled if group else True,
            "bots": bot_list,
        })
    return result


@router.put("/rebalancer")
async def save_rebalancer(
    payload: BotRebalancerSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, bool]:
    """
    Saves rebalancer settings for one currency group.
    - Upserts BotRebalancerGroup
    - For each bot slot: updates bot_rebalancer_enabled, bot_rebalancer_target_pct
    - For participating bots: writes budget_percentage = target_pct (write-through)
    - For opted-out bots: clears bot_rebalancer_enabled flag (does NOT touch budget_percentage)
    """
    # Verify account ownership
    acc_q = await db.execute(
        select(Account).where(
            Account.id == payload.account_id,
            Account.user_id == current_user.id,
        )
    )
    if not acc_q.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not your account")

    if not (0 < payload.max_total_pct <= 150):
        raise HTTPException(
            status_code=400,
            detail="max_total_pct must be between 1 and 150",
        )

    # Validate sum of enabled-bot target_pcts <= max_total_pct
    enabled_slots = [s for s in payload.bots if s.enabled]
    total = sum(s.target_pct for s in enabled_slots)
    if total > payload.max_total_pct + 0.01:  # floating-point tolerance
        raise HTTPException(
            status_code=400,
            detail=(
                f"Total allocation {total:.1f}% exceeds max_total_pct "
                f"{payload.max_total_pct:.1f}%"
            ),
        )

    # Upsert BotRebalancerGroup
    groups_q = await db.execute(
        select(BotRebalancerGroup).where(
            BotRebalancerGroup.account_id == payload.account_id,
            BotRebalancerGroup.base_currency == payload.base_currency,
        )
    )
    group = groups_q.scalar_one_or_none()
    if group is None:
        group = BotRebalancerGroup(
            account_id=payload.account_id,
            base_currency=payload.base_currency,
        )
        db.add(group)
    group.max_total_pct = payload.max_total_pct
    group.overweight_tolerance_pct = payload.overweight_tolerance_pct
    group.enabled = True

    # Verify all bot IDs belong to this account and current user
    bot_ids = [s.bot_id for s in payload.bots]
    if bot_ids:
        bots_q = await db.execute(
            select(Bot).where(
                Bot.id.in_(bot_ids),
                Bot.account_id == payload.account_id,
                Bot.user_id == current_user.id,
            )
        )
        bots_by_id = {b.id: b for b in bots_q.scalars().all()}
        if len(bots_by_id) != len(bot_ids):
            raise HTTPException(
                status_code=403,
                detail="One or more bots not found or not yours",
            )

        # Apply slot updates
        for slot in payload.bots:
            bot = bots_by_id[slot.bot_id]
            bot.bot_rebalancer_enabled = slot.enabled
            bot.bot_rebalancer_target_pct = slot.target_pct
            if slot.enabled:
                # Write-through: push the slider value into the bot's live budget
                bot.budget_percentage = slot.target_pct

    await db.commit()
    return {"ok": True}
