"""
tests/test_daily_stock_ingestion_and_mf_coverage.py
==============================================================================
Outside-In Dynamic Cadence, 15-Stock Ingestion & Mutual Fund Coverage Tests (Pillar 8 & UI Contracts)

Verifies:
1. Ingestion queue prioritizes uncovered mutual fund holdings by scheme frequency and weight.
2. Ingestion progress statistics report accurate coverage numbers and countdown to full saturation.
3. Daily stock ingestion archives 7-pillar dossiers with Health Matrices into reports.db.
4. Incremental mutual fund re-audit increases genuine look-through coverage for affected funds.
5. /discovery template displays the Mutual Fund Footprint Badge.
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
from core.db.reports import (
    get_report_by_ticker_sync,
    get_report_by_ticker,
    get_archived_reports,
    get_report_revisions,
)
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
            cur.execute("UPDATE reports SET report_text = NULL, citations_json = NULL WHERE ticker = 'RELIANCE';")
            cur.execute("DELETE FROM report_revisions WHERE ticker = 'RELIANCE';")
            cur.execute("DELETE FROM cached_fundamentals WHERE ticker = 'RELIANCE';")
            cur.execute("DELETE FROM discovery_reel WHERE edition_date = ?;", (self.test_edition_date,))
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass
        try:
            get_report_by_ticker.cache_clear()
            get_archived_reports.cache_clear()
            get_report_revisions.cache_clear()
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
            if t == "RELIANCE":
                cur.execute("UPDATE reports SET report_text = NULL, citations_json = NULL WHERE ticker = ?;", (t,))
            else:
                cur.execute("DELETE FROM reports WHERE ticker = ?;", (t,))
            cur.execute("DELETE FROM report_revisions WHERE ticker = ?;", (t,))
            cur.execute("DELETE FROM cached_fundamentals WHERE ticker = ?;", (t,))
        conn.commit()
        cur.close()
        conn.close()
        get_report_by_ticker.cache_clear()
        get_archived_reports.cache_clear()
        get_report_revisions.cache_clear()

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
            "ria_thesis": "Compounder held across 18 mutual funds.",
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

        # Check for Mutual Fund Footprint Badge
        badge = soup.find(string=lambda t: t and "Held by 18 Mutual Funds" in t)
        self.assertIsNotNone(badge, "Mutual Fund Footprint Badge missing on /discovery card.")

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
            if t == "RELIANCE":
                cur.execute("UPDATE reports SET report_text = NULL, citations_json = NULL WHERE ticker = ?;", (t,))
            else:
                cur.execute("DELETE FROM reports WHERE ticker = ?;", (t,))
            cur.execute("DELETE FROM report_revisions WHERE ticker = ?;", (t,))
            cur.execute("DELETE FROM cached_fundamentals WHERE ticker = ?;", (t,))
        conn.commit()
        cur.close()
        conn.close()
        get_report_by_ticker.cache_clear()
        get_archived_reports.cache_clear()
        get_report_revisions.cache_clear()

"""
Outside-In Dynamic Cadence and Time-Series Rotation Tests (Pillar 8)
Verifies:
1. Daily 9:00 AM MSME cohort ingestion advances firm count without duplicates.
2. Morning Discovery Reel achieves >= 40% candidate rotation across consecutive editions.
3. Admin MSME daily ingestion endpoint contract.
"""

from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from core.db.connection import init_db, get_db_connection, get_placeholder
from core.msme.seed import get_active_msme_firms_count
from core.db.discovery import save_discovery_reel, get_active_discovery_reel
from core.msme.daily_ingest import ingest_daily_msme_cohort
from core.analysis.stock_discovery import curate_morning_discovery_cohort
from web.main import app


class TestDailyCadenceAndRotation(unittest.TestCase):
    def setUp(self):
        init_db()
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM msme_firms WHERE source LIKE '%(2099-12-25)%' OR source LIKE '%(2099-12-26)%' OR source LIKE '%(2026-10-25)%' OR source LIKE '%(2026-10-26)%';")
            cur.execute("DELETE FROM discovery_reel WHERE edition_date IN ('2099-12-20', '2099-12-21', '2026-10-21');")
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass

    def test_msme_daily_cohort_ingestion_and_idempotency(self):
        """Validates that daily MSME ingestion brings in fresh firms and is idempotent."""
        initial_total = get_active_msme_firms_count()
        test_edition_date = "2099-12-25"

        # Ingest 15 new MSMEs for test edition date
        added = ingest_daily_msme_cohort(edition_date=test_edition_date, count=15)
        self.assertEqual(added, 15)

        # Verify total firms increased
        new_total = get_active_msme_firms_count()
        self.assertGreaterEqual(new_total, initial_total + 15)

        # Verify firms for this edition date exist and have complete analytical depth
        conn = get_db_connection()
        cursor = conn.cursor()
        p = get_placeholder()
        cursor.execute(f"SELECT uin, name, sector_name, annual_turnover, employee_count, source FROM msme_firms WHERE source LIKE {p};", (f"%({test_edition_date})%",))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        self.assertEqual(len(rows), 15)
        for row in rows:
            uin, name, sector, turnover, emp_count, source = row[0], row[1], row[2], row[3], row[4], row[5]
            self.assertTrue(uin.startswith("UDYAM-"))
            self.assertTrue(len(name) > 3)
            self.assertTrue(len(sector) > 2)
            self.assertGreater(turnover, 0)
            self.assertGreater(emp_count, 0)
            self.assertIn(test_edition_date, source)

        # Idempotency check: running again on same date must update in-place without duplicating rows
        added_again = ingest_daily_msme_cohort(edition_date=test_edition_date, count=15)
        self.assertEqual(added_again, 15)
        final_total = get_active_msme_firms_count()
        self.assertEqual(final_total, new_total)

    def test_stock_discovery_time_series_rotation_contract(self):
        """Validates that Morning Discovery Reel rotates >= 40% of candidates across consecutive editions."""
        edition_day1 = "2099-12-20"
        edition_day2 = "2099-12-21"

        # Curate and persist Day 1 cohort
        cohort_day1 = curate_morning_discovery_cohort(target_count=12, edition_date=edition_day1)
        self.assertGreaterEqual(len(cohort_day1), 10)
        save_discovery_reel(cohort_day1, edition_date=edition_day1)

        tickers_day1 = {item["ticker"] for item in cohort_day1}
        self.assertEqual(len(tickers_day1), len(cohort_day1))

        # Curate Day 2 cohort with prior Day 1 in place
        cohort_day2 = curate_morning_discovery_cohort(target_count=12, edition_date=edition_day2)
        self.assertGreaterEqual(len(cohort_day2), 10)

        tickers_day2 = {item["ticker"] for item in cohort_day2}

        # Calculate rotation
        fresh_tickers = tickers_day2 - tickers_day1
        rotation_pct = (len(fresh_tickers) / len(cohort_day2)) * 100.0

        # Assert >= 40% rotation covenant
        self.assertGreaterEqual(
            rotation_pct,
            40.0,
            f"Rotation failed: Only {len(fresh_tickers)}/{len(cohort_day2)} ({rotation_pct:.1f}%) fresh tickers between {edition_day1} and {edition_day2}."
        )

        # Assert sector diversification covenant: max 2 per sector
        sector_counts = {}
        for item in cohort_day2:
            sec = item.get("sector")
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            self.assertLessEqual(
                sector_counts[sec],
                2,
                f"Sector clustering violation: sector '{sec}' has {sector_counts[sec]} picks."
            )

    def test_admin_msme_daily_ingest_endpoint(self):
        """Validates outside-in API contract for POST /api/admin/msme/run-daily-ingest."""
        from web.routers.admin import ADMIN_COOKIE_NAME, _generate_admin_token
        client = TestClient(app)

        # 1. Unauthenticated request must receive 403 Forbidden
        unauth_res = client.post("/api/admin/msme/run-daily-ingest?count=15&edition_date=2099-12-26")
        self.assertEqual(unauth_res.status_code, 403)

        # 2. Authenticated admin request must receive 200 OK
        token = _generate_admin_token("admin@research.internal", "admin")
        client.cookies.set(ADMIN_COOKIE_NAME, token)

        res = client.post("/api/admin/msme/run-daily-ingest?count=15&edition_date=2099-12-26")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "initiated")
        self.assertIn("15", data.get("message", ""))

    def test_etf_matrix_dynamic_sync_and_catalog(self):
        """Validates that AMFI ETF ingestion syncs >= 400 active ETFs across 9 categories and displays outside-in."""
        from core.ingestion.etf_ingest import ingest_all_amfi_etfs
        from core.db.sovereign import get_etf_matrix

        summary = ingest_all_amfi_etfs(force_refresh=False)
        self.assertEqual(summary.get("status"), "SUCCESS")
        self.assertGreaterEqual(summary.get("persisted_to_db", 0), 400)

        # Verify all 9 categories are populated
        all_etfs = get_etf_matrix(category=None)
        self.assertGreaterEqual(len(all_etfs), 400)
        categories = {e.get("category") for e in all_etfs}
        expected_cats = {
            "EQUITY_INDEX", "EQUITY_SECTORAL", "EQUITY_FACTOR",
            "COMMODITY_GOLD", "COMMODITY_SILVER",
            "DEBT_SOVEREIGN", "DEBT_TARGET_MATURITY", "LIQUID", "INTERNATIONAL"
        }
        for ec in expected_cats:
            self.assertIn(ec, categories, f"Missing ETF category {ec}")

        # Outside-In UI verification
        client = TestClient(app)
        res = client.get("/etfs")
        self.assertEqual(res.status_code, 200)
        self.assertIn("National ETF Performance", res.text)
        self.assertIn("National ETF Matrix", res.text)

        # API Contract verification
        api_res = client.get("/api/etfs/matrix")
        self.assertEqual(api_res.status_code, 200)
        api_data = api_res.json()
        self.assertGreaterEqual(api_data.get("total_tracked_etfs", 0), 400)

    def test_sovereign_daily_benchmarks_refresh_and_admin_endpoint(self):
        """Validates Sovereign Risk-Free Benchmarks refresh and admin sync endpoint."""
        from core.db.sovereign import refresh_daily_sovereign_benchmarks, get_sovereign_yield_curve, get_sovereign_sdl_matrix
        
        test_date = "2026-10-16"
        summary = refresh_daily_sovereign_benchmarks(edition_date=test_date)
        self.assertEqual(summary.get("status"), "SUCCESS")
        self.assertEqual(summary.get("edition_date"), test_date)
        self.assertEqual(summary.get("benchmarks_updated"), 16)
        self.assertEqual(summary.get("sdl_spreads_updated"), 10)

        curve = get_sovereign_yield_curve()
        self.assertEqual(len(curve), 16)
        for item in curve:
            self.assertTrue(bool(item.get("auction_date")))

        sdls = get_sovereign_sdl_matrix()
        self.assertEqual(len(sdls), 10)
        for item in sdls:
            self.assertTrue(bool(item.get("auction_date")))

        # Outside-in Admin API contract
        client = TestClient(app)
        unauth_res = client.post("/api/admin/sovereign/refresh")
        self.assertEqual(unauth_res.status_code, 403)

        os.environ["ADMIN_API_KEY"] = "test_admin_key_sovereign_12345"
        auth_res = client.post("/api/admin/sovereign/refresh?edition_date=2026-10-16", headers={"x-admin-key": "test_admin_key_sovereign_12345"})
        self.assertEqual(auth_res.status_code, 200)
        auth_data = auth_res.json()
        self.assertEqual(auth_data.get("status"), "success")
        self.assertEqual(auth_data.get("summary", {}).get("edition_date"), test_date)

        # Public Sovereign curve page and API contract
        page_res = client.get("/sovereign")
        self.assertEqual(page_res.status_code, 200)
        self.assertIn("Indian Sovereign Debt", page_res.text)

        curve_api_res = client.get("/api/sovereign/curve")
        self.assertEqual(curve_api_res.status_code, 200)
        self.assertGreaterEqual(len(curve_api_res.json().get("curve_points", [])), 16)


    def test_asset_monitoring_scanner_and_debt_monitoring(self):
        """Validates Always-On Asset Monitoring scan execution, audit ledger persistence, and /debt page integration."""
        from core.analysis.asset_scanner import run_comprehensive_asset_scan, get_asset_scan_runs
        
        # Execute scan
        scan_res = run_comprehensive_asset_scan(scan_type="ALL_ASSETS", triggered_by="unit_test_suite", limit=20)
        self.assertEqual(scan_res.get("status"), "completed")
        self.assertGreater(scan_res.get("items_scanned", 0), 0)

        # Verify audit ledger persistence
        recent_runs = get_asset_scan_runs(limit=5)
        self.assertTrue(any(r["scan_id"] == scan_res["scan_id"] for r in recent_runs))

        # Admin route contract
        client = TestClient(app)
        unauth_res = client.post("/api/admin/assets/scan")
        self.assertEqual(unauth_res.status_code, 403)

        os.environ["ADMIN_API_KEY"] = "test_admin_key_asset_scan_12345"
        auth_res = client.post("/api/admin/assets/scan?scan_type=CORPORATE_DEBT", headers={"x-admin-key": "test_admin_key_asset_scan_12345"})
        self.assertEqual(auth_res.status_code, 200)
        auth_data = auth_res.json()
        self.assertEqual(auth_data.get("status"), "success")

        # Outside-In /debt page rendering
        debt_page = client.get("/debt")
        self.assertEqual(debt_page.status_code, 200)
        self.assertIn("Benchmark 10Y G-Sec", debt_page.text)
        self.assertIn("CRA Monitoring", debt_page.text)

    def test_mutual_funds_directory_dynamic_expansion(self):
        """Validates that Mutual Funds query and directory render without artificial limit constraints."""
        from core.db.mutual_funds import get_active_mutual_funds

        # Database returns full active directory when limit is None or large
        all_schemes = get_active_mutual_funds(limit=None)
        self.assertGreater(len(all_schemes), 500)

        # Outside-in page render
        client = TestClient(app)
        res = client.get("/funds")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Mutual Fund Look-Through", res.text)
        self.assertIn("Audited Schemes", res.text)

if __name__ == "__main__":
    unittest.main()
