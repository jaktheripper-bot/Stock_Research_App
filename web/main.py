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
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Form, Header, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from brotli_asgi import BrotliMiddleware
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
from ui.formatters import format_inr
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
)
from core.analysis.mutual_fund_engine import (
    evaluate_mutual_fund_comprehensive,
    evaluate_dual_sleeve_lookthrough,
    calculate_portfolio_overlap,
    calculate_active_share,
    calculate_fee_drag,
)

logger = logging.getLogger("equity_research.web")

from contextlib import asynccontextmanager

async def run_daily_discovery_scheduler():
    """
    Automated background BSE surveillance and screening scheduler:
    Initiates automatic crawling & screening of BSE listed companies at 09:00 AM IST daily.
    """
    logger.info("🌅 [Discovery Scheduler] Background BSE surveillance crawler initiated.")
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

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.msme.scheduler import register_jobs

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB migrations on startup
    # Include MSME router
    from core.msme.router import router as msme_router
    app.include_router(msme_router, prefix="/api/msme")
    init_db()

    is_testing = os.environ.get("TESTING") == "1" or "pytest" in sys.modules
    scheduler = None
    discovery_task = None

    if not is_testing:
        # Warm‑up task to prime async resources
        await warmup_task()
        # Start APScheduler for MSME background jobs
        scheduler = AsyncIOScheduler()
        register_jobs(scheduler)
        scheduler.start()
        # Start automated daily discovery background scheduler
        discovery_task = asyncio.create_task(run_daily_discovery_scheduler())

    try:
        yield
    finally:
        if discovery_task:
            discovery_task.cancel()
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
    logger.info("🚀 Starting warm‑up task: preloading resources...")
    try:
        # Simple warm‑up using compare_two_companies to load HTTP client pool and DB connections
        await compare_two_companies("INFY", "TCS")
        logger.info("🚀 Warm‑up task completed: compare_two_companies preloaded.")
    except Exception as e:
        logger.exception(f"Warm‑up task failed: {e}")
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


@app.get("/discovery", response_class=HTMLResponse)
def discovery_page(request: Request, edition: Optional[str] = Query(None)):
    """The Morning Discovery Reel: nightly screening of under-the-radar equities."""
    try:
        discovery_stocks = get_active_discovery_reel(edition_date=edition)
        available_editions = get_available_discovery_editions()
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


@app.get("/search")
async def search_redirect(q: str = ""):
    """Redirects search queries to the canonical ticker dossier URL."""
    clean_q = clean_ticker(q)
    if not clean_q:
        return RedirectResponse(url="/")
    canonical = resolve_canonical_symbol(clean_q) or clean_q
    return RedirectResponse(url=f"/dossier/{canonical}", status_code=302)


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
        return templates.TemplateResponse(
            request=request,
            name="dossier_pending.html",
            context={
                "display_ticker": canonical,
                "company_name": company_name,
                "scrip_code": scrip,
                "suggestions": suggestions,
                "active_page": "dossier"
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
    try:
        df_hist = get_historical_prices(canonical, period="6mo")
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
    if not securities:
        seed_default_debt_securities()
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
    if not secs:
        seed_default_debt_securities()
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


@app.get("/funds", response_class=HTMLResponse)
def fund_directory_page(
    request: Request,
    category: Optional[str] = None,
    broad_category: Optional[str] = None
):
    """Public Mutual Fund Look-Through directory & screener under SEBI disclosure norms."""
    init_db()
    schemes = get_active_mutual_funds(category=category, broad_category=broad_category)
    if not schemes:
        seed_default_mutual_funds()
        schemes = get_active_mutual_funds(category=category, broad_category=broad_category)

    total_aum = sum(s.get("aum_crores", 0.0) for s in schemes)
    drag_vals = [(s.get("ter_regular_pct", 1.5) - s.get("ter_direct_pct", 0.7)) * 100 for s in schemes]
    avg_drag_bps = round(sum(drag_vals) / len(drag_vals), 0) if drag_vals else 75

    return templates.TemplateResponse(
        request=request,
        name="fund_directory.html",
        context={
            "active_page": "funds",
            "schemes": schemes,
            "total_aum": total_aum,
            "avg_drag_bps": int(avg_drag_bps),
            "current_category": broad_category or category,
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
    if not all_funds:
        seed_default_mutual_funds()
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
    """Institutional 6-Pillar Mutual Fund Look-Through Dossier."""
    init_db()
    clean_code = scheme_code.strip().upper()
    scheme = get_mutual_fund_scheme(clean_code)
    if not scheme:
        seed_default_mutual_funds()
        scheme = get_mutual_fund_scheme(clean_code)

    if not scheme:
        raise HTTPException(status_code=404, detail=f"Mutual fund scheme with code '{clean_code}' not found.")

    dossier = evaluate_mutual_fund_comprehensive(clean_code)
    if not dossier:
        raise HTTPException(status_code=500, detail="Failed to generate mutual fund look-through dossier.")

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
        }
    )


@app.get("/api/funds/schemes")
def api_get_mutual_fund_schemes(
    category: Optional[str] = None,
    broad_category: Optional[str] = None
):
    """Public API: List all tracked mutual fund schemes with look-through health scores."""
    init_db()
    schemes = get_active_mutual_funds(category=category, broad_category=broad_category)
    if not schemes:
        seed_default_mutual_funds()
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
        seed_default_mutual_funds()
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
        seed_default_mutual_funds()
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

    if not h_a or not h_b:
        seed_default_mutual_funds()
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
    if not schemes:
        seed_default_mutual_funds()
        schemes = get_schemes_by_holding(clean_id)

    return json_response_with_cache({"status": "success", "identifier": clean_id, "count": len(schemes), "funds": schemes})


class PreMortemRequest(BaseModel):
    ticker: str
    failure_vector: str
    anti_thesis_notes: str
    user_id: Optional[str] = "guest_web_user"


@app.post("/api/premortem")
async def api_premortem(payload: PreMortemRequest):
    """Commits a Charlie Munger Pre-Mortem counter-thesis to the audit ledger."""
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


class TelemetryEventRequest(BaseModel):
    event_type: str
    ticker: Optional[str] = ""
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    session_id: Optional[str] = None
    referrer: Optional[str] = None
    landing_url: Optional[str] = None
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

    record_usage_event(
        event_type=payload.event_type,
        ticker=payload.ticker or "",
        details=payload.details or {},
        session_id=sess_id,
        traffic_source=traffic_source,
        referrer=clean_ref,
        country=country,
        device_type=client_env.get("device", "Desktop"),
        browser=client_env.get("browser", "Chrome"),
        os=client_env.get("os", "macOS"),
        user_id=payload.user_id,
        user_email=payload.user_email
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


class SignInRequest(BaseModel):
    email: str
    full_name: Optional[str] = None


@app.post("/api/auth/signin")
async def api_signin(payload: SignInRequest):
    """
    Direct user sign-in or auto-registration.
    Grants 2 welcome credits to new accounts and returns user profile.
    """
    clean_email = (payload.email or "").strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")

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
        details={"name": user.get("full_name"), "tier": user.get("subscription_tier")}
    )

    return json_response_with_cache({
        "success": True,
        "message": f"Welcome {user.get('full_name')}! You have received 2 free research credits.",
        "user": user
    })


class OrderRequest(BaseModel):
    plan_id: Optional[str] = None
    amount: Optional[int] = None       # amount in paise (minimum 100)
    currency: Optional[str] = "INR"
    receipt: Optional[str] = None
    user_id: Optional[str] = "guest_web_user"
    email: Optional[str] = "investor@example.com"


@app.post("/api/create-order")
async def api_create_order(payload: OrderRequest):
    """
    Creates an official Razorpay order or returns simulated checkout data.
    Validates amount >= 100 paise, handles 401 auth and 500 API errors.
    """
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
async def api_verify_payment(payload: VerifyPaymentRequest):
    """
    Cryptographically verifies the HMAC-SHA256 signature generated by Razorpay.
    Returns 400 for signature mismatch or missing fields, and credits user on match.
    """
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
async def api_download_pdf(ticker: str):
    """Generates and serves the official downloadable PDF report."""
    clean_t = clean_ticker(ticker)
    rep = get_report_by_ticker_sync(clean_t)
    if not rep or not rep.get("report_text"):
        raise HTTPException(status_code=404, detail="Report not found.")

    record_usage_event(
        event_type="pdf_download",
        ticker=clean_t,
        details={"action": "export_pdf"}
    )

    from ui.pdf import generate_report_pdf
    pdf_bytes = generate_report_pdf(clean_t, rep.get("report_text", ""))
    
    date_slug = datetime.now(IST).strftime("%d-%m-%Y")
    filename = f"{clean_t}_{date_slug}_Research_Report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/sitemap.xml", response_class=Response)
async def sitemap_xml():
    """Generates automated XML sitemap for Google/Perplexity/Bing search crawlers."""
    archives = get_archived_reports_sync()
    # Use current date for static pages
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <url><loc>https://stockresearch.app/</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>',
        f'  <url><loc>https://stockresearch.app/pricing</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>https://stockresearch.app/terms</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>https://stockresearch.app/privacy</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>https://stockresearch.app/refund-policy</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>https://stockresearch.app/contact</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>https://stockresearch.app/shipping-policy</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>https://stockresearch.app/disclaimer</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
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


@app.get("/healthz")
async def healthz():
    """Health check endpoint with caching (short‑lived)."""
    data = {"status": "healthy", "service": "Stock Research AI Web Server", "timestamp": datetime.now(IST).isoformat()}
    return json_response_with_cache(data, max_age=30)


@app.post("/api/admin/run-discovery")
async def api_run_discovery(
    background_tasks: BackgroundTasks,
    x_admin_key: Optional[str] = Header(None),
    count: int = 12,
    force: bool = False
):
    """Triggers the Morning Discovery Reel screening and dossier synthesis worker."""
    admin_secret = os.environ.get("ADMIN_API_KEY", "")
    if admin_secret and x_admin_key != admin_secret:
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

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "authenticated": True,
            "current_admin": admin_profile,
            "admin_team": admin_team,
            "admin_audit_logs": admin_audit_logs,
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
            b.get("sac_code", "998314"),
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
        "Sitemap: https://stock-research-app-2ljm.onrender.com/sitemap.xml\n"
    )
    return Response(content=content, media_type="text/plain")


@app.get("/sitemap.xml", response_class=Response)
async def sitemap_xml():
    """Generates an XML sitemap of all public routes and canonical stock dossiers."""
    try:
        archives = get_archived_reports_sync()
    except Exception:
        archives = []

    base_url = "https://stock-research-app-2ljm.onrender.com"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    urls = [
        f"<url><loc>{base_url}/</loc><lastmod>{today_str}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>",
        f"<url><loc>{base_url}/discovery</loc><lastmod>{today_str}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>",
        f"<url><loc>{base_url}/compare</loc><lastmod>{today_str}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>",
        f"<url><loc>{base_url}/pricing</loc><lastmod>{today_str}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>",
        f"<url><loc>{base_url}/contact</loc><lastmod>{today_str}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>",
        f"<url><loc>{base_url}/disclaimer</loc><lastmod>{today_str}</lastmod><changefreq>monthly</changefreq><priority>0.6</priority></url>",
        f"<url><loc>{base_url}/terms</loc><lastmod>{today_str}</lastmod><changefreq>monthly</changefreq><priority>0.5</priority></url>",
        f"<url><loc>{base_url}/privacy</loc><lastmod>{today_str}</lastmod><changefreq>monthly</changefreq><priority>0.5</priority></url>",
        f"<url><loc>{base_url}/refund-policy</loc><lastmod>{today_str}</lastmod><changefreq>monthly</changefreq><priority>0.5</priority></url>",
        f"<url><loc>{base_url}/shipping-policy</loc><lastmod>{today_str}</lastmod><changefreq>monthly</changefreq><priority>0.5</priority></url>",
    ]

    for a in archives:
        t = a.get("ticker")
        if t:
            urls.append(
                f"<url><loc>{base_url}/dossier/{t}</loc><lastmod>{today_str}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>"
            )

    xml_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )
    return Response(content=xml_content, media_type="application/xml")

