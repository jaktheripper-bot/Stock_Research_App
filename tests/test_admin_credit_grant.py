"""
tests/test_admin_credit_grant.py
==============================================================================
Test Suite for Admin Panel Direct Credit Granting & Task Remediation Flow.
Verifies sequence diagram:
Admin -> UI Modal -> POST /admin/users/grant-credits -> Atomic DB Transaction
(user_accounts + credit_transactions + admin_audit_log + support_tickets)
==============================================================================
"""

import unittest
import uuid
import time
from fastapi.testclient import TestClient

from core.db.connection import init_db, get_db_connection, get_placeholder
from core.db.users import get_or_create_user, get_user_by_email, get_user_credits_balance, get_all_billables
from core.db.support import create_support_ticket, get_support_tickets
from core.db.admin import (
    admin_grant_user_credits,
    get_admin_audit_logs,
    get_admin_user
)
from web.main import app, ADMIN_COOKIE_NAME, _generate_admin_token


class TestAdminCreditGrant(unittest.TestCase):
    """Rigorous tests for direct remedial credit grants and zero-revenue ledger isolation."""

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.admin_email = "lyndnpnto@gmail.com"
        cls.admin_cookie = _generate_admin_token(cls.admin_email, "owner")

    def setUp(self):
        self.unique_suffix = uuid.uuid4().hex[:8]
        self.test_user_email = f"remedy_user_{self.unique_suffix}@example.com"
        # Seed test user with initial 2.0 credits
        self.user_record = get_or_create_user(
            user_id=f"usr_test_{self.unique_suffix}",
            email=self.test_user_email,
            full_name="Remedy Test User"
        )
        self.assertEqual(float(self.user_record.get("credits_balance", 0.0)), 2.0)

    def test_admin_grant_user_credits_atomic_db_transaction(self):
        """
        Verify backend atomic transaction:
        1. user_accounts.credits_balance increments by 2.0 (2.0 -> 4.0)
        2. credit_transactions registers zero-revenue ledger entry (amount_inr = 0.0, nature = FREE_GRANT)
        3. admin_audit_log records immutable GRANT_USER_CREDITS action
        """
        initial_balance = get_user_credits_balance(self.user_record["id"])
        self.assertEqual(initial_balance, 2.0)

        # Execute grant
        res = admin_grant_user_credits(
            admin_email=self.admin_email,
            target_user_identifier=self.test_user_email,
            credits_amount=2.0,
            reason_code="TASK_REMEDY",
            admin_note="Compensating for failed synthesis retry on INFY",
            task_ticker="INFY"
        )

        self.assertTrue(res.get("success"), f"Grant failed: {res.get('error')}")
        self.assertEqual(res.get("credits_added"), 2.0)
        self.assertEqual(res.get("old_balance"), 2.0)
        self.assertEqual(res.get("new_balance"), 4.0)

        # 1. Verify user_accounts balance updated
        updated_user = get_user_by_email(self.test_user_email)
        self.assertIsNotNone(updated_user)
        self.assertEqual(float(updated_user["credits_balance"]), 4.0)

        # 2. Verify credit_transactions zero-revenue ledger record
        billables = get_all_billables(limit=100, exclude_tests=False)
        grant_tx = next((b for b in billables if b["customer_email"] == self.test_user_email and "ADMIN_GRANT" in b["pack_type"]), None)
        self.assertIsNotNone(grant_tx, "Expected credit_transactions entry for admin grant.")
        self.assertEqual(grant_tx["amount_inr"], 0.0, "Remedial credits must strictly have 0.0 INR value.")
        self.assertEqual(grant_tx["base_amount_inr"], 0.0)
        self.assertEqual(grant_tx["tax_gst_inr"], 0.0)
        self.assertEqual(grant_tx["nature"], "FREE_GRANT", "Transaction nature must be classified as FREE_GRANT.")
        self.assertEqual(grant_tx["credits_added"], 2.0)

        # 3. Verify admin_audit_log record
        audit_logs = get_admin_audit_logs(limit=20)
        grant_log = next((l for l in audit_logs if l["action"] == "GRANT_USER_CREDITS" and l["target_id"] == self.user_record["id"]), None)
        self.assertIsNotNone(grant_log, "Expected admin_audit_log entry for GRANT_USER_CREDITS.")
        self.assertEqual(grant_log["admin_email"], self.admin_email)
        details = grant_log.get("details_parsed", {})
        self.assertEqual(details.get("credits_granted"), 2.0)
        self.assertEqual(details.get("reason_code"), "TASK_REMEDY")
        self.assertEqual(details.get("task_ticker"), "INFY")
        self.assertEqual(details.get("nature"), "FREE_GRANT")

    def test_admin_grant_with_ticket_auto_resolution(self):
        """
        Verify that granting credits with a linked support ticket automatically
        updates the ticket status to 'resolved' and appends audit notes.
        """
        # Create a support ticket
        ticket_res = create_support_ticket(
            user_email=self.test_user_email,
            subject="Synthesis failed on TCS",
            message="Credits deducted but synthesis timed out",
            user_name="Remedy Test User",
            category="synthesis_error"
        )
        self.assertTrue(ticket_res.get("success"))
        ticket_id = ticket_res["ticket_id"]

        # Grant credits and resolve ticket
        res = admin_grant_user_credits(
            admin_email=self.admin_email,
            target_user_identifier=self.test_user_email,
            credits_amount=1.0,
            reason_code="TASK_REMEDY",
            admin_note="Restored 1.0 credit after timeout review",
            ticket_id=ticket_id,
            task_ticker="TCS",
            resolve_ticket=True
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("new_balance"), 3.0)

        # Verify support ticket status
        tickets = get_support_tickets(status="all", exclude_tests=False)
        target_ticket = next((t for t in tickets if t["ticket_id"] == ticket_id), None)
        self.assertIsNotNone(target_ticket)
        self.assertEqual(target_ticket["status"], "resolved")
        self.assertIn("[Admin Credits Granted: +1.0", target_ticket["admin_notes"])
        self.assertIn("Restored 1.0 credit after timeout review", target_ticket["admin_notes"])

    def test_admin_grant_validation_rejections(self):
        """Verify invalid user identifier or invalid credit amounts are cleanly rejected."""
        # Non-existent user
        res_nonexistent = admin_grant_user_credits(
            admin_email=self.admin_email,
            target_user_identifier="non_existent_ghost_user@example.com",
            credits_amount=2.0
        )
        self.assertFalse(res_nonexistent.get("success"))
        self.assertIn("not found", res_nonexistent.get("error", "").lower())

        # Zero or negative credits
        res_zero = admin_grant_user_credits(
            admin_email=self.admin_email,
            target_user_identifier=self.test_user_email,
            credits_amount=0.0
        )
        self.assertFalse(res_zero.get("success"))

        res_neg = admin_grant_user_credits(
            admin_email=self.admin_email,
            target_user_identifier=self.test_user_email,
            credits_amount=-5.0
        )
        self.assertFalse(res_neg.get("success"))

    def test_endpoint_unauthorized_rejection(self):
        """Unauthenticated requests to /admin/users/grant-credits must be rejected with 403."""
        # JSON request
        res = self.client.post(
            "/admin/users/grant-credits",
            json={"user_email": self.test_user_email, "credits": 2.0},
            headers={"Accept": "application/json"}
        )
        self.assertEqual(res.status_code, 403)

        # Form request
        res_form = self.client.post(
            "/admin/users/grant-credits",
            data={"user_email": self.test_user_email, "credits": 2.0}
        )
        self.assertEqual(res_form.status_code, 403)

    def test_endpoint_authenticated_json_ajax_success(self):
        """
        Verify authenticated POST /admin/users/grant-credits via JSON / AJAX
        returns 200 OK {success: true, new_balance: 4.0, ...} matching the sequence diagram.
        """
        payload = {
            "user_email": self.test_user_email,
            "credits": 2.0,
            "reason": "TASK_REMEDY",
            "admin_note": "Sequence diagram verification grant",
            "task_ticker": "INFY"
        }
        res = self.client.post(
            "/admin/users/grant-credits",
            json=payload,
            cookies={ADMIN_COOKIE_NAME: self.admin_cookie},
            headers={"Accept": "application/json"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("new_balance"), 4.0)
        self.assertEqual(data.get("credits_added"), 2.0)
        self.assertEqual(data.get("user_email"), self.test_user_email)
        self.assertIn(f"Successfully granted 2.0 credits to {self.test_user_email}", data.get("message"))

    def test_endpoint_authenticated_form_post_redirect(self):
        """
        Verify authenticated standard Form POST /admin/users/grant-credits
        redirects with 303 to /admin?tab=users&msg=... with success flash message.
        """
        form_data = {
            "user_email": self.test_user_email,
            "credits": "1.5",
            "reason": "GOODWILL_COMPENSATION",
            "admin_note": "Goodwill top-up",
            "tab": "users"
        }
        res = self.client.post(
            "/admin/users/grant-credits",
            data=form_data,
            cookies={ADMIN_COOKIE_NAME: self.admin_cookie},
            follow_redirects=False
        )
        self.assertEqual(res.status_code, 303)
        location = res.headers.get("location", "")
        self.assertIn("tab=users", location)
        self.assertIn("Successfully+granted+1.5+credits", location)

        # Verify new balance is 3.5 (2.0 + 1.5)
        self.assertEqual(get_user_credits_balance(self.user_record["id"]), 3.5)


if __name__ == "__main__":
    unittest.main()
