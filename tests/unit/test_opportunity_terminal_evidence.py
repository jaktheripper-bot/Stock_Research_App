"""Regression tests for the Terminal's typed financial observations and dedicated market quote store."""

from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

from core.analysis import opportunity_terminal as terminal


def days_ago(days):
    return (datetime.now(ZoneInfo("Asia/Kolkata")).date() - timedelta(days=days)).isoformat()


class TestTerminalEvidence(TestCase):
    def test_zero_and_negative_values_are_preserved_and_stale_values_are_withheld(self):
        for value in (0, -3.1):
            metric = terminal._observation("HISTORICAL_CAGR_3Y", value, days_ago(2), "AMC factsheet")
            self.assertEqual(metric["gross_yield_pct"], value)
            self.assertEqual(metric["metric_status"], "available")
        stale = terminal._observation("CONTRACTUAL_YTM", 9, days_ago(8), "Exchange quote")
        self.assertEqual(stale["metric_status"], "stale")
        self.assertIsNone(stale["gross_yield_pct"])
        self.assertEqual(stale["metric_as_of"], days_ago(8))
        for value, date_val, source in (
            (float("nan"), days_ago(0), "Source"),
            (9, days_ago(-1), "Source"),
            (9, days_ago(0), None),
        ):
            self.assertEqual(
                terminal._observation("CONTRACTUAL_YTM", value, date_val, source)["metric_status"],
                "unavailable",
            )

    def test_forbidden_vendor_sources_are_withheld(self):
        for vendor in ("Morningstar India", "Yahoo Finance", "https://www.screener.in/company/INFY/"):
            metric = terminal._observation("HISTORICAL_CAGR_3Y", 15.2, days_ago(1), vendor)
            self.assertEqual(metric["metric_status"], "unavailable", vendor)
            self.assertIsNone(metric["gross_yield_pct"], vendor)

    def test_universe_keeps_legacy_inventory_without_using_coupon_or_five_year_cagr(self):
        quote = {
            "quoted_ytm_pct": 8,
            "quoted_ytm_as_of": days_ago(0),
            "quoted_ytm_source": "Exchange quote",
            "quoted_years_to_maturity": 2,
        }
        with patch.multiple(
            terminal,
            _load_latest_debt_quote_observations=lambda: {},
            _load_latest_instrument_observations=lambda: {},
            get_active_debt_securities=lambda **_: [
                {"isin": "NODATE", "coupon_rate_pct": 50, "ytm_pct": 50},
                {"isin": "DATED", "metadata": quote},
            ],
            get_all_reits_and_invits=lambda: [],
            get_all_sgb_tranches=lambda: [],
            get_sovereign_yield_curve=lambda: [],
            get_active_mutual_funds=lambda **_: [
                {"scheme_code": "MFOLD", "returns_5y_cagr": 99},
                {
                    "scheme_code": "MFNEW",
                    "metadata": {
                        "returns_3y_cagr": 22,
                        "returns_3y_as_of": days_ago(0),
                        "returns_3y_source": "AMC factsheet",
                    },
                },
            ],
            get_etf_matrix=lambda: [{"symbol": "ETFOLD"}],
            get_archived_reports=lambda **_: [{"ticker": "EQOLD"}],
        ):
            universe = terminal.get_normalized_opportunity_universe()
            rows = {row["id"]: row for row in universe}
            for missing in ("NODATE", "MFOLD", "ETFOLD", "EQOLD"):
                self.assertIsNone(rows[missing]["gross_yield_pct"])
                self.assertEqual(rows[missing]["metric_status"], "unavailable")
            self.assertEqual(rows["DATED"]["gross_yield_pct"], 8)
            self.assertIsNone(rows["DATED"]["net_yield_pct"])
            matrix = terminal.get_heatmap_matrix(universe)
            self.assertEqual(matrix["rows"][1]["cells"]["1-3Y"]["id"], "DATED")
            comparison = terminal.get_arbitrage_comparison(["DATED", "MFNEW"])
            self.assertFalse(comparison["same_comparison_group"])
            self.assertEqual([row["id"] for row in comparison["items"]], ["DATED", "MFNEW"])

    def test_matured_sgb_excluded_and_gold_etf_classified_as_commodity_trust(self):
        with patch.multiple(
            terminal,
            _load_latest_debt_quote_observations=lambda: {},
            _load_latest_instrument_observations=lambda: {},
            get_active_debt_securities=lambda **_: [],
            get_all_reits_and_invits=lambda: [],
            get_all_sgb_tranches=lambda: [
                {
                    "symbol": "SGBMATURED",
                    "series_name": "SGB 2018-19 Series I",
                    "maturity_date": days_ago(10),
                    "ytm_pct": 8.5,
                    "last_updated": days_ago(1),
                    "metadata": {"ytm_source": "NSE secondary quote"},
                },
                {
                    "symbol": "SGBACTIVE",
                    "series_name": "SGB 2023-24 Series IV",
                    "maturity_date": "2031-12-21",
                    "ytm_pct": 7.8,
                    "last_updated": days_ago(1),
                    "metadata": {"ytm_source": "NSE secondary quote"},
                },
            ],
            get_sovereign_yield_curve=lambda: [],
            get_active_mutual_funds=lambda **_: [],
            get_etf_matrix=lambda: [
                {"symbol": "GOLDBEES", "fund_name": "Nippon India ETF Gold BeES", "underlying_index": "Domestic Gold"},
                {"symbol": "NIFTYBEES", "fund_name": "Nippon India ETF Nifty 50 BeES", "underlying_index": "Nifty 50"},
            ],
            get_archived_reports=lambda **_: [],
        ):
            universe = terminal.get_normalized_opportunity_universe()
            rows = {row["id"]: row for row in universe}
            self.assertNotIn("SGBMATURED", rows)
            self.assertIn("SGBACTIVE", rows)
            self.assertEqual(rows["SGBACTIVE"]["seniority_tier"], "SOVEREIGN")

            gold = rows["GOLDBEES"]
            self.assertEqual(gold["seniority_tier"], "COMMODITY_BACKED_TRUST")
            self.assertNotEqual(gold["seniority_tier"], "SOVEREIGN")
            self.assertEqual(gold["detail_url"], "/etfs/GOLDBEES")

            nifty = rows["NIFTYBEES"]
            self.assertEqual(nifty["seniority_tier"], "EQUITY")
            self.assertEqual(nifty["detail_url"], "/etfs/NIFTYBEES")

    def test_quote_import_preview_apply_and_survival_across_catalogue_refresh(self):
        import os
        import tempfile
        import core.db.connection as db_conn
        from core.db.connection import init_db
        from core.db.debt import get_debt_security_by_isin, save_debt_security
        from scripts.import_terminal_debt_quotes import import_quotes

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_db = os.path.join(tmp_dir, "test_terminal_quotes.db")
            with patch.dict(os.environ, {"TESTING": "1", "FORCE_LOCAL_SQLITE": "1", "TEST_DB_PATH": tmp_db}):
                db_conn._DB_INITIALIZED = False
                db_conn._INITIALIZED_DBS.clear()
                init_db(force=True)
                isin = "INE000R00014"
                self.assertTrue(
                    save_debt_security(
                        {
                            "isin": isin,
                            "ticker": "TERMQUOTE1",
                            "instrument_name": "Terminal Issuer 9.50% Secured NCD 2099",
                            "issuer_name": "Terminal Issuer Ltd",
                            "maturity_date": "2099-12-31",
                            "ytm_pct": 7.0,
                            "metadata": {"rating_source": "Fixture"},
                        }
                    )
                )
                quote = {
                    "isin": isin,
                    "ytm_pct": 9.5,
                    "as_of": days_ago(0),
                    "source_url": "https://example.invalid/exchange/observation",
                }
                import_quotes([quote])
                self.assertNotIn("quoted_ytm_pct", get_debt_security_by_isin(isin)["metadata"])
                with self.assertRaises(ValueError):
                    import_quotes([quote, quote], apply=True)
                self.assertNotIn("quoted_ytm_pct", get_debt_security_by_isin(isin)["metadata"])

                import_quotes([quote], apply=True)
                security = get_debt_security_by_isin(isin)
                self.assertEqual(security["ytm_pct"], 7.0)
                self.assertEqual(security["metadata"]["quoted_ytm_pct"], 9.5)
                self.assertEqual(security["metadata"]["rating_source"], "Fixture")

                # Simulate a subsequent debt catalogue refresh that overwrites metadata_json without quote fields
                self.assertTrue(
                    save_debt_security(
                        {
                            "isin": isin,
                            "ticker": "TERMQUOTE1",
                            "instrument_name": "Terminal Issuer 9.50% Secured NCD 2099",
                            "issuer_name": "Terminal Issuer Ltd",
                            "maturity_date": "2099-12-31",
                            "ytm_pct": 7.0,
                            "metadata": {"rating_source": "Refreshed Catalogue Only"},
                        }
                    )
                )
                refreshed = get_debt_security_by_isin(isin)
                self.assertNotIn("quoted_ytm_pct", refreshed["metadata"])

                # Dedicated debt_quote_observations table preserves the live exchange observation
                universe = terminal.get_normalized_opportunity_universe()
                rows = {row["id"]: row for row in universe}
                self.assertIn(isin, rows)
                self.assertEqual(rows[isin]["metric_status"], "available")
                self.assertEqual(rows[isin]["gross_yield_pct"], 9.5)
            db_conn._DB_INITIALIZED = False
            db_conn._INITIALIZED_DBS.clear()
