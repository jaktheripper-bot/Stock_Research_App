"""
Unit Tests: Adversarial Stress & Edge-Case Resilience Suite
============================================================
Exhaustively tests all cortex, analytical, ingestion, and calculation engines
with extreme edge-cases: NaN, Inf, NoneType, malformed dictionaries, zero-division
scenarios, negative net worth, string-encoded numbers with commas, and corrupt feeds.
"""

import unittest
import math
from typing import Dict, Any, List

from core.ingestion.angel_one import AngelOneGateway, generate_rfc6238_totp
from core.cortex.garuda import GarudaReflexEngine
from core.cortex.varan import VaranEngine
from core.cortex.sutra import SutraLookThroughEngine
from core.cortex.setu import SetuMatrixEngine
from core.cortex.chanakya import ChanakyaGate
from core.cortex.engine import (
    DynamicStatutoryYieldWedge,
    ReverseDcfHurdleDeconstruct,
    PeadQuantDriftVelocity,
    FiduciaryGovernanceScoringIndex,
)
from core.analysis.valuation_radar import compute_valuation_radar
from core.analysis.sector_scoring import detect_sector, evaluate_sector_fundamentals
from core.analysis.institutional_flow import analyze_institutional_flow
from core.analysis.forensic_sieve import evaluate_forensic_sieve
from core.analysis.bull_bear import synthesize_bull_bear_thesis
from core.analysis.tax_calculator import calculate_net_real_return, compare_asset_classes_post_tax


class TestAdversarialEngineResilience(unittest.TestCase):
    """
    Stress-tests all core analytical engines under extreme, pathological inputs.
    """

    # ----------------------------------------------------------------------
    # 1. Angel One & TOTP
    # ----------------------------------------------------------------------
    def test_totp_generator_adversarial(self):
        # Corrupt and non-string secrets must never crash
        self.assertEqual(generate_rfc6238_totp(None), "")
        self.assertEqual(generate_rfc6238_totp(""), "")
        self.assertEqual(generate_rfc6238_totp(123456), "")
        self.assertEqual(generate_rfc6238_totp("!@#$%^&*()"), "")
        # Valid base32 with lowercase and spaces must succeed
        code = generate_rfc6238_totp("  xsmb nohd 4mre woac r7kd 7bs3 zq  ")
        self.assertTrue(len(code) == 6 and code.isdigit())

    def test_angel_one_depth_adversarial(self):
        # None and malformed books
        res = AngelOneGateway.compute_depth_analytics(None, None)
        self.assertEqual(res["order_imbalance_ratio"], 0.0)

        # Corrupt records with commas, None, NaN, and Inf
        b_book = [{"price": "1,450.50", "quantity": "N/A"}, None, {"price": float("nan"), "quantity": 100}]
        s_book = [{"price": float("inf"), "quantity": "250"}, {"price": 1455.0, "quantity": None}]
        res = AngelOneGateway.compute_depth_analytics(b_book, s_book)
        self.assertIsInstance(res, dict)
        self.assertFalse(math.isnan(res["order_imbalance_ratio"]))
        self.assertFalse(math.isinf(res["order_imbalance_ratio"]))

    # ----------------------------------------------------------------------
    # 2. Garuda Reflex Engine
    # ----------------------------------------------------------------------
    def test_garuda_reflex_adversarial(self):
        # None headline & non-string symbol
        delta = GarudaReflexEngine.classify_announcement(symbol=None, headline=None)
        self.assertIsNotNone(delta)
        self.assertEqual(delta.symbol, "UNKNOWN")

        # Process feed with non-dict and None elements
        deltas = GarudaReflexEngine.process_feed("INFY", [None, "string", 123, {"headline": None}, {}])
        self.assertIsInstance(deltas, list)

        # None feed
        deltas_none = GarudaReflexEngine.process_feed("TCS", None)
        self.assertEqual(deltas_none, [])

    # ----------------------------------------------------------------------
    # 3. Varan Engine
    # ----------------------------------------------------------------------
    def test_varan_dupont_and_cagr_adversarial(self):
        # Negative net worth (insolvent enterprise)
        dupont = VaranEngine.decompose_dupont(50.0, 500.0, 1000.0, -250.0)
        self.assertEqual(dupont.driver, "NEGATIVE_EQUITY_DEFICIT")
        self.assertLess(dupont.computed_roe_pct, 0)

        # Zero sales and zero equity
        dupont_zero = VaranEngine.decompose_dupont(0.0, 0.0, 0.0, 0.0)
        self.assertEqual(dupont_zero.computed_roe_pct, 0.0)

        # Working capital cycle with zero sales and zero cogs
        wc = VaranEngine.compute_working_capital_cycle(10.0, 10.0, 10.0, 0.0, 0.0)
        self.assertEqual(wc.cash_conversion_cycle_days, 0.0)

        # compile_delta_packet with None balance sheet and empty series
        delta = VaranEngine.compile_delta_packet("TEST", [], [], [], [], [], None)
        self.assertIsNotNone(delta)
        self.assertEqual(delta.symbol, "TEST")

    # ----------------------------------------------------------------------
    # 4. Sutra Look-Through Engine
    # ----------------------------------------------------------------------
    def test_sutra_look_through_adversarial(self):
        # None collections
        res = SutraLookThroughEngine.audit_portfolio(None, None, None)
        self.assertIsNotNone(res)
        self.assertEqual(res.total_portfolio_value_inr, 1.0)

        # Strings with commas, negative values, and non-dict items
        eq = [{"symbol": "INFY", "value_inr": "50,000"}, None, "bad_entry"]
        mf = [{"scheme_key": "PPFAS_FLEXICAP", "value_inr": -1000.0}, {"scheme_key": "PPFAS_FLEXICAP", "value_inr": "100,000"}]
        fi = [{"asset_type": "GSEC", "value_inr": "25,000"}]
        res = SutraLookThroughEngine.audit_portfolio(eq, mf, fi)
        self.assertGreater(res.total_portfolio_value_inr, 100000.0)
        self.assertIsInstance(res.top_stock_exposures, list)

    # ----------------------------------------------------------------------
    # 5. Valuation Radar
    # ----------------------------------------------------------------------
    def test_valuation_radar_adversarial(self):
        # Zero price and negative price
        self.assertEqual(compute_valuation_radar(0.0, 20.0)["status"], "UNAVAILABLE")
        self.assertEqual(compute_valuation_radar(-50.0, 20.0)["status"], "UNAVAILABLE")

        # Zero discount rate (must not divide by zero)
        res = compute_valuation_radar(1000.0, 25.0, 40.0, discount_rate=0.0, terminal_growth_rate=0.04)
        self.assertEqual(res["status"], "COMPUTED")
        self.assertFalse(math.isnan(res["fair_value"]))

        # Equal discount rate and terminal growth rate (must not divide by zero)
        res_eq = compute_valuation_radar(1000.0, 25.0, 40.0, discount_rate=0.05, terminal_growth_rate=0.05)
        self.assertEqual(res_eq["status"], "COMPUTED")
        self.assertFalse(math.isnan(res_eq["fair_value"]))

        # Inverted rates (terminal growth > discount rate)
        res_inv = compute_valuation_radar(1000.0, 25.0, 40.0, discount_rate=0.03, terminal_growth_rate=0.08)
        self.assertEqual(res_inv["status"], "COMPUTED")
        self.assertGreater(res_inv["fair_value"], 0.0)

    # ----------------------------------------------------------------------
    # 6. Sector Scoring & Detect
    # ----------------------------------------------------------------------
    def test_sector_scoring_adversarial(self):
        # None and non-string tickers
        self.assertEqual(detect_sector(None), "CONSUMER_FMCG")
        self.assertEqual(detect_sector(12345), "CONSUMER_FMCG")

        # None fundamentals
        res = evaluate_sector_fundamentals("INFY", None)
        self.assertIn("score", res)

        # Strings with commas, percentages, and N/A values
        fund = {"roce": "N/A", "roe": "18.5%", "pe_ratio": "25,00", "debt_to_equity": None}
        res_strings = evaluate_sector_fundamentals("HDFCBANK", fund)
        self.assertIn("score", res_strings)
        self.assertFalse(math.isnan(res_strings["score"]))

    # ----------------------------------------------------------------------
    # 7. Institutional Flow
    # ----------------------------------------------------------------------
    def test_institutional_flow_adversarial(self):
        # None & non-dict
        res = analyze_institutional_flow(None)
        self.assertEqual(res["status"], "UNAVAILABLE")
        res_str = analyze_institutional_flow("not_a_dict")
        self.assertEqual(res_str["status"], "UNAVAILABLE")

        # String numbers with commas and NaN
        data = {
            "ltp": "1,450.25",
            "total_buy_qty": "50,000",
            "total_sell_qty": "30,000",
            "upper_circuit": "1,595.00",
            "lower_circuit": "1,305.00",
            "order_imbalance_ratio": "0.625",
            "bid_ask_spread_bps": float("nan")
        }
        res_live = analyze_institutional_flow(data)
        self.assertEqual(res_live["status"], "LIVE")
        self.assertFalse(math.isnan(res_live["score"]))

    # ----------------------------------------------------------------------
    # 8. Forensic Sieve & ChanakyaGate
    # ----------------------------------------------------------------------
    def test_forensic_sieve_adversarial(self):
        # None fundamentals
        res = evaluate_forensic_sieve("INFY", None)
        self.assertIn("score", res)
        self.assertIn("verdict", res)

        # Empty dictionary
        res_empty = evaluate_forensic_sieve("TCS", {})
        self.assertIn("score", res_empty)

        # Malformed strings in ChanakyaGate
        chan_res = ChanakyaGate.evaluate_from_dict({
            "market_cap_cr": "1,500,000",
            "operating_cash_flow_cr": "N/A",
            "auditor_replacements_3y": "0.0",
        })
        self.assertIsNotNone(chan_res)
        self.assertFalse(math.isnan(chan_res.clean_room_score))

    # ----------------------------------------------------------------------
    # 9. Bull Bear Thesis
    # ----------------------------------------------------------------------
    def test_bull_bear_thesis_adversarial(self):
        # None fundamentals
        res = synthesize_bull_bear_thesis("INFY", None)
        self.assertEqual(len(res["bull_thesis"]), 3)
        self.assertEqual(len(res["bear_thesis"]), 3)

        # Corrupt valuation fair_value string (must not crash format string)
        val_data = {"margin_of_safety_pct": 15.0, "fair_value": "N/A"}
        res_val = synthesize_bull_bear_thesis("HDFCBANK", {"roce": 18.0}, valuation_data=val_data)
        self.assertIn("bull_thesis", res_val)

    # ----------------------------------------------------------------------
    # 10. Setu Matrix Engine
    # ----------------------------------------------------------------------
    def test_setu_matrix_adversarial(self):
        # None symbol and rating
        res = SetuMatrixEngine.evaluate(symbol=None, equity_fcf_yield_pct=5.0, debt_credit_rating=None)
        self.assertEqual(res.symbol, "UNKNOWN")
        self.assertEqual(len(res.tranches), 4)

        # NaN yields and negative tax slab
        res_nan = SetuMatrixEngine.evaluate("TCS", float("nan"), tax_slab_pct=-15.0)
        self.assertFalse(math.isnan(res_nan.equity_fcf_yield_pct))

    # ----------------------------------------------------------------------
    # 11. Tax Calculator
    # ----------------------------------------------------------------------
    def test_tax_calculator_adversarial(self):
        # -100% inflation (division-by-zero deflator)
        res = calculate_net_real_return(10.0, 30.0, cpi_inflation_pct=-100.0)
        self.assertFalse(math.isnan(res["net_real_return_pct"]))

        # compare_asset_classes with NaN slab
        comps = compare_asset_classes_post_tax(marginal_tax_slab_pct=float("nan"))
        self.assertIsInstance(comps, list)
        self.assertEqual(len(comps), 7)


if __name__ == "__main__":
    unittest.main()
