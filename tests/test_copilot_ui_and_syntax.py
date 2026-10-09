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

    def test_all_copilot_starter_prompts_executable_via_api(self):
        """Verifies that starter prompts configured for Equities, MFs, and Debt are accepted by the Copilot API."""
        starter_prompts = [
            ("Run Pre-Mortem Inversion analysis on this stock: what failure modes could destroy shareholder value?", "INFY", "equity"),
            ("What implied growth rate is priced into current CMP based on Reverse DCF?", "INFY", "equity"),
            ("Evaluate the constituent moat distribution and overall portfolio quality for this fund.", "PPFAS_FLEXICAP_DIR", "mutual_fund"),
            ("Stress-test the Asset Coverage Ratio (ACR) and DSCR covenant headroom for this instrument.", "IN0020210012", "debt")
        ]

        for prompt_text, ticker, asset_type in starter_prompts:
            resp = self.client.post("/api/copilot/chat", json={
                "conversation_id": f"TEST-COPILOT-AUDIT-{urllib.parse.quote(ticker)}",
                "message": prompt_text,
                "ticker": ticker,
                "asset_type": asset_type
            })
            self.assertEqual(resp.status_code, 200, f"Copilot chat failed for prompt: {prompt_text}")
            data = resp.json()
            self.assertIn("response", data)
            self.assertTrue(len(data["response"]) > 20, "Response should contain diagnostic insights")


if __name__ == "__main__":
    unittest.main()
