"""
Security Integration Test Suite: P2 AI Compute Drain & Paywall Sabotage Remediations.
Empirically verifies:
1. QoS Governor Denial-of-Wallet Shield: Strict per-user and per-IP daily velocity caps
   on live generations (cache misses), with graceful fallback to cached historical data.
2. Server-Side Paywall Redaction: Physical stripping and sanitization of Pillar 3 (Forensic Sieve)
   and Pillar 5 (Multi-Model DCF/Valuation Radar) in JSON endpoints before HTTP dispatch.
"""

import os
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

os.environ["TESTING"] = "1"
os.environ["SECRET_KEY"] = "test_dev_secret_key_fixed_length_32_bytes_ok"

from web.main import app
from web.common import (
    redact_equity_intel_json,
    server_side_paywall_redact,
    _asset_unlocked_for_request,
    _deep_dive_unlocked_for_request,
)
from core.billing.qos_governor import (
    authorize_live_generation,
    record_live_generation,
    is_live_generation_allowed,
    reset_qos_windows_for_test,
    MAX_DAILY_LIVE_GENERATIONS_PER_USER,
    MAX_DAILY_LIVE_GENERATIONS_PER_IP,
)
from core.agents.copilot.forensic_desk import (
    redact_equity_intel_json as fd_redact_equity_intel_json,
    server_side_paywall_redact as fd_server_side_paywall_redact,
)
from core.db.reports import init_db, save_report_to_archive, get_report_by_ticker_sync
from core.analysis.dossier_report_synthesis import generate_stock_report


class TestP2QoSCacheMissAndPaywallRedaction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        reset_qos_windows_for_test()

    def tearDown(self):
        reset_qos_windows_for_test()

    # =========================================================================
    # P2-1: DENIAL OF WALLET VIA CACHE-MISS FLOODING
    # =========================================================================

    def test_daily_live_generation_cap_per_user(self):
        """Verifies that a single user account is capped at MAX_DAILY_LIVE_GENERATIONS_PER_USER."""
        user = "bot_attacker@example.com"
        ip = "10.0.0.1"

        # Under the limit: 25 requests authorized
        for i in range(MAX_DAILY_LIVE_GENERATIONS_PER_USER):
            allowed, reason = authorize_live_generation(user_email=user, client_ip=ip)
            self.assertTrue(allowed, f"Request {i+1} should be authorized, got: {reason}")

        # Limit reached
        self.assertFalse(is_live_generation_allowed(user_email=user, client_ip=ip))
        allowed, reason = authorize_live_generation(user_email=user, client_ip=ip)
        self.assertFalse(allowed)
        self.assertIn("DAILY_USER_LIVE_GEN_CAP_EXCEEDED", reason)

        # A different user from a DIFFERENT IP should still be allowed
        allowed_other, _ = authorize_live_generation(user_email="innocent@example.com", client_ip="192.168.1.50")
        self.assertTrue(allowed_other)

    def test_daily_live_generation_cap_per_ip(self):
        """Verifies that a single IP address is capped at MAX_DAILY_LIVE_GENERATIONS_PER_IP."""
        ip = "198.51.100.99"

        # Generate requests with rotating fake user emails from the same IP
        for i in range(MAX_DAILY_LIVE_GENERATIONS_PER_IP):
            user = f"rotator_{i}@example.com"
            allowed, reason = authorize_live_generation(user_email=user, client_ip=ip)
            self.assertTrue(allowed, f"IP request {i+1} should be authorized, got: {reason}")

        # Limit reached for that IP
        self.assertFalse(is_live_generation_allowed(user_email="fresh_user@example.com", client_ip=ip))
        allowed, reason = authorize_live_generation(user_email="fresh_user@example.com", client_ip=ip)
        self.assertFalse(allowed)
        self.assertIn("DAILY_IP_LIVE_GEN_CAP_EXCEEDED", reason)

    def test_generate_stock_report_falls_back_to_cached_data_on_cap_breach(self):
        """
        Denial-of-Wallet Shield in generate_stock_report:
        Once the live generation velocity limit is reached, generate_stock_report
        must strictly serve cached historical data without calling external LLM APIs.
        """
        ticker = "PENNY1"
        sample_report = (
            "# Research Dossier: PENNY1\n\n"
            "## Pillar 01: Macro & Industry Context\nStable sector trends.\n\n"
            "## Pillar 02: Business Model & Competitive Moat\nNarrow moat franchise.\n\n"
            "## Pillar 03: Accounting Check & Forensic Health\nClean balance sheet.\n\n"
            "## Pillar 04: The Drop Diagnostic\nNo systemic impairment.\n\n"
            "## Pillar 05: Valuation & Reverse DCF\nFair value estimated at 50.\n\n"
            "## Pillar 06: Technical Momentum\nConsolidating above 50-DMA.\n\n"
            "## Pillar 07: ESG Impact Scorecard\nSatisfactory governance.\n\n"
            "### Verified Regulatory Sources\nOfficial BSE filing.\n"
        )
        save_report_to_archive(
            {"ticker": ticker, "company_name": "Penny Stock Ltd", "current_price": 25.0, "market_cap": 50000000},
            sample_report
        )

        # Exhaust live generation cap
        for i in range(MAX_DAILY_LIVE_GENERATIONS_PER_IP):
            record_live_generation(user_email="spammer@example.com", client_ip="127.0.0.1")
        self.assertFalse(is_live_generation_allowed())

        # Calling generate_stock_report must succeed by returning the cached text without error
        with patch("core.analysis.dossier_report_synthesis.stream_stock_report") as mock_stream:
            result = generate_stock_report(ticker)
            # stream_stock_report should NOT be called because it served cached data
            mock_stream.assert_not_called()
            self.assertIn("## Pillar 01", result)
            self.assertIn("PENNY1", result)

    def test_synthesize_endpoint_serves_cached_data_when_daily_cap_exceeded(self):
        """
        POST /api/synthesize:
        When live generation daily cap is hit, but a cached report exists,
        it serves the cached report with already_exists=True and deducts 0 credits.
        """
        ticker = "PENNY2"
        sample_report = (
            "# Research Dossier: PENNY2\n\n"
            "## Pillar 01: Macro\nStable.\n\n"
            "## Pillar 02: Moat\nModerate.\n\n"
            "## Pillar 03: Solvency\nClean.\n\n"
            "## Pillar 04: Diagnostic\nNormal.\n\n"
            "## Pillar 05: Valuation\nFair.\n\n"
            "## Pillar 06: Technicals\nConstructive.\n\n"
            "## Pillar 07: ESG\nCompliant.\n"
        )
        save_report_to_archive(
            {"ticker": ticker, "company_name": "Penny Two Ltd", "current_price": 10.0, "market_cap": 30000000},
            sample_report
        )

        # Exhaust daily cap
        for i in range(MAX_DAILY_LIVE_GENERATIONS_PER_IP):
            record_live_generation(user_email="admin_console", client_ip="testclient")

        with patch("web.routers.dossier._is_admin_authenticated", return_value=True):
            resp = self.client.post(
                "/api/synthesize",
                json={"ticker": ticker, "force_refresh": True},
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertTrue(data.get("already_exists"))
        self.assertIn("Daily live generation velocity cap reached", data["message"])

    # =========================================================================
    # P2-2: SERVER-SIDE PAYWALL REDACTION
    # =========================================================================

    def test_redact_equity_intel_json_utility(self):
        """Verifies that redact_equity_intel_json physically removes premium fields."""
        raw_intel = {
            "ticker": "INFY",
            "composite_score": 85.0,
            "composite_verdict": "QUALITY_FRANCHISE",
            "sector_intelligence": {"score": 80.0, "verdict": "STRONG_RUNNER"},
            "forensic_intelligence": {
                "status": "COMPUTED",
                "score": 90.0,
                "passed_count": 9,
                "total_checks": 10,
                "red_flags": [{"check": "Auditor Resignations", "status": "FLAGGED"}],
                "checks": [{"name": "Cash Flow Ratio", "passed": True}],
                "beneish_m_score": -2.85,
            },
            "valuation_radar": {
                "status": "COMPUTED",
                "current_price": 1850.0,
                "fair_value": 2100.0,
                "margin_of_safety_pct": 13.5,
                "models": {
                    "dcf_model": {"fair_value": 2150.0},
                    "historical_pe_model": {"fair_value": 2050.0},
                    "epv_model": {"fair_value": 1900.0},
                },
                "inputs": {"wacc": 11.0, "terminal_growth": 4.5},
            },
            "varan_delta_packet": {"proprietary_cfo_audit": "Clean"},
            "setu_capital_matrix": {"capital_structure_verdict": "Resilient"},
        }

        # Unlocked -> Exact identity preserved
        unlocked = redact_equity_intel_json(raw_intel, is_unlocked=True)
        self.assertEqual(unlocked["forensic_intelligence"]["status"], "COMPUTED")
        self.assertIsNotNone(unlocked["valuation_radar"]["models"])

        # Locked -> Physically stripped
        locked = redact_equity_intel_json(raw_intel, is_unlocked=False)
        self.assertTrue(locked["deep_dive_locked"])
        self.assertEqual(locked["forensic_intelligence"]["status"], "LOCKED")
        self.assertTrue(locked["forensic_intelligence"]["locked"])
        self.assertEqual(locked["forensic_intelligence"]["passed_count"], 0)
        self.assertEqual(len(locked["forensic_intelligence"]["red_flags"]), 0)
        self.assertNotIn("beneish_m_score", locked["forensic_intelligence"])

        # Valuation models physically set to None
        self.assertEqual(locked["valuation_radar"]["status"], "LOCKED")
        self.assertTrue(locked["valuation_radar"]["locked"])
        self.assertIsNone(locked["valuation_radar"]["fair_value"])
        self.assertIsNone(locked["valuation_radar"]["margin_of_safety_pct"])
        self.assertIsNone(locked["valuation_radar"]["models"])
        self.assertIsNone(locked["valuation_radar"]["inputs"])

        # Varan & Setu packets locked
        self.assertTrue(locked["varan_delta_packet"]["locked"])
        self.assertTrue(locked["setu_capital_matrix"]["locked"])

    def test_api_dossier_intel_endpoint_redacts_for_free_users(self):
        """
        GET /api/dossier/intel/{ticker}:
        Free users inspecting the Network Tab must receive physical server-side redactions,
        with models and forensic checks stripped from the response payload.
        """
        # Unauthenticated / Free user request
        resp = self.client.get("/api/dossier/intel/INFY")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertFalse(data.get("deep_dive_unlocked"))

        intel = data["intelligence"]
        self.assertTrue(intel.get("deep_dive_locked"))
        self.assertEqual(intel["forensic_intelligence"]["status"], "LOCKED")
        self.assertTrue(intel["forensic_intelligence"]["locked"])
        self.assertEqual(len(intel["forensic_intelligence"].get("checks", [])), 0)

        val_radar = intel["valuation_radar"]
        self.assertEqual(val_radar["status"], "LOCKED")
        self.assertTrue(val_radar["locked"])
        self.assertIsNone(val_radar["models"])
        self.assertIsNone(val_radar["inputs"])
        self.assertIsNone(val_radar["fair_value"])

    def test_api_dossier_intel_endpoint_unlocked_for_entitled_session(self):
        """
        GET /api/dossier/intel/{ticker}:
        Entitled users (e.g. testing preview or unlocked) receive the full unredacted payload.
        """
        resp = self.client.get("/api/dossier/intel/INFY", headers={"x-unlock-preview": "1"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertTrue(data.get("deep_dive_unlocked"))

        intel = data["intelligence"]
        self.assertFalse(intel.get("deep_dive_locked", False))
        self.assertNotEqual(intel["forensic_intelligence"]["status"], "LOCKED")
        self.assertFalse(intel["forensic_intelligence"].get("locked", False))

        val_radar = intel["valuation_radar"]
        self.assertNotEqual(val_radar["status"], "LOCKED")
        self.assertFalse(val_radar.get("locked", False))
        self.assertIsNotNone(val_radar["models"])

    def test_forensic_desk_re_exports_and_polymorphic_redaction(self):
        """Verifies core.agents.copilot.forensic_desk exports and server_side_paywall_redact."""
        self.assertTrue(callable(fd_redact_equity_intel_json))
        self.assertTrue(callable(fd_server_side_paywall_redact))

        # Test polymorphic redaction for MUTUAL_FUND
        mf_data = {
            "scheme_name": "Test Fund",
            "weighted_moat_score": 82.5,
            "accounting_risk_index": 12.0,
            "top_risky_holdings": ["RISK1"],
            "headline_score": 75.0,
        }
        redacted_mf = server_side_paywall_redact(mf_data, asset_type="MUTUAL_FUND", is_unlocked=False)
        self.assertTrue(redacted_mf.get("deep_dive_locked"))
        self.assertNotIn("weighted_moat_score", redacted_mf)
        self.assertNotIn("accounting_risk_index", redacted_mf)
        self.assertNotIn("top_risky_holdings", redacted_mf)
        self.assertIn("headline_score", redacted_mf)

    def test_asset_unlocked_for_request_supports_equity_namespace(self):
        """Verifies _asset_unlocked_for_request handles kind='EQUITY' and delegates seamlessly."""
        mock_req = MagicMock()
        mock_req.headers = {"x-unlock-preview": "1"}
        mock_req.query_params = {}
        mock_req.cookies = {}

        self.assertTrue(_asset_unlocked_for_request(mock_req, "EQUITY", "INFY"))
        self.assertTrue(_asset_unlocked_for_request(mock_req, "STOCK", "INFY"))
        self.assertTrue(_asset_unlocked_for_request(mock_req, "", "INFY"))

    def test_expired_pro_subscription_does_not_unlock_deep_dive(self):
        """Expired 30-day Pro passes must revert to per-ticker unlock checks rather than granting lifetime unlocks."""
        from datetime import datetime, timedelta
        from unittest.mock import patch
        from core.db.connection import IST
        from web.common import _deep_dive_unlocked_for_request

        mock_req = MagicMock()
        mock_req.headers = {}
        mock_req.query_params = {}
        mock_req.cookies = {}

        expired_user = {
            "id": "usr_exp_1",
            "subscription_tier": "pro_monthly",
            "subscription_expires_at": (datetime.now(IST) - timedelta(days=2)).isoformat(),
        }
        active_user = {
            "id": "usr_act_1",
            "subscription_tier": "pro_monthly",
            "subscription_expires_at": (datetime.now(IST) + timedelta(days=15)).isoformat(),
        }

        with patch("web.main._get_current_web_user", return_value=expired_user), \
             patch("web.main.is_ticker_unlocked_for_user", return_value=False):
            self.assertFalse(_deep_dive_unlocked_for_request(mock_req, "INFY"))
            self.assertFalse(_asset_unlocked_for_request(mock_req, "MUTUAL_FUND", "122639"))

        with patch("web.main._get_current_web_user", return_value=active_user), \
             patch("web.main.is_ticker_unlocked_for_user", return_value=False):
            self.assertTrue(_deep_dive_unlocked_for_request(mock_req, "INFY"))
            self.assertTrue(_asset_unlocked_for_request(mock_req, "MUTUAL_FUND", "122639"))


if __name__ == "__main__":
    unittest.main()
