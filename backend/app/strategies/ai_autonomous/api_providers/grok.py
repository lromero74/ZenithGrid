"""
Grok API integration for AI autonomous trading strategy
"""

import json
import logging
import traceback
from typing import Any, Dict

from app.config import settings

logger = logging.getLogger(__name__)


async def get_grok_analysis(
    market_context: Dict[str, Any], build_prompt_func, total_tokens_tracker: Dict[str, int]
) -> Dict[str, Any]:
    """
    Call Grok API for market analysis (uses OpenAI-compatible API)

    Uses standardized prompt template shared across all AI providers

    Args:
        market_context: Market data context
        build_prompt_func: Function to build the prompt
        total_tokens_tracker: Dict with 'total' key to track token usage

    Returns:
        Analysis result dict with signal_type, confidence, reasoning, etc.
    """
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.error("openai library not installed. Run: pip install openai")
        return {
            "signal_type": "hold",
            "confidence": 0,
            "reasoning": "OpenAI library not installed",
            "suggested_allocation_pct": 0,
            "expected_profit_pct": 0,
        }

    api_key = settings.grok_api_key
    if not api_key:
        logger.error("GROK_API_KEY not set in .env file")
        return {
            "signal_type": "hold",
            "confidence": 0,
            "reasoning": "Grok API key not configured",
            "suggested_allocation_pct": 0,
            "expected_profit_pct": 0,
        }

    # Use shared prompt template
    prompt = build_prompt_func(market_context)

    try:
        client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")

        response = await client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,  # Deterministic responses (eliminates flip-flopping)
        )

        response_text = response.choices[0].message.content.strip()

        # Remove markdown if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        analysis = json.loads(response_text)

        # Track token usage
        if hasattr(response, "usage"):
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            total_tokens_tracker["total"] += input_tokens + output_tokens
            logger.info(f"📊 Grok API - Input: {input_tokens} tokens, Output: {output_tokens} tokens")

        signal_type = "none"
        if analysis["action"] == "buy":
            signal_type = "buy"
        elif analysis["action"] == "sell":
            signal_type = "sell"

        return {
            "signal_type": signal_type,
            "confidence": analysis.get("confidence", 50),
            "reasoning": analysis.get("reasoning", "AI analysis"),
            "suggested_allocation_pct": analysis.get("suggested_allocation_pct", 10),
            "expected_profit_pct": analysis.get("expected_profit_pct", 1.0),
        }

    except Exception as e:
        logger.error(f"Grok API error: {e}")
        return {
            "signal_type": "hold",
            "confidence": 0,
            "reasoning": f"Error: {str(e)[:100]}",
            "suggested_allocation_pct": 0,
            "expected_profit_pct": 0,
        }


async def get_grok_batch_analysis(
    pairs_data: Dict[str, Dict[str, Any]], build_batch_prompt_func, total_tokens_tracker: Dict[str, int]
) -> Dict[str, Dict[str, Any]]:
    """
    Analyze multiple pairs in a single Grok API call

    Uses standardized batch prompt template shared across all AI providers

    Args:
        pairs_data: Dict mapping product_id to market context data
        build_batch_prompt_func: Function to build the batch prompt
        total_tokens_tracker: Dict with 'total' key to track token usage

    Returns:
        Dict mapping product_id to analysis result
    """
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.error("openai library not installed")
        return {
            pid: {"signal_type": "hold", "confidence": 0, "reasoning": "OpenAI library not installed"}
            for pid in pairs_data.keys()
        }

    api_key = settings.grok_api_key
    if not api_key:
        logger.error("GROK_API_KEY not set")
        return {
            pid: {"signal_type": "hold", "confidence": 0, "reasoning": "API key not configured"}
            for pid in pairs_data.keys()
        }

    # Use shared batch prompt template
    prompt = build_batch_prompt_func(pairs_data)

    try:
        client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        response = await client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,  # Deterministic responses (eliminates flip-flopping)
        )

        response_text = response.choices[0].message.content.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        batch_analysis = json.loads(response_text)
        print(f"🔍 Grok batch_analysis keys: {list(batch_analysis.keys())}")

        if hasattr(response, "usage"):
            logger.info(
                f"📊 Grok BATCH - {len(pairs_data)} pairs - Input: {response.usage.prompt_tokens}, Output: {response.usage.completion_tokens}"
            )
            logger.info(f"   🎯 Efficiency: {len(pairs_data)} pairs in 1 call!")

        results = {}
        for product_id in pairs_data.keys():
            print(f"🔍 Checking if {product_id} in batch_analysis: {product_id in batch_analysis}")
            if product_id in batch_analysis:
                analysis = batch_analysis[product_id]
                signal_type = "none"
                if analysis.get("action") == "buy":
                    signal_type = "buy"
                elif analysis.get("action") == "sell":
                    signal_type = "sell"

                results[product_id] = {
                    "signal_type": signal_type,
                    "confidence": analysis.get("confidence", 50),
                    "reasoning": analysis.get("reasoning", "AI batch analysis"),
                    "suggested_allocation_pct": analysis.get("suggested_allocation_pct", 10),
                    "expected_profit_pct": analysis.get("expected_profit_pct", 1.0),
                }
            else:
                results[product_id] = {
                    "signal_type": "hold",
                    "confidence": 0,
                    "reasoning": "Not analyzed in batch response",
                }

        return results

    except Exception as e:
        print(f"🔍 Grok batch analysis EXCEPTION: {e}")
        logger.error(f"Grok batch analysis error: {e}")
        traceback.print_exc()
        return {
            pid: {"signal_type": "hold", "confidence": 0, "reasoning": f"Error: {str(e)[:100]}"}
            for pid in pairs_data.keys()
        }
