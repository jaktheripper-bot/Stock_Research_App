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

    def test_revenue_analytics_paid_vs_free_tokens_and_purge(self):
        """
        Verify that real cash income (e.g. Rs. 299) is strictly isolated from
        simulated test checkouts (Rs. 1,499) and promotional welcome tokens (Rs. 0).
        Also verify that purge_test_telemetry deletes simulated/test data without touching real revenue.
        """
        from core.db.users import get_revenue_analytics_summary, get_all_billables
        from core.db.telemetry import purge_test_telemetry
        from core.db.connection import get_db_connection, get_placeholder

        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()

        try:
            # 1. Insert Real Paid Order (Rs. 299)
            cursor.execute(
                f"""
                INSERT INTO credit_transactions (
                    id, user_id, amount_inr, credits_added, payment_gateway,
                    gateway_order_id, gateway_payment_id, status, pack_type, invoice_number,
                    customer_email, customer_name
                ) VALUES ({p}, {p}, 299.0, 20.0, 'razorpay', 'order_real_1', 'pay_real_1', 'success', 'STARTER', 'INV-REAL-1', 'genuine@investor.com', 'Genuine Buyer');
                """,
                ("tx_real_test_1", "usr_real_test_1")
            )

            # 2. Insert Free Welcome Grant (Rs. 0)
            cursor.execute(
                f"""
                INSERT INTO credit_transactions (
                    id, user_id, amount_inr, credits_added, payment_gateway,
                    gateway_order_id, gateway_payment_id, status, pack_type, invoice_number,
                    customer_email, customer_name
                ) VALUES ({p}, {p}, 0.0, 2.0, 'system_grant', NULL, NULL, 'success', 'WELCOME_GRANT', 'INV-WELCOME-1', 'freebie@investor.com', 'Freebie User');
                """,
                ("tx_welcome_test_1", "usr_free_test_1")
            )

            # 3. Insert Simulated / Sandbox Test Order (Rs. 1,499)
            cursor.execute(
                f"""
                INSERT INTO credit_transactions (
                    id, user_id, amount_inr, credits_added, payment_gateway,
                    gateway_order_id, gateway_payment_id, status, pack_type, invoice_number,
                    customer_email, customer_name
                ) VALUES ({p}, {p}, 1499.0, 100.0, 'simulation', 'order_sim_test_99', 'pay_sim_test_99', 'success', 'PRO_MONTHLY', 'INV-SIM-1', 'test@example.com', 'Test Bot');
                """,
                ("tx_sim_test_1", "test_bot_1")
            )
            conn.commit()

            # Test A: Revenue Analytics Summary must ONLY count the Rs. 299 genuine payment
            summary = get_revenue_analytics_summary(exclude_tests=True)
            self.assertEqual(summary["gross_revenue_inr"], 299.0, "Gross income must only be Rs. 299, not inflated by Rs. 1499 simulation")
            self.assertEqual(summary["paid_orders_count"], 1)
            self.assertEqual(summary["paid_credits_issued"], 20.0, "Paid credits must be 20.0 from the Rs. 299 order")
            self.assertEqual(summary["welcome_grants_count"], 1)
            self.assertEqual(summary["free_credits_issued"], 2.0, "Free credits must be 2.0 from welcome grant")

            # Test B: Billables nature tagging
            billables = get_all_billables(exclude_tests=True)
            billable_ids = [b["id"] for b in billables]
            self.assertIn("tx_real_test_1", billable_ids)
            self.assertIn("tx_welcome_test_1", billable_ids)
            self.assertNotIn("tx_sim_test_1", billable_ids, "Simulation transaction should be excluded from clean billables")

            real_tx = next(b for b in billables if b["id"] == "tx_real_test_1")
            self.assertEqual(real_tx["nature"], "VERIFIED_PAID")

            welcome_tx = next(b for b in billables if b["id"] == "tx_welcome_test_1")
            self.assertEqual(welcome_tx["nature"], "FREE_GRANT")

            # Test C: Purge Test Data
            counts = purge_test_telemetry()
            self.assertGreaterEqual(counts.get("transactions_purged", 0), 1)

            # Confirm simulation is gone, but real orders remain
            cursor.execute("SELECT id FROM credit_transactions WHERE id IN ('tx_real_test_1', 'tx_welcome_test_1', 'tx_sim_test_1');")
            remaining = [r[0] for r in cursor.fetchall()]
            self.assertIn("tx_real_test_1", remaining)
            self.assertIn("tx_welcome_test_1", remaining)
            self.assertNotIn("tx_sim_test_1", remaining)

        finally:
            cursor.execute("DELETE FROM credit_transactions WHERE id IN ('tx_real_test_1', 'tx_welcome_test_1', 'tx_sim_test_1');")
            conn.commit()
            cursor.close()
            conn.close()

if __name__ == "__main__":
    unittest.main()
