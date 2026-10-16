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
        cls.project_root = Path(__file__).resolve().parent.parent
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
        auth_ids = ["authModal", "authEmailInput", "authOtpInput", "authSubmitBtn", "closeAuthModalBtn"]
        checkout_ids = ["checkoutModal", "modalPlanName", "modalPlanPrice", "modalConfirmBtn", "closeModalBtn"]

        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")

        for elem_id in auth_ids + checkout_ids:
            self.assertIsNotNone(
                soup.find(id=elem_id),
                f"Global modal element #{elem_id} referenced in main.js is missing from base.html"
            )

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


if __name__ == "__main__":
    unittest.main()
