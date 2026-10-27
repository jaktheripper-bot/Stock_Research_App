#!/usr/bin/env python3
"""
Remediation Script: Queue Affected Template Tickers for Genuine Synthesis.

1. Identifies dossiers in reports.db that match known static fallback boilerplate templates.
2. Resets report_text = NULL and citations_json = NULL in reports (preserving ticker, quote & metadata).
3. Deletes static boilerplate snapshot rows from report_revisions.
4. Clears in-memory caches.
5. Verifies that reports.db passes both substance-based AST and database de-duplication invariants.
"""

import sys
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db.connection import get_db_connection, init_db
from core.audit.invariants import (
    KNOWN_STATIC_REPORT_TEMPLATE_PHRASES,
    scan_no_static_report_templates,
    scan_database_report_deduplication,
)
from core.db.reports import get_report_by_ticker, get_archived_reports

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("equity_research.remediation")


def remediate_template_dossiers():
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Identify affected tickers
    cur.execute("SELECT ticker, report_text FROM reports WHERE report_text IS NOT NULL")
    rows = cur.fetchall()

    affected_tickers = set()
    for row in rows:
        ticker = row[0]
        text = row[1] or ""
        for phrase in KNOWN_STATIC_REPORT_TEMPLATE_PHRASES:
            if phrase in text:
                affected_tickers.add(ticker)
                break

    logger.info("Found %d affected tickers with static boilerplate templates.", len(affected_tickers))

    if not affected_tickers:
        logger.info("No affected tickers found. Database is already clean.")
        cur.close()
        conn.close()
        return

    # 2. Reset report_text = NULL and citations_json = NULL
    for ticker in sorted(affected_tickers):
        cur.execute(
            "UPDATE reports SET report_text = NULL, citations_json = NULL WHERE ticker = ?",
            (ticker,)
        )
        cur.execute(
            "DELETE FROM report_revisions WHERE ticker = ?",
            (ticker,)
        )

    conn.commit()
    cur.close()
    conn.close()

    # 3. Clear in-memory report caches
    try:
        get_report_by_ticker.cache_clear()
    except AttributeError:
        pass
    try:
        get_archived_reports.cache_clear()
    except AttributeError:
        pass

    logger.info("Successfully reset %d tickers to PENDING compilation queue.", len(affected_tickers))

    # 4. Verify invariants
    tpl_findings = scan_no_static_report_templates()
    if tpl_findings:
        logger.error("Static template invariant failed with %d findings!", len(tpl_findings))
        sys.exit(1)
    else:
        logger.info("✅ Substance-based AST invariant passed: 0 static templates in reports.db.")

    dedup_findings = scan_database_report_deduplication()
    if dedup_findings:
        logger.error("Database de-duplication invariant failed with %d findings!", len(dedup_findings))
        sys.exit(1)
    else:
        logger.info("✅ Database de-duplication invariant passed: 0 duplicate paragraphs across non-peer reports.")


if __name__ == "__main__":
    remediate_template_dossiers()
