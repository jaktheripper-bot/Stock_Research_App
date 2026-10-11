"""Share button, canonical tags and 'Shared Link' attribution."""
import re
import unittest

from fastapi.testclient import TestClient

from telemetry import parse_traffic_source


class TestSharedLinkAttribution(unittest.TestCase):
    def test_share_utm_is_labelled_shared_link(self):
        self.assertEqual(parse_traffic_source("", {"utm_source": "share"})[0], "Shared Link")
        self.assertEqual(parse_traffic_source("https://www.linkedin.com/", {"utm_source": "SHARE"})[0], "Shared Link")

    def test_other_campaigns_keep_their_label(self):
        self.assertEqual(parse_traffic_source("", {"utm_source": "newsletter"})[0], "newsletter")


class TestCanonicalAndShareButton(unittest.TestCase):
    def setUp(self):
        from web.main import app
        self.client = TestClient(app)

    def _canonical(self, html):
        m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
        return m.group(1) if m else None

    def test_home_has_canonical_without_tracking_params(self):
        resp = self.client.get("/pricing?utm_source=share&utm_medium=referral&utm_campaign=dossier")
        canon = self._canonical(resp.text)
        self.assertIsNotNone(canon)
        self.assertTrue(canon.endswith("/pricing"))
        self.assertNotIn("utm_", canon)
        self.assertIn('property="og:url"', resp.text)

    def test_compare_canonical_keeps_both_tickers_and_has_share_button(self):
        resp = self.client.get("/compare?a=infy&b=tcs&utm_source=share")
        canon = self._canonical(resp.text)
        self.assertIsNotNone(canon)
        import html as html_mod
        self.assertTrue(html_mod.unescape(canon).endswith("/compare?a=INFY&b=TCS"))
        self.assertNotIn("utm_", canon)
        self.assertIn("shareCurrentPage('compare')", resp.text)

    def test_trailing_slash_is_normalised(self):
        resp = self.client.get("/pricing/", follow_redirects=True)
        canon = self._canonical(resp.text)
        if canon:
            self.assertFalse(canon.endswith("/"))


if __name__ == "__main__":
    unittest.main()
