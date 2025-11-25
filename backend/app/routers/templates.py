"""
Bot Template Router

Handles CRUD operations for bot templates.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import BotTemplate
from app.strategies import StrategyRegistry

router = APIRouter(prefix="/api/templates", tags=["templates"])


# Pydantic Schemas
class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    strategy_type: str
    strategy_config: dict
    product_ids: Optional[List[str]] = None
    split_budget_across_pairs: bool = False


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    strategy_config: Optional[dict] = None
    product_ids: Optional[List[str]] = None
    split_budget_across_pairs: Optional[bool] = None


class TemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    strategy_type: str
    strategy_config: dict
    product_ids: Optional[List[str]]
    split_budget_across_pairs: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Template CRUD Endpoints
@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(template_data: TemplateCreate, db: AsyncSession = Depends(get_db)):
    """Create a new bot template"""
    # Validate strategy exists
    try:
        _strategy_def = StrategyRegistry.get_definition(template_data.strategy_type)  # noqa: F841
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {template_data.strategy_type}")

    # Validate strategy config
    try:
        StrategyRegistry.get_strategy(template_data.strategy_type, template_data.strategy_config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid strategy config: {str(e)}")

    # Check if name is unique
    query = select(BotTemplate).where(BotTemplate.name == template_data.name)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(status_code=400, detail=f"Template with name '{template_data.name}' already exists")

    # Create template
    template = BotTemplate(
        name=template_data.name,
        description=template_data.description,
        strategy_type=template_data.strategy_type,
        strategy_config=template_data.strategy_config,
        product_ids=template_data.product_ids or [],
        split_budget_across_pairs=template_data.split_budget_across_pairs,
        is_default=False,  # User-created templates are not defaults
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template


@router.get("", response_model=List[TemplateResponse])
async def list_templates(db: AsyncSession = Depends(get_db)):
    """Get list of all templates (defaults first, then user-created)"""
    query = select(BotTemplate).order_by(
        desc(BotTemplate.is_default), desc(BotTemplate.created_at)  # Defaults first  # Then newest first
    )

    result = await db.execute(query)
    templates = result.scalars().all()

    return templates


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """Get details for a specific template"""
    query = select(BotTemplate).where(BotTemplate.id == template_id)
    result = await db.execute(query)
    template = result.scalars().first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return template


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(template_id: int, template_update: TemplateUpdate, db: AsyncSession = Depends(get_db)):
    """Update template configuration"""
    query = select(BotTemplate).where(BotTemplate.id == template_id)
    result = await db.execute(query)
    template = result.scalars().first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Don't allow editing default templates
    if template.is_default:
        raise HTTPException(status_code=403, detail="Cannot edit default templates")

    # Update fields
    if template_update.name is not None:
        # Check name uniqueness
        name_query = select(BotTemplate).where(BotTemplate.name == template_update.name, BotTemplate.id != template_id)
        name_result = await db.execute(name_query)
        if name_result.scalars().first():
            raise HTTPException(status_code=400, detail=f"Template with name '{template_update.name}' already exists")
        template.name = template_update.name

    if template_update.description is not None:
        template.description = template_update.description

    if template_update.strategy_config is not None:
        # Validate new config
        try:
            StrategyRegistry.get_strategy(template.strategy_type, template_update.strategy_config)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid strategy config: {str(e)}")
        template.strategy_config = template_update.strategy_config

    if template_update.product_ids is not None:
        template.product_ids = template_update.product_ids

    if template_update.split_budget_across_pairs is not None:
        template.split_budget_across_pairs = template_update.split_budget_across_pairs

    template.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(template)

    return template


@router.delete("/{template_id}")
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a template"""
    query = select(BotTemplate).where(BotTemplate.id == template_id)
    result = await db.execute(query)
    template = result.scalars().first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Don't allow deleting default templates
    if template.is_default:
        raise HTTPException(status_code=403, detail="Cannot delete default templates")

    await db.delete(template)
    await db.commit()

    return {"message": f"Template '{template.name}' deleted successfully"}


@router.post("/seed-defaults")
async def seed_default_templates(db: AsyncSession = Depends(get_db)):
    """Seed the database with default bot templates (one-time setup)"""

    # Check if defaults already exist
    query = select(BotTemplate).where(BotTemplate.is_default)
    result = await db.execute(query)
    existing_defaults = result.scalars().all()

    if existing_defaults:
        return {"message": "Default templates already exist", "count": len(existing_defaults)}

    # Default templates matching 3Commas presets
    default_templates = [
        {
            "name": "Conservative DCA",
            "description": "Low-risk DCA strategy with small orders and tight profit targets",
            "strategy_type": "conditional_dca",
            "strategy_config": {
                "base_order_type": "percentage",
                "base_order_percentage": 2.0,  # 2% of balance
                "safety_order_type": "percentage_of_base",
                "safety_order_percentage": 50.0,  # 50% of base order
                "max_safety_orders": 3,
                "price_deviation": 2.0,  # Start SO at -2%
                "safety_order_step_scale": 1.0,  # Linear
                "safety_order_volume_scale": 1.0,  # Same size
                "take_profit_percentage": 1.5,  # 1.5% profit target
                "trailing_take_profit": False,
                "trailing_deviation": 0.5,
                "stop_loss_enabled": True,
                "stop_loss_percentage": -5.0,  # -5% stop loss
                "base_order_conditions": [],
                "safety_order_conditions": [],
                "take_profit_conditions": [],
                "min_profit_for_conditions": 0.0,
            },
            "product_ids": [],
            "split_budget_across_pairs": False,
        },
        {
            "name": "Balanced DCA",
            "description": "Medium-risk DCA strategy with balanced risk/reward",
            "strategy_type": "conditional_dca",
            "strategy_config": {
                "base_order_type": "percentage",
                "base_order_percentage": 5.0,  # 5% of balance
                "safety_order_type": "percentage_of_base",
                "safety_order_percentage": 100.0,  # 100% of base order (doubling)
                "max_safety_orders": 4,
                "price_deviation": 3.0,  # Start SO at -3%
                "safety_order_step_scale": 1.2,  # Slightly increasing gaps
                "safety_order_volume_scale": 1.5,  # Martingale scaling
                "take_profit_percentage": 2.0,  # 2% profit target
                "trailing_take_profit": False,
                "trailing_deviation": 0.5,
                "stop_loss_enabled": True,
                "stop_loss_percentage": -10.0,  # -10% stop loss
                "base_order_conditions": [],
                "safety_order_conditions": [],
                "take_profit_conditions": [],
                "min_profit_for_conditions": 0.0,
            },
            "product_ids": [],
            "split_budget_across_pairs": False,
        },
        {
            "name": "Aggressive DCA",
            "description": "High-risk DCA strategy with large orders and aggressive averaging down",
            "strategy_type": "conditional_dca",
            "strategy_config": {
                "base_order_type": "percentage",
                "base_order_percentage": 10.0,  # 10% of balance
                "safety_order_type": "percentage_of_base",
                "safety_order_percentage": 150.0,  # 150% of base order
                "max_safety_orders": 5,
                "price_deviation": 5.0,  # Start SO at -5%
                "safety_order_step_scale": 1.5,  # Increasing gaps
                "safety_order_volume_scale": 2.0,  # Aggressive martingale
                "take_profit_percentage": 3.0,  # 3% profit target
                "trailing_take_profit": False,
                "trailing_deviation": 1.0,
                "stop_loss_enabled": False,  # No stop loss (risky!)
                "stop_loss_percentage": -20.0,
                "base_order_conditions": [],
                "safety_order_conditions": [],
                "take_profit_conditions": [],
                "min_profit_for_conditions": 0.0,
            },
            "product_ids": [],
            "split_budget_across_pairs": False,
        },
    ]

    # Create templates
    created_templates = []
    for template_data in default_templates:
        template = BotTemplate(
            name=template_data["name"],
            description=template_data["description"],
            strategy_type=template_data["strategy_type"],
            strategy_config=template_data["strategy_config"],
            product_ids=template_data["product_ids"],
            split_budget_across_pairs=template_data["split_budget_across_pairs"],
            is_default=True,  # Mark as default
        )
        db.add(template)
        created_templates.append(template_data["name"])

    await db.commit()

    return {"message": "Default templates created successfully", "templates": created_templates}
