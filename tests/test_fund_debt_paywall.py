"""Mutual Fund and Corporate Debt Deep Dive paywall: dossier pages, APIs, PDFs and the Forensic Desk."""
import asyncio
import os

os.environ["TESTING"] = "1"

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from core.agents.copilot.forensic_desk import (
    build_unlock_notice,
    detect_gated_topic,
    process_forensic_desk_turn,
)
from core.db import init_db
from core.reporting.pdf import generate_debt_dossier_pdf, generate_fund_dossier_pdf

UNLOCK = {"x-unlock-preview": "1"}
FUND = "PPFAS_FLEXICAP_DIR"
DEBT = "INE002A08012"


def _pdf_text(pdf: bytes) -> str:
    try:
        import pymupdf as fitz_mod
    except ImportError:
        import fitz as fitz_mod
    doc = fitz_mod.open(stream=pdf, filetype="pdf")
    text = "".join(p.get_text() for p in doc)
    doc.close()
    return text


class TestTopicDetection(unittest.TestCase):
    def test_fund_gated_topics(self):
        self.assertIsNotNone(detect_gated_topic("MUTUAL_FUND", None, "what is the moat score?"))
        self.assertIsNotNone(detect_gated_topic("MUTUAL_FUND", "asri_solvency", "tell me more"))
        self.assertIsNotNone(detect_gated_topic("MUTUAL_FUND", None, "any promoter pledge exposure?"))

    def test_fund_free_topics_not_gated(self):
        self.assertIsNone(detect_gated_topic("MUTUAL_FUND", "fee_drag", "explain the fee drag"))
        self.assertIsNone(detect_gated_topic("MUTUAL_FUND", None, "give me a summary"))
        self.assertIsNone(detect_gated_topic("MUTUAL_FUND", "active_share", "is it a closet indexer?"))

    def test_debt_gated_and_free_topics(self):
        self.assertIsNotNone(detect_gated_topic("CORPORATE_DEBT", "contagion", "radar?"))
        self.assertIsNotNone(detect_gated_topic("CORPORATE_DEBT", None, "what is the DSCR?"))
        self.assertIsNone(detect_gated_topic("CORPORATE_DEBT", "seniority", "recovery seniority tier"))
        self.assertIsNone(detect_gated_topic("CORPORATE_DEBT", None, "what is the YTM and duration?"))

    def test_notice_asks_for_a_credit_and_names_free_topics(self):
        text = build_unlock_notice("MUTUAL_FUND", "Some Fund", ("Weighted Moat & Quality Index", "the moat score"))
        self.assertIn("1 credit", text)
        self.assertIn("fees", text)


class TestForensicDeskPaywall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def _turn(self, cid, message, ticker, asset_type, section=None, **kwargs):
        return asyncio.run(process_forensic_desk_turn(
            conversation_id=cid, user_message=message, ticker=ticker,
            asset_type=asset_type, section=section, **kwargs
        ))

    def test_locked_fund_gated_topic_asks_for_credit(self):
        res = self._turn("PW-FUND-1", "What is the weighted moat score?", FUND, "mutual_fund")
        self.assertEqual(res["status"], "UNLOCK_REQUIRED")
        self.assertEqual(res["unlock_required"]["asset_kind"], "FUND")
        self.assertEqual(res["unlock_required"]["credits"], 1)
        self.assertIn("1 credit", res["response"])
        self.assertNotIn("/100", res["response"])

    def test_locked_fund_section_click_is_gated_too(self):
        res = self._turn("PW-FUND-2", "Audit this", FUND, "mutual_fund", section="asri_solvency")
        self.assertEqual(res["status"], "UNLOCK_REQUIRED")

    def test_locked_fund_free_topics_still_answered(self):
        res = self._turn("PW-FUND-3", "Explain the fee impact.", FUND, "mutual_fund", section="fee_drag")
        self.assertNotEqual(res["status"], "UNLOCK_REQUIRED")
        self.assertIn("Fee Drag", res["response"])

    def test_locked_fund_summary_hides_gated_numbers(self):
        res = self._turn("PW-FUND-4", "Give me an overview", FUND, "mutual_fund")
        self.assertNotEqual(res["status"], "UNLOCK_REQUIRED")
        self.assertNotIn("Weighted Moat Score:", res["response"])
        self.assertNotIn("(ASRI):", res["response"])
        self.assertIn("Deep Dive", res["response"])

    def test_unlocked_fund_gets_full_answer(self):
        res = self._turn("PW-FUND-5", "What is the weighted moat score?", FUND, "mutual_fund",
                         unlock_checker=lambda kind, asset_id: kind == "FUND")
        self.assertNotEqual(res["status"], "UNLOCK_REQUIRED")
        self.assertIn("Moat", res["response"])

    def test_checker_receives_namespaced_fund_id(self):
        seen = []
        self._turn("PW-FUND-6", "overview", FUND, "mutual_fund",
                   unlock_checker=lambda kind, asset_id: seen.append((kind, asset_id)) or False)
        self.assertEqual(seen[0][0], "FUND")
        self.assertEqual(seen[0][1], FUND)

    def test_locked_debt_contagion_asks_for_credit(self):
        res = self._turn("PW-DEBT-1", "What does the Credit Contagion Radar say?", DEBT, "debt")
        self.assertEqual(res["status"], "UNLOCK_REQUIRED")
        self.assertEqual(res["unlock_required"]["asset_kind"], "DEBT")
        self.assertEqual(res["unlock_required"]["asset_id"], DEBT)

    def test_locked_debt_free_topics_and_summary(self):
        seniority = self._turn("PW-DEBT-2", "Explain recovery seniority", DEBT, "debt", section="seniority")
        self.assertNotEqual(seniority["status"], "UNLOCK_REQUIRED")
        summary = self._turn("PW-DEBT-3", "Overview please", DEBT, "debt")
        self.assertNotEqual(summary["status"], "UNLOCK_REQUIRED")
        self.assertIn("Deep Dive", summary["response"])

    def test_unlocked_debt_gets_contagion_answer(self):
        res = self._turn("PW-DEBT-4", "What does the Credit Contagion Radar say?", DEBT, "debt",
                         unlock_checker=lambda kind, asset_id: True)
        self.assertNotEqual(res["status"], "UNLOCK_REQUIRED")
        self.assertIn("Contagion", res["response"])

    def test_section_data_dropped_when_locked(self):
        captured = {}
        real_builder = __import__(
            "core.agents.copilot.forensic_desk", fromlist=["build_mutual_fund_deterministic_response"]
        ).build_mutual_fund_deterministic_response

        def spy(context_data, *a, **k):
            captured.update(context_data)
            return real_builder(context_data, *a, **k)

        with mock.patch("core.agents.copilot.forensic_desk.build_mutual_fund_deterministic_response", side_effect=spy):
            self._turn("PW-FUND-7", "overview", FUND, "mutual_fund", section_data={"leak": "SECRET"})
        self.assertEqual(captured.get("section_data"), {})
        for gated in ("weighted_moat_score", "accounting_risk_index", "dossier_text"):
            self.assertNotIn(gated, captured)


class TestPagesAndApis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.main import app
        init_db()
        cls.client = TestClient(app)

    def test_guest_fund_page_shows_unlock_card_not_gated_content(self):
        text = self.client.get(f"/funds/{FUND}").text
        self.assertIn("Unlock for 1 credit", text)
        self.assertNotIn("Weighted Moat Index", text)
        self.assertNotIn("Deep-Dive Stock Forensic Audit Option", text)

    def test_unlocked_fund_page_shows_full_content(self):
        text = self.client.get(f"/funds/{FUND}", headers=UNLOCK).text
        self.assertIn("Weighted Moat Index", text)
        self.assertNotIn("Unlock for 1 credit", text)

    def test_guest_debt_page_hides_radar_and_pillars_03_05(self):
        text = self.client.get(f"/debt/{DEBT}").text
        self.assertIn("Unlock for 1 credit", text)
        self.assertNotIn("03: Cash Flow Solvency", text)
        self.assertNotIn("05: Recovery Reality", text)
        self.assertNotIn("Cross-references parent equity distress", text)
        # Free pillars stay visible
        self.assertIn("01: Credit Quality", text)
        self.assertIn("04: Duration", text)

    def test_unlocked_debt_page_shows_everything(self):
        text = self.client.get(f"/debt/{DEBT}", headers=UNLOCK).text
        self.assertIn("03: Cash Flow Solvency", text)
        self.assertIn("05: Recovery Reality", text)
        self.assertNotIn("Unlock for 1 credit", text)

    def test_fund_dossier_api_redacted_for_guest(self):
        data = self.client.get(f"/api/funds/dossier/{FUND}").json()
        self.assertTrue(data.get("deep_dive_locked"))
        for gated in ("weighted_moat_score", "accounting_risk_index", "margin_of_safety_pct",
                      "promoter_pledge_exposure_pct", "top_risky_holdings", "dossier_text"):
            self.assertNotIn(gated, data)

    def test_debt_detail_api_redacted_and_not_publicly_cacheable(self):
        resp = self.client.get(f"/api/debt/security/{DEBT}")
        posture = resp.json()["posture"]
        self.assertTrue(posture.get("deep_dive_locked"))
        self.assertNotIn("credit_contagion_radar", posture)
        self.assertNotIn("p3_solvency", posture["pillars"])
        self.assertNotIn("p5_recovery", posture["pillars"])
        self.assertIn("p1_credit_quality", posture["pillars"])
        self.assertIn("no-store", resp.headers.get("cache-control", ""))

    def test_debt_detail_api_full_when_unlocked(self):
        posture = self.client.get(f"/api/debt/security/{DEBT}", headers=UNLOCK).json()["posture"]
        self.assertIn("p3_solvency", posture["pillars"])
        self.assertNotIn("deep_dive_locked", posture)


class TestUnlockEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.main import app
        init_db()
        cls.client = TestClient(app)

    def test_unlock_requires_sign_in(self):
        self.assertEqual(self.client.post(f"/api/funds/unlock/{FUND}").status_code, 401)
        self.assertEqual(self.client.post(f"/api/debt/unlock/{DEBT}").status_code, 401)

    def test_unknown_assets_404(self):
        self.assertEqual(self.client.post("/api/debt/unlock/NOPE000000000").status_code, 404)

    def test_fund_unlock_charges_namespaced_key(self):
        with mock.patch("web.main._get_current_web_user", return_value={"id": "u1"}), \
             mock.patch("web.main.unlock_ticker_for_user", return_value=(True, 4.0, "ok")) as charge:
            resp = self.client.post(f"/api/funds/unlock/{FUND}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(charge.call_args.kwargs["ticker"], f"FUND:{FUND}")
        self.assertEqual(charge.call_args.kwargs["amount"], 1.0)
        self.assertEqual(resp.json()["new_balance"], 4.0)

    def test_debt_unlock_insufficient_credits_returns_402(self):
        with mock.patch("web.main._get_current_web_user", return_value={"id": "u1"}), \
             mock.patch("web.main.unlock_ticker_for_user", return_value=(False, 0.0, "Insufficient credits")):
            resp = self.client.post(f"/api/debt/unlock/{DEBT}")
        self.assertEqual(resp.status_code, 402)

    def test_entitlement_uses_namespaced_key_and_equity_unlock_does_not_leak(self):
        from web.main import _asset_unlocked_for_request

        def only_equity(user_id, ticker):
            return ticker == FUND  # an equity-style un-namespaced key

        request = mock.Mock()
        request.headers = {}
        with mock.patch("web.main._is_admin_authenticated", return_value=False), \
             mock.patch("web.main._get_current_web_user", return_value={"id": "u1"}), \
             mock.patch("web.main.is_ticker_unlocked_for_user", side_effect=only_equity):
            self.assertFalse(_asset_unlocked_for_request(request, "FUND", FUND))


class TestPdfPaywall(unittest.TestCase):
    def test_fund_pdf_hides_deep_dive_when_locked(self):
        dossier = {
            "composite_health_score": 71.0, "weighted_moat_score": 91.7, "accounting_risk_index": 3.3,
            "margin_of_safety_pct": 12.5, "dossier_text": "SECRET_NARRATIVE_TEXT",
        }
        scheme = {"scheme_name": "Test Fund", "category": "Flexi Cap"}
        locked = _pdf_text(generate_fund_dossier_pdf("TESTFUND", dossier, scheme, deep_dive_unlocked=False))
        self.assertNotIn("SECRET_NARRATIVE_TEXT", locked)
        self.assertNotIn("91.7", locked)
        self.assertIn("Deep Dive", locked)
        full = _pdf_text(generate_fund_dossier_pdf("TESTFUND", dossier, scheme))
        self.assertIn("SECRET_NARRATIVE_TEXT", full)
        self.assertIn("91.7", full)

    def test_debt_pdf_hides_deep_dive_when_locked(self):
        posture = {
            "composite_score": 80, "credit_contagion_radar": {"radar_summary": "SECRET_RADAR_SUMMARY"},
            "pillars": {"p3_solvency": {"institutional_analysis": "SECRET_P3_ANALYSIS"}},
        }
        security = {"instrument_name": "Test NCD"}
        locked = _pdf_text(generate_debt_dossier_pdf("INE000000001", posture, security, deep_dive_unlocked=False))
        self.assertNotIn("SECRET_RADAR_SUMMARY", locked)
        self.assertNotIn("SECRET_P3_ANALYSIS", locked)
        self.assertIn("Deep Dive", locked)
        full = _pdf_text(generate_debt_dossier_pdf("INE000000001", posture, security))
        self.assertIn("SECRET_RADAR_SUMMARY", full)
        self.assertIn("SECRET_P3_ANALYSIS", full)


if __name__ == "__main__":
    unittest.main()
