"""Speech vendor settings, defaulting to what the Mantle agent runs with.

ASR is Deepgram Flux on the EU endpoint, as in the Mantle agent's
``integrations.yml``. TTS defaults to Deepgram Aura (the vendor local Mantle
benchmark runs use); set ``LANGGRAPH_TTS_VENDOR=cartesia`` to use Cartesia
with Rasa's default Sonic model and voice. Both agents must use the same TTS
vendor for the comparison to hold.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict

SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2

DEEPGRAM_TTS = "deepgram"
CARTESIA_TTS = "cartesia"


class SpeechConfig(BaseModel):
    """Vendor endpoints, models, and voices for one call."""

    model_config = ConfigDict(frozen=True)

    asr_endpoint: str = "api.eu.deepgram.com"
    asr_model: str = "flux-general-en"
    tts_vendor: str = DEEPGRAM_TTS
    deepgram_tts_endpoint: str = "wss://api.eu.deepgram.com/v1/speak"
    deepgram_tts_model: str = "aura-2-thalia-en"
    cartesia_endpoint: str = "wss://api.cartesia.ai/tts/websocket"
    cartesia_model: str = "sonic-3.6"
    cartesia_version: str = "2026-03-01"
    cartesia_voice: str = "f786b574-daa5-4673-aa0c-cbe3e8534c02"
    cartesia_language: str = "en"

    @classmethod
    def from_env(cls) -> "SpeechConfig":
        """Returns the defaults with ``LANGGRAPH_*`` environment overrides."""
        overrides = {
            "asr_endpoint": os.environ.get("LANGGRAPH_ASR_ENDPOINT"),
            "tts_vendor": os.environ.get("LANGGRAPH_TTS_VENDOR"),
            "deepgram_tts_model": os.environ.get("LANGGRAPH_DEEPGRAM_TTS_MODEL"),
            "cartesia_voice": os.environ.get("LANGGRAPH_CARTESIA_VOICE"),
        }
        return cls(**{key: value for key, value in overrides.items() if value})


def pcm_seconds(audio: bytes) -> float:
    """Returns the duration of 16-bit mono PCM at :data:`SAMPLE_RATE`."""
    return len(audio) / BYTES_PER_SECOND
