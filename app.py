"""
Equity Research Analysis Platform - Main Application Entrypoint.

Orchestrates page configuration, global styling, session telemetry, sidebar navigation,
and routes to modular view controllers under `ui/views/`.
"""

import os
import logging
import streamlit as st

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("equity_research.app")

from ui.views import (
    render_sidebar,
    render_dossier_view,
    restore_dossier_from_url,
)
from ui.comparison import render_peer_comparison_view
from ui.analytics_hub import render_site_analytics_view
from telemetry import (
    track_user_action,
    init_session_telemetry,
    check_url_admin_auth,
    is_admin_authenticated,
)

# 1. Page Configuration (Must be invoked before any other Streamlit UI calls)
st.set_page_config(page_title="Equity Research AI", layout="wide", page_icon="📈")

# 2. Google Analytics 4 Tracking Script Injection
def inject_ga4_tracking():
    """Injects Google Analytics 4 tracking script if GA4_MEASUREMENT_ID is configured in secrets."""
    try:
        ga_id = st.secrets.get("GA4_MEASUREMENT_ID") or os.environ.get("GA4_MEASUREMENT_ID")
        if ga_id and str(ga_id).startswith("G-"):
            st.html(
                f"""
                <!-- Google tag (gtag.js) -->
                <script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>
                <script>
                  window.dataLayer = window.dataLayer || [];
                  function gtag(){{dataLayer.push(arguments);}}
                  gtag('js', new Date());
                  gtag('config', '{ga_id}');
                </script>
                """
            )
    except Exception:
        pass

inject_ga4_tracking()
check_url_admin_auth()
init_session_telemetry()

# 3. Production CSS Stylesheet (Metric Unclip, Reading Measure, & Responsive Wrapping)
st.markdown(
    """
    <style>
    /* 1. Constrain canvas width on zoom-out while staying fluid on mobile / zoom-in */
    .main .block-container {
        max-width: min(1280px, 95vw) !important;
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
        margin: 0 auto !important;
    }

    /* 2. Prevent st.metric from cutting off text with ellipses and wrap gracefully */
    [data-testid="stMetric"] {
        min-width: 180px !important;
    }
    [data-testid="stMetricValue"] > div {
        font-size: clamp(1.15rem, 1.4vw, 1.5rem) !important;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: unset !important;
        line-height: 1.25 !important;
    }
    [data-testid="stMetricLabel"] > div {
        font-size: 0.95rem !important;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: unset !important;
    }

    /* 3. Constrain reading measure strictly on report prose */
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li {
        max-width: 860px !important;
        line-height: 1.65 !important;
        font-size: 17px !important;
    }

    /* 4. Responsive horizontal column wrapping for zoom-in */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 16px !important;
    }
    [data-testid="stHorizontalBlock"] > div {
        flex: 1 1 200px !important;
        min-width: 180px !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 4. Silent Deep-Linking URL State Restoration
restore_dossier_from_url()

# 5. Persistent Sidebar Rendering (Search, Archive Selectbox, & Revision Timeline)
render_sidebar()

# 6. Main Content Header
st.title("Equity Research Analysis Platform")
st.markdown('<p style="font-size: 19px; color: #888888;">To aid stock discovery and simplify fundamentals.</p>', unsafe_allow_html=True)

# 7. Navigation Bar (Institutional Dossier, Peer Comparison, Private Analytics)
cur_view = st.session_state.get("active_view", "dossier")
is_admin = is_admin_authenticated()

if is_admin:
    nav_c1, nav_c2, nav_c3 = st.columns([1, 1, 1])
    with nav_c1:
        if st.button("🔍 Institutional Dossier", key="btn_nav_dossier", type="primary" if cur_view == "dossier" else "secondary", width="stretch"):
            st.session_state["active_view"] = "dossier"
            track_user_action("PAGE_VIEW", details={"page": "dossier"})
            st.rerun()
    with nav_c2:
        if st.button("⚖️ Peer Comparison", key="btn_nav_compare", type="primary" if cur_view == "compare" else "secondary", width="stretch"):
            st.session_state["active_view"] = "compare"
            track_user_action("PAGE_VIEW", details={"page": "compare"})
            st.rerun()
    with nav_c3:
        if st.button("📊 Private Admin Analytics 🔐", key="btn_nav_admin_analytics", type="primary" if cur_view == "analytics" else "secondary", width="stretch"):
            st.session_state["active_view"] = "analytics"
            track_user_action("PAGE_VIEW", details={"page": "analytics"})
            st.rerun()
else:
    nav_c1, nav_c2 = st.columns(2)
    with nav_c1:
        if st.button("🔍 Institutional Dossier", key="btn_nav_dossier", type="primary" if cur_view == "dossier" else "secondary", width="stretch"):
            st.session_state["active_view"] = "dossier"
            track_user_action("PAGE_VIEW", details={"page": "dossier"})
            st.rerun()
    with nav_c2:
        if st.button("⚖️ Peer Comparison", key="btn_nav_compare", type="primary" if cur_view == "compare" else "secondary", width="stretch"):
            st.session_state["active_view"] = "compare"
            track_user_action("PAGE_VIEW", details={"page": "compare"})
            st.rerun()

st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

# 8. View Routing Dispatch
if cur_view == "compare":
    render_peer_comparison_view()
    st.stop()
elif cur_view == "analytics" and is_admin:
    render_site_analytics_view()
    st.stop()
elif cur_view == "analytics" and not is_admin:
    st.session_state["active_view"] = "dossier"
    st.rerun()

# Default View: Institutional Research Dossier
render_dossier_view()
