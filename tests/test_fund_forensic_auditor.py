"""Unit test suite for Mutual Fund 7-Pillar Forensic Look-Through Engine & Daily Auditor."""

import unittest
from fastapi.testclient import TestClient

from core.db.connection import init_db
from core.db.mutual_funds import (
    seed_default_mutual_funds,
    get_active_mutual_funds,
    get_mutual_fund_scheme,
    get_scheme_holdings,
    save_fund_forensic_dossier,
    get_fund_forensic_dossier,
    get_featured_daily_fund_dossier,
    get_next_fund_for_daily_audit
)
from core.analysis.fund_forensic_auditor import (
    compute_fund_forensic_lookthrough,
    parse_stock_report_health_matrix,
    synthesize_fund_forensic_narrative,
    audit_single_fund_daily
)
from web.main import app


class TestFundForensicAuditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_default_mutual_funds()
        cls.client = TestClient(app)

    def test_expanded_universe_seeding(self):
        """Verify the mutual fund universe is expanded to 30+ marquee schemes across top AMCs."""
        funds = get_active_mutual_funds()
        self.assertGreaterEqual(len(funds), 30)
        codes = [f["scheme_code"] for f in funds]
        self.assertIn("PPFAS_FLEXICAP_DIR", codes)
        self.assertIn("HDFC_MIDCAP_DIR", codes)
        self.assertIn("MIRAE_LARGECAP_DIR", codes)
        self.assertIn("HDFC_FLEXICAP_DIR", codes)
        self.assertIn("KOTAK_FLEXICAP_DIR", codes)
        self.assertIn("ICICI_BLUECHIP_DIR", codes)
        self.assertIn("NIPPON_SMALLCAP_DIR", codes)
        self.assertIn("SBI_CONTRA_DIR", codes)
        self.assertIn("QUANT_ELSS_DIR", codes)

    def test_health_matrix_parsing(self):
        """Verify parsing of 7-pillar Health Matrix block in stock research reports."""
        sample_report = """
# INSTITUTIONAL EQUITY RESEARCH: HDFCBANK

### Health Matrix
- Macro: Stable
- Moat: Wide
- Governance: Clean
- Diagnostic: Neutral
- Valuation: Undervalued
- Balance Sheet: Debt-Free
- Capital Allocation: Disciplined

## Pillar 1: Macro-Economic
"""
        matrix = parse_stock_report_health_matrix(sample_report)
        self.assertEqual(matrix["moat"], "Wide")
        self.assertEqual(matrix["governance"], "Clean")
        self.assertEqual(matrix["valuation"], "Undervalued")
        self.assertEqual(matrix["balance_sheet"], "Debt-Free")

    def test_compute_ppfas_lookthrough(self):
        """Verify 7-pillar look-through aggregation metrics for Parag Parikh Flexi Cap Fund."""
        metrics = compute_fund_forensic_lookthrough("PPFAS_FLEXICAP_DIR")
        self.assertEqual(metrics["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertGreaterEqual(metrics["composite_health_score"], 80.0)
        self.assertGreaterEqual(metrics["weighted_moat_score"], 80.0)
        self.assertLessEqual(metrics["accounting_risk_index"], 5.0)
        self.assertGreaterEqual(metrics["active_share_pct"], 60.0)
        self.assertGreater(len(metrics["top_quality_holdings"]), 0)

    def test_dossier_persistence_and_featured_retrieval(self):
        """Verify saving, retrieving, and hero-featured selection of forensic dossiers."""
        mock_dossier = {
            "scheme_code": "PPFAS_FLEXICAP_DIR",
            "dossier_text": "# TEST INSTITUTIONAL DOSSIER\nMandate integrity verified.",
            "composite_health_score": 85.0,
            "weighted_moat_score": 86.5,
            "accounting_risk_index": 0.0,
            "margin_of_safety_pct": 5.2,
            "promoter_pledge_exposure_pct": 0.0,
            "active_share_pct": 68.0,
            "top_risky_holdings": [],
            "top_quality_holdings": [{"name": "HDFC Bank Ltd", "identifier": "HDFCBANK", "weight_pct": 8.4}],
            "audited_by": "Test_Forensic_Auditor"
        }
        saved = save_fund_forensic_dossier(mock_dossier)
        self.assertTrue(saved)

        retrieved = get_fund_forensic_dossier("PPFAS_FLEXICAP_DIR")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertEqual(retrieved["composite_health_score"], 85.0)
        self.assertEqual(retrieved["weighted_moat_score"], 86.5)

        featured = get_featured_daily_fund_dossier()
        self.assertIsNotNone(featured)
        self.assertEqual(featured["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertIn("scheme_name", featured)

    def test_rotation_queue_selection(self):
        """Verify rotation queue picks a fund needing audit or oldest timestamp."""
        next_fund = get_next_fund_for_daily_audit()
        self.assertIsNotNone(next_fund)
        self.assertIn("scheme_code", next_fund)

    def test_web_routes_and_api(self):
        """Verify web routes render the forensic look-through sections and API delivers JSON."""
        # 1. Fund Directory page
        resp = self.client.get("/funds")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Featured Daily Forensic", resp.text)

        # 2. Fund Dossier page
        resp_dos = self.client.get("/funds/PPFAS_FLEXICAP_DIR")
        self.assertEqual(resp_dos.status_code, 200)
        self.assertIn("7-Pillar Equity Look-Through", resp_dos.text)
        self.assertIn("Weighted Moat Index", resp_dos.text)

        # 3. API endpoint
        resp_api = self.client.get("/api/funds/dossier/PPFAS_FLEXICAP_DIR")
        self.assertEqual(resp_api.status_code, 200)
        data = resp_api.json()
        self.assertEqual(data["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertIn("weighted_moat_score", data)
        self.assertIn("accounting_risk_index", data)


if __name__ == "__main__":
    unittest.main()
