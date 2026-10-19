"""
Equity Dossier Intelligence Coordinator
=======================================
Synthesizes:
1. Sector-Native Operational Scoring (BFSI, IT, Capital Goods, Healthcare, Consumer)
2. Exchange Live Level-2 Market Depth & Flow Analytics
3. Unified 360° Forensic Health Sieve (10-Point Deterministic Filter)
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
from core.analysis.dossier_bull_bear import synthesize_bull_bear_thesis
from core.ingestion.angel_one import AngelOneGateway

logger = logging.getLogger("equity_research.core.analysis.equity_dossier")


def compile_equity_dossier(
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
    raw_price = (
        (angel_quote.get("ltp") if angel_quote else None) or 
        fundamentals.get("current_price") or 
        fundamentals.get("base_price") or 
        0.0
    )
    current_price = float(raw_price) if raw_price is not None else 0.0
    
    raw_pe = fundamentals.get("pe_ratio")
    pe_ratio = float(raw_pe) if raw_pe is not None else 0.0

    raw_growth = fundamentals.get("sales_growth_3y")
    sales_growth = float(raw_growth) if raw_growth is not None else None
    
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
    sec_score = float(sector_data.get("score", 60.0))
    for_score = float(forensic_data.get("score", 80.0))
    flow_score = float(flow_data.get("score", 60.0))

    if valuation_data.get("status") == "UNAVAILABLE":
        # Reweight available pillars proportionally: Sector (40%), Forensic (33.3%), Flow (26.7%)
        composite_score = round(
            (sec_score * 0.40) +
            (for_score * 0.333) +
            (flow_score * 0.267),
            1
        )
    else:
        sector_weight = 0.30
        valuation_weight = 0.25
        forensic_weight = 0.25
        flow_weight = 0.20

        # Derive 0-100 valuation sub-score from Margin of Safety
        mos = valuation_data.get("margin_of_safety_pct", 0.0)
        # Mos > 25% -> 95, Mos 0% -> 65, Mos -30% -> 35
        val_subscore = max(10.0, min(100.0, 65.0 + (mos * 1.2)))

        composite_score = round(
            (sec_score * sector_weight) +
            (val_subscore * valuation_weight) +
            (for_score * forensic_weight) +
            (flow_score * flow_weight),
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

    # 8. Varan Deterministic Financial Ingestion & Delta Packet
    varan_packet = None
    try:
        from core.cortex.varan import VaranEngine
        rev = float(fundamentals.get("revenue_cr") or 100.0)
        ebitda = float(fundamentals.get("ebitda_cr") or 20.0)
        pat = float(fundamentals.get("pat_cr") or 10.0)
        cfo = float(fundamentals.get("operating_cash_flow_cr") or 15.0)
        capex = float(fundamentals.get("capex_cr") or 5.0)
        bs = fundamentals.get("balance_sheet") if isinstance(fundamentals.get("balance_sheet"), dict) else {}
        varan_packet = VaranEngine.compile_delta_packet(
            symbol=ticker,
            annual_revenues=fundamentals.get("historical_revenues") or [rev],
            annual_ebitda=fundamentals.get("historical_ebitda") or [ebitda],
            annual_pat=fundamentals.get("historical_pat") or [pat],
            annual_cfo=fundamentals.get("historical_cfo") or [cfo],
            annual_capex=fundamentals.get("historical_capex") or [capex],
            latest_balance_sheet=bs,
        )
    except Exception as e:
        logger.debug(f"VaranEngine compilation notice for {ticker}: {e}")

    # 9. Setu Cross-Asset Capital Structure Matrix
    setu_matrix = None
    try:
        from core.cortex.setu import SetuMatrixEngine
        fcf_yield = float(fundamentals.get("fcf_yield_pct") or 5.0)
        rating = str(fundamentals.get("credit_rating") or "AAA")
        pledge = float(fundamentals.get("promoter_pledge_pct") or 0.0)
        setu_matrix = SetuMatrixEngine.evaluate(
            symbol=ticker,
            equity_fcf_yield_pct=fcf_yield,
            debt_credit_rating=rating,
            promoter_pledge_pct=pledge,
        )
    except Exception as e:
        logger.debug(f"SetuMatrixEngine evaluation notice for {ticker}: {e}")

    # 10. Epistemic Ledger & Falsification Triggers
    epistemic_ledger = None
    try:
        from core.analysis.epistemic_schema import build_equity_epistemic_ledger
        epistemic_ledger = build_equity_epistemic_ledger(
            ticker=ticker,
            stock_data=fundamentals,
            equity_intel={
                "sector_intelligence": sector_data,
                "forensic_intelligence": forensic_data,
                "valuation_radar": valuation_data,
            }
        )
    except Exception as e:
        logger.debug(f"Epistemic ledger compilation notice for {ticker}: {e}")

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
        "varan_delta_packet": varan_packet,
        "setu_capital_matrix": setu_matrix,
        "epistemic_ledger": epistemic_ledger,
    }
