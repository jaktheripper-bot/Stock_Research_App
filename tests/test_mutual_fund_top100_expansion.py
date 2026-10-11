"""
tests/test_mutual_fund_top100_expansion.py
==============================================================================
Regression and contract tests for Curated Mutual Fund Top 100 Expansion.
Validates that:
1. Exactly 100 canonical institutional schemes are seeded by seed_default_mutual_funds().
2. The 50 newly added schemes spanning Multi Cap, Focused, Value / Contra,
   ELSS (Tax Saver), Large Cap, and Sectoral / Thematic are correctly stored
   with valid AMFI metrics, metadata, and constituent look-through holdings.
3. 7-pillar look-through engine (compute_fund_forensic_lookthrough) evaluates
   new schemes and calculates genuine look-through coverage and moat metrics.
4. Pairwise portfolio overlap operates seamlessly between new and existing schemes.
5. FastAPI public routes /funds/{scheme_code} and /api/funds/dossier/{scheme_code}
   render successfully with HTTP 200.
==============================================================================
"""

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from web.main import app
from core.db.connection import init_db
from core.db.mutual_funds import (
    seed_default_mutual_funds,
    get_mutual_fund_scheme,
    get_scheme_holdings,
    get_active_mutual_funds,
)
from core.analysis.fund_overlap_auditor import compute_fund_forensic_lookthrough
from core.analysis.mutual_funds_engine import calculate_portfolio_overlap


NEW_50_SCHEME_CODES = [
    # Multi Cap (8)
    "MAHINDRA_MULTICAP_DIR",
    "QUANT_MULTICAP_DIR",
    "HDFC_MULTICAP_DIR",
    "KOTAK_MULTICAP_DIR",
    "BARODA_BNP_MULTICAP_DIR",
    "AXIS_MULTICAP_DIR",
    "DSP_MULTICAP_DIR",
    "TATA_MULTICAP_DIR",
    # Focused (8)
    "360ONE_FOCUSED_DIR",
    "ICICI_FOCUSED_DIR",
    "AXIS_FOCUSED_DIR",
    "MIRAE_FOCUSED_DIR",
    "SUNDARAM_FOCUSED_DIR",
    "FRANKLIN_FOCUSED_DIR",
    "NIPPON_FOCUSED_DIR",
    "DSP_FOCUSED_DIR",
    # Value / Contra (8)
    "INVESCO_CONTRA_DIR",
    "UTI_VALUE_DIR",
    "TATA_EQUITY_PE_DIR",
    "TEMPLETON_VALUE_DIR",
    "NIPPON_VALUE_DIR",
    "HDFC_VALUE_DIR",
    "KOTAK_VALUE_DIR",
    "HSBC_VALUE_DIR",
    # ELSS (Tax Saver) (8)
    "PPFAS_ELSS_DIR",
    "BANDHAN_ELSS_DIR",
    "DSP_ELSS_DIR",
    "CANARA_ROBECO_ELSS_DIR",
    "SBI_ELSS_DIR",
    "HDFC_ELSS_DIR",
    "KOTAK_ELSS_DIR",
    "AXIS_ELSS_DIR",
    # Large Cap (8)
    "CANARA_ROBECO_BLUECHIP_DIR",
    "BARODA_BNP_LARGECAP_DIR",
    "SBI_BLUECHIP_DIR",
    "HDFC_TOP100_DIR",
    "AXIS_BLUECHIP_DIR",
    "UTI_MASTERSHARE_DIR",
    "KOTAK_BLUECHIP_DIR",
    "TATA_LARGECAP_DIR",
    # Sectoral / Thematic (10)
    "ICICI_TECH_DIR",
    "TATA_DIGITAL_DIR",
    "SBI_HEALTHCARE_DIR",
    "ICICI_PHARMA_DIR",
    "NIPPON_POWER_INFRA_DIR",
    "SBI_BANKING_DIR",
    "ICICI_BANKING_DIR",
    "TATA_CONSUMER_DIR",
    "NIPPON_CONSUMPTION_DIR",
    "DSP_HEALTHCARE_DIR",
]


class TestMutualFundTop100Expansion(unittest.TestCase):
    """Test suite validating Top 100 Mutual Fund universe expansion."""

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.seeded_count = seed_default_mutual_funds()
        cls.client = TestClient(app)

    def test_seeded_count_is_one_hundred(self):
        """Verifies that seed_default_mutual_funds seeds exactly 100 benchmark schemes."""
        self.assertEqual(self.seeded_count, 100)
        active = get_active_mutual_funds()
        self.assertGreaterEqual(len(active), 100)

    def test_all_fifty_new_schemes_exist_in_db(self):
        """Ensures all 50 newly added schemes can be queried with valid parameters."""
        self.assertEqual(len(NEW_50_SCHEME_CODES), 50)
        for code in NEW_50_SCHEME_CODES:
            scheme = get_mutual_fund_scheme(code)
            self.assertIsNotNone(scheme, f"Scheme {code} not found in database")
            self.assertEqual(scheme["scheme_code"], code)
            self.assertGreater(float(scheme.get("aum_crores", 0)), 0, f"Scheme {code} has 0 AUM")
            self.assertGreater(float(scheme.get("nav", 0)), 0, f"Scheme {code} has 0 NAV")
            ter_dir = float(scheme.get("ter_direct_pct", 0))
            ter_reg = float(scheme.get("ter_regular_pct", 0))
            self.assertGreater(ter_dir, 0.0, f"Scheme {code} has 0 direct TER")
            self.assertGreater(ter_reg, ter_dir, f"Scheme {code} regular TER <= direct TER")

    def test_all_fifty_new_schemes_have_holdings(self):
        """Ensures all 50 newly added schemes have non-empty constituent portfolios."""
        for code in NEW_50_SCHEME_CODES:
            holdings = get_scheme_holdings(code)
            self.assertGreaterEqual(len(holdings), 5, f"Scheme {code} has fewer than 5 holdings")
            total_weight = sum(float(h.get("weight_pct", 0.0)) for h in holdings)
            self.assertGreaterEqual(total_weight, 35.0, f"Scheme {code} total holding weight too low")

    def test_category_distribution_of_expanded_universe(self):
        """Verifies that the expanded schemes cover all major market sleeves with depth."""
        schemes = get_active_mutual_funds()
        cats = {}
        for s in schemes:
            c = s.get("category", "")
            cats[c] = cats.get(c, 0) + 1

        self.assertGreaterEqual(cats.get("Multi Cap Fund", 0), 10)
        self.assertGreaterEqual(cats.get("Focused Fund", 0), 10)
        self.assertGreaterEqual(cats.get("Value / Contra Fund", 0), 11)
        self.assertGreaterEqual(cats.get("ELSS (Tax Saver)", 0), 10)
        self.assertGreaterEqual(cats.get("Large Cap Fund", 0), 11)
        self.assertGreaterEqual(cats.get("Sectoral / Thematic Fund", 0), 10)
        self.assertGreaterEqual(cats.get("Mid Cap Fund", 0), 9)
        self.assertGreaterEqual(cats.get("Small Cap Fund", 0), 8)
        self.assertGreaterEqual(cats.get("Flexi Cap Fund", 0), 8)

    def test_forensic_lookthrough_on_representative_top100_schemes(self):
        """Verifies 7-pillar look-through engine evaluates representative new schemes."""
        representatives = [
            "MAHINDRA_MULTICAP_DIR",
            "360ONE_FOCUSED_DIR",
            "INVESCO_CONTRA_DIR",
            "PPFAS_ELSS_DIR",
            "CANARA_ROBECO_BLUECHIP_DIR",
            "ICICI_TECH_DIR",
        ]
        with patch("core.analysis.fund_overlap_auditor.get_report_by_ticker") as mock_rep:
            mock_rep.return_value = {
                "report_text": "### Health Matrix\nMoat: Wide\nGovernance: Clean\nValuation: Fair\nBalance Sheet: Robust\n"
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

    def test_portfolio_overlap_between_thematic_funds(self):
        """Verifies pairwise portfolio overlap accurately calculates convergence."""
        holdings_tech = get_scheme_holdings("ICICI_TECH_DIR")
        holdings_digital = get_scheme_holdings("TATA_DIGITAL_DIR")

        overlap = calculate_portfolio_overlap(holdings_tech, holdings_digital, "ICICI Tech", "Tata Digital")
        self.assertIn("overlap_pct", overlap)
        self.assertIn("shared_holdings", overlap)
        self.assertGreaterEqual(overlap["overlap_pct"], 30.0)
        self.assertTrue(any(s["identifier"] == "INFY" for s in overlap["shared_holdings"]))
        self.assertTrue(any(s["identifier"] == "TCS" for s in overlap["shared_holdings"]))

    def test_web_routes_for_top100_schemes(self):
        """Verifies /funds/{scheme_code} and /api/funds/dossier/{scheme_code} render HTTP 200."""
        res_tech = self.client.get("/funds/ICICI_TECH_DIR")
        self.assertEqual(res_tech.status_code, 200)
        self.assertIn("ICICI Prudential Technology Fund", res_tech.text)

        res_elss = self.client.get("/funds/PPFAS_ELSS_DIR")
        self.assertEqual(res_elss.status_code, 200)
        self.assertIn("Parag Parikh ELSS Tax Saver Fund", res_elss.text)

        res_api = self.client.get("/api/funds/dossier/360ONE_FOCUSED_DIR")
        self.assertEqual(res_api.status_code, 200)
        data = res_api.json()
        self.assertEqual(data.get("scheme_code"), "360ONE_FOCUSED_DIR")
        self.assertIn("composite_health_score", data)


if __name__ == "__main__":
    unittest.main()
