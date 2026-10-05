"""Analytical Engine for National ETF Matrix, Tracking Error Auditing, and Liquidity Tiers.

Evaluates exchange pricing vs. NAV, tracking difference, expense ratio drag, and Amihud liquidity tiers.
"""

from typing import Dict, Any, List, Optional
from core.db.sovereign import get_etf_matrix, save_etf_matrix_item


def evaluate_etf_matrix(category: Optional[str] = None) -> Dict[str, Any]:
    """Audits the ETF matrix, identifying arbitrage divergences and liquidity risk tiers."""
    etfs = get_etf_matrix(category=category)

    total_aum = sum(item["aum_crores"] for item in etfs)
    high_liquidity_count = sum(1 for item in etfs if item["liquidity_tier"] == "HIGH_LIQUIDITY")
    divergence_count = sum(1 for item in etfs if abs(item["premium_discount_pct"]) >= 0.5)

    # Sort into categories for tabbed views
    categories = {
        "ALL": etfs,
        "EQUITY_INDEX": [x for x in etfs if x["category"] == "EQUITY_INDEX"],
        "COMMODITY": [x for x in etfs if "COMMODITY" in x["category"]],
        "DEBT_SOVEREIGN": [x for x in etfs if "DEBT" in x["category"] or x["category"] == "LIQUID"]
    }

    return {
        "total_tracked_etfs": len(etfs),
        "total_aum_crores": round(total_aum, 1),
        "high_liquidity_count": high_liquidity_count,
        "nav_divergence_alerts": divergence_count,
        "etfs": etfs,
        "grouped_by_category": categories
    }
