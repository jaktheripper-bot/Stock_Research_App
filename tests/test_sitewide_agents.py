"""Comprehensive unit and integration test suite for Sitewide Google Antigravity Agents.

Verifies:
- Shared agent configurations, declarative policies, and budget limits
- Database dual-binding for agent conversations, turns, and event ledgers
- Domain research squads (Equities, Funds, Debt, REITs, Macro)
- Non-advisory regulatory compliance deflection
- Interactive Copilot API endpoints
"""

import os
import uuid
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from web.main import app
from core.agents.config import (
    ANTIGRAVITY_AVAILABLE,
    get_default_agent_policies,
    get_tier_budget_config,
    SEBI_SAFE_HARBOR_DIRECTIVE
)
from core.db.agent_sessions import (
    create_or_get_agent_conversation,
    append_conversation_turn,
    get_conversation_turns,
    record_autonomous_event,
    get_recent_autonomous_events
)
from core.agents.equity.forensic_squad import run_deterministic_equity_audit
from core.agents.funds.lookthrough_squad import audit_fund_lookthrough
from core.agents.debt.credit_squad import audit_credit_offering
from core.agents.reits.real_assets_squad import audit_real_asset, scan_sgb_parity_discounts
from core.agents.macro.macro_squad import audit_macro_yield_environment
from core.agents.copilot.investor_copilot import (
    check_non_advisory_compliance,
    process_copilot_turn
)


class TestSitewideAgents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        os.environ["AUDIT_RECURSION_GUARD"] = "1"
        cls.client = TestClient(app)

    def test_agent_policies_and_budgets(self):
        """Verifies policy lists and operational tier budget limits."""
        policies = get_default_agent_policies()
        self.assertIsInstance(policies, list)

        budget_domain = get_tier_budget_config("domain_research")
        if ANTIGRAVITY_AVAILABLE:
            self.assertIsNotNone(budget_domain)
            self.assertEqual(budget_domain.max_model_calls, 15)
            budget_copilot = get_tier_budget_config("interactive_copilot")
            self.assertIsNotNone(budget_copilot)
            self.assertEqual(budget_copilot.max_model_calls, 8)
        else:
            self.assertIsNone(budget_domain)

    def test_agent_sessions_and_turns_crud(self):
        """Verifies persistence of agent conversations and dialogue turns."""
        conv_id = f"TEST-CONV-{uuid.uuid4().hex[:8]}"
        conv = create_or_get_agent_conversation(
            conversation_id=conv_id,
            user_id="usr_test_allocator",
            agent_type="equity_copilot",
            context_ticker="INFY"
        )
        self.assertEqual(conv.get("conversation_id"), conv_id)
        self.assertEqual(conv.get("context_ticker"), "INFY")

        appended = append_conversation_turn(conv_id, "user", "What is the margin of safety?")
        self.assertTrue(appended)
        appended_agent = append_conversation_turn(conv_id, "agent", "Estimated margin of safety is 38.5%.")
        self.assertTrue(appended_agent)

        turns = get_conversation_turns(conv_id)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["sender_role"], "user")
        self.assertEqual(turns[1]["sender_role"], "agent")

    def test_autonomous_event_ledger(self):
        """Verifies recording and querying of autonomous event ledger."""
        evt_id = record_autonomous_event(
            event_type="test_bse_filing",
            ticker="TCS",
            trigger_source="unit_test",
            action_taken="dispatched_audit",
            summary="Test autonomous event recording"
        )
        self.assertTrue(evt_id.startswith("EVT-"))

        events = get_recent_autonomous_events(limit=5, event_type="test_bse_filing", include_test_events=True)
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0]["ticker"], "TCS")

        # Clean up test event so DB remains unpolluted
        from core.db.connection import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM autonomous_event_ledger WHERE event_id = ?", (evt_id,))
            conn.commit()
        except Exception:
            pass
        finally:
            cur.close()
            conn.close()

    @patch("core.agents.tools_base.fetch_latest_bse_announcement", return_value="Board approved interim dividend and audited accounts.")
    def test_equity_forensic_squad(self, mock_bse):
        """Verifies equity squad deterministic output and non-advisory compliance."""
        audit = run_deterministic_equity_audit("INFY")
        self.assertEqual(audit["ticker"], "INFY")
        self.assertIn("composite_forensic_score", audit)
        self.assertIn("accounting_forensics", audit)
        self.assertIn("governance_scrutiny", audit)
        self.assertIn("valuation_stress", audit)
        self.assertIn("2(u)", audit["sebi_safe_harbor"])

    def test_fund_lookthrough_squad(self):
        """Verifies mutual fund look-through squad."""
        res = audit_fund_lookthrough("PPFAS_FLEXICAP_DIR")
        self.assertEqual(res["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertIn("has_sufficient_coverage", res)
        self.assertIn("weighted_moat_score", res)
        if res.get("has_sufficient_coverage"):
            self.assertGreater(res["composite_health_score"], 0.0)
        else:
            self.assertIsNone(res["composite_health_score"])

    def test_credit_and_real_assets_squads(self):
        """Verifies credit, REIT, and macro squads."""
        debt_res = audit_credit_offering("INE002A08012")
        self.assertIn("credit_score", debt_res)

        reit_res = audit_real_asset("EMBASSY")
        self.assertIn("compliance_score", reit_res)

        sgb_res = scan_sgb_parity_discounts()
        self.assertIn("total_tranches_scanned", sgb_res)

        macro_res = audit_macro_yield_environment()
        self.assertIn("benchmark_10y_gsec", macro_res)

    def test_non_advisory_compliance_filter(self):
        """Verifies regulatory deflection of retail buy/sell inquiries."""
        deflected = check_non_advisory_compliance("Should I buy INFY today?")
        self.assertIsNotNone(deflected)
        self.assertIn("SEBI Regulatory Non-Advisory Notice", deflected)
        self.assertIn("Section 2(u)", deflected)

        clean = check_non_advisory_compliance("Explain the ROCE trend over 3 years")
        self.assertIsNone(clean)

    def test_copilot_turn_and_api(self):
        """Verifies Copilot chat processing and REST endpoints."""
        conv_id = f"TEST-API-COPILOT-{uuid.uuid4().hex[:8]}"
        # 1. Deflection turn via API
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": conv_id,
            "message": "Is this stock a strong buy?",
            "ticker": "INFY"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("status"), "REGULATORY_DEFLECTED")
        self.assertIn("Section 2(u)", data.get("response"))

        # 2. History endpoint
        resp_hist = self.client.get(f"/api/copilot/history?conversation_id={conv_id}")
        self.assertEqual(resp_hist.status_code, 200)
        hist_data = resp_hist.json()
        self.assertTrue(hist_data.get("success"))
        self.assertGreaterEqual(len(hist_data.get("turns")), 2)

        # 3. Mutual Fund section-aware turn via API
        conv_mf_id = f"TEST-API-COPILOT-MF-{uuid.uuid4().hex[:8]}"
        resp_mf = self.client.post("/api/copilot/chat", json={
            "conversation_id": conv_mf_id,
            "message": "Explain the distributor commission fee drag.",
            "ticker": "PPFAS_FLEXICAP_DIR",
            "asset_type": "mutual_fund",
            "section": "fee_drag",
            "section_label": "Intermediary Fee Drag"
        })
        self.assertEqual(resp_mf.status_code, 200)
        data_mf = resp_mf.json()
        self.assertTrue(data_mf.get("success"))
        self.assertIn("Fee Drag", data_mf.get("response"))
        self.assertNotIn("company's Margin of Safety", data_mf.get("response"))


if __name__ == "__main__":
    unittest.main()
