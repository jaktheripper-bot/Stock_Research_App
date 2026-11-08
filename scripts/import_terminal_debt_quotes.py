"""Preview or import reviewed quoted YTM observations for existing debt ISINs."""

import argparse
from datetime import date, datetime
import json
import math
import re
from pathlib import Path
import sys
from urllib.parse import urlsplit

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


def import_quotes(records, *, apply=False):
    """Update only quote provenance in debt_quote_observations and metadata_json without clobbering catalogue fields."""
    if not isinstance(records, list) or not records:
        raise ValueError("Expected a nonempty JSON array of source observations.")
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    postgres = is_postgres_connection(conn)
    p = "%s" if postgres else "?"
    lock = " FOR UPDATE" if apply and postgres else ""
    seen = set()
    preview = []
    today = datetime.now(IST).date()
    now_iso = datetime.now(IST).isoformat()
    try:
        if apply and not postgres:
            if get_configured_supabase_url():
                raise RuntimeError("Configured PostgreSQL is unavailable.")
            cur.execute("BEGIN IMMEDIATE")
        for record in sorted(records, key=lambda item: str(item.get("isin", "")).strip().upper()):
            isin = str(record.get("isin", "")).strip().upper()
            quoted_at = date.fromisoformat(str(record.get("as_of", "")))
            source = str(record.get("source_url", "")).strip()
            url = urlsplit(source)
            value = record.get("ytm_pct")
            if (
                not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin)
                or isin in seen
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or quoted_at > today
                or url.scheme != "https"
                or not url.hostname
                or not url.path.strip("/")
                or url.username
                or url.password
                or has_forbidden_vendor_token(source)
            ):
                raise ValueError(f"Invalid or duplicate quote observation for {isin}.")
            seen.add(isin)
            cur.execute(
                f"SELECT maturity_date, metadata_json FROM corporate_debt_securities WHERE isin={p}{lock}",
                (isin,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Unknown debt ISIN {isin}.")
            maturity = date.fromisoformat(str(row[0]))
            if maturity <= today:
                raise ValueError(f"Debt security {isin} has matured.")
            metadata = json.loads(row[1] or "{}")
            previous_date = metadata.get("quoted_ytm_as_of")
            if previous_date and date.fromisoformat(str(previous_date)) > quoted_at:
                raise ValueError(f"A newer quote is already recorded for {isin}.")

            cur.execute(
                f"SELECT MAX(as_of) FROM debt_quote_observations WHERE isin={p}",
                (isin,),
            )
            obs_row = cur.fetchone()
            if obs_row and obs_row[0] and date.fromisoformat(str(obs_row[0])) > quoted_at:
                raise ValueError(f"A newer dedicated quote observation is already recorded for {isin}.")

            years_to_maturity = round((maturity - quoted_at).days / 365.25, 6)
            metadata.update(
                quoted_ytm_pct=float(value),
                quoted_ytm_as_of=quoted_at.isoformat(),
                quoted_ytm_source=source,
                quoted_years_to_maturity=years_to_maturity,
            )
            if apply:
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
                    (isin, float(value), quoted_at.isoformat(), source, years_to_maturity, now_iso),
                )
                cur.execute(
                    f"UPDATE corporate_debt_securities SET metadata_json={p} WHERE isin={p}",
                    (json.dumps(metadata, allow_nan=False), isin),
                )
            preview.append({
                "isin": isin,
                "ytm_pct": float(value),
                "as_of": quoted_at.isoformat(),
                "years_to_maturity": years_to_maturity,
                "source_url": source,
            })
        if apply:
            conn.commit()
        return preview
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("quotes", type=Path, help="JSON array with isin, ytm_pct, as_of and source_url.")
    parser.add_argument("--apply", action="store_true", help="Write reviewed observations to the configured database.")
    args = parser.parse_args()
    print(json.dumps(import_quotes(json.loads(args.quotes.read_text(encoding="utf-8")), apply=args.apply), indent=2))


if __name__ == "__main__":
    main()
