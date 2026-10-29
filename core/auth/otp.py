"""
core/auth/otp.py
==============================================================================
Secure Email OTP Generation, Storage, Rate-Limiting & Verification Engine.

Stores salted cryptographic hashes of OTP codes in the `auth_otps` table.
Features:
- 6-digit cryptographically secure random codes (secrets.randbelow)
- Salted SHA-256 hash storage (plain codes are never stored in DB)
- 10-minute expiry time-to-live (TTL)
- Max 5 verification attempts per code to prevent brute-force
- Rate limit: 60-second cooldown between code requests per email
- Test isolation support: accepts mock code '123456' when TESTING=1
==============================================================================
"""

import os
import secrets
import hashlib
import hmac
import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Dict, Any

from core.config import get_secret
from core.db.connection import get_db_connection, is_postgres_connection, IST
from core.notify import send_otp_email
from core.presentation.formatters import _coerce_datetime

logger = logging.getLogger("equity_research.core.auth.otp")

OTP_TTL_MINUTES = 10
MAX_VERIFICATION_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60

DISPOSABLE_EMAIL_DOMAINS = frozenset({
    "nolettersbox.com",
    "mailinator.com",
    "guerrillamail.com",
    "tempmail.com",
    "10minutemail.com",
    "yopmail.com",
    "trashmail.com",
    "sharklasers.com",
    "dispostable.com",
    "maildrop.cc",
    "temp-mail.org",
    "fakeinbox.com",
    "getnada.com",
    "mohmal.com",
    "throwawaymail.com",
    "geiiml.my.id",
    "tehbo.my.id",
    "smaqty.com",
})

DISPOSABLE_EMAIL_SUFFIXES = (
    ".my.id",
)


def is_disposable_or_bot_email(email: str) -> bool:
    """Returns True if email is malformed or belongs to a disposable/burner spam domain."""
    clean = (email or "").strip().lower()
    if "@" not in clean:
        return True
    domain = clean.rsplit("@", 1)[-1]
    if not domain or "." not in domain:
        return True
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        return True
    if any(domain.endswith(sfx) for sfx in DISPOSABLE_EMAIL_SUFFIXES):
        return True
    return False


def _resolve_otp_secret() -> bytes:
    """Resolves a deterministic cross-worker HMAC secret (never using os.getpid())."""
    raw = (
        os.environ.get("OTP_HMAC_SECRET")
        or get_secret("OTP_HMAC_SECRET")
        or os.environ.get("SECRET_KEY")
        or get_secret("SECRET_KEY")
        or os.environ.get("ADMIN_API_KEY")
        or get_secret("ADMIN_API_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or get_secret("SUPABASE_SERVICE_ROLE_KEY")
        or "moatnomics_deterministic_otp_hmac_salt_2026"
    )
    return str(raw).strip().encode("utf-8")


OTP_HMAC_SECRET = _resolve_otp_secret()


def _hash_otp(email: str, code: str) -> str:
    secret = _resolve_otp_secret()
    payload = f"{email.strip().lower()}:{code.strip()}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def create_email_otp(email: str) -> Tuple[bool, str, Optional[str]]:
    """
    Generates, persists, and dispatches a fresh 6-digit OTP for the given email.
    Returns:
        (success, message, code_or_none)
        In development/testing, returns code to facilitate mock testing.
    """
    clean_email = (email or "").strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return False, "Please provide a valid email address.", None
    if is_disposable_or_bot_email(clean_email):
        logger.warning("Blocked OTP generation for disposable/burner email domain: %s", clean_email)
        return False, "Temporary or disposable email domains are not permitted. Please use your primary work or personal email.", None

    conn = get_db_connection()
    is_pg = is_postgres_connection(conn)
    p = "%s" if is_pg else "?"
    cursor = conn.cursor()
    now_ist = datetime.now(IST)
    expires_at = now_ist + timedelta(minutes=OTP_TTL_MINUTES)

    # 1. Check existing record for rate-limiting
    try:
        cursor.execute(f"SELECT otp_hash, expires_at, created_at FROM auth_otps WHERE email = {p};", (clean_email,))
        row = cursor.fetchone()
        if row:
            created_at = row[2]
            created_dt = _coerce_datetime(created_at)
            if created_dt is not None:
                elapsed = (now_ist - created_dt).total_seconds()
                if elapsed < RESEND_COOLDOWN_SECONDS and os.environ.get("TESTING") != "1":
                    remaining = int(RESEND_COOLDOWN_SECONDS - elapsed)
                    return False, f"Please wait {remaining} seconds before requesting a new code.", None
    except Exception as e:
        logger.warning(f"Error checking existing OTP for {clean_email}: {e}")

    # 2. Generate code
    if os.environ.get("TESTING") == "1":
        code = "123456"
    else:
        code = f"{secrets.randbelow(900000) + 100000}"

    otp_hash = _hash_otp(clean_email, code)
    expires_str = expires_at.isoformat()
    created_str = now_ist.isoformat()

    try:
        if is_pg:
            query = f"""
                INSERT INTO auth_otps (email, otp_hash, expires_at, attempts, created_at)
                VALUES ({p}, {p}, {p}, 0, {p})
                ON CONFLICT (email) DO UPDATE SET
                    otp_hash = EXCLUDED.otp_hash,
                    expires_at = EXCLUDED.expires_at,
                    attempts = 0,
                    created_at = EXCLUDED.created_at;
            """
            cursor.execute(query, (clean_email, otp_hash, expires_at, now_ist))
        else:
            query = f"""
                INSERT INTO auth_otps (email, otp_hash, expires_at, attempts, created_at)
                VALUES ({p}, {p}, {p}, 0, {p})
                ON CONFLICT (email) DO UPDATE SET
                    otp_hash = excluded.otp_hash,
                    expires_at = excluded.expires_at,
                    attempts = 0,
                    created_at = excluded.created_at;
            """
            cursor.execute(query, (clean_email, otp_hash, expires_str, created_str))

        conn.commit()
        logger.info(f"Generated secure OTP for {clean_email}")

        from core.notify import _is_live_email_dispatch_allowed, _is_test_runtime
        if not _is_test_runtime() and _is_live_email_dispatch_allowed():
            # Primary: Standardized Supabase GoTrue Auth OTP / Magic Link dispatch
            sb_dispatched = False
            try:
                from core.auth.supabase_auth import send_magic_link
                canonical = (os.environ.get("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")
                sb_ok, _ = send_magic_link(clean_email, redirect_uri=f"{canonical}/auth/callback")
                if sb_ok:
                    sb_dispatched = True
            except Exception as sb_err:
                logger.debug(f"Supabase GoTrue OTP dispatch fallback notice for {clean_email}: {sb_err}")

            if not sb_dispatched:
                send_otp_email(clean_email, code, ttl_minutes=OTP_TTL_MINUTES)
        elif not _is_test_runtime():
            logger.info(
                "[IDE/TEST EMAIL GUARD] Local OTP generated for %s (Code: %s). "
                "Live Supabase/Resend email skipped in IDE.",
                clean_email,
                code,
            )

        return True, "Verification code sent successfully to your email.", code
    except Exception as e:
        logger.error(f"Error saving OTP for {clean_email}: {e}")
        conn.rollback()
        return False, "Could not generate verification code. Please try again.", None
    finally:
        cursor.close()
        conn.close()


def verify_email_otp(email: str, code: str) -> Tuple[bool, str]:
    """
    Validates a submitted OTP code against the persistent salted hash.
    Enforces expiry (10 min) and max attempts (5).
    Deletes the OTP record upon successful validation.
    """
    clean_email = (email or "").strip().lower()
    clean_code = (code or "").strip()

    if not clean_email or not clean_code:
        return False, "Email and verification code are required."

    conn = get_db_connection()
    is_pg = is_postgres_connection(conn)
    p = "%s" if is_pg else "?"
    cursor = conn.cursor()
    now_ist = datetime.now(IST)

    try:
        cursor.execute(f"SELECT otp_hash, expires_at, attempts FROM auth_otps WHERE email = {p};", (clean_email,))
        row = cursor.fetchone()
        if not row:
            return False, "No verification code found. Please request a new code."

        # Allow test code in testing environment if an active OTP was issued
        if os.environ.get("TESTING") == "1" and clean_code == "123456":
            _delete_otp(clean_email)
            return True, "Code verified successfully."

        stored_hash, expires_at, attempts = row[0], row[1], int(row[2] or 0)

        # 1. Check max attempts
        if attempts >= MAX_VERIFICATION_ATTEMPTS:
            _delete_otp(clean_email)
            return False, "Too many failed attempts. This code has been invalidated. Please request a new one."

        # 2. Check expiry
        exp_dt = _coerce_datetime(expires_at)
        is_expired = bool(exp_dt is not None and now_ist > exp_dt)

        if is_expired:
            _delete_otp(clean_email)
            return False, "Verification code has expired. Please request a new code."

        # 3. Primary: Standardized Supabase GoTrue OTP verification (in production)
        if os.environ.get("TESTING") != "1":
            try:
                from core.auth.supabase_auth import verify_supabase_otp_token
                sb_valid, _, _, _ = verify_supabase_otp_token(clean_email, clean_code)
                if sb_valid:
                    _delete_otp(clean_email)
                    return True, "Code verified successfully."
            except Exception as sb_v_err:
                logger.debug(f"Supabase GoTrue OTP verification fallback notice for {clean_email}: {sb_v_err}")

        # 4. Secondary / Local Hash Verification
        expected_hash = _hash_otp(clean_email, clean_code)
        if secrets.compare_digest(stored_hash, expected_hash):
            _delete_otp(clean_email)
            return True, "Code verified successfully."
        else:
            cursor.execute(f"UPDATE auth_otps SET attempts = attempts + 1 WHERE email = {p};", (clean_email,))
            conn.commit()
            remaining = MAX_VERIFICATION_ATTEMPTS - (attempts + 1)
            return False, f"Invalid verification code. {remaining} attempt(s) remaining."
    except Exception as e:
        logger.error(f"Error verifying OTP for {clean_email}: {e}")
        return False, "Verification failed due to a system error."
    finally:
        cursor.close()
        conn.close()


def _delete_otp(email: str):
    """Purges OTP record after successful use or invalidation."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        is_pg = is_postgres_connection(conn)
        p = "%s" if is_pg else "?"
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM auth_otps WHERE email = {p};", (email,))
        conn.commit()
    except Exception as e:
        logger.warning(f"Error deleting OTP for {email}: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                logger.debug(f"Cursor close notice in _delete_otp: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.debug(f"Connection close notice in _delete_otp: {e}")

