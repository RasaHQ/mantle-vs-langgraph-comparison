"""Offers the most recently paused task once the current one is finished.

The node is named ``builtin_continue_interrupted`` because the scenario
assertions read that id. It is one question over the paused stack, not a
skill with its own tools.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, interrupt

from langgraph_native import events
from langgraph_native.consent import is_yes
from langgraph_native.responses import Utterance, default_responses
from langgraph_native.tooling import CONTINUE, SUPERVISOR

_TASKS = {
    "card_replace": "replacing your card",
    "card_disambiguate": "choosing which card",
    "card_advisory": "the card advice",
    "account_advisory": "your accounts",
    "order_status": "checking your order",
    "bill_inquiry": "your bill",
    "sim_management": "the SIM",
}


async def offer_resume(state: dict, config: RunnableConfig) -> Command:
    """Asks whether to continue the most recent paused task, or drop it."""
    paused = list(state.get("paused") or [])
    if not paused:
        return Command(goto=SUPERVISOR, update={"active": None})
    skill_id = paused[-1]
    question = default_responses().render(
        Utterance(
            name="utter_continue_interrupted",
            values={"task": _TASKS.get(skill_id, "what we were doing")},
        )
    )
    answer = interrupt(question)
    agreed = await is_yes(str(answer), config["configurable"]["chat_model"])
    channel = state.get("channel") or "rest"
    remaining = paused[:-1]
    tracker = [
        events.skill_activated(CONTINUE),
        events.skill_completed(CONTINUE),
        events.bot(question),
        events.user(str(answer), channel),
    ]
    update: dict = {"paused": remaining, "events": tracker, "active": None}
    if agreed:
        return Command(goto=skill_id, update=update)
    started = dict(state.get("started") or {})
    started[skill_id] = False
    tracker.append(events.skill_cancelled(skill_id))
    update["started"] = started
    return Command(goto=CONTINUE if remaining else SUPERVISOR, update=update)
