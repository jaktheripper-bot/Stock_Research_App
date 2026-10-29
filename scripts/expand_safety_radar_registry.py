#!/usr/bin/env python3
"""
Expands `/safety-radar` with structural RBI/SEBI regulatory risk archetypes
(Aug 2024 RBI P2P NBFC Master Direction tightenings, Unlisted Invoice Discounting,
Basel III AT1 Perpetual PONV Write-Downs, Fractional Real Estate SPV Syndications).
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ENABLE_BACKGROUND_SCHEDULERS"] = "0"

from core.db.safety_radar import save_alternative_yield_product

NEW_STRUCTURAL_ARCHETYPES = [
    {
        "product_id": "ARCH_RBI_P2P_2024",
        "product_name": "NBFC-P2P Secondary Tenure / Closed-Pool Schemes",
        "category": "P2P_LENDING",
        "advertised_yield_pct": 12.0,
        "regulatory_status": "RBI_RESTRICTED_STRUCTURE",
        "danger_score": 86,
        "liquidity_lock_months": 12,
        "rbi_warning_circular": "RBI/2024-25/63 DoR.FIN.REC.35/03.10.124/2024-25 (Master Direction — NBFC-P2P Amendment, 16 Aug 2024)",
        "counterparty_risk": "100% unsecured retail borrower credit risk borne directly by lender; RBI Aug-2024 Master Direction prohibits credit enhancement, assured-return framing, and instant T+0 liquidity matching.",
        "bankruptcy_reality": "Zero DICGC insurance; platform escrow passes borrower defaults directly to lender principal.",
        "safe_alternative_recommendation": "Listed Senior Secured AAA/AA Corporate NCDs (₹10,000 SEBI face value) or RBI Retail Direct Treasury Bills.",
    },
    {
        "product_id": "ARCH_UNLISTED_INV_DISC",
        "product_name": "Unregulated Unlisted Invoice Discounting / Trade Receivables Pools",
        "category": "UNREGULATED_CREDIT",
        "advertised_yield_pct": 13.5,
        "regulatory_status": "UNREGULATED_OUTSIDE_SEBI_SDI",
        "danger_score": 91,
        "liquidity_lock_months": 3,
        "rbi_warning_circular": "SEBI (Issue and Listing of Securitised Debt Instruments and Security Receipts) Regulations vs. Unlisted Bilateral Factoring",
        "counterparty_risk": "Unlike listed SEBI Securitised Debt Instruments (SDIs) with independent trustees and rating rationales, bilateral invoice notes carry bilateral fraud, double-pledging, and platform insolvency risk.",
        "bankruptcy_reality": "Unsecured operational claim in IBC waterfall behind secured working-capital consortium banks.",
        "safe_alternative_recommendation": "Exchange-listed SEBI-regulated SDIs with independent debenture trustees and CRISIL/ICRA credit ratings.",
    },
    {
        "product_id": "ARCH_BASEL3_AT1_PONV",
        "product_name": "Basel III Additional Tier-1 (AT1) Bank Perpetual Bonds",
        "category": "HYBRID_BANK_CAPITAL",
        "advertised_yield_pct": 8.6,
        "regulatory_status": "RBI_BASEL_III_LOSS_ABSORBING",
        "danger_score": 76,
        "liquidity_lock_months": 60,
        "rbi_warning_circular": "RBI Master Circular on Basel III Capital Regulations (Annex 4 — Loss Absorption at Point of Non-Viability) & SEBI AT1 Valuation Circular",
        "counterparty_risk": "Discretionary coupon skipping and permanent principal write-down at RBI Point of Non-Viability (PONV) even prior to equity wipeout (as precedented in March 2020).",
        "bankruptcy_reality": "Subordinated below all depositors, senior bondholders, and Tier-2 capital instruments.",
        "safe_alternative_recommendation": "Scheduled Commercial Bank Fixed Deposits (DICGC insured up to ₹5 Lakh) or Senior Unsubordinated PSU Infrastructure Bonds.",
    },
    {
        "product_id": "ARCH_SEBI_SM_REIT_CHECK",
        "product_name": "Fractional Real Estate Portals Outside SEBI SM REIT Registration",
        "category": "FRACTIONAL_REAL_ESTATE",
        "advertised_yield_pct": 10.5,
        "regulatory_status": "UNREGISTERED_SPV_SYNDICATION",
        "danger_score": 84,
        "liquidity_lock_months": 36,
        "rbi_warning_circular": "SEBI (Real Estate Investment Trusts) (Amendment) Regulations, 2024 — Mandatory SM REIT Migration & Registration Framework",
        "counterparty_risk": "Unlisted private-limited SPV compulsorily convertible debentures lack exchange price discovery, mandatory 95% completed-asset cash-flow rules, and independent REIT trustee oversight.",
        "bankruptcy_reality": "Illiquid private SPV shares with severe exit discounts unless migrated under SEBI (REIT) SM REIT 2024 regulations.",
        "safe_alternative_recommendation": "SEBI-registered Mainboard REITs, InvITs, or migrated SM REITs with >=95% completed-asset NDCF payout mandates.",
    },
]


def run(apply: bool = False) -> None:
    for item in NEW_STRUCTURAL_ARCHETYPES:
        print(f"[{'APPLY' if apply else 'DRY-RUN'}] {item['product_id']}: {item['product_name']} (Danger={item['danger_score']}/100)")
        if apply:
            ok = save_alternative_yield_product(item)
            if not ok:
                raise RuntimeError(f"Failed persisting safety-radar archetype: {item['product_id']}")
    if apply:
        import json as _json
        import sqlite3
        from core.db.connection import get_db_path
        sq_path = Path(get_db_path())
        if sq_path.exists():
            sq_conn = sqlite3.connect(str(sq_path))
            try:
                for item in NEW_STRUCTURAL_ARCHETYPES:
                    cp_prose = str(item.get("counterparty_risk") or "").strip()
                    bk_prose = str(item.get("bankruptcy_reality") or "").strip()
                    prec_loss = " ".join(
                        p for p in (cp_prose, f"Bankruptcy reality: {bk_prose}" if bk_prose else "") if p
                    ).strip()
                    mat_json = _json.dumps({"counterparty_risk": cp_prose, "bankruptcy_reality": bk_prose})
                    sq_conn.execute(
                        """
                        INSERT INTO alternative_yield_products (
                            product_id, product_name, category, promoted_yield_pct,
                            danger_score, regulatory_status, counterparty_risk_level,
                            principal_guarantee_validity, rbi_warning_circular,
                            liquidity_lock_months, precedent_losses_summary,
                            safe_alternative_recommendation, audit_matrix_json,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, 'HIGH', 0, ?, ?, ?, ?, ?, (datetime('now', '+5 hours', '+30 minutes') || '+05:30'))
                        ON CONFLICT(product_id) DO UPDATE SET
                            product_name = excluded.product_name,
                            category = excluded.category,
                            promoted_yield_pct = excluded.promoted_yield_pct,
                            danger_score = excluded.danger_score,
                            regulatory_status = excluded.regulatory_status,
                            rbi_warning_circular = excluded.rbi_warning_circular,
                            liquidity_lock_months = excluded.liquidity_lock_months,
                            precedent_losses_summary = excluded.precedent_losses_summary,
                            safe_alternative_recommendation = excluded.safe_alternative_recommendation,
                            audit_matrix_json = excluded.audit_matrix_json,
                            updated_at = (datetime('now', '+5 hours', '+30 minutes') || '+05:30')
                        """,
                        (
                            item["product_id"],
                            item["product_name"],
                            item["category"],
                            item["advertised_yield_pct"],
                            item["danger_score"],
                            item["regulatory_status"],
                            item["rbi_warning_circular"],
                            item["liquidity_lock_months"],
                            prec_loss,
                            item["safe_alternative_recommendation"],
                            mat_json,
                        ),
                    )
                sq_conn.commit()
            finally:
                sq_conn.close()
    print(f"Processed {len(NEW_STRUCTURAL_ARCHETYPES)} structural safety-radar archetypes.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    run(apply=args.apply)

