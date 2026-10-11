"""Tests for SEO/GEO tracking: AI referrers, crawler logging, honest Unknown defaults."""
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from telemetry import classify_bot, extract_geo, parse_traffic_source, parse_user_agent
from core.db.telemetry import _build_telemetry_time_filter, _seo_channel


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


class TestHonestDefaults(unittest.TestCase):
    def test_missing_geo_is_unknown_not_india(self):
        self.assertEqual(extract_geo({}), "Unknown")
        self.assertEqual(extract_geo({"user-agent": "x"}), "Unknown")
        self.assertEqual(extract_geo({"cf-ipcountry": "in"}), "IN")

    def test_missing_user_agent_is_unknown(self):
        self.assertEqual(parse_user_agent("")["device"], "Unknown")


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
        from web.main import app
        client = TestClient(app)
        with mock.patch("core.db.telemetry.record_crawler_hit") as hit:
            client.get("/robots.txt", headers={"user-agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"})
            client.get("/robots.txt", headers={"user-agent": "Mozilla/5.0 (Macintosh) Safari/605"})
            time.sleep(0.3)
            self.assertEqual(hit.call_count, 1)
            self.assertEqual(hit.call_args[0][0], "Googlebot")
            self.assertEqual(hit.call_args[0][2], "/robots.txt")


if __name__ == "__main__":
    unittest.main()
