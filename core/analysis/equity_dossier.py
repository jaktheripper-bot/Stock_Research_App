"""
Equity Dossier Intelligence Coordinator
=======================================
Synthesizes:
1. Sector-Native Operational Scoring (BFSI, IT, Capital Goods, Healthcare, Consumer)
2. Exchange Live Level-2 Market Depth & Flow Analytics
3. Unified 360° Forensic Health Sieve (10-Point Deterministic Filter)
4. Multi-Model Valuation Radar & Margin of Safety
5. Bull vs. Bear Structural Thesis
Produces a unified equity intelligence package for web dossiers and APIs.
"""

from typing import Dict, Any, Optional, Tuple
import logging
import os
import threading
import time

from core.analysis.sector_scoring import evaluate_sector_fundamentals
from core.analysis.institutional_flow import analyze_institutional_flow
from core.analysis.forensic_sieve import evaluate_forensic_sieve
from core.analysis.valuation_radar import compute_valuation_radar, _safe_float
from core.analysis.dossier_bull_bear import synthesize_bull_bear_thesis
from core.ingestion.angel_one import AngelOneGateway

logger = logging.getLogger("equity_research.core.analysis.equity_dossier")

_CLOSING_L2_CACHE: Dict[str, Dict[str, Any]] = {}
_CLOSING_L2_TS: Dict[str, float] = {}
_LIVE_QUOTE_MICRO_CACHE: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}
_L2_CACHE_LOCK = threading.RLock()
_MAX_L2_CACHE = 512
_LIVE_QUOTE_TTL_SEC = 45.0
_CLOSING_L2_TTL_SEC = 86400.0
_DEFAULT_GET_STOCK_QUOTE_FUNC = getattr(AngelOneGateway.get_stock_quote, "__func__", AngelOneGateway.get_stock_quote)


def compile_equity_dossier(
    ticker: str,
    fundamentals: Dict[str, Any],
    company_name: str = "",
    industry_str: str = "",
    angel_quote: Optional[Dict[str, Any]] = None,
    report_text: str = "",
    include_gated_pillars: bool = True,
) -> Dict[str, Any]:
    """
    Assembles all Category 1 intelligence modules into a unified payload.
    """
    clean_sym = str(ticker or "").strip().upper()
    live_q: Optional[Dict[str, Any]] = None
    if angel_quote is None and clean_sym and AngelOneGateway.is_configured():
        try:
            current_fn = getattr(AngelOneGateway.get_stock_quote, "__func__", AngelOneGateway.get_stock_quote)
            is_patched = current_fn is not _DEFAULT_GET_STOCK_QUOTE_FUNC
            now_ts = time.time()
            if not is_patched and os.environ.get("TESTING") == "1":
                with _L2_CACHE_LOCK:
                    snap_ts = _CLOSING_L2_TS.get(clean_sym, 0.0)
                    if clean_sym in _CLOSING_L2_CACHE and (now_ts - snap_ts) < _CLOSING_L2_TTL_SEC:
                        angel_quote = _CLOSING_L2_CACHE[clean_sym]
            else:
                cached_hit = False
                if not is_patched:
                    with _L2_CACHE_LOCK:
                        micro = _LIVE_QUOTE_MICRO_CACHE.get(clean_sym)
                        if micro and (now_ts - micro[0]) < _LIVE_QUOTE_TTL_SEC:
                            live_q = micro[1]
                            cached_hit = True
                if not cached_hit:
                    live_q = AngelOneGateway.get_stock_quote(clean_sym)
                    if not is_patched:
                        with _L2_CACHE_LOCK:
                            if len(_LIVE_QUOTE_MICRO_CACHE) >= _MAX_L2_CACHE:
                                _LIVE_QUOTE_MICRO_CACHE.pop(next(iter(_LIVE_QUOTE_MICRO_CACHE)), None)
                            _LIVE_QUOTE_MICRO_CACHE[clean_sym] = (now_ts, live_q)

                if live_q and (_safe_float(live_q.get("total_buy_qty")) + _safe_float(live_q.get("total_sell_qty"))) > 0:
                    angel_quote = live_q
                    with _L2_CACHE_LOCK:
                        if clean_sym not in _CLOSING_L2_CACHE and len(_CLOSING_L2_CACHE) >= _MAX_L2_CACHE:
                            oldest = next(iter(_CLOSING_L2_CACHE))
                            _CLOSING_L2_CACHE.pop(oldest, None)
                            _CLOSING_L2_TS.pop(oldest, None)
                        _CLOSING_L2_CACHE[clean_sym] = {**live_q, "source": "NSE/BSE Closing Depth Snapshot"}
                        _CLOSING_L2_TS[clean_sym] = now_ts
                else:
                    with _L2_CACHE_LOCK:
                        snap_ts = _CLOSING_L2_TS.get(clean_sym, now_ts)
                        if clean_sym in _CLOSING_L2_CACHE and (now_ts - snap_ts) < _CLOSING_L2_TTL_SEC:
                            angel_quote = _CLOSING_L2_CACHE[clean_sym]
                        elif clean_sym in _CLOSING_L2_CACHE:
                            _CLOSING_L2_CACHE.pop(clean_sym, None)
                            _CLOSING_L2_TS.pop(clean_sym, None)
        except Exception as e:
            logger.debug(f"Angel One quote lookup notice for {clean_sym}: {e}")
            with _L2_CACHE_LOCK:
                snap_ts = _CLOSING_L2_TS.get(clean_sym, time.time())
                if clean_sym in _CLOSING_L2_CACHE and (time.time() - snap_ts) < _CLOSING_L2_TTL_SEC:
                    angel_quote = _CLOSING_L2_CACHE.get(clean_sym)

    # 2. Sector-Native Operational Scoring
    fund_dict = fundamentals if isinstance(fundamentals, dict) else {}
    effective_industry = industry_str
    if not effective_industry or effective_industry.strip().upper() in ("DIVERSIFIED", "GENERAL INDUSTRY", "GENERAL"):
        effective_industry = f"{fund_dict.get('sector') or ''} {fund_dict.get('industry') or ''}".strip()
    effective_name = company_name or str(fund_dict.get("company_name") or fund_dict.get("short_name") or "")

    sector_data = evaluate_sector_fundamentals(
        ticker=ticker,
        fundamentals=fund_dict,
        industry_str=effective_industry,
        company_name=effective_name
    )

    # 3. Institutional Flow & Market Depth
    flow_data = analyze_institutional_flow(angel_quote)

    # 4. Forensic & Governance Sieve
    forensic_data = evaluate_forensic_sieve(
        symbol=ticker,
        fundamentals=fund_dict
    )

    # 5. Multi-Model Valuation Radar
    raw_price = (
        (angel_quote.get("ltp") if angel_quote else None) or 
        (live_q.get("ltp") if live_q else None) or
        fund_dict.get("current_price") or 
        fund_dict.get("base_price") or 
        0.0
    )
    current_price = _safe_float(raw_price, 0.0)
    
    raw_pe = fund_dict.get("pe_ratio")
    pe_ratio = _safe_float(raw_pe, 0.0) or _safe_float(fund_dict.get("forward_pe"), 0.0)

    raw_growth = fund_dict.get("sales_growth_3y")
    if raw_growth in (None, "", "N/A"):
        raw_growth = fund_dict.get("sales_growth")
    sales_growth = _safe_float(raw_growth, 8.0) if raw_growth not in (None, "", "N/A") else 8.0
    sector_pe_med = (sector_data.get("benchmarks") or {}).get("pe_median", 22.0)

    valuation_data = compute_valuation_radar(
        current_price=current_price,
        pe_ratio=pe_ratio,
        sales_growth_3y=sales_growth,
        historical_median_pe=sector_pe_med,
        eps=fund_dict.get("eps"),
    )

    # 6. Bull vs. Bear Thesis Synthesis
    bull_bear_data = synthesize_bull_bear_thesis(
        ticker=ticker,
        fundamentals=fund_dict,
        sector_data=sector_data,
        valuation_data=valuation_data,
        forensic_data=forensic_data,
        flow_data=flow_data,
        report_text=report_text,
        include_gated_pillars=include_gated_pillars,
    )

    # 7. Generate Quality Composite Score (0-100)
    # Weights: 30% Sector Operations, 25% Valuation & MoS, 25% Forensic Integrity, 20% Institutional Flow
    sec_score = float(sector_data.get("score", 60.0))
    for_score = float(forensic_data.get("score", 80.0))
    flow_score = float(flow_data.get("score", 60.0))

    flow_available = flow_data.get("status") != "UNAVAILABLE"
    if valuation_data.get("status") in ("UNAVAILABLE", "IMPLIED_GROWTH_ONLY") or valuation_data.get("margin_of_safety_pct") is None:
        composite_score = round(
            (sec_score * 0.55 + for_score * 0.45) if not flow_available
            else (sec_score * 0.40 + for_score * 0.333 + flow_score * 0.267),
            1,
        )
    elif not flow_available:
        mos = valuation_data.get("margin_of_safety_pct", 0.0) or 0.0
        val_subscore = max(10.0, min(100.0, 65.0 + (mos * 1.2)))
        composite_score = round((sec_score * 0.375) + (val_subscore * 0.3125) + (for_score * 0.3125), 1)
    else:
        sector_weight = 0.30
        valuation_weight = 0.25
        forensic_weight = 0.25
        flow_weight = 0.20

        # Derive 0-100 valuation sub-score from Margin of Safety
        mos = valuation_data.get("margin_of_safety_pct", 0.0) or 0.0
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

    # 8. Varan Deterministic Financial Ingestion & Delta Packet (fail-closed without genuine revenue series)
    varan_packet = None
    hist_rev = fund_dict.get("historical_revenues")
    rev_raw = fund_dict.get("revenue_cr")
    if (isinstance(hist_rev, list) and len(hist_rev) > 0) or (rev_raw is not None and _safe_float(rev_raw, 0.0) > 0):
        try:
            from core.cortex.varan import VaranEngine
            rev = _safe_float(rev_raw, 0.0)
            ebitda = _safe_float(fund_dict.get("ebitda_cr"), 0.0)
            pat = _safe_float(fund_dict.get("pat_cr"), 0.0)
            cfo = _safe_float(fund_dict.get("operating_cash_flow_cr"), 0.0)
            capex = _safe_float(fund_dict.get("capex_cr"), 0.0)
            bs = fund_dict.get("balance_sheet") if isinstance(fund_dict.get("balance_sheet"), dict) else {}
            varan_packet = VaranEngine.compile_delta_packet(
                symbol=ticker,
                annual_revenues=hist_rev or [rev],
                annual_ebitda=fund_dict.get("historical_ebitda") or [ebitda],
                annual_pat=fund_dict.get("historical_pat") or [pat],
                annual_cfo=fund_dict.get("historical_cfo") or [cfo],
                annual_capex=fund_dict.get("historical_capex") or [capex],
                latest_balance_sheet=bs,
            )
        except Exception as e:
            logger.debug(f"VaranEngine compilation notice for {ticker}: {e}")

    # 9. Setu Cross-Asset Capital Structure Matrix (fail-closed without genuine FCF yield)
    setu_matrix = None
    if fund_dict.get("fcf_yield_pct") is not None:
        try:
            from core.cortex.setu import SetuMatrixEngine
            fcf_yield = _safe_float(fund_dict.get("fcf_yield_pct"), 0.0)
            rating = str(fund_dict.get("credit_rating") or "UNRATED")
            pledge = _safe_float(fund_dict.get("promoter_pledge_pct"), 0.0)
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
            stock_data=fund_dict,
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
