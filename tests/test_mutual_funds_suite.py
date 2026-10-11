"""
Consolidated Mutual Funds & Look-Through Forensic Suite
========================================================
Unifies:
1. Base Mutual Fund 6-Pillar Engine & Active Share Diagnostics
2. Marquee Top 50 AMFI Schemes Expansion & Category Distribution
3. Curated Top 100 Institutional Universe & Look-Through Verification
4. 7-Pillar Forensic Look-Through, Overlap Auditor & On-Demand Ingestion
"""
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

os.environ["TESTING"] = "1"

from web.main import app
from core.db.connection import init_db
from core.db.mutual_funds import (
    seed_default_mutual_funds,
    get_active_mutual_funds,
    get_mutual_fund_scheme,
    get_scheme_holdings,
    get_schemes_by_holding,
    save_fund_forensic_dossier,
    get_fund_forensic_dossier,
    get_featured_daily_fund_dossier,
    get_next_fund_for_daily_audit,
)
from core.analysis.mutual_funds_engine import (
    calculate_active_share,
    calculate_portfolio_overlap,
    calculate_fee_drag,
    evaluate_dual_sleeve_lookthrough,
    evaluate_mutual_fund_comprehensive,
)
from core.analysis.fund_overlap_auditor import (
    compute_fund_forensic_lookthrough,
    parse_stock_report_health_matrix,
    synthesize_fund_forensic_narrative,
    audit_single_fund_daily,
    calculate_deep_dive_credit_cost,
    ensure_scheme_and_holdings_exist,
    create_async_fund_audit_task,
    run_async_fund_audit_job,
    get_fund_audit_task_status,
)

NEW_19_SCHEME_CODES = [
    # Flexi Cap (5)
    "JM_FLEXICAP_DIR",
    "DSP_FLEXICAP_DIR",
    "CANARA_ROBECO_FLEXICAP_DIR",
    "FRANKLIN_FLEXICAP_DIR",
    "EDELWEISS_FLEXICAP_DIR",
    # Mid Cap (5)
    "NIPPON_GROWTH_MIDCAP_DIR",
    "SBI_MAGNUM_MIDCAP_DIR",
    "EDELWEISS_MIDCAP_DIR",
    "MIRAE_MIDCAP_DIR",
    "QUANT_MIDCAP_DIR",
    # Small Cap (5)
    "QUANT_SMALLCAP_DIR",
    "AXIS_SMALLCAP_DIR",
    "KOTAK_SMALLCAP_DIR",
    "CANARA_ROBECO_SMALLCAP_DIR",
    "DSP_SMALLCAP_DIR",
    # Large & Mid Cap (4)
    "HDFC_LARGEMID_DIR",
    "KOTAK_EQUITY_OPP_DIR",
    "MIRAE_LARGEMID_DIR",
    "CANARA_ROBECO_EMERGING_DIR",
]

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


# ==============================================================================
# 1. Base Mutual Fund Engine & Look-Through Diagnostics
# ==============================================================================
class TestMutualFundEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
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
        self.assertFalse(lt["has_sufficient_coverage"])
        self.assertIsNone(lt["composite_health_score"])
        self.assertEqual(lt["health_posture"], "COVERAGE_PENDING")

        with patch("core.db.reports.get_report_by_ticker") as mock_rep:
            mock_rep.return_value = {"report_text": "### Health Matrix\nVerified 7-pillar report"}
            unlocked_dossier = evaluate_mutual_fund_comprehensive("PPFAS_FLEXICAP_DIR")
            unlocked_lt = unlocked_dossier["lookthrough"]
            self.assertTrue(unlocked_lt["has_sufficient_coverage"])
            self.assertIsNotNone(unlocked_lt["composite_health_score"])
            self.assertGreaterEqual(unlocked_lt["composite_health_score"], 80.0)
            self.assertEqual(unlocked_lt["health_posture"], "INSTITUTIONAL_ALPHA")

        sleeve = lt["sleeve_breakdown"]
        self.assertGreater(sleeve["equity_weight_pct"], 60.0)
        self.assertGreater(sleeve["debt_weight_pct"], 5.0)

        ashare = dossier["active_share"]
        self.assertGreaterEqual(ashare["active_share_pct"], 60.0)
        self.assertEqual(ashare["posture"], "TRUE_ACTIVE_ALPHA")
        self.assertFalse(ashare["is_closet_indexer"])

    def test_closet_indexing_detection(self):
        from core.analysis.mutual_funds_engine import BENCHMARK_PROXIES
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

        warnings_str = " ".join(lt["warnings"])
        self.assertIn("AUM Capacity Trap", warnings_str)


# ==============================================================================
# 2. Top 50 AMFI Schemes Expansion
# ==============================================================================
class TestMutualFundTop50Expansion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.seeded_count = seed_default_mutual_funds()
        cls.client = TestClient(app)

    def test_seeded_count_is_fifty(self):
        self.assertGreaterEqual(self.seeded_count, 50)

    def test_all_nineteen_new_schemes_exist_in_db(self):
        for code in NEW_19_SCHEME_CODES:
            scheme = get_mutual_fund_scheme(code)
            self.assertIsNotNone(scheme, f"Scheme {code} not found in database")
            self.assertEqual(scheme["scheme_code"], code)
            self.assertGreater(float(scheme.get("aum_crores", 0)), 0, f"Scheme {code} has 0 AUM")
            self.assertGreater(float(scheme.get("nav", 0)), 0, f"Scheme {code} has 0 NAV")

    def test_all_nineteen_new_schemes_have_holdings(self):
        for code in NEW_19_SCHEME_CODES:
            holdings = get_scheme_holdings(code)
            self.assertGreaterEqual(len(holdings), 5, f"Scheme {code} has fewer than 5 holdings")
            total_weight = sum(float(h.get("weight_pct", 0.0)) for h in holdings)
            self.assertGreaterEqual(total_weight, 35.0, f"Scheme {code} total holding weight too low")

    def test_category_distribution_of_expanded_schemes(self):
        categories = {
            "Flexi Cap Fund": 0,
            "Mid Cap Fund": 0,
            "Small Cap Fund": 0,
            "Large & Mid Cap Fund": 0,
        }
        for code in NEW_19_SCHEME_CODES:
            scheme = get_mutual_fund_scheme(code)
            cat = scheme.get("category")
            if cat in categories:
                categories[cat] += 1

        self.assertEqual(categories["Flexi Cap Fund"], 5)
        self.assertEqual(categories["Mid Cap Fund"], 5)
        self.assertEqual(categories["Small Cap Fund"], 5)
        self.assertEqual(categories["Large & Mid Cap Fund"], 4)

    def test_forensic_lookthrough_on_representative_new_schemes(self):
        representatives = [
            "JM_FLEXICAP_DIR",
            "NIPPON_GROWTH_MIDCAP_DIR",
            "QUANT_SMALLCAP_DIR",
            "MIRAE_LARGEMID_DIR"
        ]
        with patch("core.analysis.fund_overlap_auditor.get_report_by_ticker") as mock_rep:
            mock_rep.return_value = {
                "report_text": "### Health Matrix\nMoat: Wide\nGovernance: Clean\nValuation: Undervalued\nBalance Sheet: Debt-Free\n"
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

    def test_portfolio_overlap_between_new_and_existing_schemes(self):
        holdings_ppfas = get_scheme_holdings("PPFAS_FLEXICAP_DIR")
        holdings_jm = get_scheme_holdings("JM_FLEXICAP_DIR")

        overlap = calculate_portfolio_overlap(holdings_ppfas, holdings_jm, "PPFAS", "JM")
        self.assertIn("overlap_pct", overlap)
        self.assertIn("shared_holdings", overlap)
        self.assertGreater(overlap["overlap_pct"], 0.0)
        self.assertTrue(any(s["identifier"] == "HDFCBANK" for s in overlap["shared_holdings"]))

    def test_web_routes_for_new_schemes(self):
        res = self.client.get("/funds/JM_FLEXICAP_DIR")
        self.assertEqual(res.status_code, 200)
        self.assertIn("JM Flexicap Fund", res.text)

        res_api = self.client.get("/api/funds/dossier/QUANT_SMALLCAP_DIR")
        self.assertEqual(res_api.status_code, 200)
        data = res_api.json()
        self.assertEqual(data.get("scheme_code"), "QUANT_SMALLCAP_DIR")
        self.assertIn("composite_health_score", data)


# ==============================================================================
# 3. Top 100 Institutional Universe Expansion
# ==============================================================================
class TestMutualFundTop100Expansion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.seeded_count = seed_default_mutual_funds()
        cls.client = TestClient(app)

    def test_seeded_count_is_one_hundred(self):
        self.assertEqual(self.seeded_count, 100)
        active = get_active_mutual_funds()
        self.assertGreaterEqual(len(active), 100)

    def test_all_fifty_new_schemes_exist_in_db(self):
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
        for code in NEW_50_SCHEME_CODES:
            holdings = get_scheme_holdings(code)
            self.assertGreaterEqual(len(holdings), 5, f"Scheme {code} has fewer than 5 holdings")
            total_weight = sum(float(h.get("weight_pct", 0.0)) for h in holdings)
            self.assertGreaterEqual(total_weight, 35.0, f"Scheme {code} total holding weight too low")

    def test_category_distribution_of_expanded_universe(self):
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
        holdings_tech = get_scheme_holdings("ICICI_TECH_DIR")
        holdings_digital = get_scheme_holdings("TATA_DIGITAL_DIR")

        overlap = calculate_portfolio_overlap(holdings_tech, holdings_digital, "ICICI Tech", "Tata Digital")
        self.assertIn("overlap_pct", overlap)
        self.assertIn("shared_holdings", overlap)
        self.assertGreaterEqual(overlap["overlap_pct"], 30.0)
        self.assertTrue(any(s["identifier"] == "INFY" for s in overlap["shared_holdings"]))
        self.assertTrue(any(s["identifier"] == "TCS" for s in overlap["shared_holdings"]))

    def test_web_routes_for_top100_schemes(self):
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


# ==============================================================================
# 4. 7-Pillar Forensic Look-Through Engine & Auditor
# ==============================================================================
class TestFundForensicAuditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_default_mutual_funds()
        cls.client = TestClient(app)

    def test_expanded_universe_seeding(self):
        funds = get_active_mutual_funds()
        self.assertGreaterEqual(len(funds), 30)
        codes = [f["scheme_code"] for f in funds]
        self.assertIn("PPFAS_FLEXICAP_DIR", codes)
        self.assertIn("HDFC_MIDCAP_DIR", codes)
        self.assertIn("MIRAE_LARGECAP_DIR", codes)
        self.assertIn("HDFC_FLEXICAP_DIR", codes)
        self.assertIn("KOTAK_FLEXICAP_DIR", codes)
        self.assertIn("ICICI_BLUECHIP_DIR", codes)
        self.assertIn("NIPPON_SMALLCAP_DIR", codes)
        self.assertIn("SBI_CONTRA_DIR", codes)
        self.assertIn("QUANT_ELSS_DIR", codes)

    def test_health_matrix_parsing(self):
        sample_report = """
# INSTITUTIONAL EQUITY RESEARCH: HDFCBANK

### Health Matrix
- Macro: Stable
- Moat: Wide
- Governance: Clean
- Diagnostic: Neutral
- Valuation: Undervalued
- Balance Sheet: Debt-Free
- Capital Allocation: Disciplined

## Pillar 1: Macro-Economic
"""
        matrix = parse_stock_report_health_matrix(sample_report)
        self.assertEqual(matrix["moat"], "Wide")
        self.assertEqual(matrix["governance"], "Clean")
        self.assertEqual(matrix["valuation"], "Undervalued")
        self.assertEqual(matrix["balance_sheet"], "Debt-Free")

    def test_compute_ppfas_lookthrough(self):
        metrics = compute_fund_forensic_lookthrough("PPFAS_FLEXICAP_DIR")
        self.assertEqual(metrics["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertFalse(metrics["has_sufficient_coverage"])
        self.assertIsNone(metrics["composite_health_score"])
        self.assertGreaterEqual(metrics["weighted_moat_score"], 70.0)
        self.assertLessEqual(metrics["accounting_risk_index"], 5.0)
        self.assertGreaterEqual(metrics["active_share_pct"], 60.0)

        with patch("core.analysis.fund_overlap_auditor.get_report_by_ticker") as mock_rep:
            mock_rep.return_value = {
                "report_text": "### Health Matrix\nMoat: Wide\nGovernance: Clean\nValuation: Undervalued\nBalance Sheet: Debt-Free\n"
            }
            unlocked_metrics = compute_fund_forensic_lookthrough("PPFAS_FLEXICAP_DIR")
            self.assertTrue(unlocked_metrics["has_sufficient_coverage"])
            self.assertIsNotNone(unlocked_metrics["composite_health_score"])
            self.assertGreaterEqual(unlocked_metrics["composite_health_score"], 75.0)

    def test_dossier_persistence_and_featured_retrieval(self):
        mock_dossier = {
            "scheme_code": "PPFAS_FLEXICAP_DIR",
            "dossier_text": "# TEST INSTITUTIONAL DOSSIER\nMandate integrity verified.",
            "composite_health_score": 85.0,
            "weighted_moat_score": 86.5,
            "accounting_risk_index": 0.0,
            "margin_of_safety_pct": 5.2,
            "promoter_pledge_exposure_pct": 0.0,
            "active_share_pct": 68.0,
            "top_risky_holdings": [],
            "top_quality_holdings": [{"name": "HDFC Bank Ltd", "identifier": "HDFCBANK", "weight_pct": 8.4}],
            "audited_by": "Test_Forensic_Auditor"
        }
        saved = save_fund_forensic_dossier(mock_dossier)
        self.assertTrue(saved)

        retrieved = get_fund_forensic_dossier("PPFAS_FLEXICAP_DIR")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertEqual(retrieved["composite_health_score"], 85.0)
        self.assertEqual(retrieved["weighted_moat_score"], 86.5)

        featured = get_featured_daily_fund_dossier()
        self.assertIsNotNone(featured)
        self.assertEqual(featured["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertIn("scheme_name", featured)

    def test_rotation_queue_selection(self):
        next_fund = get_next_fund_for_daily_audit()
        self.assertIsNotNone(next_fund)
        self.assertIn("scheme_code", next_fund)

    def test_web_routes_and_api(self):
        resp = self.client.get("/funds")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Featured Daily Forensic", resp.text)

        resp_dos = self.client.get("/funds/PPFAS_FLEXICAP_DIR", headers={"x-unlock-preview": "1"})
        self.assertEqual(resp_dos.status_code, 200)
        self.assertIn("7-Pillar Equity Look-Through", resp_dos.text)
        self.assertIn("Weighted Moat Index", resp_dos.text)

        resp_api = self.client.get("/api/funds/dossier/PPFAS_FLEXICAP_DIR", headers={"x-unlock-preview": "1"})
        self.assertEqual(resp_api.status_code, 200)
        data = resp_api.json()
        self.assertEqual(data["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertIn("weighted_moat_score", data)
        self.assertIn("accounting_risk_index", data)

    def test_deep_dive_quote_and_cost(self):
        quote = calculate_deep_dive_credit_cost("PPFAS_FLEXICAP_DIR")
        self.assertEqual(quote["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertGreaterEqual(quote["total_holdings_count"], 10)
        self.assertEqual(quote["layer1_credits"], 1)
        self.assertGreaterEqual(quote["uncached_count"], 1)
        self.assertEqual(quote["total_credits_for_full_audit"], 1 + quote["layer2_deep_dive_credits"])

        resp = self.client.get("/api/funds/deep-dive-quote/PPFAS_FLEXICAP_DIR")
        self.assertEqual(resp.status_code, 200)
        q_data = resp.json()
        self.assertEqual(q_data["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertIn("layer2_deep_dive_credits", q_data)
        self.assertIn("uncached_stocks", q_data)

    def test_on_demand_audit_api_and_status(self):
        resp = self.client.post("/api/funds/on-demand-audit", json={"scheme_code": "PPFAS_FLEXICAP_DIR"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        task_id = data["task_id"]
        self.assertIn("TASK-FUND-PPFAS_FLEXICAP_DIR", task_id)

        resp_status = self.client.get(f"/api/funds/audit-status/{task_id}")
        self.assertEqual(resp_status.status_code, 200)
        s_data = resp_status.json()
        self.assertIn(s_data["status"], ["QUEUED", "PROCESSING", "COMPLETED"])
        self.assertIn("progress_pct", s_data)

    def test_unlisted_fund_ingestion_and_dossier_markup(self):
        scheme = ensure_scheme_and_holdings_exist("122639")
        self.assertIsNotNone(scheme)
        self.assertEqual(scheme["scheme_code"], "122639")

        resp_dir = self.client.get("/funds")
        self.assertEqual(resp_dir.status_code, 200)
        self.assertIn("Audit Any Scheme Outside Top 50", resp_dir.text)
        self.assertIn("onDemandSchemeInput", resp_dir.text)
        self.assertIn("Alert me on desktop when complete", resp_dir.text)

        resp_dos = self.client.get("/funds/PPFAS_FLEXICAP_DIR", headers={"x-unlock-preview": "1"})
        self.assertEqual(resp_dos.status_code, 200)
        self.assertIn("Deep-Dive Stock Forensic Audit Option", resp_dos.text)
        self.assertIn("Layer 1 Active (1 Credit)", resp_dos.text)
        self.assertIn("Initiate Deep-Dive Audit", resp_dos.text)


if __name__ == "__main__":
    unittest.main()
