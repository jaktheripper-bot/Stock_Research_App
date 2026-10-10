"""
Unified 360° Forensic Health Sieve
===================================
Synthesizes the Chanakya 10-Point Deterministic Clean-Room Filter, 
accruals analysis, promoter pledge acceleration, and auditor stability
into an authoritative institutional governance scorecard.
"""

from typing import Dict, Any, List, Optional
import logging

from core.cortex.chanakya import ChanakyaGate, ChanakyaResult

logger = logging.getLogger("equity_research.core.analysis.forensic_sieve")


def evaluate_forensic_sieve(
    symbol: str,
    fundamentals: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Evaluates corporate governance, accounting integrity, and balance sheet truth.
    Returns composite score, traffic light badge, and granular red flags.
    Hardened against null fundamentals and malformed records.
    """
    safe_fund = dict(fundamentals) if isinstance(fundamentals, dict) else {}
    if not safe_fund.get("symbol") and not safe_fund.get("ticker"):
        safe_fund["symbol"] = str(symbol or "UNKNOWN").upper().strip()

    # 1. Run ChanakyaGate 10-Point Clean-Room Sieve in SOFT diagnostic mode
    chanakya_res = ChanakyaGate.evaluate_from_dict(safe_fund, mode="SOFT")

    # 2. Extract flags and analyze severity
    red_flags = list(chanakya_res.flags)
    score = chanakya_res.clean_room_score
    status = chanakya_res.status

    # 3. Classify traffic-light regime
    if status == "PRISTINE_CLEAN" and len(red_flags) == 0:
        verdict = "PRISTINE_CLEAN"
        badge_label = "Clean Forensic Audit"
        badge_color = "#10b981"
        summary = (
            f"Zero forensic or governance irregularities identified across 10 statutory accounting tests. "
            f"Cash conversion is backed by verified statutory filings."
        )
    elif len(red_flags) <= 2:
        verdict = "MONITOR_WATCHLIST"
        badge_label = f"Watchlist ({len(red_flags)} Flags)"
        badge_color = "#f59e0b"
        summary = (
            f"Minor accounting anomalies or working capital drag noted ({'; '.join(red_flags[:2])}). "
            f"Maintain surveillance on cash flow conversion and debt covenants."
        )
    else:
        verdict = "ELEVATED_GOVERNANCE_RISK"
        badge_label = f"Governance Risk ({len(red_flags)} Flags)"
        badge_color = "#ef4444"
        summary = (
            f"Multiple forensic warning signals triggered ({'; '.join(red_flags[:3])}). "
            f"Warrants institutional caution regarding balance sheet quality and accounting transparency."
        )

    # Granular check details
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
        "red_flags": red_flags,
        "failed_checks": failed_checks,
        "summary": summary,
        "chanakya_status": status,
    }
