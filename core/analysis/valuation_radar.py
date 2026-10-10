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

    if c_price <= 0:
        return {
            "status": "UNAVAILABLE",
            "fair_value": 0.0,
            "margin_of_safety_pct": 0.0,
            "regime": "UNDEFINED",
            "badge_color": "#64748b",
            "models": {}
        }

    # 1. Derive or estimate normalized EPS
    s_eps = _safe_float(eps) if eps is not None else 0.0
    if s_eps <= 0:
        if pe > 0:
            s_eps = round(c_price / pe, 2)
        else:
            s_eps = round(c_price * 0.04, 2)  # Conservative 4% earnings yield default

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
    if composite_fair_value > 0:
        margin_of_safety = round(((composite_fair_value - c_price) / composite_fair_value) * 100.0, 1)
    else:
        margin_of_safety = 0.0

    if margin_of_safety >= 25.0:
        regime = "DEEP_DISCOUNT"
        badge_label = f"Deep Margin of Safety (+{margin_of_safety}%)"
        badge_color = "#10b981"
        summary = f"Trading at a substantial {margin_of_safety}% discount to conservative intrinsic fair value of ₹{composite_fair_value:,.2f}."
    elif margin_of_safety >= 10.0:
        regime = "ATTRACTIVE_DISCOUNT"
        badge_label = f"Margin of Safety (+{margin_of_safety}%)"
        badge_color = "#38bdf8"
        summary = f"Trading at an attractive {margin_of_safety}% discount to fair value of ₹{composite_fair_value:,.2f}."
    elif margin_of_safety >= -10.0:
        regime = "FAIR_VALUE"
        badge_label = f"Fair Value (Spread {margin_of_safety}%)"
        badge_color = "#fbbf24"
        summary = f"Trading within normal fair value band (₹{min_range:,.2f} to ₹{max_range:,.2f})."
    elif margin_of_safety >= -30.0:
        regime = "PREMIUM_VALUATION"
        badge_label = f"Growth Premium ({margin_of_safety}%)"
        badge_color = "#f97316"
        summary = f"Trading at a {abs(margin_of_safety)}% premium above conservative DCF fair value. Requires sustained execution."
    else:
        regime = "ELEVATED_VALUATION_RISK"
        badge_label = f"Stretched Valuation ({margin_of_safety}%)"
        badge_color = "#ef4444"
        summary = f"Trading at an elevated {abs(margin_of_safety)}% premium above intrinsic earnings power value. Heightened multiple-contraction risk."

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
