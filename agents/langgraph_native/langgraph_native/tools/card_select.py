"""Card selection: list the customer's cards and record the one they mean."""

from __future__ import annotations

from langgraph_native import mock_data
from langgraph_native.state import CardDisambiguate
from langgraph_native.tools import Gate, Memory, Outcome, error
from langgraph_native.tools.card_replace import adopt_card


def get_customer_cards(memory: Memory) -> Outcome:
    cards = [
        {"id": card["id"], "label": card["label"], "type": card["type"]}
        for card in mock_data.CARDS.values()
    ]
    return Outcome(
        result={"cards": cards, "total": len(cards)},
        memory=CardDisambiguate.changes(card_list=cards),
    )


def select_card(memory: Memory, card_id: str) -> Outcome:
    """Records the chosen card here and as the card being replaced."""
    cards = {card["id"]: card for card in CardDisambiguate.view(memory).card_list or []}
    card = cards.get(card_id)
    if card is None:
        return error("invalid_card_id", valid_ids=sorted(cards))
    return Outcome(
        result={"ok": True, "selected_card_id": card_id, "label": card["label"]},
        memory={
            **CardDisambiguate.changes(
                selected_card_id=card_id, selected_card_label=card["label"]
            ),
            **adopt_card(memory, card_id),
        },
    )


GATES: dict[str, Gate] = {
    "select_card": lambda m: bool(CardDisambiguate.view(m).card_list),
}
