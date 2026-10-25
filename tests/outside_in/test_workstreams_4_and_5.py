"""
tests/outside_in/test_workstreams_4_and_5.py
=============================================
Outside-In Verification Suite for Batched Workstreams 4 & 5:
- Workstream 4: Commercial Trust, Pricing Transparency & Pre-Flight Credit Assurance
- Workstream 5: Homepage Information Architecture, Trust Promises & Flagship Sample Dossier
"""
import os
os.environ["TESTING"] = "1"
os.environ.setdefault("ADMIN_PASSWORD", "test_admin_pwd_default")

import unittest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from web.main import app


class TestWorkstreams4And5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.db import save_report_to_archive
        stock_data = {
            "ticker": "INFY",
            "short_name": "Infosys Ltd",
            "current_price": 1842.50,
            "pe_ratio": "26.5",
            "market_cap": 7500000000000.0,
            "roce": 38.4,
            "debt_to_equity": 0.0,
        }
        save_report_to_archive(
            stock_data=stock_data,
            report_text="""### 7-Pillar Qualitative Health Matrix:
- Moat: Wide
- Balance Sheet: Net Cash
- Capital Allocation: Clean

## Pillar 1: Long-Term Competitive Moat
High free-cash conversion business with net-cash balance sheet.

## Pillar 2: Financial Strength & Solvency
Zero long-term debt and high FCF conversion.
""",
            announcement="BSE statutory quarterly filing verified."
        )
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)
        from core.db.telemetry import purge_test_telemetry
        purge_test_telemetry()

    def test_homepage_split_hero_and_ia(self):
        """WS5: Assert split hero, flagship preview card, and live research sequence."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")

        # 1. Split Hero
        hero_split = soup.find(class_="hero-split-wrap")
        self.assertIsNotNone(hero_split, "Hero split wrap must exist")
        lead_col = soup.find(class_="hero-lead-col")
        self.assertIsNotNone(lead_col, "Hero lead column must exist")
        preview_col = soup.find(class_="hero-preview-col")
        self.assertIsNotNone(preview_col, "Hero preview column must exist")

        # 2. Tagline
        h1 = soup.find("h1", class_="hero-title")
        self.assertIsNotNone(h1)
        self.assertIn("Less noise,", h1.text)
        self.assertIn("more nuance.", h1.text)

        # 3. Flagship Sample Card
        sample_card = soup.find(class_="flagship-sample-card")
        self.assertIsNotNone(sample_card, "Flagship sample card must be rendered in hero")
        self.assertIn("INFY", sample_card.text)
        self.assertIn("38.4%", sample_card.text)
        self.assertIn("0.00x", sample_card.text)
        self.assertIn("Allocator Takeaway", sample_card.text)
        cta = sample_card.find("a", href="/dossier/INFY")
        self.assertIsNotNone(cta, "Sample card must have clickable link to INFY dossier")

        # 4. Live Research Proof Comparison Strip
        strip = soup.find(class_="comparison-strip-wrap")
        self.assertIsNotNone(strip, "Comparison strip must be present on homepage")
        self.assertIn("Always Free to Read", strip.text)
        self.assertIn("Uses 1 Research Credit", strip.text)
        self.assertIn("0 Credits", strip.text)

        # 5. Core Competence Section
        core_comp = soup.find(class_="core-competence-showcase")
        self.assertIsNotNone(core_comp, "Core competence showcase must exist")
        self.assertIn("Four things we promise every reader", core_comp.text)
        self.assertIn("We never tell you to buy or sell", core_comp.text)
        self.assertIn("Statutory Exchange & Registry Ingestion", core_comp.text)
        self.assertIn("Deterministic Financial & Risk Modelling", core_comp.text)

        # 6. Technical Solver Drawer
        drawer = soup.find("details", class_="technical-solver-drawer")
        self.assertIsNotNone(drawer, "Technical solver drawer must exist")
        summary = drawer.find("summary")
        self.assertIn("Deep Technical Architecture & Solvers", summary.text)
        self.assertIn("bisection solver", drawer.text)
        self.assertIn("Section 115UA", drawer.text)

        # 7. Asset Cards 2-Layer Layout
        pillars_grid = soup.find(class_="pillars-grid")
        self.assertIsNotNone(pillars_grid)
        cards = pillars_grid.find_all(class_="pillar-card")
        self.assertEqual(len(cards), 7, "Must render exactly 7 asset class framework cards")
        equities_card = cards[0]
        self.assertIn("See cash flow, debt burden, and valuation floor", equities_card.text)
        self.assertIn("Models: Reverse-DCF • DuPont • ASRI", equities_card.text)

    def test_pricing_page_comparison_and_personas(self):
        """WS4: Assert pricing comparison strip and persona-guided callouts."""
        res = self.client.get("/pricing")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")

        # 1. Comparison Strip
        strip = soup.find(class_="comparison-strip-wrap")
        self.assertIsNotNone(strip, "Pricing page must render comparison strip")
        self.assertIn("Always Free to Read", strip.text)
        self.assertIn("Uses 1 Research Credit", strip.text)
        self.assertIn("Atomic Refund Guarantee", strip.text)

        # 2. Persona Callout Pills
        pills = soup.find_all(class_="persona-callout-pill")
        self.assertEqual(len(pills), 4, "Each of the 4 plans must have a persona callout pill")
        self.assertIn("Evaluating a single stock", pills[0].text)
        self.assertIn("Comparing a stock against its two closest", pills[1].text)
        self.assertIn("Full portfolio health check", pills[2].text)
        self.assertIn("Full-time family offices", pills[3].text)

    def test_dossier_comparison_strip(self):
        """WS4: Assert dossier synthesis paywall card includes comparison strip."""
        res = self.client.get("/dossier/INFY")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")

        strip = soup.find(class_="comparison-strip-wrap")
        self.assertIsNotNone(strip, "Dossier page must include comparison strip in deep-dive section")
        self.assertIn("Always Free (0 Credits)", strip.text)
        self.assertIn("Uses 1 Research Credit", strip.text)

    def test_preflight_credit_modal_contract(self):
        """WS4: Assert preflight credit modal structure and client DOM contracts."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")

        modal = soup.find(id="preflightCreditModal")
        self.assertIsNotNone(modal, "#preflightCreditModal must be present in base template")
        self.assertIsNotNone(modal.find(id="preflightModalTitle"))
        self.assertIsNotNone(modal.find(id="preflightModalActionDesc"))
        self.assertIsNotNone(modal.find(id="preflightCurrentBalance"))
        self.assertIsNotNone(modal.find(id="preflightCost"))
        self.assertIsNotNone(modal.find(id="preflightRemainingBalance"))
        self.assertIsNotNone(modal.find(id="preflightConfirmBtn"))
        self.assertIsNotNone(modal.find(id="preflightErrorBox"))
        self.assertIn("Atomic Refund Guarantee", modal.text)

    def test_zero_hallucination_and_entity_hygiene(self):
        """Ensure no unregistered company labels, contact emails/phones, or personal names exist."""
        for path in ["/", "/pricing", "/dossier/INFY"]:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200)
            self.assertNotIn("Lyndon Pinto", res.text)
            self.assertNotIn("Private Limited", res.text)
            self.assertNotIn("Pvt Ltd", res.text)
            self.assertNotIn("+91", res.text)
            self.assertNotIn("@moatnomics.com", res.text)


if __name__ == "__main__":
    unittest.main()
