import json
import traceback
import platform
from datetime import datetime, timezone
import tempfile
import streamlit as st
from analyzer import generate_stock_report, stream_stock_report, get_stock_fundamentals, evaluate_material_change
from db import get_archived_reports, get_report_by_ticker
from markdown_pdf import MarkdownPdf, Section

st.set_page_config(page_title="Equity Research AI", layout="wide", page_icon="📈")

st.markdown("""
    <style>
        /* Increase body copy font size by 3 points (~19px) while keeping headers untouched */
        div[data-testid="stMarkdownContainer"] p, 
        .stTextInput label, 
        .stSelectbox label, 
        .stMarkdown li,
        .stCaptionContainer p {
            font-size: 19px !important;
        }
    </style>
""", unsafe_allow_html=True)

def format_inr(number):
    if number is None or not isinstance(number, (int, float)):
        return "N/A"
    
    def group_inr(val):
        parts = f"{val:.2f}".split(".")
        int_p, dec_p = parts[0], parts[1]
        if len(int_p) <= 3:
            return f"{int_p}.{dec_p}"
        last_three = int_p[-3:]
        rest = int_p[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        groups.reverse()
        return f"{','.join(groups)},{last_three}.{dec_p}"

    if number >= 1e7:
        return f"₹{group_inr(number / 1e7)} Cr"
    elif number >= 1e5:
        return f"₹{group_inr(number / 1e5)} Lakh"
    return f"₹{group_inr(number)}"

def convert_md_to_pdf_bytes(markdown_text: str) -> bytes:
    pdf = MarkdownPdf(toc_level=0)
    pdf.add_section(Section(markdown_text))
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.save(tmp.name)
        tmp_path = tmp.name
    with open(tmp_path, "rb") as f:
        pdf_bytes = f.read()
    return pdf_bytes

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
                        "market_cap": "Archived",
                        "pe_ratio": "N/A",
                        "sector": "General Industry"
                    }
                    st.rerun()
        else:
            st.info("No archives found.")
    except Exception:
        st.caption("Archive history unavailable.")

st.title("Equity Research Analysis Platform")

st.markdown('<p style="font-size: 19px; color: #888888;">To aid stock discovery and simplify their fundamentals.</p>', unsafe_allow_html=True)

with st.form("search_form", clear_on_submit=False):
    query = st.text_input("Enter Company Name or Ticker:", value="")
    st.caption("Press enter to start learning")
    
    selected_language = st.selectbox(
        "Select Report Language:", 
        ["English (India)", "Hindi", "Marathi", "Gujarati", "Tamil", "Telugu", "Bengali"]
    )
    
    if selected_language != "English (India)":
        st.caption("⚠️ Translations are AI-generated for accessibility; refer to the original English report for audited financial figures.")
        
    submitted = st.form_submit_button("Generate Research Report", type="primary")

def sanitize_ticker_input(q: str) -> str:
    import re
    if not q or not isinstance(q, str):
        return ""
    cleaned = re.sub(r"[^\w\s\.-]", "", q).strip()
    return cleaned[:40]

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
                    st.session_state["report_source"] = f"Cached ({cached['formatted_date']})"
                    st.session_state["gate_reason"] = reason
                    st.session_state["cached_record"] = cached
                    st.rerun()
                else:
                    # Trigger two-phase render: render metrics instantly, stream prose below
                    st.session_state["last_report"] = None
                    st.session_state["last_ticker"] = resolved_ticker
                    st.session_state["last_fundamentals"] = stock_data
                    st.session_state["report_source"] = "Freshly Generated"
                    st.session_state["gate_reason"] = reason
                    st.session_state["stream_pending"] = True
                    st.session_state["stream_language"] = selected_language
                    st.session_state.pop("cached_record", None)
                    st.rerun()
        except Exception as err:
            st.session_state["last_report"] = None
            stage = getattr(err, "stage", "Pipeline Engine")
            tech_details = getattr(err, "technical_details", "")
            
            diag_payload = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "query_entered": clean_query,
                "error_stage": stage,
                "error_type": type(err).__name__,
                "error_message": str(err),
                "technical_details": tech_details,
                "system": {
                    "python": platform.python_version(),
                    "os": platform.system()
                },
                "traceback_tail": traceback.format_exc().splitlines()[-4:]
            }
            
            st.error(f"### ❌ Data Pipeline Stopped at: {stage}")
            st.markdown(f"**Error:** {err}")
            st.caption("🛡️ **Zero-Hallucination Policy:** Synthetic estimation disabled. Reports require direct exchange quotes.")
            
            with st.expander("📋 Copy Diagnostic Report (Share to Fix)", expanded=True):
                st.code(json.dumps(diag_payload, indent=2), language="json")

if ("last_report" in st.session_state and st.session_state["last_report"] is not None) or st.session_state.get("stream_pending"):
    fund = st.session_state.get("last_fundamentals", {})
    ticker_disp = st.session_state.get("last_ticker", "STOCK")
    
    col1, col2, col3, col4 = st.columns(4)
    mcap = fund.get("market_cap", 0)
    
    if isinstance(mcap, (int, float)):
        mcap_str = format_inr(mcap)
    else:
        mcap_str = str(mcap)
        
    col1.metric("Market Capitalization", mcap_str)
    col2.metric("P/E Ratio", str(fund.get("pe_ratio", "N/A")))
    col3.metric("Sector", str(fund.get("sector", "N/A")))
    col4.metric("Exchange Status", "Active / Verified")
    
    st.markdown("---")
    company_name = fund.get("short_name", "").strip()
    clean_ticker = ticker_disp.strip().upper()
    header_label = f"{company_name} ({clean_ticker})" if company_name and company_name.upper() != clean_ticker else clean_ticker
    
    st.header(f"Equity Research Report: {header_label}")
    
    if st.session_state.get("stream_pending"):
        st.session_state["stream_pending"] = False
        lang = st.session_state.get("stream_language", "English (India)")
        
        try:
            with st.status("Auditing market data & generating report...", expanded=True) as status:
                st.write(f"📊 Verified Quote: **₹{fund.get('current_price', 'N/A')}** | Mcap: **{fund.get('market_cap', 'N/A')}**")
                
                def live_status_hook(msg):
                    st.write(msg)
                
                stream_gen = stream_stock_report(clean_ticker, language=lang, stock_data=fund, on_status=live_status_hook)
                
                # Await initial grounded response while streaming live telemetry inside the status card
                try:
                    first_chunk = next(stream_gen)
                    status.update(label="✅ Audit complete. Streaming live research...", state="complete", expanded=False)
                except StopIteration:
                    first_chunk = ""
                    status.update(label="Stream ended unexpectedly.", state="error", expanded=False)
            
            def combined_stream():
                if first_chunk:
                    yield first_chunk
                yield from stream_gen
                
            streamed_text = st.write_stream(combined_stream)
            st.session_state["last_report"] = streamed_text
        except Exception as stream_err:
            st.error(f"### ❌ Live Streaming Halted: {stream_err}")
            st.session_state["last_report"] = None
    elif st.session_state.get("last_report"):
        st.markdown(st.session_state["last_report"])
    
    full_report_md = f"# Equity Research Report: {header_label}\n\n" + str(st.session_state.get("last_report") or "")
    pdf_data = convert_md_to_pdf_bytes(full_report_md)
    st.download_button(
        label="Download Research Report (.pdf)",
        data=pdf_data,
        file_name=f"{ticker_disp.strip().upper().replace(' ', '_')}_Research_Report.pdf",
        mime="application/pdf",
        type="primary"
    )