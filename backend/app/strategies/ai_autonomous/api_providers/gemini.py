"""
Gemini API integration for AI autonomous trading strategy
"""

import json
import logging
import re
from typing import Any, Dict

from app.config import settings

logger = logging.getLogger(__name__)


async def get_gemini_analysis(
    market_context: Dict[str, Any],
    build_prompt_func,
    total_tokens_tracker: Dict[str, int]
) -> Dict[str, Any]:
    """
    Call Gemini API for market analysis

    Uses standardized prompt template shared across all AI providers

    Args:
        market_context: Market data context
        build_prompt_func: Function to build the prompt
        total_tokens_tracker: Dict with 'total' key to track token usage

    Returns:
        Analysis result dict with signal_type, confidence, reasoning, etc.
    """
    try:
        # Lazy import of Gemini library
        import google.generativeai as genai
    except ImportError:
        logger.error("google-generativeai not installed. Run: pip install google-generativeai")
        return {
            "signal_type": "hold",
            "confidence": 0,
            "reasoning": "Gemini library not installed",
            "suggested_allocation_pct": 0,
            "expected_profit_pct": 0
        }

    # Initialize Gemini client
    api_key = settings.gemini_api_key
    if not api_key:
        logger.error("GEMINI_API_KEY not set in .env file")
        return {
            "signal_type": "hold",
            "confidence": 0,
            "reasoning": "Gemini API key not configured",
            "suggested_allocation_pct": 0,
            "expected_profit_pct": 0
        }

    genai.configure(api_key=api_key)

    # Use shared prompt template
    prompt = build_prompt_func(market_context)

    try:
        model = genai.GenerativeModel(
            'gemini-2.5-flash',  # Latest Gemini 2.5 Flash
            generation_config={"temperature": 0}  # Deterministic responses
        )
        response = model.generate_content(prompt)

        # Parse response
        response_text = response.text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        analysis = json.loads(response_text)

        # Track token usage (Gemini provides usage metadata)
        if hasattr(response, 'usage_metadata'):
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count
            total_tokens_tracker['total'] += input_tokens + output_tokens
            logger.info(f"📊 Gemini API - Input: {input_tokens} tokens, Output: {output_tokens} tokens, Total: {total_tokens_tracker['total']}")

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
        logger.error(f"Failed to parse Gemini response as JSON: {response_text}")
        logger.error(f"JSON error: {e}")
        return {
            "signal_type": "hold",
            "confidence": 0,
            "reasoning": "Failed to parse AI response",
            "suggested_allocation_pct": 0,
            "expected_profit_pct": 0
        }
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}", exc_info=True)
        return {
            "signal_type": "hold",
            "confidence": 0,
            "reasoning": f"Error: {str(e)}",
            "suggested_allocation_pct": 0,
            "expected_profit_pct": 0
        }


async def get_gemini_batch_analysis(
    pairs_data: Dict[str, Dict[str, Any]],
    build_batch_prompt_func,
    total_tokens_tracker: Dict[str, int]
) -> Dict[str, Dict[str, Any]]:
    """
    Analyze multiple pairs in a single Gemini API call

    Uses standardized batch prompt template shared across all AI providers

    Args:
        pairs_data: Dict mapping product_id to market context data
        build_batch_prompt_func: Function to build the batch prompt
        total_tokens_tracker: Dict with 'total' key to track token usage

    Returns:
        Dict mapping product_id to analysis result
    """
    try:
        import google.generativeai as genai
    except ImportError:
        logger.error("google-generativeai not installed")
        return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "Gemini library not installed"}
                for pid in pairs_data.keys()}

    api_key = settings.gemini_api_key
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "API key not configured"}
                for pid in pairs_data.keys()}

    genai.configure(api_key=api_key)

    # Use shared batch prompt template
    prompt = build_batch_prompt_func(pairs_data)

    try:
        model = genai.GenerativeModel(
            'gemini-2.5-flash',
            generation_config={"temperature": 0}  # Deterministic responses
        )
        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Remove markdown if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        batch_analysis = json.loads(response_text)

        # Track token usage
        if hasattr(response, 'usage_metadata'):
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count
            total_tokens_tracker['total'] += input_tokens + output_tokens
            logger.info(f"📊 Gemini BATCH API - {len(pairs_data)} pairs - Input: {input_tokens} tokens, Output: {output_tokens} tokens")
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
        logger.error(f"Failed to parse Gemini batch response: {e}")
        return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "Failed to parse batch response"}
                for pid in pairs_data.keys()}
    except Exception as e:
        logger.error(f"Gemini batch analysis error: {e}")
        # Check for rate limit error with retry_delay
        error_str = str(e)
        if "retry_delay" in error_str or "429" in error_str:
            # Extract retry delay if present (Gemini includes this in error)
            match = re.search(r'retry_delay.*?seconds:\s*(\d+)', error_str)
            if match:
                retry_seconds = int(match.group(1))
                logger.warning(f"⏰ Gemini API quota exceeded - back off for {retry_seconds} seconds")
                # TODO: Store this in bot's last_check_time + retry_delay
            else:
                logger.warning("⏰ Gemini API quota exceeded (429) - backing off")

        return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": f"Error: {str(e)[:100]}"}
                for pid in pairs_data.keys()}
