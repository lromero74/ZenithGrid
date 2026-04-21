"""
Tests for backend/app/routers/templates.py

Focus: code-quality sweep v2.160.4 Phase 2.3 — template name-uniqueness
must not leak information about other users' templates.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.models import BotTemplate, User


# Patch StrategyRegistry validation so tests can focus on the name-uniqueness
# logic without having to construct a fully valid strategy config. The router
# calls StrategyRegistry.get_definition() and get_strategy() before the
# uniqueness check — both must pass for us to reach the branch under test.
@pytest.fixture(autouse=True)
def _skip_strategy_validation():
    with patch("app.routers.templates.StrategyRegistry") as mock_reg:
        mock_reg.get_definition.return_value = object()
        mock_reg.get_strategy.return_value = object()
        yield


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def user_a(db_session):
    u = User(
        email="alice@test.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.fixture
async def user_b(db_session):
    u = User(
        email="bob@test.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(u)
    await db_session.flush()
    return u


def _user_template(user_id: int, name: str, tid: int | None = None) -> BotTemplate:
    return BotTemplate(
        id=tid,
        user_id=user_id,
        name=name,
        description=None,
        strategy_type="conditional_dca",
        strategy_config={},
        product_ids=[],
        split_budget_across_pairs=False,
        is_default=False,
    )


def _default_template(name: str, tid: int | None = None) -> BotTemplate:
    return BotTemplate(
        id=tid,
        user_id=None,
        name=name,
        description=None,
        strategy_type="conditional_dca",
        strategy_config={},
        product_ids=[],
        split_budget_across_pairs=False,
        is_default=True,
    )


def _template_create_payload(name: str):
    from app.routers.templates import TemplateCreate

    return TemplateCreate(
        name=name,
        description=None,
        strategy_type="grid_trading",
        strategy_config={},
        product_ids=[],
        split_budget_across_pairs=False,
    )


# ---------------------------------------------------------------------------
# Phase 2.3 — per-user scoping of create_template name-uniqueness check
# ---------------------------------------------------------------------------


class TestCreateTemplateUniquenessIsScoped:
    """Name-uniqueness must consider only templates the caller can see."""

    @pytest.mark.asyncio
    async def test_other_users_name_does_not_leak_via_create(self, db_session, user_a, user_b):
        """User B creating a template with the same name as User A's must not
        hit the router's 'already exists' branch (which would leak info)."""
        from app.routers.templates import create_template

        db_session.add(_user_template(user_a.id, "SecretStrategy"))
        await db_session.flush()

        try:
            await create_template(
                template_data=_template_create_payload("SecretStrategy"),
                db=db_session,
                current_user=user_b,
            )
        except HTTPException as e:
            # 400 with an "already exists" message = router-level leak (bug).
            # Any other failure mode (e.g. generic 400 from an IntegrityError
            # handler, or success) is acceptable.
            assert "already exists" not in (e.detail or ""), (
                "router leaked another user's template name via the 400 response"
            )

    @pytest.mark.asyncio
    async def test_users_own_duplicate_name_is_rejected(self, db_session, user_a):
        """User A creating two templates with the same name still fails fast."""
        from app.routers.templates import create_template

        db_session.add(_user_template(user_a.id, "MyPreset"))
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await create_template(
                template_data=_template_create_payload("MyPreset"),
                db=db_session,
                current_user=user_a,
            )
        assert exc.value.status_code == 400
        assert "already exists" in exc.value.detail

    @pytest.mark.asyncio
    async def test_default_template_name_is_rejected(self, db_session, user_a):
        """Default template names are globally reserved — a regular user
        cannot shadow 'Conservative DCA'."""
        from app.routers.templates import create_template

        db_session.add(_default_template("Conservative DCA"))
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await create_template(
                template_data=_template_create_payload("Conservative DCA"),
                db=db_session,
                current_user=user_a,
            )
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Phase 2.3 — per-user scoping of update_template name-uniqueness check
# ---------------------------------------------------------------------------


class TestUpdateTemplateUniquenessIsScoped:
    @pytest.mark.asyncio
    async def test_rename_to_other_users_name_does_not_leak(self, db_session, user_a, user_b):
        """User B renaming their template to match User A's name must not
        produce a 400 that leaks 'already exists'."""
        from app.routers.templates import TemplateUpdate, update_template

        db_session.add(_user_template(user_a.id, "TopSecret", tid=1))
        db_session.add(_user_template(user_b.id, "MyTemplate", tid=2))
        await db_session.flush()

        try:
            await update_template(
                template_id=2,
                template_update=TemplateUpdate(name="TopSecret"),
                db=db_session,
                current_user=user_b,
            )
        except HTTPException as e:
            assert "already exists" not in (e.detail or ""), (
                "router leaked another user's template name on update"
            )

    @pytest.mark.asyncio
    async def test_rename_to_own_other_template_name_is_rejected(self, db_session, user_a):
        from app.routers.templates import TemplateUpdate, update_template

        db_session.add(_user_template(user_a.id, "FirstOne", tid=10))
        db_session.add(_user_template(user_a.id, "SecondOne", tid=11))
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await update_template(
                template_id=11,
                template_update=TemplateUpdate(name="FirstOne"),
                db=db_session,
                current_user=user_a,
            )
        assert exc.value.status_code == 400
        assert "already exists" in exc.value.detail

    @pytest.mark.asyncio
    async def test_rename_to_default_template_name_is_rejected(self, db_session, user_a):
        from app.routers.templates import TemplateUpdate, update_template

        db_session.add(_default_template("Balanced DCA", tid=100))
        db_session.add(_user_template(user_a.id, "MyTmpl", tid=101))
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await update_template(
                template_id=101,
                template_update=TemplateUpdate(name="Balanced DCA"),
                db=db_session,
                current_user=user_a,
            )
        assert exc.value.status_code == 400
