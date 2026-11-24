"""Card replacement tools for mantle_combined agent."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from rasa.mantle.tools.decorator import ToolContext, tool
from rasa.mantle.tools.result import ToolResult

_VALID_REASONS = frozenset({"lost", "stolen", "damaged", "not_received"})
_VALID_WALLETS = frozenset({"apple_pay", "google_pay"})
_VALID_REPLACE_TARGETS = frozenset({"customer", "authorized_user", "both"})
_VALID_SHIPPING = frozenset({"rush", "standard"})


def _load_mock_data():
    data_path = Path(__file__).resolve().parents[2] / "lib" / "mock_data.py"
    spec = importlib.util.spec_from_file_location("mock_data", data_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load mock data from {data_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_data = _load_mock_data()

# Own-skill fields that are only valid for the currently selected card.
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
    "shipping_type",
    "rush_eligible",
    "replacement_ordered",
    "recent_transactions",
    "replacement_order_summary",
)


def _reset_card_dependent_fields(context: ToolContext) -> None:
    for name in _CARD_DEPENDENT_FIELDS:
        context.memory.set(name, None)


def _commit_selected_card(context: ToolContext, selected_id: str) -> bool:
    previous_id = context.memory.get("committed_card_id")
    card_changed = previous_id is not None and previous_id != selected_id
    context.memory.set("selected_card_id", selected_id)
    if card_changed:
        _reset_card_dependent_fields(context)
    context.memory.set("committed_card_id", selected_id)
    return card_changed


@tool(
    description=(
        "Copy card_disambiguate.selected_card_id into this skill. Call after "
        "card_disambiguate completes, and again if that skill runs because the "
        "customer switched cards. Then call check_card_eligibility before "
        "authorized users, the wallet, shipping, or the order. Clears this "
        "skill's wallet, charges, lock, and shipping state only on a real "
        "card switch."
    )
)
async def adopt_selected_card(context: ToolContext = None) -> ToolResult:
    selected_id = context.memory.get("card_disambiguate.selected_card_id")
    if not selected_id or selected_id not in _data.CARDS:
        return ToolResult(
            llm_response={
                "ok": False,
                "error": "no_selected_card",
                "hint": "Run @skill.card_disambiguate first, then call this tool.",
            }
        )
    card_changed = _commit_selected_card(context, str(selected_id))
    card = _data.CARDS[selected_id]
    response: dict = {
        "ok": True,
        "selected_card_id": selected_id,
        "selected_card_label": card["label"],
    }
    if card_changed:
        response["card_changed"] = True
        response["hint"] = (
            "Selected card changed. Re-run card eligibility and fraud review "
            "(load_recent_transactions) for the new card. Do not reuse the "
            "old card's charges, wallet, or shipping. A lock already "
            "completed on the previous card stays completed, and you cannot "
            "unlock it."
        )
    return ToolResult(llm_response=response)


@tool(
    description="Post-write hook: reset card-tied state when this skill's card id changes."
)
async def run_after_setting_selected_card_id(
    context: ToolContext = None,
) -> ToolResult:
    selected_id = context.memory.get("selected_card_id")
    if not selected_id or selected_id not in _data.CARDS:
        context.memory.set("selected_card_id", None)
        return ToolResult(
            llm_response={
                "ok": False,
                "error": "invalid_card_id",
                "hint": "Use a card id from the card list (e.g. VISA_001).",
            }
        )
    # adopt_selected_card already committed this id; skip a second reset.
    if context.memory.get("committed_card_id") == selected_id:
        card = _data.CARDS[selected_id]
        return ToolResult(
            llm_response={
                "ok": True,
                "selected_card_id": selected_id,
                "selected_card_label": card["label"],
            }
        )
    card_changed = _commit_selected_card(context, str(selected_id))
    card = _data.CARDS[selected_id]
    response: dict = {
        "ok": True,
        "selected_card_id": selected_id,
        "selected_card_label": card["label"],
    }
    if card_changed:
        response["card_changed"] = True
        response["hint"] = (
            "Selected card changed. Re-run card eligibility and fraud review "
            "(load_recent_transactions) for the new card. Do not reuse the "
            "old card's charges, wallet, or shipping. A lock already "
            "completed on the previous card stays completed, and you cannot "
            "unlock it."
        )
    return ToolResult(llm_response=response)


@tool(
    description="Check whether the customer's account is eligible for a card replacement."
)
async def check_account_eligibility(context: ToolContext = None) -> ToolResult:
    info = _data.ACCOUNT_REPLACEMENT_ELIGIBILITY
    context.memory.set("account_eligible", info["eligible"])
    return ToolResult(llm_response=info)


@tool(description="Post-write hook: validate the replacement reason.")
async def run_after_setting_replacement_reason(
    context: ToolContext = None,
) -> ToolResult:
    raw = context.memory.get("replacement_reason")
    reason = raw.strip().lower() if isinstance(raw, str) else raw
    if reason not in _VALID_REASONS:
        return ToolResult(
            llm_response={
                "ok": False,
                "error": "invalid_reason",
                "valid_values": sorted(_VALID_REASONS),
            }
        )
    if reason != raw:
        context.memory.set("replacement_reason", reason)
    return ToolResult(llm_response={"ok": True, "replacement_reason": reason})


@tool(
    description=(
        "Check whether a specific card is eligible for replacement. "
        "Pass the card_id (e.g. VISA_001, MC_002)."
    )
)
async def check_card_eligibility(
    card_id: str, context: ToolContext = None
) -> ToolResult:
    card = _data.CARDS.get(card_id)
    if card is None:
        context.memory.set("card_eligible", False)
        return ToolResult(
            llm_response={
                "ok": False,
                "error": f"Card '{card_id}' not found.",
                "valid_ids": list(_data.CARDS.keys()),
            }
        )
    eligible = card["eligible_for_replacement"]
    fee = float(card["replacement_fee"])
    context.memory.set("card_eligible", eligible)
    return ToolResult(
        llm_response={
            "card_id": card_id,
            "card_label": card["label"],
            "eligible": eligible,
            "replacement_fee": card["replacement_fee"],
        }
    )


@tool(
    description=(
        "Check whether the card has authorized users who may also need a "
        "replacement."
    )
)
async def check_damaged_replacement_scope(
    card_id: str, context: ToolContext = None
) -> ToolResult:
    card = _data.CARDS.get(card_id)
    if card is None:
        return ToolResult(
            llm_response={"ok": False, "error": f"Card '{card_id}' not found."}
        )
    authorized_users = card.get("authorized_users", [])
    has_auth = len(authorized_users) > 0
    context.memory.set("has_authorized_users", has_auth)
    return ToolResult(
        llm_response={
            "card_id": card_id,
            "has_authorized_users": has_auth,
            "authorized_users": authorized_users,
        }
    )


@tool(
    description=(
        "Post-write hook: validate replace_target and mark damaged scope applied."
    )
)
async def run_after_setting_replace_target(context: ToolContext = None) -> ToolResult:
    raw = context.memory.get("replace_target")
    target = raw.strip().lower() if isinstance(raw, str) else raw
    if target not in _VALID_REPLACE_TARGETS:
        return ToolResult(
            llm_response={
                "ok": False,
                "error": "invalid_replace_for",
                "valid_values": sorted(_VALID_REPLACE_TARGETS),
            }
        )
    if target != raw:
        context.memory.set("replace_target", target)
    context.memory.set("damaged_applied", True)
    return ToolResult(llm_response={"ok": True, "replace_for": target})


@tool(
    description=(
        "Load the most recent transactions on a card for fraud review. "
        "Show the returned list to the customer and ask if all charges look familiar."
    )
)
async def load_recent_transactions(
    card_id: str, context: ToolContext = None
) -> ToolResult:
    card = _data.CARDS.get(card_id)
    card_label = card["label"] if card else card_id
    transactions = _data.TRANSACTIONS_BY_CARD.get(card_id) or _data.TRANSACTIONS
    display_lines = [
        f"{tx['date']} — {tx['merchant']} — ${tx['amount']:.2f}" for tx in transactions
    ]
    display_text = f"Recent charges on {card_label}:\n" + "\n".join(
        f"- {line}" for line in display_lines
    )
    context.memory.set("recent_transactions", transactions)
    return ToolResult(
        llm_response={
            "card_label": card_label,
            "transactions": [
                {
                    "id": tx["id"],
                    "date": tx["date"],
                    "merchant": tx["merchant"],
                    "amount": tx["amount"],
                }
                for tx in transactions
            ],
            "transactions_display_text": display_text,
            "hint": (
                "Present transactions_display_text to the customer once, then "
                "ask whether all charges look familiar. Do not invent charges. "
                "Record the verdict with "
                "@tool.set_memory(transactions_look_familiar=...)."
            ),
        }
    )


@tool(
    description=(
        "Get detailed information about a specific transaction by ID. "
        "Use when the customer asks about a particular charge. "
        "Valid IDs depend on the card (e.g. txn_001–txn_005 for River Visa, "
        "txn_101–txn_105 for Summit Rewards)."
    )
)
async def get_transaction_details(
    transaction_id: str, context: ToolContext = None
) -> ToolResult:
    detail = _data.TRANSACTION_DETAILS.get(transaction_id)
    if detail is None:
        return ToolResult(
            llm_response={
                "ok": False,
                "error": f"Transaction '{transaction_id}' not found.",
                "valid_ids": list(_data.TRANSACTION_DETAILS.keys()),
            }
        )
    return ToolResult(llm_response=detail)


@tool(description="Post-write hook: mark transaction review complete.")
async def run_after_setting_transactions_look_familiar(
    context: ToolContext = None,
) -> ToolResult:
    if not context.memory.get("recent_transactions"):
        return ToolResult(
            llm_response={
                "error": "transactions_not_loaded",
                "hint": (
                    "Call load_recent_transactions before recording "
                    "transactions_look_familiar via set_memory."
                ),
            }
        )
    context.memory.set("transaction_review_complete", True)
    familiar = context.memory.get("transactions_look_familiar")
    return ToolResult(llm_response={"ok": True, "all_familiar": familiar})


@tool(
    description=(
        "Report one or more transactions as fraudulent. Pass transaction_ids "
        "as a list of transaction ids, for example ['txn_001', 'txn_002']."
    )
)
async def report_fraudulent_transactions(
    card_id: str, transaction_ids: list[str], context: ToolContext = None
) -> ToolResult:
    ids = [
        tid.strip() for tid in transaction_ids if isinstance(tid, str) and tid.strip()
    ]
    if not ids:
        return ToolResult(
            llm_response={"ok": False, "error": "No transaction IDs provided."}
        )
    report_id = "FRD-2026-004291"
    context.memory.set("fraud_reported", True)
    return ToolResult(
        llm_response={
            "ok": True,
            "card_id": card_id,
            "reported_transaction_ids": ids,
            "report_id": report_id,
            "message": f"Fraud report filed for {len(ids)} transaction(s).",
        }
    )


@tool(
    description=(
        "Lock this card after customer consent, or immediately if stolen (no consent). Once locked you cannot reverse the lock."
    )
)
async def lock_card(card_id: str, context: ToolContext = None) -> ToolResult:
    card = _data.CARDS.get(card_id)
    card_label = card["label"] if card else card_id
    context.memory.set("card_locked", True)
    return ToolResult(
        llm_response={
            "success": True,
            "card_id": card_id,
            "card_label": card_label,
            "locked": True,
            "effective": "Immediately",
            "message": (
                f"{card_label} was locked. No further transactions will be "
                "authorized."
            ),
        }
    )


@tool(
    description=(
        "Check whether the card is eligible for digital wallet provisioning "
        "and whether it has already been provisioned. Call this before "
        "offering wallet provisioning."
    )
)
async def check_wallet_eligibility_and_status(
    card_id: str, context: ToolContext = None
) -> ToolResult:
    card = _data.CARDS.get(card_id)
    if card is None:
        return ToolResult(
            llm_response={"ok": False, "error": f"Card '{card_id}' not found."}
        )
    eligible = card.get("digital_wallet_eligible", False)
    already = card.get("already_provisioned", False)
    context.memory.set("wallet_eligible", eligible)
    context.memory.set("wallet_already_provisioned", already)
    response: dict = {
        "card_id": card_id,
        "wallet_eligible": eligible,
        "already_provisioned": already,
    }
    lock_question_open = (
        context.memory.get("replacement_reason") in ("lost", "not_received")
        and context.memory.get("card_locked") is not True
        and context.memory.get("wants_card_locked") is None
    )
    if eligible and not already and lock_question_open:
        response["hint"] = (
            "The lock question comes first. Ask whether they want this card "
            "locked and wait for the answer. Offer the wallet after that, "
            "unless they already asked for a wallet."
        )
    elif eligible and not already:
        response["hint"] = (
            "Next, ask only whether they want the new card added to Apple Pay "
            "or Google Pay, then wait for the answer. Do not check or mention "
            "shipping in this reply. If they already named a wallet, add it "
            "with provision_digital_wallet instead of asking."
        )
    else:
        response["hint"] = "No wallet offer for this card. Continue to shipping."
    return ToolResult(llm_response=response)


@tool(
    description=(
        "Add the replacement card to a digital wallet for immediate use. "
        "wallet_provider must be 'apple_pay' or 'google_pay'."
    )
)
async def provision_digital_wallet(
    card_id: str, wallet_provider: str, context: ToolContext = None
) -> ToolResult:
    wp = wallet_provider.lower().strip()
    if wp not in _VALID_WALLETS:
        return ToolResult(
            llm_response={
                "ok": False,
                "error": "invalid_wallet_provider",
                "valid_values": sorted(_VALID_WALLETS),
            }
        )
    card = _data.CARDS.get(card_id)
    if card is None:
        return ToolResult(
            llm_response={"ok": False, "error": f"Card '{card_id}' not found."}
        )
    if not card.get("digital_wallet_eligible", False) or card.get(
        "already_provisioned", False
    ):
        return ToolResult(
            llm_response={
                "error": "wallet_not_available",
                "hint": "Skip to shipping.",
            }
        )
    wallet_names = {"apple_pay": "Apple Pay", "google_pay": "Google Pay"}
    available_in = "2-3 minutes"
    context.memory.set("wallet_provider", wp)
    context.memory.set("wallet_consent", True)
    context.memory.set("wallet_provisioned", True)
    return ToolResult(
        llm_response={
            "success": True,
            "card_id": card_id,
            "wallet": wallet_names[wp],
            "available_in": available_in,
            "message": (
                f"Card provisioned to {wallet_names[wp]}. It will be "
                "available in your Wallet app within a few minutes."
            ),
        }
    )


@tool(
    description=(
        "Check whether the card is eligible for rush shipping and return "
        "the available shipping options with fees and delivery estimates."
    )
)
async def check_rush_shipping_eligibility(
    card_id: str, context: ToolContext = None
) -> ToolResult:
    card = _data.CARDS.get(card_id)
    if card is None:
        return ToolResult(
            llm_response={"ok": False, "error": f"Card '{card_id}' not found."}
        )
    rush_eligible = bool(card.get("rush_shipping_eligible", False))
    context.memory.set("rush_eligible", rush_eligible)
    return ToolResult(
        llm_response={
            "card_id": card_id,
            "rush_eligible": rush_eligible,
            "rush_fee": card.get("rush_shipping_fee", 0),
            "standard_delivery": card.get(
                "estimated_delivery_standard", "5-7 business days"
            ),
            "rush_delivery": card.get("estimated_delivery_rush", "1-2 business days"),
        }
    )


@tool(
    description=(
        "Place the replacement card order. shipping_type must be 'rush' or "
        "'standard'. Call this only after the customer confirms the order."
    )
)
async def process_card_replacement(
    card_id: str, shipping_type: str, context: ToolContext = None
) -> ToolResult:
    st = shipping_type.lower().strip()
    if st not in _VALID_SHIPPING:
        return ToolResult(
            llm_response={
                "ok": False,
                "error": "invalid_shipping_type",
                "valid_values": sorted(_VALID_SHIPPING),
            }
        )
    if st == "rush" and context.memory.get("rush_eligible") is not True:
        return ToolResult(
            llm_response={
                "ok": False,
                "error": "rush_not_eligible",
                "hint": "Call check_rush_shipping_eligibility first; use standard if not eligible.",
            }
        )
    card = _data.CARDS.get(card_id)
    card_label = card["label"] if card else card_id
    delivery = (
        card.get("estimated_delivery_rush", "1-2 business days")
        if st == "rush"
        else card.get("estimated_delivery_standard", "5-7 business days")
    )
    order_id = "RPL-2026-001843"
    context.memory.set("shipping_type", st)
    context.memory.set("replacement_ordered", True)
    summary = (
        f"Order ID: {order_id}\n"
        f"Card: {card_label}\n"
        f"Shipping: {st}\n"
        f"Estimated delivery: {delivery}"
    )
    context.memory.set("replacement_order_summary", summary)
    return ToolResult(
        llm_response={
            "success": True,
            "order_id": order_id,
            "card_label": card_label,
            "shipping_type": st,
            "estimated_delivery": delivery,
            "message": "Replacement card ordered successfully.",
        }
    )
