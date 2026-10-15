"""Analytical Engine for National ETF Matrix, Tracking Error Auditing, and Liquidity Tiers.

Evaluates exchange pricing vs. NAV fair value, tracking error deviations,
expense ratio drag, and secondary market liquidity depth across all 9 institutional categories.
Complies with SEBI (Mutual Funds) Regulations, 1996 passive portfolio benchmarks.
"""

from typing import Dict, Any, List, Optional
from core.db.sovereign import get_etf_matrix, get_etf_by_symbol, save_etf_matrix_items

VALID_CATEGORIES = [
    "ALL",
    "EQUITY_INDEX",
    "EQUITY_SECTORAL",
    "EQUITY_FACTOR",
    "COMMODITY_GOLD",
    "COMMODITY_SILVER",
    "DEBT_SOVEREIGN",
    "DEBT_TARGET_MATURITY",
    "LIQUID",
    "INTERNATIONAL"
]

CATEGORY_DISPLAY_NAMES = {
    "ALL": "All ETFs",
    "EQUITY_INDEX": "Equity Indices",
    "EQUITY_SECTORAL": "Sectoral & Thematic",
    "EQUITY_FACTOR": "Smart Beta & Factor",
    "COMMODITY_GOLD": "Gold ETFs",
    "COMMODITY_SILVER": "Silver ETFs",
    "DEBT_SOVEREIGN": "G-Sec & Gilts",
    "DEBT_TARGET_MATURITY": "Bharat Bond & Target",
    "LIQUID": "Overnight & Liquid",
    "INTERNATIONAL": "Global & International"
}


def _format_aum(crores: float) -> str:
    """Formats AUM in Indian financial nomenclature (Crores or Lakh Crores)."""
    if crores >= 100000.0:
        return f"₹{crores / 100000.0:.2f} Lk Cr"
    elif crores >= 1000.0:
        return f"₹{crores:,.0f} Cr"
    else:
        return f"₹{crores:.1f} Cr"


def evaluate_etf_matrix(
    category: Optional[str] = None,
    query: Optional[str] = None,
    sort_by: Optional[str] = None,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Audits the ETF matrix, identifying arbitrage divergences, tracking error drag,
    and liquidity risk tiers across all AMFI-listed ETFs.
    """
    clean_cat = category.strip().upper() if category and category.strip().upper() != "ALL" else None
    etfs = get_etf_matrix(category=clean_cat, query=query, sort_by=sort_by, limit=limit)

    # Fetch global universe stats for tab badges and benchmark context
    all_etfs = get_etf_matrix(category=None)
    total_universe_aum = sum(item.get("aum_crores", 0.0) for item in all_etfs)

    # Category counts across full universe
    category_counts = {"ALL": len(all_etfs)}
    for cat in VALID_CATEGORIES:
        if cat != "ALL":
            category_counts[cat] = sum(1 for item in all_etfs if item.get("category") == cat)

    # Compute filtered cohort statistics
    filtered_aum = sum(item.get("aum_crores", 0.0) for item in etfs)
    high_liquidity_count = sum(1 for item in etfs if item.get("liquidity_tier") == "HIGH_LIQUIDITY")
    divergence_count = sum(1 for item in etfs if abs(item.get("premium_discount_pct", 0.0)) >= 0.5)

    avg_te = round(sum(item.get("tracking_error_1y", 0.0) for item in etfs) / max(len(etfs), 1), 3)
    avg_ter = round(sum(item.get("expense_ratio_pct", 0.0) for item in etfs) / max(len(etfs), 1), 3)

    # Enrich each ETF with forensic indicators
    enriched_etfs = []
    for item in etfs:
        pd = item.get("premium_discount_pct", 0.0)
        lp = item.get("last_price", 0.0)
        nav = item.get("nav", 0.0)
        aum = item.get("aum_crores", 0.0)
        tier = item.get("liquidity_tier", "HIGH_LIQUIDITY")

        if pd > 0.5:
            arb_signal = "PREMIUM_EXPENSIVE"
            arb_note = f"Trading at {pd:+.2f}% premium over Fair NAV. Caution: Buyer pays impact surcharge."
        elif pd < -0.5:
            arb_signal = "DISCOUNT_ATTRACTIVE"
            arb_note = f"Trading at {pd:+.2f}% discount to Fair NAV. Potential arbitrage entry opportunity."
        else:
            arb_signal = "FAIR_VALUE"
            arb_note = "Tight exchange pricing matching Fair NAV within 50 bps."

        enriched = dict(item)
        enriched["arbitrage_signal"] = arb_signal
        enriched["arbitrage_note"] = arb_note
        enriched["aum_formatted"] = _format_aum(aum)
        enriched_etfs.append(enriched)

    # Grouping dictionary for backward compatibility with existing tests
    grouped = {
        "ALL": enriched_etfs,
        "EQUITY_INDEX": [x for x in enriched_etfs if x.get("category") == "EQUITY_INDEX"],
        "COMMODITY": [x for x in enriched_etfs if "COMMODITY" in x.get("category", "")],
        "DEBT_SOVEREIGN": [x for x in enriched_etfs if "DEBT" in x.get("category", "") or x.get("category") == "LIQUID"]
    }
    # Add all granular categories to grouped dict
    for cat in VALID_CATEGORIES:
        grouped[cat] = [x for x in enriched_etfs if x.get("category") == cat]

    return {
        "total_tracked_etfs": len(enriched_etfs),
        "total_universe_count": len(all_etfs),
        "total_aum_crores": round(filtered_aum, 1),
        "total_universe_aum_crores": round(total_universe_aum, 1),
        "total_aum_lakh_cr": round(filtered_aum / 100000.0, 2),
        "high_liquidity_count": high_liquidity_count,
        "nav_divergence_alerts": divergence_count,
        "avg_tracking_error_pct": avg_te,
        "avg_expense_ratio_pct": avg_ter,
        "category_counts": category_counts,
        "category_display_names": CATEGORY_DISPLAY_NAMES,
        "current_category": clean_cat or "ALL",
        "current_sort": sort_by or "aum_desc",
        "current_query": query or "",
        "etfs": enriched_etfs,
        "grouped_by_category": grouped
    }


def _extract_amc_name(scheme_name: str) -> str:
    """Extracts the Asset Management Company (AMC) name from scheme title."""
    amcs = [
        "Nippon India", "SBI", "HDFC", "ICICI Prudential", "Mirae Asset",
        "Kotak", "UTI", "Motilal Oswal", "Edelweiss", "Axis", "Aditya Birla Sun Life",
        "Bandhan", "Tata", "DSP", "Groww", "Zerodha", "Quant", "Navi", "Invesco"
    ]
    for amc in amcs:
        if amc.lower() in scheme_name.lower():
            return f"{amc} Mutual Fund"
    return "AMFI Registered AMC"


def get_etf_detail(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves deep forensic details for a single ETF, including underlying index,
    peer benchmarks in same category, tracking error audit, arbitrage corridor, and liquidity depth.
    """
    if not symbol:
        return None

    item = get_etf_by_symbol(symbol)
    if not item:
        return None

    category = item.get("category", "EQUITY_INDEX")
    category_label = CATEGORY_DISPLAY_NAMES.get(category, category)
    peers = get_etf_matrix(category=category, sort_by="aum_desc", limit=6)
    # Remove self from peers and enrich
    peer_comparisons = []
    for p in peers:
        if p["symbol"].upper() != symbol.strip().upper():
            peer_item = dict(p)
            peer_item["aum_formatted"] = _format_aum(peer_item.get("aum_crores", 0.0))
            peer_comparisons.append(peer_item)
    peer_comparisons = peer_comparisons[:5]

    pd = float(item.get("premium_discount_pct", 0.0))
    lp = float(item.get("last_price", 0.0))
    nav = float(item.get("nav", 0.0))
    te = float(item.get("tracking_error_1y", 0.05))
    ter = float(item.get("expense_ratio_pct", 0.10))
    aum = float(item.get("aum_crores", 0.0))
    volume = float(item.get("avg_daily_volume", 0.0))
    turnover = float(item.get("avg_daily_turnover_cr", 0.0))
    liquidity_tier = item.get("liquidity_tier", "HIGH_LIQUIDITY")

    spread_inr = round(lp - nav, 2)

    # Arbitrage Corridor Evaluation
    if pd > 0.5:
        arb_signal = "PREMIUM_EXPENSIVE"
        badge_color = "#f59e0b"
        arb_corridor = "Outside AP Creation Band (+50 bps)"
        ap_incentive = "Authorized Participants will short ETF on exchange and create new units with AMC to capture spread."
        retail_guidance = f"Avoid large market buy orders. Exchange buyers currently pay an unearned {pd:+.2f}% (+₹{abs(spread_inr):.2f}) impact surcharge above Fair NAV."
    elif pd < -0.5:
        arb_signal = "DISCOUNT_ATTRACTIVE"
        badge_color = "#10b981"
        arb_corridor = "Outside AP Redemption Band (-50 bps)"
        ap_incentive = "Authorized Participants will buy ETF on exchange and redeem basket with AMC for cash/constituents."
        retail_guidance = f"Favorable entry window for long-term allocators. Security trades at a {pd:+.2f}% (-₹{abs(spread_inr):.2f}) discount to fair NAV."
    else:
        arb_signal = "FAIR_VALUE"
        badge_color = "#94a3b8"
        arb_corridor = "Within Arbitrage Equilibrium Band (±50 bps)"
        ap_incentive = "Market makers quoting tight bid-ask spreads around iNAV. Arbitrage spread is within statutory cost bounds."
        retail_guidance = "Fair market pricing. Limit orders placed near CMP execute with minimal fair-value distortion."

    arbitrage_analysis = {
        "market_price": lp,
        "fair_nav": nav,
        "spread_pct": pd,
        "spread_inr": spread_inr,
        "signal": arb_signal,
        "badge_color": badge_color,
        "corridor_status": arb_corridor,
        "ap_incentive": ap_incentive,
        "retail_guidance": retail_guidance,
        "creation_basket_approx_cr": 0.25 if aum < 1000.0 else 0.50
    }

    # Tracking Error & Replication Fidelity
    te_grade = "EXEMPLARY" if te <= 0.05 else ("ACCEPTABLE" if te <= 0.15 else "ELEVATED_DRAG")
    rep_style = (
        "Physical Full Index Replication" if "EQUITY" in category
        else ("Direct Physical Bullion Vault (999 Purity)" if "COMMODITY" in category
        else ("Direct Sovereign G-Sec Portfolio" if "DEBT" in category
        else "TREPS / Overnight Reverse Repo"))
    )

    replication_audit = {
        "tracking_error_1y": te,
        "tracking_error_grade": te_grade,
        "replication_style": rep_style,
        "ter_fee_pct": ter,
        "drag_breakdown": [
            {"factor": "Management Fee (TER)", "impact": f"{ter:.2f}%", "source": "Continuous deduction from daily NAV"},
            {"factor": "Cash Drag", "impact": "0.01% - 0.03%", "source": "Uninvested cash maintained for daily redemptions"},
            {"factor": "Dividend Lag", "impact": "0.02% - 0.04%", "source": "Timing latency between corporate action ex-date and reinvestment"}
        ]
    }

    # Liquidity Depth
    liquidity_audit = {
        "avg_daily_volume": volume,
        "avg_daily_turnover_cr": turnover,
        "tier": liquidity_tier,
        "tier_badge": "High" if liquidity_tier == "HIGH_LIQUIDITY" else ("Moderate" if liquidity_tier == "MODERATE_LIQUIDITY" else "Low"),
        "estimated_impact_cost_bps": 3 if liquidity_tier == "HIGH_LIQUIDITY" else (12 if liquidity_tier == "MODERATE_LIQUIDITY" else 35)
    }

    # Pre-Mortem Inversion Risk Ledger
    inversion_risks = [
        {
            "title": "Authorized Participant Withdrawal Risk",
            "desc": "During acute liquidity panics or circuit breaker triggers in underlying constituents, APs may temporarily widen bid-ask spreads, blowing out the premium/discount band.",
            "severity": "CRITICAL" if liquidity_tier == "LOW_LIQUIDITY" else "MODERATE"
        },
        {
            "title": "Index Rebalancing Friction & Turnover Drag",
            "desc": f"Semi-annual reconstitution of {item.get('underlying_index')} requires the fund manager to transact large blocks, creating transaction impact costs inside NAV.",
            "severity": "LOW" if "Nifty 50" in item.get("underlying_index", "") else "MODERATE"
        },
        {
            "title": "Compounded Fee Drag over Holding Period",
            "desc": f"At {ter:.2f}% TER, a 10-year holding period causes approximately {round(ter * 10.5, 2)}% in cumulative fee leakage compared to a theoretical zero-cost benchmark.",
            "severity": "LOW" if ter <= 0.10 else "MODERATE"
        },
        {
            "title": "Tracking Error Spike under High Volatility",
            "desc": f"Current 1Y tracking error of {te:.2f}% can expand if tracking sampling deviations or cash reserves fluctuate during market rallies.",
            "severity": "ELEVATED" if te > 0.15 else "CONTAINED"
        }
    ]

    # Forensic audit takeaways
    forensic_notes = []
    if abs(pd) >= 0.5:
        note_type = "WARNING" if pd > 0.5 else "OPPORTUNITY"
        forensic_notes.append({
            "type": note_type,
            "title": f"Secondary Market Mispricing ({pd:+.2f}%)",
            "desc": f"Exchange CMP of ₹{lp:.2f} deviates from Fair NAV ₹{nav:.2f} by {pd:+.2f}%. "
                    f"{'Authorized Participants likely to arbitrage via creation basket.' if pd > 0.5 else 'Redemption basket pressure or attractive retail entry point.'}"
        })

    if te > 0.15:
        forensic_notes.append({
            "type": "CAUTION",
            "title": f"Elevated Tracking Error ({te:.2f}%)",
            "desc": f"1-year annualized tracking error is {te:.2f}%, indicating cash drag, dividend reinvestment lag, or index sampling friction."
        })
    else:
        forensic_notes.append({
            "type": "STRENGTH",
            "title": f"Institutional Benchmark Tracking ({te:.2f}%)",
            "desc": f"Exemplary replication fidelity with 1Y tracking error of {te:.2f}% vs underlying {item.get('underlying_index')}."
        })

    if ter > 0.30:
        forensic_notes.append({
            "type": "NOTE",
            "title": f"Expense Ratio Fee Drag ({ter:.2f}%)",
            "desc": f"Total expense ratio of {ter:.2f}% is above the institutional passive average for this category."
        })

    return {
        "etf": item,
        "amc_issuer": _extract_amc_name(item.get("scheme_name", "")),
        "category_label": category_label,
        "aum_formatted": _format_aum(aum),
        "arbitrage_analysis": arbitrage_analysis,
        "replication_audit": replication_audit,
        "liquidity_audit": liquidity_audit,
        "inversion_risks": inversion_risks,
        "peers": peer_comparisons,
        "forensic_notes": forensic_notes
    }
