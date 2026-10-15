"""
tests/test_admin_copilot.py
==============================================================================
Unit & Integration Tests for Admin Executive Copilot and Two-Step Action Engine.
==============================================================================
"""

import os
import unittest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from web.main import app
from web.common import _generate_admin_token, ADMIN_COOKIE_NAME
from core.db import init_db
from core.db.admin import get_admin_user, add_admin_user
from core.db.users import get_or_create_user
from core.db.support import create_support_ticket, get_support_tickets
from core.agents.copilot.admin_copilot import (
    AdminActionType,
    tool_get_admin_dashboard_kpis,
    tool_get_billables_summary,
    tool_get_support_tickets_summary,
    tool_lookup_user_account,
    tool_get_admin_audit_trail,
    create_action_proposal,
    execute_confirmed_admin_action,
    process_admin_copilot_turn,
)


class TestAdminCopilot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        init_db()

        cls.owner_email = "lyndnpnto@gmail.com"
        cls.owner_token = _generate_admin_token(cls.owner_email, "owner")

        cls.viewer_email = "test_viewer@moatnomics.internal"
        add_admin_user(cls.viewer_email, role="viewer")
        cls.viewer_token = _generate_admin_token(cls.viewer_email, "viewer")

        cls.test_user_email = "copilot_user@example.com"
        get_or_create_user(user_id="usr_copilot_test_1", email=cls.test_user_email, full_name="Copilot User")

    def setUp(self):
        self.client = TestClient(app)
        get_or_create_user(user_id="usr_copilot_test_1", email=self.test_user_email, full_name="Copilot User")

    def test_analytical_tools_execution(self):
        """Verify data tools retrieve live metrics cleanly without exceptions."""
        kpis = tool_get_admin_dashboard_kpis(window="30d", exclude_tests=False)
        self.assertIsInstance(kpis, dict)
        self.assertIn("unique_sessions", kpis)
        self.assertIn("gross_revenue_inr", kpis)
        self.assertIn("net_revenue_inr", kpis)
        self.assertIn("open_tickets_count", kpis)

        billables = tool_get_billables_summary(window="30d", limit=5)
        self.assertIsInstance(billables, dict)
        self.assertIn("recent_transactions", billables)

        tickets = tool_get_support_tickets_summary(status="all", limit=5, exclude_tests=False)
        self.assertIsInstance(tickets, list)

        user_info = tool_lookup_user_account(self.test_user_email)
        self.assertIsNotNone(user_info)
        self.assertEqual(user_info["email"], self.test_user_email)
        self.assertIn("credits_balance", user_info)

        audit_trail = tool_get_admin_audit_trail(limit=5)
        self.assertIsInstance(audit_trail, list)

    def test_create_action_proposal(self):
        """Verify proposal payload structure and strict two-step confirmation requirement."""
        prop = create_action_proposal(
            action_type=AdminActionType.GRANT_CREDITS,
            title="Grant 5.0 Credits",
            summary="Allocate credits to test user.",
            payload={"target_user": self.test_user_email, "credits": 5.0},
            impact_level="MEDIUM",
            impact_warning="Credits balance will increase."
        )
        self.assertTrue(prop["requires_confirmation"])
        self.assertEqual(prop["action_type"], AdminActionType.GRANT_CREDITS)
        self.assertEqual(prop["status"], "AWAITING_CONFIRMATION")
        self.assertEqual(prop["payload"]["credits"], 5.0)

    def test_execute_confirmed_admin_action_rbac_and_grant_credits(self):
        """Verify role-based access control and state mutation for credit grant."""
        # Viewer attempt -> must be rejected
        viewer_user = {"email": self.viewer_email, "role": "viewer"}
        res_viewer = execute_confirmed_admin_action(
            action_type=AdminActionType.GRANT_CREDITS,
            payload={"target_user": self.test_user_email, "credits": 3.0},
            admin_user=viewer_user
        )
        self.assertFalse(res_viewer["success"])
        self.assertIn("Forbidden", res_viewer["error"])

        # Owner attempt -> must succeed
        owner_user = {"email": self.owner_email, "role": "owner"}
        res_owner = execute_confirmed_admin_action(
            action_type=AdminActionType.GRANT_CREDITS,
            payload={
                "target_user": self.test_user_email,
                "credits": 4.0,
                "reason": "TASK_REMEDY",
                "admin_note": "Copilot Unit Test Grant"
            },
            admin_user=owner_user
        )
        self.assertTrue(res_owner.get("success"), f"Grant failed: {res_owner}")
        self.assertEqual(res_owner.get("credits_added"), 4.0)

        # Verify new balance via tool
        user_info = tool_lookup_user_account(self.test_user_email)
        self.assertGreaterEqual(user_info["credits_balance"], 4.0)

    def test_execute_confirmed_admin_action_ticket_update(self):
        """Verify support grievance ticket status update via action engine."""
        tkt = create_support_ticket(
            user_email="copilot_tkt@example.com",
            subject="Test Inquiry for Copilot",
            message="Needs resolution"
        )
        ticket_id = tkt["ticket_id"]

        owner_user = {"email": self.owner_email, "role": "owner"}
        res_update = execute_confirmed_admin_action(
            action_type=AdminActionType.UPDATE_TICKET,
            payload={
                "ticket_id": ticket_id,
                "status": "resolved",
                "admin_notes": "Resolved via Copilot Action Execution"
            },
            admin_user=owner_user
        )
        self.assertTrue(res_update["success"])
        self.assertEqual(res_update["status"], "resolved")

        # Verify ticket in DB
        tickets = get_support_tickets(status="resolved", limit=10, exclude_tests=False)
        found = any(t["ticket_id"] == ticket_id for t in tickets)
        self.assertTrue(found)

    def test_execute_confirmed_admin_action_purge_test_data(self):
        """Verify purging test telemetry via action engine."""
        owner_user = {"email": self.owner_email, "role": "owner"}
        res_purge = execute_confirmed_admin_action(
            action_type=AdminActionType.PURGE_TEST_DATA,
            payload={},
            admin_user=owner_user
        )
        self.assertTrue(res_purge["success"])
        self.assertIn("counts", res_purge)

    def test_process_admin_copilot_turn_analytical_query(self):
        """Verify analytical Q&A queries return grounded data answers without proposals."""
        import asyncio
        owner_user = {"email": self.owner_email, "role": "owner"}

        res = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="What are our unique sessions and total actions this month?"
        ))
        self.assertIn("Executive Telemetry & Site Usage", res["reply"])
        self.assertIsNone(res["action_proposal"])
        self.assertIn("COMPLETED", res["status"])

    def test_process_admin_copilot_turn_grant_credits_intent(self):
        """Verify credit grant requests generate a structured action proposal."""
        import asyncio
        owner_user = {"email": self.owner_email, "role": "owner"}

        res = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message=f"Grant 5.0 credits to {self.test_user_email} for downtime remedy"
        ))
        self.assertIsNotNone(res["action_proposal"])
        prop = res["action_proposal"]
        self.assertEqual(prop["action_type"], AdminActionType.GRANT_CREDITS)
        self.assertEqual(prop["payload"]["target_user"], self.test_user_email)
        self.assertEqual(prop["payload"]["credits"], 5.0)
        self.assertTrue(prop["requires_confirmation"])

    def test_process_admin_copilot_turn_grant_credits_to_self(self):
        """Verify credit requests targeting 'myself' or 'me' automatically resolve to admin email and directly execute."""
        import asyncio
        from core.db.users import get_user_by_email
        owner_user = {"email": self.owner_email, "role": "owner"}

        # Fetch baseline balance (ensuring account initialized)
        from core.db.users import get_or_create_user
        u_before = get_user_by_email(self.owner_email)
        if not u_before:
            u_before = get_or_create_user(user_id="usr_owner_test", email=self.owner_email, full_name="Owner")
        base_bal = float(u_before.get("credits_balance", 0.0))

        # 1. "send some credits to myself" -> Auto-executes without confirmation friction
        res1 = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="send some credits to myself"
        ))
        self.assertIsNone(res1["action_proposal"])
        self.assertEqual(res1["status"], "COMPLETED_EXECUTED")
        self.assertIn("Successfully Granted 5.0 Research Credits", res1["reply"])
        self.assertEqual(res1["new_balance"], base_bal + 5.0)

        # Verify in database
        u_after1 = get_user_by_email(self.owner_email)
        self.assertEqual(float(u_after1["credits_balance"]), base_bal + 5.0)

        # 2. "give me 10 credits"
        res2 = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="give me 10 credits"
        ))
        self.assertIsNone(res2["action_proposal"])
        self.assertEqual(res2["status"], "COMPLETED_EXECUTED")
        self.assertIn("Successfully Granted 10.0 Research Credits", res2["reply"])
        self.assertEqual(res2["new_balance"], base_bal + 15.0)

        u_after2 = get_user_by_email(self.owner_email)
        self.assertEqual(float(u_after2["credits_balance"]), base_bal + 15.0)

    def test_api_admin_copilot_chat_endpoint_unauthorized(self):
        """Verify /api/admin/copilot/chat blocks unauthenticated access with 403."""
        res = self.client.post(
            "/api/admin/copilot/chat",
            json={"message": "How many sessions today?"}
        )
        self.assertEqual(res.status_code, 403)

    def test_api_admin_copilot_chat_endpoint_authenticated(self):
        """Verify /api/admin/copilot/chat responds 200 with reply for authenticated admin."""
        self.client.cookies.set(ADMIN_COOKIE_NAME, self.owner_token)
        res = self.client.post(
            "/api/admin/copilot/chat",
            json={
                "message": "Summarize our net cash inflow and billables.",
                "context": {"window": "30d", "include_tests": 0}
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("Cash Flow & Revenue Diagnostics", data.get("reply", ""))

    def test_api_admin_copilot_execute_endpoint(self):
        """Verify /api/admin/copilot/execute executes confirmed proposals."""
        self.client.cookies.set(ADMIN_COOKIE_NAME, self.owner_token)
        res = self.client.post(
            "/api/admin/copilot/execute",
            json={
                "action_type": AdminActionType.GRANT_CREDITS,
                "payload": {
                    "target_user": self.test_user_email,
                    "credits": 2.0,
                    "reason": "TASK_REMEDY",
                    "admin_note": "API execute endpoint test"
                },
                "proposal_id": "prop_test_123"
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("credits_added"), 2.0)


if __name__ == "__main__":
    unittest.main()
