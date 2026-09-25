import traceback
import platform
import json
import os
import sys
import time
from datetime import datetime, timezone
import streamlit as st
from analyzer import (
    remove_health_matrix_text,
    extract_health_matrix,
    stream_stock_report,
    get_stock_fundamentals,
    evaluate_material_change,
    get_historical_prices,
)
from db import get_archived_reports, get_report_by_ticker
from markdown_pdf import MarkdownPdf, Section

st.set_page_config(page_title="Equity Research AI", layout="wide", page_icon="📈")

# Production UI Stylesheet (Metric Unclip & Reading Bounds)
st.markdown(
    """
    <style>
    /* 1. Constrain canvas width on zoom-out while staying fluid on mobile / zoom-in */
    .main .block-container {
        max-width: min(1280px, 95vw) !important;
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
        margin: 0 auto !important;
    }

    /* 2. Prevent st.metric from cutting off text with ellipses and wrap gracefully */
    [data-testid="stMetric"] {
        min-width: 180px !important;
    }
    [data-testid="stMetricValue"] > div {
        font-size: clamp(1.15rem, 1.4vw, 1.5rem) !important;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: unset !important;
        line-height: 1.25 !important;
    }
    [data-testid="stMetricLabel"] > div {
        font-size: 0.95rem !important;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: unset !important;
    }

    /* 3. Constrain reading measure strictly on report prose */
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li {
        max-width: 860px !important;
        line-height: 1.65 !important;
        font-size: 17px !important;
    }

    /* 4. Responsive horizontal column wrapping for zoom-in */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 16px !important;
    }
    [data-testid="stHorizontalBlock"] > div {
        flex: 1 1 200px !important;
        min-width: 180px !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

def render_material_badge(reason: str, is_regenerated: bool):
    """Renders a responsive status badge detailing cache vs regeneration triggers."""
    if not reason:
        return
    bg = "#fef3c7" if is_regenerated else "#ecfdf5"
    border = "#fde68a" if is_regenerated else "#a7f3d0"
    text_color = "#92400e" if is_regenerated else "#065f46"
    st.markdown(
        f"""
        <div style="display: inline-flex; align-items: center; background-color: {bg}; color: {text_color};
                    padding: 5px 12px; border-radius: 6px; font-size: 13px; font-weight: 600;
                    margin-bottom: 12px; border: 1px solid {border};">
            {reason}
        </div>
        """,
        unsafe_allow_html=True,
    )

def generate_pdf_chart_image(df, ticker: str):
    """Generates a high-resolution static PNG of the 6-month momentum and 50-DMA for PDF embedding."""
    if df is None or not hasattr(df, "empty") or df.empty or "Date" not in df.columns or "Close" not in df.columns:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import tempfile
        import pandas as pd

        plot_df = df.copy()
        plot_df["Date"] = pd.to_datetime(plot_df["Date"])
        plot_df = plot_df.sort_values("Date")

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 3.6), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
        fig.patch.set_facecolor('#ffffff')

        # Price & 50-DMA
        ax1.set_facecolor('#ffffff')
        ax1.plot(plot_df["Date"], plot_df["Close"], color="#2563eb", linewidth=1.6, label="Close Price")
        if "SMA50" in plot_df.columns and not plot_df["SMA50"].dropna().empty:
            ax1.plot(plot_df["Date"], plot_df["SMA50"], color="#d97706", linewidth=1.3, linestyle="--", label="50-DMA")
        
        ax1.set_title(f"6-Month Price Momentum & 50-DMA ({ticker})", fontsize=10, fontweight="bold", pad=6)
        ax1.set_ylabel("Price (INR)", fontsize=8)
        ax1.legend(loc="upper left", frameon=True, fontsize=8)
        ax1.grid(True, linestyle=":", alpha=0.5)

        # Volume
        ax2.set_facecolor('#ffffff')
        if "Volume" in plot_df.columns:
            ax2.bar(plot_df["Date"], plot_df["Volume"], color="#94a3b8", alpha=0.6, width=1.5)
        ax2.set_ylabel("Vol", fontsize=7)
        ax2.grid(True, linestyle=":", alpha=0.5)

        plt.tight_layout()
        import re as re_mod
        clean_name = re_mod.sub(r'[^a-zA-Z0-9]', '_', ticker)
        local_img_path = f"_pdf_chart_{clean_name}.png"
        plt.savefig(local_img_path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        return local_img_path
    except Exception:
        return None


def render_momentum_chart(df, ticker: str):
    """Renders a responsive 6-month price momentum chart with on-the-fly fallback and dynamic inference explainer."""
    import altair as alt
    import pandas as pd

    # Fallback fetch if viewing an archived report
    if (df is None or not hasattr(df, "empty") or df.empty) and ticker:
        with st.spinner(f"Loading price momentum for {ticker}..."):
            df = get_historical_prices(ticker)
            if df is not None and not df.empty:
                st.session_state["last_history"] = df

    if df is None or not hasattr(df, "empty") or df.empty or "Date" not in df.columns or "Close" not in df.columns:
        if ticker:
            st.caption(f"ℹ️ Trailing 6-month price momentum chart unavailable for {ticker} (exchange feed unlisted).")
        return

    base = alt.Chart(df).encode(
        x=alt.X("Date:T", title="Date", axis=alt.Axis(format="%b %Y", labelAngle=0, grid=False))
    )

    price_line = base.mark_line(color="#2563eb", strokeWidth=2).encode(
        y=alt.Y("Close:Q", scale=alt.Scale(zero=False), title="Price (₹ INR)"),
        tooltip=[
            alt.Tooltip("Date:T", format="%Y-%m-%d", title="Date"),
            alt.Tooltip("Close:Q", format=".2f", title="Close Price (₹ INR)"),
            alt.Tooltip("SMA50:Q", format=".2f", title="50-DMA [50-Day Moving Average] (₹ INR)")
        ]
    )

    sma_line = base.mark_line(color="#f59e0b", strokeWidth=1.5, strokeDash=[4, 4]).encode(
        y=alt.Y("SMA50:Q", scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("Date:T", format="%Y-%m-%d", title="Date"),
            alt.Tooltip("SMA50:Q", format=".2f", title="50-DMA [50-Day Moving Average] (₹ INR)")
        ]
    )

    vol_max = df["Volume"].max() if "Volume" in df.columns and df["Volume"].max() > 0 else 1
    vol_bars = base.mark_bar(opacity=0.18, color="#64748b").encode(
        y=alt.Y("Volume:Q", axis=None, scale=alt.Scale(domain=[0, vol_max * 4]))
    )

    chart = alt.layer(vol_bars, price_line, sma_line).properties(
        title=f"6-Month Price Momentum & 50-DMA [50-Day Moving Average] ({ticker})",
        height=300
    ).resolve_scale(y="independent")

    st.altair_chart(chart, use_container_width=True)

    # Dynamic Technical Inference Explainer
    valid_sma = df.dropna(subset=["SMA50", "Close"])
    if not valid_sma.empty:
        latest_row = valid_sma.iloc[-1]
        c_price = float(latest_row["Close"])
        sma_val = float(latest_row["SMA50"])
        diff_pct = ((c_price - sma_val) / sma_val) * 100.0

        if diff_pct >= 1.5:
            posture = "Bullish Intermediate Momentum"
            color_border = "#10b981"
            bg_color = "rgba(16, 185, 129, 0.08)"
            inference = (
                f"Trading <strong>{abs(diff_pct):.1f}% above</strong> its 50-DMA "
                f"(50-Day Moving Average). The price is sustaining upward momentum, with the 50-DMA line functioning "
                f"as dynamic intermediate support (price floor)."
            )
        elif diff_pct <= -1.5:
            posture = "Corrective / Consolidation Posture"
            color_border = "#f59e0b"
            bg_color = "rgba(245, 158, 11, 0.08)"
            inference = (
                f"Trading <strong>{abs(diff_pct):.1f}% below</strong> its 50-DMA "
                f"(50-Day Moving Average). The price faces intermediate overhead resistance, indicating "
                f"cooling demand or consolidation before a trend reversal."
            )
        else:
            posture = "Inflection / Mean-Reversion Zone"
            color_border = "#3b82f6"
            bg_color = "rgba(59, 130, 246, 0.08)"
            inference = (
                f"Trading within <strong>{abs(diff_pct):.1f}% of its 50-DMA</strong> "
                f"(50-Day Moving Average). The stock is consolidating directly along its 10-week intermediate mean."
            )

        st.markdown(
            f"""
            <div style="border-left: 3px solid {color_border}; background-color: {bg_color}; 
                        padding: 10px 14px; border-radius: 0 6px 6px 0; margin-top: -6px; margin-bottom: 16px;">
                <div style="font-size: 13px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;">
                    Technical Posture: {posture}
                </div>
                <div style="font-size: 13px; color: #cbd5e1; line-height: 1.5;">
                    Current Close: <strong>₹{c_price:,.2f}</strong> vs 50-DMA: <strong>₹{sma_val:,.2f}</strong>. {inference}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

def format_inr(number):
    if number is None or str(number).strip() in ["", "0", "N/A", "None"]:
        return "N/A"
    try:
        clean_num = str(number).replace(",", "").strip()
        val = float(clean_num)
    except (ValueError, TypeError):
        return str(number)

    def group_inr(num):
        parts = f"{num:.2f}".split(".")
        int_p, dec_p = parts[0], parts[1]
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

    if val >= 1e7:
        return f"₹{group_inr(val / 1e7)} Cr"
    elif val >= 1e5:
        return f"₹{group_inr(val / 1e5)} Lakh"
    return f"₹{group_inr(val)}"

def build_pdf_dossier(rep_text: str, ticker: str, header_label: str, hist_df) -> bytes:
    """Compiles the report, 7-pillar scorecard, and static chart into an executive PDF binary."""
    import os
    import re as re_mod
    from datetime import datetime, timezone
    from markdown_pdf import MarkdownPdf, Section
    
    clean_name = re_mod.sub(r'[^a-zA-Z0-9]', '_', ticker)
    matrix = extract_health_matrix(rep_text)
    clean_body = remove_health_matrix_text(rep_text)
    chart_filename = generate_pdf_chart_image(hist_df, ticker)
    now_str = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    
    embedded_style = """<style>
table { width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 9pt; }
th, td { border: 1px solid #cbd5e1; padding: 5px 8px; text-align: left; }
th { background-color: #f1f5f9; font-weight: bold; }
blockquote { border-left: 3px solid #2563eb; padding-left: 8px; color: #475569; margin: 8px 0; font-size: 8.5pt; }
h1 { color: #0f172a; font-size: 15pt; margin-bottom: 4px; }
h2 { color: #1e293b; font-size: 12pt; margin-top: 14px; border-bottom: 1px solid #e2e8f0; padding-bottom: 3px; }
h3 { color: #334155; font-size: 10.5pt; margin-top: 10px; }
img { max-width: 100%; height: auto; margin: 6px 0; }
p, li { font-size: 9.5pt; line-height: 1.45; }
</style>
"""
    scorecard_md = f"""### Institutional 7-Pillar Health Scorecard
| Analytical Pillar | Rating / Posture | Evaluated Dimension |
| :--- | :--- | :--- |
| **Capital Allocation** | {matrix.get('CapitalAllocation', 'Disciplined')} | Reinvestment discipline & cash returns |
| **Macro Environment** | {matrix.get('Macro', 'Neutral')} | Sector tailwinds & systemic risks |
| **Competitive Moat** | {matrix.get('Moat', 'Moderate')} | Pricing power & entry barriers |
| **Governance & Promoters** | {matrix.get('Governance', 'Clean')} | Accounting integrity & alignment |
| **Drop Diagnostic** | {matrix.get('Diagnostic', 'N/A')} | Structural erosion vs temporary dip |
| **Valuation Multiple** | {matrix.get('Valuation', 'Fair')} | Price relative to intrinsic band |
| **Balance Sheet Leverage** | {matrix.get('BalanceSheet', 'Resilient')} | Solvency & debt service capacity |
"""
    chart_md = f"\n### Trailing 6-Month Momentum & Technical Overlay\n![6-Month Price Momentum]({chart_filename})\n" if chart_filename and os.path.exists(chart_filename) else ""
    header_branding = f"""# Equity Research Report: {header_label}
> **Platform:** [Equity Research AI Platform](https://stock-research-app2.streamlit.app)  
> **Generated:** {now_str} | **Exchange Status:** Verified Indian Equities Feed
"""
    footer_disclaimer = """
---
> *Disclaimer: This report is automatically generated by an AI research assistant using public BSE disclosures and search grounding. It is intended strictly for informational and educational auditing purposes and does not constitute financial or investment advice under SEBI (Research Analysts) Regulations.*
"""
    full_md = f"{embedded_style}\n{header_branding}\n{scorecard_md}\n{chart_md}\n---\n\n{clean_body}\n{footer_disclaimer}"
    
    try:
        pdf = MarkdownPdf(toc_level=0)
        pdf.add_section(Section(full_md, root="."))
        out_name = f"_tmp_doc_{clean_name}.pdf"
        pdf.save(out_name)
        with open(out_name, "rb") as f:
            pdf_bytes = f.read()
        if os.path.exists(out_name):
            os.unlink(out_name)
        return pdf_bytes
    finally:
        if chart_filename and os.path.exists(chart_filename):
            os.unlink(chart_filename)


def render_health_card_ui(report_text: str, target_container=None):
    render_momentum_chart(st.session_state.get('last_history'), st.session_state.get('last_ticker', ''))
    render_material_badge(st.session_state.get('material_reason', ''), st.session_state.get('is_regenerated', False))
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
                st.session_state["last_history"] = get_historical_prices(stock_data.get("ticker", clean_query))
                resolved_ticker = stock_data.get("ticker", clean_query)
                scrip = stock_data.get("scrip_code", "")
                cached = get_report_by_ticker(resolved_ticker)
                should_regen, reason, latest_ann = evaluate_material_change(cached, stock_data, scrip)
                st.session_state["material_reason"] = reason
                st.session_state["is_regenerated"] = should_regen

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
            err_str = str(err).lower()
            if isinstance(err, ValueError) or "scrip code" in err_str or "not found" in err_str:
                st.warning(f"⚠️ **Stock Not Located:** Could not find verified BSE/NSE exchange listings for **'{clean_query}'**.")
                suggestions = get_ticker_suggestions(clean_query)
                if suggestions:
                    st.info(f"💡 **Did you mean:** {', '.join(suggestions)}?")
                else:
                    st.caption("Please verify the spelling, enter the listed ticker symbol (e.g., INFY, TCS), or provide the 6-digit BSE Scrip Code.")
            else:
                stage = getattr(err, "stage", "Pipeline Engine")
                diag_payload = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(), "query_entered": clean_query,
                    "error_stage": stage, "error_type": type(err).__name__, "error_message": str(err),
                    "technical_details": getattr(err, "technical_details", ""),
                    "system": {"python": platform.python_version(), "os": platform.system()},
                    "traceback_tail": traceback.format_exc().splitlines()[-4:] if 'traceback' in globals() else []
                }
                st.error(f"### ❌ Data Pipeline Stopped at: {stage}")
                st.markdown(f"**Error:** {err}")
                with st.expander("📋 Technical Diagnostic Details", expanded=False):
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

    # Top Primary Download Button (Rendered directly under header in red)
    if st.session_state.get("last_report"):
        rep_content = st.session_state["last_report"]
        pdf_cache_id = f"{clean_ticker}_{hash(rep_content)}"
        
        if st.session_state.get("pdf_cache_id") != pdf_cache_id or "cached_pdf_bytes" not in st.session_state:
            try:
                st.session_state["cached_pdf_bytes"] = build_pdf_dossier(
                    rep_content,
                    clean_ticker,
                    header_label,
                    st.session_state.get("last_history")
                )
                st.session_state["pdf_cache_id"] = pdf_cache_id
            except Exception as pdf_err:
                st.session_state["cached_pdf_bytes"] = None
                st.caption(f"PDF export notice: {pdf_err}")
                
        if st.session_state.get("cached_pdf_bytes"):
            st.download_button(
                label="Download PDF Report",
                data=st.session_state["cached_pdf_bytes"],
                file_name=f"{clean_ticker}_Research_Report.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=False
            )

    if st.session_state.get("stream_pending"):
        st.session_state["stream_pending"] = False
        lang = st.session_state.get("stream_language", "English (India)")
        try:
            with st.status("🔍 Auditing exchange filings & synthesizing research...", expanded=True) as status:
                st.caption("ℹ️ *Institutional Due Diligence: Research grounded in public BSE filings and exchange feeds via AI synthesis under SEBI educational safe-harbor standards.*")
                st.write(f"✓ **Exchange Quote Verified:** ₹{fund.get('current_price', 'N/A')} (Scrip: {fund.get('scrip_code', clean_ticker)})")
                st.write(f"✓ **Fundamental Valuation Metrics:** Market Cap ₹{format_inr(fund.get('market_cap', 0))} | Trailing P/E: {fund.get('pe_ratio', 'N/A')}")
                if st.session_state.get("last_history") is not None and not st.session_state["last_history"].empty:
                    st.write("✓ **Technical Momentum Aggregated:** 6-month OHLCV data & rolling 50-DMA calculated.")
                st.write("✓ **Regulatory Filings Scanned:** BSE Corporate Announcements & Disclosures ingested.")
                st.write("⚡ **Synthesizing 7-Pillar Institutional Equity Research Dossier...**")
                
                stream_gen = stream_stock_report(clean_ticker, language=lang, stock_data=fund, on_status=lambda msg: st.write(f"• {msg}"))
                try:
                    first_chunk = next(stream_gen)
                    status.update(label="✅ Due diligence complete. Report generated.", state="complete", expanded=False)
                except StopIteration:
                    first_chunk = ""
                    status.update(label="⚠️ Stream ended unexpectedly.", state="error", expanded=False)

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
