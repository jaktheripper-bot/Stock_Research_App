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

    def test_resolve_mode_and_date_prevents_morning_lease_poisoning_and_midnight_rollover(self):
        """08:00 AM catch-up binds to T-1; 00:00-04:59 nightly binds to T-1; 19:30 evening binds to T."""
        from datetime import datetime
        from scripts.run_scheduled_pipeline import IST, _resolve_mode_and_date

        # 08:00 AM IST Monday -> morning mode on T-1 (2026-11-01), never pre-locking 2026-11-02 evening leases
        mon_8am = datetime(2026, 11, 2, 8, 0, tzinfo=IST)
        self.assertEqual(_resolve_mode_and_date("auto", mon_8am), ("morning", "2026-11-01"))
        self.assertEqual(_resolve_mode_and_date("morning", mon_8am), ("morning", "2026-11-01"))

        # 19:30 IST Monday -> evening harvest on T (2026-11-02)
        mon_1930 = datetime(2026, 11, 2, 19, 30, tzinfo=IST)
        self.assertEqual(_resolve_mode_and_date("auto", mon_1930), ("evening", "2026-11-02"))
        self.assertEqual(_resolve_mode_and_date("evening", mon_1930), ("evening", "2026-11-02"))

        # 00:15 AM IST Tuesday (delayed GHA cron) -> nightly on T-1 (2026-11-02)
        tue_0015 = datetime(2026, 11, 3, 0, 15, tzinfo=IST)
        self.assertEqual(_resolve_mode_and_date("auto", tue_0015), ("nightly", "2026-11-02"))
        self.assertEqual(_resolve_mode_and_date("nightly", tue_0015), ("nightly", "2026-11-02"))
        self.assertEqual(_resolve_mode_and_date("all", tue_0015), ("all", "2026-11-02"))

        # 04:04 AM & 05:32 AM IST Tuesday (heavily delayed GHA evening/nightly crons) -> T-1 (2026-11-02)
        tue_0404 = datetime(2026, 11, 3, 4, 4, tzinfo=IST)
        tue_0532 = datetime(2026, 11, 3, 5, 32, tzinfo=IST)
        self.assertEqual(_resolve_mode_and_date("evening", tue_0404), ("evening", "2026-11-02"))
        self.assertEqual(_resolve_mode_and_date("nightly", tue_0532), ("nightly", "2026-11-02"))

    @patch("scripts.run_scheduled_pipeline.prune_zombie_leases")
    @patch("scripts.run_scheduled_pipeline.record_autonomous_event", autospec=True)
    @patch("core.db.sovereign.refresh_daily_sovereign_benchmarks", return_value={"benchmarks_updated": 16})
    @patch("core.ingestion.etf_ingest.ingest_all_amfi_etfs", return_value={"persisted_to_db": 442})
    @patch("core.analysis.asset_scanner.run_comprehensive_asset_scan", return_value={"status": "OK"})
    @patch("scripts.run_discovery_worker.run_discovery_pipeline", return_value=True)
    @patch("core.msme.daily_ingest.ingest_daily_msme_cohort", return_value=15)
    @patch("core.analysis.daily_stock_ingestion.ingest_daily_stock_cohort", return_value={"status": "OK", "ingested_count": 15})
    @patch("core.db.digest.has_edition_been_dispatched", return_value=False)
    @patch("core.notify.dispatch_research_bouquet", return_value={"status": "COMPLETED", "delivered": 4})
    def test_evening_harvest_runs_all_7_phases_on_weekday_and_warehouse_only_on_weekend(
        self,
        mock_bouquet,
        mock_has_dispatched,
        mock_stock_ingest,
        mock_msme,
        mock_disc,
        mock_scan,
        mock_etf,
        mock_sov,
        mock_record_event,
        mock_prune,
    ):
        from scripts.run_scheduled_pipeline import _failed_phases, run_evening_harvest_pipeline

        with patch("scripts.run_scheduled_pipeline.job_lease", self.fake_job_lease):
            # 1. Friday (2026-10-30): all 7 phases execute including Day-End Wrap
            fri_res = run_evening_harvest_pipeline("2026-10-30", force=False, respect_market_calendar=True)
            self.assertEqual(_failed_phases(fri_res), [])
            self.assertEqual(fri_res["discovery_reel"], "SUCCESS")
            self.assertEqual(fri_res["msme_ingest"], "INGESTED_15")
            self.assertEqual(fri_res["morning_bouquet"], "COMPLETED")
            mock_bouquet.assert_called_once_with(edition_date="2026-10-30", force=False)

            mock_bouquet.reset_mock()
            mock_disc.reset_mock()
            mock_sov.reset_mock()
            mock_etf.reset_mock()
            mock_scan.reset_mock()

            # 2. Sunday (2026-11-01): Weekend Warehouse Mode skips market & email phases, runs MSME + Stock Ingest
            sun_res = run_evening_harvest_pipeline("2026-11-01", force=False, respect_market_calendar=True)
            self.assertEqual(_failed_phases(sun_res), [])
            self.assertEqual(sun_res["sovereign_sync"], "SKIPPED_MARKET_CLOSED")
            self.assertEqual(sun_res["etf_sync"], "SKIPPED_MARKET_CLOSED")
            self.assertEqual(sun_res["asset_scan"], "SKIPPED_MARKET_CLOSED")
            self.assertEqual(sun_res["discovery_reel"], "SKIPPED_MARKET_CLOSED")
            self.assertEqual(sun_res["morning_bouquet"], "SKIPPED_MARKET_CLOSED")
            self.assertEqual(sun_res["msme_ingest"], "INGESTED_15")
            self.assertEqual(sun_res["stock_ingestion"]["status"], "OK")
            mock_bouquet.assert_not_called()
            mock_disc.assert_not_called()
            mock_sov.assert_not_called()
            mock_etf.assert_not_called()
            mock_scan.assert_not_called()

    @patch("scripts.run_scheduled_pipeline.prune_zombie_leases")
    @patch("scripts.run_scheduled_pipeline.record_autonomous_event", autospec=True)
    @patch("core.ingestion.amfi.ingest_amfi_daily_feed")
    @patch("core.ingestion.etf_ingest.ingest_all_amfi_etfs")
    @patch("core.db.sovereign.refresh_daily_sovereign_benchmarks")
    @patch("core.analysis.asset_scanner.run_comprehensive_asset_scan")
    @patch("core.analysis.fund_overlap_auditor.audit_single_fund_daily")
    def test_nightly_weekend_warehouse_skips_amfi_and_runs_fund_audit(
        self,
        mock_fund_audit,
        mock_scan,
        mock_sov,
        mock_etf,
        mock_amfi,
        mock_record_event,
        mock_prune,
    ):
        from scripts.run_scheduled_pipeline import _failed_phases, run_nightly_pipeline

        mock_fund_audit.return_value = {
            "scheme_code": "122639",
            "scheme_name": "Parag Parikh Flexi Cap Fund",
            "composite_health_score": 85.0,
            "weighted_moat_score": 88.0,
            "accounting_risk_index": 12.0,
            "margin_of_safety_pct": 24.5,
        }
        with patch("scripts.run_scheduled_pipeline.job_lease", self.fake_job_lease):
            sun_res = run_nightly_pipeline("2026-11-01", force=False, respect_market_calendar=True)
        self.assertEqual(_failed_phases(sun_res), [])
        self.assertEqual(sun_res["amfi_sync"], "SKIPPED_MARKET_CLOSED")
        self.assertEqual(sun_res["etf_sync"], "SKIPPED_MARKET_CLOSED")
        self.assertEqual(sun_res["sovereign_sync"], "SKIPPED_MARKET_CLOSED")
        self.assertEqual(sun_res["asset_scan"], "SKIPPED_MARKET_CLOSED")
        self.assertEqual(sun_res["fund_audit"]["scheme_code"], "122639")
        mock_amfi.assert_not_called()
        mock_fund_audit.assert_called_once()

    def test_local_email_guard_skips_bouquet_lease_when_live_dispatch_disabled(self):
        """Local non-cloud hosts must return SKIPPED_LOCAL_GUARD without locking morning_bouquet_{date}."""
        from scripts.run_scheduled_pipeline import _dispatch_bouquet_phase

        results = {}
        leased_names = []

        @contextlib.contextmanager
        def tracking_lease(name, **kwargs):
            leased_names.append(name)
            yield True

        with patch("scripts.run_scheduled_pipeline.job_lease", tracking_lease), \
             patch("core.notify._is_live_email_dispatch_allowed", return_value=False), \
             patch("core.notify._is_test_runtime", return_value=False):
            _dispatch_bouquet_phase(results, "2026-11-02", force=False, respect_market_calendar=True)

        self.assertEqual(results["morning_bouquet"], "SKIPPED_LOCAL_GUARD")
        self.assertEqual(leased_names, [])

    @patch("scripts.run_scheduled_pipeline.prune_zombie_leases")
    @patch("scripts.run_scheduled_pipeline.record_autonomous_event", autospec=True)
    @patch("scripts.run_discovery_worker.run_discovery_pipeline", return_value=True)
    @patch("core.msme.daily_ingest.ingest_daily_msme_cohort", return_value=15)
    @patch("core.db.digest.has_edition_been_dispatched", return_value=True)
    @patch("scripts.synthesize_pending_equities.synthesize_pending_cohort", return_value=2)
    def test_morning_and_evening_trigger_synthesize_pending_cohort_when_deferred(
        self,
        mock_synth_cohort,
        mock_has_dispatched,
        mock_msme,
        mock_disc,
        mock_record_event,
        mock_prune,
    ):
        """Deferred Rule-4 candidates in morning or evening stock ingestion must invoke synthesize_pending_cohort."""
        from scripts.run_scheduled_pipeline import run_evening_harvest_pipeline

        deferred_payload = {
            "status": "pending_synthesis",
            "ingested_count": 0,
            "ingested_tickers": [],
            "pending_count": 2,
            "pending_tickers": ["UNARCHIVED_ONE", "UNARCHIVED_TWO"],
        }
        with patch("scripts.run_scheduled_pipeline.job_lease", self.fake_job_lease), \
             patch("core.analysis.daily_stock_ingestion.ingest_daily_stock_cohort", side_effect=[dict(deferred_payload), dict(deferred_payload)]):
            m_res = run_morning_pipeline("2026-11-02", force=False)
            e_res = run_evening_harvest_pipeline("2026-11-01", force=False, respect_market_calendar=True)

        self.assertEqual(mock_synth_cohort.call_count, 2)
        mock_synth_cohort.assert_called_with(limit=15, tickers=["UNARCHIVED_ONE", "UNARCHIVED_TWO"])
        self.assertEqual(m_res["stock_ingestion"]["compiled_from_pending"], 2)
        self.assertEqual(m_res["stock_ingestion"]["ingested_count"], 2)
        self.assertEqual(m_res["stock_ingestion"]["status"], "success")
        self.assertEqual(e_res["stock_ingestion"]["compiled_from_pending"], 2)
        self.assertEqual(e_res["stock_ingestion"]["status"], "success")

    @patch("scripts.run_scheduled_pipeline.prune_zombie_leases")
    @patch("scripts.run_scheduled_pipeline.record_autonomous_event", autospec=True)
    @patch("scripts.run_discovery_worker.run_discovery_pipeline", return_value=True)
    @patch("core.msme.daily_ingest.ingest_daily_msme_cohort", return_value=15)
    @patch("core.db.digest.has_edition_been_dispatched", return_value=True)
    def test_evening_phase6_fails_visibly_only_on_total_ai_outage(
        self,
        mock_has_dispatched,
        mock_msme,
        mock_disc,
        mock_record_event,
        mock_prune,
    ):
        """L6: 0 compiled with pending > 0 -> FAILED; partial compile or no candidates -> not failed."""
        from scripts.run_scheduled_pipeline import _failed_phases, run_evening_harvest_pipeline

        outage_payload = {
            "status": "pending_synthesis",
            "ingested_count": 0,
            "ingested_tickers": [],
            "pending_count": 15,
            "pending_tickers": [f"PEND{i}" for i in range(15)],
        }
        no_candidates_payload = {
            "status": "no_candidates",
            "ingested_count": 0,
            "ingested_tickers": [],
            "pending_count": 0,
            "pending_tickers": [],
        }
        cases = [
            # (stock payload, synthesize_pending_cohort behaviour, expect failed)
            (outage_payload, {"return_value": 0}, True),
            (outage_payload, {"side_effect": RuntimeError("403 PERMISSION_DENIED")}, True),
            (outage_payload, {"return_value": 3}, False),
            (no_candidates_payload, {"return_value": 0}, False),
        ]
        for payload, synth_kwargs, expect_failed in cases:
            with self.subTest(payload=payload["status"], synth=synth_kwargs, expect_failed=expect_failed), \
                 patch("scripts.run_scheduled_pipeline.job_lease", self.fake_job_lease), \
                 patch("core.analysis.daily_stock_ingestion.ingest_daily_stock_cohort", return_value=dict(payload)), \
                 patch("scripts.synthesize_pending_equities.synthesize_pending_cohort", **synth_kwargs):
                res = run_evening_harvest_pipeline("2026-11-01", force=False, respect_market_calendar=True)
                failed = _failed_phases(res)
                if expect_failed:
                    self.assertEqual(failed, ["stock_ingestion"])
                    self.assertIn("SynthesisUnavailableError", res["stock_ingestion"])
                    self.assertIn("0 of 15 pending equities compiled", res["stock_ingestion"])
                else:
                    self.assertEqual(failed, [])

    def test_raise_if_synthesis_unavailable_guard_matrix(self):
        from scripts.run_scheduled_pipeline import SynthesisUnavailableError, _raise_if_synthesis_unavailable

        with self.assertRaises(SynthesisUnavailableError):
            _raise_if_synthesis_unavailable({"pending_count": 2}, 0, 0, "Evening Phase 6")
        # Directly ingested or compiled from pending -> healthy
        _raise_if_synthesis_unavailable({"pending_count": 2}, 1, 0, "Evening Phase 6")
        _raise_if_synthesis_unavailable({"pending_count": 2}, 0, 1, "Evening Phase 6")
        # Nothing needed AI (weekend / no candidates / degraded payloads) -> never raises
        for degraded in ({}, {"pending_count": 0}, {"pending_count": None}, None, "N/A"):
            _raise_if_synthesis_unavailable(degraded, 0, 0, "Evening Phase 6")

    @patch("scripts.run_scheduled_pipeline.prune_zombie_leases")
    @patch("scripts.run_scheduled_pipeline.record_autonomous_event", autospec=True)
    @patch("core.ingestion.etf_ingest.ingest_all_amfi_etfs", return_value={"persisted_to_db": 5})
    @patch("core.db.sovereign.refresh_daily_sovereign_benchmarks", return_value={"benchmarks_updated": 16})
    @patch("core.analysis.asset_scanner.run_comprehensive_asset_scan", return_value={"status": "OK"})
    @patch(
        "core.analysis.fund_overlap_auditor.audit_single_fund_daily",
        return_value={
            "scheme_code": "122639",
            "scheme_name": "Parag Parikh Flexi Cap Fund",
            "composite_health_score": 85.0,
            "weighted_moat_score": 88.0,
            "accounting_risk_index": 12.0,
            "margin_of_safety_pct": 24.5,
        },
    )
    def test_nightly_amfi_sync_logs_real_pre_snapshot_differential_scan(
        self,
        mock_fund_audit,
        mock_comp_scan,
        mock_sov,
        mock_etf,
        mock_record_event,
        mock_prune,
    ):
        """_amfi_sync must snapshot prior NAVs before ingest_amfi_daily_feed and log real diffs to asset_scan_runs."""
        import os
        from core.analysis.asset_scanner import get_asset_scan_runs

        sample_feed = (
            "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)\n"
            "PPFAS Mutual Fund\n"
            "122639;INF879O01027;-;Parag Parikh Flexi Cap Fund - Direct Plan - Growth;84.5000;02-Nov-2026\n"
            "999888;INF000TEST01;-;New Direct Growth Test Scheme - Direct Plan - Growth;12.3400;02-Nov-2026\n"
        )
        # Simulate DB state BEFORE ingest_amfi_daily_feed runs (old NAV=82.10), then mutated by ingest_amfi_daily_feed
        state = {"schemes": [{"scheme_code": "122639", "scheme_name": "PPFAS Flexi Cap", "nav": 82.10}]}

        def _fake_get_active(limit=20000):
            return list(state["schemes"])

        def _fake_ingest_amfi(limit=None, direct_growth_only=True):
            # Overwrite in-memory DB state just like real ingest_amfi_daily_feed does
            state["schemes"] = [
                {"scheme_code": "122639", "scheme_name": "PPFAS Flexi Cap", "nav": 84.50},
                {"scheme_code": "999888", "scheme_name": "New Direct Growth Test Scheme", "nav": 12.34},
            ]
            return {"status": "success", "upserted": 2, "errors": 0}

        with patch.dict(os.environ, {"TESTING": "1", "ALLOW_AMFI_DIFF_SCAN_IN_TEST": "1"}, clear=False), \
             patch("scripts.run_scheduled_pipeline.job_lease", self.fake_job_lease), \
             patch("core.db.mutual_funds.get_active_mutual_funds", side_effect=_fake_get_active), \
             patch("core.ingestion.amfi.ingest_amfi_daily_feed", side_effect=_fake_ingest_amfi), \
             patch("core.analysis.asset_scanner.fetch_amfi_nav_raw", return_value=sample_feed):
            res = run_nightly_pipeline("2026-11-02", force=False)

        self.assertEqual(res["amfi_sync"]["upserted"], 2)
        runs = [r for r in get_asset_scan_runs(limit=10) if r["triggered_by"] == "scheduled_nightly"]
        self.assertGreaterEqual(len(runs), 1)
        latest = runs[0]
        self.assertEqual(latest["scan_type"], "MUTUAL_FUNDS")
        self.assertEqual(latest["status"], "completed")
        self.assertEqual(latest["items_scanned"], 2)
        self.assertEqual(latest["items_added"], 1)    # 999888 detected as NEW despite ingest running first
        self.assertEqual(latest["items_updated"], 1)  # 122639 detected as CHANGED (82.10 -> 84.50)

    def test_force_flag_does_not_redispatch_email_without_explicit_env_opt_in(self):
        """--force alone must bypass data leases without re-emailing an already-dispatched edition."""
        import os
        from scripts.run_scheduled_pipeline import _dispatch_bouquet_phase

        # 1. Weekday --force without FORCE_EMAIL_REDISPATCH=1 -> ALREADY_DISPATCHED, 0 emails sent
        results_suppressed = {}
        with patch.dict(os.environ, {"FORCE_EMAIL_REDISPATCH": "0"}, clear=False), \
             patch("scripts.run_scheduled_pipeline.job_lease", self.fake_job_lease), \
             patch("core.db.digest.has_edition_been_dispatched", return_value=True) as mock_has_disp, \
             patch("core.notify.dispatch_research_bouquet") as mock_bouquet:
            _dispatch_bouquet_phase(results_suppressed, "2026-11-03", force=True, respect_market_calendar=True)
            mock_has_disp.assert_called_once_with("2026-11-03")
            mock_bouquet.assert_not_called()
            self.assertEqual(results_suppressed["morning_bouquet"], "ALREADY_DISPATCHED")

        # 2. Weekday --force WITH FORCE_EMAIL_REDISPATCH=1 -> explicitly re-sends with force=True
        results_forced = {}
        with patch.dict(os.environ, {"FORCE_EMAIL_REDISPATCH": "1"}, clear=False), \
             patch("scripts.run_scheduled_pipeline.job_lease", self.fake_job_lease), \
             patch("core.db.digest.has_edition_been_dispatched", return_value=True) as mock_has_disp2, \
             patch("core.notify.dispatch_research_bouquet", return_value={"status": "COMPLETED", "delivered": 2}) as mock_bouquet2:
            _dispatch_bouquet_phase(results_forced, "2026-11-03", force=True, respect_market_calendar=True)
            mock_has_disp2.assert_not_called()
            mock_bouquet2.assert_called_once_with(edition_date="2026-11-03", force=True)
            self.assertEqual(results_forced["morning_bouquet"], "COMPLETED")

    @patch("scripts.run_scheduled_pipeline.prune_zombie_leases")
    @patch("scripts.run_scheduled_pipeline.record_autonomous_event", autospec=True)
    @patch("core.db.sovereign.refresh_daily_sovereign_benchmarks", return_value={"benchmarks_updated": 16})
    @patch("core.ingestion.etf_ingest.ingest_all_amfi_etfs", return_value={"persisted_to_db": 442})
    @patch("core.analysis.asset_scanner.run_comprehensive_asset_scan", return_value={"status": "OK"})
    @patch("scripts.run_discovery_worker.run_discovery_pipeline", return_value=True)
    @patch("core.msme.daily_ingest.ingest_daily_msme_cohort", return_value=15)
    @patch("core.analysis.daily_stock_ingestion.ingest_daily_stock_cohort", return_value={"status": "OK", "ingested_count": 15})
    @patch("core.db.digest.has_edition_been_dispatched", return_value=False)
    @patch("core.notify.dispatch_research_bouquet")
    def test_weekend_force_harvest_skips_email_without_force_email_redispatch_env(
        self,
        mock_bouquet,
        mock_has_dispatched,
        mock_stock_ingest,
        mock_msme,
        mock_disc,
        mock_scan,
        mock_etf,
        mock_sov,
        mock_record_event,
        mock_prune,
    ):
        """Sunday --force harvest refreshes data phases while keeping weekend newsletter suppressed."""
        import os
        from scripts.run_scheduled_pipeline import run_evening_harvest_pipeline

        with patch.dict(os.environ, {"FORCE_EMAIL_REDISPATCH": "0"}, clear=False), \
             patch("scripts.run_scheduled_pipeline.job_lease", self.fake_job_lease):
            sun_res = run_evening_harvest_pipeline("2026-11-01", force=True, respect_market_calendar=True)

        mock_sov.assert_called_once_with("2026-11-01")
        mock_etf.assert_called_once_with(force_refresh=True)
        mock_disc.assert_called_once()
        mock_bouquet.assert_not_called()
        self.assertEqual(sun_res["morning_bouquet"], "SKIPPED_MARKET_CLOSED")

    def test_sync_amfi_diff_mode_honors_force_refresh_flag(self):
        """scripts/sync_amfi.py --diff-mode --force-refresh must refresh NAVAll.txt before scan_mutual_funds."""
        import scripts.sync_amfi as sync_amfi_cli

        call_order = []

        def _fake_fetch(force_refresh=False):
            call_order.append(("fetch", force_refresh))
            return "RAW"

        def _fake_scan(limit=None):
            call_order.append(("scan", limit))
            return {"scanned": 10, "new": 1, "changed": 2}

        with patch.object(sys, "argv", ["sync_amfi.py", "--diff-mode", "--force-refresh", "--limit", "10"]), \
             patch.object(sync_amfi_cli, "init_db"), \
             patch.object(sync_amfi_cli, "record_scan_start", return_value="scan_test_1"), \
             patch.object(sync_amfi_cli, "record_scan_complete") as mock_complete, \
             patch.object(sync_amfi_cli, "fetch_amfi_nav_raw", side_effect=_fake_fetch), \
             patch.object(sync_amfi_cli, "scan_mutual_funds", side_effect=_fake_scan):
            with self.assertRaises(SystemExit) as ctx:
                sync_amfi_cli.main()
            self.assertEqual(ctx.exception.code, 0)

        self.assertEqual(call_order, [("fetch", True), ("scan", 10)])
        mock_complete.assert_called_once()

    def test_amfi_and_etf_ssl_context_anchors_on_certifi_bundle(self):
        """AMFI & ETF TLS contexts must anchor on certifi.where() even when SSL_CERT_FILE is set."""
        import os
        import ssl
        import certifi
        from core.ingestion import amfi as amfi_mod
        from core.ingestion import etf_ingest as etf_mod

        seen_cafiles = []
        real_create_ctx = ssl.create_default_context

        def _spy_create_ctx(*args, **kwargs):
            seen_cafiles.append(kwargs.get("cafile"))
            return real_create_ctx(*args, **kwargs)

        with patch.dict(os.environ, {"SSL_CERT_FILE": "/etc/ssl/cert.pem"}, clear=False), \
             patch("ssl.create_default_context", side_effect=_spy_create_ctx):
            ctx_amfi = amfi_mod._get_ssl_context()
            ctx_etf = etf_mod._get_ssl_context()

        self.assertIsInstance(ctx_amfi, ssl.SSLContext)
        self.assertIsInstance(ctx_etf, ssl.SSLContext)
        self.assertEqual(seen_cafiles, [certifi.where(), certifi.where()])


if __name__ == "__main__":
    unittest.main()

