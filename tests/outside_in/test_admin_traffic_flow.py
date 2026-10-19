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

        # 3. Assert Link Dwell Table and Column Headers
        dwell_table = soup.find("table", id="tablePageDwellTimes")
        self.assertIsNotNone(dwell_table, "Missing #tablePageDwellTimes table in DOM.")
        headers = [th.get_text(strip=True) for th in dwell_table.find_all("th")]
        expected_headers = ["Page Link / URL Route", "Category", "Avg Dwell Time", "Engagement Tier", "Total Attention Spent", "Visits Tracked", "Attention Share"]
        for exp in expected_headers:
            self.assertTrue(any(exp in h for h in headers), f"Header '{exp}' not found in dwell table.")

        # 4. Assert Site Visit Tree Container and Filter Inputs
        tree_container = soup.find("div", id="siteVisitTreeContainer")
        self.assertIsNotNone(tree_container, "Missing #siteVisitTreeContainer in DOM.")

        filter_dwell = soup.find("input", id="inputFilterDwell")
        self.assertIsNotNone(filter_dwell, "Missing #inputFilterDwell search input.")
        self.assertIn("filterDwellTable()", filter_dwell.get("onkeyup", ""))

        filter_tree = soup.find("input", id="inputFilterVisitTree")
        self.assertIsNotNone(filter_tree, "Missing #inputFilterVisitTree search input.")
        self.assertIn("filterSiteVisitTree()", filter_tree.get("onkeyup", ""))

        # 5. Assert Service Inbox JavaScript functions exist in scripts
        script_text = "\n".join(s.string for s in soup.find_all("script") if s.string)
        self.assertIn("openTicketReplyModal", script_text, "openTicketReplyModal must be defined in scripts.")
        self.assertIn("closeTicketReplyModal", script_text, "closeTicketReplyModal must be defined in scripts.")
        self.assertIn("filterDwellTable", script_text, "filterDwellTable must be defined in scripts.")
        self.assertIn("filterSiteVisitTree", script_text, "filterSiteVisitTree must be defined in scripts.")

        # 6. Template Hygiene: Zero unrendered Jinja leaks in HTML attributes
        for tag in soup.find_all(True):
            for attr_name, attr_val in tag.attrs.items():
                val_str = " ".join(attr_val) if isinstance(attr_val, list) else str(attr_val)
                self.assertNotIn("{{", val_str, f"Unrendered Jinja expression found in <{tag.name} {attr_name}='{val_str}'>")
                self.assertNotIn("{%", val_str, f"Unrendered Jinja block found in <{tag.name} {attr_name}='{val_str}'>")


if __name__ == "__main__":
    unittest.main()
