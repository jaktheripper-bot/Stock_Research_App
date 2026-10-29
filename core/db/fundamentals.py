"""Localized Fundamentals Cache repository for peer comparison and sub-second metrics resolution."""

import re
import json
import logging
from typing import Optional, Dict, Any
from normalizer import clean_ticker
from core.db.connection import init_db, get_db_connection, get_placeholder, now_ist_iso
from core.presentation.formatters import normalize_de_ratio, normalize_pe_raw

logger = logging.getLogger("equity_research.core.db.fundamentals")


def extract_fundamentals_from_report_text(report_text: str, fallback_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Deterministically extracts verified financial ratios, multiples, and price ranges
    from research report text (7-pillar narrative + health matrix).
    """
    res: Dict[str, Any] = {}
    if fallback_data:
        res.update(fallback_data)

    if res.get("pe_ratio") == "Fair":
        res["pe_ratio"] = "N/A"

    if not report_text or not isinstance(report_text, str):
        return res

    txt = report_text.replace("\xa0", " ").replace("–", "-").replace("—", "-")
    is_legacy_synth_template = (
        "debt-to-equity ratio of 0.15" in txt
        and "Return on Capital Employed (ROCE) of 22.4%" in txt
    )

    # 0. Trailing P/E (Price-to-Earnings)
    if res.get("pe_ratio") in [None, "N/A", "Fair", "—", "-", "", 0, 0.0, "0"]:
        extracted_pe: Optional[str] = None
        # (a) Markdown table row: | **Trailing P/E Ratio** | 29.87x | or | P/E Ratio (TTM) | 120.82x |
        m_pe_tbl = re.search(
            r"\|\s*\*?\*?(?:Trailing\s+)?P/E(?:\s+(?:Ratio|Multiple))?(?:\s*\(TTM\))?\*?\*?\s*\|\s*~?`?(\d{1,3}(?:\.\d{1,2})?)\s*(?:x|times)?`?\s*\|",
            txt,
            re.I,
        )
        if m_pe_tbl:
            extracted_pe = f"{float(m_pe_tbl.group(1)):.2f}"
        # (b) Key-value colon line: Trailing P/E Ratio : 22.2x or **P/E Ratio:** 120.82x
        if not extracted_pe:
            m_pe_kv = re.search(
                r"(?:Trailing\s+)?P/E(?:\s+(?:Ratio|Multiple))?(?:\s*\(TTM\))?\*?\*?\s*:\s*\*?\*?~?(\d{1,3}(?:\.\d{1,2})?)\s*(?:x|times)?\b",
                txt,
                re.I,
            )
            if m_pe_kv and float(m_pe_kv.group(1)) > 0:
                extracted_pe = f"{float(m_pe_kv.group(1)):.2f}"
        # (c) Tight prose range: P/E [...] of approximately 12.2x to 12.8x
        if not extracted_pe:
            m_pe_rng = re.search(
                r"(?:trailing\s+)?P/E(?:\s*(?:\[[^\]]*\]|\([^\)]*\)))?(?:\s+(?:ratio|multiple))?\s*"
                r"(?:of|stands\s+at|is|at|around|approximately|near)\s*(?:approximately\s+|roughly\s+|around\s+)?"
                r"(\d{1,3}(?:\.\d{1,2})?)\s*(?:x|times)?\s*(?:to|-)\s*(\d{1,3}(?:\.\d{1,2})?)\s*(?:x|times)",
                txt,
                re.I,
            )
            if m_pe_rng:
                v1, v2 = float(m_pe_rng.group(1)), float(m_pe_rng.group(2))
                if 0 < v1 <= 500 and 0 < v2 <= 500 and abs(v2 - v1) <= 6.0:
                    extracted_pe = f"{((v1 + v2) / 2.0):.2f}"
        # (d) Prose sentence: P/E [Price-to-Earnings Ratio] stands at 21.24x / P/E ratio (...) of 43.86
        if not extracted_pe:
            m_pe_prs = re.search(
                r"(?:trailing\s+)?P/E(?:\s*(?:\[[^\]]*\]|\([^\)]*\)))?(?:\s+(?:ratio|multiple))?\s*"
                r"(?:of|stands\s+at|is|at|around|approximately|near)\s*(?:approximately\s+|roughly\s+|around\s+)?"
                r"(\d{1,3}(?:\.\d{1,2})?)\s*(?:x\b|times\b|[.,;]|\s+based\b)",
                txt,
                re.I,
            )
            if m_pe_prs and 0 < float(m_pe_prs.group(1)) <= 500:
                extracted_pe = f"{float(m_pe_prs.group(1)):.2f}"
        # (e) Explicit loss-making / negative TTM EPS statement
        if not extracted_pe and re.search(
            r"\bloss[- ]making\b|negative\s+(?:trailing\s+|ttm\s+)?(?:earnings|eps|net\s+profit)|Valuation:\s*Loss-Making",
            txt,
            re.I,
        ):
            extracted_pe = "NM"

        if extracted_pe:
            res["pe_ratio"] = extracted_pe

    # 1. ROCE (Return on Capital Employed)
    if not is_legacy_synth_template and res.get("roce") in [None, "N/A", "", 0, 0.0]:
        m_roce = re.search(r'(?:ROCE|Return on Capital Employed)[^\d\n]*?(\d+(?:\.\d+)?)\s*%', txt, re.I)
        if not m_roce:
            m_roce = re.search(r'ROCE\s*(?:of|was|is|reached|stands at|exceeding|above)?\s*\[?[^\]\n]*\]?\s*(\d+(?:\.\d+)?)\s*%', txt, re.I)
        if m_roce:
            try:
                res["roce"] = float(m_roce.group(1))
            except Exception as e:
                logger.debug("Failed parsing ROCE from report text: %s", e)

    # 2. ROE (Return on Equity)
    if res.get("roe") in [None, "N/A", "", 0, 0.0]:
        m_roe = re.search(r'(?:ROE|Return on Equity)[^\d\n]*?(\d+(?:\.\d+)?)\s*%', txt, re.I)
        if not m_roe:
            m_roe = re.search(r'ROE\s*(?:of|was|is|reached|stands at|exceeding|above)?\s*\[?[^\]\n]*\]?\s*(\d+(?:\.\d+)?)\s*%', txt, re.I)
        if m_roe:
            try:
                res["roe"] = float(m_roe.group(1))
            except Exception as e:
                logger.debug("Failed parsing ROE from report text: %s", e)

    # 3. Operating Margin (OPM) / EBITDA Margin
    if res.get("operating_margin") in [None, "N/A", "", 0, 0.0]:
        m_opm = re.search(
            r'(?:Operating\s+(?:Profit\s+)?Margins?|OPM|EBITDA\s*[\]\)]?\s*Margins?)[^\d\n%]{0,45}?(-?\d+(?:\.\d+)?)\s*%',
            txt,
            re.I,
        )
        if m_opm:
            try:
                cand_opm = float(m_opm.group(1))
                if -100.0 <= cand_opm <= 95.0:
                    res["operating_margin"] = cand_opm
            except Exception as e:
                logger.debug("Failed parsing OPM from report text: %s", e)

    # 4. Debt-to-Equity (D/E)
    if not is_legacy_synth_template and res.get("debt_to_equity") in [None, "N/A", ""]:
        if (
            re.search(r"Balance\s*Sheet\s*:\s*Debt-Free", txt, re.I)
            or re.search(r"\b(?:virtually\s+)?debt[- ]free\b", txt, re.I)
            or re.search(r"\bzero\s+(?:gross\s+|long[- ]term\s+)?debt\b", txt, re.I)
        ):
            res["debt_to_equity"] = 0.0
        else:
            m_de = re.search(
                r"(?:debt[- ]to[- ]equity|(?<!net\s)d/e)(?:\s*(?:\[[^\]]*\]|\([^\)]*\)))?(?:\s+ratio)?\s*"
                r"(?:of|stands\s+at|is|at|around|approximately|near|:|\|)\s*~?`?(\d+(?:\.\d+)?)\s*(x|%)?",
                txt,
                re.I,
            )
            if m_de:
                try:
                    raw_de = float(m_de.group(1))
                    unit = (m_de.group(2) or "").strip()
                    if unit == "%":
                        res["debt_to_equity"] = round(raw_de / 100.0, 2)
                    elif raw_de <= 10.0:
                        res["debt_to_equity"] = round(raw_de, 2)
                except Exception as e:
                    logger.debug("Failed parsing D/E from report text: %s", e)

    # 5. 52-Week High & Low (strictly reject % drawdowns or x multiples like '3.1x' / '27.0%')
    if res.get("fifty_two_week_high") in [None, "N/A", "", 0, 0.0] or res.get("fifty_two_week_low") in [None, "N/A", "", 0, 0.0]:
        mh = re.search(
            r'52-week\s+high[^\d\n%]{0,30}?(?:INR|₹|Rs\.?)\s*([\d,]+(?:\.\d+)?)(?!\s*(?:%|x\b|times\b))',
            txt,
            re.I,
        )
        ml = re.search(
            r'52-week\s+low[^\d\n%]{0,30}?(?:INR|₹|Rs\.?)\s*([\d,]+(?:\.\d+)?)(?!\s*(?:%|x\b|times\b))',
            txt,
            re.I,
        )
        if mh and res.get("fifty_two_week_high") in [None, "N/A", "", 0, 0.0]:
            try:
                res["fifty_two_week_high"] = float(mh.group(1).replace(",", "").strip())
            except Exception as e:
                logger.debug("Failed parsing 52-week high from report text: %s", e)
        if ml and res.get("fifty_two_week_low") in [None, "N/A", "", 0, 0.0]:
            try:
                res["fifty_two_week_low"] = float(ml.group(1).replace(",", "").strip())
            except Exception as e:
                logger.debug("Failed parsing 52-week low from report text: %s", e)

        # Combined range pattern fallback: "52-week range of ₹1,000 - ₹1,500"
        if res.get("fifty_two_week_high") in [None, "N/A", ""] or res.get("fifty_two_week_low") in [None, "N/A", ""]:
            m_comb = re.search(
                r'52-week\s+(?:range|band)[^\d\n%]{0,30}?(?:INR|₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)\s*[-–]\s*(?:INR|₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)(?!\s*(?:%|x\b|times\b))',
                txt,
                re.I,
            )
            if m_comb:
                try:
                    val1 = float(m_comb.group(1).replace(",", "").strip())
                    val2 = float(m_comb.group(2).replace(",", "").strip())
                    res["fifty_two_week_low"] = min(val1, val2)
                    res["fifty_two_week_high"] = max(val1, val2)
                except Exception as e:
                    logger.debug("Failed parsing 52-week range from report text: %s", e)

        # Sanity-check extracted 52W pair against inverted bounds or CMP distortion
        try:
            ref_cmp = float(str(res.get("current_price") or 0).replace(",", "").strip() or 0)
            ext_hi = res.get("fifty_two_week_high")
            ext_lo = res.get("fifty_two_week_low")
            hi_f = float(ext_hi) if ext_hi not in [None, "N/A", ""] else None
            lo_f = float(ext_lo) if ext_lo not in [None, "N/A", ""] else None
            if hi_f is not None and ref_cmp > 0 and hi_f < ref_cmp * 0.50:
                res.pop("fifty_two_week_high", None)
                hi_f = None
            if lo_f is not None and ref_cmp > 0 and lo_f > ref_cmp * 1.50:
                res.pop("fifty_two_week_low", None)
                lo_f = None
            if hi_f is not None and lo_f is not None and hi_f < lo_f:
                res.pop("fifty_two_week_high", None)
                res.pop("fifty_two_week_low", None)
        except Exception as e:
            logger.debug("52-week sanity guard notice: %s", e)

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
    had_synth_batch = False

    try:
        # 1. Query cached_fundamentals table
        cursor.execute(
            f"SELECT ticker, company_name, sector, industry, current_price, market_cap, "
            f"pe_ratio, forward_pe, pb_ratio, ev_ebitda, roce, roe, operating_margin, "
            f"debt_to_equity, fifty_two_week_high, fifty_two_week_low, source, updated_at "
            f"FROM cached_fundamentals WHERE ticker = {placeholder};",
            (clean,)
        )
        row = cursor.fetchone()
        if row:
            raw_px = float(row[4]) if row[4] is not None else None
            raw_mc = float(row[5]) if row[5] is not None else None
            raw_pe = row[6] or "N/A"
            raw_roce = float(row[10]) if row[10] is not None else None
            raw_de = float(row[13]) if row[13] is not None else None
            from bse_master import is_synthetic_test_symbol
            is_synth_batch = bool(
                not is_synthetic_test_symbol(clean)
                and raw_mc is not None
                and abs(raw_mc - 25_000_000_000.0) < 1.0
                and (
                    (raw_px is not None and abs(raw_px - 500.0) < 1e-6 and str(raw_pe).strip() in ("22.5", "22.50"))
                    or (raw_roce is not None and (abs(raw_roce - 22.0) < 1e-4 or abs(raw_roce - 22.4) < 1e-4))
                    or (str(raw_pe).strip() in ("22.5", "22.50") and raw_de is not None and abs(raw_de - 0.15) < 1e-4)
                )
            )
            had_synth_batch = is_synth_batch
            result_dict = {
                "ticker": row[0],
                "company_name": row[1] or clean,
                "short_name": row[1] or clean,
                "sector": row[2] or "General Industry",
                "industry": row[3] or "Diversified",
                "current_price": None if (is_synth_batch and raw_px is not None and abs(raw_px - 500.0) < 1e-6) else raw_px,
                "market_cap": None if is_synth_batch else raw_mc,
                "pe_ratio": "N/A" if (is_synth_batch and str(raw_pe).strip() in ("22.5", "22.50")) else raw_pe,
                "forward_pe": row[7] or "N/A",
                "pb_ratio": row[8] or "N/A",
                "price_to_book": row[8] or "N/A",
                "ev_ebitda": row[9] or "N/A",
                "ev_to_ebitda": row[9] or "N/A",
                "roce": None if (is_synth_batch and raw_roce is not None and (abs(raw_roce - 22.0) < 1e-4 or abs(raw_roce - 22.4) < 1e-4)) else raw_roce,
                "roce_pct": None if (is_synth_batch and raw_roce is not None and (abs(raw_roce - 22.0) < 1e-4 or abs(raw_roce - 22.4) < 1e-4)) else raw_roce,
                "roe": float(row[11]) if row[11] is not None else None,
                "operating_margin": float(row[12]) if row[12] is not None else None,
                "opm": float(row[12]) if row[12] is not None else None,
                "debt_to_equity": None if (is_synth_batch and raw_de is not None and abs(raw_de - 0.15) < 1e-4) else raw_de,
                "fifty_two_week_high": float(row[14]) if row[14] is not None else None,
                "52w_high": float(row[14]) if row[14] is not None else "N/A",
                "fifty_two_week_low": float(row[15]) if row[15] is not None else None,
                "52w_low": float(row[15]) if row[15] is not None else "N/A",
                "source": row[16] or "LOCAL_DB_HARMONIZED",
                "quote_updated_at": str(row[17]) if len(row) > 17 and row[17] is not None else None,
            }

        # Check if missing key metrics (ROCE, ROE, OPM, 52w range)
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
                    if result_dict.get("pe_ratio") in [None, "N/A", "Fair", "—"] and d_row[3]:
                        norm_d_pe = normalize_pe_raw(d_row[3])
                        if norm_d_pe != "N/A":
                            result_dict["pe_ratio"] = norm_d_pe
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
                    is_synth_rep = bool(
                        b_mcap is not None
                        and abs(b_mcap - 25_000_000_000.0) < 1.0
                        and b_pe.strip() in ("22.5", "22.50")
                    )

                    if not result_dict.get("company_name"):
                        result_dict["company_name"] = short_name
                        result_dict["short_name"] = short_name
                    if result_dict.get("current_price") is None and b_price is not None and not (is_synth_rep and abs(b_price - 500.0) < 1e-6):
                        result_dict["current_price"] = b_price
                    if result_dict.get("pe_ratio") in [None, "N/A"] and b_pe != "N/A" and not is_synth_rep:
                        result_dict["pe_ratio"] = b_pe
                    if result_dict.get("market_cap") is None and b_mcap is not None and not is_synth_rep:
                        result_dict["market_cap"] = b_mcap

                    # Extract quantitative ratios from report text
                    extracted = extract_fundamentals_from_report_text(report_text, result_dict)
                    result_dict.update(extracted)
            except Exception as r_err:
                logger.debug(f"Reports table parsing notice for {clean}: {r_err}")

            # If we obtained useful metrics (or scrubbed a synthetic batch tuple), persist to cached_fundamentals
            if had_synth_batch or result_dict.get("current_price") or result_dict.get("roce") or result_dict.get("fifty_two_week_high"):
                result_dict["ticker"] = clean
                save_cached_fundamentals(clean, result_dict, force_overwrite=had_synth_batch)

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


def save_cached_fundamentals(ticker: str, data: Dict[str, Any], force_overwrite: bool = False) -> None:
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
    except Exception as e:
        logger.debug("Failed parsing curr_price: %s", e)
        curr_price = None

    market_cap = data.get("market_cap")
    try:
        market_cap = float(str(market_cap).replace(",", "").strip()) if market_cap not in [None, "N/A", ""] else None
    except Exception as e:
        logger.debug("Failed parsing market_cap: %s", e)
        market_cap = None

    pe_ratio = normalize_pe_raw(data.get("pe_ratio", "N/A"))
    forward_pe = normalize_pe_raw(data.get("forward_pe", "N/A"))
    pb_ratio = str(data.get("pb_ratio") or data.get("price_to_book") or "N/A")
    ev_ebitda = str(data.get("ev_ebitda") or data.get("ev_to_ebitda") or "N/A")

    roce = data.get("roce") if data.get("roce") is not None else data.get("roce_pct")
    try:
        roce = float(str(roce).replace("%", "").strip()) if roce not in [None, "N/A", ""] else None
    except Exception as e:
        logger.debug("Failed parsing roce: %s", e)
        roce = None

    roe = data.get("roe")
    try:
        roe = float(str(roe).replace("%", "").strip()) if roe not in [None, "N/A", ""] else None
    except Exception as e:
        logger.debug("Failed parsing roe: %s", e)
        roe = None

    opm = data.get("operating_margin") if data.get("operating_margin") is not None else data.get("opm")
    try:
        opm = float(str(opm).replace("%", "").strip()) if opm not in [None, "N/A", ""] else None
    except Exception as e:
        logger.debug("Failed parsing opm: %s", e)
        opm = None

    de = normalize_de_ratio(
        data.get("debt_to_equity"),
        ticker=clean,
        industry=industry,
        company_name=company_name,
    )

    h52 = data.get("fifty_two_week_high") or data.get("52w_high")
    try:
        h52 = float(str(h52).replace(",", "").replace("₹", "").strip()) if h52 not in [None, "N/A", ""] else None
    except Exception as e:
        logger.debug("Failed parsing h52: %s", e)
        h52 = None

    l52 = data.get("fifty_two_week_low") or data.get("52w_low")
    try:
        l52 = float(str(l52).replace(",", "").replace("₹", "").strip()) if l52 not in [None, "N/A", ""] else None
    except Exception as e:
        logger.debug("Failed parsing l52: %s", e)
        l52 = None

    source = data.get("source") or "LOCAL_DB_HARMONIZED"

    de_update_expr = (
        "EXCLUDED.debt_to_equity"
        if force_overwrite
        else (
            "CASE WHEN ABS(COALESCE(cached_fundamentals.market_cap, 0) - 25000000000.0) < 1.0 "
            "AND ABS(COALESCE(cached_fundamentals.debt_to_equity, -1) - 0.15) < 0.0001 "
            "THEN EXCLUDED.debt_to_equity "
            "ELSE COALESCE(EXCLUDED.debt_to_equity, cached_fundamentals.debt_to_equity) END"
        )
    )
    pe_update_expr = (
        "EXCLUDED.pe_ratio"
        if force_overwrite
        else (
            "CASE WHEN EXCLUDED.pe_ratio NOT IN ('N/A', 'Fair', '—', '-', '') THEN EXCLUDED.pe_ratio "
            "WHEN cached_fundamentals.pe_ratio IN ('Fair', '—', '-', '') THEN 'N/A' "
            "WHEN ABS(COALESCE(cached_fundamentals.market_cap, 0) - 25000000000.0) < 1.0 "
            "AND cached_fundamentals.pe_ratio IN ('22.5', '22.50') THEN EXCLUDED.pe_ratio "
            "ELSE cached_fundamentals.pe_ratio END"
        )
    )
    roce_update_expr = (
        "EXCLUDED.roce"
        if force_overwrite
        else (
            "CASE WHEN ABS(COALESCE(cached_fundamentals.market_cap, 0) - 25000000000.0) < 1.0 "
            "AND (ABS(COALESCE(cached_fundamentals.roce, -1) - 22.0) < 0.0001 "
            "OR ABS(COALESCE(cached_fundamentals.roce, -1) - 22.4) < 0.0001) "
            "THEN EXCLUDED.roce "
            "ELSE COALESCE(EXCLUDED.roce, cached_fundamentals.roce) END"
        )
    )

    try:
        now_ts = now_ist_iso()
        query = f"""
            INSERT INTO cached_fundamentals (
                ticker, company_name, sector, industry, current_price, market_cap,
                pe_ratio, forward_pe, pb_ratio, ev_ebitda, roce, roe, operating_margin,
                debt_to_equity, fifty_two_week_high, fifty_two_week_low, source, updated_at
            )
            VALUES (
                {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}
            )
            ON CONFLICT (ticker)
            DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, cached_fundamentals.company_name),
                sector = CASE WHEN EXCLUDED.sector != 'General Industry' THEN EXCLUDED.sector ELSE cached_fundamentals.sector END,
                industry = CASE WHEN EXCLUDED.industry != 'Diversified' THEN EXCLUDED.industry ELSE cached_fundamentals.industry END,
                current_price = COALESCE(EXCLUDED.current_price, cached_fundamentals.current_price),
                market_cap = CASE WHEN ABS(COALESCE(cached_fundamentals.market_cap, 0) - 25000000000.0) < 1.0 THEN EXCLUDED.market_cap ELSE COALESCE(EXCLUDED.market_cap, cached_fundamentals.market_cap) END,
                pe_ratio = {pe_update_expr},
                forward_pe = CASE WHEN EXCLUDED.forward_pe NOT IN ('N/A', 'Fair', '—', '-', '') THEN EXCLUDED.forward_pe ELSE cached_fundamentals.forward_pe END,
                pb_ratio = CASE WHEN EXCLUDED.pb_ratio != 'N/A' THEN EXCLUDED.pb_ratio ELSE cached_fundamentals.pb_ratio END,
                ev_ebitda = CASE WHEN EXCLUDED.ev_ebitda != 'N/A' THEN EXCLUDED.ev_ebitda ELSE cached_fundamentals.ev_ebitda END,
                roce = {roce_update_expr},
                roe = COALESCE(EXCLUDED.roe, cached_fundamentals.roe),
                operating_margin = COALESCE(EXCLUDED.operating_margin, cached_fundamentals.operating_margin),
                debt_to_equity = {de_update_expr},
                fifty_two_week_high = COALESCE(EXCLUDED.fifty_two_week_high, cached_fundamentals.fifty_two_week_high),
                fifty_two_week_low = COALESCE(EXCLUDED.fifty_two_week_low, cached_fundamentals.fifty_two_week_low),
                source = EXCLUDED.source,
                updated_at = EXCLUDED.updated_at;
        """
        cursor.execute(query, (
            clean, company_name, sector, industry, curr_price, market_cap,
            pe_ratio, forward_pe, pb_ratio, ev_ebitda, roce, roe, opm,
            de, h52, l52, source, now_ts
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
    extracts metrics, and populates cached_fundamentals.
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
