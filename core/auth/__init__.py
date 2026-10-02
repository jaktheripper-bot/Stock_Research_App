"""
Authentication & User Identity Package for Stock Research App.

Exposes Supabase authentication, session handling, and OAuth/Magic link utilities.
"""

from core.auth.supabase_auth import (
    get_supabase_auth_config,
    get_google_oauth_url,
    send_magic_link,
    set_session_user,
    get_current_user,
    is_authenticated,
    sign_out_user,
    refresh_current_user,
    handle_auth_callback,
)

__all__ = [
    "get_supabase_auth_config",
    "get_google_oauth_url",
    "send_magic_link",
    "set_session_user",
    "get_current_user",
    "is_authenticated",
    "sign_out_user",
    "refresh_current_user",
    "handle_auth_callback",
]
