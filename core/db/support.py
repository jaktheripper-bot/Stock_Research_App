"""Support tickets, user grievances, and complaints repository."""

import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict
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
        except Exception as rb_err:
            logger.debug("Support ticket rollback failed: %s", rb_err)
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()


def get_support_tickets(status: str = None, limit: int = 50, exclude_tests: bool = True) -> list:
    """Retrieves support tickets filtered by status ('open', 'resolved', 'all') with automatic test ticket exclusion."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    tickets = []

    where_clauses = ["1=1"]
    params = []

    if status and status.lower() != "all":
        where_clauses.append(f"status = {p}")
        params.append(status.lower().strip())

    if exclude_tests:
        where_clauses.append(f"user_email NOT LIKE {p}")
        params.append("%@example.com")
        where_clauses.append(f"user_email NOT LIKE {p}")
        params.append("%@test.com")
        where_clauses.append(f"user_email NOT LIKE {p}")
        params.append("%@pytest.com")
        where_clauses.append(f"ticket_id NOT LIKE {p}")
        params.append("TKT-TEST-%")

    safe_limit = max(1, min(int(limit or 50), 500))
    params.append(safe_limit)

    query = f'''
        SELECT id, ticket_id, user_email, user_name, category, subject, message, status, admin_notes, source, created_at
        FROM support_tickets
        WHERE {' AND '.join(where_clauses)}
        ORDER BY created_at DESC
        LIMIT {p}
    '''

    try:
        cursor.execute(query, tuple(params))
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
                "responses": [],
            })
    except Exception as e:
        logger.error(f"Error fetching support tickets: {e}")
    finally:
        cursor.close()
        conn.close()

    # Populate conversation response thread for each ticket
    for t in tickets:
        try:
            t["responses"] = get_ticket_responses(t["ticket_id"])
        except Exception as e:
            logger.debug("Failed fetching responses for ticket %s: %s", t.get("ticket_id"), e)
            t["responses"] = []

    return tickets


def add_ticket_response(
    ticket_id: str,
    message: str = "",
    sender_email: Optional[str] = None,
    sender_name: str = "Support Desk",
    sender_type: str = "admin",
    email_dispatched: bool = False,
    responder_email: Optional[str] = None,
    responder_role: Optional[str] = None,
    email_sent: Optional[bool] = None,
    **kwargs: Any
) -> dict:
    """
    Records an outgoing or incoming response to a support ticket.
    Supports canonical sender_* and aliased responder_* parameters.
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    clean_tid = str(ticket_id or "").strip()
    clean_msg = str(message or "").strip()

    effective_email = sender_email if sender_email is not None else responder_email
    clean_sender_email = str(effective_email).strip().lower() if effective_email else None

    effective_type = responder_role if responder_role is not None else sender_type
    clean_sender_type = str(effective_type or "admin").strip().lower()

    if clean_sender_type == "user" and sender_name == "Support Desk":
        clean_sender_name = "User / Ticket Owner"
    else:
        clean_sender_name = str(sender_name or "Support Desk").strip()

    effective_sent = email_sent if email_sent is not None else email_dispatched
    disp_val = True if effective_sent else False

    try:
        query = f'''
            INSERT INTO ticket_responses (ticket_id, sender_type, sender_email, sender_name, message, email_dispatched)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p})
        '''
        cursor.execute(query, (clean_tid, clean_sender_type, clean_sender_email, clean_sender_name, clean_msg, disp_val))
        cursor.execute(f"UPDATE support_tickets SET updated_at = CURRENT_TIMESTAMP WHERE ticket_id = {p};", (clean_tid,))
        conn.commit()
        return {
            "success": True,
            "ticket_id": clean_tid,
            "sender_type": clean_sender_type,
            "sender_email": clean_sender_email,
            "sender_name": clean_sender_name,
            "message": clean_msg,
            "email_dispatched": disp_val,
            "created_at": datetime.now(IST).strftime("%d-%m-%Y %H:%M IST")
        }
    except Exception as e:
        logger.error(f"Error adding ticket response for {clean_tid}: {e}")
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug("Ticket response rollback failed: %s", rb_err)
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()


def get_ticket_responses(ticket_id: str) -> list:
    """Retrieves all responses / message history for a specific ticket in chronological order."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    responses = []
    clean_tid = str(ticket_id or "").strip()

    query = f'''
        SELECT id, ticket_id, sender_type, sender_email, sender_name, message, email_dispatched, created_at
        FROM ticket_responses
        WHERE ticket_id = {p}
        ORDER BY created_at ASC
    '''
    try:
        cursor.execute(query, (clean_tid,))
        rows = cursor.fetchall()
        for r in rows:
            responses.append({
                "id": r[0],
                "ticket_id": r[1],
                "sender_type": r[2] or "admin",
                "sender_email": r[3] or "",
                "sender_name": r[4] or "Support Desk",
                "message": r[5] or "",
                "email_dispatched": bool(r[6]),
                "created_at": _format_timestamp(r[7]),
            })
    except Exception as e:
        logger.error(f"Error fetching ticket responses for {clean_tid}: {e}")
    finally:
        cursor.close()
        conn.close()

    return responses


def get_ticket_by_id(ticket_id: str, include_responses: bool = True) -> Optional[dict]:
    """Retrieves a single support ticket by its ticket_id, optionally including full response thread."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    clean_tid = str(ticket_id or "").strip()

    query = f'''
        SELECT id, ticket_id, user_email, user_name, category, subject, message, status, admin_notes, source, created_at
        FROM support_tickets
        WHERE ticket_id = {p}
        LIMIT 1
    '''
    ticket = None
    try:
        cursor.execute(query, (clean_tid,))
        r = cursor.fetchone()
        if r:
            ticket = {
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
                "responses": []
            }
            if include_responses:
                ticket["responses"] = get_ticket_responses(clean_tid)
    except Exception as e:
        logger.error(f"Error fetching ticket {clean_tid}: {e}")
    finally:
        cursor.close()
        conn.close()

    return ticket


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
        except Exception as rb_err:
            logger.debug("Support ticket rollback failed: %s", rb_err)
        return False
    finally:
        cursor.close()
        conn.close()


def get_open_tickets_count(exclude_tests: bool = True) -> int:
    """Returns the total number of unresolved open support tickets (excluding test runs)."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    where_clauses = ["status IN ('open', 'in_progress')"]
    params = []

    if exclude_tests:
        where_clauses.append(f"user_email NOT LIKE {p}")
        params.append("%@example.com")
        where_clauses.append(f"user_email NOT LIKE {p}")
        params.append("%@test.com")
        where_clauses.append(f"user_email NOT LIKE {p}")
        params.append("%@pytest.com")
        where_clauses.append(f"ticket_id NOT LIKE {p}")
        params.append("TKT-TEST-%")

    query = f"SELECT COUNT(*) FROM support_tickets WHERE {' AND '.join(where_clauses)};"
    try:
        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        return row[0] if row else 0
    except Exception as e:
        logger.error(f"Error fetching open tickets count: {e}")
        return 0
    finally:
        cursor.close()
        conn.close()
