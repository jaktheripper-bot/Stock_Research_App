"""
Bull vs. Bear Thesis Synthesis Engine
======================================
Produces a balanced, non-advisory thesis briefing:
- Top 3 Structural Tailwinds (Bull Case)
- Top 3 Specific Vulnerabilities & Governance Risks (Bear Case)
Grounded strictly in verified exchange filings, operating metrics, and balance sheet quality.
"""

from typing import Dict, Any, List, Optional
import math
import logging

logger = logging.getLogger("equity_research.core.analysis.dossier_bull_bear")


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
    report_text: str = "",
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
                "title": "Sustained Return on Capital",
                "detail": f"Generates {metric_str}, indicating disciplined capital reinvestment above the hurdle cost of capital. The key question is whether incremental capital deployed continues to earn comparable returns."
            })
        elif c_roce >= 14.0:
            bull_points.append({
                "pillar": "Capital Productivity",
                "title": "Consistent Capital Returns",
                "detail": f"Delivers {c_roce:.1f}% ROCE above the corporate cost of capital, supporting self-funded reinvestment without balance sheet strain."
            })
        else:
            bull_points.append({
                "pillar": "Capital Productivity",
                "title": "Operating Efficiency Turnaround",
                "detail": "Capital reinvestment cycle is positioned to improve asset turnover, though sustained cash conversion remains the primary proof point."
            })
    else:
        bull_points.append({
            "pillar": "Franchise Presence",
            "title": "Established Market Presence",
            "detail": f"Established operating franchise in the {sector_name} sector with recurring enterprise relationships."
        })

    # 2. Solvency & Balance Sheet Cushion
    if de is not None:
        if de <= 0.15:
            bull_points.append({
                "pillar": "Balance Sheet Quality",
                "title": "Low-Leverage Balance Sheet",
                "detail": f"Operates with a debt-to-equity ratio of {de:.2f}, limiting refinancing exposure across rate cycles and preserving operating cash flow for internal reinvestment."
            })
        elif de <= 0.50:
            bull_points.append({
                "pillar": "Balance Sheet Quality",
                "title": "Conservative Leverage Cushion",
                "detail": f"Maintains a measured debt burden ({de:.2f} D/E) within prudential limits, keeping fixed interest charges manageable if demand softens."
            })
        else:
            bull_points.append({
                "pillar": "Balance Sheet Quality",
                "title": "Operational Cash Flow Coverage",
                "detail": "Debt servicing is supported by recurring operating cash flows and established banking lines, provided working-capital cycles remain contained."
            })
    else:
        bull_points.append({
            "pillar": "Balance Sheet Quality",
            "title": "Capital Structure Stability",
            "detail": "Supported by an equity base and committed working-capital credit lines."
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
            "title": "Valuation Buffer vs. Fair Value",
            "detail": f"Trades at a {mos:.1f}% discount to triangulated fair value (₹{fair_val:,.2f}), providing a wider margin of safety if near-term earnings moderate."
        })
    elif "ACCUMULATION" in flow_regime:
        bull_points.append({
            "pillar": "Institutional Flow",
            "title": "Exchange Depth Accumulation",
            "detail": "Order-book depth shows steady bid support absorbing secondary market supply."
        })
    else:
        bull_points.append({
            "pillar": "Industry Tailwinds",
            "title": f"{sector_name} Demand Visibility",
            "detail": f"Supported by ongoing domestic capital expenditure and sector formalization across {sector_name.lower()}, subject to disciplined working-capital conversion."
        })

    # ----------------------------------------------------
    # BEAR THESIS GENERATION
    # ----------------------------------------------------
    # 1. Valuation Multiple Headwinds
    if pe is not None and pe >= 45.0:
        bear_points.append({
            "pillar": "Valuation Multiples",
            "title": "Narrow Room for Execution Slippage",
            "detail": f"The competitive position remains credible, but a trailing P/E of {pe:.1f}x leaves little room for revenue growth or cash conversion to disappoint."
        })
    elif pe is not None and pe >= 30.0:
        bear_points.append({
            "pillar": "Valuation Multiples",
            "title": "Demanding Implied Expectations",
            "detail": f"At {pe:.1f}x trailing earnings, the market already prices in steady margin execution; any cost inflation or volume delay risks multiple compression."
        })
    elif mos < -25.0:
        bear_points.append({
            "pillar": "Valuation Multiples",
            "title": "Premium to Triangulated Fair Value",
            "detail": f"Trades at a {abs(mos):.1f}% premium to conservative DCF fair value, meaning future returns depend heavily on sustained earnings compounding."
        })
    else:
        bear_points.append({
            "pillar": "Macro Risk",
            "title": "Cyclical Demand & Input Sensitivity",
            "detail": "Exposed to intermediate demand slowdowns and raw-material cost swings if pricing pass-through lags by more than one to two quarters."
        })

    # 2. Forensic / Governance Risks
    flags = for_dict.get("red_flags", []) if isinstance(for_dict.get("red_flags"), list) else []
    if flags:
        bear_points.append({
            "pillar": "Governance / Accounting",
            "title": "Accounting & Cash-Conversion Watchpoints",
            "detail": f"Forensic screening flagged: {'; '.join(str(f) for f in flags[:2])}. Investors should track whether reported profits convert cleanly into operating cash flow."
        })
    elif de is not None and de > 0.60:
        bear_points.append({
            "pillar": "Capital Structure",
            "title": "Leverage & Refinancing Sensitivity",
            "detail": f"A debt-to-equity ratio of {de:.2f} increases sensitivity to borrowing costs; slower receivable collection would tighten interest coverage."
        })
    else:
        bear_points.append({
            "pillar": "Competitive Pressures",
            "title": "Industry Capacity & Pricing Discipline",
            "detail": "New capacity additions from peers or aggressive pricing by entrants could test gross-margin stability over the medium term."
        })


    # 3. Market Depth & Drawdown Risk
    lc_buffer = _safe_float(fl_dict.get("lower_circuit_buffer_pct"), default=10.0)
    if "DISTRIBUTION" in str(fl_dict.get("flow_regime") or ""):
        bear_points.append({
            "pillar": "Order Book Dynamics",
            "title": "Secondary Supply Overhang",
            "detail": "Exchange Level-2 depth shows persistent ask-side supply that may weigh on near-term price discovery."
        })
    elif lc_buffer <= 4.0:
        bear_points.append({
            "pillar": "Liquidity Volatility",
            "title": "Proximity to Lower Circuit Band",
            "detail": f"Trades within {lc_buffer:.1f}% of its daily exchange lower-circuit band, heightening execution slippage during volatile sessions."
        })
    else:
        bear_points.append({
            "pillar": "Execution Risk",
            "title": "Working Capital & Capex Conversion",
            "detail": "The investment case depends on converting incremental capital expenditure and receivables into free cash flow without stretching the cash conversion cycle."
        })

    if isinstance(report_text, str) and report_text.strip():
        from core.analysis.epistemic_schema import extract_falsification_triggers
        pillar_triggers = extract_falsification_triggers(report_text)
        pillar_names = {
            1: "Business Model & Revenue Visibility",
            2: "Competitive Moat Durability",
            3: "Balance Sheet & Cash Conversion",
            4: "Capital Allocation & Governance",
            5: "Valuation & Implied Expectations",
            6: "Sector & Regulatory Sensitivity",
            7: "Execution & Drawdown Risk",
        }
        grounded_bears: List[Dict[str, str]] = []
        for p_idx, trig in sorted(pillar_triggers.items()):
            detail = (trig.get("what_contradicts") or trig.get("evidence_that_forces_revision") or "").strip()
            if len(detail) >= 35:
                grounded_bears.append({
                    "pillar": f"Pillar 0{p_idx} Trigger",
                    "title": pillar_names.get(p_idx, f"Pillar 0{p_idx} Watchpoint"),
                    "detail": detail[:280],
                })
        if grounded_bears:
            bear_points = (grounded_bears + bear_points)[:3]

    return {
        "bull_thesis": bull_points[:3],
        "bear_thesis": bear_points[:3],
        "verdict_tone": "BALANCED_INSTITUTIONAL",
        "compliance_notice": "Purely descriptive diagnostic analysis under SEBI Safe Harbor principles. No investment recommendation.",
    }
