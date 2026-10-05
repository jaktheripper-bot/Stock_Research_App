"""Database Repository for Corporate Debt, NCDs, SDIs, and Credit Rating Events.

Supports dual-binding for both local SQLite and production PostgreSQL (Supabase / Render).
Complies with SEBI (Issue and Listing of Non-Convertible Securities) Regulations.
"""

import json
import logging
from decimal import Decimal
from datetime import datetime, date, timezone
from typing import Optional, List, Dict, Any

from core.db.connection import get_db_connection, get_supabase_url

def is_supabase_enabled() -> bool:
    return bool(get_supabase_url())

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
    use_pg = is_supabase_enabled()

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
    use_pg = is_supabase_enabled()
    clean_isin = isin.strip().upper()

    try:
        sql = "SELECT * FROM corporate_debt_securities WHERE isin = %s" if use_pg else "SELECT * FROM corporate_debt_securities WHERE isin = ?"
        cursor.execute(sql, (clean_isin,))
        row = cursor.fetchone()
        return clean_dict_row(cursor, row) if row else None
    except Exception as e:
        logger.error(f"Error getting debt security {clean_isin}: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_debt_securities_by_ticker(ticker: str) -> List[Dict[str, Any]]:
    """Retrieves all debt securities issued by a given company ticker."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()
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

def get_active_debt_securities(
    seniority: Optional[str] = None,
    instrument_type: Optional[str] = None,
    min_rating: Optional[str] = None,
    is_sdi: Optional[bool] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Retrieves active debt securities filtered by seniority, rating, and instrument type."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()

    clauses = ["is_listed = TRUE" if use_pg else "is_listed = 1"]
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
    sql = f"SELECT * FROM corporate_debt_securities WHERE {where_str} ORDER BY ytm_pct DESC LIMIT {limit}"

    try:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        results = [clean_dict_row(cursor, r) for r in rows]
        if min_rating:
            target_weight = RATING_TIER_ORDER.get(min_rating.strip().upper(), 1)
            results = [
                r for r in results
                if RATING_TIER_ORDER.get(r.get("credit_rating", "").replace("CRISIL ", "").replace("ICRA ", "").replace("CARE ", "").strip(), 0) >= target_weight
            ]
        return results
    except Exception as e:
        logger.error(f"Error querying active debt securities: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def record_rating_event(event: Dict[str, Any]) -> bool:
    """Records a Credit Rating Agency action (upgrade, downgrade, watch, affirmation)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()

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
    use_pg = is_supabase_enabled()
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
    use_pg = is_supabase_enabled()

    try:
        sql = f"SELECT * FROM credit_rating_events ORDER BY event_date DESC LIMIT {limit}"
        cursor.execute(sql)
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
    Seeds a representative universe of democratized Indian corporate bonds,
    NCDs, and SDIs (under SEBI's ₹10,000 face value framework) for benchmarking.
    """
    seeds = [
        {
            "isin": "INE002A08012",
            "ticker": "RELIANCE",
            "scrip_code": "935001",
            "series": "N1",
            "instrument_name": "Reliance Industries 8.65% Secured NCD 2028",
            "instrument_type": "NCD",
            "seniority_tier": "SENIOR_SECURED",
            "face_value": 10000.0,
            "coupon_rate_pct": 8.65,
            "coupon_frequency": "ANNUAL",
            "issue_date": "2023-04-15",
            "maturity_date": "2028-04-15",
            "credit_rating": "CRISIL AAA",
            "credit_rating_agency": "CRISIL",
            "asset_cover_ratio": 1.45,
            "is_listed": True,
            "exchange": "BSE",
            "is_sdi": False,
            "originator": None,
            "fldg_pct": 0.0,
            "last_traded_price": 10150.0,
            "ytm_pct": 8.25,
            "macaulay_duration_years": 2.25,
            "modified_duration_years": 2.08,
            "metadata": {
                "sector": "Conglomerate",
                "interest_payment_month": "April",
                "record_date_days": 15
            }
        },
        {
            "isin": "INE306N07MM3",
            "ticker": "TATACAP",
            "scrip_code": "936102",
            "series": "N2",
            "instrument_name": "Tata Capital Financial Services 8.85% Senior Secured NCD 2027",
            "instrument_type": "NCD",
            "seniority_tier": "SENIOR_SECURED",
            "face_value": 10000.0,
            "coupon_rate_pct": 8.85,
            "coupon_frequency": "ANNUAL",
            "issue_date": "2023-09-01",
            "maturity_date": "2027-09-01",
            "credit_rating": "CRISIL AAA",
            "credit_rating_agency": "CRISIL",
            "asset_cover_ratio": 1.30,
            "is_listed": True,
            "exchange": "BSE",
            "is_sdi": False,
            "originator": None,
            "fldg_pct": 0.0,
            "last_traded_price": 10080.0,
            "ytm_pct": 8.52,
            "macaulay_duration_years": 1.82,
            "modified_duration_years": 1.68,
            "metadata": {
                "sector": "Financial Services (NBFC)",
                "interest_payment_month": "September"
            }
        },
        {
            "isin": "INE414G07GE7",
            "ticker": "MUTHOOTFIN",
            "scrip_code": "937210",
            "series": "N4",
            "instrument_name": "Muthoot Finance 9.15% Senior Secured Gold Loan Backed NCD 2026",
            "instrument_type": "NCD",
            "seniority_tier": "SENIOR_SECURED",
            "face_value": 10000.0,
            "coupon_rate_pct": 9.15,
            "coupon_frequency": "ANNUAL",
            "issue_date": "2023-01-10",
            "maturity_date": "2026-07-10",
            "credit_rating": "ICRA AA+",
            "credit_rating_agency": "ICRA",
            "asset_cover_ratio": 1.35,
            "is_listed": True,
            "exchange": "BSE",
            "is_sdi": False,
            "originator": None,
            "fldg_pct": 0.0,
            "last_traded_price": 10040.0,
            "ytm_pct": 8.92,
            "macaulay_duration_years": 0.74,
            "modified_duration_years": 0.68,
            "metadata": {
                "sector": "Gold Loan NBFC",
                "collateral_type": "Physical Gold Bullion Pledge"
            }
        },
        {
            "isin": "INE040A08377",
            "ticker": "HDFCBANK",
            "scrip_code": "938330",
            "series": "T2",
            "instrument_name": "HDFC Bank 7.95% Subordinated Tier-II Non-Convertible Bond 2033",
            "instrument_type": "Subordinated Tier-II",
            "seniority_tier": "SUBORDINATED_TIER_2",
            "face_value": 10000.0,
            "coupon_rate_pct": 7.95,
            "coupon_frequency": "ANNUAL",
            "issue_date": "2023-08-18",
            "maturity_date": "2033-08-18",
            "credit_rating": "CRISIL AAA",
            "credit_rating_agency": "CRISIL",
            "asset_cover_ratio": 1.0,
            "is_listed": True,
            "exchange": "NSE",
            "is_sdi": False,
            "originator": None,
            "fldg_pct": 0.0,
            "last_traded_price": 9980.0,
            "ytm_pct": 7.98,
            "macaulay_duration_years": 5.40,
            "modified_duration_years": 5.00,
            "metadata": {
                "sector": "Private Sector Banking",
                "regulatory_capital": "Tier-II Capital",
                "loss_absorption": "Subordinated to depositors and senior creditors"
            }
        },
        {
            "isin": "INE090A08UD5",
            "ticker": "INDUSINDBK",
            "scrip_code": "939015",
            "series": "AT1",
            "instrument_name": "IndusInd Bank 10.50% Additional Tier-1 Perpetual Subordinated Debt",
            "instrument_type": "Perpetual AT1",
            "seniority_tier": "PERPETUAL_AT1",
            "face_value": 10000.0,
            "coupon_rate_pct": 10.50,
            "coupon_frequency": "ANNUAL",
            "issue_date": "2021-03-24",
            "maturity_date": "2099-12-31",
            "credit_rating": "CRISIL AA",
            "credit_rating_agency": "CRISIL",
            "asset_cover_ratio": 1.0,
            "is_listed": True,
            "exchange": "BSE",
            "is_sdi": False,
            "originator": None,
            "fldg_pct": 0.0,
            "last_traded_price": 9750.0,
            "ytm_pct": 10.85,
            "macaulay_duration_years": 4.10,
            "modified_duration_years": 3.70,
            "metadata": {
                "sector": "Banking",
                "is_perpetual": True,
                "loss_absorption": "Permanent write-down or equity conversion upon PONV"
            }
        },
        {
            "isin": "IN901SDI0012",
            "ticker": "KRAZYSDI",
            "scrip_code": "939900",
            "series": "SDI-1",
            "instrument_name": "Vivriti Gold Loan Receivables Series I Securitized Debt Instrument",
            "instrument_type": "SDI",
            "seniority_tier": "SENIOR_SECURED",
            "face_value": 10000.0,
            "coupon_rate_pct": 10.25,
            "coupon_frequency": "MONTHLY",
            "issue_date": "2024-01-15",
            "maturity_date": "2025-07-15",
            "credit_rating": "ICRA A+",
            "credit_rating_agency": "ICRA",
            "asset_cover_ratio": 1.20,
            "is_listed": True,
            "exchange": "NSE",
            "is_sdi": True,
            "originator": "KrazyBee Financial Services Pvt Ltd",
            "fldg_pct": 5.0,
            "last_traded_price": 10000.0,
            "ytm_pct": 10.25,
            "macaulay_duration_years": 0.72,
            "modified_duration_years": 0.65,
            "metadata": {
                "sector": "Securitized Retail Debt",
                "pool_size_cr": 45.0,
                "underlying_loan_type": "Secured Digital Gold & Consumer Loans",
                "fldg_mechanism": "Cash collateral deposit with Trustee"
            }
        }
    ]

    count = 0
    for s in seeds:
        if save_debt_security(s):
            count += 1
            # Add initial rating event
            record_rating_event({
                "isin": s["isin"],
                "ticker": s["ticker"],
                "rating_agency": s["credit_rating_agency"],
                "rating_symbol": s["credit_rating"].replace("CRISIL ", "").replace("ICRA ", "").replace("CARE ", "").strip(),
                "outlook": "STABLE",
                "action_type": "AFFIRMED",
                "event_date": s["issue_date"],
                "action_rationale": f"Initial rating assigned upon listing on {s['exchange']} debt segment."
            })
    logger.info(f"Seeded {count} benchmark corporate debt securities.")
    return count
