"""Support tickets, user grievances, and complaints repository."""

import logging
import uuid
from datetime import datetime
from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder, IST
from core.db.reports import _format_timestamp

logger = logging.getLogger("equity_research.core.db.support")


def create_support_ticket(
    user_email: str,
    subject: str,
    message: str,
    user_name: str = "",
    category: str = "general",
    source: str = "web_contact"
) -> dict:
    """
    Creates a new support/grievance ticket in the database.
    Generates a unique reference ticket ID (e.g., TKT-7A4B2C).
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()

    clean_email = str(user_email or "").strip().lower()
    clean_subj = str(subject or "").strip()
    clean_msg = str(message or "").strip()
    clean_name = str(user_name or "").strip()
    clean_cat = str(category or "general").strip().lower()
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"

    try:
        query = f'''
            INSERT INTO support_tickets (ticket_id, user_email, user_name, category, subject, message, status, source)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, 'open', {placeholder})
        '''
        cursor.execute(query, (ticket_id, clean_email, clean_name, clean_cat, clean_subj, clean_msg, source))
        conn.commit()
        logger.info(f"Created support ticket {ticket_id} from {clean_email}")
        return {
            "success": True,
            "ticket_id": ticket_id,
            "user_email": clean_email,
            "user_name": clean_name,
            "category": clean_cat,
            "subject": clean_subj,
            "message": clean_msg,
            "status": "open",
            "created_at": datetime.now(IST).strftime("%d-%m-%Y %H:%M IST")
        }
    except Exception as e:
        logger.error(f"Error creating support ticket: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()


def get_support_tickets(status: str = None, limit: int = 50) -> list:
    """Retrieves support tickets filtered by status ('open', 'resolved', 'all')."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    tickets = []

    try:
        if status and status.lower() != "all":
            query = f'''
                SELECT id, ticket_id, user_email, user_name, category, subject, message, status, admin_notes, source, created_at
                FROM support_tickets
                WHERE status = {placeholder}
                ORDER BY created_at DESC
                LIMIT {placeholder}
            '''
            cursor.execute(query, (status.lower(), limit))
        else:
            query = f'''
                SELECT id, ticket_id, user_email, user_name, category, subject, message, status, admin_notes, source, created_at
                FROM support_tickets
                ORDER BY created_at DESC
                LIMIT {placeholder}
            '''
            cursor.execute(query, (limit,))

        rows = cursor.fetchall()
        for r in rows:
            tickets.append({
                "id": r[0],
                "ticket_id": r[1],
                "user_email": r[2],
                "user_name": r[3] or "",
                "category": r[4] or "general",
                "subject": r[5] or "",
                "message": r[6] or "",
                "status": r[7] or "open",
                "admin_notes": r[8] or "",
                "source": r[9] or "web_contact",
                "created_at": _format_timestamp(r[10]),
            })
    except Exception as e:
        logger.error(f"Error fetching support tickets: {e}")
    finally:
        cursor.close()
        conn.close()

    return tickets


def update_ticket_status(ticket_id: str, new_status: str, admin_notes: str = None) -> bool:
    """Updates the status and optional admin resolution notes on a ticket."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    clean_tid = str(ticket_id).strip()
    clean_status = str(new_status).strip().lower()

    try:
        if admin_notes is not None:
            query = f'''
                UPDATE support_tickets
                SET status = {placeholder}, admin_notes = {placeholder}, updated_at = CURRENT_TIMESTAMP
                WHERE ticket_id = {placeholder}
            '''
            cursor.execute(query, (clean_status, admin_notes, clean_tid))
        else:
            query = f'''
                UPDATE support_tickets
                SET status = {placeholder}, updated_at = CURRENT_TIMESTAMP
                WHERE ticket_id = {placeholder}
            '''
            cursor.execute(query, (clean_status, clean_tid))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error updating ticket {clean_tid}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        cursor.close()
        conn.close()


def get_open_tickets_count() -> int:
    """Returns the total number of unresolved open support tickets."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'open';")
        row = cursor.fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
    finally:
        cursor.close()
        conn.close()
