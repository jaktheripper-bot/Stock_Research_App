"""Proactive 9 AM Discovery Reel Screening Watcher.

Executes autonomous screening daily at 08:45 IST, filtering 500+ scrips across 7-pillar quality criteria,
and publishes the curated morning cohort to the Discovery Reel before market open.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from core.db.agent_sessions import record_autonomous_event

logger = logging.getLogger("equity_research.core.agents.watchers.discovery")


async def execute_discovery_screening() -> str:
    """Executes the daily 9 AM Discovery screening and records event into ledger."""
    from scripts.run_discovery_worker import run_discovery_pipeline
    logger.info("🌅 [Discovery Watcher] Starting daily morning discovery screening...")
    try:
        edition = await run_discovery_pipeline()
        event_id = record_autonomous_event(
            event_type="discovery_screening_complete",
            ticker=None,
            trigger_source="discovery_watcher",
            action_taken="published_edition",
            summary=f"Published Morning Discovery Reel edition: {edition}",
            metadata={"edition": edition}
        )
        logger.info(f"🌅 [Discovery Watcher] Published morning cohort. Event ID: {event_id}")
        return event_id
    except Exception as e:
        logger.error(f"Error in discovery screening: {e}")
        return ""
