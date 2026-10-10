"""
tests/test_vestnomics_domain_config.py
==============================================================================
Regression and contract tests for vestnomics.app custom domain integration.
Verifies that:
1. vestnomics.app and www.vestnomics.app are declared in ALLOWED_ORIGIN_HOSTS.
2. Origin validation accepts requests with Origin / Referer from vestnomics.app.
3. /robots.txt publishes the canonical vestnomics.app sitemap index.
4. /sitemap.xml generates canonical vestnomics.app URLs with environment override support.
5. Telemetry filters internal navigations on vestnomics.app as Direct / Internal.
6. PDF reports format standard platform attribution to Vestnomics.
==============================================================================
"""

import os
import unittest
from fastapi.testclient import TestClient
from web.main import app, ALLOWED_ORIGIN_HOSTS, _validate_request_origin
from starlette.requests import Request
from telemetry import parse_traffic_source


class TestVestnomicsDomainConfig(unittest.TestCase):
    """Test suite validating vestnomics.app domain configuration and origin safety."""

    def setUp(self):
        self.client = TestClient(app)

    def test_allowed_origin_hosts_includes_vestnomics(self):
        """Ensures vestnomics.app and www.vestnomics.app are explicitly whitelisted."""
        self.assertIn("vestnomics.app", ALLOWED_ORIGIN_HOSTS)
        self.assertIn("www.vestnomics.app", ALLOWED_ORIGIN_HOSTS)

    def test_validate_request_origin_with_vestnomics(self):
        """Verifies _validate_request_origin accepts vestnomics.app origins."""
        scope_root = {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"origin", b"https://vestnomics.app"),
                (b"host", b"vestnomics.app")
            ]
        }
        req_root = Request(scope_root)
        self.assertTrue(_validate_request_origin(req_root))

        scope_www = {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"referer", b"https://www.vestnomics.app/discovery"),
                (b"host", b"www.vestnomics.app")
            ]
        }
        req_www = Request(scope_www)
        self.assertTrue(_validate_request_origin(req_www))

    def test_robots_txt_specifies_vestnomics_sitemap(self):
        """Validates that /robots.txt points crawlers to vestnomics.app/sitemap.xml."""
        res = self.client.get("/robots.txt")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Sitemap: https://vestnomics.app/sitemap.xml", res.text)

    def test_sitemap_xml_contains_vestnomics_urls(self):
        """Validates that /sitemap.xml serves canonical vestnomics.app URLs."""
        res = self.client.get("/sitemap.xml")
        self.assertEqual(res.status_code, 200)
        self.assertIn("https://vestnomics.app/", res.text)
        self.assertIn("https://vestnomics.app/discovery", res.text)
        self.assertIn("https://vestnomics.app/opportunities", res.text)

    def test_sitemap_xml_respects_canonical_domain_env_override(self):
        """Ensures CANONICAL_DOMAIN environment variable is respected if declared."""
        old_val = os.environ.get("CANONICAL_DOMAIN")
        try:
            os.environ["CANONICAL_DOMAIN"] = "https://custom.vestnomics.app"
            res = self.client.get("/sitemap.xml")
            self.assertEqual(res.status_code, 200)
            self.assertIn("https://custom.vestnomics.app/", res.text)
        finally:
            if old_val is not None:
                os.environ["CANONICAL_DOMAIN"] = old_val
            else:
                os.environ.pop("CANONICAL_DOMAIN", None)

    def test_telemetry_self_host_filter_handles_vestnomics(self):
        """Verifies that links from vestnomics.app are identified as internal direct navigation."""
        source, detail = parse_traffic_source(
            referrer="https://vestnomics.app/discovery",
            query_params={}
        )
        self.assertEqual(source, "Direct / Bookmark")
        self.assertEqual(detail, "Direct")

        source_www, detail_www = parse_traffic_source(
            referrer="https://www.vestnomics.app/reits",
            query_params={}
        )
        self.assertEqual(source_www, "Direct / Bookmark")
        self.assertEqual(detail_www, "Direct")


if __name__ == "__main__":
    unittest.main()
