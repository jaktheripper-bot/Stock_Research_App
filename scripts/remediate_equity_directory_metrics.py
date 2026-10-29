#!/usr/bin/env python3
"""
Repairs inverted 52W ranges (e.g. KOTAKBANK 3.1/27.0, COFORGE 50.0/1008.5),
backfills missing 52W High/Low from 252-day exchange candles, and populates
missing Operating Margin (OPM) strictly from verified upstream fundamentals.
"""

import argparse
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ENABLE_BACKGROUND_SCHEDULERS"] = "0"

from bse_master import resolve_bse_scrip_code
from core.analysis import get_historical_prices, get_stock_fundamentals
from core.analysis.fundamentals import _FUNDAMENTALS_CACHE
from core.db.connection import (
    get_db_connection,
    get_db_path,
    get_placeholder,
    is_postgres_connection,
    now_ist_iso,
)
from core.db.reports import get_all_equities_directory_sync
from core.ingestion.angel_one import AngelOneGateway
from core.presentation.formatters import is_bfsi_entity

logger = logging.getLogger("equity_research.scripts.remediate_directory_metrics")


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).replace(",", "").replace("%", "").replace("₹", "").strip()
    if not s or s.upper() in ("N/A", "NONE", "NAN", "-", "—", "NM"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_plausible_52w(hi: Optional[float], lo: Optional[float], cmp_val: float) -> bool:
    if hi is None or lo is None or hi <= 0 or lo <= 0 or hi < lo:
        return False
    if cmp_val > 0 and (hi < cmp_val * 0.90 or lo > cmp_val * 1.10):
        return False
    return True


def _resolve_verified_52w(ticker: str, cmp_val: float) -> Optional[Tuple[float, float]]:
    if AngelOneGateway.is_configured():
        eod = AngelOneGateway.get_eod_summary(ticker)
        if eod:
            hi = _to_float(eod.get("fifty_two_week_high") or eod.get("52w_high"))
            lo = _to_float(eod.get("fifty_two_week_low") or eod.get("52w_low"))
            if _is_plausible_52w(hi, lo, cmp_val):
                return round(float(hi), 2), round(float(lo), 2)

    df = get_historical_prices(ticker, period="1y")
    if df is not None and not df.empty and "High" in df.columns and "Low" in df.columns:
        hi = float(df["High"].tail(252).max())
        lo = float(df["Low"].tail(252).min())
        if _is_plausible_52w(hi, lo, cmp_val):
            return round(hi, 2), round(lo, 2)

    # Verified BSE Exchange corporate-action split-adjusted 52W fallback for BSE-only scrips
    scrip = resolve_bse_scrip_code(ticker)
    if scrip and str(scrip).isdigit():
        try:
            resp = requests.get(
                f"https://api.bseindia.com/BseIndiaAPI/api/HighLow/w?Type=EQ&flag=C&scripcode={scrip}",
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://www.bseindia.com/",
                    "Accept": "application/json",
                },
                timeout=3.0,
            )
            if resp.status_code == 200:
                payload = resp.json() or {}
                hi = _to_float(payload.get("Fifty2WkHigh_adj"))
                lo = _to_float(payload.get("Fifty2WkLow_adj"))
                if _is_plausible_52w(hi, lo, cmp_val):
                    return round(float(hi), 2), round(float(lo), 2)
        except Exception as bse_err:
            logger.debug("BSE HighLow lookup notice for %s (%s): %s", ticker, scrip, bse_err)

    return None


def _apply_updates_to_cursor(
    cur,
    ph: str,
    updates_52w: Dict[str, Tuple[float, float, str]],
    updates_opm: Dict[str, Tuple[float, str]],
    now_ts: str,
) -> None:
    for sym, (new_hi, new_lo, comp_name) in updates_52w.items():
        cur.execute(
            f"""
            INSERT INTO cached_fundamentals (ticker, company_name, fifty_two_week_high, fifty_two_week_low, updated_at)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
            ON CONFLICT (ticker) DO UPDATE SET
                fifty_two_week_high = EXCLUDED.fifty_two_week_high,
                fifty_two_week_low = EXCLUDED.fifty_two_week_low,
                updated_at = EXCLUDED.updated_at
            """,
            (sym, comp_name, new_hi, new_lo, now_ts),
        )
    for sym, (opm_num, comp_name) in updates_opm.items():
        cur.execute(
            f"""
            INSERT INTO cached_fundamentals (ticker, company_name, operating_margin, updated_at)
            VALUES ({ph}, {ph}, {ph}, {ph})
            ON CONFLICT (ticker) DO UPDATE SET
                operating_margin = EXCLUDED.operating_margin,
                updated_at = EXCLUDED.updated_at
            """,
            (sym, comp_name, opm_num, now_ts),
        )


def remediate(apply: bool = False, limit: int = 400) -> None:
    equities = get_all_equities_directory_sync()[:limit]
    fixed_52w, fixed_opm = 0, 0
    updates_52w: Dict[str, Tuple[float, float, str]] = {}
    updates_opm: Dict[str, Tuple[float, str]] = {}

    for eq in equities:
        sym = eq["ticker"]
        comp_name = str(eq.get("company_name") or eq.get("name") or sym)
        cmp_f = _to_float(eq.get("current_price")) or 0.0
        hi = _to_float(eq.get("fifty_two_week_high"))
        lo = _to_float(eq.get("fifty_two_week_low"))
        opm = _to_float(eq.get("operating_margin"))

        # 1. Detect missing, inverted, degenerate, or CMP-distorted 52W range
        #    (e.g. P/B ratio 3.1 leaked into 52W High when CMP is ₹443+, or hi <= lo)
        corrupt_52w = (
            hi is None
            or lo is None
            or hi <= 0
            or lo <= 0
            or hi <= lo
            or (cmp_f > 0 and (hi < cmp_f * 0.95 or lo > cmp_f * 1.05))
        )
        if corrupt_52w:
            pair = _resolve_verified_52w(sym, cmp_f)
            if pair:
                new_hi, new_lo = pair
                print(f"[52W] {sym}: ({hi}, {lo}) -> ({new_hi}, {new_lo})")
                fixed_52w += 1
                updates_52w[sym] = (new_hi, new_lo, comp_name)
            time.sleep(0.12)

        # 2. Backfill OPM strictly when upstream fundamentals yield a real operating margin
        #    (excluding BFSI banks/NBFCs/insurers where Operating Margin is structurally N/A)
        if opm is None and not is_bfsi_entity(
            ticker=sym,
            sector_slug=str(eq.get("sector_slug") or ""),
            sector_label=str(eq.get("sector") or ""),
            industry=str(eq.get("industry") or ""),
            company_name=comp_name,
        ):
            _FUNDAMENTALS_CACHE.pop(sym, None)
            try:
                live_f = get_stock_fundamentals(sym, fast_db_first=False) or {}
            except Exception as f_err:
                logger.debug("Live fundamentals lookup skipped for %s: %s", sym, f_err)
                live_f = {}
            live_opm = _to_float(live_f.get("operating_margin") if live_f.get("operating_margin") is not None else live_f.get("opm"))
            if live_opm is not None and -100.0 <= live_opm <= 95.0:
                opm_num = round(float(live_opm), 2)
                opm_str = f"{opm_num:.1f}%"
                print(f"[OPM] {sym}: None -> {opm_str}")
                fixed_opm += 1
                updates_opm[sym] = (opm_num, comp_name)
            time.sleep(0.12)

    if apply and (updates_52w or updates_opm):
        now_ts = now_ist_iso()
        ph = get_placeholder()
        with get_db_connection() as conn:
            is_pg = is_postgres_connection(conn)
            cur = conn.cursor()
            try:
                _apply_updates_to_cursor(cur, ph, updates_52w, updates_opm, now_ts)
                conn.commit()
            finally:
                cur.close()

            # Keep local reports.db synchronized when primary connection is PostgreSQL
            if is_pg:
                sq_path = Path(get_db_path())
                if sq_path.exists():
                    sq_conn = sqlite3.connect(str(sq_path))
                    sq_cur = sq_conn.cursor()
                    try:
                        _apply_updates_to_cursor(sq_cur, "?", updates_52w, updates_opm, now_ts)
                        sq_conn.commit()
                    finally:
                        sq_cur.close()
                        sq_conn.close()

        get_all_equities_directory_sync.cache_clear()

    print(f"Summary ({'APPLIED' if apply else 'DRY-RUN'}): 52W repaired={fixed_52w}, OPM backfilled={fixed_opm}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=400)
    args = ap.parse_args()
    remediate(apply=bool(args.apply and not args.dry_run), limit=args.limit)

