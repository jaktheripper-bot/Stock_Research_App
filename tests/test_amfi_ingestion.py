"""Comprehensive unit tests for Priority 2 Implementation:
1. Live AMFI Ingestion Pipeline & NAV Parser
2. Multi-Asset Omni Product Search
3. Always-On Asset Surveillance Engine & Ledger
4. Zero-Hallucination Dual-Sleeve Look-Through
5. Search & Asset Web Endpoints
"""

import os
import unittest
from fastapi.testclient import TestClient

from core.ingestion.amfi import (
    parse_amfi_nav_feed,
    derive_broad_category,
    derive_benchmark_index,
    search_amfi_master_directory,
    fetch_amfi_nav_raw
)
from core.search.product_search import (
    search_all_products,
    search_equities,
    search_mutual_funds,
    search_debt_securities
)
from core.analysis.asset_scanner import (
    record_scan_start,
    record_scan_complete,
    get_asset_scan_runs,
    scan_debt_securities
)
from core.analysis.mutual_fund_engine import evaluate_dual_sleeve_lookthrough
from core.db.connection import init_db
from web.main import app, _generate_admin_token, ADMIN_COOKIE_NAME


class TestAmfiIngestionAndSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        init_db()
        cls.client = TestClient(app)

    def test_parse_amfi_nav_feed_synthetic(self):
        sample_feed = (
            "Open Ended Schemes (Equity Scheme - Flexi Cap Fund)\n"
            "PPFAS Mutual Fund\n"
            "122639;INF846K01DP8;INF846K01DQ6;Parag Parikh Flexi Cap Fund;Direct;Growth;88.2600;03-Oct-2026\n"
            "122638;INF846K01DR4;;Parag Parikh Flexi Cap Fund;Regular;Growth;78.1000;03-Oct-2026\n"
        )
        # Direct Growth only
        direct_schemes = parse_amfi_nav_feed(sample_feed, direct_growth_only=True)
        self.assertEqual(len(direct_schemes), 1)
        res = direct_schemes[0]
        self.assertEqual(res["scheme_code"], "122639")
        self.assertEqual(res["isin_growth"], "INF846K01DP8")
        self.assertEqual(res["nav"], 88.26)
        self.assertEqual(res["broad_category"], "EQUITY")
        self.assertEqual(res["benchmark_index"], "NIFTY 500 TRI")
        self.assertEqual(res["fund_house"], "PPFAS Mutual Fund")
        self.assertEqual(res["nav_date"], "03-Oct-2026")

        # Both direct and regular
        all_schemes = parse_amfi_nav_feed(sample_feed, direct_growth_only=False)
        self.assertEqual(len(all_schemes), 2)

    def test_derive_category_and_benchmark(self):
        broad1 = derive_broad_category("Equity Scheme - Large Cap Fund")
        bmk1 = derive_benchmark_index("Equity Scheme - Large Cap Fund", broad1)
        self.assertEqual(broad1, "EQUITY")
        self.assertEqual(bmk1, "NIFTY 50 TRI")

        broad2 = derive_broad_category("Debt Scheme - Corporate Bond Fund")
        bmk2 = derive_benchmark_index("Debt Scheme - Corporate Bond Fund", broad2)
        self.assertEqual(broad2, "DEBT")
        self.assertEqual(bmk2, "CRISIL Composite Bond Fund Index")

        broad3 = derive_broad_category("Hybrid Scheme - Balanced Advantage")
        bmk3 = derive_benchmark_index("Hybrid Scheme - Balanced Advantage", broad3)
        self.assertEqual(broad3, "HYBRID")
        self.assertIn("CRISIL Hybrid", bmk3)

    def test_search_amfi_master_directory(self):
        matches = search_amfi_master_directory("Parag Parikh", limit=5)
        self.assertIsInstance(matches, list)
        if matches:
            first = matches[0]
            self.assertIn("scheme_code", first)
            self.assertIn("scheme_name", first)
            self.assertIn("nav", first)

    def test_omni_product_search(self):
        # 1. Search equities
        eq_res = search_equities("TCS", limit=5)
        self.assertIsInstance(eq_res, list)

        # 2. Search mutual funds
        mf_res = search_mutual_funds("Flexi", limit=5)
        self.assertIsInstance(mf_res, list)

        # 3. Search debt
        debt_res = search_debt_securities("SDI", limit=5)
        self.assertIsInstance(debt_res, list)

        # 4. Search all products unified
        all_res = search_all_products("Fund", asset_class="all", limit=10)
        self.assertIsInstance(all_res, list)
        self.assertGreater(len(all_res), 0)
        for item in all_res:
            self.assertIn("asset_class", item)
            self.assertIn("identifier", item)
            self.assertIn("title", item)
            self.assertIn("url", item)

    def test_asset_scanner_ledger(self):
        scan_id = record_scan_start("test_surveillance", triggered_by="unit_test")
        self.assertTrue(scan_id.startswith("scan_"))

        record_scan_complete(
            scan_id=scan_id,
            status="completed",
            items_scanned=42,
            items_added=5,
            items_updated=37,
            items_archived=0,
            details={"test_metric": 100}
        )

        runs = get_asset_scan_runs(limit=10)
        matching = [r for r in runs if r["scan_id"] == scan_id]
        self.assertEqual(len(matching), 1)
        run = matching[0]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["items_scanned"], 42)
        self.assertEqual(run["items_added"], 5)
        self.assertEqual(run["items_updated"], 37)

    def test_debt_asset_scanner_runs(self):
        summary = scan_debt_securities()
        self.assertEqual(summary["asset_class"], "CORPORATE_DEBT")
        self.assertGreaterEqual(summary["scanned"], 0)

    def test_zero_hallucination_lookthrough(self):
        """Verifies that unresearched stocks do not receive hallucinated scores."""
        synthetic_scheme = {
            "scheme_code": "TEST_SCHEME_XYZ",
            "scheme_name": "Test Alpha Portfolio",
            "fund_house": "Alpha Mutual Fund",
            "category": "Flexi Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 500 TRI",
            "aum_crores": 1000.0,
            "nav": 50.0,
            "ter_direct_pct": 0.50,
            "ter_regular_pct": 1.20,
            "portfolio_turnover_ratio_pct": 15.0,
            "active_share_pct": 75.0
        }
        # One unresearched holding not in benchmark proxies or database
        synthetic_holdings = [
            {
                "holding_type": "EQUITY",
                "identifier": "NONEXISTENT_TICKER_12345",
                "holding_name": "Nonexistent Small Cap Ltd",
                "weight_pct": 10.0,
                "sector_or_rating": "Speculative"
            }
        ]

        res = evaluate_dual_sleeve_lookthrough(synthetic_scheme, synthetic_holdings)
        self.assertIsNotNone(res)
        holdings_out = res["holdings"]
        self.assertEqual(len(holdings_out), 1)
        unresearched_h = holdings_out[0]
        # Must strictly have is_researched = False
        self.assertFalse(unresearched_h["is_researched"])
        # Fundamental score must be None or marked N/A
        self.assertEqual(unresearched_h["score"], "N/A")
        self.assertIn("Coverage Pending", unresearched_h["notes"])
        # Coverage percentage must be 0.0%
        self.assertEqual(res["sleeve_breakdown"]["equity_coverage_pct"], 0.0)

    def test_search_web_routes(self):
        # 1. HTML Search page
        resp_html = self.client.get("/search?q=HDFC")
        self.assertEqual(resp_html.status_code, 200)
        self.assertIn("text/html", resp_html.headers["content-type"])
        self.assertIn("Search Investment Products", resp_html.text)

        # 2. JSON API endpoint
        resp_api = self.client.get("/api/search/products?q=Tata&asset_class=all")
        self.assertEqual(resp_api.status_code, 200)
        data = resp_api.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["query"], "Tata")
        self.assertIsInstance(data["results"], list)

    def test_admin_asset_scan_api(self):
        # Unauthenticated request should fail
        resp_unauth = self.client.get("/api/admin/assets/scan-runs")
        self.assertEqual(resp_unauth.status_code, 403)

        # Authenticated with admin token
        token = _generate_admin_token("admin@research.internal", "admin")
        self.client.cookies.set(ADMIN_COOKIE_NAME, token)

        resp_auth = self.client.get("/api/admin/assets/scan-runs")
        self.assertEqual(resp_auth.status_code, 200)
        runs_data = resp_auth.json()
        self.assertEqual(runs_data["status"], "success")
        self.assertIsInstance(runs_data["runs"], list)
