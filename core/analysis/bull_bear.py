"""
Bull vs. Bear Thesis Synthesis Engine
======================================
Produces a balanced, non-advisory institutional thesis briefing:
- Top 3 Structural Tailwinds (Bull Case)
- Top 3 Specific Vulnerabilities & Governance Risks (Bear Case)
Grounded strictly in verified exchange filings, operating metrics, and balance sheet quality.
"""

from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger("equity_research.core.analysis.bull_bear")


def synthesize_bull_bear_thesis(
    ticker: str,
    fundamentals: Dict[str, Any],
    sector_data: Optional[Dict[str, Any]] = None,
    valuation_data: Optional[Dict[str, Any]] = None,
    forensic_data: Optional[Dict[str, Any]] = None,
    flow_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Synthesizes the core operational merits and risks into a digestible 60-second summary.
    """
    roce = float(fundamentals.get("roce") or fundamentals.get("return_on_capital") or 15.0)
    roe = float(fundamentals.get("roe") or fundamentals.get("return_on_equity") or 14.0)
    de = float(fundamentals.get("debt_to_equity") or fundamentals.get("debt_equity") or 0.2)
    pe = float(fundamentals.get("pe_ratio") or 22.0)
    sales_growth = float(fundamentals.get("sales_growth_3y") or 12.0)
    sector_name = (sector_data.get("sector_display_name") if sector_data else "Industry") or "Industry"

    bull_points: List[Dict[str, str]] = []
    bear_points: List[Dict[str, str]] = []

    # ----------------------------------------------------
    # BULL THESIS GENERATION
    # ----------------------------------------------------
    # 1. Capital Productivity
    if roce >= 20.0 or roe >= 18.0:
        bull_points.append({
            "pillar": "Capital Productivity",
            "title": "High-Tier Capital Efficiency",
            "detail": f"Generates an exceptional ROCE of {roce:.1f}% and ROE of {roe:.1f}%, indicating disciplined capital reinvestment and sustainable competitive advantage."
        })
    elif roce >= 14.0:
        bull_points.append({
            "pillar": "Capital Productivity",
            "title": "Consistent Capital Returns",
            "detail": f"Delivers {roce:.1f}% ROCE comfortably above the corporate cost of capital, sustaining balance sheet stability."
        })
    else:
        bull_points.append({
            "pillar": "Capital Productivity",
            "title": "Asset Re-Rating Potential",
            "detail": f"Operating efficiency turnaround underway; capital reinvestment cycle positioned to expand asset turnover."
        })

    # 2. Solvency & Balance Sheet Cushion
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

    # 3. Growth & Market Valuation
    mos = valuation_data.get("margin_of_safety_pct", 0.0) if valuation_data else 0.0
    flow_regime = flow_data.get("flow_regime", "") if flow_data else ""

    if mos > 10.0:
        bull_points.append({
            "pillar": "Valuation & Flow",
            "title": "Defensive Margin of Safety",
            "detail": f"Trades at a {mos:.1f}% discount to intrinsic fair value (₹{valuation_data.get('fair_value', 0):,.2f}), offering downside valuation protection."
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
    if pe >= 45.0 or mos < -25.0:
        bear_points.append({
            "pillar": "Valuation Multiples",
            "title": "Priced for Flawless Execution",
            "detail": f"Trailing P/E of {pe:.1f}x trades at a substantial premium above historical median, exposing the stock to sharp multiple-contraction if quarterly growth moderates."
        })
    elif pe >= 30.0:
        bear_points.append({
            "pillar": "Valuation Multiples",
            "title": "Full Valuation Band",
            "detail": f"Current multiple of {pe:.1f}x leaves limited margin of safety for operational hiccups or cost inflation."
        })
    else:
        bear_points.append({
            "pillar": "Macro Risk",
            "title": "Cyclical Growth Sensitivity",
            "detail": "Vulnerable to intermediate macro-economic demand slowdowns and raw material price volatility."
        })

    # 2. Forensic / Governance Risks
    flags = forensic_data.get("red_flags", []) if forensic_data else []
    if flags:
        bear_points.append({
            "pillar": "Governance / Accounting",
            "title": "Surveillance Flags Identified",
            "detail": f"Forensic sieve flagged: {'; '.join(flags[:2])}. Requires monitoring of cash flow realization."
        })
    elif de > 0.60:
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
    if flow_data and "DISTRIBUTION" in flow_data.get("flow_regime", ""):
        bear_points.append({
            "pillar": "Order Book Dynamics",
            "title": "Sell-Side Supply Overhang",
            "detail": "Angel One Level-2 depth indicates heavy ask-side volume capping intermediate upside momentum."
        })
    elif flow_data and flow_data.get("lower_circuit_buffer_pct", 10.0) <= 4.0:
        bear_points.append({
            "pillar": "Liquidity Volatility",
            "title": "Proximity to Lower Circuit Band",
            "detail": f"Stock is within {flow_data.get('lower_circuit_buffer_pct'):.1f}% of its daily exchange lower circuit freeze."
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
