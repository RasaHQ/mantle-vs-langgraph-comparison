"""Order status: recent orders and the details of one order."""

from __future__ import annotations

from langgraph_native import mock_data
from langgraph_native.state import OrderStatus
from langgraph_native.tools import Memory, Outcome, error


def get_orders(memory: Memory) -> Outcome:
    orders = mock_data.ORDERS
    return Outcome(
        result={"orders": orders, "total_orders": len(orders)},
        memory=OrderStatus.changes(orders_loaded=True),
    )


def get_order_details(memory: Memory, order_id: str) -> Outcome:
    detail = mock_data.ORDER_DETAILS.get(order_id)
    if detail is None:
        return error(
            f"Order '{order_id}' not found.", valid_ids=list(mock_data.ORDER_DETAILS)
        )
    return Outcome(result=dict(detail))
