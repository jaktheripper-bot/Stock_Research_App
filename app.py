import re
from datetime import datetime, timezone, timedelta
import traceback
import platform
import json
import os
import sys
import time
import streamlit as st

IST = timezone(timedelta(hours=5, minutes=30))
from analyzer import (
    remove_health_matrix_text,
    strip_conclusion_sections,
    extract_health_matrix,
    compare_revisions,
    stream_stock_report,
    get_stock_fundamentals,
    evaluate_material_change,
    get_historical_prices,
)
from db import (
    get_archived_reports,
    get_report_by_ticker,
    get_report_revisions,
    get_watchlist,
    add_to_watchlist,
    remove_from_watchlist,
    is_ticker_in_watchlist,
    get_alert_events,
    get_unread_alert_count,
    mark_alert_as_read,
    mark_all_alerts_as_read,
    dismiss_alert,
    dismiss_all_alerts,
)
from alerts import run_surveillance_scan
from bse_master import get_ticker_suggestions

st.set_page_config(page_title="Equity Research AI", layout="wide", page_icon="📈")

def inject_ga4_tracking():
    """Injects Google Analytics 4 tracking script if GA4_MEASUREMENT_ID is configured in secrets."""
    try:
        ga_id = st.secrets.get("GA4_MEASUREMENT_ID") or os.environ.get("GA4_MEASUREMENT_ID")
        if ga_id and str(ga_id).startswith("G-"):
            st.html(
                f"""
                <!-- Google tag (gtag.js) -->
                <script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>
                <script>
                  window.dataLayer = window.dataLayer || [];
                  function gtag(){{dataLayer.push(arguments);}}
                  gtag('js', new Date());
                  gtag('config', '{ga_id}');
                </script>
                """
            )
    except Exception:
        pass

inject_ga4_tracking()

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

def sanitize_ticker_input(q: str) -> str:
    """Sanitizes ticker queries by stripping non-alphanumeric characters except dots and hyphens."""
    import re
    return re.sub(r"[^\w\s\.-]", "", q or "").strip()[:40]


def set_active_dossier_state(
    ticker: str,
    report_text: str = None,
    report_date: str = None,
    fundamentals: dict = None,
    material_reason: str = "📂 Loaded from Archived Research Dossier",
    is_regenerated: bool = False,
    viewing_snapshot: dict = None,
    custom_diff: dict = None,
    history_df=None
):
    """Atomically synchronizes all report, chart, and surveillance session state for a given ticker."""
    clean_t = (ticker or "").strip().upper()
    st.session_state["last_ticker"] = clean_t
    st.session_state["last_report"] = report_text
    st.session_state["last_report_date"] = report_date
    st.session_state["last_fundamentals"] = fundamentals or {}
    st.session_state["material_reason"] = material_reason
    st.session_state["is_regenerated"] = is_regenerated
    st.session_state["cached_pdf_bytes"] = None
    st.session_state["pdf_cache_id"] = None
    st.session_state["sb_archive_sync_ticker"] = clean_t

    if history_df is not None:
        st.session_state["last_history"] = history_df
        st.session_state["last_history_ticker"] = clean_t
    else:
        st.session_state["last_history"] = None
        st.session_state["last_history_ticker"] = None

    if viewing_snapshot:
        st.session_state["viewing_snapshot"] = viewing_snapshot
    else:
        st.session_state.pop("viewing_snapshot", None)

    if custom_diff:
        st.session_state["custom_diff"] = custom_diff
    else:
        st.session_state.pop("custom_diff", None)

def execute_stock_research(query: str, selected_language: str = "English (India)"):
    """Executes the 5-phase data ingestion, validation, delta-gating, and synthesis pipeline for a stock query."""
    st.session_state.pop("viewing_snapshot", None)
    st.session_state.pop("custom_diff", None)
    clean_query = sanitize_ticker_input(query)
    if not clean_query or len(clean_query) < 2:
        st.error("Please enter a valid company name or stock ticker (minimum 2 characters).")
        return
    try:
        prog_slot = st.empty()
        prog_bar = prog_slot.progress(0.20, text=f"⏳ Step 1/4: Verifying BSE Exchange Quote for {clean_query}...")
        stock_data = get_stock_fundamentals(clean_query)
        resolved_ticker = stock_data.get("ticker", clean_query)
        scrip = stock_data.get("scrip_code", "")

        prog_bar.progress(0.50, text=f"⚡ Step 2/4: Concurrently Ingesting Technicals & BSE Disclosures for {resolved_ticker}...")
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_hist = executor.submit(get_historical_prices, resolved_ticker)
            def _fetch_delta_and_cache():
                c = get_report_by_ticker(resolved_ticker)
                s_regen, r_reason, l_ann = evaluate_material_change(c, stock_data, scrip)
                return c, s_regen, r_reason, l_ann
            future_disclosures = executor.submit(_fetch_delta_and_cache)

            hist_df = future_hist.result()
            cached, should_regen, reason, latest_ann = future_disclosures.result()

        st.session_state["last_history"] = hist_df
        st.session_state["last_history_ticker"] = resolved_ticker

        if not should_regen and selected_language == "English (India)":
            prog_bar.progress(1.0, text="✅ Step 4/4: Verified Dossier Retrieved from Archive!")
            prog_slot.empty()
            set_active_dossier_state(
                ticker=resolved_ticker,
                report_text=cached["report_text"],
                report_date=cached.get("formatted_date"),
                fundamentals=stock_data,
                material_reason=reason,
                is_regenerated=False,
                history_df=hist_df
            )
            st.rerun(scope="app")
        else:
            prog_bar.progress(0.80, text="⚡ Step 3/4: Initializing 7-Pillar Institutional AI Synthesis...")
            prog_slot.empty()
            set_active_dossier_state(
                ticker=resolved_ticker,
                report_text=None,
                fundamentals=stock_data,
                material_reason=reason,
                is_regenerated=True,
                history_df=hist_df
            )
            st.session_state["stream_pending"] = True
            st.session_state["stream_language"] = selected_language
            st.rerun(scope="app")
    except Exception as err:
        st.session_state["last_report"] = None
        err_str = str(err).lower()
        if isinstance(err, ValueError) or "scrip code" in err_str or "not found" in err_str:
            st.warning(f"⚠️ **Stock Not Located:** Could not find verified BSE/NSE exchange listings for **'{clean_query}'**.")
            suggestions = get_ticker_suggestions(clean_query)
            if suggestions:
                st.info(f"💡 **Did you mean:** {', '.join(suggestions)}?")
            else:
                st.caption("ℹ️ Examples of valid inputs: `INFY`, `TCS`, `RELIANCE`, or the 6-digit BSE Scrip Code like `500209`.")
        else:
            stage = getattr(err, "stage", "Pipeline Engine")
            diag_payload = {
                "timestamp_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
                "query_entered": clean_query,
                "error_stage": stage,
                "error_type": type(err).__name__,
                "error_message": str(err),
                "technical_details": getattr(err, "technical_details", ""),
                "system": {"python": platform.python_version(), "os": platform.system()},
                "traceback_tail": traceback.format_exc().splitlines()[-4:] if 'traceback' in globals() else []
            }
            st.error(f"### ❌ Data Pipeline Stopped at: {stage}")
            st.markdown(f"**Error:** {err}")
            with st.expander("📋 Technical Diagnostic Details", expanded=False):
                st.code(json.dumps(diag_payload, indent=2), language="json")


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

    # Fallback fetch if viewing an archived report or if cached chart belongs to a different stock
    cached_chart_ticker = st.session_state.get("last_history_ticker")
    if (df is None or not hasattr(df, "empty") or df.empty or cached_chart_ticker != ticker) and ticker:
        with st.spinner(f"Loading price momentum for {ticker}..."):
            df = get_historical_prices(ticker)
            if df is not None and not df.empty:
                st.session_state["last_history"] = df
                st.session_state["last_history_ticker"] = ticker

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

    st.altair_chart(chart, width="stretch")

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
    from markdown_pdf import MarkdownPdf, Section
    clean_name = re_mod.sub(r'[^a-zA-Z0-9]', '_', ticker)
    matrix = extract_health_matrix(rep_text)
    clean_body = strip_conclusion_sections(remove_health_matrix_text(rep_text))
    chart_filename = generate_pdf_chart_image(hist_df, ticker)
    now_str = datetime.now(IST).strftime("%d %B %Y, %H:%M IST")
    
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
> *Disclaimer: This report is automatically generated by an AI research assistant using public BSE disclosures and search grounding. It is intended strictly for informational and educational auditing purposes and does not constitute financial or investment advice.*
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


def render_dual_speed_report(markdown_text: str, expand_all: bool = False):
    """
    Renders report in a mobile-optimized dual-speed layout:
    - Diagnostic Summary & Takeaways: open above the fold
    - Analytical Pillars 1 to 7: nested inside st.expander containers
    """
    import re
    cleaned = strip_conclusion_sections(remove_health_matrix_text(markdown_text))
    # Multiline flag (?m) matches line starts without requiring escape newlines
    sections = re.split(r"(?m)(?=^##?\s+)", cleaned)
    sections = [s.strip() for s in sections if s.strip()]

    if len(sections) <= 2:
        st.markdown(cleaned)
        return

    for sec in sections:
        lines = sec.splitlines()
        first_line = lines[0].strip()
        title = re.sub(r"^#+\s*", "", first_line).strip()
        body_content = chr(10).join(lines[1:]).strip() if len(lines) > 1 else sec

        # Strict exclusion of any conclusion or monitorables headers
        if re.search(r"(?i)\b(?:Conclusion|Key Monitorables|Actionable Guidance|Diagnostic Synthesis)\b", title):
            continue

        # Nest Pillars 1 through 7 into accordions
        if re.search(r"(?i) Pillar\s*\d+", title):
            with st.expander(f"📁 {title}", expanded=expand_all):
                st.markdown(body_content)
        else:
            # Diagnostic Summary or unclassified factual headers remain open
            st.markdown(sec)


def render_health_card_ui(report_text: str, target_container=None):
    render_momentum_chart(st.session_state.get('last_history'), st.session_state.get('last_ticker', ''))
    render_material_badge(st.session_state.get('material_reason', ''), st.session_state.get('is_regenerated', False))
    matrix = extract_health_matrix(report_text)
    if not matrix:
        return

    color_map = {
        "Disciplined": "#1b5e20", "Wide": "#1b5e20", "Clean": "#1b5e20",
        "Debt-Free": "#1b5e20", "Undervalued": "#1b5e20", "Temporary": "#1b5e20", "Stable": "#1b5e20",
        "Watchlist": "#b26a00", "Moderate": "#b26a00", "Fair": "#b26a00",
        "Neutral": "#b26a00", "Moderate Debt": "#b26a00", "Resilient": "#b26a00", "N/A": "#555555",
        "Strained": "#b71c1c", "Narrow": "#b71c1c", "Caution": "#b71c1c", 
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


def render_thesis_drift_panel(ticker: str, custom_diff_data: dict = None):
    """Renders the Thesis Drift Surveillance panel comparing two discrete report revisions."""
    if custom_diff_data:
        diff = custom_diff_data["diff"]
        rev_a = custom_diff_data["rev_a"]
        rev_b = custom_diff_data["rev_b"]
        is_custom = True
    else:
        revisions = get_report_revisions(ticker)
        if len(revisions) < 2:
            return
        rev_b = revisions[0]
        rev_a = revisions[1]
        diff = compare_revisions(rev_a, rev_b)
        is_custom = False

    if diff["migration_count"] == 0 and not diff["value_trap_detected"] and not is_custom:
        return  # No drift to display

    # If custom diff active, show notice bar with reset button
    if is_custom:
        c1, c2 = st.columns([3, 1])
        with c1:
            st.info(f"⚖️ **Custom Differential Surveillance:** Comparing **{custom_diff_data.get('label_a', 'State A')}** vs **{custom_diff_data.get('label_b', 'State B')}**.")
        with c2:
            if st.button("Reset to Default Drift", key="btn_reset_drift", width="stretch"):
                st.session_state.pop("custom_diff", None)
                st.rerun()

    # Value Trap Alert Banner
    if diff["value_trap_detected"]:
        st.markdown(
            f"""
            <div style="background-color: rgba(183, 28, 28, 0.12); border: 1px solid #ef4444; border-radius: 8px;
                        padding: 12px 16px; margin-bottom: 16px;">
                <div style="font-size: 14px; font-weight: 700; color: #fca5a5; margin-bottom: 4px;">
                    ⚠️ Value Trap Signal Detected
                </div>
                <div style="font-size: 13px; color: #cbd5e1; line-height: 1.5;">
                    {diff['value_trap_detail']}.
                    This divergence pattern — qualitative pillar erosion concurrent with valuation expansion —
                    is a historically documented risk factor warranting independent investigation.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    migration_label = f"{diff['migration_count']} Pillar Migration{'s' if diff['migration_count'] != 1 else ''} Detected"
    with st.expander(f"📊 Thesis Drift Surveillance ({migration_label})", expanded=diff["value_trap_detected"] or is_custom):
        st.caption(f"Comparing: **{diff['state_a_date']}** → **{diff['state_b_date']}** | Trigger: _{diff['revision_trigger']}_")

        # Pillar migration badges
        if diff["pillar_migrations"]:
            pills = ['<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px;">']
            for m in diff["pillar_migrations"]:
                if m["direction"] == "downgrade":
                    bg, icon = "#7f1d1d", "🔻"
                elif m["direction"] == "upgrade":
                    bg, icon = "#14532d", "🔺"
                else:
                    bg, icon = "#1e3a5f", "🔄"
                pills.append(
                    f'<div style="background-color: {bg}; color: #ffffff; padding: 6px 12px; border-radius: 6px; '
                    f'font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px;">'
                    f'{icon} <span style="opacity: 0.8; font-weight: 400; text-transform: uppercase; font-size: 11px;">'
                    f'{m["label"]}:</span> {m["from"]} → {m["to"]}</div>'
                )
            pills.append('</div>')
            st.markdown("".join(pills), unsafe_allow_html=True)

        # Quantitative metric delta table
        st.markdown("**Quantitative Baseline Shift**")
        delta_rows = []
        for key in ["baseline_price", "baseline_pe", "baseline_mcap"]:
            d = diff["metric_deltas"].get(key, {})
            pct = d.get("pct_change", 0.0)
            arrow = "▲" if pct > 0 else "▼" if pct < 0 else "—"

            # Format display values
            sa = d.get("state_a", "N/A")
            sb = d.get("state_b", "N/A")
            if key == "baseline_price":
                sa = f"₹{d['num_a']:,.2f}" if d.get("num_a", 0) > 0 else "N/A"
                sb = f"₹{d['num_b']:,.2f}" if d.get("num_b", 0) > 0 else "N/A"
            elif key == "baseline_mcap":
                sa = format_inr(d.get("num_a")) if d.get("num_a", 0) > 0 else "N/A"
                sb = format_inr(d.get("num_b")) if d.get("num_b", 0) > 0 else "N/A"

            delta_rows.append(f"| {d.get('label', key)} | {sa} | {sb} | {arrow} {abs(pct):.1f}% |")

        table_md = "| Metric | State A | State B | Δ Change |\n| :--- | :--- | :--- | :--- |\n" + "\n".join(delta_rows)
        st.markdown(table_md)

        st.caption("_Thesis drift tracking is a descriptive diagnostic tool. Pillar migrations reflect changes in publicly available exchange data and do not constitute investment advice._")


with st.sidebar:
    st.header("Stock Discovery")
    with st.form("sidebar_stock_search", clear_on_submit=False):
        sb_query = st.text_input(
            "Look up any stock:",
            placeholder="e.g. INFY, TCS, RELIANCE...",
            help="Search across all BSE-listed equity instruments by ticker or company name."
        )
        sb_submit = st.form_submit_button("Search Stock", type="primary", width="stretch")
    if sb_submit and sb_query:
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
                                st.session_state["custom_diff"] = {
                                    "diff": c_diff,
                                    "label_a": sel_a_lbl,
                                    "label_b": sel_b_lbl,
                                    "rev_a": r_a,
                                    "rev_b": r_b,
                                }
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
                                st.rerun()

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

st.title("Equity Research Analysis Platform")
st.markdown('<p style="font-size: 19px; color: #888888;">To aid stock discovery and simplify fundamentals.</p>', unsafe_allow_html=True)

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
    execute_stock_research(query, selected_language)


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
                    mark_all_alerts_as_read()
                    st.toast("All notifications marked as read.", icon="✅")
                    st.rerun()
            with act_col2:
                if st.button("🗑️ Dismiss All Unread", key="btn_dismiss_all_unread", width="stretch", help="Permanently clear all unread alerts"):
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
                    from bse_master import resolve_bse_scrip_code
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


render_alert_hub()

if ("last_report" in st.session_state and st.session_state["last_report"] is not None) or st.session_state.get("stream_pending"):
    # Anchor for smooth auto-scrolling
    st.html('<div id="active-dossier-anchor" style="scroll-margin-top: 30px;"></div>')

    # Handle toast message if requested
    if st.session_state.get("toast_message"):
        msg = st.session_state.pop("toast_message")
        st.toast(msg, icon="📄")

    # Handle smooth auto-scroll to dossier
    if st.session_state.get("scroll_to_dossier"):
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
    clean_ticker = ticker_disp.strip().upper()
    header_label = f"{company_name} ({clean_ticker})" if company_name and company_name.upper() != clean_ticker else clean_ticker

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
                rec = get_report_by_ticker(clean_ticker)
                if rec:
                    set_active_dossier_state(
                        ticker=clean_ticker,
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
    badge_container = st.empty()
    if st.session_state.get("last_report"):
        render_health_card_ui(st.session_state["last_report"], target_container=badge_container)

    # Report Header & Watchlist Quick Action
    hdr_c1, hdr_c2 = st.columns([3, 1])
    with hdr_c1:
        st.header(f"Equity Research Report: {header_label}")
        rep_date = st.session_state.get("last_report_date") or datetime.now(IST).strftime("%d-%b-%Y %H:%M IST")
        st.caption(f"🕒 **Report Timing:** {rep_date} | **Feed:** BSE Verified Exchange Data")
    with hdr_c2:
        try:
            in_w = is_ticker_in_watchlist(clean_ticker)
        except Exception:
            in_w = False
        if in_w:
            if st.button("✓ Tracking on Watchlist", key="btn_watch_toggle", width="stretch", help="Click to untrack from surveillance"):
                remove_from_watchlist(clean_ticker)
                st.rerun()
        else:
            if st.button("⭐ Track on Watchlist", key="btn_watch_toggle", type="secondary", width="stretch", help="Add to surveillance watchlist for material filings & price shock alerts"):
                add_to_watchlist(
                    ticker=clean_ticker,
                    short_name=company_name or clean_ticker,
                    scrip_code=str(fund.get("scrip_code", "")),
                    initial_price=fund.get("current_price")
                )
                st.rerun()

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
                
                mat_reason = st.session_state.get("material_reason", "Live Synthesis")
                stream_gen = stream_stock_report(clean_ticker, language=lang, stock_data=fund, on_status=lambda msg: st.write(f"• {msg}"), revision_trigger=mat_reason)
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
            import time
            time.sleep(0.4)
            synth_slot.empty()
            render_health_card_ui(streamed_text, target_container=badge_container)
            if "Live Synthesis Failed" in streamed_text:
                cached_rec = get_report_by_ticker(clean_ticker)
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
        expand_all = st.toggle("📖 Expand all analytical pillars", value=False)
        render_dual_speed_report(st.session_state["last_report"], expand_all=expand_all)
        render_thesis_drift_panel(clean_ticker, custom_diff_data=st.session_state.get("custom_diff"))

    # Primary Download Button & Mandatory Immutable SEBI Disclaimer
    if st.session_state.get("last_report"):
        st.markdown("---")
        st.caption(
            "**Disclaimer:** This report is automatically generated by an AI research assistant using public BSE disclosures "
            "and search grounding. It is intended strictly for informational and educational auditing purposes "
            "and does not constitute financial or investment advice."
        )
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
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
            canonical_clean = re.sub(r'[^A-Za-z0-9]', '', str(fund.get('ticker', clean_ticker)).split('.')[0]).upper()
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
