# core/msme/utils.py
"""
Utility functions for the MSME feature.
- Normalise sector strings.
- Build safe SQL WHERE clauses from query params.
- Pagination calculations.
"""

from typing import Tuple, List, Dict
import unicodedata


def normalise_sector(sector: str) -> str:
    """Standardise sector names: lower‑case, strip whitespace, replace spaces with underscores."""
    return sector.strip().lower().replace(" ", "_")


def build_search_query(params: Dict[str, str]) -> Tuple[str, List]:
    """Return a SQL fragment for WHERE and a list of bind parameters.
    Supported keys: ``q`` (free‑text), ``sector``, ``state``.
    """
    clauses: List[str] = []
    values: List = []
    if q := params.get("q"):
        like = f"%{q}%"
        clauses.append("(name ILIKE ? OR sector_name ILIKE ?)")
        values.extend([like, like])
    if sector := params.get("sector"):
        clauses.append("sector_name = ?")
        values.append(sector)
    if state := params.get("state"):
        clauses.append("state = ?")
        values.append(state)
    where = " AND ".join(clauses) if clauses else "1 = 1"
    return where, values


def paginate(limit: int = 20, page: int = 1) -> Tuple[int, int]:
    """Calculate (limit, offset) for SQL.
    Caps ``limit`` at 100 to protect against huge responses.
    """
    limit = max(1, min(limit, 100))
    offset = max(0, (page - 1) * limit)
    return limit, offset
