"""HTTP and websocket server exposing the Rasa routes the benchmark harness calls.

Routes: ``/status`` and ``/version`` (readiness), the REST text channel, the
``json_audio`` voice channel, tracker read and event append, the
``engine_tokens`` / ``voice_usage`` usage endpoints, and the ``/chat`` page.
"""

from __future__ import annotations

import argparse
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from langgraph_native.service import AgentService
from langgraph_native.state import Incoming
from langgraph_native.tracing import ENGINE
from langgraph_native.voice.call import VoiceCall
from langgraph_native.voice.speech_config import SpeechConfig

logger = logging.getLogger(__name__)

# The harness keys tracker and token handling on this id, same as Mantle.
ENGINE_VERSION = "mantle"
AGENT_VERSION = "langgraph-native"
SENDER_HEADER = "X-Rasa-Sender"
_SESSION_START_TEXT = "/session_start"
_REST_CHANNEL = "rest"
_VOICE_CHANNEL = "voice"
_CONVERSATION_ID = re.compile(r"^[\w.:@-]{1,128}$")
_PAGE = Path(__file__).resolve().parent / "web" / "index.html"
# The combined agent listens on 5006. This one stays off that port.
_DEFAULT_PORT = 5007


def create_app(service: AgentService | None = None) -> Starlette:
    """Returns the Starlette app; the agent service is built on startup if absent."""

    @asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.service = service or await AgentService.create()
        app.state.speech = SpeechConfig.from_env()
        yield

    return Starlette(
        routes=[
            Route("/", _root),
            Route("/chat", _chat_page),
            Route("/status", _status),
            Route("/version", _version),
            Route("/webhooks/rest/webhook", _rest_webhook, methods=["POST"]),
            Route("/webhooks/json_audio/", _json_audio_health),
            WebSocketRoute("/webhooks/json_audio/websocket", _json_audio_websocket),
            Route("/conversations/{conversation_id}/tracker", _tracker),
            Route(
                "/conversations/{conversation_id}/tracker/events",
                _append_events,
                methods=["POST"],
            ),
            Route("/conversations/{conversation_id}/engine_tokens", _engine_tokens),
            Route("/conversations/{conversation_id}/voice_usage", _voice_usage),
            Route("/conversations/{conversation_id}/turn", _turn),
        ],
        lifespan=lifespan,
    )


async def _root(request: Request) -> JSONResponse:
    return JSONResponse({"message": "LangGraph native agent"})


async def _chat_page(request: Request) -> FileResponse:
    return FileResponse(_PAGE)


async def _status(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "engine_version": ENGINE_VERSION,
            "model_file": AGENT_VERSION,
            "model_id": AGENT_VERSION,
            "num_active_training_jobs": 0,
        }
    )


async def _version(request: Request) -> JSONResponse:
    return JSONResponse({"version": AGENT_VERSION})


async def _rest_webhook(request: Request) -> JSONResponse:
    body = await request.json()
    sender = str(body.get("sender") or "")
    text = str(body.get("message") or "")
    if not _CONVERSATION_ID.match(sender):
        return JSONResponse({"error": "invalid sender"}, status_code=400)
    channel = _channel(body.get("channel"))
    service: AgentService = request.app.state.service
    if text.strip() == _SESSION_START_TEXT:
        incoming = Incoming(kind="session_start", channel=channel)
    else:
        incoming = Incoming(kind="message", text=text, channel=channel)
    replies = [utterance async for utterance in service.run_turn(sender, incoming)]
    return JSONResponse([{"recipient_id": sender, "text": text} for text in replies])


async def _json_audio_health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def _json_audio_websocket(websocket: WebSocket) -> None:
    sender = websocket.headers.get(SENDER_HEADER) or websocket.query_params.get(
        "sender", ""
    )
    if not _CONVERSATION_ID.match(sender):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    call = VoiceCall(
        websocket,
        websocket.app.state.service,
        sender,
        websocket.app.state.speech,
    )
    await call.run()


async def _tracker(request: Request) -> JSONResponse:
    conversation_id = _conversation_id(request)
    if conversation_id is None:
        return JSONResponse({"error": "invalid conversation id"}, status_code=400)
    service: AgentService = request.app.state.service
    return JSONResponse(await service.tracker(conversation_id))


async def _append_events(request: Request) -> JSONResponse:
    conversation_id = _conversation_id(request)
    if conversation_id is None:
        return JSONResponse({"error": "invalid conversation id"}, status_code=400)
    body: Any = await request.json()
    new_events = body if isinstance(body, list) else [body]
    if not all(isinstance(event, dict) and "event" in event for event in new_events):
        return JSONResponse({"error": "events must have an 'event' key"}, 400)
    service: AgentService = request.app.state.service
    await service.append_events(conversation_id, new_events)
    return JSONResponse(await service.tracker(conversation_id))


async def _engine_tokens(request: Request) -> JSONResponse:
    conversation_id = _conversation_id(request)
    if conversation_id is None:
        return JSONResponse({"error": "invalid conversation id"}, status_code=400)
    service: AgentService = request.app.state.service
    return JSONResponse(service.ledger.payload(conversation_id))


async def _voice_usage(request: Request) -> JSONResponse:
    conversation_id = _conversation_id(request)
    if conversation_id is None:
        return JSONResponse({"error": "invalid conversation id"}, status_code=400)
    service: AgentService = request.app.state.service
    return JSONResponse(service.voice_usage.payload(conversation_id))


async def _turn(request: Request) -> JSONResponse:
    conversation_id = _conversation_id(request)
    if conversation_id is None:
        return JSONResponse({"error": "invalid conversation id"}, status_code=400)
    service: AgentService = request.app.state.service
    return JSONResponse(await service.turn_view(conversation_id))


def _channel(value: object) -> str:
    return value if value in {_REST_CHANNEL, _VOICE_CHANNEL} else _REST_CHANNEL


def _conversation_id(request: Request) -> str | None:
    value = request.path_params["conversation_id"]
    return value if _CONVERSATION_ID.match(value) else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the native agent.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logger.info("Serving the native agent (%s)", ENGINE)
    uvicorn.run(create_app(), host=args.host, port=args.port, ws="websockets-sansio")


if __name__ == "__main__":
    main()
