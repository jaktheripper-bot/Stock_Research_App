#!/usr/bin/env python3
"""
scripts/telemetry_cli.py
==============================================================================
Moatnomics Observability & Telemetry CLI Tool.

Enables instant query, health checks, and monitor verification from the IDE:
  python3 scripts/telemetry_cli.py --sources
  python3 scripts/telemetry_cli.py --monitors
  python3 scripts/telemetry_cli.py --health
==============================================================================
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.telemetry.betterstack_client import BetterStackClient


def print_banner(title: str):
    print("\n" + "=" * 70)
    print(f"MOATNOMICS TELEMETRY: {title.upper()}")
    print("=" * 70)


def show_sources(client: BetterStackClient):
    print_banner("Configured Log Ingestion Sources")
    sources = client.list_sources()
    if not sources:
        print("No sources found or error fetching sources.")
        return

    print(f"Total Sources: {len(sources)}\n")
    for s in sources:
        attrs = s.get("attributes", {})
        sid = s.get("id")
        name = attrs.get("name", "Unknown")
        platform = attrs.get("platform", "Unknown")
        region = attrs.get("data_region", "us")
        table = attrs.get("table_name", "N/A")
        print(f"• [{sid}] {name}")
        print(f"    Platform:    {platform}")
        print(f"    Region:      {region}")
        print(f"    Table:       {table}")
        print("-" * 50)


def show_monitors(client: BetterStackClient):
    print_banner("Uptime Monitors & Heartbeats")
    monitors = client.get_monitor_statuses()
    if not monitors:
        print("No monitors found or error fetching monitors.")
        return

    print(f"Total Monitors: {len(monitors)}\n")
    for m in monitors:
        mid = m.get("id")
        name = m.get("name")
        status = m.get("status", "unknown").upper()
        url = m.get("url") or "Heartbeat / Cron"
        checked = m.get("last_checked_at") or "Never"
        
        status_badge = f"🟢 {status}" if status == "UP" else f"🔴 {status}"
        print(f"• [{mid}] {name} -> {status_badge}")
        print(f"    Target:      {url}")
        print(f"    Last Check:  {checked}")
        print("-" * 50)


def run_health_check(client: BetterStackClient):
    print_banner("Platform Telemetry Health Check")
    # Check sources
    sources = client.list_sources()
    print(f"1. Telemetry Ingestion Sources: {len(sources)} active")
    for s in sources:
        attrs = s.get("attributes", {})
        print(f"   ✓ {attrs.get('name')} ({attrs.get('platform')})")

    # Check monitors
    monitors = client.get_monitor_statuses()
    print(f"\n2. Production Monitors: {len(monitors)} active")
    all_up = True
    for m in monitors:
        status = m.get("status", "").lower()
        if status != "up":
            all_up = False
            print(f"   ⚠️  {m.get('name')}: {status.upper()}")
        else:
            print(f"   ✓ {m.get('name')}: UP")

    print("\n" + "-" * 70)
    if all_up and len(sources) > 0:
        print("✅ ALL TELEMETRY & MONITORING SUBSYSTEMS OPERATIONAL")
    else:
        print("⚠️  ATTENTION REQUIRED: Some monitors or sources are degraded")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Moatnomics Observability & Better Stack CLI")
    parser.add_argument("--sources", action="store_true", help="List all Better Stack log sources")
    parser.add_argument("--monitors", action="store_true", help="List all Better Stack uptime monitors")
    parser.add_argument("--health", action="store_true", help="Run full telemetry and monitor health check")

    args = parser.parse_args()

    client = BetterStackClient()

    if args.sources:
        show_sources(client)
    elif args.monitors:
        show_monitors(client)
    elif args.health or len(sys.argv) == 1:
        run_health_check(client)


if __name__ == "__main__":
    main()
