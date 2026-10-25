"""Omni-Product Search Engine across all 7 Indian Capital-Market Asset Classes.

Enables unified discovery across:
1. Public Listed Equities (BSE/NSE tickers, company names, 6-digit scrip codes)
2. Mutual Fund Schemes (AMFI schemes, fund houses, categories, Direct plans)
3. Exchange-Traded Funds / ETFs (symbol, underlying index, ISIN, iNAV parity)
4. Listed Corporate Debt, NCDs & SDIs (ISINs, issuer corporates, credit ratings)
5. REITs, SM REITs, InvITs & Sovereign Gold Bonds (NDCF purity, WALE, SGB series)
6. Sovereign Yield Curve, T-Bills, Green Bonds & State Development Loans (RBI cutoffs)
7. Unlisted MSMEs & Emerging SMEs (Udyam UIN, industrial clusters, turnover tiers)
"""

import logging
from typing import Any, Dict, List, Optional

from bse_master import (
    PRIMARY_BSE_MAP,
    get_bse_scrips_cache,
    is_synthetic_test_symbol,
    resolve_canonical_symbol,
)
from core.db.connection import get_db_connection, get_placeholder, init_db
from core.db.debt import get_active_debt_securities
from core.db.reits import get_all_reits_and_invits, get_all_sgb_tranches
from core.db.sovereign import (
    get_etf_matrix,
    get_sovereign_sdl_matrix,
    get_sovereign_yield_curve,
)
from core.ingestion.amfi import search_amfi_master_directory
from core.msme.seed import CANONICAL_MSME_FIRMS
from core.presentation.formatters import format_pe_multiple

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
    {"ticker": "NEULANDLAB", "name": "Neuland Laboratories Ltd", "sector": "Pharmaceuticals", "cap": "Small Cap"},
]

CATEGORY_ORDER = (
    "equities",
    "mutual_funds",
    "etfs",
    "corporate_debt",
    "reits_invits",
    "sovereign",
    "msmes",
)


def empty_search_categories() -> Dict[str, List[Dict[str, Any]]]:
    """Returns a fresh 7-category dictionary with empty result lists."""
    return {key: [] for key in CATEGORY_ORDER}


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None or isinstance(val, bool):
            return default
        return float(val)
    except (TypeError, ValueError) as e:
        logger.warning("Float coercion fallback for %r: %s", val, e)
        return default


def search_equities(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Searches listed Indian equities across canonical index stocks, reports, cached fundamentals, and BSE master."""
    clean_q = (query or "").strip().upper()
    clean_q_lower = (query or "").strip().lower()
    if not clean_q:
        return []

    safe_limit = max(1, min(int(limit or 10), 100))
    matches: List[Dict[str, Any]] = []
    seen: set = set()

    # 1. Match against canonical master
    for stock in CANONICAL_INDIAN_STOCKS:
        ticker = stock["ticker"]
        if clean_q == ticker or clean_q in ticker or clean_q_lower in stock["name"].lower() or clean_q_lower in stock["sector"].lower():
            matches.append({
                "product_type": "EQUITY",
                "data_asset_class": "equities",
                "identifier": ticker,
                "title": stock["name"],
                "subtitle": f"{ticker} • {stock['cap']} • {stock['sector']}",
                "url": f"/dossier/{ticker}",
                "badge": "Stock",
                "badge_class": "badge-success",
                "details": {
                    "ticker": ticker,
                    "sector": stock["sector"],
                    "cap": stock["cap"],
                },
            })
            seen.add(ticker)
            if len(matches) >= safe_limit:
                return matches

    # 2. Match against existing reports + cached_fundamentals in database
    conn = None
    cursor = None
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()

        cursor.execute(
            f"""
            SELECT r.ticker, r.short_name, r.baseline_price, r.baseline_pe,
                   cf.current_price, cf.pe_ratio, cf.sector
            FROM reports r
            LEFT JOIN cached_fundamentals cf ON cf.ticker = r.ticker
            WHERE (UPPER(r.ticker) LIKE {p}
                   OR LOWER(COALESCE(r.short_name, '')) LIKE {p}
                   OR LOWER(COALESCE(cf.sector, '')) LIKE {p})
              AND r.ticker NOT LIKE {p}
              AND r.ticker NOT LIKE {p}
              AND r.ticker NOT LIKE {p}
            LIMIT {p};
            """,
            (f"%{clean_q}%", f"%{clean_q_lower}%", f"%{clean_q_lower}%", "TEST_%", "UNIT_%", "ZZTEST%", safe_limit),
        )
        rows = cursor.fetchall()
        for r in rows:
            t = str(r[0] or "").strip().upper()
            if not t or t in seen or is_synthetic_test_symbol(t):
                continue
            name = r[1] or t
            live_price = _safe_float(r[4], 0.0) or _safe_float(r[2], 0.0)
            raw_pe = r[5] if r[5] is not None else r[3]
            pe_meta = format_pe_multiple(raw_pe)
            sector_label = str(r[6] or "").strip() or "Equity Dossier"
            price_str = f"₹{live_price:,.2f}" if live_price > 0 else "—"
            pe_display = pe_meta["display"]
            subtitle_parts = [t, sector_label]
            if price_str != "—":
                subtitle_parts.append(price_str)
            if pe_display != "—":
                subtitle_parts.append(f"P/E: {pe_display}")

            matches.append({
                "product_type": "EQUITY",
                "data_asset_class": "equities",
                "identifier": t,
                "title": name,
                "subtitle": " • ".join(subtitle_parts),
                "url": f"/dossier/{t}",
                "badge": "Stock",
                "badge_class": "badge-success",
                "details": {
                    "ticker": t,
                    "sector": sector_label,
                    "price": price_str,
                    "pe": pe_display,
                },
            })
            seen.add(t)
            if len(matches) >= safe_limit:
                return matches[:safe_limit]

        # 3. Also check cached_fundamentals for stocks not yet synthesized in reports
        if len(matches) < safe_limit:
            rem = safe_limit - len(matches)
            cursor.execute(
                f"""
                SELECT ticker, sector, industry, current_price, pe_ratio
                FROM cached_fundamentals
                WHERE (UPPER(ticker) LIKE {p}
                       OR LOWER(COALESCE(sector, '')) LIKE {p}
                       OR LOWER(COALESCE(industry, '')) LIKE {p})
                  AND ticker NOT LIKE {p}
                  AND ticker NOT LIKE {p}
                  AND ticker NOT LIKE {p}
                LIMIT {p};
                """,
                (f"%{clean_q}%", f"%{clean_q_lower}%", f"%{clean_q_lower}%", "TEST_%", "UNIT_%", "ZZTEST%", rem + 10),
            )
            cf_rows = cursor.fetchall()
            for r in cf_rows:
                t = str(r[0] or "").strip().upper()
                if not t or t in seen or is_synthetic_test_symbol(t):
                    continue
                sector_label = str(r[1] or r[2] or "BSE/NSE Equity").strip()
                price_num = _safe_float(r[3], 0.0)
                pe_meta = format_pe_multiple(r[4])
                price_str = f"₹{price_num:,.2f}" if price_num > 0 else "—"
                subtitle_parts = [t, sector_label]
                if price_str != "—":
                    subtitle_parts.append(price_str)
                if pe_meta["display"] != "—":
                    subtitle_parts.append(f"P/E: {pe_meta['display']}")
                matches.append({
                    "product_type": "EQUITY",
                    "data_asset_class": "equities",
                    "identifier": t,
                    "title": t,
                    "subtitle": " • ".join(subtitle_parts),
                    "url": f"/dossier/{t}",
                    "badge": "Stock",
                    "badge_class": "badge-success",
                    "details": {
                        "ticker": t,
                        "sector": sector_label,
                        "price": price_str,
                        "pe": pe_meta["display"],
                    },
                })
                seen.add(t)
                if len(matches) >= safe_limit:
                    return matches[:safe_limit]
    except Exception as e:
        logger.warning(f"Database equities search warning: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                logger.warning(f"Cursor close warning in search_equities: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Connection close warning in search_equities: {e}")

    # 4. BSE Active Scrip Master & Alias Map fallback (resolves 6-digit scrip codes & broader listed companies)
    if len(matches) < safe_limit:
        try:
            # 6-digit direct BSE scrip code check (e.g. 532540 -> TCS)
            if clean_q.isdigit() and len(clean_q) == 6:
                canon_sym = resolve_canonical_symbol(clean_q)
                if canon_sym and canon_sym not in seen and not is_synthetic_test_symbol(canon_sym):
                    matches.append({
                        "product_type": "EQUITY",
                        "data_asset_class": "equities",
                        "identifier": canon_sym,
                        "title": f"{canon_sym} (BSE: {clean_q})",
                        "subtitle": f"{canon_sym} • BSE Scrip {clean_q} • Listed Equity",
                        "url": f"/dossier/{canon_sym}",
                        "badge": "Stock",
                        "badge_class": "badge-success",
                        "details": {"ticker": canon_sym, "scrip_code": clean_q, "price": "—", "pe": "—"},
                    })
                    seen.add(canon_sym)

            # Alias & PRIMARY_BSE_MAP check (e.g. ZOMATO, DMART, NYKAA, PAYTM, JIOFIN)
            for alias_key, scrip_code in PRIMARY_BSE_MAP.items():
                if len(matches) >= safe_limit:
                    break
                if clean_q in alias_key or scrip_code == clean_q:
                    canon_sym = resolve_canonical_symbol(alias_key) or alias_key.replace(" ", "")
                    if canon_sym and canon_sym not in seen and not is_synthetic_test_symbol(canon_sym):
                        matches.append({
                            "product_type": "EQUITY",
                            "data_asset_class": "equities",
                            "identifier": canon_sym,
                            "title": alias_key.title() if " " in alias_key else canon_sym,
                            "subtitle": f"{canon_sym} • BSE: {scrip_code} • Listed Equity",
                            "url": f"/dossier/{canon_sym}",
                            "badge": "Stock",
                            "badge_class": "badge-success",
                            "details": {"ticker": canon_sym, "scrip_code": scrip_code, "price": "—", "pe": "—"},
                        })
                        seen.add(canon_sym)

            # Cached BSE scrip universe check (symbols + company names)
            if len(matches) < safe_limit:
                bse_cache = get_bse_scrips_cache() or {}
                symbols_map = bse_cache.get("symbols") or {}
                names_map = bse_cache.get("names") or {}
                code_to_sym = {str(v).strip(): str(k).strip().upper() for k, v in symbols_map.items() if k and v}

                for sym_raw, code_raw in symbols_map.items():
                    if len(matches) >= safe_limit:
                        break
                    sym = str(sym_raw).strip().upper()
                    code_str = str(code_raw).strip()
                    if (clean_q in sym or clean_q == code_str) and sym not in seen and not is_synthetic_test_symbol(sym):
                        matches.append({
                            "product_type": "EQUITY",
                            "data_asset_class": "equities",
                            "identifier": sym,
                            "title": sym,
                            "subtitle": f"{sym} • BSE: {code_str} • Listed Equity",
                            "url": f"/dossier/{sym}",
                            "badge": "Stock",
                            "badge_class": "badge-success",
                            "details": {"ticker": sym, "scrip_code": code_str, "price": "—", "pe": "—"},
                        })
                        seen.add(sym)

                if len(matches) < safe_limit and len(clean_q_lower) >= 3:
                    for comp_name, code_raw in names_map.items():
                        if len(matches) >= safe_limit:
                            break
                        if clean_q_lower in str(comp_name).lower():
                            code_str = str(code_raw).strip()
                            sym = code_to_sym.get(code_str) or code_str
                            if sym not in seen and not is_synthetic_test_symbol(sym):
                                matches.append({
                                    "product_type": "EQUITY",
                                    "data_asset_class": "equities",
                                    "identifier": sym,
                                    "title": str(comp_name).strip(),
                                    "subtitle": f"{sym} • BSE: {code_str} • Listed Equity",
                                    "url": f"/dossier/{sym}",
                                    "badge": "Stock",
                                    "badge_class": "badge-success",
                                    "details": {"ticker": sym, "scrip_code": code_str, "price": "—", "pe": "—"},
                                })
                                seen.add(sym)
        except Exception as e:
            logger.warning(f"BSE scrip master search fallback warning: {e}")

    return matches[:safe_limit]


def search_mutual_funds(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Searches mutual funds by scheme name, code, fund house, or category."""
    clean_q = (query or "").strip().lower()
    if not clean_q:
        return []

    safe_limit = max(1, min(int(limit or 10), 100))
    matches: List[Dict[str, Any]] = []

    # 1. Search local mutual_fund_schemes table
    conn = None
    cursor = None
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
            LIMIT {p};
            """,
            (f"%{clean_q}%", f"%{clean_q}%", f"%{clean_q}%", f"%{clean_q}%", safe_limit),
        )
        rows = cursor.fetchall()
        for r in rows:
            nav_val = _safe_float(r[4], 0.0)
            aum_val = _safe_float(r[5], 0.0)
            matches.append({
                "product_type": "MUTUAL_FUND",
                "data_asset_class": "funds",
                "identifier": str(r[0]),
                "title": r[1],
                "subtitle": f"{r[2]} • {r[3]}",
                "url": f"/funds/{r[0]}",
                "badge": "Mutual Fund",
                "badge_class": "badge-cyan",
                "details": {
                    "scheme_code": str(r[0]),
                    "nav": f"₹{nav_val:,.2f}" if nav_val > 0 else "—",
                    "category": r[3],
                    "aum": f"₹{aum_val:,.0f} Cr" if aum_val > 0 else "—",
                },
            })
    except Exception as e:
        logger.warning(f"Local mutual funds search warning: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                logger.warning(f"Cursor close warning in search_mutual_funds: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Connection close warning in search_mutual_funds: {e}")

    # 2. If fewer than 3 local matches, dynamically search the master AMFI directory
    if len(matches) < 3 and len(matches) < safe_limit:
        try:
            amfi_matches = search_amfi_master_directory(
                query,
                limit=(safe_limit - len(matches)),
                direct_growth_only=True,
            )
            existing_codes = {m["identifier"] for m in matches}
            for s in amfi_matches:
                code = str(s["scheme_code"])
                if code not in existing_codes:
                    nav_num = _safe_float(s.get("nav"), 0.0)
                    matches.append({
                        "product_type": "MUTUAL_FUND",
                        "data_asset_class": "funds",
                        "identifier": code,
                        "title": s["scheme_name"],
                        "subtitle": f"{s.get('fund_house') or 'AMFI'} • {s.get('category') or 'Direct Growth'}",
                        "url": f"/funds/{code}",
                        "badge": "Mutual Fund",
                        "badge_class": "badge-cyan",
                        "details": {
                            "scheme_code": code,
                            "nav": f"₹{nav_num:,.2f}" if nav_num > 0 else "—",
                            "category": s.get("category") or "Direct Growth",
                            "aum": "Active AMFI Scheme",
                        },
                    })
                    existing_codes.add(code)
                    if len(matches) >= safe_limit:
                        break
        except Exception as e:
            logger.warning(f"AMFI directory search warning: {e}")

    return matches[:safe_limit]


def search_etfs(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Searches NSE/BSE Exchange-Traded Funds by symbol, scheme name, underlying index, category, or ISIN."""
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    safe_limit = max(1, min(int(limit or 10), 100))
    q_upper = clean_q.upper()
    q_lower = clean_q.lower()
    matches: List[Dict[str, Any]] = []
    seen: set = set()

    try:
        init_db()
        # Broad keyword triggers ("ETF", "BEES", "INAV") return top AUM ETFs
        broad_etf_query = q_upper in ("ETF", "ETFS", "BEES", "INAV", "INDEX ETF")
        candidates = (
            get_etf_matrix(limit=safe_limit)
            if broad_etf_query
            else get_etf_matrix(query=clean_q, limit=safe_limit)
        )

        # Also check ISIN, category, and underlying index across the full matrix if needed
        if len(candidates) < safe_limit and not broad_etf_query:
            full_pool = get_etf_matrix(limit=100)
            existing_syms = {str(c.get("symbol", "")).upper() for c in candidates}
            for item in full_pool:
                sym = str(item.get("symbol", "")).upper()
                if sym in existing_syms:
                    continue
                haystack = " ".join([
                    sym,
                    str(item.get("scheme_name", "")),
                    str(item.get("underlying_index", "")),
                    str(item.get("category", "")),
                    str(item.get("isin", "")),
                ]).lower()
                if q_lower in haystack:
                    candidates.append(item)
                    existing_syms.add(sym)
                    if len(candidates) >= safe_limit:
                        break

        for etf in candidates:
            sym = str(etf.get("symbol") or "").strip().upper()
            if not sym or sym in seen or is_synthetic_test_symbol(sym):
                continue
            last_price = _safe_float(etf.get("last_price"), 0.0)
            prem = _safe_float(etf.get("premium_discount_pct"), 0.0)
            ter = _safe_float(etf.get("expense_ratio_pct"), 0.0)
            te = _safe_float(etf.get("tracking_error_1y"), 0.0)
            idx_name = str(etf.get("underlying_index") or etf.get("category") or "Index ETF")
            price_str = f"₹{last_price:,.2f}" if last_price > 0 else "—"

            matches.append({
                "product_type": "ETF",
                "data_asset_class": "etfs",
                "identifier": sym,
                "title": etf.get("scheme_name") or sym,
                "subtitle": f"{sym} • {idx_name} • iNAV Δ: {prem:+.2f}% • TER: {ter:.2f}%",
                "url": f"/etfs/{sym}",
                "badge": "ETF",
                "badge_class": "badge-cyan",
                "details": {
                    "symbol": sym,
                    "isin": etf.get("isin") or "—",
                    "price": price_str,
                    "premium_discount": f"{prem:+.2f}%",
                    "tracking_error": f"{te:.2f}%",
                    "ter": f"{ter:.2f}%",
                    "category": etf.get("category") or "EQUITY",
                },
            })
            seen.add(sym)
            if len(matches) >= safe_limit:
                break
    except Exception as e:
        logger.warning(f"ETF matrix search warning: {e}")

    return matches[:safe_limit]


def search_debt_securities(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Searches corporate debt, NCDs, and SDIs by ISIN, ticker, instrument name, or credit rating."""
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    clean_q_lower = clean_q.lower()
    safe_limit = max(1, min(int(limit or 10), 100))
    matches: List[Dict[str, Any]] = []
    seen: set = set()

    conn = None
    cursor = None
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()
        cursor.execute(
            f"""
            SELECT isin, ticker, instrument_name, instrument_type, credit_rating, coupon_rate_pct, ytm_pct, face_value
            FROM corporate_debt_securities
            WHERE (LOWER(COALESCE(ticker, '')) LIKE {p}
                   OR LOWER(COALESCE(instrument_name, '')) LIKE {p}
                   OR LOWER(COALESCE(isin, '')) LIKE {p}
                   OR LOWER(COALESCE(credit_rating, '')) LIKE {p}
                   OR LOWER(COALESCE(instrument_type, '')) LIKE {p})
              AND UPPER(isin) NOT LIKE {p}
            ORDER BY ytm_pct DESC
            LIMIT {p};
            """,
            (
                f"%{clean_q_lower}%",
                f"%{clean_q_lower}%",
                f"%{clean_q_lower}%",
                f"%{clean_q_lower}%",
                f"%{clean_q_lower}%",
                "%TEST%",
                safe_limit,
            ),
        )
        rows = cursor.fetchall()
        for r in rows:
            isin_val = str(r[0] or "").strip()
            if not isin_val or isin_val in seen:
                continue
            ticker_val = r[1] or ""
            name_val = r[2] or f"{ticker_val} NCD"
            rating_val = r[4] or "—"
            coupon_val = _safe_float(r[5], 0.0)
            ytm_val = _safe_float(r[6], coupon_val)
            matches.append({
                "product_type": "DEBT",
                "data_asset_class": "debt",
                "identifier": isin_val,
                "title": name_val,
                "subtitle": f"{isin_val} • Rating: {rating_val} • YTM: {ytm_val:.2f}%",
                "url": f"/debt/{isin_val}",
                "badge": "Corporate Debt",
                "badge_class": "badge-warning",
                "details": {
                    "isin": isin_val,
                    "ticker": ticker_val or "—",
                    "issuer": name_val,
                    "credit_rating": rating_val,
                    "coupon": f"{coupon_val:.2f}%",
                    "ytm": f"{ytm_val:.2f}%",
                },
            })
            seen.add(isin_val)
    except Exception as e:
        logger.warning(f"Debt securities SQL search warning: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                logger.warning(f"Cursor close warning in search_debt_securities: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Connection close warning in search_debt_securities: {e}")

    # Fallback / supplement from active debt repository if table was cold or broad keyword used
    if len(matches) < safe_limit:
        try:
            broad_debt = clean_q_lower in ("bond", "bonds", "ncd", "ncds", "sdi", "sdis", "debt", "debenture")
            pool = get_active_debt_securities(limit=60)
            for d in pool:
                if len(matches) >= safe_limit:
                    break
                isin_val = str(d.get("isin") or "").strip()
                if not isin_val or isin_val in seen or "TEST" in isin_val.upper():
                    continue
                haystack = " ".join([
                    isin_val,
                    str(d.get("ticker") or ""),
                    str(d.get("instrument_name") or ""),
                    str(d.get("credit_rating") or ""),
                    str(d.get("instrument_type") or ""),
                    str(d.get("seniority") or ""),
                ]).lower()
                if broad_debt or clean_q_lower in haystack:
                    coupon_val = _safe_float(d.get("coupon_rate_pct"), 0.0)
                    ytm_val = _safe_float(d.get("ytm_pct"), coupon_val)
                    rating_val = str(d.get("credit_rating") or "—")
                    name_val = str(d.get("instrument_name") or f"{d.get('ticker', '')} NCD").strip()
                    matches.append({
                        "product_type": "DEBT",
                        "data_asset_class": "debt",
                        "identifier": isin_val,
                        "title": name_val,
                        "subtitle": f"{isin_val} • Rating: {rating_val} • YTM: {ytm_val:.2f}%",
                        "url": f"/debt/{isin_val}",
                        "badge": "Corporate Debt",
                        "badge_class": "badge-warning",
                        "details": {
                            "isin": isin_val,
                            "ticker": str(d.get("ticker") or "—"),
                            "issuer": name_val,
                            "credit_rating": rating_val,
                            "coupon": f"{coupon_val:.2f}%",
                            "ytm": f"{ytm_val:.2f}%",
                        },
                    })
                    seen.add(isin_val)
        except Exception as e:
            logger.warning(f"Active debt repository fallback warning: {e}")

    return matches[:safe_limit]


def search_reits_and_sgbs(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Searches REITs, SM REITs, InvITs, and Sovereign Gold Bond (SGB) tranches."""
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    q_lower = clean_q.lower()
    safe_limit = max(1, min(int(limit or 10), 100))
    matches: List[Dict[str, Any]] = []
    seen: set = set()

    try:
        init_db()
        broad_reit = q_lower in ("reit", "reits", "sm reit", "sm_reit", "invit", "invits", "real estate", "ndcf")
        reit_items = get_all_reits_and_invits(exclude_tests=True)
        for r in reit_items:
            if len(matches) >= safe_limit:
                break
            sym = str(r.get("symbol") or "").strip().upper()
            if not sym or sym in seen:
                continue
            det = r.get("details") if isinstance(r.get("details"), dict) else {}
            haystack = " ".join([
                sym,
                str(r.get("name") or ""),
                str(r.get("structure_type") or ""),
                str(det.get("sponsor") or ""),
                str(det.get("asset_focus") or ""),
                str(det.get("geography") or ""),
            ]).lower()
            if broad_reit or q_lower in haystack:
                yield_pct = _safe_float(r.get("distribution_yield_pct"), 0.0)
                disc_pct = _safe_float(r.get("discount_to_nav_pct"), 0.0)
                price_num = _safe_float(r.get("current_price"), 0.0)
                struct_label = str(r.get("structure_type") or "REIT").replace("_", " ")
                matches.append({
                    "product_type": "REIT_INVIT",
                    "data_asset_class": "reits",
                    "identifier": sym,
                    "title": r.get("name") or sym,
                    "subtitle": f"{sym} • {struct_label} • Dist. Yield: {yield_pct:.2f}% • NAV Δ: {disc_pct:+.1f}%",
                    "url": f"/reits/{sym}",
                    "badge": struct_label,
                    "badge_class": "badge-cyan",
                    "details": {
                        "symbol": sym,
                        "structure": struct_label,
                        "price": f"₹{price_num:,.2f}" if price_num > 0 else "—",
                        "yield": f"{yield_pct:.2f}%",
                        "nav_discount": f"{disc_pct:+.1f}%",
                    },
                })
                seen.add(sym)

        if len(matches) < safe_limit:
            broad_sgb = q_lower in ("sgb", "sgbs", "gold bond", "sovereign gold", "sovereign gold bond")
            sgb_items = get_all_sgb_tranches()
            for sgb in sgb_items:
                if len(matches) >= safe_limit:
                    break
                sym = str(sgb.get("symbol") or "").strip().upper()
                if not sym or sym in seen or "TEST" in sym:
                    continue
                haystack = f"{sym} {sgb.get('series_name', '')} sgb gold bond".lower()
                if broad_sgb or q_lower in haystack:
                    ytm = _safe_float(sgb.get("ytm_annualized_pct"), 0.0)
                    disc = _safe_float(sgb.get("discount_to_spot_pct"), 0.0)
                    mp = _safe_float(sgb.get("market_price"), 0.0)
                    matches.append({
                        "product_type": "REIT_INVIT",
                        "data_asset_class": "reits",
                        "identifier": sym,
                        "title": sgb.get("series_name") or sym,
                        "subtitle": f"{sym} • SGB Secondary • Spot Δ: {disc:+.2f}% • Est. YTM: {ytm:.2f}%",
                        "url": "/reits#sgbCardsGrid",
                        "badge": "SGB Tranche",
                        "badge_class": "badge-warning",
                        "details": {
                            "symbol": sym,
                            "price": f"₹{mp:,.0f}" if mp > 0 else "—",
                            "spot_discount": f"{disc:+.2f}%",
                            "ytm": f"{ytm:.2f}%",
                        },
                    })
                    seen.add(sym)
    except Exception as e:
        logger.warning(f"REITs/InvITs/SGBs search warning: {e}")

    return matches[:safe_limit]


def search_sovereign(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Searches RBI Sovereign G-Secs, T-Bills, Sovereign Green Bonds, and State Development Loans (SDLs)."""
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    q_lower = clean_q.lower()
    safe_limit = max(1, min(int(limit or 10), 100))
    matches: List[Dict[str, Any]] = []
    seen: set = set()

    try:
        init_db()
        broad_sov = q_lower in (
            "gsec", "g-sec", "g-secs", "sovereign", "tbill", "t-bill", "t-bills",
            "treasury", "rbi", "yield curve", "sgrb", "green bond",
        )
        curve = get_sovereign_yield_curve()
        for item in curve:
            if len(matches) >= safe_limit:
                break
            tenor = str(item.get("tenor_label") or "").strip()
            if not tenor or tenor in seen:
                continue
            inst_type = str(item.get("instrument_type") or "G-Sec")
            mat_yrs = _safe_float(item.get("maturity_years"), 0.0)
            cutoff = _safe_float(item.get("cut_off_yield"), 0.0)
            readable_tenor = tenor.replace("_", " ")
            is_sdl_item = inst_type.upper() == "SDL" or "SDL" in tenor.upper()
            haystack = f"{tenor} {readable_tenor} {inst_type} rbi sovereign g-sec gsec t-bill tbill".lower()
            if broad_sov or q_lower in haystack:
                matches.append({
                    "product_type": "SOVEREIGN",
                    "data_asset_class": "sovereign",
                    "identifier": tenor,
                    "title": f"India {readable_tenor} ({inst_type})",
                    "subtitle": f"RBI Auction Cutoff: {cutoff:.2f}% • Tenor: {mat_yrs:g}Y • Sovereign Zero-Default",
                    "url": "/sovereign#sdlCardsGrid" if is_sdl_item else "/sovereign#sovereignTenorCardsGrid",
                    "badge": "State SDL" if is_sdl_item else "Sovereign / RBI",
                    "badge_class": "badge-cyan",
                    "details": {
                        "tenor": tenor,
                        "instrument_type": inst_type,
                        "yield": f"{cutoff:.2f}%",
                        "auction_date": str(item.get("auction_date") or "—"),
                    },
                })
                seen.add(tenor)

        if len(matches) < safe_limit:
            broad_sdl = q_lower in ("sdl", "sdls", "state loan", "state development loan")
            sdls = get_sovereign_sdl_matrix()
            for sdl in sdls:
                if len(matches) >= safe_limit:
                    break
                state_name = str(sdl.get("state_name") or "").strip()
                state_code = str(sdl.get("state_code") or "").strip().upper()
                ident = f"SDL-{state_code}" if state_code else state_name
                if not state_name or ident in seen:
                    continue
                haystack = f"{state_name} {state_code} sdl state development loan {sdl.get('fiscal_tier', '')}".lower()
                if broad_sdl or q_lower in haystack:
                    cutoff = _safe_float(sdl.get("cut_off_yield"), 0.0)
                    spread = _safe_float(sdl.get("spread_over_gsec_bps"), 0.0)
                    tenor_yrs = _safe_float(sdl.get("tenor_years"), 10.0)
                    matches.append({
                        "product_type": "SOVEREIGN",
                        "data_asset_class": "sovereign",
                        "identifier": ident,
                        "title": f"{state_name} {tenor_yrs:g}Y State Development Loan (SDL)",
                        "subtitle": f"{ident} • Cutoff Yield: {cutoff:.2f}% • Spread vs G-Sec: +{spread:.0f} bps",
                        "url": "/sovereign#sdlCardsGrid",
                        "badge": "State SDL",
                        "badge_class": "badge-cyan",
                        "details": {
                            "state": state_name,
                            "yield": f"{cutoff:.2f}%",
                            "spread_bps": f"+{spread:.0f} bps",
                            "fiscal_tier": str(sdl.get("fiscal_tier") or "—"),
                        },
                    })
                    seen.add(ident)
    except Exception as e:
        logger.warning(f"Sovereign yield curve / SDL search warning: {e}")

    return matches[:safe_limit]


def search_msmes(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Searches Unlisted Indian MSMEs & SMEs by Udyam UIN, enterprise name, industrial cluster, or sector."""
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    q_lower = clean_q.lower()
    safe_limit = max(1, min(int(limit or 10), 100))
    matches: List[Dict[str, Any]] = []
    seen: set = set()

    conn = None
    cursor = None
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()
        cursor.execute(
            f"""
            SELECT uin, name, sector_name, city, state, annual_turnover
            FROM msme_firms
            WHERE (LOWER(COALESCE(name, '')) LIKE {p}
                   OR LOWER(COALESCE(uin, '')) LIKE {p}
                   OR LOWER(COALESCE(sector_name, '')) LIKE {p}
                   OR LOWER(COALESCE(city, '')) LIKE {p}
                   OR LOWER(COALESCE(state, '')) LIKE {p})
              AND UPPER(uin) NOT LIKE {p}
            ORDER BY annual_turnover DESC
            LIMIT {p};
            """,
            (
                f"%{q_lower}%",
                f"%{q_lower}%",
                f"%{q_lower}%",
                f"%{q_lower}%",
                f"%{q_lower}%",
                "%TEST%",
                safe_limit,
            ),
        )
        rows = cursor.fetchall()
        for r in rows:
            uin_val = str(r[0] or "").strip()
            if not uin_val or uin_val in seen:
                continue
            name_val = str(r[1] or uin_val)
            sector_val = str(r[2] or "Manufacturing").replace("_", " ").title()
            city_val = str(r[3] or "")
            state_val = str(r[4] or "")
            turnover = _safe_float(r[5], 0.0)
            loc_str = ", ".join([x for x in (city_val, state_val) if x]) or "India"
            turnover_str = f"₹{turnover:,.1f} Cr" if turnover > 0 else "—"
            matches.append({
                "product_type": "MSME",
                "data_asset_class": "msme",
                "identifier": uin_val,
                "title": name_val,
                "subtitle": f"{uin_val} • {sector_val} • {loc_str} • Turnover: {turnover_str}",
                "url": f"/msme/{uin_val}",
                "badge": "Unlisted MSME",
                "badge_class": "badge-warning",
                "details": {
                    "uin": uin_val,
                    "sector": sector_val,
                    "location": loc_str,
                    "turnover": turnover_str,
                },
            })
            seen.add(uin_val)
    except Exception as e:
        logger.warning(f"MSME database search warning: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                logger.warning(f"Cursor close warning in search_msmes: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Connection close warning in search_msmes: {e}")

    # Fallback to canonical Udyam seed registry if msme_firms table is cold or broad keyword used
    if len(matches) < safe_limit:
        try:
            broad_msme = q_lower in ("msme", "msmes", "sme", "smes", "udyam", "unlisted")
            for firm in CANONICAL_MSME_FIRMS:
                if len(matches) >= safe_limit:
                    break
                uin_val = str(firm.get("uin") or "").strip()
                if not uin_val or uin_val in seen:
                    continue
                sector_raw = str(firm.get("sector_name") or "")
                haystack = " ".join([
                    uin_val,
                    str(firm.get("name") or ""),
                    sector_raw,
                    sector_raw.replace("_", " "),
                    str(firm.get("city") or ""),
                    str(firm.get("state") or ""),
                ]).lower()
                if broad_msme or q_lower in haystack:
                    sector_val = sector_raw.replace("_", " ").title() or "Industrial"
                    loc_str = ", ".join([x for x in (firm.get("city"), firm.get("state")) if x]) or "India"
                    turnover = _safe_float(firm.get("annual_turnover"), 0.0)
                    turnover_str = f"₹{turnover:,.1f} Cr" if turnover > 0 else "—"
                    matches.append({
                        "product_type": "MSME",
                        "data_asset_class": "msme",
                        "identifier": uin_val,
                        "title": str(firm.get("name") or uin_val),
                        "subtitle": f"{uin_val} • {sector_val} • {loc_str} • Turnover: {turnover_str}",
                        "url": f"/msme/{uin_val}",
                        "badge": "Unlisted MSME",
                        "badge_class": "badge-warning",
                        "details": {
                            "uin": uin_val,
                            "sector": sector_val,
                            "location": loc_str,
                            "turnover": turnover_str,
                        },
                    })
                    seen.add(uin_val)
        except Exception as e:
            logger.warning(f"Canonical MSME fallback search warning: {e}")

    return matches[:safe_limit]


def search_investment_products(
    query: str,
    product_type: str = "ALL",
    limit_per_category: int = 6,
) -> Dict[str, Any]:
    """
    Master 7-Asset Omni-Search function querying across:
    1. Equities  2. Mutual Funds  3. ETFs  4. Corporate Debt
    5. REITs/InvITs/SGBs  6. Sovereign Curve & SDLs  7. Unlisted MSMEs

    Returns grouped `categories` across all 7 asset classes plus interleaved flat `results`.
    """
    clean_q = (query or "").strip()
    categories = empty_search_categories()
    if not clean_q:
        return {"query": "", "total_matches": 0, "results": [], "categories": categories}

    type_filter = (product_type or "ALL").strip().upper()
    cap_limit = max(1, min(int(limit_per_category or 6), 50))

    if type_filter in ("ALL", "EQUITY", "EQUITIES", "STOCK", "STOCKS"):
        categories["equities"] = search_equities(clean_q, limit=cap_limit)

    if type_filter in ("ALL", "MUTUAL_FUND", "MUTUAL_FUNDS", "FUND", "FUNDS", "MF"):
        categories["mutual_funds"] = search_mutual_funds(clean_q, limit=cap_limit)

    if type_filter in ("ALL", "ETF", "ETFS"):
        categories["etfs"] = search_etfs(clean_q, limit=cap_limit)

    if type_filter in ("ALL", "DEBT", "CORPORATE_DEBT", "BOND", "BONDS", "NCD", "SDI"):
        categories["corporate_debt"] = search_debt_securities(clean_q, limit=cap_limit)

    if type_filter in ("ALL", "REIT", "REITS", "REIT_INVIT", "REITS_INVITS", "INVIT", "SGB"):
        categories["reits_invits"] = search_reits_and_sgbs(clean_q, limit=cap_limit)

    if type_filter in ("ALL", "SOVEREIGN", "GSEC", "G-SEC", "TBILL", "SDL"):
        categories["sovereign"] = search_sovereign(clean_q, limit=cap_limit)

    if type_filter in ("ALL", "MSME", "MSMES", "SME", "UDYAM"):
        categories["msmes"] = search_msmes(clean_q, limit=cap_limit)

    # Interleave results across all 7 asset classes for flat representation
    lists_in_order = [categories[k] for k in CATEGORY_ORDER]
    max_len = max((len(lst) for lst in lists_in_order), default=0)
    combined: List[Dict[str, Any]] = []
    for i in range(max_len):
        for lst in lists_in_order:
            if i < len(lst):
                item = dict(lst[i])
                item.setdefault("asset_class", item.get("product_type", "EQUITY"))
                combined.append(item)

    total_matches = sum(len(lst) for lst in lists_in_order)

    return {
        "query": clean_q,
        "total_matches": total_matches,
        "results": combined,
        "categories": categories,
    }


def search_all_products(
    query: str,
    asset_class: str = "all",
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """Convenience flat search returning a list of product dictionaries across all 7 asset classes."""
    res = search_investment_products(query, product_type=asset_class, limit_per_category=max(8, min(limit, 30)))
    items = res.get("results", [])[:limit]
    for it in items:
        if "asset_class" not in it:
            it["asset_class"] = it.get("product_type", "EQUITY")
    return items
