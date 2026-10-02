"""Telemetry, user journey analytics, cost savings, and site usage repository."""

import json
import logging
from normalizer import clean_ticker
from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder
from core.db.reports import _format_timestamp

logger = logging.getLogger("equity_research.core.db.telemetry")

def record_usage_event(
    event_type: str,
    ticker: str = "",
    latency_ms: float = 0.0,
    cost_saved_usd: float = 0.0,
    details: dict = None,
    session_id: str = None,
    traffic_source: str = None,
    referrer: str = None,
    country: str = None,
    device_type: str = None,
    browser: str = None,
    os: str = None
):
    """
    Records a telemetry event for backend site usage measurement.
    Non-blocking: catches exceptions gracefully so app operations never fail if telemetry is unavailable.
    """
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = get_placeholder()
        clean_t = clean_ticker(ticker) if ticker else ""
        details_json = json.dumps(details or {})
        try:
            query = f'''
                INSERT INTO site_usage_events (
                    event_type, ticker, latency_ms, cost_saved_usd, details,
                    session_id, traffic_source, referrer, country, device_type, browser, os
                )
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                        {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            '''
            cursor.execute(query, (
                event_type, clean_t, latency_ms, cost_saved_usd, details_json,
                session_id, traffic_source, referrer, country, device_type, browser, os
            ))
        except Exception:
            # Fallback for earlier schema if columns not yet committed
            query_fallback = f'''
                INSERT INTO site_usage_events (event_type, ticker, latency_ms, cost_saved_usd, details)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            '''
            cursor.execute(query_fallback, (event_type, clean_t, latency_ms, cost_saved_usd, details_json))
        conn.commit()
    except Exception as e:
        logger.debug(f"Telemetry recording notice: {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

def _build_telemetry_time_filter(supabase_url: str, days: int = None, start_date = None, end_date = None) -> str:
    """Constructs dynamic SQL WHERE clause for relative days or exact start/end date ranges."""
    if start_date and end_date:
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date)[:10]
        e_str = end_date.strftime("%Y-%m-%d") if hasattr(end_date, "strftime") else str(end_date)[:10]
        if supabase_url:
            return f"timestamp >= '{s_str} 00:00:00+05:30' AND timestamp <= '{e_str} 23:59:59+05:30'"
        else:
            return f"timestamp >= '{s_str} 00:00:00' AND timestamp <= '{e_str} 23:59:59'"
    
    num_days = days if days is not None else 30
    if supabase_url:
        return f"timestamp >= NOW() - INTERVAL '{num_days} days'"
    else:
        return f"timestamp >= datetime('now', '-{num_days} days')"

def get_site_usage_summary(days: int = None, start_date = None, end_date = None) -> dict:
    """Aggregates backend usage analytics, visitor origins, demographics, and credit savings across a selectable date range."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    
    summary = {
        "unique_sessions": 0,
        "total_actions": 0,
        "total_queries": 0,
        "cache_hits": 0,
        "surgical_refreshes": 0,
        "full_syntheses": 0,
        "cache_efficiency_pct": 0.0,
        "total_cost_saved_usd": 0.0,
        "pdf_downloads": 0,
        "comparisons": 0,
        "watchlist_actions": 0,
        "action_breakdown": {},
        "top_searched_tickers": [],
        "traffic_sources": [],
        "top_referrers": [],
        "geographic_distribution": [],
        "device_breakdown": [],
        "browser_breakdown": [],
        "os_breakdown": [],
        "recent_events": [],
    }
    try:
        time_filter = _build_telemetry_time_filter(supabase_url, days=days, start_date=start_date, end_date=end_date)

        # 1. Total Events & Cost Savings by Event Type
        cursor.execute(f'''
            SELECT event_type, COUNT(*), COALESCE(SUM(cost_saved_usd), 0.0)
            FROM site_usage_events
            WHERE {time_filter}
            GROUP BY event_type
        ''')
        for row in cursor.fetchall():
            ev, count, saved = row[0], int(row[1]), float(row[2])
            summary["action_breakdown"][ev] = count
            summary["total_actions"] += count
            summary["total_cost_saved_usd"] += saved
            if ev in ["SEARCH", "QUERY", "SEARCH_QUERY"]:
                summary["total_queries"] += count
            elif ev == "CACHE_HIT":
                summary["cache_hits"] += count
            elif ev == "SURGICAL_REFRESH":
                summary["surgical_refreshes"] += count
            elif ev == "FULL_SYNTHESIS":
                summary["full_syntheses"] += count
            elif ev == "PDF_DOWNLOAD":
                summary["pdf_downloads"] += count
            elif ev in ["COMPARE", "COMPARE_STOCKS", "PEER_COMPARISON"]:
                summary["comparisons"] += count
            elif ev in ["WATCHLIST_ADD", "WATCHLIST_REMOVE", "WATCHLIST"]:
                summary["watchlist_actions"] += count

        effective_searches = max(summary["total_queries"], summary["cache_hits"] + summary["full_syntheses"] + summary["surgical_refreshes"])
        summary["total_queries"] = effective_searches
        if effective_searches > 0:
            free_served = summary["cache_hits"] + summary["surgical_refreshes"]
            summary["cache_efficiency_pct"] = round((free_served / effective_searches) * 100.0, 1)

        # 2. Unique Visitor Sessions
        try:
            cursor.execute(f'''
                SELECT COUNT(DISTINCT session_id)
                FROM site_usage_events
                WHERE {time_filter} AND session_id IS NOT NULL AND session_id != ''
            ''')
            row = cursor.fetchone()
            summary["unique_sessions"] = int(row[0]) if row and row[0] is not None else max(1, summary["total_actions"] // 4)
        except Exception:
            summary["unique_sessions"] = max(1, summary["total_actions"] // 4)

        # 3. Top Searched Equities
        cursor.execute(f'''
            SELECT ticker, COUNT(*) as cnt
            FROM site_usage_events
            WHERE {time_filter} AND ticker IS NOT NULL AND ticker != '' AND ticker != 'APP'
            GROUP BY ticker
            ORDER BY cnt DESC
            LIMIT 8
        ''')
        summary["top_searched_tickers"] = [{"ticker": row[0], "count": int(row[1])} for row in cursor.fetchall()]

        # 4. Traffic Sources ("Where they are coming from")
        try:
            cursor.execute(f'''
                SELECT COALESCE(traffic_source, 'Direct / Bookmark'), COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter}
                GROUP BY COALESCE(traffic_source, 'Direct / Bookmark')
                ORDER BY cnt DESC
                LIMIT 8
            ''')
            src_rows = cursor.fetchall()
            total_src = sum(r[1] for r in src_rows) or 1
            summary["traffic_sources"] = [
                {"source": row[0], "count": int(row[1]), "pct": round((row[1] / total_src) * 100.0, 1)}
                for row in src_rows
            ]
        except Exception:
            summary["traffic_sources"] = [{"source": "Direct / Bookmark", "count": summary["total_actions"], "pct": 100.0}]

        # 5. Top Referring URLs
        try:
            cursor.execute(f'''
                SELECT referrer, COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter} AND referrer IS NOT NULL AND referrer != '' AND referrer != 'Direct'
                GROUP BY referrer
                ORDER BY cnt DESC
                LIMIT 8
            ''')
            summary["top_referrers"] = [{"referrer": row[0], "count": int(row[1])} for row in cursor.fetchall()]
        except Exception:
            summary["top_referrers"] = []

        # 6. Geographic Distribution (Countries)
        try:
            cursor.execute(f'''
                SELECT COALESCE(country, 'IN'), COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter}
                GROUP BY COALESCE(country, 'IN')
                ORDER BY cnt DESC
                LIMIT 8
            ''')
            summary["geographic_distribution"] = [{"country": row[0], "count": int(row[1])} for row in cursor.fetchall()]
        except Exception:
            summary["geographic_distribution"] = [{"country": "IN", "count": summary["total_actions"]}]

        # 7. Device Types, Browsers, and OS
        try:
            cursor.execute(f'''
                SELECT COALESCE(device_type, 'Desktop'), COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter}
                GROUP BY COALESCE(device_type, 'Desktop')
                ORDER BY cnt DESC
            ''')
            summary["device_breakdown"] = [{"device": row[0], "count": int(row[1])} for row in cursor.fetchall()]

            cursor.execute(f'''
                SELECT COALESCE(browser, 'Chrome'), COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter}
                GROUP BY COALESCE(browser, 'Chrome')
                ORDER BY cnt DESC
                LIMIT 6
            ''')
            summary["browser_breakdown"] = [{"browser": row[0], "count": int(row[1])} for row in cursor.fetchall()]

            cursor.execute(f'''
                SELECT COALESCE(os, 'macOS'), COUNT(*) as cnt
                FROM site_usage_events
                WHERE {time_filter}
                GROUP BY COALESCE(os, 'macOS')
                ORDER BY cnt DESC
                LIMIT 6
            ''')
            summary["os_breakdown"] = [{"os": row[0], "count": int(row[1])} for row in cursor.fetchall()]
        except Exception:
            pass

        # 8. Recent Audit Events
        try:
            cursor.execute(f'''
                SELECT event_type, ticker, latency_ms, cost_saved_usd, timestamp,
                       COALESCE(session_id, '-'), COALESCE(traffic_source, 'Direct'),
                       COALESCE(country, 'IN'), COALESCE(device_type, 'Desktop')
                FROM site_usage_events
                ORDER BY timestamp DESC
                LIMIT 50
            ''')
            for row in cursor.fetchall():
                summary["recent_events"].append({
                    "event_type": row[0],
                    "ticker": row[1] or "-",
                    "latency_ms": round(float(row[2] or 0), 1),
                    "cost_saved_usd": round(float(row[3] or 0), 3),
                    "formatted_time": _format_timestamp(row[4]),
                    "session_id": str(row[5])[:10],
                    "source": row[6],
                    "country": row[7],
                    "device": row[8],
                })
        except Exception:
            # Fallback if new columns not yet queried
            cursor.execute(f'''
                SELECT event_type, ticker, latency_ms, cost_saved_usd, timestamp
                FROM site_usage_events
                ORDER BY timestamp DESC
                LIMIT 20
            ''')
            for row in cursor.fetchall():
                summary["recent_events"].append({
                    "event_type": row[0],
                    "ticker": row[1] or "-",
                    "latency_ms": round(float(row[2] or 0), 1),
                    "cost_saved_usd": round(float(row[3] or 0), 3),
                    "formatted_time": _format_timestamp(row[4]),
                    "session_id": "-",
                    "source": "Direct",
                    "country": "IN",
                    "device": "Desktop",
                })
    except Exception as e:
        logger.error(f"Error fetching site usage summary: {e}")
    finally:
        cursor.close()
        conn.close()
    return summary

def get_session_journeys(days: int = None, start_date = None, end_date = None, limit: int = 25) -> list:
    """Reconstructs chronological user journeys grouped by session ID across a selectable date range."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    journeys = []
    try:
        time_filter = _build_telemetry_time_filter(supabase_url, days=days, start_date=start_date, end_date=end_date)

        cursor.execute(f'''
            SELECT session_id,
                   MIN(timestamp) as session_start,
                   MAX(traffic_source) as source,
                   MAX(referrer) as ref,
                   MAX(country) as country,
                   MAX(device_type) as device,
                   MAX(browser) as browser,
                   COUNT(*) as action_count
            FROM site_usage_events
            WHERE {time_filter} AND session_id IS NOT NULL AND session_id != ''
            GROUP BY session_id
            ORDER BY session_start DESC
            LIMIT {limit}
        ''')
        sessions = cursor.fetchall()
        placeholder = get_placeholder()
        for s in sessions:
            sess_id, start_ts, source, ref, country, device, browser, count = s
            cursor.execute(f'''
                SELECT event_type, ticker, timestamp
                FROM site_usage_events
                WHERE session_id = {placeholder}
                ORDER BY timestamp ASC
            ''', (sess_id,))
            events = []
            for ev in cursor.fetchall():
                ev_type, ev_ticker, ev_ts = ev
                events.append({
                    "event_type": ev_type,
                    "ticker": ev_ticker or "",
                    "timestamp": _format_timestamp(ev_ts)
                })
            journeys.append({
                "session_id": sess_id,
                "start_time": _format_timestamp(start_ts),
                "traffic_source": source or "Direct / Bookmark",
                "referrer": ref or "Direct",
                "country": country or "IN",
                "device_type": device or "Desktop",
                "browser": browser or "Unknown",
                "action_count": count,
                "events": events
            })
    except Exception as e:
        logger.error(f"Error fetching session journeys: {e}")
    finally:
        cursor.close()
        conn.close()
    return journeys
