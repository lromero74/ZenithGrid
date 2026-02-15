"""
AI Service Module

Provides a unified interface for accessing AI clients (Anthropic, OpenAI, Google Gemini).
Used by grid trading and other AI-powered features.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

logger = logging.getLogger(__name__)


async def get_ai_client(provider: str = "anthropic", user_id: Optional[int] = None, db: Optional[AsyncSession] = None):
    """
    Get an AI client for the specified provider.

    Args:
        provider: AI provider name ("anthropic", "openai", or "gemini")
        user_id: Optional user ID to get user-specific API keys
        db: Optional database session for fetching user credentials

    Returns:
        AI client instance (AsyncAnthropic, AsyncOpenAI, or genai client)

    Raises:
        ValueError: If provider is invalid or credentials are missing
    """
    # Normalize provider name
    provider = provider.lower()

    # Get API key from user or fallback to system
    api_key = None
    if user_id and db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        # BUG: User model has no anthropic_api_key/openai_api_key/gemini_api_key attrs.
        # Credentials are stored in AIProviderCredential table. This code path
        # silently fails (AttributeError caught nowhere) and falls through to
        # system credentials. Needs refactoring to query AIProviderCredential.
        if user:
            if provider == "anthropic":
                api_key = user.anthropic_api_key
            elif provider == "openai":
                api_key = user.openai_api_key
            elif provider == "gemini":
                api_key = user.gemini_api_key

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
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")


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
