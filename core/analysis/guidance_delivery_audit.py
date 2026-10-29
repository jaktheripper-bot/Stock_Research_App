"""
Sequential Thesis Drift & Filing-vs-Baseline Accountability Engine
==================================================================
Compares immutable historical snapshots in `report_revisions` to surface
objective changes in 7-pillar ratings, valuation baselines, and falsification triggers.
"""

from typing import Any, Dict, List, Optional

from core.db.reports import get_report_revisions
from core.analysis.parser import extract_health_matrix
from core.analysis.epistemic_schema import extract_falsification_triggers


def _to_positive_float(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val) if val > 0 else 0.0
    s = str(val).replace(",", "").replace("₹", "").replace("INR", "").replace("Rs.", "").strip()
    if not s or s.upper() in ("N/A", "NM", "NONE", "-", "—"):
        return 0.0
    try:
        parsed = float(s)
        return parsed if parsed > 0 else 0.0
    except ValueError:
        return 0.0


def compute_sequential_thesis_drift(ticker: str) -> Dict[str, Any]:
    clean_sym = (ticker or "").strip().upper()
    revs = get_report_revisions(clean_sym, include_text=True) or []
    if len(revs) < 2:
        latest_only = revs[0] if revs else {}
        return {
            "ticker": clean_sym,
            "status": "BASELINE_ONLY",
            "revision_count": len(revs),
            "pillar_migrations": [],
            "price_drift_pct": None,
            "active_revision_triggers": extract_falsification_triggers(latest_only.get("report_text", "")) if latest_only else {},
        }

    latest = revs[0]
    latest_text = (latest.get("report_text") or "").strip()
    # Compare against the most recent distinct thesis snapshot so duplicate price-only saves do not mask pillar migrations
    prior = next(
        (
            r for r in revs[1:]
            if (r.get("report_text") or "").strip()
            and (r.get("report_text") or "").strip() != latest_text
        ),
        revs[1],
    )

    mat_now = extract_health_matrix(latest.get("report_text", "")) or {}
    mat_old = extract_health_matrix(prior.get("report_text", "")) or {}

    migrations: List[Dict[str, str]] = []
    for k in sorted(set(mat_now.keys()) | set(mat_old.keys())):
        old_v = str(mat_old.get(k) or "Unrated")
        new_v = str(mat_now.get(k) or "Unrated")
        if old_v != new_v:
            migrations.append({
                "pillar": k,
                "prior_posture": old_v,
                "current_posture": new_v,
                "prior_date": prior.get("formatted_date", ""),
                "current_date": latest.get("formatted_date", ""),
            })

    p_old = _to_positive_float(prior.get("baseline_price"))
    p_now = _to_positive_float(latest.get("baseline_price"))
    latest_trigger = latest.get("revision_trigger") or "Statutory Filing Update"

    price_drift: Optional[float] = None
    if p_old > 0 and p_now > 0 and "remediation" not in latest_trigger.lower():
        ratio = p_now / p_old
        # Guard against unadjusted corporate-action splits/bonuses or legacy scrip-token discontinuities (>5x jump)
        if 0.2 <= ratio <= 5.0:
            price_drift = round(((p_now - p_old) / p_old) * 100.0, 1)

    return {
        "ticker": clean_sym,
        "status": "DRIFT_COMPUTED",
        "revision_count": len(revs),
        "prior_snapshot_date": prior.get("formatted_date"),
        "latest_snapshot_date": latest.get("formatted_date"),
        "latest_trigger": latest_trigger,
        "price_drift_pct": price_drift,
        "pillar_migrations": migrations,
        "active_revision_triggers": extract_falsification_triggers(latest.get("report_text", "")),
    }

