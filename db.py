import os
from datetime import datetime
import streamlit as st

def get_db_connection():
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    if supabase_url:
        import psycopg2
        return psycopg2.connect(supabase_url)
    
    import sqlite3
    return sqlite3.connect("reports.db")

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    
    if supabase_url:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                ticker TEXT PRIMARY KEY,
                short_name TEXT,
                report_text TEXT,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                baseline_price NUMERIC,
                baseline_pe TEXT,
                baseline_mcap NUMERIC,
                latest_announcement TEXT
            )
        ''')
        # Add columns if migrating an existing table
        for col, col_type in [("baseline_price", "NUMERIC"), ("baseline_pe", "TEXT"), ("baseline_mcap", "NUMERIC"), ("latest_announcement", "TEXT")]:
            cursor.execute(f"ALTER TABLE reports ADD COLUMN IF NOT EXISTS {col} {col_type};")
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                ticker TEXT PRIMARY KEY,
                short_name TEXT,
                report_text TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                baseline_price REAL,
                baseline_pe TEXT,
                baseline_mcap REAL,
                latest_announcement TEXT
            )
        ''')
        # SQLite migration
        cursor.execute("PRAGMA table_info(reports);")
        existing_cols = [c[1] for c in cursor.fetchall()]
        for col, col_type in [("baseline_price", "REAL"), ("baseline_pe", "TEXT"), ("baseline_mcap", "REAL"), ("latest_announcement", "TEXT")]:
            if col not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE reports ADD COLUMN {col} {col_type};")
                except Exception:
                    pass

    conn.commit()
    cursor.close()
    conn.close()

def save_report_to_archive(stock_data: dict, report_text: str, announcement: str = ""):
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
    
    curr_price = stock_data.get("current_price") or stock_data.get("currentValue") or 0.0
    try:
        curr_price = float(str(curr_price).replace(",", "").strip())
    except Exception:
        curr_price = 0.0

    mcap = stock_data.get("market_cap") or stock_data.get("marketCapFull") or 0.0
    try:
        mcap = float(str(mcap).replace(",", "").strip())
    except Exception:
        mcap = 0.0

    pe = str(stock_data.get("pe_ratio", "N/A"))

    query = f'''
        INSERT INTO reports (ticker, short_name, report_text, baseline_price, baseline_pe, baseline_mcap, latest_announcement)
        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        ON CONFLICT (ticker) 
        DO UPDATE SET 
            short_name = EXCLUDED.short_name,
            report_text = EXCLUDED.report_text,
            timestamp = CURRENT_TIMESTAMP,
            baseline_price = EXCLUDED.baseline_price,
            baseline_pe = EXCLUDED.baseline_pe,
            baseline_mcap = EXCLUDED.baseline_mcap,
            latest_announcement = EXCLUDED.latest_announcement
    '''
    cursor.execute(query, (
        stock_data.get("ticker"), 
        stock_data.get("short_name"), 
        report_text,
        curr_price,
        pe,
        mcap,
        announcement
    ))
    conn.commit()
    cursor.close()
    conn.close()

def _format_timestamp(raw_ts) -> str:
    if not raw_ts:
        return "Unknown Date"
    if isinstance(raw_ts, datetime):
        return raw_ts.strftime("%d-%b-%Y %H:%M")
    try:
        parsed = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00").split("+")[0])
        return parsed.strftime("%d-%b-%Y %H:%M")
    except Exception:
        return str(raw_ts)[:16]

def get_archived_reports() -> list:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    results = []
    try:
        cursor.execute('''
            SELECT ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement
            FROM reports 
            ORDER BY timestamp DESC
        ''')
        rows = cursor.fetchall()
        for row in rows:
            results.append({
                "ticker": row[0],
                "short_name": row[1] or row[0],
                "report_text": row[2],
                "raw_timestamp": row[3],
                "formatted_date": _format_timestamp(row[3]),
                "baseline_price": row[4],
                "baseline_pe": row[5],
                "baseline_mcap": row[6],
                "latest_announcement": row[7] or ""
            })
    except Exception as e:
        print(f"Database query error in get_archived_reports: {e}")
    finally:
        cursor.close()
        conn.close()
    return results

def get_report_by_ticker(ticker: str) -> dict:
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
    
    record = None
    try:
        cursor.execute(f'''
            SELECT ticker, short_name, report_text, timestamp, baseline_price, baseline_pe, baseline_mcap, latest_announcement
            FROM reports 
            WHERE ticker = {placeholder}
        ''', (clean,))
        row = cursor.fetchone()
        if row:
            record = {
                "ticker": row[0],
                "short_name": row[1] or row[0],
                "report_text": row[2],
                "raw_timestamp": row[3],
                "formatted_date": _format_timestamp(row[3]),
                "baseline_price": row[4],
                "baseline_pe": row[5],
                "baseline_mcap": row[6],
                "latest_announcement": row[7] or ""
            }
    except Exception as e:
        print(f"Database query error in get_report_by_ticker: {e}")
    finally:
        cursor.close()
        conn.close()
    return record
