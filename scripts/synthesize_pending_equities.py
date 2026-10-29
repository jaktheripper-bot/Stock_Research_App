#!/usr/bin/env python3
"""
Batch Queue Synthesizer, Drift Reconciler & Test-Artifact Cleaner.

Usage:
  python3 scripts/synthesize_pending_equities.py --dry-run
  python3 scripts/synthesize_pending_equities.py --clean-test-rows --reconcile-drift
  python3 scripts/synthesize_pending_equities.py --synthesize --limit 20 --delay 3.0
  python3 scripts/synthesize_pending_equities.py --audit-mfs 5
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bse_master import is_synthetic_test_symbol, resolve_canonical_symbol
from core.audit.invariants import KNOWN_STATIC_REPORT_TEMPLATE_PHRASES
from core.config import get_secret
from core.db.connection import (
    get_configured_supabase_url,
    get_db_connection,
    get_db_path,
    init_db,
    is_postgres_connection,
    now_ist_iso,
)
from core.db.reports import (
    get_all_equities_directory_sync,
    get_archived_reports,
    get_report_by_ticker,
    get_report_by_ticker_sync,
    get_report_revisions,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("equity_research.synthesize_pending")

ERROR_SIGNATURES = (
    "Live Synthesis Failed",
    "Live Synthesis Temporarily Unavailable",
    "Grounded synthesis channels are temporarily unavailable",
)

# NSE-only listed equities that do not trade on BSE (prevents name-substring collision with BSE ETFs)
NSE_ONLY_EQUITIES = frozenset({"BSE"})


def _resolve_target_symbol(sym: str) -> str:
    clean = (sym or "").strip().upper()
    if clean in NSE_ONLY_EQUITIES:
        return clean
    return resolve_canonical_symbol(clean) or clean


def _clear_report_caches() -> None:
    for fn in (
        get_archived_reports,
        get_report_by_ticker,
        get_report_revisions,
        get_all_equities_directory_sync,
    ):
        try:
            fn.cache_clear()
        except Exception as err:
            logger.debug("Cache clear notice: %s", err)


def clean_stray_test_rows(sqlite_path: Optional[str] = None) -> Dict[str, int]:
    """Removes stray synthetic test fixtures from active runtime DB and local SQLite."""
    counts: Dict[str, int] = {}
    conn = get_db_connection()
    is_pg_primary = is_postgres_connection(conn)
    targets = [("active_db", conn, is_pg_primary)]

    sq_path = sqlite_path or get_db_path()
    if is_pg_primary and os.path.exists(sq_path):
        targets.append(("local_sqlite", sqlite3.connect(sq_path), False))

    for label, db_conn, is_pg in targets:
        p = "%s" if is_pg else "?"
        cur = db_conn.cursor()
        removed = 0
        try:
            statements = [
                (f"DELETE FROM fund_forensic_dossiers WHERE scheme_code = {p}", ("TEST_GUARD_SCHEME_001",)),
                (f"DELETE FROM mutual_fund_schemes WHERE scheme_code = {p}", ("TEST_GUARD_SCHEME_001",)),
                (f"DELETE FROM credit_rating_events WHERE isin = {p}", ("INE999TEST01",)),
                (f"DELETE FROM corporate_debt_securities WHERE isin = {p}", ("INE999TEST01",)),
                (f"DELETE FROM reits_and_invits WHERE symbol = {p}", ("SMREIT_BAD_TEST",)),
            ]
            for sql, params in statements:
                cur.execute(sql, params)
                if cur.rowcount and cur.rowcount > 0:
                    removed += cur.rowcount
            db_conn.commit()
            counts[label] = removed
            logger.info("[%s] Purged %d stray synthetic test rows.", label, removed)
        except Exception as err:
            db_conn.rollback()
            logger.error("[%s] Failed cleaning test rows: %s", label, err)
            raise
        finally:
            cur.close()
            db_conn.close()
    return counts


def reconcile_pg_sqlite_drift(sqlite_path: Optional[str] = None) -> Dict[str, int]:
    """Bi-directionally reconciles compiled `reports` rows between Supabase PostgreSQL and local SQLite."""
    sq_path = sqlite_path or get_db_path()
    if not os.path.exists(sq_path) or not get_configured_supabase_url():
        logger.info("Skipping PG <-> SQLite drift reconciliation (single-DB environment).")
        return {"pushed_to_pg": 0, "pulled_to_sqlite": 0}

    pg_conn = get_db_connection()
    if not is_postgres_connection(pg_conn):
        pg_conn.close()
        return {"pushed_to_pg": 0, "pulled_to_sqlite": 0}

    sq_conn = sqlite3.connect(sq_path)
    pg_cur = pg_conn.cursor()
    sq_cur = sq_conn.cursor()
    pushed = 0
    pulled = 0

    try:
        cols = (
            "ticker, short_name, report_text, timestamp, baseline_price, "
            "baseline_pe, baseline_mcap, latest_announcement, citations_json"
        )
        pg_cur.execute(f"SELECT {cols} FROM reports")
        pg_map = {str(r[0]).upper(): r for r in pg_cur.fetchall() if not is_synthetic_test_symbol(r[0])}

        sq_cur.execute(f"SELECT {cols} FROM reports")
        sq_map = {str(r[0]).upper(): r for r in sq_cur.fetchall() if not is_synthetic_test_symbol(r[0])}

        # 1. Local SQLite -> Supabase PG (e.g. COALINDIA compiled locally, UNITDSPR queued row)
        for sym, sq_row in sorted(sq_map.items()):
            sq_has_text = len((sq_row[2] or "").strip()) >= 500
            pg_row = pg_map.get(sym)
            pg_has_text = bool(pg_row and len((pg_row[2] or "").strip()) >= 500)
            if pg_row is None or (sq_has_text and not pg_has_text):
                pg_cur.execute(
                    """
                    INSERT INTO reports (
                        ticker, short_name, report_text, timestamp, baseline_price,
                        baseline_pe, baseline_mcap, latest_announcement, citations_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        short_name = EXCLUDED.short_name,
                        report_text = CASE
                            WHEN EXCLUDED.report_text IS NOT NULL AND TRIM(EXCLUDED.report_text) <> ''
                            THEN EXCLUDED.report_text ELSE reports.report_text
                        END,
                        timestamp = EXCLUDED.timestamp,
                        baseline_price = COALESCE(EXCLUDED.baseline_price, reports.baseline_price),
                        baseline_pe = COALESCE(EXCLUDED.baseline_pe, reports.baseline_pe),
                        baseline_mcap = COALESCE(EXCLUDED.baseline_mcap, reports.baseline_mcap),
                        latest_announcement = COALESCE(EXCLUDED.latest_announcement, reports.latest_announcement),
                        citations_json = COALESCE(EXCLUDED.citations_json, reports.citations_json)
                    """,
                    sq_row,
                )
                pushed += 1
                logger.info("Pushed %s from local SQLite -> Supabase PostgreSQL.", sym)

        # 2. Supabase PG -> Local SQLite (e.g. 3MINDIA compiled in cloud PG)
        def _sq_param(val: Any) -> Any:
            if isinstance(val, Decimal):
                return float(val)
            if isinstance(val, (dict, list)):
                return json.dumps(val)
            return val

        for sym, pg_row in sorted(pg_map.items()):
            pg_has_text = len((pg_row[2] or "").strip()) >= 500
            sq_row = sq_map.get(sym)
            sq_has_text = bool(sq_row and len((sq_row[2] or "").strip()) >= 500)
            if sq_row is None or (pg_has_text and not sq_has_text):
                ts_str = str(pg_row[3]) if pg_row[3] is not None else now_ist_iso()
                row_for_sq = (
                    _sq_param(pg_row[0]),
                    _sq_param(pg_row[1]),
                    _sq_param(pg_row[2]),
                    ts_str,
                    _sq_param(pg_row[4]),
                    _sq_param(pg_row[5]),
                    _sq_param(pg_row[6]),
                    _sq_param(pg_row[7]),
                    _sq_param(pg_row[8]),
                )
                sq_cur.execute(
                    """
                    INSERT INTO reports (
                        ticker, short_name, report_text, timestamp, baseline_price,
                        baseline_pe, baseline_mcap, latest_announcement, citations_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (ticker) DO UPDATE SET
                        short_name = excluded.short_name,
                        report_text = CASE
                            WHEN excluded.report_text IS NOT NULL AND TRIM(excluded.report_text) <> ''
                            THEN excluded.report_text ELSE reports.report_text
                        END,
                        timestamp = excluded.timestamp,
                        baseline_price = COALESCE(excluded.baseline_price, reports.baseline_price),
                        baseline_pe = COALESCE(excluded.baseline_pe, reports.baseline_pe),
                        baseline_mcap = COALESCE(excluded.baseline_mcap, reports.baseline_mcap),
                        latest_announcement = COALESCE(excluded.latest_announcement, reports.latest_announcement),
                        citations_json = COALESCE(excluded.citations_json, reports.citations_json)
                    """,
                    row_for_sq,
                )
                pulled += 1
                logger.info("Pulled %s from Supabase PostgreSQL -> local SQLite.", sym)

        # 3. Clean up superseded empty ticker aliases (e.g. AMIORG -> ACUTAAS) once canonical dossier is compiled
        alias_cleaned = 0
        for db_cur, db_map, p_mark in ((pg_cur, pg_map, "%s"), (sq_cur, sq_map, "?")):
            for sym, row in list(db_map.items()):
                if len((row[2] or "").strip()) >= 500:
                    continue
                canon = _resolve_target_symbol(sym)
                if canon != sym:
                    canon_row = db_map.get(canon)
                    if canon_row and len((canon_row[2] or "").strip()) >= 1500:
                        canon_name = str(canon_row[1] or canon)
                        db_cur.execute(
                            f"UPDATE discovery_reel SET ticker = {p_mark}, company_name = {p_mark} WHERE ticker = {p_mark}",
                            (canon, canon_name, sym),
                        )
                        db_cur.execute(
                            f"DELETE FROM reports WHERE ticker = {p_mark} AND (report_text IS NULL OR TRIM(report_text) = '')",
                            (sym,),
                        )
                        alias_cleaned += 1

        pg_conn.commit()
        sq_conn.commit()
        _clear_report_caches()
        return {"pushed_to_pg": pushed, "pulled_to_sqlite": pulled, "aliases_reconciled": alias_cleaned}
    finally:
        pg_cur.close()
        sq_cur.close()
        pg_conn.close()
        sq_conn.close()


def fetch_prioritized_pending_equities() -> List[Tuple[str, str, str]]:
    """
    Returns [(ticker, short_name, priority_bucket), ...] for real equities in `reports`
    where `report_text` is NULL or empty, ordered:
      1. DISCOVERY_REEL -> 2. MF_HOLDING -> 3. ARCHIVE_QUEUE
    """
    init_db()
    conn = get_db_connection()
    is_pg = is_postgres_connection(conn)
    cur = conn.cursor()
    try:
        active_cond = "is_active = TRUE" if is_pg else "is_active = 1"
        cur.execute(f"SELECT DISTINCT ticker FROM discovery_reel WHERE {active_cond}")
        disc_set: Set[str] = {str(r[0]).strip().upper() for r in cur.fetchall() if r[0]}

        cur.execute("SELECT DISTINCT identifier FROM mutual_fund_holdings WHERE holding_type = 'EQUITY'")
        mf_set: Set[str] = {str(r[0]).strip().upper() for r in cur.fetchall() if r[0]}

        cur.execute(
            """
            SELECT ticker, COALESCE(short_name, ticker)
            FROM reports
            WHERE (report_text IS NULL OR TRIM(report_text) = '')
              AND SUBSTR(ticker, 1, 5) NOT IN ('TEST_', 'UNIT_', 'COAL_')
              AND SUBSTR(ticker, 1, 9) != 'UNITCOAL_'
              AND ticker NOT IN ('TESTCORP', 'TESTPEER', 'ZZTESTONLY', 'COALESCE_TEST')
            ORDER BY ticker ASC
            """
        )
        raw_pending = [
            (str(r[0]).strip().upper(), str(r[1]))
            for r in cur.fetchall()
            if not is_synthetic_test_symbol(r[0])
        ]

        prioritized: List[Tuple[int, str, str, str]] = []
        for sym, sname in raw_pending:
            if sym in disc_set:
                prioritized.append((0, sym, sname, "DISCOVERY_REEL"))
            elif sym in mf_set:
                prioritized.append((1, sym, sname, "MF_HOLDING"))
            else:
                prioritized.append((2, sym, sname, "ARCHIVE_QUEUE"))

        prioritized.sort(key=lambda item: (item[0], item[1]))
        return [(sym, sname, bucket) for _, sym, sname, bucket in prioritized]
    finally:
        cur.close()
        conn.close()


def _has_live_llm_credentials() -> bool:
    gemini_key = (os.environ.get("GEMINI_API_KEY") or get_secret("GEMINI_API_KEY") or "").strip()
    pplx_key = (os.environ.get("PERPLEXITY_API_KEY") or get_secret("PERPLEXITY_API_KEY") or "").strip()
    return bool(gemini_key or pplx_key)


def synthesize_pending_batch(
    limit: Optional[int] = None,
    tickers: Optional[List[str]] = None,
    delay: float = 3.0,
    max_retries: int = 2,
) -> Dict[str, int]:
    """Compiles pending equity reports via `generate_stock_report` with strict fail-closed validation."""
    from core.analysis.dossier_report_synthesis import generate_stock_report

    if not _has_live_llm_credentials():
        logger.error("Fail-closed abort: Neither GEMINI_API_KEY nor PERPLEXITY_API_KEY is configured. Zero rows modified.")
        return {"compiled": 0, "failed": 0, "aborted_no_credentials": 1}

    queue = fetch_prioritized_pending_equities()
    if tickers:
        wanted = {t.strip().upper() for t in tickers if t.strip()}
        queue = [item for item in queue if item[0] in wanted]
    if limit is not None and limit > 0:
        queue = queue[:limit]

    compiled = 0
    failed = 0
    total = len(queue)
    logger.info("Starting fail-closed 7-pillar synthesis for %d pending equities...", total)

    for idx, (sym, sname, bucket) in enumerate(queue, start=1):
        canon = _resolve_target_symbol(sym)
        logger.info("[%d/%d] [%s] Synthesizing %s (%s)...", idx, total, bucket, sym, sname)
        ok = False
        for attempt in range(1, max_retries + 1):
            try:
                text = (generate_stock_report(canon) or "").strip()
                is_valid = (
                    len(text) >= 1500
                    and "### Health Matrix" in text
                    and not any(sig in text for sig in ERROR_SIGNATURES)
                    and not any(tpl in text for tpl in KNOWN_STATIC_REPORT_TEMPLATE_PHRASES)
                )
                if is_valid:
                    archived = get_report_by_ticker_sync(canon) or get_report_by_ticker_sync(sym)
                    if archived and len((archived.get("report_text") or "").strip()) >= 1500:
                        compiled += 1
                        ok = True
                        logger.info("  -> Compiled & verified %s (%d chars).", sym, len(text))
                        break
                logger.warning("  -> Attempt %d/%d substance check failed for %s (len=%d).", attempt, max_retries, sym, len(text))
            except Exception as err:
                logger.warning("  -> Attempt %d/%d raised error for %s: %s", attempt, max_retries, sym, err)
            if attempt < max_retries:
                time.sleep(attempt * 3.0)

        if not ok:
            failed += 1
            logger.error("  -> Fail-closed: %s remains in PENDING queue (report_text=NULL).", sym)

        if idx < total and delay > 0:
            time.sleep(delay)

    _clear_report_caches()
    return {"compiled": compiled, "failed": failed, "aborted_no_credentials": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description="Pending Asset Analysis Queue Manager & Reconciler")
    parser.add_argument("--dry-run", action="store_true", help="Inspect prioritized pending queue without mutating DB")
    parser.add_argument("--clean-test-rows", action="store_true", help="Purge stray synthetic test records")
    parser.add_argument("--reconcile-drift", action="store_true", help="Sync compiled reports between PG and local SQLite")
    parser.add_argument("--synthesize", action="store_true", help="Compile pending equity dossiers via LLM engine")
    parser.add_argument("--limit", type=int, default=None, help="Max pending equities to synthesize in this run")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated subset of tickers to synthesize")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between synthesis calls (default: 3.0)")
    parser.add_argument("--audit-mfs", type=int, default=0, help="Run daily look-through audit for N un-audited MF schemes")
    args = parser.parse_args()

    if args.clean_test_rows and not args.dry_run:
        clean_stray_test_rows()

    if args.reconcile_drift and not args.dry_run:
        drift_res = reconcile_pg_sqlite_drift()
        logger.info("Drift reconciliation summary: %s", drift_res)

    pending = fetch_prioritized_pending_equities()
    by_bucket: Dict[str, int] = {}
    for _, _, b in pending:
        by_bucket[b] = by_bucket.get(b, 0) + 1
    logger.info("Pending Equity Queue: %d total | Breakdown: %s", len(pending), by_bucket)

    if args.dry_run or not (args.synthesize or args.clean_test_rows or args.reconcile_drift or args.audit_mfs > 0):
        for i, (sym, sname, b) in enumerate(pending[:30], start=1):
            print(f"  {i:3d}. [{b:14s}] {sym:16s} | {sname}")
        if len(pending) > 30:
            print(f"  ... and {len(pending) - 30} more pending equities.")
        return

    if args.synthesize:
        ticker_list = [t.strip() for t in args.tickers.split(",")] if args.tickers else None
        res = synthesize_pending_batch(limit=args.limit, tickers=ticker_list, delay=args.delay)
        logger.info("Equity synthesis batch result: %s", res)
        reconcile_pg_sqlite_drift()

    if args.audit_mfs > 0:
        from core.analysis.fund_overlap_auditor import audit_single_fund_daily
        for idx in range(args.audit_mfs):
            try:
                out = audit_single_fund_daily(None)
                logger.info(
                    "[MF %d/%d] Audited %s (Health=%.1f)",
                    idx + 1,
                    args.audit_mfs,
                    out.get("scheme_code"),
                    out.get("composite_health_score", 0.0),
                )
            except Exception as mf_err:
                logger.warning("[MF %d/%d] Audit halted/skipped: %s", idx + 1, args.audit_mfs, mf_err)
                break


if __name__ == "__main__":
    main()

