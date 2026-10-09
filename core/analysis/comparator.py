"""Peer comparison and cross-company disparity diagnostic engine."""

import logging
import httpx
from normalizer import clean_ticker
from core.db import get_report_by_ticker_sync
from core.analysis.fundamentals import get_stock_fundamentals, enrich_fundamentals
from core.analysis.parser import extract_health_matrix

logger = logging.getLogger("equity_research.core.analysis.comparator")
import asyncio
def evaluate_company_disparity(fund_a: dict, fund_b: dict) -> dict:
    """
    Evaluates cross-company disparity across the 3 institutional axes:
    1. Sector / Business Model Disparity (e.g. Banks/NBFC vs SaaS)
    2. Lifecycle / Maturity Disparity (unprofitable/loss-making vs mature profitable)
    3. Scale & Capital Structure Divergence (>= 100x market cap divergence)
    """
    warnings = []
    
    # 1. Sector / Business Model Disparity
    sec_a = str(fund_a.get("sector") or "").strip()
    sec_b = str(fund_b.get("sector") or "").strip()
    generic = {"N/A", "General Industry", "Core Industry", "Diversified / Core Industry", ""}
    
    def norm_sec(s: str) -> str:
        sl = s.lower().strip()
        if any(k in sl for k in ["tech", "software", "it -", "computers", "information technology"]):
            return "technology"
        if any(k in sl for k in ["bank", "financial", "nbfc", "lending", "insurance"]):
            return "financial_services"
        if any(k in sl for k in ["auto", "motor", "vehicle"]):
            return "automotive"
        if any(k in sl for k in ["pharma", "health", "biotech", "drug", "hospital"]):
            return "healthcare"
        if any(k in sl for k in ["steel", "metal", "mining", "aluminium", "copper"]):
            return "metals_mining"
        if any(k in sl for k in ["telecom", "communication"]):
            return "telecommunications"
        if any(k in sl for k in ["power", "energy", "oil", "gas", "petro", "utility"]):
            return "energy_utilities"
        if any(k in sl for k in ["fmcg", "consumer", "retail", "beverage", "food"]):
            return "consumer"
        return sl

    sector_mismatch = False
    if sec_a and sec_b and sec_a not in generic and sec_b not in generic and norm_sec(sec_a) != norm_sec(sec_b):
        sector_mismatch = True
        warnings.append(
            f"Sector Disparity ({sec_a} vs. {sec_b}): These companies operate in fundamentally different sectors. "
            "Multiples like EV/EBITDA, gross margins, or P/B cannot be compared 1:1."
        )

    # 2. Lifecycle / Maturity Disparity
    pe_a = str(fund_a.get("pe_ratio", "N/A"))
    pe_b = str(fund_b.get("pe_ratio", "N/A"))
    loss_a = "Loss-Making" in pe_a or "Negative" in pe_a
    loss_b = "Loss-Making" in pe_b or "Negative" in pe_b
    lifecycle_mismatch = False
    if (loss_a and not loss_b and pe_b != "N/A") or (loss_b and not loss_a and pe_a != "N/A"):
        lifecycle_mismatch = True
        warnings.append(
            "Lifecycle Disparity: One of these companies is an early-stage or loss-making asset while the other is a mature, "
            "profitable firm. Growth metrics and valuation multiples are not directly equivalent."
        )

    # 3. Scale / Capital Structure Disparity
    mcap_a = 0.0
    mcap_b = 0.0
    try:
        mcap_a = float(str(fund_a.get("market_cap") or 0).replace(",", "").strip())
        mcap_b = float(str(fund_b.get("market_cap") or 0).replace(",", "").strip())
    except Exception as parse_err:
        logger.debug("Market cap parse error: %s", parse_err)
    
    scale_mismatch = False
    if mcap_a > 0 and mcap_b > 0:
        ratio = max(mcap_a, mcap_b) / min(mcap_a, mcap_b)
        if ratio >= 100.0:
            scale_mismatch = True
            warnings.append(
                f"Scale Disparity: Greater than {int(ratio)}x divergence in market capitalization. "
                "Institutional float, liquidity dynamics, and capital structures are not directly comparable."
            )

    return {
        "is_disparate": len(warnings) > 0,
        "warnings": warnings,
        "sector_mismatch": sector_mismatch,
        "lifecycle_mismatch": lifecycle_mismatch,
        "scale_mismatch": scale_mismatch,
        "sec_a": sec_a or "N/A",
        "sec_b": sec_b or "N/A",
    }

async def compare_two_companies(ticker_a: str, ticker_b: str, progress_callback=None) -> dict:
    """
    Executes cross-company peer comparison with 3-tier disparity evaluation,
    extracting side-by-side fundamentals, 7-pillar health matrices, and normalized indicators.
    """
    clean_a = clean_ticker(ticker_a)
    clean_b = clean_ticker(ticker_b)
    
    # Using asyncio for concurrent fetching
    async def _fetch_pipeline(ticker_str: str):
        clean = clean_ticker(ticker_str)
        # Fetch the report asynchronously
        report = get_report_by_ticker_sync(clean)
        # Fetch fundamentals synchronously
        fundamentals = get_stock_fundamentals(clean)
        # Extract health matrix from report text if available
        matrix = extract_health_matrix(report.get("report_text", "")) if report else ""
        return (clean, fundamentals, report, matrix)

    if progress_callback:
        progress_callback(0.25, f"Auditing verified BSE quotes & fundamentals for {clean_a} & {clean_b}...")

    (resolved_a, fund_a, rep_a, matrix_a), (resolved_b, fund_b, rep_b, matrix_b) = await asyncio.gather(
        _fetch_pipeline(ticker_a),
        _fetch_pipeline(ticker_b),
    )
    
    if progress_callback:
        progress_callback(0.85, "Evaluating 3-tier heuristic disparity (Sector, Lifecycle, Scale)...")
    disparity = evaluate_company_disparity(fund_a, fund_b)

    if progress_callback:
        progress_callback(1.0, "Synthesizing normalized side-by-side comparison matrix...")
    
    return {
        "ticker_a": resolved_a,
        "ticker_b": resolved_b,
        "fund_a": fund_a,
        "fund_b": fund_b,
        "rep_a": rep_a,
        "rep_b": rep_b,
        "matrix_a": matrix_a,
        "matrix_b": matrix_b,
        "disparity": disparity,
    }
