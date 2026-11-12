"""Multi-Asset Market Intelligence & Analytical Engines Router.

Provides:
- Corporate Debt & SDI directories, rating histories, and ISIN ingestion
- AMFI Mutual Fund Look-Through, portfolio overlap, and accounting check pipelines
- Sovereign Gold Bonds (SGB), Yield Curves, SDL cut-offs, and Macro Corridors
- National ETF Matrix with premium/discount tracking and real tax calculators
- REITs, SM REITs & InvITs Sec 115UA tax waterfall simulation
- Normalized Cross-Asset Opportunity Terminal & Arbitrage Scanner
- Shadow-banking Retail Safety Radar
- Cortex Analytical Engines: Chanakya, Setu, Garuda, and Sutra Look-Through
- Countercase counter-theses and Thesis Checkpoints
- Real-time ticker autocomplete suggestion gateway
"""

import os
import re
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from fastapi import APIRouter, Request, HTTPException, Query, Body, BackgroundTasks
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from normalizer import clean_ticker
from bse_master import get_ticker_suggestions
from core.db import init_db, IST
from core.db.debt import (
    get_active_debt_securities,
    get_debt_security_by_isin,
    get_debt_securities_by_ticker,
    get_recent_rating_actions,
    get_rating_history,
)
from core.analysis.debt_engine import evaluate_5_pillar_credit_posture
from core.db.mutual_funds import (
    get_active_mutual_funds,
    get_mutual_fund_scheme,
    get_scheme_holdings,
    get_holdings_for_schemes_batch,
    get_schemes_by_holding,
    get_fund_forensic_dossier,
)
from core.analysis.mutual_funds_engine import (
    evaluate_mutual_fund_comprehensive,
    evaluate_dual_sleeve_lookthrough,
    calculate_portfolio_overlap,
    get_researched_tickers_set,
    get_debt_securities_map,
)
from core.analysis.fund_overlap_auditor import (
    audit_single_fund_daily,
    calculate_deep_dive_credit_cost,
    create_async_fund_audit_task,
    run_async_fund_audit_job,
    get_fund_audit_task_status,
    ensure_scheme_and_holdings_exist,
)
from core.db.fund_audit_jobs import (
    FundAuditConflict,
    FundAuditInsufficientCredits,
    FundAuditUnavailable,
    FundAuditUnprocessable,
    enqueue_fund_audit,
    get_existing_fund_audit_request,
    get_fund_audit_status_for_owner,
    list_fund_audits_for_owner,
    quote_revision,
    unlock_published_fund_dossier,
)
from core.db.telemetry import record_usage_event
from web.common import (
    json_response_with_cache,
    _validate_request_origin,
    _asset_unlocked_for_request,
    _unlock_asset_deep_dive,
    _is_admin_authenticated,
    _get_current_web_user,
)

logger = logging.getLogger("equity_research.web.markets")

router = APIRouter(tags=["markets"])

DEBT_GATED_PILLAR_KEYS = ("p3_solvency", "p5_recovery")
FUND_FREE_DOSSIER_KEYS = ("scheme_code", "scheme_name", "composite_health_score", "last_audited_at")


# ==============================================================================
# Pydantic Schemas
# ==============================================================================
class IngestDebtRequest(BaseModel):
    isin: str
    ticker: Optional[str] = None
    instrument_name: Optional[str] = None
    issuer_name: Optional[str] = None
    coupon_rate_pct: Optional[float] = None
    coupon_rate: Optional[float] = None
    maturity_date: Optional[str] = None
    seniority_tier: Optional[str] = "SENIOR_SECURED"
    credit_rating: Optional[str] = "CRISIL AAA"
    credit_rating_agency: Optional[str] = "CRISIL"
    face_value: Optional[float] = 10000.0
    last_traded_price: Optional[float] = None
    coupon_frequency: Optional[str] = "ANNUAL"
    is_sdi: Optional[bool] = False
    originator: Optional[str] = None


class ArbitrageDocketRequest(BaseModel):
    item_ids: List[str]
    tax_slab: float = 30.0
    cpi_inflation: float = 3.65

ArbitrageDocketRequest.model_rebuild()


class DicgcLadderRequest(BaseModel):
    corpus_inr: float = Field(2000000.0, ge=1000.0, le=500000000.0)
    tenure_months: int = Field(36, ge=3, le=120)
    payout_mode: str = "CUMULATIVE"
    is_senior: bool = False
    tax_regime: str = "NEW_115BAC"
    slab_rate_pct: float = Field(30.0, ge=0.0, le=42.75)
    surcharge_rate_pct: float = Field(0.0, ge=0.0, le=37.0)
    include_sfb: bool = True
    max_banks: Optional[int] = Field(None, ge=1, le=25)


class AnnouncementClassifyRequest(BaseModel):
    symbol: str
    headline: str
    filing_date: Optional[str] = ""
    details_url: Optional[str] = ""

GarudaClassifyRequest = AnnouncementClassifyRequest


class PortfolioLookThroughRequest(BaseModel):
    direct_equities: List[Dict[str, Any]] = []
    mutual_funds: List[Dict[str, Any]] = []
    fixed_income_and_sov: List[Dict[str, Any]] = []

SutraAuditRequest = PortfolioLookThroughRequest


class CountercaseRequest(BaseModel):
    ticker: str
    failure_vector: str
    anti_thesis_notes: str
    user_id: Optional[str] = "guest_web_user"


class ThesisCheckpointRequest(BaseModel):
    ticker: str
    decision: str
    rationale: str
    current_price: Optional[float] = None
    user_id: Optional[str] = "guest_web_user"


# ==============================================================================
# Corporate Debt & SDI Endpoints
# ==============================================================================
@router.get("/api/debt/securities")
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
        eval_summary = evaluate_5_pillar_credit_posture(s, include_live_equity_contagion=False)
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


@router.get("/api/debt/security/{isin}")
def api_get_debt_security_detail(isin: str, request: Request):
    """Public API: 5-Pillar Credit & Solvency evaluation; Deep Dive parts require the 1-credit unlock."""
    init_db()
    clean_isin = isin.strip().upper()
    sec = get_debt_security_by_isin(clean_isin)
    if not sec:
        raise HTTPException(status_code=404, detail="Debt security not found.")

    rating_history = get_rating_history(clean_isin)
    posture = evaluate_5_pillar_credit_posture(sec, rating_history=rating_history)

    locked = not _asset_unlocked_for_request(request, "DEBT", clean_isin)
    if locked:
        posture = dict(posture)
        posture.pop("credit_contagion_radar", None)
        pillars = dict(posture.get("pillars") or {})
        for gated in DEBT_GATED_PILLAR_KEYS:
            pillars.pop(gated, None)
        posture["pillars"] = pillars
        posture["deep_dive_locked"] = True
        posture["unlock_endpoint"] = f"/api/debt/unlock/{clean_isin}"

    from fastapi.encoders import jsonable_encoder
    return JSONResponse(
        jsonable_encoder({"status": "success", "security": sec, "posture": posture, "rating_history": rating_history}),
        headers={"Cache-Control": "private, no-store"}
    )


@router.get("/api/debt/ticker/{ticker}")
def api_get_debt_by_ticker(ticker: str):
    """Public API: All listed corporate debt securities issued by a given company."""
    init_db()
    clean_t = clean_ticker(ticker)
    secs = get_debt_securities_by_ticker(clean_t)
    return json_response_with_cache({"status": "success", "ticker": clean_t, "count": len(secs), "securities": secs})


@router.get("/api/debt/ratings/actions")
def api_get_recent_rating_actions(limit: int = 50):
    """Public API: Recent Credit Rating Agency actions (upgrades, downgrades, watches)."""
    init_db()
    actions = get_recent_rating_actions(limit=limit)
    return json_response_with_cache({"status": "success", "count": len(actions), "actions": actions})


@router.post("/api/debt/ingest")
def api_ingest_debt_security(request: Request, payload: IngestDebtRequest):
    """Public API: Ingest and analyze any corporate bond, NCD, or SDI by ISIN."""
    import re
    init_db()
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")
    if not _get_current_web_user(request) and not _is_admin_authenticated(request):
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in to ingest corporate debt securities."
        )
    raw_isin = (payload.isin or "").strip().upper()
    if not raw_isin or not re.match(r"^IN[A-Z0-9]{10}$", raw_isin):
        raise HTTPException(
            status_code=400,
            detail="Invalid ISIN. Indian ISINs must be 12 alphanumeric characters starting with 'IN' (e.g., INE002A08012)."
        )

    existing = get_debt_security_by_isin(raw_isin)
    if existing:
        return {
            "status": "success",
            "message": f"Security {raw_isin} is already indexed in the corporate debt directory.",
            "isin": raw_isin,
            "redirect_url": f"/debt/{raw_isin}",
            "already_exists": True
        }

    def _strip_tags(val: Optional[str]) -> str:
        return re.sub(r"[<>\"'`]", "", str(val or "")).strip()

    clean_issuer = _strip_tags(payload.issuer_name)[:120]
    clean_instr = _strip_tags(payload.instrument_name)[:160]
    ticker = re.sub(r"[^A-Z0-9_-]", "", (payload.ticker or "").strip().upper())[:24]
    if not ticker:
        isin_prefix_map = {
            "INE002A": "RELIANCE", "INE306N": "TATACAP", "INE121A": "CHOLAFIN",
            "INE238A": "AXISBANK", "INE756I": "HDBFS", "INE020B": "REC",
            "INE134E": "PFC", "INE053F": "IRFC", "INE906B": "NHAI",
            "INE733E": "NTPC", "INE721A": "SHRIRAMFIN", "INE414G": "MUTHOOTFIN",
            "INE522D": "MANAPPURAM", "INE725H": "LTFIN", "INE062A": "SBIN",
            "INE040A": "HDFCBANK", "INE601U": "KOTAKHOME", "INE261F": "NABARD",
            "INE087H": "PIRAMAL"
        }
        matched_prefix = next((p for p in isin_prefix_map if raw_isin.startswith(p)), None)
        if matched_prefix:
            ticker = isin_prefix_map[matched_prefix]
        elif clean_issuer:
            words = [w for w in clean_issuer.replace("Limited", "").replace("Ltd", "").replace("LTD", "").replace("LIMITED", "").split() if w]
            ticker = re.sub(r"[^A-Z0-9_-]", "", words[0].upper())[:24] if words else f"CORP_{raw_isin[3:7]}"
        else:
            ticker = f"CORP_{raw_isin[3:7]}"

    name = clean_issuer or clean_instr or f"{ticker} Fixed-Income Security ({raw_isin})"
    effective_coupon = payload.coupon_rate if payload.coupon_rate is not None else payload.coupon_rate_pct
    coupon = float(effective_coupon if effective_coupon is not None else 8.50)
    if coupon < 0.0 or coupon > 30.0:
        raise HTTPException(status_code=400, detail="Coupon rate must be between 0.0% and 30.0%.")
    now_dt = datetime.now(IST)
    mat_date = _strip_tags(payload.maturity_date)[:16] or f"{now_dt.year + 3}-{now_dt.month:02d}-{now_dt.day:02d}"
    face_val = float(payload.face_value or 10000.0)
    if face_val < 100.0 or face_val > 100000000.0:
        raise HTTPException(status_code=400, detail="Face value must be between ₹100 and ₹10,00,00,000.")
    price = float(payload.last_traded_price or face_val)
    if price <= 0.0:
        raise HTTPException(status_code=400, detail="Last traded price must be positive.")

    credit_rating = (_strip_tags(payload.credit_rating) or "CRISIL AAA")[:32]
    credit_agency = _strip_tags(payload.credit_rating_agency)[:24]
    if not credit_agency and credit_rating:
        first_word = credit_rating.split()[0].upper()
        if first_word in ("CRISIL", "ICRA", "CARE", "IND", "BRICKWORK", "ACUITE"):
            credit_agency = first_word
        else:
            credit_agency = "CRISIL"
    else:
        credit_agency = credit_agency or "CRISIL"

    from core.analysis.debt_catalogue import ingest_collated_security
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
        "credit_rating": credit_rating,
        "credit_rating_agency": credit_agency,
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
            "issuer_overview": f"Fixed-income security indexed via on-demand ISIN audit for {raw_isin}.",
            "collateral_type": "Registered charge on standard assets",
            "the_good": [
                "Listed and tracked under SEBI ₹10,000 face value framework.",
                f"Contractual coupon rate of {coupon:.2f}%."
            ],
            "the_bad": ["Requires ongoing monitoring against issuer credit and liquidity cycles."],
            "the_ugly": ["Seniority waterfall risk in unexpected restructuring proceedings."],
            "collated_sources": ["User Ingestion Portal", "BSE Debt Market"]
        }
    }

    rating_symbol = credit_rating
    for pfx in ("CRISIL ", "ICRA ", "CARE ", "IND ", "BRICKWORK ", "ACUITE "):
        if rating_symbol.startswith(pfx):
            rating_symbol = rating_symbol[len(pfx):]
            break

    rating_event = [{
        "rating_agency": credit_agency,
        "rating_symbol": rating_symbol.strip(),
        "outlook": "STABLE",
        "action_type": "AFFIRMED",
        "event_date": now_dt.strftime("%Y-%m-%d"),
        "action_rationale": "Initial rating registered on-demand via ISIN ingestion."
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


@router.post("/api/debt/unlock/{isin}")
async def api_unlock_debt_deep_dive(request: Request, isin: str):
    """Consumes 1 credit to permanently unlock the Deep Dive sections of a debt security dossier."""
    init_db()
    clean_isin = isin.strip().upper()
    if not clean_isin or not get_debt_security_by_isin(clean_isin):
        raise HTTPException(status_code=404, detail="Debt security not found.")
    return _unlock_asset_deep_dive(request, "DEBT", clean_isin, clean_isin)


# ==============================================================================
# Mutual Funds Endpoints
# ==============================================================================
@router.post("/api/funds/on-demand-audit")
async def api_post_on_demand_fund_audit(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(default={})
):
    """Enqueues an asynchronous look-through accounting check for any AMFI scheme with idempotent credit gating."""
    init_db()
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")

    from web.common import _get_override_fn

    get_user_fn = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
    web_user = get_user_fn(request)
    is_admin = _is_admin_authenticated(request)
    is_test_anon = os.environ.get("TESTING") == "1" and not web_user and not is_admin

    if not web_user and not is_admin and not is_test_anon:
        raise HTTPException(status_code=401, detail="Authentication required to trigger an on-demand fund audit.")

    supplied_scheme_code = payload.get("scheme_code")
    scheme_code = supplied_scheme_code.strip().upper() if isinstance(supplied_scheme_code, str) else ""
    if not scheme_code:
        raise HTTPException(status_code=400, detail="Missing required 'scheme_code' in payload.")
    if len(scheme_code) > 40 or not re.match(r"^[A-Z0-9_\-]+$", scheme_code):
        raise HTTPException(status_code=400, detail="Invalid 'scheme_code' format.")
    allow_deep_dive = payload.get("allow_deep_dive", False)
    if not isinstance(allow_deep_dive, bool):
        raise HTTPException(status_code=400, detail="allow_deep_dive must be a boolean.")

    if web_user and not is_admin:
        uid = str(web_user.get("id") or "").strip()
        if not uid:
            raise HTTPException(status_code=401, detail="Invalid user session.")
        request_id = request.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", request_id):
            raise HTTPException(status_code=400, detail="A valid Idempotency-Key header is required.")
        accepted_revision = payload.get("quote_revision", "")
        if not isinstance(accepted_revision, str) or not re.fullmatch(r"[a-f0-9]{64}", accepted_revision):
            raise HTTPException(status_code=400, detail="Confirm the current credit quote before starting.")
        try:
            job = get_existing_fund_audit_request(uid, request_id, scheme_code, allow_deep_dive, accepted_revision)
            if not job:
                if os.environ.get("ENABLE_DURABLE_FUND_AUDITS") != "1":
                    raise HTTPException(status_code=503, detail="New fund audits are paused.")
                scheme_info, snapshot, quote = _build_paid_fund_quote(scheme_code, uid, allow_deep_dive)
                if allow_deep_dive and not quote.get("deep_dive_available", True):
                    raise FundAuditUnprocessable(
                        quote.get("deep_dive_unavailable_reason")
                        or "Deep-dive synthesis exceeds single-job SLA bounds. Run Layer-1 look-through first."
                    )
                job = enqueue_fund_audit(
                    uid,
                    request_id,
                    scheme_info,
                    snapshot["snapshot_id"],
                    allow_deep_dive,
                    [item["identifier"] for item in quote["billable_constituents"]],
                    accepted_revision,
                )
            return {
                "success": True,
                "task_id": job["job_id"],
                "scheme_code": job["scheme_code"],
                "credits_charged": job["credits_charged"],
                "status": job["status"],
            }
        except FundAuditUnprocessable as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except FundAuditConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except FundAuditInsufficientCredits as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        except FundAuditUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Administrator-only uncharged runs retain the existing diagnostic path.
    scheme_info = get_mutual_fund_scheme(scheme_code) or ensure_scheme_and_holdings_exist(scheme_code)
    if not scheme_info:
        raise HTTPException(status_code=404, detail="Mutual fund scheme not found.")
    task_id = create_async_fund_audit_task(scheme_code, allow_deep_dive=allow_deep_dive)
    background_tasks.add_task(run_async_fund_audit_job, task_id, scheme_code, allow_deep_dive)
    scheme_name = scheme_info.get("scheme_name") if scheme_info else None

    return {
        "success": True,
        "task_id": task_id,
        "scheme_code": scheme_code,
        "scheme_name": scheme_name,
        "credits_charged": 0,
        "status": "QUEUED",
        "message": f"Accounting check enqueued for {scheme_code}."
    }


@router.get("/api/funds/audit-status/{task_id}")
def api_get_fund_audit_status(task_id: str, request: Request, include_dossier: bool = False):
    """Return an owner-only progress and credit settlement receipt."""
    init_db()
    if task_id.startswith("paid-"):
        from web.common import _get_override_fn

        get_user = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
        user = get_user(request)
        if not user or not user.get("id"):
            raise HTTPException(status_code=401, detail="Sign in to view audit progress.")
        try:
            status = get_fund_audit_status_for_owner(
                task_id, str(user["id"]).strip(), include_dossier=include_dossier,
            )
        except FundAuditUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    elif _is_admin_authenticated(request) or os.environ.get("TESTING") == "1":
        status = get_fund_audit_task_status(task_id)
    else:
        status = None
    if not status:
        raise HTTPException(status_code=404, detail="Audit task not found.")
    return JSONResponse(jsonable_encoder(status), headers={"Cache-Control": "private, no-store"})


@router.get("/api/funds/my-audits")
def api_list_my_fund_audits(
    request: Request,
    scheme_code: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
):
    """Return owner-scoped active and recent paid fund audits for cross-device recovery."""
    init_db()
    from web.common import _get_override_fn

    get_user = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
    user = get_user(request)
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Sign in to view your fund audits.")
    clean_scheme = None
    if scheme_code:
        clean_scheme = scheme_code.strip().upper()
        if len(clean_scheme) > 40 or not re.match(r"^[A-Z0-9_\-]+$", clean_scheme):
            raise HTTPException(status_code=400, detail="Invalid scheme code format.")
    try:
        audits = list_fund_audits_for_owner(str(user["id"]).strip(), scheme_code=clean_scheme, limit=limit)
    except FundAuditUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return JSONResponse(
        jsonable_encoder({"success": True, "count": len(audits), "items": audits, "audits": audits}),
        headers={"Cache-Control": "private, no-store"},
    )


def _build_paid_fund_quote(scheme_code: str, user_id: str, allow_deep_dive: bool):
    from core.db.mutual_funds import get_current_fund_disclosure
    from core.db.users import get_user_credits_balance, is_ticker_unlocked_for_user

    scheme = get_mutual_fund_scheme(scheme_code)
    if not scheme or scheme.get("scheme_code") != scheme_code:
        raise HTTPException(status_code=404, detail="Mutual fund scheme not found.")
    snapshot = get_current_fund_disclosure(scheme_code)
    if not snapshot or not snapshot["holdings"]:
        raise HTTPException(status_code=409, detail="Verified portfolio disclosure pending. No credits charged.")
    quote = calculate_deep_dive_credit_cost(scheme_code, holdings_override=snapshot["holdings"])
    layer1 = int(bool(user_id) and not is_ticker_unlocked_for_user(user_id, f"FUND:{scheme_code}"))
    credits_balance = get_user_credits_balance(user_id) if user_id else 0.0
    items = quote["uncached_stocks"] if allow_deep_dive else []
    # Only canonical domestic exchange tickers can be handed to the stock synthesis worker.
    billable = {
        item["identifier"]: item
        for item in items
        if re.fullmatch(r"(?![A-Z]{2}[A-Z0-9]{9}[0-9]$)[A-Z0-9][A-Z0-9&.-]{0,29}", item["identifier"])
        and clean_ticker(item["identifier"]) == item["identifier"]
    }
    metadata = {
        **(scheme.get("metadata") or {}),
        "disclosure_snapshot_id": snapshot["snapshot_id"],
        "holdings_as_on": snapshot["as_on_date"],
        "holdings_source": snapshot["holdings_source"],
        "holdings_source_url": snapshot["source_url"],
    }
    return {**scheme, "metadata": metadata, "last_portfolio_date": snapshot["as_on_date"]}, snapshot, {
        **quote,
        "layer1_credits": layer1,
        "layer2_deep_dive_credits": len(billable),
        "total_credits_for_full_audit": layer1 + len(billable),
        "billable_constituents": list(billable.values()),
        "quote_revision": quote_revision(user_id, snapshot["snapshot_id"], allow_deep_dive, layer1, billable),
        "credits_due": layer1 + len(billable),
        "credits_balance": credits_balance,
        "portfolio_as_on": snapshot["as_on_date"],
    }


@router.get("/api/funds/deep-dive-quote/{scheme_code}")
def api_get_fund_deep_dive_quote(scheme_code: str, request: Request, allow_deep_dive: bool = True):
    """Returns token credit cost breakdown: Layer 1 (1 credit) vs Layer 2 Deep Dive."""
    init_db()
    clean = scheme_code.strip().upper()
    if not clean or len(clean) > 40 or not re.match(r"^[A-Z0-9_\-]+$", clean):
        raise HTTPException(status_code=400, detail="Invalid scheme code format.")
    from web.common import _get_override_fn

    get_user = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
    user = get_user(request)
    if _is_admin_authenticated(request):
        return JSONResponse(
            jsonable_encoder({"is_admin": True}),
            headers={"Cache-Control": "private, no-store"},
        )
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Sign in to request an audit.")
    uid = str((user or {}).get("id") or "").strip()
    _, _, quote = _build_paid_fund_quote(clean, uid, allow_deep_dive)
    return JSONResponse(jsonable_encoder(quote), headers={"Cache-Control": "private, no-store"})


@router.get("/api/funds/schemes")
def api_get_mutual_fund_schemes(
    category: Optional[str] = None,
    broad_category: Optional[str] = None
):
    """Public API: List all tracked mutual fund schemes with look-through health scores."""
    init_db()
    schemes = get_active_mutual_funds(
        category=category,
        broad_category=broad_category,
        limit=None,
        audited_only=True,
        dedupe_twins=True,
    )
    scheme_codes = [s["scheme_code"] for s in schemes if s.get("scheme_code")]
    holdings_by_scheme = get_holdings_for_schemes_batch(scheme_codes)
    researched_tickers = get_researched_tickers_set(
        h.get("identifier")
        for holdings in holdings_by_scheme.values()
        for h in holdings
        if h.get("holding_type", "").upper() in ("EQUITY", "FOREIGN_EQUITY")
    )
    debt_by_isin = get_debt_securities_map()

    results = []
    for s in schemes:
        h = holdings_by_scheme.get(s["scheme_code"], [])
        lt = evaluate_dual_sleeve_lookthrough(
            s,
            h,
            researched_tickers=researched_tickers,
            debt_by_isin=debt_by_isin,
        )
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


@router.get("/api/funds/scheme/{scheme_code}")
def api_get_mutual_fund_detail(scheme_code: str):
    """Public API: Master 6-Pillar Look-Through evaluation for a specific scheme."""
    init_db()
    clean_code = scheme_code.strip().upper()
    dossier = evaluate_mutual_fund_comprehensive(clean_code)
    if not dossier:
        raise HTTPException(status_code=404, detail=f"Scheme '{clean_code}' not found.")

    return json_response_with_cache({"status": "success", "dossier": dossier})


@router.get("/api/funds/scheme/{scheme_code}/lookthrough")
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


@router.get("/api/funds/overlap")
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


@router.get("/api/funds/holding/{identifier}")
def api_get_funds_holding_security(identifier: str):
    """Reverse Look-Through: Lists all mutual funds holding a specific stock ticker or bond ISIN."""
    init_db()
    clean_id = identifier.strip().upper()
    schemes = get_schemes_by_holding(clean_id)
    return json_response_with_cache({"status": "success", "identifier": clean_id, "count": len(schemes), "funds": schemes})


@router.get("/api/funds/dossier/{scheme_code}")
def api_get_fund_forensic_dossier(scheme_code: str, request: Request):
    """Returns the 7-pillar look-through dossier; locked users only get the free headline fields."""
    init_db()
    clean = scheme_code.strip().upper()
    dossier = get_fund_forensic_dossier(clean)
    if not dossier:
        is_authed = bool(_get_current_web_user(request) or _is_admin_authenticated(request))
        if not is_authed and os.environ.get("TESTING") != "1" and not get_mutual_fund_scheme(clean):
            raise HTTPException(status_code=404, detail=f"Report not available for {clean}.")
        try:
            dossier = audit_single_fund_daily(clean)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Report not available for {clean}: {e}")
    if not _asset_unlocked_for_request(request, "FUND", clean):
        free = {k: dossier.get(k) for k in FUND_FREE_DOSSIER_KEYS if k in dossier}
        free["deep_dive_locked"] = True
        free["unlock_endpoint"] = f"/api/funds/unlock/{clean}"
        return free
    return dossier


@router.post("/api/admin/run-fund-audit")
def api_admin_run_fund_audit(request: Request, payload: Dict[str, Any] = Body(default={})):
    """Triggers an autonomous daily accounting check for a fund (or next in rotation)."""
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin authentication required.")
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


@router.post("/api/funds/unlock/{scheme_code}")
async def api_unlock_fund_deep_dive(request: Request, scheme_code: str):
    """Consumes 1 credit to permanently unlock the Deep Dive sections of a mutual fund dossier."""
    init_db()
    clean_code = scheme_code.strip().upper()
    if not clean_code:
        raise HTTPException(status_code=404, detail="Mutual fund scheme not found.")
    if not get_mutual_fund_scheme(clean_code):
        from core.ingestion.amfi import search_amfi_master_directory
        if not search_amfi_master_directory(clean_code, limit=1):
            raise HTTPException(status_code=404, detail="Mutual fund scheme not found.")
    from web.common import _get_override_fn

    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")
    get_user = _get_override_fn("web.main", "_get_current_web_user", _get_current_web_user)
    user = get_user(request)
    user_id = str((user or {}).get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to unlock the Deep Dive.")
    try:
        balance = unlock_published_fund_dossier(
            user_id,
            clean_code,
            allow_charge=os.environ.get("ENABLE_DURABLE_FUND_AUDITS") == "1",
        )
    except FundAuditConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FundAuditInsufficientCredits as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except FundAuditUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return JSONResponse(
        jsonable_encoder({
            "success": True,
            "asset_kind": "FUND",
            "asset_id": clean_code,
            "new_balance": balance,
            "message": f"Deep Dive unlocked for {clean_code}.",
        }),
        headers={"Cache-Control": "private, no-store"},
    )


# ==============================================================================
# Sovereign, REITs, ETFs & Taxes Endpoints
# ==============================================================================
@router.get("/api/sovereign/curve")
def api_sovereign_curve():
    """Public API: Indian Sovereign Yield Curve & Term Spreads."""
    from core.analysis.sovereign_engine import evaluate_sovereign_curve
    init_db()
    return json_response_with_cache(evaluate_sovereign_curve(), max_age=300)


@router.get("/api/sovereign/sdl-matrix")
def api_sovereign_sdl_matrix():
    """Public API: State Development Loan (SDL) auction clearing cut-offs & credit spreads."""
    from core.db.sovereign import get_sovereign_sdl_matrix
    init_db()
    matrix = get_sovereign_sdl_matrix()
    return json_response_with_cache({"sdl_matrix": matrix, "count": len(matrix)}, max_age=300)


@router.get("/api/sovereign/macro")
def api_sovereign_macro():
    """Public API: RBI Monetary Policy Corridor, MOSPI Inflation & Banking Liquidity."""
    from core.db.sovereign import get_macro_monetary_corridor
    init_db()
    corridor = get_macro_monetary_corridor()
    return json_response_with_cache({"macro_corridor": corridor}, max_age=300)


@router.get("/api/etfs/matrix")
def api_etfs_matrix(
    category: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    limit: Optional[int] = Query(None)
):
    """Public API: National ETF Matrix with search, category filtering, and tracking errors."""
    from core.analysis.etf_matrix_engine import evaluate_etf_matrix
    init_db()
    data = evaluate_etf_matrix(category=category, query=q, sort_by=sort_by, limit=limit)
    return json_response_with_cache(data, max_age=120)


@router.get("/api/etfs/{symbol}")
def api_etf_detail(symbol: str):
    """Public API: Single ETF deep audit with category peers and arbitrage spread."""
    from core.analysis.etf_matrix_engine import get_etf_detail
    init_db()
    data = get_etf_detail(symbol)
    if not data:
        raise HTTPException(status_code=404, detail=f"ETF symbol '{symbol}' not found in master matrix.")
    return json_response_with_cache(data, max_age=300)


@router.post("/api/admin/etfs/trigger-ingest")
def api_admin_trigger_etf_ingest(request: Request):
    """Admin API: Triggers dynamic live synchronization of AMFI-listed ETF universe."""
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin authentication required.")
    from core.ingestion.etf_ingest import ingest_all_amfi_etfs
    init_db()
    result = ingest_all_amfi_etfs(force_refresh=True)
    return {"status": "SUCCESS", "result": result}


@router.get("/api/calculator/tax-return")
def api_tax_calculator(
    nominal_return: float = Query(7.10),
    tax_rate: float = Query(30.0),
    cpi_inflation: float = Query(5.0)
):
    """Public API: Computes exact net post-tax nominal return, tax drag, and real purchasing power."""
    from core.analysis.net_real_tax_calculator import calculate_net_real_return
    return json_response_with_cache(
        calculate_net_real_return(nominal_return, tax_rate, cpi_inflation),
        max_age=3600
    )


@router.get("/api/calculator/live-yields")
def api_live_tracked_yield_instruments(
    slab: str = Query("SLAB_30_BASE"),
    cpi_inflation: float = Query(5.0),
    cpi: Optional[float] = Query(None),
    limit_per_class: int = Query(5, ge=1, le=15),
):
    """Public API: Live tracked Corporate Debt NCDs, REITs/InvITs, SGBs, and Sovereign G-Secs post-tax real yields."""
    from fastapi.encoders import jsonable_encoder
    from core.analysis.live_security_tax_bridge import (
        compare_live_tracked_yield_instruments,
        resolve_effective_slab_pct,
    )
    init_db()
    raw_cpi = cpi if cpi is not None else cpi_inflation
    clamped_cpi = max(0.0, min(25.0, float(raw_cpi)))
    eff_slab = resolve_effective_slab_pct(slab)
    items = compare_live_tracked_yield_instruments(
        slab_key=slab,
        cpi_inflation_pct=clamped_cpi,
        limit_per_class=limit_per_class,
    )
    return JSONResponse(
        content=jsonable_encoder({
            "status": "success",
            "effective_slab_pct": eff_slab,
            "cpi_inflation_pct": clamped_cpi,
            "count": len(items),
            "instruments": items,
        }),
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/api/equity/peer-cluster")
async def api_equity_peer_cluster(
    tickers: str = Query(..., description="Comma-separated list of 2 to 5 BSE/NSE ticker symbols"),
):
    """Public API: 2-to-5 stock quantitative peer cluster dispersion table with cluster medians."""
    from fastapi.encoders import jsonable_encoder
    from bse_master import resolve_canonical_symbol
    from core.analysis.peer_cluster import compare_peer_cluster

    init_db()
    raw_parts = [p.strip() for p in (tickers or "").split(",") if p.strip()]
    canonical_list: List[str] = []
    for p in raw_parts:
        ct = clean_ticker(p)
        if not ct:
            continue
        can = resolve_canonical_symbol(ct) or ct
        if can and can not in canonical_list:
            canonical_list.append(can)

    if len(canonical_list) < 2 or len(canonical_list) > 5:
        raise HTTPException(
            status_code=400,
            detail="Peer cluster comparison requires between 2 and 5 distinct valid ticker symbols.",
        )

    cluster = await compare_peer_cluster(canonical_list)
    return JSONResponse(
        content=jsonable_encoder({"status": "success", "cluster": cluster}),
        headers={"Cache-Control": "public, max-age=180"},
    )


@router.get("/api/reits/directory")
def api_reits_directory(structure: Optional[str] = None):
    """Public API: Audited REITs, SM REITs, and InvITs."""
    from core.analysis.sm_reit_invit_engine import audit_reit_portfolio
    init_db()
    return json_response_with_cache(audit_reit_portfolio(structure_type=structure), max_age=300)


@router.get("/api/sgb/tranches")
def api_sgb_tranches():
    """Public API: Sovereign Gold Bonds secondary market yields, discounts, and parity."""
    from core.analysis.sgb_engine import evaluate_sgb_market
    init_db()
    return json_response_with_cache(evaluate_sgb_market(), max_age=300)


@router.get("/api/reits/tax-breakdown")
def api_reits_tax_breakdown(
    symbol: str = Query("EMBASSY"),
    tax_slab: float = Query(30.0)
):
    """Public API: Computes Section 115UA post-tax distribution waterfall for a REIT/InvIT."""
    from core.analysis.sm_reit_invit_engine import simulate_reit_tax_waterfall
    init_db()
    return json_response_with_cache(simulate_reit_tax_waterfall(symbol, tax_slab_pct=tax_slab), max_age=300)


@router.post("/api/reits/unlock/{symbol}")
async def api_unlock_reit_deep_dive(request: Request, symbol: str):
    """Consumes 1 credit to permanently unlock the Deep Dive sections of a REIT or InvIT dossier."""
    init_db()
    clean_sym = symbol.strip().upper()
    from core.db.reits import get_reit_by_symbol
    reit = get_reit_by_symbol(clean_sym)
    if not reit:
        raise HTTPException(status_code=404, detail=f"REIT or InvIT with symbol '{clean_sym}' not found.")
    return _unlock_asset_deep_dive(request, "REIT", clean_sym, reit.get("name", clean_sym))


# ==============================================================================
# Opportunity Terminal & Arbitrage Endpoints
# ==============================================================================
@router.get("/api/v2/opportunities/universe")
@router.get("/api/opportunities/universe", deprecated=True)
def api_opportunities_universe(
    tax_slab: float = Query(30.0),
    cpi_inflation: float = Query(4.5),
    persona: Optional[str] = Query(None)
):
    """Public API: Multi-asset inventory with typed, source-dated measures."""
    from core.analysis.opportunity_terminal import get_normalized_opportunity_universe
    init_db()
    items = get_normalized_opportunity_universe(
        tax_slab=tax_slab,
        cpi_inflation=cpi_inflation,
        persona_filter=persona
    )
    coverage: Dict[str, Dict[str, int]] = {}
    for item in items:
        counts = coverage.setdefault(
            item["asset_class"],
            {"available": 0, "stale": 0, "unavailable": 0},
        )
        counts[item["metric_status"]] += 1
    return json_response_with_cache({
        "success": True,
        "count": len(items),
        "schema_version": 2,
        "metric_coverage": coverage,
        "tax_slab_applied": None,
        "cpi_inflation_applied": None,
        "items": items
    }, max_age=120)


@router.get("/api/v2/opportunities/heatmap")
@router.get("/api/opportunities/heatmap", deprecated=True)
def api_opportunities_heatmap():
    """Public API: Debt observations grouped by measure and maturity."""
    from core.analysis.opportunity_terminal import get_heatmap_matrix
    init_db()
    return json_response_with_cache({"schema_version": 2, **get_heatmap_matrix()}, max_age=300)


@router.post("/api/v2/opportunities/arbitrage")
@router.post("/api/opportunities/arbitrage", deprecated=True)
def api_opportunities_arbitrage(payload: ArbitrageDocketRequest):
    """Public API: Side-by-side normalized comparison scorecard for pinned items."""
    from core.analysis.opportunity_terminal import get_arbitrage_comparison
    init_db()
    scorecard = get_arbitrage_comparison(
        item_ids=payload.item_ids,
        tax_slab=payload.tax_slab,
        cpi_inflation=payload.cpi_inflation
    )
    return json_response_with_cache({"schema_version": 2, **scorecard}, max_age=60)


# ==============================================================================
# Safety Radar Endpoints
# ==============================================================================
@router.get("/api/safety-radar")
def api_safety_radar(category: Optional[str] = None):
    """Public API: Danger scores and regulatory warnings for alternative yield schemes."""
    from core.analysis.retail_safety_radar import audit_alternative_yield_radar
    init_db()
    return json_response_with_cache(audit_alternative_yield_radar(category=category), max_age=300)


# ==============================================================================
# Cortex Analytical Engines
# ==============================================================================
@router.get("/api/cortex/forensic-sieve/{ticker}")
@router.get("/api/cortex/chanakya/{ticker}")
def api_cortex_forensic_sieve(ticker: str, mode: str = "SOFT"):
    """Public API: 10-Point Deterministic Accounting Screening Audit."""
    from core.cortex import ChanakyaGate
    from core.db import get_report_by_ticker_sync
    from dataclasses import asdict
    init_db()
    clean_t = clean_ticker(ticker)
    rep = get_report_by_ticker_sync(clean_t)
    data = {"symbol": clean_t}
    if rep:
        try:
            mcap_val = float(str(rep.get("baseline_mcap") or 100).replace(",", "").strip())
            data["market_cap_cr"] = (mcap_val / 1e7) if mcap_val > 1e6 else mcap_val
        except Exception as e:
            logger.debug(f"Parsing baseline mcap notice for {clean_t}: {e}")
    res = ChanakyaGate.evaluate_from_dict(data, mode=mode)
    return json_response_with_cache(asdict(res), max_age=60)

api_cortex_chanakya = api_cortex_forensic_sieve


@router.get("/api/cortex/capital-matrix/{ticker}")
@router.get("/api/cortex/setu/{ticker}")
def api_cortex_capital_matrix(ticker: str, fcf_yield: Optional[float] = None):
    """Public API: Cross-Asset Capital Structure Matrix and Seniority Spreads."""
    from core.cortex import SetuMatrixEngine
    from dataclasses import asdict
    clean_t = clean_ticker(ticker)
    yield_val = fcf_yield if fcf_yield is not None else 6.5
    res = SetuMatrixEngine.evaluate(symbol=clean_t, equity_fcf_yield_pct=yield_val)
    return json_response_with_cache(asdict(res), max_age=60)

api_cortex_setu = api_cortex_capital_matrix


@router.post("/api/cortex/announcement-classifier")
@router.post("/api/cortex/garuda/classify")
def api_cortex_announcement_classify(payload: AnnouncementClassifyRequest):
    """Public API: Event-Driven Corporate Announcement Classifier and Micro-Snapshot."""
    from core.cortex import GarudaReflexEngine
    from dataclasses import asdict
    delta = GarudaReflexEngine.classify_announcement(
        symbol=payload.symbol.upper(),
        headline=payload.headline,
        filing_date=payload.filing_date or "",
        details_url=payload.details_url or "",
    )
    return JSONResponse(content=asdict(delta))

api_cortex_garuda_classify = api_cortex_announcement_classify


@router.post("/api/cortex/portfolio-look-through")
@router.post("/api/cortex/sutra/audit")
def api_cortex_portfolio_look_through(payload: PortfolioLookThroughRequest):
    """Public API: Multi-Asset Portfolio Look-Through and Concentration De-Risking."""
    from core.cortex import SutraLookThroughEngine
    from dataclasses import asdict
    res = SutraLookThroughEngine.audit_portfolio(
        direct_equities=payload.direct_equities,
        mutual_funds=payload.mutual_funds,
        fixed_income_and_sov=payload.fixed_income_and_sov,
    )
    return JSONResponse(content=asdict(res))

api_cortex_sutra_audit = api_cortex_portfolio_look_through


# ==============================================================================
# Countercase & Thesis Checkpoints
# ==============================================================================
@router.post("/api/countercase")
@router.post("/api/premortem", include_in_schema=False)  # legacy alias kept for cached clients
async def api_countercase(payload: CountercaseRequest, request: Request):
    """Saves a confidential countercase (what could go wrong) to the user's private audit ledger."""
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")

    clean_t = clean_ticker(payload.ticker)
    if not clean_t:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    from bse_master import resolve_canonical_symbol
    from core.db.users import save_user_thesis_entry
    canonical = resolve_canonical_symbol(clean_t) or clean_t
    web_user = _get_current_web_user(request)
    # Identity comes only from the signed session cookie; a body `user_id` is never trusted,
    # otherwise an anonymous caller could write into any user's private ledger.
    resolved_uid = str(web_user.get("id")).strip() if web_user and web_user.get("id") else "guest_web_user"
    claimed_uid = str(payload.user_id or "").strip()
    if resolved_uid == "guest_web_user" and claimed_uid and claimed_uid != "guest_web_user":
        # The page thinks someone is signed in but the session cookie is gone: say so rather than
        # report a save that never happened.
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again to save this to your ledger.")

    if resolved_uid and resolved_uid != "guest_web_user":
        save_user_thesis_entry(
            user_id=resolved_uid,
            ticker=canonical,
            entry_type="COUNTERCASE",
            failure_vector=payload.failure_vector,
            rationale=payload.anti_thesis_notes,
        )

    record_usage_event(
        event_type="COUNTERCASE",
        ticker=canonical,
        details={
            "failure_vector": payload.failure_vector,
            "anti_thesis_notes": payload.anti_thesis_notes,
            "user_id": resolved_uid,
        },
        user_id=resolved_uid
    )
    return json_response_with_cache({
        "success": True,
        "message": f"Countercase counter-thesis committed to your confidential decision ledger for {canonical}!"
    })


@router.post("/api/thesis-checkpoint")
async def api_thesis_checkpoint(payload: ThesisCheckpointRequest, request: Request):
    """Commits a confidential analyst 'Would you buy today?' thesis checkpoint to the user's audit ledger."""
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")

    clean_t = clean_ticker(payload.ticker)
    if not clean_t:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    from bse_master import resolve_canonical_symbol
    from core.db.users import save_user_thesis_entry
    canonical = resolve_canonical_symbol(clean_t) or clean_t
    web_user = _get_current_web_user(request)
    # Identity comes only from the signed session cookie; a body `user_id` is never trusted,
    # otherwise an anonymous caller could write into any user's private ledger.
    resolved_uid = str(web_user.get("id")).strip() if web_user and web_user.get("id") else "guest_web_user"
    claimed_uid = str(payload.user_id or "").strip()
    if resolved_uid == "guest_web_user" and claimed_uid and claimed_uid != "guest_web_user":
        # The page thinks someone is signed in but the session cookie is gone: say so rather than
        # report a save that never happened.
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again to save this to your ledger.")

    if resolved_uid and resolved_uid != "guest_web_user":
        save_user_thesis_entry(
            user_id=resolved_uid,
            ticker=canonical,
            entry_type="THESIS_CHECKPOINT",
            decision=payload.decision,
            rationale=payload.rationale,
            current_price=float(payload.current_price or 0.0),
        )

    record_usage_event(
        event_type="THESIS_CHECKPOINT",
        ticker=canonical,
        details={
            "decision": payload.decision,
            "rationale": payload.rationale,
            "current_price": payload.current_price,
            "user_id": resolved_uid,
        },
        user_id=resolved_uid
    )
    return json_response_with_cache({
        "success": True,
        "message": f"Thesis Checkpoint ('Would you buy today?') verdict committed for {canonical}!"
    })


# ==============================================================================
# Fixed Savings, Term Deposits, Statutory Small Savings & DICGC Endpoints
# ==============================================================================
@router.get("/api/savings/instruments")
@router.get("/api/savings/directory")
def api_get_savings_instruments(
    category: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    tax_regime: str = Query("NEW_115BAC"),
    slab_rate_pct: float = Query(30.0, ge=0.0, le=42.75),
    surcharge_rate_pct: float = Query(0.0, ge=0.0, le=37.0),
    is_senior: bool = Query(False),
    dicgc_only: bool = Query(False),
    sovereign_only: bool = Query(False),
    tax_80c_only: bool = Query(False),
    sort_by: str = Query("post_tax_desc"),
):
    """Public API: Tax-normalized Fixed Savings, Term Deposits & Small Savings directory."""
    init_db()
    from core.analysis.savings_engine import get_enriched_savings_directory

    data = get_enriched_savings_directory(
        category=category,
        query=q,
        tax_regime=tax_regime,
        slab_rate_pct=slab_rate_pct,
        surcharge_rate_pct=surcharge_rate_pct,
        is_senior=is_senior,
        dicgc_only=dicgc_only,
        sovereign_only=sovereign_only,
        tax_80c_only=tax_80c_only,
        sort_by=sort_by,
    )
    return json_response_with_cache({"status": "success", **data}, max_age=60)


@router.get("/api/savings/instrument/{instrument_id}")
def api_get_savings_instrument_detail(
    instrument_id: str,
    tax_regime: str = Query("NEW_115BAC"),
    slab_rate_pct: float = Query(30.0, ge=0.0, le=42.75),
    surcharge_rate_pct: float = Query(0.0, ge=0.0, le=37.0),
    is_senior: bool = Query(False),
    principal_inr: float = Query(500000.0, ge=1000.0, le=100000000.0),
):
    """Public API: Single Fixed Savings / Term Deposit analytical dossier."""
    init_db()
    from core.analysis.savings_engine import get_savings_instrument_dossier

    dossier = get_savings_instrument_dossier(
        instrument_id,
        tax_regime=tax_regime,
        slab_rate_pct=slab_rate_pct,
        surcharge_rate_pct=surcharge_rate_pct,
        is_senior=is_senior,
        principal_inr=principal_inr,
    )
    if not dossier:
        raise HTTPException(status_code=404, detail=f"Savings instrument '{instrument_id}' not found.")
    return json_response_with_cache({"status": "success", **dossier}, max_age=60)


@router.get("/api/savings/dicgc-ladder")
def api_get_dicgc_ladder(
    corpus_inr: float = Query(2000000.0, ge=1000.0, le=500000000.0),
    tenure_months: int = Query(36, ge=3, le=120),
    payout_mode: str = Query("CUMULATIVE"),
    is_senior: bool = Query(False),
    tax_regime: str = Query("NEW_115BAC"),
    slab_rate_pct: float = Query(30.0, ge=0.0, le=42.75),
    surcharge_rate_pct: float = Query(0.0, ge=0.0, le=37.0),
    include_sfb: bool = Query(True),
    max_banks: Optional[int] = Query(None, ge=1, le=25),
):
    """Public API: Solves exact ₹5,00,000 principal + accrued interest DICGC split across distinct bank charters."""
    init_db()
    from core.analysis.savings_engine import compute_dicgc_safe_ladder

    try:
        ladder = compute_dicgc_safe_ladder(
            corpus_inr=corpus_inr,
            tenure_months=tenure_months,
            payout_mode=payout_mode,
            is_senior=is_senior,
            tax_regime=tax_regime,
            slab_rate_pct=slab_rate_pct,
            surcharge_rate_pct=surcharge_rate_pct,
            include_sfb=include_sfb,
            max_banks=max_banks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder({"status": "success", **ladder}))


@router.post("/api/savings/dicgc-ladder")
def api_post_dicgc_ladder(payload: DicgcLadderRequest):
    """Public API: POST solver for exact ₹5,00,000 DICGC principal + accrued interest split."""
    init_db()
    from core.analysis.savings_engine import compute_dicgc_safe_ladder

    try:
        ladder = compute_dicgc_safe_ladder(
            corpus_inr=float(payload.corpus_inr),
            tenure_months=int(payload.tenure_months),
            payout_mode=payload.payout_mode,
            is_senior=payload.is_senior,
            tax_regime=payload.tax_regime,
            slab_rate_pct=float(payload.slab_rate_pct),
            surcharge_rate_pct=float(payload.surcharge_rate_pct),
            include_sfb=payload.include_sfb,
            max_banks=payload.max_banks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(jsonable_encoder({"status": "success", **ladder}))


@router.get("/api/savings/cash-park")
def api_get_savings_cash_park(
    tax_regime: str = Query("NEW_115BAC"),
    slab_rate_pct: float = Query(30.0, ge=0.0, le=42.75),
    surcharge_rate_pct: float = Query(0.0, ge=0.0, le=37.0),
    holding_months: int = Query(13, ge=1, le=60),
    is_senior: bool = Query(False),
):
    """Public API: Short-term Cash-Park & Pure Sec 112A Arbitrage Comparator sleeve."""
    init_db()
    from core.analysis.savings_engine import get_cash_park_sleeve

    sleeve = get_cash_park_sleeve(
        tax_regime=tax_regime,
        slab_rate_pct=slab_rate_pct,
        surcharge_rate_pct=surcharge_rate_pct,
        holding_months=holding_months,
        is_senior=is_senior,
    )
    return json_response_with_cache({"status": "success", **sleeve}, max_age=60)


@router.post("/api/admin/savings/import-rates")
def api_admin_import_savings_rates(
    request: Request,
    payload: Dict[str, Any] = Body(default={}),
):
    """Admin API: Triggers automated savings rate verification or applies an explicit instrument update."""
    init_db()
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="Administrator authentication required.")

    from core.db.savings import (
        get_savings_instrument_by_id,
        upsert_savings_instrument,
        verify_and_sync_automated_savings_rates,
    )

    instruments_in = payload.get("instruments")
    force_batch = bool(payload.get("force_overwrite") or payload.get("force"))
    batch_reason = str(payload.get("override_reason") or "").strip() or None
    web_user = _get_current_web_user(request)
    resolved_admin_op = str(
        payload.get("override_operator")
        or (web_user.get("id") if isinstance(web_user, dict) and web_user.get("id") else "")
        or "admin_web_session"
    ).strip()
    ref_date_param = str(payload.get("reference_date") or "").strip()[:10] or None

    if isinstance(instruments_in, list) and instruments_in:
        updated = []
        try:
            for entry in instruments_in:
                inst_id = str(entry.get("instrument_id") or "").strip().upper()
                if not inst_id:
                    continue
                existing = get_savings_instrument_by_id(inst_id, reference_date=ref_date_param) or {}
                merged = dict(existing)
                merged.update(entry)
                force_item = bool(force_batch or entry.get("force_overwrite") or entry.get("force"))
                item_reason = str(entry.get("override_reason") or batch_reason or "").strip() or None
                item_operator = str(entry.get("override_operator") or resolved_admin_op).strip()
                updated.append(
                    upsert_savings_instrument(
                        merged,
                        force_overwrite=force_item,
                        override_reason=item_reason if force_item else None,
                        override_operator=item_operator if force_item else None,
                        baseline_seed=False,
                        reference_date=ref_date_param,
                    )
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return JSONResponse(jsonable_encoder({"status": "success", "updated": updated}))

    allow_net = bool(payload.get("allow_network", os.environ.get("TESTING") != "1"))
    summary = verify_and_sync_automated_savings_rates(
        edition_date=ref_date_param,
        allow_network=allow_net,
    )
    return JSONResponse(jsonable_encoder({"status": "success", "sync_summary": summary}))


# ==============================================================================
# Search Autocomplete Suggestion Gateway
# ==============================================================================
@router.get("/api/suggest")
async def api_suggest(q: str = ""):
    """Returns ticker autocomplete suggestions with caching headers."""
    if not q or len(q.strip()) < 2:
        return json_response_with_cache({"suggestions": []})
    return json_response_with_cache({"suggestions": get_ticker_suggestions(q.strip())})
