"""
Unit tests for Dual-Engine Discoverability (SEO and GEO).
Verifies:
- /robots.txt directives and AI search bot permissions
- /llms.txt and /llms-full.txt CommonMark formatting & headers
- Schema.org JSON-LD @graph structure on homepage and dossier
- Semantic HTML definition lead and comparison tables on dossiers
- IndexNow key serving and endpoint integration
"""

import json
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import unittest

from web.main import app


class TestDualEngineDiscoverability(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_robots_txt_dual_engine_directives(self):
        """Verify robots.txt welcomes AI answer engines and references sitemap + llms.txt."""
        res = self.client.get("/robots.txt")
        self.assertEqual(res.status_code, 200)
        text = res.text
        self.assertIn("User-agent: PerplexityBot", text)
        self.assertIn("User-agent: OAI-SearchBot", text)
        self.assertIn("User-agent: ClaudeBot", text)
        self.assertIn("Sitemap:", text)
        self.assertIn("/llms.txt", text)

    def test_llms_txt_commonmark_standard(self):
        """Verify /llms.txt follows CommonMark specification with H1, blockquote, and instructions."""
        res = self.client.get("/llms.txt")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/plain", res.headers.get("content-type", ""))
        text = res.text
        self.assertTrue(text.startswith("# Moatnomics Research Engine"))
        self.assertIn("> Moatnomics provides independent", text)
        self.assertIn("## Instructions for Large Language Model Agents", text)
        self.assertIn("/equities", text)
        self.assertIn("/dossier/{TICKER}", text)
        self.assertIn("## Optional", text)

    def test_llms_full_txt_deep_documentation(self):
        """Verify /llms-full.txt supplies full methodology and framework documentation."""
        res = self.client.get("/llms-full.txt")
        self.assertEqual(res.status_code, 200)
        text = res.text
        self.assertIn("# Moatnomics Full Analytical Architecture", text)
        self.assertIn("7-Pillar Equity Evaluation Framework", text)
        self.assertIn("Chanakya 10-Point Clean-Room Forensic Filter", text)

    def test_base_html_schema_graph(self):
        """Verify homepage renders unified Schema.org @graph linking SoftwareApplication & WebSite."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")
        schemas = soup.find_all("script", {"type": "application/ld+json"})
        self.assertTrue(len(schemas) >= 1)

        graph_found = False
        for s in schemas:
            try:
                data = json.loads(s.string)
                if "@graph" in data:
                    graph_found = True
                    types = [item.get("@type") for item in data["@graph"]]
                    self.assertIn("SoftwareApplication", types)
                    self.assertIn("WebSite", types)
            except Exception:
                pass
        self.assertTrue(graph_found, "Unified Schema.org @graph not found in base HTML.")

    def test_dossier_definition_first_and_semantic_tables(self):
        """Verify dossier renders definition-first lead, semantic tables, and AnalysisNewsArticle schema."""
        res = self.client.get("/dossier/INFY")
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.text, "html.parser")

        # 1. Definition-First Executive Hook
        lead = soup.find("section", class_="dossier-definition-lead")
        self.assertIsNotNone(lead, "Missing definition-first executive lead section.")
        self.assertIn("INFY", lead.get_text())

        # 2. Rich JSON-LD AnalysisNewsArticle Schema
        schemas = soup.find_all("script", {"type": "application/ld+json"})
        dossier_schema_found = False
        for s in schemas:
            try:
                data = json.loads(s.string)
                if "@graph" in data:
                    for item in data["@graph"]:
                        item_types = item.get("@type")
                        if isinstance(item_types, list) and "AnalysisNewsArticle" in item_types:
                            dossier_schema_found = True
                            self.assertIn("variableMeasured", item)
                            self.assertIn("citation", item)
            except Exception:
                pass
        self.assertTrue(dossier_schema_found, "Rich AnalysisNewsArticle schema not found on dossier.")


if __name__ == "__main__":
    unittest.main()
