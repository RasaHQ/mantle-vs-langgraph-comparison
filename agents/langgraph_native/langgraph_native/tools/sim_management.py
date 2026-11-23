"""SIM management: incident advice, blocking, device info, replacement SIMs."""

from __future__ import annotations

from langgraph_native import mock_data
from langgraph_native.responses import Utterance
from langgraph_native.state import IncidentReason, SimManagement, SimType
from langgraph_native.tools import Gate, Memory, Outcome, error

SIM_NAMES: dict[str, str] = {"nano_sim": "nano-SIM card", "esim": "eSIM (QR code)"}
BLOCK_CONFIRMATION = "BLK-SIM-2026-00482"


def _view(memory: Memory) -> SimManagement:
    return SimManagement.view(memory)


def record_incident(memory: Memory, reason: IncidentReason) -> Outcome:
    """Records lost or stolen and speaks that reason's advice once."""
    state = _view(memory)
    update = SimManagement.changes(incident_reason=reason)
    say: list[Utterance] = []
    if state.advice_given_for != reason:
        say.append(Utterance(name=f"utter_sim_incident_advice_{reason}"))
        update.update(SimManagement.changes(advice_given_for=reason))
    return Outcome(
        result={"ok": True, "incident_reason": reason, "advice_spoken": bool(say)},
        memory=update,
        say=say,
    )


def get_device_recovery_status(memory: Memory) -> Outcome:
    return Outcome(result=dict(mock_data.DEVICE_RECOVERY))


def check_sim_status(memory: Memory) -> Outcome:
    # The mock is process-wide; a block lives only in this conversation's memory.
    blocked = _view(memory).sim_blocked
    if blocked is None:
        blocked = bool(mock_data.SIM_STATUS["is_blocked"])
    return Outcome(
        result={**mock_data.SIM_STATUS, "is_blocked": blocked},
        memory=SimManagement.changes(sim_blocked=blocked),
    )


def record_block_consent(memory: Memory, wants_to_block: bool) -> Outcome:
    return Outcome(
        result={"ok": True, "wants_to_block": wants_to_block},
        memory=SimManagement.changes(wants_to_block=wants_to_block),
    )


def block_sim(memory: Memory) -> Outcome:
    return Outcome(
        result={
            "success": True,
            "number": mock_data.SIM_STATUS["number"],
            "sim_blocked": True,
            "effective": "Immediately",
            "confirmation": BLOCK_CONFIRMATION,
        },
        memory=SimManagement.changes(sim_blocked=True),
        say=[Utterance(name="utter_sim_blocked")],
    )


def get_device_info(memory: Memory) -> Outcome:
    """Returns the device details and speaks them the first time only."""
    info = mock_data.DEVICE_INFO
    if _view(memory).device_info_shared:
        return Outcome(
            result={**info, "note": "Already told the customer; do not repeat it."}
        )
    return Outcome(
        result=dict(info),
        memory=SimManagement.changes(
            device_name=info["device"],
            device_imei=info["imei"],
            device_serial=info["serial_number"],
            device_info_shared=True,
        ),
        say=[
            Utterance(
                name="utter_device_info_shared",
                values={
                    "device_name": info["device"],
                    "device_imei": info["imei"],
                    "device_serial": info["serial_number"],
                },
            )
        ],
    )


def record_sim_type(memory: Memory, sim_type: SimType) -> Outcome:
    return Outcome(
        result={"ok": True, "sim_type": sim_type},
        memory=SimManagement.changes(sim_type=sim_type),
    )


def order_replacement_sim(memory: Memory) -> Outcome:
    state = _view(memory)
    sim_type = state.sim_type
    if sim_type is None:
        return error("sim_type_not_set", valid_values=sorted(SIM_NAMES))
    is_nano = sim_type == "nano_sim"
    order_id = "ORD-20260701-004" if is_nano else "ORD-20260702-005"
    confirmation = "SIM-RPL-2026-00193" if is_nano else "SIM-RPL-2026-00201"
    delivery = "2-3 business days" if is_nano else "Instant (QR code via email)"
    next_step = (
        "Once received, insert the new SIM and it will activate automatically."
        if is_nano
        else "Check your email for the eSIM QR code and scan it with your device."
    )
    summary = (
        f"Order ID: {order_id}\n"
        f"Confirmation: {confirmation}\n"
        f"SIM type: {SIM_NAMES[sim_type]}\n"
        f"Delivery: {delivery}\n"
        f"Next step: {next_step}"
    )
    return Outcome(
        result={
            "success": True,
            "order_id": order_id,
            "sim_type": SIM_NAMES[sim_type],
            "cost": "Free (replacement)",
            "estimated_delivery": delivery,
            "shipping_address": (
                "Bahnhofstrasse 42, 8001 Zürich"
                if is_nano
                else "N/A, delivered via email"
            ),
            "confirmation": confirmation,
            "next_step": next_step,
        },
        memory=SimManagement.changes(
            replacement_ordered=True,
            sim_order_summary=summary,
            ordered_sim_types=[*(state.ordered_sim_types or []), sim_type],
        ),
        say=[
            Utterance(
                name="utter_sim_order_replacement_success",
                values={
                    "sim_name": SIM_NAMES[sim_type],
                    "order_id": order_id,
                    "confirmation": confirmation,
                    "delivery": delivery,
                    "next_step": next_step,
                },
            )
        ],
    )


def _can_order(memory: Memory) -> bool:
    state = _view(memory)
    return state.sim_type is not None and state.sim_type not in (
        state.ordered_sim_types or []
    )


GATES: dict[str, Gate] = {
    "get_device_recovery_status": lambda m: _view(m).incident_reason == "lost",
    "order_replacement_sim": _can_order,
}
