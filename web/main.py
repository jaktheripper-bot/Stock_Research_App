"""
Moatnomics - FastAPI Web Application.

High-performance Server-Side Rendered (SSR) institutional equity research portal.
Provides:
- Razorpay-compliant public landing page & mandatory legal policies
- Zero-latency crawlable dossier URLs for Google SEO & GEO answer engines
- Interactive UPI and card checkout endpoints
- Instant PDF report export downloads
- Modular domain routers for Auth/Billing, Dossier Intelligence, Markets, and Admin.
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
import statistics
import collections
import urllib.parse
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

logger = logging.getLogger("equity_research.web")

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception as dot_err:
    logger.debug("dotenv load notice: %s", dot_err)

try:
    import toml
    _sec_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".streamlit", "secrets.toml")
    if os.path.exists(_sec_path):
        _sec = toml.load(_sec_path)
        for _k, _v in _sec.items():
            if isinstance(_v, str) and _k not in os.environ:
                os.environ[_k] = _v
except Exception as toml_err:
    logger.debug("secrets.toml load notice: %s", toml_err)

from pydantic import BaseModel

from core.db import (
    init_db,
    get_archived_reports_sync,
    get_all_equities_directory_sync,
    SECTOR_TAXONOMY,
    get_report_by_ticker_sync,
    get_report_revisions,
    get_or_create_user,
    get_user_by_id,
    get_user_by_email,
    get_user_credits_balance,
    deduct_user_credits,
    add_user_credits,
    is_ticker_unlocked_for_user,
    unlock_ticker_for_user,
    get_user_unlocked_tickers,
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
from core.notify import dispatch_support_ticket_alert
from core.analysis import get_stock_fundamentals, get_historical_prices
from core.analysis.dossier_report_synthesis import generate_stock_report
from core.analysis.peer_comparison import compare_two_companies
from core.analysis.parser import (
    extract_health_matrix,
    compare_revisions,
    remove_health_matrix_text,
    wrap_html_with_collapsible_pillars,
    wrap_fund_dossier_with_collapsible_dimensions,
)
from core.analysis.metrics import calculate_52w_percentile, calculate_pe_percentile, get_valuation_quartile
from core.billing import (
    PRICING_PACKS,
    B2B_PACKS,
    get_plan_by_id,
    SUPPORTED_CURRENCIES,
    resolve_currency_for_request,
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
from core.analysis.mutual_funds_engine import (
    evaluate_mutual_fund_comprehensive,
    evaluate_dual_sleeve_lookthrough,
    calculate_portfolio_overlap,
    calculate_active_share,
    calculate_fee_drag,
)
from core.analysis.fund_overlap_auditor import (
    audit_single_fund_daily,
    compute_fund_forensic_lookthrough,
    calculate_deep_dive_credit_cost,
)
from core.config import get_secret
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.msme.scheduler import register_jobs

# ==============================================================================
# Shared Web Utilities & Re-Exports (Preserving 100% Backwards Compatibility)
# ==============================================================================
from web.common import (
    templates,
    canonical_for,
    json_response_with_cache,
    resolve_app_base_url,
    _validate_request_origin,
    _get_user_signing_key,
    _generate_user_session_token,
    _validate_user_session_token,
    _get_current_web_user,
    _get_admin_signing_key,
    _generate_admin_token,
    _validate_admin_token,
    _is_admin_authenticated,
    _generate_pending_2fa_token,
    _validate_pending_2fa_token,
    _build_local_qr_data_uri,
    _is_user_subscribed,
    _can_access_today_discovery,
    _is_ticker_unlocked_for_request,
    _deep_dive_unlocked_for_request,
    _asset_unlock_key,
    _asset_unlocked_for_request,
    _unlock_asset_deep_dive,
    _pdf_account_ref,
    PDF_LOCKED_NOTICE,
    ADMIN_COOKIE_NAME,
    ADMIN_2FA_PENDING_COOKIE,
    USER_SESSION_COOKIE,
    ALLOWED_ORIGIN_HOSTS,
)


# ==============================================================================
# Background Autonomous Schedulers
# ==============================================================================
async def run_daily_discovery_scheduler():
    """
    Automated background BSE surveillance and screening scheduler:
    Initiates automatic crawling & screening of BSE listed companies at 09:00 AM IST daily.
    """
    logger.info("🌅 [Discovery Scheduler] Background BSE surveillance crawler initiated.")
    try:
        now = datetime.now(IST)
        today_str = now.strftime("%Y-%m-%d")
        from core.db.discovery import get_active_discovery_reel
        from scripts.run_discovery_worker import run_discovery_pipeline

        loop = asyncio.get_running_loop()
        if now.hour >= 9:
            active_today = [x for x in get_active_discovery_reel(today_str, exclude_tests=True, allow_fallback=False)]
            if not active_today:
                logger.info(f"🌅 [Discovery Scheduler] Missing 9:00 AM edition for today ({today_str}). Triggering catch-up screening...")
                await loop.run_in_executor(None, run_discovery_pipeline, 12, today_str, False, False)
                logger.info(f"🌅 [Discovery Scheduler] Catch-up 9:00 AM edition for {today_str} published.")
        else:
            active_existing = [x for x in get_active_discovery_reel(exclude_tests=True, allow_fallback=True)]
            if not active_existing:
                yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
                logger.info(f"🌅 [Discovery Scheduler] No active historical editions found. Bootstrapping baseline edition ({yesterday_str})...")
                await loop.run_in_executor(None, run_discovery_pipeline, 12, yesterday_str, False, False)
    except Exception as boot_err:
        logger.warning(f"🌅 [Discovery Scheduler] Catch-up check notice: {boot_err}")

    last_run_date = None
    try:
        now = datetime.now(IST)
        today_str = now.strftime("%Y-%m-%d")
        if get_active_discovery_reel(today_str, exclude_tests=True, allow_fallback=False):
            last_run_date = today_str
    except Exception as e:
        logger.debug(f"[Discovery Scheduler] Initial reel check notice: {e}")

    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.now(IST)
            today_str = now.strftime("%Y-%m-%d")
            if now.hour >= 9 and last_run_date != today_str:
                from core.db.discovery import get_active_discovery_reel
                active_today = get_active_discovery_reel(today_str, exclude_tests=True, allow_fallback=False)
                if not active_today:
                    logger.info(f"🌅 [Discovery Scheduler] 09:00 AM IST trigger reached for {today_str}. Running discovery pipeline...")
                    from scripts.run_discovery_worker import run_discovery_pipeline
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, run_discovery_pipeline, 12, today_str, False, False)
                    logger.info(f"🌅 [Discovery Scheduler] Automated 9:00 AM BSE discovery edition published for {today_str}.")
                last_run_date = today_str
        except asyncio.CancelledError:
            logger.info("🌅 [Discovery Scheduler] Background scheduler cancelled.")
            break
        except Exception as e:
            logger.error(f"🌅 [Discovery Scheduler] Error in daily discovery scheduler: {e}")
            await asyncio.sleep(60)


async def run_daily_amfi_scheduler():
    """Automated background AMFI NAV synchronizer (runs daily at 23:15 IST)."""
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
    """Automated background Mutual Fund Forensic Auditor (runs daily at 23:30 IST)."""
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
            from core.analysis.fund_overlap_auditor import audit_single_fund_daily
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
    """Automated background Project Auditor (runs nightly at 03:00 IST)."""
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


async def warmup_task():
    """Primes local database connections and cache pools."""
    if os.environ.get("TESTING") == "1" or "pytest" in sys.modules:
        logger.info("🧪 Test environment detected: skipping live network warm-up task.")
        return
    logger.info("🚀 Starting warm‑up task: preloading local database connections...")
    try:
        init_db()
        logger.info("🚀 Warm‑up task completed: DB connection and schema caches primed.")
    except Exception as e:
        logger.warning(f"Warm‑up task warning: {e}")


# ==============================================================================
# Application Lifespan & Initialization
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    env = (os.environ.get("ENVIRONMENT") or "").strip().lower()
    is_render = (os.environ.get("RENDER") or "").strip().lower() in ["true", "1"]
    if env == "production" or is_render:
        secret_key = (os.environ.get("SECRET_KEY") or get_secret("SECRET_KEY") or "").strip()
        if not secret_key or len(secret_key) < 32 or secret_key == "stock_research_user_session_salt_2026":
            raise RuntimeError(
                "CRITICAL PRODUCTION BOOT FAILURE: SECRET_KEY is missing, insecure, or shorter than 32 characters. "
                "Declare a high-entropy SECRET_KEY (minimum 32 characters) in production environment variables."
            )
        admin_key = (os.environ.get("ADMIN_API_KEY") or get_secret("ADMIN_API_KEY") or "").strip()
        admin_pwd = (os.environ.get("ADMIN_PASSWORD") or get_secret("ADMIN_PASSWORD") or "").strip()
        if not admin_key or not admin_pwd:
            logger.warning("Production Notice: ADMIN_API_KEY or ADMIN_PASSWORD should be declared in production.")

    init_db()

    try:
        from core.db.mutual_funds import get_active_mutual_funds, seed_default_mutual_funds
        if not get_active_mutual_funds():
            seed_default_mutual_funds()
    except Exception as e:
        logger.warning(f"Initial mutual fund bootstrap seed skipped: {e}")

    try:
        from core.db.debt import seed_default_debt_securities
        seed_default_debt_securities()
    except Exception as e:
        logger.warning(f"Initial debt bootstrap seed skipped: {e}")

    try:
        from core.msme.seed import get_active_msme_firms_count, seed_default_msme_firms
        if get_active_msme_firms_count() == 0:
            seed_default_msme_firms()
    except Exception as e:
        logger.warning(f"Initial MSME bootstrap seed skipped: {e}")

    is_testing = os.environ.get("TESTING") == "1" or "pytest" in sys.modules
    scheduler = None
    discovery_task = None
    amfi_task = None
    fund_audit_task = None
    audit_task = None
    bse_task = None

    if not is_testing:
        asyncio.create_task(warmup_task())
        scheduler = AsyncIOScheduler()
        register_jobs(scheduler)
        scheduler.start()
        discovery_task = asyncio.create_task(run_daily_discovery_scheduler())
        amfi_task = asyncio.create_task(run_daily_amfi_scheduler())
        fund_audit_task = asyncio.create_task(run_daily_fund_audit_scheduler())
        audit_task = asyncio.create_task(run_daily_project_audit_scheduler())
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
    title="Moatnomics",
    description="Dual-Mandate Fundamental Research Platform: Audit the Asset, Protect the Allocator",
    version="2.0.0",
    lifespan=lifespan
)

# Static files mounting
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Middleware setup
if BrotliMiddleware is not None:
    app.add_middleware(BrotliMiddleware, minimum_size=500)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


class CrawlerLogMiddleware(BaseHTTPMiddleware):
    """Logs fetches by known search/AI crawlers (they never run the browser telemetry script)."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            path = request.url.path
            if request.method in ("GET", "HEAD") and not path.startswith(("/static", "/api", "/admin")):
                from telemetry import classify_bot
                bot = classify_bot(request.headers.get("user-agent", ""))
                if bot:
                    from core.db.telemetry import record_crawler_hit
                    asyncio.get_running_loop().run_in_executor(
                        None, record_crawler_hit, bot[0], bot[1], path, response.status_code
                    )
        except Exception as crawl_err:
            logger.debug("Crawler log notice: %s", crawl_err)
        return response

app.add_middleware(CrawlerLogMiddleware)


# ==============================================================================
# Modular Routers Integration
# ==============================================================================
from core.msme.router import router as msme_router
app.include_router(msme_router, prefix="/api/msme")

from web.routers.auth_billing import router as auth_billing_router
from web.routers.dossier import router as dossier_router
from web.routers.markets import router as markets_router
from web.routers.admin import router as admin_router

app.include_router(auth_billing_router)
app.include_router(dossier_router)
app.include_router(markets_router)
app.include_router(admin_router)


# ==============================================================================
# SSR HTML Page Routes
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    """Public home & landing page with live stock search, discovery reel, and featured dossiers."""
    code = request.query_params.get("code")
    if code:
        return RedirectResponse(url=f"/auth/callback?code={urllib.parse.quote(code)}", status_code=303)

    try:
        archives = get_archived_reports_sync()
    except Exception as e:
        logger.error(f"Error fetching archives: {e}")
        archives = []

    try:
        all_equities = get_all_equities_directory_sync()
    except Exception as e:
        logger.error(f"Error fetching all equities for home: {e}")
        all_equities = []

    user = _get_current_web_user(request)
    can_access_today = _can_access_today_discovery(request, user)
    now = datetime.now(IST)
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    is_past_9am = now.hour >= 9

    target_ed = today_str if (can_access_today and is_past_9am) else yesterday_str
    try:
        discovery_stocks = get_active_discovery_reel(edition_date=target_ed, allow_fallback=True)
    except Exception as e:
        logger.error(f"Error fetching discovery reel for home: {e}")
        discovery_stocks = []

    featured = archives[:9] if archives else []
    total_count = len(all_equities) if all_equities else (len(archives) if archives else 143)
    curr_ed = discovery_stocks[0]["edition_date"] if discovery_stocks else target_ed
    is_yesterday = (curr_ed == yesterday_str) or (not is_past_9am) or (curr_ed < today_str)

    sector_counts = collections.Counter(e.get("sector_slug", "DIVERSIFIED") for e in all_equities)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "active_page": "home",
            "featured_reports": featured,
            "all_equities": all_equities,
            "total_equities": total_count,
            "sector_options": SECTOR_TAXONOMY,
            "sector_counts": dict(sector_counts),
            "discovery_stocks": discovery_stocks,
            "total_reports": total_count,
            "pricing_packs": PRICING_PACKS,
            "is_yesterday_edition": is_yesterday,
            "can_access_today": can_access_today,
            "today_date": today_str,
            "yesterday_date": yesterday_str,
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
    user = _get_current_web_user(request)
    can_access_today = _can_access_today_discovery(request, user)

    now = datetime.now(IST)
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    is_past_9am = now.hour >= 9

    # Calculate countdown until next 09:00 AM IST drop
    target_9am = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= target_9am:
        target_9am += timedelta(days=1)
    seconds_until_9am = int((target_9am - now).total_seconds())
    hours_until_9am = seconds_until_9am // 3600
    mins_until_9am = (seconds_until_9am % 3600) // 60

    try:
        available_editions = get_available_discovery_editions(exclude_tests=True)
    except Exception as e:
        logger.error(f"Error fetching discovery editions: {e}")
        available_editions = []

    if edition:
        selected_edition = edition
    else:
        # Default edition selection:
        # If user is subscribed and today's edition exists past 9:00 AM, show today's edition!
        if can_access_today and is_past_9am and today_str in available_editions:
            selected_edition = today_str
        elif today_str in available_editions and is_past_9am:
            # Free user visiting /discovery: default to yesterday's archive so they can read in full with yesterday's badge, while seeing the top banner pointing to today's live Pro edition!
            selected_edition = yesterday_str if yesterday_str in available_editions else (available_editions[1] if len(available_editions) > 1 else today_str)
        else:
            # Before 9:00 AM or today not yet in DB: show yesterday's edition
            selected_edition = yesterday_str if yesterday_str in available_editions else (available_editions[0] if available_editions else today_str)

    try:
        discovery_stocks = get_active_discovery_reel(edition_date=selected_edition, allow_fallback=True)
    except Exception as e:
        logger.error(f"Error fetching discovery reel: {e}")
        discovery_stocks = []

    actual_edition = discovery_stocks[0]["edition_date"] if discovery_stocks else selected_edition
    is_today_edition = (actual_edition == today_str and is_past_9am)
    is_yesterday_edition = (actual_edition == yesterday_str) or (not is_past_9am) or (actual_edition < today_str)
    is_locked_for_user = (is_today_edition and not can_access_today)

    return templates.TemplateResponse(
        request=request,
        name="discovery.html",
        context={
            "active_page": "discovery",
            "discovery_stocks": discovery_stocks,
            "available_editions": available_editions,
            "current_edition": actual_edition,
            "today_date": today_str,
            "yesterday_date": yesterday_str,
            "is_today_edition": is_today_edition,
            "is_yesterday_edition": is_yesterday_edition,
            "is_locked_for_user": is_locked_for_user,
            "can_access_today": can_access_today,
            "is_past_9am": is_past_9am,
            "seconds_until_9am": seconds_until_9am,
            "hours_until_9am": hours_until_9am,
            "mins_until_9am": mins_until_9am,
        }
    )


@app.get("/pricing", response_class=HTMLResponse)
def pricing_page(request: Request):
    """Public pricing and checkout page displaying single-pass, credit packs, and Pro memberships."""
    detected_currency = resolve_currency_for_request(request)
    return templates.TemplateResponse(
        request=request,
        name="pricing.html",
        context={
            "active_page": "pricing",
            "pricing_packs": PRICING_PACKS,
            "b2b_packs": B2B_PACKS,
            "supported_currencies": SUPPORTED_CURRENCIES,
            "detected_currency": detected_currency,
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
        scrip = resolve_bse_scrip_code(canonical) or "N/A"
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
                contagion_alert = evaluate_equity_cross_contagion(linked_debt[0], fetch_live_fundamentals=False)
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

    # Determine institutional deep-dive unlock status (Pillars 03 & 05 + Thesis Drift)
    web_user = _get_current_web_user(request)
    is_deep_dive_unlocked = False
    if _is_admin_authenticated(request):
        is_deep_dive_unlocked = True
    elif os.environ.get("TESTING") == "1" and (request.headers.get("x-unlock-preview") == "1" or request.query_params.get("unlocked") == "1"):
        is_deep_dive_unlocked = True
    elif web_user:
        is_deep_dive_unlocked = is_ticker_unlocked_for_user(web_user.get("id", ""), canonical)

    # Convert report markdown into semantic HTML
    html_content = markdown.markdown(
        prose_md,
        extensions=["tables", "fenced_code", "nl2br"]
    )
    scrip_code = rep.get("scrip_code") or resolve_bse_scrip_code(canonical) or ""
    html_content = wrap_html_with_collapsible_pillars(
        html_content,
        scrip_code=scrip_code,
        is_deep_dive_unlocked=is_deep_dive_unlocked,
        ticker=canonical
    )

    mcap = rep.get("baseline_mcap")
    # format_inr() already prefixes the rupee symbol.
    mcap_formatted = format_inr(mcap) if mcap else "N/A"

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
    except Exception as fund_err:
        logger.debug("Fundamentals lookup notice for %s: %s", canonical, fund_err)

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

    # Phase 1 Upgrade: Institutional Equity Intelligence (Sector, Flow, Forensics, Valuation Radar, Bull/Bear)
    equity_intel = None
    try:
        from core.analysis.equity_dossier import compile_equity_dossier
        equity_intel = compile_equity_dossier(
            ticker=canonical,
            fundamentals=fund,
            company_name=rep.get("short_name", canonical),
            industry_str=rep.get("industry", ""),
        )
    except Exception as e:
        logger.debug(f"Equity dossier intelligence compilation notice for {canonical}: {e}")

    return templates.TemplateResponse(
        request=request,
        name="dossier.html",
        context={
            "ticker": clean_t,
            "short_name": rep.get("short_name", clean_t),
            "current_price": str(rep.get("baseline_price") or "N/A"),
            "pe_ratio": str(rep.get("baseline_pe") or "N/A"),
            "market_cap_str": mcap_formatted,
            "scrip_code": scrip_code if str(scrip_code or "").strip().isdigit() else "N/A",
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
            "is_deep_dive_unlocked": is_deep_dive_unlocked,
            "web_user": web_user,
            "equity_intel": equity_intel,
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

    for f_key in ["fund_a", "fund_b"]:
        m = comp_data.get(f_key, {}).get("market_cap")
        if m:
            comp_data[f_key]["market_cap_str"] = format_inr(m)

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


@app.get("/debt", response_class=HTMLResponse)
def debt_directory_page(
    request: Request,
    seniority: Optional[str] = None,
    instrument_type: Optional[str] = None,
    min_rating: Optional[str] = None,
    q: Optional[str] = None
):
    """Corporate Debt, NCDs, and SDIs under the SEBI ₹10,000 face value framework."""
    init_db()
    query_str = (q or "").strip()
    if query_str:
        from core.search.product_search import search_debt_securities
        raw_matches = search_debt_securities(query_str, limit=50)
        securities = []
        for m in raw_matches:
            sec = get_debt_security_by_isin(m["identifier"])
            if sec:
                securities.append(sec)
    else:
        securities = get_active_debt_securities(
            seniority=seniority,
            instrument_type=instrument_type,
            min_rating=min_rating
        )

    recent_actions = get_recent_rating_actions(limit=8)
    valid_ytms = [
        float(s["ytm_pct"])
        for s in securities
        if s.get("ytm_pct") is not None and float(s["ytm_pct"]) > 0
    ]
    avg_ytm = f"{statistics.mean(valid_ytms):.2f}" if valid_ytms else "9.85"
    return templates.TemplateResponse(
        request=request,
        name="debt_directory.html",
        context={
            "active_page": "debt",
            "securities": securities,
            "avg_ytm": avg_ytm,
            "recent_actions": recent_actions,
            "current_seniority": seniority,
            "current_type": instrument_type,
            "current_rating": min_rating,
            "query": query_str,
        }
    )


@app.get("/debt/{isin}", response_class=HTMLResponse)
def debt_dossier_page(request: Request, isin: str):
    """5-Pillar Credit & Solvency Dossier for a corporate bond or SDI."""
    init_db()
    clean_isin = isin.strip().upper()
    sec = get_debt_security_by_isin(clean_isin)
    if not sec:
        raise HTTPException(status_code=404, detail=f"Corporate debt security with ISIN '{clean_isin}' not found.")

    rating_history = get_rating_history(clean_isin)
    posture = evaluate_5_pillar_credit_posture(sec, rating_history=rating_history)
    is_deep_dive_unlocked = _asset_unlocked_for_request(request, "DEBT", clean_isin)

    return templates.TemplateResponse(
        request=request,
        name="debt_dossier.html",
        context={
            "active_page": "debt",
            "security": sec,
            "posture": posture,
            "rating_history": rating_history,
            "is_deep_dive_unlocked": is_deep_dive_unlocked,
            "unlock_kind": "DEBT",
            "unlock_id": clean_isin,
        }
    )


@app.get("/stocks", response_class=RedirectResponse)
def stocks_alias_redirect(request: Request):
    """Permanent canonical redirect from /stocks to /equities preserving query parameters."""
    target_url = "/equities"
    if request.url.query:
        target_url = f"/equities?{request.url.query}"
    return RedirectResponse(url=target_url, status_code=301)


@app.get("/reports", response_class=RedirectResponse)
@app.get("/reports/", response_class=RedirectResponse)
def reports_alias_redirect(request: Request):
    """Permanent canonical redirect from /reports to /equities preserving query parameters."""
    target_url = "/equities"
    if request.url.query:
        target_url = f"/equities?{request.url.query}"
    return RedirectResponse(url=target_url, status_code=301)


@app.get("/equities", response_class=HTMLResponse)
def equities_directory_page(
    request: Request,
    q: Optional[str] = None,
    sector: Optional[str] = None,
    market_cap: Optional[str] = None,
    sort: Optional[str] = "mcap_desc",
):
    """Institutional Equities Directory & Screener."""
    init_db()
    all_equities = get_all_equities_directory_sync()
    total_equities = len(all_equities)

    total_mcap_cr = sum(e.get("market_cap_cr", 0.0) for e in all_equities)
    total_mcap_lakh_cr = total_mcap_cr / 100000.0 if total_mcap_cr else 210.0

    roce_vals = [e["roce"] for e in all_equities if e.get("roce") is not None]
    median_roce = round(statistics.median(roce_vals), 1) if roce_vals else 18.2

    pe_vals = [e["pe_float"] for e in all_equities if e.get("pe_float") is not None and e["pe_float"] > 0]
    median_pe = round(statistics.median(pe_vals), 1) if pe_vals else 24.5

    sector_counts = collections.Counter(e.get("sector_slug", "DIVERSIFIED") for e in all_equities)

    featured_equity = None
    for cand_ticker in ["INFY", "TCS", "RELIANCE", "HDFCBANK", "LT"]:
        cand = next((e for e in all_equities if e["ticker"] == cand_ticker), None)
        if cand:
            featured_equity = cand
            break
    if not featured_equity and all_equities:
        featured_equity = all_equities[0]

    filtered = list(all_equities)
    query_str = (q or "").strip()
    if query_str:
        q_lower = query_str.lower()
        filtered = [
            e for e in filtered
            if q_lower in e["ticker"].lower()
            or q_lower in e.get("name", "").lower()
            or q_lower in e.get("company_name", "").lower()
            or q_lower in e.get("industry", "").lower()
            or q_lower in e.get("sector", "").lower()
        ]

    sec_filter = (sector or "").strip().upper()
    if sec_filter:
        filtered = [e for e in filtered if e.get("sector_slug", "").upper() == sec_filter]

    tier_filter = (market_cap or "").strip().upper()
    if tier_filter in ["MEGA", "LARGE", "MID", "SMALL"]:
        filtered = [e for e in filtered if e.get("market_cap_tier_slug", "").upper() == tier_filter]

    sort_key = (sort or "mcap_desc").strip().lower()
    if sort_key == "mcap_asc":
        filtered.sort(key=lambda x: (x.get("market_cap_cr", 0.0) <= 0, x.get("market_cap_cr", 0.0)))
    elif sort_key == "roce_desc":
        filtered.sort(key=lambda x: (x.get("roce") is not None, x.get("roce") or -999.0), reverse=True)
    elif sort_key == "pe_asc":
        filtered.sort(key=lambda x: (x.get("pe_float") is not None and x.get("pe_float") > 0, -(x.get("pe_float") or 999999.0)), reverse=True)
    elif sort_key == "name_asc":
        filtered.sort(key=lambda x: x.get("name", "").lower())
    elif sort_key == "rev_desc":
        filtered.sort(key=lambda x: x.get("revision_count", 1), reverse=True)
    else:
        filtered.sort(key=lambda x: x.get("market_cap_cr", 0.0), reverse=True)

    return templates.TemplateResponse(
        request=request,
        name="equities_directory.html",
        context={
            "active_page": "equities",
            "equities": filtered,
            "total_equities": total_equities,
            "total_mcap_lakh_cr": total_mcap_lakh_cr,
            "median_roce": median_roce,
            "median_pe": median_pe,
            "featured_equity": featured_equity,
            "sector_options": SECTOR_TAXONOMY,
            "sector_counts": dict(sector_counts),
            "current_sector": sec_filter or None,
            "current_tier": tier_filter or None,
            "current_sort": sort_key,
            "query": query_str,
        }
    )


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

    is_deep_dive_unlocked = _asset_unlocked_for_request(request, "FUND", clean_code)
    forensic_locked = False
    if forensic_dossier and not is_deep_dive_unlocked:
        forensic_dossier = None
        forensic_locked = True

    forensic_dossier_html = ""
    if forensic_dossier and forensic_dossier.get("dossier_text"):
        forensic_dossier_html = wrap_fund_dossier_with_collapsible_dimensions(
            forensic_dossier.get("dossier_text", ""),
            scheme_code=clean_code,
            scheme_name=dossier.get("scheme", {}).get("scheme_name", "")
        )

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
            "forensic_dossier_html": forensic_dossier_html,
            "credit_quote": credit_quote,
            "is_deep_dive_unlocked": is_deep_dive_unlocked,
            "forensic_locked": forensic_locked,
            "unlock_kind": "FUND",
            "unlock_id": clean_code,
        }
    )


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


@app.get("/etfs", response_class=HTMLResponse)
def etfs_page(
    request: Request,
    category: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None)
):
    """National ETF Matrix & Tracking Error Surveillance page."""
    from core.analysis.etf_matrix_engine import evaluate_etf_matrix
    init_db()
    matrix_data = evaluate_etf_matrix(category=category, query=q, sort_by=sort_by)
    return templates.TemplateResponse(
        request=request,
        name="etf_matrix.html",
        context={
            "active_page": "etfs",
            "current_category": category or "ALL",
            "current_query": q or "",
            "current_sort": sort_by or "aum_desc",
            "data": matrix_data
        }
    )


@app.get("/etfs/{symbol}", response_class=HTMLResponse)
def etf_dossier_page(request: Request, symbol: str):
    """Institutional ETF Dossier with live premium/discount tracking and arbitrage surveillance."""
    from core.analysis.etf_matrix_engine import get_etf_detail
    init_db()
    clean_sym = symbol.strip().upper()
    detail = get_etf_detail(clean_sym)
    if not detail:
        raise HTTPException(status_code=404, detail=f"ETF '{clean_sym}' not found in master matrix.")

    return templates.TemplateResponse(
        request=request,
        name="etf_dossier.html",
        context={
            "active_page": "etfs",
            "symbol": clean_sym,
            "data": detail,
            "etf": detail["etf"],
            "amc_issuer": detail["amc_issuer"],
            "category_label": detail["category_label"],
            "aum_formatted": detail["aum_formatted"],
            "arbitrage": detail["arbitrage_analysis"],
            "replication": detail["replication_audit"],
            "liquidity": detail["liquidity_audit"],
            "inversion_risks": detail["inversion_risks"],
            "peers": detail["peers"],
            "forensic_notes": detail["forensic_notes"]
        }
    )


@app.get("/calculator/tax", response_class=HTMLResponse)
def tax_calculator_page(
    request: Request,
    tax_slab: float = Query(30.0),
    inflation: float = Query(5.0)
):
    """Net Real Post-Tax Return & Purchasing Power Calculator page."""
    from core.analysis.net_real_tax_calculator import compare_asset_classes_post_tax
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


@app.get("/msme", response_class=HTMLResponse)
def msme_directory_page(
    request: Request,
    sector: Optional[str] = None,
    state: Optional[str] = None,
    tier: Optional[str] = None,
    q: Optional[str] = None
):
    """Unlisted MSME & Emerging SME Directory under the MSMED Act 2020."""
    init_db()
    from core.msme.seed import get_active_msme_firms_count, seed_default_msme_firms
    if get_active_msme_firms_count() == 0:
        seed_default_msme_firms()

    from core.msme.utils import build_search_query, classify_msme_tier
    from core.db.connection import get_db_connection, get_supabase_url
    conn = get_db_connection()
    cur = conn.cursor()
    use_pg = bool(get_supabase_url())
    placeholder = "%s" if use_pg else "?"

    where, values = build_search_query(
        {"q": q, "sector": sector, "state": state, "tier": tier},
        placeholder=placeholder
    )

    sql = f"""
        SELECT uin, name, sector_name, city, state, annual_turnover,
               employee_count, registration_date, source
        FROM msme_firms
        WHERE {where}
        ORDER BY annual_turnover DESC, name ASC
        LIMIT 100
    """
    cur.execute(sql, values)
    rows = cur.fetchall()

    cur.execute("SELECT COUNT(*), COALESCE(SUM(annual_turnover), 0), COUNT(DISTINCT state) FROM msme_firms")
    stat_row = cur.fetchone()
    total_firms = stat_row[0] if stat_row else 0
    total_turnover = round(float(stat_row[1]), 1) if stat_row and stat_row[1] else 0.0
    states_count = stat_row[2] if stat_row else 0

    cur.execute("SELECT COUNT(*) FROM msme_firms WHERE annual_turnover < 5.0 OR annual_turnover IS NULL")
    micro_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM msme_firms WHERE annual_turnover >= 5.0 AND annual_turnover < 50.0")
    small_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM msme_firms WHERE annual_turnover >= 50.0")
    medium_count = cur.fetchone()[0]

    cur.execute("SELECT DISTINCT sector_name FROM msme_firms WHERE sector_name IS NOT NULL AND sector_name != '' ORDER BY sector_name ASC")
    sectors = [r[0] for r in cur.fetchall()]

    cur.execute("SELECT DISTINCT state FROM msme_firms WHERE state IS NOT NULL AND state != '' ORDER BY state ASC")
    states = [r[0] for r in cur.fetchall()]

    cur.close()
    conn.close()

    firms = []
    for r in rows:
        turnover = float(r[5]) if r[5] is not None else None
        firms.append({
            "uin": r[0],
            "name": r[1],
            "sector": r[2],
            "city": r[3],
            "state": r[4],
            "annual_turnover": turnover,
            "employee_count": int(r[6]) if r[6] is not None else None,
            "registration_date": r[7],
            "source": r[8],
            "tier": classify_msme_tier(turnover)
        })

    return templates.TemplateResponse(
        request=request,
        name="msme_directory.html",
        context={
            "active_page": "msme",
            "firms": firms,
            "total_firms": total_firms,
            "total_turnover": total_turnover,
            "states_count": states_count,
            "micro_count": micro_count,
            "small_count": small_count,
            "medium_count": medium_count,
            "sectors": sectors,
            "states": states,
            "current_sector": sector,
            "current_state": state,
            "current_tier": tier,
            "current_q": q or ""
        }
    )


@app.get("/msme/{uin}", response_class=HTMLResponse)
def msme_dossier_page(request: Request, uin: str):
    """Institutional 4-Pillar Forensic Dossier for an Unlisted MSME / Emerging SME."""
    init_db()
    from core.msme.router import get_msme_detail
    dossier = get_msme_detail(uin)
    if not dossier:
        raise HTTPException(status_code=404, detail=f"MSME enterprise with UIN '{uin}' not found")

    return templates.TemplateResponse(
        request=request,
        name="msme_dossier.html",
        context={
            "request": request,
            "active_page": "msme",
            "dossier": dossier
        }
    )


@app.get("/reits", response_class=HTMLResponse)
def reits_page(request: Request, structure: Optional[str] = Query(None)):
    """SEBI SM REITs, Mainboard REITs, InvITs & SGB Secondary Parity directory."""
    from core.analysis.sm_reit_invit_engine import audit_reit_portfolio
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


@app.get("/reits/{symbol}", response_class=HTMLResponse)
def reit_dossier_page(request: Request, symbol: str):
    """Institutional REIT & InvIT Dossier with Sec 115UA tax waterfall and NDCF payout purity."""
    from core.analysis.sm_reit_invit_engine import get_reit_detail
    init_db()
    clean_sym = symbol.strip().upper()
    detail = get_reit_detail(clean_sym)
    if not detail:
        raise HTTPException(status_code=404, detail=f"REIT/InvIT '{clean_sym}' not found in master registry.")

    canonical_sym = detail["reit"]["symbol"]
    is_deep_dive_unlocked = _asset_unlocked_for_request(request, "REIT", canonical_sym)

    return templates.TemplateResponse(
        request=request,
        name="reit_dossier.html",
        context={
            "active_page": "reits",
            "symbol": canonical_sym,
            "data": detail,
            "reit": detail["reit"],
            "tax_waterfall": detail["tax_waterfall"],
            "ndcf_audit": detail["ndcf_audit"],
            "portfolio_audit": detail["portfolio_audit"],
            "inversion_risks": detail["inversion_risks"],
            "peers": detail["peers"],
            "forensic_notes": detail["forensic_notes"],
            "is_deep_dive_unlocked": is_deep_dive_unlocked
        }
    )


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


@app.get("/safety-radar", response_class=HTMLResponse)
def safety_radar_page(request: Request, category: Optional[str] = Query(None)):
    """Retail Safety & Shadow-Banking Diagnostic Radar page."""
    from core.analysis.retail_safety_radar import audit_alternative_yield_radar
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

    background_tasks.add_task(dispatch_support_ticket_alert, res)

    from core.db.telemetry import record_usage_event
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


@app.get("/health")
@app.get("/healthz")
async def healthz():
    """Health check endpoint with caching (short‑lived)."""
    data = {"status": "healthy", "service": "Moatnomics Web Server", "timestamp": datetime.now(IST).isoformat()}
    return json_response_with_cache(data, max_age=30)


@app.get("/sitemap.xml", response_class=Response)
async def sitemap_xml():
    """Generates automated XML sitemap for Google/Perplexity/Bing search crawlers."""
    archives = get_archived_reports_sync()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    base_url = (os.environ.get("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <url><loc>{base_url}/</loc><lastmod>{now_iso}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>',
        f'  <url><loc>{base_url}/discovery</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{base_url}/opportunities</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{base_url}/search</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{base_url}/equities</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{base_url}/compare</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/debt</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/funds</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/sovereign</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/etfs</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/calculator/tax</loc><lastmod>{now_iso}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/reits</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/safety-radar</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/msme</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
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
            raw_ts = a.get("raw_timestamp")
            if raw_ts:
                try:
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
                f'  <url><loc>{base_url}/dossier/{t}</loc><lastmod>{lastmod_date}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>'
            )

    try:
        from core.db.sovereign import get_etf_matrix
        top_etfs = get_etf_matrix(limit=30)
        for etf in top_etfs:
            sym = etf.get("symbol")
            if sym:
                xml_lines.append(
                    f'  <url><loc>{base_url}/etfs/{sym}</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>'
                )
    except Exception as etf_sitemap_err:
        logger.debug(f"Sitemap ETF append notice: {etf_sitemap_err}")

    try:
        from core.db.reits import get_all_reits_and_invits
        all_reits = get_all_reits_and_invits()
        for r in all_reits:
            sym = r.get("symbol")
            if sym:
                xml_lines.append(
                    f'  <url><loc>{base_url}/reits/{sym}</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>'
                )
    except Exception as reit_sitemap_err:
        logger.debug(f"Sitemap REIT append notice: {reit_sitemap_err}")

    try:
        from core.db.debt import get_active_debt_securities
        all_debt = get_active_debt_securities(limit=150)
        for d in all_debt:
            isin_val = d.get("isin")
            if isin_val:
                xml_lines.append(
                    f'  <url><loc>{base_url}/debt/{isin_val}</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>'
                )
    except Exception as debt_sitemap_err:
        logger.debug(f"Sitemap Debt append notice: {debt_sitemap_err}")

    try:
        from core.msme.seed import get_active_msme_firms_count
        from core.db.connection import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT uin FROM msme_firms LIMIT 100")
        for (m_uin,) in cur.fetchall():
            xml_lines.append(
                f'  <url><loc>{base_url}/msme/{m_uin}</loc><lastmod>{now_iso}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>'
            )
        cur.close()
        conn.close()
    except Exception as msme_sitemap_err:
        logger.debug(f"Sitemap MSME append notice: {msme_sitemap_err}")

    xml_lines.append('</urlset>')
    return Response(content="\n".join(xml_lines), media_type="application/xml")


@app.get("/robots.txt", response_class=Response)
async def robots_txt():
    """Provides search engine crawler directives and XML sitemap index pointer."""
    base_url = (os.environ.get("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /admin\n\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    return Response(content=content, media_type="text/plain")
