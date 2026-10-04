# core/msme/ingest_ministry.py
"""
Monthly ingestion script for the Ministry of MSME CSV/Excel export.
* Downloads the latest file (cached per day).
* Parses with pandas, normalises columns, and upserts into `msme_firms`.
* Logs progress – any failure is logged but does not crash the app (per compliance).
"""

import logging
import pathlib
from datetime import datetime
from typing import List, Dict

import pandas as pd
import requests

from core.db.connection import get_db_connection
from core.msme.utils import normalise_sector

logger = logging.getLogger(__name__)

DATA_DIR = pathlib.Path(__file__).parents[2] / "data" / "msme" / "monthly"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MINISTRY_URL = "https://msme.gov.in/sites/default/files/MSME_Firms_List.xlsx"  # Example URL – verify actual location


def download_latest() -> pathlib.Path:
    """Download the most recent Ministry file, caching it for the current UTC day."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    target = DATA_DIR / f"msme_{today}.xlsx"
    if target.exists():
        logger.info("Using cached Ministry file %s", target.name)
        return target
    logger.info("Downloading Ministry of MSME dataset...")
    resp = requests.get(MINISTRY_URL, timeout=30)
    resp.raise_for_status()
    with open(target, "wb") as f:
        f.write(resp.content)
    logger.info("Saved Ministry file to %s", target)
    return target


def parse_dataframe(df: pd.DataFrame) -> List[Dict]:
    """Map raw dataframe columns to our internal schema.
    The Ministry CSV/Excel column names may vary; we use a tolerant mapping.
    """
    col_map = {c.strip().upper(): c for c in df.columns}
    rows = []
    for _, row in df.iterrows():
        rows.append({
            "uin": row.get(col_map.get("UIN")),
            "name": row.get(col_map.get("NAME OF THE MSME")),
            "sector_code": row.get(col_map.get("SECTOR CODE")),
            "sector_name": normalise_sector(row.get(col_map.get("SECTOR NAME")) or ""),
            "city": row.get(col_map.get("CITY")),
            "state": row.get(col_map.get("STATE")),
            "annual_turnover": row.get(col_map.get("ANNUAL TURNOVER (INR CRORES)")),
            "employee_count": row.get(col_map.get("EMPLOYEE COUNT")),
            "registration_date": row.get(col_map.get("REGISTRATION DATE")),
            "source": "ministry",
        })
    return rows


def upsert_firms(rows: List[Dict]) -> None:
    """Upsert each record into the `msme_firms` table.
    Uses SQLite/PostgreSQL compatible ``INSERT … ON CONFLICT`` syntax.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        INSERT INTO msme_firms (
            uin, name, sector_code, sector_name, city, state,
            annual_turnover, employee_count, registration_date, source, last_updated
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now')
        )
        ON CONFLICT(uin) DO UPDATE SET
            name=excluded.name,
            sector_code=excluded.sector_code,
            sector_name=excluded.sector_name,
            city=excluded.city,
            state=excluded.state,
            annual_turnover=excluded.annual_turnover,
            employee_count=excluded.employee_count,
            registration_date=excluded.registration_date,
            source=excluded.source,
            last_updated=datetime('now')
    """
    for rec in rows:
        cur.execute(
            sql,
            (
                rec.get("uin"),
                rec.get("name"),
                rec.get("sector_code"),
                rec.get("sector_name"),
                rec.get("city"),
                rec.get("state"),
                rec.get("annual_turnover"),
                rec.get("employee_count"),
                rec.get("registration_date"),
                rec.get("source"),
            ),
        )
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Upserted %d MSME records", len(rows))


def run_monthly_job() -> None:
    """Entry point for the scheduled job – intended for APScheduler."""
    try:
        path = download_latest()
        df = pd.read_excel(path)
        rows = parse_dataframe(df)
        upsert_firms(rows)
        logger.info("Monthly MSME ingestion completed successfully.")
    except Exception as exc:
        logger.error("MSME ingestion failed: %s", exc, exc_info=True)
        raise
