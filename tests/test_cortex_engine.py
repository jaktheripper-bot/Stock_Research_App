"""
Unit Tests for Anvik Cortex Engine
===================================
Tests all 4 proprietary quantitative and forensic valuation methodologies:
1. Dynamic Statutory Yield Wedge
2. Reverse DCF Hurdle Deconstruct
3. PEAD Quant Drift Velocity
4. Fiduciary Governance Scoring Index
5. Unified Anvik Cortex Engine Composite Evaluation
"""

import unittest
from core.cortex import (
    DynamicStatutoryYieldWedge,
    ReverseDcfHurdleDeconstruct,
    PeadQuantDriftVelocity,
    FiduciaryGovernanceScoringIndex,
    AnvikCortexEngine,
)


class TestDynamicStatutoryYieldWedge(unittest.TestCase):
    def test_expansionary_regime(self):
        # OCF = 15,000 Cr, Capex = 3,000 Cr -> FCF = 12,000 Cr. EV = 100,000 Cr.
        # FCF Yield = 12.0%. 10Y G-Sec = 7.05%. Spread = 495 bps (> 250 bps hurdle)
        res = DynamicStatutoryYieldWedge.evaluate(
            symbol="COALINDIA",
            operating_cash_flow_cr=15000.0,
            maintenance_capex_cr=3000.0,
            enterprise_value_cr=100000.0,
        )
        self.assertEqual(res.symbol, "COALINDIA")
        self.assertEqual(res.statutory_fcf_yield_pct, 12.0)
        self.assertTrue(res.yield_hurdle_pass)
        self.assertEqual(res.regime, "STATUTORY_EXPANSIONARY")
        self.assertIn("exceeding the 250 bps", res.summary)

    def test_compressed_yield_deficit(self):
        # Growth tech / high PE: OCF = 100 Cr, Capex = 80 Cr -> FCF = 20 Cr. EV = 10,000 Cr.
        # FCF Yield = 0.20%. Deficit vs 7.05% G-Sec = -685 bps.
        res = DynamicStatutoryYieldWedge.evaluate(
            symbol="HIGHTECH",
            operating_cash_flow_cr=100.0,
            maintenance_capex_cr=80.0,
            enterprise_value_cr=10000.0,
        )
        self.assertFalse(res.yield_hurdle_pass)
        self.assertEqual(res.regime, "COMPRESSED_YIELD_DEFICIT")
        self.assertLess(res.gsec_spread_bps, -500.0)

    def test_defensive_handles_zero_ev(self):
        res = DynamicStatutoryYieldWedge.evaluate(
            symbol="TEST",
            operating_cash_flow_cr=10.0,
            maintenance_capex_cr=50.0,  # Negative FCF clamped to 0
            enterprise_value_cr=0.0,
        )
        self.assertEqual(res.statutory_fcf_cr, 0.0)
        self.assertEqual(res.statutory_fcf_yield_pct, 0.0)
        self.assertFalse(res.yield_hurdle_pass)


class TestReverseDcfHurdleDeconstruct(unittest.TestCase):
    def test_solve_implied_growth_moderate(self):
        # Price = 500, FCF per share = 25, WACC = 12%, Terminal = 6%
        # At g=6%, P = 25 * 1.06 / (0.12 - 0.06) = 441 approx
        implied_g = ReverseDcfHurdleDeconstruct.solve_implied_growth(
            current_price=500.0,
            fcf_per_share=25.0,
            wacc_pct=12.0,
            terminal_growth_pct=6.0,
        )
        # Should be around 7% - 9%
        self.assertGreater(implied_g, 5.0)
        self.assertLess(implied_g, 15.0)

    def test_herculean_hurdle_classification(self):
        # Extremely high price relative to current FCF implies astronomical growth
        res = ReverseDcfHurdleDeconstruct.evaluate(
            symbol="AEROSPACE",
            current_price=5000.0,
            current_fcf_per_share=10.0,
            historical_fcf_growth_cagr_5y_pct=12.0,
        )
        self.assertEqual(res.hurdle_difficulty, "HERCULEAN_HURDLE")
        self.assertGreater(res.implied_fcf_growth_cagr_5y_pct, 25.0)
        self.assertIsNotNone(res.expectation_gap_pct)
        self.assertGreater(res.expectation_gap_pct, 10.0)

    def test_low_hurdle_classification(self):
        # Depressed price relative to large cash flows
        res = ReverseDcfHurdleDeconstruct.evaluate(
            symbol="VALUECO",
            current_price=200.0,
            current_fcf_per_share=25.0,
            historical_fcf_growth_cagr_5y_pct=15.0,
        )
        self.assertEqual(res.hurdle_difficulty, "LOW_HURDLE")
        self.assertGreater(res.margin_of_safety_pct, 0.0)


class TestPeadQuantDriftVelocity(unittest.TestCase):
    def test_accelerating_drift_velocity(self):
        res = PeadQuantDriftVelocity.evaluate(
            symbol="INFY",
            reported_pat_cr=7500.0,
            consensus_or_prior_pat_cr=6000.0,  # +25% surprise
            post_volume=5000000.0,
            avg_50d_volume=1800000.0,  # 2.78x volume surge
            post_delivery_pct=64.0,  # 64% institutional delivery
        )
        self.assertEqual(res.pead_signal, "ACCELERATING_INSTITUTIONAL_DRIFT")
        self.assertGreaterEqual(res.drift_velocity_score, 65.0)
        self.assertEqual(res.momentum_persistence_days, 35)

    def test_exhaustion_reversal_signal(self):
        res = PeadQuantDriftVelocity.evaluate(
            symbol="WEAKCO",
            reported_pat_cr=200.0,
            consensus_or_prior_pat_cr=350.0,  # -42% contraction
            post_volume=500000.0,
            avg_50d_volume=1000000.0,  # 0.5x volume
            post_delivery_pct=22.0,  # 22% low delivery
        )
        self.assertEqual(res.pead_signal, "EXHAUSTION_REVERSAL")
        self.assertLess(res.drift_velocity_score, 40.0)
        self.assertEqual(res.momentum_persistence_days, 5)


class TestFiduciaryGovernanceScoringIndex(unittest.TestCase):
    def test_pristine_tier(self):
        res = FiduciaryGovernanceScoringIndex.evaluate(
            symbol="TCS",
            rpt_revenue_ratio_pct=1.2,
            promoter_pledge_pct=0.0,
            pledge_velocity_quarterly_delta=0.0,
            board_independence_ratio_pct=58.0,
            contingent_liabilities_to_networth_pct=4.5,
            auditor_qualification_flag=False,
        )
        self.assertEqual(res.governance_tier, "TIER_1_PRISTINE")
        self.assertGreaterEqual(res.fiduciary_score, 80.0)
        self.assertEqual(len(res.flags), 0)

    def test_red_flag_deficit_tier(self):
        res = FiduciaryGovernanceScoringIndex.evaluate(
            symbol="DUBIOUS_LTD",
            rpt_revenue_ratio_pct=28.5,  # -30 pts
            promoter_pledge_pct=62.0,  # -35 pts
            pledge_velocity_quarterly_delta=4.5,  # -10 pts
            board_independence_ratio_pct=25.0,  # -25 pts
            contingent_liabilities_to_networth_pct=120.0,  # -30 pts
            auditor_qualification_flag=True,  # -25 pts
        )
        self.assertEqual(res.governance_tier, "TIER_4_RED_FLAG_DEFICIT")
        self.assertEqual(res.fiduciary_score, 0.0)
        self.assertGreaterEqual(len(res.flags), 5)


class TestAnvikCortexEngineComposite(unittest.TestCase):
    def test_composite_alpha_leader(self):
        eval_res = AnvikCortexEngine.evaluate_asset(
            symbol="TITAN",
            current_price=3200.0,
            current_fcf_per_share=85.0,
            operating_cash_flow_cr=4500.0,
            maintenance_capex_cr=800.0,
            enterprise_value_cr=35000.0,  # High FCF yield
            reported_pat_cr=1200.0,
            consensus_or_prior_pat_cr=950.0,
            post_volume=2500000.0,
            avg_50d_volume=1000000.0,
            post_delivery_pct=62.0,
            historical_fcf_growth_cagr_5y_pct=22.0,
            rpt_revenue_ratio_pct=2.0,
            promoter_pledge_pct=0.0,
            board_independence_ratio_pct=55.0,
        )
        self.assertEqual(eval_res.symbol, "TITAN")
        self.assertGreaterEqual(eval_res.institutional_cortex_score, 70.0)
        self.assertIn(eval_res.conviction_quadrant, ("ALPHA_LEADER", "DEFENSIVE_COMPOUNDER"))

    def test_governance_red_flag_overrides_to_high_risk(self):
        eval_res = AnvikCortexEngine.evaluate_asset(
            symbol="RISKY_CORP",
            current_price=100.0,
            current_fcf_per_share=20.0,
            operating_cash_flow_cr=1000.0,
            maintenance_capex_cr=100.0,
            enterprise_value_cr=5000.0,
            reported_pat_cr=300.0,
            consensus_or_prior_pat_cr=200.0,
            post_volume=1000000.0,
            avg_50d_volume=500000.0,
            post_delivery_pct=50.0,
            rpt_revenue_ratio_pct=35.0,  # Critical RPT
            promoter_pledge_pct=75.0,  # Critical Pledge
            auditor_qualification_flag=True,  # Auditor qualification
        )
        self.assertEqual(eval_res.conviction_quadrant, "HIGH_RISK_DEFICIT")
        self.assertIn("Forensic governance red flags preclude institutional conviction", eval_res.executive_verdict)


if __name__ == "__main__":
    unittest.main()
