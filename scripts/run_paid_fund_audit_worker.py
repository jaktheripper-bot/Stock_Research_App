"""Dedicated worker for durable paid Mutual Fund audits."""

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import sys
from threading import Event, Thread
from time import monotonic, sleep
from typing import Any, Dict, Optional

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.analysis.dossier_report_synthesis import generate_stock_report
from core.analysis.fund_overlap_auditor import audit_single_fund_daily
from core.analysis.fund_research_evidence import qualify_fund_research
from core.db.connection import init_db
from core.db.fund_audit_jobs import (
    FundAuditConflict,
    WORKER_HEARTBEAT_MAX_AGE,
    claim_fund_audit,
    complete_fund_audit,
    fail_fund_audit,
    reconcile_expired_fund_audits,
    record_fund_constituent_delivery,
    record_worker_heartbeat,
    renew_fund_audit,
)
from core.db.mutual_funds import get_fund_disclosure_snapshot
from core.db.reports import get_report_by_ticker
from core.logging_config import setup_logging

logger = logging.getLogger(__name__)

# How often an idle worker logs that it is alive and polling (seconds).
IDLE_LOG_SECONDS = 300
POLL_SECONDS = 2


def _default_worker_id() -> str:
    explicit = os.environ.get("RENDER_INSTANCE_ID") or os.environ.get("FUND_AUDIT_WORKER_ID")
    if explicit:
        return explicit.strip()[:80]
    return f"{socket.gethostname()}:{os.getpid()}"[:80]


def _read_report(ticker: str) -> Optional[Dict[str, Any]]:
    get_report_by_ticker.cache_clear()
    return get_report_by_ticker(ticker)


def run_claim(job: Dict[str, Any]) -> None:
    try:
        snapshot = get_fund_disclosure_snapshot(job["snapshot_id"])
        if not snapshot or snapshot.get("scheme_code") != job["scheme_code"]:
            raise FundAuditConflict("The quoted portfolio could not be loaded.")

        for ticker in job["tickers"]:
            if not renew_fund_audit(job):
                return
            if qualify_fund_research(_read_report(ticker), ticker):
                # Research that arrived after the quote did not require paid synthesis.
                # Its reserved credit is returned during settlement.
                continue
            try:
                generate_stock_report(ticker, use_grounding=True)
                report = _read_report(ticker)
                if not qualify_fund_research(report, ticker):
                    continue
                revision = hashlib.sha256(str(report["report_text"]).encode()).hexdigest()
            except Exception as exc:
                logger.warning("Constituent synthesis failed for %s: %s", ticker, exc)
                continue
            if not record_fund_constituent_delivery(job, ticker, revision):
                return

        if not renew_fund_audit(job):
            return
        result = audit_single_fund_daily(
            job["scheme_code"],
            holdings_override=snapshot["holdings"],
            scheme_override=json.loads(job["scheme_json"]),
            persist=False,
        )
        complete_fund_audit(job, result["dossier_record"])
    except FundAuditConflict as exc:
        logger.warning("Paid fund audit conflict on %s: %s", job["job_id"], exc)
        fail_fund_audit(job, str(exc))
    except Exception:
        logger.exception("Paid fund audit failed for %s", job["job_id"])
        fail_fund_audit(job, "The audit failed. Undelivered credits were refunded.")


def run_claim_with_heartbeat(job: Dict[str, Any], *, worker_id: Optional[str] = None) -> None:
    stop = Event()
    interval = WORKER_HEARTBEAT_MAX_AGE / 3

    def heartbeat() -> None:
        while not stop.wait(interval):
            try:
                # A timed-out claim cannot keep advertising availability.
                if worker_id:
                    record_worker_heartbeat(job, worker_id=worker_id)
                else:
                    record_worker_heartbeat(job)
            except Exception:
                logger.exception("Could not refresh paid fund audit worker heartbeat")

    thread = Thread(target=heartbeat, name="paid-fund-audit-heartbeat", daemon=True)
    thread.start()
    try:
        run_claim(job)
    finally:
        stop.set()
        thread.join(timeout=interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process or reconcile durable paid fund audits.")
    parser.add_argument("--reconcile-only", action="store_true", help="Settle one batch of expired jobs and exit.")
    parser.add_argument("--once", action="store_true", help="Run one claim/reconcile cycle and exit.")
    args = parser.parse_args()

    setup_logging()
    init_db()
    worker_id = _default_worker_id()
    if args.reconcile_only:
        reconcile_expired_fund_audits()
        logger.info("Paid fund audit reconcile-only run finished.")
        return
    logger.info("Paid fund audit worker started (worker=%s, polling every %ss).", worker_id, POLL_SECONDS)
    jobs_done = 0
    failed_cycles = 0
    last_status_at = monotonic()
    while True:
        try:
            job = claim_fund_audit(worker_id=worker_id)
            if job:
                logger.info("Claimed paid fund audit %s.", job.get("job_id"))
                run_claim_with_heartbeat(job, worker_id=worker_id)
                jobs_done += 1
                logger.info("Finished paid fund audit %s.", job.get("job_id"))
            else:
                sleep(POLL_SECONDS)
        except Exception:
            failed_cycles += 1
            logger.exception("Paid fund audit worker cycle failed")
            sleep(5)
        if monotonic() - last_status_at >= IDLE_LOG_SECONDS:
            logger.info(
                "Paid fund audit worker alive: %d job(s) done and %d failed cycle(s) since start.",
                jobs_done, failed_cycles,
            )
            last_status_at = monotonic()
        if args.once:
            return


if __name__ == "__main__":
    main()
