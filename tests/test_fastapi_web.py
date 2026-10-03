"""Test suite for FastAPI web portal routes, dossier rendering, and momentum charting."""

import unittest
from fastapi.testclient import TestClient
from web.main import app

class TestFastAPIWebPortal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_home_page(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Institutional Equity Research Engine", res.text)
        self.assertIn("ZERO-HALLUCINATION DATA INTEGRITY", res.text)

    def test_pricing_page(self):
        res = self.client.get("/pricing")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Single Research Pass", res.text)
        self.assertIn("₹299", res.text)

    def test_peer_comparison_page(self):
        res = self.client.get("/compare?a=INFY&b=TCS")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Cross-Company Peer Comparator", res.text)
        self.assertIn("INFY", res.text)
        self.assertIn("TCS", res.text)

    def test_dossier_infy_rendering_and_chart(self):
        res = self.client.get("/dossier/INFY")
        self.assertEqual(res.status_code, 200)
        html = res.text

        # 1. 7-pillar qualitative posture badges are present at top
        self.assertIn("7-Pillar Qualitative Health Matrix:", html)
        self.assertIn("Moat:", html)

        # 2. Redundant raw markdown bullet list is stripped from prose body
        self.assertNotIn("<li>Macro: Headwinds</li>", html)

        # 3. 6-Month Momentum & 50-DMA chart is rendered
        self.assertIn('id="momentumChart"', html)
        self.assertIn("chart.umd.min.js", html)
        self.assertIn("6-Month Price Momentum & 50-DMA Trendline", html)

    def test_discovery_page(self):
        res = self.client.get("/discovery")
        self.assertEqual(res.status_code, 200)
        self.assertIn("The Morning Discovery Reel", res.text)
        self.assertIn("RIAs & PMS SURVEILLANCE", res.text)
        self.assertIn("SEBI Non-Advisory Safe Harbor Compliance", res.text)

    def test_discovery_db_repository(self):
        from core.db.discovery import save_discovery_reel, get_active_discovery_reel, get_available_discovery_editions
        test_items = [
            {
                "ticker": "TESTCORP",
                "company_name": "Test Diagnostics Corp",
                "sector": "Specialty Chemicals",
                "market_cap_tier": "Small-Cap",
                "current_price": 540.0,
                "pe_ratio": "18.5",
                "roce_pct": 24.5,
                "debt_to_equity": 0.05,
                "sales_growth_3y": 20.0,
                "ria_thesis": "Solid compounding profile under institutional radar.",
                "catalyst_headline": "BSE Announcement: Capacity expansion.",
                "key_metrics": {"roce": "24.5%", "d_e": "0.05"}
            }
        ]
        saved = save_discovery_reel(test_items, edition_date="2026-10-03")
        self.assertGreaterEqual(saved, 1)

        active = get_active_discovery_reel("2026-10-03")
        self.assertTrue(any(item["ticker"] == "TESTCORP" for item in active))

        editions = get_available_discovery_editions()
        self.assertIn("2026-10-03", editions)

    def test_legal_policy_routes(self):
        from web.legal_content import POLICIES
        for slug in POLICIES.keys():
            res = self.client.get(f"/{slug}")
            self.assertEqual(res.status_code, 200, f"Policy route /{slug} failed")

    def test_admin_run_discovery_api(self):
        from unittest.mock import patch
        with patch("scripts.run_discovery_worker.run_discovery_pipeline", return_value=True):
            res = self.client.post("/api/admin/run-discovery?count=10")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data.get("status"), "initiated")


if __name__ == "__main__":
    unittest.main()

