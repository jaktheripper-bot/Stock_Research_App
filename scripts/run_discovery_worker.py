#!/usr/bin/env python3
"""
Morning Discovery Reel Worker (Option B: Full Grounded Synthesis with Historical Data).

Nightly/batch automation script:
1. Screens and curates 10-15 under-the-radar equities across diverse sectors.
2. Ensures institutional-grade 7-pillar grounded research reports exist for all cohort members.
3. Persists the curated daily edition to PostgreSQL/SQLite discovery_reel repository.
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
from core.db.reports import get_report_by_ticker_sync
from core.db.discovery import save_discovery_reel, get_active_discovery_reel
from core.analysis.discovery import curate_morning_discovery_cohort
from core.analysis.engine import generate_stock_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("discovery_worker")


def run_discovery_pipeline(
    target_count: int = 12,
    edition_date: str = None,
    dry_run: bool = False,
    force_synthesis: bool = False
):
    init_db()
    if not edition_date:
        edition_date = datetime.now(IST).strftime("%Y-%m-%d")

    logger.info(f"🌅 Initiating Morning Discovery Reel pipeline for edition date: {edition_date}")
    logger.info(f"Target count: {target_count} under-the-radar equities across diverse sectors.")

    # 1. Screen and curate cohort
    cohort = curate_morning_discovery_cohort(target_count=target_count)
    if not cohort:
        logger.error("Screening engine returned 0 candidate stocks. Pipeline aborted.")
        return False

    logger.info(f"Successfully selected {len(cohort)} candidates across multiple sectors:")
    for idx, item in enumerate(cohort, start=1):
        logger.info(
            f"  {idx:2d}. {item['ticker']:<12} | {item['sector']:<25} | ₹{item['current_price']:<9.2f} | "
            f"ROCE: {item['roce_pct']}% | D/E: {item['debt_to_equity']}"
        )

    # 2. Persist cohort to discovery_reel repository immediately so it's live
    saved_count = save_discovery_reel(cohort, edition_date=edition_date)
    logger.info(f"💾 Persisted {saved_count} equities to Morning Discovery Reel for edition {edition_date}.")

    if dry_run:
        logger.info("Dry-run mode active. Skipping report synthesis.")
        return True

    # 3. Option B: Full Grounded Synthesis with Historical Data
    # Ensure every cohort member has a valid 7-pillar research report archived in the database
    synthesized_count = 0
    reused_count = 0

    for item in cohort:
        ticker = item["ticker"]
        try:
            existing = get_report_by_ticker_sync(ticker)
            needs_synthesis = force_synthesis or not existing or not existing.get("report_text")

            # Check staleness if existing
            if not needs_synthesis and existing.get("created_at"):
                # If existing report is older than 14 days, refresh
                try:
                    rep_date_str = str(existing.get("created_at"))[:10]
                    rep_dt = datetime.strptime(rep_date_str, "%Y-%m-%d")
                    age_days = (datetime.now() - rep_dt).days
                    if age_days > 14:
                        logger.info(f"Archived report for {ticker} is {age_days} days old (>14d threshold). Refreshing...")
                        needs_synthesis = True
                except Exception:
                    pass

            if needs_synthesis:
                logger.info(f"⚡ Synthesizing full 7-pillar grounded dossier for {ticker}...")
                report_md = generate_stock_report(ticker, use_grounding=True)
                if report_md and len(report_md.strip()) >= 500:
                    logger.info(f"✅ Successfully archived grounded dossier for {ticker} ({len(report_md)} chars).")
                    synthesized_count += 1
                else:
                    logger.warning(f"⚠️ Synthesis for {ticker} generated shorter than expected response.")
            else:
                logger.info(f"⚡ Reusing verified archived dossier for {ticker} (0 credit burn).")
                reused_count += 1

        except Exception as synth_err:
            logger.error(f"Error during report synthesis for {ticker}: {synth_err}")

    # 3. Persist cohort to discovery_reel repository
    saved_count = save_discovery_reel(cohort, edition_date=edition_date)
    logger.info(
        f"🎉 Morning Discovery Reel edition {edition_date} complete! "
        f"Saved: {saved_count} equities. Dossiers Synthesized: {synthesized_count}, Reused: {reused_count}."
    )
    return saved_count > 0


def main():
    parser = argparse.ArgumentParser(description="Morning Discovery Reel Batch Worker")
    parser.add_argument("--count", type=int, default=12, help="Target number of stocks in cohort (10-15)")
    parser.add_argument("--date", type=str, default=None, help="Edition date in YYYY-MM-DD format")
    parser.add_argument("--dry-run", action="store_true", help="Run screening without archiving or generating reports")
    parser.add_argument("--force", action="store_true", help="Force new AI synthesis for all stocks regardless of cache")

    args = parser.parse_args()
    success = run_discovery_pipeline(
        target_count=args.count,
        edition_date=args.date,
        dry_run=args.dry_run,
        force_synthesis=args.force
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
