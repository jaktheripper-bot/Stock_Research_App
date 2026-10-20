"""Comprehensive Unit, Integration and DOM Contract Test Suite for Unlisted MSME & SME Intelligence Platform.

Validates:
1. Canonical MSME Seeding Engine & MSMED Act 2020 Tier Classification
2. Ingestion Pipeline Fallback & Resiliency
3. Dual-Dialect Search & Filter Engine (SQLite & PostgreSQL Compatible)
4. Full 4-Pillar Analytical Research Engine (Working Capital, Listed Supply Chain, Solvency, Moat Score)
5. MSME REST API Endpoints (/api/msme/stats, /sectors, /states, /search, /{uin})
6. Standalone Stock Report Route & 4-Pillar HTML Rendering (/msme/{uin})
7. Web Directory DOM Modal Contract, Element Binding & Click-Wiring (/msme)
8. XML Sitemap Inclusion for /msme and enterprise dossiers
"""

import os
import re
import unittest
from fastapi.testclient import TestClient

from core.db.connection import init_db
from core.msme.seed import (
    seed_default_msme_firms,
    classify_msme_tier,
    get_active_msme_firms_count,
    CANONICAL_MSME_FIRMS
)
from core.msme.utils import (
    normalise_sector,
    build_search_query,
    paginate
)
from core.msme.ingest_ministry import run_monthly_job
from core.msme.forensic_engine import (
    compute_msme_forensic_dossier,
    SECTOR_FORENSIC_BENCHMARKS
)
from web.main import app


class TestMsmeFeatureSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        init_db()
        # Ensure database is seeded with benchmark MSMEs
        seed_default_msme_firms()
        cls.client = TestClient(app)

    def test_classify_msme_tier_statutory_thresholds(self):
        """Verify compliance with MSMED Act 2020 turnover classification thresholds."""
        # Micro: < 5 Cr
        self.assertEqual(classify_msme_tier(0.5), "Micro")
        self.assertEqual(classify_msme_tier(4.99), "Micro")
        self.assertEqual(classify_msme_tier(None), "Micro")
        self.assertEqual(classify_msme_tier(0), "Micro")

        # Small: 5 Cr to 50 Cr
        self.assertEqual(classify_msme_tier(5.0), "Small")
        self.assertEqual(classify_msme_tier(25.0), "Small")
        self.assertEqual(classify_msme_tier(49.99), "Small")

        # Medium: >= 50 Cr
        self.assertEqual(classify_msme_tier(50.0), "Medium")
        self.assertEqual(classify_msme_tier(145.0), "Medium")
        self.assertEqual(classify_msme_tier(250.0), "Medium")

    def test_msme_seeding_engine_and_idempotency(self):
        """Verify seeding populates benchmark records and handles duplicate runs gracefully."""
        count = get_active_msme_firms_count()
        self.assertGreaterEqual(count, len(CANONICAL_MSME_FIRMS))

        # Re-run seeding to assert idempotency (no primary key / UIN collisions)
        seeded = seed_default_msme_firms()
        self.assertGreaterEqual(seeded, len(CANONICAL_MSME_FIRMS))

    def test_msme_utils_helpers(self):
        """Test query builders and pagination helpers."""
        self.assertEqual(normalise_sector("Auto Components"), "auto_components")
        self.assertEqual(normalise_sector(""), "")

        limit, offset = paginate(limit=15, page=3)
        self.assertEqual(limit, 15)
        self.assertEqual(offset, 30)

        # Capped limit
        limit_capped, _ = paginate(limit=250, page=1)
        self.assertEqual(limit_capped, 100)

        where, values = build_search_query({"q": "precision", "tier": "medium"}, placeholder="?")
        self.assertIn("LOWER(name) LIKE ?", where)
        self.assertIn("annual_turnover >= 50.0", where)
        self.assertIn("%precision%", values)

    def test_ingest_ministry_msme_records_fallback(self):
        """Verify ingestion resilience handles missing external file and seeds canonical records."""
        count = run_monthly_job()
        self.assertGreaterEqual(count, len(CANONICAL_MSME_FIRMS))

    def test_compute_msme_forensic_dossier_all_4_pillars(self):
        """Empirically assert full quantitative & qualitative depth across all 4 forensic pillars."""
        for firm in CANONICAL_MSME_FIRMS[:10]:
            dossier = compute_msme_forensic_dossier(firm)
            
            # Assert Top Identifiers
            self.assertEqual(dossier["uin"], firm["uin"])
            self.assertEqual(dossier["name"], firm["name"])
            self.assertIn(dossier["tier"], ["Micro", "Small", "Medium"])

            # Pillar 1: Working Capital & CCC
            p1 = dossier["pillar_1_working_capital"]
            self.assertGreater(p1["dso_days"], 0)
            self.assertGreater(p1["dio_days"], 0)
            self.assertGreater(p1["dpo_days"], 0)
            self.assertEqual(p1["net_ccc_days"], p1["dso_days"] + p1["dio_days"] - p1["dpo_days"])
            self.assertGreater(p1["working_capital_req_cr"], 0)
            self.assertIn(p1["stress_level"], ["Low Stress", "Moderate", "Elevated Stretch", "Severe Working Capital Drag"])
            self.assertTrue(len(p1["summary"]) > 20)

            # Pillar 2: Listed Corporate Supply-Chain Linkages
            p2 = dossier["pillar_2_supply_chain"]
            self.assertIn("tier", p2["oem_supplier_tier"].lower())
            self.assertGreaterEqual(len(p2["listed_buyers"]), 2)
            for buyer in p2["listed_buyers"]:
                self.assertTrue(buyer["ticker"].isupper())
                self.assertIn("name", buyer)
                self.assertIn("role", buyer)

            # Pillar 3: Solvency & TReDS Risk
            p3 = dossier["pillar_3_solvency"]
            self.assertGreater(p3["ebitda_margin_pct"], 0)
            self.assertGreater(p3["estimated_ebitda_cr"], 0)
            self.assertGreater(p3["interest_coverage_ratio"], 0)
            self.assertIn(p3["icr_health"], ["Strong Solvency", "Adequate Coverage", "Narrow Headroom", "Vulnerable"])
            self.assertIn("Tier", p3["treds_grade"])
            self.assertIn("%", p3["treds_discount_cost"])

            # Pillar 4: Cluster Moat & Countercase Risk Inversion
            p4 = dossier["pillar_4_moat"]
            self.assertGreaterEqual(p4["moat_score"], 35)
            self.assertLessEqual(p4["moat_score"], 95)
            self.assertIn(p4["moat_tier"], ["Quality Vendor", "Core Industrial Specialist", "Developing Ancillary Workshop"])
            self.assertIn("Moat", p4["moat_badge"])
            self.assertGreaterEqual(len(p4["growth_catalysts"]), 2)
            self.assertGreaterEqual(len(p4["fragility_vectors"]), 2)

    def test_api_msme_stats_endpoint(self):
        """Verify GET /api/msme/stats returns aggregate metrics."""
        response = self.client.get("/api/msme/stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_firms", data)
        self.assertGreater(data["total_firms"], 0)
        self.assertIn("total_turnover_cr", data)
        self.assertIn("medium_count", data)
        self.assertIn("small_count", data)
        self.assertIn("states_count", data)
        self.assertIn("top_sectors", data)

    def test_api_msme_sectors_and_states_endpoints(self):
        """Verify metadata discovery endpoints."""
        res_sec = self.client.get("/api/msme/sectors")
        self.assertEqual(res_sec.status_code, 200)
        data = res_sec.json()
        self.assertIn("sectors", data)
        sector_names = [s["sector"] for s in data["sectors"]]
        self.assertIn("auto_components", sector_names)

        res_st = self.client.get("/api/msme/states")
        self.assertEqual(res_st.status_code, 200)
        data_st = res_st.json()
        self.assertIn("states", data_st)
        state_names = [s["state"] for s in data_st["states"]]
        self.assertIn("Maharashtra", state_names)

    def test_api_msme_search_endpoint(self):
        """Verify GET /api/msme/search API responses and pagination."""
        response = self.client.get("/api/msme/search?q=precision&page=1&size=5")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)
        self.assertIn("total", data)
        self.assertIn("page", data)
        self.assertEqual(data["page"], 1)

    def test_api_msme_search_filters(self):
        """Verify GET /api/msme/search with sector and tier filters."""
        response = self.client.get("/api/msme/search?sector=auto_components&tier=medium")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["total"], 0)
        for r in data["results"]:
            self.assertEqual(r["sector"], "auto_components")
            self.assertEqual(r["tier"], "Medium")
            self.assertGreaterEqual(r["annual_turnover"], 50.0)

    def test_api_msme_profile_by_uin_endpoint_with_forensic_payload(self):
        """Verify GET /api/msme/{uin} returns rich 4-pillar report."""
        sample_uin = CANONICAL_MSME_FIRMS[0]["uin"]
        response = self.client.get(f"/api/msme/{sample_uin}")
        self.assertEqual(response.status_code, 200)
        firm = response.json()
        self.assertEqual(firm["uin"], sample_uin)
        self.assertIn("name", firm)
        self.assertIn("annual_turnover", firm)
        self.assertIn("tier", firm)
        
        # Verify 4 analytical pillars in API response
        self.assertIn("pillar_1_working_capital", firm)
        self.assertIn("pillar_2_supply_chain", firm)
        self.assertIn("pillar_3_solvency", firm)
        self.assertIn("pillar_4_moat", firm)

        # 404 for invalid UIN
        not_found = self.client.get("/api/msme/INVALID-UIN-12345")
        self.assertEqual(not_found.status_code, 404)

    def test_msme_standalone_dossier_page_html_and_4_pillars(self):
        """Verify standalone /msme/{uin} HTML route renders complete forensic analysis."""
        sample_uin = CANONICAL_MSME_FIRMS[0]["uin"]
        response = self.client.get(f"/msme/{sample_uin}")
        self.assertEqual(response.status_code, 200)
        html = response.text

        # Verify header identifiers
        self.assertIn(sample_uin, html)
        self.assertIn(CANONICAL_MSME_FIRMS[0]["name"], html)
        self.assertIn("Back to MSME & SME Directory", html)

        # Verify all 4 analytical pillars in rendered HTML
        self.assertIn("01.", html)
        self.assertIn("Working Capital & Cash Conversion", html)
        self.assertIn("02.", html)
        self.assertIn("Listed Corporate Supply Chain", html)
        self.assertIn("03.", html)
        self.assertIn("Solvency, Margins & TReDS Liquidity", html)
        self.assertIn("04.", html)
        self.assertIn("Cluster Moat & Countercase", html)

        # Verify listed buyer links to equity dossiers
        self.assertIn('href="/dossier/TATAMOTORS"', html)
        self.assertIn("Moat Score", html)

        # 404 for non-existent enterprise
        res_404 = self.client.get("/msme/UDYAM-FAKE-00-0000000")
        self.assertEqual(res_404.status_code, 404)

    def test_msme_web_directory_dom_modal_and_inspect_wiring(self):
        """
        DOM Contract Test: Verify that /msme template contains all target elements
        expected by the inspectMsme() client-side JavaScript, ensuring zero ReferenceErrors.
        """
        response = self.client.get("/msme")
        self.assertEqual(response.status_code, 200)
        html = response.text

        # 1. Assert Modal Container & Backdrop
        self.assertIn('id="msmeModal"', html)
        self.assertIn('class="modal-backdrop"', html)
        self.assertIn('class="modal-dialog"', html)

        # 2. Extract and assert EVERY DOM element ID populated by inspectMsme() in JS
        required_element_ids = [
            "modalFirmName",
            "modalFirmUin",
            "modalTierBadge",
            "modalSectorBadge",
            "modalLocation",
            "modalSource",
            "modalMoatScoreBadge",
            "modalTurnover",
            "modalCCC",
            "modalWCR",
            "modalEmployees",
            "modalStressBadge",
            "modalDSO",
            "modalDIO",
            "modalDPO",
            "modalCCCSummary",
            "modalSupplierTier",
            "modalListedBuyers",
            "modalICRBadge",
            "modalEbitda",
            "modalTredsDesc",
            "modalCapexBarrier",
            "modalFragilityVector",
            "modalFullDossierLink",
        ]
        for elem_id in required_element_ids:
            self.assertIn(
                f'id="{elem_id}"',
                html,
                f"Critical DOM Contract Violation: Element #{elem_id} missing from msme_directory.html but expected by inspectMsme() JS"
            )

        # 3. Assert Table Rows have Inspect Buttons wired with 'this' pointer
        inspect_button_matches = re.findall(r'onclick="inspectMsme\(\'([^\']+)\',\s*this\)"', html)
        self.assertGreater(len(inspect_button_matches), 0, "No valid inspectMsme buttons found in table rows")
        
        # Test that the first wired UIN is valid
        first_wired_uin = inspect_button_matches[0]
        api_check = self.client.get(f"/api/msme/{first_wired_uin}")
        self.assertEqual(api_check.status_code, 200, f"Wired button UIN {first_wired_uin} returns HTTP error on API")

        # 4. Assert direct link to standalone dossier on enterprise names
        self.assertIn(f'href="/msme/{first_wired_uin}"', html)

    def test_msme_sitemap_xml_inclusion(self):
        """Verify XML sitemap includes /msme directory and individual enterprise dossiers."""
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        xml = response.text
        self.assertIn("<loc>https://moatnomics.com/msme</loc>", xml)
        self.assertIn("<loc>https://moatnomics.com/msme/UDYAM-", xml)


if __name__ == "__main__":
    unittest.main()
