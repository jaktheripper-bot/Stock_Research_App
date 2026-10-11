"""Verifies yfinance is opt-in and Angel One candles are the primary historical source."""
import os
import unittest
from unittest import mock

from core.analysis import fundamentals as fnd


def _candles(n=60):
    return [
        {"timestamp": f"2026-08-{(i % 28) + 1:02d}T00:00:00+05:30", "open": 100.0 + i, "high": 101.0 + i,
         "low": 99.0 + i, "close": 100.5 + i, "volume": 1000 + i}
        for i in range(n)
    ]


class TestYfinanceOptIn(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.pop("YFINANCE_FALLBACK", None)
        os.environ["YFINANCE_FALLBACK"] = "0"

    def tearDown(self):
        if self._prev is not None:
            os.environ["YFINANCE_FALLBACK"] = self._prev
        else:
            os.environ.pop("YFINANCE_FALLBACK", None)

    def test_flag_defaults_on_and_can_be_disabled(self):
        from core.config import yfinance_fallback_enabled
        os.environ.pop("YFINANCE_FALLBACK", None)
        self.assertTrue(yfinance_fallback_enabled())
        os.environ["YFINANCE_FALLBACK"] = "0"
        self.assertFalse(yfinance_fallback_enabled())

    def test_enrich_does_not_call_yfinance_when_off(self):
        with mock.patch.object(fnd.yf, "Ticker") as tk:
            out = fnd.enrich_fundamentals("ZZTESTONLY", {})
            tk.assert_not_called()
        self.assertEqual(out.get("pb_ratio"), "N/A")
        self.assertEqual(out.get("forward_pe"), "N/A")

    def test_historical_prices_use_angel_and_skip_yfinance(self):
        with mock.patch("core.ingestion.angel_one.AngelOneGateway.is_configured", return_value=True), \
             mock.patch("core.ingestion.angel_one.AngelOneGateway.get_historical_candles", return_value=_candles()), \
             mock.patch.object(fnd.yf, "Ticker") as tk:
            df = fnd.get_historical_prices("TESTANGELA" if False else "TSTA1")
            tk.assert_not_called()
        self.assertIsNotNone(df)
        self.assertIn("SMA50", df.columns)
        self.assertGreater(len(df), 5)

    def test_historical_prices_none_when_angel_down_and_flag_off(self):
        with mock.patch("core.ingestion.angel_one.AngelOneGateway.is_configured", return_value=False), \
             mock.patch.object(fnd.yf, "Ticker") as tk:
            self.assertIsNone(fnd.get_historical_prices("TESTANGELA" if False else "TSTB2"))
            tk.assert_not_called()


if __name__ == "__main__":
    unittest.main()
