import os
import streamlit as st

def get_db_connection():
    # Production: Uses Supabase PostgreSQL if secret exists
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    if supabase_url:
        import psycopg2
        return psycopg2.connect(supabase_url)
    
    # Local Testing Fallback: Uses SQLite if no Supabase URL is present
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
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                ticker TEXT PRIMARY KEY,
                short_name TEXT,
                report_text TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    conn.commit()
    cursor.close()
    conn.close()

def save_report_to_archive(stock_data: dict, report_text: str):
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    supabase_url = st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    placeholder = "%s" if supabase_url else "?"
    
    query = f'''
        INSERT INTO reports (ticker, short_name, report_text)
        VALUES ({placeholder}, {placeholder}, {placeholder})
        ON CONFLICT (ticker) 
        DO UPDATE SET 
            report_text = EXCLUDED.report_text,
            timestamp = CURRENT_TIMESTAMP
    '''
    cursor.execute(query, (stock_data.get("ticker"), stock_data.get("short_name"), report_text))
    conn.commit()
    cursor.close()
    conn.close()
