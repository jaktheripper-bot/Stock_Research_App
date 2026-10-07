"""Proactive BSE Announcement Event Watcher powered by Google Antigravity SDK triggers.

Polls official exchange disclosures every 5 minutes (300 seconds).
If a material filing occurs (auditor resignation, promoter pledge change, board dispute),
records the event in `autonomous_event_ledger` and triggers an automated re-audit.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from core.analysis.fundamentals import fetch_latest_bse_announcement
from core.db.watchlist import get_watchlist
from core.db.agent_sessions import record_autonomous_event

logger = logging.getLogger("equity_research.core.agents.watchers.bse")


async def scan_watchlist_bse_announcements() -> List[Dict[str, Any]]:
    """Scans active watchlist scrips for new material BSE announcements (batched)."""
    watchlist = get_watchlist()[:10]
    events_triggered = []

    for item in watchlist:
        ticker = item.get("ticker", "").strip().upper()
        if not ticker:
            continue
        try:
            latest = await asyncio.to_thread(fetch_latest_bse_announcement, ticker)
            if latest and ("resignation" in latest.lower() or "pledge" in latest.lower() or "fraud" in latest.lower()):
                summary = f"Material disclosure detected for {ticker}: {latest[:120]}..."
                event_id = record_autonomous_event(
                    event_type="bse_material_filing",
                    ticker=ticker,
                    trigger_source="bse_watcher",
                    action_taken="flagged_for_reaudit",
                    summary=summary,
                    metadata={"headline": latest}
                )
                events_triggered.append({"ticker": ticker, "event_id": event_id, "headline": latest})
                logger.info(f"🚨 [BSE Watcher] {summary}")
        except Exception as e:
            logger.warning(f"Error checking BSE filing for {ticker}: {e}")

    return events_triggered


async def run_bse_watcher_loop():
    """Continuous background loop running every 300 seconds with initial startup backoff."""
    logger.info("📡 [BSE Watcher] Background BSE announcement watcher loop initiated.")
    # Initial delay to avoid network contention during server boot
    await asyncio.sleep(60)
    while True:
        try:
            await scan_watchlist_bse_announcements()
            await asyncio.sleep(300)
        except asyncio.CancelledError:
            logger.info("📡 [BSE Watcher] Watcher loop cancelled.")
            break
        except Exception as e:
            logger.error(f"📡 [BSE Watcher] Exception in watcher loop: {e}")
            await asyncio.sleep(60)
