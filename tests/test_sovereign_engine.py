"""Test suite for Indian Sovereign Par Yield Curve, Macro Terminal, and SDL Fiscal Disparity Matrix."""

import os
os.environ["TESTING"] = "1"

import unittest
from fastapi.testclient import TestClient
from web.main import app
from core.analysis.sovereign_engine import (
    evaluate_sovereign_curve,
    generate_curve_svg_data
)
from core.db.sovereign import (
    get_sovereign_yield_curve,
    get_sovereign_sdl_matrix,
    get_macro_monetary_corridor,
    get_historical_sovereign_curves
)


class TestSovereignEngineAndTerminal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.db.sovereign import DEFAULT_SOVEREIGN_BENCHMARKS, save_sovereign_benchmark
        for b in DEFAULT_SOVEREIGN_BENCHMARKS:
            save_sovereign_benchmark(b)
        cls.client = TestClient(app)

    def test_sovereign_yield_curve_benchmarks(self):
        """Verifies 16 statutory sovereign benchmarks are retrieved from repository."""
        curve = get_sovereign_yield_curve()
        self.assertGreaterEqual(len(curve), 16)
        tenors = {item["tenor_label"] for item in curve}
        self.assertIn("91D_TBILL", tenors)
        self.assertIn("182D_TBILL", tenors)
        self.assertIn("364D_TBILL", tenors)
        self.assertIn("2Y_GSEC", tenors)
        self.assertIn("5Y_GSEC", tenors)
        self.assertIn("5Y_SGRB", tenors)
        self.assertIn("10Y_GSEC", tenors)
        self.assertIn("10Y_SGRB", tenors)
        self.assertIn("10Y_SDL", tenors)
        self.assertIn("50Y_GSEC", tenors)

    def test_sdl_fiscal_matrix(self):
        """Verifies State Development Loan benchmarks across 10 borrowing states."""
        sdls = get_sovereign_sdl_matrix()
        self.assertGreaterEqual(len(sdls), 10)
        state_codes = {s["state_code"] for s in sdls}
        self.assertIn("MH", state_codes)
        self.assertIn("GJ", state_codes)
        self.assertIn("KA", state_codes)
        self.assertIn("TN", state_codes)
        self.assertIn("UP", state_codes)
        self.assertIn("WB", state_codes)
        self.assertIn("PB", state_codes)

        # Spreads should be sorted ascending
        spreads = [s["spread_over_gsec_bps"] for s in sdls]
        self.assertEqual(spreads, sorted(spreads))

    def test_macro_monetary_corridor(self):
        """Verifies RBI Policy corridor and MOSPI inflation rates."""
        corridor = get_macro_monetary_corridor()
        self.assertIn("repo_rate", corridor)
        self.assertIn("sdf_rate", corridor)
        self.assertIn("msf_rate", corridor)
        self.assertIn("cpi_inflation", corridor)
        self.assertEqual(corridor["repo_rate"]["value"], 6.50)
        self.assertEqual(corridor["sdf_rate"]["value"], 6.25)
        self.assertEqual(corridor["msf_rate"]["value"], 6.75)
        self.assertEqual(corridor["cpi_inflation"]["value"], 3.65)

    def test_svg_chart_coordinate_generation(self):
        """Verifies mathematical square-root scaling and SVG path construction."""
        hist = get_historical_sovereign_curves()
        chart = generate_curve_svg_data(hist, width=820, height=340)
        self.assertEqual(chart["width"], 820)
        self.assertEqual(chart["height"], 340)
        self.assertIn("current", chart["series"])
        self.assertIn("one_month_ago", chart["series"])
        self.assertIn("one_year_ago", chart["series"])

        # Check path strings
        current_path = chart["series"]["current"]["path_d"]
        self.assertTrue(current_path.startswith("M "))
        self.assertIn(" L ", current_path)

        # Check points bounds
        for pt in chart["series"]["current"]["points"]:
            self.assertGreaterEqual(pt["cx"], chart["pad_left"])
            self.assertLessEqual(pt["cx"], chart["width"] - chart["pad_right"])
            self.assertGreaterEqual(pt["cy"], chart["pad_top"])
            self.assertLessEqual(pt["cy"], chart["height"] - chart["pad_bottom"])

    def test_evaluate_sovereign_curve(self):
        """Verifies the complete analytical payload for the Sovereign Terminal."""
        analytics = evaluate_sovereign_curve()
        self.assertEqual(analytics["benchmark_10y_gsec"], 7.12)
        self.assertEqual(analytics["risk_free_short_tbill"], 6.84)
        self.assertEqual(analytics["term_spread_bps"], 28.0)
        self.assertEqual(analytics["real_10y_yield"], 3.47)
        self.assertEqual(analytics["greenium_bps"], 4.0)
        self.assertGreaterEqual(len(analytics["curve_points"]), 16)
        self.assertGreaterEqual(len(analytics["sdl_matrix"]), 10)
        self.assertGreaterEqual(len(analytics["macro_insights"]), 3)

        # Institutional language check: verify zero colloquial condescension
        for insight in analytics["macro_insights"]:
            self.assertNotIn("plain-english", insight.lower())
            self.assertNotIn("for dummies", insight.lower())

    def test_web_sovereign_page_renders_cleanly(self):
        """Verifies GET /sovereign renders 200 OK with all terminal modules."""
        resp = self.client.get("/sovereign")
        self.assertEqual(resp.status_code, 200)
        html = resp.text
        self.assertIn("Indian Sovereign Debt & Macro Terminal", html)
        self.assertIn("RBI Monetary Policy Corridor", html)
        self.assertIn("sovereignSvg", html)
        self.assertIn("State Development Loan (SDL) Fiscal Disparity Matrix", html)
        self.assertIn("RBI Retail Direct", html)
        self.assertIn("50Y_GSEC", html)
        self.assertIn("10Y_SGRB", html)
        self.assertIn("Maharashtra", html)
        self.assertIn("Punjab", html)

    def test_api_sovereign_curve_endpoint(self):
        """Verifies GET /api/sovereign/curve returns 200 OK and valid JSON."""
        resp = self.client.get("/api/sovereign/curve")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["benchmark_10y_gsec"], 7.12)
        self.assertIn("svg_chart", data)
        self.assertIn("sdl_matrix", data)

    def test_api_sovereign_sdl_matrix_endpoint(self):
        """Verifies GET /api/sovereign/sdl-matrix returns 200 OK."""
        resp = self.client.get("/api/sovereign/sdl-matrix")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("sdl_matrix", data)
        self.assertGreaterEqual(data["count"], 10)

    def test_api_sovereign_macro_endpoint(self):
        """Verifies GET /api/sovereign/macro returns 200 OK."""
        resp = self.client.get("/api/sovereign/macro")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("macro_corridor", data)
        self.assertIn("repo_rate", data["macro_corridor"])
        self.assertEqual(data["macro_corridor"]["repo_rate"]["value"], 6.50)


if __name__ == "__main__":
    unittest.main()
