import unittest
import urllib.parse
from pathlib import Path
from fastapi.testclient import TestClient
from web.main import app


class TestCopilotUIAndSyntax(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.project_root = Path(__file__).resolve().parent.parent

    def test_copilot_js_no_broken_inline_quote_handlers(self):
        """Audits copilot.js to ensure no inline onclick string interpolations break HTML attribute parsing."""
        copilot_js_path = self.project_root / "web" / "static" / "js" / "copilot.js"
        self.assertTrue(copilot_js_path.exists(), "copilot.js must exist")
        content = copilot_js_path.read_text(encoding="utf-8")

        # 1. Anti-pattern: onclick="sendQuickPrompt(${JSON.stringify(...)})"
        self.assertNotIn(
            'onclick="sendQuickPrompt(${JSON.stringify',
            content,
            "Found dangerous unescaped JSON.stringify in inline onclick attribute in copilot.js!"
        )

        # 2. Verify data attribute usage for options
        self.assertIn(
            'data-copilot-prompt="${encodeURIComponent(',
            content,
            "copilot.js must use data-copilot-prompt with encodeURIComponent for safe option binding"
        )

        # 3. Verify delegated click listener exists
        self.assertIn(
            'document.addEventListener("click"',
            content,
            "copilot.js must include delegated event listener for [data-copilot-prompt]"
        )
        self.assertIn(
            'closest("[data-copilot-prompt]")',
            content,
            "copilot.js delegated listener must resolve closest [data-copilot-prompt]"
        )
        self.assertIn(
            'sendQuickPrompt(decodeURIComponent(rawPrompt))',
            content,
            "copilot.js delegated listener must decode prompt and trigger sendQuickPrompt"
        )

    def test_copilot_modal_html_has_interactive_options(self):
        """Audits copilot_modal.html to verify markup has accessible, clickable option elements."""
        modal_path = self.project_root / "web" / "templates" / "partials" / "copilot_modal.html"
        self.assertTrue(modal_path.exists(), "copilot_modal.html must exist")
        content = modal_path.read_text(encoding="utf-8")

        # Must contain data-copilot-prompt attributes
        self.assertIn("data-copilot-prompt", content)
        self.assertIn("copilot-intro-feature-item", content)
        self.assertIn("copilot-chip-btn", content)

    def test_equity_options_yield_distinct_responses(self):
        """Verifies that each option within the Forensic Intelligence Desk for Equities returns a unique, data-grounded response."""
        equity_prompts = [
            ("pre_mortem", "Run Pre-Mortem Inversion analysis on this stock: what failure modes could destroy shareholder value?"),
            ("reverse_dcf", "What implied growth rate is priced into current CMP based on Reverse DCF?"),
            ("governance", "Are there any promoter pledging or corporate governance red flags in recent disclosures?"),
            ("solvency", "Evaluate balance sheet solvency, Altman Z-Score, and leverage ratios for this company.")
        ]

        responses = {}
        for opt_key, prompt_text in equity_prompts:
            resp = self.client.post("/api/copilot/chat", json={
                "conversation_id": f"TEST-COPILOT-EQUITY-{opt_key}",
                "message": prompt_text,
                "ticker": "INFY",
                "asset_type": "equity"
            })
            self.assertEqual(resp.status_code, 200)
            text = resp.json().get("response", "")
            responses[opt_key] = text
            # Ensure it is not the default multi-pillar overview
            self.assertNotIn("Select a forensic diagnostic pillar to drill into", text, f"Option {opt_key} fell back to generic summary")

        # Verify all 4 responses are mutually distinct
        distinct_responses = set(responses.values())
        self.assertEqual(len(distinct_responses), 4, "All 4 equity options must produce completely distinct diagnostic analyses!")

        # Verify individual thematic grounding
        self.assertIn("Pre-Mortem Inversion Analysis", responses["pre_mortem"])
        self.assertIn("Charlie Munger", responses["pre_mortem"])
        self.assertIn("Reverse DCF Valuation & Implied Growth Deconstruction", responses["reverse_dcf"])
        self.assertIn("Current Market Price (CMP)", responses["reverse_dcf"])
        self.assertIn("Implied FCF Growth Priced In", responses["reverse_dcf"])
        self.assertIn("Benchmark Hurdle Rate", responses["reverse_dcf"])
        self.assertIn("Forensic Accounting & Governance Audit", responses["governance"])
        self.assertIn("0.0% Pledged", responses["governance"])
        self.assertIn("Balance Sheet Solvency & Liquidity Diagnostic", responses["solvency"])
        self.assertIn("Altman Z-Score Solvency Zone", responses["solvency"])

    def test_mutual_fund_options_yield_distinct_responses(self):
        """Verifies that each option within the Fund Look-Through Intelligence Desk returns a unique response."""
        mf_prompts = [
            ("moat", "Evaluate the constituent moat distribution and overall portfolio quality for this fund."),
            ("asri", "Which underlying constituent holdings carry the highest accounting risk or lowest health score?"),
            ("active_share", "Audit the active share and check if this fund is exhibiting benchmark hugging or style drift."),
            ("fee_drag", "What is the 20-year compounded fee drag and wealth lost to distributor commissions for this fund?")
        ]

        responses = {}
        for opt_key, prompt_text in mf_prompts:
            resp = self.client.post("/api/copilot/chat", json={
                "conversation_id": f"TEST-COPILOT-MF-{opt_key}",
                "message": prompt_text,
                "ticker": "PPFAS_FLEXICAP_DIR",
                "asset_type": "mutual_fund"
            })
            self.assertEqual(resp.status_code, 200)
            text = resp.json().get("response", "")
            responses[opt_key] = text
            self.assertNotIn("What specific look-through metric, constituent holding", text, f"Option {opt_key} fell back to generic summary")

        # Verify distinct responses
        self.assertEqual(len(set(responses.values())), 4, "All 4 mutual fund options must produce distinct analyses!")
        self.assertIn("Weighted Moat & Quality Diagnostic", responses["moat"])
        self.assertIn("Look-Through Accounting Risk (ASRI) Diagnostic", responses["asri"])
        self.assertIn("Active Share & Closet Indexing Diagnostic", responses["active_share"])
        self.assertIn("Intermediary Fee Drag & Wealth Destruction Audit", responses["fee_drag"])

    def test_debt_options_yield_distinct_responses(self):
        """Verifies that each option within the Credit & Solvency Intelligence Desk returns a unique response."""
        debt_prompts = [
            ("covenants", "Stress-test the Asset Coverage Ratio (ACR) and DSCR covenant headroom for this instrument."),
            ("seniority", "Evaluate recovery seniority and investor recourse in a stressed debt restructuring or liquidation."),
            ("contagion", "What does the Credit Contagion Radar say about the parent group and systemic risks for this issuer?")
        ]

        responses = {}
        for opt_key, prompt_text in debt_prompts:
            resp = self.client.post("/api/copilot/chat", json={
                "conversation_id": f"TEST-COPILOT-DEBT-{opt_key}",
                "message": prompt_text,
                "ticker": "IN0020210012",
                "asset_type": "debt"
            })
            self.assertEqual(resp.status_code, 200)
            text = resp.json().get("response", "")
            responses[opt_key] = text
            self.assertNotIn("What specific solvency or capital hierarchy pillar would you like to drill into", text)

        # Verify distinct responses
        self.assertEqual(len(set(responses.values())), 3, "All 3 debt options must produce distinct analyses!")
        self.assertIn("Asset Coverage & Covenant Headroom", responses["covenants"])
        self.assertIn("Recovery Seniority & Liquidation Hierarchy", responses["seniority"])
        self.assertIn("Credit Contagion Radar Analysis", responses["contagion"])


if __name__ == "__main__":
    unittest.main()

