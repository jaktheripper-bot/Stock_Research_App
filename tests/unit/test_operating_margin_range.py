import unittest

from core.db.fundamentals import (
    _extract_operating_margin_range_midpoint,
    extract_fundamentals_from_report_text,
)


class TestOperatingMarginRangeMidpoint(unittest.TestCase):
    """Report prose that states operating margin only as a range resolves to the range midpoint."""

    def test_own_margin_range_resolves_to_midpoint(self):
        cases = {
            "- **Operating Margins:** Operating margin stands firm between 24.0% and 25.3%.": 24.65,
            "- **Operating Margins:** EBITDA margins remain steady between 14.0% and 15.1%": 14.55,
            "- **Operating Margins:** Consolidated EBITDA margins sit between 13% and 14%": 13.5,
            "Operating profit margin (OPM) ranged between 6.5% and 8.0%.": 7.25,
            "Revenue grew 12%. Operating EBITDA margins typically hover between 13% and 14%.": 13.5,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(_extract_operating_margin_range_midpoint(text), expected)
                self.assertEqual(extract_fundamentals_from_report_text(text).get("operating_margin"), expected)

    def test_rejects_ranges_that_are_not_the_company_own_historical_margin(self):
        rejected = [
            # subsidiary / peer named as the subject
            "- **Unit Economics & Operating Margins:** CG Power generates operating margins between 13.0% and 14.5%",
            # industry-wide figure
            "Industry EBITDA margins, which historically ranged between 20% and 22%",
            # single segment
            "Consequently, operating margins in edible oils fluctuate between 1.5% and 3.5%",
            "- **Operating Leverage:** Core retail leasing EBITDA margins consistently range between 58% and 62%",
            # forward-looking guidance
            "Management expects EBITDA margins between 18% and 20% next year.",
            "EBITDA margins are targeted between 18% and 20%.",
            # spread wider than 10 points
            "EBITDA margins between 10% and 25%.",
            # inverted range
            "EBITDA margins between 20% and 15%.",
        ]
        for text in rejected:
            with self.subTest(text=text):
                self.assertIsNone(_extract_operating_margin_range_midpoint(text))

    def test_single_stated_margin_takes_precedence_over_range(self):
        text = (
            "- **Operating Margins:** Operating margin stood at 21.4%.\n"
            "Over the cycle, EBITDA margins ranged between 18% and 20%."
        )
        self.assertEqual(extract_fundamentals_from_report_text(text).get("operating_margin"), 21.4)

    def test_degraded_inputs_return_no_margin(self):
        for text in ("", None, "No margin disclosure in this report."):
            with self.subTest(text=text):
                self.assertIsNone(_extract_operating_margin_range_midpoint(text))


if __name__ == "__main__":
    unittest.main()
