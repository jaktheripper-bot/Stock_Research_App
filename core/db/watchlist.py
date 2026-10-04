"""Stock surveillance watchlist repository and state management."""

import logging
from functools import lru_cache
from normalizer import clean_ticker
from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder
from core.db.reports import _format_timestamp

logger = logging.getLogger("equity_research.core.db.watchlist")

@lru_cache(maxsize=128)
def get_watchlist() -> list:
    """Retrieves all tracked stocks in the surveillance watchlist."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    items = []
    try:
        cursor.execute('''
            SELECT id, ticker, short_name, scrip_code, added_at,
                   alert_material, alert_fundamental, alert_valuation,
                   digest_mode, last_scanned_price, last_scanned_announcement, last_scanned_at
            FROM watchlist
            ORDER BY ticker ASC
        ''')
        for row in cursor.fetchall():
            items.append({
                "id": row[0],
                "ticker": row[1],
                "short_name": row[2] or row[1],
                "scrip_code": row[3] or "",
                "added_at": _format_timestamp(row[4]),
                "alert_material": bool(row[5]),
                "alert_fundamental": bool(row[6]),
                "alert_valuation": bool(row[7]),
                "digest_mode": row[8] or "instant",
                "last_scanned_price": float(row[9]) if row[9] is not None else None,
                "last_scanned_announcement": row[10] or "",
                "last_scanned_at": _format_timestamp(row[11]) if row[11] else "Not yet scanned"
            })
    except Exception as e:
        logger.error(f"Database query error in get_watchlist: {e}")
    finally:
        cursor.close()
        conn.close()
    return items

get_watchlist.clear = get_watchlist.cache_clear

def add_to_watchlist(ticker: str, short_name: str = "", scrip_code: str = "",
                     alert_material: bool = True, alert_fundamental: bool = True,
                     alert_valuation: bool = True, digest_mode: str = "instant",
                     initial_price: float = None) -> bool:
    """Adds a stock to the surveillance watchlist or updates its subscription preferences."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    success = False
    try:
        if supabase_url:
            query = f'''
                INSERT INTO watchlist (ticker, short_name, scrip_code, alert_material, alert_fundamental, alert_valuation, digest_mode, last_scanned_price)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                ON CONFLICT (ticker) DO UPDATE SET
                    short_name = COALESCE(EXCLUDED.short_name, watchlist.short_name),
                    scrip_code = COALESCE(EXCLUDED.scrip_code, watchlist.scrip_code),
                    alert_material = EXCLUDED.alert_material,
                    alert_fundamental = EXCLUDED.alert_fundamental,
                    alert_valuation = EXCLUDED.alert_valuation,
                    digest_mode = EXCLUDED.digest_mode
            '''
        else:
            query = f'''
                INSERT INTO watchlist (ticker, short_name, scrip_code, alert_material, alert_fundamental, alert_valuation, digest_mode, last_scanned_price)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                ON CONFLICT (ticker) DO UPDATE SET
                    short_name = COALESCE(excluded.short_name, watchlist.short_name),
                    scrip_code = COALESCE(excluded.scrip_code, watchlist.scrip_code),
                    alert_material = excluded.alert_material,
                    alert_fundamental = excluded.alert_fundamental,
                    alert_valuation = excluded.alert_valuation,
                    digest_mode = excluded.digest_mode
            '''
        cursor.execute(query, (
            clean,
            short_name or clean,
            scrip_code,
            alert_material,
            alert_fundamental,
            alert_valuation,
            digest_mode,
            initial_price
        ))
        conn.commit()
        try:
            get_watchlist.cache_clear()
        except Exception:
            pass
        success = True
    except Exception as e:
        logger.error(f"Database error in add_to_watchlist: {e}")
    finally:
        cursor.close()
        conn.close()
    return success

def remove_from_watchlist(ticker: str) -> bool:
    """Removes a stock from the surveillance watchlist."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    placeholder = get_placeholder()
    success = False
    try:
        cursor.execute(f"DELETE FROM watchlist WHERE ticker = {placeholder}", (clean,))
        conn.commit()
        try:
            get_watchlist.cache_clear()
        except Exception:
            pass
        success = True
    except Exception as e:
        logger.error(f"Database error in remove_from_watchlist: {e}")
    finally:
        cursor.close()
        conn.close()
    return success

def is_ticker_in_watchlist(ticker: str) -> bool:
    """Checks whether a ticker is currently active on the surveillance watchlist."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    placeholder = get_placeholder()
    in_watch = False
    try:
        cursor.execute(f"SELECT 1 FROM watchlist WHERE ticker = {placeholder}", (clean,))
        in_watch = cursor.fetchone() is not None
    except Exception:
        pass
    finally:
        cursor.close()
        conn.close()
    return in_watch

def update_watchlist_scan_state(ticker: str, price: float = None, announcement: str = None):
    """Updates the last scanned price and announcement for a watchlisted stock."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = clean_ticker(ticker)
    placeholder = get_placeholder()
    try:
        cursor.execute(f'''
            UPDATE watchlist
            SET last_scanned_price = COALESCE({placeholder}, last_scanned_price),
                last_scanned_announcement = COALESCE({placeholder}, last_scanned_announcement),
                last_scanned_at = CURRENT_TIMESTAMP
            WHERE ticker = {placeholder}
        ''', (price, announcement, clean))
        conn.commit()
    except Exception as e:
        logger.error(f"Error in update_watchlist_scan_state: {e}")
    finally:
        cursor.close()
        conn.close()
