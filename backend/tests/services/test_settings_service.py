"""
Tests for backend/app/services/settings_service.py

Tests retrieval of allowed coin categories from the Settings table.
"""

import json

import pytest

from app.models import Settings
from app.services.settings_service import (
    get_allowed_categories,
    DEFAULT_ALLOWED_CATEGORIES,
    ALLOWED_CATEGORIES_KEY,
)


class TestGetAllowedCategories:
    """Tests for get_allowed_categories()."""

    @pytest.mark.asyncio
    async def test_returns_stored_categories(self, db_session):
        """Happy path: returns categories stored in the database."""
        setting = Settings(
            key=ALLOWED_CATEGORIES_KEY,
            value=json.dumps(["APPROVED", "SPECULATIVE"]),
            value_type="string",
        )
        db_session.add(setting)
        await db_session.commit()

        result = await get_allowed_categories(db_session)
        assert result == ["APPROVED", "SPECULATIVE"]

    @pytest.mark.asyncio
    async def test_returns_default_when_no_setting(self, db_session):
        """Edge case: no setting in DB returns default."""
        result = await get_allowed_categories(db_session)
        assert result == DEFAULT_ALLOWED_CATEGORIES

    @pytest.mark.asyncio
    async def test_returns_default_on_invalid_json(self, db_session):
        """Failure: invalid JSON value falls back to default."""
        setting = Settings(
            key=ALLOWED_CATEGORIES_KEY,
            value="not valid json {{{",
            value_type="string",
        )
        db_session.add(setting)
        await db_session.commit()

        result = await get_allowed_categories(db_session)
        assert result == DEFAULT_ALLOWED_CATEGORIES

    @pytest.mark.asyncio
    async def test_returns_default_when_value_is_none(self, db_session):
        """Edge case: setting exists but value is None."""
        setting = Settings(
            key=ALLOWED_CATEGORIES_KEY,
            value=None,
            value_type="string",
        )
        db_session.add(setting)
        await db_session.commit()

        result = await get_allowed_categories(db_session)
        assert result == DEFAULT_ALLOWED_CATEGORIES

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_stored_empty(self, db_session):
        """Edge case: stored empty list is returned as-is."""
        setting = Settings(
            key=ALLOWED_CATEGORIES_KEY,
            value=json.dumps([]),
            value_type="string",
        )
        db_session.add(setting)
        await db_session.commit()

        result = await get_allowed_categories(db_session)
        assert result == []
