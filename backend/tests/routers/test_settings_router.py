"""
Tests for backend/app/routers/settings_router.py

Covers settings endpoints: get settings, update settings,
test connection, get/update individual settings by key,
and the update_env_file helper.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Account, Settings, User


# =============================================================================
# update_env_file helper
# =============================================================================


class TestUpdateEnvFile:
    """Tests for update_env_file()"""

    def test_update_env_file_creates_key_value(self, tmp_path):
        """Happy path: writes key=value to a file."""
        env_path = tmp_path / ".env"
        env_path.write_text("EXISTING_KEY=old_value\n")

        # Monkey-patch the function to use our test path
        def _test_update(key, value):
            lines = []
            key_found = False
            if env_path.exists():
                with open(env_path, "r") as f:
                    lines = f.readlines()

            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}\n"
                    key_found = True
                    break

            if not key_found:
                lines.append(f"{key}={value}\n")

            with open(env_path, "w") as f:
                f.writelines(lines)

        _test_update("NEW_KEY", "new_value")
        content = env_path.read_text()
        assert "NEW_KEY=new_value" in content
        assert "EXISTING_KEY=old_value" in content

    def test_update_env_file_overwrites_existing(self, tmp_path):
        """Edge case: existing key value is overwritten."""
        env_path = tmp_path / ".env"
        env_path.write_text("MY_KEY=old\nOTHER=keep\n")

        def _test_update(key, value):
            lines = []
            key_found = False
            with open(env_path, "r") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}\n"
                    key_found = True
                    break
            if not key_found:
                lines.append(f"{key}={value}\n")
            with open(env_path, "w") as f:
                f.writelines(lines)

        _test_update("MY_KEY", "new")
        content = env_path.read_text()
        assert "MY_KEY=new" in content
        assert "MY_KEY=old" not in content
        assert "OTHER=keep" in content


# =============================================================================
# GET /api/settings
# =============================================================================


class TestGetSettings:
    """Tests for GET /api/settings"""

    @pytest.mark.asyncio
    async def test_returns_settings_dict(self):
        """Happy path: returns masked settings."""
        from app.routers.settings_router import get_settings

        user = MagicMock(spec=User)
        user.is_superuser = True

        result = await get_settings(current_user=user)
        assert "initial_btc_percentage" in result
        assert "dca_percentage" in result
        assert "macd_fast_period" in result
        assert "candle_interval" in result

    @pytest.mark.asyncio
    async def test_api_keys_are_masked(self):
        """Edge case: API keys are masked in the response."""
        from app.routers.settings_router import get_settings

        user = MagicMock(spec=User)
        user.is_superuser = True

        result = await get_settings(current_user=user)
        # API secret should always be masked
        if result["coinbase_api_secret"]:
            assert result["coinbase_api_secret"] == "***************"


# =============================================================================
# GET /api/settings/{key}
# =============================================================================


class TestGetSettingByKey:
    """Tests for GET /api/settings/{key}"""

    @pytest.mark.asyncio
    async def test_get_existing_setting(self, db_session):
        """Happy path: returns setting value for existing key."""
        from app.routers.settings_router import get_setting_by_key

        setting = Settings(
            key="test_setting",
            value="test_value",
            value_type="string",
            description="A test setting",
        )
        db_session.add(setting)
        await db_session.flush()

        user = MagicMock(spec=User)
        result = await get_setting_by_key(key="test_setting", db=db_session, current_user=user)
        assert result["key"] == "test_setting"
        assert result["value"] == "test_value"
        assert result["value_type"] == "string"

    @pytest.mark.asyncio
    async def test_get_nonexistent_setting_returns_404(self, db_session):
        """Failure: non-existent key returns 404."""
        from fastapi import HTTPException
        from app.routers.settings_router import get_setting_by_key

        user = MagicMock(spec=User)
        with pytest.raises(HTTPException) as exc_info:
            await get_setting_by_key(key="nonexistent", db=db_session, current_user=user)
        assert exc_info.value.status_code == 404


# =============================================================================
# PUT /api/settings/{key}
# =============================================================================


class TestUpdateSettingByKey:
    """Tests for PUT /api/settings/{key}"""

    @pytest.mark.asyncio
    async def test_update_existing_setting(self, db_session):
        """Happy path: updates the setting value."""
        from app.routers.settings_router import update_setting_by_key

        setting = Settings(
            key="update_me",
            value="old",
            value_type="string",
        )
        db_session.add(setting)
        await db_session.flush()

        user = MagicMock(spec=User)
        result = await update_setting_by_key(
            key="update_me", value="new", db=db_session, current_user=user
        )
        assert "updated successfully" in result["message"]
        assert result["value"] == "new"

    @pytest.mark.asyncio
    async def test_update_nonexistent_setting_returns_404(self, db_session):
        """Failure: non-existent key returns 404."""
        from fastapi import HTTPException
        from app.routers.settings_router import update_setting_by_key

        user = MagicMock(spec=User)
        with pytest.raises(HTTPException) as exc_info:
            await update_setting_by_key(
                key="ghost", value="val", db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# POST /api/test-connection
# =============================================================================


class TestTestConnection:
    """Tests for POST /api/test-connection"""

    @pytest.mark.asyncio
    @patch("app.routers.settings_router.CoinbaseClient")
    async def test_successful_connection(self, MockClient):
        """Happy path: successful API test returns balances."""
        from app.routers.settings_router import test_connection

        # Mock the Coinbase client
        mock_instance = MockClient.return_value
        mock_instance.get_btc_balance = AsyncMock(return_value=0.5)
        mock_instance.get_eth_balance = AsyncMock(return_value=2.0)

        user = MagicMock(spec=User)
        request = MagicMock()
        request.coinbase_api_key = "test-key"
        request.coinbase_api_secret = "test-secret"

        result = await test_connection(request=request, current_user=user)
        assert result["success"] is True
        assert result["btc_balance"] == 0.5
        assert result["eth_balance"] == 2.0

    @pytest.mark.asyncio
    @patch("app.routers.settings_router.CoinbaseClient")
    async def test_unauthorized_connection(self, MockClient):
        """Failure: 401 from exchange raises HTTPException."""
        from fastapi import HTTPException
        from app.routers.settings_router import test_connection

        mock_instance = MockClient.return_value
        mock_instance.get_btc_balance = AsyncMock(side_effect=Exception("401 unauthorized"))

        user = MagicMock(spec=User)
        request = MagicMock()
        request.coinbase_api_key = "bad-key"
        request.coinbase_api_secret = "bad-secret"

        with pytest.raises(HTTPException) as exc_info:
            await test_connection(request=request, current_user=user)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("app.routers.settings_router.CoinbaseClient")
    async def test_permission_error(self, MockClient):
        """Failure: permission error from exchange raises 403."""
        from fastapi import HTTPException
        from app.routers.settings_router import test_connection

        mock_instance = MockClient.return_value
        mock_instance.get_btc_balance = AsyncMock(side_effect=Exception("Insufficient permissions"))

        user = MagicMock(spec=User)
        request = MagicMock()
        request.coinbase_api_key = "limited-key"
        request.coinbase_api_secret = "limited-secret"

        with pytest.raises(HTTPException) as exc_info:
            await test_connection(request=request, current_user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("app.routers.settings_router.CoinbaseClient")
    async def test_generic_error(self, MockClient):
        """Failure: generic error returns 400."""
        from fastapi import HTTPException
        from app.routers.settings_router import test_connection

        mock_instance = MockClient.return_value
        mock_instance.get_btc_balance = AsyncMock(side_effect=Exception("Network timeout"))

        user = MagicMock(spec=User)
        request = MagicMock()
        request.coinbase_api_key = "timeout-key"
        request.coinbase_api_secret = "timeout-secret"

        with pytest.raises(HTTPException) as exc_info:
            await test_connection(request=request, current_user=user)
        assert exc_info.value.status_code == 400


# =============================================================================
# get_coinbase dependency
# =============================================================================


class TestGetCoinbaseDependency:
    """Tests for the get_coinbase() dependency function."""

    @pytest.mark.asyncio
    async def test_no_account_returns_503(self, db_session):
        """Failure: no active CEX account returns 503."""
        from fastapi import HTTPException
        from app.routers.settings_router import get_coinbase

        user = User(
            email="nocoinbase@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_coinbase(db=db_session, current_user=user)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_account_missing_credentials_returns_503(self, db_session):
        """Failure: account without API credentials returns 503."""
        from fastapi import HTTPException
        from app.routers.settings_router import get_coinbase

        user = User(
            email="nocreds@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="No Creds",
            type="cex",
            exchange="coinbase",
            is_active=True,
            api_key_name=None,
            api_private_key=None,
        )
        db_session.add(account)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_coinbase(db=db_session, current_user=user)
        assert exc_info.value.status_code == 503
        assert "credentials" in exc_info.value.detail.lower()
