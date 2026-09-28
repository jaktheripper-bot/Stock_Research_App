import os
import sys
import unittest
from datetime import datetime, timedelta, date
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analyzer import evaluate_company_disparity, compare_two_companies
from db import record_usage_event, get_site_usage_summary, get_session_journeys, get_db_connection
from telemetry import (
    parse_user_agent,
    parse_traffic_source,
    verify_admin_passcode,
    get_admin_passcode
)

class TestComparisonAndTelemetry(unittest.TestCase):
    def test_evaluate_company_disparity_axes(self):
        # 1. Compatible peers (Both IT Services, similar scale, both profitable)
        infy = {"sector": "Technology", "market_cap": 6000000000000.0, "pe_ratio": 24.5}
        tcs = {"sector": "Technology", "market_cap": 14000000000000.0, "pe_ratio": 28.1}
        disp = evaluate_company_disparity(infy, tcs)
        self.assertFalse(disp["is_disparate"])
        self.assertFalse(disp["sector_mismatch"])
        self.assertFalse(disp["lifecycle_mismatch"])
        self.assertFalse(disp["scale_mismatch"])
        self.assertEqual(len(disp["warnings"]), 0)

        # 2. Sector mismatch (Technology vs Financial Services)
        hdfc = {"sector": "Financial Services", "market_cap": 12000000000000.0, "pe_ratio": 19.2}
        disp_sec = evaluate_company_disparity(infy, hdfc)
        self.assertTrue(disp_sec["is_disparate"])
        self.assertTrue(disp_sec["sector_mismatch"])

        # 3. Lifecycle mismatch (Profitable vs Loss-Making)
        zomato_loss = {"sector": "Consumer Cyclical", "market_cap": 1500000000000.0, "pe_ratio": "Loss-Making"}
        itc_profit = {"sector": "Consumer Defensive", "market_cap": 6000000000000.0, "pe_ratio": 26.5}
        disp_life = evaluate_company_disparity(zomato_loss, itc_profit)
        self.assertTrue(disp_life["is_disparate"])
        self.assertTrue(disp_life["lifecycle_mismatch"])

        # 4. Scale divergence (>= 100x market cap)
        micro = {"sector": "Technology", "market_cap": 500000000.0, "pe_ratio": 20.0}
        mega = {"sector": "Technology", "market_cap": 6000000000000.0, "pe_ratio": 25.0}
        disp_scale = evaluate_company_disparity(micro, mega)
        self.assertTrue(disp_scale["is_disparate"])
        self.assertTrue(disp_scale["scale_mismatch"])

    def test_telemetry_recording_and_date_range_summary(self):
        # Record test telemetry events with visitor attribution
        record_usage_event(
            event_type="UNIT_TEST_SEARCH",
            ticker="UNIT_TEST_TICKER",
            latency_ms=15.0,
            session_id="sess_test123",
            traffic_source="Google Search",
            referrer="https://www.google.com/",
            country="IN",
            device_type="Desktop",
            browser="Chrome",
            os="macOS"
        )
        record_usage_event(
            event_type="UNIT_TEST_CACHE",
            ticker="UNIT_TEST_TICKER",
            cost_saved_usd=0.036,
            session_id="sess_test123",
            traffic_source="Google Search",
            country="IN"
        )

        # 1. Summary by days
        summary_days = get_site_usage_summary(days=1)
        self.assertIsNotNone(summary_days)
        self.assertIn("total_queries", summary_days)
        self.assertIn("traffic_sources", summary_days)
        self.assertIn("geographic_distribution", summary_days)

        # 2. Summary by custom date range
        today = date.today()
        start = today - timedelta(days=2)
        summary_range = get_site_usage_summary(start_date=start, end_date=today)
        self.assertIsNotNone(summary_range)

        # 3. Session Journeys
        journeys = get_session_journeys(start_date=start, end_date=today, limit=10)
        self.assertIsInstance(journeys, list)

        # Cleanup test records
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM site_usage_events WHERE event_type LIKE 'UNIT_TEST_%'")
        conn.commit()
        conn.close()

    def test_traffic_attribution_and_demographics(self):
        # 1. Traffic Source parsing
        src1, ref1 = parse_traffic_source("https://www.google.com/search?q=stocks", {})
        self.assertEqual(src1, "Google Search")

        src2, ref2 = parse_traffic_source("https://t.co/xyz123", {})
        self.assertEqual(src2, "X / Twitter")

        src3, ref3 = parse_traffic_source("https://www.linkedin.com/feed", {})
        self.assertEqual(src3, "LinkedIn")

        src4, ref4 = parse_traffic_source("", {"utm_source": "newsletter"})
        self.assertEqual(src4, "newsletter")

        src5, ref5 = parse_traffic_source("", {})
        self.assertEqual(src5, "Direct / Bookmark")

        # 2. User Agent Demographics
        desktop_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        info_d = parse_user_agent(desktop_ua)
        self.assertEqual(info_d["device"], "Desktop")
        self.assertEqual(info_d["browser"], "Chrome")
        self.assertEqual(info_d["os"], "macOS")

        mobile_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        info_m = parse_user_agent(mobile_ua)
        self.assertEqual(info_m["device"], "Mobile")
        self.assertEqual(info_m["browser"], "Safari")
        self.assertEqual(info_m["os"], "iOS")

    def test_admin_passcode_verification(self):
        # Verify valid and invalid passcodes
        current_passcode = get_admin_passcode()
        self.assertTrue(verify_admin_passcode(current_passcode))
        self.assertFalse(verify_admin_passcode("wrong_password_xyz"))
        self.assertFalse(verify_admin_passcode(""))

if __name__ == "__main__":
    unittest.main()
