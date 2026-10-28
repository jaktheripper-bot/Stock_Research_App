"""
Comprehensive Reports Database Batch Updater
=============================================
Iterates through all equity research dossiers in `reports.db`:
1. Fetches real-time exchange quotes, P/E multiples, and market caps via Angel One SmartAPI (with resilient fallbacks).
2. Updates `reports` table with official exchange metrics and refreshed timestamp.
3. Records an archived audit snapshot in `report_revisions` for thesis drift monitoring.
4. Synchronizes all updated reports to Supabase cloud storage & PostgREST database.
"""

import os
import sys
import time
import math
import sqlite3
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Ensure repository root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.ingestion.angel_one import AngelOneGateway
from core.db.connection import get_db_path, IST, now_ist_iso
from core.config import get_secret
from bse_master import resolve_canonical_symbol

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("update_all_reports")


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    s = str(val).strip().replace(",", "")
    if s.upper() in ("N/A", "NONE", "", "NAN", "NULL", "LOSS-MAKING", "UNDEFINED"):
        return None
    try:
        f = float(s)
        return None if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return None


def get_all_report_tickers(db_path: str) -> list:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        SELECT ticker, short_name, baseline_price, baseline_pe, baseline_mcap, report_text, citations_json 
        FROM reports 
        ORDER BY ticker ASC
    """)
    rows = c.fetchall()
    conn.close()
    return rows


def fetch_updated_metrics_for_ticker(row: tuple) -> Dict[str, Any]:
    """
    Fetches real-time market data from Angel One SmartAPI with zero-crash fallbacks.
    """
    ticker, short_name, old_price, old_pe, old_mcap, report_text, citations_json = row
    canonical = resolve_canonical_symbol(ticker) or ticker

    old_p_float = _safe_float(old_price)
    old_pe_float = _safe_float(old_pe)
    old_mcap_float = _safe_float(old_mcap)

    quote = None
    if AngelOneGateway.is_configured():
        try:
            quote = AngelOneGateway.get_stock_quote(canonical)
        except Exception as e:
            logger.debug(f"Angel One quote lookup notice for {canonical}: {e}")

    price = None
    pe = old_pe
    mcap = old_mcap_float
    source = "Unchanged"

    if quote and quote.get("ltp") is not None:
        p_val = _safe_float(quote.get("ltp"))
        if p_val and p_val > 0:
            price = p_val
            source = quote.get("source", "Angel One SmartAPI")

            # Adjust P/E and Market Cap proportionally to live price movement if historical base exists
            if old_p_float and old_p_float > 0:
                price_ratio = price / old_p_float
                if old_pe_float and old_pe_float > 0:
                    pe = f"{old_pe_float * price_ratio:.2f}"
                if old_mcap_float and old_mcap_float > 0:
                    mcap = round(old_mcap_float * price_ratio, 2)

    if price is None:
        price = old_p_float

    return {
        "ticker": ticker,
        "canonical": canonical,
        "price": price,
        "pe": pe,
        "mcap": mcap,
        "source": source
    }


def update_database_reports(db_path: str, max_workers: int = 6):
    reports = get_all_report_tickers(db_path)
    total = len(reports)
    logger.info(f"🚀 Starting exchange batch update for {total} reports in {db_path}...")

    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {executor.submit(fetch_updated_metrics_for_ticker, row): row[0] for row in reports}
        completed = 0
        for future in as_completed(future_to_ticker):
            completed += 1
            t = future_to_ticker[future]
            try:
                res = future.result()
                results[t] = res
                p_str = f"₹{res['price']:,.2f}" if res['price'] else "N/A"
                logger.info(f"[{completed}/{total}] {t} ➔ {p_str} (P/E: {res['pe'] or 'N/A'}) [{res['source']}]")
            except Exception as e:
                logger.warning(f"[{completed}/{total}] Error updating {t}: {e}")

    # Commit updates back to SQLite database (preserving qualitative TTL timestamps & NOT NULL invariants)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Self-heal any legacy integer-epoch timestamps written by older versions
    c.execute("UPDATE reports SET timestamp = datetime(timestamp, 'unixepoch') WHERE typeof(timestamp) = 'integer'")
    c.execute("UPDATE report_revisions SET timestamp = datetime(timestamp, 'unixepoch') WHERE typeof(timestamp) = 'integer'")

    now_iso = now_ist_iso()
    quotes_synced = 0
    revisions_archived = 0
    material_moves_flagged = 0

    for row in reports:
        ticker, short_name, old_price, old_pe, old_mcap, report_text, citations_json = row
        new_data = results.get(ticker)
        if not new_data:
            continue

        new_price = new_data["price"] if new_data["price"] is not None else old_price
        new_pe = new_data["pe"] if new_data["pe"] is not None else old_pe
        new_mcap = new_data["mcap"] if new_data["mcap"] is not None else old_mcap
        live_fetched = new_data.get("source") != "Unchanged" and new_data.get("price") is not None

        # 1. Sync live exchange quote into cached_fundamentals whenever available
        if live_fetched:
            c.execute(
                """
                UPDATE cached_fundamentals
                SET current_price = ?,
                    pe_ratio = COALESCE(?, pe_ratio),
                    market_cap = COALESCE(?, market_cap),
                    updated_at = ?
                WHERE ticker = ?
                """,
                (new_price, str(new_pe) if new_pe is not None else None, new_mcap, now_iso, ticker),
            )
            quotes_synced += 1

        has_compiled_prose = bool(report_text and str(report_text).strip())
        if not has_compiled_prose:
            # Pending compilation queue row: update exchange baselines ONLY; preserve timestamp & skip report_revisions
            c.execute(
                """
                UPDATE reports
                SET baseline_price = ?, baseline_pe = ?, baseline_mcap = ?
                WHERE ticker = ?
                """,
                (new_price, new_pe, new_mcap, ticker),
            )
            continue

        # 2. Compiled dossier row: preserve >=5% drift for MaterialChangeGate Pillar 5 & 6 re-synthesis
        old_p_float = _safe_float(old_price)
        price_delta = (
            abs(float(new_price) - old_p_float) / old_p_float
            if (live_fetched and old_p_float and old_p_float > 0)
            else 0.0
        )
        if live_fetched and price_delta < 0.05:
            c.execute(
                """
                UPDATE reports
                SET baseline_price = ?, baseline_pe = ?, baseline_mcap = ?
                WHERE ticker = ?
                """,
                (new_price, new_pe, new_mcap, ticker),
            )
            c.execute(
                """
                INSERT INTO report_revisions (
                    ticker, short_name, report_text, timestamp,
                    baseline_price, baseline_pe, baseline_mcap, revision_trigger, citations_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker, short_name, report_text, now_iso,
                    new_price, new_pe, new_mcap, "EXCHANGE_FEED_REFRESH", citations_json,
                ),
            )
            revisions_archived += 1
        elif live_fetched and price_delta >= 0.05:
            material_moves_flagged += 1

    conn.commit()
    conn.close()
    logger.info(
        f"✅ Exchange feed refresh complete across {total} tickers: "
        f"{quotes_synced} live quotes synced, {revisions_archived} revisions archived, "
        f"{material_moves_flagged} >=5% moves preserved for Pillar 5/6 re-synthesis."
    )


def main():
    db_path = get_db_path()
    update_database_reports(db_path, max_workers=6)

    # Trigger Supabase sync (direct PostgreSQL first, PostgREST fallback second)
    logger.info("📡 Synchronizing updated reports with Supabase...")
    try:
        from scripts.sync_to_supabase import (
            get_local_reports,
            get_local_revisions,
            sync_via_postgresql,
            sync_via_rest,
        )
        pg_url = get_secret("SUPABASE_DB_URL")
        sb_url = get_secret("SUPABASE_URL")
        service_key = get_secret("SUPABASE_SERVICE_ROLE_KEY")
        reports = get_local_reports(db_path)
        if pg_url:
            revisions = get_local_revisions(db_path)
            res = sync_via_postgresql(reports, revisions, pg_url, sqlite_path=db_path)
            logger.info(f"☁️  Supabase PostgreSQL sync complete: {res}")
        elif sb_url and service_key:
            res = sync_via_rest(reports, sb_url, service_key)
            logger.info(f"☁️  Supabase REST sync complete: {res}")
        else:
            logger.warning("Supabase credentials not configured in environment.")
    except Exception as e:
        logger.warning(f"Supabase synchronization notice: {e}")


if __name__ == "__main__":
    main()
