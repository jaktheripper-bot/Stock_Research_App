#!/usr/bin/env python3
"""Dossier Provenance, Baseline Synchronization & Statutory Citations Remediation CLI (Feedback #5).

Audits and remediates equity dossier provenance bars, timestamps, and statutory citations across
BOTH SQLite (`reports.db`) and Supabase PostgreSQL (`SUPABASE_DB_URL` via `core.db.connection`):

1. Audits `reports` and `report_revisions` where `citations_json` is `NULL`, empty, or lacks primary statutory filings.
2. Resolves canonical 6-digit BSE scrip codes via `bse_master.resolve_bse_scrip_code()`.
3. Deterministically enriches citations with official statutory registry links (`bseindia.com`, `nseindia.com`)
   via `core.analysis.parser.enrich_and_classify_citations()`.
4. Extracts the reported Indian fiscal statement period (e.g. `Q3 FY26 • FY25 Audited (TTM)`) from report text
   via `core.analysis.parser.extract_financial_period_covered()`.
5. Compares `reports.baseline_price` against live/cached exchange quote (`cached_fundamentals.current_price`),
   flagging synthesis baseline drift deltas (>= 0.5%).

Usage Examples:
  # 1. Safe read-only audit & before/after preview (DEFAULT)
  python3 scripts/remediate_dossier_provenance.py --sqlite-path reports.db --dry-run

  # 2. Apply deterministic citation enrichment & provenance backfill
  python3 scripts/remediate_dossier_provenance.py --sqlite-path reports.db --apply

  # 3. Target specific tickers only (e.g., TCS, INFY)
  python3 scripts/remediate_dossier_provenance.py --sqlite-path reports.db --tickers TCS,INFY --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bse_master import resolve_bse_scrip_code, resolve_canonical_symbol
from core.analysis.parser import (
    enrich_and_classify_citations,
    extract_financial_period_covered,
)
from core.db.connection import get_db_connection, is_postgres_connection

logger = logging.getLogger("equity_research.scripts.remediate_dossier_provenance")


def _open_connection(sqlite_path: Optional[str] = None) -> Tuple[Any, bool, str]:
    """Opens either an explicit SQLite DB path or the active configured DB connection."""
    if sqlite_path:
        p = Path(sqlite_path)
        conn = sqlite3.connect(str(p), timeout=30.0)
        try:
            conn.execute("PRAGMA busy_timeout = 15000")
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception as e:
            logger.warning("PRAGMA setup notice for %s: %s", p, e)
        return conn, False, f"SQLite ({p})"
    conn = get_db_connection()
    is_pg = is_postgres_connection(conn)
    desc = "PostgreSQL (SUPABASE_DB_URL)" if is_pg else f"SQLite ({os.environ.get('DB_PATH', 'reports.db')})"
    return conn, is_pg, desc


def _ph(is_pg: bool) -> str:
    return "%s" if is_pg else "?"


def run_provenance_remediation(
    *,
    sqlite_path: Optional[str] = None,
    apply_changes: bool = False,
    tickers_filter: Optional[List[str]] = None,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Audits and optionally backfills dossier provenance and statutory citations."""
    conn, is_pg, target_desc = _open_connection(sqlite_path=sqlite_path)
    p = _ph(is_pg)
    cur = conn.cursor()

    summary: Dict[str, Any] = {
        "target_db": target_desc,
        "mode": "APPLY" if apply_changes else "DRY_RUN",
        "total_reports_scanned": 0,
        "citations_backfilled": [],
        "provenance_drift_flagged": [],
        "financial_periods_extracted": [],
        "missing_scrip_codes": [],
    }

    try:
        # 1. Fetch cached fundamentals to compare live/cached CMP against baseline
        cached_prices: Dict[str, float] = {}
        try:
            cur.execute("SELECT ticker, current_price FROM cached_fundamentals WHERE current_price IS NOT NULL")
            for row in cur.fetchall():
                try:
                    cached_prices[str(row[0]).strip().upper()] = float(row[1])
                except (ValueError, TypeError):
                    pass
        except Exception as cf_err:
            if is_pg:
                try:
                    conn.rollback()
                except Exception as rb_err:
                    logger.debug("Rollback notice after cached_fundamentals pre-fetch: %s", rb_err)
            logger.debug("cached_fundamentals price pre-fetch notice: %s", cf_err)

        # 2. Fetch all compiled reports (exclude PENDING_SYNTHESIS rows with NULL/empty report_text)
        query = """
            SELECT ticker, short_name, baseline_price, timestamp, citations_json, report_text
            FROM reports
            WHERE report_text IS NOT NULL AND TRIM(report_text) != ''
            ORDER BY ticker ASC
        """
        cur.execute(query)
        rows = cur.fetchall()

        has_rev_citations = False
        if apply_changes:
            try:
                if is_pg:
                    cur.execute(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'report_revisions' AND column_name = 'citations_json'"
                    )
                    has_rev_citations = cur.fetchone() is not None
                else:
                    cur.execute("PRAGMA table_info(report_revisions)")
                    has_rev_citations = any(str(r[1]) == "citations_json" for r in cur.fetchall())
            except Exception as col_err:
                if is_pg:
                    conn.rollback()
                logger.debug("report_revisions column check notice: %s", col_err)

        pending_updates: List[Tuple[str, str]] = []

        target_tickers_set = set(t.upper() for t in tickers_filter) if tickers_filter else None

        for row in rows:
            raw_ticker = str(row[0] or "").strip().upper()
            if target_tickers_set and raw_ticker not in target_tickers_set:
                continue

            summary["total_reports_scanned"] += 1
            short_name = str(row[1] or raw_ticker)
            baseline_price = float(row[2]) if row[2] is not None else None
            eval_date = str(row[3] or "")
            citations_raw = row[4]
            report_text = str(row[5] or "")

            # Resolve scrip code
            scrip_code = resolve_bse_scrip_code(raw_ticker)
            if not scrip_code:
                canonical = resolve_canonical_symbol(raw_ticker)
                if canonical and canonical != raw_ticker:
                    scrip_code = resolve_bse_scrip_code(canonical)

            if not scrip_code:
                summary["missing_scrip_codes"].append(raw_ticker)

            # Parse existing citations
            existing_citations: List[Dict[str, Any]] = []
            if citations_raw:
                try:
                    if isinstance(citations_raw, str):
                        parsed = json.loads(citations_raw)
                    else:
                        parsed = citations_raw
                    if isinstance(parsed, list):
                        existing_citations = parsed
                    elif isinstance(parsed, dict) and "citations" in parsed:
                        existing_citations = parsed["citations"]
                except Exception:
                    existing_citations = []

            # Check if primary statutory filings exist
            has_primary = any(
                isinstance(c, dict) and ("bseindia.com" in (c.get("uri") or "") or "nseindia.com" in (c.get("uri") or ""))
                for c in existing_citations
            )

            needs_enrichment = (len(existing_citations) == 0) or (not has_primary)

            # Extract Financial Period Covered
            period_covered = extract_financial_period_covered(report_text, reference_date=eval_date)
            summary["financial_periods_extracted"].append({
                "ticker": raw_ticker,
                "period_covered": period_covered,
            })

            # Check Price Drift vs Cached Current Price
            cached_price = cached_prices.get(raw_ticker)
            drift_pct = None
            if baseline_price and cached_price and baseline_price > 0:
                drift_pct = round(((cached_price - baseline_price) / baseline_price) * 100.0, 2)
                if abs(drift_pct) >= 0.5:
                    summary["provenance_drift_flagged"].append({
                        "ticker": raw_ticker,
                        "baseline_price": baseline_price,
                        "current_price": cached_price,
                        "drift_pct": drift_pct,
                    })

            if needs_enrichment:
                enriched = enrich_and_classify_citations(
                    existing_citations,
                    scrip_code=scrip_code,
                    ticker=raw_ticker,
                    company_name=short_name,
                )

                # Flatten structured dict back to canonical list
                all_citations = enriched.get("citations", [])
                primary_items = enriched.get("primary_statutory", [c for c in all_citations if c.get("tier") == "PRIMARY_STATUTORY"])
                secondary_items = enriched.get("secondary_grounding", [c for c in all_citations if c.get("tier") == "SECONDARY_GROUNDING"])
                new_citations_json = json.dumps(all_citations, ensure_ascii=False)

                summary["citations_backfilled"].append({
                    "ticker": raw_ticker,
                    "scrip_code": scrip_code,
                    "before_count": len(existing_citations),
                    "after_count": len(all_citations),
                    "primary_count": len(primary_items),
                    "secondary_count": len(secondary_items),
                })

                if apply_changes:
                    pending_updates.append((new_citations_json, raw_ticker))

        if apply_changes and pending_updates:
            update_sql = f"UPDATE reports SET citations_json = {p} WHERE ticker = {p}"
            if is_pg:
                from psycopg2.extras import execute_batch

                execute_batch(cur, update_sql, pending_updates, page_size=100)
                if has_rev_citations:
                    rev_sql = f"UPDATE report_revisions SET citations_json = {p} WHERE ticker = {p}"
                    execute_batch(cur, rev_sql, pending_updates, page_size=100)
            else:
                cur.executemany(update_sql, pending_updates)
                if has_rev_citations:
                    rev_sql = f"UPDATE report_revisions SET citations_json = {p} WHERE ticker = {p}"
                    cur.executemany(rev_sql, pending_updates)
            conn.commit()

    finally:
        conn.close()

    if not quiet:
        _print_terminal_report(summary)

    return summary


def _print_terminal_report(s: Dict[str, Any]) -> None:
    mode_str = "\033[1;32mAPPLIED (COMMITTED)\033[0m" if s["mode"] == "APPLY" else "\033[1;33mDRY-RUN (NO CHANGES MADE)\033[0m"
    print("\n" + "=" * 80)
    print(f" DOSSIER PROVENANCE & STATUTORY CITATIONS AUDIT [{mode_str}]")
    print(f" Database Target: {s['target_db']}")
    print(f" Total Reports Scanned: {s['total_reports_scanned']}")
    print("=" * 80)

    # 1. Citations Backfilled
    backfilled = s["citations_backfilled"]
    print(f"\n1. Citations Backfilled / Grounded: {len(backfilled)}")
    if backfilled:
        print(f"   {'TICKER':<12} {'SCRIP':<10} {'BEFORE':<8} {'AFTER':<8} {'PRIMARY':<10} {'SECONDARY':<10}")
        print("   " + "-" * 60)
        for item in backfilled[:25]:
            print(f"   {item['ticker']:<12} {item['scrip_code'] or 'N/A':<10} {item['before_count']:<8} {item['after_count']:<8} {item['primary_count']:<10} {item['secondary_count']:<10}")
        if len(backfilled) > 25:
            print(f"   ... and {len(backfilled) - 25} more tickers.")
    else:
        print("   ✓ All scanned reports already possess verified statutory citations.")

    # 2. Provenance Price Drift
    drift = s["provenance_drift_flagged"]
    print(f"\n2. Synthesis Baseline Price Drift Flagged (>= 0.5%): {len(drift)}")
    if drift:
        print(f"   {'TICKER':<12} {'BASELINE':<14} {'CURRENT':<14} {'DRIFT DELTA':<12}")
        print("   " + "-" * 54)
        for item in drift[:15]:
            sign = "+" if item["drift_pct"] > 0 else ""
            print(f"   {item['ticker']:<12} ₹{item['baseline_price']:<13,.2f} ₹{item['current_price']:<13,.2f} {sign}{item['drift_pct']}%")
        if len(drift) > 15:
            print(f"   ... and {len(drift) - 15} more tickers.")
    else:
        print("   ✓ Zero significant baseline price drift detected.")

    # 3. Financial Periods Sample
    periods = s["financial_periods_extracted"]
    print(f"\n3. Financial Statement Periods Sample (Total: {len(periods)}):")
    for item in periods[:8]:
        print(f"   • {item['ticker']:<10}: {item['period_covered']}")

    # 4. Missing Scrips
    missing = s["missing_scrip_codes"]
    if missing:
        print(f"\n4. Unresolved BSE Scrip Codes: {len(missing)} ({', '.join(missing[:10])})")

    print("\n" + "=" * 80)
    if s["mode"] == "DRY_RUN" and len(backfilled) > 0:
        print(" To apply these citation fixes to the database, run:")
        print("   python3 scripts/remediate_dossier_provenance.py --apply")
    print("=" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Remediate dossier provenance and backfill statutory BSE citations.")
    parser.add_argument("--sqlite-path", help="Explicit path to SQLite database (default: configured DB or reports.db)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate remediation without applying changes (default)")
    parser.add_argument("--apply", action="store_true", help="Apply fixes directly to database (default is dry-run)")
    parser.add_argument("--tickers", help="Comma-separated tickers to filter (e.g. TCS,INFY,RELIANCE)")
    parser.add_argument("--quiet", action="store_true", help="Suppress terminal output")
    parser.add_argument("--json", action="store_true", help="Output summary as JSON")

    args = parser.parse_args()

    tickers_list = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else None

    result = run_provenance_remediation(
        sqlite_path=args.sqlite_path,
        apply_changes=bool(args.apply and not args.dry_run),
        tickers_filter=tickers_list,
        quiet=args.quiet or args.json,
    )

    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
