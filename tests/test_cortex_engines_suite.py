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


if __name__ == "__main__":
    unittest.main()

