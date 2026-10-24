"""
Unit and Integration Test Suite for Wave 12: Distributed Job Lease Lock.
Validates multi-worker concurrency defense across SQLite and PostgreSQL:
1. Dynamic table creation & schema idempotency (`distributed_job_locks`).
2. Atomic lease acquisition and duplicate lock rejection across simulated workers.
3. Heartbeat lease extension by owner vs foreign worker rejection.
4. Expiration timeout recovery: stale/abandoned lease takeover.
5. Context manager semantics: `release_on_exit=True` (interval loops) vs `release_on_exit=False` (daily cron).
6. Multi-worker simulation for the 4 production scheduled tasks:
   - 8:30 AM MF Priority Stock Ingest
   - 8:45 AM Discovery Reel Screening
   - 9:00 AM Research Bouquet Dispatch
   - BSE Watcher 300s Polling Loop
"""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

os.environ["TESTING"] = "1"

from core.db.connection import get_connection, get_placeholder, init_db
from core.db.distributed_lock import (
    WORKER_ID,
    ensure_lock_table_exists,
    acquire_job_lease,
    release_job_lease,
    job_lease,
)


class TestDistributedJobLocks(unittest.TestCase):
    def setUp(self):
        init_db()
        ensure_lock_table_exists()
        self._clear_test_locks()

    def tearDown(self):
        self._clear_test_locks()

    def _clear_test_locks(self):
        conn = get_connection()
        cur = conn.cursor()
        p = get_placeholder()
        try:
            cur.execute(f"DELETE FROM distributed_job_locks WHERE job_name LIKE {p}", ("test_%",))
            cur.execute(f"DELETE FROM distributed_job_locks WHERE job_name LIKE {p}", ("mock_%",))
            cur.execute(f"DELETE FROM distributed_job_locks WHERE job_name = {p}", ("bse_watcher_loop",))
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cur.close()
            conn.close()

    def test_01_ensure_lock_table_exists_is_idempotent(self):
        """Validates that ensure_lock_table_exists can be executed repeatedly without errors."""
        for _ in range(3):
            ensure_lock_table_exists()

        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM distributed_job_locks;")
            count = cur.fetchone()[0]
            self.assertGreaterEqual(count, 0)
        finally:
            cur.close()
            conn.close()

    def test_02_atomic_lease_acquisition_and_conflict(self):
        """Worker 1 acquires lock; Worker 2 cannot acquire while active."""
        job_name = "test_job_concurrency"

        # Worker 1 acquires lease
        acquired1 = acquire_job_lease(job_name, ttl_seconds=60)
        self.assertTrue(acquired1, "Worker 1 failed to acquire uncontested lease")

        # Worker 2 attempts to acquire lease for same job
        with mock.patch("core.db.distributed_lock.WORKER_ID", "simulated_worker_uvicorn_2:9999:abc123"):
            acquired2 = acquire_job_lease(job_name, ttl_seconds=60)
            self.assertFalse(acquired2, "Worker 2 acquired an active, unexpired lease owned by Worker 1")

        # Worker 1 re-acquires (heartbeat extension)
        acquired1_renew = acquire_job_lease(job_name, ttl_seconds=120)
        self.assertTrue(acquired1_renew, "Worker 1 failed to refresh its own lease")

        # Worker 1 releases
        release_job_lease(job_name)

        # Worker 2 now succeeds
        with mock.patch("core.db.distributed_lock.WORKER_ID", "simulated_worker_uvicorn_2:9999:abc123"):
            acquired2_after_release = acquire_job_lease(job_name, ttl_seconds=60)
            self.assertTrue(acquired2_after_release, "Worker 2 failed to acquire lease after Worker 1 released")

    def test_03_expired_lease_takeover(self):
        """Expired lease can be acquired immediately by a new worker."""
        job_name = "test_job_expiry"
        conn = get_connection()
        cur = conn.cursor()
        p = get_placeholder()

        # Seed expired lock directly
        past_utc = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        try:
            cur.execute(
                f"INSERT INTO distributed_job_locks (job_name, locked_by, locked_at, expires_at) VALUES ({p}, {p}, {p}, {p})",
                (job_name, "stale_crashed_worker:1234:xyz", past_utc, past_utc),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

        # Active worker acquires expired lease
        acquired = acquire_job_lease(job_name, ttl_seconds=300)
        self.assertTrue(acquired, "Worker failed to acquire expired/abandoned lease")

        # Verify ownership changed to current worker
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT locked_by FROM distributed_job_locks WHERE job_name = {p}", (job_name,))
            row = cur.fetchone()
            self.assertEqual(row[0], WORKER_ID)
        finally:
            cur.close()
            conn.close()

    def test_04_context_manager_release_on_exit_true(self):
        """Interval loop semantics: lease released upon context exit for next cycle."""
        job_name = "test_interval_loop"

        with job_lease(job_name, ttl_seconds=60, release_on_exit=True) as acquired:
            self.assertTrue(acquired)
            # Inside block, another worker is blocked
            with mock.patch("core.db.distributed_lock.WORKER_ID", "worker_other"):
                self.assertFalse(acquire_job_lease(job_name, ttl_seconds=60))

        # Outside block, lease is released; other worker can acquire
        with mock.patch("core.db.distributed_lock.WORKER_ID", "worker_other"):
            self.assertTrue(acquire_job_lease(job_name, ttl_seconds=60))

    def test_05_context_manager_release_on_exit_false(self):
        """Daily cron semantics: lease persists after exit to block second worker on same day."""
        job_name = "test_daily_cron_task"

        with job_lease(job_name, ttl_seconds=1800, release_on_exit=False) as acquired:
            self.assertTrue(acquired)

        # After exiting block, lease remains held until TTL expires
        with mock.patch("core.db.distributed_lock.WORKER_ID", "worker_second_uvicorn"):
            second_attempt = acquire_job_lease(job_name, ttl_seconds=1800)
            self.assertFalse(second_attempt, "Second worker executed daily cron task already completed by first worker")

    def test_06_four_production_scheduled_tasks_multi_worker_defense(self):
        """Empirically simulates 2 Uvicorn workers racing for the 4 production scheduled tasks."""
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        w1 = "uvicorn_worker_1:8000:a1b2c3"
        w2 = "uvicorn_worker_2:8000:d4e5f6"

        tasks = [
            f"mf_stock_ingest_{today_str}",
            f"discovery_reel_{today_str}",
            f"morning_bouquet_{today_str}",
            "bse_watcher_loop",
        ]

        for task_name in tasks:
            # Worker 1 acquires first
            with mock.patch("core.db.distributed_lock.WORKER_ID", w1):
                acquired_w1 = acquire_job_lease(task_name, ttl_seconds=1800)
                self.assertTrue(acquired_w1, f"Worker 1 failed to acquire lease for {task_name}")

            # Worker 2 attempts same task simultaneously
            with mock.patch("core.db.distributed_lock.WORKER_ID", w2):
                acquired_w2 = acquire_job_lease(task_name, ttl_seconds=1800)
                self.assertFalse(acquired_w2, f"Worker 2 acquired conflicting lease for {task_name}, risking duplicate execution!")

    def test_07_context_manager_release_on_failure_true(self):
        """Failure semantics: mid-run exception immediately releases lease for retry."""
        job_name = "test_failing_task_retry"

        with self.assertRaises(RuntimeError):
            with job_lease(job_name, ttl_seconds=1800, release_on_exit=False, release_on_failure=True) as acquired:
                self.assertTrue(acquired)
                raise RuntimeError("Mid-flight crash")

        # Because release_on_failure=True, the lock was freed upon exception
        with mock.patch("core.db.distributed_lock.WORKER_ID", "failover_worker"):
            retry_acquired = acquire_job_lease(job_name, ttl_seconds=1800)
            self.assertTrue(retry_acquired, "Failover worker should acquire lease immediately after mid-flight crash")

    def test_08_context_manager_release_on_failure_false(self):
        """When release_on_failure=False and release_on_exit=False, lease remains held on error."""
        job_name = "test_failing_task_no_release"

        with self.assertRaises(RuntimeError):
            with job_lease(job_name, ttl_seconds=1800, release_on_exit=False, release_on_failure=False) as acquired:
                self.assertTrue(acquired)
                raise RuntimeError("Mid-flight crash without release")

        # Lease should remain held until TTL
        with mock.patch("core.db.distributed_lock.WORKER_ID", "failover_worker"):
            retry_acquired = acquire_job_lease(job_name, ttl_seconds=1800)
            self.assertFalse(retry_acquired, "Lease should still be held when release_on_failure=False")


if __name__ == "__main__":
    unittest.main()

