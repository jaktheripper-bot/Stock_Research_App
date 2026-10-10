"""
tests/test_mutual_fund_top50_expansion.py
==============================================================================
Regression and contract tests for Option C: Mutual Fund Top 50 Expansion.
Validates that:
1. Exactly 50 canonical schemes are seeded by seed_default_mutual_funds().
2. The 19 newly added schemes spanning Flexi Cap, Mid Cap, Small Cap, and
   Large & Mid Cap are correctly stored with metadata and constituent holdings.
3. 7-pillar look-through engine (compute_fund_forensic_lookthrough) evaluates
   new schemes and calculates genuine look-through coverage and moat metrics.
4. Pairwise portfolio overlap operates seamlessly between new and existing schemes.
5. FastAPI public routes /funds/{scheme_code} and /api/funds/dossier/{scheme_code}
   render successfully with HTTP 200.
==============================================================================
"""

import unittest
from fastapi.testclient import TestClient

from web.main import app
from core.db.connection import init_db
from core.db.mutual_funds import (
    seed_default_mutual_funds,
    get_mutual_fund_scheme,
    get_scheme_holdings,
    get_active_mutual_funds,
)
from core.analysis.fund_forensic_auditor import compute_fund_forensic_lookthrough
from core.analysis.mutual_fund_engine import calculate_portfolio_overlap


NEW_19_SCHEME_CODES = [
    # Flexi Cap (5)
    "JM_FLEXICAP_DIR",
    "DSP_FLEXICAP_DIR",
    "CANARA_ROBECO_FLEXICAP_DIR",
    "FRANKLIN_FLEXICAP_DIR",
    "EDELWEISS_FLEXICAP_DIR",
    # Mid Cap (5)
    "NIPPON_GROWTH_MIDCAP_DIR",
    "SBI_MAGNUM_MIDCAP_DIR",
    "EDELWEISS_MIDCAP_DIR",
    "MIRAE_MIDCAP_DIR",
    "QUANT_MIDCAP_DIR",
    # Small Cap (5)
    "QUANT_SMALLCAP_DIR",
    "AXIS_SMALLCAP_DIR",
    "KOTAK_SMALLCAP_DIR",
    "CANARA_ROBECO_SMALLCAP_DIR",
    "DSP_SMALLCAP_DIR",
    # Large & Mid Cap (4)
    "HDFC_LARGEMID_DIR",
    "KOTAK_EQUITY_OPP_DIR",
    "MIRAE_LARGEMID_DIR",
    "CANARA_ROBECO_EMERGING_DIR",
]


class TestMutualFundTop50Expansion(unittest.TestCase):
    """Test suite validating Top 50 Mutual Fund universe expansion."""

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.seeded_count = seed_default_mutual_funds()
        cls.client = TestClient(app)

    def test_seeded_count_is_fifty(self):
        """Verifies that seed_default_mutual_funds seeds at least 50 benchmark schemes."""
        self.assertGreaterEqual(self.seeded_count, 50)

    def test_all_nineteen_new_schemes_exist_in_db(self):
        """Ensures all 19 newly added schemes can be queried by scheme_code."""
        for code in NEW_19_SCHEME_CODES:
            scheme = get_mutual_fund_scheme(code)
            self.assertIsNotNone(scheme, f"Scheme {code} not found in database")
            self.assertEqual(scheme["scheme_code"], code)
            self.assertGreater(float(scheme.get("aum_crores", 0)), 0, f"Scheme {code} has 0 AUM")
            self.assertGreater(float(scheme.get("nav", 0)), 0, f"Scheme {code} has 0 NAV")

    def test_all_nineteen_new_schemes_have_holdings(self):
        """Ensures all 19 newly added schemes have non-empty constituent portfolios."""
        for code in NEW_19_SCHEME_CODES:
            holdings = get_scheme_holdings(code)
            self.assertGreaterEqual(len(holdings), 5, f"Scheme {code} has fewer than 5 holdings")
            total_weight = sum(float(h.get("weight_pct", 0.0)) for h in holdings)
            self.assertGreaterEqual(total_weight, 35.0, f"Scheme {code} total holding weight too low")

    def test_category_distribution_of_expanded_schemes(self):
        """Verifies that the 19 schemes cover all 4 requested market cap segments."""
        categories = {
            "Flexi Cap Fund": 0,
            "Mid Cap Fund": 0,
            "Small Cap Fund": 0,
            "Large & Mid Cap Fund": 0,
        }
        for code in NEW_19_SCHEME_CODES:
            scheme = get_mutual_fund_scheme(code)
            cat = scheme.get("category")
            if cat in categories:
                categories[cat] += 1

        self.assertEqual(categories["Flexi Cap Fund"], 5)
        self.assertEqual(categories["Mid Cap Fund"], 5)
        self.assertEqual(categories["Small Cap Fund"], 5)
        self.assertEqual(categories["Large & Mid Cap Fund"], 4)

    def test_forensic_lookthrough_on_representative_new_schemes(self):
        """Verifies 7-pillar look-through engine evaluates new schemes without errors."""
        from unittest.mock import patch
        representatives = [
            "JM_FLEXICAP_DIR",
            "NIPPON_GROWTH_MIDCAP_DIR",
            "QUANT_SMALLCAP_DIR",
            "MIRAE_LARGEMID_DIR"
        ]
        with patch("core.analysis.fund_forensic_auditor.get_report_by_ticker") as mock_rep:
            mock_rep.return_value = {
                "report_text": "### Health Matrix\nMoat: Wide\nGovernance: Clean\nValuation: Undervalued\nBalance Sheet: Debt-Free\n"
            }
            for code in representatives:
                lookthrough = compute_fund_forensic_lookthrough(code)
                self.assertIsNotNone(lookthrough)
                self.assertIn("weighted_moat_score", lookthrough)
                self.assertIn("composite_health_score", lookthrough)
                self.assertIn("genuine_coverage_pct", lookthrough)
                self.assertGreaterEqual(
                    lookthrough["genuine_coverage_pct"],
                    70.0,
                    f"Scheme {code} genuine coverage {lookthrough['genuine_coverage_pct']} < 70.0"
                )
                self.assertTrue(lookthrough["has_sufficient_coverage"])
                self.assertIsNotNone(lookthrough["composite_health_score"])

    def test_portfolio_overlap_between_new_and_existing_schemes(self):
        """Verifies pairwise portfolio overlap works between new and existing funds."""
        holdings_ppfas = get_scheme_holdings("PPFAS_FLEXICAP_DIR")
        holdings_jm = get_scheme_holdings("JM_FLEXICAP_DIR")

        overlap = calculate_portfolio_overlap(holdings_ppfas, holdings_jm, "PPFAS", "JM")
        self.assertIn("overlap_pct", overlap)
        self.assertIn("shared_holdings", overlap)
        self.assertGreater(overlap["overlap_pct"], 0.0)
        self.assertTrue(any(s["identifier"] == "HDFCBANK" for s in overlap["shared_holdings"]))

    def test_web_routes_for_new_schemes(self):
        """Verifies /funds/{scheme_code} renders HTML successfully."""
        res = self.client.get("/funds/JM_FLEXICAP_DIR")
        self.assertEqual(res.status_code, 200)
        self.assertIn("JM Flexicap Fund", res.text)

        res_api = self.client.get("/api/funds/dossier/QUANT_SMALLCAP_DIR")
        self.assertEqual(res_api.status_code, 200)
        data = res_api.json()
        self.assertEqual(data.get("scheme_code"), "QUANT_SMALLCAP_DIR")
        self.assertIn("composite_health_score", data)


if __name__ == "__main__":
    unittest.main()
