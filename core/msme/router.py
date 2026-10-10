# core/msme/router.py
"""
FastAPI router exposing MSME discovery, sector classification, and cluster intelligence endpoints.
All endpoints use the project's `json_response_with_cache` helper for server‑side caching.
Supports dual bindings for SQLite and PostgreSQL.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any

from core.db.connection import get_db_connection, get_supabase_url
from core.msme.utils import build_search_query, paginate, classify_msme_tier

router = APIRouter()


def json_response_with_cache(data: dict, ttl_seconds: int = 300) -> JSONResponse:
    """Simple cache wrapper for server-side HTTP caching."""
    import json, hashlib
    content = json.dumps(data, sort_keys=True, default=str)
    etag = hashlib.sha256(content.encode()).hexdigest()
    return JSONResponse(
        content=data,
        headers={
            "Cache-Control": f"public, max-age={ttl_seconds}",
            "ETag": etag,
        }
    )


@router.get("/stats")
def get_msme_stats():
    """Returns aggregated MSME registry intelligence and classification metrics."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*), COALESCE(SUM(annual_turnover), 0), COUNT(DISTINCT state) FROM msme_firms")
    row = cur.fetchone()
    total_firms = row[0] if row else 0
    total_turnover = round(float(row[1]), 2) if row and row[1] else 0.0
    states_count = row[2] if row else 0

    cur.execute("SELECT COUNT(*) FROM msme_firms WHERE annual_turnover < 5.0 OR annual_turnover IS NULL")
    micro_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM msme_firms WHERE annual_turnover >= 5.0 AND annual_turnover < 50.0")
    small_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM msme_firms WHERE annual_turnover >= 50.0")
    medium_count = cur.fetchone()[0]

    cur.execute("""
        SELECT sector_name, COUNT(*) as cnt
        FROM msme_firms
        WHERE sector_name IS NOT NULL AND sector_name != ''
        GROUP BY sector_name
        ORDER BY cnt DESC
        LIMIT 6
    """)
    top_sectors = [{"sector": r[0], "count": r[1]} for r in cur.fetchall()]

    cur.close()
    conn.close()

    payload = {
        "total_firms": total_firms,
        "total_turnover_cr": total_turnover,
        "states_count": states_count,
        "micro_count": micro_count,
        "small_count": small_count,
        "medium_count": medium_count,
        "top_sectors": top_sectors,
    }
    return json_response_with_cache(payload, ttl_seconds=300)


@router.get("/sectors")
def get_msme_sectors():
    """Returns distinct sector names with enterprise counts."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT sector_name, COUNT(*) as cnt
        FROM msme_firms
        WHERE sector_name IS NOT NULL AND sector_name != ''
        GROUP BY sector_name
        ORDER BY cnt DESC, sector_name ASC
    """)
    sectors = [{"sector": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return json_response_with_cache({"sectors": sectors}, ttl_seconds=600)


@router.get("/states")
def get_msme_states():
    """Returns distinct states with enterprise counts."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT state, COUNT(*) as cnt
        FROM msme_firms
        WHERE state IS NOT NULL AND state != ''
        GROUP BY state
        ORDER BY cnt DESC, state ASC
    """)
    states = [{"state": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return json_response_with_cache({"states": states}, ttl_seconds=600)


@router.get("/search")
def search_msme(
    q: Optional[str] = Query(None, description="Free‑text search (name, sector, UIN, city)"),
    sector: Optional[str] = Query(None, description="Sector filter"),
    state: Optional[str] = Query(None, description="State filter"),
    tier: Optional[str] = Query(None, description="Enterprise tier: Micro, Small, Medium"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """Searches MSME firms with filters, pagination, and classification tiers."""
    conn = get_db_connection()
    cur = conn.cursor()
    use_pg = bool(get_supabase_url())
    placeholder = "%s" if use_pg else "?"

    where, values = build_search_query(
        {"q": q, "sector": sector, "state": state, "tier": tier},
        placeholder=placeholder
    )
    limit, offset = paginate(size, page)

    sql = f"""
        SELECT uin, name, sector_name, city, state, annual_turnover,
               employee_count, registration_date, source
        FROM msme_firms
        WHERE {where}
        ORDER BY annual_turnover DESC, name ASC
        LIMIT {placeholder} OFFSET {placeholder}
    """
    cur.execute(sql, (*values, limit, offset))
    rows = cur.fetchall()

    count_sql = f"SELECT COUNT(*) FROM msme_firms WHERE {where}"
    cur.execute(count_sql, values)
    total = cur.fetchone()[0]
    cur.close()
    conn.close()

    results = []
    for r in rows:
        turnover = float(r[5]) if r[5] is not None else None
        results.append({
            "uin": r[0],
            "name": r[1],
            "sector": r[2],
            "city": r[3],
            "state": r[4],
            "annual_turnover": turnover,
            "employee_count": int(r[6]) if r[6] is not None else None,
            "registration_date": r[7],
            "source": r[8],
            "tier": classify_msme_tier(turnover)
        })

    payload = {
        "results": results,
        "total": total,
        "page": page,
        "size": size,
        "total_pages": (total + size - 1) // size if size > 0 else 1
    }
    return json_response_with_cache(payload, ttl_seconds=120)


@router.get("/{uin}")
def get_msme(uin: str):
    """Returns single MSME firm intelligence record by UIN."""
    conn = get_db_connection()
    cur = conn.cursor()
    use_pg = bool(get_supabase_url())
    placeholder = "%s" if use_pg else "?"

    sql = f"""
        SELECT uin, name, sector_code, sector_name, city, state, annual_turnover,
               employee_count, registration_date, source, last_updated
        FROM msme_firms
        WHERE UPPER(uin) = {placeholder}
    """
    cur.execute(sql, (uin.strip().upper(),))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"MSME firm with UIN '{uin}' not found")

    turnover = float(row[6]) if row[6] is not None else None
    payload = {
        "uin": row[0],
        "name": row[1],
        "sector_code": row[2],
        "sector": row[3],
        "city": row[4],
        "state": row[5],
        "annual_turnover": turnover,
        "employee_count": int(row[7]) if row[7] is not None else None,
        "registration_date": row[8],
        "source": row[9],
        "last_updated": str(row[10]) if row[10] else None,
        "tier": classify_msme_tier(turnover)
    }
    return json_response_with_cache(payload, ttl_seconds=300)
