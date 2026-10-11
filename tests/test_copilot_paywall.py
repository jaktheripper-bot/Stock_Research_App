"""Copilot must enforce the Pillar 03/05 paywall server-side."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from core.agents.copilot.forensic_desk import GATED_PILLAR_NOTICE, redact_gated_pillars

REPORT = (
    "## Pillar 1: Macro\nMacro text\n\n"
    "## Pillar 2: Business\nBusiness text\n\n"
    "## Pillar 3: Cash Flow Solvency\nSECRET_P3 coverage detail\n\n"
    "## Pillar 4: Governance\nGovernance text\n\n"
    "## Pillar 5: Valuation & Margin of Safety\nSECRET_P5 intrinsic value\n\n"
    "## Pillar 6: Technical\nTechnical text\n"
)


class TestRedaction(unittest.TestCase):
    def test_gated_pillars_removed_others_kept(self):
        out = redact_gated_pillars(REPORT)
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


if __name__ == "__main__":
    unittest.main()
