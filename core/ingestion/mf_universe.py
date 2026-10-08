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
            if "idcw" in low or "dividend" in low or "bonus" in low:
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
