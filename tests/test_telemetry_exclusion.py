import os
import unittest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from web.main import app, _generate_admin_token, ADMIN_COOKIE_NAME
from core.db import get_db_connection
from core.db.telemetry import (
    record_usage_event,
    get_site_usage_summary,
    get_session_journeys,
    get_user_usage_analytics,
    is_synthetic_test_event,
    is_admin_visit_event,
    is_excluded_telemetry_event,
    purge_test_telemetry,
)
from core.db.users import get_revenue_analytics_summary, get_all_billables

class TestTelemetryExclusion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        cls.client = TestClient(app)

    def setUp(self):
        self.conn = get_db_connection()
        self.cursor = self.conn.cursor()

    def tearDown(self):
        # Clean up any test records
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
        """Validates unit detectors for synthetic tests and administrative visits."""
        # Test synthetic event detection
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

        # Test admin event detection
        self.assertTrue(is_admin_visit_event(landing_page="/admin"))
        self.assertTrue(is_admin_visit_event(landing_page="/admin/telemetry"))
        self.assertTrue(is_admin_visit_event(details={"landing_page": "/admin/dashboard"}))
        self.assertTrue(is_admin_visit_event(event_type="ADMIN_USER_CREDIT_GRANT"))
        self.assertTrue(is_admin_visit_event(user_email="lyndnpnto@gmail.com"))
        self.assertTrue(is_admin_visit_event(user_email="admin@stockresearch.internal"))
        self.assertTrue(is_admin_visit_event(user_id="adm_owner_lyndon"))
        self.assertTrue(is_admin_visit_event(user_id="adm_moderator_1"))

        # Combined exclusion
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
        """Ensures /api/telemetry/event ignores requests with admin cookies."""
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

        # Verify nothing was written to site_usage_events
        self.cursor.execute("SELECT COUNT(*) FROM site_usage_events WHERE session_id = 'test_excl_adm_sess'")
        self.assertEqual(self.cursor.fetchone()[0], 0)

        # Clear cookie
        self.client.cookies.delete(ADMIN_COOKIE_NAME)

    def test_api_telemetry_rejects_admin_route_visit(self):
        """Ensures /api/telemetry/event ignores requests browsing /admin paths."""
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
        """Ensures get_site_usage_summary, get_session_journeys, and get_user_usage_analytics never count test/admin data."""
        # Insert a real visitor event
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

        # Insert a test event
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

        # Insert an admin visit event
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

        # 1. Site Usage Summary with exclude_tests=True
        summary = get_site_usage_summary(days=30, exclude_tests=True)
        tickers = [item["ticker"] for item in summary.get("top_searched_tickers", [])]
        self.assertNotIn("TEST_CORP", tickers)
        self.assertNotIn("APP", tickers)

        for event in summary.get("recent_events", []):
            self.assertNotEqual(event.get("event_type"), "ADMIN_LOGIN")
            self.assertNotEqual(event.get("ticker"), "TEST_CORP")
            self.assertNotEqual(event.get("session_id"), "test_excl_")

        # 2. Session Journeys with exclude_tests=True
        journeys = get_session_journeys(days=30, limit=50, exclude_tests=True)
        session_ids = [j.get("session_id") for j in journeys]
        self.assertNotIn("test_excl_synthetic_test_sess", session_ids)
        self.assertNotIn("test_excl_admin_session_touch", session_ids)

        # 3. User analytics
        user_metrics = get_user_usage_analytics(days=30, exclude_tests=True)
        top_user_emails = [u.get("email") for u in user_metrics.get("top_users", [])]
        self.assertNotIn("bot@example.com", top_user_emails)
        self.assertNotIn("lyndnpnto@gmail.com", top_user_emails)

        # 4. Revenue analytics
        rev_metrics = get_revenue_analytics_summary(days=30, exclude_tests=True)
        self.assertIsInstance(rev_metrics.get("gross_revenue_inr"), (int, float))

if __name__ == "__main__":
    unittest.main()
