"""Omni-Product Search Engine across Indian Equities, Mutual Funds, and Corporate Debt.

Enables unified discovery across:
1. Public Listed Stocks (BSE/NSE tickers, company names)
2. Mutual Fund Schemes (AMFI schemes, fund houses, categories, direct/regular plans)
3. Listed Debt Securities & Debentures (ISINs, issuer corporates, credit ratings)
"""

import logging
from typing import Dict, List, Optional, Any

from core.db.connection import get_db_connection, get_placeholder, init_db
from core.db.mutual_funds import get_active_mutual_funds
from core.db.debt import get_active_debt_securities
from core.ingestion.amfi import search_amfi_master_directory

logger = logging.getLogger(__name__)

# Canonical Stock Master for instant symbol discovery
CANONICAL_INDIAN_STOCKS = [
    {"ticker": "RELIANCE", "name": "Reliance Industries Ltd", "sector": "Energy & Conglomerate", "cap": "Large Cap"},
    {"ticker": "TCS", "name": "Tata Consultancy Services Ltd", "sector": "IT Services", "cap": "Large Cap"},
    {"ticker": "HDFCBANK", "name": "HDFC Bank Ltd", "sector": "Private Banking", "cap": "Large Cap"},
    {"ticker": "ICICIBANK", "name": "ICICI Bank Ltd", "sector": "Private Banking", "cap": "Large Cap"},
    {"ticker": "INFY", "name": "Infosys Ltd", "sector": "IT Services", "cap": "Large Cap"},
    {"ticker": "ITC", "name": "ITC Ltd", "sector": "FMCG", "cap": "Large Cap"},
    {"ticker": "LT", "name": "Larsen & Toubro Ltd", "sector": "Infrastructure & Capital Goods", "cap": "Large Cap"},
    {"ticker": "BHARTIARTL", "name": "Bharti Airtel Ltd", "sector": "Telecom", "cap": "Large Cap"},
    {"ticker": "SBIN", "name": "State Bank of India", "sector": "Public Banking", "cap": "Large Cap"},
    {"ticker": "BAJFINANCE", "name": "Bajaj Finance Ltd", "sector": "NBFC", "cap": "Large Cap"},
    {"ticker": "KOTAKBANK", "name": "Kotak Mahindra Bank Ltd", "sector": "Private Banking", "cap": "Large Cap"},
    {"ticker": "HINDUNILVR", "name": "Hindustan Unilever Ltd", "sector": "FMCG", "cap": "Large Cap"},
    {"ticker": "MARUTI", "name": "Maruti Suzuki India Ltd", "sector": "Automobile", "cap": "Large Cap"},
    {"ticker": "TATAMOTORS", "name": "Tata Motors Ltd", "sector": "Automobile", "cap": "Large Cap"},
    {"ticker": "SUNPHARMA", "name": "Sun Pharmaceutical Industries", "sector": "Pharma", "cap": "Large Cap"},
    {"ticker": "NTPC", "name": "NTPC Ltd", "sector": "Power Generation", "cap": "Large Cap"},
    {"ticker": "TITAN", "name": "Titan Company Ltd", "sector": "Consumer Goods", "cap": "Large Cap"},
    {"ticker": "AXISBANK", "name": "Axis Bank Ltd", "sector": "Private Banking", "cap": "Large Cap"},
    {"ticker": "ASIANPAINT", "name": "Asian Paints Ltd", "sector": "Paints & Chemicals", "cap": "Large Cap"},
    {"ticker": "POWERGRID", "name": "Power Grid Corporation of India", "sector": "Utilities", "cap": "Large Cap"},
    {"ticker": "HCLTECH", "name": "HCL Technologies Ltd", "sector": "IT Services", "cap": "Large Cap"},
    {"ticker": "TATACOMM", "name": "Tata Communications Ltd", "sector": "Telecom Services", "cap": "Mid Cap"},
    {"ticker": "BHARATFORG", "name": "Bharat Forge Ltd", "sector": "Auto Ancillary", "cap": "Mid Cap"},
    {"ticker": "MAXHEALTH", "name": "Max Healthcare Institute", "sector": "Healthcare", "cap": "Mid Cap"},
    {"ticker": "COFORGE", "name": "Coforge Ltd", "sector": "IT Services", "cap": "Mid Cap"},
    {"ticker": "FEDERALBNK", "name": "Federal Bank Ltd", "sector": "Private Banking", "cap": "Mid Cap"},
    {"ticker": "ASTRAL", "name": "Astral Ltd", "sector": "Building Materials", "cap": "Mid Cap"},
    {"ticker": "SUPRAJIT", "name": "Suprajit Engineering Ltd", "sector": "Auto Components", "cap": "Small Cap"},
    {"ticker": "PRINCEPIPE", "name": "Prince Pipes and Fittings", "sector": "Building Products", "cap": "Small Cap"},
    {"ticker": "WENDT", "name": "Wendt India Ltd", "sector": "Industrial Machinery", "cap": "Small Cap"},
    {"ticker": "ELECON", "name": "Elecon Engineering Company", "sector": "Industrial Engineering", "cap": "Small Cap"},
    {"ticker": "NEULANDLAB", "name": "Neuland Laboratories Ltd", "sector": "Pharmaceuticals", "cap": "Small Cap"}
]


def search_equities(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Searches equities by ticker symbol and company name."""
    clean_q = query.strip().upper()
    clean_q_lower = query.strip().lower()
    matches = []

    # 1. Match against canonical master
    for stock in CANONICAL_INDIAN_STOCKS:
        if clean_q == stock["ticker"] or clean_q in stock["ticker"] or clean_q_lower in stock["name"].lower():
            matches.append({
                "product_type": "EQUITY",
                "identifier": stock["ticker"],
                "title": stock["name"],
                "subtitle": f"{stock['ticker']} • {stock['cap']} • {stock['sector']}",
                "url": f"/dossier/{stock['ticker']}",
                "badge": "Stock",
                "badge_class": "badge-success",
                "details": {
                    "ticker": stock["ticker"],
                    "sector": stock["sector"],
                    "cap": stock["cap"]
                }
            })
            if len(matches) >= limit:
                return matches

    # 2. Match against existing reports database
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()
        cursor.execute(
            f"""
            SELECT ticker, short_name, baseline_price, baseline_pe
            FROM reports
            WHERE ticker LIKE {p} OR short_name LIKE {p}
            LIMIT {limit};
            """,
            (f"%{clean_q}%", f"%{clean_q_lower}%")
        )
        rows = cursor.fetchall()
        seen = {m["identifier"] for m in matches}
        for r in rows:
            t = r[0]
            if t not in seen:
                name = r[1] or t
                matches.append({
                    "product_type": "EQUITY",
                    "identifier": t,
                    "title": name,
                    "subtitle": f"{t} • Institutional Equity Dossier",
                    "url": f"/dossier/{t}",
                    "badge": "Stock",
                    "badge_class": "badge-success",
                    "details": {
                        "ticker": t,
                        "price": f"₹{r[2]:,.2f}" if r[2] else "N/A",
                        "pe": f"{r[3]:.1f}x" if r[3] else "N/A"
                    }
                })
                seen.add(t)
                if len(matches) >= limit:
                    break
        cursor.close()
        conn.close()
    except Exception as e:
        logger.debug(f"Reports search notice: {e}")

    return matches[:limit]


def search_mutual_funds(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Searches mutual funds by scheme name, code, fund house, or category."""
    clean_q = query.strip().lower()
    matches = []

    # 1. Search local mutual_fund_schemes table
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()
        cursor.execute(
            f"""
            SELECT scheme_code, scheme_name, fund_house, category, nav, aum_crores, broad_category
            FROM mutual_fund_schemes
            WHERE LOWER(scheme_name) LIKE {p}
               OR LOWER(scheme_code) LIKE {p}
               OR LOWER(fund_house) LIKE {p}
               OR LOWER(category) LIKE {p}
            LIMIT {limit};
            """,
            (f"%{clean_q}%", f"%{clean_q}%", f"%{clean_q}%", f"%{clean_q}%")
        )
        rows = cursor.fetchall()
        for r in rows:
            nav_val = float(r[4] or 0.0)
            aum_val = float(r[5] or 0.0)
            matches.append({
                "product_type": "MUTUAL_FUND",
                "identifier": r[0],
                "title": r[1],
                "subtitle": f"{r[2]} • {r[3]}",
                "url": f"/funds/{r[0]}",
                "badge": "Mutual Fund",
                "badge_class": "badge-cyan",
                "details": {
                    "scheme_code": r[0],
                    "nav": f"₹{nav_val:,.2f}" if nav_val > 0 else "N/A",
                    "category": r[3],
                    "aum": f"₹{aum_val:,.0f} Cr" if aum_val > 0 else "N/A"
                }
            })
        cursor.close()
        conn.close()
    except Exception as e:
        logger.debug(f"Local mutual funds search notice: {e}")

    # 2. If fewer than 3 local matches, dynamically search the master AMFI directory
    if len(matches) < 3:
        try:
            amfi_matches = search_amfi_master_directory(query, limit=(limit - len(matches)), direct_growth_only=True)
            existing_codes = {m["identifier"] for m in matches}
            for s in amfi_matches:
                code = s["scheme_code"]
                if code not in existing_codes:
                    matches.append({
                        "product_type": "MUTUAL_FUND",
                        "identifier": code,
                        "title": s["scheme_name"],
                        "subtitle": f"{s.get('fund_house')} • {s.get('category')}",
                        "url": f"/funds/{code}",
                        "badge": "Mutual Fund",
                        "badge_class": "badge-cyan",
                        "details": {
                            "scheme_code": code,
                            "nav": f"₹{s.get('nav', 0.0):,.2f}",
                            "category": s.get("category"),
                            "aum": "Active AMFI Scheme"
                        }
                    })
                    existing_codes.add(code)
                    if len(matches) >= limit:
                        break
        except Exception as e:
            logger.debug(f"AMFI directory search notice: {e}")

    return matches[:limit]


def search_debt_securities(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Searches corporate debt, NCDs, and bonds by ISIN, issuer name, or rating."""
    clean_q = query.strip().lower()
    matches = []

    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()
        cursor.execute(
            f"""
            SELECT isin, issuer_name, instrument_type, credit_rating, coupon_rate_pct, ytm_pct, face_value_inr
            FROM debt_securities
            WHERE LOWER(issuer_name) LIKE {p}
               OR LOWER(isin) LIKE {p}
               OR LOWER(credit_rating) LIKE {p}
               OR LOWER(instrument_type) LIKE {p}
            LIMIT {limit};
            """,
            (f"%{clean_q}%", f"%{clean_q}%", f"%{clean_q}%", f"%{clean_q}%")
        )
        rows = cursor.fetchall()
        for r in rows:
            matches.append({
                "product_type": "DEBT",
                "identifier": r[0],
                "title": f"{r[1]} {r[4]}% {r[2]}",
                "subtitle": f"{r[0]} • Rating: {r[3]} • YTM: {r[5]}%",
                "url": f"/debt/{r[0]}",
                "badge": "Corporate Debt",
                "badge_class": "badge-warning",
                "details": {
                    "isin": r[0],
                    "issuer": r[1],
                    "credit_rating": r[3],
                    "coupon": f"{r[4]}%",
                    "ytm": f"{r[5]}%"
                }
            })
        cursor.close()
        conn.close()
    except Exception as e:
        logger.debug(f"Debt securities search notice: {e}")

    return matches[:limit]


def search_investment_products(
    query: str,
    product_type: str = "ALL",
    limit_per_category: int = 6
) -> Dict[str, Any]:
    """
    Master omni-search function querying across Equities, Mutual Funds, and Corporate Debt.
    Returns grouped matches and flat combined ranking.
    """
    clean_q = query.strip()
    if not clean_q:
        return {"query": "", "total_matches": 0, "results": [], "categories": {}}

    type_filter = product_type.upper()
    equities = []
    funds = []
    debt = []

    if type_filter in ("ALL", "EQUITY", "STOCK"):
        equities = search_equities(clean_q, limit=limit_per_category)

    if type_filter in ("ALL", "MUTUAL_FUND", "FUND", "MF"):
        funds = search_mutual_funds(clean_q, limit=limit_per_category)

    if type_filter in ("ALL", "DEBT", "BOND", "NCD"):
        debt = search_debt_securities(clean_q, limit=limit_per_category)

    # Interleave results for flat representation
    combined = []
    max_len = max(len(equities), len(funds), len(debt))
    for i in range(max_len):
        if i < len(equities):
            combined.append(equities[i])
        if i < len(funds):
            combined.append(funds[i])
        if i < len(debt):
            combined.append(debt[i])

    return {
        "query": clean_q,
        "total_matches": len(equities) + len(funds) + len(debt),
        "results": combined,
        "categories": {
            "equities": equities,
            "mutual_funds": funds,
            "corporate_debt": debt
        }
    }


def search_all_products(
    query: str,
    asset_class: str = "all",
    limit: int = 30
) -> List[Dict[str, Any]]:
    """Convenience flat search returning a list of product dictionaries."""
    res = search_investment_products(query, product_type=asset_class, limit_per_category=max(10, limit))
    items = res.get("results", [])[:limit]
    for it in items:
        if "asset_class" not in it:
            it["asset_class"] = it.get("product_type", "EQUITY")
    return items
