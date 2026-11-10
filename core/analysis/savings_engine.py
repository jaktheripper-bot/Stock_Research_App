"""Core analytical engine for Indian Fixed Savings, Term Deposits, Statutory Small Savings,
High-Yield Savings Accounts, and Statutory Retirement/Pension Instruments.

Implements:
1. Finance Act 2025 Dual-Regime Tax Normalization (`NEW_115BAC` default vs `OLD_REGIME`),
   including Section 87A ₹12L rebate, 25% vs 37% slab surcharge caps, 15% surcharge cap on
   Sec 111A/112A capital gains, Sec 80C / 80CCD(1B) / 80CCD(2) / 80TTA / 80TTB rules,
   Sec 194A TDS cash-flow drag (₹50k regular / ₹1L senior bank vs ₹10k NBFC) & Form 15G/15H,
   NSC 4-year reinvested 80C + Year-5 taxable accrual, EPF ₹2.5L Sec 10(12) proviso split,
   and NPS 60/40 normal vs 20/80 premature exit waterfall.
2. Exact Fisher Real-Return Deflation anchored to `get_live_macro_anchors()`.
3. DICGC ₹5,00,000 Principal + Accrued-Interest Split & Multi-Bank Charter Ladder Solver
   under DICGC Act 1961 Section 16(1) ("in the same right and capacity") with RBI Sovereign Overflow.
4. FD ↔ Exchange-Traded Corporate NCD ↔ Listed Equity Contagion & Seniority Inversion Bridge
   (excluding AT1 Perpetual & Tier-2 Subordinated bonds from senior comparisons, enforcing BFSI
   metric hygiene, and capping unsecured 0%-DICGC NBFC FDs at <= 72/100 safety posture).
5. Short-Term Cash-Park & Pure Sec 112A Arbitrage Comparator Sleeve (excluding Arbitrage FoFs).
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from core.db.connection import get_db_connection, get_placeholder
from core.db.savings import (
    SAVINGS_CATEGORY_LABELS,
    get_active_savings_instruments,
    get_active_tax_rule_version,
    get_savings_instrument_by_id,
    get_savings_rate_history,
)
from core.db.sovereign import get_etf_matrix, get_live_macro_anchors, get_sovereign_yield_curve

logger = logging.getLogger("equity_research.core.analysis.savings_engine")

DICGC_STATUTORY_LIMIT_INR: float = 500000.0
CORPORATE_FD_SAFETY_CAP: int = 72
RBI_DSIB_TICKERS = frozenset({"SBIN", "HDFCBANK", "ICICIBANK"})

# Bidirectional ticker alias map bridging Equity symbols <-> NSE/BSE Debt issuer symbols
ISSUER_DEBT_TICKER_ALIASES: Dict[str, Tuple[str, ...]] = {
    "BAJFINANCE": ("BAJFINANCE", "BAJAJFIN"),
    "BAJAJFIN": ("BAJFINANCE", "BAJAJFIN"),
    "M&MFIN": ("M&MFIN", "MMFSL", "MAHINDRAFIN"),
    "MMFSL": ("M&MFIN", "MMFSL", "MAHINDRAFIN"),
    "AUBANK": ("AUBANK", "AUFINBANK"),
    "SHRIRAMFIN": ("SHRIRAMFIN", "STFC"),
    "SUNDARMFIN": ("SUNDARMFIN", "SUNDARAMFIN"),
    "MUTHOOTFIN": ("MUTHOOTFIN",),
    "CHOLAFIN": ("CHOLAFIN", "CIFCL"),
    "LICHSGFIN": ("LICHSGFIN", "LICHFL"),
    "PNBHOUSING": ("PNBHOUSING", "PNBHFL"),
    "SBIN": ("SBIN", "SBI"),
    "HDFCBANK": ("HDFCBANK", "HDFC"),
    "ICICIBANK": ("ICICIBANK", "ICICI"),
    "KOTAKBANK": ("KOTAKBANK", "KOTAK"),
    "AXISBANK": ("AXISBANK", "AXIS"),
    "IDFCFIRSTB": ("IDFCFIRSTB", "IDFCFIRST"),
    "INDUSINDBK": ("INDUSINDBK", "INDUSIND"),
    "FEDERALBNK": ("FEDERALBNK", "FEDERAL"),
}

_SUBORDINATED_OR_AT1_RE = re.compile(
    r"(?:PERPETUAL|AT1|TIER[_\s-]*1|TIER[_\s-]*2|SUBORDINAT)",
    re.IGNORECASE,
)
_PURE_ARBITRAGE_RE = re.compile(r"\bARBITRAGE\b", re.IGNORECASE)
_ARBITRAGE_FOF_EXCLUSION_RE = re.compile(
    r"\b(?:FOF|FUND\s+OF\s+FUNDS?|INCOME\s+PLUS\s+ARBITRAGE|DEBT\s+PLUS\s+ARBITRAGE|HYBRID\s+FOF)\b",
    re.IGNORECASE,
)
_CASH_DEBT_MF_RE = re.compile(
    r"\b(?:OVERNIGHT|LIQUID|ULTRA\s*SHORT|MONEY\s+MARKET)\b",
    re.IGNORECASE,
)
_CASH_DEBT_ETF_RE = re.compile(
    r"\b(?:LIQUID|OVERNIGHT|GILT|BHARAT\s*BOND|SDL|TARGET|1D\s*RATE|NIFTY\s*1D)\b",
    re.IGNORECASE,
)
_BFSI_ISSUER_TYPES = frozenset(
    {
        "PUBLIC_SECTOR_BANK",
        "PRIVATE_SECTOR_BANK",
        "SMALL_FINANCE_BANK",
        "DEPOSIT_TAKING_NBFC",
        "HOUSING_FINANCE_COMPANY",
    }
)


def is_pure_sec_112a_arbitrage_fund(
    broad_category: Optional[str],
    category: Optional[str],
    scheme_name: Optional[str],
) -> bool:
    """Strict L1 guard distinguishing pure >=65% hedged-equity Sec 112A Arbitrage MFs
    from Arbitrage FoFs / Income-plus-Arbitrage FoFs.
    """
    broad = str(broad_category or "").strip().upper()
    combined = f"{scheme_name or ''} {category or ''}"
    if broad != "HYBRID":
        return False
    if not _PURE_ARBITRAGE_RE.search(combined):
        return False
    if _ARBITRAGE_FOF_EXCLUSION_RE.search(combined):
        return False
    return True


def compute_fisher_real_yield_pct(post_tax_yield_pct: float, cpi_inflation_pct: float) -> float:
    """Exact Fisher real return: ((1 + r_net) / (1 + cpi) - 1) * 100."""
    denom = 1.0 + (float(cpi_inflation_pct) / 100.0)
    if denom <= 0:
        return round(float(post_tax_yield_pct) - float(cpi_inflation_pct), 2)
    real = (((1.0 + (float(post_tax_yield_pct) / 100.0)) / denom) - 1.0) * 100.0
    return round(real, 2)


def _compounding_periods_per_year(compounding_freq: str) -> Tuple[int, bool]:
    """Returns (periods_per_year, is_reinvested_cumulative)."""
    freq = str(compounding_freq or "QUARTERLY").strip().upper()
    if freq == "MONTHLY_COMPOUNDED":
        return 12, True
    if freq == "QUARTERLY":
        return 4, True
    if freq == "SEMI_ANNUAL":
        return 2, True
    if freq == "ANNUAL":
        return 1, True
    if freq in ("MONTHLY_PAYOUT", "MONTHLY_CREDIT"):
        return 12, False
    if freq == "QUARTERLY_PAYOUT":
        return 4, False
    if freq == "SEMI_ANNUAL_PAYOUT":
        return 2, False
    return 1, False


def compute_effective_annual_gross_yield_pct(nominal_rate_pct: float, compounding_freq: str) -> float:
    """Converts nominal annual coupon rate into effective annualized gross APY."""
    r = float(nominal_rate_pct) / 100.0
    if r <= 0:
        return 0.0
    n, is_cumulative = _compounding_periods_per_year(compounding_freq)
    if not is_cumulative or n <= 1:
        return round(float(nominal_rate_pct), 2)
    apy = ((1.0 + (r / float(n))) ** n - 1.0) * 100.0
    return round(apy, 2)


SUPPORTED_DICGC_PAYOUT_MODES: Tuple[str, ...] = (
    "CUMULATIVE",
    "QUARTERLY_PAYOUT",
    "MONTHLY_PAYOUT",
)
DICGC_MIN_CORPUS_INR: float = 1000.0
DICGC_MAX_CORPUS_INR: float = 500000000.0
DICGC_MIN_TENURE_MONTHS: int = 3
DICGC_MAX_TENURE_MONTHS: int = 120
SEC_17_2_VII_EMPLOYER_CAP_INR: float = 750000.0


def _is_instrument_tariff_usable(instrument: Dict[str, Any]) -> bool:
    status = str((instrument.get("staleness") or {}).get("status") or "FRESH").upper()
    return status not in ("STALE_TARIFF", "UNVERIFIED_PROVENANCE")


def resolve_dynamic_instrument_rate(
    instrument: Dict[str, Any],
    macro_anchors: Optional[Dict[str, Any]] = None,
    nsc_rate_override: Optional[float] = None,
    principal_inr: Optional[float] = None,
) -> Dict[str, Any]:
    """Resolves dynamic/pegged nominal rates and progressive HYSA balance-slab tiers."""
    anchors = macro_anchors or get_live_macro_anchors()
    rate_type = str(instrument.get("rate_type") or "FIXED").upper()
    benchmark = str(instrument.get("floating_benchmark") or "").upper()
    spread_pct = float(instrument.get("floating_spread_bps") or 0.0) / 100.0
    base_rate = float(instrument.get("base_rate_pct") or 0.0)
    stale_status = str((instrument.get("staleness") or {}).get("status") or "FRESH").upper()

    if rate_type == "FLOATING_PEGGED" and benchmark == "SAV-NSC":
        if nsc_rate_override is not None:
            nsc_rate = float(nsc_rate_override)
        else:
            nsc_inst = get_savings_instrument_by_id("SAV-NSC")
            nsc_rate = float(nsc_inst["base_rate_pct"]) if nsc_inst else 7.70
        resolved = round(nsc_rate + spread_pct, 2)
        return {
            "nominal_base_rate_pct": resolved,
            "headline_slab_rate_pct": resolved,
            "rate_formula_note": f"[CALCULATED METRIC] Pegged at SAV-NSC ({nsc_rate:.2f}%) + {int(round(spread_pct * 100))} bps",
        }

    if rate_type == "MARKET_LINKED_NAV" and benchmark in ("10Y_GSEC", "NPS_BENCHMARK_BLEND"):
        gsec_10y = float(anchors.get("gsec_10y_pct", 7.12))
        gsec_qualifier = (
            "unverified fallback 10Y G-Sec anchor"
            if anchors.get("gsec_10y_is_fallback")
            else "live 10Y G-Sec"
        )
        resolved = round(gsec_10y + spread_pct, 2)
        return {
            "nominal_base_rate_pct": resolved,
            "headline_slab_rate_pct": resolved,
            "rate_formula_note": (
                f"[MODEL INTERPRETATION] Market-linked NAV benchmarked to {gsec_qualifier} ({gsec_10y:.2f}%) "
                f"+ {int(round(spread_pct * 100))} bps asset-mix risk premium (not a guaranteed coupon)"
            ),
        }

    notes = instrument.get("notes") or {}
    if not isinstance(notes, dict):
        try:
            notes = json.loads(instrument.get("notes_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Malformed notes_json on savings instrument %s: %s", instrument.get("instrument_id"), exc)
            notes = {}

    # Progressive Savings Account balance-slab calculation (e.g. <= ₹5L tier vs > ₹5L marginal tier)
    tier_up_to_5l = notes.get("dicgc_slab_rate_up_to_5l_pct")
    if (
        str(instrument.get("category") or "").upper() == "HIGH_YIELD_SAVINGS"
        and tier_up_to_5l is not None
        and principal_inr is not None
        and float(principal_inr) > 0
    ):
        p_amt = float(principal_inr)
        tier1_rate = float(tier_up_to_5l)
        tier1_bal = min(p_amt, DICGC_STATUTORY_LIMIT_INR)
        excess_bal = max(0.0, p_amt - DICGC_STATUTORY_LIMIT_INR)
        blended = ((tier1_bal * tier1_rate) + (excess_bal * base_rate)) / p_amt
        prefix = "[CALCULATED METRIC]" if stale_status == "FRESH" else "[MODEL INTERPRETATION]"
        return {
            "nominal_base_rate_pct": round(blended, 4),
            "headline_slab_rate_pct": round(base_rate, 2),
            "rate_formula_note": (
                f"{prefix} Progressive savings balance slab on ₹{p_amt:,.0f}: "
                f"{tier1_rate:.2f}% up to ₹5,00,000 and {base_rate:.2f}% on balance above ₹5,00,000 "
                f"(blended {blended:.2f}%)"
            ),
        }

    epistemic_tag = (
        "[VERIFIED FACT]"
        if stale_status in ("FRESH", "REVIEW_DUE")
        else "[MODEL INTERPRETATION]"
    )
    return {
        "nominal_base_rate_pct": round(base_rate, 2),
        "headline_slab_rate_pct": round(base_rate, 2),
        "rate_formula_note": f"{epistemic_tag} Published tariff / statutory notification ({instrument.get('effective_from')})",
    }


def resolve_effective_tax_parameters(
    tax_regime: str = "NEW_115BAC",
    slab_rate_pct: float = 30.0,
    surcharge_rate_pct: float = 0.0,
    annual_taxable_income_inr: Optional[float] = None,
    rule_version: Optional[str] = None,
    *,
    effective_tax_rate_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Computes effective marginal tax rates under Finance Act 2025 New vs Old Regime.

    Supports both:
    1. Base slab (`0..30%`) + explicit surcharge (`0..37%`), AND
    2. Direct effective cess/surcharge-inclusive HNI tax inputs (`31.2%`, `34.32%`, `35.88%`,
       `39.0%` New Regime cap, `42.744%` Old Regime cap) passed via `effective_tax_rate_pct`
       or `slab_rate_pct > 30.0` (when `surcharge_rate_pct == 0`).
    """
    tax_doc = get_active_tax_rule_version(rule_version)
    rules = tax_doc.get("rules") or {}
    cess_pct = float(rules.get("cess_pct", 4.0))
    cess_mult = 1.0 + (cess_pct / 100.0)

    regime_clean = str(tax_regime or "NEW_115BAC").strip().upper()
    if regime_clean not in ("NEW_115BAC", "OLD_REGIME"):
        regime_clean = "NEW_115BAC"

    regime_cfg = (
        rules.get("new_regime_115bac", {})
        if regime_clean == "NEW_115BAC"
        else rules.get("old_regime", {})
    )
    max_slab_surcharge = float(regime_cfg.get("max_surcharge_slab_pct", 25.0 if regime_clean == "NEW_115BAC" else 37.0))
    max_cg_surcharge = float(regime_cfg.get("max_surcharge_capital_gains_111a_112a_pct", 15.0))

    raw_slab_input = max(0.0, float(slab_rate_pct or 0.0))
    raw_surcharge_input = max(0.0, float(surcharge_rate_pct or 0.0))

    if effective_tax_rate_pct is not None or (raw_slab_input > 30.0 and raw_surcharge_input == 0.0):
        target_eff = max(0.0, float(effective_tax_rate_pct if effective_tax_rate_pct is not None else raw_slab_input))
        max_eff_slab = round(30.0 * (1.0 + max_slab_surcharge / 100.0) * cess_mult, 4)
        clamped_eff = min(target_eff, max_eff_slab)
        top_no_surcharge_eff = 30.0 * cess_mult  # 31.20%
        if clamped_eff <= 0.0:
            base_slab = 0.0
            implied_surcharge = 0.0
        elif clamped_eff >= top_no_surcharge_eff - 1e-6:
            base_slab = 30.0
            implied_surcharge = max(0.0, ((clamped_eff / top_no_surcharge_eff) - 1.0) * 100.0)
        else:
            base_slab = round(clamped_eff / cess_mult, 4)
            implied_surcharge = 0.0
        applied_slab_surcharge = round(min(implied_surcharge, max_slab_surcharge), 4)
        applied_cg_surcharge = round(min(implied_surcharge, max_cg_surcharge), 4)
    else:
        base_slab = min(raw_slab_input, 30.0)
        applied_slab_surcharge = min(raw_surcharge_input, max_slab_surcharge)
        applied_cg_surcharge = min(raw_surcharge_input, max_cg_surcharge)

    sec_87a_limit = float(regime_cfg.get("sec_87a_rebate_income_limit_inr", 1200000.0 if regime_clean == "NEW_115BAC" else 500000.0))
    sec_87a_applied = False
    if annual_taxable_income_inr is not None and float(annual_taxable_income_inr) <= sec_87a_limit:
        base_slab = 0.0
        applied_slab_surcharge = 0.0
        applied_cg_surcharge = 0.0
        sec_87a_applied = True

    eff_slab_pct = round(base_slab * (1.0 + applied_slab_surcharge / 100.0) * cess_mult, 4)
    eff_ltcg_112a_pct = round(12.5 * (1.0 + applied_cg_surcharge / 100.0) * cess_mult, 4)
    eff_stcg_111a_pct = round(20.0 * (1.0 + applied_cg_surcharge / 100.0) * cess_mult, 4)

    return {
        "rule_version": tax_doc.get("rule_version", "FY2025_26_FA2025"),
        "finance_act_label": tax_doc.get("finance_act_label", "Finance Act 2025"),
        "tax_regime": regime_clean,
        "base_slab_pct": base_slab,
        "surcharge_slab_pct": applied_slab_surcharge,
        "surcharge_cg_111a_112a_pct": applied_cg_surcharge,
        "cess_pct": cess_pct,
        "effective_slab_rate_pct": eff_slab_pct,
        "effective_ltcg_112a_rate_pct": eff_ltcg_112a_pct,
        "effective_stcg_111a_rate_pct": eff_stcg_111a_pct,
        "sec_87a_rebate_applied": sec_87a_applied,
        "allows_80c": bool(regime_cfg.get("allows_80c", regime_clean == "OLD_REGIME")),
        "allows_80tta": bool(regime_cfg.get("allows_80tta", regime_clean == "OLD_REGIME")),
        "allows_80ttb": bool(regime_cfg.get("allows_80ttb", regime_clean == "OLD_REGIME")),
        "allows_80ccd_1b": bool(regime_cfg.get("allows_80ccd_1b", regime_clean == "OLD_REGIME")),
        "allows_80ccd_2_employer_pct": float(regime_cfg.get("allows_80ccd_2_employer_pct", 14.0 if regime_clean == "NEW_115BAC" else 10.0)),
    }


def _amortize_upfront_deduction_irr_pct(
    coupon_post_tax_yield_pct: float,
    invested_principal_inr: float,
    upfront_tax_saved_inr: float,
    horizon_years: float,
) -> float:
    """Computes exact multi-year post-tax IRR incorporating Year-0 Chapter VI-A tax refund."""
    if upfront_tax_saved_inr <= 0.0 or invested_principal_inr <= 0.0 or horizon_years <= 0.0:
        return round(coupon_post_tax_yield_pct, 2)
    net_outlay = max(1.0, invested_principal_inr - min(upfront_tax_saved_inr, invested_principal_inr * 0.90))
    terminal_wealth = invested_principal_inr * ((1.0 + (coupon_post_tax_yield_pct / 100.0)) ** horizon_years)
    irr = ((terminal_wealth / net_outlay) ** (1.0 / horizon_years) - 1.0) * 100.0
    return round(irr, 2)


def evaluate_savings_post_tax(
    instrument: Dict[str, Any],
    *,
    tax_regime: str = "NEW_115BAC",
    slab_rate_pct: float = 30.0,
    surcharge_rate_pct: float = 0.0,
    effective_tax_rate_pct: Optional[float] = None,
    is_senior: bool = False,
    cpi_inflation_pct: Optional[float] = None,
    principal_inr: float = 500000.0,
    annual_contribution_inr: Optional[float] = None,
    has_employer_epf: bool = True,
    service_years: int = 5,
    premature_exit: bool = False,
    is_govt_employee: bool = False,
    is_joint_account: bool = False,
    basic_salary_inr: Optional[float] = None,
    employer_nps_contribution_inr: float = 0.0,
    employer_epf_contribution_inr: float = 0.0,
    sec_80c_already_used_inr: float = 0.0,
    claim_upfront_deduction: bool = True,
    holding_years: Optional[float] = None,
    annual_taxable_income_inr: Optional[float] = None,
    macro_anchors: Optional[Dict[str, Any]] = None,
    nsc_rate_override: Optional[float] = None,
) -> Dict[str, Any]:
    """Computes pre-tax APY, regime-accurate post-tax yield (including Sec 80C / 80CCD(1B) /
    80CCD(2) / 10(15)(i) / 80TTA / 80TTB / Sec 17(2)(vii) / PFRDA & EPFO exit rules),
    Sec 194A / 192A TDS drag, and exact Fisher real yield.
    """
    anchors = macro_anchors or get_live_macro_anchors()
    cpi = float(cpi_inflation_pct) if cpi_inflation_pct is not None else float(anchors["cpi_inflation_pct"])
    gsec_10y = float(anchors["gsec_10y_pct"])

    tax_params = resolve_effective_tax_parameters(
        tax_regime=tax_regime,
        slab_rate_pct=slab_rate_pct,
        surcharge_rate_pct=surcharge_rate_pct,
        annual_taxable_income_inr=annual_taxable_income_inr,
        effective_tax_rate_pct=effective_tax_rate_pct,
    )
    eff_slab_pct = tax_params["effective_slab_rate_pct"]
    t_rate = eff_slab_pct / 100.0

    raw_principal = max(1000.0, float(principal_inr or 500000.0))
    max_inv = instrument.get("max_investment_inr")
    inst_id = str(instrument.get("instrument_id") or "").upper()
    # Respect statutory annual deposit ceilings on PPF / SSY (₹1.50L/yr) when modeling principal
    if max_inv is not None and inst_id in ("SAV-PPF", "SAV-SSY"):
        principal = min(raw_principal, float(max_inv))
    else:
        principal = raw_principal

    dyn = resolve_dynamic_instrument_rate(
        instrument,
        macro_anchors=anchors,
        nsc_rate_override=nsc_rate_override,
        principal_inr=principal,
    )
    nominal_rate = float(dyn["nominal_base_rate_pct"])
    senior_bonus_pct = (float(instrument.get("senior_citizen_bonus_bps") or 0.0) / 100.0) if is_senior else 0.0
    applicable_nominal_pct = round(nominal_rate + senior_bonus_pct, 4)
    gross_apy_pct = compute_effective_annual_gross_yield_pct(
        applicable_nominal_pct,
        str(instrument.get("compounding_freq") or "QUARTERLY"),
    )

    category = str(instrument.get("category") or "").upper()
    taxability = str(instrument.get("interest_taxability") or "SLAB_TAXABLE").upper()
    annual_gross_interest_inr = round(principal * (gross_apy_pct / 100.0), 2)

    deduction_shield_inr = 0.0
    upfront_deduction_claimed_inr = 0.0
    upfront_tax_saved_inr = 0.0
    remaining_80c_headroom = max(0.0, 150000.0 - max(0.0, float(sec_80c_already_used_inr or 0.0)))
    lock_in_months = int(instrument.get("lock_in_months") or instrument.get("tenure_max_months") or 60)
    deduction_horizon_years = max(1.0, float(lock_in_months) / 12.0)

    tax_treatment_badge = "Slab Taxable"
    tax_statute_note = ""
    epf_premature_tds_triggered = False

    if taxability == "EEE_EXEMPT":
        coupon_post_tax_yield_pct = gross_apy_pct
        effective_tax_rate_pct_out = 0.0
        if tax_params["allows_80c"] and instrument.get("tax_section_80c_eligible") and claim_upfront_deduction:
            upfront_deduction_claimed_inr = min(principal, remaining_80c_headroom)
            upfront_tax_saved_inr = round(upfront_deduction_claimed_inr * t_rate, 2)
        post_tax_yield_pct = _amortize_upfront_deduction_irr_pct(
            coupon_post_tax_yield_pct,
            principal,
            upfront_tax_saved_inr,
            deduction_horizon_years,
        )
        if upfront_tax_saved_inr > 0:
            tax_treatment_badge = f"EEE + Sec 80C Shield (₹{upfront_tax_saved_inr:,.0f} Tax Saved)"
            tax_statute_note = (
                f"100% Exempt-Exempt-Exempt (Sec 10(11)/10(11A)) plus ₹{upfront_deduction_claimed_inr:,.0f} "
                f"Sec 80C upfront deduction saving ₹{upfront_tax_saved_inr:,.0f} at {eff_slab_pct:.2f}% slab "
                f"({coupon_post_tax_yield_pct:.2f}% coupon -> {post_tax_yield_pct:.2f}% effective IRR over {deduction_horizon_years:.0f}Y)."
            )
        elif tax_params["allows_80c"] and instrument.get("tax_section_80c_eligible"):
            tax_treatment_badge = "EEE Tax-Exempt (Sec 10)"
            tax_statute_note = (
                "100% Exempt-Exempt-Exempt (Sec 10(11)/10(11A)) across both regimes; "
                "Sec 80C headroom already exhausted or not claimed."
            )
        else:
            tax_treatment_badge = "EEE Tax-Exempt (Sec 10)"
            tax_statute_note = (
                "100% Exempt-Exempt-Exempt (Sec 10(11)/10(11A)) under New Regime (Sec 115BAC); "
                "Sec 80C upfront deduction is unavailable in New Regime."
            )

    elif taxability == "NSC_REINVESTED_80C_FINAL_TAXABLE":
        r = applicable_nominal_pct / 100.0
        if tax_params["allows_80c"]:
            # Years 1-4 accrued interest qualifies for deemed Sec 80C reinvestment under Old Regime
            # (within ₹1.50L annual 80C ceiling); Year 5 accrual is slab-taxed at maturity.
            gross_mat = (1.0 + r) ** 5
            yr1_to_4_accrual_per_yr = (((1.0 + r) ** 4) - 1.0) * principal / 4.0
            shielded_reinv_ratio = (
                min(1.0, remaining_80c_headroom / yr1_to_4_accrual_per_yr)
                if yr1_to_4_accrual_per_yr > 0
                else 1.0
            )
            unshielded_yr1_4 = (((1.0 + r) ** 4) - 1.0) * (1.0 - shielded_reinv_ratio)
            yr5_interest = gross_mat - ((1.0 + r) ** 4)
            net_mat = gross_mat - ((yr5_interest + unshielded_yr1_4) * t_rate)
            coupon_post_tax_yield_pct = round(((net_mat ** (1.0 / 5.0)) - 1.0) * 100.0, 2)
            effective_tax_rate_pct_out = round(
                ((gross_apy_pct - coupon_post_tax_yield_pct) / gross_apy_pct * 100.0) if gross_apy_pct > 0 else 0.0,
                2,
            )
            if claim_upfront_deduction and instrument.get("tax_section_80c_eligible"):
                upfront_deduction_claimed_inr = min(principal, remaining_80c_headroom)
                upfront_tax_saved_inr = round(upfront_deduction_claimed_inr * t_rate, 2)
            post_tax_yield_pct = _amortize_upfront_deduction_irr_pct(
                coupon_post_tax_yield_pct,
                principal,
                upfront_tax_saved_inr,
                5.0,
            )
            tax_treatment_badge = "Old Regime: 80C Principal + Yr 1-4 Shielded, Yr 5 Taxed"
            tax_statute_note = (
                f"Under Old Regime, initial deposit (up to ₹1.50L) and Years 1–4 deemed reinvested interest "
                f"qualify under Sec 80C; Year-5 final interest is taxed at {eff_slab_pct:.2f}% slab "
                f"({coupon_post_tax_yield_pct:.2f}% coupon net -> {post_tax_yield_pct:.2f}% with Year-0 80C)."
            )
        else:
            coupon_post_tax_yield_pct = round(gross_apy_pct * (1.0 - t_rate), 2)
            post_tax_yield_pct = coupon_post_tax_yield_pct
            effective_tax_rate_pct_out = round(eff_slab_pct, 2)
            tax_treatment_badge = "New Regime: Fully Slab Taxable (No 80C)"
            tax_statute_note = (
                "Under New Regime (Sec 115BAC), Sec 80C principal & reinvestment deductions are unavailable; "
                f"all 5 years of NSC interest are taxable at {eff_slab_pct:.2f}% marginal slab."
            )

    elif taxability == "EPF_250K_THRESHOLD":
        exempt_cap = 250000.0 if has_employer_epf else 500000.0
        contrib = max(
            1.0,
            float(annual_contribution_inr if annual_contribution_inr is not None else principal),
        )
        emp_total = max(0.0, float(employer_epf_contribution_inr or 0.0) + float(employer_nps_contribution_inr or 0.0))
        employer_excess_perquisite = max(0.0, emp_total - SEC_17_2_VII_EMPLOYER_CAP_INR)

        if int(service_years) < 5:
            # Premature EPF withdrawal before 5 years of continuous service loses Sec 10(12) exemption
            blended_tax_drag = t_rate
            coupon_post_tax_yield_pct = round(gross_apy_pct * (1.0 - blended_tax_drag), 2)
            post_tax_yield_pct = coupon_post_tax_yield_pct
            effective_tax_rate_pct_out = round(eff_slab_pct, 2)
            epf_premature_tds_triggered = contrib >= 50000.0
            tax_treatment_badge = f"Premature EPF (<5Y Service: {eff_slab_pct:.2f}% Slab + Sec 192A TDS)"
            tax_statute_note = (
                f"Withdrawal at {int(service_years)}Y (<5 years continuous salaried service) forfeits Sec 10(12) "
                "exemption; accumulated interest & previously untaxed employer contributions become slab-taxable "
                "with 10% Sec 192A TDS above ₹50,000."
            )
        else:
            exempt_share = min(1.0, exempt_cap / contrib)
            taxable_share = max(0.0, 1.0 - exempt_share)
            perquisite_drag_share = (
                min(0.30, (employer_excess_perquisite / (contrib + emp_total)))
                if employer_excess_perquisite > 0
                else 0.0
            )
            blended_tax_drag = min(1.0, (taxable_share + perquisite_drag_share) * t_rate)
            coupon_post_tax_yield_pct = round(gross_apy_pct * (1.0 - blended_tax_drag), 2)
            effective_tax_rate_pct_out = round(blended_tax_drag * 100.0, 2)

            if tax_params["allows_80c"] and instrument.get("tax_section_80c_eligible") and claim_upfront_deduction:
                upfront_deduction_claimed_inr = min(contrib, remaining_80c_headroom)
                upfront_tax_saved_inr = round(upfront_deduction_claimed_inr * t_rate, 2)
            post_tax_yield_pct = _amortize_upfront_deduction_irr_pct(
                coupon_post_tax_yield_pct,
                contrib,
                upfront_tax_saved_inr,
                max(5.0, float(service_years)),
            )
            if taxable_share > 0 or employer_excess_perquisite > 0:
                tax_treatment_badge = f"Sec 10(12) Split (>{int(exempt_cap // 1000)}k VPF Taxable)"
                tax_statute_note = (
                    f"Finance Act 2021 Sec 10(12) Proviso: interest on employee EPF+VPF contribution up to "
                    f"₹{exempt_cap:,.0f}/yr is exempt; excess ₹{max(0.0, contrib - exempt_cap):,.0f}/yr is taxed at "
                    f"{eff_slab_pct:.2f}% slab."
                    + (
                        f" Employer retirement contribution above ₹7.50L (₹{employer_excess_perquisite:,.0f}) is taxable u/s 17(2)(vii)."
                        if employer_excess_perquisite > 0
                        else ""
                    )
                )
            else:
                tax_treatment_badge = f"EEE Exempt (<= ₹{int(exempt_cap // 1000)}k/yr Cap)"
                tax_statute_note = (
                    f"100% tax-exempt interest under Sec 10(12) for employee EPF+VPF contributions "
                    f"up to ₹{exempt_cap:,.0f}/yr."
                )

    elif taxability == "NPS_60_EXEMPT_40_ANNUITY":
        # Multi-year E-E-T compounding over retirement horizon (normal exit at age 60 ~ 20Y accumulation;
        # premature exit after 10Y minimum lock-in requires 80% taxable annuity).
        normal_horizon_yrs = max(1.0, float(holding_years)) if holding_years is not None else 20.0
        premature_horizon_yrs = (
            max(1.0, float(holding_years)) if holding_years is not None else max(10.0, deduction_horizon_years)
        )
        r = gross_apy_pct / 100.0
        normal_terminal_corpus = principal * ((1.0 + r) ** normal_horizon_yrs)
        premature_terminal_corpus = principal * ((1.0 + r) ** premature_horizon_yrs)
        normal_small_corpus_exempt = normal_terminal_corpus <= 500000.0
        premature_small_corpus_exempt = premature_terminal_corpus <= 250000.0

        normal_annuity_share = 0.0 if normal_small_corpus_exempt else 0.40
        premature_annuity_share = 0.0 if premature_small_corpus_exempt else 0.80

        def _nps_exit_cagr(annuity_share: float, yrs: float) -> float:
            net_terminal_mult = ((1.0 + r) ** yrs) * (1.0 - (annuity_share * t_rate))
            return round(((max(1e-6, net_terminal_mult) ** (1.0 / yrs)) - 1.0) * 100.0, 2)

        normal_cagr_pct = _nps_exit_cagr(normal_annuity_share, normal_horizon_yrs)
        premature_post_tax_pct = _nps_exit_cagr(premature_annuity_share, premature_horizon_yrs)
        horizon_yrs = premature_horizon_yrs if premature_exit else normal_horizon_yrs
        coupon_post_tax_yield_pct = premature_post_tax_pct if premature_exit else normal_cagr_pct
        effective_tax_rate_pct_out = round(
            ((gross_apy_pct - coupon_post_tax_yield_pct) / gross_apy_pct * 100.0) if gross_apy_pct > 0 else 0.0,
            2,
        )

        # Upfront deductions:
        # - Old Regime: Sec 80CCD(1) up to ₹1.50L + exclusive Sec 80CCD(1B) ₹50,000 + Sec 80CCD(2) employer (10% Pvt / 14% Govt)
        # - New Regime (Sec 115BAC(2)): Sec 80CCD(2) employer contribution up to 14% of Basic+DA (capped at ₹7.50L u/s 17(2)(vii))
        emp_80ccd2_cap_pct = (
            14.0
            if (tax_params["tax_regime"] == "NEW_115BAC" or is_govt_employee)
            else float(tax_params["allows_80ccd_2_employer_pct"])
        )
        allowed_employer_deduction = 0.0
        if employer_nps_contribution_inr > 0:
            salary_cap = (
                (float(basic_salary_inr) * (emp_80ccd2_cap_pct / 100.0))
                if basic_salary_inr is not None and float(basic_salary_inr) > 0
                else float(employer_nps_contribution_inr)
            )
            remaining_17_2_cap = max(
                0.0,
                SEC_17_2_VII_EMPLOYER_CAP_INR - max(0.0, float(employer_epf_contribution_inr or 0.0)),
            )
            allowed_employer_deduction = min(float(employer_nps_contribution_inr), salary_cap, remaining_17_2_cap)

        employee_deduction = 0.0
        if claim_upfront_deduction and tax_params["tax_regime"] == "OLD_REGIME":
            ccd_1 = min(principal, remaining_80c_headroom) if tax_params["allows_80c"] else 0.0
            ccd_1b = min(max(0.0, principal - ccd_1), 50000.0) if tax_params["allows_80ccd_1b"] else 0.0
            employee_deduction = ccd_1 + ccd_1b

        upfront_deduction_claimed_inr = round(employee_deduction + allowed_employer_deduction, 2)
        upfront_tax_saved_inr = round(upfront_deduction_claimed_inr * t_rate, 2)
        total_invested_for_irr = principal + float(employer_nps_contribution_inr or 0.0)
        post_tax_yield_pct = _amortize_upfront_deduction_irr_pct(
            coupon_post_tax_yield_pct,
            total_invested_for_irr,
            upfront_tax_saved_inr,
            horizon_yrs,
        )

        if premature_exit:
            tax_treatment_badge = (
                "Premature Exit <= ₹2.5L (100% Lump Sum)"
                if premature_small_corpus_exempt
                else "Premature Exit: 20% Lump Sum / 80% Taxable Annuity"
            )
        else:
            tax_treatment_badge = (
                "Small Corpus <= ₹5L (100% Tax-Exempt Lump Sum)"
                if normal_small_corpus_exempt
                else "60% Exempt Lump Sum / 40% Taxable Annuity"
            )

        deduction_clause = (
            f"Employer contribution up to {emp_80ccd2_cap_pct:.0f}% of Basic+DA deductible u/s 80CCD(2) in New Regime (₹7.50L Sec 17(2)(vii) cap)."
            if tax_params["tax_regime"] == "NEW_115BAC"
            else f"Eligible for ₹1.5L Sec 80CCD(1) + ₹50,000 exclusive Sec 80CCD(1B) + {emp_80ccd2_cap_pct:.0f}% employer Sec 80CCD(2) in Old Regime."
        )
        tax_statute_note = (
            f"Sec 10(12A) normal exit: 60% corpus tax-exempt, 40% mandatory annuity slab-taxed "
            f"(premature exit before age 60 requires 80% annuity -> {premature_post_tax_pct:.2f}% net; "
            f"100% lump-sum withdrawal allowed if terminal corpus <= ₹5L normal / <= ₹2.5L premature). {deduction_clause}"
        )

    elif taxability == "NPS_TIER2_NAV_GAIN":
        # Open-ended market-linked NAV account: tax-deferred until redemption (no annual Sec 194A accrual tax);
        # Central Govt employees opting for 3-year lock-in qualify for Sec 80C under Old Regime.
        horizon_yrs = 3.0 if is_govt_employee else 3.0
        r = gross_apy_pct / 100.0
        gross_gain = ((1.0 + r) ** horizon_yrs) - 1.0
        net_mult = 1.0 + (gross_gain * (1.0 - t_rate))
        coupon_post_tax_yield_pct = round(((net_mult ** (1.0 / horizon_yrs)) - 1.0) * 100.0, 2)
        effective_tax_rate_pct_out = round(
            ((gross_apy_pct - coupon_post_tax_yield_pct) / gross_apy_pct * 100.0) if gross_apy_pct > 0 else 0.0,
            2,
        )
        if is_govt_employee and tax_params["allows_80c"] and claim_upfront_deduction:
            upfront_deduction_claimed_inr = min(principal, remaining_80c_headroom)
            upfront_tax_saved_inr = round(upfront_deduction_claimed_inr * t_rate, 2)
        post_tax_yield_pct = _amortize_upfront_deduction_irr_pct(
            coupon_post_tax_yield_pct,
            principal,
            upfront_tax_saved_inr,
            horizon_yrs,
        )
        tax_treatment_badge = (
            "CG Tier-II Tax Saver (80C + NAV Deferral)"
            if upfront_tax_saved_inr > 0
            else f"NAV Gain Deferred ({eff_slab_pct:.2f}% on Redemption)"
        )
        tax_statute_note = (
            f"NPS Tier-II compounds without annual TDS; redemption gains are taxed at {eff_slab_pct:.2f}% marginal slab "
            "(Central Govt employees qualify for Sec 80C under 3-year lock-in u/s 80C(2)(xxv))."
        )

    else:
        # Standard SLAB_TAXABLE deposits, bonds, POSB, POMIS, SCSS, KVP, POTD, HYSA
        notes = instrument.get("notes") or {}
        if not isinstance(notes, dict):
            notes = {}
        is_savings_acct = category == "HIGH_YIELD_SAVINGS" or bool(notes.get("is_savings_account")) or inst_id == "SAV-POSB"
        is_bank_or_postoffice = category in (
            "SCHEDULED_BANK_FD",
            "SFB_FD",
            "HIGH_YIELD_SAVINGS",
            "SMALL_SAVINGS",
        )

        # Sec 10(15)(i) Post Office Savings Account statutory exemption (₹3,500 single / ₹7,000 joint) applies in BOTH regimes!
        sec_10_15_exempt_inr = 0.0
        if inst_id == "SAV-POSB" or notes.get("sec_10_15_i_exempt_single_inr"):
            cap_10_15 = float(
                notes.get("sec_10_15_i_exempt_joint_inr", 7000.0)
                if is_joint_account
                else notes.get("sec_10_15_i_exempt_single_inr", 3500.0)
            )
            sec_10_15_exempt_inr = min(annual_gross_interest_inr, cap_10_15)

        interest_after_10_15 = max(0.0, annual_gross_interest_inr - sec_10_15_exempt_inr)
        chapter_via_interest_shield = 0.0

        if tax_params["allows_80ttb"] and is_senior and is_bank_or_postoffice:
            chapter_via_interest_shield = min(interest_after_10_15, 50000.0)
            tax_treatment_badge = "Old Regime: Sec 80TTB (₹50k Senior Shield)"
        elif tax_params["allows_80tta"] and (not is_senior) and is_savings_acct:
            chapter_via_interest_shield = min(interest_after_10_15, 10000.0)
            tax_treatment_badge = (
                "Sec 10(15)(i) + Sec 80TTA Shield"
                if sec_10_15_exempt_inr > 0
                else "Old Regime: Sec 80TTA (₹10k Savings Shield)"
            )
        elif tax_params["sec_87a_rebate_applied"]:
            tax_treatment_badge = "Sec 87A Full Rebate (0% Slab)"
        elif sec_10_15_exempt_inr > 0:
            tax_treatment_badge = f"Sec 10(15)(i) ₹{sec_10_15_exempt_inr:,.0f} Exempt + {eff_slab_pct:.2f}% Slab"
        else:
            tax_treatment_badge = f"Marginal Slab ({eff_slab_pct:.2f}% incl. Cess)"

        deduction_shield_inr = round(sec_10_15_exempt_inr + chapter_via_interest_shield, 2)
        taxable_interest_inr = max(0.0, annual_gross_interest_inr - deduction_shield_inr)
        tax_paid_inr = taxable_interest_inr * t_rate
        net_interest_inr = annual_gross_interest_inr - tax_paid_inr
        coupon_post_tax_yield_pct = round((net_interest_inr / principal) * 100.0, 2)
        effective_tax_rate_pct_out = round(
            ((tax_paid_inr / annual_gross_interest_inr) * 100.0) if annual_gross_interest_inr > 0 else 0.0,
            2,
        )

        # Upfront Sec 80C principal deduction for eligible slab-interest instruments (e.g. SAV-SCSS, SAV-POTD-5Y, 5Y Tax-Saver FD)
        if tax_params["allows_80c"] and instrument.get("tax_section_80c_eligible") and claim_upfront_deduction:
            upfront_deduction_claimed_inr = min(principal, remaining_80c_headroom)
            upfront_tax_saved_inr = round(upfront_deduction_claimed_inr * t_rate, 2)
        post_tax_yield_pct = _amortize_upfront_deduction_irr_pct(
            coupon_post_tax_yield_pct,
            principal,
            upfront_tax_saved_inr,
            deduction_horizon_years,
        )
        if upfront_tax_saved_inr > 0 and "80TTB" not in tax_treatment_badge:
            tax_treatment_badge = f"Old Regime: Sec 80C + {eff_slab_pct:.2f}% Coupon Slab"

        if category == "CORPORATE_FD":
            tax_statute_note = (
                f"NBFC/Corporate public deposit interest is 100% taxed at {eff_slab_pct:.2f}% effective slab; "
                "ineligible for Sec 80TTA or Senior Sec 80TTB even under Old Regime."
            )
        else:
            tax_statute_note = (
                f"Interest taxed at {eff_slab_pct:.2f}% marginal slab."
                + (
                    f" ₹{deduction_shield_inr:,.0f} interest shielded on ₹{principal:,.0f} principal."
                    if deduction_shield_inr > 0
                    else " Sec 80TTA/80TTB deductions do not apply under New Regime (Sec 115BAC)."
                )
                + (
                    f" Includes ₹{upfront_tax_saved_inr:,.0f} Year-0 Sec 80C tax saving amortized over {deduction_horizon_years:.0f}Y."
                    if upfront_tax_saved_inr > 0
                    else ""
                )
            )

    # Sec 194A / Sec 192A TDS cash-flow drag evaluation (Finance Act 2025 thresholds)
    tds_applicable = bool(instrument.get("tds_applicable")) or epf_premature_tds_triggered
    tds_threshold = (
        50000.0
        if epf_premature_tds_triggered
        else (
            float(instrument.get("tds_threshold_senior_inr") or 0.0)
            if is_senior
            else float(instrument.get("tds_threshold_regular_inr") or 0.0)
        )
    )
    tds_triggered = bool(
        epf_premature_tds_triggered
        or (tds_applicable and tds_threshold > 0 and annual_gross_interest_inr > tds_threshold)
    )
    tds_withheld_inr = (
        round((principal if epf_premature_tds_triggered else annual_gross_interest_inr) * 0.10, 2)
        if tds_triggered and eff_slab_pct > 0
        else 0.0
    )
    form_declaration = "Form 15H (Age 60+)" if is_senior else "Form 15G (Age <60)"
    tds_note = (
        f"Sec {'192A' if epf_premature_tds_triggered else '194A'} TDS @ 10% applies above ₹{tds_threshold:,.0f}/yr per issuer "
        f"(est. ₹{tds_withheld_inr:,.0f} withheld on ₹{principal:,.0f}; submit {form_declaration} only if total tax liability is nil)."
        if tds_applicable and tds_threshold > 0
        else "Zero TDS deducted at source."
    )

    fisher_real_pct = compute_fisher_real_yield_pct(post_tax_yield_pct, cpi)
    spread_vs_10y_gsec_bps = round((applicable_nominal_pct - gsec_10y) * 100.0, 1)

    return {
        "instrument_id": instrument.get("instrument_id"),
        "nominal_rate_pct": round(applicable_nominal_pct, 2),
        "headline_slab_rate_pct": dyn["headline_slab_rate_pct"],
        "senior_bonus_applied_bps": round(senior_bonus_pct * 100.0, 1),
        "gross_apy_pct": gross_apy_pct,
        "coupon_only_post_tax_yield_pct": coupon_post_tax_yield_pct,
        "post_tax_yield_pct": post_tax_yield_pct,
        "effective_yield_with_deduction_pct": post_tax_yield_pct,
        "upfront_deduction_claimed_inr": upfront_deduction_claimed_inr,
        "upfront_tax_saved_inr": upfront_tax_saved_inr,
        "interest_exemption_or_deduction_inr": deduction_shield_inr,
        "tax_drag_bps": round((gross_apy_pct - post_tax_yield_pct) * 100.0, 1),
        "effective_tax_rate_pct": effective_tax_rate_pct_out,
        "effective_marginal_slab_pct": eff_slab_pct,
        "fisher_real_yield_pct": fisher_real_pct,
        "purchasing_power_preserved": fisher_real_pct >= 0.0,
        "cpi_inflation_used_pct": round(cpi, 2),
        "gsec_10y_used_pct": round(gsec_10y, 2),
        "spread_vs_10y_gsec_bps": spread_vs_10y_gsec_bps,
        "tax_regime": tax_params["tax_regime"],
        "rule_version": tax_params["rule_version"],
        "tax_treatment_badge": tax_treatment_badge,
        "tax_statute_note": tax_statute_note,
        "rate_formula_note": dyn["rate_formula_note"],
        "premature_exit_modeled": bool(premature_exit),
        "service_years_modeled": int(service_years),
        "tds_applicable": tds_applicable,
        "tds_threshold_inr": tds_threshold,
        "tds_triggered_on_principal": tds_triggered,
        "tds_annual_withheld_inr": tds_withheld_inr,
        "tds_note": tds_note,
    }


def compute_dicgc_safe_principal(
    annual_rate_pct: float,
    tenure_months: int,
    compounding_freq: str = "QUARTERLY",
    payout_mode: str = "CUMULATIVE",
    dicgc_limit_inr: float = DICGC_STATUTORY_LIMIT_INR,
) -> Dict[str, Any]:
    """Exact DICGC Act 1961 Sec 16(1) safe-principal solver ensuring Principal + Accrued
    Interest never exceeds ₹5,00,000 at any point up to maturity.

    Raises ValueError on unsupported payout modes or invalid tenors.
    """
    if annual_rate_pct is None or float(annual_rate_pct) < 0.0 or float(annual_rate_pct) > 25.0:
        raise ValueError(f"Invalid annual_rate_pct={annual_rate_pct}; expected 0.0..25.0%.")
    if tenure_months is None:
        raise ValueError("tenure_months is required for DICGC safe-principal calculation.")
    months = int(tenure_months)
    if months < 1 or months > DICGC_MAX_TENURE_MONTHS:
        raise ValueError(
            f"Unsupported deposit tenure_months={months}; RBI retail bank term deposits require 1..{DICGC_MAX_TENURE_MONTHS} months."
        )
    mode = str(payout_mode or "").strip().upper()
    if mode not in SUPPORTED_DICGC_PAYOUT_MODES:
        raise ValueError(
            f"Unsupported payout_mode='{payout_mode}'. Supported modes: {', '.join(SUPPORTED_DICGC_PAYOUT_MODES)}."
        )

    r = float(annual_rate_pct) / 100.0
    limit = float(dicgc_limit_inr or DICGC_STATUTORY_LIMIT_INR)
    if limit <= 0.0:
        raise ValueError(f"dicgc_limit_inr must be positive (got {dicgc_limit_inr}).")
    t_years = float(months) / 12.0

    if mode in ("QUARTERLY_PAYOUT", "MONTHLY_PAYOUT"):
        periods_per_yr = 12.0 if mode == "MONTHLY_PAYOUT" else 4.0
        growth_factor = 1.0 + (r / periods_per_yr)
        safe_principal = float(math.floor(limit / growth_factor))
        peak_accrued_interest = round(safe_principal * (growth_factor - 1.0), 2)
        total_payout_interest = round(safe_principal * r * t_years, 2)
        return {
            "payout_mode": mode,
            "safe_principal_inr": safe_principal,
            "accrued_interest_at_risk_inr": peak_accrued_interest,
            "peak_insured_balance_inr": round(safe_principal + peak_accrued_interest, 2),
            "total_interest_earned_inr": total_payout_interest,
            "maturity_or_peak_value_inr": round(safe_principal + peak_accrued_interest, 2),
            "uninsured_exposure_inr": 0.0,
            "headroom_buffer_inr": round(max(0.0, limit - (safe_principal + peak_accrued_interest)), 2),
        }

    # CUMULATIVE mode: compound over full horizon t_years
    n_comp, _ = _compounding_periods_per_year(compounding_freq)
    n = float(max(1, n_comp))
    growth_factor = (1.0 + (r / n)) ** (n * t_years)
    safe_principal = float(math.floor(limit / growth_factor))
    maturity_val = round(safe_principal * growth_factor, 2)
    accrued_interest = round(maturity_val - safe_principal, 2)
    uninsured = round(max(0.0, maturity_val - limit), 2)
    return {
        "payout_mode": "CUMULATIVE",
        "safe_principal_inr": safe_principal,
        "accrued_interest_at_risk_inr": accrued_interest,
        "peak_insured_balance_inr": maturity_val,
        "total_interest_earned_inr": accrued_interest,
        "maturity_or_peak_value_inr": maturity_val,
        "uninsured_exposure_inr": uninsured,
        "headroom_buffer_inr": round(max(0.0, limit - maturity_val), 2),
    }


def compute_dicgc_safe_ladder(
    corpus_inr: float,
    *,
    tenure_months: int = 36,
    payout_mode: str = "CUMULATIVE",
    is_senior: bool = False,
    tax_regime: str = "NEW_115BAC",
    slab_rate_pct: float = 30.0,
    surcharge_rate_pct: float = 0.0,
    effective_tax_rate_pct: Optional[float] = None,
    include_sfb: bool = True,
    max_banks: Optional[int] = None,
) -> Dict[str, Any]:
    """Constructs a 100%-insured multi-charter DICGC deposit split & routes excess corpus
    to tenor- and payout-compatible RBI Sovereign instruments so uninsured credit exposure is ₹0.

    Strictly validates corpus, tenure, payout mode, and per-instrument deposit terms; raises
    ValueError instead of silently clamping or booking incompatible tenors/payouts.
    """
    if corpus_inr is None:
        raise ValueError("corpus_inr is required.")
    total_corpus = float(corpus_inr)
    if not (DICGC_MIN_CORPUS_INR <= total_corpus <= DICGC_MAX_CORPUS_INR):
        raise ValueError(
            f"Unsupported corpus_inr={corpus_inr}; expected ₹{DICGC_MIN_CORPUS_INR:,.0f} to ₹{DICGC_MAX_CORPUS_INR:,.0f}."
        )
    if tenure_months is None:
        raise ValueError("tenure_months is required.")
    months = int(tenure_months)
    if not (DICGC_MIN_TENURE_MONTHS <= months <= DICGC_MAX_TENURE_MONTHS):
        raise ValueError(
            f"Unsupported deposit tenure_months={months}; expected {DICGC_MIN_TENURE_MONTHS}..{DICGC_MAX_TENURE_MONTHS} months."
        )
    norm_payout = str(payout_mode or "").strip().upper()
    if norm_payout not in SUPPORTED_DICGC_PAYOUT_MODES:
        raise ValueError(
            f"Unsupported payout_mode='{payout_mode}'. Supported modes: {', '.join(SUPPORTED_DICGC_PAYOUT_MODES)}."
        )
    if max_banks is not None and int(max_banks) < 0:
        raise ValueError(f"max_banks must be >= 0 (got {max_banks}).")

    anchors = get_live_macro_anchors()
    allowed_cats = {"SCHEDULED_BANK_FD"}
    if include_sfb:
        allowed_cats.add("SFB_FD")

    all_dicgc_fds = [
        inst
        for inst in get_active_savings_instruments(dicgc_only=True)
        if inst["category"] in allowed_cats
        and inst["dicgc_limit_inr"] > 0
        and _is_instrument_tariff_usable(inst)
    ]

    raw_candidates = [
        inst
        for inst in all_dicgc_fds
        if int(inst.get("tenure_min_months") or 0) <= months <= int(inst.get("tenure_max_months") or 0)
        and norm_payout in {str(p).strip().upper() for p in (inst.get("payout_options") or [])}
    ]

    if not raw_candidates and (max_banks is None or int(max_banks) > 0):
        supported_ranges = sorted(
            {f"{int(i['tenure_min_months'])}-{int(i['tenure_max_months'])}M" for i in all_dicgc_fds}
        )
        raise ValueError(
            f"No verified DICGC-insured bank term deposits support tenure_months={months} "
            f"with payout_mode='{norm_payout}' (include_sfb={include_sfb}; available bands: {', '.join(supported_ranges) or 'none'})."
        )

    min_ticket_candidates = [
        inst for inst in raw_candidates if total_corpus >= float(inst.get("min_investment_inr") or 1000.0)
    ]
    if raw_candidates and not min_ticket_candidates:
        lowest_min = min(float(i.get("min_investment_inr") or 1000.0) for i in raw_candidates)
        raise ValueError(
            f"Corpus ₹{total_corpus:,.0f} is below the minimum deposit ticket ₹{lowest_min:,.0f} "
            f"for {months}M {norm_payout} DICGC term deposits."
        )

    # Deduplicate strictly by RBI bank_charter_key ("in the same right and capacity")
    best_by_charter: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    for inst in min_ticket_candidates:
        charter = inst["bank_charter_key"]
        tax_eval = evaluate_savings_post_tax(
            inst,
            tax_regime=tax_regime,
            slab_rate_pct=slab_rate_pct,
            surcharge_rate_pct=surcharge_rate_pct,
            effective_tax_rate_pct=effective_tax_rate_pct,
            is_senior=is_senior,
            macro_anchors=anchors,
            claim_upfront_deduction=False,
        )
        prev = best_by_charter.get(charter)
        if prev is None or tax_eval["post_tax_yield_pct"] > prev[1]["post_tax_yield_pct"]:
            best_by_charter[charter] = (inst, tax_eval)

    ranked_charters = sorted(
        best_by_charter.values(),
        key=lambda pair: (
            pair[1]["post_tax_yield_pct"],
            1 if pair[0].get("issuer_ticker") in RBI_DSIB_TICKERS else 0,
            pair[1]["gross_apy_pct"],
        ),
        reverse=True,
    )
    if max_banks is not None and max_banks >= 0:
        ranked_charters = ranked_charters[: int(max_banks)]

    remaining = total_corpus
    tranches: List[Dict[str, Any]] = []
    weighted_gross_sum = 0.0
    weighted_post_tax_sum = 0.0
    total_dicgc_allocated = 0.0

    for inst, tax_eval in ranked_charters:
        if remaining <= 0:
            break
        min_ticket = float(inst.get("min_investment_inr") or 1000.0)
        if remaining < min_ticket:
            # Residual below this bank's minimum FD ticket rolls cleanly into sovereign overflow
            continue
        split = compute_dicgc_safe_principal(
            annual_rate_pct=tax_eval["nominal_rate_pct"],
            tenure_months=months,
            compounding_freq=inst["compounding_freq"],
            payout_mode=norm_payout,
            dicgc_limit_inr=inst["dicgc_limit_inr"],
        )
        safe_cap = split["safe_principal_inr"]
        if safe_cap < min_ticket:
            continue
        max_inv = inst.get("max_investment_inr")
        inst_cap = min(safe_cap, float(max_inv)) if max_inv is not None else safe_cap
        allocated = round(min(remaining, inst_cap), 2)
        if allocated < min_ticket:
            continue
        ratio = allocated / safe_cap if safe_cap > 0 else 0.0
        est_accrued = round(split["accrued_interest_at_risk_inr"] * ratio, 2)
        peak_bal = round(allocated + est_accrued, 2)
        tranches.append(
            {
                "tranche_type": "DICGC_INSURED_BANK_CHARTER",
                "bank_charter_key": inst["bank_charter_key"],
                "instrument_id": inst["instrument_id"],
                "scheme_name": inst["scheme_name"],
                "issuer_name": inst["issuer_name"],
                "issuer_ticker": inst["issuer_ticker"],
                "category": inst["category"],
                "tenure_min_months": inst["tenure_min_months"],
                "tenure_max_months": inst["tenure_max_months"],
                "principal_allocated_inr": allocated,
                "max_safe_principal_inr": safe_cap,
                "accrued_interest_reserved_inr": est_accrued,
                "peak_balance_under_dicgc_inr": peak_bal,
                "dicgc_limit_inr": inst["dicgc_limit_inr"],
                "uninsured_exposure_inr": 0.0,
                "nominal_rate_pct": tax_eval["nominal_rate_pct"],
                "gross_apy_pct": tax_eval["gross_apy_pct"],
                "post_tax_yield_pct": tax_eval["post_tax_yield_pct"],
                "fisher_real_yield_pct": tax_eval["fisher_real_yield_pct"],
                "guarantee_label": "DICGC Act Sec 16(1) (₹5L Principal + Interest)",
            }
        )
        remaining = round(max(0.0, remaining - allocated), 2)
        total_dicgc_allocated = round(total_dicgc_allocated + allocated, 2)
        weighted_gross_sum += allocated * tax_eval["gross_apy_pct"]
        weighted_post_tax_sum += allocated * tax_eval["post_tax_yield_pct"]

    sovereign_overflow_tranches: List[Dict[str, Any]] = []
    total_sovereign_overflow = 0.0

    # Route excess corpus ONLY to tenor- and payout-compatible Sovereign instruments
    def _allocate_statutory_overflow(sov_inst_id: str, charter_key: str, senior_only: bool = False) -> None:
        nonlocal remaining, total_sovereign_overflow, weighted_gross_sum, weighted_post_tax_sum
        if remaining <= 0 or (senior_only and not is_senior):
            return
        sov = get_savings_instrument_by_id(sov_inst_id)
        if not sov or not _is_instrument_tariff_usable(sov):
            return
        if not (int(sov.get("tenure_min_months") or 0) <= months <= int(sov.get("tenure_max_months") or 0)):
            return
        sov_payouts = {str(p).strip().upper() for p in (sov.get("payout_options") or [])}
        if norm_payout not in sov_payouts:
            return
        min_s = float(sov.get("min_investment_inr") or 1000.0)
        if remaining < min_s:
            return
        max_s = float(sov["max_investment_inr"]) if sov.get("max_investment_inr") is not None else remaining
        alloc = round(min(remaining, max_s), 2)
        if alloc < min_s:
            return
        sov_eval = evaluate_savings_post_tax(
            sov,
            tax_regime=tax_regime,
            slab_rate_pct=slab_rate_pct,
            surcharge_rate_pct=surcharge_rate_pct,
            effective_tax_rate_pct=effective_tax_rate_pct,
            is_senior=is_senior,
            macro_anchors=anchors,
            claim_upfront_deduction=False,
        )
        sovereign_overflow_tranches.append(
            {
                "tranche_type": "SOVEREIGN_OVERFLOW",
                "bank_charter_key": charter_key,
                "instrument_id": sov["instrument_id"],
                "scheme_name": sov["scheme_name"],
                "issuer_name": sov["issuer_name"],
                "issuer_ticker": None,
                "category": sov["category"],
                "principal_allocated_inr": alloc,
                "max_safe_principal_inr": max_s,
                "accrued_interest_reserved_inr": 0.0,
                "peak_balance_under_dicgc_inr": alloc,
                "dicgc_limit_inr": 0.0,
                "uninsured_exposure_inr": 0.0,
                "nominal_rate_pct": sov_eval["nominal_rate_pct"],
                "gross_apy_pct": sov_eval["gross_apy_pct"],
                "post_tax_yield_pct": sov_eval["post_tax_yield_pct"],
                "fisher_real_yield_pct": sov_eval["fisher_real_yield_pct"],
                "guarantee_label": "100% Sovereign Guarantee (Govt of India)",
            }
        )
        remaining = round(max(0.0, remaining - alloc), 2)
        total_sovereign_overflow = round(total_sovereign_overflow + alloc, 2)
        weighted_gross_sum += alloc * sov_eval["gross_apy_pct"]
        weighted_post_tax_sum += alloc * sov_eval["post_tax_yield_pct"]

    if remaining > 0 and months == 60:
        if norm_payout == "QUARTERLY_PAYOUT":
            _allocate_statutory_overflow("SAV-SCSS", "GOVT_OF_INDIA_SCSS", senior_only=True)
        elif norm_payout == "CUMULATIVE":
            _allocate_statutory_overflow("SAV-NSC", "GOVT_OF_INDIA_NSC", senior_only=False)
        elif norm_payout == "MONTHLY_PAYOUT":
            _allocate_statutory_overflow("SAV-POMIS", "GOVT_OF_INDIA_POMIS", senior_only=False)

    if remaining > 0:
        tax_p = resolve_effective_tax_parameters(
            tax_regime=tax_regime,
            slab_rate_pct=slab_rate_pct,
            surcharge_rate_pct=surcharge_rate_pct,
            effective_tax_rate_pct=effective_tax_rate_pct,
        )
        sov_gross = float(anchors["tbill_364d_pct"] if months <= 18 else anchors["gsec_10y_pct"])
        sov_id = "GOI_364D_TBILL" if months <= 18 else "GOI_GSEC_LADDER"
        sov_name = (
            "RBI Retail Direct 364-Day Treasury Bill Overflow"
            if months <= 18
            else f"RBI Retail Direct {max(1, round(months / 12))}-Year Sovereign G-Sec Overflow"
        )
        sov_gross = round(sov_gross, 2)
        sov_net = round(sov_gross * (1.0 - tax_p["effective_slab_rate_pct"] / 100.0), 2)
        sov_real = compute_fisher_real_yield_pct(sov_net, anchors["cpi_inflation_pct"])

        sovereign_overflow_tranches.append(
            {
                "tranche_type": "SOVEREIGN_OVERFLOW",
                "bank_charter_key": "RBI_RETAIL_DIRECT_SOVEREIGN",
                "instrument_id": sov_id,
                "scheme_name": sov_name,
                "issuer_name": "Reserve Bank of India / Govt of India",
                "issuer_ticker": None,
                "category": "SOVEREIGN_DIRECT",
                "principal_allocated_inr": remaining,
                "max_safe_principal_inr": remaining,
                "accrued_interest_reserved_inr": 0.0,
                "peak_balance_under_dicgc_inr": remaining,
                "dicgc_limit_inr": 0.0,
                "uninsured_exposure_inr": 0.0,
                "nominal_rate_pct": sov_gross,
                "gross_apy_pct": sov_gross,
                "post_tax_yield_pct": sov_net,
                "fisher_real_yield_pct": sov_real,
                "guarantee_label": "100% Sovereign Guarantee (Consolidated Fund of India)",
            }
        )
        total_sovereign_overflow = round(total_sovereign_overflow + remaining, 2)
        weighted_gross_sum += remaining * sov_gross
        weighted_post_tax_sum += remaining * sov_net
        remaining = 0.0

    all_tranches = tranches + sovereign_overflow_tranches
    blended_gross = round(weighted_gross_sum / total_corpus, 2) if total_corpus > 0 else 0.0
    blended_post_tax = round(weighted_post_tax_sum / total_corpus, 2) if total_corpus > 0 else 0.0
    blended_real = compute_fisher_real_yield_pct(blended_post_tax, anchors["cpi_inflation_pct"]) if total_corpus > 0 else 0.0

    # Illustrative naive single-bank uninsured exposure comparison
    naive_uninsured = round(max(0.0, total_corpus - DICGC_STATUTORY_LIMIT_INR), 2)

    return {
        "corpus_inr": total_corpus,
        "tenure_months": months,
        "payout_mode": norm_payout,
        "is_senior": is_senior,
        "tax_regime": tax_regime,
        "slab_rate_pct": slab_rate_pct,
        "distinct_bank_charters_used": len(tranches),
        "dicgc_insured_allocated_inr": total_dicgc_allocated,
        "sovereign_overflow_inr": total_sovereign_overflow,
        "total_uninsured_credit_exposure_inr": 0.0,
        "naive_single_bank_uninsured_inr": naive_uninsured,
        "blended_gross_apy_pct": blended_gross,
        "blended_post_tax_yield_pct": blended_post_tax,
        "blended_fisher_real_yield_pct": blended_real,
        "cpi_inflation_used_pct": anchors["cpi_inflation_pct"],
        "tranches": all_tranches,
        "statutory_note": (
            "Under DICGC Act 1961 Section 16(1), Deposit Insurance and Credit Guarantee Corporation "
            "(wholly-owned RBI subsidiary) insures up to ₹5,00,000 COMBINED principal + accrued interest "
            "per depositor per insured bank charter in the same right and capacity. Excess principal is "
            "routed to tenor-compatible sovereign-backed Government of India securities."
        ),
    }


def evaluate_fd_issuer_contagion_bridge(instrument: Dict[str, Any]) -> Dict[str, Any]:
    """Cross-capital-structure contagion & seniority waterfall bridge joining Fixed Deposits
    to exchange-traded Senior Corporate NCDs (`corporate_debt_securities`) and Equity fundamentals
    (`cached_fundamentals` / `reports`).

    Invariants:
    - Excludes AT1 Perpetual (`PERPETUAL_AT1`) & all Tier-2 Subordinated variants (`L3`).
    - Uses bidirectional `ISSUER_DEBT_TICKER_ALIASES` (`BAJFINANCE` <-> `BAJAJFIN`, etc.).
    - Suppresses misleading BFSI `debt_to_equity`, `roce`, and `market_cap <= 0` (`B7`).
    - Caps unsecured 0%-DICGC Corporate/NBFC FDs at `<= 72/100` composite safety score.
    """
    ticker = str(instrument.get("issuer_ticker") or "").strip().upper()
    category = str(instrument.get("category") or "").upper()
    issuer_type = str(instrument.get("issuer_type") or "").upper()
    is_bfsi = issuer_type in _BFSI_ISSUER_TYPES

    fd_gross_apy = compute_effective_annual_gross_yield_pct(
        float(instrument.get("base_rate_pct") or 0.0),
        str(instrument.get("compounding_freq") or "QUARTERLY"),
    )

    senior_bonds: List[Dict[str, Any]] = []
    excluded_subordinated_count = 0
    equity_snapshot: Optional[Dict[str, Any]] = None

    if ticker:
        alias_tuple = ISSUER_DEBT_TICKER_ALIASES.get(ticker, (ticker,))
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()
        try:
            in_placeholders = ", ".join([p] * len(alias_tuple))
            cursor.execute(
                f"""
                SELECT isin, ticker, instrument_name, seniority_tier, credit_rating,
                       coupon_rate_pct, ytm_pct, asset_cover_ratio
                FROM corporate_debt_securities
                WHERE UPPER(ticker) IN ({in_placeholders})
                ORDER BY ytm_pct DESC;
                """,
                tuple(a.upper() for a in alias_tuple),
            )
            for b_row in cursor.fetchall():
                s_tier_raw = str(b_row[3] or "SENIOR_SECURED").upper()
                if _SUBORDINATED_OR_AT1_RE.search(s_tier_raw):
                    excluded_subordinated_count += 1
                    continue
                ytm_val = float(b_row[6]) if b_row[6] is not None else float(b_row[5] or 0.0)
                if ytm_val <= 0:
                    continue
                senior_bonds.append(
                    {
                        "isin": str(b_row[0]),
                        "ticker": str(b_row[1]),
                        "instrument_name": str(b_row[2]),
                        "seniority_tier": s_tier_raw,
                        "credit_rating": str(b_row[4] or "UNRATED"),
                        "coupon_rate_pct": round(float(b_row[5] or 0.0), 2),
                        "ytm_pct": round(ytm_val, 2),
                        "asset_cover_ratio": float(b_row[7]) if b_row[7] is not None else None,
                        "detail_url": f"/debt/{b_row[0]}",
                    }
                )

            cursor.execute(
                f"""
                SELECT ticker, company_name, sector, current_price, market_cap,
                       pe_ratio, pb_ratio, roe, roce, debt_to_equity
                FROM cached_fundamentals
                WHERE UPPER(ticker) = {p}
                LIMIT 1;
                """,
                (ticker,),
            )
            eq_row = cursor.fetchone()
            has_archived_dossier = False
            cursor.execute(f"SELECT 1 FROM reports WHERE UPPER(ticker) = {p} LIMIT 1;", (ticker,))
            if cursor.fetchone():
                has_archived_dossier = True

            if eq_row:
                raw_mcap = float(eq_row[4]) if eq_row[4] is not None else None
                mcap_cr = round(raw_mcap / 1e7, 2) if raw_mcap and raw_mcap > 1e8 else (round(raw_mcap, 2) if raw_mcap and raw_mcap > 0 else None)
                equity_snapshot = {
                    "ticker": str(eq_row[0]),
                    "company_name": str(eq_row[1] or instrument.get("issuer_name")),
                    "sector": str(eq_row[2] or ("Financial Services" if is_bfsi else "")),
                    "current_price": round(float(eq_row[3]), 2) if eq_row[3] and float(eq_row[3]) > 0 else None,
                    "market_cap_cr": mcap_cr,
                    "pe_ratio": round(float(eq_row[5]), 2) if eq_row[5] and float(eq_row[5]) > 0 else None,
                    "pb_ratio": round(float(eq_row[6]), 2) if eq_row[6] and float(eq_row[6]) > 0 else None,
                    "roe_pct": round(float(eq_row[7]), 2) if eq_row[7] is not None else None,
                    # BFSI Hygiene (B7): suppress meaningless ROCE & Debt/Equity on Banks/SFBs/NBFCs/HFCs
                    "roce_pct": None if is_bfsi else (round(float(eq_row[8]), 2) if eq_row[8] is not None else None),
                    "debt_to_equity": None if is_bfsi else (round(float(eq_row[9]), 2) if eq_row[9] is not None else None),
                    "is_bfsi_balance_sheet": is_bfsi,
                    "has_equity_dossier": has_archived_dossier,
                    "equity_dossier_url": f"/dossier/{ticker}" if has_archived_dossier else None,
                }
            elif has_archived_dossier:
                equity_snapshot = {
                    "ticker": ticker,
                    "company_name": str(instrument.get("issuer_name")),
                    "sector": "Financial Services" if is_bfsi else "Listed Issuer",
                    "current_price": None,
                    "market_cap_cr": None,
                    "pe_ratio": None,
                    "pb_ratio": None,
                    "roe_pct": None,
                    "roce_pct": None,
                    "debt_to_equity": None,
                    "is_bfsi_balance_sheet": is_bfsi,
                    "has_equity_dossier": True,
                    "equity_dossier_url": f"/dossier/{ticker}",
                }
        except Exception as exc:
            logger.warning("Contagion bridge lookup notice for %s: %s", ticker, exc)
        finally:
            cursor.close()
            conn.close()

    best_senior_secured = next(
        (b for b in senior_bonds if "SENIOR_SECURED" in b["seniority_tier"]),
        senior_bonds[0] if senior_bonds else None,
    )

    contagion_flag = "NO_TRADED_SENIOR_NCD"
    unsecured_spread_vs_ncd_bps: Optional[float] = None
    contagion_summary = ""

    if best_senior_secured:
        ncd_ytm = best_senior_secured["ytm_pct"]
        unsecured_spread_vs_ncd_bps = round((fd_gross_apy - ncd_ytm) * 100.0, 1)
        if category == "CORPORATE_FD":
            if unsecured_spread_vs_ncd_bps <= 0.0:
                contagion_flag = "SENIORITY_YIELD_INVERSION"
                contagion_summary = (
                    f"[CALCULATED METRIC] Seniority Yield Inversion Detected: Unsecured 0%-DICGC FD "
                    f"({fd_gross_apy:.2f}% APY) yields {abs(unsecured_spread_vs_ncd_bps):.0f} bps LESS than "
                    f"the same issuer's Senior Secured NCD ({best_senior_secured['isin']} @ {ncd_ytm:.2f}% YTM) "
                    f"despite ranking lower in the liquidation waterfall."
                )
            elif unsecured_spread_vs_ncd_bps < 25.0:
                contagion_flag = "COMPRESSED_UNSECURED_SPREAD"
                contagion_summary = (
                    f"[CALCULATED METRIC] Thin Unsecured Risk Cushion (+{unsecured_spread_vs_ncd_bps:.0f} bps) "
                    f"over Senior Secured NCD ({best_senior_secured['isin']} @ {ncd_ytm:.2f}% YTM)."
                )
            else:
                contagion_flag = "POSITIVE_UNSECURED_SPREAD"
                contagion_summary = (
                    f"[CALCULATED METRIC] Unsecured FD pays +{unsecured_spread_vs_ncd_bps:.0f} bps over "
                    f"listed Senior Secured NCD ({best_senior_secured['isin']} @ {ncd_ytm:.2f}% YTM)."
                )
        else:
            contagion_flag = "DICGC_INSURED_SENIOR_PARITY"
            contagion_summary = (
                f"[VERIFIED FACT] Retail deposit protected up to ₹5,00,000 by RBI DICGC insurance; "
                f"listed senior bond reference yields {ncd_ytm:.2f}% YTM ({best_senior_secured['isin']})."
            )
    else:
        if instrument.get("sovereign_backed"):
            contagion_flag = "SOVEREIGN_BACKED"
            contagion_summary = "[VERIFIED FACT] Backed by Sovereign Guarantee of the Government of India."
        elif instrument.get("dicgc_insured"):
            contagion_flag = "DICGC_INSURED_NO_LISTED_SENIOR_NCD"
            contagion_summary = (
                "[VERIFIED FACT] Covered up to ₹5,00,000 combined principal + interest under DICGC Act Sec 16(1)."
                + (
                    f" ({excluded_subordinated_count} subordinated Tier-2/AT1 bond(s) excluded from senior comparison.)"
                    if excluded_subordinated_count > 0
                    else ""
                )
            )
        else:
            contagion_summary = "[MODEL INTERPRETATION] Regulated non-sovereign scheme; monitor credit rating and statutory exit terms."

    # Composite Safety Posture Score (0-100) with hard <= 72 cap on 0%-DICGC Corporate FDs
    rating_upper = str(instrument.get("credit_rating") or "").upper()
    if instrument.get("sovereign_backed"):
        safety_score = 98
        safety_tier = "TIER_1_SOVEREIGN"
    elif instrument.get("dicgc_insured"):
        if ticker in RBI_DSIB_TICKERS:
            safety_score = 95
            safety_tier = "TIER_1_RBI_DSIB_DICGC"
        elif category == "SCHEDULED_BANK_FD" or issuer_type in ("PUBLIC_SECTOR_BANK", "PRIVATE_SECTOR_BANK"):
            safety_score = 92
            safety_tier = "TIER_1_SCHEDULED_BANK_DICGC"
        else:
            safety_score = 88
            safety_tier = "TIER_2_SFB_DICGC_INSURED"
    elif category == "RETIREMENT_PENSION":
        safety_score = 90
        safety_tier = "TIER_1_PFRDA_STATUTORY_TRUST"
    else:
        # Unsecured Corporate / NBFC Public Deposit — NEVER exceeds CORPORATE_FD_SAFETY_CAP (72)
        if "AAA" in rating_upper:
            base_cap = 72
        elif "AA+" in rating_upper:
            base_cap = 66
        elif "AA" in rating_upper:
            base_cap = 60
        else:
            base_cap = 48
        if contagion_flag == "SENIORITY_YIELD_INVERSION":
            base_cap -= 6
        safety_score = min(CORPORATE_FD_SAFETY_CAP, max(25, base_cap))
        safety_tier = "TIER_3_UNSECURED_NBFC_DEPOSIT"

    return {
        "issuer_ticker": ticker or None,
        "fd_gross_apy_pct": fd_gross_apy,
        "composite_safety_score": safety_score,
        "safety_tier": safety_tier,
        "contagion_flag": contagion_flag,
        "contagion_summary": contagion_summary,
        "unsecured_spread_vs_senior_ncd_bps": unsecured_spread_vs_ncd_bps,
        "comparable_senior_ncds": senior_bonds[:5],
        "best_senior_secured_ncd": best_senior_secured,
        "excluded_subordinated_or_at1_bonds": excluded_subordinated_count,
        "equity_health": equity_snapshot,
    }


def get_cash_park_sleeve(
    *,
    tax_regime: str = "NEW_115BAC",
    slab_rate_pct: float = 30.0,
    surcharge_rate_pct: float = 0.0,
    effective_tax_rate_pct: Optional[float] = None,
    holding_months: int = 13,
    is_senior: bool = False,
) -> Dict[str, Any]:
    """Builds the Short-Term Treasury & Cash-Park Comparator across:
    1. RBI Treasury Bills (`91D`, `182D`, `364D`)
    2. High-Yield Savings Accounts & Short-Tenor DICGC Bank FDs
    3. Pure `Sec 112A` Equity Arbitrage Mutual Funds (strictly excluding Arbitrage FoFs)
    4. Overnight / Liquid / Ultra-Short Debt Mutual Funds (`Sec 50AA`)
    5. Liquid & Target-Maturity ETFs (`etf_matrix`)

    Strict Zero-Hallucination Rule: Never substitutes fabricated 7.2% or 14.5% returns for MFs/ETFs;
    uses verified `instrument_metric_observations` / `metadata_json` returns when present, and marks
    unobserved NAV series explicitly while computing an analytical Sec 112A vs Sec 50AA tax-alpha
    illustration anchored to live 91D T-Bill carry minus scheme Direct TER.
    """
    anchors = get_live_macro_anchors()
    cpi = float(anchors["cpi_inflation_pct"])
    tbill_91d = float(anchors["tbill_91d_pct"])
    tbill_is_fallback = bool(anchors.get("tbill_91d_is_fallback"))
    tax_p = resolve_effective_tax_parameters(
        tax_regime=tax_regime,
        slab_rate_pct=slab_rate_pct,
        surcharge_rate_pct=surcharge_rate_pct,
        effective_tax_rate_pct=effective_tax_rate_pct,
    )
    eff_slab = tax_p["effective_slab_rate_pct"]
    eff_arb_rate = (
        tax_p["effective_ltcg_112a_rate_pct"]
        if int(holding_months or 13) > 12
        else tax_p["effective_stcg_111a_rate_pct"]
    )

    sleeve_items: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()

    # 1. RBI Treasury Bills (do NOT auto-seed assumed curve rows on empty DB)
    for pt in get_sovereign_yield_curve(auto_seed=False):
        if pt.get("instrument_type") != "TBILL":
            continue
        src_label = str(pt.get("source") or "")
        is_unverified_seed = (
            bool(pt.get("is_fallback"))
            or "FALLBACK" in src_label.upper()
            or "STATIC_BASELINE" in src_label.upper()
        )
        key = f"TBILL:{pt['tenor_label']}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        gross = round(float(pt["cut_off_yield"]), 2)
        net = round(gross * (1.0 - eff_slab / 100.0), 2)
        sleeve_items.append(
            {
                "id": f"GOI_{pt['tenor_label']}",
                "name": f"RBI Treasury Bill ({pt['tenor_label'].replace('_', ' ')})",
                "vehicle_type": "RBI_TBILL",
                "tax_section": f"Slab Discount ({eff_slab:.2f}% Sec 50AA / IFOS)",
                "guarantee": "100% Sovereign Guarantee",
                "liquidity": "T+1 Secondary / Hold to Maturity",
                "gross_yield_pct": None if is_unverified_seed else gross,
                "benchmark_carry_net_ter_pct": gross if is_unverified_seed else None,
                "post_tax_yield_pct": net,
                "fisher_real_yield_pct": compute_fisher_real_yield_pct(net, cpi),
                "yield_provenance": (
                    f"[MODEL INTERPRETATION] Unverified Baseline T-Bill Reference ({pt.get('auction_date')})"
                    if is_unverified_seed
                    else f"[VERIFIED FACT] RBI Auction Cut-off ({pt.get('auction_date')})"
                ),
                "detail_url": "/sovereign",
            }
        )

    # 2. High-Yield Savings Accounts & Short-Tenor DICGC Bank FDs (<= 15 months, non-stale only)
    for inst in get_active_savings_instruments():
        if not _is_instrument_tariff_usable(inst):
            continue
        if inst["category"] == "HIGH_YIELD_SAVINGS" or (
            inst["dicgc_insured"] and 0 < inst["tenure_min_months"] <= 15
        ):
            key = f"SAV:{inst['instrument_id']}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            ev = evaluate_savings_post_tax(
                inst,
                tax_regime=tax_regime,
                slab_rate_pct=slab_rate_pct,
                surcharge_rate_pct=surcharge_rate_pct,
                effective_tax_rate_pct=effective_tax_rate_pct,
                is_senior=is_senior,
                macro_anchors=anchors,
            )
            sleeve_items.append(
                {
                    "id": inst["instrument_id"],
                    "name": inst["scheme_name"],
                    "vehicle_type": inst["category"],
                    "tax_section": ev["tax_treatment_badge"],
                    "guarantee": "DICGC ₹5L Principal + Interest",
                    "liquidity": "T+0 Instant" if inst["category"] == "HIGH_YIELD_SAVINGS" else "Callable T+0 (Premature Penalty)",
                    "gross_yield_pct": ev["gross_apy_pct"],
                    "post_tax_yield_pct": ev["post_tax_yield_pct"],
                    "fisher_real_yield_pct": ev["fisher_real_yield_pct"],
                    "yield_provenance": f"[VERIFIED FACT] {inst['source_authority']} ({inst['effective_from']})",
                    "detail_url": f"/savings/{inst['instrument_id']}",
                }
            )

    # 3 & 4. Pure Arbitrage MFs (Sec 112A) & Liquid/Overnight Debt MFs (Sec 50AA)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT instrument_id, measure_type, value_pct, as_of, source_name
            FROM instrument_metric_observations
            WHERE asset_class IN ('MF', 'ETF')
            ORDER BY as_of DESC;
            """
        )
        obs_by_id: Dict[str, Dict[str, Any]] = {}
        for o_row in cursor.fetchall():
            oid = str(o_row[0])
            if oid not in obs_by_id:
                obs_by_id[oid] = {
                    "measure_type": str(o_row[1]),
                    "value_pct": float(o_row[2]),
                    "as_of": str(o_row[3]),
                    "source_name": str(o_row[4]),
                }

        cursor.execute(
            """
            SELECT scheme_code, scheme_name, broad_category, category, aum_crores, ter_direct_pct, metadata_json
            FROM mutual_fund_schemes
            ORDER BY COALESCE(aum_crores, 0) DESC;
            """
        )
        arb_added = 0
        liq_added = 0
        excluded_fof_count = 0
        tbill_desc = (
            f"assumed fallback 91D T-Bill ({tbill_91d:.2f}%)"
            if tbill_is_fallback
            else f"live 91D T-Bill ({tbill_91d:.2f}%)"
        )

        for m_row in cursor.fetchall():
            scode = str(m_row[0])
            sname = str(m_row[1] or "")
            broad = str(m_row[2] or "").upper()
            cat = str(m_row[3] or "")
            ter = float(m_row[5]) if m_row[5] is not None else 0.30
            meta = json.loads(m_row[6] or "{}") if m_row[6] else {}

            combined_text = f"{sname} {cat}"
            if _PURE_ARBITRAGE_RE.search(combined_text) and _ARBITRAGE_FOF_EXCLUSION_RE.search(combined_text):
                excluded_fof_count += 1
                continue

            is_arb = is_pure_sec_112a_arbitrage_fund(broad, cat, sname)
            is_cash_debt = (broad == "DEBT") and bool(_CASH_DEBT_MF_RE.search(combined_text))

            if not (is_arb or is_cash_debt):
                continue
            if is_arb and arb_added >= 3:
                continue
            if is_cash_debt and liq_added >= 3:
                continue

            obs = obs_by_id.get(scode)
            meta_ret = meta.get("returns_1y_pct") or meta.get("returns_3y_cagr") or meta.get("portfolio_ytm_pct")
            observed_gross = float(obs["value_pct"]) if obs else (float(meta_ret) if meta_ret is not None else None)

            # Analytical net-of-TER T-Bill/TREPS carry reference when trailing NAV return is pending
            carry_ref_gross = round(max(0.0, tbill_91d - ter), 2)
            effective_gross_for_tax = observed_gross if observed_gross is not None else carry_ref_gross
            applicable_tax = eff_arb_rate if is_arb else eff_slab
            net_yield = round(effective_gross_for_tax * (1.0 - applicable_tax / 100.0), 2)

            sleeve_items.append(
                {
                    "id": scode,
                    "name": sname,
                    "vehicle_type": "ARBITRAGE_MF_112A" if is_arb else "LIQUID_DEBT_MF_50AA",
                    "tax_section": (
                        f"Sec 112A Equity LTCG ({eff_arb_rate:.2f}% >12M, ₹1.25L Exempt; Tax Deferred to Redemption)"
                        if is_arb and holding_months > 12
                        else (
                            f"Sec 111A Equity STCG ({eff_arb_rate:.2f}% <=12M; Tax Deferred to Redemption)"
                            if is_arb
                            else f"Sec 50AA Debt Slab ({eff_slab:.2f}% on Redemption)"
                        )
                    ),
                    "guarantee": "SEBI Mutual Fund Trust (0% DICGC; Marked-to-Market NAV)",
                    "liquidity": "T+1 / Instant Redemption up to ₹50k (Liquid)",
                    "gross_yield_pct": round(observed_gross, 2) if observed_gross is not None else None,
                    "benchmark_carry_net_ter_pct": carry_ref_gross,
                    "post_tax_yield_pct": net_yield,
                    "fisher_real_yield_pct": compute_fisher_real_yield_pct(net_yield, cpi),
                    "ter_direct_pct": round(ter, 2),
                    "yield_provenance": (
                        f"[VERIFIED FACT] Observed Fund Return ({obs['as_of']})"
                        if obs
                        else f"[MODEL INTERPRETATION] Trailing NAV pending; taxed on {tbill_desc} minus {ter:.2f}% Direct TER"
                    ),
                    "detail_url": f"/funds/{scode}",
                }
            )
            if is_arb:
                arb_added += 1
            else:
                liq_added += 1
    except Exception as exc:
        logger.warning("Cash-park MF scan notice: %s", exc)
        excluded_fof_count = 0
    finally:
        cursor.close()
        conn.close()

    # 5. Liquid & Target-Maturity Debt ETFs
    etf_added = 0
    etf_tbill_label = "Assumed fallback 91D T-Bill" if tbill_is_fallback else "Benchmark 91D T-Bill"
    for etf in get_etf_matrix():
        if etf_added >= 3:
            break
        probe = f"{etf.get('symbol', '')} {etf.get('scheme_name', '')} {etf.get('category', '')}"
        if not _CASH_DEBT_ETF_RE.search(probe):
            continue
        sym = str(etf["symbol"])
        key = f"ETF:{sym}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        ter_etf = float(etf.get("expense_ratio_pct") or 0.15)
        carry_etf = round(max(0.0, tbill_91d - ter_etf), 2)
        net_etf = round(carry_etf * (1.0 - eff_slab / 100.0), 2)
        sleeve_items.append(
            {
                "id": sym,
                "name": str(etf.get("scheme_name") or sym),
                "vehicle_type": "LIQUID_DEBT_ETF",
                "tax_section": f"Sec 50AA Debt ETF Slab ({eff_slab:.2f}%)",
                "guarantee": "Custodial Sovereign/Money-Market Basket",
                "liquidity": "Intraday NSE/BSE Demat",
                "gross_yield_pct": None,
                "benchmark_carry_net_ter_pct": carry_etf,
                "post_tax_yield_pct": net_etf,
                "fisher_real_yield_pct": compute_fisher_real_yield_pct(net_etf, cpi),
                "ter_direct_pct": round(ter_etf, 2),
                "yield_provenance": f"[MODEL INTERPRETATION] {etf_tbill_label} ({tbill_91d:.2f}%) minus {ter_etf:.2f}% ETF TER",
                "detail_url": f"/etfs/{sym}",
            }
        )
        etf_added += 1

    sleeve_items.sort(key=lambda x: x["post_tax_yield_pct"], reverse=True)
    return {
        "holding_months": holding_months,
        "tax_regime": tax_p["tax_regime"],
        "effective_slab_rate_pct": eff_slab,
        "effective_arbitrage_tax_rate_pct": eff_arb_rate,
        "cpi_inflation_pct": cpi,
        "excluded_arbitrage_fof_count": excluded_fof_count,
        "items": sleeve_items,
    }


def get_enriched_savings_directory(
    *,
    category: Optional[str] = None,
    query: Optional[str] = None,
    tax_regime: str = "NEW_115BAC",
    slab_rate_pct: float = 30.0,
    surcharge_rate_pct: float = 0.0,
    effective_tax_rate_pct: Optional[float] = None,
    is_senior: bool = False,
    dicgc_only: bool = False,
    sovereign_only: bool = False,
    tax_80c_only: bool = False,
    sort_by: str = "post_tax_desc",
) -> Dict[str, Any]:
    """Returns full enriched Fixed Savings & Deposits directory with post-tax, Fisher real
    yield, staleness badges, and contagion/seniority flags for UI & JSON consumers.
    """
    anchors = get_live_macro_anchors()
    nsc_inst = get_savings_instrument_by_id("SAV-NSC")
    nsc_rate = float(nsc_inst["base_rate_pct"]) if nsc_inst else 7.70

    raw_list = get_active_savings_instruments(
        category=category,
        query=query,
        dicgc_only=dicgc_only,
        sovereign_only=sovereign_only,
        tax_80c_only=tax_80c_only,
    )

    enriched: List[Dict[str, Any]] = []
    for inst in raw_list:
        tax_eval = evaluate_savings_post_tax(
            inst,
            tax_regime=tax_regime,
            slab_rate_pct=slab_rate_pct,
            surcharge_rate_pct=surcharge_rate_pct,
            effective_tax_rate_pct=effective_tax_rate_pct,
            is_senior=is_senior,
            macro_anchors=anchors,
            nsc_rate_override=nsc_rate,
        )
        contagion = evaluate_fd_issuer_contagion_bridge(inst)
        safe_tenure = min(DICGC_MAX_TENURE_MONTHS, max(12, int(inst["tenure_max_months"] or 36)))
        dicgc_split = (
            compute_dicgc_safe_principal(
                annual_rate_pct=tax_eval["nominal_rate_pct"],
                tenure_months=safe_tenure,
                compounding_freq=inst["compounding_freq"],
                payout_mode="CUMULATIVE",
                dicgc_limit_inr=inst["dicgc_limit_inr"],
            )
            if inst["dicgc_insured"] and inst["dicgc_limit_inr"] > 0
            else None
        )
        row = dict(inst)
        row["tax_eval"] = tax_eval
        row["contagion"] = contagion
        row["dicgc_split"] = dicgc_split
        enriched.append(row)

    sort_key = str(sort_by or "post_tax_desc").lower()
    if sort_key == "gross_desc":
        enriched.sort(key=lambda r: (r["tax_eval"]["gross_apy_pct"], r["contagion"]["composite_safety_score"]), reverse=True)
    elif sort_key == "safety_desc":
        enriched.sort(key=lambda r: (r["contagion"]["composite_safety_score"], r["tax_eval"]["post_tax_yield_pct"]), reverse=True)
    elif sort_key == "real_desc":
        enriched.sort(key=lambda r: (r["tax_eval"]["fisher_real_yield_pct"], r["contagion"]["composite_safety_score"]), reverse=True)
    else:
        enriched.sort(key=lambda r: (r["tax_eval"]["post_tax_yield_pct"], r["contagion"]["composite_safety_score"]), reverse=True)

    category_counts: Dict[str, int] = {k: 0 for k in SAVINGS_CATEGORY_LABELS}
    for item in get_active_savings_instruments():
        category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1

    tax_params = resolve_effective_tax_parameters(
        tax_regime=tax_regime,
        slab_rate_pct=slab_rate_pct,
        surcharge_rate_pct=surcharge_rate_pct,
        effective_tax_rate_pct=effective_tax_rate_pct,
    )

    return {
        "instruments": enriched,
        "total_count": len(enriched),
        "category_counts": category_counts,
        "category_labels": SAVINGS_CATEGORY_LABELS,
        "macro_anchors": anchors,
        "tax_parameters": tax_params,
        "applied_filters": {
            "category": category or "ALL",
            "query": query or "",
            "tax_regime": tax_regime,
            "slab_rate_pct": slab_rate_pct,
            "surcharge_rate_pct": surcharge_rate_pct,
            "effective_tax_rate_pct": effective_tax_rate_pct,
            "is_senior": is_senior,
            "dicgc_only": dicgc_only,
            "sovereign_only": sovereign_only,
            "tax_80c_only": tax_80c_only,
            "sort_by": sort_key,
        },
    }


def get_savings_instrument_dossier(
    instrument_id: str,
    *,
    tax_regime: str = "NEW_115BAC",
    slab_rate_pct: float = 30.0,
    surcharge_rate_pct: float = 0.0,
    effective_tax_rate_pct: Optional[float] = None,
    is_senior: bool = False,
    principal_inr: float = 500000.0,
) -> Optional[Dict[str, Any]]:
    """Compiles a complete source-grounded analytical dossier for a single savings instrument."""
    inst = get_savings_instrument_by_id(instrument_id)
    if not inst:
        return None

    anchors = get_live_macro_anchors()
    tax_eval = evaluate_savings_post_tax(
        inst,
        tax_regime=tax_regime,
        slab_rate_pct=slab_rate_pct,
        surcharge_rate_pct=surcharge_rate_pct,
        effective_tax_rate_pct=effective_tax_rate_pct,
        is_senior=is_senior,
        principal_inr=principal_inr,
        macro_anchors=anchors,
    )
    alt_regime = "OLD_REGIME" if str(tax_regime).upper() == "NEW_115BAC" else "NEW_115BAC"
    alt_tax_eval = evaluate_savings_post_tax(
        inst,
        tax_regime=alt_regime,
        slab_rate_pct=slab_rate_pct,
        surcharge_rate_pct=surcharge_rate_pct,
        effective_tax_rate_pct=effective_tax_rate_pct,
        is_senior=is_senior,
        principal_inr=principal_inr,
        macro_anchors=anchors,
    )

    slab_matrix = []
    for slab, sur in (
        (0.0, 0.0),
        (5.0, 0.0),
        (10.0, 0.0),
        (15.0, 0.0),
        (20.0, 0.0),
        (30.0, 0.0),
        (30.0, 10.0),
        (30.0, 15.0),
        (30.0, 25.0),
        (30.0, 37.0),
    ):
        s_new = evaluate_savings_post_tax(
            inst,
            tax_regime="NEW_115BAC",
            slab_rate_pct=slab,
            surcharge_rate_pct=sur,
            is_senior=is_senior,
            principal_inr=principal_inr,
            macro_anchors=anchors,
        )
        s_old = evaluate_savings_post_tax(
            inst,
            tax_regime="OLD_REGIME",
            slab_rate_pct=slab,
            surcharge_rate_pct=sur,
            is_senior=is_senior,
            principal_inr=principal_inr,
            macro_anchors=anchors,
        )
        slab_label = f"{slab:.0f}%" if sur == 0.0 else f"{slab:.0f}% + {sur:.0f}% HNI"
        slab_matrix.append(
            {
                "slab_pct": slab,
                "surcharge_pct": sur,
                "slab_label": slab_label,
                "new_effective_slab_pct": s_new["effective_marginal_slab_pct"],
                "old_effective_slab_pct": s_old["effective_marginal_slab_pct"],
                "new_regime_post_tax_pct": s_new["post_tax_yield_pct"],
                "new_regime_real_pct": s_new["fisher_real_yield_pct"],
                "old_regime_post_tax_pct": s_old["post_tax_yield_pct"],
                "old_regime_real_pct": s_old["fisher_real_yield_pct"],
            }
        )

    contagion = evaluate_fd_issuer_contagion_bridge(inst)
    history = get_savings_rate_history(inst["instrument_id"])
    safe_tenure = min(DICGC_MAX_TENURE_MONTHS, max(12, int(inst["tenure_max_months"] or 36)))
    dicgc_cumulative = (
        compute_dicgc_safe_principal(
            annual_rate_pct=tax_eval["nominal_rate_pct"],
            tenure_months=safe_tenure,
            compounding_freq=inst["compounding_freq"],
            payout_mode="CUMULATIVE",
            dicgc_limit_inr=inst["dicgc_limit_inr"],
        )
        if inst["dicgc_insured"] and inst["dicgc_limit_inr"] > 0
        else None
    )
    dicgc_payout = (
        compute_dicgc_safe_principal(
            annual_rate_pct=tax_eval["nominal_rate_pct"],
            tenure_months=safe_tenure,
            compounding_freq=inst["compounding_freq"],
            payout_mode="QUARTERLY_PAYOUT",
            dicgc_limit_inr=inst["dicgc_limit_inr"],
        )
        if inst["dicgc_insured"] and inst["dicgc_limit_inr"] > 0
        else None
    )

    peers = [
        p
        for p in get_enriched_savings_directory(
            category=inst["category"],
            tax_regime=tax_regime,
            slab_rate_pct=slab_rate_pct,
            surcharge_rate_pct=surcharge_rate_pct,
            effective_tax_rate_pct=effective_tax_rate_pct,
            is_senior=is_senior,
        )["instruments"]
        if p["instrument_id"] != inst["instrument_id"]
    ][:4]

    return {
        "instrument": inst,
        "tax_eval": tax_eval,
        "alt_regime_eval": alt_tax_eval,
        "slab_matrix": slab_matrix,
        "contagion": contagion,
        "rate_history": history,
        "dicgc_cumulative": dicgc_cumulative,
        "dicgc_quarterly_payout": dicgc_payout,
        "macro_anchors": anchors,
        "category_peers": peers,
    }
