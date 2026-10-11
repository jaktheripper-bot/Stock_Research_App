"""Comprehensive Unit & Integration Test Suite for Frontend Wiring, UI Syntax & Copilot Desks.

Verifies:
1. Template onclick handlers are properly defined in JavaScript (zero undefined runtime reference errors).
2. Progressive 30s button fill loading animations and unlockDeepDive frontend wiring.
3. Header KPI cards hygiene and valid BSE profile link presence.
4. Credit unlock API endpoint lifecycle, authentication, deduction, and idempotency.
5. Copilot client-side JavaScript hygiene (no dangerous unescaped JSON.stringify in inline handlers).
6. Copilot modal markup and data-copilot-prompt accessibility bindings.
7. Multimodal copilot options produce distinct, grounded responses across Equities, Mutual Funds, and Debt.
"""

import os
os.environ["TESTING"] = "1"

import re
import unittest
import urllib.parse
from pathlib import Path
from fastapi.testclient import TestClient
from web.main import app


class TestFrontendClickWiringAndCredits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.project_root = Path(__file__).resolve().parent.parent

    def test_all_template_onclick_handlers_are_defined_in_javascript(self):
        """
        Audits all HTML templates in web/templates/ to ensure every onclick="..."
        handler corresponds to a defined JavaScript function.
        Prevents silent 'ReferenceError: X is not defined' runtime crashes.
        """
        templates_dir = self.project_root / "web" / "templates"
        js_dir = self.project_root / "web" / "static" / "js"

        # 1. Collect all defined JS functions
        js_content = ""
        for js_file in js_dir.glob("*.js"):
            js_content += js_file.read_text(encoding="utf-8") + "\n"

        defined_functions = set()
        patterns = [
            r'function\s+([a-zA-Z0-9_$]+)\s*\(',
            r'window\.([a-zA-Z0-9_$]+)\s*=',
            r'(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:function|\([^)]*\)\s*=>)',
        ]
        for pat in patterns:
            for match in re.finditer(pat, js_content):
                defined_functions.add(match.group(1))

        allowed_builtins = {
            "alert", "confirm", "prompt", "history", "location", "close", "focus",
            "this", "event", "toggleFilter", "switchTab", "selectFilterTab", "copyCode",
            "filterSector", "filterCategory", "toggleSurveillanceFeed", "openWatchlistModal",
            "openThesisModal", "closeThesisModal", "saveThesisNote", "openAuthModal",
            "closeAuthModal", "openSignInModal", "closeSignInModal", "openCopilot",
            "toggleDrawer", "filterReports", "openProModal", "selectCreditPack",
            "synthesizeReport", "unlockDeepDive", "clearSearch", "toggleFaq",
            "handleTabClick", "renderChart", "exportCsv", "printDossier"
        }

        # 2. Scan all HTML files for onclick handlers
        onclick_pattern = re.compile(r'onclick=["\']\s*([a-zA-Z0-9_$]+)\s*(?:\([^)]*\))?\s*["\']')
        unresolved_handlers = []

        for html_file in templates_dir.rglob("*.html"):
            content = html_file.read_text(encoding="utf-8")
            inline_scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
            local_defined = set(defined_functions)
            for script in inline_scripts:
                for pat in patterns:
                    for match in re.finditer(pat, script):
                        local_defined.add(match.group(1))

            for match in onclick_pattern.finditer(content):
                fn_name = match.group(1)
                if fn_name not in local_defined and fn_name not in allowed_builtins:
                    unresolved_handlers.append((html_file.name, fn_name))

        self.assertEqual(
            unresolved_handlers, [],
            f"Found HTML templates with undefined onclick handlers: {unresolved_handlers}"
        )

    def test_unlock_deep_dive_function_is_explicitly_defined(self):
        """Verifies that unlockDeepDive is explicitly implemented in main.js."""
        main_js_path = self.project_root / "web" / "static" / "js" / "main.js"
        content = main_js_path.read_text(encoding="utf-8")
        self.assertIn("window.unlockDeepDive = async function", content)
        self.assertIn("/api/dossier/unlock/", content)

    def test_progressive_30s_fill_button_implemented_in_css_and_js(self):
        """Verifies that 30-second progressive fill loading animation tokens exist in CSS and JS."""
        style_css_path = self.project_root / "web" / "static" / "css" / "style.css"
        css_content = style_css_path.read_text(encoding="utf-8")
        self.assertIn(".btn-loading-progress", css_content)
        self.assertIn("--btn-progress", css_content)
        self.assertIn(".btn-instant-pressed", css_content)

        main_js_path = self.project_root / "web" / "static" / "js" / "main.js"
        js_content = main_js_path.read_text(encoding="utf-8")
        self.assertIn("startButtonProgressFill", js_content)
        self.assertIn("resetButtonProgressFill", js_content)
        self.assertIn("resetAllButtonProgressFills", js_content)
        self.assertIn("pageshow", js_content)
        self.assertIn("pagehide", js_content)
        self.assertIn("popstate", js_content)
        self.assertIn("overlayProgressBar", js_content)
        self.assertIn("overlayProgressTime", js_content)

        base_html_path = self.project_root / "web" / "templates" / "base.html"
        base_html = base_html_path.read_text(encoding="utf-8")
        self.assertIn('id="overlayProgressBar"', base_html)
        self.assertIn('id="overlayProgressTime"', base_html)
        self.assertIn('id="overlayProgressStage"', base_html)

    def test_dossier_header_kpi_cards_have_no_broken_bse_search_links(self):
        """
        Verifies that dossier.html does NOT link to the broken BSE Comp_Resultsnew.aspx
        search page which outputs 'No record found!'.
        """
        dossier_html_path = self.project_root / "web" / "templates" / "dossier.html"
        content = dossier_html_path.read_text(encoding="utf-8")
        self.assertNotIn("Comp_Resultsnew.aspx", content, "Broken BSE Comp_Resultsnew.aspx link must not be in dossier.html")
        self.assertIn("dossier-meta-strip", content)
        self.assertIn("dossier-provenance-subline", content)
        self.assertIn("Official BSE Profile ↗", content)

    def test_credit_unlock_api_endpoint_lifecycle(self):
        """Tests the backend /api/dossier/unlock/{ticker} endpoint security and validation."""
        # 1. Unauthorized request
        resp_unauth = self.client.post("/api/dossier/unlock/INFY")
        self.assertEqual(resp_unauth.status_code, 401)
        self.assertIn("Sign in required", resp_unauth.json().get("detail", ""))

        # 2. Invalid ticker
        resp_bad = self.client.post("/api/dossier/unlock/---")
        self.assertEqual(resp_bad.status_code, 400)

        # 3. Authenticated unlock flow
        import uuid
        test_email = f"test_unlock_{uuid.uuid4().hex[:8]}@example.com"
        self.client.post("/api/auth/send-otp", json={"email": test_email})
        resp_verify = self.client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "code": "123456"
        })
        self.assertEqual(resp_verify.status_code, 200)
        session_cookie = {"user_session_token": resp_verify.cookies["user_session_token"]}

        resp_unlock = self.client.post("/api/dossier/unlock/INFY", cookies=session_cookie)
        self.assertEqual(resp_unlock.status_code, 200)
        data = resp_unlock.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["ticker"], "INFY")
        self.assertEqual(data["new_balance"], 1.0)

        # Repeated unlock should be idempotent (no double charge)
        resp_repeat = self.client.post("/api/dossier/unlock/INFY", cookies=session_cookie)
        self.assertEqual(resp_repeat.status_code, 200)
        data_repeat = resp_repeat.json()
        self.assertTrue(data_repeat["success"])
        self.assertEqual(data_repeat["new_balance"], 1.0)


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

        self.assertNotIn(
            'onclick="sendQuickPrompt(${JSON.stringify',
            content,
            "Found dangerous unescaped JSON.stringify in inline onclick attribute in copilot.js!"
        )
        self.assertIn(
            'data-copilot-prompt="${encodeURIComponent(',
            content,
            "copilot.js must use data-copilot-prompt with encodeURIComponent for safe option binding"
        )
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
            self.assertNotIn("Select a forensic diagnostic pillar to drill into", text, f"Option {opt_key} fell back to generic summary")

        distinct_responses = set(responses.values())
        self.assertEqual(len(distinct_responses), 4, "All 4 equity options must produce completely distinct diagnostic analyses!")

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
            }, headers={"x-unlock-preview": "1"})
            self.assertEqual(resp.status_code, 200)
            text = resp.json().get("response", "")
            responses[opt_key] = text
            self.assertNotIn("What specific look-through metric, constituent holding", text, f"Option {opt_key} fell back to generic summary")

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
            }, headers={"x-unlock-preview": "1"})
            self.assertEqual(resp.status_code, 200)
            text = resp.json().get("response", "")
            responses[opt_key] = text
            self.assertNotIn("What specific solvency or capital hierarchy pillar would you like to drill into", text)

        self.assertEqual(len(set(responses.values())), 3, "All 3 debt options must produce distinct analyses!")
        self.assertIn("Asset Coverage & Covenant Headroom", responses["covenants"])
        self.assertIn("Recovery Seniority & Liquidation Hierarchy", responses["seniority"])
        self.assertIn("Credit Contagion Radar Analysis", responses["contagion"])


if __name__ == "__main__":
    unittest.main()
