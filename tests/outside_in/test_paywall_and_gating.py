"""
Consolidated Paywalls & Access Control Test Suite
==================================================
Unifies:
1. Equity Pillar 03/05 Paywall (Copilot redaction & route entitlement)
2. PDF Watermarking & Gated Pillar Redaction
3. Mutual Fund & Corporate Debt Deep Dive Paywalls (pages, APIs, PDFs, Forensic Desk, and credit unlocks)
"""
import asyncio
import os
import unittest
from unittest import mock

os.environ["TESTING"] = "1"

from fastapi.testclient import TestClient

from core.agents.copilot.forensic_desk import (
    GATED_PILLAR_NOTICE,
    build_unlock_notice,
    detect_gated_topic,
    process_forensic_desk_turn,
    redact_gated_pillars,
)
from core.db import init_db
from core.reporting.pdf import (
    apply_pdf_watermark,
    generate_debt_dossier_pdf,
    generate_fund_dossier_pdf,
    generate_reit_dossier_pdf,
)

UNLOCK = {"x-unlock-preview": "1"}
FUND = "PPFAS_FLEXICAP_DIR"
DEBT = "INE002A08012"

EQUITY_REPORT = (
    "## Pillar 1: Macro\nMacro text\n\n"
    "## Pillar 2: Business\nBusiness text\n\n"
    "## Pillar 3: Cash Flow Solvency\nSECRET_P3 coverage detail\n\n"
    "## Pillar 4: Governance\nGovernance text\n\n"
    "## Pillar 5: Valuation & Margin of Safety\nSECRET_P5 intrinsic value\n\n"
    "## Pillar 6: Technical\nTechnical text\n"
)


def _tiny_pdf() -> bytes:
    try:
        import pymupdf as fitz_mod
    except ImportError:
        import fitz as fitz_mod
    doc = fitz_mod.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Body text")
    data = doc.tobytes()
    doc.close()
    return data


def _pdf_text(pdf: bytes) -> str:
    try:
        import pymupdf as fitz_mod
    except ImportError:
        import fitz as fitz_mod
    doc = fitz_mod.open(stream=pdf, filetype="pdf")
    text = "".join(p.get_text() for p in doc)
    doc.close()
    return text


# ==============================================================================
# 1. Equity Copilot & Pillar Redaction
# ==============================================================================
class TestEquityRedaction(unittest.TestCase):
    def test_gated_pillars_removed_others_kept(self):
        out = redact_gated_pillars(EQUITY_REPORT)
        self.assertNotIn("SECRET_P3", out)
        self.assertNotIn("SECRET_P5", out)
        for kept in ("Macro text", "Business text", "Governance text", "Technical text"):
            self.assertIn(kept, out)
        self.assertEqual(out.count(GATED_PILLAR_NOTICE), 2)

    def test_empty_text_is_safe(self):
        self.assertEqual(redact_gated_pillars(""), "")


class TestCopilotRouteEntitlement(unittest.TestCase):
    def _post(self, **kwargs):
        from web.main import app
        client = TestClient(app)
        body = {"conversation_id": "c1", "message": "summarise", "ticker": "INFY", "user_id": "spoofed_paid_user"}
        with mock.patch("core.agents.copilot.forensic_desk.process_forensic_desk_turn", new=mock.AsyncMock(return_value={"response": "ok"})) as turn:
            client.post("/api/copilot/chat", json=body, **kwargs)
        return turn.call_args.kwargs

    def test_anonymous_is_locked_and_spoofed_user_id_ignored(self):
        kw = self._post()
        self.assertFalse(kw["deep_dive_unlocked"])
        self.assertIsNone(kw["user_id"])

    def test_payload_user_id_never_unlocks(self):
        with mock.patch("web.main.is_ticker_unlocked_for_user", return_value=True) as unlocked:
            kw = self._post()
        self.assertFalse(kw["deep_dive_unlocked"])
        unlocked.assert_not_called()

    def test_signed_in_unlocked_user_gets_full_context(self):
        with mock.patch("web.main._get_current_web_user", return_value={"id": "u1"}), \
             mock.patch("web.main.is_ticker_unlocked_for_user", return_value=True):
            kw = self._post()
        self.assertTrue(kw["deep_dive_unlocked"])
        self.assertEqual(kw["user_id"], "u1")

    def test_signed_in_user_without_unlock_stays_locked(self):
        with mock.patch("web.main._get_current_web_user", return_value={"id": "u1"}), \
             mock.patch("web.main.is_ticker_unlocked_for_user", return_value=False):
            kw = self._post()
        self.assertFalse(kw["deep_dive_unlocked"])


# ==============================================================================
# 2. PDF Watermarks & Equity PDF Gating
# ==============================================================================
class TestWatermark(unittest.TestCase):
    def test_stamps_notice_and_account_ref(self):
        out = _pdf_text(apply_pdf_watermark(_tiny_pdf(), "usr_abc123"))
        self.assertIn("Body text", out)
        self.assertIn("Personal, non-commercial use only", out)
        self.assertIn("usr_abc123", out)

    def test_anonymous_has_notice_without_account(self):
        out = _pdf_text(apply_pdf_watermark(_tiny_pdf(), ""))
        self.assertIn("Redistribution is prohibited", out)
        self.assertNotIn("Licensed to account", out)

    def test_fails_open_on_bad_input(self):
        self.assertEqual(apply_pdf_watermark(b"not a pdf", "x"), b"not a pdf")


class TestEquityPdfPaywall(unittest.TestCase):
    def _download(self, headers=None):
        from web.main import app
        captured = {}

        def fake_generate(ticker, rep_text, **kwargs):
            captured["text"] = rep_text
            return _tiny_pdf()

        rep = {"report_text": EQUITY_REPORT, "citations": []}
        with mock.patch.dict(os.environ, {"TESTING": "1"}), \
             mock.patch("web.main.get_report_by_ticker_sync", return_value=rep), \
             mock.patch("web.main.get_historical_prices", return_value=None), \
             mock.patch("core.reporting.pdf.generate_report_pdf", side_effect=fake_generate):
            resp = TestClient(app).get("/api/pdf/INFY", headers=headers or {})
        return resp, captured.get("text", "")

    def test_locked_user_pdf_excludes_gated_pillars(self):
        resp, text = self._download()
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("SECRET_P3", text)
        self.assertNotIn("SECRET_P5", text)
        self.assertIn("Macro text", text)
        self.assertIn("Unlock this ticker", text)

    def test_unlocked_user_pdf_has_full_report(self):
        resp, text = self._download({"x-unlock-preview": "1"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("SECRET_P3", text)
        self.assertIn("SECRET_P5", text)

    def test_pdf_response_is_watermarked(self):
        resp, _ = self._download()
        self.assertIn("Personal, non-commercial use only", _pdf_text(resp.content))


# ==============================================================================
# 3. Fund & Debt Paywall Topic Detection
# ==============================================================================
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


# ==============================================================================
# 4. Forensic Desk Multi-Asset Paywall
# ==============================================================================
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


# ==============================================================================
# 5. Pages & APIs Gating
# ==============================================================================
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


# ==============================================================================
# 6. Unlock Endpoints & Entitlements
# ==============================================================================
class TestUnlockEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.main import app
        init_db()
        cls.client = TestClient(app)

    def test_unlock_requires_sign_in(self):
        targets = [
            f"/api/funds/unlock/{FUND}",
            f"/api/debt/unlock/{DEBT}",
            "/api/reits/unlock/EMBASSY",
            "/api/dossier/unlock/INFY",
        ]
        for url in targets:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 401)

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
            return ticker == FUND

        request = mock.Mock()
        request.headers = {}
        with mock.patch("web.main._is_admin_authenticated", return_value=False), \
             mock.patch("web.main._get_current_web_user", return_value={"id": "u1"}), \
             mock.patch("web.main.is_ticker_unlocked_for_user", side_effect=only_equity):
            self.assertFalse(_asset_unlocked_for_request(request, "FUND", FUND))


# ==============================================================================
# 7. Fund & Debt PDF Paywalls
# ==============================================================================
class TestFundAndDebtPdfPaywall(unittest.TestCase):
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

    def test_reit_pdf_hides_deep_dive_when_locked(self):
        from core.db.reits import get_reit_by_symbol
        reit = get_reit_by_symbol("EMBASSY")
        locked = _pdf_text(generate_reit_dossier_pdf("EMBASSY", reit, deep_dive_unlocked=False))
        self.assertIn("Institutional Deep-Dive Section", locked)
        self.assertNotIn("Pillar 4.1 (Cap Rate", locked)
        full = _pdf_text(generate_reit_dossier_pdf("EMBASSY", reit, deep_dive_unlocked=True))
        self.assertIn("Behavioral Pre-Mortem Inversion Risk Ledger", full)
        self.assertIn("Pillar 4.1 (Cap Rate", full)


class TestReitPaywallAndUnlock(unittest.TestCase):
    def setUp(self):
        init_db()
        from web.main import app
        self.client = TestClient(app)

    def test_reit_dossier_shows_unlock_card_when_locked(self):
        resp = self.client.get("/reits/EMBASSY")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Unlock Deep-Dive (1 Credit)", resp.text)
        self.assertIn("Download PDF (Locked)", resp.text)
        self.assertIn("Behavioral Pre-Mortem Inversion Risk Ledger", resp.text)

    def test_reit_dossier_shows_unlocked_when_unlocked(self):
        resp = self.client.get("/reits/EMBASSY", headers=UNLOCK)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Institutional Unlocked", resp.text)
        self.assertIn("Download Institutional PDF", resp.text)
        self.assertIn("Structural Failure Modes", resp.text)

    def test_reit_unlock_endpoint_requires_auth(self):
        resp = self.client.post("/api/reits/unlock/EMBASSY")
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
