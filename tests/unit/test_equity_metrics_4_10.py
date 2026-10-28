"""Unit & Outside-In Contract Tests for Equity Metric Validation & Consistency (Feedback #4 & #10)."""

import os
import sqlite3
import tempfile
import unittest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from core.db.connection import init_db
from core.db.fundamentals import extract_fundamentals_from_report_text
from core.presentation.formatters import (
    format_52w_range,
    format_de_multiple,
    format_pct_metric,
    format_pe_multiple,
    format_standard_date,
    format_standard_timestamp,
    normalize_de_ratio,
    normalize_pe_raw,
)
from scripts.remediate_equity_metrics import run_remediation
from web.main import app


class TestEquityMetricsAndConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        init_db()
        cls.client = TestClient(app)

    def test_yfinance_de_percentage_scaling_and_null_preservation(self):
        """Verifies TCS (9.83% -> 0.10x) & INFY (9.54% -> 0.10x) scaling and zero 0.00x fabrication."""
        self.assertEqual(normalize_de_ratio(9.83, is_yfinance_pct=True, ticker="TCS"), 0.10)
        self.assertEqual(normalize_de_ratio(9.54, is_yfinance_pct=True, ticker="INFY"), 0.10)
        self.assertIsNone(normalize_de_ratio(None, ticker="TATASTEEL"))
        self.assertIsNone(normalize_de_ratio("N/A", ticker="TATASTEEL"))

        missing_de = format_de_multiple(None, ticker="TATASTEEL", sector_slug="COMMODITIES_ENERGY")
        self.assertEqual(missing_de["display"], "—")
        self.assertEqual(missing_de["status"], "missing")
        self.assertIn("Pending Filing Sync", missing_de["tooltip"])

        debt_free = format_de_multiple(0.0, ticker="WENDT", sector_slug="CAPITAL_GOODS_INFRA")
        self.assertEqual(debt_free["display"], "0.00x")
        self.assertEqual(debt_free["status"], "debt_free")

        bfsi_de = format_de_multiple(None, ticker="SBILIFE", company_name="SBI Life Insurance")
        self.assertEqual(bfsi_de["display"], "BFSI")
        self.assertEqual(bfsi_de["status"], "bfsi")
        self.assertIn("CRAR", bfsi_de["tooltip"])

        bfsi_distorted = format_de_multiple(8.45, ticker="HDFCBANK", sector_slug="BFSI")
        self.assertEqual(bfsi_distorted["display"], "BFSI")

    def test_pe_multiple_standardization_and_sentinels(self):
        """Verifies P/E strips 'Fair', maps losses to 'NM', and explains extreme multiples."""
        self.assertEqual(normalize_pe_raw("Fair"), "N/A")
        self.assertEqual(normalize_pe_raw("N/A (Loss-Making)"), "NM")
        self.assertEqual(normalize_pe_raw(-18.4), "NM")
        self.assertEqual(normalize_pe_raw("22.24x"), "22.24")

        fair_pe = format_pe_multiple("Fair")
        self.assertEqual(fair_pe["display"], "—")
        self.assertEqual(fair_pe["status"], "missing")

        nm_pe = format_pe_multiple("N/A (Loss-Making)")
        self.assertEqual(nm_pe["display"], "NM")
        self.assertIn("negative", nm_pe["tooltip"].lower())

        low_pe = format_pe_multiple("0.47")
        self.assertEqual(low_pe["display"], "0.5x")
        self.assertEqual(low_pe["status"], "distressed_low")

        high_pe = format_pe_multiple("120.82")
        self.assertEqual(high_pe["display"], "120.8x")
        self.assertEqual(high_pe["status"], "elevated")

    def test_timestamp_and_52w_range_standardization(self):
        """Verifies Unix epoch integers, ISO dates, SQLite naive UTC, and IST strings format strictly in IST."""
        import logging
        from datetime import datetime, timezone
        from core.db.connection import IST
        from core.logging_config import _ISTLogFormatter
        from core.audit.remediation_plan import generate_remediation_action_plan

        ts_str = format_standard_timestamp(1792870197)
        self.assertIn("IST", ts_str)
        self.assertNotEqual(ts_str, "1792870197")

        # All representations of 2026-10-28 16:37:54 IST (= 11:07:54 UTC) must render identically
        for variant in (
            "2026-10-28 11:07:54",               # SQLite CURRENT_TIMESTAMP naive UTC
            "2026-10-28 11:07:54+00:00",         # PostgreSQL UTC ISO
            "2026-10-28T11:07:54Z",              # REST Z ISO
            "2026-10-28 11:07:54 UTC",           # Explicit UTC label
            "2026-10-28 16:37:54+05:30",         # Explicit IST ISO
            "2026-10-28 16:37:54 IST",           # Explicit IST label
            "28-10-2026 16:37 IST",              # Support ticket IST format
            "28-Oct-2026 16:37 IST",             # User account IST format
            datetime(2026, 10, 28, 11, 7, 54, tzinfo=timezone.utc),
            datetime(2026, 10, 28, 16, 37, 54, tzinfo=IST),
        ):
            self.assertEqual(format_standard_timestamp(variant), "28 Oct 2026, 16:37 IST", f"Failed for {variant!r}")

        # Audit action plan and log formatter must strictly emit IST
        plan_md = generate_remediation_action_plan("AUD-20261028-180000", 100.0, [], {}, [])
        self.assertIn("IST", plan_md.splitlines()[1])
        self.assertNotIn("UTC", plan_md.splitlines()[1])

        fmt = _ISTLogFormatter("%(asctime)s %(message)s")
        rec = logging.LogRecord("test", logging.INFO, __file__, 1, "ping", (), None)
        self.assertIn("IST", fmt.format(rec))

        self.assertEqual(format_standard_date("2026-10-25"), "25 Oct 2026")
        self.assertEqual(format_52w_range(None, None), "—")
        self.assertEqual(format_52w_range("N/A", "N/A"), "—")
        self.assertEqual(format_52w_range(1976.0, 3336.7), "₹1,976.00 – ₹3,336.70")
        self.assertEqual(format_pct_metric(None)["display"], "—")

    def test_extract_fundamentals_from_report_text_pe_and_boilerplate_guard(self):
        """Verifies P/E extraction across table/prose/loss formats and skips legacy 22.4%/0.15 boilerplate."""
        md_table = "| Metric | Value |\n|---|---|\n| **Trailing P/E Ratio** | 29.87x |\n"
        self.assertEqual(extract_fundamentals_from_report_text(md_table).get("pe_ratio"), "29.87")

        prose_rng = "Valuation reflects a trailing P/E [Price-to-Earnings Ratio] of approximately 12.2x to 12.8x."
        self.assertEqual(extract_fundamentals_from_report_text(prose_rng).get("pe_ratio"), "12.50")

        loss_txt = "### Health Matrix\n- Valuation: Loss-Making\nCompany reported negative trailing EPS."
        self.assertEqual(extract_fundamentals_from_report_text(loss_txt).get("pe_ratio"), "NM")

        synth_boilerplate = (
            "Company operates with a debt-to-equity ratio of 0.15 `[CALCULATED METRIC]` "
            "alongside a Return on Capital Employed (ROCE) of 22.4% `[CALCULATED METRIC]`."
        )
        ext_synth = extract_fundamentals_from_report_text(synth_boilerplate)
        self.assertIsNone(ext_synth.get("roce"))
        self.assertIsNone(ext_synth.get("debt_to_equity"))

    def test_remediate_equity_metrics_dry_run_and_apply(self):
        """Verifies CLI remediation script against an isolated temp SQLite database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            tmp_db = tf.name

        try:
            conn = sqlite3.connect(tmp_db)
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE reports (ticker TEXT PRIMARY KEY, short_name TEXT, "
                "baseline_price REAL, baseline_pe TEXT, baseline_mcap REAL, report_text TEXT)"
            )
            cur.execute(
                "CREATE TABLE cached_fundamentals (ticker TEXT PRIMARY KEY, company_name TEXT, "
                "sector TEXT, industry TEXT, current_price REAL, market_cap REAL, pe_ratio TEXT, "
                "roce REAL, roe REAL, operating_margin REAL, debt_to_equity REAL, "
                "fifty_two_week_high REAL, fifty_two_week_low REAL, source TEXT, "
                "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            cur.execute(
                "CREATE TABLE discovery_reel (id INTEGER PRIMARY KEY AUTOINCREMENT, edition_date TEXT, "
                "ticker TEXT, company_name TEXT, sector TEXT, current_price REAL, pe_ratio TEXT, "
                "roce_pct REAL, debt_to_equity REAL, catalyst_headline TEXT, key_metrics_json TEXT, is_active INTEGER)"
            )

            cur.execute(
                "INSERT INTO reports VALUES ('TCS', 'Tata Consultancy Services', 2530.0, '15.65', 7.8e12, 'Debt-Free')"
            )
            cur.execute(
                "INSERT INTO cached_fundamentals (ticker, company_name, sector, industry, current_price, market_cap, "
                "pe_ratio, roce, roe, operating_margin, debt_to_equity, fifty_two_week_high, fifty_two_week_low, source) "
                "VALUES ('TCS', 'TCS', 'Technology', 'IT Services', "
                "2530.0, 7.8e12, '15.65', 55.0, 48.0, 26.0, 9.83, 4500.0, 2400.0, 'LOCAL_DB_HARMONIZED')"
            )
            cur.execute(
                "INSERT INTO reports VALUES ('RAILTEL', 'RailTel Corp', 248.0, 'N/A', 8e10, "
                "'Trailing P/E Ratio: 22.2x based on audited FY earnings.')"
            )
            cur.execute(
                "INSERT INTO cached_fundamentals (ticker, company_name, sector, industry, current_price, market_cap, "
                "pe_ratio, roce, roe, operating_margin, debt_to_equity, fifty_two_week_high, fifty_two_week_low, source) "
                "VALUES ('RAILTEL', 'RailTel Corp', 'Telecom', 'Infra', "
                "248.0, 8e10, 'N/A', 18.4, 15.2, 19.0, 0.0, 618.0, 240.0, 'LOCAL_DB_HARMONIZED')"
            )
            cur.execute(
                "INSERT INTO reports VALUES ('PAGEIND', 'Page Industries', 500.0, '22.5', 2.5e10, 'Moat: Wide')"
            )
            cur.execute(
                "INSERT INTO cached_fundamentals (ticker, company_name, sector, industry, current_price, market_cap, "
                "pe_ratio, roce, roe, operating_margin, debt_to_equity, fifty_two_week_high, fifty_two_week_low, source) "
                "VALUES ('PAGEIND', 'Page Industries', 'Consumer', 'Apparel', "
                "33774.65, 3.7e11, '58.40', 44.0, 40.0, 20.0, 0.12, 48000.0, 32000.0, 'LOCAL_DB_HARMONIZED')"
            )
            cur.execute(
                "INSERT INTO reports VALUES ('BAJAJ-AUTO', 'Bajaj Auto Ltd', 10080.0, '22.50', 2.5e10, 'Auto OEM')"
            )
            cur.execute(
                "INSERT INTO cached_fundamentals (ticker, company_name, sector, industry, current_price, market_cap, "
                "pe_ratio, roce, roe, operating_margin, debt_to_equity, fifty_two_week_high, fifty_two_week_low, source) "
                "VALUES ('BAJAJ-AUTO', 'Bajaj Auto Ltd', 'Auto', 'Two Wheelers', "
                "10080.0, 2.5e10, '22.50', 22.0, NULL, NULL, 0.15, NULL, NULL, 'LOCAL_DB_HARMONIZED')"
            )
            cur.execute(
                "INSERT INTO reports VALUES ('SBILIFE', 'SBI Life Insurance', 1680.0, NULL, 1.6e12, 'Insurer')"
            )
            cur.execute(
                "INSERT INTO cached_fundamentals (ticker, company_name, sector, industry, current_price, market_cap, "
                "pe_ratio, roce, roe, operating_margin, debt_to_equity, fifty_two_week_high, fifty_two_week_low, source) "
                "VALUES ('SBILIFE', 'SBI Life Insurance', 'Financials', 'Insurance', "
                "1680.0, 1.6e12, '72.10', NULL, 14.0, NULL, 0.15, 1900.0, 1300.0, 'LOCAL_DB_HARMONIZED')"
            )
            cur.execute("INSERT INTO reports VALUES ('TOMATO', 'Tomato Typo', 323.0, 'N/A', 0.0, 'Typo')")
            cur.execute(
                "INSERT INTO discovery_reel (edition_date, ticker, company_name, sector, current_price, pe_ratio, "
                "roce_pct, debt_to_equity, catalyst_headline, key_metrics_json, is_active) "
                "VALUES ('2026-10-25', 'ACE', 'Action Construction', 'Capital Goods', 1227.5, 'Fair', "
                "27.8, 0.05, 'Filing', '{\"pe\": \"Fair\"}', 1)"
            )
            cur.execute(
                "INSERT INTO discovery_reel (edition_date, ticker, company_name, sector, current_price, pe_ratio, "
                "roce_pct, debt_to_equity, catalyst_headline, key_metrics_json, is_active) "
                "VALUES ('2026-10-23', 'GENSOL', 'Gensol Eng', 'Power', 10.76, '0.47', "
                "20.2, 0.65, 'Filing', '{\"pe\": \"0.47\"}', 1)"
            )
            conn.commit()
            conn.close()

            # 1. Dry-run must NOT mutate the database
            dry = run_remediation(sqlite_path=tmp_db, apply_changes=False, quiet=True)
            self.assertEqual(len(dry["de_100x_scaled_fixes"]), 1)
            conn = sqlite3.connect(tmp_db)
            self.assertEqual(
                conn.execute("SELECT debt_to_equity FROM cached_fundamentals WHERE ticker='TCS'").fetchone()[0],
                9.83,
            )
            conn.close()

            # 2. Apply must commit normalizations while preserving TOMATO without --purge-duplicates
            applied = run_remediation(sqlite_path=tmp_db, apply_changes=True, quiet=True)
            self.assertEqual(len(applied["purged_tickers"]), 0)
            conn = sqlite3.connect(tmp_db)
            self.assertEqual(
                conn.execute("SELECT debt_to_equity FROM cached_fundamentals WHERE ticker='TCS'").fetchone()[0],
                0.10,
            )
            self.assertIsNone(
                conn.execute("SELECT debt_to_equity FROM cached_fundamentals WHERE ticker='SBILIFE'").fetchone()[0]
            )
            self.assertEqual(
                conn.execute("SELECT pe_ratio FROM cached_fundamentals WHERE ticker='RAILTEL'").fetchone()[0],
                "22.20",
            )
            self.assertEqual(
                conn.execute("SELECT baseline_price FROM reports WHERE ticker='PAGEIND'").fetchone()[0],
                33774.65,
            )
            bajaj_cf = conn.execute(
                "SELECT current_price, market_cap, pe_ratio, roce, debt_to_equity "
                "FROM cached_fundamentals WHERE ticker='BAJAJ-AUTO'"
            ).fetchone()
            self.assertEqual(bajaj_cf[0], 10080.0)
            self.assertIsNone(bajaj_cf[1])
            self.assertEqual(bajaj_cf[2], "N/A")
            self.assertIsNone(bajaj_cf[3])
            self.assertIsNone(bajaj_cf[4])
            self.assertEqual(
                conn.execute("SELECT pe_ratio FROM discovery_reel WHERE ticker='ACE'").fetchone()[0],
                "N/A",
            )
            self.assertEqual(
                conn.execute("SELECT is_active FROM discovery_reel WHERE ticker='GENSOL'").fetchone()[0],
                0,
            )
            self.assertIsNotNone(conn.execute("SELECT ticker FROM reports WHERE ticker='TOMATO'").fetchone())
            conn.close()

            # 3. Explicit purge with --confirm-delete removes TOMATO
            purged = run_remediation(
                sqlite_path=tmp_db,
                apply_changes=True,
                purge_duplicates=True,
                confirm_delete=True,
                quiet=True,
            )
            self.assertIn("TOMATO", purged["purged_tickers"])
            conn = sqlite3.connect(tmp_db)
            self.assertIsNone(conn.execute("SELECT ticker FROM reports WHERE ticker='TOMATO'").fetchone())
            conn.close()
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

    def test_outside_in_rendered_templates_metric_consistency(self):
        """Verifies /, /equities, and /discovery render Metric Key, tooltips, and zero 'Fair'/'₹N/A – ₹N/A'."""
        for route in ("/", "/equities", "/discovery"):
            with self.subTest(route=route):
                res = self.client.get(route)
                self.assertEqual(res.status_code, 200)
                html = res.text
                self.assertNotIn("{{", html)
                self.assertNotIn("{%", html)
                self.assertNotIn("₹N/A – ₹N/A", html)
                self.assertIn("Metric Key:", html)

                soup = BeautifulSoup(html, "html.parser")
                for cell in soup.select(".tnum"):
                    txt = cell.get_text(strip=True)
                    self.assertNotEqual(txt, "Fair", f"Qualitative 'Fair' leaked into numeric .tnum cell on {route}")

    def test_search_equities_formats_string_baseline_pe_without_crash(self):
        """Regression test: search_equities formats TEXT baseline_pe ('N/A' or '22.20') cleanly."""
        from core.db.reports import save_report_to_archive
        from core.search.product_search import search_equities
        from core.db.connection import get_db_connection

        save_report_to_archive(
            stock_data={"ticker": "RAILTELTEST", "short_name": "RailTel Test Corp", "current_price": 248.0, "pe_ratio": "N/A"},
            report_text="### Health Matrix\n- Moat: Wide\n" + (" Verified filing content." * 30),
        )
        try:
            hits = search_equities("RAILTELTEST", limit=5)
            self.assertTrue(any(h["identifier"] == "RAILTELTEST" for h in hits))
            hit = next(h for h in hits if h["identifier"] == "RAILTELTEST")
            self.assertEqual(hit["details"]["pe"], "—")
            self.assertEqual(hit["details"]["price"], "₹248.00")
        finally:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM reports WHERE ticker = 'RAILTELTEST'")
            cur.execute("DELETE FROM report_revisions WHERE ticker = 'RAILTELTEST'")
            cur.execute("DELETE FROM compliance_audit_log WHERE ticker = 'RAILTELTEST'")
            conn.commit()
            cur.close()
            conn.close()

    def test_yfinance_fallback_disabled_by_default_in_production(self):
        """Verifies YFINANCE_FALLBACK defaults to False in production now that SmartAPI + BSE Direct are primary."""
        from core.config import yfinance_fallback_enabled

        old_testing = os.environ.pop("TESTING", None)
        old_yf = os.environ.pop("YFINANCE_FALLBACK", None)
        old_skip = os.environ.get("SKIP_DOTENV_IN_SUBPROCESS")
        os.environ["SKIP_DOTENV_IN_SUBPROCESS"] = "1"
        try:
            self.assertFalse(yfinance_fallback_enabled())
            os.environ["YFINANCE_FALLBACK"] = "1"
            self.assertTrue(yfinance_fallback_enabled())
            os.environ["YFINANCE_FALLBACK"] = "0"
            self.assertFalse(yfinance_fallback_enabled())
        finally:
            if old_testing is not None:
                os.environ["TESTING"] = old_testing
            else:
                os.environ.pop("TESTING", None)
            if old_yf is not None:
                os.environ["YFINANCE_FALLBACK"] = old_yf
            else:
                os.environ.pop("YFINANCE_FALLBACK", None)
            if old_skip is not None:
                os.environ["SKIP_DOTENV_IN_SUBPROCESS"] = old_skip
            else:
                os.environ.pop("SKIP_DOTENV_IN_SUBPROCESS", None)


if __name__ == "__main__":
    unittest.main()
