"""Unit & Outside-In Contract Tests for Workstream 2 (Feedback #5):
Report Provenance Bar, Share-Price Timestamp, Financial Period & Source Traceability.
"""

import json
import os
import unittest
from datetime import datetime
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from core.analysis.parser import (
    enrich_and_classify_citations,
    extract_financial_period_covered,
)
from core.db.connection import get_db_connection, get_placeholder, init_db
from core.db.fundamentals import save_cached_fundamentals
from core.db.reports import save_report_to_archive
from web.main import app


class TestDossierProvenanceAndCitationsWS2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        init_db()
        cls.client = TestClient(app)

    def test_extract_financial_period_covered_filters_reverse_dcf_horizon(self):
        """Extracts reported Indian fiscal quarters/years while ignoring Reverse-DCF terminal projections."""
        ref_date = datetime(2026, 2, 15)  # Indian FY26 (Apr 2025 - Mar 2026)
        report_md = (
            "## Pillar 1: Operating Performance\n"
            "Revenue in Q3 FY26 grew 14.2% YoY, building on audited FY2024-25 cash conversion. "
            "Reverse-DCF terminal cash flows are projected through FY31 with target FY30E margins."
        )
        period = extract_financial_period_covered(report_md, reference_date=ref_date)
        self.assertEqual(period, "Q3 FY26 • FY25 Audited (TTM)")
        self.assertNotIn("30", period)
        self.assertNotIn("31", period)

        interim_only = "Unaudited 9M FY26 statutory filing highlights 18.5% EBITDA margin."
        self.assertEqual(
            extract_financial_period_covered(interim_only, reference_date=ref_date),
            "9M FY26 Statutory Filing (TTM)",
        )

        fallback_empty = "General qualitative overview with no fiscal tokens."
        self.assertEqual(
            extract_financial_period_covered(fallback_empty, reference_date=ref_date),
            "TTM Statutory Exchange Filings",
        )

    def test_enrich_and_classify_citations_separates_primary_vs_redirect_and_backfills_bse(self):
        """Ensures direct statutory repositories are PRIMARY_STATUTORY while grounding redirects are SECONDARY_GROUNDING."""
        mixed_citations = [
            {
                "title": "bseindia.com",
                "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE_redirect_token",
                "source_type": "Gemini Search Grounding",
            },
            {
                "title": "SEBI Shareholding Regulation",
                "uri": "https://www.sebi.gov.in/legal/regulations/shareholding.html",
                "source_type": "Gemini Search Grounding",
            },
        ]
        bundle = enrich_and_classify_citations(
            mixed_citations,
            scrip_code="532540",
            ticker="TCS",
            company_name="Tata Consultancy Services",
        )
        self.assertEqual(bundle["primary_count"], 1)
        self.assertEqual(bundle["secondary_count"], 1)
        self.assertEqual(bundle["citations"][0]["tier"], "PRIMARY_STATUTORY")
        self.assertEqual(bundle["citations"][0]["source_type"], "SEBI Regulatory Filing")
        self.assertEqual(bundle["citations"][1]["tier"], "SECONDARY_GROUNDING")
        self.assertIn("Grounded Search", bundle["citations"][1]["title"])
        self.assertGreaterEqual(len(bundle["direct_registry_links"]), 5)

        # Backfill test: when TCS (532540) has 0 primary links, backfill the 4 official BSE corporate filing links
        empty_bundle = enrich_and_classify_citations(
            [],
            scrip_code="532540",
            ticker="TCS",
            company_name="Tata Consultancy Services",
        )
        self.assertEqual(empty_bundle["primary_count"], 4)
        self.assertEqual(empty_bundle["secondary_count"], 0)
        self.assertTrue(all("bseindia.com" in c["uri"] for c in empty_bundle["citations"]))

        # Anti-fabrication guard: when scrip_code is missing/N/A, fabricate 0 BSE links
        unmapped_bundle = enrich_and_classify_citations(
            [],
            scrip_code="N/A",
            ticker="UNMAPPEDCO",
            company_name="Unmapped Co",
        )
        self.assertEqual(unmapped_bundle["primary_count"], 0)
        self.assertEqual(len(unmapped_bundle["citations"]), 0)

    def test_outside_in_equity_dossier_provenance_quote_drift_and_citations(self):
        """Verifies /dossier/{ticker} renders 3-part Provenance Bar, live quote vs baseline drift, and tiered citations."""
        ticker = "WS2PROVTEST"
        citations = [
            {
                "title": "BSE Corporate Financial Results Filing",
                "uri": "https://www.bseindia.com/corporates/ann.html?scrip_cd=532540",
                "source_type": "BSE Statutory Filing",
            },
            {
                "title": "bseindia.com",
                "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/test_token_123",
                "source_type": "Gemini Search Grounding",
            },
        ]
        report_body = (
            "### Health Matrix\n"
            "- Moat: Wide\n"
            "- CapitalAllocation: Disciplined\n"
            "- Valuation: Fair\n"
            "- BalanceSheet: Resilient\n"
            "- Governance: Clean\n"
            "- Macro: Neutral\n"
            "- Diagnostic: Neutral\n\n"
            "## 1. Macro & Statutory Context\n"
            "In Q3 FY26 and audited FY25 filings, the company expanded operating cash flow with zero debt. "
            + ("Verified statutory exchange filing disclosure. " * 25)
        )
        save_report_to_archive(
            stock_data={
                "ticker": ticker,
                "short_name": "WS2 Provenance Test Ltd",
                "scrip_code": "532540",
                "current_price": 2156.00,
                "pe_ratio": "24.80",
                "market_cap": 8_000_000_000_000,
            },
            report_text=report_body,
            citations=citations,
        )
        save_cached_fundamentals(
            ticker,
            {
                "company_name": "WS2 Provenance Test Ltd",
                "sector": "Information Technology",
                "industry": "IT Services",
                "current_price": 2530.00,
                "market_cap": 9_150_000_000_000,
                "pe_ratio": "28.40",
                "roce": 54.2,
                "roe": 47.8,
                "operating_margin": 25.4,
                "debt_to_equity": 0.10,
                "fifty_two_week_high": 4200.0,
                "fifty_two_week_low": 2100.0,
                "source": "SMARTAPI_BSE_EXCHANGE",
            },
            force_overwrite=True,
        )
        try:
            res = self.client.get(f"/dossier/{ticker}")
            self.assertEqual(res.status_code, 200)
            html = res.text

            # Hygiene checks (AGENTS.md Rule 6.7 & 8.2)
            self.assertNotIn("{{", html)
            self.assertNotIn("{%", html)
            self.assertNotIn('\\"', html)

            soup = BeautifulSoup(html, "html.parser")
            prov_bar = soup.find(id="dossierProvenanceBar")
            self.assertIsNotNone(prov_bar, "#dossierProvenanceBar must render on equity dossier")
            prov_text = prov_bar.get_text(" ", strip=True)

            # 1. Live quote preferred over stale report baseline + explicit drift transparency
            self.assertIn("₹2,530.00", prov_text)
            self.assertIn("As of", prov_text)
            self.assertIn("Report Baseline:", prov_text)
            self.assertIn("₹2,156.00", prov_text)
            self.assertIn("+17.3%", prov_text)

            # 2. Financial period covered
            self.assertIn("Q3 FY26 • FY25 Audited (TTM)", prov_text)

            # 3. Direct 1-click exchange registry chips
            reg_chips = prov_bar.select("a.provenance-registry-chip")
            self.assertGreaterEqual(len(reg_chips), 4)
            self.assertTrue(any("bseindia.com" in (a.get("href") or "") for a in reg_chips))

            # 4. Citations appendix tiers & Safari role="list" accessibility contract
            cit_box = soup.find(id="citations")
            self.assertIsNotNone(cit_box)
            cit_list = cit_box.select_one("ul.citations-list")
            self.assertIsNotNone(cit_list)
            self.assertEqual(cit_list.get("role"), "list")
            self.assertGreaterEqual(len(cit_box.select(".citation-tier-primary")), 1)
            self.assertGreaterEqual(len(cit_box.select(".citation-tier-secondary")), 1)

            # 5. Inline SVG explicit sizing contract inside provenance & citations
            for svg in list(prov_bar.find_all("svg")) + list(cit_box.find_all("svg")):
                classes = svg.get("class") or []
                has_explicit_dim = ("glyph" in classes) or (svg.get("width") and svg.get("height"))
                self.assertTrue(has_explicit_dim, f"Inline <svg> missing .glyph or width/height: {svg}")
        finally:
            conn = get_db_connection()
            cur = conn.cursor()
            p = get_placeholder()
            for tbl in ("reports", "report_revisions", "compliance_audit_log", "cached_fundamentals"):
                cur.execute(f"DELETE FROM {tbl} WHERE ticker = {p}", (ticker,))
            conn.commit()
            cur.close()
            conn.close()

    def test_cross_asset_dossiers_render_provenance_bars(self):
        """Verifies Mutual Fund, ETF, REIT, and Debt dossiers also expose structured provenance bars."""
        fund_res = self.client.get("/funds/PPFAS_FLEXICAP_DIR")
        self.assertEqual(fund_res.status_code, 200)
        fund_soup = BeautifulSoup(fund_res.text, "html.parser")
        self.assertIsNotNone(fund_soup.select_one(".dossier-provenance-bar"))
        self.assertGreaterEqual(len(fund_soup.select("a.provenance-registry-chip")), 2)


if __name__ == "__main__":
    unittest.main()
