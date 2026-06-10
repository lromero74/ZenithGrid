"""
Account access helpers — shared filter utilities for multi-user account access.

Provides SQLAlchemy filter clauses and helper functions that check both
account ownership and account membership (shared access), used across
routers and service functions.

Membership roles:
  manager  — read + write access: can start/stop bots, add bots, manage positions,
             view all data including operational settings (auto-buy, rebalance, dust sweep);
             cannot touch credentials or invite/remove members
  shadow   — read-only: balances, bots, positions, reports, logs, and operational settings
             (auto-buy thresholds, rebalance config, dust sweep config)
"""

from app.utils.timeutil import utcnow
from typing import List

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account
from app.models.sharing import AccountMembership


def _active_membership_clauses(uid: int):
    """Returns the WHERE clauses that identify a non-expired membership for uid.

    Split out so accessible/manager filter builders can spread it with *clauses.
    """
    return (
        AccountMembership.user_id == uid,
        or_(
            AccountMembership.expires_at.is_(None),
            AccountMembership.expires_at > utcnow(),
        ),
    )


def accessible_accounts_filter(current_user_id: int):
    """
    SQLAlchemy filter clause matching all accounts a user can access (any role):
      1. Accounts they own
      2. Accounts they have an active (non-expired) membership on (observer OR manager)

    Suitable for read-only SELECT / WHERE clauses on the Account model.
    """
    return or_(
        Account.user_id == current_user_id,
        Account.id.in_(
            select(AccountMembership.account_id).where(*_active_membership_clauses(current_user_id))
        ),
    )


def manager_accounts_filter(current_user_id: int):
    """
    SQLAlchemy filter clause matching accounts the user can write to:
      1. Accounts they own
      2. Accounts where they have an active manager membership

    Suitable for mutating endpoints (bot start/stop/create, position actions).
    """
    return or_(
        Account.user_id == current_user_id,
        Account.id.in_(
            select(AccountMembership.account_id).where(
                *_active_membership_clauses(current_user_id),
                AccountMembership.role == 'manager',
            )
        ),
    )


async def accessible_account_ids(db: AsyncSession, current_user_id: int) -> List[int]:
    """
    Return all account IDs accessible to the user (any role: owner, manager, shadow).
    Used for read-only queries on bots, positions, logs, etc.
    """
    result = await db.execute(
        select(Account.id).where(accessible_accounts_filter(current_user_id))
    )
    return [row[0] for row in result.fetchall()]


async def manager_account_ids(db: AsyncSession, current_user_id: int) -> List[int]:
    """
    Return account IDs the user can write to: accounts they own OR have manager membership on.
    Used to gate mutating bot/position endpoints for the manager role.
    """
    result = await db.execute(
        select(Account.id).where(manager_accounts_filter(current_user_id))
    )
    return [row[0] for row in result.fetchall()]
