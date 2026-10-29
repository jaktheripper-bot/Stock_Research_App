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
    ("ebitda_cr", "ebitda"),
    ("reported_pbt_cr", "pbt_cr", "pat_cr", "pat"),
    ("tax_paid_cr", "tax_cr"),
    ("promoter_pledge_pct", "pledge_pct"),
    ("auditor_replacements_3y",),
    ("contingent_liabilities_cr",),
    ("rpt_transaction_cr",),
    ("dso_days",),
    ("debt_to_equity", "interest_coverage_ratio"),
)


def _has_valid_disclosure(d: Dict[str, Any], keys: tuple) -> bool:
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
                return True
        except (TypeError, ValueError):
            continue
    return False


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
        return {
            "verdict": "INSUFFICIENT_DISCLOSURES",
            "badge_label": f"Partial Filing ({disclosed_count}/10 Verified)",
            "badge_color": "#94a3b8",
            "score": 50.0,
            "total_checks": 10,
            "passed_count": disclosed_count,
            "failed_count": 0,
            "disclosed_count": disclosed_count,
            "red_flags": [],
            "failed_checks": [],
            "summary": (
                f"Only {disclosed_count} of 10 statutory forensic line items are currently populated in structured cache; "
                f"withholding 'Clean Accounting Check' certification pending full Regulation 33 / CARO schedule ingestion."
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
        "summary": summary,
        "status": status,
        "forensic_status": status,
        "chanakya_status": status,
    }
