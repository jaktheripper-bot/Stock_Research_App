"""Comprehensive Unit and Integration Test Suite for Alternative Real Assets,
SEBI SM REITs, Infrastructure InvITs, Sovereign Gold Bonds (SGB), National ETF Matrix,
Net Real Post-Tax Calculator, and Alternative Yield Safety Radar.

Validates:
1. SEBI (REIT) (Amendment) Regulations 2024 compliance audit engine (occupancy, NDCF, LTV cap).
2. Section 115UA / Finance Act 2023 multi-component tax waterfall simulator.
3. SGB secondary market discount, compound YTM, and Section 47(viic) tax parity engine.
4. National ETF Performance & Liquidity Matrix and tracking error calculations.
5. Net Real Post-Tax Return Engine across asset classes and inflation regimes.
6. Alternative Yield & Shadow-Banking Diagnostic Radar for retail capital preservation.
7. Full web UI and REST API endpoints for all corresponding modules.
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
from core.analysis.sm_reit_invit_engine import (
    audit_reit_portfolio,
    simulate_reit_tax_waterfall,
)
from core.analysis.sgb_engine import evaluate_sgb_market
from core.db.sovereign import (
    save_sovereign_benchmark,
    get_sovereign_yield_curve,
    get_sovereign_curve_analytics,
    save_etf_matrix_item,
    get_etf_matrix,
)
from core.analysis.sovereign_engine import evaluate_sovereign_curve
from core.analysis.etf_matrix_engine import evaluate_etf_matrix
from core.analysis.net_real_tax_calculator import (
    calculate_net_real_return,
    compare_asset_classes_post_tax,
)
from core.db.safety_radar import (
    save_alternative_yield_product,
    get_all_safety_radar_products,
)
from core.analysis.retail_safety_radar import audit_alternative_yield_radar


class TestRealAssetsAndRadarSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    # ==========================================
    # 1. REIT & INVIT REPOSITORY & COMPLIANCE
    # ==========================================

    def test_default_reit_and_invit_universe(self):
        """Verifies expanded REIT/InvIT universe contains all 10 offerings with proper classifications."""
        all_assets = get_all_reits_and_invits()
        self.assertGreaterEqual(len(all_assets), 10)

        structures = {r["structure_type"] for r in all_assets}
        self.assertIn("MAINBOARD_REIT", structures)
        self.assertIn("INVIT", structures)
        self.assertIn("SM_REIT", structures)

        embassy = get_reit_by_symbol("EMBASSY")
        self.assertIsNotNone(embassy)
        self.assertEqual(embassy["name"], "Embassy Office Parks REIT")
        self.assertEqual(embassy["structure_type"], "MAINBOARD_REIT")

        sm_reit = get_reit_by_symbol("SMREIT_BLR_01")
        self.assertIsNotNone(sm_reit)
        self.assertEqual(sm_reit["structure_type"], "SM_REIT")
        self.assertGreaterEqual(sm_reit["occupancy_pct"], 95.0)

        self.assertIsNone(get_reit_by_symbol("NON_EXISTENT_ASSET"))

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
        bad_sm_reit = {
            "symbol": "SMREIT_BAD_TEST",
            "name": "Non-Compliant Under-Construction SM REIT",
            "structure_type": "SM_REIT",
            "current_price": 500.0,
            "nav_per_unit": 500.0,
            "discount_to_nav_pct": 0.0,
            "distribution_yield_pct": 6.5,
            "occupancy_pct": 82.0,
            "ndcf_payout_purity_pct": 88.0,
            "ltv_ratio_pct": 55.0,
            "wale_years": 3.0,
            "sponsor_holding_pct": 2.0,
            "sebi_compliant": False,
            "details_json": "{}"
        }
        save_reit_or_invit(bad_sm_reit)

        audit = audit_reit_portfolio(structure_type="SM_REIT")
        issues = audit["flagged_issues"]
        self.assertTrue(any("SMREIT_BAD_TEST: SM REIT occupancy" in iss for iss in issues))
        self.assertTrue(any("SMREIT_BAD_TEST: Leverage LTV" in iss for iss in issues))
        self.assertTrue(any("SMREIT_BAD_TEST: NDCF upstreaming purity" in iss for iss in issues))

    def test_reit_tax_waterfall_simulation(self):
        """Validates Section 115UA post-tax waterfall calculation across multiple investor slabs."""
        err_res = simulate_reit_tax_waterfall("UNKNOWN_ASSET", 30.0)
        self.assertIn("error", err_res)

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

        sim_0 = simulate_reit_tax_waterfall("EMBASSY", tax_slab_pct=0.0)
        self.assertEqual(sim_0["net_post_tax_yield_pct"], sim_0["gross_distribution_yield_pct"])
        self.assertEqual(sim_0["tax_drag_bps"], 0.0)

        sim_39 = simulate_reit_tax_waterfall("EMBASSY", tax_slab_pct=39.0)
        self.assertGreater(sim_39["tax_drag_bps"], sim_30["tax_drag_bps"])
        self.assertLess(sim_39["net_post_tax_yield_pct"], sim_30["net_post_tax_yield_pct"])

    # ==========================================
    # 2. SGB TRANCHES & TAX PARITY ENGINE
    # ==========================================

    def test_default_sgb_tranches_universe(self):
        """Verifies expanded SGB universe contains all 35+ active secondary tranches (2025 to 2032 maturities)."""
        tranches = get_all_sgb_tranches()
        self.assertGreaterEqual(len(tranches), 35)

        sgb_nov25 = get_sgb_by_symbol("SGBNOV25")
        self.assertIsNotNone(sgb_nov25)
        self.assertEqual(sgb_nov25["annual_coupon_rate"], 2.50)

        sgb_feb32 = get_sgb_by_symbol("SGBFEB32")
        self.assertIsNotNone(sgb_feb32)
        self.assertEqual(sgb_feb32["annual_coupon_rate"], 2.50)

        self.assertIsNone(get_sgb_by_symbol("SGB_FAKE_99"))

    def test_sgb_market_evaluation(self):
        """Validates SGB secondary discount analysis and comparative matrix."""
        sgb_eval = evaluate_sgb_market()
        self.assertIn("total_tranches_tracked", sgb_eval)
        self.assertGreaterEqual(sgb_eval["total_tranches_tracked"], 35)
        self.assertGreater(sgb_eval["average_annualized_ytm_pct"], 6.0)
        self.assertIn("spot_gold_reference_inr", sgb_eval)
        self.assertIsNotNone(sgb_eval["best_yield_tranche"])
        self.assertIsNotNone(sgb_eval["deepest_discount_tranche"])

        comparison = sgb_eval["asset_comparison"]
        self.assertEqual(len(comparison), 4)
        dimensions = [c["dimension"] for c in comparison]
        self.assertIn("Acquisition Friction / Entry Pricing", dimensions)
        self.assertIn("Capital Gains Taxation at Redemption", dimensions)

        self.assertIn("Section 47(viic)", sgb_eval["tax_statute_citation"])
        self.assertIn("exempt from capital gains tax", sgb_eval["tax_statute_citation"])

    # ==========================================
    # 3. NATIONAL ETF MATRIX & TRACKING ERROR
    # ==========================================

    def test_etf_matrix_and_engine(self):
        item = {
            "symbol": "NIFTYBEES",
            "name": "Nippon India ETF Nifty 50 BeES",
            "category": "EQUITY_INDEX",
            "benchmark_index": "Nifty 50 TRI",
            "aum_crores": 34500.0,
            "ter_pct": 0.04,
            "tracking_error_pct": 0.03,
            "nav_inr": 268.45,
            "cmp_inr": 268.50,
            "premium_discount_pct": 0.02,
            "avg_daily_volume_shares": 5200000,
            "liquidity_tier": "HIGH_LIQUIDITY",
            "amihud_liquidity_score": 0.0001
        }
        res = save_etf_matrix_item(item)
        self.assertTrue(res)

        etfs = get_etf_matrix()
        self.assertGreaterEqual(len(etfs), 1)

        eval_matrix = evaluate_etf_matrix()
        self.assertIn("total_tracked_etfs", eval_matrix)
        self.assertIn("grouped_by_category", eval_matrix)
        self.assertGreaterEqual(eval_matrix["total_tracked_etfs"], 1)

    # ==========================================
    # 4. NET REAL POST-TAX RETURN ENGINE
    # ==========================================

    def test_tax_calculator_math(self):
        calc_fd = calculate_net_real_return(
            nominal_annual_return_pct=7.25,
            tax_rate_pct=30.0,
            cpi_inflation_pct=5.0
        )
        self.assertAlmostEqual(calc_fd["post_tax_nominal_pct"], 5.07, delta=0.05)
        self.assertAlmostEqual(calc_fd["net_real_return_pct"], 0.07, delta=0.05)
        self.assertIn("capital", calc_fd["purchasing_power_verdict"].lower())

        asset_comp = compare_asset_classes_post_tax(marginal_tax_slab_pct=30.0, cpi_inflation_pct=5.0)
        self.assertGreaterEqual(len(asset_comp), 6)

        sgb_entry = next((x for x in asset_comp if "Sovereign Gold" in x["asset_name"]), None)
        self.assertIsNotNone(sgb_entry)
        self.assertIn("Section 47(viic)", sgb_entry["tax_statute_citation"])
        self.assertGreater(sgb_entry["net_real_return_pct"], 3.0)

    # ==========================================
    # 5. RETAIL ALTERNATIVE YIELD SAFETY RADAR
    # ==========================================

    def test_safety_radar(self):
        from core.db.safety_radar import seed_default_safety_radar_products
        high_risk = {
            "platform_name": "Gullak / SafeGold",
            "product_name": "Gold Yield 16% Leasing",
            "category": "GOLD_LEASING",
            "advertised_yield_pct": 16.0,
            "danger_score": 95,
            "regulatory_status": "UNREGULATED_SHADOW",
            "bankruptcy_remoteness": "NONE_PLATFORM_BALANCE_SHEET",
            "credit_rating": "UNRATED",
            "rbi_warning_ref": "RBI Advisory on Unregulated Gold Yield Schemes (2023)",
            "safety_verdict": "CRITICAL DANGER: High risk of total capital loss upon jeweller default.",
            "safe_alternative_recommendation": "Sovereign Gold Bonds (SGB) or SEBI-regulated Gold ETFs."
        }
        try:
            save_alternative_yield_product(high_risk)

            products = get_all_safety_radar_products()
            self.assertGreaterEqual(len(products), 6)

            radar_audit = audit_alternative_yield_radar()
            self.assertIn("total_schemes_audited", radar_audit)
            self.assertIn("extreme_danger_count", radar_audit)
            self.assertGreaterEqual(radar_audit["extreme_danger_count"], 1)
        finally:
            seed_default_safety_radar_products()

    # ==========================================
    # 6. FASTAPI WEB & REST API ENDPOINTS
    # ==========================================

    def test_reits_web_page_rendering(self):
        """Verifies GET /reits renders institutional terminal HTML template successfully."""
        resp = self.client.get("/reits")
        self.assertEqual(resp.status_code, 200)
        html = resp.text
        self.assertIn("Alternative Real Assets, SM REITs & Sovereign Gold Terminal", html)
        self.assertIn("Structural Comparison Matrix", html)
        self.assertIn("SEBI SM REITs & Mainboard Commercial REITs", html)
        self.assertIn("Infrastructure Investment Trusts (InvITs)", html)
        self.assertIn("Sovereign Gold Bonds (SGB) Secondary Market Discount & Parity Scanner", html)
        self.assertIn("Section 115UA Real Asset Tax Waterfall", html)
        self.assertIn("EMBASSY", html)
        self.assertIn("copilotModalBackdrop", html)
        self.assertIn("Statutory Data Provenance:", html)

    def test_reits_web_page_structure_filter(self):
        resp = self.client.get("/reits?structure=SM_REIT")
        self.assertEqual(resp.status_code, 200)

    def test_api_reits_directory_endpoint(self):
        resp = self.client.get("/api/reits/directory")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)
        self.assertIn("average_distribution_yield_pct", data)

    def test_api_sgb_tranches_endpoint(self):
        resp = self.client.get("/api/sgb/tranches")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("tranches", data)
        self.assertIn("asset_comparison", data)
        self.assertIn("tax_statute_citation", data)

    def test_api_reits_tax_breakdown_endpoint(self):
        resp = self.client.get("/api/reits/tax-breakdown?symbol=EMBASSY&tax_slab=30")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["symbol"], "EMBASSY")
        self.assertEqual(data["investor_tax_slab_pct"], 30.0)
        self.assertIn("net_post_tax_yield_pct", data)
        self.assertIn("tax_drag_bps", data)

    def test_etf_web_routes(self):
        res = self.client.get("/etfs")
        self.assertEqual(res.status_code, 200)
        self.assertIn("National ETF Performance & Liquidity Matrix", res.text)

        api_res = self.client.get("/api/etfs/matrix")
        self.assertEqual(api_res.status_code, 200)
        data = api_res.json()
        self.assertIn("etfs", data)
        self.assertIn("grouped_by_category", data)

    def test_tax_calculator_web_routes(self):
        res = self.client.get("/calculator/tax")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Net Real Post-Tax Return Engine", res.text)

        api_res = self.client.get("/api/calculator/tax-return?nominal_return=7.25&tax_rate=30.0&cpi_inflation=5.0")
        self.assertEqual(api_res.status_code, 200)
        data = api_res.json()
        self.assertIn("net_real_return_pct", data)
        self.assertIn("purchasing_power_verdict", data)

    def test_safety_radar_web_routes(self):
        res = self.client.get("/safety-radar")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Alternative Yield & Shadow-Banking Risk Radar", res.text)

        api_res = self.client.get("/api/safety-radar")
        self.assertEqual(api_res.status_code, 200)
        data = api_res.json()
        self.assertIn("total_schemes_audited", data)
        self.assertIn("all_products", data)

    def test_reit_dossier_web_routes(self):
        """Test individual institutional dossier web pages for Mainboard REITs, SM REITs, and InvITs."""
        for sym in ["EMBASSY", "PROPSHARE", "PGINVIT", "IRBINVIT", "NHIT"]:
            # Baseline free tier view
            resp = self.client.get(f"/reits/{sym}")
            self.assertEqual(resp.status_code, 200, f"Failed for {sym}")
            self.assertIn("Section 115UA Tax Waterfall Simulator", resp.text)
            self.assertIn("NDCF Payout Purity", resp.text)
            self.assertIn("Pillar 1: Tax Architecture", resp.text)
            self.assertIn("Unlock Deep-Dive (1 Credit)", resp.text)
            self.assertIn("Countercase Risk Ledger", resp.text)

            # Unlocked Deep-Dive view (via Pro / credit / preview header)
            resp_unlocked = self.client.get(f"/reits/{sym}", headers={"x-unlock-preview": "1"})
            self.assertEqual(resp_unlocked.status_code, 200)
            self.assertIn("Pillar 4: Countercase", resp_unlocked.text)
            self.assertIn("Unlocked", resp_unlocked.text)

    def test_reit_dossier_legacy_alias_resolution(self):
        """Verify backward-compatible resolution of legacy synthetic symbols to genuine entities."""
        for alias in ["SMREIT_BLR_01", "SMREIT_HYD_02", "IRB_INVIT", "NHAI_INVIT"]:
            resp = self.client.get(f"/reits/{alias}")
            self.assertEqual(resp.status_code, 200, f"Failed alias resolution for {alias}")
            self.assertIn("Section 115UA Tax Waterfall", resp.text)

    def test_reit_dossier_not_found(self):
        """Verify 404 response for invalid REIT symbol."""
        resp = self.client.get("/reits/INVALID_TRUST_XYZ")
        self.assertEqual(resp.status_code, 404)

    def test_reit_detail_sec_115ua_math(self):
        """Verify mathematical integrity of Section 115UA multi-slab calculations and NDCF purity."""
        from core.analysis.sm_reit_invit_engine import get_reit_detail
        detail = get_reit_detail("EMBASSY")
        self.assertIsNotNone(detail)
        reit = detail["reit"]
        tax = detail["tax_waterfall"]
        ndcf = detail["ndcf_audit"]

        # Check distribution percentages sum to ~100%
        total_dist_pct = tax["dividend_pct"] + tax["interest_pct"] + tax["return_of_capital_pct"] + tax["rental_pct"]
        self.assertAlmostEqual(total_dist_pct, 100.0, places=1)

        # Check 5 tax slabs
        slabs = tax["slabs"]
        self.assertEqual(len(slabs), 5)
        slab_0 = slabs[0]
        slab_30 = slabs[3]
        slab_39 = slabs[4]

        # At 0% slab, net yield equals gross yield and tax drag is 0
        self.assertEqual(slab_0["slab_rate_pct"], 0.0)
        self.assertEqual(slab_0["net_post_tax_yield_pct"], reit["distribution_yield_pct"])
        self.assertEqual(slab_0["tax_drag_bps"], 0)

        # At 30% slab, tax drag > 0 and net yield < gross yield
        self.assertGreater(slab_30["tax_drag_bps"], 0)
        self.assertLess(slab_30["net_post_tax_yield_pct"], reit["distribution_yield_pct"])
        self.assertLess(slab_39["net_post_tax_yield_pct"], slab_30["net_post_tax_yield_pct"])

        # Check NDCF compliance
        self.assertGreaterEqual(ndcf["payout_purity_pct"], ndcf["statutory_minimum_pct"])

        # Check 4 inversion failure modes
        self.assertEqual(len(detail["inversion_risks"]), 4)


if __name__ == "__main__":
    unittest.main()

