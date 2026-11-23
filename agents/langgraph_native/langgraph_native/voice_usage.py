"""ASR and TTS usage per conversation, reported in Rasa's ``/voice_usage`` shape.

Counts only; the benchmark harness prices them from its speech price table.
The counting points match Rasa's: every inbound audio chunk streamed to ASR,
every text request sent to TTS, and every audio chunk TTS returns.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel


class _AsrTotals(BaseModel):
    audio_seconds: float = 0.0


class _TtsTotals(BaseModel):
    voice: Optional[str] = None
    characters: int = 0
    audio_seconds: float = 0.0
    requests: int = 0
    cache_hit_characters: int = 0


class _Session(BaseModel):
    asr: dict[tuple[str, str], _AsrTotals] = {}
    tts: dict[tuple[str, str], _TtsTotals] = {}


class VoiceUsageStore:
    """Thread-safe speech usage keyed by conversation id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, _Session] = defaultdict(_Session)

    def record_asr_audio(
        self, conversation_id: str, vendor: str, model: str, seconds: float
    ) -> None:
        """Adds seconds of audio streamed to one ASR vendor and model."""
        if seconds <= 0:
            return
        with self._lock:
            session = self._sessions[conversation_id]
            totals = session.asr.setdefault((vendor, model), _AsrTotals())
            totals.audio_seconds += seconds

    def record_tts_text(
        self,
        conversation_id: str,
        vendor: str,
        model: str,
        voice: Optional[str],
        characters: int,
    ) -> None:
        """Adds characters sent to one TTS vendor and counts one request."""
        if characters <= 0:
            return
        with self._lock:
            totals = self._tts(conversation_id, vendor, model, voice)
            totals.characters += characters
            totals.requests += 1

    def record_tts_audio(
        self,
        conversation_id: str,
        vendor: str,
        model: str,
        voice: Optional[str],
        seconds: float,
    ) -> None:
        """Adds seconds of audio one TTS vendor returned."""
        if seconds <= 0:
            return
        with self._lock:
            self._tts(conversation_id, vendor, model, voice).audio_seconds += seconds

    def payload(self, conversation_id: str) -> dict[str, Any]:
        """Returns the conversation's usage as Rasa's ``/voice_usage`` body."""
        fetched_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            session = self._sessions.get(conversation_id)
            if session is None or (not session.asr and not session.tts):
                return {
                    "status": "not_found",
                    "session_id": conversation_id,
                    "asr": [],
                    "tts": [],
                    "fetched_at": fetched_at,
                }
            return {
                "status": "complete",
                "session_id": conversation_id,
                "asr": [
                    {
                        "vendor": vendor,
                        "model": model,
                        "audio_seconds": round(totals.audio_seconds, 4),
                    }
                    for (vendor, model), totals in session.asr.items()
                ],
                "tts": [
                    {
                        "vendor": vendor,
                        "model": model,
                        "voice": totals.voice,
                        "characters": totals.characters,
                        "audio_seconds": round(totals.audio_seconds, 4),
                        "requests": totals.requests,
                        "cache_hit_characters": totals.cache_hit_characters,
                    }
                    for (vendor, model), totals in session.tts.items()
                ],
                "fetched_at": fetched_at,
            }

    def _tts(
        self, conversation_id: str, vendor: str, model: str, voice: Optional[str]
    ) -> _TtsTotals:
        totals = self._sessions[conversation_id].tts.setdefault(
            (vendor, model), _TtsTotals()
        )
        if totals.voice is None and voice:
            totals.voice = voice
        return totals
