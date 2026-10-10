"""Unit and regression tests for Peer Comparison (/compare) localized DB fundamentals cache & harmonization."""

import unittest
from fastapi.testclient import TestClient
from web.main import app
from core.db.fundamentals import (
    extract_fundamentals_from_report_text,
    get_cached_fundamentals,
    save_cached_fundamentals,
    sync_all_cached_fundamentals,
)
from core.analysis.fundamentals import enrich_fundamentals, get_stock_fundamentals
from core.analysis.comparator import compare_two_companies
import asyncio


class TestPeerComparisonDataHarmonization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.analysis.fundamentals import _FUNDAMENTALS_CACHE
        _FUNDAMENTALS_CACHE.clear()

        from core.db.reports import save_report_to_archive
        infy_data = {
            "ticker": "INFY",
            "short_name": "Infosys Ltd",
            "current_price": 1023.4,
            "pe_ratio": "13.95",
            "market_cap": 4153240276683.12,
        }
        infy_text = """### Health Matrix
- Macro: Headwinds
- Moat: Wide
- Governance: Clean
- Diagnostic: Temporary
- Valuation: Undervalued
- Balance Sheet: Debt-Free
- Capital Allocation: Disciplined

- **Return Ratios:** ROE [Return on Equity] remains strong at 31.68%. ROCE [Return on Capital Employed] was 42.84% in FY 2026.
- **Operating Margins:** Operating margins remain healthy within the 20.0% band.
The stock has fallen from its 52-week high of INR 1,727.85 toward INR 1,013.00, close to its 52-week low of INR 980.30.
"""
        save_report_to_archive(stock_data=infy_data, report_text=infy_text)

        tcs_data = {
            "ticker": "TCS",
            "short_name": "Tata Consultancy Services Ltd",
            "current_price": 2156.0,
            "pe_ratio": "15.65",
            "market_cap": 7800596706254.95,
        }
        tcs_text = """### Health Matrix
- Macro: Headwinds
- Moat: Wide
- Governance: Clean
- Diagnostic: Temporary
- Valuation: Undervalued
- Balance Sheet: Debt-Free
- Capital Allocation: Disciplined

- **Return Metrics:** TCS consistently records an ROE [Return on Equity] above 45.0% and an ROCE [Return on Capital Employed] exceeding 55.0%.
- **Operating Margins:** Operating margin stands firm between 24.0% and 25.3%.
The stock price has experienced downward pressure from its 52-week high of INR 3,336.70 toward its 52-week low near INR 1,976.00.
"""
        save_report_to_archive(stock_data=tcs_data, report_text=tcs_text)

        # Ensure database is synchronized with reports and discovery reel
        sync_all_cached_fundamentals()
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    def test_extract_fundamentals_from_report_text(self):
        sample_report = """
        ### Health Matrix
        - Balance Sheet: Debt-Free
        - Moat: Wide

        - **Return Ratios:** ROE [Return on Equity] remains strong at 28.5%. ROCE [Return on Capital Employed] was 36.2% in FY 2026.
        - **Operating Margins:** Operating margins remain healthy within the 22.4% band.
        - **Price Action:** The stock corrected from its 52-week high of INR 1,500.00 toward its 52-week low of INR 950.50.
        """
        extracted = extract_fundamentals_from_report_text(sample_report)
        self.assertEqual(extracted.get("roce"), 36.2)
        self.assertEqual(extracted.get("roe"), 28.5)
        self.assertEqual(extracted.get("operating_margin"), 22.4)
        self.assertEqual(extracted.get("debt_to_equity"), 0.0)
        self.assertEqual(extracted.get("fifty_two_week_high"), 1500.0)
        self.assertEqual(extracted.get("fifty_two_week_low"), 950.5)

    def test_cached_fundamentals_crud_and_aliases(self):
        test_data = {
            "ticker": "TESTPEER",
            "company_name": "Test Peer Diagnostics Ltd",
            "current_price": 500.0,
            "market_cap": 25000000000.0,
            "pe_ratio": "22.5",
            "roce": 26.4,
            "roe": 19.8,
            "operating_margin": 18.2,
            "debt_to_equity": 0.15,
            "fifty_two_week_high": 620.0,
            "fifty_two_week_low": 410.0,
            "source": "UNIT_TEST"
        }
        save_cached_fundamentals("TESTPEER", test_data)
        cached = get_cached_fundamentals("TESTPEER")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["ticker"], "TESTPEER")
        self.assertEqual(cached["roce"], 26.4)
        self.assertEqual(cached["roce_pct"], 26.4)
        self.assertEqual(cached["roe"], 19.8)
        self.assertEqual(cached["operating_margin"], 18.2)
        self.assertEqual(cached["opm"], 18.2)
        self.assertEqual(cached["debt_to_equity"], 0.15)
        self.assertEqual(cached["fifty_two_week_high"], 620.0)
        self.assertEqual(cached["52w_high"], 620.0)
        self.assertEqual(cached["fifty_two_week_low"], 410.0)
        self.assertEqual(cached["52w_low"], 410.0)

    def test_enrich_fundamentals_merges_cache_without_double_formatting(self):
        raw_fund = {"ticker": "INFY", "current_price": 1023.4}
        enriched = enrich_fundamentals("INFY", raw_fund)
        self.assertIsNotNone(enriched.get("roce"))
        self.assertIsNotNone(enriched.get("roe"))
        self.assertIsNotNone(enriched.get("fifty_two_week_high"))
        # Ratios must be numeric or clean without trailing '%'
        self.assertNotIn("%", str(enriched["roce"]))
        self.assertNotIn("%", str(enriched["roe"]))

    def test_compare_two_companies_live_resolution(self):
        res = asyncio.run(compare_two_companies("INFY", "TCS"))
        self.assertIn("fund_a", res)
        self.assertIn("fund_b", res)
        fund_a = res["fund_a"]
        fund_b = res["fund_b"]

        # Assert no N/A in essential ratios
        for key in ["roce", "roe", "operating_margin", "debt_to_equity", "fifty_two_week_high", "fifty_two_week_low"]:
            self.assertIsNotNone(fund_a.get(key), f"Key {key} was None for INFY")
            self.assertNotEqual(fund_a.get(key), "N/A", f"Key {key} was N/A for INFY")
            self.assertIsNotNone(fund_b.get(key), f"Key {key} was None for TCS")
            self.assertNotEqual(fund_b.get(key), "N/A", f"Key {key} was N/A for TCS")

    def test_compare_page_html_rendering_e2e(self):
        response = self.client.get("/compare?a=INFY&b=TCS")
        self.assertEqual(response.status_code, 200)
        html = response.text

        # 1. Title and tickers
        self.assertIn("INFY", html)
        self.assertIn("TCS", html)

        # 2. Assert no double formatting glitches
        self.assertNotIn("₹₹", html)
        self.assertNotIn("%%", html)
        self.assertNotIn("N/A%", html)
        self.assertNotIn("₹N/A", html)

        # 3. Assert verified numeric ratios populate without N/A
        self.assertIn("42.84%", html)
        self.assertIn("31.68%", html)
        self.assertIn("55", html)
        self.assertIn("₹980.3", html)
        self.assertIn("₹1727.85", html)


if __name__ == "__main__":
    unittest.main()
