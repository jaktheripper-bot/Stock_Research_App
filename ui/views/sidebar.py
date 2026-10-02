"""Sidebar component: stock discovery search, archive picker, and revision timeline."""

import streamlit as st
from core.db import get_archived_reports, get_report_by_ticker, get_report_revisions
from core.analysis import compare_revisions
from ui.formatters import format_inr
from telemetry import track_user_action
from ui.views.state import execute_stock_research, set_active_dossier_state
from ui.auth_ui import render_auth_sidebar_chip

def render_sidebar():
    """Renders the persistent sidebar with search, archived dossier picker, and revision history."""
    with st.sidebar:
        render_auth_sidebar_chip()
        st.markdown("---")
        st.header("Stock Discovery")
        with st.form("sidebar_stock_search", clear_on_submit=False):
            sb_query = st.text_input(
                "Look up any stock:",
                placeholder="e.g. INFY, TCS, RELIANCE...",
                help="Search across all BSE-listed equity instruments by ticker or company name."
            )
            sb_submit = st.form_submit_button("Search Stock", type="primary", width="stretch")
        if sb_submit and sb_query:
            track_user_action("SEARCH_QUERY", sb_query)
            execute_stock_research(sb_query)

        st.markdown("---")
        st.header("Research Archive & Surveillance")
        try:
            archives = get_archived_reports()
            if archives:
                # Format ticker labels with company name and revision counts
                ticker_options = ["Select..."]
                archive_map = {}
                for a in archives:
                    t = a.get("ticker", "Unknown")
                    name = a.get("short_name", t)
                    rev_c = a.get("revision_count", 0)
                    rev_str = f" • {rev_c} rev{'s' if rev_c != 1 else ''}" if rev_c > 0 else ""
                    label = f"{t} ({name}){rev_str}" if name and name.upper() != t.upper() else f"{t}{rev_str}"
                    ticker_options.append(label)
                    archive_map[label] = a

                # Determine currently selected index or active option
                active_ticker = st.session_state.get("last_ticker", "").strip().upper()
                active_label = None
                if active_ticker:
                    for opt in ticker_options:
                        if opt != "Select..." and archive_map[opt].get("ticker") == active_ticker:
                            active_label = opt
                            break

                # Smart synchronization: sync dropdown if active_ticker changed externally
                if "sb_archive_picker" not in st.session_state:
                    st.session_state["sb_archive_picker"] = active_label if active_label else "Select..."
                    st.session_state["sb_archive_sync_ticker"] = active_ticker
                elif active_label and st.session_state.get("sb_archive_sync_ticker") != active_ticker:
                    st.session_state["sb_archive_picker"] = active_label
                    st.session_state["sb_archive_sync_ticker"] = active_ticker

                if st.session_state.get("sb_archive_picker") not in ticker_options:
                    st.session_state["sb_archive_picker"] = "Select..."

                selected_label = st.selectbox(
                    "Select stock archive:",
                    options=ticker_options,
                    key="sb_archive_picker"
                )
                if selected_label != "Select...":
                    selected_item = archive_map[selected_label]
                    selected_ticker = selected_item.get("ticker")
                    is_active = (st.session_state.get("last_ticker") == selected_ticker) and (not st.session_state.get("viewing_snapshot"))

                    # Load Latest button
                    if st.button(
                        "✓ Active Report Loaded" if is_active else "Load Active Dossier",
                        type="secondary" if is_active else "primary",
                        disabled=is_active,
                        width="stretch"
                    ):
                        track_user_action("ARCHIVE_LOAD", selected_ticker)
                        rep_text = selected_item.get("report_text")
                        if not rep_text:
                            full_rec = get_report_by_ticker(selected_ticker)
                            rep_text = full_rec.get("report_text") if full_rec else ""
                        set_active_dossier_state(
                            ticker=selected_ticker,
                            report_text=rep_text,
                            report_date=selected_item.get("formatted_date"),
                            fundamentals={
                                "short_name": selected_item.get("short_name", selected_ticker),
                                "ticker": selected_ticker,
                                "market_cap": selected_item.get("baseline_mcap", "Archived"),
                                "pe_ratio": selected_item.get("baseline_pe", "N/A"),
                                "sector": "General Industry",
                                "current_price": selected_item.get("baseline_price", "N/A")
                            },
                            material_reason="📂 Loaded from Archived Research Dossier"
                        )
                        st.rerun()

                    st.markdown("---")
                    st.subheader("📜 Revision History & Provenance")

                    revisions = get_report_revisions(selected_ticker)
                    if not revisions:
                        st.info("No revision snapshots recorded yet.")
                    else:
                        st.caption(f"_{len(revisions)} immutable snapshot{'s' if len(revisions) != 1 else ''} archived (IST)_")

                        # Arbitrary Multi-Quarter Comparator (State A vs State B)
                        if len(revisions) >= 2:
                            with st.expander("⚖️ Compare Any 2 Revisions", expanded=False):
                                st.caption("Select discrete historical states to evaluate multi-quarter thesis drift:")
                                rev_choices = [
                                    f"Rev #{len(revisions) - i} ({r['formatted_date'][:11]} - {r['revision_trigger'][:16]})"
                                    for i, r in enumerate(revisions)
                                ]
                                def_a = min(1, len(revisions) - 1)
                                sel_b_lbl = st.selectbox("State B (Newer State):", rev_choices, index=0, key="sb_b_state")
                                sel_a_lbl = st.selectbox("State A (Baseline State):", rev_choices, index=def_a, key="sb_a_state")

                                idx_b = rev_choices.index(sel_b_lbl)
                                idx_a = rev_choices.index(sel_a_lbl)

                                if st.button("Run Differential Analysis", key="btn_run_sb_diff", width="stretch"):
                                    r_b = revisions[idx_b]
                                    r_a = revisions[idx_a]
                                    c_diff = compare_revisions(r_a, r_b)
                                    set_active_dossier_state(
                                        ticker=selected_ticker,
                                        report_text=r_b.get("report_text"),
                                        report_date=r_b.get("formatted_date"),
                                        fundamentals={
                                            "short_name": r_b.get("short_name", selected_ticker),
                                            "ticker": selected_ticker,
                                            "market_cap": r_b.get("baseline_mcap", "Archived"),
                                            "pe_ratio": r_b.get("baseline_pe", "N/A"),
                                            "sector": "General Industry",
                                            "current_price": r_b.get("baseline_price", "N/A")
                                        },
                                        material_reason=f"⚖️ Multi-Quarter Differential ({sel_a_lbl} vs {sel_b_lbl})",
                                        custom_diff={
                                            "diff": c_diff,
                                            "label_a": sel_a_lbl,
                                            "label_b": sel_b_lbl,
                                            "rev_a": r_a,
                                            "rev_b": r_b,
                                        }
                                    )
                                    st.session_state["toast_message"] = f"⚖️ Differential comparison active: {sel_a_lbl} vs {sel_b_lbl}"
                                    st.session_state["toast_icon"] = "📊"
                                    st.session_state["scroll_to_diff"] = True
                                    st.rerun()
                        elif len(revisions) == 1:
                            st.caption("ℹ️ _Revision diffing activates upon the next quarterly filing or material price shift._")
                            with st.expander("⚖️ Compare Any 2 Revisions", expanded=False):
                                st.info(
                                    "ℹ️ **Single Baseline Snapshot Archived:** Differential analysis and thesis drift tracking "
                                    "activate automatically upon subsequent quarterly earnings filings or material price shifts (≥5%)."
                                )

                        # Chronological Timeline Cards
                        st.markdown("**Timeline of Revisions**")
                        for idx, rev in enumerate(revisions):
                            rev_num = len(revisions) - idx
                            trigger = rev.get("revision_trigger", "Initial")
                            t_lower = trigger.lower()

                            if "price" in t_lower or "%" in t_lower:
                                b_bg, b_border, b_icon = "rgba(245, 158, 11, 0.15)", "#f59e0b", "⚡"
                            elif "announcement" in t_lower or "filing" in t_lower or "bse" in t_lower:
                                b_bg, b_border, b_icon = "rgba(59, 130, 246, 0.15)", "#3b82f6", "📢"
                            elif "14" in t_lower or "periodic" in t_lower or "routine" in t_lower or "expired" in t_lower:
                                b_bg, b_border, b_icon = "rgba(168, 85, 247, 0.15)", "#a855f7", "🕒"
                            elif "baseline" in t_lower or "initial" in t_lower:
                                b_bg, b_border, b_icon = "rgba(16, 185, 129, 0.15)", "#10b981", "🌱"
                            else:
                                b_bg, b_border, b_icon = "rgba(148, 163, 184, 0.15)", "#64748b", "🔍"

                            is_cur_viewing = (
                                st.session_state.get("viewing_snapshot", {}).get("id") == rev.get("id")
                                or (idx == 0 and not st.session_state.get("viewing_snapshot") and st.session_state.get("last_ticker") == selected_ticker)
                            )

                            with st.container(border=True):
                                st.markdown(
                                    f"""
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                                        <span style="font-weight: 700; font-size: 13px;">Rev #{rev_num}</span>
                                        <span style="font-size: 11px; color: #94a3b8;">{rev['formatted_date']}</span>
                                    </div>
                                    <div style="display: inline-block; background-color: {b_bg}; border: 1px solid {b_border};
                                                border-radius: 4px; padding: 2px 7px; font-size: 11px; margin-bottom: 4px; font-weight: 600;">
                                        {b_icon} {trigger}
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                                p = rev.get("baseline_price")
                                pe = rev.get("baseline_pe", "N/A")
                                mc = rev.get("baseline_mcap")
                                p_str = f"₹{p:,.1f}" if p else "N/A"
                                mc_str = format_inr(mc) if mc else "N/A"
                                st.caption(f"**P:** {p_str} | **P/E:** {pe} | **MCap:** {mc_str}")

                                if st.button(
                                    "✓ Currently Viewing" if is_cur_viewing else "View Snapshot",
                                    key=f"btn_view_rev_{rev.get('id')}",
                                    disabled=is_cur_viewing,
                                    width="stretch"
                                ):
                                    set_active_dossier_state(
                                        ticker=selected_ticker,
                                        report_text=rev.get("report_text"),
                                        report_date=rev.get("formatted_date"),
                                        fundamentals={
                                            "short_name": rev.get("short_name", selected_ticker),
                                            "ticker": selected_ticker,
                                            "market_cap": rev.get("baseline_mcap", "Archived"),
                                            "pe_ratio": rev.get("baseline_pe", "N/A"),
                                            "sector": "General Industry",
                                            "current_price": rev.get("baseline_price", "N/A")
                                        },
                                        material_reason=f"📜 Viewing Immutable Revision #{rev_num} ({rev.get('revision_trigger')})",
                                        viewing_snapshot=rev
                                    )
                                    st.rerun()
            else:
                st.info("No archives found.")
        except Exception as err:
            st.caption(f"Archive history unavailable: {err}")
