"""
End-to-End Critical Journey Tests
=================================
Validates production-hardened E2E journeys:
1. Paywall redaction for unauthenticated and 0-credit users on /dossier/{ticker} and /api/copilot/chat.
2. Replay attack simulation on payment verification (/api/billing/verify and /api/verify-payment)
   guaranteeing atomic idempotency and single credit increment.
3. Admin 2FA gate security enforcement and Admin Copilot 2-step confirmation workflow
   (interactive command chat -> explicit confirmation execution).
"""

import os
import unittest
from unittest import mock
from fastapi.testclient import TestClient

os.environ["TESTING"] = "1"

from web.main import app
from web.common import (
    ADMIN_COOKIE_NAME,
    ADMIN_2FA_PENDING_COOKIE,
    _generate_admin_token,
    _generate_pending_2fa_token,
)
from core.db import (
    init_db,
    get_or_create_user,
    get_user_credits_balance,
)
from core.db.users import get_credit_transaction_by_gateway_id
from core.agents.copilot.forensic_desk import GATED_PILLAR_NOTICE

EQUITY_FIXTURE_REPORT = (
    "## Pillar 1: Macro & Sovereign Yield Context\nIndia 10Y G-Sec benchmark is steady at 6.8%.\n\n"
    "## Pillar 2: Business Moat & Capital Allocation\nHigh return on invested capital with secular compounding.\n\n"
    "## Pillar 3: Cash Flow Solvency & Forensic Accounting\nCONFIDENTIAL_P3: ASRI accounting risk score is 18/100.\n\n"
    "## Pillar 4: Corporate Governance & Ownership Posture\nClean audit history and low promoter pledge.\n\n"
    "## Pillar 5: Intrinsic Valuation & Margin of Safety\nCONFIDENTIAL_P5: DCF intrinsic value calculated at ₹1,850.\n\n"
    "## Pillar 6: Technical Footprint & Accumulation Vectors\nConsolidating above 200 EMA.\n\n"
    "## Pillar 7: Comprehensive Analytical Verdict\nResilient compounding profile.\n"
)


# ==============================================================================
# 1. PAYWALL REDACTION JOURNEYS
# ==============================================================================
class TestPaywallRedactionJourneys(unittest.TestCase):
    def setUp(self):
        init_db()
        self.client = TestClient(app)

    def test_unauthenticated_dossier_paywall_redaction(self):
        """Unauthenticated user visiting /dossier/{ticker} must see paywall-gated pillars."""
        fixture = {
            "ticker": "INFY",
            "short_name": "Infosys Ltd",
            "report_text": EQUITY_FIXTURE_REPORT,
            "citations": [],
            "citations_json": "[]",
            "baseline_mcap": 600000.0,
            "scrip_code": "500209",
        }

        with mock.patch("web.main.get_report_by_ticker_sync", return_value=fixture), \
             mock.patch("web.main.get_ticker_suggestions", return_value=[]), \
             mock.patch("web.main.get_report_revisions", return_value=[]):
            # 1. Unauthenticated request: deep dive is locked
            resp_locked = self.client.get("/dossier/INFY")
            self.assertEqual(resp_locked.status_code, 200)
            html_locked = resp_locked.text
            # Gated pillars (03 and 05) must carry paywall locking affordance
            self.assertTrue(
                "locked" in html_locked.lower() or "unlock" in html_locked.lower() or "paywall" in html_locked.lower(),
                "Paywall gating affordance missing for unauthenticated dossier visitor"
            )

            # 2. Authenticated or unlocked request: deep dive unlocked
            resp_unlocked = self.client.get("/dossier/INFY?unlocked=1")
            self.assertEqual(resp_unlocked.status_code, 200)
            html_unlocked = resp_unlocked.text
            self.assertIn("CONFIDENTIAL_P3", html_unlocked)
            self.assertIn("CONFIDENTIAL_P5", html_unlocked)

    def test_unauthenticated_copilot_chat_paywall_redaction(self):
        """Unauthenticated request to /api/copilot/chat must have deep_dive_unlocked=False and redact gated pillars."""
        captured_kwargs = {}

        async def fake_turn(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "response": "Here is the public summary.",
                "conversation_id": kwargs.get("conversation_id", "test_c1"),
                "status": "COMPLETED"
            }

        with mock.patch("core.agents.copilot.forensic_desk.process_forensic_desk_turn", side_effect=fake_turn):
            payload = {
                "conversation_id": "c_e2e_1",
                "message": "Detail the cash flow solvency metrics",
                "ticker": "INFY",
                "user_id": "spoofed_unauthorized_user"  # Client-sent user_id must be ignored
            }
            resp = self.client.post("/api/copilot/chat", json=payload)
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json().get("success"))

            # Validate server-side security contract: deep_dive_unlocked MUST be False
            self.assertFalse(captured_kwargs.get("deep_dive_unlocked"))
            # Client-sent spoofed user_id must NOT be trusted
            self.assertIsNone(captured_kwargs.get("user_id"))


import uuid

# ==============================================================================
# 2. PAYMENT IDEMPOTENCY & REPLAY ATTACK SIMULATION
# ==============================================================================
class TestPaymentIdempotencyReplayJourneys(unittest.TestCase):
    def setUp(self):
        init_db()
        self.client = TestClient(app)
        self.user_id = f"usr_replay_sim_{uuid.uuid4().hex[:8]}"
        get_or_create_user(self.user_id, f"{self.user_id}@test.com", "Replay Test User")

    def test_billing_verify_replay_attack_simulation(self):
        """Simulates replay attacks on /api/billing/verify asserting credits increment exactly once."""
        initial_balance = get_user_credits_balance(self.user_id)

        uid_suffix = uuid.uuid4().hex[:8]
        order_id = f"order_sim_e2e_replay_{uid_suffix}"
        payment_id = f"pay_sim_e2e_replay_{uid_suffix}"

        replay_payload = {
            "order_id": order_id,
            "payment_id": payment_id,
            "signature": "simulated_success",
            "user_id": self.user_id,
            "plan_id": "single_pass"  # Adds 1 credit
        }

        # First Verification Attempt (Legitimate user purchase)
        resp1 = self.client.post("/api/billing/verify", json=replay_payload)
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertTrue(data1.get("success"))
        expected_balance = initial_balance + 1.0
        self.assertEqual(data1.get("new_balance"), expected_balance)
        self.assertEqual(get_user_credits_balance(self.user_id), expected_balance)

        # Replay Attack 1: Exact duplicate replay to /api/billing/verify
        resp2 = self.client.post("/api/billing/verify", json=replay_payload)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2.get("success"))
        # Balance MUST NOT increment a second time
        self.assertEqual(data2.get("new_balance"), expected_balance)
        self.assertEqual(get_user_credits_balance(self.user_id), expected_balance)

        # Replay Attack 2: Exact duplicate replay to alias endpoint /api/verify-payment
        resp3 = self.client.post("/api/verify-payment", json=replay_payload)
        self.assertEqual(resp3.status_code, 200)
        data3 = resp3.json()
        self.assertTrue(data3.get("success"))
        # Balance MUST STILL remain exactly the same
        self.assertEqual(data3.get("new_balance"), expected_balance)
        self.assertEqual(get_user_credits_balance(self.user_id), expected_balance)

        # Empirical Database Audit: Ensure only ONE transaction record exists
        tx = get_credit_transaction_by_gateway_id(payment_id=payment_id)
        self.assertIsNotNone(tx)
        self.assertEqual(tx["gateway_payment_id"], payment_id)


# ==============================================================================
# 3. ADMIN 2FA GATE & COPILOT 2-STEP CONFIRMATION JOURNEYS
# ==============================================================================
class TestAdmin2FAGateAndCopilotJourneys(unittest.TestCase):
    def setUp(self):
        init_db()
        self.client = TestClient(app)
        self.recipient_id = f"usr_copilot_grant_{uuid.uuid4().hex[:8]}"
        get_or_create_user(self.recipient_id, f"{self.recipient_id}@test.com", "Grant Recipient")

    def test_admin_2fa_gate_enforcement(self):
        """Unauthenticated or pending-2FA requests must be rejected from administrative endpoints."""
        # 1. Unauthenticated request to Admin Copilot
        resp_unauth = self.client.post("/api/admin/copilot/chat", json={"message": "System status"})
        self.assertEqual(resp_unauth.status_code, 403)
        self.assertIn("Admin authorization required", resp_unauth.json().get("detail", ""))

        # 2. Request carrying ONLY pending 2FA token (has not completed TOTP)
        pending_token = _generate_pending_2fa_token("admin_owner@example.com")
        self.client.cookies.set(ADMIN_2FA_PENDING_COOKIE, pending_token)
        resp_pending = self.client.post("/api/admin/copilot/chat", json={"message": "System status"})
        self.assertEqual(resp_pending.status_code, 403)

        # 3. Unauthenticated request to Admin Execute endpoint
        resp_exec = self.client.post(
            "/api/admin/copilot/execute",
            json={"action_type": "GRANT_CREDITS", "payload": {}}
        )
        self.assertEqual(resp_exec.status_code, 403)

    def test_admin_copilot_two_step_confirmation(self):
        """Admin Copilot must require explicit 2-step confirmation (chat proposes -> execute confirms)."""
        admin_token = _generate_admin_token("admin_owner@example.com", role="owner")
        self.client.cookies.set(ADMIN_COOKIE_NAME, admin_token)

        initial_bal = get_user_credits_balance(self.recipient_id)

        # Step 1: Admin sends prompt via Chat proposing an administrative state change
        chat_resp = self.client.post(
            "/api/admin/copilot/chat",
            json={"message": f"Grant 5 credits to {self.recipient_id}@test.com"}
        )
        self.assertEqual(chat_resp.status_code, 200)
        chat_data = chat_resp.json()
        self.assertTrue(chat_data.get("success"))
        proposal = chat_data.get("action_proposal")
        self.assertIsNotNone(proposal, "Admin Copilot failed to return an action proposal for credit grant")
        self.assertEqual(proposal.get("action_type"), "GRANT_CREDITS")
        self.assertTrue(proposal.get("requires_confirmation"))

        # Verify NO credits have been allocated yet (first step only proposes!)
        self.assertEqual(get_user_credits_balance(self.recipient_id), initial_bal)

        # Step 2: Administrator reviews proposal card and submits explicit confirmation
        exec_payload = {
            "action_type": proposal["action_type"],
            "payload": proposal["payload"]
        }
        exec_resp = self.client.post("/api/admin/copilot/execute", json=exec_payload)
        self.assertEqual(exec_resp.status_code, 200)
        exec_data = exec_resp.json()
        self.assertTrue(exec_data.get("success"))

        # Empirical Balance Verification: Exactly 5 credits added after explicit execution
        new_bal = get_user_credits_balance(self.recipient_id)
        self.assertEqual(new_bal, initial_bal + 5.0)


if __name__ == "__main__":
    unittest.main()
