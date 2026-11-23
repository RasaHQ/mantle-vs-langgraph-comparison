"""Streaming TTS clients for Deepgram Aura and Cartesia Sonic.

Both return 16 kHz linear PCM, the format the ``json_audio`` channel sends.
Usage is counted where Rasa counts it: characters per text request sent and
seconds per audio chunk returned.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from collections.abc import AsyncIterator
from typing import Optional, Protocol
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect

from langgraph_native.voice.speech_config import (
    CARTESIA_TTS,
    SAMPLE_RATE,
    SpeechConfig,
    pcm_seconds,
)
from langgraph_native.voice_usage import VoiceUsageStore


class TTSError(Exception):
    """Raised when the TTS vendor reports an error."""


class TextToSpeech(Protocol):
    async def synthesize(self, text: str) -> AsyncIterator[bytes]: ...

    async def reset(self) -> None: ...


class _Metered:
    def __init__(
        self,
        usage: VoiceUsageStore,
        conversation_id: str,
        vendor: str,
        model: str,
        voice: Optional[str],
    ) -> None:
        self._usage = usage
        self._conversation_id = conversation_id
        self._vendor = vendor
        self._model = model
        self._voice = voice

    def _count_text(self, text: str) -> None:
        self._usage.record_tts_text(
            self._conversation_id, self._vendor, self._model, self._voice, len(text)
        )

    def _count_audio(self, audio: bytes) -> None:
        self._usage.record_tts_audio(
            self._conversation_id,
            self._vendor,
            self._model,
            self._voice,
            pcm_seconds(audio),
        )


class DeepgramAuraTTS(_Metered):
    """Deepgram ``/v1/speak`` websocket, one connection reused per call."""

    def __init__(
        self, config: SpeechConfig, usage: VoiceUsageStore, conversation_id: str
    ) -> None:
        super().__init__(
            usage, conversation_id, "deepgram", config.deepgram_tts_model, None
        )
        self._config = config
        self._socket: Optional[ClientConnection] = None

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        socket = await self._connected()
        await socket.send(json.dumps({"type": "Speak", "text": text}))
        self._count_text(text)
        await socket.send(json.dumps({"type": "Flush"}))
        async for raw in socket:
            if isinstance(raw, bytes):
                self._count_audio(raw)
                yield raw
                continue
            message = json.loads(raw)
            if message.get("type") in ("Flushed", "Cleared", "Close"):
                return
            if message.get("type") == "Error":
                raise TTSError(str(message.get("description") or message))

    async def reset(self) -> None:
        """Drops the connection so no audio from an interrupted reply leaks."""
        if self._socket is not None:
            await self._socket.close()
            self._socket = None

    async def _connected(self) -> ClientConnection:
        if self._socket is None:
            query = urlencode(
                {
                    "model": self._config.deepgram_tts_model,
                    "encoding": "linear16",
                    "sample_rate": SAMPLE_RATE,
                }
            )
            self._socket = await connect(
                f"{self._config.deepgram_tts_endpoint}?{query}",
                additional_headers={
                    "Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"
                },
            )
        return self._socket


class CartesiaTTS(_Metered):
    """Cartesia TTS websocket; one context per utterance."""

    def __init__(
        self, config: SpeechConfig, usage: VoiceUsageStore, conversation_id: str
    ) -> None:
        super().__init__(
            usage,
            conversation_id,
            "cartesia",
            config.cartesia_model,
            config.cartesia_voice,
        )
        self._config = config
        self._socket: Optional[ClientConnection] = None

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        socket = await self._connected()
        context_id = uuid.uuid4().hex
        await socket.send(
            json.dumps(
                {
                    "model_id": self._config.cartesia_model,
                    "transcript": text,
                    "voice": {"mode": "id", "id": self._config.cartesia_voice},
                    "language": self._config.cartesia_language,
                    "output_format": {
                        "container": "raw",
                        "encoding": "pcm_s16le",
                        "sample_rate": SAMPLE_RATE,
                    },
                    "context_id": context_id,
                    "continue": False,
                }
            )
        )
        self._count_text(text)
        async for raw in socket:
            message = json.loads(raw)
            if message.get("context_id") not in (None, context_id):
                continue
            kind = message.get("type")
            if kind == "chunk" and message.get("data"):
                audio = base64.b64decode(message["data"])
                self._count_audio(audio)
                yield audio
            elif kind == "done":
                return
            elif kind == "error":
                raise TTSError(str(message.get("error") or message))

    async def reset(self) -> None:
        if self._socket is not None:
            await self._socket.close()
            self._socket = None

    async def _connected(self) -> ClientConnection:
        if self._socket is None:
            self._socket = await connect(
                self._config.cartesia_endpoint,
                additional_headers={
                    "Cartesia-Version": self._config.cartesia_version,
                    "X-API-Key": os.environ["CARTESIA_API_KEY"],
                },
            )
        return self._socket


def make_tts(
    config: SpeechConfig, usage: VoiceUsageStore, conversation_id: str
) -> TextToSpeech:
    """Returns the configured TTS client for one call."""
    if config.tts_vendor == CARTESIA_TTS:
        return CartesiaTTS(config, usage, conversation_id)
    return DeepgramAuraTTS(config, usage, conversation_id)
