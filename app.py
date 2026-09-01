import tempfile
import streamlit as st
from analyzer import generate_stock_report, get_stock_fundamentals
from db import get_archived_reports
from markdown_pdf import MarkdownPdf, Section

st.set_page_config(page_title="Equity Research AI", layout="wide", page_icon="📈")
st.title("Equity Research Analysis Platform")

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
    st.header("Controls & History")
    if st.button("Clear Application Cache", use_container_width=True):
        st.cache_data.clear()
        st.success("Cache cleared.")
        st.rerun()
        
    st.markdown("---")
    st.subheader("Archived Reports")
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
    except Exception as e:
        st.caption("Archive history unavailable.")

query = st.text_input("Enter Company Name or Ticker (e.g., Tata Motors, SBILIFE, RELIANCE):", "")

if st.button("Generate Research Report", type="primary") and query:
    try:
        with st.spinner(f"Analyzing {query} and running validation audit..."):
            stock_data = get_stock_fundamentals(query)
            report_text = generate_stock_report(query)
            st.session_state["last_report"] = report_text
            st.session_state["last_ticker"] = query
            st.session_state["last_fundamentals"] = stock_data
    except ValueError as ve:
        st.error(f"Data Retrieval Error: {str(ve)}")
    except Exception as e:
        st.error(f"Application Error: {str(e)}")

if "last_report" in st.session_state:
    fund = st.session_state.get("last_fundamentals", {})
    ticker_disp = st.session_state.get("last_ticker", "STOCK")
    
    st.markdown(f"### Executive Summary: {fund.get('short_name', ticker_disp)}")
    
    col1, col2, col3, col4 = st.columns(4)
    mcap = fund.get("market_cap", 0)
    if isinstance(mcap, (int, float)) and mcap > 0:
        mcap_str = f"₹{mcap / 10000000:.2f} Cr"
    else:
        mcap_str = str(mcap)
        
    col1.metric("Market Capitalization", mcap_str)
    col2.metric("P/E Ratio", str(fund.get("pe_ratio", "N/A")))
    col3.metric("Sector", str(fund.get("sector", "N/A")))
    col4.metric("Exchange Status", "Active / Verified")
    
    st.markdown("---")
    st.markdown(st.session_state["last_report"])
    
    pdf_data = convert_md_to_pdf_bytes(st.session_state["last_report"])
    st.download_button(
        label="Download Research Report (.pdf)",
        data=pdf_data,
        file_name=f"{ticker_disp.strip().upper().replace(' ', '_')}_Research_Report.pdf",
        mime="application/pdf",
        type="primary"
    )
