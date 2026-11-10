"""
Sync local SQLite reports and revisions to Supabase (PostgreSQL or PostgREST).

Supports:
1. Direct PostgreSQL synchronization when SUPABASE_DB_URL is available.
2. PostgREST REST API synchronization when SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are available.
3. Supabase Storage backup archive upload.
"""

import os
import sys
import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, List

# Ensure parent directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_secret
from core.db.connection import get_db_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_to_supabase")

# Authoritative PostgreSQL-only user, entitlement, billing, and queue tables.
# Offline SQLite -> Supabase sync MUST NEVER overwrite or truncate these tables.
AUTHORITATIVE_PG_ONLY_TABLES = frozenset({
    "user_accounts",
    "user_unlocked_dossiers",
    "billing_order_intents",
    "payment_event_receipts",
    "credit_transactions",
    "credit_usage_ledger",
    "credit_settlement_operations",
    "admin_audit_log",
    "admin_action_proposals",
    "fund_audit_jobs",
    "fund_audit_items",
    "fund_audit_worker_health",
    "fund_audit_worker_instances",
})

def get_local_reports(sqlite_path: str = None) -> List[Dict[str, Any]]:
    """Fetches all rows from local SQLite reports table."""
    path = sqlite_path or get_db_path()
    if not os.path.exists(path):
        logger.warning(f"Local SQLite database not found at {path}")
        return []

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ticker, short_name, report_text, timestamp, baseline_price,
               baseline_pe, baseline_mcap, latest_announcement, citations_json
        FROM reports
        ORDER BY ticker ASC
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_local_revisions(sqlite_path: str = None) -> List[Dict[str, Any]]:
    """Fetches all rows from local SQLite report_revisions table."""
    path = sqlite_path or get_db_path()
    if not os.path.exists(path):
        return []

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT ticker, short_name, report_text, timestamp, baseline_price,
                   baseline_pe, baseline_mcap, latest_announcement, revision_trigger, citations_json
            FROM report_revisions
            ORDER BY id ASC
        """)
        rows = [dict(row) for row in cursor.fetchall()]
    except Exception:
        rows = []
    finally:
        conn.close()
    return rows

def _coerce_pg_date(val: Any):
    """Coerces SQLite date/timestamp/sentinel values into a Python datetime.date or None for PostgreSQL DATE columns."""
    from datetime import date, datetime
    from core.db.connection import IST
    from core.presentation.formatters import _coerce_datetime

    if val is None:
        return None
    if isinstance(val, datetime):
        return (val.astimezone(IST) if val.tzinfo else val).date()
    if isinstance(val, date):
        return val
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(float(val), tz=IST).date()
    if isinstance(val, str):
        s = val.strip()
        if not s or s.lower() in {
            "none", "null", "n/a", "na", "pending", "pending monthly disclosure", "-", "unknown"
        }:
            return None
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            coerced = _coerce_datetime(s)
            return coerced.date() if coerced is not None else None
    return None


def sync_via_postgresql(reports: List[Dict[str, Any]], revisions: List[Dict[str, Any]], db_url: str, sqlite_path: str = None) -> Dict[str, int]:
    """Syncs all 18 multi-asset tables directly to Supabase PostgreSQL using psycopg2."""
    import psycopg2
    from psycopg2.extras import execute_batch, execute_values
    from core.db.connection import IST, _normalize_pg_dsn, close_all_pg_pools, init_db
    from core.presentation.formatters import _coerce_datetime

    logger.info("Connecting to Supabase PostgreSQL via SUPABASE_DB_URL...")
    try:
        conn = psycopg2.connect(_normalize_pg_dsn(db_url), connect_timeout=10)
    except psycopg2.OperationalError as op_err:
        if "could not translate host name" in str(op_err) and "db." in db_url and ".supabase.co" in db_url:
            logger.warning("Supabase direct host is IPv6-only or unreachable from this network. Attempting IPv4 pooler fallback...")
            import re
            m = re.search(r"postgresql://([^:]+):([^@]+)@db\.([^\.]+)\.supabase\.co:(\d+)/(.+)", db_url)
            if m:
                user, password, project_ref, port, dbname = m.groups()
                dbname_clean = dbname.split("?")[0]
                for region in ["ap-southeast-1", "ap-south-1", "us-east-1", "eu-central-1"]:
                    pooler_url = _normalize_pg_dsn(
                        f"postgresql://{user}.{project_ref}:{password}@aws-0-{region}.pooler.supabase.com:5432/{dbname_clean}"
                    )
                    try:
                        conn = psycopg2.connect(pooler_url, connect_timeout=5)
                        logger.info(f"Connected to Supabase PostgreSQL via IPv4 pooler ({region})!")
                        break
                    except Exception:
                        continue
                else:
                    raise op_err
            else:
                raise op_err
        else:
            raise op_err

    conn.autocommit = False
    cursor = conn.cursor()
    cursor.execute("SET TIME ZONE 'Asia/Kolkata';")
    conn.commit()

    # 1. Initialize complete schema migrations on PostgreSQL and release pool sockets immediately
    logger.info("Ensuring PostgreSQL schema migrations are initialized...")
    try:
        from core.db.savings import reconcile_savings_schema_and_legacy_tables

        reconcile_savings_schema_and_legacy_tables(cursor, is_pg=True)
        conn.commit()
        init_db(force=False)
    except Exception as mig_err:
        conn.rollback()
        logger.debug("Schema migration notice: %s", mig_err)
    finally:
        close_all_pg_pools()

    path = sqlite_path or get_db_path()
    sqlite_conn = sqlite3.connect(path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    # Tables to sync: (table_name, conflict_target, update_on_conflict, ts_col)
    # Parent tables precede dependent child tables to preserve PostgreSQL FK constraints.
    sync_targets = [
        ("reports", "ticker", True, "timestamp"),
        ("report_revisions", "__natural_revision__", False, "timestamp"),
        ("cached_fundamentals", "ticker", True, "updated_at"),
        ("discovery_reel", "__natural_discovery__", True, "created_at"),
        ("mutual_fund_schemes", "scheme_code", True, "last_updated"),
        ("mf_disclosure_snapshots", "snapshot_id", False, "created_at"),
        ("mutual_fund_holdings", "__scheme_holdings__", True, "created_at"),
        ("mf_current_disclosures", "scheme_code", True, "updated_at"),
        ("fund_forensic_dossiers", "scheme_code", True, "last_audited_at"),
        ("corporate_debt_securities", "isin", True, "last_updated"),
        ("debt_quote_observations", "isin, as_of, source_url", True, "recorded_at"),
        ("sovereign_benchmarks", "tenor_label", True, "updated_at"),
        ("sovereign_curve_history", "snapshot_key, tenor_label", True, None),
        ("sovereign_sdl_spreads", "state_name", True, "updated_at"),
        ("sovereign_macro_rates", "metric_key", True, "updated_at"),
        ("reits_and_invits", "symbol", True, "updated_at"),
        ("sgb_tranches", "symbol", True, "updated_at"),
        ("alternative_yield_products", "product_id", True, "updated_at"),
        ("etf_matrix", "symbol", True, "updated_at"),
        ("msme_firms", "uin", True, "last_updated"),
        ("equity_price_history_cache", "ticker, period", True, "updated_at"),
        ("instrument_metric_observations", "instrument_id, asset_class, measure_type, as_of, source_name", True, "recorded_at"),
        ("savings_override_audit_log", "override_id", False, "created_at"),
        ("savings_rate_observations", "__savings_observations_reconcile__", True, "observed_at"),
        ("savings_instruments", "__savings_instruments_reconcile__", True, "updated_at"),
        ("tax_rule_registry", "rule_version", True, "updated_at"),
    ]
    forbidden_overlap = AUTHORITATIVE_PG_ONLY_TABLES.intersection({t[0] for t in sync_targets})
    if forbidden_overlap:
        raise RuntimeError(
            f"Refusing offline sync: authoritative PostgreSQL-only tables in sync_targets: {sorted(forbidden_overlap)}"
        )

    def _transform_cell(val: Any, dt: str) -> Any:
        if val is None:
            return None
        if dt == "boolean":
            return bool(val) if not isinstance(val, str) else (val.strip().lower() in ("true", "t", "1", "yes"))
        if "timestamp" in dt:
            coerced = _coerce_datetime(val)
            return coerced if coerced is not None else None
        if dt == "date":
            return _coerce_pg_date(val)
        return val

    sync_summary = {}

    for table_name, conflict_col, do_update, ts_col in sync_targets:
        try:
            sqlite_cur.execute(f"SELECT * FROM {table_name}")
            rows = sqlite_cur.fetchall()
            if not rows:
                continue

            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = %s AND table_name = %s",
                ("public", table_name),
            )
            pg_col_types = dict(cursor.fetchall())
            if not pg_col_types:
                logger.warning(f"Table {table_name} does not exist in target PostgreSQL schema.")
                continue

            raw_cols = [col[0] for col in sqlite_cur.description]
            cols = [c for c in raw_cols if not (c == "id" and conflict_col != "id" and "id" in pg_col_types) and c in pg_col_types]
            cols_joined = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))

            if conflict_col == "__natural_discovery__":
                cursor.execute("SELECT edition_date, ticker, created_at FROM discovery_reel")
                pg_by_ed: Dict[str, List[Any]] = {}
                for ped, pticker, pcreated in cursor.fetchall():
                    pg_by_ed.setdefault(str(ped)[:10], []).append(
                        (str(pticker or "").strip().upper(), _coerce_datetime(pcreated))
                    )

                sq_by_ed: Dict[str, List[Any]] = {}
                for row in rows:
                    ed_date = _coerce_pg_date(row["edition_date"])
                    if ed_date:
                        sq_by_ed.setdefault(ed_date.isoformat(), []).append(row)

                batch_count = 0
                for ed_iso, sq_cohort in sq_by_ed.items():
                    pg_cohort = pg_by_ed.get(ed_iso)
                    sq_tickers = {str(r["ticker"] or "").strip().upper() for r in sq_cohort}
                    sq_max_dt = max(
                        (_coerce_datetime(r["created_at"]) for r in sq_cohort if _coerce_datetime(r["created_at"])),
                        default=None,
                    )
                    if pg_cohort is None:
                        to_ins = [
                            tuple(_transform_cell(r[c], pg_col_types.get(c, "")) for c in cols)
                            for r in sq_cohort
                        ]
                        execute_batch(
                            cursor,
                            f"INSERT INTO discovery_reel ({cols_joined}) VALUES ({placeholders})",
                            to_ins,
                            page_size=500,
                        )
                        batch_count += len(to_ins)
                    else:
                        pg_tickers = {x[0] for x in pg_cohort}
                        pg_max_dt = max((x[1] for x in pg_cohort if x[1] is not None), default=None)
                        if sq_tickers != pg_tickers and sq_max_dt and (pg_max_dt is None or (sq_max_dt - pg_max_dt).total_seconds() > 1.0):
                            cursor.execute("DELETE FROM discovery_reel WHERE edition_date = %s", (_coerce_pg_date(ed_iso),))
                            to_ins = [
                                tuple(_transform_cell(r[c], pg_col_types.get(c, "")) for c in cols)
                                for r in sq_cohort
                            ]
                            execute_batch(
                                cursor,
                                f"INSERT INTO discovery_reel ({cols_joined}) VALUES ({placeholders})",
                                to_ins,
                                page_size=500,
                            )
                            batch_count += len(to_ins)
            elif conflict_col == "__natural_revision__":
                cursor.execute("SELECT ticker, timestamp FROM report_revisions")
                pg_rev_keys = set()
                for pticker, pts in cursor.fetchall():
                    pdt = _coerce_datetime(pts)
                    pg_rev_keys.add((str(pticker or "").strip().upper(), int(pdt.timestamp()) if pdt else str(pts)))

                to_insert = []
                for row in rows:
                    tkr = str(row["ticker"] or "").strip().upper()
                    sdt = _coerce_datetime(row["timestamp"])
                    rkey = (tkr, int(sdt.timestamp()) if sdt else str(row["timestamp"]))
                    if rkey not in pg_rev_keys:
                        to_insert.append(tuple(_transform_cell(row[c], pg_col_types.get(c, "")) for c in cols))
                        pg_rev_keys.add(rkey)

                if to_insert:
                    execute_batch(
                        cursor,
                        f"INSERT INTO report_revisions ({cols_joined}) VALUES ({placeholders})",
                        to_insert,
                        page_size=500,
                    )
                batch_count = len(to_insert)
            elif conflict_col == "__scheme_holdings__":
                cursor.execute(
                    "SELECT scheme_code, COUNT(*), MAX(created_at) FROM mutual_fund_holdings GROUP BY scheme_code"
                )
                pg_by_scheme: Dict[str, Any] = {
                    str(sc or "").strip(): (int(cnt or 0), _coerce_datetime(max_ts))
                    for sc, cnt, max_ts in cursor.fetchall()
                }

                sq_by_scheme: Dict[str, Dict[Any, Any]] = {}
                for row in rows:
                    sc = str(row["scheme_code"] or "").strip()
                    if not sc:
                        continue
                    nk = (
                        sc,
                        str(row["holding_type"] or "").strip(),
                        str(row["identifier"] or "").strip(),
                    )
                    sq_by_scheme.setdefault(sc, {})[nk] = row

                schemes_to_replace: List[str] = []
                to_insert = []
                for sc, cohort_map in sq_by_scheme.items():
                    sq_cohort = list(cohort_map.values())
                    sq_max_dt = max(
                        (_coerce_datetime(r["created_at"]) for r in sq_cohort if _coerce_datetime(r["created_at"])),
                        default=None,
                    )
                    if sc in pg_by_scheme:
                        _pg_cnt, pg_max_dt = pg_by_scheme[sc]
                        if (
                            pg_max_dt is not None
                            and sq_max_dt is not None
                            and (pg_max_dt - sq_max_dt).total_seconds() > 1.0
                        ):
                            continue
                        schemes_to_replace.append(sc)
                    for r in sq_cohort:
                        to_insert.append(tuple(_transform_cell(r[c], pg_col_types.get(c, "")) for c in cols))

                for idx in range(0, len(schemes_to_replace), 500):
                    chunk = schemes_to_replace[idx : idx + 500]
                    cursor.execute("DELETE FROM mutual_fund_holdings WHERE scheme_code = ANY(%s)", (chunk,))

                if to_insert:
                    execute_values(
                        cursor,
                        f"INSERT INTO mutual_fund_holdings ({cols_joined}) VALUES %s",
                        to_insert,
                        page_size=2000,
                    )
                batch_count = len(to_insert)
            elif conflict_col == "__savings_observations_reconcile__":
                from core.db.savings import validate_observation_provenance

                valid_obs_rows = []
                for r in rows:
                    try:
                        validate_observation_provenance(dict(r))
                        valid_obs_rows.append(dict(r))
                    except ValueError as obs_err:
                        logger.warning(
                            "Skipped savings_rate_observations row failing provenance check: %s",
                            obs_err,
                        )
                if not valid_obs_rows:
                    continue

                sq_sup_chain: Dict[str, Any] = {
                    str(r["observation_id"]): (
                        str(r["superseded_by_observation_id"])
                        if r.get("superseded_by_observation_id")
                        else None
                    )
                    for r in valid_obs_rows
                }

                def _sq_causally_superseded(ancestor_id: str, descendant_id: str) -> bool:
                    cur_id = ancestor_id
                    visited = set()
                    while cur_id and cur_id not in visited and len(visited) < 64:
                        visited.add(cur_id)
                        nxt = sq_sup_chain.get(cur_id)
                        if nxt == descendant_id:
                            return True
                        cur_id = nxt
                    return False

                cursor.execute(
                    "SELECT instrument_id, effective_from, COALESCE(override_epoch, 0), active_observation_id "
                    "FROM savings_instruments;"
                )
                pg_inst_state = {
                    str(r[0]): (str(r[1] or "")[:10], int(r[2] or 0), str(r[3]) if r[3] else None)
                    for r in cursor.fetchall()
                }
                cursor.execute(
                    "SELECT instrument_id, effective_from, observation_id, observation_status "
                    "FROM savings_rate_observations WHERE superseded_at IS NULL;"
                )
                pg_unsup_by_inst_eff: Dict[Any, str] = {
                    (str(r[0]), str(r[1])[:10]): str(r[2]) for r in cursor.fetchall()
                }
                cursor.execute(
                    "SELECT instrument_id, override_epoch, dependent_updates_json FROM savings_override_audit_log;"
                )
                audited_epochs: Dict[str, int] = {}
                for ov_inst, ov_ep, ov_deps_raw in cursor.fetchall():
                    ov_i = str(ov_inst)
                    ov_e = int(ov_ep or 0)
                    if ov_e > audited_epochs.get(ov_i, 0):
                        audited_epochs[ov_i] = ov_e
                    try:
                        for dep in json.loads(ov_deps_raw or "[]"):
                            d_id = str(dep.get("instrument_id") or "")
                            d_ep = int(dep.get("override_epoch") or ov_e)
                            if d_id and d_ep > audited_epochs.get(d_id, 0):
                                audited_epochs[d_id] = d_ep
                    except Exception as dep_err:
                        logger.debug("Audit dependent_updates_json parse notice: %s", dep_err)
                sqlite_cur.execute("SELECT instrument_id, COALESCE(override_epoch, 0) FROM savings_instruments;")
                sq_inst_epochs = {str(r[0]): int(r[1] or 0) for r in sqlite_cur.fetchall()}

                now_sync_iso = datetime.now(IST).isoformat()
                conflicts_detected = 0
                to_upsert_obs = []
                pg_obs_to_supersede = []

                for r in valid_obs_rows:
                    obs_id_val = str(r["observation_id"])
                    inst_id_val = str(r["instrument_id"])
                    eff_val = str(r["effective_from"])[:10]
                    is_unsup = r.get("superseded_at") is None
                    pg_existing_unsup = pg_unsup_by_inst_eff.get((inst_id_val, eff_val))
                    _pg_eff, pg_epoch, _pg_act = pg_inst_state.get(inst_id_val, ("", 0, None))
                    sq_epoch = sq_inst_epochs.get(inst_id_val, 0)
                    sq_has_higher_audited_override = (
                        sq_epoch > pg_epoch and audited_epochs.get(inst_id_val, 0) >= sq_epoch
                    )

                    row_mut = dict(r)
                    if is_unsup and pg_existing_unsup and pg_existing_unsup != obs_id_val:
                        if _sq_causally_superseded(pg_existing_unsup, obs_id_val) or sq_has_higher_audited_override:
                            pg_obs_to_supersede.append((now_sync_iso, obs_id_val, pg_existing_unsup))
                            pg_unsup_by_inst_eff[(inst_id_val, eff_val)] = obs_id_val
                        else:
                            # Independent split-brain revision across DBs: PostgreSQL is authoritative;
                            # record SQLite's divergent observation as SUPERSEDED_CONFLICT without losing history.
                            row_mut["superseded_at"] = now_sync_iso
                            row_mut["superseded_by_observation_id"] = pg_existing_unsup
                            row_mut["observation_status"] = "SUPERSEDED_CONFLICT"
                            conflicts_detected += 1

                    to_upsert_obs.append(
                        tuple(_transform_cell(row_mut.get(c), pg_col_types.get(c, "")) for c in cols)
                    )

                for sup_ts, new_oid, old_oid in pg_obs_to_supersede:
                    cursor.execute(
                        """
                        UPDATE savings_rate_observations
                        SET superseded_at = %s,
                            superseded_by_observation_id = %s,
                            observation_status = 'SUPERSEDED'
                        WHERE observation_id = %s AND superseded_at IS NULL;
                        """,
                        (sup_ts, new_oid, old_oid),
                    )

                obs_query = (
                    f"INSERT INTO savings_rate_observations ({cols_joined}) VALUES ({placeholders}) "
                    f"ON CONFLICT (observation_id) DO UPDATE SET "
                    f"effective_to = COALESCE(savings_rate_observations.effective_to, EXCLUDED.effective_to), "
                    f"superseded_at = COALESCE(savings_rate_observations.superseded_at, EXCLUDED.superseded_at), "
                    f"superseded_by_observation_id = COALESCE("
                    f"savings_rate_observations.superseded_by_observation_id, "
                    f"EXCLUDED.superseded_by_observation_id), "
                    f"observation_status = CASE "
                    f"WHEN savings_rate_observations.superseded_at IS NULL AND EXCLUDED.superseded_at IS NOT NULL "
                    f"THEN EXCLUDED.observation_status "
                    f"WHEN savings_rate_observations.observation_status = 'SCHEDULED_FUTURE' "
                    f"AND EXCLUDED.observation_status = 'ACTIVE' THEN 'ACTIVE' "
                    f"ELSE savings_rate_observations.observation_status END"
                )
                execute_batch(cursor, obs_query, to_upsert_obs, page_size=500)
                batch_count = len(to_upsert_obs)
                if conflicts_detected:
                    sync_summary["savings_conflicts_detected"] = (
                        sync_summary.get("savings_conflicts_detected", 0) + conflicts_detected
                    )
            elif conflict_col == "__savings_instruments_reconcile__":
                from core.db.savings import is_valid_savings_provenance

                valid_inst_rows = [dict(r) for r in rows if is_valid_savings_provenance(dict(r))]
                if len(valid_inst_rows) < len(rows):
                    logger.warning(
                        "Skipped %d savings_instruments rows failing official provenance check.",
                        len(rows) - len(valid_inst_rows),
                    )
                if not valid_inst_rows:
                    continue

                sqlite_cur.execute(
                    "SELECT observation_id, superseded_by_observation_id FROM savings_rate_observations;"
                )
                sq_sup_map = {
                    str(r[0]): (str(r[1]) if r[1] else None) for r in sqlite_cur.fetchall()
                }

                def _is_causal_successor_sq(ancestor_oid: str, successor_oid: str) -> bool:
                    cur_id = ancestor_oid
                    seen = set()
                    while cur_id and cur_id not in seen and len(seen) < 64:
                        seen.add(cur_id)
                        nxt = sq_sup_map.get(cur_id)
                        if nxt == successor_oid:
                            return True
                        cur_id = nxt
                    return False

                cursor.execute(
                    "SELECT instrument_id, effective_from, COALESCE(override_epoch, 0), "
                    "active_observation_id, updated_at FROM savings_instruments;"
                )
                pg_cur_inst = {
                    str(r[0]): (
                        str(r[1] or "")[:10],
                        int(r[2] or 0),
                        str(r[3]) if r[3] else None,
                        _coerce_datetime(r[4]),
                    )
                    for r in cursor.fetchall()
                }
                cursor.execute(
                    "SELECT instrument_id, override_epoch, dependent_updates_json FROM savings_override_audit_log;"
                )
                pg_audited_epochs: Dict[str, int] = {}
                for ov_inst, ov_ep, ov_deps_raw in cursor.fetchall():
                    ov_i = str(ov_inst)
                    ov_e = int(ov_ep or 0)
                    if ov_e > pg_audited_epochs.get(ov_i, 0):
                        pg_audited_epochs[ov_i] = ov_e
                    try:
                        for dep in json.loads(ov_deps_raw or "[]"):
                            d_id = str(dep.get("instrument_id") or "")
                            d_ep = int(dep.get("override_epoch") or ov_e)
                            if d_id and d_ep > pg_audited_epochs.get(d_id, 0):
                                pg_audited_epochs[d_id] = d_ep
                    except Exception as dep_err:
                        logger.debug("Audit dependent_updates_json parse notice: %s", dep_err)

                allowed_inst_rows = []
                now_inst_iso = datetime.now(IST).isoformat()
                for r in valid_inst_rows:
                    iid = str(r["instrument_id"])
                    sq_eff = str(r.get("effective_from") or "")[:10]
                    sq_epoch = int(r.get("override_epoch") or 0)
                    sq_act_obs = str(r["active_observation_id"]) if r.get("active_observation_id") else None
                    sq_upd_dt = _coerce_datetime(r.get("updated_at"))

                    if iid not in pg_cur_inst:
                        allowed_inst_rows.append(r)
                        continue

                    pg_eff, pg_epoch, pg_act_obs, pg_upd_dt = pg_cur_inst[iid]
                    if sq_epoch > pg_epoch:
                        if pg_audited_epochs.get(iid, 0) >= sq_epoch:
                            # Supersede any newer PG observations rolled back by the audited override
                            if sq_act_obs:
                                cursor.execute(
                                    """
                                    UPDATE savings_rate_observations
                                    SET superseded_at = %s,
                                        superseded_by_observation_id = %s,
                                        observation_status = 'SUPERSEDED'
                                    WHERE instrument_id = %s
                                      AND superseded_at IS NULL
                                      AND observation_id <> %s
                                      AND effective_from >= %s;
                                    """,
                                    (now_inst_iso, sq_act_obs, iid, sq_act_obs, sq_eff),
                                )
                            allowed_inst_rows.append(r)
                        else:
                            logger.warning(
                                "Rejected unaudited override_epoch=%d on %s during Supabase upload.",
                                sq_epoch,
                                iid,
                            )
                    elif sq_epoch < pg_epoch:
                        continue
                    elif sq_eff > pg_eff:
                        cursor.execute(
                            """
                            UPDATE savings_rate_observations
                            SET effective_to = COALESCE(effective_to, %s),
                                observation_status = CASE
                                    WHEN observation_status = 'ACTIVE' THEN 'HISTORICAL'
                                    ELSE observation_status
                                END
                            WHERE instrument_id = %s
                              AND superseded_at IS NULL
                              AND effective_to IS NULL
                              AND effective_from < %s;
                            """,
                            (sq_eff, iid, sq_eff),
                        )
                        allowed_inst_rows.append(r)
                    elif sq_eff < pg_eff:
                        continue
                    else:
                        # Same override_epoch and same effective_from
                        if sq_act_obs and pg_act_obs and sq_act_obs != pg_act_obs:
                            if _is_causal_successor_sq(pg_act_obs, sq_act_obs):
                                allowed_inst_rows.append(r)
                            # Else split-brain conflict: keep PostgreSQL's authoritative active row!
                        elif pg_upd_dt is None or (sq_upd_dt is not None and sq_upd_dt >= pg_upd_dt):
                            allowed_inst_rows.append(r)

                if allowed_inst_rows:
                    upd_inst_sql = ", ".join(
                        [f"{c} = EXCLUDED.{c}" for c in cols if c != "instrument_id"]
                    )
                    inst_upsert_q = (
                        f"INSERT INTO savings_instruments ({cols_joined}) VALUES ({placeholders}) "
                        f"ON CONFLICT (instrument_id) DO UPDATE SET {upd_inst_sql}"
                    )
                    inst_batch = [
                        tuple(_transform_cell(r.get(c), pg_col_types.get(c, "")) for c in cols)
                        for r in allowed_inst_rows
                    ]
                    execute_batch(cursor, inst_upsert_q, inst_batch, page_size=500)
                batch_count = len(allowed_inst_rows)
            else:
                if table_name == "savings_override_audit_log":
                    valid_ovr_rows = [
                        r
                        for r in rows
                        if str(r["operator_id"] or "").strip()
                        and len(str(r["override_reason"] or "").strip()) >= 8
                    ]
                    rows = valid_ovr_rows
                elif table_name == "tax_rule_registry":
                    from core.db.savings import validate_tax_rule_provenance

                    valid_tax_rows = []
                    for r in rows:
                        try:
                            validate_tax_rule_provenance(dict(r))
                            valid_tax_rows.append(r)
                        except ValueError as tv_err:
                            logger.warning("Skipped tax_rule_registry row failing provenance check: %s", tv_err)
                    rows = valid_tax_rows
                if not rows:
                    continue

                if do_update and conflict_col:
                    conflict_targets = [c.strip() for c in conflict_col.split(",")]
                    conflict_target_sql = ", ".join(conflict_targets)
                    preserve_non_empty_cols = {"report_text", "citations_json", "dossier_text", "evidence_receipt_json"}
                    update_parts = []
                    for c in cols:
                        if c in conflict_targets:
                            continue
                        if c in preserve_non_empty_cols:
                            update_parts.append(
                                f"{c} = CASE WHEN EXCLUDED.{c} IS NOT NULL AND TRIM(EXCLUDED.{c}) <> '' "
                                f"THEN EXCLUDED.{c} ELSE {table_name}.{c} END"
                            )
                        elif table_name == "mutual_fund_schemes" and c == "aum_crores":
                            update_parts.append(
                                f"aum_crores = CASE WHEN COALESCE(EXCLUDED.aum_crores, 0) > 0 "
                                f"THEN EXCLUDED.aum_crores ELSE {table_name}.aum_crores END"
                            )
                        else:
                            update_parts.append(f"{c} = EXCLUDED.{c}")
                    update_assignments = ", ".join(update_parts)
                    where_guard = ""
                    if ts_col and ts_col in cols:
                        extra_substance_guard = ""
                        if table_name == "reports":
                            extra_substance_guard = f" OR {table_name}.report_text IS NULL OR LENGTH(TRIM({table_name}.report_text)) < 500"
                        elif table_name == "fund_forensic_dossiers":
                            extra_substance_guard = f" OR {table_name}.dossier_text IS NULL OR TRIM({table_name}.dossier_text) = ''"
                        elif table_name == "mutual_fund_schemes":
                            extra_substance_guard = (
                                f" OR (COALESCE({table_name}.aum_crores, 0) <= 0 AND COALESCE(EXCLUDED.aum_crores, 0) > 0)"
                            )
                        where_guard = (
                            f" WHERE {table_name}.{ts_col} IS NULL "
                            f"OR EXCLUDED.{ts_col} IS NULL "
                            f"OR EXCLUDED.{ts_col} >= {table_name}.{ts_col}"
                            f"{extra_substance_guard}"
                        )
                    conflict_clause = f"ON CONFLICT ({conflict_target_sql}) DO UPDATE SET {update_assignments}{where_guard}"
                elif conflict_col:
                    conflict_targets = [c.strip() for c in conflict_col.split(",")]
                    conflict_target_sql = ", ".join(conflict_targets)
                    conflict_clause = f"ON CONFLICT ({conflict_target_sql}) DO NOTHING"
                else:
                    conflict_clause = ""

                insert_query = f"INSERT INTO {table_name} ({cols_joined}) VALUES ({placeholders}) {conflict_clause}"
                batch_data = [
                    tuple(_transform_cell(row[c], pg_col_types.get(c, "")) for c in cols)
                    for row in rows
                ]
                execute_batch(cursor, insert_query, batch_data, page_size=500)
                batch_count = len(batch_data)

            # Sync sequence if table has a serial id column
            if "id" in pg_col_types:
                try:
                    cursor.execute(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE((SELECT MAX(id) FROM {table_name}), 1), true);")
                except Exception as seq_err:
                    logger.debug("Sequence reset notice for %s: %s", table_name, seq_err)

            conn.commit()
            sync_summary[table_name] = batch_count
            logger.info(f"✅ Synced {batch_count:4d} records to Supabase table: {table_name}")
        except Exception as tbl_err:
            conn.rollback()
            logger.warning(f"Notice syncing table {table_name}: {tbl_err}")
            sync_summary[table_name] = 0

    cursor.close()
    conn.close()
    sqlite_cur.close()
    sqlite_conn.close()

    logger.info(f"🎉 Multi-Asset Supabase Sync Complete across {len(sync_summary)} tables!")
    return sync_summary

def sync_via_rest(reports: List[Dict[str, Any]], supabase_url: str, service_key: str) -> Dict[str, int]:
    """Syncs rows to Supabase PostgREST endpoint /rest/v1/reports."""
    import requests

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }

    url = f"{supabase_url.rstrip('/')}/rest/v1/reports"
    synced = 0
    errors = 0

    logger.info(f"Syncing {len(reports)} reports to Supabase REST at {url}...")
    for r in reports:
        payload = {
            "ticker": r["ticker"],
            "short_name": r.get("short_name"),
            "report_text": r.get("report_text"),
            "baseline_price": r.get("baseline_price"),
            "baseline_pe": str(r.get("baseline_pe") or ""),
            "baseline_mcap": r.get("baseline_mcap"),
            "latest_announcement": r.get("latest_announcement"),
            "citations_json": r.get("citations_json")
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code in (200, 201):
                synced += 1
            else:
                logger.warning(f"Supabase REST returned {resp.status_code} for {r['ticker']}: {resp.text[:150]}")
                errors += 1
        except Exception as e:
            logger.error(f"Error syncing {r['ticker']} via REST: {e}")
            errors += 1

    logger.info(f"✅ Supabase REST Sync Complete: {synced} synced, {errors} errors.")
    return {"reports_synced": synced, "errors": errors}

def upload_sqlite_backup_to_storage(sqlite_path: str, supabase_url: str, service_key: str) -> bool:
    """Uploads the reports.db snapshot to Supabase storage 'backups' bucket."""
    import requests
    if not os.path.exists(sqlite_path):
        return False

    from core.db.connection import IST
    timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    target_name = f"reports_db_{timestamp}.sqlite"
    storage_url = f"{supabase_url.rstrip('/')}/storage/v1/object/backups/{target_name}"

    try:
        with open(sqlite_path, "rb") as f:
            data = f.read()
        resp = requests.post(
            storage_url,
            headers={
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/x-sqlite3"
            },
            data=data,
            timeout=30
        )
        if resp.status_code in (200, 201):
            logger.info(f"✅ Uploaded SQLite snapshot to Supabase Storage: backups/{target_name}")
            return True
        else:
            logger.warning(f"Supabase storage upload returned {resp.status_code}: {resp.text[:150]}")
            return False
    except Exception as e:
        logger.error(f"Failed to upload backup to Supabase Storage: {e}")
        return False

def pull_from_supabase_rest(sqlite_path: str, supabase_url: str, service_key: str) -> int:
    """Pulls all reports from Supabase PostgREST table into local SQLite database."""
    import requests
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}"
    }
    url = f"{supabase_url.rstrip('/')}/rest/v1/reports"
    logger.info(f"Pulling reports from Supabase REST at {url}...")
    resp = requests.get(url, headers=headers, timeout=20)
    if resp.status_code != 200:
        logger.error(f"Failed to fetch reports from Supabase: {resp.status_code} {resp.text}")
        return 0

    rows = resp.json()
    if not rows:
        logger.info("No reports found in Supabase.")
        return 0

    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            ticker TEXT PRIMARY KEY,
            short_name TEXT,
            report_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            baseline_price REAL,
            baseline_pe TEXT,
            baseline_mcap REAL,
            latest_announcement TEXT,
            citations_json TEXT
        )
    """)
    inserted = 0
    for r in rows:
        cursor.execute("""
            INSERT INTO reports (
                ticker, short_name, report_text, timestamp, baseline_price,
                baseline_pe, baseline_mcap, latest_announcement, citations_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker) DO UPDATE SET
                short_name = excluded.short_name,
                report_text = excluded.report_text,
                timestamp = excluded.timestamp,
                baseline_price = excluded.baseline_price,
                baseline_pe = excluded.baseline_pe,
                baseline_mcap = excluded.baseline_mcap,
                latest_announcement = excluded.latest_announcement,
                citations_json = excluded.citations_json;
        """, (
            r.get("ticker"), r.get("short_name"), r.get("report_text"), r.get("timestamp"),
            r.get("baseline_price"), r.get("baseline_pe"), r.get("baseline_mcap"),
            r.get("latest_announcement"), r.get("citations_json")
        ))
        inserted += 1
    conn.commit()
    conn.close()
    logger.info(f"✅ Successfully pulled and merged {inserted} reports into {sqlite_path}.")
    return inserted

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sync local SQLite reports to/from Supabase")
    parser.add_argument("--db-path", default=None, help="Path to SQLite file (default: reports.db)")
    parser.add_argument("--supabase-db-url", default=None, help="Direct PostgreSQL connection string")
    parser.add_argument("--supabase-url", default=None, help="Supabase Project REST URL")
    parser.add_argument("--upload-backup", action="store_true", help="Also upload SQLite file to Supabase Storage")
    parser.add_argument("--pull", action="store_true", help="Pull existing reports from Supabase into local SQLite")
    args = parser.parse_args()

    sqlite_path = args.db_path or get_db_path()

    sb_url = args.supabase_url or get_secret("SUPABASE_URL")
    service_key = get_secret("SUPABASE_SERVICE_ROLE_KEY")
    pg_url = (
        args.supabase_db_url
        if args.supabase_db_url is not None
        else (os.environ.get("SUPABASE_DB_URL") if "SUPABASE_DB_URL" in os.environ else get_secret("SUPABASE_DB_URL"))
    )

    if args.pull:
        if pg_url:
            from scripts.sync_from_supabase import sync_via_postgresql_pull
            sync_via_postgresql_pull(sqlite_path=sqlite_path, db_url=pg_url)
            return
        if sb_url and service_key:
            pull_from_supabase_rest(sqlite_path, sb_url, service_key)
            return
        logger.error("SUPABASE_DB_URL or (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY) required for --pull.")
        return

    reports = get_local_reports(sqlite_path)
    revisions = get_local_revisions(sqlite_path)

    logger.info(f"Found {len(reports)} reports and {len(revisions)} revisions in {sqlite_path}")

    # Check PostgreSQL connection
    if pg_url:
        sync_via_postgresql(reports, revisions, pg_url, sqlite_path=sqlite_path)
        return

    # Check REST connection
    if sb_url and service_key:
        sync_via_rest(reports, sb_url, service_key)
        if args.upload_backup:
            upload_sqlite_backup_to_storage(sqlite_path, sb_url, service_key)
        return

    logger.warning("No SUPABASE_DB_URL or (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY) found in environment or arguments.")
    logger.info("Reports remain securely persisted in local SQLite (reports.db).")
    logger.info("To sync to Supabase, provide SUPABASE_DB_URL or SUPABASE_URL in .env or via command-line flags.")

if __name__ == "__main__":
    main()
