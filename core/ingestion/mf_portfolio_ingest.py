"""Mutual Fund Monthly Portfolio Ingestion Pipeline (SEBI Statutory Disclosures).

1. Ranks Direct-Growth equity/hybrid/debt schemes by AMFI average AUM (and merges active
   numeric Direct-Growth schemes already registered in `mutual_fund_schemes`).
2. Backfills official AMFI scheme-wise AAUM (`aum_crores`) across numeric & twin schemes.
3. For each AMC, obtains its latest month-end portfolio workbook/bundle from:
   (a) a manually supplied file/bundle in `data/amc_portfolios/<amc_key>/` (always wins),
   (b) a verified unauthenticated SEBI statutory AMC adapter / URL template (`amc_sources.json`), or
   (c) optional sanctioned `MFFORECAST_RAPIDAPI_KEY` REST fallback if configured.
4. Matches schemes via 2-pass collision-guarded bipartite matching, resolves NSE + BSE ISINs
   to listed symbols, validates ~100% portfolio weight, saves to `mutual_fund_holdings`, and
   upgrades matched legacy non-numeric slug twins (`PPFAS_FLEXICAP_DIR`, `SBI_FOCUSED_DIR`, etc.).

Strict Fail-Closed & Zero-Bypass Invariant:
- Never bypasses login walls, CAPTCHAs, investor credentials, or WAFs.
- Nothing synthetic is ever written: schemes without obtainable verified disclosures remain cleanly
  in `PENDING_HOLDINGS_SYNC`.
"""

import concurrent.futures
import csv
import hashlib
import io
import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.db.connection import IST, get_db_connection, get_placeholder
from core.db.mutual_funds import (
    clean_dict_row,
    get_current_fund_disclosure,
    get_mutual_fund_scheme,
    parse_fund_disclosure_date,
    publish_mutual_fund_disclosure,
    resolve_legacy_slug_twins,
)
from core.ingestion.amfi import _get_ssl_context, fetch_amfi_nav_raw, parse_amfi_nav_feed
from core.ingestion.mf_portfolio_parser import (
    match_scheme_name,
    match_schemes_to_workbook_sheets,
    parse_as_on_date,
    parse_workbook,
    sniff_format,
)
from core.ingestion.mf_universe import backfill_scheme_aaum_to_db, rank_funds_by_aum

logger = logging.getLogger(__name__)

SOURCES_FILE = Path(__file__).with_name("amc_sources.json")
INBOX_DIR = Path("data/amc_portfolios")
CACHE_DIR = Path(".cache/mf_portfolios")
NSE_EQUITY_MASTER_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_SME_MASTER_URL = "https://nsearchives.nseindia.com/content/equities/SME_EQUITY_L.csv"
MIN_WEIGHT_SUM = 88.0
MAX_WEIGHT_SUM = 108.5
_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_FULL_MONTH = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) StockResearchApp/2.0"
_ISIN_EQUITY_RE = re.compile(r"^IN[A-Z0-9]{10}$")


# --------------------------------------------------------------------------- #
# Registry + dates
# --------------------------------------------------------------------------- #
def load_sources(path: Path = SOURCES_FILE) -> Dict[str, Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["amcs"]


def amc_key_for_fund_house(fund_house: str, sources: Dict[str, Dict[str, Any]]) -> Optional[str]:
    fh = (fund_house or "").strip().lower()
    if not fh:
        return None
    for key, cfg in sources.items():
        if any(fh == n.lower() for n in cfg.get("mf_names", [])):
            return key
    for key, cfg in sources.items():
        for n in cfg.get("mf_names", []):
            stem = n.lower().replace("mutual fund", "").strip()
            if stem and len(stem) >= 3 and re.search(rf"\b{re.escape(stem)}\b", fh):
                return key
    return None


def recent_month_ends(n: int = 4, today: Optional[date] = None) -> List[date]:
    """Last n completed month-end dates, newest first."""
    d = (today or datetime.now(IST).date()).replace(day=1)
    out: List[date] = []
    for _ in range(n):
        d = d - timedelta(days=1)
        out.append(date(d.year, d.month, monthrange(d.year, d.month)[1]))
        d = d.replace(day=1)
    return out


def render_url(template: str, d: date) -> str:
    return template.format(
        dd=f"{d.day:02d}",
        mm=f"{d.month:02d}",
        mon=_MON[d.month - 1].lower(),
        Mon=_MON[d.month - 1],
        Month=_FULL_MONTH[d.month - 1],
        yy=f"{d.year % 100:02d}",
        yyyy=str(d.year),
    )


# --------------------------------------------------------------------------- #
# HTTP & Multi-Workbook Bundle Helpers (certifi TLS, zero bypass)
# --------------------------------------------------------------------------- #
def _safe_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url.strip())
    encoded_path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/:@!$&'()*+,;=-._~")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, encoded_path, parts.query, parts.fragment))


def _http_request(
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 45,
) -> Optional[bytes]:
    hdrs = {"User-Agent": _UA, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(_safe_url(url), data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        logger.debug("HTTP miss %s: %s", url, e)
        return None


def _download(url: str, timeout: int = 90, extra_headers: Optional[Dict[str, str]] = None) -> Optional[bytes]:
    data = _http_request(url, timeout=timeout, headers=extra_headers)
    if not data:
        return None
    return data if sniff_format(data) in ("xlsx", "xls", "zip") else None


def _pack_files_into_zip(named_blobs: List[Tuple[str, bytes]]) -> Optional[bytes]:
    if not named_blobs:
        return None
    if len(named_blobs) == 1:
        return named_blobs[0][1]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_STORED) as zf:
        used_names = set()
        for idx, (fname, blob) in enumerate(named_blobs):
            clean_name = re.sub(r"[^A-Za-z0-9._\- ]+", "_", fname.rsplit("/", 1)[-1]) or f"book_{idx}.xlsx"
            if clean_name in used_names:
                stem, _, ext = clean_name.rpartition(".")
                clean_name = f"{stem}_{idx}.{ext or 'xlsx'}"
            used_names.add(clean_name)
            zf.writestr(zipfile.ZipInfo(clean_name), blob)
    return buf.getvalue()


def _download_many_as_zip(urls: List[str], max_workers: int = 6, timeout: int = 45) -> Optional[bytes]:
    unique_urls = list(dict.fromkeys(urls))
    if not unique_urls:
        return None

    def _fetch_one(u: str) -> Optional[Tuple[str, bytes]]:
        blob = _download(u, timeout=timeout)
        if not blob:
            return None
        fname = urllib.parse.unquote(urllib.parse.urlsplit(u).path.rsplit("/", 1)[-1]) or "scheme.xlsx"
        return fname, blob

    collected: List[Tuple[str, bytes]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        for res in pool.map(_fetch_one, unique_urls):
            if res:
                collected.append(res)
    return _pack_files_into_zip(collected)


# --------------------------------------------------------------------------- #
# Verified Public Unauthenticated SEBI Statutory AMC Adapters
# --------------------------------------------------------------------------- #
def _fetch_sbi(me: date) -> Optional[Tuple[bytes, str]]:
    payload = json.dumps({
        "FundId": 0,
        "PSYear": str(me.year),
        "PSMonth": _FULL_MONTH[me.month - 1],
        "PSFrequency": "Monthly",
    }).encode("utf-8")
    raw = _http_request(
        "https://www.sbimf.com/ajaxcall/CMS/GetSchemePortfolioSheets",
        method="POST",
        data=payload,
        headers={"Content-Type": "application/json", "Origin": "https://www.sbimf.com", "Referer": "https://www.sbimf.com/portfolios"},
        timeout=35,
    )
    if not raw:
        return None
    txt = raw.decode("utf-8", errors="ignore").replace("\\/", "/")
    links = re.findall(r'https?://[^\s"\'<>]+\.(?:xlsx?|zip)', txt, re.I)
    rel = re.findall(r'href=["\'](/[^"\']+\.(?:xlsx?|zip))["\']', txt, re.I)
    all_links = links + [f"https://www.sbimf.com{p}" for p in rel]
    consolidated = [u for u in all_links if "all-scheme" in u.lower() or "all_scheme" in u.lower()]
    for u in (consolidated or all_links[:1]):
        blob = _download(u)
        if blob:
            return blob, u
    if len(all_links) > 1:
        packed = _download_many_as_zip(all_links[:120])
        if packed:
            return packed, f"sbi_cms:{me.isoformat()}({len(all_links)} files)"
    return None


def _fetch_icici(me: date) -> Optional[Tuple[bytes, str]]:
    api_url = "https://apps.digital.icicipruamc.com/nms/v1/downloads/files"
    cat_id = "26a073d7-08d2-4a95-95fa-f83a4ee51e40"
    mon_full = _FULL_MONTH[me.month - 1].lower()
    mon_short = _MON[me.month - 1].lower()
    yr_str = str(me.year)
    matched_urls: List[str] = []

    for page in range(1, 5):
        body = json.dumps({
            "categoryId": cat_id,
            "schemeCategory": "",
            "userType": "Investor",
            "fileType": "All",
            "page": str(page),
            "size": "50",
            "filter": [],
            "categoryName": "OTHERS",
        }).encode("utf-8")
        raw = _http_request(
            api_url,
            method="POST",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://www.icicipruamc.com",
                "Referer": "https://www.icicipruamc.com/",
                "env": "api",
                "requestAPIId": str(uuid.uuid4()),
            },
            timeout=35,
        )
        if not raw:
            break
        try:
            obj = json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception as parse_err:
            logger.debug("[icici] JSON decode error on page %s: %s", page_idx, parse_err)
            break
        data = (obj.get("success") or {}).get("data") or {}
        files = data.get("files") or []
        if not files:
            break
        for row in files:
            title_obj = row.get("title")
            title = str((title_obj.get("text") if isinstance(title_obj, dict) else title_obj) or "").lower()
            if "fortnight" in title and "monthly" not in title:
                continue
            if yr_str in title and (mon_full in title or re.search(rf"\b{mon_short}\b", title)):
                u = str(row.get("url") or "").strip()
                if not u:
                    continue
                if not u.startswith("http"):
                    u = "https://www.icicipruamc.com/" + u.lstrip("/")
                u = u.replace("://www.icicipruamc.com/downloads/", "://www.icicipruamc.com/blob/downloads/")
                matched_urls.append(u)
        if matched_urls or not data.get("isNext"):
            break

    for u in matched_urls:
        blob = _download(u, timeout=90)
        if blob:
            return blob, u
    return None


def _fetch_hdfc(me: date) -> Optional[Tuple[bytes, str]]:
    fy_year = str(me.year if me.month >= 4 else me.year - 1)
    form_body = urllib.parse.urlencode({
        "year": fy_year,
        "type": "monthly",
        "month": str(me.month),
    }).encode("utf-8")
    raw = _http_request(
        "https://cms.hdfcfund.com/en/hdfc/api/v2/disclosures/monthfortportfolio",
        method="POST",
        data=form_body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.hdfcfund.com",
            "Referer": "https://www.hdfcfund.com/",
        },
        timeout=35,
    )
    if not raw:
        return None
    try:
        obj = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception as parse_err:
        logger.debug("[hdfc] JSON decode error for %s: %s", me.isoformat(), parse_err)
        return None
    files = ((obj.get("data") or {}).get("files")) or []
    urls = []
    for item in files:
        f_obj = item.get("file") if isinstance(item, dict) else None
        u = (f_obj.get("url") if isinstance(f_obj, dict) else None) or (item.get("url") if isinstance(item, dict) else None)
        if u and urllib.parse.urlsplit(u).path.lower().endswith((".xlsx", ".xls", ".zip")):
            urls.append(u)
    if not urls:
        return None
    packed = _download_many_as_zip(urls, max_workers=8, timeout=45)
    if packed:
        return packed, f"https://cms.hdfcfund.com/monthfortportfolio/{me.isoformat()}({len(urls)} files)"
    return None


def _fetch_uti(me: date) -> Optional[Tuple[bytes, str]]:
    q = urllib.parse.urlencode({"year": str(me.year), "month": _FULL_MONTH[me.month - 1]})
    raw = _http_request(f"https://www.utimf.com/api/get-consolidate-portfolio-disclosure?{q}", timeout=30)
    if not raw:
        return None
    try:
        obj = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception as parse_err:
        logger.debug("[uti] JSON decode error for %s: %s", me.isoformat(), parse_err)
        return None
    rows = obj.get("rows") or ((obj.get("data") or {}).get("rows")) or []
    for r in rows:
        u = str((r or {}).get("doc") or (r or {}).get("url") or "").strip()
        if u:
            blob = _download(u, timeout=90)
            if blob:
                return blob, u
    return None


def _fetch_absl(me: date) -> Optional[Tuple[bytes, str]]:
    q = urllib.parse.urlencode({
        "id": "3ccab227-9de5-4494-b78d-2b4f7c0c054a",
        "ctype": "/sitecore/content/Root/BSL/Library/Lists/FAQ/Customer Types/Individual",
        "month": _FULL_MONTH[me.month - 1],
        "year": str(me.year),
    })
    url = f"https://mutualfund.adityabirlacapital.com/postlogin/CustomApi/Resources/FactsheetAccordionById?{q}"
    raw = _http_request(url, timeout=35)
    if not raw:
        return None
    txt = raw.decode("utf-8", errors="ignore").replace("\\/", "/")
    links = re.findall(r'https?://[^\s"\'<>]+\.(?:zip|xlsx?)', txt, re.I)
    rel = re.findall(r'(/[^\s"\'<>]+\.(?:zip|xlsx?))', txt, re.I)
    candidates = links + [f"https://mutualfund.adityabirlacapital.com{p}" for p in rel]
    mon_short = _MON[me.month - 1].lower()
    yr_str = str(me.year)
    yr_2 = f"{me.year % 100:02d}"
    filtered = [
        u for u in candidates
        if "fortnight" not in u.lower() and (yr_str in u or yr_2 in u) and mon_short in u.lower()
    ] or [u for u in candidates if "fortnight" not in u.lower()]
    for u in filtered:
        blob = _download(u, timeout=90)
        if blob:
            return blob, u
    return None


def _fetch_axis(me: date) -> Optional[Tuple[bytes, str]]:
    browser_id = str(uuid.uuid4())
    tok_raw = _http_request(
        "https://www.axismf.com/cms/token",
        method="POST",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "browser-id": browser_id,
            "Origin": "https://www.axismf.com",
            "Referer": "https://www.axismf.com/statutory-disclosures",
        },
        timeout=25,
    )
    if not tok_raw:
        return None
    try:
        tok_obj = json.loads(tok_raw.decode("utf-8", errors="ignore"))
    except Exception as tok_err:
        logger.debug("[axis] token JSON decode error: %s", tok_err)
        return None
    token = (tok_obj.get("data") or {}).get("token") or tok_obj.get("token")
    if not token:
        return None
    auth = token if str(token).lower().startswith("bearer ") else f"Bearer {token}"
    body = json.dumps({
        "sdType": "yearMonthSchemeDocs",
        "sdID": "sdMonthSchemePortfolio",
        "year": str(me.year),
        "month": _FULL_MONTH[me.month - 1],
        "schemeCode": "Consolidated",
    }).encode("utf-8")
    docs_raw = _http_request(
        "https://www.axismf.com/cms/get-scheme-documents",
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "browser-id": browser_id,
            "Authorization": auth,
            "Origin": "https://www.axismf.com",
            "Referer": "https://www.axismf.com/statutory-disclosures",
        },
        timeout=35,
    )
    if not docs_raw:
        return None
    try:
        docs_obj = json.loads(docs_raw.decode("utf-8", errors="ignore"))
    except Exception as docs_err:
        logger.debug("[axis] docs JSON decode error: %s", docs_err)
        return None
    doc_list = ((docs_obj.get("data") or {}).get("documentList")) or []
    for d in doc_list:
        u = str((d or {}).get("docuementURL") or (d or {}).get("documentURL") or (d or {}).get("url") or "").strip()
        lbl = (str((d or {}).get("title") or "") + " " + u).lower()
        if any(skip_kw in lbl for skip_kw in ("weekly", "fortnight", "ad_hoc", "adhoc", "ad hoc", "half_yearly", "half yearly")):
            continue
        if u:
            blob = _download(u, timeout=90)
            if blob:
                return blob, u
    return None


def _fetch_dsp(me: date) -> Optional[Tuple[bytes, str]]:
    raw = _http_request("https://www.dspim.com/mandatory-disclosures/portfolio-disclosures", timeout=35)
    if not raw:
        return None
    txt = raw.decode("utf-8", errors="ignore")
    links = re.findall(r'https?://[^\s"\'<>]+\.(?:zip|xlsx?)', txt, re.I)
    mon_short = _MON[me.month - 1].lower()
    yr_str = str(me.year)
    hits = [
        u for u in links
        if ("monthend" in u.lower() or "monthly" in u.lower())
        and "fortnight" not in u.lower()
        and yr_str in u
        and mon_short in u.lower()
    ]
    for u in hits:
        blob = _download(u, timeout=90)
        if blob:
            return blob, u
    return None


def _fetch_tata(me: date) -> Optional[Tuple[bytes, str]]:
    raw = _http_request("https://www.tatamutualfund.com/schemes-related/portfolio", timeout=35)
    if not raw:
        return None
    txt = urllib.parse.unquote(raw.decode("utf-8", errors="ignore"))
    raw_links = re.findall(r'https?://[^\s"\'<>]+\.(?:xlsx?|zip)', raw.decode("utf-8", errors="ignore"), re.I)
    mon_full = _FULL_MONTH[me.month - 1].lower()
    mon_short = _MON[me.month - 1].lower()
    yr_str = str(me.year)
    for u in raw_links:
        dec = urllib.parse.unquote(u).lower()
        if "monthly" in dec and yr_str in dec and (mon_full in dec or mon_short in dec):
            blob = _download(u, timeout=90)
            if blob:
                return blob, u
    return None


def _fetch_bandhan(me: date) -> Optional[Tuple[bytes, str]]:
    target_iso = me.isoformat()
    mon_short = _MON[me.month - 1].lower()
    yr_str = str(me.year)
    urls: List[str] = []
    for page in range(1, 4):
        raw = _http_request(
            f"https://cmsnew.bandhanmutual.com/wp-json/finance-api/v1/posts/monthly-portfolios?page={page}&per_page=100",
            timeout=35,
        )
        if not raw:
            break
        try:
            obj = json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception as parse_err:
            logger.debug("[bandhan] JSON decode error on page %s: %s", page, parse_err)
            break
        posts = obj if isinstance(obj, list) else (obj.get("data") or obj.get("posts") or [])
        if not isinstance(posts, list) or not posts:
            break
        for p in posts:
            blob_txt = json.dumps(p)
            dt_cand = parse_as_on_date(str(p.get("title") or "") + " " + str(p.get("date") or "") + " " + blob_txt)
            file_links = re.findall(r'https?://[^\s"\'<>\\]+\.(?:xlsx?|zip)', blob_txt.replace("\\/", "/"), re.I)
            for fl in file_links:
                low_fl = fl.lower()
                if dt_cand == target_iso or (yr_str in low_fl and mon_short in low_fl):
                    urls.append(fl)
        if len(urls) >= 35:
            break
    if not urls:
        return None
    packed = _download_many_as_zip(urls, max_workers=6, timeout=45)
    if packed:
        return packed, f"https://cmsnew.bandhanmutual.com/monthly-portfolios/{target_iso}({len(urls)} files)"
    return None


def _fetch_ppfas(me: date) -> Optional[Tuple[bytes, str]]:
    raw = _http_request("https://amc.ppfas.com/downloads/portfolio-disclosure/", timeout=30)
    if not raw:
        return None
    txt = raw.decode("utf-8", errors="ignore")
    rels = re.findall(
        r"(?:https?://amc\.ppfas\.com)?(/downloads/portfolio-disclosure/[^\"'\s<>]+\.(?:xls|xlsx|zip))",
        txt,
        re.I,
    )
    mon_full = _FULL_MONTH[me.month - 1].lower()
    mon_short = _MON[me.month - 1].lower()
    yr_str = str(me.year)
    urls: List[str] = []
    for p in rels:
        low = p.lower()
        if yr_str in low and (mon_full in low or f"_{mon_short}_" in low or f"-{mon_short}-" in low):
            urls.append(f"https://amc.ppfas.com{p}")
    if not urls:
        return None
    packed = _download_many_as_zip(urls, max_workers=4, timeout=45)
    if packed:
        return packed, f"https://amc.ppfas.com/downloads/portfolio-disclosure/{me.isoformat()}({len(urls)} files)"
    return None


def _fetch_franklin(me: date) -> Optional[Tuple[bytes, str]]:
    raw = _http_request("https://www.franklintempletonindia.com/api/literature/v1/responseLitJson?type=report", timeout=35)
    if not raw:
        return None
    try:
        obj = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception as parse_err:
        logger.debug("[franklin] JSON decode error: %s", parse_err)
        return None
    dropdowns = obj.get("FirstDropDown") or ((obj.get("data") or {}).get("FirstDropDown")) or []
    mon_full = _FULL_MONTH[me.month - 1].lower()
    mon_short = _MON[me.month - 1].lower()
    yr_str = str(me.year)
    for dd in dropdowns:
        if "PORTFOLIO" not in str(dd.get("id") or "").upper() and "PORTFOLIO" not in str(dd.get("title") or "").upper():
            continue
        if "FORTNIGHT" in str(dd.get("id") or "").upper():
            continue
        records = dd.get("dataRecords") or []
        if isinstance(records, dict):
            records = [records]
        for rec in records:
            for item in (rec.get("linkdata") or []):
                lbl = (str(item.get("literatureLabel") or "") + " " + str(item.get("literatureHref") or "")).lower()
                if yr_str in lbl and (mon_full in lbl or mon_short in lbl):
                    href = str(item.get("literatureHref") or "").strip()
                    if not href:
                        continue
                    u = href if href.startswith("http") else f"https://www.franklintempletonindia.com/download{href if href.startswith('/') else '/' + href}"
                    blob = _download(u, timeout=90)
                    if blob:
                        return blob, u
    return None


def _fetch_motilal(me: date) -> Optional[Tuple[bytes, str]]:
    raw = _http_request(
        "https://www.motilaloswalmf.com/content/aem-cloud-dept-backend-motilal-oswal/api/search-documents.json?year=&category=month%20end%20portfolio&month=&type=mf",
        timeout=35,
    )
    if not raw:
        return None
    try:
        obj = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception as parse_err:
        logger.debug("[motilal] JSON decode error: %s", parse_err)
        return None
    results = obj.get("results") or ((obj.get("data") or {}).get("results")) or []
    mon_full = _FULL_MONTH[me.month - 1].lower()
    mon_short = _MON[me.month - 1].lower()
    yr_str = str(me.year)
    for item in results:
        title = (str(item.get("title") or "") + " " + str(item.get("path") or "")).lower()
        if "fortnight" in title or "weekly" in title:
            continue
        if yr_str in title and (mon_full in title or mon_short in title):
            p = str(item.get("path") or item.get("url") or "").strip()
            if not p:
                continue
            u = p if p.startswith("http") else f"https://www.motilaloswalmf.com{p if p.startswith('/') else '/' + p}"
            blob = _download(u, timeout=90)
            if blob:
                return blob, u
    return None


def _fetch_groww(me: date) -> Optional[Tuple[bytes, str]]:
    raw = _http_request("https://www.growwmf.in/statutory-disclosure/portfolio", timeout=35)
    if not raw:
        return None
    txt = raw.decode("utf-8", errors="ignore")
    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', txt, re.S)
    blob_str = m.group(1) if m else txt
    # Groww JSON embeds unencoded spaces inside file URLs
    raw_links = re.findall(r'https?://[^"\'<>\\]+\.(?:xlsx?|zip)', blob_str.replace("\\/", "/"), re.I)
    mon_full = _FULL_MONTH[me.month - 1].lower()
    mon_short = _MON[me.month - 1].lower()
    yr_str = str(me.year)
    yr_2 = f"{me.year % 100:02d}"
    hits = []
    for raw_u in raw_links:
        u = raw_u.strip().replace(" ", "%20")
        fname = urllib.parse.unquote(u.rsplit("/", 1)[-1]).lower()
        if "portfolio" not in fname or "aaum" in fname or "fortnight" in fname or "weekly" in fname:
            continue
        parsed_dt = parse_as_on_date(fname)
        if parsed_dt == me.isoformat() or (
            (yr_str in fname or f"-{yr_2}." in fname or f"_{yr_2}." in fname)
            and (mon_full in fname or mon_short in fname)
        ):
            hits.append(u)
    consolidated = [u for u in hits if "monthly" in urllib.parse.unquote(u.rsplit("/", 1)[-1]).lower()]
    for u in (consolidated or hits[:1]):
        blob = _download(u, timeout=90)
        if blob:
            return blob, u
    if len(hits) > 1:
        packed = _download_many_as_zip(hits[:40])
        if packed:
            return packed, f"groww_next:{me.isoformat()}({len(hits)} files)"
    return None


def _fetch_baroda(me: date) -> Optional[Tuple[bytes, str]]:
    raw = _http_request("https://www.barodabnpparibasmf.in/downloads/monthly-portfolio-scheme", timeout=35)
    if not raw:
        return None
    txt = raw.decode("utf-8", errors="ignore")
    links = re.findall(r'https?://[^\s"\'<>]+\.(?:xlsx?|zip)', txt, re.I)
    mm_yyyy = f"{me.month:02d}-{me.year}"
    mon_short = _MON[me.month - 1].lower()
    yr_str = str(me.year)
    for u in links:
        low = u.lower()
        if "monthly" in low and (mm_yyyy in low or (yr_str in low and mon_short in low)):
            blob = _download(u, timeout=90)
            if blob:
                return blob, u
    return None


def _fetch_invesco(me: date) -> Optional[Tuple[bytes, str]]:
    cls_raw = _http_request("https://invescomutualfund.com/api/ClassificationCompleteMonthlyHoldings?page=Holding", timeout=25)
    slugs = ["Equity", "Hybrid", "Debt"]
    if cls_raw:
        try:
            cls_obj = json.loads(cls_raw.decode("utf-8", errors="ignore"))
            if isinstance(cls_obj, list):
                parsed_slugs = [
                    str(c.get("Classification") or c.get("classification") or c.get("Value") or "").strip()
                    for c in cls_obj if isinstance(c, dict)
                ]
                slugs = [s for s in parsed_slugs if s] or slugs
        except Exception as cls_err:
            logger.debug("[invesco] classification JSON decode error: %s", cls_err)
    mon_col = f"{_MON[me.month - 1]}Url"
    urls: List[str] = []
    for slug in slugs:
        q = urllib.parse.urlencode({"year": str(me.year), "classification": slug})
        raw = _http_request(f"https://invescomutualfund.com/api/CompleteMonthlyHoldings?{q}", timeout=25)
        if not raw:
            continue
        try:
            rows = json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception as rows_err:
            logger.debug("[invesco] holdings JSON decode error for %s: %s", slug, rows_err)
            continue
        if isinstance(rows, dict):
            rows = rows.get("data") or rows.get("rows") or [rows]
        if isinstance(rows, list):
            for r in rows:
                if not isinstance(r, dict):
                    continue
                u = str(r.get(mon_col) or r.get(mon_col.lower()) or "").strip()
                if u:
                    if not u.startswith("http"):
                        u = "https://invescomutualfund.com/" + u.lstrip("/")
                    urls.append(u)
    if not urls:
        return None
    packed = _download_many_as_zip(urls, max_workers=5, timeout=45)
    if packed:
        return packed, f"https://invescomutualfund.com/CompleteMonthlyHoldings/{me.isoformat()}({len(urls)} files)"
    return None


_AMC_ADAPTERS: Dict[str, Callable[[date], Optional[Tuple[bytes, str]]]] = {
    "sbi_cms": _fetch_sbi,
    "icici_nms": _fetch_icici,
    "hdfc_cms": _fetch_hdfc,
    "uti_api": _fetch_uti,
    "absl_api": _fetch_absl,
    "axis_cms": _fetch_axis,
    "dsp_html": _fetch_dsp,
    "tata_html": _fetch_tata,
    "bandhan_wp": _fetch_bandhan,
    "ppfas_html": _fetch_ppfas,
    "franklin_api": _fetch_franklin,
    "motilal_api": _fetch_motilal,
    "groww_next": _fetch_groww,
    "baroda_html": _fetch_baroda,
    "invesco_api": _fetch_invesco,
}


def get_amc_workbook(
    key: str,
    cfg: Dict[str, Any],
    today: Optional[date] = None,
    inbox_dir: Path = INBOX_DIR,
    cache_dir: Path = CACHE_DIR,
    target_month_end: Optional[date] = None,
) -> Optional[Tuple[bytes, str]]:
    """Returns `(workbook_or_zip_bytes, source_label)` for an AMC, or None if unavailable."""
    folder = inbox_dir / key
    if folder.is_dir():
        files = sorted(
            [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".xls", ".xlsx", ".csv", ".zip")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if len(files) == 1:
            return files[0].read_bytes(), f"manual_upload:{files[0].name}"
        if len(files) > 1:
            packed = _pack_files_into_zip([(p.name, p.read_bytes()) for p in files])
            if packed:
                return packed, f"manual_upload:{key}({len(files)} files)"

    template = cfg.get("url_template")
    adapter_name = cfg.get("adapter")
    if not template and not adapter_name:
        return None

    cache_amc = cache_dir / key
    cache_amc.mkdir(parents=True, exist_ok=True)
    months = [target_month_end] if target_month_end else recent_month_ends(3, today)
    for me in months:
        cached = cache_amc / f"{me.isoformat()}.bin"
        meta_file = cache_amc / f"{me.isoformat()}.meta.txt"
        if not target_month_end and cached.exists() and (time.time() - cached.stat().st_mtime) < 14 * 86400:
            src_lbl = meta_file.read_text(encoding="utf-8").strip() if meta_file.exists() else f"cache:{key}:{me.isoformat()}"
            return cached.read_bytes(), src_lbl

        if template:
            url = render_url(template, me)
            data = _download(url)
            if data:
                cached.write_bytes(data)
                meta_file.write_text(url, encoding="utf-8")
                logger.info("[%s] fetched %s (%s bytes)", key, url, f"{len(data):,}")
                return data, url

        if adapter_name and adapter_name in _AMC_ADAPTERS:
            try:
                got = _AMC_ADAPTERS[adapter_name](me)
            except Exception as ad_err:
                logger.warning("[%s] adapter %s error for %s: %s", key, adapter_name, me.isoformat(), ad_err)
                got = None
            if got:
                data, src_url = got
                cached.write_bytes(data)
                meta_file.write_text(src_url, encoding="utf-8")
                logger.info("[%s] fetched via %s for %s (%s bytes)", key, adapter_name, me.isoformat(), f"{len(data):,}")
                return data, src_url

    return None


def _fetch_mfforecast_holdings_if_configured(
    scheme_code: str, isin_map: Dict[str, str]
) -> Optional[Tuple[List[Dict[str, Any]], str, str, str]]:
    """Optional sanctioned RapidAPI holdings fallback for WAF-gated AMCs when MFFORECAST_RAPIDAPI_KEY is configured."""
    api_key = os.environ.get("MFFORECAST_RAPIDAPI_KEY", "").strip()
    if not api_key:
        try:
            from core.config import get_secret
            api_key = str(get_secret("MFFORECAST_RAPIDAPI_KEY", "") or "").strip()
        except Exception as sec_err:
            logger.debug("MFFORECAST_RAPIDAPI_KEY secret lookup skipped: %s", sec_err)
            api_key = ""
    if not api_key or not scheme_code.isdigit():
        return None
    host = os.environ.get("MFFORECAST_RAPIDAPI_HOST", "mfforecast.p.rapidapi.com").strip()
    url = f"https://{host}/api/v1/schemes/{scheme_code}/holdings"
    raw = _http_request(
        url,
        headers={"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": host, "Accept": "application/json"},
        timeout=25,
    )
    if not raw:
        return None
    try:
        payload = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception as pay_err:
        logger.debug("MFForecast JSON decode error for %s: %s", scheme_code, pay_err)
        return None
    if not isinstance(payload, dict):
        return None
    items = payload.get("holdings") or payload.get("data") or []
    if not isinstance(items, list) or not items:
        return None
    reported_dates = [payload[key] for key in ("portfolio_date", "as_on_date") if payload.get(key)]
    dates = {parse_fund_disclosure_date(value) for value in reported_dates}
    if None in dates or len(dates) != 1:
        return None
    as_on = dates.pop()
    if not as_on or as_on > datetime.now(IST).date().isoformat():
        return None
    raw_rows = []
    for it in items:
        isin = str(it.get("isin") or "").strip().upper()
        w = float(it.get("weight_pct") or it.get("percentage") or 0.0)
        if w <= 0:
            continue
        htype = "EQUITY" if isin.startswith("INE") and isin[8:10] == "01" else ("DEBT" if isin.startswith("IN") else "CASH_EQUIVALENT")
        raw_rows.append({
            "isin": isin,
            "holding_name": str(it.get("name") or it.get("instrument_name") or isin),
            "holding_type": htype,
            "sector_or_rating": str(it.get("sector") or it.get("rating") or "Unclassified"),
            "weight_pct": round(w, 4),
            "instrument_details": {},
        })
    holdings = build_holdings({"as_on_date": as_on, "holdings": raw_rows}, isin_map)
    if validate_holdings(holdings) is not None:
        return None
    return holdings, as_on, url, hashlib.sha256(raw).hexdigest()


# --------------------------------------------------------------------------- #
# ISIN & Company Name -> Listed NSE / BSE Symbol Resolution (L5 Guard)
# --------------------------------------------------------------------------- #
def _normalize_company_lookup_key(name: str) -> str:
    s = (name or "").upper()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[\.\,\-\&\'\$\*\#]+", " ", s)
    s = re.sub(r"\b(?:LIMITED|LTD|INDIA|PVT|PRIVATE|THE|CORP|CORPORATION|CO)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_BSE_COMPANY_SYMBOL_CACHE: Optional[Dict[str, str]] = None


def _load_bse_company_symbol_map() -> Dict[str, str]:
    global _BSE_COMPANY_SYMBOL_CACHE
    if _BSE_COMPANY_SYMBOL_CACHE is not None:
        return _BSE_COMPANY_SYMBOL_CACHE
    out: Dict[str, str] = {}
    try:
        from bse_master import get_bse_scrips_cache

        bse_data = get_bse_scrips_cache() or {}
        symbols = bse_data.get("symbols") or {}
        names = bse_data.get("names") or {}
        scrip_to_sym = {str(code).strip(): str(sym).strip().upper() for sym, code in symbols.items() if sym and code}
        for cname, code in names.items():
            sym = scrip_to_sym.get(str(code).strip())
            if not sym:
                continue
            nk = _normalize_company_lookup_key(cname)
            if nk and len(nk) >= 3:
                out.setdefault(nk, sym)
    except Exception as e:
        logger.debug("BSE company-to-symbol map load notice: %s", e)
    _BSE_COMPANY_SYMBOL_CACHE = out
    return out


def resolve_equity_identifier(isin: str, holding_name: str, isin_map: Dict[str, str]) -> str:
    """Resolves an Indian equity ISIN + company name to an NSE or BSE ticker symbol (L5 guard)."""
    clean_isin = (isin or "").strip().upper()
    if clean_isin and clean_isin in isin_map:
        return isin_map[clean_isin]

    bse_map = _load_bse_company_symbol_map()
    if holding_name and bse_map:
        nk = _normalize_company_lookup_key(holding_name)
        if nk in bse_map:
            return bse_map[nk]
        # Also try retaining INDIA if company name is e.g. 'ABB India Ltd'
        raw_upper = re.sub(r"\b(?:LIMITED|LTD)\b", " ", (holding_name or "").upper())
        raw_upper = re.sub(r"[^A-Z0-9]+", " ", raw_upper).strip()
        for cand_name, sym in bse_map.items():
            if raw_upper and cand_name == raw_upper:
                return sym

    return clean_isin or (holding_name or "UNKNOWN").strip().upper()[:24]


def load_isin_symbol_map(force_refresh: bool = False, allow_network: bool = True) -> Dict[str, str]:
    """Loads `{ISIN: NSE_SYMBOL}` across NSE Mainboard (`EQUITY_L.csv`) and NSE Emerge (`SME_EQUITY_L.csv`)."""
    cache_dir = Path(".cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    mapping: Dict[str, str] = {}

    sources = [
        (cache_dir / "nse_equity_master.csv", NSE_EQUITY_MASTER_URL),
        (cache_dir / "nse_sme_master.csv", NSE_SME_MASTER_URL),
    ]
    for cache_file, url in sources:
        text = None
        if not force_refresh and cache_file.exists() and (
            not allow_network or (time.time() - cache_file.stat().st_mtime) < 7 * 86400
        ):
            text = cache_file.read_text(encoding="utf-8", errors="ignore")
        if text is None and allow_network:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _UA})
                with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=30) as resp:
                    text = resp.read().decode("utf-8", errors="ignore")
                cache_file.write_text(text, encoding="utf-8")
            except Exception as e:
                logger.debug("NSE ISIN feed %s notice (%s); using disk cache if available.", url, e)
                if cache_file.exists():
                    text = cache_file.read_text(encoding="utf-8", errors="ignore")
        if not text:
            continue
        for row in csv.DictReader(io.StringIO(text)):
            row = {(k or "").strip().upper(): (v or "").strip() for k, v in row.items()}
            isin = row.get("ISIN NUMBER") or row.get("ISIN_NUMBER") or row.get("ISIN")
            sym = row.get("SYMBOL")
            if isin and sym:
                mapping.setdefault(isin.upper(), sym.upper())

    return mapping


# --------------------------------------------------------------------------- #
# Holdings assembly + validation + Legacy Twin Sync
# --------------------------------------------------------------------------- #
def _canonical_holdings_source(label: str) -> str:
    low = (label or "").lower()
    if "manual_upload" in low:
        return "manual_inbox"
    if "mfforecast" in low:
        return "mfforecast_api"
    return "sebi_monthly_disclosure"


def build_holdings(parsed: Dict[str, Any], isin_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """Converts a parsed sheet into rows for `save_mutual_fund_holdings` (merging duplicate lines)."""
    as_on = parse_fund_disclosure_date(parsed.get("as_on_date"))
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for h in parsed["holdings"]:
        htype = h["holding_type"]
        if htype in ("EQUITY",):
            ident = resolve_equity_identifier(h.get("isin", ""), h.get("holding_name", ""), isin_map)
        elif htype == "CASH_EQUIVALENT":
            name = h["holding_name"].upper()
            ident = (
                "TREPS"
                if ("TREPS" in name or "TRIPARTY" in name or "CBLO" in name)
                else "NET_CURRENT_ASSETS"
                if ("NET" in name or "RECEIVABLE" in name or "PAYABLE" in name)
                else "REVERSE_REPO"
                if "REPO" in name
                else "CASH"
            )
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
            "instrument_details": {
                **h.get("instrument_details", {}),
                **({"isin": h["isin"]} if h.get("isin") else {}),
            },
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


def _publish_scheme_disclosure(
    row: Dict[str, Any],
    amfi_lookup: Dict[str, Dict[str, Any]],
    holdings: List[Dict[str, Any]],
    as_on: str,
    source: str,
    source_type: str,
    source_hash: str,
    sheet_name: Optional[str] = None,
) -> str:
    from core.db.connection import close_all_pg_pools

    for attempt in range(2):
        try:
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
            if float(row.get("aum_crores") or 0.0) > 0:
                scheme["aum_crores"] = row["aum_crores"]
            scheme["last_portfolio_date"] = as_on
            top10 = round(sum(h["weight_pct"] for h in holdings[:10]), 1)
            meta.update({
                "holdings_source": source_type,
                "holdings_source_url": source,
                "holdings_source_sha256": source_hash,
                "holdings_source_sheet": sheet_name,
                "holdings_as_on": as_on,
                "aum_rank": row.get("aum_rank"),
                "aum_source": "AMFI average AUM (scheme-wise)",
                "top_10_weight_pct": top10,
            })
            scheme["metadata"] = meta
            return publish_mutual_fund_disclosure(scheme, holdings)
        except Exception as exc:
            err_text = f"{type(exc).__name__}: {exc}".lower()
            is_transient_sock = any(
                tok in err_text
                for tok in (
                    "operationalerror",
                    "interfaceerror",
                    "connection already closed",
                    "server closed the connection",
                    "ssl syscall error",
                    "eof detected",
                    "can't assign requested address",
                )
            )
            if attempt == 0 and is_transient_sock:
                logger.warning(
                    "Transient DB socket drop publishing scheme %s (%s); resetting pool and retrying once...",
                    row.get("scheme_code"),
                    exc,
                )
                close_all_pg_pools()
                time.sleep(0.5)
                continue
            raise


def sync_legacy_slug_twins_from_verified_numeric(isin_map: Optional[Dict[str, str]] = None) -> Dict[str, int]:
    """Upgrades non-numeric legacy slug schemes (`PPFAS_FLEXICAP_DIR`, `SBI_FOCUSED_DIR`, etc.)
    from partial Top-10 static seeds to their 6-digit AMFI twin's verified ~100%-weight SEBI portfolio."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM mutual_fund_schemes")
        all_schemes = [clean_dict_row(cur, r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

    slug_to_num = resolve_legacy_slug_twins(all_schemes)
    by_code = {str(s.get("scheme_code") or "").strip(): s for s in all_schemes}
    upgraded = 0

    for slug_code, num_code in slug_to_num.items():
        num_scheme = by_code.get(num_code)
        slug_scheme = by_code.get(slug_code)
        if not num_scheme or not slug_scheme:
            continue
        snapshot = get_current_fund_disclosure(num_code)
        if not snapshot or validate_holdings(snapshot["holdings"]):
            continue

        clean_rows = []
        as_on = snapshot["as_on_date"]
        for holding in snapshot["holdings"]:
            ident = holding["identifier"]
            if holding["holding_type"] == "EQUITY" and _ISIN_EQUITY_RE.match(ident) and isin_map:
                ident = resolve_equity_identifier(ident, holding["holding_name"], isin_map)
            clean_rows.append({**holding, "identifier": ident})

        updated_slug = dict(slug_scheme)
        slug_meta = dict(slug_scheme.get("metadata") or {})
        slug_meta.update({
            "holdings_source": snapshot["holdings_source"],
            "holdings_source_url": snapshot["source_url"],
            "holdings_source_sha256": snapshot.get("source_sha256"),
            "holdings_source_sheet": snapshot.get("source_sheet"),
            "canonical_amfi_code": num_code,
            "holdings_as_on": as_on,
            "top_10_weight_pct": round(sum(r["weight_pct"] for r in clean_rows[:10]), 1),
        })
        if float(num_scheme.get("aum_crores") or 0.0) > 0:
            updated_slug["aum_crores"] = float(num_scheme["aum_crores"])
        updated_slug["last_portfolio_date"] = as_on
        updated_slug["metadata"] = slug_meta

        try:
            publish_mutual_fund_disclosure(
                updated_slug, clean_rows, canonical_snapshot_id=snapshot["snapshot_id"],
            )
        except (ValueError, RuntimeError) as error:
            logger.warning("Legacy scheme %s disclosure was not published: %s", slug_code, error)
            continue
        upgraded += 1

    return {"mapped_twins": len(slug_to_num), "upgraded_slugs": upgraded}


def backfill_existing_raw_equity_isins(isin_map: Optional[Dict[str, str]] = None) -> int:
    """Resolves any existing raw 12-char `IN...` equity identifiers in `mutual_fund_holdings` to NSE/BSE symbols."""
    isin_map = isin_map if isin_map is not None else load_isin_symbol_map()
    conn = get_db_connection()
    cur = conn.cursor()
    p = get_placeholder()
    updated = 0
    try:
        cur.execute(
            """
            SELECT h.id, h.identifier, h.holding_name FROM mutual_fund_holdings h
            WHERE h.holding_type = 'EQUITY' AND h.identifier LIKE 'IN%'
              AND NOT EXISTS (SELECT 1 FROM mf_current_disclosures d WHERE d.scheme_code = h.scheme_code)
            """
        )
        for row_id, ident, hname in cur.fetchall():
            raw_id = str(ident or "").strip().upper()
            if not _ISIN_EQUITY_RE.match(raw_id):
                continue
            resolved = resolve_equity_identifier(raw_id, str(hname or ""), isin_map)
            if resolved and resolved != raw_id and not _ISIN_EQUITY_RE.match(resolved):
                cur.execute(
                    f"UPDATE mutual_fund_holdings SET identifier = {p} WHERE id = {p}",
                    (resolved, row_id),
                )
                updated += 1
        if updated:
            conn.commit()
    finally:
        cur.close()
        conn.close()
    return updated


def _merge_db_numeric_schemes_into_universe(ranked: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Appends active numeric AMFI schemes from `mutual_fund_schemes` (e.g. Index/Gilt/Liquid schemes)
    that were outside `rank_funds_by_aum` so loaded AMC workbooks match 100% of DB schemes."""
    seen = {str(r["scheme_code"]) for r in ranked}
    merged = list(ranked)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT scheme_code, scheme_name, fund_house, category, broad_category, aum_crores FROM mutual_fund_schemes")
            for sc, sname, fh, cat, bcat, aum in cur.fetchall():
                code = str(sc or "").strip()
                if not code.isdigit() or code in seen:
                    continue
                seen.add(code)
                merged.append({
                    "scheme_code": code,
                    "scheme_name": str(sname or ""),
                    "fund_house": str(fh or ""),
                    "category": str(cat or "Other"),
                    "broad_category": str(bcat or "OTHER"),
                    "aum_crores": float(aum or 0.0),
                    "aum_rank": len(merged) + 1,
                })
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.debug("DB numeric universe merge notice: %s", e)
    return merged


def get_monthly_mf_universe() -> List[Dict[str, Any]]:
    ranked = rank_funds_by_aum()
    if not ranked:
        raise RuntimeError("AMFI AUM universe unavailable")
    return _merge_db_numeric_schemes_into_universe(ranked)


# --------------------------------------------------------------------------- #
# Bounded Parallel AMC Workbook Prefetch
# --------------------------------------------------------------------------- #
def _prefetch_amc_workbooks(
    keys: List[str],
    fetch: Callable[[str], Optional[Tuple[bytes, str]]],
    *,
    workers: int,
    per_amc_timeout_s: Optional[float] = None,
    deadline_monotonic: Optional[float] = None,
) -> Tuple[Dict[str, Tuple[str, Any]], Dict[str, str]]:
    """Fetches AMC workbooks on at most `workers` concurrent daemon threads.

    Returns `(outcomes, unfinished)`:
      * `outcomes[key]` is `("ok", (bytes, label) | None)` or `("error", exc)`.
      * `unfinished[key]` is a human-readable reason for AMCs that overran their own deadline
        or were still running / queued when the overall budget ran out.

    Fetch threads are daemons: an AMC that overruns is abandoned (its slot is handed to the next
    queued AMC) and its late result is discarded, so a hung AMC portal can never block process exit
    or the rest of the scheduled pipeline. Nothing is written for unfinished AMCs (fail-closed).
    """
    queue = list(dict.fromkeys(keys))
    active: Dict[str, float] = {}
    finished: Dict[str, Tuple[str, Any]] = {}
    outcomes: Dict[str, Tuple[str, Any]] = {}
    unfinished: Dict[str, str] = {}
    cond = threading.Condition()

    def _worker(key: str) -> None:
        try:
            outcome: Tuple[str, Any] = ("ok", fetch(key))
        except Exception as exc:  # recorded as a fetch error; never fabricates a workbook
            logger.warning("[%s] workbook fetch error: %s", key, exc)
            outcome = ("error", exc)
        with cond:
            finished[key] = outcome
            cond.notify_all()

    with cond:
        while queue or active:
            now = time.monotonic()
            if deadline_monotonic is not None and now >= deadline_monotonic:
                for key in active:
                    unfinished[key] = "time budget exhausted before workbook fetch completed"
                for key in queue:
                    unfinished[key] = "time budget exhausted before workbook fetch started"
                break
            while queue and len(active) < max(1, workers):
                key = queue.pop(0)
                active[key] = now
                threading.Thread(target=_worker, args=(key,), name=f"amc-fetch-{key}", daemon=True).start()
            for key, started in list(active.items()):
                if key in finished:
                    outcomes[key] = finished[key]
                    del active[key]
                elif per_amc_timeout_s is not None and now - started >= per_amc_timeout_s:
                    unfinished[key] = f"workbook fetch timed out after {per_amc_timeout_s:g}s"
                    logger.warning("[%s] workbook fetch abandoned after %gs", key, per_amc_timeout_s)
                    del active[key]
            if not (queue or active):
                break
            if queue and len(active) < max(1, workers):
                continue  # a slot just freed up; launch the next AMC immediately
            wake = 1.0
            if per_amc_timeout_s is not None and active:
                wake = min(wake, min(started + per_amc_timeout_s for started in active.values()) - now)
            if deadline_monotonic is not None:
                wake = min(wake, deadline_monotonic - now)
            cond.wait(timeout=max(0.01, wake))
    return outcomes, unfinished


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
    sync_twins: bool = True,
    only_scheme_codes: Optional[set[str]] = None,
    target_month_end: Optional[str] = None,
    fetch_workers: int = 1,
    per_amc_timeout_s: Optional[float] = None,
    deadline_monotonic: Optional[float] = None,
) -> Dict[str, Any]:
    """Ingests real SEBI statutory portfolios across AMCs up to `target` funds.

    `fetch_workers > 1` opts into bounded parallel workbook prefetch with an optional per-AMC
    deadline (`per_amc_timeout_s`) and an overall `time.monotonic()` deadline. AMCs that do not
    finish in time are skipped with an explicit reason and nothing is written for them. Defaults
    keep the original serial behaviour for every existing caller.
    """
    t0 = time.time()
    sources = load_sources()
    if universe is not None:
        ranked = list(universe)
    else:
        ranked = get_monthly_mf_universe()
    if target_month_end is not None and not parse_fund_disclosure_date(target_month_end):
        raise ValueError("Invalid target month-end")

    def provider(key: str, config: Dict[str, Any]):
        if workbook_provider:
            return workbook_provider(key, config)
        if target_month_end:
            return get_amc_workbook(key, config, target_month_end=date.fromisoformat(target_month_end))
        return get_amc_workbook(key, config)

    isin_map = isin_map if isin_map is not None else load_isin_symbol_map()

    aaum_stats = {"numeric_updated": 0, "slug_twins_updated": 0}
    if not dry_run and (universe is None or target_month_end) and workbook_provider is None:
        try:
            aaum_stats = backfill_scheme_aaum_to_db()
        except Exception as aaum_err:
            logger.warning("AMFI AAUM backfill notice: %s", aaum_err)

    amfi_lookup: Dict[str, Dict[str, Any]] = {}
    if workbook_provider is None:
        try:
            for s in parse_amfi_nav_feed(fetch_amfi_nav_raw(), direct_growth_only=True):
                amfi_lookup[str(s["scheme_code"])] = s
        except Exception as e:
            logger.warning("AMFI NAV master unavailable for scheme enrichment: %s", e)

    # Group ranked universe by AMC so 2-pass bipartite sheet claiming prevents L3 collisions
    schemes_by_amc: Dict[str, List[Dict[str, Any]]] = {}
    for row in ranked:
        k = amc_key_for_fund_house(row["fund_house"], sources)
        if k:
            schemes_by_amc.setdefault(k, []).append(row)

    workbook_cache: Dict[str, Optional[Dict[str, Any]]] = {}
    amc_sheet_claims: Dict[str, Dict[str, str]] = {}
    amc_status: Dict[str, str] = {}
    ingested: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    prefetched: Dict[str, Tuple[str, Any]] = {}
    unfinished_amcs: Dict[str, str] = {}
    if fetch_workers > 1:
        needed_amcs: List[str] = []
        for row in ranked:
            if only_scheme_codes is not None and str(row["scheme_code"]).strip() not in only_scheme_codes:
                continue
            k = amc_key_for_fund_house(row["fund_house"], sources)
            if k and (not only_amcs or k in only_amcs) and k not in needed_amcs:
                needed_amcs.append(k)
        logger.info(
            "Prefetching %d AMC workbooks (%d workers, per-AMC deadline %s).",
            len(needed_amcs), fetch_workers, f"{per_amc_timeout_s:g}s" if per_amc_timeout_s else "none",
        )
        prefetched, unfinished_amcs = _prefetch_amc_workbooks(
            needed_amcs,
            lambda k: provider(k, sources[k]),
            workers=fetch_workers,
            per_amc_timeout_s=per_amc_timeout_s,
            deadline_monotonic=deadline_monotonic,
        )

    def load_amc(key: str) -> Optional[Dict[str, Any]]:
        if key in workbook_cache:
            return workbook_cache[key]
        if key in unfinished_amcs:
            amc_status[key] = unfinished_amcs[key]
            workbook_cache[key] = None
            return None
        if key in prefetched:
            kind, payload = prefetched[key]
            if kind == "error":
                amc_status[key] = f"workbook fetch error: {payload}"
                workbook_cache[key] = None
                return None
            got = payload
        else:
            got = provider(key, sources[key])
        if not got:
            amc_status[key] = "no workbook available (no verified URL and no manual upload)"
            workbook_cache[key] = None
            return None
        data, label = got
        try:
            sheets = parse_workbook(data)
        except Exception as e:
            logger.warning("Unparseable workbook for %s: %s", key, e)
            amc_status[key] = f"unparseable workbook: {e}"
            workbook_cache[key] = None
            return None
        titles = {n: p["scheme_name"] or n for n, p in sheets.items()}
        amc_status[key] = f"ok: {len(sheets)} scheme sheets from {label}"
        workbook_cache[key] = {
            "sheets": sheets,
            "titles": titles,
            "source": label,
            "source_hash": hashlib.sha256(data).hexdigest(),
        }
        amc_sheet_claims[key] = match_schemes_to_workbook_sheets(schemes_by_amc.get(key, []), sheets)
        return workbook_cache[key]

    budget_exhausted = bool(unfinished_amcs) and deadline_monotonic is not None and time.monotonic() >= deadline_monotonic
    for row in ranked:
        if len(ingested) >= target:
            break
        if only_scheme_codes is not None and str(row["scheme_code"]).strip() not in only_scheme_codes:
            continue
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            budget_exhausted = True
            skipped.append({**_brief(row), "reason": "time budget exhausted"})
            continue
        key = amc_key_for_fund_house(row["fund_house"], sources)
        if not key or (only_amcs and key not in only_amcs):
            skipped.append({**_brief(row), "reason": "AMC not in scope" if key else "AMC not in registry"})
            continue
        book = load_amc(key)
        if not book:
            # Check optional sanctioned MFFORECAST_RAPIDAPI_KEY fallback before skipping
            fb = _fetch_mfforecast_holdings_if_configured(str(row["scheme_code"]), isin_map) if workbook_provider is None else None
            if fb:
                holdings, as_on, source, source_hash = fb
                if target_month_end and as_on != target_month_end:
                    skipped.append({**_brief(row), "reason": "vendor disclosure is for a different month"})
                    continue
                try:
                    if not dry_run:
                        _publish_scheme_disclosure(row, amfi_lookup, holdings, as_on, source, "mfforecast_api", source_hash)
                except (ValueError, RuntimeError) as error:
                    skipped.append({**_brief(row), "reason": str(error)})
                    continue
                ingested.append({**_brief(row), "holdings_count": len(holdings), "as_on": as_on, "source": source})
                continue
            skipped.append({**_brief(row), "reason": amc_status[key]})
            continue

        sheet_key = (amc_sheet_claims.get(key) or {}).get(str(row["scheme_code"]))
        if not sheet_key:
            skipped.append({**_brief(row), "reason": "no matching scheme sheet in AMC workbook"})
            continue

        parsed = book["sheets"][sheet_key]
        as_on = parse_fund_disclosure_date(parsed.get("as_on_date"))
        if not as_on or as_on > datetime.now(IST).date().isoformat():
            skipped.append({**_brief(row), "reason": "missing, invalid, conflicting or future disclosure date"})
            continue
        if target_month_end and as_on != target_month_end:
            skipped.append({**_brief(row), "reason": "disclosure is for a different month"})
            continue
        holdings = build_holdings(parsed, isin_map)
        problem = validate_holdings(holdings)
        if problem:
            skipped.append({**_brief(row), "reason": f"validation failed: {problem}"})
            continue

        if not dry_run:
            try:
                _publish_scheme_disclosure(
                    row,
                    amfi_lookup,
                    holdings,
                    as_on,
                    book["source"],
                    _canonical_holdings_source(book["source"]),
                    book["source_hash"],
                    sheet_name=sheet_key,
                )
            except (ValueError, RuntimeError) as error:
                skipped.append({**_brief(row), "reason": str(error)})
                continue
        ingested.append({**_brief(row), "holdings_count": len(holdings), "as_on": as_on, "source": book["source"]})

    twin_stats = {"mapped_twins": 0, "upgraded_slugs": 0}
    isin_backfilled = 0
    if budget_exhausted and sync_twins and not dry_run:
        logger.warning("MF ingest time budget exhausted; deferring legacy slug-twin sync to the next run.")
    if not dry_run and sync_twins and workbook_provider is None and not budget_exhausted:
        try:
            isin_backfilled = backfill_existing_raw_equity_isins(isin_map)
            twin_stats = sync_legacy_slug_twins_from_verified_numeric(isin_map)
        except Exception as tw_err:
            logger.warning("Legacy slug twin upgrade notice: %s", tw_err)

    audited = 0
    if audit and not dry_run:
        from core.analysis.fund_overlap_auditor import audit_single_fund_daily

        for item in ingested:
            try:
                audit_single_fund_daily(item["scheme_code"])
                audited += 1
            except Exception as e:
                logger.warning("Audit failed for %s: %s", item["scheme_code"], e)

    return {
        "target": target,
        "ingested_count": len(ingested),
        "target_met": len(ingested) >= target,
        "ingested": ingested,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "amc_status": amc_status,
        "timed_out_amcs": sorted(unfinished_amcs),
        "budget_exhausted": budget_exhausted,
        "aaum_backfill": aaum_stats,
        "twin_sync": twin_stats,
        "raw_isins_resolved": isin_backfilled,
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
