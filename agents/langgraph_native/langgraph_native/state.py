"""Domain state and the reducers for the graph's shared channels.

Domain state lives in one flat ``memory`` dict keyed ``<skill id>.<field>``,
the names Mantle uses, so ``memory_set`` events match what the scenario
assertions read. Each domain has a Pydantic model that reads its fields from
that dict and validates writes to it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any, ClassVar, Literal, Optional, Self

from langchain.agents import AgentState
from pydantic import BaseModel, ConfigDict

from langgraph_native import events
from langgraph_native.events import Event

CARD_REPLACE = "card_replace"
CARD_DISAMBIGUATE = "card_disambiguate"
CARD_ADVISORY = "card_advisory"
ACCOUNT_ADVISORY = "account_advisory"
ORDER_STATUS = "order_status"
BILL_INQUIRY = "bill_inquiry"
SIM_MANAGEMENT = "sim_management"

ReplacementReason = Literal["lost", "stolen", "damaged", "not_received"]
ReplaceTarget = Literal["customer", "authorized_user", "both"]
ShippingType = Literal["rush", "standard"]
WalletProvider = Literal["apple_pay", "google_pay"]
IncidentReason = Literal["lost", "stolen"]
SimType = Literal["nano_sim", "esim"]


class Domain(BaseModel):
    """One domain's fields, read from and written to the flat memory dict."""

    model_config = ConfigDict(frozen=True)

    skill_id: ClassVar[str]
    # Bookkeeping fields that never appear as memory_set events.
    private_fields: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def view(cls, memory: Mapping[str, Any]) -> Self:
        """Returns this domain's current values from *memory*."""
        prefix = f"{cls.skill_id}."
        return cls.model_validate(
            {name: memory.get(prefix + name) for name in cls.model_fields}
        )

    @classmethod
    def changes(cls, **values: Any) -> dict[str, Any]:
        """Returns a memory update for *values*.

        Raises:
            ValueError: When a name is not a field of this domain.
        """
        unknown = set(values) - set(cls.model_fields)
        if unknown:
            raise ValueError(f"{cls.skill_id} has no fields {sorted(unknown)}")
        return {f"{cls.skill_id}.{name}": value for name, value in values.items()}


class CardReplace(Domain):
    skill_id: ClassVar[str] = CARD_REPLACE
    private_fields: ClassVar[frozenset[str]] = frozenset({"committed_card_id"})

    account_eligible: Optional[bool] = None
    replacement_reason: Optional[ReplacementReason] = None
    selected_card_id: Optional[str] = None
    card_eligible: Optional[bool] = None
    has_authorized_users: Optional[bool] = None
    replace_target: Optional[ReplaceTarget] = None
    damaged_applied: Optional[bool] = None
    transaction_review_complete: Optional[bool] = None
    transactions_look_familiar: Optional[bool] = None
    fraud_reported: Optional[bool] = None
    card_locked: Optional[bool] = None
    wants_card_locked: Optional[bool] = None
    wallet_eligible: Optional[bool] = None
    wallet_already_provisioned: Optional[bool] = None
    wallet_consent: Optional[bool] = None
    wallet_provider: Optional[str] = None
    wallet_provisioned: Optional[bool] = None
    shipping_type: Optional[ShippingType] = None
    rush_eligible: Optional[bool] = None
    replacement_ordered: Optional[bool] = None
    recent_transactions: Optional[list[dict[str, Any]]] = None
    replacement_order_summary: Optional[str] = None
    committed_card_id: Optional[str] = None

    @property
    def reviews_charges(self) -> bool:
        """Test if the reason needs a charge review before locking."""
        return self.replacement_reason in ("lost", "not_received")


class CardDisambiguate(Domain):
    skill_id: ClassVar[str] = CARD_DISAMBIGUATE

    card_list: Optional[list[dict[str, Any]]] = None
    selected_card_id: Optional[str] = None
    selected_card_label: Optional[str] = None


class CardAdvisory(Domain):
    skill_id: ClassVar[str] = CARD_ADVISORY

    card_data_loaded: Optional[bool] = None


class AccountAdvisory(Domain):
    skill_id: ClassVar[str] = ACCOUNT_ADVISORY

    accounts_loaded: Optional[bool] = None


class OrderStatus(Domain):
    skill_id: ClassVar[str] = ORDER_STATUS

    orders_loaded: Optional[bool] = None


class SimManagement(Domain):
    skill_id: ClassVar[str] = SIM_MANAGEMENT
    private_fields: ClassVar[frozenset[str]] = frozenset(
        {"advice_given_for", "ordered_sim_types"}
    )

    incident_reason: Optional[IncidentReason] = None
    sim_blocked: Optional[bool] = None
    wants_to_block: Optional[bool] = None
    replacement_ordered: Optional[bool] = None
    sim_type: Optional[SimType] = None
    sim_order_summary: Optional[str] = None
    device_info_shared: Optional[bool] = None
    device_imei: Optional[str] = None
    device_serial: Optional[str] = None
    device_name: Optional[str] = None
    advice_given_for: Optional[IncidentReason] = None
    ordered_sim_types: Optional[list[SimType]] = None


DOMAINS: dict[str, type[Domain]] = {
    domain.skill_id: domain
    for domain in (
        CardReplace,
        CardDisambiguate,
        CardAdvisory,
        AccountAdvisory,
        OrderStatus,
        SimManagement,
    )
}


def is_private(key: str) -> bool:
    """Test if a memory key is bookkeeping that is not reported as an event."""
    skill_id, _, name = key.partition(".")
    domain = DOMAINS.get(skill_id)
    return domain is not None and name in domain.private_fields


def memory_set_events(
    before: Mapping[str, Any], update: Mapping[str, Any]
) -> list[Event]:
    """Returns one ``memory_set`` event per public key whose value changes."""
    return [
        events.memory_set(key, value)
        for key, value in update.items()
        if not is_private(key) and before.get(key) != value
    ]


def merge_memory(
    left: Optional[dict[str, Any]], right: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """Reducer for ``memory``: later writes win key by key."""
    return {**(left or {}), **(right or {})}


def merge_events(
    left: Optional[list[Event]], right: Optional[list[Event]]
) -> list[Event]:
    """Reducer for ``events``: appends, skipping events already present.

    A specialist that hands off returns its whole event list to the parent
    graph, so the same events can arrive twice; the tracker must keep one.
    """
    merged = list(left or [])
    seen = {_event_key(event) for event in merged}
    for event in right or []:
        key = _event_key(event)
        if key not in seen:
            seen.add(key)
            merged.append(event)
    return merged


def _event_key(event: Event) -> str:
    return json.dumps(event, sort_keys=True, default=str)


class Incoming(BaseModel):
    """What starts a turn: a customer message or the session start."""

    model_config = ConfigDict(frozen=True)

    kind: str
    text: str = ""
    channel: str = "rest"


class ConversationState(AgentState, total=False):
    """Checkpointed state for one conversation.

    ``messages`` comes from :class:`AgentState`. ``memory`` and ``events`` use
    reducers so a specialist's update merges into the conversation instead of
    replacing it. ``paused`` is the open tasks left by a change of subject,
    most recent last.
    """

    memory: Annotated[dict[str, Any], merge_memory]
    events: Annotated[list[Event], merge_events]
    started: Annotated[dict[str, bool], merge_memory]
    paused: list[str]
    active: Optional[str]
    channel: str
    model_calls: int
    incoming: dict[str, Any]
    end_turn: bool
