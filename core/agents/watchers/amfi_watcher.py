"""Proactive AMFI NAV Statutory Synchronizer Watcher.

Downloads official statutory NAVAll.txt feeds nightly from the AMFI portal at 23:15 IST,
updates fund database records, and logs execution to the autonomous event ledger.
"""

import asyncio
import logging
from core.db.agent_sessions import record_autonomous_event

logger = logging.getLogger("equity_research.core.agents.watchers.amfi")


async def execute_amfi_sync() -> str:
    """Executes scheduled AMFI NAV synchronization and records event into ledger."""
    from core.ingestion.amfi import ingest_amfi_daily_feed
    logger.info("📊 [AMFI Watcher] Executing statutory NAV synchronization...")
    try:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, ingest_amfi_daily_feed, None, True)
        event_id = record_autonomous_event(
            event_type="amfi_nav_sync_complete",
            ticker=None,
            trigger_source="amfi_watcher",
            action_taken="updated_nav_master",
            summary="Synchronized daily statutory AMFI NAVAll.txt master feed.",
            metadata={"status": "OK"}
        )
        logger.info(f"📊 [AMFI Watcher] Synchronization completed. Event ID: {event_id}")
        return event_id
    except Exception as e:
        logger.error(f"Error in AMFI sync: {e}")
        return ""
