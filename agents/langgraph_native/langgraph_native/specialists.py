"""One ReAct agent per domain, plus the supervisor."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from langgraph_native.config import AgentConfig
from langgraph_native.middleware import SpecialistMiddleware
from langgraph_native.prompts import (
    ACCOUNT_ADVISORY,
    BILL_INQUIRY,
    BILL_UNAVAILABLE,
    CARD_ADVISORY,
    CARD_REPLACE,
    CARD_SELECT,
    ORDER_STATUS,
    SIM_MANAGEMENT,
    SUPERVISOR,
    static_prompt,
)
from langgraph_native.state import (
    ACCOUNT_ADVISORY as ACCOUNT_ID,
)
from langgraph_native.state import (
    BILL_INQUIRY as BILL_ID,
)
from langgraph_native.state import (
    CARD_ADVISORY as CARD_ADVISORY_ID,
)
from langgraph_native.state import (
    CARD_DISAMBIGUATE,
    ConversationState,
    IncidentReason,
    ReplacementReason,
    ReplaceTarget,
    ShippingType,
    SimType,
    WalletProvider,
)
from langgraph_native.state import (
    CARD_REPLACE as CARD_ID,
)
from langgraph_native.state import (
    ORDER_STATUS as ORDER_ID,
)
from langgraph_native.state import (
    SIM_MANAGEMENT as SIM_ID,
)
from langgraph_native.tooling import (
    SUPERVISOR as SUPERVISOR_NODE,
)
from langgraph_native.tooling import (
    NoArgs,
    ToolSpec,
    cancel_tool,
    cannot_help_tool,
    finish_tool,
    handoff_tool,
    make_tool,
    note,
    search_tool,
    transfer_back_tool,
)
from langgraph_native.tools import (
    account_advisory,
    card_advisory,
    card_replace,
    card_select,
    order_status,
)
from langgraph_native.tools import sim_management as sim_tools
from langgraph_native.tools.card_replace import GATES as CARD_GATES
from langgraph_native.tools.sim_management import SIM_NAMES

BLOCK_FLOW = "block_check"


class _Reason(BaseModel):
    reason: ReplacementReason = Field(
        description="lost, stolen, damaged, or not_received"
    )


class _Card(BaseModel):
    card_id: str = Field(description="A card id from the card list, such as VISA_001.")


class _Transaction(BaseModel):
    transaction_id: str


class _Verdict(BaseModel):
    all_familiar: bool = Field(
        description="True when the customer says the charges are all theirs."
    )


class _Fraud(BaseModel):
    card_id: str
    transaction_ids: list[str] = Field(
        description="Ids of the charges the customer disputes."
    )


class _Target(BaseModel):
    target: ReplaceTarget = Field(description="customer, authorized_user, or both")


class _Consent(BaseModel):
    wants_lock: bool


class _Wallet(BaseModel):
    card_id: str
    wallet_provider: WalletProvider = Field(description="apple_pay or google_pay")


class _Shipping(BaseModel):
    shipping_type: ShippingType = Field(description="rush or standard")


class _Order(BaseModel):
    card_id: str
    shipping_type: ShippingType = Field(description="rush or standard")


class _Select(BaseModel):
    card_id: str = Field(description="The id from get_customer_cards.")


class _CardName(BaseModel):
    card_name: str


class _TargetCard(BaseModel):
    target_card: str


class _Account(BaseModel):
    account_id: str = Field(description="CHK_001, SAV_001, or MM_001")


class _OptionalAccount(BaseModel):
    account_id: str | None = Field(
        default=None, description="Omit to get every account."
    )


class _OrderId(BaseModel):
    order_id: str


class _Incident(BaseModel):
    reason: IncidentReason = Field(description="lost or stolen")


class _Sim(BaseModel):
    sim_type: SimType = Field(description="nano_sim or esim")


def _run(function: Any):
    def run(memory: dict, arguments: dict) -> Any:
        return function(memory, **arguments)

    return run


def _spec(
    name: str,
    description: str,
    skill_id: str,
    function: Any,
    schema: type[BaseModel] = NoArgs,
    **extra: Any,
) -> BaseTool:
    return make_tool(
        ToolSpec(
            name=name,
            description=description,
            skill_id=skill_id,
            run=_run(function),
            args_schema=schema,
            **extra,
        )
    )


def _agent(
    model: BaseChatModel,
    config: AgentConfig,
    skill_id: str | None,
    body: str,
    tools: list[BaseTool],
    gates: dict | None = None,
    mcp_tools: frozenset[str] = frozenset(),
) -> CompiledStateGraph:
    return create_agent(
        model,
        tools=tools,
        system_prompt=static_prompt(config, body),
        state_schema=ConversationState,
        middleware=[SpecialistMiddleware(config, skill_id, gates, mcp_tools)],
        name=skill_id or "supervisor",
    )


def _shared(skill_id: str) -> list[BaseTool]:
    return [
        search_tool(),
        finish_tool(skill_id),
        transfer_back_tool(skill_id),
        cancel_tool(skill_id),
    ]


def build_specialists(
    model: BaseChatModel,
    config: AgentConfig,
    mcp_tools: list[BaseTool],
) -> dict[str, CompiledStateGraph]:
    """Returns the supervisor and one agent per domain, keyed by node name."""
    card_tools = [
        _spec(
            "check_account_eligibility",
            "Check whether the account can have a card replaced.",
            CARD_ID,
            card_replace.check_account_eligibility,
        ),
        _spec(
            "record_reason",
            "Record why the card is being replaced.",
            CARD_ID,
            card_replace.record_reason,
            _Reason,
        ),
        handoff_tool(
            "choose_card",
            "Hand off to card selection. Do not ask which card yourself.",
            CARD_DISAMBIGUATE,
        ),
        _spec(
            "check_card_eligibility",
            "Check whether this card can be replaced.",
            CARD_ID,
            card_replace.check_card_eligibility,
            _Card,
        ),
        _spec(
            "load_recent_transactions",
            "Load the recent charges and show them to the customer.",
            CARD_ID,
            card_replace.load_recent_transactions,
            _Card,
        ),
        _spec(
            "get_transaction_details",
            "Get one charge by its id.",
            CARD_ID,
            card_replace.get_transaction_details,
            _Transaction,
        ),
        _spec(
            "record_transactions_verdict",
            "Record whether the charges look familiar.",
            CARD_ID,
            card_replace.record_transactions_verdict,
            _Verdict,
        ),
        _spec(
            "report_fraudulent_transactions",
            "Report the charges the customer says are not theirs.",
            CARD_ID,
            card_replace.report_fraudulent_transactions,
            _Fraud,
        ),
        _spec(
            "check_damaged_replacement_scope",
            "Check for authorized users on a damaged card.",
            CARD_ID,
            card_replace.check_damaged_replacement_scope,
            _Card,
        ),
        _spec(
            "record_replace_target",
            "Record who needs the damaged card replaced.",
            CARD_ID,
            card_replace.record_replace_target,
            _Target,
        ),
        _spec(
            "record_lock_consent",
            "Record whether the customer wants the card locked.",
            CARD_ID,
            card_replace.record_lock_consent,
            _Consent,
        ),
        _spec("lock_card", "Lock the card.", CARD_ID, card_replace.lock_card, _Card),
        _spec(
            "check_wallet_eligibility_and_status",
            "Check digital-wallet eligibility for this card.",
            CARD_ID,
            card_replace.check_wallet_eligibility_and_status,
            _Card,
        ),
        _spec(
            "provision_digital_wallet",
            "Add the card to Apple Pay or Google Pay.",
            CARD_ID,
            card_replace.provision_digital_wallet,
            _Wallet,
        ),
        _spec(
            "check_rush_shipping_eligibility",
            "Check whether rush shipping is available.",
            CARD_ID,
            card_replace.check_rush_shipping_eligibility,
            _Card,
        ),
        _spec(
            "record_shipping_type",
            "Record rush or standard shipping.",
            CARD_ID,
            card_replace.record_shipping_type,
            _Shipping,
        ),
        _spec(
            "process_card_replacement",
            "Place the replacement order. Do not ask the customer to confirm first.",
            CARD_ID,
            card_replace.process_card_replacement,
            _Order,
            confirm="utter_confirm_order",
            denial="utter_order_cancelled",
            confirm_values=lambda memory, args: {
                "shipping_type": args["shipping_type"]
            },
        ),
        *_shared(CARD_ID),
    ]
    select_tools = [
        _spec(
            "get_customer_cards",
            "Fetch the customer's cards.",
            CARD_DISAMBIGUATE,
            card_select.get_customer_cards,
        ),
        _spec(
            "select_card",
            "Record the card the customer means and return to the replacement.",
            CARD_DISAMBIGUATE,
            card_select.select_card,
            _Select,
            goto=CARD_ID,
            completes=True,
        ),
        *_shared(CARD_DISAMBIGUATE),
    ]
    advisory_tools = [
        _spec(
            "get_available_cards",
            "List the cards the bank offers.",
            CARD_ADVISORY_ID,
            card_advisory.get_available_cards,
        ),
        _spec(
            "get_card_details",
            "Get fees, rewards, and benefits for one card.",
            CARD_ADVISORY_ID,
            card_advisory.get_card_details,
            _CardName,
        ),
        _spec(
            "get_spending_summary",
            "Get the customer's spending by category.",
            CARD_ADVISORY_ID,
            card_advisory.get_spending_summary,
        ),
        _spec(
            "get_rewards_earned",
            "Get the rewards earned on the current card.",
            CARD_ADVISORY_ID,
            card_advisory.get_rewards_earned,
        ),
        _spec(
            "calculate_rewards_projection",
            "Project rewards on another card from their spending.",
            CARD_ADVISORY_ID,
            card_advisory.calculate_rewards_projection,
            _TargetCard,
        ),
        *_shared(CARD_ADVISORY_ID),
    ]
    account_tools = [
        _spec(
            "get_account_balance",
            "Get one account's balance.",
            ACCOUNT_ID,
            account_advisory.get_account_balance,
            _Account,
        ),
        _spec(
            "get_rate_history",
            "Get the last six months of rate changes.",
            ACCOUNT_ID,
            account_advisory.get_rate_history,
            _Account,
        ),
        _spec(
            "get_interest_rates",
            "Get current interest rates.",
            ACCOUNT_ID,
            account_advisory.get_interest_rates,
            _OptionalAccount,
        ),
        *_shared(ACCOUNT_ID),
    ]
    order_tools = [
        _spec(
            "get_orders",
            "Fetch the customer's recent orders.",
            ORDER_ID,
            order_status.get_orders,
        ),
        _spec(
            "get_order_details",
            "Get tracking and delivery details for one order.",
            ORDER_ID,
            order_status.get_order_details,
            _OrderId,
        ),
        *_shared(ORDER_ID),
    ]
    sim_tools_bound = [
        _spec(
            "record_incident",
            "Record lost or stolen and give the matching advice once.",
            SIM_ID,
            sim_tools.record_incident,
            _Incident,
        ),
        _spec(
            "get_device_recovery_status",
            "Check whether Find My is enabled. Lost devices only.",
            SIM_ID,
            sim_tools.get_device_recovery_status,
        ),
        handoff_tool(
            "start_block_sim",
            "Check the SIM, ask the customer, and block it if they agree.",
            BLOCK_FLOW,
        ),
        _spec(
            "get_device_info",
            "Get the IMEI, serial number, and eSIM support. Speaks them once.",
            SIM_ID,
            sim_tools.get_device_info,
        ),
        _spec(
            "record_sim_type",
            "Record the replacement the customer asked for.",
            SIM_ID,
            sim_tools.record_sim_type,
            _Sim,
        ),
        _spec(
            "order_replacement_sim",
            "Order the recorded replacement SIM. Do not ask to confirm first.",
            SIM_ID,
            sim_tools.order_replacement_sim,
            confirm="utter_confirm_sim_order",
            denial="utter_sim_order_cancelled",
            confirm_values=_sim_confirm_values,
        ),
        *_shared(SIM_ID),
    ]
    bill_names = frozenset(tool.name for tool in mcp_tools)
    agents = {
        SUPERVISOR_NODE: _agent(
            model,
            config,
            None,
            SUPERVISOR,
            [*_transfers(), search_tool(), cannot_help_tool()],
        ),
        CARD_ID: _agent(model, config, CARD_ID, CARD_REPLACE, card_tools, CARD_GATES),
        CARD_DISAMBIGUATE: _agent(
            model,
            config,
            CARD_DISAMBIGUATE,
            CARD_SELECT,
            select_tools,
            card_select.GATES,
        ),
        CARD_ADVISORY_ID: _agent(
            model, config, CARD_ADVISORY_ID, CARD_ADVISORY, advisory_tools
        ),
        ACCOUNT_ID: _agent(
            model,
            config,
            ACCOUNT_ID,
            ACCOUNT_ADVISORY,
            account_tools,
            account_advisory.GATES,
        ),
        ORDER_ID: _agent(model, config, ORDER_ID, ORDER_STATUS, order_tools),
        SIM_ID: _agent(
            model, config, SIM_ID, SIM_MANAGEMENT, sim_tools_bound, sim_tools.GATES
        ),
        BILL_ID: _agent(
            model,
            config,
            BILL_ID,
            BILL_INQUIRY if mcp_tools else f"{BILL_INQUIRY}\n\n{BILL_UNAVAILABLE}",
            [*mcp_tools, *_shared(BILL_ID)],
            mcp_tools=bill_names,
        ),
    }
    return agents


def _transfers() -> list[BaseTool]:
    descriptions = {
        CARD_ID: "The customer needs a card replaced.",
        CARD_ADVISORY_ID: "The customer wants advice about a card or its rewards.",
        ACCOUNT_ID: "The customer asks about balances or interest rates.",
        ORDER_ID: "The customer asks about an order or a delivery.",
        SIM_ID: "The customer lost a SIM or phone, or wants it blocked or replaced.",
        BILL_ID: "The customer asks about their mobile bill.",
    }
    return [
        handoff_tool(f"transfer_to_{skill_id}", description, skill_id)
        for skill_id, description in descriptions.items()
    ]


async def load_accounts(state: dict) -> dict:
    """Loads accounts and rates once, then the advisory agent can explore them."""
    import json

    from langgraph_native.tools import account_advisory

    memory = dict(state.get("memory") or {})
    tracker = list(_activation_events(state, ACCOUNT_ID))
    messages = []
    if not account_advisory.GATES["get_account_balance"](memory):
        for name, outcome in (
            ("get_accounts", account_advisory.get_accounts(memory)),
            ("get_interest_rates", account_advisory.get_interest_rates(memory)),
        ):
            tracker.extend(_tool_events(memory, name, outcome))
            memory = {**memory, **outcome.memory}
            messages.append(note(f"{name} returned: {json.dumps(outcome.result)}"))
    started = dict(state.get("started") or {})
    if not started.get(ACCOUNT_ID):
        started[ACCOUNT_ID] = True
    return {
        "active": ACCOUNT_ID,
        "started": started,
        "memory": memory,
        "events": tracker,
        "messages": messages,
    }


def _activation_events(state: dict, skill_id: str) -> list:
    from langgraph_native import events

    if (state.get("started") or {}).get(skill_id):
        return []
    return [events.skill_activated(skill_id)]


def _tool_events(before: dict, name: str, outcome: Any) -> list:
    import json

    from langgraph_native import events
    from langgraph_native.state import memory_set_events

    return [
        events.tool_executed(
            name,
            {},
            json.dumps(outcome.result),
            is_error=False,
            skill_id=ACCOUNT_ID,
        ),
        *memory_set_events(before, outcome.memory),
    ]


def _sim_confirm_values(memory: dict, arguments: dict) -> dict:
    from langgraph_native.state import SimManagement

    sim_type = SimManagement.view(memory).sim_type or ""
    return {"sim_name": SIM_NAMES.get(sim_type, sim_type)}
