"""SEBI Safe Harbor compliance and immutable statutory audit logging repository."""

import hashlib
import logging
from datetime import datetime
from normalizer import clean_ticker
from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder, IST

logger = logging.getLogger("equity_research.core.db.compliance")

MANDATORY_SEBI_DISCLAIMER = (
    "Mandatory SEBI Safe-Harbor Disclosure: Stock Research AI is an automated, computational financial research "
    "synthesis software utility. We are NOT registered as a Research Analyst or Investment Adviser "
    "under SEBI regulations. All analytical outputs, 7-pillar scorecards, and syntheses are algorithmically compiled "
    "from public exchange disclosures for educational and research purposes only. Past performance does not guarantee "
    "future results. Consult an independent SEBI-registered advisor before investing."
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
                except Exception as parse_err:
                    logger.debug("Timestamp parsing notice: %s", parse_err)
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
