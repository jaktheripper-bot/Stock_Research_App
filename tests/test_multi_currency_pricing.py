"""
Unit and Integration Tests for Indicative Multi-Currency Pricing Architecture.
Validates:
1. Core currency conversion math, rates, and 3.5% international cross-border buffer
2. Location detection via Cloudflare CF-IPCountry headers, cookies, and query params
3. GET /api/billing/currencies endpoint response contract
4. GET /pricing SSR page rendering with currency selector dropdown, data attributes, and transparency notice
"""

import os
import unittest
from fastapi.testclient import TestClient

os.environ["TESTING"] = "1"

from web.main import app, init_db
from core.billing.currency import (
    SUPPORTED_CURRENCIES,
    convert_inr_to_currency,
    resolve_currency_for_request,
    COUNTRY_TO_CURRENCY_MAP,
)


class TestMultiCurrencyPricing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_inr_base_conversion(self):
        """INR base conversions should have zero buffer and exact figures."""
        conv = convert_inr_to_currency(299.0, "INR")
        self.assertEqual(conv["currency"], "INR")
        self.assertEqual(conv["symbol"], "₹")
        self.assertEqual(conv["effective_amount"], 299.0)
        self.assertEqual(conv["formatted"], "₹299")
        self.assertTrue(conv["is_base"])
        self.assertEqual(conv["buffer_pct"], 0.0)

    def test_usd_conversion_with_cross_border_buffer(self):
        """USD conversion must apply the 3.5% international buffer."""
        conv = convert_inr_to_currency(299.0, "USD")
        self.assertEqual(conv["currency"], "USD")
        self.assertEqual(conv["symbol"], "$")
        self.assertFalse(conv["is_base"])
        self.assertEqual(conv["buffer_pct"], 0.035)

        # 299 / 88.50 * 1.035 = 3.4968 -> 3.50
        expected = round((299.0 / 88.50) * 1.035, 2)
        self.assertEqual(conv["effective_amount"], expected)
        self.assertEqual(conv["formatted"], f"${expected:.2f}")
        self.assertIn("3.5%", conv["notice"])
        self.assertIn("Razorpay", conv["notice"])

    def test_all_supported_currencies_exist(self):
        """Ensures all 3 global investor currencies are defined with valid metadata."""
        expected_currencies = ["INR", "USD", "EUR"]
        self.assertEqual(len(SUPPORTED_CURRENCIES), 3)
        for code in expected_currencies:
            self.assertIn(code, SUPPORTED_CURRENCIES)
            curr = SUPPORTED_CURRENCIES[code]
            self.assertGreater(curr["rate_vs_inr"], 0)
            self.assertTrue(bool(curr["symbol"]))
            self.assertTrue(bool(curr["flag"]))

    def test_country_to_currency_mapping(self):
        """Validates major geopolitical regions map to expected currencies."""
        self.assertEqual(COUNTRY_TO_CURRENCY_MAP.get("US"), "USD")
        self.assertEqual(COUNTRY_TO_CURRENCY_MAP.get("DE"), "EUR")
        self.assertEqual(COUNTRY_TO_CURRENCY_MAP.get("FR"), "EUR")
        self.assertEqual(COUNTRY_TO_CURRENCY_MAP.get("IN"), "INR")

    def test_api_billing_currencies_endpoint(self):
        """Validates GET /api/billing/currencies contract."""
        resp = self.client.get("/api/billing/currencies")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("base_currency"), "INR")
        self.assertEqual(data.get("buffer_pct"), 3.5)
        self.assertIn("USD", data.get("currencies", {}))
        self.assertIn("EUR", data.get("currencies", {}))
        self.assertIn("INR", data.get("currencies", {}))
        self.assertEqual(len(data.get("currencies", {})), 3)

    def test_pricing_page_renders_currency_dropdown_and_data_attributes(self):
        """Validates that /pricing SSR contains the dropdown, transparency notice, and base prices."""
        resp = self.client.get("/pricing")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # 1. Base price and Single Pass still present (backward compatibility)
        self.assertIn("₹299", html)
        self.assertIn("Single Research Pass", html)

        # 2. Currency Selector dropdown present
        self.assertIn('id="currencySelect"', html)
        self.assertIn('value="USD"', html)
        self.assertIn('value="EUR"', html)
        self.assertIn('value="INR"', html)

        # 3. Dynamic attributes present
        self.assertIn('data-base-inr="299"', html)
        self.assertIn('data-base-inr="699"', html)
        self.assertIn('data-base-inr="1799"', html)

        # 4. Transparency notice present
        self.assertIn('id="currencyNoticeBanner"', html)
        self.assertIn('Indicative Local Currency Pricing:', html)
        self.assertIn('3.5%', html)

    def test_pricing_page_location_detection_via_header(self):
        """Validates that international CF-IPCountry header selects local currency."""
        # US visitor
        resp_us = self.client.get("/pricing", headers={"cf-ipcountry": "US"})
        self.assertEqual(resp_us.status_code, 200)
        self.assertIn('value="USD" selected', resp_us.text)

        # Eurozone visitor
        resp_eu = self.client.get("/pricing", headers={"cf-ipcountry": "DE"})
        self.assertEqual(resp_eu.status_code, 200)
        self.assertIn('value="EUR" selected', resp_eu.text)

        # Other international visitor maps to USD
        resp_intl = self.client.get("/pricing", headers={"cf-ipcountry": "GB"})
        self.assertEqual(resp_intl.status_code, 200)
        self.assertIn('value="USD" selected', resp_intl.text)

        # Query param override takes precedence
        resp_query = self.client.get("/pricing?currency=EUR", headers={"cf-ipcountry": "US"})
        self.assertEqual(resp_query.status_code, 200)
        self.assertIn('value="EUR" selected', resp_query.text)


if __name__ == "__main__":
    unittest.main()
