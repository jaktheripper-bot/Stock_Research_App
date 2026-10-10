# core/msme/utils.py
"""
Utility functions for the MSME feature.
- Normalise sector strings.
- Build safe, dual-dialect SQL WHERE clauses from query params.
- Pagination calculations.
- MSMED Act 2020 enterprise tier classification.
"""

from typing import Tuple, List, Dict, Optional


def normalise_sector(sector: str) -> str:
    """Standardise sector names: lower‑case, strip whitespace, replace spaces with underscores."""
    if not sector:
        return ""
    return sector.strip().lower().replace(" ", "_")


def classify_msme_tier(turnover_cr: Optional[float]) -> str:
    """Classifies an enterprise under the revised statutory MSMED Act 2020 thresholds.
    - Micro:  Turnover < ₹5.0 Cr
    - Small:  Turnover >= ₹5.0 Cr and < ₹50.0 Cr
    - Medium: Turnover >= ₹50.0 Cr and <= ₹250.0 Cr
    """
    if turnover_cr is None or turnover_cr < 5.0:
        return "Micro"
    elif turnover_cr < 50.0:
        return "Small"
    return "Medium"


def build_search_query(params: Dict[str, Optional[str]], placeholder: str = "?") -> Tuple[str, List]:
    """Return a SQL fragment for WHERE and a list of bind parameters.
    Supported keys: ``q`` (free‑text across name, sector, uin, city), ``sector``, ``state``, ``tier``.
    Works seamlessly across SQLite and PostgreSQL.
    """
    clauses: List[str] = []
    values: List = []

    if q := params.get("q"):
        cleaned = q.strip()
        if cleaned:
            like_val = f"%{cleaned.lower()}%"
            clauses.append(
                f"(LOWER(name) LIKE {placeholder} OR LOWER(sector_name) LIKE {placeholder} "
                f"OR LOWER(uin) LIKE {placeholder} OR LOWER(city) LIKE {placeholder})"
            )
            values.extend([like_val, like_val, like_val, like_val])

    if sector := params.get("sector"):
        cleaned_sector = normalise_sector(sector)
        if cleaned_sector and cleaned_sector != "all":
            clauses.append(f"LOWER(sector_name) = {placeholder}")
            values.append(cleaned_sector)

    if state := params.get("state"):
        cleaned_state = state.strip()
        if cleaned_state and cleaned_state.lower() != "all":
            clauses.append(f"LOWER(state) = {placeholder}")
            values.append(cleaned_state.lower())

    if tier := params.get("tier"):
        t_clean = tier.strip().lower()
        if t_clean == "micro":
            clauses.append("annual_turnover < 5.0")
        elif t_clean == "small":
            clauses.append("annual_turnover >= 5.0 AND annual_turnover < 50.0")
        elif t_clean == "medium":
            clauses.append("annual_turnover >= 50.0")

    where = " AND ".join(clauses) if clauses else "1 = 1"
    return where, values


def paginate(limit: int = 20, page: int = 1) -> Tuple[int, int]:
    """Calculate (limit, offset) for SQL.
    Caps ``limit`` at 100 to protect against huge responses.
    """
    limit = max(1, min(limit, 100))
    offset = max(0, (page - 1) * limit)
    return limit, offset
