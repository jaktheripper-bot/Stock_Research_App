"""Institutional Mutual Fund Look-Through & Forensic Dossier Engine.

Enforces statutory and quantitative mathematical invariants for Mutual Fund Dossiers:
1. Withhold Composite Health Score (return None) whenever verified 7-pillar coverage < 70.0%.
2. Clamp Active Share strictly to [0.0, 100.0].
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

from core.analysis.fund_overlap_auditor import (
    compute_fund_forensic_lookthrough as _upstream_compute_lookthrough,
    parse_stock_report_health_matrix,
)
from core.analysis.mutual_funds_engine import (
    calculate_active_share as _upstream_calculate_active_share,
    BENCHMARK_PROXIES,
    EQUITY_HEALTH_DEFAULTS,
)
from core.db.mutual_funds import (
    get_mutual_fund_scheme,
    get_scheme_holdings,
    save_fund_forensic_dossier,
    get_fund_forensic_dossier,
)

logger = logging.getLogger(__name__)

MIN_VERIFIED_7PILLAR_COVERAGE_THRESHOLD = 70.0


def clamp_active_share(active_share: float) -> float:
    """Clamps Active Share to the valid mathematical interval [0.0, 100.0]."""
    return round(min(100.0, max(0.0, float(active_share))), 2)


def evaluate_fund_coverage_and_health(
    genuine_coverage_pct: float,
    raw_composite_health_score: float,
    raw_active_share: float
) -> Tuple[Optional[float], float]:
    """Applies institutional quantitative invariants to fund coverage and active share.

    Returns:
        (composite_health_score, clamped_active_share)
        composite_health_score is None if genuine 7-pillar coverage < 70.0%.
    """
    clamped_as = clamp_active_share(raw_active_share)

    if float(genuine_coverage_pct) < MIN_VERIFIED_7PILLAR_COVERAGE_THRESHOLD:
        logger.info(
            "Withholding fund composite health score: genuine coverage %.1f%% is below the 70.0%% minimum threshold.",
            genuine_coverage_pct,
        )
        return (None, clamped_as)

    return (round(float(raw_composite_health_score), 1), clamped_as)


def calculate_active_share(
    holdings: List[Dict[str, Any]],
    benchmark_name: str = "NIFTY 500 TRI",
    stated_active_share: Optional[float] = None
) -> Dict[str, Any]:
    """Computes Active Share AS = 0.5 * sum(|w_fund - w_bench|) clamped strictly to [0.0, 100.0]."""
    res = _upstream_calculate_active_share(
        holdings=holdings,
        benchmark_name=benchmark_name,
        stated_active_share=stated_active_share
    )
    raw_as = res.get("active_share", 65.0)
    clamped_as = clamp_active_share(raw_as)
    res["active_share"] = clamped_as
    return res


def compute_fund_forensic_lookthrough(scheme_code: str) -> Dict[str, Any]:
    """Executes lookthrough and enforces coverage & active share quantitative invariants."""
    data = _upstream_compute_lookthrough(scheme_code)

    genuine_cov = float(data.get("genuine_coverage_pct", 0.0))
    raw_score = float(data.get("composite_health_score", 70.0)) if data.get("composite_health_score") is not None else 70.0
    raw_as = float(data.get("active_share", 65.0))

    final_score, clamped_as = evaluate_fund_coverage_and_health(
        genuine_coverage_pct=genuine_cov,
        raw_composite_health_score=raw_score,
        raw_active_share=raw_as
    )

    data["composite_health_score"] = final_score
    data["active_share"] = clamped_as

    if final_score is None:
        data["health_score_withheld"] = True
        data["health_score_withheld_reason"] = (
            f"Verified 7-pillar equity research coverage is {genuine_cov:.1f}%, which is below "
            f"the institutional minimum {MIN_VERIFIED_7PILLAR_COVERAGE_THRESHOLD}%. "
            f"Composite health score is withheld to prevent unverified proxy extrapolation."
        )
    else:
        data["health_score_withheld"] = False

    return data
