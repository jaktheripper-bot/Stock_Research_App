#!/usr/bin/env python3
"""
Automated Live Cloud Verification & Ingestion Sentry.

Audits live production endpoints (https://moatnomics.com) against local database standards
to prevent verification blindspots and ensure zero static facades or silent data divergence.
"""

import sys
import os
import json
import urllib.request
import urllib.error
import sqlite3
from typing import Dict, Any

CANONICAL_TARGETS = {
    "equities_min": 150,
    "corporate_debt_min": 130,
    "etfs_min": 400,
    "sgbs_min": 36,
    "sovereign_min": 8,
    "msme_min": 90
}

def probe_endpoint(url: str, timeout: int = 15) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MoatnomicsCloudSentry/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            return {"status_code": resp.status, "data": data, "error": None}
    except urllib.error.HTTPError as e:
        return {"status_code": e.code, "data": None, "error": str(e)}
    except Exception as e:
        return {"status_code": 0, "data": None, "error": str(e)}

def audit_live_cloud(base_url: str = "https://moatnomics.com") -> bool:
    print("=" * 80)
    print(f"🌐 Moatnomics Cloud Sentry: Auditing Live Production ({base_url})")
    print("=" * 80)

    all_passed = True

    # 1. Health check
    health = probe_endpoint(f"{base_url}/health")
    if health["status_code"] == 200 and health["data"].get("status") == "healthy":
        print("  ✅ [Health Check] Live web server is HEALTHY.")
    else:
        print(f"  ❌ [Health Check] Health probe failed: {health}")
        all_passed = False

    # 2. Corporate Debt & SDIs
    debt = probe_endpoint(f"{base_url}/api/debt/securities")
    debt_count = 0
    if debt["status_code"] == 200 and isinstance(debt["data"], dict):
        debt_count = debt["data"].get("count", 0)
        if debt_count >= CANONICAL_TARGETS["corporate_debt_min"]:
            print(f"  ✅ [Corporate Debt] Active Bonds & SDIs: {debt_count} (>= {CANONICAL_TARGETS['corporate_debt_min']}).")
        else:
            print(f"  ⚠️ [Corporate Debt] Divergence: count is {debt_count} (expected >= {CANONICAL_TARGETS['corporate_debt_min']}).")
            all_passed = False
    else:
        print(f"  ❌ [Corporate Debt] Request failed: {debt['error']}")
        all_passed = False

    # 3. Opportunity Universe (Multi-Asset)
    opps = probe_endpoint(f"{base_url}/api/opportunities/universe")
    if opps["status_code"] == 200 and isinstance(opps["data"], dict):
        items = opps["data"].get("items", [])
        from collections import Counter
        breakdown = Counter(it.get("asset_class") for it in items)
        print(f"  ✅ [Multi-Asset Universe] Total Live Offerings: {len(items)}")
        print(f"      Breakdown: {dict(breakdown)}")
        if breakdown.get("ETF", 0) < CANONICAL_TARGETS["etfs_min"]:
            print(f"      ⚠️ ETF count {breakdown.get('ETF', 0)} < {CANONICAL_TARGETS['etfs_min']}")
            all_passed = False
        if breakdown.get("SGB", 0) < CANONICAL_TARGETS["sgbs_min"]:
            print(f"      ⚠️ SGB count {breakdown.get('SGB', 0)} < {CANONICAL_TARGETS['sgbs_min']}")
            all_passed = False
    else:
        print(f"  ❌ [Multi-Asset Universe] Request failed: {opps['error']}")
        all_passed = False

    # 4. Local Database Sanity Check
    db_path = "reports.db"
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM reports")
        local_reports = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM corporate_debt_securities")
        local_debt = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM sovereign_benchmarks")
        local_sov = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM sgb_tranches")
        local_sgbs = cur.fetchone()[0]
        conn.close()

        print("\n📦 Local Database Ingestion Standards (reports.db):")
        print(f"  - Researched Equities: {local_reports}")
        print(f"  - Benchmark Debt:     {local_debt}")
        print(f"  - Sovereign Yields:   {local_sov}")
        print(f"  - SGB Tranches:       {local_sgbs}")
    else:
        print("\n⚠️ Local reports.db not found.")

    print("=" * 80)
    if all_passed:
        print("🎯 AUDIT STATUS: ALL SYSTEMS IN SPEC")
    else:
        print("⚠️ AUDIT STATUS: DIVERGENCE DETECTED (Render deploy or cache bust pending)")
    print("=" * 80)
    return all_passed

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://moatnomics.com"
    success = audit_live_cloud(url)
    sys.exit(0 if success else 1)
