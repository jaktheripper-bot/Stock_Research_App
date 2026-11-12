"""
GET /api/health/mailers: 200 only when the latest due Market Close Wrap and Fund NAV Update went
out. Weekends and NSE holidays are expected skips; a missing send or unreadable ledger is a 503.
"""
import os
import unittest
from datetime import date, datetime
from unittest.mock import patch

os.environ.setdefault("TESTING", "1")

from core.mailer_health import IST, evaluate_mailer_health, latest_expected_edition  # noqa: E402

NO_HOLIDAYS = lambda d: False  # noqa: E731


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


class TestExpectedEdition(unittest.TestCase):
    def test_market_close_due_by_21_00_same_day(self):
        # Fri 2026-11-13
        self.assertEqual(latest_expected_edition(at(2026, 11, 13, 20, 59), "MARKET_CLOSE", NO_HOLIDAYS), date(2026, 11, 12))
        self.assertEqual(latest_expected_edition(at(2026, 11, 13, 21, 0), "MARKET_CLOSE", NO_HOLIDAYS), date(2026, 11, 13))

    def test_fund_nav_due_by_08_45_next_day(self):
        self.assertEqual(latest_expected_edition(at(2026, 11, 13, 8, 44), "FUND_NAV", NO_HOLIDAYS), None)  # 11-11 is before start
        self.assertEqual(latest_expected_edition(at(2026, 11, 13, 8, 45), "FUND_NAV", NO_HOLIDAYS), date(2026, 11, 12))

    def test_weekend_and_monday_morning_look_back_to_friday(self):
        for now in (at(2026, 11, 14, 22, 0), at(2026, 11, 15, 12, 0), at(2026, 11, 16, 8, 0)):
            with self.subTest(now=now):
                self.assertEqual(latest_expected_edition(now, "MARKET_CLOSE", NO_HOLIDAYS), date(2026, 11, 13))
                self.assertEqual(latest_expected_edition(now, "FUND_NAV", NO_HOLIDAYS), date(2026, 11, 13))

    def test_nse_holiday_is_skipped(self):
        # Tue 2026-11-24 is an NSE holiday: on 11-24 night the latest due wrap is Mon 11-23.
        hol = lambda d: d == date(2026, 11, 24)  # noqa: E731
        self.assertEqual(latest_expected_edition(at(2026, 11, 24, 22, 0), "MARKET_CLOSE", hol), date(2026, 11, 23))
        self.assertEqual(latest_expected_edition(at(2026, 11, 25, 9, 0), "FUND_NAV", hol), date(2026, 11, 23))

    def test_nothing_judged_before_go_live(self):
        self.assertIsNone(latest_expected_edition(at(2026, 11, 12, 20, 0), "MARKET_CLOSE", NO_HOLIDAYS))


class TestEvaluate(unittest.TestCase):
    def test_ok_when_both_sent(self):
        r = evaluate_mailer_health(at(2026, 11, 13, 22, 0), NO_HOLIDAYS, lambda d, k: True)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["editions"]["MARKET_CLOSE"]["expected_edition"], "2026-11-13")
        self.assertEqual(r["editions"]["FUND_NAV"]["expected_edition"], "2026-11-12")

    def test_late_when_one_missing(self):
        sent = {("2026-11-13", "MARKET_CLOSE")}
        r = evaluate_mailer_health(at(2026, 11, 13, 22, 0), NO_HOLIDAYS, lambda d, k: (d.isoformat(), k) in sent)
        self.assertEqual(r["status"], "late")
        self.assertFalse(r["editions"]["FUND_NAV"]["sent"])

    def test_no_subscriber_details_exposed(self):
        r = evaluate_mailer_health(at(2026, 11, 13, 22, 0), NO_HOLIDAYS, lambda d, k: True)
        self.assertEqual(set(r), {"status", "checked_at", "editions"})
        for info in r["editions"].values():
            self.assertEqual(set(info), {"expected_edition", "due_by", "sent"})

    def test_unavailable_calendar_counts_as_trading_day(self):
        from core.ingestion.market_calendar import MarketCalendarUnavailable
        from core.mailer_health import _default_is_holiday

        with patch("core.ingestion.market_calendar.is_nse_trading_holiday",
                   side_effect=MarketCalendarUnavailable("down")), \
             self.assertLogs("core.mailer_health", level="WARNING"):
            self.assertFalse(_default_is_holiday(date(2026, 11, 24)))


class TestEndpoint(unittest.TestCase):
    def _get(self, result=None, error=None):
        from fastapi.testclient import TestClient
        from web.main import app

        target = "core.mailer_health.cached_mailer_health"
        kw = {"side_effect": error} if error else {"return_value": result}
        with patch(target, **kw):
            return TestClient(app).get("/api/health/mailers")

    def test_ok_is_200(self):
        res = self._get({"status": "ok", "checked_at": "x", "editions": {}})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("cache-control"), "no-store")

    def test_late_is_503(self):
        self.assertEqual(self._get({"status": "late", "checked_at": "x", "editions": {}}).status_code, 503)

    def test_error_is_503_unavailable(self):
        res = self._get(error=RuntimeError("db down"))
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
