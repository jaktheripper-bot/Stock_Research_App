"""
Monetization Pricing Tiers, Action Costs, and SEBI-Compliant Invoice Metadata.

Approved Option 2 (+30% markup) unit economics and deliverables.
"""

from typing import Dict, Any, List

# Research credit action cost schedule
ACTION_COSTS: Dict[str, float] = {
    "LIVE_SYNTHESIS": 1.0,      # Full 7-pillar synthesis + valuation + PDF
    "DEEP_DIVE_UNLOCK": 1.0,    # Unlocks Accounting Ledger, Reverse DCF Sandbox & Thesis Drift
    "SURGICAL_REFRESH": 0.25,   # Pillars 5 & 6 announcement incremental delta (Free for Pro)
    "PDF_EXPORT": 0.0,          # Free for active and archived reports
    "ARCHIVE_READ": 0.0,        # Free archival retrieval
    "EXCHANGE_QUOTE": 0.0,      # Free real-time quote lookups
}

# Standard On-Demand Packs & Subscriptions
PRICING_PACKS: Dict[str, Dict[str, Any]] = {
    "single_pass": {
        "id": "single_pass",
        "name": "Single Research Pass",
        "badge": "On-Demand",
        "amount_inr": 299,
        "amount_paise": 29900,
        "credits": 1.0,
        "effective_per_stock": "₹299/dossier",
        "description": "Full research dossier for 1 equity with PDF export.",
        "features": [
            "1 Full 7-Pillar Stock Report",
            "Multi-Scenario DCF & Multiples Valuation",
            "PDF Report Export",
            "Full Exchange Source Footnotes & Citations",
            "Never expires"
        ],
        "is_subscription": False,
        "is_popular": False,
    },
    "analyst_3pack": {
        "id": "analyst_3pack",
        "name": "Analyst 3-Pack",
        "badge": "Most Popular",
        "amount_inr": 699,
        "amount_paise": 69900,
        "credits": 3.0,
        "effective_per_stock": "₹233/dossier (22% savings)",
        "description": "Ideal for sector deep-dives and comparing top 3 peer contenders.",
        "features": [
            "3 Full 7-Pillar Stock Reports",
            "Price & Filing Updates",
            "Multi-Quarter Thesis Drift Monitoring",
            "Unlimited PDF Downloads",
            "Never expires"
        ],
        "is_subscription": False,
        "is_popular": True,
    },
    "portfolio_10pack": {
        "id": "portfolio_10pack",
        "name": "Portfolio 10-Pack",
        "badge": "Best Value",
        "amount_inr": 1799,
        "amount_paise": 179900,
        "credits": 10.0,
        "effective_per_stock": "₹180/dossier (40% savings)",
        "description": "Comprehensive audit for an entire equity portfolio.",
        "features": [
            "10 Full 7-Pillar Stock Reports",
            "10 Watched Equities in Real-Time Monitoring",
            "Priority Report Generation",
            "Complete Audit Ledgers & Revisions",
            "Never expires"
        ],
        "is_subscription": False,
        "is_popular": False,
    },
    "pro_monthly": {
        "id": "pro_monthly",
        "name": "Pro (Monthly)",
        "badge": "Pro Desk",
        "amount_inr": 999,
        "amount_paise": 99900,
        "credits": 40.0,
        "billing_period": "month",
        "effective_per_stock": "₹25/stock (Active Tier)",
        "description": "Continuous monitoring engine for full-time investors and advisors.",
        "features": [
            "40 Fresh 7-Pillar Stock Reports / month",
            "Unlimited Price & Filing Updates (0 credits)",
            "50 Watched Equities in Real-Time Monitoring",
            "Unlimited PDF Report Exports",
            "Telegram & WhatsApp Alert Feeds",
            "Auto-renews monthly, cancel anytime"
        ],
        "is_subscription": True,
        "is_popular": False,
    },
    "pro_annual": {
        "id": "pro_annual",
        "name": "Pro (Annual)",
        "badge": "Annual VIP",
        "amount_inr": 8999,
        "amount_paise": 899900,
        "credits": 500.0,
        "billing_period": "year",
        "effective_per_stock": "₹750/mo (25% annual discount)",
        "description": "Maximum power for high-conviction equity portfolios.",
        "features": [
            "500 Fresh 7-Pillar Stock Reports / year",
            "Unlimited Price & Filing Updates (0 credits)",
            "Uncapped Watchlist Equities",
            "Dedicated API Webhook & Headless Export Access",
            "Priority VIP Processing Pipeline"
        ],
        "is_subscription": True,
        "is_popular": False,
    },
}

# Enterprise & Bulk Packs
B2B_PACKS: Dict[str, Dict[str, Any]] = {
    "b2b_50": {
        "id": "b2b_50",
        "name": "Corporate 50-Pack",
        "amount_inr": 5999,
        "amount_paise": 599900,
        "credits": 50.0,
        "effective_per_stock": "₹120/dossier",
        "target": "Family Offices & Small Advisory Teams"
    },
    "b2b_150": {
        "id": "b2b_150",
        "name": "Enterprise 150-Pack",
        "amount_inr": 16999,
        "amount_paise": 1699900,
        "credits": 150.0,
        "effective_per_stock": "₹113/dossier",
        "target": "Desks & Wealth Managers"
    },
}

from core.db.compliance import MANDATORY_SEBI_DISCLAIMER

# Invoice Metadata
INVOICE_SERVICE_DESCRIPTION = "Financial Research Synthesis Software Utility — Research Credits"
INVOICE_SAC_CODE = ""
INVOICE_DISCLAIMER = MANDATORY_SEBI_DISCLAIMER


def get_plan_by_id(plan_id: str) -> Dict[str, Any]:
    """Retrieves plan details by plan identifier."""
    if plan_id in PRICING_PACKS:
        p = dict(PRICING_PACKS[plan_id])
        if "amount_paise" not in p:
            p["amount_paise"] = int(p.get("amount_inr", 0) * 100)
        return p
    if plan_id in B2B_PACKS:
        p = dict(B2B_PACKS[plan_id])
        if "amount_paise" not in p:
            p["amount_paise"] = int(p.get("amount_inr", 0) * 100)
        return p
    return {}


def get_all_active_plans() -> List[Dict[str, Any]]:
    """Returns list of active public pricing plans."""
    return list(PRICING_PACKS.values())
