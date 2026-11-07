"""
Real PostgreSQL checks for P0 admin-credit serialization.

This suite intentionally skips unless MOATNOMICS_TEST_POSTGRES_DSN is set.
Never point that variable at a production database.
"""
import json
import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


POSTGRES_DSN = os.environ.get("MOATNOMICS_TEST_POSTGRES_DSN", "").strip()


@unittest.skipUnless(POSTGRES_DSN, "MOATNOMICS_TEST_POSTGRES_DSN is not configured")
class TestPostgresCreditGrantConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "test" not in POSTGRES_DSN.lower():
            raise RuntimeError(
                "Refusing PostgreSQL integration test: DSN must identify a dedicated test database."
            )

        import core.db.connection as db
        from core.db.connection import init_db

        cls.env = patch.dict(
            os.environ,
            {
                "TESTING": "1",
                "TEST_SUPABASE": "1",
                "SUPABASE_DB_URL": POSTGRES_DSN,
                "FORCE_LOCAL_SQLITE": "0",
            },
            clear=False,
        )
        cls.env.start()
        db._DB_INITIALIZED = False
        db._INITIALIZED_DBS.clear()
        db._SUPABASE_URL_RESOLVED = False
        db._PG_AVAILABLE = None
        init_db(force=True)

        from core.db.connection import get_db_connection, is_postgres_connection

        probe = get_db_connection()
        try:
            if not is_postgres_connection(probe):
                raise RuntimeError(
                    "PostgreSQL integration test resolved a non-PostgreSQL connection; "
                    "check TEST_SUPABASE / SUPABASE_DB_URL."
                )
        finally:
            probe.close()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        import core.db.connection as db

        db._DB_INITIALIZED = False
        db._INITIALIZED_DBS.clear()
        db._SUPABASE_URL_RESOLVED = False
        db._PG_AVAILABLE = None

    def setUp(self):
        from core.db.connection import get_db_connection

        suffix = uuid.uuid4().hex[:12]
        self.actor = f"admin_{suffix}@example.test"
        self.other_actor = f"other_{suffix}@example.test"
        self.alice_id = f"usr_alice_{suffix}"
        self.bob_id = f"usr_bob_{suffix}"
        self.carol_id = f"usr_carol_{suffix}"
        self.dan_id = f"usr_dan_{suffix}"
        self.alice_email = f"alice_{suffix}@example.test"
        self.bob_email = f"bob_{suffix}@example.test"
        self.carol_email = f"carol_{suffix}@example.test"
        self.dan_email = f"dan_{suffix}@example.test"

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO user_accounts
                    (id, email, full_name, credits_balance, subscription_tier)
                VALUES
                    (%s, %s, 'Alice Sharma', 0, 'free'),
                    (%s, %s, 'Bob Verma', 0, 'free'),
                    (%s, %s, 'Carol Sen', 0, 'free'),
                    (%s, %s, 'Dan Joshi', 0, 'free')
                """,
                (
                    self.alice_id,
                    self.alice_email,
                    self.bob_id,
                    self.bob_email,
                    self.carol_id,
                    self.carol_email,
                    self.dan_id,
                    self.dan_email,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _concurrent_grants(self, calls):
        from core.db.admin import admin_grant_user_credits

        barrier = threading.Barrier(len(calls))

        def grant(actor, target, amount):
            barrier.wait(timeout=10)
            return admin_grant_user_credits(actor, target, amount)

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            futures = [pool.submit(grant, *call) for call in calls]
            return [future.result(timeout=30) for future in futures]

    def test_target_cap_serializes_across_two_administrators(self):
        results = self._concurrent_grants(
            (
                (self.actor, self.alice_email, 6.0),
                (self.other_actor, self.alice_id, 6.0),
            )
        )
        self.assertEqual(sum(bool(item["success"]) for item in results), 1, results)
        self.assertIn(
            "24h target grant limit exceeded",
            next(item["error"] for item in results if not item["success"]),
        )

    def test_actor_cap_serializes_across_two_targets(self):
        from core.db.admin import admin_grant_user_credits

        self.assertTrue(
            admin_grant_user_credits(self.actor, self.alice_id, 10.0)["success"]
        )
        self.assertTrue(
            admin_grant_user_credits(self.actor, self.bob_id, 10.0)["success"]
        )

        results = self._concurrent_grants(
            (
                (self.actor, self.carol_id, 4.0),
                (self.actor, self.dan_id, 4.0),
            )
        )
        self.assertEqual(sum(bool(item["success"]) for item in results), 1, results)
        self.assertIn(
            "24h administrator grant limit exceeded",
            next(item["error"] for item in results if not item["success"]),
        )


if __name__ == "__main__":
    unittest.main()
