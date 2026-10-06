"""Database repository and data access layer for SEBI SM REITs, Mainboard REITs,
Infrastructure Investment Trusts (InvITs), and Sovereign Gold Bond (SGB) tranches.

Enforces SEBI (Real Estate Investment Trusts) Regulations, 2024 SM REIT criteria:
1. Occupancy >= 95%
2. NDCF Distribution Payout >= 95%
3. Leverage LTV <= 49%
4. SGB Capital Gains Exemption (Section 47(viic) Income Tax Act).
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from core.db.connection import get_db_connection, get_supabase_url, get_placeholder, IST

logger = logging.getLogger("equity_research.core.db.reits")

# Curated baseline REITs, SM REITs, and InvITs
DEFAULT_REITS_AND_INVITS = [
    {
        "symbol": "EMBASSY",
        "name": "Embassy Office Parks REIT",
        "structure_type": "MAINBOARD_REIT",
        "current_price": 388.50,
        "nav_per_unit": 412.00,
        "discount_to_nav_pct": -5.70,
        "distribution_yield_pct": 7.15,
        "occupancy_pct": 89.2,
        "ndcf_payout_purity_pct": 100.0,
        "ltv_ratio_pct": 31.4,
        "wale_years": 6.8,
        "sponsor_holding_pct": 18.2,
        "sebi_compliant": True,
        "details_json": json.dumps({
            "asset_class": "Grade-A Commercial IT Parks",
            "leasable_area_msf": 45.4,
            "top_tenants": ["JPMorgan", "Cognizant", "NTT Data", "Flipkart"],
            "city_breakdown": {"Bengaluru": "74%", "Mumbai": "10%", "Pune": "9%", "Noida": "7%"}
        })
    },
    {
        "symbol": "MINDSPACE",
        "name": "Mindspace Business Parks REIT",
        "structure_type": "MAINBOARD_REIT",
        "current_price": 352.00,
        "nav_per_unit": 384.50,
        "discount_to_nav_pct": -8.45,
        "distribution_yield_pct": 6.80,
        "occupancy_pct": 88.5,
        "ndcf_payout_purity_pct": 99.8,
        "ltv_ratio_pct": 22.8,
        "wale_years": 7.2,
        "sponsor_holding_pct": 63.4,
        "sebi_compliant": True,
        "details_json": json.dumps({
            "asset_class": "Tech & SEZ Commercial Parks",
            "leasable_area_msf": 32.0,
            "top_tenants": ["Qualcomm", "Barclays", "Amazon", "Accenture"],
            "city_breakdown": {"Mumbai Region": "44%", "Hyderabad": "39%", "Pune": "15%"}
        })
    },
    {
        "symbol": "BIRET",
        "name": "Brookfield India Real Estate Trust",
        "structure_type": "MAINBOARD_REIT",
        "current_price": 274.20,
        "nav_per_unit": 335.00,
        "discount_to_nav_pct": -18.15,
        "distribution_yield_pct": 8.10,
        "occupancy_pct": 86.4,
        "ndcf_payout_purity_pct": 100.0,
        "ltv_ratio_pct": 36.2,
        "wale_years": 7.5,
        "sponsor_holding_pct": 42.1,
        "sebi_compliant": True,
        "details_json": json.dumps({
            "asset_class": "Institutional Grade-A Offices",
            "leasable_area_msf": 25.5,
            "top_tenants": ["TCS", "Cognizant", "RBS", "Barclays"],
            "city_breakdown": {"NCR": "65%", "Mumbai": "18%", "Kolkata": "17%"}
        })
    },
    {
        "symbol": "NEXUS",
        "name": "Nexus Select Trust",
        "structure_type": "MAINBOARD_REIT",
        "current_price": 141.50,
        "nav_per_unit": 152.00,
        "discount_to_nav_pct": -6.91,
        "distribution_yield_pct": 7.40,
        "occupancy_pct": 97.4,
        "ndcf_payout_purity_pct": 100.0,
        "ltv_ratio_pct": 16.5,
        "wale_years": 5.4,
        "sponsor_holding_pct": 43.0,
        "sebi_compliant": True,
        "details_json": json.dumps({
            "asset_class": "Pure-Play Retail Urban Consumption Malls",
            "leasable_area_msf": 9.8,
            "top_tenants": ["Zara", "PVR INOX", "Shoppers Stop", "H&M"],
            "city_breakdown": {"Tier-1 Cities": "68%", "High-Growth Tier-2": "32%"}
        })
    },
    {
        "symbol": "PGINVIT",
        "name": "POWERGRID Infrastructure Investment Trust",
        "structure_type": "INVIT",
        "current_price": 102.50,
        "nav_per_unit": 108.00,
        "discount_to_nav_pct": -5.09,
        "distribution_yield_pct": 11.20,
        "occupancy_pct": 99.8,
        "ndcf_payout_purity_pct": 100.0,
        "ltv_ratio_pct": 11.2,
        "wale_years": 28.0,
        "sponsor_holding_pct": 15.0,
        "sebi_compliant": True,
        "details_json": json.dumps({
            "asset_class": "Inter-State Power Transmission Assets (TSPs)",
            "network_length_ckm": 3698.0,
            "availability_factor": "99.8%",
            "cashflow_nature": "Regulated Availability-Based Annuity"
        })
    },
    {
        "symbol": "SMREIT_BLR_01",
        "name": "PropShare Platina SM REIT (SEBI Reg.)",
        "structure_type": "SM_REIT",
        "current_price": 10000.00,
        "nav_per_unit": 10000.00,
        "discount_to_nav_pct": 0.0,
        "distribution_yield_pct": 9.00,
        "occupancy_pct": 100.0,
        "ndcf_payout_purity_pct": 100.0,
        "ltv_ratio_pct": 0.0,
        "wale_years": 8.0,
        "sponsor_holding_pct": 5.0,
        "sebi_compliant": True,
        "details_json": json.dumps({
            "asset_class": "Pre-Leased Tech Commercial Hub (Outer Ring Road, Bengaluru)",
            "leasable_area_sqft": 246935,
            "sole_tenant": "US Tech Multinational",
            "minimum_ticket_inr": 1000000,
            "leverage": "Zero Debt (100% Equity Funded)"
        })
    }
]

# Baseline Sovereign Gold Bond (SGB) Tranches on Secondary Market
DEFAULT_SGB_TRANCHES = [
    {
        "symbol": "SGBNOV26",
        "series_name": "Sovereign Gold Bond 2018-19 Series IV",
        "issue_price": 3183.0,
        "market_price": 7240.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -2.82,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2026-11-06",
        "ytm_annualized_pct": 8.85,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 1.95
    },
    {
        "symbol": "SGBMAY29",
        "series_name": "Sovereign Gold Bond 2021-22 Series I",
        "issue_price": 4777.0,
        "market_price": 7180.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.62,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2029-05-25",
        "ytm_annualized_pct": 9.42,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.15
    },
    {
        "symbol": "SGBOCT29",
        "series_name": "Sovereign Gold Bond 2021-22 Series VII",
        "issue_price": 4761.0,
        "market_price": 7120.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.43,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2029-10-30",
        "ytm_annualized_pct": 9.80,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.30
    },
    {
        "symbol": "SGBFEB32",
        "series_name": "Sovereign Gold Bond 2023-24 Series IV",
        "issue_price": 6263.0,
        "market_price": 7090.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.83,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2032-02-28",
        "ytm_annualized_pct": 10.15,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.45
    }
]


def save_reit_or_invit(reit: Dict[str, Any]) -> bool:
    """Inserts or updates a REIT, SM REIT, or InvIT entry."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url())

    try:
        cp = float(reit.get("current_price") or reit.get("cmp_inr") or 0.0)
        nav = float(reit.get("nav_per_unit") or reit.get("nav_per_unit_inr") or cp or 1.0)
        disc = round(((cp - nav) / nav) * 100, 2) if nav > 0 else 0.0

        # SEBI Regulatory compliance test:
        # 1. Occupancy >= 95% for SM REIT completed commercial asset
        # 2. NDCF distribution purity >= 95%
        # 3. Leverage LTV <= 49%
        is_sm = reit.get("structure_type") == "SM_REIT"
        occ = float(reit.get("occupancy_pct", 0.0))
        ndcf = float(reit.get("ndcf_payout_purity_pct", 100.0))
        ltv = float(reit.get("ltv_ratio_pct", 0.0))

        sebi_compliant = True
        if is_sm and (occ < 95.0 or ndcf < 95.0 or ltv > 49.0):
            sebi_compliant = False
        elif not is_sm and (ndcf < 90.0 or ltv > 49.0):
            sebi_compliant = False

        det_json = reit.get("details_json", "{}")
        if isinstance(det_json, dict):
            det_json = json.dumps(det_json)

        if is_pg:
            query = f"""
                INSERT INTO reits_and_invits (
                    symbol, name, structure_type, current_price, nav_per_unit,
                    discount_to_nav_pct, distribution_yield_pct, occupancy_pct,
                    ndcf_payout_purity_pct, ltv_ratio_pct, wale_years,
                    sponsor_holding_pct, sebi_compliant, details_json, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, now())
                ON CONFLICT (symbol) DO UPDATE SET
                    name = EXCLUDED.name,
                    structure_type = EXCLUDED.structure_type,
                    current_price = EXCLUDED.current_price,
                    nav_per_unit = EXCLUDED.nav_per_unit,
                    discount_to_nav_pct = EXCLUDED.discount_to_nav_pct,
                    distribution_yield_pct = EXCLUDED.distribution_yield_pct,
                    occupancy_pct = EXCLUDED.occupancy_pct,
                    ndcf_payout_purity_pct = EXCLUDED.ndcf_payout_purity_pct,
                    ltv_ratio_pct = EXCLUDED.ltv_ratio_pct,
                    wale_years = EXCLUDED.wale_years,
                    sponsor_holding_pct = EXCLUDED.sponsor_holding_pct,
                    sebi_compliant = EXCLUDED.sebi_compliant,
                    details_json = EXCLUDED.details_json,
                    updated_at = now();
            """
        else:
            query = f"""
                INSERT INTO reits_and_invits (
                    symbol, name, structure_type, current_price, nav_per_unit,
                    discount_to_nav_pct, distribution_yield_pct, occupancy_pct,
                    ndcf_payout_purity_pct, ltv_ratio_pct, wale_years,
                    sponsor_holding_pct, sebi_compliant, details_json, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, datetime('now'))
                ON CONFLICT (symbol) DO UPDATE SET
                    name = excluded.name,
                    structure_type = excluded.structure_type,
                    current_price = excluded.current_price,
                    nav_per_unit = excluded.nav_per_unit,
                    discount_to_nav_pct = excluded.discount_to_nav_pct,
                    distribution_yield_pct = excluded.distribution_yield_pct,
                    occupancy_pct = excluded.occupancy_pct,
                    ndcf_payout_purity_pct = excluded.ndcf_payout_purity_pct,
                    ltv_ratio_pct = excluded.ltv_ratio_pct,
                    wale_years = excluded.wale_years,
                    sponsor_holding_pct = excluded.sponsor_holding_pct,
                    sebi_compliant = excluded.sebi_compliant,
                    details_json = excluded.details_json,
                    updated_at = datetime('now');
            """
        params = (
            reit["symbol"].upper(),
            reit["name"],
            reit.get("structure_type", "MAINBOARD_REIT"),
            cp,
            nav,
            disc,
            float(reit.get("distribution_yield_pct", 7.0)),
            occ,
            ndcf,
            ltv,
            float(reit.get("wale_years", 6.0)),
            float(reit.get("sponsor_holding_pct", 15.0)),
            sebi_compliant,
            det_json,
        )
        cursor.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving REIT/InvIT {reit.get('symbol')}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_all_reits_and_invits(structure_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all tracked REITs, SM REITs, and InvITs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        where_clause = f"WHERE structure_type = {p}" if structure_type else ""
        query = f"""
            SELECT id, symbol, name, structure_type, current_price, nav_per_unit,
                   discount_to_nav_pct, distribution_yield_pct, occupancy_pct,
                   ndcf_payout_purity_pct, ltv_ratio_pct, wale_years,
                   sponsor_holding_pct, sebi_compliant, details_json, updated_at
            FROM reits_and_invits
            {where_clause}
            ORDER BY distribution_yield_pct DESC;
        """
        if structure_type:
            cursor.execute(query, (structure_type,))
        else:
            cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            logger.info("REITs and InvITs table is empty. Initializing baseline REITs...")
            for r in DEFAULT_REITS_AND_INVITS:
                save_reit_or_invit(r)
            if structure_type:
                return [x for x in DEFAULT_REITS_AND_INVITS if x["structure_type"] == structure_type]
            return DEFAULT_REITS_AND_INVITS

        results = []
        for r in rows:
            det = {}
            if r[14]:
                try:
                    det = json.loads(r[14])
                except Exception:
                    det = {}

            results.append({
                "id": r[0],
                "symbol": r[1],
                "name": r[2],
                "structure_type": r[3],
                "current_price": float(r[4]),
                "nav_per_unit": float(r[5]),
                "discount_to_nav_pct": float(r[6]),
                "distribution_yield_pct": float(r[7]),
                "occupancy_pct": float(r[8]),
                "ndcf_payout_purity_pct": float(r[9]),
                "ltv_ratio_pct": float(r[10]),
                "wale_years": float(r[11]),
                "sponsor_holding_pct": float(r[12]),
                "sebi_compliant": bool(r[13]),
                "details": det,
                "updated_at": str(r[15]),
            })
        return results
    except Exception as e:
        logger.error(f"Error fetching REITs and InvITs: {e}")
        return DEFAULT_REITS_AND_INVITS
    finally:
        cursor.close()
        conn.close()


def save_sgb_tranche(sgb: Dict[str, Any]) -> bool:
    """Inserts or updates an SGB secondary market tranche."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url())

    try:
        mp = float(sgb.get("market_price") or sgb.get("cmp_inr") or sgb.get("price") or 0.0)
        spot = float(sgb.get("spot_gold_price") or sgb.get("spot_gold_per_gram") or 7450.0)
        disc = round(((mp - spot) / spot) * 100, 2) if spot > 0 else 0.0

        if is_pg:
            query = f"""
                INSERT INTO sgb_tranches (
                    symbol, series_name, issue_price, market_price,
                    spot_gold_price, discount_to_spot_pct, annual_coupon_rate,
                    maturity_date, ytm_annualized_pct, tax_treatment,
                    etf_tax_adjusted_spread_pct, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, now())
                ON CONFLICT (symbol) DO UPDATE SET
                    series_name = EXCLUDED.series_name,
                    issue_price = EXCLUDED.issue_price,
                    market_price = EXCLUDED.market_price,
                    spot_gold_price = EXCLUDED.spot_gold_price,
                    discount_to_spot_pct = EXCLUDED.discount_to_spot_pct,
                    annual_coupon_rate = EXCLUDED.annual_coupon_rate,
                    maturity_date = EXCLUDED.maturity_date,
                    ytm_annualized_pct = EXCLUDED.ytm_annualized_pct,
                    tax_treatment = EXCLUDED.tax_treatment,
                    etf_tax_adjusted_spread_pct = EXCLUDED.etf_tax_adjusted_spread_pct,
                    updated_at = now();
            """
        else:
            query = f"""
                INSERT INTO sgb_tranches (
                    symbol, series_name, issue_price, market_price,
                    spot_gold_price, discount_to_spot_pct, annual_coupon_rate,
                    maturity_date, ytm_annualized_pct, tax_treatment,
                    etf_tax_adjusted_spread_pct, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, datetime('now'))
                ON CONFLICT (symbol) DO UPDATE SET
                    series_name = excluded.series_name,
                    issue_price = excluded.issue_price,
                    market_price = excluded.market_price,
                    spot_gold_price = excluded.spot_gold_price,
                    discount_to_spot_pct = excluded.discount_to_spot_pct,
                    annual_coupon_rate = excluded.annual_coupon_rate,
                    maturity_date = excluded.maturity_date,
                    ytm_annualized_pct = excluded.ytm_annualized_pct,
                    tax_treatment = excluded.tax_treatment,
                    etf_tax_adjusted_spread_pct = excluded.etf_tax_adjusted_spread_pct,
                    updated_at = datetime('now');
            """
        params = (
            sgb["symbol"].upper(),
            sgb["series_name"],
            float(sgb.get("issue_price") or sgb.get("issue_price_inr") or mp),
            mp,
            spot,
            disc,
            float(sgb.get("annual_coupon_rate") or sgb.get("coupon_rate_pct") or 2.50),
            str(sgb.get("maturity_date") or "2028-11-30"),
            float(sgb.get("ytm_annualized_pct", 9.0)),
            sgb.get("tax_treatment", "100% Tax-Free Capital Gains (Sec 47(viic))"),
            float(sgb.get("etf_tax_adjusted_spread_pct", 2.0)),
        )
        cursor.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving SGB tranche {sgb.get('symbol')}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_all_sgb_tranches() -> List[Dict[str, Any]]:
    """Retrieves all tracked Sovereign Gold Bond tranches sorted by annualized YTM."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, symbol, series_name, issue_price, market_price,
                   spot_gold_price, discount_to_spot_pct, annual_coupon_rate,
                   maturity_date, ytm_annualized_pct, tax_treatment,
                   etf_tax_adjusted_spread_pct, updated_at
            FROM sgb_tranches
            ORDER BY ytm_annualized_pct DESC;
        """)
        rows = cursor.fetchall()

        if not rows:
            logger.info("SGB tranches table is empty. Initializing baseline SGB tranches...")
            for sgb in DEFAULT_SGB_TRANCHES:
                save_sgb_tranche(sgb)
            return DEFAULT_SGB_TRANCHES

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "symbol": r[1],
                "series_name": r[2],
                "issue_price": float(r[3]),
                "market_price": float(r[4]),
                "spot_gold_price": float(r[5]),
                "discount_to_spot_pct": float(r[6]),
                "annual_coupon_rate": float(r[7]),
                "maturity_date": str(r[8]),
                "ytm_annualized_pct": float(r[9]),
                "tax_treatment": r[10],
                "etf_tax_adjusted_spread_pct": float(r[11]),
                "updated_at": str(r[12]),
            })
        return results
    except Exception as e:
        logger.error(f"Error fetching SGB tranches: {e}")
        return DEFAULT_SGB_TRANCHES
    finally:
        cursor.close()
        conn.close()
