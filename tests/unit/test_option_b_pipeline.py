"""
Option B pipeline contracts: close run + fund run on GitHub, Render backups, and two timed emails
(Market Close Wrap 19:30 IST, Fund NAV Update 07:30 IST). Covers the scenarios from the approved
implication brief (L1-L10).
"""
import os
import re
import sqlite3
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class TestLeaseReleaseAndCompletionMarkers(unittest.TestCase):
    """L4/L5: failures and cancellations free leases; completion markers separate done from running."""

    def test_lease_released_on_keyboard_interrupt_and_system_exit(self):
        from core.db.distributed_lock import acquire_job_lease, job_lease, release_job_lease

        for exc_type in (KeyboardInterrupt, SystemExit):
            with self.subTest(exc=exc_type.__name__):
                name = _uid("cancel_test")
                try:
                    with self.assertRaises(exc_type):
                        with job_lease(name, ttl_seconds=600, release_on_exit=False) as acquired:
                            self.assertTrue(acquired)
                            raise exc_type()
                    # Released: a different worker id would now acquire it. Simulate by checking the row is gone.
                    from core.db.connection import get_connection

                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM distributed_job_locks WHERE job_name = ?", (name,))
                    self.assertEqual(cur.fetchone()[0], 0)
                    cur.close()
                    conn.close()
                finally:
                    release_job_lease(name)

    def test_lease_kept_after_success_for_daily_jobs(self):
        from core.db.distributed_lock import job_lease, release_job_lease
        from core.db.connection import get_connection

        name = _uid("success_test")
        try:
            with job_lease(name, ttl_seconds=600, release_on_exit=False) as acquired:
                self.assertTrue(acquired)
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM distributed_job_locks WHERE job_name = ?", (name,))
            self.assertEqual(cur.fetchone()[0], 1)
            cur.close()
            conn.close()
        finally:
            release_job_lease(name)

    def test_completion_markers_and_expiry(self):
        from core.db.distributed_lock import (
            is_job_done,
            mark_job_done,
            missing_done_markers,
            release_job_lease,
        )

        a, b = _uid("phase_a"), _uid("phase_b")
        try:
            self.assertEqual(missing_done_markers([a, b]), [a, b])
            self.assertTrue(mark_job_done(a))
            self.assertTrue(is_job_done(a))
            self.assertEqual(missing_done_markers([a, b]), [b])
            # An expired marker counts as not done.
            self.assertTrue(mark_job_done(b, ttl_seconds=10))
            from core.db.connection import get_connection

            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE distributed_job_locks SET expires_at = ? WHERE job_name = ?",
                ("2000-01-01T00:00:00+05:30", f"done::{b}"),
            )
            conn.commit()
            cur.close()
            conn.close()
            self.assertEqual(missing_done_markers([a, b]), [b])
        finally:
            release_job_lease(f"done::{a}")
            release_job_lease(f"done::{b}")

    def test_run_leased_phase_marks_done_only_on_success(self):
        from scripts.run_scheduled_pipeline import _run_leased_phase
        from core.db.distributed_lock import is_job_done, release_job_lease

        ok_name, bad_name = _uid("ok_phase"), _uid("bad_phase")
        results = {}
        try:
            _run_leased_phase(results, "ok", ok_name, "OK phase", lambda: "DONE")

            def _boom():
                raise RuntimeError("upstream down")

            _run_leased_phase(results, "bad", bad_name, "Bad phase", _boom)
            self.assertEqual(results["ok"], "DONE")
            self.assertTrue(results["bad"].startswith("FAILED: RuntimeError"))
            self.assertTrue(is_job_done(ok_name))
            self.assertFalse(is_job_done(bad_name))
        finally:
            for n in (ok_name, bad_name, f"done::{ok_name}", f"done::{bad_name}"):
                release_job_lease(n)


class TestTimedEmailSenders(unittest.TestCase):
    """L1/L3/L7: senders wait for their phases, send once per kind, never on weekends."""

    def _run(self, kind, date_str, missing_seq, cap=5):
        from scripts.run_scheduled_pipeline import run_send_edition

        with patch("scripts.run_scheduled_pipeline.missing_done_markers", side_effect=missing_seq) as mock_missing, \
             patch("scripts.run_scheduled_pipeline.time.sleep") as mock_sleep, \
             patch("scripts.run_scheduled_pipeline._dispatch_bouquet_phase") as mock_dispatch:
            res = run_send_edition(kind, date_str, wait_cap_seconds=cap)
        return res, mock_missing, mock_sleep, mock_dispatch

    def test_close_wrap_sends_immediately_when_close_run_finished(self):
        res, mock_missing, mock_sleep, mock_dispatch = self._run("MARKET_CLOSE", "2026-11-12", [[]])
        mock_sleep.assert_not_called()
        mock_dispatch.assert_called_once()
        self.assertEqual(mock_dispatch.call_args.kwargs["edition_kind"], "MARKET_CLOSE")
        required = mock_missing.call_args.args[0]
        self.assertIn("discovery_reel_2026-11-12", required)
        self.assertNotIn("mf_stock_ingest_2026-11-12", required)  # slow AI phase never delays the email
        self.assertEqual(res["phases_missing_at_send"], [])

    def test_close_wrap_waits_while_github_mid_run(self):
        pending = ["msme_daily_ingest_2026-11-12"]
        res, _, mock_sleep, mock_dispatch = self._run("MARKET_CLOSE", "2026-11-12", [pending, pending, []], cap=3600)
        self.assertGreaterEqual(mock_sleep.call_count, 2)
        mock_dispatch.assert_called_once()
        self.assertEqual(res["phases_missing_at_send"], [])

    def test_sender_attempts_send_at_cap_and_records_missing_phases(self):
        pending = ["fund_audit_2026-11-11"]
        res, _, _, mock_dispatch = self._run("FUND_NAV", "2026-11-11", [pending] * 50, cap=0)
        mock_dispatch.assert_called_once()
        self.assertEqual(mock_dispatch.call_args.kwargs["edition_kind"], "FUND_NAV")
        self.assertEqual(res["phases_missing_at_send"], pending)

    def test_weekend_dates_are_never_sent(self):
        for kind in ("MARKET_CLOSE", "FUND_NAV"):
            with self.subTest(kind=kind):
                res, mock_missing, _, mock_dispatch = self._run(kind, "2026-11-14", [[]])
                mock_dispatch.assert_not_called()
                mock_missing.assert_not_called()
                self.assertEqual(res["digest_dispatch"], "SKIPPED_MARKET_CLOSED")

    def test_fund_update_waits_for_post_nav_phases(self):
        from scripts.run_scheduled_pipeline import fund_run_required_leases

        self.assertEqual(
            fund_run_required_leases("2026-11-11"),
            ["amfi_nav_sync_2026-11-11", "etf_nav_sync_2026-11-11", "fund_audit_2026-11-11"],
        )


class TestDispatchLedgerPerKind(unittest.TestCase):
    """L6/L10: one send per (date, kind); v053 migration is idempotent and backfills legacy rows."""

    def test_migration_v053_is_idempotent_and_backfills_legacy_rows(self):
        from core.db.digest import ensure_digest_edition_kind_column

        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE digest_dispatches (id TEXT PRIMARY KEY, edition_date TEXT, subject TEXT, status TEXT)"
        )
        cur.execute("INSERT INTO digest_dispatches VALUES ('d1', '2026-11-01', 'Old wrap', 'COMPLETED')")
        ensure_digest_edition_kind_column(cur, is_pg=False)
        ensure_digest_edition_kind_column(cur, is_pg=False)  # second run is a no-op
        cur.execute("SELECT edition_kind FROM digest_dispatches WHERE id = 'd1'")
        self.assertEqual(cur.fetchone()[0], "MARKET_CLOSE")
        conn.close()

    def test_has_edition_been_dispatched_is_per_kind(self):
        from core.db.digest import has_edition_been_dispatched, record_digest_dispatch
        from core.db.connection import get_connection

        date_str = f"2099-{uuid.uuid4().int % 12 + 1:02d}-{uuid.uuid4().int % 28 + 1:02d}"
        did = record_digest_dispatch(
            edition_date=date_str, subject="t", recipients_count=1, delivered_count=1,
            failed_count=0, status="COMPLETED", edition_kind="MARKET_CLOSE",
        )
        try:
            self.assertTrue(has_edition_been_dispatched(date_str, edition_kind="MARKET_CLOSE"))
            self.assertFalse(has_edition_been_dispatched(date_str, edition_kind="FUND_NAV"))
            with self.assertRaises(ValueError):
                record_digest_dispatch(
                    edition_date=date_str, subject="t", recipients_count=0, delivered_count=0,
                    failed_count=0, edition_kind="WEEKLY",
                )
        finally:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM digest_dispatches WHERE id = ?", (did,))
            conn.commit()
            cur.close()
            conn.close()


class TestEditionSplit(unittest.TestCase):
    """The 19:30 and 07:30 emails carry only their own sections, fail closed on empty ones."""

    SECTION_DATA = {
        "_load_live_equities": [{"ticker": "TCS", "company_name": "Tata Consultancy Services", "sector": "IT",
                                 "cmp": 3100.0, "roce": 55.0, "sales_growth_3y": 9.0, "debt_to_equity": 0.0,
                                 "thesis": "Test note", "dossier_url": "/dossier/TCS"}],
        "_load_live_sovereign_posture": {"ten_year_gsec": 6.4, "one_year_tbill": 5.6, "repo_rate": 5.5,
                                         "yield_wedge_bps": 90, "signal_summary": "Curve steady."},
        "_load_live_corporate_debt": {"instrument_name": "Test NCD", "isin": "INE000000001", "summary": "Debt note."},
        "_load_live_etf_highlight": {"scheme_name": "Test ETF", "symbol": "TETF", "category": "Equity", "summary": "ETF note."},
        "_load_live_reits_and_sgb": {"summary": "REIT note.", "reit_symbol": "TREIT"},
        "_load_live_mf_highlight": {"scheme_name": "Test Fund", "scheme_code": "100001", "highlight": "MF note.",
                                    "active_share": "60%", "expense_ratio": "0.6%"},
        "_load_live_msme_highlight": {"company_name": "Test MSME", "cluster": "Pune", "roce_pct": "Small", "moat_note": "MSME note.", "uin": "UDYAM-1"},
        "_load_live_savings_posture": {"scheme_name": "PPF", "instrument_id": "SAV-PPF", "base_rate_pct": 7.1, "summary": "Savings note."},
    }

    def _compile(self, kind, overrides=None, require=True):
        from core.analysis import research_bouquet as rb

        data = dict(self.SECTION_DATA)
        data.update(overrides or {})
        mocks = {name: MagicMock(return_value=value) for name, value in data.items()}
        with patch.multiple(rb, **mocks):
            out = rb.compile_research_bouquet("2026-11-12", require_live_data=require, edition_kind=kind)
        return out, mocks

    def test_market_close_has_six_sections_numbered_without_gaps(self):
        from core.analysis.research_bouquet import render_bouquet_html, render_bouquet_text

        bouquet, mocks = self._compile("MARKET_CLOSE")
        mocks["_load_live_mf_highlight"].assert_not_called()
        mocks["_load_live_etf_highlight"].assert_not_called()
        self.assertIn("Market Close Wrap", bouquet["subject"])
        html = render_bouquet_html(bouquet)
        text = render_bouquet_text(bouquet)
        self.assertNotIn("Mutual Fund Look-Through", html)
        self.assertNotIn("ETF Liquidity", html)
        for n in range(1, 7):
            self.assertIn(f'<div class="section-title">{n}. ', html)
        self.assertNotIn('<div class="section-title">7. ', html)
        self.assertIn("6. FIXED SAVINGS", text)
        self.assertIn("Good evening", html)

    def test_fund_nav_has_two_sections_and_morning_copy(self):
        from core.analysis.research_bouquet import render_bouquet_html, render_bouquet_text

        bouquet, mocks = self._compile("FUND_NAV")
        mocks["_load_live_equities"].assert_not_called()
        self.assertIn("Fund NAV Update", bouquet["subject"])
        html = render_bouquet_html(bouquet)
        text = render_bouquet_text(bouquet)
        self.assertIn('<div class="section-title">1. National ETF', html)
        self.assertIn('<div class="section-title">2. Mutual Fund Look-Through', html)
        self.assertNotIn("Listed Equities", html)
        self.assertIn("Good morning", html)
        self.assertIn("1. NATIONAL ETF", text)
        self.assertIn("2. MUTUAL FUND", text)

    def test_each_edition_fails_closed_on_its_own_empty_sections(self):
        from core.analysis.research_bouquet import BouquetDataUnavailableError

        with self.assertRaises(BouquetDataUnavailableError):
            self._compile("FUND_NAV", {"_load_live_mf_highlight": {}})
        with self.assertRaises(BouquetDataUnavailableError):
            self._compile("MARKET_CLOSE", {"_load_live_msme_highlight": {}})
        # An empty fund section never blocks the evening email (and vice versa).
        self._compile("MARKET_CLOSE", {"_load_live_mf_highlight": {}, "_load_live_etf_highlight": {}})
        self._compile("FUND_NAV", {"_load_live_equities": []})

    def test_no_kind_keeps_full_eight_section_compilation_for_mobile_brief(self):
        bouquet, mocks = self._compile(None, require=False)
        for m in mocks.values():
            m.assert_called_once()
        self.assertIn("Day-End Market Wrap", bouquet["subject"])

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            self._compile("WEEKLY")


class TestPhaseSixParallelismAndBudget(unittest.TestCase):
    """L8/L9: parallel generation matches serial; nothing new starts after the AI budget."""

    def _batch(self, n, workers, deadline):
        from core.analysis import dossier_report_synthesis as drs

        calls = []

        def fake_stream(client, prompt, sys_inst, **kwargs):
            calls.append(prompt)
            time.sleep(0.15)
            yield "A" * 600

        client = MagicMock()
        client.vertexai = True
        items = [{"ticker": f"T{i}", "stock_data": {"short_name": f"T{i}"}} for i in range(n)]
        with patch("core.config.get_secret", return_value="AQ.test-key-0123456789"), \
             patch.object(drs.genai, "Client", return_value=client), \
             patch.object(drs, "get_latest_flash_models", return_value=["gemini-test"]), \
             patch.object(drs, "pass_pre_screening_gates", return_value=(True, "")), \
             patch.object(drs, "get_system_prompt", return_value="sys"), \
             patch.object(drs, "stream_genai_with_fallback", side_effect=fake_stream), \
             patch.dict(os.environ, {"FORCE_UNARY_VERTEX_IN_TEST": "0"}):
            start = time.monotonic()
            out = drs.synthesize_batch_stock_reports(items, workers=workers, deadline_monotonic=deadline)
            elapsed = time.monotonic() - start
        return out, calls, elapsed

    def test_parallel_matches_serial_and_is_faster(self):
        serial, _, t_serial = self._batch(8, workers=1, deadline=None)
        parallel, _, t_parallel = self._batch(8, workers=4, deadline=None)
        self.assertEqual(set(serial), {f"T{i}" for i in range(8)})
        self.assertEqual(set(parallel), set(serial))
        self.assertLess(t_parallel, t_serial * 0.6)

    def test_no_ai_call_starts_after_deadline(self):
        out, calls, _ = self._batch(5, workers=4, deadline=time.monotonic() - 1)
        self.assertEqual(out, {})
        self.assertEqual(calls, [])

    def test_cohort_after_deadline_uses_no_ai_and_reports_budget_exhausted(self):
        from core.analysis import daily_stock_ingestion as dsi

        queue = [{"ticker": f"BUD{i}", "scheme_count": 1} for i in range(3)]
        archived = []

        def fake_archive(item, skip_gemini=False, pre_synthesized_report=None, resolved_stock_data=None):
            archived.append((item["ticker"], skip_gemini))
            return {"ticker": item["ticker"], "status": "PENDING_SYNTHESIS"}

        with patch.object(dsi, "get_uncovered_mutual_fund_holdings_queue", return_value=queue), \
             patch.object(dsi, "_resolve_candidate_stock_data", side_effect=lambda c: {"ticker": c["ticker"]}), \
             patch.object(dsi, "synthesize_and_archive_stock_dossier", side_effect=fake_archive), \
             patch.object(dsi, "recalculate_affected_mutual_funds", return_value=[]), \
             patch.object(dsi, "record_autonomous_event"), \
             patch.object(dsi, "get_ingestion_progress_stats", return_value={}):
            res = dsi.ingest_daily_stock_cohort(
                edition_date="2026-11-12", count=3, workers=4, deadline_monotonic=time.monotonic() - 1
            )
        self.assertTrue(res["budget_exhausted"])
        self.assertEqual(res["pending_count"], 3)
        self.assertEqual(sorted(archived), [("BUD0", True), ("BUD1", True), ("BUD2", True)])

    def test_parallel_data_fetch_preserves_every_candidate(self):
        from core.analysis import daily_stock_ingestion as dsi

        queue = [{"ticker": f"PAR{i}", "scheme_count": 1} for i in range(6)]
        seen = {}

        def fake_archive(item, skip_gemini=False, pre_synthesized_report=None, resolved_stock_data=None):
            seen[item["ticker"]] = resolved_stock_data
            return {"ticker": item["ticker"], "status": "PENDING_SYNTHESIS"}

        with patch.object(dsi, "get_uncovered_mutual_fund_holdings_queue", return_value=queue), \
             patch.object(dsi, "_resolve_candidate_stock_data", side_effect=lambda c: {"ticker": c["ticker"], "px": len(c["ticker"])}), \
             patch.object(dsi, "synthesize_and_archive_stock_dossier", side_effect=fake_archive), \
             patch.object(dsi, "recalculate_affected_mutual_funds", return_value=[]), \
             patch.object(dsi, "record_autonomous_event"), \
             patch.object(dsi, "get_ingestion_progress_stats", return_value={}):
            dsi.ingest_daily_stock_cohort(edition_date="2026-11-12", count=6, workers=4)
        self.assertEqual(set(seen), {f"PAR{i}" for i in range(6)})
        for ticker, data in seen.items():
            self.assertEqual(data["ticker"], ticker)


class TestScheduleContracts(unittest.TestCase):
    """GitHub runs the heavy work; Render runs backups and both senders at fixed IST times."""

    def test_github_workflow_has_close_and_fund_runs_only(self):
        wf = (ROOT / ".github/workflows/scheduled_pipeline.yml").read_text()
        crons = re.findall(r'^\s*- cron: "([^"]+)"', wf, re.M)
        self.assertEqual(crons, ["0 11 * * *", "45 17 * * *"])  # 16:30 and 23:15 IST
        self.assertRegex(wf, r"(?m)^\s*timeout-minutes: 90\s*$")
        self.assertNotRegex(wf, r"(?m)^\s*- morning\s*$")

    def _render_services(self):
        text = (ROOT / "render.yaml").read_text()
        blocks = re.split(r"(?m)^  - type: ", text)[1:]
        services = {}
        for block in blocks:
            svc_type = block.split("\n", 1)[0].strip()
            name = re.search(r"(?m)^    name: (\S+)", block).group(1)
            services[name] = {"type": svc_type, "text": block}
        return services

    def test_render_cron_jobs_cover_backups_and_both_emails(self):
        crons = {n: s["text"] for n, s in self._render_services().items() if s["type"] == "cron"}
        expected = {
            "close-run-backup": ("0 13 * * *", "--mode close-backup", "0"),
            "market-close-wrap-sender": ("0 14 * * 1-5", "--mode send-close-wrap", "1"),
            "fund-run-backup": ("30 19 * * *", "--mode fund-backup", "0"),
            "fund-nav-update-sender": ("0 2 * * 2-6", "--mode send-fund-update", "1"),
        }
        self.assertEqual(set(crons), set(expected))
        for name, (schedule, mode, live_email) in expected.items():
            with self.subTest(name=name):
                block = crons[name]
                self.assertIn(f'schedule: "{schedule}"', block)
                self.assertIn(mode, block)
                self.assertRegex(
                    block, r'key: ENABLE_LIVE_EMAIL_DISPATCH\n\s+value: "%s"' % live_email
                )
                self.assertRegex(block, r'key: ENABLE_BACKGROUND_SCHEDULERS\n\s+value: "0"')
                self.assertIn("key: SUPABASE_DB_URL", block)
                # Same Docker image as the live website, built from main in the website's region.
                self.assertIn("runtime: docker", block)
                self.assertIn("dockerfilePath: ./Dockerfile", block)
                self.assertIn("branch: main", block)
                self.assertIn("region: singapore", block)
                self.assertIn(f'dockerCommand: "python3 scripts/run_scheduled_pipeline.py {mode}"', block)

    def test_render_blueprint_never_defines_a_second_website(self):
        services = self._render_services()
        self.assertEqual({s["type"] for s in services.values()}, {"cron"})


if __name__ == "__main__":
    unittest.main()
