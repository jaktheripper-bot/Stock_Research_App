"""Unit tests for Epistemic Separation, Source-Passage Attribution & Falsification Engine.

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
    render_epistemic_badges_html,
    strip_conclusion_sections,
)
from core.analysis.parser import wrap_html_with_collapsible_pillars
from core.analysis.dossier_report_synthesis import get_system_prompt
from core.analysis.equity_dossier import compile_equity_dossier


class TestEpistemicSchemaAndFalsificationEngine(unittest.TestCase):
    """Test suite for epistemic separation, source attribution, and thesis falsification."""

    def test_epistemic_prompt_directive_structure(self):
        """Verifies that the prompt directive defines all 4 epistemic tiers and revision triggers block."""
        self.assertIn("[VERIFIED FACT]", EPISTEMIC_PROMPT_DIRECTIVE)
        self.assertIn("[CALCULATED METRIC]", EPISTEMIC_PROMPT_DIRECTIVE)
        self.assertIn("[MODEL INTERPRETATION]", EPISTEMIC_PROMPT_DIRECTIVE)
        self.assertIn("[UNRESOLVED UNCERTAINTY]", EPISTEMIC_PROMPT_DIRECTIVE)
        self.assertIn("#### What Would Change This View (Revision Triggers)", EPISTEMIC_PROMPT_DIRECTIVE)
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
#### What Would Change This View (Revision Triggers)
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
        self.assertIn("#### What Would Change This View (Revision Triggers)", prompt)

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

    def test_strip_conclusion_sections_preserves_falsification_and_contradicts(self):
        """Verifies that strip_conclusion_sections strips trailing conclusions while strictly preserving falsification triggers."""
        # 1. Empty/None handling
        self.assertEqual(strip_conclusion_sections(""), "")
        self.assertEqual(strip_conclusion_sections(None), "")

        # 2. Pillar with What Contradicts This Conclusion and Falsification Triggers followed by Conclusion
        sample_report = (
            "## Pillar 1: Moat & Market Architecture\n"
            "- Core moat is defensible via high switching costs.\n"
            "- [VERIFIED FACT (FY25 AR)] Operating margins expanded 180 bps.\n"
            "* **What Contradicts This Conclusion:** Raw material inflation exceeding 15% YoY.\n"
            "#### Falsification & Thesis-Revision Triggers:\n"
            "1. Operating margin drops below 14%.\n"
            "2. Debtor days increase > 25 days.\n\n"
            "## Conclusion & Final Verdict\n"
            "The stock is poised for long-term compounding.\n"
            "VERDICT: BUY"
        )
        cleaned = strip_conclusion_sections(sample_report)
        self.assertIn("What Contradicts This Conclusion", cleaned)
        self.assertIn("Falsification & Thesis-Revision Triggers", cleaned)
        self.assertIn("Debtor days increase > 25 days", cleaned)
        self.assertNotIn("## Conclusion & Final Verdict", cleaned)
        self.assertNotIn("poised for long-term compounding", cleaned)
        self.assertNotIn("VERDICT: BUY", cleaned)

        # 3. Text with What Would Change This View (Revision Triggers) should also be protected
        sample_new_title = (
            "## Pillar 1: Moat Architecture\n"
            "- Defensible margins.\n"
            "#### What Would Change This View (Revision Triggers):\n"
            "1. Margin drops below 10%.\n\n"
            "## Conclusion\n"
            "End of report."
        )
        cleaned_new = strip_conclusion_sections(sample_new_title)
        self.assertIn("What Would Change This View (Revision Triggers)", cleaned_new)
        self.assertNotIn("## Conclusion", cleaned_new)
        self.assertNotIn("End of report", cleaned_new)

        # 4. Text without conclusion should remain intact
        non_concl = (
            "## Pillar 1: Macro\n"
            "* **What Contradicts This Conclusion:** Rate hikes.\n"
            "#### Falsification & Thesis-Revision Triggers:\n"
            "1. CPI > 7%"
        )
        self.assertEqual(strip_conclusion_sections(non_concl), non_concl)

    def test_render_epistemic_badges_html(self):
        """Verifies that render_epistemic_badges_html converts epistemic tags into styled HTML pills."""
        # 1. Empty / None handling
        self.assertEqual(render_epistemic_badges_html(""), "")
        self.assertIsNone(render_epistemic_badges_html(None))

        # 2. Convert all 4 badge types with metadata passages
        html_input = (
            "<p>[VERIFIED FACT — BSE Audited FY25/Q3: Revenue stood at ₹4,500 Cr]</p>\n"
            "<p>[CALCULATED METRIC: RoCE = 24.8% (2-Stage DCF Intrinsic Value ₹1,650)]</p>\n"
            "<p>[MODEL INTERPRETATION: Specialty chemical moat protected by proprietary formulation patents]</p>\n"
            "<p>[UNRESOLVED UNCERTAINTY: Outcome of pending USFDA inspection at Unit-II facility]</p>"
        )
        rendered = render_epistemic_badges_html(html_input)

        # Check badge classes, icons, colors, and content
        self.assertIn("✓ VERIFIED FACT — BSE Audited FY25/Q3: Revenue stood at ₹4,500 Cr", rendered)
        self.assertIn("∑ CALCULATED METRIC: RoCE = 24.8%", rendered)
        self.assertIn("MODEL INTERPRETATION: Specialty chemical moat", rendered)
        self.assertIn("UNRESOLVED UNCERTAINTY: Outcome of pending USFDA inspection", rendered)
        self.assertIn("#icon-insights", rendered)
        self.assertIn("#glyph-alert", rendered)
        self.assertIn("color:#34d399", rendered)
        self.assertIn("color:#38bdf8", rendered)
        self.assertIn("color:#c084fc", rendered)
        self.assertIn("color:#fbbf24", rendered)

        # 3. Verify transformation of legacy falsification heading to What Would Change This View
        heading_html = "<h4>Falsification &amp; Thesis-Revision Triggers</h4><p>Details</p>"
        transformed = render_epistemic_badges_html(heading_html)
        self.assertIn("<h4>What Would Change This View (Revision Triggers)</h4>", transformed)
        self.assertNotIn("Falsification", transformed)

    def test_wrap_html_with_collapsible_pillars_renders_badges(self):
        """Verifies that wrap_html_with_collapsible_pillars passes body content through render_epistemic_badges_html."""
        sample_html = """
<h1>Executive Summary</h1>
<h2>Pillar 1: Macro-Economic Overlays</h2>
<p>[VERIFIED FACT (BSE)] Inflation steady at 4.2%.</p>
<h2>Pillar 2: Industry Dynamics & Moat</h2>
<p>[CALCULATED METRIC: Market share 34.2%].</p>
<h2>Pillar 3: Promoter Quality & Forensic Health</h2>
<p>[MODEL INTERPRETATION: Clean governance with zero pledging].</p>
<h2>Pillar 4: The Drop Diagnostic</h2>
<p>[UNRESOLVED UNCERTAINTY: Pending arbitration at NCLT].</p>
<h2>Pillar 5: Valuation & Margin of Safety</h2>
<p>Fair value assessment.</p>
<h2>Pillar 6: Technical & Momentum Overlay</h2>
<p>Trading above 50-DMA.</p>
<h2>Pillar 7: ESG Impact Scorecard</h2>
<p>BRSR Core compliant.</p>
"""
        wrapped = wrap_html_with_collapsible_pillars(sample_html, scrip_code="500209", ticker="INFY")
        self.assertIn("✓ VERIFIED FACT", wrapped)
        self.assertIn("∑ CALCULATED METRIC", wrapped)
        self.assertIn("MODEL INTERPRETATION", wrapped)
        self.assertIn("UNRESOLVED UNCERTAINTY", wrapped)
        self.assertIn("#icon-insights", wrapped)
        self.assertIn("#glyph-alert", wrapped)
        self.assertIn("Open BSE Financial Results ↗", wrapped)
        self.assertNotIn("Open BSE BSE", wrapped)

    def test_outside_in_dossier_dom_renders_epistemic_card_and_badges(self):
        """Rule 6 Outside-In verification: asserts #epistemicFalsificationCard and .epistemic-badge render in DOM across all 4 dossier routes."""
        from bs4 import BeautifulSoup
        from fastapi.testclient import TestClient
        from web.main import app

        client = TestClient(app)
        routes = [
            "/dossier/TCS",
            "/funds/122639",
            "/debt/INE002A08012",
            "/reits/EMBASSY",
        ]
        for route in routes:
            resp = client.get(route)
            self.assertEqual(resp.status_code, 200, f"Expected 200 OK on {route}")
            html = resp.text
            self.assertNotIn("{{", html, f"Unrendered Jinja expression found on {route}")
            self.assertNotIn("{%", html, f"Unrendered Jinja tag found on {route}")

            soup = BeautifulSoup(html, "html.parser")
            card = soup.find(id="epistemicFalsificationCard")
            self.assertIsNotNone(card, f"#epistemicFalsificationCard missing from rendered DOM on {route}")

            badges = card.select(".epistemic-badge")
            self.assertGreaterEqual(len(badges), 4, f"Expected >=4 .epistemic-badge pills inside #epistemicFalsificationCard on {route}")

            # Verify falsification matrix table rows render
            rows = card.select("table tbody tr")
            self.assertGreaterEqual(len(rows), 1, f"Expected >=1 falsification trigger row on {route}")


if __name__ == "__main__":
    unittest.main()
