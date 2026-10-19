"""Unit tests for Institutional Epistemic Separation, Source-Passage Attribution & Falsification Engine.

Tests:
1. EPISTEMIC_PROMPT_DIRECTIVE contains 4 epistemic tiers and mandatory falsification triggers.
2. build_equity_epistemic_ledger generates structured 5-part ledger with verified facts, metrics, interpretations, and falsification rules.
3. extract_epistemic_badges parses inline badges ([VERIFIED FACT], [CALCULATED METRIC], etc.).
4. extract_falsification_triggers extracts quantitative revision thresholds per pillar.
5. build_multi_asset_epistemic_ledger supports EQUITY, MUTUAL_FUND, DEBT, and REIT schemas.
6. Integration: get_system_prompt embeds epistemic directive and compile_equity_dossier attaches epistemic_ledger.
"""

import unittest
from typing import Dict, Any

from core.analysis.epistemic_schema import (
    EPISTEMIC_PROMPT_DIRECTIVE,
    build_equity_epistemic_ledger,
    extract_epistemic_badges,
    extract_falsification_triggers,
    build_multi_asset_epistemic_ledger,
)
from core.analysis.dossier_report_synthesis import get_system_prompt
from core.analysis.equity_dossier import compile_equity_dossier


class TestEpistemicSchemaAndFalsificationEngine(unittest.TestCase):
    """Test suite for epistemic separation, source attribution, and thesis falsification."""

    def test_epistemic_prompt_directive_structure(self):
        """Verifies that the prompt directive defines all 4 epistemic tiers and falsification block."""
        self.assertIn("[VERIFIED FACT]", EPISTEMIC_PROMPT_DIRECTIVE)
        self.assertIn("[CALCULATED METRIC]", EPISTEMIC_PROMPT_DIRECTIVE)
        self.assertIn("[MODEL INTERPRETATION]", EPISTEMIC_PROMPT_DIRECTIVE)
        self.assertIn("[UNRESOLVED UNCERTAINTY]", EPISTEMIC_PROMPT_DIRECTIVE)
        self.assertIn("#### Falsification & Thesis-Revision Triggers", EPISTEMIC_PROMPT_DIRECTIVE)
        self.assertIn("What Contradicts This Conclusion:", EPISTEMIC_PROMPT_DIRECTIVE)
        self.assertIn("Evidence That Forces a Revision:", EPISTEMIC_PROMPT_DIRECTIVE)

    def test_build_equity_epistemic_ledger_with_complete_data(self):
        """Verifies structured 5-part ledger generation with realistic equity data."""
        stock_data = {
            "scrip_code": "500209",
            "current_price": 1542.50,
            "pe_ratio": 26.4,
        }
        equity_intel = {
            "valuation_radar": {
                "current_price": 1542.50,
                "fair_value": 1820.00,
                "margin_of_safety_pct": 18.0,
                "regime": "UNDERVALUED",
                "summary": "Trading at attractive discount to conservative intrinsic value."
            },
            "forensic_intelligence": {
                "passed_count": 9,
                "total_checks": 10,
                "badge_label": "Audited Clean"
            },
            "sector_intelligence": {
                "verdict": "STRONG_OUTPERFORM",
                "sector_display_name": "Indian IT Services",
                "narrative": "Resilient margin profile despite BFSI tech spend deceleration."
            }
        }

        ledger = build_equity_epistemic_ledger(
            ticker="INFY",
            stock_data=stock_data,
            equity_intel=equity_intel,
            formatted_date="2026-10-19"
        )

        self.assertEqual(ledger["as_of_date"], "2026-10-19")
        self.assertEqual(len(ledger["verified_facts"]), 2)
        self.assertIn("1542.5", ledger["verified_facts"][0]["claim"])
        self.assertIn("500209", ledger["verified_facts"][0]["source"])
        self.assertIn("9/10", ledger["verified_facts"][1]["claim"])

        self.assertEqual(len(ledger["calculated_metrics"]), 2)
        self.assertIn("₹1,820.00", ledger["calculated_metrics"][0]["metric"])
        self.assertIn("18.0%", ledger["calculated_metrics"][0]["metric"])

        self.assertTrue(any("Undervalued" in interp for interp in ledger["model_interpretations"]))
        self.assertEqual(len(ledger["unresolved_uncertainties"]), 2)

        triggers = ledger["falsification_triggers"]
        self.assertIn("what_could_contradict", triggers)
        self.assertIn("evidence_that_changes_conclusion", triggers)
        self.assertTrue(len(triggers["what_could_contradict"]) >= 2)
        self.assertTrue(len(triggers["evidence_that_changes_conclusion"]) >= 2)

    def test_build_equity_epistemic_ledger_with_empty_or_none_data(self):
        """Verifies graceful defensive handling when stock_data or equity_intel is None."""
        ledger = build_equity_epistemic_ledger(ticker="UNKNOWN", stock_data=None, equity_intel=None)
        self.assertEqual(ledger["as_of_date"], "Latest Filing")
        self.assertEqual(len(ledger["verified_facts"]), 2)
        self.assertIn("CMP ₹N/A", ledger["verified_facts"][0]["claim"])
        self.assertIn("Pending", ledger["calculated_metrics"][0]["metric"])
        self.assertIn("what_could_contradict", ledger["falsification_triggers"])

    def test_extract_epistemic_badges_from_markdown(self):
        """Verifies extraction and categorization of 4 epistemic badge types from report text."""
        sample_report = """
# Research Report
## Pillar 1: Macro
[VERIFIED FACT — BSE Q3 Filing: Revenue grew 8.5% YoY to ₹3,200 Cr.]
[CALCULATED METRIC: Net Debt / EBITDA = 0.25x.]
[MODEL INTERPRETATION: Headwinds in European auto segment are cyclical.]
[UNRESOLVED UNCERTAINTY: Impact of new carbon border adjustment tariffs remains unquantified.]
"""
        extracted = extract_epistemic_badges(sample_report)
        self.assertEqual(len(extracted["verified_facts"]), 1)
        self.assertIn("VERIFIED FACT", extracted["verified_facts"][0])
        self.assertEqual(len(extracted["calculated_metrics"]), 1)
        self.assertIn("CALCULATED METRIC", extracted["calculated_metrics"][0])
        self.assertEqual(len(extracted["model_interpretations"]), 1)
        self.assertIn("MODEL INTERPRETATION", extracted["model_interpretations"][0])
        self.assertEqual(len(extracted["unresolved_uncertainties"]), 1)
        self.assertIn("UNRESOLVED UNCERTAINTY", extracted["unresolved_uncertainties"][0])

        # Empty string handling
        empty_res = extract_epistemic_badges("")
        self.assertEqual(empty_res["verified_facts"], [])

    def test_extract_falsification_triggers_from_markdown(self):
        """Verifies extraction of falsification triggers per pillar."""
        sample_report = """
## Pillar 1: Macro-Economic Overlays
Inflation trajectory remains favorable.
#### Falsification & Thesis-Revision Triggers
* **What Contradicts This Conclusion:** Global crude price sustaining above $105/bbl for >90 days.
* **Evidence That Forces a Revision:** RBI repo rate hike >50 bps or CPI inflation exceeding 6.5%.

## Pillar 2: Industry Dynamics & Competitive Positioning
Wide moat secured by patents.
#### Falsification & Thesis-Revision Triggers
* **What Contradicts This Conclusion:** Market share erosion to low-cost generic entrants in US market.
* **Evidence That Forces a Revision:** Gross margin compression >300 bps YoY in consecutive quarterly filings.
"""
        triggers = extract_falsification_triggers(sample_report)
        self.assertIn(1, triggers)
        self.assertIn("crude price", triggers[1]["what_contradicts"])
        self.assertIn("repo rate hike", triggers[1]["evidence_that_forces_revision"])

        self.assertIn(2, triggers)
        self.assertIn("generic entrants", triggers[2]["what_contradicts"])
        self.assertIn("Gross margin compression", triggers[2]["evidence_that_forces_revision"])

        # Missing or empty markdown
        self.assertEqual(extract_falsification_triggers(""), {})

    def test_build_multi_asset_epistemic_ledger_dispatch(self):
        """Verifies multi-asset epistemic ledger dispatch across MUTUAL_FUND, DEBT, and REIT."""
        # 1. Mutual Fund
        mf_ledger = build_multi_asset_epistemic_ledger(
            asset_class="MUTUAL_FUND",
            entity_id="120503",
            context={"scheme_name": "Axis Bluechip Fund", "nav": "54.20", "aum": "32000", "ter": "0.85", "active_share": 68.5}
        )
        self.assertEqual(mf_ledger["asset_class"], "MUTUAL_FUND")
        self.assertIn("AMFI", mf_ledger["verified_facts"][0]["source"])
        self.assertIn("Active Share", mf_ledger["calculated_metrics"][0]["metric"])

        # 2. Corporate Debt
        debt_ledger = build_multi_asset_epistemic_ledger(
            asset_class="DEBT",
            entity_id="INE002A08012",
            context={"issuer_name": "Reliance Industries Ltd", "coupon_rate": "7.79", "credit_rating": "AAA", "ytm": "7.82", "modified_duration": 4.1}
        )
        self.assertEqual(debt_ledger["asset_class"], "DEBT")
        self.assertIn("BSE Debt Segment", debt_ledger["verified_facts"][0]["source"])
        self.assertIn("Modified Duration", debt_ledger["calculated_metrics"][0]["metric"])

        # 3. REIT / InvIT
        reit_ledger = build_multi_asset_epistemic_ledger(
            asset_class="REIT",
            entity_id="EMBASSY",
            context={"name": "Embassy Office Parks REIT", "ndcf_distribution": "5.60", "wale": "6.8", "ltv_pct": "29.5", "post_tax_yield": "6.85"}
        )
        self.assertEqual(reit_ledger["asset_class"], "REIT")
        self.assertIn("Section 115UA", reit_ledger["verified_facts"][0]["passage"])
        self.assertIn("Post-Tax Real Yield", reit_ledger["calculated_metrics"][0]["metric"])

    def test_system_prompt_includes_epistemic_directive(self):
        """Verifies that get_system_prompt includes the epistemic separation and falsification directive."""
        prompt = get_system_prompt("TCS", "English (India)")
        self.assertIn("MANDATORY EPISTEMIC SEPARATION, SOURCE ATTRIBUTION & FALSIFICATION PROTOCOL", prompt)
        self.assertIn("[VERIFIED FACT]", prompt)
        self.assertIn("#### Falsification & Thesis-Revision Triggers", prompt)

    def test_compile_equity_dossier_attaches_epistemic_ledger(self):
        """Verifies that compile_equity_dossier attaches a valid epistemic_ledger to the intelligence package."""
        mock_fundamentals = {
            "current_price": 3500.0,
            "pe_ratio": 28.0,
            "sales_growth_3y": 14.0,
            "eps": 125.0,
            "debt_to_equity": 0.05,
            "promoter_pledge_pct": 0.0,
            "fcf_yield_pct": 4.2,
            "credit_rating": "AAA",
        }
        res = compile_equity_dossier(
            ticker="TCS",
            fundamentals=mock_fundamentals,
            company_name="Tata Consultancy Services Ltd",
            industry_str="Information Technology"
        )
        self.assertIn("epistemic_ledger", res)
        ledger = res["epistemic_ledger"]
        self.assertIsNotNone(ledger)
        self.assertIn("verified_facts", ledger)
        self.assertIn("calculated_metrics", ledger)
        self.assertIn("falsification_triggers", ledger)


if __name__ == "__main__":
    unittest.main()
