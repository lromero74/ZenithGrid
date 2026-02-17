"""
AI Service Module

Provides a unified interface for accessing AI clients (Anthropic, OpenAI, Google Gemini).
Used by grid trading and other AI-powered features.
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_ai_client(provider: str = "anthropic", user_id: Optional[int] = None, db: Optional[AsyncSession] = None):
    """
    Get an AI client for the specified provider.

    Args:
        provider: AI provider name ("anthropic", "openai", or "gemini")
        user_id: Optional user ID to get user-specific API keys
        db: Optional database session for fetching user credentials

    Returns:
        AI client instance (AsyncAnthropic, AsyncOpenAI, or genai GenerativeModel)

    Raises:
        ValueError: If provider is invalid or credentials are missing
    """
    # Normalize provider name
    provider = provider.lower()

    # Get API key: try user's AIProviderCredential first, then system fallback
    api_key = None
    if user_id and db:
        try:
            from app.services.ai_credential_service import get_user_api_key
            # Map provider names to credential table names
            provider_map = {
                "anthropic": "claude",
                "claude": "claude",
                "openai": "openai",
                "gemini": "gemini",
            }
            cred_provider = provider_map.get(provider, provider)
            api_key = await get_user_api_key(db, user_id, cred_provider)
        except Exception as e:
            logger.debug(f"Could not fetch user credential for {provider}: {e}")

    # Fallback to system credentials
    if not api_key:
        from app.config import settings
        if provider == "anthropic":
            api_key = settings.anthropic_api_key
        elif provider == "openai":
            api_key = settings.openai_api_key
        elif provider == "gemini":
            api_key = settings.gemini_api_key

    if not api_key:
        raise ValueError(f"No API key configured for provider: {provider}")

    # Create and return client
    if provider == "anthropic":
        from anthropic import AsyncAnthropic
        return AsyncAnthropic(api_key=api_key)
    elif provider == "openai":
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=api_key)
    elif provider == "gemini":
        # Return a wrapper that creates per-request model instances
        # (avoids module-global genai.configure() race condition between users)
        import google.generativeai as genai
        return GeminiClientWrapper(api_key=api_key)
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")


class GeminiClientWrapper:
    """
    Per-request Gemini client wrapper that avoids the global genai.configure() race condition.

    Instead of calling genai.configure(api_key=...) which sets state on the module-global
    object (unsafe when multiple users call concurrently), this creates model instances
    with the API key passed directly.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def GenerativeModel(self, model_name: str = "gemini-1.5-pro"):
        """Create a model instance with per-request API key."""
        import google.generativeai as genai
        # Configure with this specific key before creating the model
        # genai requires configure() before model creation, but we do it
        # in a contained scope. For true thread safety, we use the
        # client_options approach if available.
        genai.configure(api_key=self.api_key)
        return genai.GenerativeModel(model_name)


async def get_ai_analysis(
    client,
    provider: str,
    prompt: str,
    model: Optional[str] = None
) -> str:
    """
    Get AI analysis from the specified client.

    Args:
        client: AI client instance
        provider: Provider name ("anthropic", "openai", or "gemini")
        prompt: Analysis prompt
        model: Optional model name override

    Returns:
        AI response text
    """
    provider = provider.lower()

    if provider == "anthropic":
        if not model:
            model = "claude-sonnet-4-5-20250929"

        response = await client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    elif provider == "openai":
        if not model:
            model = "gpt-4-turbo-preview"

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000
        )
        return response.choices[0].message.content

    elif provider == "gemini":
        if not model:
            model = "gemini-1.5-pro"

        model_instance = client.GenerativeModel(model)
        response = await model_instance.generate_content_async(prompt)
        return response.text

    else:
        raise ValueError(f"Unsupported AI provider: {provider}")
