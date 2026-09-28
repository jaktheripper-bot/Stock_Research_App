import os
import sys
import unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analyzer import evaluate_company_disparity, compare_two_companies
from db import record_usage_event, get_site_usage_summary, get_db_connection

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

    def test_telemetry_recording_and_summary(self):
        # Record test telemetry events
        record_usage_event("UNIT_TEST_SEARCH", ticker="UNIT_TEST_TICKER", latency_ms=15.0)
        record_usage_event("UNIT_TEST_CACHE", ticker="UNIT_TEST_TICKER", cost_saved_usd=0.036)

        summary = get_site_usage_summary(days=1)
        self.assertIsNotNone(summary)
        self.assertIn("total_queries", summary)
        self.assertIn("cache_efficiency_pct", summary)
        self.assertIn("total_cost_saved_usd", summary)

        # Cleanup test records
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM site_usage_events WHERE event_type LIKE 'UNIT_TEST_%'")
        conn.commit()
        conn.close()

if __name__ == "__main__":
    unittest.main()
