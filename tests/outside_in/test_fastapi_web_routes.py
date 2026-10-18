"""
tests/outside_in/test_fastapi_web_routes.py
===========================================
Consolidated FastAPI SSR Views & Endpoints Test Suite:
1. Core Web Portal routes (landing, discovery, equities, dossier, funds, debt, calculator, etc.)
2. Opportunity Terminal routes & quantitative screening algorithms
3. Peer Comparison, telemetry journey tracking, and admin exclusions
4. Multi-currency location-aware pricing and forex buffer engine
5. Developer API v1 and custom advisory PDF branding
"""
import os
os.environ["TESTING"] = "1"

import unittest
from fastapi.testclient import TestClient
from web.main import app


"""Test suite for FastAPI web portal routes, dossier rendering, and momentum charting."""

import os
os.environ["TESTING"] = "1"
os.environ.setdefault("ADMIN_PASSWORD", "test_admin_pwd_default")

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from web.main import app

class TestFastAPIWebPortal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.db import save_report_to_archive
        stock_data = {
            "ticker": "INFY",
            "short_name": "Infosys Ltd",
            "current_price": 1520.0,
            "pe_ratio": "25.0",
            "market_cap": 6000000000000.0,
        }
        save_report_to_archive(
            stock_data=stock_data,
            report_text="""### 7-Pillar Qualitative Health Matrix:
- Moat: Strong
- Management: Stable
- Capital Allocation: Clean

## Pillar 1: Long-Term Competitive Moat
Detailed competitive advantage breakdown.

## Pillar 2: Financial Strength & Balance Sheet
Zero long-term debt and high FCF conversion.

## Pillar 3: Corporate Governance & Capital Allocation
Clean historical capital allocation track record.

### Key Fundamental Monitorables
Detailed forensic analysis with exact page grounding to bseindia.com filings.
""",
            announcement="Q2 Earnings release filed with BSE."
        )
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    def test_home_page(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Audit the Asset.", res.text)
        self.assertIn("Protect the Allocator.", res.text)
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
        # Live audit regression: market cap rendered "₹₹" and missing ranges rendered "₹N/A".
        self.assertNotIn("₹₹", res.text)
        self.assertNotIn("₹N/A", res.text)
        self.assertIn("₹1500.0", res.text)

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

        # 4. Collapsible 7-pillar accordion structure with company-specific BSE source links
        self.assertIn("details class=\"pillar-accordion\"", html)
        self.assertIn("Primary Exchange Source:", html)
        self.assertIn("bseindia.com", html)

        # 5. Data-accuracy guards (Audit 1, Batch C)
        self.assertNotIn("Exact Page Grounding", html)          # overstated verification claim removed
        self.assertNotIn("/BSE Listed/", html)                  # no placeholder text inside links
        self.assertNotIn("scrip_cd=BSE Listed", html)
        self.assertNotIn("₹₹", html)                            # no double rupee symbol
        self.assertNotIn("₹N/A", html)
        self.assertNotIn("-2.84", html)                         # fabricated Beneish preview figure
        self.assertNotIn("₹1,840", html)                        # fabricated reverse-DCF preview figure

    def test_pillar_links_never_borrow_another_company_scrip(self):
        """Without a valid scrip code, pillar cards must show no exchange link at all."""
        from core.analysis.parser import wrap_html_with_collapsible_pillars
        import markdown as md
        body = "\n\n".join(f"### Pillar {i}: Title {i}\nBody text {i}." for i in range(1, 8))
        out = wrap_html_with_collapsible_pillars(md.markdown(body), scrip_code="", ticker="NEWCO")
        self.assertEqual(out.count('class="pillar-accordion"'), 7)
        self.assertNotIn("bseindia.com", out)
        self.assertNotIn("500209", out)
        self.assertIn("BSE scrip code not yet resolved", out)

        out_valid = wrap_html_with_collapsible_pillars(md.markdown(body), scrip_code="500325", ticker="RELIANCE")
        self.assertIn("scrip_cd=500325", out_valid)
        self.assertNotIn("500209", out_valid)

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
            with self.subTest(slug=slug):
                res = self.client.get(f"/{slug}")
                self.assertEqual(res.status_code, 200, f"Policy route /{slug} failed")

    def test_primary_public_routes_parameterized(self):
        """Verifies primary public SSR view routes respond 200 with required keyword integrity."""
        primary_routes = [
            ("/", "Audit the Asset."),
            ("/discovery", "Stock Discovery @9AM"),
            ("/equities", "Institutional Equities"),
            ("/funds", "Mutual Fund Look-Through"),
            ("/debt", "Corporate Debt"),
            ("/reits", "REITs & InvITs"),
            ("/calculator/tax", "Net Real Tax Calculator"),
            ("/pricing", "Single Research Pass"),
            ("/contact", "Submit an Inquiry"),
        ]
        for path, keyword in primary_routes:
            with self.subTest(path=path):
                res = self.client.get(path)
                self.assertEqual(res.status_code, 200, f"Public route {path} failed with {res.status_code}")
                self.assertIn(keyword, res.text, f"Route {path} missing keyword: {keyword}")

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
        admin_pwd = os.environ.get("ADMIN_PASSWORD", "test_admin_pwd_default")
        client = TestClient(app)
        res_verify = client.post(
            "/admin/auth/direct-verify",
            data={"email": "lyndnpnto@gmail.com", "password": admin_pwd},
            follow_redirects=False
        )
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
        admin_pwd = os.environ.get("ADMIN_PASSWORD", "test_admin_pwd_default")
        res = self.client.post(
            "/admin/auth/direct-verify",
            data={"email": "unauthorized_user@example.com", "password": admin_pwd},
            follow_redirects=False
        )
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
        self.assertIn("Export Transaction Ledger (CSV)", res_dash.text)
        self.assertIn("Team & Access", res_dash.text)
        self.assertIn("Admin Audit Trail", res_dash.text)

    def test_admin_audit_navigation_bar_and_tabs(self):
        client = self._get_authenticated_admin_client()
        res_audit = client.get("/admin/audit")
        self.assertEqual(res_audit.status_code, 200)
        self.assertIn("admin-tabs", res_audit.text)
        self.assertIn("Return to Executive Console", res_audit.text)
        self.assertIn("Live Billables &amp; Inflow", res_audit.text)
        self.assertIn("User Accounts &amp; Usage", res_audit.text)
        self.assertTrue("Service Inbox" in res_audit.text or "Support Grievances" in res_audit.text)
        self.assertIn("Autonomous Project Auditor", res_audit.text)
        self.assertIn("Platform Home", res_audit.text)
        self.assertIn("Admin Console", res_audit.text)

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
        self.assertIn("Invoice Number,Date,Customer Email,Customer Name", res_csv.text)
        self.assertIn("Transaction_Register", res_csv.headers.get("content-disposition", ""))

    @patch("web.routers.admin.get_all_billables")
    def test_admin_tax_register_csv_formula_injection_prevention(self, mock_billables):
        mock_billables.return_value = [
            {
                "invoice_number": "=1+1",
                "date": "2026-10-18",
                "customer_email": "+user@example.com",
                "customer_name": "@AdminBoss",
                "pack_type": "-PRO",
                "payment_method": "\tUPI",
                "amount_inr": 500.0,
                "refund_amount_inr": 0.0,
                "status": "success",
                "gateway_order_id": "order_123",
                "gateway_payment_id": "pay_123",
            }
        ]
        client = self._get_authenticated_admin_client()
        res_csv = client.get("/admin/export/tax-register")
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn("'=1+1", res_csv.text)
        self.assertIn("'+user@example.com", res_csv.text)
        self.assertIn("'@AdminBoss", res_csv.text)
        self.assertIn("'-PRO", res_csv.text)
        self.assertIn("'\tUPI", res_csv.text)

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
        self.assertIn("01: Credit Quality & Rating Drift", res.text)
        self.assertIn("02: Capital Hierarchy & Seniority Cover", res.text)
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

        # 5. /api/debt/ingest (unauthenticated request rejected with 401)
        res_unauth = self.client.post("/api/debt/ingest", json={"isin": "INE999A08999"})
        self.assertEqual(res_unauth.status_code, 401)

        from web.common import _generate_admin_token, ADMIN_COOKIE_NAME
        auth_client = TestClient(app)
        auth_client.cookies.set(ADMIN_COOKIE_NAME, _generate_admin_token("admin@moatnomics.com", role="super_admin"))

        # 5b. /api/debt/ingest (validation error for short ISIN)
        res_bad = auth_client.post("/api/debt/ingest", json={"isin": "SHORT"})
        self.assertEqual(res_bad.status_code, 400)

        # 6. /api/debt/ingest (valid on-demand ISIN ingestion)
        test_isin = "INE999A08999"
        res_ingest = auth_client.post("/api/debt/ingest", json={
            "isin": test_isin,
            "ticker": "TESTCORP",
            "coupon_rate_pct": 9.20,
            "seniority_tier": "SENIOR_SECURED"
        })
        self.assertEqual(res_ingest.status_code, 200)
        ingest_data = res_ingest.json()
        self.assertEqual(ingest_data.get("status"), "success")
        self.assertEqual(ingest_data.get("isin"), test_isin)
        self.assertEqual(ingest_data.get("redirect_url"), f"/debt/{test_isin}")

        # 7. /api/debt/ingest (re-ingest existing ISIN)
        res_exist = auth_client.post("/api/debt/ingest", json={"isin": test_isin})
        self.assertEqual(res_exist.status_code, 200)
        self.assertTrue(res_exist.json().get("already_exists"))

        # Clean up test security from database
        from core.db.connection import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM corporate_debt_securities WHERE isin = ?", (test_isin,))
            conn.commit()
        except Exception:
            pass
        finally:
            cur.close()
            conn.close()

    def test_fund_directory_page(self):
        res = self.client.get("/funds")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Mutual Fund Look-Through & Fiduciary Screener", res.text)
        self.assertIn("Parag Parikh Flexi Cap Fund", res.text)
        self.assertIn("Active Share", res.text)

    def test_fund_dossier_page(self):
        # 1. Test PPFAS Flexi Cap
        res = self.client.get("/funds/PPFAS_FLEXICAP_DIR")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Parag Parikh Flexi Cap Fund", res.text)
        self.assertIn("01: Dual-Sleeve Constituent Decomposition", res.text)
        self.assertIn("02: True Diversification & Active Share", res.text)
        self.assertIn("05: Intermediary Fee Drag & Wealth Destruction", res.text)

        # 2. Test HDFC Mid-Cap (catches non-researched holding scores)
        res_hdfc = self.client.get("/funds/HDFC_MIDCAP_DIR")
        self.assertEqual(res_hdfc.status_code, 200)
        self.assertIn("HDFC Mid-Cap Opportunities Fund", res_hdfc.text)

        # 3. Test Mirae Asset Large Cap
        res_mirae = self.client.get("/funds/MIRAE_LARGECAP_DIR")
        self.assertEqual(res_mirae.status_code, 200)
        self.assertIn("Mirae Asset Large Cap Fund", res_mirae.text)

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

    def test_simplified_taskbar_navigation(self):
        """Verifies that the taskbar is organized into clean top-level categories and sub-tabs without horizontal overflow."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.text

        # Top-level category tabs
        self.assertIn("Markets", html)
        self.assertIn("Research Tools", html)
        self.assertIn("Governance", html)
        self.assertIn("Pricing", html)
        self.assertIn("Search", html)

        # Sub-tab dropdown items (Stock Reports & Mutual Funds consolidated in Markets; Generate Report removed)
        self.assertIn("Stock Reports & Equities", html)
        self.assertIn("Mutual Funds", html)
        self.assertIn("Bonds, NCDs & SDIs", html)
        self.assertIn("Morning Discovery @9AM", html)
        self.assertIn("Peer Comparison", html)
        self.assertIn("Support & Grievances", html)
        self.assertIn("SEBI Safe Harbor", html)
        self.assertNotIn("Instant Dossier Generator", html)
        self.assertNotIn("navGenerateBtn", html)

        # Accessibility semantics
        self.assertIn('aria-haspopup="true"', html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('role="menu"', html)
        self.assertIn('role="menuitem"', html)

        # Active state propagation
        res_debt = self.client.get("/debt")
        self.assertEqual(res_debt.status_code, 200)
        self.assertIn('active-parent', res_debt.text)

    @patch("web.main.get_stock_fundamentals")
    @patch("web.main.get_historical_prices")
    def test_thesis_checkpoint_api_and_modal_markup(self, mock_hist, mock_fund):
        import pandas as pd
        mock_fund.return_value = {
            "current_price": 1520.0,
            "fifty_two_week_low": 1300.0,
            "fifty_two_week_high": 1900.0,
            "pe_ratio": 25.0
        }
        mock_hist.return_value = pd.DataFrame()

        # 1. Test POST /api/thesis-checkpoint API
        payload = {
            "ticker": "INFY",
            "decision": "WOULD_BUY_TODAY",
            "rationale": "Strong balance sheet with zero net debt and durable digital transformation moat.",
            "current_price": 1850.50,
            "user_id": "test_analyst_1"
        }
        res = self.client.post("/api/thesis-checkpoint", json=payload, headers={"Origin": "http://testserver"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("Thesis Checkpoint", data.get("message", ""))

        # 2. Test Invalid Ticker rejection
        res_invalid = self.client.post("/api/thesis-checkpoint", json={"ticker": "", "decision": "WOULD_BUY_TODAY", "rationale": "test"}, headers={"Origin": "http://testserver"})
        self.assertEqual(res_invalid.status_code, 400)

        # 3. Test Dossier HTML contains Thesis Modal and trigger buttons
        res_dossier = self.client.get("/dossier/INFY")
        self.assertEqual(res_dossier.status_code, 200)
        html = res_dossier.text
        self.assertIn("thesisModalBackdrop", html)
        self.assertIn("thesisModal", html)
        self.assertIn("Would You Buy Today?", html)
        self.assertIn("btnOpenThesisTop", html)

    def test_equities_directory_page(self):
        # 1. Test canonical redirect from /stocks to /equities
        res_stocks = self.client.get("/stocks", follow_redirects=False)
        self.assertEqual(res_stocks.status_code, 301)
        self.assertIn("/equities", res_stocks.headers.get("location", ""))

        # 2. Test /equities default load
        res = self.client.get("/equities")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Institutional Equities Directory", res.text)
        self.assertIn("Monitored Equities", res.text)
        self.assertIn("INFY", res.text)

        # 3. Test search query
        res_q = self.client.get("/equities?q=INFY")
        self.assertEqual(res_q.status_code, 200)
        self.assertIn("INFY", res_q.text)

        # 4. Test sector filtering
        res_sec = self.client.get("/equities?sector=IT_TECH")
        self.assertEqual(res_sec.status_code, 200)
        self.assertIn("IT &amp; Technology", res_sec.text)

        # 5. Test market cap tier filtering
        res_tier = self.client.get("/equities?market_cap=MEGA")
        self.assertEqual(res_tier.status_code, 200)

        # 6. Test sorting parameters
        for s_mode in ["mcap_desc", "mcap_asc", "roce_desc", "pe_asc", "name_asc", "rev_desc"]:
            res_sort = self.client.get(f"/equities?sort={s_mode}")
            self.assertEqual(res_sort.status_code, 200)

    def test_reports_canonical_redirect(self):
        """Verify /reports and /reports/ permanently redirect to /equities preserving parameters."""
        res = self.client.get("/reports", follow_redirects=False)
        self.assertEqual(res.status_code, 301)
        self.assertIn("/equities", res.headers.get("location", ""))

        res_slash = self.client.get("/reports/", follow_redirects=False)
        self.assertEqual(res_slash.status_code, 301)
        self.assertIn("/equities", res_slash.headers.get("location", ""))

        res_query = self.client.get("/reports?q=TCS", follow_redirects=False)
        self.assertEqual(res_query.status_code, 301)
        self.assertIn("/equities?q=TCS", res_query.headers.get("location", ""))

    def test_home_stock_reports_browser(self):
        """Verify homepage renders interactive stock reports browser with rich cards mirroring MFs."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.text
        self.assertIn("Browse Verified Stock Research Reports", html)
        self.assertIn("home-stock-card", html)
        self.assertIn("homeStockSearchInput", html)
        self.assertIn("homeSectorPills", html)
        self.assertIn("Stock Reports", html)
        self.assertIn("Mutual Funds", html)
        self.assertIn("Inspect Full 7-Pillar Dossier", html)
        self.assertIn("Return on Equity (ROE):", html)
        self.assertIn("Operating Margin (OPM):", html)




"""
Unit and Integration Tests for Multi-Asset Opportunity Terminal & Arbitrage Scanner.

Tests:
1. calculate_tax_waterfall across statutory regimes (Sec 47(viic), Sec 115UA, Sec 50AA, Sec 112A).
2. assign_tenure_bucket categorization.
3. get_normalized_opportunity_universe cross-asset aggregation and persona filtering.
4. get_heatmap_matrix 2D matrix structure.
5. get_arbitrage_comparison side-by-side scorecard generation.
6. FastAPI web endpoints:
   - GET /opportunities (HTML)
   - GET /api/opportunities/universe (JSON)
   - GET /api/opportunities/heatmap (JSON)
   - POST /api/opportunities/arbitrage (JSON)
"""

import os
import unittest
from fastapi.testclient import TestClient

# Ensure test DB isolation
os.environ["TESTING"] = "1"

from web.main import app
from core.analysis.opportunity_terminal import (
    calculate_tax_waterfall,
    assign_tenure_bucket,
    get_normalized_opportunity_universe,
    get_heatmap_matrix,
    get_arbitrage_comparison,
    BENCHMARK_10Y_GSEC_YIELD
)


class TestOpportunityTerminalEngine(unittest.TestCase):
    """Unit tests for the financial normalization and taxation engine."""

    def test_sgb_tax_waterfall_section_47_viic(self):
        """Verify SGB capital gains are 100% tax-free under Sec 47(viic) with only coupon taxed."""
        # 8.0% total YTM on SGB with 2.50% coupon at 30% tax slab
        # Coupon taxed: 2.50 * 0.70 = 1.75%
        # Capital appreciation: 8.0 - 2.5 = 5.50% (tax-free)
        # Expected Net: 5.50 + 1.75 = 7.25%
        res = calculate_tax_waterfall(8.0, "SGB", tax_slab=30.0, details={"coupon_rate_pct": 2.50})
        self.assertEqual(res["net_yield_pct"], 7.25)
        self.assertIn("Sec 47(viic)", res["tax_statute"])
        self.assertLess(res["effective_tax_rate_pct"], 15.0)

    def test_reit_tax_waterfall_section_115_ua(self):
        """Verify REIT/InvIT distribution split under Section 115UA pass-through rules."""
        # 8.0% distribution yield at 30% slab
        # 40% Interest = 3.2% * 0.70 = 2.24%
        # 35% Dividend = 2.8% (exempt)
        # 25% RoC = 2.0% (tax-free capital reduction)
        # Total Net = 2.24 + 2.80 + 2.00 = 7.04%
        res = calculate_tax_waterfall(8.0, "REIT", tax_slab=30.0)
        self.assertEqual(res["net_yield_pct"], 7.04)
        self.assertIn("Sec 115UA", res["tax_statute"])

    def test_corporate_debt_marginal_slab_tax_sec_50_aa(self):
        """Verify standard corporate debt and SDIs are taxed at marginal slab rates."""
        # 10.0% YTM at 30% tax slab -> 7.0% net
        res = calculate_tax_waterfall(10.0, "BOND", tax_slab=30.0)
        self.assertEqual(res["net_yield_pct"], 7.0)
        self.assertEqual(res["effective_tax_rate_pct"], 30.0)
        self.assertIn("Sec 50AA", res["tax_statute"])

        # At 39% HNI surcharge slab -> 6.1% net
        res_hni = calculate_tax_waterfall(10.0, "BOND", tax_slab=39.0)
        self.assertEqual(res_hni["net_yield_pct"], 6.1)

    def test_corporate_debt_10_pct_tax_slab(self):
        """Verify 10% tax slab under New Tax Regime applies correctly."""
        res_10 = calculate_tax_waterfall(10.0, "BOND", tax_slab=10.0)
        self.assertEqual(res_10["net_yield_pct"], 9.0)
        self.assertEqual(res_10["effective_tax_rate_pct"], 10.0)

    def test_equity_long_term_capital_gains_sec_112_a(self):
        """Verify equity and equity mutual funds are taxed at flat 12.5% LTCG."""
        # 14.0% return at 12.5% LTCG -> 12.25% net
        res = calculate_tax_waterfall(14.0, "EQUITY", tax_slab=30.0)
        self.assertEqual(res["net_yield_pct"], 12.25)
        self.assertEqual(res["effective_tax_rate_pct"], 12.5)
        self.assertIn("Sec 112A", res["tax_statute"])

    def test_zero_gross_yield_and_zero_tax_slab(self):
        """Verify boundary cases for 0% return and 0% tax bracket."""
        res_zero = calculate_tax_waterfall(0.0, "BOND", tax_slab=30.0)
        self.assertEqual(res_zero["net_yield_pct"], 0.0)

        res_exempt = calculate_tax_waterfall(8.0, "BOND", tax_slab=0.0)
        self.assertEqual(res_exempt["net_yield_pct"], 8.0)
        self.assertEqual(res_exempt["tax_drag_pct"], 0.0)

    def test_assign_tenure_bucket(self):
        """Verify tenure bucket assignment boundaries."""
        self.assertEqual(assign_tenure_bucket(0.5), "<1Y")
        self.assertEqual(assign_tenure_bucket(1.0), "<1Y")
        self.assertEqual(assign_tenure_bucket(2.5), "1-3Y")
        self.assertEqual(assign_tenure_bucket(3.0), "1-3Y")
        self.assertEqual(assign_tenure_bucket(4.5), "3-5Y")
        self.assertEqual(assign_tenure_bucket(7.0), "5-10Y")
        self.assertEqual(assign_tenure_bucket(15.0), "10Y+")

    def test_get_normalized_opportunity_universe(self):
        """Verify universal aggregation across all 6 asset categories."""
        universe = get_normalized_opportunity_universe(tax_slab=30.0, cpi_inflation=4.5)
        self.assertGreater(len(universe), 20)

        # Check required schema keys on each item
        first = universe[0]
        required_keys = [
            "id", "symbol", "name", "asset_class", "category_label",
            "gross_yield_pct", "net_yield_pct", "real_yield_pct",
            "spread_vs_10y_gsec_bps", "seniority_tier", "seniority_rank",
            "macaulay_duration_years", "tenure_bucket", "min_ticket_inr",
            "liquidity_tier", "tax_statute", "recovery_recourse",
            "primary_failure_mode", "detail_url"
        ]
        for k in required_keys:
            self.assertIn(k, first, f"Missing key '{k}' in OpportunityItem")

        # Verify items are sorted descending by net_yield_pct
        for i in range(len(universe) - 1):
            self.assertGreaterEqual(universe[i]["net_yield_pct"], universe[i+1]["net_yield_pct"])

    def test_persona_filtering(self):
        """Verify persona playbooks and Phase 3 scenario aliases correctly isolate matching opportunities."""
        preservation = get_normalized_opportunity_universe(persona_filter="capital_preservation")
        self.assertGreater(len(preservation), 0)
        for item in preservation:
            self.assertIn("capital_preservation", item.get("persona_tags", []))
            self.assertGreaterEqual(item.get("real_yield_pct", 0), 0)

        cashflow = get_normalized_opportunity_universe(persona_filter="maximum_cashflow")
        self.assertGreater(len(cashflow), 0)
        for item in cashflow:
            self.assertIn("quarterly_cashflow", item.get("persona_tags", []))

        upside = get_normalized_opportunity_universe(persona_filter="asymmetric_upside")
        self.assertGreater(len(upside), 0)
        for item in upside:
            self.assertIn("compounding", item.get("persona_tags", []))

    def test_get_heatmap_matrix(self):
        """Verify 2D heatmap matrix construction."""
        matrix = get_heatmap_matrix()
        self.assertEqual(matrix["tenure_buckets"], ["<1Y", "1-3Y", "3-5Y", "5-10Y", "10Y+"])
        self.assertEqual(len(matrix["rows"]), 7)
        self.assertEqual(matrix["benchmark_10y_yield"], BENCHMARK_10Y_GSEC_YIELD)

    def test_get_arbitrage_comparison(self):
        """Verify side-by-side comparison scorecard generation."""
        universe = get_normalized_opportunity_universe()
        test_ids = [universe[0]["id"], universe[1]["id"]]
        scorecard = get_arbitrage_comparison(test_ids, tax_slab=30.0, cpi_inflation=4.5)
        self.assertEqual(scorecard["count"], 2)
        self.assertEqual(len(scorecard["items"]), 2)


class TestOpportunityTerminalWebEndpoints(unittest.TestCase):
    """Integration tests for FastAPI endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_get_opportunities_page(self):
        """GET /opportunities should return HTTP 200 with terminal HTML."""
        resp = self.client.get("/opportunities")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Multi-Asset Opportunity Terminal", resp.text)
        self.assertIn("arbitrageDocket", resp.text)
        self.assertIn("arbitrageModal", resp.text)
        self.assertIn("copilotModalBackdrop", resp.text)
        self.assertIn("10% (New Tax Regime Base)", resp.text)

    def test_get_api_opportunities_universe(self):
        """GET /api/opportunities/universe should return structured JSON."""
        resp = self.client.get("/api/opportunities/universe?tax_slab=30&cpi_inflation=4.5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertGreater(data.get("count", 0), 20)
        self.assertIsInstance(data.get("items"), list)

    def test_get_api_opportunities_heatmap(self):
        """GET /api/opportunities/heatmap should return matrix JSON."""
        resp = self.client.get("/api/opportunities/heatmap")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("tenure_buckets", data)
        self.assertIn("rows", data)

    def test_post_api_opportunities_arbitrage(self):
        """POST /api/opportunities/arbitrage should return scorecard JSON."""
        universe_resp = self.client.get("/api/opportunities/universe")
        items = universe_resp.json()["items"]
        test_ids = [items[0]["id"], items[1]["id"]]

        payload = {
            "item_ids": test_ids,
            "tax_slab": 30.0,
            "cpi_inflation": 4.5
        }
        resp = self.client.post("/api/opportunities/arbitrage", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("count"), 2)
        self.assertEqual(len(data.get("items")), 2)




"""
Consolidated Peer Comparison & Telemetry Analytics Test Suite
==============================================================
Unifies:
1. Company disparity evaluation & peer comparison mechanics
2. Telemetry event recording, traffic attribution, date-range summaries & landing page tracking
3. Localized fundamental ratios cache & clean formatting (/compare)
4. Telemetry synthetic/admin event exclusion filters and revenue isolation
"""
import asyncio
from datetime import date, datetime, timedelta
import os
import sys
import unittest

from fastapi.testclient import TestClient

from core.analysis.fundamentals import _FUNDAMENTALS_CACHE, compute_pead_drift_band, enrich_fundamentals, get_stock_fundamentals
from core.analysis.peer_comparison import compare_two_companies, evaluate_company_disparity
from core.db import get_db_connection, get_placeholder
from core.db.fundamentals import (
    extract_fundamentals_from_report_text,
    get_cached_fundamentals,
    save_cached_fundamentals,
    sync_all_cached_fundamentals,
)
from core.db.reports import save_report_to_archive
from core.db.telemetry import (
    classify_page_category,
    get_session_journeys,
    get_site_usage_summary,
    get_user_usage_analytics,
    is_admin_visit_event,
    is_excluded_telemetry_event,
    is_synthetic_test_event,
    purge_test_telemetry,
    record_usage_event,
)
from core.db.users import get_all_billables, get_revenue_analytics_summary
from telemetry import (
    get_admin_passcode,
    parse_traffic_source,
    parse_user_agent,
    verify_admin_passcode,
)
from web.main import ADMIN_COOKIE_NAME, _generate_admin_token, app


# ==============================================================================
# 1. Company Disparity & Telemetry Summaries
# ==============================================================================
class TestComparisonAndTelemetry(unittest.TestCase):
    def test_evaluate_company_disparity_axes(self):
        infy = {"sector": "Technology", "market_cap": 6000000000000.0, "pe_ratio": 24.5}
        tcs = {"sector": "Technology", "market_cap": 14000000000000.0, "pe_ratio": 28.1}
        disp = evaluate_company_disparity(infy, tcs)
        self.assertFalse(disp["is_disparate"])
        self.assertFalse(disp["sector_mismatch"])
        self.assertFalse(disp["lifecycle_mismatch"])
        self.assertFalse(disp["scale_mismatch"])
        self.assertEqual(len(disp["warnings"]), 0)

        hdfc = {"sector": "Financial Services", "market_cap": 12000000000000.0, "pe_ratio": 19.2}
        disp_sec = evaluate_company_disparity(infy, hdfc)
        self.assertTrue(disp_sec["is_disparate"])
        self.assertTrue(disp_sec["sector_mismatch"])

        zomato_loss = {"sector": "Consumer Cyclical", "market_cap": 1500000000000.0, "pe_ratio": "Loss-Making"}
        itc_profit = {"sector": "Consumer Defensive", "market_cap": 6000000000000.0, "pe_ratio": 26.5}
        disp_life = evaluate_company_disparity(zomato_loss, itc_profit)
        self.assertTrue(disp_life["is_disparate"])
        self.assertTrue(disp_life["lifecycle_mismatch"])

        micro = {"sector": "Technology", "market_cap": 500000000.0, "pe_ratio": 20.0}
        mega = {"sector": "Technology", "market_cap": 6000000000000.0, "pe_ratio": 25.0}
        disp_scale = evaluate_company_disparity(micro, mega)
        self.assertTrue(disp_scale["is_disparate"])
        self.assertTrue(disp_scale["scale_mismatch"])

    def test_telemetry_recording_and_date_range_summary(self):
        record_usage_event(
            event_type="UNIT_TEST_SEARCH",
            ticker="UNIT_TEST_TICKER",
            latency_ms=15.0,
            session_id="sess_test123",
            traffic_source="Google Search",
            referrer="https://www.google.com/",
            country="IN",
            device_type="Desktop",
            browser="Chrome",
            os="macOS"
        )
        record_usage_event(
            event_type="UNIT_TEST_CACHE",
            ticker="UNIT_TEST_TICKER",
            cost_saved_usd=0.036,
            session_id="sess_test123",
            traffic_source="Google Search",
            country="IN"
        )

        summary_days = get_site_usage_summary(days=1, exclude_tests=False)
        self.assertIsNotNone(summary_days)
        self.assertIn("total_queries", summary_days)
        self.assertIn("traffic_sources", summary_days)
        self.assertIn("top_landing_pages", summary_days)
        self.assertIn("top_visited_pages", summary_days)
        self.assertIn("geographic_distribution", summary_days)

        today = date.today()
        start = today - timedelta(days=2)
        summary_range = get_site_usage_summary(start_date=start, end_date=today, exclude_tests=False)
        self.assertIsNotNone(summary_range)
        self.assertIn("top_landing_pages", summary_range)

        journeys = get_session_journeys(start_date=start, end_date=today, limit=10, exclude_tests=False)
        self.assertIsInstance(journeys, list)
        if len(journeys) > 0:
            self.assertIn("landing_page", journeys[0])

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM site_usage_events WHERE event_type LIKE 'UNIT_TEST_%'")
        conn.commit()
        conn.close()

    def test_traffic_attribution_and_demographics(self):
        src1, ref1 = parse_traffic_source("https://www.google.com/search?q=stocks", {})
        self.assertEqual(src1, "Google Search")

        src2, ref2 = parse_traffic_source("https://t.co/xyz123", {})
        self.assertEqual(src2, "X / Twitter")

        src3, ref3 = parse_traffic_source("https://www.linkedin.com/feed", {})
        self.assertEqual(src3, "LinkedIn")

        src4, ref4 = parse_traffic_source("", {"utm_source": "newsletter"})
        self.assertEqual(src4, "newsletter")

        src5, ref5 = parse_traffic_source("", {})
        self.assertEqual(src5, "Direct / Bookmark")

        desktop_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        info_d = parse_user_agent(desktop_ua)
        self.assertEqual(info_d["device"], "Desktop")
        self.assertEqual(info_d["browser"], "Chrome")
        self.assertEqual(info_d["os"], "macOS")

        mobile_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        info_m = parse_user_agent(mobile_ua)
        self.assertEqual(info_m["device"], "Mobile")
        self.assertEqual(info_m["browser"], "Safari")
        self.assertEqual(info_m["os"], "iOS")

    def test_admin_passcode_verification(self):
        current_passcode = get_admin_passcode()
        self.assertTrue(verify_admin_passcode(current_passcode))
        self.assertFalse(verify_admin_passcode("wrong_password_xyz"))
        self.assertFalse(verify_admin_passcode(""))

    def test_revenue_analytics_paid_vs_free_tokens_and_purge(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()

        try:
            cursor.execute("DELETE FROM credit_transactions;")
            conn.commit()

            cursor.execute(
                f"""
                INSERT INTO credit_transactions (
                    id, user_id, amount_inr, credits_added, payment_gateway,
                    gateway_order_id, gateway_payment_id, status, pack_type, invoice_number,
                    customer_email, customer_name
                ) VALUES ({p}, {p}, 299.0, 20.0, 'razorpay', 'order_real_1', 'pay_real_1', 'success', 'STARTER', 'INV-REAL-1', 'genuine@investor.com', 'Genuine Buyer');
                """,
                ("tx_real_test_1", "usr_real_test_1")
            )

            cursor.execute(
                f"""
                INSERT INTO credit_transactions (
                    id, user_id, amount_inr, credits_added, payment_gateway,
                    gateway_order_id, gateway_payment_id, status, pack_type, invoice_number,
                    customer_email, customer_name
                ) VALUES ({p}, {p}, 0.0, 2.0, 'system_grant', NULL, NULL, 'success', 'WELCOME_GRANT', 'INV-WELCOME-1', 'freebie@investor.com', 'Freebie User');
                """,
                ("tx_welcome_test_1", "usr_free_test_1")
            )

            cursor.execute(
                f"""
                INSERT INTO credit_transactions (
                    id, user_id, amount_inr, credits_added, payment_gateway,
                    gateway_order_id, gateway_payment_id, status, pack_type, invoice_number,
                    customer_email, customer_name
                ) VALUES ({p}, {p}, 1499.0, 100.0, 'simulation', 'order_sim_test_99', 'pay_sim_test_99', 'success', 'PRO_MONTHLY', 'INV-SIM-1', 'test@example.com', 'Test Bot');
                """,
                ("tx_sim_test_1", "test_bot_1")
            )
            conn.commit()

            summary = get_revenue_analytics_summary(exclude_tests=True)
            self.assertEqual(summary["gross_revenue_inr"], 299.0)
            self.assertEqual(summary["paid_orders_count"], 1)
            self.assertEqual(summary["paid_credits_issued"], 20.0)
            self.assertEqual(summary["welcome_grants_count"], 1)
            self.assertEqual(summary["free_credits_issued"], 2.0)

            billables = get_all_billables(exclude_tests=True)
            billable_ids = [b["id"] for b in billables]
            self.assertIn("tx_real_test_1", billable_ids)
            self.assertIn("tx_welcome_test_1", billable_ids)
            self.assertNotIn("tx_sim_test_1", billable_ids)

            real_tx = next(b for b in billables if b["id"] == "tx_real_test_1")
            self.assertEqual(real_tx["nature"], "VERIFIED_PAID")

            welcome_tx = next(b for b in billables if b["id"] == "tx_welcome_test_1")
            self.assertEqual(welcome_tx["nature"], "FREE_GRANT")

            counts = purge_test_telemetry()
            self.assertGreaterEqual(counts.get("transactions_purged", 0), 1)

            cursor.execute("SELECT id FROM credit_transactions WHERE id IN ('tx_real_test_1', 'tx_welcome_test_1', 'tx_sim_test_1');")
            remaining = [r[0] for r in cursor.fetchall()]
            self.assertIn("tx_real_test_1", remaining)
            self.assertIn("tx_welcome_test_1", remaining)
            self.assertNotIn("tx_sim_test_1", remaining)

        finally:
            cursor.execute("DELETE FROM credit_transactions WHERE id IN ('tx_real_test_1', 'tx_welcome_test_1', 'tx_sim_test_1');")
            conn.commit()
            cursor.close()
            conn.close()

    def test_landing_pages_telemetry_and_classification(self):
        self.assertEqual(classify_page_category("/")[0], "Homepage / Terminal")
        self.assertEqual(classify_page_category("/dossier/INFY")[0], "Equity Dossier (INFY)")
        self.assertEqual(classify_page_category("/funds")[0], "Mutual Fund Directory")
        self.assertEqual(classify_page_category("/funds/118989")[0], "Mutual Fund Forensic Dossier")
        self.assertEqual(classify_page_category("/debt")[0], "Corporate Debt Directory")
        self.assertEqual(classify_page_category("/pricing")[0], "Pricing & Subscriptions")
        self.assertEqual(classify_page_category("/compare")[0], "Peer Head-to-Head Compare")
        self.assertEqual(classify_page_category("/opportunities")[0], "Multi-Asset Terminal")

        sess_id = "sess_landing_test_999"
        record_usage_event(
            event_type="PAGE_VIEW",
            ticker="TCS",
            session_id=sess_id,
            landing_page="/funds",
            traffic_source="Google Search",
            is_test_override=True
        )

        try:
            summary = get_site_usage_summary(days=1, exclude_tests=False)
            self.assertIn("top_landing_pages", summary)
            self.assertIn("top_visited_pages", summary)
            landing_paths = [lp["path"] for lp in summary["top_landing_pages"]]
            self.assertIn("/funds", landing_paths)

            journeys = get_session_journeys(days=1, limit=50, exclude_tests=False)
            test_journey = next((j for j in journeys if j["session_id"] == sess_id), None)
            self.assertIsNotNone(test_journey)
            self.assertEqual(test_journey["landing_page"], "/funds")
        finally:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("DELETE FROM site_usage_events WHERE session_id = ?", (sess_id,))
            conn.commit()
            c.close()
            conn.close()


# ==============================================================================
# 2. Localized DB Fundamentals Cache & Peer Comparison Harmonization
# ==============================================================================
class TestPeerComparisonDataHarmonization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _FUNDAMENTALS_CACHE.clear()

        infy_data = {
            "ticker": "INFY",
            "short_name": "Infosys Ltd",
            "current_price": 1023.4,
            "pe_ratio": "13.95",
            "market_cap": 4153240276683.12,
        }
        infy_text = """### Health Matrix
- Macro: Headwinds
- Moat: Wide
- Governance: Clean
- Diagnostic: Temporary
- Valuation: Undervalued
- Balance Sheet: Debt-Free
- Capital Allocation: Disciplined

- **Return Ratios:** ROE [Return on Equity] remains strong at 31.68%. ROCE [Return on Capital Employed] was 42.84% in FY 2026.
- **Operating Margins:** Operating margins remain healthy within the 20.0% band.
The stock has fallen from its 52-week high of INR 1,727.85 toward INR 1,013.00, close to its 52-week low of INR 980.30.
"""
        save_report_to_archive(stock_data=infy_data, report_text=infy_text)

        tcs_data = {
            "ticker": "TCS",
            "short_name": "Tata Consultancy Services Ltd",
            "current_price": 2156.0,
            "pe_ratio": "15.65",
            "market_cap": 7800596706254.95,
        }
        tcs_text = """### Health Matrix
- Macro: Headwinds
- Moat: Wide
- Governance: Clean
- Diagnostic: Temporary
- Valuation: Undervalued
- Balance Sheet: Debt-Free
- Capital Allocation: Disciplined

- **Return Metrics:** TCS consistently records an ROE [Return on Equity] above 45.0% and an ROCE [Return on Capital Employed] exceeding 55.0%.
- **Operating Margins:** Operating margin stands firm between 24.0% and 25.3%.
The stock price has experienced downward pressure from its 52-week high of INR 3,336.70 toward its 52-week low near INR 1,976.00.
"""
        save_report_to_archive(stock_data=tcs_data, report_text=tcs_text)

        sync_all_cached_fundamentals()
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    def test_extract_fundamentals_from_report_text(self):
        sample_report = """
        ### Health Matrix
        - Balance Sheet: Debt-Free
        - Moat: Wide

        - **Return Ratios:** ROE [Return on Equity] remains strong at 28.5%. ROCE [Return on Capital Employed] was 36.2% in FY 2026.
        - **Operating Margins:** Operating margins remain healthy within the 22.4% band.
        - **Price Action:** The stock corrected from its 52-week high of INR 1,500.00 toward its 52-week low of INR 950.50.
        """
        extracted = extract_fundamentals_from_report_text(sample_report)
        self.assertEqual(extracted.get("roce"), 36.2)
        self.assertEqual(extracted.get("roe"), 28.5)
        self.assertEqual(extracted.get("operating_margin"), 22.4)
        self.assertEqual(extracted.get("debt_to_equity"), 0.0)
        self.assertEqual(extracted.get("fifty_two_week_high"), 1500.0)
        self.assertEqual(extracted.get("fifty_two_week_low"), 950.5)

    def test_cached_fundamentals_crud_and_aliases(self):
        test_data = {
            "ticker": "TESTPEER",
            "company_name": "Test Peer Diagnostics Ltd",
            "current_price": 500.0,
            "market_cap": 25000000000.0,
            "pe_ratio": "22.5",
            "roce": 26.4,
            "roe": 19.8,
            "operating_margin": 18.2,
            "debt_to_equity": 0.15,
            "fifty_two_week_high": 620.0,
            "fifty_two_week_low": 410.0,
            "source": "UNIT_TEST"
        }
        save_cached_fundamentals("TESTPEER", test_data)
        cached = get_cached_fundamentals("TESTPEER")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["ticker"], "TESTPEER")
        self.assertEqual(cached["roce"], 26.4)
        self.assertEqual(cached["roce_pct"], 26.4)
        self.assertEqual(cached["roe"], 19.8)
        self.assertEqual(cached["operating_margin"], 18.2)
        self.assertEqual(cached["opm"], 18.2)
        self.assertEqual(cached["debt_to_equity"], 0.15)
        self.assertEqual(cached["fifty_two_week_high"], 620.0)
        self.assertEqual(cached["52w_high"], 620.0)
        self.assertEqual(cached["fifty_two_week_low"], 410.0)
        self.assertEqual(cached["52w_low"], 410.0)

    def test_enrich_fundamentals_merges_cache_without_double_formatting(self):
        raw_fund = {"ticker": "INFY", "current_price": 1023.4}
        enriched = enrich_fundamentals("INFY", raw_fund)
        self.assertIsNotNone(enriched.get("roce"))
        self.assertIsNotNone(enriched.get("roe"))
        self.assertIsNotNone(enriched.get("fifty_two_week_high"))
        self.assertNotIn("%", str(enriched["roce"]))
        self.assertNotIn("%", str(enriched["roe"]))

    def test_compare_two_companies_live_resolution(self):
        res = asyncio.run(compare_two_companies("INFY", "TCS"))
        self.assertIn("fund_a", res)
        self.assertIn("fund_b", res)
        fund_a = res["fund_a"]
        fund_b = res["fund_b"]

        for key in ["roce", "roe", "operating_margin", "debt_to_equity", "fifty_two_week_high", "fifty_two_week_low"]:
            self.assertIsNotNone(fund_a.get(key), f"Key {key} was None for INFY")
            self.assertNotEqual(fund_a.get(key), "N/A", f"Key {key} was N/A for INFY")
            self.assertIsNotNone(fund_b.get(key), f"Key {key} was None for TCS")
            self.assertNotEqual(fund_b.get(key), "N/A", f"Key {key} was N/A for TCS")

    def test_compare_page_html_rendering_e2e(self):
        response = self.client.get("/compare?a=INFY&b=TCS")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("INFY", html)
        self.assertIn("TCS", html)
        self.assertNotIn("₹₹", html)
        self.assertNotIn("%%", html)
        self.assertNotIn("N/A%", html)
        self.assertNotIn("₹N/A", html)
        self.assertIn("42.84%", html)
        self.assertTrue("31.68%" in html or "32.0%" in html)
        self.assertIn("55", html)
        self.assertIn("₹980.3", html)
        self.assertIn("₹1727.85", html)


# ==============================================================================
# 3. Telemetry Synthetic & Admin Event Exclusion
# ==============================================================================
class TestTelemetryExclusion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        cls.client = TestClient(app)

    def setUp(self):
        self.conn = get_db_connection()
        self.cursor = self.conn.cursor()

    def tearDown(self):
        try:
            self.cursor.execute("DELETE FROM site_usage_events WHERE session_id LIKE 'test_excl_%' OR user_email LIKE '%excl_test%'")
            self.cursor.execute("DELETE FROM user_accounts WHERE id LIKE 'usr_excl_test_%' OR email LIKE '%excl_test%'")
            self.cursor.execute("DELETE FROM credit_transactions WHERE id LIKE 'tx_excl_test_%' OR customer_email LIKE '%excl_test%'")
            self.conn.commit()
        except Exception:
            pass
        finally:
            self.cursor.close()
            self.conn.close()

    def test_detector_functions(self):
        self.assertTrue(is_synthetic_test_event(user_email="tester@example.com"))
        self.assertTrue(is_synthetic_test_event(user_email="user@test.com"))
        self.assertTrue(is_synthetic_test_event(browser="python-requests/2.31.0"))
        self.assertTrue(is_synthetic_test_event(browser="testclient"))
        self.assertTrue(is_synthetic_test_event(user_id="guest_web_user"))
        self.assertTrue(is_synthetic_test_event(user_id="usr_test_987654"))
        self.assertTrue(is_synthetic_test_event(ticker="TEST"))
        self.assertTrue(is_synthetic_test_event(ticker="UNIT_TEST_TICKER"))
        self.assertTrue(is_synthetic_test_event(session_id="test_sess_001"))
        self.assertTrue(is_synthetic_test_event(event_type="UNIT_TEST_SAMPLE"))

        self.assertTrue(is_admin_visit_event(landing_page="/admin"))
        self.assertTrue(is_admin_visit_event(landing_page="/admin/telemetry"))
        self.assertTrue(is_admin_visit_event(details={"landing_page": "/admin/dashboard"}))
        self.assertTrue(is_admin_visit_event(event_type="ADMIN_USER_CREDIT_GRANT"))
        self.assertTrue(is_admin_visit_event(user_email="lyndnpnto@gmail.com"))
        self.assertTrue(is_admin_visit_event(user_email="admin@stockresearch.internal"))
        self.assertTrue(is_admin_visit_event(user_id="adm_owner_lyndon"))
        self.assertTrue(is_admin_visit_event(user_id="adm_moderator_1"))

        self.assertTrue(is_excluded_telemetry_event(landing_page="/admin"))
        self.assertTrue(is_excluded_telemetry_event(browser="testclient"))
        self.assertTrue(is_excluded_telemetry_event(user_email="test@example.com"))
        self.assertFalse(is_excluded_telemetry_event(
            landing_page="/dossier/RELIANCE",
            browser="Mozilla/5.0 Chrome/120.0",
            user_email="investor.rahul@gmail.com",
            user_id="usr_investor_123",
            ticker="RELIANCE"
        ))

    def test_api_telemetry_rejects_admin_session(self):
        admin_token = _generate_admin_token("lyndnpnto@gmail.com", "superadmin")
        self.client.cookies.set(ADMIN_COOKIE_NAME, admin_token)

        resp = self.client.post("/api/telemetry/event", json={
            "event_type": "page_view",
            "landing_page": "/dossier/TCS",
            "ticker": "TCS",
            "session_id": "test_excl_adm_sess"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "filtered")
        self.assertEqual(data.get("reason"), "admin_session")

        self.cursor.execute("SELECT COUNT(*) FROM site_usage_events WHERE session_id = 'test_excl_adm_sess'")
        self.assertEqual(self.cursor.fetchone()[0], 0)
        self.client.cookies.delete(ADMIN_COOKIE_NAME)

    def test_api_telemetry_rejects_admin_route_visit(self):
        resp = self.client.post("/api/telemetry/event", json={
            "event_type": "page_view",
            "landing_page": "/admin",
            "session_id": "test_excl_admin_path"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "filtered")
        self.assertEqual(data.get("reason"), "test_or_admin")

        self.cursor.execute("SELECT COUNT(*) FROM site_usage_events WHERE session_id = 'test_excl_admin_path'")
        self.assertEqual(self.cursor.fetchone()[0], 0)

    def test_calculations_exclude_tests_and_admin_records(self):
        record_usage_event(
            event_type="SEARCH",
            ticker="INFY",
            latency_ms=25.0,
            cost_saved_usd=0.036,
            session_id="test_excl_real_investor_session",
            traffic_source="Organic Search",
            referrer="https://www.google.com",
            country="IN",
            device_type="Desktop",
            browser="Chrome",
            user_id="usr_real_investor_99",
            user_email="investor.sharma@yahoo.com",
            landing_page="/dossier/INFY",
            is_test_override=True
        )

        record_usage_event(
            event_type="SEARCH",
            ticker="TEST_CORP",
            latency_ms=10.0,
            cost_saved_usd=100.0,
            session_id="test_excl_synthetic_test_sess",
            traffic_source="Automated Test",
            browser="testclient",
            user_id="testclient",
            user_email="bot@example.com",
            landing_page="/dossier/TEST_CORP",
            is_test_override=True
        )

        record_usage_event(
            event_type="ADMIN_LOGIN",
            ticker="APP",
            latency_ms=10.0,
            cost_saved_usd=500.0,
            session_id="test_excl_admin_session_touch",
            traffic_source="Direct",
            browser="Chrome",
            user_id="adm_owner_lyndon",
            user_email="lyndnpnto@gmail.com",
            landing_page="/admin",
            is_test_override=True
        )

        summary = get_site_usage_summary(days=30, exclude_tests=True)
        tickers = [item["ticker"] for item in summary.get("top_searched_tickers", [])]
        self.assertNotIn("TEST_CORP", tickers)
        self.assertNotIn("APP", tickers)

        for event in summary.get("recent_events", []):
            self.assertNotEqual(event.get("event_type"), "ADMIN_LOGIN")
            self.assertNotEqual(event.get("ticker"), "TEST_CORP")
            self.assertNotEqual(event.get("session_id"), "test_excl_")

        journeys = get_session_journeys(days=30, limit=50, exclude_tests=True)
        session_ids = [j.get("session_id") for j in journeys]
        self.assertNotIn("test_excl_synthetic_test_sess", session_ids)
        self.assertNotIn("test_excl_admin_session_touch", session_ids)

        user_metrics = get_user_usage_analytics(days=30, exclude_tests=True)
        top_user_emails = [u.get("email") for u in user_metrics.get("top_users", [])]
        self.assertNotIn("bot@example.com", top_user_emails)
        self.assertNotIn("lyndnpnto@gmail.com", top_user_emails)

        rev_metrics = get_revenue_analytics_summary(days=30, exclude_tests=True)
        self.assertIsInstance(rev_metrics.get("gross_revenue_inr"), (int, float))




"""
Unit and Integration Tests for Indicative Multi-Currency Pricing Architecture.
Validates:
1. Core currency conversion math, rates, and 3.5% international cross-border buffer
2. Location detection via Cloudflare CF-IPCountry headers, cookies, and query params
3. GET /api/billing/currencies endpoint response contract
4. GET /pricing SSR page rendering with currency selector dropdown, data attributes, and transparency notice
"""

import os
import unittest
from fastapi.testclient import TestClient

os.environ["TESTING"] = "1"

from web.main import app, init_db
from core.billing.currency import (
    SUPPORTED_CURRENCIES,
    convert_inr_to_currency,
    resolve_currency_for_request,
    COUNTRY_TO_CURRENCY_MAP,
)


class TestMultiCurrencyPricing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_inr_base_conversion(self):
        """INR base conversions should have zero buffer and exact figures."""
        conv = convert_inr_to_currency(299.0, "INR")
        self.assertEqual(conv["currency"], "INR")
        self.assertEqual(conv["symbol"], "₹")
        self.assertEqual(conv["effective_amount"], 299.0)
        self.assertEqual(conv["formatted"], "₹299")
        self.assertTrue(conv["is_base"])
        self.assertEqual(conv["buffer_pct"], 0.0)

    def test_usd_conversion_with_cross_border_buffer(self):
        """USD conversion must apply the 3.5% international buffer."""
        conv = convert_inr_to_currency(299.0, "USD")
        self.assertEqual(conv["currency"], "USD")
        self.assertEqual(conv["symbol"], "$")
        self.assertFalse(conv["is_base"])
        self.assertEqual(conv["buffer_pct"], 0.035)

        # 299 / 88.50 * 1.035 = 3.4968 -> 3.50
        expected = round((299.0 / 88.50) * 1.035, 2)
        self.assertEqual(conv["effective_amount"], expected)
        self.assertEqual(conv["formatted"], f"${expected:.2f}")
        self.assertIn("3.5%", conv["notice"])
        self.assertIn("Razorpay", conv["notice"])

    def test_all_supported_currencies_exist(self):
        """Ensures all 3 global investor currencies are defined with valid metadata."""
        expected_currencies = ["INR", "USD", "EUR"]
        self.assertEqual(len(SUPPORTED_CURRENCIES), 3)
        for code in expected_currencies:
            self.assertIn(code, SUPPORTED_CURRENCIES)
            curr = SUPPORTED_CURRENCIES[code]
            self.assertGreater(curr["rate_vs_inr"], 0)
            self.assertTrue(bool(curr["symbol"]))
            self.assertTrue(bool(curr["flag"]))

    def test_country_to_currency_mapping(self):
        """Validates major geopolitical regions map to expected currencies."""
        self.assertEqual(COUNTRY_TO_CURRENCY_MAP.get("US"), "USD")
        self.assertEqual(COUNTRY_TO_CURRENCY_MAP.get("DE"), "EUR")
        self.assertEqual(COUNTRY_TO_CURRENCY_MAP.get("FR"), "EUR")
        self.assertEqual(COUNTRY_TO_CURRENCY_MAP.get("IN"), "INR")

    def test_api_billing_currencies_endpoint(self):
        """Validates GET /api/billing/currencies contract."""
        resp = self.client.get("/api/billing/currencies")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("base_currency"), "INR")
        self.assertEqual(data.get("buffer_pct"), 3.5)
        self.assertIn("USD", data.get("currencies", {}))
        self.assertIn("EUR", data.get("currencies", {}))
        self.assertIn("INR", data.get("currencies", {}))
        self.assertEqual(len(data.get("currencies", {})), 3)

    def test_pricing_page_renders_currency_dropdown_and_data_attributes(self):
        """Validates that /pricing SSR contains the dropdown, transparency notice, and base prices."""
        resp = self.client.get("/pricing")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # 1. Base price and Single Pass still present (backward compatibility)
        self.assertIn("₹299", html)
        self.assertIn("Single Research Pass", html)

        # 2. Currency Selector dropdown present
        self.assertIn('id="currencySelect"', html)
        self.assertIn('value="USD"', html)
        self.assertIn('value="EUR"', html)
        self.assertIn('value="INR"', html)

        # 3. Dynamic attributes present
        self.assertIn('data-base-inr="299"', html)
        self.assertIn('data-base-inr="699"', html)
        self.assertIn('data-base-inr="1799"', html)

        # 4. Transparency notice present
        self.assertIn('id="currencyNoticeBanner"', html)
        self.assertIn('Indicative Local Currency Pricing:', html)
        self.assertIn('3.5%', html)

    def test_pricing_page_location_detection_via_header(self):
        """Validates that international CF-IPCountry header selects local currency."""
        # US visitor
        resp_us = self.client.get("/pricing", headers={"cf-ipcountry": "US"})
        self.assertEqual(resp_us.status_code, 200)
        self.assertIn('value="USD" selected', resp_us.text)

        # Eurozone visitor
        resp_eu = self.client.get("/pricing", headers={"cf-ipcountry": "DE"})
        self.assertEqual(resp_eu.status_code, 200)
        self.assertIn('value="EUR" selected', resp_eu.text)

        # Other international visitor maps to USD
        resp_intl = self.client.get("/pricing", headers={"cf-ipcountry": "GB"})
        self.assertEqual(resp_intl.status_code, 200)
        self.assertIn('value="USD" selected', resp_intl.text)

        # Query param override takes precedence
        resp_query = self.client.get("/pricing?currency=EUR", headers={"cf-ipcountry": "US"})
        self.assertEqual(resp_query.status_code, 200)
        self.assertIn('value="EUR" selected', resp_query.text)




"""Test suite for Developer API v1 (/api/v1/reports/{ticker}) and Custom Advisory PDF Branding."""

import os
os.environ["TESTING"] = "1"

import unittest
from fastapi.testclient import TestClient
from web.main import app
from core.reporting.pdf import build_pdf_dossier, generate_report_pdf
from core.db import save_report_to_archive

class TestApiV1AndBranding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Seed test report for INFY
        stock_data = {
            "ticker": "INFY",
            "short_name": "Infosys Ltd",
            "current_price": 1550.0,
            "pe_ratio": "25.2",
            "market_cap": 6200000000000.0,
            "scrip_code": "500209",
            "sector": "Information Technology"
        }
        report_text = """### 7-Pillar Qualitative Health Matrix:
- Moat: Strong
- Management: Stable
- Capital Allocation: Clean

## Pillar 1: Long-Term Competitive Moat
Detailed competitive advantage breakdown.

## Pillar 2: Financial Strength & Balance Sheet
Zero long-term debt and high FCF conversion.

## Pillar 3: Corporate Governance & Capital Allocation
Clean historical capital allocation track record.

### Key Fundamental Monitorables
Detailed forensic analysis grounded in bseindia.com filings.
"""
        save_report_to_archive(stock_data=stock_data, report_text=report_text)

    def test_branded_pdf_generation(self):
        """Verify that custom advisory branding is rendered into PDF binary."""
        branding = {
            "firm_name": "Apex Wealth Advisory",
            "advisor_reg_no": "INA000012345",
            "prepared_for": "Family Trust Portfolio",
            "custom_disclaimer": "Strictly confidential - for registered client review only."
        }
        rep_text = (
            "### 7-Pillar Qualitative Health Matrix:\n- Moat: Strong\n\n"
            "## Pillar 1: Moat\nClean moat with INR [Indian Rupee] 500 Cr [Crore] cash.\n\n"
            "## Pillar 6: Technical & Momentum Overlay\n"
            "Trades above 50-DMA [50-Day Moving Average] of INR 1400."
        )
        pdf_bytes = generate_report_pdf("INFY", rep_text, branding=branding)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        # PDF magic bytes
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join([page.get_text() for page in doc])
        # Assert sources section is present
        self.assertIn("Regulatory Sources", text)
        self.assertIn("Statutory Disclosures", text)
        # Assert robotic acronym brackets are cleaned
        self.assertNotIn("INR [Indian Rupee]", text)
        self.assertNotIn("Cr [Crore]", text)
        self.assertNotIn("50-DMA [50-Day Moving Average]", text)
        self.assertIn("INR 500 Cr", text)

    def test_api_pdf_endpoint_with_branding_params(self):
        """Verify /api/pdf/{ticker} accepts branding query parameters."""
        resp = self.client.get(
            "/api/pdf/INFY",
            params={
                "firm_name": "Zenith Advisory",
                "advisor_reg_no": "INA99998888",
                "prepared_for": "Mr. Sharma",
                "custom_disclaimer": "Client confidential."
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "application/pdf")
        self.assertIn("Zenith_Advisory_INFY_", resp.headers.get("content-disposition", ""))
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_api_v1_get_report_success(self):
        """Verify /api/v1/reports/{ticker} returns structured institutional JSON with valid auth."""
        resp = self.client.get(
            "/api/v1/reports/INFY",
            headers={"Authorization": "Bearer sr_dev_test_token_12345"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["version"], "v1")
        self.assertEqual(data["ticker"], "INFY")
        self.assertEqual(data["company_name"], "Infosys Ltd")
        self.assertIn("scrip_code", data)
        self.assertIn("7_pillar_health", data)
        self.assertIn("technical_indicators", data)
        self.assertIn("pead_drift_analysis", data)
        self.assertTrue(data["pead_drift_analysis"]["active"])
        self.assertIn("regulatory_disclaimer", data)
        self.assertEqual(resp.headers.get("cache-control"), "public, max-age=300")

    def test_api_v1_get_report_not_found(self):
        """Verify /api/v1/reports/{ticker} returns 404 for missing ticker with valid auth."""
        resp = self.client.get(
            "/api/v1/reports/NONEXISTENT_TICKER_99",
            headers={"Authorization": "Bearer sr_dev_test_token_12345"}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json().get("detail", "").lower())

    def test_api_v1_authentication_enforcement(self):
        """Verify /api/v1/reports/{ticker} rejects unauthenticated requests and enforces environment boundaries."""
        orig_testing = os.environ.get("TESTING")
        orig_admin_key = os.environ.get("ADMIN_API_KEY")
        try:
            # 1. Unauthenticated in testing mode -> 401
            resp_no_auth = self.client.get("/api/v1/reports/INFY")
            self.assertEqual(resp_no_auth.status_code, 401)

            # 2. Invalid mock key in testing mode -> 401
            resp_bad_key = self.client.get(
                "/api/v1/reports/INFY",
                headers={"Authorization": "Bearer invalid_random_key_999"}
            )
            self.assertEqual(resp_bad_key.status_code, 401)

            # 3. Valid dev key in testing mode -> 200
            resp_dev_test = self.client.get(
                "/api/v1/reports/INFY",
                headers={"Authorization": "Bearer sr_dev_test_token_12345"}
            )
            self.assertEqual(resp_dev_test.status_code, 200)

            # 4. Valid usr_ key via X-API-Key header in testing mode -> 200
            resp_usr_test = self.client.get(
                "/api/v1/reports/INFY",
                headers={"X-API-Key": "usr_client_test_key_888"}
            )
            self.assertEqual(resp_usr_test.status_code, 200)

            # 5. Disable testing mode to simulate production
            os.environ["TESTING"] = "0"
            os.environ["ADMIN_API_KEY"] = "prod_verified_admin_key_777"

            # In production, sr_dev_* simulation keys must be strictly rejected
            resp_dev_in_prod = self.client.get(
                "/api/v1/reports/INFY",
                headers={"Authorization": "Bearer sr_dev_test_token_12345"}
            )
            self.assertEqual(resp_dev_in_prod.status_code, 401)

            # In production, valid expected_api_key must succeed via timing-safe HMAC
            resp_prod_auth = self.client.get(
                "/api/v1/reports/INFY",
                headers={"Authorization": "Bearer prod_verified_admin_key_777"}
            )
            self.assertEqual(resp_prod_auth.status_code, 200)
            self.assertTrue(resp_prod_auth.json()["success"])
        finally:
            if orig_testing is not None:
                os.environ["TESTING"] = orig_testing
            else:
                os.environ.pop("TESTING", None)
            if orig_admin_key is not None:
                os.environ["ADMIN_API_KEY"] = orig_admin_key
            else:
                os.environ.pop("ADMIN_API_KEY", None)

class TestSlowAPIRateLimiter(unittest.TestCase):
    """Verifies SlowAPIMiddleware, app.state.limiter, and 429 RateLimitExceeded handler."""

    def test_limiter_and_middleware_registration(self):
        from web.main import app
        from slowapi.middleware import SlowAPIMiddleware
        self.assertTrue(hasattr(app.state, "limiter"))
        self.assertIsNotNone(app.state.limiter)
        middleware_classes = [m.cls for m in app.user_middleware]
        self.assertIn(SlowAPIMiddleware, middleware_classes)

    def test_rate_limit_exceeded_handler(self):
        from unittest.mock import MagicMock
        from web.main import app
        from slowapi.errors import RateLimitExceeded
        from starlette.requests import Request
        handler = app.exception_handlers.get(RateLimitExceeded)
        self.assertIsNotNone(handler)
        scope = {"type": "http", "method": "GET", "path": "/test", "headers": []}
        req = Request(scope)
        mock_limit = MagicMock(error_message=None, limit="100/minute")
        exc = RateLimitExceeded(mock_limit)
        resp = handler(req, exc)
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.body, b"Rate limit exceeded")

    def test_slowapi_middleware_functional_throttling(self):
        from fastapi import FastAPI, Response
        from fastapi.testclient import TestClient
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware

        sub_app = FastAPI()
        sub_limiter = Limiter(key_func=get_remote_address, default_limits=["2/minute"])
        sub_app.state.limiter = sub_limiter
        sub_app.add_exception_handler(RateLimitExceeded, lambda request, exc: Response(content="Rate limit exceeded", status_code=429))
        sub_app.add_middleware(SlowAPIMiddleware)

        @sub_app.get("/limited-ping")
        def limited_ping():
            return {"status": "ok"}

        client = TestClient(sub_app)
        r1 = client.get("/limited-ping")
        self.assertEqual(r1.status_code, 200)
        r2 = client.get("/limited-ping")
        self.assertEqual(r2.status_code, 200)
        r3 = client.get("/limited-ping")
        self.assertEqual(r3.status_code, 429)
        self.assertEqual(r3.text, "Rate limit exceeded")


if __name__ == "__main__":
    unittest.main()
