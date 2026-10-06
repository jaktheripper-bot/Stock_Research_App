"""Executive PDF Compilation Component for Stock Research App."""

import logging
import os
import re as re_mod
from datetime import datetime

from analyzer import (
    extract_health_matrix,
    remove_health_matrix_text,
    strip_conclusion_sections,
    calculate_overall_health_score,
)
from db import IST, MANDATORY_SEBI_DISCLAIMER

logger = logging.getLogger("equity_research.core.reporting.pdf")


def generate_pdf_chart_image(df, ticker: str):
    """Generates a high-resolution static PNG of the 6-month momentum and 50-DMA for PDF embedding."""
    if df is None or not hasattr(df, "empty") or df.empty or "Date" not in df.columns or "Close" not in df.columns:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
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
        clean_name = re_mod.sub(r'[^a-zA-Z0-9]', '_', ticker)
        local_img_path = f"_pdf_chart_{clean_name}.png"
        plt.savefig(local_img_path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        return local_img_path
    except Exception as e:
        logger.warning(f"Could not generate PDF momentum chart for {ticker}: {e}")
        return None


def build_pdf_dossier(rep_text: str, ticker: str, header_label: str, hist_df=None, branding: dict = None) -> bytes:
    """Compiles the report, 7-pillar scorecard, and static chart into an executive PDF binary with optional firm branding."""
    from markdown_pdf import MarkdownPdf, Section
    clean_name = re_mod.sub(r'[^a-zA-Z0-9]', '_', ticker)
    matrix = extract_health_matrix(rep_text)
    clean_body = strip_conclusion_sections(remove_health_matrix_text(rep_text))
    chart_filename = generate_pdf_chart_image(hist_df, ticker) if hist_df is not None else None
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
a { color: #1d4ed8; text-decoration: underline; }
ol { margin-top: 6px; padding-left: 20px; }
ol li { margin-bottom: 4px; font-size: 8.5pt; color: #334155; line-height: 1.4; }
</style>
"""
    health = calculate_overall_health_score(matrix)
    posture_line = f"> **Aggregate Thesis Health:** **{health['status']}** ({health['total_score']}/21 pts • {health['percentage']}% quality alignment)\n" if health.get("total_score") else ""

    scorecard_md = f"""### Institutional 7-Pillar Health Scorecard
{posture_line}
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
    doc_receipt_id = f"SR-DOC-{clean_name.upper()}-{int(datetime.now().timestamp())}"

    # Custom Corporate / RIA Advisory Branding Header
    if branding and branding.get("firm_name"):
        firm = str(branding["firm_name"]).strip()
        reg = str(branding.get("advisor_reg_no") or "Registered Financial Intermediary").strip()
        prep = str(branding.get("prepared_for") or "Private Client Wealth Portfolio").strip()
        header_branding = f"""# Institutional Equity Research Dossier: {header_label}
> **Advisory Desk:** **{firm}** | **Registration No:** `{reg}`  
> **Prepared For:** {prep} | **Document ID:** `{doc_receipt_id}`  
> **Compilation Timestamp:** {now_str} | **Licensing Tier:** Corporate Advisory Deliverable  
> **Data Provenance:** Statutory Exchange Disclosures (BSE/NSE), Licensed Vendor Feeds, and Official AMFI/RBI Repositories.
"""
    else:
        header_branding = f"""# Institutional Equity Research Dossier: {header_label}
> **Platform:** [Stock Research AI](https://stockresearch.app) | **Document ID:** `{doc_receipt_id}`  
> **Compilation Timestamp:** {now_str} | **Licensing Tier:** Standard Subscriber Deliverable  
> **Data Provenance:** Statutory Exchange Disclosures (BSE/NSE), Commercial Vendor Feeds (EODHD), and AMFI/RBI Benchmarks.
"""

    custom_disc = f"\n> \n> **Advisory Firm Disclosures ({branding.get('firm_name')}):**  \n> *{branding.get('custom_disclaimer')}*" if branding and branding.get("custom_disclaimer") else ""

    footer_disclaimer = f"""
---
### Statutory Regulatory Disclaimers & Data Provenance Notice
> **SEBI Safe-Harbor (Section 2(u) RA Regulations 2014):**  
> *{MANDATORY_SEBI_DISCLAIMER}*  
> 
> **Data Grounding & Commercial Provenance:**  
> Financial multiples, price series, and qualitative thesis assessments are synthesized algorithmically from public exchange filings and licensed commercial data feeds. Figures represent delayed or End-of-Day historical points and are not suitable for high-frequency or real-time trade execution. Past performance does not guarantee future outcomes. Independent verification with primary exchange filings is recommended.{custom_disc}
> 
> *Generated by Stock Research App • SAC Code: 998314 • Document Tracking ID: {doc_receipt_id}*
"""
    full_md = f"{embedded_style}\n{header_branding}\n{scorecard_md}\n{chart_md}\n---\n\n{clean_body}\n{footer_disclaimer}"
    
    out_name = f"_tmp_doc_{clean_name}.pdf"
    try:
        pdf = MarkdownPdf(toc_level=0)
        pdf.add_section(Section(full_md, root="."))
        pdf.save(out_name)
        with open(out_name, "rb") as f:
            pdf_bytes = f.read()
        return pdf_bytes
    except Exception as e:
        logger.error(f"Failed to generate PDF dossier for {ticker}: {e}")
        raise
    finally:
        if os.path.exists(out_name):
            try:
                os.unlink(out_name)
            except OSError:
                pass
        if chart_filename and os.path.exists(chart_filename):
            try:
                os.unlink(chart_filename)
            except OSError:
                pass


def generate_report_pdf(ticker: str, rep_text: str, header_label: str = None, hist_df=None, branding: dict = None) -> bytes:
    """Convenience wrapper for headless / web report PDF export with optional advisory firm branding."""
    label = header_label or f"{ticker} Institutional Research Dossier"
    return build_pdf_dossier(rep_text, ticker, label, hist_df=hist_df, branding=branding)

