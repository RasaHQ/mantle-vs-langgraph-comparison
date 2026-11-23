"""The conversation graph: a greeting, a supervisor, and one agent per domain."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from langgraph_native import events
from langgraph_native.barge import unheard_message
from langgraph_native.config import AgentConfig
from langgraph_native.flows.block_sim import add_block_flow
from langgraph_native.flows.resume import offer_resume
from langgraph_native.responses import Utterance, default_responses
from langgraph_native.specialists import build_specialists, load_accounts
from langgraph_native.state import (
    ACCOUNT_ADVISORY,
    BILL_INQUIRY,
    CARD_ADVISORY,
    CARD_DISAMBIGUATE,
    CARD_REPLACE,
    ORDER_STATUS,
    SIM_MANAGEMENT,
    ConversationState,
    Incoming,
)
from langgraph_native.tooling import CONTINUE, SUPERVISOR, note, speak

RECURSION_LIMIT = 80

SKILL_IDS = (
    CARD_REPLACE,
    CARD_DISAMBIGUATE,
    CARD_ADVISORY,
    ACCOUNT_ADVISORY,
    ORDER_STATUS,
    BILL_INQUIRY,
    SIM_MANAGEMENT,
)


def build_graph(
    model: BaseChatModel,
    config: AgentConfig,
    checkpointer: BaseCheckpointSaver,
    mcp_tools: list[BaseTool] | None = None,
) -> CompiledStateGraph:
    """Returns the compiled conversation graph."""
    agents = build_specialists(model, config, mcp_tools or [])
    graph = StateGraph(ConversationState)
    graph.add_node("ingest", ingest)
    graph.add_node(SUPERVISOR, agents[SUPERVISOR])
    graph.add_node(CONTINUE, offer_resume)
    for skill_id in SKILL_IDS:
        entry = load_accounts if skill_id == ACCOUNT_ADVISORY else _enter(skill_id)
        graph.add_node(skill_id, entry)
        graph.add_node(f"{skill_id}_agent", agents[skill_id])
        graph.add_edge(skill_id, f"{skill_id}_agent")
    add_block_flow(graph, f"{SIM_MANAGEMENT}_agent")
    graph.add_node("preseed", preseed)
    graph.add_edge("preseed", END)
    graph.add_edge(START, "ingest")
    graph.add_conditional_edges(
        "ingest",
        lambda state: _route(state, config),
        [SUPERVISOR, *SKILL_IDS, END],
    )
    return graph.compile(checkpointer=checkpointer)


def preseed(state: ConversationState) -> dict:
    """Writer for events the harness appends outside a turn.

    ``update_state`` attributes that write to this node. Its only edge is the
    end, so the append does not start a turn.
    """
    return {}


def ingest(state: ConversationState) -> dict:
    """Records the incoming message and, on the first turn, greets and stops."""
    raw = dict(state.get("incoming") or {})
    missed = [text for text in raw.pop("unheard", []) or [] if isinstance(text, str)]
    incoming = Incoming.model_validate(raw)
    prior = list(state.get("messages") or [])
    noted: list[SystemMessage] = []
    reminder = unheard_message(prior, missed)
    if reminder is not None:
        noted.append(reminder)
    if incoming.kind == "session_start":
        if _session_open(state):
            update: dict = {"end_turn": True, "channel": incoming.channel}
            if noted:
                update["messages"] = noted
            return update
        text = default_responses().render(Utterance(name="utter_greet"))
        speak(text)
        return {
            "end_turn": True,
            "channel": incoming.channel,
            "model_calls": 0,
            "messages": [*noted, AIMessage(content=text)],
            "events": [
                events.action("action_session_start"),
                events.session_started(),
                events.bot(text),
            ],
        }
    return {
        "end_turn": False,
        "channel": incoming.channel,
        "model_calls": 0,
        "messages": [*noted, HumanMessage(content=incoming.text)],
        "events": [events.user(incoming.text, incoming.channel)],
    }


def _route(state: ConversationState, config: AgentConfig) -> str:
    if state.get("end_turn"):
        return END
    if config.router_first:
        return SUPERVISOR
    return state.get("active") or SUPERVISOR


def _enter(skill_id: str):
    def enter(state: ConversationState) -> dict:
        started = dict(state.get("started") or {})
        already = bool(started.get(skill_id))
        tracker = []
        if not already:
            tracker.append(events.skill_activated(skill_id))
            started[skill_id] = True
        update: dict = {"active": skill_id, "started": started, "events": tracker}
        if already:
            update["messages"] = [
                note(
                    "The customer chose to continue this task. Continue from "
                    "the current state and do not repeat completed steps. If "
                    "they are only signing off or thanking you and the work is "
                    "already done, call finish_task."
                )
            ]
        return update

    return enter


def _session_open(state: ConversationState) -> bool:
    return any(
        event.get("event") == "session_started" for event in state.get("events") or []
    )
