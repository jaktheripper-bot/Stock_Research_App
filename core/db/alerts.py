"""Alert events, unread notifications, and user dismissals repository."""

import logging
import streamlit as st
from normalizer import clean_ticker
from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder
from core.db.reports import _format_timestamp

logger = logging.getLogger("equity_research.core.db.alerts")

def record_alert_event(ticker: str, category: str, severity: str, title: str, details: str = "", source: str = "BSE Surveillance") -> int:
    """Records an immutable alert event for a stock."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    new_id = None
    try:
        query = f'''
            INSERT INTO alert_events (ticker, category, severity, title, details, source)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        '''
        if supabase_url:
            query += " RETURNING id"
            cursor.execute(query, (clean, category, severity, title, details, source))
            row = cursor.fetchone()
            if row:
                new_id = row[0]
        else:
            cursor.execute(query, (clean, category, severity, title, details, source))
            new_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        logger.error(f"Error in record_alert_event: {e}")
    finally:
        cursor.close()
        conn.close()
    return new_id

def get_alert_events(ticker: str = None, category: str = None, unread_only: bool = False, limit: int = 50) -> list:
    """Retrieves recorded alert events with optional filters."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    alerts = []
    try:
        conditions = []
        params = []
        if ticker:
            clean = clean_ticker(ticker)
            conditions.append(f"ticker = {placeholder}")
            params.append(clean)
        if category and category.lower() != "all":
            conditions.append(f"category = {placeholder}")
            params.append(category.lower())
        if unread_only:
            conditions.append("is_read = FALSE" if supabase_url else "is_read = 0")
        
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        query = f'''
            SELECT id, ticker, category, severity, title, details, timestamp, is_read, source
            FROM alert_events
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT {placeholder}
        '''
        params.append(int(limit))
        cursor.execute(query, tuple(params))
        for row in cursor.fetchall():
            alerts.append({
                "id": row[0],
                "ticker": row[1],
                "category": row[2],
                "severity": row[3] or "medium",
                "title": row[4],
                "details": row[5] or "",
                "timestamp": _format_timestamp(row[6]),
                "is_read": bool(row[7]),
                "source": row[8] or "BSE Surveillance"
            })
    except Exception as e:
        logger.error(f"Error in get_alert_events: {e}")
    finally:
        cursor.close()
        conn.close()
    return alerts

def mark_alert_as_read(alert_id: int):
    """Marks a single alert event as read."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    try:
        val = "TRUE" if supabase_url else "1"
        cursor.execute(f"UPDATE alert_events SET is_read = {val} WHERE id = {placeholder}", (alert_id,))
        conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error in mark_alert_as_read: {e}")
    finally:
        cursor.close()
        conn.close()

def mark_all_alerts_as_read(ticker: str = None):
    """Marks all alerts (optionally filtered by ticker) as read."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    try:
        val = "TRUE" if supabase_url else "1"
        if ticker:
            clean = clean_ticker(ticker)
            cursor.execute(f"UPDATE alert_events SET is_read = {val} WHERE ticker = {placeholder}", (clean,))
        else:
            cursor.execute(f"UPDATE alert_events SET is_read = {val}")
        conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error in mark_all_alerts_as_read: {e}")
    finally:
        cursor.close()
        conn.close()

def dismiss_alert(alert_id: int) -> bool:
    """Permanently dismisses and deletes an alert event from the database."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    success = False
    try:
        cursor.execute(f"DELETE FROM alert_events WHERE id = {placeholder}", (alert_id,))
        conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
        success = True
    except Exception as e:
        logger.error(f"Error in dismiss_alert: {e}")
    finally:
        cursor.close()
        conn.close()
    return success

def dismiss_all_alerts(unread_only: bool = False) -> bool:
    """Permanently dismisses and deletes alerts."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    success = False
    try:
        if unread_only:
            unread_cond = "is_read = FALSE" if supabase_url else "is_read = 0"
            cursor.execute(f"DELETE FROM alert_events WHERE {unread_cond}")
        else:
            cursor.execute("DELETE FROM alert_events")
        conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
        success = True
    except Exception as e:
        logger.error(f"Error in dismiss_all_alerts: {e}")
    finally:
        cursor.close()
        conn.close()
    return success

def get_unread_alert_count(ticker: str = None) -> int:
    """Returns the total number of unread alerts."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    count = 0
    try:
        unread_cond = "is_read = FALSE" if supabase_url else "is_read = 0"
        if ticker:
            clean = clean_ticker(ticker)
            cursor.execute(f"SELECT COUNT(*) FROM alert_events WHERE {unread_cond} AND ticker = {placeholder}", (clean,))
        else:
            cursor.execute(f"SELECT COUNT(*) FROM alert_events WHERE {unread_cond}")
        row = cursor.fetchone()
        if row:
            count = row[0]
    except Exception:
        pass
    finally:
        cursor.close()
        conn.close()
    return count
