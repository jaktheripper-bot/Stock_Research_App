"""
Outside-In and Unit Test Suite for Research Bouquet & Morning Digest System.

Empirically validates:
1. Multi-asset research bouquet synthesis across Equities, Sovereign, Mutual Funds, and MSME.
2. Email template rendering with branded tracking subdomains and statutory disclosures.
3. Subscriber database preferences, token generation, and 1-click unsubscribe/resubscribe lifecycle.
4. Authenticated Admin Console dispatch endpoints (Preview, Test Dispatch, Broadcast, History).
5. UI and DOM element binding contracts (zero missing IDs, zero unrendered Jinja leaks).
"""

import os
import unittest

os.environ["TESTING"] = "1"

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
    get_emailer_utm_analytics,
    has_edition_been_dispatched,
)
from core.analysis.research_bouquet import (
    BouquetDataUnavailableError,
    compile_research_bouquet,
    render_bouquet_html,
    render_bouquet_text,
    get_tracking_base_url,
    build_tracked_link,
    compute_subscriber_ref,
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

        # Ensure cold-container hermeticity when test_reports.db starts completely empty
        from core.db.discovery import get_active_discovery_reel, save_discovery_reel
        from core.db.reports import get_report_by_ticker_sync, save_report_to_archive
        from core.db.sovereign import get_sovereign_curve_analytics, refresh_daily_sovereign_benchmarks
        from core.db.debt import get_active_debt_securities, seed_default_debt_securities
        from core.db.mutual_funds import get_active_mutual_funds, seed_default_mutual_funds
        from core.msme.seed import seed_default_msme_firms

        if not get_report_by_ticker_sync("TRITURBINE"):
            save_report_to_archive(
                {
                    "ticker": "TRITURBINE",
                    "short_name": "Triveni Turbine Limited",
                    "current_price": 685.0,
                    "pe_ratio": "52.4",
                    "market_cap": 218_000_000_000.0,
                },
                (
                    "### Health Matrix\n- Macro: Stable\n- Moat: Wide\n- Governance: Clean\n"
                    "- Diagnostic: Neutral\n- Valuation: Fair\n- Balance Sheet: Debt-Free\n"
                    "- Capital Allocation: Disciplined\n\n"
                    + ("Triveni Turbine Limited (TRITURBINE) industrial steam turbine aftermarket franchise dossier. " * 12)
                ),
                revision_trigger="Hermetic Bouquet Test Seed",
            )
        if not get_active_discovery_reel(edition_date="2026-10-30", exclude_tests=True, allow_fallback=True):
            save_discovery_reel(
                [
                    {
                        "ticker": "TRITURBINE",
                        "company_name": "Triveni Turbine Limited",
                        "sector": "Capital Goods",
                        "market_cap_tier": "Mid-Cap",
                        "current_price": 685.0,
                        "pe_ratio": "52.4",
                        "roce_pct": 34.2,
                        "debt_to_equity": 0.0,
                        "sales_growth_3y": 28.5,
                        "ria_thesis": "High-margin aftermarket steam turbine servicing franchise with zero debt and 34.2% ROCE.",
                        "catalyst_headline": "Export Aftermarket Backlog Expansion",
                        "key_metrics": {"roce": "34.2%", "debt_to_equity": "0.00x", "pe": "52.4"},
                    }
                ],
                edition_date="2026-10-30",
            )
        if not (get_sovereign_curve_analytics() or {}).get("benchmark_10y_gsec"):
            refresh_daily_sovereign_benchmarks("2026-10-30")
        if not get_active_debt_securities():
            seed_default_debt_securities()
        if not get_active_mutual_funds(limit=1):
            seed_default_mutual_funds()
        seed_default_msme_firms()
        from core.db.sovereign import get_etf_matrix
        from core.analysis.sm_reit_invit_engine import audit_reit_portfolio
        from core.analysis.sgb_engine import evaluate_sgb_market
        get_etf_matrix(limit=5)
        audit_reit_portfolio()
        evaluate_sgb_market()

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
        """Validates that compile_research_bouquet aggregates all 7 required live asset pillars."""
        bouquet = compile_research_bouquet("2026-10-30", require_live_data=True)
        self.assertIn("Moatnomics Day-End Market Wrap", bouquet["subject"])
        self.assertIn("equities", bouquet)
        self.assertGreater(len(bouquet["equities"]), 0)

        # Check equity structure & real ROCE/CMP mapping (zero hardcoded 18.0 Potemkin fallback)
        eq0 = bouquet["equities"][0]
        self.assertIn("ticker", eq0)
        self.assertIn("company_name", eq0)
        self.assertIn("roce", eq0)
        self.assertIn("thesis", eq0)
        self.assertIsNotNone(eq0["cmp"])
        self.assertGreater(eq0["cmp"], 0.0)

        # Check sovereign posture
        self.assertIn("sovereign", bouquet)
        self.assertIn("ten_year_gsec", bouquet["sovereign"])
        self.assertIn("repo_rate", bouquet["sovereign"])

        # Check corporate debt, ETFs, and REITs/SGBs
        self.assertIn("corporate_debt", bouquet)
        self.assertIn("isin", bouquet["corporate_debt"])
        self.assertIn("etfs", bouquet)
        self.assertIn("symbol", bouquet["etfs"])
        self.assertIn("reits_sgb", bouquet)
        self.assertIn("reit_symbol", bouquet["reits_sgb"])

        # Check mutual fund spotlight & Prior-Session AMFI Audit badge
        self.assertIn("mutual_funds", bouquet)
        self.assertIn("scheme_name", bouquet["mutual_funds"])
        self.assertIn("Prior-Session AMFI Audit", bouquet["mutual_funds"]["provenance_badge"])

        # Check MSME highlight
        self.assertIn("msme", bouquet)
        self.assertIn("company_name", bouquet["msme"])

    def test_01b_bouquet_fails_closed_when_live_pillars_missing(self):
        """Validates fail-closed BouquetDataUnavailableError when live asset tables are empty."""
        from unittest.mock import patch

        with patch("core.analysis.research_bouquet._load_live_equities", return_value=[]):
            with self.assertRaises(BouquetDataUnavailableError) as ctx:
                compile_research_bouquet("2026-10-30", require_live_data=True)
            self.assertIn("equities", str(ctx.exception))

    def test_02_email_rendering_and_statutory_hygiene(self):
        """Validates HTML and plain text renderings for all 7 asset sections, domain links, and statutory disclosures."""
        bouquet = compile_research_bouquet("2026-10-30", require_live_data=True)
        sub = {
            "full_name": "Rahul Sharma",
            "email": "rahul.sharma@example.com",
            "unsubscribe_token": "unsub_token_test_123"
        }

        html = render_bouquet_html(bouquet, subscriber=sub)
        self.assertIn("Rahul Sharma", html)
        self.assertIn("Good evening", html)
        self.assertNotIn("antigravity.averagettv.in", html)
        self.assertIn("/api/notifications/unsubscribe?token=unsub_token_test_123", html)
        self.assertIn("Regulatory Safe-Harbor Disclosure", html)
        self.assertIn("independent financial technology analytics software tool", html)
        for sec_num in range(1, 8):
            self.assertIn(f"{sec_num}.", html)

        # Plain text rendering
        text = render_bouquet_text(bouquet, subscriber=sub)
        self.assertIn("Rahul Sharma", text)
        self.assertNotIn("antigravity.averagettv.in", text)
        self.assertIn("/api/notifications/unsubscribe?token=unsub_token_test_123", text)
        self.assertIn("MANDATORY STATUTORY SAFE HARBOR", text)
        for sec_num in range(1, 8):
            self.assertIn(f"{sec_num}.", text)

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

        # 4. Preview containers & UTM attribution panels
        self.assertIsNotNone(soup.find("iframe", id="digestPreviewIframe"))
        self.assertIsNotNone(soup.find("pre", id="digestTextContent"))
        self.assertIsNotNone(soup.find("tbody", id="digestHistoryTableBody"))
        self.assertIsNotNone(soup.find("div", id="digestUtmTotalClicks"))
        self.assertIsNotNone(soup.find("div", id="digestUtmCtrLabel"))
        self.assertIsNotNone(soup.find("div", id="cardEmailerUtmAttribution"))
        self.assertIsNotNone(soup.find("table", id="tableEmailerAssetClicks"))
        self.assertIsNotNone(soup.find("tbody", id="tbodyEmailerAssetClicks"))

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

    def test_08_has_edition_been_dispatched_idempotency(self):
        """Validates has_edition_been_dispatched correctly guards broadcast status without blocking tests."""
        test_date = "2026-10-28"
        conn = get_db_connection()
        cur = conn.cursor()
        p = get_placeholder()
        cur.execute(f"DELETE FROM digest_dispatches WHERE edition_date = {p};", (test_date,))
        conn.commit()
        cur.close()
        conn.close()
        
        # 1. Non-existent date or empty inputs
        self.assertFalse(has_edition_been_dispatched(""))
        self.assertFalse(has_edition_been_dispatched(test_date))

        # 2. TEST_SENT record should NOT mark edition as dispatched
        record_digest_dispatch(
            edition_date=test_date,
            subject="Test Dispatch",
            recipients_count=1,
            delivered_count=1,
            failed_count=0,
            status="TEST_SENT",
        )
        self.assertFalse(has_edition_been_dispatched(test_date))

        # 3. FAILED record should NOT mark edition as dispatched
        record_digest_dispatch(
            edition_date=test_date,
            subject="Failed Dispatch",
            recipients_count=10,
            delivered_count=0,
            failed_count=10,
            status="FAILED",
        )
        self.assertFalse(has_edition_been_dispatched(test_date))

        # 4. COMPLETED record marks edition as dispatched
        record_digest_dispatch(
            edition_date=test_date,
            subject="Completed Broadcast",
            recipients_count=5,
            delivered_count=5,
            failed_count=0,
            status="COMPLETED",
        )
        self.assertTrue(has_edition_been_dispatched(test_date))

        # Cleanup
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM digest_dispatches WHERE edition_date = {p};", (test_date,))
        conn.commit()
        cur.close()
        conn.close()

    def test_09_broadcast_idempotency_guard_and_force_override(self):
        """Validates dispatch_research_bouquet and API broadcast prevent duplicate sends unless forced."""
        test_date = "2026-10-29"
        conn = get_db_connection()
        cur = conn.cursor()
        p = get_placeholder()
        cur.execute(f"DELETE FROM digest_dispatches WHERE edition_date = {p};", (test_date,))
        conn.commit()
        cur.close()
        conn.close()

        # Record initial completed broadcast
        record_digest_dispatch(
            edition_date=test_date,
            subject="Existing Broadcast",
            recipients_count=1,
            delivered_count=1,
            failed_count=0,
            status="COMPLETED",
        )
        self.assertTrue(has_edition_been_dispatched(test_date))

        # Direct function call without force -> ALREADY_DISPATCHED
        res = dispatch_research_bouquet(edition_date=test_date, force=False)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "ALREADY_DISPATCHED")
        self.assertEqual(res["delivered"], 0)

        # Authenticated API broadcast without force -> ALREADY_DISPATCHED
        self.client.cookies.set(ADMIN_COOKIE_NAME, self.admin_token)
        api_res = self.client.post(
            "/api/admin/digest/broadcast",
            json={"edition_date": test_date, "force": False}
        )
        self.assertEqual(api_res.status_code, 200)
        data = api_res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "ALREADY_DISPATCHED")

        # Authenticated API broadcast with force=True -> succeeds and dispatches
        api_res_forced = self.client.post(
            "/api/admin/digest/broadcast",
            json={"edition_date": test_date, "force": True}
        )
        self.assertEqual(api_res_forced.status_code, 200)
        data_forced = api_res_forced.json()
        self.assertTrue(data_forced["success"])
        self.assertIn(data_forced["status"], ("COMPLETED", "PARTIAL"))

        # Cleanup
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM digest_dispatches WHERE edition_date = {p};", (test_date,))
        conn.commit()
        cur.close()
        conn.close()

    def test_10_emailer_utm_tags_and_sub_ref_privacy_contracts(self):
        """Validates Loopholes L1–L6: edition-aware UTM tags, hashed sub_ref (never raw sub_tk on content links), and end-to-end CTR/dwell aggregation."""
        from urllib.parse import urlparse, parse_qs
        import json

        bouquet = compile_research_bouquet("2026-10-30", require_live_data=True)
        raw_token = "unsub_secret_token_991122"
        expected_sub_ref = compute_subscriber_ref(raw_token)
        self.assertTrue(expected_sub_ref.startswith("sub_"))
        self.assertNotIn(raw_token, expected_sub_ref)

        html = render_bouquet_html(
            bouquet,
            subscriber={"full_name": "Rahul Sharma", "email": "rahul@domain.in", "unsubscribe_token": raw_token},
        )
        soup = BeautifulSoup(html, "html.parser")
        links = [a.get("href", "") for a in soup.find_all("a") if a.get("href")]
        self.assertGreaterEqual(len(links), 10)

        content_sections_seen = set()
        for href in links:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            if "/api/notifications/unsubscribe" in parsed.path:
                self.assertEqual(qs.get("token", [""])[0], raw_token)
                self.assertNotIn("sub_ref", qs)
            else:
                # L2: Zero raw unsubscribe tokens on content links; uses non-reversible sub_ref
                self.assertNotIn("sub_tk", qs, f"Raw sub_tk leaked in content link: {href}")
                self.assertNotIn(raw_token, href)
                self.assertEqual(qs.get("sub_ref", [""])[0], expected_sub_ref)
                # L3: Edition-specific campaign & section-specific utm_content
                self.assertEqual(qs.get("utm_source", [""])[0], "moatnomics_digest")
                self.assertEqual(qs.get("utm_medium", [""])[0], "email_digest")
                self.assertEqual(qs.get("utm_campaign", [""])[0], "research_bouquet_2026-10-30")
                self.assertIn("utm_content", qs, f"Missing utm_content on link: {href}")
                content_sections_seen.add(qs["utm_content"][0])

        for expected_sec in (
            "equity_card",
            "sovereign_curve",
            "corporate_debt",
            "etf_matrix",
            "reits_sgb",
            "mutual_fund",
            "msme_spotlight",
            "terminal_cta",
        ):
            self.assertIn(expected_sec, content_sections_seen)

        # L1, L4, L5: Simulate real visitor telemetry landing & dwell from emailer and verify CTR clamping <= 100%
        test_ed = "2026-10-27"
        conn = get_db_connection()
        cur = conn.cursor()
        p = get_placeholder()
        cur.execute(f"DELETE FROM digest_dispatches WHERE edition_date = {p};", (test_ed,))
        cur.execute(f"DELETE FROM site_usage_events WHERE session_id IN ({p}, {p});", ("sess_utm_live_01", "sess_utm_live_02"))
        conn.commit()
        cur.close()
        conn.close()

        try:
            record_digest_dispatch(
                edition_date=test_ed,
                subject="Wrap 2026-10-27",
                recipients_count=2,
                delivered_count=2,
                failed_count=0,
                status="COMPLETED",
            )
            # Same subscriber (sub_ref) opens 2 different asset cards in 2 sessions -> unique_clickers = 1, click_sessions = 2, CTR = 50.0%
            ua_headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36"}
            unauth_client = TestClient(app)
            r1 = unauth_client.post(
                "/api/telemetry/event",
                headers=ua_headers,
                json={
                    "event_type": "DOSSIER_VIEW",
                    "ticker": "RELIANCE",
                    "session_id": "sess_utm_live_01",
                    "landing_page": "/dossier/RELIANCE",
                    "utm_source": "moatnomics_digest",
                    "utm_medium": "email_digest",
                    "utm_campaign": f"research_bouquet_{test_ed}",
                    "utm_content": "equity_card",
                    "utm_term": "RELIANCE",
                    "sub_ref": expected_sub_ref,
                },
            )
            self.assertEqual(r1.status_code, 200)
            self.assertEqual(r1.json().get("status"), "ok")

            r2 = unauth_client.post(
                "/api/telemetry/dwell",
                headers=ua_headers,
                json={
                    "event_type": "PAGE_DWELL",
                    "session_id": "sess_utm_live_01",
                    "path": "/dossier/RELIANCE",
                    "dwell_seconds": 80.0,
                    "utm_source": "moatnomics_digest",
                    "utm_medium": "email_digest",
                    "utm_campaign": f"research_bouquet_{test_ed}",
                    "utm_content": "equity_card",
                    "utm_term": "RELIANCE",
                    "sub_ref": expected_sub_ref,
                },
            )
            self.assertEqual(r2.status_code, 200)

            r3 = unauth_client.post(
                "/api/telemetry/event",
                headers=ua_headers,
                json={
                    "event_type": "PAGE_VIEW",
                    "session_id": "sess_utm_live_02",
                    "landing_page": "/sovereign",
                    "utm_source": "moatnomics_digest",
                    "utm_medium": "email_digest",
                    "utm_campaign": f"research_bouquet_{test_ed}",
                    "utm_content": "sovereign_curve",
                    "utm_term": "10Y_GSEC",
                    "sub_ref": expected_sub_ref,
                },
            )
            self.assertEqual(r3.status_code, 200)

            # Verify automated headless event is filtered out by is_synthetic_test_event
            r_bot = unauth_client.post(
                "/api/telemetry/event",
                headers=ua_headers,
                json={
                    "event_type": "DOSSIER_VIEW",
                    "ticker": "TCS",
                    "session_id": "sess_utm_bot_99",
                    "landing_page": "/dossier/TCS",
                    "utm_source": "moatnomics_digest",
                    "details": {"is_automated": True},
                },
            )
            self.assertEqual(r_bot.json().get("status"), "filtered")

            history = get_digest_dispatch_history(limit=15)
            ed_row = next((h for h in history if h["edition_date"] == test_ed), None)
            self.assertIsNotNone(ed_row)
            self.assertEqual(ed_row["click_sessions"], 2)
            self.assertEqual(ed_row["unique_clickers"], 1)
            self.assertEqual(ed_row["ctr_pct"], 50.0)
            self.assertEqual(ed_row["avg_dwell_seconds"], 40.0)

            utm_summary = get_emailer_utm_analytics()
            self.assertGreaterEqual(utm_summary["total_click_sessions"], 2)
            ab_keys = {a["content_key"] for a in utm_summary["asset_breakdown"]}
            self.assertIn("equity_card", ab_keys)
            self.assertIn("sovereign_curve", ab_keys)
        finally:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(f"DELETE FROM digest_dispatches WHERE edition_date = {p};", (test_ed,))
            cur.execute(f"DELETE FROM site_usage_events WHERE session_id IN ({p}, {p});", ("sess_utm_live_01", "sess_utm_live_02"))
            conn.commit()
            cur.close()
            conn.close()


if __name__ == "__main__":
    unittest.main()
