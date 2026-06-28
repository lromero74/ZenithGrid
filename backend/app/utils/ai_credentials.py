"""Single source of truth for mapping an AI provider name to its stored
credential name. Previously copy-pasted across the AI-team agents and the
ai_spot_opinion indicator (CLAUDE.md rule 14 — don't let dupes drift)."""

_CREDENTIAL_NAMES = {"claude": "claude", "gpt": "openai", "openai": "openai", "gemini": "gemini"}


def credential_name_for(ai_model: str) -> str:
    """Return the stored credential name for an AI provider (e.g. 'gpt' -> 'openai').

    Raises ValueError for an unknown/empty provider so a misconfigured model is
    surfaced loudly rather than silently using the wrong key.
    """
    key = (ai_model or "").lower()
    try:
        return _CREDENTIAL_NAMES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown AI model: {ai_model}") from exc
