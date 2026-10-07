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


get_mutual_fund_by_code = get_mutual_fund_scheme



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
        },
        {
            "scheme_code": "HDFC_FLEXICAP_DIR",
            "scheme_name": "HDFC Flexi Cap Fund - Direct Plan - Growth",
            "fund_house": "HDFC Mutual Fund",
            "category": "Flexi Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 500 TRI",
            "aum_crores": 54600.0,
            "nav": 1720.50,
            "ter_direct_pct": 0.72,
            "ter_regular_pct": 1.54,
            "portfolio_turnover_ratio_pct": 28.5,
            "active_share_pct": 68.4,
            "risk_grade": "Very High",
            "fund_manager": "Roshi Jain",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 84.5,
                "sortino_ratio": 2.05,
                "downside_capture_ratio": 66.0,
                "upside_capture_ratio": 106.0,
                "hurst_exponent": 0.64,
                "top_10_weight_pct": 52.5,
                "asset_allocation": {"equity": 93.0, "debt_cash": 7.0}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 9.2, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 8.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 6.5, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "AXISBANK", "holding_name": "Axis Bank Ltd", "weight_pct": 5.2, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 4.9, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "BHARTIARTL", "holding_name": "Bharti Airtel Ltd", "weight_pct": 4.5, "sector_or_rating": "Telecom"},
                {"holding_type": "EQUITY", "identifier": "SBIN", "holding_name": "State Bank of India", "weight_pct": 4.1, "sector_or_rating": "PSU Banks"},
                {"holding_type": "EQUITY", "identifier": "LT", "holding_name": "Larsen & Toubro Ltd", "weight_pct": 3.8, "sector_or_rating": "Infrastructure"},
                {"holding_type": "EQUITY", "identifier": "HINDUNILVR", "holding_name": "Hindustan Unilever Ltd", "weight_pct": 3.2, "sector_or_rating": "FMCG"},
                {"holding_type": "EQUITY", "identifier": "CIPLA", "holding_name": "Cipla Ltd", "weight_pct": 2.8, "sector_or_rating": "Pharmaceuticals"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Tri-Party Repo & Cash", "weight_pct": 7.0, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "KOTAK_FLEXICAP_DIR",
            "scheme_name": "Kotak Flexicap Fund - Direct Plan - Growth",
            "fund_house": "Kotak Mutual Fund",
            "category": "Flexi Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 500 TRI",
            "aum_crores": 48200.0,
            "nav": 84.10,
            "ter_direct_pct": 0.68,
            "ter_regular_pct": 1.48,
            "portfolio_turnover_ratio_pct": 22.0,
            "active_share_pct": 66.0,
            "risk_grade": "Very High",
            "fund_manager": "Harsha Upadhyaya",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 81.0,
                "sortino_ratio": 1.88,
                "downside_capture_ratio": 72.0,
                "upside_capture_ratio": 98.0,
                "hurst_exponent": 0.58,
                "top_10_weight_pct": 48.0,
                "asset_allocation": {"equity": 90.2, "debt_cash": 9.8}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 8.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 7.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 6.2, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 5.5, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "LT", "holding_name": "Larsen & Toubro Ltd", "weight_pct": 4.9, "sector_or_rating": "Infrastructure"},
                {"holding_type": "EQUITY", "identifier": "TCS", "holding_name": "Tata Consultancy Services", "weight_pct": 4.2, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "MARUTI", "holding_name": "Maruti Suzuki India", "weight_pct": 3.8, "sector_or_rating": "Automobiles"},
                {"holding_type": "EQUITY", "identifier": "TITAN", "holding_name": "Titan Company Ltd", "weight_pct": 3.1, "sector_or_rating": "Consumer Goods"},
                {"holding_type": "EQUITY", "identifier": "BHARATFORG", "holding_name": "Bharat Forge Ltd", "weight_pct": 2.8, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Tri-Party Repo & Cash", "weight_pct": 9.8, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "ICICI_BLUECHIP_DIR",
            "scheme_name": "ICICI Prudential Bluechip Fund - Direct Plan - Growth",
            "fund_house": "ICICI Prudential Mutual Fund",
            "category": "Large Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 100 TRI",
            "aum_crores": 55200.0,
            "nav": 104.25,
            "ter_direct_pct": 0.89,
            "ter_regular_pct": 1.62,
            "portfolio_turnover_ratio_pct": 36.0,
            "active_share_pct": 54.2,
            "risk_grade": "Very High",
            "fund_manager": "Anish Tawakley",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 78.0,
                "sortino_ratio": 1.75,
                "downside_capture_ratio": 76.0,
                "upside_capture_ratio": 94.0,
                "hurst_exponent": 0.55,
                "top_10_weight_pct": 56.5,
                "asset_allocation": {"equity": 91.2, "debt_cash": 8.8}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 9.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 9.1, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 8.9, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 7.6, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "LT", "holding_name": "Larsen & Toubro Ltd", "weight_pct": 5.8, "sector_or_rating": "Infrastructure"},
                {"holding_type": "EQUITY", "identifier": "TCS", "holding_name": "Tata Consultancy Services", "weight_pct": 4.9, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "AXISBANK", "holding_name": "Axis Bank Ltd", "weight_pct": 4.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "BHARTIARTL", "holding_name": "Bharti Airtel Ltd", "weight_pct": 4.2, "sector_or_rating": "Telecom"},
                {"holding_type": "EQUITY", "identifier": "MARUTI", "holding_name": "Maruti Suzuki India", "weight_pct": 3.5, "sector_or_rating": "Automobiles"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "TREPS Margin", "weight_pct": 8.8, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "NIPPON_LARGECAP_DIR",
            "scheme_name": "Nippon India Large Cap Fund - Direct Plan - Growth",
            "fund_house": "Nippon India Mutual Fund",
            "category": "Large Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "BSE 100 TRI",
            "aum_crores": 32400.0,
            "nav": 89.40,
            "ter_direct_pct": 0.78,
            "ter_regular_pct": 1.58,
            "portfolio_turnover_ratio_pct": 32.0,
            "active_share_pct": 58.0,
            "risk_grade": "Very High",
            "fund_manager": "Sailesh Raj Bhan",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 79.5,
                "sortino_ratio": 1.82,
                "downside_capture_ratio": 74.0,
                "upside_capture_ratio": 97.0,
                "hurst_exponent": 0.56,
                "top_10_weight_pct": 54.0,
                "asset_allocation": {"equity": 87.4, "debt_cash": 12.6}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 9.6, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 8.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 7.9, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 6.5, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "ITC", "holding_name": "ITC Ltd", "weight_pct": 5.1, "sector_or_rating": "FMCG"},
                {"holding_type": "EQUITY", "identifier": "LT", "holding_name": "Larsen & Toubro Ltd", "weight_pct": 4.8, "sector_or_rating": "Infrastructure"},
                {"holding_type": "EQUITY", "identifier": "SBIN", "holding_name": "State Bank of India", "weight_pct": 4.2, "sector_or_rating": "PSU Banks"},
                {"holding_type": "EQUITY", "identifier": "AXISBANK", "holding_name": "Axis Bank Ltd", "weight_pct": 3.9, "sector_or_rating": "Private Banks"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "TREPS Reserves", "weight_pct": 12.6, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "SBI_LARGEMID_DIR",
            "scheme_name": "SBI Large & Midcap Fund - Direct Plan - Growth",
            "fund_house": "SBI Mutual Fund",
            "category": "Large & Mid Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY LargeMidcap 250 TRI",
            "aum_crores": 26800.0,
            "nav": 562.30,
            "ter_direct_pct": 0.84,
            "ter_regular_pct": 1.68,
            "portfolio_turnover_ratio_pct": 26.0,
            "active_share_pct": 69.5,
            "risk_grade": "Very High",
            "fund_manager": "Saurabh Pant",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 82.0,
                "sortino_ratio": 1.90,
                "downside_capture_ratio": 68.0,
                "upside_capture_ratio": 103.0,
                "hurst_exponent": 0.62,
                "top_10_weight_pct": 44.0,
                "asset_allocation": {"equity": 88.9, "debt_cash": 11.1}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 5.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 5.2, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 4.5, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 4.1, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "MAXHEALTH", "holding_name": "Max Healthcare Institute", "weight_pct": 3.5, "sector_or_rating": "Healthcare Services"},
                {"holding_type": "EQUITY", "identifier": "BHARATFORG", "holding_name": "Bharat Forge Ltd", "weight_pct": 3.2, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "TATACOMM", "holding_name": "Tata Communications Ltd", "weight_pct": 3.1, "sector_or_rating": "Telecom Services"},
                {"holding_type": "EQUITY", "identifier": "FEDERALBNK", "holding_name": "Federal Bank Ltd", "weight_pct": 2.9, "sector_or_rating": "Banks"},
                {"holding_type": "EQUITY", "identifier": "COFORGE", "holding_name": "Coforge Ltd", "weight_pct": 2.8, "sector_or_rating": "IT Services"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Repo Margin", "weight_pct": 11.1, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "MOTILAL_LARGEMID_DIR",
            "scheme_name": "Motilal Oswal Large and Midcap Fund - Direct Plan - Growth",
            "fund_house": "Motilal Oswal Mutual Fund",
            "category": "Large & Mid Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY LargeMidcap 250 TRI",
            "aum_crores": 12400.0,
            "nav": 42.15,
            "ter_direct_pct": 0.65,
            "ter_regular_pct": 1.45,
            "portfolio_turnover_ratio_pct": 38.0,
            "active_share_pct": 74.0,
            "risk_grade": "Very High",
            "fund_manager": "Ajay Khandelwal",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 85.0,
                "sortino_ratio": 2.10,
                "downside_capture_ratio": 70.0,
                "upside_capture_ratio": 112.0,
                "hurst_exponent": 0.65,
                "top_10_weight_pct": 46.5,
                "asset_allocation": {"equity": 84.2, "debt_cash": 15.8}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 5.2, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 4.8, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "MAXHEALTH", "holding_name": "Max Healthcare Institute", "weight_pct": 4.5, "sector_or_rating": "Healthcare Services"},
                {"holding_type": "EQUITY", "identifier": "BHARATFORG", "holding_name": "Bharat Forge Ltd", "weight_pct": 4.1, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "COFORGE", "holding_name": "Coforge Ltd", "weight_pct": 3.8, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "ASTRAL", "holding_name": "Astral Ltd", "weight_pct": 3.5, "sector_or_rating": "Building Products"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Cash Margin", "weight_pct": 15.8, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "KOTAK_EMERGING_DIR",
            "scheme_name": "Kotak Emerging Equity Fund - Direct Plan - Growth",
            "fund_house": "Kotak Mutual Fund",
            "category": "Mid Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY Midcap 150 TRI",
            "aum_crores": 45800.0,
            "nav": 128.50,
            "ter_direct_pct": 0.74,
            "ter_regular_pct": 1.58,
            "portfolio_turnover_ratio_pct": 21.0,
            "active_share_pct": 73.5,
            "risk_grade": "Very High",
            "fund_manager": "Pankaj Tibrewal",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 83.5,
                "sortino_ratio": 2.02,
                "downside_capture_ratio": 65.0,
                "upside_capture_ratio": 105.0,
                "hurst_exponent": 0.66,
                "top_10_weight_pct": 38.0,
                "asset_allocation": {"equity": 81.7, "debt_cash": 18.3}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "SUPRAJIT", "holding_name": "Suprajit Engineering Ltd", "weight_pct": 4.5, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "BHARATFORG", "holding_name": "Bharat Forge Ltd", "weight_pct": 4.2, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "ASTRAL", "holding_name": "Astral Ltd", "weight_pct": 3.9, "sector_or_rating": "Building Products"},
                {"holding_type": "EQUITY", "identifier": "MAXHEALTH", "holding_name": "Max Healthcare Institute", "weight_pct": 3.8, "sector_or_rating": "Healthcare Services"},
                {"holding_type": "EQUITY", "identifier": "COFORGE", "holding_name": "Coforge Ltd", "weight_pct": 3.5, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "FEDERALBNK", "holding_name": "Federal Bank Ltd", "weight_pct": 3.2, "sector_or_rating": "Banks"},
                {"holding_type": "EQUITY", "identifier": "BALKRISIND", "holding_name": "Balkrishna Industries", "weight_pct": 2.8, "sector_or_rating": "Automobiles"},
                {"holding_type": "EQUITY", "identifier": "APOLLOTYRE", "holding_name": "Apollo Tyres Ltd", "weight_pct": 2.7, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Cash Reserve", "weight_pct": 18.3, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "MOTILAL_MIDCAP_DIR",
            "scheme_name": "Motilal Oswal Midcap Fund - Direct Plan - Growth",
            "fund_house": "Motilal Oswal Mutual Fund",
            "category": "Mid Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY Midcap 150 TRI",
            "aum_crores": 18500.0,
            "nav": 96.80,
            "ter_direct_pct": 0.68,
            "ter_regular_pct": 1.48,
            "portfolio_turnover_ratio_pct": 34.0,
            "active_share_pct": 77.0,
            "risk_grade": "Very High",
            "fund_manager": "Niket Shah",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 87.0,
                "sortino_ratio": 2.25,
                "downside_capture_ratio": 62.0,
                "upside_capture_ratio": 114.0,
                "hurst_exponent": 0.68,
                "top_10_weight_pct": 42.0,
                "asset_allocation": {"equity": 82.8, "debt_cash": 17.2}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "MAXHEALTH", "holding_name": "Max Healthcare Institute", "weight_pct": 5.2, "sector_or_rating": "Healthcare Services"},
                {"holding_type": "EQUITY", "identifier": "COFORGE", "holding_name": "Coforge Ltd", "weight_pct": 4.8, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "BHARATFORG", "holding_name": "Bharat Forge Ltd", "weight_pct": 4.1, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "ASTRAL", "holding_name": "Astral Ltd", "weight_pct": 3.8, "sector_or_rating": "Building Products"},
                {"holding_type": "EQUITY", "identifier": "TATACOMM", "holding_name": "Tata Communications Ltd", "weight_pct": 3.5, "sector_or_rating": "Telecom Services"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Cash Margin", "weight_pct": 17.2, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "NIPPON_SMALLCAP_DIR",
            "scheme_name": "Nippon India Small Cap Fund - Direct Plan - Growth",
            "fund_house": "Nippon India Mutual Fund",
            "category": "Small Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY Smallcap 250 TRI",
            "aum_crores": 56400.0,
            "nav": 154.20,
            "ter_direct_pct": 0.69,
            "ter_regular_pct": 1.49,
            "portfolio_turnover_ratio_pct": 19.0,
            "active_share_pct": 82.0,
            "risk_grade": "Very High",
            "fund_manager": "Samir Rachh",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 89.0,
                "sortino_ratio": 2.30,
                "downside_capture_ratio": 61.0,
                "upside_capture_ratio": 107.0,
                "hurst_exponent": 0.70,
                "top_10_weight_pct": 34.0,
                "asset_allocation": {"equity": 83.2, "debt_cash": 16.8}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ELECON", "holding_name": "Elecon Engineering Ltd", "weight_pct": 3.8, "sector_or_rating": "Heavy Electricals"},
                {"holding_type": "EQUITY", "identifier": "WENDT", "holding_name": "Wendt India Ltd", "weight_pct": 3.5, "sector_or_rating": "Industrial Machinery"},
                {"holding_type": "EQUITY", "identifier": "PRINCEPIPE", "holding_name": "Prince Pipes and Fittings", "weight_pct": 3.2, "sector_or_rating": "Building Products"},
                {"holding_type": "EQUITY", "identifier": "DYNAMATECH", "holding_name": "Dynamatic Technologies", "weight_pct": 3.1, "sector_or_rating": "Aerospace & Defense"},
                {"holding_type": "EQUITY", "identifier": "NEULANDLAB", "holding_name": "Neuland Laboratories Ltd", "weight_pct": 2.9, "sector_or_rating": "Pharma Active Ingredients"},
                {"holding_type": "EQUITY", "identifier": "GENSOL", "holding_name": "Gensol Engineering Ltd", "weight_pct": 2.4, "sector_or_rating": "Clean Energy EPC"},
                {"holding_type": "EQUITY", "identifier": "INOXGREEN", "holding_name": "Inox Green Energy Services", "weight_pct": 2.2, "sector_or_rating": "Renewable Power"},
                {"holding_type": "EQUITY", "identifier": "SUPRAJIT", "holding_name": "Suprajit Engineering Ltd", "weight_pct": 2.1, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Repo Margin", "weight_pct": 16.8, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "HDFC_SMALLCAP_DIR",
            "scheme_name": "HDFC Small Cap Fund - Direct Plan - Growth",
            "fund_house": "HDFC Mutual Fund",
            "category": "Small Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "BSE 250 SmallCap TRI",
            "aum_crores": 31800.0,
            "nav": 132.40,
            "ter_direct_pct": 0.73,
            "ter_regular_pct": 1.55,
            "portfolio_turnover_ratio_pct": 18.0,
            "active_share_pct": 81.0,
            "risk_grade": "Very High",
            "fund_manager": "Chirag Setalvad",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 88.0,
                "sortino_ratio": 2.20,
                "downside_capture_ratio": 64.0,
                "upside_capture_ratio": 104.0,
                "hurst_exponent": 0.69,
                "top_10_weight_pct": 35.0,
                "asset_allocation": {"equity": 82.4, "debt_cash": 17.6}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ELECON", "holding_name": "Elecon Engineering Ltd", "weight_pct": 3.9, "sector_or_rating": "Heavy Electricals"},
                {"holding_type": "EQUITY", "identifier": "PRINCEPIPE", "holding_name": "Prince Pipes and Fittings", "weight_pct": 3.6, "sector_or_rating": "Building Products"},
                {"holding_type": "EQUITY", "identifier": "WENDT", "holding_name": "Wendt India Ltd", "weight_pct": 3.4, "sector_or_rating": "Industrial Machinery"},
                {"holding_type": "EQUITY", "identifier": "SUPRAJIT", "holding_name": "Suprajit Engineering Ltd", "weight_pct": 3.2, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "DYNAMATECH", "holding_name": "Dynamatic Technologies", "weight_pct": 3.0, "sector_or_rating": "Aerospace & Defense"},
                {"holding_type": "EQUITY", "identifier": "NEULANDLAB", "holding_name": "Neuland Laboratories Ltd", "weight_pct": 2.8, "sector_or_rating": "Pharma Active Ingredients"},
                {"holding_type": "EQUITY", "identifier": "FEDERALBNK", "holding_name": "Federal Bank Ltd", "weight_pct": 2.5, "sector_or_rating": "Banks"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Cash Margin", "weight_pct": 17.6, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "NIPPON_MULTICAP_DIR",
            "scheme_name": "Nippon India Multi Cap Fund - Direct Plan - Growth",
            "fund_house": "Nippon India Mutual Fund",
            "category": "Multi Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 500 Multicap 50:25:25 TRI",
            "aum_crores": 34500.0,
            "nav": 245.80,
            "ter_direct_pct": 0.82,
            "ter_regular_pct": 1.62,
            "portfolio_turnover_ratio_pct": 31.0,
            "active_share_pct": 71.0,
            "risk_grade": "Very High",
            "fund_manager": "Sailesh Raj Bhan",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 81.5,
                "sortino_ratio": 1.86,
                "downside_capture_ratio": 70.0,
                "upside_capture_ratio": 102.0,
                "hurst_exponent": 0.61,
                "top_10_weight_pct": 45.0,
                "asset_allocation": {"equity": 89.5, "debt_cash": 10.5}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 6.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 5.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 5.2, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "BHARATFORG", "holding_name": "Bharat Forge Ltd", "weight_pct": 3.5, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "MAXHEALTH", "holding_name": "Max Healthcare Institute", "weight_pct": 3.2, "sector_or_rating": "Healthcare Services"},
                {"holding_type": "EQUITY", "identifier": "ELECON", "holding_name": "Elecon Engineering Ltd", "weight_pct": 2.8, "sector_or_rating": "Heavy Electricals"},
                {"holding_type": "EQUITY", "identifier": "PRINCEPIPE", "holding_name": "Prince Pipes and Fittings", "weight_pct": 2.5, "sector_or_rating": "Building Products"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "TREPS Cash", "weight_pct": 10.5, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "ICICI_MULTICAP_DIR",
            "scheme_name": "ICICI Prudential Multicap Fund - Direct Plan - Growth",
            "fund_house": "ICICI Prudential Mutual Fund",
            "category": "Multi Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 500 Multicap 50:25:25 TRI",
            "aum_crores": 14200.0,
            "nav": 742.10,
            "ter_direct_pct": 0.95,
            "ter_regular_pct": 1.72,
            "portfolio_turnover_ratio_pct": 45.0,
            "active_share_pct": 68.0,
            "risk_grade": "Very High",
            "fund_manager": "Sankaran Naren",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 80.0,
                "sortino_ratio": 1.78,
                "downside_capture_ratio": 72.0,
                "upside_capture_ratio": 99.0,
                "hurst_exponent": 0.59,
                "top_10_weight_pct": 46.0,
                "asset_allocation": {"equity": 88.1, "debt_cash": 11.9}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 7.2, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 6.1, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 5.5, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "TATACOMM", "holding_name": "Tata Communications Ltd", "weight_pct": 3.6, "sector_or_rating": "Telecom Services"},
                {"holding_type": "EQUITY", "identifier": "MAXHEALTH", "holding_name": "Max Healthcare Institute", "weight_pct": 3.2, "sector_or_rating": "Healthcare Services"},
                {"holding_type": "EQUITY", "identifier": "ELECON", "holding_name": "Elecon Engineering Ltd", "weight_pct": 2.5, "sector_or_rating": "Heavy Electricals"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "TREPS Repo", "weight_pct": 11.9, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "SBI_FOCUSED_DIR",
            "scheme_name": "SBI Focused Equity Fund - Direct Plan - Growth",
            "fund_house": "SBI Mutual Fund",
            "category": "Focused Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "BSE 500 TRI",
            "aum_crores": 32900.0,
            "nav": 312.40,
            "ter_direct_pct": 0.70,
            "ter_regular_pct": 1.52,
            "portfolio_turnover_ratio_pct": 24.0,
            "active_share_pct": 72.0,
            "risk_grade": "Very High",
            "fund_manager": "Rama Iyer Srinivasan",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 83.0,
                "sortino_ratio": 1.95,
                "downside_capture_ratio": 66.0,
                "upside_capture_ratio": 101.0,
                "hurst_exponent": 0.63,
                "top_10_weight_pct": 58.0,
                "asset_allocation": {"equity": 85.8, "debt_cash": 14.2}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 9.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 8.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 7.9, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 7.2, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "TCS", "holding_name": "Tata Consultancy Services", "weight_pct": 6.5, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "BHARTIARTL", "holding_name": "Bharti Airtel Ltd", "weight_pct": 5.8, "sector_or_rating": "Telecom"},
                {"holding_type": "EQUITY", "identifier": "BAJFINANCE", "holding_name": "Bajaj Finance Ltd", "weight_pct": 5.2, "sector_or_rating": "NBFC"},
                {"holding_type": "EQUITY", "identifier": "MARUTI", "holding_name": "Maruti Suzuki India", "weight_pct": 4.9, "sector_or_rating": "Automobiles"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Cash Margin", "weight_pct": 14.2, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "HDFC_FOCUSED_DIR",
            "scheme_name": "HDFC Focused 30 Fund - Direct Plan - Growth",
            "fund_house": "HDFC Mutual Fund",
            "category": "Focused Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 500 TRI",
            "aum_crores": 12800.0,
            "nav": 198.60,
            "ter_direct_pct": 0.65,
            "ter_regular_pct": 1.48,
            "portfolio_turnover_ratio_pct": 32.0,
            "active_share_pct": 70.5,
            "risk_grade": "Very High",
            "fund_manager": "Roshi Jain",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 82.0,
                "sortino_ratio": 1.90,
                "downside_capture_ratio": 67.0,
                "upside_capture_ratio": 103.0,
                "hurst_exponent": 0.62,
                "top_10_weight_pct": 56.0,
                "asset_allocation": {"equity": 80.5, "debt_cash": 19.5}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 9.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 9.2, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "AXISBANK", "holding_name": "Axis Bank Ltd", "weight_pct": 7.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 6.9, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 6.2, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "BHARTIARTL", "holding_name": "Bharti Airtel Ltd", "weight_pct": 5.8, "sector_or_rating": "Telecom"},
                {"holding_type": "EQUITY", "identifier": "LT", "holding_name": "Larsen & Toubro Ltd", "weight_pct": 5.1, "sector_or_rating": "Infrastructure"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "TREPS Reserves", "weight_pct": 19.5, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "SBI_CONTRA_DIR",
            "scheme_name": "SBI Contra Fund - Direct Plan - Growth",
            "fund_house": "SBI Mutual Fund",
            "category": "Value / Contra Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "BSE 500 TRI",
            "aum_crores": 36500.0,
            "nav": 388.20,
            "ter_direct_pct": 0.67,
            "ter_regular_pct": 1.49,
            "portfolio_turnover_ratio_pct": 42.0,
            "active_share_pct": 78.5,
            "risk_grade": "Very High",
            "fund_manager": "Dinesh Balachandran",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 87.5,
                "sortino_ratio": 2.15,
                "downside_capture_ratio": 60.0,
                "upside_capture_ratio": 109.0,
                "hurst_exponent": 0.67,
                "top_10_weight_pct": 42.0,
                "asset_allocation": {"equity": 84.9, "debt_cash": 15.1}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "SBIN", "holding_name": "State Bank of India", "weight_pct": 6.8, "sector_or_rating": "PSU Banks"},
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 4.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "ITC", "holding_name": "ITC Ltd", "weight_pct": 4.2, "sector_or_rating": "FMCG"},
                {"holding_type": "EQUITY", "identifier": "BHARATFORG", "holding_name": "Bharat Forge Ltd", "weight_pct": 3.8, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "FEDERALBNK", "holding_name": "Federal Bank Ltd", "weight_pct": 3.4, "sector_or_rating": "Banks"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Repo Margin", "weight_pct": 15.1, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "ICICI_VALUE_DIR",
            "scheme_name": "ICICI Prudential Value Discovery Fund - Direct Plan - Growth",
            "fund_house": "ICICI Prudential Mutual Fund",
            "category": "Value / Contra Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 500 TRI",
            "aum_crores": 46200.0,
            "nav": 420.50,
            "ter_direct_pct": 0.78,
            "ter_regular_pct": 1.58,
            "portfolio_turnover_ratio_pct": 38.0,
            "active_share_pct": 74.0,
            "risk_grade": "Very High",
            "fund_manager": "Sankaran Naren",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 84.0,
                "sortino_ratio": 2.05,
                "downside_capture_ratio": 63.0,
                "upside_capture_ratio": 104.0,
                "hurst_exponent": 0.65,
                "top_10_weight_pct": 44.0,
                "asset_allocation": {"equity": 80.5, "debt_cash": 19.5}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 8.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "BHARTIARTL", "holding_name": "Bharti Airtel Ltd", "weight_pct": 6.2, "sector_or_rating": "Telecom"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 5.5, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "ITC", "holding_name": "ITC Ltd", "weight_pct": 4.5, "sector_or_rating": "FMCG"},
                {"holding_type": "EQUITY", "identifier": "SUNPHARMA", "holding_name": "Sun Pharmaceutical Ind", "weight_pct": 4.1, "sector_or_rating": "Pharmaceuticals"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "TREPS Cash Reserve", "weight_pct": 19.5, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "MIRAE_ELSS_DIR",
            "scheme_name": "Mirae Asset ELSS Tax Saver Fund - Direct Plan - Growth",
            "fund_house": "Mirae Asset Mutual Fund",
            "category": "ELSS (Tax Saver)",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 500 TRI",
            "aum_crores": 23400.0,
            "nav": 48.90,
            "ter_direct_pct": 0.58,
            "ter_regular_pct": 1.48,
            "portfolio_turnover_ratio_pct": 28.0,
            "active_share_pct": 64.0,
            "risk_grade": "Very High",
            "fund_manager": "Neelesh Surana",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 81.0,
                "sortino_ratio": 1.84,
                "downside_capture_ratio": 72.0,
                "upside_capture_ratio": 99.0,
                "hurst_exponent": 0.58,
                "top_10_weight_pct": 52.0,
                "asset_allocation": {"equity": 95.0, "debt_cash": 5.0}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 8.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 8.2, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 7.5, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 6.8, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "TCS", "holding_name": "Tata Consultancy Services", "weight_pct": 5.1, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "LT", "holding_name": "Larsen & Toubro Ltd", "weight_pct": 4.5, "sector_or_rating": "Infrastructure"},
                {"holding_type": "EQUITY", "identifier": "AXISBANK", "holding_name": "Axis Bank Ltd", "weight_pct": 4.1, "sector_or_rating": "Private Banks"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Repo Margin", "weight_pct": 5.0, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "QUANT_ELSS_DIR",
            "scheme_name": "Quant ELSS Tax Saver Fund - Direct Plan - Growth",
            "fund_house": "Quant Mutual Fund",
            "category": "ELSS (Tax Saver)",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 500 TRI",
            "aum_crores": 10800.0,
            "nav": 395.20,
            "ter_direct_pct": 0.77,
            "ter_regular_pct": 1.62,
            "portfolio_turnover_ratio_pct": 145.0,
            "active_share_pct": 86.0,
            "risk_grade": "Very High",
            "fund_manager": "Sandeep Tandon",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 76.0,
                "sortino_ratio": 2.12,
                "downside_capture_ratio": 78.0,
                "upside_capture_ratio": 122.0,
                "hurst_exponent": 0.72,
                "top_10_weight_pct": 54.0,
                "asset_allocation": {"equity": 82.7, "debt_cash": 17.3}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 9.8, "sector_or_rating": "Energy & Petrochemicals"},
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 6.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "BHARTIARTL", "holding_name": "Bharti Airtel Ltd", "weight_pct": 5.8, "sector_or_rating": "Telecom"},
                {"holding_type": "EQUITY", "identifier": "TATACOMM", "holding_name": "Tata Communications Ltd", "weight_pct": 4.5, "sector_or_rating": "Telecom Services"},
                {"holding_type": "EQUITY", "identifier": "MAXHEALTH", "holding_name": "Max Healthcare Institute", "weight_pct": 3.8, "sector_or_rating": "Healthcare Services"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Cash & Arbitrage Margin", "weight_pct": 17.3, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "EDELWEISS_BAF_DIR",
            "scheme_name": "Edelweiss Balanced Advantage Fund - Direct Plan - Growth",
            "fund_house": "Edelweiss Mutual Fund",
            "category": "Balanced Advantage Fund",
            "broad_category": "HYBRID",
            "benchmark_index": "NIFTY 50 Hybrid Composite Debt 50:50 Index",
            "aum_crores": 11900.0,
            "nav": 49.60,
            "ter_direct_pct": 0.71,
            "ter_regular_pct": 1.58,
            "portfolio_turnover_ratio_pct": 74.0,
            "active_share_pct": 61.0,
            "risk_grade": "Moderately High",
            "fund_manager": "Bhavesh Jain",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 84.0,
                "sortino_ratio": 1.98,
                "downside_capture_ratio": 56.0,
                "upside_capture_ratio": 76.0,
                "hurst_exponent": 0.60,
                "top_10_weight_pct": 42.0,
                "asset_allocation": {"net_equity": 45.0, "debt": 40.4, "cash": 14.6}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd", "weight_pct": 5.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 4.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd", "weight_pct": 4.2, "sector_or_rating": "Energy & Conglomerate"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 3.9, "sector_or_rating": "IT Services"},
                {"holding_type": "DEBT", "identifier": "IN0020230085", "holding_name": "7.18% Central Government Sovereign G-Sec 2033", "weight_pct": 18.5, "sector_or_rating": "SOVEREIGN", "instrument_details": {"ytm": 7.08, "duration": 6.8}},
                {"holding_type": "DEBT", "identifier": "INE002A08012", "holding_name": "Reliance Industries 8.65% Secured NCD 2028", "weight_pct": 8.5, "sector_or_rating": "CRISIL AAA", "instrument_details": {"ytm": 8.65, "duration": 1.53, "seniority": "SENIOR_SECURED"}},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "TREPS Repo", "weight_pct": 14.6, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "KOTAK_ARBITRAGE_DIR",
            "scheme_name": "Kotak Equity Arbitrage Fund - Direct Plan - Growth",
            "fund_house": "Kotak Mutual Fund",
            "category": "Arbitrage Fund",
            "broad_category": "HYBRID",
            "benchmark_index": "NIFTY 50 Arbitrage Index",
            "aum_crores": 49500.0,
            "nav": 35.80,
            "ter_direct_pct": 0.38,
            "ter_regular_pct": 0.88,
            "portfolio_turnover_ratio_pct": 210.0,
            "active_share_pct": 15.0,
            "risk_grade": "Low",
            "fund_manager": "Hiten Shah",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 98.0,
                "sortino_ratio": 3.40,
                "downside_capture_ratio": 5.0,
                "upside_capture_ratio": 24.0,
                "hurst_exponent": 0.51,
                "top_10_weight_pct": 45.0,
                "asset_allocation": {"hedged_equity": 68.0, "debt_t_bills": 18.0, "cash_treps": 14.0}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "HDFCBANK", "holding_name": "HDFC Bank Ltd (Fully Hedged)", "weight_pct": 8.2, "sector_or_rating": "Hedged Arbitrage"},
                {"holding_type": "EQUITY", "identifier": "RELIANCE", "holding_name": "Reliance Industries Ltd (Fully Hedged)", "weight_pct": 7.5, "sector_or_rating": "Hedged Arbitrage"},
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd (Fully Hedged)", "weight_pct": 6.8, "sector_or_rating": "Hedged Arbitrage"},
                {"holding_type": "DEBT", "identifier": "IN0020230085", "holding_name": "91-Day Sovereign Treasury Bills", "weight_pct": 18.0, "sector_or_rating": "SOVEREIGN", "instrument_details": {"ytm": 6.85, "duration": 0.25}},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Tri-Party Repo & Margin", "weight_pct": 14.0, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "HDFC_BANKPSU_DIR",
            "scheme_name": "HDFC Banking and PSU Debt Fund - Direct Plan - Growth",
            "fund_house": "HDFC Mutual Fund",
            "category": "Banking & PSU Debt Fund",
            "broad_category": "DEBT",
            "benchmark_index": "NIFTY Banking & PSU Debt Index",
            "aum_crores": 10200.0,
            "nav": 22.40,
            "ter_direct_pct": 0.30,
            "ter_regular_pct": 0.75,
            "portfolio_turnover_ratio_pct": 48.0,
            "active_share_pct": 45.0,
            "risk_grade": "Low to Moderate",
            "fund_manager": "Anil Bamboli",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 96.0,
                "sortino_ratio": 2.95,
                "downside_capture_ratio": 28.0,
                "upside_capture_ratio": 92.0,
                "hurst_exponent": 0.58,
                "top_10_weight_pct": 72.0,
                "asset_allocation": {"psu_bonds": 65.0, "sovereign_gsec": 23.0, "cash": 12.0}
            },
            "holdings": [
                {"holding_type": "DEBT", "identifier": "INE040A08377", "holding_name": "HDFC Bank 7.95% Subordinated Tier-II Bond 2033", "weight_pct": 12.5, "sector_or_rating": "CRISIL AAA", "instrument_details": {"ytm": 7.95, "duration": 5.42, "seniority": "SUBORDINATED_TIER_2"}},
                {"holding_type": "DEBT", "identifier": "IN0020230085", "holding_name": "7.18% Central Government Sovereign G-Sec 2033", "weight_pct": 23.0, "sector_or_rating": "SOVEREIGN", "instrument_details": {"ytm": 7.08, "duration": 6.8}},
                {"holding_type": "DEBT", "identifier": "INE306N07MM3", "holding_name": "Tata Capital Financial Services 8.85% Secured NCD 2027", "weight_pct": 14.5, "sector_or_rating": "CRISIL AAA", "instrument_details": {"ytm": 8.85, "duration": 1.48, "seniority": "SENIOR_SECURED"}},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "TREPS Collateral", "weight_pct": 12.0, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "SBI_LIQUID_DIR",
            "scheme_name": "SBI Liquid Fund - Direct Plan - Growth",
            "fund_house": "SBI Mutual Fund",
            "category": "Liquid Fund",
            "broad_category": "DEBT",
            "benchmark_index": "CRISIL Liquid Debt Index",
            "aum_crores": 68500.0,
            "nav": 3780.20,
            "ter_direct_pct": 0.18,
            "ter_regular_pct": 0.28,
            "portfolio_turnover_ratio_pct": 320.0,
            "active_share_pct": 20.0,
            "risk_grade": "Low",
            "fund_manager": "Ardhendu Bhattacharya",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 99.5,
                "sortino_ratio": 4.10,
                "downside_capture_ratio": 1.0,
                "upside_capture_ratio": 30.0,
                "hurst_exponent": 0.50,
                "top_10_weight_pct": 55.0,
                "asset_allocation": {"treasury_bills": 42.0, "treps_repo": 38.0, "bank_cd": 20.0}
            },
            "holdings": [
                {"holding_type": "DEBT", "identifier": "IN0020230085", "holding_name": "91-Day Central Government Sovereign T-Bills", "weight_pct": 42.0, "sector_or_rating": "SOVEREIGN", "instrument_details": {"ytm": 6.82, "duration": 0.25}},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Tri-Party Repo (TREPS) & Call Reserves", "weight_pct": 38.0, "sector_or_rating": "CASH"},
                {"holding_type": "DEBT", "identifier": "INE040A08377", "holding_name": "HDFC Bank 90-Day Certificate of Deposit", "weight_pct": 20.0, "sector_or_rating": "CRISIL A1+", "instrument_details": {"ytm": 7.15, "duration": 0.24}}
            ]
        },
        {
            "scheme_code": "BANDHAN_STERLING_DIR",
            "scheme_name": "Bandhan Sterling Value Fund - Direct Plan - Growth",
            "fund_house": "Bandhan Mutual Fund",
            "category": "Value / Contra Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "BSE 500 TRI",
            "aum_crores": 9800.0,
            "nav": 142.10,
            "ter_direct_pct": 0.72,
            "ter_regular_pct": 1.55,
            "portfolio_turnover_ratio_pct": 36.0,
            "active_share_pct": 76.0,
            "risk_grade": "Very High",
            "fund_manager": "Daylynn Pinto",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 83.0,
                "sortino_ratio": 1.98,
                "downside_capture_ratio": 65.0,
                "upside_capture_ratio": 105.0,
                "hurst_exponent": 0.65,
                "top_10_weight_pct": 41.0,
                "asset_allocation": {"equity": 88.1, "debt_cash": 11.9}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 6.2, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "AXISBANK", "holding_name": "Axis Bank Ltd", "weight_pct": 5.5, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "CIPLA", "holding_name": "Cipla Ltd", "weight_pct": 4.8, "sector_or_rating": "Pharmaceuticals"},
                {"holding_type": "EQUITY", "identifier": "BHARATFORG", "holding_name": "Bharat Forge Ltd", "weight_pct": 4.2, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "TATACOMM", "holding_name": "Tata Communications Ltd", "weight_pct": 3.9, "sector_or_rating": "Telecom Services"},
                {"holding_type": "EQUITY", "identifier": "FEDERALBNK", "holding_name": "Federal Bank Ltd", "weight_pct": 3.5, "sector_or_rating": "Banks"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Cash Margin", "weight_pct": 11.9, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "DSP_MIDCAP_DIR",
            "scheme_name": "DSP Midcap Fund - Direct Plan - Growth",
            "fund_house": "DSP Mutual Fund",
            "category": "Mid Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY Midcap 150 TRI",
            "aum_crores": 18200.0,
            "nav": 124.60,
            "ter_direct_pct": 0.81,
            "ter_regular_pct": 1.65,
            "portfolio_turnover_ratio_pct": 28.0,
            "active_share_pct": 74.5,
            "risk_grade": "Very High",
            "fund_manager": "Vinit Sambre",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 82.5,
                "sortino_ratio": 1.94,
                "downside_capture_ratio": 67.0,
                "upside_capture_ratio": 104.0,
                "hurst_exponent": 0.64,
                "top_10_weight_pct": 39.0,
                "asset_allocation": {"equity": 83.9, "debt_cash": 16.1}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "MAXHEALTH", "holding_name": "Max Healthcare Institute", "weight_pct": 4.8, "sector_or_rating": "Healthcare Services"},
                {"holding_type": "EQUITY", "identifier": "BHARATFORG", "holding_name": "Bharat Forge Ltd", "weight_pct": 4.5, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "ASTRAL", "holding_name": "Astral Ltd", "weight_pct": 4.1, "sector_or_rating": "Building Products"},
                {"holding_type": "EQUITY", "identifier": "COFORGE", "holding_name": "Coforge Ltd", "weight_pct": 3.8, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "SUPRAJIT", "holding_name": "Suprajit Engineering Ltd", "weight_pct": 3.5, "sector_or_rating": "Auto Ancillary"},
                {"holding_type": "EQUITY", "identifier": "FEDERALBNK", "holding_name": "Federal Bank Ltd", "weight_pct": 3.2, "sector_or_rating": "Banks"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "TREPS Cash", "weight_pct": 16.1, "sector_or_rating": "CASH"}
            ]
        },
        {
            "scheme_code": "AXIS_GROWTH_DIR",
            "scheme_name": "Axis Growth Opportunities Fund - Direct Plan - Growth",
            "fund_house": "Axis Mutual Fund",
            "category": "Large & Mid Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY LargeMidcap 250 TRI",
            "aum_crores": 12100.0,
            "nav": 32.80,
            "ter_direct_pct": 0.69,
            "ter_regular_pct": 1.52,
            "portfolio_turnover_ratio_pct": 35.0,
            "active_share_pct": 75.0,
            "risk_grade": "Very High",
            "fund_manager": "Jinesh Gopani",
            "last_portfolio_date": "2026-09-30",
            "metadata": {
                "rolling_consistency_3y_pct": 81.0,
                "sortino_ratio": 1.91,
                "downside_capture_ratio": 69.0,
                "upside_capture_ratio": 105.0,
                "hurst_exponent": 0.63,
                "top_10_weight_pct": 45.0,
                "asset_allocation": {"equity": 84.7, "debt_cash": 15.3}
            },
            "holdings": [
                {"holding_type": "EQUITY", "identifier": "ICICIBANK", "holding_name": "ICICI Bank Ltd", "weight_pct": 6.8, "sector_or_rating": "Private Banks"},
                {"holding_type": "EQUITY", "identifier": "BAJFINANCE", "holding_name": "Bajaj Finance Ltd", "weight_pct": 6.2, "sector_or_rating": "NBFC"},
                {"holding_type": "EQUITY", "identifier": "INFY", "holding_name": "Infosys Ltd", "weight_pct": 5.8, "sector_or_rating": "IT Services"},
                {"holding_type": "EQUITY", "identifier": "MAXHEALTH", "holding_name": "Max Healthcare Institute", "weight_pct": 4.5, "sector_or_rating": "Healthcare Services"},
                {"holding_type": "EQUITY", "identifier": "COFORGE", "holding_name": "Coforge Ltd", "weight_pct": 4.1, "sector_or_rating": "IT Services"},
                {"holding_type": "FOREIGN_EQUITY", "identifier": "GOOGL", "holding_name": "Alphabet Inc (Google)", "weight_pct": 3.8, "sector_or_rating": "US Tech"},
                {"holding_type": "FOREIGN_EQUITY", "identifier": "MSFT", "holding_name": "Microsoft Corp", "weight_pct": 3.5, "sector_or_rating": "US Tech"},
                {"holding_type": "CASH_EQUIVALENT", "identifier": "TREPS", "holding_name": "Cash Margin", "weight_pct": 15.3, "sector_or_rating": "CASH"}
            ]
        }
    ]

    for s in schemes:
        holdings = s.pop("holdings", [])
        if save_mutual_fund_scheme(s):
            save_mutual_fund_holdings(s["scheme_code"], holdings)
            seeded += 1

    return seeded


def save_fund_forensic_dossier(dossier: Dict[str, Any]) -> bool:
    """Saves or updates a synthesized 7-pillar forensic fund dossier."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()

    code = dossier["scheme_code"].strip().upper()
    text = dossier.get("dossier_text", "")
    comp_score = float(dossier.get("composite_health_score", 0.0))
    moat_score = float(dossier.get("weighted_moat_score", 0.0))
    asri = float(dossier.get("accounting_risk_index", 0.0))
    mos = float(dossier.get("margin_of_safety_pct", 0.0))
    pledge = float(dossier.get("promoter_pledge_exposure_pct", 0.0))
    active_share = float(dossier.get("active_share_pct", 0.0))
    risky_json = json.dumps(dossier.get("top_risky_holdings", []))
    quality_json = json.dumps(dossier.get("top_quality_holdings", []))
    auditor = dossier.get("audited_by", "Gemini_Chief_Forensic_Officer")

    try:
        if use_pg:
            cursor.execute("""
                INSERT INTO fund_forensic_dossiers (
                    scheme_code, dossier_text, composite_health_score, weighted_moat_score,
                    accounting_risk_index, margin_of_safety_pct, promoter_pledge_exposure_pct,
                    active_share_pct, top_risky_holdings_json, top_quality_holdings_json,
                    audited_by, last_audited_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (scheme_code) DO UPDATE SET
                    dossier_text = EXCLUDED.dossier_text,
                    composite_health_score = EXCLUDED.composite_health_score,
                    weighted_moat_score = EXCLUDED.weighted_moat_score,
                    accounting_risk_index = EXCLUDED.accounting_risk_index,
                    margin_of_safety_pct = EXCLUDED.margin_of_safety_pct,
                    promoter_pledge_exposure_pct = EXCLUDED.promoter_pledge_exposure_pct,
                    active_share_pct = EXCLUDED.active_share_pct,
                    top_risky_holdings_json = EXCLUDED.top_risky_holdings_json,
                    top_quality_holdings_json = EXCLUDED.top_quality_holdings_json,
                    audited_by = EXCLUDED.audited_by,
                    last_audited_at = now();
            """, (code, text, comp_score, moat_score, asri, mos, pledge, active_share, risky_json, quality_json, auditor))
        else:
            cursor.execute("""
                INSERT INTO fund_forensic_dossiers (
                    scheme_code, dossier_text, composite_health_score, weighted_moat_score,
                    accounting_risk_index, margin_of_safety_pct, promoter_pledge_exposure_pct,
                    active_share_pct, top_risky_holdings_json, top_quality_holdings_json,
                    audited_by, last_audited_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT (scheme_code) DO UPDATE SET
                    dossier_text = excluded.dossier_text,
                    composite_health_score = excluded.composite_health_score,
                    weighted_moat_score = excluded.weighted_moat_score,
                    accounting_risk_index = excluded.accounting_risk_index,
                    margin_of_safety_pct = excluded.margin_of_safety_pct,
                    promoter_pledge_exposure_pct = excluded.promoter_pledge_exposure_pct,
                    active_share_pct = excluded.active_share_pct,
                    top_risky_holdings_json = excluded.top_risky_holdings_json,
                    top_quality_holdings_json = excluded.top_quality_holdings_json,
                    audited_by = excluded.audited_by,
                    last_audited_at = datetime('now');
            """, (code, text, comp_score, moat_score, asri, mos, pledge, active_share, risky_json, quality_json, auditor))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving fund forensic dossier for {code}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_fund_forensic_dossier(scheme_code: str) -> Optional[Dict[str, Any]]:
    """Retrieves the latest forensic look-through dossier for a fund scheme."""
    conn = get_db_connection()
    cursor = conn.cursor()
    use_pg = is_supabase_enabled()
    clean_code = scheme_code.strip().upper()

    try:
        sql = "SELECT * FROM fund_forensic_dossiers WHERE scheme_code = %s" if use_pg else "SELECT * FROM fund_forensic_dossiers WHERE scheme_code = ?"
        cursor.execute(sql, (clean_code,))
        row = cursor.fetchone()
        if not row:
            return None
        res = clean_dict_row(cursor, row)
        if "top_risky_holdings_json" in res and res["top_risky_holdings_json"]:
            try:
                res["top_risky_holdings"] = json.loads(res["top_risky_holdings_json"])
            except Exception:
                res["top_risky_holdings"] = []
        if "top_quality_holdings_json" in res and res["top_quality_holdings_json"]:
            try:
                res["top_quality_holdings"] = json.loads(res["top_quality_holdings_json"])
            except Exception:
                res["top_quality_holdings"] = []
        return res
    except Exception as e:
        logger.error(f"Error getting fund forensic dossier for {clean_code}: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_featured_daily_fund_dossier() -> Optional[Dict[str, Any]]:
    """Retrieves the most recently audited fund dossier with scheme metadata for hero placement."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        sql = """
            SELECT d.*, s.scheme_name, s.fund_house, s.category, s.broad_category,
                   s.aum_crores, s.nav, s.ter_direct_pct, s.fund_manager, s.benchmark_index
            FROM fund_forensic_dossiers d
            JOIN mutual_fund_schemes s ON d.scheme_code = s.scheme_code
            ORDER BY d.last_audited_at DESC
            LIMIT 1
        """
        cursor.execute(sql)
        row = cursor.fetchone()
        if not row:
            return None
        res = clean_dict_row(cursor, row)
        if "top_risky_holdings_json" in res and res["top_risky_holdings_json"]:
            try:
                res["top_risky_holdings"] = json.loads(res["top_risky_holdings_json"])
            except Exception:
                res["top_risky_holdings"] = []
        if "top_quality_holdings_json" in res and res["top_quality_holdings_json"]:
            try:
                res["top_quality_holdings"] = json.loads(res["top_quality_holdings_json"])
            except Exception:
                res["top_quality_holdings"] = []
        return res
    except Exception as e:
        logger.error(f"Error getting featured daily fund dossier: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_next_fund_for_daily_audit() -> Optional[Dict[str, Any]]:
    """Selects the next fund in the rotation queue (never audited or oldest audit timestamp)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        sql = """
            SELECT s.scheme_code, s.scheme_name, s.category, d.last_audited_at
            FROM mutual_fund_schemes s
            LEFT JOIN fund_forensic_dossiers d ON s.scheme_code = d.scheme_code
            WHERE s.broad_category IN ('EQUITY', 'HYBRID')
            ORDER BY (d.last_audited_at IS NOT NULL), d.last_audited_at ASC
            LIMIT 1
        """
        cursor.execute(sql)
        row = cursor.fetchone()
        if not row:
            return None
        return clean_dict_row(cursor, row)
    except Exception as e:
        logger.error(f"Error getting next fund for daily audit: {e}")
        return None
    finally:
        cursor.close()
        conn.close()
