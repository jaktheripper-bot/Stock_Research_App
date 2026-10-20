"""Brand voice contracts (Track 3): AI call sites must carry the brand context, and retired wording must not return.

These are static source/DOM checks, so they run fast and never call a live AI provider.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AI_CALL = re.compile(r"genai\.Client\(|\.generate_content\(|generate_content_stream\(")

# Wording retired in Track 3. Matching is on visible/prompt text, so identifiers (snake_case, camelCase) are not matched.
RETIRED_VISIBLE = [
    "Audit the Asset",
    "Protect the Allocator",
    "Stock Research" + " App",
    "Fiduciary",
    "Wealth Destruction",
    "zero-hallucination",
    "Pre-Mortem Inversion",
    "What Shocked You",
    "Forensic Intelligence Desk",
]
# Audit tooling and the brand lexicon legitimately name the retired terms (rules, forbidden lists, history).
ALLOWED_FILES = {
    "core/brand/moatnomics_house.py",
    "core/audit/tools.py",
    "scripts/verify_reality_audit.py",
    "scripts/ai_auditor.py",
    "scripts/dump_conversation.py",
}


def _py_files(*roots):
    for r in roots:
        for p in (ROOT / r).rglob("*.py"):
            if "__pycache__" not in p.parts:
                yield p


class TestAiCallSitesCarryBrandContext(unittest.TestCase):
    def test_every_ai_call_site_imports_brand_context(self):
        offenders = []
        for p in _py_files("core", "web"):
            src = p.read_text(encoding="utf-8", errors="ignore")
            if AI_CALL.search(src) and "get_system_prompt_context" not in src and "MASTER_AI_PROMPT" not in src:
                offenders.append(str(p.relative_to(ROOT)))
        self.assertEqual(offenders, [], f"AI call sites missing brand voice context: {offenders}")


class TestRetiredWordingStaysRetired(unittest.TestCase):
    def test_no_retired_wording_in_site_templates_and_scripts(self):
        hits = []
        files = list((ROOT / "web" / "templates").rglob("*.html")) + list((ROOT / "web" / "static" / "js").glob("*.js"))
        for p in files:
            text = p.read_text(encoding="utf-8", errors="ignore")
            for term in RETIRED_VISIBLE:
                if term in text:
                    hits.append(f"{p.relative_to(ROOT)}: {term}")
        self.assertEqual(hits, [], f"Retired wording found on the site: {hits}")

    def test_no_retired_wording_in_backend_text(self):
        hits = []
        for p in _py_files("core", "web"):
            rel = str(p.relative_to(ROOT))
            if rel in ALLOWED_FILES or rel.startswith("core/audit/"):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for term in RETIRED_VISIBLE:
                if term in text:
                    hits.append(f"{rel}: {term}")
        self.assertEqual(hits, [], f"Retired wording found in backend text: {hits}")


class TestSocialAndTouchIconWiring(unittest.TestCase):
    """Outside-in: the rendered <head> points at real, absolute, reachable brand images."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from bs4 import BeautifulSoup
        from web.main import app
        cls.client = TestClient(app)
        cls.soup = BeautifulSoup(cls.client.get("/").text, "html.parser")

    def _meta(self, **attrs):
        tag = self.soup.find("meta", attrs=attrs)
        self.assertIsNotNone(tag, f"missing <meta {attrs}>")
        return tag.get("content", "")

    def test_og_and_twitter_image_are_absolute_and_reachable(self):
        for content in (self._meta(property="og:image"), self._meta(name="twitter:image")):
            self.assertTrue(content.startswith("https://"), content)
            self.assertNotIn("{{", content)
            path = "/" + content.split("/", 3)[3]
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertTrue(self._meta(property="og:image:alt"))

    def test_apple_touch_icon_is_linked_and_reachable(self):
        link = self.soup.find("link", rel="apple-touch-icon")
        self.assertIsNotNone(link)
        self.assertEqual(self.client.get(link["href"]).status_code, 200)

    def test_unused_legacy_glyph_removed(self):
        self.assertNotIn("glyph-castle", self.client.get("/").text)


if __name__ == "__main__":
    unittest.main()
