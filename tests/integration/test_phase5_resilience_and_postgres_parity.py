"""
Integration and regression test suite for Phase 5:
Verification & Living Documentation Sync across:
1. /funds/{scheme_code} GET requests for unindexed/locked schemes (no audit_single_fund_daily invocation or memory leaks).
2. _FUNDAMENTALS_CACHE and FUND_AUDIT_TASKS maxsize eviction enforcement.
3. get_active_digest_subscribers and sovereign_macro_rates seeding cleanly under both SQLite and PostgreSQL rules.
"""

import time
import unittest
from unittest import mock
from starlette.testclient import TestClient

from web.main import app
from core.analysis.fundamentals import _FUNDAMENTALS_CACHE, _BoundedFundamentalsCache
from core.analysis.fund_overlap_auditor import (
    FUND_AUDIT_TASKS,
    MAX_FUND_AUDIT_TASKS,
    _bound_fund_audit_tasks,
)
from core.db.connection import get_db_connection, is_postgres_connection
from core.db.digest import get_active_digest_subscribers, get_digest_subscribers
from core.db.sovereign import get_macro_monetary_corridor, DEFAULT_MACRO_RATES


class TestPhase5FundDossierGetResilience(unittest.TestCase):
    """Verifies GET /funds/{scheme_code} is memory-safe and never triggers synchronous audit."""

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_locked_scheme_does_not_invoke_audit_single_fund_daily(self):
        """Action 1.1 verification: GET request on locked scheme must not invoke audit_single_fund_daily."""
        with mock.patch("core.analysis.fund_overlap_auditor.audit_single_fund_daily") as mock_audit:
            # Scheme 120503 or 122639 are canonical mutual funds seeded in the database
            response = self.client.get("/funds/120503")
            self.assertEqual(response.status_code, 200)
            mock_audit.assert_not_called()

    def test_unindexed_or_invalid_scheme_does_not_invoke_audit_or_leak(self):
        """Action 1.2 verification: Invalid or crawler-noise scheme codes must 404 without invoking audit."""
        with mock.patch("core.analysis.fund_overlap_auditor.audit_single_fund_daily") as mock_audit:
            for invalid_code in ["robots.txt", "wp-admin", "NON_EXISTENT_ALPHA", "999999999"]:
                resp = self.client.get(f"/funds/{invalid_code}")
                self.assertIn(resp.status_code, [404, 400])
                mock_audit.assert_not_called()

    def test_repeated_get_does_not_allocate_background_tasks(self):
        """Verify that GET requests do not pollute FUND_AUDIT_TASKS or leak memory."""
        initial_task_count = len(FUND_AUDIT_TASKS)
        with mock.patch("core.analysis.fund_overlap_auditor.audit_single_fund_daily") as mock_audit:
            for _ in range(5):
                resp = self.client.get("/funds/120503")
                self.assertEqual(resp.status_code, 200)
                mock_audit.assert_not_called()
        self.assertEqual(len(FUND_AUDIT_TASKS), initial_task_count)


class TestPhase5MaxsizeEviction(unittest.TestCase):
    """Verifies _FUNDAMENTALS_CACHE and FUND_AUDIT_TASKS strictly enforce maxsize bounds."""

    def test_fundamentals_cache_strictly_enforces_maxsize(self):
        """Action 2.4 verification: _FUNDAMENTALS_CACHE must never exceed maxsize=64."""
        test_cache = _BoundedFundamentalsCache(maxsize=64, ttl_seconds=3600.0)
        base_time = time.time()

        # Insert 75 distinct items
        for i in range(75):
            test_cache[f"TICKER_{i}"] = (base_time + i, {"pe": float(i), "roe": 15.0})

        # Length must be bounded at maxsize
        self.assertEqual(len(test_cache), 64)

        # Oldest items (TICKER_0 .. TICKER_10) should have been evicted
        self.assertNotIn("TICKER_0", test_cache)
        self.assertNotIn("TICKER_5", test_cache)
        self.assertNotIn("TICKER_10", test_cache)

        # Most recent items (TICKER_60 .. TICKER_74) must be present
        self.assertIn("TICKER_60", test_cache)
        self.assertIn("TICKER_74", test_cache)

    def test_fundamentals_cache_prunes_expired_entries(self):
        """Verifies that expired entries are pruned on write operations."""
        test_cache = _BoundedFundamentalsCache(maxsize=64, ttl_seconds=10.0)
        now = time.time()

        # Insert expired entries
        test_cache["EXPIRED_1"] = (now - 20.0, {"pe": 10.0})
        test_cache["EXPIRED_2"] = (now - 15.0, {"pe": 12.0})

        # Insert fresh entry which triggers pruning
        test_cache["FRESH_1"] = (now, {"pe": 14.0})

        self.assertNotIn("EXPIRED_1", test_cache)
        self.assertNotIn("EXPIRED_2", test_cache)
        self.assertIn("FRESH_1", test_cache)

    def test_fund_audit_tasks_strictly_enforces_maxsize(self):
        """Action 1.5 verification: FUND_AUDIT_TASKS bounds itself to MAX_FUND_AUDIT_TASKS=64."""
        # Save original tasks
        original_tasks = dict(FUND_AUDIT_TASKS)
        try:
            FUND_AUDIT_TASKS.clear()
            # Populate 80 tasks (mix of completed and running)
            for i in range(80):
                status = "COMPLETED" if i < 60 else "PROCESSING"
                created_iso = f"2026-10-23T08:{i:02d}:00"
                FUND_AUDIT_TASKS[f"task_{i:03d}"] = {
                    "task_id": f"task_{i:03d}",
                    "status": status,
                    "created_at": created_iso,
                    "completed_at": created_iso if status == "COMPLETED" else None,
                }

            # Enforce bounds
            _bound_fund_audit_tasks(MAX_FUND_AUDIT_TASKS)

            self.assertLessEqual(len(FUND_AUDIT_TASKS), MAX_FUND_AUDIT_TASKS)
            self.assertEqual(len(FUND_AUDIT_TASKS), 64)

            # Oldest completed tasks should be evicted first
            self.assertNotIn("task_000", FUND_AUDIT_TASKS)
            self.assertNotIn("task_010", FUND_AUDIT_TASKS)

            # Active/processing tasks should still be present
            self.assertIn("task_079", FUND_AUDIT_TASKS)
            self.assertIn("task_070", FUND_AUDIT_TASKS)
        finally:
            FUND_AUDIT_TASKS.clear()
            FUND_AUDIT_TASKS.update(original_tasks)


class TestPhase5PostgresAndSqliteParity(unittest.TestCase):
    """Verifies get_active_digest_subscribers and sovereign_macro_rates parity under both engines."""

    def test_get_active_digest_subscribers_dialect_parity(self):
        """Action 4.2 verification: Strict boolean syntax in PostgreSQL vs = 1 in SQLite."""
        executed_queries = []

        class MockCursor:
            def execute(self, sql, params=None):
                executed_queries.append(sql)

            def fetchall(self):
                return []

            def close(self):
                pass

        class MockConnection:
            def cursor(self):
                return MockCursor()

            def close(self):
                pass

        # 1. PostgreSQL rules: IS TRUE and NOW()
        with mock.patch("core.db.digest.get_db_connection", return_value=MockConnection()):
            with mock.patch("core.db.digest.is_postgres_connection", return_value=True):
                executed_queries.clear()
                get_active_digest_subscribers(only_active_pro=True)
                self.assertTrue(len(executed_queries) > 0)
                pg_sql = executed_queries[0]

                # Assert strict PostgreSQL booleans
                self.assertIn("is_digest_subscribed IS TRUE", pg_sql)
                self.assertIn("is_subscriber IS TRUE", pg_sql)
                self.assertIn("subscription_expires_at > NOW()", pg_sql)
                self.assertNotIn("= 1", pg_sql)
                self.assertNotIn("datetime('now')", pg_sql)

        # 2. SQLite rules: = 1 and datetime('now')
        with mock.patch("core.db.digest.get_db_connection", return_value=MockConnection()):
            with mock.patch("core.db.digest.is_postgres_connection", return_value=False):
                executed_queries.clear()
                get_active_digest_subscribers(only_active_pro=True)
                self.assertTrue(len(executed_queries) > 0)
                sqlite_sql = executed_queries[0]

                # Assert SQLite compatibility
                self.assertIn("is_digest_subscribed = 1", sqlite_sql)
                self.assertIn("is_subscriber = 1", sqlite_sql)
                self.assertIn("datetime('now')", sqlite_sql)
                self.assertNotIn("IS TRUE", sqlite_sql)

        # 3. Live local execution on SQLite
        subs = get_active_digest_subscribers(only_active_pro=False)
        self.assertIsInstance(subs, list)
        self.assertEqual(get_digest_subscribers, get_active_digest_subscribers)

    def test_sovereign_macro_rates_seeds_cleanly_under_sqlite_and_postgres_rules(self):
        """Action 4.1 verification: Seeding sovereign_macro_rates preserves 54-char string and satisfies VARCHAR(120)."""
        # 1. Inspect live macro rates seeding via get_macro_monetary_corridor
        corridor = get_macro_monetary_corridor()
        self.assertIsInstance(corridor, dict)
        self.assertIn("repo_rate", corridor)

        repo = corridor["repo_rate"]
        period = repo.get("period_label") or repo.get("period")
        self.assertEqual(period, "Current Stance (Neutral / Withdrawal of Accommodation)")
        self.assertEqual(len(period), 54)
        self.assertLessEqual(len(period), 120)

        # 2. Verify all default macro items fit comfortably within VARCHAR(120)
        for item in DEFAULT_MACRO_RATES:
            name = item.get("metric_name") or item.get("indicator_name", "")
            period_label = item.get("period_label", "")
            self.assertLessEqual(len(name), 120, f"metric_name exceeds VARCHAR(120): {name}")
            self.assertLessEqual(len(period_label), 120, f"period_label exceeds VARCHAR(120): {period_label}")

        # 3. Verify PostgreSQL base DDL and migration in core/db/connection.py
        with open("core/db/connection.py", "r", encoding="utf-8") as f:
            conn_py = f.read()

        self.assertIn("metric_name VARCHAR(120) NOT NULL", conn_py)
        self.assertIn("period_label VARCHAR(120) NOT NULL", conn_py)
        self.assertIn("v031_widen_sovereign_macro_columns", conn_py)
        self.assertIn("ALTER TABLE sovereign_macro_rates ALTER COLUMN period_label TYPE VARCHAR(120);", conn_py)
        self.assertIn("ALTER TABLE sovereign_macro_rates ALTER COLUMN metric_name TYPE VARCHAR(120);", conn_py)


if __name__ == "__main__":
    unittest.main()
