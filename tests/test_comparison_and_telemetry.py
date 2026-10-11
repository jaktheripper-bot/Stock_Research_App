"""
Consolidated Peer Comparison & Telemetry Analytics Test Suite
==============================================================
Unifies:
1. Company disparity evaluation & peer comparison mechanics
2. Telemetry event recording, traffic attribution, date-range summaries & landing page tracking
3. Localized fundamental ratios cache & clean formatting (/compare)
4. Telemetry synthetic/admin event exclusion filters and revenue isolation
"""
import asyncio
from datetime import date, datetime, timedelta
import os
import sys
import unittest

from fastapi.testclient import TestClient

from core.analysis.fundamentals import _FUNDAMENTALS_CACHE, compute_pead_drift_band, enrich_fundamentals, get_stock_fundamentals
from core.analysis.peer_comparison import compare_two_companies, evaluate_company_disparity
from core.db import get_db_connection, get_placeholder
from core.db.fundamentals import (
    extract_fundamentals_from_report_text,
    get_cached_fundamentals,
    save_cached_fundamentals,
    sync_all_cached_fundamentals,
)
from core.db.reports import save_report_to_archive
from core.db.telemetry import (
    classify_page_category,
    get_session_journeys,
    get_site_usage_summary,
    get_user_usage_analytics,
    is_admin_visit_event,
    is_excluded_telemetry_event,
    is_synthetic_test_event,
    purge_test_telemetry,
    record_usage_event,
)
from core.db.users import get_all_billables, get_revenue_analytics_summary
from telemetry import (
    get_admin_passcode,
    parse_traffic_source,
    parse_user_agent,
    verify_admin_passcode,
)
from web.main import ADMIN_COOKIE_NAME, _generate_admin_token, app


# ==============================================================================
# 1. Company Disparity & Telemetry Summaries
# ==============================================================================
class TestComparisonAndTelemetry(unittest.TestCase):
    def test_evaluate_company_disparity_axes(self):
        infy = {"sector": "Technology", "market_cap": 6000000000000.0, "pe_ratio": 24.5}
        tcs = {"sector": "Technology", "market_cap": 14000000000000.0, "pe_ratio": 28.1}
        disp = evaluate_company_disparity(infy, tcs)
        self.assertFalse(disp["is_disparate"])
        self.assertFalse(disp["sector_mismatch"])
        self.assertFalse(disp["lifecycle_mismatch"])
        self.assertFalse(disp["scale_mismatch"])
        self.assertEqual(len(disp["warnings"]), 0)

        hdfc = {"sector": "Financial Services", "market_cap": 12000000000000.0, "pe_ratio": 19.2}
        disp_sec = evaluate_company_disparity(infy, hdfc)
        self.assertTrue(disp_sec["is_disparate"])
        self.assertTrue(disp_sec["sector_mismatch"])

        zomato_loss = {"sector": "Consumer Cyclical", "market_cap": 1500000000000.0, "pe_ratio": "Loss-Making"}
        itc_profit = {"sector": "Consumer Defensive", "market_cap": 6000000000000.0, "pe_ratio": 26.5}
        disp_life = evaluate_company_disparity(zomato_loss, itc_profit)
        self.assertTrue(disp_life["is_disparate"])
        self.assertTrue(disp_life["lifecycle_mismatch"])

        micro = {"sector": "Technology", "market_cap": 500000000.0, "pe_ratio": 20.0}
        mega = {"sector": "Technology", "market_cap": 6000000000000.0, "pe_ratio": 25.0}
        disp_scale = evaluate_company_disparity(micro, mega)
        self.assertTrue(disp_scale["is_disparate"])
        self.assertTrue(disp_scale["scale_mismatch"])

    def test_telemetry_recording_and_date_range_summary(self):
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

        summary_days = get_site_usage_summary(days=1, exclude_tests=False)
        self.assertIsNotNone(summary_days)
        self.assertIn("total_queries", summary_days)
        self.assertIn("traffic_sources", summary_days)
        self.assertIn("top_landing_pages", summary_days)
        self.assertIn("top_visited_pages", summary_days)
        self.assertIn("geographic_distribution", summary_days)

        today = date.today()
        start = today - timedelta(days=2)
        summary_range = get_site_usage_summary(start_date=start, end_date=today, exclude_tests=False)
        self.assertIsNotNone(summary_range)
        self.assertIn("top_landing_pages", summary_range)

        journeys = get_session_journeys(start_date=start, end_date=today, limit=10, exclude_tests=False)
        self.assertIsInstance(journeys, list)
        if len(journeys) > 0:
            self.assertIn("landing_page", journeys[0])

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM site_usage_events WHERE event_type LIKE 'UNIT_TEST_%'")
        conn.commit()
        conn.close()

    def test_traffic_attribution_and_demographics(self):
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
        current_passcode = get_admin_passcode()
        self.assertTrue(verify_admin_passcode(current_passcode))
        self.assertFalse(verify_admin_passcode("wrong_password_xyz"))
        self.assertFalse(verify_admin_passcode(""))

    def test_revenue_analytics_paid_vs_free_tokens_and_purge(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()

        try:
            cursor.execute("DELETE FROM credit_transactions;")
            conn.commit()

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

            summary = get_revenue_analytics_summary(exclude_tests=True)
            self.assertEqual(summary["gross_revenue_inr"], 299.0)
            self.assertEqual(summary["paid_orders_count"], 1)
            self.assertEqual(summary["paid_credits_issued"], 20.0)
            self.assertEqual(summary["welcome_grants_count"], 1)
            self.assertEqual(summary["free_credits_issued"], 2.0)

            billables = get_all_billables(exclude_tests=True)
            billable_ids = [b["id"] for b in billables]
            self.assertIn("tx_real_test_1", billable_ids)
            self.assertIn("tx_welcome_test_1", billable_ids)
            self.assertNotIn("tx_sim_test_1", billable_ids)

            real_tx = next(b for b in billables if b["id"] == "tx_real_test_1")
            self.assertEqual(real_tx["nature"], "VERIFIED_PAID")

            welcome_tx = next(b for b in billables if b["id"] == "tx_welcome_test_1")
            self.assertEqual(welcome_tx["nature"], "FREE_GRANT")

            counts = purge_test_telemetry()
            self.assertGreaterEqual(counts.get("transactions_purged", 0), 1)

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

    def test_landing_pages_telemetry_and_classification(self):
        self.assertEqual(classify_page_category("/")[0], "Homepage / Terminal")
        self.assertEqual(classify_page_category("/dossier/INFY")[0], "Equity Dossier (INFY)")
        self.assertEqual(classify_page_category("/funds")[0], "Mutual Fund Directory")
        self.assertEqual(classify_page_category("/funds/118989")[0], "Mutual Fund Forensic Dossier")
        self.assertEqual(classify_page_category("/debt")[0], "Corporate Debt Directory")
        self.assertEqual(classify_page_category("/pricing")[0], "Pricing & Subscriptions")
        self.assertEqual(classify_page_category("/compare")[0], "Peer Head-to-Head Compare")
        self.assertEqual(classify_page_category("/opportunities")[0], "Multi-Asset Terminal")

        sess_id = "sess_landing_test_999"
        record_usage_event(
            event_type="PAGE_VIEW",
            ticker="TCS",
            session_id=sess_id,
            landing_page="/funds",
            traffic_source="Google Search",
            is_test_override=True
        )

        try:
            summary = get_site_usage_summary(days=1, exclude_tests=False)
            self.assertIn("top_landing_pages", summary)
            self.assertIn("top_visited_pages", summary)
            landing_paths = [lp["path"] for lp in summary["top_landing_pages"]]
            self.assertIn("/funds", landing_paths)

            journeys = get_session_journeys(days=1, limit=50, exclude_tests=False)
            test_journey = next((j for j in journeys if j["session_id"] == sess_id), None)
            self.assertIsNotNone(test_journey)
            self.assertEqual(test_journey["landing_page"], "/funds")
        finally:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("DELETE FROM site_usage_events WHERE session_id = ?", (sess_id,))
            conn.commit()
            c.close()
            conn.close()


# ==============================================================================
# 2. Localized DB Fundamentals Cache & Peer Comparison Harmonization
# ==============================================================================
class TestPeerComparisonDataHarmonization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _FUNDAMENTALS_CACHE.clear()

        infy_data = {
            "ticker": "INFY",
            "short_name": "Infosys Ltd",
            "current_price": 1023.4,
            "pe_ratio": "13.95",
            "market_cap": 4153240276683.12,
        }
        infy_text = """### Health Matrix
- Macro: Headwinds
- Moat: Wide
- Governance: Clean
- Diagnostic: Temporary
- Valuation: Undervalued
- Balance Sheet: Debt-Free
- Capital Allocation: Disciplined

- **Return Ratios:** ROE [Return on Equity] remains strong at 31.68%. ROCE [Return on Capital Employed] was 42.84% in FY 2026.
- **Operating Margins:** Operating margins remain healthy within the 20.0% band.
The stock has fallen from its 52-week high of INR 1,727.85 toward INR 1,013.00, close to its 52-week low of INR 980.30.
"""
        save_report_to_archive(stock_data=infy_data, report_text=infy_text)

        tcs_data = {
            "ticker": "TCS",
            "short_name": "Tata Consultancy Services Ltd",
            "current_price": 2156.0,
            "pe_ratio": "15.65",
            "market_cap": 7800596706254.95,
        }
        tcs_text = """### Health Matrix
- Macro: Headwinds
- Moat: Wide
- Governance: Clean
- Diagnostic: Temporary
- Valuation: Undervalued
- Balance Sheet: Debt-Free
- Capital Allocation: Disciplined

- **Return Metrics:** TCS consistently records an ROE [Return on Equity] above 45.0% and an ROCE [Return on Capital Employed] exceeding 55.0%.
- **Operating Margins:** Operating margin stands firm between 24.0% and 25.3%.
The stock price has experienced downward pressure from its 52-week high of INR 3,336.70 toward its 52-week low near INR 1,976.00.
"""
        save_report_to_archive(stock_data=tcs_data, report_text=tcs_text)

        sync_all_cached_fundamentals()
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    def test_extract_fundamentals_from_report_text(self):
        sample_report = """
        ### Health Matrix
        - Balance Sheet: Debt-Free
        - Moat: Wide

        - **Return Ratios:** ROE [Return on Equity] remains strong at 28.5%. ROCE [Return on Capital Employed] was 36.2% in FY 2026.
        - **Operating Margins:** Operating margins remain healthy within the 22.4% band.
        - **Price Action:** The stock corrected from its 52-week high of INR 1,500.00 toward its 52-week low of INR 950.50.
        """
        extracted = extract_fundamentals_from_report_text(sample_report)
        self.assertEqual(extracted.get("roce"), 36.2)
        self.assertEqual(extracted.get("roe"), 28.5)
        self.assertEqual(extracted.get("operating_margin"), 22.4)
        self.assertEqual(extracted.get("debt_to_equity"), 0.0)
        self.assertEqual(extracted.get("fifty_two_week_high"), 1500.0)
        self.assertEqual(extracted.get("fifty_two_week_low"), 950.5)

    def test_cached_fundamentals_crud_and_aliases(self):
        test_data = {
            "ticker": "TESTPEER",
            "company_name": "Test Peer Diagnostics Ltd",
            "current_price": 500.0,
            "market_cap": 25000000000.0,
            "pe_ratio": "22.5",
            "roce": 26.4,
            "roe": 19.8,
            "operating_margin": 18.2,
            "debt_to_equity": 0.15,
            "fifty_two_week_high": 620.0,
            "fifty_two_week_low": 410.0,
            "source": "UNIT_TEST"
        }
        save_cached_fundamentals("TESTPEER", test_data)
        cached = get_cached_fundamentals("TESTPEER")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["ticker"], "TESTPEER")
        self.assertEqual(cached["roce"], 26.4)
        self.assertEqual(cached["roce_pct"], 26.4)
        self.assertEqual(cached["roe"], 19.8)
        self.assertEqual(cached["operating_margin"], 18.2)
        self.assertEqual(cached["opm"], 18.2)
        self.assertEqual(cached["debt_to_equity"], 0.15)
        self.assertEqual(cached["fifty_two_week_high"], 620.0)
        self.assertEqual(cached["52w_high"], 620.0)
        self.assertEqual(cached["fifty_two_week_low"], 410.0)
        self.assertEqual(cached["52w_low"], 410.0)

    def test_enrich_fundamentals_merges_cache_without_double_formatting(self):
        raw_fund = {"ticker": "INFY", "current_price": 1023.4}
        enriched = enrich_fundamentals("INFY", raw_fund)
        self.assertIsNotNone(enriched.get("roce"))
        self.assertIsNotNone(enriched.get("roe"))
        self.assertIsNotNone(enriched.get("fifty_two_week_high"))
        self.assertNotIn("%", str(enriched["roce"]))
        self.assertNotIn("%", str(enriched["roe"]))

    def test_compare_two_companies_live_resolution(self):
        res = asyncio.run(compare_two_companies("INFY", "TCS"))
        self.assertIn("fund_a", res)
        self.assertIn("fund_b", res)
        fund_a = res["fund_a"]
        fund_b = res["fund_b"]

        for key in ["roce", "roe", "operating_margin", "debt_to_equity", "fifty_two_week_high", "fifty_two_week_low"]:
            self.assertIsNotNone(fund_a.get(key), f"Key {key} was None for INFY")
            self.assertNotEqual(fund_a.get(key), "N/A", f"Key {key} was N/A for INFY")
            self.assertIsNotNone(fund_b.get(key), f"Key {key} was None for TCS")
            self.assertNotEqual(fund_b.get(key), "N/A", f"Key {key} was N/A for TCS")

    def test_compare_page_html_rendering_e2e(self):
        response = self.client.get("/compare?a=INFY&b=TCS")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("INFY", html)
        self.assertIn("TCS", html)
        self.assertNotIn("₹₹", html)
        self.assertNotIn("%%", html)
        self.assertNotIn("N/A%", html)
        self.assertNotIn("₹N/A", html)
        self.assertIn("42.84%", html)
        self.assertTrue("31.68%" in html or "32.0%" in html)
        self.assertIn("55", html)
        self.assertIn("₹980.3", html)
        self.assertIn("₹1727.85", html)


# ==============================================================================
# 3. Telemetry Synthetic & Admin Event Exclusion
# ==============================================================================
class TestTelemetryExclusion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        cls.client = TestClient(app)

    def setUp(self):
        self.conn = get_db_connection()
        self.cursor = self.conn.cursor()

    def tearDown(self):
        try:
            self.cursor.execute("DELETE FROM site_usage_events WHERE session_id LIKE 'test_excl_%' OR user_email LIKE '%excl_test%'")
            self.cursor.execute("DELETE FROM user_accounts WHERE id LIKE 'usr_excl_test_%' OR email LIKE '%excl_test%'")
            self.cursor.execute("DELETE FROM credit_transactions WHERE id LIKE 'tx_excl_test_%' OR customer_email LIKE '%excl_test%'")
            self.conn.commit()
        except Exception:
            pass
        finally:
            self.cursor.close()
            self.conn.close()

    def test_detector_functions(self):
        self.assertTrue(is_synthetic_test_event(user_email="tester@example.com"))
        self.assertTrue(is_synthetic_test_event(user_email="user@test.com"))
        self.assertTrue(is_synthetic_test_event(browser="python-requests/2.31.0"))
        self.assertTrue(is_synthetic_test_event(browser="testclient"))
        self.assertTrue(is_synthetic_test_event(user_id="guest_web_user"))
        self.assertTrue(is_synthetic_test_event(user_id="usr_test_987654"))
        self.assertTrue(is_synthetic_test_event(ticker="TEST"))
        self.assertTrue(is_synthetic_test_event(ticker="UNIT_TEST_TICKER"))
        self.assertTrue(is_synthetic_test_event(session_id="test_sess_001"))
        self.assertTrue(is_synthetic_test_event(event_type="UNIT_TEST_SAMPLE"))

        self.assertTrue(is_admin_visit_event(landing_page="/admin"))
        self.assertTrue(is_admin_visit_event(landing_page="/admin/telemetry"))
        self.assertTrue(is_admin_visit_event(details={"landing_page": "/admin/dashboard"}))
        self.assertTrue(is_admin_visit_event(event_type="ADMIN_USER_CREDIT_GRANT"))
        self.assertTrue(is_admin_visit_event(user_email="lyndnpnto@gmail.com"))
        self.assertTrue(is_admin_visit_event(user_email="admin@stockresearch.internal"))
        self.assertTrue(is_admin_visit_event(user_id="adm_owner_lyndon"))
        self.assertTrue(is_admin_visit_event(user_id="adm_moderator_1"))

        self.assertTrue(is_excluded_telemetry_event(landing_page="/admin"))
        self.assertTrue(is_excluded_telemetry_event(browser="testclient"))
        self.assertTrue(is_excluded_telemetry_event(user_email="test@example.com"))
        self.assertFalse(is_excluded_telemetry_event(
            landing_page="/dossier/RELIANCE",
            browser="Mozilla/5.0 Chrome/120.0",
            user_email="investor.rahul@gmail.com",
            user_id="usr_investor_123",
            ticker="RELIANCE"
        ))

    def test_api_telemetry_rejects_admin_session(self):
        admin_token = _generate_admin_token("lyndnpnto@gmail.com", "superadmin")
        self.client.cookies.set(ADMIN_COOKIE_NAME, admin_token)

        resp = self.client.post("/api/telemetry/event", json={
            "event_type": "page_view",
            "landing_page": "/dossier/TCS",
            "ticker": "TCS",
            "session_id": "test_excl_adm_sess"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "filtered")
        self.assertEqual(data.get("reason"), "admin_session")

        self.cursor.execute("SELECT COUNT(*) FROM site_usage_events WHERE session_id = 'test_excl_adm_sess'")
        self.assertEqual(self.cursor.fetchone()[0], 0)
        self.client.cookies.delete(ADMIN_COOKIE_NAME)

    def test_api_telemetry_rejects_admin_route_visit(self):
        resp = self.client.post("/api/telemetry/event", json={
            "event_type": "page_view",
            "landing_page": "/admin",
            "session_id": "test_excl_admin_path"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "filtered")
        self.assertEqual(data.get("reason"), "test_or_admin")

        self.cursor.execute("SELECT COUNT(*) FROM site_usage_events WHERE session_id = 'test_excl_admin_path'")
        self.assertEqual(self.cursor.fetchone()[0], 0)

    def test_calculations_exclude_tests_and_admin_records(self):
        record_usage_event(
            event_type="SEARCH",
            ticker="INFY",
            latency_ms=25.0,
            cost_saved_usd=0.036,
            session_id="test_excl_real_investor_session",
            traffic_source="Organic Search",
            referrer="https://www.google.com",
            country="IN",
            device_type="Desktop",
            browser="Chrome",
            user_id="usr_real_investor_99",
            user_email="investor.sharma@yahoo.com",
            landing_page="/dossier/INFY",
            is_test_override=True
        )

        record_usage_event(
            event_type="SEARCH",
            ticker="TEST_CORP",
            latency_ms=10.0,
            cost_saved_usd=100.0,
            session_id="test_excl_synthetic_test_sess",
            traffic_source="Automated Test",
            browser="testclient",
            user_id="testclient",
            user_email="bot@example.com",
            landing_page="/dossier/TEST_CORP",
            is_test_override=True
        )

        record_usage_event(
            event_type="ADMIN_LOGIN",
            ticker="APP",
            latency_ms=10.0,
            cost_saved_usd=500.0,
            session_id="test_excl_admin_session_touch",
            traffic_source="Direct",
            browser="Chrome",
            user_id="adm_owner_lyndon",
            user_email="lyndnpnto@gmail.com",
            landing_page="/admin",
            is_test_override=True
        )

        summary = get_site_usage_summary(days=30, exclude_tests=True)
        tickers = [item["ticker"] for item in summary.get("top_searched_tickers", [])]
        self.assertNotIn("TEST_CORP", tickers)
        self.assertNotIn("APP", tickers)

        for event in summary.get("recent_events", []):
            self.assertNotEqual(event.get("event_type"), "ADMIN_LOGIN")
            self.assertNotEqual(event.get("ticker"), "TEST_CORP")
            self.assertNotEqual(event.get("session_id"), "test_excl_")

        journeys = get_session_journeys(days=30, limit=50, exclude_tests=True)
        session_ids = [j.get("session_id") for j in journeys]
        self.assertNotIn("test_excl_synthetic_test_sess", session_ids)
        self.assertNotIn("test_excl_admin_session_touch", session_ids)

        user_metrics = get_user_usage_analytics(days=30, exclude_tests=True)
        top_user_emails = [u.get("email") for u in user_metrics.get("top_users", [])]
        self.assertNotIn("bot@example.com", top_user_emails)
        self.assertNotIn("lyndnpnto@gmail.com", top_user_emails)

        rev_metrics = get_revenue_analytics_summary(days=30, exclude_tests=True)
        self.assertIsInstance(rev_metrics.get("gross_revenue_inr"), (int, float))


if __name__ == "__main__":
    unittest.main()
