"""Card advisory tools for mantle_combined agent."""

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
    description="List all credit cards the bank offers with a short summary of each."
)
async def get_available_cards(context: ToolContext = None) -> ToolResult:
    cards = [
        {"card_name": key, "name": details["name"], "annual_fee": details["annual_fee"]}
        for key, details in _data.CARD_DETAILS.items()
    ]
    return ToolResult(llm_response={"cards": cards})


@tool(
    description=(
        "Get details about a specific credit card including fees, rewards "
        "structure, and benefits."
    )
)
async def get_card_details(card_name: str, context: ToolContext = None) -> ToolResult:
    key = "summit" if "summit" in card_name.lower() else "river"
    details = _data.CARD_DETAILS[key]
    context.memory.set("card_data_loaded", True)
    return ToolResult(llm_response=details)


@tool(
    description="Get the customer's spending breakdown by category over the past 12 months."
)
async def get_spending_summary(context: ToolContext = None) -> ToolResult:
    summary = _data.SPENDING_SUMMARY
    context.memory.set("card_data_loaded", True)
    return ToolResult(llm_response=summary)


@tool(
    description=(
        "Get rewards or cashback the customer earned in the past 12 months "
        "on their current card."
    )
)
async def get_rewards_earned(context: ToolContext = None) -> ToolResult:
    r = _data.REWARDS_EARNED
    return ToolResult(llm_response=r)


@tool(
    description=(
        "Project annual rewards the customer would earn on a target card "
        "based on their actual spending pattern."
    )
)
async def calculate_rewards_projection(
    target_card: str, context: ToolContext = None
) -> ToolResult:
    key = "summit" if "summit" in target_card.lower() else "river"
    projection = _data.REWARDS_PROJECTIONS[key]
    return ToolResult(llm_response=projection)
