"""
Tests for backend/app/services/coin_review_service.py

Covers:
- _parse_ai_response — JSON parsing with markdown handling
- call_ai_for_review — batched AI calls with mocked providers
- update_coin_statuses — database upsert logic
- run_weekly_review — full orchestration
- AI provider function dispatch
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from app.services.coin_review_service import (
    _parse_ai_response,
    call_ai_for_review,
    update_coin_statuses,
    run_weekly_review,
    VALID_AI_PROVIDERS,
    DEFAULT_AI_PROVIDER,
    COIN_REVIEW_PROMPT,
)


# ---------------------------------------------------------------------------
# _parse_ai_response
# ---------------------------------------------------------------------------


class TestParseAiResponse:
    """Tests for _parse_ai_response()"""

    def test_parse_plain_json(self):
        """Happy path: plain JSON is parsed correctly."""
        response = '{"BTC": {"category": "APPROVED", "reason": "Digital gold"}}'
        result = _parse_ai_response(response)

        assert "BTC" in result
        assert result["BTC"]["category"] == "APPROVED"
        assert result["BTC"]["reason"] == "Digital gold"

    def test_parse_markdown_code_block(self):
        """Edge case: JSON wrapped in markdown code block."""
        response = '```json\n{"ETH": {"category": "APPROVED", "reason": "DeFi king"}}\n```'
        result = _parse_ai_response(response)

        assert "ETH" in result
        assert result["ETH"]["category"] == "APPROVED"

    def test_parse_markdown_no_language(self):
        """Edge case: markdown code block without language tag."""
        response = '```\n{"SOL": {"category": "APPROVED", "reason": "Fast chain"}}\n```'
        result = _parse_ai_response(response)

        assert "SOL" in result

    def test_parse_with_whitespace(self):
        """Edge case: JSON with leading/trailing whitespace."""
        response = '  \n  {"ADA": {"category": "BORDERLINE", "reason": "Slow development"}}  \n  '
        result = _parse_ai_response(response)

        assert "ADA" in result
        assert result["ADA"]["category"] == "BORDERLINE"

    def test_parse_invalid_json_raises(self):
        """Failure: invalid JSON raises json.JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            _parse_ai_response("not valid json at all")

    def test_parse_multiple_coins(self):
        """Happy path: multiple coins in response."""
        response = json.dumps({
            "BTC": {"category": "APPROVED", "reason": "King"},
            "DOGE": {"category": "MEME", "reason": "Such wow"},
            "LUNA": {"category": "BLACKLISTED", "reason": "Collapsed"},
        })
        result = _parse_ai_response(response)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# call_ai_for_review
# ---------------------------------------------------------------------------


class TestCallAiForReview:
    """Tests for call_ai_for_review()"""

    @pytest.mark.asyncio
    async def test_single_batch_claude(self):
        """Happy path: single batch of coins processed by Claude."""
        ai_response = json.dumps({
            "BTC": {"category": "APPROVED", "reason": "Digital gold"},
            "ETH": {"category": "APPROVED", "reason": "DeFi platform"},
        })

        with patch(
            "app.services.coin_review_service.get_ai_review_provider_from_db",
            new_callable=AsyncMock,
            return_value="claude",
        ):
            with patch(
                "app.services.coin_review_service._call_claude",
                new_callable=AsyncMock,
                return_value=ai_response,
            ) as mock_call:
                result = await call_ai_for_review(["BTC", "ETH"], batch_size=50)

        assert "BTC" in result
        assert "ETH" in result
        mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_batches(self):
        """Edge case: coins split into multiple batches."""
        batch1_response = json.dumps({
            "BTC": {"category": "APPROVED", "reason": "Gold"},
        })
        batch2_response = json.dumps({
            "ETH": {"category": "APPROVED", "reason": "DeFi"},
        })

        with patch(
            "app.services.coin_review_service.get_ai_review_provider_from_db",
            new_callable=AsyncMock,
            return_value="claude",
        ):
            with patch(
                "app.services.coin_review_service._call_claude",
                new_callable=AsyncMock,
                side_effect=[batch1_response, batch2_response],
            ) as mock_call:
                result = await call_ai_for_review(["BTC", "ETH"], batch_size=1)

        assert "BTC" in result
        assert "ETH" in result
        assert mock_call.await_count == 2

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self):
        """Failure: unknown AI provider raises ValueError."""
        with patch(
            "app.services.coin_review_service.get_ai_review_provider_from_db",
            new_callable=AsyncMock,
            return_value="notreal",
        ):
            with pytest.raises(ValueError, match="Unknown AI provider"):
                await call_ai_for_review(["BTC"])

    @pytest.mark.asyncio
    async def test_openai_provider(self):
        """Happy path: OpenAI provider is dispatched correctly."""
        ai_response = json.dumps({
            "BTC": {"category": "APPROVED", "reason": "Digital gold"},
        })

        with patch(
            "app.services.coin_review_service.get_ai_review_provider_from_db",
            new_callable=AsyncMock,
            return_value="openai",
        ):
            with patch(
                "app.services.coin_review_service._call_openai",
                new_callable=AsyncMock,
                return_value=ai_response,
            ) as mock_call:
                result = await call_ai_for_review(["BTC"], batch_size=50)

        assert "BTC" in result
        mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_gemini_provider(self):
        """Happy path: Gemini provider is dispatched correctly."""
        ai_response = json.dumps({
            "BTC": {"category": "APPROVED", "reason": "Digital gold"},
        })

        with patch(
            "app.services.coin_review_service.get_ai_review_provider_from_db",
            new_callable=AsyncMock,
            return_value="gemini",
        ):
            with patch(
                "app.services.coin_review_service._call_gemini",
                new_callable=AsyncMock,
                return_value=ai_response,
            ) as mock_call:
                result = await call_ai_for_review(["BTC"], batch_size=50)

        assert "BTC" in result
        mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_grok_provider(self):
        """Happy path: Grok provider is dispatched correctly."""
        ai_response = json.dumps({
            "BTC": {"category": "APPROVED", "reason": "Digital gold"},
        })

        with patch(
            "app.services.coin_review_service.get_ai_review_provider_from_db",
            new_callable=AsyncMock,
            return_value="grok",
        ):
            with patch(
                "app.services.coin_review_service._call_grok",
                new_callable=AsyncMock,
                return_value=ai_response,
            ) as mock_call:
                result = await call_ai_for_review(["BTC"], batch_size=50)

        assert "BTC" in result
        mock_call.assert_awaited_once()


# ---------------------------------------------------------------------------
# update_coin_statuses
# ---------------------------------------------------------------------------


class TestUpdateCoinStatuses:
    """Tests for update_coin_statuses()"""

    @pytest.mark.asyncio
    async def test_adds_new_coins(self, db_session):
        """Happy path: new coins are added to blacklisted_coins."""
        analysis = {
            "BTC": {"category": "APPROVED", "reason": "Digital gold"},
            "DOGE": {"category": "MEME", "reason": "Such wow"},
        }

        # Mock async_session_maker to return our test session
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.coin_review_service.async_session_maker",
            return_value=mock_session_ctx,
        ):
            stats = await update_coin_statuses(analysis)

        assert stats["added"] == 2
        assert stats["updated"] == 0
        assert stats["unchanged"] == 0

    @pytest.mark.asyncio
    async def test_updates_existing_coin(self, db_session):
        """Edge case: existing coin with different reason gets updated."""
        from app.models import BlacklistedCoin

        # Pre-add a coin
        existing = BlacklistedCoin(symbol="BTC", reason="[APPROVED] Old reason", user_id=None)
        db_session.add(existing)
        await db_session.flush()

        analysis = {
            "BTC": {"category": "APPROVED", "reason": "New reason"},
        }

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.coin_review_service.async_session_maker",
            return_value=mock_session_ctx,
        ):
            stats = await update_coin_statuses(analysis)

        assert stats["updated"] == 1

    @pytest.mark.asyncio
    async def test_unchanged_coin(self, db_session):
        """Edge case: existing coin with same reason is unchanged."""
        from app.models import BlacklistedCoin

        # Pre-add a coin with exact reason that would be generated
        existing = BlacklistedCoin(symbol="BTC", reason="[APPROVED] Digital gold", user_id=None)
        db_session.add(existing)
        await db_session.flush()

        analysis = {
            "BTC": {"category": "APPROVED", "reason": "Digital gold"},
        }

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.coin_review_service.async_session_maker",
            return_value=mock_session_ctx,
        ):
            stats = await update_coin_statuses(analysis)

        assert stats["unchanged"] == 1

    @pytest.mark.asyncio
    async def test_blacklisted_category_no_prefix(self, db_session):
        """Edge case: BLACKLISTED category has no prefix in reason."""
        analysis = {
            "LUNA": {"category": "BLACKLISTED", "reason": "Collapsed"},
        }

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.coin_review_service.async_session_maker",
            return_value=mock_session_ctx,
        ):
            stats = await update_coin_statuses(analysis)

        assert stats["added"] == 1

        # Verify the stored reason has no prefix
        from app.models import BlacklistedCoin
        from sqlalchemy import select
        result = await db_session.execute(
            select(BlacklistedCoin).where(BlacklistedCoin.symbol == "LUNA")
        )
        coin = result.scalars().first()
        assert coin.reason == "Collapsed"  # No prefix


# ---------------------------------------------------------------------------
# run_weekly_review
# ---------------------------------------------------------------------------


class TestRunWeeklyReview:
    """Tests for run_weekly_review()"""

    @pytest.mark.asyncio
    async def test_successful_review(self):
        """Happy path: full review completes with status=success."""
        mock_coins = ["BTC", "ETH", "DOGE"]
        mock_analysis = {
            "BTC": {"category": "APPROVED", "reason": "King"},
            "ETH": {"category": "APPROVED", "reason": "DeFi"},
            "DOGE": {"category": "MEME", "reason": "Wow"},
        }
        mock_stats = {"added": 3, "updated": 0, "unchanged": 0}

        with patch(
            "app.services.coin_review_service.get_tracked_coins",
            new_callable=AsyncMock,
            return_value=mock_coins,
        ):
            with patch(
                "app.services.coin_review_service.call_ai_for_review",
                new_callable=AsyncMock,
                return_value=mock_analysis,
            ):
                with patch(
                    "app.services.coin_review_service.update_coin_statuses",
                    new_callable=AsyncMock,
                    return_value=mock_stats,
                ):
                    result = await run_weekly_review(standalone=False)

        assert result["status"] == "success"
        assert result["coins_analyzed"] == 3
        assert result["categories"]["APPROVED"] == 2
        assert result["categories"]["MEME"] == 1

    @pytest.mark.asyncio
    async def test_no_coins_found(self):
        """Edge case: no tracked coins returns error status."""
        with patch(
            "app.services.coin_review_service.get_tracked_coins",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await run_weekly_review(standalone=False)

        assert result["status"] == "error"
        assert "No tracked coins" in result["message"]

    @pytest.mark.asyncio
    async def test_exception_returns_error(self):
        """Failure: exception during review returns error status."""
        with patch(
            "app.services.coin_review_service.get_tracked_coins",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API key missing"),
        ):
            result = await run_weekly_review(standalone=False)

        assert result["status"] == "error"
        assert "API key missing" in result["message"]

    @pytest.mark.asyncio
    async def test_standalone_mode_inits_db(self):
        """Edge case: standalone=True calls init_db."""
        mock_coins = ["BTC"]
        mock_analysis = {"BTC": {"category": "APPROVED", "reason": "King"}}
        mock_stats = {"added": 1, "updated": 0, "unchanged": 0}

        with patch(
            "app.services.coin_review_service.init_db",
            new_callable=AsyncMock,
        ) as mock_init:
            with patch(
                "app.services.coin_review_service.get_tracked_coins",
                new_callable=AsyncMock,
                return_value=mock_coins,
            ):
                with patch(
                    "app.services.coin_review_service.call_ai_for_review",
                    new_callable=AsyncMock,
                    return_value=mock_analysis,
                ):
                    with patch(
                        "app.services.coin_review_service.update_coin_statuses",
                        new_callable=AsyncMock,
                        return_value=mock_stats,
                    ):
                        result = await run_weekly_review(standalone=True)

        mock_init.assert_awaited_once()
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify module-level constants."""

    def test_valid_providers(self):
        """Valid providers list matches expected providers."""
        assert "claude" in VALID_AI_PROVIDERS
        assert "openai" in VALID_AI_PROVIDERS
        assert "gemini" in VALID_AI_PROVIDERS
        assert "grok" in VALID_AI_PROVIDERS

    def test_default_provider_is_claude(self):
        """Default provider is Claude."""
        assert DEFAULT_AI_PROVIDER == "claude"

    def test_prompt_template_has_placeholder(self):
        """Prompt template has the coins_list placeholder."""
        assert "{coins_list}" in COIN_REVIEW_PROMPT
