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
from core.analysis.sector_scoring import (
    detect_sector,
    evaluate_sector_fundamentals,
    SECTOR_DISPLAY_NAMES,
)
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
        """Validates the 14-day freshness window and >=500-char fail-closed dossier evaluator."""
        now = datetime.now(timezone.utc)
        fresh_ts = (now - timedelta(days=2)).isoformat()
        stale_ts = (now - timedelta(days=20)).isoformat()
        valid_body = "Institutional 7-pillar equity research synthesis grounded in statutory filings. " * 10

        self.assertTrue(is_report_fresh({"report_text": valid_body, "timestamp": fresh_ts}))
        self.assertFalse(is_report_fresh({"report_text": valid_body, "timestamp": stale_ts}))
        self.assertFalse(is_report_fresh({"report_text": "short stub", "timestamp": fresh_ts}))
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
        # Direct KNOWN_TICKER_SECTORS expansions
        self.assertEqual(detect_sector("BIOCON"), "HEALTHCARE_PHARMA")
        self.assertEqual(detect_sector("ATHER"), "AUTOMOTIVE")
        self.assertEqual(detect_sector("ZOMATO"), "CONSUMER_FMCG")
        self.assertEqual(detect_sector("PIDILITIND"), "CHEMICALS_MATERIALS")
        self.assertEqual(detect_sector("DLF"), "CAPITAL_GOODS_INFRA")
        self.assertEqual(detect_sector("AVANTEL"), "IT_TECH")
        # Edge cases: NONE string and empty
        self.assertEqual(detect_sector("NONE"), "CONSUMER_FMCG")
        self.assertEqual(detect_sector(""), "CONSUMER_FMCG")

    def test_sector_display_names_and_word_boundaries(self):
        # 1. Verify all 8 core sectors have defined display names
        expected_sectors = {
            "BFSI", "IT_TECH", "HEALTHCARE_PHARMA", "CAPITAL_GOODS_INFRA",
            "AUTOMOTIVE", "CONSUMER_FMCG", "CHEMICALS_MATERIALS", "COMMODITIES_ENERGY"
        }
        self.assertEqual(set(SECTOR_DISPLAY_NAMES.keys()), expected_sectors)

        # 2. Verify word-boundary enforcement prevents 'LIMITED' from triggering IT_TECH
        self.assertEqual(detect_sector("ABC", company_name="ABC Limited"), "CONSUMER_FMCG")
        self.assertEqual(detect_sector("BIOCON", company_name="Biocon Limited"), "HEALTHCARE_PHARMA")
        self.assertEqual(detect_sector("VEDL", "Metals & Mining", "Vedanta Limited"), "COMMODITIES_ENERGY")
        self.assertEqual(detect_sector("TATAMOTORS", "Automobiles", "Tata Motors Limited"), "AUTOMOTIVE")

        # 3. Verify evaluate_sector_fundamentals populates sector_display_name
        res = evaluate_sector_fundamentals("TCS", {"roce": 30.0}, industry_str="Software")
        self.assertEqual(res["sector_display_name"], "IT & Technology Services")

        # 4. Verify evaluate_sector_fundamentals populates canonical display names across all 8 sectors
        sector_sample_tickers = {
            "BFSI": "HDFCBANK",
            "IT_TECH": "TCS",
            "HEALTHCARE_PHARMA": "SUNPHARMA",
            "CAPITAL_GOODS_INFRA": "LT",
            "AUTOMOTIVE": "MARUTI",
            "CONSUMER_FMCG": "ITC",
            "CHEMICALS_MATERIALS": "PIDILITIND",
            "COMMODITIES_ENERGY": "RELIANCE",
        }
        for sec, sym in sector_sample_tickers.items():
            s_res = evaluate_sector_fundamentals(sym, {})
            self.assertEqual(s_res["sector"], sec)
            self.assertEqual(s_res["sector_display_name"], SECTOR_DISPLAY_NAMES[sec])

    def test_unify_sector_classification_telecom_fintech_consumer_electricals(self):
        """2.1.3: Telecom (MTNL), Fintech/Insurance (POLICYBZR, PAYTM), and Consumer Electricals (CROMPTON, VOLTAS, VGUARD) route accurately."""
        self.assertEqual(detect_sector("MTNL", "General Industry", "Mahanagar Telephone Nigam Ltd"), "IT_TECH")
        self.assertEqual(detect_sector("UNKNOWN_TEL", "", "Bharat Telephone Services Ltd"), "IT_TECH")
        self.assertEqual(detect_sector("POLICYBZR", "General Industry", "PB Fintech Limited"), "BFSI")
        self.assertEqual(detect_sector("PAYTM", "Fintech", "One 97 Communications Ltd"), "BFSI")
        self.assertEqual(detect_sector("UNKNOWN_BRK", "Insurance Broking", "Acme Broking Services Ltd"), "BFSI")
        self.assertEqual(detect_sector("CROMPTON", "Consumer Electricals", "Crompton Greaves Consumer Electricals Ltd"), "CONSUMER_FMCG")
        self.assertEqual(detect_sector("VOLTAS", "Consumer Durables", "Voltas Limited"), "CONSUMER_FMCG")
        self.assertEqual(detect_sector("VGUARD", "Consumer Electricals", "V-Guard Industries Ltd"), "CONSUMER_FMCG")
        self.assertEqual(detect_sector("UNKNOWN_CE", "Consumer Electricals", "Sunrise Electricals Ltd"), "CONSUMER_FMCG")
        self.assertEqual(detect_sector("ELECON", "Industrial Machinery", "Elecon Engineering Company Ltd"), "CAPITAL_GOODS_INFRA")

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
        self.assertGreaterEqual(res["disclosed_count"], 5)

    def test_forensic_sieve_insufficient_disclosures_fails_closed(self):
        """Step A (2.1.2): Missing or partial (<5/10) statutory fields must fail closed to INSUFFICIENT_DISCLOSURES."""
        res_empty = evaluate_forensic_sieve("PARTIALCO", {})
        self.assertEqual(res_empty["verdict"], "INSUFFICIENT_DISCLOSURES")
        self.assertEqual(res_empty["status"], "INSUFFICIENT_DISCLOSURES")
        self.assertEqual(res_empty["disclosed_count"], 0)
        self.assertEqual(res_empty["passed_count"], 0)
        self.assertEqual(res_empty["score"], 50.0)
        self.assertIn("Partial Filing (0/10 Verified)", res_empty["badge_label"])
        self.assertNotIn("Clean Accounting Check", res_empty["badge_label"])

        res_partial = evaluate_forensic_sieve(
            "PARTIALCO",
            {"cfo_cr": 120.0, "ebitda_cr": 150.0, "debt_to_equity": 0.25, "pledge_pct": "N/A"},
        )
        self.assertEqual(res_partial["verdict"], "INSUFFICIENT_DISCLOSURES")
        self.assertEqual(res_partial["disclosed_count"], 3)
        self.assertEqual(res_partial["passed_count"], 3)
        self.assertIn("Partial Filing (3/10 Verified)", res_partial["badge_label"])

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

    def test_valuation_radar_extreme_pe_implied_growth_only_and_bounded_mos(self):
        """Step A (2.1.4): Distorted P/Es (<4x or >120x without explicit EPS) return IMPLIED_GROWTH_ONLY; downside MoS is bounded vs CMP."""
        vedl_res = compute_valuation_radar(current_price=232.45, pe_ratio=2.22)
        self.assertEqual(vedl_res["status"], "IMPLIED_GROWTH_ONLY")
        self.assertIsNone(vedl_res["fair_value"])
        self.assertIsNone(vedl_res["margin_of_safety_pct"])
        self.assertEqual(vedl_res["regime"], "EXTREME_MULTIPLE_REGIME")
        self.assertEqual(vedl_res["models"], {})

        eternal_res = compute_valuation_radar(current_price=330.05, pe_ratio=722.92)
        self.assertEqual(eternal_res["status"], "IMPLIED_GROWTH_ONLY")
        self.assertIsNone(eternal_res["fair_value"])
        self.assertIsNone(eternal_res["margin_of_safety_pct"])
        self.assertGreater(eternal_res["inputs"]["implied_fcf_growth_pct"], 20.0)
        self.assertTrue(eternal_res["inputs"]["implied_fcf_growth_bounded"])
        self.assertEqual(eternal_res["inputs"]["implied_fcf_growth_display"], ">45.0% CAGR")
        self.assertEqual(vedl_res["inputs"]["implied_fcf_growth_display"], "<-20.0% CAGR")

        # Discounted stock uses exact Benjamin Graham (FV - P) / FV
        disc_res = compute_valuation_radar(current_price=600.0, pe_ratio=12.0, eps=50.0, sales_growth_3y=14.0, historical_median_pe=22.0)
        expected_graham_mos = round(((disc_res["fair_value"] - 600.0) / disc_res["fair_value"]) * 100.0, 1)
        self.assertEqual(disc_res["margin_of_safety_pct"], expected_graham_mos)

        high_pe_res = compute_valuation_radar(current_price=5000.0, pe_ratio=110.0, sales_growth_3y=15.0)
        self.assertEqual(high_pe_res["status"], "COMPUTED")
        self.assertGreater(high_pe_res["margin_of_safety_pct"], -100.0)

        dossier_ext = compile_equity_dossier("ETERNAL", {"current_price": 330.05, "pe_ratio": 722.92})
        self.assertEqual(dossier_ext["valuation_radar"]["status"], "IMPLIED_GROWTH_ONLY")
        self.assertIn("composite_score", dossier_ext)

        # Step B: sector pe_median & conservative 8.0% sales_growth fallback wired into compile_equity_dossier
        it_dossier = compile_equity_dossier("TCS", {"current_price": 3500.0, "pe_ratio": 25.0})
        self.assertEqual(it_dossier["valuation_radar"]["inputs"]["historical_median_pe"], 28.0)
        self.assertEqual(it_dossier["valuation_radar"]["inputs"]["initial_growth_pct"], 8.0)
        bfsi_dossier = compile_equity_dossier("HDFCBANK", {"current_price": 1700.0, "pe_ratio": 18.0})
        self.assertEqual(bfsi_dossier["valuation_radar"]["inputs"]["historical_median_pe"], 16.0)

    def test_nse_only_equities_never_collide_with_bse_etfs(self):
        """NSE-only equities (BSE, CDSL) must never resolve to BSE Sensex ETF scrips like SENSEX1 (532985)."""
        from bse_master import resolve_bse_scrip_code, resolve_canonical_symbol
        self.assertIsNone(resolve_bse_scrip_code("BSE"))
        self.assertIsNone(resolve_bse_scrip_code("BSE Limited"))
        self.assertIsNone(resolve_bse_scrip_code("CDSL"))
        self.assertEqual(resolve_canonical_symbol("BSE"), "BSE")
        self.assertEqual(resolve_canonical_symbol("BSE Limited"), "BSE")
        self.assertEqual(resolve_canonical_symbol("CDSL"), "CDSL")
        self.assertEqual(resolve_canonical_symbol("Central Depository Services (India) Limited"), "CDSL")

    def test_extract_fundamentals_52w_and_opm_guards(self):
        """2.2.2: 52W regex rejects P/B multiples & % drawdowns (e.g. KOTAKBANK 3.1x / 27.0%) and extracts [EBITDA] margin."""
        from core.db.fundamentals import extract_fundamentals_from_report_text

        prose_trap = (
            "Near its 52-week high, trading at 3.1x P/B, while after correcting 27.0% from its "
            "52-week low of ₹345.50 it stabilized. Earnings Before Interest, Taxes, Depreciation, "
            "and Amortisation [EBITDA] margin expanded to 16.10% in the quarter."
        )
        extracted = extract_fundamentals_from_report_text(prose_trap, fallback_data={"current_price": 459.0})
        self.assertIsNone(extracted.get("fifty_two_week_high"))
        self.assertEqual(extracted.get("fifty_two_week_low"), 345.5)
        self.assertEqual(extracted.get("operating_margin"), 16.1)

        valid_range = "The stock traded across a 52-week range of ₹1,008.50 – ₹2,021.95 with Operating Profit Margin of 17.8%."
        ext_ok = extract_fundamentals_from_report_text(valid_range, fallback_data={"current_price": 1960.0})
        self.assertEqual(ext_ok.get("fifty_two_week_high"), 2021.95)
        self.assertEqual(ext_ok.get("fifty_two_week_low"), 1008.5)
        self.assertEqual(ext_ok.get("operating_margin"), 17.8)

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

    def test_bull_bear_thesis_injects_report_text_falsification_triggers(self):
        fund = {"roce": 22.0, "roe": 19.0, "debt_to_equity": 0.12, "pe_ratio": 26.0}
        sample_report = (
            "## Pillar 1: Business Model\n"
            "Core telecom and retail operations.\n"
            "#### What Would Change This View (Revision Triggers)\n"
            "- **What Contradicts This Conclusion:** Sustained ARPU contraction below ₹195 alongside retail store footprint closures across Tier-2 cities.\n"
            "- **Evidence That Forces a Revision:** Consolidated OCF/EBITDA falling below 60% for two consecutive quarters.\n\n"
            "## Pillar 2: Competitive Moat\n"
            "Scale advantages.\n"
            "#### What Would Change This View (Revision Triggers)\n"
            "- **What Contradicts This Conclusion:** Too short.\n"
            "- **Evidence That Forces a Revision:** N/A\n\n"
            "## Pillar 4: Capital Allocation\n"
            "Disciplined capex.\n"
            "#### What Would Change This View (Revision Triggers)\n"
            "- **What Contradicts This Conclusion:**\n"
            "- **Evidence That Forces a Revision:** Unhedged foreign-currency capex debt exceeding 1.5x consolidated EBITDA in statutory balance sheet filings.\n"
        )
        thesis = synthesize_bull_bear_thesis("RELIANCE", fund, report_text=sample_report)
        bears = thesis["bear_thesis"]
        self.assertEqual(len(bears), 3)
        self.assertEqual(bears[0]["pillar"], "Pillar 01 Trigger")
        self.assertEqual(bears[0]["title"], "Business Model & Revenue Visibility")
        self.assertIn("Sustained ARPU contraction below ₹195", bears[0]["detail"])
        # Pillar 2 (< 35 chars) skipped; Pillar 4 falls back cleanly to evidence_that_forces_revision
        self.assertEqual(bears[1]["pillar"], "Pillar 04 Trigger")
        self.assertEqual(bears[1]["title"], "Capital Allocation & Governance")
        self.assertIn("Unhedged foreign-currency capex debt", bears[1]["detail"])
        # 3rd slot padded from quantitative fallback bear_points
        self.assertNotIn("Trigger", bears[2]["pillar"])

        # Degraded / None report_text preserves quantitative fallback safely
        degraded = synthesize_bull_bear_thesis("RELIANCE", fund, report_text=None)  # type: ignore[arg-type]
        self.assertEqual(len(degraded["bear_thesis"]), 3)

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

    def test_closing_l2_depth_cache_and_non_penalized_composite_score(self):
        from unittest.mock import patch
        from core.analysis import equity_dossier as ed_mod

        ed_mod._CLOSING_L2_CACHE.pop("L2TESTCO", None)
        ed_mod._CLOSING_L2_CACHE.pop("UNAVAILCO", None)
        ed_mod._CLOSING_L2_CACHE.pop("IMPGROWCO", None)

        fund = {"current_price": 1500.0, "pe_ratio": 22.0, "roce": 24.0, "roe": 20.0, "debt_to_equity": 0.05}
        closing_book = {
            "ltp": 1505.0,
            "total_buy_qty": 12000,
            "total_sell_qty": 4000,
            "order_imbalance_ratio": 0.75,
            "depth_pressure_regime": "ACCUMULATION_DOMINANT",
            "upper_circuit": 1650.0,
            "lower_circuit": 1350.0,
            "bid_ask_spread_bps": 4.0,
            "source": "Official Exchange Live Feed",
        }
        empty_after_hours = {"ltp": 1505.0, "total_buy_qty": 0, "total_sell_qty": 0}

        with patch.object(ed_mod.AngelOneGateway, "is_configured", return_value=True):
            # 1. Fetches live L2 depth even when fundamentals["current_price"] > 0 and caches closing snapshot
            with patch.object(ed_mod.AngelOneGateway, "get_stock_quote", return_value=closing_book) as mock_q:
                live_res = compile_equity_dossier("L2TESTCO", fund, industry_str="Information Technology")
                mock_q.assert_called_once_with("L2TESTCO")
                self.assertEqual(live_res["institutional_flow"]["status"], "LIVE")
                self.assertEqual(live_res["institutional_flow"]["source"], "Official Exchange Live Feed")

            # 2. Serves persisted 15:30 IST Closing Depth Snapshot when post-close order book is empty
            with patch.object(ed_mod.AngelOneGateway, "get_stock_quote", return_value=empty_after_hours):
                snap_res = compile_equity_dossier("L2TESTCO", fund, industry_str="Information Technology")
                self.assertEqual(snap_res["institutional_flow"]["status"], "LIVE")
                self.assertEqual(snap_res["institutional_flow"]["source"], "NSE/BSE Closing Depth Snapshot")

            # 3. Never penalizes composite_score by 20% when L2 feed is UNAVAILABLE
            with patch.object(ed_mod.AngelOneGateway, "get_stock_quote", return_value=None):
                no_l2_comp = compile_equity_dossier("UNAVAILCO", fund, industry_str="Information Technology")
                self.assertEqual(no_l2_comp["institutional_flow"]["status"], "UNAVAILABLE")
                sec_s = float(no_l2_comp["sector_intelligence"]["score"])
                for_s = float(no_l2_comp["forensic_intelligence"]["score"])
                mos = no_l2_comp["valuation_radar"]["margin_of_safety_pct"] or 0.0
                val_s = max(10.0, min(100.0, 65.0 + (mos * 1.2)))
                expected_comp = round((sec_s * 0.375) + (val_s * 0.3125) + (for_s * 0.3125), 1)
                self.assertEqual(no_l2_comp["composite_score"], expected_comp)

                no_l2_imp = compile_equity_dossier(
                    "IMPGROWCO", {"current_price": 330.0, "pe_ratio": 450.0, "roce": 20.0}, industry_str="IT"
                )
                self.assertEqual(no_l2_imp["valuation_radar"]["status"], "IMPLIED_GROWTH_ONLY")
                expected_imp = round(
                    float(no_l2_imp["sector_intelligence"]["score"]) * 0.55
                    + float(no_l2_imp["forensic_intelligence"]["score"]) * 0.45,
                    1,
                )
                self.assertEqual(no_l2_imp["composite_score"], expected_imp)

    def test_compile_equity_dossier_effective_industry_and_name_fallbacks(self):
        # 1. When industry_str is empty, fallback to fundamentals sector/industry
        fund_empty_ind = {
            "sector": "Technology",
            "industry": "Software Services",
            "company_name": "Infosys Limited",
            "current_price": 1800.0,
        }
        intel_1 = compile_equity_dossier(
            ticker="INFY",
            fundamentals=fund_empty_ind,
            company_name="",
            industry_str=""
        )
        self.assertEqual(intel_1["sector_intelligence"]["sector"], "IT_TECH")

        # 2. When industry_str is generic ('DIVERSIFIED'), fallback to fundamentals
        fund_generic_ind = {
            "sector": "Automotive",
            "industry": "Commercial Vehicles",
            "company_name": "Tata Motors Ltd",
            "current_price": 950.0,
        }
        intel_2 = compile_equity_dossier(
            ticker="TMCV",
            fundamentals=fund_generic_ind,
            company_name="",
            industry_str="DIVERSIFIED"
        )
        self.assertEqual(intel_2["sector_intelligence"]["sector"], "AUTOMOTIVE")

        # 3. When company_name is missing, fallback to fundamentals company_name / short_name
        fund_pharma = {
            "sector": "Healthcare",
            "industry": "Pharmaceuticals",
            "short_name": "Cipla Ltd",
            "current_price": 1400.0,
        }
        intel_3 = compile_equity_dossier(
            ticker="CIPLA",
            fundamentals=fund_pharma,
            company_name="",
            industry_str="GENERAL INDUSTRY"
        )
        self.assertEqual(intel_3["sector_intelligence"]["sector"], "HEALTHCARE_PHARMA")

    def test_compile_equity_dossier_varan_and_setu_fail_closed(self):
        # 1. Empty fundamentals -> fail closed: both varan_delta_packet and setu_capital_matrix are None
        intel_empty = compile_equity_dossier("EMPTY_CO", {})
        self.assertIsNone(intel_empty["varan_delta_packet"])
        self.assertIsNone(intel_empty["setu_capital_matrix"])

        # 2. Non-dict fundamentals (None) -> fail closed
        intel_none = compile_equity_dossier("NONE_CO", None)
        self.assertIsNone(intel_none["varan_delta_packet"])
        self.assertIsNone(intel_none["setu_capital_matrix"])

        # 3. Scalar revenue_cr only -> varan compiled, setu stays None
        fund_rev_only = {
            "revenue_cr": 2500.0,
            "ebitda_cr": 500.0,
            "pat_cr": 300.0,
        }
        intel_rev = compile_equity_dossier("REV_CO", fund_rev_only)
        self.assertIsNotNone(intel_rev["varan_delta_packet"])
        self.assertIsNone(intel_rev["setu_capital_matrix"])

        # 4. FCF yield only -> setu compiled, varan stays None
        fund_fcf_only = {
            "fcf_yield_pct": 5.2,
            "credit_rating": "AA",
            "promoter_pledge_pct": 2.5,
        }
        intel_fcf = compile_equity_dossier("FCF_CO", fund_fcf_only)
        self.assertIsNone(intel_fcf["varan_delta_packet"])
        self.assertIsNotNone(intel_fcf["setu_capital_matrix"])

        # 5. Full financial fundamentals -> both compiled
        fund_full = {
            "historical_revenues": [1000.0, 1200.0, 1500.0],
            "historical_ebitda": [200.0, 260.0, 350.0],
            "historical_pat": [100.0, 140.0, 200.0],
            "fcf_yield_pct": 4.8,
            "credit_rating": "AAA",
        }
        intel_full = compile_equity_dossier("FULL_CO", fund_full)
        self.assertIsNotNone(intel_full["varan_delta_packet"])
        self.assertIsNotNone(intel_full["setu_capital_matrix"])

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
            self.assertRegex(spliced, r"₹\s*1,?100(?:\.00)?")
        finally:
            from core.db.telemetry import purge_test_telemetry
            purge_test_telemetry()

    def test_compare_peer_cluster_2_to_5_equities(self):
        import asyncio
        from unittest.mock import patch
        from core.analysis.peer_cluster import compare_peer_cluster

        # 1. Bounds enforcement (< 2 or > 5 distinct tickers)
        with self.assertRaises(ValueError):
            asyncio.run(compare_peer_cluster(["INFY"]))
        with self.assertRaises(ValueError):
            asyncio.run(compare_peer_cluster(["INFY", "TCS", "HCLTECH", "WIPRO", "PERSISTENT", "COFORGE"]))

        # 2. Mocked 3-peer cluster with 1 degraded market_cap=None peer & cross-sector disparity
        fake_funds = {
            "INFY": {"company_name": "Infosys Ltd", "market_cap": 5_000_000_000_000, "pe_ratio": "25.0", "roce": 38.0, "roe": 31.0, "operating_margin": 21.0, "debt_to_equity": 0.0, "sector": "Technology"},
            "PERSISTENT": {"company_name": "Persistent Systems", "market_cap": 900_000_000_000, "pe_ratio": "34.0", "roce": 26.0, "roe": 22.0, "operating_margin": 18.0, "debt_to_equity": 0.02, "sector": "IT Services"},
            "HDFCBANK": {"company_name": "HDFC Bank", "market_cap": None, "pe_ratio": "18.0", "roce": None, "roe": 16.5, "operating_margin": None, "debt_to_equity": None, "sector": "Banking"},
        }
        with patch("core.analysis.peer_cluster.get_report_by_ticker_sync", return_value=None), \
             patch("core.analysis.peer_cluster.get_stock_fundamentals", side_effect=lambda s, **kw: dict(fake_funds[s])), \
             patch("core.analysis.peer_cluster.enrich_fundamentals", side_effect=lambda s, f: f):
            res_it = asyncio.run(compare_peer_cluster(["INFY", "INFY", "PERSISTENT"]))
            self.assertEqual(res_it["count"], 2)
            self.assertEqual(res_it["disparity_warnings"], [])
            self.assertEqual(res_it["cluster_medians"]["pe_ratio"], 29.5)

            res_mix = asyncio.run(compare_peer_cluster(["INFY", "PERSISTENT", "HDFCBANK"]))
            self.assertEqual(res_mix["count"], 3)
            # HDFCBANK missing market_cap stays None rather than 0.0, so median of (500000.0, 90000.0) == 295000.0
            self.assertIsNone(res_mix["peers"][2]["metrics"]["market_cap_cr"])
            self.assertEqual(res_mix["cluster_medians"]["market_cap_cr"], 295000.0)
            self.assertTrue(any("[INFY vs HDFCBANK] Sector Disparity" in w for w in res_mix["disparity_warnings"]))


if __name__ == "__main__":
    unittest.main()
