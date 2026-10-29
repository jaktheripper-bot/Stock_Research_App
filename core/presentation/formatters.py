"""Canonical institutional metric, sentinel, and timestamp formatters (Feedback #4 & #10).

Enforces uniform conventions across Homepage, Stock Discovery @9AM, Equities Directory,
Omni-Search, and Research Dossiers:
- Multiples (P/E, EV/EBITDA, P/B): 1 decimal + 'x' (e.g. '22.2x'); negative EPS -> 'NM'
  (Not Meaningful); missing/qualitative leaks ('N/A', 'Fair', None) -> '—' with reason tooltip.
- Leverage (D/E): 2 decimals + 'x' (e.g. '0.10x'); BFSI banks/insurers/lenders where
  industrial D/E is inapplicable -> 'BFSI' with CRAR/NPA tooltip; missing -> '—' (never
  silently coerced to '0.00x'). Normalizes Yahoo Finance percentage points (e.g. 9.83% -> 0.10x).
- Percentages (ROCE, ROE, OPM): 1 decimal + '%' (e.g. '55.0%') or '—' with tooltip.
- Dates & Timestamps: 'DD Mon YYYY' (e.g. '25 Oct 2026') and 'DD Mon YYYY, HH:MM IST'
  across ISO strings, YYYY-MM-DD strings, datetime objects, and Unix epoch integers.
"""

from datetime import date, datetime, timedelta, timezone
import logging
import math
import re
from typing import Any, Dict, Optional

IST = timezone(timedelta(hours=5, minutes=30))

logger = logging.getLogger("equity_research.core.presentation.formatters")

BFSI_KEYWORDS = (
    "bank",
    "banking",
    "insurance",
    "life insurance",
    "general insurance",
    "nbfc",
    "finserv",
    "finance",
    "housing finance",
    "microfinance",
    "asset management",
    "amc",
    "broking",
    "financial services",
)

BFSI_EXPLICIT_TICKERS = frozenset({
    "RECLTD",
    "PFC",
    "IRFC",
    "HUDCO",
    "LTF",
    "CHOLAFIN",
    "CHOLAHLDNG",
    "BAJFINANCE",
    "BAJAJFINSV",
    "SHRIRAMFIN",
    "MUTHOOTFIN",
    "MANAPPURAM",
    "POONAWALLA",
    "JIOFIN",
    "PIRAMALFIN",
    "SBICARD",
    "SBILIFE",
    "HDFCLIFE",
    "ICICIPRULI",
    "ICICIGI",
    "LICI",
    "MFSL",
    "IIFL",
    "IIFLCAPS",
    "UTIAMC",
    "HDFCAMC",
    "KFINTECH",
    "CAMS",
    "MCX",
    "BSE",
    "ANGELONE",
    "MOTILALOFS",
})

_MISSING_SENTINELS = frozenset({
    "",
    "-",
    "—",
    "–",
    "n/a",
    "na",
    "none",
    "null",
    "nan",
    "fair",
    "undervalued",
    "stretched",
    "pending",
    "unrated",
})

_LOSS_SENTINELS = frozenset({
    "nm",
    "n/m",
    "loss",
    "loss-making",
    "n/a (loss-making)",
    "na (loss-making)",
    "negative",
    "neg",
    "neg eps",
})


def is_bfsi_entity(
    ticker: str = "",
    sector_slug: str = "",
    sector_label: str = "",
    industry: str = "",
    company_name: str = "",
) -> bool:
    """Returns True if the entity is a Bank, Insurer, NBFC, AMC, or Financial Services firm."""
    t_up = str(ticker or "").strip().upper()
    if t_up in BFSI_EXPLICIT_TICKERS:
        return True
    if str(sector_slug or "").strip().upper() == "BFSI":
        return True
    try:
        from core.analysis.sector_scoring import KNOWN_TICKER_SECTORS
        if t_up and KNOWN_TICKER_SECTORS.get(t_up) == "BFSI":
            return True
    except Exception as sec_err:
        logger.debug("Sector lookup notice for %s: %s", t_up, sec_err)
    combined = f"{ticker} {sector_label} {industry} {company_name}".lower()
    return any(kw in combined for kw in BFSI_KEYWORDS)


def normalize_de_ratio(
    raw_val: Any,
    *,
    is_yfinance_pct: bool = False,
    source: str = "",
    ticker: str = "",
    sector_slug: str = "",
    industry: str = "",
    company_name: str = "",
) -> Optional[float]:
    """Normalizes raw Debt-to-Equity into a clean ratio multiple (e.g. 0.10 for 10% D/E).

    - Never coerces None / 'N/A' to 0.0.
    - Converts Yahoo Finance percentage values (e.g. 9.83 meaning 9.83% = 0.0983x) via / 100.0.
    - Returns None for BFSI entities when D/E is unpopulated or distorted by deposit/float liabilities.
    """
    if raw_val is None:
        return None
    if isinstance(raw_val, bool):
        return None

    is_pct_str = False
    if isinstance(raw_val, str):
        s = raw_val.strip()
        s_low = s.lower()
        if s_low in _MISSING_SENTINELS or "bfsi" in s_low:
            return None
        if s.endswith("%"):
            is_pct_str = True
            s = s[:-1].strip()
        elif s_low.endswith("x"):
            s = s[:-1].strip()
        s = s.replace(",", "")
        try:
            val = float(s)
        except ValueError:
            return None
    elif isinstance(raw_val, (int, float)):
        val = float(raw_val)
    else:
        try:
            val = float(raw_val)
        except (TypeError, ValueError):
            return None

    if math.isnan(val) or math.isinf(val) or val < 0:
        return None

    if is_yfinance_pct or is_pct_str or str(source or "").upper() == "YFINANCE_PCT":
        val = val / 100.0

    if is_bfsi_entity(
        ticker=ticker,
        sector_slug=sector_slug,
        industry=industry,
        company_name=company_name,
    ) and val > 2.5:
        return None

    return round(val, 2)


def normalize_pe_raw(raw_val: Any) -> str:
    """Normalizes stored P/E string for DB persistence ('22.50', 'NM', or 'N/A'). Never returns 'Fair'."""
    if raw_val is None or isinstance(raw_val, bool):
        return "N/A"

    if isinstance(raw_val, (int, float)):
        fval = float(raw_val)
        if math.isnan(fval) or math.isinf(fval) or fval == 0.0:
            return "N/A"
        if fval < 0:
            return "NM"
        return f"{fval:.2f}"

    s = str(raw_val).strip()
    s_low = s.lower()
    if s_low in _LOSS_SENTINELS or "loss" in s_low:
        return "NM"
    if s_low in _MISSING_SENTINELS:
        return "N/A"

    s_clean = re.sub(r"(?i)\s*(?:x|times)$", "", s).replace(",", "").strip()
    try:
        fval = float(s_clean)
    except ValueError:
        return "N/A"

    if math.isnan(fval) or math.isinf(fval) or fval == 0.0:
        return "N/A"
    if fval < 0:
        return "NM"
    return f"{fval:.2f}"


def format_pe_multiple(raw_val: Any) -> Dict[str, Any]:
    """Formats P/E consistently across all UI cards with institutional tooltip context."""
    norm = normalize_pe_raw(raw_val)
    if norm == "NM":
        return {
            "display": "NM",
            "tooltip": "Not Meaningful (NM): Trailing 12-month net profit (EPS) is negative; evaluate via P/B or EV/Sales.",
            "float_val": None,
            "status": "nm",
        }
    if norm == "N/A":
        return {
            "display": "—",
            "tooltip": "Pending Filing Sync: Trailing 12-month P/E awaiting statutory earnings reconciliation.",
            "float_val": None,
            "status": "missing",
        }

    fval = float(norm)
    if fval < 3.0:
        tip = (
            f"Optical Low Trailing P/E ({fval:.1f}x): Share price compressed sharply relative to historical "
            f"trailing 12-month EPS or reflects non-recurring income; inspect Pillar 03 Solvency & Governance."
        )
        status = "distressed_low"
    elif fval > 80.0:
        tip = (
            f"Trailing TTM P/E ({fval:.1f}x): Elevated optical multiple — often reflects cyclical/trough "
            f"earnings or early capex ramp; inspect EV/EBITDA and Reverse-DCF."
        )
        status = "elevated"
    else:
        tip = f"Trailing TTM P/E ({fval:.1f}x): Market Price divided by Trailing 12-Month Diluted EPS."
        status = "ok"

    return {
        "display": f"{fval:.1f}x",
        "tooltip": tip,
        "float_val": round(fval, 2),
        "status": status,
    }


def format_de_multiple(
    raw_val: Any,
    *,
    ticker: str = "",
    sector_slug: str = "",
    sector_label: str = "",
    industry: str = "",
    company_name: str = "",
) -> Dict[str, Any]:
    """Formats Debt-to-Equity consistently across all UI cards without fabricating 0.00x."""
    bfsi = is_bfsi_entity(
        ticker=ticker,
        sector_slug=sector_slug,
        sector_label=sector_label,
        industry=industry,
        company_name=company_name,
    )
    norm_val = normalize_de_ratio(
        raw_val,
        ticker=ticker,
        sector_slug=sector_slug,
        industry=industry,
        company_name=company_name,
    )

    if norm_val is None:
        if bfsi:
            return {
                "display": "BFSI",
                "tooltip": (
                    "Financials / BFSI: Deposit, insurance, and lending balance sheets are evaluated via "
                    "Capital Adequacy (CRAR) and Net NPA rather than industrial D/E."
                ),
                "float_val": None,
                "status": "bfsi",
            }
        return {
            "display": "—",
            "tooltip": "Pending Filing Sync: Balance-sheet debt-to-equity awaiting statutory filing extract.",
            "float_val": None,
            "status": "missing",
        }

    if norm_val == 0.0:
        tip = "Debt-Free Balance Sheet (0.00x): Zero gross borrowings or net-cash position in latest audited filing."
        status = "debt_free"
    elif norm_val <= 0.50:
        tip = (
            f"Conservative Leverage ({norm_val:.2f}x): Total Debt / Shareholder Equity ≤ 0.50x "
            f"(includes Ind-AS 116 lease liabilities where applicable)."
        )
        status = "conservative"
    elif norm_val <= 1.50:
        tip = f"Moderate Leverage ({norm_val:.2f}x): Total Debt / Shareholder Equity."
        status = "moderate"
    else:
        tip = (
            f"Elevated Leverage ({norm_val:.2f}x): Total Debt / Shareholder Equity > 1.50x — "
            f"verify Interest Coverage Ratio (ICR) in Pillar 03."
        )
        status = "elevated"

    return {
        "display": f"{norm_val:.2f}x",
        "tooltip": tip,
        "float_val": norm_val,
        "status": status,
    }


def format_pct_metric(
    raw_val: Any,
    *,
    metric_name: str = "ROCE",
    signed: bool = False,
) -> Dict[str, Any]:
    """Formats percentage profitability/return metrics consistently ('55.0%' or '—')."""
    if raw_val is None or isinstance(raw_val, bool):
        return {
            "display": "—",
            "tooltip": f"Pending Filing Sync: {metric_name} awaiting statutory filing extract.",
            "float_val": None,
            "status": "missing",
        }

    s = str(raw_val).replace("%", "").replace(",", "").strip()
    if s.lower() in _MISSING_SENTINELS:
        return {
            "display": "—",
            "tooltip": f"Pending Filing Sync: {metric_name} awaiting statutory filing extract.",
            "float_val": None,
            "status": "missing",
        }

    try:
        fval = float(s)
    except ValueError:
        return {
            "display": "—",
            "tooltip": f"Pending Filing Sync: {metric_name} awaiting statutory filing extract.",
            "float_val": None,
            "status": "missing",
        }

    if math.isnan(fval) or math.isinf(fval):
        return {
            "display": "—",
            "tooltip": f"Pending Filing Sync: {metric_name} awaiting statutory filing extract.",
            "float_val": None,
            "status": "missing",
        }

    prefix = "+" if (signed and fval > 0) else ""
    return {
        "display": f"{prefix}{fval:.1f}%",
        "tooltip": f"{metric_name}: {prefix}{fval:.1f}% (audited trailing filing basis).",
        "float_val": round(fval, 2),
        "status": "ok",
    }


def format_52w_range(low_val: Any, high_val: Any) -> str:
    """Formats 52-week range cleanly ('₹1,976.00 – ₹3,336.70') or '—' when unavailable."""
    def _parse_price(v: Any) -> Optional[float]:
        if v is None or isinstance(v, bool):
            return None
        s = str(v).replace("₹", "").replace(",", "").strip()
        if s.lower() in _MISSING_SENTINELS:
            return None
        try:
            f = float(s)
            return f if (not math.isnan(f) and not math.isinf(f) and f > 0) else None
        except ValueError:
            return None

    lo = _parse_price(low_val)
    hi = _parse_price(high_val)
    if lo is None or hi is None:
        return "—"
    return f"₹{lo:,.2f} – ₹{hi:,.2f}"


def _coerce_datetime(raw_ts: Any) -> Optional[datetime]:
    """Parses datetime, date, ISO string, IST/UTC-labelled string, YYYY-MM-DD, or Unix epoch into IST datetime."""
    if raw_ts is None or raw_ts == "":
        return None
    try:
        if isinstance(raw_ts, datetime):
            dt = raw_ts if raw_ts.tzinfo else raw_ts.replace(tzinfo=timezone.utc)
            return dt.astimezone(IST)
        if isinstance(raw_ts, date):
            return datetime(raw_ts.year, raw_ts.month, raw_ts.day, tzinfo=IST)
        if isinstance(raw_ts, (int, float)) and not isinstance(raw_ts, bool):
            epoch = float(raw_ts)
            if epoch > 1e12:
                epoch /= 1000.0
            if epoch > 946684800:  # >= 2000-01-01
                return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(IST)
            return None

        s = str(raw_ts).strip()
        if not s or s.upper() in ("N/A", "NA", "NONE", "NULL", "—", "-"):
            return None
        if re.fullmatch(r"\d{10}(?:\.\d+)?", s):
            return datetime.fromtimestamp(float(s), tz=timezone.utc).astimezone(IST)
        if re.fullmatch(r"\d{13}", s):
            return datetime.fromtimestamp(float(s) / 1000.0, tz=timezone.utc).astimezone(IST)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            d = datetime.strptime(s, "%Y-%m-%d")
            return d.replace(tzinfo=IST)

        if re.search(r"\s+IST$", s, flags=re.IGNORECASE):
            body = re.sub(r"\s+IST$", "", s, flags=re.IGNORECASE).strip()
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%d %b %Y, %H:%M",
                "%d %B %Y, %H:%M",
                "%d %B %Y, %I:%M %p",
                "%d-%m-%Y %H:%M",
                "%d-%b-%Y %H:%M",
            ):
                try:
                    return datetime.strptime(body, fmt).replace(tzinfo=IST)
                except ValueError:
                    continue
            dt_ist = datetime.fromisoformat(body)
            return (dt_ist if dt_ist.tzinfo else dt_ist.replace(tzinfo=IST)).astimezone(IST)

        if re.search(r"\s+(?:UTC|GMT)$", s, flags=re.IGNORECASE):
            body = re.sub(r"\s+(?:UTC|GMT)$", "", s, flags=re.IGNORECASE).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d %b %Y, %H:%M"):
                try:
                    return datetime.strptime(body, fmt).replace(tzinfo=timezone.utc).astimezone(IST)
                except ValueError:
                    continue
            dt_utc = datetime.fromisoformat(body)
            return (dt_utc if dt_utc.tzinfo else dt_utc.replace(tzinfo=timezone.utc)).astimezone(IST)

        iso_clean = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_clean)
        if not dt.tzinfo:
            # SQLite CURRENT_TIMESTAMP / datetime('now') produces naive UTC strings
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST)
    except Exception as err:
        logger.debug("Date coercion notice for %r: %s", raw_ts, err)
        return None


def format_standard_date(raw_ts: Any, fallback: str = "—") -> str:
    """Formats any date/timestamp into uniform institutional 'DD Mon YYYY' (e.g. '25 Oct 2026')."""
    dt = _coerce_datetime(raw_ts)
    if not dt:
        return fallback
    return dt.strftime("%d %b %Y")


def format_standard_timestamp(raw_ts: Any, fallback: str = "—") -> str:
    """Formats any timestamp into uniform 'DD Mon YYYY, HH:MM IST' (or 'DD Mon YYYY' if midnight/date-only)."""
    if isinstance(raw_ts, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_ts.strip()):
        return format_standard_date(raw_ts, fallback=fallback)
    dt = _coerce_datetime(raw_ts)
    if not dt:
        return fallback
    return dt.strftime("%d %b %Y, %H:%M IST")
