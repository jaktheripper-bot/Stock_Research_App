"""Comprehensive Unit and Integration Test Suite for Unlisted MSME & SME Intelligence Platform.

Validates:
1. Canonical MSME Seeding Engine & MSMED Act 2020 Tier Classification
2. Ingestion Pipeline Fallback & Resiliency
3. Dual-Dialect Search & Filter Engine (SQLite & PostgreSQL Compatible)
4. MSME REST API Endpoints (/api/msme/stats, /sectors, /states, /search, /{uin})
5. Web Directory Route & Navigation Wiring (/msme)
"""

import os
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

    def test_api_msme_profile_by_uin_endpoint(self):
        """Verify GET /api/msme/{uin} for valid and invalid records."""
        sample_uin = CANONICAL_MSME_FIRMS[0]["uin"]
        response = self.client.get(f"/api/msme/{sample_uin}")
        self.assertEqual(response.status_code, 200)
        firm = response.json()
        self.assertEqual(firm["uin"], sample_uin)
        self.assertIn("name", firm)
        self.assertIn("annual_turnover", firm)
        self.assertIn("tier", firm)

        # 404 for invalid UIN
        not_found = self.client.get("/api/msme/INVALID-UIN-12345")
        self.assertEqual(not_found.status_code, 404)

    def test_msme_web_directory_page_and_navigation(self):
        """Verify /msme HTML route loads successfully and base template links to it."""
        response = self.client.get("/msme")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Unlisted MSME & Emerging SME Directory", html)
        self.assertIn("MSMED Act 2020", html)
        self.assertIn("vestnomics", html.lower())

        # Check navigation item in base.html
        home_res = self.client.get("/")
        self.assertEqual(home_res.status_code, 200)
        self.assertIn('href="/msme"', home_res.text)


if __name__ == "__main__":
    unittest.main()
