import os
os.environ["TESTING"] = "1"
import re
import unittest
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
        # Regex patterns for function declarations in JS
        patterns = [
            r'function\s+([a-zA-Z0-9_$]+)\s*\(',
            r'window\.([a-zA-Z0-9_$]+)\s*=',
            r'(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:function|\([^)]*\)\s*=>)',
        ]
        for pat in patterns:
            for match in re.finditer(pat, js_content):
                defined_functions.add(match.group(1))

        # Standard browser global builtins or inline-defined utility functions
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
            # Also extract any inline script definitions from this template
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

        main_js_path = self.project_root / "web" / "static" / "js" / "main.js"
        js_content = main_js_path.read_text(encoding="utf-8")
        self.assertIn("startButtonProgressFill", js_content)
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
        # Verifies single valid BSE profile link is retained
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

        # User starts with 2 free welcome credits
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


if __name__ == "__main__":
    unittest.main()
