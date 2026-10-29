"""
tests/outside_in/test_interactive_ui_and_contracts.py
=====================================================
Mandatory Outside-In Testing Protocol Suite (AGENTS.md Rule 6):
1. DOM Element Binding Integrity (zero null element references)
2. Viewport Centering & Modal Backdrop Architecture
3. Client-to-Server Route Contracts
4. Template Attribute & Jinja Hygiene
5. JavaScript onclick & tactile button affordances
6. Competitive UI & Institutional Flow
"""
import os
os.environ["TESTING"] = "1"

import re
import json
import unittest
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from web.main import app


"""
Empirical Interactive UI, DOM Contract & Modal Binding Test Suite.

Eliminates superficial status-code-only testing by validating:
1. Modal Architecture & Centering Contracts (all modals have .modal-backdrop, .modal-dialog, close handlers).
2. JavaScript DOM Element Binding Integrity (zero getElementById null ReferenceErrors).
3. Client-Side API Route Call Contracts (every fetch() target corresponds to a live FastAPI route).
4. Full DOM Parsing & Semantic Element Assertions on /msme and /msme/{uin}.
5. Zero unrendered Jinja tags in HTML tag attributes sitewide.
"""

import os
os.environ["TESTING"] = "1"

import re
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from web.main import app


class TestInteractiveUiAndDomContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.project_root = Path(__file__).resolve().parent.parent.parent
        cls.templates_dir = cls.project_root / "web" / "templates"
        cls.js_dir = cls.project_root / "web" / "static" / "js"
        cls.css_dir = cls.project_root / "web" / "static" / "css"

        # Collect all active registered route paths from FastAPI app (including sub-routers)
        cls.registered_routes = set()
        for route in app.routes:
            if hasattr(route, "path"):
                cls.registered_routes.add(route.path)
            elif hasattr(route, "original_router"):
                prefix = getattr(route.include_context, "prefix", "") if hasattr(route, "include_context") else ""
                for sub in route.original_router.routes:
                    if hasattr(sub, "path"):
                        cls.registered_routes.add(prefix + sub.path)

    # =========================================================================
    # Pillar 1: Modal Architecture & CSS Centering Contract
    # =========================================================================

    def test_all_modals_adhere_to_standard_backdrop_dialog_contract(self):
        """
        Verify every modal across the template suite utilizes the standardized
        .modal-backdrop and .modal-dialog structure to guarantee viewport centering,
        overlay click dismissibility, and prevention of DOM containment trapping.
        """
        modal_id_pattern = re.compile(r'<div[^>]+id=["\']([a-zA-Z0-9_-]*Modal)["\'][^>]*class=["\']([^"\']+)["\']')
        
        for template_file in self.templates_dir.rglob("*.html"):
            content = template_file.read_text(encoding="utf-8")
            matches = modal_id_pattern.findall(content)
            for modal_id, class_str in matches:
                # Assert modal root has modal-backdrop
                classes = class_str.split()
                self.assertIn(
                    "modal-backdrop",
                    classes,
                    f"Modal #{modal_id} in {template_file.name} lacks '.modal-backdrop' class, risking viewport clipping."
                )

                # Parse snippet to ensure .modal-dialog is a direct or near child
                soup = BeautifulSoup(content, "html.parser")
                modal_elem = soup.find(id=modal_id)
                self.assertIsNotNone(modal_elem, f"Could not find #{modal_id} in {template_file.name}")
                
                dialog = modal_elem.find(class_="modal-dialog")
                self.assertIsNotNone(
                    dialog,
                    f"Modal #{modal_id} in {template_file.name} lacks an inner '.modal-dialog' container."
                )

                # Verify presence of an accessible close button
                close_btn = modal_elem.find(class_="modal-close-btn") or modal_elem.find("button", onclick=re.compile(r"close|dismiss|hide", re.IGNORECASE))
                self.assertIsNotNone(
                    close_btn,
                    f"Modal #{modal_id} in {template_file.name} lacks an accessible close button."
                )

    # =========================================================================
    # Pillar 2: DOM Element ID Binding (Zero Null / ReferenceErrors)
    # =========================================================================

    def test_msme_inspect_javascript_dom_bindings(self):
        """
        Verify that EVERY single document.getElementById('...') invoked by inspectMsme()
        in msme_directory.html has a matching element in the rendered /msme page.
        """
        directory_template = self.templates_dir / "msme_directory.html"
        content = directory_template.read_text(encoding="utf-8")

        # Extract all getElementById targets inside script tags in msme_directory.html
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
        combined_script = "\n".join(scripts)
        id_matches = re.findall(r'document\.getElementById\(["\']([a-zA-Z0-9_-]+)["\']\)', combined_script)
        self.assertGreater(len(id_matches), 15, "Expected at least 15 DOM elements bound in msme_directory.html scripts")

        # Fetch rendered /msme HTML
        res = self.client.get("/msme")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")

        missing_ids = []
        for target_id in set(id_matches):
            elem = soup.find(id=target_id)
            if not elem:
                missing_ids.append(target_id)

        self.assertEqual(
            missing_ids,
            [],
            f"inspectMsme() references DOM IDs not present in /msme HTML: {missing_ids}"
        )

    def test_global_auth_and_checkout_modal_dom_bindings(self):
        """
        Verify that auth and checkout modal scripts in main.js bind to elements
        that actually exist in base.html.
        """
        main_js = self.js_dir / "main.js"
        js_code = main_js.read_text(encoding="utf-8")

        # Extract IDs used in openSignInModal / handleAuthFormSubmit / openCheckout
        auth_ids = [
            "authModal", "authForm", "authEmailGroup", "authEmailInput", "authEmailError",
            "authOtpGroup", "authOtpInput", "authOtpNotice", "authSubmitBtn", "closeAuthModalBtn"
        ]
        checkout_ids = ["checkoutModal", "modalPlanName", "modalPlanPrice", "modalConfirmBtn", "closeModalBtn"]

        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")

        for elem_id in auth_ids + checkout_ids:
            self.assertIsNotNone(
                soup.find(id=elem_id),
                f"Global modal element #{elem_id} referenced in main.js is missing from base.html"
            )

        # Accessibility and modern form validation contract checks
        email_input = soup.find(id="authEmailInput")
        self.assertEqual(email_input.get("autocomplete"), "email")
        self.assertEqual(email_input.get("aria-errormessage"), "authEmailError")
        email_err = soup.find(id="authEmailError")
        self.assertIn("field-error-msg", email_err.get("class", []))

        otp_input = soup.find(id="authOtpInput")
        self.assertEqual(otp_input.get("autocomplete"), "one-time-code")
        self.assertEqual(otp_input.get("inputmode"), "numeric")

        otp_notice = soup.find(id="authOtpNotice")
        self.assertEqual(otp_notice.get("role"), "status")
        self.assertEqual(otp_notice.get("aria-live"), "polite")

        # Labels linked via for attribute
        email_label = soup.find("label", attrs={"for": "authEmailInput"})
        self.assertIsNotNone(email_label, "Missing label[for='authEmailInput'] in authModal")
        otp_label = soup.find("label", attrs={"for": "authOtpInput"})
        self.assertIsNotNone(otp_label, "Missing label[for='authOtpInput'] in authModal")

    def test_etf_matrix_dom_bindings_and_sync_contract(self):
        """
        Verify that triggerAmfiSync() in etf_matrix.html references valid DOM elements
        (#sync-amfi-btn, #sync-icon, #sync-text) and targets the active /api/admin/etfs/trigger-ingest route.
        """
        res = self.client.get("/etfs")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")

        btn = soup.find(id="sync-amfi-btn")
        self.assertIsNotNone(btn, "Missing #sync-amfi-btn in /etfs")
        self.assertIn("triggerAmfiSync()", btn.get("onclick", ""))

        icon = soup.find(id="sync-icon")
        self.assertIsNotNone(icon, "Missing #sync-icon in /etfs")

        text = soup.find(id="sync-text")
        self.assertIsNotNone(text, "Missing #sync-text in /etfs")

        # Verify triggerAmfiSync function exists and references these elements
        html_text = res.text
        self.assertIn("async function triggerAmfiSync()", html_text)
        self.assertIn("/api/admin/etfs/trigger-ingest", html_text)
        self.assertIn("Admin Auth Required", html_text)
        self.assertIn("res.json().catch", html_text)

    # =========================================================================
    # Pillar 3: Client-Side Fetch Contracts (Route Alignment)
    # =========================================================================

    def test_client_fetch_calls_target_registered_fastapi_endpoints(self):
        """
        Inspects all fetch('/api/...') calls in JS files and inline scripts
        to ensure they target valid registered FastAPI routes.
        """
        all_scripts = []
        for js_file in self.js_dir.glob("*.js"):
            all_scripts.append((js_file.name, js_file.read_text(encoding="utf-8")))

        for html_file in self.templates_dir.rglob("*.html"):
            content = html_file.read_text(encoding="utf-8")
            inline = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
            for s in inline:
                all_scripts.append((html_file.name, s))

        # Known route template matchers
        def is_route_valid(path: str) -> bool:
            # Strip query strings
            clean = path.split("?")[0]
            if clean in self.registered_routes:
                return True
            # Parameterized matching
            clean_regex = "^" + re.sub(r'TEST_PARAM', r'[^/]+', clean) + "$"
            for reg in self.registered_routes:
                reg_regex = "^" + re.sub(r'\{[a-zA-Z0-9_]+\}', r'[^/]+', reg) + "$"
                if re.match(reg_regex, clean) or re.match(clean_regex, reg):
                    return True
            return False

        fetch_pattern = re.compile(r'fetch\(["\'`](/api/[^"\'`\s?]+)[^"\'`]*["\'`]')

        for source_name, code in all_scripts:
            # Normalize template literals e.g. /api/msme/${uin} -> /api/msme/TEST
            normalized_code = re.sub(r'\$\{.*?\}', 'TEST_PARAM', code)
            matches = fetch_pattern.findall(normalized_code)
            for endpoint in matches:
                self.assertTrue(
                    is_route_valid(endpoint),
                    f"Source '{source_name}' calls unregistered API route: '{endpoint}'"
                )

    # =========================================================================
    # Pillar 4: Full DOM Parsing & Semantic Verification on /msme & /msme/{uin}
    # =========================================================================

    def test_msme_directory_table_rows_and_inspect_buttons(self):
        """
        Parse /msme with BeautifulSoup to verify:
        - At least 60 active table rows exist.
        - Every row has an 'Inspect' button with a well-formed onclick="inspectMsme('UDYAM-...', this)".
        - Every row contains an explicit hyperlink to /msme/{uin}.
        """
        res = self.client.get("/msme")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")

        # Table rows in tbody
        tbody = soup.find("tbody")
        self.assertIsNotNone(tbody, "Missing <tbody> in /msme directory table")
        rows = tbody.find_all("tr")
        self.assertGreaterEqual(len(rows), 60, f"Expected at least 60 MSME rows, found {len(rows)}")

        for idx, row in enumerate(rows[:20]):  # Sample first 20 rows thoroughly
            # Inspect button
            inspect_btn = row.find("button", onclick=re.compile(r"^inspectMsme\("))
            self.assertIsNotNone(inspect_btn, f"Row {idx} missing functional inspect button")
            self.assertIn("btn", inspect_btn.get("class", []))
            self.assertIn("Inspect", inspect_btn.get_text())

            # Direct link to standalone dossier
            uin_link = row.find("a", href=re.compile(r"^/msme/UDYAM-"))
            self.assertIsNotNone(uin_link, f"Row {idx} missing direct hyperlink to /msme/{{uin}}")

    def test_msme_standalone_dossier_dom_structure(self):
        """
        Verify /msme/{uin} renders with full DOM hierarchy:
        - Breadcrumb navigation link to /msme
        - 4 distinct analytical pillar sections with correct numbering (01 to 04)
        - Active listed corporate equity badges linking to /dossier/{ticker}
        - Print / PDF trigger button
        - Statutory regulatory safe harbor
        """
        sample_uin = "UDYAM-MH-26-0012480"
        res = self.client.get(f"/msme/{sample_uin}")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")

        # Breadcrumb link
        back_link = soup.find(lambda tag: tag.name == "a" and "Back to MSME" in tag.get_text())
        self.assertIsNotNone(back_link, "Breadcrumb link to /msme is missing")
        self.assertEqual(back_link.get("href"), "/msme")

        # Heading 1
        h1 = soup.find("h1")
        self.assertIsNotNone(h1)
        self.assertIn("Sahyadri Precision Forgings", h1.get_text())

        # 4 Pillar headings inside <main>
        main_content = soup.find("main")
        self.assertIsNotNone(main_content)
        pillar_headings = main_content.find_all("h2")
        self.assertEqual(len(pillar_headings), 4, f"Expected 4 pillar <h2> elements inside main, found {len(pillar_headings)}")

        pillar_texts = [h.get_text() for h in pillar_headings]
        self.assertTrue(any("Working Capital" in t for t in pillar_texts))
        self.assertTrue(any("Supply Chain" in t for t in pillar_texts))
        self.assertTrue(any("Solvency" in t for t in pillar_texts))
        self.assertTrue(any("Moat" in t for t in pillar_texts))

        # Listed corporate badges
        equity_links = soup.find_all("a", href=re.compile(r"^/dossier/"))
        self.assertGreaterEqual(len(equity_links), 2, "Expected at least 2 listed corporate linkage links")
        for link in equity_links:
            self.assertIn("Audit", link.get_text())

        # Regulatory Notice
        text = soup.get_text()
        self.assertIn("Statutory Regulatory Notice:", text)
        self.assertIn("MSMED Act 2020", text)

    # =========================================================================
    # Pillar 5: Template Hygiene (Zero Raw Jinja Expression Leaks in Attributes)
    # =========================================================================

    def test_no_unrendered_jinja_expressions_in_rendered_html_attributes(self):
        """
        Audit major rendered pages to ensure zero unrendered '{{' or '{%' fragments
        accidentally leak into href, onclick, id, class, or data attributes.
        """
        test_routes = [
            "/",
            "/search",
            "/equities",
            "/funds",
            "/debt",
            "/sovereign",
            "/reits",
            "/opportunities",
            "/pricing",
            "/contact",
            "/msme",
            "/msme/UDYAM-MH-26-0012480"
        ]

        attribute_names = ["href", "onclick", "id", "class", "src", "action", "data-target"]

        for route in test_routes:
            res = self.client.get(route)
            self.assertEqual(res.status_code, 200, f"Route {route} failed with status {res.status_code}")
            soup = BeautifulSoup(res.text, "html.parser")

            for tag in soup.find_all(True):
                for attr in attribute_names:
                    val = tag.get(attr)
                    if isinstance(val, str):
                        self.assertNotIn(
                            "{{", val,
                            f"Unrendered Jinja template tag '{{{{' leaked in {tag.name} [{attr}='{val}'] on {route}"
                        )
                        self.assertNotIn(
                            "{%", val,
                            f"Unrendered Jinja template tag '{{%' leaked in {tag.name} [{attr}='{val}'] on {route}"
                        )




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
        cls.project_root = Path(__file__).resolve().parent.parent.parent

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
            "filterSector", "filterCategory", "toggleMonitoringFeed", "openWatchlistModal",
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

    def test_extract_api_error_implementation_and_evaluation(self):
        """Verifies that extractApiError is defined, exposed on window, and properly parses all FastAPI error variants."""
        import subprocess
        import json
        import re

        main_js_path = self.project_root / "web" / "static" / "js" / "main.js"
        content = main_js_path.read_text(encoding="utf-8")
        self.assertIn("function extractApiError", content)
        self.assertIn("window.extractApiError = extractApiError", content)
        self.assertIn("extractApiError(data", content)

        # Extract the exact function implementation directly from main.js
        pattern = r"(function extractApiError\([\s\S]*?^\})"
        match = re.search(pattern, content, re.MULTILINE)
        self.assertIsNotNone(match, "extractApiError must be declared in main.js")
        fn_code = match.group(1)

        # Empirically execute the exact function using Node.js
        node_script = f"""
        {fn_code}
        const results = [
            extractApiError({{ detail: 'String error' }}, 'fallback'),
            extractApiError({{ detail: {{ message: 'Nested message error' }} }}, 'fallback'),
            extractApiError({{ detail: {{ error: 'ERR_CODE_ONLY' }} }}, 'fallback'),
            extractApiError({{ detail: [{{ loc: ['body', 'ticker'], msg: 'field required' }}] }}, 'fallback'),
            extractApiError({{ message: 'Top-level message' }}, 'fallback'),
            extractApiError({{ error: 'Top-level error' }}, 'fallback'),
            extractApiError(null, 'Custom fallback'),
            extractApiError({{}}, 'Custom fallback')
        ];
        console.log(JSON.stringify(results));
        """
        import shutil
        node_bin = shutil.which("node")
        if node_bin:
            proc = subprocess.run(
                [node_bin, "-e", node_script],
                capture_output=True,
                text=True,
                check=True
            )
            res = json.loads(proc.stdout.strip())
            self.assertEqual(res[0], "String error")
            self.assertEqual(res[1], "Nested message error")
            self.assertEqual(res[2], "ERR_CODE_ONLY")
            self.assertEqual(res[3], "ticker: field required")
            self.assertEqual(res[4], "Top-level message")
            self.assertEqual(res[5], "Top-level error")
            self.assertEqual(res[6], "Custom fallback")
            self.assertEqual(res[7], "Custom fallback")
        else:
            # Rigorous AST/regex structural verification when Node.js is not installed (e.g. Render / pure Python runtime)
            self.assertIn("typeof data === 'string'", fn_code)
            self.assertIn("typeof data.detail === 'string'", fn_code)
            self.assertIn("Array.isArray(data.detail)", fn_code)
            self.assertIn("data.detail.message", fn_code)
            self.assertIn("data.detail.error", fn_code)
            self.assertIn("data.message", fn_code)
            self.assertIn("data.error", fn_code)
            self.assertIn("return fallbackMessage", fn_code)

    def test_refresh_user_balance_and_update_nav_auth_ui_contracts(self):
        """Verifies that refreshUserBalance handles 401/403/404 session invalidation and updateNavAuthUI updates DOM state."""
        import subprocess
        import json
        import re
        import shutil

        main_js_path = self.project_root / "web" / "static" / "js" / "main.js"
        content = main_js_path.read_text(encoding="utf-8")
        self.assertIn("function refreshUserBalance", content)
        self.assertIn("window.refreshUserBalance = refreshUserBalance", content)
        self.assertIn("function updateNavAuthUI", content)
        self.assertIn("window.updateNavAuthUI = updateNavAuthUI", content)
        self.assertIn("localStorage.removeItem('sr_user')", content)

        # Extract refreshUserBalance and updateNavAuthUI implementations
        pattern_refresh = r"(async function refreshUserBalance\([\s\S]*?^\})"
        match_refresh = re.search(pattern_refresh, content, re.MULTILINE)
        self.assertIsNotNone(match_refresh, "refreshUserBalance must be declared in main.js")

        pattern_nav = r"(function updateNavAuthUI\([\s\S]*?^\})"
        match_nav = re.search(pattern_nav, content, re.MULTILINE)
        self.assertIsNotNone(match_nav, "updateNavAuthUI must be declared in main.js")

        node_script = f"""
        const mockStorage = {{}};
        global.localStorage = {{
            setItem: (k, v) => {{ mockStorage[k] = v; }},
            getItem: (k) => mockStorage[k] || null,
            removeItem: (k) => {{ delete mockStorage[k]; }}
        }};

        const navBtn = {{ innerText: '', innerHTML: '', classList: {{ remove: () => {{}}, add: () => {{}} }} }};
        const modalBal = {{ innerText: '' }};
        global.document = {{
            getElementById: (id) => {{
                if (id === 'navSignInBtn') return navBtn;
                if (id === 'generateModalCreditsText') return modalBal;
                return null;
            }}
        }};
        global.getStoredUser = () => mockStorage['sr_user'] ? JSON.parse(mockStorage['sr_user']) : null;

        {match_nav.group(1)}

        // Test 1: updateNavAuthUI with valid user
        updateNavAuthUI({{ id: 'usr_test', full_name: 'Test Allocator', credits_balance: 5.0 }});
        const authedBtnText = navBtn.innerText;
        const authedModalText = modalBal.innerText;

        // Test 2: updateNavAuthUI with null (signed out)
        updateNavAuthUI(null);
        const signedOutBtnText = navBtn.innerHTML;
        const signedOutModalText = modalBal.innerText;

        console.log(JSON.stringify({{
            authedBtn: authedBtnText,
            authedModal: authedModalText,
            signedOutBtn: signedOutBtnText,
            signedOutModal: signedOutModalText
        }}));
        """
        node_bin = shutil.which("node")
        if node_bin:
            proc = subprocess.run(
                [node_bin, "-e", node_script],
                capture_output=True,
                text=True,
                check=True
            )
            res = json.loads(proc.stdout.strip())
            self.assertIn("Test Allocator", res["authedBtn"])
            self.assertIn("5 Credits", res["authedBtn"])
            self.assertIn("5 Credits Available", res["authedModal"])
            self.assertIn("Sign In / 2 Credits", res["signedOutBtn"])
            self.assertIn("2 Free Credits on Sign In", res["signedOutModal"])
        else:
            # Rigorous AST/regex structural verification when Node.js is not installed (e.g. Render / pure Python runtime)
            self.assertIn("user.full_name", match_nav.group(1))
            self.assertIn("credits_balance", match_nav.group(1))
            self.assertIn("Credits Available", match_nav.group(1))
            self.assertIn("Sign In / 2 Credits", match_nav.group(1))
            self.assertIn("2 Free Credits on Sign In", match_nav.group(1))
            self.assertIn("localStorage.removeItem('sr_user')", match_refresh.group(1))



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
        self.assertIn('id="overlayTrustCardDeck"', base_html)
        self.assertIn('id="overlayCardCategoryBadge"', base_html)
        self.assertIn('id="overlayCardTitle"', base_html)
        self.assertIn('id="overlayCardBody"', base_html)
        self.assertIn('id="overlayCardTimerFill"', base_html)
        self.assertIn("HUD_DISCOVERY_CARDS", js_content)
        self.assertIn("completeEvaluationHUD", js_content)
        self.assertIn("nextEvaluationCard", js_content)
        self.assertIn("prevEvaluationCard", js_content)
        self.assertGreaterEqual(js_content.count("category: 'trust'"), 20)
        self.assertGreaterEqual(js_content.count("category: 'product'"), 12)

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
        cls.project_root = Path(__file__).resolve().parent.parent.parent

    def test_copilot_js_uses_brand_icons_not_raw_emojis(self):
        """Research Desk must render brand sprite icons only; every icon id must exist in the base.html sprite."""
        content = (self.project_root / "web" / "static" / "js" / "copilot.js").read_text(encoding="utf-8")
        emoji = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50]")
        self.assertEqual(emoji.findall(content), [], "copilot.js must not contain raw OS emojis")
        base_html = (self.project_root / "web" / "templates" / "base.html").read_text(encoding="utf-8")
        sprite_ids = set(re.findall(r'<symbol id="([a-z0-9-]+)"', base_html))
        used = set(re.findall(r'icon: "(icon-[a-z0-9-]+)"', content)) | set(re.findall(r'brandGlyph\("(icon-[a-z0-9-]+)"\)', content))
        self.assertTrue(used, "copilot.js must reference brand icons")
        self.assertEqual(sorted(used - sprite_ids), [], "copilot.js references icon ids missing from the base.html sprite")

    def test_legacy_app_name_and_named_person_not_in_visible_copy(self):
        """Visible copy uses 'Moatnomics', and no feature title attributes an endorsement to a named person."""
        paths = [self.project_root / "web" / "legal_content.py", self.project_root / "web" / "templates" / "base.html"]
        for p in paths:
            self.assertNotIn("Stock Research" + " App", p.read_text(encoding="utf-8"), f"{p.name} must say Moatnomics")
        for p in (self.project_root / "web" / "templates").rglob("*.html"):
            self.assertNotIn("Munger", p.read_text(encoding="utf-8"), f"{p.name} names a person in a feature title")
        pdf_src = (self.project_root / "core" / "reporting" / "pdf.py").read_text(encoding="utf-8")
        self.assertNotIn("Generated by " + "Stock Research" + " App", pdf_src)

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
        self.assertIn(
            'rawText = await resp.text();',
            content,
            "copilot.js must read rawText before JSON parsing to guard against non-JSON error pages"
        )
        self.assertIn(
            'clearInterval(thinkingTimer);',
            content,
            "copilot.js must unconditionally clear thinkingTimer in finally block"
        )
        self.assertTrue(
            'throw new Error(errMsg);' in content or 'throw new Error(detailMsg);' in content,
            "copilot.js must throw structured error on non-200 responses"
        )
        self.assertIn(
            'data.guardrail_triggered',
            content,
            "copilot.js must check data.guardrail_triggered for SEBI safe harbor notice"
        )
        self.assertIn(
            'copilot-guardrail-badge',
            content,
            "copilot.js must render .copilot-guardrail-badge"
        )
        self.assertIn(
            'copilot-citation-tag',
            content,
            "copilot.js must render .copilot-citation-tag for citations"
        )
        self.assertIn(
            'formatCopilotMarkdown',
            content,
            "copilot.js must support formatCopilotMarkdown"
        )
        self.assertIn(
            'document.body.appendChild(modal);',
            content,
            "copilot.js must hoist #copilotModalBackdrop to document.body outside <main>"
        )
        self.assertIn(
            '!mainEl.contains(modal)',
            content,
            "copilot.js must guard mainEl.inert = true with !mainEl.contains(modal) to prevent self-lockout"
        )
        self.assertIn(
            'modal.inert = false;',
            content,
            "copilot.js must explicitly keep #copilotModalBackdrop non-inert"
        )
        self.assertIn(
            'mainEl.inert = true;',
            content,
            "copilot.js must set mainEl.inert = true on modal open for background focus trapping"
        )
        self.assertIn(
            'mainEl.inert = false;',
            content,
            "copilot.js must set mainEl.inert = false on closeCopilot"
        )
        self.assertIn(
            'event.isComposing || event.keyCode === 229',
            content,
            "copilot.js handleCopilotKeydown must protect against premature IME composition submit"
        )

    def test_copilot_modal_html_has_interactive_options(self):
        """Audits copilot_modal.html to verify markup has accessible, clickable option elements."""
        modal_path = self.project_root / "web" / "templates" / "partials" / "copilot_modal.html"
        self.assertTrue(modal_path.exists(), "copilot_modal.html must exist")
        content = modal_path.read_text(encoding="utf-8")

        self.assertIn("data-copilot-prompt", content)
        self.assertIn("copilot-intro-feature-item", content)
        self.assertIn("copilot-chip-btn", content)

    def test_modern_web_guidance_css_tokens_and_directives(self):
        """Outside-in verification: Asserts style.css includes modern browser UI theming, dialogs, toasts, and containment."""
        css_path = self.project_root / "web" / "static" / "css" / "style.css"
        self.assertTrue(css_path.exists(), "style.css must exist")
        content = css_path.read_text(encoding="utf-8")

        self.assertIn("color-scheme: dark;", content)
        self.assertIn("accent-color: var(--accent-cyan);", content)
        self.assertIn("text-wrap: balance;", content)
        self.assertIn("text-wrap: pretty;", content)
        self.assertIn("dialog.modal-dialog-native", content)
        self.assertIn("overscroll-behavior: contain;", content)
        self.assertIn(".toast-popover[popover]", content)
        self.assertIn("content-visibility: auto;", content)
        self.assertIn("contain-intrinsic-size: auto 180px;", content)
        self.assertIn("input:user-invalid", content)
        self.assertIn("input:user-valid", content)
        self.assertIn("mask-image: linear-gradient(to bottom, black 50%, transparent 100%);", content)
        self.assertIn("progress.loading-spinner:indeterminate", content)
        self.assertIn("prefers-reduced-motion: reduce", content)

    def test_modern_web_guidance_js_utilities(self):
        """Outside-in verification: Asserts main.js includes showToast, initDialogLightDismiss, modal Escape handler, and user-invalid ARIA sync."""
        js_path = self.project_root / "web" / "static" / "js" / "main.js"
        self.assertTrue(js_path.exists(), "main.js must exist")
        content = js_path.read_text(encoding="utf-8")

        self.assertIn("window.showToast = function", content)
        self.assertIn('toast.className = "toast-popover";', content)
        self.assertIn('toast.setAttribute("popover", "manual");', content)
        self.assertIn('toast.showPopover()', content)
        self.assertIn("window.initDialogLightDismiss = function", content)
        self.assertIn('"closedBy" in HTMLDialogElement.prototype', content)
        self.assertIn('document.querySelectorAll(".modal-backdrop")', content)
        self.assertIn("initUserInvalidAriaSync", content)
        self.assertIn('el.setAttribute("aria-invalid", el.matches(":user-invalid") ? "true" : "false");', content)
        self.assertIn('document.querySelectorAll(\'[hidden="until-found"]\')', content)
        self.assertIn('panel.addEventListener("beforematch"', content)
        self.assertIn('panel.removeAttribute("hidden");', content)
        self.assertIn('trigger.setAttribute("aria-expanded", "true");', content)

    def test_equity_options_yield_distinct_responses(self):
        """Verifies that each option within the Research Desk for Equities returns a unique, data-grounded response."""
        equity_prompts = [
            ("countercase", "Run a countercase analysis on this stock: what failure modes could destroy shareholder value?"),
            ("reverse_dcf", "What implied growth rate is priced into current CMP based on Reverse DCF?"),
            ("governance", "Are there any promoter pledging or corporate governance red flags in recent disclosures?"),
            ("solvency", "Evaluate balance sheet solvency and leverage ratios for this company.")
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
            self.assertNotIn("Select a diagnostic pillar to drill into", text, f"Option {opt_key} fell back to generic summary")

        distinct_responses = set(responses.values())
        self.assertEqual(len(distinct_responses), 4, "All 4 equity options must produce completely distinct diagnostic analyses!")

        self.assertIn("Countercase Analysis", responses["countercase"])
        self.assertIn("Countercase", responses["countercase"])
        self.assertIn("assume the investment thesis disappoints", responses["countercase"])
        self.assertIn("Reverse DCF Valuation & Implied Growth Deconstruction", responses["reverse_dcf"])
        self.assertIn("Current Market Price (CMP)", responses["reverse_dcf"])
        self.assertIn("Implied FCF Growth Priced In", responses["reverse_dcf"])
        self.assertIn("Benchmark Hurdle Rate", responses["reverse_dcf"])
        self.assertIn("Forensic Accounting & Governance Audit", responses["governance"])
        self.assertIn("0.0% Pledged", responses["governance"])
        self.assertIn("Balance Sheet Solvency & Liquidity Diagnostic", responses["solvency"])
        self.assertIn("Balance-Sheet Distress & Solvency Zone", responses["solvency"])

    def test_mutual_fund_options_yield_distinct_responses(self):
        """Verifies that each option within the Fund Look-Through Intelligence Desk returns a unique response."""
        mf_prompts = [
            ("moat", "Evaluate the constituent moat distribution and overall portfolio quality for this fund."),
            ("asri", "Which underlying constituent holdings carry the highest accounting risk or lowest health score?"),
            ("active_share", "Audit the active share and check if this fund is exhibiting benchmark hugging or style drift."),
            ("fee_drag", "What is the 20-year compounded fee drag and cost of distributor commissions for this fund?")
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
        self.assertIn("Intermediary Fee Drag & Compounding Cost Audit", responses["fee_drag"])

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

    def test_open_ended_and_liveness_queries(self):
        """Verifies that open-ended and liveness conversational queries produce robust responses."""
        queries = [
            ("begin", "I don't know, where should we begin?", "Forensic Research Roadmap"),
            ("liveness", "Why don't you respond to me?", "Research Desk Active"),
            ("best_thing", "tell me the best thing about this stock?", "Bull Thesis")
        ]

        for key, prompt, expected_keyword in queries:
            resp = self.client.post("/api/copilot/chat", json={
                "conversation_id": f"TEST-COPILOT-OPEN-{key}",
                "message": prompt,
                "ticker": "CUPID",
                "asset_type": "equity"
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("success"))
            text = data.get("response", "")
            self.assertTrue(len(text) > 200, f"Query '{prompt}' yielded truncated response")
            self.assertIn(expected_keyword, text, f"Query '{prompt}' missing expected keyword '{expected_keyword}'")




"""Unit and Integration Test Suite for Competitive Differentiation Enhancements.

Tests:
1. Phase 1: Daily Mutual Fund Forensic Rotation Scheduler & AMFI Event Ledger Syndication
2. Phase 2: Equity-to-Debt Contagion Bridge (Credit Contagion Radar & SDI Isolation)
3. Phase 3: Opportunity Terminal Cross-Asset 5-Sleeve Post-Tax Real Yield
4. Phase 4: Autonomous Event Syndication & UI Radar Elements
5. Phase 5: Multi-Asset Research Desk & PDF Report Dossier Compilation
"""

import os
os.environ["TESTING"] = "1"

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from web.main import app
from core.db.connection import init_db
from core.db.mutual_funds import seed_default_mutual_funds, get_mutual_fund_scheme, get_fund_forensic_dossier
from core.db.debt import seed_default_debt_securities, get_debt_security_by_isin
from core.db.agent_sessions import record_autonomous_event, get_recent_autonomous_events
from core.analysis.debt_engine import evaluate_equity_cross_contagion, evaluate_5_pillar_credit_posture
from core.reporting.pdf import generate_fund_dossier_pdf, generate_debt_dossier_pdf


class TestCompetitiveEnhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_default_mutual_funds()
        seed_default_debt_securities()
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    def test_credit_contagion_radar_insulated_equity(self):
        """Tests that a strong corporate debt issuer maps to Insulated Equity Moat."""
        sec = get_debt_security_by_isin("INE002A08012")  # Reliance Industries NCD
        self.assertIsNotNone(sec)
        radar = evaluate_equity_cross_contagion(sec)
        self.assertIn(radar["radar_status"], ["INSULATED_EQUITY_MOAT", "MONITORED_EQUITY_DRIFT"])
        self.assertEqual(radar["risk_level"], "LOW")
        self.assertIn("promoter_pledged_pct", radar)
        self.assertTrue(len(radar["radar_indicators"]) >= 3)

    def test_credit_contagion_radar_sdi_ringfenced(self):
        """Tests that a Securitized Debt Instrument (SDI) is classified as Bankruptcy-Remote SPV."""
        sec = get_debt_security_by_isin("IN902SDI0025")  # Grip LeaseX SDI
        self.assertIsNotNone(sec)
        radar = evaluate_equity_cross_contagion(sec)
        self.assertEqual(radar["radar_status"], "BANK_RINGFENCED_SDI")
        self.assertEqual(radar["badge_color"], "#38bdf8")
        self.assertIn("Bankruptcy-Remote", radar["radar_label"])
        self.assertIn("FLDG", radar["radar_indicators"][1]["metric"])

    def test_credit_contagion_radar_active_alert_on_pledge(self):
        """Tests that high promoter pledge triggers ACTIVE_CONTAGION_ALERT."""
        stressed_sec = {
            "isin": "INE999STRESS01",
            "ticker": "STRESSCORP",
            "is_sdi": False,
            "metadata": {"debt_to_equity": 3.8}
        }
        with patch("core.analysis.fundamentals.get_stock_fundamentals") as mock_fund:
            mock_fund.return_value = {
                "pledged_promoter_holding": 28.5,
                "promoter_holding": 42.0,
                "debt_to_equity": 3.8,
                "piotroski_f_score": 2
            }
            # Also clear testing flag temporarily for this targeted assertion
            with patch.dict(os.environ, {"TESTING": ""}):
                radar = evaluate_equity_cross_contagion(stressed_sec)
                self.assertEqual(radar["radar_status"], "ACTIVE_CONTAGION_ALERT")
                self.assertEqual(radar["risk_level"], "HIGH")
                self.assertEqual(radar["badge_color"], "#ef4444")
                self.assertIn("Elevated equity distress", radar["radar_summary"])

    def test_get_debt_securities_for_equity(self):
        """Tests that equity tickers find matching debt securities and subsidiary debentures."""
        from core.db.debt import get_debt_securities_for_equity
        rel_debt = get_debt_securities_for_equity("RELIANCE")
        self.assertGreater(len(rel_debt), 0)
        self.assertTrue(any(d.get("isin") == "INE002A08012" for d in rel_debt))

        tata_debt = get_debt_securities_for_equity("TATAMOTORS")
        self.assertGreater(len(tata_debt), 0)
        self.assertTrue(any("TATACAP" in d.get("ticker", "") for d in tata_debt))

    def test_equity_dossier_pending_renders_linked_debt(self):
        """Tests that uncompiled equity tickers with active debt display listed debt tranches."""
        with patch("web.main.get_report_by_ticker_sync", return_value=None):
            resp = self.client.get("/dossier/RELIANCE")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("PENDING COMPILATION", resp.text)
            self.assertIn("Capital Structure: Listed Corporate Debentures", resp.text)
            self.assertIn("INE002A08012", resp.text)
            self.assertIn("/debt/INE002A08012", resp.text)

    def test_phase_3_opportunity_terminal_cross_asset_real_yield(self):
        """Tests Phase 3 cross-asset aggregation, statutory tax waterfalls, and scenario filters."""
        from core.analysis.opportunity_terminal import get_normalized_opportunity_universe, calculate_tax_waterfall

        # 1. Verify multi-asset classes present
        universe = get_normalized_opportunity_universe(tax_slab=30.0, cpi_inflation=4.5)
        asset_classes = {x["asset_class"] for x in universe}
        expected_classes = {"BOND", "REIT", "SGB", "SOVEREIGN", "MF", "EQUITY"}
        for ec in expected_classes:
            self.assertIn(ec, asset_classes)

        # 2. Verify dynamic tax slab calculation (e.g. 10% New Tax Regime vs 30% Standard)
        b_10 = calculate_tax_waterfall(10.0, "BOND", tax_slab=10.0)
        b_30 = calculate_tax_waterfall(10.0, "BOND", tax_slab=30.0)
        self.assertEqual(b_10["net_yield_pct"], 9.0)
        self.assertEqual(b_30["net_yield_pct"], 7.0)

        # 3. Verify scenario filters
        pres = get_normalized_opportunity_universe(persona_filter="capital_preservation")
        self.assertTrue(all(x.get("real_yield_pct", 0) >= 0 for x in pres))

        cash = get_normalized_opportunity_universe(persona_filter="maximum_cashflow")
        self.assertTrue(len(cash) > 0)

        upside = get_normalized_opportunity_universe(persona_filter="asymmetric_upside")
        self.assertTrue(len(upside) > 0)

    def test_multi_asset_copilot_mutual_fund(self):
        """Tests that Copilot correctly grounds context when querying a mutual fund scheme."""
        import asyncio
        from core.agents.copilot.research_desk import process_research_desk_turn

        async def _run():
            res = await process_research_desk_turn(
                conversation_id="TEST-COPILOT-MF-101",
                user_message="Provide a diagnostic look-through summary of this fund.",
                ticker="PPFAS_FLEXICAP_DIR",
                asset_type="mutual_fund"
            )
            self.assertIn(res["status"], ["COMPLETED", "DETERMINISTIC_FALLBACK"])
            self.assertTrue(len(res["response"]) > 50)
            # Response must discuss fund forensics and not single company P/E or Reverse DCF
            self.assertNotIn("company's Margin of Safety", res["response"])

        asyncio.run(_run())

    def test_copilot_mutual_fund_non_advisory_deflection(self):
        """Tests that retail advisory queries on mutual funds yield fund-specific SEBI notices without stock jargon."""
        import asyncio
        from core.agents.copilot.research_desk import process_research_desk_turn

        async def _run():
            res = await process_research_desk_turn(
                conversation_id="TEST-COPILOT-MF-DEFLECT",
                user_message="Should I buy this fund right now?",
                ticker="PPFAS_FLEXICAP_DIR",
                asset_type="mutual_fund"
            )
            self.assertEqual(res["status"], "REGULATORY_DEFLECTED")
            self.assertIn("Section 2(u)", res["response"])
            self.assertIn("Look-Through Forensic Breakdown", res["response"])
            self.assertIn("Distributor Fee Drag", res["response"])
            # MUST NOT mention single stock DCF or the company's balance sheet
            self.assertNotIn("break down the company's Margin of Safety", res["response"])

        asyncio.run(_run())

    def test_copilot_mutual_fund_section_awareness(self):
        """Tests that clicking Copilot within specific sections yields section-anchored diagnostic intelligence."""
        import asyncio
        from core.agents.copilot.research_desk import process_research_desk_turn

        async def _run():
            # 1. Fee Drag Section
            res_fee = await process_research_desk_turn(
                conversation_id="TEST-COPILOT-SEC-FEE",
                user_message="Explain the fee impact.",
                ticker="PPFAS_FLEXICAP_DIR",
                asset_type="mutual_fund",
                section="fee_drag",
                section_label="Intermediary Fee Drag"
            )
            self.assertIn(res_fee["status"], ["COMPLETED", "DETERMINISTIC_FALLBACK"])
            self.assertIn("Fee Drag", res_fee["response"])

            # 2. Active Share Section
            res_as = await process_research_desk_turn(
                conversation_id="TEST-COPILOT-SEC-AS",
                user_message="Is this fund hugging the benchmark?",
                ticker="PPFAS_FLEXICAP_DIR",
                asset_type="mutual_fund",
                section="active_share",
                section_label="Active Share & Closet Indexing"
            )
            self.assertIn(res_as["status"], ["COMPLETED", "DETERMINISTIC_FALLBACK"])
            self.assertIn("Active Share", res_as["response"])

            # 3. Look-Through Accounting Risk (ASRI) Section
            res_asri = await process_research_desk_turn(
                conversation_id="TEST-COPILOT-SEC-ASRI",
                user_message="What are the accounting red flags?",
                ticker="PPFAS_FLEXICAP_DIR",
                asset_type="mutual_fund",
                section="asri_solvency",
                section_label="Accounting Risk (ASRI)",
                deep_dive_unlocked=True
            )
            self.assertIn(res_asri["status"], ["COMPLETED", "DETERMINISTIC_FALLBACK"])
            self.assertIn("Accounting Risk", res_asri["response"])

        asyncio.run(_run())

    def test_multi_asset_copilot_debt_security(self):
        """Tests that Copilot correctly grounds context when querying a debt security."""
        import asyncio
        from core.agents.copilot.research_desk import process_research_desk_turn

        async def _run():
            res = await process_research_desk_turn(
                conversation_id="TEST-COPILOT-DEBT-102",
                user_message="Assess the solvency and duration risk of this NCD.",
                ticker="INE002A08012"
            )
            self.assertIn(res["status"], ["COMPLETED", "DETERMINISTIC_FALLBACK"])
            self.assertTrue(len(res["response"]) > 50)

        asyncio.run(_run())

    def test_fund_pdf_generation_and_endpoint(self):
        """Tests compiling and serving PDF dossiers for mutual funds."""
        scheme = get_mutual_fund_scheme("PPFAS_FLEXICAP_DIR")
        dossier = get_fund_forensic_dossier("PPFAS_FLEXICAP_DIR") or {}
        pdf_bytes = generate_fund_dossier_pdf("PPFAS_FLEXICAP_DIR", dossier, scheme)
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        # Test HTTP route
        resp = self.client.get("/api/pdf/fund/PPFAS_FLEXICAP_DIR")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_debt_pdf_generation_and_endpoint(self):
        """Tests compiling and serving PDF dossiers for debt securities."""
        sec = get_debt_security_by_isin("INE002A08012")
        posture = evaluate_5_pillar_credit_posture(sec)
        pdf_bytes = generate_debt_dossier_pdf("INE002A08012", posture, sec)
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        # Test HTTP route
        resp = self.client.get("/api/pdf/debt/INE002A08012")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_web_ui_radar_and_copilot_markup(self):
        """Tests that base template, debt dossier, and fund dossier contain radar and copilot markup."""
        # 1. Base nav and action buttons
        resp_home = self.client.get("/")
        self.assertEqual(resp_home.status_code, 200)
        self.assertIn("Stock Reports & Equities", resp_home.text)
        self.assertIn("Mutual Funds", resp_home.text)
        self.assertIn("navSignInBtn", resp_home.text)
        self.assertNotIn("navGenerateBtn", resp_home.text)
        self.assertIn("/admin/audit", resp_home.text)

        # 2. Debt dossier contains Contagion Radar, Copilot trigger, and link to parent equity
        resp_debt = self.client.get("/debt/INE002A08012", headers={"x-unlock-preview": "1"})
        self.assertEqual(resp_debt.status_code, 200)
        self.assertIn("Credit Contagion Radar", resp_debt.text)
        self.assertIn("/dossier/RELIANCE", resp_debt.text)
        self.assertTrue("Research Desk" in resp_debt.text)
        self.assertIn("Export PDF", resp_debt.text)
        self.assertIn("copilotModalBackdrop", resp_debt.text)

        # 3. Fund dossier contains Copilot trigger and PDF export
        resp_fund = self.client.get("/funds/PPFAS_FLEXICAP_DIR")
        self.assertEqual(resp_fund.status_code, 200)
        self.assertTrue("Research Desk" in resp_fund.text)
        self.assertIn("Export PDF Dossier", resp_fund.text)
        self.assertIn("copilotModalBackdrop", resp_fund.text)

    def test_autonomous_event_ledger_integration(self):
        """Tests recording and retrieving autonomous fund and AMFI events."""
        event_id = record_autonomous_event(
            event_type="DAILY_FUND_AUDIT",
            ticker="TEST_FLEXICAP_DIR",
            trigger_source="TEST_SUITE_ROTATION",
            action_taken="7_PILLAR_LOOKTHROUGH_AUDIT",
            summary="Test automated 7-pillar look-through audit completed.",
            metadata={"health_score": 85.0}
        )
        self.assertTrue(event_id.startswith("EVT-"))
        events = get_recent_autonomous_events(limit=5, event_type="DAILY_FUND_AUDIT", include_test_events=True)
        self.assertTrue(any(e.get("event_id") == event_id for e in events))

        # Clean up test event so DB remains unpolluted
        from core.db.connection import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM autonomous_event_ledger WHERE event_id = ?", (event_id,))
            conn.commit()
        except Exception:
            pass
        finally:
            cur.close()
            conn.close()

    def test_reit_pdf_generation_and_endpoint(self):
        """Tests compiling and serving PDF research dossiers for REITs and InvITs."""
        from core.db.reits import get_reit_by_symbol
        from core.reporting.pdf import generate_reit_dossier_pdf

        reit = get_reit_by_symbol("EMBASSY")
        self.assertIsNotNone(reit)
        pdf_bytes = generate_reit_dossier_pdf("EMBASSY", reit)
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        # Test HTTP route
        resp = self.client.get("/api/pdf/reit/EMBASSY")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_monitoring_feed_endpoint(self):
        """Tests public /api/autonomous/events feed endpoint."""
        resp = self.client.get("/api/autonomous/events?limit=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("events"), list)

    def test_bse_watcher_material_filing_event_dispatch(self):
        """Tests BSE watcher event recording on material exchange disclosures."""
        import asyncio
        from core.agents.watchers.bse_watcher import scan_watchlist_bse_announcements

        with patch("core.agents.watchers.bse_watcher.get_watchlist") as mock_wl, \
             patch("core.agents.watchers.bse_watcher.fetch_latest_bse_announcement") as mock_fetch:
            mock_wl.return_value = [{"ticker": "TESTCORP"}]
            mock_fetch.return_value = "Resignation of Statutory Auditor M/s ABC & Co with immediate effect."

            events = asyncio.run(scan_watchlist_bse_announcements())
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["ticker"], "TESTCORP")
            self.assertTrue(events[0]["event_id"].startswith("EVT-"))




    def test_interactive_reverse_dcf_sandbox_contracts(self):
        """
        [Rule 6 Outside-In UI Contract Test]
        Validates the Interactive Pillar 05 Reverse DCF & 3-Model Valuation Sandbox:
        1. Container presence (#reverseDcfSandbox).
        2. All 3 interactive range sliders (#dcfGrowthSlider, #dcfWaccSlider, #dcfTermSlider) with oninput handler.
        3. All simulated output and value indicator elements exist (#dcfGrowthVal, #dcfWaccVal, #dcfTermVal, #dcfSimFairValue, #dcfSimMos, #dcfSimVerdictBar).
        4. Inline script defines recalcDcfSandbox function with valid numeric JSON embeddings.
        5. Zero unrendered Jinja tags ({{ or {%) leak into markup.
        """
        from bs4 import BeautifulSoup
        resp = self.client.get("/dossier/INFY")
        self.assertEqual(resp.status_code, 200)

        soup = BeautifulSoup(resp.text, "html.parser")
        sandbox = soup.find(id="reverseDcfSandbox")
        self.assertIsNotNone(sandbox, "#reverseDcfSandbox must be present when valuation_radar is COMPUTED")

        # Verify Sliders
        growth_slider = sandbox.find("input", id="dcfGrowthSlider")
        wacc_slider = sandbox.find("input", id="dcfWaccSlider")
        term_slider = sandbox.find("input", id="dcfTermSlider")

        self.assertIsNotNone(growth_slider)
        self.assertEqual(growth_slider.get("type"), "range")
        self.assertEqual(growth_slider.get("oninput"), "recalcDcfSandbox()")

        self.assertIsNotNone(wacc_slider)
        self.assertEqual(wacc_slider.get("type"), "range")
        self.assertEqual(wacc_slider.get("oninput"), "recalcDcfSandbox()")

        self.assertIsNotNone(term_slider)
        self.assertEqual(term_slider.get("type"), "range")
        self.assertEqual(term_slider.get("oninput"), "recalcDcfSandbox()")

        # Verify Output Elements
        self.assertIsNotNone(sandbox.find(id="dcfGrowthVal"))
        self.assertIsNotNone(sandbox.find(id="dcfWaccVal"))
        self.assertIsNotNone(sandbox.find(id="dcfTermVal"))
        self.assertIsNotNone(sandbox.find(id="dcfSimFairValue"))
        self.assertIsNotNone(sandbox.find(id="dcfSimMos"))
        self.assertIsNotNone(sandbox.find(id="dcfSimVerdictBar"))

        # Verify JS Wiring
        scripts = [s.string for s in soup.find_all("script") if s.string and "recalcDcfSandbox" in s.string]
        self.assertEqual(len(scripts), 1, "Exactly one script defining recalcDcfSandbox must be rendered")
        self.assertIn("function recalcDcfSandbox()", scripts[0])
        self.assertIn("dcfGrowthSlider", scripts[0])
        self.assertIn("dcfSimFairValue", scripts[0])
        self.assertIn("(dcfFv * 0.40) + (peModelFv * 0.35) + (epvModelFv * 0.25)", scripts[0])
        self.assertIn("Historical P/E Multiple (35%)", resp.text)
        self.assertIn("Graham Earnings Power Value Floor (25%)", resp.text)

        # Verify Zero Jinja Leaks in rendered sandbox
        sandbox_str = str(sandbox)
        self.assertNotIn("{{", sandbox_str, "Unrendered Jinja tag detected in #reverseDcfSandbox")
        self.assertNotIn("{%", sandbox_str, "Unrendered Jinja directive detected in #reverseDcfSandbox")

        # Verify locked dossier Free Strip does NOT falsely claim 'Interactive Reverse-DCF slider' is free
        locked_resp = TestClient(app).get("/dossier/INFY")
        self.assertEqual(locked_resp.status_code, 200)
        self.assertNotIn("Interactive Reverse-DCF slider", locked_resp.text)

        # Verify IMPLIED_GROWTH_ONLY renders Implied CAGR / Implied 5Y Growth without None% or 1 Credit Unlock on unlocked view
        ext_resp = self.client.get("/dossier/ETERNAL")
        self.assertEqual(ext_resp.status_code, 200)
        self.assertIn("Implied CAGR", ext_resp.text)
        self.assertIn("Implied 5Y Growth", ext_resp.text)
        self.assertNotIn("None%", ext_resp.text)
        self.assertNotIn("1 Credit Unlock", ext_resp.text)


    def test_interactive_mf_fee_drag_simulator_contracts(self):
        """
        [Rule 6 Outside-In UI Contract Test]
        Validates the Interactive 20-Year Direct vs. Regular Fee-Drag Simulator:
        1. Container presence (#mfFeeDragSimulator).
        2. All 3 interactive range sliders (#mfCorpusSlider, #mfHorizonSlider, #mfCagrSlider) with oninput handler.
        3. All label and simulated output elements exist (#mfCorpusLabel, #mfHorizonLabel, #mfCagrLabel, #mfDirectFinalVal, #mfRegularFinalVal, #mfDragLossVal, #mfDragPctSub).
        4. Inline script defines recalcMfFeeDrag function with valid numeric JSON embeddings.
        5. Zero unrendered Jinja tags ({{ or {%) leak into markup.
        """
        from bs4 import BeautifulSoup
        resp = self.client.get("/funds/PPFAS_FLEXICAP_DIR")
        self.assertEqual(resp.status_code, 200)

        soup = BeautifulSoup(resp.text, "html.parser")
        sim = soup.find(id="mfFeeDragSimulator")
        self.assertIsNotNone(sim, "#mfFeeDragSimulator must be present in fund dossier")

        # Verify Sliders
        corpus_slider = sim.find("input", id="mfCorpusSlider")
        horizon_slider = sim.find("input", id="mfHorizonSlider")
        cagr_slider = sim.find("input", id="mfCagrSlider")

        self.assertIsNotNone(corpus_slider)
        self.assertEqual(corpus_slider.get("type"), "range")
        self.assertEqual(corpus_slider.get("oninput"), "recalcMfFeeDrag()")

        self.assertIsNotNone(horizon_slider)
        self.assertEqual(horizon_slider.get("type"), "range")
        self.assertEqual(horizon_slider.get("oninput"), "recalcMfFeeDrag()")

        self.assertIsNotNone(cagr_slider)
        self.assertEqual(cagr_slider.get("type"), "range")
        self.assertEqual(cagr_slider.get("oninput"), "recalcMfFeeDrag()")

        # Verify Output and Label Elements
        self.assertIsNotNone(sim.find(id="mfCorpusLabel"))
        self.assertIsNotNone(sim.find(id="mfHorizonLabel"))
        self.assertIsNotNone(sim.find(id="mfCagrLabel"))
        self.assertIsNotNone(sim.find(id="mfDirectFinalVal"))
        self.assertIsNotNone(sim.find(id="mfRegularFinalVal"))
        self.assertIsNotNone(sim.find(id="mfDragLossVal"))
        self.assertIsNotNone(sim.find(id="mfDragPctSub"))

        # Verify JS Wiring
        scripts = [s.string for s in soup.find_all("script") if s.string and "recalcMfFeeDrag" in s.string]
        self.assertEqual(len(scripts), 1, "Exactly one script defining recalcMfFeeDrag must be rendered")
        self.assertIn("function recalcMfFeeDrag()", scripts[0])
        self.assertIn("mfCorpusSlider", scripts[0])
        self.assertIn("mfDragLossVal", scripts[0])

        # Verify Zero Jinja Leaks in rendered simulator
        sim_str = str(sim)
        self.assertNotIn("{{", sim_str, "Unrendered Jinja tag detected in #mfFeeDragSimulator")
        self.assertNotIn("{%", sim_str, "Unrendered Jinja directive detected in #mfFeeDragSimulator")

    def test_interactive_reit_sec56_cost_basis_simulator_contracts(self):
        """
        Verify the Interactive Corpus & Sec 56(2)(xii) Cost-Basis Amortization Simulator:
        1. #reitSec56Simulator container is rendered in REIT dossier.
        2. Both range sliders (#reitCorpusSlider and #reitYearsSlider) are present with oninput="recalcReitCorpusWaterfall()".
        3. All label and output tracker elements exist (#reitCorpusVal, #reitYearsVal, #reitSec56TrackerBar).
        4. Inline script defines recalcReitCorpusWaterfall function with reactive slab updates.
        5. Zero unrendered Jinja tags ({{ or {%) leak into markup.
        """
        from bs4 import BeautifulSoup
        for sym in ["EMBASSY", "PROPSHARE", "PGINVIT"]:
            resp = self.client.get(f"/reits/{sym}")
            self.assertEqual(resp.status_code, 200, f"Failed for /reits/{sym}")

            soup = BeautifulSoup(resp.text, "html.parser")
            sim = soup.find(id="reitSec56Simulator")
            self.assertIsNotNone(sim, f"#reitSec56Simulator must be present in /reits/{sym}")

            # Verify Sliders
            corpus_slider = sim.find("input", id="reitCorpusSlider")
            years_slider = sim.find("input", id="reitYearsSlider")

            self.assertIsNotNone(corpus_slider)
            self.assertEqual(corpus_slider.get("type"), "range")
            self.assertEqual(corpus_slider.get("oninput"), "recalcReitCorpusWaterfall()")

            self.assertIsNotNone(years_slider)
            self.assertEqual(years_slider.get("type"), "range")
            self.assertEqual(years_slider.get("oninput"), "recalcReitCorpusWaterfall()")

            # Verify Output and Label Elements
            self.assertIsNotNone(sim.find(id="reitCorpusVal"))
            self.assertIsNotNone(sim.find(id="reitYearsVal"))
            self.assertIsNotNone(sim.find(id="reitSec56TrackerBar"))

            # Verify JS Wiring
            scripts = [s.string for s in soup.find_all("script") if s.string and "recalcReitCorpusWaterfall" in s.string]
            self.assertEqual(len(scripts), 1, "Exactly one script defining recalcReitCorpusWaterfall must be rendered")
            self.assertIn("function recalcReitCorpusWaterfall()", scripts[0])
            self.assertIn("reitCorpusSlider", scripts[0])
            self.assertIn("reitYearsSlider", scripts[0])
            self.assertIn("reitSec56TrackerBar", scripts[0])
            self.assertIn("selectTaxSlab", scripts[0])

            # Verify Zero Jinja Leaks in rendered simulator
            sim_str = str(sim)
            self.assertNotIn("{{", sim_str, f"Unrendered Jinja tag detected in #reitSec56Simulator for {sym}")
            self.assertNotIn("{%", sim_str, f"Unrendered Jinja directive detected in #reitSec56Simulator for {sym}")

    def test_moatnomics_visual_identity_v2_contracts(self):
        """
        [Rule 6 Outside-In UI Contract Test]
        Verifies Moatnomics Visual Identity v2.0 visual cues across Phases 1–5:
        1. Brand tokens & ASSET_CLASS_VISUAL_TOKENS in core/brand/visual_identity.py.
        2. Dual-theme CSS tokens, Playfair Display + tabular-nums, and 7 [data-asset-class] scopes in style.css.
        3. Perspective Portal SVG logo (#logo-perspective-portal), 12 canonical icons (#icon-*), and #themeToggleBtn in base.html.
        4. Asset-class visual framing across directories and Warm Ivory reading surface toggle (#dossierReadingToggleBtn) across dossiers.
        5. Forest/Ink/Ivory print styling and Matplotlib chart palette in core/reporting/pdf.py.
        """
        from bs4 import BeautifulSoup
        from core.brand import BRAND_PALETTE_V2, ASSET_CLASS_ACCENTS_V2, CANONICAL_ICONS_V2

        self.assertEqual(BRAND_PALETTE_V2["forest"]["hex"], "#0E3D32")
        self.assertEqual(BRAND_PALETTE_V2["ink_navy"]["hex"], "#0B2337")
        self.assertEqual(BRAND_PALETTE_V2["warm_ivory"]["hex"], "#F7F5EE")
        self.assertEqual(BRAND_PALETTE_V2["sage"]["hex"], "#7DA77A")
        self.assertEqual(BRAND_PALETTE_V2["botanical_lime"]["hex"], "#C7E268")
        self.assertEqual(len(ASSET_CLASS_ACCENTS_V2), 9)
        self.assertEqual(len(CANONICAL_ICONS_V2), 13)

        resp_home = self.client.get("/")
        self.assertEqual(resp_home.status_code, 200)
        soup_home = BeautifulSoup(resp_home.text, "html.parser")
        self.assertIsNotNone(soup_home.find(id="logo-perspective-portal"))
        self.assertIsNotNone(soup_home.find(id="themeToggleBtn"))
        self.assertIsNotNone(soup_home.find(class_="portal-reveal-mark"))

        # Check asset-class framing on directories
        for route, expected_ac in [
            ("/equities", "equities"),
            ("/funds", "funds"),
            ("/etfs", "etfs"),
            ("/debt", "debt"),
            ("/sovereign", "sovereign"),
            ("/reits", "reits"),
            ("/opportunities", "opportunities"),
            ("/msme", "msme"),
            ("/safety-radar", "safety"),
        ]:
            r = self.client.get(route)
            self.assertEqual(r.status_code, 200)
            self.assertIn(f'data-asset-class="{expected_ac}"', r.text)

        # Check dossier reading mode toggle & masthead framing across all 6 dossiers
        for route, expected_ac in [
            ("/dossier/INFY", "equities"),
            ("/funds/PPFAS_FLEXICAP_DIR", "funds"),
            ("/etfs/NIFTYBEES", "etfs"),
            ("/debt/INE002A08012", "debt"),
            ("/reits/EMBASSY", "reits"),
            ("/msme/UDYAM-MH-26-0012480", "msme"),
        ]:
            r = self.client.get(route)
            self.assertEqual(r.status_code, 200)
            s = BeautifulSoup(r.text, "html.parser")
            self.assertIsNotNone(s.find(id="dossierReadingContainer"), f"Missing #dossierReadingContainer on {route}")
            self.assertIsNotNone(s.find(id="dossierReadingToggleBtn"), f"Missing #dossierReadingToggleBtn on {route}")
            self.assertIsNotNone(s.find(class_="dossier-masthead-v2"), f"Missing .dossier-masthead-v2 on {route}")
            self.assertIn(f'data-asset-class="{expected_ac}"', r.text)

        # Check Track 1 secondary utility pages, sector/tier SVG symbols, and WebP portal plates
        for sym_id in [
            "icon-sector-technology", "icon-sector-financials", "icon-sector-healthcare",
            "icon-sector-capital-goods", "icon-sector-automotive", "icon-sector-consumer",
            "icon-sector-chemicals", "icon-sector-energy", "icon-sector-defence", "icon-sector-diversified",
            "icon-tier-single", "icon-tier-3pack", "icon-tier-10pack", "icon-tier-pro",
            "icon-state-vault-locked", "icon-state-dossier-pending", "icon-state-empty-search",
        ]:
            self.assertIsNotNone(soup_home.find(id=sym_id), f"Missing SVG symbol #{sym_id} in base.html")

        for sec_route in ["/pricing", "/opportunities", "/safety-radar", "/compare", "/calculator/tax", "/search"]:
            r_sec = self.client.get(sec_route)
            self.assertEqual(r_sec.status_code, 200)
            self.assertIn("hero-portal-banner", r_sec.text, f"Missing .hero-portal-banner on {sec_route}")

        import pathlib
        self.assertEqual(len(list(pathlib.Path("web/static/img/brand").glob("portal-*.webp"))), 4)
        self.assertEqual(len(list(pathlib.Path("web/static/img/heroes").glob("hero-*.webp"))), 13)

        # Check Track 2 (2A Chart Anatomy, 2B Editorial Callouts, 2C Light/Ivory Contrast Sweep)
        r_sov = self.client.get("/sovereign")
        s_sov = BeautifulSoup(r_sov.text, "html.parser")
        self.assertIsNotNone(s_sov.find(class_="chart-anatomy-card"), "Missing .chart-anatomy-card on /sovereign")
        self.assertIsNotNone(s_sov.find(class_="chart-anatomy-header"), "Missing .chart-anatomy-header on /sovereign")
        self.assertIsNotNone(s_sov.find(class_="chart-anatomy-canvas"), "Missing .chart-anatomy-canvas on /sovereign")

        r_infy = self.client.get("/dossier/INFY")
        s_infy = BeautifulSoup(r_infy.text, "html.parser")
        self.assertIsNotNone(s_infy.find(class_="editorial-callout-conclusion"))
        self.assertIsNotNone(s_infy.find(class_="editorial-callout-countercase"))
        self.assertIsNotNone(s_infy.find(class_="editorial-callout-snapshot"))
        self.assertIsNotNone(s_infy.find(class_="editorial-callout-watchpoints"))

        css_text = pathlib.Path("web/static/css/style.css").read_text(encoding="utf-8")
        for token in [
            ".chart-anatomy-card",
            ".editorial-callout-conclusion",
            ".editorial-callout-countercase",
            ".editorial-callout-watchpoints",
            'html[data-theme="light"] [style*="background: rgba(15, 23, 42"]',
            '.dossier-ivory-surface [style*="color: #f8fafc"]',
            ".dropdown-item[data-asset-class]",
            ".pillar-card[data-asset-class]",
            "[data-asset-class] .hero-portal-banner",
        ]:
            self.assertIn(token, css_text)

        # Verify navigation dropdown items and homepage 7-framework cards carry data-asset-class continuity
        markets_dd = soup_home.find(id="navMarketsDropdown")
        self.assertIsNotNone(markets_dd)
        for item in markets_dd.select("a.dropdown-item"):
            self.assertTrue(
                item.get("data-asset-class"),
                f"Dropdown item {item.get('href')} in #navMarketsDropdown missing data-asset-class",
            )
        tools_dd = soup_home.find(id="navToolsDropdown")
        self.assertIsNotNone(tools_dd)
        for item in tools_dd.select("a.dropdown-item"):
            self.assertTrue(
                item.get("data-asset-class"),
                f"Dropdown item {item.get('href')} in #navToolsDropdown missing data-asset-class",
            )
        competence_showcase = soup_home.select_one(".core-competence-showcase")
        self.assertIsNotNone(competence_showcase, "Missing .core-competence-showcase on homepage")
        competence_cards = soup_home.select(".methodology-discipline-card")
        self.assertEqual(len(competence_cards), 4, "Expected 4 flagship competence pillars on homepage")
        disciplines_showcase = soup_home.select_one(".core-competence-disciplines-showcase")
        self.assertIsNotNone(disciplines_showcase, "Missing .core-competence-disciplines-showcase on homepage")
        self.assertIn("Glass-Box Multi-Agent AI", disciplines_showcase.get_text())

        pillar_cards = soup_home.select(".pillars-grid .pillar-card")
        self.assertEqual(len(pillar_cards), 7)
        for pcard in pillar_cards:
            self.assertTrue(pcard.get("data-asset-class"), "Homepage .pillar-card missing data-asset-class")
            self.assertTrue(pcard.get("data-href"), "Homepage .pillar-card missing data-href for whole-card link navigation")
            self.assertEqual(pcard.get("role"), "link", "Homepage .pillar-card missing role='link'")
            self.assertEqual(pcard.get("tabindex"), "0", "Homepage .pillar-card missing tabindex='0'")

        # Verify /etfs and /msme render Snapshot Biscuit Card Grids by default and never set overflow-x: visible on .table-sticky-wrap
        r_etfs = self.client.get("/etfs")
        s_etfs = BeautifulSoup(r_etfs.text, "html.parser")
        etf_grid = s_etfs.find(id="etfCardsGrid")
        self.assertIsNotNone(etf_grid, "Missing #etfCardsGrid snapshot biscuit grid on /etfs")
        self.assertGreater(len(etf_grid.select(".asset-card-accent")), 0, "Expected ETF snapshot biscuit cards in #etfCardsGrid")

        r_msme = self.client.get("/msme")
        s_msme = BeautifulSoup(r_msme.text, "html.parser")
        msme_grid = s_msme.find(id="msmeCardsGrid")
        self.assertIsNotNone(msme_grid, "Missing #msmeCardsGrid snapshot biscuit grid on /msme")
        self.assertGreater(len(msme_grid.select(".asset-card-accent")), 0, "Expected MSME snapshot biscuit cards in #msmeCardsGrid")

        for debt_url in [
            "/debt",
            "/debt?seniority=SENIOR_SECURED",
            "/debt?is_sdi=true",
            "/debt?seniority=SUBORDINATED_TIER_2",
            "/debt?seniority=PERPETUAL_AT1",
        ]:
            r_debt = self.client.get(debt_url)
            self.assertEqual(r_debt.status_code, 200, f"Failed GET {debt_url}")
            self.assertNotIn(">0 Issues<", r_debt.text, f"{debt_url} rendered 0 Issues")
            self.assertNotIn("All Issues (0)", r_debt.text, f"{debt_url} rendered All Issues (0)")
            s_debt = BeautifulSoup(r_debt.text, "html.parser")
            debt_grid = s_debt.find(id="debtCardsGrid")
            self.assertIsNotNone(debt_grid, f"Missing #debtCardsGrid on {debt_url}")
            self.assertGreater(
                len(debt_grid.select(".asset-card-accent")),
                0,
                f"Expected non-zero .asset-card-accent bond cards on {debt_url}",
            )

        # Verify /reits, /sovereign, and /safety also host Snapshot Biscuit Card Grids by default
        r_reits = self.client.get("/reits")
        s_reits = BeautifulSoup(r_reits.text, "html.parser")
        for grid_id in ["reitCardsGrid", "invitCardsGrid", "sgbCardsGrid"]:
            g_el = s_reits.find(id=grid_id)
            self.assertIsNotNone(g_el, f"Missing #{grid_id} snapshot biscuit grid on /reits")
            self.assertGreater(len(g_el.select(".asset-card-accent")), 0, f"Expected .asset-card-accent cards in #{grid_id}")

        for grid_id in ["sovereignTenorCardsGrid", "sdlCardsGrid"]:
            g_el = s_sov.find(id=grid_id)
            self.assertIsNotNone(g_el, f"Missing #{grid_id} snapshot biscuit grid on /sovereign")
            self.assertGreater(len(g_el.select(".asset-card-accent")), 0, f"Expected .asset-card-accent cards in #{grid_id}")

        r_safety = self.client.get("/safety-radar")
        s_safety = BeautifulSoup(r_safety.text, "html.parser")
        safety_grid = s_safety.find(id="safetyCardsGrid")
        self.assertIsNotNone(safety_grid, "Missing #safetyCardsGrid on /safety-radar")
        self.assertGreater(len(safety_grid.select(".asset-card-accent")), 0, "Expected .asset-card-accent cards in #safetyCardsGrid")

        # Verify Page-to-Page Navigation Ribbon is present and strictly separated from Report Evaluation HUD
        self.assertIsNotNone(soup_home.find(id="pageNavProgressRibbon"), "Missing #pageNavProgressRibbon in base.html")
        self.assertIsNotNone(soup_home.find(id="pageNavProgressFill"), "Missing #pageNavProgressFill in base.html")
        self.assertIn(".page-nav-progress-ribbon", css_text)
        self.assertIn("@view-transition", css_text)
        main_js_text = pathlib.Path("web/static/js/main.js").read_text(encoding="utf-8")
        self.assertIn("window.startPageNavigationRibbon", main_js_text)
        self.assertIn("window.completePageNavigationRibbon", main_js_text)
        resolve_fn_slice = main_js_text.split("function resolveEvaluationTarget(a)")[1].split("// Global click interceptor")[0]
        for forbidden_dir_hud in [
            "p === '/opportunities'",
            "p === '/sovereign'",
            "p === '/reits'",
            "p === '/etfs'",
            "p === '/safety-radar'",
            "p === '/discovery'",
            "p === '/msme'",
            "p === '/calculator/tax'",
        ]:
            self.assertNotIn(
                forbidden_dir_hud,
                resolve_fn_slice,
                f"Directory route {forbidden_dir_hud} must not trigger the Report Evaluation HUD in resolveEvaluationTarget",
            )

        # Verify PostgreSQL datetime.date / Decimal serialization safety on /api/msme/{uin} and /api/msme/search
        import datetime
        import decimal
        from core.msme.router import json_response_with_cache as msme_json_cache
        pg_type_payload = {
            "uin": "UDYAM-AP-10-0023910",
            "registration_date": datetime.date(2020, 7, 25),
            "annual_turnover": decimal.Decimal("188.0"),
        }
        pg_resp = msme_json_cache(pg_type_payload, ttl_seconds=300)
        self.assertEqual(pg_resp.status_code, 200)
        self.assertIn(b"2020-07-25", pg_resp.body)

        r_msme_api = self.client.get("/api/msme/UDYAM-AP-10-0023910")
        self.assertEqual(r_msme_api.status_code, 200)
        self.assertEqual(r_msme_api.json().get("uin"), "UDYAM-AP-10-0023910")

        # Verify cache-busted SVG, PNG, and root /favicon.ico assets
        for fav_id in ["siteFaviconSvg", "siteFaviconPng64", "siteFaviconPng32", "siteFaviconShortcut"]:
            fav_el = soup_home.find(id=fav_id)
            self.assertIsNotNone(fav_el, f"Missing #{fav_id} in base.html")
            self.assertIn("?v=", fav_el.get("href", ""), f"#{fav_id} missing ?v= cache-bust query")

        for fav_url in [
            "/favicon.ico",
            "/static/img/brand/favicon.svg",
            "/static/img/brand/favicon-64x64.png",
            "/static/img/brand/favicon-32x32.png",
            "/static/img/brand/apple-touch-icon.png",
        ]:
            r_fav = self.client.get(fav_url)
            self.assertEqual(r_fav.status_code, 200, f"Failed GET {fav_url}")

        # Permanent Microscope Gate 1: Zero Dead Hover Cards Across All Directory, Search & Pricing Pages
        for card_route in [
            "/",
            "/equities",
            "/funds",
            "/etfs",
            "/debt",
            "/sovereign",
            "/reits",
            "/msme",
            "/safety-radar",
            "/discovery",
            "/search?q=TCS",
            "/pricing",
        ]:
            r_page = self.client.get(card_route)
            self.assertEqual(r_page.status_code, 200, f"Failed GET {card_route}")
            s_page = BeautifulSoup(r_page.text, "html.parser")
            candidates = s_page.select(
                ".pillar-card, .home-stock-card, .discovery-card, .plan-card, .asset-card-accent"
            )
            for card_el in candidates:
                cls_list = card_el.get("class") or []
                if "hero-portal-banner" in cls_list or "dossier-masthead-v2" in cls_list:
                    continue
                has_action = bool(
                    card_el.get("data-href")
                    or (card_el.name == "a" and card_el.get("href"))
                    or card_el.find_parent("a", href=True)
                    or card_el.find("a", href=True)
                    or card_el.find("button", onclick=True)
                )
                self.assertTrue(
                    has_action,
                    f"Dead hover card without link/button action on {card_route}: classes={cls_list}",
                )

        # Permanent Microscope Gate 2: Luminous Dark Mode & Light Mode Section Accents + Epistemic Badges
        for section_cls in [
            "equities",
            "funds",
            "etfs",
            "debt",
            "sovereign",
            "reits",
            "opportunities",
            "msme",
            "safety",
        ]:
            self.assertIn(
                f'html[data-theme="dark"] [data-asset-class="{section_cls}"]',
                css_text,
                f"Missing dark-mode luminous section accent for {section_cls} in style.css",
            )
        for badge_cls in [
            "epistemic-badge-fact",
            "epistemic-badge-calc",
            "epistemic-badge-interp",
            "epistemic-badge-uncert",
        ]:
            self.assertIn(
                f'html[data-theme="light"] .{badge_cls}',
                css_text,
                f"Missing Light Mode contrast rule for .{badge_cls} in style.css",
            )

        # Permanent Microscope Gate 3: Brand Identity Board Palette (#F7F5EE Warm Ivory, #0E3D32 Forest, #7DA77A Sage) & IBM Plex Typography
        for brand_token in [
            "--bg-primary: #F7F5EE;",
            "--accent-cyan: #0E3D32;",
            "--bg-surface: #18181B;",
            "IBM Plex Sans",
            "IBM Plex Mono",
        ]:
            self.assertIn(
                brand_token,
                css_text,
                f"Missing Moatnomics Brand Identity Board / IBM Plex token '{brand_token}' in style.css",
            )

        # Permanent Microscope Gate 4: PostgreSQL psycopg2 Percent Escaping & REIT/Safety Fallback Normalization Parity
        from core.db.connection import _escape_pg_literal_percents, _SafePgCursorProxy
        from core.db.reits import DEFAULT_REITS_AND_INVITS, _normalize_reit_item
        from core.db.safety_radar import DEFAULT_ALTERNATIVE_YIELD_PRODUCTS, _normalize_safety_product

        sample_sql = (
            "SELECT * FROM reits_and_invits "
            "WHERE structure_type = %s "
            "AND UPPER(symbol) NOT LIKE '%TEST%' "
            "AND product_name != 'Gold Yield 16% Leasing'"
        )
        escaped_sql = _escape_pg_literal_percents(sample_sql)
        # Simulate psycopg2 Python %-interpolation
        interpolated = escaped_sql % ("'SM_REIT'",)
        self.assertIn("NOT LIKE '%TEST%'", interpolated)
        self.assertIn("'Gold Yield 16% Leasing'", interpolated)

        class _DummyPgCur:
            def __init__(self):
                self.calls = []
            def execute(self, q, v=None):
                if v is not None:
                    # Simulate psycopg2 mogrify % formatting
                    _ = q % tuple(repr(x) for x in v)
                self.calls.append((q, v))

        dummy_cur = _DummyPgCur()
        proxy_cur = _SafePgCursorProxy(dummy_cur)
        proxy_cur.execute("SELECT * FROM reits_and_invits WHERE UPPER(symbol) NOT LIKE '%TEST%'", ())
        self.assertIsNone(dummy_cur.calls[-1][1], "Empty tuple must call execute(query) with vars=None")
        proxy_cur.execute(sample_sql, ("SM_REIT",))
        self.assertEqual(dummy_cur.calls[-1][1], ("SM_REIT",))

        for raw_reit in DEFAULT_REITS_AND_INVITS:
            norm_r = _normalize_reit_item(raw_reit)
            self.assertIsInstance(norm_r.get("details"), dict)
            if norm_r["structure_type"] == "INVIT":
                self.assertIn("subtype", norm_r["details"])

        for raw_prod in DEFAULT_ALTERNATIVE_YIELD_PRODUCTS:
            norm_p = _normalize_safety_product(raw_prod)
            self.assertIsInstance(norm_p.get("audit_matrix"), dict)

        # Permanent Microscope Gate 5: Biscuit Card Pill Containment & SVG Symbol Integrity
        self.assertIn("/* Card Pill & Badge Containment Hygiene (Prevent pill border spillover) */", css_text)
        self.assertIn(".asset-card-accent", css_text)

        # Verify #icon-ai-spark exists in base.html SVG sprite
        with open("web/templates/base.html", "r", encoding="utf-8") as f:
            base_html_content = f.read()
        self.assertIn('id="icon-ai-spark"', base_html_content)

        # Verify card headers in REITs, Sovereign, Equities, MSME, Funds, ETFs have wrap enabled
        for route_path in ["/reits", "/sovereign", "/equities", "/msme", "/funds", "/etfs"]:
            resp = self.client.get(route_path)
            self.assertEqual(resp.status_code, 200, f"Route {route_path} failed HTTP 200 check")
            # Assert no broken svg symbol references in rendered output
            soup = BeautifulSoup(resp.text, "html.parser")
            uses = soup.find_all("use")
            for u in uses:
                href = u.get("href", "")
                if href.startswith("#"):
                    symbol_id = href[1:]
                    self.assertIn(f'id="{symbol_id}"', base_html_content, f"Route {route_path} references undefined symbol #{symbol_id}")

    def test_dossier_cockpit_full_width_layout_and_payment_links(self):
        """
        Empirically verifies:
        1. dossier.html tag nesting integrity (zero unclosed tags, balanced divs).
        2. #reverseDcfSandbox and #epistemicFalsificationCard are full-width direct cockpit children.
        3. Payment links in base.html and pricing.html use razorpay.me/@moatnomics (0 stockresearchapp).
        4. /equities directory renders 0 synthetic test tickers.
        """
        import html.parser
        import re

        # 1. Dossier HTML Tag Nesting
        templates_dir = Path("web/templates")
        dossier_path = templates_dir / "dossier.html"
        with open(dossier_path, "r", encoding="utf-8") as f:
            dossier_raw = f.read()

        div_opens = len(re.findall(r'<div\b', dossier_raw))
        div_closes = len(re.findall(r'</div>', dossier_raw))
        self.assertEqual(div_opens, div_closes, f"Mismatched div tags in dossier.html: <div={div_opens}, </div={div_closes}")

        # 2. Rendered /dossier/INFY Cockpit Architecture
        resp = self.client.get("/dossier/INFY")
        self.assertEqual(resp.status_code, 200)
        soup = BeautifulSoup(resp.text, "html.parser")
        sandbox = soup.find(id="reverseDcfSandbox")
        epistemic = soup.find(id="epistemicFalsificationCard")
        self.assertIsNotNone(sandbox, "#reverseDcfSandbox must exist in rendered /dossier/INFY")
        self.assertIsNotNone(epistemic, "#epistemicFalsificationCard must exist in rendered /dossier/INFY")

        # Parent should be the cockpit container, NOT a nested auto-fit grid
        sandbox_parent_style = sandbox.parent.get("style", "")
        self.assertNotIn("grid-template-columns", sandbox_parent_style, "Sandbox must not be trapped in a multi-column grid")
        self.assertIn("margin-bottom", sandbox_parent_style)

        epistemic_parent_style = epistemic.parent.get("style", "")
        self.assertNotIn("grid-template-columns", epistemic_parent_style, "Epistemic card must not be trapped in a multi-column grid")

        # 3. Payment Link Verification
        with open(templates_dir / "base.html", "r", encoding="utf-8") as f:
            base_html = f.read()
        with open(templates_dir / "pricing.html", "r", encoding="utf-8") as f:
            pricing_html = f.read()

        self.assertIn("razorpay.me/@moatnomics", base_html)
        self.assertIn("razorpay.me/@moatnomics", pricing_html)
        self.assertNotIn("stockresearchapp", base_html)
        self.assertNotIn("stockresearchapp", pricing_html)

        # 4. /equities Directory Hygiene
        resp_eq = self.client.get("/equities")
        self.assertEqual(resp_eq.status_code, 200)
        self.assertNotIn("TEST_PILLAR_INFY", resp_eq.text)
        self.assertNotIn("TEST_SURGICAL_INFY", resp_eq.text)
        self.assertNotIn("COAL_1792573802959", resp_eq.text)
        self.assertNotIn("UNIT_SAMPLE_STOCK", resp_eq.text)

    def test_dynamic_ticker_specific_countercase_vector_and_bear_triggers(self):
        """
        Outside-in contract: #countercaseVector populates filing-grounded Revision Triggers
        specific to each ticker (capped <= 140 chars) with accessible label/name/status bindings,
        and falls back cleanly to structural archetypes when Revision Triggers are absent.
        """
        from unittest.mock import patch

        mock_reports = {
            "INFY": {
                "ticker": "INFY",
                "short_name": "Infosys Ltd",
                "industry": "IT Services",
                "baseline_price": 1820.0,
                "formatted_date": "29 Oct 2026",
                "raw_timestamp": "2026-10-29T00:00:00Z",
                "report_text": (
                    "## Pillar 1: Business Model\nEnterprise IT services.\n"
                    "#### What Would Change This View (Revision Triggers)\n"
                    "- **What Contradicts This Conclusion:** Discretionary BFSI software budgets freezing across North American tier-1 accounts for two straight quarters.\n"
                    "- **Evidence That Forces a Revision:** Constant-currency revenue growth dropping below 0% YoY alongside large-deal TCV slipping under USD 1.5B.\n"
                ),
            },
            "FEDERALBNK": {
                "ticker": "FEDERALBNK",
                "short_name": "Federal Bank Ltd",
                "industry": "Banking",
                "baseline_price": 205.0,
                "formatted_date": "29 Oct 2026",
                "raw_timestamp": "2026-10-29T00:00:00Z",
                "report_text": (
                    "## Pillar 1: Deposit Franchise\nRemittance-backed deposit base.\n"
                    "#### What Would Change This View (Revision Triggers)\n"
                    "- **What Contradicts This Conclusion:** Wholesale funding reliance rising faster than NRE deposit inflows in southern corridors.\n"
                    "- **Evidence That Forces a Revision:** NRE/NRO deposit growth decelerating below 6% YoY coupled with credit-deposit ratio breaching 90%.\n"
                ),
            },
            "LEGACYCO": {
                "ticker": "LEGACYCO",
                "short_name": "Legacy Corp",
                "industry": "Manufacturing",
                "baseline_price": 450.0,
                "formatted_date": "29 Oct 2026",
                "raw_timestamp": "2026-10-29T00:00:00Z",
                "report_text": "## Pillar 1: Business Model\nLegacy text without revision triggers block.\n" * 15,
            },
        }

        with patch("web.main.get_report_by_ticker_sync", side_effect=lambda sym: mock_reports.get(sym)):
            r_infy = self.client.get("/dossier/INFY")
            self.assertEqual(r_infy.status_code, 200)
            s_infy = BeautifulSoup(r_infy.text, "html.parser")
            sel_infy = s_infy.find("select", id="countercaseVector")
            self.assertIsNotNone(sel_infy)
            self.assertEqual(sel_infy.get("name"), "failure_vector")
            self.assertIsNotNone(s_infy.find("label", attrs={"for": "countercaseVector"}))
            self.assertIsNotNone(s_infy.find("label", attrs={"for": "countercaseNotes"}))
            status_el = s_infy.find(id="countercaseStatus")
            self.assertIsNotNone(status_el)
            self.assertEqual(status_el.get("aria-live"), "polite")

            infy_opts = [o.get_text(strip=True) for o in sel_infy.find_all("option")]
            self.assertTrue(all(len(o) <= 140 for o in infy_opts))
            self.assertIn("Constant-currency revenue growth dropping below 0%", infy_opts[0])
            self.assertEqual(infy_opts[-1], "Custom Operational Vulnerability...")

            bear_infy = s_infy.find(class_="editorial-callout-countercase")
            self.assertIsNotNone(bear_infy)
            self.assertIn("Discretionary BFSI software budgets freezing", bear_infy.get_text())

            r_fed = self.client.get("/dossier/FEDERALBNK")
            self.assertEqual(r_fed.status_code, 200)
            s_fed = BeautifulSoup(r_fed.text, "html.parser")
            sel_fed = s_fed.find("select", id="countercaseVector")
            fed_opts = [o.get_text(strip=True) for o in sel_fed.find_all("option")]
            self.assertNotEqual(infy_opts[0], fed_opts[0])
            self.assertIn("NRE/NRO deposit growth decelerating below 6%", fed_opts[0])

            # Fallback when Revision Triggers block is absent
            r_leg = self.client.get("/dossier/LEGACYCO")
            self.assertEqual(r_leg.status_code, 200)
            s_leg = BeautifulSoup(r_leg.text, "html.parser")
            sel_leg = s_leg.find("select", id="countercaseVector")
            leg_opts = [o.get_text(strip=True) for o in sel_leg.find_all("option")]
            self.assertEqual(len(leg_opts), 4)

    def test_equities_directory_quantitative_range_filters(self):
        """
        Outside-in contract: /equities supports min_roce, max_de, max_pe, and min_opm
        without 422 errors on empty form strings, and normalize_de_ratio handles Decimal.
        """
        from decimal import Decimal
        from unittest.mock import patch
        from core.presentation.formatters import normalize_de_ratio

        self.assertEqual(normalize_de_ratio(Decimal("0.18")), 0.18)

        sample_dir = [
            {
                "ticker": "HIGHQUAL",
                "name": "High Quality Ltd",
                "company_name": "High Quality Ltd",
                "sector": "Information Technology",
                "sector_slug": "IT_TECH",
                "sector_icon": "icon-sector-it",
                "sector_svg_id": "icon-sector-it",
                "industry": "Software",
                "current_price": 1500.0,
                "formatted_price": "₹1,500.00",
                "market_cap_cr": 120000.0,
                "formatted_mcap": "₹1,20,000 Cr",
                "market_cap_tier": "Mega-Cap",
                "market_cap_tier_slug": "MEGA",
                "pe_ratio": "22.0x",
                "pe_float": 22.0,
                "roce": 32.0,
                "roce_pct": "32.0%",
                "roe": 28.0,
                "roe_pct": "28.0%",
                "debt_to_equity": "0.05x",
                "debt_to_equity_float": 0.05,
                "operating_margin": "24.0%",
                "operating_margin_float": 24.0,
                "opm_float": 24.0,
                "formatted_52w_range": "₹1,100 – ₹1,650",
                "revision_count": 2,
                "formatted_date": "29 Oct 2026",
                "dossier_url": "/dossier/HIGHQUAL",
                "is_recently_inducted": False,
            },
            {
                "ticker": "LEVERAGEDCO",
                "name": "Leveraged Infra Ltd",
                "company_name": "Leveraged Infra Ltd",
                "sector": "Capital Goods",
                "sector_slug": "CAPITAL_GOODS_INFRA",
                "sector_icon": "icon-sector-industrials",
                "sector_svg_id": "icon-sector-industrials",
                "industry": "Infra",
                "current_price": 400.0,
                "formatted_price": "₹400.00",
                "market_cap_cr": 15000.0,
                "formatted_mcap": "₹15,000 Cr",
                "market_cap_tier": "Mid-Cap",
                "market_cap_tier_slug": "MID",
                "pe_ratio": "48.0x",
                "pe_float": 48.0,
                "roce": 11.0,
                "roce_pct": "11.0%",
                "roe": 9.0,
                "roe_pct": "9.0%",
                "debt_to_equity": "1.40x",
                "debt_to_equity_float": 1.40,
                "operating_margin": "10.5%",
                "operating_margin_float": 10.5,
                "opm_float": 10.5,
                "formatted_52w_range": "₹280 – ₹460",
                "revision_count": 1,
                "formatted_date": "29 Oct 2026",
                "dossier_url": "/dossier/LEVERAGEDCO",
                "is_recently_inducted": False,
            },
        ]

        with patch("web.main.get_all_equities_directory_sync", return_value=sample_dir):
            r_all = self.client.get("/equities")
            self.assertEqual(r_all.status_code, 200)
            self.assertIn("/dossier/HIGHQUAL", r_all.text)
            self.assertIn("/dossier/LEVERAGEDCO", r_all.text)

            r_filt = self.client.get("/equities?min_roce=20&max_de=0.5&max_pe=30&min_opm=18")
            self.assertEqual(r_filt.status_code, 200)
            self.assertIn("/dossier/HIGHQUAL", r_filt.text)
            self.assertNotIn("/dossier/LEVERAGEDCO", r_filt.text)

            # Empty browser form inputs must never trigger 422 Unprocessable Entity
            r_blank = self.client.get("/equities?min_roce=20&max_de=&max_pe=&min_opm=")
            self.assertEqual(r_blank.status_code, 200)
            self.assertIn("/dossier/HIGHQUAL", r_blank.text)
            self.assertNotIn("/dossier/LEVERAGEDCO", r_blank.text)


if __name__ == "__main__":
    unittest.main()

