#!/usr/bin/env python3
"""Purges corrupt typo ticker rows (e.g. 'TOMATO') and orphaned discovery_reel cards."""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ENABLE_BACKGROUND_SCHEDULERS"] = "0"

from core.db.connection import get_db_connection, get_db_path, init_db, is_postgres_connection

CORRUPT_TICKERS = ("TOMATO",)


def _row_scalar(row) -> int:
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(next(iter(row.values())))
    return int(row[0])


def _purge_on_connection(conn, ph: str, label: str, apply: bool) -> None:
    cur = conn.cursor()
    mode_tag = "APPLY" if apply else "DRY-RUN"
    try:
        for sym in CORRUPT_TICKERS:
            for tbl, col in (
                ("reports", "ticker"),
                ("report_revisions", "ticker"),
                ("cached_fundamentals", "ticker"),
                ("discovery_reel", "ticker"),
            ):
                cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {col} = {ph}", (sym,))
                cnt = _row_scalar(cur.fetchone())
                print(f"[{mode_tag}][{label}] {tbl}.{col}='{sym}': {cnt} row(s)")
                if apply and cnt > 0:
                    cur.execute(f"DELETE FROM {tbl} WHERE {col} = {ph}", (sym,))

        cur.execute(
            """
            SELECT d.ticker, d.edition_date FROM discovery_reel d
            LEFT JOIN reports r ON d.ticker = r.ticker
            WHERE r.report_text IS NULL OR TRIM(r.report_text) = ''
            """
        )
        stale_rows = cur.fetchall()
        stale_reel = len(stale_rows)
        stale_tickers = [r["ticker"] if isinstance(r, dict) else r[0] for r in stale_rows]
        print(
            f"[{mode_tag}][{label}] discovery_reel cards without synthesized report_text: {stale_reel}"
            + (f" ({', '.join(stale_tickers)})" if stale_tickers else "")
        )
        if apply and stale_reel > 0:
            cur.execute(
                """
                DELETE FROM discovery_reel
                WHERE ticker NOT IN (
                    SELECT ticker FROM reports WHERE report_text IS NOT NULL AND TRIM(report_text) != ''
                )
                """
            )
        if apply:
            conn.commit()
    finally:
        cur.close()


def run(apply: bool = False) -> None:
    init_db()
    conn = get_db_connection()
    is_pg = is_postgres_connection(conn)
    ph = "%s" if is_pg else "?"
    try:
        _purge_on_connection(conn, ph, "PRIMARY_DB", apply)
    finally:
        conn.close()

    # Keep local SQLite mirror aligned when primary DB is PostgreSQL so drift sync never resurrects purged stubs
    if is_pg:
        sqlite_path = Path(get_db_path())
        if sqlite_path.exists():
            sconn = sqlite3.connect(str(sqlite_path))
            try:
                _purge_on_connection(sconn, "?", "LOCAL_SQLITE", apply)
            finally:
                sconn.close()

    if apply:
        print("Committed stub cleanup successfully.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Purge corrupt ticker stubs and orphaned discovery_reel cards.")
    ap.add_argument("--dry-run", action="store_true", help="Inspect matching rows without mutating DB (default)")
    ap.add_argument("--apply", action="store_true", help="Execute deletions against active DB")
    args = ap.parse_args()
    run(apply=bool(args.apply and not args.dry_run))

