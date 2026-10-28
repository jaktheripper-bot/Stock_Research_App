#!/usr/bin/env python3
"""Daily Autonomous Mutual Fund Accounting Check Worker.

Rotates through the curated mutual fund universe, executes deep 7-pillar portfolio
look-through aggregation across constituent holdings, synthesizes qualitative
dossiers via Gemini AI / deterministic fallback, and archives results to reports.db.

Usage:
    python scripts/run_daily_fund_audit.py --next
    python scripts/run_daily_fund_audit.py --scheme PPFAS_FLEXICAP_DIR
    python scripts/run_daily_fund_audit.py --list
    python scripts/run_daily_fund_audit.py --all
"""

import os
import sys
import argparse
import logging
from typing import Optional

# Ensure project root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.db.connection import init_db, get_db_connection
from core.db.mutual_funds import (
    get_active_mutual_funds,
    get_fund_forensic_dossier,
    get_next_fund_for_daily_audit,
    seed_default_mutual_funds
)
from core.analysis.fund_overlap_auditor import (
    audit_single_fund_daily,
    compute_fund_forensic_lookthrough
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("fund_audit_worker")


def list_fund_audit_status(limit: int = 500):
    """Prints table of mutual funds and their current accounting check status via single batch JOIN."""
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT s.scheme_code,
                   s.category,
                   d.composite_health_score,
                   d.accounting_risk_index,
                   d.margin_of_safety_pct,
                   d.last_audited_at
            FROM mutual_fund_schemes s
            LEFT JOIN fund_forensic_dossiers d ON s.scheme_code = d.scheme_code
            WHERE s.broad_category IN ('EQUITY', 'HYBRID')
            ORDER BY s.aum_crores DESC, s.scheme_name ASC
            LIMIT %s
            """
            if hasattr(cur, "mogrify") or getattr(cur, "_cur", None) is not None
            else """
            SELECT s.scheme_code,
                   s.category,
                   d.composite_health_score,
                   d.accounting_risk_index,
                   d.margin_of_safety_pct,
                   d.last_audited_at
            FROM mutual_fund_schemes s
            LEFT JOIN fund_forensic_dossiers d ON s.scheme_code = d.scheme_code
            WHERE s.broad_category IN ('EQUITY', 'HYBRID')
            ORDER BY s.aum_crores DESC, s.scheme_name ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    print("\n" + "=" * 95)
    print(f"{'SCHEME CODE':<25} | {'CATEGORY':<20} | {'HEALTH':<7} | {'ASRI':<6} | {'MOS':<6} | {'LAST AUDITED':<19}")
    print("=" * 95)
    for row in rows:
        code = str(row[0] or "")
        cat = str(row[1] or "")[:20]
        comp_h_raw = row[2]
        asri_val = row[3]
        mos_val = row[4]
        last_raw = row[5]
        if last_raw is not None:
            comp_h = float(comp_h_raw) if (comp_h_raw is not None and float(comp_h_raw) >= 0) else None
            health = f"{comp_h:.1f}" if comp_h is not None else "Paused"
            asri = f"{float(asri_val):.1f}%" if asri_val is not None else "0.0%"
            mos = f"{float(mos_val):+.1f}%" if mos_val is not None else "+0.0%"
            last = str(last_raw)[:19]
        else:
            health = "N/A"
            asri = "N/A"
            mos = "N/A"
            last = "Pending Initial Audit"
        print(f"{code:<25} | {cat:<20} | {health:<7} | {asri:<6} | {mos:<6} | {last:<19}")
    print("=" * 95 + "\n")


def run_worker(scheme_code: Optional[str] = None, audit_all: bool = False):
    init_db()
    if not get_active_mutual_funds(limit=1):
        seed_default_mutual_funds()

    if audit_all:
        funds = get_active_mutual_funds()
        logger.info(f"Running bulk accounting check for all {len(funds)} funds...")
        for f in funds:
            code = f.get("scheme_code")
            try:
                res = audit_single_fund_daily(code)
                logger.info(f"✓ Audited {code}: Health={res['composite_health_score']}, Moat={res['weighted_moat_score']}, ASRI={res['accounting_risk_index']}%")
            except Exception as e:
                logger.error(f"✗ Failed auditing {code}: {e}")
        return

    target = scheme_code
    if not target:
        next_fund = get_next_fund_for_daily_audit()
        if not next_fund:
            logger.error("No eligible mutual fund found in rotation queue.")
            return
        target = next_fund["scheme_code"]
        logger.info(f"Selected next fund from rotation queue: {target} ({next_fund.get('scheme_name')})")

    logger.info(f"Executing 7-pillar look-through audit on {target}...")
    res = audit_single_fund_daily(target)
    if isinstance(res, dict) and res.get("scheme_code"):
        from core.db.agent_sessions import record_autonomous_event
        record_autonomous_event(
            event_type="DAILY_FUND_AUDIT",
            ticker=res.get("scheme_code", "UNKNOWN"),
            trigger_source="CLI_FUND_AUDIT_WORKER",
            action_taken="7_PILLAR_LOOKTHROUGH_AUDIT",
            summary=f"Automated 7-pillar look-through audit completed for {res.get('scheme_name')} ({res.get('scheme_code')}).",
            metadata={
                "composite_health_score": res.get("composite_health_score"),
                "weighted_moat_score": res.get("weighted_moat_score"),
                "accounting_risk_index": res.get("accounting_risk_index"),
                "margin_of_safety_pct": res.get("margin_of_safety_pct"),
            },
        )
    print("\n" + "="*80)
    print(f"AUDIT COMPLETED: {res['scheme_name']} ({res['scheme_code']})")
    health_disp = f"{res['composite_health_score']:.1f} / 100" if res.get('composite_health_score') is not None else "Paused (Genuine Coverage < 70%)"
    print(f"Composite Health Score: {health_disp}")
    print(f"Weighted Moat Score:    {float(res.get('weighted_moat_score') or 0.0):.1f} / 100")
    print(f"Accounting Risk (ASRI): {float(res.get('accounting_risk_index') or 0.0):.1f}% of portfolio")
    mos_disp = f"{float(res['margin_of_safety_pct']):+.1f}%" if res.get('margin_of_safety_pct') is not None else "+0.0%"
    print(f"Margin of Safety (DCF): {mos_disp}")
    print(f"Promoter Pledge Risk:   {float(res.get('promoter_pledge_exposure_pct') or 0.0):.1f}%")
    print(f"Active Share vs Index:  {float(res.get('active_share_pct') or 0.0):.1f}%")
    print("="*80)
    print("\nSYNTHESIZED FORENSIC DOSSIER PREVIEW:")
    preview_text = (res.get("dossier_text") or "").strip()
    if preview_text:
        print(preview_text[:600] + "\n...\n")
    else:
        print("[Pending Gemini narrative synthesis — quantitative look-through scores archived cleanly]\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Mutual Fund Look-Through Audit Worker")
    parser.add_argument("--scheme", type=str, help="Specific scheme code to audit (e.g. PPFAS_FLEXICAP_DIR)")
    parser.add_argument("--next", action="store_true", help="Audit the next fund in the rotation queue")
    parser.add_argument("--list", action="store_true", help="List all funds and their audit status")
    parser.add_argument("--all", action="store_true", help="Audit all funds in universe sequentially")

    args = parser.parse_args()

    if args.list:
        list_fund_audit_status()
    else:
        run_worker(scheme_code=args.scheme, audit_all=args.all)
