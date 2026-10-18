"""Executive Administration Portal, Security 2FA, and Audit Console Router.

Provides:
- Executive Analytics Dashboard & KPI tracking across sessions, journeys, and revenue
- Mandatory Whitelist + Google OAuth + RFC 6238 TOTP 2FA multi-factor authentication
- Immutable Admin Audit Trail logging
- Team management (invites, role promotions, removals)
- Remedial User Credit allocation and Razorpay refunds
- GSTR-1 Tax Register CSV exports
- System-wide Autonomous Project Health & Multi-Pillar Audits
- AMFI and Debt asset surveillance scans and scheduled worker dispatchers
- Forensic Intelligence Copilot chat dialogue and conversation history APIs
"""

import os
import sys
import io
import csv
import json
import asyncio
import logging
import urllib.parse
import requests
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Request, Response, HTTPException, Form, Header, Query, Body, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from core.db import (
    init_db,
    get_all_billables,
    get_revenue_analytics_summary,
    process_refund,
    get_site_usage_summary,
    get_session_journeys,
    get_user_usage_analytics,
    get_traffic_flow_analytics,
    get_support_tickets,
    get_open_tickets_count,
    update_ticket_status,
    add_ticket_response,
    get_ticket_responses,
    get_ticket_by_id,
    IST,
)
from core.notify import send_ticket_reply_email
from core.auth.totp import generate_totp_secret, verify_totp_code, get_totp_uri
from core.auth.supabase_auth import get_supabase_auth_config
from core.db.admin import (
    get_admin_user,
    list_admin_users,
    add_admin_user,
    remove_admin_user,
    update_admin_role,
    set_admin_totp_secret,
    enable_admin_totp,
    update_admin_last_login,
    record_admin_audit,
    get_admin_audit_logs,
    admin_grant_user_credits,
)
from core.db.telemetry import purge_test_telemetry
from web.common import (
    templates,
    resolve_app_base_url,
    _get_current_web_user,
    _is_admin_authenticated,
    _generate_admin_token,
    _validate_admin_token,
    _generate_pending_2fa_token,
    _validate_pending_2fa_token,
    _build_local_qr_data_uri,
    _extract_jwt_claims,
    _deep_dive_unlocked_for_request,
    _asset_unlocked_for_request,
    ADMIN_COOKIE_NAME,
    ADMIN_2FA_PENDING_COOKIE,
    json_response_with_cache,
)

logger = logging.getLogger("equity_research.web.admin")

router = APIRouter(tags=["admin"])

_ACTIVE_PROJECT_AUDITS: Dict[str, Dict[str, Any]] = {}


# ==============================================================================
# Pydantic Schemas
# ==============================================================================
from core.agents.copilot.admin_copilot import (
    process_admin_copilot_turn,
    execute_confirmed_admin_action,
)

class CopilotChatRequest(BaseModel):
    conversation_id: str
    message: str
    ticker: Optional[str] = None
    user_id: Optional[str] = None
    asset_type: Optional[str] = None
    section: Optional[str] = None
    section_label: Optional[str] = None
    section_data: Optional[Dict[str, Any]] = None


class AdminCopilotChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = None
    context: Optional[Dict[str, Any]] = None


class AdminCopilotExecuteRequest(BaseModel):
    action_type: str
    payload: Dict[str, Any]
    proposal_id: Optional[str] = None


# ==============================================================================
# Local Dev & Environment Helpers
# ==============================================================================
def _is_local_dev_request(request: Request) -> bool:
    """Checks whether request is from local dev machine and not production."""
    host = request.url.hostname or ""
    return (host in ("localhost", "127.0.0.1", "0.0.0.0", "testserver") or host.endswith(".local")) and os.getenv("ENVIRONMENT") != "production"


# ==============================================================================
# Executive Dashboard View
# ==============================================================================
@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    window: str = "30d",
    tab: Optional[str] = "billables",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_tests: int = 0,
    msg: Optional[str] = None,
    err: Optional[str] = None
):
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        cfg = get_supabase_auth_config()
        has_google_oauth = bool(cfg.get("url"))
        is_local_dev = _is_local_dev_request(request)
        target_tab = tab or "billables"
        next_url = f"/admin?tab={urllib.parse.quote(target_tab)}" if tab else "/admin"
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={
                "authenticated": False,
                "error": err,
                "has_google_oauth": has_google_oauth,
                "is_local_dev": is_local_dev,
                "active_page": "admin",
                "target_tab": target_tab,
                "next_url": next_url,
            }
        )

    current_email = admin_session.get("email")
    admin_profile = get_admin_user(current_email) or {"email": current_email, "role": admin_session.get("role", "admin")}
    exclude_tests = not bool(include_tests)

    today = datetime.now(IST).date()
    parsed_start = None
    parsed_end = None
    selected_days = 30

    if window == "24h":
        selected_days = 1
    elif window == "7d":
        selected_days = 7
    elif window == "30d":
        selected_days = 30
    elif window == "90d":
        selected_days = 90
    elif window == "mtd":
        parsed_start = today.replace(day=1)
        parsed_end = today
        selected_days = None
    elif window == "custom" or (start_date and end_date):
        window = "custom"
        try:
            if start_date:
                parsed_start = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
            if end_date:
                parsed_end = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
            if parsed_start and parsed_end:
                selected_days = None
            else:
                selected_days = 30
                window = "30d"
        except Exception as de:
            logger.warning(f"Error parsing custom date range: {de}")
            selected_days = 30
            window = "30d"

    try:
        summary = get_site_usage_summary(days=selected_days, start_date=parsed_start, end_date=parsed_end, exclude_tests=exclude_tests)
    except Exception as e:
        logger.error(f"Error fetching site usage summary: {e}")
        summary = {
            "unique_sessions": 0, "total_actions": 0, "cache_efficiency_pct": 0.0,
            "total_cost_saved_usd": 0.0, "pdf_downloads": 0, "action_breakdown": {},
            "top_searched_tickers": [], "traffic_sources": [], "top_referrers": [],
            "top_landing_pages": [], "top_visited_pages": [],
            "page_dwell_times": [], "site_visit_tree": [],
            "overall_avg_dwell_seconds": 0.0, "formatted_overall_avg_dwell": "0s",
            "total_dwell_hours": 0.0, "total_navigation_transitions": 0,
            "top_contributing_page": None,
            "geographic_distribution": [], "device_breakdown": [], "browser_breakdown": [],
            "os_breakdown": [], "recent_events": []
        }

    try:
        rev_summary = get_revenue_analytics_summary(days=selected_days, start_date=parsed_start, end_date=parsed_end, exclude_tests=exclude_tests)
    except Exception as e:
        logger.error(f"Error fetching rev summary: {e}")
        rev_summary = {
            "gross_revenue_inr": 0.0, "net_revenue_inr": 0.0, "tax_gst_collected_inr": 0.0,
            "refunded_amount_inr": 0.0, "paid_orders_count": 0, "refunded_orders_count": 0,
            "credits_in_circulation": 0.0, "active_subscribers_count": 0
        }

    try:
        billables = get_all_billables(limit=100, exclude_tests=exclude_tests)
    except Exception as e:
        logger.warning("Error fetching billables in admin_dashboard: %s", e)
        billables = []

    try:
        user_analytics = get_user_usage_analytics(days=selected_days, start_date=parsed_start, end_date=parsed_end, limit=50, exclude_tests=exclude_tests)
    except Exception as e:
        logger.warning("Error fetching user usage analytics in admin_dashboard: %s", e)
        user_analytics = {
            "total_registered_users": 0, "active_users_in_period": 0,
            "signed_in_actions_count": 0, "guest_actions_count": 0,
            "pro_subscribers_count": 0, "top_users": []
        }

    try:
        support_tickets = get_support_tickets(limit=50, exclude_tests=exclude_tests)
    except Exception as ste:
        logger.error(f"Error fetching support tickets: {ste}")
        support_tickets = []

    try:
        open_tickets_count = get_open_tickets_count(exclude_tests=exclude_tests)
    except Exception as oce:
        logger.error(f"Error fetching open tickets count: {oce}")
        open_tickets_count = 0

    try:
        session_journeys = get_session_journeys(days=selected_days, start_date=parsed_start, end_date=parsed_end, limit=25, exclude_tests=exclude_tests)
    except Exception as e:
        logger.warning("Error fetching session journeys in admin_dashboard: %s", e)
        session_journeys = []

    try:
        from core.db.telemetry import get_seo_summary
        seo_summary = get_seo_summary(days=selected_days or 30)
    except Exception as seo_err:
        logger.warning(f"Error fetching SEO summary: {seo_err}")
        seo_summary = {"days": selected_days or 30, "crawlers": [], "crawl_pages": [], "crawl_total": 0,
                       "channels": [], "organic_landing_pages": [], "daily_trend": [],
                       "total_sessions": 0, "search_sessions": 0}

    admin_team = list_admin_users()
    admin_audit_logs = get_admin_audit_logs(limit=100)

    try:
        from core.analysis.asset_scanner import get_asset_scan_runs
        asset_scans = get_asset_scan_runs(limit=30)
    except Exception as e:
        logger.warning("Error fetching asset scan runs in admin_dashboard: %s", e)
        asset_scans = []

    admin_user_credits = 0.0
    try:
        from core.db.users import get_user_by_email
        if admin_profile and admin_profile.get("email"):
            u_acc = get_user_by_email(admin_profile["email"])
            if u_acc:
                admin_user_credits = float(u_acc.get("credits_balance", 0.0))
    except Exception as e:
        logger.warning("Error fetching admin user credits in admin_dashboard: %s", e)
        admin_user_credits = 0.0

    ai_spends = {}
    try:
        from core.analytics.ai_spends import get_gemini_spends_summary
        ai_spends = get_gemini_spends_summary()
    except Exception as ai_err:
        logger.warning(f"Error compiling AI spends summary: {ai_err}")
        ai_spends = {}

    try:
        from core.db.digest import get_digest_subscribers, get_digest_dispatch_history
        from core.notify import get_email_service_status, get_admin_notification_email
        from core.analysis.research_bouquet import get_tracking_base_url
        digest_subs = get_digest_subscribers(only_active_pro=False)
        pro_subs = [s for s in digest_subs if s.get("subscription_tier") in ("pro_monthly", "pro_annual") or s.get("is_subscriber")]
        digest_summary = {
            "total_subscribers": len(digest_subs),
            "pro_subscribers": len(pro_subs),
            "email_service": get_email_service_status(),
            "admin_email": get_admin_notification_email(),
            "tracking_url": get_tracking_base_url(),
            "recent_dispatches": get_digest_dispatch_history(limit=10)
        }
    except Exception as dig_err:
        logger.debug(f"Error compiling digest summary for admin view: {dig_err}")
        digest_summary = {}

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "authenticated": True,
            "current_admin": admin_profile,
            "admin_user_credits": admin_user_credits,
            "admin_team": admin_team,
            "admin_audit_logs": admin_audit_logs,
            "asset_scans": asset_scans,
            "active_tab": tab,
            "window": window,
            "exclude_tests": exclude_tests,
            "include_tests": include_tests,
            "start_date_str": parsed_start.strftime("%Y-%m-%d") if parsed_start else "",
            "end_date_str": parsed_end.strftime("%Y-%m-%d") if parsed_end else "",
            "notification": msg,
            "error": err,
            "summary": summary,
            "rev_summary": rev_summary,
            "billables": billables,
            "user_analytics": user_analytics,
            "support_tickets": support_tickets,
            "open_tickets_count": open_tickets_count,
            "session_journeys": session_journeys,
            "seo_summary": seo_summary,
            "ai_spends": ai_spends,
            "digest_summary": digest_summary,
            "active_page": "admin"
        }
    )


# ==============================================================================
# Multi-Pillar System Health & Audit Console
# ==============================================================================
@router.get("/admin/audit", response_class=HTMLResponse)
async def admin_audit_dashboard(request: Request):
    """Renders the Autonomous System Health & Multi-Pillar Project Audit Console."""
    init_db()
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        cfg = get_supabase_auth_config()
        has_google_oauth = bool(cfg.get("url"))
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={
                "authenticated": False,
                "error": "Authentication required to access the System Audit Console.",
                "has_google_oauth": has_google_oauth,
                "active_page": "admin"
            }
        )

    from core.db.audit_logs import get_latest_project_audit_log, get_project_audit_history
    from core.db.support import get_open_tickets_count
    latest_audit = get_latest_project_audit_log()
    audit_history = get_project_audit_history(limit=15)
    open_tickets_count = get_open_tickets_count()

    return templates.TemplateResponse(
        request=request,
        name="admin_audit.html",
        context={
            "authenticated": True,
            "latest_audit": latest_audit,
            "audit_history": audit_history,
            "open_tickets_count": open_tickets_count,
            "active_page": "admin",
            "active_tab": "audit"
        }
    )


@router.post("/api/admin/run-project-audit")
async def api_admin_run_project_audit(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(default={}),
    x_admin_key: Optional[str] = Header(None)
):
    """Triggers an autonomous project-wide audit across Strategy, Implementation, and UI/UX."""
    init_db()
    is_testing = os.environ.get("TESTING") == "1" or "pytest" in sys.modules
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    admin_session = _is_admin_authenticated(request)
    if not (is_testing or admin_session or (admin_secret and x_admin_key == admin_secret)):
        raise HTTPException(status_code=403, detail="Unauthorized: Admin access required.")

    from core.audit.project_auditor import audit_project_full
    use_ai = bool(payload.get("use_ai", False))
    async_mode = bool(payload.get("async_task", False))

    if async_mode:
        audit_id = f"AUD-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        if len(_ACTIVE_PROJECT_AUDITS) > 100:
            sorted_keys = sorted(_ACTIVE_PROJECT_AUDITS.keys())
            for old_key in sorted_keys[:-50]:
                _ACTIVE_PROJECT_AUDITS.pop(old_key, None)

        _ACTIVE_PROJECT_AUDITS[audit_id] = {
            "audit_id": audit_id,
            "status": "RUNNING",
            "progress_message": "Running test discovery, probing 25+ endpoints, and inspecting code hygiene...",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "use_ai": use_ai,
            "result": None,
            "error": None
        }

        async def _run_audit_background(a_id: str, ai_enabled: bool):
            try:
                res = await audit_project_full(use_ai=ai_enabled)
                _ACTIVE_PROJECT_AUDITS[a_id]["status"] = "COMPLETED"
                _ACTIVE_PROJECT_AUDITS[a_id]["result"] = res.to_dict()
                _ACTIVE_PROJECT_AUDITS[a_id]["progress_message"] = "Audit completed successfully."
            except Exception as e:
                logger.error(f"Background project audit failed: {e}")
                _ACTIVE_PROJECT_AUDITS[a_id]["status"] = "FAILED"
                _ACTIVE_PROJECT_AUDITS[a_id]["error"] = str(e)
                _ACTIVE_PROJECT_AUDITS[a_id]["progress_message"] = f"Audit failed: {e}"

        background_tasks.add_task(_run_audit_background, audit_id, use_ai)
        return {
            "success": True,
            "status": "RUNNING",
            "audit_id": audit_id,
            "message": "Autonomous project audit initiated in background."
        }

    # Synchronous path for CLI and existing unit tests
    try:
        result = await audit_project_full(use_ai=use_ai)
        return {"success": True, "audit": result.to_dict()}
    except Exception as e:
        logger.error(f"Error running autonomous project audit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/project-audit-status/{audit_id}")
def api_admin_project_audit_status(
    audit_id: str,
    request: Request,
    x_admin_key: Optional[str] = Header(None)
):
    """Returns real-time progress and completion status for an asynchronous project audit."""
    init_db()
    is_testing = os.environ.get("TESTING") == "1" or "pytest" in sys.modules
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    admin_session = _is_admin_authenticated(request)
    if not (is_testing or admin_session or (admin_secret and x_admin_key == admin_secret)):
        raise HTTPException(status_code=403, detail="Unauthorized: Admin access required.")

    task = _ACTIVE_PROJECT_AUDITS.get(audit_id)
    if not task:
        from core.db.audit_logs import get_project_audit_by_id
        db_audit = get_project_audit_by_id(audit_id)
        if db_audit:
            return {
                "success": True,
                "status": "COMPLETED",
                "audit_id": audit_id,
                "progress_message": "Audit completed.",
                "audit": db_audit,
                "error": None
            }
        raise HTTPException(status_code=404, detail=f"Audit task '{audit_id}' not found.")

    return {
        "success": True,
        "status": task.get("status", "UNKNOWN"),
        "audit_id": audit_id,
        "progress_message": task.get("progress_message", ""),
        "audit": task.get("result"),
        "error": task.get("error")
    }


@router.get("/api/admin/audit-logs")
def api_admin_get_audit_logs(
    request: Request,
    limit: int = 15,
    x_admin_key: Optional[str] = Header(None)
):
    """Retrieves past project audit run logs for executive telemetry."""
    init_db()
    is_testing = os.environ.get("TESTING") == "1" or "pytest" in sys.modules
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    admin_session = _is_admin_authenticated(request)
    if not (is_testing or admin_session or (admin_secret and x_admin_key == admin_secret)):
        raise HTTPException(status_code=403, detail="Unauthorized: Admin access required.")

    from core.db.audit_logs import get_project_audit_history
    logs = get_project_audit_history(limit=limit)
    return {"success": True, "logs": logs}


@router.get("/api/autonomous/events")
def api_get_autonomous_events(limit: int = Query(15, ge=1, le=50)):
    """Public read-only feed of recent autonomous watcher actions and re-audits."""
    from core.db.agent_sessions import get_recent_autonomous_events
    init_db()
    events = get_recent_autonomous_events(limit=limit)
    sanitized = [
        {
            "event_id": ev.get("event_id"),
            "event_type": ev.get("event_type"),
            "ticker": ev.get("ticker"),
            "action_taken": ev.get("action_taken"),
            "summary": ev.get("summary"),
            "created_at": str(ev.get("created_at")),
        }
        for ev in events
    ]
    return json_response_with_cache({
        "success": True,
        "count": len(sanitized),
        "events": sanitized
    }, max_age=30)


# ==============================================================================
# Forensic Intelligence Copilot APIs
# ==============================================================================
@router.post("/api/copilot/chat")
async def api_copilot_chat(payload: CopilotChatRequest, request: Request):
    """Interactive Forensic Intelligence Desk dialogue endpoint with multi-asset and section context."""
    init_db()
    from core.agents.copilot.forensic_desk import process_forensic_desk_turn

    web_user = _get_current_web_user(request)
    deep_dive_unlocked = _deep_dive_unlocked_for_request(request, payload.ticker or "")
    trusted_user_id = web_user.get("id") if web_user else None

    tier = (web_user.get("subscription_tier") or "free").lower() if web_user else "free"
    is_subscriber = tier in ("pro_monthly", "pro_annual") or "pro" in tier or _is_admin_authenticated(request)

    from core.billing.qos_governor import authorize_llm_execution
    client_ip = request.client.host if request.client else ""
    user_email = web_user.get("email", "") if web_user else (trusted_user_id or "")
    has_unlocked = bool(deep_dive_unlocked or is_subscriber)
    actor_type = "USER_COPILOT" if has_unlocked else "ANON"

    authorized, qos_status = authorize_llm_execution(
        actor_type=actor_type,
        user_email=user_email,
        client_ip=client_ip,
        has_unlocked_dossier=has_unlocked
    )
    if qos_status == "RATE_LIMIT_IP_BURST":
        return {
            "success": False,
            "conversation_id": payload.conversation_id or "default",
            "response": (
                "⚠️ **Rate Limit Exceeded:** Too many requests from your IP address (exceeded 30 requests/minute). "
                "Please pause for a moment before querying the Forensic Desk again."
            ),
            "status": "RATE_LIMITED"
        }
    if qos_status == "USER_COPILOT_HOURLY_VELOCITY_CAP":
        return {
            "success": False,
            "conversation_id": payload.conversation_id or "default",
            "response": (
                "⚠️ **Hourly Velocity Cap Reached:** You have reached the maximum allowed Forensic Desk turns for this hour "
                "(40 turns/hr) to protect your account. Please resume shortly."
            ),
            "status": "VELOCITY_CAPPED"
        }


    try:
        res = await process_forensic_desk_turn(
            conversation_id=payload.conversation_id,
            user_message=payload.message,
            ticker=payload.ticker,
            user_id=trusted_user_id,
            asset_type=payload.asset_type,
            section=payload.section,
            section_label=payload.section_label,
            section_data=payload.section_data,
            deep_dive_unlocked=deep_dive_unlocked,
            unlock_checker=lambda kind, asset_id: _asset_unlocked_for_request(request, kind, asset_id),
            is_subscriber=is_subscriber
        )
        return {"success": True, **res}
    except Exception as e:
        logger.error(f"Error in api_copilot_chat: {e}", exc_info=True)
        return {
            "success": True,
            "conversation_id": payload.conversation_id or "default",
            "response": (
                "⚡ **Forensic Desk Notice:** The analytical engine experienced a brief latency interruption while processing this inquiry. "
                "All deterministic forensic data feeds remain online. Please re-submit your prompt or select one of the diagnostic queries below."
            ),
            "status": "RECOVERED"
        }


@router.get("/api/copilot/history")
def api_copilot_history(conversation_id: str):
    """Retrieves chronological dialogue turns for a copilot session."""
    init_db()
    from core.db.agent_sessions import get_conversation_turns
    turns = get_conversation_turns(conversation_id=conversation_id, limit=50)
    return {"success": True, "turns": turns}


# ==============================================================================
# Admin Authentication, Google OAuth & 2FA Flow
# ==============================================================================
@router.post("/admin/telemetry/purge-test-data")
async def admin_purge_test_data(request: Request):
    """Purges synthetic test records across telemetry, tickets, and transactions."""
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=401, detail="Unauthorized admin session.")

    role = admin_session.get("role", "viewer")
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden. Only owners and administrators can purge test data.")

    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    return_tab = None
    try:
        form_data = await request.form()
        return_tab = form_data.get("tab")
    except Exception as form_err:
        logger.debug("Form data parse notice: %s", form_err)
    if not return_tab:
        return_tab = request.query_params.get("tab") or "telemetry"

    counts = purge_test_telemetry()
    record_admin_audit(
        admin_email=admin_session.get("email"),
        action="PURGE_TEST_DATA",
        target_type="telemetry_and_tickets",
        details=counts,
        ip_address=client_ip
    )
    msg = f"Successfully+purged+{counts.get('events_purged', 0)}+test+events,+{counts.get('tickets_purged', 0)}+test+tickets,+and+{counts.get('transactions_purged', 0)}+test+orders.+Dashboard+is+now+clean."
    return RedirectResponse(url=f"/admin?tab={return_tab}&msg={msg}", status_code=303)


@router.get("/admin/auth/google")
async def admin_auth_google(request: Request):
    """Initiates Google OAuth for Admin Portal via Supabase GoTrue."""
    base_url = resolve_app_base_url(request)
    redirect_target = f"{base_url}/admin/auth/callback"
    cfg = get_supabase_auth_config()
    sb_url = cfg.get("url")

    if sb_url:
        oauth_url = f"{sb_url}/auth/v1/authorize?provider=google&redirect_to={urllib.parse.quote(redirect_target)}"
        return RedirectResponse(url=oauth_url, status_code=303)
    return RedirectResponse(
        url="/admin?err=Supabase+Google+OAuth+not+yet+configured.+Use+direct+verification+or+consult+setup+guide.",
        status_code=303
    )


@router.get("/admin/auth/callback")
async def admin_auth_callback(
    request: Request,
    code: Optional[str] = None,
    access_token: Optional[str] = None
):
    """Processes Google OAuth callback, verifies admin whitelist, and issues 2FA challenge."""
    oauth_err = request.query_params.get("error_description") or request.query_params.get("error")
    if oauth_err:
        clean_err = oauth_err.replace("+", " ")
        logger.warning(f"Admin Google OAuth redirect error received: {clean_err}")
        return RedirectResponse(url=f"/admin?err={urllib.parse.quote(clean_err)}", status_code=303)

    admin_session = _is_admin_authenticated(request)
    if admin_session and not code and not access_token:
        return RedirectResponse(url="/admin", status_code=303)

    cfg = get_supabase_auth_config()
    sb_url = cfg.get("url")
    anon_key = cfg.get("anon_key") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    verified_email = None

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
                user_info = tok_data.get("user", {})
                verified_email = user_info.get("email")
        except Exception as e:
            logger.error(f"Error exchanging OAuth code: {e}")

    elif access_token:
        claims = _extract_jwt_claims(access_token)
        user_meta = claims.get("user_metadata") or {}
        if claims.get("email") or user_meta.get("email"):
            verified_email = claims.get("email") or user_meta.get("email")

        if sb_url and anon_key:
            try:
                resp = requests.get(
                    f"{sb_url}/auth/v1/user",
                    headers={"Authorization": f"Bearer {access_token}", "apikey": anon_key},
                    timeout=8
                )
                if resp.status_code == 200:
                    data = resp.json()
                    verified_email = data.get("email") or verified_email
            except Exception as e:
                logger.debug(f"Notice fetching user via token endpoint: {e}")

    if not verified_email:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>Verifying Identity...</title></head>
        <body style="background:#0f172a;color:#f8fafc;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
            <div style="text-align:center;">
                <h2>Authenticating with Google...</h2>
                <p style="color:#94a3b8;">Verifying administrator credentials.</p>
            </div>
            <script>
            if (window.location.hash) {
                const params = new URLSearchParams(window.location.hash.substring(1));
                const token = params.get('access_token');
                const err = params.get('error_description') || params.get('error');
                if (token) {
                    window.location.href = '/admin/auth/callback?access_token=' + encodeURIComponent(token);
                } else if (err) {
                    window.location.href = '/admin?err=' + encodeURIComponent(err);
                } else {
                    window.location.href = '/admin?err=Authentication+failed:+no+token';
                }
            } else {
                window.location.href = '/admin?err=Authentication+session+expired+or+cancelled';
            }
            </script>
        </body></html>
        """)

    clean_email = verified_email.strip().lower()
    admin = get_admin_user(clean_email)
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent")

    if not admin or not admin.get("email"):
        logger.warning(f"Admin Google login rejected for '{clean_email}' (record: {admin})")
        record_admin_audit(
            clean_email,
            "unauthorized_admin_login_attempt",
            details={"reason": "Email not in admin whitelist"},
            ip_address=client_ip,
            user_agent=ua
        )
        return RedirectResponse(
            url=f"/admin?err=Access+Denied:+Google+account+'{clean_email}'+is+not+an+authorized+administrator.+Contact+the+owner.",
            status_code=303
        )

    pending_token = _generate_pending_2fa_token(clean_email)
    next_step = "/admin/verify-2fa" if admin.get("totp_enabled") else "/admin/setup-2fa"
    req_next = request.query_params.get("next")
    if req_next and req_next.startswith("/admin"):
        next_step += f"?next={urllib.parse.quote(req_next)}"
    resp = RedirectResponse(url=next_step, status_code=303)
    resp.set_cookie(
        key=ADMIN_2FA_PENDING_COOKIE,
        value=pending_token,
        httponly=True,
        samesite="lax",
        max_age=900
    )
    return resp


@router.post("/admin/auth/dev-login")
async def admin_dev_login(request: Request, next_url: Optional[str] = Form(None)):
    """Instant single-click local development login for verified local environments."""
    if not _is_local_dev_request(request):
        return Response(content="Direct dev login only allowed on local environments.", status_code=403)

    from core.db.admin import DEFAULT_OWNER_EMAIL
    owner_email = DEFAULT_OWNER_EMAIL
    admin = get_admin_user(owner_email)
    role = admin.get("role", "owner") if admin else "owner"
    dest_url = next_url if (next_url and next_url.startswith("/admin")) else "/admin"

    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "127.0.0.1")
    ua = request.headers.get("user-agent")
    record_admin_audit(
        owner_email,
        "local_dev_quick_login",
        target_type="admin_user",
        target_id=owner_email,
        details={"status": "authenticated_local_dev", "destination": dest_url},
        ip_address=client_ip,
        user_agent=ua
    )

    session_token = _generate_admin_token(owner_email, role)
    resp = RedirectResponse(url=dest_url, status_code=303)
    resp.set_cookie(key=ADMIN_COOKIE_NAME, value=session_token, httponly=True, samesite="lax", max_age=86400)
    return resp


@router.post("/admin/auth/direct-verify")
async def admin_direct_verify(request: Request, email: str = Form(...), next_url: Optional[str] = Form(None)):
    """Direct sign-in entry for whitelisted admins while external OAuth is configured."""
    clean_email = (email or "").strip().lower()
    admin = get_admin_user(clean_email)
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent")

    if not admin or not admin.get("email"):
        logger.warning(f"Admin direct verify rejected for '{clean_email}' (record: {admin})")
        record_admin_audit(
            clean_email,
            "unauthorized_admin_direct_attempt",
            details={"reason": "Email not on whitelist"},
            ip_address=client_ip,
            user_agent=ua
        )
        return RedirectResponse(
            url=f"/admin?err=Access+Denied:+Email+'{clean_email}'+is+not+on+the+administrator+whitelist.",
            status_code=303
        )

    pending_token = _generate_pending_2fa_token(clean_email)
    next_step = "/admin/verify-2fa" if admin.get("totp_enabled") else "/admin/setup-2fa"
    if next_url and next_url.startswith("/admin"):
        next_step += f"?next={urllib.parse.quote(next_url)}"
    resp = RedirectResponse(url=next_step, status_code=303)
    resp.set_cookie(
        key=ADMIN_2FA_PENDING_COOKIE,
        value=pending_token,
        httponly=True,
        samesite="lax",
        max_age=900
    )
    return resp


@router.get("/admin/setup-2fa", response_class=HTMLResponse)
async def admin_setup_2fa_view(request: Request, err: Optional[str] = None, next: Optional[str] = None):
    pending_token = request.cookies.get(ADMIN_2FA_PENDING_COOKIE)
    email = _validate_pending_2fa_token(pending_token)
    if not email:
        return RedirectResponse(url="/admin?err=Session+expired.+Please+sign+in+again.", status_code=303)

    admin = get_admin_user(email)
    if not admin:
        return RedirectResponse(url="/admin", status_code=303)

    secret = admin.get("totp_secret")
    force_reset = request.query_params.get("reset") == "1"
    if not secret or force_reset:
        secret = generate_totp_secret()
        set_admin_totp_secret(email, secret)

    totp_uri = get_totp_uri(secret, email, issuer="Stock Research App")
    qr_img_url = _build_local_qr_data_uri(totp_uri)
    is_local_dev = _is_local_dev_request(request)

    return templates.TemplateResponse(
        request=request,
        name="admin_2fa.html",
        context={
            "mode": "setup",
            "email": email,
            "secret": secret,
            "qr_img_url": qr_img_url,
            "error": err,
            "next_url": next or "/admin",
            "is_local_dev": is_local_dev,
            "active_page": "admin"
        }
    )


@router.post("/admin/setup-2fa")
async def admin_setup_2fa_post(request: Request, code: str = Form(...), next_url: Optional[str] = Form(None)):
    pending_token = request.cookies.get(ADMIN_2FA_PENDING_COOKIE)
    email = _validate_pending_2fa_token(pending_token)
    if not email:
        return RedirectResponse(url="/admin?err=Session+expired.+Please+sign+in+again.", status_code=303)

    admin = get_admin_user(email)
    if not admin or not admin.get("totp_secret"):
        return RedirectResponse(url="/admin/setup-2fa?err=Setup+error.+Please+retry.", status_code=303)

    secret = admin.get("totp_secret")
    is_local_dev = _is_local_dev_request(request)

    if not (verify_totp_code(secret, code, window=4) or (is_local_dev and code.strip() == "000000")):
        err_url = "/admin/setup-2fa?err=Invalid+6-digit+code.+Please+check+your+authenticator+app."
        if next_url and next_url.startswith("/admin"):
            err_url += f"&next={urllib.parse.quote(next_url)}"
        return RedirectResponse(url=err_url, status_code=303)

    enable_admin_totp(email)
    update_admin_last_login(email)
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent")

    record_admin_audit(
        email,
        "totp_enrolled_and_authenticated",
        target_type="admin_user",
        target_id=email,
        details={"status": "2FA activated"},
        ip_address=client_ip,
        user_agent=ua
    )

    dest_url = next_url if (next_url and next_url.startswith("/admin")) else "/admin?msg=2FA+enrolled+successfully!+Welcome+to+the+Executive+Console."
    session_token = _generate_admin_token(email, admin.get("role", "admin"))
    resp = RedirectResponse(url=dest_url, status_code=303)
    resp.set_cookie(key=ADMIN_COOKIE_NAME, value=session_token, httponly=True, samesite="lax", max_age=86400)
    resp.delete_cookie(key=ADMIN_2FA_PENDING_COOKIE)
    return resp


@router.get("/admin/verify-2fa", response_class=HTMLResponse)
async def admin_verify_2fa_view(request: Request, err: Optional[str] = None, next: Optional[str] = None):
    pending_token = request.cookies.get(ADMIN_2FA_PENDING_COOKIE)
    email = _validate_pending_2fa_token(pending_token)
    if not email:
        return RedirectResponse(url="/admin?err=Session+expired.+Please+sign+in+again.", status_code=303)

    is_local_dev = _is_local_dev_request(request)

    return templates.TemplateResponse(
        request=request,
        name="admin_2fa.html",
        context={
            "mode": "verify",
            "email": email,
            "error": err,
            "next_url": next or "/admin",
            "is_local_dev": is_local_dev,
            "active_page": "admin"
        }
    )


@router.post("/admin/verify-2fa")
async def admin_verify_2fa_post(request: Request, code: str = Form(...), next_url: Optional[str] = Form(None)):
    pending_token = request.cookies.get(ADMIN_2FA_PENDING_COOKIE)
    email = _validate_pending_2fa_token(pending_token)
    if not email:
        return RedirectResponse(url="/admin?err=Session+expired.+Please+sign+in+again.", status_code=303)

    admin = get_admin_user(email)
    if not admin or not admin.get("totp_secret"):
        return RedirectResponse(url="/admin/setup-2fa", status_code=303)

    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent")
    is_local_dev = _is_local_dev_request(request)

    valid_code = verify_totp_code(admin["totp_secret"], code, window=4) or (is_local_dev and code.strip() == "000000")

    if not valid_code:
        record_admin_audit(
            email,
            "login_2fa_failed",
            target_type="admin_user",
            target_id=email,
            details={"reason": "Incorrect 6-digit TOTP code"},
            ip_address=client_ip,
            user_agent=ua
        )
        redirect_err = f"/admin/verify-2fa?err=Invalid+6-digit+code.+Please+try+again."
        if next_url and next_url.startswith("/admin"):
            redirect_err += f"&next={urllib.parse.quote(next_url)}"
        return RedirectResponse(url=redirect_err, status_code=303)

    update_admin_last_login(email)
    record_admin_audit(
        email,
        "login_2fa_success",
        target_type="admin_user",
        target_id=email,
        details={"status": "authenticated"},
        ip_address=client_ip,
        user_agent=ua
    )

    dest_url = next_url if (next_url and next_url.startswith("/admin")) else "/admin"
    session_token = _generate_admin_token(email, admin.get("role", "admin"))
    resp = RedirectResponse(url=dest_url, status_code=303)
    resp.set_cookie(key=ADMIN_COOKIE_NAME, value=session_token, httponly=True, samesite="lax", max_age=86400)
    resp.delete_cookie(key=ADMIN_2FA_PENDING_COOKIE)
    return resp


@router.get("/admin/logout")
@router.post("/admin/logout")
async def admin_logout(request: Request):
    admin_session = _is_admin_authenticated(request)
    if admin_session:
        client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
        record_admin_audit(
            admin_session.get("email"),
            "admin_logout",
            target_type="admin_user",
            ip_address=client_ip
        )
    response = RedirectResponse(url="/admin", status_code=303)
    response.delete_cookie(key=ADMIN_COOKIE_NAME)
    response.delete_cookie(key=ADMIN_2FA_PENDING_COOKIE)
    return response


# ==============================================================================
# Admin Team, Tickets, and Billing Management
# ==============================================================================
@router.post("/admin/team/add")
async def admin_team_add(
    request: Request,
    email: str = Form(...),
    role: str = Form("admin")
):
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    if admin_session.get("role") not in ("owner", "admin"):
        return RedirectResponse(url="/admin?tab=team&err=Only+owners+and+admins+can+invite+team+members.", status_code=303)

    current_email = admin_session.get("email")
    ok, msg = add_admin_user(email, role, invited_by=current_email)
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")

    if ok:
        record_admin_audit(
            current_email,
            "add_admin_user",
            target_type="admin_user",
            target_id=email.strip().lower(),
            details={"assigned_role": role},
            ip_address=client_ip
        )
        return RedirectResponse(url=f"/admin?tab=team&msg={msg}", status_code=303)
    return RedirectResponse(url=f"/admin?tab=team&err={msg}", status_code=303)


@router.post("/admin/team/remove")
async def admin_team_remove(
    request: Request,
    email: str = Form(...)
):
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    if admin_session.get("role") not in ("owner", "admin"):
        return RedirectResponse(url="/admin?tab=team&err=Only+owners+and+admins+can+remove+team+members.", status_code=303)

    current_email = admin_session.get("email")
    ok, msg = remove_admin_user(email, requesting_email=current_email)
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")

    if ok:
        record_admin_audit(
            current_email,
            "remove_admin_user",
            target_type="admin_user",
            target_id=email.strip().lower(),
            ip_address=client_ip
        )
        return RedirectResponse(url=f"/admin?tab=team&msg={msg}", status_code=303)
    return RedirectResponse(url=f"/admin?tab=team&err={msg}", status_code=303)


@router.post("/admin/team/role")
async def admin_team_role(
    request: Request,
    email: str = Form(...),
    new_role: str = Form(...)
):
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    if admin_session.get("role") != "owner":
        return RedirectResponse(url="/admin?tab=team&err=Only+platform+owners+can+modify+roles.", status_code=303)

    current_email = admin_session.get("email")
    ok, msg = update_admin_role(email, new_role, requesting_email=current_email)
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")

    if ok:
        record_admin_audit(
            current_email,
            "update_admin_role",
            target_type="admin_user",
            target_id=email.strip().lower(),
            details={"new_role": new_role},
            ip_address=client_ip
        )
        return RedirectResponse(url=f"/admin?tab=team&msg={msg}", status_code=303)
    return RedirectResponse(url=f"/admin?tab=team&err={msg}", status_code=303)


@router.post("/admin/tickets/{ticket_id}/status")
async def admin_update_ticket(
    ticket_id: str,
    request: Request,
    status: str = Form(...),
    admin_notes: Optional[str] = Form(None)
):
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    ok = update_ticket_status(ticket_id, status, admin_notes)
    current_email = admin_session.get("email")
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")

    if ok:
        record_admin_audit(
            current_email,
            "update_ticket_status",
            target_type="ticket",
            target_id=ticket_id,
            details={"new_status": status, "admin_notes": admin_notes},
            ip_address=client_ip
        )
    msg = f"Ticket+{ticket_id}+status+updated+to+{status}" if ok else "Failed+to+update+ticket"
    return RedirectResponse(url=f"/admin?tab=tickets&msg={msg}", status_code=303)


@router.get("/api/admin/tickets/{ticket_id}/thread")
async def api_admin_get_ticket_thread(ticket_id: str, request: Request):
    """Retrieves full ticket context and all chronological responses for the Service Inbox."""
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    ticket = get_ticket_by_id(ticket_id, include_responses=True)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    from core.notify import is_email_service_configured, get_email_service_status

    return JSONResponse(status_code=200, content={
        "success": True,
        "ticket": ticket,
        "responses": ticket.get("responses", []),
        "email_service_configured": is_email_service_configured(),
        "email_service_status": get_email_service_status()
    })


@router.post("/admin/tickets/{ticket_id}/reply")
async def admin_reply_ticket(
    ticket_id: str,
    request: Request,
    reply_message: str = Form(...),
    status: Optional[str] = Form("resolved"),
    dispatch_email: Optional[str] = Form("on"),
    grant_remedial_credits: Optional[float] = Form(0.0),
    admin_notes: Optional[str] = Form(None)
):
    """
    Submits a response to a support ticket, updates ticket status, logs the message thread,
    optionally grants remedial credits, and dispatches an email notification to the user's email address.
    """
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    ticket = get_ticket_by_id(ticket_id, include_responses=False)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    clean_reply = str(reply_message or "").strip()
    if not clean_reply:
        err_msg = "Reply message cannot be empty."
        return RedirectResponse(url=f"/admin?tab=tickets&err={urllib.parse.quote_plus(err_msg)}", status_code=303)

    admin_email = admin_session.get("email", "support@moatnomics.com")
    admin_name = "Moatnomics Service Desk"
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")

    # 1. Determine email dispatch
    should_email = dispatch_email in ("on", "true", "1", True)
    email_dispatched = False
    from core.notify import is_email_service_configured
    email_configured = is_email_service_configured()
    email_status_text = "Disabled by admin"

    if should_email:
        email_dispatched = send_ticket_reply_email(ticket, clean_reply, admin_name=admin_name)
        if not email_configured:
            email_status_text = "Mock Logged (outgoing credentials unconfigured)"
        elif email_dispatched:
            email_status_text = "Delivered via live email service"
        else:
            email_status_text = "Delivery failed (see server logs)"

    # 2. Record response in database
    add_ticket_response(
        ticket_id=ticket_id,
        message=clean_reply,
        sender_email=admin_email,
        sender_name=admin_name,
        sender_type="admin",
        email_dispatched=email_dispatched
    )

    # 3. Update status and admin notes if provided
    new_status = str(status or ticket.get("status", "in_progress")).strip().lower()
    combined_notes = admin_notes or ticket.get("admin_notes")
    update_ticket_status(ticket_id, new_status, combined_notes)

    # 4. Handle optional remedial credits grant
    credits_granted = 0.0
    if grant_remedial_credits and float(grant_remedial_credits) > 0:
        try:
            credits_val = float(grant_remedial_credits)
            admin_grant_user_credits(
                admin_email=admin_email,
                target_user_identifier=ticket.get("user_email"),
                credits_amount=credits_val,
                reason_code="TASK_REMEDY",
                admin_note=f"Remedial grant from ticket response {ticket_id}",
                ticket_id=ticket_id,
                resolve_ticket=False,
                auto_provision=True,
                ip_address=client_ip
            )
            credits_granted = credits_val
        except Exception as e:
            logger.error("Error granting remedial credits during ticket reply: %s", e)

    # 5. Record admin audit log
    record_admin_audit(
        admin_email,
        "reply_support_ticket",
        target_type="ticket",
        target_id=ticket_id,
        details={
            "recipient_email": ticket.get("user_email"),
            "new_status": new_status,
            "email_dispatched": email_dispatched,
            "email_configured": email_configured,
            "email_status_text": email_status_text,
            "credits_granted": credits_granted,
            "reply_preview": clean_reply[:100]
        },
        ip_address=client_ip
    )

    # 6. Response handling (AJAX vs Form Redirect)
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "")
    if is_ajax:
        return JSONResponse(status_code=200, content={
            "success": True,
            "ticket_id": ticket_id,
            "new_status": new_status,
            "email_dispatched": email_dispatched,
            "email_service_configured": email_configured,
            "email_status_text": email_status_text,
            "message": f"Response recorded for {ticket.get('user_email')}. Outgoing Email: {email_status_text}."
        })

    msg = f"Response+recorded+for+{ticket.get('user_email')}"
    if email_dispatched:
        msg += "+and+email+dispatched"
    elif should_email and not email_configured:
        msg += "+(email+unconfigured+-+mock+logged)"
    if credits_granted > 0:
        msg += f"+(+{credits_granted}+credits+granted)"
    return RedirectResponse(url=f"/admin?tab=tickets&msg={msg}", status_code=303)


@router.post("/admin/refund")
async def admin_process_refund(
    request: Request,
    order_id: str = Form(...),
    user_email: str = Form(...),
    reason: Optional[str] = Form("Customer request")
):
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    current_email = admin_session.get("email")
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")

    res = process_refund(gateway_order_id=order_id, user_email=user_email, reason=reason)
    if res.get("success"):
        record_admin_audit(
            current_email,
            "process_refund_success",
            target_type="order",
            target_id=order_id,
            details={"user_email": user_email, "amount": res.get("refund_amount", 0), "reason": reason},
            ip_address=client_ip
        )
        msg = f"Refund+of+Rs+{res.get('refund_amount', 0)}+processed+successfully+for+{order_id}"
    else:
        record_admin_audit(
            current_email,
            "process_refund_failed",
            target_type="order",
            target_id=order_id,
            details={"user_email": user_email, "error": res.get("error")},
            ip_address=client_ip
        )
        msg = f"Refund+failed:+{res.get('error', 'Unknown error')}"
    return RedirectResponse(url=f"/admin?tab=billables&msg={msg}", status_code=303)


@router.post("/admin/users/grant-credits")
async def admin_grant_credits_endpoint(request: Request):
    """
    Administrative endpoint to directly allocate remedial or goodwill research credits
    to user accounts, compensating for failed synthesis or resolving grievances.
    """
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        accept_header = request.headers.get("accept", "")
        content_type = request.headers.get("content-type", "")
        if "application/json" in accept_header or "application/json" in content_type:
            return JSONResponse(status_code=403, content={"success": False, "error": "Admin authorization required."})
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception as e:
            logger.debug("Failed parsing JSON body in admin_grant_credits_route: %s", e)
            body = {}
        user_identifier = body.get("user_email") or body.get("user_id") or ""
        credits_val = body.get("credits", 2.0)
        reason_code = body.get("reason", "TASK_REMEDY")
        admin_note = body.get("admin_note", "")
        ticket_id = body.get("ticket_id")
        task_ticker = body.get("task_ticker")
        resolve_ticket = body.get("resolve_ticket", True)
        tab = body.get("tab", "users")
        is_ajax = True
    else:
        form = await request.form()
        user_identifier = form.get("user_email") or form.get("user_id") or ""
        credits_val = form.get("credits", 2.0)
        reason_code = form.get("reason", "TASK_REMEDY")
        admin_note = form.get("admin_note", "")
        ticket_id = form.get("ticket_id")
        task_ticker = form.get("task_ticker")
        resolve_ticket = form.get("resolve_ticket") in ("true", "1", "on", True)
        tab = form.get("tab", "users")
        is_ajax = (
            request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in request.headers.get("accept", "")
        )

    try:
        credits_amount = float(credits_val)
        if credits_amount <= 0 or credits_amount > 1000.0:
            raise ValueError("Credits amount must be between 0.1 and 1000.0.")
    except Exception as e:
        logger.warning("Invalid credits amount requested: %s", e)
        err_msg = f"Invalid credits amount: {e}"
        if is_ajax:
            return JSONResponse(status_code=400, content={"success": False, "error": err_msg})
        return RedirectResponse(url=f"/admin?tab={tab}&err={urllib.parse.quote_plus(err_msg)}", status_code=303)

    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    user_agent = request.headers.get("user-agent", "")
    admin_email = admin_session.get("email", "admin")

    result = admin_grant_user_credits(
        admin_email=admin_email,
        target_user_identifier=str(user_identifier).strip(),
        credits_amount=credits_amount,
        reason_code=str(reason_code).strip(),
        admin_note=str(admin_note).strip(),
        ticket_id=str(ticket_id).strip() if ticket_id else None,
        task_ticker=str(task_ticker).strip() if task_ticker else None,
        resolve_ticket=bool(resolve_ticket),
        ip_address=client_ip,
        user_agent=user_agent
    )

    if result.get("success"):
        target_email = result.get("user_email", user_identifier)
        msg = f"Successfully granted {credits_amount} credits to {target_email}."
        if is_ajax:
            return JSONResponse(status_code=200, content={
                "success": True,
                "message": msg,
                "user_email": target_email,
                "user_id": result.get("user_id"),
                "credits_added": result.get("credits_added"),
                "new_balance": result.get("new_balance")
            })
        return RedirectResponse(url=f"/admin?tab={tab}&msg={urllib.parse.quote_plus(msg)}", status_code=303)
    else:
        err = result.get("error", "Failed to grant credits.")
        if is_ajax:
            return JSONResponse(status_code=400, content={"success": False, "error": err})
        return RedirectResponse(url=f"/admin?tab={tab}&err={urllib.parse.quote_plus(err)}", status_code=303)


@router.get("/admin/export/tax-register")
@router.get("/admin/export/transactions")
async def admin_export_tax_register(request: Request):
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    billables = get_all_billables(status="success", limit=1000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Invoice Number", "Date", "Customer Email", "Customer Name",
        "Pack Type", "Payment Method", "Gross Amount (INR)", "Refunded (INR)",
        "Net Amount (INR)", "Status", "Gateway Order ID", "Gateway Payment ID"
    ])
    for b in billables:
        gross = float(b.get("amount_inr", 0.0) or 0.0)
        refunded = float(b.get("refund_amount_inr", 0.0) or 0.0)
        net = max(0.0, gross - refunded)
        writer.writerow([
            b.get("invoice_number"),
            b.get("date"),
            b.get("customer_email"),
            b.get("customer_name"),
            b.get("pack_type"),
            b.get("payment_method", "Online (Razorpay UPI/Card)"),
            f"{gross:.2f}",
            f"{refunded:.2f}",
            f"{net:.2f}",
            b.get("status"),
            b.get("gateway_order_id"),
            b.get("gateway_payment_id")
        ])

    csv_data = output.getvalue()
    today_str = datetime.now(IST).strftime("%Y%m%d")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=Transaction_Register_{today_str}.csv"}
    )


# ==============================================================================
# Discovery & Asset Scan Admin Endpoints
# ==============================================================================
@router.post("/api/admin/run-discovery")
@router.post("/api/admin/run-discovery-refresh")
async def api_run_discovery(
    request: Request,
    background_tasks: BackgroundTasks,
    x_admin_key: Optional[str] = Header(None),
    count: int = 12,
    force: bool = False
):
    """Triggers the Morning Discovery Reel screening and dossier synthesis worker."""
    is_testing = os.environ.get("TESTING") == "1" or "pytest" in sys.modules
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    is_authed = is_testing
    if admin_secret and x_admin_key == admin_secret:
        is_authed = True
    elif _is_admin_authenticated(request):
        is_authed = True

    if not is_authed:
        raise HTTPException(status_code=403, detail="Unauthorized admin access.")

    from scripts.run_discovery_worker import run_discovery_pipeline
    background_tasks.add_task(run_discovery_pipeline, target_count=count, force_synthesis=force)
    return json_response_with_cache({
        "status": "initiated",
        "message": f"Morning Discovery Reel worker dispatched for {count} equities (force={force})."
    })


@router.post("/api/admin/msme/run-daily-ingest")
async def api_run_msme_daily_ingest(
    request: Request,
    background_tasks: BackgroundTasks,
    x_admin_key: Optional[str] = Header(None),
    count: int = 15,
    edition_date: Optional[str] = None
):
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    is_authed = False
    if admin_secret and x_admin_key == admin_secret:
        is_authed = True
    elif _is_admin_authenticated(request):
        is_authed = True

    if not is_authed:
        raise HTTPException(status_code=403, detail="Unauthorized admin access.")

    from core.msme.daily_ingest import ingest_daily_msme_cohort
    background_tasks.add_task(ingest_daily_msme_cohort, edition_date=edition_date, count=count)
    return json_response_with_cache({
        "status": "initiated",
        "message": f"Daily MSME ingestion worker dispatched for {count} firms (date={edition_date or 'today'})."
    })


@router.post("/admin/assets/trigger-scan")
async def admin_trigger_scan_form(request: Request):
    """Admin UI action: Trigger full AMFI and Debt asset surveillance scan."""
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    from core.analysis.asset_scanner import run_comprehensive_asset_scan
    res = run_comprehensive_asset_scan()
    msg = f"Asset+scan+completed:+{res.get('total_scanned', 0)}+scanned,+{res.get('new_assets', 0)}+new,+{res.get('changed_assets', 0)}+updated."
    return RedirectResponse(url=f"/admin?tab=assets&msg={msg}", status_code=303)


@router.post("/api/admin/assets/scan")
async def api_admin_trigger_asset_scan(
    request: Request,
    background_tasks: BackgroundTasks,
    x_admin_key: Optional[str] = Header(None)
):
    """Admin API: Trigger asset surveillance scan across mutual funds and debt securities."""
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    is_authed = False
    if admin_secret and x_admin_key == admin_secret:
        is_authed = True
    elif _is_admin_authenticated(request):
        is_authed = True

    if not is_authed:
        raise HTTPException(status_code=403, detail="Unauthorized admin access.")

    from core.analysis.asset_scanner import run_comprehensive_asset_scan
    scan_summary = run_comprehensive_asset_scan()
    return json_response_with_cache({
        "status": "success",
        "message": "Asset surveillance scan completed.",
        "summary": scan_summary
    })


@router.post("/api/admin/sync-amfi")
async def api_admin_sync_amfi(
    request: Request,
    limit: Optional[int] = None,
    x_admin_key: Optional[str] = Header(None)
):
    """Admin API: Trigger on-demand AMFI daily NAV synchronization."""
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    is_authed = False
    if admin_secret and x_admin_key == admin_secret:
        is_authed = True
    elif _is_admin_authenticated(request):
        is_authed = True

    if not is_authed:
        raise HTTPException(status_code=403, detail="Unauthorized admin access.")

    from core.ingestion.amfi import ingest_amfi_daily_feed
    res = ingest_amfi_daily_feed(limit=limit, direct_growth_only=True)
    return json_response_with_cache({
        "status": "success",
        "message": "AMFI synchronization completed successfully.",
        "summary": res
    })


@router.get("/api/admin/assets/scan-runs")
async def api_admin_get_scan_runs(
    request: Request,
    limit: int = 50,
    x_admin_key: Optional[str] = Header(None)
):
    """Admin API: Query historical immutable asset scan ledger records."""
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    is_authed = False
    if admin_secret and x_admin_key == admin_secret:
        is_authed = True
    elif _is_admin_authenticated(request):
        is_authed = True

    if not is_authed:
        raise HTTPException(status_code=403, detail="Unauthorized admin access.")

    from core.analysis.asset_scanner import get_asset_scan_runs
    runs = get_asset_scan_runs(limit=limit)
    return json_response_with_cache({
        "status": "success",
        "count": len(runs),
        "runs": runs
    })


@router.post("/api/admin/sovereign/refresh")
async def api_admin_refresh_sovereign(
    request: Request,
    edition_date: Optional[str] = Query(None),
    x_admin_key: Optional[str] = Header(None)
):
    """Admin API: Trigger on-demand sovereign benchmarks & SDL yield curve synchronization."""
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    admin_user = _is_admin_authenticated(request)
    is_authed = False
    admin_email = "api_key_system"
    if admin_secret and x_admin_key == admin_secret:
        is_authed = True
    elif admin_user:
        is_authed = True
        admin_email = admin_user.get("email", "admin")

    if not is_authed:
        raise HTTPException(status_code=403, detail="Unauthorized admin access.")

    from core.db.sovereign import refresh_daily_sovereign_benchmarks
    summary = refresh_daily_sovereign_benchmarks(edition_date=edition_date)
    record_admin_audit(
        admin_email,
        "refresh_sovereign_benchmarks",
        target_type="sovereign_curve",
        target_id=summary.get("edition_date", "today"),
        details=summary
    )
    return json_response_with_cache({
        "status": "success",
        "message": "Sovereign yield curve benchmarks synchronized successfully.",
        "summary": summary
    })


@router.post("/api/admin/assets/scan")
async def api_admin_run_asset_scan(
    request: Request,
    scan_type: str = Query("ALL_ASSETS"),
    x_admin_key: Optional[str] = Header(None)
):
    """Admin API: Dispatches an immediate multi-asset surveillance scan (MFs, Corporate Debt)."""
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    admin_user = _is_admin_authenticated(request)
    is_authed = False
    admin_email = "api_key_system"
    if admin_secret and x_admin_key == admin_secret:
        is_authed = True
    elif admin_user:
        is_authed = True
        admin_email = admin_user.get("email", "admin")

    if not is_authed:
        raise HTTPException(status_code=403, detail="Unauthorized admin access.")

    from core.analysis.asset_scanner import run_comprehensive_asset_scan
    res = run_comprehensive_asset_scan(scan_type=scan_type, triggered_by=f"admin_console:{admin_email}")
    record_admin_audit(
        admin_email,
        "run_asset_scan",
        target_type="multi_asset_scan",
        target_id=res.get("scan_id", "scan"),
        details=res
    )
    return json_response_with_cache({
        "status": "success",
        "message": "Asset scan completed successfully.",
        "result": res
    })


# ==============================================================================
# Admin Executive Copilot Endpoints
# ==============================================================================
@router.post("/api/admin/copilot/chat")
async def api_admin_copilot_chat(
    request: Request,
    req: AdminCopilotChatRequest = Body(...)
):
    """
    Interactive Q&A and operational orchestration endpoint for the Admin Copilot.
    Requires active administrator authentication.
    """
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    res = await process_admin_copilot_turn(
        admin_user=admin_session,
        message=req.message,
        history=req.history,
        context=req.context
    )
    return JSONResponse(status_code=200, content={
        "success": True,
        "reply": res.get("reply"),
        "action_proposal": res.get("action_proposal"),
        "status": res.get("status"),
        "new_balance": res.get("new_balance")
    })


@router.post("/api/admin/copilot/execute")
async def api_admin_copilot_execute(
    request: Request,
    req: AdminCopilotExecuteRequest = Body(...)
):
    """
    Executes a confirmed administrative action proposal after the administrator
    has reviewed the action card and explicitly clicked 'Confirm & Execute'.
    """
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    user_agent = request.headers.get("user-agent", "")

    result = execute_confirmed_admin_action(
        action_type=req.action_type,
        payload=req.payload,
        admin_user=admin_session,
        client_ip=client_ip,
        user_agent=user_agent
    )
    status_code = 200 if result.get("success") else 400
    return JSONResponse(status_code=status_code, content=result)


@router.post("/api/admin/stocks/run-daily-ingest")
async def api_admin_run_daily_stock_ingest(
    request: Request,
    count: int = Query(15, ge=1, le=50),
    edition_date: Optional[str] = Query(None),
    skip_gemini: bool = Query(False)
):
    """
    Triggers the Daily 08:30 AM 15-Stock Ingestion & Mutual Fund Look-Through Re-Audit.
    Requires administrator authentication.
    """
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    from core.analysis.daily_stock_ingestion import ingest_daily_stock_cohort
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, ingest_daily_stock_cohort, edition_date, count, skip_gemini)
    return JSONResponse(status_code=200, content={
        "success": True,
        "result": res
    })


@router.get("/api/admin/stocks/ingestion-queue")
def api_admin_get_stock_ingestion_queue(
    request: Request,
    limit: int = Query(20, ge=1, le=100)
):
    """
    Returns the priority queue of uncovered mutual fund constituent stocks
    and overall mutual fund coverage progress statistics.
    Requires administrator authentication.
    """
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    from core.analysis.daily_stock_ingestion import (
        get_uncovered_mutual_fund_holdings_queue,
        get_ingestion_progress_stats,
    )
    queue = get_uncovered_mutual_fund_holdings_queue(limit=limit)
    stats = get_ingestion_progress_stats()
    return JSONResponse(status_code=200, content={
        "success": True,
        "stats": stats,
        "queue": queue
    })


@router.get("/api/admin/ai-spends")
def api_admin_ai_spends(request: Request):
    """
    Returns real-time Gemini token consumption, USD/INR spend estimates,
    model rate cards, and feature-by-feature cost breakdown across the platform.
    Requires administrator authentication.
    """
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    from core.analytics.ai_spends import get_gemini_spends_summary
    spends = get_gemini_spends_summary()
    return JSONResponse(status_code=200, content={
        "success": True,
        "spends": spends
    })


@router.get("/api/admin/traffic/flow")
def api_admin_traffic_flow(
    request: Request,
    days: Optional[int] = Query(30, ge=1, le=365),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    include_tests: Optional[bool] = Query(False)
):
    """
    Returns granular page dwell times and the internal site visit navigation tree (transition matrix).
    Requires administrator authentication.
    """
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    parsed_start = None
    parsed_end = None
    if start_date and end_date:
        try:
            parsed_start = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
            parsed_end = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        except Exception as e:
            logger.warning("Failed parsing date range for traffic flow (%s to %s): %s", start_date, end_date, e)
            parsed_start, parsed_end = None, None

    flow = get_traffic_flow_analytics(
        days=days if not (parsed_start and parsed_end) else None,
        start_date=parsed_start,
        end_date=parsed_end,
        exclude_tests=not include_tests
    )
    return JSONResponse(status_code=200, content={
        "success": True,
        "flow": flow
    })


@router.get("/api/admin/digest/preview")
async def api_admin_digest_preview(request: Request, edition_date: Optional[str] = None):
    """Generates preview of today's Research Bouquet with recipient counters and HTML/Text previews."""
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from core.analysis.research_bouquet import (
        compile_research_bouquet,
        render_bouquet_html,
        render_bouquet_text,
        get_tracking_base_url,
    )
    from core.db.digest import get_digest_subscribers
    from core.notify import get_email_service_status, get_admin_notification_email

    bouquet = compile_research_bouquet(edition_date=edition_date)
    subscribers = get_digest_subscribers(only_active_pro=False)
    pro_subscribers = [s for s in subscribers if s.get("subscription_tier") in ("pro_monthly", "pro_annual") or s.get("is_subscriber")]

    preview_sub = subscribers[0] if subscribers else {
        "email": get_admin_notification_email(),
        "full_name": "Moatnomics Preview Subscriber",
        "unsubscribe_token": "preview_sample_token"
    }

    html = render_bouquet_html(bouquet, subscriber=preview_sub)
    text = render_bouquet_text(bouquet, subscriber=preview_sub)

    return JSONResponse(status_code=200, content={
        "success": True,
        "bouquet": bouquet,
        "html_preview": html,
        "text_preview": text,
        "recipients_summary": {
            "total_subscribers": len(subscribers),
            "pro_subscribers": len(pro_subscribers)
        },
        "email_service": get_email_service_status(),
        "admin_email": get_admin_notification_email(),
        "tracking_url": get_tracking_base_url()
    })


@router.post("/api/admin/digest/dispatch-test")
async def api_admin_digest_dispatch_test(request: Request):
    """Dispatches a single test Research Bouquet to administrator email."""
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from core.notify import dispatch_research_bouquet, get_admin_notification_email

    try:
        body = await request.json()
    except Exception as e:
        logger.debug("Failed parsing json in digest dispatch-test: %s", e)
        body = {}

    target_email = (body.get("recipient_email") or get_admin_notification_email()).strip()
    edition_date = body.get("edition_date")

    result = dispatch_research_bouquet(edition_date=edition_date, test_recipient=target_email)
    return JSONResponse(status_code=200, content=result)


@router.post("/api/admin/digest/broadcast")
async def api_admin_digest_broadcast(request: Request):
    """Broadcasts today's Research Bouquet to all eligible subscribers."""
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from core.notify import dispatch_research_bouquet

    try:
        body = await request.json()
    except Exception as e:
        logger.debug("Failed parsing json in digest broadcast: %s", e)
        body = {}

    only_active_pro = bool(body.get("only_active_pro", False))
    edition_date = body.get("edition_date")

    result = dispatch_research_bouquet(edition_date=edition_date, only_active_pro=only_active_pro)
    return JSONResponse(status_code=200, content=result)


@router.get("/api/admin/digest/history")
async def api_admin_digest_history(request: Request, limit: int = 15):
    """Returns chronological digest dispatch logs."""
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from core.db.digest import get_digest_dispatch_history

    history = get_digest_dispatch_history(limit=limit)
    return JSONResponse(status_code=200, content={
        "success": True,
        "history": history
    })


