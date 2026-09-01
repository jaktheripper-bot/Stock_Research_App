import pytest
from checker import verify_stock_report

@pytest.fixture
def flaky_stock_data():
    return {
        "ticker": "SBILIFE",
        "short_name": "SBI Life Insurance"
    }

def test_valid_report(flaky_stock_data):
    valid_text = """
    # SBI Life Insurance Research Report
    Target Ticker: SBILIFE
    
    ## Values & Beliefs Impact Scorecard
    1. **Corporate Governance & Transparency:** Score: 8.5/10
    2. **Socio-Economic Impact:** Score: 7.0/10
    3. **Environmental & Sustainability Alignment:** Score: 7.5/10
    """
    passed, discrepancies = verify_stock_report(flaky_stock_data, valid_text)
    assert passed is True, f"Report failed audit with discrepancies: {discrepancies}"
    assert len(discrepancies) == 0

def test_missing_ticker_and_name(flaky_stock_data):
    faulty_text = """
    # General Equity Research
    ## Values & Beliefs Impact Scorecard
    1. **Corporate Governance & Transparency:** 8/10
    2. **Socio-Economic Impact:** 7/10
    3. **Environmental & Sustainability Alignment:** 7/10
    """
    passed, discrepancies = verify_stock_report(flaky_stock_data, faulty_text)
    assert passed is False, "Audit incorrectly passed a report missing the ticker and name."
    assert any("ticker symbol" in d for d in discrepancies), f"Ticker discrepancy missing. Found: {discrepancies}"
    assert any("Company name" in d for d in discrepancies), f"Name discrepancy missing. Found: {discrepancies}"

def test_unresolved_na_placeholders(flaky_stock_data):
    faulty_text = """
    # SBI Life Insurance Research Report (SBILIFE)
    Market Cap: N/A
    P/E Ratio: N/A
    
    ## Values & Beliefs Impact Scorecard
    1. **Corporate Governance & Transparency:** 8/10
    2. **Socio-Economic Impact:** 7/10
    3. **Environmental & Sustainability Alignment:** 7/10
    """
    passed, discrepancies = verify_stock_report(flaky_stock_data, faulty_text)
    assert passed is False, "Audit incorrectly passed unresolved N/A placeholders."
    assert any("N/A" in d for d in discrepancies), f"Placeholder discrepancy missing. Found: {discrepancies}"

def test_missing_mandatory_sections(flaky_stock_data):
    faulty_text = """
    # SBI Life Insurance Research Report (SBILIFE)
    Market Cap: 150000 Cr
    P/E Ratio: 45.2
    
    ## Alternative Overview
    Some text here, but missing the mandatory scorecard sections.
    """
    passed, discrepancies = verify_stock_report(flaky_stock_data, faulty_text)
    assert passed is False, "Audit incorrectly passed missing mandatory sections."
    assert any("Missing mandatory section" in d for d in discrepancies), f"Section discrepancy missing. Found: {discrepancies}"

def test_out_of_bounds_score(flaky_stock_data):
    faulty_text = """
    # SBI Life Insurance Research Report (SBILIFE)
    Market Cap: 150000 Cr
    P/E Ratio: 45.2
    
    ## Values & Beliefs Impact Scorecard
    1. **Corporate Governance & Transparency:** 12.5/10
    2. **Socio-Economic Impact:** 7/10
    3. **Environmental & Sustainability Alignment:** 7/10
    """
    passed, discrepancies = verify_stock_report(flaky_stock_data, faulty_text)
    assert passed is False, "Audit incorrectly passed an out-of-bounds score."
    assert any("exceeds allowable 0-10 bounds" in d for d in discrepancies), f"Bounds discrepancy missing. Found: {discrepancies}"
