"""Deepgram Flux streaming ASR over the ``/v2/listen`` websocket.

Mirrors Rasa's ``deepgram_flux`` engine: linear16 at 16 kHz, turn events from
``TurnInfo`` messages, and every audio chunk sent counted as ASR seconds.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Optional
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from langgraph_native.voice.speech_config import (
    SAMPLE_RATE,
    SpeechConfig,
    pcm_seconds,
)
from langgraph_native.voice_usage import VoiceUsageStore

logger = logging.getLogger(__name__)

VENDOR = "deepgram_flux"

OnSpeechStart = Callable[[], Awaitable[None]]
OnTranscript = Callable[[str], Awaitable[None]]


class DeepgramFluxASR:
    """One streaming recognition session for one call."""

    def __init__(
        self,
        config: SpeechConfig,
        usage: VoiceUsageStore,
        conversation_id: str,
        on_speech_start: OnSpeechStart,
        on_transcript: OnTranscript,
    ) -> None:
        self._config = config
        self._usage = usage
        self._conversation_id = conversation_id
        self._on_speech_start = on_speech_start
        self._on_transcript = on_transcript
        self._socket: Optional[ClientConnection] = None
        self._reader: Optional[asyncio.Task[None]] = None

    async def connect(self) -> None:
        """Opens the Deepgram websocket and starts reading turn events."""
        query = urlencode(
            {
                "encoding": "linear16",
                "sample_rate": SAMPLE_RATE,
                "model": self._config.asr_model,
            }
        )
        url = f"wss://{self._config.asr_endpoint}/v2/listen?{query}"
        headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}
        self._socket = await connect(url, additional_headers=headers)
        self._reader = asyncio.create_task(self._read())

    async def send_audio(self, audio: bytes) -> None:
        """Streams one inbound PCM chunk and counts its duration."""
        if self._socket is None or not audio:
            return
        try:
            await self._socket.send(audio)
        except ConnectionClosed:
            logger.warning("Deepgram ASR socket closed while sending audio")
            return
        self._usage.record_asr_audio(
            self._conversation_id, VENDOR, self._config.asr_model, pcm_seconds(audio)
        )

    async def close(self) -> None:
        """Ends the stream and closes the socket."""
        if self._socket is not None:
            try:
                await self._socket.send(json.dumps({"type": "CloseStream"}))
                await self._socket.close()
            except ConnectionClosed:
                pass
        if self._reader is not None:
            self._reader.cancel()

    async def _read(self) -> None:
        socket = self._socket
        if socket is None:
            return
        try:
            async for raw in socket:
                if isinstance(raw, bytes):
                    continue
                message = json.loads(raw)
                if message.get("type") == "Error":
                    logger.error("Deepgram ASR error code=%s", message.get("code"))
                    continue
                if message.get("type") != "TurnInfo":
                    continue
                event = message.get("event")
                if event == "StartOfTurn":
                    await self._on_speech_start()
                elif event == "EndOfTurn":
                    transcript = (message.get("transcript") or "").strip()
                    if transcript:
                        await self._on_transcript(transcript)
        except ConnectionClosed:
            logger.info("Deepgram ASR socket closed")
