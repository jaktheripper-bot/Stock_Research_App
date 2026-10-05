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
                "sector": "Diversified Conglomerate / Energy & Telecom",
                "promoter_group": "Reliance Industries (Mukesh Ambani)",
                "issuer_overview": "Reliance Industries Limited (RIL) is India's largest private sector enterprise with dominant market leadership spanning petrochemicals, refining, telecom (Jio), and organized retail (Reliance Retail). The company possesses massive operating cash flows and pristine access to domestic and international capital markets.",
                "collateral_type": "First pari-passu charge over manufacturing plants and movable tangible assets",
                "aum_cr": "Enterprise Net Worth ₹7,50,000+ Cr",
                "interest_coverage": 6.8,
                "dscr": 2.4,
                "debt_to_equity": 0.42,
                "credit_rating_rationale": "CRISIL affirms AAA/Stable rating driven by extraordinary business diversity, industry leadership across energy and digital services, and robust debt service coverage.",
                "the_good": [
                    "Sovereign-Equivalent Safety: CRISIL AAA rating reflects zero historical default probability among domestic corporate issuers.",
                    "Sturdy Collateral Cushion: Registered first charge provides 1.45x tangible asset cover with IDBI Trusteeship.",
                    "Robust Solvency: Interest Coverage of 6.8x ensures uninterrupted debt service across commodity cycles."
                ],
                "the_bad": [
                    "Yield Compression: At 8.25% YTM, the credit spread over 10Y G-Sec is modest (~115 bps), reflecting its near risk-free corporate status.",
                    "Tax Drag: For a 30% tax bracket investor, post-tax yield drops to ~5.68%, barely pacing CPI inflation."
                ],
                "the_ugly": [
                    "Global Energy Price Disruption: Extreme geopolitical shocks impacting gross refining margins (GRM) would compress operating cash flows, though solvency remains insulated."
                ],
                "collated_sources": ["BSE Debt Market", "GoldenPi", "IndiaBonds"]
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
                "sector": "Diversified NBFC",
                "promoter_group": "Tata Sons (100% Ultimate Parentage)",
                "issuer_overview": "Tata Capital Financial Services Limited is the flagship financial services arm of the Tata Group. The company operates a well-diversified loan book spanning retail consumer finance, commercial auto loans, housing finance, and SME corporate credit across 400+ branches nationwide.",
                "collateral_type": "First pari-passu charge on standard book debts and receivables",
                "aum_cr": "₹1,45,000+ Cr AUM",
                "gnpa_pct": 1.45,
                "nnpa_pct": 0.38,
                "crar_pct": 18.2,
                "roa_pct": 2.3,
                "interest_coverage": 3.8,
                "credit_rating_rationale": "CRISIL AAA rating is anchored by the strategic importance to Tata Sons, proven track record of timely equity infusion, pristine asset quality, and healthy capital adequacy.",
                "the_good": [
                    "Tata Group Pedigree: Unmatched moral and financial backing from parent Tata Sons.",
                    "Pristine Asset Quality: Gross NPA of 1.45% and Net NPA of 0.38% represent top-decile NBFC asset quality in India.",
                    "Comfortable Asset Cover: 1.30x registered hypothecation cover with Catalyst Trusteeship Ltd."
                ],
                "the_bad": [
                    "Moderate Reinvestment Window: 2.5-year maturity requires redeployment planning in late 2027.",
                    "Subdued Secondary Turnover: Retail lot exits on BSE RFQ typically trade with small discount spreads."
                ],
                "the_ugly": [
                    "Systemic NBFC Liquidity Shock: In a sharp systemic liquidity squeeze, credit spreads for non-bank lenders could widen, causing paper drawdowns before maturity."
                ],
                "collated_sources": ["BSE Debt Market", "Wint Wealth", "GoldenPi"]
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
                "promoter_group": "Muthoot M. George Family",
                "issuer_overview": "Muthoot Finance Limited is India's largest gold loan NBFC, holding over 185 tonnes of physical gold bullion collateral in bank-grade vaults across 5,000+ branches. Gold loans carry ultra-short tenures (under 12 months), low average LTV (65-70%), and immediate liquidity via gold auctions upon borrower default.",
                "collateral_type": "Hypothecation of physical gold bullion loan portfolio",
                "aum_cr": "₹75,000+ Cr AUM",
                "gnpa_pct": 3.8,
                "nnpa_pct": 0.9,
                "crar_pct": 25.4,
                "roa_pct": 5.1,
                "interest_coverage": 4.1,
                "credit_rating_rationale": "ICRA AA+/Stable rating reflects Muthoot's unchallenged leadership in gold financing, extraordinary capital adequacy (CRAR 25.4%), stellar profitability (RoA >5%), and strong gold-backed collateral cushions.",
                "the_good": [
                    "Liquid Physical Collateral: Every rupee lent is backed by pledged 22-carat gold jewellery stored in branch vaults.",
                    "High Profitability Buffer: Return on Assets exceeding 5% provides enormous cash flow cushion against operational shocks.",
                    "High Coupon: 9.15% coupon generates steady, predictable annual income."
                ],
                "the_bad": [
                    "Regulatory Surveillance: RBI norms on gold loan cash disbursements and LTV caps introduce operational compliance sensitivity.",
                    "Gold Price Sensitivity: A sustained crash in global gold bullion prices (>30%) could reduce collateral auction recovery margins."
                ],
                "the_ugly": [
                    "Severe Multi-Branch Vault Heist or Collateral Fraud: Any systemic breach in vault physical security or localized gold spurious pledge fraud could impact brand trust."
                ],
                "collated_sources": ["BSE Debt Market", "Wint Wealth", "GoldenPi", "IndiaBonds"]
            }
        },
        {
            "isin": "INE721A07RV3",
            "ticker": "SHRIRAMFIN",
            "scrip_code": "937812",
            "series": "N3",
            "instrument_name": "Shriram Finance 9.10% Senior Secured NCD 2027",
            "instrument_type": "NCD",
            "seniority_tier": "SENIOR_SECURED",
            "face_value": 10000.0,
            "coupon_rate_pct": 9.10,
            "coupon_frequency": "ANNUAL",
            "issue_date": "2024-01-09",
            "maturity_date": "2027-01-09",
            "credit_rating": "CRISIL AA+",
            "credit_rating_agency": "CRISIL",
            "asset_cover_ratio": 1.25,
            "is_listed": True,
            "exchange": "BSE",
            "is_sdi": False,
            "originator": None,
            "fldg_pct": 0.0,
            "last_traded_price": 10020.0,
            "ytm_pct": 9.02,
            "macaulay_duration_years": 1.28,
            "modified_duration_years": 1.17,
            "metadata": {
                "sector": "Commercial Vehicle & MSME Finance",
                "promoter_group": "Shriram Group",
                "issuer_overview": "Shriram Finance Limited is India's largest retail asset financing NBFC, formed via the mega-merger of Shriram Transport Finance and Shriram City Union Finance. The company commands deep entrenched presence in pre-owned commercial vehicle financing, rural two-wheeler loans, MSME micro-enterprise lending, and gold loans across 3,000+ branches.",
                "collateral_type": "First pari-passu hypothecation on vehicle loan receivables",
                "aum_cr": "₹2,14,000+ Cr AUM",
                "gnpa_pct": 5.3,
                "nnpa_pct": 2.7,
                "crar_pct": 20.8,
                "roa_pct": 3.1,
                "interest_coverage": 3.2,
                "credit_rating_rationale": "CRISIL AA+/Stable rating recognizes Shriram's unassailable franchise in used commercial vehicle financing, proven collection mechanisms through economic downturns, and healthy capitalization post-merger.",
                "the_good": [
                    "Market Leadership: Unrivaled 40-year history underwriting Bharat's informal road logistics and used commercial transport economy.",
                    "Substantial Yield: 9.02% YTM offers +192 bps over 10Y G-Secs with monthly/annual coupon stability.",
                    "High Capital Base: CRAR of 20.8% well above regulatory thresholds."
                ],
                "the_bad": [
                    "High Headline GNPA: Gross NPA of 5.3% reflects informal borrower profiles (though mitigated by high yields and repossession rights).",
                    "Fuel Price & Freight Cycle Sensitivity: Road transport demand slowdowns directly impact transporter repayment velocity."
                ],
                "the_ugly": [
                    "Severe Rural Drought / Diesel Price Spiral: Widespread logistics fleet standstills would trigger spike in credit provisioning."
                ],
                "collated_sources": ["BSE Debt Market", "Wint Wealth", "GoldenPi"]
            }
        },
        {
            "isin": "INE342T07279",
            "ticker": "NAVIFIN",
            "scrip_code": "938550",
            "series": "N1",
            "instrument_name": "Navi Finserv 10.45% Senior Secured NCD 2026",
            "instrument_type": "NCD",
            "seniority_tier": "SENIOR_SECURED",
            "face_value": 10000.0,
            "coupon_rate_pct": 10.45,
            "coupon_frequency": "ANNUAL",
            "issue_date": "2024-03-05",
            "maturity_date": "2026-03-05",
            "credit_rating": "CRISIL A",
            "credit_rating_agency": "CRISIL",
            "asset_cover_ratio": 1.20,
            "is_listed": True,
            "exchange": "BSE",
            "is_sdi": False,
            "originator": None,
            "fldg_pct": 0.0,
            "last_traded_price": 10000.0,
            "ytm_pct": 10.45,
            "macaulay_duration_years": 0.95,
            "modified_duration_years": 0.86,
            "metadata": {
                "sector": "Fintech Digital Lending NBFC",
                "promoter_group": "Sachin Bansal (Co-founder, Flipkart)",
                "issuer_overview": "Navi Finserv Limited is a technology-first digital NBFC founded by Sachin Bansal. The company originates 100% paperless personal loans and home loans via its proprietary mobile app, relying on automated algorithmic underwriting and UPI e-mandates for collection.",
                "collateral_type": "First charge on personal and housing loan book receivables",
                "aum_cr": "₹11,500+ Cr AUM",
                "gnpa_pct": 3.2,
                "nnpa_pct": 1.1,
                "crar_pct": 27.5,
                "roa_pct": 2.1,
                "interest_coverage": 2.6,
                "credit_rating_rationale": "CRISIL A/Stable rating supported by significant equity capitalization from founder Sachin Bansal, comfortable liquidity buffers, and rapid digital scalability, constrained by seasoning of uncollateralized personal loan portfolio.",
                "the_good": [
                    "High Double-Digit Yield: 10.45% YTM provides premium yield (+335 bps over G-Secs) popular among retail fixed-income accumulators.",
                    "Enormous Capital Adequacy: CRAR of 27.5% provides deep equity absorption cushion against unexpected loan write-offs.",
                    "Short Tenure: 2-year maturity minimizes duration and reinvestment exposure."
                ],
                "the_bad": [
                    "Unsecured Personal Loan Vulnerability: Underwriting algorithms face higher loss rates during retail job cuts or fintech collection friction.",
                    "CRISIL A Rating: Single-A credit rating carries higher credit spread risk and sensitivity to RBI unsecured lending circulars."
                ],
                "the_ugly": [
                    "Regulatory Clampdown on Digital Fintech NBFCs: RBI restrictions on digital originations or surge in digital collection defaults could impair loan recovery."
                ],
                "collated_sources": ["Wint Wealth", "GoldenPi", "BSE Debt Market"]
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
                "sector": "Private Sector Banking (D-SIB)",
                "promoter_group": "HDFC Bank (Institutionally Held D-SIB)",
                "issuer_overview": "HDFC Bank Limited is India's largest private sector bank and a designated Domestic Systemically Important Bank (D-SIB) by the RBI. Holding over ₹25 lakh crore in deposits, HDFC Bank's balance sheet is universally recognized as the bedrock of the Indian financial ecosystem.",
                "collateral_type": "Unsecured Subordinated Regulatory Capital (Tier-II)",
                "aum_cr": "Total Balance Sheet ₹36,00,000+ Cr",
                "gnpa_pct": 1.26,
                "nnpa_pct": 0.35,
                "crar_pct": 19.8,
                "credit_rating_rationale": "CRISIL AAA/Stable rating reflects systemically vital franchise, exceptional funding profile, market-leading asset quality, and robust capital buffers.",
                "the_good": [
                    "Too Big To Fail (D-SIB): Designated systemically important bank; sovereign-like regulatory supervision.",
                    "Rock-Solid Asset Quality: Net NPA of 0.35% with 75% provision coverage ratio.",
                    "Long-Term Compounding: 10-year locked coupon providing predictable retirement cash flows."
                ],
                "the_bad": [
                    "Subordinated Liquidation Rank: Tier-II bonds rank junior to retail depositors and senior creditors in resolution.",
                    "High Duration Sensitivity: 5.0-year modified duration implies ~5% price volatility for every 100 bps shift in long-term sovereign bond yields."
                ],
                "the_ugly": [
                    "Point of Non-Viability (PONV) Risk: While near-impossible for HDFC Bank, Basel III Tier-II debt can be converted or written off under extreme RBI bank failure intervention."
                ],
                "collated_sources": ["GoldenPi", "IndiaBonds", "NSE Debt"]
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
                "sector": "Private Sector Banking",
                "promoter_group": "Hinduja Group",
                "issuer_overview": "IndusInd Bank Limited is a mid-to-large private commercial bank with specialized leadership in vehicle financing, microfinance (Bharat Financial Inclusion Ltd), and gem & jewellery financing.",
                "collateral_type": "Perpetual Quasi-Equity Loss-Absorbing Instrument",
                "aum_cr": "Loan Book ₹3,45,000+ Cr",
                "gnpa_pct": 1.93,
                "nnpa_pct": 0.57,
                "crar_pct": 17.5,
                "credit_rating_rationale": "CRISIL AA/Stable rating on AT1 bonds is lower than bank's senior rating due to inherent loss-absorption triggers under RBI Basel III guidelines.",
                "the_good": [
                    "Very High Yield: 10.85% YTM provides superior cash flow for accredited institutional risk capital.",
                    "Strong Capital Base: CRAR of 17.5% keeps bank well above minimum regulatory trigger levels."
                ],
                "the_bad": [
                    "Perpetual Instrument: No contractual maturity date; repayment relies entirely on bank exercising 5-year or 10-year call option.",
                    "Coupon Discretion: Bank can skip coupon payment if capital adequacy falls below regulatory limits, with zero catch-up (non-cumulative)."
                ],
                "the_ugly": [
                    "Permanent Write-Off at PONV: Under RBI Basel III guidelines, AT1 bonds can be written down to zero without shareholder consent if RBI declares Point of Non-Viability (as witnessed in Yes Bank March 2020)."
                ],
                "collated_sources": ["GoldenPi", "IndiaBonds", "BSE Debt Market"]
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
                "sector": "Securitized Retail Debt (SDI)",
                "promoter_group": "KrazyBee / Vivriti Asset Management",
                "issuer_overview": "This Securitized Debt Instrument (SDI) represents pass-through units issued by a SEBI-registered SPV Trust managed by Vivriti. The trust holds an isolated pool of retail secured loans originated by KrazyBee Financial Services. Monthly borrower principal and interest collections are remitted directly to unitholders' demat bank accounts.",
                "collateral_type": "Bankruptcy-remote pool of retail loans held in SPV trust",
                "underlying_loan_type": "Secured Digital Gold & Consumer Asset Loans",
                "fldg_pct": 5.0,
                "pool_size_cr": 45.0,
                "credit_rating_rationale": "ICRA A+(SO) rating reflects the bankruptcy-remote structural isolation of the loan pool and the 5.0% First Loss Default Guarantee (FLDG) deposited in an escrow account with the Trustee.",
                "the_good": [
                    "Bankruptcy Remote: The loan pool is legally ring-fenced in a trust; if the originator goes bankrupt, creditors cannot touch these assets.",
                    "5% FLDG Protection: First Loss Default Guarantee absorbs the first 5% of borrower defaults before investor principal is impacted.",
                    "Monthly Cash Flow: Monthly coupon + principal amortization accelerates capital recovery within 18 months."
                ],
                "the_bad": [
                    "Zero Secondary Liquidity: SDIs have virtually no exchange trading volume; investors must hold through monthly amortization to maturity.",
                    "Origination Servicing Risk: If originator operations halt, an alternate backup servicer must step in to manage loan collections."
                ],
                "the_ugly": [
                    "Catastrophic Pool Default Spike: If retail borrower defaults exceed the 5.0% FLDG buffer, investors face direct pro-rata principal haircuts."
                ],
                "collated_sources": ["Wint Wealth", "Grip Invest", "NSE Debt"]
            }
        },
        {
            "isin": "IN902SDI0025",
            "ticker": "LEASEXSDI",
            "scrip_code": "939915",
            "series": "SDI-2",
            "instrument_name": "Grip LeaseX Corporate Equipment Rental Series II SDI",
            "instrument_type": "SDI",
            "seniority_tier": "SENIOR_SECURED",
            "face_value": 10000.0,
            "coupon_rate_pct": 11.20,
            "coupon_frequency": "MONTHLY",
            "issue_date": "2024-02-10",
            "maturity_date": "2026-02-10",
            "credit_rating": "CRISIL A",
            "credit_rating_agency": "CRISIL",
            "asset_cover_ratio": 1.25,
            "is_listed": True,
            "exchange": "NSE",
            "is_sdi": True,
            "originator": "Grip Invest / Virenxia Capital",
            "fldg_pct": 8.0,
            "last_traded_price": 10000.0,
            "ytm_pct": 11.20,
            "macaulay_duration_years": 0.98,
            "modified_duration_years": 0.89,
            "metadata": {
                "sector": "Equipment Leasing Securitized Debt (SDI)",
                "promoter_group": "Grip Invest Alternative Assets",
                "issuer_overview": "LeaseX is a SEBI-regulated Securitized Debt Instrument backed by corporate equipment and electric vehicle fleet lease agreements entered into with blue-chip and high-growth Indian companies. Lease rental payments flow directly into an escrow account administered by an independent SEBI debenture trustee.",
                "collateral_type": "Leased industrial equipment, EV fleet assets, and contracted lease rentals",
                "underlying_loan_type": "Corporate Operating & Financial Leases",
                "fldg_pct": 8.0,
                "pool_size_cr": 30.0,
                "credit_rating_rationale": "CRISIL A(SO) rating supported by strong corporate lessee counterparty credit profiles, hypothecated equipment title, and an 8.0% cash credit enhancement (FLDG).",
                "the_good": [
                    "High 11.20% Net YTM: One of the highest institutional yields available under the SEBI ₹10,000 framework.",
                    "Substantial 8% FLDG: Substantial cash cushion protects against lessee payment delays.",
                    "Monthly Demat Payouts: Regular monthly interest and principal repayment credited directly via RTGS/NEFT."
                ],
                "the_bad": [
                    "Corporate Counterparty Concentration: Pool returns rely on a concentrated group of corporate lessees paying monthly rentals on time.",
                    "Equipment Repossession Friction: If a lessee defaults, reclaiming and liquidating industrial machinery can take several months."
                ],
                "the_ugly": [
                    "Lessee Bankruptcy & Equipment Obsolescence: If multiple lessees declare insolvency under NCLT simultaneously, recovered lease equipment salvage values may be heavily discounted."
                ],
                "collated_sources": ["Grip Invest", "Wint Wealth", "NSE Debt"]
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
