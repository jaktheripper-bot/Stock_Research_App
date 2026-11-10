"""PostgreSQL 17+ integration, migration, bidirectional sync, and 2-connection concurrency
verification suite for Package 01 (`savings_instruments`, `savings_rate_observations`,
`tax_rule_registry`).

Uses `MOATNOMICS_TEST_POSTGRES_DSN` when supplied (e.g. CI / release_preflight.py), or
automatically provisions a disposable local PostgreSQL cluster via `initdb` + `pg_ctl`
when local PostgreSQL binaries are installed. Never touches production databases.
"""

from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import patch


def _find_pg_bin_dir() -> Optional[Path]:
    for candidate in (Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path("/usr/lib/postgresql/17/bin")):
        if (candidate / "initdb").is_file() and (candidate / "pg_ctl").is_file():
            return candidate
    initdb_bin = shutil.which("initdb")
    if initdb_bin:
        parent = Path(initdb_bin).resolve().parent
        if (parent / "pg_ctl").is_file():
            return parent
    return None


def _allocate_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


EXTERNAL_PG_DSN = os.environ.get("MOATNOMICS_TEST_POSTGRES_DSN", "").strip()
LOCAL_PG_BIN = _find_pg_bin_dir()


@unittest.skipUnless(
    bool(EXTERNAL_PG_DSN or LOCAL_PG_BIN),
    "Neither MOATNOMICS_TEST_POSTGRES_DSN nor local PostgreSQL (initdb/pg_ctl) is available.",
)
class TestPostgresSavingsPackage01(unittest.TestCase):
    """Real PostgreSQL verification for Package 01 schema, sync round-trip, and concurrency."""

    _ephemeral_tmp: Optional[tempfile.TemporaryDirectory] = None
    _pg_data_dir: Optional[Path] = None
    _pg_dsn: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        if EXTERNAL_PG_DSN:
            if not any(tok in EXTERNAL_PG_DSN.lower() for tok in ("test", "staging", "disposable", "ci", "sandbox")):
                raise RuntimeError("Refusing PostgreSQL test on non-disposable database DSN.")
            cls._pg_dsn = EXTERNAL_PG_DSN
        else:
            assert LOCAL_PG_BIN is not None
            cls._ephemeral_tmp = tempfile.TemporaryDirectory(prefix="moat-pg-pkg01-")
            tmp_root = Path(cls._ephemeral_tmp.name)
            cls._pg_data_dir = tmp_root / "pgdata"
            port = _allocate_free_port()
            subprocess.run(
                [
                    str(LOCAL_PG_BIN / "initdb"),
                    "-D",
                    str(cls._pg_data_dir),
                    "-A",
                    "trust",
                    "-U",
                    "postgres",
                    "--no-locale",
                    "-E",
                    "UTF8",
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    str(LOCAL_PG_BIN / "pg_ctl"),
                    "-D",
                    str(cls._pg_data_dir),
                    "-l",
                    str(tmp_root / "postgres.log"),
                    "-o",
                    f"-F -p {port} -k {tmp_root}",
                    "start",
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    str(LOCAL_PG_BIN / "psql"),
                    "-h",
                    "127.0.0.1",
                    "-p",
                    str(port),
                    "-U",
                    "postgres",
                    "-d",
                    "postgres",
                    "-c",
                    "CREATE DATABASE moatnomics_test_pkg01;",
                ],
                check=True,
                capture_output=True,
            )
            cls._pg_dsn = f"postgresql://postgres@127.0.0.1:{port}/moatnomics_test_pkg01"

        import core.db.connection as db_conn

        cls._env_patcher = patch.dict(
            os.environ,
            {
                "TESTING": "1",
                "TEST_SUPABASE": "1",
                "SUPABASE_DB_URL": cls._pg_dsn,
                "FORCE_LOCAL_SQLITE": "0",
            },
            clear=False,
        )
        cls._env_patcher.start()
        db_conn.close_all_pg_pools()
        db_conn._DB_INITIALIZED = False
        db_conn._INITIALIZED_DBS.clear()
        db_conn._SUPABASE_URL_RESOLVED = False
        db_conn._CACHED_SUPABASE_URL = None
        db_conn._PG_AVAILABLE = None
        db_conn.init_db(force=True)

    @classmethod
    def tearDownClass(cls) -> None:
        import core.db.connection as db_conn

        db_conn.close_all_pg_pools()
        cls._env_patcher.stop()
        db_conn._DB_INITIALIZED = False
        db_conn._INITIALIZED_DBS.clear()
        db_conn._SUPABASE_URL_RESOLVED = False
        db_conn._CACHED_SUPABASE_URL = None
        db_conn._PG_AVAILABLE = None

        if cls._pg_data_dir is not None and LOCAL_PG_BIN is not None:
            subprocess.run(
                [str(LOCAL_PG_BIN / "pg_ctl"), "-D", str(cls._pg_data_dir), "-m", "immediate", "stop"],
                check=False,
                capture_output=True,
            )
        if cls._ephemeral_tmp is not None:
            cls._ephemeral_tmp.cleanup()

    def setUp(self) -> None:
        from core.db.connection import get_db_connection, is_postgres_connection
        from core.db.savings import seed_baseline_savings_universe

        conn = get_db_connection()
        try:
            self.assertTrue(is_postgres_connection(conn))
            cur = conn.cursor()
            cur.execute("TRUNCATE TABLE savings_override_audit_log;")
            cur.execute("TRUNCATE TABLE savings_rate_observations;")
            cur.execute("TRUNCATE TABLE savings_instruments;")
            cur.execute("TRUNCATE TABLE tax_rule_registry;")
            conn.commit()
            cur.close()
        finally:
            conn.close()
        seed_baseline_savings_universe()

    def test_01_postgres_canonical_schema_and_v050_legacy_upgrade(self) -> None:
        import core.db.connection as db_conn
        from core.db.connection import get_db_connection, init_db
        from core.db.savings import (
            drop_retired_v049_savings_tables,
            validate_legacy_savings_migration_preservation,
        )

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'savings_instruments', 'savings_rate_observations', 'tax_rule_registry',
                      'savings_override_audit_log',
                      'fixed_savings_instruments', 'savings_rate_history', 'regulatory_tax_rule_versions'
                  );
                """
            )
            present = {r[0] for r in cur.fetchall()}
            self.assertEqual(
                present,
                {
                    "savings_instruments",
                    "savings_rate_observations",
                    "tax_rule_registry",
                    "savings_override_audit_log",
                },
            )

            # Simulate dual-populated legacy draft tables + canonical tables on PostgreSQL and re-run v050/v051
            cur.execute(
                "DELETE FROM schema_migrations WHERE version IN ("
                "'v050_reconcile_savings_observations_and_table_names', "
                "'v051_savings_global_observation_ids_and_override_audit');"
            )
            cur.execute(
                """
                CREATE TABLE fixed_savings_instruments AS
                SELECT instrument_id, scheme_name, category, issuer_name, issuer_ticker, issuer_type,
                       sovereign_backed, dicgc_insured, dicgc_limit_inr, credit_rating,
                       base_rate_pct, senior_citizen_bonus_bps, rate_type, floating_benchmark,
                       floating_spread_bps, compounding_freq, payout_options_json,
                       tenure_min_months, tenure_max_months, lock_in_months, premature_exit_rule,
                       min_investment_inr, max_investment_inr, tax_section_80c_eligible,
                       interest_taxability, maturity_taxability, tds_applicable,
                       tds_threshold_regular_inr, tds_threshold_senior_inr,
                       effective_from, next_review_date, source_authority, source_url,
                       notes_json, is_active, updated_at
                FROM savings_instruments
                WHERE instrument_id = 'SAV-PPF';
                """
            )
            cur.execute(
                "ALTER TABLE fixed_savings_instruments ADD PRIMARY KEY (instrument_id);"
            )
            cur.execute(
                "UPDATE fixed_savings_instruments SET base_rate_pct = 7.05, "
                "premature_exit_rule = 'PG_LEGACY_CLAUSE', "
                "updated_at = '2026-09-01T00:00:00+05:30' WHERE instrument_id = 'SAV-PPF';"
            )
            cur.execute(
                """
                CREATE TABLE savings_rate_history (
                    id SERIAL PRIMARY KEY,
                    instrument_id TEXT NOT NULL,
                    base_rate_pct REAL NOT NULL,
                    senior_citizen_bonus_bps REAL NOT NULL DEFAULT 0.0,
                    effective_from TEXT NOT NULL,
                    effective_to TEXT,
                    source_authority TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                """
            )
            cur.execute(
                """
                INSERT INTO savings_rate_history (
                    instrument_id, base_rate_pct, senior_citizen_bonus_bps,
                    effective_from, source_authority, source_url, recorded_at
                ) VALUES (
                    'SAV-PPF', 7.25, 0.0, '2026-11-01',
                    'Department of Economic Affairs (DEA), Ministry of Finance',
                    'https://dea.gov.in', '2026-11-01T10:00:00+05:30'
                );
                """
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()

        db_conn._DB_INITIALIZED = False
        db_conn._INITIALIZED_DBS.clear()
        init_db(force=True)

        pres = validate_legacy_savings_migration_preservation()
        self.assertTrue(pres["valid"], f"PG preservation check failed: {pres['errors']}")

        conn2 = get_db_connection()
        try:
            cur2 = conn2.cursor()
            # Legacy tables are RETAINED for rollback compatibility until drop_retired_v049_savings_tables(confirm=True)
            cur2.execute(
                "SELECT to_regclass('public.fixed_savings_instruments'), to_regclass('public.savings_rate_history');"
            )
            retained = cur2.fetchone()
            self.assertIsNotNone(retained[0])
            self.assertIsNotNone(retained[1])

            cur2.execute(
                "SELECT base_rate_pct, revision_seq, terms_snapshot_json FROM savings_rate_observations "
                "WHERE instrument_id = 'SAV-PPF' ORDER BY effective_from DESC, base_rate_pct DESC;"
            )
            migrated_obs = cur2.fetchall()
            self.assertGreaterEqual(len(migrated_obs), 3)
            self.assertTrue(any("PG_LEGACY_CLAUSE" in str(r[2]) for r in migrated_obs))
            cur2.close()
        finally:
            conn2.close()

        cutover = drop_retired_v049_savings_tables(confirm=True)
        self.assertIn("fixed_savings_instruments", cutover["dropped_tables"])
        self.assertIn("savings_rate_history", cutover["dropped_tables"])

    def test_02_postgres_two_stage_roundtrip_sync_preserves_same_date_revisions(self) -> None:
        import core.db.connection as db_conn
        from core.db.connection import init_db
        from core.db.savings import (
            get_savings_instrument_by_id,
            seed_baseline_savings_universe,
            upsert_savings_instrument,
        )
        from scripts.sync_from_supabase import sync_via_postgresql_pull
        from scripts.sync_to_supabase import sync_via_postgresql

        with tempfile.TemporaryDirectory(prefix="pkg01-sync-") as tmp:
            src_sqlite = Path(tmp) / "src.db"
            dst_sqlite = Path(tmp) / "dst.db"

            # Stage 1: Populate local SQLite with 2026-11-01 rev 1 (7.90%) and sync SQLite -> PG -> dst SQLite
            with patch.dict(
                os.environ,
                {
                    "FORCE_LOCAL_SQLITE": "1",
                    "SUPABASE_DB_URL": "",
                    "TEST_DB_PATH": str(src_sqlite),
                },
            ):
                db_conn._DB_INITIALIZED = False
                db_conn._INITIALIZED_DBS.clear()
                db_conn._SUPABASE_URL_RESOLVED = False
                db_conn._CACHED_SUPABASE_URL = None
                init_db(force=True)
                seed_baseline_savings_universe()
                nsc = dict(get_savings_instrument_by_id("SAV-NSC"))
                upsert_savings_instrument(
                    {**nsc, "base_rate_pct": 7.90, "effective_from": "2026-11-01", "rate_circular_ref": "DEA-REV1"}
                )

            db_conn._SUPABASE_URL_RESOLVED = False
            db_conn._CACHED_SUPABASE_URL = None
            sync_via_postgresql([], [], self._pg_dsn, sqlite_path=str(src_sqlite))
            sync_via_postgresql_pull(
                str(dst_sqlite),
                self._pg_dsn,
                dry_run=False,
                force=False,
                selected_tables=["savings_instruments", "savings_rate_observations", "tax_rule_registry"],
            )

            # Stage 2: Issue same-date revision 2 (8.00% on 2026-11-01) in src_sqlite and re-sync both directions
            with patch.dict(
                os.environ,
                {
                    "FORCE_LOCAL_SQLITE": "1",
                    "SUPABASE_DB_URL": "",
                    "TEST_DB_PATH": str(src_sqlite),
                },
            ):
                db_conn._SUPABASE_URL_RESOLVED = False
                db_conn._CACHED_SUPABASE_URL = None
                nsc_cur = dict(get_savings_instrument_by_id("SAV-NSC"))
                upsert_savings_instrument(
                    {**nsc_cur, "base_rate_pct": 8.00, "effective_from": "2026-11-01", "rate_circular_ref": "DEA-REV2"}
                )

            db_conn._SUPABASE_URL_RESOLVED = False
            db_conn._CACHED_SUPABASE_URL = None
            sync_via_postgresql([], [], self._pg_dsn, sqlite_path=str(src_sqlite))
            sync_via_postgresql_pull(
                str(dst_sqlite),
                self._pg_dsn,
                dry_run=False,
                force=False,
                selected_tables=["savings_instruments", "savings_rate_observations", "tax_rule_registry"],
            )

            sq = sqlite3.connect(str(dst_sqlite))
            rows = sq.execute(
                "SELECT revision_seq, base_rate_pct, rate_circular_ref, superseded_at IS NOT NULL "
                "FROM savings_rate_observations "
                "WHERE instrument_id = 'SAV-NSC' AND effective_from = '2026-11-01' "
                "ORDER BY revision_seq DESC;"
            ).fetchall()
            active_rate = sq.execute(
                "SELECT base_rate_pct FROM savings_instruments WHERE instrument_id = 'SAV-NSC';"
            ).fetchone()[0]
            sq.close()

            self.assertAlmostEqual(active_rate, 8.00, places=2)
            self.assertEqual(len(rows), 2)
            self.assertEqual((rows[0][0], round(rows[0][1], 2), rows[0][2], bool(rows[0][3])), (2, 8.00, "DEA-REV2", False))
            self.assertEqual((rows[1][0], round(rows[1][1], 2), rows[1][2], bool(rows[1][3])), (1, 7.90, "DEA-REV1", True))

        db_conn._SUPABASE_URL_RESOLVED = False
        db_conn._CACHED_SUPABASE_URL = None

    def test_03_postgres_two_connection_concurrent_monotonicity_and_revisions(self) -> None:
        from core.db.savings import (
            get_savings_instrument_by_id,
            get_savings_rate_observations,
            upsert_savings_instrument,
        )

        nsc_base = dict(get_savings_instrument_by_id("SAV-NSC"))

        # Race 1: Concurrent newer (2026-11-04 @ 8.15%) vs older (2026-10-15 @ 7.60%) writers
        barrier_dates = threading.Barrier(2)

        def _date_writer(eff_from: str, rate: float) -> Dict[str, object]:
            item = {**nsc_base, "effective_from": eff_from, "base_rate_pct": rate}
            barrier_dates.wait(timeout=5.0)
            return upsert_savings_instrument(item)

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_new = pool.submit(_date_writer, "2026-11-04", 8.15)
            f_old = pool.submit(_date_writer, "2026-10-15", 7.60)
            f_new.result()
            f_old.result()

        nsc_after = get_savings_instrument_by_id("SAV-NSC")
        frsb_after = get_savings_instrument_by_id("SAV-FRSB-2020")
        self.assertEqual(nsc_after["effective_from"], "2026-11-04")
        self.assertAlmostEqual(nsc_after["base_rate_pct"], 8.15, places=2)
        self.assertEqual(frsb_after["effective_from"], "2026-11-04")
        self.assertAlmostEqual(frsb_after["base_rate_pct"], 8.50, places=2)

        # Race 2: Concurrent same-date revisions (2026-11-08 @ 8.20% vs 8.30%)
        barrier_same = threading.Barrier(2)

        def _same_date_writer(rate: float) -> Dict[str, object]:
            item = {**nsc_after, "effective_from": "2026-11-08", "base_rate_pct": rate}
            barrier_same.wait(timeout=5.0)
            return upsert_savings_instrument(item)

        with ThreadPoolExecutor(max_workers=2) as pool:
            fa = pool.submit(_same_date_writer, 8.20)
            fb = pool.submit(_same_date_writer, 8.30)
            fa.result()
            fb.result()

        nov_revs = [o for o in get_savings_rate_observations("SAV-NSC") if o["effective_from"] == "2026-11-08"]
        self.assertEqual(sorted(o["revision_seq"] for o in nov_revs), [1, 2])
        self.assertEqual(sorted(round(o["base_rate_pct"], 2) for o in nov_revs), [8.20, 8.30])
        active_nov = [o for o in nov_revs if o["superseded_at"] is None]
        superseded_nov = [o for o in nov_revs if o["superseded_at"] is not None]
        self.assertEqual(len(active_nov), 1)
        self.assertEqual(len(superseded_nov), 1)

    def test_04_postgres_cross_db_conflicting_revisions_and_forced_override_sync(self) -> None:
        import core.db.connection as db_conn
        from core.db.savings import (
            get_savings_instrument_by_id,
            get_savings_override_audit_log,
            get_savings_rate_observations,
            upsert_savings_instrument,
        )
        from scripts.sync_from_supabase import sync_via_postgresql_pull
        from scripts.sync_to_supabase import sync_via_postgresql

        with tempfile.TemporaryDirectory(prefix="pkg01-conflict-") as tmp:
            sq_path = Path(tmp) / "split_brain.db"

            # 1. Seed initial 2026-11-01 rev=1 (7.90%) on PG and pull to SQLite so both share rev=1
            nsc_pg = dict(get_savings_instrument_by_id("SAV-NSC"))
            upsert_savings_instrument(
                {**nsc_pg, "base_rate_pct": 7.90, "effective_from": "2026-11-01", "rate_circular_ref": "DEA-SHARED-REV1"}
            )
            sync_via_postgresql_pull(
                str(sq_path),
                self._pg_dsn,
                dry_run=False,
                force=False,
                selected_tables=[
                    "savings_override_audit_log",
                    "savings_rate_observations",
                    "savings_instruments",
                    "tax_rule_registry",
                ],
            )

            # 2. Independently create revision_seq=2 on PG (8.05%) AND revision_seq=2 on SQLite (7.95%)
            r_pg_rev2 = upsert_savings_instrument(
                {**nsc_pg, "base_rate_pct": 8.05, "effective_from": "2026-11-01", "rate_circular_ref": "DEA-PG-AUTHORITATIVE"}
            )
            self.assertEqual(r_pg_rev2["revision_seq"], 2)

            with patch.dict(
                os.environ,
                {
                    "FORCE_LOCAL_SQLITE": "1",
                    "SUPABASE_DB_URL": "",
                    "TEST_DB_PATH": str(sq_path),
                },
            ):
                db_conn._SUPABASE_URL_RESOLVED = False
                db_conn._CACHED_SUPABASE_URL = None
                nsc_sq = dict(get_savings_instrument_by_id("SAV-NSC"))
                r_sq_rev2 = upsert_savings_instrument(
                    {**nsc_sq, "base_rate_pct": 7.95, "effective_from": "2026-11-01", "rate_circular_ref": "DEA-SQLITE-DIVERGENT"}
                )
                self.assertEqual(r_sq_rev2["revision_seq"], 2)
                self.assertNotEqual(r_sq_rev2["observation_id"], r_pg_rev2["observation_id"])

            # 3. Sync SQLite -> PG and PG -> SQLite:
            #    - Zero PK collision despite both having revision_seq=2 on (SAV-NSC, 2026-11-01)
            #    - Conflict detected; SQLite's 7.95% observation marked SUPERSEDED_CONFLICT
            #    - Both DBs converge to authoritative PG (SAV-NSC = 8.05%, SAV-FRSB-2020 = 8.40%)
            db_conn._SUPABASE_URL_RESOLVED = False
            db_conn._CACHED_SUPABASE_URL = None
            up_summary = sync_via_postgresql([], [], self._pg_dsn, sqlite_path=str(sq_path))
            self.assertGreaterEqual(up_summary.get("savings_conflicts_detected", 0), 1)

            pull_summary = sync_via_postgresql_pull(
                str(sq_path),
                self._pg_dsn,
                dry_run=False,
                force=False,
                selected_tables=[
                    "savings_override_audit_log",
                    "savings_rate_observations",
                    "savings_instruments",
                    "tax_rule_registry",
                ],
            )
            self.assertGreaterEqual(
                pull_summary["savings_instruments"].get("conflicts_reconciled", 0)
                + up_summary.get("savings_conflicts_detected", 0),
                1,
            )

            self.assertAlmostEqual(get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"], 8.05, places=2)
            self.assertAlmostEqual(get_savings_instrument_by_id("SAV-FRSB-2020")["base_rate_pct"], 8.40, places=2)
            pg_nov_obs = [
                o for o in get_savings_rate_observations("SAV-NSC") if o["effective_from"] == "2026-11-01"
            ]
            self.assertEqual(len(pg_nov_obs), 3)
            pg_conflict_obs = next(o for o in pg_nov_obs if o["observation_id"] == r_sq_rev2["observation_id"])
            self.assertEqual(pg_conflict_obs["observation_status"], "SUPERSEDED_CONFLICT")
            self.assertEqual(pg_conflict_obs["superseded_by_observation_id"], r_pg_rev2["observation_id"])

            with patch.dict(
                os.environ,
                {
                    "FORCE_LOCAL_SQLITE": "1",
                    "SUPABASE_DB_URL": "",
                    "TEST_DB_PATH": str(sq_path),
                },
            ):
                db_conn._SUPABASE_URL_RESOLVED = False
                db_conn._CACHED_SUPABASE_URL = None
                self.assertAlmostEqual(get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"], 8.05, places=2)
                self.assertAlmostEqual(get_savings_instrument_by_id("SAV-FRSB-2020")["base_rate_pct"], 8.40, places=2)
                sq_nov_obs = [
                    o for o in get_savings_rate_observations("SAV-NSC") if o["effective_from"] == "2026-11-01"
                ]
                self.assertEqual(len(sq_nov_obs), 3)

                # 4. Perform an audited forced rollback in SQLite (override_epoch=1) and sync to PG
                nsc_sq_cur = dict(get_savings_instrument_by_id("SAV-NSC"))
                r_force_sq = upsert_savings_instrument(
                    {**nsc_sq_cur, "base_rate_pct": 7.65, "effective_from": "2026-10-15"},
                    force_overwrite=True,
                    override_reason="Audited DEA retrospective gazette rollback",
                    override_operator="cli:rahul_sharma",
                )
                self.assertEqual(r_force_sq["override_epoch"], 1)

            db_conn._SUPABASE_URL_RESOLVED = False
            db_conn._CACHED_SUPABASE_URL = None
            sync_via_postgresql([], [], self._pg_dsn, sqlite_path=str(sq_path))
            self.assertAlmostEqual(get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"], 7.65, places=2)
            self.assertEqual(get_savings_instrument_by_id("SAV-NSC")["effective_from"], "2026-10-15")
            self.assertAlmostEqual(get_savings_instrument_by_id("SAV-FRSB-2020")["base_rate_pct"], 8.00, places=2)
            self.assertEqual(len(get_savings_override_audit_log("SAV-NSC")), 1)

        db_conn._SUPABASE_URL_RESOLVED = False
        db_conn._CACHED_SUPABASE_URL = None


if __name__ == "__main__":
    unittest.main()
