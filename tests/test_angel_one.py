"""
Unit Tests for Angel One SmartAPI Gateway and Selective Proxy Routing
===================================================================
Tests:
1. RFC 6238 Pure Python TOTP Generation.
2. Selective Proxy Configuration Resolution.
3. Outbound Static IP Discovery Probe.
4. Fallback Safety when Credentials are Absent.
"""

import unittest
import os
from unittest.mock import patch, MagicMock
from core.ingestion.angel_one import AngelOneGateway, generate_rfc6238_totp


class TestAngelOneGateway(unittest.TestCase):
    def test_rfc6238_totp_generation(self):
        # Known standard base32 secret
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
        # Empty
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(AngelOneGateway.get_proxy_config())

        # Set
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


if __name__ == "__main__":
    unittest.main()
