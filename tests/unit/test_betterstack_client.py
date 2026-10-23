"""
tests/unit/test_betterstack_client.py
==============================================================================
Unit tests for Better Stack Telemetry and Incidents Client.
==============================================================================
"""

import unittest
from unittest.mock import MagicMock, patch

from core.telemetry.betterstack_client import BetterStackClient


class TestBetterStackClient(unittest.TestCase):
    def setUp(self):
        self.client = BetterStackClient(
            telemetry_token="mock-telemetry-token",
            incidents_token="mock-incidents-token",
            timeout=5,
        )

    def test_missing_token_raises_error(self):
        client = BetterStackClient(telemetry_token="", incidents_token="")
        with self.assertRaises(ValueError):
            client._request("https://example.com", token="")

    @patch("urllib.request.urlopen")
    def test_list_sources_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": [{"id": "1", "attributes": {"name": "Moatnomics"}}]}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        sources = self.client.list_sources()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["attributes"]["name"], "Moatnomics")

    @patch("urllib.request.urlopen")
    def test_get_source_by_name(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": [{"id": "1", "attributes": {"name": "Moatnomics Render"}}]}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        source = self.client.get_source_by_name("render")
        self.assertIsNotNone(source)
        self.assertEqual(source["id"], "1")

        not_found = self.client.get_source_by_name("non-existent")
        self.assertIsNone(not_found)

    @patch("urllib.request.urlopen")
    def test_get_monitor_statuses(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": [{"id": "99", "attributes": {"pronounceable_name": "Moatnomics Web", "url": "https://moatnomics.com", "status": "up", "monitor_type": "status", "last_checked_at": "2026-10-24T00:00:00Z"}}]}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        statuses = self.client.get_monitor_statuses()
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0]["name"], "Moatnomics Web")
        self.assertEqual(statuses[0]["status"], "up")


if __name__ == "__main__":
    unittest.main()
