#!/usr/bin/env python3
"""
Scheduled Multi-Asset Report & Update Pipeline Runner.
Executes autonomously across Cloud (GitHub Actions Cron / Render Failover) and Local macOS Failover
against Supabase PostgreSQL with distributed job leases.

Cadence Architecture (IST) — option B: two runs, two timed emails, off-GitHub backups:
  --mode evening           (GitHub 16:30 IST close run: Sovereign, Savings, ETF prices, Debt Scan,
                            Discovery Reel, MSME, MF constituent stock reports, monthly SEBI MF sync;
                            Sat/Sun: Weekend Warehouse Mode runs MSME + Stock Constituents only)
  --mode close-backup      (Render 18:30 IST: same phases; skips finished/in-progress ones)
  --mode send-close-wrap   (Render 19:30 IST: Market Close Wrap email, Mon-Fri)
  --mode nightly           (GitHub 23:15 IST fund run: AMFI NAVs, post-NAV ETF matrix, Sovereign/Scan
                            failover, Mutual Fund Rotation Audit)
  --mode fund-backup       (Render 01:00 IST: same phases for the prior evening's date)
  --mode send-fund-update  (Render 07:30 IST: Fund NAV Update email for the prior trading day, Tue-Sat)
  --mode auto              (Resolves evening / nightly + edition date from the IST wall clock)
  --mode all               (Executes evening + nightly sequentially; manual use)
Runs that start before 12:00 IST bind to the previous date, so delayed runners never take over
the next day's leases or emails.
"""
import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

# Setup environment path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.db.agent_sessions import record_autonomous_event
from core.db.connection import init_db
from core.mailer_monitor import report_mailer_outcome
from core.db.distributed_lock import job_lease, mark_job_done, missing_done_markers, prune_zombie_leases
from core.logging_config import flush_betterstack_logs, setup_logging

IST = ZoneInfo("Asia/Kolkata")
DAILY_LEASE_TTL_SECONDS = 28800  # 8 hours: coordinates cloud + failover workers without locking same-day post-close runs

# Monthly SEBI MF portfolio sync budget (runs at the end of the 16:30 IST close run; the GitHub
# Actions job is capped at 90 minutes). The sync stops at 25 minutes and leaves slow or
# unpublished AMCs for the next evening (nothing written for them).
MF_SYNC_FETCH_WORKERS = 4
MF_SYNC_PER_AMC_TIMEOUT_SECONDS = 600
MF_SYNC_BUDGET_SECONDS = 25 * 60

# Phase 6 (daily MF constituent stock reports): parallel workers and the AI time budget. After
# the budget no new AI generation starts; unstarted equities stay PENDING (unarchived).
STOCK_INGEST_WORKERS = 4
STOCK_INGEST_AI_BUDGET_SECONDS = 40 * 60

# Email editions (option B): the Market Close Wrap is sent at 19:30 IST for the same trading day
# and the Fund NAV Update at 07:30 IST for the prior trading day. Senders wait for the phases
# that feed their sections, then fail closed if those sections are still empty.
EDITION_MARKET_CLOSE = "MARKET_CLOSE"
EDITION_FUND_NAV = "FUND_NAV"
SEND_WAIT_CAP_SECONDS = {EDITION_MARKET_CLOSE: 60 * 60, EDITION_FUND_NAV: 45 * 60}
SEND_POLL_SECONDS = 60


def close_run_required_leases(date_str: str) -> list:
    """Close-run phases that feed the Market Close Wrap sections (weekday editions)."""
    return [
        f"sovereign_sync_{date_str}",
        f"savings_rate_sync_{date_str}",
        f"asset_scan_{date_str}",
        f"discovery_reel_{date_str}",
        f"msme_daily_ingest_{date_str}",
    ]


def fund_run_required_leases(date_str: str) -> list:
    """Fund-run phases that feed the Fund NAV Update sections (MF look-through + ETF matrix)."""
    return [
        f"amfi_nav_sync_{date_str}",
        f"etf_nav_sync_{date_str}",
        f"fund_audit_{date_str}",
    ]


def _install_termination_handler() -> None:
    """Turns SIGTERM (CI cancellation / timeout, Render shutdown) into SystemExit so held phase
    leases are released by `job_lease` and a backup runner can retry those phases."""

    def _on_sigterm(signum, _frame):
        logger.error("Received signal %s; aborting pipeline so held leases are released.", signum)
        raise SystemExit(128 + int(signum))

    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
    except (ValueError, OSError) as sig_err:
        logger.warning("Could not install SIGTERM handler: %s", sig_err)


class SynthesisUnavailableError(RuntimeError):
    """Raised when a phase needed live AI synthesis for at least one item and compiled none."""


def _raise_if_synthesis_unavailable(res: dict, ingested_n: int, synth_count: int, phase_label: str) -> None:
    """Turns a total AI outage into a visible phase failure instead of a silent green run.

    Fires only when at least one equity needed synthesis (`pending_count > 0`) and nothing was
    archived, neither directly (`ingested_n`) nor from the pending retry pass (`synth_count`).
    Partial outages stay green; pending items remain queued (unarchived) for the next run.
    """
    pending_n = int((res or {}).get("pending_count") or 0) if isinstance(res, dict) else 0
    if pending_n > 0 and ingested_n == 0 and synth_count == 0:
        raise SynthesisUnavailableError(
            f"{phase_label}: AI synthesis unavailable — 0 of {pending_n} pending equities compiled; "
            f"all remain PENDING (unarchived) for retry."
        )

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
        "SKIPPED_OUTSIDE_SEBI_WINDOW",
        "ALREADY_DISPATCHED",
        "ALREADY_SYNCED",
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


DATED_MODES = (
    "evening", "close-backup", "send-close-wrap",
    "nightly", "fund-backup", "send-fund-update",
    "all",
)


def _resolve_mode_and_date(
    requested_mode: str,
    now_ist: datetime,
    explicit_date: Optional[str] = None,
) -> Tuple[str, str]:
    """Resolves effective pipeline mode and target IST edition date.

    Runs that start before 12:00 IST bind to `T-1` (`yesterday_str`): delayed close/fund runs,
    the 01:00 IST `fund-backup` and the 07:30 IST `send-fund-update` all belong to the previous
    date, and never take over today's 16:30 IST close-run leases or emails.
    """
    today_str = now_ist.strftime("%Y-%m-%d")
    yesterday_str = (now_ist - timedelta(days=1)).strftime("%Y-%m-%d")

    if requested_mode == "auto":
        if 12 <= now_ist.hour <= 21:
            return "evening", (explicit_date or today_str)
        if now_ist.hour >= 22:
            return "nightly", (explicit_date or today_str)
        return "nightly", (explicit_date or yesterday_str)

    if requested_mode in DATED_MODES:
        # Delayed GitHub Actions cron runs arriving post-midnight (00:00–11:59 IST)
        # belong to prior trading day T-1; never hijack today's post-close leases or mailer.
        default_date = yesterday_str if now_ist.hour < 12 else today_str
        return requested_mode, (explicit_date or default_date)

    return requested_mode, (explicit_date or today_str)


def _phase_status(value) -> str:
    """Maps a phase result to OK / SKIPPED / FAILED / PARTIAL for event summaries."""
    if isinstance(value, str) and value in SKIPPED_SENTINELS:
        return "SKIPPED"
    if isinstance(value, str) and value.startswith("FAILED"):
        return "FAILED"
    if isinstance(value, dict) and value.get("status") == "PARTIAL":
        return "PARTIAL"
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
                mark_job_done(lease_name)
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
    edition_kind: str = EDITION_MARKET_CLOSE,
) -> None:
    """Sends one email edition (`MARKET_CLOSE` or `FUND_NAV`) once per date, with weekend & local-host guards."""
    force_email_redispatch = bool(force and os.environ.get("FORCE_EMAIL_REDISPATCH") == "1")
    if respect_market_calendar and not force_email_redispatch and _is_weekend_date(date_str):
        logger.info(f"Markets closed on weekend ({date_str}). Skipping {edition_kind} email dispatch.")
        results["digest_dispatch"] = "SKIPPED_MARKET_CLOSED"
        return

    from core.notify import _is_live_email_dispatch_allowed, _is_test_runtime

    lease_name = f"digest_{edition_kind.lower()}_{date_str}"
    if not _is_live_email_dispatch_allowed() and not _is_test_runtime():
        logger.info(
            f"[Local Email Guard] Live email dispatch disabled on this host; skipping {lease_name} "
            f"lease acquisition so cloud failover remains unblocked."
        )
        results["digest_dispatch"] = "SKIPPED_LOCAL_GUARD"
        return

    already_dispatched = False
    dispatch_check_failed = False
    if not force_email_redispatch:
        try:
            from core.db.digest import has_edition_been_dispatched

            already_dispatched = has_edition_been_dispatched(date_str, edition_kind=edition_kind)
        except Exception as exc:
            logger.exception(f"Dispatch-ledger check failed; skipping email dispatch (fail-closed): {exc}")
            results["digest_dispatch"] = f"FAILED: {type(exc).__name__}: {exc}"
            dispatch_check_failed = True

    if already_dispatched:
        logger.info(f"{edition_kind} email for {date_str} already dispatched. Skipping duplicate send.")
        results["digest_dispatch"] = "ALREADY_DISPATCHED"
    elif not dispatch_check_failed:
        def _send_bouquet():
            from core.notify import dispatch_research_bouquet

            bouquet_res = dispatch_research_bouquet(
                edition_date=date_str,
                edition_kind=edition_kind,
                force=force_email_redispatch,
            )
            status = bouquet_res.get("status", "COMPLETED")
            logger.info(
                f"{edition_kind} email dispatch status={status} (delivered={bouquet_res.get('delivered', 0)})."
            )
            return status

        _run_leased_phase(
            results,
            "digest_dispatch",
            lease_name,
            f"{edition_kind} Email Dispatch",
            _send_bouquet,
            force=force,
            ttl_seconds=86400,
        )


def _wait_for_required_phases(required: list, cap_seconds: int, poll_seconds: int = SEND_POLL_SECONDS) -> list:
    """Polls completion markers until every required phase is done or `cap_seconds` passes.

    Returns the phases still missing (empty list when all are done)."""
    deadline = time.monotonic() + max(0, int(cap_seconds))
    missing = missing_done_markers(required)
    while missing and time.monotonic() < deadline:
        logger.info("Waiting for %d phase(s) before sending: %s", len(missing), ", ".join(missing))
        time.sleep(max(1, min(poll_seconds, max(1.0, deadline - time.monotonic()))))
        missing = missing_done_markers(required)
    return missing


def run_send_edition(
    edition_kind: str,
    date_str: str,
    force: bool = False,
    wait_cap_seconds: Optional[int] = None,
) -> dict:
    """Render sender job: waits for the phases that feed `edition_kind`, then sends that email once.

    MARKET_CLOSE goes out for weekday `date_str` only; FUND_NAV covers the prior trading day's NAVs
    (weekday `date_str`). If required phases are still unfinished at the wait cap, the email is still
    attempted and the builder fails closed when any of its sections is empty."""
    results: dict = {"edition_kind": edition_kind}
    if _is_weekend_date(date_str) and not force:
        logger.info(f"{edition_kind} edition for weekend date {date_str} is not sent.")
        results["digest_dispatch"] = "SKIPPED_MARKET_CLOSED"
        return results

    required = (
        close_run_required_leases(date_str)
        if edition_kind == EDITION_MARKET_CLOSE
        else fund_run_required_leases(date_str)
    )
    cap = SEND_WAIT_CAP_SECONDS.get(edition_kind, 0) if wait_cap_seconds is None else wait_cap_seconds
    missing = _wait_for_required_phases(required, cap)
    results["phases_missing_at_send"] = missing
    if missing:
        logger.warning(
            "%s for %s: %d phase(s) still unfinished after %ss wait (%s); attempting send, builder fails closed on empty sections.",
            edition_kind, date_str, len(missing), cap, ", ".join(missing),
        )
    _dispatch_bouquet_phase(
        results,
        date_str=date_str,
        force=force,
        respect_market_calendar=True,
        edition_kind=edition_kind,
    )
    return results


def run_evening_harvest_pipeline(
    date_str: str,
    force: bool = False,
    respect_market_calendar: bool = True,
) -> dict:
    """Executes the close run (GitHub 16:30 IST; Render `close-backup` 18:30 IST re-runs unfinished phases).

    Sends no email: the Market Close Wrap is sent by the Render `send-close-wrap` job at 19:30 IST.
    On Saturdays & Sundays (`respect_market_calendar=True` and `not force`), market-session syncs
    (`sovereign_sync`, `etf_sync`, `asset_scan`, `discovery_reel`) are skipped
    (`SKIPPED_MARKET_CLOSED`), while **Weekend Warehouse Mode** continues building `msme_ingest`
    (15 firms) and `stock_ingestion` (MF constituent dossiers). The monthly SEBI MF portfolio
    sync runs last, from day 4 of the month, until that month's portfolios are fresh.
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

        def _savings_rate_sync():
            from core.db.savings import verify_and_sync_automated_savings_rates

            allow_net = os.environ.get("TESTING") != "1"
            sav_res = verify_and_sync_automated_savings_rates(
                edition_date=date_str,
                allow_network=allow_net,
            )
            logger.info(
                "Evening Phase 1B: Verified %s fixed-savings instruments (%s live changes, %s review-due).",
                sav_res.get("total_active", 0),
                sav_res.get("live_rate_changes", 0),
                sav_res.get("review_due_count", 0),
            )
            return sav_res

        _run_leased_phase(
            results,
            "savings_rate_sync",
            f"savings_rate_sync_{date_str}",
            "Evening Phase 1B: Statutory & Bank Savings Rate Verification",
            _savings_rate_sync,
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

    # 6. Daily Catch-Up (25/15-Stock) MF Constituent Ingestion & Re-Audit (7/7 Days — Active in Weekend Warehouse Mode)
    def _stock_ingestion():
        from core.analysis.daily_stock_ingestion import ingest_daily_stock_cohort

        ai_deadline = time.monotonic() + STOCK_INGEST_AI_BUDGET_SECONDS
        res = ingest_daily_stock_cohort(
            edition_date=date_str,
            count=None,
            skip_gemini=False,
            workers=STOCK_INGEST_WORKERS,
            deadline_monotonic=ai_deadline,
        )
        ingested_n = res.get("ingested_count", len(res.get("ingested_tickers") or res.get("ingested_stocks") or []))
        logger.info(f"Evening Phase 6: {res.get('status')} ({ingested_n} equities).")

        # If any candidate equities were deferred to the pending queue under fail-closed integrity,
        # automatically trigger the batch synthesis worker to compile them immediately.
        synth_count = 0
        if res.get("pending_count", 0) > 0 or ingested_n == 0:
            try:
                from scripts.synthesize_pending_equities import synthesize_pending_cohort
                pending_list = res.get("pending_tickers") or []
                logger.info("Compiling pending equities queue for edition %s...", date_str)
                synth_count = synthesize_pending_cohort(
                    limit=max(15, len(pending_list)),
                    tickers=pending_list or None,
                    deadline_monotonic=ai_deadline,
                )
                logger.info("Compiled %d pending equities for edition %s.", synth_count, date_str)
                if isinstance(res, dict) and synth_count > 0:
                    res["compiled_from_pending"] = synth_count
                    res["ingested_count"] = ingested_n + synth_count
                    if res.get("status") == "pending_synthesis":
                        res["status"] = "success"
            except Exception as synth_err:
                logger.warning("Pending synthesis pass notice: %s", synth_err)

        _raise_if_synthesis_unavailable(res, ingested_n, synth_count, "Evening Phase 6")
        return res

    _run_leased_phase(
        results,
        "stock_ingestion",
        f"mf_stock_ingest_{date_str}",
        "Evening Phase 6: Daily MF Constituent Ingestion",
        _stock_ingestion,
        force=force,
    )

    # 7. Monthly SEBI MF portfolio sync (moved here from the retired 08:00 IST morning run; budgeted)
    try:
        day_of_month = int(str(date_str)[8:10])
    except ValueError:
        day_of_month = 0
    if day_of_month >= 4 and os.environ.get("TESTING") != "1":
        mf_res = run_monthly_mf_portfolio_pipeline(date_str, force=force)
        results["mf_portfolio_sync"] = mf_res.get("mf_portfolio_sync")
        if "mf_portfolio_coverage" in mf_res:
            results["mf_portfolio_coverage"] = mf_res["mf_portfolio_coverage"]

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
            f"SEBI MF Sync: {_phase_status(results.get('mf_portfolio_sync'))}"
        ),
        metadata=results,
    )
    return results


def _monthly_mf_coverage(ref_date_str: str, universe: list[dict]) -> dict:
    from core.db.connection import get_db_connection
    from core.ingestion.mf_portfolio_ingest import amc_key_for_fund_house, load_sources, recent_month_ends

    ref_date = datetime.strptime(str(ref_date_str)[:10], "%Y-%m-%d").date()
    target_date = recent_month_ends(1, today=ref_date)[0].isoformat()
    sources = load_sources()
    expected = set()
    excluded = {}
    for scheme in universe:
        code = str(scheme["scheme_code"]).strip()
        amc = amc_key_for_fund_house(scheme["fund_house"], sources)
        if not code.isdigit():
            excluded[code] = "not a canonical AMFI code"
        elif not amc:
            excluded[code] = "no enabled scheduled disclosure source"
        else:
            expected.add(code)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT d.scheme_code, s.as_on_date
            FROM mf_current_disclosures d
            JOIN mf_disclosure_snapshots s ON s.snapshot_id = d.snapshot_id
        """)
        dates = dict(cur.fetchall())
    finally:
        cur.close()
        conn.close()

    missing = sorted(code for code in expected if str(dates.get(code) or "")[:10] != target_date)
    return {
        "target_date": target_date,
        "expected_scheme_codes": sorted(expected),
        "excluded": excluded,
        "missing_scheme_codes": missing,
        "fresh_count": len(expected) - len(missing),
        "complete": bool(expected) and not missing,
    }


def _are_monthly_mf_portfolios_fresh_for_prior_month(ref_date_str: str) -> bool:
    from core.ingestion.mf_portfolio_ingest import get_monthly_mf_universe

    return _monthly_mf_coverage(ref_date_str, get_monthly_mf_universe())["complete"]


def run_monthly_mf_portfolio_pipeline(
    date_str: str,
    force: bool = False,
) -> dict:
    """Executes SEBI monthly mutual fund portfolio synchronization across verified public AMC disclosures."""
    results = {}
    prune_zombie_leases()

    try:
        day_of_month = int(str(date_str)[8:10])
    except ValueError:
        day_of_month = 0

    if not force and day_of_month < 4:
        results["mf_portfolio_sync"] = "SKIPPED_OUTSIDE_SEBI_WINDOW"
        return results

    def _mf_sync():
        from core.ingestion.mf_portfolio_ingest import get_monthly_mf_universe, ingest_top_funds

        universe = get_monthly_mf_universe()
        coverage = _monthly_mf_coverage(date_str, universe)
        if not force and coverage["complete"]:
            results["mf_portfolio_coverage"] = coverage
            return "ALREADY_SYNCED"
        missing = coverage["missing_scheme_codes"]
        if not coverage["expected_scheme_codes"]:
            raise RuntimeError("No canonical schemes in the scheduled portfolio scope")
        codes = coverage["expected_scheme_codes"] if force else missing
        # Bounded parallel AMC fetch + overall budget so the sync finishes (as PARTIAL if needed)
        # well inside the 45-minute GitHub Actions job limit instead of being killed mid-run.
        outcome = ingest_top_funds(
            target=len(codes),
            dry_run=False,
            audit=False,
            universe=universe,
            only_scheme_codes=set(codes),
            target_month_end=coverage["target_date"],
            fetch_workers=MF_SYNC_FETCH_WORKERS,
            per_amc_timeout_s=MF_SYNC_PER_AMC_TIMEOUT_SECONDS,
            deadline_monotonic=time.monotonic() + MF_SYNC_BUDGET_SECONDS,
        )
        if outcome.get("timed_out_amcs"):
            logger.warning(
                "MF portfolio sync left %d AMC(s) for the next run: %s",
                len(outcome["timed_out_amcs"]), ", ".join(outcome["timed_out_amcs"]),
            )
        coverage = _monthly_mf_coverage(date_str, universe)
        results["mf_portfolio_coverage"] = coverage
        return {**outcome, "status": "SYNCED" if coverage["complete"] else "PARTIAL"}

    _run_leased_phase(
        results,
        "mf_portfolio_sync",
        f"mf_portfolio_sync_{date_str}",
        "SEBI Monthly Mutual Fund Portfolio Sync",
        _mf_sync,
        force=force,
    )
    record_autonomous_event(
        event_type="MONTHLY_MF_PORTFOLIO_SYNC",
        ticker="MUTUAL_FUNDS",
        trigger_source="SCHEDULED_RUNNER",
        action_taken=f"Executed monthly SEBI MF portfolio sync for {date_str}",
        summary=f"MF Portfolio Sync: {_phase_status(results.get('mf_portfolio_sync'))}",
        metadata=results,
    )
    return results


def run_nightly_pipeline(
    date_str: str,
    force: bool = False,
    respect_market_calendar: bool = False,
) -> dict:
    """Executes the fund run (GitHub 23:15 IST; Render `fund-backup` 01:00 IST re-runs unfinished phases).

    AMFI NAVAll.txt sync + post-NAV ETF matrix + Mutual Fund Rotation Audit. Sends no email: the Fund
    NAV Update is sent by the Render `send-fund-update` job at 07:30 IST for this date.

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

    # 2. National ETF Matrix re-sync after the night's AMFI NAVs (own lease: the 16:30 close-run ETF
    #    price sync must not suppress this post-NAV refresh that feeds the 07:30 Fund NAV Update)
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
            f"etf_nav_sync_{date_str}",
            "Nightly Phase 2: National ETF NAV Matrix Synchronization",
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
        choices=[
            "auto", "evening", "close-backup", "send-close-wrap",
            "nightly", "fund-backup", "send-fund-update", "mf-portfolios", "all",
        ],
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
    _install_termination_handler()
    init_db()

    now_ist = datetime.now(IST)
    effective_mode, date_str = _resolve_mode_and_date(args.mode, now_ist, args.date)

    logger.info(
        f"Initializing Multi-Asset Scheduled Pipeline "
        f"[Requested: {args.mode.upper()}, Effective: {effective_mode.upper()}, Date: {date_str}, Force: {args.force}]"
    )
    try:
        summary = {}
        if effective_mode in ("evening", "close-backup"):
            summary[effective_mode] = run_evening_harvest_pipeline(
                date_str, force=args.force, respect_market_calendar=True
            )
        elif effective_mode in ("nightly", "fund-backup"):
            summary[effective_mode] = run_nightly_pipeline(
                date_str, force=args.force, respect_market_calendar=True
            )
        elif effective_mode == "send-close-wrap":
            summary[effective_mode] = run_send_edition(EDITION_MARKET_CLOSE, date_str, force=args.force)
            report_mailer_outcome(EDITION_MARKET_CLOSE, date_str, summary[effective_mode])
        elif effective_mode == "send-fund-update":
            summary[effective_mode] = run_send_edition(EDITION_FUND_NAV, date_str, force=args.force)
            report_mailer_outcome(EDITION_FUND_NAV, date_str, summary[effective_mode])
        elif effective_mode == "mf-portfolios":
            summary["mf_portfolios"] = run_monthly_mf_portfolio_pipeline(
                date_str, force=args.force or True
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
