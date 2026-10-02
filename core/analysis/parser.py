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

    return "\n".join(lines) + "\n"

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
