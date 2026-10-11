"""
Consolidated Market Data Gateways & Auth Security Suite
========================================================
Unifies:
1. Angel One SmartAPI Gateway, Level-2 Depth Analytics, TOTP, and Proxies
2. yfinance Opt-in Flag & Historical Price Source Prioritization
3. Local TOTP 2FA QR Generation (No 3rd Party Leaks)
"""
import base64
import os
from pathlib import Path
import re
import unittest
from unittest.mock import MagicMock, patch

from core.analysis import fundamentals as fnd
from core.ingestion.angel_one import AngelOneGateway, generate_rfc6238_totp
from web.main import _build_local_qr_data_uri

ROOT = Path(__file__).resolve().parent.parent


def _candles(n=60):
    return [
        {
            "timestamp": f"2026-08-{(i % 28) + 1:02d}T00:00:00+05:30",
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 1000 + i,
        }
        for i in range(n)
    ]


# ==============================================================================
# 1. Angel One SmartAPI Gateway & Order Depth
# ==============================================================================
class TestAngelOneGateway(unittest.TestCase):
    def test_rfc6238_totp_generation(self):
        secret = "JBSWY3DPEHPK3PXP"
        totp = generate_rfc6238_totp(secret)
        self.assertIsInstance(totp, str)
        self.assertEqual(len(totp), 6)
        self.assertTrue(totp.isdigit())

    def test_rfc6238_totp_handles_spaces_and_lowercase(self):
        secret = "jbsw y3dp ehpk 3pxp"
        totp = generate_rfc6238_totp(secret)
        self.assertEqual(len(totp), 6)
        self.assertTrue(totp.isdigit())

    def test_is_configured_returns_false_when_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(AngelOneGateway.is_configured())

    def test_is_configured_returns_true_when_all_present(self):
        env_vars = {
            "ANGEL_API_KEY": "test_key",
            "ANGEL_CLIENT_CODE": "test_client",
            "ANGEL_PIN": "1234",
            "ANGEL_TOTP_KEY": "JBSWY3DPEHPK3PXP",
        }
        with patch.dict(os.environ, env_vars):
            self.assertTrue(AngelOneGateway.is_configured())

    def test_proxy_config_resolution(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(AngelOneGateway.get_proxy_config())

        proxy_url = "http://user:pass@proxy.quotaguard.com:9293"
        with patch.dict(os.environ, {"SMARTAPI_PROXY_URL": proxy_url}):
            proxies = AngelOneGateway.get_proxy_config()
            self.assertIsNotNone(proxies)
            self.assertEqual(proxies.get("http"), proxy_url)
            self.assertEqual(proxies.get("https"), proxy_url)

    @patch("requests.get")
    def test_probe_outbound_ip_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"ip": "54.217.100.200"}'
        mock_resp.json.return_value = {"ip": "54.217.100.200"}
        mock_get.return_value = mock_resp

        res = AngelOneGateway.probe_outbound_ip()
        self.assertEqual(res["outbound_ip"], "54.217.100.200")
        self.assertEqual(res["status"], "SUCCESS")

    def test_unauthenticated_quote_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            res = AngelOneGateway.get_quote_with_depth("NSE", "3045")
            self.assertIsNone(res)

    def test_resolve_symbol_token_nse(self):
        exch, token = AngelOneGateway.resolve_symbol_token("INFY")
        self.assertEqual(exch, "NSE")
        self.assertEqual(token, "1594")

        exch, token = AngelOneGateway.resolve_symbol_token("RELIANCE")
        self.assertEqual(exch, "NSE")
        self.assertEqual(token, "2885")

    def test_resolve_symbol_token_bse_fallback(self):
        exch, token = AngelOneGateway.resolve_symbol_token("ONIDA")
        self.assertEqual(exch, "BSE")
        self.assertEqual(token, "500279")

    def test_compute_depth_analytics(self):
        buy_book = [{"price": 100.0, "quantity": 1000}, {"price": 99.5, "quantity": 500}]
        sell_book = [{"price": 100.5, "quantity": 200}, {"price": 101.0, "quantity": 300}]
        analytics = AngelOneGateway.compute_depth_analytics(buy_book, sell_book)
        self.assertEqual(analytics["total_buy_qty"], 1500)
        self.assertEqual(analytics["total_sell_qty"], 500)
        self.assertAlmostEqual(analytics["order_imbalance_ratio"], 0.5, places=2)
        self.assertEqual(analytics["depth_pressure_regime"], "ACCUMULATION_DOMINANT")
        self.assertGreater(analytics["bid_ask_spread_bps"], 0.0)

    def test_format_dossier_market_depth_badge(self):
        dummy_quote = {
            "order_imbalance_ratio": 0.35,
            "upper_circuit": 1500.0,
            "lower_circuit": 1300.0,
            "ltp": 1420.0,
        }
        badge = AngelOneGateway.format_dossier_market_depth_badge(dummy_quote)
        self.assertIn("Exchange Level-2 Depth", badge)
        self.assertIn("Institutional Accumulation", badge)
        self.assertIn("Circuit Bands", badge)


# ==============================================================================
# 2. yfinance Opt-in & Fallback Verification
# ==============================================================================
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
        with patch.object(fnd.yf, "Ticker") as tk:
            out = fnd.enrich_fundamentals("ZZTESTONLY", {})
            tk.assert_not_called()
        self.assertEqual(out.get("pb_ratio"), "N/A")
        self.assertEqual(out.get("forward_pe"), "N/A")

    def test_historical_prices_use_angel_and_skip_yfinance(self):
        with patch("core.ingestion.angel_one.AngelOneGateway.is_configured", return_value=True), \
             patch("core.ingestion.angel_one.AngelOneGateway.get_historical_candles", return_value=_candles()), \
             patch.object(fnd.yf, "Ticker") as tk:
            df = fnd.get_historical_prices("TSTA1")
            tk.assert_not_called()
        self.assertIsNotNone(df)
        self.assertIn("SMA50", df.columns)
        self.assertGreater(len(df), 5)

    def test_historical_prices_none_when_angel_down_and_flag_off(self):
        with patch("core.ingestion.angel_one.AngelOneGateway.is_configured", return_value=False), \
             patch.object(fnd.yf, "Ticker") as tk:
            self.assertIsNone(fnd.get_historical_prices("TSTB2"))
            tk.assert_not_called()


# ==============================================================================
# 3. Local TOTP QR Code Generation
# ==============================================================================
class TestLocalTotpQr(unittest.TestCase):
    def test_qr_is_inline_svg_data_uri(self):
        uri = _build_local_qr_data_uri("otpauth://totp/Test:a@b.com?secret=ABC&issuer=Test")
        self.assertTrue(uri.startswith("data:image/svg+xml;base64,"))
        svg = base64.b64decode(uri.split(",", 1)[1]).decode("utf-8")
        self.assertIn("<svg", svg)

    def test_no_third_party_qr_service_in_source(self):
        src = (ROOT / "web" / "main.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"qrserver\.com|chart\.googleapis\.com/chart\?cht=qr", src))


if __name__ == "__main__":
    unittest.main()
