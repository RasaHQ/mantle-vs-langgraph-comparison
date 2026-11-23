"""The mock backend each domain's tools call, as plain functions.

Each function takes the conversation's memory and the model's arguments and
returns an :class:`Outcome`. The graph turns an outcome into a tool message,
memory writes, and spoken responses, so these functions need no LangGraph.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from langgraph_native.responses import Utterance

Memory = Mapping[str, Any]
Gate = Callable[[Memory], bool]


class Outcome(BaseModel):
    """What one tool call produced."""

    model_config = ConfigDict(frozen=True)

    result: dict[str, Any]
    memory: dict[str, Any] = Field(default_factory=dict)
    say: list[Utterance] = Field(default_factory=list)


def error(message: str, **details: Any) -> Outcome:
    """Returns an outcome that reports *message* to the model and changes nothing."""
    return Outcome(result={"ok": False, "error": message, **details})
