"""Unit tests for the Google Antigravity Multi-Agent Forensic Audit Module."""

import unittest
from unittest.mock import patch

from core.analysis.multi_agent_audit import (
    tool_get_fundamentals,
    tool_get_bse_disclosures,
    tool_compute_forensic_signals,
    run_deterministic_forensic_fallback,
    ForensicAuditResult,
    ANTIGRAVITY_AVAILABLE
)

MOCK_FUNDAMENTALS = {
    "current_price": 1520.0,
    "market_cap": 620000.0,
    "pe_ratio": 24.5,
    "price_to_book": 7.2,
    "debt_to_equity": 0.08,
    "return_on_equity": 28.5,
    "piotroski_f_score": 8,
    "altman_z_score": 6.5,
    "promoter_pledge_pct": 0.0,
    "promoter_holding_pct": 14.8
}


class TestMultiAgentForensicAudit(unittest.TestCase):
    def test_antigravity_sdk_installation(self):
        """Verifies that the google-antigravity package is installed and importable."""
        self.assertTrue(ANTIGRAVITY_AVAILABLE, "google-antigravity should be installed in the environment.")

    @patch("core.analysis.multi_agent_audit.get_stock_fundamentals", return_value=MOCK_FUNDAMENTALS)
    def test_deterministic_forensic_fallback(self, mock_fund):
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

    @patch("core.analysis.multi_agent_audit.get_stock_fundamentals", return_value=MOCK_FUNDAMENTALS)
    def test_forensic_tools(self, mock_fund):
        """Verifies individual deterministic forensic tools execute properly."""
        tools_fund = tool_get_fundamentals("INFY")
        self.assertIn("ticker", tools_fund)

        disclosures = tool_get_bse_disclosures("INFY")
        self.assertIn("ticker", disclosures)

        signals = tool_compute_forensic_signals("INFY")
        self.assertIn("solvency_posture", signals)


if __name__ == "__main__":
    unittest.main()

