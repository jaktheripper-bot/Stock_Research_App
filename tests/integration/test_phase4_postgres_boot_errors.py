"""
Integration and regression test suite for Phase 4:
Fix the Two PostgreSQL Boot Errors Logged in Log 1, Log 2, and Log 3.
"""

import os
import unittest
from unittest import mock

from core.db.connection import get_db_connection, init_db
from core.db.sovereign import get_macro_monetary_corridor, DEFAULT_MACRO_RATES
from core.db.digest import get_active_digest_subscribers, get_digest_subscribers, set_user_digest_subscription


class TestPhase4PostgresBootErrors(unittest.TestCase):
    """Empirical verification suite for Phase 4 PostgreSQL fixes."""

    def test_action_4_1_sovereign_macro_schema_and_migration(self):
        """Action 4.1: Verify sovereign_macro_rates column widening in DDL and migration."""
        # 1. Inspect core/db/connection.py for base DDL and migration
        with open("core/db/connection.py", "r", encoding="utf-8") as f:
            conn_code = f.read()

        self.assertIn("v031_widen_sovereign_macro_columns", conn_code)
        self.assertIn("period_label VARCHAR(120) NOT NULL", conn_code)
        self.assertIn("metric_name VARCHAR(120) NOT NULL", conn_code)

        # 2. Verify get_macro_monetary_corridor execution
        corridor = get_macro_monetary_corridor()
        self.assertIsInstance(corridor, dict)
        self.assertIn("repo_rate", corridor)
        repo_data = corridor["repo_rate"]
        self.assertIn("indicator_name", repo_data)
        self.assertIn("period_label", repo_data)

        # 3. Verify that 54-char long period_label is preserved
        self.assertEqual(
            repo_data["period_label"],
            "Current Stance (Neutral / Withdrawal of Accommodation)"
        )
        self.assertGreater(len(repo_data["period_label"]), 50)

    def test_action_4_2_get_active_digest_subscribers_pg_branching(self):
        """Action 4.2: Verify PostgreSQL query branching uses IS TRUE and NOW()."""
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

        # 1. Simulate PostgreSQL connection
        with mock.patch("core.db.digest.get_db_connection", return_value=MockConnection()):
            with mock.patch("core.db.digest.is_postgres_connection", return_value=True):
                # When only_active_pro=False
                executed_queries.clear()
                get_active_digest_subscribers(only_active_pro=False)
                self.assertTrue(len(executed_queries) > 0)
                pg_query_all = executed_queries[0]
                self.assertIn("is_digest_subscribed IS TRUE", pg_query_all)
                self.assertNotIn("is_digest_subscribed = 1", pg_query_all)

                # When only_active_pro=True
                executed_queries.clear()
                get_active_digest_subscribers(only_active_pro=True)
                self.assertTrue(len(executed_queries) > 0)
                pg_query_pro = executed_queries[0]
                self.assertIn("is_digest_subscribed IS TRUE", pg_query_pro)
                self.assertIn("is_subscriber IS TRUE", pg_query_pro)
                self.assertIn("subscription_expires_at > NOW()", pg_query_pro)
                self.assertNotIn("= 1", pg_query_pro)

        # 2. Simulate SQLite connection
        with mock.patch("core.db.digest.get_db_connection", return_value=MockConnection()):
            with mock.patch("core.db.digest.is_postgres_connection", return_value=False):
                # When only_active_pro=False
                executed_queries.clear()
                get_active_digest_subscribers(only_active_pro=False)
                self.assertTrue(len(executed_queries) > 0)
                sqlite_query_all = executed_queries[0]
                self.assertIn("is_digest_subscribed = 1", sqlite_query_all)

                # When only_active_pro=True
                executed_queries.clear()
                get_active_digest_subscribers(only_active_pro=True)
                self.assertTrue(len(executed_queries) > 0)
                sqlite_query_pro = executed_queries[0]
                self.assertIn("is_digest_subscribed = 1", sqlite_query_pro)
                self.assertIn("is_subscriber = 1", sqlite_query_pro)
                self.assertIn("datetime('now')", sqlite_query_pro)

    def test_action_4_2_get_digest_subscribers_alias_and_live_execution(self):
        """Action 4.2: Verify get_digest_subscribers alias and live execution."""
        self.assertEqual(get_digest_subscribers, get_active_digest_subscribers)
        subs = get_active_digest_subscribers(only_active_pro=False)
        self.assertIsInstance(subs, list)


if __name__ == "__main__":
    unittest.main()
