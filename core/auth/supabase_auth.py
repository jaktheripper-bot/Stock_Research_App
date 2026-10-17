"""
Supabase Authentication, Session Management, and Identity State Module.

Handles:
- Supabase Auth GoTrue REST endpoints (Google OAuth redirect, Magic Link / OTP dispatch, token exchange)
- Streamlit session state binding for authenticated user profile and credit balances
- Safe query parameter parsing on OAuth/Magic Link callbacks
- Frictionless guest-to-user conversion with 2 welcome credits
"""

import os
import re
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

def _is_streamlit_running() -> bool:
    return False

def get_supabase_auth_config() -> Dict[str, str]:
    """
    Resolves Supabase Project REST URL and Public Anon Key from secrets or environment.
    If direct SUPABASE_URL is not set, derives it from the PostgreSQL host ref.
    """
    supabase_url = get_secret("SUPABASE_URL")

    # Fallback: Extract from SUPABASE_DB_URL
    if not supabase_url:
        db_url = get_supabase_url() or ""
        match = re.search(r"postgres(?:ql)?://(?:postgres\.)?([a-z0-9]+):", db_url)
        if match:
            project_ref = match.group(1)
            supabase_url = f"https://{project_ref}.supabase.co"

    anon_key = get_secret("SUPABASE_ANON_KEY") or get_secret("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""

    return {
        "url": (supabase_url or "").rstrip("/"),
        "anon_key": anon_key or ""
    }


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
