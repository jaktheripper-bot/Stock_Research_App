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
        except Exception:
            pass
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
        except Exception:
            pass
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
        except Exception:
            pass
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
        except Exception:
            pass
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
        except Exception:
            pass
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
        except Exception:
            pass
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
