import re

def verify_stock_report(stock_data: dict, report_text: str) -> tuple[bool, list[str]]:
    discrepancies = []
    
    ticker = stock_data.get("ticker", "").upper()
    short_name = stock_data.get("short_name", "")
    
    if not ticker or ticker not in report_text.upper():
        discrepancies.append(f"Critical: Target ticker symbol '{ticker}' is missing from report text.")
    if short_name and short_name.lower() not in report_text.lower():
        discrepancies.append(f"Critical: Company name '{short_name}' is missing from report text.")

    if "N/A" in report_text and ("Market Cap" in report_text or "P/E" in report_text):
        discrepancies.append("Data Integrity Error: Report contains unresolved 'N/A' placeholders for core financial metrics.")

    required_sections = [
        "Values & Beliefs Impact Scorecard",
        "Corporate Governance & Transparency",
        "Socio-Economic Impact",
        "Environmental & Sustainability Alignment"
    ]
    
    for section in required_sections:
        if section.lower() not in report_text.lower():
            discrepancies.append(f"Structure Error: Missing mandatory section -> '{section}'.")

    score_matches = re.findall(r'(\d+(?:\.\d+)?)\s*/\s*10', report_text)
    if not score_matches:
        discrepancies.append("Scorecard Error: No valid 'X/10' numerical ratings found in the impact scorecard.")
        
    for score_str in score_matches:
        try:
            score_val = float(score_str)
            if score_val < 0 or score_val > 10:
                discrepancies.append(f"Scorecard Error: Rating '{score_val}/10' exceeds allowable 0-10 bounds.")
        except ValueError:
            discrepancies.append(f"Scorecard Error: Malformed score formatting detected ('{score_str}').")

    passed = len(discrepancies) == 0
    return passed, discrepancies
