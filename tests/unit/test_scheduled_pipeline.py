"""
Unit tests for scripts/run_scheduled_pipeline.py.
Verifies invocation contracts, signatures, and lease coordination across morning and nightly workflows.
"""
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
    def test_run_morning_pipeline_signatures(
        self,
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

        res = run_morning_pipeline("2026-10-25", force=False)

        self.assertEqual(res.get("discovery_reel"), "SUCCESS")
        self.assertEqual(res.get("msme_ingest"), "INGESTED_15")
        mock_discovery.assert_called_once_with(
            target_count=15,
            edition_date="2026-10-25",
            dry_run=False,
            force_synthesis=False,
        )
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


if __name__ == "__main__":
    unittest.main()

