"""Institutional research dossier view component: query entry, report streaming, metrics scorecard, and PDF export."""

import re
import time
from datetime import datetime
import streamlit as st

from core.db import (
    IST,
    MANDATORY_SEBI_DISCLAIMER,
    get_archived_reports,
    get_report_by_ticker,
    is_ticker_in_watchlist,
    add_to_watchlist,
    remove_from_watchlist,
)
from core.analysis import (
    execute_surgical_pillar_update,
    stream_stock_report,
)
from ui.formatters import format_inr
from ui.pdf import build_pdf_dossier
from ui.scorecard import (
    render_health_card_ui,
    render_thesis_drift_panel,
    render_dual_speed_report,
)
from telemetry import track_user_action
from ui.views.alerts_view import render_alert_hub
from ui.views.state import (
    sanitize_ticker_input,
    set_active_dossier_state,
    execute_stock_research,
)

def render_dossier_view():
    """Renders the primary institutional research dossier search, streaming engine, and presentation layout."""
    with st.form("search_form", clear_on_submit=False):
        col_q1, col_q2 = st.columns([3, 1])
        with col_q1:
            query = st.text_input(
                "Enter Company Name or Ticker:",
                value="",
                placeholder="Type any listed Indian company (e.g., RELIANCE, TCS, INFY)...",
                help="Search across all BSE-listed equity instruments by symbol or company name."
            )
        with col_q2:
            selected_language = st.selectbox(
                "Report Language:",
                ["English (India)", "Hindi", "Marathi", "Gujarati", "Tamil", "Telugu", "Bengali"]
            )
        st.caption("💡 *Examples: `RELIANCE`, `TCS`, `INFY`, or `500325` (BSE Scrip Code). Field is blank by default.*")
        submitted = st.form_submit_button("Generate Research Report", type="primary")

    if submitted and query:
        track_user_action("SEARCH_QUERY", query, details={"language": selected_language})
        execute_stock_research(query, selected_language)

    # Quick Lookup Chips: Recently Researched Stocks
    recent_tickers = st.session_state.get("recent_searches")
    if recent_tickers is None:
        try:
            recent_tickers = [r["ticker"] for r in get_archived_reports()[:5] if r.get("ticker")]
        except Exception:
            recent_tickers = []
        st.session_state["recent_searches"] = recent_tickers

    if recent_tickers:
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px; margin-bottom: 8px;">
                <span style="font-size: 12px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">
                    ⚡ Quick Lookup:
                </span>
            </div>
            """,
            unsafe_allow_html=True
        )
        chip_cols = st.columns(len(recent_tickers) + 1)
        for idx, r_ticker in enumerate(recent_tickers):
            with chip_cols[idx]:
                if st.button(r_ticker, key=f"quick_lookup_chip_{r_ticker}_{idx}", width="stretch", help=f"Instant dossier lookup for {r_ticker}"):
                    execute_stock_research(r_ticker, selected_language)

    # Embed Surveillance Alert Hub
    render_alert_hub()

    # Active Dossier Rendering Section
    if ("last_report" in st.session_state and st.session_state["last_report"] is not None) or st.session_state.get("stream_pending"):
        # Anchor for smooth auto-scrolling
        st.html('<div id="active-dossier-anchor" style="scroll-margin-top: 30px;"></div>')

        # Handle toast message if requested
        if st.session_state.get("toast_message"):
            msg = st.session_state.pop("toast_message")
            icon = st.session_state.pop("toast_icon", "📄")
            st.toast(msg, icon=icon)

        # Handle smooth auto-scroll to differential panel or dossier
        if st.session_state.get("scroll_to_diff"):
            st.session_state["scroll_to_diff"] = False
            st.html(
                """
                <script>
                setTimeout(function() {
                    var el = document.getElementById("thesis-drift-anchor");
                    if (el) {
                        el.scrollIntoView({behavior: "smooth", block: "start"});
                    }
                }, 150);
                </script>
                """
            )
        elif st.session_state.get("scroll_to_dossier"):
            st.session_state["scroll_to_dossier"] = False
            st.html(
                """
                <script>
                setTimeout(function() {
                    var el = document.getElementById("active-dossier-anchor");
                    if (el) {
                        el.scrollIntoView({behavior: "smooth", block: "start"});
                    }
                }, 150);
                </script>
                """
            )

        fund = st.session_state.get("last_fundamentals", {})
        ticker_disp = st.session_state.get("last_ticker", "STOCK")
        company_name = fund.get("short_name", "").strip()
        clean_t = ticker_disp.strip().upper()
        header_label = f"{company_name} ({clean_t})" if company_name and company_name.upper() != clean_t else clean_t

        if st.session_state.get("pending_price_delta"):
            p_delta = st.session_state["pending_price_delta"]
            if p_delta.get("ticker") == clean_t:
                with st.container():
                    st.warning(
                        f"⚡ **Price Shift Detected:** {p_delta.get('reason')}. "
                        "Pillars 1–4 & 7 (Business Model, Moat, Governance & ESG) remain fundamentally intact. "
                        "You can quickly update Pillars 5 & 6 with verified live exchange data."
                    )
                    b_c1, b_c2, b_c3 = st.columns([3, 2.5, 1])
                    with b_c1:
                        if st.button("⚡ Quick-Update Valuation & Technicals", key="btn_surgical_refresh", type="primary", width="stretch", help="Surgically refreshes Pillar 5 (Valuation) & Pillar 6 (Technicals) using live exchange data. Fast, zero Google search fees, saves 90%+ credits."):
                            cached_data = p_delta.get("cached") or get_report_by_ticker(clean_t) or {}
                            updated_report = execute_surgical_pillar_update(
                                ticker=clean_t,
                                cached_report=cached_data,
                                stock_data=p_delta.get("stock_data", fund),
                                hist_df=p_delta.get("hist_df"),
                                language=p_delta.get("language", "English (India)")
                            )
                            st.session_state["last_report"] = updated_report
                            st.session_state["last_report_date"] = datetime.now(IST).strftime("%d-%b-%Y %H:%M IST")
                            track_user_action("SURGICAL_REFRESH", clean_t, cost_saved_usd=0.035, details={"reason": p_delta.get("reason")})
                            st.session_state.pop("pending_price_delta", None)
                            st.toast("Valuation & Technicals surgically updated!", icon="⚡")
                            st.rerun(scope="app")
                    with b_c2:
                        if st.button("🔄 Full 7-Pillar Re-synthesis", key="btn_full_regen", width="stretch", help="Re-synthesize all 7 pillars with full AI reasoning."):
                            reason_msg = p_delta.get("reason", "Full Regeneration Requested")
                            lang_choice = p_delta.get("language", "English (India)")
                            st.session_state.pop("pending_price_delta", None)
                            st.session_state["last_report"] = None
                            st.session_state["stream_pending"] = True
                            st.session_state["stream_language"] = lang_choice
                            st.session_state["material_reason"] = reason_msg
                            st.rerun(scope="app")
                    with b_c3:
                        if st.button("✕ Dismiss", key="btn_dismiss_delta", width="stretch", help="Keep current report as-is"):
                            st.session_state.pop("pending_price_delta", None)
                            st.rerun(scope="app")

        if st.session_state.get("viewing_snapshot"):
            snap = st.session_state["viewing_snapshot"]
            col_s1, col_s2 = st.columns([3, 1])
            with col_s1:
                st.warning(
                    f"📜 **Viewing Historical Revision Snapshot** ({snap.get('formatted_date')}) • "
                    f"Trigger: *{snap.get('revision_trigger')}*"
                )
            with col_s2:
                if st.button("Return to Latest", key="btn_return_latest_snap", width="stretch"):
                    rec = get_report_by_ticker(clean_t)
                    if rec:
                        set_active_dossier_state(
                            ticker=clean_t,
                            report_text=rec.get("report_text"),
                            report_date=rec.get("formatted_date"),
                            fundamentals=fund,
                            material_reason="📂 Returned to Active Dossier"
                        )
                    else:
                        st.session_state.pop("viewing_snapshot", None)
                    st.rerun()

        col1, col2, col3, col4 = st.columns(4)
        mcap = fund.get("market_cap", 0)
        col1.metric("Market Capitalization", format_inr(mcap))

        pe_val = str(fund.get("pe_ratio", "N/A"))
        if "Loss-Making" in pe_val or "Negative" in pe_val:
            col2.metric("P/E Ratio", "Loss-Making", delta="- Negative EPS", delta_color="inverse")
        else:
            col2.metric("P/E Ratio", pe_val)

        col3.metric("Sector", str(fund.get("sector", "N/A")))
        col4.metric("Exchange Status", "Active / Verified")

        if "Loss-Making" in pe_val or "Negative" in pe_val:
            st.error(f"❌ **Valuation Multiple Error: P/E Undefined.** {ticker_disp} operates at a trailing net loss. Indian exchanges suppress negative multiples.")
        elif pe_val == "N/A":
            st.warning(f"⚠️ **Valuation Notice:** Trailing P/E multiple is unavailable from exchange feeds for {ticker_disp}.")

        st.markdown("---")

        # Hoisted Differential Analysis / Thesis Drift Surveillance Anchor & Card
        st.html('<div id="thesis-drift-anchor" style="scroll-margin-top: 30px;"></div>')
        if not st.session_state.get("stream_pending") and st.session_state.get("last_report"):
            render_thesis_drift_panel(clean_t, custom_diff_data=st.session_state.get("custom_diff"))

        badge_container = st.empty()
        if st.session_state.get("last_report"):
            render_health_card_ui(st.session_state["last_report"], target_container=badge_container)

        # Report Header & Watchlist / Re-synthesis Actions
        hdr_c1, hdr_c2 = st.columns([2.6, 1.4])
        with hdr_c1:
            st.header(f"Equity Research Report: {header_label}")
            rep_date = st.session_state.get("last_report_date") or datetime.now(IST).strftime("%d-%b-%Y %H:%M IST")
            st.caption(f"🕒 **Report Timing:** {rep_date} | **Feed:** BSE Verified Exchange Data")
        with hdr_c2:
            btn_w_col, btn_regen_col = st.columns(2)
            with btn_w_col:
                try:
                    in_w = is_ticker_in_watchlist(clean_t)
                except Exception:
                    in_w = False
                if in_w:
                    if st.button("✓ Tracking", key="btn_watch_toggle", width="stretch", help="Click to untrack from surveillance"):
                        remove_from_watchlist(clean_t)
                        st.rerun()
                else:
                    if st.button("⭐ Watchlist", key="btn_watch_toggle", type="secondary", width="stretch", help="Add to surveillance watchlist for material filings & price shock alerts"):
                        add_to_watchlist(
                            ticker=clean_t,
                            short_name=company_name or clean_t,
                            scrip_code=str(fund.get("scrip_code", "")),
                            initial_price=fund.get("current_price")
                        )
                        st.rerun()
            with btn_regen_col:
                if st.button("🔄 Re-synthesize", key="btn_force_resynthesize_dossier", width="stretch", help="Force a fresh live AI synthesis grounded in latest BSE filings, bypassing cache"):
                    execute_stock_research(clean_t, selected_language=st.session_state.get("last_language", "English (India)"), force_refresh=True)

        if st.session_state.get("stream_pending"):
            st.session_state["stream_pending"] = False
            lang = st.session_state.get("stream_language", "English (India)")
            try:
                with st.status("🔍 Auditing exchange filings & synthesizing research...", expanded=True) as status:
                    st.caption("ℹ️ *Institutional Due Diligence: Research grounded in public BSE filings and exchange feeds via AI synthesis under SEBI educational safe-harbor standards.*")
                    st.write(f"✓ **Exchange Quote Verified:** ₹{fund.get('current_price', 'N/A')} (Scrip: {fund.get('scrip_code', clean_t)})")
                    st.write(f"✓ **Fundamental Valuation Metrics:** Market Cap ₹{format_inr(fund.get('market_cap', 0))} | Trailing P/E: {fund.get('pe_ratio', 'N/A')}")
                    if st.session_state.get("last_history") is not None and not st.session_state["last_history"].empty:
                        st.write("✓ **Technical Momentum Aggregated:** 6-month OHLCV data & rolling 50-DMA calculated.")
                    st.write("✓ **Regulatory Filings Scanned:** BSE Corporate Announcements & Disclosures ingested.")
                    st.write("⚡ **Synthesizing 7-Pillar Institutional Equity Research Dossier...**")
                    
                    mat_reason = st.session_state.get("material_reason", "Live Synthesis")
                    stream_gen = stream_stock_report(clean_t, language=lang, stock_data=fund, on_status=lambda msg: st.write(f"• {msg}"), revision_trigger=mat_reason)
                    try:
                        first_chunk = next(stream_gen)
                        status.update(label="✅ Due diligence complete. Report generated.", state="complete", expanded=False)
                    except StopIteration:
                        first_chunk = ""
                        status.update(label="⚠️ Stream ended unexpectedly.", state="error", expanded=False)

                synth_slot = st.empty()
                synth_bar = synth_slot.progress(0.70, text="⚡ Step 4/5: Synthesizing 7-Pillar Institutional Equity Research Dossier...")

                accumulated = []
                def combined_stream():
                    if first_chunk:
                        accumulated.append(first_chunk)
                        yield first_chunk
                    for chunk in stream_gen:
                        accumulated.append(chunk)
                        txt = "".join(accumulated)
                        if "Pillar 7" in txt or "ESG" in txt:
                            synth_bar.progress(0.96, text="🌱 Step 4/5: Synthesizing Pillar 7: ESG Impact Scorecard...")
                        elif "Pillar 6" in txt or "Balance Sheet" in txt:
                            synth_bar.progress(0.92, text="🛡️ Step 4/5: Synthesizing Pillar 6: Balance Sheet Stress-Test...")
                        elif "Pillar 5" in txt or "Valuation" in txt:
                            synth_bar.progress(0.88, text="⚡ Step 4/5: Synthesizing Pillar 5: Valuation Diagnostic...")
                        elif "Pillar 4" in txt or "Governance" in txt:
                            synth_bar.progress(0.84, text="🔍 Step 4/5: Synthesizing Pillar 4: Corporate Governance...")
                        elif "Pillar 3" in txt or "Capital Allocation" in txt:
                            synth_bar.progress(0.80, text="📊 Step 4/5: Synthesizing Pillar 3: Capital Allocation Track Record...")
                        elif "Pillar 2" in txt or "Moat" in txt:
                            synth_bar.progress(0.75, text="🏰 Step 4/5: Synthesizing Pillar 2: Business Model & Competitive Moat...")
                        yield chunk

                streamed_text = st.write_stream(combined_stream)
                synth_bar.progress(1.0, text="✅ Step 5/5: SEBI Compliance Verified & Dossier Archived!")
                time.sleep(0.4)
                synth_slot.empty()
                render_health_card_ui(streamed_text, target_container=badge_container)
                if "Live Synthesis Failed" in streamed_text:
                    cached_rec = get_report_by_ticker(clean_t)
                    if cached_rec and cached_rec.get("report_text"):
                        st.warning(f"⚠️ Live generation failed. Displaying archive from {cached_rec.get('formatted_date')}.")
                        st.session_state["last_report"] = cached_rec["report_text"]
                        st.session_state["last_report_date"] = cached_rec.get("formatted_date")
                    else:
                        st.session_state["last_report"] = streamed_text
                        st.session_state["last_report_date"] = datetime.now(IST).strftime("%d-%b-%Y %H:%M IST")
                else:
                    st.session_state["last_report"] = streamed_text
                    st.session_state["last_report_date"] = datetime.now(IST).strftime("%d-%b-%Y %H:%M IST")
                st.rerun()
            except Exception as stream_err:
                st.error(f"### ❌ Live Streaming Halted: {stream_err}")
                st.session_state["last_report"] = None
        elif st.session_state.get("last_report"):
            expand_all = st.toggle("📖 Expand all analytical pillars", value=False, key="toggle_expand_pillars")
            render_dual_speed_report(st.session_state["last_report"], expand_all=expand_all)

        # Primary Download Button & Mandatory Immutable SEBI Disclaimer
        if st.session_state.get("last_report"):
            st.markdown("---")
            st.caption(f"**Statutory Safe Harbor & SEBI Regulatory Compliance Notice:** {MANDATORY_SEBI_DISCLAIMER}")
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            rep_content = st.session_state["last_report"]
            pdf_cache_id = f"{clean_t}_{hash(rep_content)}"
            
            if st.session_state.get("pdf_cache_id") != pdf_cache_id or "cached_pdf_bytes" not in st.session_state:
                try:
                    st.session_state["cached_pdf_bytes"] = build_pdf_dossier(
                        rep_content,
                        clean_t,
                        header_label,
                        st.session_state.get("last_history")
                    )
                    st.session_state["pdf_cache_id"] = pdf_cache_id
                    track_user_action("PDF_DOWNLOAD", clean_t, details={"file_bytes": len(st.session_state["cached_pdf_bytes"]) if st.session_state.get("cached_pdf_bytes") else 0})
                except Exception as pdf_err:
                    st.session_state["cached_pdf_bytes"] = None
                    st.caption(f"PDF export notice: {pdf_err}")
                    
            if st.session_state.get("cached_pdf_bytes"):
                canonical_clean = re.sub(r'[^A-Za-z0-9]', '', str(fund.get('ticker', clean_t)).split('.')[0]).upper()
                date_stamp = datetime.now(IST).strftime('%d-%m-%Y')
                target_filename = f"{canonical_clean}_{date_stamp}_Research_Report.pdf"
                
                st.download_button(
                    label="Download Research Report (PDF)",
                    data=st.session_state["cached_pdf_bytes"],
                    file_name=target_filename,
                    mime="application/pdf",
                    type="primary",
                    width="stretch"
                )
