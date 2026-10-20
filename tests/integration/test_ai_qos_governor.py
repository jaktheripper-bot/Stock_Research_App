"""
Integration test suite for Actor-Scoped AI QoS Governor & Single-Flight Coalescer (Wave 15).
Validates 3-lane priority QoS gating, bot protection, daemon spend isolation, VIP immunity,
and single-flight ticker locking.
"""
import threading
import time
import unittest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from web.main import app
from core.billing.qos_governor import (
    authorize_llm_execution,
    single_flight_ticker_lock,
    reset_qos_windows_for_test,
    record_daemon_spend_usd,
    get_daemon_daily_spend_usd,
    MAX_COPILOT_TURNS_PER_USER_HOUR,
    MAX_SYNTHESIS_PER_USER_HOUR,
    MAX_ANON_REQUESTS_PER_IP_MINUTE,
    MAX_DAEMON_DAILY_SPEND_USD,
)
from core.db.reports import save_report_to_archive, get_report_by_ticker
from core.db.connection import init_db


class TestAiQosGovernor(unittest.TestCase):
    """Rigorous tests for 3-lane QoS governor and single-flight coalescing."""

    def setUp(self):
        init_db()
        reset_qos_windows_for_test()

    def tearDown(self):
        reset_qos_windows_for_test()

    def test_01_lane_1_anon_and_free_tier_ip_burst_limiting(self):
        """Lane 1: Unauthenticated or free-tier users get deterministic replies and IP rate limiting."""
        ip = "192.168.1.101"

        # Within the 30 req/min limit, free tier is routed to deterministic only
        for i in range(MAX_ANON_REQUESTS_PER_IP_MINUTE):
            ok, reason = authorize_llm_execution(
                actor_type="ANON",
                client_ip=ip,
                has_unlocked_dossier=False
            )
            self.assertFalse(ok)
            self.assertEqual(reason, "FREE_TIER_DETERMINISTIC_ONLY")

        # The 31st request exceeds burst rate limit
        ok, reason = authorize_llm_execution(
            actor_type="ANON",
            client_ip=ip,
            has_unlocked_dossier=False
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "RATE_LIMIT_IP_BURST")

        # Different IP is not affected
        ok2, reason2 = authorize_llm_execution(
            actor_type="ANON",
            client_ip="192.168.1.102",
            has_unlocked_dossier=False
        )
        self.assertFalse(ok2)
        self.assertEqual(reason2, "FREE_TIER_DETERMINISTIC_ONLY")

    def test_02_lane_2_background_daemon_spend_ceiling(self):
        """Lane 2: Background cron jobs are capped at MAX_DAEMON_DAILY_SPEND_USD ($5.00/day)."""
        # Initially spend is 0.0 -> authorized
        ok, reason = authorize_llm_execution(
            actor_type="BACKGROUND_DAEMON",
            current_daemon_spend_usd=0.0
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "DAEMON_AUTHORIZED")

        # Under the $5.00 budget
        record_daemon_spend_usd(2.50)
        self.assertAlmostEqual(get_daemon_daily_spend_usd(), 2.50)
        ok, reason = authorize_llm_execution(
            actor_type="BACKGROUND_DAEMON",
            current_daemon_spend_usd=get_daemon_daily_spend_usd()
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "DAEMON_AUTHORIZED")

        # Spend reaches or exceeds $5.00
        record_daemon_spend_usd(2.50)
        self.assertAlmostEqual(get_daemon_daily_spend_usd(), 5.00)
        ok, reason = authorize_llm_execution(
            actor_type="BACKGROUND_DAEMON",
            current_daemon_spend_usd=get_daemon_daily_spend_usd()
        )
        self.assertFalse(ok)
        self.assertIn("DAEMON_BUDGET_PAUSED", reason)

    def test_03_lane_3_vip_paying_unlocked_users_immunity_and_velocity_cap(self):
        """Lane 3: VIP paying/unlocked users are immune to daemon spend and bot bursts."""
        # Max out daemon spend and burst another IP
        record_daemon_spend_usd(10.00)
        for _ in range(35):
            authorize_llm_execution("ANON", client_ip="192.168.1.99")

        vip_email = "vip_allocator@moatnomics.com"

        # 1. VIP Copilot is authorized despite daemon budget pause
        ok, reason = authorize_llm_execution(
            actor_type="USER_COPILOT",
            user_email=vip_email,
            client_ip="192.168.1.99",  # Even if from the same IP!
            has_unlocked_dossier=True
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "VIP_COPILOT_AUTHORIZED")

        # 2. Test Copilot hourly velocity cap (40 turns/hr)
        # Already used 1 turn above, now run 39 more
        for _ in range(MAX_COPILOT_TURNS_PER_USER_HOUR - 1):
            ok, reason = authorize_llm_execution(
                actor_type="USER_COPILOT",
                user_email=vip_email,
                has_unlocked_dossier=True
            )
            self.assertTrue(ok)

        # 41st turn is velocity-capped to prevent account abuse
        ok, reason = authorize_llm_execution(
            actor_type="USER_COPILOT",
            user_email=vip_email,
            has_unlocked_dossier=True
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "USER_COPILOT_HOURLY_VELOCITY_CAP")

        # 3. Test VIP Synthesis hourly velocity cap (20/hr)
        for _ in range(MAX_SYNTHESIS_PER_USER_HOUR):
            ok, reason = authorize_llm_execution(
                actor_type="USER_SYNTHESIS",
                user_email=vip_email
            )
            self.assertTrue(ok)
            self.assertEqual(reason, "VIP_SYNTHESIS_AUTHORIZED")

        # 21st synthesis is velocity-capped
        ok, reason = authorize_llm_execution(
            actor_type="USER_SYNTHESIS",
            user_email=vip_email
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "USER_SYNTHESIS_HOURLY_VELOCITY_CAP")

    def test_04_single_flight_coalescer_concurrency(self):
        """Single-Flight Coalescer: Concurrent requests for same ticker coalesce onto 1 execution."""
        ticker = f"COAL_{int(time.time() * 1000)}"
        synthesis_call_count = 0
        synthesis_lock = threading.Lock()
        results = []


        def worker_task(worker_id: int):
            nonlocal synthesis_call_count
            with single_flight_ticker_lock(ticker):
                cached = get_report_by_ticker(ticker)
                if cached and cached.get("report_text") and len(cached.get("report_text", "").strip()) >= 500:
                    results.append((worker_id, "CACHED", cached.get("report_text")))
                    return

                # Simulate slow first synthesis
                with synthesis_lock:
                    synthesis_call_count += 1
                time.sleep(0.05)  # simulate LLM latency

                # Save synthesized report to cache
                dummy_stock_data = {
                    "ticker": ticker,
                    "short_name": "Coalesce Test Ltd",
                    "sector": "Technology"
                }
                dummy_report_text = "# DIAGNOSTIC SUMMARY & KEY TAKEAWAYS\n\n## Pillar 1: Macro\n" + ("Valid Report Text " * 50)
                save_report_to_archive(dummy_stock_data, dummy_report_text, revision_trigger="Test Coalesce")
                results.append((worker_id, "SYNTHESIZED", dummy_report_text))

        # Launch 5 concurrent threads for the exact same ticker
        threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 5)
        # Exactly 1 thread performed the synthesis; the remaining 4 threads reused the cached result
        self.assertEqual(synthesis_call_count, 1)
        cached_returns = [r for r in results if r[1] == "CACHED"]
        self.assertEqual(len(cached_returns), 4)

        from core.db.telemetry import purge_test_telemetry
        purge_test_telemetry()

    def test_05_api_copilot_chat_ip_burst_and_velocity_cap(self):
        """Outside-In: /api/copilot/chat responds with RATE_LIMITED on IP burst and VELOCITY_CAPPED on cap."""
        client = TestClient(app)

        # 1. Trigger IP burst rate limit (30 requests/minute)
        for _ in range(MAX_ANON_REQUESTS_PER_IP_MINUTE):
            resp = client.post(
                "/api/copilot/chat",
                json={"ticker": "INFY", "message": "Give me DCF details", "conversation_id": "conv_burst_test"}
            )
            self.assertEqual(resp.status_code, 200)

        # 31st request receives rate limited notice
        resp_burst = client.post(
            "/api/copilot/chat",
            json={"ticker": "INFY", "message": "Give me DCF details", "conversation_id": "conv_burst_test"}
        )
        self.assertEqual(resp_burst.status_code, 200)
        data = resp_burst.json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("status"), "RATE_LIMITED")
        self.assertIn("Rate Limit Exceeded", data.get("response", ""))

    def test_06_dossier_synthesis_velocity_cap_http_429(self):
        """Outside-In: Full synthesis route rejects beyond hourly velocity cap with HTTP 429."""
        from unittest import mock
        client = TestClient(app)
        email = "burst_allocator@test.com"

        # Max out USER_SYNTHESIS window for this user
        for _ in range(MAX_SYNTHESIS_PER_USER_HOUR):
            authorize_llm_execution("USER_SYNTHESIS", user_email=email)

        # Authenticated user attempting full synthesis returns HTTP 429
        with mock.patch("web.routers.dossier._get_current_web_user", return_value={"id": "usr_burst", "email": email, "subscription_tier": "free"}):
            resp = client.post(
                "/api/synthesize",
                json={"ticker": "INFY", "user_id": email, "force_refresh": True}
            )
            self.assertEqual(resp.status_code, 429)
            self.assertIn("Hourly report generation limit reached", resp.json().get("detail", ""))



if __name__ == "__main__":
    unittest.main()
