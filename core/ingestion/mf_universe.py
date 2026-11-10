"""Mutual Fund Universe Ranking from AMFI's official scheme-wise Average AUM data.

Source (public, no login): https://www.amfiindia.com/api/average-aum-schemewise
AMFI reports Average AUM in Rs. Lakhs; this module converts to Rs. Crores.

The ranked universe drives the portfolio-disclosure ingestion pipeline: funds are
walked from largest AUM downward, and any fund whose portfolio cannot be obtained
is skipped in favour of the next one until the requested target is reached.
"""

import json
import logging
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.ingestion.amfi import _get_ssl_context, derive_broad_category

logger = logging.getLogger(__name__)

AAUM_BASE_URL = "https://www.amfiindia.com/api/average-aum-schemewise"
AAUM_PERIODS_URL = "https://www.amfiindia.com/api/average-aum-fundwise"
CACHE_DIR = Path(".cache")
CACHE_TTL_SECONDS = 24 * 3600
LAKHS_PER_CRORE = 100.0

_ELIGIBLE_BROAD = {"EQUITY", "HYBRID", "DEBT"}
# Fund-of-funds hold units of other funds: no direct securities to look through.
_EXCLUDED_CATEGORY_MARKERS = ("fund of funds", "fof", "other scheme")


def _http_get_json(url: str, timeout: int = 90) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 StockResearchApp/2.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _list_periods(fy_id: int = 1) -> List[Dict[str, Any]]:
    payload = _http_get_json(f"{AAUM_PERIODS_URL}?fyId={fy_id}", timeout=30)
    return ((payload.get("data") or {}).get("periods")) or []


def fetch_scheme_aaum_raw(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Returns the most recent non-empty scheme-wise AAUM payload (cached on disk for 24h)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / "amfi_aaum_schemewise.json"

    if not force_refresh and cache_file.exists():
        if (time.time() - cache_file.stat().st_mtime) < CACHE_TTL_SECONDS:
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Unreadable AAUM cache, refetching: {e}")

    try:
        # Newest financial year first; newest period first. The most recent period is
        # sometimes listed before AMFI has published its data, so fall through to older ones.
        for fy_id in (1, 2):
            for period in _list_periods(fy_id):
                url = (
                    f"{AAUM_BASE_URL}?strType=Categorywise&fyId={fy_id}"
                    f"&periodId={period['id']}&MF_ID=0"
                )
                data = (_http_get_json(url) or {}).get("data") or []
                if data:
                    logger.info(f"AMFI AAUM loaded for period '{period.get('period')}' (fyId={fy_id}).")
                    cache_file.write_text(json.dumps(data), encoding="utf-8")
                    return data
    except Exception as e:
        logger.error(f"Error fetching AMFI scheme-wise AAUM: {e}")
        if cache_file.exists():
            logger.info("Falling back to stale AAUM cache on disk.")
            return json.loads(cache_file.read_text(encoding="utf-8"))
        raise
    return []


_NON_GROWTH_PAYOUT_RE = re.compile(
    r"\b(?:idcw|bonus)\b|\bdividend\b(?!\s+(?:yield|opportunities|leaders|power)\b)",
    re.IGNORECASE,
)


def rank_funds_by_aum(
    aaum_data: Optional[List[Dict[str, Any]]] = None,
    broad_categories: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Ranks Direct-Growth schemes by average AUM (Rs. Cr), largest first."""
    if aaum_data is None:
        aaum_data = fetch_scheme_aaum_raw()
    allowed = broad_categories or _ELIGIBLE_BROAD

    ranked: List[Dict[str, Any]] = []
    seen_codes = set()
    for block in aaum_data:
        category = block.get("SchemeCat_Desc", "") or ""
        cat_lower = category.lower()
        if any(m in cat_lower for m in _EXCLUDED_CATEGORY_MARKERS):
            continue
        broad = derive_broad_category(category)
        if broad not in allowed:
            continue
        for s in block.get("schemes", []):
            name = s.get("SchemeNAVName", "") or ""
            low = name.lower()
            if "direct" not in low or "growth" not in low:
                continue
            if _NON_GROWTH_PAYOUT_RE.search(low):
                continue
            code = str(s.get("AMFI_Code", "")).strip()
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            lakhs = ((s.get("AverageAumForTheMonth") or {}).get(
                "ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas"
            )) or 0.0
            ranked.append({
                "scheme_code": code,
                "scheme_name": name,
                "fund_house": block.get("Mfname", ""),
                "category": re.sub(r"^.*?-\s*", "", category).strip() or category,
                "category_raw": category,
                "broad_category": broad,
                "aum_crores": round(float(lakhs) / LAKHS_PER_CRORE, 2),
            })

    ranked.sort(key=lambda r: r["aum_crores"], reverse=True)
    for i, r in enumerate(ranked, start=1):
        r["aum_rank"] = i
    return ranked


def extract_all_scheme_aaum_map(
    aaum_data: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, float]:
    """Extracts `{amfi_code: aum_crores}` across ALL categories in AMFI's official AAUM feed."""
    if aaum_data is None:
        aaum_data = fetch_scheme_aaum_raw()
    aum_by_code: Dict[str, float] = {}
    for block in aaum_data or []:
        for s in block.get("schemes", []) or []:
            code = str(s.get("AMFI_Code") or "").strip()
            if not code:
                continue
            lakhs = (
                (s.get("AverageAumForTheMonth") or {}).get(
                    "ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas"
                )
            ) or 0.0
            cr = round(float(lakhs) / LAKHS_PER_CRORE, 2)
            if cr > 0 and cr > aum_by_code.get(code, 0.0):
                aum_by_code[code] = cr
    return aum_by_code


def backfill_scheme_aaum_to_db(
    aaum_data: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """Backfills official AMFI scheme-wise AAUM (`aum_crores`) onto `mutual_fund_schemes` rows."""
    from core.db.connection import IST, get_db_connection, get_placeholder
    from core.db.mutual_funds import clean_dict_row, resolve_legacy_slug_twins

    aum_map = extract_all_scheme_aaum_map(aaum_data)
    if not aum_map:
        return {"numeric_updated": 0, "slug_twins_updated": 0}

    conn = get_db_connection()
    cur = conn.cursor()
    p = get_placeholder()
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S+05:30")
    numeric_updated = 0
    slug_updated = 0
    try:
        cur.execute("SELECT scheme_code, scheme_name, fund_house, aum_crores, nav FROM mutual_fund_schemes")
        rows = [clean_dict_row(cur, r) for r in cur.fetchall()]

        for r in rows:
            code = str(r.get("scheme_code") or "").strip()
            if code.isdigit() and code in aum_map:
                new_aum = aum_map[code]
                if abs(float(r.get("aum_crores") or 0.0) - new_aum) >= 0.01:
                    cur.execute(
                        f"UPDATE mutual_fund_schemes SET aum_crores = {p}, last_updated = {p} WHERE scheme_code = {p}",
                        (new_aum, now_ist, code),
                    )
                    r["aum_crores"] = new_aum
                    numeric_updated += 1

        # Propagate official AAUM to legacy slug twins when the numeric twin carries live AAUM
        slug_to_num = resolve_legacy_slug_twins(rows)
        row_by_code = {str(r.get("scheme_code") or "").strip(): r for r in rows}
        for slug_code, num_code in slug_to_num.items():
            num_aum = float((row_by_code.get(num_code) or {}).get("aum_crores") or 0.0)
            slug_row = row_by_code.get(slug_code) or {}
            if num_aum > 0 and float(slug_row.get("aum_crores") or 0.0) <= 0:
                cur.execute(
                    f"UPDATE mutual_fund_schemes SET aum_crores = {p}, last_updated = {p} WHERE scheme_code = {p}",
                    (num_aum, now_ist, slug_code),
                )
                slug_updated += 1

        conn.commit()
    finally:
        cur.close()
        conn.close()
    return {"numeric_updated": numeric_updated, "slug_twins_updated": slug_updated}
