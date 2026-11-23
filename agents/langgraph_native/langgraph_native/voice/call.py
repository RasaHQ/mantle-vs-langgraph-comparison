"""One ``json_audio`` voice call: inbound audio to ASR, turns, and TTS back out.

Speaks the protocol of Rasa's ``json_audio`` channel: inbound
``{"type": "audio", "audio": <b64 PCM>}`` and mark acknowledgements; outbound
audio, a ``mark`` after each utterance, and ``clear`` on barge-in. Utterances
are spoken as the graph streams them, so an acknowledgement plays while the
tools behind it run. A barge-in drops the audio still queued and records those
lines so the next turn does not treat them as heard.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from typing import Optional

from starlette.websockets import WebSocket, WebSocketDisconnect

from langgraph_native.service import AgentService
from langgraph_native.state import Incoming
from langgraph_native.voice.asr import DeepgramFluxASR
from langgraph_native.voice.speech_config import SpeechConfig
from langgraph_native.voice.tts import TTSError, make_tts

logger = logging.getLogger(__name__)

VOICE_CHANNEL = "voice"
_MESSAGE_KIND = "message"


class VoiceCall:
    """Bridges one websocket call to the agent service."""

    def __init__(
        self,
        websocket: WebSocket,
        service: AgentService,
        conversation_id: str,
        speech: SpeechConfig,
    ) -> None:
        self._websocket = websocket
        self._service = service
        self._conversation_id = conversation_id
        self._tts = make_tts(speech, service.voice_usage, conversation_id)
        self._asr = DeepgramFluxASR(
            speech,
            service.voice_usage,
            conversation_id,
            on_speech_start=self._on_speech_start,
            on_transcript=self._on_transcript,
        )
        self._transcripts: asyncio.Queue[Optional[Incoming]] = asyncio.Queue()
        self._utterances: asyncio.Queue[str] = asyncio.Queue()
        self._speaking: Optional[asyncio.Task[None]] = None
        self._current: Optional[str] = None
        self._send_lock = asyncio.Lock()

    async def run(self) -> None:
        """Serves the call until the client disconnects."""
        await self._asr.connect()
        turns = asyncio.create_task(self._run_turns())
        speaker = asyncio.create_task(self._run_speaker())
        if not await self._service.has_session(self._conversation_id):
            await self._transcripts.put(
                Incoming(kind="session_start", channel=VOICE_CHANNEL)
            )
        try:
            while True:
                message = json.loads(await self._websocket.receive_text())
                if message.get("type") == "audio" and message.get("audio"):
                    await self._asr.send_audio(base64.b64decode(message["audio"]))
        except WebSocketDisconnect:
            logger.info("Voice call ended")
        finally:
            await self._transcripts.put(None)
            turns.cancel()
            speaker.cancel()
            if self._speaking is not None:
                self._speaking.cancel()
            await self._asr.close()
            await self._tts.reset()

    async def _on_speech_start(self) -> None:
        if self._speaking is None or self._speaking.done():
            return
        missed: list[str] = []
        if self._current:
            missed.append(self._current)
        self._speaking.cancel()
        while not self._utterances.empty():
            missed.append(self._utterances.get_nowait())
        self._current = None
        await self._tts.reset()
        await self._send({"type": "clear"})
        if missed:
            self._service.note_unheard(self._conversation_id, missed)

    async def _on_transcript(self, transcript: str) -> None:
        await self._transcripts.put(
            Incoming(kind=_MESSAGE_KIND, text=transcript, channel=VOICE_CHANNEL)
        )

    async def _run_turns(self) -> None:
        while True:
            incoming = await self._transcripts.get()
            if incoming is None:
                return
            try:
                async for utterance in self._service.run_turn(
                    self._conversation_id, incoming
                ):
                    await self._utterances.put(utterance)
            except Exception as exc:
                logger.warning("Agent turn failed (%s)", type(exc).__name__)

    async def _run_speaker(self) -> None:
        while True:
            utterance = await self._utterances.get()
            self._current = utterance
            self._speaking = asyncio.create_task(self._speak(utterance))
            try:
                await self._speaking
            except asyncio.CancelledError:
                if not self._speaking.cancelled():
                    raise
            finally:
                self._current = None

    async def _speak(self, text: str) -> None:
        try:
            async for chunk in self._tts.synthesize(text):
                await self._send(
                    {"type": "audio", "audio": base64.b64encode(chunk).decode()}
                )
        except TTSError as exc:
            logger.warning("TTS failed (%s)", type(exc).__name__)
            await self._tts.reset()
            return
        await self._send({"type": "mark", "mark": {"name": uuid.uuid4().hex}})

    async def _send(self, message: dict) -> None:
        async with self._send_lock:
            try:
                await self._websocket.send_text(json.dumps(message))
            except (WebSocketDisconnect, RuntimeError):
                logger.info("Voice client gone; dropping outbound message")
