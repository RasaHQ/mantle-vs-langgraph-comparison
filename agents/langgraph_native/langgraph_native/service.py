"""Runs one conversation turn at a time and streams what the agent says."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from langgraph_native.config import AgentConfig, load_config
from langgraph_native.graph import RECURSION_LIMIT, build_graph
from langgraph_native.knowledge import Knowledge, KnowledgeIndex
from langgraph_native.llm import Embeddings, build_chat_model
from langgraph_native.state import Incoming
from langgraph_native.tracing import ENGINE, configure_tracing
from langgraph_native.usage import UsageLedger
from langgraph_native.voice_usage import VoiceUsageStore

logger = logging.getLogger(__name__)

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class AgentService:
    """The in-process runner used by the terminal, the web chat, and the server."""

    def __init__(
        self,
        graph: CompiledStateGraph,
        model: BaseChatModel,
        ledger: UsageLedger,
        knowledge: Knowledge,
    ) -> None:
        self.graph = graph
        self.model = model
        self.ledger = ledger
        self.knowledge = knowledge
        self.voice_usage = VoiceUsageStore()
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._unheard: dict[str, list[str]] = defaultdict(list)

    @classmethod
    async def create(cls, config: AgentConfig | None = None) -> "AgentService":
        """Builds the model, the knowledge index, and the bill tools."""
        load_dotenv(_ENV_FILE)
        configure_tracing()
        settings = config or load_config()
        ledger = UsageLedger()
        model = build_chat_model(settings)
        knowledge = await _knowledge(Embeddings(settings, ledger))
        mcp_tools = await _bill_tools(settings)
        graph = build_graph(model, settings, InMemorySaver(), mcp_tools)
        return cls(graph, model, ledger, knowledge)

    async def run_turn(
        self, conversation_id: str, incoming: Incoming
    ) -> AsyncIterator[str]:
        """Runs one turn and yields each thing the customer should hear.

        A turn that paused on a confirmation resumes with this message instead
        of starting again at the supervisor.
        """
        config = self._config(conversation_id, incoming.channel)
        async with self._locks[conversation_id]:
            missed = self._unheard.pop(conversation_id, [])
            if missed:
                config["configurable"]["unheard"] = missed
            snapshot = await self.graph.aget_state(config)
            if snapshot.interrupts and incoming.kind == "message":
                payload: Any = Command(resume=incoming.text)
            else:
                raw = incoming.model_dump()
                if missed:
                    raw["unheard"] = missed
                payload = {"incoming": raw}
            async for item in self.graph.astream(
                payload, config, stream_mode="custom", subgraphs=True
            ):
                text = _utterance(item)
                if text:
                    yield text
            paused = await self.graph.aget_state(config)
            for interrupt in paused.interrupts:
                if isinstance(interrupt.value, str) and interrupt.value:
                    yield interrupt.value

    def note_unheard(self, conversation_id: str, texts: list[str]) -> None:
        """Records replies the caller interrupted, for the next turn to mark."""
        pending = self._unheard[conversation_id]
        for text in texts:
            cleaned = text.strip()
            if cleaned and cleaned not in pending:
                pending.append(cleaned)

    async def has_session(self, conversation_id: str) -> bool:
        """Test if the conversation already ran its session start."""
        return any(
            event.get("event") == "session_started"
            for event in await self.events(conversation_id)
        )

    async def events(self, conversation_id: str) -> list[dict[str, Any]]:
        """Returns the conversation's tracker events."""
        snapshot = await self.graph.aget_state(self._config(conversation_id))
        return list((snapshot.values or {}).get("events") or [])

    async def append_events(
        self, conversation_id: str, new_events: list[dict[str, Any]]
    ) -> None:
        """Appends externally supplied events (the harness's preseed)."""
        stamped = [{"timestamp": time.time(), **event} for event in new_events]
        async with self._locks[conversation_id]:
            await self.graph.aupdate_state(
                self._config(conversation_id),
                {"events": stamped},
                as_node="preseed",
            )

    async def tracker(self, conversation_id: str) -> dict[str, Any]:
        """Returns the tracker JSON the evaluation harness reads."""
        tracker_events = await self.events(conversation_id)
        latest_user = next(
            (event for event in reversed(tracker_events) if event["event"] == "user"),
            None,
        )
        return {
            "sender_id": conversation_id,
            "slots": {},
            "latest_message": (latest_user or {}).get("parse_data", {}),
            "latest_event_time": tracker_events[-1]["timestamp"]
            if tracker_events
            else None,
            "followup_action": None,
            "paused": False,
            "events": tracker_events,
            "latest_input_channel": (latest_user or {}).get("input_channel"),
            "active_loop": {},
            "latest_action_name": "action_listen",
        }

    async def turn_view(self, conversation_id: str) -> dict[str, Any]:
        """Returns the domain state, events, and token usage the chat page shows."""
        snapshot = await self.snapshot(conversation_id)
        snapshot["events"] = await self.events(conversation_id)
        snapshot["usage"] = self.ledger.payload(conversation_id)
        return snapshot

    async def snapshot(self, conversation_id: str) -> dict[str, Any]:
        """Returns the active task, the paused stack, and the domain memory."""
        state = await self.graph.aget_state(self._config(conversation_id))
        values = state.values or {}
        return {
            "active": values.get("active"),
            "paused": list(values.get("paused") or []),
            "memory": dict(values.get("memory") or {}),
        }

    def _config(self, conversation_id: str, channel: str = "rest") -> dict[str, Any]:
        return {
            "configurable": {
                "thread_id": conversation_id,
                "chat_model": self.model,
                "ledger": self.ledger,
                "knowledge": self.knowledge,
            },
            "recursion_limit": RECURSION_LIMIT,
            "tags": [ENGINE, channel],
            "metadata": {
                "conversation_id": conversation_id,
                "thread_id": conversation_id,
                "engine": ENGINE,
                "channel": channel,
            },
        }


class EmptyKnowledge:
    """Search result used when the reference index could not be built."""

    async def search(self, query: str, conversation_id: str) -> str:
        return "No relevant policy was found."


async def _knowledge(embeddings: Embeddings) -> Knowledge:
    try:
        return await KnowledgeIndex.build(embeddings)
    except Exception:
        logger.warning("Knowledge index unavailable; policy search is disabled")
        return EmptyKnowledge()


async def _bill_tools(config: AgentConfig) -> list:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    from langgraph_native.config import MCP_SERVER_NAME

    client = MultiServerMCPClient(
        {
            MCP_SERVER_NAME: {
                "url": config.mcp_server_url,
                "transport": "streamable_http",
                "headers": {"Authorization": f"Bearer {config.mcp_token}"},
            }
        }
    )
    try:
        return await client.get_tools()
    except Exception:
        logger.warning("MCP server unavailable; bill tools disabled")
        return []


def _utterance(item: object) -> str | None:
    data = item[-1] if isinstance(item, tuple) else item
    if isinstance(data, dict):
        text = data.get("utterance")
        return text or None
    return None
