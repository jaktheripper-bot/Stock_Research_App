"""Unit test suite for Mutual Fund 6-Pillar Look-Through & Fiduciary Engine."""

import unittest
from core.db.mutual_funds import (
    seed_default_mutual_funds,
    get_active_mutual_funds,
    get_mutual_fund_scheme,
    get_scheme_holdings,
    get_schemes_by_holding
)
from core.analysis.mutual_fund_engine import (
    calculate_active_share,
    calculate_portfolio_overlap,
    calculate_fee_drag,
    evaluate_dual_sleeve_lookthrough,
    evaluate_mutual_fund_comprehensive
)


class TestMutualFundEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_default_mutual_funds()

    def test_seeded_schemes_count(self):
        schemes = get_active_mutual_funds()
        self.assertGreaterEqual(len(schemes), 6)
        codes = [s["scheme_code"] for s in schemes]
        self.assertIn("PPFAS_FLEXICAP_DIR", codes)
        self.assertIn("MIRAE_LARGECAP_DIR", codes)
        self.assertIn("ICICI_BAF_DIR", codes)
        self.assertIn("ABSL_CORPBOND_DIR", codes)

    def test_ppfas_flexicap_lookthrough_evaluation(self):
        dossier = evaluate_mutual_fund_comprehensive("PPFAS_FLEXICAP_DIR")
        self.assertIsNotNone(dossier)

        lt = dossier["lookthrough"]
        # Under strict SEBI zero-hallucination directive: <70% coverage pauses composite score
        self.assertFalse(lt["has_sufficient_coverage"])
        self.assertIsNone(lt["composite_health_score"])
        self.assertEqual(lt["health_posture"], "COVERAGE_PENDING")

        # When verified reports exist for constituent equities, lookthrough unlocks
        from unittest.mock import patch
        with patch("core.db.reports.get_report_by_ticker") as mock_rep:
            mock_rep.return_value = {"report_text": "### Health Matrix\nVerified 7-pillar report"}
            unlocked_dossier = evaluate_mutual_fund_comprehensive("PPFAS_FLEXICAP_DIR")
            unlocked_lt = unlocked_dossier["lookthrough"]
            self.assertTrue(unlocked_lt["has_sufficient_coverage"])
            self.assertIsNotNone(unlocked_lt["composite_health_score"])
            self.assertGreaterEqual(unlocked_lt["composite_health_score"], 80.0)
            self.assertEqual(unlocked_lt["health_posture"], "INSTITUTIONAL_ALPHA")

        # Verify sleeve breakdown
        sleeve = lt["sleeve_breakdown"]
        self.assertGreater(sleeve["equity_weight_pct"], 60.0)
        self.assertGreater(sleeve["debt_weight_pct"], 5.0)

        # Active Share
        ashare = dossier["active_share"]
        self.assertGreaterEqual(ashare["active_share_pct"], 60.0)
        self.assertEqual(ashare["posture"], "TRUE_ACTIVE_ALPHA")
        self.assertFalse(ashare["is_closet_indexer"])

    def test_closet_indexing_detection(self):
        from core.analysis.mutual_fund_engine import BENCHMARK_PROXIES
        # Create a synthetic index hugger portfolio (matches Nifty 50 benchmark proxy)
        index_hugger_holdings = [
            {"holding_type": "EQUITY", "identifier": k, "weight_pct": v}
            for k, v in BENCHMARK_PROXIES["NIFTY 50 TRI"].items()
        ]
        res = calculate_active_share(index_hugger_holdings, benchmark_name="NIFTY 50 TRI")
        self.assertLess(res["active_share_pct"], 40.0)
        self.assertEqual(res["posture"], "CLOSET_INDEX_FUND")
        self.assertTrue(res["is_closet_indexer"])

    def test_portfolio_overlap_diagnostic(self):
        h_ppfas = get_scheme_holdings("PPFAS_FLEXICAP_DIR")
        h_mirae = get_scheme_holdings("MIRAE_LARGECAP_DIR")
        overlap = calculate_portfolio_overlap(h_ppfas, h_mirae, "PPFAS", "Mirae Large Cap")

        # PPFAS and Mirae both hold HDFCBANK, INFY, RELIANCE, TCS, ITC, etc.
        self.assertGreater(overlap["overlap_pct"], 25.0)
        self.assertLess(overlap["overlap_pct"], 60.0)
        self.assertEqual(overlap["verdict"], "MODERATE_CONVERGENCE")
        self.assertIn("overlap", overlap["recommendation"].lower())
        self.assertGreater(overlap["shared_holdings_count"], 0)

        shared_idents = [s["identifier"] for s in overlap["shared_holdings"]]
        self.assertIn("HDFCBANK", shared_idents)
        self.assertIn("RELIANCE", shared_idents)
        self.assertIn("INFY", shared_idents)

    def test_fee_drag_and_wealth_destruction_schedule(self):
        drag = calculate_fee_drag(
            ter_direct_pct=0.62,
            ter_regular_pct=1.33,
            initial_investment_lakhs=10.0,
            assumed_gross_return_pct=12.0
        )
        self.assertEqual(drag["ter_spread_bps"], 71.0)
        self.assertEqual(len(drag["schedule"]), 4)

        sched_10y = drag["schedule"][1]
        self.assertEqual(sched_10y["years"], 10)
        self.assertGreater(sched_10y["wealth_lost_inr"], 100000.0)
        self.assertGreater(sched_10y["wealth_lost_pct"], 5.0)

    def test_hybrid_dual_sleeve_icici_baf(self):
        dossier = evaluate_mutual_fund_comprehensive("ICICI_BAF_DIR")
        self.assertIsNotNone(dossier)

        lt = dossier["lookthrough"]
        sleeve = lt["sleeve_breakdown"]
        self.assertGreater(sleeve["equity_weight_pct"], 20.0)
        self.assertGreater(sleeve["debt_weight_pct"], 20.0)
        self.assertGreaterEqual(sleeve["debt_sleeve_score"], 80.0)

    def test_reverse_lookthrough_holding_lookup(self):
        schemes = get_schemes_by_holding("INFY")
        self.assertGreaterEqual(len(schemes), 3)
        scheme_codes = [s["scheme_code"] for s in schemes]
        self.assertIn("PPFAS_FLEXICAP_DIR", scheme_codes)
        self.assertIn("MIRAE_LARGECAP_DIR", scheme_codes)
        self.assertIn("ICICI_BAF_DIR", scheme_codes)

    def test_aum_capacity_trap_warnings(self):
        scheme_small = get_mutual_fund_scheme("SBI_SMALLCAP_DIR")
        holdings_small = get_scheme_holdings("SBI_SMALLCAP_DIR")
        lt = evaluate_dual_sleeve_lookthrough(scheme_small, holdings_small)

        # SBI Small Cap has AUM > 25,000 Cr, should trigger capacity warning
        warnings_str = " ".join(lt["warnings"])
        self.assertIn("AUM Capacity Trap", warnings_str)


if __name__ == "__main__":
    unittest.main()
