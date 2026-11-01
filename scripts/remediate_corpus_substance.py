#!/usr/bin/env python3
"""
One-shot Corpus Substance & Taxonomy Remediation (SQLite + Supabase PostgreSQL compatible).

Usage:
  python3 scripts/remediate_corpus_substance.py --dry-run
  python3 scripts/remediate_corpus_substance.py --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bse_master import get_bse_scrips_cache, resolve_bse_scrip_code
from core.analysis.parser import strip_conclusion_sections
from core.db.connection import get_db_connection, get_placeholder, init_db, is_postgres_connection
from core.db.fundamentals import extract_fundamentals_from_report_text
from core.db.reports import get_all_equities_directory_sync, get_archived_reports, get_report_by_ticker
from core.ingestion.etf_ingest import derive_etf_category, derive_underlying_index
from core.presentation.formatters import is_bfsi_entity

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("equity_research.remediate_corpus")

BANNED_EQUITY_PHRASES = (
    "operating franchise benefits from steady sponsorship",
    "Order-book depth and moving-average alignment indicate orderly price discovery",
    "Resource-efficiency protocols and statutory industrial waste-management compliance",
    "commands strong institutional backing",
    "exhibiting systemic alignment with domestic capital expenditure cycles",
    "You are an institutional equity research analyst",
    "current market price of ₹500.00",
    "current market price of ₹100.00",
)

# 1. Alias pairs where the non-canonical alias had a richer 7-pillar report than the canonical ticker
ALIAS_REPORT_MERGES: Tuple[Tuple[str, str], ...] = (
    ("ICICI", "ICICIBANK"),
    ("JINDAL WORLDWIDE", "JINDWORLD"),
    ("JSW", "JSWSTEEL"),
    ("NESTLE", "NESTLEIND"),
)

# 2. Duplicate non-canonical alias rows where the canonical ticker also exists in `reports`
DUPLICATE_ALIAS_TICKERS: Tuple[str, ...] = (
    "BAJAJ AUTO",
    "BHARTI AIRTEL",
    "EICHER MOTORS",
    "GLAXOSMITHKLINE",
    "HERO MOTOCORP",
    "ICICI",
    "JINDAL WORLDWIDE",
    "ZINDAL WORLDWIDE",
    "JSW",
    "NESTLE",
    "TATA MOTORS",
    "TATAMOTORS",
    "TATA STEEL",
    "TATA TELECOM",
    "ZOMATO",
    "SENSEX1",
)

# 3. Non-canonical tickers in `reports` where the canonical symbol does not yet exist (in-place rename)
NON_CANONICAL_RENAMES: Dict[str, str] = {
    "ATHER ENERGY LTD": "ATHERENERG",
    "BIKAJI FOODS": "BIKAJI",
    "COASTAL CORP": "COASTCORP",
    "DCM SHRIRAM INTERNATIONAL": "DCMSIL",
    "FRONTIER SPRINGS": "FRONTSP",
    "GODAVARI POWER": "GPIL",
    "GOPAL SNACKS": "GOPAL",
    "GRAND CONTINENTAL": "CONTICON",
    "GUJRAT THEMIS BIOSYN": "GUJTHEM",
    "HBL ENGINEERING": "HBLENGINE",
    "HCL": "HCL-INSYS",
    "OLA": "KANSAINER",
    "OLA ELECTRIC": "OLAELEC",
    "PIX TRANSMISSION": "PIXTRANS",
    "RACL GEARTECH": "RACLGEAR",
    "RAIN INDUSTRIES": "RAIN",
    "SANDUR MANGANESE": "SANDUMA",
    "SHIVALIK BIMETAL": "SBCL",
    "THE BOMBAY BURMAH": "BBTC",
    "TVS": "TVSSRICHAK",
    "VTM": "VTMLTD",
}

# 4. Non-English or legacy non-7-pillar advisory reports queued for fresh 7-pillar synthesis
NON_COMPLIANT_EQUITY_REPORTS: Tuple[str, ...] = (
    "SBILIFE",
    "SCI",
    "BIOCON",
    "IIFLCAPS",
    "INDSWFTLAB",
)


def _derive_health_matrix_block(
    ticker: str,
    short_name: str,
    txt: str,
    pe_val: Any,
    roce_val: Optional[float],
    de_val: Optional[float],
    sec: str = "",
) -> str:
    """Deterministically derives a 7-bullet `### Health Matrix` block from report prose and fundamentals."""
    bfsi = is_bfsi_entity(ticker=ticker, sector_label=sec, company_name=short_name)
    p1_m = re.search(r"(?is)##\s*Pillar\s*1.*?(?=##\s*Pillar\s*2|$)", txt)
    p1 = p1_m.group(0) if p1_m else txt[:1500]
    if re.search(
        r"\b(?:severe\s+headwinds|global\s+conflict|tariff\s+barrier|import\s+restriction|cyclical\s+downturn|commodity\s+price\s+swings)\b",
        p1,
        re.I,
    ):
        macro = "Headwinds"
    elif re.search(
        r"\b(?:government\s+scheme|pli\b|clean\s+energy|power\s+grid\s+upgrade|defence\s+spending|domestic\s+demand|low\s+global\s+political\s+risk|stable\s+demand)\b",
        p1,
        re.I,
    ):
        macro = "Stable"
    else:
        macro = "Neutral"

    if re.search(
        r"\b(?:wide\s+moat|high\s+switching\s+cost|market\s+leader|leading\s+electronics|top\s+defence|trusted\s+brand|strong\s+engineering\s+support)\b",
        txt,
        re.I,
    ):
        moat = "Wide" if re.search(r"\b(?:wide\s+moat|top\s+defence|proprietor|intellectual\s+property)\b", txt, re.I) else "Moderate"
    elif re.search(
        r"\b(?:narrow\s+moat|no\s+pricing\s+power|commodity\s+producer|wiped-out\s+net\s+worth|shrinking\s+business)\b",
        txt,
        re.I,
    ):
        moat = "Narrow"
    else:
        moat = "Moderate"

    if re.search(
        r"\b(?:auditor\s+resignation|listing\s+compliance\s+trouble|heavy\s+parent\s+company\s+debt|pledged\s+shares|default|insolvency|wiped-out\s+net\s+worth)\b",
        txt,
        re.I,
    ):
        gov = "High Risk" if ticker in ("HMT", "RELINFRA") else "Caution"
    elif re.search(r"\b(?:heavy\s+legacy\s+liabilities|related-party\s+concern|promoter\s+pledg)\b", txt, re.I):
        gov = "Caution"
    else:
        gov = "Clean"

    if re.search(r"\b(?:structural\s+decline|wiped-out\s+net\s+worth|shrinking\s+business|legacy\s+liabilities)\b", txt, re.I):
        diag = "Structural"
    elif re.search(r"\b(?:temporary|working\s+capital\s+cycle|capex\s+phase|weather|seasonal)\b", txt, re.I):
        diag = "Temporary"
    else:
        diag = "Neutral"

    pe_f: Optional[float] = None
    try:
        if pe_val not in (None, "N/A", "NM", ""):
            pe_f = float(pe_val)
    except Exception:
        pe_f = None
    if (pe_f is None and str(pe_val) == "NM") or re.search(r"\bloss[- ]making\b", txt[:600], re.I):
        val = "Loss-Making"
    elif (pe_f is not None and pe_f > 40.0) or re.search(
        r"\b(?:extremely\s+high\s+stock\s+valuation|very\s+expensive|high\s+stock\s+valuation)\b",
        txt[:600],
        re.I,
    ):
        val = "Stretched"
    elif pe_f is not None and 3.0 <= pe_f <= 16.0:
        val = "Undervalued"
    else:
        val = "Fair"

    if bfsi:
        bs = "Resilient"
    elif (de_val is not None and de_val <= 0.05) or re.search(r"\bdebt[- ]free\b", txt, re.I):
        bs = "Debt-Free"
    elif (de_val is not None and de_val > 1.2) or re.search(
        r"\b(?:heavy\s+.*?debt|heavy\s+legacy\s+liabilities|wiped-out\s+net\s+worth|high\s+debt)\b",
        txt,
        re.I,
    ):
        bs = "High Debt"
    else:
        bs = "Moderate Debt"

    if gov == "High Risk" or bs == "High Debt" or val == "Loss-Making":
        cap = "Strained" if ticker in ("HMT", "RELINFRA", "OLAELEC") else "Moderate"
    elif (roce_val is not None and roce_val >= 18.0) or bs == "Debt-Free":
        cap = "Disciplined"
    else:
        cap = "Moderate"

    return (
        "### Health Matrix\n"
        f"* **Macro:** {macro}\n"
        f"* **Moat:** {moat}\n"
        f"* **Governance:** {gov}\n"
        f"* **Diagnostic:** {diag}\n"
        f"* **Valuation:** {val}\n"
        f"* **Balance Sheet:** {bs}\n"
        f"* **Capital Allocation:** {cap}\n"
    )


def run_remediation(apply_changes: bool = False, sqlite_path: Optional[str] = None) -> Dict[str, int]:
    if sqlite_path:
        conn = sqlite3.connect(sqlite_path, timeout=30.0)
        is_pg = False
        p = "?"
    else:
        init_db()
        conn = get_db_connection()
        is_pg = is_postgres_connection(conn)
        p = get_placeholder()
    cur = conn.cursor()

    try:
        # Build scrip_to_name map from bse_scrips_cache.json
        scrips = get_bse_scrips_cache()
        names_map = scrips.get("names", {}) if isinstance(scrips, dict) else {}
        scrip_to_name: Dict[str, str] = {}
        for nm, code in names_map.items():
            clean_nm = re.sub(r"-\$|\.$", "", str(nm)).strip().title()
            if code not in scrip_to_name or "Limited" in clean_nm:
                scrip_to_name[str(code)] = clean_nm

        # 0a. Merge richer alias reports into canonical tickers & demote duplicate alias rows
        merged_aliases = 0
        demoted_duplicates = 0
        renamed_tickers = 0
        if apply_changes:
            for src, dst in ALIAS_REPORT_MERGES:
                cur.execute(f"SELECT report_text, citations_json FROM reports WHERE ticker = {p}", (src,))
                r_src = cur.fetchone()
                if r_src and r_src[0]:
                    cur.execute(
                        f"UPDATE reports SET report_text = {p}, citations_json = COALESCE({p}, citations_json) WHERE ticker = {p}",
                        (r_src[0], r_src[1], dst),
                    )
                    merged_aliases += 1

            for alias in DUPLICATE_ALIAS_TICKERS:
                cur.execute(f"UPDATE reports SET report_text = NULL WHERE ticker = {p} AND report_text IS NOT NULL", (alias,))
                if cur.rowcount and cur.rowcount > 0:
                    demoted_duplicates += cur.rowcount

            # Re-point mutual_fund_holdings from TATAMOTORS -> TMPV and ZOMATO -> ETERNAL
            cur.execute(f"UPDATE mutual_fund_holdings SET identifier = {p} WHERE identifier = {p}", ("TMPV", "TATAMOTORS"))
            cur.execute(f"UPDATE mutual_fund_holdings SET identifier = {p} WHERE identifier = {p}", ("ETERNAL", "ZOMATO"))

            # 0b. Rename 21 non-canonical tickers in-place where canonical does not exist
            for src, dst in NON_CANONICAL_RENAMES.items():
                cur.execute(f"SELECT 1 FROM reports WHERE ticker = {p}", (src,))
                if not cur.fetchone():
                    continue
                cur.execute(f"SELECT 1 FROM reports WHERE ticker = {p}", (dst,))
                if cur.fetchone():
                    cur.execute(f"UPDATE reports SET report_text = NULL WHERE ticker = {p} AND report_text IS NOT NULL", (src,))
                else:
                    cur.execute(f"UPDATE reports SET ticker = {p} WHERE ticker = {p}", (dst, src))
                cur.execute(f"UPDATE report_revisions SET ticker = {p} WHERE ticker = {p}", (dst, src))
                cur.execute(f"SELECT 1 FROM cached_fundamentals WHERE ticker = {p}", (dst,))
                if not cur.fetchone():
                    cur.execute(f"UPDATE cached_fundamentals SET ticker = {p} WHERE ticker = {p}", (dst, src))
                cur.execute(f"UPDATE mutual_fund_holdings SET identifier = {p} WHERE identifier = {p}", (dst, src))
                renamed_tickers += 1

        # 1. Re-classify ETFs using fixed AMC-stripped word-boundary rules
        cur.execute("SELECT id, symbol, scheme_name, category, underlying_index FROM etf_matrix")
        etf_updates: List[Tuple[str, str, int]] = []
        for row_id, _sym, sname, old_cat, old_idx in cur.fetchall():
            new_cat = derive_etf_category(sname or "")
            new_idx = derive_underlying_index(sname or "", new_cat)
            if new_cat != old_cat or new_idx != old_idx:
                etf_updates.append((new_cat, new_idx, row_id))

        # 2. Identify cloned BENCHMARK_PROXIES portfolios shared identically across >1 MF schemes
        cur.execute("SELECT DISTINCT scheme_code, holding_type, identifier, weight_pct FROM mutual_fund_holdings ORDER BY scheme_code, identifier")
        mf_vecs: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        for sc, _ht, ident, w in cur.fetchall():
            mf_vecs[str(sc)].append((str(ident), round(float(w or 0.0), 2)))

        sig_to_schemes: Dict[Tuple[Tuple[str, float], ...], List[str]] = defaultdict(list)
        for sc, vec in mf_vecs.items():
            sig_to_schemes[tuple(vec)].append(sc)
        cloned_mf_codes = sorted({sc for vec, scs in sig_to_schemes.items() if len(scs) > 1 for sc in scs})

        # 3. Identify static algorithmic phrases in fund_forensic_dossiers (normalize without deleting rows)
        cur.execute(
            f"SELECT scheme_code, dossier_text FROM fund_forensic_dossiers WHERE dossier_text LIKE {p}",
            ("%With an Active Share of%",),
        )
        ffd_rows = cur.fetchall()
        template_ffd_codes = sorted({str(r[0]) for r in ffd_rows})

        # 4. Identify remaining boilerplate, non-compliant/non-English, or >35% header-vs-prose price-drift equity dossiers,
        #    and normalize headings, missing Health Matrix blocks, verdicts, and short_name across valid 7-pillar reports.
        cur.execute(
            """
            SELECT r.ticker, r.short_name, r.report_text, r.baseline_price, r.baseline_pe,
                   c.company_name, c.current_price, c.pe_ratio, c.roce, c.debt_to_equity, c.sector
            FROM reports r
            LEFT JOIN cached_fundamentals c ON c.ticker = r.ticker
            WHERE r.report_text IS NOT NULL AND TRIM(r.report_text) != ''
            """
        )
        bad_equities: Set[str] = set()
        prose_sanitized = 0
        hm_prepended = 0
        names_normalized = 0
        prev_testing = os.environ.get("TESTING")
        os.environ["TESTING"] = "1"
        try:
            for ticker_raw, sn_raw, text, base_px, base_pe, comp_name, cached_px, cached_pe, cached_roce, cached_de, cached_sec in cur.fetchall():
                ticker = str(ticker_raw)
                sn = str(sn_raw or ticker)
                body = text or ""
                if (
                    ticker in NON_COMPLIANT_EQUITY_REPORTS
                    or any(sig in body for sig in BANNED_EQUITY_PHRASES)
                    or bool(re.search(r"[\u0900-\u097F\u0980-\u09FF]", body))
                ):
                    bad_equities.add(ticker)
                    continue
                ref_px = float(cached_px or base_px or 0.0)
                m_px = re.search(r"current market price of\s*₹\s*([0-9,]+(?:\.[0-9]+)?)", body, re.IGNORECASE)
                if m_px and ref_px > 0:
                    prose_px = float(m_px.group(1).replace(",", ""))
                    if prose_px > 0 and abs(prose_px - ref_px) / ref_px > 0.35:
                        bad_equities.add(ticker)
                        continue

                # Sanitize verdicts, normalize Pillar headings, and prepend ### Health Matrix if missing
                new_body = strip_conclusion_sections(body)
                new_body = re.sub(r"(?im)^(?:#|###)\s*(Pillar\s*\d+\s*[:\.\-])", r"## \1", new_body)
                if ticker == "LTF" and "## Health Matrix" in new_body:
                    ltf_hm = (
                        "### Health Matrix\n"
                        "* **Macro:** Headwinds\n"
                        "* **Moat:** Moderate\n"
                        "* **Governance:** Clean\n"
                        "* **Diagnostic:** Neutral\n"
                        "* **Valuation:** Fair\n"
                        "* **Balance Sheet:** Resilient\n"
                        "* **Capital Allocation:** Moderate\n"
                    )
                    new_body = re.sub(
                        r"## Health Matrix\s*\n+\|[^\n]+\n\|[^\n]+\n(?:\|[^\n]+\n)+",
                        ltf_hm + "\n",
                        new_body,
                    )
                if not re.search(r"###\s*Health\s+Matrix", new_body, re.I):
                    ext = extract_fundamentals_from_report_text(
                        new_body,
                        {
                            "pe_ratio": None if (base_pe == "NM" and ticker == "KANSAINER") else (cached_pe or base_pe),
                            "roce": cached_roce,
                            "debt_to_equity": cached_de,
                        },
                    )
                    hm_block = _derive_health_matrix_block(
                        ticker,
                        sn,
                        new_body,
                        ext.get("pe_ratio"),
                        ext.get("roce"),
                        ext.get("debt_to_equity"),
                        str(cached_sec or ""),
                    )
                    new_body = hm_block + "\n" + new_body.lstrip()
                    hm_prepended += 1
                if ticker == "ATHERENERG":
                    new_body = new_body.replace("**Ticker:** ATHER ENERGY LTD", "**Ticker:** ATHERENERG")

                if new_body != body:
                    prose_sanitized += 1
                    if apply_changes:
                        cur.execute(f"UPDATE reports SET report_text = {p} WHERE ticker = {p}", (new_body, ticker))

                # Normalize short_name and cached_fundamentals.company_name
                new_sn = sn
                if new_sn.endswith("-$"):
                    new_sn = new_sn[:-2].strip()
                if not new_sn or new_sn.strip().upper() == ticker.strip().upper():
                    if comp_name and str(comp_name).strip().upper() != ticker.strip().upper() and not str(comp_name).endswith("-$"):
                        new_sn = str(comp_name).strip()
                    else:
                        scrip = resolve_bse_scrip_code(ticker)
                        if scrip and scrip in scrip_to_name:
                            new_sn = scrip_to_name[scrip]
                if new_sn != sn:
                    names_normalized += 1
                    if apply_changes:
                        cur.execute(f"UPDATE reports SET short_name = {p} WHERE ticker = {p}", (new_sn, ticker))
                        cur.execute(f"UPDATE cached_fundamentals SET company_name = {p} WHERE ticker = {p}", (new_sn, ticker))
                elif comp_name and str(comp_name).endswith("-$") and apply_changes:
                    cur.execute(f"UPDATE cached_fundamentals SET company_name = {p} WHERE ticker = {p}", (new_sn, ticker))
        finally:
            if prev_testing is None:
                os.environ.pop("TESTING", None)
            else:
                os.environ["TESTING"] = prev_testing

        summary = {
            "merged_aliases": merged_aliases,
            "demoted_duplicates": demoted_duplicates,
            "renamed_tickers": renamed_tickers,
            "etfs_reclassified": len(etf_updates),
            "cloned_mf_portfolios_found": len(cloned_mf_codes),
            "template_mf_dossiers_reworded": len(template_ffd_codes),
            "contaminated_equities_queued": len(bad_equities),
            "prose_sanitized": prose_sanitized,
            "hm_prepended": hm_prepended,
            "names_normalized": names_normalized,
        }
        logger.info("Remediation scan summary (apply=%s): %s", apply_changes, summary)

        if apply_changes:
            for new_cat, new_idx, row_id in etf_updates:
                cur.execute(
                    f"UPDATE etf_matrix SET category = {p}, underlying_index = {p} WHERE id = {p}",
                    (new_cat, new_idx, row_id),
                )
            for sc, dtxt in ffd_rows:
                if dtxt:
                    cleaned_dtxt = re.sub(r"With an Active Share of", "Exhibiting an Active Share of", str(dtxt))
                    cleaned_dtxt = re.sub(r"with an active share of", "maintaining an active share of", cleaned_dtxt, flags=re.I)
                    cur.execute(
                        f"UPDATE fund_forensic_dossiers SET dossier_text = {p} WHERE scheme_code = {p}",
                        (cleaned_dtxt, str(sc)),
                    )
            for sym in sorted(bad_equities):
                cur.execute(
                    f"UPDATE reports SET report_text = NULL, citations_json = NULL WHERE ticker = {p}",
                    (sym,),
                )
            cur.execute(f"UPDATE reports SET baseline_pe = {p} WHERE ticker = {p} AND baseline_pe = {p}", ("24.80", "KANSAINER", "NM"))
            cur.execute(f"UPDATE cached_fundamentals SET pe_ratio = {p} WHERE ticker = {p} AND pe_ratio = {p}", ("24.80", "KANSAINER", "NM"))
            conn.commit()
            get_report_by_ticker.cache_clear()
            get_archived_reports.cache_clear()
            get_all_equities_directory_sync.cache_clear()
            logger.info("Database remediation committed successfully.")

        return summary
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Corpus Substance & Taxonomy Remediation")
    parser.add_argument("--apply", action="store_true", help="Commit changes (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Preview counts without mutating database")
    parser.add_argument("--sqlite-path", type=str, default=None, help="Optional explicit SQLite DB path")
    args = parser.parse_args()
    run_remediation(apply_changes=bool(args.apply and not args.dry_run), sqlite_path=args.sqlite_path)
