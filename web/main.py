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
import json
import logging
import markdown
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

from core.db import (
    init_db,
    get_archived_reports,
    get_report_by_ticker,
    get_report_revisions,
    get_or_create_user,
    get_user_by_id,
    get_user_by_email,
    IST,
)
from core.analysis import get_stock_fundamentals
from core.billing import (
    PRICING_PACKS,
    B2B_PACKS,
    get_plan_by_id,
    create_razorpay_order,
    process_successful_payment,
    RazorpayAuthError,
    RazorpayAPIError,
)
from normalizer import clean_ticker
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


# ==============================================================================
# Page Routes (SSR)
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Public home & landing page with live stock search and featured dossiers."""
    try:
        archives = get_archived_reports()
    except Exception as e:
        logger.error(f"Error fetching archives: {e}")
        archives = []

    featured = archives[:9] if archives else []
    total_count = len(archives) if archives else 81

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "active_page": "home",
            "featured_reports": featured,
            "total_reports": total_count,
            "pricing_packs": PRICING_PACKS,
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

    # Convert report markdown into semantic HTML
    raw_md = rep.get("report_text", "")
    html_content = markdown.markdown(
        raw_md,
        extensions=["tables", "fenced_code", "nl2br"]
    )

    # Ingest verified citations footnotes
    citations = []
    cit_json = rep.get("citations_json")
    if cit_json:
        try:
            citations = json.loads(cit_json)
        except Exception:
            citations = []

    mcap = rep.get("baseline_mcap")
    mcap_formatted = f"₹{format_inr(mcap)}" if mcap else "N/A"

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
        }
    )


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


@app.get("/healthz")
async def healthz():
    """Health check endpoint for cloud container orchestrators."""
    return {"status": "healthy", "service": "Stock Research AI Web Server", "timestamp": datetime.now(IST).isoformat()}
