"""Morning Discovery Reel repository: under-the-radar equities persistence and retrieval."""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder, IST
from core.db.reports import _format_timestamp
from normalizer import clean_ticker

logger = logging.getLogger("equity_research.core.db.discovery")


def save_discovery_reel(items: List[Dict[str, Any]], edition_date: Optional[str] = None) -> int:
    """
    Persists a cohort of 10-15 under-the-radar equity highlight items for a given edition date.
    Deactivates previous active items for the same edition to avoid duplicate entries.
    Returns the number of saved records.
    """
    if not items:
        return 0

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    is_pg = bool(get_supabase_url())

    if not edition_date:
        edition_date = datetime.now(IST).strftime("%Y-%m-%d")

    saved_count = 0
    try:
        # Mark previous items for this edition date as inactive
        if is_pg:
            cursor.execute(
                f"UPDATE discovery_reel SET is_active = FALSE WHERE edition_date = {placeholder};",
                (edition_date,)
            )
        else:
            cursor.execute(
                f"UPDATE discovery_reel SET is_active = 0 WHERE edition_date = {placeholder};",
                (edition_date,)
            )

        insert_sql = f"""
            INSERT INTO discovery_reel (
                edition_date, ticker, company_name, sector, market_cap_tier,
                current_price, pe_ratio, roce_pct, debt_to_equity, sales_growth_3y,
                ria_thesis, catalyst_headline, key_metrics_json, is_active
            )
            VALUES (
                {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                {placeholder}, {placeholder}, {placeholder}, {placeholder}
            )
        """

        for item in items:
            ticker = clean_ticker(item.get("ticker", ""))
            if not ticker:
                continue

            company_name = item.get("company_name") or ticker
            sector = item.get("sector") or "General Contender"
            mcap_tier = item.get("market_cap_tier") or "Small-Cap"
            price = item.get("current_price") or 0.0
            pe = str(item.get("pe_ratio") or "N/A")
            roce = item.get("roce_pct") or 0.0
            de = item.get("debt_to_equity") or 0.0
            sales_g = item.get("sales_growth_3y") or 0.0
            ria_thesis = item.get("ria_thesis") or "High capital compounding profile with negligible institutional coverage."
            catalyst = item.get("catalyst_headline") or "BSE Corporate Announcements"
            metrics_json = json.dumps(item.get("key_metrics") or {})
            is_active_val = True if is_pg else 1

            cursor.execute(
                insert_sql,
                (
                    edition_date, ticker, company_name, sector, mcap_tier,
                    price, pe, roce, de, sales_g,
                    ria_thesis, catalyst, metrics_json, is_active_val
                )
            )
            saved_count += 1

        conn.commit()
        logger.info(f"Successfully saved {saved_count} discovery reel items for edition {edition_date}.")
        return saved_count
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving discovery reel: {e}")
        return 0
    finally:
        cursor.close()
        conn.close()


def get_active_discovery_reel(edition_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves the active morning discovery reel for a given edition date.
    If edition_date is None or has no items, falls back to the most recent available active edition.
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    is_pg = bool(get_supabase_url())

    try:
        active_clause = "is_active = TRUE" if is_pg else "is_active = 1"

        if edition_date:
            query = f"""
                SELECT id, edition_date, ticker, company_name, sector, market_cap_tier,
                       current_price, pe_ratio, roce_pct, debt_to_equity, sales_growth_3y,
                       ria_thesis, catalyst_headline, key_metrics_json, created_at
                FROM discovery_reel
                WHERE edition_date = {placeholder} AND {active_clause}
                ORDER BY id ASC;
            """
            cursor.execute(query, (edition_date,))
            rows = cursor.fetchall()
        else:
            rows = []

        # Fallback to latest available edition if requested edition yielded no rows
        if not rows:
            query = f"""
                SELECT id, edition_date, ticker, company_name, sector, market_cap_tier,
                       current_price, pe_ratio, roce_pct, debt_to_equity, sales_growth_3y,
                       ria_thesis, catalyst_headline, key_metrics_json, created_at
                FROM discovery_reel
                WHERE {active_clause}
                  AND edition_date = (
                      SELECT MAX(edition_date) FROM discovery_reel WHERE {active_clause}
                  )
                ORDER BY id ASC;
            """
            cursor.execute(query)
            rows = cursor.fetchall()

        results = []
        for r in rows:
            metrics_dict = {}
            if r[13]:
                try:
                    metrics_dict = json.loads(r[13])
                except Exception:
                    metrics_dict = {}

            results.append({
                "id": r[0],
                "edition_date": str(r[1]),
                "ticker": r[2],
                "company_name": r[3],
                "sector": r[4],
                "market_cap_tier": r[5],
                "current_price": float(r[6]) if r[6] is not None else 0.0,
                "pe_ratio": str(r[7] or "N/A"),
                "roce_pct": float(r[8]) if r[8] is not None else 0.0,
                "debt_to_equity": float(r[9]) if r[9] is not None else 0.0,
                "sales_growth_3y": float(r[10]) if r[10] is not None else 0.0,
                "ria_thesis": r[11],
                "catalyst_headline": r[12] or "",
                "key_metrics": metrics_dict,
                "formatted_date": _format_timestamp(r[14]),
            })

        return results
    except Exception as e:
        logger.error(f"Error fetching active discovery reel: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_available_discovery_editions() -> List[str]:
    """Retrieves all distinct available discovery edition dates, sorted descending."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    is_pg = bool(get_supabase_url())

    try:
        active_clause = "is_active = TRUE" if is_pg else "is_active = 1"
        cursor.execute(f"SELECT DISTINCT edition_date FROM discovery_reel WHERE {active_clause} ORDER BY edition_date DESC LIMIT 30;")
        rows = cursor.fetchall()
        return [str(r[0]) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching available discovery editions: {e}")
        return []
    finally:
        cursor.close()
        conn.close()
