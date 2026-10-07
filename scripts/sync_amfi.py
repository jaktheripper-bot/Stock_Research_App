#!/usr/bin/env python3
"""
Automated AMFI Daily NAV & Scheme Master Synchronization CLI.

Scheduled/nightly background worker:
1. Fetches official AMFI NAVAll.txt feed directly from AMFI India statutory servers.
2. Ingests or updates mutual fund schemes with zero hallucination and complete audit history.
3. Automatically classifies schemes (Equity, Debt, Hybrid, etc.) and links benchmark indices.
"""

import os
import sys
import argparse
import logging
from datetime import datetime

# Ensure project root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.db.connection import init_db, IST
from core.ingestion.amfi import ingest_amfi_daily_feed, fetch_amfi_nav_raw
from core.analysis.asset_scanner import scan_mutual_funds, record_scan_start, record_scan_complete

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sync_amfi")


def main():
    parser = argparse.ArgumentParser(description="Synchronize AMFI Daily NAV feed into database.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of schemes to process (for smoke testing).")
    parser.add_argument("--all-options", action="store_true", help="Include non-Direct/Growth options as well.")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass disk cache and download fresh feed from AMFI.")
    parser.add_argument("--diff-mode", action="store_true", help="Run audit differential scan against asset_scan_runs ledger.")
    args = parser.parse_args()

    init_db()
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    logger.info(f"📊 Starting AMFI NAV & Scheme Master synchronization at {now_ist}...")

    direct_growth_only = not args.all_options

    if args.diff_mode:
        scan_id = record_scan_start("MUTUAL_FUNDS", triggered_by="cli_sync_amfi")
        try:
            summary = scan_mutual_funds(limit=args.limit)
            record_scan_complete(
                scan_id=scan_id,
                status="completed",
                items_scanned=summary["scanned"],
                items_added=summary["new"],
                items_updated=summary["changed"],
                details=summary
            )
            logger.info(f"✅ AMFI diff scan completed successfully: {summary['scanned']} scanned, {summary['new']} new, {summary['changed']} changed.")
            sys.exit(0)
        except Exception as e:
            record_scan_complete(scan_id=scan_id, status="failed", error_message=str(e))
            logger.error(f"❌ AMFI diff scan failed: {e}")
            sys.exit(1)
    else:
        try:
            if args.force_refresh:
                fetch_amfi_nav_raw(force_refresh=True)
            res = ingest_amfi_daily_feed(limit=args.limit, direct_growth_only=direct_growth_only)
            logger.info(
                f"✅ AMFI Ingestion complete! Total parsed: {res['total_parsed']}, "
                f"Upserted: {res['upserted']}, Errors: {res['errors']} in {res['duration_seconds']}s. "
                f"Feed Date: {res['feed_date']}"
            )
            sys.exit(0)
        except Exception as e:
            logger.error(f"❌ AMFI ingestion pipeline failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
