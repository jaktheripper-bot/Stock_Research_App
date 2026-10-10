"""
Unit tests for Institutional Equity Upgrades:
- Sector-Native Scoring Engine
- Angel One Institutional Flow & Level-2 Market Depth
- Unified 360° Forensic Health Sieve
- Multi-Model Valuation Radar & Margin of Safety
- Bull vs. Bear Thesis Synthesis
- Full Dossier Intelligence Compilation
"""

import unittest
from core.analysis.sector_scoring import detect_sector, evaluate_sector_fundamentals
from core.analysis.institutional_flow import analyze_institutional_flow
from core.analysis.forensic_sieve import evaluate_forensic_sieve
from core.analysis.valuation_radar import compute_valuation_radar
from core.analysis.bull_bear import synthesize_bull_bear_thesis
from core.analysis.equity_dossier_intelligence import compile_equity_dossier_intelligence


class TestEquityUpgrades(unittest.TestCase):

    def test_sector_detection(self):
        self.assertEqual(detect_sector("HDFCBANK"), "BFSI")
        self.assertEqual(detect_sector("SBIN"), "BFSI")
        self.assertEqual(detect_sector("INFY", "Information Technology"), "IT_TECH")
        self.assertEqual(detect_sector("TCS", "Software Consulting"), "IT_TECH")
        self.assertEqual(detect_sector("SUNPHARMA", "Pharmaceuticals"), "HEALTHCARE_PHARMA")
        self.assertEqual(detect_sector("L&T", "Engineering & Construction"), "CAPITAL_GOODS_INFRA")

    def test_sector_fundamentals_bfsi(self):
        fund = {
            "roe": 16.5,
            "pb_ratio": 1.7,
            "pe_ratio": 18.0,
            "debt_to_equity": 6.5, # Should NOT be penalized in BFSI!
        }
        res = evaluate_sector_fundamentals("HDFCBANK", fund)
        self.assertEqual(res["sector"], "BFSI")
        self.assertGreater(res["score"], 65.0)
        self.assertTrue(any("Return on Assets" in k["name"] for k in res["kpis"]))

    def test_sector_fundamentals_tech(self):
        fund = {
            "roce": 32.0,
            "roe": 28.0,
            "debt_to_equity": 0.05,
            "pe_ratio": 24.0,
            "sales_growth_3y": 14.5,
        }
        res = evaluate_sector_fundamentals("INFY", fund)
        self.assertEqual(res["sector"], "IT_TECH")
        self.assertGreater(res["score"], 80.0)
        self.assertEqual(res["verdict"], "INDUSTRY_OUTPERFORMER")

    def test_institutional_flow_accumulation(self):
        quote = {
            "ltp": 1200.0,
            "total_buy_qty": 75000,
            "total_sell_qty": 25000,
            "order_imbalance_ratio": 0.75,
            "depth_pressure_regime": "ACCUMULATION_DOMINANT",
            "upper_circuit": 1320.0,
            "lower_circuit": 1080.0,
            "bid_ask_spread_bps": 4.5,
        }
        res = analyze_institutional_flow(quote)
        self.assertEqual(res["status"], "LIVE")
        self.assertEqual(res["flow_regime"], "INSTITUTIONAL_ACCUMULATION")
        self.assertGreaterEqual(res["score"], 70.0)
        self.assertEqual(res["lower_circuit_buffer_pct"], 10.0)

    def test_institutional_flow_unavailable(self):
        res = analyze_institutional_flow(None)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertEqual(res["flow_regime"], "DATA_UNAVAILABLE")

    def test_forensic_sieve_pristine(self):
        clean_fund = {
            "symbol": "TCS",
            "market_cap_cr": 1400000.0,
            "cfo_cr": 45000.0,
            "ebitda_cr": 55000.0,
            "pbt_cr": 50000.0,
            "tax_cr": 12500.0,
            "pledge_pct": 0.0,
            "debt_to_equity": 0.02,
            "interest_coverage_ratio": 50.0,
        }
        res = evaluate_forensic_sieve("TCS", clean_fund)
        self.assertIn(res["verdict"], ["PRISTINE_CLEAN", "MONITOR_WATCHLIST"])
        self.assertGreaterEqual(res["score"], 75.0)

    def test_valuation_radar_margin_of_safety(self):
        # Current price 1000, PE 18, growth 14%
        res = compute_valuation_radar(
            current_price=1000.0,
            pe_ratio=18.0,
            sales_growth_3y=14.0,
            historical_median_pe=24.0,
        )
        self.assertEqual(res["status"], "COMPUTED")
        self.assertGreater(res["fair_value"], 0.0)
        self.assertIn("models", res)
        self.assertIn("dcf_model", res["models"])
        self.assertIn("historical_pe_model", res["models"])

    def test_bull_bear_thesis_generation(self):
        fund = {
            "roce": 24.5,
            "roe": 20.1,
            "debt_to_equity": 0.05,
            "pe_ratio": 28.0,
            "sales_growth_3y": 15.0,
        }
        thesis = synthesize_bull_bear_thesis("RELIANCE", fund)
        self.assertEqual(len(thesis["bull_thesis"]), 3)
        self.assertEqual(len(thesis["bear_thesis"]), 3)
        self.assertTrue(all("title" in b and "detail" in b for b in thesis["bull_thesis"]))
        self.assertTrue(all("title" in b and "detail" in b for b in thesis["bear_thesis"]))

    def test_full_dossier_intelligence_compilation(self):
        fund = {
            "current_price": 1170.3,
            "roce": 22.0,
            "roe": 18.0,
            "debt_to_equity": 0.35,
            "pe_ratio": 25.0,
            "sales_growth_3y": 14.0,
        }
        quote = {
            "ltp": 1170.3,
            "total_buy_qty": 50000,
            "total_sell_qty": 30000,
            "order_imbalance_ratio": 0.625,
            "depth_pressure_regime": "ACCUMULATION_DOMINANT",
            "upper_circuit": 1287.0,
            "lower_circuit": 1053.0,
            "bid_ask_spread_bps": 5.0,
        }
        intel = compile_equity_dossier_intelligence(
            ticker="RELIANCE",
            fundamentals=fund,
            company_name="Reliance Industries Ltd",
            industry_str="Energy & Petrochemicals",
            angel_quote=quote
        )
        self.assertIn("composite_score", intel)
        self.assertIn("sector_intelligence", intel)
        self.assertIn("institutional_flow", intel)
        self.assertIn("forensic_intelligence", intel)
        self.assertIn("valuation_radar", intel)
        self.assertIn("bull_bear_thesis", intel)
    def test_missing_fundamentals_honest_reporting(self):
        # Empty fundamentals must not assert synthetic 15% ROCE or 0.25 D/E
        res = evaluate_sector_fundamentals("TESTCO", {})
        self.assertIn("coverage", res)
        self.assertIn("0 of 4", res["coverage"])
        for k in res["kpis"]:
            self.assertEqual(k["val"], "Not disclosed")
            self.assertEqual(k["status"], "NEUTRAL")
        self.assertIn("statutory", res["narrative"])

    def test_valuation_radar_unavailable_on_missing_or_negative_inputs(self):
        # If price or PE is missing/invalid, should return UNAVAILABLE without fabricating DCF
        res = compute_valuation_radar(current_price=0.0, pe_ratio=0.0)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertEqual(res["fair_value"], 0.0)
        self.assertEqual(res["regime"], "DATA_UNAVAILABLE")

        res2 = compute_valuation_radar(current_price=100.0, pe_ratio=0.0, eps=None)
        self.assertEqual(res2["status"], "UNAVAILABLE")

    def test_chanakya_market_cap_inr_no_false_shell_flag(self):
        from core.cortex.chanakya import evaluate_from_dict
        # Large cap stock with market_cap in INR (~6.5 lakh crore like INFY)
        fund = {
            "symbol": "INFY",
            "market_cap": 6500000000000.0, # INR
            "revenue": 1500000000000.0,
            "ebitda": 350000000000.0,
            "cfo": 250000000000.0,
            "pat": 260000000000.0,
            "debt": 0.0,
            "interest": 0.0,
        }
        res = evaluate_from_dict(fund)
        self.assertNotIn("SUB_SCALE_ILLIQUID_SHELL", res.flags)
        self.assertGreater(res.clean_room_score, 60.0)


if __name__ == "__main__":
    unittest.main()

