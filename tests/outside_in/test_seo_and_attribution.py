"""
Consolidated SEO, Domain Configuration & Traffic Attribution Test Suite
========================================================================
Unifies:
1. SEO & GEO Tracking (AI referrers, crawler bot logging, honest defaults)
2. Share Button, Clean-URL capturing & self-referencing canonical tags
3. vestnomics.app canonical domain whitelisting, origin checks, sitemap & robots.txt
"""
import html as html_mod
import os
import re
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from starlette.requests import Request

from core.db.telemetry import _build_telemetry_time_filter, _seo_channel
from telemetry import (
    classify_bot,
    extract_geo,
    parse_traffic_source,
    parse_user_agent,
)
from web.main import ALLOWED_ORIGIN_HOSTS, app, _validate_request_origin


# ==============================================================================
# 1. AI Referrers & Channel Grouping
# ==============================================================================
class TestAiReferrers(unittest.TestCase):
    def test_ai_engines_are_classified(self):
        self.assertEqual(parse_traffic_source("https://chatgpt.com/", {})[0], "ChatGPT (AI)")
        self.assertEqual(parse_traffic_source("https://www.perplexity.ai/search", {})[0], "Perplexity (AI)")
        self.assertEqual(parse_traffic_source("https://claude.ai/", {})[0], "Claude (AI)")
        self.assertEqual(parse_traffic_source("https://copilot.microsoft.com/", {})[0], "Copilot (AI)")

    def test_gemini_is_not_counted_as_google_search(self):
        self.assertEqual(parse_traffic_source("https://gemini.google.com/app", {})[0], "Gemini (AI)")
        self.assertEqual(parse_traffic_source("https://www.google.com/search?q=x", {})[0], "Google Search")

    def test_channel_grouping(self):
        self.assertEqual(_seo_channel("Google Search"), "Organic Search")
        self.assertEqual(_seo_channel("ChatGPT (AI)"), "AI Search")
        self.assertEqual(_seo_channel("LinkedIn"), "Other")


# ==============================================================================
# 2. Honest Defaults (No Synthetic Demographics)
# ==============================================================================
class TestHonestDefaults(unittest.TestCase):
    def test_missing_geo_is_unknown_not_india(self):
        self.assertEqual(extract_geo({}), "Unknown")
        self.assertEqual(extract_geo({"user-agent": "x"}), "Unknown")
        self.assertEqual(extract_geo({"cf-ipcountry": "in"}), "IN")

    def test_missing_user_agent_is_unknown(self):
        self.assertEqual(parse_user_agent("")["device"], "Unknown")


# ==============================================================================
# 3. Crawler Logging & Filtering
# ==============================================================================
class TestCrawlerLogging(unittest.TestCase):
    def test_classify_bot(self):
        self.assertEqual(classify_bot("Mozilla/5.0 (compatible; Googlebot/2.1)")[0], "Googlebot")
        self.assertEqual(classify_bot("Mozilla/5.0 AppleWebKit; compatible; GPTBot/1.1")[1], "AI")
        self.assertIsNone(classify_bot("Mozilla/5.0 (Macintosh) Safari/605"))
        self.assertIsNone(classify_bot(""))

    def test_visitor_filter_excludes_bot_events_but_seo_view_can_include(self):
        self.assertIn("BOT_CRAWL", _build_telemetry_time_filter("", days=7))
        self.assertNotIn("BOT_CRAWL", _build_telemetry_time_filter("", days=7, include_bots=True))

    def test_middleware_logs_crawler_but_not_humans(self):
        client = TestClient(app)
        with mock.patch("core.db.telemetry.record_crawler_hit") as hit:
            client.get("/robots.txt", headers={"user-agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"})
            client.get("/robots.txt", headers={"user-agent": "Mozilla/5.0 (Macintosh) Safari/605"})
            time.sleep(0.3)
            self.assertEqual(hit.call_count, 1)
            self.assertEqual(hit.call_args[0][0], "Googlebot")
            self.assertEqual(hit.call_args[0][2], "/robots.txt")


# ==============================================================================
# 4. Shared Link Attribution
# ==============================================================================
class TestSharedLinkAttribution(unittest.TestCase):
    def test_share_utm_is_labelled_shared_link(self):
        self.assertEqual(parse_traffic_source("", {"utm_source": "share"})[0], "Shared Link")
        self.assertEqual(parse_traffic_source("https://www.linkedin.com/", {"utm_source": "SHARE"})[0], "Shared Link")

    def test_other_campaigns_keep_their_label(self):
        self.assertEqual(parse_traffic_source("", {"utm_source": "newsletter"})[0], "newsletter")


# ==============================================================================
# 5. Canonical URLs & Share Buttons
# ==============================================================================
class TestCanonicalAndShareButton(unittest.TestCase):
    def setUp(self):
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
        self.assertTrue(html_mod.unescape(canon).endswith("/compare?a=INFY&b=TCS"))
        self.assertNotIn("utm_", canon)
        self.assertIn("shareCurrentPage('compare')", resp.text)

    def test_trailing_slash_is_normalised(self):
        resp = self.client.get("/pricing/", follow_redirects=True)
        canon = self._canonical(resp.text)
        if canon:
            self.assertFalse(canon.endswith("/"))


# ==============================================================================
# 6. Vestnomics Domain Configuration & Whitelisting
# ==============================================================================
class TestMoatnomicsDomainConfig(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_allowed_origin_hosts_includes_moatnomics(self):
        self.assertIn("moatnomics.com", ALLOWED_ORIGIN_HOSTS)
        self.assertIn("www.moatnomics.com", ALLOWED_ORIGIN_HOSTS)
        self.assertIn("vestnomics.app", ALLOWED_ORIGIN_HOSTS)
        self.assertIn("www.vestnomics.app", ALLOWED_ORIGIN_HOSTS)
        self.assertIn("vestfolio.app", ALLOWED_ORIGIN_HOSTS)
        self.assertIn("www.vestfolio.app", ALLOWED_ORIGIN_HOSTS)

    def test_validate_request_origin_with_moatnomics(self):
        scope_root = {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [
                (b"origin", b"https://moatnomics.com"),
                (b"host", b"moatnomics.com")
            ]
        }
        req_root = Request(scope_root)
        self.assertTrue(_validate_request_origin(req_root))

        scope_www = {
            "type": "http",
            "method": "POST",
            "path": "/discovery",
            "headers": [
                (b"referer", b"https://www.moatnomics.com/discovery"),
                (b"host", b"www.moatnomics.com")
            ]
        }
        req_www = Request(scope_www)
        self.assertTrue(_validate_request_origin(req_www))

    def test_cors_middleware_allowed_and_blocked_origins(self):
        res_allowed = self.client.get("/robots.txt", headers={"Origin": "https://moatnomics.com"})
        self.assertEqual(res_allowed.headers.get("access-control-allow-origin"), "https://moatnomics.com")
        self.assertEqual(res_allowed.headers.get("access-control-allow-credentials"), "true")

        res_blocked = self.client.get("/robots.txt", headers={"Origin": "https://attacker-evil.com"})
        self.assertNotIn("access-control-allow-origin", res_blocked.headers)

    def test_robots_txt_specifies_moatnomics_sitemap(self):
        res = self.client.get("/robots.txt")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Sitemap: https://moatnomics.com/sitemap.xml", res.text)

    def test_sitemap_xml_contains_moatnomics_urls(self):
        res = self.client.get("/sitemap.xml")
        self.assertEqual(res.status_code, 200)
        self.assertIn("https://moatnomics.com/", res.text)
        self.assertIn("https://moatnomics.com/discovery", res.text)
        self.assertIn("https://moatnomics.com/opportunities", res.text)

    def test_sitemap_xml_respects_canonical_domain_env_override(self):
        old_val = os.environ.get("CANONICAL_DOMAIN")
        try:
            os.environ["CANONICAL_DOMAIN"] = "https://custom.moatnomics.com"
            res = self.client.get("/sitemap.xml")
            self.assertEqual(res.status_code, 200)
            self.assertIn("https://custom.moatnomics.com/", res.text)
        finally:
            if old_val is not None:
                os.environ["CANONICAL_DOMAIN"] = old_val
            else:
                os.environ.pop("CANONICAL_DOMAIN", None)

    def test_telemetry_self_host_filter_handles_moatnomics(self):
        source, detail = parse_traffic_source(
            referrer="https://moatnomics.com/discovery",
            query_params={}
        )
        self.assertEqual(source, "Direct / Bookmark")
        self.assertEqual(detail, "Direct")

        source_www, detail_www = parse_traffic_source(
            referrer="https://www.moatnomics.com/reits",
            query_params={}
        )
        self.assertEqual(source_www, "Direct / Bookmark")
        self.assertEqual(detail_www, "Direct")


# ==============================================================================
# 9. Route Formatting & UTM Campaign Attribution Engine
# ==============================================================================
class TestRouteFormattingAndCampaignTracking(unittest.TestCase):
    def test_format_route_display(self):
        from core.db.telemetry import format_route_display
        self.assertEqual(format_route_display("/"), "Homepage (/)")
        self.assertEqual(format_route_display(""), "Homepage (/)")
        self.assertEqual(format_route_display("/dossier/TCS"), "Equity Dossier (TCS) (/dossier/TCS)")
        self.assertEqual(format_route_display("/funds"), "Mutual Fund Directory (/funds)")
        self.assertEqual(format_route_display("/debt"), "Corporate Debt Directory (/debt)")
        self.assertEqual(format_route_display("/pricing"), "Pricing & Subscriptions (/pricing)")

    def test_utm_campaign_aggregation_in_summary(self):
        from core.db.telemetry import get_site_usage_summary, record_usage_event
        # Record synthetic events with is_test_override=True
        record_usage_event(
            event_type="PAGE_VIEW",
            ticker="TCS",
            session_id="camp_sess_01",
            details={
                "landing_page": "/dossier/TCS",
                "utm_campaign": "launch_beta",
                "utm_source": "linkedin",
                "utm_medium": "social"
            },
            traffic_source="linkedin",
            is_test_override=True
        )
        record_usage_event(
            event_type="PAGE_VIEW",
            ticker="INFY",
            session_id="camp_sess_02",
            details={
                "landing_page": "/dossier/INFY",
                "utm_campaign": "launch_beta",
                "utm_source": "linkedin",
                "utm_medium": "social"
            },
            traffic_source="linkedin",
            is_test_override=True
        )

        summary = get_site_usage_summary(days=7, exclude_tests=False)
        self.assertIn("top_campaigns", summary)
        camps = [c["campaign"] for c in summary["top_campaigns"]]
        self.assertIn("launch_beta", camps)

        # Verify display_name is present in top_landing_pages and top_visited_pages
        if summary.get("top_landing_pages"):
            self.assertIn("display_name", summary["top_landing_pages"][0])
        if summary.get("top_visited_pages"):
            self.assertIn("display_name", summary["top_visited_pages"][0])


if __name__ == "__main__":
    unittest.main()

