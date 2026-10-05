"""Database Repository for Mutual Fund Schemes and Constituent Holdings.

Supports dual-binding for local SQLite and production PostgreSQL (Supabase / Render).
Complies with SEBI (Mutual Funds) Regulations, 1996 portfolio disclosure norms.
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


def save_mutual_fund_scheme(scheme: Dict[str, Any]) -> bool:
    """Inserts or updates a mutual fund scheme master record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()

    code = scheme["scheme_code"].strip().upper()
    name = scheme["scheme_name"].strip()
    amc = scheme.get("fund_house", "Generic AMC")
    cat = scheme.get("category", "Flexi Cap Fund")
    broad_cat = scheme.get("broad_category", "EQUITY").upper()
    benchmark = scheme.get("benchmark_index", "NIFTY 500 TRI")
    aum = float(scheme.get("aum_crores", 0.0))
    nav = float(scheme.get("nav", 10.0))
    ter_dir = float(scheme.get("ter_direct_pct", 0.75))
    ter_reg = float(scheme.get("ter_regular_pct", 1.50))
    ptr = float(scheme.get("portfolio_turnover_ratio_pct", 25.0))
    active_share = float(scheme.get("active_share_pct", 65.0))
    risk_grade = scheme.get("risk_grade", "Very High")
    fund_mgr = scheme.get("fund_manager", "Senior Fund Manager")
    port_date = scheme.get("last_portfolio_date", date.today().isoformat())

    meta = scheme.get("metadata", {})
    if isinstance(meta, dict):
        meta_json = json.dumps(meta)
    else:
        meta_json = str(meta)

    try:
        if use_pg:
            cursor.execute("""
                INSERT INTO mutual_fund_schemes (
                    scheme_code, scheme_name, fund_house, category, broad_category,
                    benchmark_index, aum_crores, nav, ter_direct_pct, ter_regular_pct,
                    portfolio_turnover_ratio_pct, active_share_pct, risk_grade,
                    fund_manager, metadata_json, last_portfolio_date, last_updated
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, now()
                )
                ON CONFLICT (scheme_code) DO UPDATE SET
                    scheme_name = EXCLUDED.scheme_name,
                    fund_house = EXCLUDED.fund_house,
                    category = EXCLUDED.category,
                    broad_category = EXCLUDED.broad_category,
                    benchmark_index = EXCLUDED.benchmark_index,
                    aum_crores = EXCLUDED.aum_crores,
                    nav = EXCLUDED.nav,
                    ter_direct_pct = EXCLUDED.ter_direct_pct,
                    ter_regular_pct = EXCLUDED.ter_regular_pct,
                    portfolio_turnover_ratio_pct = EXCLUDED.portfolio_turnover_ratio_pct,
                    active_share_pct = EXCLUDED.active_share_pct,
                    risk_grade = EXCLUDED.risk_grade,
                    fund_manager = EXCLUDED.fund_manager,
                    metadata_json = EXCLUDED.metadata_json,
                    last_portfolio_date = EXCLUDED.last_portfolio_date,
                    last_updated = now();
            """, (
                code, name, amc, cat, broad_cat,
                benchmark, aum, nav, ter_dir, ter_reg,
                ptr, active_share, risk_grade,
                fund_mgr, meta_json, port_date
            ))
        else:
            cursor.execute("""
                INSERT INTO mutual_fund_schemes (
                    scheme_code, scheme_name, fund_house, category, broad_category,
                    benchmark_index, aum_crores, nav, ter_direct_pct, ter_regular_pct,
                    portfolio_turnover_ratio_pct, active_share_pct, risk_grade,
                    fund_manager, metadata_json, last_portfolio_date, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT (scheme_code) DO UPDATE SET
                    scheme_name = excluded.scheme_name,
                    fund_house = excluded.fund_house,
                    category = excluded.category,
                    broad_category = excluded.broad_category,
                    benchmark_index = excluded.benchmark_index,
                    aum_crores = excluded.aum_crores,
                    nav = excluded.nav,
                    ter_direct_pct = excluded.ter_direct_pct,
                    ter_regular_pct = excluded.ter_regular_pct,
                    portfolio_turnover_ratio_pct = excluded.portfolio_turnover_ratio_pct,
                    active_share_pct = excluded.active_share_pct,
                    risk_grade = excluded.risk_grade,
                    fund_manager = excluded.fund_manager,
                    metadata_json = excluded.metadata_json,
                    last_portfolio_date = excluded.last_portfolio_date,
                    last_updated = datetime('now');
            """, (
                code, name, amc, cat, broad_cat,
                benchmark, aum, nav, ter_dir, ter_reg,
                ptr, active_share, risk_grade,
                fund_mgr, meta_json, port_date
            ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving mutual fund scheme {code}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def save_mutual_fund_holdings(scheme_code: str, holdings: List[Dict[str, Any]]) -> bool:
    """Replaces or saves the portfolio constituents for a mutual fund scheme."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()
    clean_code = scheme_code.strip().upper()

    try:
        # Delete existing holdings for this scheme to refresh with newest disclosure
        if use_pg:
            cursor.execute("DELETE FROM mutual_fund_holdings WHERE scheme_code = %s;", (clean_code,))
        else:
            cursor.execute("DELETE FROM mutual_fund_holdings WHERE scheme_code = ?;", (clean_code,))

        for h in holdings:
            h_type = h.get("holding_type", "EQUITY").upper()
            ident = h.get("identifier", "").strip().upper()
            name = h.get("holding_name", ident)
            weight = float(h.get("weight_pct", 0.0))
            sector = h.get("sector_or_rating", "Diversified")
            port_date = h.get("portfolio_date", date.today().isoformat())
            det = h.get("instrument_details", {})
            det_json = json.dumps(det) if isinstance(det, dict) else str(det)

            if use_pg:
                cursor.execute("""
                    INSERT INTO mutual_fund_holdings (
                        scheme_code, holding_type, identifier, holding_name,
                        weight_pct, sector_or_rating, instrument_details, portfolio_date
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """, (clean_code, h_type, ident, name, weight, sector, det_json, port_date))
            else:
                cursor.execute("""
                    INSERT INTO mutual_fund_holdings (
                        scheme_code, holding_type, identifier, holding_name,
                        weight_pct, sector_or_rating, instrument_details, portfolio_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (clean_code, h_type, ident, name, weight, sector, det_json, port_date))

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving holdings for scheme {clean_code}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_mutual_fund_scheme(scheme_code: str) -> Optional[Dict[str, Any]]:
    """Fetches a single mutual fund scheme record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()
    clean_code = scheme_code.strip().upper()

    try:
        sql = "SELECT * FROM mutual_fund_schemes WHERE scheme_code = %s" if use_pg else "SELECT * FROM mutual_fund_schemes WHERE scheme_code = ?"
        cursor.execute(sql, (clean_code,))
        row = cursor.fetchone()
        if not row:
            return None
        return clean_dict_row(cursor, row)
    except Exception as e:
        logger.error(f"Error getting mutual fund scheme {clean_code}: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_active_mutual_funds(
    category: Optional[str] = None,
    broad_category: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Retrieves active mutual fund schemes filtered by category."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()

    clauses = []
    params = []

    if category:
        clauses.append("category = %s" if use_pg else "category = ?")
        params.append(category.strip())
    if broad_category:
        clauses.append("broad_category = %s" if use_pg else "broad_category = ?")
        params.append(broad_category.strip().upper())

    where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM mutual_fund_schemes {where_str} ORDER BY aum_crores DESC LIMIT {limit}"

    try:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        return [clean_dict_row(cursor, r) for r in rows]
    except Exception as e:
        logger.error(f"Error querying active mutual funds: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_scheme_holdings(scheme_code: str) -> List[Dict[str, Any]]:
    """Fetches all granular portfolio constituents for a mutual fund scheme sorted by weight."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()
    clean_code = scheme_code.strip().upper()

    try:
        sql = """
            SELECT * FROM mutual_fund_holdings
            WHERE scheme_code = %s
            ORDER BY weight_pct DESC
        """ if use_pg else """
            SELECT * FROM mutual_fund_holdings
            WHERE scheme_code = ?
            ORDER BY weight_pct DESC
        """
        cursor.execute(sql, (clean_code,))
        rows = cursor.fetchall()
        results = [clean_dict_row(cursor, r) for r in rows]
        for r in results:
            if "instrument_details" in r and isinstance(r["instrument_details"], str):
                try:
                    r["details"] = json.loads(r["instrument_details"])
                except Exception:
                    r["details"] = {}
            else:
                r["details"] = {}
        return results
    except Exception as e:
        logger.error(f"Error getting holdings for scheme {clean_code}: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_schemes_by_holding(identifier: str) -> List[Dict[str, Any]]:
    """Reverse Look-Through: finds which mutual funds hold a specific stock ticker or bond ISIN."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()
    clean_id = identifier.strip().upper()

    try:
        sql = """
            SELECT h.scheme_code, s.scheme_name, s.category, s.broad_category,
                   h.holding_type, h.weight_pct, h.portfolio_date, s.aum_crores
            FROM mutual_fund_holdings h
            JOIN mutual_fund_schemes s ON h.scheme_code = s.scheme_code
            WHERE h.identifier = %s
            ORDER BY h.weight_pct DESC
        """ if use_pg else """
            SELECT h.scheme_code, s.scheme_name, s.category, s.broad_category,
                   h.holding_type, h.weight_pct, h.portfolio_date, s.aum_crores
            FROM mutual_fund_holdings h
            JOIN mutual_fund_schemes s ON h.scheme_code = s.scheme_code
            WHERE h.identifier = ?
            ORDER BY h.weight_pct DESC
        """
        cursor.execute(sql, (clean_id,))
        rows = cursor.fetchall()
        return [clean_dict_row(cursor, r) for r in rows]
    except Exception as e:
        logger.error(f"Error reverse-querying schemes for holding {clean_id}: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def seed_default_mutual_funds() -> int:
    """Seeds canonical benchmark Indian Mutual Funds representing all major asset sleeves."""
    seeded = 0

    schemes = [
        {
            "scheme_code": "PPFAS_FLEXICAP_DIR",
            "scheme_name": "Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
            "fund_house": "PPFAS Mutual Fund",
            "category": "Flexi Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 500 TRI",
            "aum_crores": 74200.0,
            "nav": 84.62,
            "ter_direct_pct": 0.62,
            "ter_regular_pct": 1.33,
            "portfolio_turnover_ratio_pct": 18.2,
            "active_share_pct": 76.5,
            "risk_grade": "Very High",
            "fund_manager": "Rajeev Thakkar / Raunak Onkar",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 88.5,
                "sortino_ratio": 2.15,
                "downside_capture_ratio": 64.2,
                "upside_capture_ratio": 104.5,
                "hurst_exponent": 0.68,
                "top_10_weight_pct": 53.8,
                "asset_allocation": {"equity": 68.5, "foreign_equity": 15.5, "debt_cash": 16.0}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 8.4, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 6.8, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "ITC", "holding_name": "ITC Ltd", "weight_pct": 6.2, "sector_or_rating": "FMCG"},
                {"holding_type": "EQUITY", "identifier": "BAJFINANCE", "holding_name": "Bajaj Finance Ltd", "weight_pct": 5.9, "sector_or_rating": "NBFC"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 5.4, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "TCS", "holding_name": "Tata Consultancy Services", "weight_pct": 4.8, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 4.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "AXISBANK", "holding_name": "Axis Bank Ltd", "weight_pct": 4.1, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "HCLTECH", "holding_name": "HCL Technologies Ltd", "weight_pct": 3.9, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "MARUTI", "holding_name": "Maruti Suzuki India", "weight_pct": 3.8, "sector_or_rating": "Automobiles"},
                {"holding_type": "FOREIGN_EQUITY", "identifier": "GOOGL", "holding_name": "Alphabet Inc (Google)", "weight_pct": 4.8, "sector_or_rating": "US Tech"},
                {"holding_type": "FOREIGN_EQUITY", "identifier": "MSFT", "holding_name": "Microsoft Corp", "weight_pct": 4.5, "sector_or_rating": "US Tech"},
                {"holding_type": "FOREIGN_EQUITY", "identifier": "META", "holding_name": "Meta Platforms Inc", "weight_pct": 3.6, "sector_or_rating": "US Tech"},
                {"holding_type": "FOREIGN_EQUITY", "identifier": "AMZN", "holding_name": "Amazon.com Inc", "weight_pct": 2.6, "sector_or_rating": "US Consumer Tech"},
                {"holding_type": "DEBT", "identifier": "IN0020230085", "holding_name": "7.18% Central Government Sovereign G-Sec 2033", "weight_pct": 9.5, "sector_or_rating": "SOVEREIGN", "instrument_details": {"ytm": 7.08, "duration": 6.8}},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Tri-Party Repo (TREPS) & Cash Margin", "weight_pct": 6.5, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "HDFC_MIDCAP_DIR",
            "scheme_name": "HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth",
            "fund_house": "HDFC Mutual Fund",
            "category": "Mid Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY Midcap 150 TRI",
            "aum_crores": 71800.0,
            "nav": 194.20,
            "ter_direct_pct": 0.78,
            "ter_regular_pct": 1.62,
            "portfolio_turnover_ratio_pct": 24.5,
            "active_share_pct": 72.1,
            "risk_grade": "Very High",
            "fund_manager": "Chirag Setalvad",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 82.0,
                "sortino_ratio": 1.95,
                "downside_capture_ratio": 68.5,
                "upside_capture_ratio": 108.2,
                "hurst_exponent": 0.65,
                "top_10_weight_pct": 36.4,
                "asset_allocation": {"equity": 93.5, "debt_cash": 6.5}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "TATACOMM", "holding_name": "Tata Communications Ltd", "weight_pct": 4.6, "sector_or_rating": "Telecom Services"},
                {"holding_type": "EQUITY", "identifier": "BHARATFORG", "holding_name": "Bharat Forge Ltd", "weight_pct": 4.2, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "MAXHEALTH", "holding_name": "Max Healthcare Institute", "weight_pct": 3.9, "sector_or_rating": "Healthcare Services"},
                {"holding_type": "EQUITY", "identifier": "COFORGE", "holding_name": "Coforge Ltd", "weight_pct": 3.7, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "FEDERALBNK", "holding_name": "Federal Bank Ltd", "weight_pct": 3.5, "sector_or_rating": "Banks"},
                {"holding_type": "EQUITY", "identifier": "ASTRAL", "holding_name": "Astral Ltd", "weight_pct": 3.4, "sector_or_rating": "Building Products"},
                {"holding_type": "EQUITY", "identifier": "SUPRAJIT", "holding_name": "Suprajit Engineering Ltd", "weight_pct": 3.1, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "APOLLOTYRE", "holding_name": "Apollo Tyres Ltd", "weight_pct": 2.9, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "AUROPHARMA", "holding_name": "Aurobindo Pharma Ltd", "weight_pct": 2.7, "sector_or_rating": "Pharmaceuticals"},
                {"holding_type": "EQUITY", "identifier": "BALKRISIND", "holding_name": "Balkrishna Industries", "weight_pct": 2.5, "sector_or_rating": "Automobiles"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Tri-Party Repo & Cash", "weight_pct": 6.5, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "MIRAE_LARGECAP_DIR",
            "scheme_name": "Mirae Asset Large Cap Fund - Direct Plan - Growth",
            "fund_house": "Mirae Asset Mutual Fund",
            "category": "Large Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 100 TRI",
            "aum_crores": 38400.0,
            "nav": 112.50,
            "ter_direct_pct": 0.54,
            "ter_regular_pct": 1.48,
            "portfolio_turnover_ratio_pct": 42.0,
            "active_share_pct": 52.4,
            "risk_grade": "Very High",
            "fund_manager": "Gaurav Misra",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 64.0,
                "sortino_ratio": 1.42,
                "downside_capture_ratio": 84.5,
                "upside_capture_ratio": 96.0,
                "hurst_exponent": 0.52,
                "top_10_weight_pct": 58.2,
                "asset_allocation": {"equity": 98.2, "debt_cash": 1.8}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 9.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 9.2, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 8.6, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 7.4, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "TCS", "holding_name": "Tata Consultancy Services", "weight_pct": 5.2, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "LT", "holding_name": "Larsen & Toubro Ltd", "weight_pct": 4.9, "sector_or_rating": "Infrastructure"},
                {"holding_type": "EQUITY", "identifier": "ITC", "holding_name": "ITC Ltd", "weight_pct": 4.5, "sector_or_rating": "FMCG"},
                {"holding_type": "EQUITY", "identifier": "AXISBANK", "holding_name": "Axis Bank Ltd", "weight_pct": 3.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "SBIN", "holding_name": "State Bank of India", "weight_pct": 3.5, "sector_or_rating": "PSU Banks"},
                {"holding_type": "EQUITY", "identifier": "BHARTIARTL", "holding_name": "Bharti Airtel Ltd", "weight_pct": 3.4, "sector_or_rating": "Telecom"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Net Cash & Call Money", "weight_pct": 1.8, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "SBI_SMALLCAP_DIR",
            "scheme_name": "SBI Small Cap Fund - Direct Plan - Growth",
            "fund_house": "SBI Mutual Fund",
            "category": "Small Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "BSE 250 SmallCap TRI",
            "aum_crores": 31200.0,
            "nav": 168.40,
            "ter_direct_pct": 0.72,
            "ter_regular_pct": 1.58,
            "portfolio_turnover_ratio_pct": 16.0,
            "active_share_pct": 84.5,
            "risk_grade": "Very High",
            "fund_manager": "R. Srinivasan",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 91.0,
                "sortino_ratio": 2.38,
                "downside_capture_ratio": 59.0,
                "upside_capture_ratio": 102.5,
                "hurst_exponent": 0.72,
                "top_10_weight_pct": 32.5,
                "asset_allocation": {"equity": 89.2, "debt_cash": 10.8}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "PRINCEPIPE", "holding_name": "Prince Pipes and Fittings", "weight_pct": 3.9, "sector_or_rating": "Building Products"},
                {"holding_type": "EQUITY", "identifier": "WENDT", "holding_name": "Wendt India Ltd", "weight_pct": 3.6, "sector_or_rating": "Industrial Machinery"},
                {"holding_type": "EQUITY", "identifier": "ELECON", "holding_name": "Elecon Engineering Ltd", "weight_pct": 3.4, "sector_or_rating": "Heavy Electricals"},
                {"holding_type": "EQUITY", "identifier": "NEULANDLAB", "holding_name": "Neuland Laboratories Ltd", "weight_pct": 3.2, "sector_or_rating": "Pharma Active Ingredients"},
                {"holding_type": "EQUITY", "identifier": "DYNAMATECH", "holding_name": "Dynamatic Technologies", "weight_pct": 3.1, "sector_or_rating": "Aerospace & Defense"},
                {"holding_type": "EQUITY", "identifier": "GENSOL", "holding_name": "Gensol Engineering Ltd", "weight_pct": 2.8, "sector_or_rating": "Clean Energy EPC"},
                {"holding_type": "EQUITY", "identifier": "INOXGREEN", "holding_name": "Inox Green Energy Services", "weight_pct": 2.5, "sector_or_rating": "Renewable Power"},
                {"holding_type": "EQUITY", "identifier": "SUPRAJIT", "holding_name": "Suprajit Engineering Ltd", "weight_pct": 2.4, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Cash & Sovereign Margin", "weight_pct": 10.8, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "ICICI_BAF_DIR",
            "scheme_name": "ICICI Prudential Balanced Advantage Fund - Direct Plan - Growth",
            "fund_house": "ICICI Prudential Mutual Fund",
            "category": "Balanced Advantage Fund",
            "broad_category": "HYBRID",
            "benchmark_index": "NIFTY 50 Hybrid Composite Debt 50:50 Index",
            "aum_crores": 59500.0,
            "nav": 72.85,
            "ter_direct_pct": 0.88,
            "ter_regular_pct": 1.68,
            "portfolio_turnover_ratio_pct": 82.0,
            "active_share_pct": 62.0,
            "risk_grade": "Moderately High",
            "fund_manager": "Sankaran Naren",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 86.0,
                "sortino_ratio": 2.05,
                "downside_capture_ratio": 54.0,
                "upside_capture_ratio": 78.5,
                "hurst_exponent": 0.62,
                "top_10_weight_pct": 44.5,
                "asset_allocation": {"net_equity": 42.5, "hedged_derivatives": 23.5, "debt": 24.5, "cash": 9.5}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 7.2, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 6.1, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 5.8, "sector_or_rating": "Energy & Conglomerate"},
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 5.4, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "BHARTIARTL", "holding_name": "Bharti Airtel Ltd", "weight_pct": 4.2, "sector_or_rating": "Telecom"},
                {"holding_type": "DEBT", "identifier": "INE002A08012", "holding_name": "Reliance Industries 8.65% Secured NCD 2028", "weight_pct": 7.5, "sector_or_rating": "CRISIL AAA", "instrument_details": {"ytm": 8.65, "duration": 1.53, "seniority": "SENIOR_SECURED"}},
                {"holding_type": "DEBT", "identifier": "INE306N07MM3", "holding_name": "Tata Capital Financial Services 8.85% Secured NCD 2027", "weight_pct": 6.8, "sector_or_rating": "CRISIL AAA", "instrument_details": {"ytm": 8.85, "duration": 1.48, "seniority": "SENIOR_SECURED"}},
                {"holding_type": "DEBT", "identifier": "INE040A08377", "holding_name": "HDFC Bank 7.95% Subordinated Tier-II Bond 2033", "weight_pct": 5.2, "sector_or_rating": "CRISIL AAA", "instrument_details": {"ytm": 7.95, "duration": 5.42, "seniority": "SUBORDINATED_TIER_2"}},
                {"holding_type": "DEBT", "identifier": "INE414G07GE7", "holding_name": "Muthoot Finance 9.15% Secured Gold NCD 2026", "weight_pct": 5.0, "sector_or_rating": "CRISIL AA+", "instrument_details": {"ytm": 9.15, "duration": 0.88, "seniority": "SENIOR_SECURED"}},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "TREPS Repo & Margin Reserves", "weight_pct": 9.5, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "ABSL_CORPBOND_DIR",
            "scheme_name": "Aditya Birla Sun Life Corporate Bond Fund - Direct Plan - Growth",
            "fund_house": "Aditya Birla Sun Life Mutual Fund",
            "category": "Corporate Bond Fund",
            "broad_category": "DEBT",
            "benchmark_index": "CRISIL Corporate Bond Index",
            "aum_crores": 22100.0,
            "nav": 108.95,
            "ter_direct_pct": 0.32,
            "ter_regular_pct": 0.78,
            "portfolio_turnover_ratio_pct": 55.0,
            "active_share_pct": 58.0,
            "risk_grade": "Moderate",
            "fund_manager": "Kaustubh Gupta",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 94.0,
                "sortino_ratio": 2.85,
                "downside_capture_ratio": 32.0,
                "upside_capture_ratio": 95.0,
                "hurst_exponent": 0.61,
                "top_10_weight_pct": 68.5,
                "asset_allocation": {"corporate_debt": 84.5, "sovereign_gsec": 12.0, "cash": 3.5}
            },
            "holdings": [
                {"holding_type": "DEBT", "identifier": "INE002A08012", "holding_name": "Reliance Industries 8.65% Secured NCD 2028", "weight_pct": 9.5, "sector_or_rating": "CRISIL AAA", "instrument_details": {"ytm": 8.65, "duration": 1.53, "seniority": "SENIOR_SECURED"}},
                {"holding_type": "DEBT", "identifier": "INE306N07MM3", "holding_name": "Tata Capital Financial Services 8.85% Secured NCD 2027", "weight_pct": 9.0, "sector_or_rating": "CRISIL AAA", "instrument_details": {"ytm": 8.85, "duration": 1.48, "seniority": "SENIOR_SECURED"}},
                {"holding_type": "DEBT", "identifier": "INE040A08377", "holding_name": "HDFC Bank 7.95% Subordinated Tier-II Bond 2033", "weight_pct": 8.5, "sector_or_rating": "CRISIL AAA", "instrument_details": {"ytm": 7.95, "duration": 5.42, "seniority": "SUBORDINATED_TIER_2"}},
                {"holding_type": "DEBT", "identifier": "INE414G07GE7", "holding_name": "Muthoot Finance 9.15% Secured Gold NCD 2026", "weight_pct": 7.5, "sector_or_rating": "CRISIL AA+", "instrument_details": {"ytm": 9.15, "duration": 0.88, "seniority": "SENIOR_SECURED"}},
                {"holding_type": "DEBT", "identifier": "IN901SDI0012", "holding_name": "Vivriti Gold Loan Receivables Series I SDI", "weight_pct": 4.5, "sector_or_rating": "CRISIL BBB+", "instrument_details": {"ytm": 10.25, "duration": 1.15, "seniority": "SECURITIZED_DEBT_INSTRUMENT"}},
                {"holding_type": "DEBT", "identifier": "IN0020230085", "holding_name": "7.18% Central Government Sovereign G-Sec 2033", "weight_pct": 12.0, "sector_or_rating": "SOVEREIGN", "instrument_details": {"ytm": 7.08, "duration": 6.8}},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Collateralized Borrowing & Lending / TREPS", "weight_pct": 3.5, "sector_or_rating": "CASH"}
            ]
        }
    ]

    for s in schemes:
        holdings = s.pop("holdings", [])
        if save_mutual_fund_scheme(s):
            save_mutual_fund_holdings(s["scheme_code"], holdings)
            seeded += 1

    return seeded
