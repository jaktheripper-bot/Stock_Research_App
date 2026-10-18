"""Authentication, Session Management, Telemetry and Razorpay Billing Router.

Provides:
- Public email OTP verification and 30-day cryptographically signed user sessions
- Supabase Google OAuth PKCE and implicit token callbacks
- Client-side anonymous and user acquisition telemetry pipeline
- Razorpay order creation and HMAC-SHA256 signature verification
"""

import os
import json
import logging
import urllib.parse
import hashlib
import requests
from typing import Optional, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from core.auth.otp import create_email_otp, verify_email_otp
from core.auth.supabase_auth import get_supabase_auth_config
from core.db import get_or_create_user, get_user_by_id
from core.db.telemetry import (
    record_usage_event,
    parse_traffic_source,
    parse_user_agent,
    extract_geo,
    is_excluded_telemetry_event,
)
from core.billing import (
    create_razorpay_order,
    process_successful_payment,
    RazorpayAuthError,
    RazorpayAPIError,
    SUPPORTED_CURRENCIES,
    convert_inr_to_currency,
    resolve_currency_for_request,
)
from web.common import (
    resolve_app_base_url,
    _validate_request_origin,
    _generate_user_session_token,
    _validate_user_session_token,
    _get_current_web_user,
    _extract_jwt_claims,
    _is_admin_authenticated,
    ADMIN_COOKIE_NAME,
    USER_SESSION_COOKIE,
    json_response_with_cache,
)

logger = logging.getLogger("equity_research.web.auth_billing")

router = APIRouter(tags=["auth_billing"])


# ==============================================================================
# Pydantic Schemas
# ==============================================================================
class SendOtpRequest(BaseModel):
    email: str


class VerifyOtpRequest(BaseModel):
    email: str
    code: str
    full_name: Optional[str] = None


class SignInRequest(BaseModel):
    email: str
    full_name: Optional[str] = None
    otp_code: Optional[str] = None


class OrderRequest(BaseModel):
    plan_id: Optional[str] = None
    amount: Optional[int] = None       # amount in paise (minimum 100)
    currency: Optional[str] = "INR"
    receipt: Optional[str] = None
    user_id: Optional[str] = "guest_web_user"
    email: Optional[str] = "investor@example.com"


class VerifyPaymentRequest(BaseModel):
    order_id: Optional[str] = None
    razorpay_order_id: Optional[str] = None
    payment_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    signature: Optional[str] = None
    razorpay_signature: Optional[str] = None
    plan_id: Optional[str] = "single_pass"
    user_id: Optional[str] = "guest_web_user"


class TelemetryEventRequest(BaseModel):
    event_type: str
    ticker: Optional[str] = ""
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    session_id: Optional[str] = None
    referrer: Optional[str] = None
    landing_url: Optional[str] = None
    landing_page: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    ref: Optional[str] = None
    details: Optional[dict] = None


# ==============================================================================
# Email OTP Authentication Endpoints
# ==============================================================================
@router.post("/api/auth/send-otp")
async def api_send_otp(payload: SendOtpRequest):
    """
    Generates and dispatches a cryptographically secure 6-digit email OTP.
    Enforces a 60-second cooldown rate-limit per email.
    """
    clean_email = (payload.email or "").strip().lower()
    success, msg, code = create_email_otp(clean_email)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    response_data = {"success": True, "message": msg}
    if os.environ.get("TESTING") == "1":
        response_data["test_code"] = code
    return JSONResponse(content=response_data)


@router.post("/api/auth/verify-otp")
async def api_verify_otp(payload: VerifyOtpRequest):
    """
    Validates email OTP, registers/authenticates user, and issues a 30-day signed session cookie.
    """
    clean_email = (payload.email or "").strip().lower()
    valid, msg = verify_email_otp(clean_email, payload.code)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)

    user_id = f"usr_{clean_email.replace('@', '_at_').replace('.', '_')}"
    user = get_or_create_user(
        user_id=user_id,
        email=clean_email,
        full_name=payload.full_name or clean_email.split("@")[0].capitalize()
    )
    if not user:
        raise HTTPException(status_code=500, detail="Could not initialize user profile.")

    record_usage_event(
        event_type="user_signin",
        user_id=user_id,
        user_email=clean_email,
        details={"name": user.get("full_name"), "tier": user.get("subscription_tier"), "method": "email_otp"}
    )

    token = _generate_user_session_token(user_id, clean_email)
    resp = JSONResponse(content={
        "success": True,
        "token": token,
        "message": f"Welcome {user.get('full_name')}! You have received 2 free research credits.",
        "user": user
    })
    resp.set_cookie(
        key=USER_SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=2592000
    )
    return resp


@router.post("/api/auth/signin")
async def api_signin(payload: SignInRequest):
    """
    Hardened user sign-in endpoint.
    Requires verified OTP code or testing bypass. Direct unverified email registration is blocked in production.
    """
    clean_email = (payload.email or "").strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")

    if os.environ.get("TESTING") != "1":
        if not payload.otp_code:
            raise HTTPException(
                status_code=403,
                detail="Direct unverified sign-in is disabled. Please verify your email via OTP or Google OAuth."
            )
        valid, msg = verify_email_otp(clean_email, payload.otp_code)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)

    user_id = f"usr_{clean_email.replace('@', '_at_').replace('.', '_')}"
    user = get_or_create_user(
        user_id=user_id,
        email=clean_email,
        full_name=payload.full_name or clean_email.split("@")[0].capitalize()
    )
    if not user:
        raise HTTPException(status_code=500, detail="Could not initialize user profile.")

    record_usage_event(
        event_type="user_signin",
        user_id=user_id,
        user_email=clean_email,
        details={"name": user.get("full_name"), "tier": user.get("subscription_tier"), "method": "direct_verified"}
    )

    token = _generate_user_session_token(user_id, clean_email)
    resp = JSONResponse(content={
        "success": True,
        "token": token,
        "message": f"Welcome {user.get('full_name')}! You have received 2 free research credits.",
        "user": user
    })
    resp.set_cookie(
        key=USER_SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=2592000
    )
    return resp


# ==============================================================================
# Google OAuth Flow via Supabase GoTrue
# ==============================================================================
@router.get("/auth/google")
async def public_auth_google(request: Request, redirect: Optional[str] = "/"):
    """Public Google OAuth initiation via Supabase GoTrue."""
    base_url = resolve_app_base_url(request)
    redirect_target = f"{base_url}/auth/callback"
    cfg = get_supabase_auth_config()
    sb_url = cfg.get("url")

    if sb_url:
        oauth_url = f"{sb_url}/auth/v1/authorize?provider=google&redirect_to={urllib.parse.quote(redirect_target)}"
        resp = RedirectResponse(url=oauth_url, status_code=303)
        if redirect and redirect != "/":
            is_secure = base_url.startswith("https://")
            resp.set_cookie(
                key="oauth_next",
                value=redirect,
                max_age=600,
                httponly=True,
                samesite="lax",
                secure=is_secure,
                path="/"
            )
        return resp
    return RedirectResponse(
        url="/?err=Google+OAuth+not+yet+configured.+Please+use+Email+OTP+verification.",
        status_code=303
    )


@router.get("/auth/callback")
async def public_auth_callback(
    request: Request,
    code: Optional[str] = None,
    access_token: Optional[str] = None,
    next: Optional[str] = "/"
):
    """Processes Google OAuth callback for public users, sets session cookie and localStorage."""
    oauth_err = request.query_params.get("error_description") or request.query_params.get("error")
    if oauth_err:
        clean_err = oauth_err.replace("+", " ")
        logger.warning(f"Public Google OAuth redirect error received: {clean_err}")
        return RedirectResponse(url=f"/?err={urllib.parse.quote(clean_err)}", status_code=303)

    current_user = _get_current_web_user(request)
    if current_user and not code and not access_token:
        raw_next = request.query_params.get("next") or "/"
        dest_url = raw_next if (raw_next.startswith("/") and not raw_next.startswith("//")) else "/"
        return RedirectResponse(url=dest_url, status_code=303)

    cfg = get_supabase_auth_config()
    sb_url = cfg.get("url")
    anon_key = cfg.get("anon_key") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    verified_email = None
    user_name = None

    if code and sb_url:
        try:
            resp = requests.post(
                f"{sb_url}/auth/v1/token?grant_type=pkce",
                json={"auth_code": code},
                headers={"apikey": anon_key, "Content-Type": "application/json"},
                timeout=8
            )
            if resp.status_code == 200:
                tok_data = resp.json()
                u_info = tok_data.get("user", {})
                verified_email = u_info.get("email")
                user_name = u_info.get("user_metadata", {}).get("full_name") or u_info.get("user_metadata", {}).get("name")
        except Exception as e:
            logger.error(f"Error exchanging public OAuth code: {e}")

    elif access_token:
        if sb_url and anon_key:
            try:
                resp = requests.get(
                    f"{sb_url}/auth/v1/user",
                    headers={"Authorization": f"Bearer {access_token}", "apikey": anon_key},
                    timeout=8
                )
                if resp.status_code == 200:
                    data = resp.json()
                    verified_email = data.get("email")
                    user_name = data.get("user_metadata", {}).get("full_name") or data.get("user_metadata", {}).get("name")
            except Exception as e:
                logger.debug(f"Notice fetching public user via token endpoint: {e}")

        # Only allow synthetic JWT claim decoding inside automated test runs (TESTING=1)
        if not verified_email and os.environ.get("TESTING") == "1":
            claims = _extract_jwt_claims(access_token)
            user_meta = claims.get("user_metadata") or {}
            if claims.get("email") or user_meta.get("email"):
                verified_email = claims.get("email") or user_meta.get("email")
                user_name = user_meta.get("full_name") or user_meta.get("name") or claims.get("name")

    if not verified_email:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>Verifying Identity...</title></head>
        <body style="background:#0f172a;color:#f8fafc;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
            <div style="text-align:center;">
                <h2>Authenticating with Google...</h2>
                <p style="color:#94a3b8;">Verifying your account credentials.</p>
            </div>
            <script>
            if (window.location.hash) {{
                const params = new URLSearchParams(window.location.hash.substring(1));
                const token = params.get('access_token');
                const err = params.get('error_description') || params.get('error');
                if (token) {{
                    window.location.href = '/auth/callback?access_token=' + encodeURIComponent(token) + '&next=' + encodeURIComponent('{next or "/"}');
                }} else if (err) {{
                    window.location.href = '/?err=' + encodeURIComponent(err);
                }} else {{
                    window.location.href = '/?err=Authentication+failed';
                }}
            }} else {{
                window.location.href = '/?err=Authentication+session+expired+or+cancelled';
            }}
            </script>
        </body></html>
        """)

    clean_email = verified_email.strip().lower()
    full_name = user_name or clean_email.split("@")[0].capitalize()
    user_id = f"usr_{clean_email.replace('@', '_at_').replace('.', '_')}"
    user = get_or_create_user(user_id=user_id, email=clean_email, full_name=full_name)

    token = _generate_user_session_token(user_id, clean_email)
    oauth_next_cookie = (request.cookies.get("oauth_next") or "").strip('"')
    import html as _html
    raw_next = request.query_params.get("next") or oauth_next_cookie or "/"
    dest_url = raw_next if (raw_next.startswith("/") and not raw_next.startswith("//")) else "/"
    safe_name = _html.escape(str(full_name or ""))
    safe_dest_html = _html.escape(dest_url, quote=True)
    safe_dest_js = json.dumps(dest_url).replace("</", "<\\/")
    safe_user_js = json.dumps(user).replace("</", "<\\/")

    html_content = f"""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><title>Authentication Successful</title></head>
    <body style="background:#0f172a;color:#f8fafc;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
        <div style="text-align:center;">
            <h2>🎉 Welcome, {safe_name}!</h2>
            <p style="color:#94a3b8;">Redirecting to your research terminal...</p>
            <noscript><meta http-equiv="refresh" content="1;url={safe_dest_html}"></noscript>
        </div>
        <script>
        try {{
            const profile = {safe_user_js};
            localStorage.setItem('sr_user', JSON.stringify(profile));
        }} catch (e) {{
            console.error('Session sync error:', e);
        }}
        setTimeout(function() {{
            window.location.replace({safe_dest_js});
        }}, 300);
        </script>
    </body></html>
    """
    resp = HTMLResponse(content=html_content)
    base_url = resolve_app_base_url(request)
    is_secure = base_url.startswith("https://")
    resp.set_cookie(
        key=USER_SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        path="/",
        max_age=2592000
    )
    if oauth_next_cookie:
        resp.delete_cookie(key="oauth_next", path="/")
    return resp


@router.get("/api/auth/me")
async def api_auth_me(request: Request):
    """Returns the currently authenticated user profile from session cookie or Authorization header."""
    user = _get_current_web_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return JSONResponse(content={"authenticated": True, "user": user})


@router.post("/api/auth/signout")
async def api_auth_signout():
    """Clears the authenticated user session cookie."""
    resp = JSONResponse(content={"success": True, "message": "Successfully signed out."})
    resp.delete_cookie(key=USER_SESSION_COOKIE)
    return resp


# ==============================================================================
# Razorpay Billing Endpoints
# ==============================================================================
@router.post("/api/create-order")
async def api_create_order(payload: OrderRequest, request: Request):
    """
    Creates an official Razorpay order or returns simulated checkout data.
    Validates amount >= 100 paise, handles 401 auth and 500 API errors.
    """
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")

    try:
        order = create_razorpay_order(
            plan_id=payload.plan_id,
            amount_paise=payload.amount,
            currency=payload.currency or "INR",
            receipt=payload.receipt,
            user_id=payload.user_id or "guest_web_user",
            user_email=payload.email or "investor@example.com"
        )
        return json_response_with_cache({
            "order_id": order.get("order_id") or order.get("id"),
            "id": order.get("id") or order.get("order_id"),
            "amount": order.get("amount"),
            "currency": order.get("currency", "INR"),
            "key_id": order.get("key_id"),
            "receipt": order.get("receipt"),
            "status": order.get("status", "created"),
            "is_simulated": order.get("is_simulated", False),
            "plan": order.get("plan")
        })
    except RazorpayAuthError as e:
        logger.error(f"Razorpay auth failure: {e}")
        raise HTTPException(status_code=401, detail="Razorpay authentication failed. Verify API credentials.")
    except RazorpayAPIError as e:
        logger.error(f"Razorpay API failure: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unhandled error creating order: {e}")
        raise HTTPException(status_code=500, detail=f"Order creation failed: {e}")


@router.post("/api/verify-payment")
@router.post("/api/billing/verify")
async def api_verify_payment(payload: VerifyPaymentRequest, request: Request):
    """
    Cryptographically verifies the HMAC-SHA256 signature generated by Razorpay.
    Returns 400 for signature mismatch or missing fields, and credits user on match.
    """
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")

    eff_order_id = payload.order_id or payload.razorpay_order_id
    eff_payment_id = payload.payment_id or payload.razorpay_payment_id
    eff_signature = payload.signature or payload.razorpay_signature

    if not eff_order_id or not eff_payment_id or not eff_signature:
        raise HTTPException(
            status_code=400,
            detail="Missing required payment verification fields (order_id, payment_id, signature)."
        )

    try:
        ok, new_bal, inv_num, msg = process_successful_payment(
            user_id=payload.user_id or "guest_web_user",
            plan_id=payload.plan_id or "single_pass",
            order_id=eff_order_id,
            payment_id=eff_payment_id,
            signature=eff_signature
        )
        if not ok:
            raise HTTPException(
                status_code=400,
                detail=msg or "Payment signature verification failed. Transaction was not confirmed."
            )

        record_usage_event(
            event_type="purchase_success",
            user_id=payload.user_id,
            details={"plan_id": payload.plan_id, "payment_id": eff_payment_id, "invoice": inv_num}
        )

        return json_response_with_cache({
            "success": True,
            "message": "Payment verified successfully",
            "order_id": eff_order_id,
            "payment_id": eff_payment_id,
            "new_balance": new_bal,
            "invoice_number": inv_num
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ==============================================================================
# Client Telemetry Ingestion
# ==============================================================================
@router.post("/api/telemetry/event")
async def api_record_telemetry_event(payload: TelemetryEventRequest, request: Request):
    """Client-side telemetry event capture for user-level journey and acquisition tracking."""
    admin_cookie = request.cookies.get(ADMIN_COOKIE_NAME) or request.cookies.get("admin_session")
    if admin_cookie or _is_admin_authenticated(request):
        return json_response_with_cache({"status": "filtered", "reason": "admin_session"})

    user_agent = request.headers.get("user-agent", "")

    query_params = {}
    if payload.utm_source:
        query_params["utm_source"] = payload.utm_source
    if payload.utm_medium:
        query_params["utm_medium"] = payload.utm_medium
    if payload.utm_campaign:
        query_params["utm_campaign"] = payload.utm_campaign
    if payload.ref:
        query_params["ref"] = payload.ref

    effective_referrer = (payload.referrer or "").strip()
    if not effective_referrer:
        hdr_ref = request.headers.get("referer", "")
        base_host = request.base_url.netloc
        if hdr_ref and base_host not in hdr_ref:
            effective_referrer = hdr_ref

    traffic_source, clean_ref = parse_traffic_source(effective_referrer, query_params)
    client_env = parse_user_agent(user_agent)
    country = extract_geo(dict(request.headers))

    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    sess_id = payload.session_id or f"sess_{hashlib.md5((client_ip + user_agent).encode()).hexdigest()[:10]}"

    evt_details = dict(payload.details or {})
    resolved_lp = payload.landing_page or evt_details.get("landing_page") or ""
    if not resolved_lp and payload.landing_url:
        try:
            from urllib.parse import urlparse
            p = urlparse(payload.landing_url).path
            if p:
                resolved_lp = p
        except Exception as url_err:
            logger.debug("Landing URL parse notice: %s", url_err)
    if not resolved_lp:
        resolved_lp = evt_details.get("path") or evt_details.get("page") or "/"
    if not resolved_lp.startswith("/"):
        resolved_lp = "/" + resolved_lp
    if len(resolved_lp) > 1 and resolved_lp.endswith("/"):
        resolved_lp = resolved_lp.rstrip("/")

    evt_details["landing_page"] = resolved_lp
    if payload.landing_url and "landing_url" not in evt_details:
        evt_details["landing_url"] = payload.landing_url

    if is_excluded_telemetry_event(
        event_type=payload.event_type or "",
        ticker=payload.ticker or "",
        browser=client_env.get("browser", "Chrome"),
        user_id=payload.user_id or "",
        user_email=payload.user_email or "",
        landing_page=resolved_lp,
        session_id=sess_id,
        details=evt_details
    ):
        return json_response_with_cache({"status": "filtered", "reason": "test_or_admin"})

    record_usage_event(
        event_type=payload.event_type,
        ticker=payload.ticker or "",
        details=evt_details,
        session_id=sess_id,
        traffic_source=traffic_source,
        referrer=clean_ref,
        country=country,
        device_type=client_env.get("device", "Unknown"),
        browser=client_env.get("browser", "Unknown"),
        os=client_env.get("os", "Unknown"),
        user_id=payload.user_id,
        user_email=payload.user_email,
        landing_page=resolved_lp
    )
    return json_response_with_cache({"status": "ok"})


@router.get("/api/user/{user_id}")
def api_get_user(user_id: str, request: Request):
    """Fetches user profile only for the authenticated session owner or admin."""
    web_user = _get_current_web_user(request)
    if not _is_admin_authenticated(request):
        if not web_user or web_user.get("id") != user_id.strip():
            raise HTTPException(status_code=403, detail="Forbidden: cannot inspect another user's profile.")
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "success", "user": user}


@router.get("/api/billing/currencies")
async def api_get_currencies(request: Request):
    """
    Returns supported display currencies, reference exchange rates, and buffer info.
    Includes detected currency based on request origin headers or cookies.
    """
    detected_currency = resolve_currency_for_request(request)
    return json_response_with_cache({
        "success": True,
        "base_currency": "INR",
        "detected_currency": detected_currency,
        "buffer_pct": 3.5,
        "currencies": SUPPORTED_CURRENCIES
    })


@router.get("/api/notifications/unsubscribe")
async def api_unsubscribe_notifications(request: Request, token: Optional[str] = None, email: Optional[str] = None):
    """
    Statutory 1-Click Unsubscribe Endpoint (IT Rules 2021 & Anti-Spam Compliance).
    Supports token-based or email-based unsubscribes.
    Returns clean confirmation HTML for browser navigation, or JSON for programmatic requests.
    """
    from core.db.digest import set_user_digest_subscription, get_subscriber_by_token

    param = (token or email or "").strip()
    if not param:
        raise HTTPException(status_code=400, detail="Missing unsubscribe token or email parameter.")

    subscriber = get_subscriber_by_token(param)
    success = set_user_digest_subscription(param, subscribe=False)

    accept_header = request.headers.get("accept", "")
    is_html_request = "text/html" in accept_header

    if is_html_request:
        email_display = subscriber["email"] if subscriber else param
        resubscribe_url = f"/api/notifications/resubscribe?token={urllib.parse.quote(param)}"
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Unsubscribed — Moatnomics Research</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b1329; color: #f8fafc; margin: 0; padding: 40px 16px; display: flex; align-items: center; justify-content: center; min-height: 80vh; }}
    .card {{ background: #131d38; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; max-width: 520px; width: 100%; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.4); text-align: center; }}
    .icon {{ font-size: 40px; margin-bottom: 16px; }}
    h1 {{ font-size: 22px; font-weight: 800; margin: 0 0 10px; color: #ffffff; }}
    p {{ font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0 0 20px; }}
    .email-badge {{ background: rgba(14,165,233,0.15); color: #38bdf8; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-family: monospace; }}
    .btn {{ display: inline-block; padding: 10px 20px; border-radius: 8px; font-size: 13.5px; font-weight: 700; text-decoration: none; cursor: pointer; transition: all 0.2s; }}
    .btn-secondary {{ background: rgba(255,255,255,0.06); color: #e2e8f0; border: 1px solid rgba(255,255,255,0.15); }}
    .btn-secondary:hover {{ background: rgba(255,255,255,0.12); }}
    .btn-undo {{ background: #0ea5e9; color: #020617; border: none; margin-right: 10px; }}
    .footer-note {{ font-size: 12px; color: #64748b; margin-top: 24px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✉️</div>
    <h1>You have been unsubscribed</h1>
    <p>
      We have updated your preferences. <span class="email-badge">{email_display}</span> will no longer receive the daily Moatnomics Research Bouquet and Morning Digest.
    </p>
    <div style="margin-top: 24px;">
      <a href="{resubscribe_url}" class="btn btn-undo">Undo &amp; Re-subscribe</a>
      <a href="/" class="btn btn-secondary">Return to Platform</a>
    </div>
    <div class="footer-note">
      Your research credits, bookmarks, and account access remain unaffected.
    </div>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)

    return JSONResponse(status_code=200, content={
        "success": True,
        "unsubscribed": success,
        "message": f"Successfully unsubscribed from Moatnomics Research Digest."
    })


@router.get("/api/notifications/resubscribe")
async def api_resubscribe_notifications(request: Request, token: Optional[str] = None, email: Optional[str] = None):
    """Re-subscribes user to Research Digest."""
    from core.db.digest import set_user_digest_subscription

    param = (token or email or "").strip()
    if not param:
        raise HTTPException(status_code=400, detail="Missing token or email parameter.")

    success = set_user_digest_subscription(param, subscribe=True)

    accept_header = request.headers.get("accept", "")
    is_html_request = "text/html" in accept_header

    if is_html_request:
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Re-subscribed — Moatnomics Research</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b1329; color: #f8fafc; margin: 0; padding: 40px 16px; display: flex; align-items: center; justify-content: center; min-height: 80vh; }}
    .card {{ background: #131d38; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; max-width: 520px; width: 100%; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.4); text-align: center; }}
    .icon {{ font-size: 40px; margin-bottom: 16px; }}
    h1 {{ font-size: 22px; font-weight: 800; margin: 0 0 10px; color: #ffffff; }}
    p {{ font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0 0 20px; }}
    .btn {{ display: inline-block; padding: 10px 20px; border-radius: 8px; font-size: 13.5px; font-weight: 700; text-decoration: none; background: #0ea5e9; color: #020617; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>Subscription Restored</h1>
    <p>You have successfully re-subscribed to the daily Moatnomics Research Bouquet and Morning Digest.</p>
    <a href="/" class="btn">Return to Platform</a>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)

    return JSONResponse(status_code=200, content={
        "success": True,
        "subscribed": success,
        "message": "Successfully re-subscribed to Moatnomics Research Digest."
    })

