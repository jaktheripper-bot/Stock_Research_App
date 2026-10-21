# core/msme/router.py
"""
FastAPI router exposing MSME discovery, sector classification, and cluster intelligence endpoints.
All endpoints use the project's `json_response_with_cache` helper for server‑side caching.
Supports dual bindings for SQLite and PostgreSQL.
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any

from core.db.connection import get_db_connection, get_supabase_url, is_postgres_connection
from core.msme.utils import build_search_query, paginate, classify_msme_tier

logger = logging.getLogger(__name__)
router = APIRouter()


def json_response_with_cache(data: dict, ttl_seconds: int = 300) -> JSONResponse:
    """Simple cache wrapper for server-side HTTP caching (PostgreSQL date/Decimal safe)."""
    import json, hashlib
    from fastapi.encoders import jsonable_encoder
    safe_data = jsonable_encoder(data)
    content = json.dumps(safe_data, sort_keys=True, default=str)
    etag = hashlib.sha256(content.encode()).hexdigest()
    return JSONResponse(
        content=safe_data,
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
    try:
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
    finally:
        try:
            cur.close()
        except Exception as e:
            logger.debug(f"Cursor close notice: {e}")
        try:
            conn.close()
        except Exception as e:
            logger.debug(f"Connection close notice: {e}")

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
    try:
        cur.execute("""
            SELECT sector_name, COUNT(*) as cnt
            FROM msme_firms
            WHERE sector_name IS NOT NULL AND sector_name != ''
            GROUP BY sector_name
            ORDER BY cnt DESC, sector_name ASC
        """)
        sectors = [{"sector": r[0], "count": r[1]} for r in cur.fetchall()]
    finally:
        try:
            cur.close()
        except Exception as e:
            logger.debug(f"Cursor close notice: {e}")
        try:
            conn.close()
        except Exception as e:
            logger.debug(f"Connection close notice: {e}")
    return json_response_with_cache({"sectors": sectors}, ttl_seconds=600)


@router.get("/states")
def get_msme_states():
    """Returns distinct states with enterprise counts."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT state, COUNT(*) as cnt
            FROM msme_firms
            WHERE state IS NOT NULL AND state != ''
            GROUP BY state
            ORDER BY cnt DESC, state ASC
        """)
        states = [{"state": r[0], "count": r[1]} for r in cur.fetchall()]
    finally:
        try:
            cur.close()
        except Exception as e:
            logger.debug(f"Cursor close notice: {e}")
        try:
            conn.close()
        except Exception as e:
            logger.debug(f"Connection close notice: {e}")
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
    try:
        use_pg = is_postgres_connection(conn)
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
    finally:
        try:
            cur.close()
        except Exception as e:
            logger.debug(f"Cursor close notice: {e}")
        try:
            conn.close()
        except Exception as e:
            logger.debug(f"Connection close notice: {e}")

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
            "registration_date": str(r[7]) if r[7] is not None else None,
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


from core.msme.forensic_engine import compute_msme_forensic_dossier


def get_msme_detail(uin: str) -> Optional[Dict[str, Any]]:
    """Retrieves single MSME firm and computes complete forensic analysis dossier."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        use_pg = is_postgres_connection(conn)
        placeholder = "%s" if use_pg else "?"

        sql = f"""
            SELECT uin, name, sector_code, sector_name, city, state, annual_turnover,
                   employee_count, registration_date, source
            FROM msme_firms
            WHERE UPPER(uin) = {placeholder}
        """
        cur.execute(sql, (uin.strip().upper(),))
        row = cur.fetchone()
    finally:
        try:
            cur.close()
        except Exception as e:
            logger.debug(f"Cursor close notice: {e}")
        try:
            conn.close()
        except Exception as e:
            logger.debug(f"Connection close notice: {e}")

    if not row:
        # Resilient fallback to canonical/daily MSME catalogs if DB row was not yet seeded
        clean_target = uin.strip().upper()
        try:
            from core.msme.seed import CANONICAL_MSME_FIRMS
            from core.msme.daily_ingest import DAILY_MSME_CATALOG
            for cand in list(CANONICAL_MSME_FIRMS) + list(DAILY_MSME_CATALOG):
                if str(cand.get("uin", "")).strip().upper() == clean_target:
                    row = (
                        cand["uin"],
                        cand["name"],
                        cand.get("sector_code", ""),
                        cand.get("sector_name", ""),
                        cand.get("city", ""),
                        cand.get("state", ""),
                        cand.get("annual_turnover"),
                        cand.get("employee_count"),
                        cand.get("registration_date"),
                        cand.get("source", "Udyam Gazette / Open Registry"),
                    )
                    break
        except Exception as e:
            logger.warning(f"MSME catalog fallback lookup notice for {clean_target}: {e}")

    if not row:
        return None

    turnover = float(row[6]) if row[6] is not None else None
    reg_date_str = str(row[8]) if row[8] is not None else None
    base_data = {
        "uin": row[0],
        "name": row[1],
        "sector_code": row[2],
        "sector": row[3],
        "sector_name": row[3],
        "city": row[4],
        "state": row[5],
        "annual_turnover": turnover,
        "employee_count": int(row[7]) if row[7] is not None else None,
        "registration_date": reg_date_str,
        "source": row[9],
        "last_updated": reg_date_str,
        "tier": classify_msme_tier(turnover)
    }

    # Enrich with full 4-pillar forensic analytics
    dossier = compute_msme_forensic_dossier(base_data)
    dossier["sector_code"] = base_data["sector_code"]
    dossier["last_updated"] = base_data["last_updated"]
    return dossier


@router.get("/{uin}")
def get_msme(uin: str):
    """Returns single MSME firm intelligence record and 4-pillar report by UIN."""
    dossier = get_msme_detail(uin)
    if not dossier:
        raise HTTPException(status_code=404, detail=f"MSME firm with UIN '{uin}' not found")

    return json_response_with_cache(dossier, ttl_seconds=300)

