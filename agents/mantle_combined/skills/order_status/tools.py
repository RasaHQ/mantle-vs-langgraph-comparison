"""Order status tools for mantle_combined agent."""

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
        "Fetch the customer's recent orders. Call this first and present the "
        "results clearly — date, item, and status for each order."
    )
)
async def get_orders(context: ToolContext = None) -> ToolResult:
    orders = _data.ORDERS
    context.memory.set("orders_loaded", True)
    return ToolResult(llm_response={"orders": orders, "total_orders": len(orders)})


@tool(
    description=(
        "Get detailed information about a specific order including tracking, "
        "shipping address, and delivery estimates."
    )
)
async def get_order_details(order_id: str, context: ToolContext = None) -> ToolResult:
    detail = _data.ORDER_DETAILS.get(order_id)
    if detail is None:
        return ToolResult(
            llm_response={
                "ok": False,
                "error": f"Order '{order_id}' not found.",
                "valid_ids": list(_data.ORDER_DETAILS.keys()),
            }
        )
    return ToolResult(llm_response=detail)
