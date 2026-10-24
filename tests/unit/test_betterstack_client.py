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
    def test_list_heartbeats(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": [{"id": "hb_99", "attributes": {"name": "Morning Ingestion", "url": "https://example.com/hb", "status": "up", "updated_at": "2026-10-24T00:00:00Z"}}]}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        heartbeats = self.client.list_heartbeats()
        self.assertEqual(len(heartbeats), 1)
        self.assertEqual(heartbeats[0]["attributes"]["name"], "Morning Ingestion")

    @patch("core.telemetry.betterstack_client.BetterStackClient.list_monitors")
    @patch("core.telemetry.betterstack_client.BetterStackClient.list_heartbeats")
    def test_get_monitor_statuses(self, mock_heartbeats, mock_monitors):
        mock_monitors.return_value = [{
            "id": "99",
            "attributes": {
                "pronounceable_name": "Moatnomics Web",
                "url": "https://moatnomics.com",
                "status": "up",
                "monitor_type": "status",
                "last_checked_at": "2026-10-24T00:00:00Z",
            }
        }]
        mock_heartbeats.return_value = [{
            "id": "hb_1",
            "attributes": {
                "name": "Morning Pipeline",
                "url": "https://example.com/hb1",
                "status": "up",
                "updated_at": "2026-10-24T00:00:00Z",
            }
        }]

        statuses = self.client.get_monitor_statuses()
        self.assertEqual(len(statuses), 2)
        self.assertEqual(statuses[0]["name"], "Moatnomics Web")
        self.assertEqual(statuses[0]["monitor_type"], "status")
        self.assertEqual(statuses[1]["name"], "Morning Pipeline")
        self.assertEqual(statuses[1]["monitor_type"], "heartbeat")

    @patch("urllib.request.urlopen")
    def test_update_monitor(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": {"id": "99", "attributes": {"pronounceable_name": "Updated Web"}}}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = self.client.update_monitor("99", {"pronounceable_name": "Updated Web"})
        self.assertEqual(res.get("data", {}).get("attributes", {}).get("pronounceable_name"), "Updated Web")

    @patch("urllib.request.urlopen")
    def test_create_heartbeat(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": {"id": "hb_1", "attributes": {"name": "Morning Pipeline"}}}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = self.client.create_heartbeat("Morning Pipeline", period=86400)
        self.assertEqual(res.get("data", {}).get("id"), "hb_1")

    @patch("core.telemetry.betterstack_client.BetterStackClient.list_sources")
    @patch("core.telemetry.betterstack_client.BetterStackClient.get_monitor_statuses")
    def test_get_cached_telemetry_summary(self, mock_monitors, mock_sources):
        mock_sources.return_value = [{"id": "s1"}]
        mock_monitors.return_value = [{"id": "m1", "status": "up"}]

        from core.telemetry.betterstack_client import get_cached_telemetry_summary
        summary = get_cached_telemetry_summary(client=self.client, ttl_seconds=10, force_refresh=True)
        self.assertTrue(summary["is_configured"])
        self.assertEqual(summary["sources_count"], 1)
        self.assertEqual(summary["monitors_count"], 1)
        self.assertTrue(summary["all_monitors_up"])


if __name__ == "__main__":
    unittest.main()
