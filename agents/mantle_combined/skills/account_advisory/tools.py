"""Account advisory tools for mantle_combined agent."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Optional

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



@tool(description="Get all of the customer's bank accounts.")
async def get_accounts(context: ToolContext = None) -> ToolResult:
    accounts = _data.ACCOUNTS
    context.memory.set("accounts_loaded", True)
    return ToolResult(llm_response={"accounts": accounts})


@tool(
    description=(
        "Get current interest rates for one or all accounts. "
        "Pass account_id to get a specific account's rate, or omit for all. "
        "Valid IDs: CHK_001, SAV_001, MM_001."
    )
)
async def get_interest_rates(
    account_id: Optional[str] = None, context: ToolContext = None
) -> ToolResult:
    if account_id:
        rate = _data.INTEREST_RATES.get(account_id)
        if rate is None:
            return ToolResult(
                llm_response={"error": f"Account '{account_id}' not found"}
            )
        return ToolResult(llm_response=rate)
    return ToolResult(llm_response={"rates": _data.INTEREST_RATES})


@tool(
    description=(
        "Get the current balance of a specific account. "
        "Valid IDs: CHK_001 (checking), SAV_001 (savings), MM_001 (money market)."
    )
)
async def get_account_balance(
    account_id: str, context: ToolContext = None
) -> ToolResult:
    balance = _data.ACCOUNT_BALANCES.get(account_id)
    if balance is None:
        return ToolResult(llm_response={"error": f"Account '{account_id}' not found"})
    return ToolResult(llm_response=balance)


@tool(
    description=(
        "Get historical interest rate changes for a specific account "
        "over the past 6 months. Useful when the customer asks whether "
        "rates have gone up or down."
    )
)
async def get_rate_history(account_id: str, context: ToolContext = None) -> ToolResult:
    trend = "Rates dropped slightly in March and have been stable since."
    return ToolResult(
        llm_response={
            "account_id": account_id,
            "history": _data.RATE_HISTORY,
            "trend": trend,
        }
    )
