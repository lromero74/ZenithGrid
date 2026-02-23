"""
Shared filesystem path constants.

Centralizes paths that are referenced across multiple modules,
preventing cross-layer imports (e.g., router → router).
"""

import os
from pathlib import Path

# Root of the backend/ directory
BACKEND_DIR = Path(os.path.dirname(os.path.dirname(__file__)))

# TTS audio cache: backend/tts_cache/{article_id}/{voice_id}.mp3
TTS_CACHE_DIR = BACKEND_DIR / "tts_cache"
