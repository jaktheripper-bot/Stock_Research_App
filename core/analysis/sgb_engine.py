"""Analytical Engine for Sovereign Gold Bonds (SGB) Secondary Market Discount & Tax Parity.

Models annualized Yield-to-Maturity (YTM), secondary market discount vs spot gold,
and tax-adjusted yield advantage over Gold ETFs (Budget 2024 12.5% LTCG + TER drag)
under Section 47(viic) of the Income Tax Act.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from core.db.reits import get_all_sgb_tranches, get_sgb_by_symbol, save_sgb_tranche


def evaluate_sgb_market() -> Dict[str, Any]:
    """Audits all active SGB tranches trading on NSE/BSE secondary markets."""
    tranches = get_all_sgb_tranches()

    count = len(tranches)
    avg_ytm = round(sum(x["ytm_annualized_pct"] for x in tranches) / count, 2) if count else 0.0
    avg_disc = round(sum(x["discount_to_spot_pct"] for x in tranches) / count, 2) if count else 0.0

    best_ytm_tranche = max(tranches, key=lambda x: x["ytm_annualized_pct"]) if tranches else None
    deepest_discount_tranche = min(tranches, key=lambda x: x["discount_to_spot_pct"]) if tranches else None
    shortest_tranche = min(tranches, key=lambda x: x["maturity_date"]) if tranches else None
    longest_tranche = max(tranches, key=lambda x: x["maturity_date"]) if tranches else None

    # Institutional Comparative Asset Matrix (SGB vs Gold ETF vs Physical Gold)
    asset_comparison = [
        {
            "dimension": "Acquisition Friction / Entry Pricing",
            "sgb": "3% to 5% Secondary Discount to 999 Spot",
            "gold_etf": "At Par / NAV with 0.1% to 0.3% Market Spread",
            "physical_gold": "3% GST + 5% to 15% Making Charges"
        },
        {
            "dimension": "Ongoing Holding Return / Yield",
            "sgb": "+2.50% p.a. Sovereign Interest (Semi-Annual)",
            "gold_etf": "-0.50% p.a. Total Expense Ratio Drag",
            "physical_gold": "0% Yield + Bank Locker / Insurance Costs"
        },
        {
            "dimension": "Capital Gains Taxation at Redemption",
            "sgb": "100% Tax-Free (Section 47(viic) for Individuals)",
            "gold_etf": "12.5% LTCG (Budget 2024 Amendment)",
            "physical_gold": "12.5% LTCG (Holding Period > 24 Months)"
        },
        {
            "dimension": "Counterparty & Default Risk",
            "sgb": "Zero Default Risk (Government of India Sovereign)",
            "gold_etf": "Mutual Fund Trustee / Physical Vault Custodian",
            "physical_gold": "Purity & Storage Security Risk"
        }
    ]

    macro_takeaways = [
        "SGB Supply Scarcity Window: Following the Union Budget 2024 gold import duty cut and suspension of primary issuances, secondary SGBs represent a finite, closed-ended institutional asset.",
        "Secondary Discount Liquidity Premium: Illiquidity in exchange cash segments creates systematic mispricings, allowing astute allocators to acquire pure sovereign gold below bullion market parity.",
        "Statutory Tax Exemption Shield: Section 47(viic) guarantees 100% exemption from capital gains tax upon redemption at maturity, generating an unreplicable 200+ bps annualized hurdle over Gold ETFs."
    ]

    return {
        "total_tranches_tracked": count,
        "average_annualized_ytm_pct": avg_ytm,
        "average_discount_to_spot_pct": avg_disc,
        "spot_gold_reference_inr": 7450.0,
        "best_yield_tranche": best_ytm_tranche,
        "deepest_discount_tranche": deepest_discount_tranche,
        "shortest_tranche": shortest_tranche,
        "longest_tranche": longest_tranche,
        "asset_comparison": asset_comparison,
        "macro_takeaways": macro_takeaways,
        "tax_statute_citation": "Section 47(viic) of the Income Tax Act, 1961: Any transfer of Sovereign Gold Bonds issued by the Reserve Bank of India under the Sovereign Gold Bond Scheme, 2015, by way of redemption by an individual, is exempt from capital gains tax.",
        "tranches": tranches
    }
