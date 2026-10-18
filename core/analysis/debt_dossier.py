"""Quantitative Fixed-Income & Institutional Debt Dossier Engine.

Enforces statutory and quantitative mathematical invariants for Debt, NCDs, and SDIs:
1. Modified Duration = Macaulay Duration / (1 + y/k) < Macaulay Duration for y > 0.
2. Positive Convexity in Rate-Shock Delta: Delta P / P = -D_mod * dy + 0.5 * C * (dy)^2.
3. Post-tax real return and purchasing power erosion under Indian tax slabs.
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple

from core.analysis.debt_engine import (
    calculate_time_to_maturity_years,
    generate_cash_flows,
    solve_ytm,
    calculate_tax_drag_and_real_return,
    evaluate_5_pillar_credit_posture,
    generate_issuer_profile,
    generate_executive_primer,
    generate_investment_thesis,
    determine_retail_suitability,
    evaluate_equity_cross_contagion,
    FREQUENCY_PERIODS,
    RATING_SCORES,
    DEFAULT_BENCHMARK_10Y_GSEC_YIELD,
)

logger = logging.getLogger(__name__)


def compute_duration_and_convexity(
    current_price: float,
    face_value: float,
    coupon_rate_pct: float,
    coupon_frequency: str,
    time_to_maturity_years: float,
    ytm_pct: float
) -> Dict[str, float]:
    """Computes Macaulay Duration, Modified Duration, and Convexity.

    Enforces quantitative invariant:
    Modified Duration = Macaulay Duration / (1 + y/k) < Macaulay Duration for y > 0.
    """
    if current_price <= 0 or time_to_maturity_years <= 0:
        return {
            "macaulay_duration": 0.0,
            "modified_duration": 0.0,
            "convexity": 0.0,
            "ytm_pct": round(float(ytm_pct), 2),
        }

    cash_flows = generate_cash_flows(face_value, coupon_rate_pct, coupon_frequency, time_to_maturity_years)
    k = FREQUENCY_PERIODS.get(coupon_frequency.upper(), 1)
    y = max(0.0, float(ytm_pct) / 100.0)

    weighted_time_sum = 0.0
    convexity_sum = 0.0

    for t, cf in cash_flows:
        discount = (1.0 + y / k) ** (k * t)
        pv_cf = cf / discount
        weighted_time_sum += t * pv_cf
        convexity_sum += pv_cf * (t ** 2 + t / k)

    macaulay_duration = weighted_time_sum / current_price
    factor = 1.0 + y / k
    modified_duration = macaulay_duration / factor
    convexity = convexity_sum / (current_price * (factor ** 2))

    # Invariant Enforcement: For any positive yield (y > 0), Modified Duration must be strictly less than Macaulay Duration
    if y > 1e-6 and macaulay_duration > 1e-4:
        if modified_duration >= macaulay_duration:
            raise ValueError(
                f"Quantitative Invariant Failure: Modified Duration ({modified_duration:.4f}) "
                f"must be strictly less than Macaulay Duration ({macaulay_duration:.4f}) for y > 0 (y={y:.4f})."
            )

    return {
        "macaulay_duration": round(macaulay_duration, 4),
        "modified_duration": round(modified_duration, 4),
        "convexity": round(convexity, 4),
        "ytm_pct": round(float(ytm_pct), 2),
    }


def compute_rate_shock_scenarios(
    current_price: float,
    modified_duration: float,
    convexity: float,
    rate_shifts_bps: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """Simulates bond price and percentage change under RBI rate shock scenarios.

    Enforces quantitative invariant:
    Includes positive convexity adjustment: Delta P / P = -D_mod * dy + 0.5 * C * (dy)^2.
    Convexity dampens price declines during rate hikes (dy > 0) and amplifies price gains
    during rate cuts (dy < 0).
    """
    if rate_shifts_bps is None:
        rate_shifts_bps = [-200, -100, -50, -25, 0, 25, 50, 100, 200]

    scenarios = []
    for bps in rate_shifts_bps:
        dy = bps / 10000.0  # 1 bps = 0.0001
        # Duration impact (linear approximation)
        linear_impact = -modified_duration * dy
        # Convexity adjustment (second-order curvature)
        convexity_adjustment = 0.5 * convexity * (dy ** 2)

        pct_change = (linear_impact + convexity_adjustment) * 100.0
        new_price = current_price * (1.0 + pct_change / 100.0)

        scenarios.append({
            "rate_shift_bps": bps,
            "rate_shift_label": f"{'+' if bps > 0 else ''}{bps / 100.0:+.2f}%",
            "pct_price_change": round(pct_change, 4),
            "linear_duration_pct": round(linear_impact * 100.0, 4),
            "convexity_adjustment_pct": round(convexity_adjustment * 100.0, 4),
            "estimated_price": round(new_price, 2)
        })

    return scenarios
