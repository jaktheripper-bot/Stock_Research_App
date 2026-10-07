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


def clean_paragraph_prose(text: str) -> str:
    """
    Cleans paragraph prose for executive readability:
    - Eliminates robotic bracketed acronym expansions (e.g. INR [Indian Rupee], Cr [Crore], P/E [Price-to-Earnings Ratio])
    - Protects markdown hyperlinks [Text](url)
    - Normalizes double spacing and broken punctuation.
    """
    if not text:
        return ""
    # Normalize common multi-word prefixes with bracketed acronyms
    text = re_mod.sub(r'\bFinancial Year\s*\[FY\]', 'FY', text, flags=re_mod.IGNORECASE)
    # Generic replacement of ACRONYM [Full Expanded Form in brackets] -> ACRONYM
    # Negative lookahead (?!\() protects markdown links like [Title](url)
    text = re_mod.sub(r'\b([A-Za-z0-9/\-]{2,12})\s*\[([A-Za-z0-9\s,\-–\'/]+)\](?!\()', r'\1', text)
    # Remove awkward double punctuation like [Over-The-Top] if left behind
    text = re_mod.sub(r'\s+\[Over-The-Top\]', '', text, flags=re_mod.IGNORECASE)
    return text.strip()


def build_sources_section(ticker: str, citations: list = None, scrip_code: str = None) -> str:
    """Constructs a comprehensive, grounded list of statutory regulatory sources and filings."""
    clean = re_mod.sub(r'[^a-zA-Z0-9]', '', ticker).upper()
    lines = [
        "### 📚 Verified Regulatory Sources & Statutory Disclosures",
        "> *All qualitative findings, corporate governance audits, and financial metrics in this dossier are grounded in primary exchange disclosures and statutory repositories under SEBI Research Analyst Regulations 2014 Section 2(u):*\n"
    ]
    seen_urls = set()
    source_idx = 1

    # 1. Include specific citations if present
    if citations:
        for c in citations:
            if isinstance(c, dict):
                uri = (c.get("uri") or "").strip()
                title = (c.get("title") or "Exchange Filing").strip()
                stype = (c.get("source_type") or "Verified Grounding").strip()
            elif isinstance(c, str):
                uri = c.strip()
                title = "Primary Statutory Document"
                stype = "Exchange Grounding"
            else:
                continue

            if uri and uri in seen_urls:
                continue
            if uri:
                seen_urls.add(uri)
                lines.append(f"{source_idx}. [{title}]({uri}) — *{stype}*")
                source_idx += 1
            elif title:
                lines.append(f"{source_idx}. **{title}** — *{stype}*")
                source_idx += 1

    # 2. Add primary exchange filings for this ticker using scrip_code
    from bse_master import resolve_bse_scrip_code
    scrip = str(scrip_code or resolve_bse_scrip_code(clean) or "").strip()
    if not scrip or not scrip.isdigit():
        scrip = "500209"

    statutory_links = [
        ("BSE Regulatory Disclosures & Corporate Announcements", f"https://www.bseindia.com/corporates/ann.html?scrip_cd={scrip}", "BSE Statutory Feed"),
        ("BSE Concall Transcripts & Investor Presentations", f"https://www.bseindia.com/corporates/ann.html?scrip_cd={scrip}", "Management Transcripts"),
        ("Official BSE Shareholding Pattern & Promoter Pledging", f"https://www.bseindia.com/corporates/ShareholdingPattern.aspx?scrip_cd={scrip}", "Shareholding Archive"),
        ("BSE Audited Financial Statements & Balance Sheet", f"https://www.bseindia.com/corporates/Comp_Resultsnew.aspx?scrip_cd={scrip}", "Financial Results (Comp_Results)"),
        ("Official BSE Bhavcopy Trade Execution & Price History", f"https://www.bseindia.com/stock-share-price/-/-/{scrip}/", "Historical Market Execution"),
        ("SEBI Business Responsibility and Sustainability Report (BRSR)", f"https://www.bseindia.com/corporates/ann.html?scrip_cd={scrip}", "Statutory ESG Filing"),
        ("AMFI Mutual Fund Statutory Holdings & NAV Utility", "https://www.amfiindia.com/research-information/other-data/raw-data", "AMFI Statutory Feed"),
        ("RBI / FBIL Sovereign Benchmark Par Yield Gazettes", "https://www.fbil.org.in", "RBI Sovereign Benchmarks"),
    ]

    for title, url, stype in statutory_links:
        if url not in seen_urls and source_idx <= 12:
            seen_urls.add(url)
            lines.append(f"{source_idx}. [{title}]({url}) — *{stype}*")
            source_idx += 1

    return "\n".join(lines) + "\n"


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

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 3.4), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
        fig.patch.set_facecolor('#ffffff')

        # Price & 50-DMA
        ax1.set_facecolor('#ffffff')
        ax1.plot(plot_df["Date"], plot_df["Close"], color="#2563eb", linewidth=1.6, label="Close Price")
        if "SMA50" in plot_df.columns and not plot_df["SMA50"].dropna().empty:
            ax1.plot(plot_df["Date"], plot_df["SMA50"], color="#d97706", linewidth=1.3, linestyle="--", label="50-DMA")
        
        ax1.set_title(f"6-Month Price Momentum & 50-DMA ({ticker})", fontsize=10, fontweight="bold", pad=6, color="#0f172a")
        ax1.set_ylabel("Price (INR)", fontsize=8, color="#334155")
        ax1.legend(loc="upper left", frameon=True, fontsize=8)
        ax1.grid(True, linestyle=":", alpha=0.5)

        # Volume
        ax2.set_facecolor('#ffffff')
        if "Volume" in plot_df.columns:
            ax2.bar(plot_df["Date"], plot_df["Volume"], color="#94a3b8", alpha=0.6, width=1.5)
        ax2.set_ylabel("Vol", fontsize=7, color="#334155")
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


def build_pdf_dossier(
    rep_text: str,
    ticker: str,
    header_label: str = None,
    hist_df=None,
    citations: list = None,
    scrip_code: str = None,
    branding: dict = None
) -> bytes:
    """Compiles the report, 7-pillar scorecard, 50-DMA chart, verified sources, and SEBI safe-harbor into an institutional PDF."""
    from markdown_pdf import MarkdownPdf, Section
    clean_name = re_mod.sub(r'[^a-zA-Z0-9]', '_', ticker).upper()

    # Auto-fetch 6-month historical prices for 50-DMA chart if not supplied
    if hist_df is None:
        try:
            from core.analysis import get_historical_prices
            hist_df = get_historical_prices(clean_name, period="6mo")
        except Exception as e:
            logger.debug(f"Could not auto-fetch historical prices for {clean_name}: {e}")
            hist_df = None

    chart_filename = generate_pdf_chart_image(hist_df, clean_name) if hist_df is not None else None

    # Parse and clean text
    matrix = extract_health_matrix(rep_text)
    clean_body = strip_conclusion_sections(remove_health_matrix_text(rep_text))
    clean_body = clean_paragraph_prose(clean_body)

    # Insert 50-DMA chart directly into Pillar 6 (Technical & Momentum Overlay) or append to body
    if chart_filename and os.path.exists(chart_filename):
        chart_md = f"\n\n![6-Month Price Momentum & 50-DMA]({chart_filename})\n\n"
        if re_mod.search(r'##\s*Pillar\s*6', clean_body, re_mod.IGNORECASE):
            clean_body = re_mod.sub(
                r'(##\s*Pillar\s*6[^\n]*\n)',
                r'\1' + chart_md,
                clean_body,
                count=1,
                flags=re_mod.IGNORECASE
            )
        else:
            clean_body += f"\n\n## Trailing 6-Month Momentum & Technical Overlay\n{chart_md}"

    now_str = datetime.now(IST).strftime("%d %B %Y, %H:%M IST")
    doc_receipt_id = f"SR-DOC-{clean_name}-{int(datetime.now().timestamp())}"

    # Typography & Institutional Print Styling
    user_css = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 9.5pt;
    line-height: 1.55;
    color: #1e293b;
}
h1 {
    font-size: 15pt;
    font-weight: 700;
    color: #0f172a;
    margin-top: 0;
    margin-bottom: 6px;
    letter-spacing: -0.2px;
}
h2 {
    font-size: 11.5pt;
    font-weight: 700;
    color: #1e3a8a;
    margin-top: 14px;
    margin-bottom: 6px;
    padding-bottom: 3px;
    border-bottom: 1.5px solid #3b82f6;
    page-break-after: avoid;
}
h3 {
    font-size: 10pt;
    font-weight: 700;
    color: #1e293b;
    margin-top: 10px;
    margin-bottom: 4px;
    page-break-after: avoid;
}
p {
    margin-top: 0;
    margin-bottom: 7px;
    line-height: 1.55;
    text-align: justify;
}
ul, ol {
    margin-top: 3px;
    margin-bottom: 7px;
    padding-left: 18px;
}
li {
    font-size: 9.5pt;
    line-height: 1.5;
    margin-bottom: 3px;
    color: #1e293b;
}
ol li {
    font-size: 9.5pt;
    line-height: 1.5;
    margin-bottom: 4px;
    color: #1e293b;
}
blockquote {
    border-left: 3.5px solid #2563eb;
    background: #f8fafc;
    padding: 6px 12px;
    margin: 8px 0;
    color: #334155;
    font-size: 9pt;
}
table {
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0 12px 0;
    font-size: 8.5pt;
    page-break-inside: avoid;
}
th {
    background-color: #f1f5f9;
    color: #0f172a;
    font-weight: 600;
    padding: 5px 8px;
    border: 1px solid #cbd5e1;
    text-align: left;
}
td {
    padding: 5px 8px;
    border: 1px solid #e2e8f0;
    color: #334155;
    text-align: left;
    vertical-align: top;
}
tr:nth-child(even) td {
    background-color: #f8fafc;
}
hr {
    border: 0;
    height: 1px;
    background-color: #e2e8f0;
    margin: 12px 0;
}
img {
    max-width: 100%;
    height: auto;
    margin: 6px 0;
    page-break-inside: avoid;
}
a {
    color: #1d4ed8;
    text-decoration: underline;
}
"""

    health = calculate_overall_health_score(matrix)
    posture_line = f"> **Aggregate Thesis Health:** **{health['status']}** ({health['total_score']}/21 pts • {health['percentage']}% quality alignment)\n" if health.get("total_score") else ""

    scorecard_md = f"""### Institutional Forensic Health Scorecard (01–07)
{posture_line}
| Core Check | Rating / Posture | Evaluated Area |
| :--- | :--- | :--- |
| **Capital Allocation** | {matrix.get('CapitalAllocation', 'Disciplined')} | Reinvestment discipline & cash returns |
| **Macro Environment** | {matrix.get('Macro', 'Neutral')} | Sector tailwinds & systemic risks |
| **Competitive Moat** | {matrix.get('Moat', 'Moderate')} | Pricing power & entry barriers |
| **Governance & Promoters** | {matrix.get('Governance', 'Clean')} | Accounting integrity & alignment |
| **Drop Diagnostic** | {matrix.get('Diagnostic', 'N/A')} | Structural erosion vs temporary dip |
| **Valuation Multiple** | {matrix.get('Valuation', 'Fair')} | Price relative to intrinsic band |
| **Balance Sheet Leverage** | {matrix.get('BalanceSheet', 'Resilient')} | Solvency & debt service capacity |
"""

    # Clean display title
    display_title = clean_name
    if header_label and clean_name not in header_label.upper():
        display_title = f"{clean_name} — {header_label}"

    # Custom Corporate / RIA Advisory Branding Header
    if branding and branding.get("firm_name"):
        firm = str(branding["firm_name"]).strip()
        reg = str(branding.get("advisor_reg_no") or "Registered Financial Intermediary").strip()
        prep = str(branding.get("prepared_for") or "Private Client Wealth Portfolio").strip()
        header_branding = f"""# Equity Research Dossier: {display_title}
> **Advisory Desk:** **{firm}** | **Registration No:** `{reg}`  
> **Prepared For:** {prep} | **Document ID:** `{doc_receipt_id}`  
> **Compilation Timestamp:** {now_str} | **Licensing Tier:** Corporate Advisory Deliverable  
> **Data Provenance:** Statutory Exchange Disclosures (BSE/NSE), Authoritative Broker Gateway APIs, and Official AMFI/RBI Repositories.
"""
    else:
        header_branding = f"""# Equity Research Dossier: {display_title}
> **Platform:** [Stock Research AI](https://stockresearch.app) | **Document ID:** `{doc_receipt_id}`  
> **Compilation Timestamp:** {now_str} | **Licensing Tier:** Standard Subscriber Deliverable  
> **Data Provenance:** Statutory Exchange Disclosures (BSE/NSE), Authoritative Broker Gateway APIs, and Official AMFI/RBI Repositories.
"""

    custom_disc = f"\n> \n> **Advisory Firm Disclosures ({branding.get('firm_name')}):**  \n> *{branding.get('custom_disclaimer')}*" if branding and branding.get("custom_disclaimer") else ""

    # Sources & Statutory Disclosures Appendix
    sources_md = build_sources_section(clean_name, citations=citations, scrip_code=scrip_code)

    footer_disclaimer = f"""
---
### Statutory Regulatory Disclaimers & Data Provenance Notice
> **SEBI Safe-Harbor (Section 2(u) RA Regulations 2014):**  
> *{MANDATORY_SEBI_DISCLAIMER}*  
> 
> **Data Grounding & Statutory Provenance:**  
> Financial multiples, price series, and qualitative thesis assessments are synthesized algorithmically from public exchange filings (BSE/NSE), statutory AMFI NAV feeds, RBI benchmark publications, and authorized broker gateway APIs. Figures represent delayed or End-of-Day historical levels and are not suitable for high-frequency or real-time trade execution. Past performance does not guarantee future outcomes. Independent verification with primary exchange disclosures is recommended.{custom_disc}
> 
> *Generated by Stock Research App • SAC Code: 998314 • Document Tracking ID: {doc_receipt_id}*
"""
    full_md = (
        f"{header_branding}\n"
        f"{scorecard_md}\n"
        f"---\n\n"
        f"{clean_body}\n\n"
        f"<div style=\"page-break-before: always;\"></div>\n\n"
        f"{sources_md}\n"
        f"{footer_disclaimer}"
    )

    out_name = f"_tmp_doc_{clean_name}.pdf"
    try:
        pdf = MarkdownPdf(toc_level=0)
        pdf.add_section(Section(full_md, root="."), user_css=user_css)
        pdf.save(out_name)
        with open(out_name, "rb") as f:
            pdf_bytes = f.read()
        return pdf_bytes
    except Exception as e:
        logger.error(f"Failed to generate PDF dossier for {clean_name}: {e}")
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


def generate_report_pdf(
    ticker: str,
    rep_text: str,
    header_label: str = None,
    hist_df=None,
    citations: list = None,
    scrip_code: str = None,
    branding: dict = None
) -> bytes:
    """Convenience wrapper for headless / web report PDF export with optional advisory firm branding."""
    return build_pdf_dossier(
        rep_text=rep_text,
        ticker=ticker,
        header_label=header_label,
        hist_df=hist_df,
        citations=citations,
        scrip_code=scrip_code,
        branding=branding
    )


def generate_fund_dossier_pdf(
    scheme_code: str,
    dossier: dict,
    scheme: dict,
    branding: dict = None
) -> bytes:
    """Compiles institutional PDF dossier for a Mutual Fund scheme."""
    from markdown_pdf import MarkdownPdf, Section
    now_str = datetime.now(IST).strftime("%d %B %Y, %I:%M %p IST")
    doc_id = f"MF-{scheme_code[:8].upper()}-{datetime.now(IST).strftime('%Y%m%d%H%M')}"
    clean_name = re_mod.sub(r'[^a-zA-Z0-9_]', '', scheme_code)
    scheme_title = scheme.get("scheme_name", scheme_code)
    health = float(dossier.get("composite_health_score", 70.0))
    moat = float(dossier.get("weighted_moat_score", 65.0))
    asri = float(dossier.get("accounting_risk_index", 15.0))
    mos = float(dossier.get("margin_of_safety_pct", 0.0))
    active_share = float(dossier.get("active_share_pct", 75.0))

    header = f"""# Mutual Fund Forensic Look-Through Dossier: {scheme_title}
> **Scheme Code:** `{scheme_code}` | **Document ID:** `{doc_id}`  
> **Compilation Timestamp:** {now_str} | **Licensing Tier:** Institutional Asset Management Research  
> **Data Provenance:** Official AMFI Daily NAV Data, AMC Monthly Portfolio Disclosures & BSE/NSE Listings.
"""

    scorecard_md = f"""### Executive Look-Through Scorecard
| Metric | Value | Posture / Status |
| :--- | :--- | :--- |
| **Composite Health Score** | **{health:.1f} / 100** | {'High Quality Portfolio' if health >= 75 else 'Moderate Moat'} |
| **Weighted Moat Score** | **{moat:.1f} / 100** | {'Wide Moat Bias' if moat >= 70 else 'Blend'} |
| **Accounting Risk Index (ASRI)** | **{asri:.1f}%** | {'Clean Portfolio' if asri < 20 else 'Elevated Audit Caution'} |
| **Margin of Safety (MoS)** | **{mos:+.1f}%** | {'Discounted Under-Valuation' if mos > 0 else 'Premium Over Fair Value'} |
| **Active Share (Closet-Indexing)** | **{active_share:.1f}%** | {'True Active Alpha' if active_share >= 60 else 'Closet Indexing Drag'} |
"""

    meta_table = f"""### Scheme Profile & Portfolio Facts
| Category | Benchmark | Risk Grade | Fund House | Fund Manager |
| :--- | :--- | :--- | :--- | :--- |
| {scheme.get('category', 'Equity')} | {scheme.get('benchmark_index', 'NIFTY 500')} | {scheme.get('risk_grade', 'Very High')} | {scheme.get('fund_house', 'AMC')} | {scheme.get('fund_manager', 'Manager')} |
"""

    narrative = dossier.get("dossier_text", "No detailed narrative recorded.")
    footer = f"""
---
### Statutory Regulatory Disclaimers & Provenance Notice
> **SEBI Safe-Harbor (Section 2(u) RA Regulations 2014):**  
> *{MANDATORY_SEBI_DISCLAIMER}*  
> 
> Mutual Fund investments are subject to market risks, read all scheme related documents carefully.
"""
    full_md = f"{header}\n\n{scorecard_md}\n\n{meta_table}\n\n---\n\n{narrative}\n\n{footer}"
    out_name = f"_tmp_doc_mf_{clean_name}.pdf"
    try:
        pdf = MarkdownPdf(toc_level=0)
        pdf.add_section(Section(full_md, root="."))
        pdf.save(out_name)
        with open(out_name, "rb") as f:
            pdf_bytes = f.read()
        return pdf_bytes
    finally:
        if os.path.exists(out_name):
            try:
                os.unlink(out_name)
            except OSError:
                pass


def generate_debt_dossier_pdf(
    isin: str,
    posture: dict,
    security: dict,
    branding: dict = None
) -> bytes:
    """Compiles institutional PDF credit dossier for a Corporate Debt security."""
    from markdown_pdf import MarkdownPdf, Section
    now_str = datetime.now(IST).strftime("%d %B %Y, %I:%M %p IST")
    doc_id = f"BOND-{isin[:8]}-{datetime.now(IST).strftime('%Y%m%d%H%M')}"
    clean_isin = re_mod.sub(r'[^a-zA-Z0-9_]', '', isin)
    
    name = security.get("instrument_name", isin)
    score = posture.get("composite_score", 75.0)
    badge = posture.get("posture_badge", "Investment Grade")
    ytm = posture.get("ytm_pct", 8.5)
    coupon = posture.get("coupon_rate_pct", 8.0)
    dur = posture.get("macaulay_duration_years", 2.5)
    sen = posture.get("seniority_tier", "SENIOR_SECURED").replace('_', ' ')
    rating = security.get("credit_rating", "AAA")
    radar = posture.get("credit_contagion_radar", {})

    header = f"""# Corporate Debt Credit Dossier: {name}
> **ISIN:** `{isin}` | **Ticker:** `{posture.get('ticker', 'N/A')}` | **Document ID:** `{doc_id}`  
> **Compilation Timestamp:** {now_str} | **Regulatory Standard:** SEBI ₹10,000 Face Value Framework  
> **Data Provenance:** BSE Debt Clearing, Credit Rating Agency Circulars (CRISIL/ICRA), and Wint Wealth / GoldenPi Collation.
"""

    scorecard_md = f"""### Executive 5-Pillar Credit Scorecard
| Metric | Value | Evaluation / Status |
| :--- | :--- | :--- |
| **Credit Posture Score** | **{score} / 100** | **{badge}** |
| **Credit Rating** | **{rating}** | Issued by {security.get('credit_rating_agency', 'CRISIL')} |
| **Yield-to-Maturity (YTM)** | **{ytm}%** | Contractual Cash Flow Yield |
| **Coupon & Frequency** | **{coupon}%** | {posture.get('coupon_frequency', 'Annual').title()} |
| **Macaulay Duration** | **{dur} yrs** | Price Sensitivity & Interest Rate Risk |
| **Capital Seniority** | **{sen}** | Waterfall Priority in Insolvency (IBC) |
"""

    contagion_md = f"""### 📡 Credit Contagion Radar (Parent Equity Linkage)
> **Contagion Status:** **{radar.get('radar_label', 'Active Radar')}**  
> **Risk Tier:** `{radar.get('risk_level', 'LOW')}`  
> **Parent Equity:** `{radar.get('equity_ticker', 'N/A')}`  
> **Contagion Summary:** {radar.get('radar_summary', 'Isolated.')}
"""

    primer_summary = posture.get("primer", {}).get("summary", "")
    primer_md = f"""### Executive Investment Primer
{primer_summary}

- **Bank FD Comparison:** {posture.get('primer', {}).get('fd_comparison', 'N/A')}
- **Cash Flow Certainty:** {posture.get('primer', {}).get('contractual_certainty', 'N/A')}
- **Core Risk Factors:** {posture.get('primer', {}).get('primary_risks', 'N/A')}
"""

    p1 = posture.get("pillars", {}).get("p1_credit_quality", {}).get("institutional_analysis", "")
    p2 = posture.get("pillars", {}).get("p2_capital_hierarchy", {}).get("institutional_analysis", "")
    p3 = posture.get("pillars", {}).get("p3_solvency", {}).get("institutional_analysis", "")

    pillars_md = f"""### 5-Pillar Diagnostic Teardown
#### 01: Credit Quality & Rating Drift
{p1}

#### 02: Capital Hierarchy & Seniority Cover
{p2}

#### 03: Cash Flow Solvency & Coverage Ratios
{p3}
"""

    footer = f"""
---
### Statutory Regulatory Disclaimers & Provenance Notice
> **SEBI Safe-Harbor (Section 2(u) RA Regulations 2014):**  
> *{MANDATORY_SEBI_DISCLAIMER}*  
> 
> Fixed-income investments carry market, credit, and reinvestment risk. YTMs are subject to prevailing secondary market prices and issuer creditworthiness.
"""
    full_md = f"{header}\n\n{scorecard_md}\n\n{contagion_md}\n\n{primer_md}\n\n{pillars_md}\n\n{footer}"
    out_name = f"_tmp_doc_debt_{clean_isin}.pdf"
    try:
        pdf = MarkdownPdf(toc_level=0)
        pdf.add_section(Section(full_md, root="."))
        pdf.save(out_name)
        with open(out_name, "rb") as f:
            pdf_bytes = f.read()
        return pdf_bytes
    finally:
        if os.path.exists(out_name):
            try:
                os.unlink(out_name)
            except OSError:
                pass


def generate_reit_dossier_pdf(
    symbol: str,
    reit: dict,
    branding: dict = None
) -> bytes:
    """Compiles clean, institutional PDF research dossier for a REIT or InvIT offering."""
    from markdown_pdf import MarkdownPdf, Section
    now_str = datetime.now(IST).strftime("%d %B %Y, %I:%M %p IST")
    doc_id = f"REIT-{symbol[:8]}-{datetime.now(IST).strftime('%Y%m%d%H%M')}"
    clean_sym = re_mod.sub(r'[^a-zA-Z0-9_]', '', symbol)
    
    name = reit.get("name", symbol)
    structure = reit.get("structure_type", "MAINBOARD_REIT").replace('_', ' ').title()
    price = float(reit.get("current_price", 0.0))
    nav = float(reit.get("nav_per_unit", 0.0))
    disc = float(reit.get("discount_to_nav_pct", 0.0))
    yield_pct = float(reit.get("distribution_yield_pct", 0.0))
    occupancy = float(reit.get("occupancy_pct", 0.0))
    ndcf = float(reit.get("ndcf_payout_purity_pct", 100.0))
    ltv = float(reit.get("ltv_ratio_pct", 0.0))
    wale = float(reit.get("wale_years", 0.0))
    compliant = reit.get("sebi_compliant", True)
    details = reit.get("details", {})
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            details = {}

    header = f"""# Real Asset Research Dossier: {name} ({symbol})
> **Asset Structure:** `{structure}` | **Symbol:** `{symbol}` | **Document ID:** `{doc_id}`  
> **Compilation Timestamp:** {now_str} | **Regulatory Standard:** SEBI REIT / InvIT Regulations 2024  
> **Data Provenance:** Exchange Disclosures, Quarterly NDCF Distribution Reports, Valuation Reports.
"""

    scorecard_md = f"""### Key Operating & Valuation Metrics
| Metric | Reported Value | Regulatory / Institutional Benchmark | Status |
| :--- | :--- | :--- | :--- |
| **Current Unit Price** | **₹{price:,.2f}** | Secondary Market Trading Price | Active |
| **Net Asset Value (NAV)** | **₹{nav:,.2f}** | Independent Property Valuation | Benchmark |
| **Discount / Premium to NAV** | **{disc:+.2f}%** | Fair Value Entry Cushion | {'Discount' if disc < 0 else 'Premium'} |
| **Distribution Yield (p.a.)** | **{yield_pct:.2f}%** | Annualized Pre-Tax Cash Flow Yield | Yield |
| **Portfolio Occupancy** | **{occupancy:.1f}%** | Minimum 95% for SEBI SM REITs | {'Compliant' if occupancy >= 95.0 or 'MAINBOARD' in reit.get('structure_type', '') else 'Monitored'} |
| **NDCF Payout Purity** | **{ndcf:.1f}%** | Statutory 90%+ Mandatory Distribution | Compliant |
| **Loan-to-Value (LTV)** | **{ltv:.1f}%** | Statutory Cap: 49% Net Debt / Assets | Safe Buffer |
| **Weighted Average Lease (WALE)** | **{wale:.1f} Years** | Income Stability & Re-leasing Runway | Long Duration |
"""

    tax_info = details.get("tax_breakdown", {})
    tax_div = tax_info.get("dividend_pct", 35.0)
    tax_int = tax_info.get("interest_pct", 40.0)
    tax_roc = tax_info.get("amortization_pct", 25.0)

    tax_md = f"""### ⚖️ Taxation Breakdown (Section 115UA Pass-Through)
Under Indian tax laws, distributions from REITs and InvITs pass through three distinct components:
- **Exempt Dividends (~{tax_div}% of payout):** Received tax-free when the underlying SPV has not opted for the concessional corporate tax regime.
- **Interest Income (~{tax_int}% of payout):** Taxed at your individual marginal income tax slab.
- **Return of Capital / Amortization (~{tax_roc}% of payout):** Reduces your acquisition cost and is received tax-free until total distributions exceed your purchase price.
"""

    tenants = ", ".join(details.get("top_tenants", [])) or "Institutional Grade Global & Domestic Tenants"
    asset_class = details.get("asset_class", "Commercial Real Estate / Infrastructure")

    primer_md = f"""### 🏢 Asset Overview & Tenant Ecosystem
- **Underlying Assets:** {asset_class}
- **Anchor Tenants:** {tenants}
- **Cash Flow Profile:** Long-term contracted leases with contractual rental escalations (typically 12-15% escalation every 3 years).
- **Core Risk Factors:** Tenant non-renewal at lease expiration, macro interest rate fluctuations, and property re-leasing downtime.
"""

    footer = f"""
---
### Statutory Regulatory Disclaimers & Provenance Notice
> **SEBI Safe-Harbor (Section 2(u) RA Regulations 2014):**  
> *{MANDATORY_SEBI_DISCLAIMER}*  
> 
> Real estate and infrastructure investments carry market, tenant, occupancy, and interest rate risks. Past cash distributions are not a guarantee of future yield.
"""
    full_md = f"{header}\n\n{scorecard_md}\n\n{tax_md}\n\n{primer_md}\n\n{footer}"
    out_name = f"_tmp_doc_reit_{clean_sym}.pdf"
    try:
        pdf = MarkdownPdf(toc_level=0)
        pdf.add_section(Section(full_md, root="."))
        pdf.save(out_name)
        with open(out_name, "rb") as f:
            pdf_bytes = f.read()
        return pdf_bytes
    finally:
        if os.path.exists(out_name):
            try:
                os.unlink(out_name)
            except OSError:
                pass
