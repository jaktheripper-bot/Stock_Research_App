"""Telemetry, user journey analytics, cost savings, and site usage repository."""

import json
import logging
from normalizer import clean_ticker
from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder
from core.db.reports import _format_timestamp
from telemetry import parse_traffic_source, parse_user_agent, extract_geo

logger = logging.getLogger("equity_research.core.db.telemetry")

def is_synthetic_test_event(
    event_type: str = "",
    ticker: str = "",
    browser: str = "",
    user_id: str = "",
    user_email: str = ""
) -> bool:
    """Detects whether an event originates from test runners or synthetic development runs."""
    if user_email and any(dom in str(user_email).lower() for dom in ["@example.com", "@test.com", "test_"]):
        return True
    if user_id and (user_id in ("guest_web_user", "test_user", "testclient", "test_admin") or str(user_id).startswith("test_")):
        return True
    if ticker and str(ticker).upper() in ("TEST", "APP", "XYZ", "SAMPLE"):
        return True
    if browser and any(b in str(browser).lower() for b in ["testclient", "pytest"]):
        return True
    return False


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
    os: str = None,
    user_id: str = None,
    user_email: str = None,
    is_test_override: bool = False
):
    """
    Records a telemetry event for backend site usage measurement.
    Non-blocking: catches exceptions gracefully so app operations never fail if telemetry is unavailable.
    Filters out synthetic automated test runs and testclient traffic unless explicitly overridden.
    """
    if not is_test_override and is_synthetic_test_event(
        event_type=event_type,
        ticker=ticker,
        browser=browser,
        user_id=user_id,
        user_email=user_email
    ):
        return
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
                    session_id, traffic_source, referrer, country, device_type, browser, os,
                    user_id, user_email
                )
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                        {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                        {placeholder}, {placeholder})
            '''
            cursor.execute(query, (
                event_type, clean_t, latency_ms, cost_saved_usd, details_json,
                session_id, traffic_source, referrer, country, device_type, browser, os,
                user_id, user_email
            ))
        except Exception:
            try:
                # Fallback for earlier schema if user columns not yet committed
                query_fallback_session = f'''
                    INSERT INTO site_usage_events (
                        event_type, ticker, latency_ms, cost_saved_usd, details,
                        session_id, traffic_source, referrer, country, device_type, browser, os
                    )
                    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                            {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                '''
                cursor.execute(query_fallback_session, (
                    event_type, clean_t, latency_ms, cost_saved_usd, details_json,
                    session_id, traffic_source, referrer, country, device_type, browser, os
                ))
            except Exception:
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

def _build_telemetry_time_filter(
    supabase_url: str,
    days: int = None,
    start_date = None,
    end_date = None,
    exclude_tests: bool = True
) -> str:
    """Constructs dynamic SQL WHERE clause for relative days or exact start/end date ranges with automated test exclusion."""
    if start_date and end_date:
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date)[:10]
        e_str = end_date.strftime("%Y-%m-%d") if hasattr(end_date, "strftime") else str(end_date)[:10]
        if supabase_url:
            base_clause = f"timestamp >= '{s_str} 00:00:00+05:30' AND timestamp <= '{e_str} 23:59:59+05:30'"
        else:
            base_clause = f"timestamp >= '{s_str} 00:00:00' AND timestamp <= '{e_str} 23:59:59'"
    else:
        num_days = days if days is not None else 30
        if supabase_url:
            base_clause = f"timestamp >= NOW() - INTERVAL '{num_days} days'"
        else:
            base_clause = f"timestamp >= datetime('now', '-{num_days} days')"

    if exclude_tests:
        base_clause += (
            " AND (user_email IS NULL OR (user_email NOT LIKE '%@example.com' AND user_email NOT LIKE '%@test.com' AND user_email NOT LIKE 'test_%'))"
            " AND (user_id IS NULL OR (user_id NOT IN ('guest_web_user', 'test_user', 'testclient', 'test_admin') AND user_id NOT LIKE 'test_%'))"
            " AND (ticker IS NULL OR ticker NOT IN ('TEST', 'APP', 'XYZ', 'SAMPLE'))"
            " AND (browser IS NULL OR browser NOT LIKE '%testclient%')"
        )

    return base_clause

def get_site_usage_summary(days: int = None, start_date = None, end_date = None, exclude_tests: bool = True) -> dict:
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
        time_filter = _build_telemetry_time_filter(
            supabase_url, days=days, start_date=start_date, end_date=end_date, exclude_tests=exclude_tests
        )

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

def get_session_journeys(days: int = None, start_date = None, end_date = None, limit: int = 25, exclude_tests: bool = True) -> list:
    """Reconstructs chronological user journeys grouped by session ID across a selectable date range."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    journeys = []
    try:
        time_filter = _build_telemetry_time_filter(
            supabase_url, days=days, start_date=start_date, end_date=end_date, exclude_tests=exclude_tests
        )

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


def get_user_usage_analytics(days: int = None, start_date = None, end_date = None, limit: int = 50, exclude_tests: bool = True) -> dict:
    """
    Aggregates user-level telemetry and usage attribution:
    - Registered user accounts vs active in period
    - Top active users by queries, dossier generations, and export volume
    - Per-user credit balance and subscription tier correlation
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    p = get_placeholder()

    result = {
        "total_registered_users": 0,
        "active_users_in_period": 0,
        "signed_in_actions_count": 0,
        "guest_actions_count": 0,
        "top_users": [],
        "pro_subscribers_count": 0
    }

    try:
        time_filter = _build_telemetry_time_filter(
            supabase_url, days=days, start_date=start_date, end_date=end_date, exclude_tests=exclude_tests
        )

        # 1. Total registered users & Pro counts
        try:
            cursor.execute("""
                SELECT 
                    COUNT(*), 
                    COUNT(CASE WHEN subscription_tier IN ('pro_monthly', 'pro_annual') THEN 1 END) 
                FROM user_accounts
                WHERE email NOT LIKE '%@example.com' AND email NOT LIKE '%@test.com' AND user_id NOT LIKE 'test_%';
            """)
            u_row = cursor.fetchone()
            if u_row:
                result["total_registered_users"] = int(u_row[0] or 0)
                result["pro_subscribers_count"] = int(u_row[1] or 0)
        except Exception as ue:
            logger.debug(f"User accounts count probe: {ue}")

        # 2. Signed-in vs guest action count in period
        try:
            cursor.execute(f"""
                SELECT 
                    COUNT(CASE WHEN user_email IS NOT NULL AND user_email != '' THEN 1 END) as signed_in,
                    COUNT(CASE WHEN user_email IS NULL OR user_email = '' THEN 1 END) as guest,
                    COUNT(DISTINCT CASE WHEN user_email IS NOT NULL AND user_email != '' THEN user_email END) as active_users
                FROM site_usage_events
                WHERE {time_filter};
            """)
            counts_row = cursor.fetchone()
            if counts_row:
                result["signed_in_actions_count"] = int(counts_row[0] or 0)
                result["guest_actions_count"] = int(counts_row[1] or 0)
                result["active_users_in_period"] = int(counts_row[2] or 0)
        except Exception as ce:
            logger.debug(f"Signed-in action counts probe: {ce}")

        # 3. Top active users in period
        try:
            cursor.execute(f"""
                SELECT 
                    e.user_email,
                    COALESCE(u.id, NULLIF(MAX(e.user_id), ''), 'Unassigned') as uid,
                    COUNT(*) as total_events,
                    COUNT(DISTINCT e.ticker) as distinct_tickers,
                    COUNT(CASE WHEN e.event_type = 'pdf_download' THEN 1 END) as pdf_exports,
                    COUNT(CASE WHEN e.event_type = 'peer_comparison' THEN 1 END) as comparisons,
                    MAX(e.timestamp) as last_seen
                FROM site_usage_events e
                LEFT JOIN user_accounts u ON LOWER(e.user_email) = LOWER(u.email)
                WHERE {time_filter} AND e.user_email IS NOT NULL AND e.user_email != ''
                GROUP BY e.user_email, u.id
                ORDER BY total_events DESC
                LIMIT {limit};
            """)
            top_rows = cursor.fetchall()
            user_list = []
            for r in top_rows:
                email = r[0]
                uid = r[1]
                events_cnt = int(r[2] or 0)
                tickers_cnt = int(r[3] or 0)
                pdf_cnt = int(r[4] or 0)
                comp_cnt = int(r[5] or 0)
                last_active = _format_timestamp(r[6])

                # Get user profile metadata
                credits = 0.0
                tier = "free"
                name = email.split("@")[0]
                try:
                    cursor.execute(f"SELECT full_name, credits_balance, subscription_tier FROM user_accounts WHERE email = {p} OR id = {p} LIMIT 1;", (email, uid))
                    acc = cursor.fetchone()
                    if acc:
                        name = acc[0] or name
                        credits = float(acc[1] or 0.0)
                        tier = (acc[2] or "free").lower()
                except Exception:
                    pass

                user_list.append({
                    "email": email,
                    "name": name,
                    "user_id": uid,
                    "total_actions": events_cnt,
                    "distinct_tickers": tickers_cnt,
                    "pdf_exports": pdf_cnt,
                    "comparisons": comp_cnt,
                    "credits_balance": credits,
                    "subscription_tier": tier,
                    "last_active": last_active
                })
            result["top_users"] = user_list
        except Exception as te:
            logger.debug(f"Top users aggregation error: {te}")

    except Exception as e:
        logger.error(f"Error compiling user usage analytics: {e}")
    finally:
        cursor.close()
        conn.close()

    return result


def purge_test_telemetry() -> dict:
    """
    Purges synthetic testing and automated test runner records:
    - site_usage_events: test email domains, test uids, test tickers, test browsers/IPs
    - support_tickets: test emails, dummy test tickets
    - credit_transactions: test emails, test user accounts
    - user_accounts: test accounts
    Preserves all real user accounts, legitimate customer transactions, and genuine visitor records.
    Returns dictionary with counts of purged records.
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    purged_counts = {
        "events_purged": 0,
        "tickets_purged": 0,
        "transactions_purged": 0,
        "users_purged": 0
    }
    try:
        # 1. Purge synthetic site_usage_events
        cursor.execute("""
            DELETE FROM site_usage_events
            WHERE user_email LIKE '%@example.com'
               OR user_email LIKE '%@test.com'
               OR user_email LIKE 'test_%'
               OR user_id IN ('guest_web_user', 'test_user', 'testclient', 'test_admin')
               OR user_id LIKE 'test_%'
               OR ticker IN ('TEST', 'APP', 'XYZ', 'SAMPLE')
               OR browser LIKE '%testclient%'
               OR browser LIKE '%pytest%';
        """)
        purged_counts["events_purged"] = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0

        # 2. Purge test support_tickets
        try:
            cursor.execute("""
                DELETE FROM support_tickets
                WHERE user_email LIKE '%@example.com'
                   OR user_email LIKE '%@test.com'
                   OR user_email LIKE 'test_%'
                   OR ticket_id LIKE 'TKT-TEST-%'
                   OR subject LIKE '%[TEST]%';
            """)
            purged_counts["tickets_purged"] = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        except Exception as te:
            logger.debug(f"Support tickets purge notice: {te}")

        # 3. Purge test credit_transactions (including simulation checkouts)
        try:
            cursor.execute("""
                DELETE FROM credit_transactions
                WHERE customer_email LIKE '%@example.com'
                   OR customer_email LIKE '%@test.com'
                   OR customer_email LIKE '%@pytest.com'
                   OR user_id LIKE 'test_%'
                   OR user_id IN ('guest_web_user', 'test_user', 'testclient', 'test_admin')
                   OR gateway_order_id LIKE 'order_test_%'
                   OR gateway_order_id LIKE 'order_sim_%'
                   OR gateway_order_id LIKE 'test_%'
                   OR gateway_payment_id LIKE 'pay_test_%'
                   OR gateway_payment_id LIKE 'pay_sim_%'
                   OR payment_gateway = 'simulation'
                   OR id LIKE 'tx_test_%'
                   OR id LIKE 'test_%';
            """)
            purged_counts["transactions_purged"] = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        except Exception as cte:
            logger.warning(f"Credit transactions purge notice: {cte}")

        # 4. Purge test user_accounts (primary key is id)
        try:
            cursor.execute("""
                DELETE FROM user_accounts
                WHERE email LIKE '%@example.com'
                   OR email LIKE '%@test.com'
                   OR email LIKE '%@pytest.com'
                   OR id LIKE 'test_%'
                   OR id IN ('guest_web_user', 'test_user', 'testclient', 'test_admin');
            """)
            purged_counts["users_purged"] = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        except Exception as ue:
            logger.warning(f"User accounts purge notice: {ue}")

        # 5. Purge test credit_usage_ledger
        try:
            cursor.execute("""
                DELETE FROM credit_usage_ledger
                WHERE user_id LIKE 'test_%'
                   OR user_id IN ('guest_web_user', 'test_user', 'testclient', 'test_admin');
            """)
            purged_counts["ledger_purged"] = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        except Exception as le:
            logger.warning(f"Credit usage ledger purge notice: {le}")

        conn.commit()
    except Exception as e:
        logger.error(f"Error executing test data purge: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        cursor.close()
        conn.close()

    return purged_counts

