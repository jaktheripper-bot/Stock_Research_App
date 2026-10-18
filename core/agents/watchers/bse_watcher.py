"""Proactive BSE Announcement Event Watcher powered by Google Antigravity SDK triggers.

Polls official exchange disclosures every 5 minutes (300 seconds).
If a material filing occurs (auditor resignation, promoter pledge change, board dispute),
records the event in `autonomous_event_ledger` and triggers an automated re-audit.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from core.analysis.fundamentals import fetch_latest_bse_announcement, resolve_bse_scrip_code
from core.cortex.garuda import GarudaReflexEngine
from core.db.watchlist import get_watchlist
from core.db.agent_sessions import record_autonomous_event
from core.db.distributed_lock import job_lease

logger = logging.getLogger("equity_research.core.agents.watchers.bse")


async def _recheck_equity_thesis_background(ticker: str, headline: str):
    """Executes background thesis review following material exchange filing."""
    try:
        from core.analysis.dossier_report_synthesis import generate_stock_report
        # Execute synthesis asynchronously in background thread
        await asyncio.to_thread(generate_stock_report, ticker)
        record_autonomous_event(
            event_type="bse_reaudit_completed",
            ticker=ticker,
            trigger_source="bse_watcher",
            action_taken="thesis_impact_summarized",
            summary=f"Autonomous review completed for {ticker}. Governance metrics and risk pillars synchronized with latest exchange disclosure.",
            metadata={"headline": headline, "completed": True}
        )
        logger.info(f"✅ [BSE Watcher] Background thesis review completed for {ticker}")
    except Exception as e:
        logger.warning(f"BSE watcher background synthesis notice for {ticker}: {e}")


def invalidate_surgical_cache(ticker: str, pillar_id: Optional[int] = None) -> None:
    """Invalidates cached dossiers and reports for the given ticker following material catalyst."""
    try:
        from core.db.reports import get_report_by_ticker, get_archived_reports
        if hasattr(get_report_by_ticker, "cache_clear"):
            get_report_by_ticker.cache_clear()
        if hasattr(get_archived_reports, "cache_clear"):
            get_archived_reports.cache_clear()
        logger.info(f"⚡ Surgical cache invalidation executed for {ticker} (Pillar {pillar_id})")
    except Exception as e:
        logger.warning(f"Surgical cache invalidation warning for {ticker}: {e}")


async def scan_watchlist_bse_announcements() -> List[Dict[str, Any]]:
    """Scans active watchlist scrips for new material BSE announcements (batched)."""
    watchlist = get_watchlist()[:10]
    events_triggered = []

    for item in watchlist:
        ticker = item.get("ticker", "").strip().upper()
        if not ticker:
            continue
        try:
            # Resolve 6-digit numeric BSE scrip code before calling fetch_latest_bse_announcement
            scrip_code = item.get("scrip_code") or resolve_bse_scrip_code(ticker) or ticker
            latest = await asyncio.to_thread(fetch_latest_bse_announcement, str(scrip_code))
            if latest:
                delta = GarudaReflexEngine.classify_announcement(ticker, latest)
                is_material = delta.urgency in ["IMMEDIATE_REFRESH", "ROUTINE_PATCH"] or any(
                    w in latest.lower() for w in ["resignation", "pledge", "fraud", "litigation", "default", "merger", "acquisition"]
                )
                if is_material:
                    # Trigger surgical cache invalidation for the affected pillar
                    invalidate_surgical_cache(ticker, delta.target_pillar_id)
                    summary = f"Material disclosure detected for {ticker} [Pillar {delta.target_pillar_id}: {delta.catalyst_type}]: {latest[:95]}... Autonomous re-audit dispatched."
                    event_id = record_autonomous_event(
                        event_type="bse_material_filing",
                        ticker=ticker,
                        trigger_source="bse_watcher",
                        action_taken="auto_reaudit_dispatched",
                        summary=summary,
                        metadata={
                            "headline": latest,
                            "pillar_id": delta.target_pillar_id,
                            "catalyst_type": delta.catalyst_type,
                            "urgency": delta.urgency,
                            "delta_snippet": delta.delta_snippet_md,
                        }
                    )
                    events_triggered.append({"ticker": ticker, "event_id": event_id, "headline": latest, "delta": delta})
                    logger.info(f"🚨 [BSE Watcher] {summary}")
                    # Launch background thesis re-check
                    asyncio.create_task(_recheck_equity_thesis_background(ticker, latest))
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
            with job_lease("bse_watcher_loop", ttl_seconds=360, release_on_exit=True) as acquired:
                if acquired:
                    await scan_watchlist_bse_announcements()
                else:
                    logger.debug("📡 [BSE Watcher] Lease held by another worker. Skipping poll cycle.")
            await asyncio.sleep(300)
        except asyncio.CancelledError:
            logger.info("📡 [BSE Watcher] Watcher loop cancelled.")
            break
        except Exception as e:
            logger.error(f"📡 [BSE Watcher] Exception in watcher loop: {e}")
            await asyncio.sleep(60)
