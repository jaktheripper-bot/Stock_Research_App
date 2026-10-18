"""Unit tests for Actor-Scoped AI QoS Governor & Single-Flight Coalescer (Wave 15).

Verifies:
1. VIP immunity during daemon budget exhaustion (daemon pauses, VIP allocators remain unblocked).
2. Rogue user isolation (rogue user throttled at hourly cap while legitimate user remains unaffected).
3. Single-flight ticker lock coalescing across 10 concurrent threads (exactly 1 LLM call executes, 9 reuse cached report).
"""

import threading
import time
import unittest

from core.analytics.ai_qos_governor import (
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


class TestAiQosGovernorUnit(unittest.TestCase):
    """Unit test suite for Actor-Scoped AI QoS Governor & Single-Flight Coalescer."""

    def setUp(self):
        init_db()
        reset_qos_windows_for_test()

    def tearDown(self):
        reset_qos_windows_for_test()

    def test_vip_immunity_during_daemon_budget_exhaustion(self):
        """VIP paying users must remain 100% authorized even when background daemon budget is exhausted."""
        # 1. Exhaust daemon spend well beyond the limit ($999.00 spent)
        record_daemon_spend_usd(999.00)
        self.assertGreaterEqual(get_daemon_daily_spend_usd(), MAX_DAEMON_DAILY_SPEND_USD)

        # 2. Daemon execution must be rejected/paused
        daemon_ok, daemon_reason = authorize_llm_execution(
            actor_type="BACKGROUND_DAEMON",
            current_daemon_spend_usd=get_daemon_daily_spend_usd(),
        )
        self.assertFalse(daemon_ok)
        self.assertIn("DAEMON_BUDGET_PAUSED", daemon_reason)

        # 3. VIP paying user for synthesis must remain 100% unblocked
        vip_email = "paying_allocator@moatnomics.com"
        vip_synth_ok, vip_synth_reason = authorize_llm_execution(
            actor_type="USER_SYNTHESIS",
            user_email=vip_email,
            has_unlocked_dossier=True,
            current_daemon_spend_usd=get_daemon_daily_spend_usd(),
        )
        self.assertTrue(vip_synth_ok, f"VIP synthesis blocked: {vip_synth_reason}")
        self.assertEqual(vip_synth_reason, "VIP_SYNTHESIS_AUTHORIZED")

        # 4. VIP user for Copilot must also remain 100% unblocked
        vip_copilot_ok, vip_copilot_reason = authorize_llm_execution(
            actor_type="USER_COPILOT",
            user_email=vip_email,
            has_unlocked_dossier=True,
            current_daemon_spend_usd=get_daemon_daily_spend_usd(),
        )
        self.assertTrue(vip_copilot_ok, f"VIP copilot blocked: {vip_copilot_reason}")
        self.assertEqual(vip_copilot_reason, "VIP_COPILOT_AUTHORIZED")

    def test_rogue_user_isolation(self):
        """Rogue user exceeding hourly velocity cap must be throttled without affecting other users."""
        rogue_user = "rogue_bot@attacker.com"
        legit_user = "legit_investor@moatnomics.com"

        # 1. Rogue user exhausts all allowed hourly Copilot turns
        for _ in range(MAX_COPILOT_TURNS_PER_USER_HOUR):
            ok, reason = authorize_llm_execution(
                actor_type="USER_COPILOT",
                user_email=rogue_user,
                has_unlocked_dossier=True,
            )
            self.assertTrue(ok)

        # 2. The next attempt from rogue user is throttled
        rogue_ok, rogue_reason = authorize_llm_execution(
            actor_type="USER_COPILOT",
            user_email=rogue_user,
            has_unlocked_dossier=True,
        )
        self.assertFalse(rogue_ok)
        self.assertEqual(rogue_reason, "USER_COPILOT_HOURLY_VELOCITY_CAP")

        # 3. Legitimate user is completely unaffected and proceeds normally
        legit_ok, legit_reason = authorize_llm_execution(
            actor_type="USER_COPILOT",
            user_email=legit_user,
            has_unlocked_dossier=True,
        )
        self.assertTrue(legit_ok, f"Legitimate user incorrectly blocked: {legit_reason}")
        self.assertEqual(legit_reason, "VIP_COPILOT_AUTHORIZED")

    def test_anon_ip_rate_limiting_isolation(self):
        """Anon users are IP rate-limited without paid LLM spend; distinct IPs remain isolated."""
        bad_ip = "192.0.2.100"
        good_ip = "192.0.2.200"

        # Bad IP fires 30 requests -> all deterministic only
        for _ in range(MAX_ANON_REQUESTS_PER_IP_MINUTE):
            ok, reason = authorize_llm_execution(
                actor_type="ANON",
                client_ip=bad_ip,
                has_unlocked_dossier=False,
            )
            self.assertFalse(ok)
            self.assertEqual(reason, "FREE_TIER_DETERMINISTIC_ONLY")

        # 31st request from bad IP triggers rate limiting
        bad_ok, bad_reason = authorize_llm_execution(
            actor_type="ANON",
            client_ip=bad_ip,
            has_unlocked_dossier=False,
        )
        self.assertFalse(bad_ok)
        self.assertEqual(bad_reason, "RATE_LIMIT_IP_BURST")

        # Good IP is not rate limited
        good_ok, good_reason = authorize_llm_execution(
            actor_type="ANON",
            client_ip=good_ip,
            has_unlocked_dossier=False,
        )
        self.assertFalse(good_ok)
        self.assertEqual(good_reason, "FREE_TIER_DETERMINISTIC_ONLY")

    def test_single_flight_coalescing_across_10_concurrent_threads(self):
        """Single-Flight Coalescer: Exactly 1 LLM execution across 10 concurrent threads."""
        ticker = f"UNITCOAL_{int(time.time() * 1000)}"
        synthesis_call_count = 0
        synthesis_count_lock = threading.Lock()
        results = []
        barrier = threading.Barrier(10)

        synthetic_report = (
            f"# Institutional Research Dossier for {ticker}\n"
            "## 1. Executive Summary\n"
            "This company demonstrates durable competitive advantages with high ROCE and expanding margins. "
            "Capital allocation discipline is exemplary with zero promoter pledging and consistent dividend growth. "
            "Free cash flow conversion exceeds 85% with negligible debt obligations on the balance sheet.\n"
            "## 2. Quantitative Health Matrix\n"
            "- Moat: Wide\n- Governance: Clean\n- Balance Sheet: Net Cash\n- Valuation: Fair\n"
            + ("Detailed financial metrics and historical trend analysis. " * 15)
        )

        def worker_task(worker_id: int):
            nonlocal synthesis_call_count
            # Wait for all 10 threads to be ready before firing simultaneously
            barrier.wait()

            with single_flight_ticker_lock(ticker):
                # Double-checked cache lookup inside lock
                cached = get_report_by_ticker(ticker)
                if cached and cached.get("report_text") and len(cached.get("report_text", "").strip()) >= 500:
                    results.append((worker_id, "CACHED", cached.get("report_text")))
                    return

                # First thread executes the simulated expensive LLM synthesis
                with synthesis_count_lock:
                    synthesis_call_count += 1

                # Simulate network/LLM synthesis latency
                time.sleep(0.04)

                # Commit newly synthesized report to DB cache
                save_report_to_archive(
                    stock_data={"ticker": ticker, "short_name": "Coalesce Test Ltd"},
                    report_text=synthetic_report,
                )
                results.append((worker_id, "SYNTHESIZED", synthetic_report))

        threads = []
        for i in range(10):
            t = threading.Thread(target=worker_task, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5.0)

        # Invariant Verification:
        # Exactly 1 thread must have executed the synthesis
        self.assertEqual(
            synthesis_call_count,
            1,
            f"Expected exactly 1 synthesis call across 10 concurrent threads, but got {synthesis_call_count}!",
        )

        # All 10 threads must have received the full report
        self.assertEqual(len(results), 10, "All 10 threads must complete successfully.")
        synthesized_count = sum(1 for _, status, _ in results if status == "SYNTHESIZED")
        cached_count = sum(1 for _, status, _ in results if status == "CACHED")

        self.assertEqual(synthesized_count, 1, "Exactly 1 worker must perform synthesis.")
        self.assertEqual(cached_count, 9, "9 workers must reuse the cached report.")

        # Every worker's report text must match the expected report
        for worker_id, _, text in results:
            self.assertEqual(text, synthetic_report)


if __name__ == "__main__":
    unittest.main()
