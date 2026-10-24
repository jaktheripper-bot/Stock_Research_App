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


def site_asset_url(path: str) -> str:
    """Absolute URL for a static asset (social cards need absolute URLs): configured domain + path."""
    base = (os.environ.get("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")
    return f"{base}/{(path or '').lstrip('/')}"


templates.env.globals["site_asset_url"] = site_asset_url


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
    """Validates Origin/Referer headers on state-changing POST endpoints to mitigate CSRF."""
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    target = origin or referer
    if not target:
        return True
    try:
        parsed = urllib.parse.urlparse(target)
        host = (parsed.hostname or "").lower()
        req_host = ""
        try:
            req_host = (request.url.hostname or "").lower()
        except Exception as e_host:
            logger.debug("Request URL hostname resolution notice: %s", e_host)
            host_header = request.headers.get("host", "")
            req_host = (host_header.split(":")[0] if host_header else "").lower()
        canonical_host = (urllib.parse.urlparse(os.environ.get("CANONICAL_DOMAIN", "")).hostname or "").lower()
        allowed_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "testserver", "moatnomics.com", "www.moatnomics.com"}
        if req_host:
            allowed_hosts.add(req_host)
        if canonical_host:
            allowed_hosts.add(canonical_host)
        if host in allowed_hosts:
            return True
        return False
    except Exception as e:
        logger.debug("Origin validation parse error: %s", e)
        return False


def _get_client_ip(request: Request) -> str:
    """Safely extracts client IP behind reverse proxy (Render/Cloudflare) using rightmost XFF hop."""
    cf_ip = (request.headers.get("cf-connecting-ip") or request.headers.get("true-client-ip") or "").strip()
    if cf_ip:
        return cf_ip
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


def is_production_environment() -> bool:
    """Returns True if running in production, on Render, or with production flags enabled."""
    env = (os.environ.get("ENVIRONMENT") or "").strip().lower()
    is_render = (os.environ.get("RENDER") or "").strip().lower() in ("true", "1")
    is_prod = (os.environ.get("PRODUCTION") or "").strip().lower() in ("true", "1")
    return env in ("production", "prod", "live") or is_render or is_prod


def is_local_dev_request(request: Request) -> bool:
    """
    Evaluates whether an administrative request originates from an authentic local development host.

    Hardcoded Production Kill-Switch & Anti-Spoofing Directives:
    1. If running in production or on Render (ENVIRONMENT in ['production', 'prod'] or RENDER == 'true'),
       dev-bypass is HARD-DISABLED and this function strictly returns False.
    2. In production, never inspect or trust X-Forwarded-For, X-Real-IP, X-Forwarded-Host, or Host headers.
    3. In local development, the presence of forwarding proxy headers (X-Forwarded-For, X-Forwarded-Host,
       X-Real-IP, Forwarded) immediately disqualifies the request to natively prevent proxy header injection.
    4. Client TCP host must strictly match loopback interfaces ('127.0.0.1', '::1') or 'testclient'.
    5. URL host must strictly match 'localhost', '127.0.0.1', or 'testserver'.
    """
    # 1. Hardcoded Environment Kill-Switch
    if is_production_environment():
        return False

    # 2. Reject any forwarding proxy headers (prevents proxy spoofing via X-Forwarded-For / Host)
    for proxy_header in ("x-forwarded-for", "x-forwarded-host", "x-real-ip", "forwarded", "cf-connecting-ip", "true-client-ip"):
        if request.headers.get(proxy_header):
            return False

    # 3. Direct Peer Socket Verification
    client_ip = (request.client.host if request.client else "").strip()
    if client_ip not in ("127.0.0.1", "::1", "testclient"):
        return False

    # 4. Host Header Verification
    host = (request.url.hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "testserver")


_is_local_dev_request = is_local_dev_request


def _get_user_signing_key() -> bytes:
    key = (
        os.environ.get("SECRET_KEY")
        or get_secret("SECRET_KEY")
        or os.environ.get("ADMIN_API_KEY")
        or get_secret("ADMIN_API_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or get_secret("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_DB_URL")
        or get_secret("SUPABASE_DB_URL")
    )
    if is_production_environment() and not key:
        raise RuntimeError("CRITICAL PRODUCTION SECURITY FAILURE: Cannot generate user signing key without SECRET_KEY in production.")
    key = key or "stock_research_user_session_salt_2026"
    return hashlib.sha256(f"user_session:{key}".encode("utf-8")).digest()


def _generate_user_session_token(user_id: str, email: str) -> str:
    secret = _get_user_signing_key()
    now_ts = int(datetime.now(timezone.utc).timestamp())
    data = json.dumps({"user_id": user_id, "email": email.strip().lower(), "purpose": "user_session", "ts": now_ts})
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
        if not isinstance(payload, dict) or not payload.get("email") or payload.get("pending_email"):
            return None
        ts = payload.get("ts", 0)
        # Valid for 30 days
        if datetime.now(timezone.utc).timestamp() - ts < 2592000:
            return payload
        return None
    except Exception as e:
        logger.debug("Failed validating user session token: %s", e)
        return None


def _get_current_web_user(request: Request) -> Optional[Dict[str, Any]]:
    """Retrieves authenticated web user from signed session cookie, Supabase JWT cookie, or Bearer header."""
    override = _get_override_fn("web.main", "_get_current_web_user", None)
    if override is not None and override is not _get_current_web_user:
        return override(request)
    token = request.cookies.get(USER_SESSION_COOKIE) or request.cookies.get("sb-access-token")
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
    session = _validate_user_session_token(token)
    if session and session.get("email"):
        user = get_user_by_email(session["email"])
        if user:
            return user
    if token and token.count(".") == 2:
        from core.auth.supabase_auth import verify_supabase_access_token
        v_email, _ = verify_supabase_access_token(token)
        if v_email:
            user = get_user_by_email(v_email)
            if user:
                return user
    return None


def _get_admin_signing_key(purpose: str = "admin_session") -> bytes:
    key = (
        os.environ.get("ADMIN_API_KEY")
        or get_secret("ADMIN_API_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or get_secret("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SECRET_KEY")
        or get_secret("SECRET_KEY")
        or os.environ.get("SUPABASE_DB_URL")
        or get_secret("SUPABASE_DB_URL")
    )
    if is_production_environment() and not key:
        raise RuntimeError(f"CRITICAL PRODUCTION SECURITY FAILURE: Cannot generate admin key for '{purpose}' without ADMIN_API_KEY or SECRET_KEY in production.")
    key = key or "stock_research_admin_master_secret_2026"
    return hashlib.sha256(f"{purpose}:{key}".encode("utf-8")).digest()


def _generate_admin_token(email: str, role: str = "super_admin") -> str:
    secret = _get_admin_signing_key("admin_session")
    now_ts = int(datetime.now(timezone.utc).timestamp())
    data = json.dumps({"email": email.strip().lower(), "role": role, "purpose": "admin_session", "ts": now_ts})
    payload_b64 = base64.urlsafe_b64encode(data.encode("utf-8")).decode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _validate_admin_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig = token.rsplit(".", 1)
        secret = _get_admin_signing_key("admin_session")
        expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        data_str = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(data_str)
        # Prevent token confusion: reject pending_2fa tokens or tokens without verified admin email
        if (
            not isinstance(payload, dict)
            or not payload.get("email")
            or payload.get("pending_email")
            or payload.get("purpose", "admin_session") != "admin_session"
        ):
            return None
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
    secret = _get_admin_signing_key("admin_2fa_pending")
    now_ts = int(datetime.now(timezone.utc).timestamp())
    data = json.dumps({"pending_email": email.strip().lower(), "purpose": "admin_2fa_pending", "ts": now_ts})
    payload_b64 = base64.urlsafe_b64encode(data.encode("utf-8")).decode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _validate_pending_2fa_token(token: Optional[str]) -> Optional[str]:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig = token.rsplit(".", 1)
        secret = _get_admin_signing_key("admin_2fa_pending")
        expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8"))
        if not isinstance(data, dict) or data.get("purpose", "admin_2fa_pending") != "admin_2fa_pending":
            return None
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
    if os.environ.get("TESTING") == "1" and (
        request.headers.get("x-unlock-preview") == "1" or request.query_params.get("unlocked") == "1"
    ):
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
    "*Deep-dive section. Unlock this ticker on the website (1 credit) "
    "to include it in your PDF.*"
)


def _is_ticker_unlocked_for_request(request: Request, ticker: str) -> bool:
    """Server-side check: True if user unlocked this ticker or is an active Pro subscriber / admin."""
    return _deep_dive_unlocked_for_request(request, ticker)


def _asset_unlock_key(kind: str, asset_id: str) -> str:
    """Namespaced key so fund/debt unlocks never collide with equity tickers (e.g. 'FUND:119551')."""
    return f"{kind.upper()}:{str(asset_id).strip().upper()}"


def _asset_unlocked_for_request(request: Request, kind: str, asset_id: str) -> bool:
    """Server-side rule for Equity / Mutual Fund / Corporate Debt / REIT deep-dive paywall (1 credit each)."""
    kind_clean = (kind or "").strip().upper()
    if kind_clean in ("EQUITY", "STOCK", ""):
        return _deep_dive_unlocked_for_request(request, asset_id)

    admin_auth_fn = _get_override_fn("web.main", "_is_admin_authenticated", _is_admin_authenticated)
    if admin_auth_fn(request):
        return True
    if os.environ.get("TESTING") == "1" and (
        request.headers.get("x-unlock-preview") == "1" or request.query_params.get("unlocked") == "1"
    ):
        return True
    get_user_fn = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
    web_user = get_user_fn(request)
    if web_user and asset_id:
        tier = (web_user.get("subscription_tier") or "free").lower()
        if tier in ("pro_monthly", "pro_annual") or "pro" in tier or web_user.get("is_pro"):
            return True
        from core.db import is_ticker_unlocked_for_user
        check_fn = _get_override_fn("web.main", "is_ticker_unlocked_for_user", is_ticker_unlocked_for_user)
        return bool(check_fn(web_user.get("id", ""), _asset_unlock_key(kind_clean, asset_id)))
    return False


def redact_equity_intel_json(intel: Optional[Dict[str, Any]], is_unlocked: bool = False) -> Optional[Dict[str, Any]]:
    """
    Enforces strict server-side redaction on Equity Intelligence JSON.
    When is_unlocked is False, physically strips or overwrites Pillar 3 (Forensic Accounting)
    and Pillar 5 (Multi-Model DCF/Valuation Radar) so premium IP is never dispatched over HTTP.
    """
    if not intel or not isinstance(intel, dict):
        return intel
    if is_unlocked:
        return intel

    import copy
    redacted = copy.deepcopy(intel)
    clean_sym = str(redacted.get("ticker") or "").strip().upper()
    unlock_url = f"/api/dossier/unlock/{clean_sym}" if clean_sym else "/pricing"

    # Redact Pillar 3: Forensic Intelligence Ledger
    if "forensic_intelligence" in redacted and redacted["forensic_intelligence"]:
        redacted["forensic_intelligence"] = {
            "status": "LOCKED",
            "locked": True,
            "badge_color": "#fbbf24",
            "badge_label": "Gated (1 Credit)",
            "passed_count": 0,
            "total_checks": 10,
            "summary": "Detailed 360° Forensic Clean-Room Ledger is locked. Unlock this dossier (1 credit) to view Beneish M-Score, cash quality, and auditor forensics.",
            "red_flags": [],
            "checks": [],
            "unlock_endpoint": unlock_url,
        }

    # Redact Pillar 5: Valuation Radar & Reverse DCF Sandbox
    if "valuation_radar" in redacted and redacted["valuation_radar"]:
        orig_vr = redacted["valuation_radar"]
        redacted["valuation_radar"] = {
            "status": "LOCKED",
            "locked": True,
            "badge_color": "#fbbf24",
            "badge_label": "Gated (1 Credit)",
            "current_price": orig_vr.get("current_price"),
            "fair_value": None,
            "margin_of_safety_pct": None,
            "summary": "Triangulated Multi-Model Intrinsic Valuation Matrix & Reverse DCF Sandbox are locked. Unlock this dossier (1 credit) to view detailed model valuations.",
            "models": None,
            "inputs": None,
            "unlock_endpoint": unlock_url,
        }

    # Redact deep proprietary packets if present
    if "varan_delta_packet" in redacted and redacted["varan_delta_packet"]:
        redacted["varan_delta_packet"] = {
            "status": "LOCKED",
            "locked": True,
            "unlock_endpoint": unlock_url,
        }

    if "setu_capital_matrix" in redacted and redacted["setu_capital_matrix"]:
        redacted["setu_capital_matrix"] = {
            "status": "LOCKED",
            "locked": True,
            "unlock_endpoint": unlock_url,
        }

    redacted["deep_dive_locked"] = True
    redacted["unlock_endpoint"] = unlock_url
    return redacted


DEBT_GATED_PILLAR_KEYS = ("p3_solvency", "p5_recovery")
FUND_FREE_DOSSIER_KEYS = ("scheme_code", "scheme_name", "composite_health_score", "last_audited_at")


def server_side_paywall_redact(data: Dict[str, Any], asset_type: str, is_unlocked: bool) -> Dict[str, Any]:
    """
    Polymorphic server-side paywall redaction helper.
    Physically removes premium intellectual property from JSON objects before HTTP response dispatch.
    """
    if is_unlocked or not data:
        return data

    asset_upper = (asset_type or "").strip().upper()
    if asset_upper in ("EQUITY", "STOCK"):
        return redact_equity_intel_json(data, is_unlocked=False) or {}

    import copy
    redacted = copy.deepcopy(data)
    if asset_upper == "MUTUAL_FUND":
        from core.agents.copilot.research_desk import MF_GATED_FIELDS
        for field in MF_GATED_FIELDS:
            redacted.pop(field, None)
        redacted["deep_dive_locked"] = True
        return redacted

    if asset_upper == "CORPORATE_DEBT":
        redacted.pop("credit_contagion_radar", None)
        pillars = dict(redacted.get("pillars") or {})
        for gated in DEBT_GATED_PILLAR_KEYS:
            pillars.pop(gated, None)
        redacted["pillars"] = pillars
        redacted["deep_dive_locked"] = True
        return redacted

    if asset_upper == "REIT":
        redacted.pop("countercase_risks", None)
        redacted["deep_dive_locked"] = True
        return redacted

    return redacted


def _unlock_asset_deep_dive(request: Request, kind: str, asset_id: str, label: str):
    """Charges 1 credit (idempotent) and records the unlock for a fund scheme or debt security."""
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")
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

