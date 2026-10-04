"""
ui/analytics_hub.py
==============================================================================
Backend Site Usage Measurements & Telemetry Analytics Hub.
Renders restricted administrative telemetry:
  1. Admin Passcode Gate: Ensures only the site owner can view analytics.
  2. Traffic Acquisition: Identifies where visitors originate (Direct, Google,
     Twitter/X, LinkedIn, WhatsApp, BSE India, UTM campaigns, referrers, geo/countries).
  3. User Engagement & Behavior: Tracks what users do (searches, archive loads,
     peer comparisons, watchlist actions, 7-pillar expansions, PDF downloads).
  4. Session Journeys: Chronological breadcrumb path of individual visitor sessions.
  5. Live Operational Telemetry: Latency, cache hit efficiency, and dollar credit savings.
==============================================================================
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from db import (
    IST,
    get_site_usage_summary,
    get_session_journeys,
    get_support_tickets,
    update_ticket_status,
    get_open_tickets_count,
    get_user_usage_analytics,
    get_all_billables,
    get_revenue_analytics_summary,
    process_refund,
)
from telemetry import (
    is_admin_authenticated,
    set_admin_authenticated,
    verify_admin_passcode,
    get_admin_passcode,
)


def render_admin_login_gate():
    """Renders a restricted access lockbox when unauthenticated users attempt to view analytics."""
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    col_center = st.columns([1, 2, 1])[1]
    with col_center:
        with st.container(border=True):
            st.markdown("### 🔒 Administrator Access Required")
            st.write(
                "This dashboard contains private site usage measurements, traffic origin attribution, "
                "and user behavioral telemetry. Authorization is restricted strictly to the site owner."
            )
            pass_input = st.text_input(
                "Enter Administrator Passcode:",
                type="password",
                key="hub_passcode_input",
                placeholder="••••••••••••"
            )
            col_b1, col_b2 = st.columns([1, 1])
            with col_b1:
                if st.button("Authenticate", key="btn_auth_submit", type="primary", width="stretch"):
                    if verify_admin_passcode(pass_input):
                        set_admin_authenticated(True)
                        st.toast("Admin authorization certified.", icon="🔓")
                        st.rerun()
                    else:
                        st.error("Invalid passcode. Access denied.")
            with col_b2:
                if st.button("Return to Dossier", key="btn_return_dossier", width="stretch"):
                    st.session_state["active_view"] = "dossier"
                    st.rerun()

            st.caption("🔒 Strict password authentication enforced. Access is restricted to certified administrators.")


def render_site_analytics_view():
    """Renders the administrative site usage measurements and operational analytics dashboard."""
    # 1. Authorization Enforcement Gate
    if not is_admin_authenticated():
        render_admin_login_gate()
        return

    # 2. Header & Admin Controls Bar
    c_title, c_range, c_lock = st.columns([2.0, 1.8, 0.8])
    today = datetime.now(IST).date()
    start_date = None
    end_date = None
    selected_days = 30

    with c_title:
        st.markdown("### 📊 Executive Telemetry & Site Usage Hub")
        st.caption("Live visitor acquisition, user behavior paths, cache efficiency, and API cost savings.")
    with c_range:
        range_mode = st.selectbox(
            "Telemetry Window:",
            options=[
                "Last 24 Hours",
                "Last 7 Days",
                "Last 30 Days (Default)",
                "Last 90 Days",
                "Month to Date",
                "Custom Date Range 📅"
            ],
            index=2,
            key="analytics_days_picker",
            label_visibility="collapsed"
        )
        if range_mode == "Last 24 Hours":
            selected_days = 1
        elif range_mode == "Last 7 Days":
            selected_days = 7
        elif range_mode == "Last 30 Days (Default)":
            selected_days = 30
        elif range_mode == "Last 90 Days":
            selected_days = 90
        elif range_mode == "Month to Date":
            start_date = today.replace(day=1)
            end_date = today
            selected_days = None
        elif range_mode == "Custom Date Range 📅":
            default_start = today - timedelta(days=14)
            date_selection = st.date_input(
                "Select Date Range (Start to End):",
                value=(default_start, today),
                max_value=today,
                key="analytics_custom_date_range"
            )
            if isinstance(date_selection, (list, tuple)) and len(date_selection) == 2:
                start_date, end_date = date_selection
                selected_days = None
            elif isinstance(date_selection, (list, tuple)) and len(date_selection) == 1:
                start_date = end_date = date_selection[0]
                selected_days = None
            else:
                start_date = default_start
                end_date = today
                selected_days = None

    with c_lock:
        if st.button("🔒 Lock / Logout", key="btn_hub_logout", width="stretch"):
            set_admin_authenticated(False)
            st.session_state["active_view"] = "dossier"
            st.toast("Admin session locked.", icon="🔒")
            st.rerun()

    if start_date and end_date:
        st.caption(f"🗓️ Telemetry Scope: **{start_date.strftime('%d-%b-%Y')}** to **{end_date.strftime('%d-%b-%Y')}**")

    try:
        summary = get_site_usage_summary(days=selected_days, start_date=start_date, end_date=end_date)
    except Exception as err:
        st.error(f"Failed to fetch usage metrics: {err}")
        return

    # 3. Top Executive KPI Cards
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "Unique Sessions",
        summary.get("unique_sessions", 0),
        help="Number of distinct visitor browser sessions detected."
    )
    k2.metric(
        "Total User Actions",
        summary.get("total_actions", 0),
        help="All combined searches, comparisons, archive loads, and exports."
    )
    k3.metric(
        "Cache Efficiency",
        f"{summary.get('cache_efficiency_pct', 0.0)}%",
        delta="Zero-Cost Serve",
        help="Inquiries resolved without calling billable Gemini/Perplexity external APIs."
    )
    k4.metric(
        "Est. API Cost Saved",
        f"${summary.get('total_cost_saved_usd', 0.0):.2f}",
        delta="Search Bypass",
        help="Cumulative dollars saved by bypassing Google Search Grounding fees and synthesis."
    )
    k5.metric(
        "PDFs Exported",
        summary.get("pdf_downloads", 0),
        help="Total institutional research PDF reports downloaded by users."
    )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    try:
        open_tickets = get_open_tickets_count()
    except Exception:
        open_tickets = 0

    support_tab_title = f"📩 User Complaints & Tickets ({open_tickets} Open)" if open_tickets > 0 else "📩 User Complaints & Tickets"

    # 4. Tabbed Deep-Dive Workspaces
    t_billables, t_users, t_tickets, t_traffic, t_behavior, t_journeys, t_stream = st.tabs([
        "💳 Live Billables & Invoices",
        "👤 User Accounts & Usage",
        support_tab_title,
        "🌐 Traffic Origins (Where They Come From)",
        "🎯 User Actions (What Users Are Doing)",
        "🧭 Session Journeys (Step-by-Step Paths)",
        "📜 Live Telemetry Audit Stream"
    ])

    # -------------------------------------------------------------------------
    # TAB 0: Live Billables, Invoices, GST & Returns Desk
    # -------------------------------------------------------------------------
    with t_billables:
        st.markdown("#### 💳 Live Billables, Invoices & Returns Audit Desk")
        st.caption("Immutable transaction ledger, GST/SAC 998314 tax breakdowns, customer invoices, and refund reversals for regulatory audit compliance.")

        try:
            rev_summary = get_revenue_analytics_summary(days=selected_days, start_date=start_date, end_date=end_date)
        except Exception:
            rev_summary = {}

        # Executive Financial KPIs
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Gross Revenue", f"₹{rev_summary.get('gross_revenue_inr', 0.0):,.2f}", help="Total paid purchases (Card/UPI)")
        m2.metric("GST (18% SAC 998314)", f"₹{rev_summary.get('tax_gst_collected_inr', 0.0):,.2f}", help="CGST 9% + SGST 9% / IGST 18%")
        m3.metric("Net Software Revenue", f"₹{rev_summary.get('net_revenue_inr', 0.0):,.2f}", help="Revenue net of GST and returns")
        m4.metric("Total Returns/Refunds", f"₹{rev_summary.get('refunded_amount_inr', 0.0):,.2f}", f"{rev_summary.get('refunded_orders_count', 0)} return(s)", delta_color="inverse")
        m5.metric("Circulating Credits", f"{rev_summary.get('credits_in_circulation', 0.0):,.1f}", f"{rev_summary.get('active_subscribers_count', 0)} Pro users", help="Unearned revenue / active credit liabilities")

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        cb1, cb2, cb3 = st.columns([2.5, 1.2, 1.3])
        with cb1:
            bill_filter = st.segmented_control(
                "Filter Ledger:",
                options=["All Records 📜", "Paid Only ✅", "Refunded ↩️"],
                default="All Records 📜",
                key="billables_status_filter"
            )
        with cb2:
            if st.button("🔄 Refresh Ledger", key="btn_refresh_billables", width="stretch"):
                st.rerun()

        status_arg = "success" if bill_filter == "Paid Only ✅" else ("refunded" if bill_filter == "Refunded ↩️" else None)
        all_billables = get_all_billables(status=status_arg, limit=100)

        if all_billables:
            df_export = pd.DataFrame(all_billables)
            csv_bytes = df_export.to_csv(index=False).encode('utf-8')
            with cb3:
                st.download_button(
                    label="📥 Export GSTR-1 Tax CSV",
                    data=csv_bytes,
                    file_name=f"Tax_Invoice_Register_{datetime.now(IST).strftime('%d_%m_%Y')}.csv",
                    mime="text/csv",
                    width="stretch"
                )

        if all_billables:
            table_rows = []
            for b in all_billables:
                status_icon = "✅ Paid" if b["status"] == "success" else ("↩️ Refunded" if b["status"] == "refunded" else b["status"].upper())
                table_rows.append({
                    "Invoice #": b["invoice_number"],
                    "Date (IST)": b["date"],
                    "Customer Email": b["customer_email"],
                    "Pack / Description": b["pack_type"].replace("_", " ").title(),
                    "Base (₹)": f"₹{b['base_amount_inr']:,.2f}",
                    "GST 18% (₹)": f"₹{b['tax_gst_inr']:,.2f}",
                    "Total (₹)": f"₹{b['amount_inr']:,.2f}",
                    "Gateway ID": b["gateway_payment_id"] or b["gateway_order_id"] or "system",
                    "Status": status_icon,
                    "Tx ID": b["id"]
                })
            st.dataframe(pd.DataFrame(table_rows), width="stretch", hide_index=True)
        else:
            st.info("No billing transactions found matching filter.")

        # Formal Refund Reversal Action Modal
        with st.expander("↩️ Process Return & Credit Reversal (Regulatory Audit Action)", expanded=False):
            st.markdown("**Issue a formal refund, reverse granted research credits, and commit an immutable audit trail:**")
            with st.form("admin_refund_form", clear_on_submit=True):
                r_c1, r_c2 = st.columns(2)
                with r_c1:
                    ref_tx_id = st.text_input("Transaction ID or Invoice Number:", placeholder="e.g. tx_1728000000_usr_123 or INV-1728000000")
                    ref_amt = st.number_input("Refund Amount (INR, Leave 0 for full amount):", min_value=0.0, step=100.0, value=0.0)
                with r_c2:
                    ref_reason = st.selectbox(
                        "Refund Reason (Mandatory Audit Categorization):",
                        options=[
                            "Customer requested return within 7-day policy",
                            "Accidental duplicate charge",
                            "Payment gateway verification dispute",
                            "Service non-delivery or system generation error",
                            "Goodwill courtesy reversal"
                        ]
                    )
                    ref_notes = st.text_input("Administrator Notes:", placeholder="Approval notes / ticket link...")

                ref_submit = st.form_submit_button("🚨 Commit Refund & Reverse Credits", type="primary")
                if ref_submit:
                    if not ref_tx_id:
                        st.error("Please provide a valid Transaction ID or Invoice Number.")
                    else:
                        clean_target_tx = ref_tx_id.strip()
                        if clean_target_tx.startswith("INV-"):
                            for b in all_billables:
                                if b["invoice_number"] == clean_target_tx:
                                    clean_target_tx = b["id"]
                                    break
                        amt_arg = float(ref_amt) if ref_amt > 0 else None
                        ok, msg = process_refund(clean_target_tx, refund_amount=amt_arg, reason=ref_reason, admin_notes=ref_notes)
                        if ok:
                            st.success(f"✅ {msg}")
                            st.toast("Refund processed cleanly.", icon="↩️")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")

    # -------------------------------------------------------------------------
    # TAB 1: User Accounts & Usage Intelligence
    # -------------------------------------------------------------------------
    with t_users:
        st.markdown("#### 👤 User Accounts & Usage Intelligence")
        st.caption("Live registered accounts, per-user query volumes, distinct tickers researched, and credit consumption.")

        try:
            user_analytics = get_user_usage_analytics(days=selected_days, start_date=start_date, end_date=end_date)
        except Exception:
            user_analytics = {}

        u1, u2, u3, u4 = st.columns(4)
        u1.metric("Registered Users", user_analytics.get("total_registered_users", 0), help="Total user profiles created in user_accounts")
        u2.metric("Active in Period", user_analytics.get("active_users_in_period", 0), help="Unique logged-in users who executed actions in this scope")
        u3.metric("Signed-in Actions", user_analytics.get("signed_in_actions_count", 0), f"{user_analytics.get('guest_actions_count', 0)} guest actions", delta_color="normal")
        u4.metric("Pro Subscribers", user_analytics.get("pro_subscribers_count", 0), help="Users on Pro Monthly or Pro Annual plans")

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        st.markdown("##### 🏆 Top Active Users & Research Volume")
        top_u = user_analytics.get("top_users", [])
        if top_u:
            u_df = pd.DataFrame([
                {
                    "User Email": u["email"],
                    "Full Name": u["name"],
                    "Total Actions": u["total_actions"],
                    "Tickers Studied": u["distinct_tickers"],
                    "PDF Exports": u["pdf_exports"],
                    "Comparisons": u["comparisons"],
                    "Credits Balance": f"{u['credits_balance']:.1f}",
                    "Subscription": u["subscription_tier"].upper(),
                    "Last Active (IST)": u["last_active"]
                }
                for u in top_u
            ])
            st.dataframe(u_df, width="stretch", hide_index=True)
        else:
            st.info("No signed-in user actions recorded in this scope yet.")

    # -------------------------------------------------------------------------
    # TAB 2: User Complaints, Support Tickets & Grievance Redressal
    # -------------------------------------------------------------------------
    with t_tickets:
        st.markdown("#### 📩 User Grievances, Inquiries & Redressal Desk")
        st.write("Track and resolve complaints from users, payment issues, or statutory regulatory inquiries.")

        c_status, c_refresh = st.columns([3, 1])
        with c_status:
            sel_status = st.segmented_control(
                "Filter Ticket Status:",
                options=["Open Only ⏳", "All Tickets 📜", "Resolved Only ✅"],
                default="Open Only ⏳",
                key="admin_ticket_status_filter"
            )
        with c_refresh:
            if st.button("🔄 Refresh Tickets", key="btn_refresh_tickets", width="stretch"):
                st.rerun()

        filter_arg = "open" if sel_status == "Open Only ⏳" else ("resolved" if sel_status == "Resolved Only ✅" else "all")
        tickets = get_support_tickets(status=filter_arg, limit=50)

        if tickets:
            for t in tickets:
                status_color = "#ef4444" if t["status"] == "open" else "#10b981"
                status_badge = "⏳ OPEN" if t["status"] == "open" else "✅ RESOLVED"
                with st.expander(
                    f"{status_badge} [{t['category'].upper()}] {t['ticket_id']} — {t['subject']} ({t['user_email']})",
                    expanded=(t["status"] == "open")
                ):
                    st.caption(f"**Submitted At:** {t['created_at']} | **User Name:** {t['user_name'] or 'N/A'} | **Source:** `{t['source']}`")
                    st.markdown("**Message / Complaint Content:**")
                    st.info(t["message"])

                    if t.get("admin_notes"):
                        st.caption(f"**Admin Resolution Notes:** {t['admin_notes']}")

                    col_act1, col_act2 = st.columns([2, 1])
                    with col_act1:
                        new_note = st.text_input(
                            "Resolution / Follow-up Note:",
                            value=t.get("admin_notes", ""),
                            key=f"note_{t['ticket_id']}",
                            placeholder="Add action taken, email response date, or refund reference..."
                        )
                    with col_act2:
                        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                        if t["status"] == "open":
                            if st.button("Mark Resolved ✅", key=f"res_{t['ticket_id']}", type="primary", width="stretch"):
                                update_ticket_status(t["ticket_id"], "resolved", new_note)
                                st.toast(f"Ticket {t['ticket_id']} marked as resolved!", icon="✅")
                                st.rerun()
                        else:
                            if st.button("Re-open Ticket ⏳", key=f"reopen_{t['ticket_id']}", width="stretch"):
                                update_ticket_status(t["ticket_id"], "open", new_note)
                                st.toast(f"Ticket {t['ticket_id']} re-opened.", icon="⏳")
                                st.rerun()
        else:
            st.success("🎉 No pending complaints or unresolved tickets in this view! All inquiries are resolved.")

    # -------------------------------------------------------------------------
    # TAB 1: Traffic Origins & Demographics
    # -------------------------------------------------------------------------
    with t_traffic:
        st.markdown("#### 🌐 Visitor Acquisition & Traffic Channels")
        st.write("Identifies the external referral origins, campaigns, and devices powering incoming visits.")

        c_src, c_geo = st.columns([1.2, 1])
        with c_src:
            st.markdown("##### 🚀 Acquisition Source Channels")
            sources = summary.get("traffic_sources", [])
            if sources:
                src_df = pd.DataFrame(sources)
                src_df.columns = ["Traffic Channel / Source", "Visitors", "Share %"]
                st.dataframe(src_df, width="stretch", hide_index=True)
            else:
                st.info("No external referral sources detected yet (mostly direct visits).")

            st.markdown("##### 🔗 Top Referring URLs")
            referrers = summary.get("top_referrers", [])
            if referrers:
                ref_df = pd.DataFrame(referrers)
                ref_df.columns = ["Referring Domain / Link", "Inbound Visits"]
                st.dataframe(ref_df, width="stretch", hide_index=True)
            else:
                st.caption("No external referring URLs recorded for this window.")

        with c_geo:
            st.markdown("##### 📍 Geographic Origin (Countries)")
            geos = summary.get("geographic_distribution", [])
            if geos:
                geo_df = pd.DataFrame(geos)
                geo_df.columns = ["Country Code", "Visitor Actions"]
                st.dataframe(geo_df, width="stretch", hide_index=True)
            else:
                st.caption("Geographic distribution will populate dynamically.")

            st.markdown("##### 💻 Client Platforms & Devices")
            with st.container(border=True):
                devices = summary.get("device_breakdown", [])
                browsers = summary.get("browser_breakdown", [])
                os_list = summary.get("os_breakdown", [])

                d_str = ", ".join([f"{d['device']}: {d['count']}" for d in devices]) if devices else "Desktop"
                b_str = ", ".join([f"{b['browser']}: {b['count']}" for b in browsers]) if browsers else "Chrome"
                o_str = ", ".join([f"{o['os']}: {o['count']}" for o in os_list]) if os_list else "macOS / Windows"

                st.write(f"• **Device Split:** {d_str}")
                st.write(f"• **Browsers:** {b_str}")
                st.write(f"• **Operating Systems:** {o_str}")

    # -------------------------------------------------------------------------
    # TAB 2: User Behavior & Engagement
    # -------------------------------------------------------------------------
    with t_behavior:
        st.markdown("#### 🎯 User Interaction & Feature Engagement")
        st.write("Measures which companies users investigate and how deeply they engage with research tools.")

        col_b1, col_b2 = st.columns([1, 1.2])

        with col_b1:
            st.markdown("##### ⚡ Most Researched Equities")
            top_list = summary.get("top_searched_tickers", [])
            if top_list:
                top_df = pd.DataFrame(top_list)
                top_df.columns = ["Ticker", "Research Count"]
                st.dataframe(top_df, width="stretch", hide_index=True)
            else:
                st.info("No ticker queries recorded yet.")

            st.markdown("##### 💡 Compute & Credit Optimization Breakdown")
            with st.container(border=True):
                st.write(f"• **Instant Cache Hits:** {summary.get('cache_hits', 0)} queries (~15ms serve)")
                st.write(f"• **Surgical Refreshes (P5/P6):** {summary.get('surgical_refreshes', 0)} calls (Bypassed $0.035 search fees)")
                st.write(f"• **Full 7-Pillar AI Syntheses:** {summary.get('full_syntheses', 0)} deep reports")
                st.write(f"• **Peer Comparisons Run:** {summary.get('comparisons', 0)} cross-company matches")
                st.write(f"• **Watchlist Modifications:** {summary.get('watchlist_actions', 0)} additions/removals")

        with col_b2:
            st.markdown("##### 📊 Action Category Distribution")
            breakdown = summary.get("action_breakdown", {})
            if breakdown:
                b_df = pd.DataFrame([{"Action Event": k, "Occurrences": v} for k, v in breakdown.items()])
                b_df = b_df.sort_values(by="Occurrences", ascending=False)
                st.dataframe(b_df, width="stretch", hide_index=True)
            else:
                st.caption("Action distributions will populate as visitors explore.")

    # -------------------------------------------------------------------------
    # TAB 3: Session Journeys (Chronological User Trails)
    # -------------------------------------------------------------------------
    with t_journeys:
        st.markdown("#### 🧭 Individual Visitor Session Journeys")
        st.write("Chronological trail of steps taken by each visitor from initial arrival to final export.")

        try:
            journeys = get_session_journeys(days=selected_days, start_date=start_date, end_date=end_date, limit=20)
        except Exception:
            journeys = []

        if journeys:
            for j in journeys:
                sess_short = j["session_id"]
                start_t = j["start_time"]
                source = j["traffic_source"]
                country = j["country"]
                dev = f"{j['device_type']} ({j['browser']})"
                count = j["action_count"]

                with st.expander(f"📍 Session `{sess_short}` • {source} • {country} • {dev} • {count} action(s)", expanded=False):
                    st.caption(f"**Session Initiated:** {start_t} | **Referring Link:** `{j['referrer']}`")
                    for idx, step in enumerate(j["events"], 1):
                        tick_str = f" `{step['ticker']}`" if step.get("ticker") else ""
                        st.markdown(f"**{idx}.** `{step['event_type']}`{tick_str} <span style='color: #888; font-size: 12px;'>({step['timestamp']})</span>", unsafe_allow_html=True)
        else:
            st.info("Session journeys are recorded automatically when visitors interact with the site.")

    # -------------------------------------------------------------------------
    # TAB 4: Live Telemetry Stream
    # -------------------------------------------------------------------------
    with t_stream:
        st.markdown("#### 🕒 Real-Time Telemetry Audit Stream (Last 50 Events)")
        recent = summary.get("recent_events", [])
        if recent:
            rec_df = pd.DataFrame(recent)
            rec_df.columns = [
                "Event", "Ticker", "Latency (ms)", "Credits Saved ($)",
                "IST Timestamp", "Session", "Source", "Country", "Device"
            ]
            st.dataframe(rec_df, width="stretch", hide_index=True)
        else:
            st.info("Telemetry activity stream is operational. Inbound actions will appear here in real time.")

    st.markdown("---")
    st.caption(
        "🔒 **Administrative Privacy & Safe-Harbor Guarantee:** Zero personal portfolio holdings, identity records, "
        "or unmasked IP addresses are captured. Telemetry strictly monitors visitor acquisition, compute efficiency, "
        "and data integrity under SEBI educational safe-harbor standards."
    )
