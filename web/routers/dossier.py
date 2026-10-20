"""Institutional Equity Dossier, Synthesis, and PDF Export Router.

Provides:
- Synchronous 7-pillar AI research synthesis with automated credit rollback on failure
- Ticker-level deep dive unlocking and session entitlement verification
- High-performance Category 1 institutional intelligence payload generation
- Branded PDF research dossier compilation with watermarking & paywall gating
- Public Developer API v1 for programmatic equity research ingestion
"""

import os
import re
import json
import logging
import hmac
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Request, Response, HTTPException, Header
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

PDF_SEMAPHORE = asyncio.Semaphore(4)

from normalizer import clean_ticker
from bse_master import resolve_canonical_symbol, resolve_bse_scrip_code, get_ticker_suggestions
from core.config import get_secret
from core.db import (
    init_db,
    get_report_by_ticker_sync,
    get_latest_report,
    get_user_credits_balance,
    deduct_user_credits,
    add_user_credits,
    unlock_ticker_for_user,
    get_user_by_id,
    is_ticker_unlocked_for_user,
    IST,
)
from core.db.telemetry import record_usage_event
from core.analysis import get_stock_fundamentals, get_historical_prices
from core.analysis.dossier_report_synthesis import generate_stock_report

from web.common import (
    json_response_with_cache,
    _validate_request_origin,
    _get_client_ip,
    _get_current_web_user,
    _is_admin_authenticated,
    _deep_dive_unlocked_for_request,
    _asset_unlocked_for_request,
    _pdf_account_ref,
    PDF_LOCKED_NOTICE,
    _get_override_fn,
    USER_SESSION_COOKIE,
    _validate_user_session_token,
)

logger = logging.getLogger("equity_research.web.dossier")

router = APIRouter(tags=["dossier"])


# ==============================================================================
# Pydantic Schemas
# ==============================================================================
class SynthesizeRequest(BaseModel):
    ticker: str
    user_id: Optional[str] = None
    force_refresh: Optional[bool] = False


class UnlockDossierRequest(BaseModel):
    user_id: Optional[str] = None


# ==============================================================================
# Dossier Synthesis & Status Endpoints
# ==============================================================================
@router.post("/api/synthesize")
async def synthesize_report(request: Request, payload: SynthesizeRequest):
    """Requires a verified session cookie; ignores unverified client-supplied user_id."""
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")
    web_user = _get_current_web_user(request)
    is_admin = _is_admin_authenticated(request)
    if not web_user and not is_admin:
        raise HTTPException(
            status_code=401,
            detail={"error": "AUTHENTICATION_REQUIRED", "message": "Please sign in to synthesize a dossier."}
        )
    clean_uid = web_user["id"] if web_user else "admin_console"

    clean_t = clean_ticker(payload.ticker)
    if not clean_t:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    canonical = resolve_canonical_symbol(clean_t) or clean_t

    # Pre-flight validation: Ensure ticker is a recognized BSE/NSE security or archived entity
    scrip_code = resolve_bse_scrip_code(canonical)
    existing_report = get_latest_report(canonical)
    if (not scrip_code or scrip_code == "N/A") and not existing_report:
        suggestions = get_ticker_suggestions(canonical, limit=5)
        raise HTTPException(
            status_code=404,
            detail={
                "error": "UNRECOGNIZED_TICKER",
                "message": (
                    f"'{canonical}' was not found in the BSE/NSE scrip master. "
                    + (f"Did you mean: {', '.join(suggestions)}?" if suggestions else "Please verify the ticker symbol.")
                ),
                "suggestions": suggestions,
            },
        )

    existing = get_report_by_ticker_sync(canonical)
    if existing and existing.get("report_text") and not payload.force_refresh:
        return json_response_with_cache({
            "success": True,
            "already_exists": True,
            "ticker": canonical,
            "dossier_url": f"/dossier/{canonical}",
            "new_balance": get_user_credits_balance(clean_uid) if web_user else 999.0,
            "message": f"An existing dossier for {canonical} is already available. No credits were deducted."
        })

    from core.billing.qos_governor import authorize_llm_execution
    client_ip = _get_client_ip(request)
    user_email = web_user.get("email", "") if web_user else "admin_console"
    synth_auth, synth_reason = authorize_llm_execution(
        actor_type="USER_SYNTHESIS",
        user_email=user_email,
        client_ip=client_ip
    )
    if not synth_auth:
        raise HTTPException(
            status_code=429,
            detail="Hourly synthesis velocity cap reached (maximum 20 reports/hour per user) to protect account quota. Please retry later."
        )

    if not is_admin:
        ok, new_balance, msg = deduct_user_credits(
            user_id=clean_uid,
            ticker=canonical,
            action_type="FULL_SYNTHESIS",
            amount=1.0
        )
        if not ok:
            raise HTTPException(status_code=402, detail=msg)
    else:
        new_balance = get_user_credits_balance(clean_uid) if web_user else 999.0

    try:
        report_text = generate_stock_report(canonical)
    except Exception as e:
        logger.error(f"Synthesis failed for {canonical}: {e}")
        if not is_admin and web_user:
            add_user_credits(clean_uid, 0.0, 1.0, pack_type="REFUND_FAILED_SYNTHESIS")
            refunded_bal = get_user_credits_balance(clean_uid)
            detail_msg = f"Report generation encountered an error for {canonical}. Your research credit has been automatically refunded (balance: {refunded_bal:.1f} credits). Error: {e}"
        else:
            detail_msg = f"Report generation encountered an error for {canonical}. Error: {e}"
        raise HTTPException(status_code=500, detail=detail_msg)

    rep = get_report_by_ticker_sync(canonical)
    if not rep or not rep.get("report_text"):
        if not is_admin and web_user:
            add_user_credits(clean_uid, 0.0, 1.0, pack_type="REFUND_FAILED_SYNTHESIS")
            refunded_bal = get_user_credits_balance(clean_uid)
            detail_msg = f"Synthesis could not verify report archiving for {canonical}. Your credit has been automatically refunded (balance: {refunded_bal:.1f} credits)."
        else:
            detail_msg = f"Synthesis could not verify report archiving for {canonical}."
        raise HTTPException(status_code=500, detail=detail_msg)

    return json_response_with_cache({
        "success": True,
        "already_exists": False,
        "ticker": canonical,
        "dossier_url": f"/dossier/{canonical}",
        "new_balance": new_balance,
        "message": f"Dossier for {canonical} synthesized successfully! 1 credit deducted." if not is_admin else f"Dossier for {canonical} synthesized successfully via Admin Console!"
    })


api_synthesize = synthesize_report


@router.post("/api/dossier/unlock/{ticker}")
async def api_unlock_dossier(
    request: Request,
    ticker: str,
    payload: Optional[UnlockDossierRequest] = None
):
    """
    Consumes 1 credit and permanently unlocks the institutional deep-dive tier
    (Forensic Accounting Ledger, Reverse DCF Sandbox & Thesis Drift Migrations) for this equity.
    """
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")
    clean_t = clean_ticker(ticker)
    if not clean_t or not any(c.isalnum() for c in clean_t):
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    canonical = resolve_canonical_symbol(clean_t) or clean_t
    get_user_fn = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
    web_user = get_user_fn(request)
    if not web_user:
        return JSONResponse(
            status_code=401,
            content={
                "status": "error",
                "code": "AUTH_REQUIRED",
                "message": "Sign in required to unlock dossiers.",
                "detail": "Sign in required to unlock dossiers."
            }
        )
    uid = web_user.get("id")

    clean_uid = str(uid).strip()
    user = get_user_by_id(clean_uid)
    if not user:
        raise HTTPException(status_code=404, detail="User account not found. Please sign in.")

    unlock_fn = _get_override_fn("web.main", "unlock_ticker_for_user", unlock_ticker_for_user)
    ok, new_bal, msg = unlock_fn(user_id=clean_uid, ticker=canonical, amount=1.0)
    if not ok:
        raise HTTPException(status_code=402, detail=msg)

    record_usage_event(
        event_type="dossier_unlock",
        ticker=canonical,
        user_id=clean_uid,
        details={"action": "deep_dive_unlock", "new_balance": new_bal}
    )

    return json_response_with_cache({
        "success": True,
        "ticker": canonical,
        "new_balance": new_bal,
        "message": msg
    })


@router.get("/api/dossier/status/{ticker}")
async def api_dossier_status(request: Request, ticker: str):
    """Returns the unlock status of the requested ticker for the current user session."""
    clean_t = clean_ticker(ticker)
    if not clean_t:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    canonical = resolve_canonical_symbol(clean_t) or clean_t
    get_user_fn = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
    web_user = get_user_fn(request)
    is_unlocked = _deep_dive_unlocked_for_request(request, canonical)

    return json_response_with_cache({
        "success": True,
        "ticker": canonical,
        "is_unlocked": is_unlocked,
        "user_id": web_user.get("id") if web_user else None
    })


@router.get("/api/dossier/intel/{ticker}")
async def api_dossier_intel(ticker: str):
    """
    Returns comprehensive Category 1 institutional equity intelligence:
    Sector-native metrics, exchange level-2 depth, 360 forensic sieve, valuation radar, and bull/bear thesis.
    """
    clean_t = clean_ticker(ticker)
    if not clean_t:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")
    canonical = resolve_canonical_symbol(clean_t) or clean_t

    get_rep_fn = _get_override_fn("web.main", "get_report_by_ticker_sync", get_report_by_ticker_sync)
    rep = get_rep_fn(canonical) or {}
    fund = {}
    try:
        fund = get_stock_fundamentals(canonical) or {}
    except Exception as e:
        logger.debug(f"Fundamentals lookup notice for {canonical}: {e}")

    from core.analysis.equity_dossier import compile_equity_dossier
    intel = compile_equity_dossier(
        ticker=canonical,
        fundamentals=fund,
        company_name=rep.get("short_name", canonical),
        industry_str=rep.get("industry", ""),
    )
    return json_response_with_cache({"success": True, "intelligence": intel})


# ==============================================================================
# PDF Export Endpoints
# ==============================================================================
@router.get("/api/pdf/{ticker}")
async def api_download_pdf(
    ticker: str,
    request: Request,
    firm_name: Optional[str] = None,
    advisor_reg_no: Optional[str] = None,
    prepared_for: Optional[str] = None,
    custom_disclaimer: Optional[str] = None
):
    """Generates and serves the official downloadable PDF report with optional firm branding."""
    clean_t = clean_ticker(ticker)
    get_rep_fn = _get_override_fn("web.main", "get_report_by_ticker_sync", get_report_by_ticker_sync)
    rep = get_rep_fn(clean_t)
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
        except Exception as e:
            logger.debug("Failed parsing citations_json in export_dossier_pdf: %s", e)
            citations = []

    scrip_code = rep.get("scrip_code") or resolve_bse_scrip_code(clean_t)
    df_hist = None
    try:
        get_hist_fn = _get_override_fn("web.main", "get_historical_prices", get_historical_prices)
        df_hist = get_hist_fn(clean_t, period="6mo")
    except Exception as e:
        logger.debug(f"Historical price pre-fetch notice for {clean_t}: {e}")

    report_text_for_pdf = rep.get("report_text", "")
    if not _deep_dive_unlocked_for_request(request, clean_t):
        from core.agents.copilot.forensic_desk import redact_gated_pillars
        report_text_for_pdf = redact_gated_pillars(report_text_for_pdf, notice=PDF_LOCKED_NOTICE)

    from core.reporting.pdf import generate_report_pdf, apply_pdf_watermark
    async with PDF_SEMAPHORE:
        pdf_bytes = await run_in_threadpool(
            generate_report_pdf,
            clean_t,
            report_text_for_pdf,
            hist_df=df_hist,
            citations=citations,
            scrip_code=scrip_code,
            branding=branding
        )
        pdf_bytes = await run_in_threadpool(apply_pdf_watermark, pdf_bytes, _pdf_account_ref(request))

    date_slug = datetime.now(IST).strftime("%d-%m-%Y")
    clean_firm = re.sub(r'[^a-zA-Z0-9]', '_', firm_name) + "_" if firm_name else ""
    filename = f"{clean_firm}{clean_t}_{date_slug}_Research_Report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/api/pdf/fund/{scheme_code}")
async def api_download_fund_pdf(scheme_code: str, request: Request):
    """Generates and serves downloadable institutional PDF look-through dossier for a Mutual Fund."""
    clean_code = scheme_code.strip()
    from core.db.mutual_funds import get_mutual_fund_scheme, get_fund_forensic_dossier
    from core.reporting.pdf import generate_fund_dossier_pdf, apply_pdf_watermark

    scheme = get_mutual_fund_scheme(clean_code)
    if not scheme:
        raise HTTPException(status_code=404, detail=f"Scheme '{clean_code}' not found.")

    dossier = get_fund_forensic_dossier(clean_code) or {}
    async with PDF_SEMAPHORE:
        pdf_bytes = await run_in_threadpool(
            generate_fund_dossier_pdf,
            clean_code, dossier, scheme,
            deep_dive_unlocked=_asset_unlocked_for_request(request, "FUND", clean_code)
        )
        pdf_bytes = await run_in_threadpool(apply_pdf_watermark, pdf_bytes, _pdf_account_ref(request))
    filename = f"Fund_Dossier_{clean_code}_{datetime.now(IST).strftime('%d-%m-%Y')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/api/pdf/debt/{isin}")
async def api_download_debt_pdf(isin: str, request: Request):
    """Generates and serves downloadable institutional PDF credit dossier for a Corporate Debt security."""
    clean_isin = isin.strip().upper()
    from core.db.debt import get_debt_security_by_isin
    from core.analysis.debt_engine import evaluate_5_pillar_credit_posture
    from core.reporting.pdf import generate_debt_dossier_pdf, apply_pdf_watermark

    sec = get_debt_security_by_isin(clean_isin)
    if not sec:
        raise HTTPException(status_code=404, detail=f"Debt security with ISIN '{clean_isin}' not found.")

    posture = evaluate_5_pillar_credit_posture(sec)
    async with PDF_SEMAPHORE:
        pdf_bytes = await run_in_threadpool(
            generate_debt_dossier_pdf,
            clean_isin, posture, sec,
            deep_dive_unlocked=_asset_unlocked_for_request(request, "DEBT", clean_isin)
        )
        pdf_bytes = await run_in_threadpool(apply_pdf_watermark, pdf_bytes, _pdf_account_ref(request))
    filename = f"Debt_Credit_Dossier_{clean_isin}_{datetime.now(IST).strftime('%d-%m-%Y')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/api/pdf/reit/{symbol}")
async def api_download_reit_pdf(symbol: str, request: Request):
    """Generates and serves downloadable institutional PDF research dossier for a REIT or InvIT."""
    clean_sym = symbol.strip().upper()
    from core.db.reits import get_reit_by_symbol
    from core.reporting.pdf import generate_reit_dossier_pdf, apply_pdf_watermark

    reit = get_reit_by_symbol(clean_sym)
    if not reit:
        raise HTTPException(status_code=404, detail=f"REIT or InvIT with symbol '{clean_sym}' not found.")

    is_unlocked = _asset_unlocked_for_request(request, "REIT", clean_sym)
    async with PDF_SEMAPHORE:
        pdf_bytes = await run_in_threadpool(
            generate_reit_dossier_pdf,
            clean_sym, reit, deep_dive_unlocked=is_unlocked
        )
        pdf_bytes = await run_in_threadpool(apply_pdf_watermark, pdf_bytes, _pdf_account_ref(request))
    filename = f"REIT_Dossier_{clean_sym}_{datetime.now(IST).strftime('%d-%m-%Y')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/api/pdf/msme/{uin}")
async def api_download_msme_pdf(uin: str, request: Request):
    """Generates and serves downloadable institutional 4-pillar PDF forensic dossier for an unlisted MSME."""
    clean_uin = uin.strip().upper()
    from core.msme.router import get_msme_detail
    from core.reporting.pdf import generate_msme_dossier_pdf, apply_pdf_watermark

    dossier = get_msme_detail(clean_uin)
    if not dossier:
        raise HTTPException(status_code=404, detail=f"MSME enterprise with UIN '{clean_uin}' not found.")

    record_usage_event(
        event_type="pdf_download",
        ticker=clean_uin,
        details={"action": "export_msme_pdf"}
    )

    is_unlocked = _asset_unlocked_for_request(request, "MSME", clean_uin)
    async with PDF_SEMAPHORE:
        pdf_bytes = await run_in_threadpool(
            generate_msme_dossier_pdf,
            clean_uin,
            dossier,
            deep_dive_unlocked=is_unlocked
        )
        pdf_bytes = await run_in_threadpool(apply_pdf_watermark, pdf_bytes, _pdf_account_ref(request))
    safe_uin = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_uin)
    filename = f"MSME_Forensic_Dossier_{safe_uin}_{datetime.now(IST).strftime('%d-%m-%Y')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ==============================================================================
# Public Developer API v1
# ==============================================================================
@router.get("/api/v1/reports/{ticker}")
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

    expected_api_key = (os.environ.get("ADMIN_API_KEY") or get_secret("ADMIN_API_KEY") or "").strip()
    is_valid_auth = False
    if provided_key:
        if expected_api_key and hmac.compare_digest(provided_key, expected_api_key):
            is_valid_auth = True
        elif os.environ.get("TESTING") == "1" and (provided_key.startswith("sr_dev_") or provided_key.startswith("usr_")):
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

    get_rep_fn = _get_override_fn("web.main", "get_report_by_ticker_sync", get_report_by_ticker_sync)
    rep = get_rep_fn(clean_t)
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
            "attribution": "Moatnomics (https://moatnomics.com)"
        },
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Robots-Tag": "noindex"
        }
    )
