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
    render_policies_view,
)
from ui.comparison import render_peer_comparison_view
from ui.analytics_hub import render_site_analytics_view
from ui.auth_ui import (
    render_login_dialog,
    render_ledger_dialog,
    check_and_render_auth_dialogs,
)
from ui.billing_modal import render_top_up_dialog
from core.auth import handle_auth_callback
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
handle_auth_callback()

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

    /* 5. Cognitive Ergonomics: Tabular lining numerals for vertical alignment & magnitude scanning */
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"],
    table, th, td,
    .stDataFrame,
    [data-testid="stTable"] {
        font-variant-numeric: tabular-nums !important;
        font-feature-settings: "tnum" 1 !important;
    }

    /* 6. WCAG 2.2 AA Minimum Interactive Target Sizing (24x24 px) */
    button,
    [data-baseweb="select"],
    [data-testid="stExpander"] summary {
        min-height: 24px !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 4. Silent Deep-Linking URL State Restoration & Policy Routing
restore_dossier_from_url()

query_page = st.query_params.get("page") or st.query_params.get("policy")
if query_page and query_page.lower() in ["terms", "privacy", "refund-policy", "shipping-policy", "contact", "disclaimer", "pricing", "policies"]:
    st.session_state["active_view"] = "policies"

# 4b. Modal Dialog Triggers (Authentication, Top-Up Packs, Ledger)
if st.session_state.get("show_login_dialog"):
    st.session_state["show_login_dialog"] = False
    render_login_dialog()

if st.session_state.get("show_top_up_dialog"):
    st.session_state["show_top_up_dialog"] = False
    render_top_up_dialog()

if st.session_state.get("show_ledger_dialog"):
    st.session_state["show_ledger_dialog"] = False
    render_ledger_dialog()

# 5. Persistent Sidebar Rendering (Search, Archive Selectbox, & Revision Timeline)
render_sidebar()

# 6. Main Content Header
st.title("Equity Research Analysis Platform")
st.markdown('<p style="font-size: 19px; color: #888888;">To aid stock discovery and simplify fundamentals.</p>', unsafe_allow_html=True)

# 7. Navigation Bar (Institutional Dossier, Peer Comparison, Legal Policies, Private Analytics)
cur_view = st.session_state.get("active_view", "dossier")
is_admin = is_admin_authenticated()

if is_admin:
    nav_c1, nav_c2, nav_c3, nav_c4 = st.columns([1, 1, 1, 1])
    with nav_c1:
        if st.button("🔍 Institutional Dossier", key="btn_nav_dossier", type="primary" if cur_view == "dossier" else "secondary", width="stretch"):
            st.session_state["active_view"] = "dossier"
            st.query_params.clear()
            track_user_action("PAGE_VIEW", details={"page": "dossier"})
            st.rerun()
    with nav_c2:
        if st.button("⚖️ Peer Comparison", key="btn_nav_compare", type="primary" if cur_view == "compare" else "secondary", width="stretch"):
            st.session_state["active_view"] = "compare"
            st.query_params.clear()
            track_user_action("PAGE_VIEW", details={"page": "compare"})
            st.rerun()
    with nav_c3:
        if st.button("📜 Legal & Policies", key="btn_nav_policies", type="primary" if cur_view == "policies" else "secondary", width="stretch"):
            st.session_state["active_view"] = "policies"
            track_user_action("PAGE_VIEW", details={"page": "policies"})
            st.rerun()
    with nav_c4:
        if st.button("📊 Private Admin Analytics 🔐", key="btn_nav_admin_analytics", type="primary" if cur_view == "analytics" else "secondary", width="stretch"):
            st.session_state["active_view"] = "analytics"
            st.query_params.clear()
            track_user_action("PAGE_VIEW", details={"page": "analytics"})
            st.rerun()
else:
    nav_c1, nav_c2, nav_c3 = st.columns([1, 1, 1])
    with nav_c1:
        if st.button("🔍 Institutional Dossier", key="btn_nav_dossier", type="primary" if cur_view == "dossier" else "secondary", width="stretch"):
            st.session_state["active_view"] = "dossier"
            st.query_params.clear()
            track_user_action("PAGE_VIEW", details={"page": "dossier"})
            st.rerun()
    with nav_c2:
        if st.button("⚖️ Peer Comparison", key="btn_nav_compare", type="primary" if cur_view == "compare" else "secondary", width="stretch"):
            st.session_state["active_view"] = "compare"
            st.query_params.clear()
            track_user_action("PAGE_VIEW", details={"page": "compare"})
            st.rerun()
    with nav_c3:
        if st.button("📜 Legal & Policies", key="btn_nav_policies", type="primary" if cur_view == "policies" else "secondary", width="stretch"):
            st.session_state["active_view"] = "policies"
            track_user_action("PAGE_VIEW", details={"page": "policies"})
            st.rerun()

st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

# Render active auth & billing modals if requested in session state
check_and_render_auth_dialogs()

# 8. View Routing Dispatch
if cur_view == "compare":
    render_peer_comparison_view()
    check_and_render_auth_dialogs()
elif cur_view == "policies":
    render_policies_view()
    check_and_render_auth_dialogs()
elif cur_view == "analytics" and is_admin:
    render_site_analytics_view()
    check_and_render_auth_dialogs()
elif cur_view == "analytics" and not is_admin:
    st.session_state["active_view"] = "dossier"
    st.rerun()
else:
    # Default View: Institutional Research Dossier
    render_dossier_view()
    check_and_render_auth_dialogs()

# 9. Statutory Footer & Direct Policy Links
st.markdown("---")
f_c1, f_c2 = st.columns([3, 2])
with f_c1:
    st.caption("📈 **Stock Research App** • Automated 7-Pillar Institutional Equity Research Engine Grounded in Public BSE Disclosures.")
    st.caption("⚖️ **SEBI Safe Harbor:** Non-advisory computational research synthesis software utility (SAC Code 998314). Not an investment advisor or research analyst.")
with f_c2:
    st.markdown(
        """
        <div style="font-size: 12px; color: #888888; text-align: right; line-height: 1.8;">
            <a href="?page=terms" target="_self" style="color: #0ea5e9; text-decoration: none;">Terms & Conditions</a> • 
            <a href="?page=privacy" target="_self" style="color: #0ea5e9; text-decoration: none;">Privacy Policy</a> • 
            <a href="?page=refund-policy" target="_self" style="color: #0ea5e9; text-decoration: none;">Refund Policy</a><br>
            <a href="?page=shipping-policy" target="_self" style="color: #0ea5e9; text-decoration: none;">Delivery Policy</a> • 
            <a href="?page=contact" target="_self" style="color: #0ea5e9; text-decoration: none;">Contact Us</a> • 
            <a href="?page=disclaimer" target="_self" style="color: #0ea5e9; text-decoration: none;">Disclaimer</a>
        </div>
        """,
        unsafe_allow_html=True
    )
