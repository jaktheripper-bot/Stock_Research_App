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
from pydantic import BaseModel

from fastapi import APIRouter, Request, HTTPException, Query, Body, BackgroundTasks
from fastapi.responses import JSONResponse

from normalizer import clean_ticker
from bse_master import get_ticker_suggestions
from core.db import init_db
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
    get_schemes_by_holding,
    get_fund_forensic_dossier,
)
from core.analysis.mutual_funds_engine import (
    evaluate_mutual_fund_comprehensive,
    evaluate_dual_sleeve_lookthrough,
    calculate_portfolio_overlap,
)
from core.analysis.fund_overlap_auditor import (
    audit_single_fund_daily,
    calculate_deep_dive_credit_cost,
    create_async_fund_audit_task,
    run_async_fund_audit_job,
    get_fund_audit_task_status,
    ensure_scheme_and_holdings_exist,
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
    cpi_inflation: float = 4.5

ArbitrageDocketRequest.model_rebuild()


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
    now_dt = datetime.now()
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
    """Enqueues an asynchronous look-through accounting check for any AMFI scheme."""
    init_db()
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")
    if os.environ.get("TESTING") != "1" and not _get_current_web_user(request) and not _is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required to trigger an on-demand fund audit.")
    scheme_code = (payload.get("scheme_code") or "").strip().upper()
    if not scheme_code:
        raise HTTPException(status_code=400, detail="Missing required 'scheme_code' in payload.")
    if len(scheme_code) > 40 or not re.match(r"^[A-Z0-9_\-]+$", scheme_code):
        raise HTTPException(status_code=400, detail="Invalid 'scheme_code' format.")
    allow_deep_dive = bool(payload.get("allow_deep_dive", False))

    task_id = create_async_fund_audit_task(scheme_code, allow_deep_dive=allow_deep_dive)
    background_tasks.add_task(run_async_fund_audit_job, task_id, scheme_code, allow_deep_dive)

    scheme_info = get_mutual_fund_scheme(scheme_code) or ensure_scheme_and_holdings_exist(scheme_code)
    scheme_name = scheme_info.get("scheme_name") if scheme_info else None

    return {
        "success": True,
        "task_id": task_id,
        "scheme_code": scheme_code,
        "scheme_name": scheme_name,
        "status": "QUEUED",
        "message": f"Accounting check enqueued for {scheme_code}."
    }


@router.get("/api/funds/audit-status/{task_id}")
def api_get_fund_audit_status(task_id: str):
    """Returns real-time progress and completion status for an asynchronous fund audit task."""
    init_db()
    status = get_fund_audit_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Audit task '{task_id}' not found.")
    return status


@router.get("/api/funds/deep-dive-quote/{scheme_code}")
def api_get_fund_deep_dive_quote(scheme_code: str):
    """Returns token credit cost breakdown: Layer 1 (1 credit) vs Layer 2 Deep Dive."""
    init_db()
    clean = scheme_code.strip().upper()
    if not clean or len(clean) > 40 or not re.match(r"^[A-Z0-9_\-]+$", clean):
        raise HTTPException(status_code=400, detail="Invalid scheme code format.")
    scheme = get_mutual_fund_scheme(clean)
    if not scheme:
        from core.ingestion.amfi import search_amfi_master_directory, save_mutual_fund_scheme
        amfi_matches = search_amfi_master_directory(clean, limit=5)
        for m in amfi_matches:
            if str(m.get("scheme_code", "")).strip().upper() == clean:
                save_mutual_fund_scheme(m)
                scheme = get_mutual_fund_scheme(clean) or m
                break
    if not scheme:
        raise HTTPException(status_code=404, detail=f"Mutual fund scheme '{clean}' not found.")
    try:
        return calculate_deep_dive_credit_cost(clean)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate credit quote for {clean}: {str(e)}")


@router.get("/api/funds/schemes")
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
    return _unlock_asset_deep_dive(request, "FUND", clean_code, clean_code)


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
@router.get("/api/opportunities/universe")
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


@router.get("/api/opportunities/heatmap")
def api_opportunities_heatmap():
    """Public API: 2D relative yield spread heatmap matrix over 10Y G-Sec."""
    from core.analysis.opportunity_terminal import get_heatmap_matrix
    init_db()
    return json_response_with_cache(get_heatmap_matrix(), max_age=300)


@router.post("/api/opportunities/arbitrage")
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
    resolved_uid = str(web_user.get("id") if web_user and web_user.get("id") else (payload.user_id or "guest_web_user")).strip()

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
    resolved_uid = str(web_user.get("id") if web_user and web_user.get("id") else (payload.user_id or "guest_web_user")).strip()

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
# Search Autocomplete Suggestion Gateway
# ==============================================================================
@router.get("/api/suggest")
async def api_suggest(q: str = ""):
    """Returns ticker autocomplete suggestions with caching headers."""
    if not q or len(q.strip()) < 2:
        return json_response_with_cache({"suggestions": []})
    return json_response_with_cache({"suggestions": get_ticker_suggestions(q.strip())})
