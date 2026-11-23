"""Account advisory: accounts, interest rates, balances, and rate history."""

from __future__ import annotations

from typing import Optional

from langgraph_native import mock_data
from langgraph_native.state import AccountAdvisory
from langgraph_native.tools import Gate, Memory, Outcome, error

_RATE_TREND = "Rates dropped slightly in March and have been stable since."


def get_accounts(memory: Memory) -> Outcome:
    return Outcome(
        result={"accounts": mock_data.ACCOUNTS},
        memory=AccountAdvisory.changes(accounts_loaded=True),
    )


def get_interest_rates(memory: Memory, account_id: Optional[str] = None) -> Outcome:
    if account_id is None:
        return Outcome(result={"rates": mock_data.INTEREST_RATES})
    rate = mock_data.INTEREST_RATES.get(account_id)
    if rate is None:
        return error(f"Account '{account_id}' not found")
    return Outcome(result=dict(rate))


def get_account_balance(memory: Memory, account_id: str) -> Outcome:
    balance = mock_data.ACCOUNT_BALANCES.get(account_id)
    if balance is None:
        return error(f"Account '{account_id}' not found")
    return Outcome(result=dict(balance))


def get_rate_history(memory: Memory, account_id: str) -> Outcome:
    return Outcome(
        result={
            "account_id": account_id,
            "history": mock_data.RATE_HISTORY,
            "trend": _RATE_TREND,
        }
    )


def _loaded(memory: Memory) -> bool:
    return AccountAdvisory.view(memory).accounts_loaded is True


GATES: dict[str, Gate] = {
    "get_account_balance": _loaded,
    "get_rate_history": _loaded,
}
