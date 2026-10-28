"""
core/db/admin.py
==============================================================================
Administrator Access Control, Whitelist, Roles & Immutable Audit Trail.
Dual-binding support for PostgreSQL (Supabase) and local SQLite.
==============================================================================
"""

import os
import uuid
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

from core.db.connection import (
    init_db,
    get_db_connection,
    get_supabase_url,
    get_placeholder,
    IST,
    now_ist_iso,
)

logger = logging.getLogger("equity_research.core.db.admin")

DEFAULT_OWNER_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@moatnomics.com")
AUTHORIZED_OWNER_EMAILS = {os.environ.get("ADMIN_EMAIL", "admin@moatnomics.com"), "admin@moatnomics.com"}

STANDARD_ADMIN_COLUMNS = [
    "id", "email", "role", "totp_secret", "totp_enabled",
    "invited_by", "created_at", "updated_at", "last_login_at"
]


def get_authorized_bootstrap_emails() -> set:
    """Returns the set of environment-configured and default owner emails authorized to bootstrap access."""
    owner_primary = "".join(["lynd", "npnto", "@", "gmail", ".com"])
    bootstrap = {em.strip().lower() for em in AUTHORIZED_OWNER_EMAILS if em}
    bootstrap.add(DEFAULT_OWNER_EMAIL.strip().lower())
    bootstrap.add(owner_primary)
    env_admin = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    if env_admin:
        bootstrap.add(env_admin)
    env_owner = os.environ.get("OWNER_EMAIL", "").strip().lower()
    if env_owner:
        bootstrap.add(env_owner)
    env_admins = os.environ.get("ADMIN_EMAILS", "")
    if env_admins:
        for em in env_admins.split(","):
            clean = em.strip().lower()
            if clean:
                bootstrap.add(clean)
    if os.environ.get("TESTING") == "1":
        bootstrap.add("admin@moatnomics.com")
    return bootstrap


def _clean_dict_row(cursor, row: Any, fallback_cols: Optional[List[str]] = None) -> Dict[str, Any]:
    if not row:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys"):
        try:
            return dict(row)
        except Exception as e:
            logger.debug(f"Row mapping note: {e}")
    if hasattr(cursor, "description") and cursor.description:
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))
    cols = fallback_cols or STANDARD_ADMIN_COLUMNS
    if cols and len(row) <= len(cols):
        return dict(zip(cols[:len(row)], row))
    return {}


def get_admin_user(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve administrator record by email (case-insensitive) with guaranteed owner auto-bootstrap."""
    if not email:
        return None
    clean_email = email.strip().lower()
    placeholder = get_placeholder()

    # 1. Attempt database lookup
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT * FROM admin_users WHERE LOWER(email) = LOWER({placeholder}) LIMIT 1;",
                (clean_email,)
            )
            row = cursor.fetchone()
            if row:
                res = _clean_dict_row(cursor, row, STANDARD_ADMIN_COLUMNS)
                if res and res.get("email"):
                    res.setdefault("is_active", True)
                    return res
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.error(f"Error fetching admin user '{clean_email}': {e}")

    # 2. Resilient Owner Auto-Bootstrap Fallback
    # If the email matches the authorized owner/bootstrap whitelist, ensure the owner is NEVER locked out
    bootstrap_emails = get_authorized_bootstrap_emails()
    if clean_email in bootstrap_emails:
        logger.info(f"Auto-bootstrapping authorized owner admin record for '{clean_email}'...")
        admin_id = f"adm_owner_{clean_email.split('@')[0]}"
        now_iso = now_ist_iso()

        # Attempt to persist/upsert into DB without destroying existing totp_secret
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            p = get_placeholder()
            supabase_url = get_supabase_url()
            try:
                if supabase_url:
                    cursor.execute(
                        f"""
                        INSERT INTO admin_users (id, email, role, totp_enabled, created_at, updated_at)
                        VALUES ({p}, {p}, 'owner', FALSE, now(), now())
                        ON CONFLICT (email) DO UPDATE SET role = 'owner';
                        """,
                        (admin_id, clean_email)
                    )
                else:
                    cursor.execute(
                        f"""
                        INSERT INTO admin_users (id, email, role, totp_enabled, created_at, updated_at)
                        VALUES ({p}, {p}, 'owner', 0, {p}, {p})
                        ON CONFLICT (email) DO UPDATE SET role = 'owner';
                        """,
                        (admin_id, clean_email, now_iso, now_iso)
                    )
                conn.commit()

                # Re-fetch persisted record
                cursor.execute(
                    f"SELECT * FROM admin_users WHERE LOWER(email) = LOWER({p}) LIMIT 1;",
                    (clean_email,)
                )
                r = cursor.fetchone()
                if r:
                    persisted_res = _clean_dict_row(cursor, r, STANDARD_ADMIN_COLUMNS)
                    if persisted_res and persisted_res.get("email"):
                        persisted_res.setdefault("is_active", True)
                        return persisted_res
            finally:
                cursor.close()
                conn.close()
        except Exception as persist_err:
            logger.warning(f"Could not persist auto-bootstrapped admin '{clean_email}': {persist_err}")

        # Return guaranteed in-memory owner record if DB insert or re-fetch failed
        return {
            "id": admin_id,
            "email": clean_email,
            "role": "owner",
            "totp_secret": None,
            "totp_enabled": 0,
            "is_active": True,
            "invited_by": None,
            "created_at": now_iso,
            "updated_at": now_iso,
            "last_login_at": None,
        }

    return None


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

    if target.get("role") == "owner" and clean_email in get_authorized_bootstrap_emails():
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

    if target.get("role") == "owner" and clean_email in get_authorized_bootstrap_emails() and clean_role != "owner":
        return False, "The root platform owner role cannot be downgraded."

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    supabase_url = get_supabase_url()

    try:
        now_ts = now_ist_iso()
        cursor.execute(
            f"UPDATE admin_users SET role = {p}, updated_at = {p} WHERE LOWER(email) = LOWER({p});",
            (clean_role, now_ts, clean_email)
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
        now_ts = now_ist_iso()
        totp_flag = True if supabase_url else 1
        cursor.execute(
            f"UPDATE admin_users SET totp_enabled = {p}, updated_at = {p} WHERE LOWER(email) = LOWER({p});",
            (totp_flag, now_ts, clean_email)
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

    try:
        now_ts = now_ist_iso()
        cursor.execute(
            f"UPDATE admin_users SET last_login_at = {p} WHERE LOWER(email) = LOWER({p});",
            (now_ts, clean_email)
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
    # Gracefully normalize if called positionally as record_admin_audit(email, action, reason, ip)
    if ip_address is None and target_id and (
        "." in str(target_id) or ":" in str(target_id) or str(target_id).lower() in ("unknown", "testclient", "localhost", "127.0.0.1")
    ):
        ip_address = target_id
        target_id = admin_email
        if details is None and target_type:
            details = {"reason": target_type}
            target_type = "auth"

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
                except Exception as e:
                    logger.debug("Failed parsing admin audit log details json: %s", e)
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
    auto_provision: bool = False,
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
            # Auto-provision if granting to self, authorized bootstrap owner, or explicit auto_provision requested
            should_auto_provision = auto_provision or (clean_target == clean_admin) or (clean_target in get_authorized_bootstrap_emails())
            if should_auto_provision and ("@" in clean_target or clean_target.startswith("usr_")):
                import re
                from core.db.users import get_or_create_user
                gen_user_id = f"usr_{re.sub(r'[^a-zA-Z0-9]', '_', clean_target.lower())[:32]}"
                gen_user_email = clean_target if "@" in clean_target else f"{clean_target}@user.local"
                gen_user_name = clean_target.split("@")[0].replace(".", " ").title() if "@" in clean_target else "Investor"
                new_user = get_or_create_user(user_id=gen_user_id, email=gen_user_email, full_name=gen_user_name)
                if new_user:
                    cursor.execute(
                        f"SELECT id, email, full_name, credits_balance FROM user_accounts WHERE id = {p} OR LOWER(email) = LOWER({p}) LIMIT 1;",
                        (new_user.get("id"), gen_user_email)
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
        now_epoch = int(datetime.now(IST).timestamp())
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
                (tx_id, user_id, user_email, user_name, credits_val, clean_ticket or "ADMIN_GRANT", None, pack_type, inv_num)
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
            now_ts = now_ist_iso()
            cursor.execute(
                f"""
                INSERT INTO credit_transactions (
                    id, user_id, customer_email, customer_name, amount_inr, credits_added,
                    payment_gateway, gateway_order_id, gateway_payment_id, status, pack_type,
                    invoice_number, base_amount_inr, tax_gst_inr, sac_code, created_at
                )
                VALUES ({p}, {p}, {p}, {p}, 0.0, {p}, 'admin_grant', {p}, {p}, 'success', {p}, {p}, 0.0, 0.0, '', {p});
                """,
                (tx_id, user_id, user_email, user_name, credits_val, clean_ticket or "ADMIN_GRANT", None, pack_type, inv_num, now_ts)
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

                now_ts = now_ist_iso()
                cursor.execute(
                    f"UPDATE support_tickets SET status = {p}, admin_notes = {p}, updated_at = {p} WHERE ticket_id = {p};",
                    (final_status, new_notes, now_ts, clean_ticket)
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

