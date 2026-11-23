"""LangChain tools over the plain domain functions.

A tool returns a :class:`langgraph.types.Command` so the conversation memory
and the tracker events update together with the tool message. A handoff
copies the whole memory and event list into that command: leaving a
specialist through ``Command.PARENT`` sends only the command's update to the
parent graph, not the specialist's other writes. A handoff therefore also
answers any other tool call from the same model reply, which would otherwise
be dropped and rejected on the next turn.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.config import get_stream_writer
from langgraph.graph import END
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field

from langgraph_native import events
from langgraph_native.consent import is_yes
from langgraph_native.events import Event
from langgraph_native.responses import Utterance, default_responses
from langgraph_native.state import memory_set_events
from langgraph_native.tools import Memory, Outcome

logger = logging.getLogger(__name__)

SUPERVISOR = "supervisor"
CONTINUE = "default_continue_interrupted"
_MCP_SERVER = "mock_tools"


class NoArgs(BaseModel):
    """A tool that takes nothing from the model."""


class ToolSpec(BaseModel):
    """One domain function exposed to a specialist."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    description: str
    skill_id: str
    run: Callable[[Memory, dict[str, Any]], Outcome]
    args_schema: type[BaseModel] = NoArgs
    confirm: str | None = None
    denial: str | None = None
    confirm_values: Callable[[Memory, dict[str, Any]], dict[str, Any]] | None = None
    goto: str | None = None
    completes: bool = False


def speak(text: str) -> None:
    """Sends *text* to the caller while the turn is still running.

    A direct call with no stream writer, such as a unit test, says nothing.
    """
    if not text:
        return
    try:
        get_stream_writer()({"utterance": text})
    except RuntimeError:
        return


class _Tool(StructuredTool):
    def _to_args_and_kwargs(
        self, tool_input: str | dict[str, Any], tool_call_id: str | None
    ) -> tuple[tuple[str, ...], dict[str, Any]]:
        # An empty schema makes StructuredTool drop every argument, including
        # the injected ToolRuntime, so a tool with no model inputs never runs.
        parsed = self._parse_input(tool_input, tool_call_id)
        if isinstance(parsed, str):
            return (parsed,), {}
        return (), dict(parsed)


def make_tool(spec: ToolSpec) -> BaseTool:
    """Returns a tool that runs *spec* and writes its memory and events."""

    async def run(runtime: ToolRuntime, **kwargs: Any) -> Command:
        memory: Memory = runtime.state.get("memory") or {}
        arguments = spec.args_schema.model_validate(kwargs).model_dump()
        new_events: list[Event] = []
        if spec.confirm:
            agreed, consent_events = await _confirm(spec, runtime, memory, arguments)
            new_events.extend(consent_events)
            if not agreed:
                denial = default_responses().render(Utterance(name=spec.denial or ""))
                speak(denial)
                new_events.append(events.bot(denial))
                return _result(
                    runtime,
                    spec,
                    {"ok": False, "error": "customer_declined"},
                    {},
                    new_events,
                    is_error=True,
                    error_message="customer_declined",
                )
        outcome = spec.run(memory, arguments)
        for utterance in outcome.say:
            text = default_responses().render(utterance)
            speak(text)
            new_events.append(events.bot(text))
        if spec.goto and _succeeded(outcome.result):
            return _handoff(
                runtime,
                json.dumps(outcome.result),
                spec.goto,
                memory=outcome.memory,
                extra_events=new_events,
                tool=(spec, outcome.result, arguments, False, None),
                complete=spec.skill_id if spec.completes else None,
            )
        return _result(
            runtime,
            spec,
            outcome.result,
            outcome.memory,
            new_events,
            is_error=not _succeeded(outcome.result),
            error_message=_error_message(outcome.result),
            arguments=arguments,
        )

    return _Tool.from_function(
        coroutine=run,
        name=spec.name,
        description=spec.description,
        args_schema=spec.args_schema,
    )


def handoff_tool(
    name: str,
    description: str,
    goto: str,
    *,
    skill_id: str | None = None,
    completes: bool = False,
    cancels: bool = False,
    pause: bool = False,
) -> BaseTool:
    """Returns a tool whose only effect is to move the conversation to *goto*."""

    async def run(runtime: ToolRuntime) -> Command:
        return _handoff(
            runtime,
            f"Transferred to {goto}.",
            goto,
            complete=skill_id if completes else None,
            cancel=skill_id if cancels else None,
            pause=pause,
            tool_name=name,
            skill_id=skill_id,
        )

    return _Tool.from_function(
        coroutine=run, name=name, description=description, args_schema=NoArgs
    )


def finish_tool(skill_id: str) -> BaseTool:
    """Returns the tool that ends a task and goes back to the supervisor."""
    return handoff_tool(
        "finish_task",
        "Call when this task is done and the customer has been told the outcome.",
        SUPERVISOR,
        skill_id=skill_id,
        completes=True,
    )


def transfer_back_tool(skill_id: str) -> BaseTool:
    """Returns the tool that gives the conversation back without ending the task."""
    return handoff_tool(
        "transfer_back",
        "Call when the customer changes the subject. What is already recorded is kept.",
        SUPERVISOR,
        skill_id=skill_id,
        pause=True,
    )


def cancel_tool(skill_id: str) -> BaseTool:
    """Returns the tool that abandons a task the customer no longer wants."""
    return handoff_tool(
        "cancel_task",
        "Call when the customer no longer wants this task done.",
        SUPERVISOR,
        skill_id=skill_id,
        cancels=True,
    )


def search_tool() -> BaseTool:
    """Returns the policy search tool."""

    class Query(BaseModel):
        query: str = Field(description="What to look up in the policy documents.")

    async def run(query: str, runtime: ToolRuntime) -> Command:
        knowledge = runtime.config["configurable"]["knowledge"]
        conversation_id = runtime.config["configurable"]["thread_id"]
        found = await knowledge.search(query, conversation_id)
        return _result(
            runtime,
            _search_spec(runtime),
            {"results": found},
            {},
            [],
            is_error=False,
            error_message=None,
            arguments={"query": query},
        )

    return _Tool.from_function(
        coroutine=run,
        name="search_knowledge",
        description=(
            "Look up an Acme policy. Call this before answering a policy question "
            "or before saying something cannot be done."
        ),
        args_schema=Query,
    )


def cannot_help_tool() -> BaseTool:
    """Returns the tool that says the request is out of scope and stops."""

    async def run(runtime: ToolRuntime) -> Command:
        text = default_responses().render(Utterance(name="utter_decline_out_of_scope"))
        speak(text)
        return _handoff(
            runtime,
            "Told the customer this is out of scope.",
            END,
            extra_events=[events.bot(text)],
            tool_name="cannot_help",
        )

    return _Tool.from_function(
        coroutine=run,
        name="cannot_help",
        description=(
            "Call when the request is not about cards, accounts, "
            "orders, SIMs, or bills."
        ),
        args_schema=NoArgs,
    )


def mcp_event(
    name: str, arguments: dict[str, Any], content: str, *, is_error: bool
) -> Event:
    """Returns the tracker event for one MCP bill tool call."""
    return events.tool_executed(
        name,
        arguments,
        content,
        is_error=is_error,
        error_message=content if is_error else None,
        source="mcp",
        mcp_server=_MCP_SERVER,
        skill_id="bill_inquiry",
    )


async def _confirm(
    spec: ToolSpec,
    runtime: ToolRuntime,
    memory: Memory,
    arguments: dict[str, Any],
) -> tuple[bool, list[Event]]:
    values = spec.confirm_values(memory, arguments) if spec.confirm_values else {}
    question = default_responses().render(
        Utterance(name=spec.confirm or "", values=values)
    )
    # The question is spoken by the service when the run pauses. Recording it
    # here would speak it twice, because this function restarts on resume.
    answer = interrupt_value(question)
    agreed = await is_yes(str(answer), runtime.config["configurable"]["chat_model"])
    channel = runtime.state.get("channel") or "rest"
    return agreed, [events.bot(question), events.user(str(answer), channel)]


def interrupt_value(question: str) -> Any:
    """Pauses for the customer's answer. Split out so a test can replace it."""
    from langgraph.types import interrupt

    return interrupt(question)


def _result(
    runtime: ToolRuntime,
    spec: ToolSpec,
    result: dict[str, Any],
    memory: dict[str, Any],
    extra_events: list[Event],
    *,
    is_error: bool,
    error_message: str | None,
    arguments: dict[str, Any] | None = None,
) -> Command:
    before: Memory = runtime.state.get("memory") or {}
    tracker = [
        events.tool_executed(
            spec.name,
            arguments or {},
            json.dumps(result),
            is_error=is_error,
            error_message=error_message,
            skill_id=spec.skill_id,
        ),
        *memory_set_events(before, memory),
        *extra_events,
    ]
    return Command(
        update={
            "memory": memory,
            "events": tracker,
            "messages": [
                ToolMessage(
                    content=json.dumps(result), tool_call_id=runtime.tool_call_id
                )
            ],
        }
    )


def _handoff(
    runtime: ToolRuntime,
    content: str,
    goto: str,
    *,
    memory: dict[str, Any] | None = None,
    extra_events: list[Event] | None = None,
    tool: tuple[ToolSpec, dict[str, Any], dict[str, Any], bool, str | None]
    | None = None,
    tool_name: str | None = None,
    skill_id: str | None = None,
    complete: str | None = None,
    cancel: str | None = None,
    pause: bool = False,
) -> Command:
    state = runtime.state
    merged_memory = {**(state.get("memory") or {}), **(memory or {})}
    tracker = list(extra_events or [])
    if tool is not None:
        spec, result, arguments, is_error, error_message = tool
        tracker.insert(
            0,
            events.tool_executed(
                spec.name,
                arguments,
                json.dumps(result),
                is_error=is_error,
                error_message=error_message,
                skill_id=spec.skill_id,
            ),
        )
        tracker[1:1] = memory_set_events(state.get("memory") or {}, memory or {})
    elif tool_name:
        tracker.append(
            events.tool_executed(
                tool_name,
                {},
                content,
                is_error=False,
                skill_id=skill_id,
            )
        )
    started = dict(state.get("started") or {})
    active = state.get("active")
    if complete:
        tracker.append(events.skill_completed(complete))
        started[complete] = False
        active = None
    if cancel:
        tracker.append(events.skill_cancelled(cancel))
        started[cancel] = False
        active = None
    if goto == SUPERVISOR:
        active = None
    paused = _paused_after(
        state, started, skill_id, pause=pause, done=complete or cancel
    )
    if paused and (complete or cancel) and goto == SUPERVISOR:
        goto = CONTINUE
    own = ToolMessage(content=content, tool_call_id=runtime.tool_call_id)
    return Command(
        goto=goto,
        graph=Command.PARENT,
        update={
            "messages": [
                *state.get("messages", []),
                own,
                *_dropped_tool_calls(state, runtime.tool_call_id),
            ],
            "memory": merged_memory,
            "events": [*(state.get("events") or []), *tracker],
            "started": started,
            "paused": paused,
            "active": active,
            "model_calls": state.get("model_calls", 0),
        },
    )


def _dropped_tool_calls(
    state: dict[str, Any], answered: str | None
) -> list[ToolMessage]:
    """Returns a reply for each sibling tool call a parent handoff drops.

    The parent graph keeps only this command's update, so the other tool
    results from the same model reply never land. The next model call rejects
    a tool call that has no reply.
    """
    messages = state.get("messages") or []
    calling = next(
        (
            message
            for message in reversed(messages)
            if isinstance(message, AIMessage) and message.tool_calls
        ),
        None,
    )
    if calling is None:
        return []
    return [
        ToolMessage(
            content=json.dumps({"ok": False, "error": "dropped_by_handoff"}),
            tool_call_id=tool_call["id"],
            name=tool_call.get("name"),
            status="error",
        )
        for tool_call in calling.tool_calls
        if tool_call["id"] != answered
    ]


def _paused_after(
    state: dict[str, Any],
    started: dict[str, bool],
    skill_id: str | None,
    *,
    pause: bool,
    done: str | None,
) -> list[str]:
    """Returns the paused tasks after this handoff, most recent last.

    Choosing a card sits inside the replacement, so leaving the choice keeps
    the replacement underneath it.
    """
    paused = [item for item in (state.get("paused") or []) if item != done]
    if not pause:
        return paused
    for open_id, on in started.items():
        if on and open_id not in paused and open_id != skill_id:
            paused.append(open_id)
    if skill_id and skill_id not in paused:
        paused.append(skill_id)
    return paused


def note(text: str) -> SystemMessage:
    """Returns a message that tells the model the outcome of a fixed step."""
    return SystemMessage(content=text)


def _search_spec(runtime: ToolRuntime) -> ToolSpec:
    return ToolSpec(
        name="search_knowledge",
        description="",
        skill_id=runtime.state.get("active") or "",
        run=lambda memory, args: Outcome(result={}),
    )


def _succeeded(result: dict[str, Any]) -> bool:
    if result.get("ok") is False or result.get("success") is False:
        return False
    return (
        "error" not in result
        or result.get("success") is True
        or result.get("ok") is True
    )


def _error_message(result: dict[str, Any]) -> str | None:
    if _succeeded(result):
        return None
    error = result.get("error")
    return str(error) if error else "tool_failed"
