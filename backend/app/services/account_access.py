"""
Account access helpers — shared filter utilities for multi-user account access.

Provides SQLAlchemy filter clauses and helper functions that check both
account ownership and account membership (shared access), used across
routers and service functions to allow observers/managers to read data
from accounts they have been granted access to.
"""

from datetime import datetime
from typing import List

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account
from app.models.sharing import AccountMembership


def accessible_accounts_filter(current_user_id: int):
    """
    SQLAlchemy filter clause matching all accounts a user can access:
      1. Accounts they own (account.user_id == current_user_id)
      2. Accounts they have an active (non-expired) membership on

    Suitable for any SELECT / WHERE clause on the Account model.
    """
    return or_(
        Account.user_id == current_user_id,
        Account.id.in_(
            select(AccountMembership.account_id).where(
                AccountMembership.user_id == current_user_id,
                or_(
                    AccountMembership.expires_at.is_(None),
                    AccountMembership.expires_at > datetime.utcnow(),
                ),
            )
        ),
    )


async def accessible_account_ids(db: AsyncSession, current_user_id: int) -> List[int]:
    """
    Return a list of account IDs accessible to the given user:
      - Accounts they own
      - Accounts with an active (non-expired) membership

    Used in queries that filter related objects (bots, positions, orders)
    by account_id rather than by user ownership.
    """
    result = await db.execute(
        select(Account.id).where(accessible_accounts_filter(current_user_id))
    )
    return [row[0] for row in result.fetchall()]
