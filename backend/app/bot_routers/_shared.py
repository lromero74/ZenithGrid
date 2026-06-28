"""Shared helpers for the bot routers."""

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bot
from app.services.account_access import manager_account_ids


async def bot_write_filter(db: AsyncSession, current_user_id: int):
    """SQLAlchemy filter clause for bots the user may WRITE — ones they own OR
    manage (manager membership on the account).

    Single source of truth for the bot-write authorization predicate, used to
    gate start/stop/edit/clone/delete. Previously duplicated across
    bot_control_router and bot_crud_router (CLAUDE.md rule 14).
    """
    mgr_ids = await manager_account_ids(db, current_user_id)
    return or_(Bot.user_id == current_user_id, Bot.account_id.in_(mgr_ids))
