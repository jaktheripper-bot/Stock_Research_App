"""Comprehensive unit and integration test suite for Alternative Real Assets,
SEBI SM REITs, Infrastructure InvITs, and Sovereign Gold Bonds (SGB) Engine.

Validates:
1. SEBI (REIT) (Amendment) Regulations 2024 compliance audit engine:
   - Occupancy >= 95% completed asset threshold for SM REITs
   - NDCF Payout Purity >= 95%
   - LTV cap <= 49%
2. Section 115UA / Finance Act 2023 multi-component tax waterfall simulator
3. SGB secondary market discount, compound YTM, and Section 47(viic) tax parity engine
4. End-to-end FastAPI endpoints (/reits, /api/reits/directory, /api/reits/tax-breakdown, /api/sgb/tranches)
"""

import os
os.environ["TESTING"] = "1"

import unittest
from fastapi.testclient import TestClient
from web.main import app

from core.db.reits import (
    get_all_reits_and_invits,
    get_reit_by_symbol,
    get_all_sgb_tranches,
    get_sgb_by_symbol,
    save_reit_or_invit,
    save_sgb_tranche,
)
from core.analysis.reit_engine import (
    audit_reit_portfolio,
    simulate_reit_tax_waterfall,
)
from core.analysis.sgb_engine import evaluate_sgb_market


class TestReitAndSgbEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    # ==========================================
    # 1. DATABASE ACCESS & RETRIEVAL TESTS
    # ==========================================

    def test_default_reit_and_invit_universe(self):
        """Verifies expanded REIT/InvIT universe contains all 10 offerings with proper classifications."""
        all_assets = get_all_reits_and_invits()
        self.assertGreaterEqual(len(all_assets), 10)

        structures = {r["structure_type"] for r in all_assets}
        self.assertIn("MAINBOARD_REIT", structures)
        self.assertIn("INVIT", structures)
        self.assertIn("SM_REIT", structures)

        # Lookup by symbol
        embassy = get_reit_by_symbol("EMBASSY")
        self.assertIsNotNone(embassy)
        self.assertEqual(embassy["name"], "Embassy Office Parks REIT")
        self.assertEqual(embassy["structure_type"], "MAINBOARD_REIT")

        sm_reit = get_reit_by_symbol("SMREIT_BLR_01")
        self.assertIsNotNone(sm_reit)
        self.assertEqual(sm_reit["structure_type"], "SM_REIT")
        self.assertGreaterEqual(sm_reit["occupancy_pct"], 95.0)

        # Non-existent asset
        self.assertIsNone(get_reit_by_symbol("NON_EXISTENT_ASSET"))

    def test_default_sgb_tranches_universe(self):
        """Verifies expanded SGB universe contains active secondary tranches (2025 to 2032 maturities)."""
        tranches = get_all_sgb_tranches()
        self.assertGreaterEqual(len(tranches), 10)

        # Verify key tranches exist
        sgb_nov25 = get_sgb_by_symbol("SGBNOV25")
        self.assertIsNotNone(sgb_nov25)
        self.assertEqual(sgb_nov25["annual_coupon_rate"], 2.50)

        sgb_feb32 = get_sgb_by_symbol("SGBFEB32")
        self.assertIsNotNone(sgb_feb32)
        self.assertEqual(sgb_feb32["annual_coupon_rate"], 2.50)

        # Non-existent tranche
        self.assertIsNone(get_sgb_by_symbol("SGB_FAKE_99"))

    # ==========================================
    # 2. REIT ENGINE & SEBI 2024 COMPLIANCE TESTS
    # ==========================================

    def test_reit_portfolio_audit_metrics(self):
        """Validates portfolio analytics, averages, and group decomposition."""
        audit = audit_reit_portfolio()
        self.assertIn("total_tracked", audit)
        self.assertGreaterEqual(audit["total_tracked"], 10)
        self.assertGreater(audit["average_distribution_yield_pct"], 0.0)
        self.assertGreater(audit["average_occupancy_pct"], 80.0)
        self.assertGreater(audit["average_ltv_pct"], 10.0)
        self.assertIn("macro_observations", audit)
        self.assertGreaterEqual(len(audit["macro_observations"]), 3)

        # Decomposed asset categories
        self.assertGreaterEqual(len(audit["mainboard_reits"]), 4)
        self.assertGreaterEqual(len(audit["invits"]), 4)
        self.assertGreaterEqual(len(audit["sm_reits"]), 2)

    def test_reit_filtering_by_structure(self):
        """Validates structure filtering on audit_reit_portfolio."""
        sm_audit = audit_reit_portfolio(structure_type="SM_REIT")
        for item in sm_audit["items"]:
            self.assertEqual(item["structure_type"], "SM_REIT")

        invit_audit = audit_reit_portfolio(structure_type="INVIT")
        for item in invit_audit["items"]:
            self.assertEqual(item["structure_type"], "INVIT")

    def test_sebi_sm_reit_compliance_flagging(self):
        """Verifies SEBI 2024 compliance guardrails flag violations (occupancy < 95% or LTV > 49%)."""
        # Inject an artificial non-compliant SM REIT to verify auditor detection
        bad_sm_reit = {
            "symbol": "SMREIT_BAD_TEST",
            "name": "Non-Compliant Under-Construction SM REIT",
            "structure_type": "SM_REIT",
            "current_price": 500.0,
            "nav_per_unit": 500.0,
            "discount_to_nav_pct": 0.0,
            "distribution_yield_pct": 6.5,
            "occupancy_pct": 82.0,  # Breaches 95% threshold!
            "ndcf_payout_purity_pct": 88.0,  # Breaches 95% threshold!
            "ltv_ratio_pct": 55.0,  # Breaches 49% statutory cap!
            "wale_years": 3.0,
            "sponsor_holding_pct": 2.0,
            "sebi_compliant": False,
            "details_json": "{}"
        }
        save_reit_or_invit(bad_sm_reit)

        audit = audit_reit_portfolio(structure_type="SM_REIT")
        issues = audit["flagged_issues"]
        # Must flag occupancy breach, LTV breach, and NDCF breach
        self.assertTrue(any("SMREIT_BAD_TEST: SM REIT occupancy" in iss for iss in issues))
        self.assertTrue(any("SMREIT_BAD_TEST: Leverage LTV" in iss for iss in issues))
        self.assertTrue(any("SMREIT_BAD_TEST: NDCF upstreaming purity" in iss for iss in issues))

    # ==========================================
    # 3. SECTION 115UA TAX WATERFALL TESTS
    # ==========================================

    def test_reit_tax_waterfall_simulation(self):
        """Validates Section 115UA post-tax waterfall calculation across multiple investor slabs."""
        # Non-existent symbol returns error
        err_res = simulate_reit_tax_waterfall("UNKNOWN_ASSET", 30.0)
        self.assertIn("error", err_res)

        # Embassy 30% slab
        sim_30 = simulate_reit_tax_waterfall("EMBASSY", tax_slab_pct=30.0)
        self.assertEqual(sim_30["symbol"], "EMBASSY")
        self.assertEqual(sim_30["gross_distribution_yield_pct"], 7.15)
        self.assertEqual(sim_30["investor_tax_slab_pct"], 30.0)
        self.assertGreater(sim_30["net_post_tax_yield_pct"], 0.0)
        self.assertLess(sim_30["net_post_tax_yield_pct"], sim_30["gross_distribution_yield_pct"])
        self.assertGreater(sim_30["tax_drag_bps"], 0.0)
        self.assertIn("tax_breakdown_weights", sim_30)
        self.assertEqual(sim_30["tax_breakdown_weights"]["dividend_pct"], 38.0)
        self.assertEqual(sim_30["tax_breakdown_weights"]["return_of_capital_pct"], 28.0)

        # Embassy 0% slab (tax drag must be 0)
        sim_0 = simulate_reit_tax_waterfall("EMBASSY", tax_slab_pct=0.0)
        self.assertEqual(sim_0["net_post_tax_yield_pct"], sim_0["gross_distribution_yield_pct"])
        self.assertEqual(sim_0["tax_drag_bps"], 0.0)

        # Higher slab produces higher tax drag
        sim_39 = simulate_reit_tax_waterfall("EMBASSY", tax_slab_pct=39.0)
        self.assertGreater(sim_39["tax_drag_bps"], sim_30["tax_drag_bps"])
        self.assertLess(sim_39["net_post_tax_yield_pct"], sim_30["net_post_tax_yield_pct"])

    # ==========================================
    # 4. SGB ENGINE & TAX PARITY TESTS
    # ==========================================

    def test_sgb_market_evaluation(self):
        """Validates SGB secondary discount analysis and comparative matrix."""
        sgb_eval = evaluate_sgb_market()
        self.assertIn("total_tranches_tracked", sgb_eval)
        self.assertGreaterEqual(sgb_eval["total_tranches_tracked"], 10)
        self.assertGreater(sgb_eval["average_annualized_ytm_pct"], 6.0)
        self.assertIn("spot_gold_reference_inr", sgb_eval)
        self.assertIsNotNone(sgb_eval["best_yield_tranche"])
        self.assertIsNotNone(sgb_eval["deepest_discount_tranche"])

        # Check institutional comparative matrix (SGB vs ETF vs Physical Gold)
        comparison = sgb_eval["asset_comparison"]
        self.assertEqual(len(comparison), 4)
        dimensions = [c["dimension"] for c in comparison]
        self.assertIn("Acquisition Friction / Entry Pricing", dimensions)
        self.assertIn("Capital Gains Taxation at Redemption", dimensions)

        # Verify Section 47(viic) citation
        self.assertIn("Section 47(viic)", sgb_eval["tax_statute_citation"])
        self.assertIn("exempt from capital gains tax", sgb_eval["tax_statute_citation"])

    # ==========================================
    # 5. FASTAPI WEB & API ROUTE INTEGRATION TESTS
    # ==========================================

    def test_reits_web_page_rendering(self):
        """Verifies GET /reits renders institutional terminal HTML template successfully."""
        resp = self.client.get("/reits")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # Verify key terminal sections
        self.assertIn("Alternative Real Assets, SM REITs & Sovereign Gold Terminal", html)
        self.assertIn("Structural Comparison Matrix", html)
        self.assertIn("SEBI SM REITs & Mainboard Commercial REITs", html)
        self.assertIn("Infrastructure Investment Trusts (InvITs)", html)
        self.assertIn("Sovereign Gold Bonds (SGB) Secondary Market Discount & Parity Scanner", html)
        self.assertIn("Section 115UA Real Asset Tax Waterfall", html)
        self.assertIn("Section 2(u) of SEBI (Research Analysts) Regulations, 2014", html)

        # Check badge styling and data elements
        self.assertIn("EMBASSY", html)
        self.assertIn("PGINVIT", html)
        self.assertIn("SMREIT_BLR_01", html)
        self.assertIn("SGBFEB32", html)

    def test_reits_web_page_structure_filter(self):
        """Verifies GET /reits?structure=SM_REIT filters the view cleanly."""
        resp = self.client.get("/reits?structure=SM_REIT")
        self.assertEqual(resp.status_code, 200)

    def test_api_reits_directory_endpoint(self):
        """Verifies GET /api/reits/directory returns audited JSON payload."""
        resp = self.client.get("/api/reits/directory")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)
        self.assertIn("average_distribution_yield_pct", data)
        self.assertIn("macro_observations", data)

    def test_api_sgb_tranches_endpoint(self):
        """Verifies GET /api/sgb/tranches returns secondary market audit."""
        resp = self.client.get("/api/sgb/tranches")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("tranches", data)
        self.assertIn("asset_comparison", data)
        self.assertIn("tax_statute_citation", data)

    def test_api_reits_tax_breakdown_endpoint(self):
        """Verifies GET /api/reits/tax-breakdown returns post-tax calculation."""
        resp = self.client.get("/api/reits/tax-breakdown?symbol=EMBASSY&tax_slab=30")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["symbol"], "EMBASSY")
        self.assertEqual(data["investor_tax_slab_pct"], 30.0)
        self.assertIn("net_post_tax_yield_pct", data)
        self.assertIn("tax_drag_bps", data)


if __name__ == "__main__":
    unittest.main()
