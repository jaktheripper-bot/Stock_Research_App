"""
Equity Dossier Intelligence Coordinator
=======================================
Synthesizes:
1. Sector-Native Operational Scoring (BFSI, IT, Capital Goods, Healthcare, Consumer)
2. Angel One Live Level-2 Market Depth & Flow Analytics
3. Unified 360° Forensic Health Sieve (Chanakya 10-point check)
4. Multi-Model Valuation Radar & Margin of Safety
5. Bull vs. Bear Structural Thesis
Produces a unified institutional equity intelligence package for web dossiers and APIs.
"""

from typing import Dict, Any, Optional
import logging

from core.analysis.sector_scoring import evaluate_sector_fundamentals
from core.analysis.institutional_flow import analyze_institutional_flow
from core.analysis.forensic_sieve import evaluate_forensic_sieve
from core.analysis.valuation_radar import compute_valuation_radar
from core.analysis.bull_bear import synthesize_bull_bear_thesis
from core.ingestion.angel_one import AngelOneGateway

logger = logging.getLogger("equity_research.core.analysis.equity_dossier_intelligence")


def compile_equity_dossier_intelligence(
    ticker: str,
    fundamentals: Dict[str, Any],
    company_name: str = "",
    industry_str: str = "",
    angel_quote: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Assembles all Category 1 institutional intelligence modules into a unified payload.
    """
    # 1. Fetch Angel One quote if not provided and configured
    if angel_quote is None and AngelOneGateway.is_configured():
        try:
            angel_quote = AngelOneGateway.get_stock_quote(ticker)
        except Exception as e:
            logger.debug(f"Angel One quote lookup notice for {ticker}: {e}")

    # 2. Sector-Native Operational Scoring
    sector_data = evaluate_sector_fundamentals(
        ticker=ticker,
        fundamentals=fundamentals,
        industry_str=industry_str,
        company_name=company_name
    )

    # 3. Institutional Flow & Market Depth
    flow_data = analyze_institutional_flow(angel_quote)

    # 4. Forensic & Governance Sieve
    forensic_data = evaluate_forensic_sieve(
        symbol=ticker,
        fundamentals=fundamentals
    )

    # 5. Multi-Model Valuation Radar
    current_price = float(
        (angel_quote.get("ltp") if angel_quote else None) or 
        fundamentals.get("current_price") or 
        fundamentals.get("base_price") or 
        100.0
    )
    pe_ratio = float(fundamentals.get("pe_ratio") or 22.0)
    sales_growth = float(fundamentals.get("sales_growth_3y") or 12.0)
    
    valuation_data = compute_valuation_radar(
        current_price=current_price,
        pe_ratio=pe_ratio,
        sales_growth_3y=sales_growth,
        eps=fundamentals.get("eps"),
    )

    # 6. Bull vs. Bear Thesis Synthesis
    bull_bear_data = synthesize_bull_bear_thesis(
        ticker=ticker,
        fundamentals=fundamentals,
        sector_data=sector_data,
        valuation_data=valuation_data,
        forensic_data=forensic_data,
        flow_data=flow_data,
    )

    # 7. Synthesize Institutional Quality Composite Score (0-100)
    # Weights: 30% Sector Operations, 25% Valuation & MoS, 25% Forensic Integrity, 20% Institutional Flow
    sector_weight = 0.30
    valuation_weight = 0.25
    forensic_weight = 0.25
    flow_weight = 0.20

    # Derive 0-100 valuation sub-score from Margin of Safety
    mos = valuation_data.get("margin_of_safety_pct", 0.0)
    # Mos > 25% -> 95, Mos 0% -> 65, Mos -30% -> 35
    val_subscore = max(10.0, min(100.0, 65.0 + (mos * 1.2)))

    composite_score = round(
        (sector_data.get("score", 60.0) * sector_weight) +
        (val_subscore * valuation_weight) +
        (forensic_data.get("score", 80.0) * forensic_weight) +
        (flow_data.get("score", 60.0) * flow_weight),
        1
    )

    if composite_score >= 80.0:
        composite_verdict = "INSTITUTIONAL_LEADER"
        composite_color = "#10b981"
    elif composite_score >= 65.0:
        composite_verdict = "QUALITY_FRANCHISE"
        composite_color = "#38bdf8"
    elif composite_score >= 50.0:
        composite_verdict = "BALANCED_RUNNER"
        composite_color = "#fbbf24"
    else:
        composite_verdict = "ELEVATED_VULNERABILITY"
        composite_color = "#ef4444"

    return {
        "ticker": ticker,
        "composite_score": composite_score,
        "composite_verdict": composite_verdict,
        "composite_color": composite_color,
        "sector_intelligence": sector_data,
        "institutional_flow": flow_data,
        "forensic_intelligence": forensic_data,
        "valuation_radar": valuation_data,
        "bull_bear_thesis": bull_bear_data,
    }
