"""Multi-Peer Cluster Matrix Engine (2 to 5 Equities) — Non-Advisory Quantitative Benchmarking."""

import asyncio
import math
import statistics
from typing import Any, Dict, List, Optional

from normalizer import clean_ticker
from core.db import get_report_by_ticker_sync
from core.analysis.fundamentals import get_stock_fundamentals, enrich_fundamentals
from core.analysis.parser import extract_health_matrix
from core.analysis.peer_comparison import build_comparison_pillars, evaluate_company_disparity


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).replace(",", "").replace("%", "").replace("₹", "").strip()
    if not s or s.upper() in ("N/A", "NM", "NONE", "-", "—"):
        return None
    try:
        val = float(s)
        return None if (math.isnan(val) or math.isinf(val)) else val
    except ValueError:
        return None


def _load_one_sync(sym: str) -> Dict[str, Any]:
    rep = get_report_by_ticker_sync(sym)
    fund = enrich_fundamentals(sym, get_stock_fundamentals(sym, fast_db_first=True) or {})
    matrix = extract_health_matrix(rep.get("report_text", "")) if rep else {}
    raw_mcap = _num(fund.get("market_cap"))
    return {
        "ticker": sym,
        "name": (rep or {}).get("short_name") or fund.get("company_name") or sym,
        "fundamentals": fund,
        "pillars": build_comparison_pillars(matrix),
        "metrics": {
            "market_cap_cr": round(raw_mcap / 1e7, 1) if (raw_mcap is not None and raw_mcap > 0) else None,
            "pe_ratio": _num(fund.get("pe_ratio")),
            "roce_pct": _num(fund.get("roce")),
            "roe_pct": _num(fund.get("roe")),
            "opm_pct": _num(fund.get("operating_margin") or fund.get("opm")),
            "debt_to_equity": _num(fund.get("debt_to_equity")),
        },
    }


async def compare_peer_cluster(tickers: List[str]) -> Dict[str, Any]:
    cleaned: List[str] = []
    for raw in tickers or []:
        c = clean_ticker(raw)
        if c and c not in cleaned:
            cleaned.append(c)
    if len(cleaned) < 2 or len(cleaned) > 5:
        raise ValueError("Peer cluster requires between 2 and 5 distinct tickers.")

    async def _load_one(sym: str) -> Dict[str, Any]:
        return await asyncio.to_thread(_load_one_sync, sym)

    peers = list(await asyncio.gather(*[_load_one(t) for t in cleaned]))

    # Compute cluster medians across populated peers
    metric_keys = ("market_cap_cr", "pe_ratio", "roce_pct", "roe_pct", "opm_pct", "debt_to_equity")
    cluster_medians: Dict[str, Optional[float]] = {}
    for k in metric_keys:
        vals = [p["metrics"][k] for p in peers if p["metrics"][k] is not None]
        cluster_medians[k] = round(statistics.median(vals), 2) if vals else None

    # Pairwise disparity warnings against anchor peer[0]
    disparity_warnings: List[str] = []
    for other in peers[1:]:
        disp = evaluate_company_disparity(peers[0]["fundamentals"], other["fundamentals"])
        for w in disp.get("warnings", []):
            tag = f"[{peers[0]['ticker']} vs {other['ticker']}] {w}"
            if tag not in disparity_warnings:
                disparity_warnings.append(tag)

    return {
        "count": len(peers),
        "tickers": cleaned,
        "peers": peers,
        "cluster_medians": cluster_medians,
        "disparity_warnings": disparity_warnings,
        "compliance_notice": "Descriptive peer-cluster dispersion table under SEBI Safe Harbor; no ranking implies a recommendation.",
    }

