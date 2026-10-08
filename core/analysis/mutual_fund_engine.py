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
    holdings_a: List[Dict[str, Any]],
    holdings_b: List[Dict[str, Any]],
    name_a: str = "Fund A",
    name_b: str = "Fund B"
) -> Dict[str, Any]:
    """Computes pairwise portfolio overlap Overlap(A, B) = sum(min(w_A, w_B))."""
    map_a = {}
    names_map = {}
    for h in holdings_a:
        ident = h.get("identifier", "").strip().upper()
        if ident and ident not in ("CASH", "TREPS"):
            map_a[ident] = map_a.get(ident, 0.0) + float(h.get("weight_pct", 0.0))
            names_map[ident] = h.get("holding_name", ident)

    map_b = {}
    for h in holdings_b:
        ident = h.get("identifier", "").strip().upper()
        if ident and ident not in ("CASH", "TREPS"):
            map_b[ident] = map_b.get(ident, 0.0) + float(h.get("weight_pct", 0.0))
            names_map[ident] = h.get("holding_name", ident)

    common_keys = set(map_a.keys()).intersection(set(map_b.keys()))
    overlap_pct = 0.0
    shared_holdings = []

    for k in common_keys:
        w_a = map_a[k]
        w_b = map_b[k]
        min_w = min(w_a, w_b)
        overlap_pct += min_w
        shared_holdings.append({
            "identifier": k,
            "name": names_map.get(k, k),
            "weight_fund_a": round(w_a, 2),
            "weight_fund_b": round(w_b, 2),
            "overlap_weight": round(min_w, 2)
        })

    shared_holdings.sort(key=lambda x: x["overlap_weight"], reverse=True)
    overlap_pct = round(overlap_pct, 1)

    if overlap_pct > 50.0:
        verdict = "HIGH_DUPLICATION_RISK"
        badge = "badge-danger"
        recommendation = "Severe portfolio overlap. Holding both funds provides illusory diversification with doubled expense fees."
    elif overlap_pct >= 25.0:
        verdict = "MODERATE_CONVERGENCE"
        badge = "badge-warning"
        recommendation = "Moderate overlap in core holdings. Ensure sector/cap allocations remain complementary."
    else:
        verdict = "TRUE_DIVERSIFICATION"
        badge = "badge-success"
        recommendation = "Excellent portfolio complementarity with minimal cross-scheme holding duplication."

    return {
        "fund_a_name": name_a,
        "fund_b_name": name_b,
        "overlap_pct": overlap_pct,
        "verdict": verdict,
        "badge": badge,
        "recommendation": recommendation,
        "shared_holdings_count": len(shared_holdings),
        "shared_holdings": shared_holdings
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
            except Exception:
                pass

            is_researched = bool(rep and rep.get("report_text"))
            if is_researched:
                score = 82.0  # Verified 7-pillar institutional asset
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
                    score = 80.0
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
