"""
Background service for monitoring US debt ceiling legislation changes.

This service runs weekly to check for new debt ceiling legislation that
may have been passed since our last recorded entry. Uses the system AI
(same as coin review) to analyze Congressional sources and news for
debt ceiling changes.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.news_data import DEBT_CEILING_HISTORY
from app.services.coin_review_service import (
    _call_claude,
    _call_gemini,
    _call_grok,
    _call_openai,
    get_ai_review_provider_from_db,
)

logger = logging.getLogger(__name__)

# Check interval: once per week (in seconds)
CHECK_INTERVAL = 7 * 24 * 60 * 60  # 7 days
INITIAL_DELAY = 60 * 5  # Wait 5 minutes after startup

# Cache file for tracking last check
CACHE_DIR = Path(__file__).parent.parent.parent
DEBT_CEILING_CHECK_CACHE = CACHE_DIR / "debt_ceiling_check_cache.json"


class DebtCeilingMonitor:
    """Background service that monitors for new debt ceiling legislation."""

    def __init__(self):
        self._task = None
        self._running = False
        self._last_check: datetime | None = None
        self._last_result: Dict[str, Any] | None = None

    async def start(self):
        """Start the background monitor task."""
        if self._running:
            logger.warning("Debt ceiling monitor already running")
            return

        self._running = True
        self._load_cache()
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Debt ceiling monitor started")

    async def stop(self):
        """Stop the background monitor task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Debt ceiling monitor stopped")

    def _load_cache(self):
        """Load last check timestamp from cache."""
        try:
            if DEBT_CEILING_CHECK_CACHE.exists():
                with open(DEBT_CEILING_CHECK_CACHE, "r") as f:
                    data = json.load(f)
                    if "last_check" in data:
                        self._last_check = datetime.fromisoformat(data["last_check"])
                    self._last_result = data.get("last_result")
                    logger.info(f"Loaded debt ceiling check cache, last check: {self._last_check}")
        except Exception as e:
            logger.warning(f"Failed to load debt ceiling check cache: {e}")

    def _save_cache(self):
        """Save last check timestamp to cache."""
        try:
            data = {
                "last_check": self._last_check.isoformat() if self._last_check else None,
                "last_result": self._last_result,
            }
            with open(DEBT_CEILING_CHECK_CACHE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save debt ceiling check cache: {e}")

    async def _monitor_loop(self):
        """Main loop that checks for debt ceiling changes weekly."""
        await asyncio.sleep(INITIAL_DELAY)

        while self._running:
            try:
                now = datetime.utcnow()

                # Check if we need to run
                should_check = False
                if self._last_check is None:
                    should_check = True
                else:
                    time_since_check = (now - self._last_check).total_seconds()
                    if time_since_check >= CHECK_INTERVAL:
                        should_check = True

                if should_check:
                    await self._check_for_updates()
                    self._last_check = now
                    self._save_cache()

            except Exception as e:
                logger.error(f"Error in debt ceiling monitor loop: {e}")

            # Sleep for an hour before checking again if we need to run
            await asyncio.sleep(60 * 60)

    async def _check_for_updates(self):
        """Check Congressional sources for new debt ceiling legislation."""
        logger.info("Debt ceiling monitor: Checking for new legislation...")

        try:
            # Get the most recent entry date from our history
            latest_entry_date = None
            latest_ceiling = None
            if DEBT_CEILING_HISTORY:
                latest_entry = DEBT_CEILING_HISTORY[0]
                latest_entry_date = latest_entry.get("date")
                latest_ceiling = latest_entry.get("amount_trillion")

            # Use AI to check for new debt ceiling legislation
            result = await self._ai_check_debt_ceiling(latest_entry_date, latest_ceiling)

            self._last_result = result

            if result and result.get("new_legislation_found"):
                logger.warning(
                    f"Debt ceiling monitor: NEW LEGISLATION DETECTED! "
                    f"Date: {result.get('date')}, Amount: ${result.get('amount_trillion')}T, "
                    f"Legislation: {result.get('legislation')}"
                )
                logger.warning(
                    "ACTION REQUIRED: Update debt_ceiling_data.py with the new entry."
                )
            else:
                logger.info("Debt ceiling monitor: No new legislation found since last entry")

        except Exception as e:
            logger.error(f"Debt ceiling monitor: Error checking for updates: {e}")

    async def _ai_check_debt_ceiling(
        self, latest_date: Optional[str], latest_ceiling: Optional[float]
    ) -> Dict[str, Any]:
        """
        Use system AI to check for new debt ceiling legislation.

        Returns dict with:
        - new_legislation_found: bool
        - date: str (if found)
        - amount_trillion: float (if found)
        - legislation: str (if found)
        - summary: str
        """
        prompt = f"""You are a financial analyst assistant. Check if there has been any new US debt ceiling legislation passed after {latest_date or '2025-01-01'}.

The last recorded debt ceiling in our database is:
- Date: {latest_date or 'Unknown'}
- Amount: ${latest_ceiling}T (trillion dollars)

Based on your knowledge, has Congress passed any new debt ceiling legislation after this date?

Respond in JSON format only:
{{
    "new_legislation_found": true/false,
    "date": "YYYY-MM-DD" or null,
    "amount_trillion": number or null,
    "suspended": true/false,
    "suspension_end": "YYYY-MM-DD" or null,
    "legislation": "Name of the act/bill" or null,
    "political_context": "Brief context" or null,
    "source_url": "congress.gov URL" or null,
    "summary": "Brief explanation of findings"
}}"""

        try:
            # Use the same AI provider as coin review
            provider = await get_ai_review_provider_from_db()
            logger.info(f"Debt ceiling check using AI provider: {provider}")

            ai_callers = {
                "claude": _call_claude,
                "openai": _call_openai,
                "gemini": _call_gemini,
                "grok": _call_grok,
            }

            caller = ai_callers.get(provider)
            if not caller:
                logger.warning(f"Unknown AI provider: {provider}")
                return {"new_legislation_found": False, "summary": f"Unknown provider: {provider}"}

            response_text = await caller(prompt)

            # Parse JSON from response
            response_text = response_text.strip()
            # Remove markdown if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            # Find JSON in the response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(response_text[start:end])
                return result

            logger.warning(f"Failed to parse AI response as JSON: {response_text[:200]}")

        except ValueError as e:
            # Missing API key
            logger.warning(f"AI configuration error: {e}")
            return {"new_legislation_found": False, "summary": str(e)}
        except Exception as e:
            logger.error(f"Error calling AI API: {e}")

        return {"new_legislation_found": False, "summary": "Failed to check with AI"}

    @property
    def status(self) -> dict:
        """Get current status of the monitor service."""
        return {
            "running": self._running,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "last_result": self._last_result,
            "check_interval_days": CHECK_INTERVAL // (24 * 60 * 60),
            "current_ceiling_trillion": DEBT_CEILING_HISTORY[0].get("amount_trillion") if DEBT_CEILING_HISTORY else None,
        }


# Global instance
debt_ceiling_monitor = DebtCeilingMonitor()
