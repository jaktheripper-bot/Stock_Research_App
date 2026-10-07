"""Unit tests for the Google Antigravity Multi-Agent Forensic Audit Module."""

import unittest
from core.analysis.multi_agent_audit import (
    tool_get_fundamentals,
    tool_get_bse_disclosures,
    tool_compute_forensic_signals,
    run_deterministic_forensic_fallback,
    ForensicAuditResult,
    ANTIGRAVITY_AVAILABLE
)


class TestMultiAgentForensicAudit(unittest.TestCase):
    def test_antigravity_sdk_installation(self):
        """Verifies that the google-antigravity package is installed and importable."""
        self.assertTrue(ANTIGRAVITY_AVAILABLE, "google-antigravity should be installed in the environment.")

    def test_deterministic_forensic_fallback(self):
        """Verifies fallback audit output produces required schema and metrics."""
        res = run_deterministic_forensic_fallback("INFY")
        self.assertIsInstance(res, ForensicAuditResult)
        self.assertEqual(res.ticker, "INFY")
        self.assertGreaterEqual(res.forensic_score, 0.0)
        self.assertLessEqual(res.forensic_score, 100.0)
        self.assertIn("accounting_forensics", res.to_dict())
        self.assertIn("governance_scrutiny", res.to_dict())
        self.assertIn("valuation_stress", res.to_dict())
        self.assertIn("Section 2(u)", res.sebi_safe_harbor)

    def test_forensic_tools(self):
        """Verifies individual deterministic forensic tools execute properly."""
        tools_fund = tool_get_fundamentals("INFY")
        self.assertIn("ticker", tools_fund)

        disclosures = tool_get_bse_disclosures("INFY")
        self.assertIn("ticker", disclosures)

        signals = tool_compute_forensic_signals("INFY")
        self.assertIn("solvency_posture", signals)


if __name__ == "__main__":
    unittest.main()
