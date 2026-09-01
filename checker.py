import re

def verify_stock_report(stock_data: dict, report_text: str) -> tuple[bool, list[str]]:
    """
    Audits the generated AI report to ensure structural integrity, 
    proper 1-100 ESG bounds, and strict adherence to the Indian numerical system.
    """
    discrepancies = []
    
    required_headers = [
        "VERDICT",
        "Pillar 1",
        "Pillar 2",
        "Pillar 3",
        "Pillar 4",
        "Pillar 5",
        "Pillar 6",
        "Pillar 7",
        "Conclusion"
    ]
    
    for header in required_headers:
        if not re.search(rf"{header}", report_text, re.IGNORECASE):
            discrepancies.append(f"Missing required section: {header}")

    esg_pattern = re.compile(r'\|\s*\*\*?(Environmental|Social|Governance)\*?\*\s*\|\s*(\d+(?:\.\d+)?)\s*\|', re.IGNORECASE)
    esg_matches = esg_pattern.findall(report_text)
    
    if not esg_matches or len(esg_matches) < 3:
        discrepancies.append("ESG Impact Scorecard table is missing, incomplete, or improperly formatted.")
    else:
        for match in esg_matches:
            param, score_str = match
            try:
                score = float(score_str)
                if not (0 <= score <= 100):
                    discrepancies.append(f"Scorecard Error: {param} rating '{score}' exceeds allowable 0-100 bounds.")
            except ValueError:
                discrepancies.append(f"Scorecard Error: Could not parse numerical score for {param}.")

    if re.search(r'\b(billion|billions|million|millions)\b', report_text, re.IGNORECASE):
        discrepancies.append("Formatting Error: Report contains disallowed international numeric formats (Millions/Billions). It must strictly use the Indian numbering system (Lakhs/Crores).")

    passed = len(discrepancies) == 0
    return passed, discrepancies