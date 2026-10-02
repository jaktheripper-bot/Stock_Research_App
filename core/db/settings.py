"""System settings key-value persistence repository."""

import logging
from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder

logger = logging.getLogger("equity_research.core.db.settings")

def get_system_setting(key: str, default: str | None = None) -> str | None:
    """Retrieve a persisted system setting from PostgreSQL/SQLite."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    try:
        cursor.execute(f"SELECT value FROM system_settings WHERE key = {placeholder};", (key,))
        row = cursor.fetchone()
        if row and row[0] is not None:
            return str(row[0])
        return default
    except Exception as e:
        logger.error(f"Error fetching system setting '{key}': {e}")
        return default
    finally:
        cursor.close()
        conn.close()

def set_system_setting(key: str, value: str) -> bool:
    """Upsert a persisted system setting in PostgreSQL/SQLite."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    placeholder = get_placeholder()
    try:
        if supabase_url:
            cursor.execute(
                f"""
                INSERT INTO system_settings (key, value, updated_at)
                VALUES ({placeholder}, {placeholder}, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
                """,
                (key, value)
            )
        else:
            cursor.execute(
                f"""
                INSERT INTO system_settings (key, value, updated_at)
                VALUES ({placeholder}, {placeholder}, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
                """,
                (key, value)
            )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error persisting system setting '{key}': {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        cursor.close()
        conn.close()
