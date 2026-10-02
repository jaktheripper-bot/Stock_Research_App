"""
Quantitative Metrics, Percentile Rankings, and Pillar Health Scoring Engine.

Provides zero-hallucination mathematical indicators, valuation percentiles,
range rankings, and qualitative pillar score quantifiers to mitigate cognitive
biases (Anchoring Bias, Confirmation Bias, Disposition Effect, and False Equivalence).
"""

from typing import Dict, Any, List, Optional, Tuple


def calculate_52w_percentile(current_price: Any, low_52w: Any, high_52w: Any) -> Optional[float]:
    """
    Computes the percentile position of the current price within its 52-week range [0.0 to 100.0].
    Mitigates Anchoring Bias by reframing price as a relative distribution rather than an absolute level.
    """
    try:
        if current_price is None or low_52w is None or high_52w is None:
            return None
        price = float(current_price)
        low = float(low_52w)
        high = float(high_52w)

        if high <= low or price <= 0:
            return None

        # Clamp between 0.0% and 100.0%
        pct = ((price - low) / (high - low)) * 100.0
        return round(max(0.0, min(100.0, pct)), 1)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def calculate_pe_percentile(current_pe: Any, revisions: List[Dict[str, Any]]) -> Optional[float]:
    """
    Computes the historical percentile ranking of the current P/E ratio across archived snapshots.
    Mitigates Valuation Anchoring by grounding multiples in longitudinal reality.
    """
    try:
        if current_pe is None or str(current_pe).strip().upper() in ("N/A", "LOSS-MAKING", "UNDEFINED"):
            return None
        pe_val = float(current_pe)
        if pe_val <= 0:
            return None

        historical_pes = []
        for r in revisions:
            raw_pe = r.get("baseline_pe")
            if raw_pe is not None and str(raw_pe).strip().upper() not in ("N/A", "LOSS-MAKING", "UNDEFINED"):
                try:
                    hp = float(raw_pe)
                    if hp > 0:
                        historical_pes.append(hp)
                except (ValueError, TypeError):
                    continue

        if not historical_pes:
            return None

        # Add current_pe to population if not present
        if pe_val not in historical_pes:
            historical_pes.append(pe_val)

        historical_pes.sort()
        # Rank of current_pe within sorted historical values
        less_count = sum(1 for p in historical_pes if p < pe_val)
        equal_count = sum(1 for p in historical_pes if p == pe_val)
        percentile = (less_count + 0.5 * equal_count) / len(historical_pes) * 100.0
        return round(max(0.0, min(100.0, percentile)), 1)
    except Exception:
        return None


def get_valuation_quartile(percentile: Optional[float]) -> Dict[str, str]:
    """
    Classifies a valuation percentile into an objective distribution quartile.
    """
    if percentile is None:
        return {"quartile": "N/A", "label": "Multiples Unranked", "color": "#64748b"}
    if percentile <= 25.0:
        return {"quartile": "Q1", "label": "Lower Historical Quartile (Discounted)", "color": "#1b5e20"}
    elif percentile <= 75.0:
        return {"quartile": "Q2-Q3", "label": "Median Historical Range (Fair)", "color": "#b26a00"}
    else:
        return {"quartile": "Q4", "label": "Upper Historical Quartile (Elevated)", "color": "#b71c1c"}


# Ordinal scoring maps for 7 qualitative diagnostic pillars (1 = Strained/Risk, 2 = Moderate/Fair, 3 = Disciplined/Wide/Clean)
PILLAR_SCORE_MAP = {
    "CapitalAllocation": {
        "Disciplined": 3,
        "Moderate": 2,
        "Strained": 1
    },
    "Macro": {
        "Stable": 3,
        "Neutral": 2,
        "Headwinds": 1
    },
    "Moat": {
        "Wide": 3,
        "Moderate": 2,
        "Narrow": 1
    },
    "Governance": {
        "Clean": 3,
        "Caution": 2,
        "High Risk": 1
    },
    "Diagnostic": {
        "Temporary": 3,
        "Neutral": 2,
        "Structural": 1,
        "N/A": 2
    },
    "Valuation": {
        "Undervalued": 3,
        "Fair": 2,
        "Stretched": 1,
        "Loss-Making": 0
    },
    "BalanceSheet": {
        "Debt-Free": 3,
        "Resilient": 3,
        "Moderate Debt": 2,
        "High Debt": 1
    }
}


def quantify_pillar_health(matrix: Dict[str, str]) -> Dict[str, int]:
    """
    Translates qualitative pillar matrix into numerical ordinal scores (0 to 3).
    Agnostic to case formatting.
    """
    if not matrix or not isinstance(matrix, dict):
        return {}

    scores = {}
    for pillar, label_map in PILLAR_SCORE_MAP.items():
        raw_val = matrix.get(pillar, "")
        normalized_val = str(raw_val).strip().title()
        # Fallback search if exact match fails
        score = label_map.get(normalized_val)
        if score is None:
            # Check partial matches
            for key, val in label_map.items():
                if key.lower() in normalized_val.lower():
                    score = val
                    break
        scores[pillar] = score if score is not None else 2  # Default to neutral (2)
    return scores


def calculate_overall_health_score(matrix: Dict[str, str]) -> Dict[str, Any]:
    """
    Computes an aggregate qualitative health score across all 7 pillars.
    Max achievable score: 21 (7 pillars * 3 max points).
    """
    scores = quantify_pillar_health(matrix)
    if not scores:
        return {"total_score": 0, "max_score": 21, "percentage": 0.0, "status": "N/A", "scores": {}}

    total = sum(scores.values())
    max_score = 21
    pct = round((total / max_score) * 100.0, 1)

    if pct >= 75.0:
        status = "High Quality Compounder"
        badge_color = "#1b5e20"
    elif pct >= 50.0:
        status = "Balanced / Moderate Moat"
        badge_color = "#b26a00"
    else:
        status = "Structural Risk / Headwinds"
        badge_color = "#b71c1c"

    return {
        "total_score": total,
        "max_score": max_score,
        "percentage": pct,
        "status": status,
        "badge_color": badge_color,
        "scores": scores
    }
