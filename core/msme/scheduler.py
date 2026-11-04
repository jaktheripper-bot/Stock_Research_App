# core/msme/scheduler.py
"""
Scheduler utilities for monthly background pipelines (MSME Ministry & SEBI Mutual Fund Disclosures).
Registers background jobs with an APScheduler instance (strictly active only when ENABLE_BACKGROUND_SCHEDULERS=1).
"""

import logging
from datetime import datetime

from apscheduler.triggers.cron import CronTrigger
from core.db.connection import IST
from core.msme.ingest_ministry import run_monthly_job

logger = logging.getLogger(__name__)


def job_monthly_mf_portfolio_sync() -> dict:
    """Runs during the SEBI statutory disclosure window (days 4-12 at 07:45 IST) to ingest fresh month-end portfolios."""
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    try:
        from scripts.run_scheduled_pipeline import run_monthly_mf_portfolio_pipeline

        return run_monthly_mf_portfolio_pipeline(today_str, force=False)
    except Exception as exc:
        logger.error("Monthly SEBI MF portfolio sync job failed: %s", exc)
        return {"mf_portfolio_sync": f"FAILED: {type(exc).__name__}: {exc}"}


def register_jobs(scheduler):
    """Register monthly scheduled jobs (MSME Ministry on Day 1 @ 07:30 IST; SEBI MF Portfolios on Days 4-12 @ 07:45 IST)."""
    msme_trigger = CronTrigger(day="1", hour="7", minute="30", second="0", timezone="Asia/Kolkata")
    scheduler.add_job(run_monthly_job, msme_trigger, id="msme_monthly_ingest", replace_existing=True)

    mf_trigger = CronTrigger(day="4-12", hour="7", minute="45", second="0", timezone="Asia/Kolkata")
    scheduler.add_job(job_monthly_mf_portfolio_sync, mf_trigger, id="sebi_mf_monthly_portfolio_sync", replace_existing=True)
