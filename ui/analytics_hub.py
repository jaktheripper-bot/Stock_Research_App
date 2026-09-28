"""
Backend Site Usage Measurements & Telemetry Analytics Hub.
Renders live operational telemetry, cache hit rates, estimated API credit savings,
top searched equities, and activity event stream.
"""

import streamlit as st
import pandas as pd
from db import get_site_usage_summary


def render_site_analytics_view():
    """Renders the backend site usage measurements and operational analytics dashboard."""
    st.markdown("### 📊 Backend Site Usage & Telemetry Analytics")
    st.caption(
        "Live operational telemetry, cache hit efficiency, credit burn savings, and query activity "
        "under SEBI safe-harbor standards."
    )

    try:
        summary = get_site_usage_summary(days=30)
    except Exception as err:
        st.error(f"Failed to fetch usage metrics: {err}")
        return

    # Top KPI Metrics Cards
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total User Searches", summary["total_queries"])
    k2.metric(
        "Cache Efficiency",
        f"{summary['cache_efficiency_pct']}%",
        delta="Instant Serve",
        help="Percentage of inquiries served via zero-cost local cache or surgical delta refreshes."
    )
    k3.metric(
        "Est. API Credits Saved",
        f"${summary['total_cost_saved_usd']:.2f}",
        delta="Search Bypass",
        help="Cumulative dollars saved by bypassing Google Search Grounding fees and re-syntheses."
    )
    k4.metric(
        "PDF Reports Exported",
        summary["pdf_downloads"],
        help="Total institutional research PDF dossiers downloaded."
    )

    st.markdown("---")

    col_left, col_right = st.columns([1, 1.2])

    with col_left:
        st.markdown("#### ⚡ Top Searched Equities")
        top_list = summary.get("top_searched_tickers", [])
        if top_list:
            top_df = pd.DataFrame(top_list)
            top_df.columns = ["Stock Ticker", "Inquiries Count"]
            st.dataframe(top_df, width="stretch", hide_index=True)
        else:
            st.info("No query activity recorded yet. Inquiries will populate here dynamically.")

        st.markdown("#### 💡 Cache & Resilience Breakdown")
        with st.container(border=True):
            st.write(f"• **Instant Cache Hits:** {summary.get('cache_hits', 0)} requests served in ~15ms")
            st.write(
                f"• **Surgical Refreshes (P5 & P6):** {summary.get('surgical_refreshes', 0)} "
                "(Eliminated $0.035 Google Search fee per call)"
            )
            st.write(f"• **Full 7-Pillar AI Syntheses:** {summary.get('full_syntheses', 0)}")
            st.write(f"• **Peer Comparisons Run:** {summary.get('comparisons', 0)}")
            st.write(f"• **Surveillance Watchlist Actions:** {summary.get('watchlist_actions', 0)}")

    with col_right:
        st.markdown("#### 🕒 Live Telemetry Activity Stream (Last 12 Events)")
        recent = summary.get("recent_events", [])
        if recent:
            rec_df = pd.DataFrame(recent)
            rec_df.columns = ["Event", "Ticker", "Latency (ms)", "Credits Saved ($)", "Timestamp (IST)"]
            st.dataframe(rec_df, width="stretch", hide_index=True)
        else:
            st.info("Activity stream is ready. Live exchange and user actions will display here.")

    st.caption(
        "🔒 **Safe-Harbor Privacy Standard:** Zero personal identifiable information (PII), portfolio holdings, "
        "or user IP addresses are captured. Telemetry strictly monitors backend compute health, API efficiency, "
        "and data integrity."
    )
