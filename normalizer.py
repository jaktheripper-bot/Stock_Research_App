from core.formatters import format_inr

def clean_ticker(raw: str) -> str:
    """Normalize stock ticker by stripping whitespace, uppercase, and removing exchange suffixes (.NS, .BO)."""
    if not raw:
        return ""
    return str(raw).strip().upper().replace(".NS", "").replace(".BO", "")

def format_indian_currency(val) -> str:
    """Formats numeric INR values using standard Indian numbering system (Lakhs / Crores)."""
    return format_inr(val)

def normalize_stock_data(raw_data: dict, exchange: str = "NSE") -> dict:
    normalized = raw_data.copy()
    raw_mcap = raw_data.get("market_cap")
    
    if exchange in ["NSE", "BSE", "NSEI", "BOM"]:
        normalized["formatted_market_cap"] = format_indian_currency(raw_mcap)
        normalized["currency"] = "INR"
    else:
        try:
            num = float(raw_mcap)
            normalized["formatted_market_cap"] = f"${num/1_000_000_000:,.2f} B"
            normalized["currency"] = "USD"
        except (ValueError, TypeError):
            normalized["formatted_market_cap"] = "N/A"
            normalized["currency"] = "Unknown"

    return normalized


def extract_citations_from_report(report_text: str) -> list[dict]:
    """
    Extracts structured citation items from a markdown equity research report.
    Recognizes footnote blocks, numbered source links, and markdown anchors.
    Returns a list of dicts: [{'index': 1, 'title': '...', 'uri': '...', 'source_type': '...'}]
    """
    import re
    if not report_text or not isinstance(report_text, str):
        return []

    citations = []
    seen_uris = set()

    pattern_md = r'(?m)^\s*(?:(?:\d+[\.:\)]|\[\^?\d+\]|[-*•])\s+)?\[([^\]]+)\]\((https?://[^\s\)]+)\)(?:\s*(?:—|-|•|\|)\s*\*?([^\*\n]+)\*?)?'
    for m in re.finditer(pattern_md, report_text):
        title = m.group(1).strip()
        uri = m.group(2).strip()
        stype = (m.group(3) or "").strip()
        if not stype:
            low_u = uri.lower()
            low_t = title.lower()
            if "bseindia.com" in low_u or "bse" in low_t:
                stype = "BSE Regulatory Filing"
            elif "nseindia.com" in low_u or "nse" in low_t:
                stype = "NSE Exchange Filing"
            elif "mca.gov.in" in low_u:
                stype = "MCA Registry Record"
            elif "sebi.gov.in" in low_u:
                stype = "SEBI Statutory Disclosure"
            elif any(k in low_u for k in ["investor", "annualreport", "concall", "transcript"]):
                stype = "Corporate Investor Relations"
            else:
                stype = "Verified Web Grounding"

        if "stock-research-app" in uri or uri.startswith("#"):
            continue

        if uri not in seen_uris:
            seen_uris.add(uri)
            citations.append({
                "index": len(citations) + 1,
                "title": title,
                "uri": uri,
                "source_type": stype
            })

    return citations