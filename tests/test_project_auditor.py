"""Comprehensive Unit and Integration Test Suite for Project, Multi-Agent & AI Auditors.

Verifies:
1. Deterministic project audit tools (test runner, endpoint prober, term scanner, hygiene scanner, design tokens)
2. Tri-Pillar score computation & markdown dossier synthesis
3. Database persistence & retrieval of project audit logs
4. Admin dashboard route and REST API endpoints (/admin/audit, /api/admin/audit-logs, /api/admin/run-project-audit)
5. Google Antigravity Multi-Agent Forensic Audit Module & fallback signals
6. Hybrid Sandboxed AI Auditor, BudgetGuard ceilings, personas & failure synthesizer
"""

import os
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["TESTING"] = "1"
os.environ["ENVIRONMENT"] = "testing"
os.environ["AUDIT_RECURSION_GUARD"] = "1"

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
from core.analysis.multi_agent_audit import (
    tool_get_fundamentals,
    tool_get_bse_disclosures,
    tool_compute_forensic_signals,
    run_deterministic_forensic_fallback,
    ForensicAuditResult,
    ANTIGRAVITY_AVAILABLE
)
from scripts.ai_auditor import (
    BudgetGuard,
    BudgetExceededError,
    SiteZone,
    AnomalyReport,
    FailureSynthesizer,
    RegulatoryBaiter,
    EdgeCaseQuant,
    StateSaboteur,
)

MOCK_FUNDAMENTALS = {
    "current_price": 1520.0,
    "market_cap": 620000.0,
    "pe_ratio": 24.5,
    "price_to_book": 7.2,
    "debt_to_equity": 0.08,
    "return_on_equity": 28.5,
    "piotroski_f_score": 8,
    "altman_z_score": 6.5,
    "promoter_pledge_pct": 0.0,
    "promoter_holding_pct": 14.8
}


class TestProjectAuditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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


class TestMultiAgentForensicAudit(unittest.TestCase):
    def test_antigravity_sdk_installation(self):
        """Verifies that the google-antigravity package presence is cleanly detected."""
        self.assertIn(ANTIGRAVITY_AVAILABLE, [True, False])

    @patch("core.analysis.multi_agent_audit.get_stock_fundamentals", return_value=MOCK_FUNDAMENTALS)
    def test_deterministic_forensic_fallback(self, mock_fund):
        """Verifies fallback audit output produces required schema and metrics."""
        res = run_deterministic_forensic_fallback("INFY")
        self.assertIsInstance(res, ForensicAuditResult)
        self.assertEqual(res.ticker, "INFY")
        self.assertGreaterEqual(res.forensic_score, 0.0)
        self.assertLessEqual(res.forensic_score, 100.0)
        self.assertIn("accounting_forensics", res.to_dict())
        self.assertIn("governance_scrutiny", res.to_dict())
        self.assertIn("valuation_stress", res.to_dict())
        self.assertIn("Section 2(u)", res.sebi_safe_harbor)

    @patch("core.analysis.multi_agent_audit.get_stock_fundamentals", return_value=MOCK_FUNDAMENTALS)
    def test_forensic_tools(self, mock_fund):
        """Verifies individual deterministic forensic tools execute properly."""
        tools_fund = tool_get_fundamentals("INFY")
        self.assertIn("ticker", tools_fund)

        disclosures = tool_get_bse_disclosures("INFY")
        self.assertIn("ticker", disclosures)

        signals = tool_compute_forensic_signals("INFY")
        self.assertIn("solvency_posture", signals)


class TestAiAuditorEngine(unittest.TestCase):
    """Test suite for AI Auditor and failure synthesizer mechanics."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_budget_guard_accumulation_and_limits(self):
        """Verifies that BudgetGuard accurately tracks tokens and raises when ceiling is exceeded."""
        guard = BudgetGuard(max_tokens=1000, max_cost_usd=0.10)
        self.assertEqual(guard.tokens_used, 0)
        self.assertEqual(guard.cost_used, 0.0)

        # Record normal usage
        guard.record_usage(prompt_tokens=400, candidate_tokens=100)
        self.assertEqual(guard.tokens_used, 500)
        self.assertGreater(guard.cost_used, 0.0)
        self.assertTrue(guard.can_spend(estimated_tokens=400))

        # Exceed token ceiling
        with self.assertRaises(BudgetExceededError):
            guard.record_usage(prompt_tokens=400, candidate_tokens=200)

    def test_site_zones_coverage(self):
        """Verifies that all 5 site zones are defined and distinct."""
        zones = [
            SiteZone.ZONE_1_EQUITY,
            SiteZone.ZONE_2_MULTI_ASSET,
            SiteZone.ZONE_3_CALCULATORS,
            SiteZone.ZONE_4_FORENSIC_DESK,
            SiteZone.ZONE_5_ADMIN_SECURITY,
        ]
        self.assertEqual(len(set(zones)), 5)
        for z in zones:
            self.assertTrue(z.startswith("Zone "))

    def test_regulatory_baiter_execution(self):
        """Verifies that Regulatory Baiter audits /api/copilot/chat and /contact cleanly."""
        baiter = RegulatoryBaiter(self.client)
        anomalies = baiter.run_probes()
        self.assertEqual(len(anomalies), 0, f"Unexpected regulatory anomalies detected: {anomalies}")

    def test_edge_case_quant_execution(self):
        """Verifies that Edge-Case Quant runs boundary queries without unhandled 500s."""
        quant = EdgeCaseQuant(self.client)
        anomalies = quant.run_probes()
        self.assertEqual(len(anomalies), 0, f"Unexpected quant anomalies detected: {anomalies}")

    def test_state_saboteur_execution(self):
        """Verifies that State Saboteur confirms authentication and payload boundaries."""
        saboteur = StateSaboteur(self.client)
        anomalies = saboteur.run_probes()
        self.assertEqual(len(anomalies), 0, f"Unexpected security anomalies detected: {anomalies}")

    def test_failure_synthesizer_generates_valid_artifacts(self):
        """Verifies that FailureSynthesizer writes executable unit tests and markdown dossiers."""
        guard = BudgetGuard(max_tokens=10000, max_cost_usd=0.50)
        synthesizer = FailureSynthesizer(guard)

        mock_anomaly = AnomalyReport(
            anomaly_id="ANOM-TEST-UNIT-01",
            zone=SiteZone.ZONE_3_CALCULATORS,
            endpoint="/calculator/tax",
            method="GET",
            persona="Edge-Case Quant",
            probe_description="Test anomaly for synthesizer verification",
            payload={"holding_years": -99},
            status_code=500,
            error_message="Test synthetic 500 failure",
            response_snippet="Traceback: line 1 in tax_test",
            threat_level="HIGH",
            timestamp="2026-10-10T18:00:00Z",
        )

        res = synthesizer.synthesize(mock_anomaly)
        test_file = Path(res["test_file"])
        report_file = Path(res["report_file"])

        try:
            self.assertTrue(test_file.exists(), "Synthesized test file was not created on disk")
            self.assertTrue(report_file.exists(), "Synthesized report file was not created on disk")

            # Check test file content
            with open(test_file, "r", encoding="utf-8") as f:
                code = f.read()
                self.assertTrue("class Test" in code, "Synthesized code must define a test case class")
                self.assertIn("assertNotEqual", code)

            # Check report file content
            with open(report_file, "r", encoding="utf-8") as f:
                report = f.read()
                self.assertIn("AI Auditor Threat Dossier", report)
                self.assertIn("ANOM-TEST-UNIT-01", report)
        finally:
            # Clean up test artifacts
            if test_file.exists():
                test_file.unlink()
            if report_file.exists():
                report_file.unlink()


if __name__ == "__main__":
    unittest.main()
