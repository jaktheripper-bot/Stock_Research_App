"""Comprehensive test suite for Priority 3, 4, and 5 implementations.

Covers:
- Priority 3: Sovereign Benchmarks, Par Yield Curve, ETF Matrix & Net Real Post-Tax Return Engine
- Priority 4: SM REITs, Mainboard REITs, InvITs Compliance & SGB Parity Engine
- Priority 5: Retail Alternative Yield & Shadow-Banking Diagnostic Radar
- Web UI & API Endpoints for all corresponding modules
"""

import os
os.environ["TESTING"] = "1"

import unittest
from fastapi.testclient import TestClient
from web.main import app

from core.db.sovereign import (
    save_sovereign_benchmark,
    get_sovereign_yield_curve,
    get_sovereign_curve_analytics,
    save_etf_matrix_item,
    get_etf_matrix,
)
from core.analysis.sovereign_engine import evaluate_sovereign_curve
from core.analysis.etf_engine import evaluate_etf_matrix
from core.analysis.tax_calculator import (
    calculate_net_real_return,
    compare_asset_classes_post_tax,
)
from core.db.reits import (
    save_reit_or_invit,
    get_all_reits_and_invits,
    save_sgb_tranche,
    get_all_sgb_tranches,
)
from core.analysis.reit_engine import audit_reit_portfolio
from core.analysis.sgb_engine import evaluate_sgb_market
from core.db.safety_radar import (
    save_alternative_yield_product,
    get_all_safety_radar_products,
)
from core.analysis.safety_radar import audit_alternative_yield_radar


class TestPriorities345(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    # ==========================================
    # PRIORITY 3: SOVEREIGN BENCHMARKS & PAR CURVE
    # ==========================================

    def test_sovereign_benchmarks_and_engine(self):
        # Insert a benchmark
        bench = {
            "tenor_label": "10Y_GSEC",
            "instrument_type": "GSEC",
            "maturity_years": 10.0,
            "cut_off_yield": 7.08,
            "auction_date": "2026-10-01",
            "source": "RBI_AUCTION_CUTOFF"
        }
        res = save_sovereign_benchmark(bench)
        self.assertTrue(res)

        curve = get_sovereign_yield_curve()
        self.assertGreaterEqual(len(curve), 1)

        analytics = get_sovereign_curve_analytics()
        self.assertIn("benchmark_10y_gsec", analytics)
        self.assertIn("term_spread_bps", analytics)

        curve_eval = evaluate_sovereign_curve()
        self.assertIn("curve_points", curve_eval)
        self.assertIn("macro_insights", curve_eval)
        self.assertGreaterEqual(len(curve_eval["macro_insights"]), 1)

    # ==========================================
    # PRIORITY 3: ETF MATRIX & TRACKING ERROR
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
    # PRIORITY 3: NET REAL POST-TAX RETURN ENGINE
    # ==========================================

    def test_tax_calculator_math(self):
        # 1. Bank FD: 7.25% pre-tax, 30% tax rate, 5.0% inflation
        calc_fd = calculate_net_real_return(
            nominal_annual_return_pct=7.25,
            tax_rate_pct=30.0,
            cpi_inflation_pct=5.0
        )
        # post_tax_nominal = 7.25 * (1 - 0.30) = 5.075% -> 5.07%
        # real return = (1 + 0.05075) / (1 + 0.05) - 1 = +0.000714 -> +0.07%
        self.assertAlmostEqual(calc_fd["post_tax_nominal_pct"], 5.07, delta=0.05)
        self.assertAlmostEqual(calc_fd["net_real_return_pct"], 0.07, delta=0.05)
        self.assertIn("capital", calc_fd["purchasing_power_verdict"].lower())

        # 2. Compare multi-asset classes
        asset_comp = compare_asset_classes_post_tax(marginal_tax_slab_pct=30.0, cpi_inflation_pct=5.0)
        self.assertGreaterEqual(len(asset_comp), 6)
        
        # Verify SGB has 0% tax on capital gains and preserves purchasing power
        sgb_entry = next((x for x in asset_comp if "Sovereign Gold" in x["asset_name"]), None)
        self.assertIsNotNone(sgb_entry)
        self.assertIn("Section 47(viic)", sgb_entry["tax_statute_citation"])
        self.assertGreater(sgb_entry["net_real_return_pct"], 3.0)

    # ==========================================
    # PRIORITY 4: SM REITS, REITS, INVITS & SGB
    # ==========================================

    def test_reits_and_sm_reit_compliance(self):
        # Insert a compliant SM REIT
        reit_item = {
            "symbol": "PROPSHARE_PLATINA",
            "name": "PropShare Platina SM REIT",
            "structure_type": "SM_REIT",
            "cmp_inr": 1025.0,
            "nav_per_unit_inr": 1050.0,
            "distribution_yield_pct": 8.75,
            "occupancy_pct": 98.2,
            "ltv_ratio_pct": 21.0,
            "ndcf_payout_purity_pct": 97.0,
            "sponsor_skin_in_game_pct": 5.2,
            "sebi_compliant": True,
            "notes": "Grade A IT Park asset in Bangalore"
        }
        save_reit_or_invit(reit_item)

        reits = get_all_reits_and_invits()
        self.assertGreaterEqual(len(reits), 1)

        portfolio_audit = audit_reit_portfolio()
        self.assertIn("total_tracked", portfolio_audit)
        self.assertIn("compliant_count", portfolio_audit)
        self.assertGreaterEqual(portfolio_audit["total_tracked"], 1)

    def test_sgb_market_analysis(self):
        sgb_item = {
            "symbol": "SGB2028IV",
            "series_name": "SGB 2028-29 Series IV",
            "issue_price_inr": 4807.0,
            "cmp_inr": 7250.0,
            "spot_gold_per_gram": 7520.0,
            "discount_to_spot_pct": -3.59,
            "coupon_rate_pct": 2.50,
            "maturity_date": "2029-03-08",
            "years_to_maturity": 2.42,
            "ytm_annualized_pct": 9.20,
            "secondary_volume_daily": 15000,
            "liquidity_status": "MODERATE_LIQUIDITY"
        }
        save_sgb_tranche(sgb_item)

        tranches = get_all_sgb_tranches()
        self.assertGreaterEqual(len(tranches), 1)

        sgb_market = evaluate_sgb_market()
        self.assertIn("total_tranches_tracked", sgb_market)
        self.assertIn("tax_statute_citation", sgb_market)
        self.assertGreaterEqual(sgb_market["total_tranches_tracked"], 1)

    # ==========================================
    # PRIORITY 5: RETAIL SAFETY RADAR
    # ==========================================

    def test_safety_radar(self):
        # Insert a high risk product
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
            "safety_verdict": "CRITICAL DANGER: High risk of total capital loss upon jeweller default."
        }
        save_alternative_yield_product(high_risk)

        products = get_all_safety_radar_products()
        self.assertGreaterEqual(len(products), 1)

        radar_audit = audit_alternative_yield_radar()
        self.assertIn("total_schemes_audited", radar_audit)
        self.assertIn("extreme_danger_count", radar_audit)
        self.assertGreaterEqual(radar_audit["extreme_danger_count"], 1)

    # ==========================================
    # WEB UI & FASTAPI ROUTES TEST
    # ==========================================

    def test_sovereign_web_routes(self):
        res = self.client.get("/sovereign")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Indian Sovereign Par Yield Curve", res.text)

        api_res = self.client.get("/api/sovereign/curve")
        self.assertEqual(api_res.status_code, 200)
        data = api_res.json()
        self.assertIn("curve_points", data)
        self.assertIn("macro_insights", data)

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

    def test_reit_directory_web_routes(self):
        res = self.client.get("/reits")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Fractional Real Estate, InvITs & Sovereign Gold", res.text)

        api_res_reits = self.client.get("/api/reits/directory")
        self.assertEqual(api_res_reits.status_code, 200)
        self.assertIn("items", api_res_reits.json())

        api_res_sgb = self.client.get("/api/sgb/tranches")
        self.assertEqual(api_res_sgb.status_code, 200)
        self.assertIn("tranches", api_res_sgb.json())

    def test_safety_radar_web_routes(self):
        res = self.client.get("/safety-radar")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Alternative Yield & Shadow-Banking Risk Radar", res.text)

        api_res = self.client.get("/api/safety-radar")
        self.assertEqual(api_res.status_code, 200)
        data = api_res.json()
        self.assertIn("total_schemes_audited", data)
        self.assertIn("all_products", data)


if __name__ == "__main__":
    unittest.main()
