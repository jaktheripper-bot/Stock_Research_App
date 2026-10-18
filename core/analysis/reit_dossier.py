"""Statutory Section 115UA Tax Waterfall & Institutional REIT Dossier Engine.

Enforces statutory and quantitative mathematical invariants for REITs, SM REITs, and InvITs:
1. Section 115UA waterfall splits must sum to 100.0% (+/- 0.01%).
2. Net Post-Tax Yield <= Gross Pre-Tax Yield.
3. Post-Tax Real Yield (inflation adjusted) <= Pre-Tax Yield.
"""

import logging
from typing import Dict, Any, List, Optional, Union

from core.db.reits import get_all_reits_and_invits, get_reit_by_symbol, save_reit_or_invit
from core.analysis.sm_reit_invit_engine import (
    audit_reit_portfolio,
    get_reit_detail,
)

logger = logging.getLogger(__name__)


def validate_section_115ua_waterfall(tax_breakdown: Dict[str, float]) -> Dict[str, float]:
    """Validates that Section 115UA cash flow distribution splits sum to 100.0% (+/- 0.01%).

    Section 115UA cash flow components:
    - dividend_pct
    - interest_pct
    - return_of_capital_pct (amortization_pct)
    - rental_pct
    """
    div_pct = float(tax_breakdown.get("dividend_pct", 0.0))
    int_pct = float(tax_breakdown.get("interest_pct", 0.0))
    roc_pct = float(
        tax_breakdown.get("return_of_capital_pct")
        if "return_of_capital_pct" in tax_breakdown
        else tax_breakdown.get("amortization_pct", 0.0)
    )
    rent_pct = float(tax_breakdown.get("rental_pct", 0.0))

    total = div_pct + int_pct + roc_pct + rent_pct

    if abs(total - 100.0) > 0.01:
        raise ValueError(
            f"Section 115UA Waterfall Invariant Violated: Distribution splits must sum to 100.0% (+/- 0.01%). "
            f"Got {total:.4f}% (div={div_pct}%, int={int_pct}%, roc={roc_pct}%, rent={rent_pct}%)."
        )

    return {
        "dividend_pct": round(div_pct, 4),
        "interest_pct": round(int_pct, 4),
        "return_of_capital_pct": round(roc_pct, 4),
        "amortization_pct": round(roc_pct, 4),
        "rental_pct": round(rent_pct, 4),
    }


def simulate_reit_tax_waterfall(
    target: Union[str, Dict[str, Any]],
    tax_slab_pct: float = 30.0,
    inflation_pct: float = 5.0
) -> Dict[str, Any]:
    """Calculates post-tax distribution yield decomposing cash flows under Section 115UA.

    Enforces quantitative invariants:
    1. Waterfall splits sum to 100.0% (+/- 0.01%).
    2. Net Post-Tax Yield <= Gross Pre-Tax Yield.
    3. Post-Tax Real Yield <= Gross Pre-Tax Yield.
    """
    if isinstance(target, str):
        reit = get_reit_by_symbol(target)
        if not reit:
            raise ValueError(f"Asset {target} not found in database.")
    elif isinstance(target, dict):
        reit = target
    else:
        raise TypeError("target must be a ticker string or REIT dict")

    gross_yield = float(reit.get("distribution_yield_pct", 0.0))
    details = reit.get("details", {})
    raw_splits = details.get("tax_breakdown") or reit.get("tax_breakdown") or {
        "dividend_pct": 35.0,
        "interest_pct": 35.0,
        "amortization_pct": 30.0,
        "rental_pct": 0.0
    }

    validated_splits = validate_section_115ua_waterfall(raw_splits)
    div_pct = validated_splits["dividend_pct"]
    int_pct = validated_splits["interest_pct"]
    roc_pct = validated_splits["return_of_capital_pct"]
    rent_pct = validated_splits["rental_pct"]

    # Calculate statutory effective blended tax drag
    # Interest: Slab rate
    tax_on_interest = (int_pct / 100.0) * (tax_slab_pct / 100.0)
    # Rental: Pass-through at slab rate
    tax_on_rental = (rent_pct / 100.0) * (tax_slab_pct / 100.0)
    # Dividend: 0% if SPV paid 115BAA corporate tax, or partial concession
    tax_on_dividend = (div_pct / 100.0) * 0.5 * (tax_slab_pct / 100.0)
    # Return of capital (Amortization): 0% tax drag up to cost of acquisition
    tax_on_roc = 0.0

    blended_tax_rate = tax_on_interest + tax_on_rental + tax_on_dividend + tax_on_roc
    net_post_tax_yield = gross_yield * (1.0 - blended_tax_rate)
    post_tax_real_yield = net_post_tax_yield - inflation_pct
    tax_drag_bps = (gross_yield - net_post_tax_yield) * 100.0

    # Invariant Enforcement: Post-Tax Real Yield <= Pre-Tax Yield
    if net_post_tax_yield > (gross_yield + 1e-4):
        raise ValueError(
            f"Quantitative Invariant Violated: Net post-tax yield ({net_post_tax_yield:.2f}%) "
            f"exceeds pre-tax yield ({gross_yield:.2f}%)."
        )

    if post_tax_real_yield > (gross_yield + 1e-4):
        raise ValueError(
            f"Quantitative Invariant Violated: Post-tax real yield ({post_tax_real_yield:.2f}%) "
            f"exceeds pre-tax yield ({gross_yield:.2f}%)."
        )

    symbol = reit.get("symbol", "CUSTOM_REIT")
    name = reit.get("name", symbol)
    structure_type = reit.get("structure_type", "MAINBOARD_REIT")

    return {
        "symbol": symbol,
        "name": name,
        "structure_type": structure_type,
        "gross_distribution_yield_pct": round(gross_yield, 2),
        "investor_tax_slab_pct": round(tax_slab_pct, 2),
        "blended_tax_rate_pct": round(blended_tax_rate * 100.0, 2),
        "net_post_tax_yield_pct": round(net_post_tax_yield, 2),
        "inflation_pct": round(inflation_pct, 2),
        "post_tax_real_yield_pct": round(post_tax_real_yield, 2),
        "tax_drag_bps": round(tax_drag_bps, 1),
        "tax_breakdown_weights": validated_splits,
        "tax_treatment_summary": (
            f"At a {tax_slab_pct}% tax slab, {symbol} delivers a net in-hand distribution yield of "
            f"{net_post_tax_yield:.2f}% (vs {gross_yield:.2f}% gross pre-tax), with a real purchasing power yield of "
            f"{post_tax_real_yield:.2f}% after {inflation_pct}% CPI inflation."
        )
    }
