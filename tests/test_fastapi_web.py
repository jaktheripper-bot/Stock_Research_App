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

    def test_legal_policy_routes(self):
        from web.legal_content import POLICIES
        for slug in POLICIES.keys():
            res = self.client.get(f"/{slug}")
            self.assertEqual(res.status_code, 200, f"Policy route /{slug} failed")

if __name__ == "__main__":
    unittest.main()
