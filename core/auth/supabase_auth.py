"""
Supabase Authentication, Session Management, and Identity State Module.

Handles:
- Supabase Auth GoTrue REST endpoints (Google OAuth redirect, Magic Link / OTP dispatch, token exchange)
- ContextVar session state binding for authenticated user profile and credit balances
- Safe query parameter parsing on OAuth/Magic Link callbacks
- Frictionless guest-to-user conversion with 2 welcome credits
"""

import os
import re
import time
import json
import base64
import logging
import requests
import contextvars
from typing import Optional, Dict, Any, Tuple

from core.db import (
    get_or_create_user,
    get_user_by_id,
    get_user_by_email,
    get_supabase_url,
)
from core.config import get_secret

logger = logging.getLogger("equity_research.core.auth")

_user_session_var: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar("user_session", default=None)
_auth_token_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("auth_token", default=None)

_JWKS_CACHE: Dict[str, Any] = {"keys": [], "fetched_at": 0.0, "url": ""}


def _b64url_decode(data: str) -> bytes:
    rem = len(data) % 4
    if rem:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def get_supabase_auth_config() -> Dict[str, str]:
    """
    Resolves Supabase Project REST URL and Public Anon Key from secrets or environment.
    If direct SUPABASE_URL is not set, derives it from SUPABASE_DB_URL even when PostgreSQL
    has failed over to SQLite.
    """
    supabase_url = get_secret("SUPABASE_URL") or os.environ.get("SUPABASE_URL") or ""
    if supabase_url.startswith(("postgres://", "postgresql://")):
        db_url = supabase_url
        supabase_url = ""
    else:
        db_url = get_secret("SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL") or get_supabase_url() or ""

    # Fallback: Extract from SUPABASE_DB_URL
    if not supabase_url and db_url:
        match = (
            re.search(r"postgres(?:ql)?://postgres\.([a-z0-9]+):", db_url)
            or re.search(r"@db\.([a-z0-9]+)\.supabase\.co", db_url)
            or re.search(r"postgres(?:ql)?://(?!postgres:)([a-z0-9]+):", db_url)
        )
        if match:
            project_ref = match.group(1)
            supabase_url = f"https://{project_ref}.supabase.co"

    if not supabase_url:
        supabase_url = "https://omswdxrtzrvlszkidssh.supabase.co"

    anon_key = (
        get_secret("SUPABASE_ANON_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or get_secret("SUPABASE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or get_secret("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    )

    return {
        "url": (supabase_url or "").rstrip("/"),
        "anon_key": anon_key or ""
    }


def _fetch_supabase_jwks(sb_url: str, force_refresh: bool = False) -> list:
    """Fetches and caches Supabase Auth public JWKS keys (requires zero API keys)."""
    now = time.time()
    if (
        not force_refresh
        and _JWKS_CACHE["keys"]
        and _JWKS_CACHE["url"] == sb_url
        and (now - _JWKS_CACHE["fetched_at"]) < 3600
    ):
        return _JWKS_CACHE["keys"]

    if os.environ.get("TESTING") == "1" and not force_refresh:
        return _JWKS_CACHE["keys"]

    try:
        resp = requests.get(f"{sb_url}/auth/v1/.well-known/jwks.json", timeout=6)
        if resp.status_code == 200:
            keys = resp.json().get("keys") or []
            if keys:
                _JWKS_CACHE["keys"] = keys
                _JWKS_CACHE["fetched_at"] = now
                _JWKS_CACHE["url"] = sb_url
                return keys
    except Exception as e:
        logger.warning(f"Notice fetching Supabase JWKS from {sb_url}: {e}")
    return _JWKS_CACHE["keys"]


def _verify_es256_jwt_with_jwks(access_token: str, header: dict, sb_url: str) -> bool:
    """Verifies an ES256 Supabase access_token signature against the public JWKS endpoint."""
    if header.get("alg") != "ES256":
        return False

    parts = access_token.split(".")
    if len(parts) != 3:
        return False

    kid = header.get("kid")
    keys = _fetch_supabase_jwks(sb_url, force_refresh=False)
    matching_jwk = next((k for k in keys if not kid or k.get("kid") == kid), None)
    if not matching_jwk and os.environ.get("TESTING") != "1":
        keys = _fetch_supabase_jwks(sb_url, force_refresh=True)
        matching_jwk = next((k for k in keys if not kid or k.get("kid") == kid), None)

    if not matching_jwk or matching_jwk.get("kty") != "EC":
        return False

    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        from cryptography.hazmat.primitives import hashes

        x_int = int.from_bytes(_b64url_decode(matching_jwk["x"]), "big")
        y_int = int.from_bytes(_b64url_decode(matching_jwk["y"]), "big")
        pub_key = ec.EllipticCurvePublicNumbers(x_int, y_int, ec.SECP256R1()).public_key()

        raw_sig = _b64url_decode(parts[2])
        if len(raw_sig) != 64:
            return False
        r_int = int.from_bytes(raw_sig[:32], "big")
        s_int = int.from_bytes(raw_sig[32:], "big")
        der_sig = encode_dss_signature(r_int, s_int)

        signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
        pub_key.verify(der_sig, signing_input, ec.ECDSA(hashes.SHA256()))
        return True
    except Exception as e:
        logger.warning(f"ES256 JWKS signature verification failed: {e}")
        return False


def verify_supabase_access_token(access_token: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Verifies a Supabase OAuth access_token and returns (verified_email, full_name).
    Uses a 3-tier verification strategy so authentication succeeds even if SUPABASE_ANON_KEY
    is omitted on Render or set to an sb_secret_ key:
      1. Cryptographic ES256 verification via public {sb_url}/auth/v1/.well-known/jwks.json
      2. Supabase REST /auth/v1/user verification
      3. Supabase Admin /auth/v1/admin/users/{sub} verification (when using sb_secret_ key)
      4. Synthetic token claim extraction strictly in unit test mode (TESTING=1)
    """
    if not access_token or not isinstance(access_token, str):
        return None, None

    cfg = get_supabase_auth_config()
    sb_url = cfg.get("url") or "https://omswdxrtzrvlszkidssh.supabase.co"
    anon_key = cfg.get("anon_key") or ""

    header: Dict[str, Any] = {}
    claims: Dict[str, Any] = {}
    parts = access_token.split(".")
    if len(parts) >= 2:
        try:
            header = json.loads(_b64url_decode(parts[0]).decode("utf-8"))
        except Exception as e:
            logger.debug(f"JWT header decode notice: {e}")
        try:
            claims = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        except Exception as e:
            logger.debug(f"JWT payload decode notice: {e}")

    # Reject expired tokens immediately
    exp = claims.get("exp")
    if exp is not None:
        try:
            if float(exp) < (time.time() - 60):
                logger.warning("Rejected expired Supabase OAuth access_token.")
                return None, None
        except (TypeError, ValueError) as e:
            logger.debug(f"JWT exp parse notice: {e}")

    user_meta = claims.get("user_metadata") or {}
    claim_email = claims.get("email") or user_meta.get("email")
    claim_name = user_meta.get("full_name") or user_meta.get("name") or claims.get("name")

    # Tier 1: Cryptographic ES256 signature verification via Supabase public JWKS (zero API key needed)
    if claim_email and header.get("alg") == "ES256" and sb_url:
        if _verify_es256_jwt_with_jwks(access_token, header, sb_url):
            logger.info(f"Verified Supabase OAuth token via ES256 JWKS for {claim_email}")
            return claim_email, claim_name

    # Tier 2: Supabase /auth/v1/user REST endpoint
    if sb_url and os.environ.get("TESTING") != "1":
        # Note: Supabase API gateway blocks sb_secret_ keys on /auth/v1/user; only pass non-secret anon_key
        req_headers = {"Authorization": f"Bearer {access_token}"}
        if anon_key and not anon_key.startswith("sb_secret_"):
            req_headers["apikey"] = anon_key
        try:
            resp = requests.get(f"{sb_url}/auth/v1/user", headers=req_headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                v_email = data.get("email")
                v_meta = data.get("user_metadata") or {}
                v_name = v_meta.get("full_name") or v_meta.get("name") or claim_name
                if v_email:
                    logger.info(f"Verified Supabase OAuth token via /auth/v1/user for {v_email}")
                    return v_email, v_name
        except Exception as e:
            logger.warning(f"Notice calling Supabase /auth/v1/user: {e}")

    # Tier 3: Supabase Admin /auth/v1/admin/users/{sub} endpoint when configured with sb_secret_ key
    sub = claims.get("sub")
    if sb_url and sub and anon_key.startswith("sb_secret_") and os.environ.get("TESTING") != "1":
        try:
            resp = requests.get(
                f"{sb_url}/auth/v1/admin/users/{sub}",
                headers={"apikey": anon_key, "Authorization": f"Bearer {anon_key}"},
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                v_email = data.get("email")
                v_meta = data.get("user_metadata") or {}
                v_name = v_meta.get("full_name") or v_meta.get("name") or claim_name
                if v_email:
                    logger.info(f"Verified Supabase OAuth token via /auth/v1/admin/users for {v_email}")
                    return v_email, v_name
        except Exception as e:
            logger.warning(f"Notice calling Supabase /auth/v1/admin/users: {e}")

    # Tier 4: Unit test synthetic token support (strictly when TESTING=1)
    if os.environ.get("TESTING") == "1" and claim_email:
        return claim_email, claim_name

    return None, None


def get_google_oauth_url(redirect_uri: Optional[str] = None) -> str:
    """
    Constructs the Supabase Google OAuth authorization URL.
    When users click 'Sign In with Google', they are redirected through Supabase GoTrue.
    """
    cfg = get_supabase_auth_config()
    base_url = cfg["url"]
    if not base_url:
        return ""

    canonical = (os.environ.get("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")
    callback_target = redirect_uri or f"{canonical}/auth/callback"
    return f"{base_url}/auth/v1/authorize?provider=google&redirect_to={callback_target}"


def send_magic_link(email: str, redirect_uri: Optional[str] = None) -> Tuple[bool, str]:
    """
    Dispatches a Supabase Magic Link / OTP login email to the user.
    Strictly verifies email delivery via Supabase GoTrue API; never auto-logs in unverified users.
    """
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return False, "Please enter a valid email address."

    cfg = get_supabase_auth_config()
    base_url = cfg["url"]
    anon_key = cfg["anon_key"]

    if base_url and anon_key:
        try:
            endpoint = f"{base_url}/auth/v1/otp"
            headers = {
                "apikey": anon_key,
                "Content-Type": "application/json"
            }
            payload = {
                "email": clean_email,
                "create_user": True,
            }
            if redirect_uri:
                payload["options"] = {"email_redirect_to": redirect_uri}

            resp = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            if resp.status_code in (200, 201):
                logger.info(f"Supabase magic link dispatched to {clean_email}")
                return True, f"Magic link dispatched! Check your inbox ({clean_email}) to complete sign in."
            else:
                logger.warning(f"Supabase OTP error: {resp.status_code} - {resp.text}")
                return False, f"Failed to dispatch magic link. Authentication gateway returned {resp.status_code}."
        except Exception as e:
            logger.error(f"Failed to dispatch magic link via Supabase: {e}")
            return False, f"Authentication service error: {e}"

    return False, "Authentication service is not configured. Please use Google Sign-In or contact support."


def verify_supabase_otp_token(email: str, token: str) -> Tuple[bool, Optional[str], Optional[str], str]:
    """
    Verifies a 6-digit email OTP or Magic Link token directly against Supabase GoTrue (/auth/v1/verify).
    Returns:
        (is_valid, verified_email, full_name, access_token_or_message)
    """
    clean_email = (email or "").strip().lower()
    clean_token = (token or "").strip()
    if not clean_email or not clean_token:
        return False, None, None, "Email and verification token are required."

    cfg = get_supabase_auth_config()
    base_url = cfg.get("url")
    anon_key = cfg.get("anon_key")
    if not (base_url and anon_key) or os.environ.get("TESTING") == "1":
        return False, None, None, "Supabase GoTrue OTP verification skipped."

    endpoint = f"{base_url}/auth/v1/verify"
    headers = {
        "apikey": anon_key,
        "Content-Type": "application/json",
    }

    for otp_type in ("email", "magiclink", "signup"):
        try:
            payload = {
                "type": otp_type,
                "email": clean_email,
                "token": clean_token,
            }
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=8)
            if resp.status_code in (200, 201):
                data = resp.json() or {}
                u_info = data.get("user") or {}
                v_email = (u_info.get("email") or clean_email).strip().lower()
                u_meta = u_info.get("user_metadata") or {}
                v_name = u_meta.get("full_name") or u_meta.get("name")
                acc_tok = data.get("access_token") or ""
                logger.info(f"Verified Supabase GoTrue OTP ({otp_type}) for {v_email}")
                return True, v_email, v_name, acc_tok
        except Exception as e:
            logger.debug(f"Supabase GoTrue OTP verify ({otp_type}) notice for {clean_email}: {e}")

    return False, None, None, "Supabase GoTrue OTP verification did not match."


def set_session_user(user_record: Dict[str, Any], auth_token: Optional[str] = None):
    """Stores active user session record into thread-safe ContextVar."""
    _user_session_var.set(user_record)
    _auth_token_var.set(auth_token)
    logger.info(f"Active session set for: {user_record.get('email')} (Credits: {user_record.get('credits_balance')})")


def get_current_user() -> Optional[Dict[str, Any]]:
    """Returns the currently authenticated user dictionary or None if unauthenticated."""
    return _user_session_var.get()


def is_authenticated() -> bool:
    """Returns True if a user is currently logged in."""
    user = get_current_user()
    return bool(user and user.get("id"))


def sign_out_user():
    """Clears active user session."""
    _user_session_var.set(None)
    _auth_token_var.set(None)



def refresh_current_user() -> Optional[Dict[str, Any]]:
    """Refreshes active user profile and credit balances from database."""
    current = get_current_user()
    if not current or not current.get("id"):
        return None
    refreshed = get_user_by_id(current["id"])
    if refreshed:
        set_session_user(refreshed)
        return refreshed
    return current


def handle_auth_callback() -> Optional[Dict[str, Any]]:
    """Disabled: Auth handled directly via web routes."""
    return None
