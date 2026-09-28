"""
admin.py
==============================================================================
Standalone Private Administrator Portal for Stock Research App
==============================================================================
Provides exclusive, password-protected access to site usage analytics, visitor
acquisition origins (traffic channels, referrers, geographic distribution,
device/OS demographics), user behavioral tracking, session journey breadcrumbs,
and interactive date range filtering.

Security:
  - Strict password authentication required on dedicated login screen.
  - Zero URL parameter bypass.
  - Active session memory locking.

Usage:
  Local:      ./run.sh admin   (Runs on http://localhost:8502)
  Production: Deploy as a private standalone Streamlit Community Cloud app.
==============================================================================
"""

import streamlit as st
from telemetry import (
    is_admin_authenticated,
    set_admin_authenticated,
    verify_admin_passcode,
)
from ui.analytics_hub import render_site_analytics_view

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
        padding-top: 2rem !important;
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

def render_login_screen():
    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    c1, c_card, c3 = st.columns([1, 1.8, 1])
    with c_card:
        with st.container(border=True):
            st.markdown("## 🔐 Executive Admin Portal")
            st.markdown(
                '<p style="font-size: 14px; color: #94a3b8; margin-top: -8px;">'
                'Restricted access: Real-time telemetry, visitor attribution & user journey analytics.'
                '</p>',
                unsafe_allow_html=True
            )
            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

            with st.form("admin_login_form", clear_on_submit=False):
                entered_pass = st.text_input(
                    "Administrator Password:",
                    type="password",
                    placeholder="Enter admin password...",
                    help="Password configured in your deployment secrets."
                )
                st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                login_submit = st.form_submit_button("🔓 Log In to Admin Dashboard", type="primary", width="stretch")

            if login_submit:
                if verify_admin_passcode(entered_pass):
                    set_admin_authenticated(True)
                    st.toast("Password certified. Welcome, Administrator.", icon="🔓")
                    st.rerun()
                else:
                    st.error("❌ Access Denied: Incorrect password. Please try again.")

            st.caption("🔒 All access attempts and telemetry queries are strictly isolated to authenticated administrators.")

# Dispatcher
if not is_admin_authenticated():
    render_login_screen()
else:
    render_site_analytics_view()
