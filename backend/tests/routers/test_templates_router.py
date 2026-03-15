"""
Tests for backend/app/routers/templates.py

Covers CRUD operations for bot templates: create, list, get, update, delete,
and the seed-defaults admin endpoint.
"""

import pytest

from sqlalchemy import select

from app.models import BotTemplate, BotTemplateProduct, User

# Valid strategy type and config for use across tests
_VALID_STRATEGY = "indicator_based"
_VALID_CONFIG = {}  # indicator_based accepts empty config (uses defaults)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db_session, email="templates_test@example.com", is_superuser=False):
    """Create and flush a test User."""
    user = User(
        email=email,
        hashed_password="hashed",
        display_name="Tester",
        is_superuser=is_superuser,
    )
    db_session.add(user)
    return user


async def _make_template(db_session, user, name="My Template", is_default=False,
                         strategy_type=None, strategy_config=None,
                         product_ids=None, user_id_override=None):
    """Create and flush a BotTemplate.

    For default templates, user_id is set to None unless user_id_override is given.
    """
    uid = user_id_override if user_id_override is not None else (
        None if is_default else user.id
    )
    template = BotTemplate(
        user_id=uid,
        name=name,
        description="Test template",
        strategy_type=strategy_type or _VALID_STRATEGY,
        strategy_config=strategy_config or _VALID_CONFIG,
        product_ids=product_ids or [],
        split_budget_across_pairs=False,
        is_default=is_default,
    )
    db_session.add(template)
    await db_session.flush()
    await db_session.refresh(template)
    return template


# ---------------------------------------------------------------------------
# CREATE template
# ---------------------------------------------------------------------------

class TestCreateTemplate:
    """Tests for POST /api/templates"""

    @pytest.mark.asyncio
    async def test_create_template_happy_path(self, db_session):
        """Happy path: creates a template and returns it."""
        from app.routers.templates import create_template, TemplateCreate

        user = _make_user(db_session)
        await db_session.flush()

        data = TemplateCreate(
            name="New Template",
            description="A test template",
            strategy_type=_VALID_STRATEGY,
            strategy_config=_VALID_CONFIG,
            product_ids=["BTC-USD", "ETH-USD"],
        )

        result = await create_template(data, db=db_session, current_user=user)

        assert result.name == "New Template"
        assert result.is_default is False
        assert result.user_id == user.id

    @pytest.mark.asyncio
    async def test_create_template_unknown_strategy_raises_400(self, db_session):
        """Failure: unknown strategy type raises HTTPException 400."""
        from fastapi import HTTPException
        from app.routers.templates import create_template, TemplateCreate

        user = _make_user(db_session)
        await db_session.flush()

        data = TemplateCreate(
            name="Bad Strategy",
            strategy_type="nonexistent_strategy",
            strategy_config={},
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_template(data, db=db_session, current_user=user)
        assert exc_info.value.status_code == 400
        assert "Unknown strategy" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_template_duplicate_name_raises_400(self, db_session):
        """Failure: duplicate template name raises HTTPException 400."""
        from fastapi import HTTPException
        from app.routers.templates import create_template, TemplateCreate

        user = _make_user(db_session)
        await db_session.flush()

        await _make_template(db_session, user, name="Duplicate Name")

        data = TemplateCreate(
            name="Duplicate Name",
            strategy_type=_VALID_STRATEGY,
            strategy_config=_VALID_CONFIG,
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_template(data, db=db_session, current_user=user)
        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_template_creates_junction_rows(self, db_session):
        """Edge case: product_ids creates BotTemplateProduct junction rows."""
        from app.routers.templates import create_template, TemplateCreate

        user = _make_user(db_session)
        await db_session.flush()

        data = TemplateCreate(
            name="With Products",
            strategy_type=_VALID_STRATEGY,
            strategy_config=_VALID_CONFIG,
            product_ids=["BTC-USD", "ETH-USD"],
        )

        result = await create_template(data, db=db_session, current_user=user)

        q = select(BotTemplateProduct).where(BotTemplateProduct.template_id == result.id)
        rows = (await db_session.execute(q)).scalars().all()
        assert len(rows) == 2
        pids = {r.product_id for r in rows}
        assert pids == {"BTC-USD", "ETH-USD"}

    @pytest.mark.asyncio
    async def test_create_template_no_product_ids_defaults_empty(self, db_session):
        """Edge case: no product_ids defaults to empty list."""
        from app.routers.templates import create_template, TemplateCreate

        user = _make_user(db_session, email="noproducts@test.com")
        await db_session.flush()

        data = TemplateCreate(
            name="No Products",
            strategy_type=_VALID_STRATEGY,
            strategy_config=_VALID_CONFIG,
        )

        result = await create_template(data, db=db_session, current_user=user)
        assert result.product_ids == []


# ---------------------------------------------------------------------------
# LIST templates
# ---------------------------------------------------------------------------

class TestListTemplates:
    """Tests for GET /api/templates"""

    @pytest.mark.asyncio
    async def test_list_templates_returns_own_and_defaults(self, db_session):
        """Happy path: user sees their own templates and defaults."""
        from app.routers.templates import list_templates

        user = _make_user(db_session)
        await db_session.flush()

        await _make_template(db_session, user, name="User Template")
        await _make_template(db_session, user, name="Default Template", is_default=True)

        result = await list_templates(db=db_session, current_user=user)

        names = [t.name for t in result]
        assert "User Template" in names
        assert "Default Template" in names

    @pytest.mark.asyncio
    async def test_list_templates_excludes_other_users(self, db_session):
        """Edge case: user should NOT see another user's templates."""
        from app.routers.templates import list_templates

        user1 = _make_user(db_session, email="user1@test.com")
        user2 = _make_user(db_session, email="user2@test.com")
        await db_session.flush()

        await _make_template(db_session, user1, name="User1 Template")
        await _make_template(db_session, user2, name="User2 Template")

        result = await list_templates(db=db_session, current_user=user2)

        names = [t.name for t in result]
        assert "User2 Template" in names
        assert "User1 Template" not in names

    @pytest.mark.asyncio
    async def test_list_templates_empty_result(self, db_session):
        """Edge case: no templates returns empty list."""
        from app.routers.templates import list_templates

        user = _make_user(db_session, email="empty@test.com")
        await db_session.flush()

        result = await list_templates(db=db_session, current_user=user)
        assert result == []


# ---------------------------------------------------------------------------
# GET template by ID
# ---------------------------------------------------------------------------

class TestGetTemplate:
    """Tests for GET /api/templates/{template_id}"""

    @pytest.mark.asyncio
    async def test_get_template_own_template(self, db_session):
        """Happy path: user can get their own template."""
        from app.routers.templates import get_template

        user = _make_user(db_session)
        await db_session.flush()
        template = await _make_template(db_session, user, name="My Get Test")

        result = await get_template(template.id, db=db_session, current_user=user)
        assert result.name == "My Get Test"

    @pytest.mark.asyncio
    async def test_get_template_default_visible_to_all(self, db_session):
        """Happy path: default templates are visible to any user."""
        from app.routers.templates import get_template

        user1 = _make_user(db_session, email="owner@test.com")
        user2 = _make_user(db_session, email="viewer@test.com")
        await db_session.flush()
        default_tmpl = await _make_template(db_session, user1, name="Default Visible", is_default=True)

        result = await get_template(default_tmpl.id, db=db_session, current_user=user2)
        assert result.name == "Default Visible"

    @pytest.mark.asyncio
    async def test_get_template_not_found_raises_404(self, db_session):
        """Failure: non-existent template returns 404."""
        from fastapi import HTTPException
        from app.routers.templates import get_template

        user = _make_user(db_session, email="nofind@test.com")
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_template(99999, db=db_session, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_template_other_user_raises_404(self, db_session):
        """Failure: cannot see another user's non-default template."""
        from fastapi import HTTPException
        from app.routers.templates import get_template

        user1 = _make_user(db_session, email="private_owner@test.com")
        user2 = _make_user(db_session, email="snooper@test.com")
        await db_session.flush()
        tmpl = await _make_template(db_session, user1, name="Private Template")

        with pytest.raises(HTTPException) as exc_info:
            await get_template(tmpl.id, db=db_session, current_user=user2)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# UPDATE template
# ---------------------------------------------------------------------------

class TestUpdateTemplate:
    """Tests for PUT /api/templates/{template_id}"""

    @pytest.mark.asyncio
    async def test_update_template_name(self, db_session):
        """Happy path: update template name."""
        from app.routers.templates import update_template, TemplateUpdate

        user = _make_user(db_session, email="updater@test.com")
        await db_session.flush()
        tmpl = await _make_template(db_session, user, name="Old Name")

        update_data = TemplateUpdate(name="New Name")
        result = await update_template(tmpl.id, update_data, db=db_session, current_user=user)
        assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_update_template_not_found_raises_404(self, db_session):
        """Failure: updating non-existent template raises 404."""
        from fastapi import HTTPException
        from app.routers.templates import update_template, TemplateUpdate

        user = _make_user(db_session, email="noupdate@test.com")
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await update_template(99999, TemplateUpdate(name="X"), db=db_session, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_default_template_raises_403(self, db_session):
        """Failure: cannot edit default templates even if user owns them."""
        from fastapi import HTTPException
        from app.routers.templates import update_template, TemplateUpdate

        user = _make_user(db_session, email="defaultedit@test.com")
        await db_session.flush()
        # Default template with user_id set to this user so the ownership
        # check passes, but the is_default guard should block the edit.
        tmpl = await _make_template(
            db_session, user, name="Default No Edit",
            is_default=True, user_id_override=user.id,
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_template(tmpl.id, TemplateUpdate(name="Edited"), db=db_session, current_user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_update_template_duplicate_name_raises_400(self, db_session):
        """Failure: renaming to an existing name raises 400."""
        from fastapi import HTTPException
        from app.routers.templates import update_template, TemplateUpdate

        user = _make_user(db_session, email="dupname@test.com")
        await db_session.flush()
        await _make_template(db_session, user, name="Existing Name")
        tmpl2 = await _make_template(db_session, user, name="Other Name")

        with pytest.raises(HTTPException) as exc_info:
            await update_template(tmpl2.id, TemplateUpdate(name="Existing Name"), db=db_session, current_user=user)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_template_product_ids_syncs_junction(self, db_session):
        """Edge case: updating product_ids replaces junction rows."""
        from app.routers.templates import update_template, TemplateUpdate

        user = _make_user(db_session, email="junc_update@test.com")
        await db_session.flush()
        tmpl = await _make_template(db_session, user, name="Junction Test")

        update_data = TemplateUpdate(product_ids=["SOL-USD", "DOGE-USD"])
        result = await update_template(tmpl.id, update_data, db=db_session, current_user=user)

        q = select(BotTemplateProduct).where(BotTemplateProduct.template_id == result.id)
        rows = (await db_session.execute(q)).scalars().all()
        pids = {r.product_id for r in rows}
        assert pids == {"SOL-USD", "DOGE-USD"}

    @pytest.mark.asyncio
    async def test_update_template_description(self, db_session):
        """Happy path: update only the description field."""
        from app.routers.templates import update_template, TemplateUpdate

        user = _make_user(db_session, email="desc_update@test.com")
        await db_session.flush()
        tmpl = await _make_template(db_session, user, name="Desc Test")

        update_data = TemplateUpdate(description="Updated description")
        result = await update_template(tmpl.id, update_data, db=db_session, current_user=user)
        assert result.description == "Updated description"

    @pytest.mark.asyncio
    async def test_update_template_split_budget(self, db_session):
        """Edge case: update split_budget_across_pairs flag."""
        from app.routers.templates import update_template, TemplateUpdate

        user = _make_user(db_session, email="split_update@test.com")
        await db_session.flush()
        tmpl = await _make_template(db_session, user, name="Split Test")
        assert tmpl.split_budget_across_pairs is False

        update_data = TemplateUpdate(split_budget_across_pairs=True)
        result = await update_template(tmpl.id, update_data, db=db_session, current_user=user)
        assert result.split_budget_across_pairs is True


# ---------------------------------------------------------------------------
# DELETE template
# ---------------------------------------------------------------------------

class TestDeleteTemplate:
    """Tests for DELETE /api/templates/{template_id}"""

    @pytest.mark.asyncio
    async def test_delete_template_happy_path(self, db_session):
        """Happy path: deletes user's own template."""
        from app.routers.templates import delete_template

        user = _make_user(db_session, email="deleter@test.com")
        await db_session.flush()
        tmpl = await _make_template(db_session, user, name="To Delete")

        result = await delete_template(tmpl.id, db=db_session, current_user=user)
        assert "deleted" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_template_not_found_raises_404(self, db_session):
        """Failure: deleting non-existent template raises 404."""
        from fastapi import HTTPException
        from app.routers.templates import delete_template

        user = _make_user(db_session, email="nodelete@test.com")
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await delete_template(99999, db=db_session, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_default_template_raises_403(self, db_session):
        """Failure: cannot delete default templates even if user owns them."""
        from fastapi import HTTPException
        from app.routers.templates import delete_template

        user = _make_user(db_session, email="deldefault@test.com")
        await db_session.flush()
        # Set user_id_override so the ownership check passes,
        # then the is_default guard should block deletion.
        tmpl = await _make_template(
            db_session, user, name="Default No Delete",
            is_default=True, user_id_override=user.id,
        )

        with pytest.raises(HTTPException) as exc_info:
            await delete_template(tmpl.id, db=db_session, current_user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_other_user_template_raises_404(self, db_session):
        """Failure: cannot delete another user's template."""
        from fastapi import HTTPException
        from app.routers.templates import delete_template

        user1 = _make_user(db_session, email="owner_del@test.com")
        user2 = _make_user(db_session, email="thief_del@test.com")
        await db_session.flush()
        tmpl = await _make_template(db_session, user1, name="Not Yours To Delete")

        with pytest.raises(HTTPException) as exc_info:
            await delete_template(tmpl.id, db=db_session, current_user=user2)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# SEED defaults
# ---------------------------------------------------------------------------

class TestSeedDefaults:
    """Tests for POST /api/templates/seed-defaults"""

    @pytest.mark.asyncio
    async def test_seed_defaults_creates_templates(self, db_session):
        """Happy path: seeds 3 default templates when none exist."""
        from app.routers.templates import seed_default_templates

        user = _make_user(db_session, email="admin@test.com", is_superuser=True)
        await db_session.flush()

        result = await seed_default_templates(db=db_session, current_user=user)
        assert result["message"] == "Default templates created successfully"
        assert len(result["templates"]) == 3

    @pytest.mark.asyncio
    async def test_seed_defaults_idempotent(self, db_session):
        """Edge case: calling seed again when defaults exist does nothing."""
        from app.routers.templates import seed_default_templates

        user = _make_user(db_session, email="admin2@test.com", is_superuser=True)
        await db_session.flush()

        # Create a default template first
        await _make_template(db_session, user, name="Pre-existing Default", is_default=True)

        result = await seed_default_templates(db=db_session, current_user=user)
        assert "already exist" in result["message"]
