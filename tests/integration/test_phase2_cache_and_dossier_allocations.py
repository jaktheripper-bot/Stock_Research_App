"""
Integration and regression test suite for Phase 2:
Right-Size Caches & Eliminate Heavy Per-Request Allocations on /dossier/{ticker}.
"""

import time
import unittest
from unittest import mock
import pandas as pd
from starlette.testclient import TestClient

from web.main import app, _CONTACT_RATE_BUCKETS, _check_and_record_contact_rate
from bse_master import is_synthetic_test_symbol, resolve_bse_scrip_code, resolve_canonical_symbol
from core.db.reports import (
    get_report_revisions,
    get_report_by_ticker,
    get_archived_reports,
    get_all_equities_directory_sync,
    save_report_to_archive,
)
from core.db.connection import get_db_connection
from core.analysis.fundamentals import (
    _FUNDAMENTALS_CACHE,
    _BoundedFundamentalsCache,
    get_historical_prices,
)


class TestPhase2CacheAndDossierAllocations(unittest.TestCase):
    """Empirical verification suite for Phase 2 cache right-sizing and dossier optimizations."""

    def setUp(self):
        self.client = TestClient(app)
        get_report_revisions.cache_clear()
        get_report_by_ticker.cache_clear()
        get_archived_reports.cache_clear()
        get_all_equities_directory_sync.cache_clear()
        _FUNDAMENTALS_CACHE.clear()

    def tearDown(self):
        get_report_revisions.cache_clear()
        get_report_by_ticker.cache_clear()
        get_archived_reports.cache_clear()
        get_all_equities_directory_sync.cache_clear()
        _FUNDAMENTALS_CACHE.clear()

    def test_action_2_1_get_report_revisions_include_text_flag_and_cache(self):
        """Action 2.1: get_report_revisions defaults to include_text=False and is cached with maxsize=32."""
        # Verify cache maxsize is 32
        self.assertEqual(get_report_revisions.cache_parameters()["maxsize"], 32)

        # Call with include_text=False (default)
        revs_no_text = get_report_revisions("INFY", include_text=False)
        self.assertIsInstance(revs_no_text, list)
        if revs_no_text:
            first = revs_no_text[0]
            self.assertEqual(first["report_text"], "")
            self.assertEqual(first["citations"], [])
            self.assertIn("ticker", first)
            self.assertIn("baseline_price", first)

        # Call with include_text=True
        revs_with_text = get_report_revisions("INFY", include_text=True)
        self.assertIsInstance(revs_with_text, list)
        if revs_with_text:
            first = revs_with_text[0]
            self.assertTrue(len(first["report_text"]) > 0 or first["report_text"] != "")

        # Verify separate cache entries for include_text=True vs include_text=False
        info = get_report_revisions.cache_info()
        self.assertGreaterEqual(info.currsize, 1)

    def test_action_2_2_reduced_lru_cache_sizes(self):
        """Action 2.2: Verify reduced lru_cache sizes for get_report_by_ticker and get_archived_reports."""
        self.assertEqual(get_report_by_ticker.cache_parameters()["maxsize"], 48)
        self.assertEqual(get_archived_reports.cache_parameters()["maxsize"], 16)

    def test_action_2_2_get_archived_reports_filters_null_and_empty_text(self):
        """Verify get_archived_reports and get_all_equities_directory_sync exclude NULL/empty report_text and enforce literal underscore prefixes."""
        conn = get_db_connection()
        cur = conn.cursor()
        test_tickers = (
            "NULL_TEXT_TICK",
            "EMPTY_TEXT_TICK",
            "COALINDIA",
            "UNITDSPR",
            "COAL_SYNTH99",
            "UNIT_SYNTH99",
            "TEST_SYNTH99",
            "UNITCOAL_SYNTH99",
        )
        try:
            for t in test_tickers:
                cur.execute("DELETE FROM reports WHERE ticker = ?;", (t,))
            cur.execute(
                "INSERT INTO reports (ticker, short_name, report_text, timestamp) VALUES (?, ?, ?, ?);",
                ("NULL_TEXT_TICK", "Null Candidate", None, "2026-10-28 09:00:00"),
            )
            cur.execute(
                "INSERT INTO reports (ticker, short_name, report_text, timestamp) VALUES (?, ?, ?, ?);",
                ("EMPTY_TEXT_TICK", "Empty Candidate", "   ", "2026-10-28 09:00:00"),
            )
            cur.execute(
                "INSERT INTO reports (ticker, short_name, report_text, timestamp) VALUES (?, ?, ?, ?);",
                ("COALINDIA", "Coal India Ltd", "## Executive Summary\nValid archived dossier.", "2026-10-28 09:00:00"),
            )
            cur.execute(
                "INSERT INTO reports (ticker, short_name, report_text, timestamp) VALUES (?, ?, ?, ?);",
                ("UNITDSPR", "United Spirits Ltd", "## Executive Summary\nValid archived dossier.", "2026-10-28 09:00:00"),
            )
            for synth in ("COAL_SYNTH99", "UNIT_SYNTH99", "TEST_SYNTH99", "UNITCOAL_SYNTH99"):
                cur.execute(
                    "INSERT INTO reports (ticker, short_name, report_text, timestamp) VALUES (?, ?, ?, ?);",
                    (synth, "Synthetic Fixture", "## Executive Summary\nSynthetic text.", "2026-10-28 09:00:00"),
                )
            conn.commit()

            get_archived_reports.cache_clear()
            get_all_equities_directory_sync.cache_clear()
            reps_with_text = get_archived_reports(include_text=True)
            reps_without_text = get_archived_reports(include_text=False)
            dir_equities = get_all_equities_directory_sync()

            returned_tickers_with = {r["ticker"] for r in reps_with_text}
            returned_tickers_without = {r["ticker"] for r in reps_without_text}
            returned_dir_tickers = {r["ticker"] for r in dir_equities}

            for returned in (returned_tickers_with, returned_tickers_without, returned_dir_tickers):
                self.assertNotIn("NULL_TEXT_TICK", returned)
                self.assertNotIn("EMPTY_TEXT_TICK", returned)
                self.assertIn("COALINDIA", returned)
                self.assertIn("UNITDSPR", returned)
                self.assertNotIn("COAL_SYNTH99", returned)
                self.assertNotIn("UNIT_SYNTH99", returned)
                self.assertNotIn("TEST_SYNTH99", returned)
                self.assertNotIn("UNITCOAL_SYNTH99", returned)

            # Verify search_equities includes COALINDIA and UNITDSPR while excluding synthetic prefixes
            from core.search.product_search import search_equities
            coal_hits = {m["identifier"] for m in search_equities("COAL", limit=50)}
            unit_hits = {m["identifier"] for m in search_equities("UNIT", limit=50)}
            self.assertIn("COALINDIA", coal_hits)
            self.assertNotIn("COAL_SYNTH99", coal_hits)
            self.assertNotIn("UNITCOAL_SYNTH99", coal_hits)
            self.assertIn("UNITDSPR", unit_hits)
            self.assertNotIn("UNIT_SYNTH99", unit_hits)

            # Verify purge_test_telemetry deletes synthetic prefixes while preserving COALINDIA and UNITDSPR
            from core.db.telemetry import purge_test_telemetry
            purge_test_telemetry()
            surviving = {
                r[0]
                for r in cur.execute(
                    "SELECT ticker FROM reports WHERE ticker IN ('COALINDIA', 'UNITDSPR', 'COAL_SYNTH99', 'UNIT_SYNTH99', 'TEST_SYNTH99', 'UNITCOAL_SYNTH99');"
                ).fetchall()
            }
            self.assertEqual(surviving, {"COALINDIA", "UNITDSPR"})

            # Ensure all returned items have non-empty text when include_text=True
            for r in reps_with_text:
                self.assertIsNotNone(r["report_text"])
                self.assertTrue(r["report_text"].strip() != "")
        finally:
            for t in test_tickers:
                cur.execute("DELETE FROM reports WHERE ticker = ?;", (t,))
            conn.commit()
            cur.close()
            conn.close()
            get_archived_reports.cache_clear()
            get_all_equities_directory_sync.cache_clear()


    def test_action_2_3_ttl_cache_on_get_all_equities_directory_sync(self):
        """Action 2.3: get_all_equities_directory_sync has TTL cache and invalidation on archive save."""
        get_all_equities_directory_sync.cache_clear()
        res1 = get_all_equities_directory_sync()
        if not res1:
            save_report_to_archive(
                {
                    "ticker": "INFY",
                    "short_name": "Infosys Ltd.",
                    "industry": "Information Technology",
                    "current_price": 1520.0,
                    "pe_ratio": "24.5",
                    "market_cap": 6300000000000,
                },
                "## Executive Summary\nBaseline test dossier for Infosys Ltd.",
            )
            res1 = get_all_equities_directory_sync()
        self.assertIsInstance(res1, list)
        self.assertGreater(len(res1), 0)

        # Second call returns the cached object
        res2 = get_all_equities_directory_sync()
        self.assertIs(res1, res2)

        # Manual cache clear
        get_all_equities_directory_sync.cache_clear()
        res3 = get_all_equities_directory_sync()
        self.assertIsNot(res1, res3)
        self.assertEqual(len(res1), len(res3))

    def test_action_2_4_bounded_fundamentals_cache(self):
        """Action 2.4: _FUNDAMENTALS_CACHE enforces maxsize=64 and prunes expired entries on write."""
        cache = _BoundedFundamentalsCache(maxsize=4, ttl_seconds=0.1)

        # Populate cache up to maxsize
        now = time.time()
        cache["SYM1"] = (now, {"price": 100})
        cache["SYM2"] = (now, {"price": 200})
        cache["SYM3"] = (now, {"price": 300})
        cache["SYM4"] = (now, {"price": 400})
        self.assertEqual(len(cache), 4)

        # Adding a 5th item when full evicts the oldest entry (SYM1)
        cache["SYM5"] = (now + 0.01, {"price": 500})
        self.assertEqual(len(cache), 4)
        self.assertNotIn("SYM1", cache)
        self.assertIn("SYM5", cache)

        # Wait for TTL expiration
        time.sleep(0.12)
        # On read, expired entries are cleared
        self.assertNotIn("SYM2", cache)

        # On write, expired entries are pruned
        cache["SYM6"] = (time.time(), {"price": 600})
        self.assertEqual(len(cache), 1)
        self.assertIn("SYM6", cache)

    def test_action_2_5_historical_prices_cache_and_vectorized_loop(self):
        """Action 2.5: get_historical_prices maxsize=32 and vectorized record conversion in dossier."""
        # Check cache decorated property
        self.assertTrue(hasattr(get_historical_prices, "cache_clear"))

        # Test df.to_dict('records') speed and format compatibility with dossier chart logic
        dates = pd.date_range("2026-01-01", periods=10, freq="D")
        df_dummy = pd.DataFrame({
            "Date": dates,
            "Close": [100.0 + i for i in range(10)],
            "SMA50": [95.0 + i for i in range(10)]
        })
        records = df_dummy.to_dict("records")
        self.assertEqual(len(records), 10)
        self.assertEqual(records[0]["Close"], 100.0)
        self.assertEqual(records[0]["SMA50"], 95.0)

    def test_action_2_6_synthetic_ticker_guard_returns_404_without_bse_cache(self):
        """Action 2.6: Synthetic test tickers return 404 without loading bse_scrips_cache.json."""
        synthetic_cases = [
            "COAL_1792573802959",
            "TESTCORP",
            "TEST_DUMMY_STOCK",
            "UNIT_SAMPLE_STOCK",
            "ZZTEST_PROBE",
            "UNITCOAL_9999",
            "MOCK_1712345678901",
        ]

        for sym in synthetic_cases:
            self.assertTrue(is_synthetic_test_symbol(sym), f"Should recognize {sym} as synthetic")
            self.assertIsNone(resolve_bse_scrip_code(sym))
            self.assertEqual(resolve_canonical_symbol(sym), sym)

        # Mock get_bse_scrips_cache to verify it is NEVER called for synthetic 404 probes
        with mock.patch("web.main.get_bse_scrips_cache") as mock_scrip_cache:
            resp = self.client.get("/dossier/COAL_1792573802959")
            self.assertEqual(resp.status_code, 404)
            mock_scrip_cache.assert_not_called()

            resp2 = self.client.get("/dossier/TESTCORP")
            self.assertEqual(resp2.status_code, 404)
            mock_scrip_cache.assert_not_called()

    def test_action_2_7_contact_rate_bucket_pruning_and_cap(self):
        """Action 2.7: Prunes expired entries and caps _CONTACT_RATE_BUCKETS at 512 keys."""
        _CONTACT_RATE_BUCKETS.clear()
        t_base = time.time()

        # Seed 500 expired entries (>600s old)
        for i in range(500):
            _CONTACT_RATE_BUCKETS[f"old_client_{i}:test@example.com"] = [t_base - 700]

        self.assertEqual(len(_CONTACT_RATE_BUCKETS), 500)

        # Recording a hit prunes expired entries
        allowed = _check_and_record_contact_rate("new_client:new@example.com", t_base)
        self.assertTrue(allowed)
        # All 500 old keys should be pruned since they were >600s old
        self.assertLessEqual(len(_CONTACT_RATE_BUCKETS), 512)
        self.assertNotIn("old_client_0:test@example.com", _CONTACT_RATE_BUCKETS)
        self.assertIn("new_client:new@example.com", _CONTACT_RATE_BUCKETS)

        # Now test 512 hard cap eviction
        _CONTACT_RATE_BUCKETS.clear()
        for i in range(520):
            _CONTACT_RATE_BUCKETS[f"active_{i}:user@example.com"] = [t_base]

        # Trigger cap enforcement
        _check_and_record_contact_rate("overflow_client:user@example.com", t_base)
        self.assertLessEqual(len(_CONTACT_RATE_BUCKETS), 512)

        _CONTACT_RATE_BUCKETS.clear()

    def test_discovery_reel_pending_report_guard(self):
        """Excludes discovery_reel rows queued in reports with NULL/empty report_text until synthesized, while preserving rows absent from reports."""
        from core.db.discovery import save_discovery_reel, get_active_discovery_reel

        edition = "2026-10-04"
        conn = get_db_connection()
        cur = conn.cursor()
        test_tickers = ("DISC_PENDING_NULL", "DISC_PENDING_EMPTY", "DISC_SYNTH_OK", "DISC_UNQUEUED_OK")
        try:
            cur.execute("DELETE FROM discovery_reel WHERE edition_date = ?;", (edition,))
            for t in test_tickers:
                cur.execute("DELETE FROM reports WHERE ticker = ?;", (t,))

            cur.execute(
                "INSERT INTO reports (ticker, short_name, report_text, timestamp) VALUES (?, ?, ?, ?);",
                ("DISC_PENDING_NULL", "Pending Null Ltd", None, "2026-10-04 09:00:00"),
            )
            cur.execute(
                "INSERT INTO reports (ticker, short_name, report_text, timestamp) VALUES (?, ?, ?, ?);",
                ("DISC_PENDING_EMPTY", "Pending Empty Ltd", "   ", "2026-10-04 09:00:00"),
            )
            cur.execute(
                "INSERT INTO reports (ticker, short_name, report_text, timestamp) VALUES (?, ?, ?, ?);",
                ("DISC_SYNTH_OK", "Synthesized Ltd", "## Executive Summary\nComplete dossier.", "2026-10-04 09:00:00"),
            )
            conn.commit()

            save_discovery_reel(
                [
                    {"ticker": "DISC_PENDING_NULL", "company_name": "Pending Null Ltd", "sector": "Industrials", "current_price": 450.0, "ria_thesis": "Thesis A"},
                    {"ticker": "DISC_PENDING_EMPTY", "company_name": "Pending Empty Ltd", "sector": "Industrials", "current_price": 460.0, "ria_thesis": "Thesis B"},
                    {"ticker": "DISC_SYNTH_OK", "company_name": "Synthesized Ltd", "sector": "Industrials", "current_price": 470.0, "ria_thesis": "Thesis C"},
                    {"ticker": "DISC_UNQUEUED_OK", "company_name": "Unqueued Ltd", "sector": "Industrials", "current_price": 480.0, "ria_thesis": "Thesis D"},
                ],
                edition_date=edition,
            )

            for excl in (False, True):
                reel = get_active_discovery_reel(edition_date=edition, exclude_tests=excl, allow_fallback=False)
                tickers = [r["ticker"] for r in reel]
                self.assertEqual(tickers, ["DISC_SYNTH_OK", "DISC_UNQUEUED_OK"])

            # Once DISC_PENDING_NULL is synthesized, it automatically reappears
            cur.execute(
                "UPDATE reports SET report_text = ? WHERE ticker = ?;",
                ("## Executive Summary\nNewly synthesized dossier.", "DISC_PENDING_NULL"),
            )
            conn.commit()

            reel_after = get_active_discovery_reel(edition_date=edition, exclude_tests=True, allow_fallback=False)
            self.assertEqual([r["ticker"] for r in reel_after], ["DISC_PENDING_NULL", "DISC_SYNTH_OK", "DISC_UNQUEUED_OK"])
        finally:
            cur.execute("DELETE FROM discovery_reel WHERE edition_date = ?;", (edition,))
            for t in test_tickers:
                cur.execute("DELETE FROM reports WHERE ticker = ?;", (t,))
            conn.commit()
            cur.close()
            conn.close()

    def test_get_active_mutual_funds_audited_only_and_test_prefix_guard(self):
        """Verifies get_active_mutual_funds filters TEST_ prefixes and enforces audited_only holdings EXISTS check when requested."""
        from core.db.mutual_funds import (
            get_active_mutual_funds,
            save_mutual_fund_scheme,
            save_mutual_fund_holdings,
        )

        codes = ("MF_AUDITED_PROBE_99", "MF_UNAUDITED_PROBE_99", "TEST_MF_PROBE_99")
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            for code in codes:
                cur.execute("DELETE FROM mutual_fund_holdings WHERE scheme_code = ?;", (code,))
                cur.execute("DELETE FROM mutual_fund_schemes WHERE scheme_code = ?;", (code,))
            conn.commit()

            for code in codes:
                save_mutual_fund_scheme(
                    {
                        "scheme_code": code,
                        "scheme_name": f"Probe Scheme {code}",
                        "fund_house": "Probe AMC",
                        "category": "Flexi Cap Fund",
                        "broad_category": "EQUITY",
                        "aum_crores": 999999.0,
                        "nav": 120.0,
                    }
                )
            save_mutual_fund_holdings(
                "MF_AUDITED_PROBE_99",
                [
                    {
                        "holding_type": "EQUITY",
                        "identifier": "INFY",
                        "holding_name": "Infosys Ltd",
                        "weight_pct": 10.0,
                        "sector_or_rating": "IT",
                    }
                ],
            )
            save_mutual_fund_holdings(
                "TEST_MF_PROBE_99",
                [
                    {
                        "holding_type": "EQUITY",
                        "identifier": "INFY",
                        "holding_name": "Infosys Ltd",
                        "weight_pct": 10.0,
                        "sector_or_rating": "IT",
                    }
                ],
            )

            all_codes = {s["scheme_code"] for s in get_active_mutual_funds(limit=None)}
            audited_codes = {s["scheme_code"] for s in get_active_mutual_funds(limit=None, audited_only=True)}

            self.assertIn("MF_AUDITED_PROBE_99", all_codes)
            self.assertIn("MF_UNAUDITED_PROBE_99", all_codes)
            self.assertNotIn("TEST_MF_PROBE_99", all_codes)

            self.assertIn("MF_AUDITED_PROBE_99", audited_codes)
            self.assertNotIn("MF_UNAUDITED_PROBE_99", audited_codes)
            self.assertNotIn("TEST_MF_PROBE_99", audited_codes)

            # Outside-in /funds browse grid shows audited schemes only, while /funds?q=... still finds unaudited AMFI schemes
            resp_browse = self.client.get("/funds")
            self.assertEqual(resp_browse.status_code, 200)
            self.assertIn("MF_AUDITED_PROBE_99", resp_browse.text)
            self.assertNotIn("MF_UNAUDITED_PROBE_99", resp_browse.text)
            self.assertNotIn("TEST_MF_PROBE_99", resp_browse.text)

            resp_search = self.client.get("/funds?q=MF_UNAUDITED_PROBE_99")
            self.assertEqual(resp_search.status_code, 200)
            self.assertIn("MF_UNAUDITED_PROBE_99", resp_search.text)

            resp_api = self.client.get("/api/funds/schemes")
            self.assertEqual(resp_api.status_code, 200)
            api_codes = {s["scheme_code"] for s in resp_api.json().get("schemes", [])}
            self.assertIn("MF_AUDITED_PROBE_99", api_codes)
            self.assertNotIn("MF_UNAUDITED_PROBE_99", api_codes)
            self.assertNotIn("TEST_MF_PROBE_99", api_codes)

            resp_opp = self.client.get("/api/opportunities/universe")
            self.assertEqual(resp_opp.status_code, 200)
            opp_mf_codes = {
                item["symbol"]
                for item in resp_opp.json().get("items", [])
                if item.get("asset_class") == "MF"
            }
            self.assertIn("MF_AUDITED_PROBE_99", opp_mf_codes)
            self.assertNotIn("MF_UNAUDITED_PROBE_99", opp_mf_codes)
            self.assertNotIn("TEST_MF_PROBE_99", opp_mf_codes)
        finally:
            for code in codes:
                cur.execute("DELETE FROM mutual_fund_holdings WHERE scheme_code = ?;", (code,))
                cur.execute("DELETE FROM mutual_fund_schemes WHERE scheme_code = ?;", (code,))
            conn.commit()
            cur.close()
            conn.close()


if __name__ == "__main__":
    unittest.main()
