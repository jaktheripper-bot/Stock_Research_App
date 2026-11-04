#!/usr/bin/env python3
"""Ingest real SEBI monthly portfolio disclosures across public AMCs.

Usage:
    python3 scripts/ingest_mf_portfolios.py --status               # what is available per AMC
    python3 scripts/ingest_mf_portfolios.py --dry-run              # parse + match, write nothing
    python3 scripts/ingest_mf_portfolios.py --all                  # ingest all obtainable funds across AMCs
    python3 scripts/ingest_mf_portfolios.py --target 150           # ingest top 150 obtainable funds
    python3 scripts/ingest_mf_portfolios.py --amc sbi --amc hdfc   # restrict to selected AMCs
    python3 scripts/ingest_mf_portfolios.py --all --audit          # also run look-through audits

For WAF-gated AMCs without an open statutory feed, drop downloaded monthly workbooks into
`data/amc_portfolios/<amc_key>/` (keys listed in `core/ingestion/amc_sources.json`).
"""

import argparse
import json
import logging
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

os.environ.setdefault("ENABLE_BACKGROUND_SCHEDULERS", "0")

from core.db.connection import init_db
from core.ingestion.mf_portfolio_ingest import ingest_top_funds, load_sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=int, default=150, help="number of funds to ingest (default 150)")
    ap.add_argument("--all", action="store_true", help="ingest every matched Direct-Growth scheme across all obtainable AMCs")
    ap.add_argument("--amc", action="append", help="restrict to AMC key (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="parse and match only; do not write to the DB")
    ap.add_argument("--audit", action="store_true", help="run look-through audit on ingested funds")
    ap.add_argument("--status", action="store_true", help="show AMC source status and exit")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args()

    if args.status:
        for key, cfg in load_sources().items():
            state = "AUTOMATED" if (cfg.get("url_template") or cfg.get("adapter")) else "manual upload / API"
            print(f"{key:15s} {state}")
        return 0

    effective_target = 5000 if args.all else args.target

    init_db()
    report = ingest_top_funds(
        target=effective_target,
        dry_run=args.dry_run,
        only_amcs=args.amc,
        audit=args.audit,
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    print(
        f"\nIngested {report['ingested_count']} / {report['target']} funds"
        f"{' (dry run)' if report['dry_run'] else ''} in {report['duration_seconds']}s"
    )
    if report.get("aaum_backfill"):
        print(f"AMFI AAUM Backfill: {report['aaum_backfill']}")
    if report.get("twin_sync"):
        print(f"Legacy Slug Twin Sync: {report['twin_sync']} (raw ISINs resolved={report.get('raw_isins_resolved', 0)})")
    for f in report["ingested"][:80]:
        print(
            f"  #{str(f.get('aum_rank') or '-'):<4} {f['scheme_code']:>8}  {f['scheme_name'][:58]:58s} "
            f"{f['holdings_count']:>4} holdings  as on {f['as_on']}"
        )
    if len(report["ingested"]) > 80:
        print(f"  ... and {len(report['ingested']) - 80} more schemes ingested.")
    print("\nAMC source status:")
    for k, v in report["amc_status"].items():
        print(f"  {k:15s} {v}")
    print(
        f"\nSkipped {report['skipped_count']} ranked funds (no data / no match). "
        f"Re-run with --json for the per-fund reasons."
    )
    if not args.all and not report["target_met"]:
        print(
            f"\nNotice: only {report['ingested_count']} funds had obtainable portfolios. "
            f"Add AMC workbooks to data/amc_portfolios/<amc_key>/ and re-run."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
