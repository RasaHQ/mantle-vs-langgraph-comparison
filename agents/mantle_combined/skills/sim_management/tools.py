"""SIM management tools for mantle_combined agent."""

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
        "Check the current status of the customer's SIM — whether it is active or blocked."
    )
)
async def check_sim_status(context: ToolContext = None) -> ToolResult:
    # The mock is process-wide. A block lives only in this conversation's memory.
    is_blocked = context.memory.get("sim_blocked")
    if is_blocked is None:
        is_blocked = _data.SIM_STATUS["is_blocked"]
        context.memory.set("sim_blocked", is_blocked)
    status = {**_data.SIM_STATUS, "is_blocked": is_blocked}
    return ToolResult(llm_response=status)


@tool(
    description=(
        "Block the customer's SIM card. Do not call this tool directly. "
        "Invoke block_sim_flow, which checks the SIM status, collects explicit "
        "consent, and executes this tool."
    )
)
async def block_sim(context: ToolContext = None) -> ToolResult:
    context.memory.set("sim_blocked", True)
    response = {
        "success": True,
        "number": _data.SIM_STATUS["number"],
        "sim_blocked": True,
        "effective": "Immediately",
        "confirmation": "BLK-SIM-2026-00482",
        "message": (
            "SIM card blocked. No calls, texts, or data will be possible on "
            "this line until a replacement is activated."
        ),
    }
    return ToolResult(llm_response=response)


@tool(
    description=(
        "Order a replacement SIM card or eSIM for the customer's line. "
        "Uses the sim_type already stored in memory: 'nano_sim' "
        "(physical, 2-3 day shipping) or 'esim' (instant QR code via email). "
        "Call get_device_info first if the customer wants to check eSIM compatibility."
    )
)
async def order_replacement_sim(context: ToolContext = None) -> ToolResult:
    sim_type = context.memory.get("sim_type")
    sim_names = {"nano_sim": "nano-SIM card", "esim": "eSIM (QR code)"}
    if sim_type not in sim_names:
        return ToolResult(
            llm_response={
                "success": False,
                "error": "sim_type_not_set",
                "valid_values": sorted(sim_names),
            }
        )
    is_nano = sim_type == "nano_sim"
    context.memory.set("replacement_ordered", True)
    response = {
        "success": True,
        "order_id": "ORD-20260701-004" if is_nano else "ORD-20260702-005",
        "sim_type": sim_names.get(sim_type, sim_type),
        "cost": "Free (replacement)",
        "estimated_delivery": (
            "2-3 business days" if is_nano else "Instant (QR code via email)"
        ),
        "shipping_address": (
            "Bahnhofstrasse 42, 8001 Zürich" if is_nano else "N/A — delivered via email"
        ),
        "confirmation": "SIM-RPL-2026-00193" if is_nano else "SIM-RPL-2026-00201",
        "next_step": (
            "Once received, insert the new SIM and it will activate automatically."
            if sim_type == "nano_sim"
            else "Check your email for the eSIM QR code and scan it with your device."
        ),
    }
    summary = (
        f"Order ID: {response['order_id']}\n"
        f"Confirmation: {response['confirmation']}\n"
        f"SIM type: {response['sim_type']}\n"
        f"Delivery: {response['estimated_delivery']}\n"
        f"Next step: {response['next_step']}"
    )
    context.memory.set("sim_order_summary", summary)
    return ToolResult(llm_response=response)


@tool(
    description=(
        "Get device details including IMEI number, serial number, and "
        "eSIM compatibility. Use when the customer needs IMEI for a police "
        "report or insurance claim, or to check if their device supports eSIM."
    )
)
async def get_device_info(context: ToolContext = None) -> ToolResult:
    info = _data.DEVICE_INFO
    context.memory.set("device_name", info["device"])
    context.memory.set("device_imei", info["imei"])
    context.memory.set("device_serial", info["serial_number"])
    context.memory.set("device_info_shared", True)
    return ToolResult(llm_response=info)


@tool(
    description=(
        "Get Find My Device location status. Use only for a lost device "
        "when the customer asks whether Find My is currently enabled."
    )
)
async def get_device_recovery_status(context: ToolContext = None) -> ToolResult:
    return ToolResult(llm_response=_data.DEVICE_RECOVERY)
