import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from datetime import datetime, timezone, timedelta
from analyzer import (
    compute_deterministic_technical_context,
    splice_report_pillars,
    evaluate_material_change,
    execute_surgical_pillar_update
)

SAMPLE_REPORT = """# Institutional Equity Research Report: Infosys Ltd (INFY)

---
## Pillar 1: Macro-Economic, Geopolitical & Environmental Overlays
Macro conditions for global IT services remain cautious due to rate cuts and discretionary tech spending delays.

## Pillar 2: Industry Dynamics & Competitive Positioning
Infosys maintains a top-tier digital transformation moat alongside TCS.

## Pillar 3: Promoter Quality & Fundamental Health
Zero promoter pledge, net-cash balance sheet, high return on equity.

## Pillar 4: The "Structural vs. Temporary" Drop Diagnostic
Recent margin contraction is cyclical, driven by delayed client decision cycles.

## Pillar 5: Valuation & Margin of Safety
Old valuation: Trades at 28x P/E which is rich compared to 10-year historical average of 22x.

## Pillar 6: Technical & Momentum Overlay
Old technicals: Consolidating near 200-DMA with declining momentum.

## Pillar 7: ESG Impact Scorecard
| Parameter | Score (0-100) | Evaluation & Key Drivers |
| :--- | :--- | :--- |
| **Environmental** | 88 | Carbon neutral operations |
| **Social** | 85 | High diversity in tech |
| **Governance** | 94 | High independent board oversight |
"""

def test_compute_deterministic_technical_context():
    stock_data = {
        "current_price": 1500.0,
        "pe_ratio": "24.5",
        "market_cap": 6000000000000.0,
        "fifty_two_week_high": 1750.0,
        "fifty_two_week_low": 1250.0,
    }
    dates = pd.date_range(end=pd.Timestamp.now(), periods=60)
    prices = [1400.0] * 60
    hist_df = pd.DataFrame({"Close": prices}, index=dates)

    metrics = compute_deterministic_technical_context(stock_data, hist_df)
    assert metrics["price"] == 1500.0
    assert metrics["pe_ratio"] == "24.5"
    assert metrics["mcap_cr"] == 600000.0
    assert metrics["dma_50"] == 1400.0
    assert metrics["pct_from_dma50"] is not None
    assert round(metrics["pct_from_dma50"], 1) == 7.1

def test_splice_report_pillars():
    new_p5 = "## Pillar 5: Valuation & Margin of Safety\n\nNew valuation analysis at ₹1500 per share with 24.5x P/E."
    new_p6 = "## Pillar 6: Technical & Momentum Overlay\n\nNew momentum overlay: stock trades +7.1% above 50-DMA."

    spliced = splice_report_pillars(SAMPLE_REPORT, {5: new_p5, 6: new_p6})

    # Assert Pillars 1, 2, 3, 4, and 7 are completely preserved
    assert "Macro conditions for global IT services" in spliced
    assert "Infosys maintains a top-tier digital transformation moat" in spliced
    assert "Zero promoter pledge, net-cash balance sheet" in spliced
    assert "Recent margin contraction is cyclical" in spliced
    assert "Carbon neutral operations" in spliced
    assert "High independent board oversight" in spliced

    # Assert Pillars 5 and 6 are cleanly replaced
    assert "Old valuation: Trades at 28x P/E" not in spliced
    assert "New valuation analysis at ₹1500 per share" in spliced
    assert "Old technicals: Consolidating near 200-DMA" not in spliced
    assert "New momentum overlay: stock trades +7.1% above 50-DMA." in spliced

def test_evaluate_material_change_types():
    cached = {
        "raw_timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_price": 1000.0,
        "latest_announcement": "Clean",
    }

    # 1. No change (<5% move)
    live_fund_no_change = {"current_price": 1020.0}
    regen, reason, ann, change_type = evaluate_material_change(cached, live_fund_no_change, "")
    assert not regen
    assert change_type == "NONE"

    # 2. Price shift (>= 5%)
    live_fund_shift = {"current_price": 1060.0}
    regen, reason, ann, change_type = evaluate_material_change(cached, live_fund_shift, "")
    assert regen
    assert change_type == "PRICE_DELTA"
    assert "+6.0%" in reason

    # 3. Expired (>14 days)
    cached_expired = {
        "raw_timestamp": (datetime.now(timezone.utc) - timedelta(days=15)).isoformat(),
        "baseline_price": 1000.0,
        "latest_announcement": "Clean",
    }
    regen, reason, ann, change_type = evaluate_material_change(cached_expired, live_fund_no_change, "")
    assert regen
    assert change_type == "EXPIRED"

def test_execute_surgical_pillar_update_fallback():
    # Test that when no external API or offline, deterministic Python fallback executes seamlessly
    cached = {
        "report_text": SAMPLE_REPORT,
        "baseline_price": 1000.0,
    }
    stock_data = {
        "ticker": "INFY",
        "short_name": "Infosys Ltd",
        "current_price": 1100.0,
        "pe_ratio": "25.0",
        "market_cap": 5000000000000.0,
        "fifty_two_week_high": 1200.0,
        "fifty_two_week_low": 900.0,
    }
    spliced = execute_surgical_pillar_update("INFY", cached, stock_data)
    assert "## Pillar 5: Valuation & Margin of Safety" in spliced
    assert "## Pillar 6: Technical & Momentum Overlay" in spliced
    assert "Pillar 1: Macro-Economic" in spliced
    assert "₹1100.00" in spliced

if __name__ == "__main__":
    test_compute_deterministic_technical_context()
    print("✓ test_compute_deterministic_technical_context passed")
    test_splice_report_pillars()
    print("✓ test_splice_report_pillars passed")
    test_evaluate_material_change_types()
    print("✓ test_evaluate_material_change_types passed")
    test_execute_surgical_pillar_update_fallback()
    print("✓ test_execute_surgical_pillar_update_fallback passed")
    print("🎉 All surgical update tests passed successfully.")

