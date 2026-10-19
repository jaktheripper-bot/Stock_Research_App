"""
Comprehensive Unit Tests for the 5 Cortex Proprietary Engines
============================================================
Tests:
1. Phase 1: Chanakya Clean-Room Forensic Screening Filter (ChanakyaGate)
2. Phase 2: Varan Deterministic Financial Ingestion & XBRL Delta Engine (VaranEngine)
3. Phase 3: Setu Cross-Asset Capital Structure Matrix (SetuMatrixEngine)
4. Phase 4: Garuda Event-Driven Micro-Snapshot Engine (GarudaReflexEngine)
5. Phase 5: Sutra Multi-Asset Portfolio Look-Through Engine (SutraLookThroughEngine)
"""

import unittest
import json
from core.cortex import (
    ChanakyaGate,
    ChanakyaResult,
    VaranEngine,
    VaranDeltaPacket,
    SetuMatrixEngine,
    SetuMatrixResult,
    GarudaReflexEngine,
    MicroSnapshotDelta,
    SutraLookThroughEngine,
    SutraLookThroughResult,
    DynamicStatutoryYieldWedge,
    ReverseDcfHurdleDeconstruct,
    PeadQuantDriftVelocity,
    FiduciaryGovernanceScoringIndex,
    AnvikCortexEngine,
)


class TestChanakyaGate(unittest.TestCase):
    def test_pristine_company_passes(self):
        # A clean, high-quality company
        res = ChanakyaGate.evaluate(
            symbol="PRISTINE_IND",
            operating_cash_flow_cr=250.0,
            ebitda_cr=300.0,
            reported_pbt_cr=220.0,
            tax_paid_cr=55.0,  # ~25% ETR
            promoter_pledge_pct=0.0,
            auditor_replacements_3y=0,
            contingent_liabilities_cr=20.0,
            net_worth_cr=800.0,
            rpt_transaction_cr=10.0,
            net_revenue_cr=1000.0,
            dso_days=45.0,
            interest_coverage_ratio=15.0,
            debt_to_equity=0.05,
            tangible_net_worth_cr=800.0,
            retained_earnings_cr=600.0,
            market_cap_cr=5000.0,
            mode="STRICT",
        )
        self.assertTrue(res.overall_passed)
        self.assertEqual(res.status, "PRISTINE_CLEAN")
        self.assertGreaterEqual(res.clean_room_score, 90.0)
        self.assertEqual(len(res.flags), 0)

    def test_negative_cfo_ebitda_divergence(self):
        # EBITDA is 100 Cr, but CFO is -20 Cr
        res = ChanakyaGate.evaluate(
            symbol="PHANTOM_CASH",
            operating_cash_flow_cr=-20.0,
            ebitda_cr=100.0,
            reported_pbt_cr=80.0,
            tax_paid_cr=20.0,
            net_worth_cr=500.0,
            net_revenue_cr=600.0,
            mode="STRICT",
        )
        self.assertFalse(res.overall_passed)
        self.assertIn("NEGATIVE_CFO_EBITDA_DIVERGENCE", res.flags)
        self.assertEqual(res.status, "CAUTIONARY_DEFICIT")

    def test_phantom_tax_rate_deficit(self):
        # PBT is 100 Cr, but tax paid is only 2 Cr (2% ETR)
        res = ChanakyaGate.evaluate(
            symbol="TAX_EVADER",
            operating_cash_flow_cr=80.0,
            ebitda_cr=100.0,
            reported_pbt_cr=100.0,
            tax_paid_cr=2.0,  # 2% ETR (< 8% critical)
            net_worth_cr=500.0,
            net_revenue_cr=600.0,
            mode="STRICT",
        )
        self.assertFalse(res.overall_passed)
        self.assertIn("SUSPICIOUS_STATUTORY_TAX_RATE", res.flags)

    def test_promoter_pledge_spike(self):
        res = ChanakyaGate.evaluate(
            symbol="PLEDGE_TRAP",
            operating_cash_flow_cr=80.0,
            ebitda_cr=100.0,
            reported_pbt_cr=70.0,
            tax_paid_cr=18.0,
            promoter_pledge_pct=65.0,  # > 50% critical
            promoter_pledge_qoq_delta=6.0,
            net_worth_cr=500.0,
            net_revenue_cr=600.0,
            mode="STRICT",
        )
        self.assertFalse(res.overall_passed)
        self.assertIn("CRITICAL_PROMOTER_PLEDGE_ENCUMBRANCE", res.flags)

    def test_auditor_churn(self):
        res = ChanakyaGate.evaluate(
            symbol="AUDIT_CHURN",
            operating_cash_flow_cr=80.0,
            ebitda_cr=100.0,
            reported_pbt_cr=70.0,
            tax_paid_cr=18.0,
            auditor_replacements_3y=3,  # >= 2 critical
            net_worth_cr=500.0,
            net_revenue_cr=600.0,
            mode="STRICT",
        )
        self.assertFalse(res.overall_passed)
        self.assertIn("EXCESSIVE_AUDITOR_CHURN", res.flags)

    def test_evaluate_from_dict(self):
        cand = {
            "symbol": "TESTCO",
            "base_mcap": 50_000_000_000,
            "roce": 22.0,
            "debt_to_equity": 0.1,
            "cfo_cr": 120.0,
            "ebitda_cr": 150.0,
            "pbt_cr": 110.0,
            "tax_cr": 28.0,
            "sales_cr": 800.0,
        }
        res = ChanakyaGate.evaluate_from_dict(cand, mode="STRICT")
        self.assertTrue(res.overall_passed)
        self.assertEqual(res.status, "PRISTINE_CLEAN")


class TestVaranEngine(unittest.TestCase):
    def test_cagr_calculation(self):
        # 100 to 200 in 3 years is ((2)^(1/3) - 1) = 25.99%
        cagr = VaranEngine.calculate_cagr(100.0, 200.0, 3)
        self.assertIsNotNone(cagr)
        self.assertAlmostEqual(cagr, 25.99, places=1)

    def test_dupont_decomposition(self):
        # Net Profit = 15 Cr, Sales = 100 Cr, Assets = 150 Cr, Equity = 75 Cr
        # Net Margin = 15%, Asset Turnover = 0.67, Leverage = 2.0 -> ROE = 20%
        dupont = VaranEngine.decompose_dupont(
            net_profit_cr=15.0,
            net_sales_cr=100.0,
            total_assets_cr=150.0,
            total_equity_cr=75.0,
        )
        self.assertEqual(dupont.net_profit_margin_pct, 15.0)
        self.assertAlmostEqual(dupont.computed_roe_pct, 20.0, places=1)

    def test_working_capital_cycle(self):
        wc = VaranEngine.compute_working_capital_cycle(
            accounts_receivable_cr=100.0,
            inventory_cr=150.0,
            accounts_payable_cr=80.0,
            net_sales_cr=1000.0,
            cogs_or_expenses_cr=700.0,
        )
        # DSO = (100 / 1000) * 365 = 36.5
        # DIO = (150 / 700) * 365 = 78.2
        # DPO = (80 / 700) * 365 = 41.7
        # CCC = 36.5 + 78.2 - 41.7 = 73.0
        self.assertAlmostEqual(wc.dso_days, 36.5, places=1)
        self.assertAlmostEqual(wc.cash_conversion_cycle_days, 73.0, places=0)
        self.assertEqual(wc.trajectory, "STRETCHED")

    def test_compile_delta_packet(self):
        packet = VaranEngine.compile_delta_packet(
            symbol="CLEAN_COMPOUNDER",
            annual_revenues=[500.0, 600.0, 720.0, 850.0, 1000.0],
            annual_ebitda=[100.0, 130.0, 160.0, 200.0, 250.0],
            annual_pat=[60.0, 80.0, 100.0, 130.0, 170.0],
            annual_cfo=[70.0, 90.0, 110.0, 150.0, 190.0],
            annual_capex=[20.0, 25.0, 30.0, 40.0, 50.0],
            latest_balance_sheet={
                "total_assets_cr": 1200.0,
                "total_equity_cr": 800.0,
                "total_debt_cr": 50.0,
                "cash_and_equivalents_cr": 100.0,
                "accounts_receivable_cr": 120.0,
                "inventory_cr": 100.0,
                "accounts_payable_cr": 90.0,
                "interest_expense_cr": 4.0,
            },
            reporting_period="FY24",
        )
        self.assertEqual(packet.symbol, "CLEAN_COMPOUNDER")
        self.assertEqual(packet.growth_quality_grade, "INSTITUTIONAL_COMPOUNDER")
        self.assertIsNotNone(packet.cagrs.sales_cagr_3y)
        self.assertGreater(packet.returns.roce_pct, 15.0)
        # Verify JSON is compact and parses cleanly
        data = json.loads(packet.dense_json_payload)
        self.assertEqual(data["symbol"], "CLEAN_COMPOUNDER")
        self.assertEqual(data["grade"], "INSTITUTIONAL_COMPOUNDER")


class TestSetuMatrixEngine(unittest.TestCase):
    def test_pristine_capital_hierarchy(self):
        # Equity FCF Yield = 8.5%, Senior NCD = 7.9% (AAA spread over 7.05% G-Sec)
        res = SetuMatrixEngine.evaluate(
            symbol="CASH_RICH",
            equity_fcf_yield_pct=8.5,
            senior_debt_ytm_pct=7.9,
            gsec_10y_yield_pct=7.05,
            mutual_fund_net_flow_cr=150.0,
        )
        self.assertEqual(res.capital_posture_regime, "PRISTINE_CAPITAL_HIERARCHY")
        self.assertGreater(res.seniority_spread_bps, 0.0)
        self.assertEqual(len(res.anomalies), 0)
        self.assertGreater(res.institutional_mf_velocity_score, 50.0)

    def test_capital_structure_inversion(self):
        # Equity priced for perfection (FCF yield = 1.2%), Senior NCD yields 8.5%
        res = SetuMatrixEngine.evaluate(
            symbol="BUBBLE_VALUATION",
            equity_fcf_yield_pct=1.2,
            senior_debt_ytm_pct=8.5,
            gsec_10y_yield_pct=7.05,
        )
        self.assertEqual(res.capital_posture_regime, "CAPITAL_STRUCTURE_INVERSION")
        self.assertLess(res.seniority_spread_bps, -500.0)
        self.assertGreater(len(res.anomalies), 0)
        self.assertEqual(res.anomalies[0].anomaly_type, "CAPITAL_STRUCTURE_INVERSION")

    def test_credit_stress_dislocation(self):
        # Senior debt YTM is 11.2% (spread = 415 bps over 7.05% G-Sec)
        res = SetuMatrixEngine.evaluate(
            symbol="DISTRESSED_BOND",
            equity_fcf_yield_pct=12.0,
            senior_debt_ytm_pct=11.2,
            gsec_10y_yield_pct=7.05,
        )
        self.assertEqual(res.capital_posture_regime, "CREDIT_STRESS_DISLOCATION")
        self.assertTrue(any(a.anomaly_type == "CREDIT_SPREAD_BLOWOUT" for a in res.anomalies))

    def test_sanitized_inputs_capital_structure_inversion(self):
        # Passes None / non-numeric values to ensure sanitized fcf_yield, mf_flow, and pledge_val are evaluated safely
        res = SetuMatrixEngine.evaluate(
            symbol="NONE_PARAM_CO",
            equity_fcf_yield_pct=None,
            senior_debt_ytm_pct=7.9,
            gsec_10y_yield_pct=7.05,
            mutual_fund_net_flow_cr=None,
            promoter_pledge_pct=None,
        )
        self.assertEqual(res.capital_posture_regime, "CAPITAL_STRUCTURE_INVERSION")
        self.assertEqual(res.equity_fcf_yield_pct, 0.0)
        self.assertTrue(any(a.anomaly_type == "CAPITAL_STRUCTURE_INVERSION" for a in res.anomalies))


class TestGarudaReflexEngine(unittest.TestCase):
    def test_classifies_earnings_to_pillar_5(self):
        delta = GarudaReflexEngine.classify_announcement(
            symbol="INFY",
            headline="Financial Results For The Quarter Ended September 30, 2026",
            filing_date="2026-10-10",
        )
        self.assertEqual(delta.target_pillar_id, 5)
        self.assertEqual(delta.catalyst_type, "FINANCIAL_EARNINGS")
        self.assertEqual(delta.urgency, "IMMEDIATE_REFRESH")
        self.assertTrue(delta.action_required)
        self.assertIn("INFY", delta.delta_snippet_md)

    def test_classifies_auditor_resignation_to_pillar_6(self):
        delta = GarudaReflexEngine.classify_announcement(
            symbol="TESTCORP",
            headline="Resignation of Statutory Auditor M/s ABC & Co.",
            filing_date="2026-10-10",
        )
        self.assertEqual(delta.target_pillar_id, 6)
        self.assertEqual(delta.catalyst_type, "GOVERNANCE_REGULATORY")
        self.assertEqual(delta.urgency, "IMMEDIATE_REFRESH")

    def test_classifies_dividend_to_pillar_4(self):
        delta = GarudaReflexEngine.classify_announcement(
            symbol="TCS",
            headline="Declaration of Second Interim Dividend of Rs 10 per share",
            filing_date="2026-10-10",
        )
        self.assertEqual(delta.target_pillar_id, 4)
        self.assertEqual(delta.catalyst_type, "CAPITAL_ALLOCATION")

    def test_classifies_shareholding_to_pillar_3(self):
        delta = GarudaReflexEngine.classify_announcement(
            symbol="RELIANCE",
            headline="Shareholding Pattern for the quarter ended September 2026",
            filing_date="2026-10-10",
        )
        self.assertEqual(delta.target_pillar_id, 3)
        self.assertEqual(delta.catalyst_type, "PROMOTER_SHAREHOLDING")

    def test_classifies_concall_to_pillar_2(self):
        delta = GarudaReflexEngine.classify_announcement(
            symbol="HCLTECH",
            headline="Audio Recording and Transcript of Earnings Concall",
            filing_date="2026-10-10",
        )
        self.assertEqual(delta.target_pillar_id, 2)
        self.assertEqual(delta.catalyst_type, "CONCALL_PRESENTATION")


class TestSutraLookThroughEngine(unittest.TestCase):
    def test_detects_hidden_single_stock_concentration(self):
        # Investor owns HDFCBANK directly (₹1,00,000)
        # Also owns PPFAS Flexi Cap (₹4,00,000) which has ~7.8% in HDFCBANK (₹31,200)
        # Also owns HDFC Top 100 (₹3,00,000) which has ~9.8% in HDFCBANK (₹29,400)
        # Also owns ₹2,00,000 in SGB
        # Total Portfolio = ₹10,00,000.
        # Direct HDFC Bank = 10%.
        # Indirect HDFC Bank = (31,200 + 29,400) = 60,600 (6.06%).
        # Total HDFC Bank Exposure = 16.06% (> 10% safe limit -> ELEVATED)
        res = SutraLookThroughEngine.audit_portfolio(
            direct_equities=[
                {"symbol": "HDFCBANK", "value_inr": 100000.0},
                {"symbol": "INFY", "value_inr": 50000.0},
            ],
            mutual_funds=[
                {"scheme_key": "PPFAS_FLEXICAP", "value_inr": 400000.0},
                {"scheme_key": "HDFC_TOP100", "value_inr": 300000.0},
            ],
            fixed_income_and_sov=[
                {"asset_type": "SGB_GOLD", "value_inr": 150000.0},
            ],
        )
        self.assertAlmostEqual(res.total_portfolio_value_inr, 1000000.0, places=0)
        hdfc_exp = next((e for e in res.top_stock_exposures if e.symbol == "HDFCBANK"), None)
        self.assertIsNotNone(hdfc_exp)
        self.assertAlmostEqual(hdfc_exp.total_exposure_pct, 16.06, places=1)
        self.assertEqual(hdfc_exp.concentration_flag, "ELEVATED")
        self.assertIn("PPFAS_FLEXICAP", hdfc_exp.holding_funds)
        self.assertIn("HDFC_TOP100", hdfc_exp.holding_funds)
        self.assertTrue(any("HDFCBANK" in alert for alert in res.hidden_overlap_alerts))
        self.assertGreater(res.capital_hierarchy.sovereign_gold_pct, 10.0)


class TestCortexAPIEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from web.main import app
        cls.client = TestClient(app)

    def test_api_cortex_chanakya(self):
        resp = self.client.get("/api/cortex/chanakya/INFY")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["symbol"], "INFY")
        self.assertIn("clean_room_score", data)
        self.assertIn("status", data)

    def test_api_cortex_setu(self):
        resp = self.client.get("/api/cortex/setu/INFY?fcf_yield=5.5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["symbol"], "INFY")
        self.assertEqual(data["equity_fcf_yield_pct"], 5.5)
        self.assertIn("tranches", data)

    def test_api_cortex_garuda_classify(self):
        resp = self.client.post(
            "/api/cortex/garuda/classify",
            json={
                "symbol": "INFY",
                "headline": "Financial Results for the Quarter Ended September 30, 2026",
                "filing_date": "2026-10-10",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["target_pillar_id"], 5)
        self.assertEqual(data["catalyst_type"], "FINANCIAL_EARNINGS")

    def test_api_cortex_sutra_audit(self):
        resp = self.client.post(
            "/api/cortex/sutra/audit",
            json={
                "direct_equities": [{"symbol": "HDFCBANK", "value_inr": 100000}],
                "mutual_funds": [{"scheme_key": "PPFAS_FLEXICAP", "value_inr": 400000}],
                "fixed_income_and_sov": [{"asset_type": "SGB", "value_inr": 100000}],
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["total_portfolio_value_inr"], 0)
        self.assertIn("top_stock_exposures", data)
        self.assertIn("capital_hierarchy", data)


# ==============================================================================
# Anvik Cortex Quantitative & Forensic Valuation Methodologies
# ==============================================================================
class TestDynamicStatutoryYieldWedge(unittest.TestCase):
    def test_expansionary_regime(self):
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
            maintenance_capex_cr=50.0,
            enterprise_value_cr=0.0,
        )
        self.assertEqual(res.statutory_fcf_cr, 0.0)
        self.assertEqual(res.statutory_fcf_yield_pct, 0.0)
        self.assertFalse(res.yield_hurdle_pass)


class TestReverseDcfHurdleDeconstruct(unittest.TestCase):
    def test_solve_implied_growth_moderate(self):
        implied_g = ReverseDcfHurdleDeconstruct.solve_implied_growth(
            current_price=500.0,
            fcf_per_share=25.0,
            wacc_pct=12.0,
            terminal_growth_pct=6.0,
        )
        self.assertGreater(implied_g, 5.0)
        self.assertLess(implied_g, 15.0)

    def test_herculean_hurdle_classification(self):
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
            consensus_or_prior_pat_cr=6000.0,
            post_volume=5000000.0,
            avg_50d_volume=1800000.0,
            post_delivery_pct=64.0,
        )
        self.assertEqual(res.pead_signal, "ACCELERATING_INSTITUTIONAL_DRIFT")
        self.assertGreaterEqual(res.drift_velocity_score, 65.0)
        self.assertEqual(res.momentum_persistence_days, 35)

    def test_exhaustion_reversal_signal(self):
        res = PeadQuantDriftVelocity.evaluate(
            symbol="WEAKCO",
            reported_pat_cr=200.0,
            consensus_or_prior_pat_cr=350.0,
            post_volume=500000.0,
            avg_50d_volume=1000000.0,
            post_delivery_pct=22.0,
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
            rpt_revenue_ratio_pct=28.5,
            promoter_pledge_pct=62.0,
            pledge_velocity_quarterly_delta=4.5,
            board_independence_ratio_pct=25.0,
            contingent_liabilities_to_networth_pct=120.0,
            auditor_qualification_flag=True,
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
            enterprise_value_cr=35000.0,
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
            rpt_revenue_ratio_pct=35.0,
            promoter_pledge_pct=75.0,
            auditor_qualification_flag=True,
        )
        self.assertEqual(eval_res.conviction_quadrant, "HIGH_RISK_DEFICIT")
        self.assertIn("Forensic governance red flags preclude institutional conviction", eval_res.executive_verdict)
from core.brand.moatnomics_house import (
    MOATNOMICS_BRAND_HOUSE,
    MASTER_AI_PROMPT,
    get_system_prompt_context,
    get_content_framework_brief,
)
from core.brand import (
    MOATNOMICS_BRAND_HOUSE as EXPORTED_HOUSE,
    MASTER_AI_PROMPT as EXPORTED_MASTER_PROMPT,
    get_system_prompt_context as exported_context_fn,
    get_content_framework_brief as exported_brief_fn,
)

class TestMoatnomicsBrandHouse(unittest.TestCase):
    def test_brand_house_structure(self):
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["brand_name"], "Moatnomics")
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["tagline"], "Audit the Asset. Protect the Allocator.")
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["creative_territory"], "Less noise, more nuance.")
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["category_descriptor"], "Multi-asset investment research")
        self.assertEqual(
            MOATNOMICS_BRAND_HOUSE["core_promise"],
            "Understand the evidence. Examine the trade-offs. Know what deserves a closer look.",
        )
        self.assertIn("Dual-Mandate", MOATNOMICS_BRAND_HOUSE["core_philosophy"])
        self.assertIn("Clinical, objective, empirical", MOATNOMICS_BRAND_HOUSE["tone_and_voice"])
        self.assertIn("NEVER output prescriptive advice", MOATNOMICS_BRAND_HOUSE["sebi_safe_harbor_rules"])
        self.assertIsInstance(MOATNOMICS_BRAND_HOUSE["forbidden_vocabulary"], list)
        self.assertIn("Multibagger", MOATNOMICS_BRAND_HOUSE["forbidden_vocabulary"])
        self.assertIn("AI Prediction", MOATNOMICS_BRAND_HOUSE["forbidden_vocabulary"])
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["taxonomy"]["Equities"], "Moatnomics Equities")
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["taxonomy"]["Funds"], "Moatnomics Funds")
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["taxonomy"]["Debt"], "Moatnomics Yield")

        # Verify 4 Brand Behaviours, 5 Personality Traits, Editorial Method, Epistemic Tiers, and 4 Franchises
        self.assertEqual(len(MOATNOMICS_BRAND_HOUSE["brand_behaviours"]), 4)
        self.assertEqual(len(MOATNOMICS_BRAND_HOUSE["personality_traits"]), 5)
        self.assertEqual(len(MOATNOMICS_BRAND_HOUSE["editorial_method"]["stages"]), 4)
        self.assertEqual(len(MOATNOMICS_BRAND_HOUSE["editorial_method"]["six_point_quality_gate"]), 6)
        self.assertEqual(
            MOATNOMICS_BRAND_HOUSE["epistemic_tiers"],
            ["VERIFIED FACT", "CALCULATION", "INTERPRETATION", "ASSUMPTION", "UNCERTAINTY"],
        )
        self.assertEqual(len(MOATNOMICS_BRAND_HOUSE["editorial_franchises"]), 4)
        self.assertEqual(len(MOATNOMICS_BRAND_HOUSE["content_frameworks"]), 8)

    def test_system_prompt_context_compilation(self):
        ctx = get_system_prompt_context()
        self.assertIsInstance(ctx, str)
        self.assertIn("You represent Moatnomics", ctx)
        self.assertIn("Less noise, more nuance.", ctx)
        self.assertIn("Dual-Mandate", ctx)
        self.assertIn("NEVER output prescriptive advice", ctx)
        self.assertIn("RESEARCH INTEGRITY", ctx)

        dossier_ctx = get_system_prompt_context(content_type="research_dossiers")
        self.assertIn("CONTENT TYPE FRAMEWORK (RESEARCH_DOSSIERS", dossier_ctx)
        self.assertIn("Countercase:", dossier_ctx)
        self.assertEqual(get_content_framework_brief("non_existent_type"), "")

    def test_package_exports(self):
        self.assertIs(MOATNOMICS_BRAND_HOUSE, EXPORTED_HOUSE)
        self.assertIs(MASTER_AI_PROMPT, EXPORTED_MASTER_PROMPT)
        self.assertIs(get_system_prompt_context, exported_context_fn)
        self.assertIs(get_content_framework_brief, exported_brief_fn)

    def test_multi_asset_dossier_tonality_alignment(self):
        import os
        os.environ["TESTING"] = "1"
        from core.analysis.dossier_bull_bear import synthesize_bull_bear_thesis
        from core.analysis.valuation_radar import compute_valuation_radar
        from core.analysis.daily_stock_ingestion import generate_deterministic_7pillar_report
        from core.analysis.fund_overlap_auditor import synthesize_fund_forensic_narrative
        from core.analysis.debt_engine import generate_executive_primer
        from core.msme.forensic_engine import compute_msme_forensic_dossier

        # 1. Equity Bull/Bear Thesis separates quality from valuation
        bb = synthesize_bull_bear_thesis(
            ticker="INFY",
            fundamentals={"roce": 28.0, "roe": 24.0, "debt_to_equity": 0.08, "pe_ratio": 48.0},
        )
        bull_titles = [p["title"] for p in bb["bull_thesis"]]
        bear_details = " ".join(p["detail"] for p in bb["bear_thesis"])
        self.assertIn("Sustained Return on Capital", bull_titles)
        self.assertIn("competitive position remains credible", bear_details)

        # 2. Valuation Radar summary separates business quality from valuation
        vr = compute_valuation_radar(current_price=2000.0, pe_ratio=42.0, eps=47.6, sales_growth_3y=12.0)
        self.assertIn("leaves less room for execution to disappoint", vr["summary"])

        # 3. Deterministic 7-Pillar Equity Report includes epistemic tags & falsification triggers
        rep_md = generate_deterministic_7pillar_report(
            {"ticker": "INFY", "short_name": "Infosys Ltd", "current_price": 1500.0, "pe_ratio": "25.0"},
            {"scheme_count": 12, "default_roce": 26.0, "default_de": 0.05},
        )
        self.assertIn("[VERIFIED FACT]", rep_md)
        self.assertIn("[CALCULATED METRIC]", rep_md)
        self.assertIn("Falsification & Thesis-Revision Triggers", rep_md)

        # 4. Mutual Fund Dossier narrative uses calm trade-off language
        mf_md = synthesize_fund_forensic_narrative(
            {
                "active_share_pct": 68.0,
                "weighted_moat_score": 76.0,
                "accounting_risk_index": 3.5,
                "margin_of_safety_pct": -8.0,
                "promoter_pledge_exposure_pct": 0.5,
                "portfolio_turnover_ratio_pct": 22.0,
                "benchmark_index": "NIFTY 500 TRI",
                "top_risky_holdings": [],
                "top_quality_holdings": [{"name": "Infosys Ltd"}],
            },
            {
                "scheme_code": "TEST_MF_01",
                "scheme_name": "Test Flexi Cap Fund",
                "category": "Flexi Cap",
                "aum_crores": 12000.0,
                "ter_direct_pct": 0.65,
                "ter_regular_pct": 1.65,
            },
        )
        self.assertIn("Separating constituent quality from valuation", mf_md)
        self.assertIn("reduces terminal value by roughly", mf_md)

        # 5. Corporate Debt Executive Primer explicitly frames higher yield vs credit/liquidity risk
        debt_primer = generate_executive_primer(
            {"instrument_name": "Test Corp 9.25% NCD", "coupon_rate_pct": 9.25, "ytm_pct": 9.25, "seniority_tier": "SENIOR_SECURED", "maturity_date": "2028-06-30"},
            {},
            {},
        )
        self.assertIn("does not automatically make the bond more attractive", debt_primer["fd_comparison"])

        # 6. MSME Forensic Dossier uses measured cash-conversion language
        msme = compute_msme_forensic_dossier({"uin": "UDYAM-MH-01-0000001", "name": "Test Precision Ltd", "sector_name": "Food Processing", "annual_turnover": 60.0})
        self.assertIn("Cash Conversion", msme["pillar_1_working_capital"]["summary"])


if __name__ == "__main__":
    unittest.main()
