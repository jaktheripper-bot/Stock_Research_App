import json
import traceback
import platform
import tempfile
from datetime import datetime, timezone
import streamlit as st
from analyzer import (
    remove_health_matrix_text,
    extract_health_matrix, stream_stock_report, 
    get_stock_fundamentals, evaluate_material_change
)
from db import get_archived_reports, get_report_by_ticker
from markdown_pdf import MarkdownPdf, Section

st.set_page_config(page_title="Equity Research AI", layout="centered", page_icon="📈")
# Typography Styling (Zero Layout/Container Overrides)

# Unified Responsive Typography & Layout Constraints

# Responsive Typography & Column Wrapping

# Streamlit 1.63 Responsive Viewport & Flex Constraints

# Responsive Typography & Container Constraints

def format_inr(number):
    if number is None or str(number).strip() in ["", "0", "N/A"]:
        return "N/A"
    try:
        clean_num = str(number).replace(",", "").strip()
        number = float(clean_num)
    except (ValueError, TypeError):
        return str(number)

    def group_inr(val):
        parts = f"{val:.2f}".split(".")
        int_p = parts[0]
        dec_p = parts[1]
        if len(int_p) <= 3:
            return f"{int_p}.{dec_p}"
        last_three = int_p[-3:]
        remaining = int_p[:-3]
        groups = []
        while remaining:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        groups.reverse()
        return f"{','.join(groups)},{last_three}.{dec_p}"

    if number >= 1e7:
        return f"₹{group_inr(number / 1e7)} Cr"
    elif number >= 1e5:
        return f"₹{group_inr(number / 1e5)} Lakh"
    return f"₹{group_inr(number)}"

def render_health_card_ui(report_text: str, target_container=None):
    matrix = extract_health_matrix(report_text)
    if not matrix:
        return

    color_map = {
        "Disciplined": "#1b5e20", "Buy": "#1b5e20", "Wide": "#1b5e20", "Clean": "#1b5e20",
        "Debt-Free": "#1b5e20", "Undervalued": "#1b5e20", "Temporary": "#1b5e20", "Stable": "#1b5e20",
        "Watchlist": "#b26a00", "Moderate": "#b26a00", "Fair": "#b26a00",
        "Neutral": "#b26a00", "Moderate Debt": "#b26a00", "Resilient": "#b26a00", "N/A": "#555555",
        "Strained": "#b71c1c", "Avoid": "#b71c1c", "Narrow": "#b71c1c", "Caution": "#b71c1c", 
        "High Risk": "#b71c1c", "Structural": "#b71c1c", "Stretched": "#b71c1c", 
        "Loss-Making": "#b71c1c", "High Debt": "#b71c1c", "Headwinds": "#b71c1c"
    }

    labels = [
        ("Capital Allocation", matrix.get("CapitalAllocation", "Disciplined")),
        ("Macro", matrix.get("Macro", "Neutral")),
        ("Moat", matrix.get("Moat", "Moderate")),
        ("Gov", matrix.get("Governance", "Clean")),
        ("Diagnostic", matrix.get("Diagnostic", "N/A")),
        ("Valuation", matrix.get("Valuation", "Fair")),
        ("Balance Sheet", matrix.get("BalanceSheet", "Resilient")),
    ]

    pills_html = ['<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px;">']
    for title, val in labels:
        bg = color_map.get(val, "#333333")
        pills_html.append(
            f'<div style="background-color: {bg}; color: #ffffff; padding: 6px 12px; border-radius: 6px; '
            f'font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px;">'
            f'<span style="opacity: 0.8; font-weight: 400; text-transform: uppercase; font-size: 11px;">{title}:</span>'
            f'<span>{val}</span></div>'
        )
    pills_html.append('</div>')
    
    renderer = target_container if target_container is not None else st
    renderer.markdown("".join(pills_html), unsafe_allow_html=True)

with st.sidebar:
    st.header("Archived Reports")
    try:
        archives = get_archived_reports()
        if archives:
            selected_archive = st.selectbox("Select past report:", ["Select..."] + [a.get("ticker", "Unknown") for a in archives])
            if selected_archive != "Select...":
                match = next((a for a in archives if a.get("ticker") == selected_archive), None)
                if match and st.button("Load Archive", use_container_width=True):
                    st.session_state["last_report"] = match.get("report_text")
                    st.session_state["last_ticker"] = selected_archive
                    st.session_state["last_fundamentals"] = {
                        "short_name": match.get("short_name", selected_archive),
                        "market_cap": match.get("baseline_mcap", "Archived"),
                        "pe_ratio": match.get("baseline_pe", "N/A"),
                        "sector": "General Industry",
                        "current_price": match.get("baseline_price", "N/A")
                    }
                    st.rerun()
        else:
            st.info("No archives found.")
    except Exception:
        st.caption("Archive history unavailable.")

st.title("Equity Research Analysis Platform")
st.markdown('<p style="font-size: 19px; color: #888888;">To aid stock discovery and simplify fundamentals.</p>', unsafe_allow_html=True)

with st.form("search_form", clear_on_submit=False):
    query = st.text_input("Enter Company Name or Ticker:", value="")
    selected_language = st.selectbox("Select Report Language:", ["English (India)", "Hindi", "Marathi", "Gujarati", "Tamil", "Telugu", "Bengali"])
    submitted = st.form_submit_button("Generate Research Report", type="primary")

def sanitize_ticker_input(q: str) -> str:
    import re
    return re.sub(r"[^\w\s\.-]", "", q or "").strip()[:40]

if submitted and query:
    clean_query = sanitize_ticker_input(query)
    if not clean_query or len(clean_query) < 2:
        st.error("Please enter a valid company name or stock ticker (minimum 2 characters).")
    else:
        try:
            with st.spinner(f"Auditing market data & filings for {clean_query}..."):
                stock_data = get_stock_fundamentals(clean_query)
                resolved_ticker = stock_data.get("ticker", clean_query)
                scrip = stock_data.get("scrip_code", "")
                cached = get_report_by_ticker(resolved_ticker)
                should_regen, reason, latest_ann = evaluate_material_change(cached, stock_data, scrip)

                if not should_regen and selected_language == "English (India)":
                    st.session_state["last_report"] = cached["report_text"]
                    st.session_state["last_ticker"] = resolved_ticker
                    st.session_state["last_fundamentals"] = stock_data
                    st.rerun()
                else:
                    st.session_state["last_report"] = None
                    st.session_state["last_ticker"] = resolved_ticker
                    st.session_state["last_fundamentals"] = stock_data
                    st.session_state["stream_pending"] = True
                    st.session_state["stream_language"] = selected_language
                    st.rerun()
        except Exception as err:
            st.session_state["last_report"] = None
            stage = getattr(err, "stage", "Pipeline Engine")
            diag_payload = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(), "query_entered": clean_query,
                "error_stage": stage, "error_type": type(err).__name__, "error_message": str(err),
                "technical_details": getattr(err, "technical_details", ""),
                "system": {"python": platform.python_version(), "os": platform.system()},
                "traceback_tail": traceback.format_exc().splitlines()[-4:]
            }
            st.error(f"### ❌ Data Pipeline Stopped at: {stage}")
            st.markdown(f"**Error:** {err}")
            with st.expander("📋 Copy Diagnostic Report", expanded=True):
                st.code(json.dumps(diag_payload, indent=2), language="json")

if ("last_report" in st.session_state and st.session_state["last_report"] is not None) or st.session_state.get("stream_pending"):
    fund = st.session_state.get("last_fundamentals", {})
    ticker_disp = st.session_state.get("last_ticker", "STOCK")
    company_name = fund.get("short_name", "").strip()
    clean_ticker = ticker_disp.strip().upper()
    header_label = f"{company_name} ({clean_ticker})" if company_name and company_name.upper() != clean_ticker else clean_ticker

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
    badge_container = st.empty()
    if st.session_state.get("last_report"):
        render_health_card_ui(st.session_state["last_report"], target_container=badge_container)
    st.header(f"Equity Research Report: {header_label}")

    if st.session_state.get("stream_pending"):
        st.session_state["stream_pending"] = False
        lang = st.session_state.get("stream_language", "English (India)")
        try:
            with st.status("Auditing market data & generating report...", expanded=True) as status:
                st.write(f"📊 Verified Quote: **₹{fund.get('current_price', 'N/A')}**")
                stream_gen = stream_stock_report(clean_ticker, language=lang, stock_data=fund, on_status=lambda msg: st.write(msg))
                try:
                    first_chunk = next(stream_gen)
                    status.update(label="✅ Audit complete. Streaming live research...", state="complete", expanded=False)
                except StopIteration:
                    first_chunk = ""
                    status.update(label="Stream ended unexpectedly.", state="error", expanded=False)

            def combined_stream():
                if first_chunk: yield first_chunk
                yield from stream_gen

            streamed_text = st.write_stream(combined_stream)
            render_health_card_ui(streamed_text, target_container=badge_container)
            if "Live Synthesis Failed" in streamed_text:
                cached_rec = get_report_by_ticker(clean_ticker)
                if cached_rec and cached_rec.get("report_text"):
                    st.warning(f"⚠️ Live generation failed. Displaying archive from {cached_rec.get('formatted_date')}.")
                    st.session_state["last_report"] = cached_rec["report_text"]
                else:
                    st.session_state["last_report"] = streamed_text
            else:
                st.session_state["last_report"] = streamed_text
            st.rerun()
        except Exception as stream_err:
            st.error(f"### ❌ Live Streaming Halted: {stream_err}")
            st.session_state["last_report"] = None
    elif st.session_state.get("last_report"):
        st.markdown(remove_health_matrix_text(st.session_state["last_report"]))

    if st.session_state.get("last_report"):
        if st.button("Generate & Download PDF", type="primary"):
            with st.spinner("Compiling print-ready PDF..."):
                full_md = f"# Equity Research Report: {header_label}\n\n" + remove_health_matrix_text(str(st.session_state["last_report"]))
                pdf = MarkdownPdf(toc_level=0)
                pdf.add_section(Section(full_md))
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    pdf.save(tmp.name)
                    tmp_path = tmp.name
                with open(tmp_path, "rb") as f:
                    pdf_bytes = f.read()
                st.download_button(
                    label="Click Here to Download (.pdf)",
                    data=pdf_bytes,
                    file_name=f"{clean_ticker}_Research_Report.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
