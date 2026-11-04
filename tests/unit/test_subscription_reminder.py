"""
Unit tests for scripts/send_subscription_reminder.py and data/vendor_subscriptions.json.
Verifies dynamic rolling due-date math, billing-window alerts, pattern-lock graduation,
HTML/text rendering parity, degraded offline safety, and distributed lease idempotency.
"""

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from scripts.send_subscription_reminder import (
    build_reminder_report,
    dispatch_subscription_reminder_email,
    evaluate_subscription_due_state,
    load_subscription_registry,
    render_reminder_html,
    render_reminder_text,
)


class TestSubscriptionReminder(unittest.TestCase):
    def test_canonical_registry_structure_and_services(self):
        reg = load_subscription_registry()
        self.assertGreaterEqual(len(reg["subscriptions"]), 6)
        self.assertGreaterEqual(len(reg["free_tier_accounts"]), 6)
        self.assertGreaterEqual(len(reg["optimizations"]), 6)

        render_sub = next(s for s in reg["subscriptions"] if s["id"] == "render")
        self.assertEqual(render_sub["pattern_status"], "CONFIRMED")
        self.assertEqual(render_sub["last_paid_date"], "2026-11-03")
        self.assertGreaterEqual(len(render_sub["billable_line_items"]), 2)
        self.assertGreaterEqual(len(render_sub["project_workloads"]), 2)

    def test_early_month_flags_unconfirmed_billing_windows(self):
        report = build_reminder_report(ref_date=date(2026, 11, 4), include_live_metrics=False)
        self.assertFalse(report["all_patterns_fixed"])
        self.assertEqual(report["confirmed_count"], 2)

        by_id = {s["id"]: s for s in report["evaluated_subs"]}
        self.assertEqual(by_id["render"]["computed_state"], "SCHEDULED")
        self.assertEqual(by_id["render"]["next_expected_iso"], "2026-12-03")
        self.assertEqual(by_id["aws_lightsail"]["computed_state"], "VERIFY_BILLING_WINDOW_NOW")
        self.assertEqual(by_id["gcp_vertex"]["computed_state"], "VERIFY_BILLING_WINDOW_NOW")

    def test_pre_renewal_due_soon_and_overdue_receipt_states(self):
        reg = load_subscription_registry()
        render_sub = next(s for s in reg["subscriptions"] if s["id"] == "render")

        due_soon = evaluate_subscription_due_state(render_sub, date(2026, 11, 29))
        self.assertEqual(due_soon["computed_state"], "DUE_SOON")
        self.assertEqual(due_soon["days_until"], 4)

        due_today = evaluate_subscription_due_state(render_sub, date(2026, 12, 3))
        self.assertEqual(due_today["computed_state"], "DUE_TODAY")
        self.assertEqual(due_today["days_until"], 0)

        overdue = evaluate_subscription_due_state(render_sub, date(2026, 12, 6))
        self.assertEqual(overdue["computed_state"], "RECEIPT_CHECK_OVERDUE")
        self.assertEqual(overdue["days_until"], -3)

    def test_graduation_banner_when_all_patterns_confirmed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = Path(tmpdir) / "subs.json"
            reg = load_subscription_registry()
            for s in reg["subscriptions"]:
                s["pattern_status"] = "CONFIRMED"
                if not s.get("anchor_day"):
                    s["anchor_day"] = 10
                if not s.get("last_paid_date"):
                    s["last_paid_date"] = "2026-11-10"
            custom_path.write_text(json.dumps(reg), encoding="utf-8")

            report = build_reminder_report(
                ref_date=date(2026, 11, 15),
                registry_path=custom_path,
                include_live_metrics=False,
            )
            self.assertTrue(report["all_patterns_fixed"])
            self.assertIn("[All Patterns Confirmed]", report["subject"])
            txt = render_reminder_text(report)
            htm = render_reminder_html(report)
            self.assertIn("All due-date patterns are now CONFIRMED", txt)
            self.assertIn("All subscription due-date patterns are CONFIRMED", htm)

    def test_idempotent_daily_lease_prevents_duplicate_email(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox_db = os.path.join(tmpdir, "lease_test.db")
            report = build_reminder_report(ref_date=date(2026, 11, 4), include_live_metrics=False)

            with patch.dict(
                os.environ,
                {
                    "DB_PATH": sandbox_db,
                    "TEST_DB_PATH": sandbox_db,
                    "FORCE_LOCAL_SQLITE": "1",
                    "SUPABASE_DB_URL": "",
                    "RESEND_API_KEY": "re_test_key",
                    "ADMIN_ALERT_EMAIL": "ops@moatnomics.com",
                },
                clear=False,
            ), patch(
                "scripts.send_subscription_reminder.get_secret",
                side_effect=lambda k, default=None: "re_test_key" if k == "RESEND_API_KEY" else default,
            ), patch(
                "scripts.send_subscription_reminder._is_live_email_dispatch_allowed",
                return_value=True,
            ), patch(
                "scripts.send_subscription_reminder._dispatch_via_resend",
                return_value=True,
            ) as mock_resend:
                first = dispatch_subscription_reminder_email(report, force=False)
                second = dispatch_subscription_reminder_email(report, force=False)

                self.assertEqual(first["status"], "SENT")
                self.assertTrue(first["delivered"])
                self.assertEqual(second["status"], "SKIPPED_ALREADY_SENT")
                self.assertFalse(second["delivered"])
                self.assertEqual(mock_resend.call_count, 1)

    def test_sandbox_logged_dispatch_releases_lease_for_subsequent_live_send(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox_db = os.path.join(tmpdir, "lease_sandbox_test.db")
            report = build_reminder_report(ref_date=date(2026, 11, 4), include_live_metrics=False)

            with patch.dict(
                os.environ,
                {
                    "DB_PATH": sandbox_db,
                    "TEST_DB_PATH": sandbox_db,
                    "FORCE_LOCAL_SQLITE": "1",
                    "SUPABASE_DB_URL": "",
                    "RESEND_API_KEY": "re_test_key",
                    "ADMIN_ALERT_EMAIL": "ops@moatnomics.com",
                },
                clear=False,
            ), patch(
                "scripts.send_subscription_reminder.get_secret",
                side_effect=lambda k, default=None: "re_test_key" if k == "RESEND_API_KEY" else default,
            ), patch(
                "scripts.send_subscription_reminder._dispatch_via_resend",
                return_value=True,
            ) as mock_resend:
                with patch(
                    "scripts.send_subscription_reminder._is_live_email_dispatch_allowed",
                    return_value=False,
                ):
                    sandbox_run = dispatch_subscription_reminder_email(report, force=False)
                self.assertEqual(sandbox_run["status"], "SANDBOX_LOGGED")

                with patch(
                    "scripts.send_subscription_reminder._is_live_email_dispatch_allowed",
                    return_value=True,
                ):
                    live_run = dispatch_subscription_reminder_email(report, force=False)
                self.assertEqual(live_run["status"], "SENT")
                self.assertEqual(mock_resend.call_count, 2)


if __name__ == "__main__":
    unittest.main()
