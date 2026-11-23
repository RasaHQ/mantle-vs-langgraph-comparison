"""Card disambiguation tools for mantle_combined agent."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from rasa.mantle.tools.decorator import ToolContext, tool
from rasa.mantle.tools.result import ToolResult


def _load_mock_data():
    data_path = Path(__file__).resolve().parents[2] / "lib" / "mock_data.py"
    spec = importlib.util.spec_from_file_location("mock_data", data_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load mock data from {data_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_data = _load_mock_data()


@tool(
    description=(
        "Fetch all cards on the customer's account. Present the list so the "
        "customer can choose which card to act on."
    )
)
async def get_customer_cards(context: ToolContext = None) -> ToolResult:
    cards = [
        {"id": c["id"], "label": c["label"], "type": c["type"]}
        for c in _data.CARDS.values()
    ]
    context.memory.set("card_list", cards)
    return ToolResult(
        llm_response={
            "cards": cards,
            "total": len(cards),
            "hint": (
                "Match the customer's words to a card from this list. "
                "Record with set_memory(selected_card_id=...)."
            ),
        }
    )


@tool(description="Post-write hook: validate the selected card id and set its label.")
async def run_after_setting_selected_card_id(
    context: ToolContext = None,
) -> ToolResult:
    card_list = context.memory.get("card_list") or []
    selected_id = context.memory.get("selected_card_id")

    card_map = {str(c["id"]): c for c in card_list}
    if not selected_id or selected_id not in card_map:
        context.memory.set("selected_card_id", None)
        context.memory.set("selected_card_label", None)
        return ToolResult(
            llm_response={
                "ok": False,
                "error": "invalid_card_id",
                "hint": "That ID doesn't match any card. Check the card list and try again.",
            }
        )

    context.memory.set("selected_card_label", card_map[selected_id]["label"])
    return ToolResult(
        llm_response={
            "ok": True,
            "selected_card_id": selected_id,
            "selected_card_label": card_map[selected_id]["label"],
            "hint": (
                "Card pick is recorded on this skill only. The caller must "
                "adopt it with @tool.adopt_selected_card (or set_memory on "
                "the caller's selected_card_id) so card-replace can reset "
                "wallet, charges, and shipping on a real card switch."
            ),
        }
    )
