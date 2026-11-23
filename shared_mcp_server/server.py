"""
Mock MCP server for the Mantle benchmarking project.
Exposes all banking and telecom tools using shared mock data.

Run with: python -m shared_mcp_server.server
Listens on: http://localhost:8001/mcp/
"""

import hmac
import os
from typing import Optional

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from shared_mock_data import data as D


def mcp_bind_host() -> str:
    """Return the interface used by the mock MCP server."""
    return os.getenv("MCP_BIND_HOST", "0.0.0.0")


app = FastMCP("Banking & Telecom Mock Tools", host=mcp_bind_host(), port=8001)


class BearerAuthMiddleware:
    """Require a configured bearer token for HTTP requests."""

    def __init__(self, application: ASGIApp, expected_token: str) -> None:
        self._application = application
        self._expected_token = expected_token

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self._application(scope, receive, send)
            return

        authorization = Headers(scope=scope).get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        is_authorized = (
            separator == " "
            and scheme.casefold() == "bearer"
            and bool(token)
            and hmac.compare_digest(token, self._expected_token)
        )
        if not is_authorized:
            response = PlainTextResponse(
                "Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self._application(scope, receive, send)


def authenticated_http_app(
    mcp_server: FastMCP,
    expected_token: str,
) -> ASGIApp:
    """Create a bearer-protected Streamable HTTP application."""
    if not expected_token.strip():
        raise ValueError("MCP_BANKING_TOKEN must be set when authentication is enabled")
    return BearerAuthMiddleware(
        mcp_server.streamable_http_app(),
        expected_token,
    )


def auth_enabled() -> bool:
    """Return whether bearer authentication is enabled."""
    return os.getenv("AUTH_ENABLED", "").strip().lower() == "true"


def run_server() -> None:
    """Run the mock MCP server using its configured authentication mode."""
    if not auth_enabled():
        app.run(transport="streamable-http")
        return

    expected_token = os.getenv("MCP_BANKING_TOKEN", "")
    protected_app = authenticated_http_app(app, expected_token)
    uvicorn.run(
        protected_app,
        host=app.settings.host,
        port=app.settings.port,
    )


# ============================================================
# BANKING: CARD REPLACEMENT
# ============================================================


@app.tool()
def check_account_replacement_eligibility(customer_id: str = "CUST_001") -> dict:
    """Check whether the customer's account is eligible for self-service card replacement."""
    return D.ACCOUNT_REPLACEMENT_ELIGIBILITY


@app.tool()
def get_customer_cards(customer_id: str = "CUST_001") -> dict:
    """Get all cards on the customer's account. Used for card disambiguation when the customer has multiple cards."""
    return {
        "cards": [
            {"card_id": c["id"], "label": c["label"], "type": c["type"]}
            for c in D.CARDS.values()
        ],
    }


@app.tool()
def check_card_eligibility(customer_id: str = "CUST_001", card_id: str = "") -> dict:
    """Check whether a specific card is eligible for replacement."""
    card = D.CARDS.get(card_id)
    if not card:
        return {
            "error": f"Card '{card_id}' not found. Valid IDs: {list(D.CARDS.keys())}"
        }
    return {
        "card_id": card_id,
        "card_label": card["label"],
        "eligible": card["eligible_for_replacement"],
        "replacement_fee": card["replacement_fee"],
    }


@app.tool()
def check_damaged_replacement_scope(
    customer_id: str = "CUST_001", card_id: str = ""
) -> dict:
    """For damaged card replacements, check if the card has authorized users who also need a replacement."""
    card = D.CARDS.get(card_id)
    if not card:
        return {"error": f"Card '{card_id}' not found."}
    return {
        "card_id": card_id,
        "card_label": card["label"],
        "authorized_users": card["authorized_users"],
        "has_authorized_users": len(card["authorized_users"]) > 0,
    }


@app.tool()
def apply_damaged_replacement(
    customer_id: str = "CUST_001", card_id: str = "", replace_for: str = "customer"
) -> dict:
    """Apply a damaged card replacement. replace_for: 'customer', 'authorized_user', or 'both'."""
    card = D.CARDS.get(card_id, {})
    return {
        "success": True,
        "card_id": card_id,
        "card_label": card.get("label", card_id),
        "replaced_for": replace_for,
        "message": f"Damaged card replacement initiated for: {replace_for}.",
    }


@app.tool()
def load_recent_transactions(customer_id: str = "CUST_001", card_id: str = "") -> dict:
    """Load recent transactions on a specific card for fraud review."""
    card = D.CARDS.get(card_id, {})
    transactions = D.TRANSACTIONS_BY_CARD.get(card_id) or D.TRANSACTIONS
    return {
        "card_id": card_id,
        "card_label": card.get("label", card_id),
        "transaction_count": len(transactions),
        "transactions": [
            {
                "id": tx["id"],
                "date": tx["date"],
                "merchant": tx["merchant"],
                "amount": tx["amount"],
                "category": tx["category"],
            }
            for tx in transactions
        ],
    }


@app.tool()
def get_transaction_details(
    customer_id: str = "CUST_001", transaction_id: str = ""
) -> dict:
    """Get detailed information about a specific transaction by ID."""
    detail = D.TRANSACTION_DETAILS.get(transaction_id)
    if detail is not None:
        return detail
    known = ", ".join(sorted(D.TRANSACTION_DETAILS))
    return {
        "error": (f"Transaction '{transaction_id}' not found. " f"Valid IDs: {known}"),
    }


@app.tool()
def record_transaction_review(
    customer_id: str = "CUST_001", all_familiar: bool = True
) -> dict:
    """Record whether the customer confirmed all recent transactions look familiar."""
    return {"ok": True, "all_familiar": all_familiar}


@app.tool()
def check_fraud_report_status(customer_id: str = "CUST_001") -> dict:
    """Check whether a fraud report has already been filed for this account."""
    return D.FRAUD_REPORT


@app.tool()
def report_fraudulent_transactions(
    customer_id: str = "CUST_001", card_id: str = "", transaction_ids: str = ""
) -> dict:
    """File a fraud report for specific transactions flagged as unrecognized. transaction_ids is a comma-separated list."""
    ids = (
        [t.strip() for t in transaction_ids.split(",") if t.strip()]
        if transaction_ids
        else []
    )
    return {
        "success": True,
        "report_id": "FRD-2026-004291",
        "card_id": card_id,
        "flagged_transactions": ids,
        "message": "Fraud report filed. Our team will investigate within 48 hours.",
        "filed_date": "July 7, 2026",
    }


@app.tool()
def lock_card(customer_id: str = "CUST_001", card_id: str = "") -> dict:
    """Immediately lock a card to prevent any further transactions."""
    card = D.CARDS.get(card_id, {})
    return {
        "success": True,
        "card_id": card_id,
        "card_label": card.get("label", card_id),
        "locked": True,
        "effective": "Immediately",
        "message": "Card locked. No further transactions will be authorized.",
    }


@app.tool()
def check_wallet_eligibility_and_status(
    customer_id: str = "CUST_001", card_id: str = ""
) -> dict:
    """Check if a card is eligible for digital wallet provisioning and whether it is already provisioned."""
    card = D.CARDS.get(card_id, {})
    return {
        "card_id": card_id,
        "eligible": card.get("digital_wallet_eligible", False),
        "already_provisioned": card.get("already_provisioned", False),
    }


@app.tool()
def provision_digital_wallet(
    customer_id: str = "CUST_001", card_id: str = "", wallet_provider: str = "apple_pay"
) -> dict:
    """Add a card to Apple Pay or Google Pay for immediate use while awaiting the physical replacement."""
    wallet_names = {"apple_pay": "Apple Pay", "google_pay": "Google Pay"}
    wallet_name = wallet_names.get(wallet_provider, wallet_provider)
    return {
        "success": True,
        "card_id": card_id,
        "wallet": wallet_name,
        "available_in": "2-3 minutes",
        "message": f"Card provisioned to {wallet_name}. It will be available in your Wallet app within a few minutes.",
    }


@app.tool()
def check_rush_shipping_eligibility(
    customer_id: str = "CUST_001", card_id: str = ""
) -> dict:
    """Check whether rush shipping is available for a card replacement."""
    card = D.CARDS.get(card_id, {})
    return {
        "card_id": card_id,
        "rush_eligible": card.get("rush_shipping_eligible", False),
        "rush_fee": card.get("rush_shipping_fee", 25.00),
        "standard_delivery": card.get(
            "estimated_delivery_standard", "5-7 business days"
        ),
        "rush_delivery": card.get("estimated_delivery_rush", "1-2 business days"),
    }


@app.tool()
def process_card_replacement(
    customer_id: str = "CUST_001", card_id: str = "", shipping_type: str = "standard"
) -> dict:
    """Place the final replacement card order with chosen shipping speed."""
    card = D.CARDS.get(card_id, {})
    is_rush = shipping_type.lower() == "rush"
    return {
        "success": True,
        "order_id": "RPL-2026-001843",
        "card_label": card.get("label", card_id),
        "shipping_type": "Rush" if is_rush else "Standard",
        "estimated_delivery": card.get("estimated_delivery_rush")
        if is_rush
        else card.get("estimated_delivery_standard"),
        "fee": card.get("rush_shipping_fee", 25.00) if is_rush else 0,
        "tracking": "Will be emailed when dispatched",
    }


# ============================================================
# BANKING: CARD ADVISORY
# ============================================================


@app.tool()
def get_card_details(customer_id: str = "CUST_001", card_name: str = "") -> dict:
    """Get details about a specific credit card including fees, rewards structure, and benefits."""
    key = "summit" if "summit" in card_name.lower() else "river"
    return D.CARD_DETAILS[key]


@app.tool()
def get_spending_summary(customer_id: str = "CUST_001", months: int = 12) -> dict:
    """Get a breakdown of the user's spending by category over the past N months."""
    return D.SPENDING_SUMMARY


@app.tool()
def get_rewards_earned(customer_id: str = "CUST_001", card_id: str = "river") -> dict:
    """Get the rewards or cashback the user earned in the past 12 months on their current card."""
    return D.REWARDS_EARNED


@app.tool()
def calculate_rewards_projection(
    customer_id: str = "CUST_001",
    target_card: str = "",
    spending_data: Optional[dict] = None,
) -> dict:
    """Project annual rewards the user would earn on a target card given their spending history."""
    key = "summit" if "summit" in target_card.lower() else "river"
    return D.REWARDS_PROJECTIONS[key]


# ============================================================
# BANKING: ACCOUNT ADVISORY
# ============================================================


@app.tool()
def get_accounts(customer_id: str = "CUST_001") -> dict:
    """Get all of the user's bank accounts."""
    return {"accounts": D.ACCOUNTS}


@app.tool()
def get_interest_rates(
    customer_id: str = "CUST_001", account_id: Optional[str] = None
) -> dict:
    """Get current interest rates for one or all accounts."""
    if account_id:
        return D.INTEREST_RATES.get(
            account_id, {"error": f"Account '{account_id}' not found"}
        )
    return {"rates": D.INTEREST_RATES}


@app.tool()
def get_account_balance(customer_id: str = "CUST_001", account_id: str = "") -> dict:
    """Get the current balance of a specific account."""
    return D.ACCOUNT_BALANCES.get(
        account_id, {"error": f"Account '{account_id}' not found"}
    )


@app.tool()
def get_rate_history(
    customer_id: str = "CUST_001", account_id: str = "", months: int = 6
) -> dict:
    """Get historical interest rate changes for a specific account."""
    return {
        "account_id": account_id,
        "history": D.RATE_HISTORY,
        "trend": "Rates dropped slightly in March and have been stable since.",
    }


# ============================================================
# TELECOM: PLAN MANAGEMENT
# ============================================================


@app.tool()
def get_current_plan(customer_id: str = "CUST_001") -> dict:
    """Get the user's current telecom plan and contract details."""
    return D.CURRENT_PLAN


@app.tool()
def get_available_plans(customer_id: str = "CUST_001") -> dict:
    """Get available telecom plan options the user can upgrade or switch to."""
    return {"plans": D.AVAILABLE_PLANS, "addons": D.PLAN_ADDONS}


@app.tool()
def get_current_usage(customer_id: str = "CUST_001") -> dict:
    """Get the user's current data usage for this billing cycle."""
    return D.CURRENT_USAGE


@app.tool()
def calculate_plan_cost(
    customer_id: str = "CUST_001", plan_id: str = "", addon_ids: Optional[list] = None
) -> dict:
    """Calculate the total monthly bill for a given plan and optional add-ons."""
    base = D.PLAN_COSTS.get(plan_id, 45.00)
    addon_total = sum(D.ADDON_COSTS.get(a, 0) for a in (addon_ids or []))
    return {
        "plan_id": plan_id,
        "base_cost": base,
        "addons": addon_ids or [],
        "addons_cost": addon_total,
        "total_monthly_cost": base + addon_total,
        "vs_current_plan": (base + addon_total) - 45.00,
    }


@app.tool()
def check_contract_status(customer_id: str = "CUST_001") -> dict:
    """Check the user's contract status and applicable early termination fees."""
    return D.CONTRACT_STATUS


@app.tool()
def apply_plan_change(
    customer_id: str = "CUST_001", plan_id: str = "", addon_ids: Optional[list] = None
) -> dict:
    """Apply a plan change to the user's account."""
    return {
        "success": True,
        "new_plan": D.PLAN_NAMES.get(plan_id, plan_id),
        "addons_applied": addon_ids or [],
        "effective_date": "July 1, 2026 (next billing cycle)",
        "confirmation_number": "PLAN-CHG-2026-00834",
    }


# ============================================================
# TELECOM: SIM MANAGEMENT
# ============================================================


@app.tool()
def check_sim_status(customer_id: str = "CUST_001", line_id: str = "LINE_001") -> dict:
    """Check the current status of the SIM card on a line — whether it is active or blocked."""
    return {
        **D.SIM_STATUS,
        "line_id": line_id,
    }


@app.tool()
def block_sim(customer_id: str = "CUST_001", line_id: str = "LINE_001") -> dict:
    """Immediately block the SIM card on a line to prevent unauthorized use."""
    return {
        "success": True,
        "line_id": line_id,
        "number": D.SIM_STATUS["number"],
        "sim_blocked": True,
        "effective": "Immediately",
        "confirmation": "BLK-SIM-2026-00482",
        "message": "SIM card blocked. No calls, texts, or data will be possible on this line until a replacement is activated.",
    }


@app.tool()
def order_replacement_sim(
    customer_id: str = "CUST_001", line_id: str = "LINE_001", sim_type: str = "nano_sim"
) -> dict:
    """Order a replacement SIM card or eSIM for an existing line. sim_type: nano_sim or esim."""
    sim_names = {"nano_sim": "nano-SIM card", "esim": "eSIM (QR code)"}
    is_nano = sim_type == "nano_sim"
    return {
        "success": True,
        "order_id": "ORD-20260701-004" if is_nano else "ORD-20260702-005",
        "line_id": line_id,
        "sim_type": sim_names.get(sim_type, sim_type),
        "cost": "Free (replacement)",
        "estimated_delivery": "2-3 business days"
        if is_nano
        else "Instant (QR code via email)",
        "shipping_address": "Bahnhofstrasse 42, 8001 Zürich"
        if is_nano
        else "N/A — delivered via email",
        "confirmation": "SIM-RPL-2026-00193" if is_nano else "SIM-RPL-2026-00201",
        "next_step": "Once received, insert the new SIM and it will activate automatically."
        if is_nano
        else "Check your email for the eSIM QR code and scan it with your device.",
    }


@app.tool()
def get_device_info(customer_id: str = "CUST_001", line_id: str = "LINE_001") -> dict:
    """Get device details including IMEI number for insurance or police reports."""
    return D.DEVICE_INFO


@app.tool()
def get_device_recovery_status(
    customer_id: str = "CUST_001", line_id: str = "LINE_001"
) -> dict:
    """Get Find My location status. Use only for a lost device."""
    return D.DEVICE_RECOVERY


# ============================================================
# TELECOM: FAMILY PLAN ADVISORY
# ============================================================


@app.tool()
def get_family_lines(customer_id: str = "CUST_001") -> dict:
    """Get all phone lines on the user's family plan."""
    return D.FAMILY_LINES


@app.tool()
def get_usage_by_line(customer_id: str = "CUST_001") -> dict:
    """Get data usage for each individual line in the family plan this billing cycle."""
    return {"lines": D.USAGE_BY_LINE, "total_usage_gb": 127}


@app.tool()
def get_individual_plan_costs(
    customer_id: str = "CUST_001", line_usage_data: Optional[dict] = None
) -> dict:
    """Calculate what each family member would pay on their own individual plan based on their usage."""
    return D.INDIVIDUAL_PLAN_COSTS


# ============================================================
# TELECOM: SERVICE TROUBLESHOOTING
# ============================================================


@app.tool()
def run_diagnostics(customer_id: str = "CUST_001", line_id: str = "primary") -> dict:
    """Run network diagnostics on the user's line to identify service issues."""
    return {"line_id": line_id, **D.DIAGNOSTICS}


@app.tool()
def block_premium_services(
    customer_id: str = "CUST_001", line_id: str = "primary"
) -> dict:
    """Immediately block all premium SMS and third-party subscription charges on a line."""
    return {
        "success": True,
        "line_id": line_id,
        "blocked_services": [
            "Premium SMS",
            "Premium rate numbers",
            "Third-party app subscriptions",
        ],
        "effective": "Immediately",
        "confirmation": "BLK-2026-00291",
        "message": "All premium SMS and services blocked. No new charges will be applied to this line.",
        "note": "You can re-enable premium services at any time by contacting us.",
    }


@app.tool()
def apply_network_booster(
    customer_id: str = "CUST_001", line_id: str = "primary"
) -> dict:
    """Apply a home network booster device solution to improve indoor signal strength."""
    return {
        "success": True,
        "solution": "Network Booster Device",
        "device": "T-Boost Home Signal Amplifier",
        "monthly_cost": 0,
        "one_time_cost": 0,
        "shipping": "Free — arrives in 3-5 business days",
        "setup": "Plug-and-play, no configuration required",
        "expected_improvement": "Improves indoor signal by 10-15 dBm",
        "limitation": "Boosts signal strength but does not bypass network congestion during peak hours",
        "confirmation": "BOOST-2026-00184",
    }


@app.tool()
def apply_priority_data(
    customer_id: str = "CUST_001", line_id: str = "primary"
) -> dict:
    """Add a priority data add-on so the line gets preferential treatment during network congestion."""
    return {
        "success": True,
        "solution": "Priority Data Add-on",
        "monthly_cost": 10.00,
        "effective_date": "Today",
        "effect": "Your data traffic is deprioritized last during congestion — you get faster speeds when others slow down",
        "coverage": "Everywhere on the network (not just home)",
        "limitation": "Does not improve base signal strength in low-signal areas",
        "confirmation": "PRI-2026-00573",
    }


# ============================================================
# TELECOM: DATA USAGE
# ============================================================


@app.tool()
def get_usage_by_category(customer_id: str = "CUST_001") -> dict:
    """Get the user's data usage this billing cycle broken down by category."""
    return D.USAGE_BY_CATEGORY


@app.tool()
def get_usage_detail(customer_id: str = "CUST_001", category: str = "") -> dict:
    """Get a detailed per-app breakdown of data usage within a specific category."""
    key = category.lower().replace(" ", "_").replace("-", "_")
    return D.USAGE_DETAILS.get(
        key,
        {
            "error": f"Category '{category}' not found. Try: streaming, social_media, app_updates"
        },
    )


@app.tool()
def get_usage_history(
    customer_id: str = "CUST_001", category: Optional[str] = None, months: int = 3
) -> dict:
    """Get historical data usage, optionally for a specific category, for the past N months."""
    if category and ("app" in category.lower() or "update" in category.lower()):
        return {
            "category": "App Updates",
            "history": D.USAGE_HISTORY_APP_UPDATES,
            "trend": "Significant spike in June — likely caused by a major iOS system update.",
        }
    return {
        "category": "Total Data Usage",
        "history": D.USAGE_HISTORY_TOTAL,
        "plan_limit_gb": 40,
    }


@app.tool()
def add_data_top_up(customer_id: str = "CUST_001", amount_gb: int = 5) -> dict:
    """Add a one-time data top-up to the current billing cycle."""
    return {
        "success": True,
        "gb_added": amount_gb,
        "cost": amount_gb * 2.00,
        "new_total_allowance_gb": 40 + amount_gb,
        "valid_until": "June 30, 2026 (end of current billing cycle)",
        "confirmation": "TOP-2026-00129",
    }


# ============================================================
# TELECOM: BILLING INVESTIGATION
# ============================================================


@app.tool()
def get_current_bill(customer_id: str = "CUST_001") -> dict:
    """Get the user's most recent bill total and due date."""
    return D.CURRENT_BILL


@app.tool()
def get_previous_bills(customer_id: str = "CUST_001", months: int = 3) -> dict:
    """Get summary totals for the user's most recent past bills."""
    return {"bills": D.PREVIOUS_BILLS, "average": 76.00}


@app.tool()
def get_bill_line_items(customer_id: str = "CUST_001", period: str = "current") -> dict:
    """Get the itemized charge breakdown for a specific billing period."""
    if period == "current" or "june" in period.lower() or period == "2026-06":
        return D.BILL_LINE_ITEMS["june"]
    elif "may" in period.lower() or period == "2026-05":
        return D.BILL_LINE_ITEMS["may"]
    return {
        "period": period,
        "items": [],
        "total": 0,
        "note": "No data for this period",
    }


@app.tool()
def get_charge_explanation(customer_id: str = "CUST_001", charge_id: str = "") -> dict:
    """Get a detailed explanation for a specific charge type on the bill."""
    return D.CHARGE_EXPLANATIONS.get(
        charge_id,
        {
            "error": f"No explanation found for charge '{charge_id}'. Try: intl_roaming, data_overage, cancelled_line"
        },
    )


@app.tool()
def get_active_lines(customer_id: str = "CUST_001") -> dict:
    """Get all currently active phone lines on the account."""
    return {"lines": D.ACTIVE_LINES}


@app.tool()
def get_cancelled_lines(customer_id: str = "CUST_001") -> dict:
    """Get all cancelled phone lines on the account."""
    return {"lines": D.CANCELLED_LINES}


@app.tool()
def get_line_history(customer_id: str = "CUST_001", line_id: str = "") -> dict:
    """Get the full event history of a phone line including activations and cancellations."""
    if line_id in ("LINE_003", "5578"):
        return D.LINE_HISTORY_5578
    return {"line_id": line_id, "events": [], "note": "No history found for this line"}


@app.tool()
def create_billing_adjustment(
    customer_id: str = "CUST_001",
    line_id: str = "",
    amount: float = 0.0,
    reason: str = "",
) -> dict:
    """Create a billing credit for an incorrect or disputed charge."""
    return {
        "success": True,
        "adjustment_id": "ADJ-2026-00741",
        "line_id": line_id,
        "credit_amount": amount,
        "reason": reason,
        "applied_to": "July 2026 bill",
        "confirmation": f"Credit of ${amount:.2f} applied. Confirmation #ADJ-2026-00741.",
        "message": f"We apologize for the error. A credit of ${amount:.2f} will appear on your July bill.",
    }


# ============================================================
# TELECOM: ORDER STATUS
# ============================================================


@app.tool()
def get_orders(customer_id: str = "CUST_001", days: int = 90) -> dict:
    """Get the user's recent orders within the specified number of days."""
    return {"orders": D.ORDERS, "total_orders": len(D.ORDERS)}


@app.tool()
def get_order_details(customer_id: str = "CUST_001", order_id: str = "") -> dict:
    """Get detailed information about a specific order including tracking, shipping address, and delivery estimates."""
    return D.ORDER_DETAILS.get(
        order_id,
        {
            "error": f"Order '{order_id}' not found. Valid IDs: ORD-20260701-004, ORD-20260628-001, ORD-20260615-002"
        },
    )


if __name__ == "__main__":
    run_server()
