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

def _coerce_pg_date(val: Any):
    """Coerces SQLite date/timestamp/sentinel values into a Python datetime.date or None for PostgreSQL DATE columns."""
    from datetime import date, datetime
    from core.db.connection import IST
    from core.presentation.formatters import _coerce_datetime

    if val is None:
        return None
    if isinstance(val, datetime):
        return (val.astimezone(IST) if val.tzinfo else val).date()
    if isinstance(val, date):
        return val
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(float(val), tz=IST).date()
    if isinstance(val, str):
        s = val.strip()
        if not s or s.lower() in {
            "none", "null", "n/a", "na", "pending", "pending monthly disclosure", "-", "unknown"
        }:
            return None
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            coerced = _coerce_datetime(s)
            return coerced.date() if coerced is not None else None
    return None


def sync_via_postgresql(reports: List[Dict[str, Any]], revisions: List[Dict[str, Any]], db_url: str, sqlite_path: str = None) -> Dict[str, int]:
    """Syncs all 17 multi-asset tables directly to Supabase PostgreSQL using psycopg2."""
    import psycopg2
    from psycopg2.extras import execute_batch
    from core.db.connection import IST, _normalize_pg_dsn, close_all_pg_pools, init_db
    from core.presentation.formatters import _coerce_datetime

    logger.info("Connecting to Supabase PostgreSQL via SUPABASE_DB_URL...")
    try:
        conn = psycopg2.connect(_normalize_pg_dsn(db_url), connect_timeout=10)
    except psycopg2.OperationalError as op_err:
        if "could not translate host name" in str(op_err) and "db." in db_url and ".supabase.co" in db_url:
            logger.warning("Supabase direct host is IPv6-only or unreachable from this network. Attempting IPv4 pooler fallback...")
            import re
            m = re.search(r"postgresql://([^:]+):([^@]+)@db\.([^\.]+)\.supabase\.co:(\d+)/(.+)", db_url)
            if m:
                user, password, project_ref, port, dbname = m.groups()
                dbname_clean = dbname.split("?")[0]
                for region in ["ap-southeast-1", "ap-south-1", "us-east-1", "eu-central-1"]:
                    pooler_url = _normalize_pg_dsn(
                        f"postgresql://{user}.{project_ref}:{password}@aws-0-{region}.pooler.supabase.com:5432/{dbname_clean}"
                    )
                    try:
                        conn = psycopg2.connect(pooler_url, connect_timeout=5)
                        logger.info(f"Connected to Supabase PostgreSQL via IPv4 pooler ({region})!")
                        break
                    except Exception:
                        continue
                else:
                    raise op_err
            else:
                raise op_err
        else:
            raise op_err

    conn.autocommit = False
    cursor = conn.cursor()
    cursor.execute("SET TIME ZONE 'Asia/Kolkata';")
    conn.commit()

    # 1. Initialize complete schema migrations on PostgreSQL and release pool sockets immediately
    logger.info("Ensuring PostgreSQL schema migrations are initialized...")
    try:
        init_db(force=False)
    except Exception as mig_err:
        logger.debug("Schema migration notice: %s", mig_err)
    finally:
        close_all_pg_pools()

    path = sqlite_path or get_db_path()
    sqlite_conn = sqlite3.connect(path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    # Tables to sync: (table_name, conflict_target, update_on_conflict, ts_col)
    sync_targets = [
        ("reports", "ticker", True, "timestamp"),
        ("report_revisions", "__natural_revision__", False, "timestamp"),
        ("cached_fundamentals", "ticker", True, "updated_at"),
        ("discovery_reel", "__natural_discovery__", True, "created_at"),
        ("mutual_fund_schemes", "scheme_code", True, "last_updated"),
        ("mutual_fund_holdings", "scheme_code, holding_type, identifier", True, "created_at"),
        ("fund_forensic_dossiers", "scheme_code", True, "last_audited_at"),
        ("corporate_debt_securities", "isin", True, "last_updated"),
        ("sovereign_benchmarks", "tenor_label", True, "updated_at"),
        ("sovereign_curve_history", "snapshot_key, tenor_label", True, None),
        ("sovereign_sdl_spreads", "state_name", True, "updated_at"),
        ("sovereign_macro_rates", "metric_key", True, "updated_at"),
        ("reits_and_invits", "symbol", True, "updated_at"),
        ("sgb_tranches", "symbol", True, "updated_at"),
        ("alternative_yield_products", "product_id", True, "updated_at"),
        ("etf_matrix", "symbol", True, "updated_at"),
        ("msme_firms", "uin", True, "last_updated"),
    ]

    def _transform_cell(val: Any, dt: str) -> Any:
        if val is None:
            return None
        if dt == "boolean":
            return bool(val) if not isinstance(val, str) else (val.strip().lower() in ("true", "t", "1", "yes"))
        if "timestamp" in dt:
            coerced = _coerce_datetime(val)
            return coerced if coerced is not None else None
        if dt == "date":
            return _coerce_pg_date(val)
        return val

    sync_summary = {}

    for table_name, conflict_col, do_update, ts_col in sync_targets:
        try:
            sqlite_cur.execute(f"SELECT * FROM {table_name}")
            rows = sqlite_cur.fetchall()
            if not rows:
                continue

            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = %s AND table_name = %s",
                ("public", table_name),
            )
            pg_col_types = dict(cursor.fetchall())
            if not pg_col_types:
                logger.warning(f"Table {table_name} does not exist in target PostgreSQL schema.")
                continue

            raw_cols = [col[0] for col in sqlite_cur.description]
            cols = [c for c in raw_cols if not (c == "id" and conflict_col != "id" and "id" in pg_col_types) and c in pg_col_types]
            cols_joined = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))

            if conflict_col == "__natural_discovery__":
                cursor.execute("SELECT edition_date, ticker, created_at FROM discovery_reel")
                pg_by_ed: Dict[str, List[Any]] = {}
                for ped, pticker, pcreated in cursor.fetchall():
                    pg_by_ed.setdefault(str(ped)[:10], []).append(
                        (str(pticker or "").strip().upper(), _coerce_datetime(pcreated))
                    )

                sq_by_ed: Dict[str, List[Any]] = {}
                for row in rows:
                    ed_date = _coerce_pg_date(row["edition_date"])
                    if ed_date:
                        sq_by_ed.setdefault(ed_date.isoformat(), []).append(row)

                batch_count = 0
                for ed_iso, sq_cohort in sq_by_ed.items():
                    pg_cohort = pg_by_ed.get(ed_iso)
                    sq_tickers = {str(r["ticker"] or "").strip().upper() for r in sq_cohort}
                    sq_max_dt = max(
                        (_coerce_datetime(r["created_at"]) for r in sq_cohort if _coerce_datetime(r["created_at"])),
                        default=None,
                    )
                    if pg_cohort is None:
                        to_ins = [
                            tuple(_transform_cell(r[c], pg_col_types.get(c, "")) for c in cols)
                            for r in sq_cohort
                        ]
                        execute_batch(
                            cursor,
                            f"INSERT INTO discovery_reel ({cols_joined}) VALUES ({placeholders})",
                            to_ins,
                            page_size=500,
                        )
                        batch_count += len(to_ins)
                    else:
                        pg_tickers = {x[0] for x in pg_cohort}
                        pg_max_dt = max((x[1] for x in pg_cohort if x[1] is not None), default=None)
                        if sq_tickers != pg_tickers and sq_max_dt and (pg_max_dt is None or (sq_max_dt - pg_max_dt).total_seconds() > 1.0):
                            cursor.execute("DELETE FROM discovery_reel WHERE edition_date = %s", (_coerce_pg_date(ed_iso),))
                            to_ins = [
                                tuple(_transform_cell(r[c], pg_col_types.get(c, "")) for c in cols)
                                for r in sq_cohort
                            ]
                            execute_batch(
                                cursor,
                                f"INSERT INTO discovery_reel ({cols_joined}) VALUES ({placeholders})",
                                to_ins,
                                page_size=500,
                            )
                            batch_count += len(to_ins)
            elif conflict_col == "__natural_revision__":
                cursor.execute("SELECT ticker, timestamp FROM report_revisions")
                pg_rev_keys = set()
                for pticker, pts in cursor.fetchall():
                    pdt = _coerce_datetime(pts)
                    pg_rev_keys.add((str(pticker or "").strip().upper(), int(pdt.timestamp()) if pdt else str(pts)))

                to_insert = []
                for row in rows:
                    tkr = str(row["ticker"] or "").strip().upper()
                    sdt = _coerce_datetime(row["timestamp"])
                    rkey = (tkr, int(sdt.timestamp()) if sdt else str(row["timestamp"]))
                    if rkey not in pg_rev_keys:
                        to_insert.append(tuple(_transform_cell(row[c], pg_col_types.get(c, "")) for c in cols))
                        pg_rev_keys.add(rkey)

                if to_insert:
                    execute_batch(
                        cursor,
                        f"INSERT INTO report_revisions ({cols_joined}) VALUES ({placeholders})",
                        to_insert,
                        page_size=500,
                    )
                batch_count = len(to_insert)
            else:
                if do_update and conflict_col:
                    conflict_targets = [c.strip() for c in conflict_col.split(",")]
                    conflict_target_sql = ", ".join(conflict_targets)
                    preserve_non_empty_cols = {"report_text", "citations_json", "dossier_text"}
                    update_parts = []
                    for c in cols:
                        if c in conflict_targets:
                            continue
                        if c in preserve_non_empty_cols:
                            update_parts.append(
                                f"{c} = CASE WHEN EXCLUDED.{c} IS NOT NULL AND TRIM(EXCLUDED.{c}) <> '' "
                                f"THEN EXCLUDED.{c} ELSE {table_name}.{c} END"
                            )
                        else:
                            update_parts.append(f"{c} = EXCLUDED.{c}")
                    update_assignments = ", ".join(update_parts)
                    where_guard = ""
                    if ts_col and ts_col in cols:
                        extra_substance_guard = ""
                        if table_name == "reports":
                            extra_substance_guard = f" OR {table_name}.report_text IS NULL OR LENGTH(TRIM({table_name}.report_text)) < 500"
                        elif table_name == "fund_forensic_dossiers":
                            extra_substance_guard = f" OR {table_name}.dossier_text IS NULL OR TRIM({table_name}.dossier_text) = ''"
                        where_guard = (
                            f" WHERE {table_name}.{ts_col} IS NULL "
                            f"OR EXCLUDED.{ts_col} IS NULL "
                            f"OR EXCLUDED.{ts_col} >= {table_name}.{ts_col}"
                            f"{extra_substance_guard}"
                        )
                    conflict_clause = f"ON CONFLICT ({conflict_target_sql}) DO UPDATE SET {update_assignments}{where_guard}"
                elif conflict_col:
                    conflict_targets = [c.strip() for c in conflict_col.split(",")]
                    conflict_target_sql = ", ".join(conflict_targets)
                    conflict_clause = f"ON CONFLICT ({conflict_target_sql}) DO NOTHING"
                else:
                    conflict_clause = ""

                insert_query = f"INSERT INTO {table_name} ({cols_joined}) VALUES ({placeholders}) {conflict_clause}"
                batch_data = [
                    tuple(_transform_cell(row[c], pg_col_types.get(c, "")) for c in cols)
                    for row in rows
                ]
                execute_batch(cursor, insert_query, batch_data, page_size=500)
                batch_count = len(batch_data)

            # Sync sequence if table has a serial id column
            if "id" in pg_col_types:
                try:
                    cursor.execute(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE((SELECT MAX(id) FROM {table_name}), 1), true);")
                except Exception as seq_err:
                    logger.debug("Sequence reset notice for %s: %s", table_name, seq_err)

            conn.commit()
            sync_summary[table_name] = batch_count
            logger.info(f"✅ Synced {batch_count:4d} records to Supabase table: {table_name}")
        except Exception as tbl_err:
            conn.rollback()
            logger.warning(f"Notice syncing table {table_name}: {tbl_err}")
            sync_summary[table_name] = 0

    cursor.close()
    conn.close()
    sqlite_cur.close()
    sqlite_conn.close()

    logger.info(f"🎉 Multi-Asset Supabase Sync Complete across {len(sync_summary)} tables!")
    return sync_summary

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
    
    from core.db.connection import IST
    timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
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
    pg_url = (
        args.supabase_db_url
        if args.supabase_db_url is not None
        else (os.environ.get("SUPABASE_DB_URL") if "SUPABASE_DB_URL" in os.environ else get_secret("SUPABASE_DB_URL"))
    )

    if args.pull:
        if pg_url:
            from scripts.sync_from_supabase import sync_via_postgresql_pull
            sync_via_postgresql_pull(sqlite_path=sqlite_path, db_url=pg_url)
            return
        if sb_url and service_key:
            pull_from_supabase_rest(sqlite_path, sb_url, service_key)
            return
        logger.error("SUPABASE_DB_URL or (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY) required for --pull.")
        return

    reports = get_local_reports(sqlite_path)
    revisions = get_local_revisions(sqlite_path)

    logger.info(f"Found {len(reports)} reports and {len(revisions)} revisions in {sqlite_path}")

    # Check PostgreSQL connection
    if pg_url:
        sync_via_postgresql(reports, revisions, pg_url, sqlite_path=sqlite_path)
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

