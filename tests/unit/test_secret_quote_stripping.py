"""
Values pasted into a host dashboard straight from a .env line keep their quotes
(KEY="https://..."). get_secret must strip one wrapping pair so URLs and keys still work.
Seen on Render: the Better Stack heartbeat failed with `unknown url type: "https`.
"""
import os
import unittest
from unittest.mock import patch


class TestStripWrappingQuotes(unittest.TestCase):
    def test_helper(self):
        from core.config import _strip_wrapping_quotes

        cases = {
            '"https://uptime.example/hb"': "https://uptime.example/hb",
            "'abc123'": "abc123",
            '  "spaced"  ': "spaced",
            "plain": "plain",
            '"unbalanced': '"unbalanced',
            "mixed'\"": "mixed'\"",
            'a"b"': 'a"b"',
            '""': "",
            '"': '"',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(_strip_wrapping_quotes(raw), expected)

    def test_get_secret_strips_quoted_env_value(self):
        from core.config import get_secret

        key = "BETTER_STACK_HEARTBEAT_URL_MARKET_CLOSE"
        with patch.dict(os.environ, {key: '"https://uptime.example/hb"'}):
            self.assertEqual(get_secret(key), "https://uptime.example/hb")

    def test_mailer_heartbeat_reads_clean_url(self):
        from core import mailer_monitor

        with patch.dict(os.environ, {"BETTER_STACK_HEARTBEAT_URL_FUND_NAV": "'https://uptime.example/fn'"}):
            self.assertEqual(mailer_monitor._cfg("BETTER_STACK_HEARTBEAT_URL_FUND_NAV"), "https://uptime.example/fn")


if __name__ == "__main__":
    unittest.main()
