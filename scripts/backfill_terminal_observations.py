"""Idempotently backfill dedicated terminal observation tables from verified dated DB records."""

import argparse
from datetime import date, datetime
import json
import logging
import math
from pathlib import Path
import sys
from typing import Any, Dict, List

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.analysis.metric_contract import has_forbidden_vendor_token
from core.db.connection import (
    IST,
    get_configured_supabase_url,
    get_db_connection,
    init_db,
    is_postgres_connection,
)

logger = logging.getLogger(__name__)


def _valid_finite(val: Any) -> float | None:
    if isinstance(val, bool):
        return None
    try:
        num = float(val)
    except (TypeError, ValueError, OverflowError):
        return None
    return num if math.isfinite(num) else None


def _valid_past_or_today_iso(raw: Any, today: date) -> str | None:
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None
    return parsed.isoformat() if parsed <= today else None


def backfill_terminal_observations(*, apply: bool = False) -> Dict[str, Any]:
    """Scan existing DB tables for dated, non-vendor observations and persist to v047 tables."""
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    postgres = is_postgres_connection(conn)
    p = "%s" if postgres else "?"
    today = datetime.now(IST).date()
    now_iso = datetime.now(IST).isoformat()

    debt_candidates: List[Dict[str, Any]] = []
    instrument_candidates: List[Dict[str, Any]] = []

    try:
        if apply and not postgres:
            if get_configured_supabase_url():
                raise RuntimeError("Configured PostgreSQL is unavailable.")
            cur.execute("BEGIN IMMEDIATE")

        # 1. Sovereign RBI auction cut-off observations
        cur.execute(
            "SELECT tenor_label, cut_off_yield, auction_date, source FROM sovereign_benchmarks LIMIT 200"
        )
        for tenor, yld, auc_date, src in cur.fetchall() or []:
            source_str = str(src or "").strip()
            val = _valid_finite(yld)
            as_of_iso = _valid_past_or_today_iso(auc_date, today)
            if (
                tenor
                and source_str == "RBI_AUCTION_CUTOFF"
                and val is not None
                and as_of_iso
                and not has_forbidden_vendor_token(source_str)
            ):
                instrument_candidates.append({
                    "instrument_id": f"GOI_{str(tenor).strip()}",
                    "asset_class": "SOVEREIGN",
                    "measure_type": "AUCTION_CUTOFF_YIELD",
                    "value_pct": val,
                    "as_of": as_of_iso,
                    "source_name": source_str,
                    "source_url": None,
                })

        # 2. Corporate debt metadata_json quoted_ytm observations (if already reviewed)
        cur.execute(
            "SELECT isin, maturity_date, metadata_json FROM corporate_debt_securities LIMIT 500"
        )
        for isin, mat_raw, meta_raw in cur.fetchall() or []:
            try:
                meta = json.loads(meta_raw or "{}")
            except Exception as exc:
                logger.warning("Invalid metadata_json on debt %s: %s", isin, exc)
                continue
            val = _valid_finite(meta.get("quoted_ytm_pct"))
            as_of_iso = _valid_past_or_today_iso(meta.get("quoted_ytm_as_of"), today)
            src_url = str(meta.get("quoted_ytm_source") or "").strip()
            if (
                isin
                and val is not None
                and as_of_iso
                and src_url
                and not has_forbidden_vendor_token(src_url)
            ):
                ytm_years = _valid_finite(meta.get("quoted_years_to_maturity"))
                if ytm_years is None and mat_raw:
                    try:
                        mat_d = date.fromisoformat(str(mat_raw)[:10])
                        ytm_years = round((mat_d - date.fromisoformat(as_of_iso)).days / 365.25, 6)
                    except ValueError:
                        ytm_years = None
                debt_candidates.append({
                    "isin": str(isin).strip().upper(),
                    "ytm_pct": val,
                    "as_of": as_of_iso,
                    "source_url": src_url,
                    "years_to_maturity": ytm_years,
                })

        if apply:
            for dc in debt_candidates:
                cur.execute(
                    f"""
                    INSERT INTO debt_quote_observations (
                        isin, ytm_pct, as_of, source_url, years_to_maturity, recorded_at
                    ) VALUES ({p}, {p}, {p}, {p}, {p}, {p})
                    ON CONFLICT (isin, as_of, source_url) DO UPDATE SET
                        ytm_pct = EXCLUDED.ytm_pct,
                        years_to_maturity = EXCLUDED.years_to_maturity,
                        recorded_at = EXCLUDED.recorded_at
                    """,
                    (
                        dc["isin"],
                        dc["ytm_pct"],
                        dc["as_of"],
                        dc["source_url"],
                        dc["years_to_maturity"],
                        now_iso,
                    ),
                )
            for ic in instrument_candidates:
                cur.execute(
                    f"""
                    INSERT INTO instrument_metric_observations (
                        instrument_id, asset_class, measure_type, value_pct,
                        as_of, source_name, source_url, recorded_at
                    ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                    ON CONFLICT (instrument_id, asset_class, measure_type, as_of, source_name) DO UPDATE SET
                        value_pct = EXCLUDED.value_pct,
                        source_url = EXCLUDED.source_url,
                        recorded_at = EXCLUDED.recorded_at
                    """,
                    (
                        ic["instrument_id"],
                        ic["asset_class"],
                        ic["measure_type"],
                        ic["value_pct"],
                        ic["as_of"],
                        ic["source_name"],
                        ic["source_url"],
                        now_iso,
                    ),
                )
            conn.commit()

        return {
            "applied": apply,
            "debt_quote_observations_count": len(debt_candidates),
            "instrument_metric_observations_count": len(instrument_candidates),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist backfilled observations.")
    args = parser.parse_args()
    result = backfill_terminal_observations(apply=args.apply)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
