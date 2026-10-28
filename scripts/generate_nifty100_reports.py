"""
Batch Generation Pipeline for Nifty 100 Research Dossiers.

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

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.universe.nifty100 import NIFTY_100_CONSTITUENTS, get_nifty100_symbols, get_nifty100_constituent
from core.analysis.dossier_report_synthesis import generate_stock_report
from core.db.connection import get_db_connection, is_postgres_connection
from core.db.reports import get_report_by_ticker, get_report_by_ticker_sync, get_archived_reports
from core.config import get_secret
from bse_master import resolve_bse_scrip_code, resolve_canonical_symbol

IST = timezone(timedelta(hours=5, minutes=30))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_nifty100")

STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nifty100_batch_status.json")
_STATUS_LOCK = threading.Lock()
_ERROR_SIGNATURES = (
    "Live Synthesis Failed",
    "Live Synthesis Temporarily Unavailable",
    "Grounded synthesis channels are temporarily unavailable",
)

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
    """Checks whether cached report is a valid >=500-char dossier within the acceptable TTL window."""
    if not cached_report:
        return False
    txt = (cached_report.get("report_text") or "").strip()
    if len(txt) < 500 or any(sig in txt for sig in _ERROR_SIGNATURES):
        return False
    raw_ts = cached_report.get("timestamp") or cached_report.get("raw_timestamp")
    if not raw_ts:
        return False
    try:
        from core.presentation.formatters import _coerce_datetime
        dt = _coerce_datetime(raw_ts)
        if dt is None:
            return False
        now = datetime.now(IST)
        return (now - dt).days < max_age_days
    except Exception:
        return False


def _fetch_nifty100_reports_map(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """Fetches cached report metadata for all Nifty 100 symbols (and canonical exchange aliases) in a single DB round-trip."""
    alias_map = {s.strip().upper(): resolve_canonical_symbol(s.strip().upper()) for s in symbols if s}
    query_syms = list(set(alias_map.keys()) | set(alias_map.values()) | {"TMPV", "LTM"})
    out: Dict[str, Dict[str, Any]] = {}
    conn = get_db_connection()
    is_pg = is_postgres_connection(conn)
    cur = conn.cursor()
    try:
        if is_pg:
            cur.execute(
                "SELECT ticker, report_text, timestamp FROM reports WHERE ticker = ANY(%s)",
                (query_syms,),
            )
        else:
            placeholders = ",".join(["?"] * len(query_syms))
            cur.execute(
                f"SELECT ticker, report_text, timestamp FROM reports WHERE ticker IN ({placeholders})",
                query_syms,
            )
        for ticker, r_text, ts in cur.fetchall():
            out[str(ticker).upper()] = {"ticker": ticker, "report_text": r_text, "timestamp": ts}
        for orig_sym, canon_sym in alias_map.items():
            if orig_sym not in out and canon_sym in out:
                out[orig_sym] = out[canon_sym]
        if "TATAMOTORS" not in out and "TMPV" in out:
            out["TATAMOTORS"] = out["TMPV"]
        if "LTIM" not in out and "LTM" in out:
            out["LTIM"] = out["LTM"]
    finally:
        cur.close()
        conn.close()
    return out


def print_status_summary():
    """Prints a formatted summary of Nifty 100 research coverage."""
    symbols = get_nifty100_symbols()
    state = load_batch_status()
    reports_map = _fetch_nifty100_reports_map(symbols)

    covered_fresh = 0
    covered_stale = 0
    uncovered = 0

    print("=" * 70)
    print(" 📊 NIFTY 100 RESEARCH COVERAGE LEDGER")
    print("=" * 70)

    for s in symbols:
        meta = get_nifty100_constituent(s)
        rep = reports_map.get(s.upper())
        has_valid_body = bool(rep and len((rep.get("report_text") or "").strip()) >= 500)
        fresh = is_report_fresh(rep)
        if has_valid_body and fresh:
            covered_fresh += 1
            st = "✅ FRESH"
        elif has_valid_body:
            covered_stale += 1
            st = "⚠️ STALE"
        else:
            uncovered += 1
            st = "❌ MISSING"

        last_run = state.get("tickers", {}).get(s, {}).get("status", "-")
        if covered_fresh + covered_stale + uncovered <= 10 or not fresh:
            name = (meta.get("company_name") if meta else s)[:30]
            print(f"[{st}] {s:<12} {name:<32} Status: {last_run}")

    print("-" * 70)
    print(f"Summary: Total: {len(symbols)} | Fresh: {covered_fresh} | Stale: {covered_stale} | Uncovered: {uncovered}")
    print(f"Coverage Percentage: {(covered_fresh / len(symbols)) * 100:.1f}%")
    print("=" * 70)


def generate_single_stock(symbol: str, meta: Dict[str, Any], force: bool = False, max_retries: int = 3) -> Dict[str, Any]:
    """Generates 7-pillar research report for a single stock with fail-closed archival verification."""
    canon_sym = resolve_canonical_symbol(symbol)
    cached = get_report_by_ticker_sync(symbol) or (get_report_by_ticker_sync(canon_sym) if canon_sym != symbol else None)
    if not cached and symbol == "TATAMOTORS":
        cached = get_report_by_ticker_sync("TMPV")
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
    logger.info(f"🔬 Starting 7-Pillar Analysis for {symbol} ({company_name})...")
    start_time = time.time()

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            report_text = generate_stock_report(symbol)
            clean_body = (report_text or "").strip()
            has_error_sig = any(sig in clean_body for sig in _ERROR_SIGNATURES)
            if len(clean_body) >= 500 and not has_error_sig:
                archived = get_report_by_ticker_sync(symbol) or (get_report_by_ticker_sync(canon_sym) if canon_sym != symbol else None)
                if not archived and symbol == "TATAMOTORS":
                    archived = get_report_by_ticker_sync("TMPV")
                arch_len = len((archived.get("report_text") or "").strip()) if archived else 0
                if arch_len >= 500:
                    elapsed = time.time() - start_time
                    logger.info(f"✅ Successfully compiled & archived dossier for {symbol} in {elapsed:.1f}s ({arch_len} chars).")
                    return {
                        "symbol": symbol,
                        "status": "SUCCESS",
                        "latency_seconds": round(elapsed, 1),
                        "report_length": arch_len,
                        "error": None,
                        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
                    }
                last_error = f"Generated {len(clean_body)} chars for {symbol} but DB archive verification failed ({arch_len} chars)"
                logger.warning(f"⚠️ Attempt {attempt}/{max_retries} for {symbol} failed: {last_error}")
            else:
                last_error = (
                    f"Synthesis returned error banner or truncated text ({len(clean_body)} chars)"
                    if has_error_sig
                    else f"Empty or truncated report returned ({len(clean_body)} chars)"
                )
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
    sync_supabase: bool = False,
    workers: int = 1,
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
    safe_workers = max(1, min(int(workers or 1), 6))
    logger.info(f"🚀 Launching Nifty 100 Batch Generation Pipeline for {total} equities...")
    logger.info(f"Parameters: force={force}, delay={delay}s, workers={safe_workers}, sync_supabase={sync_supabase}")

    state = load_batch_status()
    success_count = 0
    skipped_count = 0
    failed_count = 0
    start_batch = time.time()

    if safe_workers == 1:
        for idx, item in enumerate(target_universe, start=1):
            symbol = item["symbol"]
            print(f"\n[{idx}/{total}] Processing {symbol} ({item.get('company_name')}) [Sector: {item.get('sector')}]")
            res = generate_single_stock(symbol, item, force=force)
            with _STATUS_LOCK:
                state.setdefault("tickers", {})[symbol] = res
                save_batch_status(state)
            if res["status"] == "SUCCESS":
                success_count += 1
            elif res["status"] == "SKIPPED":
                skipped_count += 1
            else:
                failed_count += 1
            if idx < total and res["status"] != "SKIPPED":
                time.sleep(delay)
    else:
        # Fast-path skip check using batch map so worker threads only run missing/stale tickers
        reports_map = _fetch_nifty100_reports_map([it["symbol"] for it in target_universe])
        to_generate: List[Dict[str, Any]] = []
        for item in target_universe:
            sym = item["symbol"]
            rep = reports_map.get(sym.upper())
            if rep and is_report_fresh(rep) and not force:
                skipped_count += 1
                with _STATUS_LOCK:
                    state.setdefault("tickers", {})[sym] = {
                        "symbol": sym,
                        "status": "SKIPPED",
                        "report_length": len(rep.get("report_text") or ""),
                        "error": None,
                        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
                    }
            else:
                to_generate.append(item)
        with _STATUS_LOCK:
            save_batch_status(state)
        logger.info(f"⏭️ Pre-screened {skipped_count} fresh Nifty 100 stocks; dispatching {len(to_generate)} to {safe_workers} workers...")

        with ThreadPoolExecutor(max_workers=safe_workers) as pool:
            fut_map = {pool.submit(generate_single_stock, it["symbol"], it, force): it for it in to_generate}
            for fut in as_completed(fut_map):
                it = fut_map[fut]
                sym = it["symbol"]
                try:
                    res = fut.result()
                except Exception as exc:
                    res = {
                        "symbol": sym,
                        "status": "FAILED",
                        "latency_seconds": 0.0,
                        "report_length": 0,
                        "error": str(exc),
                        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
                    }
                with _STATUS_LOCK:
                    state.setdefault("tickers", {})[sym] = res
                    save_batch_status(state)
                if res["status"] == "SUCCESS":
                    success_count += 1
                elif res["status"] == "SKIPPED":
                    skipped_count += 1
                else:
                    failed_count += 1

    try:
        get_archived_reports.cache_clear()
        get_report_by_ticker.cache_clear()
    except Exception:
        pass

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
    parser.add_argument("--workers", type=int, default=1, help="Parallel synthesis workers (1-6, default 1)")
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
        sync_supabase=args.sync_supabase,
        workers=args.workers,
    )

if __name__ == "__main__":
    main()
