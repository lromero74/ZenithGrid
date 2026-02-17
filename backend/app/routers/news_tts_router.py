"""
News TTS Router

Text-to-speech endpoints with word-level timing for synchronized highlighting.
Uses edge-tts (Microsoft Edge Neural Voices) for high-quality speech synthesis.

Extracted from news_router.py for maintainability.
"""

import asyncio
import base64
import logging
from typing import Dict

import edge_tts
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.models import User
from app.routers.auth_dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["news-tts"])

# =============================================================================
# TTS Concurrency Control
# =============================================================================

# Global semaphore: max 3 concurrent TTS generations across all users
_tts_semaphore = asyncio.Semaphore(3)

# Per-user semaphores: max 1 concurrent TTS request per user
# Prevents one user from monopolizing all 3 global slots
_tts_user_semaphores: Dict[int, asyncio.Semaphore] = {}


def _get_user_tts_semaphore(user_id: int) -> asyncio.Semaphore:
    """Get or create a per-user TTS semaphore (limit 1 per user)."""
    if user_id not in _tts_user_semaphores:
        _tts_user_semaphores[user_id] = asyncio.Semaphore(1)
    return _tts_user_semaphores[user_id]


# =============================================================================
# TTS Voice Configuration
# =============================================================================

# Available voices for TTS (high-quality neural voices from all English locales)
TTS_VOICES = {
    # US voices
    "aria": "en-US-AriaNeural",        # Female - default
    "guy": "en-US-GuyNeural",          # Male
    "jenny": "en-US-JennyNeural",      # Female
    "brian": "en-US-BrianNeural",      # Male
    "emma": "en-US-EmmaNeural",        # Female
    "andrew": "en-US-AndrewNeural",    # Male
    "ava": "en-US-AvaNeural",          # Female, Expressive
    "ana": "en-US-AnaNeural",          # Female, Cute
    "christopher": "en-US-ChristopherNeural",  # Male, Reliable
    "eric": "en-US-EricNeural",        # Male, Rational
    "michelle": "en-US-MichelleNeural",  # Female, Friendly
    "roger": "en-US-RogerNeural",      # Male, Lively
    "steffan": "en-US-SteffanNeural",  # Male, Rational
    # British voices
    "libby": "en-GB-LibbyNeural",      # Female
    "sonia": "en-GB-SoniaNeural",      # Female
    "ryan": "en-GB-RyanNeural",        # Male
    "thomas": "en-GB-ThomasNeural",    # Male
    "maisie": "en-GB-MaisieNeural",    # Female (child)
    # Australian voices
    "natasha": "en-AU-NatashaNeural",  # Female
    "william": "en-AU-WilliamNeural",  # Male
    # Canadian voices
    "clara": "en-CA-ClaraNeural",      # Female
    "liam": "en-CA-LiamNeural",        # Male
    # Irish voices
    "connor": "en-IE-ConnorNeural",    # Male
    "emily": "en-IE-EmilyNeural",      # Female
    # Indian English voices
    "neerja": "en-IN-NeerjaNeural",    # Female
    "prabhat": "en-IN-PrabhatNeural",  # Male
    # New Zealand voices
    "mitchell": "en-NZ-MitchellNeural",  # Male
    "molly": "en-NZ-MollyNeural",      # Female
    # South African voices
    "leah": "en-ZA-LeahNeural",        # Female
    "luke": "en-ZA-LukeNeural",        # Male
    # Singapore voices
    "luna": "en-SG-LunaNeural",        # Female
    "wayne": "en-SG-WayneNeural",      # Male
    # Hong Kong voices
    "sam": "en-HK-SamNeural",          # Male
    "yan": "en-HK-YanNeural",          # Female
    # Kenya voices
    "asilia": "en-KE-AsiliaNeural",    # Female
    "chilemba": "en-KE-ChilembaNeural",  # Male
    # Nigeria voices
    "abeo": "en-NG-AbeoNeural",        # Male
    "ezinne": "en-NG-EzinneNeural",    # Female
    # Philippines voices
    "james": "en-PH-JamesNeural",      # Male
    "rosa": "en-PH-RosaNeural",        # Female
    # Tanzania voices
    "elimu": "en-TZ-ElimuNeural",      # Male
    "imani": "en-TZ-ImaniNeural",      # Female
}

DEFAULT_VOICE = "aria"


# =============================================================================
# Request Models
# =============================================================================

class TTSSyncRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=15000)
    voice: str = Field(default="aria")
    rate: str = Field(default="+0%")


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/tts/voices")
async def get_tts_voices(current_user: User = Depends(get_current_user)):
    """
    Get available TTS voices.

    Returns list of voice options with descriptions.
    """
    return {
        "voices": [
            {"id": "aria", "name": "Aria", "gender": "Female", "style": "News", "desc": "Clear"},
            {"id": "guy", "name": "Guy", "gender": "Male", "style": "News", "desc": "Authoritative"},
            {"id": "jenny", "name": "Jenny", "gender": "Female", "style": "General", "desc": "Friendly"},
            {"id": "brian", "name": "Brian", "gender": "Male", "style": "Casual", "desc": "Approachable"},
            {"id": "emma", "name": "Emma", "gender": "Female", "style": "Casual", "desc": "Cheerful"},
            {"id": "andrew", "name": "Andrew", "gender": "Male", "style": "Casual", "desc": "Warm"},
        ],
        "default": DEFAULT_VOICE,
    }


@router.post("/tts-sync")
async def text_to_speech_with_sync(
    body: TTSSyncRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Convert text to speech with word-level timing for synchronized highlighting.

    Returns JSON with:
    - audio: Base64-encoded MP3 audio
    - words: Array of {text, startTime, endTime} for each word (times in seconds)

    This enables karaoke-style word highlighting during playback.
    """
    text = body.text
    voice = body.voice
    rate = body.rate

    voice_name = TTS_VOICES.get(voice.lower(), TTS_VOICES[DEFAULT_VOICE])

    if not (rate.startswith("+") or rate.startswith("-")) or not rate.endswith("%"):
        rate = "+0%"

    user_semaphore = _get_user_tts_semaphore(current_user.id)

    try:
        async with asyncio.timeout(60):
            # Per-user semaphore first (prevents one user queueing multiple),
            # then global semaphore (limits total concurrency to 3)
            async with user_semaphore:
                async with _tts_semaphore:
                    communicate = edge_tts.Communicate(
                        text, voice_name, rate=rate, boundary="WordBoundary"
                    )

                    audio_chunks = []
                    word_boundaries = []

                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            audio_chunks.append(chunk["data"])
                        elif chunk["type"] == "WordBoundary":
                            # Convert 100-nanosecond units to seconds
                            offset_sec = chunk["offset"] / 10_000_000
                            duration_sec = chunk["duration"] / 10_000_000
                            word_boundaries.append({
                                "text": chunk["text"],
                                "startTime": round(offset_sec, 3),
                                "endTime": round(offset_sec + duration_sec, 3),
                            })

                    # Combine audio chunks and encode as base64
                    audio_data = b"".join(audio_chunks)
                    audio_base64 = base64.b64encode(audio_data).decode("utf-8")

                    return {
                        "audio": audio_base64,
                        "words": word_boundaries,
                        "voice": voice,
                        "rate": rate,
                    }

    except TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="TTS service busy, try again shortly",
            headers={"Retry-After": "5"},
        )
    except Exception as e:
        logger.error(f"TTS sync generation error: {e}")
        raise HTTPException(status_code=500, detail="TTS generation failed")
