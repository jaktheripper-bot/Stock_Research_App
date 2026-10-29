"""Telemetry, user journey analytics, cost savings, and site usage repository."""

import json
import logging
from datetime import datetime
from normalizer import clean_ticker
from core.db.connection import init_db, get_db_connection, get_supabase_url, get_placeholder
from core.db.reports import _format_timestamp
from telemetry import parse_traffic_source, parse_user_agent, extract_geo

logger = logging.getLogger("equity_research.core.db.telemetry")

def get_admin_emails() -> set[str]:
    """Retrieves all registered administrator emails, lowercased."""
    try:
        from core.db.admin import list_admin_users, get_authorized_bootstrap_emails
        users = list_admin_users()
        emails = {u.get("email", "").strip().lower() for u in users if u.get("email")}
        emails.update(get_authorized_bootstrap_emails())
        return emails
    except Exception as e:
        logger.debug("Failed fetching admin emails: %s", e)
        return {"admin@moatnomics.com"}


def get_admin_user_ids() -> set[str]:
    """Retrieves all registered administrator user IDs."""
    try:
        from core.db.admin import list_admin_users
        users = list_admin_users()
        ids = {u.get("id", "").strip() for u in users if u.get("id")}
        ids.update({"adm_owner_lyndon", "admin", "test_admin"})
        return ids
    except Exception as e:
        logger.debug("Failed fetching admin user IDs: %s", e)
        return {"adm_owner_lyndon", "admin", "test_admin"}


def is_synthetic_test_event(
    event_type: str = "",
    ticker: str = "",
    browser: str = "",
    user_id: str = "",
    user_email: str = "",
    landing_page: str = "",
    session_id: str = "",
    details: dict = None
) -> bool:
    """Detects whether an event originates from test runners or synthetic development runs."""
    if user_email:
        em = str(user_email).strip().lower()
        if any(dom in em for dom in ["@example.com", "@test.com", "@pytest.com", "test_", "ghost_user", "@localhost"]):
            return True
        if em.startswith("test") and "@" in em:
            return True
    if user_id:
        uid = str(user_id).strip().lower()
        if uid in ("guest_web_user", "test_user", "testclient", "test_admin") or uid.startswith("test_") or uid.startswith("usr_test_"):
            return True
    if ticker:
        t = str(ticker).strip().upper()
        if t in ("TEST", "APP", "XYZ", "SAMPLE", "MOCK") or t.startswith("TEST") or t.startswith("UNIT_TEST_"):
            return True
    if browser:
        b = str(browser).strip().lower()
        if any(agent in b for agent in ["testclient", "pytest", "python-requests", "playwright", "headless", "curl", "postman"]):
            return True
    if session_id:
        s = str(session_id).strip().lower()
        if s.startswith("test_") or s.startswith("sess_test") or "test" in s:
            return True
    if event_type:
        ev = str(event_type).strip().upper()
        if ev.startswith("UNIT_TEST_") or ev.startswith("TEST_"):
            return True
    if details and isinstance(details, dict):
        if details.get("is_test") or details.get("test") or details.get("synthetic"):
            return True
    return False


def is_admin_visit_event(
    event_type: str = "",
    user_email: str = "",
    user_id: str = "",
    landing_page: str = "",
    session_id: str = "",
    details: dict = None
) -> bool:
    """Detects whether an event originates from an administrative visit or admin panel interaction."""
    if event_type and str(event_type).strip().upper().startswith("ADMIN_"):
        return True
    if landing_page:
        lp = str(landing_page).strip().lower()
        if lp.startswith("/admin") or "/admin" in lp:
            return True
    if user_email:
        em = str(user_email).strip().lower()
        if em.startswith("admin@") or em in get_admin_emails():
            return True
        admin_emails = get_admin_emails()
        if em in admin_emails:
            return True
    if user_id:
        uid = str(user_id).strip().lower()
        if uid in ("adm_owner_lyndon", "admin", "test_admin") or uid.startswith("adm_"):
            return True
    if details and isinstance(details, dict):
        p = str(details.get("landing_page") or details.get("path") or details.get("page") or "").strip().lower()
        if p.startswith("/admin") or "/admin" in p:
            return True
    return False


def is_excluded_telemetry_event(
    event_type: str = "",
    ticker: str = "",
    browser: str = "",
    user_id: str = "",
    user_email: str = "",
    landing_page: str = "",
    session_id: str = "",
    details: dict = None
) -> bool:
    """Returns True if the event is from automated tests OR from admin visits to the website."""
    return is_synthetic_test_event(
        event_type=event_type,
        ticker=ticker,
        browser=browser,
        user_id=user_id,
        user_email=user_email,
        landing_page=landing_page,
        session_id=session_id,
        details=details
    ) or is_admin_visit_event(
        event_type=event_type,
        user_email=user_email,
        user_id=user_id,
        landing_page=landing_page,
        session_id=session_id,
        details=details
    )


def classify_page_category(path: str) -> tuple[str, str]:
    """
    Returns (category_name, badge_emoji) for a platform page path.
    """
    clean_p = (path or "").strip()
    if not clean_p or clean_p == "/":
        return "Homepage / Terminal", "🏠"
    if clean_p.startswith("/dossier/"):
        tick = clean_p.split("/")[2] if len(clean_p.split("/")) > 2 else ""
        if tick.startswith("UDYAM"):
            return (f"MSME Dossier ({tick})", "🏭") if tick else ("MSME Dossier", "🏭")
        return (f"Equity Dossier ({tick})", "📈") if tick else ("Equity Dossier", "📈")
    if clean_p == "/dossier":
        return "Equity Dossier Index", "📈"
    if clean_p == "/funds":
        return "Mutual Fund Directory", "🏦"
    if clean_p.startswith("/funds/"):
        return "Mutual Fund Report", "🏦"
    if clean_p == "/debt":
        return "Corporate Debt Directory", "📜"
    if clean_p.startswith("/debt/"):
        return "Corporate Debt Dossier", "📜"
    if clean_p.startswith("/pricing"):
        return "Pricing & Subscriptions", "💳"
    if clean_p.startswith("/compare"):
        return "Peer Head-to-Head Compare", "⚖️"
    if clean_p.startswith("/discovery"):
        return "Alpha Discovery Radar", "🧭"
    if clean_p.startswith("/opportunities"):
        return "Multi-Asset Terminal", "🎯"
    if clean_p.startswith("/reits"):
        return "REITs & InvITs Monitoring", "🏢"
    if clean_p.startswith("/sovereign") or "curve" in clean_p:
        return "Sovereign Yield Curve", "🏛️"
    if clean_p.startswith("/safety-radar"):
        return "Retail Safety Radar", "🛡️"
    if clean_p.startswith("/calculator") or clean_p.startswith("/tax"):
        return "Advance Tax Calculator", "🧮"
    if clean_p.startswith("/etf"):
        return "ETF Matrix & Benchmarks", "📊"
    if clean_p.startswith("/admin"):
        return "Executive Admin Console", "🔐"
    if clean_p.startswith("/equities") or clean_p.startswith("/stocks") or clean_p.startswith("/reports"):
        return "Equities Screener & Directory", "📊"
    if clean_p.startswith("/msme"):
        return "MSME Enterprise Directory", "🏭"
    if any(clean_p.startswith(x) for x in ["/terms", "/privacy", "/refund", "/disclaimer"]):
        return "Legal & Policies", "📑"
    if clean_p.startswith("/contact") or clean_p.startswith("/support"):
        return "Investor Support Grievances", "📩"
    return "Platform Page", "🌐"


def format_route_display(path: str) -> str:
    """
    Returns a human-readable display title for any path route, e.g.
    '/' -> 'Homepage (/)', '/dossier/TCS' -> 'Equity Dossier (TCS)'.
    """
    clean_p = (path or "").strip()
    if not clean_p or clean_p == "/":
        return "Homepage (/)"
    cat_name, _ = classify_page_category(clean_p)
    if cat_name and cat_name != "Platform Page":
        return f"{cat_name} ({clean_p})"
    return clean_p



def format_duration(seconds: float) -> str:
    """Formats numeric seconds into human-readable duration string (e.g. 45s, 2m 14s, 1h 22m)."""
    sec = int(round(seconds))
    if sec < 60:
        return f"{sec}s"
    mins = sec // 60
    rem = sec % 60
    if mins < 60:
        return f"{mins}m {rem:02d}s" if rem else f"{mins}m"
    hrs = mins // 60
    rem_m = mins % 60
    return f"{hrs}h {rem_m:02d}m"


def _parse_event_ts(ev_ts):
    """Safely parses timestamp string or datetime object to datetime instance."""
    if not ev_ts:
        return None
    if isinstance(ev_ts, datetime):
        return ev_ts
    try:
        s_ts = str(ev_ts).strip().replace("T", " ")[:19]
        return datetime.strptime(s_ts, "%Y-%m-%d %H:%M:%S")
    except Exception as ts_err:
        logger.debug("Timestamp parse notice: %s", ts_err)
        return None


def _estimate_default_dwell(path: str) -> float:
    """Zero-Illusion Policy: Never fabricate dwell time on unmeasured single-page bounces or terminal exits."""
    return 0.0


def compute_page_dwell_and_visit_tree(all_events: list) -> dict:
    """
    Computes:
    1. Average and aggregate dwell time per page route from explicit client Active Attention Beacons
       (`dwell_seconds`) and bounded inter-event deltas (1s..1800s), without fabricating dwell on single-page bounces.
    2. Pillar / Section-level reading attention breakdown (`pillar_dwell_breakdown`) and scroll depth (`avg_scroll_pct`).
    3. Site Visit Tree / Transition Matrix tracking which pages contributed to which subsequent clicks within the site.
    4. Global summary statistics (average engaged dwell, total transitions).
    """
    raw_session_events = {}

    for ev_row in all_events:
        eid, sess_id, lp_col, det_raw, ev_tick, ev_type, ts_raw = ev_row[:7]
        effective_sess = str(sess_id).strip() if sess_id and str(sess_id).strip() else f"anon_{eid}"

        p = str(lp_col).strip() if lp_col else ""
        det = {}
        if det_raw:
            try:
                det = json.loads(det_raw) if isinstance(det_raw, str) else det_raw
            except Exception as e:
                logger.debug("Failed parsing det_raw json: %s", e)
                det = {}

        if not p and det:
            p = det.get("landing_page") or det.get("path") or det.get("page") or ""
            if not p and det.get("landing_url"):
                try:
                    from urllib.parse import urlparse
                    p = urlparse(det["landing_url"]).path
                except Exception as url_err:
                    logger.debug("URL parse notice: %s", url_err)
        if not p and ev_tick and str(ev_tick).upper() != "APP":
            p = f"/dossier/{clean_ticker(ev_tick)}"
        if not p:
            if "COMPARE" in (ev_type or ""): p = "/compare"
            elif "TICKET" in (ev_type or ""): p = "/contact"
            elif "PDF" in (ev_type or ""): p = f"/dossier/{clean_ticker(ev_tick)}" if ev_tick else "/dossier"
            else: p = "/"

        if not p.startswith("/"):
            p = "/" + p
        if len(p) > 1 and p.endswith("/"):
            p = p.rstrip("/")

        ts = _parse_event_ts(ts_raw)

        if effective_sess not in raw_session_events:
            raw_session_events[effective_sess] = []
        raw_session_events[effective_sess].append({
            "path": p,
            "timestamp": ts,
            "details": det if isinstance(det, dict) else {},
            "event_type": ev_type or ""
        })

    # Coalesce PAGE_DWELL exit beacons onto their corresponding page visit in the same session
    # so client beacons enrich dwell_seconds, max_scroll_pct, and pillar_dwell without double-counting visits.
    session_events = {}
    pillar_dwell_accum = {}
    scroll_accum = {}

    for s_id, raw_list in raw_session_events.items():
        coalesced = []
        for ev in raw_list:
            p = ev["path"]
            det = ev["details"]
            ev_type = (ev["event_type"] or "").upper()

            # Harvest pillar-level dwell & scroll depth from any event that carries them
            p_map = det.get("pillar_dwell")
            if isinstance(p_map, dict):
                for pil_key, pil_sec in p_map.items():
                    try:
                        val_s = min(max(float(pil_sec), 0.0), 1800.0)
                    except (TypeError, ValueError):
                        val_s = 0.0
                    if val_s > 0:
                        clean_pil = str(pil_key).strip()[:80]
                        pillar_dwell_accum.setdefault(clean_pil, []).append(val_s)

            sc_pct = det.get("max_scroll_pct")
            if sc_pct is not None:
                try:
                    sc_val = min(max(float(sc_pct), 0.0), 100.0)
                    if sc_val > 0:
                        scroll_accum.setdefault(p, []).append(sc_val)
                except (TypeError, ValueError):
                    pass

            if ev_type == "PAGE_DWELL" and not det.get("to_path") and coalesced and coalesced[-1]["path"] == p:
                prev_det = dict(coalesced[-1]["details"])
                prev_dwell = float(prev_det.get("dwell_seconds") or prev_det.get("duration_seconds") or 0.0)
                new_dwell = float(det.get("dwell_seconds") or det.get("duration_seconds") or 0.0)
                prev_det["dwell_seconds"] = min(prev_dwell + new_dwell, 1800.0)
                if det.get("max_scroll_pct") is not None:
                    prev_det["max_scroll_pct"] = max(
                        float(prev_det.get("max_scroll_pct") or 0.0),
                        float(det.get("max_scroll_pct") or 0.0),
                    )
                coalesced[-1]["details"] = prev_det
            else:
                coalesced.append(ev)
        session_events[s_id] = coalesced

    dwell_accum = {}
    transitions = {}
    session_exits = {}

    for s_id, ev_list in session_events.items():
        for i in range(len(ev_list)):
            curr = ev_list[i]
            p = curr["path"]
            c_dwell = curr["details"].get("dwell_seconds") or curr["details"].get("duration_seconds")

            # 1. Dwell time calculation (Strictly empirical: client beacon or bounded inter-event delta)
            if c_dwell is not None and float(c_dwell) > 0:
                dwell = min(float(c_dwell), 1800.0)
            elif i + 1 < len(ev_list) and curr["timestamp"] and ev_list[i + 1]["timestamp"]:
                delta = (ev_list[i + 1]["timestamp"] - curr["timestamp"]).total_seconds()
                if 1.0 <= delta <= 1800.0:
                    dwell = delta
                else:
                    dwell = 0.0
            else:
                dwell = 0.0

            if p not in dwell_accum:
                dwell_accum[p] = []
            dwell_accum[p].append(dwell)

            # 2. Site Visit Tree / Transitions tracking
            c_to = curr["details"].get("to_path")
            if c_to and c_to != p:
                c_to_clean = c_to if c_to.startswith("/") else "/" + c_to
                if len(c_to_clean) > 1 and c_to_clean.endswith("/"):
                    c_to_clean = c_to_clean.rstrip("/")
                if p not in transitions:
                    transitions[p] = {}
                transitions[p][c_to_clean] = transitions[p].get(c_to_clean, 0) + 1
            elif i + 1 < len(ev_list):
                next_p = ev_list[i + 1]["path"]
                if next_p != p:
                    if p not in transitions:
                        transitions[p] = {}
                    transitions[p][next_p] = transitions[p].get(next_p, 0) + 1
            else:
                session_exits[p] = session_exits.get(p, 0) + 1

    page_dwell_times = []
    all_dwell_values = []
    for path, d_list in dwell_accum.items():
        samples = len(d_list)
        measured_list = [d for d in d_list if d > 0]
        measured_samples = len(measured_list)
        tot_sec = sum(measured_list)
        avg_sec = round(tot_sec / max(1, measured_samples), 1) if measured_samples > 0 else 0.0
        all_dwell_values.extend(measured_list)
        cat_name, cat_icon = classify_page_category(path)

        scroll_list = scroll_accum.get(path, [])
        avg_scroll_pct = round(sum(scroll_list) / len(scroll_list), 1) if scroll_list else None

        if measured_samples == 0:
            tier = "quick"
            tier_label = "Bounce / Unmeasured (0s)"
            badge_color = "#64748b"
        elif avg_sec >= 90:
            tier = "high"
            tier_label = "Deep Read (>90s)"
            badge_color = "#10b981"
        elif avg_sec >= 35:
            tier = "medium"
            tier_label = "Engaged (35s–90s)"
            badge_color = "#38bdf8"
        else:
            tier = "quick"
            tier_label = "Glance (<35s)"
            badge_color = "#94a3b8"

        page_dwell_times.append({
            "path": path,
            "display_name": format_route_display(path),
            "category": cat_name,
            "icon": cat_icon,
            "avg_dwell_seconds": avg_sec,
            "formatted_avg_dwell": format_duration(avg_sec),
            "total_dwell_seconds": round(tot_sec, 1),
            "formatted_total_dwell": format_duration(tot_sec),
            "visits_count": samples,
            "measured_visits_count": measured_samples,
            "avg_scroll_pct": avg_scroll_pct,
            "tier": tier,
            "tier_label": tier_label,
            "badge_color": badge_color,
        })

    page_dwell_times.sort(key=lambda x: (x["total_dwell_seconds"], x["visits_count"]), reverse=True)

    pillar_dwell_breakdown = []
    for pil_label, p_list in pillar_dwell_accum.items():
        p_samples = len(p_list)
        p_tot = sum(p_list)
        p_avg = round(p_tot / max(1, p_samples), 1)
        pillar_dwell_breakdown.append({
            "pillar": pil_label,
            "section": pil_label,
            "avg_dwell_seconds": p_avg,
            "formatted_avg_dwell": format_duration(p_avg),
            "total_dwell_seconds": round(p_tot, 1),
            "total_seconds": round(p_tot, 1),
            "formatted_total_dwell": format_duration(p_tot),
            "formatted_total": format_duration(p_tot),
            "samples": p_samples,
        })
    pillar_dwell_breakdown.sort(key=lambda x: (x["total_dwell_seconds"], x["samples"]), reverse=True)

    site_visit_tree = []
    total_transitions_count = 0
    for from_p, dest_dict in transitions.items():
        total_outbound = sum(dest_dict.values())
        total_transitions_count += total_outbound
        exits = session_exits.get(from_p, 0)
        cat_name, cat_icon = classify_page_category(from_p)

        destinations = []
        for to_p, cnt in sorted(dest_dict.items(), key=lambda x: x[1], reverse=True):
            to_cat, to_icon = classify_page_category(to_p)
            destinations.append({
                "to_path": to_p,
                "display_name": format_route_display(to_p),
                "category": to_cat,
                "icon": to_icon,
                "count": cnt,
                "percentage": round((cnt / max(1, total_outbound)) * 100.0, 1)
            })

        exit_rate = round((exits / max(1, total_outbound + exits)) * 100.0, 1)

        site_visit_tree.append({
            "from_path": from_p,
            "display_name": format_route_display(from_p),
            "category": cat_name,
            "icon": cat_icon,
            "total_outbound": total_outbound,
            "exit_count": exits,
            "exit_rate_pct": exit_rate,
            "destinations": destinations
        })

    site_visit_tree.sort(key=lambda x: x["total_outbound"], reverse=True)

    overall_avg_sec = round(sum(all_dwell_values) / max(1, len(all_dwell_values)), 1) if all_dwell_values else 0.0
    overall_total_sec = sum(all_dwell_values) if all_dwell_values else 0.0

    return {
        "page_dwell_times": page_dwell_times,
        "pillar_dwell_breakdown": pillar_dwell_breakdown,
        "site_visit_tree": site_visit_tree,
        "overall_avg_dwell_seconds": overall_avg_sec,
        "formatted_overall_avg_dwell": format_duration(overall_avg_sec),
        "total_dwell_hours": round(overall_total_sec / 3600.0, 2),
        "total_navigation_transitions": total_transitions_count,
        "top_contributing_page": site_visit_tree[0] if site_visit_tree else None
    }


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
    is_test_override: bool = False,
    landing_page: str = None
):
    """
    Records a telemetry event for backend site usage measurement.
    Non-blocking: catches exceptions gracefully so app operations never fail if telemetry is unavailable.
    Filters out synthetic automated test runs and testclient traffic unless explicitly overridden.
    """
    if not is_test_override and is_excluded_telemetry_event(
        event_type=event_type,
        ticker=ticker,
        browser=browser,
        user_id=user_id,
        user_email=user_email,
        landing_page=landing_page,
        session_id=session_id,
        details=details
    ):
        return
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = get_placeholder()
        clean_t = clean_ticker(ticker) if ticker else ""

        details_dict = dict(details or {})
        resolved_lp = landing_page or details_dict.get("landing_page") or details_dict.get("path") or details_dict.get("page") or ""
        if not resolved_lp and ticker and ticker != "APP":
            resolved_lp = f"/dossier/{clean_t}"
        if resolved_lp:
            if not resolved_lp.startswith("/"):
                resolved_lp = "/" + resolved_lp
            if len(resolved_lp) > 1 and resolved_lp.endswith("/"):
                resolved_lp = resolved_lp.rstrip("/")
        else:
            resolved_lp = "/"
        details_dict["landing_page"] = resolved_lp
        details_json = json.dumps(details_dict)

        try:
            # 1. Primary insert including landing_page column
            query = f'''
                INSERT INTO site_usage_events (
                    event_type, ticker, latency_ms, cost_saved_usd, details,
                    session_id, traffic_source, referrer, country, device_type, browser, os,
                    user_id, user_email, landing_page
                )
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                        {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                        {placeholder}, {placeholder}, {placeholder})
            '''
            cursor.execute(query, (
                event_type, clean_t, latency_ms, cost_saved_usd, details_json,
                session_id, traffic_source, referrer, country, device_type, browser, os,
                user_id, user_email, resolved_lp
            ))
        except Exception as e:
            logger.debug("Fallback inserting usage event without landing_page: %s", e)
            try:
                # Fallback without landing_page column
                query_fallback_user = f'''
                    INSERT INTO site_usage_events (
                        event_type, ticker, latency_ms, cost_saved_usd, details,
                        session_id, traffic_source, referrer, country, device_type, browser, os,
                        user_id, user_email
                    )
                    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                            {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                            {placeholder}, {placeholder})
                '''
                cursor.execute(query_fallback_user, (
                    event_type, clean_t, latency_ms, cost_saved_usd, details_json,
                    session_id, traffic_source, referrer, country, device_type, browser, os,
                    user_id, user_email
                ))
            except Exception as e:
                logger.debug("Fallback inserting usage event without user columns: %s", e)
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
                except Exception as e:
                    logger.debug("Fallback inserting usage event with basic columns: %s", e)
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
        except Exception as close_err:
            logger.debug("Telemetry connection close notice: %s", close_err)

def _build_telemetry_time_filter(
    supabase_url: str,
    days: int = None,
    start_date = None,
    end_date = None,
    exclude_tests: bool = True,
    include_bots: bool = False
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
        admin_emails = get_admin_emails()
        admin_emails_sql = ", ".join(f"'{e}'" for e in sorted(admin_emails)) if admin_emails else "'admin@moatnomics.com'"
        admin_ids = get_admin_user_ids()
        admin_ids_sql = ", ".join(f"'{i}'" for i in sorted(admin_ids)) if admin_ids else "'adm_owner_primary'"

        base_clause += (
            # 1. Exclude synthetic test events & test runner traffic
            " AND (user_email IS NULL OR ("
            "     user_email NOT LIKE '%@example.com'"
            " AND user_email NOT LIKE '%@test.com'"
            " AND user_email NOT LIKE '%@pytest.com'"
            " AND user_email NOT LIKE 'test_%'"
            " AND user_email NOT LIKE '%ghost_user%'"
            " AND user_email NOT LIKE '%@localhost%'"
            "))"
            " AND (user_id IS NULL OR ("
            "     user_id NOT IN ('guest_web_user', 'test_user', 'testclient', 'test_admin')"
            " AND user_id NOT LIKE 'test_%'"
            " AND user_id NOT LIKE 'usr_test_%'"
            "))"
            " AND (ticker IS NULL OR ("
            "     ticker NOT IN ('TEST', 'APP', 'XYZ', 'SAMPLE', 'MOCK')"
            " AND ticker NOT LIKE 'TEST%'"
            " AND ticker NOT LIKE 'UNIT_TEST_%'"
            "))"
            " AND (browser IS NULL OR ("
            "     browser NOT LIKE '%testclient%'"
            " AND browser NOT LIKE '%pytest%'"
            " AND browser NOT LIKE '%python-requests%'"
            " AND browser NOT LIKE '%playwright%'"
            " AND browser NOT LIKE '%headless%'"
            " AND browser NOT LIKE '%curl%'"
            "))"
            " AND (session_id IS NULL OR ("
            "     session_id NOT LIKE 'test_%'"
            " AND session_id NOT LIKE 'sess_test%'"
            "))"
            " AND (event_type IS NULL OR ("
            "     event_type NOT LIKE 'UNIT_TEST_%'"
            " AND event_type NOT LIKE 'TEST_%'"
            "))"
            # 2. Exclude administrative visits, admin route activity, and admin accounts
            f" AND (user_email IS NULL OR (LOWER(user_email) NOT IN ({admin_emails_sql}) AND user_email NOT LIKE 'admin@%'))"
            f" AND (user_id IS NULL OR (user_id NOT IN ({admin_ids_sql}) AND user_id NOT LIKE 'adm_%' AND user_id != 'admin'))"
            " AND (event_type IS NULL OR event_type NOT LIKE 'ADMIN_%')"
            " AND (landing_page IS NULL OR (landing_page NOT LIKE '/admin%' AND landing_page NOT LIKE '%/admin%'))"
            # 3. Exclude entire sessions that touched admin pages or had admin activity or test runners
            f" AND (session_id IS NULL OR session_id NOT IN ("
            f"     SELECT DISTINCT session_id FROM site_usage_events "
            f"     WHERE session_id IS NOT NULL AND ("
            f"         landing_page LIKE '/admin%'"
            f"      OR event_type LIKE 'ADMIN_%'"
            f"      OR LOWER(user_email) IN ({admin_emails_sql})"
            f"      OR user_id IN ({admin_ids_sql})"
            f"      OR user_id LIKE 'adm_%'"
            f"      OR browser LIKE '%testclient%'"
            f"      OR browser LIKE '%pytest%'"
            f"      OR browser LIKE '%python-requests%'"
            f"      OR browser LIKE '%playwright%'"
            f"      OR session_id LIKE 'test_%'"
            f"      OR session_id LIKE 'sess_test%'"
            f"     )"
            f" ))"
        )

    if exclude_tests and not include_bots:
        # Crawler hits are logged as BOT_CRAWL events and must never count as visitors
        base_clause += " AND (event_type IS NULL OR event_type != 'BOT_CRAWL')"

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
        "price_filing_updates": 0,
        "full_syntheses": 0,
        "cache_efficiency_pct": 0.0,
        "total_cost_saved_usd": 0.0,
        "total_cost_saved_inr": 0.0,
        "pdf_downloads": 0,
        "comparisons": 0,
        "watchlist_actions": 0,
        "action_breakdown": {},
        "top_searched_tickers": [],
        "traffic_sources": [],
        "top_referrers": [],
        "top_landing_pages": [],
        "top_visited_pages": [],
        "top_campaigns": [],
        "page_dwell_times": [],
        "site_visit_tree": [],
        "overall_avg_dwell_seconds": 0.0,
        "formatted_overall_avg_dwell": "0s",
        "total_dwell_hours": 0.0,
        "total_navigation_transitions": 0,
        "top_contributing_page": None,
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
            summary["total_cost_saved_usd"] += saved
            summary["total_cost_saved_inr"] = round(summary["total_cost_saved_usd"] * 84.0, 2)
            # Passive PAGE_DWELL beacons measure attention duration; do not inflate user action counts
            if ev != "PAGE_DWELL":
                summary["total_actions"] += count
            if ev in ["SEARCH", "QUERY", "SEARCH_QUERY"]:
                summary["total_queries"] += count
            elif ev == "CACHE_HIT":
                summary["cache_hits"] += count
            elif ev == "SURGICAL_REFRESH":
                summary["price_filing_updates"] += count
            elif ev == "FULL_SYNTHESIS":
                summary["full_syntheses"] += count
            elif ev == "PDF_DOWNLOAD":
                summary["pdf_downloads"] += count
            elif ev in ["COMPARE", "COMPARE_STOCKS", "PEER_COMPARISON"]:
                summary["comparisons"] += count
            elif ev in ["WATCHLIST_ADD", "WATCHLIST_REMOVE", "WATCHLIST"]:
                summary["watchlist_actions"] += count

        effective_searches = max(summary["total_queries"], summary["cache_hits"] + summary["full_syntheses"] + summary["price_filing_updates"])
        summary["total_queries"] = effective_searches
        if effective_searches > 0:
            free_served = summary["cache_hits"] + summary["price_filing_updates"]
            summary["cache_efficiency_pct"] = round((free_served / effective_searches) * 100.0, 1)

        # 2. Unique Visitor Sessions
        try:
            cursor.execute(f'''
                SELECT COUNT(DISTINCT session_id)
                FROM site_usage_events
                WHERE {time_filter} AND session_id IS NOT NULL AND session_id != ''
            ''')
            row = cursor.fetchone()
            summary["unique_sessions"] = int(row[0]) if row and row[0] is not None else 0
        except Exception as e:
            logger.debug("Failed querying unique sessions count: %s", e)
            summary["unique_sessions"] = 0

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
                SELECT COALESCE(traffic_source, 'Direct / Bookmark'), COUNT(DISTINCT session_id) as cnt
                FROM site_usage_events
                WHERE {time_filter} AND session_id IS NOT NULL AND session_id != ''
                GROUP BY COALESCE(traffic_source, 'Direct / Bookmark')
                ORDER BY cnt DESC
                LIMIT 8
            ''')
            src_rows = cursor.fetchall()
            total_src = sum(r[1] for r in src_rows) or 1
            summary["traffic_sources"] = [
                {"source": row[0], "count": int(row[1]), "pct": round((row[1] / total_src) * 100.0, 1),
                 "percentage": round((row[1] / total_src) * 100.0, 1)}
                for row in src_rows
            ]
        except Exception as e:
            logger.debug("Failed querying traffic sources: %s", e)
            summary["traffic_sources"] = []

        # 5. Top Referring URLs
        try:
            cursor.execute(f'''
                SELECT referrer, COUNT(DISTINCT session_id) as cnt
                FROM site_usage_events
                WHERE {time_filter} AND session_id IS NOT NULL AND session_id != '' AND referrer IS NOT NULL AND referrer != '' AND referrer != 'Direct'
                GROUP BY referrer
                ORDER BY cnt DESC
                LIMIT 8
            ''')
            summary["top_referrers"] = [{"referrer": row[0], "count": int(row[1])} for row in cursor.fetchall()]
        except Exception as e:
            logger.debug("Failed querying top referrers: %s", e)
            summary["top_referrers"] = []

        # 5b. Top Landing Pages (Entry Points) & Visited Routes
        try:
            try:
                cursor.execute(f'''
                    SELECT id, session_id, COALESCE(landing_page, ''), details, ticker, event_type, timestamp
                    FROM site_usage_events
                    WHERE {time_filter}
                    ORDER BY timestamp ASC
                ''')
                all_events = cursor.fetchall()
            except Exception as e:
                logger.debug("Failed querying landing pages with landing_page column, falling back: %s", e)
                cursor.execute(f'''
                    SELECT id, session_id, '', details, ticker, event_type, timestamp
                    FROM site_usage_events
                    WHERE {time_filter}
                    ORDER BY timestamp ASC
                ''')
                all_events = cursor.fetchall()

            session_landing_map = {}
            page_views_map = {}
            session_profile_map = {}
            session_campaign_map = {}

            for ev_row in all_events:
                eid, sess_id, lp_col, det_raw, ev_tick, ev_type, _ = ev_row
                effective_sess = str(sess_id).strip() if sess_id and str(sess_id).strip() else f"anon_{eid}"

                p = str(lp_col).strip() if lp_col else ""
                det_obj = {}
                if det_raw:
                    try:
                        det_obj = json.loads(det_raw) if isinstance(det_raw, str) else det_raw
                        if not isinstance(det_obj, dict):
                            det_obj = {}
                        if not p:
                            p = det_obj.get("landing_page") or det_obj.get("path") or det_obj.get("page") or ""
                            if not p and det_obj.get("landing_url"):
                                from urllib.parse import urlparse
                                p = urlparse(det_obj["landing_url"]).path
                    except Exception as parse_err:
                        logger.debug("Failed to parse telemetry details_json landing page: %s", parse_err)
                if not p and ev_tick and str(ev_tick).upper() != "APP":
                    p = f"/dossier/{clean_ticker(ev_tick)}"
                if not p:
                    if "COMPARE" in (ev_type or ""): p = "/compare"
                    elif "TICKET" in (ev_type or ""): p = "/contact"
                    elif "PDF" in (ev_type or ""): p = f"/dossier/{clean_ticker(ev_tick)}" if ev_tick else "/dossier"
                    else: p = "/"

                if not p.startswith("/"):
                    p = "/" + p
                if len(p) > 1 and p.endswith("/"):
                    p = p.rstrip("/")

                if effective_sess not in session_landing_map:
                    session_landing_map[effective_sess] = p

                # Track UTM campaign attribution from details or query params
                camp_name = (det_obj.get("utm_campaign") or "").strip()
                camp_src = (det_obj.get("utm_source") or "").strip()
                camp_med = (det_obj.get("utm_medium") or "").strip()
                if (camp_name or camp_src) and effective_sess not in session_campaign_map:
                    session_campaign_map[effective_sess] = {
                        "campaign": camp_name or "default",
                        "source": camp_src or "Organic / Other",
                        "medium": camp_med or "referral"
                    }

                sp = session_profile_map.setdefault(effective_sess, {"paths": set(), "non_dwell_events": 0, "dwell_sec": 0.0})
                sp["paths"].add(p)
                if (ev_type or "").upper() == "PAGE_DWELL":
                    try:
                        sp["dwell_sec"] += float(det_obj.get("dwell_seconds") or det_obj.get("duration_seconds") or 0.0)
                    except (TypeError, ValueError):
                        pass
                else:
                    sp["non_dwell_events"] += 1

                if p not in page_views_map:
                    page_views_map[p] = {"views": 0, "sessions": set()}
                if (ev_type or "").upper() != "PAGE_DWELL" or effective_sess not in page_views_map[p]["sessions"]:
                    page_views_map[p]["views"] += 1
                page_views_map[p]["sessions"].add(effective_sess)

            # Compute empirical Bounce Rate (1 page visited, <= 1 non-dwell action, < 10s measured dwell)
            if session_profile_map:
                bounced_cnt = sum(
                    1 for sp in session_profile_map.values()
                    if len(sp["paths"]) <= 1 and sp["non_dwell_events"] <= 1 and sp["dwell_sec"] < 10.0
                )
                summary["bounce_rate_pct"] = round((bounced_cnt / max(1, len(session_profile_map))) * 100.0, 1)
            else:
                summary["bounce_rate_pct"] = 0.0

            landing_counts = {}
            for s_id, l_path in session_landing_map.items():
                landing_counts[l_path] = landing_counts.get(l_path, 0) + 1

            total_landing_sessions = max(1, sum(landing_counts.values()))
            summary["top_landing_pages"] = []
            for path_key, s_count in sorted(landing_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
                cat_name, cat_icon = classify_page_category(path_key)
                summary["top_landing_pages"].append({
                    "path": path_key,
                    "display_name": format_route_display(path_key),
                    "category": cat_name,
                    "icon": cat_icon,
                    "sessions": s_count,
                    "percentage": round((s_count / total_landing_sessions) * 100.0, 1)
                })

            total_all_views = max(1, sum(v["views"] for v in page_views_map.values()))
            summary["top_visited_pages"] = []
            for path_key, v_data in sorted(page_views_map.items(), key=lambda x: x[1]["views"], reverse=True)[:15]:
                cat_name, cat_icon = classify_page_category(path_key)
                summary["top_visited_pages"].append({
                    "path": path_key,
                    "route": path_key,
                    "display_name": format_route_display(path_key),
                    "count": v_data["views"],
                    "category": cat_name,
                    "icon": cat_icon,
                    "views": v_data["views"],
                    "unique_sessions": len(v_data["sessions"]),
                    "percentage": round((v_data["views"] / total_all_views) * 100.0, 1)
                })
            summary["top_routes"] = summary["top_visited_pages"]
            summary["top_tickers"] = summary["top_searched_tickers"]

            # Aggregate Campaign Performance
            campaign_counts = {}
            for s_id, c_info in session_campaign_map.items():
                c_key = (c_info["campaign"], c_info["source"], c_info["medium"])
                campaign_counts[c_key] = campaign_counts.get(c_key, 0) + 1

            total_campaign_sessions = max(1, sum(campaign_counts.values()))
            summary["top_campaigns"] = []
            for (c_name, c_src, c_med), c_count in sorted(campaign_counts.items(), key=lambda x: x[1], reverse=True)[:12]:
                summary["top_campaigns"].append({
                    "campaign": c_name,
                    "source": c_src,
                    "medium": c_med,
                    "sessions": c_count,
                    "percentage": round((c_count / total_campaign_sessions) * 100.0, 1)
                })

            # 5c. Link Dwell Times and Site Visit Navigation Tree
            try:
                flow_data = compute_page_dwell_and_visit_tree(all_events)
                summary["page_dwell_times"] = flow_data.get("page_dwell_times", [])
                summary["pillar_dwell_breakdown"] = flow_data.get("pillar_dwell_breakdown", [])
                summary["site_visit_tree"] = flow_data.get("site_visit_tree", [])
                summary["overall_avg_dwell_seconds"] = flow_data.get("overall_avg_dwell_seconds", 0.0)
                summary["formatted_overall_avg_dwell"] = flow_data.get("formatted_overall_avg_dwell", "0s")
                summary["total_dwell_hours"] = flow_data.get("total_dwell_hours", 0.0)
                summary["total_navigation_transitions"] = flow_data.get("total_navigation_transitions", 0)
                summary["top_contributing_page"] = flow_data.get("top_contributing_page")
            except Exception as dwell_tree_err:
                logger.warning(f"Error computing dwell and site visit tree in telemetry: {dwell_tree_err}")
        except Exception as lp_err:
            logger.warning(f"Error computing top landing pages: {lp_err}")
            summary["top_landing_pages"] = []
            summary["top_visited_pages"] = []
            summary["page_dwell_times"] = []
            summary["site_visit_tree"] = []

        # 6. Geographic Distribution (Countries)
        try:
            cursor.execute(f'''
                SELECT COALESCE(country, 'Unknown'), COUNT(DISTINCT session_id) as cnt
                FROM site_usage_events
                WHERE {time_filter} AND session_id IS NOT NULL AND session_id != ''
                GROUP BY COALESCE(country, 'Unknown')
                ORDER BY cnt DESC
                LIMIT 8
            ''')
            summary["geographic_distribution"] = [{"country": row[0], "count": int(row[1])} for row in cursor.fetchall()]
        except Exception as e:
            logger.debug("Failed querying geographic distribution: %s", e)
            summary["geographic_distribution"] = []

        # 7. Device Types, Browsers, and OS
        try:
            cursor.execute(f'''
                SELECT COALESCE(device_type, 'Unknown'), COUNT(DISTINCT session_id) as cnt
                FROM site_usage_events
                WHERE {time_filter} AND session_id IS NOT NULL AND session_id != ''
                GROUP BY COALESCE(device_type, 'Unknown')
                ORDER BY cnt DESC
            ''')
            summary["device_breakdown"] = [{"device": row[0], "count": int(row[1])} for row in cursor.fetchall()]

            cursor.execute(f'''
                SELECT COALESCE(browser, 'Unknown'), COUNT(DISTINCT session_id) as cnt
                FROM site_usage_events
                WHERE {time_filter} AND session_id IS NOT NULL AND session_id != ''
                GROUP BY COALESCE(browser, 'Unknown')
                ORDER BY cnt DESC
                LIMIT 6
            ''')
            summary["browser_breakdown"] = [{"browser": row[0], "count": int(row[1])} for row in cursor.fetchall()]

            cursor.execute(f'''
                SELECT COALESCE(os, 'Unknown'), COUNT(DISTINCT session_id) as cnt
                FROM site_usage_events
                WHERE {time_filter} AND session_id IS NOT NULL AND session_id != ''
                GROUP BY COALESCE(os, 'Unknown')
                ORDER BY cnt DESC
                LIMIT 6
            ''')
            summary["os_breakdown"] = [{"os": row[0], "count": int(row[1])} for row in cursor.fetchall()]
        except Exception as os_err:
            logger.debug("OS breakdown query notice: %s", os_err)

        # 8. Recent Audit Events
        try:
            cursor.execute(f'''
                SELECT event_type, ticker, latency_ms, cost_saved_usd, timestamp,
                       COALESCE(session_id, '-'), COALESCE(traffic_source, 'Direct'),
                       COALESCE(country, 'Unknown'), COALESCE(device_type, 'Unknown')
                FROM site_usage_events
                WHERE {time_filter}
                ORDER BY timestamp DESC
                LIMIT 50
            ''')
            for row in cursor.fetchall():
                fmt_ts = _format_timestamp(row[4])
                summary["recent_events"].append({
                    "event_type": row[0],
                    "ticker": row[1] or "-",
                    "latency_ms": round(float(row[2] or 0), 1),
                    "cost_saved_usd": round(float(row[3] or 0), 3),
                    "formatted_time": fmt_ts,
                    "timestamp": fmt_ts,
                    "session_id": str(row[5])[:10],
                    "source": row[6],
                    "traffic_source": row[6],
                    "country": row[7],
                    "device": row[8],
                })
        except Exception as e:
            logger.debug("Failed querying recent events with rich columns, falling back: %s", e)
            # Fallback if new columns not yet queried
            cursor.execute(f'''
                SELECT event_type, ticker, latency_ms, cost_saved_usd, timestamp
                FROM site_usage_events
                WHERE {time_filter}
                ORDER BY timestamp DESC
                LIMIT 20
            ''')
            for row in cursor.fetchall():
                fmt_ts = _format_timestamp(row[4])
                summary["recent_events"].append({
                    "event_type": row[0],
                    "ticker": row[1] or "-",
                    "latency_ms": round(float(row[2] or 0), 1),
                    "cost_saved_usd": round(float(row[3] or 0), 3),
                    "formatted_time": fmt_ts,
                    "timestamp": fmt_ts,
                    "session_id": "-",
                    "source": "Unrecorded",
                    "traffic_source": "Unrecorded",
                    "country": "Unknown",
                    "device": "Unknown",
                })
    except Exception as e:
        logger.error(f"Error fetching site usage summary: {e}")
    finally:
        cursor.close()
        conn.close()
    return summary


def get_traffic_flow_analytics(days: int = None, start_date = None, end_date = None, exclude_tests: bool = True) -> dict:
    """
    Computes fine-grained link dwell times and internal transition navigation tree
    across sessions for the traffic and landing pages analytics dashboard.
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()
    try:
        time_filter = _build_telemetry_time_filter(
            supabase_url, days=days, start_date=start_date, end_date=end_date, exclude_tests=exclude_tests
        )
        try:
            cursor.execute(f'''
                SELECT id, session_id, COALESCE(landing_page, ''), details, ticker, event_type, timestamp
                FROM site_usage_events
                WHERE {time_filter}
                ORDER BY timestamp ASC
            ''')
            all_events = cursor.fetchall()
        except Exception as e:
            logger.debug("Failed querying all events with landing_page column, falling back: %s", e)
            cursor.execute(f'''
                SELECT id, session_id, '', details, ticker, event_type, timestamp
                FROM site_usage_events
                WHERE {time_filter}
                ORDER BY timestamp ASC
            ''')
            all_events = cursor.fetchall()
        return compute_page_dwell_and_visit_tree(all_events)
    except Exception as e:
        logger.error(f"Error computing traffic flow analytics: {e}")
        return {
            "page_dwell_times": [],
            "site_visit_tree": [],
            "overall_avg_dwell_seconds": 0.0,
            "formatted_overall_avg_dwell": "0s",
            "total_dwell_hours": 0.0,
            "total_navigation_transitions": 0,
            "top_contributing_page": None
        }
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception as close_err:
            logger.debug("Traffic flow cursor close notice: %s", close_err)


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

        placeholder = get_placeholder()
        safe_limit = max(1, min(int(limit or 25), 500))
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
            LIMIT {placeholder}
        ''', (safe_limit,))
        sessions = cursor.fetchall()
        for s in sessions:
            sess_id, start_ts, source, ref, country, device, browser, count = s
            try:
                cursor.execute(f'''
                    SELECT event_type, ticker, timestamp, COALESCE(landing_page, ''), details
                    FROM site_usage_events
                    WHERE session_id = {placeholder} AND {time_filter}
                    ORDER BY timestamp ASC
                ''', (sess_id,))
                sess_events = cursor.fetchall()
            except Exception as e:
                logger.debug("Failed querying session events with landing_page, falling back: %s", e)
                cursor.execute(f'''
                    SELECT event_type, ticker, timestamp, '', details
                    FROM site_usage_events
                    WHERE session_id = {placeholder} AND {time_filter}
                    ORDER BY timestamp ASC
                ''', (sess_id,))
                sess_events = cursor.fetchall()

            events = []
            session_landing_page = "/"
            first_event = True
            first_dt = None
            prev_dt = None

            for ev in sess_events:
                ev_type, ev_ticker, ev_ts, ev_lp, ev_det = ev
                cur_dt = _parse_event_ts(ev_ts)
                if first_dt is None and cur_dt is not None:
                    first_dt = cur_dt

                delta_sec = 0
                if prev_dt is not None and cur_dt is not None:
                    delta_sec = max(0, min(int((cur_dt - prev_dt).total_seconds()), 1800))
                prev_dt = cur_dt or prev_dt

                if first_event:
                    first_event = False
                    p = str(ev_lp).strip() if ev_lp else ""
                    if not p and ev_det:
                        try:
                            d = json.loads(ev_det) if isinstance(ev_det, str) else ev_det
                            p = d.get("landing_page") or d.get("path") or d.get("page") or ""
                            if not p and d.get("landing_url"):
                                from urllib.parse import urlparse
                                p = urlparse(d["landing_url"]).path
                        except Exception as parse_err:
                            logger.debug("Failed to parse journey landing page: %s", parse_err)
                    if not p and ev_ticker and str(ev_ticker).upper() != "APP":
                        p = f"/dossier/{clean_ticker(ev_ticker)}"
                    if not p:
                        if "COMPARE" in (ev_type or ""): p = "/compare"
                        elif "TICKET" in (ev_type or ""): p = "/contact"
                        elif "PDF" in (ev_type or ""): p = f"/dossier/{clean_ticker(ev_ticker)}" if ev_ticker else "/dossier"
                        else: p = "/"
                    if not p.startswith("/"):
                        p = "/" + p
                    if len(p) > 1 and p.endswith("/"):
                        p = p.rstrip("/")
                    session_landing_page = p

                events.append({
                    "event_type": ev_type,
                    "ticker": ev_ticker if (ev_ticker and str(ev_ticker).upper() != "APP") else "",
                    "timestamp": _format_timestamp(ev_ts),
                    "delta_sec": delta_sec,
                })

            total_dur = 0
            if first_dt is not None and prev_dt is not None and prev_dt >= first_dt:
                total_dur = int((prev_dt - first_dt).total_seconds())
            # Also account for explicit client PAGE_DWELL beacon seconds on single-page reading sessions
            beacon_dwell_sum = 0
            for ev in sess_events:
                ev_det = ev[4]
                if ev_det:
                    try:
                        d_obj = json.loads(ev_det) if isinstance(ev_det, str) else ev_det
                        if isinstance(d_obj, dict) and d_obj.get("dwell_seconds"):
                            beacon_dwell_sum += int(min(float(d_obj["dwell_seconds"]), 1800.0))
                    except Exception as bd_err:
                        logger.debug("Beacon dwell parse notice: %s", bd_err)
            total_dur = max(total_dur, beacon_dwell_sum)

            formatted_start = _format_timestamp(start_ts)
            journeys.append({
                "session_id": sess_id,
                "start_time": formatted_start,
                "started_at": formatted_start,
                "duration_seconds": total_dur,
                "formatted_duration": format_duration(total_dur),
                "traffic_source": source or "Direct / Bookmark",
                "referrer": ref or "Direct",
                "country": country or "IN",
                "device_type": device or "Desktop",
                "browser": browser or "Unknown",
                "action_count": count,
                "landing_page": session_landing_page,
                "events": events,
                "steps": events,
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
            admin_emails = get_admin_emails()
            admin_emails_sql = ", ".join(f"'{e}'" for e in sorted(admin_emails)) if admin_emails else "'admin@moatnomics.com'"
            cursor.execute(f"""
                SELECT 
                    COUNT(*), 
                    COUNT(CASE WHEN subscription_tier IN ('pro_monthly', 'pro_annual') THEN 1 END) 
                FROM user_accounts
                WHERE email NOT LIKE '%@example.com' 
                  AND email NOT LIKE '%@test.com' 
                  AND email NOT LIKE '%@pytest.com'
                  AND email NOT LIKE 'test_%'
                  AND email NOT LIKE 'admin@%'
                  AND id NOT LIKE 'test_%'
                  AND id NOT LIKE 'usr_test_%'
                  AND id NOT LIKE 'adm_%'
                  AND id NOT IN ('guest_web_user', 'test_user', 'testclient', 'test_admin')
                  AND LOWER(email) NOT IN ({admin_emails_sql})
                  AND id NOT IN ('adm_owner_lyndon', 'admin');
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
            admin_emails = get_admin_emails()
            admin_emails_sql = ", ".join(f"'{e}'" for e in sorted(admin_emails)) if admin_emails else "'admin@moatnomics.com'"
            p = get_placeholder()
            safe_limit = max(1, min(int(limit or 20), 500))
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
                WHERE {time_filter} 
                  AND e.user_email IS NOT NULL 
                  AND e.user_email != ''
                  AND LOWER(e.user_email) NOT IN ({admin_emails_sql})
                  AND (u.id IS NULL OR (u.id NOT LIKE 'test_%' AND u.id NOT LIKE 'usr_test_%' AND u.id NOT LIKE 'adm_%'))
                  AND (u.email IS NULL OR LOWER(u.email) NOT IN ({admin_emails_sql}))
                GROUP BY e.user_email, u.id
                ORDER BY total_events DESC
                LIMIT {safe_limit};
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
                except Exception as acc_err:
                    logger.debug("Failed to fetch user account details for %s: %s", email, acc_err)

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
        admin_emails = get_admin_emails()
        admin_emails_sql = ", ".join(f"'{e}'" for e in sorted(admin_emails)) if admin_emails else "'admin@moatnomics.com'"
        admin_ids = get_admin_user_ids()
        admin_ids_sql = ", ".join(f"'{i}'" for i in sorted(admin_ids)) if admin_ids else "'adm_owner_primary'"

        # 1. Purge synthetic test events & admin visit events from site_usage_events
        cursor.execute(f"""
            DELETE FROM site_usage_events
            WHERE user_email LIKE '%@example.com'
               OR user_email LIKE '%@test.com'
               OR user_email LIKE '%@pytest.com'
               OR user_email LIKE 'test_%'
               OR user_email LIKE '%ghost_user%'
               OR LOWER(user_email) IN ({admin_emails_sql})
               OR user_id IN ('guest_web_user', 'test_user', 'testclient', 'test_admin')
               OR user_id LIKE 'test_%'
               OR user_id LIKE 'usr_test_%'
               OR user_id IN ({admin_ids_sql})
               OR user_id LIKE 'adm_%'
               OR ticker IN ('TEST', 'APP', 'XYZ', 'SAMPLE', 'MOCK')
               OR ticker LIKE 'TEST%'
               OR ticker LIKE 'UNIT_TEST_%'
               OR browser LIKE '%testclient%'
               OR browser LIKE '%pytest%'
               OR browser LIKE '%python-requests%'
               OR event_type LIKE 'UNIT_TEST_%'
               OR event_type LIKE 'TEST_%'
               OR event_type LIKE 'ADMIN_%'
               OR (event_type = 'api_v1_fetch' AND browser IS NULL AND session_id IS NULL)
               OR landing_page LIKE '/admin%'
               OR landing_page LIKE '%/admin%';
        """)
        purged_counts["events_purged"] = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0

        # 2. Purge test and automated bot/spam support_tickets
        try:
            cursor.execute("""
                DELETE FROM support_tickets
                WHERE user_email LIKE '%@example.com'
                   OR user_email LIKE '%@test.com'
                   OR user_email LIKE '%@pytest.com'
                   OR user_email LIKE '%@domain.org'
                   OR user_email LIKE '%@nolettersbox.com'
                   OR user_email LIKE 'test_%'
                   OR ticket_id LIKE 'TKT-TEST-%'
                   OR UPPER(ticket_id) = 'TKT-0F9A10CE'
                   OR subject LIKE '%[TEST]%'
                   OR (LENGTH(TRIM(message)) >= 16 AND TRIM(message) NOT LIKE '% %');
            """)
            purged_counts["tickets_purged"] = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
            cursor.execute("""
                DELETE FROM ticket_responses
                WHERE UPPER(ticket_id) = 'TKT-0F9A10CE'
                   OR ticket_id LIKE 'TKT-TEST-%'
                   OR ticket_id NOT IN (SELECT ticket_id FROM support_tickets);
            """)
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
                   OR user_id LIKE 'usr_test_%'
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
                   OR id LIKE 'usr_test_%'
                   OR id IN ('guest_web_user', 'test_user', 'testclient', 'test_admin');
            """)
            purged_counts["users_purged"] = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        except Exception as ue:
            logger.warning(f"User accounts purge notice: {ue}")

        # 5. Purge test credit_usage_ledger and user_thesis_ledger
        try:
            cursor.execute("""
                DELETE FROM credit_usage_ledger
                WHERE user_id LIKE 'test_%'
                   OR user_id LIKE 'usr_test_%'
                   OR user_id IN ('guest_web_user', 'test_user', 'testclient', 'test_admin');
            """)
            purged_counts["ledger_purged"] = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
            cursor.execute("""
                DELETE FROM user_thesis_ledger
                WHERE user_id LIKE 'test_%'
                   OR user_id LIKE 'usr_test_%'
                   OR user_id IN ('guest_web_user', 'test_user', 'testclient', 'test_admin');
            """)
        except Exception as le:
            logger.warning(f"Credit usage ledger purge notice: {le}")

        # 6. Purge leaked test stubs from alternative_yield_products and reports
        try:
            cursor.execute("""
                DELETE FROM alternative_yield_products
                WHERE product_id = 'GULLAK___SAFEGOLD'
                   OR product_name = 'Gold Yield 16% Leasing';
            """)
            purged_counts["safety_radar_stubs_purged"] = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        except Exception as sre:
            logger.warning(f"Safety radar stub purge notice: {sre}")

        try:
            cursor.execute("""
                DELETE FROM reports
                WHERE SUBSTR(ticker, 1, 5) IN ('COAL_', 'TEST_', 'UNIT_')
                   OR SUBSTR(ticker, 1, 9) = 'UNITCOAL_'
                   OR ticker IN ('TESTCORP', 'TESTPEER', 'ZZTESTONLY', 'COALESCE_TEST')
                   OR short_name = 'Coalesce Test Ltd';
            """)
            purged_counts["test_reports_purged"] = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
            cursor.execute("""
                DELETE FROM report_revisions
                WHERE SUBSTR(ticker, 1, 5) IN ('COAL_', 'TEST_', 'UNIT_')
                   OR SUBSTR(ticker, 1, 9) = 'UNITCOAL_'
                   OR ticker IN ('TESTCORP', 'TESTPEER', 'ZZTESTONLY', 'COALESCE_TEST');
            """)
            # If a test suite overwrote INFY or TCS with a short test stub (<2000 chars), restore the full revision
            p = "%s" if get_supabase_url() else "?"
            for canonical_ticker in ("INFY", "TCS"):
                cursor.execute(
                    f"SELECT report_text, baseline_price, baseline_pe, baseline_mcap FROM report_revisions WHERE ticker = {p} AND LENGTH(report_text) > 5000 ORDER BY LENGTH(report_text) DESC, id DESC LIMIT 1;",
                    (canonical_ticker,)
                )
                full_rev = cursor.fetchone()
                if full_rev and full_rev[0]:
                    cursor.execute(
                        f"UPDATE reports SET report_text = {p} WHERE ticker = {p} AND LENGTH(report_text) < 2500;",
                        (full_rev[0], canonical_ticker)
                    )
                    cursor.execute(
                        f"DELETE FROM report_revisions WHERE ticker = {p} AND LENGTH(report_text) < 2500;",
                        (canonical_ticker,)
                    )
            cursor.execute("""
                DELETE FROM discovery_reel
                WHERE ticker = 'TESTCORP'
                   OR SUBSTR(ticker, 1, 5) IN ('TEST_', 'UNIT_')
                   OR company_name = 'Test Diagnostics Corp'
                   OR edition_date >= '2099-01-01';
            """)
            cursor.execute("""
                DELETE FROM cached_fundamentals
                WHERE SUBSTR(ticker, 1, 5) IN ('COAL_', 'TEST_', 'UNIT_')
                   OR SUBSTR(ticker, 1, 9) = 'UNITCOAL_'
                   OR ticker IN ('TESTCORP', 'TESTPEER', 'ZZTESTONLY', 'COALESCE_TEST')
                   OR source = 'UNIT_TEST';
            """)
            cursor.execute("""
                DELETE FROM compliance_audit_log
                WHERE SUBSTR(ticker, 1, 5) IN ('COAL_', 'TEST_', 'UNIT_')
                   OR SUBSTR(ticker, 1, 9) = 'UNITCOAL_'
                   OR ticker IN ('TESTCORP', 'TESTPEER', 'ZZTESTONLY', 'COALESCE_TEST');
            """)
            cursor.execute("""
                DELETE FROM autonomous_event_ledger
                WHERE ticker LIKE 'TEST_%'
                   OR trigger_source LIKE '%TEST%'
                   OR summary LIKE '%2026-10-25%'
                   OR summary LIKE '%2026-10-26%'
                   OR summary LIKE '%2026-10-27%'
                   OR summary LIKE '%2099-%';
            """)
            cursor.execute("""
                DELETE FROM asset_scan_runs
                WHERE triggered_by = 'unit_test_suite';
            """)
        except Exception as rpe:
            logger.warning(f"Test reports purge notice: {rpe}")

        conn.commit()
    except Exception as e:
        logger.error(f"Error executing test data purge: {e}")
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.debug("Purge rollback notice: %s", rb_err)
    finally:
        cursor.close()
        conn.close()

    return purged_counts


_ORGANIC_SEARCH_SOURCES = {"Google Search", "Bing Search", "Yahoo Search", "DuckDuckGo"}


def record_crawler_hit(bot_name: str, kind: str, path: str, status_code: int = 200) -> None:
    """Logs a search/AI crawler fetch. Stored as BOT_CRAWL events, which are excluded from visitor analytics."""
    record_usage_event(
        event_type="BOT_CRAWL",
        details={"bot": bot_name, "kind": kind, "status": int(status_code), "path": path},
        traffic_source="Crawler",
        browser=bot_name,
        os=kind,
        device_type="Bot",
        landing_page=path,
        is_test_override=True,
    )


def _seo_channel(source: str) -> str:
    src = source or ""
    if src in _ORGANIC_SEARCH_SOURCES:
        return "Organic Search"
    if src.endswith("(AI)") or src == "Other AI Search":
        return "AI Search"
    return "Other"


def get_seo_summary(days: int = 30) -> dict:
    """SEO/GEO effort tracking: crawler visits, organic + AI-search sessions, landing pages and downstream actions."""
    summary = {
        "days": days,
        "crawlers": [],
        "crawl_pages": [],
        "crawl_total": 0,
        "channels": [],
        "organic_landing_pages": [],
        "daily_trend": [],
        "total_sessions": 0,
        "search_sessions": 0,
    }
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        time_filter = _build_telemetry_time_filter(
            get_supabase_url(), days=days, exclude_tests=True, include_bots=True
        )
        cursor.execute(f'''
            SELECT event_type, session_id, traffic_source, COALESCE(landing_page, ''), browser, os, timestamp, details
            FROM site_usage_events
            WHERE {time_filter}
            ORDER BY timestamp ASC
        ''')
        rows = cursor.fetchall()
    except Exception as e:
        logger.warning(f"SEO summary query notice: {e}")
        rows = []
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception as close_err:
            logger.debug("SEO summary close notice: %s", close_err)

    bots, crawl_pages = {}, {}
    sessions = {}
    asset_crawls = {"Equities": 0, "Mutual Funds": 0, "Corporate Debt": 0, "REITs": 0, "ETFs": 0, "MSME": 0, "General": 0}

    for ev_type, sess, source, lp, browser, os_kind, ts, det in rows:
        if ev_type == "BOT_CRAWL":
            name = browser or "Unknown bot"
            status = 200
            try:
                d = json.loads(det) if isinstance(det, str) else (det or {})
                status = int(d.get("status", 200))
            except Exception as parse_err:
                logger.debug("Crawler details parse notice: %s", parse_err)
            b = bots.setdefault(name, {"bot": name, "kind": os_kind or "Search", "hits": 0, "pages": set(), "errors": 0, "last_seen": ""})
            b["hits"] += 1
            b["pages"].add(lp)
            b["errors"] += 1 if status >= 400 else 0
            b["last_seen"] = str(ts)[:16]
            crawl_pages[lp] = crawl_pages.get(lp, 0) + 1

            # Categorize asset class crawled
            if "/dossier/" in lp or lp == "/equities":
                asset_crawls["Equities"] += 1
            elif "/funds" in lp:
                asset_crawls["Mutual Funds"] += 1
            elif "/debt" in lp:
                asset_crawls["Corporate Debt"] += 1
            elif "/reits" in lp:
                asset_crawls["REITs"] += 1
            elif "/etfs" in lp:
                asset_crawls["ETFs"] += 1
            elif "/msme" in lp:
                asset_crawls["MSME"] += 1
            else:
                asset_crawls["General"] += 1
            continue

        if not sess:
            continue
        s = sessions.setdefault(sess, {"source": source or "Direct / Bookmark", "landing": lp or "/", "date": str(ts)[:10], "pdf": False, "pricing": False})
        if ev_type == "PDF_DOWNLOAD":
            s["pdf"] = True
        if "/pricing" in (lp or ""):
            s["pricing"] = True

    all_crawlers = sorted(
        ({"bot": b["bot"], "kind": b["kind"], "hits": b["hits"], "pages": len(b["pages"]), "errors": b["errors"], "last_seen": b["last_seen"]} for b in bots.values()),
        key=lambda x: x["hits"], reverse=True,
    )
    summary["crawlers"] = all_crawlers
    summary["ai_crawlers"] = [b for b in all_crawlers if b["kind"] == "AI"]
    summary["search_crawlers"] = [b for b in all_crawlers if b["kind"] == "Search"]
    summary["crawl_total"] = sum(b["hits"] for b in all_crawlers)
    summary["ai_crawl_total"] = sum(b["hits"] for b in summary["ai_crawlers"])
    summary["search_crawl_total"] = sum(b["hits"] for b in summary["search_crawlers"])
    summary["crawl_pages"] = [{"path": p, "hits": h} for p, h in sorted(crawl_pages.items(), key=lambda x: x[1], reverse=True)[:12]]
    summary["asset_class_crawls"] = [{"asset": k, "hits": v} for k, v in asset_crawls.items() if v > 0]

    channels = {"Organic Search": [0, 0, 0], "AI Search": [0, 0, 0], "Other": [0, 0, 0]}
    landing, trend = {}, {}
    for s in sessions.values():
        ch = _seo_channel(s["source"])
        channels[ch][0] += 1
        channels[ch][1] += 1 if s["pdf"] else 0
        channels[ch][2] += 1 if s["pricing"] else 0
        if ch != "Other":
            landing[s["landing"]] = landing.get(s["landing"], 0) + 1
            trend[s["date"]] = trend.get(s["date"], 0) + 1
    summary["total_sessions"] = len(sessions)
    summary["search_sessions"] = channels["Organic Search"][0] + channels["AI Search"][0]
    summary["ai_search_sessions"] = channels["AI Search"][0]
    summary["channels"] = [{"channel": k, "sessions": v[0], "pdf_sessions": v[1], "pricing_sessions": v[2]} for k, v in channels.items()]
    summary["organic_landing_pages"] = [{"path": p, "sessions": c} for p, c in sorted(landing.items(), key=lambda x: x[1], reverse=True)[:12]]
    summary["daily_trend"] = [{"date": d, "sessions": c} for d, c in sorted(trend.items())]
    return summary


def get_returning_visitor_insights(
    days: int = 30,
    start_date=None,
    end_date=None,
    exclude_tests: bool = True,
    limit: int = 25,
) -> dict:
    """
    Computes Returning Visitor & Return-Intent Analytics:
    1. Stitches anonymous persistent `visitor_id`s to authenticated `user_email` / `user_id` once signed in.
    2. Separates First-Time vs. Returning Visitors (>= 2 distinct sessions OR explicit client `visit_number >= 2`).
    3. Ranks "What Brought Users Back" (`return_magnets` + `return_intent_categories`) across return sessions.
    4. Builds expandable Multi-Session Returning Visitor Timelines (`returning_timelines`).
    """
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    supabase_url = get_supabase_url()

    result = {
        "total_visitors": 0,
        "returning_visitors": 0,
        "new_visitors": 0,
        "returning_rate_pct": 0.0,
        "identified_returning_count": 0,
        "avg_sessions_per_returning": 0.0,
        "return_dwell_avg_seconds": 0.0,
        "formatted_return_dwell_avg": "0s",
        "new_dwell_avg_seconds": 0.0,
        "formatted_new_dwell_avg": "0s",
        "return_magnets": [],
        "return_intent_categories": [],
        "returning_timelines": [],
    }

    try:
        where_clause = _build_telemetry_time_filter(
            supabase_url=supabase_url,
            days=days,
            start_date=start_date,
            end_date=end_date,
            exclude_tests=exclude_tests,
            include_bots=False,
        )
        cursor.execute(
            f"""
            SELECT
                id, session_id, user_id, user_email, event_type, ticker,
                landing_page, traffic_source, details, browser, timestamp
            FROM site_usage_events
            WHERE {where_clause}
            ORDER BY timestamp ASC, id ASC
            """
        )
        rows = cursor.fetchall() or []
    except Exception as q_err:
        logger.warning("Failed querying returning visitor insights: %s", q_err)
        rows = []
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception as c_err:
            logger.debug("Connection close notice in get_returning_visitor_insights: %s", c_err)

    if not rows:
        return result

    # Pass 1: Parse events, filter synthetic/admin rows if exclude_tests, and build identity stitch map
    parsed_events = []
    vid_to_email = {}
    vid_to_uid = {}
    sess_to_email = {}
    sess_to_vid = {}

    for r in rows:
        eid, sess_raw, uid_raw, email_raw, ev_type_raw, tick_raw, lp_raw, src_raw, det_raw, brw_raw, ts_raw = r[:11]
        det = {}
        if det_raw:
            try:
                det = json.loads(det_raw) if isinstance(det_raw, str) else det_raw
                if not isinstance(det, dict):
                    det = {}
            except Exception as j_err:
                logger.debug("JSON parse notice in get_returning_visitor_insights: %s", j_err)
                det = {}

        sess_id = str(sess_raw or "").strip() or f"anon_evt_{eid}"
        uid = str(uid_raw or "").strip()
        email = str(email_raw or "").strip().lower()
        ev_type = str(ev_type_raw or "").strip()
        tick = clean_ticker(tick_raw) if tick_raw else ""
        lp = str(lp_raw or det.get("path") or det.get("landing_page") or "/").strip() or "/"
        if not lp.startswith("/"):
            lp = "/" + lp
        if len(lp) > 1 and lp.endswith("/"):
            lp = lp.rstrip("/")

        if exclude_tests and is_excluded_telemetry_event(
            event_type=ev_type,
            ticker=tick,
            browser=str(brw_raw or ""),
            user_id=uid,
            user_email=email,
            landing_page=lp,
            session_id=sess_id,
            details=det,
        ):
            continue

        vid = str(det.get("visitor_id") or "").strip()
        if vid and sess_id:
            sess_to_vid[sess_id] = vid
        if email:
            sess_to_email[sess_id] = email
            if vid:
                vid_to_email[vid] = email
        if uid and vid:
            vid_to_uid[vid] = uid

        parsed_events.append({
            "id": eid,
            "session_id": sess_id,
            "visitor_id": vid,
            "user_id": uid,
            "user_email": email,
            "event_type": ev_type,
            "ticker": tick,
            "path": lp,
            "traffic_source": str(src_raw or "Direct / Bookmark").strip() or "Direct / Bookmark",
            "details": det,
            "timestamp": _parse_event_ts(ts_raw),
            "ts_raw": str(ts_raw or ""),
        })

    if not parsed_events:
        return result

    # Propagate stitched email across sessions sharing a visitor_id
    for sess_id, vid in sess_to_vid.items():
        if sess_id in sess_to_email and vid not in vid_to_email:
            vid_to_email[vid] = sess_to_email[sess_id]

    # Pass 2: Group events into visitor profiles -> sessions
    visitors = {}
    for ev in parsed_events:
        sess_id = ev["session_id"]
        vid = ev["visitor_id"] or sess_to_vid.get(sess_id, "")
        stitched_email = ev["user_email"] or sess_to_email.get(sess_id, "") or (vid_to_email.get(vid, "") if vid else "")
        stitched_uid = ev["user_id"] or (vid_to_uid.get(vid, "") if vid else "")

        if stitched_email:
            v_key = f"acct:{stitched_email}"
        elif stitched_uid:
            v_key = f"uid:{stitched_uid}"
        elif vid:
            v_key = f"vis:{vid}"
        else:
            v_key = f"sess:{sess_id}"

        prof = visitors.setdefault(v_key, {
            "visitor_key": v_key,
            "visitor_id": vid,
            "user_email": stitched_email,
            "user_id": stitched_uid,
            "max_visit_number": 1,
            "explicit_returning": False,
            "days_since_last_visit": None,
            "sessions": {},
        })
        if stitched_email and not prof["user_email"]:
            prof["user_email"] = stitched_email
        if vid and not prof["visitor_id"]:
            prof["visitor_id"] = vid

        det = ev["details"]
        try:
            v_num = int(det.get("visit_number") or 1)
            if v_num > prof["max_visit_number"]:
                prof["max_visit_number"] = v_num
        except (TypeError, ValueError):
            v_num = 1

        if det.get("is_returning") is True or v_num >= 2:
            prof["explicit_returning"] = True

        if det.get("days_since_last_visit") is not None:
            try:
                prof["days_since_last_visit"] = round(float(det.get("days_since_last_visit")), 1)
            except (TypeError, ValueError):
                pass

        s_obj = prof["sessions"].setdefault(sess_id, {
            "session_id": sess_id,
            "first_ts": ev["timestamp"],
            "first_ts_raw": ev["ts_raw"],
            "last_ts": ev["timestamp"],
            "traffic_source": ev["traffic_source"],
            "entry_path": ev["path"],
            "explicit_visit_num": v_num,
            "events": [],
        })
        if ev["timestamp"] and (not s_obj["first_ts"] or ev["timestamp"] < s_obj["first_ts"]):
            s_obj["first_ts"] = ev["timestamp"]
            s_obj["first_ts_raw"] = ev["ts_raw"]
            s_obj["entry_path"] = ev["path"]
        if ev["timestamp"] and (not s_obj["last_ts"] or ev["timestamp"] > s_obj["last_ts"]):
            s_obj["last_ts"] = ev["timestamp"]
        if v_num > s_obj["explicit_visit_num"]:
            s_obj["explicit_visit_num"] = v_num
        s_obj["events"].append(ev)

    # Pass 3: Compute session dwell, return magnets, intent categories, and timelines
    total_visitors = len(visitors)
    returning_profiles = []
    return_session_dwells = []
    new_session_dwells = []
    magnet_accum = {}
    intent_cat_accum = {}

    def _intent_bucket(path: str, ev_types: set) -> str:
        if any("UNLOCK" in t or "PDF" in t or "MODEL" in t for t in ev_types):
            return "Deep-Dive Unlocks & Exports"
        if path.startswith("/dossier/"):
            return "Equity Dossiers"
        if path.startswith("/discovery") or path.startswith("/opportunities"):
            return "Daily Discovery & Alpha Screening"
        if path.startswith("/compare"):
            return "Peer Cluster Benchmarking"
        if path.startswith("/funds"):
            return "Mutual Fund Look-Through"
        if path.startswith("/debt") or path.startswith("/sovereign") or path.startswith("/reits") or path.startswith("/calculator"):
            return "Yield, Debt & Post-Tax Real Assets"
        if path.startswith("/safety-radar"):
            return "Retail Safety Radar"
        if path.startswith("/equities"):
            return "Equities Screener & Directory"
        if path.startswith("/pricing"):
            return "Pricing & Credit Packs"
        return "Platform Navigation"

    for v_key, prof in visitors.items():
        ordered_sessions = sorted(
            prof["sessions"].values(),
            key=lambda s: (s["first_ts"] is None, s["first_ts"] or datetime.min, s["session_id"]),
        )
        is_returning = (len(ordered_sessions) >= 2) or prof["explicit_returning"]

        session_summaries = []
        visitor_total_dwell = 0.0
        visitor_tickers = []
        visitor_cat_counts = {}
        high_intent_badges = []

        for idx, s_obj in enumerate(ordered_sessions):
            evs = s_obj["events"]
            route_dwell = {}
            route_order = []
            ev_types_set = set()

            for i, e_item in enumerate(evs):
                rp = e_item["path"]
                ev_u = (e_item["event_type"] or "").upper()
                ev_types_set.add(ev_u)
                if rp not in route_dwell:
                    route_dwell[rp] = 0.0
                    route_order.append(rp)

                c_dw = e_item["details"].get("dwell_seconds") or e_item["details"].get("duration_seconds")
                dw_val = 0.0
                if c_dw is not None:
                    try:
                        dw_val = min(max(float(c_dw), 0.0), 1800.0)
                    except (TypeError, ValueError):
                        dw_val = 0.0
                elif i + 1 < len(evs) and e_item["timestamp"] and evs[i + 1]["timestamp"]:
                    delta_s = (evs[i + 1]["timestamp"] - e_item["timestamp"]).total_seconds()
                    if 1.0 <= delta_s <= 1800.0 and evs[i + 1]["event_type"].upper() != "PAGE_DWELL":
                        dw_val = delta_s
                route_dwell[rp] = min(1800.0, route_dwell[rp] + dw_val)

                tk = e_item["ticker"]
                if not tk and rp.startswith("/dossier/") and len(rp.split("/")) > 2:
                    tk = clean_ticker(rp.split("/")[2])
                if tk and tk not in ("APP", "TEST") and tk not in visitor_tickers:
                    visitor_tickers.append(tk)

                if "UNLOCK" in ev_u and "Deep-Dive Unlock" not in high_intent_badges:
                    high_intent_badges.append("Deep-Dive Unlock")
                if ("PDF" in ev_u or "MODEL" in ev_u) and "Report / Model Export" not in high_intent_badges:
                    high_intent_badges.append("Report / Model Export")
                if (rp.startswith("/compare") or "COMPARE" in ev_u) and "Peer Compare" not in high_intent_badges:
                    high_intent_badges.append("Peer Compare")
                if rp.startswith("/pricing") and "Checked Pricing" not in high_intent_badges:
                    high_intent_badges.append("Checked Pricing")

            sess_dwell = round(sum(route_dwell.values()), 1)
            visitor_total_dwell += sess_dwell

            is_return_session = (idx >= 1) or (s_obj["explicit_visit_num"] >= 2) or (is_returning and len(ordered_sessions) == 1)
            if is_return_session:
                return_session_dwells.append(sess_dwell)
                # Determine primary return magnet for this return session:
                # If entry was generic '/', prefer deepest non-root route visited in that return session if any
                non_root = [r_p for r_p in route_order if r_p != "/"]
                if s_obj["entry_path"] == "/" and non_root:
                    magnet_path = max(non_root, key=lambda r_p: (route_dwell.get(r_p, 0.0), -route_order.index(r_p)))
                else:
                    magnet_path = s_obj["entry_path"]

                m_entry = magnet_accum.setdefault(magnet_path, {
                    "path": magnet_path,
                    "sessions": 0,
                    "visitors": set(),
                    "dwell_total": 0.0,
                    "high_intent_actions": 0,
                })
                m_entry["sessions"] += 1
                m_entry["visitors"].add(v_key)
                m_entry["dwell_total"] += route_dwell.get(magnet_path, sess_dwell)
                if any(("UNLOCK" in x or "PDF" in x or "MODEL" in x or "COMPARE" in x) for x in ev_types_set):
                    m_entry["high_intent_actions"] += 1

                bucket = _intent_bucket(magnet_path, ev_types_set)
                b_entry = intent_cat_accum.setdefault(bucket, {"category": bucket, "sessions": 0, "visitors": set()})
                b_entry["sessions"] += 1
                b_entry["visitors"].add(v_key)
            else:
                new_session_dwells.append(sess_dwell)

            routes_out = []
            for r_p in route_order[:8]:
                cat_n, cat_i = classify_page_category(r_p)
                visitor_cat_counts[cat_n] = visitor_cat_counts.get(cat_n, 0) + 1
                routes_out.append({
                    "path": r_p,
                    "category": cat_n,
                    "icon": cat_i,
                    "dwell_seconds": round(route_dwell.get(r_p, 0.0), 1),
                    "formatted_dwell": format_duration(route_dwell.get(r_p, 0.0)),
                })

            entry_cat, entry_icon = classify_page_category(s_obj["entry_path"])
            started_str = _format_timestamp(s_obj["first_ts_raw"]) if s_obj["first_ts_raw"] else "Recent"
            session_summaries.append({
                "visit_index": max(idx + 1, s_obj["explicit_visit_num"]),
                "is_return_session": is_return_session,
                "started_at_str": started_str,
                "traffic_source": s_obj["traffic_source"],
                "entry_path": s_obj["entry_path"],
                "entry_category": entry_cat,
                "entry_icon": entry_icon,
                "pages_visited_count": len(route_order),
                "dwell_seconds": sess_dwell,
                "formatted_dwell": format_duration(sess_dwell),
                "routes": routes_out,
            })

        if is_returning:
            gap_days = prof["days_since_last_visit"]
            if gap_days is None and len(ordered_sessions) >= 2:
                t_prev = ordered_sessions[-2]["last_ts"] or ordered_sessions[-2]["first_ts"]
                t_curr = ordered_sessions[-1]["first_ts"]
                if t_prev and t_curr and t_curr >= t_prev:
                    gap_days = round((t_curr - t_prev).total_seconds() / 86400.0, 1)

            fav_cat = max(visitor_cat_counts.items(), key=lambda kv: kv[1])[0] if visitor_cat_counts else "Platform Page"
            raw_vid = prof["visitor_id"] or v_key
            short_tag = raw_vid[-6:].upper() if len(raw_vid) >= 6 else raw_vid.upper()
            display_id = prof["user_email"] if prof["user_email"] else f"Returning Reader #{short_tag}"
            last_seen_dt = ordered_sessions[-1]["last_ts"] or ordered_sessions[-1]["first_ts"]

            returning_profiles.append({
                "visitor_key": v_key,
                "display_identity": display_id,
                "is_authenticated": bool(prof["user_email"]),
                "visit_count": max(len(ordered_sessions), prof["max_visit_number"]),
                "recorded_sessions_in_window": len(ordered_sessions),
                "days_since_prev_visit": gap_days,
                "total_dwell_seconds": round(visitor_total_dwell, 1),
                "formatted_total_dwell": format_duration(visitor_total_dwell),
                "favorite_category": fav_cat,
                "top_tickers": visitor_tickers[:5],
                "high_intent_badges": high_intent_badges[:4],
                "last_seen_dt": last_seen_dt,
                "last_seen_str": session_summaries[-1]["started_at_str"] if session_summaries else "Recent",
                "latest_return_route": session_summaries[-1]["entry_path"] if session_summaries else "/",
                "sessions": list(reversed(session_summaries)),
            })

    returning_count = len(returning_profiles)
    new_count = max(0, total_visitors - returning_count)
    identified_count = sum(1 for rp in returning_profiles if rp["is_authenticated"])
    avg_sess_ret = round(
        sum(rp["visit_count"] for rp in returning_profiles) / max(1, returning_count),
        1,
    ) if returning_count else 0.0

    ret_avg_dwell = round(sum(return_session_dwells) / max(1, len(return_session_dwells)), 1) if return_session_dwells else 0.0
    new_avg_dwell = round(sum(new_session_dwells) / max(1, len(new_session_dwells)), 1) if new_session_dwells else 0.0

    return_magnets = []
    total_return_sessions = max(1, sum(m["sessions"] for m in magnet_accum.values()))
    for m_path, m_data in sorted(
        magnet_accum.items(),
        key=lambda kv: (kv[1]["sessions"], kv[1]["dwell_total"]),
        reverse=True,
    )[:12]:
        cat_n, cat_i = classify_page_category(m_path)
        tk = clean_ticker(m_path.split("/")[2]) if m_path.startswith("/dossier/") and len(m_path.split("/")) > 2 else ""
        avg_dw = round(m_data["dwell_total"] / max(1, m_data["sessions"]), 1)
        return_magnets.append({
            "path": m_path,
            "display_name": format_route_display(m_path),
            "category": cat_n,
            "icon": cat_i,
            "ticker": tk,
            "return_sessions_count": m_data["sessions"],
            "share_pct": round((m_data["sessions"] / total_return_sessions) * 100.0, 1),
            "unique_returning_visitors": len(m_data["visitors"]),
            "avg_dwell_seconds": avg_dw,
            "formatted_avg_dwell": format_duration(avg_dw),
            "high_intent_actions": m_data["high_intent_actions"],
        })

    return_intent_categories = [
        {
            "category": b_val["category"],
            "return_sessions": b_val["sessions"],
            "unique_visitors": len(b_val["visitors"]),
            "share_pct": round((b_val["sessions"] / total_return_sessions) * 100.0, 1),
        }
        for b_val in sorted(intent_cat_accum.values(), key=lambda x: x["sessions"], reverse=True)
    ]

    returning_profiles.sort(
        key=lambda rp: (
            rp["last_seen_dt"] is not None,
            rp["last_seen_dt"] or datetime.min,
            rp["visit_count"],
            rp["total_dwell_seconds"],
        ),
        reverse=True,
    )
    for rp in returning_profiles:
        rp.pop("last_seen_dt", None)

    result.update({
        "total_visitors": total_visitors,
        "returning_visitors": returning_count,
        "new_visitors": new_count,
        "returning_rate_pct": round((returning_count / max(1, total_visitors)) * 100.0, 1) if total_visitors else 0.0,
        "identified_returning_count": identified_count,
        "avg_sessions_per_returning": avg_sess_ret,
        "return_dwell_avg_seconds": ret_avg_dwell,
        "formatted_return_dwell_avg": format_duration(ret_avg_dwell),
        "new_dwell_avg_seconds": new_avg_dwell,
        "formatted_new_dwell_avg": format_duration(new_avg_dwell),
        "return_magnets": return_magnets,
        "return_intent_categories": return_intent_categories,
        "returning_timelines": returning_profiles[: max(1, int(limit or 25))],
    })
    return result


