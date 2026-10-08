#!/usr/bin/env python3
"""Ingest real monthly portfolio disclosures for the top-N mutual funds by AUM.

Usage:
    python scripts/ingest_mf_portfolios.py --status                # what is available per AMC
    python scripts/ingest_mf_portfolios.py --dry-run               # parse + match, write nothing
    python scripts/ingest_mf_portfolios.py --target 150            # ingest into reports.db
    python scripts/ingest_mf_portfolios.py --amc nippon            # restrict to one AMC
    python scripts/ingest_mf_portfolios.py --target 150 --audit    # also build forensic dossiers

For AMCs without a verified automated URL, download their latest monthly portfolio workbook
and drop it in data/amc_portfolios/<amc_key>/ (keys are listed in core/ingestion/amc_sources.json).
"""

import argparse
import json
import logging
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.db.connection import init_db
from core.ingestion.mf_portfolio_ingest import ingest_top_funds, load_sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=int, default=150, help="number of funds to ingest (default 150)")
    ap.add_argument("--amc", action="append", help="restrict to AMC key (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="parse and match only; do not write to the DB")
    ap.add_argument("--audit", action="store_true", help="run forensic look-through audit on ingested funds")
    ap.add_argument("--status", action="store_true", help="show AMC source status and exit")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args()

    if args.status:
        for key, cfg in load_sources().items():
            state = "AUTOMATED" if cfg.get("url_template") else "manual upload"
            print(f"{key:15s} {state}")
        return 0

    init_db()
    report = ingest_top_funds(target=args.target, dry_run=args.dry_run, only_amcs=args.amc, audit=args.audit)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    print(f"\nIngested {report['ingested_count']} / {report['target']} funds"
          f"{' (dry run)' if report['dry_run'] else ''} in {report['duration_seconds']}s")
    for f in report["ingested"]:
        print(f"  #{f['aum_rank']:<4} {f['scheme_code']:>8}  {f['scheme_name'][:58]:58s} "
              f"{f['holdings_count']:>4} holdings  as on {f['as_on']}")
    print("\nAMC source status:")
    for k, v in report["amc_status"].items():
        print(f"  {k:15s} {v}")
    print(f"\nSkipped {report['skipped_count']} ranked funds (no data / no match). "
          f"Re-run with --json for the per-fund reasons.")
    if not report["target_met"]:
        print(f"\n⚠ Target not met: only {report['ingested_count']} funds had obtainable portfolios. "
              f"Add AMC workbooks to data/amc_portfolios/<amc_key>/ and re-run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
