"""
Small savings rate checks: a broken official page is recorded (not silently skipped), and the
21:00 owner reminder prompts a quarterly confirmation around each scheme's next_review_date.
"""
import json
import os
import unittest
import urllib.error
from datetime import date
from unittest.mock import patch

os.environ.setdefault("TESTING", "1")


def _inst(iid, review, rate=7.1, eff="2026-10-01"):
    return {
        "instrument_id": iid,
        "scheme_name": iid,
        "base_rate_pct": rate,
        "effective_from": eff,
        "next_review_date": review,
    }


class TestProbeHealthRecord(unittest.TestCase):
    def _record(self, previous, date_str, outcomes):
        from core.db import savings

        saved = {}
        with patch.object(savings, "get_savings_probe_health", return_value=previous), \
             patch("core.db.settings.set_system_setting", side_effect=lambda k, v: saved.update({k: v}) or True):
            rec = savings.record_savings_probe_health(date_str, outcomes)
        return rec, json.loads(saved[savings.PROBE_HEALTH_SETTING_KEY])

    def test_failing_since_carries_over_and_clears_on_success(self):
        from core.db.savings import PROBE_SOURCE_UNAVAILABLE, PROBE_VERIFIED

        prev = {"probes": {"SAV-PPF": {"failing_since": "2026-11-01", "last_verified_on": "2026-10-30"}}}
        rec, stored = self._record(prev, "2026-11-12", {
            "SAV-PPF": (PROBE_SOURCE_UNAVAILABLE, "HTTP Error 404", "https://a"),
            "SAV-NSC": (PROBE_VERIFIED, "", "https://b"),
        })
        self.assertEqual(stored, rec)
        self.assertEqual(rec["probes"]["SAV-PPF"]["failing_since"], "2026-11-01")
        self.assertEqual(rec["probes"]["SAV-PPF"]["last_verified_on"], "2026-10-30")
        self.assertIsNone(rec["probes"]["SAV-NSC"]["failing_since"])
        self.assertEqual(rec["probes"]["SAV-NSC"]["last_verified_on"], "2026-11-12")

    def test_storage_failure_is_logged_not_raised(self):
        from core.db import savings

        with patch.object(savings, "get_savings_probe_health", return_value={}), \
             patch("core.db.settings.set_system_setting", side_effect=RuntimeError("db down")), \
             self.assertLogs("equity_research.core.db.savings", level="WARNING"):
            savings.record_savings_probe_health("2026-11-12", {})

    def test_unreadable_stored_record_reads_as_empty(self):
        from core.db import savings

        with patch("core.db.settings.get_system_setting", return_value="not json"), \
             self.assertLogs("equity_research.core.db.savings", level="WARNING"):
            self.assertEqual(savings.get_savings_probe_health(), {})


class TestBrokenSourceIsRecorded(unittest.TestCase):
    def test_404_source_marks_every_probe_unavailable_and_fetches_once(self):
        from core.db import savings

        calls = []

        def fake_urlopen(req, timeout=None, context=None):
            calls.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

        captured = {}
        with patch.object(savings, "seed_baseline_savings_universe", return_value={"status": "SUCCESS"}), \
             patch.object(savings, "activate_due_future_savings_rates", return_value={}), \
             patch.object(savings, "SAVINGS_INBOX_DIR", savings.PROJECT_ROOT / "does-not-exist"), \
             patch.object(savings, "get_active_savings_instruments", return_value=[]), \
             patch.object(savings.urllib.request, "urlopen", side_effect=fake_urlopen), \
             patch.object(savings, "record_savings_probe_health",
                          side_effect=lambda d, o: captured.update(o) or {}):
            result = savings.verify_and_sync_automated_savings_rates("2026-11-12", allow_network=True)

        probe_ids = sorted(p["instrument_id"] for p in savings._PUBLIC_RATE_PROBES)
        self.assertEqual(result["probe_failures"], probe_ids)
        self.assertEqual(result["live_probes_verified"], 0)
        self.assertTrue(all(v[0] == savings.PROBE_SOURCE_UNAVAILABLE for v in captured.values()))
        self.assertTrue(all("404" in v[1] for v in captured.values()))
        # All probes share one page: a failed fetch is not retried per scheme.
        self.assertEqual(len(calls), len({p["url"] for p in savings._PUBLIC_RATE_PROBES}))


class TestQuarterlyReview(unittest.TestCase):
    def _collect(self, target, instruments, health=None):
        from scripts.send_subscription_reminder import collect_savings_rate_review

        with patch("core.db.savings.get_active_savings_instruments", return_value=instruments), \
             patch("core.db.savings.get_savings_probe_health", return_value=health or {}):
            return collect_savings_rate_review(target)

    def test_states_around_the_review_date(self):
        insts = [_inst("SAV-PPF", "2026-12-31")]
        for target, expected in (
            (date(2026, 11, 12), []),
            (date(2026, 12, 25), ["DUE"]),
            (date(2026, 12, 31), ["DUE"]),
            (date(2027, 1, 3), ["OVERDUE"]),
        ):
            with self.subTest(target=target):
                r = self._collect(target, insts)
                self.assertEqual([x["state"] for x in r["action_needed"]], expected)
                self.assertEqual(r["overdue"], expected == ["OVERDUE"])

    def test_failing_probes_are_listed_and_verified_ones_are_not(self):
        health = {"checked_on": "2026-11-12", "probes": {
            "SAV-PPF": {"status": "SOURCE_UNAVAILABLE", "reason": "404", "failing_since": "2026-11-01"},
            "SAV-NSC": {"status": "VERIFIED"},
        }}
        r = self._collect(date(2026, 11, 12), [_inst("SAV-PPF", "2026-12-31")], health)
        self.assertEqual([f["instrument_id"] for f in r["failing_probes"]], ["SAV-PPF"])

    def test_database_error_never_invents_rates(self):
        from scripts.send_subscription_reminder import collect_savings_rate_review

        with patch("core.db.savings.get_active_savings_instruments", side_effect=RuntimeError("db down")):
            r = collect_savings_rate_review(date(2026, 12, 28))
        self.assertFalse(r["available"])
        self.assertNotIn("schemes", r)

    def test_report_subject_and_both_renderings(self):
        from scripts import send_subscription_reminder as rem

        review = self._collect(date(2027, 1, 3), [_inst("SAV-PPF", "2026-12-31")])
        with patch.object(rem, "collect_savings_rate_review", return_value=review), \
             patch.object(rem, "load_subscription_registry", return_value={"subscriptions": []}):
            rep = rem.build_reminder_report(date(2027, 1, 3), include_live_metrics=False)
        self.assertTrue(rep["subject"].startswith("[Savings Rates Overdue]"))
        text = rem.render_reminder_text(rep)
        self.assertIn("6. SMALL SAVINGS RATES (QUARTERLY CHECK)", text)
        self.assertIn("[OVERDUE] SAV-PPF (SAV-PPF): 7.1%", text)
        self.assertIn("import_savings_rates.py", text)
        html_out = rem.render_reminder_html(rep)
        self.assertIn("Small Savings Rates (Quarterly Check)", html_out)
        self.assertNotIn("{{", html_out)

    def test_quiet_when_nothing_due_and_all_checks_pass(self):
        from scripts import send_subscription_reminder as rem

        review = self._collect(date(2026, 11, 12), [_inst("SAV-PPF", "2026-12-31")])
        with patch.object(rem, "collect_savings_rate_review", return_value=review), \
             patch.object(rem, "load_subscription_registry", return_value={"subscriptions": []}):
            rep = rem.build_reminder_report(date(2026, 11, 12), include_live_metrics=False)
        self.assertNotIn("SMALL SAVINGS", rem.render_reminder_text(rep))
        self.assertNotIn("Savings", rep["subject"])


if __name__ == "__main__":
    unittest.main()
