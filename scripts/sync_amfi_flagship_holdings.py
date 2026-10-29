#!/usr/bin/env python3
"""
Audits and purges static-seed-cloned mutual fund holdings and forensic dossiers
on numeric AMFI scheme codes, and deduplicates constituent holding rows so
un-ingested AMFI funds cleanly fail closed to Pending (AGENTS.md Rule 4 & 7).
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ENABLE_BACKGROUND_SCHEDULERS"] = "0"

from core.db.connection import (
    _get_raw_connection,
    get_db_connection,
    get_db_path,
    get_placeholder,
    is_postgres_connection,
)
from core.db.mutual_funds import normalize_scheme_stem


def _norm_scheme_stem(name: str) -> str:
    return normalize_scheme_stem(name)


def _purge_seeded_clones_on_cursor(
    cur, ph: str, is_pg: bool = False, apply: bool = False, verbose: bool = True
) -> Dict[str, int]:
    """Detects and removes static-seed-cloned numeric AMFI holdings/dossiers and duplicate holding rows."""
    # 1. Identify numeric AMFI schemes whose exact holding vector matches a non-numeric seeded slug scheme
    cur.execute(
        """
        SELECT DISTINCT scheme_code, holding_type, identifier, weight_pct
        FROM mutual_fund_holdings
        ORDER BY scheme_code, holding_type, identifier
        """
    )
    vecs: Dict[str, list] = {}
    for sc, ht, ident, w in cur.fetchall():
        vecs.setdefault(str(sc), []).append((str(ht or "").upper(), str(ident or "").upper(), round(float(w or 0.0), 2)))

    slug_fingerprints = {tuple(v): sc for sc, v in vecs.items() if v and not sc.isdigit()}
    cloned_numeric_codes = sorted(
        sc for sc, v in vecs.items() if sc.isdigit() and tuple(v) in slug_fingerprints
    )

    # 2. Identify numeric AMFI forensic dossiers whose text was cloned verbatim from a slug dossier
    if is_pg:
        cur.execute(
            """
            SELECT d.scheme_code
            FROM fund_forensic_dossiers d
            WHERE d.scheme_code ~ '^[0-9]+$'
              AND EXISTS (
                  SELECT 1 FROM fund_forensic_dossiers slug
                  WHERE slug.scheme_code !~ '^[0-9]+$'
                    AND slug.dossier_text = d.dossier_text
              )
            ORDER BY d.scheme_code
            """
        )
    else:
        cur.execute(
            """
            SELECT d.scheme_code
            FROM fund_forensic_dossiers d
            WHERE d.scheme_code GLOB '[0-9]*'
              AND EXISTS (
                  SELECT 1 FROM fund_forensic_dossiers slug
                  WHERE slug.scheme_code NOT GLOB '[0-9]*'
                    AND slug.dossier_text = d.dossier_text
              )
            ORDER BY d.scheme_code
            """
        )
    cloned_dossier_codes = [str(r[0]) for r in cur.fetchall()]

    # 3. Count excess duplicate holding rows (stale portfolio_date or duplicate holding_type+identifier)
    cur.execute(
        """
        SELECT COUNT(*) FROM mutual_fund_holdings h
        WHERE h.portfolio_date < (
            SELECT MAX(h2.portfolio_date)
            FROM mutual_fund_holdings h2
            WHERE h2.scheme_code = h.scheme_code
        )
        """
    )
    stale_date_rows = int((cur.fetchone() or [0])[0] or 0)

    cur.execute(
        """
        SELECT COUNT(*) FROM mutual_fund_holdings
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM mutual_fund_holdings
            GROUP BY scheme_code, holding_type, identifier
        )
        """
    )
    dup_rows = int((cur.fetchone() or [0])[0] or 0)

    stats = {
        "cloned_numeric_schemes": len(cloned_numeric_codes),
        "deleted_cloned_holdings": 0,
        "deleted_cloned_dossiers": len(cloned_dossier_codes) if not apply else 0,
        "reset_scheme_metadata": 0,
        "deduped_holding_rows": stale_date_rows + dup_rows if not apply else 0,
    }

    if verbose:
        mode = "APPLY" if apply else "DRY-RUN"
        print(
            f"[{mode}] Cloned numeric AMFI schemes={len(cloned_numeric_codes)} | "
            f"Cloned dossiers={len(cloned_dossier_codes)} | "
            f"Stale-date rows={stale_date_rows} | Duplicate rows={dup_rows}"
        )

    if not apply:
        return stats

    affected_codes = sorted(set(cloned_numeric_codes) | set(cloned_dossier_codes))

    if cloned_numeric_codes:
        in_ph = ",".join([ph] * len(cloned_numeric_codes))
        cur.execute(
            f"DELETE FROM mutual_fund_holdings WHERE scheme_code IN ({in_ph})",
            tuple(cloned_numeric_codes),
        )
        stats["deleted_cloned_holdings"] = int(cur.rowcount or 0)

    if cloned_dossier_codes:
        in_ph = ",".join([ph] * len(cloned_dossier_codes))
        cur.execute(
            f"DELETE FROM fund_forensic_dossiers WHERE scheme_code IN ({in_ph})",
            tuple(cloned_dossier_codes),
        )
        stats["deleted_cloned_dossiers"] = int(cur.rowcount or 0)

    if affected_codes:
        in_ph = ",".join([ph] * len(affected_codes))
        if is_pg:
            cur.execute(
                f"""
                UPDATE mutual_fund_schemes
                SET aum_crores = 0.0,
                    active_share_pct = 0.0,
                    fund_manager = 'Pending Monthly Fact Sheet Sync',
                    metadata_json = '{{}}',
                    last_portfolio_date = COALESCE(last_updated::date, CURRENT_DATE)
                WHERE scheme_code IN ({in_ph})
                  AND NOT EXISTS (
                      SELECT 1 FROM mutual_fund_holdings h WHERE h.scheme_code = mutual_fund_schemes.scheme_code
                  )
                """,
                tuple(affected_codes),
            )
        else:
            cur.execute(
                f"""
                UPDATE mutual_fund_schemes
                SET aum_crores = 0.0,
                    active_share_pct = 0.0,
                    fund_manager = 'Pending Monthly Fact Sheet Sync',
                    metadata_json = '{{}}',
                    last_portfolio_date = 'Pending Monthly Disclosure'
                WHERE scheme_code IN ({in_ph})
                  AND NOT EXISTS (
                      SELECT 1 FROM mutual_fund_holdings h WHERE h.scheme_code = mutual_fund_schemes.scheme_code
                  )
                """,
                tuple(affected_codes),
            )
        stats["reset_scheme_metadata"] = int(cur.rowcount or 0)

    cur.execute(
        """
        DELETE FROM mutual_fund_holdings
        WHERE portfolio_date < (
            SELECT MAX(h2.portfolio_date)
            FROM mutual_fund_holdings h2
            WHERE h2.scheme_code = mutual_fund_holdings.scheme_code
        )
        """
    )
    removed_stale = int(cur.rowcount or 0)

    cur.execute(
        """
        DELETE FROM mutual_fund_holdings
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM mutual_fund_holdings
            GROUP BY scheme_code, holding_type, identifier
        )
        """
    )
    removed_dups = int(cur.rowcount or 0)
    stats["deduped_holding_rows"] = removed_stale + removed_dups

    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mf_holdings_scheme_type_ident
            ON mutual_fund_holdings (scheme_code, holding_type, identifier)
        """
    )
    cur.execute("SAVEPOINT sp_mig")
    try:
        cur.execute(
            "INSERT INTO schema_migrations (version) VALUES ('v038_mf_holdings_unique_index') ON CONFLICT DO NOTHING"
        )
        cur.execute("RELEASE SAVEPOINT sp_mig")
    except Exception as mig_err:
        cur.execute("ROLLBACK TO SAVEPOINT sp_mig")
        if verbose:
            print(f"[NOTICE] schema_migrations update skipped: {mig_err}")
    return stats


def purge_seeded_amfi_clones(apply: bool = False) -> Dict[str, int]:
    ph = get_placeholder()
    conn_factory = get_db_connection if apply else _get_raw_connection
    with conn_factory() as conn:
        is_pg = is_postgres_connection(conn)
        cur = conn.cursor()
        try:
            stats = _purge_seeded_clones_on_cursor(cur, ph, is_pg=is_pg, apply=apply, verbose=True)
            if apply:
                conn.commit()
            else:
                conn.rollback()
        finally:
            cur.close()

        if apply and is_pg:
            sq_path = Path(get_db_path())
            if sq_path.exists():
                sq_conn = sqlite3.connect(str(sq_path))
                sq_cur = sq_conn.cursor()
                try:
                    _purge_seeded_clones_on_cursor(sq_cur, "?", is_pg=False, apply=True, verbose=True)
                    sq_conn.commit()
                finally:
                    sq_cur.close()
                    sq_conn.close()

    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    purge_seeded_amfi_clones(apply=bool(args.apply and not args.dry_run))
