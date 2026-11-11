# core/msme/scheduler.py
"""
Scheduler utilities for the monthly MSME Ministry background pipeline.
Registers background jobs with an APScheduler instance (strictly active only when ENABLE_BACKGROUND_SCHEDULERS=1).
"""

import logging

from apscheduler.triggers.cron import CronTrigger
from core.msme.ingest_ministry import run_monthly_job

logger = logging.getLogger(__name__)


def register_jobs(scheduler):
    """Register monthly scheduled jobs (MSME Ministry on Day 1 @ 07:30 IST).

    The SEBI MF portfolio sync is owned by the 16:30 IST close run (scripts/run_scheduled_pipeline.py)."""
    msme_trigger = CronTrigger(day="1", hour="7", minute="30", second="0", timezone="Asia/Kolkata")
    scheduler.add_job(run_monthly_job, msme_trigger, id="msme_monthly_ingest", replace_existing=True)

