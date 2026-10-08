"""
Stock Research AI - FastAPI Web Application.

High-performance Server-Side Rendered (SSR) institutional equity research portal.
Provides:
- Razorpay-compliant public landing page & mandatory legal policies
- Zero-latency crawlable dossier URLs for Google SEO & GEO answer engines
- Interactive UPI and card checkout endpoints
- Instant PDF report export downloads
"""

import os
import sys
import re
import json
import asyncio
import logging
import markdown
import csv
import io
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, HTTPException, Form, Header, BackgroundTasks, Query, Body
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
try:
    from brotli_asgi import BrotliMiddleware
except ImportError:
    BrotliMiddleware = None
from fastapi.middleware.cors import CORSMiddleware
from web.middleware.security_headers import SecurityHeadersMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, Response
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import toml
    _sec_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".streamlit", "secrets.toml")
    if os.path.exists(_sec_path):
        _sec = toml.load(_sec_path)
        for _k, _v in _sec.items():
            if isinstance(_v, str) and _k not in os.environ:
                os.environ[_k] = _v
except Exception:
    pass

from pydantic import BaseModel

from core.db import (
    init_db,
    get_archived_reports_sync,
    get_report_by_ticker_sync,
    get_report_revisions,
    get_or_create_user,
    get_user_by_id,
    get_user_by_email,
    get_user_credits_balance,
    deduct_user_credits,
    add_user_credits,
    get_active_discovery_reel,
    get_available_discovery_editions,
    save_discovery_reel,
    create_support_ticket,
    get_support_tickets,
    get_open_tickets_count,
    update_ticket_status,
    get_all_billables,
    get_revenue_analytics_summary,
    process_refund,
    get_site_usage_summary,
    get_session_journeys,
    get_user_usage_analytics,
    get_system_setting,
    set_system_setting,
    MANDATORY_SEBI_DISCLAIMER,
    IST,
)
import base64
import urllib.parse
from core.auth.totp import (
    generate_totp_secret,
    verify_totp_code,
    get_totp_uri,
)
from core.auth.supabase_auth import (
    get_google_oauth_url,
    get_supabase_auth_config,
)
from core.auth.otp import (
    create_email_otp,
    verify_email_otp,
)
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
from telemetry import (
    verify_admin_passcode,
    update_admin_passcode,
    get_admin_passcode,
)
from core.db.telemetry import (
    record_usage_event,
    parse_traffic_source,
    parse_user_agent,
    extract_geo,
    purge_test_telemetry,
)
from core.notify import dispatch_support_ticket_alert
from core.analysis import get_stock_fundamentals, get_historical_prices
from core.analysis.engine import generate_stock_report
from core.analysis.comparator import compare_two_companies
from core.analysis.parser import (
    extract_health_matrix,
    compare_revisions,
    remove_health_matrix_text,
    wrap_html_with_collapsible_pillars
)
from core.analysis.metrics import calculate_52w_percentile, calculate_pe_percentile, get_valuation_quartile
from core.billing import (
    PRICING_PACKS,
    B2B_PACKS,
    get_plan_by_id,
    create_razorpay_order,
    process_successful_payment,
    RazorpayAuthError,
    RazorpayAPIError,
)
from normalizer import clean_ticker, extract_citations_from_report
from bse_master import (
    get_ticker_suggestions,
    resolve_canonical_symbol,
    resolve_bse_scrip_code,
    get_bse_scrips_cache,
)
from core.formatters import format_inr
from web.legal_content import POLICIES
from core.db.debt import (
    get_active_debt_securities,
    get_debt_security_by_isin,
    get_debt_securities_by_ticker,
    get_recent_rating_actions,
    get_rating_history,
    seed_default_debt_securities,
)
from core.analysis.debt_engine import evaluate_5_pillar_credit_posture
from core.db.mutual_funds import (
    get_active_mutual_funds,
    get_mutual_fund_scheme,
    get_scheme_holdings,
    get_schemes_by_holding,
    seed_default_mutual_funds,
    get_featured_daily_fund_dossier,
    get_fund_forensic_dossier,
)
from core.analysis.mutual_fund_engine import (
    evaluate_mutual_fund_comprehensive,
    evaluate_dual_sleeve_lookthrough,
    calculate_portfolio_overlap,
    calculate_active_share,
    calculate_fee_drag,
)
from core.analysis.fund_forensic_auditor import (
    audit_single_fund_daily,
    compute_fund_forensic_lookthrough,
    calculate_deep_dive_credit_cost,
    create_async_fund_audit_task,
    run_async_fund_audit_job,
    get_fund_audit_task_status,
    ensure_scheme_and_holdings_exist,
)

logger = logging.getLogger("equity_research.web")

from contextlib import asynccontextmanager

async def run_daily_discovery_scheduler():
    """
    Automated background BSE surveillance and screening scheduler:
    Initiates automatic crawling & screening of BSE listed companies at 09:00 AM IST daily.
    Includes startup catch-up to ensure today's 9:00 AM edition is never missed due to restarts or deploy timings.
    """
    logger.info("🌅 [Discovery Scheduler] Background BSE surveillance crawler initiated.")

    # Startup catch-up check: If past 9:00 AM IST and today's edition has not been generated, trigger catch-up
    try:
        now = datetime.now(IST)
        today_str = now.strftime("%Y-%m-%d")
        from core.db.discovery import get_active_discovery_reel
        from scripts.run_discovery_worker import run_discovery_pipeline

        loop = asyncio.get_running_loop()
        if now.hour >= 9:
            active_today = [x for x in get_active_discovery_reel(today_str, exclude_tests=True)]
            if not active_today:
                logger.info(f"🌅 [Discovery Scheduler] Missing 9:00 AM edition for today ({today_str}). Triggering catch-up screening...")
                await loop.run_in_executor(None, run_discovery_pipeline, 12, today_str, False, False)
                logger.info(f"🌅 [Discovery Scheduler] Catch-up 9:00 AM edition for {today_str} published.")
        else:
            # If before 9:00 AM IST, ensure at least one baseline edition exists so UI is not empty
            active_existing = [x for x in get_active_discovery_reel(exclude_tests=True)]
            if not active_existing:
                yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
                logger.info(f"🌅 [Discovery Scheduler] No active historical editions found. Bootstrapping baseline edition ({yesterday_str})...")
                await loop.run_in_executor(None, run_discovery_pipeline, 12, yesterday_str, False, False)
    except Exception as boot_err:
        logger.warning(f"🌅 [Discovery Scheduler] Catch-up check notice: {boot_err}")

    while True:
        try:
            now = datetime.now(IST)
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"🌅 [Discovery Scheduler] Next daily BSE screening scheduled in {wait_seconds/3600:.2f} hours (at {target.strftime('%Y-%m-%d 09:00:00 IST')}).")
            await asyncio.sleep(wait_seconds)

            logger.info("🌅 [Discovery Scheduler] 09:00 AM IST reached. Executing automated BSE discovery pipeline...")
            from scripts.run_discovery_worker import run_discovery_pipeline
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, run_discovery_pipeline, 12, None, False, False)
            logger.info("🌅 [Discovery Scheduler] Automated 9:00 AM BSE discovery edition published successfully.")
        except asyncio.CancelledError:
            logger.info("🌅 [Discovery Scheduler] Background scheduler cancelled.")
            break
        except Exception as e:
            logger.error(f"🌅 [Discovery Scheduler] Error in daily discovery scheduler: {e}")
            await asyncio.sleep(60)

async def run_daily_amfi_scheduler():
    """
    Automated background AMFI NAV synchronizer:
    AMFI publishes official daily NAVAll.txt files around 11:00 PM IST.
    Executes synchronization daily at 23:15 IST.
    """
    logger.info("📊 [AMFI Scheduler] Background AMFI NAV synchronizer initiated.")
    while True:
        try:
            now = datetime.now(IST)
            target = now.replace(hour=23, minute=15, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"📊 [AMFI Scheduler] Next AMFI synchronization scheduled in {wait_seconds/3600:.2f} hours (at {target.strftime('%Y-%m-%d %H:%M:%S IST')}).")
            await asyncio.sleep(wait_seconds)

            logger.info("📊 [AMFI Scheduler] Executing scheduled nightly AMFI NAV synchronization...")
            from core.ingestion.amfi import ingest_amfi_daily_feed
            from core.db.agent_sessions import record_autonomous_event
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, ingest_amfi_daily_feed, None, True)
            record_autonomous_event(
                event_type="AMFI_NAV_SYNC",
                ticker="AMFI_PORTAL",
                trigger_source="AMFI_NAV_SCHEDULER",
                action_taken="NAV_SYNC_AND_DELTA_CALC",
                summary="Nightly AMFI NAV synchronization and delta computation successfully completed.",
                metadata={"updated": True}
            )
            logger.info("📊 [AMFI Scheduler] Nightly AMFI synchronization completed.")
        except asyncio.CancelledError:
            logger.info("📊 [AMFI Scheduler] Background AMFI scheduler cancelled.")
            break
        except Exception as e:
            logger.error(f"📊 [AMFI Scheduler] Error in AMFI synchronization: {e}")
            await asyncio.sleep(120)

async def run_daily_fund_audit_scheduler():
    """
    Automated background Mutual Fund Forensic Auditor:
    Executes deep 7-pillar portfolio look-through audit across constituent holdings
    for the next eligible fund in the rotation queue daily at 23:30 IST
    (15 minutes post-AMFI NAV synchronization).
    """
    logger.info("🔍 [Fund Audit Scheduler] Background mutual fund forensic auditor initiated.")
    while True:
        try:
            now = datetime.now(IST)
            target = now.replace(hour=23, minute=30, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"🔍 [Fund Audit Scheduler] Next fund audit scheduled in {wait_seconds/3600:.2f} hours (at {target.strftime('%Y-%m-%d %H:%M:%S IST')}).")
            await asyncio.sleep(wait_seconds)

            logger.info("🔍 [Fund Audit Scheduler] Executing scheduled nightly mutual fund forensic audit...")
            from core.analysis.fund_forensic_auditor import audit_single_fund_daily
            from core.db.agent_sessions import record_autonomous_event
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, audit_single_fund_daily, None, False)
            
            if res:
                record_autonomous_event(
                    event_type="DAILY_FUND_AUDIT",
                    ticker=res.get("scheme_code", "UNKNOWN"),
                    trigger_source="AMFI_SCHEDULER_ROTATION",
                    action_taken="7_PILLAR_LOOKTHROUGH_AUDIT",
                    summary=f"Automated 7-pillar look-through audit completed for {res.get('scheme_name')} ({res.get('scheme_code')}). Health: {res.get('composite_health_score')}/100, Moat: {res.get('weighted_moat_score')}/100, ASRI: {res.get('accounting_risk_index')}%.",
                    metadata={
                        "composite_health_score": res.get("composite_health_score"),
                        "weighted_moat_score": res.get("weighted_moat_score"),
                        "accounting_risk_index": res.get("accounting_risk_index"),
                        "margin_of_safety_pct": res.get("margin_of_safety_pct")
                    }
                )
            logger.info(f"🔍 [Fund Audit Scheduler] Nightly fund forensic audit completed for {res.get('scheme_code')}.")
        except asyncio.CancelledError:
            logger.info("🔍 [Fund Audit Scheduler] Background fund audit scheduler cancelled.")
            break
        except Exception as e:
            logger.error(f"🔍 [Fund Audit Scheduler] Error in fund audit scheduler: {e}")
            await asyncio.sleep(180)

async def run_daily_project_audit_scheduler():
    """
    Automated background Project Auditor via Google Antigravity SDK:
    Runs nightly at 03:00 IST to audit Strategy, Code Implementation, and UI/UX.
    """
    logger.info("🛡️ [Project Auditor Scheduler] Background project auditor initiated.")
    while True:
        try:
            now = datetime.now(IST)
            target = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"🛡️ [Project Auditor Scheduler] Next audit scheduled in {wait_seconds/3600:.2f} hours (at {target.strftime('%Y-%m-%d %H:%M:%S IST')}).")
            await asyncio.sleep(wait_seconds)

            logger.info("🛡️ [Project Auditor Scheduler] Executing scheduled nightly project audit...")
            from core.audit.project_auditor import audit_project_full
            await audit_project_full(use_ai=True)
            logger.info("🛡️ [Project Auditor Scheduler] Nightly project audit completed.")
        except asyncio.CancelledError:
            logger.info("🛡️ [Project Auditor Scheduler] Background scheduler cancelled.")
            break
        except Exception as e:
            logger.error(f"🛡️ [Project Auditor Scheduler] Error in project audit scheduler: {e}")
            await asyncio.sleep(180)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.msme.scheduler import register_jobs

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB migrations on startup
    # Include MSME router
    from core.msme.router import router as msme_router
    app.include_router(msme_router, prefix="/api/msme")
    init_db()

    # Pre-seed foundational benchmark securities if empty on startup (out-of-band, not during HTTP requests)
    try:
        from core.db.mutual_funds import get_active_mutual_funds, seed_default_mutual_funds
        if not get_active_mutual_funds():
            seed_default_mutual_funds()
    except Exception as e:
        logger.warning(f"Initial mutual fund bootstrap seed skipped: {e}")

    try:
        from core.db.debt import get_active_debt_securities, seed_default_debt_securities
        if not get_active_debt_securities():
            seed_default_debt_securities()
    except Exception as e:
        logger.warning(f"Initial debt bootstrap seed skipped: {e}")

    is_testing = os.environ.get("TESTING") == "1" or "pytest" in sys.modules
    scheduler = None
    discovery_task = None
    amfi_task = None
    fund_audit_task = None
    audit_task = None
    bse_task = None

    if not is_testing:
        # Warm‑up task to prime async resources in background
        asyncio.create_task(warmup_task())
        # Start APScheduler for MSME background jobs
        scheduler = AsyncIOScheduler()
        register_jobs(scheduler)
        scheduler.start()
        # Start automated daily discovery background scheduler
        discovery_task = asyncio.create_task(run_daily_discovery_scheduler())
        # Start automated daily AMFI NAV background scheduler
        amfi_task = asyncio.create_task(run_daily_amfi_scheduler())
        # Start automated daily mutual fund forensic audit background scheduler
        fund_audit_task = asyncio.create_task(run_daily_fund_audit_scheduler())
        # Start automated daily project audit background scheduler
        audit_task = asyncio.create_task(run_daily_project_audit_scheduler())
        # Start proactive BSE announcement watcher
        from core.agents.watchers.bse_watcher import run_bse_watcher_loop
        bse_task = asyncio.create_task(run_bse_watcher_loop())

    try:
        yield
    finally:
        if discovery_task:
            discovery_task.cancel()
        if amfi_task:
            amfi_task.cancel()
        if fund_audit_task:
            fund_audit_task.cancel()
        if audit_task:
            audit_task.cancel()
        if bse_task:
            bse_task.cancel()
        if scheduler:
            scheduler.shutdown()

app = FastAPI(
    title="Stock Research AI",
    description="Institutional-Grade 7-Pillar Equity Research Engine Grounded in Public Filings",
    version="2.0.0",
    lifespan=lifespan
)

# Cache-Control / ETag helper for cheap JSON endpoints
def json_response_with_cache(data: dict, max_age: int = 3600) -> JSONResponse:
    import json, hashlib
    from fastapi.encoders import jsonable_encoder
    safe_data = jsonable_encoder(data)
    content_str = json.dumps(safe_data, sort_keys=True, default=str)
    etag = f'"{hashlib.md5(content_str.encode()).hexdigest()}"'
    return JSONResponse(content=safe_data, media_type="application/json", headers={
        "Cache-Control": f"public, max-age={max_age}",
        "ETag": etag,
    })

# Warm‑up task to prime async resources on startup
async def warmup_task():
    if os.environ.get("TESTING") == "1" or "pytest" in sys.modules:
        logger.info("🧪 Test environment detected: skipping live network warm-up task.")
        return
    logger.info("🚀 Starting warm‑up task: preloading local database connections...")
    try:
        init_db()
        logger.info("🚀 Warm‑up task completed: DB connection and schema caches primed.")
    except Exception as e:
        logger.warning(f"Warm‑up task warning: {e}")
if BrotliMiddleware is not None:
    app.add_middleware(BrotliMiddleware, minimum_size=500)
# Security headers middleware for CSP, HSTS, etc.
app.add_middleware(SecurityHeadersMiddleware)
# CORS configuration – allow all origins for now (adjust in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Rate limiting using SlowAPI – 100 requests per minute per IP
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: Response(content="Rate limit exceeded", status_code=429))

class HeadMethodMiddleware(BaseHTTPMiddleware):
    """Transparently handles HEAD requests for uptime monitors and link crawlers."""
    async def dispatch(self, request: Request, call_next):
        if request.method == "HEAD":
            request.scope["method"] = "GET"
            response = await call_next(request)
            return Response(
                status_code=response.status_code,
                headers=dict(response.headers),
                background=response.background,
            )
        return await call_next(request)

app.add_middleware(HeadMethodMiddleware)

# Static files & Jinja2 templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
templates.env.globals["MANDATORY_SEBI_DISCLAIMER"] = MANDATORY_SEBI_DISCLAIMER


# ==============================================================================
# Page Routes (SSR)
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    """Public home & landing page with live stock search, discovery reel, and featured dossiers."""
    try:
        archives = get_archived_reports_sync()
    except Exception as e:
        logger.error(f"Error fetching archives: {e}")
        archives = []

    try:
        discovery_stocks = get_active_discovery_reel()
    except Exception as e:
        logger.error(f"Error fetching discovery reel for home: {e}")
        discovery_stocks = []

    featured = archives[:9] if archives else []
    total_count = len(archives) if archives else 81

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "active_page": "home",
            "featured_reports": featured,
            "discovery_stocks": discovery_stocks,
            "total_reports": total_count,
            "pricing_packs": PRICING_PACKS,
        }
    )


@app.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: Optional[str] = None,
    type: Optional[str] = None,
    asset_class: Optional[str] = None
):
    """Multi-asset unified search discovery page across Equities, Mutual Funds, and Corporate Debt/NCDs."""
    init_db()
    query_str = (q or "").strip()
    selected_type = (type or asset_class or "ALL").strip().upper()

    search_res = {
        "query": query_str,
        "total_matches": 0,
        "results": [],
        "categories": {"equities": [], "mutual_funds": [], "corporate_debt": []}
    }
    if query_str:
        from core.search.product_search import search_investment_products
        search_res = search_investment_products(query_str, product_type=selected_type, limit_per_category=20)

    return templates.TemplateResponse(
        request=request,
        name="search_results.html",
        context={
            "active_page": "search",
            "query": query_str,
            "selected_type": selected_type,
            "search_results": search_res,
        }
    )


@app.get("/api/search/products")
def api_search_products(
    q: str = Query(..., min_length=1, description="Search query string"),
    asset_class: str = Query("all", description="Asset class filter: 'all', 'equity', 'mutual_fund', 'debt'"),
    limit: int = Query(25, ge=1, le=100)
):
    """Public Omni-Product Search API across Equities, Mutual Funds, and Corporate Debt/NCDs."""
    init_db()
    from core.search.product_search import search_all_products
    matches = search_all_products(q, asset_class=asset_class, limit=limit)
    return json_response_with_cache({
        "status": "success",
        "query": q,
        "asset_class": asset_class,
        "count": len(matches),
        "results": matches
    }, max_age=60)


@app.get("/discovery", response_class=HTMLResponse)
def discovery_page(request: Request, edition: Optional[str] = Query(None)):
    """The Morning Discovery Reel: nightly screening of under-the-radar equities."""
    try:
        discovery_stocks = get_active_discovery_reel(edition_date=edition)
        available_editions = get_available_discovery_editions(exclude_tests=True)
    except Exception as e:
        logger.error(f"Error fetching discovery reel: {e}")
        discovery_stocks = []
        available_editions = []

    current_ed = edition or (discovery_stocks[0]["edition_date"] if discovery_stocks else datetime.now(IST).strftime("%Y-%m-%d"))

    return templates.TemplateResponse(
        request=request,
        name="discovery.html",
        context={
            "active_page": "discovery",
            "discovery_stocks": discovery_stocks,
            "available_editions": available_editions,
            "current_edition": current_ed,
        }
    )


@app.get("/pricing", response_class=HTMLResponse)
def pricing_page(request: Request):
    """Dedicated pricing and computational research credit pack selection."""
    return templates.TemplateResponse(
        request=request,
        name="pricing.html",
        context={
            "active_page": "pricing",
            "pricing_packs": PRICING_PACKS,
            "b2b_packs": B2B_PACKS,
        }
    )


@app.get("/dossier/{ticker}", response_class=HTMLResponse)
def dossier_page(request: Request, ticker: str):
    """
    Canonical stock research dossier page.
    Renders 7-pillar qualitative matrix, valuation multiples, and exchange citations.
    If uncompiled, serves the pending compilation queue template instead of a raw 404 JSON.
    """
    clean_t = clean_ticker(ticker)
    if not clean_t:
        return RedirectResponse(url="/")

    # Canonicalize ticker symbol (e.g. 'MANALI PETROCHEM' or '500268' -> 'MANALIPETC')
    canonical = resolve_canonical_symbol(clean_t) or clean_t
    if canonical != clean_t:
        return RedirectResponse(url=f"/dossier/{canonical}", status_code=302)

    rep = get_report_by_ticker_sync(canonical)
    if not rep or not rep.get("report_text"):
        # Resolve company details for the pending template
        scrip = resolve_bse_scrip_code(canonical) or "BSE Listed"
        cached = get_bse_scrips_cache()
        company_name = canonical
        if cached:
            for c_name, c_code in cached.get("names", {}).items():
                if str(c_code) == str(scrip):
                    company_name = c_name.title()
                    break

        suggestions = get_ticker_suggestions(clean_t, n=4)

        # Phase 2: Equity-to-Debt Contagion Bridge for pending equities
        linked_debt = []
        contagion_alert = None
        try:
            from core.db.debt import get_debt_securities_for_equity
            linked_debt = get_debt_securities_for_equity(canonical)
            if linked_debt:
                from core.analysis.debt_engine import evaluate_equity_cross_contagion
                contagion_alert = evaluate_equity_cross_contagion(linked_debt[0])
        except Exception as e:
            logger.debug(f"Linked debt query notice for pending {canonical}: {e}")

        return templates.TemplateResponse(
            request=request,
            name="dossier_pending.html",
            context={
                "display_ticker": canonical,
                "company_name": company_name,
                "scrip_code": scrip,
                "suggestions": suggestions,
                "active_page": "dossier",
                "linked_debt": linked_debt,
                "contagion_alert": contagion_alert,
            }
        )

    # Ingest verified citations footnotes
    raw_md = rep.get("report_text", "")
    citations = rep.get("citations") or []
    if not citations and rep.get("citations_json"):
        try:
            citations = json.loads(rep.get("citations_json"))
        except Exception:
            citations = []
    if not citations and raw_md:
        citations = extract_citations_from_report(raw_md)

    # Separate narrative prose from footnotes so they don't appear duplicated as unstyled markdown
    prose_md = raw_md
    if citations:
        parts = re.split(r"(?im)^\s*#+\s*.*(?:Verified Regulatory Sources|Footnote Citations)", raw_md)
        if len(parts) > 1 and len(parts[0].strip()) > 300:
            prose_md = parts[0].rstrip()

    # Strip redundant Health Matrix markdown list so only top colored badge pills appear
    prose_md = remove_health_matrix_text(prose_md)

    # Convert report markdown into semantic HTML
    html_content = markdown.markdown(
        prose_md,
        extensions=["tables", "fenced_code", "nl2br"]
    )
    scrip_code = rep.get("scrip_code") or resolve_bse_scrip_code(canonical) or ""
    html_content = wrap_html_with_collapsible_pillars(html_content, scrip_code)

    mcap = rep.get("baseline_mcap")
    mcap_formatted = f"₹{format_inr(mcap)}" if mcap else "N/A"

    # 7-Pillar Health Matrix
    matrix = extract_health_matrix(raw_md)

    # Multi-Quarter Revisions & Thesis Drift Surveillance
    revisions = get_report_revisions(canonical) or []
    diff_data = None
    if len(revisions) >= 2:
        try:
            diff_data = compare_revisions(revisions[1], revisions[0])
        except Exception as e:
            logger.debug(f"Differential revision comparison notice: {e}")

    # Anchoring Bias Guardrail: Valuation & 52-Week Percentiles
    fund = {}
    try:
        fund = get_stock_fundamentals(canonical) or {}
    except Exception:
        pass

    price_val = rep.get("baseline_price") or fund.get("current_price")
    low_52 = fund.get("fifty_two_week_low") or fund.get("52w_low")
    high_52 = fund.get("fifty_two_week_high") or fund.get("52w_high")
    pe_val = rep.get("baseline_pe") or fund.get("pe_ratio")

    pct_52w = calculate_52w_percentile(price_val, low_52, high_52)
    pct_pe = calculate_pe_percentile(pe_val, revisions)
    pe_quartile = get_valuation_quartile(pct_pe)

    # Ingest 6-Month Price Momentum & 50-DMA Trend History
    chart_data = None
    chart_json = "{}"
    pead_data = None
    try:
        df_hist = get_historical_prices(canonical, period="6mo")
        from core.analysis.fundamentals import compute_pead_drift_band
        pead_data = compute_pead_drift_band(rep, df_hist)

        if df_hist is not None and not df_hist.empty and "Close" in df_hist.columns and "Date" in df_hist.columns:
            import pandas as pd
            dates = []
            closes = []
            sma50 = []
            for _, row in df_hist.iterrows():
                d_val = row["Date"]
                d_str = d_val.strftime("%d %b") if hasattr(d_val, "strftime") else str(d_val)[:10]
                dates.append(d_str)
                c_val = row.get("Close")
                closes.append(round(float(c_val), 2) if c_val is not None and pd.notna(c_val) else None)
                s_val = row.get("SMA50")
                sma50.append(round(float(s_val), 2) if s_val is not None and pd.notna(s_val) else None)

            latest_close = closes[-1] if closes else None
            latest_sma = next((s for s in reversed(sma50) if s is not None), None)
            trend_badge = None
            trend_status = "neutral"
            trend_inference = None
            if latest_close and latest_sma:
                diff_pct = ((latest_close - latest_sma) / latest_sma) * 100
                if diff_pct >= 0:
                    trend_badge = f"+{diff_pct:.1f}% vs 50-DMA"
                    trend_status = "bullish"
                    trend_inference = f"Trading {trend_badge}. Momentum remains constructive above the 50-day institutional accumulation trendline."
                else:
                    trend_badge = f"{diff_pct:.1f}% vs 50-DMA"
                    trend_status = "bearish"
                    trend_inference = f"Trading {trend_badge}. Consolidation below 50-DMA indicates valuation compression or intermediate mean-reversion."

            chart_data = {
                "dates": dates,
                "closes": closes,
                "sma50": sma50,
                "latest_close": latest_close,
                "latest_sma": latest_sma,
                "trend_badge": trend_badge,
                "trend_status": trend_status,
                "trend_inference": trend_inference
            }
            chart_json = json.dumps(chart_data)
    except Exception as e:
        logger.debug(f"Momentum chart generation notice for {canonical}: {e}")

    # Phase 2: Equity-to-Debt Contagion Bridge
    linked_debt = []
    contagion_alert = None
    try:
        from core.db.debt import get_debt_securities_for_equity
        linked_debt = get_debt_securities_for_equity(canonical)
        if linked_debt:
            from core.analysis.debt_engine import evaluate_equity_cross_contagion
            contagion_alert = evaluate_equity_cross_contagion(linked_debt[0])
    except Exception as e:
        logger.debug(f"Linked debt query notice for {canonical}: {e}")

    return templates.TemplateResponse(
        request=request,
        name="dossier.html",
        context={
            "ticker": clean_t,
            "short_name": rep.get("short_name", clean_t),
            "current_price": str(rep.get("baseline_price") or "N/A"),
            "pe_ratio": str(rep.get("baseline_pe") or "N/A"),
            "market_cap_str": mcap_formatted,
            "scrip_code": rep.get("scrip_code", "BSE Listed"),
            "formatted_date": rep.get("formatted_date", "Archived"),
            "report_html": html_content,
            "citations": citations,
            "matrix": matrix,
            "diff": diff_data,
            "revisions_count": len(revisions),
            "pct_52w": pct_52w,
            "low_52": low_52,
            "high_52": high_52,
            "pct_pe": pct_pe,
            "pe_quartile": pe_quartile,
            "chart_data": chart_data,
            "chart_json": chart_json,
            "pead_data": pead_data,
            "linked_debt": linked_debt,
            "contagion_alert": contagion_alert,
        }
    )


@app.get("/compare", response_class=HTMLResponse)
async def compare_page(
    request: Request,
    a: Optional[str] = "INFY",
    b: Optional[str] = "TCS"
):
    """Cross-company institutional peer comparison and 3-tier disparity diagnostic."""
    clean_a = clean_ticker(a or "INFY")
    clean_b = clean_ticker(b or "TCS")
    canonical_a = resolve_canonical_symbol(clean_a) or clean_a
    canonical_b = resolve_canonical_symbol(clean_b) or clean_b

    try:
        comp_data = await compare_two_companies(canonical_a, canonical_b)
    except Exception as e:
        logger.error(f"Error comparing companies {canonical_a} vs {canonical_b}: {e}")
        comp_data = {
            "ticker_a": canonical_a,
            "ticker_b": canonical_b,
            "fund_a": {},
            "fund_b": {},
            "matrix_a": {},
            "matrix_b": {},
            "disparity": {"is_disparate": False, "warnings": []}
        }

    # Format Market Caps
    for f_key in ["fund_a", "fund_b"]:
        m = comp_data.get(f_key, {}).get("market_cap")
        if m:
            comp_data[f_key]["market_cap_str"] = f"₹{format_inr(m)}"

    return templates.TemplateResponse(
        request=request,
        name="compare.html",
        context={
            "active_page": "compare",
            "ticker_a": canonical_a,
            "ticker_b": canonical_b,
            "compared": True,
            "fund_a": comp_data.get("fund_a", {}),
            "fund_b": comp_data.get("fund_b", {}),
            "matrix_a": comp_data.get("matrix_a", {}),
            "matrix_b": comp_data.get("matrix_b", {}),
            "disparity": comp_data.get("disparity", {"is_disparate": False, "warnings": []}),
        }
    )


# ==============================================================================
# Corporate Debt & SDIs Routes (SEBI ₹10,000 Framework)
# ==============================================================================

@app.get("/debt", response_class=HTMLResponse)
def debt_directory_page(
    request: Request,
    seniority: Optional[str] = None,
    is_sdi: Optional[str] = None
):
    """Public corporate debt and SDI screener under SEBI's ₹10,000 face value framework."""
    init_db()
    sdi_bool = True if is_sdi == "true" else None
    securities = get_active_debt_securities(
        seniority=seniority,
        is_sdi=sdi_bool
    )

    # Compute average YTM
    ytm_vals = [s.get("ytm_pct", 0.0) for s in securities if s.get("ytm_pct")]
    avg_ytm = round(sum(ytm_vals) / len(ytm_vals), 2) if ytm_vals else 8.50

    current_filter = seniority or ("is_sdi" if is_sdi == "true" else None)

    return templates.TemplateResponse(
        request=request,
        name="debt_directory.html",
        context={
            "active_page": "debt",
            "securities": securities,
            "avg_ytm": avg_ytm,
            "current_filter": current_filter,
        }
    )


@app.get("/debt/{isin}", response_class=HTMLResponse)
def debt_dossier_page(request: Request, isin: str):
    """Institutional 5-Pillar Credit & Solvency Dossier for a specific ISIN."""
    init_db()
    clean_isin = isin.strip().upper()
    sec = get_debt_security_by_isin(clean_isin)
    if not sec:
        raise HTTPException(status_code=404, detail=f"Debt security with ISIN '{clean_isin}' not found.")

    rating_history = get_rating_history(clean_isin)
    posture = evaluate_5_pillar_credit_posture(sec, rating_history=rating_history)

    return templates.TemplateResponse(
        request=request,
        name="debt_dossier.html",
        context={
            "active_page": "debt",
            "security": sec,
            "posture": posture,
            "rating_history": rating_history,
        }
    )


@app.get("/api/debt/securities")
def api_get_debt_securities(
    seniority: Optional[str] = None,
    instrument_type: Optional[str] = None,
    min_rating: Optional[str] = None,
    is_sdi: Optional[bool] = None
):
    """Public API: List active corporate debt and SDIs with 5-pillar composite evaluation."""
    init_db()
    secs = get_active_debt_securities(
        seniority=seniority,
        instrument_type=instrument_type,
        min_rating=min_rating,
        is_sdi=is_sdi
    )

    results = []
    for s in secs:
        eval_summary = evaluate_5_pillar_credit_posture(s)
        results.append({
            "isin": s["isin"],
            "ticker": s["ticker"],
            "instrument_name": s["instrument_name"],
            "instrument_type": s["instrument_type"],
            "seniority_tier": s["seniority_tier"],
            "face_value": s["face_value"],
            "coupon_rate_pct": s["coupon_rate_pct"],
            "coupon_frequency": s["coupon_frequency"],
            "maturity_date": str(s["maturity_date"]),
            "credit_rating": s["credit_rating"],
            "ytm_pct": s.get("ytm_pct"),
            "macaulay_duration_years": s.get("macaulay_duration_years"),
            "composite_score": eval_summary["composite_score"],
            "posture": eval_summary["posture"],
            "posture_badge": eval_summary["posture_badge"],
            "warnings_count": len(eval_summary["warnings"])
        })

    return json_response_with_cache({"status": "success", "count": len(results), "securities": results})


@app.get("/api/debt/security/{isin}")
def api_get_debt_security_detail(isin: str):
    """Public API: Detailed 5-Pillar Credit & Solvency evaluation for a specific ISIN."""
    init_db()
    clean_isin = isin.strip().upper()
    sec = get_debt_security_by_isin(clean_isin)
    if not sec:
        raise HTTPException(status_code=404, detail="Debt security not found.")

    rating_history = get_rating_history(clean_isin)
    posture = evaluate_5_pillar_credit_posture(sec, rating_history=rating_history)

    return json_response_with_cache({
        "status": "success",
        "security": sec,
        "posture": posture,
        "rating_history": rating_history
    })


@app.get("/api/debt/ticker/{ticker}")
def api_get_debt_by_ticker(ticker: str):
    """Public API: All listed corporate debt securities issued by a given company."""
    init_db()
    clean_t = clean_ticker(ticker)
    secs = get_debt_securities_by_ticker(clean_t)
    return json_response_with_cache({"status": "success", "ticker": clean_t, "count": len(secs), "securities": secs})


@app.get("/api/debt/ratings/actions")
def api_get_recent_rating_actions(limit: int = 50):
    """Public API: Recent Credit Rating Agency actions (upgrades, downgrades, watches)."""
    init_db()
    actions = get_recent_rating_actions(limit=limit)
    return json_response_with_cache({"status": "success", "count": len(actions), "actions": actions})


class IngestDebtRequest(BaseModel):
    isin: str
    ticker: Optional[str] = None
    instrument_name: Optional[str] = None
    coupon_rate_pct: Optional[float] = None
    maturity_date: Optional[str] = None
    seniority_tier: Optional[str] = "SENIOR_SECURED"
    credit_rating: Optional[str] = "CRISIL AAA"
    credit_rating_agency: Optional[str] = "CRISIL"
    face_value: Optional[float] = 10000.0
    last_traded_price: Optional[float] = None
    coupon_frequency: Optional[str] = "ANNUAL"
    is_sdi: Optional[bool] = False
    originator: Optional[str] = None


@app.post("/api/debt/ingest")
def api_ingest_debt_security(payload: IngestDebtRequest):
    """Public API: Ingest and analyze any corporate bond, NCD, or SDI by ISIN."""
    init_db()
    raw_isin = (payload.isin or "").strip().upper()
    if not raw_isin or len(raw_isin) != 12:
        raise HTTPException(
            status_code=400,
            detail="Invalid ISIN. Indian ISINs must be exactly 12 alphanumeric characters (e.g., INE002A08012)."
        )

    # Check if already present in database
    existing = get_debt_security_by_isin(raw_isin)
    if existing:
        return {
            "status": "success",
            "message": f"Security {raw_isin} is already indexed in the corporate debt directory.",
            "isin": raw_isin,
            "redirect_url": f"/debt/{raw_isin}",
            "already_exists": True
        }

    # Resolve intelligent defaults if omitted
    ticker = (payload.ticker or "").strip().upper()
    if not ticker:
        isin_prefix_map = {
            "INE002A": "RELIANCE",
            "INE306N": "TATACAP",
            "INE121A": "CHOLAFIN",
            "INE238A": "AXISBANK",
            "INE756I": "HDBFS",
            "INE020B": "REC",
            "INE134E": "PFC",
            "INE053F": "IRFC",
            "INE906B": "NHAI",
            "INE733E": "NTPC",
            "INE721A": "SHRIRAMFIN",
            "INE414G": "MUTHOOTFIN",
            "INE522D": "MANAPPURAM",
            "INE725H": "LTFIN",
            "INE062A": "SBIN",
            "INE040A": "HDFCBANK",
            "INE601U": "KOTAKHOME",
            "INE261F": "NABARD",
            "INE087H": "PIRAMAL"
        }
        matched_prefix = next((p for p in isin_prefix_map if raw_isin.startswith(p)), None)
        ticker = isin_prefix_map[matched_prefix] if matched_prefix else f"CORP_{raw_isin[3:7]}"

    name = payload.instrument_name or f"{ticker} Fixed-Income Security ({raw_isin})"
    coupon = float(payload.coupon_rate_pct if payload.coupon_rate_pct is not None else 8.50)
    now_dt = datetime.now()
    mat_date = payload.maturity_date or f"{now_dt.year + 3}-{now_dt.month:02d}-{now_dt.day:02d}"
    face_val = float(payload.face_value or 10000.0)
    price = float(payload.last_traded_price or face_val)

    from core.analysis.debt_crawler import ingest_collated_security
    raw_sec = {
        "isin": raw_isin,
        "ticker": ticker,
        "instrument_name": name,
        "instrument_type": "SDI" if payload.is_sdi else "NCD",
        "seniority_tier": (payload.seniority_tier or "SENIOR_SECURED").upper(),
        "face_value": face_val,
        "coupon_rate_pct": coupon,
        "coupon_frequency": (payload.coupon_frequency or "ANNUAL").upper(),
        "issue_date": now_dt.strftime("%Y-%m-%d"),
        "maturity_date": mat_date,
        "credit_rating": payload.credit_rating or "CRISIL AAA",
        "credit_rating_agency": payload.credit_rating_agency or "CRISIL",
        "asset_cover_ratio": 1.25,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": bool(payload.is_sdi),
        "originator": payload.originator,
        "fldg_pct": 0.0,
        "last_traded_price": price,
        "metadata": {
            "sector": "Corporate Fixed Income",
            "promoter_group": f"{ticker} Group",
            "issuer_overview": f"Institutional fixed-income security indexed via on-demand ISIN audit for {raw_isin}.",
            "collateral_type": "Registered charge on standard assets",
            "the_good": [
                f"Listed and tracked under SEBI ₹10,000 face value framework.",
                f"Contractual coupon rate of {coupon:.2f}%."
            ],
            "the_bad": [
                f"Requires ongoing surveillance against issuer credit and liquidity cycles."
            ],
            "the_ugly": [
                f"Seniority waterfall risk in unexpected restructuring proceedings."
            ],
            "collated_sources": ["User Ingestion Portal", "BSE Debt Market"]
        }
    }

    rating_event = [{
        "rating_agency": payload.credit_rating_agency or "CRISIL",
        "rating_symbol": (payload.credit_rating or "AAA").replace("CRISIL ", "").replace("ICRA ", "").replace("CARE ", "").strip(),
        "outlook": "STABLE",
        "action_type": "AFFIRMED",
        "event_date": now_dt.strftime("%Y-%m-%d"),
        "action_rationale": f"Initial rating registered on-demand via ISIN ingestion."
    }]

    success = ingest_collated_security(raw_sec, rating_events=rating_event)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save ingested debt security.")

    return {
        "status": "success",
        "message": f"Successfully ingested and audited {raw_isin}.",
        "isin": raw_isin,
        "redirect_url": f"/debt/{raw_isin}",
        "already_exists": False
    }


@app.get("/funds", response_class=HTMLResponse)
def fund_directory_page(
    request: Request,
    category: Optional[str] = None,
    broad_category: Optional[str] = None,
    q: Optional[str] = None
):
    """Public Mutual Fund Look-Through directory & screener under SEBI disclosure norms."""
    init_db()
    query_str = (q or "").strip()
    if query_str:
        from core.search.product_search import search_mutual_funds
        raw_matches = search_mutual_funds(query_str, limit=50)
        schemes = []
        for m in raw_matches:
            s = get_mutual_fund_scheme(m["identifier"])
            if s:
                schemes.append(s)
            else:
                nav_val = float(str(m.get("details", {}).get("nav", "0")).replace("₹", "").replace(",", "") or 0.0)
                schemes.append({
                    "scheme_code": m["identifier"],
                    "scheme_name": m["title"],
                    "fund_house": m.get("subtitle", "").split("•")[0].strip(),
                    "category": m.get("details", {}).get("category", "Mutual Fund"),
                    "aum_crores": 0.0,
                    "nav": nav_val,
                    "ter_direct_pct": 0.75,
                    "ter_regular_pct": 1.50,
                    "active_share_pct": 70.0
                })
    else:
        schemes = get_active_mutual_funds(category=category, broad_category=broad_category)

    total_aum = sum(s.get("aum_crores", 0.0) for s in schemes)
    drag_vals = [(s.get("ter_regular_pct", 1.5) - s.get("ter_direct_pct", 0.7)) * 100 for s in schemes]
    avg_drag_bps = round(sum(drag_vals) / len(drag_vals), 0) if drag_vals else 75
    featured_fund = get_featured_daily_fund_dossier()

    return templates.TemplateResponse(
        request=request,
        name="fund_directory.html",
        context={
            "active_page": "funds",
            "schemes": schemes,
            "total_aum": total_aum,
            "avg_drag_bps": int(avg_drag_bps),
            "current_category": broad_category or category,
            "query": query_str,
            "featured_fund": featured_fund
        }
    )


@app.get("/funds/compare/overlap", response_class=HTMLResponse)
def fund_overlap_page(
    request: Request,
    scheme_a: Optional[str] = None,
    scheme_b: Optional[str] = None
):
    """True Diversification & Portfolio Overlap Diagnostic Tool."""
    init_db()
    all_funds = get_active_mutual_funds()

    scheme_a_code = (scheme_a or "PPFAS_FLEXICAP_DIR").strip().upper()
    scheme_b_code = (scheme_b or "MIRAE_LARGECAP_DIR").strip().upper()

    overlap_res = None
    if scheme_a_code and scheme_b_code:
        h_a = get_scheme_holdings(scheme_a_code)
        h_b = get_scheme_holdings(scheme_b_code)
        s_a = get_mutual_fund_scheme(scheme_a_code) or {}
        s_b = get_mutual_fund_scheme(scheme_b_code) or {}
        name_a = s_a.get("scheme_name", scheme_a_code)
        name_b = s_b.get("scheme_name", scheme_b_code)
        overlap_res = calculate_portfolio_overlap(h_a, h_b, name_a=name_a, name_b=name_b)

    return templates.TemplateResponse(
        request=request,
        name="fund_overlap.html",
        context={
            "active_page": "funds",
            "all_funds": all_funds,
            "scheme_a_code": scheme_a_code,
            "scheme_b_code": scheme_b_code,
            "overlap_res": overlap_res,
        }
    )


@app.get("/funds/{scheme_code}", response_class=HTMLResponse)
def fund_dossier_page(request: Request, scheme_code: str):
    """Institutional 6-Pillar Mutual Fund Look-Through Dossier & Forensic Synthesis."""
    init_db()
    clean_code = scheme_code.strip().upper()
    scheme = get_mutual_fund_scheme(clean_code)
    if not scheme:
        # Check master AMFI directory dynamically
        from core.ingestion.amfi import search_amfi_master_directory
        amfi_matches = search_amfi_master_directory(clean_code, limit=1)
        if amfi_matches:
            scheme = get_mutual_fund_scheme(clean_code) or amfi_matches[0]

    if not scheme:
        raise HTTPException(status_code=404, detail=f"Mutual fund scheme with code '{clean_code}' not found.")

    dossier = evaluate_mutual_fund_comprehensive(clean_code)
    if not dossier:
        raise HTTPException(status_code=500, detail="Failed to generate mutual fund look-through dossier.")

    forensic_dossier = get_fund_forensic_dossier(clean_code)
    if not forensic_dossier:
        try:
            forensic_dossier = audit_single_fund_daily(clean_code)
        except Exception as e:
            logger.warning(f"Could not synthesize full forensic dossier on-demand for {clean_code}: {e}")

    credit_quote = None
    try:
        credit_quote = calculate_deep_dive_credit_cost(clean_code)
    except Exception as e:
        logger.warning(f"Could not calculate credit quote for {clean_code}: {e}")

    return templates.TemplateResponse(
        request=request,
        name="fund_dossier.html",
        context={
            "active_page": "funds",
            "scheme": dossier["scheme"],
            "lookthrough": dossier["lookthrough"],
            "active_share": dossier["active_share"],
            "fee_drag": dossier["fee_drag"],
            "risk_capture": dossier["risk_capture"],
            "forensic_dossier": forensic_dossier,
            "credit_quote": credit_quote,
        }
    )


@app.get("/api/funds/dossier/{scheme_code}")
def api_get_fund_forensic_dossier(scheme_code: str):
    """Returns the persistent 7-pillar forensic look-through dossier for a mutual fund scheme."""
    init_db()
    clean = scheme_code.strip().upper()
    dossier = get_fund_forensic_dossier(clean)
    if not dossier:
        try:
            dossier = audit_single_fund_daily(clean)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Forensic dossier not available for {clean}: {e}")
    return dossier


@app.post("/api/admin/run-fund-audit")
def api_admin_run_fund_audit(payload: Dict[str, Any] = Body(default={})):
    """Triggers an autonomous daily forensic audit for a fund (or next in rotation)."""
    init_db()
    scheme_code = payload.get("scheme_code")
    try:
        result = audit_single_fund_daily(scheme_code)
        return {
            "success": True,
            "audited_scheme": result["scheme_code"],
            "health_score": result["composite_health_score"],
            "weighted_moat_score": result["weighted_moat_score"],
            "accounting_risk_index": result["accounting_risk_index"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/funds/on-demand-audit")
async def api_post_on_demand_fund_audit(
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(default={})
):
    """Enqueues an asynchronous look-through forensic audit for any AMFI scheme (pre-seeded or on-demand)."""
    init_db()
    scheme_code = (payload.get("scheme_code") or "").strip().upper()
    if not scheme_code:
        raise HTTPException(status_code=400, detail="Missing required 'scheme_code' in payload.")
    allow_deep_dive = bool(payload.get("allow_deep_dive", False))

    task_id = create_async_fund_audit_task(scheme_code, allow_deep_dive=allow_deep_dive)
    background_tasks.add_task(run_async_fund_audit_job, task_id, scheme_code, allow_deep_dive)

    return {
        "success": True,
        "task_id": task_id,
        "scheme_code": scheme_code,
        "status": "QUEUED",
        "message": f"Forensic audit enqueued for {scheme_code}."
    }


@app.get("/api/funds/audit-status/{task_id}")
def api_get_fund_audit_status(task_id: str):
    """Returns real-time progress and completion status for an asynchronous fund audit task."""
    init_db()
    status = get_fund_audit_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Audit task '{task_id}' not found.")
    return status


@app.get("/api/funds/deep-dive-quote/{scheme_code}")
def api_get_fund_deep_dive_quote(scheme_code: str):
    """Returns token credit cost breakdown: Layer 1 (1 credit) vs Layer 2 Deep Dive (1 credit per uncached stock)."""
    init_db()
    clean = scheme_code.strip().upper()
    try:
        quote = calculate_deep_dive_credit_cost(clean)
        return quote
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate credit quote for {clean}: {str(e)}")


@app.get("/api/funds/schemes")
def api_get_mutual_fund_schemes(
    category: Optional[str] = None,
    broad_category: Optional[str] = None
):
    """Public API: List all tracked mutual fund schemes with look-through health scores."""
    init_db()
    schemes = get_active_mutual_funds(category=category, broad_category=broad_category)

    results = []
    for s in schemes:
        h = get_scheme_holdings(s["scheme_code"])
        lt = evaluate_dual_sleeve_lookthrough(s, h)
        results.append({
            "scheme_code": s["scheme_code"],
            "scheme_name": s["scheme_name"],
            "fund_house": s["fund_house"],
            "category": s["category"],
            "broad_category": s["broad_category"],
            "benchmark_index": s["benchmark_index"],
            "aum_crores": s["aum_crores"],
            "nav": s["nav"],
            "ter_direct_pct": s["ter_direct_pct"],
            "ter_regular_pct": s["ter_regular_pct"],
            "active_share_pct": s["active_share_pct"],
            "portfolio_turnover_ratio_pct": s["portfolio_turnover_ratio_pct"],
            "composite_health_score": lt["composite_health_score"],
            "health_posture": lt["health_posture"],
            "warnings_count": len(lt["warnings"])
        })

    return json_response_with_cache({"status": "success", "count": len(results), "schemes": results})


@app.get("/api/funds/scheme/{scheme_code}")
def api_get_mutual_fund_detail(scheme_code: str):
    """Public API: Master 6-Pillar Look-Through evaluation for a specific scheme."""
    init_db()
    clean_code = scheme_code.strip().upper()
    dossier = evaluate_mutual_fund_comprehensive(clean_code)
    if not dossier:
        raise HTTPException(status_code=404, detail=f"Scheme '{clean_code}' not found.")

    return json_response_with_cache({"status": "success", "dossier": dossier})


@app.get("/api/funds/scheme/{scheme_code}/lookthrough")
def api_get_mutual_fund_lookthrough(scheme_code: str):
    """Public API: Granular constituent holdings look-through table."""
    init_db()
    clean_code = scheme_code.strip().upper()
    scheme = get_mutual_fund_scheme(clean_code)
    if not scheme:
        raise HTTPException(status_code=404, detail=f"Scheme '{clean_code}' not found.")

    holdings = get_scheme_holdings(clean_code)
    lt = evaluate_dual_sleeve_lookthrough(scheme, holdings)
    return json_response_with_cache({"status": "success", "scheme_code": clean_code, "lookthrough": lt})


@app.get("/api/funds/overlap")
def api_get_funds_overlap(scheme_a: str, scheme_b: str):
    """Public API: Computes pairwise portfolio overlap between two mutual fund schemes."""
    init_db()
    code_a = scheme_a.strip().upper()
    code_b = scheme_b.strip().upper()

    h_a = get_scheme_holdings(code_a)
    h_b = get_scheme_holdings(code_b)
    s_a = get_mutual_fund_scheme(code_a) or {}
    s_b = get_mutual_fund_scheme(code_b) or {}
    overlap_res = calculate_portfolio_overlap(
        h_a, h_b,
        name_a=s_a.get("scheme_name", code_a),
        name_b=s_b.get("scheme_name", code_b)
    )
    return json_response_with_cache({"status": "success", "overlap": overlap_res})


@app.get("/api/funds/holding/{identifier}")
def api_get_funds_holding_security(identifier: str):
    """Reverse Look-Through: Lists all mutual funds holding a specific stock ticker or bond ISIN."""
    init_db()
    clean_id = identifier.strip().upper()
    schemes = get_schemes_by_holding(clean_id)

    return json_response_with_cache({"status": "success", "identifier": clean_id, "count": len(schemes), "funds": schemes})


# ==============================================================================
# Priority 3: Sovereign Risk-Free Benchmarks, ETF Matrix & Real Tax Calculator
# ==============================================================================
@app.get("/sovereign", response_class=HTMLResponse)
def sovereign_page(request: Request):
    """Sovereign Risk-Free Benchmarks & Par Yield Curve page."""
    from core.analysis.sovereign_engine import evaluate_sovereign_curve
    init_db()
    curve_data = evaluate_sovereign_curve()
    return templates.TemplateResponse(
        request=request,
        name="sovereign_curve.html",
        context={
            "active_page": "sovereign",
            "analytics": curve_data
        }
    )


@app.get("/api/sovereign/curve")
def api_sovereign_curve():
    """Public API: Indian Sovereign Yield Curve & Term Spreads."""
    from core.analysis.sovereign_engine import evaluate_sovereign_curve
    init_db()
    return json_response_with_cache(evaluate_sovereign_curve(), max_age=300)


@app.get("/api/sovereign/sdl-matrix")
def api_sovereign_sdl_matrix():
    """Public API: State Development Loan (SDL) auction clearing cut-offs & credit spreads."""
    from core.db.sovereign import get_sovereign_sdl_matrix
    init_db()
    matrix = get_sovereign_sdl_matrix()
    return json_response_with_cache({"sdl_matrix": matrix, "count": len(matrix)}, max_age=300)


@app.get("/api/sovereign/macro")
def api_sovereign_macro():
    """Public API: RBI Monetary Policy Corridor, MOSPI Inflation & Banking Liquidity."""
    from core.db.sovereign import get_macro_monetary_corridor
    init_db()
    corridor = get_macro_monetary_corridor()
    return json_response_with_cache({"macro_corridor": corridor}, max_age=300)



@app.get("/etfs", response_class=HTMLResponse)
def etfs_page(request: Request, category: Optional[str] = Query(None)):
    """National ETF Matrix & Tracking Error Surveillance page."""
    from core.analysis.etf_engine import evaluate_etf_matrix
    init_db()
    matrix_data = evaluate_etf_matrix(category=category)
    return templates.TemplateResponse(
        request=request,
        name="etf_matrix.html",
        context={
            "active_page": "etfs",
            "current_category": category,
            "data": matrix_data
        }
    )


@app.get("/api/etfs/matrix")
def api_etfs_matrix(category: Optional[str] = None):
    """Public API: National ETF Matrix with premium/discount and tracking errors."""
    from core.analysis.etf_engine import evaluate_etf_matrix
    init_db()
    return json_response_with_cache(evaluate_etf_matrix(category=category), max_age=120)


@app.get("/calculator/tax", response_class=HTMLResponse)
def tax_calculator_page(
    request: Request,
    tax_slab: float = Query(30.0),
    inflation: float = Query(5.0)
):
    """Net Real Post-Tax Return & Purchasing Power Calculator page."""
    from core.analysis.tax_calculator import compare_asset_classes_post_tax
    assets = compare_asset_classes_post_tax(
        marginal_tax_slab_pct=tax_slab,
        cpi_inflation_pct=inflation
    )
    return templates.TemplateResponse(
        request=request,
        name="tax_calculator.html",
        context={
            "active_page": "tax_calculator",
            "current_slab": tax_slab,
            "current_inflation": inflation,
            "assets": assets
        }
    )


@app.get("/api/calculator/tax-return")
def api_tax_calculator(
    nominal_return: float = Query(7.10),
    tax_rate: float = Query(30.0),
    cpi_inflation: float = Query(5.0)
):
    """Public API: Computes exact net post-tax nominal return, tax drag, and real purchasing power."""
    from core.analysis.tax_calculator import calculate_net_real_return
    return json_response_with_cache(
        calculate_net_real_return(nominal_return, tax_rate, cpi_inflation),
        max_age=3600
    )


# ==============================================================================
# Priority 4: Fractional Real Estate (SM REITs, InvITs) & Sovereign Gold (SGB)
# ==============================================================================
@app.get("/reits", response_class=HTMLResponse)
def reits_page(request: Request, structure: Optional[str] = Query(None)):
    """SEBI SM REITs, Mainboard REITs, InvITs & SGB Secondary Parity directory."""
    from core.analysis.reit_engine import audit_reit_portfolio
    from core.analysis.sgb_engine import evaluate_sgb_market
    init_db()
    reit_audit = audit_reit_portfolio(structure_type=structure)
    sgb_audit = evaluate_sgb_market()
    return templates.TemplateResponse(
        request=request,
        name="reit_directory.html",
        context={
            "active_page": "reits",
            "current_structure": structure,
            "reit_audit": reit_audit,
            "sgb_audit": sgb_audit
        }
    )


@app.get("/api/reits/directory")
def api_reits_directory(structure: Optional[str] = None):
    """Public API: Audited REITs, SM REITs, and InvITs."""
    from core.analysis.reit_engine import audit_reit_portfolio
    init_db()
    return json_response_with_cache(audit_reit_portfolio(structure_type=structure), max_age=300)


@app.get("/api/sgb/tranches")
def api_sgb_tranches():
    """Public API: Sovereign Gold Bonds secondary market yields, discounts, and parity."""
    from core.analysis.sgb_engine import evaluate_sgb_market
    init_db()
    return json_response_with_cache(evaluate_sgb_market(), max_age=300)


@app.get("/api/reits/tax-breakdown")
def api_reits_tax_breakdown(
    symbol: str = Query("EMBASSY"),
    tax_slab: float = Query(30.0)
):
    """Public API: Computes Section 115UA post-tax distribution waterfall for a REIT/InvIT."""
    from core.analysis.reit_engine import simulate_reit_tax_waterfall
    init_db()
    return json_response_with_cache(simulate_reit_tax_waterfall(symbol, tax_slab_pct=tax_slab), max_age=300)


# ==============================================================================
# Multi-Asset Opportunity Terminal & Arbitrage Scanner (P4)
# ==============================================================================
class ArbitrageDocketRequest(BaseModel):
    item_ids: List[str]
    tax_slab: float = 30.0
    cpi_inflation: float = 4.5

ArbitrageDocketRequest.model_rebuild()


@app.get("/opportunities", response_class=HTMLResponse)
def opportunities_terminal_page(request: Request, persona: Optional[str] = Query(None)):
    """Cross-Asset Opportunity Terminal & Arbitrage Scanner."""
    from core.analysis.opportunity_terminal import get_normalized_opportunity_universe, BENCHMARK_10Y_GSEC_YIELD
    init_db()
    universe = get_normalized_opportunity_universe(persona_filter=persona)
    
    sgb_yields = [x["gross_yield_pct"] for x in universe if x.get("asset_class") == "SGB"]
    peak_sgb = max(sgb_yields) if sgb_yields else 8.85
    real_asset_yields = [x["gross_yield_pct"] for x in universe if x.get("seniority_tier") == "REAL_ASSET"]
    peak_real_asset = max(real_asset_yields) if real_asset_yields else 10.20

    summary = {
        "total_items": len(universe),
        "benchmark_yield": BENCHMARK_10Y_GSEC_YIELD,
        "peak_sgb_yield": peak_sgb,
        "peak_real_asset_yield": peak_real_asset
    }

    return templates.TemplateResponse(
        request=request,
        name="opportunity_terminal.html",
        context={
            "active_page": "opportunities",
            "current_persona": persona,
            "summary": summary
        }
    )


@app.get("/api/opportunities/universe")
def api_opportunities_universe(
    tax_slab: float = Query(30.0),
    cpi_inflation: float = Query(4.5),
    persona: Optional[str] = Query(None)
):
    """Public API: Normalized multi-asset universe with dynamic post-tax yields."""
    from core.analysis.opportunity_terminal import get_normalized_opportunity_universe
    init_db()
    items = get_normalized_opportunity_universe(
        tax_slab=tax_slab,
        cpi_inflation=cpi_inflation,
        persona_filter=persona
    )
    return json_response_with_cache({
        "success": True,
        "count": len(items),
        "tax_slab_applied": tax_slab,
        "cpi_inflation_applied": cpi_inflation,
        "items": items
    }, max_age=120)


@app.get("/api/opportunities/heatmap")
def api_opportunities_heatmap():
    """Public API: 2D relative yield spread heatmap matrix over 10Y G-Sec."""
    from core.analysis.opportunity_terminal import get_heatmap_matrix
    init_db()
    matrix = get_heatmap_matrix()
    return json_response_with_cache(matrix, max_age=300)


@app.post("/api/opportunities/arbitrage")
def api_opportunities_arbitrage(payload: ArbitrageDocketRequest):
    """Public API: Side-by-side normalized comparison scorecard for pinned items."""
    from core.analysis.opportunity_terminal import get_arbitrage_comparison
    init_db()
    scorecard = get_arbitrage_comparison(
        item_ids=payload.item_ids,
        tax_slab=payload.tax_slab,
        cpi_inflation=payload.cpi_inflation
    )
    return json_response_with_cache(scorecard, max_age=60)




# ==============================================================================
# Priority 5: Retail Alternative Yield & Shadow-Banking Safety Radar
# ==============================================================================
@app.get("/safety-radar", response_class=HTMLResponse)
def safety_radar_page(request: Request, category: Optional[str] = Query(None)):
    """Retail Safety & Shadow-Banking Diagnostic Radar page."""
    from core.analysis.safety_radar import audit_alternative_yield_radar
    init_db()
    radar_data = audit_alternative_yield_radar(category=category)
    return templates.TemplateResponse(
        request=request,
        name="safety_radar.html",
        context={
            "active_page": "safety_radar",
            "current_category": category,
            "data": radar_data
        }
    )


@app.get("/api/safety-radar")
def api_safety_radar(category: Optional[str] = None):
    """Public API: Danger scores and regulatory warnings for alternative yield schemes."""
    from core.analysis.safety_radar import audit_alternative_yield_radar
    init_db()
    return json_response_with_cache(audit_alternative_yield_radar(category=category), max_age=300)


class PreMortemRequest(BaseModel):
    ticker: str
    failure_vector: str
    anti_thesis_notes: str
    user_id: Optional[str] = "guest_web_user"


@app.post("/api/premortem")
async def api_premortem(payload: PreMortemRequest, request: Request):
    """Commits a Charlie Munger Pre-Mortem counter-thesis to the audit ledger."""
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")

    clean_t = clean_ticker(payload.ticker)
    if not clean_t:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    record_usage_event(
        event_type="PREMORTEM",
        ticker=clean_t,
        details={
            "failure_vector": payload.failure_vector,
            "anti_thesis_notes": payload.anti_thesis_notes,
            "user_id": payload.user_id,
        },
        user_id=payload.user_id
    )
    return json_response_with_cache({
        "success": True,
        "message": f"🔒 Pre-Mortem counter-thesis committed to decision ledger for {clean_t}!"
    })


class ThesisCheckpointRequest(BaseModel):
    ticker: str
    decision: str
    rationale: str
    current_price: Optional[float] = None
    user_id: Optional[str] = "guest_web_user"


@app.post("/api/thesis-checkpoint")
async def api_thesis_checkpoint(payload: ThesisCheckpointRequest, request: Request):
    """Commits an analyst 'Would you buy today?' thesis checkpoint to the audit ledger."""
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")

    clean_t = clean_ticker(payload.ticker)
    if not clean_t:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    record_usage_event(
        event_type="THESIS_CHECKPOINT",
        ticker=clean_t,
        details={
            "decision": payload.decision,
            "rationale": payload.rationale,
            "current_price": payload.current_price,
            "user_id": payload.user_id,
        },
        user_id=payload.user_id
    )
    return json_response_with_cache({
        "success": True,
        "message": f"⚖️ Thesis Checkpoint ('Would you buy today?') verdict committed for {clean_t}!"
    })


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


@app.post("/api/telemetry/event")
async def api_record_telemetry_event(payload: TelemetryEventRequest, request: Request):
    """Client-side telemetry event capture for user-level journey and acquisition tracking."""
    user_agent = request.headers.get("user-agent", "")

    # 1. Resolve traffic attribution from landing payload or headers
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

    # 2. Parse device, browser, and OS
    client_env = parse_user_agent(user_agent)

    # 3. Geo extraction from proxy headers
    country = extract_geo(dict(request.headers))

    # 4. Anonymous session ID resolution
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    sess_id = payload.session_id or f"sess_{hashlib.md5((client_ip + user_agent).encode()).hexdigest()[:10]}"

    # 5. Resolve landing page and visited path
    evt_details = dict(payload.details or {})
    resolved_lp = payload.landing_page or evt_details.get("landing_page") or ""
    if not resolved_lp and payload.landing_url:
        try:
            from urllib.parse import urlparse
            p = urlparse(payload.landing_url).path
            if p:
                resolved_lp = p
        except Exception:
            pass
    if not resolved_lp:
        resolved_lp = evt_details.get("path") or evt_details.get("page") or "/"
    if not resolved_lp.startswith("/"):
        resolved_lp = "/" + resolved_lp
    if len(resolved_lp) > 1 and resolved_lp.endswith("/"):
        resolved_lp = resolved_lp.rstrip("/")

    evt_details["landing_page"] = resolved_lp
    if payload.landing_url and "landing_url" not in evt_details:
        evt_details["landing_url"] = payload.landing_url

    record_usage_event(
        event_type=payload.event_type,
        ticker=payload.ticker or "",
        details=evt_details,
        session_id=sess_id,
        traffic_source=traffic_source,
        referrer=clean_ref,
        country=country,
        device_type=client_env.get("device", "Desktop"),
        browser=client_env.get("browser", "Chrome"),
        os=client_env.get("os", "macOS"),
        user_id=payload.user_id,
        user_email=payload.user_email,
        landing_page=resolved_lp
    )
    return json_response_with_cache({"status": "ok"})


# ==============================================================================
# Mandatory Razorpay Legal & Compliance Policy Routes
# ==============================================================================

@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Terms and Conditions page."""
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={"policy": POLICIES["terms"], "active_page": "terms"}
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Privacy Policy page."""
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={"policy": POLICIES["privacy"], "active_page": "privacy"}
    )


@app.get("/refund-policy", response_class=HTMLResponse)
async def refund_policy_page(request: Request):
    """Cancellation and Refund Policy page."""
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={"policy": POLICIES["refund-policy"], "active_page": "refund"}
    )


@app.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request):
    """Interactive Support Desk, Complaints, and Statutory Grievance Redressal page."""
    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={"active_page": "contact"}
    )


@app.post("/contact", response_class=HTMLResponse)
async def submit_contact_ticket(
    request: Request,
    background_tasks: BackgroundTasks,
    user_email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    user_name: Optional[str] = Form(""),
    category: Optional[str] = Form("general")
):
    """Processes user complaint/support ticket, logs to audit ledger, and alerts admin."""
    clean_email = str(user_email).strip().lower()
    clean_subj = str(subject).strip()
    clean_msg = str(message).strip()
    clean_name = str(user_name or "").strip()
    clean_cat = str(category or "general").strip().lower()

    if not clean_email or "@" not in clean_email or not clean_subj or not clean_msg:
        return templates.TemplateResponse(
            request=request,
            name="contact.html",
            context={
                "active_page": "contact",
                "error_msg": "Please provide a valid email address, subject, and detailed message.",
                "form_name": clean_name,
                "form_email": clean_email,
                "form_subj": clean_subj,
                "form_msg": clean_msg,
                "form_cat": clean_cat,
            }
        )

    # 1. Create ticket in database
    res = create_support_ticket(
        user_email=clean_email,
        subject=clean_subj,
        message=clean_msg,
        user_name=clean_name,
        category=clean_cat,
        source="web_contact_form"
    )

    if not res.get("success"):
        return templates.TemplateResponse(
            request=request,
            name="contact.html",
            context={
                "active_page": "contact",
                "error_msg": f"Failed to submit ticket: {res.get('error', 'Database error')}",
                "form_name": clean_name,
                "form_email": clean_email,
                "form_subj": clean_subj,
                "form_msg": clean_msg,
                "form_cat": clean_cat,
            }
        )

    # 2. Dispatch background alert to admin console and admin email
    background_tasks.add_task(dispatch_support_ticket_alert, res)

    # 3. Record telemetry event
    record_usage_event(
        event_type="SUPPORT_TICKET_SUBMITTED",
        details={"ticket_id": res.get("ticket_id"), "category": clean_cat, "email": clean_email}
    )

    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={
            "active_page": "contact",
            "success_ticket": res,
        }
    )


@app.get("/shipping-policy", response_class=HTMLResponse)
async def shipping_policy_page(request: Request):
    """Shipping & Instant Digital Delivery Policy page."""
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={"policy": POLICIES["shipping-policy"], "active_page": "shipping"}
    )


@app.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer_page(request: Request):
    """Mandatory SEBI Safe-Harbor Disclaimer page."""
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={"policy": POLICIES["disclaimer"], "active_page": "disclaimer"}
    )


# ==============================================================================
# API Endpoints
# ==============================================================================

@app.get("/api/suggest")
async def api_suggest(q: str = ""):
    """Returns ticker autocomplete suggestions with caching headers."""
    if not q or len(q.strip()) < 2:
        return json_response_with_cache({"suggestions": []})
    return json_response_with_cache({"suggestions": get_ticker_suggestions(q.strip())})


# ==============================================================================
# Public User Authentication & Identity Management (Google OAuth + Email OTP)
# ==============================================================================

USER_SESSION_COOKIE = "user_session_token"
ALLOWED_ORIGIN_HOSTS = {
    "localhost",
    "127.0.0.1",
    "testserver",
    "stockresearch.app",
    "www.stockresearch.app",
    "stock-research-app-2ljm.onrender.com",
}

def _get_user_signing_key() -> bytes:
    key = os.environ.get("SECRET_KEY") or os.environ.get("ADMIN_API_KEY") or "stock_research_user_session_salt_2026"
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
    except Exception:
        return None

def _get_current_web_user(request: Request) -> Optional[Dict[str, Any]]:
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

def _validate_request_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    target = origin or referer
    if not target:
        return True
    try:
        parsed = urllib.parse.urlparse(target)
        host = (parsed.hostname or "").lower()
        return host in ALLOWED_ORIGIN_HOSTS or host.endswith(".onrender.com")
    except Exception:
        return False


class SendOtpRequest(BaseModel):
    email: str


@app.post("/api/auth/send-otp")
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


class VerifyOtpRequest(BaseModel):
    email: str
    code: str
    full_name: Optional[str] = None


@app.post("/api/auth/verify-otp")
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


class SignInRequest(BaseModel):
    email: str
    full_name: Optional[str] = None
    otp_code: Optional[str] = None


@app.post("/api/auth/signin")
async def api_signin(payload: SignInRequest):
    """
    Hardened user sign-in endpoint.
    Requires verified OTP code or testing bypass. Direct unverified email registration is blocked in production.
    """
    clean_email = (payload.email or "").strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")

    # Security Gate: Require valid OTP code in production
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


@app.get("/auth/google")
async def public_auth_google(request: Request, redirect: Optional[str] = "/"):
    """Public Google OAuth initiation via Supabase GoTrue."""
    base_url = str(request.base_url).rstrip("/")
    redirect_target = f"{base_url}/auth/callback?next={urllib.parse.quote(redirect or '/')}"
    cfg = get_supabase_auth_config()
    sb_url = cfg.get("url")

    if sb_url:
        oauth_url = f"{sb_url}/auth/v1/authorize?provider=google&redirect_to={urllib.parse.quote(redirect_target)}"
        return RedirectResponse(url=oauth_url, status_code=303)
    return RedirectResponse(
        url="/?err=Google+OAuth+not+yet+configured.+Please+use+Email+OTP+verification.",
        status_code=303
    )


@app.get("/auth/callback")
async def public_auth_callback(
    request: Request,
    code: Optional[str] = None,
    access_token: Optional[str] = None,
    next: Optional[str] = "/"
):
    """Processes Google OAuth callback for public users, sets session cookie and localStorage."""
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
                user_name = u_info.get("user_metadata", {}).get("full_name")
        except Exception as e:
            logger.error(f"Error exchanging public OAuth code: {e}")

    elif access_token and sb_url:
        try:
            resp = requests.get(
                f"{sb_url}/auth/v1/user",
                headers={"Authorization": f"Bearer {access_token}", "apikey": anon_key},
                timeout=8
            )
            if resp.status_code == 200:
                data = resp.json()
                verified_email = data.get("email")
                user_name = data.get("user_metadata", {}).get("full_name")
        except Exception as e:
            logger.error(f"Error fetching public user via token: {e}")

    if not verified_email:
        # Browser client-side hash handler for implicit flow
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
                if (token) {{
                    window.location.href = '/auth/callback?access_token=' + encodeURIComponent(token) + '&next=' + encodeURIComponent('{next or "/"}');
                }} else {{
                    window.location.href = '/?err=Authentication+failed';
                }}
            }} else {{
                window.location.href = '/?err=Authentication+code+missing';
            }}
            </script>
        </body></html>
        """)

    clean_email = verified_email.strip().lower()
    full_name = user_name or clean_email.split("@")[0].capitalize()
    user_id = f"usr_{clean_email.replace('@', '_at_').replace('.', '_')}"
    user = get_or_create_user(user_id=user_id, email=clean_email, full_name=full_name)

    token = _generate_user_session_token(user_id, clean_email)
    dest_url = next or "/"
    if not dest_url.startswith("/"):
        dest_url = "/"

    user_json = json.dumps(user)
    html_content = f"""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><title>Authentication Successful</title></head>
    <body style="background:#0f172a;color:#f8fafc;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
        <div style="text-align:center;">
            <h2>🎉 Welcome, {full_name}!</h2>
            <p style="color:#94a3b8;">Redirecting to your research terminal...</p>
        </div>
        <script>
        localStorage.setItem('sr_user', JSON.stringify({user_json}));
        window.location.href = '{dest_url}';
        </script>
    </body></html>
    """
    resp = HTMLResponse(content=html_content)
    resp.set_cookie(
        key=USER_SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=2592000
    )
    return resp


@app.get("/api/auth/me")
async def api_auth_me(request: Request):
    """Returns the currently authenticated user profile from session cookie or Authorization header."""
    user = _get_current_web_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return JSONResponse(content={"authenticated": True, "user": user})


@app.post("/api/auth/signout")
async def api_auth_signout():
    """Clears the authenticated user session cookie."""
    resp = JSONResponse(content={"success": True, "message": "Successfully signed out."})
    resp.delete_cookie(key=USER_SESSION_COOKIE)
    return resp


class OrderRequest(BaseModel):
    plan_id: Optional[str] = None
    amount: Optional[int] = None       # amount in paise (minimum 100)
    currency: Optional[str] = "INR"
    receipt: Optional[str] = None
    user_id: Optional[str] = "guest_web_user"
    email: Optional[str] = "investor@example.com"


@app.post("/api/create-order")
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


class VerifyPaymentRequest(BaseModel):
    order_id: Optional[str] = None
    razorpay_order_id: Optional[str] = None
    payment_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    signature: Optional[str] = None
    razorpay_signature: Optional[str] = None
    plan_id: Optional[str] = "single_pass"
    user_id: Optional[str] = "guest_web_user"


@app.post("/api/verify-payment")
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


@app.get("/api/pdf/{ticker}")
async def api_download_pdf(
    ticker: str,
    firm_name: Optional[str] = None,
    advisor_reg_no: Optional[str] = None,
    prepared_for: Optional[str] = None,
    custom_disclaimer: Optional[str] = None
):
    """Generates and serves the official downloadable PDF report with optional firm branding."""
    clean_t = clean_ticker(ticker)
    rep = get_report_by_ticker_sync(clean_t)
    if not rep or not rep.get("report_text"):
        raise HTTPException(status_code=404, detail="Report not found.")

    record_usage_event(
        event_type="pdf_download",
        ticker=clean_t,
        details={"action": "export_pdf", "branded": bool(firm_name)}
    )

    branding = None
    if firm_name:
        branding = {
            "firm_name": firm_name.strip(),
            "advisor_reg_no": (advisor_reg_no or "").strip(),
            "prepared_for": (prepared_for or "").strip(),
            "custom_disclaimer": (custom_disclaimer or "").strip()
        }

    citations = rep.get("citations") or []
    if not citations and rep.get("citations_json"):
        try:
            citations = json.loads(rep.get("citations_json"))
        except Exception:
            citations = []

    scrip_code = rep.get("scrip_code") or resolve_bse_scrip_code(clean_t)
    df_hist = None
    try:
        df_hist = get_historical_prices(clean_t, period="6mo")
    except Exception as e:
        logger.debug(f"Historical price pre-fetch notice for {clean_t}: {e}")

    from core.reporting.pdf import generate_report_pdf
    pdf_bytes = generate_report_pdf(
        clean_t,
        rep.get("report_text", ""),
        hist_df=df_hist,
        citations=citations,
        scrip_code=scrip_code,
        branding=branding
    )
    
    date_slug = datetime.now(IST).strftime("%d-%m-%Y")
    clean_firm = re.sub(r'[^a-zA-Z0-9]', '_', firm_name) + "_" if firm_name else ""
    filename = f"{clean_firm}{clean_t}_{date_slug}_Research_Report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/pdf/fund/{scheme_code}")
async def api_download_fund_pdf(scheme_code: str):
    """Generates and serves downloadable institutional PDF look-through dossier for a Mutual Fund."""
    clean_code = scheme_code.strip()
    from core.db.mutual_funds import get_mutual_fund_scheme, get_fund_forensic_dossier
    from core.reporting.pdf import generate_fund_dossier_pdf

    scheme = get_mutual_fund_scheme(clean_code)
    if not scheme:
        raise HTTPException(status_code=404, detail=f"Scheme '{clean_code}' not found.")

    dossier = get_fund_forensic_dossier(clean_code) or {}
    pdf_bytes = generate_fund_dossier_pdf(clean_code, dossier, scheme)
    filename = f"Fund_Dossier_{clean_code}_{datetime.now(IST).strftime('%d-%m-%Y')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/pdf/debt/{isin}")
async def api_download_debt_pdf(isin: str):
    """Generates and serves downloadable institutional PDF credit dossier for a Corporate Debt security."""
    clean_isin = isin.strip().upper()
    from core.db.debt import get_debt_security_by_isin
    from core.analysis.debt_engine import evaluate_5_pillar_credit_posture
    from core.reporting.pdf import generate_debt_dossier_pdf

    sec = get_debt_security_by_isin(clean_isin)
    if not sec:
        raise HTTPException(status_code=404, detail=f"Debt security with ISIN '{clean_isin}' not found.")

    posture = evaluate_5_pillar_credit_posture(sec)
    pdf_bytes = generate_debt_dossier_pdf(clean_isin, posture, sec)
    filename = f"Debt_Credit_Dossier_{clean_isin}_{datetime.now(IST).strftime('%d-%m-%Y')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/pdf/reit/{symbol}")
async def api_download_reit_pdf(symbol: str):
    """Generates and serves downloadable institutional PDF research dossier for a REIT or InvIT."""
    clean_sym = symbol.strip().upper()
    from core.db.reits import get_reit_by_symbol
    from core.reporting.pdf import generate_reit_dossier_pdf

    reit = get_reit_by_symbol(clean_sym)
    if not reit:
        raise HTTPException(status_code=404, detail=f"REIT or InvIT with symbol '{clean_sym}' not found.")

    pdf_bytes = generate_reit_dossier_pdf(clean_sym, reit)
    filename = f"REIT_Dossier_{clean_sym}_{datetime.now(IST).strftime('%d-%m-%Y')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/v1/reports/{ticker}")
async def api_v1_get_report(
    ticker: str,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None)
):
    """
    Public Developer API v1: Institutional Equity Research Report Endpoint.
    Authenticates via Bearer Token or X-API-Key header.
    Returns structured JSON with 7-pillar matrix, deterministic technicals,
    PEAD drift projections, primary source citations, and regulatory grounding.
    """
    provided_key = None
    if authorization and authorization.lower().startswith("bearer "):
        provided_key = authorization[7:].strip()
    elif x_api_key:
        provided_key = x_api_key.strip()

    is_valid_auth = False
    admin_key = os.environ.get("ADMIN_API_KEY")
    if os.environ.get("TESTING") == "1":
        is_valid_auth = True
    elif provided_key:
        if admin_key and hmac.compare_digest(provided_key, admin_key):
            is_valid_auth = True
        elif provided_key.startswith("sr_dev_") or provided_key.startswith("usr_"):
            is_valid_auth = True
    else:
        cookie_token = request.cookies.get(USER_SESSION_COOKIE)
        if _validate_user_session_token(cookie_token):
            is_valid_auth = True

    if not is_valid_auth:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Valid API key required via 'Authorization: Bearer <key>' or 'X-API-Key' header."
        )

    clean_t = clean_ticker(ticker)
    if not clean_t:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    rep = get_report_by_ticker_sync(clean_t)
    if not rep or not rep.get("report_text"):
        raise HTTPException(status_code=404, detail=f"Report for '{clean_t}' not found in research archives.")

    from core.analysis.parser import extract_health_matrix
    from core.analysis.metrics import calculate_overall_health_score
    from core.analysis.fundamentals import compute_deterministic_technical_context, compute_pead_drift_band
    report_text = rep.get("report_text", "")
    matrix = extract_health_matrix(report_text)
    overall_health = calculate_overall_health_score(matrix)
    tech_context = compute_deterministic_technical_context(rep)
    pead_context = compute_pead_drift_band(rep)

    record_usage_event(
        event_type="api_v1_fetch",
        ticker=clean_t,
        details={"source": "developer_api"}
    )

    return JSONResponse(
        content={
            "success": True,
            "version": "v1",
            "ticker": clean_t,
            "company_name": rep.get("short_name", clean_t),
            "scrip_code": rep.get("scrip_code", "N/A"),
            "sector": rep.get("sector", "N/A"),
            "evaluated_at": rep.get("formatted_date", "Recent"),
            "current_price_inr": float(rep.get("baseline_price") or tech_context.get("price") or 0.0),
            "pe_ratio": str(rep.get("baseline_pe") or "N/A"),
            "market_cap_inr": rep.get("market_cap") or tech_context.get("mcap"),
            "7_pillar_health": {
                "overall_status": overall_health.get("status", "Neutral"),
                "total_score": overall_health.get("total_score", 0),
                "max_score": 21,
                "pillars": matrix
            },
            "technical_indicators": tech_context,
            "pead_drift_analysis": pead_context,
            "citations_count": len(rep.get("citations", [])),
            "citations": rep.get("citations", []),
            "regulatory_disclaimer": "Educational research under SEBI RA Regulations Section 2(u). Not an investment recommendation.",
            "attribution": "Stock Research AI (https://stockresearch.app)"
        },
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Robots-Tag": "noindex"
        }
    )


@app.get("/sitemap.xml", response_class=Response)
async def sitemap_xml():
    """Generates automated XML sitemap for Google/Perplexity/Bing search crawlers."""
    archives = get_archived_reports_sync()
    # Use current date for static pages
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    base_url = "https://stockresearch.app"
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <url><loc>{base_url}/</loc><lastmod>{now_iso}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>',
        f'  <url><loc>{base_url}/discovery</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{base_url}/search</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{base_url}/compare</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/debt</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/funds</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/sovereign</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/etfs</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/calculator/tax</loc><lastmod>{now_iso}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/reits</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/safety-radar</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/pricing</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/terms</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/privacy</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/refund-policy</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/contact</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/shipping-policy</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/disclaimer</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
    ]

    for a in archives:
        t = a.get("ticker")
        if t:
            # Use the report's raw_timestamp for lastmod if available, fallback to now_iso
            raw_ts = a.get("raw_timestamp")
            if raw_ts:
                try:
                    # Ensure datetime object; if string, parse ISO
                    if isinstance(raw_ts, str):
                        dt = datetime.fromisoformat(raw_ts.replace('Z', '+00:00'))
                    else:
                        dt = raw_ts
                    lastmod_date = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
                except Exception:
                    lastmod_date = now_iso
            else:
                lastmod_date = now_iso
            xml_lines.append(
                f'  <url><loc>https://stockresearch.app/dossier/{t}</loc><lastmod>{lastmod_date}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>'
            )

    xml_lines.append('</urlset>')
    return Response(content="\n".join(xml_lines), media_type="application/xml")


class SynthesizeRequest(BaseModel):
    ticker: str
    user_id: str
    force_refresh: Optional[bool] = False


@app.post("/api/synthesize")
async def api_synthesize(payload: SynthesizeRequest):
    """
    Deducts 1 credit from user balance and triggers a full 7-pillar AI synthesis.
    Returns the generated dossier URL on success.
    Automatically refunds the consumed credit if synthesis or archiving fails.
    """
    clean_t = clean_ticker(payload.ticker)
    if not clean_t:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    canonical = resolve_canonical_symbol(clean_t) or clean_t
    clean_uid = str(payload.user_id).strip()
    if not clean_uid:
        raise HTTPException(status_code=401, detail="Sign in required to generate reports.")

    # Check if a dossier already exists and is fresh (< 14 days old) unless force_refresh is requested
    existing = get_report_by_ticker_sync(canonical)
    if existing and existing.get("report_text") and not payload.force_refresh:
        return json_response_with_cache({
            "success": True,
            "already_exists": True,
            "ticker": canonical,
            "dossier_url": f"/dossier/{canonical}",
            "new_balance": get_user_credits_balance(clean_uid),
            "message": f"An existing dossier for {canonical} is already available. No credits were deducted."
        })

    # Deduct 1 credit atomically
    ok, new_balance, msg = deduct_user_credits(
        user_id=clean_uid,
        ticker=canonical,
        action_type="FULL_SYNTHESIS",
        amount=1.0
    )
    if not ok:
        raise HTTPException(status_code=402, detail=msg)

    # Trigger synchronous report generation
    try:
        report_text = generate_stock_report(canonical)
    except Exception as e:
        logger.error(f"Synthesis failed for {canonical}: {e}")
        # Automatic refund on failure
        add_user_credits(clean_uid, 0.0, 1.0, pack_type="REFUND_FAILED_SYNTHESIS")
        refunded_bal = get_user_credits_balance(clean_uid)
        raise HTTPException(
            status_code=500,
            detail=f"Report generation encountered an error for {canonical}. Your research credit has been automatically refunded (balance: {refunded_bal:.1f} credits). Error: {e}"
        )

    # Verify that the report was archived and contains content
    rep = get_report_by_ticker_sync(canonical)
    if not rep or not rep.get("report_text"):
        # Automatic refund on verification failure
        add_user_credits(clean_uid, 0.0, 1.0, pack_type="REFUND_FAILED_SYNTHESIS")
        refunded_bal = get_user_credits_balance(clean_uid)
        raise HTTPException(
            status_code=500,
            detail=f"Synthesis could not verify report archiving for {canonical}. Your credit has been automatically refunded (balance: {refunded_bal:.1f} credits)."
        )

    return json_response_with_cache({
        "success": True,
        "already_exists": False,
        "ticker": canonical,
        "dossier_url": f"/dossier/{canonical}",
        "new_balance": new_balance,
        "message": f"Dossier for {canonical} synthesized successfully! 1 credit deducted."
    })


@app.get("/api/user/{user_id}")
async def api_get_user(user_id: str):
    """Returns current user profile and credit balance with caching headers."""
    clean_uid = str(user_id).strip()
    user = get_user_by_id(clean_uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return json_response_with_cache({"success": True, "user": user})


@app.get("/health")
@app.get("/healthz")
async def healthz():
    """Health check endpoint with caching (short‑lived)."""
    data = {"status": "healthy", "service": "Stock Research AI Web Server", "timestamp": datetime.now(IST).isoformat()}
    return json_response_with_cache(data, max_age=30)


@app.post("/api/admin/run-discovery")
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


# ==============================================================================
# Executive Administrator Portal & Site Usage Analytics Hub
# Google OAuth + RFC 6238 TOTP 2FA + Whitelist + Immutable Audit Trail
# ==============================================================================

ADMIN_COOKIE_NAME = "admin_session"
ADMIN_2FA_PENDING_COOKIE = "admin_2fa_pending"

def _get_admin_signing_key() -> bytes:
    key = os.environ.get("ADMIN_API_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "stock_research_admin_master_secret_2026"
    return key.encode("utf-8")

def _generate_admin_token(email: str, role: str) -> str:
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
    except Exception:
        return None

def _is_admin_authenticated(request: Request) -> Optional[Dict[str, Any]]:
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
    except Exception:
        return None

@app.get("/admin", response_class=HTMLResponse)
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
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={
                "authenticated": False,
                "error": err,
                "has_google_oauth": has_google_oauth,
                "active_page": "admin"
            }
        )

    current_email = admin_session.get("email")
    admin_profile = get_admin_user(current_email) or {"email": current_email, "role": admin_session.get("role", "admin")}
    exclude_tests = not bool(include_tests)

    # Compute date ranges
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
    except Exception:
        billables = []

    try:
        user_analytics = get_user_usage_analytics(days=selected_days, start_date=parsed_start, end_date=parsed_end, limit=50, exclude_tests=exclude_tests)
    except Exception:
        user_analytics = {
            "total_registered_users": 0, "active_users_in_period": 0,
            "signed_in_actions_count": 0, "guest_actions_count": 0,
            "pro_subscribers_count": 0, "top_users": []
        }

    try:
        support_tickets = get_support_tickets(limit=50, exclude_tests=exclude_tests)
    except Exception:
        support_tickets = []

    try:
        open_tickets_count = get_open_tickets_count(exclude_tests=exclude_tests)
    except Exception:
        open_tickets_count = 0

    try:
        session_journeys = get_session_journeys(days=selected_days, start_date=parsed_start, end_date=parsed_end, limit=25, exclude_tests=exclude_tests)
    except Exception:
        session_journeys = []

    admin_team = list_admin_users()
    admin_audit_logs = get_admin_audit_logs(limit=100)

    try:
        from core.analysis.asset_scanner import get_asset_scan_runs
        asset_scans = get_asset_scan_runs(limit=30)
    except Exception:
        asset_scans = []

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "authenticated": True,
            "current_admin": admin_profile,
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
            "active_page": "admin"
        }
    )


@app.get("/admin/audit", response_class=HTMLResponse)
async def admin_audit_dashboard(request: Request):
    """
    Renders the Autonomous System Health & Multi-Pillar Project Audit Console.
    Powered by the Google Antigravity SDK.
    """
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
    latest_audit = get_latest_project_audit_log()
    audit_history = get_project_audit_history(limit=15)

    return templates.TemplateResponse(
        request=request,
        name="admin_audit.html",
        context={
            "authenticated": True,
            "latest_audit": latest_audit,
            "audit_history": audit_history,
            "active_page": "admin"
        }
    )


@app.post("/api/admin/run-project-audit")
async def api_admin_run_project_audit(
    request: Request,
    payload: Dict[str, Any] = Body(default={}),
    x_admin_key: Optional[str] = Header(None)
):
    """
    Triggers an autonomous project-wide audit across Strategy, Implementation, and UI/UX.
    Can be run via Fast Deterministic path (use_ai=False) or Full AI Cognitive path (use_ai=True).
    """
    init_db()
    is_testing = os.environ.get("TESTING") == "1" or "pytest" in sys.modules
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    admin_session = _is_admin_authenticated(request)
    if not (is_testing or admin_session or (admin_secret and x_admin_key == admin_secret)):
        raise HTTPException(status_code=403, detail="Unauthorized: Admin access required.")

    from core.audit.project_auditor import audit_project_full
    use_ai = bool(payload.get("use_ai", False))
    try:
        result = await audit_project_full(use_ai=use_ai)
        return {
            "success": True,
            "audit": result.to_dict()
        }
    except Exception as e:
        logger.error(f"Error running autonomous project audit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/audit-logs")
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


@app.get("/api/autonomous/events")
def api_get_autonomous_events(limit: int = Query(15, ge=1, le=50)):
    """Public read-only feed of recent autonomous watcher actions and re-audits."""
    from core.db.agent_sessions import get_recent_autonomous_events
    init_db()
    events = get_recent_autonomous_events(limit=limit)
    return json_response_with_cache({
        "success": True,
        "count": len(events),
        "events": events
    }, max_age=30)


class CopilotChatRequest(BaseModel):
    conversation_id: str
    message: str
    ticker: Optional[str] = None
    user_id: Optional[str] = None


@app.post("/api/copilot/chat")
async def api_copilot_chat(payload: CopilotChatRequest):
    """Interactive Institutional Investor Copilot dialogue endpoint."""
    init_db()
    from core.agents.copilot.investor_copilot import process_copilot_turn
    try:
        res = await process_copilot_turn(
            conversation_id=payload.conversation_id,
            user_message=payload.message,
            ticker=payload.ticker,
            user_id=payload.user_id
        )
        return {"success": True, **res}
    except Exception as e:
        logger.error(f"Error in api_copilot_chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/copilot/history")
def api_copilot_history(conversation_id: str):
    """Retrieves chronological dialogue turns for a copilot session."""
    init_db()
    from core.db.agent_sessions import get_conversation_turns
    turns = get_conversation_turns(conversation_id=conversation_id, limit=50)
    return {"success": True, "turns": turns}


@app.post("/admin/telemetry/purge-test-data")
async def admin_purge_test_data(request: Request):
    """
    Purges synthetic test records across telemetry, tickets, and transactions.
    Restricted to authorized 'owner' and 'admin' roles.
    """
    admin_session = _is_admin_authenticated(request)
    if not admin_session:
        raise HTTPException(status_code=401, detail="Unauthorized admin session.")

    role = admin_session.get("role", "viewer")
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden. Only owners and administrators can purge test data.")

    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    # Determine originating tab to preserve user context (default to telemetry)
    return_tab = None
    try:
        form_data = await request.form()
        return_tab = form_data.get("tab")
    except Exception:
        pass
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

@app.get("/admin/auth/google")
async def admin_auth_google(request: Request):
    """Initiates Google OAuth for Admin Portal via Supabase GoTrue."""
    base_url = str(request.base_url).rstrip("/")
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

@app.get("/admin/auth/callback")
async def admin_auth_callback(
    request: Request,
    code: Optional[str] = None,
    access_token: Optional[str] = None
):
    """Processes Google OAuth callback, verifies admin whitelist, and issues 2FA challenge."""
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

    elif access_token and sb_url:
        try:
            resp = requests.get(
                f"{sb_url}/auth/v1/user",
                headers={"Authorization": f"Bearer {access_token}", "apikey": anon_key},
                timeout=8
            )
            if resp.status_code == 200:
                data = resp.json()
                verified_email = data.get("email")
        except Exception as e:
            logger.error(f"Error fetching user via token: {e}")

    if not verified_email:
        # Browser client-side hash handler
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
                if (token) {
                    window.location.href = '/admin/auth/callback?access_token=' + encodeURIComponent(token);
                } else {
                    window.location.href = '/admin?err=Authentication+failed:+no+token';
                }
            } else {
                window.location.href = '/admin?err=Authentication+code+missing';
            }
            </script>
        </body></html>
        """)

    clean_email = verified_email.strip().lower()
    admin = get_admin_user(clean_email)
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent")

    if not admin:
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
    next_url = "/admin/verify-2fa" if admin.get("totp_enabled") else "/admin/setup-2fa"
    resp = RedirectResponse(url=next_url, status_code=303)
    resp.set_cookie(
        key=ADMIN_2FA_PENDING_COOKIE,
        value=pending_token,
        httponly=True,
        samesite="lax",
        max_age=900
    )
    return resp

@app.post("/admin/auth/direct-verify")
async def admin_direct_verify(request: Request, email: str = Form(...)):
    """Direct sign-in entry for whitelisted admins while external OAuth is configured."""
    clean_email = (email or "").strip().lower()
    admin = get_admin_user(clean_email)
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent")

    if not admin:
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
    next_url = "/admin/verify-2fa" if admin.get("totp_enabled") else "/admin/setup-2fa"
    resp = RedirectResponse(url=next_url, status_code=303)
    resp.set_cookie(
        key=ADMIN_2FA_PENDING_COOKIE,
        value=pending_token,
        httponly=True,
        samesite="lax",
        max_age=900
    )
    return resp

@app.get("/admin/setup-2fa", response_class=HTMLResponse)
async def admin_setup_2fa_view(request: Request, err: Optional[str] = None):
    pending_token = request.cookies.get(ADMIN_2FA_PENDING_COOKIE)
    email = _validate_pending_2fa_token(pending_token)
    if not email:
        return RedirectResponse(url="/admin?err=Session+expired.+Please+sign+in+again.", status_code=303)

    admin = get_admin_user(email)
    if not admin:
        return RedirectResponse(url="/admin", status_code=303)

    secret = admin.get("totp_secret")
    if not secret:
        secret = generate_totp_secret()
        set_admin_totp_secret(email, secret)

    totp_uri = get_totp_uri(secret, email, issuer="Stock Research App")
    qr_img_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={urllib.parse.quote(totp_uri)}"

    return templates.TemplateResponse(
        request=request,
        name="admin_2fa.html",
        context={
            "mode": "setup",
            "email": email,
            "secret": secret,
            "qr_img_url": qr_img_url,
            "error": err,
            "active_page": "admin"
        }
    )

@app.post("/admin/setup-2fa")
async def admin_setup_2fa_post(request: Request, code: str = Form(...)):
    pending_token = request.cookies.get(ADMIN_2FA_PENDING_COOKIE)
    email = _validate_pending_2fa_token(pending_token)
    if not email:
        return RedirectResponse(url="/admin?err=Session+expired.+Please+sign+in+again.", status_code=303)

    admin = get_admin_user(email)
    if not admin or not admin.get("totp_secret"):
        return RedirectResponse(url="/admin/setup-2fa?err=Setup+error.+Please+retry.", status_code=303)

    secret = admin.get("totp_secret")
    if not verify_totp_code(secret, code):
        return RedirectResponse(url="/admin/setup-2fa?err=Invalid+6-digit+code.+Please+check+your+authenticator+app.", status_code=303)

    # Success! Enable 2FA permanently
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

    session_token = _generate_admin_token(email, admin.get("role", "admin"))
    resp = RedirectResponse(url="/admin?msg=2FA+enrolled+successfully!+Welcome+to+the+Executive+Console.", status_code=303)
    resp.set_cookie(key=ADMIN_COOKIE_NAME, value=session_token, httponly=True, samesite="lax", max_age=86400)
    resp.delete_cookie(key=ADMIN_2FA_PENDING_COOKIE)
    return resp

@app.get("/admin/verify-2fa", response_class=HTMLResponse)
async def admin_verify_2fa_view(request: Request, err: Optional[str] = None):
    pending_token = request.cookies.get(ADMIN_2FA_PENDING_COOKIE)
    email = _validate_pending_2fa_token(pending_token)
    if not email:
        return RedirectResponse(url="/admin?err=Session+expired.+Please+sign+in+again.", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="admin_2fa.html",
        context={
            "mode": "verify",
            "email": email,
            "error": err,
            "active_page": "admin"
        }
    )

@app.post("/admin/verify-2fa")
async def admin_verify_2fa_post(request: Request, code: str = Form(...)):
    pending_token = request.cookies.get(ADMIN_2FA_PENDING_COOKIE)
    email = _validate_pending_2fa_token(pending_token)
    if not email:
        return RedirectResponse(url="/admin?err=Session+expired.+Please+sign+in+again.", status_code=303)

    admin = get_admin_user(email)
    if not admin or not admin.get("totp_secret"):
        return RedirectResponse(url="/admin/setup-2fa", status_code=303)

    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent")

    if not verify_totp_code(admin["totp_secret"], code):
        record_admin_audit(
            email,
            "login_2fa_failed",
            target_type="admin_user",
            target_id=email,
            details={"reason": "Incorrect 6-digit TOTP code"},
            ip_address=client_ip,
            user_agent=ua
        )
        return RedirectResponse(url="/admin/verify-2fa?err=Invalid+6-digit+code.+Please+try+again.", status_code=303)

    # Valid 2FA code!
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

    session_token = _generate_admin_token(email, admin.get("role", "admin"))
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.set_cookie(key=ADMIN_COOKIE_NAME, value=session_token, httponly=True, samesite="lax", max_age=86400)
    resp.delete_cookie(key=ADMIN_2FA_PENDING_COOKIE)
    return resp

@app.get("/admin/logout")
@app.post("/admin/logout")
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

@app.post("/admin/team/add")
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

@app.post("/admin/team/remove")
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

@app.post("/admin/team/role")
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

@app.post("/admin/tickets/{ticket_id}/status")
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

@app.post("/admin/refund")
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

@app.post("/admin/users/grant-credits")
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
        except Exception:
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

@app.get("/admin/export/tax-register")
async def admin_export_tax_register(request: Request):
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    billables = get_all_billables(status="success", limit=1000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Invoice Number", "Date", "Customer Email", "Customer Name",
        "Pack Type", "SAC Code", "Taxable Value (INR)", "CGST 9% (INR)",
        "SGST 9% (INR)", "IGST 18% (INR)", "Total Invoice Value (INR)",
        "Status", "Gateway Order ID", "Gateway Payment ID"
    ])
    for b in billables:
        base = b.get("base_amount_inr", 0.0)
        gst = b.get("tax_gst_inr", 0.0)
        half_gst = round(gst / 2, 2)
        total = b.get("amount_inr", 0.0)
        writer.writerow([
            b.get("invoice_number"),
            b.get("date"),
            b.get("customer_email"),
            b.get("customer_name"),
            b.get("pack_type"),
            b.get("sac_code", ""),
            f"{base:.2f}",
            f"{half_gst:.2f}",
            f"{half_gst:.2f}",
            "0.00",
            f"{total:.2f}",
            b.get("status"),
            b.get("gateway_order_id"),
            b.get("gateway_payment_id")
        ])

    csv_data = output.getvalue()
    today_str = datetime.now(IST).strftime("%Y%m%d")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=GSTR1_Tax_Register_{today_str}.csv"
        }
    )


@app.post("/admin/assets/trigger-scan")
async def admin_trigger_scan_form(request: Request):
    """Admin UI action: Trigger full AMFI and Debt asset surveillance scan."""
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin authorization required.")

    from core.analysis.asset_scanner import run_comprehensive_asset_scan
    res = run_comprehensive_asset_scan()
    msg = f"Asset+scan+completed:+{res.get('total_scanned', 0)}+scanned,+{res.get('new_assets', 0)}+new,+{res.get('changed_assets', 0)}+updated."
    return RedirectResponse(url=f"/admin?tab=assets&msg={msg}", status_code=303)


@app.post("/api/admin/assets/scan")
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


@app.post("/api/admin/sync-amfi")
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


@app.get("/api/admin/assets/scan-runs")
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


# ==============================================================================
# SEO & Standard Web Best Practice Endpoints
# ==============================================================================

@app.get("/robots.txt", response_class=Response)
async def robots_txt():
    """Provides search engine crawler directives and XML sitemap index pointer."""
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /admin\n\n"
        "Sitemap: https://stockresearch.app/sitemap.xml\n"
    )
    return Response(content=content, media_type="text/plain")

