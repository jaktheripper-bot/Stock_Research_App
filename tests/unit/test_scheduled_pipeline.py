"""
Unit tests for scripts/run_scheduled_pipeline.py.
Verifies invocation contracts, signatures, and lease coordination across morning and nightly workflows.
"""
import contextlib
import sys
import unittest
from unittest.mock import patch, MagicMock

from scripts.run_scheduled_pipeline import run_morning_pipeline, run_nightly_pipeline


class TestScheduledPipeline(unittest.TestCase):

    @patch("scripts.run_scheduled_pipeline.job_lease")
    @patch("scripts.run_scheduled_pipeline.prune_zombie_leases")
    @patch("scripts.run_scheduled_pipeline.record_autonomous_event", autospec=True)
    @patch("core.analysis.daily_stock_ingestion.ingest_daily_stock_cohort")
    @patch("scripts.run_discovery_worker.run_discovery_pipeline")
    @patch("core.msme.daily_ingest.ingest_daily_msme_cohort")
    @patch("core.db.digest.has_edition_been_dispatched", return_value=False)
    @patch("core.notify.dispatch_research_bouquet")
    def test_run_morning_pipeline_signatures(
        self,
        mock_bouquet,
        mock_has_dispatched,
        mock_msme,
        mock_discovery,
        mock_stock_ingest,
        mock_record_event,
        mock_prune,
        mock_lease,
    ):
        mock_lease.return_value.__enter__.return_value = True
        mock_stock_ingest.return_value = {"status": "SUCCESS", "ingested_stocks": ["TCS", "INFY"]}
        mock_discovery.return_value = True
        mock_msme.return_value = 15
        mock_bouquet.return_value = {"status": "COMPLETED", "delivered": 3}

        res = run_morning_pipeline("2026-10-25", force=False)

        self.assertEqual(res.get("discovery_reel"), "SUCCESS")
        self.assertEqual(res.get("msme_ingest"), "INGESTED_15")
        self.assertEqual(res.get("morning_bouquet"), "COMPLETED")
        mock_discovery.assert_called_once_with(
            target_count=15,
            edition_date="2026-10-25",
            dry_run=False,
            force_synthesis=False,
        )
        mock_bouquet.assert_called_once_with(edition_date="2026-10-25", force=False)
        mock_record_event.assert_called_once()
        call_kwargs = mock_record_event.call_args[1]
        self.assertEqual(call_kwargs.get("event_type"), "MORNING_PIPELINE_COMPLETE")
        self.assertIsInstance(call_kwargs.get("metadata"), dict)
        self.assertEqual(call_kwargs.get("metadata"), res)

    @patch("scripts.run_scheduled_pipeline.job_lease")
    @patch("scripts.run_scheduled_pipeline.prune_zombie_leases")
    @patch("scripts.run_scheduled_pipeline.record_autonomous_event", autospec=True)
    @patch("core.ingestion.amfi.ingest_amfi_daily_feed")
    @patch("core.ingestion.etf_ingest.ingest_all_amfi_etfs")
    @patch("core.db.sovereign.refresh_daily_sovereign_benchmarks")
    @patch("core.analysis.asset_scanner.run_comprehensive_asset_scan")
    @patch("core.analysis.fund_overlap_auditor.audit_single_fund_daily")
    def test_run_nightly_pipeline_signatures(
        self,
        mock_fund_audit,
        mock_scanner,
        mock_sov,
        mock_etf,
        mock_amfi,
        mock_record_event,
        mock_prune,
        mock_lease,
    ):
        mock_lease.return_value.__enter__.return_value = True
        mock_amfi.return_value = {"upserted": 10, "errors": 0}
        mock_etf.return_value = {"persisted_to_db": 5}
        mock_sov.return_value = {"benchmarks_updated": 16}
        mock_scanner.return_value = {"status": "OK"}
        mock_fund_audit.return_value = {
            "scheme_code": "122639",
            "scheme_name": "Parag Parikh Flexi Cap Fund",
            "composite_health_score": 85.0,
            "weighted_moat_score": 88.0,
            "accounting_risk_index": 12.0,
            "margin_of_safety_pct": 24.5,
        }

        res = run_nightly_pipeline("2026-10-25", force=False)

        mock_amfi.assert_called_once_with(limit=None, direct_growth_only=True)
        mock_fund_audit.assert_called_once_with(scheme_code=None, force_refresh_stocks=False)
        self.assertEqual(res.get("amfi_sync"), {"upserted": 10, "errors": 0})
        self.assertEqual(res.get("fund_audit"), mock_fund_audit.return_value)

        # 2 events recorded: DAILY_FUND_AUDIT and NIGHTLY_PIPELINE_COMPLETE
        self.assertEqual(mock_record_event.call_count, 2)
        fund_event_kwargs = mock_record_event.call_args_list[0][1]
        self.assertEqual(fund_event_kwargs.get("event_type"), "DAILY_FUND_AUDIT")
        self.assertEqual(fund_event_kwargs.get("ticker"), "122639")
        self.assertIsInstance(fund_event_kwargs.get("metadata"), dict)
        self.assertEqual(fund_event_kwargs.get("metadata")["composite_health_score"], 85.0)

        nightly_event_kwargs = mock_record_event.call_args_list[1][1]
        self.assertEqual(nightly_event_kwargs.get("event_type"), "NIGHTLY_PIPELINE_COMPLETE")
        self.assertIsInstance(nightly_event_kwargs.get("metadata"), dict)
        self.assertEqual(nightly_event_kwargs.get("metadata"), res)

    def test_run_discovery_worker_backward_compatibility_alias(self):
        from scripts.run_discovery_worker import run_discovery_worker, run_discovery_pipeline
        self.assertIs(run_discovery_worker, run_discovery_pipeline)

    def test_scheduler_boot_guard_requires_explicit_enable_flag(self):
        """Verifies that background schedulers do not boot without ENABLE_BACKGROUND_SCHEDULERS=1."""
        from web.main import lifespan, app
        import asyncio
        import os
        import sys

        async def _noop(*args, **kwargs):
            pass

        # When ENABLE_BACKGROUND_SCHEDULERS is not set
        with patch.dict(os.environ, {"TESTING": "0", "ENABLE_BACKGROUND_SCHEDULERS": "0"}, clear=False), \
             patch.dict(sys.modules):
            sys.modules.pop("pytest", None)
            with patch("web.main.AsyncIOScheduler") as mock_sched, \
                 patch("web.main.warmup_task", side_effect=_noop), \
                 patch("web.main.run_daily_discovery_scheduler", side_effect=_noop) as mock_disc, \
                 patch("web.main.run_daily_amfi_scheduler", side_effect=_noop) as mock_amfi:

                async def _run():
                    async with lifespan(app):
                        pass

                asyncio.run(_run())
                mock_sched.assert_not_called()
                mock_disc.assert_not_called()
                mock_amfi.assert_not_called()

        # When ENABLE_BACKGROUND_SCHEDULERS=1
        with patch.dict(os.environ, {"TESTING": "0", "ENABLE_BACKGROUND_SCHEDULERS": "1"}, clear=False), \
             patch.dict(sys.modules):
            sys.modules.pop("pytest", None)
            with patch("web.main.AsyncIOScheduler") as mock_sched, \
                 patch("web.main.warmup_task", side_effect=_noop), \
                 patch("web.main.run_daily_discovery_scheduler", side_effect=_noop), \
                 patch("web.main.run_daily_amfi_scheduler", side_effect=_noop), \
                 patch("web.main.run_daily_fund_audit_scheduler", side_effect=_noop), \
                 patch("web.main.run_daily_project_audit_scheduler", side_effect=_noop), \
                 patch("core.agents.watchers.bse_watcher.run_bse_watcher_loop", side_effect=_noop):

                mock_sched_instance = MagicMock()
                mock_sched.return_value = mock_sched_instance

                async def _run_enabled():
                    async with lifespan(app):
                        pass

                asyncio.run(_run_enabled())
                mock_sched.assert_called_once()
                mock_sched_instance.start.assert_called_once()

    def test_ide_and_test_email_guard_blocks_live_network_calls(self):
        """Verifies that local IDE / test runs never fire real HTTP requests to Resend or SMTP unless mocked or explicitly enabled."""
        import os
        import urllib.request
        from core.notify import _dispatch_via_resend, _is_live_email_dispatch_allowed

        # 1. Under test runtime, _is_live_email_dispatch_allowed() is always False
        self.assertFalse(_is_live_email_dispatch_allowed())

        # 2. Even if RESEND_API_KEY is present in os.environ, unmocked urllib.request.urlopen is NEVER called
        def _forbid_network(*args, **kwargs):
            raise AssertionError("Real network call to Resend API was attempted during test/IDE guard!")

        with patch.dict(os.environ, {"RESEND_API_KEY": "re_live_simulated_key_123", "TESTING": "1"}, clear=False), \
             patch.object(urllib.request, "urlopen", side_effect=_forbid_network):
            # Note: patch.object with side_effect creates a MagicMock, so let's test with a plain function replacement
            orig_urlopen = urllib.request.urlopen
            try:
                urllib.request.urlopen = _forbid_network
                ok = _dispatch_via_resend(
                    "desk@moatnomics.com",
                    "subscriber@example.com",
                    "Test Subject",
                    "Test Body",
                )
                self.assertTrue(ok)
            finally:
                urllib.request.urlopen = orig_urlopen


class TestScheduledPipelinePhaseIsolation(unittest.TestCase):
    """A failing phase must not abort later phases, must free its lease, and must fail the run."""

    def setUp(self):
        self.released = []
        released = self.released

        @contextlib.contextmanager
        def fake_job_lease(job_name, ttl_seconds=1800, release_on_exit=False, release_on_failure=True):
            # Mirrors core.db.distributed_lock.job_lease: release only on exit or on failure.
            failed = False
            try:
                yield True
            except Exception:
                failed = True
                raise
            finally:
                if release_on_exit or (failed and release_on_failure):
                    released.append(job_name)

        self.fake_job_lease = fake_job_lease

    @patch("scripts.run_scheduled_pipeline.prune_zombie_leases")
    @patch("scripts.run_scheduled_pipeline.record_autonomous_event", autospec=True)
    @patch("core.ingestion.amfi.ingest_amfi_daily_feed", side_effect=RuntimeError("AMFI feed timeout"))
    @patch("core.ingestion.etf_ingest.ingest_all_amfi_etfs", return_value={"persisted_to_db": 5})
    @patch("core.db.sovereign.refresh_daily_sovereign_benchmarks", return_value={"benchmarks_updated": 16})
    @patch("core.analysis.asset_scanner.run_comprehensive_asset_scan", return_value={"status": "OK"})
    @patch("core.analysis.fund_overlap_auditor.audit_single_fund_daily")
    def test_nightly_phase_failure_does_not_abort_later_phases(
        self, mock_fund_audit, mock_scan, mock_sov, mock_etf, mock_amfi, mock_record_event, mock_prune
    ):
        from core.analysis.fund_overlap_auditor import FundSynthesisPendingError
        mock_fund_audit.side_effect = FundSynthesisPendingError("Live AI synthesis unavailable for scheme X")

        with patch("scripts.run_scheduled_pipeline.job_lease", self.fake_job_lease):
            res = run_nightly_pipeline("2026-10-30", force=False)

        self.assertTrue(res["amfi_sync"].startswith("FAILED: RuntimeError"))
        self.assertTrue(res["fund_audit"].startswith("FAILED: FundSynthesisPendingError"))
        mock_etf.assert_called_once()
        mock_sov.assert_called_once()
        mock_scan.assert_called_once()
        mock_fund_audit.assert_called_once()
        # Failed phases free their lease for a same-day retry; successful phases keep theirs.
        self.assertIn("amfi_nav_sync_2026-10-30", self.released)
        self.assertIn("fund_audit_2026-10-30", self.released)
        self.assertNotIn("etf_matrix_sync_2026-10-30", self.released)
        # No DAILY_FUND_AUDIT event for a failed audit; only the pipeline summary event.
        self.assertEqual(mock_record_event.call_count, 1)
        summary_kwargs = mock_record_event.call_args.kwargs
        self.assertEqual(summary_kwargs["event_type"], "NIGHTLY_PIPELINE_COMPLETE")
        self.assertIn("AMFI: FAILED", summary_kwargs["summary"])
        self.assertIn("Fund Audit: FAILED", summary_kwargs["summary"])
        self.assertIn("ETFs: OK", summary_kwargs["summary"])

    @patch("scripts.run_scheduled_pipeline.prune_zombie_leases")
    @patch("scripts.run_scheduled_pipeline.record_autonomous_event", autospec=True)
    @patch("core.analysis.daily_stock_ingestion.ingest_daily_stock_cohort", return_value={"status": "OK", "ingested_count": 15})
    @patch("scripts.run_discovery_worker.run_discovery_pipeline", return_value=True)
    @patch("core.msme.daily_ingest.ingest_daily_msme_cohort", return_value=15)
    @patch("core.db.digest.has_edition_been_dispatched", side_effect=RuntimeError("ledger unavailable"))
    @patch("core.notify.dispatch_research_bouquet")
    def test_morning_bouquet_fails_closed_when_dispatch_ledger_unreadable(
        self, mock_bouquet, mock_has_dispatched, mock_msme, mock_discovery, mock_ingest, mock_record_event, mock_prune
    ):
        with patch("scripts.run_scheduled_pipeline.job_lease", self.fake_job_lease):
            res = run_morning_pipeline("2026-10-30", force=False)

        mock_bouquet.assert_not_called()
        self.assertTrue(res["morning_bouquet"].startswith("FAILED: RuntimeError"))
        self.assertEqual(res["discovery_reel"], "SUCCESS")
        self.assertEqual(res["msme_ingest"], "INGESTED_15")

    @patch("scripts.run_scheduled_pipeline.prune_zombie_leases")
    @patch("scripts.run_scheduled_pipeline.record_autonomous_event", autospec=True)
    @patch("core.analysis.daily_stock_ingestion.ingest_daily_stock_cohort", return_value={"status": "OK", "ingested_count": 15})
    @patch("scripts.run_discovery_worker.run_discovery_pipeline", return_value=False)
    @patch("core.msme.daily_ingest.ingest_daily_msme_cohort", return_value=15)
    @patch("core.db.digest.has_edition_been_dispatched", return_value=True)
    def test_unsuccessful_discovery_run_is_failed_and_releases_lease(
        self, mock_has_dispatched, mock_msme, mock_discovery, mock_ingest, mock_record_event, mock_prune
    ):
        with patch("scripts.run_scheduled_pipeline.job_lease", self.fake_job_lease):
            res = run_morning_pipeline("2026-10-30", force=False)

        self.assertTrue(res["discovery_reel"].startswith("FAILED: RuntimeError"))
        self.assertIn("discovery_reel_2026-10-30", self.released)
        self.assertEqual(res["msme_ingest"], "INGESTED_15")
        self.assertEqual(res["morning_bouquet"], "ALREADY_DISPATCHED")

    def test_main_exits_nonzero_and_withholds_heartbeat_when_a_phase_failed(self):
        import scripts.run_scheduled_pipeline as runner
        with patch.object(sys, "argv", ["run_scheduled_pipeline.py", "--mode", "nightly", "--date", "2026-10-30"]), \
             patch.object(runner, "setup_logging"), \
             patch.object(runner, "init_db"), \
             patch.object(runner, "flush_betterstack_logs"), \
             patch.object(runner, "dispatch_heartbeat") as mock_heartbeat, \
             patch.object(runner, "run_nightly_pipeline", return_value={"amfi_sync": "FAILED: RuntimeError: x", "etf_sync": {}}):
            self.assertEqual(runner.main(), 1)
        mock_heartbeat.assert_not_called()

    def test_main_exits_zero_and_sends_heartbeat_when_all_phases_ok(self):
        import scripts.run_scheduled_pipeline as runner
        with patch.object(sys, "argv", ["run_scheduled_pipeline.py", "--mode", "nightly", "--date", "2026-10-30"]), \
             patch.object(runner, "setup_logging"), \
             patch.object(runner, "init_db"), \
             patch.object(runner, "flush_betterstack_logs"), \
             patch.object(runner, "dispatch_heartbeat") as mock_heartbeat, \
             patch.object(runner, "run_nightly_pipeline", return_value={"amfi_sync": {}, "etf_sync": "SKIPPED_LEASE_HELD"}):
            self.assertEqual(runner.main(), 0)
        mock_heartbeat.assert_called_once_with("nightly")


if __name__ == "__main__":
    unittest.main()

