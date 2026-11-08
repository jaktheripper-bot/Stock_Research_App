"""Evidence eligibility, constituent scope partitioning, and versioned research signals for fund look-through."""

from datetime import datetime, timedelta
from hashlib import sha256
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

from core.analysis.financial_invariants import RAW_ISIN_RE
from core.db.connection import IST

METHOD_VERSION = "fund-lookthrough-evidence-v1"
RESEARCH_MAX_AGE_DAYS = 180
MAX_SYNTHESIZABLE_CONSTITUENTS_PER_SLA = 5

PRIMARY_SOURCE_HOSTS = (
    "bseindia.com",
    "nseindia.com",
    "sebi.gov.in",
    "rbi.org.in",
    "mca.gov.in",
    "sec.gov",
)

PILLAR_LABELS = {
    "macro": {"stable", "headwinds", "neutral"},
    "moat": {"wide", "moderate", "narrow", "strong"},
    "governance": {"clean", "caution", "high risk"},
    "diagnostic": {"temporary", "structural", "neutral", "n/a"},
    "valuation": {"undervalued", "fair", "stretched", "loss-making"},
    "balance_sheet": {"debt-free", "moderate debt", "high debt", "resilient"},
    "capital_allocation": {"disciplined", "moderate", "strained", "clean"},
}

_URL_RE = re.compile(r"https://[^\s\)\]>\"']+")


def _is_official_primary_url(raw_url: str) -> Optional[str]:
    clean = str(raw_url or "").strip().rstrip(".,;)")
    if not clean:
        return None
    try:
        parts = urlsplit(clean)
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    if parts.scheme != "https" or not host:
        return None
    if "vertexaisearch.cloud.google.com" in host:
        return None
    if any(host == domain or host.endswith("." + domain) for domain in PRIMARY_SOURCE_HOSTS):
        return clean
    return None


def _primary_source_links(citations: Any, report_text: str = "") -> List[str]:
    links = set()
    for citation in citations or ():
        uri = None
        if isinstance(citation, dict):
            uri = citation.get("uri") or citation.get("url")
        elif isinstance(citation, str):
            uri = citation
        if isinstance(uri, str):
            accepted = _is_official_primary_url(uri)
            if accepted:
                links.add(accepted)
    if not links and report_text:
        for match in _URL_RE.findall(report_text):
            accepted = _is_official_primary_url(match)
            if accepted:
                links.add(accepted)
    return sorted(links)


def _parse_report_timestamp(report: Dict[str, Any]) -> Optional[datetime]:
    for key in ("raw_timestamp", "timestamp", "updated_at", "created_at"):
        raw = report.get(key)
        if not raw:
            continue
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=IST)
        text = str(raw).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def qualify_fund_research(
    report: Optional[Dict[str, Any]],
    ticker: str,
    *,
    analyzed_at: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Return reproducible qualitative inputs for an eligible archived report."""
    clean_ticker = str(ticker or "").strip().upper()
    if not clean_ticker or RAW_ISIN_RE.match(clean_ticker):
        return None
    if not report or str(report.get("ticker", "")).strip().upper() != clean_ticker:
        return None
    text = report.get("report_text")
    if not isinstance(text, str) or len(text.strip()) < 500:
        return None

    timestamp = _parse_report_timestamp(report)
    if timestamp is None:
        return None
    now_dt = analyzed_at or datetime.now(IST)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=IST)
    if not now_dt - timedelta(days=RESEARCH_MAX_AGE_DAYS) <= timestamp <= now_dt + timedelta(minutes=5):
        return None

    section = re.search(r"(?im)^#{1,6}\s*Health\s+Matrix[ \t]*\n(?P<block>.*?)(?=^#{1,6} |\Z)", text, re.S | re.M)
    if not section:
        return None
    matrix: Dict[str, str] = {}
    for line in section.group("block").splitlines():
        label, sep, value = line.strip().lstrip("-*• ").replace("**", "").replace("`", "").partition(":")
        key = label.strip().lower().replace(" ", "_")
        if not sep or key not in PILLAR_LABELS:
            continue
        clean_val = value.strip().strip("*[] ").lower()
        if key in matrix or clean_val not in PILLAR_LABELS[key]:
            return None
        matrix[key] = clean_val
    links = _primary_source_links(report.get("citations"), text)
    if set(matrix) != set(PILLAR_LABELS) or not links:
        return None

    return {
        "ticker": clean_ticker,
        "report_timestamp": timestamp.isoformat(),
        "report_sha256": sha256(text.encode("utf-8")).hexdigest(),
        "primary_source_links": links,
        "pillar_inputs": matrix,
    }


def partition_constituent_quote_scope(
    holdings: Iterable[Dict[str, Any]],
    get_report_fn: Any,
    *,
    analyzed_at: Optional[datetime] = None,
    max_synthesizable: int = MAX_SYNTHESIZABLE_CONSTITUENTS_PER_SLA,
) -> Dict[str, Any]:
    """Partition equity holdings into cached, synthesizable domestic, and excluded non-synthesizable buckets.

    Prevents charging users for `FOREIGN_EQUITY` or unresolved raw ISINs (`INE...`) that the Indian
    NSE/BSE stock synthesis pipeline cannot produce, and signals when `uncached_domestic_tickers`
    exceeds the synchronous 15-minute SLA budget.
    """
    cached: List[str] = []
    synthesizable_domestic: List[Tuple[str, float]] = []
    excluded_foreign: List[str] = []
    excluded_unresolved_isin: List[str] = []
    seen = set()
    prequalified_set = (
        {str(s).strip().upper() for s in get_report_fn}
        if isinstance(get_report_fn, (set, frozenset))
        else None
    )

    for holding in holdings:
        htype = str(holding.get("holding_type") or "").strip().upper()
        ident = str(holding.get("identifier") or "").strip().upper()
        weight = float(holding.get("weight_pct") or 0.0)
        if not ident or weight <= 0 or (htype, ident) in seen:
            continue
        seen.add((htype, ident))

        if prequalified_set is not None and ident in prequalified_set:
            cached.append(ident)
            continue

        if htype == "FOREIGN_EQUITY":
            excluded_foreign.append(ident)
            continue
        if htype not in ("EQUITY", "RAW_ISIN_EQUITY"):
            continue
        if RAW_ISIN_RE.match(ident) or htype == "RAW_ISIN_EQUITY":
            excluded_unresolved_isin.append(ident)
            continue

        if prequalified_set is not None:
            is_cached = ident in prequalified_set
        else:
            rep = get_report_fn(ident)
            is_cached = qualify_fund_research(rep, ident, analyzed_at=analyzed_at) is not None
        if is_cached:
            cached.append(ident)
        else:
            synthesizable_domestic.append((ident, weight))

    synthesizable_domestic.sort(key=lambda item: (-item[1], item[0]))
    billable_tickers = [t for t, _ in synthesizable_domestic]
    exceeds_sla = len(billable_tickers) > max_synthesizable

    return {
        "cached_tickers": sorted(cached),
        "billable_domestic_tickers": billable_tickers,
        "excluded_foreign_tickers": sorted(excluded_foreign),
        "excluded_unresolved_isin_tickers": sorted(excluded_unresolved_isin),
        "max_synthesizable_per_sla": max_synthesizable,
        "deep_dive_available": not exceeds_sla,
        "deep_dive_unavailable_reason": (
            f"Deep-dive constituent synthesis requires {len(billable_tickers)} uncached stocks, "
            f"exceeding the {max_synthesizable}-stock synchronous SLA limit."
            if exceeds_sla
            else None
        ),
    }
