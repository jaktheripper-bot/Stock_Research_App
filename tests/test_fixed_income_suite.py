"""Comprehensive Unit and Integration Test Suite for Fixed Income & Sovereign Debt.

Verifies:
1. Fixed-Income Mathematical Core (YTM solver, Macaulay/Modified Duration, Convexity, Rate Shocks).
2. 5-Pillar Credit & Solvency Matrix (Rating Drift, Seniority/ACR, ICR/DSCR, Duration, Recovery/SDI FLDG).
3. AT1 Perpetual loss-absorption write-down regulatory alerts.
4. Database repository operations (dual-binding SQLite/PostgreSQL, CRUD, chronological rating events).
5. Indian Sovereign Par Yield Curve, Macro Corridor, and SDL Fiscal Disparity Matrix.
6. Square-root scaling SVG curve generation and sovereign web/API endpoints.
"""

import os
os.environ["TESTING"] = "1"

import unittest
from datetime import date
from fastapi.testclient import TestClient
from web.main import app

from core.db.debt import (
    save_debt_security,
    get_debt_security_by_isin,
    get_debt_securities_by_ticker,
    get_active_debt_securities,
    record_rating_event,
    get_rating_history,
    seed_default_debt_securities
)
from core.analysis.debt_engine import (
    solve_ytm,
    compute_duration_and_convexity,
    compute_rate_shock_scenarios,
    evaluate_pillar_1_credit_quality,
    evaluate_pillar_2_capital_hierarchy,
    evaluate_pillar_3_cash_flow_solvency,
    evaluate_pillar_4_duration_risk,
    evaluate_pillar_5_recovery_and_pool_quality,
    evaluate_5_pillar_credit_posture,
    calculate_tax_drag_and_real_return
)
from core.analysis.debt_catalogue import (
    get_collation_platform_catalog,
    normalize_debt_security_payload
)
from core.analysis.sovereign_engine import (
    evaluate_sovereign_curve,
    generate_curve_svg_data
)
from core.db.sovereign import (
    DEFAULT_SOVEREIGN_BENCHMARKS,
    save_sovereign_benchmark,
    get_sovereign_yield_curve,
    get_sovereign_sdl_matrix,
    get_macro_monetary_corridor,
    get_historical_sovereign_curves
)


class TestDebtEngineAndRepository(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_default_debt_securities()

    @classmethod
    def tearDownClass(cls):
        from core.db.connection import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM corporate_debt_securities WHERE isin = 'INE999TEST01' OR ticker = 'UNITTESTCORP'")
            cur.execute("DELETE FROM credit_rating_events WHERE isin = 'INE999TEST01' OR ticker = 'UNITTESTCORP'")
            conn.commit()
        except Exception:
            pass
        finally:
            cur.close()
            conn.close()

    # ==========================================================================
    # 1. Fixed-Income Mathematical Core Tests
    # ==========================================================================

    def test_ytm_solver_par_bond(self):
        """A bond priced exactly at par (10,000) must yield exactly its coupon rate."""
        ytm = solve_ytm(
            current_price=10000.0,
            face_value=10000.0,
            coupon_rate_pct=8.50,
            coupon_frequency="ANNUAL",
            time_to_maturity_years=3.0
        )
        self.assertAlmostEqual(ytm, 8.50, delta=0.05)

    def test_ytm_solver_discount_and_premium(self):
        """Discount bond has YTM > coupon; premium bond has YTM < coupon."""
        ytm_discount = solve_ytm(
            current_price=9500.0,
            face_value=10000.0,
            coupon_rate_pct=8.0,
            coupon_frequency="ANNUAL",
            time_to_maturity_years=2.0
        )
        self.assertGreater(ytm_discount, 8.0)

        ytm_premium = solve_ytm(
            current_price=10500.0,
            face_value=10000.0,
            coupon_rate_pct=8.0,
            coupon_frequency="ANNUAL",
            time_to_maturity_years=2.0
        )
        self.assertLess(ytm_premium, 8.0)

    def test_macaulay_and_modified_duration(self):
        """Macaulay duration must be <= maturity; modified duration = Macaulay / (1 + y/k)."""
        dur = compute_duration_and_convexity(
            current_price=10000.0,
            face_value=10000.0,
            coupon_rate_pct=9.0,
            coupon_frequency="ANNUAL",
            time_to_maturity_years=3.0,
            ytm_pct=9.0
        )
        m_dur = dur["macaulay_duration"]
        mod_dur = dur["modified_duration"]
        self.assertLessEqual(m_dur, 3.0)
        self.assertGreater(m_dur, 1.0)
        self.assertAlmostEqual(mod_dur, m_dur / 1.09, delta=0.02)
        self.assertGreater(dur["convexity"], 0.0)

    def test_rate_shock_price_sensitivity(self):
        """Bond price must fall when interest rates rise (negative duration relationship)."""
        scenarios = compute_rate_shock_scenarios(
            current_price=10000.0,
            modified_duration=2.5,
            convexity=8.0,
            rate_shifts_bps=[-100, 0, 100]
        )
        up_rate = next(s for s in scenarios if s["rate_shift_bps"] == 100)
        down_rate = next(s for s in scenarios if s["rate_shift_bps"] == -100)

        self.assertLess(up_rate["pct_price_change"], 0.0)
        self.assertLess(up_rate["estimated_price"], 10000.0)
        self.assertGreater(down_rate["pct_price_change"], 0.0)
        self.assertGreater(down_rate["estimated_price"], 10000.0)

    # ==========================================================================
    # 2. 5-Pillar Credit & Solvency Matrix Tests
    # ==========================================================================

    def test_pillar_1_credit_drift_and_spread(self):
        p1_aaa = evaluate_pillar_1_credit_quality(
            credit_rating="CRISIL AAA",
            rating_history=[{"action_type": "UPGRADE", "outlook": "POSITIVE"}],
            ytm_pct=8.0,
            benchmark_yield=7.10
        )
        self.assertEqual(p1_aaa["score"], 100.0)
        self.assertEqual(p1_aaa["base_symbol"], "AAA")
        self.assertTrue(p1_aaa["is_investment_grade"])

        p1_thin = evaluate_pillar_1_credit_quality(
            credit_rating="CARE BBB",
            rating_history=[],
            ytm_pct=7.50,
            benchmark_yield=7.10
        )
        self.assertIsNotNone(p1_thin["warning"])
        self.assertIn("Uncompensated Credit Risk", p1_thin["warning"])

    def test_pillar_2_seniority_and_at1_warning(self):
        p2_sec = evaluate_pillar_2_capital_hierarchy("SENIOR_SECURED", asset_cover_ratio=1.40)
        self.assertEqual(p2_sec["score"], 100.0)
        self.assertFalse(p2_sec["covenant_breach"])
        self.assertIsNone(p2_sec["critical_warning"])

        p2_breach = evaluate_pillar_2_capital_hierarchy("SENIOR_SECURED", asset_cover_ratio=0.85)
        self.assertTrue(p2_breach["covenant_breach"])
        self.assertLess(p2_breach["score"], 70.0)

        p2_at1 = evaluate_pillar_2_capital_hierarchy("PERPETUAL_AT1")
        self.assertIsNotNone(p2_at1["critical_warning"])
        self.assertIn("Point of Non-Viability", p2_at1["critical_warning"])
        self.assertIn("Yes Bank", p2_at1["critical_warning"])
        self.assertEqual(p2_at1["score"], 10.0)

    def test_pillar_3_cash_flow_solvency(self):
        p3_good = evaluate_pillar_3_cash_flow_solvency({
            "interest_coverage": 4.5,
            "dscr": 1.45,
            "net_debt_to_ebitda": 1.8
        })
        self.assertGreaterEqual(p3_good["score"], 85.0)

        p3_bad = evaluate_pillar_3_cash_flow_solvency({
            "interest_coverage": 1.2,
            "dscr": 0.95
        })
        self.assertLess(p3_bad["score"], 60.0)
        self.assertTrue(any("Distressed ICR" in n for n in p3_bad["notes"]))

    def test_pillar_4_duration_posture(self):
        p4_short = evaluate_pillar_4_duration_risk(0.8, 0.75, 1.0)
        self.assertEqual(p4_short["duration_posture"], "ULTRA_LOW_DURATION")

        p4_long = evaluate_pillar_4_duration_risk(5.5, 5.0, 7.0)
        self.assertEqual(p4_long["duration_posture"], "LONG_DURATION")

    def test_pillar_5_sdi_pool_evaluation(self):
        p5_sdi = evaluate_pillar_5_recovery_and_pool_quality(
            is_sdi=True,
            fldg_pct=5.0,
            originator="Test NBFC"
        )
        self.assertEqual(p5_sdi["score"], 90.0)
        self.assertIn("credit enhancement", p5_sdi["details"]["fldg_status"].lower())

    def test_composite_5_pillar_synthesis(self):
        rel = get_debt_security_by_isin("INE002A08012")
        self.assertIsNotNone(rel)
        posture_rel = evaluate_5_pillar_credit_posture(rel)
        self.assertEqual(posture_rel["posture"], "INSTITUTIONAL_PRIME")
        self.assertGreaterEqual(posture_rel["composite_score"], 80.0)

        at1 = get_debt_security_by_isin("INE090A08UD5")
        self.assertIsNotNone(at1)
        posture_at1 = evaluate_5_pillar_credit_posture(at1)
        self.assertIn(posture_at1["posture"], ["SPECULATIVE_YIELD", "DISTRESSED_VULNERABLE"])
        self.assertTrue(len(posture_at1["warnings"]) > 0)
        self.assertTrue(any("AT1" in w for w in posture_at1["warnings"]))

    # ==========================================================================
    # 3. Database Repository CRUD Tests
    # ==========================================================================

    def test_save_and_retrieve_debt_security(self):
        test_sec = {
            "isin": "INE999TEST01",
            "ticker": "UNITTESTCORP",
            "scrip_code": "939999",
            "series": "N1",
            "instrument_name": "Unit Test Corp 9.50% Secured NCD 2027",
            "instrument_type": "NCD",
            "seniority_tier": "SENIOR_SECURED",
            "face_value": 10000.0,
            "coupon_rate_pct": 9.50,
            "coupon_frequency": "ANNUAL",
            "issue_date": "2024-01-01",
            "maturity_date": "2027-01-01",
            "credit_rating": "CRISIL AA",
            "credit_rating_agency": "CRISIL",
            "asset_cover_ratio": 1.30,
            "is_listed": True,
            "exchange": "BSE",
            "is_sdi": False,
            "last_traded_price": 10000.0,
            "ytm_pct": 9.50,
            "macaulay_duration_years": 2.2,
            "modified_duration_years": 2.0,
            "metadata": {"test_field": "verified"}
        }
        self.assertTrue(save_debt_security(test_sec))

        retrieved = get_debt_security_by_isin("INE999TEST01")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["ticker"], "UNITTESTCORP")
        self.assertEqual(retrieved["coupon_rate_pct"], 9.50)
        self.assertEqual(retrieved["metadata"].get("test_field"), "verified")

        by_ticker = get_debt_securities_by_ticker("UNITTESTCORP")
        self.assertEqual(len(by_ticker), 1)

    def test_record_and_retrieve_rating_events(self):
        event = {
            "isin": "INE999TEST01",
            "ticker": "UNITTESTCORP",
            "rating_agency": "CRISIL",
            "rating_symbol": "AA+",
            "outlook": "POSITIVE",
            "action_type": "UPGRADE",
            "event_date": "2024-06-15",
            "action_rationale": "Deleveraging and stronger operational cash flows."
        }
        self.assertTrue(record_rating_event(event))

        history = get_rating_history("INE999TEST01")
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["action_type"], "UPGRADE")
        self.assertEqual(history[0]["rating_symbol"], "AA+")

    def test_institutional_narrative_and_primer_synthesis(self):
        """Verifies that evaluate_5_pillar_credit_posture generates comprehensive narrative dossiers."""
        sec = get_debt_security_by_isin("INE414G07GE7")
        self.assertIsNotNone(sec)

        posture = evaluate_5_pillar_credit_posture(sec)

        self.assertIn("primer", posture)
        self.assertIn("What Am I Looking At?", posture["primer"]["title"])
        self.assertIn("summary", posture["primer"])
        self.assertIn("fd_comparison", posture["primer"])

        self.assertIn("issuer_profile", posture)
        self.assertEqual(posture["issuer_profile"]["ticker"], "MUTHOOTFIN")
        self.assertIn("description", posture["issuer_profile"])
        self.assertIn("gnpa_pct", posture["issuer_profile"])

        self.assertIn("investment_thesis", posture)
        self.assertGreaterEqual(len(posture["investment_thesis"]["the_good"]), 2)
        self.assertGreaterEqual(len(posture["investment_thesis"]["the_bad"]), 2)
        self.assertGreaterEqual(len(posture["investment_thesis"]["the_ugly"]), 1)

        self.assertIn("tax_drag_schedule", posture)
        self.assertIn("benchmark_30pct_post_tax_yield", posture["tax_drag_schedule"])
        self.assertIn("slab_breakdown", posture["tax_drag_schedule"])

        self.assertIn("collated_sources", posture)
        source_names = [s["name"] for s in posture["collated_sources"]]
        self.assertIn("Wint Wealth", source_names)
        self.assertIn("BSE Debt Market", source_names)

        for p_key in ["p1_credit_quality", "p2_capital_hierarchy", "p3_solvency", "p4_duration", "p5_recovery"]:
            p = posture["pillars"][p_key]
            self.assertIn("educational_overview", p, f"{p_key} missing educational_overview")
            self.assertIn("institutional_analysis", p, f"{p_key} missing institutional_analysis")
            self.assertIn("plain_english_takeaway", p, f"{p_key} missing plain_english_takeaway")

    def test_tax_drag_calculator_accuracy(self):
        """Verifies tax drag calculations against known tax slabs."""
        res = calculate_tax_drag_and_real_return(ytm_pct=10.0, inflation_pct=5.5)
        self.assertEqual(res["nominal_ytm_pct"], 10.0)
        self.assertAlmostEqual(res["benchmark_30pct_post_tax_yield"], 6.88, delta=0.05)
        self.assertAlmostEqual(res["benchmark_30pct_real_return"], 1.38, delta=0.05)

    def test_debt_crawler_collation_catalog(self):
        """Verifies supported platform directory for Indian alternative fixed-income collation."""
        catalog = get_collation_platform_catalog()
        platforms = catalog["platforms"]
        self.assertIn("WINT_WEALTH", platforms)
        self.assertIn("GOLDEN_PI", platforms)
        self.assertIn("BSE_DEBT", platforms)
        self.assertIn("GRIP_INVEST", platforms)

        raw = {
            "isin": "INE123TEST99",
            "ticker": "TESTCORP",
            "coupon_rate_pct": 10.5,
            "ytm_pct": 10.5,
            "maturity_date": "2027-12-31",
            "seniority_tier": "SENIOR_SECURED",
            "credit_rating": "CRISIL AA"
        }
        normalized = normalize_debt_security_payload(raw)
        self.assertEqual(normalized["isin"], "INE123TEST99")
        self.assertEqual(normalized["ytm_pct"], 10.5)
        self.assertGreater(normalized["macaulay_duration_years"], 0.0)


class TestSovereignEngineAndTerminal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for b in DEFAULT_SOVEREIGN_BENCHMARKS:
            save_soVEREIGN_benchmark = save_sovereign_benchmark(b)
        cls.client = TestClient(app)

    def test_sovereign_yield_curve_benchmarks(self):
        """Verifies 16 statutory sovereign benchmarks are retrieved from repository."""
        curve = get_sovereign_yield_curve()
        self.assertGreaterEqual(len(curve), 16)
        tenors = {item["tenor_label"] for item in curve}
        self.assertIn("91D_TBILL", tenors)
        self.assertIn("182D_TBILL", tenors)
        self.assertIn("364D_TBILL", tenors)
        self.assertIn("2Y_GSEC", tenors)
        self.assertIn("5Y_GSEC", tenors)
        self.assertIn("5Y_SGRB", tenors)
        self.assertIn("10Y_GSEC", tenors)
        self.assertIn("10Y_SGRB", tenors)
        self.assertIn("10Y_SDL", tenors)
        self.assertIn("50Y_GSEC", tenors)

    def test_sdl_fiscal_matrix(self):
        """Verifies State Development Loan benchmarks across 10 borrowing states."""
        sdls = get_sovereign_sdl_matrix()
        self.assertGreaterEqual(len(sdls), 10)
        state_codes = {s["state_code"] for s in sdls}
        self.assertIn("MH", state_codes)
        self.assertIn("GJ", state_codes)
        self.assertIn("KA", state_codes)
        self.assertIn("TN", state_codes)
        self.assertIn("UP", state_codes)
        self.assertIn("WB", state_codes)
        self.assertIn("PB", state_codes)

        # Spreads should be sorted ascending
        spreads = [s["spread_over_gsec_bps"] for s in sdls]
        self.assertEqual(spreads, sorted(spreads))

    def test_macro_monetary_corridor(self):
        """Verifies RBI Policy corridor and MOSPI inflation rates."""
        corridor = get_macro_monetary_corridor()
        self.assertIn("repo_rate", corridor)
        self.assertIn("sdf_rate", corridor)
        self.assertIn("msf_rate", corridor)
        self.assertIn("cpi_inflation", corridor)
        self.assertEqual(corridor["repo_rate"]["value"], 6.50)
        self.assertEqual(corridor["sdf_rate"]["value"], 6.25)
        self.assertEqual(corridor["msf_rate"]["value"], 6.75)
        self.assertEqual(corridor["cpi_inflation"]["value"], 3.65)

    def test_svg_chart_coordinate_generation(self):
        """Verifies mathematical square-root scaling and SVG path construction."""
        hist = get_historical_sovereign_curves()
        chart = generate_curve_svg_data(hist, width=820, height=340)
        self.assertEqual(chart["width"], 820)
        self.assertEqual(chart["height"], 340)
        self.assertIn("current", chart["series"])
        self.assertIn("one_month_ago", chart["series"])
        self.assertIn("one_year_ago", chart["series"])

        current_path = chart["series"]["current"]["path_d"]
        self.assertTrue(current_path.startswith("M "))
        self.assertIn(" L ", current_path)

        for pt in chart["series"]["current"]["points"]:
            self.assertGreaterEqual(pt["cx"], chart["pad_left"])
            self.assertLessEqual(pt["cx"], chart["width"] - chart["pad_right"])
            self.assertGreaterEqual(pt["cy"], chart["pad_top"])
            self.assertLessEqual(pt["cy"], chart["height"] - chart["pad_bottom"])

    def test_evaluate_sovereign_curve(self):
        """Verifies the complete analytical payload for the Sovereign Terminal."""
        analytics = evaluate_sovereign_curve()
        self.assertEqual(analytics["benchmark_10y_gsec"], 7.12)
        self.assertEqual(analytics["risk_free_short_tbill"], 6.84)
        self.assertEqual(analytics["term_spread_bps"], 28.0)
        self.assertEqual(analytics["real_10y_yield"], 3.47)
        self.assertEqual(analytics["greenium_bps"], 4.0)
        self.assertGreaterEqual(len(analytics["curve_points"]), 16)
        self.assertGreaterEqual(len(analytics["sdl_matrix"]), 10)
        self.assertGreaterEqual(len(analytics["macro_insights"]), 3)

        for insight in analytics["macro_insights"]:
            self.assertNotIn("plain-english", insight.lower())
            self.assertNotIn("for dummies", insight.lower())

    def test_web_sovereign_page_renders_cleanly(self):
        """Verifies GET /sovereign renders 200 OK with all terminal modules."""
        resp = self.client.get("/sovereign")
        self.assertEqual(resp.status_code, 200)
        html = resp.text
        self.assertIn("Indian Sovereign Debt & Macro Terminal", html)
        self.assertIn("RBI Monetary Policy Corridor", html)
        self.assertIn("sovereignSvg", html)
        self.assertIn("State Development Loan (SDL) Fiscal Disparity Matrix", html)
        self.assertIn("RBI Retail Direct", html)
        self.assertIn("50Y_GSEC", html)
        self.assertIn("10Y_SGRB", html)
        self.assertIn("Maharashtra", html)
        self.assertIn("Punjab", html)

    def test_api_sovereign_curve_endpoint(self):
        """Verifies GET /api/sovereign/curve returns 200 OK and valid JSON."""
        resp = self.client.get("/api/sovereign/curve")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["benchmark_10y_gsec"], 7.12)
        self.assertIn("svg_chart", data)
        self.assertIn("sdl_matrix", data)

    def test_api_sovereign_sdl_matrix_endpoint(self):
        """Verifies GET /api/sovereign/sdl-matrix returns 200 OK."""
        resp = self.client.get("/api/sovereign/sdl-matrix")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("sdl_matrix", data)
        self.assertGreaterEqual(data["count"], 10)

    def test_api_sovereign_macro_endpoint(self):
        """Verifies GET /api/sovereign/macro returns 200 OK."""
        resp = self.client.get("/api/sovereign/macro")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("macro_corridor", data)
        self.assertIn("repo_rate", data["macro_corridor"])
        self.assertEqual(data["macro_corridor"]["repo_rate"]["value"], 6.50)


if __name__ == "__main__":
    unittest.main()
