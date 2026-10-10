"""Report parsing, 7-pillar health matrix extraction, regulatory sanitization, citations formatting, and differential comparison."""

import re
import logging

logger = logging.getLogger("equity_research.core.analysis.parser")

def extract_health_matrix(report_text: str) -> dict:
    """
    Parses the 7-Pillar Health Matrix from report text.
    Case-insensitive, agnostic to bullet markers (*, -, •), numbered lists, colons, and hyphens.
    """
    if not report_text or not isinstance(report_text, str):
        return {}

    clean = report_text.replace("\xa0", " ").replace("–", "-").replace("—", "-")

    matrix = {
        "Macro": "Neutral", "Moat": "Moderate", "Governance": "Clean",
        "Diagnostic": "N/A", "Valuation": "Fair", "BalanceSheet": "Resilient", "CapitalAllocation": "Disciplined"
    }

    patterns = {
        "Macro": r"(?i)(?:[-*•]|\d+\.)?\s*Macro\s*[:\-]?\s*\[?\s*(Stable|Headwinds|Neutral)\s*\]?",
        "Moat": r"(?i)(?:[-*•]|\d+\.)?\s*Moat\s*[:\-]?\s*\[?\s*(Wide|Moderate|Narrow)\s*\]?",
        "Governance": r"(?i)(?:[-*•]|\d+\.)?\s*Governance\s*[:\-]?\s*\[?\s*(Clean|Caution|High Risk)\s*\]?",
        "Diagnostic": r"(?i)(?:[-*•]|\d+\.)?\s*Diagnostic\s*[:\-]?\s*\[?\s*(Temporary|Structural|Neutral|N/A)\s*\]?",
        "Valuation": r"(?i)(?:[-*•]|\d+\.)?\s*Valuation\s*[:\-]?\s*\[?\s*(Undervalued|Fair|Stretched|Loss-Making)\s*\]?",
        "BalanceSheet": r"(?i)(?:[-*•]|\d+\.)?\s*Balance\s*Sheet\s*[:\-]?\s*\[?\s*(Debt-Free|Moderate Debt|High Debt|Resilient)\s*\]?",
        "CapitalAllocation": r"(?i)(?:[-*•]|\d+\.)?\s*Capital\s*Allocation\s*[:\-]?\s*\[?\s*(Disciplined|Moderate|Strained)\s*\]?"
    }

    for key, pat in patterns.items():
        match = re.search(pat, clean)
        if match:
            matrix[key] = match.group(1).strip().title()

    if matrix.get("CapitalAllocation") == "Disciplined":
        ca_match = re.search(r"(?i)Capital\s*Allocation\s*[:\-]?\s*\[?\s*(Disciplined|Moderate|Strained)\s*\]?", clean)
        if ca_match:
            matrix["CapitalAllocation"] = ca_match.group(1).strip().title()

    return matrix

def remove_health_matrix_text(text: str) -> str:
    """Removes redundant markdown Health Matrix bullet blocks from presentation."""
    if not text or not isinstance(text, str):
        return ""
    cleaned = re.sub(
        r'(?i)#*\s*Health Matrix\s*\n+(?:[ \t]*[-*•\d\.]+\s+[^\n]+\n*)+',
        '',
        text
    )
    return cleaned.strip()

def strip_conclusion_sections(text: str) -> str:
    """
    Strips conclusion, monitorables, recommendations, and actionable guidance sections
    for strict SEBI Safe Harbor compliance.
    """
    if not text or not isinstance(text, str):
        return ""
    conclusion_pattern = r'(?im)^\s*#*\s*(?:\d+[\.:\)]\s*)?(?:Conclusion|Key Monitorables|Actionable Guidance|Diagnostic Synthesis|Recommendation|Target Price|Investment Summary\b|Outlook & Recommendation|Strategic Portfolio Roadmap|निष्कर्ष|कार्रवाई योग्य मार्गदर्शन)'
    parts = re.split(conclusion_pattern, text)
    cleaned = parts[0] if len(parts) > 1 else text
    cleaned = re.sub(r'(?im)^\s*(?:#+|\*\*|__)?\s*VERDICT\s*:\s*(?:BUY|HOLD|SELL|AVOID)\b[^\n]*\n*', '', cleaned)
    cleaned = re.sub(r'(?im)^[ \t]*[-*•]\s*(?:Verdict|Rating|Recommendation)\s*:\s*(?:BUY|HOLD|SELL|AVOID)\b[^\n]*\n*', '', cleaned)
    cleaned = re.sub(r'\n*---\s*$', '', cleaned.rstrip())
    return cleaned.strip()

def format_citations_section(citations: list[dict], stock_data: dict = None) -> str:
    """
    Formats a structured list of citations into an institutional Sell-Side footnotes block.
    Deduplicates URLs and displays clean attribution labels and source types.
    """
    if not citations:
        return ""

    lines = [
        "\n\n### 📚 Verified Regulatory Sources & Footnote Citations",
        "*All qualitative findings, corporate governance audits, and strategic disclosures in this report are grounded in primary exchange filings and verified public intelligence under SEBI statutory safe-harbor standards:*\n"
    ]
    seen = set()
    idx = 1
    for c in citations:
        uri = (c.get("uri") or "").strip()
        title = (c.get("title") or "Exchange / Public Document").strip()
        stype = (c.get("source_type") or "Verified Grounding").strip()

        # Clean title if domain-only
        if title.lower() == "bseindia.com":
            title = "BSE India Official Disclosures & Filing Repository"
        elif title.lower() == "nseindia.com":
            title = "NSE India Corporate Announcements Feed"
        elif title.lower() == "mca.gov.in":
            title = "Ministry of Corporate Affairs Company Master Data"
        elif title.lower() == "sebi.gov.in":
            title = "SEBI Statutory Orders & Regulatory Framework"

        if uri and uri in seen:
            continue
        if uri:
            seen.add(uri)
            lines.append(f"{idx}. [{title}]({uri}) — *{stype}*")
            idx += 1
        elif title:
            lines.append(f"{idx}. **{title}** — *{stype}*")
            idx += 1

PILLAR_METADATA = {
    1: {
        "label": "BSE Announcements",
        "url_path": "corporates/ann.html?scrip_cd={scrip}",
        "name": "BSE Regulatory Disclosures & Macro Bulletins",
        "standard_title": "Macro-Economic, Geopolitical & Environmental Overlays",
    },
    2: {
        "label": "BSE Transcripts",
        "url_path": "corporates/ann.html?scrip_cd={scrip}",
        "name": "BSE Investor Presentations & Concall Transcripts",
        "standard_title": "Industry Dynamics & Competitive Positioning",
    },
    3: {
        "label": "BSE Shareholding",
        "url_path": "corporates/ShareholdingPattern.aspx?scrip_cd={scrip}",
        "name": "Official BSE Shareholding Pattern & Promoter Pledging",
        "standard_title": "Promoter Quality & Fundamental Health",
    },
    4: {
        "label": "BSE Financial Results",
        "url_path": "corporates/Comp_Resultsnew.aspx?scrip_cd={scrip}",
        "name": "BSE Audited Financial Results (Comp_Results)",
        "standard_title": 'The "Structural vs. Temporary" Drop Diagnostic',
    },
    5: {
        "label": "BSE Valuation Filings",
        "url_path": "corporates/Comp_Resultsnew.aspx?scrip_cd={scrip}",
        "name": "BSE Exchange Earnings Filings & Balance Sheet",
        "standard_title": "Valuation & Margin of Safety",
    },
    6: {
        "label": "BSE Bhavcopy",
        "url_path": "stock-share-price/-/-/{scrip}/",
        "name": "Official BSE Bhavcopy Trade Execution Records",
        "standard_title": "Technical & Momentum Overlay",
    },
    7: {
        "label": "BSE BRSR ESG",
        "url_path": "corporates/ann.html?scrip_cd={scrip}",
        "name": "SEBI Business Responsibility and Sustainability Report (BRSR)",
        "standard_title": "ESG Impact Scorecard",
    },
}

# Data-free placeholder shown under the paywall blur when a gated pillar has little text.
# It must never contain figures: blurred HTML is still readable in page source.
_LOCKED_SKELETON_HTML = """
<div aria-hidden="true" style="display: grid; gap: 10px; margin-top: 12px;">
  <div style="height: 12px; width: 92%; border-radius: 6px; background: rgba(148, 163, 184, 0.18);"></div>
  <div style="height: 12px; width: 78%; border-radius: 6px; background: rgba(148, 163, 184, 0.18);"></div>
  <div style="height: 12px; width: 85%; border-radius: 6px; background: rgba(148, 163, 184, 0.18);"></div>
  <div style="height: 12px; width: 64%; border-radius: 6px; background: rgba(148, 163, 184, 0.18);"></div>
</div>
"""

def wrap_html_with_collapsible_pillars(
    html_content: str,
    scrip_code: str = "",
    is_deep_dive_unlocked: bool = False,
    ticker: str = ""
) -> str:
    """
    Transforms flat <h2>Pillar X: ...</h2> sections into interactive, mobile-optimized
    <details class="pillar-accordion" open> blocks with exact verified BSE filing hyperlinks.
    
    Tiered Institutional Architecture:
    - Free Tier: Pillars 01, 02, 04, 06, 07 are un-gated and fully readable.
    - Institutional Deep-Dive Tier: Pillar 03 (Forensic Ledger) and Pillar 05 (Reverse DCF Sandbox)
      display a teaser paragraph followed by an institutional frosted-glass paywall overlay
      when is_deep_dive_unlocked is False.
    """
    if not html_content:
        return html_content

    # Check for presence of pillar token across English, Hindi, and technical sections
    has_pillar_token = any(token in html_content for token in ("Pillar", "स्तंभ", "Dimension"))
    if not has_pillar_token:
        return html_content

    # Only build exchange links from a real, numeric BSE scrip code for THIS company.
    # Never substitute another company's code: a wrong citation is worse than none.
    scrip = str(scrip_code or "").strip()
    has_valid_scrip = bool(scrip) and scrip.isdigit()

    # Strict AST heading pattern: requires explicit Pillar/स्तंभ/Dimension token across H1-H3
    # This prevents subheadings like <h2>1. Profitability risk</h2> or <h2>1. Executive Summary</h2> from hijacking Pillar 1
    pattern = re.compile(
        r'(<h[1-3][^>]*>.*?(?:Pillar|स्तंभ|Dimension)\s*(\d+)[:\.\s\-]*([^<]*?)</h[1-3]>)',
        re.IGNORECASE
    )
    splits = pattern.split(html_content)
    
    if len(splits) < 5:
        # Fallback to secondary pattern if token was formatted with non-breaking whitespace or brackets
        pattern = re.compile(
            r'(<h[1-3][^>]*>.*?(?:Pillar|स्तंभ|Dimension)[^\w<]*?(\d+)[:\.\s\-]*([^<]*?)</h[1-3]>)',
            re.IGNORECASE
        )
        splits = pattern.split(html_content)
        if len(splits) < 5:
            return html_content

    output_parts = [splits[0]]
    i = 1
    t_clean = (ticker or "").upper()
    while i < len(splits):
        num_str = splits[i+1]
        raw_title = splits[i+2].strip().strip(" :.-")
        body_content = splits[i+3] if i + 3 < len(splits) else ""

        try:
            p_num = int(num_str)
        except ValueError:
            p_num = 1

        meta = PILLAR_METADATA.get(p_num, PILLAR_METADATA[1])
        url = f"https://www.bseindia.com/{meta['url_path'].format(scrip=scrip)}" if has_valid_scrip else ""
        label = meta["label"]
        name = meta["name"]
        clean_title = raw_title or meta.get("standard_title", f"Pillar {p_num:02d}")

        # Tiered Institutional Gating Logic for Pillars 03 & 05
        status_pill_html = ""
        rendered_body = body_content

        if p_num in (3, 5):
            if is_deep_dive_unlocked:
                status_pill_html = '<span class="badge badge-emerald" style="font-size: 11px;">🔓 Institutional Unlocked</span>'
            else:
                status_pill_html = '<span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); font-size: 11px;">🔒 Institutional Gated (1 Credit)</span>'
                
                # Split body into introductory teaser paragraph and locked remainder
                teaser = ""
                remainder = ""
                p_end = body_content.find("</p>")
                if p_end != -1:
                    teaser = body_content[:p_end + 4]
                    remainder = body_content[p_end + 4:].strip()
                else:
                    teaser = body_content[:300]
                    remainder = body_content[300:].strip()

                if p_num == 3:
                    lead_snippet = (remainder[:180].rstrip() + "...") if len(remainder) > 180 else remainder
                    blur_body = f"""<div style="opacity: 0.5; filter: blur(3px); user-select: none; pointer-events: none;"><p style="margin: 0; line-height: 1.6;">{lead_snippet}</p>\n{_LOCKED_SKELETON_HTML}</div>"""
                    paywall_card = f"""
<div class="gated-pillar-container">
  <div class="gated-blur-content">
    {blur_body}
  </div>
  <div class="gated-paywall-overlay">
    <div class="gated-badge">
      🔒 Institutional Forensic Audit
    </div>
    <h4 class="gated-title">
      Balance Sheet & Forensic Accounting Ledger
    </h4>
    <p class="gated-desc">
      Unlock Beneish M-Score accrual scrubbing, related-party cash extraction audits, promoter pledging risk, and off-balance sheet contingent liability headroom.
    </p>
    <div class="gated-features-grid">
      <span class="badge gated-feature-chip">🛡️ Beneish M-Score Accrual Model</span>
      <span class="badge gated-feature-chip">🔍 Related-Party Transaction Scrubbing</span>
      <span class="badge gated-feature-chip">📊 Contingent Liability Headroom</span>
      <span class="badge gated-feature-chip">🏛️ Promoter Pledging & Debt Run-Rate</span>
    </div>
    <div class="gated-action-row">
      <button type="button" class="btn btn-primary" onclick="unlockDeepDive('{t_clean}')">
        <span>🔓</span> Unlock Full Forensic Ledger (1 Credit)
      </button>
    </div>
    <div class="gated-subtext">
      Includes full PDF export • <a href="javascript:void(0)" onclick="openSignInModal()">Sign in to claim 2 free research credits</a>
    </div>
  </div>
</div>
"""
                    rendered_body = f"{teaser}\n{paywall_card}"

                elif p_num == 5:
                    lead_snippet = (remainder[:180].rstrip() + "...") if len(remainder) > 180 else remainder
                    blur_body = f"""<div style="opacity: 0.5; filter: blur(3px); user-select: none; pointer-events: none;"><p style="margin: 0; line-height: 1.6;">{lead_snippet}</p>\n{_LOCKED_SKELETON_HTML}</div>"""
                    paywall_card = f"""
<div class="gated-pillar-container">
  <div class="gated-blur-content">
    {blur_body}
  </div>
  <div class="gated-paywall-overlay">
    <div class="gated-badge">
      🔒 Valuation & Reverse DCF Sandbox
    </div>
    <h4 class="gated-title">
      Reverse DCF Sensitivity Sandbox & Valuation Model
    </h4>
    <p class="gated-desc">
      Stress-test current price expectations against Reverse DCF implied Free Cash Flow growth, multi-scenario terminal multiples, and cost of capital (WACC) hurdle matrices.
    </p>
    <div class="gated-features-grid">
      <span class="badge gated-feature-chip">🎯 Reverse DCF Implied Cash Flow Growth</span>
      <span class="badge gated-feature-chip">📐 Multi-Scenario Terminal Multiple Matrix</span>
      <span class="badge gated-feature-chip">📉 Margin of Safety Intrinsic Discount Table</span>
      <span class="badge gated-feature-chip">🔄 Historical Valuation Band Normalization</span>
    </div>
    <div class="gated-action-row">
      <button type="button" class="btn btn-primary" onclick="unlockDeepDive('{t_clean}')">
        <span>🔓</span> Unlock Reverse DCF Sandbox (1 Credit)
      </button>
    </div>
    <div class="gated-subtext">
      Includes full PDF export • <a href="javascript:void(0)" onclick="openSignInModal()">Sign in to claim 2 free research credits</a>
    </div>
  </div>
</div>
"""
                    rendered_body = f"{teaser}\n{paywall_card}"

        if has_valid_scrip:
            source_chip_html = (
                f'<a href="{url}" target="_blank" rel="noopener noreferrer" class="badge" '
                f'style="background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.25); '
                f'text-decoration: none; font-size: 11px; font-weight: 600;" onclick="event.stopPropagation()">'
                f'📄 {label} ↗</a>'
            )
            citation_strip_html = (
                f'<span>📄 <strong>Primary Exchange Source:</strong> '
                f'<a href="{url}" target="_blank" rel="noopener noreferrer" class="pillar-citation-link">{name}</a> '
                f'(official BSE page for BSE scrip {scrip}).</span>'
            )
        else:
            source_chip_html = ""
            citation_strip_html = (
                '<span>📄 <strong>Primary Exchange Source:</strong> '
                'BSE scrip code not yet resolved for this company, so no exchange link is shown.</span>'
            )

        card = f"""
<details class="pillar-accordion" id="pillar-{p_num}" open>
  <summary>
    <div class="pillar-summary-left">
      <span class="badge badge-cyan pillar-badge">{p_num:02d}</span>
      <h3 class="pillar-summary-title">{clean_title}</h3>
      {status_pill_html}
    </div>
    <div style="display: flex; align-items: center; gap: 10px;">
      {source_chip_html}
      <span class="pillar-chevron">▼</span>
    </div>
  </summary>
  <div class="pillar-body">
    <div class="pillar-citation-strip">
      {citation_strip_html}
    </div>
    {rendered_body}
  </div>
</details>
"""
        output_parts.append(card)
        i += 4

    return "\n".join(output_parts)

def compare_revisions(rev_a: dict, rev_b: dict) -> dict:
    """
    Standalone differential engine: compares two discrete report states (State A vs State B).
    State A is the older revision, State B is the newer revision.
    Returns a structured diff dict with pillar migrations, metric deltas,
    value trap detection, and trigger provenance — all purely descriptive diagnostics.

    Designed to be decoupled: accepts any two revision dicts, enabling
    "Current vs Previous", "Current vs 1 Year Ago", or "Current vs Pre-COVID" comparisons.
    """
    matrix_a = extract_health_matrix(rev_a.get("report_text", ""))
    matrix_b = extract_health_matrix(rev_b.get("report_text", ""))

    # Pillar quality rankings: index 0 = strongest, higher index = weaker
    PILLAR_RANKS = {
        "Macro": ["Stable", "Neutral", "Headwinds"],
        "Moat": ["Wide", "Moderate", "Narrow"],
        "Governance": ["Clean", "Caution", "High Risk"],
        "Diagnostic": ["Temporary", "Neutral", "Structural", "N/A"],
        "Valuation": ["Undervalued", "Fair", "Stretched", "Loss-Making"],
        "BalanceSheet": ["Debt-Free", "Resilient", "Moderate Debt", "High Debt"],
        "CapitalAllocation": ["Disciplined", "Moderate", "Strained"],
    }

    PILLAR_LABELS = {
        "Macro": "Macro Environment",
        "Moat": "Competitive Moat",
        "Governance": "Governance & Promoters",
        "Diagnostic": "Drop Diagnostic",
        "Valuation": "Valuation Multiple",
        "BalanceSheet": "Balance Sheet Leverage",
        "CapitalAllocation": "Capital Allocation",
    }

    pillar_migrations = []
    downgrade_count = 0
    upgrade_count = 0

    for pillar, ranks in PILLAR_RANKS.items():
        val_a = matrix_a.get(pillar, "N/A")
        val_b = matrix_b.get(pillar, "N/A")
        if val_a == val_b:
            continue

        rank_a = ranks.index(val_a) if val_a in ranks else -1
        rank_b = ranks.index(val_b) if val_b in ranks else -1

        if rank_a == -1 or rank_b == -1:
            direction = "changed"
        elif rank_b > rank_a:
            direction = "downgrade"
            downgrade_count += 1
        else:
            direction = "upgrade"
            upgrade_count += 1

        pillar_migrations.append({
            "pillar": pillar,
            "label": PILLAR_LABELS.get(pillar, pillar),
            "from": val_a,
            "to": val_b,
            "direction": direction,
        })

    # Quantitative metric deltas
    metric_deltas = {}
    for key, label in [("baseline_price", "Price (₹)"), ("baseline_pe", "Trailing P/E"), ("baseline_mcap", "Market Cap")]:
        raw_a = rev_a.get(key)
        raw_b = rev_b.get(key)
        try:
            num_a = float(str(raw_a).replace(",", "").replace("N/A", "0").replace("Loss-Making", "0").strip() or "0")
            num_b = float(str(raw_b).replace(",", "").replace("N/A", "0").replace("Loss-Making", "0").strip() or "0")
        except (ValueError, TypeError):
            num_a, num_b = 0.0, 0.0

        pct_change = ((num_b - num_a) / num_a * 100.0) if num_a > 0 else 0.0
        metric_deltas[key] = {
            "label": label,
            "state_a": raw_a,
            "state_b": raw_b,
            "num_a": num_a,
            "num_b": num_b,
            "pct_change": round(pct_change, 1),
        }

    # Value Trap Detection: qualitative downgrade + valuation expansion (price or P/E rise)
    price_delta = metric_deltas.get("baseline_price", {}).get("pct_change", 0.0)
    pe_delta = metric_deltas.get("baseline_pe", {}).get("pct_change", 0.0)
    value_trap_detected = downgrade_count > 0 and (price_delta > 5.0 or pe_delta > 10.0)

    # Trigger provenance
    trigger_b = rev_b.get("revision_trigger", "Unknown")

    return {
        "state_a_date": rev_a.get("formatted_date", "Unknown"),
        "state_b_date": rev_b.get("formatted_date", "Unknown"),
        "pillar_migrations": pillar_migrations,
        "migration_count": len(pillar_migrations),
        "upgrades": upgrade_count,
        "downgrades": downgrade_count,
        "metric_deltas": metric_deltas,
        "value_trap_detected": value_trap_detected,
        "value_trap_detail": (
            f"{downgrade_count} qualitative downgrade(s) alongside "
            f"{'+' if price_delta > 0 else ''}{price_delta:.1f}% price shift"
        ) if value_trap_detected else "",
        "revision_trigger": trigger_b,
        "matrix_a": matrix_a,
        "matrix_b": matrix_b,
    }
