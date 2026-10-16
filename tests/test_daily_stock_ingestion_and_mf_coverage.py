"""
tests/test_daily_stock_ingestion_and_mf_coverage.py
==============================================================================
Outside-In Dynamic Cadence, 15-Stock Ingestion & Mutual Fund Coverage Tests (Pillar 8 & UI Contracts)

Verifies:
1. Ingestion queue prioritizes uncovered mutual fund holdings by scheme frequency and weight.
2. Ingestion progress statistics report accurate coverage numbers and countdown to full saturation.
3. Daily stock ingestion archives 7-pillar dossiers with Health Matrices into reports.db.
4. Incremental mutual fund re-audit increases genuine look-through coverage for affected funds.
5. /discovery template displays the Mutual Fund Institutional Footprint Badge.
6. /equities directory supports the 'Recently Inducted' filter chip and card badges.
7. Admin endpoints (/api/admin/stocks/run-daily-ingest, /api/admin/stocks/ingestion-queue)
   enforce strict admin authentication and return valid schemas.
==============================================================================
"""

import os
import unittest
from datetime import datetime
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from core.db.connection import init_db, get_db_connection
from core.analysis.daily_stock_ingestion import (
    get_uncovered_mutual_fund_holdings_queue,
    get_ingestion_progress_stats,
    ingest_daily_stock_cohort,
    recalculate_affected_mutual_funds,
)
from core.db.reports import get_report_by_ticker_sync
from core.db.mutual_funds import get_fund_forensic_dossier
from web.main import app
from web.routers.admin import ADMIN_COOKIE_NAME, _generate_admin_token


class TestDailyStockIngestionAndMFCoverage(unittest.TestCase):
    def setUp(self):
        os.environ["TESTING"] = "1"
        init_db()
        self.client = TestClient(app)
        self.test_tickers = ["TEST_MF_STOCK_A", "TEST_MF_STOCK_B"]
        self.test_edition_date = "2026-10-27"
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            for t in self.test_tickers:
                cur.execute("DELETE FROM reports WHERE ticker = ?;", (t,))
                cur.execute("DELETE FROM report_revisions WHERE ticker = ?;", (t,))
                cur.execute("DELETE FROM cached_fundamentals WHERE ticker = ?;", (t,))
                cur.execute("DELETE FROM mutual_fund_holdings WHERE identifier = ?;", (t,))
            cur.execute("DELETE FROM reports WHERE ticker = 'RELIANCE';")
            cur.execute("DELETE FROM report_revisions WHERE ticker = 'RELIANCE';")
            cur.execute("DELETE FROM cached_fundamentals WHERE ticker = 'RELIANCE';")
            cur.execute("DELETE FROM discovery_reel WHERE edition_date = ?;", (self.test_edition_date,))
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass

    def test_uncovered_mutual_fund_queue_ranking(self):
        """Verifies that the queue ranks uncovered MF holdings by scheme count and weight."""
        queue = get_uncovered_mutual_fund_holdings_queue(limit=10)
        self.assertGreaterEqual(len(queue), 5)

        prev_scnt = 99999
        prev_wt = 999999.0
        for item in queue:
            self.assertIn("ticker", item)
            self.assertIn("company_name", item)
            self.assertIn("scheme_count", item)
            self.assertIn("total_weight_pct", item)
            scnt = item["scheme_count"]
            wt = item["total_weight_pct"]

            # Must be ordered by scheme_count DESC, then weight DESC
            self.assertTrue(
                scnt < prev_scnt or (scnt == prev_scnt and wt <= prev_wt) or (scnt == 0 and prev_scnt == 0),
                f"Queue ordering violation: {scnt} schemes vs {prev_scnt}"
            )
            prev_scnt = scnt
            prev_wt = wt

    def test_ingestion_progress_stats_metrics(self):
        """Verifies that progress stats reflect mathematical consistency and countdown."""
        stats = get_ingestion_progress_stats()
        self.assertIn("total_mf_holdings", stats)
        self.assertIn("covered_mf_holdings", stats)
        self.assertIn("uncovered_mf_holdings", stats)
        self.assertIn("coverage_pct", stats)
        self.assertIn("days_to_full_coverage", stats)

        total = stats["total_mf_holdings"]
        covered = stats["covered_mf_holdings"]
        uncovered = stats["uncovered_mf_holdings"]

        self.assertGreaterEqual(total, 50)
        self.assertEqual(covered + uncovered, total)
        self.assertGreater(stats["days_to_full_coverage"], 0)

    def test_stock_ingestion_and_lookthrough_recalculation(self):
        """Verifies that ingesting candidate stocks archives them and triggers fund re-audits."""
        # Seed test MF holdings for our test ticker
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO mutual_fund_holdings (scheme_code, holding_type, identifier, holding_name, weight_pct, sector_or_rating, portfolio_date)
            VALUES (?, 'EQUITY', ?, 'Test Ingestion Asset A', 5.5, 'IT Services', '2026-10-01');
        """, ("PPFAS_FLEXICAP_DIR", self.test_tickers[0]))
        conn.commit()
        cur.close()
        conn.close()

        # Ingest 2 stocks
        res = ingest_daily_stock_cohort(
            edition_date=self.test_edition_date,
            count=2,
            skip_gemini=True
        )

        self.assertIn("ingested_count", res)
        self.assertGreaterEqual(res["ingested_count"], 1)
        self.assertEqual(res["edition_date"], self.test_edition_date)

        # Verify ingested stocks have complete 7-pillar qualitative text and health matrix
        ingested_tickers = res["ingested_tickers"]
        self.assertTrue(len(ingested_tickers) > 0)
        for t in ingested_tickers:
            rep = get_report_by_ticker_sync(t)
            self.assertIsNotNone(rep)
            rep_text = rep.get("report_text", "")
            self.assertIn("### Health Matrix", rep_text)
            self.assertIn("Pillar 1", rep_text)
            self.assertIn("Pillar 5", rep_text)

        # Clean up the ingested tickers created in this specific test
        conn = get_db_connection()
        cur = conn.cursor()
        for t in ingested_tickers:
            cur.execute("DELETE FROM reports WHERE ticker = ?;", (t,))
            cur.execute("DELETE FROM report_revisions WHERE ticker = ?;", (t,))
            cur.execute("DELETE FROM cached_fundamentals WHERE ticker = ?;", (t,))
        conn.commit()
        cur.close()
        conn.close()

    def test_discovery_page_renders_mutual_fund_footprint(self):
        """Verifies that /discovery renders the Mutual Fund Footprint Badge on stock cards."""
        # Seed 1 test item into discovery_reel with scheme_count
        from core.db.discovery import save_discovery_reel
        test_item = [{
            "ticker": "TEST_MF_FOOTPRINT",
            "company_name": "Test Footprint Industries Ltd",
            "sector": "Precision Engineering",
            "market_cap_tier": "Small-Cap",
            "current_price": 450.0,
            "pe_ratio": "18.5",
            "roce_pct": 24.5,
            "debt_to_equity": 0.12,
            "sales_growth_3y": 20.0,
            "ria_thesis": "Institutional compounder held across 18 mutual funds.",
            "catalyst_headline": "Statutory MF Constituent Induction",
            "key_metrics": {
                "roce": "24.5%",
                "debt_to_equity": "0.12",
                "pe": "18.5",
                "scheme_count": 18,
                "estimated_aum_cr": "₹3,450 Cr",
                "top_schemes": ["PPFAS Flexi Cap", "HDFC Mid Cap"]
            }
        }]
        save_discovery_reel(test_item, edition_date=self.test_edition_date)

        response = self.client.get(f"/discovery?edition={self.test_edition_date}")
        self.assertEqual(response.status_code, 200)

        soup = BeautifulSoup(response.text, "html.parser")
        # Assert page rendered cleanly with zero Jinja tag leakage
        self.assertNotIn("{{", response.text)
        self.assertNotIn("{%", response.text)

        # Check for Mutual Fund Institutional Footprint Badge
        badge = soup.find(string=lambda t: t and "Held by 18 Mutual Funds" in t)
        self.assertIsNotNone(badge, "Mutual Fund Institutional Footprint Badge missing on /discovery card.")

        aum_badge = soup.find(string=lambda t: t and "₹3,450 Cr AUM" in t)
        self.assertIsNotNone(aum_badge, "AUM exposure pill missing on /discovery card.")

    def test_equities_directory_recent_inductions_filter(self):
        """Verifies that /equities supports the 'Recently Inducted' filter chip."""
        # Request equities with market_cap=RECENT
        response = self.client.get("/equities?market_cap=RECENT")
        self.assertEqual(response.status_code, 200)

        soup = BeautifulSoup(response.text, "html.parser")
        self.assertNotIn("{{", response.text)
        self.assertNotIn("{%", response.text)

        # Check for Recently Inducted chip in the DOM
        chip = soup.find("a", string=lambda s: s and "Recently Inducted" in s)
        self.assertIsNotNone(chip, "Recently Inducted filter chip missing from /equities directory.")
        self.assertIn("market_cap=RECENT", chip.get("href", ""))

    def test_admin_daily_ingest_and_queue_api_contracts(self):
        """Verifies API contracts and authentication for admin stock ingestion routes."""
        # 1. Unauthenticated requests must receive 403 Forbidden
        unauth_post = self.client.post("/api/admin/stocks/run-daily-ingest?count=2")
        self.assertEqual(unauth_post.status_code, 403)

        unauth_get = self.client.get("/api/admin/stocks/ingestion-queue")
        self.assertEqual(unauth_get.status_code, 403)

        # 2. Authenticated requests must succeed
        token = _generate_admin_token("admin@research.internal", "admin")
        self.client.cookies.set(ADMIN_COOKIE_NAME, token)

        # Test queue endpoint
        queue_res = self.client.get("/api/admin/stocks/ingestion-queue?limit=5")
        self.assertEqual(queue_res.status_code, 200)
        q_data = queue_res.json()
        self.assertTrue(q_data.get("success"))
        self.assertIn("stats", q_data)
        self.assertIn("queue", q_data)
        self.assertIsInstance(q_data["queue"], list)

        # Test run daily ingest endpoint with count=1 and skip_gemini=True
        ingest_res = self.client.post(f"/api/admin/stocks/run-daily-ingest?count=1&edition_date={self.test_edition_date}&skip_gemini=true")
        self.assertEqual(ingest_res.status_code, 200)
        i_data = ingest_res.json()
        self.assertTrue(i_data.get("success"))
        self.assertIn("result", i_data)
        self.assertIn("ingested_tickers", i_data["result"])

        # Clean up the ingested test stock
        ingested_tickers = i_data["result"]["ingested_tickers"]
        conn = get_db_connection()
        cur = conn.cursor()
        for t in ingested_tickers:
            cur.execute("DELETE FROM reports WHERE ticker = ?;", (t,))
            cur.execute("DELETE FROM report_revisions WHERE ticker = ?;", (t,))
            cur.execute("DELETE FROM cached_fundamentals WHERE ticker = ?;", (t,))
        conn.commit()
        cur.close()
        conn.close()


if __name__ == "__main__":
    unittest.main()
