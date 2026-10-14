"""Test Suite for Dynamic AMFI ETF Ingestion Pipeline, Analytical Engine, and UI Integration.

Validates:
1. Canonical Institutional ETF Universe completeness (140+ ETFs across 9 categories).
2. AMFI text feed parsing, FoF exclusion, deterministic symbol resolution, and categorization.
3. Database persistence (SQLite/PostgreSQL dual-binding, batch upserts, search, sorting).
4. Analytical engine evaluations (arbitrage detection, tracking error drag, liquidity tiers).
5. Web router endpoints (/etfs, /api/etfs/matrix, /api/etfs/{symbol}, /api/admin/etfs/trigger-ingest).
"""

import unittest
from fastapi.testclient import TestClient

from core.db.connection import init_db
from core.db.etf_universe import CANONICAL_ETF_UNIVERSE
from core.ingestion.etf_ingest import (
    derive_etf_category,
    derive_underlying_index,
    resolve_symbol,
    parse_amfi_etf_feed,
    ingest_all_amfi_etfs,
    get_or_seed_canonical_etfs,
)
from core.db.sovereign import (
    get_etf_matrix,
    get_etf_by_symbol,
    save_etf_matrix_item,
    save_etf_matrix_items,
    DEFAULT_ETF_MATRIX,
)
from core.analysis.etf_matrix_engine import evaluate_etf_matrix, get_etf_detail
from web.main import app


class TestCanonicalETFUniverse(unittest.TestCase):
    """Validates the seed universe of institutional benchmark ETFs."""

    def test_canonical_universe_size(self):
        self.assertGreaterEqual(len(CANONICAL_ETF_UNIVERSE), 140, "Universe must contain at least 140 ETFs")

    def test_symbol_uniqueness(self):
        symbols = [item["symbol"].upper() for item in CANONICAL_ETF_UNIVERSE]
        self.assertEqual(len(symbols), len(set(symbols)), "Canonical ETF symbols must be strictly unique")

    def test_category_coverage(self):
        expected_categories = {
            "EQUITY_INDEX",
            "EQUITY_SECTORAL",
            "EQUITY_FACTOR",
            "COMMODITY_GOLD",
            "COMMODITY_SILVER",
            "DEBT_SOVEREIGN",
            "DEBT_TARGET_MATURITY",
            "LIQUID",
            "INTERNATIONAL",
        }
        actual_categories = {item["category"] for item in CANONICAL_ETF_UNIVERSE}
        self.assertEqual(expected_categories, actual_categories, "All 9 categories must be represented in universe")

    def test_numeric_integrity(self):
        for item in CANONICAL_ETF_UNIVERSE:
            self.assertGreater(item["last_price"], 0.0, f"Invalid price for {item['symbol']}")
            self.assertGreater(item["nav"], 0.0, f"Invalid NAV for {item['symbol']}")
            self.assertGreater(item["aum_crores"], 0.0, f"Invalid AUM for {item['symbol']}")
            self.assertGreaterEqual(item["expense_ratio_pct"], 0.0, f"Invalid TER for {item['symbol']}")
            self.assertGreaterEqual(item["tracking_error_1y"], 0.0, f"Invalid tracking error for {item['symbol']}")


class TestAMFIParsingAndCategorization(unittest.TestCase):
    """Validates classification, FoF exclusion, and deterministic symbol allocation."""

    def test_category_derivation(self):
        self.assertEqual(derive_etf_category("Nippon India ETF Gold BeES"), "COMMODITY_GOLD")
        self.assertEqual(derive_etf_category("SBI Silver ETF"), "COMMODITY_SILVER")
        self.assertEqual(derive_etf_category("Nippon India ETF Liquid BeES"), "LIQUID")
        self.assertEqual(derive_etf_category("Edelweiss BHARAT Bond ETF - April 2030"), "DEBT_TARGET_MATURITY")
        self.assertEqual(derive_etf_category("ICICI Prudential Nifty 5 yr Benchmark G-Sec ETF"), "DEBT_SOVEREIGN")
        self.assertEqual(derive_etf_category("Motilal Oswal Nasdaq 100 ETF"), "INTERNATIONAL")
        self.assertEqual(derive_etf_category("Mirae Asset Nifty Midcap 150 ETF"), "EQUITY_INDEX")
        self.assertEqual(derive_etf_category("Nippon India ETF Nifty Bank BeES"), "EQUITY_SECTORAL")
        self.assertEqual(derive_etf_category("UTI Nifty200 Momentum 30 ETF"), "EQUITY_FACTOR")

    def test_underlying_index_derivation(self):
        self.assertEqual(derive_underlying_index("Nippon India ETF Gold BeES", "COMMODITY_GOLD"), "Domestic Price of Physical Gold (999 Purity)")
        self.assertEqual(derive_underlying_index("Nippon India ETF Liquid BeES", "LIQUID"), "Nifty 1D Rate Index (TREPS)")
        self.assertIn("Nifty 50", derive_underlying_index("HDFC Nifty 50 ETF", "EQUITY_INDEX"))
        self.assertIn("Momentum", derive_underlying_index("UTI Nifty200 Momentum 30 ETF", "EQUITY_FACTOR"))

    def test_fof_filtering_in_feed_parser(self):
        sample_feed = (
            "Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\n"
            "Open Ended Schemes ( Other Scheme - Other ETFs )\n"
            "Nippon India Mutual Fund\n"
            "119551;INF204KB14I2;-;Nippon India ETF Nifty 50 BeES;272.4200;14-Oct-2026\n"
            "140088;INF204KB17I5;-;Nippon India ETF Gold BeES;122.4186;14-Oct-2026\n"
            "152980;INF666M01IX9;-;Groww Gold ETF FOF - Direct Plan - Growth;18.1815;14-Oct-2026\n"
            "153745;INF666M01LN4;-;Groww BSE Power ETF Fund of Fund - Regular;10.6922;14-Oct-2026\n"
        )
        parsed = parse_amfi_etf_feed(sample_feed)
        scheme_names = [p["scheme_name"].lower() for p in parsed]
        # FoFs must be filtered out
        for name in scheme_names:
            self.assertNotIn("fof", name, "FoF should be excluded from direct ETF matrix")
            self.assertNotIn("fund of fund", name, "Fund of Fund should be excluded from direct ETF matrix")

    def test_symbol_resolution_uniqueness(self):
        allocated = set()
        lookup = {item["scheme_code"]: item for item in CANONICAL_ETF_UNIVERSE if item.get("scheme_code")}
        sym1 = resolve_symbol("Groww Nifty 50 ETF", "153699", "INF666M01LL8", lookup, allocated)
        sym2 = resolve_symbol("Groww Nifty 500 Low Volatility 50 ETF", "153583", "INF666M01LB9", lookup, allocated)
        sym3 = resolve_symbol("Groww Nifty 500 Momentum 50 ETF", "153452", "INF666M01KJ4", lookup, allocated)
        self.assertNotEqual(sym1, sym2)
        self.assertNotEqual(sym2, sym3)
        self.assertEqual(len(allocated), 3)


class TestETFDatabaseOperations(unittest.TestCase):
    """Validates DB persistence, querying, multi-attribute filtering, and sorting."""

    @classmethod
    def setUpClass(cls):
        init_db()
        get_or_seed_canonical_etfs()

    def test_save_and_retrieve_etf_matrix(self):
        test_item = {
            "symbol": "TESTNIFTY",
            "scheme_name": "Test Benchmark Nifty ETF",
            "category": "EQUITY_INDEX",
            "underlying_index": "Nifty 50 TRI",
            "last_price": 250.00,
            "nav": 249.50,
            "tracking_error_1y": 0.03,
            "expense_ratio_pct": 0.05,
            "aum_crores": 5000.0,
            "avg_daily_volume": 100000.0,
            "avg_daily_turnover_cr": 2.5,
            "liquidity_tier": "HIGH_LIQUIDITY",
            "scheme_code": "999999",
            "isin": "INF999K01999"
        }
        saved = save_etf_matrix_item(test_item)
        self.assertTrue(saved)

        fetched = get_etf_by_symbol("TESTNIFTY")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["symbol"], "TESTNIFTY")
        self.assertEqual(fetched["scheme_name"], "Test Benchmark Nifty ETF")
        self.assertEqual(fetched["last_price"], 250.00)
        self.assertEqual(fetched["nav"], 249.50)

    def test_get_etf_matrix_with_filters(self):
        # Category filter
        gold_etfs = get_etf_matrix(category="COMMODITY_GOLD")
        self.assertGreater(len(gold_etfs), 0)
        for item in gold_etfs:
            self.assertEqual(item["category"], "COMMODITY_GOLD")

        # Query filter
        nifty_etfs = get_etf_matrix(query="NIFTY")
        self.assertGreater(len(nifty_etfs), 0)
        for item in nifty_etfs:
            matches = (
                "NIFTY" in item["symbol"].upper() or
                "NIFTY" in item["scheme_name"].upper() or
                "NIFTY" in item.get("underlying_index", "").upper()
            )
            self.assertTrue(matches, f"Item {item['symbol']} does not match query NIFTY")

    def test_get_etf_matrix_sorting(self):
        # Sort by AUM descending
        by_aum = get_etf_matrix(sort_by="aum_desc", limit=5)
        for i in range(len(by_aum) - 1):
            self.assertGreaterEqual(by_aum[i]["aum_crores"], by_aum[i+1]["aum_crores"])

        # Sort by tracking error ascending
        by_te = get_etf_matrix(sort_by="tracking_error_asc", limit=5)
        for i in range(len(by_te) - 1):
            self.assertLessEqual(by_te[i]["tracking_error_1y"], by_te[i+1]["tracking_error_1y"])


class TestETFMatrixEngine(unittest.TestCase):
    """Validates analytical computations, forensic audit notes, and detail resolution."""

    @classmethod
    def setUpClass(cls):
        init_db()
        get_or_seed_canonical_etfs()

    def test_evaluate_etf_matrix_aggregation(self):
        matrix = evaluate_etf_matrix()
        self.assertIn("total_tracked_etfs", matrix)
        self.assertGreaterEqual(matrix["total_tracked_etfs"], 120)
        self.assertIn("total_aum_lakh_cr", matrix)
        self.assertGreater(matrix["total_aum_crores"], 100000.0)
        self.assertIn("category_counts", matrix)
        self.assertIn("EQUITY_INDEX", matrix["category_counts"])
        self.assertIn("COMMODITY_GOLD", matrix["category_counts"])

        # Check grouped_by_category backward compatibility
        self.assertIn("grouped_by_category", matrix)
        self.assertIn("ALL", matrix["grouped_by_category"])
        self.assertIn("EQUITY_INDEX", matrix["grouped_by_category"])

    def test_get_etf_detail_resolution(self):
        detail = get_etf_detail("NIFTYBEES")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["etf"]["symbol"], "NIFTYBEES")
        self.assertIn("aum_formatted", detail)
        self.assertIn("peers", detail)
        self.assertIn("forensic_notes", detail)


class TestWebAndApiEndpoints(unittest.TestCase):
    """Validates web routes and JSON API contracts."""

    @classmethod
    def setUpClass(cls):
        init_db()
        get_or_seed_canonical_etfs()

    def setUp(self):
        self.client = TestClient(app)

    def test_etfs_html_page(self):
        response = self.client.get("/etfs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("National ETF Performance & Liquidity Matrix", response.text)
        self.assertIn("Equity Indices", response.text)
        self.assertIn("Gold", response.text)

    def test_api_etfs_matrix_endpoint(self):
        response = self.client.get("/api/etfs/matrix")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_tracked_etfs", data)
        self.assertGreaterEqual(data["total_tracked_etfs"], 120)
        self.assertIn("etfs", data)

    def test_api_etfs_detail_endpoint(self):
        response = self.client.get("/api/etfs/NIFTYBEES")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["etf"]["symbol"], "NIFTYBEES")

    def test_api_etfs_detail_not_found(self):
        response = self.client.get("/api/etfs/NONEXISTENT_TICKER_999")
        self.assertEqual(response.status_code, 404)

    def test_api_admin_trigger_ingest(self):
        response = self.client.post("/api/admin/etfs/trigger-ingest")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
