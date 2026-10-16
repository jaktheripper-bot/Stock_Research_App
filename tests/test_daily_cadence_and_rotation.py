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


if __name__ == "__main__":
    unittest.main()
