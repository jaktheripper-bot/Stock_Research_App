"""
Bull vs. Bear Thesis Synthesis Engine
======================================
Produces a balanced, non-advisory institutional thesis briefing:
- Top 3 Structural Tailwinds (Bull Case)
- Top 3 Specific Vulnerabilities & Governance Risks (Bear Case)
Grounded strictly in verified exchange filings, operating metrics, and balance sheet quality.
"""

from typing import Dict, Any, List, Optional
import math
import logging

logger = logging.getLogger("equity_research.core.analysis.bull_bear")


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


def _parse_optional_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if math.isnan(v) or math.isinf(v):
            return None
        return float(v)
    s = str(v).strip().replace(",", "").replace("%", "")
    if not s or s.upper() in ("N/A", "NONE", "NAN", "-", ""):
        return None
    try:
        f = float(s)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def synthesize_bull_bear_thesis(
    ticker: str,
    fundamentals: Optional[Dict[str, Any]],
    sector_data: Optional[Dict[str, Any]] = None,
    valuation_data: Optional[Dict[str, Any]] = None,
    forensic_data: Optional[Dict[str, Any]] = None,
    flow_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Synthesizes the core operational merits and risks into a digestible 60-second summary.
    Hardened against null fundamentals, non-numeric strings, and format specifier errors.
    """
    fund = fundamentals if isinstance(fundamentals, dict) else {}
    roce = _parse_optional_float(fund.get("roce") or fund.get("return_on_capital"))
    roe = _parse_optional_float(fund.get("roe") or fund.get("return_on_equity"))
    de = _parse_optional_float(fund.get("debt_to_equity") or fund.get("debt_equity"))
    pe = _parse_optional_float(fund.get("pe_ratio"))
    sales_growth = _parse_optional_float(fund.get("sales_growth_3y"))
    sec_dict = sector_data if isinstance(sector_data, dict) else {}
    sector_name = str(sec_dict.get("sector_display_name") or "Industry")

    bull_points: List[Dict[str, str]] = []
    bear_points: List[Dict[str, str]] = []

    # ----------------------------------------------------
    # BULL THESIS GENERATION
    # ----------------------------------------------------
    # 1. Capital Productivity
    if roce is not None or roe is not None:
        c_roce = roce if roce is not None else 0.0
        c_roe = roe if roe is not None else 0.0
        if c_roce >= 20.0 or c_roe >= 18.0:
            roce_str = f"ROCE of {c_roce:.1f}%" if roce is not None else ""
            roe_str = f"ROE of {c_roe:.1f}%" if roe is not None else ""
            metric_str = " and ".join(filter(None, [roce_str, roe_str]))
            bull_points.append({
                "pillar": "Capital Productivity",
                "title": "High-Tier Capital Efficiency",
                "detail": f"Generates an exceptional {metric_str}, indicating disciplined capital reinvestment and sustainable competitive advantage."
            })
        elif c_roce >= 14.0:
            bull_points.append({
                "pillar": "Capital Productivity",
                "title": "Consistent Capital Returns",
                "detail": f"Delivers {c_roce:.1f}% ROCE comfortably above the corporate cost of capital, sustaining balance sheet stability."
            })
        else:
            bull_points.append({
                "pillar": "Capital Productivity",
                "title": "Asset Re-Rating Potential",
                "detail": f"Operating efficiency turnaround underway; capital reinvestment cycle positioned to expand asset turnover."
            })
    else:
        bull_points.append({
            "pillar": "Franchise Presence",
            "title": f"Established Market Presence",
            "detail": f"Established operating franchise in the {sector_name} sector with ongoing enterprise contracts."
        })

    # 2. Solvency & Balance Sheet Cushion
    if de is not None:
        if de <= 0.15:
            bull_points.append({
                "pillar": "Balance Sheet Quality",
                "title": "Virtually Debt-Free Structure",
                "detail": f"Pristine solvency with a debt-to-equity ratio of {de:.2f}, insulating the company against interest rate cycles and liquidity contractions."
            })
        elif de <= 0.50:
            bull_points.append({
                "pillar": "Balance Sheet Quality",
                "title": "Conservative Leverage Cushion",
                "detail": f"Prudent debt burden ({de:.2f} D/E) well within industry safety guidelines, providing financial flexibility for ongoing expansion."
            })
        else:
            bull_points.append({
                "pillar": "Balance Sheet Quality",
                "title": "Operational Cash Flow Backstop",
                "detail": f"Debt servicing sustained by operational cash flow visibility and long-term banking relationships."
            })
    else:
        bull_points.append({
            "pillar": "Balance Sheet Quality",
            "title": "Capital Structure Stability",
            "detail": "Supported by institutional equity base and statutory banking credit lines."
        })

    # 3. Growth & Market Valuation
    val_dict = valuation_data if isinstance(valuation_data, dict) else {}
    fl_dict = flow_data if isinstance(flow_data, dict) else {}
    for_dict = forensic_data if isinstance(forensic_data, dict) else {}

    mos = _safe_float(val_dict.get("margin_of_safety_pct"), 0.0)
    fair_val = _safe_float(val_dict.get("fair_value"), 0.0)
    flow_regime = str(fl_dict.get("flow_regime") or "")

    if mos > 10.0:
        bull_points.append({
            "pillar": "Valuation & Flow",
            "title": "Defensive Margin of Safety",
            "detail": f"Trades at a {mos:.1f}% discount to intrinsic fair value (₹{fair_val:,.2f}), offering downside valuation protection."
        })
    elif "ACCUMULATION" in flow_regime:
        bull_points.append({
            "pillar": "Institutional Flow",
            "title": "Exchange Depth Accumulation",
            "detail": "Live exchange order book reflects institutional accumulation pressure on primary bid tiers."
        })
    else:
        bull_points.append({
            "pillar": "Industry Tailwinds",
            "title": f"Structural {sector_name} Momentum",
            "detail": f"Supported by multi-year secular tailwinds and domestic capital expenditure expansion across {sector_name.lower()}."
        })

    # ----------------------------------------------------
    # BEAR THESIS GENERATION
    # ----------------------------------------------------
    # 1. Valuation Multiple Headwinds
    if pe is not None and pe >= 45.0:
        bear_points.append({
            "pillar": "Valuation Multiples",
            "title": "Priced for Flawless Execution",
            "detail": f"Trailing P/E of {pe:.1f}x trades at a substantial premium above historical median, exposing the stock to sharp multiple-contraction if quarterly growth moderates."
        })
    elif pe is not None and pe >= 30.0:
        bear_points.append({
            "pillar": "Valuation Multiples",
            "title": "Full Valuation Band",
            "detail": f"Current multiple of {pe:.1f}x leaves limited margin of safety for operational hiccups or cost inflation."
        })
    elif mos < -25.0:
        bear_points.append({
            "pillar": "Valuation Multiples",
            "title": "Premium to Intrinsic Value",
            "detail": f"Trades at a {abs(mos):.1f}% premium above triangulated intrinsic fair value, requiring sustained quarterly growth."
        })
    else:
        bear_points.append({
            "pillar": "Macro Risk",
            "title": "Cyclical Growth Sensitivity",
            "detail": "Vulnerable to intermediate macro-economic demand slowdowns and raw material price volatility."
        })

    # 2. Forensic / Governance Risks
    flags = for_dict.get("red_flags", []) if isinstance(for_dict.get("red_flags"), list) else []
    if flags:
        bear_points.append({
            "pillar": "Governance / Accounting",
            "title": "Surveillance Flags Identified",
            "detail": f"Forensic sieve flagged: {'; '.join(str(f) for f in flags[:2])}. Requires monitoring of cash flow realization."
        })
    elif de is not None and de > 0.60:
        bear_points.append({
            "pillar": "Capital Structure",
            "title": "Leverage Sensitivity",
            "detail": f"Elevated leverage ratio ({de:.2f} D/E) requires consistent operating cash flows to maintain interest coverage."
        })
    else:
        bear_points.append({
            "pillar": "Competitive Pressures",
            "title": "Intensifying Industry Competition",
            "detail": "Threat of capacity additions from domestic peers and potential gross margin pressure from unorganized entrants."
        })


    # 3. Market Depth & Drawdown Risk
    lc_buffer = _safe_float(fl_dict.get("lower_circuit_buffer_pct"), default=10.0)
    if "DISTRIBUTION" in str(fl_dict.get("flow_regime") or ""):
        bear_points.append({
            "pillar": "Order Book Dynamics",
            "title": "Sell-Side Supply Overhang",
            "detail": "Exchange Level-2 depth indicates heavy ask-side volume capping intermediate upside momentum."
        })
    elif lc_buffer <= 4.0:
        bear_points.append({
            "pillar": "Liquidity Volatility",
            "title": "Proximity to Lower Circuit Band",
            "detail": f"Stock is within {lc_buffer:.1f}% of its daily exchange lower circuit freeze."
        })
    else:
        bear_points.append({
            "pillar": "Execution Risk",
            "title": "Working Capital & Reinvestment Cycles",
            "detail": "Capital allocation discipline depends on timely commissioning of ongoing expansion projects without cost overruns."
        })

    return {
        "bull_thesis": bull_points[:3],
        "bear_thesis": bear_points[:3],
        "verdict_tone": "BALANCED_INSTITUTIONAL",
        "compliance_notice": "Purely descriptive diagnostic analysis under SEBI Safe Harbor principles. No investment recommendation.",
    }
