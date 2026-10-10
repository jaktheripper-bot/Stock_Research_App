"""Localized Fundamentals Cache repository for peer comparison and sub-second metrics resolution."""

import re
import json
import logging
from typing import Optional, Dict, Any
from normalizer import clean_ticker
from core.db.connection import init_db, get_db_connection, get_placeholder

logger = logging.getLogger("equity_research.core.db.fundamentals")


def extract_fundamentals_from_report_text(report_text: str, fallback_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Deterministically extracts verified financial ratios, multiples, and price ranges
    from institutional research report text (7-pillar narrative + health matrix).
    """
    res: Dict[str, Any] = {}
    if fallback_data:
        res.update(fallback_data)

    if not report_text or not isinstance(report_text, str):
        return res

    txt = report_text.replace("\xa0", " ").replace("–", "-").replace("—", "-")

    # 1. ROCE (Return on Capital Employed)
    if res.get("roce") in [None, "N/A", "", 0, 0.0]:
        m_roce = re.search(r'(?:ROCE|Return on Capital Employed)[^\d\n]*?(\d+(?:\.\d+)?)\s*%', txt, re.I)
        if not m_roce:
            m_roce = re.search(r'ROCE\s*(?:of|was|is|reached|stands at|exceeding|above)?\s*\[?[^\]\n]*\]?\s*(\d+(?:\.\d+)?)\s*%', txt, re.I)
        if m_roce:
            try:
                res["roce"] = float(m_roce.group(1))
            except Exception:
                pass

    # 2. ROE (Return on Equity)
    if res.get("roe") in [None, "N/A", "", 0, 0.0]:
        m_roe = re.search(r'(?:ROE|Return on Equity)[^\d\n]*?(\d+(?:\.\d+)?)\s*%', txt, re.I)
        if not m_roe:
            m_roe = re.search(r'ROE\s*(?:of|was|is|reached|stands at|exceeding|above)?\s*\[?[^\]\n]*\]?\s*(\d+(?:\.\d+)?)\s*%', txt, re.I)
        if m_roe:
            try:
                res["roe"] = float(m_roe.group(1))
            except Exception:
                pass

    # 3. Operating Margin (OPM) / EBITDA Margin
    if res.get("operating_margin") in [None, "N/A", "", 0, 0.0]:
        m_opm = re.search(r'(?:Operating\s+Margins?|OPM|EBITDA\s+Margins?)[^\d\n]*?(\d+(?:\.\d+)?)\s*%', txt, re.I)
        if not m_opm:
            m_opm = re.search(r'(?:Operating\s+Margins?|OPM|EBITDA\s+Margins?)\s*(?:remains?|stands?|is|was|between|in the|near)?\s*(?:healthy|steady|firm)?[^\d\n]*?(\d+(?:\.\d+)?)\s*%', txt, re.I)
        if m_opm:
            try:
                res["operating_margin"] = float(m_opm.group(1))
            except Exception:
                pass

    # 4. Debt-to-Equity (D/E)
    if res.get("debt_to_equity") in [None, "N/A", ""]:
        if re.search(r'Balance\s*Sheet\s*:\s*Debt-Free', txt, re.I) or re.search(r'\bdebt-free\b', txt, re.I):
            res["debt_to_equity"] = 0.0
        else:
            m_de = re.search(r'(?:debt[- ]to[- ]equity|d/e)[^\d\n]*?(\d+(?:\.\d+)?)', txt, re.I)
            if m_de:
                try:
                    res["debt_to_equity"] = float(m_de.group(1))
                except Exception:
                    pass

    # 5. 52-Week High & Low
    if res.get("fifty_two_week_high") in [None, "N/A", "", 0, 0.0] or res.get("fifty_two_week_low") in [None, "N/A", "", 0, 0.0]:
        mh = re.search(r'52-week\s+high[^\d\n]*?(?:INR|₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)\s*(?:INR|₹|Rs\.?)?', txt, re.I)
        ml = re.search(r'52-week\s+low[^\d\n]*?(?:INR|₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)\s*(?:INR|₹|Rs\.?)?', txt, re.I)
        if mh and res.get("fifty_two_week_high") in [None, "N/A", "", 0, 0.0]:
            try:
                res["fifty_two_week_high"] = float(mh.group(1).replace(",", "").strip())
            except Exception:
                pass
        if ml and res.get("fifty_two_week_low") in [None, "N/A", "", 0, 0.0]:
            try:
                res["fifty_two_week_low"] = float(ml.group(1).replace(",", "").strip())
            except Exception:
                pass

        # Combined range pattern fallback: "52-week range of 1,000 - 1,500"
        if res.get("fifty_two_week_high") in [None, "N/A", ""] or res.get("fifty_two_week_low") in [None, "N/A", ""]:
            m_comb = re.search(r'52-week\s+(?:range|band)[^\d\n]*?(?:INR|₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)\s*[-–]\s*(?:INR|₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)', txt, re.I)
            if m_comb:
                try:
                    val1 = float(m_comb.group(1).replace(",", "").strip())
                    val2 = float(m_comb.group(2).replace(",", "").strip())
                    res["fifty_two_week_low"] = min(val1, val2)
                    res["fifty_two_week_high"] = max(val1, val2)
                except Exception:
                    pass

    # 6. Price to Book (P/B)
    if res.get("pb_ratio") in [None, "N/A", ""]:
        m_pb = re.search(r'(?:Price[- ]to[- ]Book|P/B|PBV)[^\d\n]*?(\d+(?:\.\d+)?)\s*x?', txt, re.I)
        if m_pb:
            res["pb_ratio"] = f"{float(m_pb.group(1)):.2f}"

    # 7. EV / EBITDA
    if res.get("ev_ebitda") in [None, "N/A", ""]:
        m_eve = re.search(r'(?:EV[ /]EBITDA)[^\d\n]*?(\d+(?:\.\d+)?)\s*x?', txt, re.I)
        if m_eve:
            res["ev_ebitda"] = f"{float(m_eve.group(1)):.2f}"

    # 8. Forward P/E
    if res.get("forward_pe") in [None, "N/A", ""]:
        m_fpe = re.search(r'(?:Forward\s+P/E)[^\d\n]*?(\d+(?:\.\d+)?)', txt, re.I)
        if m_fpe:
            res["forward_pe"] = f"{float(m_fpe.group(1)):.2f}"

    return res


def get_cached_fundamentals(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves fundamentals from the localized database cache.
    If not cached or if key ratios are missing, automatically falls back to
    analyzing the stored research report and discovery reel, caching the result.
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    clean = clean_ticker(ticker)

    result_dict: Dict[str, Any] = {}

    try:
        # 1. Query cached_fundamentals table
        cursor.execute(
            f"SELECT ticker, company_name, sector, industry, current_price, market_cap, "
            f"pe_ratio, forward_pe, pb_ratio, ev_ebitda, roce, roe, operating_margin, "
            f"debt_to_equity, fifty_two_week_high, fifty_two_week_low, source "
            f"FROM cached_fundamentals WHERE ticker = {placeholder};",
            (clean,)
        )
        row = cursor.fetchone()
        if row:
            result_dict = {
                "ticker": row[0],
                "company_name": row[1] or clean,
                "short_name": row[1] or clean,
                "sector": row[2] or "General Industry",
                "industry": row[3] or "Diversified",
                "current_price": float(row[4]) if row[4] is not None else None,
                "market_cap": float(row[5]) if row[5] is not None else None,
                "pe_ratio": row[6] or "N/A",
                "forward_pe": row[7] or "N/A",
                "pb_ratio": row[8] or "N/A",
                "price_to_book": row[8] or "N/A",
                "ev_ebitda": row[9] or "N/A",
                "ev_to_ebitda": row[9] or "N/A",
                "roce": float(row[10]) if row[10] is not None else None,
                "roce_pct": float(row[10]) if row[10] is not None else None,
                "roe": float(row[11]) if row[11] is not None else None,
                "operating_margin": float(row[12]) if row[12] is not None else None,
                "opm": float(row[12]) if row[12] is not None else None,
                "debt_to_equity": float(row[13]) if row[13] is not None else None,
                "fifty_two_week_high": float(row[14]) if row[14] is not None else None,
                "52w_high": float(row[14]) if row[14] is not None else "N/A",
                "fifty_two_week_low": float(row[15]) if row[15] is not None else None,
                "52w_low": float(row[15]) if row[15] is not None else "N/A",
                "source": row[16] or "LOCAL_DB_HARMONIZED"
            }

        # Check if missing key institutional metrics (ROCE, ROE, OPM, 52w range)
        has_essential = (
            result_dict.get("roce") is not None and
            result_dict.get("roe") is not None and
            result_dict.get("fifty_two_week_high") is not None
        )

        if not has_essential:
            # 2. Check discovery_reel for any curated screening metrics
            try:
                cursor.execute(
                    f"SELECT company_name, sector, current_price, pe_ratio, roce_pct, debt_to_equity, key_metrics_json "
                    f"FROM discovery_reel WHERE ticker = {placeholder} ORDER BY id DESC LIMIT 1;",
                    (clean,)
                )
                d_row = cursor.fetchone()
                if d_row:
                    if not result_dict.get("company_name"):
                        result_dict["company_name"] = d_row[0]
                        result_dict["short_name"] = d_row[0]
                    if not result_dict.get("sector") or result_dict.get("sector") == "General Industry":
                        result_dict["sector"] = d_row[1]
                    if result_dict.get("current_price") is None and d_row[2] is not None:
                        result_dict["current_price"] = float(d_row[2])
                    if result_dict.get("pe_ratio") in [None, "N/A"] and d_row[3]:
                        result_dict["pe_ratio"] = str(d_row[3])
                    if result_dict.get("roce") is None and d_row[4] is not None:
                        result_dict["roce"] = float(d_row[4])
                        result_dict["roce_pct"] = float(d_row[4])
                    if result_dict.get("debt_to_equity") is None and d_row[5] is not None:
                        result_dict["debt_to_equity"] = float(d_row[5])
            except Exception as d_err:
                logger.debug(f"Discovery reel lookup notice for {clean}: {d_err}")

            # 3. Check reports table for report text and baseline data
            try:
                cursor.execute(
                    f"SELECT short_name, baseline_price, baseline_pe, baseline_mcap, report_text "
                    f"FROM reports WHERE ticker = {placeholder};",
                    (clean,)
                )
                r_row = cursor.fetchone()
                if r_row:
                    short_name = r_row[0] or clean
                    b_price = float(r_row[1]) if r_row[1] is not None else None
                    b_pe = str(r_row[2]) if r_row[2] is not None else "N/A"
                    b_mcap = float(r_row[3]) if r_row[3] is not None else None
                    report_text = r_row[4] or ""

                    if not result_dict.get("company_name"):
                        result_dict["company_name"] = short_name
                        result_dict["short_name"] = short_name
                    if result_dict.get("current_price") is None and b_price is not None:
                        result_dict["current_price"] = b_price
                    if result_dict.get("pe_ratio") in [None, "N/A"] and b_pe != "N/A":
                        result_dict["pe_ratio"] = b_pe
                    if result_dict.get("market_cap") is None and b_mcap is not None:
                        result_dict["market_cap"] = b_mcap

                    # Extract quantitative ratios from report text
                    extracted = extract_fundamentals_from_report_text(report_text, result_dict)
                    result_dict.update(extracted)
            except Exception as r_err:
                logger.debug(f"Reports table parsing notice for {clean}: {r_err}")

            # If we obtained useful metrics, persist to cached_fundamentals
            if result_dict.get("current_price") or result_dict.get("roce") or result_dict.get("fifty_two_week_high"):
                result_dict["ticker"] = clean
                save_cached_fundamentals(clean, result_dict)

    except Exception as e:
        logger.error(f"Error fetching cached fundamentals for {ticker}: {e}")
    finally:
        cursor.close()
        conn.close()

    if not result_dict:
        return None

    # Harmonize complementary alias keys
    result_dict["roce_pct"] = result_dict.get("roce")
    result_dict["opm"] = result_dict.get("operating_margin")
    result_dict["price_to_book"] = result_dict.get("pb_ratio")
    result_dict["ev_to_ebitda"] = result_dict.get("ev_ebitda")
    result_dict["52w_high"] = result_dict.get("fifty_two_week_high") or "N/A"
    result_dict["52w_low"] = result_dict.get("fifty_two_week_low") or "N/A"

    return result_dict


def save_cached_fundamentals(ticker: str, data: Dict[str, Any]) -> None:
    """Upserts stock fundamentals into the localized cached_fundamentals repository."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    clean = clean_ticker(ticker)

    company_name = data.get("company_name") or data.get("short_name") or clean
    sector = data.get("sector") or "General Industry"
    industry = data.get("industry") or "Diversified"

    curr_price = data.get("current_price")
    try:
        curr_price = float(str(curr_price).replace(",", "").strip()) if curr_price not in [None, "N/A", ""] else None
    except Exception:
        curr_price = None

    market_cap = data.get("market_cap")
    try:
        market_cap = float(str(market_cap).replace(",", "").strip()) if market_cap not in [None, "N/A", ""] else None
    except Exception:
        market_cap = None

    pe_ratio = str(data.get("pe_ratio", "N/A"))
    forward_pe = str(data.get("forward_pe", "N/A"))
    pb_ratio = str(data.get("pb_ratio") or data.get("price_to_book") or "N/A")
    ev_ebitda = str(data.get("ev_ebitda") or data.get("ev_to_ebitda") or "N/A")

    roce = data.get("roce") or data.get("roce_pct")
    try:
        roce = float(str(roce).replace("%", "").strip()) if roce not in [None, "N/A", ""] else None
    except Exception:
        roce = None

    roe = data.get("roe")
    try:
        roe = float(str(roe).replace("%", "").strip()) if roe not in [None, "N/A", ""] else None
    except Exception:
        roe = None

    opm = data.get("operating_margin") or data.get("opm")
    try:
        opm = float(str(opm).replace("%", "").strip()) if opm not in [None, "N/A", ""] else None
    except Exception:
        opm = None

    de = data.get("debt_to_equity")
    try:
        de = float(str(de).strip()) if de not in [None, "N/A", ""] else None
    except Exception:
        de = None

    h52 = data.get("fifty_two_week_high") or data.get("52w_high")
    try:
        h52 = float(str(h52).replace(",", "").replace("₹", "").strip()) if h52 not in [None, "N/A", ""] else None
    except Exception:
        h52 = None

    l52 = data.get("fifty_two_week_low") or data.get("52w_low")
    try:
        l52 = float(str(l52).replace(",", "").replace("₹", "").strip()) if l52 not in [None, "N/A", ""] else None
    except Exception:
        l52 = None

    source = data.get("source") or "LOCAL_DB_HARMONIZED"

    try:
        query = f"""
            INSERT INTO cached_fundamentals (
                ticker, company_name, sector, industry, current_price, market_cap,
                pe_ratio, forward_pe, pb_ratio, ev_ebitda, roce, roe, operating_margin,
                debt_to_equity, fifty_two_week_high, fifty_two_week_low, source, updated_at
            )
            VALUES (
                {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, CURRENT_TIMESTAMP
            )
            ON CONFLICT (ticker)
            DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, cached_fundamentals.company_name),
                sector = CASE WHEN EXCLUDED.sector != 'General Industry' THEN EXCLUDED.sector ELSE cached_fundamentals.sector END,
                industry = CASE WHEN EXCLUDED.industry != 'Diversified' THEN EXCLUDED.industry ELSE cached_fundamentals.industry END,
                current_price = COALESCE(EXCLUDED.current_price, cached_fundamentals.current_price),
                market_cap = COALESCE(EXCLUDED.market_cap, cached_fundamentals.market_cap),
                pe_ratio = CASE WHEN EXCLUDED.pe_ratio != 'N/A' THEN EXCLUDED.pe_ratio ELSE cached_fundamentals.pe_ratio END,
                forward_pe = CASE WHEN EXCLUDED.forward_pe != 'N/A' THEN EXCLUDED.forward_pe ELSE cached_fundamentals.forward_pe END,
                pb_ratio = CASE WHEN EXCLUDED.pb_ratio != 'N/A' THEN EXCLUDED.pb_ratio ELSE cached_fundamentals.pb_ratio END,
                ev_ebitda = CASE WHEN EXCLUDED.ev_ebitda != 'N/A' THEN EXCLUDED.ev_ebitda ELSE cached_fundamentals.ev_ebitda END,
                roce = COALESCE(EXCLUDED.roce, cached_fundamentals.roce),
                roe = COALESCE(EXCLUDED.roe, cached_fundamentals.roe),
                operating_margin = COALESCE(EXCLUDED.operating_margin, cached_fundamentals.operating_margin),
                debt_to_equity = COALESCE(EXCLUDED.debt_to_equity, cached_fundamentals.debt_to_equity),
                fifty_two_week_high = COALESCE(EXCLUDED.fifty_two_week_high, cached_fundamentals.fifty_two_week_high),
                fifty_two_week_low = COALESCE(EXCLUDED.fifty_two_week_low, cached_fundamentals.fifty_two_week_low),
                source = EXCLUDED.source,
                updated_at = CURRENT_TIMESTAMP;
        """
        cursor.execute(query, (
            clean, company_name, sector, industry, curr_price, market_cap,
            pe_ratio, forward_pe, pb_ratio, ev_ebitda, roce, roe, opm,
            de, h52, l52, source
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Error saving cached fundamentals for {ticker}: {e}")
    finally:
        cursor.close()
        conn.close()


def sync_all_cached_fundamentals() -> int:
    """
    Scans all existing reports and discovery reel records in the database,
    extracts institutional metrics, and populates cached_fundamentals.
    Returns the count of successfully synchronized equities.
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    count = 0

    try:
        cursor.execute("SELECT ticker, short_name, baseline_price, baseline_pe, baseline_mcap, report_text FROM reports;")
        rows = cursor.fetchall()
        for r in rows:
            clean = clean_ticker(r[0])
            base_data = {
                "ticker": clean,
                "company_name": r[1] or clean,
                "current_price": float(r[2]) if r[2] is not None else None,
                "pe_ratio": str(r[3]) if r[3] is not None else "N/A",
                "market_cap": float(r[4]) if r[4] is not None else None,
                "source": "REPORTS_BASELINE_SYNC"
            }
            extracted = extract_fundamentals_from_report_text(r[5] or "", base_data)
            save_cached_fundamentals(clean, extracted)
            count += 1

        # Also blend in discovery reel
        cursor.execute("SELECT ticker, company_name, sector, current_price, pe_ratio, roce_pct, debt_to_equity FROM discovery_reel;")
        d_rows = cursor.fetchall()
        for dr in d_rows:
            clean = clean_ticker(dr[0])
            d_data = {
                "ticker": clean,
                "company_name": dr[1] or clean,
                "sector": dr[2] or "General Industry",
                "current_price": float(dr[3]) if dr[3] is not None else None,
                "pe_ratio": str(dr[4]) if dr[4] is not None else "N/A",
                "roce": float(dr[5]) if dr[5] is not None else None,
                "debt_to_equity": float(dr[6]) if dr[6] is not None else None,
                "source": "DISCOVERY_REEL_SYNC"
            }
            save_cached_fundamentals(clean, d_data)

    except Exception as e:
        logger.error(f"Error during sync_all_cached_fundamentals: {e}")
    finally:
        cursor.close()
        conn.close()

    logger.info(f"Synchronized {count} equities into cached_fundamentals repository.")
    return count
