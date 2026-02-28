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

    @pytest.mark.asyncio
    async def test_returns_single_category(self, db_session):
        """Happy path: single category stored is returned."""
        setting = Settings(
            key=ALLOWED_CATEGORIES_KEY,
            value=json.dumps(["SPECULATIVE"]),
            value_type="string",
        )
        db_session.add(setting)
        await db_session.commit()

        result = await get_allowed_categories(db_session)
        assert result == ["SPECULATIVE"]

    @pytest.mark.asyncio
    async def test_returns_many_categories(self, db_session):
        """Happy path: multiple categories stored are all returned."""
        categories = ["APPROVED", "SPECULATIVE", "STABLECOIN", "MEME"]
        setting = Settings(
            key=ALLOWED_CATEGORIES_KEY,
            value=json.dumps(categories),
            value_type="string",
        )
        db_session.add(setting)
        await db_session.commit()

        result = await get_allowed_categories(db_session)
        assert result == categories
        assert len(result) == 4

    @pytest.mark.asyncio
    async def test_ignores_other_settings_keys(self, db_session):
        """Edge case: settings with different keys don't interfere."""
        other_setting = Settings(
            key="some_other_key",
            value=json.dumps(["SHOULD_NOT_RETURN"]),
            value_type="string",
        )
        db_session.add(other_setting)
        await db_session.commit()

        result = await get_allowed_categories(db_session)
        assert result == DEFAULT_ALLOWED_CATEGORIES

    @pytest.mark.asyncio
    async def test_returns_default_when_value_is_empty_string(self, db_session):
        """Edge case: empty string value falls back to default."""
        setting = Settings(
            key=ALLOWED_CATEGORIES_KEY,
            value="",
            value_type="string",
        )
        db_session.add(setting)
        await db_session.commit()

        result = await get_allowed_categories(db_session)
        # Empty string is falsy, so falls into the default branch
        assert result == DEFAULT_ALLOWED_CATEGORIES

    @pytest.mark.asyncio
    async def test_default_categories_is_approved_only(self):
        """Sanity check: default constant is APPROVED only."""
        assert DEFAULT_ALLOWED_CATEGORIES == ["APPROVED"]

    @pytest.mark.asyncio
    async def test_key_constant_value(self):
        """Sanity check: key constant matches expected string."""
        assert ALLOWED_CATEGORIES_KEY == "allowed_coin_categories"
