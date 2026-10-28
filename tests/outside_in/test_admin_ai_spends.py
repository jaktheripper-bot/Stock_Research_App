"""
tests/outside_in/test_admin_ai_spends.py
========================================
Outside-In & Contract Verification Test Suite for:
1. Gemini Spends & Token Telemetry Analytics Engine (core/analytics/ai_spends.py)
2. Admin REST API Endpoint (GET /api/admin/ai-spends)
3. Admin Console UI Tab Rendering & DOM Contract Integrity (/admin?tab=ai-spends)
"""
import os
os.environ["TESTING"] = "1"

import unittest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from web.main import app
from core.analytics.ai_spends import get_gemini_spends_summary
from web.common import _generate_admin_token, ADMIN_COOKIE_NAME


class TestAiSpendsAnalyticsEngine(unittest.TestCase):
    """Validates mathematical correctness and structure of AI spends telemetry."""

    def test_get_gemini_spends_summary_structure(self):
        summary = get_gemini_spends_summary()
        self.assertIsInstance(summary, dict)

        required_keys = [
            "total_cost_usd",
            "total_cost_inr",
            "total_tokens",
            "total_input_tokens",
            "total_output_tokens",
            "primary_model",
            "fallback_models",
            "rate_card",
            "cortex_precompression_savings_pct",
            "features",
        ]
        for key in required_keys:
            self.assertIn(key, summary, f"Missing key in AI spends summary: {key}")

        self.assertGreaterEqual(summary["total_cost_usd"], 0.0)
        self.assertGreaterEqual(summary["total_cost_inr"], 0.0)
        self.assertGreaterEqual(summary["total_tokens"], 0)
        self.assertGreaterEqual(summary["cortex_precompression_savings_pct"], 90.0)

    def test_feature_workloads_breakdown(self):
        summary = get_gemini_spends_summary()
        features = summary.get("features", [])
        self.assertGreaterEqual(len(features), 5, "Expected at least 5 tracked feature workloads.")

        feature_ids = [f["id"] for f in features]
        self.assertIn("equity_dossiers", feature_ids)
        self.assertIn("mutual_funds", feature_ids)
        self.assertIn("copilot_desk", feature_ids)
        self.assertIn("ai_auditor", feature_ids)
        self.assertIn("deterministic_engines", feature_ids)

        total_shares = 0.0
        for f in features:
            self.assertIn("name", f)
            self.assertIn("target_engine", f)
            self.assertIn("cost_usd", f)
            self.assertIn("share_pct", f)
            self.assertGreaterEqual(f["cost_usd"], 0.0)
            self.assertGreaterEqual(f["share_pct"], 0.0)
            total_shares += f["share_pct"]

        # Total share should sum to ~100% (allowing small rounding tolerance)
        self.assertAlmostEqual(total_shares, 100.0, delta=1.5)


class TestAiSpendsApiEndpoint(unittest.TestCase):
    """Validates security and payload contracts of GET /api/admin/ai-spends."""

    def setUp(self):
        self.client = TestClient(app)

    def test_unauthenticated_request_rejected(self):
        resp = self.client.get("/api/admin/ai-spends")
        self.assertIn(resp.status_code, [401, 403], "Unauthenticated request must be rejected.")

    def test_authenticated_admin_retrieves_spends_json(self):
        admin_token = _generate_admin_token("lyndnpnto@gmail.com", "owner")
        self.client.cookies.set(ADMIN_COOKIE_NAME, admin_token)

        resp = self.client.get("/api/admin/ai-spends")
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIn("spends", data)

        spends = data["spends"]
        self.assertIn("total_cost_usd", spends)
        self.assertIn("total_tokens", spends)
        self.assertIn("features", spends)

    def test_unauthenticated_provider_constraints_rejected(self):
        resp = self.client.get("/api/admin/provider-constraints")
        self.assertIn(resp.status_code, [401, 403], "Unauthenticated provider constraints request must be rejected.")

    def test_authenticated_admin_retrieves_provider_constraints_json(self):
        admin_token = _generate_admin_token("lyndnpnto@gmail.com", "owner")
        self.client.cookies.set(ADMIN_COOKIE_NAME, admin_token)

        resp = self.client.get("/api/admin/provider-constraints")
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIn("provider_constraints", data)
        constraints = data["provider_constraints"]
        self.assertIn("providers", constraints)
        self.assertIn("healthy_count", constraints)
        self.assertIn("total_count", constraints)
        self.assertEqual(len(constraints["providers"]), constraints["total_count"])
        self.assertGreaterEqual(len(constraints["providers"]), 6)

        host_card = next((p for p in constraints["providers"] if p["id"] == "host_runtime"), None)
        self.assertIsNotNone(host_card, "Missing host_runtime card in provider constraints")
        self.assertIn("Peak RSS:", host_card.get("secondary_metric", ""))
        self.assertIn("MB RAM", host_card.get("primary_metric", ""))


class TestAiSpendsAdminUiOutsideIn(unittest.TestCase):
    """Outside-in contract testing for /admin?tab=ai-spends DOM rendering."""

    def setUp(self):
        self.client = TestClient(app)
        self.admin_token = _generate_admin_token("lyndnpnto@gmail.com", "owner")
        self.client.cookies.set(ADMIN_COOKIE_NAME, self.admin_token)

    def test_admin_dashboard_ai_spends_tab_renders_200(self):
        resp = self.client.get("/admin?tab=ai-spends")
        self.assertEqual(resp.status_code, 200)

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. Navigation Tab Trigger Contract
        tab_btn = soup.find("button", attrs={"data-tab": "ai-spends"})
        self.assertIsNotNone(tab_btn, "Missing .admin-tab-btn[data-tab='ai-spends']")
        self.assertIn("active", tab_btn.get("class", []))
        self.assertIn("showTab('ai-spends')", tab_btn.get("onclick", ""))

        # 2. Tab Pane Container Contract
        tab_pane = soup.find("div", id="tab-ai-spends")
        self.assertIsNotNone(tab_pane, "Missing tab pane #tab-ai-spends")
        self.assertIn("active", tab_pane.get("class", []))

        # 3. Provider Constraints & Quotas Monitor Card Contract
        constraints_card = soup.find("div", id="cardProviderConstraints")
        self.assertIsNotNone(constraints_card, "Missing #cardProviderConstraints in #tab-ai-spends")
        self.assertIn("Subscribed Service Provider Quotas", constraints_card.text)
        self.assertIn("Providers Healthy", constraints_card.text)

        # 4. KPI Elements Binding Contract (INR Primary)
        cost_inr_el = soup.find("div", id="aiKpiTotalCostInr")
        self.assertIsNotNone(cost_inr_el, "Missing KPI element #aiKpiTotalCostInr")
        self.assertIn("INR", cost_inr_el.text)
        self.assertIn("₹", cost_inr_el.text)

        cost_el = soup.find("div", id="aiKpiTotalCostUsd")
        self.assertIsNotNone(cost_el, "Missing KPI element #aiKpiTotalCostUsd")
        self.assertIn("tokens", cost_el.text)

        tokens_el = soup.find("div", id="aiKpiTotalTokens")
        self.assertIsNotNone(tokens_el, "Missing KPI element #aiKpiTotalTokens")

        # 5. Refresh Button Tactile Contract
        refresh_btn = soup.find("button", id="btnRefreshAiSpends")
        self.assertIsNotNone(refresh_btn, "Missing refresh button #btnRefreshAiSpends")
        self.assertIn("btn", refresh_btn.get("class", []))
        self.assertIn("refreshAiSpends()", refresh_btn.get("onclick", ""))

        # 6. Table & Rows Rendering Contract
        table = soup.find("table", id="tableAiSpends")
        self.assertIsNotNone(table, "Missing table #tableAiSpends")
        tbody = soup.find("tbody", id="tbodyAiSpends")
        self.assertIsNotNone(tbody, "Missing tbody #tbodyAiSpends")
        rows = tbody.find_all("tr")
        self.assertGreaterEqual(len(rows), 5, "Expected at least 5 feature spend rows.")

        # 7. Template Hygiene: Zero Unrendered Jinja Leaks
        html_str = resp.text
        self.assertNotIn("{{ ai_spends", html_str)
        self.assertNotIn("{% for feat in ai_spends", html_str)
        self.assertNotIn("{{ provider_constraints", html_str)
        self.assertNotIn("{% for p in provider_constraints", html_str)

        # 8. Top Header Executive Copilot Button & SVG Hygiene Contract
        copilot_toggle = soup.find("button", onclick="toggleAdminCopilot()")
        self.assertIsNotNone(copilot_toggle, "Missing Executive Copilot toggle button in admin header")
        self.assertIn("btn-sm", copilot_toggle.get("class", []))
        self.assertIn("btn-primary", copilot_toggle.get("class", []))
        svg = copilot_toggle.find("svg")
        self.assertIsNotNone(svg, "Executive Copilot toggle button must contain an SVG icon")
        self.assertEqual(svg.get("class"), ["glyph"], "SVG must have clean ['glyph'] class without backslash escaping")
        self.assertIn("width: 14px", svg.get("style", ""), "SVG must have explicit inline width style without backslash escaping")
        self.assertIn("height: 14px", svg.get("style", ""), "SVG must have explicit inline height style without backslash escaping")
        use = svg.find("use")
        self.assertIsNotNone(use, "SVG must contain a <use> element")
        self.assertEqual(use.get("href"), "#icon-ai-spark", "SVG <use> must reference #icon-ai-spark without backslash escaping")

    def test_admin_audit_mirrors_ai_spends_tab_link(self):
        resp = self.client.get("/admin/audit")
        self.assertEqual(resp.status_code, 200)

        soup = BeautifulSoup(resp.text, "html.parser")
        audit_tab_link = soup.find("a", href="/admin?tab=ai-spends")
        self.assertIsNotNone(audit_tab_link, "Missing link to /admin?tab=ai-spends in admin_audit.html tabs.")


if __name__ == "__main__":
    unittest.main()
