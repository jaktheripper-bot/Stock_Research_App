"""Shared web utilities, template engine, and authentication context helpers.

Provides common helpers for authentication, session verification, canonical URL
formatting, and response caching across all domain routers.
"""

import os
import sys
import json
import base64
import hmac
import hashlib
import urllib.parse
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from core.config import get_secret
from core.db import init_db, IST, MANDATORY_SEBI_DISCLAIMER
from core.db.users import get_user_by_email, is_ticker_unlocked_for_user
from normalizer import clean_ticker
from bse_master import resolve_canonical_symbol

logger = logging.getLogger("equity_research.web.common")

# Template Engine Initializer
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
templates.env.globals["MANDATORY_SEBI_DISCLAIMER"] = MANDATORY_SEBI_DISCLAIMER

# Cookie Identifiers
ADMIN_COOKIE_NAME = "admin_session"
ADMIN_2FA_PENDING_COOKIE = "admin_2fa_pending"
USER_SESSION_COOKIE = "user_session_token"

ALLOWED_ORIGIN_HOSTS = {
    "localhost",
    "127.0.0.1",
    "testserver",
    "moatnomics.com",
    "www.moatnomics.com",
    "vestfolio.app",
    "www.vestfolio.app",
    "vestnomics.app",
    "www.vestnomics.app",
    "stockresearch.app",
    "www.stockresearch.app",
    "stock-research-app-2ljm.onrender.com",
}


def canonical_for(request: Request) -> str:
    """Canonical URL for a request: configured domain + path, without tracking or stray query params."""
    try:
        base = (os.environ.get("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")
        path = request.url.path or "/"
        if len(path) > 1:
            path = path.rstrip("/")
        url = f"{base}{path}"
        if path == "/compare":
            a = (request.query_params.get("a") or "").strip().upper()
            b = (request.query_params.get("b") or "").strip().upper()
            if a and b:
                url += "?" + urllib.parse.urlencode({"a": a, "b": b})
        return url
    except Exception as canon_err:
        logger.debug("Canonical URL notice: %s", canon_err)
        return ""


templates.env.globals["canonical_for"] = canonical_for


def json_response_with_cache(data: dict, max_age: int = 3600) -> JSONResponse:
    """Returns JSONResponse with ETag and Cache-Control headers."""
    from fastapi.encoders import jsonable_encoder
    safe_data = jsonable_encoder(data)
    content_str = json.dumps(safe_data, sort_keys=True, default=str)
    etag = f'"{hashlib.md5(content_str.encode()).hexdigest()}"'

    # Anti-staleness guard: Never cache empty or error payloads at the edge/CDN.
    # This prevents transient startup / cold migration states from locking in empty responses for 3600s.
    is_empty = False
    if isinstance(safe_data, dict):
        if safe_data.get("count") == 0:
            is_empty = True
        elif safe_data.get("status") in ("error", "failed"):
            is_empty = True
        elif safe_data.get("success") is False:
            is_empty = True
        elif "data" in safe_data and isinstance(safe_data["data"], list) and len(safe_data["data"]) == 0:
            is_empty = True
        elif "securities" in safe_data and isinstance(safe_data["securities"], list) and len(safe_data["securities"]) == 0:
            is_empty = True
        elif "items" in safe_data and isinstance(safe_data["items"], list) and len(safe_data["items"]) == 0:
            is_empty = True

    cache_header = "no-cache, no-store, must-revalidate" if is_empty else f"public, max-age={max_age}"

    return JSONResponse(
        content=safe_data,
        media_type="application/json",
        headers={
            "Cache-Control": cache_header,
            "ETag": etag,
        }
    )


def resolve_app_base_url(request: Request) -> str:
    """Resolves canonical public base URL handling reverse proxies (Render SSL termination)."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc or ""

    is_prod = bool(os.environ.get("RENDER")) or os.environ.get("ENVIRONMENT") == "production"
    if is_prod and (not host or "localhost" in host or "127.0.0.1" in host):
        return (os.environ.get("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")

    if "onrender.com" in host or ("localhost" not in host and "127.0.0.1" not in host and "testserver" not in host):
        proto = "https"
    return f"{proto}://{host}".rstrip("/")


def _validate_request_origin(request: Request) -> bool:
    """Validates state-mutating request origin against CSRF host whitelist."""
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    target = origin or referer
    if not target:
        return True
    try:
        parsed = urllib.parse.urlparse(target)
        host = (parsed.hostname or "").lower()
        return host in ALLOWED_ORIGIN_HOSTS or host.endswith(".onrender.com")
    except Exception as e:
        logger.debug("Failed validating CSRF origin: %s", e)
        return False


def _get_user_signing_key() -> bytes:
    key = os.environ.get("SECRET_KEY") or get_secret("SECRET_KEY") or os.environ.get("ADMIN_API_KEY") or get_secret("ADMIN_API_KEY") or "stock_research_user_session_salt_2026"
    return key.encode("utf-8")


def _generate_user_session_token(user_id: str, email: str) -> str:
    secret = _get_user_signing_key()
    now_ts = int(datetime.now(timezone.utc).timestamp())
    data = json.dumps({"user_id": user_id, "email": email.strip().lower(), "ts": now_ts})
    payload_b64 = base64.urlsafe_b64encode(data.encode("utf-8")).decode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _validate_user_session_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig = token.rsplit(".", 1)
        secret = _get_user_signing_key()
        expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        data_str = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(data_str)
        ts = payload.get("ts", 0)
        # Valid for 30 days
        if datetime.now(timezone.utc).timestamp() - ts < 2592000:
            return payload
        return None
    except Exception as e:
        logger.debug("Failed validating user session token: %s", e)
        return None


def _get_current_web_user(request: Request) -> Optional[Dict[str, Any]]:
    """Retrieves authenticated web user from signed cookie or Bearer header."""
    override = _get_override_fn("web.main", "_get_current_web_user", None)
    if override is not None and override is not _get_current_web_user:
        return override(request)
    token = request.cookies.get(USER_SESSION_COOKIE)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
    session = _validate_user_session_token(token)
    if session and session.get("email"):
        user = get_user_by_email(session["email"])
        if user:
            return user
    return None


def _get_admin_signing_key() -> bytes:
    key = os.environ.get("ADMIN_API_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "stock_research_admin_master_secret_2026"
    return key.encode("utf-8")


def _generate_admin_token(email: str, role: str = "super_admin") -> str:
    secret = _get_admin_signing_key()
    now_ts = int(datetime.now(timezone.utc).timestamp())
    data = json.dumps({"email": email.strip().lower(), "role": role, "ts": now_ts})
    payload_b64 = base64.urlsafe_b64encode(data.encode("utf-8")).decode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _validate_admin_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig = token.rsplit(".", 1)
        secret = _get_admin_signing_key()
        expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        data_str = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(data_str)
        ts = payload.get("ts", 0)
        # Valid for 24 hours
        if datetime.now(timezone.utc).timestamp() - ts < 86400:
            return payload
        return None
    except Exception as e:
        logger.debug("Failed validating admin token: %s", e)
        return None


def _is_admin_authenticated(request: Request) -> Optional[Dict[str, Any]]:
    """Checks whether the request carries a valid admin session cookie."""
    override = _get_override_fn("web.main", "_is_admin_authenticated", None)
    if override is not None and override is not _is_admin_authenticated:
        return override(request)
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    return _validate_admin_token(token)


def _generate_pending_2fa_token(email: str) -> str:
    secret = _get_admin_signing_key()
    now_ts = int(datetime.now(timezone.utc).timestamp())
    data = json.dumps({"pending_email": email.strip().lower(), "ts": now_ts})
    payload_b64 = base64.urlsafe_b64encode(data.encode("utf-8")).decode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _validate_pending_2fa_token(token: Optional[str]) -> Optional[str]:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig = token.rsplit(".", 1)
        secret = _get_admin_signing_key()
        expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8"))
        ts = data.get("ts", 0)
        # Valid for 15 minutes
        if datetime.now(timezone.utc).timestamp() - ts < 900:
            return data.get("pending_email")
        return None
    except Exception as e:
        logger.debug("Failed validating pending 2fa token: %s", e)
        return None


def _build_local_qr_data_uri(payload: str) -> str:
    """Renders a QR code locally as an inline SVG data URI."""
    import io
    import segno
    buf = io.BytesIO()
    segno.make(payload, error="m").save(buf, kind="svg", scale=5, border=2, dark="#000000", light="#ffffff")
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _is_user_subscribed(user: Optional[Dict[str, Any]]) -> bool:
    """Checks whether the user has an active Pro/Institutional subscription."""
    if not user:
        return False
    tier = (user.get("subscription_tier") or "free").lower()
    if tier in ("pro_monthly", "pro_annual", "pro", "institutional_pro"):
        exp = user.get("subscription_expires_at")
        if not exp:
            return True
        now = datetime.now(timezone.utc)
        if isinstance(exp, str):
            try:
                exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                return exp_dt > now
            except Exception as e:
                logger.debug("Failed parsing subscription_expires_at in _is_user_subscribed: %s", e)
                return True
        elif hasattr(exp, "tzinfo"):
            return exp > now
        return True
    return False


def _can_access_today_discovery(request: Request, user: Optional[Dict[str, Any]]) -> bool:
    """Returns True if the request has entitlement to view today's live 9:00 AM Discovery Reel."""
    if os.environ.get("TESTING") == "1":
        if request.headers.get("x-admin-key") or request.query_params.get("test_access") == "1":
            return True
        return _is_user_subscribed(user)
    try:
        if _is_admin_authenticated(request):
            return True
    except Exception as e:
        logger.debug(f"Admin auth check in deep dive access notice: {e}")
    return _is_user_subscribed(user)


def _get_override_fn(mod_name: str, attr_name: str, fallback):
    """Dynamic attribute lookup allowing unittest mock.patch('web.main.xyz') to intercept seamlessly."""
    import sys
    mod = sys.modules.get(mod_name)
    if mod and hasattr(mod, attr_name):
        val = getattr(mod, attr_name)
        if val is not None and val is not fallback:
            return val
    return fallback


def _extract_jwt_claims(token_str: str) -> dict:
    """Safely decodes Supabase JWT claims without requiring remote network roundtrips."""
    try:
        parts = str(token_str).strip().split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            return json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8"))
    except Exception as e:
        logger.debug(f"JWT claim extraction notice: {e}")
    return {}


def _deep_dive_unlocked_for_request(request: Request, ticker: str) -> bool:
    """Single server-side rule for the Pillar 03/05 paywall, shared by copilot and PDF export."""
    admin_auth_fn = _get_override_fn("web.main", "_is_admin_authenticated", _is_admin_authenticated)
    if admin_auth_fn(request):
        return True
    if os.environ.get("TESTING") == "1" and request.headers.get("x-unlock-preview") == "1":
        return True
    get_user_fn = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
    web_user = get_user_fn(request)
    if web_user and ticker:
        tier = (web_user.get("subscription_tier") or "free").lower()
        if tier in ("pro_monthly", "pro_annual") or "pro" in tier or web_user.get("is_pro"):
            return True
        t_clean = clean_ticker(ticker)
        canonical = resolve_canonical_symbol(t_clean) or t_clean
        from core.db import is_ticker_unlocked_for_user
        check_fn = _get_override_fn("web.main", "is_ticker_unlocked_for_user", is_ticker_unlocked_for_user)
        return bool(check_fn(web_user.get("id", ""), canonical))
    return False


def _pdf_account_ref(request: Request) -> str:
    """Opaque account reference stamped on PDFs (never the email address)."""
    get_user_fn = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
    web_user = get_user_fn(request)
    return str(web_user.get("id", ""))[:12] if web_user else ""


PDF_LOCKED_NOTICE = (
    "*Institutional deep-dive section. Unlock this ticker on the website (1 credit) "
    "to include it in your PDF.*"
)


def _is_ticker_unlocked_for_request(request: Request, ticker: str) -> bool:
    """Server-side check: True if user unlocked this ticker or is an active Pro subscriber / admin."""
    return _deep_dive_unlocked_for_request(request, ticker)


def _asset_unlock_key(kind: str, asset_id: str) -> str:
    """Namespaced key so fund/debt unlocks never collide with equity tickers (e.g. 'FUND:119551')."""
    return f"{kind.upper()}:{str(asset_id).strip().upper()}"


def _asset_unlocked_for_request(request: Request, kind: str, asset_id: str) -> bool:
    """Server-side rule for the Mutual Fund / Corporate Debt / REIT deep-dive paywall (1 credit each)."""
    admin_auth_fn = _get_override_fn("web.main", "_is_admin_authenticated", _is_admin_authenticated)
    if admin_auth_fn(request):
        return True
    if os.environ.get("TESTING") == "1" and request.headers.get("x-unlock-preview") == "1":
        return True
    get_user_fn = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
    web_user = get_user_fn(request)
    if web_user and asset_id:
        tier = (web_user.get("subscription_tier") or "free").lower()
        if tier in ("pro_monthly", "pro_annual") or "pro" in tier or web_user.get("is_pro"):
            return True
        from core.db import is_ticker_unlocked_for_user
        check_fn = _get_override_fn("web.main", "is_ticker_unlocked_for_user", is_ticker_unlocked_for_user)
        return bool(check_fn(web_user.get("id", ""), _asset_unlock_key(kind, asset_id)))
    return False


def _unlock_asset_deep_dive(request: Request, kind: str, asset_id: str, label: str):
    """Charges 1 credit (idempotent) and records the unlock for a fund scheme or debt security."""
    get_user_fn = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
    web_user = get_user_fn(request)
    if not web_user:
        raise HTTPException(
            status_code=401,
            detail="Sign in to unlock the Deep Dive. New accounts get 2 free welcome credits."
        )
    uid = str(web_user.get("id", "")).strip()
    key = _asset_unlock_key(kind, asset_id)

    from core.db import unlock_ticker_for_user
    from core.db.telemetry import record_usage_event
    unlock_fn = _get_override_fn("web.main", "unlock_ticker_for_user", unlock_ticker_for_user)
    ok, new_bal, msg = unlock_fn(user_id=uid, ticker=key, amount=1.0)
    if not ok:
        raise HTTPException(status_code=402, detail=msg)

    record_usage_event(
        event_type="dossier_unlock",
        ticker=key,
        user_id=uid,
        details={"action": f"{kind.lower()}_deep_dive_unlock", "new_balance": new_bal}
    )
    return json_response_with_cache({
        "success": True,
        "asset_kind": kind,
        "asset_id": str(asset_id).strip().upper(),
        "new_balance": new_bal,
        "message": f"Deep Dive unlocked for {label}."
    })

