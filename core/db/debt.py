"""Database Repository for Corporate Debt, NCDs, SDIs, and Credit Rating Events.

Supports dual-binding for both local SQLite and production PostgreSQL (Supabase / Render).
Complies with SEBI (Issue and Listing of Non-Convertible Securities) Regulations.
"""

import json
import logging
from decimal import Decimal
from datetime import datetime, date, timezone
from typing import Optional, List, Dict, Any

from core.db.connection import get_db_connection, get_supabase_url, is_postgres_connection, is_postgres_active
from core.db.debt_universe import (
    CANONICAL_DEBT_UNIVERSE,
    CANONICAL_DEBT_BY_ISIN,
    CANONICAL_DEBT_BY_TICKER,
)

def is_supabase_enabled() -> bool:
    return bool(get_supabase_url() and is_postgres_active())

logger = logging.getLogger(__name__)

# Standardized 8-tier rating scale weights
RATING_TIER_ORDER = {
    "AAA": 8,
    "AA+": 7,
    "AA": 6,
    "AA-": 5,
    "A+": 4,
    "A": 3,
    "BBB": 2,
    "D": 1
}

def clean_dict_row(cursor, row: Any) -> Dict[str, Any]:
    """Converts a sqlite3.Row, tuple, or psycopg2 dict into a pure Python dictionary."""
    if not row:
        return {}
    if hasattr(row, "keys"):
        d = dict(row)
    elif cursor and cursor.description:
        cols = [c[0] for c in cursor.description]
        d = dict(zip(cols, row))
    else:
        d = dict(row)

    for k, v in list(d.items()):
        if isinstance(v, Decimal):
            d[k] = float(v)
        elif isinstance(v, (datetime, date)):
            d[k] = str(v)

    if "metadata_json" in d and isinstance(d["metadata_json"], str):
        try:
            d["metadata"] = json.loads(d["metadata_json"])
        except Exception:
            d["metadata"] = {}
    return d

def save_debt_security(sec: Dict[str, Any]) -> bool:
    """Inserts or updates a corporate debt security or SDI."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)

    isin = sec["isin"].strip().upper()
    ticker = sec.get("ticker", "").strip().upper()
    scrip_code = sec.get("scrip_code")
    series = sec.get("series", "N1")
    instrument_name = sec.get("instrument_name", "")
    instrument_type = sec.get("instrument_type", "NCD")
    seniority_tier = sec.get("seniority_tier", "SENIOR_SECURED").upper()
    face_value = float(sec.get("face_value", 10000.0))
    coupon_rate_pct = float(sec.get("coupon_rate_pct", 0.0))
    coupon_frequency = sec.get("coupon_frequency", "ANNUAL").upper()
    issue_date = sec.get("issue_date")
    maturity_date = sec.get("maturity_date")
    credit_rating = sec.get("credit_rating", "AAA").upper()
    credit_rating_agency = sec.get("credit_rating_agency", "CRISIL").upper()
    asset_cover_ratio = float(sec.get("asset_cover_ratio", 1.25))
    is_listed = bool(sec.get("is_listed", True))
    exchange = sec.get("exchange", "BSE").upper()
    is_sdi = bool(sec.get("is_sdi", False))
    originator = sec.get("originator")
    fldg_pct = float(sec.get("fldg_pct", 0.0))
    last_traded_price = float(sec["last_traded_price"]) if sec.get("last_traded_price") is not None else face_value
    ytm_pct = float(sec["ytm_pct"]) if sec.get("ytm_pct") is not None else coupon_rate_pct
    macaulay_duration_years = float(sec["macaulay_duration_years"]) if sec.get("macaulay_duration_years") is not None else None
    modified_duration_years = float(sec["modified_duration_years"]) if sec.get("modified_duration_years") is not None else None
    meta_json = json.dumps(sec.get("metadata", {}))

    try:
        if use_pg:
            query = """
                INSERT INTO corporate_debt_securities (
                    isin, ticker, scrip_code, series, instrument_name, instrument_type,
                    seniority_tier, face_value, coupon_rate_pct, coupon_frequency,
                    issue_date, maturity_date, credit_rating, credit_rating_agency,
                    asset_cover_ratio, is_listed, exchange, is_sdi, originator,
                    fldg_pct, last_traded_price, ytm_pct, macaulay_duration_years,
                    modified_duration_years, metadata_json, last_updated
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, now()
                )
                ON CONFLICT (isin) DO UPDATE SET
                    ticker = EXCLUDED.ticker,
                    scrip_code = EXCLUDED.scrip_code,
                    series = EXCLUDED.series,
                    instrument_name = EXCLUDED.instrument_name,
                    instrument_type = EXCLUDED.instrument_type,
                    seniority_tier = EXCLUDED.seniority_tier,
                    face_value = EXCLUDED.face_value,
                    coupon_rate_pct = EXCLUDED.coupon_rate_pct,
                    coupon_frequency = EXCLUDED.coupon_frequency,
                    maturity_date = EXCLUDED.maturity_date,
                    credit_rating = EXCLUDED.credit_rating,
                    credit_rating_agency = EXCLUDED.credit_rating_agency,
                    asset_cover_ratio = EXCLUDED.asset_cover_ratio,
                    is_listed = EXCLUDED.is_listed,
                    exchange = EXCLUDED.exchange,
                    is_sdi = EXCLUDED.is_sdi,
                    originator = EXCLUDED.originator,
                    fldg_pct = EXCLUDED.fldg_pct,
                    last_traded_price = EXCLUDED.last_traded_price,
                    ytm_pct = EXCLUDED.ytm_pct,
                    macaulay_duration_years = EXCLUDED.macaulay_duration_years,
                    modified_duration_years = EXCLUDED.modified_duration_years,
                    metadata_json = EXCLUDED.metadata_json,
                    last_updated = now();
            """
            cursor.execute(query, (
                isin, ticker, scrip_code, series, instrument_name, instrument_type,
                seniority_tier, face_value, coupon_rate_pct, coupon_frequency,
                issue_date, maturity_date, credit_rating, credit_rating_agency,
                asset_cover_ratio, is_listed, exchange, is_sdi, originator,
                fldg_pct, last_traded_price, ytm_pct, macaulay_duration_years,
                modified_duration_years, meta_json
            ))
        else:
            query = """
                INSERT INTO corporate_debt_securities (
                    isin, ticker, scrip_code, series, instrument_name, instrument_type,
                    seniority_tier, face_value, coupon_rate_pct, coupon_frequency,
                    issue_date, maturity_date, credit_rating, credit_rating_agency,
                    asset_cover_ratio, is_listed, exchange, is_sdi, originator,
                    fldg_pct, last_traded_price, ytm_pct, macaulay_duration_years,
                    modified_duration_years, metadata_json, last_updated
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, datetime('now')
                )
                ON CONFLICT(isin) DO UPDATE SET
                    ticker=excluded.ticker,
                    scrip_code=excluded.scrip_code,
                    series=excluded.series,
                    instrument_name=excluded.instrument_name,
                    instrument_type=excluded.instrument_type,
                    seniority_tier=excluded.seniority_tier,
                    face_value=excluded.face_value,
                    coupon_rate_pct=excluded.coupon_rate_pct,
                    coupon_frequency=excluded.coupon_frequency,
                    maturity_date=excluded.maturity_date,
                    credit_rating=excluded.credit_rating,
                    credit_rating_agency=excluded.credit_rating_agency,
                    asset_cover_ratio=excluded.asset_cover_ratio,
                    is_listed=excluded.is_listed,
                    exchange=excluded.exchange,
                    is_sdi=excluded.is_sdi,
                    originator=excluded.originator,
                    fldg_pct=excluded.fldg_pct,
                    last_traded_price=excluded.last_traded_price,
                    ytm_pct=excluded.ytm_pct,
                    macaulay_duration_years=excluded.macaulay_duration_years,
                    modified_duration_years=excluded.modified_duration_years,
                    metadata_json=excluded.metadata_json,
                    last_updated=datetime('now');
            """
            cursor.execute(query, (
                isin, ticker, scrip_code, series, instrument_name, instrument_type,
                seniority_tier, face_value, coupon_rate_pct, coupon_frequency,
                issue_date, maturity_date, credit_rating, credit_rating_agency,
                asset_cover_ratio, 1 if is_listed else 0, exchange, 1 if is_sdi else 0, originator,
                fldg_pct, last_traded_price, ytm_pct, macaulay_duration_years,
                modified_duration_years, meta_json
            ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving debt security {isin}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def get_debt_security_by_isin(isin: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single corporate debt security or SDI by its ISIN."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)
    clean_isin = isin.strip().upper()

    try:
        sql = "SELECT * FROM corporate_debt_securities WHERE isin = %s" if use_pg else "SELECT * FROM corporate_debt_securities WHERE isin = ?"
        cursor.execute(sql, (clean_isin,))
        row = cursor.fetchone()
        if row:
            return clean_dict_row(cursor, row)
        canonical = CANONICAL_DEBT_BY_ISIN.get(clean_isin)
        if canonical:
            save_debt_security(canonical)
            return dict(canonical)
        return None
    except Exception as e:
        logger.error(f"Error getting debt security {clean_isin}: {e}")
        return CANONICAL_DEBT_BY_ISIN.get(clean_isin)
    finally:
        cursor.close()
        conn.close()

def get_debt_securities_by_ticker(ticker: str) -> List[Dict[str, Any]]:
    """Retrieves all debt securities issued by a given company ticker."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)
    clean_ticker = ticker.strip().upper()

    try:
        sql = "SELECT * FROM corporate_debt_securities WHERE ticker = %s ORDER BY maturity_date ASC" if use_pg else "SELECT * FROM corporate_debt_securities WHERE ticker = ? ORDER BY maturity_date ASC"
        cursor.execute(sql, (clean_ticker,))
        rows = cursor.fetchall()
        return [clean_dict_row(cursor, r) for r in rows]
    except Exception as e:
        logger.error(f"Error getting debt securities for ticker {clean_ticker}: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def get_debt_securities_for_equity(equity_ticker: str) -> List[Dict[str, Any]]:
    """
    Finds all corporate debt securities / NCDs issued by an equity ticker or its subsidiaries.
    Supports bidirectional mapping between parent equity symbol and debt issuer tickers.
    """
    clean_sym = (equity_ticker or "").strip().upper()
    if not clean_sym:
        return []

    debt_to_equity_map = {
        "TATACAP": "TATAMOTORS",
        "TATA": "TATAMOTORS",
        "HDFCBANK": "HDFCBANK",
        "RELIANCE": "RELIANCE",
        "L&T": "LT",
        "LT": "LT",
        "LTFIN": "LT",
        "CHOLAFIN": "CHOLAFIN",
        "INDUSINDBK": "INDUSINDBK",
        "PIRAMAL": "PEL",
        "PEL": "PEL",
        "MANAPPURAM": "MANAPPURAM",
        "SHRIRAMFIN": "SHRIRAMFIN",
        "MUTHOOT": "MUTHOOTFIN",
        "MUTHOOTFIN": "MUTHOOTFIN",
        "BAJFINANCE": "BAJFINANCE",
        "BAJAJFIN": "BAJFINANCE",
        "KOTAK": "KOTAKBANK",
        "KOTAKHOME": "KOTAKBANK",
        "SBIN": "SBIN",
        "IRFC": "IRFC",
        "NTPC": "NTPC",
        "PFC": "PFC",
        "REC": "REC"
    }

    matching_debt_tickers = {clean_sym}
    for debt_sym, eq_sym in debt_to_equity_map.items():
        if eq_sym.upper() == clean_sym or debt_sym.upper() == clean_sym:
            matching_debt_tickers.add(debt_sym.upper())

    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)
    try:
        placeholders = ", ".join(["%s" if use_pg else "?" for _ in matching_debt_tickers])
        sql = f"SELECT * FROM corporate_debt_securities WHERE UPPER(ticker) IN ({placeholders}) ORDER BY maturity_date ASC"
        cursor.execute(sql, tuple(matching_debt_tickers))
        rows = cursor.fetchall()
        return [clean_dict_row(cursor, r) for r in rows]
    except Exception as e:
        logger.error(f"Error querying debt securities for equity {clean_sym}: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def get_active_debt_securities(
    seniority: Optional[str] = None,
    instrument_type: Optional[str] = None,
    min_rating: Optional[str] = None,
    is_sdi: Optional[bool] = None,
    limit: int = 500
) -> List[Dict[str, Any]]:
    """Retrieves active debt securities filtered by seniority, rating, and instrument type."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)

    clauses = ["(CAST(is_listed AS TEXT) IN ('1', 'true', 'TRUE', 't') OR is_listed IS TRUE)" if use_pg else "(is_listed = 1 OR CAST(is_listed AS TEXT) = '1')"]
    clauses.append("(ticker NOT LIKE '%TEST%' AND ticker NOT LIKE '%UNITTEST%' AND isin NOT LIKE '%TEST%' AND instrument_name NOT LIKE '%Test%')")
    params = []

    if seniority:
        clauses.append("seniority_tier = %s" if use_pg else "seniority_tier = ?")
        params.append(seniority.strip().upper())
    if instrument_type:
        clauses.append("instrument_type = %s" if use_pg else "instrument_type = ?")
        params.append(instrument_type.strip().upper())
    if is_sdi is not None:
        clauses.append("is_sdi = %s" if use_pg else "is_sdi = ?")
        params.append(True if is_sdi else False)

    where_str = " AND ".join(clauses)
    p = "%s" if use_pg else "?"
    sql = f"SELECT * FROM corporate_debt_securities WHERE {where_str} ORDER BY ytm_pct DESC LIMIT {p}"
    params.append(int(limit))

    try:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        results = [clean_dict_row(cursor, r) for r in rows]

        # Auto-seed canonical universe only if table is completely empty
        if not results and not seniority and not instrument_type and not min_rating and is_sdi is None:
            cursor.execute("SELECT COUNT(*) FROM corporate_debt_securities")
            cnt_row = cursor.fetchone()
            total_count = cnt_row[0] if cnt_row else 0
            if total_count == 0:
                cursor.close()
                conn.close()
                seed_default_debt_securities()
                return get_active_debt_securities(
                    seniority=seniority,
                    instrument_type=instrument_type,
                    min_rating=min_rating,
                    is_sdi=is_sdi,
                    limit=limit
                )

        if min_rating:
            target_weight = RATING_TIER_ORDER.get(min_rating.strip().upper(), 1)
            results = [
                r for r in results
                if RATING_TIER_ORDER.get(r.get("credit_rating", "").replace("CRISIL ", "").replace("ICRA ", "").replace("CARE ", "").replace("IND ", "").strip(), 0) >= target_weight
            ]
        return results
    except Exception as e:
        logger.error(f"Error querying active debt securities: {e}")
        return []
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception as close_err:
            logger.debug("Debt cursor close notice: %s", close_err)

def record_rating_event(event: Dict[str, Any]) -> bool:
    """Records a Credit Rating Agency action (upgrade, downgrade, watch, affirmation)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)

    isin = event["isin"].strip().upper()
    ticker = event.get("ticker", "").strip().upper()
    rating_agency = event.get("rating_agency", "CRISIL").upper()
    rating_symbol = event.get("rating_symbol", "AAA").upper()
    outlook = event.get("outlook", "STABLE").upper()
    action_type = event.get("action_type", "AFFIRMED").upper()
    event_date = event.get("event_date", date.today().isoformat())
    action_rationale = event.get("action_rationale", "")

    try:
        if use_pg:
            sql = """
                INSERT INTO credit_rating_events (
                    isin, ticker, rating_agency, rating_symbol, outlook,
                    action_type, event_date, action_rationale, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            """
            cursor.execute(sql, (isin, ticker, rating_agency, rating_symbol, outlook, action_type, event_date, action_rationale))
        else:
            sql = """
                INSERT INTO credit_rating_events (
                    isin, ticker, rating_agency, rating_symbol, outlook,
                    action_type, event_date, action_rationale, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """
            cursor.execute(sql, (isin, ticker, rating_agency, rating_symbol, outlook, action_type, event_date, action_rationale))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error recording rating event for {isin}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def get_rating_history(isin: str) -> List[Dict[str, Any]]:
    """Retrieves chronological credit rating history for an ISIN."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)
    clean_isin = isin.strip().upper()

    try:
        sql = "SELECT * FROM credit_rating_events WHERE isin = %s ORDER BY event_date DESC" if use_pg else "SELECT * FROM credit_rating_events WHERE isin = ? ORDER BY event_date DESC"
        cursor.execute(sql, (clean_isin,))
        rows = cursor.fetchall()
        return [clean_dict_row(cursor, r) for r in rows]
    except Exception as e:
        logger.error(f"Error getting rating history for {clean_isin}: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def get_recent_rating_actions(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves latest credit rating agency actions across all issuers."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_postgres_connection(conn)

    try:
        p = "%s" if use_pg else "?"
        sql = f"SELECT * FROM credit_rating_events ORDER BY event_date DESC LIMIT {p}"
        cursor.execute(sql, (int(limit),))
        rows = cursor.fetchall()
        return [clean_dict_row(cursor, r) for r in rows]
    except Exception as e:
        logger.error(f"Error getting recent rating actions: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def seed_default_debt_securities() -> int:
    """
    Seeds the full canonical benchmark universe of Indian corporate debt, NCDs,
    and SDIs (under SEBI's ₹10,000 face value framework) into SQLite and PostgreSQL.
    Guarantees 100% offline availability for 105+ benchmark instruments.
    """
    count = 0
    for s in CANONICAL_DEBT_UNIVERSE:
        if save_debt_security(s):
            count += 1
            clean_rating = s.get("credit_rating", "AAA")
            for prefix_str in ("CRISIL ", "ICRA ", "CARE ", "IND "):
                clean_rating = clean_rating.replace(prefix_str, "")
            record_rating_event({
                "isin": s["isin"],
                "ticker": s.get("ticker", ""),
                "rating_agency": s.get("credit_rating_agency", "CRISIL"),
                "rating_symbol": clean_rating.strip(),
                "outlook": "STABLE",
                "action_type": "AFFIRMED",
                "event_date": s.get("issue_date", date.today().isoformat()),
                "action_rationale": f"Initial benchmark rating assigned upon listing on {s.get('exchange', 'BSE')} debt segment."
            })
    logger.info(f"Seeded {count} benchmark corporate debt securities from canonical universe.")
    return count
