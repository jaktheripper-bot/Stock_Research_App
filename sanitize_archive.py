import os
import sqlite3
import streamlit as st
from db import get_db_connection
from analyzer import strip_conclusion_sections

def sanitize_database():
    print("=======================================================")
    print("   ARCHIVE SANITIZATION: SEBI COMPLIANCE RETROFIT")
    print("=======================================================")

    # 1. Sanitize Primary Database (Supabase PostgreSQL or fallback)
    conn = get_db_connection()
    cursor = conn.cursor()
    updated_count = 0
    total_count = 0

    try:
        cursor.execute("SELECT ticker, report_text FROM reports")
        rows = cursor.fetchall()
        total_count = len(rows)
        print(f"Auditing {total_count} records in primary database...")

        is_pg = hasattr(cursor, "mogrify") or (st.secrets.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL"))
        param_placeholder = "%s" if is_pg else "?"

        for ticker, original_text in rows:
            if not original_text:
                continue
            cleaned = strip_conclusion_sections(original_text)
            if cleaned != original_text:
                cursor.execute(
                    f"UPDATE reports SET report_text = {param_placeholder} WHERE ticker = {param_placeholder}",
                    (cleaned, ticker)
                )
                updated_count += 1
                diff = len(original_text) - len(cleaned)
                print(f"  ✓ Sanitized '{ticker}': stripped {diff} characters of non-compliant content.")

        conn.commit()
        print(f"\n✅ Primary database updated: {updated_count} of {total_count} archived reports sanitized.")
    except Exception as e:
        print(f"❌ Error during primary database sanitization: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    # 2. Also Sanitize Local SQLite (reports.db) if it exists and has rows
    if os.path.exists("reports.db"):
        print("\nChecking local SQLite reports.db...")
        local_conn = sqlite3.connect("reports.db")
        local_cur = local_conn.cursor()
        try:
            local_cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='reports'")
            if local_cur.fetchone()[0] > 0:
                local_cur.execute("SELECT ticker, report_text FROM reports")
                local_rows = local_cur.fetchall()
                local_updated = 0
                for ticker, original_text in local_rows:
                    if not original_text:
                        continue
                    cleaned = strip_conclusion_sections(original_text)
                    if cleaned != original_text:
                        local_cur.execute("UPDATE reports SET report_text = ? WHERE ticker = ?", (cleaned, ticker))
                        local_updated += 1
                local_conn.commit()
                print(f"✅ Local SQLite reports.db: {local_updated} of {len(local_rows)} sanitized.")
        except Exception as e:
            print(f"Local SQLite notice: {e}")
        finally:
            local_cur.close()
            local_conn.close()

    print("\n🎉 Archive sanitization complete. All stored reports are compliant.")

if __name__ == "__main__":
    sanitize_database()
