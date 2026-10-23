"""
Integration and regression test suite for Phase 3:
Consolidate Uvicorn Workers & Guard Boot-Time Schedulers.
"""

import os
import unittest
from unittest import mock

from core.db.sovereign import get_etf_count, get_etf_matrix
from core.db.connection import DB_POOL_MAX, DB_POOL_MIN
from core.db.distributed_lock import job_lease


class TestPhase3WorkersAndBootSchedulers(unittest.TestCase):
    """Empirical verification suite for Phase 3 worker consolidation and boot guards."""

    def test_action_3_1_render_yaml_and_dockerfile_configuration(self):
        """Action 3.1: Verify render.yaml and Dockerfile match single-worker and memory settings."""
        # 1. Inspect render.yaml
        with open("render.yaml", "r", encoding="utf-8") as f:
            render_text = f.read()

        self.assertIn("--workers 1", render_text)
        self.assertIn("--limit-concurrency 60", render_text)
        self.assertIn("--timeout-keep-alive 5", render_text)
        self.assertIn("MALLOC_TRIM_THRESHOLD_", render_text)
        self.assertIn("PYTHONMALLOC", render_text)
        self.assertIn("value: \"65536\"", render_text)
        self.assertIn("value: malloc", render_text)

        # 2. Inspect Dockerfile
        with open("Dockerfile", "r", encoding="utf-8") as f:
            docker_content = f.read()

        self.assertIn("MALLOC_TRIM_THRESHOLD_=65536", docker_content)
        self.assertIn("PYTHONMALLOC=malloc", docker_content)
        self.assertIn("--workers 1", docker_content)
        self.assertIn("--limit-concurrency 60", docker_content)
        self.assertIn("--timeout-keep-alive 5", docker_content)

    def test_action_3_2_boot_scheduler_lease_guards(self):
        """Action 3.2: Verify boot catch-up blocks acquire distributed lease to prevent duplicate runs."""
        today_str = "2026-10-23"
        lease_name = f"boot_catchup_amfi_{today_str}_test"

        try:
            # Acquire the lease once with worker 1
            with job_lease(lease_name, ttl_seconds=60, release_on_exit=False) as acq1:
                self.assertTrue(acq1, "First boot worker should acquire catch-up lease")

                # A second concurrent worker process trying to run catch-up on boot must be denied
                with mock.patch("core.db.distributed_lock.WORKER_ID", "remote_worker_pid_99999"):
                    with job_lease(lease_name, ttl_seconds=60, release_on_exit=False) as acq2:
                        self.assertFalse(acq2, "Second boot worker must not acquire duplicate catch-up lease")
        finally:
            from core.db.distributed_lock import release_job_lease
            release_job_lease(lease_name, force=True)

    def test_action_3_3_lightweight_get_etf_count_helper(self):
        """Action 3.3: Verify get_etf_count executes lightweight count matching get_etf_matrix length."""
        count = get_etf_count()
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 0)

        # Confirm count matches table row count returned by matrix query
        matrix_len = len(get_etf_matrix(category=None))
        self.assertEqual(count, matrix_len)

    def test_action_3_4_db_pool_max_lowered_to_10(self):
        """Action 3.4: Verify DB_POOL_MAX default lowered from 20 to 10."""
        # Check current imported module setting
        self.assertLessEqual(DB_POOL_MAX, 10)
        self.assertGreaterEqual(DB_POOL_MAX, DB_POOL_MIN)


if __name__ == "__main__":
    unittest.main()
