"""Database repository and data access layer for the Retail Alternative Yield & Shadow-Banking Safety Radar.

Audits unregulated gold leasing (Gullak Gold+, SafeGold), RBI-restricted P2P lending,
and corporate deposits to protect retail investors from hidden capital loss risks.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from core.db.connection import get_db_connection, get_supabase_url, get_placeholder, IST

logger = logging.getLogger("equity_research.core.db.safety_radar")

# Authoritative diagnostic evaluations of prominent alternative yield products in India
DEFAULT_ALTERNATIVE_YIELD_PRODUCTS = [
    {
        "product_id": "GULLAK_GOLD_PLUS",
        "product_name": "Gullak Gold+ (Leasing to Jewelers)",
        "category": "UNREGULATED_GOLD_LEASING",
        "promoted_yield_pct": 11.50,  # Promoted as 11-12% (gold appreciation + 4-5% lease yield)
        "danger_score": 88,
        "regulatory_status": "UNREGULATED_GREY_ZONE",
        "counterparty_risk_level": "EXTREME",
        "principal_guarantee_validity": False,
        "rbi_warning_circular": "RBI Public Advisory on Unauthorized Electronic Gold Platforms & Collective Investment Schemes",
        "liquidity_lock_months": 12,
        "precedent_losses_summary": "Lending physical gold to unrated mid-market jewelers as working capital. In the event of jeweler bankruptcy or inventory distress, retail investors hold unsecured creditor status with zero DICGC or SEBI recourse.",
        "safe_alternative_recommendation": "Sovereign Gold Bonds (SGB) via secondary market or Nippon Gold BeES ETF (100% physically backed in SEBI audited vaults).",
        "audit_matrix_json": json.dumps({
            "regulatory_license": "None (Operates as corporate lease contract outside SEBI/RBI)",
            "bankruptcy_remoteness": "Zero (Gold enters jeweler's operational balance sheet)",
            "insurance_reality": "Transit insurance only; jeweler solvency NOT insured",
            "capital_risk": "100% Capital at Risk for 4-5% incremental yield"
        })
    },
    {
        "product_id": "SAFEGOLD_LEASE",
        "product_name": "SafeGold Gold Lease",
        "category": "UNREGULATED_GOLD_LEASING",
        "promoted_yield_pct": 9.50,
        "danger_score": 82,
        "regulatory_status": "UNREGULATED_GREY_ZONE",
        "counterparty_risk_level": "HIGH",
        "principal_guarantee_validity": False,
        "rbi_warning_circular": "SEBI Cautionary Notice on Unregulated Digital Gold and Derivative Leases",
        "liquidity_lock_months": 6,
        "precedent_losses_summary": "Unsecured lease agreements with verified institutional jewelers. Security deposits held by the platform cover only a fractional margin of total leased volume.",
        "safe_alternative_recommendation": "SGB Tranches offering 2.50% Sovereign coupon + 100% Tax-Free capital gains.",
        "audit_matrix_json": json.dumps({
            "regulatory_license": "Digital vault provider (not a regulated NBFC or asset manager)",
            "bankruptcy_remoteness": "Partial escrow; credit risk remains with lessee",
            "insurance_reality": "No credit default insurance",
            "capital_risk": "High counterparty default vulnerability"
        })
    },
    {
        "product_id": "P2P_12CLUB",
        "product_name": "12% Club (BharatPe / Lendbox P2P)",
        "category": "P2P_LENDING",
        "promoted_yield_pct": 12.00,
        "danger_score": 92,
        "regulatory_status": "RBI_RESTRICTED",
        "counterparty_risk_level": "EXTREME",
        "principal_guarantee_validity": False,
        "rbi_warning_circular": "RBI Circular RBI/2024-25/60 (Master Direction NBFC-P2P: Absolute Prohibition on Credit Enhancement & T+0 Withdrawal Marketing)",
        "liquidity_lock_months": 3,
        "precedent_losses_summary": "Aggressive marketing of P2P as an 'Anytime Liquidity 12% Account'. RBI cracked down in August 2024 for masking bad loan NPAs through fresh lender pooling and prohibited auto-debit sweeps.",
        "safe_alternative_recommendation": "Senior Secured Listed Corporate NCDs (CRISIL AA/AAA rated) or Target Maturity Debt ETFs.",
        "audit_matrix_json": json.dumps({
            "regulatory_license": "NBFC-P2P (Lendbox), but product was repackaged as fintech savings deposit",
            "rbi_compliance_action": "Forced withdrawal restrictions and ban on credit enhancement",
            "underlying_borrowers": "Unsecured retail and merchant subprime borrowers",
            "capital_risk": "Severe capital erosion and delayed recovery cycles"
        })
    },
    {
        "product_id": "P2P_LIQUILOANS",
        "product_name": "LiquiLoans P2P Auto-Invest",
        "category": "P2P_LENDING",
        "promoted_yield_pct": 10.00,
        "danger_score": 76,
        "regulatory_status": "RBI_RESTRICTED",
        "counterparty_risk_level": "HIGH",
        "principal_guarantee_validity": False,
        "rbi_warning_circular": "RBI NBFC-P2P Directions 2024: Mandated direct one-to-one portfolio lookthrough and ban on platform-level liquidity pools",
        "liquidity_lock_months": 12,
        "precedent_losses_summary": "Unsecured consumer financing for medical, education, and consumer electronics loans. True default rates concealed by automated churning until RBI mandated explicit NPA disclosures.",
        "safe_alternative_recommendation": "Democratized SEBI ₹10K Face-Value Senior Secured NCDs or 364D Treasury Bills.",
        "audit_matrix_json": json.dumps({
            "regulatory_license": "Regulated NBFC-P2P",
            "rbi_compliance_action": "Compelled to remove instant liquidity claims",
            "underlying_borrowers": "Prime and near-prime consumer loans",
            "capital_risk": "Moderate-to-High credit risk with zero collateral security"
        })
    },
    {
        "product_id": "UNRATED_NBFC_FD",
        "product_name": "Unrated / Sub-Investment Grade Corporate FD",
        "category": "UNRATED_NBFC_DEPOSIT",
        "promoted_yield_pct": 11.00,
        "danger_score": 85,
        "regulatory_status": "HIGH_DEFAULT_RISK",
        "counterparty_risk_level": "HIGH",
        "principal_guarantee_validity": False,
        "rbi_warning_circular": "RBI NBFC Acceptance of Public Deposits Directions",
        "liquidity_lock_months": 36,
        "precedent_losses_summary": "Precedents like DHFL, IL&FS, and Reliance Capital where fixed deposit holders suffered up to 70% haircuts over 4-year legal insolvency proceedings.",
        "safe_alternative_recommendation": "AAA Rated PSU Bonds (REC, PFC) or Scheduled Commercial Bank FDs within DICGC limits.",
        "audit_matrix_json": json.dumps({
            "regulatory_license": "NBFC-Deposit Taking",
            "bankruptcy_remoteness": "Unsecured creditor status under IBC 2016",
            "dicgc_insurance": "Zero coverage (DICGC applies ONLY to scheduled banks)",
            "capital_risk": "Catastrophic principal loss upon corporate liquidity crunch"
        })
    },
    {
        "product_id": "SCHEDULED_BANK_FD",
        "product_name": "Scheduled Commercial Bank FD (HDFC / SBI / ICICI)",
        "category": "SCHEDULED_COMMERCIAL_BANK",
        "promoted_yield_pct": 7.10,
        "danger_score": 8,
        "regulatory_status": "DICGC_INSURED_5LAKH",
        "counterparty_risk_level": "MINIMAL_SOVEREIGN",
        "principal_guarantee_validity": True,
        "rbi_warning_circular": "Statutory Deposit Insurance Coverage Act (DICGC)",
        "liquidity_lock_months": 12,
        "precedent_losses_summary": "100% capital safety for deposits up to ₹5,00,000 per depositor per bank backed by DICGC sovereign guarantee. D-SIBs (SBI, HDFC, ICICI) are systemically backed.",
        "safe_alternative_recommendation": "Gold standard for absolute capital protection up to ₹5 Lakhs.",
        "audit_matrix_json": json.dumps({
            "regulatory_license": "Scheduled Commercial Bank (RBI Regulated)",
            "dicgc_insurance": "₹5,00,000 statutory insurance backed by RBI subsidiary",
            "capital_risk": "Near Zero nominal risk (subject to inflation tax drag)"
        })
    }
]


def save_alternative_yield_product(prod: Dict[str, Any]) -> bool:
    """Inserts or updates an alternative yield product evaluation."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url())

    try:
        mat_json = prod.get("audit_matrix_json", "{}")
        if isinstance(mat_json, dict):
            mat_json = json.dumps(mat_json)

        if is_pg:
            query = f"""
                INSERT INTO alternative_yield_products (
                    product_id, product_name, category, promoted_yield_pct,
                    danger_score, regulatory_status, counterparty_risk_level,
                    principal_guarantee_validity, rbi_warning_circular,
                    liquidity_lock_months, precedent_losses_summary,
                    safe_alternative_recommendation, audit_matrix_json, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, now())
                ON CONFLICT (product_id) DO UPDATE SET
                    product_name = EXCLUDED.product_name,
                    category = EXCLUDED.category,
                    promoted_yield_pct = EXCLUDED.promoted_yield_pct,
                    danger_score = EXCLUDED.danger_score,
                    regulatory_status = EXCLUDED.regulatory_status,
                    counterparty_risk_level = EXCLUDED.counterparty_risk_level,
                    principal_guarantee_validity = EXCLUDED.principal_guarantee_validity,
                    rbi_warning_circular = EXCLUDED.rbi_warning_circular,
                    liquidity_lock_months = EXCLUDED.liquidity_lock_months,
                    precedent_losses_summary = EXCLUDED.precedent_losses_summary,
                    safe_alternative_recommendation = EXCLUDED.safe_alternative_recommendation,
                    audit_matrix_json = EXCLUDED.audit_matrix_json,
                    updated_at = now();
            """
        else:
            query = f"""
                INSERT INTO alternative_yield_products (
                    product_id, product_name, category, promoted_yield_pct,
                    danger_score, regulatory_status, counterparty_risk_level,
                    principal_guarantee_validity, rbi_warning_circular,
                    liquidity_lock_months, precedent_losses_summary,
                    safe_alternative_recommendation, audit_matrix_json, updated_at
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, datetime('now'))
                ON CONFLICT (product_id) DO UPDATE SET
                    product_name = excluded.product_name,
                    category = excluded.category,
                    promoted_yield_pct = excluded.promoted_yield_pct,
                    danger_score = excluded.danger_score,
                    regulatory_status = excluded.regulatory_status,
                    counterparty_risk_level = excluded.counterparty_risk_level,
                    principal_guarantee_validity = excluded.principal_guarantee_validity,
                    rbi_warning_circular = excluded.rbi_warning_circular,
                    liquidity_lock_months = excluded.liquidity_lock_months,
                    precedent_losses_summary = excluded.precedent_losses_summary,
                    safe_alternative_recommendation = excluded.safe_alternative_recommendation,
                    audit_matrix_json = excluded.audit_matrix_json,
                    updated_at = datetime('now');
            """
        params = (
            prod["product_id"].upper(),
            prod["product_name"],
            prod["category"],
            float(prod["promoted_yield_pct"]),
            int(prod.get("danger_score", 50)),
            prod["regulatory_status"],
            prod["counterparty_risk_level"],
            bool(prod.get("principal_guarantee_validity", False)),
            prod.get("rbi_warning_circular", ""),
            int(prod.get("liquidity_lock_months", 0)),
            prod.get("precedent_losses_summary", ""),
            prod.get("safe_alternative_recommendation", ""),
            mat_json,
        )
        cursor.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving alternative yield product {prod.get('product_id')}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_all_safety_radar_products(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all tracked alternative yield products sorted by danger score descending."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        where_clause = f"WHERE category = {p}" if category else ""
        query = f"""
            SELECT id, product_id, product_name, category, promoted_yield_pct,
                   danger_score, regulatory_status, counterparty_risk_level,
                   principal_guarantee_validity, rbi_warning_circular,
                   liquidity_lock_months, precedent_losses_summary,
                   safe_alternative_recommendation, audit_matrix_json, updated_at
            FROM alternative_yield_products
            {where_clause}
            ORDER BY danger_score DESC;
        """
        if category:
            cursor.execute(query, (category,))
        else:
            cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            logger.info("Alternative yield products table is empty. Initializing baseline products...")
            for prod in DEFAULT_ALTERNATIVE_YIELD_PRODUCTS:
                save_alternative_yield_product(prod)
            if category:
                return [x for x in DEFAULT_ALTERNATIVE_YIELD_PRODUCTS if x["category"] == category]
            return DEFAULT_ALTERNATIVE_YIELD_PRODUCTS

        results = []
        for r in rows:
            mat = {}
            if r[13]:
                try:
                    mat = json.loads(r[13])
                except Exception:
                    mat = {}

            results.append({
                "id": r[0],
                "product_id": r[1],
                "product_name": r[2],
                "category": r[3],
                "promoted_yield_pct": float(r[4]),
                "danger_score": int(r[5]),
                "regulatory_status": r[6],
                "counterparty_risk_level": r[7],
                "principal_guarantee_validity": bool(r[8]),
                "rbi_warning_circular": r[9] or "",
                "liquidity_lock_months": int(r[10]),
                "precedent_losses_summary": r[11] or "",
                "safe_alternative_recommendation": r[12] or "",
                "audit_matrix": mat,
                "updated_at": str(r[14]),
            })
        return results
    except Exception as e:
        logger.error(f"Error fetching safety radar products: {e}")
        return DEFAULT_ALTERNATIVE_YIELD_PRODUCTS
    finally:
        cursor.close()
        conn.close()
