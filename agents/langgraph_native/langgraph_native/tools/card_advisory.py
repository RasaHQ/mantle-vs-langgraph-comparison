"""Card advisory: spending, rewards, and the cards the bank offers."""

from __future__ import annotations

from langgraph_native import mock_data
from langgraph_native.state import CardAdvisory
from langgraph_native.tools import Memory, Outcome


def _card_key(card_name: str) -> str:
    return "summit" if "summit" in card_name.lower() else "river"


def get_available_cards(memory: Memory) -> Outcome:
    cards = [
        {"card_name": key, "name": details["name"], "annual_fee": details["annual_fee"]}
        for key, details in mock_data.CARD_DETAILS.items()
    ]
    return Outcome(result={"cards": cards})


def get_card_details(memory: Memory, card_name: str) -> Outcome:
    return Outcome(
        result=dict(mock_data.CARD_DETAILS[_card_key(card_name)]),
        memory=CardAdvisory.changes(card_data_loaded=True),
    )


def get_spending_summary(memory: Memory) -> Outcome:
    return Outcome(
        result=dict(mock_data.SPENDING_SUMMARY),
        memory=CardAdvisory.changes(card_data_loaded=True),
    )


def get_rewards_earned(memory: Memory) -> Outcome:
    return Outcome(result=dict(mock_data.REWARDS_EARNED))


def calculate_rewards_projection(memory: Memory, target_card: str) -> Outcome:
    return Outcome(result=dict(mock_data.REWARDS_PROJECTIONS[_card_key(target_card)]))
