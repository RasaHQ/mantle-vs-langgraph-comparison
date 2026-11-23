"""Rasa tracker events in the flat JSON shape ``rasa.shared.core.events`` reads.

The evaluation harness fetches ``GET /conversations/<id>/tracker`` and runs
``deserialise_events`` over ``events``. Scenario assertions read
``skill_activated``, ``skill_completed``, ``memory_set`` and ``tool_executed``,
so each builder emits the keys those event classes take.
"""

from __future__ import annotations

import time
from typing import Any, Optional

Event = dict[str, Any]


def _event(type_name: str, **fields: Any) -> Event:
    return {"event": type_name, "timestamp": time.time(), **fields}


def action(name: str) -> Event:
    return _event("action", name=name, policy=None, confidence=None)


def session_started() -> Event:
    return _event("session_started")


def user(text: str, input_channel: str) -> Event:
    return _event(
        "user",
        text=text,
        parse_data={"intent": {}, "entities": [], "text": text},
        input_channel=input_channel,
    )


def bot(text: str) -> Event:
    return _event("bot", text=text, data={}, metadata={})


def memory_set(key: str, value: Any) -> Event:
    return _event("memory_set", key=key, value=value)


def skill_activated(skill_id: str) -> Event:
    return _event("skill_activated", skill_id=skill_id)


def skill_completed(skill_id: str) -> Event:
    return _event("skill_completed", skill_id=skill_id)


def skill_cancelled(skill_id: str) -> Event:
    return _event("skill_cancelled", skill_id=skill_id, step_id=None)


def skill_interrupted(skill_id: str) -> Event:
    return _event("skill_interrupted", skill_id=skill_id, step_id=None)


def skill_resumed(skill_id: str) -> Event:
    return _event("skill_resumed", skill_id=skill_id, step_id=None)


def tool_executed(
    tool_name: str,
    arguments: dict[str, Any],
    result: str,
    *,
    is_error: bool,
    error_message: Optional[str] = None,
    source: str = "local",
    mcp_server: Optional[str] = None,
    skill_id: Optional[str] = None,
) -> Event:
    return _event(
        "tool_executed",
        tool_name=tool_name,
        arguments=arguments,
        source=source,
        result=result,
        is_error=is_error,
        error_message=error_message,
        mcp_server=mcp_server,
        metadata={"skill_id": skill_id} if skill_id else {},
    )
