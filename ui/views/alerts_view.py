"""Surveillance and regulatory alert hub view component."""

import streamlit as st
from core.db import (
    get_unread_alert_count,
    get_alert_events,
    mark_alert_as_read,
    mark_all_alerts_as_read,
    dismiss_alert,
    dismiss_all_alerts,
    get_watchlist,
    add_to_watchlist,
    remove_from_watchlist,
    get_report_by_ticker,
)
from alerts import run_surveillance_scan
from bse_master import resolve_bse_scrip_code
from telemetry import track_user_action
from ui.views.state import set_active_dossier_state, execute_stock_research, sanitize_ticker_input

@st.fragment
def render_alert_hub():
    """Renders the Granular Event Alerting Engine Hub with Feed, Watchlist, and Exchange Polling."""
    try:
        unread_c = get_unread_alert_count()
    except Exception:
        unread_c = 0

    hub_title = f"🔔 Surveillance & Regulatory Alert Hub ({unread_c} Unread)" if unread_c > 0 else "🔔 Surveillance & Regulatory Alert Hub"
    # Auto-collapse expander when a dossier is active or user requested collapse
    user_has_active_dossier = bool(st.session_state.get("last_report") or st.session_state.get("stream_pending"))
    default_expanded = (unread_c > 0) and not user_has_active_dossier and not st.session_state.get("collapse_alert_hub", False)
    with st.expander(hub_title, expanded=default_expanded):
        tab_feed, tab_watchlist, tab_scan = st.tabs([
            f"📥 Alert Feed ({unread_c})",
            "👁️ Surveillance Watchlist",
            "⚡ Scan Filings & Exchange"
        ])

        with tab_feed:
            c_filter1, c_filter2 = st.columns([3, 2])
            with c_filter1:
                sel_cat = st.segmented_control(
                    "Filter Category:",
                    options=["All", "Material 📢", "Fundamental 📊", "Valuation ⚡"],
                    default="All"
                )
            with c_filter2:
                feed_view = st.segmented_control(
                    "Feed View:",
                    options=["📥 Unread Inbox", "📜 All History"],
                    default="📥 Unread Inbox"
                )

            act_col1, act_col2 = st.columns(2)
            with act_col1:
                if st.button("✓ Mark All as Read", key="btn_mark_all_read", width="stretch", help="Mark all unread alerts as read"):
                    track_user_action("ALERTS_MARK_READ")
                    mark_all_alerts_as_read()
                    st.toast("All notifications marked as read.", icon="✅")
                    st.rerun()
            with act_col2:
                if st.button("🗑️ Dismiss All Unread", key="btn_dismiss_all_unread", width="stretch", help="Permanently clear all unread alerts"):
                    track_user_action("ALERTS_DISMISS")
                    dismiss_all_alerts(unread_only=True)
                    st.toast("Unread notifications dismissed.", icon="🗑️")
                    st.rerun()

            cat_map = {"All": None, "Material 📢": "material", "Fundamental 📊": "fundamental", "Valuation ⚡": "valuation"}
            raw_cat = cat_map.get(sel_cat)
            is_unread_only = (feed_view == "📥 Unread Inbox")
            try:
                alerts = get_alert_events(category=raw_cat, unread_only=is_unread_only, limit=30)
            except Exception:
                alerts = []

            if not alerts:
                if is_unread_only:
                    st.success("🎉 All caught up! No unread notifications in your inbox.")
                else:
                    st.info("No alert events found matching the selected filters.")
            else:
                for alt in alerts:
                    cat = alt.get("category", "material")
                    sev = alt.get("severity", "medium")
                    is_read = alt.get("is_read", False)

                    if cat == "valuation":
                        icon, border_c = "⚡", "#f59e0b"
                    elif cat == "fundamental":
                        icon, border_c = "📊", "#10b981"
                    else:
                        icon, border_c = "📢", "#3b82f6"

                    with st.container(border=True):
                        h_col1, h_col2 = st.columns([3, 1])
                        with h_col1:
                            unread_ind = "🔵 " if not is_read else ""
                            st.markdown(f"**{unread_ind}{icon} {alt['title']}**")
                            st.caption(f"🕒 {alt['timestamp']} | Source: {alt.get('source', 'BSE Surveillance')} | Tier: `{sev.upper()}`")
                        with h_col2:
                            btn_c1, btn_c2 = st.columns([1, 1])
                            with btn_c1:
                                if st.button(
                                    "Dossier",
                                    key=f"dossier_{alt['id']}",
                                    width="stretch",
                                    type="primary",
                                    help=f"Open full 7-pillar institutional equity research dossier & technical chart for {alt['ticker']}"
                                ):
                                    rec = get_report_by_ticker(alt["ticker"])
                                    if rec:
                                        set_active_dossier_state(
                                            ticker=alt["ticker"],
                                            report_text=rec.get("report_text"),
                                            report_date=rec.get("formatted_date"),
                                            fundamentals={
                                                "short_name": rec.get("short_name", alt["ticker"]),
                                                "ticker": alt["ticker"],
                                                "market_cap": rec.get("baseline_mcap", "Archived"),
                                                "pe_ratio": rec.get("baseline_pe", "N/A"),
                                                "sector": "General Industry",
                                                "current_price": rec.get("baseline_price", "N/A")
                                            },
                                            material_reason=f"🔔 Loaded from Surveillance Alert: {alt.get('title')}"
                                        )
                                    else:
                                        execute_stock_research(alt["ticker"])
                                    st.session_state["scroll_to_dossier"] = True
                                    st.session_state["collapse_alert_hub"] = True
                                    st.session_state["toast_message"] = f"📄 Loaded dossier for {alt['ticker']}!"
                                    st.rerun(scope="app")
                            with btn_c2:
                                if not is_read:
                                    if st.button(
                                        "Read",
                                        key=f"read_{alt['id']}",
                                        width="stretch",
                                        help="Mark as read (dismisses from Unread Inbox)"
                                    ):
                                        mark_alert_as_read(alt["id"])
                                        st.rerun()
                                else:
                                    if st.button(
                                        "Dismiss",
                                        key=f"dism_{alt['id']}",
                                        width="stretch",
                                        help="Permanently delete this alert from history"
                                    ):
                                        dismiss_alert(alt["id"])
                                        st.rerun()

                        if alt.get("details"):
                            st.markdown(f"> {alt['details']}")

            st.caption("_Alerts are informational event notifications of public BSE filings and exchange price moves under SEBI educational standards._")

        with tab_watchlist:
            try:
                watchlist_items = get_watchlist()
            except Exception:
                watchlist_items = []

            st.markdown("#### Tracked Stocks & Alert Preferences")
            if watchlist_items:
                for w in watchlist_items:
                    with st.container(border=True):
                        row_c1, row_c2, row_c3 = st.columns([3, 2, 2])
                        with row_c1:
                            st.markdown(f"**{w['ticker']}** — {w['short_name']}")
                            p_str = f"₹{w['last_scanned_price']:,.2f}" if w.get('last_scanned_price') else "Not Scanned"
                            st.caption(f"Last Price: {p_str} | Scanned: {w['last_scanned_at']}")
                        with row_c2:
                            badges = []
                            if w["alert_material"]: badges.append("📢 Material")
                            if w["alert_fundamental"]: badges.append("📊 Fundamental")
                            if w["alert_valuation"]: badges.append("⚡ Valuation")
                            st.markdown(" ".join([f"`{b}`" for b in badges]))
                            st.caption(f"Mode: `{w['digest_mode'].title()}`")
                        with row_c3:
                            btn_w1, btn_w2 = st.columns(2)
                            with btn_w1:
                                if st.button(
                                    "Research",
                                    key=f"res_watch_{w['ticker']}",
                                    width="stretch",
                                    help=f"Open full 7-pillar institutional equity research dossier & technical chart for {w['ticker']}"
                                ):
                                    rec = get_report_by_ticker(w["ticker"])
                                    if rec:
                                        set_active_dossier_state(
                                            ticker=w["ticker"],
                                            report_text=rec.get("report_text"),
                                            report_date=rec.get("formatted_date"),
                                            fundamentals={
                                                "short_name": w.get("short_name", w["ticker"]),
                                                "ticker": w["ticker"],
                                                "market_cap": rec.get("baseline_mcap", "Archived"),
                                                "pe_ratio": rec.get("baseline_pe", "N/A"),
                                                "sector": "General Industry",
                                                "current_price": rec.get("baseline_price", "N/A")
                                            },
                                            material_reason="👁️ Loaded from Surveillance Watchlist"
                                        )
                                    else:
                                        execute_stock_research(w["ticker"])
                                    st.session_state["scroll_to_dossier"] = True
                                    st.session_state["collapse_alert_hub"] = True
                                    st.session_state["toast_message"] = f"📄 Loaded dossier for {w['ticker']}!"
                                    st.rerun(scope="app")
                            with btn_w2:
                                if st.button("Remove", key=f"rm_watch_{w['ticker']}", width="stretch"):
                                    remove_from_watchlist(w["ticker"])
                                    st.rerun()
            else:
                st.info("Your surveillance watchlist is empty. Add stocks below or directly from any equity research report.")

            # Comprehensive Notification & Push Preferences Card (Opt-in & Opt-out)
            with st.container(border=True):
                st.markdown("#### 🔔 Notification & Push Preferences")

                is_opted_out = st.session_state.get("notifications_opted_out", False)
                notif_c1, notif_c2 = st.columns([3, 1])
                with notif_c1:
                    if is_opted_out:
                        st.markdown("🔕 **Surveillance Alerts: OPTED OUT (Muted)**")
                        st.caption("All event notifications and unread badge alerts are silenced. Market data is still polled.")
                    else:
                        st.markdown("🔔 **Surveillance Alerts: ACTIVE (Opted In)**")
                        st.caption("Receiving event alerts for public BSE corporate filings, fundamental shifts, and valuation shocks.")
                with notif_c2:
                    if is_opted_out:
                        if st.button("🔔 Re-Enable Alerts", key="btn_enable_global_notifs", width="stretch", type="primary"):
                            st.session_state["notifications_opted_out"] = False
                            st.toast("Surveillance alerts re-enabled.", icon="🔔")
                            st.rerun()
                    else:
                        if st.button("🔕 Opt Out of Alerts", key="btn_opt_out_global_notifs", width="stretch"):
                            st.session_state["notifications_opted_out"] = True
                            st.toast("You have opted out of surveillance alerts.", icon="🔕")
                            st.rerun()

                st.markdown("---")
                push_c1, push_c2 = st.columns([3, 2])
                with push_c1:
                    st.markdown("📲 **Device Desktop Push Notifications (Zero-PII)**")
                    st.caption("Receive background OS push alerts for BSE disclosures directly on your device.")
                with push_c2:
                    p_btn1, p_btn2 = st.columns(2)
                    with p_btn1:
                        if st.button("Enable Push", key="btn_enable_web_push", width="stretch", help="Request browser permission for background OS push notifications"):
                            st.session_state["web_push_requested"] = True
                    with p_btn2:
                        if st.button("Disable Push", key="btn_disable_web_push", width="stretch", help="Opt out and disable device push notifications"):
                            st.session_state["web_push_disabled"] = True
                            st.toast("Push notifications disabled.", icon="🔕")
                            st.rerun()

            if st.session_state.get("web_push_requested"):
                st.session_state["web_push_requested"] = False
                st.html(
                    """
                    <script>
                    if (!("Notification" in window)) {
                        alert("This browser does not support desktop notifications.");
                    } else if (Notification.permission === "granted") {
                        new Notification("🔔 Surveillance Alerts Active", {
                            body: "You will receive real-time BSE filings and price shock notifications for watchlisted companies!",
                            icon: "https://raw.githubusercontent.com/feathericons/feather/master/icons/bell.svg"
                        });
                    } else if (Notification.permission !== "denied") {
                        Notification.requestPermission().then(function (permission) {
                            if (permission === "granted") {
                                new Notification("🔔 Surveillance Alerts Active", {
                                    body: "Push alerts successfully enabled for your surveillance watchlist!",
                                    icon: "https://raw.githubusercontent.com/feathericons/feather/master/icons/bell.svg"
                                });
                            }
                        });
                    }
                    </script>
                    """
                )
                st.success("✓ Browser notification request triggered. Click 'Allow' in your browser prompt.")

            if st.session_state.get("web_push_disabled"):
                st.session_state["web_push_disabled"] = False
                st.info("🔕 Device push notifications have been disabled. You have opted out of browser alerts.")

            st.markdown("---")
            st.markdown("#### Add Stock to Surveillance Watchlist")
            with st.form("add_watchlist_form", clear_on_submit=True):
                w_ticker_input = st.text_input(
                    "Stock Ticker or BSE Scrip Code:",
                    placeholder="Type ticker or 6-digit scrip code (e.g., INFY, TCS, 500209)...",
                    help="Enter an official BSE scrip code (e.g. 500209) or exchange ticker symbol (e.g. INFY, TCS, RELIANCE)."
                )
                st.caption("💡 *Example inputs: `INFY` (Infosys), `TCS` (Tata Consultancy Services), or `500209` (BSE Scrip Code). Field is blank by default.*")
                pref_c1, pref_c2, pref_c3 = st.columns(3)
                with pref_c1:
                    pref_mat = st.checkbox("Material Filings 📢", value=True)
                with pref_c2:
                    pref_fund = st.checkbox("Fundamental Shifts 📊", value=True)
                with pref_c3:
                    pref_val = st.checkbox("Valuation Shock (±5%) ⚡", value=True)

                digest_choice = st.radio("Notification Frequency:", ["Instant Notifications", "Daily Digest"], horizontal=True)
                also_research = st.checkbox("Also generate complete research dossier now", value=False)
                add_sub = st.form_submit_button("Add to Watchlist", type="primary")

                if add_sub and w_ticker_input:
                    clean_t = sanitize_ticker_input(w_ticker_input).upper()
                    scrip = resolve_bse_scrip_code(clean_t)
                    added = add_to_watchlist(
                        ticker=clean_t,
                        short_name=clean_t,
                        scrip_code=scrip or "",
                        alert_material=pref_mat,
                        alert_fundamental=pref_fund,
                        alert_valuation=pref_val,
                        digest_mode="instant" if "Instant" in digest_choice else "digest"
                    )
                    if added:
                        st.success(f"✓ Added **{clean_t}** to surveillance watchlist.")
                        if also_research:
                            execute_stock_research(clean_t)
                        else:
                            st.rerun()
                    else:
                        st.error("Failed to add stock to watchlist.")

        with tab_scan:
            st.markdown("#### On-Demand Regulatory & Exchange Sweep")
            st.caption("Polls official BSE Corporate Disclosures, board meeting intimations, and live exchange quotes for all watchlisted companies.")

            if st.session_state.get("notifications_opted_out", False):
                st.info("🔕 **Surveillance Alerts Muted:** You are opted out of notifications. Sweeps update live quotes and disclosure archives without generating new alert events.")

            try:
                w_list = get_watchlist()
            except Exception:
                w_list = []

            st.info(f"Currently tracking **{len(w_list)} stock{'s' if len(w_list) != 1 else ''}** on watchlist.")

            if st.button("⚡ Run Surveillance Sweep Now", type="primary", disabled=(len(w_list) == 0)):
                with st.status("Executing BSE regulatory filings & price surveillance sweep...", expanded=True) as scan_status:
                    progress_bar = st.progress(0.0)

                    def on_scan_progress(curr, total, ticker_scanned):
                        progress_bar.progress(curr / total)
                        st.write(f"• Auditing BSE filings & quotes for **{ticker_scanned}** ({curr}/{total})...")

                    results = run_surveillance_scan(progress_callback=on_scan_progress)
                    progress_bar.progress(1.0)

                    new_c = results.get("new_alerts_count", 0)
                    if new_c > 0:
                        scan_status.update(label=f"✅ Sweep complete: {new_c} new alert{'s' if new_c != 1 else ''} generated!", state="complete")
                    else:
                        scan_status.update(label="✅ Sweep complete: All watchlisted companies verified (No new alerts).", state="complete")

                st.rerun()
