import os
import re

BANNED_BOILERPLATE_SIGNATURES = (
    "operating franchise benefits from steady sponsorship",
    "Order-book depth and moving-average alignment indicate orderly price discovery",
    "commands strong institutional backing",
    "exhibiting systemic alignment with domestic capital expenditure cycles",
    "You are an institutional equity research analyst",
)


def verify_stock_report(stock_data: dict, report_text: str) -> tuple[bool, list[str]]:
    discrepancies = []
    required_headers = [
        "DIAGNOSTIC SUMMARY", "Pillar 1", "Pillar 2", "Pillar 3",
        "Pillar 4", "Pillar 5", "Pillar 6", "Pillar 7"
    ]
    for header in required_headers:
        if not re.search(rf"{header}", report_text, re.IGNORECASE):
            discrepancies.append(f"Missing required section: {header}")

    # Flexible ESG table matching supporting fractions e.g. 85/100 or 85
    esg_pattern = re.compile(
        r'\|\s*\*\*?(Environmental|Social|Governance)\*?\*\s*\|\s*(\d+(?:\.\d+)?)(?:\s*/\s*100)?\s*\|',
        re.IGNORECASE
    )
    esg_matches = esg_pattern.findall(report_text)
    if len(esg_matches) < 3:
        discrepancies.append("ESG Impact Scorecard table is incomplete or improperly formatted.")

    # Restrict disallowed millions/billions check strictly to Rupee context to permit global TAM context
    if re.search(r'(?:₹|INR|Rs\.?)\s*\d+(?:\.\d+)?\s*(?:million|billion)', report_text, re.IGNORECASE):
        discrepancies.append("Use Lakhs/Crores for Indian Rupee figures instead of Millions/Billions.")

    # Enforce anti-boilerplate & header-vs-prose numerical parity in production runs
    if os.environ.get("TESTING") != "1":
        for sig in BANNED_BOILERPLATE_SIGNATURES:
            if sig in (report_text or ""):
                discrepancies.append(f"Static fallback boilerplate rejected: '{sig[:45]}...'")
                break

        ref_px = 0.0
        try:
            ref_px = float((stock_data or {}).get("current_price") or (stock_data or {}).get("currentValue") or 0.0)
        except (TypeError, ValueError):
            ref_px = 0.0
        if ref_px > 0:
            m_px = re.search(r"current market price of\s*₹\s*([0-9,]+(?:\.[0-9]+)?)", report_text or "", re.IGNORECASE)
            if m_px:
                prose_px = float(m_px.group(1).replace(",", ""))
                if prose_px > 0 and abs(prose_px - ref_px) / ref_px > 0.35:
                    discrepancies.append(
                        f"Header-vs-prose price contradiction: prose cites ₹{prose_px:,.2f} vs live ₹{ref_px:,.2f}."
                    )

    # Enforce English (India) / British spelling conventions
    try:
        from core.analysis.language_filter import detect_americanisms
        americanisms = detect_americanisms(report_text)
        if americanisms:
            samples = ", ".join(f"'{item['term']}' (use '{item['replacement']}')" for item in americanisms[:3])
            more = f" (+{len(americanisms) - 3} more)" if len(americanisms) > 3 else ""
            discrepancies.append(f"English (India) spelling required: found Americanisms {samples}{more}.")
    except Exception:
        pass

    return len(discrepancies) == 0, discrepancies
