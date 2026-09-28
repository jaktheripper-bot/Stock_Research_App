"""
admin.py
==============================================================================
Standalone Private Administrator Portal for Stock Research App
==============================================================================
Provides exclusive, authenticated access to site usage analytics, visitor
acquisition origins (traffic channels, referrers, geographic distribution,
device/OS demographics), user behavioral tracking, session journey breadcrumbs,
and date range filtering.

Usage:
  Local:      ./run.sh admin   (Runs on http://localhost:8502)
  Production: Deploy as a private standalone Streamlit Community Cloud app.
==============================================================================
"""

import streamlit as st
from telemetry import check_url_admin_auth, is_admin_authenticated
from ui.analytics_hub import render_site_analytics_view, render_admin_login_gate

# Configure Dedicated Admin Portal Window
st.set_page_config(
    page_title="Executive Telemetry & Site Usage Admin Portal",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Admin Portal Styling
st.markdown(
    """
    <style>
    .main .block-container {
        max-width: min(1360px, 95vw) !important;
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        margin: 0 auto !important;
    }
    header[data-testid="stHeader"] {
        background-color: transparent !important;
    }
    div[data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 26px !important;
        font-weight: 700 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 1. Proactive Query Parameter Check (?admin=YOUR_PASSCODE)
check_url_admin_auth()

# 2. Main Administration Portal Dispatcher
if not is_admin_authenticated():
    st.title("🔐 Executive Administration Portal")
    st.markdown('<p style="font-size: 16px; color: #888888;">Private operational analytics & visitor telemetry engine.</p>', unsafe_allow_html=True)
    render_admin_login_gate()
else:
    render_site_analytics_view()
