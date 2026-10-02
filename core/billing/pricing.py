"""
Monetization Pricing Tiers, Action Costs, and SEBI-Compliant Invoice Metadata.

Approved Option 2 (+30% markup) unit economics and deliverables.
"""

from typing import Dict, Any, List

# Computational credit action cost schedule
ACTION_COSTS: Dict[str, float] = {
    "LIVE_SYNTHESIS": 1.0,      # Full 7-pillar institutional synthesis + valuation + PDF
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
        "credits": 1.0,
        "effective_per_stock": "₹299/dossier",
        "description": "Full institutional research dossier for 1 equity with PDF export.",
        "features": [
            "1 Full 7-Pillar Institutional Synthesis",
            "Multi-Scenario DCF & Multiples Valuation",
            "Institutional PDF Report Export",
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
        "credits": 3.0,
        "effective_per_stock": "₹233/dossier (22% savings)",
        "description": "Ideal for sector deep-dives and comparing top 3 peer contenders.",
        "features": [
            "3 Full 7-Pillar Syntheses",
            "Surgical Announcement Refreshes",
            "Multi-Quarter Thesis Drift Surveillance",
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
        "credits": 10.0,
        "effective_per_stock": "₹180/dossier (40% savings)",
        "description": "Comprehensive institutional audit for an entire equity portfolio.",
        "features": [
            "10 Full 7-Pillar Syntheses",
            "10 Watched Equities in Real-Time Surveillance",
            "Priority AI Synthesis Pipeline",
            "Complete Audit Ledgers & Revisions",
            "Never expires"
        ],
        "is_subscription": False,
        "is_popular": False,
    },
    "pro_monthly": {
        "id": "pro_monthly",
        "name": "Institutional Pro (Monthly)",
        "badge": "Pro Desk",
        "amount_inr": 999,
        "credits": 40.0,
        "billing_period": "month",
        "effective_per_stock": "₹25/stock (Active Tier)",
        "description": "Continuous surveillance engine for full-time investors and advisors.",
        "features": [
            "40 Fresh 7-Pillar Syntheses / month",
            "Unlimited Surgical Updates (0 credits)",
            "50 Watched Equities in Real-Time Surveillance",
            "Unlimited Institutional PDF Exports",
            "Telegram & WhatsApp Alert Feeds",
            "Auto-renews monthly, cancel anytime"
        ],
        "is_subscription": True,
        "is_popular": False,
    },
    "pro_annual": {
        "id": "pro_annual",
        "name": "Institutional Pro (Annual)",
        "badge": "Annual VIP",
        "amount_inr": 8999,
        "credits": 500.0,
        "billing_period": "year",
        "effective_per_stock": "₹750/mo (25% annual discount)",
        "description": "Maximum institutional power for high-conviction equity portfolios.",
        "features": [
            "500 Fresh 7-Pillar Syntheses / year",
            "Unlimited Surgical Updates (0 credits)",
            "Uncapped Watchlist Equities",
            "Dedicated API Webhook & Headless Export Access",
            "Priority VIP Processing Pipeline"
        ],
        "is_subscription": True,
        "is_popular": False,
    },
}

# Enterprise & Bulk Institutional Packs
B2B_PACKS: Dict[str, Dict[str, Any]] = {
    "b2b_50": {
        "id": "b2b_50",
        "name": "Corporate 50-Pack",
        "amount_inr": 5999,
        "credits": 50.0,
        "effective_per_stock": "₹120/dossier",
        "target": "Family Offices & Small Advisory Teams"
    },
    "b2b_150": {
        "id": "b2b_150",
        "name": "Enterprise 150-Pack",
        "amount_inr": 16999,
        "credits": 150.0,
        "effective_per_stock": "₹113/dossier",
        "target": "Institutional Desks & Wealth Managers"
    },
}

# SEBI-Compliant Invoice Metadata
INVOICE_SERVICE_DESCRIPTION = "Financial Research Synthesis Software Utility — Computational Research Credits"
INVOICE_SAC_CODE = "998314"  # Information Technology Software Services
INVOICE_DISCLAIMER = (
    "Non-Advisory Disclosure: This invoice covers automated software compute and API research aggregation units. "
    "This service does not constitute investment advice, research analyst recommendations under SEBI (Research Analysts) "
    "Regulations 2014, or portfolio management services. Past performance does not guarantee future results."
)


def get_plan_by_id(plan_id: str) -> Dict[str, Any]:
    """Retrieves plan details by plan identifier."""
    if plan_id in PRICING_PACKS:
        return PRICING_PACKS[plan_id]
    if plan_id in B2B_PACKS:
        return B2B_PACKS[plan_id]
    return {}


def get_all_active_plans() -> List[Dict[str, Any]]:
    """Returns list of active public pricing plans."""
    return list(PRICING_PACKS.values())
