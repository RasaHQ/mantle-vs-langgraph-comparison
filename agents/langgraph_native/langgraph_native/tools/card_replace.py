"""Card replacement: eligibility, charge review, lock, wallet, shipping, order."""

from __future__ import annotations

from typing import Any

from langgraph_native import mock_data
from langgraph_native.responses import Utterance
from langgraph_native.state import (
    CardReplace,
    ReplacementReason,
    ReplaceTarget,
    ShippingType,
    WalletProvider,
)
from langgraph_native.tools import Gate, Memory, Outcome, error

ORDER_ID = "RPL-2026-001843"
FRAUD_REPORT_ID = "FRD-2026-004291"
_WALLET_NAMES = {"apple_pay": "Apple Pay", "google_pay": "Google Pay"}
_STANDARD_DELIVERY = "5-7 business days"
_RUSH_DELIVERY = "1-2 business days"

# Fields that only hold for the card they were collected for.
_CARD_DEPENDENT_FIELDS = (
    "card_eligible",
    "has_authorized_users",
    "replace_target",
    "damaged_applied",
    "transaction_review_complete",
    "transactions_look_familiar",
    "fraud_reported",
    "card_locked",
    "wants_card_locked",
    "wallet_eligible",
    "wallet_already_provisioned",
    "wallet_consent",
    "wallet_provider",
    "wallet_provisioned",
    "wallet_declined",
    "shipping_type",
    "rush_eligible",
    "replacement_ordered",
    "recent_transactions",
    "replacement_order_summary",
)


def _card(card_id: str) -> dict[str, Any] | None:
    return mock_data.CARDS.get(card_id)


def _unknown_card(card_id: str) -> Outcome:
    return error(f"Card '{card_id}' not found.", valid_ids=list(mock_data.CARDS))


def adopt_card(memory: Memory, card_id: str) -> dict[str, Any]:
    """Returns the memory update that makes *card_id* the card being replaced.

    Switching to a different card clears everything collected for the old
    one; re-selecting the same card keeps it.
    """
    state = CardReplace.view(memory)
    update = CardReplace.changes(selected_card_id=card_id, committed_card_id=card_id)
    if state.committed_card_id is not None and state.committed_card_id != card_id:
        update.update(
            CardReplace.changes(**{name: None for name in _CARD_DEPENDENT_FIELDS})
        )
    return update


def check_account_eligibility(memory: Memory) -> Outcome:
    info = mock_data.ACCOUNT_REPLACEMENT_ELIGIBILITY
    return Outcome(
        result=dict(info), memory=CardReplace.changes(account_eligible=info["eligible"])
    )


def record_reason(memory: Memory, reason: ReplacementReason) -> Outcome:
    return Outcome(
        result={"ok": True, "replacement_reason": reason},
        memory=CardReplace.changes(replacement_reason=reason),
    )


def check_card_eligibility(memory: Memory, card_id: str) -> Outcome:
    card = _card(card_id)
    if card is None:
        outcome = _unknown_card(card_id)
        return outcome.model_copy(
            update={"memory": CardReplace.changes(card_eligible=False)}
        )
    eligible = bool(card["eligible_for_replacement"])
    return Outcome(
        result={
            "card_id": card_id,
            "card_label": card["label"],
            "eligible": eligible,
            "replacement_fee": card["replacement_fee"],
        },
        memory=CardReplace.changes(card_eligible=eligible),
    )


def check_damaged_replacement_scope(memory: Memory, card_id: str) -> Outcome:
    card = _card(card_id)
    if card is None:
        return _unknown_card(card_id)
    authorized_users = card.get("authorized_users", [])
    has_authorized_users = len(authorized_users) > 0
    return Outcome(
        result={
            "card_id": card_id,
            "has_authorized_users": has_authorized_users,
            "authorized_users": authorized_users,
        },
        memory=CardReplace.changes(has_authorized_users=has_authorized_users),
    )


def record_replace_target(memory: Memory, target: ReplaceTarget) -> Outcome:
    return Outcome(
        result={"ok": True, "replace_target": target},
        memory=CardReplace.changes(replace_target=target, damaged_applied=True),
    )


def load_recent_transactions(memory: Memory, card_id: str) -> Outcome:
    card = _card(card_id)
    card_label = card["label"] if card else card_id
    transactions = mock_data.TRANSACTIONS_BY_CARD.get(card_id) or mock_data.TRANSACTIONS
    summary = [
        {
            "id": tx["id"],
            "date": tx["date"],
            "merchant": tx["merchant"],
            "amount": tx["amount"],
        }
        for tx in transactions
    ]
    return Outcome(
        result={"card_label": card_label, "transactions": summary},
        memory=CardReplace.changes(recent_transactions=list(transactions)),
    )


def get_transaction_details(memory: Memory, transaction_id: str) -> Outcome:
    detail = mock_data.TRANSACTION_DETAILS.get(transaction_id)
    if detail is None:
        return error(
            f"Transaction '{transaction_id}' not found.",
            valid_ids=list(mock_data.TRANSACTION_DETAILS),
        )
    return Outcome(result=dict(detail))


def record_transactions_verdict(memory: Memory, all_familiar: bool) -> Outcome:
    return Outcome(
        result={"ok": True, "all_familiar": all_familiar},
        memory=CardReplace.changes(
            transactions_look_familiar=all_familiar, transaction_review_complete=True
        ),
    )


def report_fraudulent_transactions(
    memory: Memory, card_id: str, transaction_ids: list[str]
) -> Outcome:
    ids = [tid.strip() for tid in transaction_ids if tid.strip()]
    if not ids:
        return error("No transaction IDs provided.")
    return Outcome(
        result={
            "ok": True,
            "card_id": card_id,
            "reported_transaction_ids": ids,
            "report_id": FRAUD_REPORT_ID,
        },
        memory=CardReplace.changes(fraud_reported=True),
    )


def record_lock_consent(memory: Memory, wants_lock: bool) -> Outcome:
    return Outcome(
        result={"ok": True, "wants_card_locked": wants_lock},
        memory=CardReplace.changes(wants_card_locked=wants_lock),
    )


def record_lock_declined(memory: Memory) -> Outcome:
    return Outcome(
        result={"ok": True, "wants_card_locked": False},
        memory=CardReplace.changes(wants_card_locked=False),
    )


def lock_card(memory: Memory, card_id: str) -> Outcome:
    """Locks the card. For a lost or not-received card the tool asked first."""
    card = _card(card_id)
    update = CardReplace.changes(card_locked=True)
    if _view(memory).reviews_charges:
        update.update(CardReplace.changes(wants_card_locked=True))
    return Outcome(
        result={
            "success": True,
            "card_id": card_id,
            "card_label": card["label"] if card else card_id,
            "locked": True,
        },
        memory=update,
        say=[Utterance(name="utter_card_locked")],
    )


def check_wallet_eligibility_and_status(memory: Memory, card_id: str) -> Outcome:
    card = _card(card_id)
    if card is None:
        return _unknown_card(card_id)
    eligible = bool(card.get("digital_wallet_eligible", False))
    already = bool(card.get("already_provisioned", False))
    return Outcome(
        result={
            "card_id": card_id,
            "wallet_eligible": eligible,
            "already_provisioned": already,
        },
        memory=CardReplace.changes(
            wallet_eligible=eligible, wallet_already_provisioned=already
        ),
    )


def named_wallet(text: str) -> WalletProvider | None:
    """Returns the wallet the customer named in *text*, if any."""
    lowered = text.lower()
    if "apple" in lowered:
        return "apple_pay"
    if "google" in lowered:
        return "google_pay"
    return None


def provision_digital_wallet(
    memory: Memory, card_id: str, wallet_provider: WalletProvider | None = None
) -> Outcome:
    """Adds the card to a wallet. The tool asked the customer first."""
    card = _card(card_id)
    if card is None:
        return _unknown_card(card_id)
    if not card.get("digital_wallet_eligible") or card.get("already_provisioned"):
        return error("wallet_not_available", hint="Skip to shipping.")
    if wallet_provider is None:
        return error(
            "wallet_not_named",
            hint=(
                "The customer wants a wallet but did not say which. Ask whether "
                "Apple Pay or Google Pay, then call provision_digital_wallet "
                "with it."
            ),
        )
    wallet = _WALLET_NAMES[wallet_provider]
    return Outcome(
        result={
            "success": True,
            "card_id": card_id,
            "wallet": wallet,
            "available_in": "2-3 minutes",
        },
        memory=CardReplace.changes(
            wallet_provider=wallet_provider,
            wallet_consent=True,
            wallet_provisioned=True,
        ),
    )


def record_wallet_declined(memory: Memory) -> Outcome:
    return Outcome(
        result={"ok": True, "wallet": "declined"},
        memory=CardReplace.changes(wallet_declined=True),
    )


def check_rush_shipping_eligibility(memory: Memory, card_id: str) -> Outcome:
    card = _card(card_id)
    if card is None:
        return _unknown_card(card_id)
    rush_eligible = bool(card.get("rush_shipping_eligible", False))
    return Outcome(
        result={
            "card_id": card_id,
            "rush_eligible": rush_eligible,
            "rush_fee": card.get("rush_shipping_fee", 0),
            "standard_delivery": card.get(
                "estimated_delivery_standard", _STANDARD_DELIVERY
            ),
            "rush_delivery": card.get("estimated_delivery_rush", _RUSH_DELIVERY),
        },
        memory=CardReplace.changes(rush_eligible=rush_eligible),
    )


def record_shipping_type(memory: Memory, shipping_type: ShippingType) -> Outcome:
    if shipping_type == "rush" and CardReplace.view(memory).rush_eligible is not True:
        return error(
            "rush_not_eligible",
            hint="This card cannot ship rush. Tell the customer and record standard.",
        )
    return Outcome(
        result={"ok": True, "shipping_type": shipping_type},
        memory=CardReplace.changes(shipping_type=shipping_type),
    )


def process_card_replacement(
    memory: Memory, card_id: str, shipping_type: ShippingType
) -> Outcome:
    if shipping_type == "rush" and CardReplace.view(memory).rush_eligible is not True:
        return error("rush_not_eligible", hint="Use standard shipping.")
    card = _card(card_id)
    card_label = card["label"] if card else card_id
    if shipping_type == "rush":
        delivery = (card or {}).get("estimated_delivery_rush", _RUSH_DELIVERY)
    else:
        delivery = (card or {}).get("estimated_delivery_standard", _STANDARD_DELIVERY)
    summary = (
        f"Order ID: {ORDER_ID}\n"
        f"Card: {card_label}\n"
        f"Shipping: {shipping_type}\n"
        f"Estimated delivery: {delivery}"
    )
    return Outcome(
        result={
            "success": True,
            "order_id": ORDER_ID,
            "card_label": card_label,
            "shipping_type": shipping_type,
            "estimated_delivery": delivery,
        },
        memory=CardReplace.changes(
            shipping_type=shipping_type,
            replacement_ordered=True,
            replacement_order_summary=summary,
        ),
        say=[
            Utterance(
                name="utter_card_replace_complete",
                values={
                    "card_label": card_label,
                    "shipping_type": shipping_type,
                    "order_id": ORDER_ID,
                    "delivery": delivery,
                },
            )
        ],
    )


def _view(memory: Memory) -> CardReplace:
    return CardReplace.view(memory)


def _can_lock(state: CardReplace) -> bool:
    if state.replacement_reason == "stolen":
        return True
    # lock_card asks the customer itself, so the model cannot give consent.
    return (
        state.reviews_charges
        and state.wants_card_locked is not False
        and state.transactions_look_familiar is not None
    )


def lock_needs_consent(memory: Memory) -> bool:
    """Test if lock_card must ask first: every reason but stolen."""
    return _view(memory).replacement_reason != "stolen"


def _lock_settled(state: CardReplace) -> bool:
    """Test if the lock step is done, as Mantle's order constraint requires."""
    if state.replacement_reason == "damaged":
        return True
    if state.card_locked is True:
        return True
    return state.wants_card_locked is False and state.replacement_reason != "stolen"


def _wallet_settled(state: CardReplace) -> bool:
    """Test if the wallet step is done, so shipping can start."""
    return state.wallet_eligible is False or bool(
        state.wallet_already_provisioned
        or state.wallet_provisioned
        or state.wallet_declined
    )


def can_finish(memory: Memory) -> bool:
    """Test if the replacement is done, or cannot go ahead at all."""
    state = _view(memory)
    if state.account_eligible is False or state.card_eligible is False:
        return True
    return state.replacement_ordered is True and (
        state.transaction_review_complete is True or not state.reviews_charges
    )


GATES: dict[str, Gate] = {
    "check_account_eligibility": lambda m: _view(m).account_eligible is None,
    "choose_card": lambda m: _view(m).account_eligible is True,
    "check_card_eligibility": lambda m: _view(m).selected_card_id is not None,
    "load_recent_transactions": lambda m: _view(m).card_eligible is True,
    "get_transaction_details": lambda m: bool(_view(m).recent_transactions),
    "record_transactions_verdict": lambda m: bool(_view(m).recent_transactions),
    "report_fraudulent_transactions": (
        lambda m: _view(m).transaction_review_complete is True
    ),
    "check_damaged_replacement_scope": (
        lambda m: (
            _view(m).replacement_reason == "damaged" and _view(m).card_eligible is True
        )
    ),
    "record_replace_target": (
        lambda m: (
            _view(m).replacement_reason == "damaged"
            and _view(m).has_authorized_users is True
        )
    ),
    "record_lock_declined": (
        lambda m: _view(m).reviews_charges and _view(m).card_locked is not True
    ),
    "lock_card": lambda m: _can_lock(_view(m)),
    "check_wallet_eligibility_and_status": lambda m: _view(m).card_eligible is True,
    "provision_digital_wallet": (
        lambda m: _view(m).wallet_eligible is True and not _wallet_settled(_view(m))
    ),
    "record_wallet_declined": (
        lambda m: _view(m).wallet_eligible is True and not _wallet_settled(_view(m))
    ),
    "check_rush_shipping_eligibility": (
        lambda m: _view(m).card_eligible is True and _wallet_settled(_view(m))
    ),
    "record_shipping_type": (
        lambda m: _view(m).rush_eligible is not None and _wallet_settled(_view(m))
    ),
    "process_card_replacement": (
        lambda m: (
            _view(m).card_eligible is True
            and _wallet_settled(_view(m))
            and _view(m).shipping_type is not None
            and _view(m).rush_eligible is not None
            and _view(m).replacement_ordered is not True
            and _lock_settled(_view(m))
        )
    ),
    "finish_task": can_finish,
}
