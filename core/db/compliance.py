"""SEBI Safe Harbor compliance and immutable statutory audit logging repository."""

import hashlib
import logging
from datetime import datetime
from normalizer import clean_ticker
from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder, IST

logger = logging.getLogger("equity_research.core.db.compliance")

MANDATORY_SEBI_DISCLAIMER = (
    "SEBI Safe Harbor & Statutory Compliance: Antigravity Equity Research Engine is a diagnostic "
    "algorithmic analytics and financial research tool developed strictly for informational, educational, "
    "and analytical purposes. It does NOT provide, and should NEVER be construed as providing, investment advice, "
    "recommendations, endorsements, or financial solicitations of any kind. Antigravity is not a SEBI-registered "
    "Research Analyst (RA) or Investment Adviser (IA). Indian securities markets are subject to high market risks; "
    "past performance, algorithmic valuations, fair values, and technical support/resistance bands are historical "
    "and model-based estimates that do not guarantee future returns. Users must consult a qualified, SEBI-registered "
    "financial adviser before executing any investment decisions."
)

def log_compliance_event(ticker: str, disclaimer_text: str = None) -> bool:
    """Records a SEBI Safe Harbor disclaimer attachment event in the immutable audit log."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()

    clean_sym = clean_ticker(ticker)
    target_disclaimer = disclaimer_text or MANDATORY_SEBI_DISCLAIMER
    disclaimer_hash = hashlib.sha256(target_disclaimer.encode("utf-8")).hexdigest()
    disclaimer_version = "SEBI-RA-2024-V1"

    try:
        query = f'''
            INSERT INTO compliance_audit_log (ticker, disclaimer_version, disclaimer_hash)
            VALUES ({placeholder}, {placeholder}, {placeholder})
        '''
        cursor.execute(query, (clean_sym, disclaimer_version, disclaimer_hash))
        conn.commit()
        logger.info(f"Recorded SEBI compliance audit event for {clean_sym} (hash={disclaimer_hash[:8]}...)")
        return True
    except Exception as e:
        logger.error(f"Error logging compliance event for {clean_sym}: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def get_compliance_audit_logs(ticker: str = None, limit: int = 50) -> list:
    """Retrieves immutable SEBI Safe Harbor compliance audit events."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()

    try:
        if ticker:
            clean_sym = clean_ticker(ticker)
            query = f'''
                SELECT id, ticker, disclaimer_version, disclaimer_hash, timestamp
                FROM compliance_audit_log
                WHERE ticker = {placeholder}
                ORDER BY timestamp DESC
                LIMIT {placeholder}
            '''
            cursor.execute(query, (clean_sym, limit))
        else:
            query = f'''
                SELECT id, ticker, disclaimer_version, disclaimer_hash, timestamp
                FROM compliance_audit_log
                ORDER BY timestamp DESC
                LIMIT {placeholder}
            '''
            cursor.execute(query, (limit,))

        rows = cursor.fetchall()
        logs = []
        for row in rows:
            ts = row[4]
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    pass
            if hasattr(ts, "astimezone"):
                ts = ts.astimezone(IST)
            formatted_date = ts.strftime("%d-%m-%Y %H:%M IST") if hasattr(ts, "strftime") else str(ts)
            logs.append({
                "id": row[0],
                "ticker": row[1],
                "disclaimer_version": row[2],
                "disclaimer_hash": row[3],
                "timestamp": ts,
                "formatted_date": formatted_date
            })
        return logs
    except Exception as e:
        logger.error(f"Error fetching compliance audit logs: {e}")
        return []
    finally:
        cursor.close()
        conn.close()
