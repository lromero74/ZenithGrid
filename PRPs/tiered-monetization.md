# PRP: Tiered Subscription Monetization

**Version:** 1.0
**Feature Branch:** `feature/tiered-monetization`
**Confidence Score:** 8/10

---

## Overview

Implement a self-serve subscription billing system with four tiers (Free, Base, Pro, Premium)
using Stripe Checkout and the Stripe Customer Portal. No custom payment forms — Stripe
hosts the checkout and management UI. Users upgrade/downgrade/cancel via Stripe's hosted
portal pages. Our job is plan enforcement, webhook handling, and surfacing plan status in
the UI.

This is the full Phase 3 of the commercialization roadmap (`COMMERCIALIZATION.md`).

---

## Tier Structure

### Competitive Rationale

Leading self-serve SaaS trading platforms converge on the same pattern:
- A **free tier** that lets users try the core loop (paper trading or 1-2 live bots)
- A **$19-29/mo base** that covers most hobbyist needs
- A **$49-79/mo pro** for active traders running many strategies in parallel
- A **$99+/mo premium** for power users or small firms who want unlimited everything

### Recommended Tiers

| Feature | Free | Base ($19/mo) | Pro ($49/mo) | Premium ($99/mo) |
|---------|------|---------------|--------------|------------------|
| Active bots | 2 | 5 | 20 | Unlimited |
| **Active deals (all bots)** | **10** | **50** | **200** | **Unlimited** |
| Live exchange accounts | 1 | 2 | 5 | Unlimited |
| Paper accounts | 1 | 2 | 5 | Unlimited |
| Account sharing members | 0 | 1 | 5 | Unlimited |
| Auto portfolio rebalancing | ❌ | ✅ | ✅ | ✅ |
| AI blacklist review | ❌ | ✅ | ✅ | ✅ |
| Reports (PDF export) | ❌ | ✅ | ✅ | ✅ |
| Scheduled reports | ❌ | ❌ | ✅ | ✅ |
| Trade history | 30 days | 90 days | 1 year | Unlimited |
| Advanced strategies | ❌ | ✅ | ✅ | ✅ |
| Priority support | ❌ | ❌ | ❌ | ✅ |

**Active deals** counts all open positions across every bot owned by the user. This is the
primary scaling limit — a user on Free with 2 bots and `max_concurrent_deals=10` per bot
still cannot exceed 10 total open positions across both. Per-bot limits from strategy config
(`max_concurrent_deals`) remain and are enforced first; the user-level plan cap is a
second gate checked before any new position opens.

**Annual pricing:** 2 months free (10×monthly). e.g. Base = $190/yr, Pro = $490/yr, Premium = $990/yr.

**Trial:** 14-day Pro trial for new signups (no credit card required initially — trial enforced
via Stripe trial_period_days on first subscription).

**Grandfathering:** All existing users (at ship time) receive `plan = "legacy_free"` which
gets free unlimited access for 90 days, then drops to the Free tier unless they subscribe.
This is an enum value in DB, not a separate Stripe product.

---

## Architecture

### Payment Flow (Stripe Checkout)

```
User clicks "Upgrade to Pro"
  → POST /api/billing/create-checkout-session {plan_id: "pro", interval: "monthly"}
  → Backend creates Stripe CheckoutSession (mode=subscription)
  → Returns {checkout_url: "https://checkout.stripe.com/..."}
  → Frontend: window.location.href = checkout_url
  → User completes payment on Stripe-hosted page
  → Stripe redirects to /settings?billing=success
  → Stripe fires webhook → POST /api/billing/webhook
  → Webhook handler updates auth.user_subscriptions + user plan
  → User sees new plan on next page load / AuthContext refresh
```

### Subscription Management Flow (Stripe Customer Portal)

```
User clicks "Manage Billing"
  → POST /api/billing/create-portal-session
  → Backend creates Stripe BillingPortal.Session
  → Returns {portal_url: "https://billing.stripe.com/..."}
  → Frontend redirects → User can upgrade/downgrade/cancel/update card
  → Stripe fires webhook for any changes
  → Webhook handler syncs plan in DB
```

### Data Flow for Plan Enforcement

```
Request arrives at any protected endpoint
  → current_user loaded from JWT
  → current_user.active_plan property (computed from auth.user_subscriptions)
  → PLAN_LIMITS[plan]["max_active_bots"] checked against COUNT(active bots)
  → If over limit: raise PlanLimitError(feature="bots", limit=N, current=M)
  → PlanLimitError → HTTP 402 {"error": "plan_limit", "feature": "bots", "limit": 2, "current": 2, "upgrade_url": "/settings#billing"}
```

---

## Database Schema

### Migration: `072_subscription_plans.py`

```sql
-- Plans catalog (seeded from code, not user-editable)
CREATE TABLE IF NOT EXISTS auth.subscription_plans (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,           -- "free", "base", "pro", "premium"
    display_name VARCHAR(100) NOT NULL,         -- "Free", "Base", "Pro", "Premium"
    stripe_price_id_monthly VARCHAR(100),       -- price_xxx (from Stripe dashboard)
    stripe_price_id_annual VARCHAR(100),        -- price_yyy (from Stripe dashboard)
    price_monthly_cents INTEGER NOT NULL DEFAULT 0,
    price_annual_cents INTEGER NOT NULL DEFAULT 0,
    max_active_bots INTEGER NOT NULL DEFAULT 2,   -- 0 = unlimited
    max_active_deals INTEGER NOT NULL DEFAULT 10, -- 0 = unlimited; cross-bot total open positions
    max_live_accounts INTEGER NOT NULL DEFAULT 1,
    max_paper_accounts INTEGER NOT NULL DEFAULT 1,
    max_account_members INTEGER NOT NULL DEFAULT 0,
    ai_blacklist_review BOOLEAN NOT NULL DEFAULT FALSE,
    auto_rebalance BOOLEAN NOT NULL DEFAULT FALSE,
    reports_pdf BOOLEAN NOT NULL DEFAULT FALSE,
    report_scheduling BOOLEAN NOT NULL DEFAULT FALSE,
    max_history_days INTEGER NOT NULL DEFAULT 30, -- 0 = unlimited
    advanced_strategies BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Per-user subscriptions (one active row per user at any time)
CREATE TABLE IF NOT EXISTS auth.user_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    plan_name VARCHAR(50) NOT NULL DEFAULT 'free',  -- denorm for fast lookups
    stripe_customer_id VARCHAR(100),
    stripe_subscription_id VARCHAR(100),
    stripe_price_id VARCHAR(100),
    interval VARCHAR(20),                           -- "monthly", "annual"
    status VARCHAR(50) NOT NULL DEFAULT 'active',   -- "active","trialing","past_due","canceled","legacy_free"
    trial_end TIMESTAMP,
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    canceled_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user_id ON auth.user_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_stripe_customer ON auth.user_subscriptions(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_stripe_sub ON auth.user_subscriptions(stripe_subscription_id);

-- Add stripe_customer_id to users for fast lookup
ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(100);
CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON auth.users(stripe_customer_id);
```

**Seed data** (inserted by migration, idempotent via ON CONFLICT DO NOTHING):
```sql
INSERT INTO auth.subscription_plans
    (name, display_name, price_monthly_cents, price_annual_cents,
     max_active_bots, max_active_deals, max_live_accounts, max_paper_accounts,
     max_account_members, ai_blacklist_review, auto_rebalance, reports_pdf,
     report_scheduling, max_history_days, advanced_strategies, sort_order)
VALUES
--                                              bots  deals  live  paper  mbrs  ai     rebal  pdf    sched  hist   strat  ord
    ('free',    'Free',    0,     0,      2,    10,   1,    1,     0,    false, false, false, false, 30,    false, 0),
    ('base',    'Base',    1900,  19000,  5,    50,   2,    2,     1,    true,  true,  true,  false, 90,    true,  1),
    ('pro',     'Pro',     4900,  49000,  20,   200,  5,    5,     5,    true,  true,  true,  true,  365,   true,  2),
    ('premium', 'Premium', 9900,  99000,  0,    0,    0,    0,     0,    true,  true,  true,  true,  0,     true,  3)
ON CONFLICT (name) DO NOTHING;

-- Seed free subscription for every existing user
INSERT INTO auth.user_subscriptions (user_id, plan_name, status)
SELECT id, 'free', 'active' FROM auth.users
WHERE id NOT IN (SELECT user_id FROM auth.user_subscriptions)
ON CONFLICT DO NOTHING;
```

---

## Backend Implementation

### New Files

```
backend/app/
├── services/
│   └── subscription_service.py    # Plan enforcement + Stripe sync logic
├── routers/
│   └── billing_router.py          # /api/billing/* endpoints
└── models/
    └── (extend auth.py with SubscriptionPlan, UserSubscription models)
```

### Models: `backend/app/models/auth.py` (additions)

```python
class SubscriptionPlan(Base):
    """Catalog of available subscription tiers (seeded by migration)."""
    __tablename__ = "subscription_plans"
    __table_args__ = {'schema': 'auth'}

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)           # "free", "base", "pro", "premium"
    display_name = Column(String(100), nullable=False)
    stripe_price_id_monthly = Column(String(100), nullable=True)
    stripe_price_id_annual = Column(String(100), nullable=True)
    price_monthly_cents = Column(Integer, nullable=False, default=0)
    price_annual_cents = Column(Integer, nullable=False, default=0)
    max_active_bots = Column(Integer, nullable=False, default=2)     # 0 = unlimited
    max_active_deals = Column(Integer, nullable=False, default=10)  # 0 = unlimited; cross-bot total open positions
    max_live_accounts = Column(Integer, nullable=False, default=1)
    max_paper_accounts = Column(Integer, nullable=False, default=1)
    max_account_members = Column(Integer, nullable=False, default=0)
    ai_blacklist_review = Column(Boolean, nullable=False, default=False)
    auto_rebalance = Column(Boolean, nullable=False, default=False)
    reports_pdf = Column(Boolean, nullable=False, default=False)
    report_scheduling = Column(Boolean, nullable=False, default=False)
    max_history_days = Column(Integer, nullable=False, default=30)   # 0 = unlimited
    advanced_strategies = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserSubscription(Base):
    """Active (and historical) subscription rows per user."""
    __tablename__ = "user_subscriptions"
    __table_args__ = {'schema': 'auth'}

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    plan_name = Column(String(50), nullable=False, default="free")
    stripe_customer_id = Column(String(100), nullable=True)
    stripe_subscription_id = Column(String(100), nullable=True)
    stripe_price_id = Column(String(100), nullable=True)
    interval = Column(String(20), nullable=True)                    # "monthly", "annual"
    status = Column(String(50), nullable=False, default="active")  # active, trialing, past_due, canceled, legacy_free
    trial_end = Column(DateTime, nullable=True)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    canceled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscription")
```

Add to User model:
```python
stripe_customer_id = Column(String(100), nullable=True)      # denorm for fast Stripe lookup
subscription = relationship("UserSubscription",
    primaryjoin="User.id == foreign(UserSubscription.user_id)",
    uselist=False,
    order_by="desc(UserSubscription.id)")
```

### Config: `backend/app/config.py` (additions)

```python
# Stripe billing
stripe_secret_key: str = ""           # sk_live_xxx or sk_test_xxx
stripe_publishable_key: str = ""      # pk_live_xxx or pk_test_xxx
stripe_webhook_secret: str = ""       # whsec_xxx (from Stripe dashboard → Webhooks)

# Stripe Price IDs (populated after creating products in Stripe dashboard)
stripe_price_base_monthly: str = ""
stripe_price_base_annual: str = ""
stripe_price_pro_monthly: str = ""
stripe_price_pro_annual: str = ""
stripe_price_premium_monthly: str = ""
stripe_price_premium_annual: str = ""

# Billing behaviour
billing_trial_days: int = 14
billing_enabled: bool = False  # Feature flag — set True when Stripe is configured
```

### Subscription Service: `backend/app/services/subscription_service.py`

```python
"""
Subscription and plan enforcement service.

Centralizes all plan-limit logic. Callers receive either a resolved SubscriptionPlan
or a PlanLimitError (HTTP 402) — never raw SQL.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import stripe
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User, UserSubscription, SubscriptionPlan, Bot, Account

logger = logging.getLogger(__name__)


@dataclass
class PlanContext:
    plan_name: str                    # "free", "base", "pro", "premium", "legacy_free"
    status: str                       # "active", "trialing", "past_due", "canceled"
    stripe_customer_id: Optional[str]
    stripe_subscription_id: Optional[str]
    cancel_at_period_end: bool
    current_period_end: Optional[datetime]
    trial_end: Optional[datetime]
    limits: SubscriptionPlan          # ORM row from auth.subscription_plans


def plan_limit_error(feature: str, limit: int, current: int) -> HTTPException:
    """Return a standardized 402 error for plan limit violations."""
    return HTTPException(
        status_code=402,
        detail={
            "error": "plan_limit",
            "feature": feature,
            "limit": limit,
            "current": current,
            "upgrade_url": "/settings#billing",
        }
    )


def feature_gate_error(feature: str, required_plan: str) -> HTTPException:
    """Return a standardized 402 error for feature gates."""
    return HTTPException(
        status_code=402,
        detail={
            "error": "feature_gate",
            "feature": feature,
            "required_plan": required_plan,
            "upgrade_url": "/settings#billing",
        }
    )


async def get_user_plan(db: AsyncSession, user: User) -> PlanContext:
    """
    Load active plan context for a user.
    Returns default Free plan context if no subscription row exists.
    """
    sub_result = await db.execute(
        select(UserSubscription)
        .where(UserSubscription.user_id == user.id)
        .order_by(UserSubscription.id.desc())
        .limit(1)
    )
    sub = sub_result.scalar_one_or_none()

    if sub is None:
        # No subscription row — treat as free (should not happen after migration seeds rows)
        plan_name = "free"
        status = "active"
    else:
        plan_name = sub.plan_name
        status = sub.status

    # Canceled subscriptions fall back to free
    if status == "canceled":
        plan_name = "free"

    # past_due: keep plan active but flag in context (let user in, but show warning)

    plan_result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.name == plan_name)
    )
    plan = plan_result.scalar_one_or_none()

    if plan is None:
        # Fallback: load free plan limits
        plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.name == "free")
        )
        plan = plan_result.scalar_one()

    return PlanContext(
        plan_name=plan_name,
        status=status,
        stripe_customer_id=sub.stripe_customer_id if sub else None,
        stripe_subscription_id=sub.stripe_subscription_id if sub else None,
        cancel_at_period_end=sub.cancel_at_period_end if sub else False,
        current_period_end=sub.current_period_end if sub else None,
        trial_end=sub.trial_end if sub else None,
        limits=plan,
    )


async def enforce_bot_limit(db: AsyncSession, user: User) -> None:
    """Raise 402 if user is at or over their active bot limit."""
    ctx = await get_user_plan(db, user)
    max_bots = ctx.limits.max_active_bots
    if max_bots == 0:  # unlimited
        return
    count_result = await db.execute(
        select(func.count()).select_from(Bot)
        .where(Bot.user_id == user.id, Bot.status == "running")
    )
    current = count_result.scalar_one()
    if current >= max_bots:
        raise plan_limit_error("bots", max_bots, current)


async def enforce_live_account_limit(db: AsyncSession, user: User) -> None:
    """Raise 402 if user is at or over their live account limit."""
    ctx = await get_user_plan(db, user)
    max_accts = ctx.limits.max_live_accounts
    if max_accts == 0:
        return
    count_result = await db.execute(
        select(func.count()).select_from(Account)
        .where(
            Account.user_id == user.id,
            Account.is_paper_trading.is_(False),
        )
    )
    current = count_result.scalar_one()
    if current >= max_accts:
        raise plan_limit_error("live_accounts", max_accts, current)


async def get_user_active_deal_count(db: AsyncSession, user_id: int) -> int:
    """Return current count of open positions across ALL bots for this user."""
    from app.models import Position  # avoid circular
    result = await db.execute(
        select(func.count()).select_from(Position)
        .where(Position.user_id == user_id, Position.status == "open")
    )
    return result.scalar_one()


async def is_deal_allowed(db: AsyncSession, user_id: int, plan: SubscriptionPlan) -> tuple[bool, str]:
    """
    Check whether a new deal can be opened for this user.

    Returns (allowed: bool, reason: str).
    Called from signal_processor — does NOT raise HTTPException since it runs in a
    background loop, not an HTTP request context.
    """
    max_deals = plan.max_active_deals
    if max_deals == 0:  # unlimited
        return True, ""
    current = await get_user_active_deal_count(db, user_id)
    if current >= max_deals:
        return False, f"Plan limit: {current}/{max_deals} active deals — upgrade to open more"
    return True, ""


async def enforce_deal_limit(db: AsyncSession, user: User) -> None:
    """
    Raise HTTP 402 if the user is at or over their active deal limit.
    Use this in HTTP endpoint contexts (manual deal creation UI, if added).
    For the background signal processor use is_deal_allowed() instead.
    """
    ctx = await get_user_plan(db, user)
    allowed, reason = await is_deal_allowed(db, user.id, ctx.limits)
    if not allowed:
        raise plan_limit_error("active_deals", ctx.limits.max_active_deals,
                               await get_user_active_deal_count(db, user.id))


async def enforce_account_members_limit(db: AsyncSession, user: User, account_id: int) -> None:
    """Raise 402 if account owner is at member capacity."""
    from app.models import AccountMember  # avoid circular import
    ctx = await get_user_plan(db, user)
    max_members = ctx.limits.max_account_members
    if max_members == 0:
        return
    count_result = await db.execute(
        select(func.count()).select_from(AccountMember)
        .where(AccountMember.account_id == account_id)
    )
    current = count_result.scalar_one()
    if current >= max_members:
        raise plan_limit_error("account_members", max_members, current)


async def require_feature(db: AsyncSession, user: User, feature: str) -> None:
    """
    Raise 402 if user's plan does not include a boolean feature.

    feature: one of "ai_blacklist_review", "auto_rebalance", "reports_pdf",
             "report_scheduling", "advanced_strategies"
    """
    ctx = await get_user_plan(db, user)
    allowed = getattr(ctx.limits, feature, False)
    if not allowed:
        # Find lowest plan with this feature
        result = await db.execute(
            select(SubscriptionPlan)
            .where(getattr(SubscriptionPlan, feature).is_(True))
            .order_by(SubscriptionPlan.sort_order)
            .limit(1)
        )
        gating_plan = result.scalar_one_or_none()
        required = gating_plan.name if gating_plan else "base"
        raise feature_gate_error(feature, required)


# ─── Stripe helpers ──────────────────────────────────────────────────────────

async def get_or_create_stripe_customer(db: AsyncSession, user: User) -> str:
    """Return existing Stripe customer ID or create a new one."""
    if user.stripe_customer_id:
        return user.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email,
        name=user.display_name or user.email,
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer.id
    db.add(user)
    await db.commit()
    return customer.id


async def sync_subscription_from_stripe(
    db: AsyncSession,
    stripe_subscription: dict,
) -> None:
    """
    Upsert a UserSubscription row from a Stripe subscription object.
    Called from webhook handlers.
    """
    stripe_customer_id = stripe_subscription["customer"]
    stripe_sub_id = stripe_subscription["id"]
    status = stripe_subscription["status"]
    price_id = stripe_subscription["items"]["data"][0]["price"]["id"]
    interval = stripe_subscription["items"]["data"][0]["price"]["recurring"]["interval"]
    interval_label = "annual" if interval == "year" else "monthly"

    # Resolve plan name from price ID
    plan_name = _price_id_to_plan_name(price_id)

    # Find user by stripe_customer_id
    user_result = await db.execute(
        select(User).where(User.stripe_customer_id == stripe_customer_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        logger.warning(f"Webhook: no user found for Stripe customer {stripe_customer_id}")
        return

    # Upsert subscription row
    sub_result = await db.execute(
        select(UserSubscription).where(UserSubscription.user_id == user.id)
    )
    sub = sub_result.scalar_one_or_none()

    trial_end = None
    if stripe_subscription.get("trial_end"):
        trial_end = datetime.utcfromtimestamp(stripe_subscription["trial_end"])

    period_start = datetime.utcfromtimestamp(stripe_subscription["current_period_start"])
    period_end = datetime.utcfromtimestamp(stripe_subscription["current_period_end"])

    if sub is None:
        sub = UserSubscription(user_id=user.id)
        db.add(sub)

    sub.plan_name = plan_name if status != "canceled" else "free"
    sub.stripe_customer_id = stripe_customer_id
    sub.stripe_subscription_id = stripe_sub_id
    sub.stripe_price_id = price_id
    sub.interval = interval_label
    sub.status = status
    sub.trial_end = trial_end
    sub.current_period_start = period_start
    sub.current_period_end = period_end
    sub.cancel_at_period_end = stripe_subscription.get("cancel_at_period_end", False)
    if status == "canceled":
        sub.canceled_at = datetime.utcnow()

    await db.commit()
    logger.info(f"Synced subscription for user {user.id}: plan={plan_name} status={status}")


def _price_id_to_plan_name(price_id: str) -> str:
    """Map a Stripe price_id to our internal plan name."""
    mapping = {
        settings.stripe_price_base_monthly:   "base",
        settings.stripe_price_base_annual:    "base",
        settings.stripe_price_pro_monthly:    "pro",
        settings.stripe_price_pro_annual:     "pro",
        settings.stripe_price_premium_monthly: "premium",
        settings.stripe_price_premium_annual:  "premium",
    }
    return mapping.get(price_id, "free")
```

### Billing Router: `backend/app/routers/billing_router.py`

```python
"""
Billing endpoints — Stripe Checkout + Customer Portal integration.

All billing state changes flow through Stripe webhooks (not direct API calls).
This ensures payment status is always authoritative from Stripe's side.
"""
import logging
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User
from app.auth_routers.helpers import get_current_user
from app.services.subscription_service import (
    get_user_plan, get_or_create_stripe_customer,
    sync_subscription_from_stripe,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/billing", tags=["billing"])

stripe.api_key = settings.stripe_secret_key


# ── Request / Response schemas ────────────────────────────────────────────────

class CreateCheckoutRequest(BaseModel):
    plan_id: str           # "base", "pro", "premium"
    interval: str = "monthly"   # "monthly" or "annual"


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class PortalSessionResponse(BaseModel):
    portal_url: str


class SubscriptionStatusResponse(BaseModel):
    plan_name: str
    status: str
    cancel_at_period_end: bool
    current_period_end: Optional[str]
    trial_end: Optional[str]
    billing_enabled: bool
    limits: dict


class PlanInfo(BaseModel):
    name: str
    display_name: str
    price_monthly_cents: int
    price_annual_cents: int
    max_active_bots: int
    max_live_accounts: int
    max_account_members: int
    ai_blacklist_review: bool
    auto_rebalance: bool
    reports_pdf: bool
    report_scheduling: bool
    sort_order: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/plans", response_model=list[PlanInfo])
async def list_plans(db: AsyncSession = Depends(get_db)):
    """Return all active subscription plans (public — no auth required)."""
    from sqlalchemy import select
    from app.models import SubscriptionPlan
    result = await db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_active.is_(True))
        .order_by(SubscriptionPlan.sort_order)
    )
    plans = result.scalars().all()
    return [PlanInfo.model_validate(p) for p in plans]


@router.get("/subscription", response_model=SubscriptionStatusResponse)
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's current subscription status."""
    ctx = await get_user_plan(db, current_user)
    limits_dict = {
        "max_active_bots": ctx.limits.max_active_bots,
        "max_live_accounts": ctx.limits.max_live_accounts,
        "max_paper_accounts": ctx.limits.max_paper_accounts,
        "max_account_members": ctx.limits.max_account_members,
        "ai_blacklist_review": ctx.limits.ai_blacklist_review,
        "auto_rebalance": ctx.limits.auto_rebalance,
        "reports_pdf": ctx.limits.reports_pdf,
        "report_scheduling": ctx.limits.report_scheduling,
        "max_history_days": ctx.limits.max_history_days,
        "advanced_strategies": ctx.limits.advanced_strategies,
    }
    return SubscriptionStatusResponse(
        plan_name=ctx.plan_name,
        status=ctx.status,
        cancel_at_period_end=ctx.cancel_at_period_end,
        current_period_end=ctx.current_period_end.isoformat() if ctx.current_period_end else None,
        trial_end=ctx.trial_end.isoformat() if ctx.trial_end else None,
        billing_enabled=settings.billing_enabled,
        limits=limits_dict,
    )


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    body: CreateCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Checkout Session for the requested plan/interval."""
    if not settings.billing_enabled:
        raise HTTPException(status_code=503, detail="Billing is not configured")

    # Resolve price ID
    price_map = {
        ("base", "monthly"):   settings.stripe_price_base_monthly,
        ("base", "annual"):    settings.stripe_price_base_annual,
        ("pro", "monthly"):    settings.stripe_price_pro_monthly,
        ("pro", "annual"):     settings.stripe_price_pro_annual,
        ("premium", "monthly"): settings.stripe_price_premium_monthly,
        ("premium", "annual"):  settings.stripe_price_premium_annual,
    }
    price_id = price_map.get((body.plan_id, body.interval))
    if not price_id:
        raise HTTPException(status_code=400, detail="Invalid plan or interval")

    customer_id = await get_or_create_stripe_customer(db, current_user)

    # Check if already subscribed (portal instead)
    ctx = await get_user_plan(db, current_user)
    if ctx.stripe_subscription_id and ctx.status in ("active", "trialing"):
        raise HTTPException(
            status_code=400,
            detail="Already subscribed — use the billing portal to change plans",
        )

    trial_days = settings.billing_trial_days if ctx.plan_name == "free" else 0

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        subscription_data={
            "trial_period_days": trial_days if trial_days > 0 else None,
            "metadata": {"user_id": str(current_user.id)},
        },
        success_url=f"{settings.frontend_url}/settings?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.frontend_url}/settings?billing=cancelled",
        allow_promotion_codes=True,
        metadata={"user_id": str(current_user.id)},
    )

    return CheckoutSessionResponse(checkout_url=session.url)


@router.post("/create-portal-session", response_model=PortalSessionResponse)
async def create_portal_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Customer Portal session for subscription self-service."""
    if not settings.billing_enabled:
        raise HTTPException(status_code=503, detail="Billing is not configured")

    customer_id = await get_or_create_stripe_customer(db, current_user)

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.frontend_url}/settings?billing=portal_return",
    )

    return PortalSessionResponse(portal_url=session.url)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Stripe webhook endpoint. All subscription state changes are processed here.
    Must be registered as PUBLIC (no auth) in nginx/middleware.
    Signature verification replaces auth.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    logger.info(f"Stripe webhook received: {event_type}")

    # Events that update subscription state
    subscription_events = {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }

    if event_type in subscription_events:
        await sync_subscription_from_stripe(db, event["data"]["object"])

    elif event_type == "invoice.payment_failed":
        # Optional: send payment-failed email via SES
        customer_id = event["data"]["object"]["customer"]
        logger.warning(f"Payment failed for Stripe customer {customer_id}")

    elif event_type == "checkout.session.completed":
        # Subscription is already handled by customer.subscription.created
        # Nothing extra needed here unless we want to log/track checkout conversions
        pass

    return Response(status_code=200)
```

### Updates to Existing Routers

#### `backend/app/bot_routers/bot_crud_router.py` — add limit check to create_bot

```python
# At the top of create_bot(), before any DB write:
from app.services.subscription_service import enforce_bot_limit

@router.post("/")
async def create_bot(
    bot_data: BotCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.BOTS_WRITE)),
):
    # Plan enforcement — raises 402 if at limit
    await enforce_bot_limit(db, current_user)

    # ... rest of existing create_bot logic unchanged ...
```

#### `backend/app/routers/accounts_router.py` — add limit check to create_account

```python
from app.services.subscription_service import (
    enforce_live_account_limit, require_feature
)

@router.post("/")
async def create_account(
    account_data: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE)),
):
    if not account_data.is_paper_trading:
        await enforce_live_account_limit(db, current_user)
    # ... rest unchanged ...
```

#### `backend/app/routers/accounts_router.py` — account sharing invite

```python
@router.post("/{account_id}/invitations")
async def invite_member(
    account_id: int,
    ...
):
    await enforce_account_members_limit(db, current_user, account_id)
    # ... rest unchanged ...
```

#### `backend/app/routers/reports_router.py` — gate PDF export

```python
from app.services.subscription_service import require_feature

@router.get("/{report_id}/pdf")
async def download_report_pdf(...):
    await require_feature(db, current_user, "reports_pdf")
    # ... rest unchanged ...
```

#### `backend/app/trading_engine/signal_processor.py` — gate new deal opening

The signal processor already checks per-bot `max_concurrent_deals` at approximately line 392.
The user-level plan check goes **before** the per-bot check, as an earlier short-circuit:

```python
# In should_buy() or the calling loop in signal_processor.py,
# immediately before the per-bot max_concurrent_deals check:

from app.services.subscription_service import is_deal_allowed, get_user_plan

# Only check when considering opening a NEW position (position is None)
if position is None:
    ctx = await get_user_plan(db, bot_user)   # bot_user = User loaded by user_id from bot
    allowed, reason = await is_deal_allowed(db, bot.user_id, ctx.limits)
    if not allowed:
        return False, 0, reason   # matches existing (bool, amount, reason) return signature
    # ... existing per-bot max_concurrent_deals check follows ...
```

**Key detail:** `bot_user` must be loaded from `bot.user_id` — the signal processor already
has `db` in scope. Add a helper or reuse the existing user-load pattern from the calling
context (multi_bot_monitor loads the bot's owner for other purposes).

**Position manager addition** — add to `position_manager.py`:
```python
async def get_open_positions_count_for_user(db: AsyncSession, user_id: int) -> int:
    """Count ALL open positions across every bot owned by this user."""
    result = await db.execute(
        select(func.count(Position.id))
        .where(Position.user_id == user_id, Position.status == "open")
    )
    return result.scalar() or 0
```
(Used by `is_deal_allowed` via `get_user_active_deal_count` in subscription_service.)

#### `backend/app/services/rebalance_monitor.py` — gate auto-rebalance

```python
# In _process_account, after loading account:
from app.services.subscription_service import require_feature, get_user_plan

ctx = await get_user_plan(db, account_owner_user)
if not ctx.limits.auto_rebalance:
    logger.debug(f"Rebalance skipped for account {account.id}: plan {ctx.plan_name} does not include auto-rebalance")
    return
```

### Auth Schema Update: `backend/app/auth_routers/schemas.py`

Add to `UserResponse`:
```python
class UserResponse(BaseModel):
    # ... existing fields ...
    plan: str = "free"              # "free", "base", "pro", "premium"
    plan_status: str = "active"     # "active", "trialing", "past_due", "canceled"
    trial_end: Optional[str] = None
    plan_limits: Optional[dict] = None   # Full limits dict for frontend enforcement
```

Update the login/me endpoint to include plan data by joining `user_subscriptions`.

### Register Router: `backend/app/main.py`

```python
from app.routers.billing_router import router as billing_router

# Add after existing routers:
app.include_router(billing_router)
```

Also add `/api/billing/webhook` to the public endpoints list (skip JWT auth):
```python
PUBLIC_ENDPOINTS = {
    "/api/auth/login",
    "/api/auth/register",
    # ...
    "/api/billing/webhook",   # ← add this
    "/api/billing/plans",     # ← add this (public pricing page)
}
```

---

## Frontend Implementation

### New Files

```
frontend/src/
├── components/
│   ├── PlanGate.tsx           # Wrapper that shows upgrade prompt if feature gated
│   └── billing/
│       ├── BillingSection.tsx  # Settings tab: plan info + upgrade/manage buttons
│       ├── PlanCard.tsx        # Plan comparison card (Free/Base/Pro/Premium)
│       └── UpgradeModal.tsx    # Feature-gated prompt with plan comparison table
└── services/
    └── billingApi.ts          # /api/billing/* API calls
```

### Extend AuthContext: `frontend/src/contexts/AuthContext.tsx`

Add to the `User` interface and context:
```typescript
interface User {
  // ... existing fields ...
  plan: 'free' | 'base' | 'pro' | 'premium';
  plan_status: 'active' | 'trialing' | 'past_due' | 'canceled';
  trial_end: string | null;
  plan_limits: PlanLimits | null;
}

interface PlanLimits {
  max_active_bots: number;       // 0 = unlimited
  max_active_deals: number;      // 0 = unlimited; cross-bot total open positions
  max_live_accounts: number;
  max_paper_accounts: number;
  max_account_members: number;
  ai_blacklist_review: boolean;
  auto_rebalance: boolean;
  reports_pdf: boolean;
  report_scheduling: boolean;
  max_history_days: number;
  advanced_strategies: boolean;
}
```

Add helper hook:
```typescript
export function usePlan() {
  const { user } = useAuth();
  const plan = user?.plan ?? 'free';
  const limits = user?.plan_limits;

  function canUse(feature: keyof PlanLimits): boolean {
    if (!limits) return false;
    const val = limits[feature];
    return typeof val === 'boolean' ? val : (val as number) !== 0;
  }

  function isAtLimit(feature: 'max_active_bots' | 'max_live_accounts' | 'max_account_members', current: number): boolean {
    if (!limits) return false;
    const max = limits[feature] as number;
    return max !== 0 && current >= max;
  }

  return { plan, limits, canUse, isAtLimit };
}
```

### PlanGate Component: `frontend/src/components/PlanGate.tsx`

```typescript
interface PlanGateProps {
  feature: keyof PlanLimits;       // e.g. "reports_pdf"
  requiredPlan?: string;           // "base" | "pro" | "premium"
  children: React.ReactNode;
  fallback?: React.ReactNode;      // Optional custom locked state
}

export function PlanGate({ feature, requiredPlan, children, fallback }: PlanGateProps) {
  const { canUse } = usePlan();

  if (canUse(feature)) return <>{children}</>;

  return fallback ? <>{fallback}</> : (
    <UpgradePrompt feature={feature} requiredPlan={requiredPlan ?? 'base'} />
  );
}

// Inline upgrade prompt shown where a locked feature would appear
function UpgradePrompt({ feature, requiredPlan }: { feature: string; requiredPlan: string }) {
  const { setShowUpgradeModal, setUpgradeContext } = useUpgradeModal();

  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-700/50 border border-slate-600/50 text-slate-400 text-sm cursor-pointer hover:border-indigo-500/50 transition-colors"
         onClick={() => { setUpgradeContext(feature); setShowUpgradeModal(true); }}>
      <Lock className="w-4 h-4 text-indigo-400" />
      <span>Available on <span className="text-indigo-400 capitalize font-medium">{requiredPlan}</span> plan</span>
      <ChevronRight className="w-3 h-3 ml-auto" />
    </div>
  );
}
```

### Billing Section: `frontend/src/components/billing/BillingSection.tsx`

Key elements:
- Current plan badge (green "Active", orange "Trial X days left", red "Past Due")
- Plan name, renewal date, cancel-at-period-end warning
- Usage meters: "3 / 5 bots", "1 / 2 accounts", etc.
- "Upgrade Plan" button → calls `POST /api/billing/create-checkout-session`
- "Manage Billing" button (if subscribed) → calls `POST /api/billing/create-portal-session`
- Plan comparison table (all four plans side by side)
- Redirects user to Stripe URLs on button click

```typescript
export function BillingSection() {
  const { user } = useAuth();
  const [subscription, setSubscription] = useState<SubscriptionStatus | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(false);

  // Load from /api/billing/subscription and /api/billing/plans
  useEffect(() => { /* fetch both */ }, []);

  async function handleUpgrade(planId: string, interval: string) {
    setLoading(true);
    const { checkout_url } = await billingApi.createCheckoutSession(planId, interval);
    window.location.href = checkout_url;  // Redirect to Stripe
  }

  async function handleManageBilling() {
    const { portal_url } = await billingApi.createPortalSession();
    window.location.href = portal_url;
  }

  // Show success/cancel toast if returning from Stripe
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('billing') === 'success') {
      // Show success toast, refresh subscription status
    }
  }, []);

  return (
    // Plan status card + usage meters + upgrade CTA + plan comparison table
  );
}
```

### Upgrade Modal: `frontend/src/components/billing/UpgradeModal.tsx`

Triggered when user hits a plan gate. Shows:
- What feature they're trying to use
- Which plans include it (highlighted)
- One-click upgrade to the cheapest qualifying plan
- Close/dismiss option

### Settings Integration: `frontend/src/pages/Settings.tsx`

Add a new "Billing" section to the settings page (before or after the Profile section):
```typescript
// Import new component
import { BillingSection } from '../components/billing/BillingSection'

// Add section to settings page JSX (after Profile, before Security):
{/* Billing & Plan */}
<section>
  <h2 className="text-lg font-semibold text-white mb-4">Subscription & Billing</h2>
  <BillingSection />
</section>
```

---

## Stripe Setup Guide (for deployment)

The following steps must be completed in the Stripe dashboard **before** setting `billing_enabled=true`:

1. **Create Products in Stripe Dashboard:**
   - "Base Plan" → Monthly price ($19) + Annual price ($190)
   - "Pro Plan" → Monthly price ($49) + Annual price ($490)
   - "Premium Plan" → Monthly price ($99) + Annual price ($990)

2. **Copy Price IDs** to `.env`:
   ```
   STRIPE_SECRET_KEY=sk_live_xxx
   STRIPE_PUBLISHABLE_KEY=pk_live_xxx
   STRIPE_WEBHOOK_SECRET=whsec_xxx
   STRIPE_PRICE_BASE_MONTHLY=price_xxx
   STRIPE_PRICE_BASE_ANNUAL=price_xxx
   ...
   ```

3. **Register Webhook in Stripe Dashboard:**
   - URL: `https://tradebot.romerotechsolutions.com/api/billing/webhook`
   - Events to listen for:
     - `customer.subscription.created`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
     - `invoice.payment_failed`
     - `checkout.session.completed`

4. **Configure Billing Portal** (Stripe Dashboard → Billing → Customer Portal):
   - Allow customers to switch plans
   - Allow cancellation (at period end, not immediate)
   - Allow payment method updates
   - Return URL: `https://tradebot.romerotechsolutions.com/settings?billing=portal_return`

5. **Install Stripe library:**
   ```bash
   cd backend && venv/bin/python3 -m pip install stripe>=7.0.0
   ```
   Add to `requirements.txt`.

---

## Implementation Tasks (in order)

1. **[Migration]** Write `072_subscription_plans.py` — create tables, seed plans, seed free subs for existing users
2. **[Models]** Add `SubscriptionPlan` and `UserSubscription` to `backend/app/models/auth.py`; add `stripe_customer_id` + `subscription` relationship to `User`; update `database.py` if needed
3. **[Config]** Add Stripe config fields to `backend/app/config.py`
4. **[Dep]** Add `stripe>=7.0.0` to `backend/requirements.txt` and install in venv
5. **[Service]** Write `backend/app/services/subscription_service.py` (plan enforcement + Stripe sync)
6. **[Router]** Write `backend/app/routers/billing_router.py` (all 5 endpoints)
7. **[Register]** Add billing router to `main.py`; add `/api/billing/webhook` and `/api/billing/plans` to public endpoints
8. **[Enforce - bots]** Add `await enforce_bot_limit(db, current_user)` to `create_bot` in `bot_crud_router.py`
9. **[Enforce - deals]** Add `get_open_positions_count_for_user()` to `position_manager.py`; add `is_deal_allowed()` call in `signal_processor.py` before the per-bot `max_concurrent_deals` check (around line 391); load `bot_user` from `bot.user_id` for the check
10. **[Enforce - accounts]** Add `await enforce_live_account_limit(db, current_user)` to `create_account` in `accounts_router.py`
11. **[Enforce - sharing]** Add `await enforce_account_members_limit(...)` to invite_member in account-sharing router
12. **[Enforce - reports]** Add `await require_feature(db, current_user, "reports_pdf")` to PDF download endpoint
13. **[Enforce - rebalancer]** Add plan check at top of `_process_account` in `rebalance_monitor.py`
13. **[Auth schema]** Add `plan`, `plan_status`, `trial_end`, `plan_limits` to `UserResponse` in `schemas.py`
14. **[Auth endpoint]** Update `/api/auth/me` (or login response) to include plan fields (join on `user_subscriptions`)
15. **[Migration run]** Run `update.py --yes` on production
16. **[Frontend - types]** Extend `User` interface in `frontend/src/types/index.ts` with plan fields; add `PlanLimits` type
17. **[Frontend - context]** Update `AuthContext.tsx` — add `plan`, `plan_limits` to user state; add `usePlan()` hook
18. **[Frontend - api]** Write `frontend/src/services/billingApi.ts`
19. **[Frontend - PlanGate]** Write `frontend/src/components/PlanGate.tsx`
20. **[Frontend - BillingSection]** Write `frontend/src/components/billing/BillingSection.tsx`
21. **[Frontend - UpgradeModal]** Write `frontend/src/components/billing/UpgradeModal.tsx`
22. **[Frontend - Settings]** Add Billing section to `frontend/src/pages/Settings.tsx`
23. **[Frontend - gates]** Add `<PlanGate feature="reports_pdf">` around PDF buttons; `<PlanGate feature="auto_rebalance">` around rebalancer toggle
24. **[Tests - service]** Write `backend/tests/services/test_subscription_service.py`
25. **[Tests - router]** Write `backend/tests/routers/test_billing_router.py`
26. **[Tests - enforcement]** Write integration tests: bot creation blocked at limit, account creation blocked at limit
27. **[Stripe config]** Follow Stripe Setup Guide above (after tests pass, before setting `billing_enabled=true`)
28. **[Deploy]** `/shipit` as v2.142.0 (minor: new feature)

---

## Testing Strategy

### Unit Tests (subscription_service.py)
```python
# test_subscription_service.py
class TestPlanEnforcement:
    async def test_enforce_bot_limit_free_at_limit_raises_402(self):
        """Free plan: 2 active bots → creating 3rd raises 402."""

    async def test_enforce_bot_limit_unlimited_never_raises(self):
        """Premium plan: max_bots=0 → no limit raised regardless of count."""

    async def test_is_deal_allowed_free_at_limit_returns_false(self):
        """Free plan at 10 open positions → is_deal_allowed returns (False, reason)."""

    async def test_is_deal_allowed_free_under_limit_returns_true(self):
        """Free plan with 9 open positions → is_deal_allowed returns (True, '')."""

    async def test_is_deal_allowed_premium_unlimited_always_true(self):
        """Premium plan: max_active_deals=0 → is_deal_allowed always (True, '')."""

    async def test_is_deal_allowed_counts_across_all_bots(self):
        """Deal count is sum of open positions across bot_a AND bot_b for same user."""

    async def test_require_feature_reports_pdf_on_free_raises_402(self):
        """Free plan: reports_pdf=False → require_feature raises 402."""

    async def test_require_feature_pro_with_reports_pdf_passes(self):
        """Pro plan: reports_pdf=True → require_feature does not raise."""

    async def test_get_user_plan_no_subscription_defaults_to_free(self):
        """User with no subscription row → returns Free plan."""

    async def test_get_user_plan_canceled_subscription_returns_free(self):
        """Canceled subscription → plan_name falls back to free."""

    async def test_sync_subscription_from_stripe_upserts_row(self):
        """Webhook data creates/updates user_subscriptions row correctly."""

    async def test_price_id_to_plan_name_resolves_correctly(self):
        """All configured price IDs map to correct plan names."""


class TestBillingRouter:
    async def test_list_plans_returns_all_active_plans(self):
        """GET /api/billing/plans returns 4 plans in sort order."""

    async def test_get_subscription_returns_current_plan(self):
        """GET /api/billing/subscription returns user's plan details."""

    async def test_webhook_invalid_signature_returns_400(self):
        """POST /api/billing/webhook with bad signature → 400."""

    async def test_webhook_subscription_updated_syncs_plan(self):
        """POST /api/billing/webhook with valid subscription.updated → DB synced."""

    async def test_create_checkout_billing_disabled_returns_503(self):
        """POST /api/billing/create-checkout-session when billing_enabled=False → 503."""
```

### Integration Tests (enforcement in existing routers)
```python
class TestBotLimitEnforcement:
    async def test_create_bot_blocked_at_free_limit(self):
        """User on free plan with 2 active bots → POST /api/bots/ returns 402."""

    async def test_create_bot_allowed_under_limit(self):
        """User on free plan with 1 active bot → POST /api/bots/ returns 201."""

    async def test_create_bot_unlimited_on_premium(self):
        """User on premium (max=0) → POST /api/bots/ always returns 201."""


class TestDealLimitEnforcement:
    async def test_signal_processor_blocked_at_deal_limit(self):
        """User at 10 open positions (free plan) → signal_processor returns False with plan limit reason."""

    async def test_signal_processor_counts_across_bots(self):
        """8 positions on bot_a + 2 on bot_b = 10 total → next signal blocked for same user."""

    async def test_signal_processor_allowed_under_limit(self):
        """User with 9 open positions (free plan, limit=10) → signal_processor proceeds normally."""

    async def test_deal_limit_independent_of_bot_max_concurrent(self):
        """Per-bot max_concurrent_deals=1, plan allows 50 → second bot CAN open a deal (plan not exhausted)."""
```

---

## Validation Gates

```bash
# ── Backend ───────────────────────────────────────────────────────────────────
cd /home/ec2-user/ZenithGrid/backend

# Lint
venv/bin/python3 -m flake8 app/services/subscription_service.py \
    app/routers/billing_router.py --max-line-length=120

# Type safety
venv/bin/python3 -c "from app.services.subscription_service import get_user_plan; print('OK')"
venv/bin/python3 -c "from app.routers.billing_router import router; print('OK')"

# Migration dry-run
venv/bin/python3 -c "
import asyncio
from migrations.migration_072 import run_migration
print('Migration import OK')
"

# Tests (targeted)
venv/bin/python3 -m pytest tests/services/test_subscription_service.py -v
venv/bin/python3 -m pytest tests/routers/test_billing_router.py -v
venv/bin/python3 -m pytest tests/routers/test_bot_crud_router.py -k "limit" -v
venv/bin/python3 -m pytest tests/routers/test_accounts_router.py -k "limit" -v

# ── Frontend ──────────────────────────────────────────────────────────────────
cd /home/ec2-user/ZenithGrid/frontend

# TypeScript
npx tsc --noEmit

# Build check
npm run build
```

---

## Error Handling

### 402 Payment Required
All plan enforcement raises HTTP 402 with a consistent body:
```json
{
  "error": "plan_limit",
  "feature": "bots",
  "limit": 2,
  "current": 2,
  "upgrade_url": "/settings#billing"
}
```
or:
```json
{
  "error": "feature_gate",
  "feature": "reports_pdf",
  "required_plan": "base",
  "upgrade_url": "/settings#billing"
}
```

Frontend intercepts 402 responses in `api.ts` interceptor and triggers the UpgradeModal
automatically, passing the `feature` and `required_plan` from the response body.

### Webhook Idempotency
Stripe may deliver the same webhook event more than once. `sync_subscription_from_stripe`
uses upsert (load existing row, update in place) rather than insert, so duplicate events
are safe.

### Stripe API Failures
All Stripe API calls in the billing router are wrapped in try/except. Stripe errors surface
as 502 (gateway error), not 500, to distinguish billing infrastructure issues from bugs.

### `billing_enabled = False` (default)
When `billing_enabled=False` in config, checkout/portal endpoints return 503. The
subscription service still enforces limits (based on DB plan rows). This allows testing
limit enforcement in staging without a live Stripe account.

---

## Key Files to Reference During Implementation

| File | What to read | Purpose |
|------|-------------|---------|
| `backend/app/models/auth.py` | Full file | Extend User; add SubscriptionPlan + UserSubscription models |
| `backend/app/auth_routers/schemas.py` | `UserResponse` class | Extend with plan fields |
| `backend/app/auth_routers/auth_core_router.py` | login + me endpoints | Where to inject plan data into response |
| `backend/app/config.py` | Full file | Add Stripe keys using same BaseSettings pattern |
| `backend/migrations/add_session_limits.py` | Full file | Idempotent async migration pattern |
| `backend/migrations/add_rbac_tables.py` | Full file | Table creation + seed data pattern |
| `backend/app/routers/accounts_router.py` | `create_account` function | Where to add enforce_live_account_limit |
| `backend/app/bot_routers/bot_crud_router.py` | `create_bot` function | Where to add enforce_bot_limit |
| `backend/app/trading_engine/signal_processor.py` | lines 389–415 (max_concurrent_deals block) | Add user-level deal gate immediately before this block |
| `backend/app/trading_engine/position_manager.py` | `get_open_positions_count` (line 223) | Pattern for `get_open_positions_count_for_user` |
| `backend/app/services/rebalance_monitor.py` | `_process_account` function | Where to add auto_rebalance gate |
| `backend/app/main.py` | Router registration + PUBLIC_ENDPOINTS | Add billing router + webhook to public |
| `frontend/src/contexts/AuthContext.tsx` | Full file | Extend User type + add usePlan hook |
| `frontend/src/pages/Settings.tsx` | Section structure | Add Billing section in correct place |
| `backend/tests/conftest.py` | Fixtures | Use existing test_user, db_session fixtures |
| `COMMERCIALIZATION.md` | Phase 3 section | Pricing context and commercialization goals |

---

## Gotchas & Known Pitfalls

1. **Webhook endpoint must bypass JWT auth** — add to `PUBLIC_ENDPOINTS` in `main.py`.
   Do NOT wrap with `require_permission`. Stripe does NOT send auth tokens.

2. **PostgreSQL schema qualification** — `UserSubscription` ForeignKey must use
   `ForeignKey("auth.users.id")` not `ForeignKey("users.id")` (domain schemas in place
   since migration 068).

3. **Stripe webhook raw body** — Stripe signature verification requires the raw request body,
   NOT JSON-parsed. Use `await request.body()` in FastAPI, not `await request.json()`.

4. **`billing_enabled=False` default** — enforcement logic still runs against DB plan rows.
   This is intentional: allows testing limit enforcement before Stripe is wired up.

5. **`max_bots=0` means unlimited** — check `== 0` explicitly, never `if not max_bots`.

6. **Existing users get seeded Free subscriptions** — migration seeds a `user_subscriptions`
   row for every existing user. `get_user_plan()` still handles the None case gracefully.

7. **Trial period is per-user, not per-plan** — only granted if user has never had a paid
   subscription. Check subscription history before applying `trial_period_days`.

8. **Stripe Customer Portal requires configuration** — must be set up in Stripe Dashboard
   before portal sessions can be created. See Setup Guide above.

9. **Frontend 402 interceptor** — add 402 handling to `api.ts` interceptor alongside the
   existing 401 handler. Trigger global UpgradeModal with the feature/plan from response body.

10. **`is_deal_allowed` vs `enforce_deal_limit`** — two functions, different contexts.
    `is_deal_allowed()` returns `(bool, str)` for use in background loops (signal_processor,
    multi_bot_monitor) where you cannot raise HTTPException. `enforce_deal_limit()` raises
    HTTP 402 for use in HTTP request handlers. Never call the HTTP-raising version from
    background tasks — it will crash the scheduler job.

11. **Plan in JWT vs DB** — do NOT bake plan into the JWT. Always load from DB. Plan changes
    via Stripe webhooks take effect immediately on next API call (no need to re-login).
    JWT only carries user_id; plan is always DB-authoritative.

---

## Confidence Score: 8/10

-1 for Stripe Checkout integration (no existing Stripe code to reference — first time)
-1 for frontend UpgradeModal UX polish (plan comparison tables are deceptively complex to
   make look great; budget extra time for the billing UI)

All backend enforcement, DB schema, and service layer are straightforward given the existing
RBAC + async SQLAlchemy patterns in the codebase. The Stripe integration itself uses the
simplest possible Stripe approach (Checkout + Portal) which avoids all PCI scope and custom
payment form complexity.
