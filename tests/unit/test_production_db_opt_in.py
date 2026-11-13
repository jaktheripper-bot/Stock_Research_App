"""A non-hosted machine reaches a remote (production) database only with ALLOW_PRODUCTION_DB=1.

The laptop's `.env` holds the production address, so without this guard `./run.sh start`, any
script, or a test file run directly would connect to production and run migrations there.
"""
import os
import unittest
from unittest.mock import patch

from core.db import connection as conn_mod

REMOTE = "postgresql://app_user:x@db.example-project.supabase.co:5432/postgres"
LOCAL = "postgresql://postgres:x@127.0.0.1:5432/moat_test"
HOSTED_KEYS = ("RENDER", "RENDER_SERVICE_ID", "FLY_APP_NAME", "K_SERVICE", "ENVIRONMENT", "APP_ENV")
TEST_KEYS = ("TESTING", "PYTEST_CURRENT_TEST", "SKIP_DOTENV_IN_SUBPROCESS", "FORCE_LOCAL_SQLITE", "ALLOW_PRODUCTION_DB")


def _env(**overrides):
    env = {k: v for k, v in os.environ.items() if k not in HOSTED_KEYS + TEST_KEYS + ("SUPABASE_DB_URL",)}
    env.update(overrides)
    return patch.dict(os.environ, env, clear=True)


class TestProductionDbOptIn(unittest.TestCase):
    def setUp(self):
        # Behave like a plain local command, not a test runner.
        self._not_test = patch.object(conn_mod, "_is_unit_test_runtime", return_value=False)
        self._not_test.start()
        self.addCleanup(self._not_test.stop)
        conn_mod._PRODUCTION_DB_BLOCK_WARNED = False

    def test_local_command_with_remote_address_uses_sqlite(self):
        with _env(SUPABASE_DB_URL=REMOTE), self.assertLogs(conn_mod.logger.name, level="WARNING") as cm:
            self.assertIsNone(conn_mod.get_configured_supabase_url())
        self.assertIn("ALLOW_PRODUCTION_DB=1", "\n".join(cm.output))
        self.assertNotIn("supabase.co", "\n".join(cm.output))

    def test_explicit_opt_in_reaches_remote(self):
        with _env(SUPABASE_DB_URL=REMOTE, ALLOW_PRODUCTION_DB="1"):
            self.assertEqual(conn_mod.get_configured_supabase_url(), REMOTE)

    def test_hosted_service_reaches_remote_without_flag(self):
        with _env(SUPABASE_DB_URL=REMOTE, RENDER="true"):
            self.assertEqual(conn_mod.get_configured_supabase_url(), REMOTE)

    def test_local_postgres_needs_no_flag(self):
        with _env(SUPABASE_DB_URL=LOCAL):
            self.assertEqual(conn_mod.get_configured_supabase_url(), LOCAL)

    def test_address_from_secrets_file_is_also_guarded(self):
        with _env(), patch.object(conn_mod, "get_secret", return_value=REMOTE), \
             patch.object(conn_mod, "_SUPABASE_URL_RESOLVED", False), \
             patch.object(conn_mod, "_CACHED_SUPABASE_URL", None):
            self.assertIsNone(conn_mod.get_configured_supabase_url())
        with _env(ALLOW_PRODUCTION_DB="1"), patch.object(conn_mod, "get_secret", return_value=REMOTE), \
             patch.object(conn_mod, "_SUPABASE_URL_RESOLVED", False), \
             patch.object(conn_mod, "_CACHED_SUPABASE_URL", None):
            self.assertEqual(conn_mod.get_configured_supabase_url(), REMOTE)

    def test_force_local_sqlite_still_wins_over_opt_in(self):
        with _env(SUPABASE_DB_URL=REMOTE, ALLOW_PRODUCTION_DB="1", FORCE_LOCAL_SQLITE="1"):
            self.assertIsNone(conn_mod.get_configured_supabase_url())

    def test_manual_workflows_declare_the_opt_in(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        for name in ("scheduled_pipeline.yml", "subscription_renewal_reminder.yml"):
            with self.subTest(workflow=name):
                self.assertIn('ALLOW_PRODUCTION_DB: "1"', (root / ".github/workflows" / name).read_text())



class TestSharedTestRuntimeCheck(unittest.TestCase):
    def test_directly_run_test_file_counts_as_a_test(self):
        from core import runtime

        with patch.dict(os.environ, {k: "" for k in ("TESTING", "ENVIRONMENT", "SKIP_DOTENV_IN_SUBPROCESS", "PYTEST_CURRENT_TEST")}), \
             patch.dict("sys.modules", {"pytest": None}):
            import sys
            modules_without_pytest = {k: v for k, v in sys.modules.items() if k != "pytest"}
            with patch.dict("sys.modules", modules_without_pytest, clear=True):
                for argv0, want in [
                    ("tests/unit/test_x.py", True),
                    ("/repo/tests/security/test_y.py", True),
                    ("-m unittest", True),
                    ("scripts/run_scheduled_pipeline.py", False),
                    ("/usr/local/bin/uvicorn", False),
                ]:
                    with self.subTest(argv0=argv0), patch.object(sys, "argv", [argv0]):
                        self.assertEqual(runtime.is_test_runtime(), want)

    def test_all_detectors_share_the_definition(self):
        from core import config, notify

        with patch("core.runtime.is_test_runtime", return_value=True):
            self.assertTrue(conn_mod._is_unit_test_runtime())
            self.assertTrue(config._is_test_runtime())
            self.assertTrue(notify._is_test_runtime())


if __name__ == "__main__":
    unittest.main()
