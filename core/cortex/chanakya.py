"""
Chanakya Clean-Room Forensic Screening Filter
============================================
Phase 1 Proprietary Architecture (Anvik Cortex Engine).

A deterministic 10-point mathematical forensic sieve designed to:
1. Screen out fundamentally uninvestable and forensic-deficit equities before expensive LLM synthesis.
2. Slash downstream compute consumption in batch discovery screening pipelines.
3. Provide non-exclusionary soft forensic diagnostic badges for human equity research dossiers.

The 10-Point Deterministic Forensic Checks:
1. CFO to EBITDA Conversion Check (Operating Cash Quality)
2. Statutory Tax Wedge / Phantom Profit Check (Effective Tax Rate vs PBT)
3. Promoter Pledge Acceleration / Velocity Sieve
4. Auditor Churn / Governance Resignation Sieve
5. Contingent Liabilities to Net Worth Ratio (Off-Balance Sheet Drag)
6. Related-Party Transactions (RPT) Revenue Leakage Sieve
7. Receivables / Working Capital Drag Check (DSO Expansion vs Sales Growth)
8. Solvency & Debt Service Coverage (ICR & D/E for non-NBFCs)
9. Tangible Capital & Retained Earnings Erosion Check
10. Shell Company & Liquidity Viability Threshold
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import math
import logging

logger = logging.getLogger(__name__)


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        if math.isnan(v) or math.isinf(v):
            return default
        return float(v)
    try:
        clean = str(v).strip().replace(",", "").replace("%", "")
        f = float(clean)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    f = _safe_float(v, default=float(default))
    return int(round(f))


@dataclass
class ChanakyaCheckResult:
    check_name: str
    passed: bool
    severity: str  # "INFO", "WARNING", "CRITICAL"
    metric_value: float
    threshold: float
    message: str


@dataclass
class ChanakyaResult:
    symbol: str
    overall_passed: bool
    clean_room_score: float  # 0.0 to 100.0 (100 = Pristine forensic health)
    status: str  # "PRISTINE_CLEAN", "CAUTIONARY_DEFICIT", "FORENSIC_EXCLUSION"
    mode: str  # "STRICT" or "SOFT"
    checks: List[ChanakyaCheckResult] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    summary: str = ""


class ChanakyaGate:
    """
    Deterministic Clean-Room Screening Filter for Indian Capital Markets.
    """

    # Threshold constants
    MIN_CFO_EBITDA_RATIO: float = 0.35
    MIN_EFFECTIVE_TAX_RATE: float = 15.0  # Statutory minimum corporate floor
    MAX_PROMOTER_PLEDGE_PCT: float = 20.0
    MAX_PLEDGE_QOQ_DELTA: float = 3.0
    MAX_AUDITOR_REPLACEMENTS_3Y: int = 1
    MAX_CONTINGENT_LIAB_RATIO: float = 50.0  # % of Net Worth
    MAX_RPT_REVENUE_PCT: float = 15.0  # % of Net Sales
    MAX_DSO_GROWTH_PREMIUM: float = 30.0  # DSO expanding 30% faster than sales
    MIN_INTEREST_COVERAGE: float = 1.75
    MAX_DEBT_TO_EQUITY: float = 2.0
    MIN_MARKET_CAP_CR: float = 25.0

    @classmethod
    def evaluate(
        cls,
        symbol: str,
        operating_cash_flow_cr: float,
        ebitda_cr: float,
        reported_pbt_cr: float,
        tax_paid_cr: float,
        promoter_pledge_pct: float = 0.0,
        promoter_pledge_qoq_delta: float = 0.0,
        auditor_replacements_3y: int = 0,
        contingent_liabilities_cr: float = 0.0,
        net_worth_cr: float = 0.0,
        rpt_transaction_cr: float = 0.0,
        net_revenue_cr: float = 0.0,
        dso_days: float = 0.0,
        dso_prior_year: float = 0.0,
        sales_growth_pct: float = 0.0,
        interest_coverage_ratio: float = 10.0,
        debt_to_equity: float = 0.0,
        is_financial_sector: bool = False,
        tangible_net_worth_cr: float = 10.0,
        retained_earnings_cr: float = 10.0,
        market_cap_cr: float = 100.0,
        mode: str = "STRICT",
    ) -> ChanakyaResult:
        """
        Executes the 10-point deterministic forensic sieve.
        """
        checks: List[ChanakyaCheckResult] = []
        flags: List[str] = []
        critical_failures = 0
        warning_failures = 0

        # 1. CFO to EBITDA Conversion Check
        if ebitda_cr > 0:
            cfo_ratio = operating_cash_flow_cr / ebitda_cr
            if cfo_ratio < 0:
                p1 = False
                sev = "CRITICAL"
                critical_failures += 1
                msg = f"Negative cash conversion: CFO (₹{operating_cash_flow_cr:.1f} Cr) is negative while EBITDA (₹{ebitda_cr:.1f} Cr) is positive."
                flags.append("NEGATIVE_CFO_EBITDA_DIVERGENCE")
            elif cfo_ratio < cls.MIN_CFO_EBITDA_RATIO:
                p1 = False
                sev = "WARNING"
                warning_failures += 1
                msg = f"Weak cash conversion: CFO/EBITDA of {cfo_ratio:.2f} is below statutory benchmark ({cls.MIN_CFO_EBITDA_RATIO:.2f})."
                flags.append("SUB_PAR_CFO_CONVERSION")
            else:
                p1 = True
                sev = "INFO"
                msg = f"Robust cash conversion: CFO/EBITDA ratio at {cfo_ratio:.2f}."
        else:
            p1 = operating_cash_flow_cr >= ebitda_cr
            sev = "WARNING" if not p1 else "INFO"
            if not p1:
                warning_failures += 1
                flags.append("EBITDA_CFO_DEFICIT")
            msg = f"Trough/Operating loss regime: EBITDA ₹{ebitda_cr:.1f} Cr, CFO ₹{operating_cash_flow_cr:.1f} Cr."

        checks.append(ChanakyaCheckResult("cfo_to_ebitda", p1, sev, round(operating_cash_flow_cr, 2), cls.MIN_CFO_EBITDA_RATIO, msg))

        # 2. Statutory Tax Wedge / Phantom Profit Check
        if reported_pbt_cr > 5.0:  # Material profit
            etr = (tax_paid_cr / reported_pbt_cr) * 100.0 if reported_pbt_cr > 0 else 0.0
            if etr < 8.0:
                p2 = False
                sev = "CRITICAL"
                critical_failures += 1
                msg = f"Phantom profit warning: Effective tax paid ({etr:.1f}%) is far below statutory floor ({cls.MIN_EFFECTIVE_TAX_RATE}%)."
                flags.append("SUSPICIOUS_STATUTORY_TAX_RATE")
            elif etr < cls.MIN_EFFECTIVE_TAX_RATE:
                p2 = False
                sev = "WARNING"
                warning_failures += 1
                msg = f"Low effective tax rate: {etr:.1f}% vs {cls.MIN_EFFECTIVE_TAX_RATE}% statutory benchmark."
                flags.append("SUB_STATUTORY_TAX_RATE")
            else:
                p2 = True
                sev = "INFO"
                msg = f"Healthy statutory tax compliance: ETR at {etr:.1f}%."
        else:
            p2 = True
            sev = "INFO"
            etr = 25.0
            msg = "Low or negative PBT base; phantom profit check neutral."

        checks.append(ChanakyaCheckResult("statutory_tax_wedge", p2, sev, round(etr, 2), cls.MIN_EFFECTIVE_TAX_RATE, msg))

        # 3. Promoter Pledge Acceleration Sieve
        if promoter_pledge_pct > 50.0 or promoter_pledge_qoq_delta > 5.0:
            p3 = False
            sev = "CRITICAL"
            critical_failures += 1
            msg = f"Dangerous promoter pledge encumbrance: {promoter_pledge_pct:.1f}% pledged (QoQ surge +{promoter_pledge_qoq_delta:.1f}%)."
            flags.append("CRITICAL_PROMOTER_PLEDGE_ENCUMBRANCE")
        elif promoter_pledge_pct > cls.MAX_PROMOTER_PLEDGE_PCT or promoter_pledge_qoq_delta > cls.MAX_PLEDGE_QOQ_DELTA:
            p3 = False
            sev = "WARNING"
            warning_failures += 1
            msg = f"Elevated promoter pledge: {promoter_pledge_pct:.1f}% pledged (QoQ surge +{promoter_pledge_qoq_delta:.1f}%)."
            flags.append("ELEVATED_PROMOTER_PLEDGE")
        else:
            p3 = True
            sev = "INFO"
            msg = f"Unencumbered promoter shareholding: {promoter_pledge_pct:.1f}% pledged."

        checks.append(ChanakyaCheckResult("promoter_pledge", p3, sev, round(promoter_pledge_pct, 2), cls.MAX_PROMOTER_PLEDGE_PCT, msg))

        # 4. Auditor Churn / Resignation Sieve
        if auditor_replacements_3y >= 2:
            p4 = False
            sev = "CRITICAL"
            critical_failures += 1
            msg = f"High statutory auditor churn: {auditor_replacements_3y} replacements in trailing 3 years."
            flags.append("EXCESSIVE_AUDITOR_CHURN")
        else:
            p4 = True
            sev = "INFO"
            msg = f"Stable statutory audit tenure: {auditor_replacements_3y} replacements in trailing 3 years."

        checks.append(ChanakyaCheckResult("auditor_churn", p4, sev, float(auditor_replacements_3y), float(cls.MAX_AUDITOR_REPLACEMENTS_3Y), msg))

        # 5. Contingent Liabilities Drag (% of Net Worth)
        if net_worth_cr > 0:
            cont_ratio = (contingent_liabilities_cr / net_worth_cr) * 100.0
            if cont_ratio > 100.0:
                p5 = False
                sev = "CRITICAL"
                critical_failures += 1
                msg = f"Severe contingent liability overhang: ₹{contingent_liabilities_cr:.1f} Cr exceeds 100% of Net Worth ({cont_ratio:.1f}%)."
                flags.append("CONTINGENT_LIABILITY_OVERHANG")
            elif cont_ratio > cls.MAX_CONTINGENT_LIAB_RATIO:
                p5 = False
                sev = "WARNING"
                warning_failures += 1
                msg = f"High contingent liabilities: ₹{contingent_liabilities_cr:.1f} Cr is {cont_ratio:.1f}% of Net Worth."
                flags.append("ELEVATED_CONTINGENT_LIABILITIES")
            else:
                p5 = True
                sev = "INFO"
                msg = f"Manageable contingent liabilities: {cont_ratio:.1f}% of Net Worth."
        else:
            p5 = contingent_liabilities_cr <= 0
            sev = "CRITICAL" if not p5 else "INFO"
            if not p5:
                critical_failures += 1
                flags.append("CONTINGENT_RISK_ZERO_EQUITY")
            cont_ratio = 999.0 if not p5 else 0.0
            msg = "Zero or negative net worth base."

        checks.append(ChanakyaCheckResult("contingent_liabilities", p5, sev, round(cont_ratio, 2), cls.MAX_CONTINGENT_LIAB_RATIO, msg))

        # 6. Related-Party Transactions (RPT) Sieve
        if net_revenue_cr > 0:
            rpt_ratio = (rpt_transaction_cr / net_revenue_cr) * 100.0
            if rpt_ratio > 25.0:
                p6 = False
                sev = "CRITICAL"
                critical_failures += 1
                msg = f"Aggressive RPT revenue tunneling: RPT ₹{rpt_transaction_cr:.1f} Cr is {rpt_ratio:.1f}% of Net Revenue."
                flags.append("AGGRESSIVE_RPT_LEAKAGE")
            elif rpt_ratio > cls.MAX_RPT_REVENUE_PCT:
                p6 = False
                sev = "WARNING"
                warning_failures += 1
                msg = f"Elevated related-party exposure: RPT is {rpt_ratio:.1f}% of Net Revenue."
                flags.append("ELEVATED_RPT_VOLUME")
            else:
                p6 = True
                sev = "INFO"
                msg = f"Controlled related-party volume: {rpt_ratio:.1f}% of Net Revenue."
        else:
            p6 = rpt_transaction_cr <= 0
            sev = "WARNING" if not p6 else "INFO"
            if not p6:
                warning_failures += 1
            rpt_ratio = 0.0
            msg = "Low revenue base."

        checks.append(ChanakyaCheckResult("rpt_leakage", p6, sev, round(rpt_ratio, 2), cls.MAX_RPT_REVENUE_PCT, msg))

        # 7. Receivables / Working Capital Drag
        if dso_prior_year > 0 and dso_days > 0:
            dso_growth_pct = ((dso_days - dso_prior_year) / dso_prior_year) * 100.0
            dso_spread = dso_growth_pct - max(sales_growth_pct, 0.0)
            if dso_spread > cls.MAX_DSO_GROWTH_PREMIUM and dso_days > 90:
                p7 = False
                sev = "WARNING"
                warning_failures += 1
                msg = f"Working capital drag: DSO surged {dso_growth_pct:.1f}% YoY (to {dso_days:.0f} days), outpacing sales growth by {dso_spread:.1f}%."
                flags.append("RECEIVABLES_BALLOONING_DRAG")
            else:
                p7 = True
                sev = "INFO"
                msg = f"Normal cash collection cycle: DSO at {dso_days:.0f} days."
        else:
            p7 = True
            sev = "INFO"
            dso_spread = 0.0
            msg = "Standard working capital trajectory."

        checks.append(ChanakyaCheckResult("working_capital_drag", p7, sev, round(dso_days, 1), 90.0, msg))

        # 8. Solvency & Debt Service Coverage
        if not is_financial_sector:
            if interest_coverage_ratio < 1.0 or debt_to_equity > 3.0:
                p8 = False
                sev = "CRITICAL"
                critical_failures += 1
                msg = f"Solvency distress: ICR at {interest_coverage_ratio:.2f}x (<1.0x) or D/E at {debt_to_equity:.2f}x (>3.0x)."
                flags.append("SOLVENCY_DISTRESS_RISK")
            elif interest_coverage_ratio < cls.MIN_INTEREST_COVERAGE or debt_to_equity > cls.MAX_DEBT_TO_EQUITY:
                p8 = False
                sev = "WARNING"
                warning_failures += 1
                msg = f"Elevated balance sheet leverage: ICR at {interest_coverage_ratio:.2f}x, D/E at {debt_to_equity:.2f}x."
                flags.append("ELEVATED_LEVERAGE_BURDEN")
            else:
                p8 = True
                sev = "INFO"
                msg = f"Conservative debt profile: ICR at {interest_coverage_ratio:.2f}x, D/E at {debt_to_equity:.2f}x."
        else:
            p8 = True
            sev = "INFO"
            msg = "Financial sector exempted from standard D/E and ICR constraints."

        checks.append(ChanakyaCheckResult("solvency_coverage", p8, sev, round(interest_coverage_ratio, 2), cls.MIN_INTEREST_COVERAGE, msg))

        # 9. Tangible Capital & Retained Earnings Check
        if tangible_net_worth_cr <= 0 or retained_earnings_cr < 0:
            p9 = False
            sev = "CRITICAL"
            critical_failures += 1
            msg = f"Eroded net worth: Tangible Net Worth ₹{tangible_net_worth_cr:.1f} Cr, Retained Earnings ₹{retained_earnings_cr:.1f} Cr."
            flags.append("CAPITAL_EROSION_DEFICIT")
        else:
            p9 = True
            sev = "INFO"
            msg = f"Positive retained capital base: Net Worth ₹{tangible_net_worth_cr:.1f} Cr."

        checks.append(ChanakyaCheckResult("capital_erosion", p9, sev, round(tangible_net_worth_cr, 2), 0.0, msg))

        # 10. Shell Company & Liquidity Viability Threshold
        if market_cap_cr < cls.MIN_MARKET_CAP_CR:
            p10 = False
            sev = "CRITICAL"
            critical_failures += 1
            msg = f"Illiquid shell risk: Market capitalization ₹{market_cap_cr:.1f} Cr is below institutional threshold (₹{cls.MIN_MARKET_CAP_CR} Cr)."
            flags.append("SUB_SCALE_ILLIQUID_SHELL")
        else:
            p10 = True
            sev = "INFO"
            msg = f"Viable enterprise scale: Market capitalization ₹{market_cap_cr:.1f} Cr."

        checks.append(ChanakyaCheckResult("shell_liquidity_threshold", p10, sev, round(market_cap_cr, 1), cls.MIN_MARKET_CAP_CR, msg))

        # Compute Clean-Room Score (0 to 100)
        # 100 base score, -15 per critical failure, -5 per warning failure
        deductions = (critical_failures * 15.0) + (warning_failures * 5.0)
        clean_room_score = max(0.0, min(100.0, 100.0 - deductions))

        # Determine overall pass/fail status
        if mode.upper() == "STRICT":
            # In strict mode: 0 critical failures, and max 1 warning allowed
            overall_passed = (critical_failures == 0) and (warning_failures <= 1)
        else:
            # In soft mode: non-exclusionary, fails only on catastrophic multiple red flags
            overall_passed = critical_failures <= 1

        if clean_room_score >= 80.0 and critical_failures == 0:
            status = "PRISTINE_CLEAN"
        elif clean_room_score >= 50.0:
            status = "CAUTIONARY_DEFICIT"
        else:
            status = "FORENSIC_EXCLUSION"

        summary = (
            f"Forensic Clean-Room Sieve: {status} (Score {clean_room_score:.1f}/100). "
            f"{'Passed clean-room filter.' if overall_passed else 'Excluded due to forensic flags.'} "
            f"Critical Flags: {critical_failures}, Warnings: {warning_failures}."
        )

        return ChanakyaResult(
            symbol=symbol,
            overall_passed=overall_passed,
            clean_room_score=round(clean_room_score, 1),
            status=status,
            mode=mode.upper(),
            checks=checks,
            flags=flags,
            summary=summary,
        )

    @classmethod
    def evaluate_from_dict(cls, data: Optional[Dict[str, Any]], mode: str = "STRICT") -> ChanakyaResult:
        """
        Convenience adapter to evaluate from standard stock dictionary or fundamentals payload.
        Hardened against null dictionaries, non-numeric strings, commas, and NaNs.
        """
        d = data if isinstance(data, dict) else {}
        symbol = str(d.get("symbol") or d.get("ticker") or "UNKNOWN").upper().strip()
        # Extract market cap in Crores safely (fundamentals.py provides market_cap in INR, or market_cap_cr)
        raw_mcap = d.get("market_cap_cr") or d.get("mcap_cr")
        if raw_mcap is None and d.get("market_cap"):
            # fundamentals.py uses market_cap in INR (e.g. 4.15e12) or in Cr if < 1e7
            val = _safe_float(d.get("market_cap"), default=0.0)
            raw_mcap = (val / 1e7) if val > 1e7 else val
        elif raw_mcap is None and d.get("base_mcap"):
            val = _safe_float(d.get("base_mcap"), default=0.0)
            raw_mcap = (val / 1e7) if val > 1e7 else val

        mcap = _safe_float(raw_mcap, default=100.0)
        if mcap <= 0:
            mcap = 100.0

        cfo = _safe_float(d.get("operating_cash_flow_cr") or d.get("cfo_cr"), default=15.0)
        ebitda = _safe_float(d.get("ebitda_cr") or d.get("ebitda"), default=20.0)
        pbt = _safe_float(d.get("reported_pbt_cr") or d.get("pbt_cr"), default=15.0)
        tax = _safe_float(d.get("tax_paid_cr") or d.get("tax_cr"), default=3.8)
        pledge = _safe_float(d.get("promoter_pledge_pct") or d.get("pledge_pct"), default=0.0)
        pledge_delta = _safe_float(d.get("promoter_pledge_qoq_delta"), default=0.0)
        auditor_churn = _safe_int(d.get("auditor_replacements_3y"), default=0)
        cont_liab = _safe_float(d.get("contingent_liabilities_cr"), default=0.0)
        net_worth = _safe_float(d.get("net_worth_cr") or d.get("tangible_net_worth_cr"), default=50.0)
        rpt = _safe_float(d.get("rpt_transaction_cr"), default=0.0)
        revenue = _safe_float(d.get("net_revenue_cr") or d.get("sales_cr"), default=100.0)
        dso = _safe_float(d.get("dso_days"), default=45.0)
        dso_prior = _safe_float(d.get("dso_prior_year"), default=45.0)
        sales_growth = _safe_float(d.get("sales_growth_3y") or d.get("sales_growth_pct"), default=15.0)
        de = _safe_float(d.get("debt_to_equity"), default=0.1)
        icr = _safe_float(d.get("interest_coverage_ratio"), default=10.0)
        is_fin = bool(d.get("is_financial_sector") or ("Bank" in str(d.get("sector", ""))))

        return cls.evaluate(
            symbol=symbol,
            operating_cash_flow_cr=cfo,
            ebitda_cr=ebitda,
            reported_pbt_cr=pbt,
            tax_paid_cr=tax,
            promoter_pledge_pct=pledge,
            promoter_pledge_qoq_delta=pledge_delta,
            auditor_replacements_3y=auditor_churn,
            contingent_liabilities_cr=cont_liab,
            net_worth_cr=net_worth,
            rpt_transaction_cr=rpt,
            net_revenue_cr=revenue,
            dso_days=dso,
            dso_prior_year=dso_prior,
            sales_growth_pct=sales_growth,
            interest_coverage_ratio=icr,
            debt_to_equity=de,
            is_financial_sector=is_fin,
            tangible_net_worth_cr=net_worth,
            retained_earnings_cr=net_worth * 0.7,
            market_cap_cr=mcap,
            mode=mode,
        )


def evaluate_from_dict(data: Dict[str, Any], mode: str = "SCREENING") -> ChanakyaScorecard:
    """Convenience module-level wrapper for ChanakyaGate.evaluate_from_dict."""
    return ChanakyaGate.evaluate_from_dict(data, mode=mode)
