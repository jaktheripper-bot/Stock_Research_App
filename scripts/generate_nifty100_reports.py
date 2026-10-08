"""
Batch Generation Pipeline for Nifty 100 Institutional Research Dossiers.

Iterates through India's canonical Nifty 100 universe, invokes the core 7-pillar
fundamental analysis engine (BSE filings + Gemini reasoning + citation extraction),
archives reports to the primary database, and syncs to Supabase.
"""

import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.universe.nifty100 import NIFTY_100_CONSTITUENTS, get_nifty100_symbols, get_nifty100_constituent
from core.analysis.engine import generate_stock_report
from core.db.reports import get_report_by_ticker, get_archived_reports
from core.config import get_secret
from bse_master import resolve_bse_scrip_code

IST = timezone(timedelta(hours=5, minutes=30))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_nifty100")

STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nifty100_batch_status.json")

def load_batch_status() -> Dict[str, Any]:
    """Loads batch execution state ledger from disk."""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"updated_at": None, "tickers": {}}

def save_batch_status(status_data: Dict[str, Any]):
    """Persists batch execution state ledger to disk atomically."""
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    status_data["updated_at"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    tmp = f"{STATUS_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status_data, f, indent=2)
    os.replace(tmp, STATUS_FILE)

def is_report_fresh(cached_report: Dict[str, Any], max_age_days: int = 14) -> bool:
    """Checks whether cached report timestamp is within the acceptable TTL window."""
    if not cached_report or not cached_report.get("report_text"):
        return False
    raw_ts = cached_report.get("timestamp")
    if not raw_ts:
        return False
    try:
        if isinstance(raw_ts, datetime):
            dt = raw_ts
        elif isinstance(raw_ts, str):
            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        else:
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - dt).days < max_age_days
    except Exception:
        return False

def print_status_summary():
    """Prints a formatted summary of Nifty 100 research coverage."""
    symbols = get_nifty100_symbols()
    state = load_batch_status()
    
    covered_fresh = 0
    covered_stale = 0
    uncovered = 0

    print("=" * 70)
    print(" 📊 NIFTY 100 INSTITUTIONAL RESEARCH COVERAGE LEDGER")
    print("=" * 70)
    
    for s in symbols:
        meta = get_nifty100_constituent(s)
        rep = get_report_by_ticker(s)
        fresh = is_report_fresh(rep)
        if rep and fresh:
            covered_fresh += 1
            st = "✅ FRESH"
        elif rep:
            covered_stale += 1
            st = "⚠️ STALE"
        else:
            uncovered += 1
            st = "❌ MISSING"
        
        last_run = state.get("tickers", {}).get(s, {}).get("status", "-")
        # Print sample
        if covered_fresh + covered_stale + uncovered <= 10 or not fresh:
            name = (meta.get("company_name") if meta else s)[:30]
            print(f"[{st}] {s:<12} {name:<32} Status: {last_run}")
    
    print("-" * 70)
    print(f"Summary: Total: {len(symbols)} | Fresh: {covered_fresh} | Stale: {covered_stale} | Uncovered: {uncovered}")
    print(f"Coverage Percentage: {(covered_fresh / len(symbols)) * 100:.1f}%")
    print("=" * 70)

def generate_single_stock(symbol: str, meta: Dict[str, Any], force: bool = False, max_retries: int = 3) -> Dict[str, Any]:
    """Generates 7-pillar institutional research report for a single stock."""
    # Check cache
    cached = get_report_by_ticker(symbol)
    if cached and is_report_fresh(cached) and not force:
        logger.info(f"⏭️ Skipping {symbol}: Fresh report exists in database ({len(cached.get('report_text', ''))} chars).")
        return {
            "symbol": symbol,
            "status": "SKIPPED",
            "report_length": len(cached.get("report_text", "")),
            "error": None,
            "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        }

    company_name = meta.get("company_name", symbol) if meta else symbol
    logger.info(f"🔬 Starting 7-Pillar Institutional Analysis for {symbol} ({company_name})...")
    start_time = time.time()

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            report_text = generate_stock_report(symbol)
            if report_text and len(report_text.strip()) > 300:
                elapsed = time.time() - start_time
                logger.info(f"✅ Successfully compiled & archived dossier for {symbol} in {elapsed:.1f}s ({len(report_text)} chars).")
                return {
                    "symbol": symbol,
                    "status": "SUCCESS",
                    "latency_seconds": round(elapsed, 1),
                    "report_length": len(report_text),
                    "error": None,
                    "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
                }
            else:
                last_error = f"Empty or truncated report returned ({len(report_text) if report_text else 0} chars)"
                logger.warning(f"⚠️ Attempt {attempt}/{max_retries} for {symbol} failed: {last_error}")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"⚠️ Attempt {attempt}/{max_retries} for {symbol} raised error: {e}")
        
        if attempt < max_retries:
            backoff = attempt * 3.0
            logger.info(f"Retrying {symbol} in {backoff:.1f}s...")
            time.sleep(backoff)

    elapsed = time.time() - start_time
    logger.error(f"❌ Failed to generate report for {symbol} after {max_retries} attempts: {last_error}")
    return {
        "symbol": symbol,
        "status": "FAILED",
        "latency_seconds": round(elapsed, 1),
        "report_length": 0,
        "error": last_error,
        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    }

def run_nifty100_batch(
    limit: int = None,
    tickers: List[str] = None,
    force: bool = False,
    delay: float = 2.0,
    sync_supabase: bool = False
):
    """Executes the batch generation pipeline across the Nifty 100 universe."""
    universe = NIFTY_100_CONSTITUENTS
    if tickers:
        selected_symbols = [t.strip().upper() for t in tickers]
        target_universe = [item for item in universe if item["symbol"] in selected_symbols]
    else:
        target_universe = universe

    if limit and limit > 0:
        target_universe = target_universe[:limit]

    total = len(target_universe)
    logger.info(f"🚀 Launching Nifty 100 Batch Generation Pipeline for {total} equities...")
    logger.info(f"Parameters: force={force}, delay={delay}s, sync_supabase={sync_supabase}")

    state = load_batch_status()
    success_count = 0
    skipped_count = 0
    failed_count = 0
    start_batch = time.time()

    for idx, item in enumerate(target_universe, start=1):
        symbol = item["symbol"]
        print(f"\n[{idx}/{total}] Processing {symbol} ({item.get('company_name')}) [Sector: {item.get('sector')}]")
        
        res = generate_single_stock(symbol, item, force=force)
        
        # Update persistent ledger
        state.setdefault("tickers", {})[symbol] = res
        save_batch_status(state)

        if res["status"] == "SUCCESS":
            success_count += 1
        elif res["status"] == "SKIPPED":
            skipped_count += 1
        else:
            failed_count += 1

        # Inter-stock polite pause
        if idx < total and res["status"] != "SKIPPED":
            time.sleep(delay)

    total_time = time.time() - start_batch
    print("\n" + "=" * 70)
    print(f"🏁 NIFTY 100 BATCH PIPELINE RUN COMPLETED in {total_time/60:.1f} minutes")
    print(f"   Success: {success_count} | Skipped (Cached): {skipped_count} | Failed: {failed_count} | Total Processed: {total}")
    print("=" * 70)

    if sync_supabase:
        logger.info("Initiating automatic Supabase synchronization...")
        try:
            from scripts.sync_to_supabase import main as sync_main
            sys.argv = ["sync_to_supabase.py"]
            sync_main()
        except Exception as se:
            logger.error(f"Error during post-batch Supabase sync: {se}")

def main():
    parser = argparse.ArgumentParser(description="Nifty 100 Batch Research Generation Engine")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N stocks")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated list of symbols (e.g. RELIANCE,TCS,HDFCBANK)")
    parser.add_argument("--force", action="store_true", help="Force regeneration even if freshly cached")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between generation requests in seconds")
    parser.add_argument("--sync-supabase", action="store_true", help="Sync to Supabase after execution")
    parser.add_argument("--status", action="store_true", help="Display coverage status ledger and exit")
    args = parser.parse_args()

    if args.status:
        print_status_summary()
        return

    ticker_list = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else None
    run_nifty100_batch(
        limit=args.limit,
        tickers=ticker_list,
        force=args.force,
        delay=args.delay,
        sync_supabase=args.sync_supabase
    )

if __name__ == "__main__":
    main()
