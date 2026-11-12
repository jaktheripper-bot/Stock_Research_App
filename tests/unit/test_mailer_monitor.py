"""Mailer monitoring: heartbeat on a send, admin alert on anything else except an expected skip."""
import os
import unittest
from unittest.mock import patch

from core import mailer_monitor as mm


class TestMailerMonitor(unittest.TestCase):

    def _report(self, results, env=None):
        env = {"ADMIN_ALERT_EMAIL": "alerts@example.com", "RESEND_API_KEY": "re_test", **(env or {})}
        with patch.dict(os.environ, env, clear=False), \
             patch("core.config.get_secret", return_value=None), \
             patch.object(mm, "ping_mailer_heartbeat", return_value=True) as ping, \
             patch("core.notify._is_live_email_dispatch_allowed", return_value=True), \
             patch("core.notify._dispatch_via_resend", return_value=True) as resend:
            outcome = mm.report_mailer_outcome("MARKET_CLOSE", "2026-11-12", results)
        return outcome, ping, resend

    def test_completed_send_pings_heartbeat_without_alert(self):
        outcome, ping, resend = self._report({"digest_dispatch": "COMPLETED"})
        self.assertEqual(outcome, "SENT")
        ping.assert_called_once_with("MARKET_CLOSE")
        resend.assert_not_called()

    def test_already_dispatched_counts_as_sent(self):
        outcome, ping, resend = self._report({"digest_dispatch": "ALREADY_DISPATCHED"})
        self.assertEqual(outcome, "SENT")
        ping.assert_called_once()
        resend.assert_not_called()

    def test_partial_send_pings_and_alerts(self):
        outcome, ping, resend = self._report({"digest_dispatch": "PARTIAL"})
        self.assertEqual(outcome, "PARTIAL")
        ping.assert_called_once()
        self.assertIn("partly delivered", resend.call_args.args[2])

    def test_failures_alert_and_never_ping(self):
        cases = [
            {"digest_dispatch": "FAILED: BouquetDataUnavailableError: missing live sections: msme",
             "phases_missing_at_send": ["msme_daily_ingest_2026-11-12"]},
            {"digest_dispatch": "NO_SUBSCRIBERS"},
            {"digest_dispatch": "SKIPPED_LOCAL_GUARD"},
            {"digest_dispatch": "FAILED: MarketCalendarUnavailable: calendar down"},
            {},
        ]
        for results in cases:
            with self.subTest(results=results):
                outcome, ping, resend = self._report(results)
                self.assertEqual(outcome, "NOT_SENT")
                ping.assert_not_called()
                resend.assert_called_once()
                _, to_addr, subject, body = resend.call_args.args[:4]
                self.assertEqual(to_addr, "alerts@example.com")
                self.assertIn("Market Close Wrap NOT sent for 2026-11-12", subject)
                if results.get("phases_missing_at_send"):
                    self.assertIn("msme_daily_ingest_2026-11-12", body)

    def test_weekend_or_holiday_skip_pings_without_alerting(self):
        """Senders run daily; a market-closed skip is a healthy run, so it keeps the 24 h heartbeat alive."""
        outcome, ping, resend = self._report({"digest_dispatch": "SKIPPED_MARKET_CLOSED"})
        self.assertEqual(outcome, "SKIPPED")
        ping.assert_called_once()
        resend.assert_not_called()

    def test_missing_alert_address_logs_instead_of_guessing_a_recipient(self):
        with patch.dict(os.environ, {"ADMIN_ALERT_EMAIL": ""}, clear=False), \
             patch("core.config.get_secret", return_value=None), \
             patch("core.notify._dispatch_via_resend") as resend, \
             self.assertLogs("core.mailer_monitor", level="ERROR"):
            ok = mm.send_mailer_alert("FUND_NAV", "2026-11-11", "NOT_SENT", {"digest_dispatch": "FAILED: x"})
        self.assertFalse(ok)
        resend.assert_not_called()

    def test_each_mailer_uses_its_own_heartbeat_url(self):
        env = {"BETTER_STACK_HEARTBEAT_URL_MARKET_CLOSE": "https://hb.example/close",
               "BETTER_STACK_HEARTBEAT_URL_FUND_NAV": "https://hb.example/fund"}
        with patch.dict(os.environ, env, clear=False), \
             patch("core.config.get_secret", return_value=None), \
             patch.object(mm.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200
            self.assertTrue(mm.ping_mailer_heartbeat("FUND_NAV"))
        self.assertEqual(urlopen.call_args.args[0].full_url, "https://hb.example/fund")

    def test_unset_heartbeat_url_is_a_warning_not_a_ping(self):
        with patch.dict(os.environ, {"BETTER_STACK_HEARTBEAT_URL_MARKET_CLOSE": ""}, clear=False), \
             patch("core.config.get_secret", return_value=None), \
             patch.object(mm.urllib.request, "urlopen") as urlopen:
            self.assertFalse(mm.ping_mailer_heartbeat("MARKET_CLOSE"))
        urlopen.assert_not_called()

    def test_runner_reports_outcome_for_both_sender_modes(self):
        import sys
        import scripts.run_scheduled_pipeline as runner

        for mode, kind in (("send-close-wrap", "MARKET_CLOSE"), ("send-fund-update", "FUND_NAV")):
            with self.subTest(mode=mode), \
                 patch.object(sys, "argv", ["run_scheduled_pipeline.py", "--mode", mode, "--date", "2026-11-12"]), \
                 patch.object(runner, "setup_logging"), patch.object(runner, "init_db"), \
                 patch.object(runner, "flush_betterstack_logs"), patch.object(runner, "dispatch_heartbeat"), \
                 patch.object(runner, "run_send_edition", return_value={"digest_dispatch": "COMPLETED"}), \
                 patch.object(runner, "report_mailer_outcome") as report:
                self.assertEqual(runner.main(), 0)
                report.assert_called_once_with(kind, "2026-11-12", {"digest_dispatch": "COMPLETED"})


if __name__ == "__main__":
    unittest.main()
