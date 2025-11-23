"""
Claude API integration for AI autonomous trading strategy
"""

import json
import logging
from typing import Any, Dict

from app.config import settings

logger = logging.getLogger(__name__)


async def get_claude_analysis(
    client,
    market_context: Dict[str, Any],
    build_prompt_func,
    total_tokens_tracker: Dict[str, int]
) -> Dict[str, Any]:
    """
    Call Claude API for market analysis

    Uses standardized prompt template shared across all AI providers

    Args:
        client: Anthropic client instance
        market_context: Market data context
        build_prompt_func: Function to build the prompt
        total_tokens_tracker: Dict with 'total' key to track token usage

    Returns:
        Analysis result dict with signal_type, confidence, reasoning, etc.
    """
    # Use shared prompt template
    prompt = build_prompt_func(market_context)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",  # Claude Sonnet 4.5 (latest)
            max_tokens=1000,  # Allow for detailed reasoning
            temperature=0,  # Deterministic responses (eliminates flip-flopping)
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        # Track token usage
        total_tokens_tracker['total'] += response.usage.input_tokens + response.usage.output_tokens
        logger.info(f"📊 Claude API - Input: {response.usage.input_tokens} tokens, Output: {response.usage.output_tokens} tokens, Total: {total_tokens_tracker['total']}")

        # Parse response
        response_text = response.content[0].text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        analysis = json.loads(response_text)

        # Convert to our signal format
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
            "current_price": market_context['current_price'],  # Include current price for DCA logic
            "raw_analysis": analysis
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {response_text}")
        logger.error(f"JSON error: {e}")
        return {
            "signal_type": "hold",
            "confidence": 0,
            "reasoning": "Failed to parse AI response",
            "suggested_allocation_pct": 0,
            "expected_profit_pct": 0
        }
    except Exception as e:
        logger.error(f"Error calling Claude API: {e}", exc_info=True)
        return {
            "signal_type": "hold",
            "confidence": 0,
            "reasoning": f"Error: {str(e)}",
            "suggested_allocation_pct": 0,
            "expected_profit_pct": 0
        }


async def get_claude_batch_analysis(
    pairs_data: Dict[str, Dict[str, Any]],
    build_batch_prompt_func,
    total_tokens_tracker: Dict[str, int]
) -> Dict[str, Dict[str, Any]]:
    """
    Analyze multiple pairs in a single Claude API call

    Uses standardized batch prompt template shared across all AI providers

    Args:
        pairs_data: Dict mapping product_id to market context data
        build_batch_prompt_func: Function to build the batch prompt
        total_tokens_tracker: Dict with 'total' key to track token usage

    Returns:
        Dict mapping product_id to analysis result
    """
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        logger.error("anthropic library not installed")
        return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "Anthropic library not installed"}
                for pid in pairs_data.keys()}

    api_key = settings.anthropic_api_key
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set")
        return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "API key not configured"}
                for pid in pairs_data.keys()}

    # Use shared batch prompt template
    prompt = build_batch_prompt_func(pairs_data)

    try:
        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0,  # Deterministic responses (eliminates flip-flopping)
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Remove markdown if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        batch_analysis = json.loads(response_text)

        # Track token usage
        if hasattr(response, 'usage'):
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            total_tokens_tracker['total'] += input_tokens + output_tokens
            logger.info(f"📊 Claude BATCH API - {len(pairs_data)} pairs - Input: {input_tokens} tokens, Output: {output_tokens} tokens")
            logger.info(f"   🎯 Efficiency: {len(pairs_data)} pairs in 1 call (saved {len(pairs_data)-1} API calls!)")

        # Convert to our signal format for each pair
        results = {}
        for product_id in pairs_data.keys():
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
                    "expected_profit_pct": analysis.get("expected_profit_pct", 1.0)
                }
            else:
                # Pair missing from response
                results[product_id] = {
                    "signal_type": "hold",
                    "confidence": 0,
                    "reasoning": "Not analyzed in batch response"
                }

        return results

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude batch response: {e}")
        return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "Failed to parse batch response"}
                for pid in pairs_data.keys()}
    except Exception as e:
        logger.error(f"Claude batch analysis error: {e}")
        return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": f"Error: {str(e)[:100]}"}
                for pid in pairs_data.keys()}
