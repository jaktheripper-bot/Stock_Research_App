"""
Live Security-Linked Net Real Post-Tax Purchasing Power Bridge
==============================================================
Computes Finance Act 2024 post-tax & post-CPI real yields directly on live
tracked Corporate Debt ISINs, REIT/InvIT Sec 115UA distributions, and SGBs.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("equity_research.core.analysis.live_security_tax_bridge")

from core.db.debt import get_active_debt_securities
from core.db.reits import get_all_reits_invits, get_all_sgb_tranches
from core.db.savings import get_active_savings_instruments
from core.db.sovereign import get_sovereign_yield_curve
from core.analysis.net_real_tax_calculator import (
    calculate_net_real_return,
    DEFAULT_CPI_INFLATION,
    get_default_cpi_inflation,
)
from core.analysis.savings_engine import evaluate_savings_post_tax

HNI_EFFECTIVE_SLABS = {
    "SLAB_0": 0.0,
    "SLAB_10_CESS": 10.40,       # 10% + 4% Health & Education Cess
    "SLAB_15_CESS": 15.60,       # 15% + 4% Health & Education Cess
    "SLAB_20_CESS": 20.80,       # 20% + 4% Health & Education Cess
    "SLAB_30_BASE": 31.20,       # 30% + 4% Cess (Income <= ₹50L)
    "HNI_50L_1CR": 34.32,        # 30% + 10% Surcharge + 4% Cess
    "HNI_1CR_2CR": 35.88,        # 30% + 15% Surcharge + 4% Cess
    "UHNI_ABOVE_2CR": 39.00,     # 30% + 25% Surcharge + 4% Cess (New Regime Cap)
}


def resolve_effective_slab_pct(slab_key_or_pct: Any) -> float:
    """Resolves either a symbolic HNI_EFFECTIVE_SLABS key or a numeric slab %."""
    if slab_key_or_pct is None:
        return 31.20
    key_str = str(slab_key_or_pct).strip().upper()
    if key_str in HNI_EFFECTIVE_SLABS:
        return HNI_EFFECTIVE_SLABS[key_str]
    val = _to_float(slab_key_or_pct, 31.20)
    return max(0.0, min(42.74, val))


def _to_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").replace("%", "").strip()
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _resolve_reit_taxable_share(trust: Dict[str, Any]) -> Optional[float]:
    """
    Derives entity-specific Sec 115UA taxable distribution share strictly from disclosed SPV splits.
    Fails closed (returns None) when neither taxable_interest_share_pct nor tax_breakdown is disclosed.
    """
    if trust.get("taxable_interest_share_pct") is not None:
        return max(0.0, min(1.0, _to_float(trust.get("taxable_interest_share_pct")) / 100.0))

    details = trust.get("details") if isinstance(trust.get("details"), dict) else {}
    tb = details.get("tax_breakdown") if isinstance(details.get("tax_breakdown"), dict) else {}
    if tb:
        int_pct = _to_float(tb.get("interest_pct"), 0.0)
        rent_pct = _to_float(tb.get("rental_pct"), 0.0)
        div_pct = _to_float(tb.get("dividend_pct"), 0.0)
        # Sec 115UA: SPV interest + rental taxed at investor slab; SPV dividend partially exempt depending on 115BAA election; SPV debt amortization = 0% current tax
        eff_share = (int_pct + rent_pct + (0.5 * div_pct)) / 100.0
        return max(0.0, min(1.0, eff_share))

    return None


def compare_live_tracked_yield_instruments(
    slab_key: Any = "SLAB_30_BASE",
    cpi_inflation_pct: Optional[float] = None,
    limit_per_class: int = 5,
    tax_regime: str = "NEW_115BAC",
    is_senior: bool = False,
) -> List[Dict[str, Any]]:
    eff_slab = resolve_effective_slab_pct(slab_key)
    resolved_cpi = _to_float(cpi_inflation_pct, get_default_cpi_inflation()) if cpi_inflation_pct is not None else get_default_cpi_inflation()
    cap = max(1, int(limit_per_class or 5))
    rows: List[Dict[str, Any]] = []

    # 1. Live Corporate Debt / Senior Secured NCDs (Taxed at marginal slab + surcharge + cess)
    debt_items = sorted(
        get_active_debt_securities() or [],
        key=lambda d: _to_float(d.get("ytm_pct") or d.get("coupon_rate_pct"), 0.0),
        reverse=True,
    )
    added_debt = 0
    for sec in debt_items:
        if added_debt >= cap:
            break
        isin = str(sec.get("isin") or "").strip()
        if not isin or "TEST" in isin.upper():
            continue
        ytm = _to_float(sec.get("ytm_pct") or sec.get("coupon_rate_pct"), 0.0)
        if ytm <= 0:
            continue
        calc = calculate_net_real_return(ytm, eff_slab, resolved_cpi)
        rows.append({
            "asset_class": "CORPORATE_DEBT",
            "asset_class_label": "Corporate Bond / NCD",
            "identifier": isin,
            "name": sec.get("instrument_name") or isin,
            "rating": sec.get("credit_rating", "Rated"),
            "dossier_url": f"/debt/{isin}",
            "tax_treatment": f"Sec 56(2) Interest/NCD — {eff_slab:.2f}% effective slab",
            **calc,
        })
        added_debt += 1

    # 2. Live REITs & InvITs (Sec 115UA Pass-Through Waterfall — fail-closed when SPV split undisclosed)
    reit_items = sorted(
        get_all_reits_invits() or [],
        key=lambda t: _to_float(t.get("distribution_yield_pct"), 0.0),
        reverse=True,
    )
    added_reit = 0
    for trust in reit_items:
        if added_reit >= cap:
            break
        gross_yield = _to_float(trust.get("distribution_yield_pct"), 0.0)
        sym = str(trust.get("symbol") or trust.get("ticker") or "").strip()
        if not sym or "TEST" in sym.upper() or gross_yield <= 0:
            continue
        taxable_share = _resolve_reit_taxable_share(trust)
        if taxable_share is None:
            continue
        blended_tax_rate = eff_slab * taxable_share
        calc = calculate_net_real_return(gross_yield, blended_tax_rate, resolved_cpi)
        rows.append({
            "asset_class": "REIT_INVIT",
            "asset_class_label": "SEBI REIT / InvIT",
            "identifier": sym,
            "name": trust.get("name", sym),
            "rating": "SEBI Registered Trust",
            "dossier_url": f"/reits/{sym}",
            "tax_treatment": f"Sec 115UA Waterfall ({blended_tax_rate:.1f}% blended effective tax)",
            **calc,
        })
        added_reit += 1

    # 3. Live Sovereign Gold Bond (SGB) Tranches (Sec 47(viic): 2.5% coupon taxed at slab; redemption capital gains 100% tax-free)
    sgb_items = sorted(
        get_all_sgb_tranches() or [],
        key=lambda s: _to_float(s.get("ytm_annualized_pct"), 0.0),
        reverse=True,
    )
    added_sgb = 0
    for sgb in sgb_items:
        if added_sgb >= cap:
            break
        sym = str(sgb.get("symbol") or "").strip()
        ytm = _to_float(sgb.get("ytm_annualized_pct"), 0.0)
        if not sym or "TEST" in sym.upper() or ytm <= 0:
            continue
        coupon = max(0.0, min(ytm, _to_float(sgb.get("annual_coupon_rate"), 2.5)))
        sgb_blended_tax = eff_slab * (coupon / ytm)
        calc = calculate_net_real_return(ytm, sgb_blended_tax, resolved_cpi)
        rows.append({
            "asset_class": "SGB",
            "asset_class_label": "Sovereign Gold Bond",
            "identifier": sym,
            "name": sgb.get("series_name") or sym,
            "rating": "Sovereign (RBI / GoI)",
            "dossier_url": "/reits",
            "tax_treatment": f"Sec 47(viic) Maturity Exempt ({sgb_blended_tax:.1f}% blended coupon tax)",
            **calc,
        })
        added_sgb += 1

    # 4. Live Sovereign G-Secs / T-Bills (RBI / FBIL Par Yield Curve — do NOT auto-seed assumed curve)
    try:
        sov_items = sorted(
            [
                g
                for g in (get_sovereign_yield_curve(auto_seed=False) or [])
                if not g.get("is_fallback")
                and "FALLBACK" not in str(g.get("source") or "").upper()
                and "STATIC_BASELINE" not in str(g.get("source") or "").upper()
            ],
            key=lambda g: _to_float(g.get("cut_off_yield"), 0.0),
            reverse=True,
        )
    except Exception as sov_err:
        logger.debug("Sovereign yield curve lookup notice in live_security_tax_bridge: %s", sov_err)
        sov_items = []
    added_sov = 0
    for gsec in sov_items:
        if added_sov >= cap:
            break
        tenor = str(gsec.get("tenor_label") or "").strip()
        ytm = _to_float(gsec.get("cut_off_yield"), 0.0)
        if not tenor or "TEST" in tenor.upper() or ytm <= 0:
            continue
        calc = calculate_net_real_return(ytm, eff_slab, resolved_cpi)
        rows.append({
            "asset_class": "SOVEREIGN_GSEC",
            "asset_class_label": "Sovereign G-Sec / T-Bill",
            "identifier": tenor,
            "name": f"GoI Sovereign Benchmark ({tenor.replace('_', ' ')})",
            "rating": "Sovereign (RBI / GoI)",
            "dossier_url": "/sovereign",
            "tax_treatment": f"Sec 56(2) G-Sec Coupon — {eff_slab:.2f}% effective slab",
            **calc,
        })
        added_sov += 1

    # 5. Live Statutory Small Savings, Term Deposits & Retirement Schemes (full HNI surcharge & staleness fidelity)
    try:
        sav_items = [
            s
            for s in get_active_savings_instruments()
            if str((s.get("staleness") or {}).get("status") or "FRESH").upper()
            not in ("STALE_TARIFF", "UNVERIFIED_PROVENANCE")
        ]
        sav_scored = []
        for sv in sav_items:
            ev = evaluate_savings_post_tax(
                sv,
                tax_regime=tax_regime,
                slab_rate_pct=eff_slab,
                effective_tax_rate_pct=eff_slab,
                is_senior=is_senior,
                cpi_inflation_pct=resolved_cpi,
            )
            sav_scored.append((sv, ev))
        sav_scored.sort(key=lambda pair: pair[1]["fisher_real_yield_pct"], reverse=True)
        for sv, ev in sav_scored[:cap]:
            rows.append({
                "asset_class": "SAVINGS_DEPOSIT",
                "asset_class_label": sv.get("category_label", "Fixed Savings & Deposit"),
                "identifier": sv["instrument_id"],
                "name": sv["scheme_name"],
                "rating": sv.get("credit_rating", "DICGC / Sovereign"),
                "dossier_url": f"/savings/{sv['instrument_id']}",
                "tax_treatment": ev["tax_treatment_badge"],
                "nominal_return_pct": ev["gross_apy_pct"],
                "post_tax_nominal_pct": ev["post_tax_yield_pct"],
                "cpi_inflation_pct": resolved_cpi,
                "net_real_return_pct": ev["fisher_real_yield_pct"],
                "tax_drag_pct": round(ev["gross_apy_pct"] - ev["post_tax_yield_pct"], 2),
                "purchasing_power_verdict": "Real Growth" if ev["fisher_real_yield_pct"] > 1.5 else ("Capital Preserved" if ev["fisher_real_yield_pct"] >= 0 else "Negative Real Return"),
            })
    except Exception as sav_err:
        logger.warning("Savings bridge lookup notice in live_security_tax_bridge: %s", sav_err)

    for r in rows:
        r.setdefault("nominal_yield_pct", r.get("nominal_return_pct", 0.0))
        r.setdefault("post_tax_yield_pct", r.get("post_tax_nominal_pct", 0.0))
    rows.sort(key=lambda r: r["net_real_return_pct"], reverse=True)
    return rows

