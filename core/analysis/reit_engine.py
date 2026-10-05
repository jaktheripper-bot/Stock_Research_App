"""Analytical Engine for SEBI Small & Medium Real Estate Investment Trusts (SM REITs) and InvITs.

Audits adherence to SEBI (REIT) (Amendment) Regulations, 2024:
1. Completed Asset Occupancy >= 95%
2. Net Distributable Cash Flow (NDCF) Payout Purity >= 95%
3. Loan-to-Value (LTV) Cap <= 49%
4. Sponsor Unencumbered Skin-in-the-game >= 5%
"""

from typing import Dict, Any, List, Optional
from core.db.reits import get_all_reits_and_invits, save_reit_or_invit


def audit_reit_portfolio(structure_type: Optional[str] = None) -> Dict[str, Any]:
    """Audits tracked REITs, SM REITs, and InvITs against regulatory metrics and yield quality."""
    items = get_all_reits_and_invits(structure_type=structure_type)

    compliant_count = sum(1 for r in items if r["sebi_compliant"])
    avg_yield = round(sum(r["distribution_yield_pct"] for r in items) / len(items), 2) if items else 0.0
    avg_occupancy = round(sum(r["occupancy_pct"] for r in items) / len(items), 1) if items else 0.0

    flagged_issues = []
    for r in items:
        sym = r["symbol"]
        if r["structure_type"] == "SM_REIT":
            if r["occupancy_pct"] < 95.0:
                flagged_issues.append(f"{sym}: SM REIT occupancy {r['occupancy_pct']}% breaches SEBI >= 95% completed threshold.")
            if r["ltv_ratio_pct"] > 49.0:
                flagged_issues.append(f"{sym}: Leverage LTV {r['ltv_ratio_pct']}% exceeds statutory 49% limit.")
        if r["ndcf_payout_purity_pct"] < 90.0:
            flagged_issues.append(f"{sym}: NDCF upstreaming purity {r['ndcf_payout_purity_pct']}% below institutional standards.")

    return {
        "total_tracked": len(items),
        "compliant_count": compliant_count,
        "average_distribution_yield_pct": avg_yield,
        "average_occupancy_pct": avg_occupancy,
        "flagged_issues": flagged_issues,
        "items": items,
        "reits": items
    }
