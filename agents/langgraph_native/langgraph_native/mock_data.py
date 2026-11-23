"""Single source of truth for all mock data used across every agent.

Every agent — MCP server, mantle_autonomous, mantle_hybrid — imports from
here so the customer sees identical backend state regardless of orchestration.
"""

from __future__ import annotations

from typing import Any


# ============================================================
# BANKING: ACCOUNT & CARD REPLACEMENT
# ============================================================

ACCOUNT_REPLACEMENT_ELIGIBILITY = {
    "customer_id": "CUST_001",
    "eligible": True,
    "reason": None,
}

CARDS: dict[str, dict[str, Any]] = {
    "VISA_001": {
        "id": "VISA_001",
        "label": "River Visa ending 4821",
        "type": "River Visa",
        "eligible_for_replacement": True,
        "replacement_fee": 0,
        "is_locked": False,
        "digital_wallet_eligible": True,
        "already_provisioned": False,
        "rush_shipping_eligible": True,
        "rush_shipping_fee": 25.00,
        "estimated_delivery_standard": "5-7 business days",
        "estimated_delivery_rush": "1-2 business days",
        "authorized_users": [
            {"name": "Mike Chen", "relationship": "business partner"},
        ],
    },
    "MC_002": {
        "id": "MC_002",
        "label": "Summit Rewards ending 9173",
        "type": "Summit Rewards",
        "eligible_for_replacement": True,
        "replacement_fee": 0,
        "is_locked": False,
        "digital_wallet_eligible": True,
        "already_provisioned": True,
        "rush_shipping_eligible": True,
        "rush_shipping_fee": 25.00,
        "estimated_delivery_standard": "5-7 business days",
        "estimated_delivery_rush": "1-2 business days",
        "authorized_users": [
            {"name": "Sarah Johnson", "relationship": "spouse"},
        ],
    },
}

FRAUD_REPORT = {
    "has_existing_report": False,
    "report_id": None,
    "filed_date": None,
}

# Backward-compatible alias for skills that reference the primary card
CARD = CARDS["VISA_001"]

TRANSACTIONS_BY_CARD: dict[str, list[dict[str, Any]]] = {
    "VISA_001": [
        {
            "id": "txn_001",
            "date": "Jun 15",
            "merchant": "Amazon.com",
            "amount": 47.22,
            "category": "Shopping",
        },
        {
            "id": "txn_002",
            "date": "Jun 14",
            "merchant": "Shell Gas Station",
            "amount": 38.50,
            "category": "Gas",
        },
        {
            "id": "txn_003",
            "date": "Jun 13",
            "merchant": "Uber Eats",
            "amount": 24.99,
            "category": "Food",
        },
        {
            "id": "txn_004",
            "date": "Jun 12",
            "merchant": "Netflix",
            "amount": 15.99,
            "category": "Subscriptions",
        },
        {
            "id": "txn_005",
            "date": "Jun 10",
            "merchant": "Whole Foods",
            "amount": 112.35,
            "category": "Groceries",
        },
    ],
    "MC_002": [
        {
            "id": "txn_101",
            "date": "Jun 16",
            "merchant": "Apple Store",
            "amount": 129.00,
            "category": "Shopping",
        },
        {
            "id": "txn_102",
            "date": "Jun 14",
            "merchant": "Delta Airlines",
            "amount": 342.80,
            "category": "Travel",
        },
        {
            "id": "txn_103",
            "date": "Jun 12",
            "merchant": "Starbucks",
            "amount": 6.45,
            "category": "Food",
        },
        {
            "id": "txn_104",
            "date": "Jun 11",
            "merchant": "Spotify",
            "amount": 10.99,
            "category": "Subscriptions",
        },
        {
            "id": "txn_105",
            "date": "Jun 09",
            "merchant": "Target",
            "amount": 67.23,
            "category": "Shopping",
        },
    ],
}

# Backward-compatible alias: primary card (River Visa) transaction list
TRANSACTIONS = TRANSACTIONS_BY_CARD["VISA_001"]

TRANSACTION_DETAILS: dict[str, dict[str, Any]] = {
    "txn_001": {
        "id": "txn_001",
        "merchant": "Amazon.com",
        "amount": 47.22,
        "date": "Jun 15",
        "time": "3:22 PM",
        "description": "Purchase: Kindle Protective Case - Black",
        "shipped_to": "your address on file",
        "order_id": "113-8472910-5691823",
        "status": "Delivered Jun 16",
    },
    "txn_002": {
        "id": "txn_002",
        "merchant": "Shell Gas Station",
        "amount": 38.50,
        "date": "Jun 14",
        "time": "2:47 PM",
        "description": "Fuel purchase - 12.3 gallons",
        "location": "Shell on Main St, Springfield",
        "card_type": "Swipe",
    },
    "txn_003": {
        "id": "txn_003",
        "merchant": "Uber Eats",
        "amount": 24.99,
        "date": "Jun 13",
        "time": "7:18 PM",
        "description": "Food delivery - Chipotle order",
        "delivery_address": "your address on file",
    },
    "txn_004": {
        "id": "txn_004",
        "merchant": "Netflix",
        "amount": 15.99,
        "date": "Jun 12",
        "time": "12:00 AM",
        "description": "Monthly subscription - Standard plan",
        "account": "netflix@email.com",
    },
    "txn_005": {
        "id": "txn_005",
        "merchant": "Whole Foods Market",
        "amount": 112.35,
        "date": "Jun 10",
        "time": "5:43 PM",
        "description": "In-store grocery purchase",
        "location": "Whole Foods - Downtown",
        "items_count": 18,
    },
    "txn_101": {
        "id": "txn_101",
        "merchant": "Apple Store",
        "amount": 129.00,
        "date": "Jun 16",
        "time": "1:15 PM",
        "description": "AirPods Pro - White",
        "location": "Apple Store - Downtown",
    },
    "txn_102": {
        "id": "txn_102",
        "merchant": "Delta Airlines",
        "amount": 342.80,
        "date": "Jun 14",
        "time": "9:02 AM",
        "description": "Flight booking - round trip",
        "confirmation": "DL-884291",
    },
    "txn_103": {
        "id": "txn_103",
        "merchant": "Starbucks",
        "amount": 6.45,
        "date": "Jun 12",
        "time": "8:11 AM",
        "description": "Grande latte",
        "location": "Starbucks on Market St",
    },
    "txn_104": {
        "id": "txn_104",
        "merchant": "Spotify",
        "amount": 10.99,
        "date": "Jun 11",
        "time": "12:00 AM",
        "description": "Monthly subscription - Individual",
        "account": "spotify@email.com",
    },
    "txn_105": {
        "id": "txn_105",
        "merchant": "Target",
        "amount": 67.23,
        "date": "Jun 09",
        "time": "4:30 PM",
        "description": "In-store purchase",
        "location": "Target - Westside",
    },
}


# ============================================================
# BANKING: CARD ADVISORY
# ============================================================

CARD_DETAILS: dict[str, dict[str, Any]] = {
    "river": {
        "name": "River",
        "annual_fee": 0,
        "rewards_rate": "1.5% flat cashback on all purchases",
        "rewards_type": "cashback",
        "benefits": ["No annual fee", "Purchase protection", "Extended warranty"],
        "foreign_transaction_fee": "3%",
    },
    "summit": {
        "name": "Summit Rewards",
        "annual_fee": 95,
        "rewards_rate": "3x points on dining, 2x on travel, 1x on everything else",
        "rewards_type": "points (1 point = ~$0.0125)",
        "sign_up_bonus": "60,000 points after $4,000 spend in 3 months (~$750 value)",
        "benefits": [
            "Travel insurance",
            "No foreign transaction fees",
            "Primary car rental insurance",
            "Trip cancellation/interruption insurance",
        ],
        "foreign_transaction_fee": "0%",
    },
}

SPENDING_SUMMARY = {
    "period_months": 12,
    "total_spend": 12000,
    "categories": {
        "dining": 2400,
        "travel": 1800,
        "groceries": 3200,
        "gas": 1100,
        "shopping": 2000,
        "entertainment": 800,
        "other": 700,
    },
}

REWARDS_EARNED = {
    "card": "River",
    "period": "Last 12 months",
    "rewards_earned": 180.00,
    "reward_type": "cashback",
    "pending": 12.50,
    "redeemed_ytd": 50.00,
    "current_balance": 142.50,
}

REWARDS_PROJECTIONS: dict[str, dict[str, Any]] = {
    "summit": {
        "card": "Summit Rewards",
        "projected_annual_rewards": 340.00,
        "annual_fee": 95.00,
        "net_annual_value": 245.00,
        "vs_current_card_net_gain": 65.00,
        "breakdown": {
            "dining_3x_2400": 90.00,
            "travel_2x_1800": 45.00,
            "other_1x_7800": 97.50,
        },
        "recommendation": (
            "Upgrade is financially worthwhile. You'd net ~$65/year more, "
            "plus significantly better travel benefits."
        ),
    },
    "river": {
        "card": "River",
        "projected_annual_rewards": 180.00,
        "annual_fee": 0.00,
        "net_annual_value": 180.00,
        "vs_current_card_net_gain": 0.00,
        "breakdown": {"flat_1_5pct_12000": 180.00},
        "recommendation": "Current card is optimal for flat-rate cashback.",
    },
}


# ============================================================
# BANKING: ACCOUNT ADVISORY
# ============================================================

ACCOUNTS = [
    {"id": "CHK_001", "type": "Checking", "name": "Primary Checking"},
    {"id": "SAV_001", "type": "Savings", "name": "High-Yield Savings"},
    {"id": "MM_001", "type": "Money Market", "name": "Money Market Account"},
]

INTEREST_RATES: dict[str, dict[str, Any]] = {
    "CHK_001": {
        "account": "Primary Checking",
        "apy": 0.01,
        "minimum_balance": 0,
        "note": "Primarily for daily spending",
    },
    "SAV_001": {
        "account": "High-Yield Savings",
        "apy": 4.25,
        "minimum_balance": 0,
        "note": "No minimum required",
    },
    "MM_001": {
        "account": "Money Market",
        "apy": 4.50,
        "minimum_balance": 10000,
        "apy_below_minimum": 0.50,
        "note": "Best rate but requires $10,000 minimum; drops to 0.50% if balance falls below",
    },
}

ACCOUNT_BALANCES: dict[str, dict[str, Any]] = {
    "CHK_001": {
        "account": "Primary Checking",
        "balance": 4250.67,
        "available": 4200.67,
    },
    "SAV_001": {
        "account": "High-Yield Savings",
        "balance": 18500.00,
        "available": 18500.00,
    },
    "MM_001": {
        "account": "Money Market",
        "balance": 3200.00,
        "available": 3200.00,
        "warning": "Currently below $10,000 minimum — earning 0.50% APY instead of 4.50%",
    },
}

RATE_HISTORY = [
    {"month": "Jan 2026", "apy": 4.50},
    {"month": "Feb 2026", "apy": 4.50},
    {"month": "Mar 2026", "apy": 4.25},
    {"month": "Apr 2026", "apy": 4.25},
    {"month": "May 2026", "apy": 4.25},
    {"month": "Jun 2026", "apy": 4.25},
]


# ============================================================
# TELECOM: ORDER STATUS
# ============================================================

ORDERS = [
    {
        "id": "ORD-20260701-004",
        "date": "July 1, 2026",
        "status": "OPEN",
        "description": "SIM replacement",
        "devices": [
            {
                "name": "Replacement nano-SIM",
                "device_status": "PENDING",
                "status_detail": "Being prepared for shipment",
            }
        ],
    },
    {
        "id": "ORD-20260628-001",
        "date": "June 28, 2026",
        "status": "OPEN",
        "description": "Device order",
        "devices": [
            {
                "name": "Samsung Galaxy Watch 7",
                "device_status": "PENDING",
                "status_detail": "Being prepared for shipment",
            }
        ],
    },
    {
        "id": "ORD-20260615-002",
        "date": "June 15, 2026",
        "status": "COMPLETE",
        "description": "Equipment order",
        "devices": [
            {
                "name": "Internet Box 3 Router",
                "device_status": "COMPLETE",
                "status_detail": "Delivered June 18, 2026",
                "tracking": "POST-CH-98234857",
            }
        ],
    },
]

ORDER_DETAILS: dict[str, dict[str, Any]] = {
    "ORD-20260701-004": {
        "id": "ORD-20260701-004",
        "date": "July 1, 2026",
        "status": "OPEN",
        "devices": [
            {
                "name": "Replacement nano-SIM",
                "device_status": "PENDING",
                "status_detail": "Being prepared for shipment at distribution center",
                "estimated_ship_date": "July 2, 2026",
                "estimated_delivery": "July 3-4, 2026",
                "tracking": "Not yet available — tracking number assigned once shipped",
                "shipping_method": "Priority Post (Swiss Post)",
            }
        ],
        "shipping_address": "Bahnhofstrasse 42, 8001 Zürich",
        "payment_method": "No charge (replacement)",
        "order_total": "CHF 0.00",
    },
    "ORD-20260628-001": {
        "id": "ORD-20260628-001",
        "date": "June 28, 2026",
        "status": "OPEN",
        "devices": [
            {
                "name": "Samsung Galaxy Watch 7",
                "device_status": "PENDING",
                "status_detail": "Being prepared for shipment at distribution center",
                "estimated_ship_date": "July 1, 2026",
                "estimated_delivery": "July 3-5, 2026",
                "tracking": "Not yet available — tracking number assigned once shipped",
                "shipping_method": "Standard Post (Swiss Post)",
            }
        ],
        "shipping_address": "Bahnhofstrasse 42, 8001 Zürich",
        "payment_method": "Monthly bill",
        "order_total": "CHF 299.00",
    },
    "ORD-20260615-002": {
        "id": "ORD-20260615-002",
        "date": "June 15, 2026",
        "status": "COMPLETE",
        "devices": [
            {
                "name": "Internet Box 3 Router",
                "device_status": "COMPLETE",
                "status_detail": "Delivered June 18, 2026 — signed by M. Müller",
                "tracking": "POST-CH-98234857",
                "shipping_method": "Priority Post (Swiss Post)",
            }
        ],
        "shipping_address": "Bahnhofstrasse 42, 8001 Zürich",
        "payment_method": "Monthly bill",
        "order_total": "CHF 0.00 (included with subscription)",
    },
}


# ============================================================
# TELECOM: SIM MANAGEMENT
# ============================================================

# IMEI intentionally omitted from status — callers must use get_device_info
# for IMEI/serial so the model cannot cite status as a shortcut.
SIM_STATUS = {
    "line_id": "LINE_001",
    "number": "ending 4821",
    "name": "Primary — John",
    "sim_type": "nano-SIM",
    "is_blocked": False,
    "device": "iPhone 15 Pro",
    "esim_compatible": True,
}

DEVICE_INFO = {
    "line_id": "LINE_001",
    "device": "iPhone 15 Pro",
    "imei": "352345678901234",
    "serial_number": "F2LZK1HQGRX",
    "purchase_date": "September 22, 2024",
    "warranty_status": "AppleCare+ active until September 2026",
    "note": "Keep the IMEI number for police reports or insurance claims.",
}

DEVICE_RECOVERY = {
    "line_id": "LINE_001",
    "find_my_device": "Enabled — locate via iCloud.com/find or Find My app",
}


# ============================================================
# TELECOM: PLAN MANAGEMENT
# ============================================================

CURRENT_PLAN = {
    "plan_name": "Essential",
    "monthly_cost": 45.00,
    "data_allowance_gb": 40,
    "data_used_gb": 37.4,
    "hotspot": False,
    "international_texting": False,
    "international_calling": False,
    "contract": {
        "type": "2-year",
        "start_date": "October 15, 2024",
        "end_date": "October 14, 2026",
        "months_remaining": 8,
    },
}

AVAILABLE_PLANS = [
    {
        "id": "essential_plus",
        "name": "Essential Plus",
        "monthly_cost": 55.00,
        "data_gb": 50,
        "hotspot": False,
        "international_texting": False,
        "international_calling": False,
    },
    {
        "id": "premium",
        "name": "Premium",
        "monthly_cost": 75.00,
        "data_gb": 100,
        "hotspot": True,
        "hotspot_data_gb": 15,
        "international_texting": False,
        "international_calling": False,
    },
    {
        "id": "ultimate",
        "name": "Ultimate",
        "monthly_cost": 95.00,
        "data_gb": "Unlimited",
        "hotspot": True,
        "hotspot_data_gb": "Unlimited",
        "international_texting": True,
        "international_calling": True,
    },
]

PLAN_ADDONS = [
    {
        "id": "intl_texting",
        "name": "International Texting",
        "monthly_cost": 10.00,
        "compatible_plans": ["essential", "essential_plus", "premium"],
    },
    {
        "id": "intl_calling",
        "name": "International Calling",
        "monthly_cost": 15.00,
        "compatible_plans": ["essential", "essential_plus", "premium"],
    },
    {
        "id": "extra_hotspot_10gb",
        "name": "Extra Hotspot 10GB",
        "monthly_cost": 10.00,
        "compatible_plans": ["premium"],
    },
]

PLAN_COSTS: dict[str, float] = {
    "essential": 45.00,
    "essential_plus": 55.00,
    "premium": 75.00,
    "ultimate": 95.00,
}

ADDON_COSTS: dict[str, float] = {
    "intl_texting": 10.00,
    "intl_calling": 15.00,
    "extra_hotspot_10gb": 10.00,
}

PLAN_NAMES: dict[str, str] = {
    "essential_plus": "Essential Plus",
    "premium": "Premium",
    "ultimate": "Ultimate",
}

CONTRACT_STATUS = {
    "contract_type": "2-year",
    "start_date": "October 15, 2024",
    "end_date": "October 14, 2026",
    "months_remaining": 8,
    "etf_if_cancelled": 120.00,
    "etf_if_downgraded": 120.00,
    "etf_if_upgraded": 0.00,
    "etf_if_same_tier": 0.00,
    "note": "No ETF for upgrading to a higher-tier plan. $120 fee applies for downgrading or full cancellation.",
}

CURRENT_USAGE = {
    "billing_cycle_end": "June 30, 2026",
    "days_remaining": 3,
    "data_used_gb": 42,
    "data_limit_gb": 40,
    "overage": True,
    "overage_gb": 2,
    "overage_cost": 20.00,
    "usage_last_6_months_gb": [38, 47, 40, 45, 39, 42],
    "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
    "note": "You've exceeded 45GB in 3 of the last 6 months.",
}


# ============================================================
# TELECOM: FAMILY PLAN ADVISORY
# ============================================================

FAMILY_LINES = {
    "plan": "Family Essential",
    "monthly_cost": 180.00,
    "lines": [
        {"line_id": "FAM_001", "name": "Primary", "number": "ending 4821"},
        {"line_id": "FAM_002", "name": "Spouse", "number": "ending 7734"},
        {"line_id": "FAM_003", "name": "Child 1", "number": "ending 3392"},
        {"line_id": "FAM_004", "name": "Child 2", "number": "ending 8819"},
    ],
}

USAGE_BY_LINE = [
    {
        "line_id": "FAM_001",
        "name": "Primary",
        "usage_gb": 45,
        "avg_last_3_months_gb": 43,
    },
    {
        "line_id": "FAM_002",
        "name": "Spouse",
        "usage_gb": 12,
        "avg_last_3_months_gb": 11,
    },
    {"line_id": "FAM_003", "name": "Child 1", "usage_gb": 8, "avg_last_3_months_gb": 9},
    {
        "line_id": "FAM_004",
        "name": "Child 2",
        "usage_gb": 62,
        "avg_last_3_months_gb": 58,
    },
]

INDIVIDUAL_PLAN_COSTS = {
    "individual_costs": [
        {
            "line": "Primary (45GB avg)",
            "recommended_plan": "Essential Plus 50GB",
            "monthly_cost": 55.00,
        },
        {
            "line": "Spouse (11GB avg)",
            "recommended_plan": "Basic 15GB",
            "monthly_cost": 35.00,
        },
        {
            "line": "Child 1 (9GB avg)",
            "recommended_plan": "Basic 15GB",
            "monthly_cost": 35.00,
        },
        {
            "line": "Child 2 (58GB avg)",
            "recommended_plan": "Ultimate Unlimited",
            "monthly_cost": 75.00,
        },
    ],
    "total_individual_cost": 200.00,
    "current_family_plan_cost": 180.00,
    "family_plan_saves": 20.00,
    "analysis": (
        "Family plan saves $20/month. The savings come from the lighter users (Spouse, Child 1) "
        "being subsidized under the family tier. If you split them off, the heavy users would "
        "drive total costs higher."
    ),
}


# ============================================================
# TELECOM: SERVICE TROUBLESHOOTING
# ============================================================

DIAGNOSTICS = {
    "signal_strength_dbm": -98,
    "signal_quality": "Weak — below -90 dBm indicates a struggling connection",
    "signal_issue": "Tower-side (not device-side): tower distance 2.8 km with obstructions",
    "download_speed_mbps": 2.1,
    "expected_download_mbps": 25.0,
    "upload_speed_mbps": 0.8,
    "latency_ms": 180,
    "network_congestion": "High in your area (ZIP 94105)",
    "congestion_peak_hours": "5 PM – 9 PM",
    "issue_type": "Combined: weak signal + high network congestion",
    "diagnosis": (
        "Your signal of -98 dBm is quite weak — anything below -90 dBm means your phone is "
        "struggling to hold a stable connection. Combined with high congestion in your area, "
        "this is a tower-side problem, not your phone. The booster would help at home; "
        "priority data would help everywhere."
    ),
}


# ============================================================
# TELECOM: DATA USAGE
# ============================================================

USAGE_BY_CATEGORY = {
    "billing_cycle_end": "June 30, 2026",
    "total_used_gb": 37.4,
    "plan_limit_gb": 40,
    "remaining_gb": 2.6,
    "categories": {
        "streaming": {"gb": 18.2, "top_apps": ["YouTube", "Netflix", "Spotify"]},
        "social_media": {"gb": 8.4, "top_apps": ["TikTok", "Instagram", "Twitter"]},
        "app_updates": {"gb": 5.6, "note": "Call get_usage_detail for app breakdown"},
        "web_browsing": {"gb": 3.1},
        "other": {"gb": 2.1},
    },
}

USAGE_DETAILS: dict[str, dict[str, Any]] = {
    "app_updates": {
        "category": "App Updates",
        "total_gb": 5.6,
        "breakdown": [
            {"app": "iOS System Update (17.5)", "gb": 2.1},
            {"app": "Game updates (Clash of Clans, PUBG, Genshin)", "gb": 2.2},
            {"app": "Instagram app update", "gb": 1.3},
        ],
        "tip": "Go to Settings > App Store > turn off 'App Updates' over cellular to use Wi-Fi only.",
    },
    "streaming": {
        "category": "Streaming",
        "total_gb": 18.2,
        "breakdown": [
            {"app": "YouTube", "gb": 9.4, "hours_approx": 47},
            {"app": "Netflix", "gb": 6.8, "hours_approx": 34},
            {"app": "Spotify", "gb": 2.0, "hours_approx": 320},
        ],
        "tip": "Downloading content on Wi-Fi before leaving home can significantly cut cellular streaming.",
    },
    "social_media": {
        "category": "Social Media",
        "total_gb": 8.4,
        "breakdown": [
            {"app": "TikTok", "gb": 4.2},
            {"app": "Instagram", "gb": 2.8},
            {"app": "Twitter/X", "gb": 1.4},
        ],
    },
}

USAGE_HISTORY_APP_UPDATES = [
    {"month": "April 2026", "gb": 2.8},
    {"month": "May 2026", "gb": 3.1},
    {"month": "June 2026", "gb": 5.6},
]

USAGE_HISTORY_TOTAL = [
    {"month": "April 2026", "gb": 35.2},
    {"month": "May 2026", "gb": 38.7},
    {"month": "June 2026", "gb": 37.4},
]


# ============================================================
# TELECOM: BILLING INVESTIGATION
# ============================================================

CURRENT_BILL = {
    "bill_period": "June 2026",
    "total_amount": 142.50,
    "due_date": "July 15, 2026",
    "auto_pay": True,
    "status": "Pending",
}

PREVIOUS_BILLS = [
    {"period": "May 2026", "total": 75.00, "status": "Paid"},
    {"period": "April 2026", "total": 78.00, "status": "Paid"},
    {"period": "March 2026", "total": 75.00, "status": "Paid"},
]

BILL_LINE_ITEMS: dict[str, dict[str, Any]] = {
    "june": {
        "period": "June 2026",
        "items": [
            {"description": "Essential Plan (40GB)", "amount": 45.00},
            {"description": "Taxes & Fees", "amount": 7.50},
            {
                "description": "International Roaming — Portugal (Jun 12-14)",
                "amount": 45.00,
                "flag": "unusual",
            },
            {
                "description": "Data Overage — 2GB @ $10/GB",
                "amount": 20.00,
                "flag": "unusual",
            },
            {
                "description": "Line ending 5578 — monthly service",
                "amount": 35.00,
                "flag": "error — line was cancelled Apr 28",
            },
        ],
        "total": 142.50,
    },
    "may": {
        "period": "May 2026",
        "items": [
            {"description": "Essential Plan (40GB)", "amount": 40.00},
            {
                "description": "Line ending 5578 — monthly service",
                "amount": 35.00,
                "flag": "error — line was cancelled Apr 28",
            },
        ],
        "total": 75.00,
    },
}

CHARGE_EXPLANATIONS: dict[str, dict[str, Any]] = {
    "intl_roaming": {
        "charge": "International Roaming — Portugal",
        "amount": 45.00,
        "explanation": "Your phone automatically connected to partner networks in Portugal Jun 12-14. Charged at $15/day for 3 days.",
        "prevention": "Add an International Day Pass ($10/day) before traveling — it replaces per-use roaming with a flat daily rate and saves money.",
    },
    "data_overage": {
        "charge": "Data Overage",
        "amount": 20.00,
        "explanation": "You used 42GB against your 40GB Essential plan limit. The 2GB overage is billed at $10/GB.",
        "prevention": "Consider upgrading to Essential Plus (50GB, $55/mo) or setting a data usage alert in the app.",
    },
    "cancelled_line": {
        "charge": "Line ending 5578 — cancelled line still being billed",
        "amount": 35.00,
        "explanation": "This line was cancelled April 28, 2026 but a system error prevented billing from being terminated. This is an incorrect charge.",
        "resolution": "Eligible for a full credit. Call create_billing_adjustment to process.",
    },
}

ACTIVE_LINES = [
    {
        "line_id": "LINE_001",
        "number": "ending 4821",
        "name": "Primary — John",
        "status": "Active",
        "plan": "Essential",
    },
    {
        "line_id": "LINE_002",
        "number": "ending 7734",
        "name": "Spouse — Jane",
        "status": "Active",
        "plan": "Essential",
    },
]

CANCELLED_LINES = [
    {
        "line_id": "LINE_003",
        "number": "ending 5578",
        "name": "Kid's Phone",
        "status": "Cancelled",
        "cancelled_date": "April 28, 2026",
        "monthly_charge": 35.00,
        "cancellation_method": "Customer request via app",
    },
]

LINE_HISTORY_5578 = {
    "line_id": "LINE_003",
    "number": "ending 5578",
    "events": [
        {
            "date": "March 1, 2024",
            "event": "Line activated",
            "method": "Store activation",
        },
        {
            "date": "April 28, 2026",
            "event": "Cancellation requested by customer",
            "method": "Mobile app",
        },
        {
            "date": "April 28, 2026",
            "event": "Cancellation processed — service terminated",
        },
        {
            "date": "April 28, 2026",
            "event": "⚠ Billing termination NOT applied",
            "note": "System error: billing flag was not set during cancellation",
        },
    ],
    "billing_status": "ERROR — Line cancelled but billing continued for May and June",
    "months_incorrectly_billed": 2,
    "total_incorrect_charges": 70.00,
}
