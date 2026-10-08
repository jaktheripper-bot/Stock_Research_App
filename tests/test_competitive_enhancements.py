"""Unit and Integration Test Suite for Competitive Differentiation Enhancements.

Tests:
1. Phase 1: Daily Mutual Fund Forensic Rotation Scheduler & AMFI Event Ledger Syndication
2. Phase 2: Equity-to-Debt Contagion Bridge (Credit Contagion Radar & SDI Isolation)
3. Phase 3: Opportunity Terminal Cross-Asset 5-Sleeve Post-Tax Real Yield
4. Phase 4: Autonomous Event Syndication & UI Radar Elements
5. Phase 5: Multi-Asset Forensic Copilot & Institutional PDF Dossier Compilation
"""

import os
os.environ["TESTING"] = "1"

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from web.main import app
from core.db.connection import init_db
from core.db.mutual_funds import seed_default_mutual_funds, get_mutual_fund_scheme, get_fund_forensic_dossier
from core.db.debt import seed_default_debt_securities, get_debt_security_by_isin
from core.db.agent_sessions import record_autonomous_event, get_recent_autonomous_events
from core.analysis.debt_engine import evaluate_equity_cross_contagion, evaluate_5_pillar_credit_posture
from core.reporting.pdf import generate_fund_dossier_pdf, generate_debt_dossier_pdf


class TestCompetitiveEnhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_default_mutual_funds()
        seed_default_debt_securities()
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    def test_credit_contagion_radar_insulated_equity(self):
        """Tests that a strong corporate debt issuer maps to Insulated Equity Moat."""
        sec = get_debt_security_by_isin("INE002A08012")  # Reliance Industries NCD
        self.assertIsNotNone(sec)
        radar = evaluate_equity_cross_contagion(sec)
        self.assertIn(radar["radar_status"], ["INSULATED_EQUITY_MOAT", "MONITORED_EQUITY_DRIFT"])
        self.assertEqual(radar["risk_level"], "LOW")
        self.assertIn("promoter_pledged_pct", radar)
        self.assertTrue(len(radar["radar_indicators"]) >= 3)

    def test_credit_contagion_radar_sdi_ringfenced(self):
        """Tests that a Securitized Debt Instrument (SDI) is classified as Bankruptcy-Remote SPV."""
        sec = get_debt_security_by_isin("IN902SDI0025")  # Grip LeaseX SDI
        self.assertIsNotNone(sec)
        radar = evaluate_equity_cross_contagion(sec)
        self.assertEqual(radar["radar_status"], "BANK_RINGFENCED_SDI")
        self.assertEqual(radar["badge_color"], "#38bdf8")
        self.assertIn("Bankruptcy-Remote", radar["radar_label"])
        self.assertIn("FLDG", radar["radar_indicators"][1]["metric"])

    def test_credit_contagion_radar_active_alert_on_pledge(self):
        """Tests that high promoter pledge triggers ACTIVE_CONTAGION_ALERT."""
        stressed_sec = {
            "isin": "INE999STRESS01",
            "ticker": "STRESSCORP",
            "is_sdi": False,
            "metadata": {"debt_to_equity": 3.8}
        }
        with patch("core.analysis.fundamentals.get_stock_fundamentals") as mock_fund:
            mock_fund.return_value = {
                "pledged_promoter_holding": 28.5,
                "promoter_holding": 42.0,
                "debt_to_equity": 3.8,
                "piotroski_f_score": 2
            }
            # Also clear testing flag temporarily for this targeted assertion
            with patch.dict(os.environ, {"TESTING": ""}):
                radar = evaluate_equity_cross_contagion(stressed_sec)
                self.assertEqual(radar["radar_status"], "ACTIVE_CONTAGION_ALERT")
                self.assertEqual(radar["risk_level"], "HIGH")
                self.assertEqual(radar["badge_color"], "#ef4444")
                self.assertIn("Elevated equity distress", radar["radar_summary"])

    def test_get_debt_securities_for_equity(self):
        """Tests that equity tickers find matching debt securities and subsidiary debentures."""
        from core.db.debt import get_debt_securities_for_equity
        rel_debt = get_debt_securities_for_equity("RELIANCE")
        self.assertGreater(len(rel_debt), 0)
        self.assertTrue(any(d.get("isin") == "INE002A08012" for d in rel_debt))

        tata_debt = get_debt_securities_for_equity("TATAMOTORS")
        self.assertGreater(len(tata_debt), 0)
        self.assertTrue(any("TATACAP" in d.get("ticker", "") for d in tata_debt))

    def test_equity_dossier_pending_renders_linked_debt(self):
        """Tests that uncompiled equity tickers with active debt display listed debt tranches."""
        resp = self.client.get("/dossier/RELIANCE")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("PENDING INSTITUTIONAL COMPILATION", resp.text)
        self.assertIn("Capital Structure: Listed Corporate Debentures", resp.text)
        self.assertIn("INE002A08012", resp.text)
        self.assertIn("/debt/INE002A08012", resp.text)

    def test_phase_3_opportunity_terminal_cross_asset_real_yield(self):
        """Tests Phase 3 cross-asset aggregation, statutory tax waterfalls, and scenario filters."""
        from core.analysis.opportunity_terminal import get_normalized_opportunity_universe, calculate_tax_waterfall

        # 1. Verify multi-asset classes present
        universe = get_normalized_opportunity_universe(tax_slab=30.0, cpi_inflation=4.5)
        asset_classes = {x["asset_class"] for x in universe}
        expected_classes = {"BOND", "REIT", "SGB", "SOVEREIGN", "MF", "EQUITY"}
        for ec in expected_classes:
            self.assertIn(ec, asset_classes)

        # 2. Verify dynamic tax slab calculation (e.g. 10% New Tax Regime vs 30% Standard)
        b_10 = calculate_tax_waterfall(10.0, "BOND", tax_slab=10.0)
        b_30 = calculate_tax_waterfall(10.0, "BOND", tax_slab=30.0)
        self.assertEqual(b_10["net_yield_pct"], 9.0)
        self.assertEqual(b_30["net_yield_pct"], 7.0)

        # 3. Verify scenario filters
        pres = get_normalized_opportunity_universe(persona_filter="capital_preservation")
        self.assertTrue(all(x.get("real_yield_pct", 0) >= 0 for x in pres))

        cash = get_normalized_opportunity_universe(persona_filter="maximum_cashflow")
        self.assertTrue(len(cash) > 0)

        upside = get_normalized_opportunity_universe(persona_filter="asymmetric_upside")
        self.assertTrue(len(upside) > 0)

    def test_multi_asset_copilot_mutual_fund(self):
        """Tests that Copilot correctly grounds context when querying a mutual fund scheme."""
        import asyncio
        from core.agents.copilot.investor_copilot import process_copilot_turn

        async def _run():
            res = await process_copilot_turn(
                conversation_id="TEST-COPILOT-MF-101",
                user_message="Provide a diagnostic look-through summary of this fund.",
                ticker="PPFAS_FLEXICAP_DIR",
                asset_type="mutual_fund"
            )
            self.assertIn(res["status"], ["COMPLETED", "DETERMINISTIC_FALLBACK"])
            self.assertTrue(len(res["response"]) > 50)
            # Response must discuss fund forensics and not single company P/E or Reverse DCF
            self.assertNotIn("company's Margin of Safety", res["response"])

        asyncio.run(_run())

    def test_copilot_mutual_fund_non_advisory_deflection(self):
        """Tests that retail advisory queries on mutual funds yield fund-specific SEBI notices without stock jargon."""
        import asyncio
        from core.agents.copilot.investor_copilot import process_copilot_turn

        async def _run():
            res = await process_copilot_turn(
                conversation_id="TEST-COPILOT-MF-DEFLECT",
                user_message="Should I buy this fund right now?",
                ticker="PPFAS_FLEXICAP_DIR",
                asset_type="mutual_fund"
            )
            self.assertEqual(res["status"], "REGULATORY_DEFLECTED")
            self.assertIn("Section 2(u)", res["response"])
            self.assertIn("Look-Through Forensic Breakdown", res["response"])
            self.assertIn("Distributor Fee Drag", res["response"])
            # MUST NOT mention single stock DCF or the company's balance sheet
            self.assertNotIn("break down the company's Margin of Safety", res["response"])

        asyncio.run(_run())

    def test_copilot_mutual_fund_section_awareness(self):
        """Tests that clicking Copilot within specific sections yields section-anchored diagnostic intelligence."""
        import asyncio
        from core.agents.copilot.investor_copilot import process_copilot_turn

        async def _run():
            # 1. Fee Drag Section
            res_fee = await process_copilot_turn(
                conversation_id="TEST-COPILOT-SEC-FEE",
                user_message="Explain the fee impact.",
                ticker="PPFAS_FLEXICAP_DIR",
                asset_type="mutual_fund",
                section="fee_drag",
                section_label="Intermediary Fee Drag"
            )
            self.assertIn(res_fee["status"], ["COMPLETED", "DETERMINISTIC_FALLBACK"])
            self.assertIn("Fee Drag", res_fee["response"])

            # 2. Active Share Section
            res_as = await process_copilot_turn(
                conversation_id="TEST-COPILOT-SEC-AS",
                user_message="Is this fund hugging the benchmark?",
                ticker="PPFAS_FLEXICAP_DIR",
                asset_type="mutual_fund",
                section="active_share",
                section_label="Active Share & Closet Indexing"
            )
            self.assertIn(res_as["status"], ["COMPLETED", "DETERMINISTIC_FALLBACK"])
            self.assertIn("Active Share", res_as["response"])

            # 3. Look-Through Accounting Risk (ASRI) Section
            res_asri = await process_copilot_turn(
                conversation_id="TEST-COPILOT-SEC-ASRI",
                user_message="What are the accounting red flags?",
                ticker="PPFAS_FLEXICAP_DIR",
                asset_type="mutual_fund",
                section="asri_solvency",
                section_label="Accounting Risk (ASRI)"
            )
            self.assertIn(res_asri["status"], ["COMPLETED", "DETERMINISTIC_FALLBACK"])
            self.assertIn("Accounting Risk", res_asri["response"])

        asyncio.run(_run())

    def test_multi_asset_copilot_debt_security(self):
        """Tests that Copilot correctly grounds context when querying a debt security."""
        import asyncio
        from core.agents.copilot.investor_copilot import process_copilot_turn

        async def _run():
            res = await process_copilot_turn(
                conversation_id="TEST-COPILOT-DEBT-102",
                user_message="Assess the solvency and duration risk of this NCD.",
                ticker="INE002A08012"
            )
            self.assertIn(res["status"], ["COMPLETED", "DETERMINISTIC_FALLBACK"])
            self.assertTrue(len(res["response"]) > 50)

        asyncio.run(_run())

    def test_fund_pdf_generation_and_endpoint(self):
        """Tests compiling and serving institutional PDF dossiers for mutual funds."""
        scheme = get_mutual_fund_scheme("PPFAS_FLEXICAP_DIR")
        dossier = get_fund_forensic_dossier("PPFAS_FLEXICAP_DIR") or {}
        pdf_bytes = generate_fund_dossier_pdf("PPFAS_FLEXICAP_DIR", dossier, scheme)
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        # Test HTTP route
        resp = self.client.get("/api/pdf/fund/PPFAS_FLEXICAP_DIR")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_debt_pdf_generation_and_endpoint(self):
        """Tests compiling and serving institutional PDF dossiers for debt securities."""
        sec = get_debt_security_by_isin("INE002A08012")
        posture = evaluate_5_pillar_credit_posture(sec)
        pdf_bytes = generate_debt_dossier_pdf("INE002A08012", posture, sec)
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        # Test HTTP route
        resp = self.client.get("/api/pdf/debt/INE002A08012")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_web_ui_radar_and_copilot_markup(self):
        """Tests that base template, debt dossier, and fund dossier contain radar and copilot markup."""
        # 1. Base nav contains Agent Radar
        resp_home = self.client.get("/")
        self.assertEqual(resp_home.status_code, 200)
        self.assertIn("Agent Radar", resp_home.text)
        self.assertIn("/admin/audit", resp_home.text)

        # 2. Debt dossier contains Contagion Radar, Copilot trigger, and link to parent equity
        resp_debt = self.client.get("/debt/INE002A08012")
        self.assertEqual(resp_debt.status_code, 200)
        self.assertIn("Credit Contagion Radar", resp_debt.text)
        self.assertIn("/dossier/RELIANCE", resp_debt.text)
        self.assertIn("Forensic Copilot", resp_debt.text)
        self.assertIn("Export PDF", resp_debt.text)
        self.assertIn("copilotModalBackdrop", resp_debt.text)

        # 3. Fund dossier contains Copilot trigger and PDF export
        resp_fund = self.client.get("/funds/PPFAS_FLEXICAP_DIR")
        self.assertEqual(resp_fund.status_code, 200)
        self.assertIn("Forensic Copilot", resp_fund.text)
        self.assertIn("Export PDF Dossier", resp_fund.text)
        self.assertIn("copilotModalBackdrop", resp_fund.text)

    def test_autonomous_event_ledger_integration(self):
        """Tests recording and retrieving autonomous fund and AMFI events."""
        event_id = record_autonomous_event(
            event_type="DAILY_FUND_AUDIT",
            ticker="TEST_FLEXICAP_DIR",
            trigger_source="TEST_SUITE_ROTATION",
            action_taken="7_PILLAR_LOOKTHROUGH_AUDIT",
            summary="Test automated 7-pillar look-through audit completed.",
            metadata={"health_score": 85.0}
        )
        self.assertTrue(event_id.startswith("EVT-"))
        events = get_recent_autonomous_events(limit=5, event_type="DAILY_FUND_AUDIT")
        self.assertTrue(any(e.get("event_id") == event_id for e in events))

    def test_reit_pdf_generation_and_endpoint(self):
        """Tests compiling and serving institutional PDF research dossiers for REITs and InvITs."""
        from core.db.reits import get_reit_by_symbol
        from core.reporting.pdf import generate_reit_dossier_pdf

        reit = get_reit_by_symbol("EMBASSY")
        self.assertIsNotNone(reit)
        pdf_bytes = generate_reit_dossier_pdf("EMBASSY", reit)
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        # Test HTTP route
        resp = self.client.get("/api/pdf/reit/EMBASSY")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_autonomous_surveillance_feed_endpoint(self):
        """Tests public /api/autonomous/events feed endpoint."""
        resp = self.client.get("/api/autonomous/events?limit=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("events"), list)

    def test_bse_watcher_material_filing_event_dispatch(self):
        """Tests BSE watcher event recording on material exchange disclosures."""
        import asyncio
        from core.agents.watchers.bse_watcher import scan_watchlist_bse_announcements

        with patch("core.agents.watchers.bse_watcher.get_watchlist") as mock_wl, \
             patch("core.agents.watchers.bse_watcher.fetch_latest_bse_announcement") as mock_fetch:
            mock_wl.return_value = [{"ticker": "TESTCORP"}]
            mock_fetch.return_value = "Resignation of Statutory Auditor M/s ABC & Co with immediate effect."

            events = asyncio.run(scan_watchlist_bse_announcements())
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["ticker"], "TESTCORP")
            self.assertTrue(events[0]["event_id"].startswith("EVT-"))


if __name__ == "__main__":
    unittest.main()
