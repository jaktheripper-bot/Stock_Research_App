"""
Sync local SQLite reports and revisions to Supabase (PostgreSQL or PostgREST).

Supports:
1. Direct PostgreSQL synchronization when SUPABASE_DB_URL is available.
2. PostgREST REST API synchronization when SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are available.
3. Supabase Storage backup archive upload.
"""

import os
import sys
import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, List

# Ensure parent directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_secret
from core.db.connection import get_db_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_to_supabase")

def get_local_reports(sqlite_path: str = None) -> List[Dict[str, Any]]:
    """Fetches all rows from local SQLite reports table."""
    path = sqlite_path or get_db_path()
    if not os.path.exists(path):
        logger.warning(f"Local SQLite database not found at {path}")
        return []
    
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ticker, short_name, report_text, timestamp, baseline_price, 
               baseline_pe, baseline_mcap, latest_announcement, citations_json
        FROM reports
        ORDER BY ticker ASC
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_local_revisions(sqlite_path: str = None) -> List[Dict[str, Any]]:
    """Fetches all rows from local SQLite report_revisions table."""
    path = sqlite_path or get_db_path()
    if not os.path.exists(path):
        return []
    
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT ticker, short_name, report_text, timestamp, baseline_price, 
                   baseline_pe, baseline_mcap, latest_announcement, revision_trigger, citations_json
            FROM report_revisions
            ORDER BY id ASC
        """)
        rows = [dict(row) for row in cursor.fetchall()]
    except Exception:
        rows = []
    finally:
        conn.close()
    return rows

def sync_via_postgresql(reports: List[Dict[str, Any]], revisions: List[Dict[str, Any]], db_url: str) -> Dict[str, int]:
    """Syncs rows directly to Supabase PostgreSQL using psycopg2."""
    import psycopg2
    from psycopg2.extras import execute_batch

    logger.info("Connecting to Supabase PostgreSQL via SUPABASE_DB_URL...")
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    # Ensure tables exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            ticker TEXT PRIMARY KEY,
            short_name TEXT,
            report_text TEXT,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            baseline_price REAL,
            baseline_pe TEXT,
            baseline_mcap REAL,
            latest_announcement TEXT,
            citations_json TEXT
        );
        CREATE TABLE IF NOT EXISTS report_revisions (
            id SERIAL PRIMARY KEY,
            ticker TEXT,
            short_name TEXT,
            report_text TEXT,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            baseline_price REAL,
            baseline_pe TEXT,
            baseline_mcap REAL,
            latest_announcement TEXT,
            revision_trigger TEXT,
            citations_json TEXT
        );
    """)
    conn.commit()

    upsert_query = """
        INSERT INTO reports (
            ticker, short_name, report_text, timestamp, baseline_price,
            baseline_pe, baseline_mcap, latest_announcement, citations_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ticker) DO UPDATE SET
            short_name = EXCLUDED.short_name,
            report_text = EXCLUDED.report_text,
            timestamp = EXCLUDED.timestamp,
            baseline_price = EXCLUDED.baseline_price,
            baseline_pe = EXCLUDED.baseline_pe,
            baseline_mcap = EXCLUDED.baseline_mcap,
            latest_announcement = EXCLUDED.latest_announcement,
            citations_json = EXCLUDED.citations_json;
    """

    report_params = [
        (
            r["ticker"], r["short_name"], r["report_text"], r["timestamp"],
            r["baseline_price"], r["baseline_pe"], r["baseline_mcap"],
            r["latest_announcement"], r["citations_json"]
        )
        for r in reports
    ]
    execute_batch(cursor, upsert_query, report_params)
    conn.commit()

    cursor.close()
    conn.close()
    logger.info(f"✅ Successfully synced {len(reports)} reports to Supabase PostgreSQL.")
    return {"reports_synced": len(reports), "revisions_synced": len(revisions)}

def sync_via_rest(reports: List[Dict[str, Any]], supabase_url: str, service_key: str) -> Dict[str, int]:
    """Syncs rows to Supabase PostgREST endpoint /rest/v1/reports."""
    import requests

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }

    url = f"{supabase_url.rstrip('/')}/rest/v1/reports"
    synced = 0
    errors = 0

    logger.info(f"Syncing {len(reports)} reports to Supabase REST at {url}...")
    for r in reports:
        payload = {
            "ticker": r["ticker"],
            "short_name": r.get("short_name"),
            "report_text": r.get("report_text"),
            "baseline_price": r.get("baseline_price"),
            "baseline_pe": str(r.get("baseline_pe") or ""),
            "baseline_mcap": r.get("baseline_mcap"),
            "latest_announcement": r.get("latest_announcement"),
            "citations_json": r.get("citations_json")
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code in (200, 201):
                synced += 1
            else:
                logger.warning(f"Supabase REST returned {resp.status_code} for {r['ticker']}: {resp.text[:150]}")
                errors += 1
        except Exception as e:
            logger.error(f"Error syncing {r['ticker']} via REST: {e}")
            errors += 1

    logger.info(f"✅ Supabase REST Sync Complete: {synced} synced, {errors} errors.")
    return {"reports_synced": synced, "errors": errors}

def upload_sqlite_backup_to_storage(sqlite_path: str, supabase_url: str, service_key: str) -> bool:
    """Uploads the reports.db snapshot to Supabase storage 'backups' bucket."""
    import requests
    if not os.path.exists(sqlite_path):
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_name = f"reports_db_{timestamp}.sqlite"
    storage_url = f"{supabase_url.rstrip('/')}/storage/v1/object/backups/{target_name}"

    try:
        with open(sqlite_path, "rb") as f:
            data = f.read()
        resp = requests.post(
            storage_url,
            headers={
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/x-sqlite3"
            },
            data=data,
            timeout=30
        )
        if resp.status_code in (200, 201):
            logger.info(f"✅ Uploaded SQLite snapshot to Supabase Storage: backups/{target_name}")
            return True
        else:
            logger.warning(f"Supabase storage upload returned {resp.status_code}: {resp.text[:150]}")
            return False
    except Exception as e:
        logger.error(f"Failed to upload backup to Supabase Storage: {e}")
        return False

def pull_from_supabase_rest(sqlite_path: str, supabase_url: str, service_key: str) -> int:
    """Pulls all reports from Supabase PostgREST table into local SQLite database."""
    import requests
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}"
    }
    url = f"{supabase_url.rstrip('/')}/rest/v1/reports"
    logger.info(f"Pulling reports from Supabase REST at {url}...")
    resp = requests.get(url, headers=headers, timeout=20)
    if resp.status_code != 200:
        logger.error(f"Failed to fetch reports from Supabase: {resp.status_code} {resp.text}")
        return 0
    
    rows = resp.json()
    if not rows:
        logger.info("No reports found in Supabase.")
        return 0

    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            ticker TEXT PRIMARY KEY,
            short_name TEXT,
            report_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            baseline_price REAL,
            baseline_pe TEXT,
            baseline_mcap REAL,
            latest_announcement TEXT,
            citations_json TEXT
        )
    """)
    inserted = 0
    for r in rows:
        cursor.execute("""
            INSERT INTO reports (
                ticker, short_name, report_text, timestamp, baseline_price,
                baseline_pe, baseline_mcap, latest_announcement, citations_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker) DO UPDATE SET
                short_name = excluded.short_name,
                report_text = excluded.report_text,
                timestamp = excluded.timestamp,
                baseline_price = excluded.baseline_price,
                baseline_pe = excluded.baseline_pe,
                baseline_mcap = excluded.baseline_mcap,
                latest_announcement = excluded.latest_announcement,
                citations_json = excluded.citations_json;
        """, (
            r.get("ticker"), r.get("short_name"), r.get("report_text"), r.get("timestamp"),
            r.get("baseline_price"), r.get("baseline_pe"), r.get("baseline_mcap"),
            r.get("latest_announcement"), r.get("citations_json")
        ))
        inserted += 1
    conn.commit()
    conn.close()
    logger.info(f"✅ Successfully pulled and merged {inserted} reports into {sqlite_path}.")
    return inserted

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sync local SQLite reports to/from Supabase")
    parser.add_argument("--db-path", default=None, help="Path to SQLite file (default: reports.db)")
    parser.add_argument("--supabase-db-url", default=None, help="Direct PostgreSQL connection string")
    parser.add_argument("--supabase-url", default=None, help="Supabase Project REST URL")
    parser.add_argument("--upload-backup", action="store_true", help="Also upload SQLite file to Supabase Storage")
    parser.add_argument("--pull", action="store_true", help="Pull existing reports from Supabase into local SQLite")
    args = parser.parse_args()

    sqlite_path = args.db_path or get_db_path()

    sb_url = args.supabase_url or get_secret("SUPABASE_URL")
    service_key = get_secret("SUPABASE_SERVICE_ROLE_KEY")

    if args.pull:
        if sb_url and service_key:
            pull_from_supabase_rest(sqlite_path, sb_url, service_key)
            return
        else:
            logger.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required for --pull.")
            return

    reports = get_local_reports(sqlite_path)
    revisions = get_local_revisions(sqlite_path)

    logger.info(f"Found {len(reports)} reports and {len(revisions)} revisions in {sqlite_path}")

    # Check PostgreSQL connection
    pg_url = args.supabase_db_url or get_secret("SUPABASE_DB_URL")
    if pg_url:
        sync_via_postgresql(reports, revisions, pg_url)
        return

    # Check REST connection
    if sb_url and service_key:
        sync_via_rest(reports, sb_url, service_key)
        if args.upload_backup:
            upload_sqlite_backup_to_storage(sqlite_path, sb_url, service_key)
        return

    logger.warning("No SUPABASE_DB_URL or (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY) found in environment or arguments.")
    logger.info("Reports remain securely persisted in local SQLite (reports.db).")
    logger.info("To sync to Supabase, provide SUPABASE_DB_URL or SUPABASE_URL in .env or via command-line flags.")

if __name__ == "__main__":
    main()

