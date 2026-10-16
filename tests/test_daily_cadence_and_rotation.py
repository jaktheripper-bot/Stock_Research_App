"""
Outside-In Dynamic Cadence and Time-Series Rotation Tests (Pillar 8)
Verifies:
1. Daily 9:00 AM MSME cohort ingestion advances firm count without duplicates.
2. Morning Discovery Reel achieves >= 40% candidate rotation across consecutive editions.
3. Admin MSME daily ingestion endpoint contract.
"""

import unittest
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
            cur.execute("DELETE FROM msme_firms WHERE source LIKE '%(2026-10-25)%' OR source LIKE '%(2026-10-26)%';")
            cur.execute("DELETE FROM discovery_reel WHERE edition_date IN ('2026-10-20', '2026-10-21');")
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass

    def test_msme_daily_cohort_ingestion_and_idempotency(self):
        """Validates that daily MSME ingestion brings in fresh firms and is idempotent."""
        initial_total = get_active_msme_firms_count()
        test_edition_date = "2026-10-25"

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
        edition_day1 = "2026-10-20"
        edition_day2 = "2026-10-21"

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
        unauth_res = client.post("/api/admin/msme/run-daily-ingest?count=15&edition_date=2026-10-26")
        self.assertEqual(unauth_res.status_code, 403)

        # 2. Authenticated admin request must receive 200 OK
        token = _generate_admin_token("admin@research.internal", "admin")
        client.cookies.set(ADMIN_COOKIE_NAME, token)

        res = client.post("/api/admin/msme/run-daily-ingest?count=15&edition_date=2026-10-26")
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

        # Verify all 9 institutional categories are populated
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
        import os

        test_date = "2026-10-16"
        summary = refresh_daily_sovereign_benchmarks(edition_date=test_date)
        self.assertEqual(summary.get("status"), "SUCCESS")
        self.assertEqual(summary.get("edition_date"), test_date)
        self.assertEqual(summary.get("benchmarks_updated"), 16)
        self.assertEqual(summary.get("sdl_spreads_updated"), 10)

        curve = get_sovereign_yield_curve()
        self.assertEqual(len(curve), 16)
        for item in curve:
            self.assertEqual(item.get("auction_date"), test_date)

        sdls = get_sovereign_sdl_matrix()
        self.assertEqual(len(sdls), 10)
        for item in sdls:
            self.assertEqual(item.get("auction_date"), test_date)

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


    def test_asset_surveillance_scanner_and_debt_monitoring(self):
        """Validates Always-On Asset Surveillance scan execution, audit ledger persistence, and /debt page integration."""
        from core.analysis.asset_scanner import run_comprehensive_asset_scan, get_asset_scan_runs
        import os

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
        self.assertIn("CRA Surveillance", debt_page.text)

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

