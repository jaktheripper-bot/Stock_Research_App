#!/usr/bin/env python3
"""
Scheduled Multi-Asset Report & Update Pipeline Runner.
Executes autonomously across Cloud (GitHub Actions Cron / Render Failover) and Local macOS Failover
against Supabase PostgreSQL with distributed job leases.

Cadence Architecture (IST):
  --mode evening   (19:30 IST Step A: Post-Close Sovereign, ETFs, Debt Scan, 15-Stock Discovery Reel,
                    15-Firm MSME Cohort, 15-Stock MF Constituents + ~19:45 IST 7-Asset Day-End Market Wrap;
                    on Sat/Sun: Weekend Warehouse Mode runs MSME + Stock Constituents only)
  --mode nightly   (23:15 IST Step B: Silent AMFI NAVAll.txt Sync + 7-Pillar Mutual Fund Rotation Audit;
                    on Sat/Sun: Weekend Warehouse Mode runs Mutual Fund Rotation Audit only)
  --mode morning   (08:00 IST Catch-Up: Silent T-1 lease verification; never locks today's evening leases)
  --mode auto      (Resolves evening / nightly / morning + edition date automatically from IST wall clock)
  --mode all       (Executes evening harvest + nightly AMFI/MF rotation sequentially)
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

# Setup environment path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.db.agent_sessions import record_autonomous_event
from core.db.connection import init_db
from core.db.distributed_lock import job_lease, prune_zombie_leases
from core.logging_config import flush_betterstack_logs, setup_logging

IST = ZoneInfo("Asia/Kolkata")
DAILY_LEASE_TTL_SECONDS = 28800  # 8 hours: coordinates cloud + failover workers without locking same-day post-close runs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("equity_research.scheduled_pipeline")

SKIPPED_SENTINELS = frozenset(
    {
        "SKIPPED_LEASE_HELD",
        "SKIPPED_LOCAL_GUARD",
        "SKIPPED_MARKET_CLOSED",
        "ALREADY_DISPATCHED",
    }
)


def _is_weekend_date(date_str: str) -> bool:
    """Returns True if `date_str` (YYYY-MM-DD) falls on Saturday (5) or Sunday (6)."""
    try:
        dt = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return dt.weekday() >= 5
    except ValueError:
        return False


def _last_trading_date_str(ref_dt: datetime) -> str:
    """Returns `ref_dt`'s date in YYYY-MM-DD, rolled back to Friday if `ref_dt` falls on Sat/Sun."""
    cursor = ref_dt.date()
    while cursor.weekday() >= 5:
        cursor -= timedelta(days=1)
    return cursor.isoformat()


def _resolve_mode_and_date(
    requested_mode: str,
    now_ist: datetime,
    explicit_date: Optional[str] = None,
) -> Tuple[str, str]:
    """Resolves effective pipeline mode and target IST edition date.

    - Morning runs without an explicit `--date` bind strictly to `T-1` (`yesterday_str`) so
      08:00 AM catch-up checks never pre-lock today's 19:30 IST evening leases.
    - Post-midnight runs (`00:00–04:59 IST`) bind nightly mode to `T-1` (`yesterday_str`) so
      late cloud runners do not stamp yesterday's AMFI run under the new calendar day.
    """
    today_str = now_ist.strftime("%Y-%m-%d")
    yesterday_str = (now_ist - timedelta(days=1)).strftime("%Y-%m-%d")

    if requested_mode == "auto":
        if 16 <= now_ist.hour <= 21:
            return "evening", (explicit_date or today_str)
        if now_ist.hour >= 22:
            return "nightly", (explicit_date or today_str)
        if now_ist.hour < 5:
            return "nightly", (explicit_date or yesterday_str)
        return "morning", (explicit_date or yesterday_str)

    if requested_mode == "morning":
        return "morning", (explicit_date or yesterday_str)

    if requested_mode == "nightly":
        default_date = yesterday_str if now_ist.hour < 5 else today_str
        return "nightly", (explicit_date or default_date)

    return requested_mode, (explicit_date or today_str)


def _phase_status(value) -> str:
    """Maps a phase result to OK / SKIPPED / FAILED for event summaries."""
    if isinstance(value, str) and value in SKIPPED_SENTINELS:
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
    """Runs one leased pipeline phase in isolation with a 1-shot retry on transient DB socket resets."""
    from core.db.connection import close_all_pg_pools

    for attempt in range(2):
        try:
            with job_lease(lease_name, ttl_seconds=ttl_seconds, release_on_exit=False) as acquired:
                if not (acquired or force):
                    logger.info(f"Lease for {lease_name} held by another worker. Skipping {phase_label}.")
                    results[result_key] = "SKIPPED_LEASE_HELD"
                    return
                logger.info(f"Executing {phase_label} (attempt {attempt + 1}/2)...")
                results[result_key] = phase_fn()
                logger.info(f"{phase_label} complete.")
                return
        except Exception as exc:
            is_transient_conn_err = any(
                token in f"{type(exc).__name__}: {exc}".lower()
                for token in (
                    "interfaceerror",
                    "operationalerror",
                    "connection already closed",
                    "ssl syscall error",
                    "eof detected",
                )
            )
            if attempt == 0 and is_transient_conn_err:
                logger.warning(
                    f"Transient DB socket drop in {phase_label} ({exc}); resetting pool and retrying once..."
                )
                close_all_pg_pools()
                continue
            logger.exception(f"{phase_label} failed; continuing with remaining phases: {exc}")
            results[result_key] = f"FAILED: {type(exc).__name__}: {exc}"
            return


def _dispatch_bouquet_phase(
    results: dict,
    date_str: str,
    force: bool = False,
    respect_market_calendar: bool = False,
) -> None:
    """Executes the Day-End 7-Asset Market Wrap email dispatch with weekend & local-host guards."""
    if respect_market_calendar and not force and _is_weekend_date(date_str):
        logger.info(f"Markets closed on weekend ({date_str}). Skipping Day-End Market Wrap dispatch.")
        results["morning_bouquet"] = "SKIPPED_MARKET_CLOSED"
        return

    from core.notify import _is_live_email_dispatch_allowed, _is_test_runtime

    if not _is_live_email_dispatch_allowed() and not _is_test_runtime():
        logger.info(
            f"[Local Email Guard] Live email dispatch disabled on this host; skipping morning_bouquet_{date_str} "
            f"lease acquisition so cloud failover remains unblocked."
        )
        results["morning_bouquet"] = "SKIPPED_LOCAL_GUARD"
        return

    already_dispatched = False
    dispatch_check_failed = False
    if not force:
        try:
            from core.db.digest import has_edition_been_dispatched

            already_dispatched = has_edition_been_dispatched(date_str)
        except Exception as exc:
            logger.exception(f"Dispatch-ledger check failed; skipping email dispatch (fail-closed): {exc}")
            results["morning_bouquet"] = f"FAILED: {type(exc).__name__}: {exc}"
            dispatch_check_failed = True

    if already_dispatched:
        logger.info(f"Day-End Research Bouquet for {date_str} already dispatched. Skipping duplicate send.")
        results["morning_bouquet"] = "ALREADY_DISPATCHED"
    elif not dispatch_check_failed:
        def _send_bouquet():
            from core.notify import dispatch_research_bouquet

            bouquet_res = dispatch_research_bouquet(edition_date=date_str, force=force)
            status = bouquet_res.get("status", "COMPLETED")
            logger.info(
                f"Day-End Market Wrap dispatch status={status} (delivered={bouquet_res.get('delivered', 0)})."
            )
            return status

        _run_leased_phase(
            results,
            "morning_bouquet",
            f"morning_bouquet_{date_str}",
            "Day-End 7-Asset Market Wrap Email Dispatch",
            _send_bouquet,
            force=force,
            ttl_seconds=86400,
        )


def run_evening_harvest_pipeline(
    date_str: str,
    force: bool = False,
    respect_market_calendar: bool = True,
) -> dict:
    """Executes Step A (19:30 IST): Post-close 7-asset harvest + ~19:45 IST Day-End Market Wrap.

    On Saturdays & Sundays (`respect_market_calendar=True` and `not force`), market-session syncs
    (`sovereign_sync`, `etf_sync`, `asset_scan`, `discovery_reel`) and the Day-End Newsletter
    are skipped (`SKIPPED_MARKET_CLOSED`), while **Weekend Warehouse Mode** continues building
    `msme_ingest` (15 firms) and `stock_ingestion` (15 MF constituent dossiers).
    """
    is_weekend_skip = bool(respect_market_calendar and not force and _is_weekend_date(date_str))
    mode_banner = "Weekend Warehouse Mode" if is_weekend_skip else "Post-Close Evening Harvest"
    logger.info(f"Starting {mode_banner} Pipeline for {date_str}...")
    results = {}
    prune_zombie_leases()

    # 1. Sovereign Curve & SDL Spreads Refresh (Mon-Fri post-close)
    if is_weekend_skip:
        results["sovereign_sync"] = "SKIPPED_MARKET_CLOSED"
    else:
        def _sovereign_sync():
            from core.db.sovereign import refresh_daily_sovereign_benchmarks

            sov_res = refresh_daily_sovereign_benchmarks(date_str)
            logger.info(f"Evening Phase 1: Refreshed {sov_res.get('benchmarks_updated', 0)} sovereign benchmarks.")
            return sov_res

        _run_leased_phase(
            results,
            "sovereign_sync",
            f"sovereign_sync_{date_str}",
            "Evening Phase 1: Sovereign Curve & SDL Spreads Refresh",
            _sovereign_sync,
            force=force,
        )

    # 2. National ETF Matrix Synchronization (Mon-Fri post-close)
    if is_weekend_skip:
        results["etf_sync"] = "SKIPPED_MARKET_CLOSED"
    else:
        def _etf_sync():
            from core.ingestion.etf_ingest import ingest_all_amfi_etfs

            etf_res = ingest_all_amfi_etfs(force_refresh=True)
            logger.info(f"Evening Phase 2: Synced {etf_res.get('persisted_to_db', 0)} ETFs.")
            return etf_res

        _run_leased_phase(
            results,
            "etf_sync",
            f"etf_matrix_sync_{date_str}",
            "Evening Phase 2: National ETF Matrix Synchronization",
            _etf_sync,
            force=force,
        )

    # 3. Corporate Debt & Multi-Asset Surveillance Scan (Mon-Fri post-close)
    if is_weekend_skip:
        results["asset_scan"] = "SKIPPED_MARKET_CLOSED"
    else:
        def _asset_scan():
            from core.analysis.asset_scanner import run_comprehensive_asset_scan

            return run_comprehensive_asset_scan("ALL_ASSETS", "evening_harvest")

        _run_leased_phase(
            results,
            "asset_scan",
            f"asset_scan_{date_str}",
            "Evening Phase 3: Corporate Debt & Multi-Asset Surveillance Scan",
            _asset_scan,
            force=force,
        )

    # 4. Post-Settlement 15-Stock Discovery Reel Screening (Mon-Fri post-close)
    if is_weekend_skip:
        results["discovery_reel"] = "SKIPPED_MARKET_CLOSED"
    else:
        def _discovery_reel():
            from scripts.run_discovery_worker import run_discovery_pipeline

            success = run_discovery_pipeline(
                target_count=15,
                edition_date=date_str,
                dry_run=False,
                force_synthesis=False,
            )
            if not success:
                raise RuntimeError("Discovery pipeline reported an unsuccessful run.")
            return "SUCCESS"

        _run_leased_phase(
            results,
            "discovery_reel",
            f"discovery_reel_{date_str}",
            "Evening Phase 4: Post-Close Discovery Reel Screening",
            _discovery_reel,
            force=force,
        )

    # 5. Daily Unlisted MSME 15-Firm Cohort Ingestion (7/7 Days — Active in Weekend Warehouse Mode)
    def _msme_ingest():
        from core.msme.daily_ingest import ingest_daily_msme_cohort

        msme_count = ingest_daily_msme_cohort(date_str, 15)
        return f"INGESTED_{msme_count}"

    _run_leased_phase(
        results,
        "msme_ingest",
        f"msme_daily_ingest_{date_str}",
        "Evening Phase 5: Daily MSME 15-Firm Cohort Ingestion",
        _msme_ingest,
        force=force,
    )

    # 6. Daily 15-Stock MF Constituent Ingestion & Re-Audit (7/7 Days — Active in Weekend Warehouse Mode)
    def _stock_ingestion():
        from core.analysis.daily_stock_ingestion import ingest_daily_stock_cohort

        res = ingest_daily_stock_cohort(edition_date=date_str, count=15, skip_gemini=False)
        ingested_n = res.get("ingested_count", len(res.get("ingested_tickers") or res.get("ingested_stocks") or []))
        logger.info(f"Evening Phase 6: {res.get('status')} ({ingested_n} equities).")

        # If any candidate equities were deferred to the pending queue under fail-closed integrity,
        # automatically trigger the batch synthesis worker to compile them immediately.
        if res.get("pending_count", 0) > 0 or ingested_n == 0:
            try:
                from scripts.synthesize_pending_equities import synthesize_pending_cohort
                logger.info("Compiling pending equities queue for edition %s...", date_str)
                synth_count = synthesize_pending_cohort(
                    limit=15,
                    tickers=res.get("pending_tickers") or None,
                )
                logger.info("Compiled %d pending equities for edition %s.", synth_count, date_str)
                if isinstance(res, dict) and synth_count > 0:
                    res["compiled_from_pending"] = synth_count
                    res["ingested_count"] = ingested_n + synth_count
                    if res.get("status") == "pending_synthesis":
                        res["status"] = "success"
            except Exception as synth_err:
                logger.warning("Pending synthesis pass notice: %s", synth_err)

        return res

    _run_leased_phase(
        results,
        "stock_ingestion",
        f"mf_stock_ingest_{date_str}",
        "Evening Phase 6: Daily 15-Stock MF Constituent Ingestion",
        _stock_ingestion,
        force=force,
    )

    # 7. ~19:45 IST Day-End 7-Asset Market Wrap Dispatch (Mon-Fri post-harvest)
    _dispatch_bouquet_phase(
        results,
        date_str=date_str,
        force=force,
        respect_market_calendar=respect_market_calendar,
    )

    record_autonomous_event(
        event_type="EVENING_HARVEST_COMPLETE",
        ticker="MULTI_ASSET",
        trigger_source="SCHEDULED_RUNNER",
        action_taken=f"Executed {mode_banner.lower()} pipeline for {date_str}",
        summary=(
            f"Sovereign: {_phase_status(results.get('sovereign_sync'))}, "
            f"ETFs: {_phase_status(results.get('etf_sync'))}, "
            f"Scan: {_phase_status(results.get('asset_scan'))}, "
            f"Discovery: {_phase_status(results.get('discovery_reel'))}, "
            f"MSME: {_phase_status(results.get('msme_ingest'))}, "
            f"Stock Ingest: {_phase_status(results.get('stock_ingestion'))}, "
            f"Day-End Wrap: {_phase_status(results.get('morning_bouquet'))}"
        ),
        metadata=results,
    )
    return results


def run_morning_pipeline(
    date_str: str,
    force: bool = False,
    respect_market_calendar: bool = False,
) -> dict:
    """Executes the morning catch-up / ingestion verification pipeline for `date_str`."""
    is_weekend_skip = bool(respect_market_calendar and not force and _is_weekend_date(date_str))
    logger.info(f"Starting Morning Multi-Asset Catch-Up Pipeline for {date_str}...")
    results = {}
    prune_zombie_leases()

    # 1. Daily 15-Stock Ingestion & Mutual Fund Look-Through Saturation
    def _stock_ingestion():
        from core.analysis.daily_stock_ingestion import ingest_daily_stock_cohort

        res = ingest_daily_stock_cohort(edition_date=date_str, count=15, skip_gemini=False)
        ingested_n = res.get("ingested_count", len(res.get("ingested_tickers") or res.get("ingested_stocks") or []))
        logger.info(f"Phase 1 result: {res.get('status')} ({ingested_n} equities).")

        # If any candidate equities were deferred to the pending queue under fail-closed integrity,
        # automatically trigger the batch synthesis worker to compile them immediately.
        if res.get("pending_count", 0) > 0 or ingested_n == 0:
            try:
                from scripts.synthesize_pending_equities import synthesize_pending_cohort
                logger.info("Compiling pending equities queue for edition %s...", date_str)
                synth_count = synthesize_pending_cohort(
                    limit=15,
                    tickers=res.get("pending_tickers") or None,
                )
                logger.info("Compiled %d pending equities for edition %s.", synth_count, date_str)
                if isinstance(res, dict) and synth_count > 0:
                    res["compiled_from_pending"] = synth_count
                    res["ingested_count"] = ingested_n + synth_count
                    if res.get("status") == "pending_synthesis":
                        res["status"] = "success"
            except Exception as synth_err:
                logger.warning("Pending synthesis pass notice: %s", synth_err)

        return res

    _run_leased_phase(
        results,
        "stock_ingestion",
        f"mf_stock_ingest_{date_str}",
        "Phase 1: Daily 15-Stock MF Constituent Ingestion",
        _stock_ingestion,
        force=force,
    )

    # 2. Discovery Reel Screening (Mon-Fri editions only when respect_market_calendar=True)
    if is_weekend_skip:
        results["discovery_reel"] = "SKIPPED_MARKET_CLOSED"
    else:
        def _discovery_reel():
            from scripts.run_discovery_worker import run_discovery_pipeline

            success = run_discovery_pipeline(
                target_count=15,
                edition_date=date_str,
                dry_run=False,
                force_synthesis=False,
            )
            if not success:
                raise RuntimeError("Discovery pipeline reported an unsuccessful run.")
            return "SUCCESS"

        _run_leased_phase(
            results,
            "discovery_reel",
            f"discovery_reel_{date_str}",
            "Phase 2: Discovery Reel Screening & Dossier Verification",
            _discovery_reel,
            force=force,
        )

    # 3. Daily Unlisted MSME Cohort Ingestion
    def _msme_ingest():
        from core.msme.daily_ingest import ingest_daily_msme_cohort

        msme_count = ingest_daily_msme_cohort(date_str, 15)
        return f"INGESTED_{msme_count}"

    _run_leased_phase(
        results,
        "msme_ingest",
        f"msme_daily_ingest_{date_str}",
        "Phase 3: Daily MSME 15-Firm Cohort Ingestion",
        _msme_ingest,
        force=force,
    )

    # 4. Research Bouquet Catch-Up Verification
    _dispatch_bouquet_phase(
        results,
        date_str=date_str,
        force=force,
        respect_market_calendar=respect_market_calendar,
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


def run_nightly_pipeline(
    date_str: str,
    force: bool = False,
    respect_market_calendar: bool = False,
) -> dict:
    """Executes Step B (23:15 IST): Silent AMFI NAVAll.txt sync + Mutual Fund Rotation Audit.

    On Saturdays & Sundays (`respect_market_calendar=True` and `not force`), market/NAV syncs
    (`amfi_sync`, `etf_sync`, `sovereign_sync`, `asset_scan`) return `SKIPPED_MARKET_CLOSED`,
    while **Weekend Warehouse Mode** continues executing `fund_audit` (7-pillar rotation audit).
    """
    is_weekend_skip = bool(respect_market_calendar and not force and _is_weekend_date(date_str))
    logger.info(f"Starting Nightly Multi-Asset Pipeline for {date_str}...")
    results = {}
    prune_zombie_leases()

    # 1. 23:15 IST: AMFI Daily NAV Feed & Scheme Master Ingestion (Mon-Fri)
    if is_weekend_skip:
        results["amfi_sync"] = "SKIPPED_MARKET_CLOSED"
    else:
        def _amfi_sync():
            from core.ingestion.amfi import ingest_amfi_daily_feed
            from core.analysis.asset_scanner import scan_mutual_funds, record_scan_start, record_scan_complete
            from core.db.mutual_funds import get_active_mutual_funds

            is_test_mock_mode = (
                os.environ.get("TESTING") == "1"
                and os.environ.get("ALLOW_AMFI_DIFF_SCAN_IN_TEST") != "1"
            )
            pre_snapshot = (
                None
                if is_test_mock_mode
                else {s["scheme_code"]: s for s in get_active_mutual_funds(limit=20000)}
            )
            res = ingest_amfi_daily_feed(limit=None, direct_growth_only=True)
            if is_test_mock_mode:
                return res

            scan_id = record_scan_start("MUTUAL_FUNDS", triggered_by="scheduled_nightly")
            try:
                summary = scan_mutual_funds(
                    limit=None,
                    pre_snapshot=pre_snapshot,
                    skip_upsert=True,
                )
                record_scan_complete(
                    scan_id=scan_id,
                    status="completed",
                    items_scanned=summary.get("scanned", 0),
                    items_added=summary.get("new", 0),
                    items_updated=summary.get("changed", 0),
                    details=summary,
                )
            except Exception as scan_err:
                logger.warning("AMFI nightly differential scan failed (%s): %s", scan_id, scan_err)
                record_scan_complete(scan_id=scan_id, status="failed", error_message=str(scan_err))
            return res

        _run_leased_phase(
            results,
            "amfi_sync",
            f"amfi_nav_sync_{date_str}",
            "Nightly Phase 1: AMFI Daily NAV & Master Sync",
            _amfi_sync,
            force=force,
        )

    # 2. National ETF Matrix Ingestion (Failover if not already leased in Step A)
    if is_weekend_skip:
        results["etf_sync"] = "SKIPPED_MARKET_CLOSED"
    else:
        def _etf_sync():
            from core.ingestion.etf_ingest import ingest_all_amfi_etfs

            etf_res = ingest_all_amfi_etfs(force_refresh=True)
            logger.info(f"Nightly Phase 2 result: Synced {etf_res.get('persisted_to_db', 0)} ETFs.")
            return etf_res

        _run_leased_phase(
            results,
            "etf_sync",
            f"etf_matrix_sync_{date_str}",
            "Nightly Phase 2: National ETF Matrix Synchronization",
            _etf_sync,
            force=force,
        )

    # 3. Sovereign Curve & Benchmarks Refresh (Failover if not already leased in Step A)
    if is_weekend_skip:
        results["sovereign_sync"] = "SKIPPED_MARKET_CLOSED"
    else:
        def _sovereign_sync():
            from core.db.sovereign import refresh_daily_sovereign_benchmarks

            sov_res = refresh_daily_sovereign_benchmarks(date_str)
            logger.info(f"Nightly Phase 3 result: Refreshed {sov_res.get('benchmarks_updated', 0)} benchmarks.")
            return sov_res

        _run_leased_phase(
            results,
            "sovereign_sync",
            f"sovereign_sync_{date_str}",
            "Nightly Phase 3: Sovereign Curve & SDL Spreads Refresh",
            _sovereign_sync,
            force=force,
        )

    # 4. Multi-Asset Monitoring Scan (Failover if not already leased in Step A)
    if is_weekend_skip:
        results["asset_scan"] = "SKIPPED_MARKET_CLOSED"
    else:
        def _asset_scan():
            from core.analysis.asset_scanner import run_comprehensive_asset_scan

            return run_comprehensive_asset_scan("ALL_ASSETS", "nightly_pipeline")

        _run_leased_phase(
            results,
            "asset_scan",
            f"asset_scan_{date_str}",
            "Nightly Phase 4: Multi-Asset Surveillance Scan",
            _asset_scan,
            force=force,
        )

    # 5. 23:30 IST: Mutual Fund Rotation Look-Through Audit (7/7 Days — Active in Weekend Warehouse Mode)
    def _fund_audit():
        from core.analysis.fund_overlap_auditor import audit_single_fund_daily

        fund_res = audit_single_fund_daily(scheme_code=None, force_refresh_stocks=False)
        if isinstance(fund_res, dict) and fund_res.get("scheme_code"):
            record_autonomous_event(
                event_type="DAILY_FUND_AUDIT",
                ticker=fund_res.get("scheme_code", "UNKNOWN"),
                trigger_source="SCHEDULED_RUNNER",
                action_taken="7_PILLAR_LOOKTHROUGH_AUDIT",
                summary=(
                    f"Automated 7-pillar look-through audit completed for "
                    f"{fund_res.get('scheme_name')} ({fund_res.get('scheme_code')})."
                ),
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
        results,
        "fund_audit",
        f"fund_audit_{date_str}",
        "Nightly Phase 5: Mutual Fund Rotation Look-Through Audit",
        _fund_audit,
        force=force,
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


def sync_local_sqlite_mirror_if_present() -> None:
    """When running on a local workstation (not GitHub Actions/Render/tests), mirrors Supabase into local `reports.db`."""
    from core.notify import _is_test_runtime

    if (
        _is_test_runtime()
        or os.environ.get("GITHUB_ACTIONS") == "true"
        or os.environ.get("RENDER")
        or os.environ.get("FORCE_LOCAL_SQLITE") == "1"
    ):
        return

    local_db = os.path.join(ROOT_DIR, "reports.db")
    if not os.path.exists(local_db):
        return

    try:
        from core.db.connection import get_configured_supabase_url
        from scripts.sync_from_supabase import sync_via_postgresql_pull

        pg_url = get_configured_supabase_url()
        if pg_url:
            logger.info("Synchronizing Supabase PostgreSQL state into local SQLite mirror (reports.db)...")
            sync_via_postgresql_pull(sqlite_path=local_db, db_url=pg_url)
    except Exception as sync_err:
        logger.warning(f"Local SQLite mirror pull notice: {sync_err}")


def dispatch_heartbeat(mode: str) -> None:
    """Dispatches an uptime heartbeat to Better Stack if configured."""
    import ssl
    import urllib.request

    import certifi

    from core.config import get_secret

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
        choices=["auto", "evening", "morning", "nightly", "all"],
        default="auto",
        help="Pipeline mode to execute (default: auto from IST clock)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date string in YYYY-MM-DD format (default: resolved per mode in IST)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force execution even if distributed job lease is locked or markets are closed",
    )
    args = parser.parse_args()

    setup_logging()
    init_db()

    now_ist = datetime.now(IST)
    effective_mode, date_str = _resolve_mode_and_date(args.mode, now_ist, args.date)

    logger.info(
        f"Initializing Multi-Asset Scheduled Pipeline "
        f"[Requested: {args.mode.upper()}, Effective: {effective_mode.upper()}, Date: {date_str}, Force: {args.force}]"
    )
    try:
        summary = {}
        if effective_mode == "evening":
            summary["evening"] = run_evening_harvest_pipeline(
                date_str, force=args.force, respect_market_calendar=True
            )
        elif effective_mode == "morning":
            summary["morning"] = run_morning_pipeline(
                date_str, force=args.force, respect_market_calendar=True
            )
        elif effective_mode == "nightly":
            summary["nightly"] = run_nightly_pipeline(
                date_str, force=args.force, respect_market_calendar=True
            )
        elif effective_mode == "all":
            summary["evening"] = run_evening_harvest_pipeline(
                date_str, force=args.force, respect_market_calendar=True
            )
            summary["nightly"] = run_nightly_pipeline(
                date_str, force=args.force, respect_market_calendar=True
            )

        sync_local_sqlite_mirror_if_present()

        failed = [
            f"{mode}.{key}"
            for mode, mode_results in summary.items()
            for key in _failed_phases(mode_results)
        ]
        if failed:
            logger.error(f"Multi-Asset Scheduled Pipeline finished with failed phases: {failed}")
            return 1

        logger.info("Multi-Asset Scheduled Pipeline execution finished.")
        dispatch_heartbeat(effective_mode)
        return 0
    finally:
        flush_betterstack_logs()


if __name__ == "__main__":
    sys.exit(main())
