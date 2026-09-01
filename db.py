import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st

def get_db_connection():
    # Pulls the connection URI directly from your .streamlit/secrets.toml
    return psycopg2.connect(st.secrets["SUPABASE_DB_URL"])

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            ticker TEXT PRIMARY KEY,
            short_name TEXT,
            report_text TEXT,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

def save_report_to_archive(stock_data: dict, report_text: str):
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO reports (ticker, short_name, report_text)
        VALUES (%s, %s, %s)
        ON CONFLICT (ticker) 
        DO UPDATE SET 
            short_name = EXCLUDED.short_name,
            report_text = EXCLUDED.report_text,
            timestamp = CURRENT_TIMESTAMP
    ''', (stock_data.get("ticker"), stock_data.get("short_name"), report_text))
    conn.commit()
    cursor.close()
    conn.close()

def get_archived_reports() -> list:
    init_db()
    conn = get_db_connection()
    # RealDictCursor ensures compatibility with your existing frontend dict loop
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT ticker, short_name, report_text, timestamp FROM reports ORDER BY timestamp DESC')
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(row) for row in rows]