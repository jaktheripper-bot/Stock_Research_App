"""Unit and integration tests for the Autonomous Project Auditor Engine and Tools.

Verifies:
- Deterministic audit tools (test runner, endpoint prober, term scanner, hygiene scanner, design tokens)
- Tri-Pillar score computation & markdown dossier synthesis
- Database persistence & retrieval of project audit logs
- Admin dashboard route and REST API endpoints
"""

import os
import unittest
from fastapi.testclient import TestClient

from web.main import app
from core.audit.tools import (
    tool_scan_prohibited_terms,
    tool_scan_code_hygiene,
    tool_audit_design_tokens,
    tool_probe_web_endpoints
)
from core.audit.project_auditor import (
    compute_deterministic_audit_metrics,
    synthesize_deterministic_markdown_report,
    audit_project_full,
    ProjectAuditResult
)
from core.db.audit_logs import (
    save_project_audit_log,
    get_latest_project_audit_log,
    get_project_audit_history,
    get_project_audit_by_id
)


class TestProjectAuditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        os.environ["AUDIT_RECURSION_GUARD"] = "1"
        cls.client = TestClient(app)

    def test_tool_scan_prohibited_terms(self):
        """Verifies regulatory term scanner identifies compliance status."""
        res = tool_scan_prohibited_terms()
        self.assertIn("scanned_templates", res)
        self.assertIn("violations_count", res)
        self.assertIn("has_statutory_disclaimer", res)
        self.assertTrue(res["has_statutory_disclaimer"], "Statutory non-advisory disclaimer should be present.")
        self.assertEqual(res["violations_count"], 0, "No prohibited prescriptive recommendation words should be present.")

    def test_tool_scan_code_hygiene(self):
        """Verifies code hygiene scanner inspects files and reports findings."""
        res = tool_scan_code_hygiene()
        self.assertIn("scanned_python_files", res)
        self.assertGreater(res["scanned_python_files"], 10)
        self.assertIn("anti_patterns_count", res)
        self.assertIsInstance(res["findings"], list)

    def test_tool_audit_design_tokens(self):
        """Verifies CSS design token & tabular numeral audits."""
        res = tool_audit_design_tokens()
        self.assertIn("has_tabular_nums", res)
        self.assertIn("has_design_tokens", res)
        self.assertTrue(res["has_tabular_nums"], "tabular-nums / tnum styling should be active.")
        self.assertTrue(res["has_design_tokens"], "CSS design tokens should be active.")

    def test_tool_probe_web_endpoints(self):
        """Verifies live endpoint prober checks critical routes."""
        res = tool_probe_web_endpoints()
        self.assertIn("total_checked", res)
        self.assertIn("healthy_count", res)
        self.assertGreater(res["total_checked"], 20)
        self.assertGreaterEqual(res["healthy_count"], 20)

    def test_compute_deterministic_audit_metrics(self):
        """Verifies metric computation across all 3 pillars."""
        metrics = compute_deterministic_audit_metrics()
        self.assertIn("overall_score", metrics)
        self.assertIn("strategy_score", metrics)
        self.assertIn("implementation_score", metrics)
        self.assertIn("uiux_score", metrics)
        self.assertIn("status", metrics)
        self.assertGreaterEqual(metrics["overall_score"], 0.0)
        self.assertLessEqual(metrics["overall_score"], 100.0)

    def test_synthesize_deterministic_markdown_report(self):
        """Verifies markdown report contains executive scorecard and disclaimer."""
        metrics = compute_deterministic_audit_metrics()
        report = synthesize_deterministic_markdown_report("AUD-TEST-001", metrics)
        self.assertIn("Autonomous Project Health Audit Report", report)
        self.assertIn("AUD-TEST-001", report)
        self.assertIn("Pillar 1: Strategy & Regulatory", report)
        self.assertIn("Pillar 2: Technical & Code", report)
        self.assertIn("Pillar 3: UI/UX & Front-End", report)
        self.assertIn("SEBI Safe Harbor", report)

    def test_audit_logs_db_crud(self):
        """Verifies database persistence and retrieval of project audit records."""
        test_audit = {
            "audit_id": "AUD-TEST-UNIT-999",
            "overall_score": 94.5,
            "strategy_score": 100.0,
            "implementation_score": 90.0,
            "uiux_score": 95.0,
            "status": "EXEMPLARY",
            "tests_total": 129,
            "tests_passed": 129,
            "tests_failed": 0,
            "endpoints_checked": 25,
            "endpoints_healthy": 25,
            "critical_violations": [],
            "recommendations": ["Maintain continuous audit cadence."],
            "pillar_breakdown": {"strategy": {}, "implementation": {}, "uiux": {}},
            "full_markdown_report": "# Test Report",
            "audit_engine": "test-runner"
        }
        saved = save_project_audit_log(test_audit)
        self.assertTrue(saved, "Audit log should save successfully to database.")

        record = get_project_audit_by_id("AUD-TEST-UNIT-999")
        self.assertIsNotNone(record)
        self.assertEqual(record["audit_id"], "AUD-TEST-UNIT-999")
        self.assertAlmostEqual(record["overall_score"], 94.5, places=1)

        history = get_project_audit_history(limit=5)
        self.assertIsInstance(history, list)
        self.assertGreaterEqual(len(history), 1)

    def test_web_admin_audit_routes(self):
        """Verifies /admin/audit and audit API endpoints."""
        # 1. Health endpoint alias
        resp_health = self.client.get("/health")
        self.assertEqual(resp_health.status_code, 200)
        self.assertEqual(resp_health.json().get("status"), "healthy")

        # 2. Admin audit page (authenticated via TESTING=1 admin mock or unauthenticated response)
        resp_admin = self.client.get("/admin/audit")
        self.assertIn(resp_admin.status_code, (200, 303))

        # 3. GET /api/admin/audit-logs
        resp_logs = self.client.get("/api/admin/audit-logs")
        self.assertEqual(resp_logs.status_code, 200)
        data = resp_logs.json()
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("logs"), list)

        # 4. POST /api/admin/run-project-audit (Fast deterministic path)
        resp_run = self.client.post("/api/admin/run-project-audit", json={"use_ai": False})
        self.assertEqual(resp_run.status_code, 200)
        res_data = resp_run.json()
        self.assertTrue(res_data.get("success"))
        self.assertIn("audit", res_data)
        self.assertGreater(res_data["audit"]["overall_score"], 0)


if __name__ == "__main__":
    unittest.main()
