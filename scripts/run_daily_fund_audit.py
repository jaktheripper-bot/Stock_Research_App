#!/usr/bin/env python3
"""Daily Autonomous Mutual Fund Forensic Audit Worker.

Rotates through the curated mutual fund universe, executes deep 7-pillar portfolio
look-through aggregation across constituent holdings, synthesizes institutional qualitative
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

from core.db.connection import init_db
from core.db.mutual_funds import (
    get_active_mutual_funds,
    get_fund_forensic_dossier,
    get_next_fund_for_daily_audit,
    seed_default_mutual_funds
)
from core.analysis.fund_forensic_auditor import (
    audit_single_fund_daily,
    compute_fund_forensic_lookthrough
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("fund_audit_worker")


def list_fund_audit_status():
    """Prints table of mutual funds and their current forensic audit status."""
    init_db()
    funds = get_active_mutual_funds()
    print("\n" + "="*95)
    print(f"{'SCHEME CODE':<25} | {'CATEGORY':<20} | {'HEALTH':<7} | {'ASRI':<6} | {'MOS':<6} | {'LAST AUDITED':<19}")
    print("="*95)
    for f in funds:
        code = f.get("scheme_code", "")
        cat = f.get("category", "")[:20]
        dos = get_fund_forensic_dossier(code)
        if dos:
            health = f"{dos.get('composite_health_score', 0):.1f}"
            asri = f"{dos.get('accounting_risk_index', 0):.1f}%"
            mos = f"{dos.get('margin_of_safety_pct', 0):+.1f}%"
            last = str(dos.get("last_audited_at", ""))[:19]
        else:
            health = "N/A"
            asri = "N/A"
            mos = "N/A"
            last = "Pending Initial Audit"
        print(f"{code:<25} | {cat:<20} | {health:<7} | {asri:<6} | {mos:<6} | {last:<19}")
    print("="*95 + "\n")


def run_worker(scheme_code: Optional[str] = None, audit_all: bool = False):
    init_db()
    seed_default_mutual_funds()

    if audit_all:
        funds = get_active_mutual_funds()
        logger.info(f"Running bulk forensic audit for all {len(funds)} funds...")
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
    print("\n" + "="*80)
    print(f"AUDIT COMPLETED: {res['scheme_name']} ({res['scheme_code']})")
    print(f"Composite Health Score: {res['composite_health_score']} / 100")
    print(f"Weighted Moat Score:    {res['weighted_moat_score']} / 100")
    print(f"Accounting Risk (ASRI): {res['accounting_risk_index']}% of portfolio")
    print(f"Margin of Safety (DCF): {res['margin_of_safety_pct']:+.1f}%")
    print(f"Promoter Pledge Risk:   {res['promoter_pledge_exposure_pct']}%")
    print(f"Active Share vs Index:  {res['active_share_pct']}%")
    print("="*80)
    print("\nSYNTHeSIZED INSTITUTIONAL FORENSIC DOSSIER PREVIEW:")
    print(res["dossier_text"][:600] + "\n...\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Mutual Fund Forensic Look-Through Audit Worker")
    parser.add_argument("--scheme", type=str, help="Specific scheme code to audit (e.g. PPFAS_FLEXICAP_DIR)")
    parser.add_argument("--next", action="store_true", help="Audit the next fund in the rotation queue")
    parser.add_argument("--list", action="store_true", help="List all funds and their audit status")
    parser.add_argument("--all", action="store_true", help="Audit all funds in universe sequentially")

    args = parser.parse_args()

    if args.list:
        list_fund_audit_status()
    else:
        run_worker(scheme_code=args.scheme, audit_all=args.all)
