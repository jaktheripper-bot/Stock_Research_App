"""
Unit and Integration Tests for Multi-Asset Opportunity Terminal & Arbitrage Scanner.

Tests:
1. calculate_tax_waterfall across statutory regimes (Sec 47(viic), Sec 115UA, Sec 50AA, Sec 112A).
2. assign_tenure_bucket categorization.
3. get_normalized_opportunity_universe cross-asset aggregation and persona filtering.
4. get_heatmap_matrix 2D matrix structure.
5. get_arbitrage_comparison side-by-side scorecard generation.
6. FastAPI web endpoints:
   - GET /opportunities (HTML)
   - GET /api/opportunities/universe (JSON)
   - GET /api/opportunities/heatmap (JSON)
   - POST /api/opportunities/arbitrage (JSON)
"""

import os
import unittest
from fastapi.testclient import TestClient

# Ensure test DB isolation
os.environ["TESTING"] = "1"

from web.main import app
from core.analysis.opportunity_terminal import (
    calculate_tax_waterfall,
    assign_tenure_bucket,
    get_normalized_opportunity_universe,
    get_heatmap_matrix,
    get_arbitrage_comparison,
    BENCHMARK_10Y_GSEC_YIELD
)


class TestOpportunityTerminalEngine(unittest.TestCase):
    """Unit tests for the financial normalization and taxation engine."""

    def test_sgb_tax_waterfall_section_47_viic(self):
        """Verify SGB capital gains are 100% tax-free under Sec 47(viic) with only coupon taxed."""
        # 8.0% total YTM on SGB with 2.50% coupon at 30% tax slab
        # Coupon taxed: 2.50 * 0.70 = 1.75%
        # Capital appreciation: 8.0 - 2.5 = 5.50% (tax-free)
        # Expected Net: 5.50 + 1.75 = 7.25%
        res = calculate_tax_waterfall(8.0, "SGB", tax_slab=30.0, details={"coupon_rate_pct": 2.50})
        self.assertEqual(res["net_yield_pct"], 7.25)
        self.assertIn("Sec 47(viic)", res["tax_statute"])
        self.assertLess(res["effective_tax_rate_pct"], 15.0)

    def test_reit_tax_waterfall_section_115_ua(self):
        """Verify REIT/InvIT distribution split under Section 115UA pass-through rules."""
        # 8.0% distribution yield at 30% slab
        # 40% Interest = 3.2% * 0.70 = 2.24%
        # 35% Dividend = 2.8% (exempt)
        # 25% RoC = 2.0% (tax-free capital reduction)
        # Total Net = 2.24 + 2.80 + 2.00 = 7.04%
        res = calculate_tax_waterfall(8.0, "REIT", tax_slab=30.0)
        self.assertEqual(res["net_yield_pct"], 7.04)
        self.assertIn("Sec 115UA", res["tax_statute"])

    def test_corporate_debt_marginal_slab_tax_sec_50_aa(self):
        """Verify standard corporate debt and SDIs are taxed at marginal slab rates."""
        # 10.0% YTM at 30% tax slab -> 7.0% net
        res = calculate_tax_waterfall(10.0, "BOND", tax_slab=30.0)
        self.assertEqual(res["net_yield_pct"], 7.0)
        self.assertEqual(res["effective_tax_rate_pct"], 30.0)
        self.assertIn("Sec 50AA", res["tax_statute"])

        # At 39% HNI surcharge slab -> 6.1% net
        res_hni = calculate_tax_waterfall(10.0, "BOND", tax_slab=39.0)
        self.assertEqual(res_hni["net_yield_pct"], 6.1)

    def test_corporate_debt_10_pct_tax_slab(self):
        """Verify 10% tax slab under New Tax Regime applies correctly."""
        res_10 = calculate_tax_waterfall(10.0, "BOND", tax_slab=10.0)
        self.assertEqual(res_10["net_yield_pct"], 9.0)
        self.assertEqual(res_10["effective_tax_rate_pct"], 10.0)

    def test_equity_long_term_capital_gains_sec_112_a(self):
        """Verify equity and equity mutual funds are taxed at flat 12.5% LTCG."""
        # 14.0% return at 12.5% LTCG -> 12.25% net
        res = calculate_tax_waterfall(14.0, "EQUITY", tax_slab=30.0)
        self.assertEqual(res["net_yield_pct"], 12.25)
        self.assertEqual(res["effective_tax_rate_pct"], 12.5)
        self.assertIn("Sec 112A", res["tax_statute"])

    def test_zero_gross_yield_and_zero_tax_slab(self):
        """Verify boundary cases for 0% return and 0% tax bracket."""
        res_zero = calculate_tax_waterfall(0.0, "BOND", tax_slab=30.0)
        self.assertEqual(res_zero["net_yield_pct"], 0.0)

        res_exempt = calculate_tax_waterfall(8.0, "BOND", tax_slab=0.0)
        self.assertEqual(res_exempt["net_yield_pct"], 8.0)
        self.assertEqual(res_exempt["tax_drag_pct"], 0.0)

    def test_assign_tenure_bucket(self):
        """Verify tenure bucket assignment boundaries."""
        self.assertEqual(assign_tenure_bucket(0.5), "<1Y")
        self.assertEqual(assign_tenure_bucket(1.0), "<1Y")
        self.assertEqual(assign_tenure_bucket(2.5), "1-3Y")
        self.assertEqual(assign_tenure_bucket(3.0), "1-3Y")
        self.assertEqual(assign_tenure_bucket(4.5), "3-5Y")
        self.assertEqual(assign_tenure_bucket(7.0), "5-10Y")
        self.assertEqual(assign_tenure_bucket(15.0), "10Y+")

    def test_get_normalized_opportunity_universe(self):
        """Verify universal aggregation across all 6 asset categories."""
        universe = get_normalized_opportunity_universe(tax_slab=30.0, cpi_inflation=4.5)
        self.assertGreater(len(universe), 20)

        # Check required schema keys on each item
        first = universe[0]
        required_keys = [
            "id", "symbol", "name", "asset_class", "category_label",
            "gross_yield_pct", "net_yield_pct", "real_yield_pct",
            "spread_vs_10y_gsec_bps", "seniority_tier", "seniority_rank",
            "macaulay_duration_years", "tenure_bucket", "min_ticket_inr",
            "liquidity_tier", "tax_statute", "recovery_recourse",
            "primary_failure_mode", "detail_url"
        ]
        for k in required_keys:
            self.assertIn(k, first, f"Missing key '{k}' in OpportunityItem")

        # Verify items are sorted descending by net_yield_pct
        for i in range(len(universe) - 1):
            self.assertGreaterEqual(universe[i]["net_yield_pct"], universe[i+1]["net_yield_pct"])

    def test_persona_filtering(self):
        """Verify persona playbooks and Phase 3 scenario aliases correctly isolate matching opportunities."""
        preservation = get_normalized_opportunity_universe(persona_filter="capital_preservation")
        self.assertGreater(len(preservation), 0)
        for item in preservation:
            self.assertIn("capital_preservation", item.get("persona_tags", []))
            self.assertGreaterEqual(item.get("real_yield_pct", 0), 0)

        cashflow = get_normalized_opportunity_universe(persona_filter="maximum_cashflow")
        self.assertGreater(len(cashflow), 0)
        for item in cashflow:
            self.assertIn("quarterly_cashflow", item.get("persona_tags", []))

        upside = get_normalized_opportunity_universe(persona_filter="asymmetric_upside")
        self.assertGreater(len(upside), 0)
        for item in upside:
            self.assertIn("compounding", item.get("persona_tags", []))

    def test_get_heatmap_matrix(self):
        """Verify 2D heatmap matrix construction."""
        matrix = get_heatmap_matrix()
        self.assertEqual(matrix["tenure_buckets"], ["<1Y", "1-3Y", "3-5Y", "5-10Y", "10Y+"])
        self.assertEqual(len(matrix["rows"]), 7)
        self.assertEqual(matrix["benchmark_10y_yield"], BENCHMARK_10Y_GSEC_YIELD)

    def test_get_arbitrage_comparison(self):
        """Verify side-by-side comparison scorecard generation."""
        universe = get_normalized_opportunity_universe()
        test_ids = [universe[0]["id"], universe[1]["id"]]
        scorecard = get_arbitrage_comparison(test_ids, tax_slab=30.0, cpi_inflation=4.5)
        self.assertEqual(scorecard["count"], 2)
        self.assertEqual(len(scorecard["items"]), 2)


class TestOpportunityTerminalWebEndpoints(unittest.TestCase):
    """Integration tests for FastAPI endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_get_opportunities_page(self):
        """GET /opportunities should return HTTP 200 with terminal HTML."""
        resp = self.client.get("/opportunities")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Multi-Asset Opportunity Terminal", resp.text)
        self.assertIn("arbitrageDocket", resp.text)
        self.assertIn("arbitrageModal", resp.text)
        self.assertIn("copilotModalBackdrop", resp.text)
        self.assertIn("10% (New Tax Regime Base)", resp.text)

    def test_get_api_opportunities_universe(self):
        """GET /api/opportunities/universe should return structured JSON."""
        resp = self.client.get("/api/opportunities/universe?tax_slab=30&cpi_inflation=4.5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertGreater(data.get("count", 0), 20)
        self.assertIsInstance(data.get("items"), list)

    def test_get_api_opportunities_heatmap(self):
        """GET /api/opportunities/heatmap should return matrix JSON."""
        resp = self.client.get("/api/opportunities/heatmap")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("tenure_buckets", data)
        self.assertIn("rows", data)

    def test_post_api_opportunities_arbitrage(self):
        """POST /api/opportunities/arbitrage should return scorecard JSON."""
        universe_resp = self.client.get("/api/opportunities/universe")
        items = universe_resp.json()["items"]
        test_ids = [items[0]["id"], items[1]["id"]]

        payload = {
            "item_ids": test_ids,
            "tax_slab": 30.0,
            "cpi_inflation": 4.5
        }
        resp = self.client.post("/api/opportunities/arbitrage", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("count"), 2)
        self.assertEqual(len(data.get("items")), 2)


if __name__ == "__main__":
    unittest.main()
