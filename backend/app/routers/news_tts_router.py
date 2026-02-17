"""
News TTS Router

Text-to-speech endpoints with word-level timing for synchronized highlighting.
Uses edge-tts (Microsoft Edge Neural Voices) for high-quality speech synthesis.

TTS audio is persisted to disk (tts_cache/{article_id}/{voice_id}.mp3) and
shared across users. Word timings stored in DB as JSON.
"""

import asyncio
import base64
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import edge_tts
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker, get_db
from app.models import (
    ArticleTTS, User, UserArticleTTSHistory, UserVoiceSubscription,
)
from app.routers.auth_dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["news-tts"])

# TTS cache directory (relative to backend/)
TTS_CACHE_DIR = Path(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
) / "tts_cache"

# =============================================================================
# TTS Concurrency Control
# =============================================================================

_tts_semaphore = asyncio.Semaphore(3)
_tts_user_semaphores: Dict[int, asyncio.Semaphore] = {}


def _get_user_tts_semaphore(user_id: int) -> asyncio.Semaphore:
    """Get or create a per-user TTS semaphore (limit 1 per user)."""
    if user_id not in _tts_user_semaphores:
        _tts_user_semaphores[user_id] = asyncio.Semaphore(1)
    return _tts_user_semaphores[user_id]


# =============================================================================
# TTS Voice Configuration
# =============================================================================

TTS_VOICES = {
    # US voices
    "aria": "en-US-AriaNeural",
    "guy": "en-US-GuyNeural",
    "jenny": "en-US-JennyNeural",
    "brian": "en-US-BrianNeural",
    "emma": "en-US-EmmaNeural",
    "andrew": "en-US-AndrewNeural",
    "ava": "en-US-AvaNeural",
    "ana": "en-US-AnaNeural",
    "christopher": "en-US-ChristopherNeural",
    "eric": "en-US-EricNeural",
    "michelle": "en-US-MichelleNeural",
    "roger": "en-US-RogerNeural",
    "steffan": "en-US-SteffanNeural",
    # British voices
    "libby": "en-GB-LibbyNeural",
    "sonia": "en-GB-SoniaNeural",
    "ryan": "en-GB-RyanNeural",
    "thomas": "en-GB-ThomasNeural",
    "maisie": "en-GB-MaisieNeural",
    # Australian voices
    "natasha": "en-AU-NatashaNeural",
    "william": "en-AU-WilliamNeural",
    # Canadian voices
    "clara": "en-CA-ClaraNeural",
    "liam": "en-CA-LiamNeural",
    # Irish voices
    "connor": "en-IE-ConnorNeural",
    "emily": "en-IE-EmilyNeural",
    # Indian English voices
    "neerja": "en-IN-NeerjaNeural",
    "prabhat": "en-IN-PrabhatNeural",
    # New Zealand voices
    "mitchell": "en-NZ-MitchellNeural",
    "molly": "en-NZ-MollyNeural",
    # South African voices
    "leah": "en-ZA-LeahNeural",
    "luke": "en-ZA-LukeNeural",
    # Singapore voices
    "luna": "en-SG-LunaNeural",
    "wayne": "en-SG-WayneNeural",
    # Hong Kong voices
    "sam": "en-HK-SamNeural",
    "yan": "en-HK-YanNeural",
    # Kenya voices
    "asilia": "en-KE-AsiliaNeural",
    "chilemba": "en-KE-ChilembaNeural",
    # Nigeria voices
    "abeo": "en-NG-AbeoNeural",
    "ezinne": "en-NG-EzinneNeural",
    # Philippines voices
    "james": "en-PH-JamesNeural",
    "rosa": "en-PH-RosaNeural",
    # Tanzania voices
    "elimu": "en-TZ-ElimuNeural",
    "imani": "en-TZ-ImaniNeural",
}

DEFAULT_VOICE = "aria"


# =============================================================================
# Request Models
# =============================================================================

class TTSSyncRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=15000)
    voice: str = Field(default="aria")
    rate: str = Field(default="+0%")
    article_id: Optional[int] = Field(
        None, description="Article ID for TTS caching",
    )


class VoiceSubscriptionUpdate(BaseModel):
    voices: Dict[str, bool] = Field(
        ..., description="Map of voice_id -> is_enabled",
    )


# =============================================================================
# Helper Functions
# =============================================================================

async def _generate_tts(
    text: str, voice_name: str, rate: str
) -> tuple:
    """Generate TTS audio and word boundaries. Returns (audio_bytes, words)."""
    communicate = edge_tts.Communicate(
        text, voice_name, rate=rate, boundary="WordBoundary"
    )

    audio_chunks = []
    word_boundaries = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            offset_sec = chunk["offset"] / 10_000_000
            duration_sec = chunk["duration"] / 10_000_000
            word_boundaries.append({
                "text": chunk["text"],
                "startTime": round(offset_sec, 3),
                "endTime": round(offset_sec + duration_sec, 3),
            })

    return b"".join(audio_chunks), word_boundaries


async def _get_or_create_tts(
    article_id: int,
    voice: str,
    text: str,
    rate: str,
    user_id: int,
) -> tuple:
    """Get cached TTS or generate new one. Returns (audio_bytes, words)."""
    voice_name = TTS_VOICES.get(voice.lower(), TTS_VOICES[DEFAULT_VOICE])

    # Check DB cache
    async with async_session_maker() as db:
        result = await db.execute(
            select(ArticleTTS).where(
                ArticleTTS.article_id == article_id,
                ArticleTTS.voice_id == voice,
            )
        )
        cached = result.scalars().first()

    if cached:
        cache_path = TTS_CACHE_DIR / cached.audio_path
        if cache_path.exists():
            audio_data = cache_path.read_bytes()
            words = json.loads(cached.word_timings) if cached.word_timings else []
            return audio_data, words
        # File missing — regenerate below

    # Generate new TTS
    audio_data, words = await _generate_tts(text, voice_name, rate)

    # Save to filesystem
    article_dir = TTS_CACHE_DIR / str(article_id)
    article_dir.mkdir(parents=True, exist_ok=True)
    audio_path = f"{article_id}/{voice}.mp3"
    (TTS_CACHE_DIR / audio_path).write_bytes(audio_data)

    # Save to DB
    async with async_session_maker() as db:
        # Upsert: delete old record if exists (file was missing)
        if cached:
            await db.execute(
                delete(ArticleTTS).where(
                    ArticleTTS.article_id == article_id,
                    ArticleTTS.voice_id == voice,
                )
            )
            await db.flush()

        tts_record = ArticleTTS(
            article_id=article_id,
            voice_id=voice,
            audio_path=audio_path,
            word_timings=json.dumps(words),
            file_size_bytes=len(audio_data),
            created_by_user_id=user_id,
        )
        try:
            db.add(tts_record)
            await db.commit()
        except IntegrityError:
            await db.rollback()
            # R1: Another request won the race — audio file already written

    return audio_data, words


async def _update_tts_history(
    user_id: int, article_id: int, voice_id: str
):
    """Record the user's last-used voice for an article."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(UserArticleTTSHistory).where(
                UserArticleTTSHistory.user_id == user_id,
                UserArticleTTSHistory.article_id == article_id,
            )
        )
        history = result.scalars().first()

        if history:
            history.last_voice_id = voice_id
            history.last_played_at = datetime.now(timezone.utc)
        else:
            history = UserArticleTTSHistory(
                user_id=user_id,
                article_id=article_id,
                last_voice_id=voice_id,
            )
            db.add(history)

        await db.commit()


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/tts/voices")
async def get_tts_voices(current_user: User = Depends(get_current_user)):
    """Get available TTS voices."""
    return {
        "voices": [
            {
                "id": "aria", "name": "Aria",
                "gender": "Female", "style": "News", "desc": "Clear",
            },
            {
                "id": "guy", "name": "Guy",
                "gender": "Male", "style": "News",
                "desc": "Authoritative",
            },
            {
                "id": "jenny", "name": "Jenny",
                "gender": "Female", "style": "General",
                "desc": "Friendly",
            },
            {
                "id": "brian", "name": "Brian",
                "gender": "Male", "style": "Casual",
                "desc": "Approachable",
            },
            {
                "id": "emma", "name": "Emma",
                "gender": "Female", "style": "Casual",
                "desc": "Cheerful",
            },
            {
                "id": "andrew", "name": "Andrew",
                "gender": "Male", "style": "Casual", "desc": "Warm",
            },
        ],
        "default": DEFAULT_VOICE,
    }


@router.post("/tts-sync")
async def text_to_speech_with_sync(
    body: TTSSyncRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Convert text to speech with word-level timing.

    If article_id is provided, caches the result for sharing across users.
    Returns JSON with audio (base64 MP3) and words (timing array).
    """
    text = body.text
    voice = body.voice.lower()
    rate = body.rate

    # S1: Validate voice against known voices to prevent path traversal
    if voice not in TTS_VOICES:
        raise HTTPException(status_code=400, detail="Unknown voice")

    voice_name = TTS_VOICES[voice]

    # R2: Strict rate validation — must be +/-NNN%
    if not re.match(r'^[+-]\d{1,3}%$', rate):
        rate = "+0%"

    user_semaphore = _get_user_tts_semaphore(current_user.id)

    try:
        async with asyncio.timeout(60):
            async with user_semaphore:
                async with _tts_semaphore:
                    if body.article_id:
                        audio_data, words = await _get_or_create_tts(
                            body.article_id, voice, text, rate,
                            current_user.id,
                        )
                        # Record history
                        await _update_tts_history(
                            current_user.id, body.article_id, voice,
                        )
                    else:
                        audio_data, words = await _generate_tts(
                            text, voice_name, rate,
                        )

                    audio_base64 = base64.b64encode(
                        audio_data
                    ).decode("utf-8")

                    return {
                        "audio": audio_base64,
                        "words": words,
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
        raise HTTPException(
            status_code=500, detail="TTS generation failed"
        )


@router.get("/tts/article/{article_id}/voices")
async def get_cached_voices_for_article(
    article_id: int,
    current_user: User = Depends(get_current_user),
):
    """List voice_ids that have cached TTS for an article."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(ArticleTTS.voice_id).where(
                ArticleTTS.article_id == article_id
            )
        )
        voices = [row[0] for row in result.all()]
    return {"article_id": article_id, "cached_voices": voices}


@router.get("/tts/history/{article_id}")
async def get_tts_history_for_article(
    article_id: int,
    current_user: User = Depends(get_current_user),
):
    """Get user's last-used voice for an article."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(UserArticleTTSHistory).where(
                UserArticleTTSHistory.user_id == current_user.id,
                UserArticleTTSHistory.article_id == article_id,
            )
        )
        history = result.scalars().first()

    if history:
        return {
            "article_id": article_id,
            "last_voice_id": history.last_voice_id,
            "last_played_at": history.last_played_at.isoformat() + "Z",
        }
    return {"article_id": article_id, "last_voice_id": None}


@router.get("/tts/audio/{article_id}/{voice_id}")
async def serve_tts_audio(
    article_id: int,
    voice_id: str,
    current_user: User = Depends(get_current_user),
):
    """Serve cached TTS MP3 file directly."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(ArticleTTS).where(
                ArticleTTS.article_id == article_id,
                ArticleTTS.voice_id == voice_id,
            )
        )
        cached = result.scalars().first()

    if not cached:
        raise HTTPException(status_code=404, detail="TTS not found")

    filepath = TTS_CACHE_DIR / cached.audio_path
    # S2: Ensure resolved path stays within TTS cache directory
    if not filepath.resolve().is_relative_to(TTS_CACHE_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid audio path")
    if not filepath.exists():
        raise HTTPException(
            status_code=404, detail="TTS file missing"
        )

    return FileResponse(
        filepath,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/tts/voice-subscriptions")
async def get_voice_subscriptions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's voice subscription preferences."""
    result = await db.execute(
        select(UserVoiceSubscription).where(
            UserVoiceSubscription.user_id == current_user.id
        )
    )
    subs = result.scalars().all()
    return {
        "voices": {s.voice_id: s.is_enabled for s in subs},
    }


@router.put("/tts/voice-subscriptions")
async def update_voice_subscriptions(
    body: VoiceSubscriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch update user's voice subscription preferences."""
    for voice_id, is_enabled in body.voices.items():
        if voice_id not in TTS_VOICES:
            continue

        result = await db.execute(
            select(UserVoiceSubscription).where(
                UserVoiceSubscription.user_id == current_user.id,
                UserVoiceSubscription.voice_id == voice_id,
            )
        )
        sub = result.scalars().first()

        if sub:
            sub.is_enabled = is_enabled
        else:
            sub = UserVoiceSubscription(
                user_id=current_user.id,
                voice_id=voice_id,
                is_enabled=is_enabled,
            )
            db.add(sub)

    await db.commit()
    return {"message": "Voice preferences updated"}


# =============================================================================
# TTS Cleanup (called when articles are deleted)
# =============================================================================

async def cleanup_tts_for_articles(article_ids: List[int]):
    """Remove TTS cache files and DB records for deleted articles."""
    if not article_ids:
        return

    async with async_session_maker() as db:
        from sqlalchemy import delete
        await db.execute(
            delete(ArticleTTS).where(
                ArticleTTS.article_id.in_(article_ids)
            )
        )
        await db.execute(
            delete(UserArticleTTSHistory).where(
                UserArticleTTSHistory.article_id.in_(article_ids)
            )
        )
        await db.commit()

    # Remove cache directories
    for aid in article_ids:
        cache_dir = TTS_CACHE_DIR / str(aid)
        if cache_dir.exists():
            try:
                shutil.rmtree(cache_dir)
            except OSError as e:
                logger.warning(f"Failed to remove TTS cache for article {aid}: {e}")
