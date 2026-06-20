"""Agent memory — DB-backed read/write of past agent outputs and market insights.

HARD RULE: every read and write is scoped to account_id. A query for account A
can never return rows belonging to account B.

Backed by the trading.ai_team_runs table (created by migration 092).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentMemory:
    """Persistent store for AI-team run outputs, strictly account-scoped."""

    async def save_run(
        self,
        *,
        db: Any,
        account_id: int,
        bot_id: Optional[int],
        product_id: str,
        signal_output: Dict[str, Any],
        bull_output: Dict[str, Any],
        bear_output: Dict[str, Any],
        verdict_output: Dict[str, Any],
        plan_output: Dict[str, Any],
        final_action: str,
    ) -> Optional[int]:
        """Persist a completed AI-team run. Returns the new row id or None on error.

        The account_id column is set on INSERT; all future reads are filtered by it.
        """
        from sqlalchemy import text

        try:
            result = await db.execute(
                text(
                    """
                    INSERT INTO ai_team_runs (
                        account_id, bot_id, product_id,
                        signal_output, bull_output, bear_output,
                        verdict_output, plan_output, final_action
                    ) VALUES (
                        :account_id, :bot_id, :product_id,
                        :signal_output, :bull_output, :bear_output,
                        :verdict_output, :plan_output, :final_action
                    )
                    """
                ),
                {
                    "account_id": account_id,
                    "bot_id": bot_id,
                    "product_id": product_id,
                    "signal_output": _json_dumps(signal_output),
                    "bull_output": _json_dumps(bull_output),
                    "bear_output": _json_dumps(bear_output),
                    "verdict_output": _json_dumps(verdict_output),
                    "plan_output": _json_dumps(plan_output),
                    "final_action": final_action,
                },
            )
            await db.commit()
            return result.lastrowid
        except Exception:
            logger.exception("AgentMemory.save_run failed for account_id=%d", account_id)
            return None

    async def recent_runs(
        self,
        *,
        db: Any,
        account_id: int,
        product_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return the most recent AI-team runs for this account (and optionally product).

        HARD RULE enforced: WHERE account_id = :account_id is always present.
        """
        import json as _json
        from sqlalchemy import text

        try:
            where_clauses = ["account_id = :account_id"]
            params: Dict[str, Any] = {"account_id": account_id, "limit": limit}
            if product_id:
                where_clauses.append("product_id = :product_id")
                params["product_id"] = product_id

            where_sql = " AND ".join(where_clauses)
            rows = await db.execute(
                text(
                    f"""
                    SELECT id, account_id, bot_id, product_id, final_action, created_at,
                           signal_output, bull_output, bear_output, verdict_output, plan_output
                    FROM ai_team_runs
                    WHERE {where_sql}
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            )
            results = []
            for row in rows.fetchall():
                results.append({
                    "id": row[0],
                    "account_id": row[1],
                    "bot_id": row[2],
                    "product_id": row[3],
                    "final_action": row[4],
                    "created_at": str(row[5]),
                    "signal": _safe_parse(_json, row[6]),
                    "bull": _safe_parse(_json, row[7]),
                    "bear": _safe_parse(_json, row[8]),
                    "verdict": _safe_parse(_json, row[9]),
                    "plan": _safe_parse(_json, row[10]),
                })
            return results
        except Exception:
            logger.exception("AgentMemory.recent_runs failed for account_id=%d", account_id)
            return []


def _json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, default=str)


def _safe_parse(json_mod: Any, value: Optional[str]) -> Any:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json_mod.loads(value)
    except Exception:
        return {}
