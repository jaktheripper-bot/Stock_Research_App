"""Top-N Mutual Fund Portfolio Ingestion Pipeline.

1. Ranks Direct-Growth equity/hybrid/debt schemes by AMFI average AUM.
2. For each AMC, obtains its latest month-end portfolio workbook from either
   (a) a manually supplied file in data/amc_portfolios/<amc_key>/ (always wins), or
   (b) a verified URL template in core/ingestion/amc_sources.json.
3. Matches each ranked scheme to a sheet, validates the parsed portfolio, and saves it.
4. Walks down the ranking so that a fund with no obtainable portfolio is replaced by the
   next-largest fund that does have data, until `target` funds are ingested.

Nothing synthetic is ever written: a fund either gets its real disclosed holdings or is skipped.
"""

import csv
import io
import json
import logging
import time
import urllib.request
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.db.mutual_funds import (
    get_mutual_fund_scheme,
    save_mutual_fund_holdings,
    save_mutual_fund_scheme,
)
from core.ingestion.amfi import _get_ssl_context, fetch_amfi_nav_raw, parse_amfi_nav_feed
from core.ingestion.mf_portfolio_parser import match_scheme_name, parse_workbook, sniff_format
from core.ingestion.mf_universe import rank_funds_by_aum

logger = logging.getLogger(__name__)

SOURCES_FILE = Path(__file__).with_name("amc_sources.json")
INBOX_DIR = Path("data/amc_portfolios")
CACHE_DIR = Path(".cache/mf_portfolios")
NSE_EQUITY_MASTER_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
MIN_WEIGHT_SUM = 95.0
MAX_WEIGHT_SUM = 101.5
_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) StockResearchApp/2.0"


# --------------------------------------------------------------------------- #
# Registry + dates
# --------------------------------------------------------------------------- #
def load_sources(path: Path = SOURCES_FILE) -> Dict[str, Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["amcs"]


def amc_key_for_fund_house(fund_house: str, sources: Dict[str, Dict[str, Any]]) -> Optional[str]:
    fh = (fund_house or "").strip().lower()
    for key, cfg in sources.items():
        if any(fh == n.lower() for n in cfg.get("mf_names", [])):
            return key
    return None


def recent_month_ends(n: int = 4, today: Optional[date] = None) -> List[date]:
    """Last n completed month-end dates, newest first."""
    d = (today or date.today()).replace(day=1)
    out: List[date] = []
    for _ in range(n):
        d = d - timedelta(days=1)
        out.append(date(d.year, d.month, monthrange(d.year, d.month)[1]))
        d = d.replace(day=1)
    return out


def render_url(template: str, d: date) -> str:
    return template.format(
        dd=f"{d.day:02d}", mm=f"{d.month:02d}", mon=_MON[d.month - 1].lower(),
        Mon=_MON[d.month - 1], yy=f"{d.year % 100:02d}", yyyy=str(d.year),
    )


# --------------------------------------------------------------------------- #
# Workbook acquisition
# --------------------------------------------------------------------------- #
def _download(url: str, timeout: int = 90) -> Optional[bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=timeout) as resp:
            data = resp.read()
    except Exception as e:
        logger.info(f"Download miss {url}: {e}")
        return None
    return data if data and sniff_format(data) in ("xlsx", "xls") else None


def get_amc_workbook(
    key: str,
    cfg: Dict[str, Any],
    today: Optional[date] = None,
    inbox_dir: Path = INBOX_DIR,
    cache_dir: Path = CACHE_DIR,
) -> Optional[Tuple[bytes, str]]:
    """Returns (workbook_bytes, source_label) for an AMC, or None if nothing is available."""
    folder = inbox_dir / key
    if folder.is_dir():
        files = sorted(
            [p for p in folder.iterdir() if p.suffix.lower() in (".xls", ".xlsx", ".csv")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if files:
            return files[0].read_bytes(), f"manual_upload:{files[0].name}"

    template = cfg.get("url_template")
    if not template:
        return None

    cache_amc = cache_dir / key
    cache_amc.mkdir(parents=True, exist_ok=True)
    for me in recent_month_ends(4, today):
        cached = cache_amc / f"{me.isoformat()}.bin"
        if cached.exists() and (time.time() - cached.stat().st_mtime) < 7 * 86400:
            return cached.read_bytes(), f"cache:{render_url(template, me)}"
        url = render_url(template, me)
        data = _download(url)
        if data:
            cached.write_bytes(data)
            logger.info(f"[{key}] fetched {url} ({len(data):,} bytes)")
            return data, url
    return None


# --------------------------------------------------------------------------- #
# ISIN -> NSE symbol (lets equity holdings join to the 7-pillar stock reports)
# --------------------------------------------------------------------------- #
def load_isin_symbol_map(force_refresh: bool = False) -> Dict[str, str]:
    cache = Path(".cache") / "nse_equity_master.csv"
    cache.parent.mkdir(parents=True, exist_ok=True)
    text = None
    if not force_refresh and cache.exists() and (time.time() - cache.stat().st_mtime) < 7 * 86400:
        text = cache.read_text(encoding="utf-8", errors="ignore")
    if text is None:
        try:
            req = urllib.request.Request(NSE_EQUITY_MASTER_URL, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=30) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
            cache.write_text(text, encoding="utf-8")
        except Exception as e:
            logger.warning(f"NSE ISIN master unavailable ({e}); equity holdings keep ISIN identifiers.")
            if cache.exists():
                text = cache.read_text(encoding="utf-8", errors="ignore")
    if not text:
        return {}
    mapping: Dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        isin, sym = row.get("ISIN NUMBER"), row.get("SYMBOL")
        if isin and sym:
            mapping[isin.upper()] = sym.upper()
    return mapping


# --------------------------------------------------------------------------- #
# Holdings assembly + validation
# --------------------------------------------------------------------------- #
def build_holdings(parsed: Dict[str, Any], isin_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """Converts a parsed sheet into rows for save_mutual_fund_holdings (merging duplicate lines)."""
    as_on = parsed.get("as_on_date") or date.today().isoformat()
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for h in parsed["holdings"]:
        htype = h["holding_type"]
        if htype in ("EQUITY",):
            ident = isin_map.get(h["isin"], h["isin"])
        elif htype == "CASH_EQUIVALENT":
            name = h["holding_name"].upper()
            ident = "TREPS" if ("TREPS" in name or "TRIPARTY" in name) else \
                    "NET_CURRENT_ASSETS" if "NET" in name else \
                    "REVERSE_REPO" if "REPO" in name else "CASH"
        else:
            ident = h["isin"] or h["holding_name"].upper()[:24]
        k = (htype, ident)
        if k in merged:
            merged[k]["weight_pct"] = round(merged[k]["weight_pct"] + h["weight_pct"], 4)
            continue
        merged[k] = {
            "holding_type": htype,
            "identifier": ident,
            "holding_name": h["holding_name"] or ident,
            "weight_pct": h["weight_pct"],
            "sector_or_rating": h["sector_or_rating"] or "Unclassified",
            "portfolio_date": as_on,
            "instrument_details": {**h["instrument_details"], **({"isin": h["isin"]} if h["isin"] else {})},
        }
    return sorted(merged.values(), key=lambda x: x["weight_pct"], reverse=True)


def validate_holdings(holdings: List[Dict[str, Any]]) -> Optional[str]:
    """Returns a rejection reason, or None if the portfolio looks complete and sane."""
    if not holdings:
        return "no holdings parsed"
    total = sum(h["weight_pct"] for h in holdings)
    if not (MIN_WEIGHT_SUM <= total <= MAX_WEIGHT_SUM):
        return f"weights sum to {total:.1f}% (expected ~100%)"
    return None


def _upsert_scheme_master(
    row: Dict[str, Any],
    amfi_lookup: Dict[str, Dict[str, Any]],
    holdings: List[Dict[str, Any]],
    as_on: str,
    source: str,
) -> bool:
    existing = get_mutual_fund_scheme(row["scheme_code"])
    if existing and existing.get("scheme_code", "").upper() == row["scheme_code"].upper():
        scheme = dict(existing)
        meta = dict(existing.get("metadata") or {})
    else:
        scheme = dict(amfi_lookup.get(row["scheme_code"]) or {})
        scheme.setdefault("scheme_code", row["scheme_code"])
        scheme.setdefault("scheme_name", row["scheme_name"])
        scheme.setdefault("fund_house", row["fund_house"])
        scheme.setdefault("category", row["category"])
        scheme.setdefault("broad_category", row["broad_category"])
        meta = {}
    scheme["aum_crores"] = row["aum_crores"]
    scheme["last_portfolio_date"] = as_on
    top10 = round(sum(h["weight_pct"] for h in holdings[:10]), 1)
    meta.update({
        "holdings_source": source,
        "holdings_as_on": as_on,
        "aum_rank": row.get("aum_rank"),
        "aum_source": "AMFI average AUM (scheme-wise)",
        "top_10_weight_pct": top10,
    })
    scheme["metadata"] = meta
    return save_mutual_fund_scheme(scheme)


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def ingest_top_funds(
    target: int = 150,
    dry_run: bool = False,
    only_amcs: Optional[List[str]] = None,
    universe: Optional[List[Dict[str, Any]]] = None,
    workbook_provider: Optional[Callable[[str, Dict[str, Any]], Optional[Tuple[bytes, str]]]] = None,
    isin_map: Optional[Dict[str, str]] = None,
    audit: bool = False,
) -> Dict[str, Any]:
    """Ingests real portfolios for the `target` largest funds that have obtainable data."""
    t0 = time.time()
    sources = load_sources()
    ranked = universe if universe is not None else rank_funds_by_aum()
    provider = workbook_provider or get_amc_workbook
    isin_map = isin_map if isin_map is not None else load_isin_symbol_map()

    amfi_lookup: Dict[str, Dict[str, Any]] = {}
    try:
        for s in parse_amfi_nav_feed(fetch_amfi_nav_raw(), direct_growth_only=True):
            amfi_lookup[str(s["scheme_code"])] = s
    except Exception as e:
        logger.warning(f"AMFI NAV master unavailable for scheme enrichment: {e}")

    workbook_cache: Dict[str, Optional[Dict[str, Any]]] = {}
    amc_status: Dict[str, str] = {}
    ingested: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    def load_amc(key: str) -> Optional[Dict[str, Any]]:
        if key in workbook_cache:
            return workbook_cache[key]
        got = provider(key, sources[key])
        if not got:
            amc_status[key] = "no workbook available (no verified URL and no manual upload)"
            workbook_cache[key] = None
            return None
        data, label = got
        try:
            sheets = parse_workbook(data)
        except Exception as e:
            amc_status[key] = f"unparseable workbook: {e}"
            workbook_cache[key] = None
            return None
        titles = {n: p["scheme_name"] or n for n, p in sheets.items()}
        amc_status[key] = f"ok: {len(sheets)} scheme sheets from {label}"
        workbook_cache[key] = {"sheets": sheets, "titles": titles, "source": label}
        return workbook_cache[key]

    for row in ranked:
        if len(ingested) >= target:
            break
        key = amc_key_for_fund_house(row["fund_house"], sources)
        if not key or (only_amcs and key not in only_amcs):
            skipped.append({**_brief(row), "reason": "AMC not in scope" if key else "AMC not in registry"})
            continue
        book = load_amc(key)
        if not book:
            skipped.append({**_brief(row), "reason": amc_status[key]})
            continue
        sheet_name = match_scheme_name(row["scheme_name"], list(book["titles"].values()))
        if not sheet_name:
            skipped.append({**_brief(row), "reason": "no matching scheme sheet in AMC workbook"})
            continue
        parsed = next(p for n, p in book["sheets"].items() if (p["scheme_name"] or n) == sheet_name)
        holdings = build_holdings(parsed, isin_map)
        problem = validate_holdings(holdings)
        if problem:
            skipped.append({**_brief(row), "reason": f"validation failed: {problem}"})
            continue

        as_on = parsed.get("as_on_date") or date.today().isoformat()
        if not dry_run:
            if not _upsert_scheme_master(row, amfi_lookup, holdings, as_on, book["source"]):
                skipped.append({**_brief(row), "reason": "scheme master save failed"})
                continue
            if not save_mutual_fund_holdings(row["scheme_code"], holdings):
                skipped.append({**_brief(row), "reason": "holdings save failed"})
                continue
        ingested.append({**_brief(row), "holdings_count": len(holdings), "as_on": as_on, "source": book["source"]})

    audited = 0
    if audit and not dry_run:
        from core.analysis.fund_forensic_auditor import audit_single_fund_daily
        for item in ingested:
            try:
                audit_single_fund_daily(item["scheme_code"])
                audited += 1
            except Exception as e:
                logger.warning(f"Audit failed for {item['scheme_code']}: {e}")

    return {
        "target": target,
        "ingested_count": len(ingested),
        "target_met": len(ingested) >= target,
        "ingested": ingested,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "amc_status": amc_status,
        "audited": audited,
        "dry_run": dry_run,
        "duration_seconds": round(time.time() - t0, 1),
    }


def _brief(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "aum_rank": row.get("aum_rank"),
        "scheme_code": row["scheme_code"],
        "scheme_name": row["scheme_name"],
        "fund_house": row["fund_house"],
        "aum_crores": row["aum_crores"],
    }
