"""AMC Monthly Portfolio Disclosure Parser.

SEBI requires every AMC to publish month-end portfolio statements. AMCs publish them
as Excel/CSV workbooks or ZIP bundles in a broadly common layout: one sheet per scheme
(plus an optional Index/Summary sheet), a header row
(ISIN | Name of the Instrument | Industry / Rating | Quantity | Market Value | % to NAV),
and section rows ("Equity & Equity related", "Debt Instruments", "Money Market
Instruments", ...). This module parses that layout generically:

* Sniffs the real file format from bytes (AMCs ship xlsx content under .xls names, and
  multi-workbook archives as .zip bundles).
* Resolves Index/Summary shortcode tables and "(Formerly known as ...)" scheme aliases.
* Locates columns from header text instead of fixed positions.
* Normalises % to NAV whether the AMC reports 2.93 or 0.0293.
* Enforces collision-proof numeric & strategy-qualifier compatibility before fuzzy matching.
"""

import csv
import difflib
import io
import logging
import re
import zipfile
from datetime import date, datetime
from typing import Any, Dict, Generator, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}

_STOP_MARKERS = (
    "notes:",
    "notes",
    "derivatives disclosure",
    "additional notes",
    "benchmark name",
    "scheme riskometer",
    "benchmark riskometer",
    "product label",
)
_TOTAL_PREFIXES = (
    "total",
    "sub total",
    "subtotal",
    "grand total",
    "net assets",
    "grand",
    "aum",
)

_BANNER_SKIP_PATTERNS = re.compile(
    r"(?i)^(?:"
    r"monthly\s+portfolio.*|"
    r"portfolio\s+(?:statement|disclosure).*|"
    r"statement\s+of\s+portfolio.*|"
    r"[a-z0-9\s&.'\-]+\s+mutual\s+fund|"
    r"[a-z0-9\s&.'\-]+\s+asset\s+management.*|"
    r"unhedged\s+portfolio.*|"
    r"as\s+on\s+.*"
    r")$"
)

_FORMERLY_RE = re.compile(
    r"\(\s*(?:formerly(?:\s+known\s+as)?|erstwhile)\s+([^)]+)\)",
    re.IGNORECASE,
)

# Strategy & asset-class qualifiers that must NEVER mismatch across a fuzzy match (L3 guard)
_CRITICAL_QUALIFIER_TOKENS: Set[str] = {
    "ultra",
    "low",
    "short",
    "medium",
    "long",
    "overnight",
    "liquid",
    "money",
    "gilt",
    "dynamic",
    "corporate",
    "credit",
    "banking",
    "psu",
    "financial",
    "pharma",
    "healthcare",
    "technology",
    "digital",
    "infrastructure",
    "consumption",
    "consumer",
    "automotive",
    "manufacturing",
    "defence",
    "energy",
    "commodities",
    "mnc",
    "dividend",
    "contra",
    "value",
    "focused",
    "elss",
    "arbitrage",
    "balanced",
    "aggressive",
    "conservative",
    "multi",
    "gold",
    "silver",
    "nasdaq",
    "global",
    "international",
    "small",
    "mid",
    "large",
    "flexi",
    "next",
    "equal",
    "momentum",
    "quality",
    "alpha",
    "index",
    "nifty",
    "sensex",
    "bse",
    "fmp",
    "interval",
    "retirement",
    "children",
    " ESG ".strip().lower(),
    "esg",
    "quant",
    "innovative",
    "innovation",
    "business",
    "cycle",
    "special",
    "ethical",
    "shariah",
    "rural",
    "export",
    "services",
    "transportation",
    "logistics",
}

_QUALIFIER_CANON_SUBS = (
    (r"\bflexicap\b", "flexi cap"),
    (r"\blargecap\b", "large cap"),
    (r"\bmidcap\b", "mid cap"),
    (r"\bsmallcap\b", "small cap"),
    (r"\bmulticap\b", "multi cap"),
    (r"\binfra\b", "infrastructure"),
    (r"\btech\b", "technology"),
    (r"\bauto\b", "automotive"),
    (r"\bfin\s+serv(?:ices)?\b", "financial services"),
    (r"\btax\s+saver\b", "elss"),
)

MAX_ZIP_MEMBERS = 250
MAX_ZIP_MEMBER_BYTES = 80 * 1024 * 1024


# --------------------------------------------------------------------------- #
# Workbook loading (.xlsx, .xls, .csv, and multi-workbook .zip bundles)
# --------------------------------------------------------------------------- #
def sniff_format(data: bytes) -> str:
    """Returns 'xlsx', 'zip', 'xls', 'html' or 'csv' from file magic bytes (never trusts extension)."""
    if data[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = {n.replace("\\", "/").lower() for n in zf.namelist()}
                if "xl/workbook.xml" in names or any(n.endswith("workbook.xml") for n in names):
                    return "xlsx"
                return "zip"
        except Exception as zip_err:
            logger.debug("ZIP magic inspection fallback to xlsx: %s", zip_err)
            return "xlsx"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls"
    head = data[:512].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html") or head.startswith(b"<?xml"):
        if b"<html" in head or b"<!doctype html" in head:
            return "html"
    return "csv"


def load_sheets(
    data: bytes, _depth: int = 0
) -> Generator[Tuple[str, Iterable[List[Any]]], None, None]:
    """Yields `(sheet_name, row_iterator)` for every sheet in an xlsx/xls/csv/zip payload."""
    fmt = sniff_format(data)
    if fmt == "html":
        raise ValueError("Expected a spreadsheet but received an HTML page (blocked or moved link).")

    if fmt == "zip":
        if _depth > 2:
            return
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()][:MAX_ZIP_MEMBERS]
            for info in infos:
                lower_name = info.filename.lower()
                if lower_name.startswith("__macosx") or "/." in lower_name:
                    continue
                if not lower_name.endswith((".xlsx", ".xls", ".csv", ".zip")):
                    continue
                if info.file_size > MAX_ZIP_MEMBER_BYTES:
                    continue
                try:
                    member_bytes = zf.read(info.filename)
                except Exception as z_err:
                    logger.debug("Skipping unreadable zip member %s: %s", info.filename, z_err)
                    continue
                stem = info.filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                try:
                    for sub_name, rows in load_sheets(member_bytes, _depth=_depth + 1):
                        tab_label = stem if sub_name in ("csv", "Sheet1", "Sheet 1", "Portfolio") else f"{stem}::{sub_name}"
                        yield tab_label, rows
                except Exception as sub_err:
                    logger.debug("Skipping non-portfolio zip member %s: %s", info.filename, sub_err)
        return

    if fmt == "xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            for name in wb.sheetnames:
                ws = wb[name]
                yield name, [list(r) for r in ws.iter_rows(values_only=True)]
        finally:
            try:
                wb.close()
            except Exception as close_err:
                logger.debug("Workbook close notice: %s", close_err)
        return

    if fmt == "xls":
        import xlrd

        wb = xlrd.open_workbook(file_contents=data)
        for sh in wb.sheets():
            yield sh.name, (sh.row_values(i) for i in range(sh.nrows))
        return

    text = data.decode("utf-8", errors="ignore")
    yield "csv", (row for row in csv.reader(io.StringIO(text)))


# --------------------------------------------------------------------------- #
# Cell & scheme-name helpers
# --------------------------------------------------------------------------- #
def _clean(v: Any) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v).replace("\xa0", " ")).strip()


def _to_float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = _clean(v).replace(",", "").replace("%", "").replace("$", "").replace("₹", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1].strip()
    if s in ("", "-", "--", "NIL", "Nil", "nil", "NA", "N.A.", "N/A", "*", "**", "#"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_formerly_aliases(text: str) -> List[str]:
    """Extracts legacy scheme names from '(Formerly known as ...)' or '(Erstwhile ...)' clauses."""
    aliases: List[str] = []
    for m in _FORMERLY_RE.finditer(text or ""):
        raw = _clean(m.group(1)).strip(" -–:()")
        if len(raw) >= 5:
            aliases.append(raw)
    return aliases


def _strip_parenthetical(name: str) -> str:
    s = _clean(name)
    # Iteratively remove balanced (...) blocks so trailing tokens after "(Formerly ...)" survive
    prev = None
    while prev != s and "(" in s:
        prev = s
        s = re.sub(r"\([^()]*\)", " ", s)
    s = re.sub(r"\(.*", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" -–:")


def _strip_plan_suffixes(name: str) -> str:
    n = _strip_parenthetical(_clean(name)).lower()
    n = re.sub(r"^scheme\s*:\s*", "", n)
    n = re.sub(r"^[a-z]{2,5}\d{1,4}\s*[-–:]\s*", "", n)
    n = n.replace("&", " and ").replace("’", "'").replace("–", "-").replace("—", "-")
    n = re.sub(r"\s+-\s+(?:direct|regular)\b.*$", "", n)
    n = re.sub(
        r"\b(?:direct|regular|plan|growth|option|options|idcw|payout|reinvestment|monthly\s+portfolio|portfolio\s+statement|as\s+on\b.*)$",
        " ",
        n,
    )
    for pat, repl in _QUALIFIER_CANON_SUBS:
        n = re.sub(pat, repl, n)
    n = re.sub(r"\b(?:the|mutual|fund|scheme|india)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def normalize_scheme_name(name: str) -> str:
    """Canonical key for matching AMFI scheme names to workbook sheet titles."""
    n = _strip_parenthetical(_clean(name)).lower()
    n = re.sub(r"^scheme\s*:\s*", "", n)
    n = re.sub(r"^[a-z]{2,5}\d{1,4}\s*[-–:]\s*", "", n)
    n = re.sub(r"\s+as\s+(?:on|at)\s+.*$", "", n)
    n = re.sub(
        r"(?:^|\s*[-–:]\s*)(?:monthly\s+)?portfolio(?:\s+(?:statement|disclosure|report))?\b.*$",
        "",
        n,
    )
    n = re.split(r"\s+[-–]\s+(?:direct|regular)\b", n)[0]
    n = re.sub(r"\b(?:direct|regular)\s+plan\b.*$", "", n)
    n = re.sub(r"\bgrowth\s+option\b.*$", "", n)
    n = n.replace("&", " and ").replace("’", "'")
    for pat, repl in _QUALIFIER_CANON_SUBS:
        n = re.sub(pat, repl, n)
    n = re.sub(r"\b(the|mutual|fund|scheme)\b", " ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


def _tokens_compatible(target: str, candidate: str) -> bool:
    """Enforces exact numeric-tuple and strategy-qualifier parity to prevent L3 collisions
    (e.g. Nifty 50 vs Nifty 500, Midcap 150 vs Midcap 50, Large Cap vs Large & Mid Cap,
    Short Duration vs Ultra Short Duration)."""
    t_clean = _strip_plan_suffixes(target)
    c_clean = _strip_plan_suffixes(candidate)
    if not t_clean or not c_clean:
        return False

    t_nums = tuple(re.findall(r"\d+", t_clean))
    c_nums = tuple(re.findall(r"\d+", c_clean))
    if t_nums != c_nums:
        return False

    t_words = set(re.findall(r"[a-z]+", t_clean))
    c_words = set(re.findall(r"[a-z]+", c_clean))

    t_quals = t_words & _CRITICAL_QUALIFIER_TOKENS
    c_quals = c_words & _CRITICAL_QUALIFIER_TOKENS
    if t_quals != c_quals:
        return False

    return True


def match_scheme_name(target: str, candidates: List[str], cutoff: float = 0.91) -> Optional[str]:
    """Returns the single best collision-checked candidate for target, or None (never guesses on ties)."""
    key = normalize_scheme_name(target)
    if not key:
        return None
    exact = [c for c in candidates if normalize_scheme_name(c) == key]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    compatible_scored: List[Tuple[float, str]] = []
    for c in candidates:
        c_key = normalize_scheme_name(c)
        if not c_key:
            continue
        if not _tokens_compatible(target, c):
            continue
        ratio = difflib.SequenceMatcher(None, key, c_key).ratio()
        compatible_scored.append((ratio, c))

    compatible_scored.sort(reverse=True)
    if not compatible_scored or compatible_scored[0][0] < cutoff:
        return None
    if len(compatible_scored) > 1 and (compatible_scored[0][0] - compatible_scored[1][0]) < 0.02:
        return None
    return compatible_scored[0][1]


def match_schemes_to_workbook_sheets(
    schemes: List[Dict[str, Any]],
    sheets: Dict[str, Dict[str, Any]],
    cutoff: float = 0.90,
) -> Dict[str, str]:
    """2-pass bipartite matcher mapping `scheme_code -> sheet_key` without sheet double-claiming.

    Pass 1 claims exact normalized matches across `scheme_name`, `index_title`, `aliases`, and sheet tab names.
    Pass 2 claims unambiguous `_tokens_compatible` fuzzy matches across remaining unclaimed sheets.
    """
    sheet_candidates: Dict[str, List[str]] = {}
    norm_to_sheets: Dict[str, List[str]] = {}
    for skey, parsed in sheets.items():
        labels: List[str] = []
        for raw_lbl in [
            parsed.get("scheme_name") or "",
            parsed.get("index_title") or "",
            *(parsed.get("aliases") or []),
            skey.split("::")[-1],
            skey.split("::")[0],
        ]:
            cleaned = _clean(raw_lbl)
            if cleaned and cleaned not in labels:
                labels.append(cleaned)
        sheet_candidates[skey] = labels
        seen_norms_for_sheet = set()
        for lbl in labels:
            nk = normalize_scheme_name(lbl)
            if nk and nk not in seen_norms_for_sheet:
                seen_norms_for_sheet.add(nk)
                norm_to_sheets.setdefault(nk, []).append(skey)

    claimed_sheets: Set[str] = set()
    matched: Dict[str, str] = {}

    # Pass 1: Exact normalized match (highest-AUM schemes first as passed in)
    for row in schemes:
        scode = str(row.get("scheme_code") or "").strip()
        sname = str(row.get("scheme_name") or "")
        nk = normalize_scheme_name(sname)
        if not scode or not nk:
            continue
        exact_hits = [sk for sk in norm_to_sheets.get(nk, []) if sk not in claimed_sheets]
        if len(exact_hits) == 1:
            claimed_sheets.add(exact_hits[0])
            matched[scode] = exact_hits[0]

    # Pass 2: Collision-guarded fuzzy match on remaining unclaimed sheets
    for row in schemes:
        scode = str(row.get("scheme_code") or "").strip()
        if not scode or scode in matched:
            continue
        sname = str(row.get("scheme_name") or "")
        nk = normalize_scheme_name(sname)
        if not nk:
            continue

        scored_sheets: List[Tuple[float, str]] = []
        for skey, labels in sheet_candidates.items():
            if skey in claimed_sheets:
                continue
            best_for_sheet = 0.0
            for lbl in labels:
                lbl_nk = normalize_scheme_name(lbl)
                if not lbl_nk or not _tokens_compatible(sname, lbl):
                    continue
                r = difflib.SequenceMatcher(None, nk, lbl_nk).ratio()
                if r > best_for_sheet:
                    best_for_sheet = r
            if best_for_sheet >= cutoff:
                scored_sheets.append((best_for_sheet, skey))

        scored_sheets.sort(reverse=True)
        if not scored_sheets:
            continue
        if len(scored_sheets) > 1 and (scored_sheets[0][0] - scored_sheets[1][0]) < 0.02:
            continue
        chosen = scored_sheets[0][1]
        claimed_sheets.add(chosen)
        matched[scode] = chosen

    return matched


# --------------------------------------------------------------------------- #
# Column + section detection + Index-tab shortcode extraction
# --------------------------------------------------------------------------- #
def _detect_columns(row: List[Any]) -> Optional[Dict[str, int]]:
    cols: Dict[str, int] = {}
    for i, cell in enumerate(row):
        t = _clean(cell).lower()
        if not t:
            continue
        if t == "isin" or t.startswith("isin"):
            cols.setdefault("isin", i)
        elif (
            "name of the instrument" in t
            or "name of instrument" in t
            or "scheme & instrument" in t
            or "instrument name" in t
            or "company/issuer" in t
            or "company / issuer" in t
            or t in ("instrument", "security name", "security", "issuer", "particulars", "company name")
        ):
            cols.setdefault("name", i)
        elif "industry" in t or "rating" in t or "sector" in t:
            cols.setdefault("sector", i)
        elif t.startswith("quantity") or t.startswith("qty") or "no. of shares" in t:
            cols.setdefault("qty", i)
        elif (
            ("market" in t and "value" in t)
            or ("fair" in t and "value" in t)
            or t.startswith("market/fair")
            or "exposure/market" in t
        ):
            cols.setdefault("value", i)
        elif (
            ("% to" in t and ("nav" in t or "net" in t or "aum" in t))
            or "% of net" in t
            or "% of nav" in t
            or "% to net" in t
            or "%age to nav" in t
            or "percentage to net" in t
            or "rounded % to net" in t
        ):
            cols.setdefault("weight", i)
        elif t.startswith("yield") or t.startswith("ytm") or "ytc" in t:
            cols.setdefault("yield", i)
    if "isin" in cols and "weight" in cols:
        cols.setdefault("name", cols["isin"] + 1)
        return cols
    return None


def _parse_index_shortcode_sheet(rows: Iterable[List[Any]]) -> Dict[str, str]:
    """Extracts `{short_code: full_scheme_name}` from AMC Index / Contents / Summary sheets."""
    mapping: Dict[str, str] = {}
    for row in rows:
        cells = [_clean(c) for c in row if _clean(c)]
        if len(cells) < 2:
            continue
        # Ignore serial numbers in col 0 if 3+ columns exist (e.g. [1, 'SBLUECHIP', 'SBI BlueChip Fund'])
        if len(cells) >= 3 and cells[0].isdigit() and len(cells[1]) <= 31:
            code_cand, name_cand = cells[1], cells[2]
        else:
            code_cand, name_cand = cells[0], cells[1]
        if (
            1 <= len(code_cand) <= 31
            and len(name_cand) >= 10
            and not ISIN_RE.match(code_cand.upper())
            and code_cand.lower() not in ("sr. no", "sr no", "s.no", "sno", "short code", "scheme code", "index")
            and ("fund" in name_cand.lower() or "plan" in name_cand.lower() or "scheme" in name_cand.lower() or "etf" in name_cand.lower())
        ):
            mapping[code_cand] = name_cand
    return mapping


def classify_section(text: str) -> Optional[str]:
    """Maps a section-title row to a holding type. None means 'not a recognised section'."""
    t = text.lower()
    if any(
        k in t
        for k in (
            "triparty",
            "tri-party",
            "treps",
            "reverse repo",
            "repo",
            "cblo",
            "cash",
            "net current",
            "net receivable",
            "receivables",
            "payables",
            "margin",
            "clearing corporation",
            "ccil",
            "bank balance",
        )
    ):
        return "CASH_EQUIVALENT"
    if any(k in t for k in ("foreign", "overseas", "adr", "gdr")):
        return "FOREIGN_EQUITY"
    if "equity" in t and "related" in t:
        return "EQUITY"
    if t.startswith("equity") or ("listed / awaiting listing on stock" in t and "debt" not in t and "equity" in t):
        return "EQUITY"
    if any(k in t for k in ("mutual fund unit", "exchange traded fund", "etf", "reit", "invit", "units of", "alternative investment")):
        return "OTHER"
    if any(k in t for k in ("future", "option", "derivative", "index / stock")):
        return "DERIVATIVES"
    if any(
        k in t
        for k in (
            "government securit",
            "central government",
            "state government",
            "g-sec",
            "treasury bill",
            "t-bill",
            "state development",
            "debt",
            "debenture",
            "bond",
            "certificate of deposit",
            "commercial paper",
            "money market",
            "securitised",
            "securitized",
            "zero coupon",
            "pass through",
            "ncd",
            "floating rate",
            "fixed deposit",
        )
    ):
        return "DEBT"
    return None


def _holding_type_from_isin(isin: str, section: Optional[str]) -> str:
    if section in ("EQUITY", "FOREIGN_EQUITY", "DEBT", "OTHER", "DERIVATIVES"):
        base = section
    elif isin.startswith("INF"):
        base = "OTHER"
    elif isin.startswith("INE") and isin[8:10] == "01":
        base = "EQUITY"
    elif isin.startswith("IN"):
        base = "DEBT"
    else:
        base = "FOREIGN_EQUITY"
    if base == "EQUITY" and not isin.startswith("IN"):
        return "FOREIGN_EQUITY"
    return base


def _disclosure_dates(text: str) -> List[str]:
    text = re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b", r"\1", _clean(text), flags=re.IGNORECASE)
    results: List[str] = []
    patterns = (
        (r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", (1, 2, 3)),
        (r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*,?\s*(\d{4})(?!\d)", (3, 1, 2)),
        (r"(?<!\d)(\d{1,2})[-\s/_]([A-Za-z]{3,9})[-\s/_,]*(\d{2,4})(?!\d)", (3, 2, 1)),
        (r"(?<![\d-])(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)", (3, 2, 1)),
    )
    for pattern, (year_group, month_group, day_group) in patterns:
        for match in re.finditer(pattern, text):
            month_raw = match.group(month_group).lower()
            if month_raw.isdigit():
                month: Optional[int] = int(month_raw)
            else:
                month = next((number for name, number in _MONTHS.items() if name[:3] == month_raw[:3]), None)
            if month is None:
                continue
            year = int(match.group(year_group))
            if year < 100:
                year += 2000
            try:
                results.append(date(year, month, int(match.group(day_group))).isoformat())
            except ValueError as dt_err:
                logger.debug("Invalid disclosure date candidate in %r: %s", text, dt_err)
                continue
    return results


def parse_as_on_date(text: str) -> Optional[str]:
    """Return the first date candidate for legacy source discovery."""
    dates = _disclosure_dates(text)
    return dates[0] if dates else None


def _pick_scheme_title_candidate(candidates: List[str]) -> str:
    """Selects the most specific scheme title from pre-header banner lines (skipping AMC-only banners)."""
    non_banner = [c for c in candidates if not _BANNER_SKIP_PATTERNS.match(c)]
    for line in non_banner:
        low = line.lower()
        if any(k in low for k in ("fund", "scheme", "plan", "etf", "fmp", "series")) and "mutual fund" not in low:
            return line
    if non_banner:
        return non_banner[0]
    return candidates[0] if candidates else ""


# --------------------------------------------------------------------------- #
# Sheet parsing
# --------------------------------------------------------------------------- #
def parse_scheme_sheet(rows: Iterable[List[Any]]) -> Optional[Dict[str, Any]]:
    """Parses one scheme sheet. Returns None if the sheet is not a portfolio statement."""
    title_candidates: List[str] = []
    aliases: List[str] = []
    explicit_dates: set[str] = set()
    contextual_dates: set[str] = set()
    cols: Optional[Dict[str, int]] = None
    section: Optional[str] = None
    holdings: List[Dict[str, Any]] = []
    header_seen_at = None

    for idx, row in enumerate(rows):
        texts = [_clean(c) for c in row]
        nonempty = [t for t in texts if t]
        if not nonempty:
            continue

        if cols is None:
            joined = " ".join(nonempty)
            marker = re.search(r"\bas\s+(?:on|at|of)\b", joined, re.IGNORECASE)
            if marker:
                explicit_dates.update(_disclosure_dates(joined[marker.end():]))
            elif re.search(r"\b(?:portfolio|statement)\b", joined, re.IGNORECASE):
                contextual_dates.update(_disclosure_dates(joined))
            detected = _detect_columns(list(row))
            if detected:
                cols = detected
                header_seen_at = idx
                continue
            if idx < 10:
                for cell_txt in nonempty:
                    if len(cell_txt) > 8 and not ISIN_RE.match(cell_txt.upper()):
                        for al in extract_formerly_aliases(cell_txt):
                            if al not in aliases:
                                aliases.append(al)
                        # Strip inline "Monthly Portfolio Statement of <Scheme> as on ..." or "<Scheme> - Monthly Portfolio as on ..." wrappers
                        unwrapped = re.sub(r"(?i)^scheme\s*:\s*", "", cell_txt)
                        unwrapped = re.sub(r"(?i)^scheme\s+code\w*starts$", "", unwrapped)
                        unwrapped = re.sub(
                            r"(?i)^(?:monthly\s+)?portfolio(?:\s+(?:statement|disclosure|report))?\s+(?:of\s+)?",
                            "",
                            unwrapped,
                        )
                        unwrapped = re.sub(r"(?i)\s+as\s+(?:on|at|of)\s+.*$", "", unwrapped).strip(" -–:.")
                        unwrapped = re.sub(
                            r"(?i)\s*[-–:]\s*(?:monthly\s+)?portfolio(?:\s+(?:statement|disclosure|report))?$",
                            "",
                            unwrapped,
                        ).strip(" -–:.")
                        if len(unwrapped) > 6 and unwrapped not in title_candidates:
                            title_candidates.append(unwrapped)
            continue

        if len(nonempty) == 1:
            title = nonempty[0]
            low = title.lower()
            if any(low.startswith(s) for s in _STOP_MARKERS):
                break
            sec = classify_section(title)
            if sec:
                section = sec
            continue

        # Also check if col 0/1 carries a section header while trailing cells are blank/zero
        isin_cell = _clean(row[cols["isin"]]) if cols["isin"] < len(row) else ""
        weight = _to_float(row[cols["weight"]]) if cols["weight"] < len(row) else None
        name_cell = _clean(row[cols["name"]]) if cols["name"] < len(row) else ""

        if not ISIN_RE.match(isin_cell.upper()) and weight is None:
            joined_row = " ".join(nonempty)
            if any(joined_row.lower().startswith(s) for s in _STOP_MARKERS):
                break
            sec = classify_section(name_cell or joined_row)
            if sec:
                section = sec
                continue

        if ISIN_RE.match(isin_cell.upper()) and weight is not None:
            isin = isin_cell.upper()
            sector = _clean(row[cols["sector"]]) if "sector" in cols and cols["sector"] < len(row) else ""
            htype = _holding_type_from_isin(isin, section)
            details: Dict[str, Any] = {}
            if "yield" in cols and cols["yield"] < len(row):
                y = _to_float(row[cols["yield"]])
                if y is not None:
                    details["ytm_raw"] = y
            if "qty" in cols and cols["qty"] < len(row):
                q = _to_float(row[cols["qty"]])
                if q is not None:
                    details["quantity"] = q
            if "value" in cols and cols["value"] < len(row):
                v = _to_float(row[cols["value"]])
                if v is not None:
                    details["market_value_lakhs"] = v
            clean_hname = re.sub(r"^(?:EQ|DB|MM|GS)\s*[-–:]\s*", "", name_cell, flags=re.IGNORECASE)
            holdings.append({
                "isin": isin,
                "holding_name": re.sub(r"[\*\#\^\$]+$", "", clean_hname).strip(),
                "holding_type": htype,
                "sector_or_rating": sector,
                "weight_raw": weight,
                "instrument_details": details,
            })
            continue

        # Non-ISIN lines: TREPS / repo / CBLO / net current assets / receivables cash rows
        label = name_cell or next((t for t in texts if t and _to_float(t) is None), "")
        if not label or any(label.lower().startswith(p) for p in _TOTAL_PREFIXES):
            continue
        if weight is None:
            continue
        if section == "CASH_EQUIVALENT" or classify_section(label) == "CASH_EQUIVALENT":
            holdings.append({
                "isin": "",
                "holding_name": label,
                "holding_type": "CASH_EQUIVALENT",
                "sector_or_rating": "CASH",
                "weight_raw": weight,
                "instrument_details": {},
            })

    if cols is None or not holdings:
        return None

    scheme_title = _pick_scheme_title_candidate(title_candidates)
    dates = explicit_dates or contextual_dates
    return {
        "scheme_title": scheme_title,
        "scheme_name": _strip_parenthetical(scheme_title),
        "aliases": aliases,
        "as_on_date": next(iter(dates)) if len(dates) == 1 else None,
        "holdings": holdings,
        "header_row": header_seen_at,
    }


def normalize_weights(holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Converts weight_raw into weight_pct. Handles fraction (0.0293) vs percent (2.93) files.

    Short futures in arbitrage funds are negative and are dropped: the engine treats weights as
    non-negative exposures, and the hedged equity leg is already captured as a long position.
    """
    positives = [h for h in holdings if h["weight_raw"] > 0]
    if not positives:
        return []
    # Ignore non-derivative short futures when checking scale (0.01 vs 1.00)
    non_deriv = [h for h in positives if h.get("holding_type") != "DERIVATIVES"]
    ref = non_deriv if non_deriv else positives
    total = sum(h["weight_raw"] for h in ref)
    scale = 100.0 if 0.3 <= total <= 1.6 else 1.0
    out = []
    for h in positives:
        if h.get("holding_type") == "DERIVATIVES":
            # Equity/Index futures duplicate underlying hedged cash/equity notional in arbitrage funds
            continue
        item = dict(h)
        item["weight_pct"] = round(h["weight_raw"] * scale, 4)
        if "ytm_raw" in item["instrument_details"]:
            y = item["instrument_details"].pop("ytm_raw")
            item["instrument_details"]["ytm"] = round(y * 100.0 if 0 < y < 0.5 else y, 4)
        out.append(item)
    return out


def _split_stacked_scheme_blocks(name: str, row_list: List[List[Any]]) -> List[Tuple[str, List[List[Any]]]]:
    """Splits single-sheet stacked multi-scheme disclosures (e.g. UTI 'SCHEME CODE002STARTS' blocks) into per-scheme slices."""
    starts: List[Tuple[int, str]] = []
    for idx, r in enumerate(row_list):
        if not r:
            continue
        c0 = _clean(r[0])
        m = re.match(r"(?i)^scheme\s*code\s*([a-z0-9]+)\s*starts$", c0)
        if m:
            starts.append((idx, m.group(1)))
    if len(starts) < 2:
        return [(name, row_list)]
    slices: List[Tuple[str, List[List[Any]]]] = []
    for pos, (start_idx, code_lbl) in enumerate(starts):
        end_idx = starts[pos + 1][0] if (pos + 1) < len(starts) else len(row_list)
        slices.append((f"{name}::UTI_{code_lbl}", row_list[start_idx:end_idx]))
    return slices


def parse_workbook(data: bytes) -> Dict[str, Dict[str, Any]]:
    """Parses every scheme sheet in a workbook or zip archive. Returns `{sheet_name: parsed_sheet}`."""
    results: Dict[str, Dict[str, Any]] = {}
    shortcode_map: Dict[str, str] = {}

    for raw_sheet_name, rows in load_sheets(data):
        full_row_list = list(rows)
        tab_only = raw_sheet_name.split("::")[-1].strip().lower()
        if tab_only in ("index", "contents", "summary", "scheme index", "cover", "list of schemes"):
            try:
                shortcode_map.update(_parse_index_shortcode_sheet(full_row_list))
            except Exception as idx_err:
                logger.debug("Index sheet parse notice on '%s': %s", raw_sheet_name, idx_err)
            continue

        for name, row_list in _split_stacked_scheme_blocks(raw_sheet_name, full_row_list):
            try:
                parsed = parse_scheme_sheet(row_list)
            except Exception as e:
                logger.warning("Skipping unparseable sheet '%s': %s", name, e)
                continue
            if parsed:
                parsed["holdings"] = normalize_weights(parsed["holdings"])
                if parsed["holdings"]:
                    raw_tab = name.split("::")[-1].strip()
                    if raw_tab in shortcode_map:
                        idx_title = shortcode_map[raw_tab]
                        parsed["index_title"] = _strip_parenthetical(idx_title)
                        for al in extract_formerly_aliases(idx_title):
                            if al not in parsed["aliases"]:
                                parsed["aliases"].append(al)
                        if not parsed["scheme_name"] or len(parsed["scheme_name"]) < 6:
                            parsed["scheme_name"] = parsed["index_title"]
                    results[name] = parsed

    # Second pass in case an Index sheet appeared at the end of the workbook
    if shortcode_map:
        for name, parsed in results.items():
            raw_tab = name.split("::")[-1].strip()
            if raw_tab in shortcode_map and not parsed.get("index_title"):
                idx_title = shortcode_map[raw_tab]
                parsed["index_title"] = _strip_parenthetical(idx_title)
                for al in extract_formerly_aliases(idx_title):
                    if al not in parsed["aliases"]:
                        parsed["aliases"].append(al)
                if not parsed["scheme_name"] or len(parsed["scheme_name"]) < 6:
                    parsed["scheme_name"] = parsed["index_title"]

    return results
