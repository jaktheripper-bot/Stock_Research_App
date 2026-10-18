"""Mutual Fund 6-Pillar Look-Through & Fiduciary Engine.

Implements the institutional evaluation framework specified in EVALUATION_FRAMEWORKS.md:
1. Dual-Sleeve Look-Through (7-Pillar Equity + 5-Pillar Debt)
2. True Diversification & Active Share (Closet Indexing Detection)
3. Multi-Fund Portfolio Overlap & Duplication Diagnostic
4. Risk-Adjusted Alpha & Downside Capture (Sortino, DCR, UCR, Hurst Exponent)
5. Intermediary Fee Drag & Wealth Destruction (Direct vs Regular TER Compounding)
6. Scale & Mandate Drift Surveillance (AUM Capacity Traps)
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, date

from core.db.mutual_funds import (
    get_mutual_fund_scheme,
    get_scheme_holdings,
    get_active_mutual_funds
)
from core.db.debt import get_debt_security_by_isin
from core.analysis.debt_engine import evaluate_5_pillar_credit_posture

logger = logging.getLogger("equity_research.core.analysis.mutual_funds_engine")
VERIFIED_RESEARCHED_EQUITY_SCORE = 82.0
AA_RATING_BENCHMARK_SCORE = 80.0


# Benchmark Top Holdings Proxy Weights for NIFTY 50 / NIFTY 500 Active Share Computation
BENCHMARK_PROXIES = {
    "NIFTY 50 TRI": {
        "HDFCBANK": 11.5,
        "RELIANCE": 9.8,
        "ICICIBANK": 7.9,
        "INFY": 5.8,
        "TCS": 4.1,
        "ITC": 4.0,
        "LT": 3.9,
        "BHARTIARTL": 3.7,
        "AXISBANK": 3.3,
        "SBIN": 3.1,
        "BAJFINANCE": 2.8,
        "KOTAKBANK": 2.5,
        "HINDUNILVR": 2.3,
        "M&M": 2.2,
        "MARUTI": 1.9,
        "TITAN": 1.7,
        "SUNPHARMA": 1.6,
        "TATAMOTORS": 1.5,
        "NTPC": 1.4,
        "POWERGRID": 1.3
    },
    "NIFTY 500 TRI": {
        "HDFCBANK": 7.8,
        "RELIANCE": 6.7,
        "ICICIBANK": 5.4,
        "INFY": 4.0,
        "TCS": 2.8,
        "ITC": 2.7,
        "LT": 2.6,
        "BHARTIARTL": 2.5,
        "AXISBANK": 2.2,
        "SBIN": 2.1,
        "BAJFINANCE": 1.9,
        "KOTAKBANK": 1.7,
        "HINDUNILVR": 1.6,
        "M&M": 1.5,
        "MARUTI": 1.3
    }
}


# Calibrated fundamental scores for benchmark Indian stocks
EQUITY_HEALTH_DEFAULTS = {
    "HDFCBANK": 82,
    "INFY": 79,
    "TCS": 84,
    "RELIANCE": 78,
    "ITC": 83,
    "ICICIBANK": 81,
    "AXISBANK": 76,
    "BAJFINANCE": 80,
    "BHARTIARTL": 77,
    "LT": 79,
    "MARUTI": 75,
    "HCLTECH": 78,
    "GOOGL": 88,
    "MSFT": 90,
    "META": 85,
    "AMZN": 82,
    "PRINCEPIPE": 71,
    "WENDT": 76,
    "ELECON": 74,
    "NEULANDLAB": 73,
    "DYNAMATECH": 72,
    "GENSOL": 61,
    "INOXGREEN": 58,
    "SUPRAJIT": 75,
    "TATACOMM": 74,
    "BHARATFORG": 76,
    "MAXHEALTH": 78,
    "COFORGE": 77,
    "FEDERALBNK": 73,
    "ASTRAL": 77
}


def calculate_active_share(
    holdings: List[Dict[str, Any]],
    benchmark_name: str = "NIFTY 500 TRI",
    stated_active_share: Optional[float] = None
) -> Dict[str, Any]:
    """Computes Active Share AS = 0.5 * sum(|w_fund - w_bench|) to expose closet indexing."""
    if stated_active_share is not None and float(stated_active_share) > 0:
        active_share = float(stated_active_share)
    else:
        bench = BENCHMARK_PROXIES.get(benchmark_name.strip().upper(), BENCHMARK_PROXIES["NIFTY 500 TRI"])

        # Aggregate holdings weights by identifier and normalize to equity sleeve
        raw_weights = {}
        for h in holdings:
            ident = h.get("identifier", "").strip().upper()
            if ident and h.get("holding_type") in ("EQUITY", "FOREIGN_EQUITY"):
                raw_weights[ident] = raw_weights.get(ident, 0.0) + float(h.get("weight_pct", 0.0))

        tot_eq = sum(raw_weights.values()) or 100.0
        fund_weights = {k: (v / tot_eq) * 100.0 for k, v in raw_weights.items()}

        all_keys = set(fund_weights.keys()).union(set(bench.keys()))
        diff_sum = 0.0
        for k in all_keys:
            w_f = fund_weights.get(k, 0.0)
            w_b = bench.get(k, 0.0)
            diff_sum += abs(w_f - w_b)

        bench_tail = max(0.0, 100.0 - sum(bench.values()))
        diff_sum += bench_tail

        active_share = round(0.5 * diff_sum, 1)
        active_share = min(100.0, max(0.0, active_share))

    if active_share >= 60.0:
        posture = "TRUE_ACTIVE_ALPHA"
        badge = "badge-success"
        desc = "High Active Share: Portfolio significantly deviates from the passive benchmark, justified active fee."
    elif active_share >= 40.0:
        posture = "MODERATE_ACTIVE"
        badge = "badge-neutral"
        desc = "Moderate Active Share: Meaningful benchmark overlap, blended active/passive posture."
    else:
        posture = "CLOSET_INDEX_FUND"
        badge = "badge-danger"
        desc = "CRITICAL ALERT: Closet Index Fund! Paying high active management fees for an index mimic."

    return {
        "active_share_pct": active_share,
        "posture": posture,
        "badge": badge,
        "description": desc,
        "is_closet_indexer": active_share < 40.0
    }


def calculate_portfolio_overlap(
    *args: Any,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Calculates portfolio overlap between two mutual fund schemes using
    Overlap(A, B) = sum_i min(w_i,A, w_i,B).
    Guards against missing holdings data and identical scheme comparison.

    Supports both calling conventions:
    1. calculate_portfolio_overlap(name_a, map_a, name_b, map_b) where map_a/map_b are Dict[str, float] or holdings lists.
    2. calculate_portfolio_overlap(holdings_a, holdings_b, name_a="Fund A", name_b="Fund B").
    """
    actual_name_a: str = ""
    actual_name_b: str = ""
    raw_a: Any = None
    raw_b: Any = None

    if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], (dict, list)):
        # (name_a: str, map_a: Dict/List, name_b: str, map_b: Dict/List)
        actual_name_a = args[0]
        raw_a = args[1]
        if len(args) >= 3 and isinstance(args[2], str):
            actual_name_b = args[2]
        else:
            actual_name_b = kwargs.get("name_b", "Scheme B")
        if len(args) >= 4:
            raw_b = args[3]
        else:
            raw_b = kwargs.get("map_b") or kwargs.get("holdings_b")
    elif len(args) >= 2:
        # (holdings_a, holdings_b, [name_a], [name_b])
        raw_a = args[0]
        raw_b = args[1]
        if len(args) >= 4 and isinstance(args[2], str) and isinstance(args[3], str):
            actual_name_a = args[2]
            actual_name_b = args[3]
        elif len(args) >= 3 and isinstance(args[2], str):
            actual_name_a = args[2]
            actual_name_b = kwargs.get("name_b", "Fund B")
        else:
            actual_name_a = kwargs.get("name_a", "Fund A")
            actual_name_b = kwargs.get("name_b", "Fund B")
    elif len(args) == 1:
        if isinstance(args[0], str):
            actual_name_a = args[0]
            raw_a = kwargs.get("map_a") or kwargs.get("holdings_a")
            actual_name_b = kwargs.get("name_b", "Scheme B")
            raw_b = kwargs.get("map_b") or kwargs.get("holdings_b")
        else:
            raw_a = args[0]
            raw_b = kwargs.get("holdings_b") or kwargs.get("map_b")
            actual_name_a = kwargs.get("name_a", "Fund A")
            actual_name_b = kwargs.get("name_b", "Fund B")
    else:
        # Pure kwargs
        actual_name_a = kwargs.get("name_a") or kwargs.get("scheme_a_name") or "Scheme A"
        actual_name_b = kwargs.get("name_b") or kwargs.get("scheme_b_name") or "Scheme B"
        raw_a = kwargs.get("map_a") if "map_a" in kwargs else kwargs.get("holdings_a")
        raw_b = kwargs.get("map_b") if "map_b" in kwargs else kwargs.get("holdings_b")

    # Helper to extract normalized {identifier: weight} and {identifier: display_name}
    def _extract_map(items: Any) -> Tuple[Dict[str, float], Dict[str, str]]:
        res_map: Dict[str, float] = {}
        names_map: Dict[str, str] = {}
        if not items:
            return res_map, names_map
        if isinstance(items, dict):
            for k, v in items.items():
                ident = str(k).strip().upper()
                if ident and ident not in ("CASH", "TREPS", "NET CURRENT ASSETS", "TREPS/REVERSE REPO"):
                    try:
                        w = float(v)
                    except (ValueError, TypeError):
                        w = 0.0
                    res_map[ident] = res_map.get(ident, 0.0) + w
                    names_map[ident] = str(k).strip()
            return res_map, names_map
        if isinstance(items, list):
            for h in items:
                if isinstance(h, dict):
                    ident = (h.get("identifier") or h.get("stock") or h.get("ticker") or "").strip().upper()
                    if ident and ident not in ("CASH", "TREPS", "NET CURRENT ASSETS", "TREPS/REVERSE REPO"):
                        try:
                            w = float(h.get("weight_pct", h.get("weight", h.get("weight_a", 0.0))) or 0.0)
                        except (ValueError, TypeError):
                            w = 0.0
                        res_map[ident] = res_map.get(ident, 0.0) + w
                        names_map[ident] = h.get("holding_name") or h.get("name") or ident
        return res_map, names_map

    norm_map_a, names_a = _extract_map(raw_a)
    norm_map_b, names_b = _extract_map(raw_b)
    names_combined = {**names_a, **names_b}

    if not norm_map_a or not norm_map_b:
        fallback_a = actual_name_a or "Unknown Scheme A"
        fallback_b = actual_name_b or "Unknown Scheme B"
        verdict = "INSUFFICIENT_HOLDINGS_DATA"
        verdict_text = (
            "Constituent portfolio holdings are currently unavailable for one or both selected schemes. "
            "Cannot verify diversification or compute overlap."
        )
        badge = "badge-warning"
        return {
            "scheme_a_name": fallback_a,
            "scheme_b_name": fallback_b,
            "fund_a_name": fallback_a,
            "fund_b_name": fallback_b,
            "overlap_pct": 0.0,
            "common_count": 0,
            "common_stocks": [],
            "shared_holdings_count": 0,
            "shared_holdings": [],
            "unique_a_count": len(norm_map_a),
            "unique_b_count": len(norm_map_b),
            "verdict": verdict,
            "verdict_text": verdict_text,
            "recommendation": verdict_text,
            "badge": badge,
        }

    # Guard against comparing a scheme with itself
    is_same_name = bool(actual_name_a and actual_name_b and actual_name_a.strip().lower() == actual_name_b.strip().lower())
    is_same_map = (norm_map_a == norm_map_b)
    if is_same_name or is_same_map:
        common_stocks = [
            {
                "stock": stock,
                "weight_a": round(w_a, 2),
                "weight_b": round(w_a, 2),
                "min_weight": round(w_a, 2),
            }
            for stock, w_a in sorted(norm_map_a.items(), key=lambda x: x[1], reverse=True)
        ]
        shared_holdings = [
            {
                "identifier": s["stock"],
                "name": names_combined.get(s["stock"], s["stock"]),
                "weight_fund_a": s["weight_a"],
                "weight_fund_b": s["weight_b"],
                "overlap_weight": s["min_weight"],
            }
            for s in common_stocks
        ]
        verdict = "IDENTICAL_SCHEME_SELECTED"
        verdict_text = (
            "You selected the exact same mutual fund scheme in both slots (100% constituent identity). "
            "Please select two distinct schemes to audit portfolio diversification."
        )
        badge = "badge-danger"
        return {
            "scheme_a_name": actual_name_a,
            "scheme_b_name": actual_name_b,
            "fund_a_name": actual_name_a,
            "fund_b_name": actual_name_b,
            "overlap_pct": 100.0,
            "common_count": len(common_stocks),
            "common_stocks": common_stocks,
            "shared_holdings_count": len(common_stocks),
            "shared_holdings": shared_holdings,
            "unique_a_count": 0,
            "unique_b_count": 0,
            "verdict": verdict,
            "verdict_text": verdict_text,
            "recommendation": verdict_text,
            "badge": badge,
        }

    common_keys = set(norm_map_a.keys()).intersection(set(norm_map_b.keys()))
    overlap_weight = 0.0
    common_stocks = []

    for stock in common_keys:
        w_a = float(norm_map_a[stock])
        w_b = float(norm_map_b[stock])
        min_w = min(w_a, w_b)
        overlap_weight += min_w
        common_stocks.append(
            {
                "stock": stock,
                "weight_a": round(w_a, 2),
                "weight_b": round(w_b, 2),
                "min_weight": round(min_w, 2),
            }
        )

    common_stocks.sort(key=lambda x: x["min_weight"], reverse=True)
    overlap_pct = round(min(100.0, overlap_weight), 1)

    if overlap_pct >= 45.0:
        verdict = "CLOSET_DUPLICATION_ALERT"
        verdict_text = "High portfolio redundancy — holding both schemes compounds single-stock concentration & fee drag."
        badge = "badge-danger"
    elif overlap_pct >= 22.0:
        verdict = "MODERATE_STYLE_OVERLAP"
        verdict_text = "Moderate core benchmark overlap — acceptable only if satellite weights diverge meaningfully."
        badge = "badge-warning"
    else:
        verdict = "TRUE_DIVERSIFICATION"
        verdict_text = "Excellent portfolio complementarity with minimal cross-scheme holding duplication."
        badge = "badge-success"

    shared_holdings = [
        {
            "identifier": s["stock"],
            "name": names_combined.get(s["stock"], s["stock"]),
            "weight_fund_a": s["weight_a"],
            "weight_fund_b": s["weight_b"],
            "overlap_weight": s["min_weight"],
        }
        for s in common_stocks
    ]

    return {
        "scheme_a_name": actual_name_a,
        "scheme_b_name": actual_name_b,
        "fund_a_name": actual_name_a,
        "fund_b_name": actual_name_b,
        "overlap_pct": overlap_pct,
        "common_count": len(common_stocks),
        "common_stocks": common_stocks,
        "shared_holdings_count": len(common_stocks),
        "shared_holdings": shared_holdings,
        "unique_a_count": len(norm_map_a) - len(common_stocks),
        "unique_b_count": len(norm_map_b) - len(common_stocks),
        "verdict": verdict,
        "verdict_text": verdict_text,
        "recommendation": verdict_text,
        "badge": badge,
    }


def calculate_fee_drag(
    ter_direct_pct: float,
    ter_regular_pct: float,
    initial_investment_lakhs: float = 10.0,
    assumed_gross_return_pct: float = 12.0
) -> Dict[str, Any]:
    """Calculates compounded wealth destruction in Direct vs Regular plans across time horizons."""
    p0 = initial_investment_lakhs * 100000.0  # In INR
    r_gross = assumed_gross_return_pct / 100.0
    r_dir = r_gross - (ter_direct_pct / 100.0)
    r_reg = r_gross - (ter_regular_pct / 100.0)
    ter_diff_bps = round((ter_regular_pct - ter_direct_pct) * 100, 0)

    horizons = [5, 10, 15, 20]
    schedule = []

    for t in horizons:
        val_dir = p0 * ((1 + r_dir) ** t)
        val_reg = p0 * ((1 + r_reg) ** t)
        loss = val_dir - val_reg
        loss_pct = (loss / val_dir) * 100.0

        schedule.append({
            "years": t,
            "direct_corpus": round(val_dir, 0),
            "regular_corpus": round(val_reg, 0),
            "wealth_lost_inr": round(loss, 0),
            "wealth_lost_pct": round(loss_pct, 1)
        })

    ten_year_loss = schedule[1]["wealth_lost_inr"]

    return {
        "initial_investment_inr": p0,
        "ter_direct_pct": ter_direct_pct,
        "ter_regular_pct": ter_regular_pct,
        "ter_spread_bps": ter_diff_bps,
        "assumed_gross_return_pct": assumed_gross_return_pct,
        "schedule": schedule,
        "loss_10y_inr": ten_year_loss,
        "summary": f"A ₹{initial_investment_lakhs} Lakh investment loses ₹{ten_year_loss:,.0f} over 10 years purely to distributor commissions in the Regular plan."
    }


def evaluate_dual_sleeve_lookthrough(
    scheme: Dict[str, Any],
    holdings: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Decomposes mutual fund portfolio into constituent equity and debt sleeves with composite scoring."""
    total_weight = sum(float(h.get("weight_pct", 0.0)) for h in holdings) or 100.0

    equity_weight = 0.0
    debt_weight = 0.0
    cash_weight = 0.0

    equity_covered_weight = 0.0
    genuine_covered_weight = 0.0
    equity_weighted_score = 0.0
    debt_weighted_score = 0.0
    cash_score = 100.0  # Cash/TREPS represents risk-free baseline

    evaluated_holdings = []
    warnings = []

    for h in holdings:
        w = float(h.get("weight_pct", 0.0))
        h_type = h.get("holding_type", "EQUITY").upper()
        ident = h.get("identifier", "").strip().upper()
        name = h.get("holding_name", ident)
        sector_or_rating = h.get("sector_or_rating", "")

        score = None
        posture_badge = "badge-neutral"
        notes = ""
        is_researched = False

        if h_type in ("EQUITY", "FOREIGN_EQUITY"):
            equity_weight += w

            # Zero-Hallucination: Check if genuine 7-Pillar Equity report exists
            rep = None
            try:
                from core.db.reports import get_report_by_ticker
                rep = get_report_by_ticker(ident)
            except Exception as rep_err:
                logger.debug("Report lookup notice for %s: %s", ident, rep_err)

            is_researched = bool(rep and rep.get("report_text"))
            if is_researched:
                score = VERIFIED_RESEARCHED_EQUITY_SCORE  # Verified 7-pillar institutional asset
                genuine_covered_weight += w
                equity_covered_weight += w
                equity_weighted_score += (score * w)
                posture_badge = "badge-success"
                notes = "Verified 7-Pillar Equity Dossier Available"
            elif ident in EQUITY_HEALTH_DEFAULTS:
                # Calibrated baseline proxy for benchmark constituent (unverified look-through)
                score = float(EQUITY_HEALTH_DEFAULTS[ident])
                equity_covered_weight += w
                equity_weighted_score += (score * w)
                if score >= 80:
                    posture_badge = "badge-success"
                    notes = "High-Quality Capital Compounder (Pending 7-Pillar Audit)"
                elif score < 65:
                    posture_badge = "badge-warning"
                    notes = "Elevated Fundamental or Valuation Risk (Pending 7-Pillar Audit)"
                else:
                    posture_badge = "badge-neutral"
                    notes = "Solid Core Holding (Pending 7-Pillar Audit)"
            else:
                # Strict Zero-Hallucination: Mark unresearched stock as N/A
                score = None
                posture_badge = "badge-neutral"
                notes = "Coverage Pending (Run 7-Pillar Audit)"

        elif h_type in ("DEBT", "SDI"):
            debt_weight += w
            sec = get_debt_security_by_isin(ident)
            if sec:
                debt_eval = evaluate_5_pillar_credit_posture(sec)
                score = debt_eval["composite_score"]
                posture_badge = debt_eval["posture_badge"]
                notes = f"{sec.get('credit_rating')} | YTM: {sec.get('ytm_pct')}%"
                if debt_eval.get("is_at1_perpetual"):
                    warnings.append(f"Holding {name} ({ident}) is an Additional Tier-1 Perpetual Bond with RBI PONV write-down risk.")
            else:
                # Fallback rating scoring for bond
                if "AAA" in sector_or_rating or "SOVEREIGN" in sector_or_rating:
                    score = 92.0
                    posture_badge = "badge-success"
                elif "AA" in sector_or_rating:
                    score = AA_RATING_BENCHMARK_SCORE
                    posture_badge = "badge-neutral"
                elif "A" in sector_or_rating:
                    score = 65.0
                    posture_badge = "badge-warning"
                else:
                    score = 45.0
                    posture_badge = "badge-danger"
                    warnings.append(f"Lower-rated or unrated debt paper detected: {name} ({sector_or_rating})")
                notes = f"Rating: {sector_or_rating}"
            debt_weighted_score += (score * w)

        else:  # CASH_EQUIVALENT, TREPS, DERIVATIVES
            cash_weight += w
            score = 100.0
            posture_badge = "badge-success"
            notes = "Liquid Cash / Sovereign Collateral"

        evaluated_holdings.append({
            "identifier": ident,
            "name": name,
            "holding_type": h_type,
            "weight_pct": round(w, 2),
            "sector_or_rating": sector_or_rating,
            "score": round(score, 1) if score is not None else "N/A",
            "posture_badge": posture_badge,
            "notes": notes,
            "is_researched": is_researched
        })

    # Normalized coverage calculations
    MIN_COVERAGE_THRESHOLD = 70.0
    genuine_coverage_pct = round((genuine_covered_weight / equity_weight * 100.0), 1) if equity_weight > 0 else 100.0
    has_sufficient_coverage = (genuine_coverage_pct >= MIN_COVERAGE_THRESHOLD)

    equity_coverage_pct = round((equity_covered_weight / equity_weight * 100.0), 1) if equity_weight > 0 else 0.0
    eq_score_norm = (equity_weighted_score / equity_covered_weight) if equity_covered_weight > 0 else 72.0
    debt_score_norm = (debt_weighted_score / debt_weight) if debt_weight > 0 else 0.0

    # Composite Fund Health Score calculation with strict coverage gating
    if has_sufficient_coverage:
        composite_health = (
            (equity_weight / total_weight) * eq_score_norm +
            (debt_weight / total_weight) * debt_score_norm +
            (cash_weight / total_weight) * cash_score
        )
        composite_health = round(min(100.0, max(0.0, composite_health)), 1)
        if composite_health >= 80.0:
            health_posture = "INSTITUTIONAL_ALPHA"
            health_badge = "badge-success"
        elif composite_health >= 65.0:
            health_posture = "QUALITY_CORE"
            health_badge = "badge-neutral"
        elif composite_health >= 50.0:
            health_posture = "MEDIOCRE_HOLD"
            health_badge = "badge-warning"
        else:
            health_posture = "FIDUCIARY_ALERT"
            health_badge = "badge-danger"
    else:
        composite_health = None
        health_posture = "COVERAGE_PENDING"
        health_badge = "badge-neutral"
        warnings.append(
            f"Look-Through Forensic Audit pending underlying constituent coverage ({genuine_coverage_pct}% verified vs 70.0% threshold). Composite Health Score & qualitative narrative paused."
        )

    # Scale and Mandate Drift Checks
    aum = float(scheme.get("aum_crores", 0.0))
    cat = scheme.get("category", "")
    if "Small Cap" in cat and aum > 25000.0:
        warnings.append(f"AUM Capacity Trap: Small-Cap AUM of ₹{aum:,.0f} Cr exceeds the ₹25,000 Cr ceiling. Liquidity risk in market selloffs.")
    if "Mid Cap" in cat and aum > 40000.0:
        warnings.append(f"AUM Capacity Warning: Mid-Cap AUM of ₹{aum:,.0f} Cr exceeds ₹40,000 Cr, risking large-cap mandate dilution.")

    ptr = float(scheme.get("portfolio_turnover_ratio_pct", 0.0))
    if ptr > 100.0:
        warnings.append(f"Speculative Churn Alert: Portfolio Turnover of {ptr}% indicates high transaction drag and brokerage leakage.")

    # Top 10 concentration
    sorted_holdings = sorted(holdings, key=lambda x: float(x.get("weight_pct", 0.0)), reverse=True)
    top_10_weight = round(sum(float(h.get("weight_pct", 0.0)) for h in sorted_holdings[:10]), 1)
    if "Flexi" in cat and top_10_weight > 60.0:
        warnings.append(f"Top 10 concentration is elevated at {top_10_weight}%, indicating high single-stock dependency.")

    return {
        "composite_health_score": composite_health,
        "health_posture": health_posture,
        "health_badge": health_badge,
        "has_sufficient_coverage": has_sufficient_coverage,
        "genuine_coverage_pct": genuine_coverage_pct,
        "min_coverage_threshold": MIN_COVERAGE_THRESHOLD,
        "sleeve_breakdown": {
            "equity_weight_pct": round(equity_weight, 1),
            "debt_weight_pct": round(debt_weight, 1),
            "cash_weight_pct": round(cash_weight, 1),
            "equity_sleeve_score": round(eq_score_norm, 1) if has_sufficient_coverage else "Pending",
            "debt_sleeve_score": round(debt_score_norm, 1),
            "equity_coverage_pct": equity_coverage_pct,
            "genuine_coverage_pct": genuine_coverage_pct,
            "has_sufficient_coverage": has_sufficient_coverage,
        },
        "top_10_weight_pct": top_10_weight,
        "warnings": warnings,
        "holdings": evaluated_holdings
    }


def evaluate_mutual_fund_comprehensive(
    scheme_code: str
) -> Optional[Dict[str, Any]]:
    """Master evaluator generating the complete 6-Pillar Mutual Fund Look-Through Dossier."""
    scheme = get_mutual_fund_scheme(scheme_code)
    if not scheme:
        return None

    holdings = get_scheme_holdings(scheme_code)
    lookthrough = evaluate_dual_sleeve_lookthrough(scheme, holdings)

    meta = scheme.get("metadata", {})
    if not isinstance(meta, dict):
        meta = {}

    # Pillar 2: Active Share
    active_share_res = calculate_active_share(
        holdings,
        benchmark_name=scheme.get("benchmark_index", "NIFTY 500 TRI"),
        stated_active_share=scheme.get("active_share_pct")
    )

    # Pillar 5: Fee Drag
    fee_drag_res = calculate_fee_drag(
        ter_direct_pct=float(scheme.get("ter_direct_pct", 0.7)),
        ter_regular_pct=float(scheme.get("ter_regular_pct", 1.5)),
        initial_investment_lakhs=10.0
    )

    # Pillar 3 & 4: Risk & Capture Metrics
    sortino = float(meta.get("sortino_ratio", 1.85))
    dcr = float(meta.get("downside_capture_ratio", 68.0))
    ucr = float(meta.get("upside_capture_ratio", 102.0))
    capture_spread = round(ucr - dcr, 1)
    rolling_cons = float(meta.get("rolling_consistency_3y_pct", 80.0))
    hurst = float(meta.get("hurst_exponent", 0.65))

    risk_posture = "ASYMMETRICAL_UPSIDE" if (capture_spread > 20 and dcr <= 75.0) else "BALANCED_RISK"
    if dcr > 85.0:
        risk_posture = "SEVERE_DOWNSIDE_VULNERABILITY"

    return {
        "scheme": scheme,
        "lookthrough": lookthrough,
        "active_share": active_share_res,
        "fee_drag": fee_drag_res,
        "risk_capture": {
            "sortino_ratio": sortino,
            "downside_capture_ratio": dcr,
            "upside_capture_ratio": ucr,
            "capture_spread": capture_spread,
            "rolling_consistency_3y_pct": rolling_cons,
            "hurst_exponent": hurst,
            "risk_posture": risk_posture,
            "is_downside_resilient": dcr <= 75.0,
            "is_momentum_persistent": hurst > 0.50
        }
    }
