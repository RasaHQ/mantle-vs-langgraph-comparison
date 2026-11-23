"""The SIM block flow: check, ask, block, then share the device details.

Each step is its own node. The ask node pauses with ``interrupt``, and a node
restarts from the top when the customer answers, so the ask node does nothing
before the interrupt.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from langgraph_native import events
from langgraph_native.consent import is_yes
from langgraph_native.responses import Utterance, default_responses
from langgraph_native.state import SimManagement, memory_set_events
from langgraph_native.tooling import note, speak
from langgraph_native.tools import sim_management as sim

CHECK = "block_check"
ASK = "block_ask"
APPLY = "block_apply"
DECLINE = "block_decline"
DEVICE = "block_device"


def add_block_flow(graph: StateGraph, sim_agent: str) -> None:
    """Adds the block flow and returns it to the SIM agent."""
    graph.add_node(CHECK, block_check)
    graph.add_node(ASK, block_ask)
    graph.add_node(APPLY, block_apply)
    graph.add_node(DECLINE, block_decline)
    graph.add_node(DEVICE, block_device)
    graph.add_conditional_edges(CHECK, _after_check, [ASK, DEVICE])
    graph.add_conditional_edges(ASK, _after_ask, [APPLY, DECLINE])
    graph.add_edge(APPLY, DEVICE)
    graph.add_edge(DEVICE, sim_agent)
    graph.add_edge(DECLINE, sim_agent)


async def block_check(state: dict) -> dict:
    return _stored(
        state, sim.check_sim_status(state.get("memory") or {}), "check_sim_status", {}
    )


async def block_ask(state: dict, config: RunnableConfig) -> dict:
    question = default_responses().render(Utterance(name="utter_ask_block_sim"))
    answer = interrupt(question)
    wants = await is_yes(str(answer), config["configurable"]["chat_model"])
    before = state.get("memory") or {}
    outcome = sim.record_block_consent(before, wants)
    channel = state.get("channel") or "rest"
    return {
        "memory": outcome.memory,
        "events": [
            events.bot(question),
            events.user(str(answer), channel),
            *_tracker(
                before, outcome, "record_block_consent", {"wants_to_block": wants}
            ),
        ],
    }


async def block_apply(state: dict) -> dict:
    before = state.get("memory") or {}
    return _stored(state, sim.block_sim(before), "block_sim", {})


async def block_decline(state: dict) -> dict:
    text = default_responses().render(Utterance(name="utter_sim_left_active"))
    speak(text)
    return {
        "events": [events.bot(text)],
        "messages": [
            note(
                "SIM block flow finished. The customer declined, "
                "so the SIM stays active."
            )
        ],
    }


async def block_device(state: dict) -> dict:
    before = state.get("memory") or {}
    outcome = sim.get_device_info(before)
    shared = SimManagement.view({**before, **outcome.memory}).device_info_shared
    return {
        **_stored(state, outcome, "get_device_info", {}),
        "messages": [
            note(
                "SIM block flow finished. "
                + (
                    "The device IMEI and serial were just spoken."
                    if outcome.say
                    else "The device details were already shared."
                )
                + f" Device info shared: {shared is True}."
            )
        ],
    }


def _after_check(state: dict) -> str:
    if SimManagement.view(state.get("memory") or {}).sim_blocked:
        return DEVICE
    return ASK


def _after_ask(state: dict) -> str:
    if SimManagement.view(state.get("memory") or {}).wants_to_block:
        return APPLY
    return DECLINE


def _stored(state: dict, outcome: Any, name: str, arguments: dict) -> dict:
    return {
        "memory": outcome.memory,
        "events": _tracker(state.get("memory") or {}, outcome, name, arguments),
    }


def _tracker(before: dict, outcome: Any, name: str, arguments: dict) -> list:
    tracker = [
        events.tool_executed(
            name,
            arguments,
            json.dumps(outcome.result),
            is_error=False,
            skill_id="sim_management",
        ),
        *memory_set_events(before, outcome.memory),
    ]
    for utterance in outcome.say:
        text = default_responses().render(utterance)
        speak(text)
        tracker.append(events.bot(text))
    return tracker
