"""
tests/unit/test_affiliated_services_contract.py
==============================================================================
Unit tests for Affiliated External Services Health Matrix and Contracts.
==============================================================================
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from scripts.check_affiliated_services import (
    check_supabase_db,
    check_betterstack,
    check_angel_one,
    check_gemini_ai,
    check_perplexity_sonar,
    check_resend_email,
    check_razorpay,
)


class TestAffiliatedServicesContract(unittest.TestCase):
    def test_check_supabase_db_local_or_pg(self):
        res = check_supabase_db()
        self.assertIn(res["status"], ["HEALTHY", "WARNING"])
        self.assertIn("Database:", res["name"])
        self.assertGreaterEqual(res["latency_ms"], 0.0)

    @patch("scripts.check_affiliated_services.BetterStackClient")
    def test_check_betterstack_healthy(self, mock_client_cls):
        mock_instance = MagicMock()
        mock_instance.telemetry_token = "mock-token"
        mock_instance.incidents_token = "mock-token"
        mock_instance.list_sources.return_value = [{"id": "s1"}]
        mock_instance.get_monitor_statuses.return_value = [
            {"id": "m1", "status": "up", "monitor_type": "status"},
            {"id": "hb1", "status": "up", "monitor_type": "heartbeat"},
        ]
        mock_client_cls.return_value = mock_instance

        res = check_betterstack()
        self.assertEqual(res["status"], "HEALTHY")
        self.assertIn("1 Uptime Monitors", res["details"])
        self.assertIn("1 Heartbeats", res["details"])

    @patch("scripts.check_affiliated_services.get_secret")
    def test_check_angel_one_configured(self, mock_secret):
        # 1. With SmartAPI proxy configured
        mock_secret.side_effect = lambda k: "mock_value" if ("ANGEL_ONE" in k or k == "SMARTAPI_PROXY_URL") else ""
        with patch.dict(os.environ, {"SMARTAPI_PROXY_URL": "http://mock-proxy:8888"}):
            res = check_angel_one()
            self.assertEqual(res["status"], "HEALTHY")
            self.assertIn("Selective AWS Proxy Active", res["details"])

        # 2. Direct egress fallback when proxy is unconfigured
        mock_secret.side_effect = lambda k: "mock_value" if "ANGEL_ONE" in k else ""
        with patch.dict(os.environ, {}, clear=True):
            res = check_angel_one()
            self.assertEqual(res["status"], "HEALTHY")
            self.assertIn("Direct Egress", res["details"])

    @patch("scripts.check_affiliated_services.get_secret")
    def test_check_gemini_ai_configured(self, mock_secret):
        mock_secret.side_effect = lambda k: "ai-secret" if k == "GEMINI_API_KEY" else ""
        res = check_gemini_ai()
        self.assertEqual(res["status"], "HEALTHY")
        self.assertIn("Fallback Cascade", res["details"])
        self.assertIn("Batch/Flex 50% Tier", res["details"])

    @patch("scripts.check_affiliated_services.get_secret")
    def test_check_perplexity_sonar_configured(self, mock_secret):
        mock_secret.side_effect = lambda k: "pplx-test-key" if k == "PERPLEXITY_API_KEY" else ""
        res = check_perplexity_sonar()
        self.assertEqual(res["status"], "HEALTHY")
        self.assertIn("Grounding Failover Active", res["details"])

    @patch("scripts.check_affiliated_services.get_secret")
    def test_check_resend_email_configured(self, mock_secret):
        mock_secret.side_effect = lambda k: "re_test_key" if k == "RESEND_API_KEY" else ""
        res = check_resend_email()
        self.assertEqual(res["status"], "HEALTHY")
        self.assertIn("Supabase GoTrue Auth Primary", res["details"])

    @patch("scripts.check_affiliated_services.get_secret")
    def test_check_razorpay_configured(self, mock_secret):
        mock_secret.side_effect = lambda k: "rzp_test_key" if "RAZORPAY" in k else ""
        res = check_razorpay()
        self.assertEqual(res["status"], "HEALTHY")
        self.assertIn("rzp_test", res["details"])


if __name__ == "__main__":
    unittest.main()
