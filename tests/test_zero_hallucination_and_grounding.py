"""
tests/test_zero_hallucination_and_grounding.py
==============================================================================
Zero-Hallucination & Anti-Fabrication Test Suite.
Enforces that templates, legal content, codebases, and public UI strings
strictly adhere to verified project facts established in user directives:

1. Zero Corporate Entity Hallucinations (No claims of registered operating entity).
2. Zero Tax/Service Code Hallucinations (No claims of SAC 998314 or fake GST classifications).
3. Zero Physical Office Address Hallucinations (No Indiranagar / 100 Feet Road / 560038).
4. Zero Public Email / Mailto Hallucinations (No support@stockresearch.app, grievance@..., etc.).
5. Zero Phone Number / Hotline Hallucinations (No fake +91 numbers or WhatsApp desks).
6. Author Name Placeholder Hygiene (No 'Lyndon Pinto' in UI placeholders or form examples).
7. Pure On-Site Feedback Mandate (Inquiries & complaints strictly routed via /contact).
8. SEBI Safe-Harbor Affirmation (Explicit disclaimer that platform is NOT registered under SEBI).
==============================================================================
"""

import os
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "web" / "templates"
LEGAL_FILE = PROJECT_ROOT / "web" / "legal_content.py"
CORE_DIR = PROJECT_ROOT / "core"


class TestZeroHallucinationAndGrounding(unittest.TestCase):
    """Regression test suite enforcing zero hallucination of contact, entity, or address details."""

    def setUp(self):
        self.template_files = []
        for root, _, files in os.walk(TEMPLATES_DIR):
            for f in files:
                if f.endswith((".html", ".jinja2")):
                    self.template_files.append(Path(root) / f)

        self.assertTrue(len(self.template_files) > 0, "Expected web templates to be found for scanning.")
        self.assertTrue(LEGAL_FILE.exists(), "Expected web/legal_content.py to exist.")

    def test_no_hallucinated_physical_addresses(self):
        """Ensures no hallucinated physical office locations (Indiranagar, 100 Feet Road, 560038) exist."""
        forbidden_address_patterns = [
            r"Indiranagar",
            r"100\s*Feet\s*Road",
            r"560038",
            r"Operational\s*Office:",
            r"Operational\s*Address:"
        ]

        scanned = self.template_files + [LEGAL_FILE]
        violations = []

        for fpath in scanned:
            content = fpath.read_text(encoding="utf-8")
            for pat in forbidden_address_patterns:
                matches = re.findall(pat, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{fpath.name} matched pattern '{pat}' ({len(matches)} occurrence(s))")

        self.assertEqual(
            violations, [],
            f"Found hallucinated physical office address details in codebase:\n" + "\n".join(violations)
        )

    def test_no_hallucinated_corporate_service_codes(self):
        """Ensures no hallucinated GST SAC codes (998314) exist in public templates or legal policies."""
        forbidden_sac_patterns = [
            r"SAC\s*(?:Code)?[:\s]*998314",
            r"\b998314\b",
        ]

        scanned = self.template_files + [LEGAL_FILE]
        violations = []

        for fpath in scanned:
            content = fpath.read_text(encoding="utf-8")
            for pat in forbidden_sac_patterns:
                matches = re.findall(pat, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{fpath.name} matched pattern '{pat}' ({len(matches)} occurrence(s))")

        self.assertEqual(
            violations, [],
            f"Found hallucinated SAC / GST service codes in public templates or legal policies:\n" + "\n".join(violations)
        )

    def test_no_hallucinated_registered_operating_entity_claims(self):
        """Ensures the app does not imply or claim to be a registered corporate operating entity."""
        forbidden_entity_patterns = [
            r"Registered\s+Operating\s+Entity",
            r"Entity\s*Name:\s*Stock\s*Research\s*App",
            r"Entity:\s*Stock\s*Research\s*App\s*/\s*Equity\s*Research\s*AI",
            r"Corporate\s*Entity:",
        ]

        scanned = self.template_files + [LEGAL_FILE]
        violations = []

        for fpath in scanned:
            content = fpath.read_text(encoding="utf-8")
            for pat in forbidden_entity_patterns:
                matches = re.findall(pat, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{fpath.name} matched pattern '{pat}' ({len(matches)} occurrence(s))")

        self.assertEqual(
            violations, [],
            f"Found hallucinated corporate entity declarations in public files:\n" + "\n".join(violations)
        )

    def test_no_hallucinated_public_support_emails(self):
        """Ensures no ungrounded public support emails or mailto links exist on the site."""
        forbidden_email_patterns = [
            r"support@stockresearch\.app",
            r"grievance@stockresearch\.app",
            r"privacy@stockresearch\.app",
            r"support@stockresearch\.ai",
            r"mailto:",
        ]

        # Scan all templates and legal files. Exclude admin.html which contains the whitelisted root owner email.
        scanned = [f for f in self.template_files if f.name != "admin.html"] + [LEGAL_FILE]
        violations = []

        for fpath in scanned:
            content = fpath.read_text(encoding="utf-8")
            for pat in forbidden_email_patterns:
                matches = re.findall(pat, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{fpath.name} matched pattern '{pat}' ({len(matches)} occurrence(s))")

        self.assertEqual(
            violations, [],
            f"Found hallucinated public email addresses or mailto links on the site:\n" + "\n".join(violations)
        )

    def test_no_hallucinated_phone_numbers(self):
        """Ensures no fake phone numbers, customer support hotlines, or WhatsApp desks are listed."""
        forbidden_phone_patterns = [
            r"\+91\s*98450",
            r"Support\s*Hotline",
            r"WhatsApp:\s*\+91",
            r"Direct\s*Phone:",
        ]

        scanned = self.template_files + [LEGAL_FILE]
        violations = []

        for fpath in scanned:
            content = fpath.read_text(encoding="utf-8")
            for pat in forbidden_phone_patterns:
                matches = re.findall(pat, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{fpath.name} matched pattern '{pat}' ({len(matches)} occurrence(s))")

        self.assertEqual(
            violations, [],
            f"Found hallucinated phone numbers or hotline descriptions:\n" + "\n".join(violations)
        )

    def test_personal_name_placeholder_hygiene(self):
        """Ensures the author's personal name ('Lyndon Pinto') is NEVER featured in UI placeholders or examples."""
        # Check all public templates (excluding internal admin auth login which validates the root owner account)
        public_templates = [f for f in self.template_files if f.name != "admin.html"]
        violations = []

        for fpath in public_templates:
            content = fpath.read_text(encoding="utf-8")
            # Look for Lyndon Pinto as placeholder or example text
            if re.search(r"placeholder=[\"'].*Lyndon.*[\"']", content, re.IGNORECASE) or \
               re.search(r"e\.g\.,?\s*Lyndon", content, re.IGNORECASE):
                violations.append(f"{fpath.name} features 'Lyndon' in a placeholder or form example.")

        self.assertEqual(
            violations, [],
            f"Personal name hygiene violation found in UI templates:\n" + "\n".join(violations)
        )

    def test_sebi_safe_harbor_not_registered_affirmation(self):
        """Validates that statutory disclaimers explicitly affirm the platform is NOT registered under SEBI."""
        from core.db.compliance import MANDATORY_SEBI_DISCLAIMER
        from web.legal_content import POLICIES

        # Must explicitly affirm non-registration
        self.assertIn(
            "NOT registered as a Research Analyst or Investment Adviser",
            MANDATORY_SEBI_DISCLAIMER,
            "Mandatory SEBI disclaimer must explicitly state that the platform is not registered."
        )

        terms_content = POLICIES.get("terms", {}).get("content_html", "")
        self.assertIn(
            "Neither the Platform nor its operators are registered as Research Analysts",
            terms_content,
            "Terms of Service must clearly disclaim SEBI Research Analyst registration."
        )

    def test_contact_form_routes_to_on_site_management_console(self):
        """Ensures contact page and legal policies guide users strictly to the on-site form (/contact)."""
        contact_tmpl = TEMPLATES_DIR / "contact.html"
        self.assertTrue(contact_tmpl.exists())
        contact_text = contact_tmpl.read_text(encoding="utf-8")

        # Form must submit to /contact
        self.assertIn('action="/contact"', contact_text)
        self.assertIn('method="POST"', contact_text)

        # Must describe review by administration console
        self.assertIn("Admin Desk Review", contact_text)


if __name__ == "__main__":
    unittest.main()
