"""Tests for the Nifty 100 universe registry and batch generation helpers."""

import unittest
from datetime import datetime, timezone, timedelta
from core.universe.nifty100 import (
    NIFTY_100_CONSTITUENTS,
    get_nifty100_symbols,
    get_nifty100_constituent,
    is_nifty100_stock,
)
from bse_master import resolve_bse_scrip_code
from scripts.generate_nifty100_reports import is_report_fresh

class TestNifty100Universe(unittest.TestCase):
    def test_nifty100_universe_completeness(self):
        """Ensures exactly 100 unique constituents exist in the universe."""
        self.assertEqual(len(NIFTY_100_CONSTITUENTS), 100)
        symbols = get_nifty100_symbols()
        self.assertEqual(len(symbols), 100)
        self.assertEqual(len(set(symbols)), 100)

    def test_nifty100_scrip_resolution(self):
        """Verifies that all 100 constituents resolve cleanly to BSE scrip codes."""
        for item in NIFTY_100_CONSTITUENTS:
            sym = item["symbol"]
            scrip = resolve_bse_scrip_code(sym)
            self.assertIsNotNone(scrip, f"Failed to resolve BSE scrip for {sym}")
            self.assertTrue(len(str(scrip)) >= 6, f"Invalid scrip {scrip} for {sym}")

    def test_lookup_utilities(self):
        """Tests symbol lookup and membership check helpers."""
        self.assertTrue(is_nifty100_stock("RELIANCE"))
        self.assertTrue(is_nifty100_stock("reliance"))
        self.assertTrue(is_nifty100_stock("TCS"))
        self.assertFalse(is_nifty100_stock("NON_EXISTENT_TICKER_XYZ"))

        reliance = get_nifty100_constituent("RELIANCE")
        self.assertIsNotNone(reliance)
        self.assertEqual(reliance["bse_scrip"], "500325")

    def test_is_report_fresh(self):
        """Validates the 14-day freshness window evaluator."""
        now = datetime.now(timezone.utc)
        fresh_ts = (now - timedelta(days=2)).isoformat()
        stale_ts = (now - timedelta(days=20)).isoformat()

        self.assertTrue(is_report_fresh({"report_text": "sample text", "timestamp": fresh_ts}))
        self.assertFalse(is_report_fresh({"report_text": "sample text", "timestamp": stale_ts}))
        self.assertFalse(is_report_fresh({"report_text": "", "timestamp": fresh_ts}))
        self.assertFalse(is_report_fresh(None))

if __name__ == "__main__":
    unittest.main()
