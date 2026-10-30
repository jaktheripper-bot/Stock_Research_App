"""Unit and contract tests for bidirectional Supabase sync, PG pool/IST safety, and GenAI HTTP timeouts."""

import ast
import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]


class TestPipelineSyncAndTimeouts(unittest.TestCase):
    """Verifies all 5 multi-asset pipeline & sync hardening contracts."""

    def test_all_genai_clients_configure_http_timeout(self):
        """Every google.genai Client(...) instantiation must specify bounded http_options timeout."""
        targets = [
            "core/analysis/fund_overlap_auditor.py",
            "core/analysis/dossier_report_synthesis.py",
            "core/analysis/delta.py",
            "core/audit/project_auditor.py",
            "core/agents/copilot/research_desk.py",
            "core/agents/copilot/admin_copilot.py",
            "scripts/ai_auditor.py",
        ]
        checked_calls = 0
        for rel in targets:
            path = ROOT / rel
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                is_genai_client = (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "Client"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "genai"
                ) or (isinstance(node.func, ast.Name) and node.func.id == "Client")
                if not is_genai_client:
                    continue
                checked_calls += 1
                kw_names = {kw.arg for kw in node.keywords if kw.arg}
                self.assertIn(
                    "http_options",
                    kw_names,
                    f"{rel}:{node.lineno} instantiates genai Client without http_options timeout",
                )
        self.assertGreaterEqual(checked_calls, 8)

    def test_pg_pool_teardown_and_transaction_pooler_ist_safety(self):
        """Session pool (:5432) caches IST TZ per socket; transaction pool (:6543) re-applies on each checkout."""
        import core.db.connection as conn_mod

        session_conn = MagicMock()
        session_conn.dsn = "host=aws-0-ap-south-1.pooler.supabase.com port=5432 dbname=postgres"
        conn_mod._CONN_TZ_SET.discard(id(session_conn))

        conn_mod._ensure_pg_ist_timezone(session_conn)
        conn_mod._ensure_pg_ist_timezone(session_conn)
        self.assertEqual(session_conn.commit.call_count, 1)
        self.assertIn(id(session_conn), conn_mod._CONN_TZ_SET)

        tx_conn = MagicMock()
        tx_conn.dsn = "host=aws-0-ap-south-1.pooler.supabase.com port=6543 dbname=postgres"
        conn_mod._CONN_TZ_SET.discard(id(tx_conn))

        conn_mod._ensure_pg_ist_timezone(tx_conn)
        conn_mod._ensure_pg_ist_timezone(tx_conn)
        self.assertEqual(tx_conn.commit.call_count, 2)
        self.assertNotIn(id(tx_conn), conn_mod._CONN_TZ_SET)

        fake_pool = MagicMock()
        with conn_mod._PG_POOL_LOCK:
            conn_mod._PG_POOLS["postgresql://unit-test"] = fake_pool
        conn_mod.close_all_pg_pools()
        fake_pool.closeall.assert_called_once()
        self.assertNotIn("postgresql://unit-test", conn_mod._PG_POOLS)

    def test_explicit_empty_supabase_url_forces_local_sqlite(self):
        """SUPABASE_DB_URL='' or FORCE_LOCAL_SQLITE=1 must bypass configured secrets."""
        import core.db.connection as conn_mod

        with patch.dict(os.environ, {"SUPABASE_DB_URL": "", "TESTING": "0"}, clear=False):
            self.assertIsNone(conn_mod.get_configured_supabase_url())
        with patch.dict(os.environ, {"FORCE_LOCAL_SQLITE": "1", "TESTING": "0"}, clear=False):
            self.assertIsNone(conn_mod.get_configured_supabase_url())

    def test_coerce_pg_date_handles_sentinels_and_valid_dates(self):
        """Sentinel strings like 'Pending Monthly Disclosure' coerce to None instead of crashing PG DATE."""
        from scripts.sync_to_supabase import _coerce_pg_date

        self.assertIsNone(_coerce_pg_date(None))
        self.assertIsNone(_coerce_pg_date(""))
        self.assertIsNone(_coerce_pg_date("Pending Monthly Disclosure"))
        self.assertIsNone(_coerce_pg_date("N/A"))
        self.assertEqual(_coerce_pg_date("2026-10-29"), date(2026, 10, 29))
        self.assertEqual(_coerce_pg_date("2026-10-30 08:30:00+05:30"), date(2026, 10, 30))
        self.assertEqual(_coerce_pg_date(date(2026, 10, 28)), date(2026, 10, 28))

    def test_sync_from_supabase_type_normalization_and_freshness_guards(self):
        """Verifies Decimal/UTC->IST conversion, anti-Potemkin report protection, and edition-atomic pull."""
        from scripts.sync_from_supabase import (
            normalize_pg_value_for_sqlite,
            should_apply_incoming_row,
            sync_via_postgresql_pull,
        )

        self.assertEqual(normalize_pg_value_for_sqlite(Decimal("2450.75")), 2450.75)
        self.assertEqual(normalize_pg_value_for_sqlite(True), 1)
        self.assertEqual(normalize_pg_value_for_sqlite(False), 0)
        self.assertEqual(normalize_pg_value_for_sqlite(date(2026, 10, 30)), "2026-10-30")
        utc_dt = datetime(2026, 10, 29, 22, 58, 5, tzinfo=timezone.utc)
        self.assertEqual(normalize_pg_value_for_sqlite(utc_dt), "2026-10-30 04:28:05+05:30")

        # Anti-Potemkin guard: never overwrite >=500-char local report with a <500-char stub
        compiled_local = {"ticker": "INFY", "report_text": "A" * 800, "timestamp": "2026-10-29 10:00:00+05:30"}
        stub_remote = {"ticker": "INFY", "report_text": "short stub", "timestamp": "2026-10-30 10:00:00+05:30"}
        self.assertFalse(should_apply_incoming_row("reports", stub_remote, compiled_local, "timestamp"))

        # Freshness guard: preserve newer local row
        older_remote = {"ticker": "INFY", "report_text": "B" * 900, "timestamp": "2026-10-28 10:00:00+05:30"}
        self.assertFalse(should_apply_incoming_row("reports", older_remote, compiled_local, "timestamp"))

        newer_remote = {"ticker": "INFY", "report_text": "B" * 900, "timestamp": "2026-10-30 09:00:00+05:30"}
        self.assertTrue(should_apply_incoming_row("reports", newer_remote, compiled_local, "timestamp"))

        # End-to-end edition-atomic discovery_reel pull against an isolated temp SQLite DB
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_db = os.path.join(tmpdir, "pull_test.db")
            conn = sqlite3.connect(tmp_db)
            conn.execute(
                """
                CREATE TABLE discovery_reel (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    edition_date TEXT,
                    ticker TEXT,
                    company_name TEXT,
                    current_price REAL,
                    is_active INTEGER,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO discovery_reel (edition_date, ticker, company_name, current_price, is_active, created_at) "
                "VALUES ('2026-10-29', 'OLDTICKER', 'Old Co', 100.0, 1, '2026-10-29 08:30:00+05:30')"
            )
            conn.commit()
            conn.close()

            fake_pg_cur = MagicMock()
            fake_pg_cur.fetchall.return_value = [
                {
                    "id": 999,
                    "edition_date": date(2026, 10, 29),
                    "ticker": "NEWTICKER1",
                    "company_name": "New Co 1",
                    "current_price": Decimal("512.40"),
                    "is_active": True,
                    "created_at": datetime(2026, 10, 29, 4, 0, 0, tzinfo=timezone.utc),
                },
                {
                    "id": 1000,
                    "edition_date": date(2026, 10, 29),
                    "ticker": "NEWTICKER2",
                    "company_name": "New Co 2",
                    "current_price": Decimal("725.10"),
                    "is_active": True,
                    "created_at": datetime(2026, 10, 29, 4, 0, 0, tzinfo=timezone.utc),
                },
            ]
            fake_pg_conn = MagicMock()
            fake_pg_conn.cursor.return_value.__enter__.return_value = fake_pg_cur

            with patch("scripts.sync_from_supabase.connect_supabase_pg", return_value=fake_pg_conn), \
                 patch("scripts.sync_from_supabase._ensure_local_sqlite_schema"):
                summary = sync_via_postgresql_pull(
                    sqlite_path=tmp_db,
                    db_url="postgresql://mock",
                    selected_tables=["discovery_reel"],
                )

            self.assertEqual(summary["discovery_reel"]["updated"], 2)
            vconn = sqlite3.connect(tmp_db)
            rows = vconn.execute(
                "SELECT ticker, current_price, is_active, created_at FROM discovery_reel ORDER BY ticker"
            ).fetchall()
            vconn.close()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "NEWTICKER1")
            self.assertAlmostEqual(rows[0][1], 512.40)
            self.assertEqual(rows[0][2], 1)
            self.assertTrue(rows[0][3].endswith("+05:30"))


if __name__ == "__main__":
    unittest.main()
