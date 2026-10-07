"""Autonomous Mutual Fund Look-Through Research Squad powered by Google Antigravity SDK.

Aggregates company-level forensic dossiers from `reports.db` to derive:
- Weighted Economic Moat Index
- Accounting & Solvency Risk Index (ASRI)
- Portfolio Margin of Safety vs Intrinsic DCF
- Promoter Pledging Exposure & Style Drift Tracking
"""

import json
import logging
from typing import Dict, Any, Optional

from core.agents.tools_base import tool_get_fund_holdings
from core.analysis.fund_forensic_auditor import compute_fund_forensic_lookthrough
from core.db.mutual_funds import get_mutual_fund_by_code, get_scheme_holdings

logger = logging.getLogger("equity_research.core.agents.funds")


def audit_fund_lookthrough(scheme_code: str) -> Dict[str, Any]:
    """Conducts a comprehensive 7-pillar look-through audit of a mutual fund scheme."""
    clean = (scheme_code or "").strip()
    scheme = get_mutual_fund_by_code(clean)
    if not scheme:
        return {"error": f"Scheme {clean} not found.", "scheme_code": clean}

    lookthrough = compute_fund_forensic_lookthrough(clean)

    return {
        "scheme_code": clean,
        "scheme_name": scheme.get("scheme_name"),
        "category": scheme.get("category"),
        "composite_health_score": lookthrough.get("composite_health_score", 70.0),
        "weighted_moat_score": lookthrough.get("weighted_moat_score", 70.0),
        "accounting_risk_index": lookthrough.get("accounting_risk_index", 0.0),
        "margin_of_safety_pct": lookthrough.get("margin_of_safety_pct", 0.0),
        "promoter_pledge_exposure_pct": lookthrough.get("promoter_pledge_exposure_pct", 0.0),
        "top_quality_holdings": lookthrough.get("top_quality_holdings", []),
        "top_risky_holdings": lookthrough.get("top_risky_holdings", []),
        "sebi_safe_harbor": "Under SEBI (Mutual Funds) Regulations, 1996 and SEBI RA 2014 Sec. 2(u).",
        "engine": "google-antigravity-fund-squad"
    }
