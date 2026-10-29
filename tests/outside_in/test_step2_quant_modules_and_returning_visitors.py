"""
Outside-In & Unit Verification Suite for Step 2 Quantitative Modules & Returning Visitor Tracker:
1. Excel/CSV Valuation & Forensic Workbook Export (/api/model/{ticker}) + 1-Credit Paywall + Watermark
2. Equities Directory Quantitative Screener Drawer (<details id="quantScreenerDrawer">) + BFSI Notice
3. Unified 2-to-5 Stock Peer Cluster Comparator (/compare?tickers=... & /api/equity/peer-cluster)
4. Live Security Tax Bridge Fail-Closed Sec 115UA + Cess/HNI Slabs + /calculator/tax?yield=
5. Ind AS 108 Segment Extractor (Car/EV/PE label fix) + Conditional #indAs108SegmentCard on Dossier
6. Sequential Thesis Drift API (/api/equity/thesis-drift/{ticker}) Pillar 3/5 Redaction + Single Card
7. Returning Visitor & Return-Intent Tracker (Identity Stitch, Return Magnets, #tab-traffic, fetchLater)
"""

import io
import json
import os
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ["TESTING"] = "1"

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from core.analysis.live_security_tax_bridge import (
    _resolve_reit_taxable_share,
    resolve_effective_slab_pct,
)
from core.analysis.segment_extractor import extract_ind_as_108_segments
from core.db.connection import get_db_connection, get_placeholder, init_db
from core.db.reports import get_report_by_ticker_sync, save_report_to_archive
from core.db.telemetry import get_returning_visitor_insights
from core.db.users import get_or_create_user, unlock_ticker_for_user
from web.common import (
    ADMIN_COOKIE_NAME,
    USER_SESSION_COOKIE,
    _generate_admin_token,
    _generate_user_session_token,
)
from web.main import app


def _ensure_seed_equity(ticker: str, short_name: str, report_md: str, price: float = 1540.0) -> None:
    init_db()
    existing = get_report_by_ticker_sync(ticker)
    if not existing:
        save_report_to_archive(
            ticker=ticker,
            short_name=short_name,
            report_text=report_md,
            baseline_price=price,
            baseline_pe="24.5",
            baseline_mcap=640_000_000_000.0,
            revision_trigger="Initial Statutory Filing Audit",
        )


class TestStep2QuantModulesAndReturningVisitors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        _ensure_seed_equity(
            "INFY",
            "Infosys Limited",
            (
                "## Executive Summary\nInfosys Limited (NSE: INFY) global digital services.\n"
                "| Pillar | Rating |\n|---|---|\n| 1. Business Moat & Durability | Strong |\n"
                "### Pillar 3: Financial Health\n#### What Would Change This View\n"
                "- **Evidence That Forces a Revision:** Operating cash conversion dropping below 75% in FY2026.\n"
                "### Pillar 5: Valuation\n#### What Would Change This View\n"
                "- **Evidence That Forces a Revision:** Implied 5Y FCF CAGR exceeding 22% above 12% WACC.\n"
            ),
            price=1540.0,
        )
        _ensure_seed_equity(
            "TCS",
            "Tata Consultancy Services Limited",
            "## Executive Summary\nTata Consultancy Services Limited (NSE: TCS) enterprise IT services.\n",
            price=3820.0,
        )
        _ensure_seed_equity(
            "HCLTECH",
            "HCL Technologies Limited",
            "## Executive Summary\nHCL Technologies Limited (NSE: HCLTECH) engineering and cloud services.\n",
            price=1610.0,
        )

    @classmethod
    def tearDownClass(cls):
        conn = get_db_connection()
        cur = conn.cursor()
        p = get_placeholder()
        test_uids = (
            "usr_step2_locked_01",
            "usr_step2_unlocked_02",
            "rahul.locked.step2@moatreader.in",
            "rahul.unlocked.step2@moatreader.in",
        )
        try:
            for uid in test_uids:
                cur.execute(f"DELETE FROM user_unlocked_dossiers WHERE user_id = {p}", (uid,))
                cur.execute(f"DELETE FROM credit_usage_ledger WHERE user_id = {p}", (uid,))
                cur.execute(f"DELETE FROM credit_transactions WHERE user_id = {p}", (uid,))
                cur.execute(f"DELETE FROM site_usage_events WHERE user_id = {p}", (uid,))
                cur.execute(f"DELETE FROM user_accounts WHERE id = {p}", (uid,))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def test_1_model_export_entitlement_watermark_and_dossier_cta(self):
        anon_client = TestClient(app)
        r_anon = anon_client.get("/api/model/INFY?format=xlsx")
        self.assertEqual(r_anon.status_code, 401)

        locked_user = get_or_create_user(
            "usr_step2_locked_01",
            "rahul.locked.step2@moatreader.in",
            "Rahul Sharma",
        )
        locked_token = _generate_user_session_token(locked_user["id"], locked_user["email"])
        locked_client = TestClient(app)
        locked_client.cookies.set(USER_SESSION_COOKIE, locked_token)

        r_locked = locked_client.get("/api/model/INFY?format=xlsx")
        self.assertEqual(r_locked.status_code, 402)

        r_dossier_locked = locked_client.get("/dossier/INFY")
        self.assertEqual(r_dossier_locked.status_code, 200)
        self.assertIn("Excel Model (Locked)", r_dossier_locked.text)

        unlocked_user = get_or_create_user(
            "usr_step2_unlocked_02",
            "priya.unlocked.step2@moatreader.in",
            "Priya Nair",
        )
        unlock_ticker_for_user(unlocked_user["id"], "INFY")
        unlocked_token = _generate_user_session_token(unlocked_user["id"], unlocked_user["email"])
        unlocked_client = TestClient(app)
        unlocked_client.cookies.set(USER_SESSION_COOKIE, unlocked_token)

        expected_watermark_ref = unlocked_user["id"][:12]
        r_xlsx = unlocked_client.get("/api/model/INFY?format=xlsx")
        self.assertEqual(r_xlsx.status_code, 200)
        self.assertTrue(r_xlsx.content.startswith(b"PK\x03\x04"), "Expected valid XLSX zip container")
        with zipfile.ZipFile(io.BytesIO(r_xlsx.content), "r") as zf:
            xml_blob = b"".join(zf.read(n) for n in zf.namelist() if n.endswith(".xml")).decode("utf-8", errors="ignore")
            self.assertIn("INFY", xml_blob)
            self.assertIn(expected_watermark_ref, xml_blob)

        r_csv = unlocked_client.get("/api/model/INFY?format=csv")
        self.assertEqual(r_csv.status_code, 200)
        self.assertIn(expected_watermark_ref, r_csv.text)
        self.assertIn("INFY", r_csv.text)

        r_dossier_unlocked = unlocked_client.get("/dossier/INFY")
        self.assertEqual(r_dossier_unlocked.status_code, 200)
        self.assertIn('/api/model/INFY?format=xlsx', r_dossier_unlocked.text)
        self.assertIn("Download Excel (.xlsx)", r_dossier_unlocked.text)

    def test_2_equities_quantitative_screener_drawer_and_bfsi_notice(self):
        client = TestClient(app)
        r_default = client.get("/equities")
        self.assertEqual(r_default.status_code, 200)
        soup_def = BeautifulSoup(r_default.text, "html.parser")
        drawer_def = soup_def.find("details", id="quantScreenerDrawer")
        self.assertIsNotNone(drawer_def, "Missing #quantScreenerDrawer on /equities")
        self.assertFalse(drawer_def.has_attr("open"))
        self.assertIsNone(soup_def.find(id="bfsiScreenerNotice"))
        for inp_id in ("inputMinRoce", "inputMaxDe", "inputMaxPe", "inputMinOpm"):
            self.assertIsNotNone(soup_def.find("input", id=inp_id), f"Missing #{inp_id}")

        r_filtered = client.get("/equities?min_opm=18&max_de=0.4")
        self.assertEqual(r_filtered.status_code, 200)
        soup_flt = BeautifulSoup(r_filtered.text, "html.parser")
        drawer_flt = soup_flt.find("details", id="quantScreenerDrawer")
        self.assertTrue(drawer_flt.has_attr("open"))
        bfsi_notice = soup_flt.find(id="bfsiScreenerNotice")
        self.assertIsNotNone(bfsi_notice, "Expected #bfsiScreenerNotice when min_opm or max_de is active")
        self.assertIn("BFSI Accounting Scope Notice", bfsi_notice.get_text())

    def test_3_unified_peer_cluster_compare_and_api(self):
        client = TestClient(app)
        r_api = client.get("/api/equity/peer-cluster?tickers=INFY,TCS,HCLTECH")
        self.assertEqual(r_api.status_code, 200)
        body = r_api.json()
        self.assertEqual(body["status"], "success")
        cluster = body["cluster"]
        self.assertEqual(cluster["count"], 3)
        self.assertEqual(cluster["tickers"], ["INFY", "TCS", "HCLTECH"])
        self.assertIn("cluster_medians", cluster)

        r_page = client.get("/compare?tickers=INFY,TCS,HCLTECH")
        self.assertEqual(r_page.status_code, 200)
        self.assertIn("Cluster Median", r_page.text)
        self.assertIn("HCLTECH", r_page.text)
        soup = BeautifulSoup(r_page.text, "html.parser")
        regions = soup.find_all("div", attrs={"role": "region", "tabindex": "0"})
        self.assertGreaterEqual(len(regions), 2, "Expected keyboard-scrollable responsive table regions")

        r_dos = client.get("/dossier/INFY")
        self.assertEqual(r_dos.status_code, 200)
        self.assertIn("Compare Sector Peers", r_dos.text)
        self.assertIn("/compare?tickers=INFY,", r_dos.text)

    def test_4_live_security_tax_bridge_fail_closed_and_calculator_ui(self):
        # Fail-closed when REIT SPV tax_breakdown is missing
        self.assertIsNone(_resolve_reit_taxable_share({"symbol": "MISSING_SPV", "details": {}}))
        disclosed_share = _resolve_reit_taxable_share(
            {"symbol": "EMBASSY", "details": {"tax_breakdown": {"interest_pct": 25.0, "rental_pct": 35.0, "dividend_pct": 10.0}}}
        )
        self.assertAlmostEqual(disclosed_share, 0.65, places=3)

        # 4% Cess & HNI Surcharge slabs
        self.assertAlmostEqual(resolve_effective_slab_pct("SLAB_10_CESS"), 10.40, places=2)
        self.assertAlmostEqual(resolve_effective_slab_pct("SLAB_15_CESS"), 15.60, places=2)
        self.assertAlmostEqual(resolve_effective_slab_pct("HNI_1CR_2CR"), 35.88, places=2)
        self.assertAlmostEqual(resolve_effective_slab_pct("UHNI_ABOVE_2CR"), 39.00, places=2)

        client = TestClient(app)
        r_api = client.get("/api/calculator/live-yields?slab=HNI_50L_1CR&cpi=5.0&limit_per_class=4")
        self.assertEqual(r_api.status_code, 200)
        payload = r_api.json()
        self.assertAlmostEqual(payload["effective_slab_pct"], 34.32, places=2)
        for row in payload.get("instruments", []):
            self.assertNotIn("TEST", row["identifier"].upper())
            self.assertGreater(row["nominal_yield_pct"], 0.0)
            self.assertIsNotNone(row["post_tax_yield_pct"])

        r_calc = client.get("/calculator/tax?tax_slab=34.32&inflation=5.0&yield=8.10")
        self.assertEqual(r_calc.status_code, 200)
        soup = BeautifulSoup(r_calc.text, "html.parser")
        audit_card = soup.find(id="customYieldAuditCard")
        self.assertIsNotNone(audit_card)
        self.assertIn("8.1%", audit_card.get_text())
        self.assertIn("5.32%", audit_card.get_text())

    def test_5_segment_extractor_noise_fix_and_conditional_dossier_card(self):
        md_car_ev_pe = (
            "## Pillar 2: Business Model & Segment Mix\n"
            "[VERIFIED FACT — Q3 FY26 Statutory Segment Filing under Ind AS 108]\n"
            "The enterprise reports audited revenue disaggregation across three primary operating verticals "
            "serving domestic automotive OEMs, fleet electrification operators, and municipal water infrastructure.\n\n"
            "| Operating Segment | Revenue Share (%) |\n"
            "|---|---|\n"
            "| Passenger Car Division | 48.0% |\n"
            "| EV & Mobility Solutions | 32.0% |\n"
            "| PE Pipes & Fittings | 20.0% |\n\n"
            "Executable order book stands at ₹14,250 Cr as of Q3 FY26 with 18-month execution visibility.\n"
        )
        seg_res = extract_ind_as_108_segments(
            "SAMPLEAUTO",
            md_car_ev_pe,
            company_name="Sample Auto Industries",
        )
        self.assertEqual(seg_res["status"], "DISCLOSED")
        names = [s["segment_name"] for s in seg_res["segments"]]
        self.assertIn("Passenger Car Division", names)
        self.assertIn("EV & Mobility Solutions", names)
        self.assertIn("PE Pipes & Fittings", names)
        self.assertEqual(seg_res["order_book_cr"], 14250.0)

        # Valuation table noise (>= 300 chars) must still be rejected
        md_noise = (
            "## Pillar 5: Valuation & Peer Multiples — Infosys Limited (NSE: INFY)\n"
            "The table below summarizes current trading multiples relative to historical 5-year medians "
            "and capital efficiency ratios derived from audited consolidated financial statements for FY2026.\n\n"
            "| Segment Valuation Metric | Revenue Share / Ratio |\n"
            "|---|---|\n"
            "| P/E Ratio | 24.5% |\n"
            "| EV/EBITDA | 16.2% |\n"
            "| Net Margin | 18.4% |\n"
        )
        noise_res = extract_ind_as_108_segments(
            "INFY",
            md_noise,
            company_name="Infosys Limited",
        )
        self.assertEqual(noise_res["status"], "SINGLE_SEGMENT_OR_UNDISCLOSED")

        # Single-segment dossier must NOT render empty #indAs108SegmentCard
        client = TestClient(app)
        with patch("core.analysis.segment_extractor.extract_ind_as_108_segments") as mock_seg:
            mock_seg.return_value = {
                "ticker": "INFY",
                "status": "SINGLE_SEGMENT_OR_UNDISCLOSED",
                "filing_period": "FY26",
                "segments": [],
                "order_book_cr": None,
            }
            r_single = client.get("/dossier/INFY")
            self.assertEqual(r_single.status_code, 200)
            self.assertNotIn('id="indAs108SegmentCard"', r_single.text)

        # Multi-segment dossier MUST render #indAs108SegmentCard
        with patch("core.analysis.segment_extractor.extract_ind_as_108_segments") as mock_seg2:
            mock_seg2.return_value = seg_res
            r_multi = client.get("/dossier/INFY")
            self.assertEqual(r_multi.status_code, 200)
            self.assertIn('id="indAs108SegmentCard"', r_multi.text)
            self.assertIn("Passenger Car Division", r_multi.text)
            self.assertIn("₹14,250", r_multi.text)

    def test_6_thesis_drift_api_redaction_and_single_card(self):
        def _fake_drift(_ticker: str):
            return {
                "ticker": "INFY",
                "status": "DRIFT_COMPUTED",
                "revision_count": 3,
                "prior_snapshot_date": "10 Oct 2026",
                "latest_snapshot_date": "29 Oct 2026",
                "latest_trigger": "Q2 FY27 Statutory Results",
                "price_drift_pct": 6.4,
                "pillar_migrations": [{"pillar": "1. Business Moat", "prior_posture": "Stable", "current_posture": "Strong"}],
                "active_revision_triggers": {
                    "1": "Client concentration rising above 35%",
                    "3": "OCF/EBITDA falling below 75%",
                    "5": "Implied FCF CAGR exceeding 24%",
                },
            }

        anon_client = TestClient(app)
        with patch("core.analysis.guidance_delivery_audit.compute_sequential_thesis_drift", side_effect=_fake_drift):
            r_locked = anon_client.get("/api/equity/thesis-drift/INFY")
            self.assertEqual(r_locked.status_code, 200)
            drift_locked = r_locked.json()["drift"]
            self.assertTrue(drift_locked["deep_dive_locked"])
            self.assertEqual(drift_locked["redacted_trigger_pillars"], [3, 5])
            trig_locked = drift_locked["active_revision_triggers"]
            self.assertEqual(trig_locked["1"], "Client concentration rising above 35%")
            self.assertNotIn("3", trig_locked)
            self.assertNotIn("5", trig_locked)

            # Admin/unlocked session sees Pillars 3 and 5 triggers
            admin_client = TestClient(app)
            admin_client.cookies.set(ADMIN_COOKIE_NAME, _generate_admin_token("admin@moatnomics.com", "owner"))
            r_unlocked = admin_client.get("/api/equity/thesis-drift/INFY")
            self.assertEqual(r_unlocked.status_code, 200)
            drift_unlocked = r_unlocked.json()["drift"]
            self.assertFalse(drift_unlocked["deep_dive_locked"])
            self.assertEqual(drift_unlocked["active_revision_triggers"]["3"], "OCF/EBITDA falling below 75%")
            self.assertEqual(drift_unlocked["active_revision_triggers"]["5"], "Implied FCF CAGR exceeding 24%")

            r_html = anon_client.get("/dossier/INFY")
            self.assertEqual(r_html.status_code, 200)
            soup = BeautifulSoup(r_html.text, "html.parser")
            drift_cards = soup.find_all(id="thesisDriftCard")
            self.assertLessEqual(len(drift_cards), 1, "Must never render duplicate Thesis Drift cards")

    def test_7_returning_visitor_insights_identity_stitch_and_admin_tab(self):
        conn = get_db_connection()
        cur = conn.cursor()
        p = get_placeholder()
        now = datetime.now(timezone.utc)
        t_visit1 = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        t_visit2 = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        t_new = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

        s1 = "sess_rv_v1_991a"
        s2 = "sess_rv_v2_991b"
        s3 = "sess_rv_new_882c"
        vid_repeat = "vis_rahul_repeat_01"
        vid_new = "vis_ananya_first_02"
        reader_email = "rahul.sharma@moatreader.in"

        try:
            # Visit #1 (3 days ago, anonymous): /equities -> /dossier/INFY
            cur.execute(
                f"""
                INSERT INTO site_usage_events
                    (session_id, user_id, user_email, event_type, ticker, landing_page, traffic_source, details, browser, timestamp)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                """,
                (
                    s1,
                    None,
                    None,
                    "PAGE_DWELL",
                    "INFY",
                    "/dossier/INFY",
                    "Google Search",
                    json.dumps({"visitor_id": vid_repeat, "visit_number": 1, "is_returning": False, "dwell_seconds": 95}),
                    "Chrome 135",
                    t_visit1,
                ),
            )
            # Visit #2 (2 hours ago, signed in as Rahul Sharma): returns directly to /dossier/INFY then /compare
            cur.execute(
                f"""
                INSERT INTO site_usage_events
                    (session_id, user_id, user_email, event_type, ticker, landing_page, traffic_source, details, browser, timestamp)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                """,
                (
                    s2,
                    "usr_rahul_01",
                    reader_email,
                    "PAGE_DWELL",
                    "INFY",
                    "/dossier/INFY",
                    "Direct / Bookmark",
                    json.dumps({
                        "visitor_id": vid_repeat,
                        "visit_number": 2,
                        "is_returning": True,
                        "days_since_last_visit": 2.9,
                        "dwell_seconds": 140,
                        "to_path": "/compare",
                    }),
                    "Chrome 135",
                    t_visit2,
                ),
            )
            # Separate 1-time visitor
            cur.execute(
                f"""
                INSERT INTO site_usage_events
                    (session_id, user_id, user_email, event_type, ticker, landing_page, traffic_source, details, browser, timestamp)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                """,
                (
                    s3,
                    None,
                    None,
                    "PAGE_DWELL",
                    "",
                    "/equities",
                    "Organic",
                    json.dumps({"visitor_id": vid_new, "visit_number": 1, "is_returning": False, "dwell_seconds": 30}),
                    "Safari 18",
                    t_new,
                ),
            )
            conn.commit()

            insights = get_returning_visitor_insights(days=30, exclude_tests=True, limit=25)
            self.assertGreaterEqual(insights["returning_visitors"], 1)
            self.assertGreaterEqual(insights["identified_returning_count"], 1)

            magnet_paths = [m["path"] for m in insights["return_magnets"]]
            self.assertIn("/dossier/INFY", magnet_paths)

            rahul_tl = next(
                (tl for tl in insights["returning_timelines"] if tl["display_identity"] == reader_email),
                None,
            )
            self.assertIsNotNone(rahul_tl, "Expected anonymous Visit #1 + signed-in Visit #2 stitched to rahul.sharma@moatreader.in")
            self.assertEqual(rahul_tl["visit_count"], 2)
            self.assertIn("INFY", rahul_tl["top_tickers"])

            # Verify /admin/api/returning-visitors auth gate + /admin?tab=traffic UI contract
            unauth_client = TestClient(app)
            self.assertEqual(unauth_client.get("/admin/api/returning-visitors").status_code, 403)

            admin_client = TestClient(app)
            admin_client.cookies.set(ADMIN_COOKIE_NAME, _generate_admin_token("admin@moatnomics.com", "owner"))
            api_resp = admin_client.get("/admin/api/returning-visitors?days=30")
            self.assertEqual(api_resp.status_code, 200)
            self.assertGreaterEqual(api_resp.json()["returning_visitors"], 1)

            ui_resp = admin_client.get("/admin?tab=traffic")
            self.assertEqual(ui_resp.status_code, 200)
            soup = BeautifulSoup(ui_resp.text, "html.parser")
            self.assertIsNotNone(soup.find(id="cardReturningVisitorsIntel"))
            self.assertIsNotNone(soup.find(id="tableReturnMagnets"))
            self.assertIsNotNone(soup.find(id="returningTimelinesContainer"))
            self.assertIn(reader_email, ui_resp.text)
        finally:
            cur2 = conn.cursor()
            cur2.execute(
                f"DELETE FROM site_usage_events WHERE session_id IN ({p}, {p}, {p})",
                (s1, s2, s3),
            )
            conn.commit()
            cur2.close()
            cur.close()
            conn.close()

        # Verify client-side fetchLater polyfill + AbortController + returning visitor metadata in main.js
        with open("web/static/js/main.js", "r", encoding="utf-8") as jf:
            js_src = jf.read()
        self.assertIn("globalThis.fetchLater ??= function fetchLater", js_src)
        self.assertIn("new AbortController()", js_src)
        self.assertIn("function getReturningVisitorMeta()", js_src)
        self.assertIn("sr_visitor_id", js_src)


if __name__ == "__main__":
    unittest.main()
