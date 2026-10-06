"""Test suite for Developer API v1 (/api/v1/reports/{ticker}) and Custom Advisory PDF Branding."""

import os
os.environ["TESTING"] = "1"

import unittest
from fastapi.testclient import TestClient
from web.main import app
from core.reporting.pdf import build_pdf_dossier, generate_report_pdf
from core.db import save_report_to_archive

class TestApiV1AndBranding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Seed test report for INFY
        stock_data = {
            "ticker": "INFY",
            "short_name": "Infosys Ltd",
            "current_price": 1550.0,
            "pe_ratio": "25.2",
            "market_cap": 6200000000000.0,
            "scrip_code": "500209",
            "sector": "Information Technology"
        }
        report_text = """### 7-Pillar Qualitative Health Matrix:
- Moat: Strong
- Management: Stable
- Capital Allocation: Clean

## Pillar 1: Long-Term Competitive Moat
Detailed competitive advantage breakdown.

## Pillar 2: Financial Strength & Balance Sheet
Zero long-term debt and high FCF conversion.

## Pillar 3: Corporate Governance & Capital Allocation
Clean historical capital allocation track record.

### Key Fundamental Monitorables
Detailed forensic analysis grounded in bseindia.com filings.
"""
        save_report_to_archive(stock_data=stock_data, report_text=report_text)

    def test_branded_pdf_generation(self):
        """Verify that custom advisory branding is rendered into PDF binary."""
        branding = {
            "firm_name": "Apex Wealth Advisory",
            "advisor_reg_no": "INA000012345",
            "prepared_for": "Family Trust Portfolio",
            "custom_disclaimer": "Strictly confidential - for registered client review only."
        }
        rep_text = "### 7-Pillar Qualitative Health Matrix:\n- Moat: Strong\n\n## Pillar 1: Moat\nClean moat."
        pdf_bytes = generate_report_pdf("INFY", rep_text, branding=branding)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        # PDF magic bytes
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_api_pdf_endpoint_with_branding_params(self):
        """Verify /api/pdf/{ticker} accepts branding query parameters."""
        resp = self.client.get(
            "/api/pdf/INFY",
            params={
                "firm_name": "Zenith Advisory",
                "advisor_reg_no": "INA99998888",
                "prepared_for": "Mr. Sharma",
                "custom_disclaimer": "Client confidential."
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "application/pdf")
        self.assertIn("Zenith_Advisory_INFY_", resp.headers.get("content-disposition", ""))
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_api_v1_get_report_success(self):
        """Verify /api/v1/reports/{ticker} returns structured institutional JSON."""
        resp = self.client.get("/api/v1/reports/INFY")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["version"], "v1")
        self.assertEqual(data["ticker"], "INFY")
        self.assertEqual(data["company_name"], "Infosys Ltd")
        self.assertIn("scrip_code", data)
        self.assertIn("7_pillar_health", data)
        self.assertIn("technical_indicators", data)
        self.assertIn("pead_drift_analysis", data)
        self.assertTrue(data["pead_drift_analysis"]["active"])
        self.assertIn("regulatory_disclaimer", data)
        self.assertEqual(resp.headers.get("cache-control"), "public, max-age=300")

    def test_api_v1_get_report_not_found(self):
        """Verify /api/v1/reports/{ticker} returns 404 for missing ticker."""
        resp = self.client.get("/api/v1/reports/NONEXISTENT_TICKER_99")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json().get("detail", "").lower())

    def test_api_v1_authentication_enforcement(self):
        """Verify /api/v1/reports/{ticker} rejects unauthenticated requests when not in testing bypass."""
        # Temporarily disable TESTING mode to assert auth gate
        os.environ["TESTING"] = "0"
        try:
            # Request without any headers
            resp = self.client.get("/api/v1/reports/INFY")
            self.assertEqual(resp.status_code, 401)
            self.assertIn("Valid API key required", resp.json().get("detail", ""))

            # Request with valid Bearer token format
            resp_auth = self.client.get(
                "/api/v1/reports/INFY",
                headers={"Authorization": "Bearer sr_dev_test_token_12345"}
            )
            self.assertEqual(resp_auth.status_code, 200)
            self.assertTrue(resp_auth.json()["success"])
        finally:
            os.environ["TESTING"] = "1"


if __name__ == "__main__":
    unittest.main()
