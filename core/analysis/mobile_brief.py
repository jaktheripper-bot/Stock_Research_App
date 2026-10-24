"""Deterministic Multi-Asset Mobile Brief Compiler (`/m`).

Produces compact, read-only 3-4 line brief cards across:
- 9:00 AM Morning Research Bouquet
- Listed Equities (with 7-pillar status pills & paywall-aware 1-pillar Research Desk chips)
- Mutual Funds, Corporate Debt, REITs/InvITs & Unlisted MSMEs

Strictly deterministic (Gate 4: zero LLM calls on GET), enforces SEBI Safe-Harbor
non-advisory disclosures, and respects Pillar 03 / Pillar 05 deep-dive paywall boundaries.

Zero-hallucination rule: any field missing from the stored record renders as "N/A"
(or the line is omitted). No invented ratings, scores or cycle days.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.analysis.parser import extract_health_matrix, remove_health_matrix_text
from core.analysis.research_bouquet import compile_research_bouquet
from core.db.compliance import MANDATORY_SEBI_DISCLAIMER
from normalizer import clean_ticker

logger = logging.getLogger("equity_research.core.analysis.mobile_brief")

IST = timezone(timedelta(hours=5, minutes=30))
NA = "N/A"
FRESHNESS_UNKNOWN = "Not recorded"

EQUITY_PILLAR_CHIPS: List[Dict[str, Any]] = [
    {"num": "01", "key": "Macro", "label": "Pillar 01 · Macro & Policy", "gated": False,
     "prompt": "Summarize Pillar 01 (Macro & Policy exposure) in 3 concise bullet points."},
    {"num": "02", "key": "Moat", "label": "Pillar 02 · Competitive Moat", "gated": False,
     "prompt": "Summarize Pillar 02 (Competitive Moat & Pricing Power) in 3 concise bullet points."},
    {"num": "03", "key": "Governance", "label": "Pillar 03 · Accounting & Promoters", "gated": True,
     "prompt": "Summarize Pillar 03 (Promoter Quality, Pledging & Accounting Checks) in 3 concise bullet points."},
    {"num": "04", "key": "Diagnostic", "label": "Pillar 04 · Drop Diagnostic", "gated": False,
     "prompt": "Summarize Pillar 04 (Structural vs Temporary Drop Diagnostic) in 3 concise bullet points."},
    {"num": "05", "key": "Valuation", "label": "Pillar 05 · Valuation & Reverse DCF", "gated": True,
     "prompt": "Summarize Pillar 05 (Valuation Multiples & Reverse DCF Implied Growth) in 3 concise bullet points."},
    {"num": "06", "key": "BalanceSheet", "label": "Pillar 06 · Technical & Solvency", "gated": False,
     "prompt": "Summarize Pillar 06 (Technical Trend & Balance Sheet Solvency) in 3 concise bullet points."},
    {"num": "07", "key": "CapitalAllocation", "label": "Pillar 07 · Capital & ESG", "gated": False,
     "prompt": "Summarize Pillar 07 (Capital Allocation & BRSR Governance) in 3 concise bullet points."},
]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _num(value: Any, digits: int = 1, suffix: str = "") -> str:
    """Format a numeric value, or 'N/A' when missing/non-numeric."""
    if not _present(value):
        return NA
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return NA


def _txt(value: Any) -> str:
    return str(value).strip() if _present(value) else NA


def _freshness(value: Any) -> str:
    return str(value).strip() if _present(value) else FRESHNESS_UNKNOWN


def _lines(*candidates: Optional[str]) -> List[str]:
    return [c for c in candidates if c]


# ---------------------------------------------------------------------------
# Equity text extraction
# ---------------------------------------------------------------------------
def _extract_clean_sentences(report_text: str, max_sentences: int = 3) -> List[str]:
    """Extract up to `max_sentences` clean factual sentences from markdown report text."""
    if not report_text:
        return []
    cleaned = remove_health_matrix_text(report_text)
    cleaned = re.sub(r"```.*?```", " ", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"(?m)^#+\s+.*$", " ", cleaned)
    cleaned = re.sub(
        r"\[(?:VERIFIED FACT|CALCULATED METRIC|MODEL INTERPRETATION|UNRESOLVED UNCERTAINTY)[^\]]*\]", "", cleaned
    )
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    results: List[str] = []
    for s in re.split(r"(?<=[.!?])\s+", cleaned):
        s_clean = s.strip(" -•*|")
        if 40 <= len(s_clean) <= 240 and not s_clean.lower().startswith(("table", "factor", "pillar")):
            results.append(s_clean)
            if len(results) >= max_sentences:
                break
    return results


def _extract_top_risk_flag(report_text: str, matrix: Dict[str, str]) -> str:
    """Deterministically extract the primary risk watchpoint from report text or health matrix."""
    if report_text:
        risk_match = re.search(
            r"(?im)(?:countercase|what\s+could\s+go\s+wrong|falsification|key\s+risk|downside\s+trigger|watchpoint)"
            r"[^:\n]*[:\-—]\s*([^\n]{30,220})",
            report_text,
        )
        if risk_match:
            clean_risk = re.sub(r"[*_`#]", "", risk_match.group(1)).strip()
            if clean_risk:
                return clean_risk

    if matrix.get("Governance") in ("Caution", "High Risk"):
        return f"Governance rated {matrix['Governance']} — verify promoter pledging and related-party footnotes."
    if matrix.get("Valuation") in ("Stretched", "Loss-Making"):
        return f"Valuation rated {matrix['Valuation']} — heightened sensitivity to earnings or margin compression."
    if matrix.get("BalanceSheet") in ("Moderate Debt", "High Debt"):
        return f"Balance Sheet rated {matrix['BalanceSheet']} — monitor interest coverage and working capital cycle."
    if matrix.get("Macro") == "Headwinds":
        return "Macro environment shows sector headwinds — track demand elasticity and input cost pass-through."
    return "No explicit risk watchpoint recorded in the stored report; see the full dossier for the countercase."


# ---------------------------------------------------------------------------
# Per-asset compilers
# ---------------------------------------------------------------------------
def _compile_equity(ident: str, is_unlocked: bool) -> Optional[Dict[str, Any]]:
    from bse_master import resolve_bse_scrip_code, resolve_canonical_symbol
    from core.db.reports import get_report_by_ticker

    canonical = resolve_canonical_symbol(clean_ticker(ident))
    row = get_report_by_ticker(canonical)
    if not row:
        return None

    report_text = row.get("report_text") or ""
    matrix = extract_health_matrix(report_text) or {}
    sentences = _extract_clean_sentences(report_text, max_sentences=3)
    if not sentences:
        sentences = ["No narrative summary is available in the stored report; open the full dossier."]

    scrip_code = resolve_bse_scrip_code(canonical) or NA

    pillar_chips = []
    for chip in EQUITY_PILLAR_CHIPS:
        locked = bool(chip["gated"] and not is_unlocked)
        pillar_chips.append({
            "num": chip["num"],
            "key": chip["key"],
            "label": chip["label"],
            "status": "Locked (1 Credit)" if locked else _txt(matrix.get(chip["key"])),
            "locked": locked,
            "prompt": chip["prompt"],
        })

    return {
        "asset_type": "equity",
        "asset_class_token": "equities",
        "asset_id": canonical,
        "title": canonical,
        "subtitle": (
            f"BSE: {scrip_code} · Price: ₹{_txt(row.get('baseline_price'))} · "
            f"P/E: {_txt(row.get('baseline_pe'))} · MCap: {_txt(row.get('baseline_mcap'))}"
        ),
        "headline_score": (
            f"Moat: {_txt(matrix.get('Moat'))} · Solvency: {_txt(matrix.get('BalanceSheet'))} · "
            f"Valuation: {_txt(matrix.get('Valuation'))}"
        ),
        "brief_lines": sentences[:4],
        "top_risk_flag": _extract_top_risk_flag(report_text, matrix),
        "matrix": matrix,
        "pillar_chips": pillar_chips,
        "is_unlocked": is_unlocked,
        "desktop_url": f"/dossier/{canonical}",
        "brief_url": f"/m/equity/{canonical}",
        "last_updated": _freshness(row.get("formatted_date")),
        "sebi_disclaimer": MANDATORY_SEBI_DISCLAIMER,
    }


def _compile_fund(ident: str, is_unlocked: bool) -> Optional[Dict[str, Any]]:
    from core.analysis.mutual_funds_engine import evaluate_mutual_fund_comprehensive
    from core.db.mutual_funds import get_fund_forensic_dossier, get_mutual_fund_scheme

    scheme = get_mutual_fund_scheme(ident)
    if not scheme:
        return None
    code = scheme.get("scheme_code") or ident
    dossier = get_fund_forensic_dossier(code) or {}
    eval_data = evaluate_mutual_fund_comprehensive(code) or {}

    meta = scheme.get("metadata") if isinstance(scheme.get("metadata"), dict) else {}
    lookthrough = eval_data.get("lookthrough") or {}
    fee_drag = eval_data.get("fee_drag") or {}
    active_info = eval_data.get("active_share") or {}

    ter_dir = scheme.get("ter_direct_pct")
    ter_reg = scheme.get("ter_regular_pct")
    ter_spread_bps = fee_drag.get("ter_spread_bps")
    active_share = (
        scheme.get("active_share_pct")
        if _present(scheme.get("active_share_pct"))
        else dossier.get("active_share_pct")
    )
    consistency_3y = meta.get("rolling_consistency_3y_pct")
    sortino = meta.get("sortino_ratio")
    top10_wt = lookthrough.get("top_10_weight_pct") or meta.get("top_10_weight_pct")
    moat = dossier.get("weighted_moat_score")
    health = dossier.get("composite_health_score") or lookthrough.get("composite_health_score")
    pledge = dossier.get("promoter_pledge_exposure_pct")
    aum_cr = scheme.get("aum_crores")
    turnover = scheme.get("portfolio_turnover_ratio_pct")

    fee_line = None
    if _present(ter_dir) and _present(ter_reg) and _present(ter_spread_bps):
        fee_line = (
            f"Direct TER {_num(ter_dir, 2, '%')} vs Regular {_num(ter_reg, 2, '%')} "
            f"({_num(ter_spread_bps, 0, ' bps')} annual commission spread)."
        )
    elif _present(ter_dir):
        fee_line = f"Direct-plan expense ratio: {_num(ter_dir, 2, '%')}."

    mandate_line = None
    if _present(aum_cr) or _present(turnover) or _present(top10_wt):
        mandate_line = (
            f"AUM ₹{_num(aum_cr, 0)} Cr · Annual turnover {_num(turnover, 1, '%')} · "
            f"Top-10 holdings concentration {_num(top10_wt, 1, '%')}."
        )

    quality_line = None
    if _present(moat) or _present(health):
        quality_line = (
            f"Look-through Health Score {_num(health, 1, '/100')} · "
            f"Weighted Moat {_num(moat, 1, '/100')} · "
            f"Promoter pledge exposure {_num(pledge, 2, '%')}."
        )
    elif _present(sortino):
        quality_line = (
            f"Sortino ratio {_num(sortino, 2)} · "
            f"Downside capture {_num(meta.get('downside_capture_ratio'), 1, '%')} vs benchmark {_txt(scheme.get('benchmark_index'))}."
        )

    lines = _lines(fee_line, mandate_line, quality_line) or [
        "Holdings look-through metrics are not yet recorded for this scheme."
    ]

    if active_info.get("is_closet_indexer") or dossier.get("closet_indexer_flag"):
        risk = f"Closet-index alert: active share ({_num(active_share, 1, '%')}) is low relative to the active fee spread."
    elif _present(top10_wt) and float(top10_wt) >= 55.0:
        risk = f"Top-10 holdings account for {_num(top10_wt, 1, '%')} of assets; monitor single-sector concentration and redemption liquidity."
    else:
        risk = f"Benchmark: {_txt(scheme.get('benchmark_index'))} · Risk grade: {_txt(scheme.get('risk_grade'))}. Monitor style drift and cash buffer across drawdowns."

    headline_rhs = (
        f"3Y Consistency: {_num(consistency_3y, 1, '%')}"
        if _present(consistency_3y)
        else f"Health: {_num(health, 1, '/100')}"
    )

    return {
        "asset_type": "fund",
        "asset_class_token": "funds",
        "asset_id": code,
        "title": scheme.get("scheme_name") or code,
        "subtitle": f"{_txt(scheme.get('category'))} · Direct TER: {_num(ter_dir, 2, '%')} · NAV: ₹{_num(scheme.get('nav'), 2)}",
        "headline_score": f"Active Share: {_num(active_share, 1, '%')} · {headline_rhs}",
        "brief_lines": lines,
        "top_risk_flag": risk,
        "matrix": {},
        "pillar_chips": [],
        "is_unlocked": is_unlocked,
        "desktop_url": f"/funds/{code}",
        "brief_url": f"/m/fund/{code}",
        "last_updated": _freshness(scheme.get("last_portfolio_date") or scheme.get("last_updated")),
        "sebi_disclaimer": MANDATORY_SEBI_DISCLAIMER,
    }


def _compile_debt(ident: str, is_unlocked: bool) -> Optional[Dict[str, Any]]:
    from core.db.debt import get_debt_security_by_isin

    sec = get_debt_security_by_isin(ident.upper())
    if not sec:
        return None
    isin = sec.get("isin") or ident.upper()
    rating = _txt(sec.get("credit_rating"))
    agency = _txt(sec.get("credit_rating_agency"))
    seniority = _txt(sec.get("seniority_tier")).replace("_", " ").title() if _present(sec.get("seniority_tier")) else NA
    coupon = _num(sec.get("coupon_rate_pct"), 2, "%")
    ytm = _num(sec.get("ytm_pct"), 2, "%")
    cover = sec.get("asset_cover_ratio")

    lines = _lines(
        f"Coupon {coupon} ({_txt(sec.get('coupon_frequency'))}), seniority: {seniority}.",
        f"Rated {rating} by {agency}; yield to maturity {ytm}.",
        f"Maturity: {_txt(sec.get('maturity_date'))}; asset cover ratio: {_num(cover, 2, 'x')}.",
    )

    return {
        "asset_type": "debt",
        "asset_class_token": "debt",
        "asset_id": isin,
        "title": sec.get("instrument_name") or sec.get("ticker") or isin,
        "subtitle": f"ISIN: {isin} · Rating: {rating} · YTM: {ytm}",
        "headline_score": f"Rating: {rating} · Seniority: {seniority} · YTM: {ytm}",
        "brief_lines": lines,
        "top_risk_flag": "Listed bonds can trade thinly; spreads may widen if the issuer's credit rating is downgraded.",
        "matrix": {},
        "pillar_chips": [],
        "is_unlocked": is_unlocked,
        "desktop_url": f"/debt/{isin}",
        "brief_url": f"/m/debt/{isin}",
        "last_updated": _freshness(sec.get("last_updated")),
        "sebi_disclaimer": MANDATORY_SEBI_DISCLAIMER,
    }


def _compile_reit(ident: str, is_unlocked: bool) -> Optional[Dict[str, Any]]:
    from core.db.reits import get_reit_by_symbol

    item = get_reit_by_symbol(ident)
    if not item:
        return None
    symbol = item.get("symbol") or ident.upper()
    details = item.get("details") if isinstance(item.get("details"), dict) else {}

    price, nav = item.get("current_price"), item.get("nav_per_unit")
    try:
        p_nav = f"{float(price) / float(nav):.2f}x" if _present(price) and _present(nav) and float(nav) > 0 else NA
    except (TypeError, ValueError):
        p_nav = NA
    disc = item.get("discount_to_nav_pct")
    yld = _num(item.get("distribution_yield_pct"), 2, "%")
    occ = _num(item.get("occupancy_pct"), 1, "%")
    ltv = _num(item.get("ltv_ratio_pct"), 1, "%")
    sponsor = _num(item.get("sponsor_holding_pct"), 1, "%")

    asset_desc = details.get("asset_class")
    area_msf = details.get("leasable_area_msf")
    tenants = details.get("top_tenants") if isinstance(details.get("top_tenants"), list) else []

    portfolio_line = None
    if _present(asset_desc) or _present(area_msf):
        tenant_str = f" · Key tenants: {', '.join(str(t) for t in tenants[:3])}" if tenants else ""
        portfolio_line = (
            f"Portfolio: {_txt(asset_desc)}"
            f"{f' ({_num(area_msf, 1)} msf)' if _present(area_msf) else ''}{tenant_str}."
        )

    lines = _lines(
        f"Price ₹{_num(price, 2)} vs NAV ₹{_num(nav, 2)}/unit ({p_nav}, {_num(disc, 1, '%')} vs NAV) · Occupancy {occ}.",
        f"Distribution yield {yld} · NDCF payout purity {_num(item.get('ndcf_payout_purity_pct'), 1, '%')} · Sponsor holding {sponsor}.",
        f"Consolidated LTV {ltv} · Weighted average lease expiry (WALE) {_num(item.get('wale_years'), 1, ' yrs')}.",
        portfolio_line,
    )

    return {
        "asset_type": "reit",
        "asset_class_token": "reits",
        "asset_id": symbol,
        "title": item.get("name") or symbol,
        "subtitle": f"{_txt(item.get('structure_type')).replace('_', ' ')} · Yield: {yld} · Price: ₹{_num(price, 2)}",
        "headline_score": f"Yield: {yld} · P/NAV: {p_nav} · Occupancy: {occ}",
        "brief_lines": lines[:4],
        "top_risk_flag": f"Refinancing sensitivity at {ltv} consolidated LTV and lease rollovers across {_num(item.get('wale_years'), 1, ' yr')} WALE.",
        "matrix": {},
        "pillar_chips": [],
        "is_unlocked": is_unlocked,
        "desktop_url": f"/reits/{symbol}",
        "brief_url": f"/m/reit/{symbol}",
        "last_updated": _freshness(item.get("updated_at") or item.get("last_updated")),
        "sebi_disclaimer": MANDATORY_SEBI_DISCLAIMER,
    }


def _compile_msme(ident: str, is_unlocked: bool) -> Optional[Dict[str, Any]]:
    from core.msme.router import get_msme_detail

    d = get_msme_detail(ident)
    if not d:
        return None
    uin = d.get("uin") or ident.upper()
    wc = d.get("pillar_1_working_capital") or {}
    sc = d.get("pillar_2_supply_chain") or {}
    solv = d.get("pillar_3_solvency") or {}
    moat = d.get("pillar_4_moat") or {}
    turnover = d.get("annual_turnover")
    emp = d.get("employee_count")
    place = ", ".join(x for x in (d.get("city"), d.get("state")) if _present(x)) or NA

    fragility_list = moat.get("fragility_vectors") if isinstance(moat.get("fragility_vectors"), list) else []
    primary_fragility = fragility_list[0] if fragility_list else "unlisted private enterprise illiquidity"

    lines = _lines(
        f"Verified Udyam registry: {_txt(d.get('tier'))} enterprise in {place} · "
        f"Turnover ₹{_num(turnover, 1)} Cr · Employees: {_txt(emp)} (₹{_num(moat.get('rev_per_emp_lakhs'), 1)}L/employee).",
        f"Cluster benchmark ({_txt(sc.get('cluster_type'))}): median net CCC {_num(wc.get('net_ccc_days'), 0, ' days')} "
        f"(DSO {_num(wc.get('dso_days'), 0, 'd')} / DIO {_num(wc.get('dio_days'), 0, 'd')} / DPO {_num(wc.get('dpo_days'), 0, 'd')}, "
        f"{_txt(wc.get('stress_level'))} working-capital load).",
        f"Sector-benchmark solvency: est. EBITDA margin {_num(solv.get('ebitda_margin_pct'), 1, '%')}, "
        f"ICR {_num(solv.get('interest_coverage_ratio'), 2, 'x')} ({_txt(solv.get('icr_health'))}), "
        f"heuristic Moat {_num(moat.get('moat_score'), 0, '/100')} ({_txt(moat.get('moat_tier'))}).",
    )

    return {
        "asset_type": "msme",
        "asset_class_token": "msme",
        "asset_id": uin,
        "title": d.get("name") or uin,
        "subtitle": f"UIN: {uin} · {_txt(d.get('tier'))} Enterprise · {place}",
        "headline_score": (
            f"Turnover: ₹{_num(turnover, 1)} Cr · Moat (heuristic): {_num(moat.get('moat_score'), 0, '/100')} · "
            f"CCC (sector median): {_num(wc.get('net_ccc_days'), 0, 'd')}"
        ),
        "brief_lines": lines,
        "top_risk_flag": f"Sector fragility benchmark: {primary_fragility}. Unlisted enterprise with no public secondary exit.",
        "matrix": {},
        "pillar_chips": [],
        "is_unlocked": is_unlocked,
        "desktop_url": f"/msme/{uin}",
        "brief_url": f"/m/msme/{uin}",
        "last_updated": _freshness(d.get("last_updated")),
        "sebi_disclaimer": MANDATORY_SEBI_DISCLAIMER,
    }


_COMPILERS = (
    (("equity", "equities", "stock"), _compile_equity),
    (("fund", "funds", "mf"), _compile_fund),
    (("debt", "bond", "ncd"), _compile_debt),
    (("reit", "reits", "invit"), _compile_reit),
    (("msme", "sme"), _compile_msme),
)


def compile_asset_mobile_brief(
    asset_type: str,
    asset_id: str,
    is_unlocked: bool = False,
) -> Optional[Dict[str, Any]]:
    """Compile a deterministic single-asset mobile brief across the 5 supported asset classes."""
    kind = (asset_type or "equity").strip().lower()
    ident = (asset_id or "").strip()
    if not ident:
        return None
    for aliases, compiler in _COMPILERS:
        if kind in aliases:
            try:
                return compiler(ident, is_unlocked)
            except Exception as e:
                logger.error("Mobile brief compile failed for %s/%s: %s", kind, ident, e)
                return None
    return None


def compile_morning_hub_brief(edition_date: Optional[str] = None) -> Dict[str, Any]:
    """Compile the `/m` pocket hub combining the 9:00 AM Research Bouquet and quick-access asset briefs."""
    target_date = edition_date or datetime.now(IST).strftime("%Y-%m-%d")
    bouquet = compile_research_bouquet(target_date) or {}
    return {
        "edition_date": bouquet.get("edition_date", target_date),
        "formatted_date": bouquet.get("formatted_date", target_date),
        "bouquet": bouquet,
        "sebi_disclaimer": MANDATORY_SEBI_DISCLAIMER,
    }
