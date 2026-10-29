"""
Watermarked Deterministic Financial Model Exporter
==================================================
Exports multi-tab institutional workbooks (Valuation Sensitivity, 360° Accounting Sieve,
and Sector KPIs) stamped with opaque account provenance under Terms §5.
"""

import csv
import io
import re
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from core.db.connection import IST
from web.legal_content import MANDATORY_SEBI_DISCLAIMER

_SIGNED_NUMERIC_RE = re.compile(r"^[\+\-]?\d+(?:\.\d+)?%?$")


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").replace("%", "").replace("₹", "").strip()
    if not s or s.upper() in ("N/A", "NM", "NONE", "-", "—"):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _sanitize_cell(val: Any) -> Any:
    """Prevents spreadsheet formula injection (=, @, non-numeric +/-) while preserving numeric types."""
    if val is None or isinstance(val, (int, float)):
        return val
    s = str(val)
    if not s:
        return s
    if s[0] in ("=", "@", "\t", "\r") or (s[0] in ("+", "-") and not _SIGNED_NUMERIC_RE.match(s.strip())):
        return f"'{s}"
    return s


def _compile_model_sections(
    ticker: str,
    fundamentals: Optional[Dict[str, Any]],
    equity_intel: Optional[Dict[str, Any]],
    account_ref: str = "",
) -> Dict[str, List[List[Any]]]:
    fund = fundamentals or {}
    intel = equity_intel or {}
    clean_sym = (ticker or "").strip().upper()
    ts = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    provenance = _sanitize_cell((account_ref or "").strip() or "PRO_DESK")

    vr = intel.get("valuation_radar") or {}
    fi = intel.get("forensic_intelligence") or {}
    si = intel.get("sector_intelligence") or {}
    inputs = vr.get("inputs") or {}

    header_rows: List[List[Any]] = [
        ["MOATNOMICS QUANTITATIVE RESEARCH MODEL", clean_sym],
        ["Generated (IST)", ts, "Account Provenance Ref", provenance],
        ["Compliance Notice", MANDATORY_SEBI_DISCLAIMER],
    ]

    sec_pe = (si.get("benchmarks") or {}).get("pe_median", "N/A")
    disc_pct = _safe_float(inputs.get("discount_rate_pct"), 11.0)
    baseline_rows: List[List[Any]] = [
        ["Metric", "Value", "Notes / Benchmark"],
        ["Current Market Price (INR)", vr.get("current_price"), "BSE/NSE Feed"],
        ["Trailing P/E", _sanitize_cell(fund.get("pe_ratio")), f"Sector Median: {sec_pe}x"],
        ["Triangulated Fair Value (INR)", vr.get("fair_value") or "Implied-Growth Regime", vr.get("regime", "")],
        ["Margin of Safety / Spread (%)", vr.get("margin_of_safety_pct"), "40% DCF / 35% Median PE / 25% EPV"],
        ["Market-Implied 5Y FCF CAGR (%)", inputs.get("implied_fcf_growth_pct"), f"Solved at {disc_pct}% WACC"],
    ]

    is_implied_only = vr.get("status") == "IMPLIED_GROWTH_ONLY"
    eps = 0.0 if is_implied_only else _safe_float(inputs.get("normalized_eps"), 0.0)
    tg = _safe_float(inputs.get("terminal_growth_pct"), 4.5) / 100.0
    growth_grid = [0.06, 0.09, 0.12, 0.15, 0.18]
    wacc_grid = [0.095, 0.105, 0.11, 0.12, 0.13]

    sensitivity_rows: List[List[Any]] = [
        ["WACC \\ 5Y Growth"] + [f"{int(g * 100)}%" for g in growth_grid]
    ]
    for w in wacc_grid:
        row: List[Any] = [f"{w * 100:.1f}%"]
        for g in growth_grid:
            if eps <= 0:
                row.append("N/A")
                continue
            pv, proj = 0.0, eps
            for yr in range(1, 6):
                proj *= (1.0 + g)
                pv += proj / ((1.0 + w) ** yr)
            tv = (proj * (1.0 + tg)) / max(0.02, w - tg)
            row.append(round(pv + tv / ((1.0 + w) ** 5), 2))
        sensitivity_rows.append(row)

    kpi_rows: List[List[Any]] = [
        ["KPI", "Reported Value", "Sector Benchmark", "Status"],
    ]
    for k in si.get("kpis") or []:
        kpi_rows.append([
            _sanitize_cell(k.get("name")),
            _sanitize_cell(k.get("val")),
            _sanitize_cell(k.get("benchmark")),
            _sanitize_cell(k.get("status")),
        ])

    forensic_rows: List[List[Any]] = [
        ["Verdict", _sanitize_cell(fi.get("verdict")), "Summary", _sanitize_cell(fi.get("summary"))],
    ]
    for fc in fi.get("failed_checks") or []:
        forensic_rows.append([
            "Flagged Check",
            _sanitize_cell(fc.get("name")),
            _sanitize_cell(fc.get("severity")),
            _sanitize_cell(fc.get("msg")),
        ])

    return {
        "header": header_rows,
        "baseline": baseline_rows,
        "sensitivity": sensitivity_rows,
        "sector_name": [[si.get("sector_display_name", "")]],
        "kpis": kpi_rows,
        "forensic_badge": [[fi.get("badge_label", "")]],
        "forensics": forensic_rows,
    }


def build_equity_model_csv_bundle(
    ticker: str,
    fundamentals: Dict[str, Any],
    equity_intel: Dict[str, Any],
    account_ref: str = "",
) -> bytes:
    """Builds a clean UTF-8 BOM CSV/Workbook export compatible with Excel, Numbers, and Google Sheets."""
    sections = _compile_model_sections(ticker, fundamentals, equity_intel, account_ref=account_ref)

    buf = io.StringIO()
    buf.write("\ufeff")  # UTF-8 BOM for direct Microsoft Excel opening
    writer = csv.writer(buf)

    for r in sections["header"]:
        writer.writerow(r)
    writer.writerow([])

    writer.writerow(["SECTION 1: FUNDAMENTAL & VALUATION BASELINE"])
    for r in sections["baseline"]:
        writer.writerow(r)
    writer.writerow([])

    writer.writerow(["SECTION 2: WACC vs. STAGE-1 GROWTH DCF SENSITIVITY MATRIX (INR / SHARE)"])
    for r in sections["sensitivity"]:
        writer.writerow(r)
    writer.writerow([])

    writer.writerow(["SECTION 3: SECTOR BENCHMARK KPIS", sections["sector_name"][0][0]])
    for r in sections["kpis"]:
        writer.writerow(r)
    writer.writerow([])

    writer.writerow(["SECTION 4: 360 ACCOUNTING CHECK SUMMARY", sections["forensic_badge"][0][0]])
    for r in sections["forensics"]:
        writer.writerow(r)

    return buf.getvalue().encode("utf-8")


def _col_letter(idx_zero_based: int) -> str:
    n = idx_zero_based + 1
    letters = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters))


def _sheet_xml(rows: List[List[Any]]) -> str:
    xml_rows = []
    for r_idx, row in enumerate(rows, start=1):
        cells = []
        for c_idx, val in enumerate(row):
            if val is None or val == "":
                continue
            ref = f"{_col_letter(c_idx)}{r_idx}"
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                cells.append(f'<c r="{ref}"><v>{val}</v></c>')
            else:
                safe_txt = escape(str(val))
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{safe_txt}</t></is></c>')
        xml_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        "</worksheet>"
    )


def build_equity_model_xlsx_workbook(
    ticker: str,
    fundamentals: Dict[str, Any],
    equity_intel: Dict[str, Any],
    account_ref: str = "",
) -> bytes:
    """Builds a zero-dependency multi-tab OOXML (.xlsx) workbook stamped with account provenance."""
    sections = _compile_model_sections(ticker, fundamentals, equity_intel, account_ref=account_ref)

    tab1 = (
        sections["header"]
        + [[]]
        + [["SECTION 1: FUNDAMENTAL & VALUATION BASELINE"]]
        + sections["baseline"]
        + [[]]
        + [["SECTION 2: WACC vs. STAGE-1 GROWTH DCF SENSITIVITY MATRIX (INR / SHARE)"]]
        + sections["sensitivity"]
    )
    tab2 = (
        sections["header"]
        + [[]]
        + [["SECTOR BENCHMARK KPIS", sections["sector_name"][0][0]]]
        + sections["kpis"]
    )
    tab3 = (
        sections["header"]
        + [[]]
        + [["360 ACCOUNTING CHECK SUMMARY", sections["forensic_badge"][0][0]]]
        + sections["forensics"]
    )

    sheets = [
        ("Valuation Sensitivity", tab1),
        ("Sector KPIs", tab2),
        ("360 Accounting Sieve", tab3),
    ]

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            + "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            + "".join(
                f'<sheet name="{escape(title)}" sheetId="{i}" r:id="rId{i}"/>'
                for i, (title, _) in enumerate(sheets, start=1)
            )
            + "</sheets></workbook>",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            + "</Relationships>",
        )
        for i, (_, rows) in enumerate(sheets, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(rows))

    return mem.getvalue()

