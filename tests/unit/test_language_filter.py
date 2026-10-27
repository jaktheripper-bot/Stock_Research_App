"""Unit tests for the English (India) Language and Report Quality Filter.

Verifies:
1. Exact vocabulary conversions and inflections.
2. Dynamic suffix rules (-ize -> -ise, -yze -> -yse).
3. Casing preservation (lowercase, TitleCase, ALL CAPS, hyphenated compounds).
4. Protected words, brand names, and root words (Pfizer, size, mid-sized, prize, seize, universal -or words).
5. Technical shielding (URLs, Markdown links, HTML tags, inline code, code blocks, epistemic tags).
6. Discrepancy detection (detect_americanisms).
7. Comprehensive report quality audit (audit_report_quality).
"""

import unittest
from core.analysis.language_filter import (
    enforce_indian_english,
    detect_americanisms,
    audit_report_quality,
    ReportQualityResult,
)


class TestIndianEnglishConversions(unittest.TestCase):
    def test_explicit_spelling_conversions(self):
        cases = [
            ("The capitalization of the firm has surged.", "The capitalisation of the firm has surged."),
            ("We prioritize labor efficiency and favor automation.", "We prioritise labour efficiency and favour automation."),
            ("The defense sector is seeing higher government favors.", "The defence sector is seeing higher government favours."),
            ("The company is modeling and signaling strong growth.", "The company is modelling and signalling strong growth."),
            ("Please review the product catalog and dialogue notes.", "Please review the product catalogue and dialogue notes."),
            ("The operations center is undergoing fiber upgrades.", "The operations centre is undergoing fibre upgrades."),
            ("The aging workforce requires careful judgment.", "The ageing workforce requires careful judgement."),
            ("Customer fulfillment and installment payments are smooth.", "Customer fulfilment and instalment payments are smooth."),
            ("They launched an employee wellness program.", "They launched an employee wellness programme."),
            ("We analyze the competitive behavior rigorously.", "We analyse the competitive behaviour rigorously."),
        ]
        for src, expected in cases:
            self.assertEqual(enforce_indian_english(src), expected)

    def test_casing_preservation(self):
        # Lowercase
        self.assertEqual(enforce_indian_english("monetize"), "monetise")
        self.assertEqual(enforce_indian_english("favorable"), "favourable")
        # TitleCase
        self.assertEqual(enforce_indian_english("Optimization"), "Optimisation")
        self.assertEqual(enforce_indian_english("Behavior"), "Behaviour")
        # UPPERCASE
        self.assertEqual(enforce_indian_english("CAPITALIZATION"), "CAPITALISATION")
        self.assertEqual(enforce_indian_english("LABOR"), "LABOUR")

    def test_compounds_and_hyphenation(self):
        self.assertEqual(enforce_indian_english("cost-optimization"), "cost-optimisation")
        self.assertEqual(enforce_indian_english("labor-intensive"), "labour-intensive")
        self.assertEqual(enforce_indian_english("high-priority-signaling"), "high-priority-signalling")

    def test_preserved_size_roots_and_exceptions(self):
        # Crucial: size, mid-sized, downsized must NEVER be converted to sise
        self.assertEqual(enforce_indian_english("mid-sized"), "mid-sized")
        self.assertEqual(enforce_indian_english("large-sized"), "large-sized")
        self.assertEqual(enforce_indian_english("small-sized"), "small-sized")
        self.assertEqual(enforce_indian_english("downsized"), "downsized")
        self.assertEqual(enforce_indian_english("oversized"), "oversized")
        self.assertEqual(enforce_indian_english("sizing"), "sizing")
        self.assertEqual(enforce_indian_english("sizable"), "sizable")
        self.assertEqual(enforce_indian_english("prize"), "prize")
        self.assertEqual(enforce_indian_english("seize"), "seize")
        self.assertEqual(enforce_indian_english("capsize"), "capsize")

    def test_preserved_brand_names_and_proper_nouns(self):
        self.assertEqual(enforce_indian_english("Pfizer Ltd shares rallied."), "Pfizer Ltd shares rallied.")
        self.assertEqual(enforce_indian_english("Amazon and Citizen are global brands."), "Amazon and Citizen are global brands.")
        self.assertEqual(enforce_indian_english("ICICI Bank InstaBIZ app"), "ICICI Bank InstaBIZ app")
        self.assertEqual(enforce_indian_english("Lubrizol and Horizon investments"), "Lubrizol and Horizon investments")

    def test_universal_or_words_not_converted_to_our(self):
        # Words ending in -or in both British and American English must remain intact
        text = "The sector factor was reviewed by the director, doctor, auditor, investor, and regulator."
        self.assertEqual(enforce_indian_english(text), text)


class TestTechnicalShielding(unittest.TestCase):
    def test_url_shielding(self):
        text = "Check the defense report at https://sec.gov/defense/prioritize-filings.html before reading."
        expected = "Check the defence report at https://sec.gov/defense/prioritize-filings.html before reading."
        self.assertEqual(enforce_indian_english(text), expected)

    def test_markdown_link_shielding(self):
        text = "Refer to [Defense Sector Review](https://example.com/defense/prioritize) for details."
        expected = "Refer to [Defence Sector Review](https://example.com/defense/prioritize) for details."
        self.assertEqual(enforce_indian_english(text), expected)

    def test_code_block_shielding(self):
        text = "```python\ndef prioritize_task(labor_cost):\n    return labor_cost * 1.1\n```\nWe prioritize labor efficiency."
        res = enforce_indian_english(text)
        self.assertIn("def prioritize_task(labor_cost):", res)
        self.assertIn("We prioritise labour efficiency.", res)

    def test_inline_code_shielding(self):
        text = "Run `normalize_data(prioritize=True)` to optimize performance."
        expected = "Run `normalize_data(prioritize=True)` to optimise performance."
        self.assertEqual(enforce_indian_english(text), expected)

    def test_html_tag_shielding(self):
        text = '<div class="color-picker" data-action="prioritize">Our color strategy is sound.</div>'
        expected = '<div class="color-picker" data-action="prioritize">Our colour strategy is sound.</div>'
        self.assertEqual(enforce_indian_english(text), expected)

    def test_epistemic_tags_shielding(self):
        text = "[VERIFIED FACT] The operating profit margin expanded to 18.2%.\n[MODEL INTERPRETATION] Market capitalisation is resilient."
        res = enforce_indian_english(text)
        self.assertIn("[VERIFIED FACT]", res)
        self.assertIn("[MODEL INTERPRETATION]", res)


class TestAmericanismDetection(unittest.TestCase):
    def test_detects_americanisms_with_line_numbers(self):
        content = "Line one is fine.\nLine two mentions labor costs and capitalization.\nLine three is clean."
        issues = detect_americanisms(content)
        self.assertEqual(len(issues), 2)
        words = [i["word"].lower() for i in issues]
        self.assertIn("labor", words)
        self.assertIn("capitalization", words)
        self.assertEqual(issues[0]["line"], 2)
        self.assertEqual(issues[1]["line"], 2)

    def test_clean_text_returns_no_issues(self):
        content = "The market capitalisation of the company reflects strong operational behaviour and defence focus."
        issues = detect_americanisms(content)
        self.assertEqual(issues, [])


class TestAuditReportQuality(unittest.TestCase):
    def test_quality_audit_high_score(self):
        mock_report = """# Comprehensive Equity Research Dossier: INFOSYS LTD (INFY)
[VERIFIED FACT] Market capitalisation stands at ₹6,45,000 Cr as of Q3 FY26.

## Pillar 1: Macro-Economic, Geopolitical & Environmental Overlays
The macroeconomic environment remains stable across global BFSI and enterprise cloud spending.

## Pillar 2: Industry Dynamics & Competitive Positioning
The business benefits from high switching costs and proprietary platforms in IT services.

## Pillar 3: Promoter Quality & Fundamental Health
Beneish M-Score confirms clean accounting with zero revenue inflation and pristine promoter integrity.

## Pillar 4: The "Structural vs. Temporary" Drop Diagnostic
Recent growth moderations represent cyclical delays rather than structural client attrition.

## Pillar 5: Valuation & Margin of Safety
Trading at 24.5x PE against a 5-year historical median of 26.0x, offering reasonable margin of safety.

## Pillar 6: Technical & Momentum Overlay
Moving averages show consolidation near the 200-DMA with healthy accumulation patterns.

## Pillar 7: ESG Impact Scorecard
| Parameter | Score | Key Drivers |
|:---|:---:|:---|
| **Environmental** | 85/100 | Carbon neutral campus operations and water recycling. |
| **Social** | 82/100 | High labour retention and gender diversity programmes. |
| **Governance** | 92/100 | Independent board oversight with clean auditor remarks. |

### Revision Triggers & Falsification Conditions
- Trigger 1: Core operating margin dropping below 19.5% for two consecutive quarters.
- Trigger 2: Attrition exceeding 22% indicating structural talent drain.

[CALCULATED METRIC] Return on Equity (ROE): 31.4%
[MODEL INTERPRETATION] Fair value intrinsic range estimates moderate upside.
[UNRESOLVED UNCERTAINTY] Geopolitical spending headwinds in European manufacturing clients.
"""
        result = audit_report_quality(mock_report)
        self.assertIsInstance(result, ReportQualityResult)
        self.assertTrue(result.passed)
        self.assertGreaterEqual(result.quality_score, 85.0)
        self.assertEqual(result.americanisms, [])
        self.assertEqual(len(result.missing_pillars), 0)

    def test_quality_audit_flags_deficiencies(self):
        bad_report = """# Stock Report on XYZ Corp
This report issues a strong buy verdict with an ambitious target price: ₹1500 per share.
The company generated INR 500 million in quarterly revenue, showing solid top-line acceleration.
We prioritize cost-cutting, labor rationalization, and operational optimization across our defense units.
Management intends to commercialize the new product line while signaling strong customer demand.
The operations center is undergoing fiber upgrades to improve customer fulfillment.
"""
        result = audit_report_quality(bad_report)
        self.assertFalse(result.passed)
        self.assertLess(result.quality_score, 60.0)
        # Should flag Americanisms
        self.assertGreater(len(result.americanisms), 0)
        # Should flag compliance risks (strong buy verdict, target price)
        self.assertGreater(len(result.compliance_risks), 0)
        # Should flag missing pillars
        self.assertGreater(len(result.missing_pillars), 0)
        # Should flag missing epistemic tags
        self.assertGreater(len(result.epistemic_deficiencies), 0)


class TestCheckerIntegration(unittest.TestCase):
    def test_checker_flags_americanisms(self):
        from checker import verify_stock_report
        stock_data = {"short_name": "Test Corp", "ticker": "TEST"}
        report_with_americanism = """# DIAGNOSTIC SUMMARY
Strong fundamentals.
## Pillar 1: Macro
Clean.
## Pillar 2: Industry
Clean.
## Pillar 3: Promoter
Clean.
## Pillar 4: Structural Drop
Clean.
## Pillar 5: Valuation
Clean.
## Pillar 6: Technical
Clean.
## Pillar 7: ESG Impact Scorecard
| Parameter | Score | Factors |
| **Environmental** | 80/100 | Clean |
| **Social** | 80/100 | Clean |
| **Governance** | 80/100 | Clean |

We prioritize cost reduction and analyze the market.
"""
        valid, discrepancies = verify_stock_report(stock_data, report_with_americanism)
        self.assertFalse(valid)
        self.assertTrue(any("Americanisms" in d for d in discrepancies))

    def test_checker_passes_clean_indian_english(self):
        from checker import verify_stock_report
        stock_data = {"short_name": "Test Corp", "ticker": "TEST"}
        clean_report = """# DIAGNOSTIC SUMMARY
Strong fundamentals.
## Pillar 1: Macro
Clean.
## Pillar 2: Industry
Clean.
## Pillar 3: Promoter
Clean.
## Pillar 4: Structural Drop
Clean.
## Pillar 5: Valuation
Clean.
## Pillar 6: Technical
Clean.
## Pillar 7: ESG Impact Scorecard
| Parameter | Score | Factors |
| **Environmental** | 80/100 | Clean |
| **Social** | 80/100 | Clean |
| **Governance** | 80/100 | Clean |

We prioritise cost reduction and analyse the market. Market capitalisation is resilient.
"""
        valid, discrepancies = verify_stock_report(stock_data, clean_report)
        self.assertTrue(valid, f"Unexpected discrepancies: {discrepancies}")


if __name__ == "__main__":
    unittest.main()
