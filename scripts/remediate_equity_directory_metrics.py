#!/usr/bin/env python3
"""
Authoritative Exchange Metrics Remediation (Angel One SmartAPI + Official BSE Direct)
=====================================================================================
Strictly enforces YFINANCE_FALLBACK=0:
1. Refreshes stale current_price when CMP drifts outside verified 52W exchange bounds
   (e.g. AVALON, GRAND CONTINENTAL).
2. Repairs missing, inverted, or face-value-corrupted 52W High/Low ranges (e.g. IPCALAB,
   MEDPLUS, PPLPHARMA, GRAND CONTINENTAL, PRICOL, AMIORG) via Angel One SmartAPI EOD summary,
   252-day SmartAPI candles, or BSE HighLow/w.
3. Surgically remediates provably poisoned operating_margin values (BFSI entities,
   unanchored 'Devel-OPM-ent' regex victims, clause-skipping prose victims, and standalone
   BSE exceptional/dividend outliers) without overwriting healthy consolidated margins.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ENABLE_BACKGROUND_SCHEDULERS"] = "0"
os.environ["YFINANCE_FALLBACK"] = "0"

from bse_master import get_bse_scrips_cache, resolve_bse_scrip_code
from core.analysis import get_historical_prices
from core.db.connection import (
    get_db_connection,
    get_db_path,
    get_placeholder,
    is_postgres_connection,
    now_ist_iso,
)
from core.db.fundamentals import extract_fundamentals_from_report_text
from core.db.reports import get_all_equities_directory_sync
from core.ingestion.angel_one import AngelOneGateway
from core.presentation.formatters import is_bfsi_entity

logger = logging.getLogger("equity_research.scripts.remediate_directory_metrics")

_BSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json",
}

# Tickers whose cached operating_margin was populated from standalone BSE dividend/exceptional spikes
# or multi-clause prose skips (mapped to their poisoned legacy values for idempotent execution)
_EXPLICIT_POISONED_OPM_VALUES: Dict[str, float] = {
    "BAJAJ-AUTO": 1.0,
    "COALINDIA": 67.56,
    "DIXON": 56.4,
    "IPCALAB": 4.8,
    "LGEINDIA": 46.0,
    "MAXHEALTH": 12.0,
    "ONGC": 65.04,
    "RELIANCE": 53.3,
    "TVSMOTOR": 24.0,
    "WHIRLPOOL": 20.0,
}

_RENAME_52W_PROXY = {
    "AMIORG": "ACUTAAS",
    "PRICOL": "PRICOLLTD",
}


def _to_float(v: Any) -> Optional[float]:
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
    if hi is None or lo is None or hi <= 0 or lo <= 0 or hi <= lo:
        return False
    # Reject ₹1/₹2/₹5/₹10 face-value corruption on >₹100 equities while preserving genuine multibaggers
    if cmp_val > 0 and (hi < cmp_val * 0.90 or lo > cmp_val * 1.10 or (cmp_val >= 100.0 and lo < cmp_val * 0.05)):
        return False
    return True


def _resolve_fast_scrip(sym: str, company_name: str = "") -> Optional[str]:
    """Resolves 6-digit BSE scrip code from local master maps without triggering slow LLM search."""
    scrips_cache = get_bse_scrips_cache() or {}
    sym_map = scrips_cache.get("symbols") or {}
    names_map = scrips_cache.get("names") or {}
    clean_sym = sym.strip().upper()
    if clean_sym.isdigit() and len(clean_sym) == 6:
        return clean_sym
    if clean_sym in sym_map:
        return str(sym_map[clean_sym])
    from bse_master import PRIMARY_BSE_MAP
    if clean_sym in PRIMARY_BSE_MAP:
        return str(PRIMARY_BSE_MAP[clean_sym])
    if company_name:
        up_nm = company_name.strip().upper()
        for cand in (up_nm, up_nm.rstrip("."), up_nm.replace(" LIMITED", " LTD")):
            if cand in names_map:
                return str(names_map[cand])
    return None


def _fetch_bse_direct_snapshot(item: Tuple[str, str]) -> Dict[str, Any]:
    """Queries official BSE JSON ComHeadernew/w for 52W range and consolidated-aligned OPM."""
    sym, company_name = item
    scrip = _resolve_fast_scrip(sym, company_name)
    if not scrip or not str(scrip).isdigit():
        return {}
    out: Dict[str, Any] = {"scrip": str(scrip)}
    try:
        com_res = requests.get(
            f"https://api.bseindia.com/BseIndiaAPI/api/ComHeadernew/w?quotetype=EQ&scripcode={scrip}&seriesid=",
            headers=_BSE_HEADERS,
            timeout=4.0,
        )
        if com_res.status_code == 200:
            com_json = com_res.json() or {}
            out["hi_52"] = _to_float(com_json.get("FiftyTwoWkHigh"))
            out["lo_52"] = _to_float(com_json.get("FiftyTwoWkLow"))
            raw_con_opm = str(com_json.get("ConOPM") or "").replace(",", "").strip()
            raw_st_opm = str(com_json.get("OPM") or "").replace(",", "").strip()
            con_pe_val = _to_float(com_json.get("ConPE"))
            st_pe_val = _to_float(com_json.get("PE"))
            con_eps_val = _to_float(com_json.get("ConEPS"))
            st_eps_val = _to_float(com_json.get("EPS"))
            if con_eps_val == 0.0:
                con_eps_val = None
            if st_eps_val == 0.0:
                st_eps_val = None

            opm_cand = None
            if raw_con_opm not in ("", "-", "None", "0", "0.00"):
                opm_cand = _to_float(raw_con_opm)
            elif raw_st_opm not in ("", "-", "None", "0", "0.00"):
                st_val = _to_float(raw_st_opm)
                eps_divergent = (
                    con_eps_val is not None
                    and st_eps_val is not None
                    and max(abs(con_eps_val), abs(st_eps_val)) > 0
                    and abs(con_eps_val - st_eps_val) / max(abs(con_eps_val), abs(st_eps_val)) > 0.25
                )
                loss_making = (con_pe_val is not None and con_pe_val < 0) or (st_pe_val is not None and st_pe_val < 0)
                if st_val is not None and not eps_divergent and not loss_making and -40.0 <= st_val <= 42.0:
                    opm_cand = st_val
            if opm_cand is not None and -100.0 <= opm_cand <= 95.0:
                out["opm_aligned"] = round(float(opm_cand), 2)
    except Exception as err:
        logger.debug("BSE ComHeadernew lookup notice for %s (%s): %s", sym, scrip, err)
    return out


def _resolve_live_price(ticker: str, scrip: Optional[str]) -> Optional[float]:
    if " " not in ticker and AngelOneGateway.is_configured():
        for probe in ([ticker] if ticker not in _RENAME_52W_PROXY else [ticker, _RENAME_52W_PROXY[ticker]]):
            eod = AngelOneGateway.get_eod_summary(probe)
            if eod:
                ltp = _to_float(eod.get("current_price") or eod.get("ltp") or eod.get("close"))
                if ltp and ltp > 0:
                    return round(float(ltp), 2)
    if scrip and str(scrip).isdigit():
        try:
            hdr_res = requests.get(
                f"https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w?Debtflag=&scripcode={scrip}&seriesid=",
                headers=_BSE_HEADERS,
                timeout=4.5,
            )
            if hdr_res.status_code == 200:
                ltp = _to_float(((hdr_res.json() or {}).get("CurrRate") or {}).get("LTP"))
                if ltp and ltp > 0:
                    return round(float(ltp), 2)
        except Exception as err:
            logger.debug("BSE LTP lookup notice for %s (%s): %s", ticker, scrip, err)
    return None


def _resolve_verified_52w(ticker: str, cmp_val: float, bse_snap: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    probes = [ticker]
    if ticker in _RENAME_52W_PROXY:
        probes.append(_RENAME_52W_PROXY[ticker])

    if " " not in ticker and AngelOneGateway.is_configured():
        for probe in probes:
            eod = AngelOneGateway.get_eod_summary(probe)
            if eod:
                hi = _to_float(eod.get("fifty_two_week_high") or eod.get("52w_high"))
                lo = _to_float(eod.get("fifty_two_week_low") or eod.get("52w_low"))
                ref_px = _to_float(eod.get("current_price")) or cmp_val
                if _is_plausible_52w(hi, lo, ref_px):
                    return round(float(hi), 2), round(float(lo), 2)

    if _is_plausible_52w(bse_snap.get("hi_52"), bse_snap.get("lo_52"), cmp_val):
        return round(float(bse_snap["hi_52"]), 2), round(float(bse_snap["lo_52"]), 2)

    scrip = bse_snap.get("scrip")
    if scrip and str(scrip).isdigit():
        try:
            resp = requests.get(
                f"https://api.bseindia.com/BseIndiaAPI/api/HighLow/w?Type=EQ&flag=C&scripcode={scrip}",
                headers=_BSE_HEADERS,
                timeout=4.5,
            )
            if resp.status_code == 200:
                payload = resp.json() or {}
                hi = _to_float(payload.get("Fifty2WkHigh_adj") or payload.get("Fifty2WkHigh"))
                lo = _to_float(payload.get("Fifty2WkLow_adj") or payload.get("Fifty2WkLow"))
                if _is_plausible_52w(hi, lo, cmp_val):
                    return round(float(hi), 2), round(float(lo), 2)
        except Exception as bse_err:
            logger.debug("BSE HighLow lookup notice for %s (%s): %s", ticker, scrip, bse_err)

    for probe in probes:
        if " " in probe:
            continue
        df = get_historical_prices(probe, period="1y")
        if df is not None and not df.empty and "High" in df.columns and "Low" in df.columns:
            hi = float(df["High"].tail(252).max())
            lo = float(df["Low"].tail(252).min())
            if _is_plausible_52w(hi, lo, cmp_val):
                return round(hi, 2), round(lo, 2)

    return None


def _load_corpus_rows() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    cf.ticker,
                    COALESCE(cf.company_name, r.short_name, cf.ticker) AS company_name,
                    COALESCE(cf.sector, '') AS sector,
                    COALESCE(cf.industry, '') AS industry,
                    cf.current_price,
                    cf.fifty_two_week_high,
                    cf.fifty_two_week_low,
                    cf.operating_margin,
                    r.report_text
                FROM cached_fundamentals cf
                LEFT JOIN reports r ON UPPER(r.ticker) = UPPER(cf.ticker)
                ORDER BY cf.ticker ASC
                """
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            cur.close()


def _apply_updates_to_cursor(
    cur,
    ph: str,
    updates_price: Dict[str, Tuple[float, str]],
    updates_52w: Dict[str, Tuple[float, float, str]],
    updates_opm: Dict[str, Tuple[Optional[float], str]],
    now_ts: str,
) -> None:
    for sym, (new_px, comp_name) in updates_price.items():
        cur.execute(
            f"""
            INSERT INTO cached_fundamentals (ticker, company_name, current_price, updated_at)
            VALUES ({ph}, {ph}, {ph}, {ph})
            ON CONFLICT (ticker) DO UPDATE SET
                current_price = EXCLUDED.current_price,
                updated_at = EXCLUDED.updated_at
            """,
            (sym, comp_name, new_px, now_ts),
        )
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
    rows = _load_corpus_rows()[:limit]
    candidate_pairs: List[Tuple[str, str]] = []
    for eq in rows:
        sym = eq["ticker"]
        if sym.startswith(("TEST_", "UNIT_", "COAL_")):
            continue
        cmp_f = _to_float(eq.get("current_price")) or 0.0
        hi = _to_float(eq.get("fifty_two_week_high"))
        lo = _to_float(eq.get("fifty_two_week_low"))
        opm = _to_float(eq.get("operating_margin"))
        txt = str(eq.get("report_text") or "")
        needs_52w_or_px = (
            cmp_f <= 0
            or hi is None
            or lo is None
            or hi <= 0
            or lo <= 0
            or hi <= lo
            or (cmp_f > 0 and (hi < cmp_f * 0.95 or lo > cmp_f * 1.05 or (cmp_f >= 100.0 and lo < cmp_f * 0.05)))
        )
        is_opment = False
        if opm is not None and txt:
            m_old = re.search(r"(?:Operating Margin|OPM|EBITDA Margin)[^\d\n]*?(\d+(?:\.\d+)?)\s*%", txt, re.I)
            if m_old and "opment" in m_old.group(0).lower() and abs(float(m_old.group(1)) - opm) < 0.25:
                is_opment = True
        is_explicit_poison = (
            opm is not None
            and sym in _EXPLICIT_POISONED_OPM_VALUES
            and abs(opm - _EXPLICIT_POISONED_OPM_VALUES[sym]) < 0.25
        )
        if needs_52w_or_px or is_opment or is_explicit_poison:
            candidate_pairs.append((sym, str(eq.get("company_name") or "")))

    print(f"Fetching official BSE snapshots for {len(candidate_pairs)} candidate equities out of {len(rows)} (YFINANCE_FALLBACK=0)...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        bse_snaps = dict(zip([p[0] for p in candidate_pairs], pool.map(_fetch_bse_direct_snapshot, candidate_pairs)))

    updates_price: Dict[str, Tuple[float, str]] = {}
    updates_52w: Dict[str, Tuple[float, float, str]] = {}
    updates_opm: Dict[str, Tuple[Optional[float], str]] = {}

    for eq in rows:
        sym = eq["ticker"]
        if sym.startswith(("TEST_", "UNIT_", "COAL_")):
            continue
        comp_name = str(eq.get("company_name") or sym)
        cmp_f = _to_float(eq.get("current_price")) or 0.0
        hi = _to_float(eq.get("fifty_two_week_high"))
        lo = _to_float(eq.get("fifty_two_week_low"))
        opm = _to_float(eq.get("operating_margin"))
        txt = str(eq.get("report_text") or "")
        bse_snap = bse_snaps.get(sym) or {}

        # 1. Refresh stale current_price if CMP is missing, 52W is missing, or CMP sits outside 52W bounds
        needs_px_check = (
            cmp_f <= 0
            or hi is None
            or lo is None
            or (hi > lo > 0 and (cmp_f < lo * 0.95 or cmp_f > hi * 1.05))
        )
        if needs_px_check:
            live_px = _resolve_live_price(sym, bse_snap.get("scrip"))
            if live_px and live_px > 0 and (cmp_f <= 0 or abs(live_px - cmp_f) / cmp_f >= 0.005):
                print(f"[PRICE] {sym}: {cmp_f} -> {live_px}")
                updates_price[sym] = (live_px, comp_name)
                cmp_f = live_px
            time.sleep(0.08)

        # 2. Repair missing, inverted, CMP-distorted, or face-value-corrupted (lo < cmp*0.05) 52W ranges
        corrupt_52w = (
            hi is None
            or lo is None
            or hi <= 0
            or lo <= 0
            or hi <= lo
            or (cmp_f > 0 and (hi < cmp_f * 0.95 or lo > cmp_f * 1.05 or (cmp_f >= 100.0 and lo < cmp_f * 0.05)))
        )
        if corrupt_52w:
            pair = _resolve_verified_52w(sym, cmp_f, bse_snap)
            if pair:
                new_hi, new_lo = pair
                print(f"[52W] {sym}: ({hi}, {lo}) -> ({new_hi}, {new_lo})")
                updates_52w[sym] = (new_hi, new_lo, comp_name)
            else:
                print(f"[52W-PENDING] {sym}: unresolved ({hi}, {lo}) at CMP={cmp_f}")
            time.sleep(0.10)

        # 3. Surgical remediation of provably poisoned Operating Margin values only
        is_bfsi = is_bfsi_entity(
            ticker=sym,
            sector_label=str(eq.get("sector") or ""),
            industry=str(eq.get("industry") or ""),
            company_name=comp_name,
        )
        if is_bfsi or sym == "SENSEX1":
            if opm is not None:
                print(f"[OPM-BFSI-CLEAR] {sym}: {opm}% -> NULL")
                updates_opm[sym] = (None, comp_name)
            continue

        # Detect 'Devel-OPM-ent' unanchored word-boundary victim
        is_opment_victim = False
        if opm is not None and txt:
            m_old = re.search(r"(?:Operating Margin|OPM|EBITDA Margin)[^\d\n]*?(\d+(?:\.\d+)?)\s*%", txt, re.I)
            if m_old and "opment" in m_old.group(0).lower() and abs(float(m_old.group(1)) - opm) < 0.25:
                is_opment_victim = True

        is_explicit_poison = (
            opm is not None
            and sym in _EXPLICIT_POISONED_OPM_VALUES
            and abs(opm - _EXPLICIT_POISONED_OPM_VALUES[sym]) < 0.25
        )
        if is_opment_victim or is_explicit_poison:
            new_opm: Optional[float] = bse_snap.get("opm_aligned")
            if new_opm is None and txt:
                extracted = extract_fundamentals_from_report_text(
                    txt,
                    {
                        "ticker": sym,
                        "company_name": comp_name,
                        "sector": str(eq.get("sector") or ""),
                        "industry": str(eq.get("industry") or ""),
                    },
                )
                ext_val = _to_float(extracted.get("operating_margin"))
                if ext_val is not None and -40.0 <= ext_val <= 45.0:
                    new_opm = round(ext_val, 2)

            if opm != new_opm:
                label = f"{new_opm}%" if new_opm is not None else "NULL (pending consolidated sync)"
                print(f"[OPM-REMEDIATE] {sym}: {opm}% -> {label}")
                updates_opm[sym] = (new_opm, comp_name)

    if apply and (updates_price or updates_52w or updates_opm):
        now_ts = now_ist_iso()
        ph = get_placeholder()
        with get_db_connection() as conn:
            is_pg = is_postgres_connection(conn)
            cur = conn.cursor()
            try:
                _apply_updates_to_cursor(cur, ph, updates_price, updates_52w, updates_opm, now_ts)
                conn.commit()
            finally:
                cur.close()

            if is_pg:
                sq_path = Path(get_db_path())
                if sq_path.exists():
                    sq_conn = sqlite3.connect(str(sq_path))
                    sq_cur = sq_conn.cursor()
                    try:
                        _apply_updates_to_cursor(sq_cur, "?", updates_price, updates_52w, updates_opm, now_ts)
                        sq_conn.commit()
                    finally:
                        sq_cur.close()
                        sq_conn.close()

        get_all_equities_directory_sync.cache_clear()

    print(
        f"Summary ({'APPLIED' if apply else 'DRY-RUN'}): "
        f"price_refreshed={len(updates_price)}, 52W_repaired={len(updates_52w)}, OPM_remediated={len(updates_opm)}"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=400)
    args = ap.parse_args()
    remediate(apply=bool(args.apply and not args.dry_run), limit=args.limit)
