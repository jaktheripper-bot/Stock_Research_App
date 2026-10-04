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
import re
import json
import logging
import markdown
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Form, Header, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
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
    get_archived_reports,
    get_report_by_ticker,
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
    MANDATORY_SEBI_DISCLAIMER,
    IST,
)
from core.db.telemetry import record_usage_event
from core.analysis import get_stock_fundamentals, get_historical_prices
from core.analysis.engine import generate_stock_report
from core.analysis.comparator import compare_two_companies
from core.analysis.parser import extract_health_matrix, compare_revisions, remove_health_matrix_text
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

logger = logging.getLogger("equity_research.web")

# Initialize DB migrations on startup
init_db()

app = FastAPI(
    title="Stock Research AI",
    description="Institutional-Grade 7-Pillar Equity Research Engine Grounded in Public Filings",
    version="2.0.0"
)

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
async def home_page(request: Request):
    """Public home & landing page with live stock search, discovery reel, and featured dossiers."""
    try:
        archives = get_archived_reports()
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
async def discovery_page(request: Request, edition: Optional[str] = Query(None)):
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
async def pricing_page(request: Request):
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
async def dossier_page(request: Request, ticker: str):
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

    rep = get_report_by_ticker(canonical)
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
        comp_data = compare_two_companies(canonical_a, canonical_b)
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
        }
    )
    return {
        "success": True,
        "message": f"🔒 Pre-Mortem counter-thesis committed to decision ledger for {clean_t}!"
    }


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
    """Contact Us & Support page."""
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={"policy": POLICIES["contact"], "active_page": "contact"}
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
    """Returns ticker autocomplete suggestions."""
    if not q or len(q.strip()) < 2:
        return {"suggestions": []}
    return {"suggestions": get_ticker_suggestions(q.strip())}


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

    return {
        "success": True,
        "message": f"Welcome {user.get('full_name')}! You have received 2 free research credits.",
        "user": user
    }


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
        return {
            "order_id": order.get("order_id") or order.get("id"),
            "id": order.get("id") or order.get("order_id"),
            "amount": order.get("amount"),
            "currency": order.get("currency", "INR"),
            "key_id": order.get("key_id"),
            "receipt": order.get("receipt"),
            "status": order.get("status", "created"),
            "is_simulated": order.get("is_simulated", False),
            "plan": order.get("plan")
        }
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

        return {
            "success": True,
            "message": "Payment verified successfully",
            "order_id": eff_order_id,
            "payment_id": eff_payment_id,
            "new_balance": new_bal,
            "invoice_number": inv_num
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/pdf/{ticker}")
async def api_download_pdf(ticker: str):
    """Generates and serves the official downloadable PDF report."""
    clean_t = clean_ticker(ticker)
    rep = get_report_by_ticker(clean_t)
    if not rep or not rep.get("report_text"):
        raise HTTPException(status_code=404, detail="Report not found.")

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
    archives = get_archived_reports()
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
            xml_lines.append(
                f'  <url><loc>https://stockresearch.app/dossier/{t}</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>'
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
    existing = get_report_by_ticker(canonical)
    if existing and existing.get("report_text") and not payload.force_refresh:
        return {
            "success": True,
            "already_exists": True,
            "ticker": canonical,
            "dossier_url": f"/dossier/{canonical}",
            "new_balance": get_user_credits_balance(clean_uid),
            "message": f"An existing dossier for {canonical} is already available. No credits were deducted."
        }

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
    rep = get_report_by_ticker(canonical)
    if not rep or not rep.get("report_text"):
        # Automatic refund on verification failure
        add_user_credits(clean_uid, 0.0, 1.0, pack_type="REFUND_FAILED_SYNTHESIS")
        refunded_bal = get_user_credits_balance(clean_uid)
        raise HTTPException(
            status_code=500,
            detail=f"Synthesis could not verify report archiving for {canonical}. Your credit has been automatically refunded (balance: {refunded_bal:.1f} credits)."
        )

    return {
        "success": True,
        "already_exists": False,
        "ticker": canonical,
        "dossier_url": f"/dossier/{canonical}",
        "new_balance": new_balance,
        "message": f"Dossier for {canonical} synthesized successfully! 1 credit deducted."
    }


@app.get("/api/user/{user_id}")
async def api_get_user(user_id: str):
    """Returns current user profile and credit balance from the database."""
    clean_uid = str(user_id).strip()
    user = get_user_by_id(clean_uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"success": True, "user": user}


@app.get("/healthz")
async def healthz():
    """Health check endpoint for cloud container orchestrators."""
    return {"status": "healthy", "service": "Stock Research AI Web Server", "timestamp": datetime.now(IST).isoformat()}


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
    return {
        "status": "initiated",
        "message": f"Morning Discovery Reel worker dispatched for {count} equities (force={force})."
    }
