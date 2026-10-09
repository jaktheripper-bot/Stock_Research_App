"""
core/db/admin.py
==============================================================================
Administrator Access Control, Whitelist, Roles & Immutable Audit Trail.
Dual-binding support for PostgreSQL (Supabase) and local SQLite.
==============================================================================
"""

import uuid
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

from core.db.connection import (
    init_db,
    get_db_connection,
    get_supabase_url,
    get_placeholder
)

logger = logging.getLogger("equity_research.core.db.admin")

DEFAULT_OWNER_EMAIL = "lyndnpnto@gmail.com"


def _clean_dict_row(cursor, row: Any) -> Dict[str, Any]:
    if not row:
        return {}
    if hasattr(cursor, "description") and cursor.description:
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))
    return {}


def get_admin_user(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve administrator record by email (case-insensitive)."""
    if not email:
        return None
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    clean_email = email.strip().lower()

    try:
        cursor.execute(
            f"SELECT * FROM admin_users WHERE LOWER(email) = LOWER({placeholder}) LIMIT 1;",
            (clean_email,)
        )
        row = cursor.fetchone()
        if row:
            return _clean_dict_row(cursor, row)
        return None
    except Exception as e:
        logger.error(f"Error fetching admin user '{clean_email}': {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def list_admin_users() -> List[Dict[str, Any]]:
    """List all registered administrators with their role and 2FA activation status."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM admin_users ORDER BY role = 'owner' DESC, created_at ASC;")
        rows = cursor.fetchall()
        return [_clean_dict_row(cursor, r) for r in rows]
    except Exception as e:
        logger.error(f"Error listing admin users: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def add_admin_user(email: str, role: str = "admin", invited_by: Optional[str] = None) -> Tuple[bool, str]:
    """Add a new administrator to the access whitelist."""
    clean_email = (email or "").strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return False, "Please provide a valid email address."

    clean_role = role.strip().lower()
    if clean_role not in ("owner", "admin", "viewer"):
        clean_role = "admin"

    existing = get_admin_user(clean_email)
    if existing:
        return False, f"Administrator with email '{clean_email}' already exists."

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    admin_id = f"adm_{uuid.uuid4().hex[:12]}"
    supabase_url = get_supabase_url()

    try:
        if supabase_url:
            cursor.execute(
                f"""
                INSERT INTO admin_users (id, email, role, totp_enabled, invited_by, created_at, updated_at)
                VALUES ({p}, {p}, {p}, FALSE, {p}, now(), now());
                """,
                (admin_id, clean_email, clean_role, invited_by)
            )
        else:
            cursor.execute(
                f"""
                INSERT INTO admin_users (id, email, role, totp_enabled, invited_by)
                VALUES ({p}, {p}, {p}, 0, {p});
                """,
                (admin_id, clean_email, clean_role, invited_by)
            )
        conn.commit()
        return True, f"Administrator '{clean_email}' added successfully with role '{clean_role}'."
    except Exception as e:
        logger.error(f"Error adding admin user '{clean_email}': {e}")
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug(f"Rollback failed: {rb_err}")
        return False, f"Database error adding administrator: {e}"
    finally:
        cursor.close()
        conn.close()


def remove_admin_user(email: str, requesting_email: str) -> Tuple[bool, str]:
    """Remove an administrator from the whitelist. Enforces owner protection."""
    clean_email = (email or "").strip().lower()
    clean_req = (requesting_email or "").strip().lower()

    target = get_admin_user(clean_email)
    if not target:
        return False, "Administrator not found."

    if target.get("role") == "owner" and clean_email == DEFAULT_OWNER_EMAIL.lower():
        return False, "The root platform owner account cannot be deleted."

    if clean_email == clean_req:
        return False, "You cannot remove your own administrator account."

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        cursor.execute(f"DELETE FROM admin_users WHERE LOWER(email) = LOWER({p});", (clean_email,))
        conn.commit()
        return True, f"Administrator '{clean_email}' has been removed."
    except Exception as e:
        logger.error(f"Error deleting admin user '{clean_email}': {e}")
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug(f"Rollback failed: {rb_err}")
        return False, f"Failed to delete administrator: {e}"
    finally:
        cursor.close()
        conn.close()


def update_admin_role(email: str, new_role: str, requesting_email: str) -> Tuple[bool, str]:
    """Update role for an administrator."""
    clean_email = (email or "").strip().lower()
    clean_role = new_role.strip().lower()

    if clean_role not in ("owner", "admin", "viewer"):
        return False, "Invalid role. Must be 'owner', 'admin', or 'viewer'."

    target = get_admin_user(clean_email)
    if not target:
        return False, "Administrator not found."

    if target.get("role") == "owner" and clean_email == DEFAULT_OWNER_EMAIL.lower() and clean_role != "owner":
        return False, "The root platform owner role cannot be downgraded."

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    supabase_url = get_supabase_url()

    try:
        if supabase_url:
            cursor.execute(
                f"UPDATE admin_users SET role = {p}, updated_at = now() WHERE LOWER(email) = LOWER({p});",
                (clean_role, clean_email)
            )
        else:
            cursor.execute(
                f"UPDATE admin_users SET role = {p}, updated_at = datetime('now') WHERE LOWER(email) = LOWER({p});",
                (clean_role, clean_email)
            )
        conn.commit()
        return True, f"Updated role for '{clean_email}' to '{clean_role}'."
    except Exception as e:
        logger.error(f"Error updating role for '{clean_email}': {e}")
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug(f"Rollback failed: {rb_err}")
        return False, f"Failed to update role: {e}"
    finally:
        cursor.close()
        conn.close()


def set_admin_totp_secret(email: str, secret: str) -> bool:
    """Stores the pending Base32 TOTP secret for an admin."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    clean_email = email.strip().lower()

    try:
        cursor.execute(
            f"UPDATE admin_users SET totp_secret = {p} WHERE LOWER(email) = LOWER({p});",
            (secret, clean_email)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error updating TOTP secret for '{clean_email}': {e}")
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug(f"Rollback failed: {rb_err}")
        return False
    finally:
        cursor.close()
        conn.close()


def enable_admin_totp(email: str) -> bool:
    """Marks TOTP 2FA as fully activated after successful code confirmation."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    clean_email = email.strip().lower()
    supabase_url = get_supabase_url()

    try:
        if supabase_url:
            cursor.execute(
                f"UPDATE admin_users SET totp_enabled = TRUE, updated_at = now() WHERE LOWER(email) = LOWER({p});",
                (clean_email,)
            )
        else:
            cursor.execute(
                f"UPDATE admin_users SET totp_enabled = 1, updated_at = datetime('now') WHERE LOWER(email) = LOWER({p});",
                (clean_email,)
            )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error enabling TOTP for '{clean_email}': {e}")
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug(f"Rollback failed: {rb_err}")
        return False
    finally:
        cursor.close()
        conn.close()


def update_admin_last_login(email: str):
    """Updates last_login_at timestamp on successful 2FA verification."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    clean_email = email.strip().lower()
    supabase_url = get_supabase_url()

    try:
        if supabase_url:
            cursor.execute(
                f"UPDATE admin_users SET last_login_at = now() WHERE LOWER(email) = LOWER({p});",
                (clean_email,)
            )
        else:
            cursor.execute(
                f"UPDATE admin_users SET last_login_at = datetime('now') WHERE LOWER(email) = LOWER({p});",
                (clean_email,)
            )
        conn.commit()
    except Exception as e:
        logger.warning(f"Error recording last login for '{clean_email}': {e}")
    finally:
        cursor.close()
        conn.close()


def record_admin_audit(
    admin_email: str,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> bool:
    """Appends an immutable audit event to admin_audit_log."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    audit_id = f"aud_{uuid.uuid4().hex[:14]}"
    details_str = json.dumps(details or {}, ensure_ascii=False)
    supabase_url = get_supabase_url()

    try:
        if supabase_url:
            cursor.execute(
                f"""
                INSERT INTO admin_audit_log (id, admin_email, action, target_type, target_id, details, ip_address, user_agent, created_at)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, now());
                """,
                (audit_id, admin_email, action, target_type, target_id, details_str, ip_address, user_agent)
            )
        else:
            cursor.execute(
                f"""
                INSERT INTO admin_audit_log (id, admin_email, action, target_type, target_id, details, ip_address, user_agent)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
                """,
                (audit_id, admin_email, action, target_type, target_id, details_str, ip_address, user_agent)
            )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error appending admin audit log: {e}")
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug(f"Rollback failed: {rb_err}")
        return False
    finally:
        cursor.close()
        conn.close()


def get_admin_audit_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve recent admin actions from the immutable audit log."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()

    try:
        cursor.execute(
            f"SELECT * FROM admin_audit_log ORDER BY created_at DESC LIMIT {p};",
            (limit,)
        )
        rows = cursor.fetchall()
        items = []
        for r in rows:
            d = _clean_dict_row(cursor, r)
            if d.get("details"):
                try:
                    d["details_parsed"] = json.loads(d["details"])
                except Exception:
                    d["details_parsed"] = {}
            items.append(d)
        return items
    except Exception as e:
        logger.error(f"Error reading admin audit logs: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def admin_grant_user_credits(
    admin_email: str,
    target_user_identifier: str,
    credits_amount: float,
    reason_code: str = "TASK_REMEDY",
    admin_note: str = "",
    ticket_id: Optional[str] = None,
    task_ticker: Optional[str] = None,
    resolve_ticket: bool = True,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Dict[str, Any]:
    """
    Atomically grants remedial or promotional research credits to a user account.

    1. Updates user_accounts (credits_balance += credits_amount).
    2. Inserts isolated zero-revenue ledger record into credit_transactions (nature: FREE_GRANT, amount: 0.0).
    3. Records ledger transaction in credit_usage_ledger.
    4. Appends immutable event to admin_audit_log (action: GRANT_USER_CREDITS).
    5. Optionally marks linked support_tickets record as resolved and appends resolution note.

    Dual-binding support for SQLite and PostgreSQL.
    """
    clean_admin = (admin_email or "").strip().lower()
    clean_target = (target_user_identifier or "").strip().lower()

    if not clean_target:
        return {"success": False, "error": "Target user email or user ID is required."}

    try:
        credits_val = round(float(credits_amount), 2)
        if credits_val <= 0:
            return {"success": False, "error": "Credits amount must be greater than zero."}
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid credits amount."}

    clean_reason = (reason_code or "TASK_REMEDY").strip().upper().replace(" ", "_")
    clean_ticket = (ticket_id or "").strip() if ticket_id else None
    clean_ticker = (task_ticker or "").strip().upper() if task_ticker else None

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    supabase_url = get_supabase_url()

    try:
        # Step 0: Locate target user account
        cursor.execute(
            f"SELECT id, email, full_name, credits_balance FROM user_accounts WHERE LOWER(email) = LOWER({p}) OR id = {p} LIMIT 1;",
            (clean_target, clean_target)
        )
        user_row = cursor.fetchone()
        if not user_row:
            return {"success": False, "error": f"User '{target_user_identifier}' not found in registered accounts."}

        user_id = user_row[0]
        user_email = user_row[1]
        user_name = user_row[2] or "Investor"
        old_balance = float(user_row[3] or 0.0)
        new_balance = round(old_balance + credits_val, 2)

        # Step 1: Update user_accounts balance
        cursor.execute(
            f"UPDATE user_accounts SET credits_balance = credits_balance + {p} WHERE id = {p};",
            (credits_val, user_id)
        )

        # Step 2: Insert into credit_transactions (Isolated zero-revenue ledger entry)
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        tx_id = f"tx_grant_{user_id[:8]}_{now_epoch}_{uuid.uuid4().hex[:6]}"
        inv_num = f"INV-GRANT-{uuid.uuid4().hex[:8].upper()}"
        pack_type = f"ADMIN_GRANT_{clean_reason}"

        if supabase_url:
            cursor.execute(
                f"""
                INSERT INTO credit_transactions (
                    id, user_id, customer_email, customer_name, amount_inr, credits_added,
                    payment_gateway, gateway_order_id, gateway_payment_id, status, pack_type,
                    invoice_number, base_amount_inr, tax_gst_inr, sac_code, created_at
                )
                VALUES ({p}, {p}, {p}, {p}, 0.0, {p}, 'admin_grant', {p}, {p}, 'success', {p}, {p}, 0.0, 0.0, '', now());
                """,
                (tx_id, user_id, user_email, user_name, credits_val, clean_ticket or "ADMIN_GRANT", f"grant_by_{clean_admin}", pack_type, inv_num)
            )
            # Insert into credit_usage_ledger
            cursor.execute(
                f"""
                INSERT INTO credit_usage_ledger (user_id, ticker, action_type, credits_consumed, balance_after, created_at)
                VALUES ({p}, {p}, {p}, 0.0, {p}, now());
                """,
                (user_id, clean_ticker or "PLATFORM", pack_type, new_balance)
            )
        else:
            cursor.execute(
                f"""
                INSERT INTO credit_transactions (
                    id, user_id, customer_email, customer_name, amount_inr, credits_added,
                    payment_gateway, gateway_order_id, gateway_payment_id, status, pack_type,
                    invoice_number, base_amount_inr, tax_gst_inr, sac_code, created_at
                )
                VALUES ({p}, {p}, {p}, {p}, 0.0, {p}, 'admin_grant', {p}, {p}, 'success', {p}, {p}, 0.0, 0.0, '', datetime('now'));
                """,
                (tx_id, user_id, user_email, user_name, credits_val, clean_ticket or "ADMIN_GRANT", f"grant_by_{clean_admin}", pack_type, inv_num)
            )
            # Insert into credit_usage_ledger
            cursor.execute(
                f"""
                INSERT INTO credit_usage_ledger (user_id, ticker, action_type, credits_consumed, balance_after)
                VALUES ({p}, {p}, {p}, 0.0, {p});
                """,
                (user_id, clean_ticker or "PLATFORM", pack_type, new_balance)
            )

        # Step 3: Append immutable admin_audit_log event
        audit_id = f"aud_{uuid.uuid4().hex[:14]}"
        audit_details = {
            "user_email": user_email,
            "user_id": user_id,
            "credits_granted": credits_val,
            "old_balance": old_balance,
            "new_balance": new_balance,
            "reason_code": clean_reason,
            "admin_note": admin_note,
            "ticket_id": clean_ticket,
            "task_ticker": clean_ticker,
            "nature": "FREE_GRANT",
            "amount_inr": 0.0
        }
        details_json = json.dumps(audit_details, ensure_ascii=False)

        if supabase_url:
            cursor.execute(
                f"""
                INSERT INTO admin_audit_log (id, admin_email, action, target_type, target_id, details, ip_address, user_agent, created_at)
                VALUES ({p}, {p}, 'GRANT_USER_CREDITS', 'user', {p}, {p}, {p}, {p}, now());
                """,
                (audit_id, clean_admin, user_id, details_json, ip_address, user_agent)
            )
        else:
            cursor.execute(
                f"""
                INSERT INTO admin_audit_log (id, admin_email, action, target_type, target_id, details, ip_address, user_agent)
                VALUES ({p}, {p}, 'GRANT_USER_CREDITS', 'user', {p}, {p}, {p}, {p});
                """,
                (audit_id, clean_admin, user_id, details_json, ip_address, user_agent)
            )

        # Step 4: (Optional) Update support ticket if ticket_id provided
        if clean_ticket:
            cursor.execute(
                f"SELECT status, admin_notes FROM support_tickets WHERE ticket_id = {p};",
                (clean_ticket,)
            )
            t_row = cursor.fetchone()
            if t_row:
                curr_status = t_row[0] or "open"
                prev_notes = t_row[1] or ""
                remedy_text = f"[Admin Credits Granted: +{credits_val} by {clean_admin}. Reason: {clean_reason}]"
                new_notes = f"{prev_notes}\n{remedy_text} {admin_note}".strip() if prev_notes else f"{remedy_text} {admin_note}".strip()
                final_status = "resolved" if resolve_ticket else curr_status

                if supabase_url:
                    cursor.execute(
                        f"UPDATE support_tickets SET status = {p}, admin_notes = {p}, updated_at = now() WHERE ticket_id = {p};",
                        (final_status, new_notes, clean_ticket)
                    )
                else:
                    cursor.execute(
                        f"UPDATE support_tickets SET status = {p}, admin_notes = {p}, updated_at = datetime('now') WHERE ticket_id = {p};",
                        (final_status, new_notes, clean_ticket)
                    )

        conn.commit()
        logger.info(f"Admin '{clean_admin}' successfully granted {credits_val} credits to {user_email} (New balance: {new_balance})")
        return {
            "success": True,
            "user_id": user_id,
            "user_email": user_email,
            "credits_added": credits_val,
            "old_balance": old_balance,
            "new_balance": new_balance,
            "ticket_id": clean_ticket,
            "reason_code": clean_reason,
            "message": f"Successfully granted {credits_val} credits to {user_email}."
        }
    except Exception as e:
        logger.error(f"Error granting credits to '{clean_target}': {e}", exc_info=True)
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug(f"Rollback failed: {rb_err}")
        return {"success": False, "error": f"Database error during credit grant: {e}"}
    finally:
        cursor.close()
        conn.close()

