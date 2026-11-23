"""Per-specialist middleware: tool gates, fillers, spoken text, and token usage.

Channel rules, the clock, and the task state are appended after the
conversation rather than written into the system prompt. The system prompt
then stays identical across calls, which is what the provider caches, and one
specialist can serve both the text and the voice channel.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime

from langchain.agents.middleware import (
    AgentMiddleware,
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
)
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.config import get_config
from langgraph.errors import GraphBubbleUp
from langgraph.types import Command

from langgraph_native import events
from langgraph_native.barge import configured_unheard, unheard_message
from langgraph_native.config import AgentConfig
from langgraph_native.skill_catalog import skills_catalog_section
from langgraph_native.state import DOMAINS
from langgraph_native.text import message_text
from langgraph_native.tooling import mcp_event, speak
from langgraph_native.tools import Gate
from langgraph_native.usage import Generation, UsageLedger

logger = logging.getLogger(__name__)

_FILLER = """\
If this reply calls a tool, start it with one short sentence the customer
hears while the tool runs. It must stay true whatever the tool returns.
A reply without a tool call has no such sentence.

Examples:
{examples}"""


class SpecialistMiddleware(AgentMiddleware):
    """Gates one specialist's tools and speaks what its model writes."""

    def __init__(
        self,
        config: AgentConfig,
        skill_id: str | None,
        gates: dict[str, Gate] | None = None,
        mcp_tools: frozenset[str] = frozenset(),
    ) -> None:
        self.config = config
        self.skill_id = skill_id
        self.gates = gates or {}
        self.mcp_tools = mcp_tools

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable
    ) -> ExtendedModelResponse:
        prepared = self._prepare(request)
        return self._finish(prepared, handler(prepared))

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable
    ) -> ExtendedModelResponse:
        prepared = self._prepare(request)
        return self._finish(prepared, await handler(prepared))

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable):
        if not self._allowed(request):
            return self._refused(request)
        try:
            result = handler(request)
        except GraphBubbleUp:
            # interrupt() pauses by raising, so a confirmation is not a failure.
            raise
        except Exception as exc:
            logger.warning(
                "Tool %s failed (%s)",
                request.tool_call.get("name"),
                type(exc).__name__,
            )
            return self._failed(request)
        return self._with_mcp_event(request, result)

    async def awrap_tool_call(self, request: ToolCallRequest, handler: Callable):
        if not self._allowed(request):
            return self._refused(request)
        try:
            result = await handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:
            logger.warning(
                "Tool %s failed (%s)",
                request.tool_call.get("name"),
                type(exc).__name__,
            )
            return self._failed(request)
        return self._with_mcp_event(request, result)

    def _prepare(self, request: ModelRequest) -> ModelRequest:
        memory = request.state.get("memory") or {}
        finished = _transfers_to_finished(request.state)
        tools = [
            tool
            for tool in request.tools
            if self._keeps(tool, memory) and _tool_name(tool) not in finished
        ]
        messages = [*request.messages, SystemMessage(content=self._context(request))]
        reminder = unheard_message(request.messages, configured_unheard())
        if reminder is not None:
            messages.append(reminder)
        if request.state.get("model_calls", 0) == 0 and self.config.fillers_on(
            request.state.get("channel") or "rest"
        ):
            messages.append(SystemMessage(content=self._filler()))
        # One tool call per reply. A handoff leaves through the parent graph
        # and drops every other tool result from that same reply.
        settings = dict(request.model_settings)
        if tools:
            settings["parallel_tool_calls"] = False
        return request.override(tools=tools, messages=messages, model_settings=settings)

    def _finish(
        self,
        request: ModelRequest,
        response: ModelResponse | AIMessage | ExtendedModelResponse,
    ) -> ExtendedModelResponse:
        model_response, message = _model_response(response)
        self._record(request, message)
        text = message_text(message) if message else ""
        spoken = []
        if text:
            speak(text)
            spoken.append(events.bot(text))
        update: dict = {
            "model_calls": request.state.get("model_calls", 0) + 1,
            "events": spoken,
        }
        # A paused confirmation resumes inside the specialist, so ingest never
        # sees the interrupted lines. Record them on this model call instead.
        reminder = unheard_message(
            list(request.state.get("messages") or []), configured_unheard()
        )
        if reminder is not None:
            update["messages"] = [reminder]
        return ExtendedModelResponse(
            model_response=model_response,
            command=Command(update=update),
        )

    def _keeps(self, tool: object, memory: dict) -> bool:
        name = _tool_name(tool)
        gate = self.gates.get(name or "")
        return gate is None or bool(gate(memory))

    def _allowed(self, request: ToolCallRequest) -> bool:
        name = request.tool_call.get("name") or ""
        gate = self.gates.get(name)
        if gate is None:
            return True
        return bool(gate(request.state.get("memory") or {}))

    def _refused(self, request: ToolCallRequest) -> Command:
        name = request.tool_call.get("name") or ""
        arguments = request.tool_call.get("args") or {}
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({"ok": False, "error": "not_available"}),
                        tool_call_id=request.tool_call["id"],
                    )
                ],
                "events": [
                    events.tool_executed(
                        name,
                        arguments,
                        json.dumps({"ok": False, "error": "not_available"}),
                        is_error=True,
                        error_message="not_available",
                        skill_id=self.skill_id,
                    )
                ],
            }
        )

    def _failed(self, request: ToolCallRequest) -> Command:
        name = request.tool_call.get("name") or ""
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({"ok": False, "error": "tool_failed"}),
                        tool_call_id=request.tool_call["id"],
                    )
                ],
                "events": [
                    events.tool_executed(
                        name,
                        request.tool_call.get("args") or {},
                        json.dumps({"ok": False, "error": "tool_failed"}),
                        is_error=True,
                        error_message="tool_failed",
                        skill_id=self.skill_id,
                    )
                ],
            }
        )

    def _with_mcp_event(self, request: ToolCallRequest, result: object) -> object:
        name = request.tool_call.get("name") or ""
        if name not in self.mcp_tools or isinstance(result, Command):
            return result
        content = result.content if isinstance(result, ToolMessage) else str(result)
        message = (
            result
            if isinstance(result, ToolMessage)
            else ToolMessage(content=content, tool_call_id=request.tool_call["id"])
        )
        failed = isinstance(content, str) and content.lower().startswith("error")
        return Command(
            update={
                "messages": [message],
                "events": [
                    mcp_event(
                        name,
                        request.tool_call.get("args") or {},
                        content,
                        is_error=failed,
                    )
                ],
            }
        )

    def _context(self, request: ModelRequest) -> str:
        channel = request.state.get("channel") or "rest"
        parts = [
            self.config.channel_rules(channel),
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            _summary(self.skill_id, request.state, self.config),
        ]
        if self.config.skill_catalog_each_turn:
            parts.append(skills_catalog_section())
        if self.config.router_first and self.skill_id is None:
            parts.append(_router_first_hints(request.state))
        return "\n\n".join(part for part in parts if part)

    def _filler(self) -> str:
        examples = "\n".join(
            f'- customer: "{example.user}" -> "{example.filler}"'
            for example in self.config.filler_examples
        )
        return _FILLER.format(examples=examples)

    def _record(self, request: ModelRequest, message: AIMessage | None) -> None:
        if message is None:
            return
        usage = message.usage_metadata or {}
        if not usage.get("input_tokens") and not usage.get("output_tokens"):
            return
        try:
            configurable = get_config().get("configurable") or {}
        except RuntimeError:
            return
        ledger: UsageLedger | None = configurable.get("ledger")
        conversation_id = configurable.get("thread_id")
        if ledger is None or not conversation_id:
            return
        details = usage.get("input_token_details") or {}
        model = getattr(request.model, "model_name", None) or getattr(
            request.model, "model", "unknown"
        )
        ledger.record(
            conversation_id,
            Generation(
                call_type=self.skill_id or "supervisor",
                model=str(model),
                prompt=usage.get("input_tokens", 0),
                completion=usage.get("output_tokens", 0),
                cached=details.get("cache_read") or 0,
                cache_write=details.get("cache_creation") or 0,
            ),
        )


_ROUTER_FIRST = """\
Router-first turn: choose the right skill for this message.
- If a task is already active and the customer continues it, transfer there again.
- If a task is still active and the customer is only thanking you, signing off,
  or saying they need nothing else, transfer to that same task so it can call
  finish_task. Do not say goodbye yourself while a task is active.
- If they change the subject, transfer to the matching skill (or transfer_back is
  not available here; use the right transfer_to_* tool).
- Do not answer the request yourself."""


def _router_first_hints(state: dict) -> str:
    active = state.get("active")
    if not active:
        return _ROUTER_FIRST
    return (
        f"{_ROUTER_FIRST}\nActive task before this message: `{active}`. "
        "If the customer is still on that task, transfer there."
    )


def _summary(skill_id: str | None, state: dict, config: AgentConfig) -> str:
    domain = DOMAINS.get(skill_id or "")
    if domain is None:
        lines: list[str] = []
        active = state.get("active")
        if active:
            lines.append(f"Active task: `{active}`.")
        paused = state.get("paused") or []
        if paused:
            lines.append(
                "Paused tasks, most recent last: "
                + ", ".join(paused)
                + ". Route the new request. Do not resume a paused task yourself."
            )
        if not lines:
            return "No task is active or paused."
        return "\n".join(lines)
    view = domain.view(state.get("memory") or {})
    lines = [
        f"{name}: {value}"
        for name, value in view.model_dump().items()
        if value is not None and name not in domain.private_fields
    ]
    recorded = "\n".join(lines) if lines else "nothing recorded yet"
    return f"Current task state:\n{recorded}"


def _transfers_to_finished(state: dict) -> set[str]:
    """Transfer tool names for skills that finished since the customer last spoke.

    A skill that finished without a reply would otherwise be handed the same
    turn again, and the turn would loop until the graph's recursion limit.
    """
    finished: set[str] = set()
    for event in state.get("events") or []:
        if event.get("event") == "user":
            finished.clear()
        elif event.get("event") == "skill_completed":
            finished.add(event["skill_id"])
    return {f"transfer_to_{skill_id}" for skill_id in finished}


def _tool_name(tool: object) -> str | None:
    if isinstance(tool, dict):
        function = tool.get("function") or {}
        return tool.get("name") or function.get("name")
    return getattr(tool, "name", None)


def _model_response(
    response: ModelResponse | AIMessage | ExtendedModelResponse,
) -> tuple[ModelResponse, AIMessage | None]:
    if isinstance(response, AIMessage):
        return ModelResponse(result=[response]), response
    if isinstance(response, ExtendedModelResponse):
        response = response.model_response
    message = next(
        (item for item in response.result if isinstance(item, AIMessage)), None
    )
    return response, message
