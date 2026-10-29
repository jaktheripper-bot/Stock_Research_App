"""
Unified 360° Forensic Health Sieve
===================================
Synthesizes the Chanakya 10-Point Deterministic Clean-Room Filter with strict
fail-closed disclosure counting so missing statutory filings never masquerade
as '10/10 Clean Accounting Check'.
"""

from typing import Dict, Any, Optional
import logging
import math

from core.cortex.chanakya import ChanakyaGate

logger = logging.getLogger("equity_research.core.analysis.forensic_sieve")

_STATUTORY_FIELD_GROUPS = (
    ("operating_cash_flow_cr", "cfo_cr", "cfo"),
    ("ebitda_cr", "ebitda", "operating_margin", "opm"),
    ("reported_pbt_cr", "pbt_cr", "pat_cr", "pat"),
    ("tax_paid_cr", "tax_cr"),
    ("promoter_pledge_pct", "pledge_pct"),
    ("auditor_replacements_3y",),
    ("contingent_liabilities_cr", "rpt_transaction_cr", "dso_days"),
    ("tangible_net_worth_cr", "net_worth_cr", "pb_ratio", "roce", "roe"),
    ("market_cap_cr", "mcap_cr", "market_cap", "base_mcap"),
    ("debt_to_equity", "interest_coverage_ratio"),
)


def _first_valid_float(d: Dict[str, Any], keys: tuple) -> Optional[float]:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        s = str(v).strip().replace(",", "").replace("%", "")
        if not s or s.upper() in ("N/A", "NONE", "NAN", "NM", "-", "—"):
            continue
        try:
            f = float(s)
            if not math.isnan(f) and not math.isinf(f):
                return f
        except (TypeError, ValueError):
            continue
    return None


def _has_valid_disclosure(d: Dict[str, Any], keys: tuple) -> bool:
    return _first_valid_float(d, keys) is not None


def _build_partial_checks(d: Dict[str, Any]) -> tuple[list[Dict[str, str]], list[str], int]:
    """
    Evaluates disclosed balance-sheet, profitability, and governance schedules
    without fabricating 'Verified Clean' verdicts on undisclosed CARO/Reg 31 fields.
    Returns (checks_detail, red_flags, failed_disclosed_count).
    """
    checks_detail: list[Dict[str, str]] = []
    red_flags: list[str] = []
    failed_disclosed = 0

    cfo = _first_valid_float(d, ("operating_cash_flow_cr", "cfo_cr", "cfo"))
    ebitda = _first_valid_float(d, ("ebitda_cr", "ebitda"))
    opm = _first_valid_float(d, ("operating_margin", "opm"))
    if cfo is not None and ebitda is not None:
        if ebitda > 0 and (cfo / ebitda) < ChanakyaGate.MIN_CFO_EBITDA_RATIO:
            failed_disclosed += 1
            red_flags.append("SUB_PAR_CFO_CONVERSION")
            checks_detail.append({"label": "CFO / EBITDA Cash Quality", "verdict": f"Weak ({cfo / ebitda:.2f}x)", "color": "#f59e0b"})
        elif ebitda <= 0 and cfo < ebitda:
            failed_disclosed += 1
            red_flags.append("EBITDA_CFO_DEFICIT")
            checks_detail.append({"label": "CFO / EBITDA Cash Quality", "verdict": "Cash Deficit", "color": "#ef4444"})
        else:
            ratio_txt = f"{cfo / ebitda:.2f}x" if ebitda > 0 else "Positive CFO"
            checks_detail.append({"label": "CFO / EBITDA Cash Quality", "verdict": f"Verified ({ratio_txt})", "color": "#10b981"})
    elif opm is not None:
        if opm <= 0.0:
            failed_disclosed += 1
            red_flags.append("OPERATING_MARGIN_DEFICIT")
            checks_detail.append({"label": "Operating Margin & Cash Quality", "verdict": f"Operating Loss ({opm:.1f}%)", "color": "#ef4444"})
        else:
            checks_detail.append({"label": "Operating Margin & Cash Quality", "verdict": f"OPM {opm:.1f}% (CFO Pending)", "color": "#10b981"})
    else:
        checks_detail.append({"label": "CFO / EBITDA Cash Quality", "verdict": "Pending Cash-Flow Filing", "color": "#94a3b8"})

    de = _first_valid_float(d, ("debt_to_equity",))
    icr = _first_valid_float(d, ("interest_coverage_ratio",))
    is_fin = bool(d.get("is_financial_sector") or ("BANK" in str(d.get("sector", "")).upper()))
    if is_fin:
        checks_detail.append({"label": "Solvency & Leverage Profile", "verdict": "BFSI Capital Regime", "color": "#38bdf8"})
    elif de is not None or icr is not None:
        de_bad = de is not None and de > ChanakyaGate.MAX_DEBT_TO_EQUITY
        icr_bad = icr is not None and icr < ChanakyaGate.MIN_INTEREST_COVERAGE
        if de_bad or icr_bad:
            failed_disclosed += 1
            red_flags.append("ELEVATED_LEVERAGE_BURDEN")
            metric_lbl = f"D/E {de:.2f}x" if de is not None else f"ICR {icr:.2f}x"
            checks_detail.append({"label": "Solvency & Leverage Profile", "verdict": f"Elevated ({metric_lbl})", "color": "#f59e0b"})
        else:
            metric_lbl = f"D/E {de:.2f}x" if de is not None else f"ICR {icr:.2f}x"
            checks_detail.append({"label": "Solvency & Leverage Profile", "verdict": f"Conservative ({metric_lbl})", "color": "#10b981"})
    else:
        checks_detail.append({"label": "Solvency & Leverage Profile", "verdict": "Pending Balance Sheet", "color": "#94a3b8"})

    roce = _first_valid_float(d, ("roce",))
    roe = _first_valid_float(d, ("roe",))
    nw = _first_valid_float(d, ("tangible_net_worth_cr", "net_worth_cr", "pb_ratio"))
    if roce is not None or roe is not None or nw is not None:
        cap_val = roce if roce is not None else (roe if roe is not None else nw)
        cap_lbl = f"ROCE {roce:.1f}%" if roce is not None else (f"ROE {roe:.1f}%" if roe is not None else f"P/B {nw:.2f}x")
        if cap_val is not None and cap_val <= 0:
            failed_disclosed += 1
            red_flags.append("CAPITAL_EROSION_DEFICIT")
            checks_detail.append({"label": "Capital Efficiency & Equity Base", "verdict": f"Eroded ({cap_lbl})", "color": "#ef4444"})
        else:
            checks_detail.append({"label": "Capital Efficiency & Equity Base", "verdict": f"Healthy ({cap_lbl})", "color": "#10b981"})
    else:
        checks_detail.append({"label": "Capital Efficiency & Equity Base", "verdict": "Pending Return Schedule", "color": "#94a3b8"})

    pledge = _first_valid_float(d, ("promoter_pledge_pct", "pledge_pct"))
    auditor = _first_valid_float(d, ("auditor_replacements_3y",))
    if pledge is not None or auditor is not None:
        if (pledge is not None and pledge > ChanakyaGate.MAX_PROMOTER_PLEDGE_PCT) or (auditor is not None and auditor >= 2):
            failed_disclosed += 1
            red_flags.append("GOVERNANCE_PLEDGE_OR_AUDITOR_FLAG")
            checks_detail.append({"label": "Promoter Pledge & CARO Audit", "verdict": "Governance Flag", "color": "#ef4444"})
        else:
            p_lbl = f"{pledge:.1f}% Pledged" if pledge is not None else "Stable Audit Desk"
            checks_detail.append({"label": "Promoter Pledge & CARO Audit", "verdict": p_lbl, "color": "#10b981"})
    else:
        checks_detail.append({"label": "Promoter Pledge & CARO Audit", "verdict": "Pending Reg 31 / CARO", "color": "#94a3b8"})

    return checks_detail, red_flags, failed_disclosed


def evaluate_forensic_sieve(
    symbol: str,
    fundamentals: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    safe_fund = dict(fundamentals) if isinstance(fundamentals, dict) else {}
    if not safe_fund.get("symbol") and not safe_fund.get("ticker"):
        safe_fund["symbol"] = str(symbol or "UNKNOWN").upper().strip()

    disclosed_count = sum(1 for grp in _STATUTORY_FIELD_GROUPS if _has_valid_disclosure(safe_fund, grp))

    # Fail-closed gate: require at least 5 of 10 statutory forensic input groups to issue a Clean-Room pass
    if disclosed_count < 5:
        checks_detail, partial_flags, failed_disclosed = _build_partial_checks(safe_fund)
        passed_partial = max(0, disclosed_count - failed_disclosed)
        partial_score = 50.0 if disclosed_count == 0 else max(35.0, round(80.0 - (failed_disclosed * 15.0), 1))
        return {
            "verdict": "INSUFFICIENT_DISCLOSURES",
            "badge_label": f"Partial Filing ({disclosed_count}/10 Verified)",
            "badge_color": "#94a3b8" if failed_disclosed == 0 else "#f59e0b",
            "score": partial_score,
            "total_checks": 10,
            "passed_count": passed_partial,
            "failed_count": failed_disclosed,
            "disclosed_count": disclosed_count,
            "red_flags": partial_flags,
            "failed_checks": [],
            "checks_detail": checks_detail,
            "summary": (
                f"{disclosed_count} of 10 statutory forensic schedules verified from exchange filings; "
                f"full 'Clean Accounting Check' certification awaits Regulation 31 / CARO cash-flow schedule ingestion."
            ),
            "status": "INSUFFICIENT_DISCLOSURES",
            "forensic_status": "INSUFFICIENT_DISCLOSURES",
            "chanakya_status": "INSUFFICIENT_DISCLOSURES",
        }

    chanakya_res = ChanakyaGate.evaluate_from_dict(safe_fund, mode="SOFT")
    red_flags = list(chanakya_res.flags)
    score = chanakya_res.clean_room_score
    status = chanakya_res.status

    if status == "PRISTINE_CLEAN" and len(red_flags) == 0:
        verdict = "PRISTINE_CLEAN"
        badge_label = "Clean Accounting Check"
        badge_color = "#10b981"
        summary = (
            f"Zero forensic or governance irregularities identified across {disclosed_count} verified statutory accounting tests. "
            f"Cash conversion is backed by verified statutory filings."
        )
    elif len(red_flags) <= 2:
        verdict = "MONITOR_WATCHLIST"
        badge_label = f"Watchlist ({len(red_flags)} Flags)"
        badge_color = "#f59e0b"
        summary = (
            f"Minor accounting anomalies or working capital drag noted ({'; '.join(red_flags[:2])}). "
            f"Maintain monitoring on cash flow conversion and debt covenants."
        )
    else:
        verdict = "ELEVATED_GOVERNANCE_RISK"
        badge_label = f"Governance Risk ({len(red_flags)} Flags)"
        badge_color = "#ef4444"
        summary = (
            f"Multiple forensic warning signals triggered ({'; '.join(red_flags[:3])}). "
            f"Warrants caution regarding balance sheet quality and accounting transparency."
        )

    passed_checks = [c.check_name for c in chanakya_res.checks if c.passed]
    failed_checks = [{"name": c.check_name, "severity": c.severity, "msg": c.message} for c in chanakya_res.checks if not c.passed]
    label_map = {
        "cfo_to_ebitda": "CFO / EBITDA Cash Quality",
        "promoter_pledge": "Promoter Pledge Velocity",
        "auditor_churn": "Auditor Tenure & Resignations",
        "working_capital_drag": "Working Capital Drag & DSO",
        "solvency_coverage": "Solvency & Debt Coverage",
    }
    checks_detail = []
    for c in chanakya_res.checks:
        if c.check_name in label_map:
            checks_detail.append({
                "label": label_map[c.check_name],
                "verdict": "Verified Clean" if c.passed else ("Critical Flag" if c.severity == "CRITICAL" else "Watchlist"),
                "color": "#10b981" if c.passed else ("#ef4444" if c.severity == "CRITICAL" else "#f59e0b"),
            })

    return {
        "verdict": verdict,
        "badge_label": badge_label,
        "badge_color": badge_color,
        "score": score,
        "total_checks": len(chanakya_res.checks),
        "passed_count": len(passed_checks),
        "failed_count": len(failed_checks),
        "disclosed_count": disclosed_count,
        "red_flags": red_flags,
        "failed_checks": failed_checks,
        "checks_detail": checks_detail,
        "summary": summary,
        "status": status,
        "forensic_status": status,
        "chanakya_status": status,
    }
