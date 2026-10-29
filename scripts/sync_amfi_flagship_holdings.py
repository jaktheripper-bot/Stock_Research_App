#!/usr/bin/env python3
"""
Bridges verified constituent holdings from curated slug schemes (e.g. PPFAS_FLEXICAP_DIR)
to their exact numeric AMFI Direct-Plan Growth counterparts (e.g. 122639) when AMC + core
scheme name match, eliminating empty-holdings split brains without fabricating holdings.
"""

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ENABLE_BACKGROUND_SCHEDULERS"] = "0"

from core.db.connection import (
    get_db_connection,
    get_db_path,
    get_placeholder,
    is_postgres_connection,
)
from core.db.mutual_funds import normalize_scheme_stem


def _norm_scheme_stem(name: str) -> str:
    return normalize_scheme_stem(name)


def _sync_on_cursor(cur, ph: str, apply: bool = False, verbose: bool = True) -> int:
    cur.execute(
        """
        SELECT s.scheme_code, s.scheme_name, COUNT(h.identifier) AS raw_cnt
        FROM mutual_fund_schemes s
        LEFT JOIN mutual_fund_holdings h ON s.scheme_code = h.scheme_code
        GROUP BY s.scheme_code, s.scheme_name
        ORDER BY s.scheme_code
        """
    )
    rows = cur.fetchall()

    # Count deduplicated verified holdings per curated slug source
    cur.execute(
        """
        SELECT scheme_code, COUNT(*) FROM (
            SELECT DISTINCT scheme_code, holding_type, identifier
            FROM mutual_fund_holdings
        ) AS dedup_h
        GROUP BY scheme_code
        """
    )
    distinct_cnt_map = {str(sc): int(cnt or 0) for sc, cnt in cur.fetchall()}

    populated_by_stem = {}
    empty_numeric = []
    for code, name, _raw_cnt in rows:
        code_str = str(code or "").strip()
        stem = _norm_scheme_stem(name)
        if not stem or len(stem) < 8:
            continue
        h_cnt = distinct_cnt_map.get(code_str, 0)
        if h_cnt >= 5 and not code_str.isdigit():
            populated_by_stem.setdefault(stem, (code_str, name, h_cnt))
        elif code_str.isdigit() and h_cnt < 5:
            if not re.search(r"(?i)\b(idcw|payout|reinvestment|bonus|segregated)\b", name or ""):
                empty_numeric.append((code_str, name, stem))

    bridged = 0
    for num_code, num_name, stem in empty_numeric:
        if stem not in populated_by_stem:
            continue
        src_code, _src_name, src_cnt = populated_by_stem[stem]
        if src_code == num_code:
            continue
        if verbose:
            print(
                f"[{'APPLY' if apply else 'DRY-RUN'}] Link AMFI {num_code} ({num_name}) <- {src_code} ({src_cnt} verified holdings)"
            )
        bridged += 1
        if apply:
            # 1. Bridge deduplicated verified holdings (preserving NOT NULL portfolio_date & instrument_details)
            cur.execute(
                f"""
                INSERT INTO mutual_fund_holdings (
                    scheme_code, identifier, holding_name, holding_type,
                    weight_pct, sector_or_rating, instrument_details, portfolio_date
                )
                SELECT
                    {ph}, src.identifier, src.holding_name, src.holding_type,
                    src.weight_pct, src.sector_or_rating, COALESCE(src.instrument_details, '{{}}'), src.portfolio_date
                FROM mutual_fund_holdings src
                WHERE src.id IN (
                    SELECT MAX(id)
                    FROM mutual_fund_holdings
                    WHERE scheme_code = {ph}
                    GROUP BY holding_type, identifier
                )
                AND NOT EXISTS (
                    SELECT 1 FROM mutual_fund_holdings ex
                    WHERE ex.scheme_code = {ph}
                      AND ex.holding_type = src.holding_type
                      AND ex.identifier = src.identifier
                )
                """,
                (num_code, src_code, num_code),
            )

            # 2. Bridge curated scheme metadata (AUM, TER, Manager, Risk Capture) while keeping live AMFI NAV
            cur.execute(
                f"""
                UPDATE mutual_fund_schemes
                SET
                    aum_crores = CASE WHEN COALESCE(aum_crores, 0) <= 0 THEN (SELECT aum_crores FROM mutual_fund_schemes WHERE scheme_code = {ph}) ELSE aum_crores END,
                    ter_direct_pct = CASE WHEN ter_direct_pct IS NULL OR ABS(ter_direct_pct - 0.75) < 1e-6 THEN (SELECT ter_direct_pct FROM mutual_fund_schemes WHERE scheme_code = {ph}) ELSE ter_direct_pct END,
                    ter_regular_pct = CASE WHEN ter_regular_pct IS NULL OR ABS(ter_regular_pct - 1.50) < 1e-6 THEN (SELECT ter_regular_pct FROM mutual_fund_schemes WHERE scheme_code = {ph}) ELSE ter_regular_pct END,
                    portfolio_turnover_ratio_pct = CASE WHEN portfolio_turnover_ratio_pct IS NULL OR ABS(portfolio_turnover_ratio_pct - 25.0) < 1e-6 THEN (SELECT portfolio_turnover_ratio_pct FROM mutual_fund_schemes WHERE scheme_code = {ph}) ELSE portfolio_turnover_ratio_pct END,
                    active_share_pct = CASE WHEN active_share_pct IS NULL OR ABS(active_share_pct - 70.0) < 1e-6 OR ABS(active_share_pct - 65.0) < 1e-6 THEN (SELECT active_share_pct FROM mutual_fund_schemes WHERE scheme_code = {ph}) ELSE active_share_pct END,
                    fund_manager = CASE WHEN fund_manager IS NULL OR fund_manager IN ('', 'Senior Fund Manager') THEN (SELECT fund_manager FROM mutual_fund_schemes WHERE scheme_code = {ph}) ELSE fund_manager END,
                    metadata_json = CASE WHEN metadata_json IS NULL OR metadata_json IN ('', '{{}}') THEN (SELECT metadata_json FROM mutual_fund_schemes WHERE scheme_code = {ph}) ELSE metadata_json END,
                    last_portfolio_date = COALESCE((SELECT last_portfolio_date FROM mutual_fund_schemes WHERE scheme_code = {ph}), last_portfolio_date)
                WHERE scheme_code = {ph}
                """,
                (src_code, src_code, src_code, src_code, src_code, src_code, src_code, src_code, num_code),
            )

            # 3. Bridge genuine LLM forensic dossier if the numeric AMFI twin does not yet have one
            cur.execute(
                f"""
                INSERT INTO fund_forensic_dossiers (
                    scheme_code, dossier_text, composite_health_score, weighted_moat_score,
                    accounting_risk_index, margin_of_safety_pct, promoter_pledge_exposure_pct,
                    active_share_pct, top_risky_holdings_json, top_quality_holdings_json,
                    audited_by, last_audited_at
                )
                SELECT
                    {ph}, src.dossier_text, src.composite_health_score, src.weighted_moat_score,
                    src.accounting_risk_index, src.margin_of_safety_pct, src.promoter_pledge_exposure_pct,
                    src.active_share_pct, src.top_risky_holdings_json, src.top_quality_holdings_json,
                    src.audited_by, src.last_audited_at
                FROM fund_forensic_dossiers src
                WHERE src.scheme_code = {ph}
                  AND src.composite_health_score IS NOT NULL
                  AND COALESCE(src.dossier_text, '') NOT LIKE {ph}
                  AND NOT EXISTS (
                      SELECT 1 FROM fund_forensic_dossiers ex WHERE ex.scheme_code = {ph}
                  )
                """,
                (num_code, src_code, "%With an Active Share of%", num_code),
            )
    return bridged


def sync_exact_amfi_twins(apply: bool = False) -> int:
    ph = get_placeholder()
    with get_db_connection() as conn:
        is_pg = is_postgres_connection(conn)
        cur = conn.cursor()
        try:
            bridged = _sync_on_cursor(cur, ph, apply=apply, verbose=True)
            if apply:
                conn.commit()
        finally:
            cur.close()

        # Keep local reports.db synchronized when primary connection is PostgreSQL
        if apply and is_pg:
            sq_path = Path(get_db_path())
            if sq_path.exists():
                sq_conn = sqlite3.connect(str(sq_path))
                sq_cur = sq_conn.cursor()
                try:
                    _sync_on_cursor(sq_cur, "?", apply=True, verbose=False)
                    sq_conn.commit()
                finally:
                    sq_cur.close()
                    sq_conn.close()

    print(f"Exact AMFI twin schemes bridged: {bridged}")
    return bridged


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sync_exact_amfi_twins(apply=bool(args.apply and not args.dry_run))
