"""Comprehensive Unit and Integration Test Suite for Equity Intelligence & Report Generation.

Verifies:
1. Nifty 100 universe registry, BSE scrip code resolution, and report freshness windows.
2. Sector-native KPI scoring engine (BFSI, IT/Tech, Healthcare, Capital Goods).
3. Institutional flow and order depth pressure analysis (accumulation vs distribution).
4. Unified 360° Forensic Health Sieve (governance, cash flow quality, debt solvency).
5. Multi-model valuation radar (DCF, Graham, historical PE) and margin of safety.
6. Bull vs. Bear thesis generation and full equity dossier compilation.
7. Price & Filing pillar updates, technical DMA contexts, and incremental splicing.
"""

import os
import unittest
import pandas as pd
from datetime import datetime, timezone, timedelta

from core.universe.nifty100 import (
    NIFTY_100_CONSTITUENTS,
    get_nifty100_symbols,
    get_nifty100_constituent,
    is_nifty100_stock,
)
from bse_master import resolve_bse_scrip_code
from scripts.generate_nifty100_reports import is_report_fresh
from core.analysis.sector_scoring import detect_sector, evaluate_sector_fundamentals
from core.analysis.institutional_flow import analyze_institutional_flow
from core.analysis.forensic_sieve import evaluate_forensic_sieve
from core.analysis.valuation_radar import compute_valuation_radar
from core.analysis.dossier_bull_bear import synthesize_bull_bear_thesis
from core.analysis.equity_dossier import compile_equity_dossier
from core.cortex.chanakya import evaluate_from_dict
from analyzer import (
    compute_deterministic_technical_context,
    splice_report_pillars,
    evaluate_material_change,
    execute_pillar_update
)

SAMPLE_REPORT = """# Equity Research Report: Infosys Ltd (INFY)

---
## Pillar 1: Macro-Economic, Geopolitical & Environmental Overlays
Macro conditions for global IT services remain cautious due to rate cuts and discretionary tech spending delays.

## Pillar 2: Industry Dynamics & Competitive Positioning
Infosys maintains a top-tier digital transformation moat alongside TCS.

## Pillar 3: Promoter Quality & Fundamental Health
Zero promoter pledge, net-cash balance sheet, high return on equity.

## Pillar 4: The "Structural vs. Temporary" Drop Diagnostic
Recent margin contraction is cyclical, driven by delayed client decision cycles.

## Pillar 5: Valuation & Margin of Safety
Old valuation: Trades at 28x P/E which is rich compared to 10-year historical average of 22x.

## Pillar 6: Technical & Momentum Overlay
Old technicals: Consolidating near 200-DMA with declining momentum.

## Pillar 7: ESG Impact Scorecard
| Parameter | Score (0-100) | Evaluation & Key Drivers |
| :--- | :--- | :--- |
| **Environmental** | 88 | Carbon neutral operations |
| **Social** | 85 | High diversity in tech |
| **Governance** | 94 | High independent board oversight |
"""


class TestNifty100Universe(unittest.TestCase):
    def test_nifty100_universe_completeness(self):
        """Ensures exactly 100 unique constituents exist in the universe."""
        self.assertEqual(len(NIFTY_100_CONSTITUENTS), 100)
        symbols = get_nifty100_symbols()
        self.assertEqual(len(symbols), 100)
        self.assertEqual(len(set(symbols)), 100)

    def test_nifty100_scrip_resolution(self):
        """Verifies that all 100 constituents resolve cleanly to BSE scrip codes."""
        for item in NIFTY_100_CONSTITUENTS:
            sym = item["symbol"]
            scrip = resolve_bse_scrip_code(sym)
            self.assertIsNotNone(scrip, f"Failed to resolve BSE scrip for {sym}")
            self.assertTrue(len(str(scrip)) >= 6, f"Invalid scrip {scrip} for {sym}")

    def test_lookup_utilities(self):
        """Tests symbol lookup and membership check helpers."""
        self.assertTrue(is_nifty100_stock("RELIANCE"))
        self.assertTrue(is_nifty100_stock("reliance"))
        self.assertTrue(is_nifty100_stock("TCS"))
        self.assertFalse(is_nifty100_stock("NON_EXISTENT_TICKER_XYZ"))

        reliance = get_nifty100_constituent("RELIANCE")
        self.assertIsNotNone(reliance)
        self.assertEqual(reliance["bse_scrip"], "500325")

    def test_is_report_fresh(self):
        """Validates the 14-day freshness window evaluator."""
        now = datetime.now(timezone.utc)
        fresh_ts = (now - timedelta(days=2)).isoformat()
        stale_ts = (now - timedelta(days=20)).isoformat()

        self.assertTrue(is_report_fresh({"report_text": "sample text", "timestamp": fresh_ts}))
        self.assertFalse(is_report_fresh({"report_text": "sample text", "timestamp": stale_ts}))
        self.assertFalse(is_report_fresh({"report_text": "", "timestamp": fresh_ts}))
        self.assertFalse(is_report_fresh(None))


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
        self.assertIn("inputs", res)
        self.assertIn("implied_fcf_growth_pct", res["inputs"])
        self.assertGreater(res["inputs"]["implied_fcf_growth_pct"], 0.0)

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
        intel = compile_equity_dossier(
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
        res = evaluate_sector_fundamentals("TESTCO", {})
        self.assertIn("coverage", res)
        self.assertIn("0 of 4", res["coverage"])
        for k in res["kpis"]:
            self.assertEqual(k["val"], "Not disclosed")
            self.assertEqual(k["status"], "NEUTRAL")
        self.assertIn("statutory", res["narrative"])

    def test_valuation_radar_unavailable_on_missing_or_negative_inputs(self):
        res = compute_valuation_radar(current_price=0.0, pe_ratio=0.0)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertEqual(res["fair_value"], 0.0)
        self.assertEqual(res["regime"], "DATA_UNAVAILABLE")
        self.assertIn("inputs", res)
        self.assertEqual(res["inputs"]["implied_fcf_growth_pct"], 0.0)

        res2 = compute_valuation_radar(current_price=100.0, pe_ratio=0.0, eps=None)
        self.assertEqual(res2["status"], "UNAVAILABLE")
        self.assertIn("inputs", res2)

    def test_chanakya_market_cap_inr_no_false_shell_flag(self):
        fund = {
            "symbol": "INFY",
            "market_cap": 6500000000000.0,
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


class TestPillarReportUpdates(unittest.TestCase):
    def test_compute_deterministic_technical_context(self):
        stock_data = {
            "current_price": 1500.0,
            "pe_ratio": "24.5",
            "market_cap": 6000000000000.0,
            "fifty_two_week_high": 1750.0,
            "fifty_two_week_low": 1250.0,
        }
        dates = pd.date_range(end=pd.Timestamp.now(), periods=60)
        prices = [1400.0] * 60
        hist_df = pd.DataFrame({"Close": prices}, index=dates)

        metrics = compute_deterministic_technical_context(stock_data, hist_df)
        self.assertEqual(metrics["price"], 1500.0)
        self.assertEqual(metrics["pe_ratio"], "24.5")
        self.assertEqual(metrics["mcap_cr"], 600000.0)
        self.assertEqual(metrics["dma_50"], 1400.0)
        self.assertIsNotNone(metrics["pct_from_dma50"])
        self.assertEqual(round(metrics["pct_from_dma50"], 1), 7.1)

    def test_splice_report_pillars(self):
        new_p5 = "## Pillar 5: Valuation & Margin of Safety\n\nNew valuation analysis at ₹1500 per share with 24.5x P/E."
        new_p6 = "## Pillar 6: Technical & Momentum Overlay\n\nNew momentum overlay: stock trades +7.1% above 50-DMA."

        spliced = splice_report_pillars(SAMPLE_REPORT, {5: new_p5, 6: new_p6})

        self.assertIn("Macro conditions for global IT services", spliced)
        self.assertIn("Infosys maintains a top-tier digital transformation moat", spliced)
        self.assertIn("Zero promoter pledge, net-cash balance sheet", spliced)
        self.assertIn("Recent margin contraction is cyclical", spliced)
        self.assertIn("Carbon neutral operations", spliced)
        self.assertIn("High independent board oversight", spliced)

        self.assertNotIn("Old valuation: Trades at 28x P/E", spliced)
        self.assertIn("New valuation analysis at ₹1500 per share", spliced)
        self.assertNotIn("Old technicals: Consolidating near 200-DMA", spliced)
        self.assertIn("New momentum overlay: stock trades +7.1% above 50-DMA.", spliced)

    def test_evaluate_material_change_types(self):
        cached = {
            "raw_timestamp": datetime.now(timezone.utc).isoformat(),
            "baseline_price": 1000.0,
            "latest_announcement": "Clean",
        }

        # 1. No change (<5% move)
        live_fund_no_change = {"current_price": 1020.0}
        regen, reason, ann, change_type = evaluate_material_change(cached, live_fund_no_change, "")
        self.assertFalse(regen)
        self.assertEqual(change_type, "NONE")

        # 2. Price shift (>= 5%)
        live_fund_shift = {"current_price": 1060.0}
        regen, reason, ann, change_type = evaluate_material_change(cached, live_fund_shift, "")
        self.assertTrue(regen)
        self.assertEqual(change_type, "PRICE_DELTA")
        self.assertIn("+6.0%", reason)

        # 3. Expired (>14 days)
        cached_expired = {
            "raw_timestamp": (datetime.now(timezone.utc) - timedelta(days=15)).isoformat(),
            "baseline_price": 1000.0,
            "latest_announcement": "Clean",
        }
        regen, reason, ann, change_type = evaluate_material_change(cached_expired, live_fund_no_change, "")
        self.assertTrue(regen)
        self.assertEqual(change_type, "EXPIRED")

    def test_execute_pillar_update_fallback(self):
        cached = {
            "report_text": SAMPLE_REPORT,
            "baseline_price": 1000.0,
        }
        stock_data = {
            "ticker": "TEST_PILLAR_INFY",
            "short_name": "Infosys Ltd",
            "current_price": 1100.0,
            "pe_ratio": "25.0",
            "market_cap": 5000000000000.0,
            "fifty_two_week_high": 1200.0,
            "fifty_two_week_low": 900.0,
        }
        try:
            spliced = execute_pillar_update("TEST_PILLAR_INFY", cached, stock_data)
            self.assertIn("## Pillar 5: Valuation & Margin of Safety", spliced)
            self.assertIn("## Pillar 6: Technical & Momentum Overlay", spliced)
            self.assertIn("Pillar 1: Macro-Economic", spliced)
            self.assertIn("₹1100.00", spliced)
        finally:
            from core.db.telemetry import purge_test_telemetry
            purge_test_telemetry()


if __name__ == "__main__":
    unittest.main()
