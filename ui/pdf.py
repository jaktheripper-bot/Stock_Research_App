"""Executive PDF Compilation Component for Stock Research App."""

import logging
import os
import re as re_mod
from datetime import datetime

from analyzer import (
    extract_health_matrix,
    remove_health_matrix_text,
    strip_conclusion_sections,
)
from db import IST, MANDATORY_SEBI_DISCLAIMER
from ui.charts import generate_pdf_chart_image

logger = logging.getLogger("equity_research.ui.pdf")

def build_pdf_dossier(rep_text: str, ticker: str, header_label: str, hist_df) -> bytes:
    """Compiles the report, 7-pillar scorecard, and static chart into an executive PDF binary."""
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
    footer_disclaimer = f"""
---
> **Statutory Safe Harbor & Regulatory Compliance Notice:**  
> *{MANDATORY_SEBI_DISCLAIMER}*
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
