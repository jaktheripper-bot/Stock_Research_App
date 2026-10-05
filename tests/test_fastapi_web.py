"""Test suite for FastAPI web portal routes, dossier rendering, and momentum charting."""

import os
os.environ["TESTING"] = "1"

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from web.main import app

class TestFastAPIWebPortal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    def test_home_page(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Institutional Equity Research Engine", res.text)
        self.assertIn("ZERO-HALLUCINATION DATA INTEGRITY", res.text)

    def test_pricing_page(self):
        res = self.client.get("/pricing")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Single Research Pass", res.text)
        self.assertIn("₹299", res.text)

    @patch("web.main.compare_two_companies")
    def test_peer_comparison_page(self, mock_compare):
        async def fake_compare(a, b):
            return {
                "ticker_a": a,
                "ticker_b": b,
                "fund_a": {"current_price": 1500.0, "market_cap": 6000000000000.0, "pe_ratio": 24.5, "sector": "Technology"},
                "fund_b": {"current_price": 3800.0, "market_cap": 14000000000000.0, "pe_ratio": 28.1, "sector": "Technology"},
                "matrix_a": {"moat": "Strong", "management": "Stable"},
                "matrix_b": {"moat": "Strong", "management": "Stable"},
                "disparity": {"is_disparate": False, "warnings": []}
            }
        mock_compare.side_effect = fake_compare
        res = self.client.get("/compare?a=INFY&b=TCS")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Cross-Company Peer Comparator", res.text)
        self.assertIn("INFY", res.text)
        self.assertIn("TCS", res.text)

    @patch("web.main.get_stock_fundamentals")
    @patch("web.main.get_historical_prices")
    def test_dossier_infy_rendering_and_chart(self, mock_hist, mock_fund):
        import pandas as pd
        mock_fund.return_value = {
            "current_price": 1520.0,
            "fifty_two_week_low": 1300.0,
            "fifty_two_week_high": 1900.0,
            "pe_ratio": 25.0
        }
        dates = pd.date_range(end=pd.Timestamp.now(), periods=30)
        mock_hist.return_value = pd.DataFrame({
            "Date": dates,
            "Close": [1500.0 + i for i in range(30)],
            "SMA_50": [1480.0] * 30
        })
        res = self.client.get("/dossier/INFY")
        self.assertEqual(res.status_code, 200)
        html = res.text

        # 1. 7-pillar qualitative posture badges are present at top
        self.assertIn("7-Pillar Qualitative Health Matrix:", html)
        self.assertIn("Moat:", html)

        # 2. Redundant raw markdown bullet list is stripped from prose body
        self.assertNotIn("<li>Macro: Headwinds</li>", html)

        # 3. 6-Month Momentum & 50-DMA chart is rendered
        self.assertIn('id="momentumChart"', html)
        self.assertIn("chart.umd.min.js", html)
        self.assertIn("6-Month Price Momentum & 50-DMA Trendline", html)

        # 4. Collapsible 7-pillar accordion structure with exact BSE citations
        self.assertIn("details class=\"pillar-accordion\"", html)
        self.assertIn("Exact Page Grounding:", html)
        self.assertIn("bseindia.com", html)

    def test_discovery_page(self):
        res = self.client.get("/discovery")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Stock Discovery @9AM", res.text)
        self.assertIn("INSTITUTIONAL QUALITY SURVEILLANCE", res.text)
        self.assertIn("Mandatory SEBI Safe-Harbor Disclosure", res.text)

    def test_discovery_db_repository(self):
        from core.db.discovery import save_discovery_reel, get_active_discovery_reel, get_available_discovery_editions
        test_items = [
            {
                "ticker": "TESTCORP",
                "company_name": "Test Diagnostics Corp",
                "sector": "Specialty Chemicals",
                "market_cap_tier": "Small-Cap",
                "current_price": 540.0,
                "pe_ratio": "18.5",
                "roce_pct": 24.5,
                "debt_to_equity": 0.05,
                "sales_growth_3y": 20.0,
                "ria_thesis": "Solid compounding profile under institutional radar.",
                "catalyst_headline": "BSE Announcement: Capacity expansion.",
                "key_metrics": {"roce": "24.5%", "d_e": "0.05"}
            }
        ]
        saved = save_discovery_reel(test_items, edition_date="2026-10-03")
        self.assertGreaterEqual(saved, 1)

        active = get_active_discovery_reel("2026-10-03")
        self.assertTrue(any(item["ticker"] == "TESTCORP" for item in active))

        editions = get_available_discovery_editions()
        self.assertIn("2026-10-03", editions)

    def test_legal_policy_routes(self):
        from web.legal_content import POLICIES
        for slug in POLICIES.keys():
            res = self.client.get(f"/{slug}")
            self.assertEqual(res.status_code, 200, f"Policy route /{slug} failed")

    def test_admin_run_discovery_api(self):
        from unittest.mock import patch
        with patch("scripts.run_discovery_worker.run_discovery_pipeline", return_value=True):
            res = self.client.post("/api/admin/run-discovery?count=10")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data.get("status"), "initiated")

    def test_contact_page_get_and_post(self):
        # 1. GET /contact returns interactive form
        res_get = self.client.get("/contact")
        self.assertEqual(res_get.status_code, 200)
        self.assertIn("Submit an Inquiry or Complaint", res_get.text)
        self.assertIn("Grievance Redressal", res_get.text)

        # 2. POST /contact creates ticket and dispatches alert
        post_data = {
            "user_name": "Test Investor",
            "user_email": "investor@example.com",
            "category": "billing",
            "subject": "Payment credit verification query",
            "message": "Testing automated support ticket dispatch and admin alerting."
        }
        res_post = self.client.post("/contact", data=post_data)
        self.assertEqual(res_post.status_code, 200)
        self.assertIn("Ticket Registered Successfully", res_post.text)
        self.assertIn("TKT-", res_post.text)

    def test_seo_robots_and_sitemap(self):
        res_robots = self.client.get("/robots.txt")
        self.assertEqual(res_robots.status_code, 200)
        self.assertIn("User-agent: *", res_robots.text)
        self.assertIn("Sitemap:", res_robots.text)

        res_sitemap = self.client.get("/sitemap.xml")
        self.assertEqual(res_sitemap.status_code, 200)
        self.assertIn("<urlset", res_sitemap.text)
        self.assertIn("/dossier/INFY", res_sitemap.text)

    def _get_authenticated_admin_client(self):
        from core.db.admin import get_admin_user
        from core.auth.totp import get_totp_code
        client = TestClient(app)
        res_verify = client.post("/admin/auth/direct-verify", data={"email": "lyndnpnto@gmail.com"}, follow_redirects=False)
        pending_cookie = res_verify.cookies["admin_2fa_pending"]
        client.cookies.set("admin_2fa_pending", pending_cookie)

        owner = get_admin_user("lyndnpnto@gmail.com")
        secret = owner.get("totp_secret")
        if not secret:
            client.get("/admin/setup-2fa")
            owner = get_admin_user("lyndnpnto@gmail.com")
            secret = owner["totp_secret"]
            code = get_totp_code(secret)
            res_post = client.post("/admin/setup-2fa", data={"code": code}, follow_redirects=False)
        else:
            code = get_totp_code(secret)
            endpoint = "/admin/verify-2fa" if owner.get("totp_enabled") else "/admin/setup-2fa"
            res_post = client.post(endpoint, data={"code": code}, follow_redirects=False)

        session_cookie = res_post.cookies["admin_session"]
        client.cookies.set("admin_session", session_cookie)
        return client

    def test_admin_unauthenticated_shows_login(self):
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Executive Administrator Portal", res.text)
        self.assertIn("Sign In with Google", res.text)

    def test_admin_login_invalid_user(self):
        res = self.client.post("/admin/auth/direct-verify", data={"email": "unauthorized_user@example.com"}, follow_redirects=False)
        self.assertEqual(res.status_code, 303)
        self.assertIn("err=", res.headers.get("location", ""))

    def test_admin_login_success_and_dashboard_access(self):
        client = self._get_authenticated_admin_client()
        res_dash = client.get("/admin")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn("Executive Telemetry & Site Usage Hub", res_dash.text)
        self.assertIn("Live Billables & Invoices", res_dash.text)
        self.assertIn("Unique Sessions", res_dash.text)
        self.assertIn("Est. API Cost Saved", res_dash.text)
        self.assertIn("Export GSTR-1 Tax Register (CSV)", res_dash.text)
        self.assertIn("Team & Access", res_dash.text)
        self.assertIn("Admin Audit Trail", res_dash.text)

    def test_admin_update_ticket_status(self):
        from core.db.support import create_support_ticket
        client = self._get_authenticated_admin_client()

        # Create ticket
        t = create_support_ticket("test_admin@example.com", "Test Subject", "Test message", user_name="Admin Tester")
        ticket_id = t["ticket_id"]

        # Update status
        res_update = client.post(
            f"/admin/tickets/{ticket_id}/status",
            data={"status": "resolved", "admin_notes": "Tested resolution note."},
            follow_redirects=True
        )
        self.assertEqual(res_update.status_code, 200)
        self.assertIn("Ticket", res_update.text)
        self.assertIn("status updated", res_update.text)

    def test_admin_tax_register_csv_export(self):
        client = self._get_authenticated_admin_client()
        res_csv = client.get("/admin/export/tax-register")
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn("text/csv", res_csv.headers["content-type"])
        self.assertIn("Invoice Number,Date,Customer Email,Customer Name", res_csv.text)
        self.assertIn("GSTR1_Tax_Register", res_csv.headers.get("content-disposition", ""))

    def test_admin_logout(self):
        client = self._get_authenticated_admin_client()
        res_logout = client.get("/admin/logout", follow_redirects=False)
        self.assertEqual(res_logout.status_code, 303)

    def test_debt_directory_page(self):
        res = self.client.get("/debt")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Corporate Bonds & Securitized Debt Directory", res.text)
        self.assertIn("SEBI ₹10,000 Face Value", res.text)
        self.assertIn("RELIANCE", res.text)
        self.assertIn("5-Pillar Credit & Solvency Matrix", res.text)

    def test_debt_dossier_page(self):
        res = self.client.get("/debt/INE002A08012")
        self.assertEqual(res.status_code, 200)
        self.assertIn("RELIANCE", res.text)
        self.assertIn("Pillar 1: Credit Quality & Rating Drift", res.text)
        self.assertIn("Pillar 2: Capital Hierarchy & Seniority Cover", res.text)
        self.assertIn("RBI Repo Rate Shock Sensitivity Model", res.text)

    def test_debt_api_endpoints(self):
        # 1. /api/debt/securities
        res_list = self.client.get("/api/debt/securities")
        self.assertEqual(res_list.status_code, 200)
        data = res_list.json()
        self.assertEqual(data.get("status"), "success")
        self.assertGreater(data.get("count", 0), 0)

        # 2. /api/debt/security/{isin}
        res_sec = self.client.get("/api/debt/security/INE002A08012")
        self.assertEqual(res_sec.status_code, 200)
        sec_data = res_sec.json()
        self.assertEqual(sec_data.get("status"), "success")
        self.assertIn("posture", sec_data)
        self.assertEqual(sec_data["posture"]["posture"], "INSTITUTIONAL_PRIME")

        # 3. /api/debt/ticker/{ticker}
        res_ticker = self.client.get("/api/debt/ticker/RELIANCE")
        self.assertEqual(res_ticker.status_code, 200)
        self.assertEqual(res_ticker.json().get("status"), "success")

        # 4. /api/debt/ratings/actions
        res_act = self.client.get("/api/debt/ratings/actions")
        self.assertEqual(res_act.status_code, 200)
        self.assertEqual(res_act.json().get("status"), "success")

    def test_fund_directory_page(self):
        res = self.client.get("/funds")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Mutual Fund Look-Through & Fiduciary Screener", res.text)
        self.assertIn("Parag Parikh Flexi Cap Fund", res.text)
        self.assertIn("Active Share", res.text)

    def test_fund_dossier_page(self):
        res = self.client.get("/funds/PPFAS_FLEXICAP_DIR")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Parag Parikh Flexi Cap Fund", res.text)
        self.assertIn("Pillar 1: Dual-Sleeve Constituent Decomposition", res.text)
        self.assertIn("Pillar 2: True Diversification & Active Share", res.text)
        self.assertIn("Pillar 5: Intermediary Fee Drag & Wealth Destruction", res.text)

    def test_fund_overlap_page(self):
        res = self.client.get("/funds/compare/overlap?scheme_a=PPFAS_FLEXICAP_DIR&scheme_b=MIRAE_LARGECAP_DIR")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Mutual Fund Portfolio Overlap & Duplication Diagnostic", res.text)
        self.assertIn("Portfolio Overlap Score", res.text)
        self.assertIn("Shared Constituent Holdings", res.text)

    def test_fund_api_endpoints(self):
        # 1. /api/funds/schemes
        res_list = self.client.get("/api/funds/schemes")
        self.assertEqual(res_list.status_code, 200)
        data_list = res_list.json()
        self.assertEqual(data_list.get("status"), "success")
        self.assertGreaterEqual(len(data_list.get("schemes", [])), 6)

        # 2. /api/funds/scheme/{scheme_code}
        res_detail = self.client.get("/api/funds/scheme/PPFAS_FLEXICAP_DIR")
        self.assertEqual(res_detail.status_code, 200)
        data_detail = res_detail.json()
        self.assertEqual(data_detail.get("status"), "success")
        self.assertIn("dossier", data_detail)

        # 3. /api/funds/scheme/{scheme_code}/lookthrough
        res_lt = self.client.get("/api/funds/scheme/PPFAS_FLEXICAP_DIR/lookthrough")
        self.assertEqual(res_lt.status_code, 200)
        self.assertEqual(res_lt.json().get("status"), "success")

        # 4. /api/funds/overlap
        res_over = self.client.get("/api/funds/overlap?scheme_a=PPFAS_FLEXICAP_DIR&scheme_b=MIRAE_LARGECAP_DIR")
        self.assertEqual(res_over.status_code, 200)
        self.assertEqual(res_over.json().get("status"), "success")
        self.assertGreater(res_over.json()["overlap"]["overlap_pct"], 20.0)

        # 5. /api/funds/holding/{identifier}
        res_hold = self.client.get("/api/funds/holding/HDFCBANK")
        self.assertEqual(res_hold.status_code, 200)
        self.assertEqual(res_hold.json().get("status"), "success")
        self.assertGreaterEqual(res_hold.json().get("count", 0), 2)


if __name__ == "__main__":
    unittest.main()

