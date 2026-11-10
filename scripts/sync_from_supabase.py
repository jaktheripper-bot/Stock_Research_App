#!/usr/bin/env python3
"""
Pull multi-asset research tables from Supabase (PostgreSQL or PostgREST) into local SQLite (reports.db).

Guarantees:
1. Single short-lived PostgreSQL socket (never allocates a multi-connection pool against Supavisor).
2. Strict Asia/Kolkata (+05:30) timestamp normalization for all SQLite timestamp columns.
3. Freshness-aware & anti-Potemkin merge: never overwrites a newer local row or replaces a compiled
   dossier/report with an empty/stub payload unless --force is passed.
4. Natural-key matching for dual-autoincrement tables (discovery_reel, report_revisions, mutual_fund_holdings)
   to prevent serial ID collisions or duplicate cohorts.
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_secret
from core.db.connection import IST, _normalize_pg_dsn, get_db_path
from core.presentation.formatters import _coerce_datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_from_supabase")

# (table_name, key_cols, ts_col, mode)
# mode="upsert": target table has a UNIQUE/PK index on key_cols in SQLite
# mode="edition_cohort": discovery_reel synced atomically per edition_date cohort
# mode="natural_no_uniq": report_revisions matched by (ticker, timestamp) in Python
SYNC_TABLE_SPECS: List[Tuple[str, Tuple[str, ...], Optional[str], str]] = [
    ("reports", ("ticker",), "timestamp", "upsert"),
    ("report_revisions", ("ticker", "timestamp"), "timestamp", "natural_no_uniq"),
    ("cached_fundamentals", ("ticker",), "updated_at", "upsert"),
    ("discovery_reel", ("edition_date", "ticker"), "created_at", "edition_cohort"),
    ("mutual_fund_schemes", ("scheme_code",), "last_updated", "upsert"),
    ("mutual_fund_holdings", ("scheme_code", "holding_type", "identifier"), "created_at", "scheme_cohort"),
    ("fund_forensic_dossiers", ("scheme_code",), "last_audited_at", "upsert"),
    ("corporate_debt_securities", ("isin",), "last_updated", "upsert"),
    ("sovereign_benchmarks", ("tenor_label",), "updated_at", "upsert"),
    ("sovereign_curve_history", ("snapshot_key", "tenor_label"), None, "upsert"),
    ("sovereign_sdl_spreads", ("state_name",), "updated_at", "upsert"),
    ("sovereign_macro_rates", ("metric_key",), "updated_at", "upsert"),
    ("reits_and_invits", ("symbol",), "updated_at", "upsert"),
    ("sgb_tranches", ("symbol",), "updated_at", "upsert"),
    ("alternative_yield_products", ("product_id",), "updated_at", "upsert"),
    ("etf_matrix", ("symbol",), "updated_at", "upsert"),
    ("msme_firms", ("uin",), "last_updated", "upsert"),
    ("equity_price_history_cache", ("ticker", "period"), "updated_at", "upsert"),
    ("savings_override_audit_log", ("override_id",), "created_at", "upsert"),
    ("savings_rate_observations", ("observation_id",), "observed_at", "upsert"),
    ("savings_instruments", ("instrument_id",), "updated_at", "upsert"),
    ("tax_rule_registry", ("rule_version",), "updated_at", "upsert"),
]


def connect_supabase_pg(db_url: str):
    """Opens a single short-lived PostgreSQL connection in Asia/Kolkata timezone with IPv4 pooler fallback."""
    import psycopg2

    norm_url = _normalize_pg_dsn(db_url)
    conn = None
    try:
        conn = psycopg2.connect(norm_url, connect_timeout=10)
    except psycopg2.OperationalError as op_err:
        if "could not translate host name" in str(op_err) and "db." in db_url and ".supabase.co" in db_url:
            logger.warning("Direct Supabase host unreachable on this network; trying IPv4 session poolers...")
            m = re.search(r"postgresql://([^:]+):([^@]+)@db\.([^\.]+)\.supabase\.co:(\d+)/(.+)", db_url)
            if m:
                user, password, project_ref, _port, dbname = m.groups()
                dbname_clean = dbname.split("?")[0]
                for region in ("ap-southeast-1", "ap-south-1", "us-east-1", "eu-central-1"):
                    pooler_url = _normalize_pg_dsn(
                        f"postgresql://{user}.{project_ref}:{password}@aws-0-{region}.pooler.supabase.com:5432/{dbname_clean}"
                    )
                    try:
                        conn = psycopg2.connect(pooler_url, connect_timeout=5)
                        logger.info("Connected to Supabase via IPv4 pooler (%s).", region)
                        break
                    except Exception as region_err:
                        logger.debug("Pooler probe (%s) notice: %s", region, region_err)
                if conn is None:
                    raise op_err
            else:
                raise op_err
        else:
            raise op_err

    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'Asia/Kolkata';")
    conn.commit()
    return conn


def normalize_pg_value_for_sqlite(val: Any) -> Any:
    """Converts psycopg2 Python return types into SQLite-native values adhering to the IST invariant."""
    if val is None:
        return None
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, datetime):
        ist_dt = val.astimezone(IST) if val.tzinfo is not None else val.replace(tzinfo=IST)
        return ist_dt.strftime("%Y-%m-%d %H:%M:%S+05:30")
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return val


def _canonical_key(table_name: str, key_cols: Tuple[str, ...], row_dict: Dict[str, Any]) -> Tuple[Any, ...]:
    """Builds a normalized lookup tuple for matching rows across PostgreSQL and SQLite."""
    parts: List[Any] = []
    for col in key_cols:
        raw = row_dict.get(col)
        if table_name == "report_revisions" and col == "timestamp":
            dt = _coerce_datetime(raw)
            parts.append(int(dt.timestamp()) if dt is not None else str(raw or "").strip())
        elif table_name == "discovery_reel" and col == "edition_date":
            parts.append(str(raw or "").strip()[:10])
        elif col == "revision_seq":
            parts.append(int(raw if raw is not None else 1))
        elif isinstance(raw, str):
            parts.append(raw.strip())
        else:
            parts.append(raw)
    return tuple(parts)


def should_apply_incoming_row(
    table_name: str,
    incoming: Dict[str, Any],
    existing: Optional[Dict[str, Any]],
    ts_col: Optional[str],
    force: bool = False,
) -> bool:
    """Determines whether an incoming Supabase row should insert/overwrite the local SQLite row."""
    if table_name == "reports":
        inc_len = len(str(incoming.get("report_text") or "").strip())
        if existing is None:
            return inc_len > 0
        ex_len = len(str(existing.get("report_text") or "").strip())
        if ex_len >= 500 and inc_len < 500:
            return False
        if ex_len < 500 and inc_len >= 500:
            return True

    if table_name == "fund_forensic_dossiers":
        inc_has_dossier = bool(str(incoming.get("dossier_text") or "").strip())
        if existing is not None:
            ex_has_dossier = bool(str(existing.get("dossier_text") or "").strip())
            if ex_has_dossier and not inc_has_dossier:
                return False
            if not ex_has_dossier and inc_has_dossier:
                return True

    if table_name == "savings_instruments":
        from core.db.savings import is_valid_savings_provenance

        if not is_valid_savings_provenance(incoming):
            logger.warning(
                "Rejected incoming savings_instruments row %s failing official provenance validation.",
                incoming.get("instrument_id"),
            )
            return False
    elif table_name == "tax_rule_registry":
        from core.db.savings import validate_tax_rule_provenance

        try:
            validate_tax_rule_provenance(incoming)
        except ValueError as tv_err:
            logger.warning("Rejected incoming tax_rule_registry row failing provenance check: %s", tv_err)
            return False
    elif table_name == "savings_override_audit_log":
        if not str(incoming.get("operator_id") or "").strip() or len(str(incoming.get("override_reason") or "").strip()) < 8:
            logger.warning("Rejected incoming savings_override_audit_log row missing operator_id or override_reason.")
            return False
        return existing is None
    elif table_name == "savings_rate_observations":
        from core.db.savings import validate_observation_provenance

        try:
            validate_observation_provenance(incoming)
        except ValueError as obs_err:
            logger.warning("Rejected incoming savings_rate_observations row failing provenance check: %s", obs_err)
            return False
        if existing is None:
            return True
        needs_eff_to = not existing.get("effective_to") and bool(incoming.get("effective_to"))
        needs_superseded = not existing.get("superseded_at") and bool(incoming.get("superseded_at"))
        needs_sup_by = not existing.get("superseded_by_observation_id") and bool(
            incoming.get("superseded_by_observation_id")
        )
        needs_status_upgrade = (
            str(existing.get("observation_status") or "") != str(incoming.get("observation_status") or "")
            and str(incoming.get("observation_status") or "")
            in ("SUPERSEDED", "SUPERSEDED_CONFLICT", "HISTORICAL", "ACTIVE")
        )
        return bool(needs_eff_to or needs_superseded or needs_sup_by or needs_status_upgrade)

    if existing is None:
        return True

    if force:
        return True

    if table_name == "savings_instruments":
        inc_epoch = int(incoming.get("override_epoch") or 0)
        ex_epoch = int(existing.get("override_epoch") or 0)
        if inc_epoch > ex_epoch:
            return True
        if inc_epoch < ex_epoch:
            return False
        inc_eff = str(incoming.get("effective_from") or "").strip()[:10]
        ex_eff = str(existing.get("effective_from") or "").strip()[:10]
        if inc_eff and ex_eff:
            if inc_eff < ex_eff:
                return False
            if inc_eff > ex_eff:
                return True
            inc_act_obs = str(incoming.get("active_observation_id") or "").strip()
            ex_act_obs = str(existing.get("active_observation_id") or "").strip()
            if inc_act_obs and ex_act_obs and inc_act_obs != ex_act_obs:
                # Authoritative PostgreSQL active_observation_id differs on same effective_from;
                # caller checks whether local causally superseded remote or if PG wins split-brain.
                return True
            inc_rate = float(incoming.get("base_rate_pct") or 0.0)
            ex_rate = float(existing.get("base_rate_pct") or 0.0)
            inc_bonus = float(incoming.get("senior_citizen_bonus_bps") or 0.0)
            ex_bonus = float(existing.get("senior_citizen_bonus_bps") or 0.0)
            if abs(inc_rate - ex_rate) >= 1e-6 or abs(inc_bonus - ex_bonus) >= 1e-6:
                inc_dt_s = _coerce_datetime(incoming.get(ts_col)) if ts_col else None
                ex_dt_s = _coerce_datetime(existing.get(ts_col)) if ts_col else None
                if inc_dt_s is None or ex_dt_s is None or inc_dt_s >= ex_dt_s:
                    return True

    if ts_col:
        inc_dt = _coerce_datetime(incoming.get(ts_col))
        ex_dt = _coerce_datetime(existing.get(ts_col))
        if inc_dt is not None and ex_dt is not None:
            return (inc_dt - ex_dt).total_seconds() > 1.0
        if inc_dt is not None and ex_dt is None:
            return True
        if inc_dt is None and ex_dt is not None:
            return False

    # For non-timestamped tables (e.g. sovereign_curve_history), update only if a non-id value differs
    for col, inc_val in incoming.items():
        if col == "id":
            continue
        ex_val = existing.get(col)
        if isinstance(inc_val, float) and isinstance(ex_val, (int, float)):
            if abs(inc_val - float(ex_val)) > 1e-6:
                return True
        elif inc_val != ex_val:
            return True
    return False


def _ensure_local_sqlite_schema(sqlite_path: str) -> None:
    """Initializes local SQLite schema if the target file is new or missing core/v051 tables."""
    need_init = not os.path.exists(sqlite_path)
    if not need_init:
        conn = sqlite3.connect(sqlite_path)
        try:
            existing_tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            need_init = not all(spec[0] in existing_tables for spec in SYNC_TABLE_SPECS)
            if not need_init:
                obs_cols = {
                    r[1] for r in conn.execute("PRAGMA table_info(savings_rate_observations)").fetchall()
                }
                inst_cols = {
                    r[1] for r in conn.execute("PRAGMA table_info(savings_instruments)").fetchall()
                }
                if "observation_id" not in obs_cols or "override_epoch" not in inst_cols:
                    need_init = True
        finally:
            conn.close()

    if need_init:
        import core.db.connection as db_conn

        prev_db_path = os.environ.get("DB_PATH")
        prev_test_db_path = os.environ.get("TEST_DB_PATH")
        prev_force_sqlite = os.environ.get("FORCE_LOCAL_SQLITE")
        prev_sb_url = os.environ.get("SUPABASE_DB_URL")
        prev_cached = db_conn._CACHED_SUPABASE_URL
        prev_resolved = db_conn._SUPABASE_URL_RESOLVED
        try:
            os.environ["DB_PATH"] = sqlite_path
            os.environ["TEST_DB_PATH"] = sqlite_path
            os.environ["FORCE_LOCAL_SQLITE"] = "1"
            os.environ["SUPABASE_DB_URL"] = ""
            db_conn._CACHED_SUPABASE_URL = ""
            db_conn._SUPABASE_URL_RESOLVED = True
            db_conn.init_db(force=True)
        finally:
            if prev_db_path is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = prev_db_path
            if prev_test_db_path is None:
                os.environ.pop("TEST_DB_PATH", None)
            else:
                os.environ["TEST_DB_PATH"] = prev_test_db_path
            if prev_force_sqlite is None:
                os.environ.pop("FORCE_LOCAL_SQLITE", None)
            else:
                os.environ["FORCE_LOCAL_SQLITE"] = prev_force_sqlite
            if prev_sb_url is None:
                os.environ.pop("SUPABASE_DB_URL", None)
            else:
                os.environ["SUPABASE_DB_URL"] = prev_sb_url
            db_conn._CACHED_SUPABASE_URL = prev_cached
            db_conn._SUPABASE_URL_RESOLVED = prev_resolved


def sync_via_postgresql_pull(
    sqlite_path: str,
    db_url: str,
    dry_run: bool = False,
    force: bool = False,
    selected_tables: Optional[List[str]] = None,
) -> Dict[str, Dict[str, int]]:
    """Pulls multi-asset tables from Supabase PostgreSQL into local SQLite."""
    from psycopg2.extras import RealDictCursor

    if not dry_run:
        _ensure_local_sqlite_schema(sqlite_path)

    pg_conn = connect_supabase_pg(db_url)
    sqlite_conn = sqlite3.connect(sqlite_path, timeout=30.0)
    sqlite_conn.row_factory = sqlite3.Row

    summary: Dict[str, Dict[str, int]] = {}
    preserve_non_empty = {"report_text", "citations_json", "dossier_text"}
    allowed_set = {t.strip() for t in selected_tables if t.strip()} if selected_tables else None

    try:
        try:
            sqlite_conn.execute("PRAGMA journal_mode=WAL;")
            sqlite_conn.execute("PRAGMA busy_timeout = 5000;")
        except Exception as pragma_err:
            logger.debug("SQLite PRAGMA notice: %s", pragma_err)

        with pg_conn.cursor(cursor_factory=RealDictCursor) as pg_cur:
            for table_name, key_cols, ts_col, mode in SYNC_TABLE_SPECS:
                if allowed_set is not None and table_name not in allowed_set:
                    continue

                stats = {"remote_rows": 0, "inserted": 0, "updated": 0, "skipped_fresh": 0}
                try:
                    sq_cols_info = sqlite_conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                    if not sq_cols_info:
                        logger.warning("Local SQLite table '%s' missing; skipping.", table_name)
                        summary[table_name] = stats
                        continue
                    sq_cols = [r[1] for r in sq_cols_info]
                    has_auto_id = "id" in sq_cols and "id" not in key_cols

                    pg_cur.execute(f"SELECT * FROM {table_name}")
                    remote_rows = pg_cur.fetchall()
                    stats["remote_rows"] = len(remote_rows)
                    if not remote_rows:
                        summary[table_name] = stats
                        continue

                    local_rows = [dict(r) for r in sqlite_conn.execute(f"SELECT * FROM {table_name}").fetchall()]
                    local_index: Dict[Tuple[Any, ...], Dict[str, Any]] = {
                        _canonical_key(table_name, key_cols, lr): lr for lr in local_rows
                    }

                    write_cols = [c for c in sq_cols if not (has_auto_id and c == "id") and c in remote_rows[0]]
                    sq_cur = sqlite_conn.cursor()

                    if mode == "edition_cohort":
                        remote_by_ed: Dict[str, List[Dict[str, Any]]] = {}
                        for raw_remote in remote_rows:
                            inc = {c: normalize_pg_value_for_sqlite(raw_remote.get(c)) for c in write_cols}
                            ed_key = str(inc.get("edition_date") or "").strip()[:10]
                            if ed_key:
                                remote_by_ed.setdefault(ed_key, []).append(inc)

                        local_by_ed: Dict[str, List[Dict[str, Any]]] = {}
                        for lr in local_rows:
                            ed_key = str(lr.get("edition_date") or "").strip()[:10]
                            if ed_key:
                                local_by_ed.setdefault(ed_key, []).append(lr)

                        cols_sql = ", ".join(write_cols)
                        placeholders = ", ".join(["?"] * len(write_cols))
                        ins_sql = f"INSERT INTO {table_name} ({cols_sql}) VALUES ({placeholders})"

                        for ed_key, r_cohort in remote_by_ed.items():
                            l_cohort = local_by_ed.get(ed_key)
                            if not l_cohort:
                                if not dry_run:
                                    sq_cur.executemany(
                                        ins_sql,
                                        [tuple(item[c] for c in write_cols) for item in r_cohort],
                                    )
                                stats["inserted"] += len(r_cohort)
                                continue

                            r_tickers = {str(x.get("ticker") or "").strip().upper() for x in r_cohort}
                            l_tickers = {str(x.get("ticker") or "").strip().upper() for x in l_cohort}
                            r_max_dt = max(
                                (_coerce_datetime(x.get("created_at")) for x in r_cohort if _coerce_datetime(x.get("created_at"))),
                                default=None,
                            )
                            l_max_dt = max(
                                (_coerce_datetime(x.get("created_at")) for x in l_cohort if _coerce_datetime(x.get("created_at"))),
                                default=None,
                            )
                            is_remote_newer = force or (
                                r_max_dt is not None and (l_max_dt is None or (r_max_dt - l_max_dt).total_seconds() > 1.0)
                            )
                            if r_tickers == l_tickers and len(r_cohort) == len(l_cohort) and not force:
                                stats["skipped_fresh"] += len(r_cohort)
                                continue
                            if is_remote_newer:
                                if not dry_run:
                                    sq_cur.execute(
                                        f"DELETE FROM {table_name} WHERE substr(edition_date, 1, 10) = ?",
                                        (ed_key,),
                                    )
                                    sq_cur.executemany(
                                        ins_sql,
                                        [tuple(item[c] for c in write_cols) for item in r_cohort],
                                    )
                                stats["updated"] += len(r_cohort)
                            else:
                                stats["skipped_fresh"] += len(r_cohort)

                        if not dry_run:
                            sqlite_conn.commit()
                        summary[table_name] = stats
                        logger.info(
                            "Table %-27s | remote=%4d | inserted=%4d | updated=%4d | unchanged=%4d%s",
                            table_name,
                            stats["remote_rows"],
                            stats["inserted"],
                            stats["updated"],
                            stats["skipped_fresh"],
                            " (DRY-RUN)" if dry_run else "",
                        )
                        continue

                    if mode == "scheme_cohort":
                        remote_by_sc: Dict[str, Dict[Tuple[Any, ...], Dict[str, Any]]] = {}
                        for raw_remote in remote_rows:
                            inc = {c: normalize_pg_value_for_sqlite(raw_remote.get(c)) for c in write_cols}
                            sc_key = str(inc.get("scheme_code") or "").strip()
                            if sc_key:
                                remote_by_sc.setdefault(sc_key, {})[_canonical_key(table_name, key_cols, inc)] = inc

                        local_by_sc: Dict[str, List[Dict[str, Any]]] = {}
                        for lr in local_rows:
                            sc_key = str(lr.get("scheme_code") or "").strip()
                            if sc_key:
                                local_by_sc.setdefault(sc_key, []).append(lr)

                        cols_sql = ", ".join(write_cols)
                        placeholders = ", ".join(["?"] * len(write_cols))
                        ins_sql = f"INSERT INTO {table_name} ({cols_sql}) VALUES ({placeholders})"

                        for sc_key, r_cohort_map in remote_by_sc.items():
                            r_cohort = list(r_cohort_map.values())
                            l_cohort = local_by_sc.get(sc_key)
                            if not l_cohort:
                                if not dry_run:
                                    sq_cur.executemany(
                                        ins_sql,
                                        [tuple(item[c] for c in write_cols) for item in r_cohort],
                                    )
                                stats["inserted"] += len(r_cohort)
                                continue

                            r_keys = {_canonical_key(table_name, key_cols, x) for x in r_cohort}
                            l_keys = {_canonical_key(table_name, key_cols, x) for x in l_cohort}
                            r_max_dt = max(
                                (_coerce_datetime(x.get("created_at")) for x in r_cohort if _coerce_datetime(x.get("created_at"))),
                                default=None,
                            )
                            l_max_dt = max(
                                (_coerce_datetime(x.get("created_at")) for x in l_cohort if _coerce_datetime(x.get("created_at"))),
                                default=None,
                            )
                            is_remote_newer = force or (
                                r_max_dt is not None and (l_max_dt is None or (r_max_dt - l_max_dt).total_seconds() > 1.0)
                            )
                            if r_keys == l_keys and len(r_cohort) == len(l_cohort) and not is_remote_newer and not force:
                                stats["skipped_fresh"] += len(r_cohort)
                                continue
                            if is_remote_newer:
                                if not dry_run:
                                    sq_cur.execute(
                                        f"DELETE FROM {table_name} WHERE scheme_code = ?",
                                        (sc_key,),
                                    )
                                    sq_cur.executemany(
                                        ins_sql,
                                        [tuple(item[c] for c in write_cols) for item in r_cohort],
                                    )
                                stats["updated"] += len(r_cohort)
                            else:
                                stats["skipped_fresh"] += len(r_cohort)

                        if not dry_run:
                            sqlite_conn.commit()
                        summary[table_name] = stats
                        logger.info(
                            "Table %-27s | remote=%4d | inserted=%4d | updated=%4d | unchanged=%4d%s",
                            table_name,
                            stats["remote_rows"],
                            stats["inserted"],
                            stats["updated"],
                            stats["skipped_fresh"],
                            " (DRY-RUN)" if dry_run else "",
                        )
                        continue

                    # Preload local observation causal chain when pulling savings_instruments
                    local_obs_sup_chain: Dict[str, Optional[str]] = {}
                    if table_name == "savings_instruments":
                        try:
                            for orow in sqlite_conn.execute(
                                "SELECT observation_id, superseded_by_observation_id FROM savings_rate_observations"
                            ).fetchall():
                                local_obs_sup_chain[str(orow[0])] = (
                                    str(orow[1]) if orow[1] else None
                                )
                        except Exception as obs_chain_err:
                            logger.debug("Local observation chain notice: %s", obs_chain_err)

                    def _local_causally_superseded(ancestor_oid: str, descendant_oid: str) -> bool:
                        cur_id: Optional[str] = ancestor_oid
                        seen = set()
                        while cur_id and cur_id not in seen and len(seen) < 64:
                            seen.add(cur_id)
                            nxt = local_obs_sup_chain.get(cur_id)
                            if nxt == descendant_oid:
                                return True
                            cur_id = nxt
                        return False

                    now_pull_iso = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S+05:30")

                    for raw_remote in remote_rows:
                        incoming = {
                            c: normalize_pg_value_for_sqlite(raw_remote.get(c))
                            for c in write_cols
                        }
                        k = _canonical_key(table_name, key_cols, incoming)
                        existing = local_index.get(k)

                        if not should_apply_incoming_row(table_name, incoming, existing, ts_col, force=force):
                            stats["skipped_fresh"] += 1
                            continue

                        # Handle causal vs split-brain conflict resolution on savings_instruments
                        if table_name == "savings_instruments" and existing is not None and not force:
                            inc_epoch = int(incoming.get("override_epoch") or 0)
                            ex_epoch = int(existing.get("override_epoch") or 0)
                            inc_eff = str(incoming.get("effective_from") or "")[:10]
                            ex_eff = str(existing.get("effective_from") or "")[:10]
                            inc_act_obs = str(incoming.get("active_observation_id") or "").strip()
                            ex_act_obs = str(existing.get("active_observation_id") or "").strip()

                            if (
                                inc_epoch == ex_epoch
                                and inc_eff == ex_eff
                                and inc_act_obs
                                and ex_act_obs
                                and inc_act_obs != ex_act_obs
                            ):
                                if _local_causally_superseded(inc_act_obs, ex_act_obs):
                                    # Local SQLite has an un-pushed sequential amendment on top of PG's observation
                                    stats["skipped_fresh"] += 1
                                    continue
                                # Otherwise PG causally superseded local OR this is a cross-DB split-brain conflict:
                                # PostgreSQL is authoritative; mark divergent local observation SUPERSEDED_CONFLICT!
                                if not dry_run:
                                    sq_cur.execute(
                                        """
                                        UPDATE savings_rate_observations
                                        SET superseded_at = COALESCE(superseded_at, ?),
                                            superseded_by_observation_id = COALESCE(superseded_by_observation_id, ?),
                                            observation_status = CASE
                                                WHEN superseded_at IS NULL THEN 'SUPERSEDED_CONFLICT'
                                                ELSE observation_status
                                            END
                                        WHERE observation_id = ? AND superseded_at IS NULL
                                        """,
                                        (now_pull_iso, inc_act_obs, ex_act_obs),
                                    )
                                    if sq_cur.rowcount > 0:
                                        stats["conflicts_reconciled"] = (
                                            stats.get("conflicts_reconciled", 0) + sq_cur.rowcount
                                        )
                            elif inc_epoch > ex_epoch and not dry_run and inc_act_obs:
                                sq_cur.execute(
                                    """
                                    UPDATE savings_rate_observations
                                    SET superseded_at = COALESCE(superseded_at, ?),
                                        superseded_by_observation_id = COALESCE(superseded_by_observation_id, ?),
                                        observation_status = 'SUPERSEDED'
                                    WHERE instrument_id = ?
                                      AND superseded_at IS NULL
                                      AND observation_id <> ?
                                      AND effective_from >= ?
                                    """,
                                    (
                                        now_pull_iso,
                                        inc_act_obs,
                                        str(incoming["instrument_id"]),
                                        inc_act_obs,
                                        inc_eff,
                                    ),
                                )

                        # Preserve non-empty local prose/citations when incoming field is blank
                        if existing is not None:
                            for pcol in preserve_non_empty:
                                if pcol in incoming:
                                    inc_str = str(incoming.get(pcol) or "").strip()
                                    ex_str = str(existing.get(pcol) or "").strip()
                                    if not inc_str and ex_str:
                                        incoming[pcol] = existing[pcol]

                        if dry_run:
                            if existing is None:
                                stats["inserted"] += 1
                            else:
                                stats["updated"] += 1
                            continue

                        if mode == "upsert":
                            cols_sql = ", ".join(write_cols)
                            placeholders = ", ".join(["?"] * len(write_cols))
                            conflict_sql = ", ".join(key_cols)
                            if table_name == "savings_rate_observations":
                                sql = (
                                    f"INSERT INTO {table_name} ({cols_sql}) VALUES ({placeholders}) "
                                    f"ON CONFLICT ({conflict_sql}) DO UPDATE SET "
                                    f"effective_to = COALESCE({table_name}.effective_to, excluded.effective_to), "
                                    f"superseded_at = COALESCE({table_name}.superseded_at, excluded.superseded_at), "
                                    f"superseded_by_observation_id = COALESCE("
                                    f"{table_name}.superseded_by_observation_id, excluded.superseded_by_observation_id), "
                                    f"observation_status = CASE "
                                    f"WHEN {table_name}.superseded_at IS NULL AND excluded.superseded_at IS NOT NULL "
                                    f"THEN excluded.observation_status "
                                    f"WHEN {table_name}.observation_status = 'SCHEDULED_FUTURE' "
                                    f"AND excluded.observation_status = 'ACTIVE' THEN 'ACTIVE' "
                                    f"ELSE {table_name}.observation_status END"
                                )
                            elif table_name == "savings_override_audit_log":
                                sql = (
                                    f"INSERT INTO {table_name} ({cols_sql}) VALUES ({placeholders}) "
                                    f"ON CONFLICT ({conflict_sql}) DO NOTHING"
                                )
                            elif table_name == "savings_instruments" and not force:
                                update_cols = [c for c in write_cols if c not in key_cols]
                                update_sql = ", ".join([f"{c} = excluded.{c}" for c in update_cols])
                                sql = (
                                    f"INSERT INTO {table_name} ({cols_sql}) VALUES ({placeholders}) "
                                    f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql} "
                                    f"WHERE COALESCE(excluded.override_epoch, 0) > COALESCE({table_name}.override_epoch, 0) "
                                    f"OR (COALESCE(excluded.override_epoch, 0) = COALESCE({table_name}.override_epoch, 0) "
                                    f"AND ({table_name}.effective_from IS NULL "
                                    f"OR excluded.effective_from >= {table_name}.effective_from))"
                                )
                            else:
                                update_cols = [c for c in write_cols if c not in key_cols]
                                update_sql = ", ".join([f"{c} = excluded.{c}" for c in update_cols])
                                sql = (
                                    f"INSERT INTO {table_name} ({cols_sql}) VALUES ({placeholders}) "
                                    f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}"
                                )
                            sq_cur.execute(sql, tuple(incoming[c] for c in write_cols))
                        else:
                            # natural_no_uniq (discovery_reel, report_revisions)
                            if existing is None:
                                cols_sql = ", ".join(write_cols)
                                placeholders = ", ".join(["?"] * len(write_cols))
                                sql = f"INSERT INTO {table_name} ({cols_sql}) VALUES ({placeholders})"
                                sq_cur.execute(sql, tuple(incoming[c] for c in write_cols))
                            elif "id" in existing and table_name != "report_revisions":
                                update_cols = [c for c in write_cols if c not in key_cols]
                                update_sql = ", ".join([f"{c} = ?" for c in update_cols])
                                sql = f"UPDATE {table_name} SET {update_sql} WHERE id = ?"
                                sq_cur.execute(
                                    sql,
                                    tuple(incoming[c] for c in update_cols) + (existing["id"],),
                                )
                            else:
                                stats["skipped_fresh"] += 1
                                continue

                        if existing is None:
                            stats["inserted"] += 1
                        else:
                            stats["updated"] += 1
                        local_index[k] = {**(existing or {}), **incoming}

                    if not dry_run:
                        sqlite_conn.commit()

                    summary[table_name] = stats
                    logger.info(
                        "Table %-27s | remote=%4d | inserted=%4d | updated=%4d | unchanged=%4d%s",
                        table_name,
                        stats["remote_rows"],
                        stats["inserted"],
                        stats["updated"],
                        stats["skipped_fresh"],
                        " (DRY-RUN)" if dry_run else "",
                    )
                except Exception as tbl_err:
                    if not dry_run:
                        sqlite_conn.rollback()
                    logger.error("Error pulling table %s from Supabase: %s", table_name, tbl_err)
                    summary[table_name] = stats
    finally:
        try:
            pg_conn.close()
        except Exception as pg_close_err:
            logger.debug("PG close notice: %s", pg_close_err)
        try:
            sqlite_conn.close()
        except Exception as sq_close_err:
            logger.debug("SQLite close notice: %s", sq_close_err)

    total_ins = sum(v["inserted"] for v in summary.values())
    total_upd = sum(v["updated"] for v in summary.values())
    logger.info(
        "Supabase -> SQLite sync complete (%s): %d inserted, %d updated across %d tables.",
        "dry-run" if dry_run else sqlite_path,
        total_ins,
        total_upd,
        len(summary),
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull multi-asset data from Supabase into local SQLite (reports.db)")
    parser.add_argument("--db-path", default=None, help="Target SQLite path (default: reports.db)")
    parser.add_argument("--supabase-db-url", default=None, help="Direct PostgreSQL DSN override")
    parser.add_argument("--supabase-url", default=None, help="Supabase REST URL fallback")
    parser.add_argument("--tables", default=None, help="Comma-separated subset of tables to pull")
    parser.add_argument("--dry-run", action="store_true", help="Inspect incoming diffs without writing to SQLite")
    parser.add_argument("--force", action="store_true", help="Overwrite local rows even if local timestamp is newer")
    args = parser.parse_args()

    sqlite_path = args.db_path or get_db_path()
    pg_url = (
        args.supabase_db_url
        if args.supabase_db_url is not None
        else (os.environ.get("SUPABASE_DB_URL") if "SUPABASE_DB_URL" in os.environ else get_secret("SUPABASE_DB_URL"))
    )
    selected_tables = [t.strip() for t in args.tables.split(",")] if args.tables else None

    if pg_url and pg_url.strip():
        try:
            sync_via_postgresql_pull(
                sqlite_path=sqlite_path,
                db_url=pg_url.strip(),
                dry_run=args.dry_run,
                force=args.force,
                selected_tables=selected_tables,
            )
            return 0
        except Exception as exc:
            logger.error("Direct PostgreSQL pull failed (%s). Failing closed with local SQLite intact.", exc)
            return 1

    sb_url = args.supabase_url or get_secret("SUPABASE_URL")
    service_key = get_secret("SUPABASE_SERVICE_ROLE_KEY")
    if sb_url and service_key and not args.dry_run:
        from scripts.sync_to_supabase import pull_from_supabase_rest

        pull_from_supabase_rest(sqlite_path, sb_url, service_key)
        return 0

    logger.warning("No SUPABASE_DB_URL or (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY) configured; skipping pull.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
