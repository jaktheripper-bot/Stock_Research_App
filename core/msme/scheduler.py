# core/msme/scheduler.py
"""
Scheduler utilities for the MSME module.
Registers background jobs with an APScheduler instance.
"""

from apscheduler.triggers.cron import CronTrigger
from core.msme.ingest_ministry import run_monthly_job


def register_jobs(scheduler):
    """Register all MSME‑related scheduled jobs.

    Currently schedules the monthly Ministry ingestion on the 1st day of each month
    at 07:30 IST. Adjust the Cron expression if a different schedule is desired.
    """
    # Schedule monthly ingestion – runs on the 1st day at 07:30 IST (Asia/Kolkata)
    trigger = CronTrigger(day="1", hour="7", minute="30", second="0", timezone="Asia/Kolkata")
    scheduler.add_job(run_monthly_job, trigger, id="msme_monthly_ingest", replace_existing=True)
