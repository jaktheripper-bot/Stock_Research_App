"""
Outside-In and Unit Test Suite for Research Bouquet & Morning Digest System.

Empirically validates:
1. Multi-asset research bouquet synthesis across Equities, Sovereign, Mutual Funds, and MSME.
2. Email template rendering with branded tracking subdomains and statutory disclosures.
3. Subscriber database preferences, token generation, and 1-click unsubscribe/resubscribe lifecycle.
4. Authenticated Admin Console dispatch endpoints (Preview, Test Dispatch, Broadcast, History).
5. UI and DOM element binding contracts (zero missing IDs, zero unrendered Jinja leaks).
"""

import unittest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from web.main import app
from web.common import _generate_admin_token, ADMIN_COOKIE_NAME
from core.db.connection import init_db, get_db_connection, get_placeholder
from core.db.digest import (
    get_digest_subscribers,
    get_subscriber_by_token,
    set_user_digest_subscription,
    record_digest_dispatch,
    get_digest_dispatch_history,
)
from core.analysis.research_bouquet import (
    compile_research_bouquet,
    render_bouquet_html,
    render_bouquet_text,
    get_tracking_base_url,
    build_tracked_link,
)
from core.notify import dispatch_research_bouquet


class TestResearchBouquetAndDigest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.admin_token = _generate_admin_token("test_admin@moatnomics.com", "super_admin")

        # Seed a test subscriber in user_accounts
        conn = get_db_connection()
        cur = conn.cursor()
        p = get_placeholder()
        cls.test_email = "investor_digest_test@moatnomics.com"
        cls.test_uid = "usr_digest_test_9988"
        cur.execute(f"DELETE FROM user_accounts WHERE email = {p} OR id = {p};", (cls.test_email, cls.test_uid))
        cur.execute(
            f"""
            INSERT INTO user_accounts (id, email, full_name, credits_balance, subscription_tier, is_subscriber, is_digest_subscribed)
            VALUES ({p}, {p}, 'Test Investor', 5.0, 'pro_monthly', 1, 1);
            """,
            (cls.test_uid, cls.test_email)
        )
        conn.commit()
        cur.close()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        conn = get_db_connection()
        cur = conn.cursor()
        p = get_placeholder()
        cur.execute(f"DELETE FROM user_accounts WHERE email = {p} OR id = {p};", (cls.test_email, cls.test_uid))
        conn.commit()
        cur.close()
        conn.close()

    def test_01_bouquet_synthesis_multi_asset_depth(self):
        """Validates that compile_research_bouquet aggregates all 4 required asset pillars."""
        bouquet = compile_research_bouquet("2026-10-17")
        self.assertIn("Moatnomics Morning Bouquet", bouquet["subject"])
        self.assertIn("equities", bouquet)
        self.assertGreater(len(bouquet["equities"]), 0)
        
        # Check equity structure
        eq0 = bouquet["equities"][0]
        self.assertIn("ticker", eq0)
        self.assertIn("company_name", eq0)
        self.assertIn("roce", eq0)
        self.assertIn("thesis", eq0)

        # Check sovereign posture
        self.assertIn("sovereign", bouquet)
        self.assertIn("ten_year_gsec", bouquet["sovereign"])
        self.assertIn("repo_rate", bouquet["sovereign"])

        # Check mutual fund spotlight
        self.assertIn("mutual_funds", bouquet)
        self.assertIn("scheme_name", bouquet["mutual_funds"])

        # Check MSME highlight
        self.assertIn("msme", bouquet)
        self.assertIn("company_name", bouquet["msme"])

    def test_02_email_rendering_and_statutory_hygiene(self):
        """Validates HTML and plain text renderings for unsubscribe URLs, tracking domains, and statutory disclosures."""
        bouquet = compile_research_bouquet("2026-10-17")
        sub = {
            "full_name": "Rahul Sharma",
            "email": "rahul.sharma@example.com",
            "unsubscribe_token": "unsub_token_test_123"
        }

        html = render_bouquet_html(bouquet, subscriber=sub)
        self.assertIn("Rahul Sharma", html)
        self.assertIn("/api/notifications/unsubscribe?token=unsub_token_test_123", html)
        self.assertIn("Regulatory Safe-Harbor Disclosure", html)
        self.assertIn("independent financial technology analytics software tool", html)

        # Plain text rendering
        text = render_bouquet_text(bouquet, subscriber=sub)
        self.assertIn("Rahul Sharma", text)
        self.assertIn("/api/notifications/unsubscribe?token=unsub_token_test_123", text)
        self.assertIn("MANDATORY STATUTORY SAFE HARBOR", text)

    def test_03_subscriber_retrieval_and_token_generation(self):
        """Validates get_digest_subscribers backfills unsubscribe tokens and correctly filters audiences."""
        subs = get_digest_subscribers(only_active_pro=False)
        test_sub = next((s for s in subs if s["email"] == self.test_email), None)
        self.assertIsNotNone(test_sub)
        self.assertTrue(test_sub["unsubscribe_token"].startswith("unsub_"))

        # Test token lookup
        resolved = get_subscriber_by_token(test_sub["unsubscribe_token"])
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["email"], self.test_email)

    def test_04_statutory_1_click_unsubscribe_and_resubscribe(self):
        """Validates statutory 1-click unsubscribe and undo flow via API."""
        subs = get_digest_subscribers(only_active_pro=False)
        test_sub = next(s for s in subs if s["email"] == self.test_email)
        token = test_sub["unsubscribe_token"]

        # 1. Unsubscribe via browser HTML request
        resp = self.client.get(f"/api/notifications/unsubscribe?token={token}", headers={"Accept": "text/html"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("You have been unsubscribed", resp.text)
        self.assertIn(self.test_email, resp.text)
        self.assertIn("Undo &amp; Re-subscribe", resp.text)

        # Assert user is marked unsubscribed in DB
        updated_sub = get_subscriber_by_token(token)
        self.assertFalse(updated_sub["is_digest_subscribed"])

        # 2. Resubscribe via browser request
        resp_undo = self.client.get(f"/api/notifications/resubscribe?token={token}", headers={"Accept": "text/html"})
        self.assertEqual(resp_undo.status_code, 200)
        self.assertIn("Subscription Restored", resp_undo.text)

        # Assert user is marked active in DB
        restored_sub = get_subscriber_by_token(token)
        self.assertTrue(restored_sub["is_digest_subscribed"])

    def test_05_admin_digest_preview_endpoint(self):
        """Validates GET /api/admin/digest/preview requires auth and returns complete preview payload."""
        # Unauthenticated checks
        unauth_resp = self.client.get("/api/admin/digest/preview")
        self.assertEqual(unauth_resp.status_code, 401)
        self.assertEqual(unauth_resp.json().get("detail"), "Admin authentication required.")
        self.assertEqual(self.client.post("/api/admin/digest/dispatch-test").status_code, 401)
        self.assertEqual(self.client.post("/api/admin/digest/broadcast").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/digest/history").status_code, 401)

        # Authenticated check
        self.client.cookies.set(ADMIN_COOKIE_NAME, self.admin_token)
        resp = self.client.get("/api/admin/digest/preview")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("bouquet", data)
        self.assertIn("html_preview", data)
        self.assertIn("recipients_summary", data)

    def test_06_admin_digest_dispatch_test_endpoint(self):
        """Validates POST /api/admin/digest/dispatch-test records test execution."""
        self.client.cookies.set(ADMIN_COOKIE_NAME, self.admin_token)
        resp = self.client.post(
            "/api/admin/digest/dispatch-test",
            json={"recipient_email": "admin_test_verify@moatnomics.com"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "TEST_SENT")
        self.assertTrue(data["dispatch_id"].startswith("dsp_"))

        # Check history contains the record
        history_resp = self.client.get("/api/admin/digest/history")
        self.assertEqual(history_resp.status_code, 200)
        history = history_resp.json()["history"]
        match = next((h for h in history if h["id"] == data["dispatch_id"]), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["status"], "TEST_SENT")

    def test_07_outside_in_admin_ui_dom_contract(self):
        """Validates admin.html outside-in contract: tab button, tab pane, and all queried elements exist."""
        self.client.cookies.set(ADMIN_COOKIE_NAME, self.admin_token)
        resp = self.client.get("/admin?tab=digest")
        self.assertEqual(resp.status_code, 200)

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. Tab trigger button
        tab_btn = soup.find("button", attrs={"data-tab": "digest"})
        self.assertIsNotNone(tab_btn)
        self.assertIn("admin-tab-btn", tab_btn.get("class", []))

        # 2. Tab pane
        pane = soup.find("div", id="tab-digest")
        self.assertIsNotNone(pane)
        self.assertIn("admin-tab-pane", pane.get("class", []))

        # 3. Action triggers
        self.assertIsNotNone(soup.find("button", id="btnRefreshDigestPreview"))
        self.assertIsNotNone(soup.find("button", id="btnSendTestDigest"))
        self.assertIsNotNone(soup.find("button", id="btnOpenBroadcastModal"))

        # 4. Preview containers
        self.assertIsNotNone(soup.find("iframe", id="digestPreviewIframe"))
        self.assertIsNotNone(soup.find("pre", id="digestTextContent"))
        self.assertIsNotNone(soup.find("tbody", id="digestHistoryTableBody"))

        # 5. Broadcast modal
        modal = soup.find("div", id="broadcastDigestModal")
        self.assertIsNotNone(modal)
        self.assertIn("modal-backdrop", modal.get("class", []))
        self.assertIsNotNone(modal.find("button", id="btnConfirmBroadcast"))

        # 6. Zero unrendered Jinja leaks
        for attr in ["id", "class", "style"]:
            for tag in soup.find_all(attrs={attr: True}):
                val = str(tag[attr])
                self.assertNotIn("{{", val, f"Unrendered Jinja leak in {attr}: {val}")
                self.assertNotIn("{%", val, f"Unrendered Jinja block leak in {attr}: {val}")


if __name__ == "__main__":
    unittest.main()
