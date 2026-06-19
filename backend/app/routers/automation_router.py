"""
Automation Router

CRUD endpoints for automation rules and a manual trigger endpoint.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AutomationRule, User
from app.auth.dependencies import get_current_user, require_permission, Perm
from app.services.account_access import manager_account_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/automation", tags=["automation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AutomationRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    account_id: int
    trigger_type: str  # price_threshold|holding_threshold|period_check|profitability_threshold
    trigger_config: Dict[str, Any]
    action_type: str  # cancel_open_orders, sell_all_positions, stop_trading, etc.
    action_config: Optional[Dict[str, Any]] = None


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[Dict[str, Any]] = None
    action_type: Optional[str] = None
    action_config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class AutomationRuleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    account_id: int
    trigger_type: str
    trigger_config: Dict[str, Any]
    action_type: str
    action_config: Optional[Dict[str, Any]]
    enabled: bool
    last_fired_at: Optional[str] = None
    fire_count: int = 0

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Valid types
# ---------------------------------------------------------------------------

VALID_TRIGGER_TYPES = {"price_threshold", "holding_threshold", "period_check", "profitability_threshold"}
VALID_ACTION_TYPES = {
    "cancel_open_orders", "sell_all_positions", "stop_trading",
    "stop_strategies", "send_notification", "start_bot",
}


# ---------------------------------------------------------------------------
# Access check
# ---------------------------------------------------------------------------

async def _check_account_access(db: AsyncSession, user_id: int, account_id: int) -> None:
    """Verify the user owns or manages the account."""
    mgr_ids = await manager_account_ids(db, user_id)
    if account_id not in mgr_ids:
        raise HTTPException(status_code=403, detail="Not authorized for this account")


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.get("/rules", response_model=List[AutomationRuleResponse])
async def list_rules(
    account_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List automation rules for the current user, optionally filtered by account."""
    mgr_ids = await manager_account_ids(db, current_user.id)
    query = select(AutomationRule).where(AutomationRule.user_id == current_user.id)
    if account_id is not None:
        if account_id not in mgr_ids:
            raise HTTPException(status_code=403, detail="Not authorized for this account")
        query = query.where(AutomationRule.account_id == account_id)

    result = await db.execute(query.order_by(AutomationRule.created_at.desc()))
    rules = result.scalars().all()
    return [AutomationRuleResponse.model_validate(r) for r in rules]


@router.post("/rules", response_model=AutomationRuleResponse)
async def create_rule(
    rule_data: AutomationRuleCreate,
    current_user: User = Depends(require_permission(Perm.BOTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new automation rule."""
    if rule_data.trigger_type not in VALID_TRIGGER_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid trigger type: {rule_data.trigger_type}")
    if rule_data.action_type not in VALID_ACTION_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid action type: {rule_data.action_type}")

    await _check_account_access(db, current_user.id, rule_data.account_id)

    rule = AutomationRule(
        user_id=current_user.id,
        account_id=rule_data.account_id,
        name=rule_data.name,
        description=rule_data.description,
        trigger_type=rule_data.trigger_type,
        trigger_config=rule_data.trigger_config,
        action_type=rule_data.action_type,
        action_config=rule_data.action_config,
        enabled=True,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return AutomationRuleResponse.model_validate(rule)


@router.put("/rules/{rule_id}", response_model=AutomationRuleResponse)
async def update_rule(
    rule_id: int,
    update: AutomationRuleUpdate,
    current_user: User = Depends(require_permission(Perm.BOTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Update an automation rule."""
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.user_id == current_user.id)
    )
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    if update.name is not None:
        rule.name = update.name
    if update.description is not None:
        rule.description = update.description
    if update.trigger_type is not None:
        if update.trigger_type not in VALID_TRIGGER_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid trigger type: {update.trigger_type}")
        rule.trigger_type = update.trigger_type
    if update.trigger_config is not None:
        rule.trigger_config = update.trigger_config
    if update.action_type is not None:
        if update.action_type not in VALID_ACTION_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid action type: {update.action_type}")
        rule.action_type = update.action_type
    if update.action_config is not None:
        rule.action_config = update.action_config
    if update.enabled is not None:
        rule.enabled = update.enabled

    await db.commit()
    await db.refresh(rule)
    return AutomationRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: int,
    current_user: User = Depends(require_permission(Perm.BOTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete an automation rule."""
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.user_id == current_user.id)
    )
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.delete(rule)
    await db.commit()
    return {"status": "deleted"}


@router.post("/rules/{rule_id}/test")
async def test_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually evaluate a rule and execute its action if triggered."""
    from app.automation import evaluate_rule
    from app.services.exchange_service import get_exchange_client_for_account

    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.user_id == current_user.id)
    )
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    exchange = await get_exchange_client_for_account(db, rule.account_id)

    action_result = await evaluate_rule(rule, db, exchange)
    if action_result is None:
        return {"status": "not_triggered", "message": "Trigger conditions not met"}

    return {"status": "triggered", "result": action_result}
