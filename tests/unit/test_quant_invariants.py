"""Unit tests for quantitative and statutory financial math invariants.

Tests:
1. Debt Dossier: Modified Duration = Macaulay Duration / (1 + y/k) < Macaulay Duration for y > 0,
   and positive convexity dampens drawdowns during rate hikes.
2. REIT Dossier: Section 115UA waterfall splits sum to 100.0% (+/- 0.01%),
   and Net Post-Tax Real Yield <= Gross Pre-Tax Yield.
3. Fund Dossier: Withhold Composite Health Score (None) when 7-pillar coverage < 70.0%,
   and clamp Active Share strictly to [0.0, 100.0].
4. Setu Capital Structure Matrix: Cross-asset spread calculation (+250 bps for 11.0% equity FCF yield vs 8.5% NCD YTM).
"""

import unittest
import pytest

from core.analysis.debt_dossier import (
    compute_duration_and_convexity,
    compute_rate_shock_scenarios,
)
from core.analysis.reit_dossier import (
    validate_section_115ua_waterfall,
    simulate_reit_tax_waterfall,
)
from core.analysis.fund_dossier import (
    clamp_active_share,
    evaluate_fund_coverage_and_health,
)
from core.cortex.setu import SetuMatrixEngine


class TestQuantitativeMathInvariants(unittest.TestCase):
    """Test suite for rigorous quantitative and statutory financial math invariants."""

    # =========================================================================
    # 1. DEBT DOSSIER INVARIANTS
    # =========================================================================
    def test_debt_duration_modified_strictly_less_than_macaulay_for_positive_yield(self):
        """Invariant: Modified Duration = Macaulay Duration / (1 + y/k) < Macaulay Duration for y > 0."""
        # Standard corporate bond: 1000 FV, 9% annual coupon, 5 years maturity, priced at par (YTM = 9%)
        res = compute_duration_and_convexity(
            current_price=1000.0,
            face_value=1000.0,
            coupon_rate_pct=9.0,
            coupon_frequency="ANNUAL",
            time_to_maturity_years=5.0,
            ytm_pct=9.0,
        )

        mac_dur = res["macaulay_duration"]
        mod_dur = res["modified_duration"]
        convexity = res["convexity"]

        self.assertGreater(mac_dur, 0.0)
        self.assertGreater(mod_dur, 0.0)
        # Mathematical invariant: For y = 9% > 0, factor = 1 + 0.09 = 1.09 > 1
        # Therefore, mod_dur = mac_dur / 1.09 must be strictly less than mac_dur
        self.assertLess(
            mod_dur,
            mac_dur,
            f"Modified duration ({mod_dur}) must be strictly less than Macaulay duration ({mac_dur}) for y > 0",
        )
        expected_mod_dur = round(mac_dur / (1.0 + 0.09 / 1), 4)
        self.assertAlmostEqual(mod_dur, expected_mod_dur, places=3)
        self.assertGreater(convexity, 0.0, "Convexity must be strictly positive for standard option-free bonds.")

    def test_debt_convexity_dampens_rate_hike_drawdown(self):
        """Invariant: Rate shock delta includes positive convexity: Delta P/P = -D_mod * dy + 0.5 * C * (dy)^2."""
        current_price = 1000.0
        mod_dur = 4.0
        convexity = 25.0

        # Scenario: +200 bps (+0.02) rate hike
        scenarios = compute_rate_shock_scenarios(
            current_price=current_price,
            modified_duration=mod_dur,
            convexity=convexity,
            rate_shifts_bps=[200],
        )
        self.assertEqual(len(scenarios), 1)
        sc = scenarios[0]

        # Linear duration alone would predict: -4.0 * 0.02 = -8.0%
        # Convexity adjustment: +0.5 * 25.0 * (0.02)^2 = +0.5 * 25.0 * 0.0004 = +0.0050 = +0.50%
        # Total change with convexity: -8.0% + 0.50% = -7.50%
        expected_linear = -8.0
        expected_convexity_adj = 0.50
        expected_total = -7.50

        self.assertAlmostEqual(sc["linear_duration_pct"], expected_linear, places=2)
        self.assertAlmostEqual(sc["convexity_adjustment_pct"], expected_convexity_adj, places=2)
        self.assertAlmostEqual(sc["pct_price_change"], expected_total, places=2)

        # Convexity must cushion the loss: actual price drop (-7.50%) is less severe than linear (-8.0%)
        self.assertGreater(
            sc["pct_price_change"],
            sc["linear_duration_pct"],
            "Positive convexity must cushion bond losses during yield hikes.",
        )

    # =========================================================================
    # 2. REIT & INVIT DOSSIER INVARIANTS
    # =========================================================================
    def test_reit_waterfall_splits_sum_to_100_percent(self):
        """Invariant: Section 115UA waterfall splits must sum to 100.0% (+/- 0.01%)."""
        valid_breakdown = {
            "dividend_pct": 35.0,
            "interest_pct": 35.0,
            "return_of_capital_pct": 20.0,
            "rental_pct": 10.0,
        }
        res = validate_section_115ua_waterfall(valid_breakdown)
        total = sum([res["dividend_pct"], res["interest_pct"], res["return_of_capital_pct"], res["rental_pct"]])
        self.assertAlmostEqual(total, 100.0, places=2)

        # Invalid breakdown summing to 90% must raise ValueError
        invalid_breakdown = {
            "dividend_pct": 30.0,
            "interest_pct": 30.0,
            "return_of_capital_pct": 30.0,
            "rental_pct": 0.0,
        }
        with self.assertRaises(ValueError) as ctx:
            validate_section_115ua_waterfall(invalid_breakdown)
        self.assertIn("Section 115UA Waterfall Invariant Violated", str(ctx.exception))

    def test_reit_post_tax_real_yield_less_than_or_equal_to_pre_tax_yield(self):
        """Invariant: Post-Tax Real Yield <= Pre-Tax Yield across all tax brackets and inflation."""
        mock_reit = {
            "symbol": "BIRET",
            "name": "Brookfield India Real Estate Trust",
            "structure_type": "MAINBOARD_REIT",
            "distribution_yield_pct": 8.40,
            "tax_breakdown": {
                "dividend_pct": 30.0,
                "interest_pct": 40.0,
                "return_of_capital_pct": 30.0,
                "rental_pct": 0.0,
            },
        }

        # Test across standard 10%, 20%, 30%, 39% slabs and various inflation rates
        for slab in [10.0, 20.0, 30.0, 39.0]:
            for inflation in [0.0, 4.0, 5.5, 7.0]:
                waterfall = simulate_reit_tax_waterfall(
                    target=mock_reit,
                    tax_slab_pct=slab,
                    inflation_pct=inflation,
                )
                gross = waterfall["gross_distribution_yield_pct"]
                net_post_tax = waterfall["net_post_tax_yield_pct"]
                post_tax_real = waterfall["post_tax_real_yield_pct"]

                self.assertLessEqual(
                    net_post_tax,
                    gross,
                    f"Net post-tax yield ({net_post_tax}) must be <= gross yield ({gross}) for slab {slab}%",
                )
                self.assertLessEqual(
                    post_tax_real,
                    gross,
                    f"Post-tax real yield ({post_tax_real}) must be <= gross yield ({gross}) for inflation {inflation}%",
                )

    # =========================================================================
    # 3. MUTUAL FUND DOSSIER INVARIANTS
    # =========================================================================
    def test_fund_health_score_withheld_when_coverage_below_70_percent(self):
        """Invariant: Composite Health Score is strictly None when verified 7-pillar coverage < 70.0%."""
        # Case A: Low coverage (55.0% < 70.0%) -> Score must be None
        score_low, as_low = evaluate_fund_coverage_and_health(
            genuine_coverage_pct=55.0,
            raw_composite_health_score=82.5,
            raw_active_share=72.0,
        )
        self.assertIsNone(score_low, "Composite health score must be withheld (None) when coverage < 70.0%")
        self.assertEqual(as_low, 72.0)

        # Case B: Adequate coverage (75.0% >= 70.0%) -> Score must be retained
        score_ok, as_ok = evaluate_fund_coverage_and_health(
            genuine_coverage_pct=75.0,
            raw_composite_health_score=82.5,
            raw_active_share=72.0,
        )
        self.assertIsNotNone(score_ok)
        self.assertEqual(score_ok, 82.5)

    def test_fund_active_share_clamped_to_valid_interval(self):
        """Invariant: Active Share is clamped to [0.0, 100.0]."""
        self.assertEqual(clamp_active_share(-15.0), 0.0)
        self.assertEqual(clamp_active_share(125.0), 100.0)
        self.assertEqual(clamp_active_share(68.456), 68.46)
        self.assertEqual(clamp_active_share(0.0), 0.0)
        self.assertEqual(clamp_active_share(100.0), 100.0)

    # =========================================================================
    # 4. SETU CAPITAL STRUCTURE SPREAD INVARIANT
    # =========================================================================
    def test_setu_cross_asset_capital_structure_spread(self):
        """Invariant: Setu spread between Equity FCF Yield and Senior NCD YTM (11.0% vs 8.5% = +250 bps)."""
        engine = SetuMatrixEngine()
        res = engine.evaluate_capital_structure(
            ticker="TESTCORP",
            market_cap_cr=10000.0,
            trailing_fcf_cr=1100.0,   # 11.0% Equity FCF Yield
            senior_ncd_ytm_pct=8.5,   # 8.5% Senior Bond YTM
            sovereign_10y_ytm_pct=6.8,
        )

        spread_bps = getattr(res, "equity_over_debt_spread_bps", None)
        if spread_bps is None and isinstance(res, dict):
            spread_bps = res.get("equity_over_debt_spread_bps", 0.0)

        # 11.0% - 8.5% = 2.50% = 250 bps
        self.assertAlmostEqual(float(spread_bps), 250.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
