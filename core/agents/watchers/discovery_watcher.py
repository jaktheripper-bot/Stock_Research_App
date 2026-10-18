"""Proactive 9 AM Discovery Reel Screening Watcher.

Executes autonomous screening daily at 08:45 IST, filtering 500+ scrips across 7-pillar quality criteria,
and publishes the curated morning cohort to the Discovery Reel before market open.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from core.db.agent_sessions import record_autonomous_event
from core.db.distributed_lock import job_lease

logger = logging.getLogger("equity_research.core.agents.watchers.discovery")


async def execute_discovery_screening() -> str:
    """Executes the daily 9 AM Discovery screening and records event into ledger."""
    from scripts.run_discovery_worker import run_discovery_pipeline
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with job_lease(f"discovery_reel_{today_str}", ttl_seconds=7200, release_on_exit=False) as acquired:
        if not acquired:
            logger.info(f"🌅 [Discovery Watcher] Discovery screening lease for {today_str} held by another worker. Skipping duplicate execution.")
            return ""
        logger.info("🌅 [Discovery Watcher] Acquired job lease. Starting daily morning discovery screening...")
        try:
            loop = asyncio.get_running_loop()
            success = await loop.run_in_executor(None, run_discovery_pipeline, 12, today_str, False, False)
            event_id = record_autonomous_event(
                event_type="discovery_screening_complete",
                ticker=None,
                trigger_source="discovery_watcher",
                action_taken="published_edition",
                summary=f"Published Morning Discovery Reel edition: {today_str} (success={success})",
                metadata={"edition": today_str, "success": bool(success)}
            )
            logger.info(f"🌅 [Discovery Watcher] Published morning cohort. Event ID: {event_id}")
            return event_id
        except Exception as e:
            logger.error(f"Error in discovery screening: {e}")
            return ""
