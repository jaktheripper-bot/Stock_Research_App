"""
core/telemetry/betterstack_client.py
==============================================================================
Client wrapper for Better Stack Telemetry and Incidents/Uptime APIs.

Enables automated diagnostic queries, error inspection, log searching,
and uptime monitor health checks from within the IDE and CLI tools.
==============================================================================
"""

import json
import logging
import ssl
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

import certifi

from core.config import get_secret

logger = logging.getLogger("equity_research.telemetry.betterstack")

TELEMETRY_API_BASE = "https://telemetry.betterstack.com/api/v1"
INCIDENTS_API_BASE = "https://uptime.betterstack.com/api/v2"


class BetterStackClient:
    """Interface for Better Stack Telemetry & Incidents REST APIs."""

    def __init__(
        self,
        telemetry_token: Optional[str] = None,
        incidents_token: Optional[str] = None,
        timeout: int = 15,
    ):
        self.telemetry_token = (
            telemetry_token
            or get_secret("BETTER_STACK_TELEMETRY_TOKEN")
            or get_secret("BETTER_STACK_API_TOKEN")
            or ""
        ).strip()
        self.incidents_token = (
            incidents_token
            or get_secret("BETTER_STACK_INCIDENTS_TOKEN")
            or ""
        ).strip()
        self.timeout = timeout
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())

    def _request(
        self,
        url: str,
        token: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatches an authenticated HTTPS request with TLS verification."""
        if not token:
            raise ValueError("Better Stack API token is required but was not provided or configured.")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Moatnomics-Telemetry-Client/1.0",
        }
        data = json.dumps(payload).encode("utf-8") if payload else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl_context) as resp:
                raw_bytes = resp.read()
                if not raw_bytes:
                    return {"status": resp.status, "data": []}
                return json.loads(raw_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception as read_err:
                logger.warning(f"Could not read HTTPError response body: {read_err}")
            logger.error(f"Better Stack API HTTP {e.code} on {url}: {err_body}")
            return {"error": True, "status": e.code, "message": err_body}
        except Exception as e:
            logger.error(f"Better Stack API request failed on {url}: {e}")
            return {"error": True, "status": 500, "message": str(e)}

    # -------------------------------------------------------------------------
    # Telemetry Sources & Logs
    # -------------------------------------------------------------------------

    def list_sources(self) -> List[Dict[str, Any]]:
        """Lists all configured log sources in Better Stack."""
        url = f"{TELEMETRY_API_BASE}/sources"
        res = self._request(url, self.telemetry_token)
        return res.get("data", [])

    def get_source_by_name(self, name_fragment: str) -> Optional[Dict[str, Any]]:
        """Finds a source by matching a case-insensitive name fragment."""
        frag = name_fragment.lower().strip()
        for src in self.list_sources():
            attrs = src.get("attributes", {})
            name = (attrs.get("name") or "").lower()
            if frag in name:
                return src
        return None

    # -------------------------------------------------------------------------
    # Incidents & Uptime Monitors
    # -------------------------------------------------------------------------

    def list_monitors(self) -> List[Dict[str, Any]]:
        """Lists all configured uptime monitors and heartbeats."""
        url = f"{INCIDENTS_API_BASE}/monitors"
        res = self._request(url, self.incidents_token)
        return res.get("data", [])

    def get_monitor_statuses(self) -> List[Dict[str, Any]]:
        """Extracts lightweight status summaries across all monitors."""
        monitors = self.list_monitors()
        summary = []
        for m in monitors:
            attrs = m.get("attributes", {})
            summary.append({
                "id": m.get("id"),
                "name": attrs.get("pronounceable_name"),
                "url": attrs.get("url"),
                "status": attrs.get("status"),
                "monitor_type": attrs.get("monitor_type"),
                "last_checked_at": attrs.get("last_checked_at"),
            })
        return summary
