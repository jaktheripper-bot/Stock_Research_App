"""
tests/outside_in/test_admin_traffic_flow.py
===========================================
Outside-In & Contract Verification Test Suite for:
1. Traffic Dwell Time & Site Visit Tree Analytics Engine (core/db/telemetry.py)
2. Admin REST API Endpoint (GET /api/admin/traffic/flow)
3. Admin Console UI Tab Rendering & DOM Contract Integrity (/admin?tab=traffic)
4. Client-Side Telemetry & Interactive Search/Filter Wiring
"""
import os
os.environ["TESTING"] = "1"

import unittest
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from web.main import app
from core.db.telemetry import (
    compute_page_dwell_and_visit_tree,
    format_duration,
    get_traffic_flow_analytics,
    get_site_usage_summary,
    get_session_journeys,
    _parse_event_ts,
)
from web.common import _generate_admin_token, ADMIN_COOKIE_NAME


class TestTrafficFlowAnalyticsEngine(unittest.TestCase):
    """Validates mathematical and structural correctness of page dwell times and the site visit tree."""

    def test_format_duration(self):
        self.assertEqual(format_duration(0), "0s")
        self.assertEqual(format_duration(45), "45s")
        self.assertEqual(format_duration(90), "1m 30s")
        self.assertEqual(format_duration(3600), "1h 00m")
        self.assertEqual(format_duration(3665), "1h 01m")

    def test_compute_page_dwell_and_visit_tree_simulation(self):
        t0 = datetime(2026, 10, 15, 10, 0, 0)
        events = [
            # Session 1: / -> /dossier/INFY (explicit 60s dwell) -> /compare (explicit 120s dwell) -> Exit
            (1, "sess_1", "/", json.dumps({"dwell_seconds": 25, "to_path": "/dossier/INFY"}), "", "PAGE_DWELL", t0),
            (2, "sess_1", "/dossier/INFY", json.dumps({"dwell_seconds": 60, "to_path": "/compare"}), "INFY", "PAGE_DWELL", t0 + timedelta(seconds=25)),
            (3, "sess_1", "/compare", json.dumps({"dwell_seconds": 120}), "", "PAGE_DWELL", t0 + timedelta(seconds=85)),
            # Session 2: / -> /dossier/INFY (inter-event delta 40s) -> Exit (terminal default dwell)
            (4, "sess_2", "/", "{}", "", "VIEW", t0 + timedelta(minutes=5)),
            (5, "sess_2", "/dossier/INFY", "{}", "INFY", "VIEW", t0 + timedelta(minutes=5, seconds=40)),
            # Session 3: /pricing -> /contact -> Exit
            (6, "sess_3", "/pricing", json.dumps({"to_path": "/contact"}), "", "VIEW", t0 + timedelta(minutes=10)),
            (7, "sess_3", "/contact", "{}", "", "VIEW", t0 + timedelta(minutes=10, seconds=50)),
        ]

        result = compute_page_dwell_and_visit_tree(events)

        self.assertIn("page_dwell_times", result)
        self.assertIn("site_visit_tree", result)
        self.assertIn("overall_avg_dwell_seconds", result)
        self.assertIn("formatted_overall_avg_dwell", result)
        self.assertIn("total_dwell_hours", result)
        self.assertIn("total_navigation_transitions", result)
        self.assertIn("top_contributing_page", result)

        dwells = {item["path"]: item for item in result["page_dwell_times"]}
        self.assertIn("/", dwells)
        self.assertIn("/dossier/INFY", dwells)
        self.assertIn("/compare", dwells)

        # /compare has 120s dwell -> tier should be "high" (Deep Read (>90s))
        self.assertEqual(dwells["/compare"]["tier"], "high")
        self.assertIn("Deep Read", dwells["/compare"]["tier_label"])

        # Check visit tree transitions
        tree_map = {node["from_path"]: node for node in result["site_visit_tree"]}
        self.assertIn("/", tree_map)
        home_node = tree_map["/"]
        self.assertEqual(home_node["total_outbound"], 2)  # sess_1 and sess_2 both moved to /dossier/INFY
        self.assertEqual(len(home_node["destinations"]), 1)
        self.assertEqual(home_node["destinations"][0]["to_path"], "/dossier/INFY")
        self.assertEqual(home_node["destinations"][0]["count"], 2)
        self.assertEqual(home_node["destinations"][0]["percentage"], 100.0)

        # /dossier/INFY contributed to /compare (sess_1) and exited in sess_2
        self.assertIn("/dossier/INFY", tree_map)
        infy_node = tree_map["/dossier/INFY"]
        self.assertEqual(infy_node["total_outbound"], 1)
        self.assertEqual(infy_node["exit_count"], 1)
        self.assertEqual(infy_node["destinations"][0]["to_path"], "/compare")

    def test_get_traffic_flow_analytics_structure(self):
        flow = get_traffic_flow_analytics(days=30, exclude_tests=False)
        self.assertIsInstance(flow, dict)
        self.assertIn("page_dwell_times", flow)
        self.assertIn("site_visit_tree", flow)
        self.assertIn("overall_avg_dwell_seconds", flow)
        self.assertIn("formatted_overall_avg_dwell", flow)
        self.assertIn("total_dwell_hours", flow)
        self.assertIn("total_navigation_transitions", flow)

    def test_get_site_usage_summary_includes_dwell_and_tree(self):
        summary = get_site_usage_summary(days=30, exclude_tests=False)
        self.assertIn("page_dwell_times", summary)
        self.assertIn("site_visit_tree", summary)
        self.assertIn("overall_avg_dwell_seconds", summary)
        self.assertIn("formatted_overall_avg_dwell", summary)
        self.assertIn("total_dwell_hours", summary)
        self.assertIn("total_navigation_transitions", summary)
        self.assertIn("recent_events", summary)
        for ev in summary["recent_events"][:5]:
            self.assertIn("timestamp", ev)
            self.assertIn("formatted_time", ev)
            self.assertIn("traffic_source", ev)
            self.assertIn("source", ev)

    def test_parse_event_ts(self):
        self.assertIsNone(_parse_event_ts(None))
        self.assertIsNone(_parse_event_ts(""))
        self.assertIsNone(_parse_event_ts("invalid_ts_format"))
        dt = datetime(2026, 10, 19, 10, 30, 45)
        self.assertEqual(_parse_event_ts(dt), dt)
        self.assertEqual(_parse_event_ts("2026-10-19 10:30:45"), dt)
        self.assertEqual(_parse_event_ts("2026-10-19T10:30:45.999999"), dt)

    def test_session_journeys_duration_and_steps(self):
        from core.db.connection import get_db_connection, get_placeholder
        sess_id = "sess_duration_test_ outside_in"
        conn = get_db_connection()
        c = conn.cursor()
        p = get_placeholder()
        t0 = datetime(2026, 10, 19, 8, 0, 0)
        t1 = t0 + timedelta(seconds=42)
        try:
            c.execute(f"""
                INSERT INTO site_usage_events (session_id, event_type, ticker, timestamp, landing_page, traffic_source)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p})
            """, (sess_id, "PAGE_VIEW", "APP", t0, "/funds", "Google Search"))
            c.execute(f"""
                INSERT INTO site_usage_events (session_id, event_type, ticker, timestamp, landing_page, traffic_source)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p})
            """, (sess_id, "DOSSIER_VIEW", "INFY", t1, "/dossier/INFY", "Google Search"))
            conn.commit()

            journeys = get_session_journeys(days=365, limit=50, exclude_tests=False)
            test_j = next((j for j in journeys if j["session_id"] == sess_id), None)
            self.assertIsNotNone(test_j, "Test session journey not found")
            self.assertEqual(test_j["landing_page"], "/funds")
            self.assertEqual(test_j["started_at"], test_j["start_time"])
            self.assertEqual(test_j["duration_seconds"], 42)
            self.assertEqual(test_j["formatted_duration"], "42s")
            self.assertEqual(test_j["steps"], test_j["events"])
            self.assertEqual(len(test_j["steps"]), 2)
            self.assertEqual(test_j["steps"][0]["delta_sec"], 0)
            self.assertEqual(test_j["steps"][0]["ticker"], "")  # 'APP' was filtered out
            self.assertEqual(test_j["steps"][1]["delta_sec"], 42)
            self.assertEqual(test_j["steps"][1]["ticker"], "INFY")
        finally:
            c.execute(f"DELETE FROM site_usage_events WHERE session_id = {p}", (sess_id,))
            conn.commit()
            c.close()
            conn.close()


class TestTrafficFlowApiEndpoint(unittest.TestCase):
    """Validates security and payload contracts of GET /api/admin/traffic/flow."""

    def setUp(self):
        self.client = TestClient(app)

    def test_unauthenticated_request_rejected(self):
        resp = self.client.get("/api/admin/traffic/flow")
        self.assertEqual(resp.status_code, 403)

    def test_authenticated_admin_returns_traffic_flow(self):
        admin_token = _generate_admin_token("lyndnpnto@gmail.com", "owner")
        self.client.cookies.set(ADMIN_COOKIE_NAME, admin_token)

        resp = self.client.get("/api/admin/traffic/flow?days=30")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIn("flow", data)
        flow = data["flow"]
        self.assertIn("page_dwell_times", flow)
        self.assertIn("site_visit_tree", flow)
        self.assertIn("overall_avg_dwell_seconds", flow)
        self.assertIn("total_navigation_transitions", flow)


class TestAdminTrafficUiAndDomContracts(unittest.TestCase):
    """Outside-in DOM assertions verifying Tab 4 traffic elements, dwell tables, and visit tree."""

    def setUp(self):
        self.client = TestClient(app)
        admin_token = _generate_admin_token("lyndnpnto@gmail.com", "owner")
        self.client.cookies.set(ADMIN_COOKIE_NAME, admin_token)

    def test_admin_traffic_tab_renders_with_complete_contracts(self):
        resp = self.client.get("/admin?tab=traffic")
        self.assertEqual(resp.status_code, 200)

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. Assert tab container is active
        traffic_pane = soup.find("div", id="tab-traffic")
        self.assertIsNotNone(traffic_pane, "Missing #tab-traffic pane in admin console.")
        self.assertIn("active", traffic_pane.get("class", []))

        # 2. Assert Dwell & Visit Tree KPI cards are rendered
        pane_text = traffic_pane.get_text()
        self.assertIn("Avg Link Dwell Time", pane_text)
        self.assertIn("Total Attention Spent", pane_text)
        self.assertIn("Site Visit Transitions", pane_text)
        self.assertIn("Top Downstream Driver", pane_text)

        # 3. Assert Link Dwell Table and Column Headers with Interactive Sorting Controls
        dwell_table = soup.find("table", id="tablePageDwellTimes")
        self.assertIsNotNone(dwell_table, "Missing #tablePageDwellTimes table in DOM.")
        headers = [th.get_text(strip=True) for th in dwell_table.find_all("th")]
        expected_headers = ["Page Link / URL Route", "Category", "Avg Dwell Time", "Engagement Tier", "Total Attention Spent", "Visits Tracked", "Attention Share"]
        for exp in expected_headers:
            self.assertTrue(any(exp in h for h in headers), f"Header '{exp}' not found in dwell table.")

        # 3b. Outside-in contract: Sortable headers and click/keyboard affordances
        sortable_ths = dwell_table.find_all("th", class_="dwell-sortable-th")
        self.assertEqual(len(sortable_ths), 7, "All 7 column headers must be sortable (.dwell-sortable-th).")
        expected_keys = ["path", "category", "avg-dwell", "tier-rank", "total-dwell", "visits", "attention-share"]
        for th in sortable_ths:
            key = th.get("data-sort-key")
            self.assertIn(key, expected_keys, f"Unexpected sort key: {key}")
            self.assertEqual(th.get("role"), "columnheader")
            self.assertEqual(th.get("tabindex"), "0")
            self.assertIn(f"sortDwellTable('{key}')", th.get("onclick", ""))
            indicator = th.find("span", id=f"dwell-sort-ind-{key}")
            self.assertIsNotNone(indicator, f"Missing sort indicator span for column {key}")

        # 3c. Default sort contract: Total Attention Spent is active descending
        total_th = dwell_table.find("th", attrs={"data-sort-key": "total-dwell"})
        self.assertIsNotNone(total_th)
        self.assertIn("sorted-active", total_th.get("class", []))
        self.assertEqual(total_th.get("aria-sort"), "descending")
        self.assertEqual(total_th.find("span", id="dwell-sort-ind-total-dwell").get_text(strip=True), "▼")

        # 4. Assert Site Visit Tree Container and Filter Inputs
        tree_container = soup.find("div", id="siteVisitTreeContainer")
        self.assertIsNotNone(tree_container, "Missing #siteVisitTreeContainer in DOM.")

        filter_dwell = soup.find("input", id="inputFilterDwell")
        self.assertIsNotNone(filter_dwell, "Missing #inputFilterDwell search input.")
        self.assertIn("filterDwellTable()", filter_dwell.get("onkeyup", ""))

        filter_tree = soup.find("input", id="inputFilterVisitTree")
        self.assertIsNotNone(filter_tree, "Missing #inputFilterVisitTree search input.")
        self.assertIn("filterSiteVisitTree()", filter_tree.get("onkeyup", ""))

        # 5. Assert Service Inbox & Dwell Table JavaScript functions exist in scripts
        script_text = "\n".join(s.string for s in soup.find_all("script") if s.string)
        self.assertIn("openTicketReplyModal", script_text, "openTicketReplyModal must be defined in scripts.")
        self.assertIn("closeTicketReplyModal", script_text, "closeTicketReplyModal must be defined in scripts.")
        self.assertIn("filterDwellTable", script_text, "filterDwellTable must be defined in scripts.")
        self.assertIn("filterSiteVisitTree", script_text, "filterSiteVisitTree must be defined in scripts.")
        self.assertIn("sortDwellTable", script_text, "sortDwellTable must be defined in scripts.")
        self.assertIn("handleDwellHeaderKeydown", script_text, "handleDwellHeaderKeydown must be defined in scripts.")
        self.assertIn("updateDwellSortHeaders", script_text, "updateDwellSortHeaders must be defined in scripts.")
        self.assertIn("DWELL_COLUMN_CONFIG", script_text, "DWELL_COLUMN_CONFIG must be defined in scripts.")

        # 5b. Assert Pillar-level breakdown card is present in #tab-traffic
        pillar_card = soup.find("div", id="cardPillarDwellBreakdown")
        self.assertIsNotNone(pillar_card, "Missing #cardPillarDwellBreakdown in #tab-traffic.")

        # 6. Template Hygiene: Zero unrendered Jinja leaks in HTML attributes
        for tag in soup.find_all(True):
            for attr_name, attr_val in tag.attrs.items():
                val_str = " ".join(attr_val) if isinstance(attr_val, list) else str(attr_val)
                self.assertNotIn("{{", val_str, f"Unrendered Jinja expression found in <{tag.name} {attr_name}='{val_str}'>")
                self.assertNotIn("{%", val_str, f"Unrendered Jinja block found in <{tag.name} {attr_name}='{val_str}'>")

    def test_single_page_bounce_records_zero_dwell_not_fake_65s(self):
        """#6a: Single-page bounce with no exit beacon must record 0.0s dwell, never fabricated 65s/55s."""
        t0 = datetime(2026, 10, 20, 9, 0, 0)
        events = [
            (1, "sess_bounce_only", "/dossier/RELIANCE", "{}", "RELIANCE", "DOSSIER_VIEW", t0),
        ]
        res = compute_page_dwell_and_visit_tree(events)
        dwells = {d["path"]: d for d in res["page_dwell_times"]}
        self.assertIn("/dossier/RELIANCE", dwells)
        self.assertEqual(dwells["/dossier/RELIANCE"]["avg_dwell_seconds"], 0.0)
        self.assertEqual(dwells["/dossier/RELIANCE"]["total_dwell_seconds"], 0.0)
        self.assertEqual(dwells["/dossier/RELIANCE"]["measured_visits_count"], 0)
        self.assertEqual(dwells["/dossier/RELIANCE"]["visits_count"], 1)

    def test_dwell_beacon_coalesces_without_inflating_visits_and_tracks_pillars(self):
        """Options 1 & 2: PAGE_DWELL beacon coalesces onto prior page view, records scroll & pillar dwell."""
        t0 = datetime(2026, 10, 20, 10, 0, 0)
        events = [
            (1, "sess_reader", "/dossier/TCS", "{}", "TCS", "DOSSIER_VIEW", t0),
            (
                2,
                "sess_reader",
                "/dossier/TCS",
                json.dumps({
                    "dwell_seconds": 95.0,
                    "max_scroll_pct": 84,
                    "pillar_dwell": {"pillar-1": 35, "pillar-4": 60},
                }),
                "TCS",
                "PAGE_DWELL",
                t0 + timedelta(seconds=95),
            ),
        ]
        res = compute_page_dwell_and_visit_tree(events)
        dwells = {d["path"]: d for d in res["page_dwell_times"]}
        self.assertIn("/dossier/TCS", dwells)
        tcs = dwells["/dossier/TCS"]
        self.assertEqual(tcs["visits_count"], 1, "PAGE_DWELL must coalesce onto DOSSIER_VIEW without doubling visits.")
        self.assertEqual(tcs["measured_visits_count"], 1)
        self.assertEqual(tcs["avg_dwell_seconds"], 95.0)
        self.assertEqual(tcs["avg_scroll_pct"], 84)

        pillars = {p["section"]: p["total_seconds"] for p in res.get("pillar_dwell_breakdown", [])}
        self.assertEqual(pillars.get("pillar-4"), 60.0)
        self.assertEqual(pillars.get("pillar-1"), 35.0)

    def test_post_telemetry_dwell_endpoint_and_billables_date_window(self):
        """#6a + #6b: POST /api/telemetry/dwell records active attention; get_all_billables respects days filter."""
        from core.db.users import get_all_billables
        from core.db.connection import get_db_connection, get_placeholder

        anon_client = TestClient(app)
        resp = anon_client.post(
            "/api/telemetry/dwell",
            json={
                "event_type": "PAGE_DWELL",
                "path": "/dossier/HDFCBANK",
                "ticker": "HDFCBANK",
                "dwell_seconds": 72.5,
                "max_scroll_pct": 68,
                "pillar_dwell": {"pillar-2": 40, "pillar-5": 32.5},
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "ok")

        # Verify #6b: get_all_billables filters out transactions outside selected days window
        conn = get_db_connection()
        c = conn.cursor()
        p = get_placeholder()
        old_tx_id = "tx_test_old_window_6b"
        recent_tx_id = "tx_test_recent_window_6b"
        old_ts = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S")
        recent_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            c.execute(
                f"INSERT INTO credit_transactions (id, user_id, amount_inr, credits_added, payment_gateway, status, pack_type, created_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})",
                (old_tx_id, "usr_test_6b", 99.0, 1.0, "razorpay", "captured", "single", old_ts),
            )
            c.execute(
                f"INSERT INTO credit_transactions (id, user_id, amount_inr, credits_added, payment_gateway, status, pack_type, created_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})",
                (recent_tx_id, "usr_test_6b", 99.0, 1.0, "razorpay", "captured", "single", recent_ts),
            )
            conn.commit()

            rows_7d = get_all_billables(limit=200, days=7, exclude_tests=False)
            ids_7d = {r["id"] for r in rows_7d}
            self.assertIn(recent_tx_id, ids_7d)
            self.assertNotIn(old_tx_id, ids_7d, "45-day-old billable must not leak into 7-day window (#6b).")

            rows_90d = get_all_billables(limit=200, days=90, exclude_tests=False)
            ids_90d = {r["id"] for r in rows_90d}
            self.assertIn(recent_tx_id, ids_90d)
            self.assertIn(old_tx_id, ids_90d)
        finally:
            c.execute(f"DELETE FROM credit_transactions WHERE id IN ({p}, {p})", (old_tx_id, recent_tx_id))
            c.execute(f"DELETE FROM site_usage_events WHERE ticker = {p} AND event_type = {p}", ("HDFCBANK", "PAGE_DWELL"))
            conn.commit()
            c.close()
            conn.close()

    def test_dossier_templates_include_reading_progress_bar_and_study_timer(self):
        """Option 3: All 5 dossier templates and main.js wire #dossierReadingProgressBar & #dossierReadTimeBadge."""
        template_files = [
            "web/templates/dossier.html",
            "web/templates/fund_dossier.html",
            "web/templates/debt_dossier.html",
            "web/templates/reit_dossier.html",
            "web/templates/msme_dossier.html",
        ]
        for path in template_files:
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
            self.assertIn('id="dossierReadingProgressBar"', html, f"Missing #dossierReadingProgressBar in {path}")
            self.assertIn('id="dossierReadingProgressFill"', html, f"Missing #dossierReadingProgressFill in {path}")
            self.assertIn('id="dossierReadTimeBadge"', html, f"Missing #dossierReadTimeBadge in {path}")
            self.assertIn('id="dossierEstReadMinutes"', html, f"Missing #dossierEstReadMinutes in {path}")
            self.assertIn('id="dossierActiveTimerText"', html, f"Missing #dossierActiveTimerText in {path}")

        with open("web/static/js/main.js", "r", encoding="utf-8") as f:
            js_code = f.read()
        self.assertIn("/api/telemetry/dwell", js_code)
        self.assertIn("dossierReadingProgressFill", js_code)
        self.assertIn("dossierActiveTimerText", js_code)
        self.assertIn("unsentPillarDwell", js_code)

    def test_consolidated_5_hub_navigation_contracts(self):
        """#7: Verify Admin Console renders Consolidated 5-Hub Primary Navigation + Contextual Sub-View Bar."""
        resp = self.client.get("/admin?tab=traffic")
        self.assertEqual(resp.status_code, 200)
        soup = BeautifulSoup(resp.text, "html.parser")

        hub_nav = soup.find("div", id="adminPrimaryHubNav")
        self.assertIsNotNone(hub_nav, "Missing #adminPrimaryHubNav 5-Hub container.")
        hub_btns = hub_nav.find_all("button", class_="admin-hub-btn")
        self.assertEqual(len(hub_btns), 5, "Expected exactly 5 primary Executive Hubs.")
        hub_ids = [b.get("data-hub") for b in hub_btns]
        self.assertEqual(hub_ids, ["revenue", "service", "traffic", "platform", "governance"])

        # Deep-linking to ?tab=traffic must mark the 'traffic' hub active
        traffic_hub_btn = hub_nav.find("button", attrs={"data-hub": "traffic"})
        self.assertIn("active", traffic_hub_btn.get("class", []))

        # Sub-tab bar must group all 13 sub-views under the 5 hubs
        sub_nav = soup.find("div", id="adminSubTabNav")
        self.assertIsNotNone(sub_nav, "Missing #adminSubTabNav contextual sub-view bar.")
        sub_btns = sub_nav.find_all("button", class_="admin-tab-btn")
        self.assertEqual(len(sub_btns), 13)
        for b in sub_btns:
            self.assertIn(b.get("data-hub"), {"revenue", "service", "traffic", "platform", "governance"})

        # Verify JS wiring for showHub & TAB_TO_HUB_MAP
        script_text = "\n".join(s.string for s in soup.find_all("script") if s.string)
        self.assertIn("function showHub(", script_text)
        self.assertIn("TAB_TO_HUB_MAP", script_text)
        self.assertIn("HUB_DEFAULT_TAB_MAP", script_text)




if __name__ == "__main__":
    unittest.main()
