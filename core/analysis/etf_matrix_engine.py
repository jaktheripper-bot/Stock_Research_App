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


def get_etf_detail(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves deep forensic details for a single ETF, including underlying index,
    peer benchmarks in same category, tracking error audit, and arbitrage spread.
    """
    if not symbol:
        return None

    item = get_etf_by_symbol(symbol)
    if not item:
        return None

    category = item.get("category", "EQUITY_INDEX")
    peers = get_etf_matrix(category=category, sort_by="aum_desc", limit=6)
    # Remove self from peers
    peer_comparisons = [p for p in peers if p["symbol"].upper() != symbol.strip().upper()][:5]

    pd = item.get("premium_discount_pct", 0.0)
    lp = item.get("last_price", 0.0)
    nav = item.get("nav", 0.0)
    te = item.get("tracking_error_1y", 0.05)
    ter = item.get("expense_ratio_pct", 0.10)

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
        "aum_formatted": _format_aum(item.get("aum_crores", 0.0)),
        "peers": peer_comparisons,
        "forensic_notes": forensic_notes
    }
