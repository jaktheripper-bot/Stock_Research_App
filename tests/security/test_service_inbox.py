"""
Tests for Service Inbox, direct ticket responses, and email dispatch.
"""

import unittest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from core.db.connection import init_db
from core.db.support import (
    create_support_ticket,
    get_support_tickets,
    get_ticket_by_id,
    add_ticket_response,
    get_ticket_responses,
    update_ticket_status,
)
from core.notify import send_ticket_reply_email
from core.agents.copilot.admin_copilot import execute_confirmed_admin_action, AdminActionType
from web.main import app


class TestServiceInboxAndEmailReply(unittest.TestCase):
    def setUp(self):
        init_db()
        self.client = TestClient(app)
        # Create a test ticket
        ticket_res = create_support_ticket(
            user_email="inbox_tester@test.com",
            subject="Question regarding DCF hurdle rate",
            message="Why is the WACC hurdle rate set to 12.5% for midcaps?",
            user_name="Priya Patel",
            category="research",
            source="web_contact"
        )
        self.ticket_id = ticket_res["ticket_id"]

    def test_add_and_retrieve_ticket_responses(self):
        """Test recording responses in ticket_responses and retrieving conversation thread."""
        resp1 = add_ticket_response(
            ticket_id=self.ticket_id,
            message="We received your query and our research analyst is reviewing the WACC assumption.",
            sender_email="admin@moatnomics.com",
            sender_name="Moatnomics Service Desk",
            sender_type="admin",
            email_dispatched=True
        )
        self.assertTrue(resp1["success"])
        self.assertEqual(resp1["ticket_id"], self.ticket_id)
        self.assertTrue(resp1["email_dispatched"])

        # Add second response
        resp2 = add_ticket_response(
            ticket_id=self.ticket_id,
            message="The 12.5% WACC hurdle incorporates a 7.0% 10Y G-Sec risk-free rate plus a 5.5% equity risk premium.",
            sender_email="admin@moatnomics.com",
            sender_name="Moatnomics Service Desk",
            sender_type="admin",
            email_dispatched=True
        )
        self.assertTrue(resp2["success"])

        # Fetch thread
        thread = get_ticket_responses(self.ticket_id)
        self.assertGreaterEqual(len(thread), 2)
        self.assertIn("WACC assumption", thread[0]["message"])
        self.assertIn("12.5% WACC hurdle", thread[1]["message"])

        # Fetch single ticket with responses
        ticket = get_ticket_by_id(self.ticket_id, include_responses=True)
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["ticket_id"], self.ticket_id)
        self.assertEqual(ticket["user_name"], "Priya Patel")
        self.assertEqual(ticket["user_email"], "inbox_tester@test.com")
        self.assertGreaterEqual(len(ticket["responses"]), 2)

    def test_send_ticket_reply_email_mock_fallback(self):
        """Test that send_ticket_reply_email gracefully falls back to logging without crashing and returns False when unconfigured."""
        with patch.dict("os.environ", {
            "RESEND_API_KEY": "",
            "SMTP_HOST": "",
            "SMTP_USER": "",
            "SMTP_PASSWORD": ""
        }):
            ticket = get_ticket_by_id(self.ticket_id)
            ok = send_ticket_reply_email(
                ticket=ticket,
                reply_message="This is a test response dispatched to the user."
            )
            self.assertFalse(ok)

    @patch("smtplib.SMTP")
    def test_send_ticket_reply_email_with_smtp(self, mock_smtp_cls):
        """Test SMTP STARTTLS dispatch on port 587 when credentials are configured."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        with patch.dict("os.environ", {
            "RESEND_API_KEY": "",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "mailer@moatnomics.com",
            "SMTP_PASSWORD": "secretpassword",
            "SMTP_FROM": "support@moatnomics.com"
        }):
            ticket = get_ticket_by_id(self.ticket_id)
            ok = send_ticket_reply_email(
                ticket=ticket,
                reply_message="Official response dispatched through secure SMTP TLS."
            )
            self.assertTrue(ok)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_with("mailer@moatnomics.com", "secretpassword")
            mock_server.send_message.assert_called_once()

    @patch("smtplib.SMTP_SSL")
    def test_send_ticket_reply_email_with_smtp_ssl(self, mock_smtp_ssl_cls):
        """Test SMTP SSL dispatch on port 465."""
        mock_server = MagicMock()
        mock_smtp_ssl_cls.return_value.__enter__.return_value = mock_server

        with patch.dict("os.environ", {
            "RESEND_API_KEY": "",
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "465",
            "SMTP_USER": "mailer@moatnomics.com",
            "SMTP_PASSWORD": "secretpassword",
            "SMTP_FROM": "support@moatnomics.com"
        }):
            ticket = get_ticket_by_id(self.ticket_id)
            ok = send_ticket_reply_email(
                ticket=ticket,
                reply_message="Official response dispatched through secure SMTP SSL 465."
            )
            self.assertTrue(ok)
            mock_server.login.assert_called_with("mailer@moatnomics.com", "secretpassword")
            mock_server.send_message.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_send_ticket_reply_email_with_resend(self, mock_urlopen):
        """Test HTTP REST API email dispatch when RESEND_API_KEY is configured."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.dict("os.environ", {
            "RESEND_API_KEY": "re_test_key_xyz",
            "SMTP_FROM": "support@moatnomics.com"
        }):
            ticket = get_ticket_by_id(self.ticket_id)
            ok = send_ticket_reply_email(
                ticket=ticket,
                reply_message="Official response dispatched through Resend REST API."
            )
            self.assertTrue(ok)
            mock_urlopen.assert_called_once()

    def test_admin_reply_ticket_auth_enforced(self):
        """Test that unauthenticated requests to POST /admin/tickets/{ticket_id}/reply are rejected."""
        resp = self.client.post(
            f"/admin/tickets/{self.ticket_id}/reply",
            data={"reply_message": "Unauthorized attempt", "status": "resolved"}
        )
        self.assertEqual(resp.status_code, 403)

    @patch("web.routers.admin.send_ticket_reply_email", return_value=True)
    @patch("web.routers.admin._is_admin_authenticated")
    def test_admin_reply_ticket_endpoint_flow(self, mock_auth, mock_send_email):
        """Test the full admin reply endpoint flow with status update and email dispatch."""
        mock_auth.return_value = {
            "email": "owner@moatnomics.com",
            "role": "owner"
        }

        # 1. API thread check
        thread_resp = self.client.get(f"/api/admin/tickets/{self.ticket_id}/thread")
        self.assertEqual(thread_resp.status_code, 200)
        data = thread_resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["ticket"]["ticket_id"], self.ticket_id)

        # 2. Post reply via form/AJAX
        reply_resp = self.client.post(
            f"/admin/tickets/{self.ticket_id}/reply",
            headers={"X-Requested-With": "XMLHttpRequest"},
            data={
                "reply_message": "We have updated the equity risk premium schedule for you.",
                "status": "resolved",
                "dispatch_email": "on",
                "grant_remedial_credits": "0.0"
            }
        )
        self.assertEqual(reply_resp.status_code, 200)
        reply_json = reply_resp.json()
        self.assertTrue(reply_json["success"])
        self.assertEqual(reply_json["new_status"], "resolved")
        mock_send_email.assert_called_once()

        # Verify state in DB
        ticket_after = get_ticket_by_id(self.ticket_id, include_responses=True)
        self.assertEqual(ticket_after["status"], "resolved")
        self.assertGreaterEqual(len(ticket_after["responses"]), 1)
        self.assertIn("equity risk premium", ticket_after["responses"][-1]["message"])

    @patch("core.agents.copilot.admin_copilot.send_ticket_reply_email", return_value=True)
    @patch("core.agents.copilot.admin_copilot.get_admin_user")
    def test_copilot_reply_ticket_action(self, mock_get_admin, mock_send_email):
        """Test REPLY_TICKET action via Admin Copilot."""
        mock_get_admin.return_value = {"email": "admin@moatnomics.com", "role": "admin"}
        action_res = execute_confirmed_admin_action(
            action_type=AdminActionType.REPLY_TICKET,
            payload={
                "ticket_id": self.ticket_id,
                "reply_message": "Automated analytical guidance dispatched from Executive Copilot.",
                "status": "resolved",
                "dispatch_email": True
            },
            admin_user={"email": "admin@moatnomics.com", "role": "admin"}
        )
        self.assertTrue(action_res["success"])
        self.assertEqual(action_res["ticket_id"], self.ticket_id)
        mock_send_email.assert_called_once()

    @patch("web.routers.admin._is_admin_authenticated")
    @patch("web.routers.admin.send_ticket_reply_email", return_value=True)
    def test_api_admin_reply_ticket_endpoint(self, mock_send_email, mock_auth):
        """Test AJAX JSON POST /api/admin/tickets/reply endpoint."""
        mock_auth.return_value = {
            "email": "owner@moatnomics.com",
            "role": "owner"
        }

        # 1. Post reply via AJAX alias endpoint
        reply_resp = self.client.post(
            "/api/admin/tickets/reply",
            headers={"Accept": "application/json"},
            data={
                "ticket_id": self.ticket_id,
                "reply_message": "Updated terminal growth assumption via AJAX API.",
                "status": "resolved",
                "dispatch_email": "on",
                "grant_remedial_credits": "1.0"
            }
        )
        self.assertEqual(reply_resp.status_code, 200)
        reply_json = reply_resp.json()
        self.assertTrue(reply_json["success"])
        self.assertEqual(reply_json["ticket_id"], self.ticket_id)
        self.assertEqual(reply_json["new_status"], "resolved")
        self.assertTrue(reply_json.get("email_status_text"))

        # 2. Assert ticket in DB has response
        ticket_after = get_ticket_by_id(self.ticket_id, include_responses=True)
        self.assertEqual(ticket_after["status"], "resolved")
        self.assertTrue(any("terminal growth" in r["message"] for r in ticket_after["responses"]))

        # 3. Missing ticket_id returns 400
        bad_resp = self.client.post(
            "/api/admin/tickets/reply",
            headers={"Accept": "application/json"},
            data={"reply_message": "Missing ticket id"}
        )
        self.assertEqual(bad_resp.status_code, 400)

    @patch("web.routers.admin._is_admin_authenticated")
    @patch("web.routers.admin.send_ticket_reply_email", return_value=True)
    def test_api_reply_without_accept_header_updates_status_and_returns_json(self, mock_send_email, mock_auth):
        """Regression test: browser fetch('/api/admin/tickets/reply') with default Accept: */* must return JSON and persist status."""
        mock_auth.return_value = {"email": "owner@moatnomics.com", "role": "owner"}

        # Change status to in_progress during reply with default Accept: */*
        r1 = self.client.post(
            "/api/admin/tickets/reply",
            headers={"Accept": "*/*"},
            data={
                "ticket_id": self.ticket_id,
                "reply_message": "Investigating your DCF query now.",
                "status": "in_progress",
                "dispatch_email": "on",
            },
            follow_redirects=False,
        )
        self.assertEqual(r1.status_code, 200)
        j1 = r1.json()
        self.assertTrue(j1["success"])
        self.assertEqual(j1["new_status"], "in_progress")
        self.assertEqual(get_ticket_by_id(self.ticket_id)["status"], "in_progress")

        # Change status to closed during second reply
        r2 = self.client.post(
            "/api/admin/tickets/reply",
            headers={"Accept": "*/*"},
            data={
                "ticket_id": self.ticket_id,
                "reply_message": "Closing ticket after resolution.",
                "status": "closed",
                "dispatch_email": "on",
            },
            follow_redirects=False,
        )
        self.assertEqual(r2.status_code, 200)
        j2 = r2.json()
        self.assertTrue(j2["success"])
        self.assertEqual(j2["new_status"], "closed")
        self.assertEqual(get_ticket_by_id(self.ticket_id)["status"], "closed")

    @patch("web.routers.admin._is_admin_authenticated")
    def test_ajax_status_toggle_no_reload(self, mock_auth):
        """Test inline status toggle via /api/admin/tickets/{id}/status returns 200 JSON without 303 page reload."""
        mock_auth.return_value = {"email": "owner@moatnomics.com", "role": "owner"}

        for next_st in ("in_progress", "resolved", "closed", "open"):
            resp = self.client.post(
                f"/api/admin/tickets/{self.ticket_id}/status",
                data={"status": next_st},
                follow_redirects=False,
            )
            self.assertEqual(resp.status_code, 200)
            payload = resp.json()
            self.assertTrue(payload["success"])
            self.assertEqual(payload["new_status"], next_st)
            self.assertIn("open_tickets_count", payload)
            self.assertEqual(get_ticket_by_id(self.ticket_id)["status"], next_st)

    @patch("web.routers.admin._is_admin_authenticated")
    def test_active_vs_archived_inbox_partitioning_and_search(self, mock_auth):
        """Test that active inbox only contains open/in_progress and archived contains resolved/closed with search & sort."""
        mock_auth.return_value = {"email": "owner@moatnomics.com", "role": "owner"}

        t_open = create_support_ticket(
            user_email="rahul.sharma@domain.in",
            subject="Active Open Inquiry",
            message="Need help with mutual fund direct vs regular expense ratio",
            user_name="Rahul Sharma",
            category="general",
        )["ticket_id"]
        t_prog = create_support_ticket(
            user_email="ananya.verma@domain.in",
            subject="Active In-Progress Inquiry",
            message="Checking bond yield to maturity calculation",
            user_name="Ananya Verma",
            category="technical",
        )["ticket_id"]
        update_ticket_status(t_prog, "in_progress")

        t_res = create_support_ticket(
            user_email="vikram.mehta@domain.in",
            subject="Archived Resolved Ticket",
            message="Billing invoice GST reconciliation completed",
            user_name="Vikram Mehta",
            category="billing",
        )["ticket_id"]
        add_ticket_response(t_res, message="UniqueArchiveReplyKeyword991", sender_email="admin@moatnomics.com")
        update_ticket_status(t_res, "resolved")

        t_closed = create_support_ticket(
            user_email="neha.kapoor@domain.in",
            subject="Archived Closed Ticket",
            message="Duplicate inquiry closed",
            user_name="Neha Kapoor",
            category="general",
        )["ticket_id"]
        update_ticket_status(t_closed, "closed")

        active_tickets = get_support_tickets(status="active", limit=200, exclude_tests=False)
        active_ids = {t["ticket_id"] for t in active_tickets}
        self.assertIn(t_open, active_ids)
        self.assertIn(t_prog, active_ids)
        self.assertNotIn(t_res, active_ids)
        self.assertNotIn(t_closed, active_ids)

        archived_tickets = get_support_tickets(status="archived", limit=200, exclude_tests=False)
        archived_ids = {t["ticket_id"] for t in archived_tickets}
        self.assertIn(t_res, archived_ids)
        self.assertIn(t_closed, archived_ids)
        self.assertNotIn(t_open, archived_ids)
        self.assertNotIn(t_prog, archived_ids)

        # Search archive via API by reply message keyword
        search_resp = self.client.get(
            "/api/admin/tickets/search",
            params={"status": "archived", "q": "UniqueArchiveReplyKeyword991", "include_tests": 1, "sort_by": "newest"}
        )
        self.assertEqual(search_resp.status_code, 200)
        s_data = search_resp.json()
        self.assertTrue(s_data["success"])
        found_ids = [t["ticket_id"] for t in s_data["tickets"]]
        self.assertIn(t_res, found_ids)
        self.assertNotIn(t_open, found_ids)

    @patch("web.routers.admin._is_admin_authenticated")
    def test_canned_responses_crud_endpoints(self, mock_auth):
        """Test listing, saving, and deleting custom canned responses."""
        mock_auth.return_value = {"email": "owner@moatnomics.com", "role": "owner"}

        # 1. List initial canned responses (seeds defaults)
        list_resp = self.client.get("/api/admin/tickets/canned-responses")
        self.assertEqual(list_resp.status_code, 200)
        initial_items = list_resp.json()["canned_responses"]
        self.assertGreaterEqual(len(initial_items), 4)

        # 2. Save a new custom canned response
        save_resp = self.client.post(
            "/api/admin/tickets/canned-responses",
            json={
                "title": "Custom KYC Verification Follow-up",
                "body": "Hello {{user_name}}, your account verification has been completed.",
                "target_status": "resolved",
                "default_credits": 1.0,
                "category": "general"
            }
        )
        self.assertEqual(save_resp.status_code, 200)
        save_data = save_resp.json()
        self.assertTrue(save_data["success"])
        new_id = save_data["canned_response"]["id"]
        self.assertTrue(new_id > 0)

        # 3. Delete the custom canned response
        del_resp = self.client.delete(f"/api/admin/tickets/canned-responses/{new_id}")
        self.assertEqual(del_resp.status_code, 200)
        self.assertTrue(del_resp.json()["success"])

    @patch("web.routers.admin._is_admin_authenticated")
    def test_admin_tickets_tab_outside_in_dom_contracts(self, mock_auth):
        """Verify rendered DOM contracts for Active Service Inbox, Archive, Canned Responses, and Spell Check."""
        from bs4 import BeautifulSoup
        mock_auth.return_value = {"email": "owner@moatnomics.com", "role": "owner"}

        resp = self.client.get("/admin?tab=tickets&include_tests=1")
        self.assertEqual(resp.status_code, 200)
        soup = BeautifulSoup(resp.text, "html.parser")

        self.assertIsNotNone(soup.find(id="activeTicketsTable"))
        self.assertIsNotNone(soup.find(id="archivedTicketsTable"))
        self.assertIsNotNone(soup.find(id="archiveSearchInput"))
        self.assertIsNotNone(soup.find(id="archiveStatusFilter"))
        self.assertIsNotNone(soup.find(id="archiveSortSelect"))
        self.assertIsNotNone(soup.find(id="saveCannedResponseBar"))
        self.assertIsNotNone(soup.find(id="cannedResponseTitleInput"))
        self.assertIsNotNone(soup.find(id="replySpellCheckTray"))
        self.assertIsNotNone(soup.find(id="btnRunSpellCheck"))

        reply_textarea = soup.find(id="ticketReplyMessage")
        self.assertIsNotNone(reply_textarea)
        self.assertEqual(reply_textarea.get("spellcheck"), "true")
        self.assertEqual(reply_textarea.get("lang"), "en")


if __name__ == "__main__":
    unittest.main()

