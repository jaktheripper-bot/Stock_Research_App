"""Proactive 9 AM Discovery Reel Screening Watcher.

Executes autonomous screening daily at 08:45 IST, filtering 500+ scrips across 7-pillar quality criteria,
and publishes the curated morning cohort to the Discovery Reel before market open.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from core.db.connection import IST
from core.db.agent_sessions import record_autonomous_event
from core.db.distributed_lock import job_lease

logger = logging.getLogger("equity_research.core.agents.watchers.discovery")


async def _run_screening_for_edition(target_date: str, target_count: int = 15) -> str:
    from scripts.run_discovery_worker import run_discovery_pipeline

    try:
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(
            None, run_discovery_pipeline, target_count, target_date, False, False
        )
        event_id = record_autonomous_event(
            event_type="discovery_screening_complete",
            ticker=None,
            trigger_source="discovery_watcher",
            action_taken="published_edition",
            summary=f"Published Morning Discovery Reel edition: {target_date} (success={success})",
            metadata={"edition": target_date, "target_count": target_count, "success": bool(success)},
        )
        logger.info(f"🌅 [Discovery Watcher] Published morning cohort for {target_date}. Event ID: {event_id}")
        return event_id
    except Exception as e:
        logger.error(f"Error in discovery screening for {target_date}: {e}")
        return ""


async def execute_discovery_screening(
    edition_date: Optional[str] = None,
    acquire_lease: bool = True,
    target_count: int = 15,
) -> str:
    """Executes the daily Discovery screening in IST and records event into ledger."""
    target_date = edition_date or datetime.now(IST).strftime("%Y-%m-%d")
    if not acquire_lease:
        return await _run_screening_for_edition(target_date, target_count=target_count)

    with job_lease(f"discovery_reel_{target_date}", ttl_seconds=72000, release_on_exit=False) as acquired:
        if not acquired:
            logger.info(
                f"🌅 [Discovery Watcher] Discovery screening lease for {target_date} held by another worker. Skipping duplicate execution."
            )
            return ""
        logger.info(f"🌅 [Discovery Watcher] Acquired job lease for {target_date}. Starting daily morning discovery screening...")
        return await _run_screening_for_edition(target_date, target_count=target_count)
