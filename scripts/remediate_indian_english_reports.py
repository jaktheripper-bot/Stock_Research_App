#!/usr/bin/env python3
"""
Database remediation script: Enforces English (India) / British spelling
site-wide across all stored research reports, historical revisions,
fund forensic dossiers, and discovery reel theses in reports.db.

Usage:
    python3 scripts/remediate_indian_english_reports.py --dry-run
    python3 scripts/remediate_indian_english_reports.py --apply
"""

import argparse
import logging
import os
import sqlite3
import sys
from typing import Any, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analysis.language_filter import enforce_indian_english, detect_americanisms
from core.db.connection import get_db_connection, is_postgres_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("remediate_indian_english")


def _open_target_connection(sqlite_path: Optional[str] = None) -> Tuple[Any, bool, str]:
    if sqlite_path:
        conn = sqlite3.connect(sqlite_path, timeout=30.0)
        return conn, False, f"SQLite ({sqlite_path})"
    conn = get_db_connection()
    is_pg = is_postgres_connection(conn)
    label = "PostgreSQL (SUPABASE_DB_URL)" if is_pg else f"SQLite ({os.environ.get('DB_PATH', 'reports.db')})"
    return conn, is_pg, label


def remediate_table(conn: Any, is_pg: bool, table: str, pk_col: str, text_col: str, apply_changes: bool = False) -> Tuple[int, int]:
    cursor = conn.cursor()
    cursor.execute(f"SELECT {pk_col}, {text_col} FROM {table} WHERE {text_col} IS NOT NULL AND TRIM({text_col}) != ''")
    rows = cursor.fetchall()

    scanned = len(rows)
    updated = 0

    updates: List[Tuple[str, Any]] = []

    for pk_val, text in rows:
        if not text:
            continue
        cleaned = enforce_indian_english(text)
        if cleaned != text:
            updated += 1
            updates.append((cleaned, pk_val))
            if not apply_changes and updated <= 5:
                ams = detect_americanisms(text)
                terms = [a["term"] for a in ams[:3]]
                logger.info(f"[{table}] ID {pk_val}: detected Americanisms {terms}")

    if apply_changes and updates:
        if is_pg:
            from psycopg2.extras import execute_batch
            raw_cur = getattr(cursor, "_cur", cursor)
            execute_batch(raw_cur, f"UPDATE {table} SET {text_col} = %s WHERE {pk_col} = %s", updates, page_size=100)
        else:
            cursor.executemany(f"UPDATE {table} SET {text_col} = ? WHERE {pk_col} = ?", updates)
        conn.commit()
        logger.info(f"[{table}] Applied {len(updates)} English (India) spelling remediations.")
    else:
        logger.info(f"[{table}] Scanned {scanned} records; {updated} require remediation.")

    return scanned, updated


def main():
    parser = argparse.ArgumentParser(description="Remediate reports database to English (India) spellings.")
    parser.add_argument("--apply", action="store_true", help="Apply updates to database.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without modifying database.")
    parser.add_argument("--sqlite-path", type=str, default=None, help="Optional explicit SQLite DB path (bypasses SUPABASE_DB_URL).")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        print("Please specify either --dry-run or --apply.")
        sys.exit(1)

    conn, is_pg, db_label = _open_target_connection(args.sqlite_path)

    try:
        logger.info(f"Starting English (India) database audit on {db_label} (apply={args.apply})...")

        # 1. reports
        s1, u1 = remediate_table(conn, is_pg, "reports", "ticker", "report_text", apply_changes=args.apply)

        # 2. report_revisions
        s2, u2 = remediate_table(conn, is_pg, "report_revisions", "id", "report_text", apply_changes=args.apply)

        # 3. fund_forensic_dossiers
        s3, u3 = remediate_table(conn, is_pg, "fund_forensic_dossiers", "scheme_code", "dossier_text", apply_changes=args.apply)

        # 4. discovery_reel (ria_thesis)
        s4, u4 = remediate_table(conn, is_pg, "discovery_reel", "id", "ria_thesis", apply_changes=args.apply)

        total_scanned = s1 + s2 + s3 + s4
        total_updated = u1 + u2 + u3 + u4

        logger.info(
            f"Remediation summary: {total_updated}/{total_scanned} records updated "
            f"(reports: {u1}/{s1}, revisions: {u2}/{s2}, funds: {u3}/{s3}, discovery: {u4}/{s4})."
        )

        if args.apply:
            try:
                from core.db.reports import get_archived_reports, get_report_by_ticker, get_report_revisions, get_all_equities_directory_sync
                get_archived_reports.cache_clear()
                get_report_by_ticker.cache_clear()
                get_report_revisions.cache_clear()
                get_all_equities_directory_sync.cache_clear()
                logger.info("Cleared in-memory LRU report caches.")
            except Exception as c_err:
                logger.debug("Cache clear notice: %s", c_err)

    finally:
        conn.close()

if __name__ == "__main__":
    main()
