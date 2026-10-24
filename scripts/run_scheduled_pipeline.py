#!/usr/bin/env python3
"""
Scheduled Multi-Asset Report & Update Pipeline Runner.
Executes autonomously in the cloud (GitHub Actions Cron / Render Failover) against Supabase PostgreSQL.
Supports:
  --mode morning   (08:30 Stock Ingest, 08:45 Discovery Reel, 09:00 MSME Cohort)
  --mode nightly   (23:15 AMFI NAV & ETF Sync, Sovereign Curve, Multi-Asset Scan, 23:30 Fund Audit)
  --mode all       (Runs both morning and nightly workflows)
"""
import argparse
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Setup environment path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.db.connection import init_db
from core.db.distributed_lock import job_lease, prune_zombie_leases
from core.db.agent_sessions import record_autonomous_event
from core.logging_config import setup_logging, flush_betterstack_logs

IST = ZoneInfo("Asia/Kolkata")
DAILY_LEASE_TTL_SECONDS = 72000  # 20 hours: prevents duplicate runs across cloud workers on the same IST date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("equity_research.scheduled_pipeline")


def run_morning_pipeline(date_str: str, force: bool = False) -> dict:
    """Executes the pre-market morning ingestion and screening pipeline."""
    logger.info(f"Starting Morning Multi-Asset Pipeline for {date_str}...")
    results = {}
    prune_zombie_leases()

    # 1. 08:30 AM IST: Daily 15-Stock Ingestion & Mutual Fund Look-Through Saturation
    from core.analysis.daily_stock_ingestion import ingest_daily_stock_cohort
    lease_name = f"mf_stock_ingest_{date_str}"
    with job_lease(lease_name, ttl_seconds=DAILY_LEASE_TTL_SECONDS, release_on_exit=False) as acquired:
        if acquired or force:
            logger.info("Executing Phase 1: Daily 15-Stock MF Constituent Ingestion...")
            res = ingest_daily_stock_cohort(edition_date=date_str, count=15, skip_gemini=False)
            results["stock_ingestion"] = res
            logger.info(f"Phase 1 Complete: {res.get('status')} ({len(res.get('ingested_stocks', []))} equities).")
        else:
            logger.info(f"Lease for {lease_name} held by another worker. Skipping Phase 1.")
            results["stock_ingestion"] = "SKIPPED_LEASE_HELD"

    # 2. 08:45 AM / 09:00 AM IST: Discovery Reel Morning Screening
    from scripts.run_discovery_worker import run_discovery_pipeline
    lease_name = f"discovery_reel_{date_str}"
    with job_lease(lease_name, ttl_seconds=DAILY_LEASE_TTL_SECONDS, release_on_exit=False) as acquired:
        if acquired or force:
            logger.info("Executing Phase 2: Discovery Reel Screening & Dossier Verification...")
            success = run_discovery_pipeline(
                target_count=15,
                edition_date=date_str,
                dry_run=False,
                force_synthesis=False,
            )
            results["discovery_reel"] = "SUCCESS" if success else "FAILED"
            logger.info(f"Phase 2 Complete: Discovery reel {results['discovery_reel']}.")
        else:
            logger.info(f"Lease for {lease_name} held by another worker. Skipping Phase 2.")
            results["discovery_reel"] = "SKIPPED_LEASE_HELD"

    # 3. 09:00 AM IST: Daily Unlisted MSME Cohort Ingestion
    from core.msme.daily_ingest import ingest_daily_msme_cohort
    lease_name = f"msme_daily_ingest_{date_str}"
    with job_lease(lease_name, ttl_seconds=DAILY_LEASE_TTL_SECONDS, release_on_exit=False) as acquired:
        if acquired or force:
            logger.info("Executing Phase 3: Daily MSME 15-Firm Cohort Ingestion...")
            msme_count = ingest_daily_msme_cohort(date_str, 15)
            results["msme_ingest"] = f"INGESTED_{msme_count}"
            logger.info(f"Phase 3 Complete: Ingested {msme_count} MSME firms.")
        else:
            logger.info(f"Lease for {lease_name} held by another worker. Skipping Phase 3.")
            results["msme_ingest"] = "SKIPPED_LEASE_HELD"

    record_autonomous_event(
        event_type="MORNING_PIPELINE_COMPLETE",
        ticker="MULTI_ASSET",
        trigger_source="SCHEDULED_RUNNER",
        action_taken=f"Executed morning pipeline for {date_str}",
        summary=f"Stock Ingest: {results.get('stock_ingestion')}, Discovery: {results.get('discovery_reel')}, MSME: {results.get('msme_ingest')}",
        metadata=results,
    )
    return results


def run_nightly_pipeline(date_str: str, force: bool = False) -> dict:
    """Executes the post-market nightly surveillance and synchronization pipeline."""
    logger.info(f"Starting Nightly Multi-Asset Pipeline for {date_str}...")
    results = {}
    prune_zombie_leases()

    # 1. 23:15 IST: AMFI Daily NAV Feed & Scheme Master Ingestion
    from core.ingestion.amfi import ingest_amfi_daily_feed
    lease_name = f"amfi_nav_sync_{date_str}"
    with job_lease(lease_name, ttl_seconds=DAILY_LEASE_TTL_SECONDS, release_on_exit=False) as acquired:
        if acquired or force:
            logger.info("Executing Nightly Phase 1: AMFI Daily NAV & Master Sync...")
            amfi_res = ingest_amfi_daily_feed(limit=None, direct_growth_only=True)
            results["amfi_sync"] = amfi_res
            logger.info("Nightly Phase 1 Complete: AMFI sync finished.")
        else:
            logger.info(f"Lease for {lease_name} held by another worker. Skipping AMFI Sync.")
            results["amfi_sync"] = "SKIPPED_LEASE_HELD"

    # 2. National ETF Matrix Ingestion
    from core.ingestion.etf_ingest import ingest_all_amfi_etfs
    lease_name = f"etf_matrix_sync_{date_str}"
    with job_lease(lease_name, ttl_seconds=DAILY_LEASE_TTL_SECONDS, release_on_exit=False) as acquired:
        if acquired or force:
            logger.info("Executing Nightly Phase 2: National ETF Matrix Synchronization...")
            etf_res = ingest_all_amfi_etfs(force_refresh=True)
            results["etf_sync"] = etf_res
            logger.info(f"Nightly Phase 2 Complete: Synced {etf_res.get('persisted_to_db', 0)} ETFs.")
        else:
            logger.info(f"Lease for {lease_name} held by another worker. Skipping ETF Sync.")
            results["etf_sync"] = "SKIPPED_LEASE_HELD"

    # 3. Sovereign Curve & Benchmarks Refresh
    from core.db.sovereign import refresh_daily_sovereign_benchmarks
    lease_name = f"sovereign_sync_{date_str}"
    with job_lease(lease_name, ttl_seconds=DAILY_LEASE_TTL_SECONDS, release_on_exit=False) as acquired:
        if acquired or force:
            logger.info("Executing Nightly Phase 3: Sovereign Curve & SDL Spreads Refresh...")
            sov_res = refresh_daily_sovereign_benchmarks(date_str)
            results["sovereign_sync"] = sov_res
            logger.info(f"Nightly Phase 3 Complete: Refreshed {sov_res.get('benchmarks_updated', 0)} benchmarks.")
        else:
            logger.info(f"Lease for {lease_name} held by another worker. Skipping Sovereign Sync.")
            results["sovereign_sync"] = "SKIPPED_LEASE_HELD"

    # 4. Multi-Asset Monitoring Scan
    from core.analysis.asset_scanner import run_comprehensive_asset_scan
    lease_name = f"asset_scan_{date_str}"
    with job_lease(lease_name, ttl_seconds=DAILY_LEASE_TTL_SECONDS, release_on_exit=False) as acquired:
        if acquired or force:
            logger.info("Executing Nightly Phase 4: Multi-Asset Surveillance Scan...")
            scan_res = run_comprehensive_asset_scan("ALL_ASSETS", "nightly_pipeline")
            results["asset_scan"] = scan_res
            logger.info("Nightly Phase 4 Complete: Surveillance scan finished.")
        else:
            logger.info(f"Lease for {lease_name} held by another worker. Skipping Surveillance Scan.")
            results["asset_scan"] = "SKIPPED_LEASE_HELD"

    # 5. 23:30 IST: Mutual Fund Accounting Checkor
    from core.analysis.fund_overlap_auditor import audit_single_fund_daily
    lease_name = f"fund_audit_{date_str}"
    with job_lease(lease_name, ttl_seconds=DAILY_LEASE_TTL_SECONDS, release_on_exit=False) as acquired:
        if acquired or force:
            logger.info("Executing Nightly Phase 5: Mutual Fund Rotation Look-Through Audit...")
            fund_res = audit_single_fund_daily(scheme_code=None, force_refresh_stocks=False)
            results["fund_audit"] = fund_res
            if isinstance(fund_res, dict) and fund_res.get("scheme_code"):
                record_autonomous_event(
                    event_type="DAILY_FUND_AUDIT",
                    ticker=fund_res.get("scheme_code", "UNKNOWN"),
                    trigger_source="SCHEDULED_RUNNER",
                    action_taken="7_PILLAR_LOOKTHROUGH_AUDIT",
                    summary=f"Automated 7-pillar look-through audit completed for {fund_res.get('scheme_name')} ({fund_res.get('scheme_code')}).",
                    metadata={
                        "composite_health_score": fund_res.get("composite_health_score"),
                        "weighted_moat_score": fund_res.get("weighted_moat_score"),
                        "accounting_risk_index": fund_res.get("accounting_risk_index"),
                        "margin_of_safety_pct": fund_res.get("margin_of_safety_pct"),
                    },
                )
            logger.info(f"Nightly Phase 5 Complete: Audited fund {fund_res.get('scheme_code') if fund_res else 'none'}.")
        else:
            logger.info(f"Lease for {lease_name} held by another worker. Skipping Fund Audit.")
            results["fund_audit"] = "SKIPPED_LEASE_HELD"

    record_autonomous_event(
        event_type="NIGHTLY_PIPELINE_COMPLETE",
        ticker="MULTI_ASSET",
        trigger_source="SCHEDULED_RUNNER",
        action_taken=f"Executed nightly pipeline for {date_str}",
        summary=f"AMFI: {'OK' if results.get('amfi_sync') != 'SKIPPED_LEASE_HELD' else 'SKIPPED'}, ETFs: {'OK' if results.get('etf_sync') != 'SKIPPED_LEASE_HELD' else 'SKIPPED'}, Sovereign: {'OK' if results.get('sovereign_sync') != 'SKIPPED_LEASE_HELD' else 'SKIPPED'}",
        metadata=results,
    )
    return results


def dispatch_heartbeat(mode: str) -> None:
    """Dispatches an uptime heartbeat to Better Stack if configured."""
    from core.config import get_secret
    import ssl
    import urllib.request
    import certifi

    heartbeat_url = (
        get_secret("BETTER_STACK_HEARTBEAT_URL")
        or os.environ.get("BETTER_STACK_HEARTBEAT_URL")
        or ""
    ).strip()
    if not heartbeat_url:
        return

    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(
            heartbeat_url,
            headers={"User-Agent": f"Moatnomics-Pipeline-Heartbeat/{mode}"},
        )
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            logger.info("Heartbeat successfully dispatched to Better Stack (status=%s)", resp.status)
    except Exception as e:
        logger.warning("Better Stack heartbeat notice: %s", e)


def main():
    parser = argparse.ArgumentParser(description="Multi-Asset Scheduled Pipeline Runner")
    parser.add_argument(
        "--mode",
        choices=["morning", "nightly", "all"],
        default="all",
        help="Pipeline mode to execute (default: all)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date string in YYYY-MM-DD format (default: today in IST)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force execution even if distributed job lease is locked",
    )
    args = parser.parse_args()

    setup_logging()
    init_db()

    now_ist = datetime.now(IST)
    date_str = args.date or now_ist.strftime("%Y-%m-%d")

    logger.info(
        f"Initializing Multi-Asset Scheduled Pipeline [Mode: {args.mode.upper()}, Date: {date_str}, Force: {args.force}]"
    )
    try:
        summary = {}
        if args.mode in ("morning", "all"):
            summary["morning"] = run_morning_pipeline(date_str, force=args.force)

        if args.mode in ("nightly", "all"):
            summary["nightly"] = run_nightly_pipeline(date_str, force=args.force)

        logger.info("Multi-Asset Scheduled Pipeline execution finished.")
        dispatch_heartbeat(args.mode)
        return 0
    finally:
        flush_betterstack_logs()


if __name__ == "__main__":
    sys.exit(main())
