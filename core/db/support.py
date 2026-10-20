"""Support tickets, user grievances, and complaints repository."""

import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder, is_postgres_connection, IST
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


def get_support_tickets(
    status: str = None,
    limit: int = 100,
    exclude_tests: bool = True,
    search_query: str = None,
    category: str = None,
    sort_by: str = "newest"
) -> list:
    """
    Retrieves support tickets filtered by status ('open', 'in_progress', 'resolved', 'closed',
    'active' -> open/in_progress, 'archived' -> resolved/closed, or 'all'), optional search query,
    category, and sort order.
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = "%s" if is_postgres_connection(conn) else "?"
    tickets = []

    where_clauses = ["1=1"]
    params = []

    if status:
        st_clean = status.lower().strip()
        if st_clean == "active":
            where_clauses.append("LOWER(status) IN ('open', 'in_progress')")
        elif st_clean == "archived":
            where_clauses.append("LOWER(status) IN ('resolved', 'closed')")
        elif st_clean != "all":
            where_clauses.append(f"LOWER(status) = {p}")
            params.append(st_clean)

    if category and category.lower().strip() not in ("", "all"):
        where_clauses.append(f"LOWER(category) = {p}")
        params.append(category.lower().strip())

    if search_query and search_query.strip():
        q_like = f"%{search_query.strip().lower()}%"
        where_clauses.append(
            f"(LOWER(ticket_id) LIKE {p} OR LOWER(user_email) LIKE {p} OR LOWER(COALESCE(user_name, '')) LIKE {p} "
            f"OR LOWER(COALESCE(subject, '')) LIKE {p} OR LOWER(COALESCE(message, '')) LIKE {p} "
            f"OR LOWER(COALESCE(admin_notes, '')) LIKE {p} "
            f"OR EXISTS (SELECT 1 FROM ticket_responses tr WHERE tr.ticket_id = support_tickets.ticket_id AND LOWER(COALESCE(tr.message, '')) LIKE {p}))"
        )
        params.extend([q_like, q_like, q_like, q_like, q_like, q_like, q_like])

    if exclude_tests:
        where_clauses.append(f"user_email NOT LIKE {p}")
        params.append("%@example.com")
        where_clauses.append(f"user_email NOT LIKE {p}")
        params.append("%@test.com")
        where_clauses.append(f"user_email NOT LIKE {p}")
        params.append("%@pytest.com")
        where_clauses.append(f"ticket_id NOT LIKE {p}")
        params.append("TKT-TEST-%")

    order_map = {
        "newest": "created_at DESC, id DESC",
        "oldest": "created_at ASC, id ASC",
        "ticket_id": "ticket_id ASC",
        "email": "user_email ASC",
        "category": "category ASC, created_at DESC",
        "status": "status ASC, created_at DESC",
    }
    order_clause = order_map.get((sort_by or "newest").lower().strip(), "created_at DESC, id DESC")

    safe_limit = max(1, min(int(limit or 100), 500))
    params.append(safe_limit)

    query = f'''
        SELECT id, ticket_id, user_email, user_name, category, subject, message, status, admin_notes, source, created_at
        FROM support_tickets
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {order_clause}
        LIMIT {p}
    '''

    try:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        for r in rows:
            raw_ts = r[10]
            iso_ts = str(raw_ts or "")
            tickets.append({
                "id": r[0],
                "ticket_id": r[1],
                "user_email": r[2],
                "user_name": r[3] or "",
                "category": r[4] or "general",
                "subject": r[5] or "",
                "message": r[6] or "",
                "status": (r[7] or "open").lower().strip(),
                "admin_notes": r[8] or "",
                "source": r[9] or "web_contact",
                "created_at": _format_timestamp(raw_ts),
                "created_at_raw": iso_ts,
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
            "responder_role": clean_sender_type,
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
                "responder_role": r[2] or "admin",
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
        WHERE UPPER(ticket_id) = UPPER({p})
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
                "status": (r[7] or "open").lower().strip(),
                "admin_notes": r[8] or "",
                "source": r[9] or "web_contact",
                "created_at": _format_timestamp(r[10]),
                "created_at_raw": str(r[10] or ""),
                "responses": []
            }
            if include_responses:
                ticket["responses"] = get_ticket_responses(ticket["ticket_id"])
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
    clean_tid = str(ticket_id or "").strip()
    clean_status = str(new_status or "open").strip().lower()

    try:
        if admin_notes is not None:
            query = f'''
                UPDATE support_tickets
                SET status = {placeholder}, admin_notes = {placeholder}, updated_at = CURRENT_TIMESTAMP
                WHERE UPPER(ticket_id) = UPPER({placeholder})
            '''
            cursor.execute(query, (clean_status, admin_notes, clean_tid))
        else:
            query = f'''
                UPDATE support_tickets
                SET status = {placeholder}, updated_at = CURRENT_TIMESTAMP
                WHERE UPPER(ticket_id) = UPPER({placeholder})
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
    where_clauses = ["LOWER(status) IN ('open', 'in_progress')"]
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


DEFAULT_CANNED_RESPONSES = [
    {
        "title": "Acknowledge & Investigating",
        "category": "general",
        "target_status": "in_progress",
        "default_credits": 0.0,
        "body": (
            "Hello,\n\nThank you for reaching out to our Support Desk. We have received your inquiry "
            "and our engineering team is actively investigating the details.\n\nWe will follow up shortly "
            "with a resolution update.\n\nWarm regards,\nSupport & Operations Desk"
        ),
        "is_system": 1,
    },
    {
        "title": "Issue Resolved + Courtesy Credit",
        "category": "general",
        "target_status": "resolved",
        "default_credits": 1.0,
        "body": (
            "Hello,\n\nThank you for bringing this to our attention. We have resolved the issue you reported "
            "and verified that everything is functioning normally.\n\nAs a token of appreciation for your patience, "
            "we have added complimentary report credit(s) directly to your account.\n\nWarm regards,\nSupport & Operations Desk"
        ),
        "is_system": 1,
    },
    {
        "title": "Billing / Payment Clarified",
        "category": "billing",
        "target_status": "resolved",
        "default_credits": 0.0,
        "body": (
            "Hello,\n\nWe have reviewed your billing and credit ledger. Your transaction has been reconciled "
            "and your account balance reflects the updated credits.\n\nPlease let us know if you need any "
            "additional assistance.\n\nWarm regards,\nSupport & Operations Desk"
        ),
        "is_system": 1,
    },
    {
        "title": "Report Regenerated",
        "category": "technical",
        "target_status": "resolved",
        "default_credits": 1.0,
        "body": (
            "Hello,\n\nWe noticed the report generation hiccup on your recent request. We have cleared the cache "
            "and credited your account so you can trigger a fresh evaluation right away.\n\n"
            "Warm regards,\nSupport & Operations Desk"
        ),
        "is_system": 1,
    },
]


def ensure_canned_responses_table() -> None:
    """Ensures the support_canned_responses table exists and seeds default templates if empty."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    is_pg = is_postgres_connection(conn)
    p = "%s" if is_pg else "?"
    try:
        if is_pg:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS support_canned_responses (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    target_status TEXT DEFAULT 'resolved',
                    default_credits REAL DEFAULT 0.0,
                    is_system INTEGER DEFAULT 0,
                    created_by TEXT DEFAULT 'admin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS support_canned_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    target_status TEXT DEFAULT 'resolved',
                    default_credits REAL DEFAULT 0.0,
                    is_system INTEGER DEFAULT 0,
                    created_by TEXT DEFAULT 'admin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')
        cursor.execute("SELECT COUNT(*) FROM support_canned_responses;")
        cnt_row = cursor.fetchone()
        cnt = cnt_row[0] if cnt_row else 0
        if cnt == 0:
            for item in DEFAULT_CANNED_RESPONSES:
                cursor.execute(
                    f'''
                    INSERT INTO support_canned_responses
                        (title, body, category, target_status, default_credits, is_system, created_by)
                    VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
                    ''',
                    (
                        item["title"],
                        item["body"],
                        item["category"],
                        item["target_status"],
                        float(item["default_credits"]),
                        int(item["is_system"]),
                        "system",
                    ),
                )
        conn.commit()
    except Exception as e:
        logger.error("Error ensuring support_canned_responses table: %s", e)
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug("Canned response table rollback failed: %s", rb_err)
    finally:
        cursor.close()
        conn.close()


def get_canned_responses() -> List[Dict[str, Any]]:
    """Returns all saved canned responses ordered by system defaults first, then newest custom templates."""
    ensure_canned_responses_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    results: List[Dict[str, Any]] = []
    try:
        cursor.execute('''
            SELECT id, title, body, category, target_status, default_credits, is_system, created_by, created_at
            FROM support_canned_responses
            ORDER BY is_system DESC, id ASC
        ''')
        for r in cursor.fetchall():
            results.append({
                "id": r[0],
                "title": r[1] or "Untitled Template",
                "body": r[2] or "",
                "category": r[3] or "general",
                "target_status": (r[4] or "resolved").lower().strip(),
                "default_credits": float(r[5] or 0.0),
                "is_system": bool(r[6]),
                "created_by": r[7] or "admin",
                "created_at": _format_timestamp(r[8]),
            })
    except Exception as e:
        logger.error("Error fetching canned responses: %s", e)
    finally:
        cursor.close()
        conn.close()
    return results


def save_canned_response(
    title: str,
    body: str,
    target_status: str = "resolved",
    default_credits: float = 0.0,
    category: str = "general",
    created_by: str = "admin",
    response_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Creates or updates a custom canned response template."""
    ensure_canned_responses_table()
    clean_title = str(title or "").strip()
    clean_body = str(body or "").strip()
    clean_status = str(target_status or "resolved").strip().lower()
    if clean_status not in ("open", "in_progress", "resolved", "closed"):
        clean_status = "resolved"
    clean_cat = str(category or "general").strip().lower()
    clean_credits = max(0.0, float(default_credits or 0.0))

    if not clean_title or not clean_body:
        return {"success": False, "error": "Both title and response message are required."}

    conn = get_db_connection()
    cursor = conn.cursor()
    is_pg = is_postgres_connection(conn)
    p = "%s" if is_pg else "?"
    try:
        if response_id:
            cursor.execute(
                f'''
                UPDATE support_canned_responses
                SET title = {p}, body = {p}, category = {p}, target_status = {p}, default_credits = {p}
                WHERE id = {p}
                ''',
                (clean_title, clean_body, clean_cat, clean_status, clean_credits, int(response_id)),
            )
            new_id = int(response_id)
        else:
            if is_pg:
                cursor.execute(
                    f'''
                    INSERT INTO support_canned_responses
                        (title, body, category, target_status, default_credits, is_system, created_by)
                    VALUES ({p}, {p}, {p}, {p}, {p}, 0, {p})
                    RETURNING id
                    ''',
                    (clean_title, clean_body, clean_cat, clean_status, clean_credits, str(created_by or "admin")),
                )
                row = cursor.fetchone()
                new_id = int(row[0]) if row else 0
            else:
                cursor.execute(
                    f'''
                    INSERT INTO support_canned_responses
                        (title, body, category, target_status, default_credits, is_system, created_by)
                    VALUES ({p}, {p}, {p}, {p}, {p}, 0, {p})
                    ''',
                    (clean_title, clean_body, clean_cat, clean_status, clean_credits, str(created_by or "admin")),
                )
                new_id = int(cursor.lastrowid or 0)
        conn.commit()
        return {
            "success": True,
            "canned_response": {
                "id": new_id,
                "title": clean_title,
                "body": clean_body,
                "category": clean_cat,
                "target_status": clean_status,
                "default_credits": clean_credits,
                "is_system": False,
                "created_by": str(created_by or "admin"),
            },
        }
    except Exception as e:
        logger.error("Error saving canned response '%s': %s", clean_title, e)
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug("Save canned response rollback failed: %s", rb_err)
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()


def delete_canned_response(response_id: int) -> Dict[str, Any]:
    """Deletes a canned response by ID."""
    ensure_canned_responses_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = "%s" if is_postgres_connection(conn) else "?"
    try:
        cursor.execute(f"DELETE FROM support_canned_responses WHERE id = {p};", (int(response_id),))
        conn.commit()
        return {"success": True, "deleted_id": int(response_id)}
    except Exception as e:
        logger.error("Error deleting canned response %s: %s", response_id, e)
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug("Delete canned response rollback failed: %s", rb_err)
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()


def delete_support_ticket(ticket_id: str) -> Dict[str, Any]:
    """Permanently deletes a spam/invalid support ticket and its associated response thread."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = "%s" if is_postgres_connection(conn) else "?"
    clean_tid = str(ticket_id or "").strip().upper()
    if not clean_tid:
        cursor.close()
        conn.close()
        return {"success": False, "error": "Ticket ID is required."}

    try:
        cursor.execute(f"DELETE FROM ticket_responses WHERE UPPER(ticket_id) = UPPER({p});", (clean_tid,))
        cursor.execute(f"DELETE FROM support_tickets WHERE UPPER(ticket_id) = UPPER({p});", (clean_tid,))
        deleted_rows = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        conn.commit()
        return {
            "success": True,
            "ticket_id": clean_tid,
            "deleted": deleted_rows > 0,
            "deleted_count": deleted_rows,
        }
    except Exception as e:
        logger.error("Error deleting support ticket %s: %s", clean_tid, e)
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug("Delete support ticket rollback failed: %s", rb_err)
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()


