"""Terminal chat for one conversation.

``python -m langgraph_native.chat`` runs the agent in-process. ``--url`` talks
to a running server's REST webhook instead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from urllib.parse import urlparse

from langgraph_native.service import AgentService
from langgraph_native.state import Incoming
from langgraph_native.tracing import configure_tracing

_SESSION_START = "/session_start"


class ChatRequestError(Exception):
    """The remote server did not answer a chat request."""

    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(status)


class Session(Protocol):
    """What the terminal loop needs from an in-process or remote conversation."""

    async def start(self) -> list[str]:
        """Starts the conversation and returns the greeting."""

    async def say(self, text: str) -> list[str]:
        """Sends one customer message and returns what the agent says."""

    async def reset(self) -> list[str]:
        """Starts a fresh conversation and returns its greeting."""

    async def state(self) -> str:
        """Returns the domain state as text."""

    async def cost(self) -> str:
        """Returns the token usage and cost as text."""


class LocalSession:
    """A conversation run inside this process."""

    def __init__(self, service: AgentService, *, voice: bool) -> None:
        self.service = service
        self.channel = "voice" if voice else "rest"
        self.conversation_id = _new_id()

    async def start(self) -> list[str]:
        return await self._turn(Incoming(kind="session_start", channel=self.channel))

    async def say(self, text: str) -> list[str]:
        incoming = Incoming(kind="message", text=text, channel=self.channel)
        return await self._turn(incoming)

    async def reset(self) -> list[str]:
        self.conversation_id = _new_id()
        return await self.start()

    async def state(self) -> str:
        return format_state(await self.service.snapshot(self.conversation_id))

    async def cost(self) -> str:
        return format_cost(self.service.ledger.payload(self.conversation_id))

    async def _turn(self, incoming: Incoming) -> list[str]:
        return [
            text async for text in self.service.run_turn(self.conversation_id, incoming)
        ]


class RemoteSession:
    """A conversation on a running server, over its REST webhook."""

    def __init__(
        self,
        base_url: str,
        *,
        voice: bool,
        request: Callable[[str, str, dict | None], Awaitable[Any]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.channel = "voice" if voice else "rest"
        self.conversation_id = _new_id()
        self._request = request or http_json

    async def start(self) -> list[str]:
        return await self.say(_SESSION_START)

    async def say(self, text: str) -> list[str]:
        body = await self._request(
            "POST",
            f"{self.base_url}/webhooks/rest/webhook",
            {
                "sender": self.conversation_id,
                "message": text,
                "channel": self.channel,
            },
        )
        if not isinstance(body, list):
            raise ChatRequestError(0)
        return [str(item.get("text") or "") for item in body if isinstance(item, dict)]

    async def reset(self) -> list[str]:
        self.conversation_id = _new_id()
        return await self.start()

    async def state(self) -> str:
        body = await self._request(
            "GET",
            f"{self.base_url}/conversations/{self.conversation_id}/tracker",
            None,
        )
        return json.dumps(body, indent=2, default=str)

    async def cost(self) -> str:
        body = await self._request(
            "GET",
            f"{self.base_url}/conversations/{self.conversation_id}/engine_tokens",
            None,
        )
        if isinstance(body, dict) and (
            body.get("status") == "not_found" or "prompt" in body
        ):
            return format_cost(body)
        return json.dumps(body, indent=2, default=str)


async def run_loop(
    session: Session, read: Callable[[], str], write: Callable[[str], None]
) -> None:
    """Reads commands and customer messages until ``/quit`` or end of input."""
    for line in await session.start():
        write(line)
    while True:
        try:
            text = read().strip()
        except EOFError:
            return
        if not text:
            continue
        if text == "/quit":
            return
        if text == "/reset":
            for line in await session.reset():
                write(line)
            continue
        if text == "/state":
            write(await session.state())
            continue
        if text == "/cost":
            write(await session.cost())
            continue
        if text.startswith("/"):
            write("Unknown command. Use /reset, /state, /cost, or /quit.")
            continue
        for line in await session.say(text):
            write(line)


def format_state(snapshot: dict[str, Any]) -> str:
    """Returns the active task, the paused stack, and the domain memory."""
    return json.dumps(
        {
            "active": snapshot.get("active"),
            "paused": snapshot.get("paused") or [],
            "memory": snapshot.get("memory") or {},
        },
        indent=2,
        default=str,
    )


def format_cost(payload: dict[str, Any]) -> str:
    """Returns one line of token counts and cost."""
    if payload.get("status") == "not_found":
        return "No model usage yet."
    cost = payload.get("cost")
    return (
        f"prompt {payload.get('prompt', 0)}  "
        f"completion {payload.get('completion', 0)}  "
        f"cached {payload.get('cached', 0)}  "
        f"cost {cost} ({payload.get('cost_status', 'partial')})"
    )


async def http_json(method: str, url: str, body: dict | None) -> Any:
    """Sends one JSON request and returns the decoded body."""
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise ChatRequestError(exc.code) from exc
    except urllib.error.URLError as exc:
        raise ChatRequestError(0) from exc


def main(argv: list[str] | None = None) -> int:
    """Runs the terminal chat."""
    args = _parser().parse_args(argv)
    if args.url and not _http_url(args.url):
        print("The url must start with http:// or https://.", file=sys.stderr)
        return 2
    try:
        asyncio.run(_main(args))
    except ChatRequestError as exc:
        print(f"Request failed ({exc.status}).", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


async def _main(args: argparse.Namespace) -> None:
    configure_tracing()
    if args.url:
        session: Session = RemoteSession(args.url, voice=args.voice_rules)
    else:
        session = LocalSession(await AgentService.create(), voice=args.voice_rules)
    await run_loop(session, _read, print)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Talk to the native agent.")
    parser.add_argument("--voice-rules", action="store_true")
    parser.add_argument("--url", default="")
    return parser


def _read() -> str:
    return input("you> ")


def _http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _new_id() -> str:
    return uuid.uuid4().hex


if __name__ == "__main__":
    sys.exit(main())
