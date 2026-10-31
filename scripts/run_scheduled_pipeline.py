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


def _phase_status(value) -> str:
    """Maps a phase result to OK / SKIPPED / FAILED for event summaries."""
    if value == "SKIPPED_LEASE_HELD":
        return "SKIPPED"
    if isinstance(value, str) and value.startswith("FAILED"):
        return "FAILED"
    return "OK"


def _failed_phases(results: dict) -> list:
    """Returns the result keys of every phase that failed in a pipeline run."""
    return [key for key, value in results.items() if _phase_status(value) == "FAILED"]


def _run_leased_phase(
    results: dict,
    result_key: str,
    lease_name: str,
    phase_label: str,
    phase_fn,
    force: bool = False,
    ttl_seconds: int = DAILY_LEASE_TTL_SECONDS,
) -> None:
    """Runs one leased pipeline phase in isolation.

    The exception is caught OUTSIDE the job_lease context manager on purpose: job_lease
    must still observe the failure so release_on_failure=True frees the daily lease for a
    same-day retry (local catch-up or a second cloud worker). A failed phase is recorded as
    "FAILED: ..." in results and the remaining phases continue. Nothing is fabricated: the
    failed phase simply has no output for this cycle.
    """
    try:
        with job_lease(lease_name, ttl_seconds=ttl_seconds, release_on_exit=False) as acquired:
            if not (acquired or force):
                logger.info(f"Lease for {lease_name} held by another worker. Skipping {phase_label}.")
                results[result_key] = "SKIPPED_LEASE_HELD"
                return
            logger.info(f"Executing {phase_label}...")
            results[result_key] = phase_fn()
            logger.info(f"{phase_label} complete.")
    except Exception as exc:
        logger.exception(f"{phase_label} failed; continuing with remaining phases: {exc}")
        results[result_key] = f"FAILED: {type(exc).__name__}: {exc}"


def run_morning_pipeline(date_str: str, force: bool = False) -> dict:
    """Executes the pre-market morning ingestion and screening pipeline."""
    logger.info(f"Starting Morning Multi-Asset Pipeline for {date_str}...")
    results = {}
    prune_zombie_leases()

    # 1. 08:30 AM IST: Daily 15-Stock Ingestion & Mutual Fund Look-Through Saturation
    def _stock_ingestion():
        from core.analysis.daily_stock_ingestion import ingest_daily_stock_cohort
        res = ingest_daily_stock_cohort(edition_date=date_str, count=15, skip_gemini=False)
        ingested_n = res.get("ingested_count", len(res.get("ingested_tickers") or res.get("ingested_stocks") or []))
        logger.info(f"Phase 1 result: {res.get('status')} ({ingested_n} equities).")
        return res

    _run_leased_phase(
        results, "stock_ingestion", f"mf_stock_ingest_{date_str}",
        "Phase 1: Daily 15-Stock MF Constituent Ingestion", _stock_ingestion, force=force,
    )

    # 2. 08:45 AM / 09:00 AM IST: Discovery Reel Morning Screening
    def _discovery_reel():
        from scripts.run_discovery_worker import run_discovery_pipeline
        success = run_discovery_pipeline(
            target_count=15,
            edition_date=date_str,
            dry_run=False,
            force_synthesis=False,
        )
        if not success:
            # Raise so job_lease releases the daily lease and a same-day retry can run.
            raise RuntimeError("Discovery pipeline reported an unsuccessful run.")
        return "SUCCESS"

    _run_leased_phase(
        results, "discovery_reel", f"discovery_reel_{date_str}",
        "Phase 2: Discovery Reel Screening & Dossier Verification", _discovery_reel, force=force,
    )

    # 3. 08:45 AM IST: Daily Unlisted MSME Cohort Ingestion
    def _msme_ingest():
        from core.msme.daily_ingest import ingest_daily_msme_cohort
        msme_count = ingest_daily_msme_cohort(date_str, 15)
        return f"INGESTED_{msme_count}"

    _run_leased_phase(
        results, "msme_ingest", f"msme_daily_ingest_{date_str}",
        "Phase 3: Daily MSME 15-Firm Cohort Ingestion", _msme_ingest, force=force,
    )

    # 4. Pre-09:00 AM IST: Morning Research Bouquet Email Dispatch (Immediate post-screening delivery)
    already_dispatched = False
    dispatch_check_failed = False
    if not force:
        try:
            from core.db.digest import has_edition_been_dispatched
            already_dispatched = has_edition_been_dispatched(date_str)
        except Exception as exc:
            # Fail closed: if we cannot confirm the edition was not sent, do not risk a duplicate email.
            logger.exception(f"Phase 4 dispatch-ledger check failed; skipping email dispatch: {exc}")
            results["morning_bouquet"] = f"FAILED: {type(exc).__name__}: {exc}"
            dispatch_check_failed = True

    if already_dispatched:
        logger.info(f"Morning Research Bouquet for {date_str} already dispatched. Skipping Phase 4.")
        results["morning_bouquet"] = "ALREADY_DISPATCHED"
    elif not dispatch_check_failed:
        def _morning_bouquet():
            from core.notify import dispatch_research_bouquet
            bouquet_res = dispatch_research_bouquet(edition_date=date_str, force=force)
            status = bouquet_res.get("status", "COMPLETED")
            logger.info(
                f"Phase 4 result: Morning Bouquet dispatch status={status} "
                f"(delivered={bouquet_res.get('delivered', 0)})."
            )
            return status

        _run_leased_phase(
            results, "morning_bouquet", f"morning_bouquet_{date_str}",
            "Phase 4: Morning Research Bouquet Email Dispatch", _morning_bouquet,
            force=force, ttl_seconds=86400,
        )

    record_autonomous_event(
        event_type="MORNING_PIPELINE_COMPLETE",
        ticker="MULTI_ASSET",
        trigger_source="SCHEDULED_RUNNER",
        action_taken=f"Executed morning pipeline for {date_str}",
        summary=(
            f"Stock Ingest: {_phase_status(results.get('stock_ingestion'))}, "
            f"Discovery: {_phase_status(results.get('discovery_reel'))}, "
            f"MSME: {_phase_status(results.get('msme_ingest'))}, "
            f"Bouquet: {_phase_status(results.get('morning_bouquet'))}"
        ),
        metadata=results,
    )
    return results


def run_nightly_pipeline(date_str: str, force: bool = False) -> dict:
    """Executes the post-market nightly surveillance and synchronization pipeline."""
    logger.info(f"Starting Nightly Multi-Asset Pipeline for {date_str}...")
    results = {}
    prune_zombie_leases()

    # 1. 23:15 IST: AMFI Daily NAV Feed & Scheme Master Ingestion
    def _amfi_sync():
        from core.ingestion.amfi import ingest_amfi_daily_feed
        return ingest_amfi_daily_feed(limit=None, direct_growth_only=True)

    _run_leased_phase(
        results, "amfi_sync", f"amfi_nav_sync_{date_str}",
        "Nightly Phase 1: AMFI Daily NAV & Master Sync", _amfi_sync, force=force,
    )

    # 2. National ETF Matrix Ingestion
    def _etf_sync():
        from core.ingestion.etf_ingest import ingest_all_amfi_etfs
        etf_res = ingest_all_amfi_etfs(force_refresh=True)
        logger.info(f"Nightly Phase 2 result: Synced {etf_res.get('persisted_to_db', 0)} ETFs.")
        return etf_res

    _run_leased_phase(
        results, "etf_sync", f"etf_matrix_sync_{date_str}",
        "Nightly Phase 2: National ETF Matrix Synchronization", _etf_sync, force=force,
    )

    # 3. Sovereign Curve & Benchmarks Refresh
    def _sovereign_sync():
        from core.db.sovereign import refresh_daily_sovereign_benchmarks
        sov_res = refresh_daily_sovereign_benchmarks(date_str)
        logger.info(f"Nightly Phase 3 result: Refreshed {sov_res.get('benchmarks_updated', 0)} benchmarks.")
        return sov_res

    _run_leased_phase(
        results, "sovereign_sync", f"sovereign_sync_{date_str}",
        "Nightly Phase 3: Sovereign Curve & SDL Spreads Refresh", _sovereign_sync, force=force,
    )

    # 4. Multi-Asset Monitoring Scan
    def _asset_scan():
        from core.analysis.asset_scanner import run_comprehensive_asset_scan
        return run_comprehensive_asset_scan("ALL_ASSETS", "nightly_pipeline")

    _run_leased_phase(
        results, "asset_scan", f"asset_scan_{date_str}",
        "Nightly Phase 4: Multi-Asset Surveillance Scan", _asset_scan, force=force,
    )

    # 5. 23:30 IST: Mutual Fund Rotation Look-Through Audit
    def _fund_audit():
        from core.analysis.fund_overlap_auditor import audit_single_fund_daily
        fund_res = audit_single_fund_daily(scheme_code=None, force_refresh_stocks=False)
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
        logger.info(f"Nightly Phase 5 result: Audited fund {fund_res.get('scheme_code') if fund_res else 'none'}.")
        return fund_res

    _run_leased_phase(
        results, "fund_audit", f"fund_audit_{date_str}",
        "Nightly Phase 5: Mutual Fund Rotation Look-Through Audit", _fund_audit, force=force,
    )

    record_autonomous_event(
        event_type="NIGHTLY_PIPELINE_COMPLETE",
        ticker="MULTI_ASSET",
        trigger_source="SCHEDULED_RUNNER",
        action_taken=f"Executed nightly pipeline for {date_str}",
        summary=(
            f"AMFI: {_phase_status(results.get('amfi_sync'))}, "
            f"ETFs: {_phase_status(results.get('etf_sync'))}, "
            f"Sovereign: {_phase_status(results.get('sovereign_sync'))}, "
            f"Scan: {_phase_status(results.get('asset_scan'))}, "
            f"Fund Audit: {_phase_status(results.get('fund_audit'))}"
        ),
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

        failed = [
            f"{mode}.{key}"
            for mode, mode_results in summary.items()
            for key in _failed_phases(mode_results)
        ]
        if failed:
            # Every phase has already run; exit non-zero so the cloud run is visibly red and
            # withhold the Better Stack heartbeat so the missed-heartbeat alert fires.
            logger.error(f"Multi-Asset Scheduled Pipeline finished with failed phases: {failed}")
            return 1

        logger.info("Multi-Asset Scheduled Pipeline execution finished.")
        dispatch_heartbeat(args.mode)
        return 0
    finally:
        flush_betterstack_logs()


if __name__ == "__main__":
    sys.exit(main())
