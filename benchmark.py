#!/usr/bin/env python3
"""
Performance Benchmark & Latency Budget Scanner
Empirically benchmarks database queries, connection pooling, and payload transfer.
Enforces performance budgets to prevent latency regressions in future builds.
"""

import os
import sys
import time

# Ensure bare-mode streamlit logs don't pollute output
os.environ["STREAMLIT_LOG_LEVEL"] = "error"

def run_benchmarks():
    print("\n=======================================================")
    print("   STOCK RESEARCH APP - LATENCY & SPEED BENCHMARK")
    print("=======================================================")
    
    try:
        from db import (
            get_db_connection,
            get_archived_reports,
            get_unread_alert_count,
            get_alert_events,
            get_watchlist,
            init_db
        )
    except Exception as e:
        print(f"❌ Failed to import database modules: {e}")
        return 1

    # Ensure DB tables/indexes are warm
    init_db()

    # 1. Warm Pooled Connection Borrow + Query + Return
    t0 = time.perf_counter()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1;")
    cur.fetchone()
    cur.close()
    conn.close()
    t_conn = (time.perf_counter() - t0) * 1000

    # 2. Lean Archive Query (without report_text payload)
    if hasattr(get_archived_reports, "cache_clear"):
        get_archived_reports.cache_clear()
    elif hasattr(get_archived_reports, "clear"):
        get_archived_reports.clear()
    t0 = time.perf_counter()
    archives = get_archived_reports(include_text=False)
    t_arch = (time.perf_counter() - t0) * 1000

    # 3. Unread Alert Count Query
    t0 = time.perf_counter()
    unread_c = get_unread_alert_count()
    t_unread = (time.perf_counter() - t0) * 1000

    # 4. Alert Events Query
    t0 = time.perf_counter()
    alerts = get_alert_events(limit=30)
    t_alerts = (time.perf_counter() - t0) * 1000

    # 5. Watchlist Query
    t0 = time.perf_counter()
    watchlist = get_watchlist()
    t_watch = (time.perf_counter() - t0) * 1000

    # 6. Cached In-Memory Query
    t0 = time.perf_counter()
    cached_archives = get_archived_reports(include_text=False)
    t_cached = (time.perf_counter() - t0) * 1000

    total_db_ms = t_arch + t_unread + t_alerts + t_watch
    baseline_ms = 2578.0  # Unpooled pre-optimization baseline

    print(f"1. Pooled DB Connection Handshake:      {t_conn:7.2f} ms")
    print(f"2. Lean Archive Query ({len(archives):2d} stocks):         {t_arch:7.2f} ms")
    print(f"3. Unread Alert Count Query ({unread_c:2d} unread):   {t_unread:7.2f} ms")
    print(f"4. Alert Events Fetch ({len(alerts):2d} events):         {t_alerts:7.2f} ms")
    print(f"5. Watchlist Fetch ({len(watchlist):2d} stocks):            {t_watch:7.2f} ms")
    print(f"6. Cached In-Memory Archive Return:     {t_cached:7.3f} ms")
    print("-------------------------------------------------------")
    print(f"⚡ Total Active DB Latency:              {total_db_ms:7.2f} ms")
    print(f"📦 Unpooled Pre-Optimization Baseline:  {baseline_ms:7.2f} ms")
    
    speedup = baseline_ms / max(total_db_ms, 1.0)
    time_saved = baseline_ms - total_db_ms
    print(f"🚀 Speed Improvement:                  {speedup:.1f}x faster (~{time_saved:.0f} ms saved)")
    print("=======================================================")

    # Performance Budget Enforcement
    # Budget: Total DB queries on warm pool must complete under 2,500ms (down from 2,600ms baseline)
    budget_limit = 2500.0
    if total_db_ms > budget_limit:
        print(f"⚠️ Performance Budget Exceeded: {total_db_ms:.2f} ms > {budget_limit:.2f} ms limit.")
        return 1
    else:
        print("✅ Performance Budget Passed: All queries operating within fast bounds.")
        return 0

if __name__ == "__main__":
    sys.exit(run_benchmarks())
