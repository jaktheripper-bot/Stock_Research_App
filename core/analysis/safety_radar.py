"""Analytical Engine for Retail Safety & Shadow-Banking Diagnostic Radar.

Audits unregulated alternative yield products (Gold Leasing, P2P Lending, Sub-Investment Grade Corporate FDs)
to compute a 0-100 Danger Score based on regulatory status, counterparty risk, and bankruptcy reality.
"""

from typing import Dict, Any, List, Optional
from core.db.safety_radar import get_all_safety_radar_products, save_alternative_yield_product


def audit_alternative_yield_radar(category: Optional[str] = None) -> Dict[str, Any]:
    """Audits shadow-banking alternative yield schemes and computes risk alerts."""
    products = get_all_safety_radar_products(category=category)

    extreme_danger_count = sum(1 for p in products if p["danger_score"] >= 80)
    unregulated_count = sum(1 for p in products if "UNREGULATED" in p["regulatory_status"])

    # Group by risk severity
    high_danger_schemes = [p for p in products if p["danger_score"] >= 75]
    moderate_danger_schemes = [p for p in products if 40 <= p["danger_score"] < 75]
    safe_sovereign_schemes = [p for p in products if p["danger_score"] < 40]

    return {
        "total_schemes_audited": len(products),
        "extreme_danger_count": extreme_danger_count,
        "unregulated_count": unregulated_count,
        "high_danger_schemes": high_danger_schemes,
        "moderate_danger_schemes": moderate_danger_schemes,
        "safe_sovereign_schemes": safe_sovereign_schemes,
        "all_products": products
    }
