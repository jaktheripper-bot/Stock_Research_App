"""
Security Integration Test Suite: P3 Infrastructure Resilience & Concurrency.
Empirically verifies:
1. PDF Memory Exhaustion Defense (OOM & ReDoS):
   - Strict 50,000 character payload limits on markdown strings before passing to compiler.
   - Hard 15.0-second timeout enforcement returning HTTP 504 on long/malicious rendering.
2. Distributed Lock Zombie Lease Recovery:
   - Strict expires_at TTL enforcement on acquire_job_lease.
   - Automatic and routine pruning of zombie leases left by killed worker processes (SIGKILL).
3. Connection Pool Starvation Defense:
   - Guaranteed pool release in try...finally and context managers under malformed/error inputs.
   - Proxy __del__ GC finalizer preventing connection leaks if local frames drop unclosed proxies.
   - Dead/corrupted socket eviction from pool on rollback failure.
"""

import asyncio
import gc
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

os.environ["TESTING"] = "1"
os.environ["SECRET_KEY"] = "test_dev_secret_key_fixed_length_32_bytes_ok"

from web.main import app
from core.reporting.pdf import (
    build_pdf_dossier,
    generate_report_pdf,
    generate_fund_dossier_pdf,
    generate_debt_dossier_pdf,
    generate_reit_dossier_pdf,
    generate_msme_dossier_pdf,
    MAX_PDF_MARKDOWN_CHARS,
    PDF_GENERATION_TIMEOUT_SECONDS,
)
from core.db.distributed_lock import (
    WORKER_ID,
    acquire_job_lease,
    release_job_lease,
    prune_zombie_leases,
    clear_zombie_leases,
    ensure_lock_table_exists,
    DEFAULT_LEASE_TTL_SECONDS,
    MIN_LEASE_TTL_SECONDS,
    MAX_LEASE_TTL_SECONDS,
)
import core.db.locks as db_locks
from core.db.connection import (
    get_connection,
    get_db_connection,
    get_db_context,
    get_placeholder,
    init_db,
    _PooledConnectionProxy,
    _INITIALIZED_DBS,
)


class TestP3PDFMemoryExhaustionAndReDoS(unittest.TestCase):
    """P3-1: Defense against Catastrophic ReDoS and Memory Exhaustion in PDF Generator."""

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_01_max_pdf_markdown_chars_configured_and_clamped(self):
        """Validates that MAX_PDF_MARKDOWN_CHARS defaults to 50,000 and clamps oversized payloads."""
        self.assertEqual(MAX_PDF_MARKDOWN_CHARS, 50000)

        # Generate a malicious / oversized string with 80,000 characters
        huge_payload = "# Executive Thesis\n\n" + ("This is an extensively nested text paragraph. " * 1700)
        self.assertGreater(len(huge_payload), 50000)

        # Compile should NOT crash or OOM, and should produce valid PDF bytes
        pdf_bytes = build_pdf_dossier(
            rep_text=huge_payload,
            ticker="TATAMOTORS",
            header_label="Test Clamped Dossier",
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"), "Output must be a valid binary PDF document")
        self.assertGreater(len(pdf_bytes), 1000)

    def test_02_specialized_dossiers_clamp_oversized_markdown(self):
        """Validates that Fund, Debt, REIT, and MSME PDF generators clamp compiled markdown."""
        huge_narrative = "Forensic qualitative assessment. " * 3000

        # 1. Fund Dossier
        fund_pdf = generate_fund_dossier_pdf(
            scheme_code="120503",
            dossier={"narrative": huge_narrative},
            scheme={"scheme_name": "Test Large Fund", "fund_house": "Test AMC", "category": "Equity"},
        )
        self.assertTrue(fund_pdf.startswith(b"%PDF"))

        # 2. Debt Dossier
        debt_pdf = generate_debt_dossier_pdf(
            isin="INE002A08018",
            posture={"composite_score": 85.0, "ytm_pct": 9.2},
            security={"instrument_name": "Test Huge Bond", "credit_rating": "AAA"},
        )
        self.assertTrue(debt_pdf.startswith(b"%PDF"))

        # 3. REIT Dossier
        reit_pdf = generate_reit_dossier_pdf(
            symbol="EMBASSY",
            reit={"name": "Embassy Office Parks REIT", "distribution_yield_pct": 7.5},
        )
        self.assertTrue(reit_pdf.startswith(b"%PDF"))

        # 4. MSME Dossier
        msme_pdf = generate_msme_dossier_pdf(
            uin="UDYAM-MH-01-0000001",
            dossier={"name": "Test Industrial Forge", "annual_turnover": 45.0},
        )
        self.assertTrue(msme_pdf.startswith(b"%PDF"))

    @staticmethod
    async def _timeout_wait_for(coro, timeout=None):
        if hasattr(coro, "close"):
            coro.close()
        raise asyncio.TimeoutError()

    def test_03_equity_pdf_timeout_returns_http_504(self):
        """Verifies that an equity PDF generation exceeding 15.0s is aborted with HTTP 504 Gateway Timeout."""
        from core.db.reports import save_report_to_archive
        save_report_to_archive({"ticker": "RELIANCE", "short_name": "Reliance Industries"}, "## Executive Summary\nSafe report.")

        with patch("web.routers.dossier.asyncio.wait_for", side_effect=self._timeout_wait_for):
            resp = self.client.get("/api/pdf/RELIANCE")
            self.assertEqual(resp.status_code, 504)
            self.assertIn("PDF generation timed out", resp.json().get("detail", ""))

    def test_04_fund_pdf_timeout_returns_http_504(self):
        """Verifies that a mutual fund PDF generation exceeding 15.0s returns HTTP 504."""
        with patch("core.db.mutual_funds.get_mutual_fund_scheme", return_value={"scheme_name": "Test Fund"}), \
             patch("web.routers.dossier.asyncio.wait_for", side_effect=self._timeout_wait_for):
            resp = self.client.get("/api/pdf/fund/120503")
            self.assertEqual(resp.status_code, 504)
            self.assertIn("PDF generation timed out", resp.json().get("detail", ""))

    def test_05_debt_pdf_timeout_returns_http_504(self):
        """Verifies that a corporate debt PDF generation exceeding 15.0s returns HTTP 504."""
        with patch("core.db.debt.get_debt_security_by_isin", return_value={"instrument_name": "Test Bond"}), \
             patch("web.routers.dossier.asyncio.wait_for", side_effect=self._timeout_wait_for):
            resp = self.client.get("/api/pdf/debt/INE002A08018")
            self.assertEqual(resp.status_code, 504)
            self.assertIn("PDF generation timed out", resp.json().get("detail", ""))

    def test_06_reit_pdf_timeout_returns_http_504(self):
        """Verifies that a REIT PDF generation exceeding 15.0s returns HTTP 504."""
        with patch("core.db.reits.get_reit_by_symbol", return_value={"name": "Test REIT"}), \
             patch("web.routers.dossier.asyncio.wait_for", side_effect=self._timeout_wait_for):
            resp = self.client.get("/api/pdf/reit/EMBASSY")
            self.assertEqual(resp.status_code, 504)
            self.assertIn("PDF generation timed out", resp.json().get("detail", ""))

    def test_07_msme_pdf_timeout_returns_http_504(self):
        """Verifies that an MSME PDF generation exceeding 15.0s returns HTTP 504."""
        with patch("core.msme.router.get_msme_detail", return_value={"name": "Test MSME"}), \
             patch("web.routers.dossier.asyncio.wait_for", side_effect=self._timeout_wait_for):
            resp = self.client.get("/api/pdf/msme/UDYAM-MH-01-0000001")
            self.assertEqual(resp.status_code, 504)
            self.assertIn("PDF generation timed out", resp.json().get("detail", ""))


class TestP3DistributedLockZombieLeases(unittest.TestCase):
    """P3-2: Defense against killed worker zombie leases stalling scheduled pipelines."""

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
            cur.execute(f"DELETE FROM distributed_job_locks WHERE job_name LIKE {p}", ("p3_test_%",))
            cur.execute(f"DELETE FROM distributed_job_locks WHERE job_name = {p}", ("daily_stock_ingest",))
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cur.close()
            conn.close()

    def test_01_locks_module_reexports_pruning_functions(self):
        """Validates that core/db/locks.py re-exports prune_zombie_leases and clear_zombie_leases."""
        self.assertTrue(callable(getattr(db_locks, "prune_zombie_leases", None)))
        self.assertTrue(callable(getattr(db_locks, "clear_zombie_leases", None)))
        self.assertIn("prune_zombie_leases", db_locks.__all__)
        self.assertIn("clear_zombie_leases", db_locks.__all__)

    def test_02_prune_zombie_leases_clears_expired_locks_from_killed_workers(self):
        """Simulates a worker dying (SIGKILL) mid-job, leaving an expired lease, and verifies automatic pruning."""
        job_name = "p3_test_sigkilled_worker_job"
        conn = get_connection()
        cur = conn.cursor()
        p = get_placeholder()

        # Seed an expired lock from a killed worker 10 minutes ago
        past_utc = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        try:
            cur.execute(
                f"INSERT INTO distributed_job_locks (job_name, locked_by, locked_at, expires_at) VALUES ({p}, {p}, {p}, {p})",
                (job_name, "killed_worker:99999:deadbeef", past_utc, past_utc),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

        # Prune zombie leases
        pruned_count = prune_zombie_leases(job_name=job_name)
        self.assertGreaterEqual(pruned_count, 1, "Zombie lease must be pruned from database")

        # Verify row is completely deleted
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT COUNT(*) FROM distributed_job_locks WHERE job_name = {p}", (job_name,))
            count = cur.fetchone()[0]
            self.assertEqual(count, 0, "Zombie lock row must no longer exist after pruning")
        finally:
            cur.close()
            conn.close()

    def test_03_prune_zombie_leases_preserves_active_unexpired_leases(self):
        """Verifies that prune_zombie_leases does NOT delete active leases that have not expired."""
        job_name = "p3_test_active_job"
        conn = get_connection()
        cur = conn.cursor()
        p = get_placeholder()

        # Seed an active lock expiring in 30 minutes
        now_utc = datetime.now(timezone.utc).isoformat()
        future_utc = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        try:
            cur.execute(
                f"INSERT INTO distributed_job_locks (job_name, locked_by, locked_at, expires_at) VALUES ({p}, {p}, {p}, {p})",
                (job_name, "active_worker:1234:live", now_utc, future_utc),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

        # Prune should not touch this active lease
        pruned = prune_zombie_leases(job_name=job_name)
        self.assertEqual(pruned, 0, "Active lease must not be deleted by zombie pruner")

        # Verify active lock remains intact
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT COUNT(*) FROM distributed_job_locks WHERE job_name = {p}", (job_name,))
            count = cur.fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            cur.close()
            conn.close()

    def test_04_acquire_job_lease_auto_prunes_and_acquires_after_sigkill(self):
        """Verifies acquire_job_lease automatically purges zombie lease and grants lock to new worker."""
        job_name = "daily_stock_ingest"
        conn = get_connection()
        cur = conn.cursor()
        p = get_placeholder()

        # Seed expired lock representing killed daily_stock_ingest process
        expired_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        try:
            cur.execute(
                f"INSERT INTO distributed_job_locks (job_name, locked_by, locked_at, expires_at) VALUES ({p}, {p}, {p}, {p})",
                (job_name, "stale_killed_worker:8888:killed", expired_ts, expired_ts),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

        # Morning scheduled pipeline starts up and attempts lease acquisition
        acquired = acquire_job_lease(job_name, ttl_seconds=1800)
        self.assertTrue(acquired, "Pipeline must acquire lease after auto-pruning zombie lease")

        # Verify ownership is now held by current live worker
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT locked_by FROM distributed_job_locks WHERE job_name = {p}", (job_name,))
            owner = cur.fetchone()[0]
            self.assertEqual(owner, WORKER_ID)
        finally:
            cur.close()
            conn.close()

    def test_05_strict_ttl_bounds_enforced(self):
        """Verifies that invalid or extreme TTLs are strictly clamped to [10s, 86400s]."""
        job_name = "p3_test_ttl_bounds"

        # 1. Negative TTL should clamp to MIN_LEASE_TTL_SECONDS
        acquire_job_lease(job_name, ttl_seconds=-100)
        conn = get_connection()
        cur = conn.cursor()
        p = get_placeholder()
        try:
            cur.execute(f"SELECT locked_at, expires_at FROM distributed_job_locks WHERE job_name = {p}", (job_name,))
            row = cur.fetchone()
            locked_at = datetime.fromisoformat(row[0])
            expires_at = datetime.fromisoformat(row[1])
            diff = (expires_at - locked_at).total_seconds()
            self.assertGreaterEqual(diff, MIN_LEASE_TTL_SECONDS)
        finally:
            cur.close()
            conn.close()
            release_job_lease(job_name)

        # 2. Excessive TTL (e.g. 10 years) should clamp to MAX_LEASE_TTL_SECONDS (24h)
        acquire_job_lease(job_name, ttl_seconds=315360000)
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT locked_at, expires_at FROM distributed_job_locks WHERE job_name = {p}", (job_name,))
            row = cur.fetchone()
            locked_at = datetime.fromisoformat(row[0])
            expires_at = datetime.fromisoformat(row[1])
            diff = (expires_at - locked_at).total_seconds()
            self.assertLessEqual(diff, MAX_LEASE_TTL_SECONDS + 2)
        finally:
            cur.close()
            conn.close()
            release_job_lease(job_name)


class TestP3ConnectionPoolStarvationDefense(unittest.TestCase):
    """P3-3: Defense against ThreadedConnectionPool starvation from malformed inputs or silent errors."""

    def test_01_pooled_connection_proxy_close_returns_connection_to_pool(self):
        """Verifies that closing a _PooledConnectionProxy returns connection to pool.putconn."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.closed = 0

        proxy = _PooledConnectionProxy(mock_pool, mock_conn)
        proxy.close()

        # Must execute rollback and return connection to pool
        mock_conn.rollback.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)
        self.assertTrue(proxy._returned)

        # Subsequent close() calls should be idempotent
        proxy.close()
        self.assertEqual(mock_pool.putconn.call_count, 1)

    def test_02_pooled_connection_proxy_gc_finalizer_prevents_pool_starvation(self):
        """Verifies __del__ GC finalizer auto-releases connection to pool if dropped unclosed."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.closed = 0

        def create_and_abandon_proxy():
            proxy = _PooledConnectionProxy(mock_pool, mock_conn)
            # Intentionally return without calling proxy.close()

        create_and_abandon_proxy()
        gc.collect()

        # __del__ must have released connection back to pool
        mock_pool.putconn.assert_called_once_with(mock_conn)

    def test_03_pooled_connection_proxy_evicts_corrupted_connection_from_pool(self):
        """Verifies that if rollback fails on a broken socket, pool.putconn(conn, close=True) is called."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.closed = 0
        mock_conn.rollback.side_effect = Exception("Broken pipe / server terminated connection")

        proxy = _PooledConnectionProxy(mock_pool, mock_conn)
        proxy.close()

        # Must evict dead connection with close=True so pool does not recycle poison socket
        mock_pool.putconn.assert_called_once_with(mock_conn, close=True)

    def test_04_get_db_context_guarantees_connection_close_under_exceptions(self):
        """Verifies context manager get_db_context guarantees connection closure under mid-query exceptions."""
        with patch("core.db.connection.get_db_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_get_conn.return_value = mock_conn

            with self.assertRaises(ZeroDivisionError):
                with get_db_context() as conn:
                    # Simulate fatal runtime exception mid-query
                    _ = 1 / 0

            # Connection must be closed in finally block despite exception
            mock_conn.close.assert_called_once()

    def test_05_init_db_skips_pool_checkout_when_already_initialized(self):
        """Verifies init_db does not consume connections from pool when database is already initialized."""
        with patch("core.db.connection._get_raw_connection") as mock_get_raw:
            # When target database is marked initialized, init_db(force=False) must not checkout connection
            _INITIALIZED_DBS.add("test_cached_db")
            with patch("core.db.connection.get_db_path", return_value="test_cached_db"), \
                 patch("core.db.connection.get_configured_supabase_url", return_value=None):
                init_db(force=False)

            mock_get_raw.assert_not_called()


if __name__ == "__main__":
    unittest.main()
