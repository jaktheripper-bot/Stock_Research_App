"""Analytical Engine for Sovereign Risk-Free Benchmarks and RBI Yield Curves.

Constructs the institutional Indian Sovereign Par Yield Curve across 91D, 182D, 364D Treasury Bills,
2Y, 3Y, 5Y, 7Y, 10Y, 14Y, 20Y, 30Y, 40Y, and 50Y Central Government Securities (G-Sec),
Sovereign Green Bonds (SGrB), and State Development Loans (SDL) across 10 borrowing states.
"""

import math
from typing import Dict, Any, List, Optional
from core.db.sovereign import (
    get_sovereign_yield_curve,
    get_sovereign_curve_analytics,
    save_sovereign_benchmark,
    get_sovereign_sdl_matrix,
    get_macro_monetary_corridor,
    get_historical_sovereign_curves,
)


def generate_curve_svg_data(
    curves: Dict[str, List[Dict[str, Any]]],
    width: int = 820,
    height: int = 340,
    pad_left: int = 55,
    pad_right: int = 35,
    pad_top: int = 25,
    pad_bottom: int = 35
) -> Dict[str, Any]:
    """Generates pure SVG coordinate mappings, gridlines, and polyline paths.
    
    Uses square-root maturity scaling to provide balanced visual density across
    ultra-short money-market tenors (91D to 1Y) and ultra-long sovereign bonds (10Y to 50Y).
    """
    sqrt_min = math.sqrt(0.25)
    sqrt_max = math.sqrt(50.0)
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    def map_x(maturity_years: float) -> float:
        m = max(0.25, min(50.0, float(maturity_years)))
        pct = (math.sqrt(m) - sqrt_min) / (sqrt_max - sqrt_min)
        return round(pad_left + pct * plot_w, 1)

    y_min = 6.50
    y_max = 7.80
    y_span = y_max - y_min

    def map_y(yield_pct: float) -> float:
        y = max(y_min, min(y_max, float(yield_pct)))
        pct = (y - y_min) / y_span
        return round((height - pad_bottom) - pct * plot_h, 1)

    # Horizontal Grid Lines & Yield Ticks
    yield_ticks = [6.60, 6.80, 7.00, 7.20, 7.40, 7.60, 7.80]
    grid_y = []
    for yt in yield_ticks:
        grid_y.append({
            "yield_val": yt,
            "label": f"{yt:.2f}%",
            "y": map_y(yt)
        })

    # Vertical Grid Lines & Tenor Ticks
    tenor_ticks = [
        (0.25, "91D"),
        (0.50, "182D"),
        (1.00, "1Y"),
        (2.00, "2Y"),
        (3.00, "3Y"),
        (5.00, "5Y"),
        (7.00, "7Y"),
        (10.00, "10Y"),
        (14.00, "14Y"),
        (20.00, "20Y"),
        (30.00, "30Y"),
        (50.00, "50Y")
    ]
    grid_x = []
    for mat, lbl in tenor_ticks:
        grid_x.append({
            "maturity": mat,
            "label": lbl,
            "x": map_x(mat)
        })

    # Generate curves data
    curve_series = {}
    for series_key, raw_pts in curves.items():
        sorted_pts = sorted(raw_pts, key=lambda p: float(p.get("maturity_years", 0.0)))
        pts_coords = []
        path_segments = []

        for idx, pt in enumerate(sorted_pts):
            mat = float(pt.get("maturity_years", 0.0))
            yd = float(pt.get("yield_pct", pt.get("cut_off_yield", 0.0)))
            lbl = pt.get("tenor_label", f"{mat}Y")
            cx = map_x(mat)
            cy = map_y(yd)

            pts_coords.append({
                "cx": cx,
                "cy": cy,
                "tenor_label": lbl,
                "maturity_years": mat,
                "yield_pct": yd
            })

            cmd = "M" if idx == 0 else "L"
            path_segments.append(f"{cmd} {cx} {cy}")

        curve_series[series_key] = {
            "path_d": " ".join(path_segments),
            "points": pts_coords
        }

    return {
        "width": width,
        "height": height,
        "pad_left": pad_left,
        "pad_right": pad_right,
        "pad_top": pad_top,
        "pad_bottom": pad_bottom,
        "grid_y": grid_y,
        "grid_x": grid_x,
        "series": curve_series
    }


def evaluate_sovereign_curve() -> Dict[str, Any]:
    """Evaluates the full sovereign yield curve structure, macro corridor, and SDL spreads."""
    analytics = get_sovereign_curve_analytics()
    points = analytics["curve_points"]
    macro_rates = get_macro_monetary_corridor()
    sdl_matrix = get_sovereign_sdl_matrix()
    historical_curves = get_historical_sovereign_curves()

    # Generate SVG coordinates
    svg_chart = generate_curve_svg_data(historical_curves)

    # Core Macro Rates
    repo_val = macro_rates.get("repo_rate", {}).get("value", 6.50)
    sdf_val = macro_rates.get("sdf_rate", {}).get("value", 6.25)
    msf_val = macro_rates.get("msf_rate", {}).get("value", 6.75)
    cpi_val = macro_rates.get("cpi_inflation", {}).get("value", 3.65)
    laf_val = macro_rates.get("net_laf_liquidity_cr", {}).get("value", 125400.0)

    gsec_10y = analytics["benchmark_10y_gsec"]
    tbill_91d = analytics["risk_free_short_tbill"]

    # Real Risk-Free 10Y Yield (Fisher Approximation)
    real_10y_yield = round(gsec_10y - cpi_val, 2)

    # Policy transmission spread (10Y minus Policy Repo)
    policy_spread_bps = round((gsec_10y - repo_val) * 100, 1)

    # Institutional Macro Insights (Zero-condescension, authoritative tone)
    insights = []
    term_spread = analytics["term_spread_bps"]
    if term_spread > 50:
        insights.append(
            f"Steep Term Premium (+{term_spread} bps): Term structure reflects robust economic growth and ample short-term market liquidity."
        )
    elif term_spread >= 15:
        insights.append(
            f"Normal Upward-Sloping Curve (+{term_spread} bps): Term structure provides orderly duration risk compensation across 1Y to 50Y maturities."
        )
    elif term_spread >= -10:
        insights.append(
            f"Flat Sovereign Curve ({term_spread} bps): Indicates potential liquidity tightness or monetary policy transmission transition."
        )
    else:
        insights.append(
            f"Inverted Sovereign Curve ({term_spread} bps): Short-dated liquidity pressure exceeds long-dated economic growth expectations."
        )

    insights.append(
        f"Policy Corridor Transmission: 10Y Benchmark trades at +{policy_spread_bps} bps over Policy Repo (6.50%), bounded within the SDF (6.25%) and MSF (6.75%) operational corridor."
    )
    insights.append(
        f"Substantial Real Yield Anchor: 10Y Sovereign Real Return is +{real_10y_yield}% (Nominal {gsec_10y}% minus Headline CPI {cpi_val}%), exceeding institutional capital hurdle rates."
    )
    insights.append(
        f"Sub-Sovereign Fiscal Spread: 10Y State Development Loans (SDL) clear at a weighted spread of +{analytics['sdl_credit_spread_bps']} bps over Central G-Secs, reflecting state-level borrowing volume and debt-to-GSDP disparity."
    )
    if analytics.get("greenium_bps", 0) > 0:
        insights.append(
            f"Sovereign Greenium (+{analytics['greenium_bps']} bps): 10Y Sovereign Green Bonds trade at a premium over conventional G-Secs, driven by statutory ESG mandates."
        )

    return {
        "benchmark_10y_gsec": gsec_10y,
        "risk_free_short_tbill": tbill_91d,
        "gsec_2y": analytics["gsec_2y"],
        "gsec_30y": analytics["gsec_30y"],
        "gsec_50y": analytics["gsec_50y"],
        "sgrb_10y": analytics["sgrb_10y"],
        "sdl_10y_yield": analytics["sdl_state_yield"],
        "term_spread_bps": term_spread,
        "policy_spread_bps": policy_spread_bps,
        "policy_slope_bps": analytics["policy_slope_bps"],
        "long_premium_bps": analytics["long_premium_bps"],
        "greenium_bps": analytics.get("greenium_bps", 4.0),
        "sdl_credit_spread_bps": analytics["sdl_credit_spread_bps"],
        "curve_shape": analytics["curve_shape"],
        "real_10y_yield": real_10y_yield,
        "curve_points": points,
        "macro_rates": macro_rates,
        "sdl_matrix": sdl_matrix,
        "historical_curves": historical_curves,
        "svg_chart": svg_chart,
        "macro_insights": insights
    }
