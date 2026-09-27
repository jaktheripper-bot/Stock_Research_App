from checker import verify_stock_report

def get_mock_stock_data():
    return {
        "ticker": "INFY",
        "short_name": "Infosys Limited"
    }

def test_valid_7_pillar_report(mock_stock_data=None):
    if mock_stock_data is None:
        mock_stock_data = get_mock_stock_data()
    valid_text = """
    # DIAGNOSTIC SUMMARY & KEY TAKEAWAYS
    **Summary:** Strong market position with robust free cash flows.

    ## Pillar 1: Macro-Economic, Geopolitical & Environmental Overlays
    Stable domestic environment with global IT headwinds.

    ## Pillar 2: Industry Dynamics & Competitive Positioning
    Top tier digital transformation provider.

    ## Pillar 3: Promoter Quality & Fundamental Health
    Exemplary corporate governance track record.

    ## Pillar 4: The "Structural vs. Temporary" Drop Diagnostic
    Recent correction driven by cyclical slowdown rather than moat erosion.

    ## Pillar 5: Valuation & Margin of Safety
    Fair valuation at ₹1,450 per share with solid margin of safety.

    ## Pillar 6: Technical & Momentum Overlay
    Consolidating above 50-DMA with moderate volume.

    ## Pillar 7: ESG Impact Scorecard
    | Parameter | Score (0-100) | Evaluation & Key Drivers |
    | :--- | :--- | :--- |
    | **Environmental** | 85 | Carbon neutral campus goals |
    | **Social** | 78 | Extensive employee reskilling programs |
    | **Governance** | 92 | Independent board oversight |
    """
    passed, discrepancies = verify_stock_report(mock_stock_data, valid_text)
    assert passed is True, f"Valid report failed audit: {discrepancies}"
    assert len(discrepancies) == 0

def test_missing_required_section(mock_stock_data=None):
    if mock_stock_data is None:
        mock_stock_data = get_mock_stock_data()
    faulty_text = """
    # DIAGNOSTIC SUMMARY
    Summary here.
    ## Pillar 1: Macro
    ## Pillar 2: Industry
    ## Pillar 3: Governance
    ## Pillar 5: Valuation
    ## Pillar 6: Technical
    ## Pillar 7: ESG Impact Scorecard
    | **Environmental** | 80 | Good |
    | **Social** | 75 | Good |
    | **Governance** | 85 | Good |
    """
    passed, discrepancies = verify_stock_report(mock_stock_data, faulty_text)
    assert passed is False
    assert any("Missing required section: Pillar 4" in d for d in discrepancies)

def test_incomplete_esg_scorecard(mock_stock_data=None):
    if mock_stock_data is None:
        mock_stock_data = get_mock_stock_data()
    faulty_text = """
    # DIAGNOSTIC SUMMARY
    ## Pillar 1: Macro
    ## Pillar 2: Industry
    ## Pillar 3: Promoters
    ## Pillar 4: Diagnostic
    ## Pillar 5: Valuation
    ## Pillar 6: Momentum
    ## Pillar 7: ESG
    | Parameter | Score | Drivers |
    | **Environmental** | 80 | Clean |
    """
    passed, discrepancies = verify_stock_report(mock_stock_data, faulty_text)
    assert passed is False
    assert any("ESG Impact Scorecard table is incomplete" in d for d in discrepancies)

def test_disallowed_inr_millions_rule(mock_stock_data=None):
    if mock_stock_data is None:
        mock_stock_data = get_mock_stock_data()
    faulty_text = """
    # DIAGNOSTIC SUMMARY
    ## Pillar 1: Macro
    ## Pillar 2: Industry
    ## Pillar 3: Promoters
    ## Pillar 4: Diagnostic
    ## Pillar 5: Valuation
    Operating revenue stood at ₹ 500 million for the quarter.
    ## Pillar 6: Momentum
    ## Pillar 7: ESG
    | **Environmental** | 80 | Clean |
    | **Social** | 80 | Clean |
    | **Governance** | 80 | Clean |
    """
    passed, discrepancies = verify_stock_report(mock_stock_data, faulty_text)
    assert passed is False
    assert any("Use Lakhs/Crores for Indian Rupee figures" in d for d in discrepancies)

def test_permitted_usd_billions_context(mock_stock_data=None):
    if mock_stock_data is None:
        mock_stock_data = get_mock_stock_data()
    valid_text = """
    # DIAGNOSTIC SUMMARY
    ## Pillar 1: Macro
    ## Pillar 2: Industry
    Global addressable cloud software market is estimated at $120 billion.
    ## Pillar 3: Promoters
    ## Pillar 4: Diagnostic
    ## Pillar 5: Valuation
    Revenue reached ₹ 15,000 Cr with resilient ROCE.
    ## Pillar 6: Momentum
    ## Pillar 7: ESG
    | **Environmental** | 80 | Clean |
    | **Social** | 80 | Clean |
    | **Governance** | 80 | Clean |
    """
    passed, discrepancies = verify_stock_report(mock_stock_data, valid_text)
    assert passed is True, f"USD billions in global context was wrongly rejected: {discrepancies}"

if __name__ == "__main__":
    test_valid_7_pillar_report()
    test_missing_required_section()
    test_incomplete_esg_scorecard()
    test_disallowed_inr_millions_rule()
    test_permitted_usd_billions_context()
    print("🎉 All 5 checker test suites passed successfully.")
