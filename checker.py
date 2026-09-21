import re

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

    return len(discrepancies) == 0, discrepancies
