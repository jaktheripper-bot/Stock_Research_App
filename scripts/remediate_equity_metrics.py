#!/usr/bin/env python3
"""Equity Metric Validation, Backfill & Consistency Remediation CLI (Feedback #4 & #10).

Audits and remediates equity card & dossier metrics across BOTH SQLite (`reports.db`) and
Supabase PostgreSQL (`SUPABASE_DB_URL` via `core.db.connection`) using Angel One SmartAPI,
Official BSE Exchange APIs, and archived BSE statutory filing text (YFINANCE_FALLBACK=0):

1. Legacy Pre-SmartAPI Cached `debt_to_equity` Percentage Residue (`TCS: 9.83x -> 0.10x`,
   `INFY: 9.54x -> 0.10x`) and BFSI industrial D/E cleanup (`LTF`, `RECLTD`, `SBILIFE`, etc. -> `NULL` / `BFSI`).
2. Qualitative `'Fair'` & `'N/A (Loss-Making)'` leaks inside `discovery_reel.pe_ratio`,
   `cached_fundamentals.pe_ratio`, and `reports.baseline_pe` -> resolved numeric `P/E`, `'NM'`, or `'N/A'` (`'—'`).
3. Deterministic report-text quantitative backfill (`extract_fundamentals_from_report_text`)
   recovering missing Trailing `P/E`, `D/E`, `ROCE`, `ROE`, `OPM`, and `52-Week` ranges from archived dossiers.
4. Stale `reports.baseline_price` synchronization (`PAGEIND: ₹500 -> ₹33,774.65`, `SHREECEM: ₹500 -> ₹22,749.55`, etc.)
   and detection/cleanup of legacy `(price=500.0, mcap=₹2,500 Cr, pe='22.5')` batch placeholders.
5. `discovery_reel` quality hygiene: reconciles legacy hardcoded `ROCE=22.4% / D/E=0.15x` MF-induction rows
   and deactivates (`is_active = FALSE`, zero destructive DELETE) High-Risk/distressed (`GENSOL 0.47x`) or Mega-Cap (`RELIANCE`) reel entries.
6. Duplicate/non-canonical/typo ticker audit (`TATA STEEL` vs `TATASTEEL`, `TOMATO`, etc.) — strictly read-only
   unless BOTH `--purge-duplicates` AND `--confirm-delete` are explicitly passed.

Usage Examples:
  # 1. Safe read-only audit & before/after preview (DEFAULT)
  python3 scripts/remediate_equity_metrics.py --sqlite-path reports.db --dry-run

  # 2. Apply deterministic fixes + live-enrich via Angel One SmartAPI + BSE Official API (zero YFinance)
  python3 scripts/remediate_equity_metrics.py --sqlite-path reports.db --apply --live-enrich

  # 3. Apply deterministic fixes offline only (replaces remaining ₹500/22.5x placeholders with '—')
  python3 scripts/remediate_equity_metrics.py --sqlite-path reports.db --apply --clear-synthetic-placeholders
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bse_master import resolve_bse_scrip_code, resolve_canonical_symbol
from core.db.connection import get_db_connection, is_postgres_connection
from core.db.fundamentals import extract_fundamentals_from_report_text
from core.presentation.formatters import (
    is_bfsi_entity,
    normalize_de_ratio,
    normalize_pe_raw,
)
from normalizer import clean_ticker

logger = logging.getLogger("equity_research.scripts.remediate_equity_metrics")

# Known non-scrip typos or unrecognized entries for explicit reporting
KNOWN_TYPO_TICKERS = {
    "TOMATO": "Typo for ZOMATO / ETERNAL (no BSE/NSE scrip 'TOMATO')",
    "GRAND CONTINENTAL": "Unrecognized space-separated non-scrip string",
}


def _open_connection(sqlite_path: Optional[str] = None) -> Tuple[Any, bool, str]:
    """Opens either an explicit SQLite DB path or the active configured DB connection."""
    if sqlite_path:
        p = Path(sqlite_path)
        conn = sqlite3.connect(str(p), timeout=30.0)
        try:
            conn.execute("PRAGMA busy_timeout = 15000")
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception as e:
            logger.warning("PRAGMA setup notice for %s: %s", p, e)
        return conn, False, f"SQLite ({p})"
    conn = get_db_connection()
    is_pg = is_postgres_connection(conn)
    desc = "PostgreSQL (SUPABASE_DB_URL)" if is_pg else f"SQLite ({os.environ.get('DB_PATH', 'reports.db')})"
    return conn, is_pg, desc


def _ph(is_pg: bool) -> str:
    return "%s" if is_pg else "?"


def _is_synthetic_500_tuple(
    price: Any,
    mcap: Any,
    pe: Any,
    roce: Any = None,
    de: Any = None,
) -> bool:
    """Detects legacy offline batch placeholders, including partially-migrated ₹2,500 Cr (25B) rows."""
    try:
        p = float(price) if price is not None else -1.0
        m = float(mcap) if mcap is not None else -1.0
        pe_s = str(pe or "").strip()
        r = float(roce) if roce is not None else None
        d = float(de) if de is not None else None
        if abs(m - 25_000_000_000.0) >= 1.0:
            return False
        if abs(p - 500.0) < 1e-6 and pe_s in ("22.5", "22.50"):
            return True
        if r is not None and (abs(r - 22.0) < 1e-4 or abs(r - 22.4) < 1e-4):
            return True
        if pe_s in ("22.5", "22.50") and d is not None and abs(d - 0.15) < 1e-4:
            return True
        if pe_s in ("22.5", "22.50") and r is None and d is None:
            return True
        return False
    except (TypeError, ValueError):
        return False


def run_remediation(
    *,
    sqlite_path: Optional[str] = None,
    apply_changes: bool = False,
    clear_synthetic_placeholders: bool = False,
    live_enrich: bool = False,
    live_limit: int = 120,
    purge_duplicates: bool = False,
    confirm_delete: bool = False,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Executes full equity metric audit and (when apply_changes=True) non-destructive remediation."""
    conn, is_pg, target_desc = _open_connection(sqlite_path=sqlite_path)
    p = _ph(is_pg)
    cur = conn.cursor()

    summary: Dict[str, Any] = {
        "target_db": target_desc,
        "mode": "APPLY" if apply_changes else "DRY_RUN",
        "de_100x_scaled_fixes": [],
        "bfsi_de_cleared": [],
        "report_text_backfills": [],
        "baseline_price_synced": [],
        "baseline_pe_normalized": [],
        "synthetic_500_placeholders": [],
        "discovery_fair_pe_fixes": [],
        "discovery_synthetic_ratio_fixes": [],
        "discovery_deactivated_rows": [],
        "live_enriched_tickers": [],
        "duplicate_or_typo_tickers": [],
        "legacy_redirect_aliases": [],
        "purged_tickers": [],
    }

    try:
        # ------------------------------------------------------------------
        # 1. Load current snapshots from `reports` and `cached_fundamentals`
        # ------------------------------------------------------------------
        cur.execute(
            "SELECT ticker, short_name, baseline_price, baseline_pe, baseline_mcap, report_text "
            "FROM reports"
        )
        reports_rows = cur.fetchall()
        reports_map: Dict[str, Dict[str, Any]] = {}
        for r in reports_rows:
            reports_map[str(r[0])] = {
                "ticker": str(r[0]),
                "short_name": r[1] or str(r[0]),
                "baseline_price": float(r[2]) if r[2] is not None else None,
                "baseline_pe": str(r[3]) if r[3] is not None else None,
                "baseline_mcap": float(r[4]) if r[4] is not None else None,
                "report_text": r[5] or "",
            }

        cur.execute(
            "SELECT ticker, company_name, sector, industry, current_price, market_cap, "
            "pe_ratio, roce, roe, operating_margin, debt_to_equity, "
            "fifty_two_week_high, fifty_two_week_low, source "
            "FROM cached_fundamentals"
        )
        cf_rows = cur.fetchall()
        cf_map: Dict[str, Dict[str, Any]] = {}
        for r in cf_rows:
            cf_map[str(r[0])] = {
                "ticker": str(r[0]),
                "company_name": r[1] or str(r[0]),
                "sector": r[2] or "",
                "industry": r[3] or "",
                "current_price": float(r[4]) if r[4] is not None else None,
                "market_cap": float(r[5]) if r[5] is not None else None,
                "pe_ratio": str(r[6]) if r[6] is not None else None,
                "roce": float(r[7]) if r[7] is not None else None,
                "roe": float(r[8]) if r[8] is not None else None,
                "operating_margin": float(r[9]) if r[9] is not None else None,
                "debt_to_equity": float(r[10]) if r[10] is not None else None,
                "fifty_two_week_high": float(r[11]) if r[11] is not None else None,
                "fifty_two_week_low": float(r[12]) if r[12] is not None else None,
                "source": r[13] or "",
            }

        # ------------------------------------------------------------------
        # 2. Audit Duplicate / Space-Separated / Typo Tickers in `reports`
        # ------------------------------------------------------------------
        for t_raw, r_info in sorted(reports_map.items()):
            if t_raw.startswith(("TEST_", "UNIT_", "COAL_", "UNITCOAL_")) or t_raw in (
                "TESTCORP", "TESTPEER", "ZZTESTONLY", "COALESCE_TEST"
            ):
                continue
            if t_raw in KNOWN_TYPO_TICKERS:
                summary["duplicate_or_typo_tickers"].append({
                    "ticker": t_raw,
                    "canonical": None,
                    "reason": KNOWN_TYPO_TICKERS[t_raw],
                })
                continue

            cleaned = clean_ticker(t_raw)
            canon = resolve_canonical_symbol(cleaned) or cleaned.replace(" ", "")
            if " " in t_raw or (canon != t_raw and canon in reports_map):
                scrip = resolve_bse_scrip_code(t_raw)
                has_canon_in_db = canon in reports_map and canon != t_raw
                if " " in t_raw and has_canon_in_db:
                    summary["duplicate_or_typo_tickers"].append({
                        "ticker": t_raw,
                        "canonical": canon,
                        "reason": f"Space-separated duplicate of canonical dossier '{canon}'",
                    })
                elif " " in t_raw and (not scrip or scrip == "N/A"):
                    summary["duplicate_or_typo_tickers"].append({
                        "ticker": t_raw,
                        "canonical": canon,
                        "reason": "Non-canonical space-separated ticker without BSE scrip match",
                    })
                elif has_canon_in_db:
                    summary["legacy_redirect_aliases"].append({
                        "ticker": t_raw,
                        "canonical": canon,
                    })

        # ------------------------------------------------------------------
        # 3. Remediate `cached_fundamentals` & `reports` (Offline Deterministic)
        # ------------------------------------------------------------------
        all_tickers = sorted(set(reports_map.keys()) | set(cf_map.keys()))
        for ticker in all_tickers:
            if ticker.startswith(("TEST_", "UNIT_", "COAL_", "UNITCOAL_")):
                continue

            rep = reports_map.get(ticker)
            cf = cf_map.get(ticker)
            comp_name = (cf.get("company_name") if cf else None) or (rep.get("short_name") if rep else ticker) or ticker
            sec = cf.get("sector", "") if cf else ""
            ind = cf.get("industry", "") if cf else ""
            bfsi = is_bfsi_entity(ticker=ticker, sector_label=sec, industry=ind, company_name=comp_name)

            is_synth_cf = bool(
                cf and _is_synthetic_500_tuple(
                    cf.get("current_price"),
                    cf.get("market_cap"),
                    cf.get("pe_ratio"),
                    cf.get("roce"),
                    cf.get("debt_to_equity"),
                )
            )
            is_synth_rep = bool(
                rep and _is_synthetic_500_tuple(rep.get("baseline_price"), rep.get("baseline_mcap"), rep.get("baseline_pe"))
            )

            if is_synth_cf or is_synth_rep:
                # Check if cached_fundamentals ALREADY has a real non-500 price AND real non-25B mcap while reports has 500.0
                cf_px = cf.get("current_price") if cf else None
                if rep and is_synth_rep and not is_synth_cf and cf_px and abs(cf_px - 500.0) > 1e-6:
                    summary["baseline_price_synced"].append({
                        "ticker": ticker,
                        "old_price": rep["baseline_price"],
                        "new_price": cf_px,
                    })
                    if apply_changes:
                        cur.execute(
                            f"UPDATE reports SET baseline_price = {p} WHERE ticker = {p}",
                            (cf_px, ticker),
                        )
                        rep["baseline_price"] = cf_px
                else:
                    summary["synthetic_500_placeholders"].append(ticker)
                    # Clear synthetic 25B/22.5x/22.0%/0.15x ratios when applying changes
                    if apply_changes:
                        if cf and is_synth_cf:
                            keep_px = cf_px if (cf_px is not None and abs(cf_px - 500.0) > 1e-6) else None
                            cur.execute(
                                f"UPDATE cached_fundamentals SET current_price = {p}, market_cap = NULL, "
                                f"pe_ratio = {p}, roce = NULL, debt_to_equity = NULL WHERE ticker = {p}",
                                (keep_px, "N/A", ticker),
                            )
                            cf["current_price"] = keep_px
                            cf["market_cap"] = None
                            cf["pe_ratio"] = "N/A"
                            cf["roce"] = None
                            cf["debt_to_equity"] = None
                        if rep and is_synth_rep:
                            rep_px = rep.get("baseline_price")
                            keep_rep_px = rep_px if (rep_px is not None and abs(rep_px - 500.0) > 1e-6) else None
                            cur.execute(
                                f"UPDATE reports SET baseline_price = {p}, baseline_mcap = NULL, baseline_pe = {p} "
                                f"WHERE ticker = {p}",
                                (keep_rep_px, "N/A", ticker),
                            )
                            rep["baseline_price"] = keep_rep_px
                            rep["baseline_mcap"] = None
                            rep["baseline_pe"] = "N/A"

            # 3a. Fix yfinance 100x debt_to_equity scaling & BFSI distorted D/E in cached_fundamentals
            if cf and cf.get("debt_to_equity") is not None:
                old_de = cf["debt_to_equity"]
                if bfsi and (old_de > 2.5 or abs(old_de - 0.15) < 1e-6):
                    summary["bfsi_de_cleared"].append({"ticker": ticker, "old_de": old_de, "new_de": None})
                    if apply_changes:
                        cur.execute(
                            f"UPDATE cached_fundamentals SET debt_to_equity = NULL WHERE ticker = {p}",
                            (ticker,),
                        )
                    cf["debt_to_equity"] = None
                elif not bfsi and old_de >= 5.0:
                    # Yahoo Finance debtToEquity is reported in % (e.g. TCS 9.83% -> 0.10x, INFY 9.54% -> 0.10x)
                    new_de = normalize_de_ratio(old_de, is_yfinance_pct=True, ticker=ticker)
                    summary["de_100x_scaled_fixes"].append({
                        "ticker": ticker,
                        "old_de": old_de,
                        "new_de": new_de,
                    })
                    if apply_changes:
                        cur.execute(
                            f"UPDATE cached_fundamentals SET debt_to_equity = {p} WHERE ticker = {p}",
                            (new_de, ticker),
                        )
                    cf["debt_to_equity"] = new_de

            # 3b. Extract missing metrics from archived `reports.report_text`
            if rep and rep.get("report_text"):
                seed_for_extract = {
                    "pe_ratio": cf.get("pe_ratio") if cf else rep.get("baseline_pe"),
                    "roce": cf.get("roce") if cf else None,
                    "roe": cf.get("roe") if cf else None,
                    "operating_margin": cf.get("operating_margin") if cf else None,
                    "debt_to_equity": cf.get("debt_to_equity") if cf else None,
                    "fifty_two_week_high": cf.get("fifty_two_week_high") if cf else None,
                    "fifty_two_week_low": cf.get("fifty_two_week_low") if cf else None,
                }
                extracted = extract_fundamentals_from_report_text(rep["report_text"], fallback_data=seed_for_extract)
                if bfsi:
                    extracted["debt_to_equity"] = None

                changed_fields: Dict[str, Tuple[Any, Any]] = {}
                if cf:
                    for col in (
                        "pe_ratio",
                        "roce",
                        "roe",
                        "operating_margin",
                        "debt_to_equity",
                        "fifty_two_week_high",
                        "fifty_two_week_low",
                    ):
                        old_v = cf.get(col)
                        new_v = extracted.get(col)
                        if col == "pe_ratio":
                            norm_old = normalize_pe_raw(old_v)
                            norm_new = normalize_pe_raw(new_v)
                            if old_v in (None, "N/A", "Fair", "", "N/A (Loss-Making)") and norm_new != "N/A":
                                changed_fields[col] = (old_v, norm_new)
                                cf[col] = norm_new
                            elif old_v in ("Fair", "N/A (Loss-Making)"):
                                changed_fields[col] = (old_v, norm_old)
                                cf[col] = norm_old
                        else:
                            if old_v is None and new_v is not None:
                                changed_fields[col] = (old_v, new_v)
                                cf[col] = new_v

                    if changed_fields:
                        summary["report_text_backfills"].append({"ticker": ticker, "changes": changed_fields})
                        if apply_changes:
                            set_clauses = ", ".join(f"{col} = {p}" for col in changed_fields.keys())
                            params = [v[1] for v in changed_fields.values()] + [ticker]
                            cur.execute(
                                f"UPDATE cached_fundamentals SET {set_clauses} WHERE ticker = {p}",
                                tuple(params),
                            )

                # Normalize `reports.baseline_pe` ('Fair' / 'N/A (Loss-Making)' / backfill from cf or extracted)
                old_b_pe = rep.get("baseline_pe")
                best_pe = normalize_pe_raw(
                    (cf.get("pe_ratio") if cf and cf.get("pe_ratio") not in (None, "N/A", "Fair") else None)
                    or extracted.get("pe_ratio")
                    or old_b_pe
                )
                same_numeric = False
                try:
                    if old_b_pe is not None and best_pe not in ("N/A", "NM"):
                        same_numeric = abs(float(old_b_pe) - float(best_pe)) < 1e-4
                except ValueError:
                    same_numeric = False

                if old_b_pe != best_pe and not same_numeric and not (old_b_pe == "N/A" and best_pe == "N/A"):
                    summary["baseline_pe_normalized"].append({
                        "ticker": ticker,
                        "old_pe": old_b_pe,
                        "new_pe": best_pe,
                    })
                    if apply_changes:
                        cur.execute(
                            f"UPDATE reports SET baseline_pe = {p} WHERE ticker = {p}",
                            (best_pe, ticker),
                        )
                    rep["baseline_pe"] = best_pe

        if apply_changes:
            conn.commit()

        # ------------------------------------------------------------------
        # 4. Remediate `discovery_reel` ('Fair' P/E, synthetic 22.4/0.15, GENSOL/RELIANCE)
        #    Executed BEFORE --live-enrich so all discovery rows are cleaned in <1s
        # ------------------------------------------------------------------
        cur.execute(
            "SELECT id, edition_date, ticker, company_name, sector, current_price, "
            "pe_ratio, roce_pct, debt_to_equity, catalyst_headline, key_metrics_json, is_active "
            "FROM discovery_reel"
        )
        reel_rows = cur.fetchall()
        inactive_val = False if is_pg else 0

        for r in reel_rows:
            row_id = r[0]
            ed_date = str(r[1])
            ticker = str(r[2] or "")
            comp_name = str(r[3] or ticker)
            sec = str(r[4] or "")
            px = float(r[5]) if r[5] is not None else 0.0
            raw_pe = r[6]
            roce_v = float(r[7]) if r[7] is not None else None
            de_v = float(r[8]) if r[8] is not None else None
            cat_h = str(r[9] or "")
            km_raw = r[10]
            is_act = bool(r[11])

            if ticker.startswith(("TEST", "UNITTEST", "SYNTHETIC")):
                continue

            cf = cf_map.get(ticker, {})
            rep = reports_map.get(ticker, {})
            rep_txt = rep.get("report_text") or ""

            # 4a. Deactivate High Governance Risk, distressed optical P/E (<3.0x), or Mega-Cap rows in active reel
            has_high_risk = bool(re.search(r"Governance:\s*High\s*Risk", rep_txt, re.I))
            mcap_cf = float(cf.get("market_cap") or rep.get("baseline_mcap") or 0.0)
            is_mega_cap = mcap_cf >= 1_000_000_000_000.0 or ticker == "RELIANCE"
            norm_pe_check = normalize_pe_raw(raw_pe)
            is_distressed_pe = False
            if norm_pe_check not in ("N/A", "NM"):
                try:
                    is_distressed_pe = float(norm_pe_check) < 3.0
                except ValueError:
                    is_distressed_pe = False

            if is_act and (has_high_risk or is_distressed_pe or is_mega_cap):
                reason = (
                    "High Governance/Debt Risk or Distressed Optical P/E (<3.0x)"
                    if (has_high_risk or is_distressed_pe)
                    else "Mega-Cap (>= ₹1L Cr) ineligible for Under-the-Radar reel"
                )
                summary["discovery_deactivated_rows"].append({
                    "id": row_id,
                    "edition_date": ed_date,
                    "ticker": ticker,
                    "reason": reason,
                })
                if apply_changes:
                    cur.execute(
                        f"UPDATE discovery_reel SET is_active = {p} WHERE id = {p}",
                        (inactive_val, row_id),
                    )
                continue

            # 4b. Resolve 'Fair' or missing P/E on discovery_reel
            resolved_pe = normalize_pe_raw(raw_pe)
            if resolved_pe == "N/A":
                cf_pe = normalize_pe_raw(cf.get("pe_ratio"))
                rep_pe = normalize_pe_raw(rep.get("baseline_pe"))
                resolved_pe = cf_pe if cf_pe != "N/A" else rep_pe

            # 4c. Fix legacy MF-induction hardcoded ROCE=22.4% / D/E=0.15x & BFSI D/E on discovery_reel
            bfsi = is_bfsi_entity(ticker=ticker, sector_label=sec, company_name=comp_name)
            is_mf_induction_synth = (
                "Statutory Mutual Fund Constituent Induction" in cat_h
                and roce_v is not None
                and de_v is not None
                and abs(roce_v - 22.4) < 1e-6
                and abs(de_v - 0.15) < 1e-6
            )
            new_roce = roce_v
            new_de = de_v
            if is_mf_induction_synth:
                real_roce = cf.get("roce")
                real_de = cf.get("debt_to_equity")
                new_roce = real_roce if (real_roce is not None and abs(real_roce - 22.0) > 1e-6) else None
                new_de = None if bfsi else (real_de if (real_de is not None and abs(real_de - 0.15) > 1e-6) else None)
                if resolved_pe == "22.50" and abs(px - 500.0) > 1e-6 and cf.get("pe_ratio") in (None, "N/A", "22.5", "22.50"):
                    resolved_pe = "N/A"
            elif bfsi and de_v is not None and de_v > 2.5:
                new_de = None

            pe_changed = str(raw_pe or "") != resolved_pe
            ratios_changed = (new_roce != roce_v) or (new_de != de_v)

            if pe_changed or ratios_changed:
                km_dict: Dict[str, Any] = {}
                if km_raw:
                    try:
                        km_dict = json.loads(km_raw)
                    except Exception as km_err:
                        logger.debug("Discovery key_metrics_json parse notice on id=%s: %s", row_id, km_err)
                        km_dict = {}
                km_dict["pe"] = resolved_pe
                if ratios_changed:
                    km_dict["roce"] = f"{new_roce:.1f}%" if new_roce is not None else "—"
                    km_dict["debt_to_equity"] = "BFSI" if bfsi else (f"{new_de:.2f}x" if new_de is not None else "—")
                new_km_json = json.dumps(km_dict)

                if pe_changed:
                    summary["discovery_fair_pe_fixes"].append({
                        "id": row_id,
                        "edition_date": ed_date,
                        "ticker": ticker,
                        "old_pe": raw_pe,
                        "new_pe": resolved_pe,
                    })
                if ratios_changed:
                    summary["discovery_synthetic_ratio_fixes"].append({
                        "id": row_id,
                        "edition_date": ed_date,
                        "ticker": ticker,
                        "old_roce_de": (roce_v, de_v),
                        "new_roce_de": (new_roce, new_de),
                    })
                if apply_changes:
                    cur.execute(
                        f"UPDATE discovery_reel SET pe_ratio = {p}, roce_pct = {p}, "
                        f"debt_to_equity = {p}, key_metrics_json = {p} WHERE id = {p}",
                        (resolved_pe, new_roce, new_de, new_km_json, row_id),
                    )

        if apply_changes:
            conn.commit()

        # ------------------------------------------------------------------
        # 5. Optional Live Exchange Enrichment (--live-enrich: SmartAPI + BSE Direct, YFINANCE_FALLBACK=0)
        # ------------------------------------------------------------------
        if live_enrich:
            os.environ["YFINANCE_FALLBACK"] = "0"
            from core.analysis.fundamentals import _FUNDAMENTALS_CACHE, enrich_fundamentals, get_stock_fundamentals
            _FUNDAMENTALS_CACHE.clear()

            candidates_for_live = [
                t for t in all_tickers
                if not t.startswith(("TEST_", "UNIT_", "COAL_", "UNITCOAL_"))
                and " " not in t
                and t not in KNOWN_TYPO_TICKERS
                and (
                    t in summary["synthetic_500_placeholders"]
                    or (cf_map.get(t, {}).get("pe_ratio") in (None, "N/A", "Fair"))
                    or (cf_map.get(t, {}).get("fifty_two_week_high") in (None, 0, 0.0))
                )
            ][: max(1, int(live_limit))]

            for t in candidates_for_live:
                try:
                    live = get_stock_fundamentals(t, fast_db_first=False)
                    if live:
                        live = enrich_fundamentals(t, live)
                    if not live or not live.get("current_price"):
                        continue
                    live_px = float(live["current_price"])
                    raw_mcap = live.get("market_cap")
                    live_mcap = (
                        float(raw_mcap)
                        if isinstance(raw_mcap, (int, float))
                        and raw_mcap > 0
                        and abs(float(raw_mcap) - 25_000_000_000.0) >= 1.0
                        else None
                    )
                    live_pe = normalize_pe_raw(live.get("pe_ratio"))
                    live_de = normalize_de_ratio(
                        live.get("debt_to_equity"),
                        ticker=t,
                        industry=str(live.get("industry") or ""),
                        company_name=str(live.get("short_name") or t),
                    )
                    live_roce = live.get("roce") if isinstance(live.get("roce"), (int, float)) else None
                    live_roe = live.get("roe") if isinstance(live.get("roe"), (int, float)) else None
                    live_opm = live.get("operating_margin") if isinstance(live.get("operating_margin"), (int, float)) else None
                    raw_h52 = live.get("fifty_two_week_high") or live.get("52w_high")
                    raw_l52 = live.get("fifty_two_week_low") or live.get("52w_low")
                    live_h52 = float(str(raw_h52).replace(",", "")) if raw_h52 not in (None, "N/A", "", 0, 0.0) else None
                    live_l52 = float(str(raw_l52).replace(",", "")) if raw_l52 not in (None, "N/A", "", 0, 0.0) else None
                    live_comp = str(live.get("short_name") or reports_map.get(t, {}).get("short_name") or t)
                    live_sec = str(live.get("sector") or "General Industry")
                    live_ind = str(live.get("industry") or "Diversified")

                    summary["live_enriched_tickers"].append({
                        "ticker": t,
                        "price": live_px,
                        "pe": live_pe,
                        "de": live_de,
                    })
                    if apply_changes:
                        cur.execute(
                            f"""
                            INSERT INTO cached_fundamentals (
                                ticker, company_name, sector, industry, current_price, market_cap,
                                pe_ratio, roce, roe, operating_margin, debt_to_equity,
                                fifty_two_week_high, fifty_two_week_low, source, updated_at
                            )
                            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, CURRENT_TIMESTAMP)
                            ON CONFLICT (ticker) DO UPDATE SET
                                current_price = COALESCE(EXCLUDED.current_price, cached_fundamentals.current_price),
                                market_cap = CASE WHEN ABS(COALESCE(cached_fundamentals.market_cap, 0) - 25000000000.0) < 1.0 THEN EXCLUDED.market_cap ELSE COALESCE(EXCLUDED.market_cap, cached_fundamentals.market_cap) END,
                                pe_ratio = CASE WHEN EXCLUDED.pe_ratio != 'N/A' THEN EXCLUDED.pe_ratio ELSE cached_fundamentals.pe_ratio END,
                                debt_to_equity = COALESCE(EXCLUDED.debt_to_equity, cached_fundamentals.debt_to_equity),
                                roce = COALESCE(EXCLUDED.roce, cached_fundamentals.roce),
                                roe = COALESCE(EXCLUDED.roe, cached_fundamentals.roe),
                                operating_margin = COALESCE(EXCLUDED.operating_margin, cached_fundamentals.operating_margin),
                                fifty_two_week_high = COALESCE(EXCLUDED.fifty_two_week_high, cached_fundamentals.fifty_two_week_high),
                                fifty_two_week_low = COALESCE(EXCLUDED.fifty_two_week_low, cached_fundamentals.fifty_two_week_low),
                                source = EXCLUDED.source,
                                updated_at = CURRENT_TIMESTAMP
                            """,
                            (
                                t,
                                live_comp,
                                live_sec,
                                live_ind,
                                live_px,
                                live_mcap,
                                live_pe,
                                live_roce,
                                live_roe,
                                live_opm,
                                live_de,
                                live_h52,
                                live_l52,
                                "SMARTAPI_BSE_EXCHANGE",
                            ),
                        )
                        cur.execute(
                            f"UPDATE reports SET "
                            f"baseline_price = {p}, "
                            f"baseline_mcap = CASE WHEN ABS(COALESCE(baseline_mcap, 0) - 25000000000.0) < 1.0 THEN {p} ELSE COALESCE({p}, baseline_mcap) END, "
                            f"baseline_pe = CASE WHEN {p} != 'N/A' THEN {p} ELSE baseline_pe END "
                            f"WHERE ticker = {p}",
                            (live_px, live_mcap, live_mcap, live_pe, live_pe, t),
                        )
                        if live_pe != "N/A":
                            cur.execute(
                                f"UPDATE discovery_reel SET pe_ratio = {p} WHERE ticker = {p} AND pe_ratio IN ('N/A', 'Fair', '22.5', '22.50')",
                                (live_pe, t),
                            )
                        conn.commit()
                        cf_map.setdefault(t, {"ticker": t, "company_name": live_comp, "sector": live_sec, "industry": live_ind})
                        cf_map[t]["current_price"] = live_px
                        if live_mcap is not None:
                            cf_map[t]["market_cap"] = live_mcap
                        if live_pe != "N/A":
                            cf_map[t]["pe_ratio"] = live_pe
                        if live_de is not None:
                            cf_map[t]["debt_to_equity"] = live_de
                except Exception as live_err:
                    logger.warning("Live enrichment notice for %s: %s", t, live_err)

        # ------------------------------------------------------------------
        # 6. Optional Explicitly-Confirmed Duplicate/Typo Purge
        # ------------------------------------------------------------------
        if purge_duplicates and confirm_delete and apply_changes:
            for item in summary["duplicate_or_typo_tickers"]:
                bad_t = item["ticker"]
                cur.execute(f"DELETE FROM reports WHERE ticker = {p}", (bad_t,))
                cur.execute(f"DELETE FROM cached_fundamentals WHERE ticker = {p}", (bad_t,))
                summary["purged_tickers"].append(bad_t)

        if apply_changes:
            conn.commit()
            try:
                from core.db.reports import get_all_equities_directory_sync
                get_all_equities_directory_sync.cache_clear()
            except Exception as cache_err:
                logger.debug("Directory cache clear notice: %s", cache_err)
        else:
            conn.rollback()

    finally:
        cur.close()
        conn.close()

    if not quiet:
        _print_report(summary, purge_duplicates=purge_duplicates, confirm_delete=confirm_delete)
    return summary


def _print_report(summary: Dict[str, Any], *, purge_duplicates: bool, confirm_delete: bool) -> None:
    print("=" * 80)
    print(f"MOATNOMICS EQUITY METRIC REMEDIATION AUDIT ({summary['mode']})")
    print(f"Target Database : {summary['target_db']}")
    print("=" * 80)

    print(f"\n[1] Legacy Pre-SmartAPI Cached D/E % Residue Fixes: {len(summary['de_100x_scaled_fixes'])}")
    for item in summary["de_100x_scaled_fixes"]:
        print(f"    • {item['ticker']:<14} D/E {item['old_de']}x  ->  {item['new_de']:.2f}x")

    print(f"\n[2] BFSI Distorted/Synthetic D/E Cleared (-> 'BFSI'): {len(summary['bfsi_de_cleared'])}")
    for item in summary["bfsi_de_cleared"][:20]:
        print(f"    • {item['ticker']:<14} D/E {item['old_de']}  ->  NULL (renders 'BFSI')")
    if len(summary["bfsi_de_cleared"]) > 20:
        print(f"    ... and {len(summary['bfsi_de_cleared']) - 20} more")

    print(f"\n[3] Archived Report-Text Quantitative Backfills   : {len(summary['report_text_backfills'])}")
    for item in summary["report_text_backfills"][:25]:
        chg_str = ", ".join(f"{k}: {v[0]} -> {v[1]}" for k, v in item["changes"].items())
        print(f"    • {item['ticker']:<14} {chg_str}")
    if len(summary["report_text_backfills"]) > 25:
        print(f"    ... and {len(summary['report_text_backfills']) - 25} more")

    print(f"\n[4] Stale `reports.baseline_price` Synced         : {len(summary['baseline_price_synced'])}")
    for item in summary["baseline_price_synced"]:
        print(f"    • {item['ticker']:<14} ₹{item['old_price']:,.2f}  ->  ₹{item['new_price']:,.2f}")

    print(f"\n[5] `reports.baseline_pe` Normalized/Backfilled   : {len(summary['baseline_pe_normalized'])}")
    for item in summary["baseline_pe_normalized"][:20]:
        print(f"    • {item['ticker']:<14} {item['old_pe']!r}  ->  {item['new_pe']!r}")
    if len(summary["baseline_pe_normalized"]) > 20:
        print(f"    ... and {len(summary['baseline_pe_normalized']) - 20} more")

    print(f"\n[6] `discovery_reel` 'Fair'/Unnormalized P/E Fixes: {len(summary['discovery_fair_pe_fixes'])}")
    for item in summary["discovery_fair_pe_fixes"][:15]:
        print(f"    • [{item['edition_date']}] {item['ticker']:<12} {item['old_pe']!r}  ->  {item['new_pe']!r}")
    if len(summary["discovery_fair_pe_fixes"]) > 15:
        print(f"    ... and {len(summary['discovery_fair_pe_fixes']) - 15} more across archive editions")

    print(f"\n[7] `discovery_reel` Hardcoded 22.4%/0.15x Fixes  : {len(summary['discovery_synthetic_ratio_fixes'])}")
    for item in summary["discovery_synthetic_ratio_fixes"][:15]:
        print(f"    • [{item['edition_date']}] {item['ticker']:<12} ROCE/DE {item['old_roce_de']} -> {item['new_roce_de']}")
    if len(summary["discovery_synthetic_ratio_fixes"]) > 15:
        print(f"    ... and {len(summary['discovery_synthetic_ratio_fixes']) - 15} more")

    print(f"\n[8] `discovery_reel` Quality Gate Deactivations   : {len(summary['discovery_deactivated_rows'])}")
    for item in summary["discovery_deactivated_rows"]:
        print(f"    • [{item['edition_date']}] {item['ticker']:<12} -> is_active=False ({item['reason']})")

    print(f"\n[9] Legacy Synthetic ₹500 / ₹2,500Cr / 22.5x Rows : {len(summary['synthetic_500_placeholders'])}")
    if summary["synthetic_500_placeholders"]:
        sample = ", ".join(summary["synthetic_500_placeholders"][:15])
        print(f"    • Tickers: {sample}" + (" ..." if len(summary["synthetic_500_placeholders"]) > 15 else ""))
        print("    • Tip: Run with `--apply --live-enrich` to hydrate via Angel One SmartAPI + BSE Official Direct API,")
        print("           or `--apply --clear-synthetic-placeholders` (offline) to replace fake ₹500/22.5x with '—'.")

    if summary["live_enriched_tickers"]:
        print(f"\n[10] Live Exchange Enriched Tickers               : {len(summary['live_enriched_tickers'])}")
        for item in summary["live_enriched_tickers"][:20]:
            print(f"    • {item['ticker']:<14} ₹{item['price']:,.2f} | P/E: {item['pe']} | D/E: {item['de']}")

    print(f"\n[11] Duplicate / Non-Canonical / Typo Tickers     : {len(summary['duplicate_or_typo_tickers'])}")
    for item in summary["duplicate_or_typo_tickers"]:
        print(f"    • {item['ticker']!r:<28} -> {item['reason']}")
    if summary["duplicate_or_typo_tickers"] and not (purge_duplicates and confirm_delete):
        print("    • Safe Mode: Zero rows deleted. Pass `--apply --purge-duplicates --confirm-delete` only if you want to delete these.")
    if summary["purged_tickers"]:
        print(f"    • Purged with explicit confirmation: {summary['purged_tickers']}")

    print("=" * 80)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate, backfill, and standardize Moatnomics equity metrics (Feedback #4 & #10)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview all changes without modifying the database (default unless --apply is set).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit non-destructive metric normalizations and backfills to the database.",
    )
    parser.add_argument(
        "--sqlite-path",
        type=str,
        default=None,
        help="Optional explicit path to a SQLite database file (bypasses SUPABASE_DB_URL).",
    )
    parser.add_argument(
        "--clear-synthetic-placeholders",
        action="store_true",
        help="Clear legacy offline batch placeholders (₹500.00 / ₹2,500 Cr / 22.5x) to NULL/'N/A' ('—').",
    )
    parser.add_argument(
        "--live-enrich",
        action="store_true",
        help="Query Angel One SmartAPI + Official BSE Direct API (YFINANCE_FALLBACK=0) to enrich synthetic/missing rows.",
    )
    parser.add_argument(
        "--live-limit",
        type=int,
        default=120,
        help="Maximum number of tickers to query during --live-enrich (default: 120).",
    )
    parser.add_argument(
        "--purge-duplicates",
        action="store_true",
        help="Delete identified duplicate space-separated aliases / non-scrip typos (requires --confirm-delete).",
    )
    parser.add_argument(
        "--confirm-delete",
        action="store_true",
        help="Explicit confirmation gate required alongside --purge-duplicates.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    args = build_arg_parser().parse_args(argv)
    if args.purge_duplicates and not args.confirm_delete:
        print("ERROR: --purge-duplicates requires --confirm-delete to prevent accidental data loss.", file=sys.stderr)
        return 2
    if args.sqlite_path:
        import core.db.connection as db_conn
        db_conn._CACHED_SUPABASE_URL = None
        db_conn._SUPABASE_URL_RESOLVED = True
    run_remediation(
        sqlite_path=args.sqlite_path,
        apply_changes=bool(args.apply),
        clear_synthetic_placeholders=bool(args.clear_synthetic_placeholders),
        live_enrich=bool(args.live_enrich),
        live_limit=args.live_limit,
        purge_duplicates=bool(args.purge_duplicates),
        confirm_delete=bool(args.confirm_delete),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
