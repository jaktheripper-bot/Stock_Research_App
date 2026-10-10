"""Unit test suite for the Hybrid Sandboxed AI Auditor & Failure Synthesizer.

Verifies:
1. BudgetGuard token and dollar tracking and hard ceiling aborts.
2. SiteMap Zone mapping consistency.
3. Personas execution with mock and sandboxed TestClient.
4. FailureSynthesizer deterministic fallback and artifact generation.
"""

import unittest
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["TESTING"] = "1"
os.environ["ENVIRONMENT"] = "testing"

from fastapi.testclient import TestClient
from web.main import app
from scripts.ai_auditor import (
    BudgetGuard,
    BudgetExceededError,
    SiteZone,
    AnomalyReport,
    FailureSynthesizer,
    RegulatoryBaiter,
    EdgeCaseQuant,
    StateSaboteur,
)


class TestAiAuditorEngine(unittest.TestCase):
    """Test suite for AI Auditor and failure synthesizer mechanics."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_budget_guard_accumulation_and_limits(self):
        """Verifies that BudgetGuard accurately tracks tokens and raises when ceiling is exceeded."""
        guard = BudgetGuard(max_tokens=1000, max_cost_usd=0.10)
        self.assertEqual(guard.tokens_used, 0)
        self.assertEqual(guard.cost_used, 0.0)

        # Record normal usage
        guard.record_usage(prompt_tokens=400, candidate_tokens=100)
        self.assertEqual(guard.tokens_used, 500)
        self.assertGreater(guard.cost_used, 0.0)
        self.assertTrue(guard.can_spend(estimated_tokens=400))

        # Exceed token ceiling
        with self.assertRaises(BudgetExceededError):
            guard.record_usage(prompt_tokens=400, candidate_tokens=200)

    def test_site_zones_coverage(self):
        """Verifies that all 5 site zones are defined and distinct."""
        zones = [
            SiteZone.ZONE_1_EQUITY,
            SiteZone.ZONE_2_MULTI_ASSET,
            SiteZone.ZONE_3_CALCULATORS,
            SiteZone.ZONE_4_FORENSIC_DESK,
            SiteZone.ZONE_5_ADMIN_SECURITY,
        ]
        self.assertEqual(len(set(zones)), 5)
        for z in zones:
            self.assertTrue(z.startswith("Zone "))

    def test_regulatory_baiter_execution(self):
        """Verifies that Regulatory Baiter audits /api/copilot/chat and /contact cleanly."""
        baiter = RegulatoryBaiter(self.client)
        anomalies = baiter.run_probes()
        # Should be empty since our endpoint is now properly deflecting advisory prompts
        self.assertEqual(len(anomalies), 0, f"Unexpected regulatory anomalies detected: {anomalies}")

    def test_edge_case_quant_execution(self):
        """Verifies that Edge-Case Quant runs boundary queries without unhandled 500s."""
        quant = EdgeCaseQuant(self.client)
        anomalies = quant.run_probes()
        self.assertEqual(len(anomalies), 0, f"Unexpected quant anomalies detected: {anomalies}")

    def test_state_saboteur_execution(self):
        """Verifies that State Saboteur confirms authentication and payload boundaries."""
        saboteur = StateSaboteur(self.client)
        anomalies = saboteur.run_probes()
        self.assertEqual(len(anomalies), 0, f"Unexpected security anomalies detected: {anomalies}")

    def test_failure_synthesizer_generates_valid_artifacts(self):
        """Verifies that FailureSynthesizer writes executable unit tests and markdown dossiers."""
        guard = BudgetGuard(max_tokens=10000, max_cost_usd=0.50)
        synthesizer = FailureSynthesizer(guard)

        mock_anomaly = AnomalyReport(
            anomaly_id="ANOM-TEST-UNIT-01",
            zone=SiteZone.ZONE_3_CALCULATORS,
            endpoint="/calculator/tax",
            method="GET",
            persona="Edge-Case Quant",
            probe_description="Test anomaly for synthesizer verification",
            payload={"holding_years": -99},
            status_code=500,
            error_message="Test synthetic 500 failure",
            response_snippet="Traceback: line 1 in tax_test",
            threat_level="HIGH",
            timestamp="2026-10-10T18:00:00Z",
        )

        res = synthesizer.synthesize(mock_anomaly)
        test_file = Path(res["test_file"])
        report_file = Path(res["report_file"])

        try:
            self.assertTrue(test_file.exists(), "Synthesized test file was not created on disk")
            self.assertTrue(report_file.exists(), "Synthesized report file was not created on disk")

            # Check test file content
            with open(test_file, "r", encoding="utf-8") as f:
                code = f.read()
                self.assertIn("class TestRegression_", code)
                self.assertIn("assertNotEqual", code)

            # Check report file content
            with open(report_file, "r", encoding="utf-8") as f:
                report = f.read()
                self.assertIn("AI Auditor Threat Dossier", report)
                self.assertIn("ANOM-TEST-UNIT-01", report)
        finally:
            # Clean up test artifacts
            if test_file.exists():
                test_file.unlink()
            if report_file.exists():
                report_file.unlink()


if __name__ == "__main__":
    unittest.main()
