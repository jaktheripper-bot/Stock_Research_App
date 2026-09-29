"""
telemetry.py
==============================================================================
Production Site Usage Telemetry, Visitor Attribution & Admin Access Control
for Stock Research App

Features:
  1. Admin Passcode Gate: Secures private telemetry and analytics views.
     Supports .streamlit/secrets.toml, environment variables, and URL query params.
  2. Visitor Acquisition Attribution: Resolves traffic sources (Direct, Google,
     X/Twitter, LinkedIn, WhatsApp, BSE India, UTM tags) and referring URLs.
  3. Device & Client Demographics: Parses user agent strings into Device Category
     (Mobile/Tablet/Desktop), Browser, and Operating System without heavy dependencies.
  4. User Journey Tracking: Automatically binds all user interactions (searches,
     comparisons, archive loads, watchlist edits, PDF exports) to anonymous session IDs.
==============================================================================
"""

import os
import uuid
import hmac
import logging
from urllib.parse import urlparse
import streamlit as st

logger = logging.getLogger("equity_research.telemetry")

DEFAULT_ADMIN_PASSCODE = "admin2026"

def get_admin_passcode() -> str:
    """Retrieve configured administrator passcode from database, secrets or environment."""
    try:
        from db import get_system_setting
        db_pass = get_system_setting("admin_passcode")
        if db_pass:
            return db_pass.strip()
    except Exception:
        pass

    try:
        if hasattr(st, "secrets") and st.secrets.get("ADMIN_PASSCODE"):
            return str(st.secrets["ADMIN_PASSCODE"]).strip()
    except Exception:
        pass
    env_pass = os.environ.get("ADMIN_PASSCODE")
    if env_pass:
        return env_pass.strip()
    return DEFAULT_ADMIN_PASSCODE

def verify_admin_passcode(candidate: str) -> bool:
    """Verify administrator passcode securely using constant-time comparison."""
    if not candidate:
        return False
    expected = get_admin_passcode()
    try:
        return hmac.compare_digest(str(candidate).strip(), expected)
    except Exception:
        return str(candidate).strip() == expected

def update_admin_passcode(current_passcode: str, new_passcode: str) -> tuple[bool, str]:
    """Verify current passcode and persist new administrator passcode to DB and local secrets."""
    if not verify_admin_passcode(current_passcode):
        return False, "Current administrator password is incorrect."
    
    cleaned_new = (new_passcode or "").strip()
    if len(cleaned_new) < 6:
        return False, "New password must be at least 6 characters long."
    
    # Persist to database (dual-binding PostgreSQL / SQLite)
    try:
        from db import set_system_setting
        db_ok = set_system_setting("admin_passcode", cleaned_new)
        if not db_ok:
            logger.warning("Failed to persist admin password to database.")
    except Exception as e:
        logger.error(f"Error persisting admin password to DB: {e}")

    # Also sync local .streamlit/secrets.toml if accessible
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        secrets_path = os.path.join(base_dir, ".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            with open(secrets_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            replaced = False
            for line in lines:
                if line.strip().startswith("ADMIN_PASSCODE"):
                    new_lines.append(f'ADMIN_PASSCODE = "{cleaned_new}"\n')
                    replaced = True
                else:
                    new_lines.append(line)
            if not replaced:
                new_lines.append(f'ADMIN_PASSCODE = "{cleaned_new}"\n')
            with open(secrets_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
    except Exception as e:
        logger.warning(f"Could not update local secrets.toml: {e}")

    return True, "Password successfully updated."

def is_admin_authenticated() -> bool:
    """Check if the current session has valid administrator authorization."""
    return bool(st.session_state.get("is_admin_authenticated", False))

def set_admin_authenticated(status: bool = True):
    """Set administrator authorization state for current session."""
    st.session_state["is_admin_authenticated"] = bool(status)

def check_url_admin_auth():
    """Disabled: Strict password authentication required on login screen (no URL bypass)."""
    pass

def get_session_id() -> str:
    """Retrieve or initialize an anonymous session identifier."""
    if "telemetry_session_id" not in st.session_state:
        st.session_state["telemetry_session_id"] = f"sess_{uuid.uuid4().hex[:10]}"
    return st.session_state["telemetry_session_id"]

def parse_user_agent(ua_string: str) -> dict:
    """Classifies user agent into device, browser, and operating system."""
    if not ua_string:
        return {"device": "Desktop", "browser": "Unknown", "os": "Unknown"}

    ua = ua_string.lower()

    # 1. Device Type
    if any(k in ua for k in ["ipad", "tablet"]):
        device = "Tablet"
    elif any(k in ua for k in ["mobile", "android", "iphone", "ipod", "windows phone"]):
        device = "Mobile"
    else:
        device = "Desktop"

    # 2. Browser
    if "edg/" in ua or "edge/" in ua:
        browser = "Edge"
    elif "chrome/" in ua and "crios" not in ua and "edg" not in ua:
        browser = "Chrome"
    elif "safari/" in ua and "chrome/" not in ua and "crios" not in ua:
        browser = "Safari"
    elif "firefox/" in ua or "fxios" in ua:
        browser = "Firefox"
    elif "crios" in ua:
        browser = "Chrome iOS"
    else:
        browser = "Other"

    # 3. Operating System
    if "windows" in ua:
        os_name = "Windows"
    elif "iphone" in ua or "ipad" in ua or "ipod" in ua:
        os_name = "iOS"
    elif "android" in ua:
        os_name = "Android"
    elif "macintosh" in ua or "mac os x" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Other"

    return {"device": device, "browser": browser, "os": os_name}

def parse_traffic_source(referrer: str, query_params: dict) -> tuple:
    """
    Classifies origin into standard traffic acquisition sources
    and returns (traffic_source, clean_referrer).
    """
    # 1. UTM Attribution
    utm_source = query_params.get("utm_source") or query_params.get("ref") or query_params.get("source")
    if utm_source:
        return str(utm_source), referrer or "Campaign Link"

    # 2. Direct Navigation
    if not referrer:
        return "Direct / Bookmark", "Direct"

    ref_lower = referrer.lower()
    if "google." in ref_lower:
        return "Google Search", referrer
    elif "bing." in ref_lower:
        return "Bing Search", referrer
    elif any(k in ref_lower for k in ["t.co", "twitter.com", "x.com"]):
        return "X / Twitter", referrer
    elif "linkedin.com" in ref_lower:
        return "LinkedIn", referrer
    elif any(k in ref_lower for k in ["whatsapp.com", "wa.me"]):
        return "WhatsApp", referrer
    elif "bseindia.com" in ref_lower:
        return "BSE India", referrer
    elif "reddit.com" in ref_lower:
        return "Reddit", referrer
    elif "youtube.com" in ref_lower:
        return "YouTube", referrer
    else:
        try:
            parsed = urlparse(referrer)
            domain = parsed.netloc
            return domain if domain else "Referral", referrer
        except Exception:
            return "Referral", referrer

def extract_geo(headers: dict) -> str:
    """Extract country from reverse proxy headers (Cloudflare, Vercel, etc.)."""
    if not headers:
        return "IN"
    cf_country = headers.get("cf-ipcountry")
    if cf_country and cf_country != "XX":
        return cf_country.upper()
    x_country = headers.get("x-country-code") or headers.get("x-vercel-ip-country")
    if x_country:
        return x_country.upper()
    return "IN"

def get_visitor_context() -> dict:
    """Assembles full client environment, traffic attribution, and session info."""
    session_id = get_session_id()
    headers = {}
    try:
        if hasattr(st, "context") and hasattr(st.context, "headers") and st.context.headers:
            headers = dict(st.context.headers)
    except Exception:
        pass

    query_params = {}
    try:
        if hasattr(st, "query_params") and st.query_params:
            query_params = dict(st.query_params)
    except Exception:
        pass

    referrer = headers.get("referer") or headers.get("referrer", "")
    traffic_source, clean_ref = parse_traffic_source(referrer, query_params)
    ua_str = headers.get("user-agent", "")
    ua_info = parse_user_agent(ua_str)
    country = extract_geo(headers)

    return {
        "session_id": session_id,
        "traffic_source": traffic_source,
        "referrer": clean_ref,
        "country": country,
        "device_type": ua_info["device"],
        "browser": ua_info["browser"],
        "os": ua_info["os"],
    }

def track_user_action(
    event_type: str,
    ticker: str = "",
    latency_ms: float = 0.0,
    cost_saved_usd: float = 0.0,
    details: dict = None
):
    """
    Enriches user interaction with visitor context and logs it non-blockingly to DB.
    """
    try:
        from db import record_usage_event
        ctx = get_visitor_context()
        record_usage_event(
            event_type=event_type,
            ticker=ticker,
            latency_ms=latency_ms,
            cost_saved_usd=cost_saved_usd,
            details=details,
            session_id=ctx["session_id"],
            traffic_source=ctx["traffic_source"],
            referrer=ctx["referrer"],
            country=ctx["country"],
            device_type=ctx["device_type"],
            browser=ctx["browser"],
            os=ctx["os"],
        )
    except Exception as e:
        logger.debug(f"Telemetry tracking suppressed: {e}")

def init_session_telemetry():
    """Initializes session tracking once per browser session."""
    if "session_telemetry_logged" not in st.session_state:
        st.session_state["session_telemetry_logged"] = True
        ctx = get_visitor_context()
        utm_params = {}
        try:
            if hasattr(st, "query_params"):
                utm_params = {k: v for k, v in dict(st.query_params).items() if k.startswith("utm_") or k in ("ref", "source")}
        except Exception:
            pass
        track_user_action(
            event_type="SESSION_START",
            ticker="APP",
            details={"utm_params": utm_params}
        )
