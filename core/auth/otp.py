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
import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Dict, Any

from core.db.connection import get_db_connection, get_supabase_url, get_placeholder

logger = logging.getLogger("equity_research.core.auth.otp")

OTP_TTL_MINUTES = 10
MAX_VERIFICATION_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


def _hash_otp(email: str, code: str) -> str:
    salt = os.environ.get("ADMIN_API_KEY", "stock_research_otp_salt_2026")
    payload = f"{email.strip().lower()}:{code.strip()}:{salt}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_email_otp(email: str) -> Tuple[bool, str, Optional[str]]:
    """
    Generates and persists a fresh 6-digit OTP for the given email.
    Returns:
        (success, message, code_or_none)
        In development/testing, returns code to facilitate mock testing.
    """
    clean_email = (email or "").strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return False, "Please provide a valid email address.", None

    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    is_pg = bool(get_supabase_url())
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(minutes=OTP_TTL_MINUTES)

    # 1. Check existing record for rate-limiting
    try:
        cursor.execute(f"SELECT otp_hash, expires_at, created_at FROM auth_otps WHERE email = {p};", (clean_email,))
        row = cursor.fetchone()
        if row:
            created_at = row[2]
            if isinstance(created_at, str):
                try:
                    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if created_dt.tzinfo is None:
                        created_dt = created_dt.replace(tzinfo=timezone.utc)
                    elapsed = (now_utc - created_dt).total_seconds()
                    if elapsed < RESEND_COOLDOWN_SECONDS and os.environ.get("TESTING") != "1":
                        remaining = int(RESEND_COOLDOWN_SECONDS - elapsed)
                        return False, f"Please wait {remaining} seconds before requesting a new code.", None
                except Exception as parse_err:
                    logger.debug("OTP created_at parse error: %s", parse_err)
            elif isinstance(created_at, datetime):
                created_dt = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
                elapsed = (now_utc - created_dt).total_seconds()
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
    created_str = now_utc.isoformat()

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
            cursor.execute(query, (clean_email, otp_hash, expires_at, now_utc))
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
    cursor = conn.cursor()
    p = get_placeholder()
    now_utc = datetime.now(timezone.utc)

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
        is_expired = False
        if isinstance(expires_at, str):
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if now_utc > exp_dt:
                    is_expired = True
            except Exception:
                is_expired = False
        elif isinstance(expires_at, datetime):
            exp_dt = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
            if now_utc > exp_dt:
                is_expired = True

        if is_expired:
            _delete_otp(clean_email)
            return False, "Verification code has expired. Please request a new code."

        # 3. Check hash
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
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()
        cursor.execute(f"DELETE FROM auth_otps WHERE email = {p};", (email,))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Error deleting OTP for {email}: {e}")
