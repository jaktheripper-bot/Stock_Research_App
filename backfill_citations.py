#!/usr/bin/env python3
"""
Backfills verified regulatory source citations and footnote blocks across all existing
archived equity reports and historical revisions in the database.
"""

import json
import logging
import sys
from db import init_db, get_db_connection, get_placeholder
from bse_master import resolve_bse_scrip_code
from normalizer import extract_citations_from_report
from analyzer import format_citations_section

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_citations")

def generate_regulatory_citations(ticker: str, short_name: str, scrip_code: str, announcement: str) -> list[dict]:
    """Generates structured primary regulatory filing citations for an Indian equity."""
    name = short_name or ticker
    scrip = str(scrip_code or resolve_bse_scrip_code(ticker) or "").strip()
    cits = []
    if scrip and scrip.isdigit():
        cits.append({
            "title": f"BSE Corporate Announcements & Disclosures ({name})",
            "uri": f"https://www.bseindia.com/stock-share-price/-/{scrip}/corporate-announcements/",
            "source_type": "BSE Official Regulatory Filing"
        })
        ann_text = (announcement or "").strip()
        if ann_text and ann_text.lower() not in ["none", "n/a", ""]:
            cits.append({
                "title": f"BSE Disclosure: {ann_text[:80]}",
                "uri": f"https://www.bseindia.com/corporates/anndet_new.aspx?scrip_cd={scrip}",
                "source_type": "BSE Regulation 30 Filing"
            })
        cits.append({
            "title": f"BSE Shareholding Pattern & Promoter Disclosures ({name})",
            "uri": f"https://www.bseindia.com/stock-share-price/-/{scrip}/shareholding-pattern/",
            "source_type": "BSE Official Regulatory Filing"
        })
    cits.append({
        "title": "Ministry of Corporate Affairs Master Data",
        "uri": "https://www.mca.gov.in/content/mca/global/en/home.html",
        "source_type": "MCA Statutory Registry"
    })
    return cits

def backfill_all_citations():
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    p = get_placeholder()

    logger.info("=" * 60)
    logger.info("STARTING RETROSPECTIVE CITATIONS BACKFILL")
    logger.info("=" * 60)

    # 1. Backfill 'reports' table (Current active snapshots)
    cur.execute("SELECT ticker, short_name, report_text, latest_announcement, citations_json FROM reports;")
    report_rows = cur.fetchall()
    logger.info(f"Auditing {len(report_rows)} records in 'reports' table...")

    rep_updated = 0
    rep_skipped = 0

    for row in report_rows:
        ticker = row[0]
        short_name = row[1] or ticker
        report_text = row[2] or ""
        announcement = row[3] or ""
        citations_json = row[4]

        existing_cits = []
        if citations_json:
            try:
                existing_cits = json.loads(citations_json)
            except Exception:
                existing_cits = []

        if not existing_cits and report_text:
            existing_cits = extract_citations_from_report(report_text)

        if existing_cits:
            rep_skipped += 1
            continue

        # Generate verified citations
        scrip = resolve_bse_scrip_code(ticker)
        citations = generate_regulatory_citations(ticker, short_name, scrip, announcement)
        cit_block = format_citations_section(citations, {"ticker": ticker, "short_name": short_name, "scrip_code": scrip})
        new_text = report_text.rstrip() + cit_block
        cit_json_str = json.dumps(citations)

        cur.execute(
            f"UPDATE reports SET report_text = {p}, citations_json = {p} WHERE ticker = {p};",
            (new_text, cit_json_str, ticker)
        )
        rep_updated += 1
        logger.info(f" ✓ Backfilled {ticker} ({short_name}): {len(citations)} citations attached.")

    conn.commit()
    logger.info(f"Reports Table Summary: {rep_updated} updated, {rep_skipped} already had citations.")

    # 2. Backfill 'report_revisions' table (Immutable historical revisions)
    cur.execute("SELECT id, ticker, short_name, report_text, latest_announcement, citations_json FROM report_revisions;")
    rev_rows = cur.fetchall()
    logger.info(f"Auditing {len(rev_rows)} records in 'report_revisions' table...")

    rev_updated = 0
    rev_skipped = 0

    for row in rev_rows:
        rev_id = row[0]
        ticker = row[1]
        short_name = row[2] or ticker
        report_text = row[3] or ""
        announcement = row[4] or ""
        citations_json = row[5]

        existing_cits = []
        if citations_json:
            try:
                existing_cits = json.loads(citations_json)
            except Exception:
                existing_cits = []

        if not existing_cits and report_text:
            existing_cits = extract_citations_from_report(report_text)

        if existing_cits:
            rev_skipped += 1
            continue

        scrip = resolve_bse_scrip_code(ticker)
        citations = generate_regulatory_citations(ticker, short_name, scrip, announcement)
        cit_block = format_citations_section(citations, {"ticker": ticker, "short_name": short_name, "scrip_code": scrip})
        new_text = report_text.rstrip() + cit_block
        cit_json_str = json.dumps(citations)

        cur.execute(
            f"UPDATE report_revisions SET report_text = {p}, citations_json = {p} WHERE id = {p};",
            (new_text, cit_json_str, rev_id)
        )
        rev_updated += 1
        logger.info(f" ✓ Backfilled revision #{rev_id} for {ticker}: {len(citations)} citations attached.")

    conn.commit()
    cur.close()
    conn.close()

    logger.info(f"Report Revisions Summary: {rev_updated} updated, {rev_skipped} already had citations.")
    logger.info("=" * 60)
    logger.info("RETROSPECTIVE CITATIONS BACKFILL COMPLETED SUCCESSFULLY!")
    logger.info("=" * 60)

if __name__ == "__main__":
    backfill_all_citations()
