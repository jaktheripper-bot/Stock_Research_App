"""Analytical Engine for Sovereign Risk-Free Benchmarks and RBI Yield Curves.

Constructs the Indian Sovereign Par Yield Curve across 91D, 182D, 364D Treasury Bills,
2Y, 5Y, 10Y, 30Y Central Government Securities (G-Sec), and 10Y State Development Loans (SDL).
"""

from typing import Dict, Any, List, Optional
from core.db.sovereign import (
    get_sovereign_yield_curve,
    get_sovereign_curve_analytics,
    save_sovereign_benchmark
)


def evaluate_sovereign_curve() -> Dict[str, Any]:
    """Evaluates the full sovereign yield curve structure and provides macro insights."""
    analytics = get_sovereign_curve_analytics()
    points = analytics["curve_points"]

    # Classify Curve Dynamics
    term_spread = analytics["term_spread_bps"]
    sdl_spread = analytics["sdl_credit_spread_bps"]

    insights = []
    if term_spread > 50:
        insights.append("Steep Curve: Market anticipates long-term growth and stable liquidity; favors short-tenor debt roll.")
    elif term_spread >= 10:
        insights.append("Normal Upward-Sloping Curve: Healthy maturity premium compensating for term duration risk.")
    elif term_spread >= -10:
        insights.append("Flat Sovereign Curve: Market pricing potential RBI rate easing or tight short-term liquidity.")
    else:
        insights.append("Inverted Sovereign Curve: Extreme short-term liquidity pressure or recessionary signal.")

    if sdl_spread > 40:
        insights.append(f"Elevated State Premium ({sdl_spread} bps): State government borrowing spreads wider than historical average.")
    else:
        insights.append(f"Tight State Premium ({sdl_spread} bps): Sub-sovereign SDLs trading at narrow spread over Central G-Secs.")

    return {
        "benchmark_10y_gsec": analytics["benchmark_10y_gsec"],
        "risk_free_short_tbill": analytics["risk_free_short_tbill"],
        "sdl_10y_yield": analytics["sdl_state_yield"],
        "term_spread_bps": term_spread,
        "sdl_credit_spread_bps": sdl_spread,
        "curve_shape": analytics["curve_shape"],
        "curve_points": points,
        "macro_insights": insights
    }
