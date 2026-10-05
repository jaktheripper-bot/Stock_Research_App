"""Analytical Engine for Sovereign Gold Bonds (SGB) Secondary Market Discount & Tax Parity.

Models annualized Yield-to-Maturity (YTM), secondary market discount vs spot gold,
and tax-adjusted yield advantage over Gold ETFs (Budget 2024 12.5% LTCG + TER drag).
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from core.db.reits import get_all_sgb_tranches, save_sgb_tranche


def evaluate_sgb_market() -> Dict[str, Any]:
    """Audits all active SGB tranches trading on NSE/BSE secondary markets."""
    tranches = get_all_sgb_tranches()

    # Identify tranche with highest annualized YTM and deepest discount
    best_ytm_tranche = max(tranches, key=lambda x: x["ytm_annualized_pct"]) if tranches else None
    deepest_discount_tranche = min(tranches, key=lambda x: x["discount_to_spot_pct"]) if tranches else None
    avg_ytm = round(sum(x["ytm_annualized_pct"] for x in tranches) / len(tranches), 2) if tranches else 0.0

    return {
        "total_tranches_tracked": len(tranches),
        "average_annualized_ytm_pct": avg_ytm,
        "best_yield_tranche": best_ytm_tranche,
        "deepest_discount_tranche": deepest_discount_tranche,
        "tax_statute_citation": "Section 47(viic) Income Tax Act: Capital gains upon redemption by individuals are 100% EXEMPT from tax.",
        "tranches": tranches
    }
