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
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db.connection import get_db_connection, get_placeholder, init_db
from core.db.reports import get_archived_reports, get_report_by_ticker
from core.ingestion.etf_ingest import derive_etf_category, derive_underlying_index

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


def run_remediation(apply_changes: bool = False) -> Dict[str, int]:
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    p = get_placeholder()

    try:
        # 1. Re-classify ETFs using fixed AMC-stripped word-boundary rules
        cur.execute("SELECT id, symbol, scheme_name, category, underlying_index FROM etf_matrix")
        etf_updates: List[Tuple[str, str, int]] = []
        for row_id, _sym, sname, old_cat, old_idx in cur.fetchall():
            new_cat = derive_etf_category(sname or "")
            new_idx = derive_underlying_index(sname or "", new_cat)
            if new_cat != old_cat or new_idx != old_idx:
                etf_updates.append((new_cat, new_idx, row_id))

        # 2. Identify cloned BENCHMARK_PROXIES portfolios shared identically across >1 distinct MF schemes
        from core.db.mutual_funds import normalize_scheme_stem

        cur.execute("SELECT scheme_code, scheme_name FROM mutual_fund_schemes")
        mf_name_map = {str(sc): str(sn or sc) for sc, sn in cur.fetchall()}
        cur.execute("SELECT DISTINCT scheme_code, holding_type, identifier, weight_pct FROM mutual_fund_holdings ORDER BY scheme_code, identifier")
        mf_vecs: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        for sc, _ht, ident, w in cur.fetchall():
            mf_vecs[str(sc)].append((str(ident), round(float(w or 0.0), 2)))

        sig_to_schemes: Dict[Tuple[Tuple[str, float], ...], List[str]] = defaultdict(list)
        for sc, vec in mf_vecs.items():
            sig_to_schemes[tuple(vec)].append(sc)
        cloned_mf_codes = sorted(
            {
                sc
                for vec, scs in sig_to_schemes.items()
                if len({normalize_scheme_stem(mf_name_map.get(c, c)) or c for c in scs}) > 1
                for sc in scs
            }
        )

        # 3. Identify static algorithmic narratives in fund_forensic_dossiers
        cur.execute(
            f"SELECT scheme_code FROM fund_forensic_dossiers WHERE dossier_text LIKE {p}",
            ("%With an Active Share of%",),
        )
        template_ffd_codes = sorted({str(r[0]) for r in cur.fetchall()})

        # 4. Identify remaining boilerplate or >35% header-vs-prose price-drift equity dossiers
        cur.execute(
            """
            SELECT r.ticker, r.report_text, r.baseline_price, c.current_price
            FROM reports r
            LEFT JOIN cached_fundamentals c ON c.ticker = r.ticker
            WHERE r.report_text IS NOT NULL
            """
        )
        bad_equities: Set[str] = set()
        for ticker, text, base_px, cached_px in cur.fetchall():
            body = text or ""
            if any(sig in body for sig in BANNED_EQUITY_PHRASES):
                bad_equities.add(str(ticker))
                continue
            ref_px = float(cached_px or base_px or 0.0)
            m_px = re.search(r"current market price of\s*₹\s*([0-9,]+(?:\.[0-9]+)?)", body, re.IGNORECASE)
            if m_px and ref_px > 0:
                prose_px = float(m_px.group(1).replace(",", ""))
                if prose_px > 0 and abs(prose_px - ref_px) / ref_px > 0.35:
                    bad_equities.add(str(ticker))

        summary = {
            "etfs_reclassified": len(etf_updates),
            "cloned_mf_portfolios_purged": len(cloned_mf_codes),
            "template_mf_dossiers_purged": len(template_ffd_codes),
            "contaminated_equities_queued": len(bad_equities),
        }
        logger.info("Remediation scan summary (apply=%s): %s", apply_changes, summary)

        if apply_changes:
            for new_cat, new_idx, row_id in etf_updates:
                cur.execute(
                    f"UPDATE etf_matrix SET category = {p}, underlying_index = {p} WHERE id = {p}",
                    (new_cat, new_idx, row_id),
                )
            for sc in cloned_mf_codes:
                cur.execute(f"DELETE FROM mutual_fund_holdings WHERE scheme_code = {p}", (sc,))
                cur.execute(f"DELETE FROM fund_forensic_dossiers WHERE scheme_code = {p}", (sc,))
            for sc in template_ffd_codes:
                cur.execute(f"DELETE FROM fund_forensic_dossiers WHERE scheme_code = {p}", (sc,))
            for sym in sorted(bad_equities):
                cur.execute(
                    f"UPDATE reports SET report_text = NULL, citations_json = NULL WHERE ticker = {p}",
                    (sym,),
                )
                cur.execute(f"DELETE FROM report_revisions WHERE ticker = {p}", (sym,))
            conn.commit()
            get_report_by_ticker.cache_clear()
            get_archived_reports.cache_clear()
            logger.info("Database remediation committed successfully.")

        return summary
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Corpus Substance & Taxonomy Remediation")
    parser.add_argument("--apply", action="store_true", help="Commit changes (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Preview counts without mutating database")
    args = parser.parse_args()
    run_remediation(apply_changes=bool(args.apply and not args.dry_run))
