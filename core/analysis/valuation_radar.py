"""
Multi-Model Valuation Radar & Margin of Safety Sieve
=====================================================
Computes a robust intrinsic fair value range combining:
1. Historical Multiple Model (5-Year Median P/E)
2. 2-Stage Discounted Cash Flow (DCF) with conservative terminal growth
3. Earnings Power Value (EPV) / Graham Intrinsic Floor
Calculates the Margin of Safety % against current exchange quotes.
"""

from typing import Dict, Any, List, Optional
import math
import logging

logger = logging.getLogger("equity_research.core.analysis.valuation_radar")


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        if math.isnan(v) or math.isinf(v):
            return default
        return float(v)
    try:
        clean = str(v).strip().replace(",", "").replace("%", "")
        f = float(clean)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return default


def compute_valuation_radar(
    current_price: float,
    pe_ratio: float,
    eps: Optional[float] = None,
    sales_growth_3y: Optional[float] = None,
    historical_median_pe: Optional[float] = None,
    book_value_per_share: Optional[float] = None,
    discount_rate: float = 0.11,  # 11% Cost of Equity (7.1% G-Sec + 3.9% ERP)
    terminal_growth_rate: float = 0.045 # 4.5% perpetual growth
) -> Dict[str, Any]:
    """
    Computes a triangulated intrinsic fair value range and Margin of Safety %.
    Hardened against division by zero, discount rate inversions, and corrupt price inputs.
    """
    c_price = _safe_float(current_price)
    pe = _safe_float(pe_ratio)

    if c_price <= 0 or (pe <= 0 and (_safe_float(eps) if eps is not None else 0.0) <= 0):
        return {
            "status": "UNAVAILABLE",
            "current_price": c_price,
            "fair_value": 0.0,
            "range_low": 0.0,
            "range_high": 0.0,
            "margin_of_safety_pct": 0.0,
            "regime": "DATA_UNAVAILABLE",
            "badge_label": "Valuation Not Available",
            "badge_color": "#64748b",
            "summary": "Fundamental earnings or price data is not disclosed or currently negative, precluding intrinsic multiple modeling.",
            "inputs": {
                "normalized_eps": 0.0,
                "initial_growth_pct": 0.0,
                "discount_rate_pct": round(_safe_float(discount_rate, default=0.11) * 100.0, 1),
                "terminal_growth_pct": round(_safe_float(terminal_growth_rate, default=0.045) * 100.0, 1),
                "historical_median_pe": 0.0,
                "implied_fcf_growth_pct": 0.0,
            },
            "models": {}
        }

    # 1. Guard distorted TTM multiples (e.g. VEDL 2.22x demerger/one-off EPS or ETERNAL 722.9x inflection EPS)
    #    when explicit normalized EPS is not supplied by the caller.
    explicit_eps = _safe_float(eps) if eps is not None else 0.0
    if explicit_eps <= 0 and (pe < 4.0 or pe > 120.0):
        s_eps = round(c_price / pe, 2) if pe > 0 else 0.0
        disc_rate = max(0.02, _safe_float(discount_rate, default=0.11))
        term_rate = min(disc_rate - 0.015, max(0.01, _safe_float(terminal_growth_rate, default=0.045)))
        low_g, high_g = -0.20, 0.45
        for _ in range(32):
            mid_g = (low_g + high_g) / 2.0
            pv_s1, proj = 0.0, s_eps
            for yr in range(1, 6):
                proj *= (1.0 + mid_g)
                pv_s1 += proj / ((1.0 + disc_rate) ** yr)
            pv_tv = ((proj * (1.0 + term_rate)) / max(0.02, disc_rate - term_rate)) / ((1.0 + disc_rate) ** 5)
            if (pv_s1 + pv_tv) < c_price:
                low_g = mid_g
            else:
                high_g = mid_g
        implied_g = round(((low_g + high_g) / 2.0) * 100.0, 1)
        return {
            "status": "IMPLIED_GROWTH_ONLY",
            "current_price": c_price,
            "fair_value": None,
            "range_low": 0.0,
            "range_high": 0.0,
            "margin_of_safety_pct": None,
            "regime": "EXTREME_MULTIPLE_REGIME",
            "badge_label": f"Implied Growth ({implied_g}% CAGR)",
            "badge_color": "#f59e0b",
            "summary": (
                f"Trailing P/E ({pe:.1f}x) reflects non-normalized or early inflection-stage earnings; "
                f"evaluated via Reverse-DCF market-implied 5Y FCF growth ({implied_g}% CAGR at {disc_rate*100:.1f}% WACC)."
            ),
            "inputs": {
                "normalized_eps": s_eps,
                "initial_growth_pct": 0.0,
                "discount_rate_pct": round(disc_rate * 100.0, 1),
                "terminal_growth_pct": round(term_rate * 100.0, 1),
                "historical_median_pe": 0.0,
                "implied_fcf_growth_pct": implied_g,
            },
            "models": {},
        }

    # Derive or estimate normalized EPS
    s_eps = explicit_eps
    if s_eps <= 0:
        if pe > 0:
            s_eps = round(c_price / pe, 2)
        else:
            s_eps = 0.0

    s_growth = _safe_float(sales_growth_3y, default=12.0)
    growth_rate = s_growth / 100.0
    # Conservative cap on initial 5-year growth to prevent DCF hyper-extrapolation
    growth_rate = max(0.04, min(0.18, growth_rate))

    # Safe discount rate & perpetual growth spread (Strictly prevents ZeroDivisionError)
    disc_rate = max(0.02, _safe_float(discount_rate, default=0.11))
    raw_term = _safe_float(terminal_growth_rate, default=0.045)
    # Ensure terminal growth is clamped below discount rate by at least 150 bps
    term_rate = min(disc_rate - 0.015, max(0.01, raw_term))
    spread = max(0.015, disc_rate - term_rate)

    # Model 1: 5-Year Historical Median Multiple Fair Value
    med_pe = max(5.0, _safe_float(historical_median_pe, default=22.0))
    model1_pe_value = round(s_eps * med_pe, 2)

    # Model 2: 2-Stage Conservative DCF
    # Stage 1: 5 Years cash flow projection
    pv_stage1 = 0.0
    projected_eps = s_eps
    for year in range(1, 6):
        projected_eps *= (1.0 + growth_rate)
        pv_stage1 += projected_eps / math.pow(1.0 + disc_rate, year)

    # Stage 2: Terminal Value
    terminal_eps = projected_eps * (1.0 + term_rate)
    terminal_value = terminal_eps / spread
    pv_terminal = terminal_value / math.pow(1.0 + disc_rate, 5)

    model2_dcf_value = round(pv_stage1 + pv_terminal, 2)

    # Model 3: Graham / Earnings Power Value (Zero-growth asset floor)
    # EPV = EPS / Discount Rate (sustainable earnings in perpetuity without expansion capex)
    model3_epv_value = round(s_eps / disc_rate, 2)

    # Triangulate Composite Intrinsic Fair Value
    # 40% DCF, 35% Historical Median PE, 25% Conservative EPV
    composite_fair_value = round(
        (model2_dcf_value * 0.40) + 
        (model1_pe_value * 0.35) + 
        (model3_epv_value * 0.25), 
        2
    )

    # Valuation Range
    min_range = round(min(model1_pe_value, model2_dcf_value, model3_epv_value), 2)
    max_range = round(max(model1_pe_value, model2_dcf_value, model3_epv_value), 2)

    # Margin of Safety %
    # Positive means current price is below fair value (Discount)
    # Negative means current price is above fair value (Premium / Overvalued)
    if c_price > 0 and composite_fair_value > 0:
        margin_of_safety = round(((composite_fair_value - c_price) / c_price) * 100.0, 1)
    else:
        margin_of_safety = 0.0

    if margin_of_safety >= 25.0:
        regime = "DEEP_DISCOUNT"
        badge_label = f"Deep Margin of Safety (+{margin_of_safety}%)"
        badge_color = "#10b981"
        summary = f"Trades at a {margin_of_safety}% discount to triangulated fair value (₹{composite_fair_value:,.2f}), offering a meaningful valuation buffer if operating fundamentals hold."
    elif margin_of_safety >= 10.0:
        regime = "ATTRACTIVE_DISCOUNT"
        badge_label = f"Margin of Safety (+{margin_of_safety}%)"
        badge_color = "#38bdf8"
        summary = f"Trades at a {margin_of_safety}% discount to triangulated fair value (₹{composite_fair_value:,.2f}), leaving room for steady compounding without relying on multiple expansion."
    elif margin_of_safety >= -10.0:
        regime = "FAIR_VALUE"
        badge_label = f"Fair Value (Spread {margin_of_safety}%)"
        badge_color = "#fbbf24"
        summary = f"Trades within the triangulated fair-value band (₹{min_range:,.2f} to ₹{max_range:,.2f}), where returns will track underlying earnings and cash-flow execution."
    elif margin_of_safety >= -30.0:
        regime = "PREMIUM_VALUATION"
        badge_label = f"Growth Premium ({margin_of_safety}%)"
        badge_color = "#f97316"
        summary = f"Trades at a {abs(margin_of_safety)}% premium to conservative DCF fair value; the business quality may be credible, but the valuation leaves less room for execution to disappoint."
    else:
        regime = "ELEVATED_VALUATION_RISK"
        badge_label = f"Stretched Valuation ({margin_of_safety}%)"
        badge_color = "#ef4444"
        summary = f"Trades at an elevated {abs(margin_of_safety)}% premium to intrinsic earnings power value, creating valuation sensitivity if growth or margins moderate."

    g_rate = growth_rate

    # Reverse-solve implied 10Y growth rate required to justify current_price at discount_rate
    implied_g = 0.0
    if s_eps > 0 and current_price > 0:
        low_g, high_g = -0.20, 0.45
        for _ in range(32):
            mid_g = (low_g + high_g) / 2.0
            pv_s1 = 0.0
            proj = s_eps
            for yr in range(1, 6):
                proj *= (1.0 + mid_g)
                pv_s1 += proj / ((1.0 + disc_rate) ** yr)
            tv = (proj * (1.0 + term_rate)) / max(0.02, (disc_rate - term_rate))
            pv_tv = tv / ((1.0 + disc_rate) ** 5)
            if (pv_s1 + pv_tv) < current_price:
                low_g = mid_g
            else:
                high_g = mid_g
        implied_g = round(((low_g + high_g) / 2.0) * 100.0, 1)

    return {
        "status": "COMPUTED",
        "current_price": current_price,
        "fair_value": composite_fair_value,
        "range_low": min_range,
        "range_high": max_range,
        "margin_of_safety_pct": margin_of_safety,
        "regime": regime,
        "badge_label": badge_label,
        "badge_color": badge_color,
        "summary": summary,
        "inputs": {
            "normalized_eps": round(s_eps, 2),
            "initial_growth_pct": round(g_rate * 100.0, 1),
            "discount_rate_pct": round(discount_rate * 100.0, 1),
            "terminal_growth_pct": round(terminal_growth_rate * 100.0, 1),
            "historical_median_pe": round(med_pe, 1),
            "implied_fcf_growth_pct": implied_g,
        },
        "models": {
            "historical_pe_model": {
                "name": "Historical P/E Median Model",
                "multiple_used": med_pe,
                "fair_value": model1_pe_value,
            },
            "dcf_model": {
                "name": "2-Stage Conservative DCF",
                "discount_rate_pct": round(discount_rate * 100, 1),
                "terminal_growth_pct": round(terminal_growth_rate * 100, 1),
                "fair_value": model2_dcf_value,
            },
            "epv_model": {
                "name": "Earnings Power Value (EPV)",
                "fair_value": model3_epv_value,
            }
        }
    }
