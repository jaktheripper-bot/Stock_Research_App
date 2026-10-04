# core/msme/router.py
"""
FastAPI router exposing MSME discovery endpoints.
All endpoints use the project's `json_response_with_cache` helper for server‑side caching.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional

from core.db.connection import get_db_connection
from core.msme.utils import build_search_query, paginate

router = APIRouter()


def json_response_with_cache(data: dict, ttl_seconds: int = 300) -> JSONResponse:
    """Simple cache wrapper – mirrors the helper defined in `web/main.py`."""
    import json, hashlib
    content = json.dumps(data, sort_keys=True)
    etag = hashlib.sha256(content.encode()).hexdigest()
    return JSONResponse(content=data, headers={
        "Cache-Control": f"public, max-age={ttl_seconds}",
        "ETag": etag,
    })


@router.get("/search")
def search_msme(
    q: Optional[str] = Query(None, description="Free‑text search"),
    sector: Optional[str] = Query(None, description="Sector filter"),
    state: Optional[str] = Query(None, description="State filter"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    conn = get_db_connection()
    cur = conn.cursor()
    where, values = build_search_query({"q": q, "sector": sector, "state": state})
    limit, offset = paginate(size, page)
    sql = f"""
        SELECT uin, name, sector_name, city, state, annual_turnover,
               employee_count, registration_date, source
        FROM msme_firms
        WHERE {where}
        ORDER BY name ASC
        LIMIT ? OFFSET ?
    """
    cur.execute(sql, (*values, limit, offset))
    rows = cur.fetchall()
    # Total count for pagination metadata
    count_sql = f"SELECT COUNT(*) FROM msme_firms WHERE {where}"
    cur.execute(count_sql, values)
    total = cur.fetchone()[0]
    cur.close()
    conn.close()

    results = [
        {
            "uin": r[0],
            "name": r[1],
            "sector": r[2],
            "city": r[3],
            "state": r[4],
            "annual_turnover": r[5],
            "employee_count": r[6],
            "registration_date": r[7],
            "source": r[8],
        }
        for r in rows
    ]
    payload = {"results": results, "total": total, "page": page, "size": size}
    return json_response_with_cache(payload, ttl_seconds=300)


@router.get("/{uin}")
def get_msme(uin: str):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        SELECT uin, name, sector_name, city, state, annual_turnover,
               employee_count, registration_date, source, last_updated
        FROM msme_firms
        WHERE uin = ?
    """
    cur.execute(sql, (uin,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="MSME not found")
    payload = {
        "uin": row[0],
        "name": row[1],
        "sector": row[2],
        "city": row[3],
        "state": row[4],
        "annual_turnover": row[5],
        "employee_count": row[6],
        "registration_date": row[7],
        "source": row[8],
        "last_updated": row[9],
    }
    return json_response_with_cache(payload, ttl_seconds=3600)


@router.get("/suggest")
def suggest_msme(q: str = Query(..., description="Partial name or sector")):
    conn = get_db_connection()
    cur = conn.cursor()
    like = f"%{q}%"
    sql = """
        SELECT DISTINCT name FROM msme_firms WHERE name ILIKE ?
        UNION
        SELECT DISTINCT sector_name FROM msme_firms WHERE sector_name ILIKE ?
        LIMIT 10
    """
    cur.execute(sql, (like, like))
    suggestions = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return json_response_with_cache({"suggestions": suggestions}, ttl_seconds=300)
