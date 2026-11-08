"""Unit tests for typed metric contracts, Fisher real returns, CSV safety, and fund coverage invariants."""

from datetime import date
import math
import unittest

from core.analysis.financial_invariants import (
    compute_active_share,
    evaluate_fund_coverage,
    is_synthesizable_domestic_ticker,
    real_return,
    real_return_pct,
    requires_positive_convexity,
)
from core.analysis.metric_contract import (
    AccessState,
    EvidenceKind,
    FreshnessStatus,
    MEASURE_MAX_AGE_DAYS,
    MetricContract,
    build_observed_metric,
    has_forbidden_vendor_token,
    sanitize_csv_cell,
    sort_key,
)


class TestMetricAndFinancialInvariants(unittest.TestCase):
    def test_metric_contracts_and_forbidden_vendor_tokens(self):
        self.assertIn("CONTRACTUAL_YTM", MEASURE_MAX_AGE_DAYS)
        self.assertEqual(MEASURE_MAX_AGE_DAYS["CONTRACTUAL_YTM"], 7)
        self.assertEqual(MEASURE_MAX_AGE_DAYS["HISTORICAL_CAGR_3Y"], 45)

        for forbidden in (
            "yfinance",
            "Yahoo Finance",
            "https://www.morningstar.in/funds/123",
            "Screener.in",
            "Trendlyne Consensus",
            "TickerTape",
            "ValueResearch Online",
            "Moneycontrol",
            "mfforecast_api",
            "mfapi.in",
        ):
            self.assertTrue(has_forbidden_vendor_token(forbidden), forbidden)

        for allowed in (
            "NSE Debt Market Quote",
            "https://www.nseindia.com/market-data/bonds-traded-in-capital-market",
            "RBI Retail Direct Auction Result",
            "AMC Monthly Factsheet",
            "SEBI Statutory Portfolio Disclosure",
        ):
            self.assertFalse(has_forbidden_vendor_token(allowed), allowed)

        with self.assertRaises(ValueError):
            MetricContract(
                instrument_id="X",
                measure_type="CONTRACTUAL_YTM",
                value=None,
                unit="%",
                evidence_kind=EvidenceKind.UNAVAILABLE,
                freshness=FreshnessStatus.UNAVAILABLE,
                access=AccessState.LOCKED,
            )

    def test_build_observed_metric_preserves_zero_and_withholds_vendor_or_stale_values(self):
        today = date(2026, 11, 8)
        zero_obs = build_observed_metric(
            "TEST_EQ",
            "DIVIDEND_YIELD_TTM",
            0.0,
            "%",
            "2026-11-05",
            "NSE Corporate Filing",
            today=today,
        )
        self.assertEqual(zero_obs.freshness, FreshnessStatus.AVAILABLE)
        self.assertEqual(zero_obs.current_value, 0.0)

        stale_obs = build_observed_metric(
            "INE001A08011",
            "CONTRACTUAL_YTM",
            8.75,
            "%",
            "2026-10-20",
            "https://www.nseindia.com/bonds/quote",
            today=today,
        )
        self.assertEqual(stale_obs.freshness, FreshnessStatus.STALE)
        self.assertIsNone(stale_obs.current_value)
        self.assertEqual(stale_obs.historical_value, 8.75)

        vendor_obs = build_observed_metric(
            "122639",
            "HISTORICAL_CAGR_3Y",
            18.4,
            "%",
            "2026-11-05",
            "Morningstar India",
            today=today,
        )
        self.assertEqual(vendor_obs.freshness, FreshnessStatus.UNAVAILABLE)
        self.assertIsNone(vendor_obs.current_value)

        nan_obs = build_observed_metric(
            "INE001A08011",
            "CONTRACTUAL_YTM",
            math.nan,
            "%",
            "2026-11-05",
            "NSE Quote",
            today=today,
        )
        self.assertEqual(nan_obs.freshness, FreshnessStatus.UNAVAILABLE)

        ranked = sorted(
            [stale_obs, zero_obs],
            key=lambda m: sort_key(m, comparison_group="DIVIDEND_YIELD_TTM:EQUITY"),
        )
        self.assertEqual(ranked[0].instrument_id, "TEST_EQ")

    def test_csv_cell_sanitization_preserves_negative_numbers_and_quotes_formulas(self):
        self.assertEqual(sanitize_csv_cell(None), "")
        self.assertEqual(sanitize_csv_cell(-3.25), '"-3.25"')
        self.assertEqual(sanitize_csv_cell(0), '"0"')
        self.assertEqual(sanitize_csv_cell(9.45), '"9.45"')
        self.assertEqual(sanitize_csv_cell("=SUM(A1:A5)"), '"\'=SUM(A1:A5)"')
        self.assertEqual(sanitize_csv_cell("+CMD|' /C calc'!A0"), '"\'+CMD|\' /C calc\'!A0"')
        self.assertEqual(sanitize_csv_cell("-CMD()"), '"\'-CMD()"')
        self.assertEqual(sanitize_csv_cell("@IMPORTXML(A1,B1)"), '"\'@IMPORTXML(A1,B1)"')
        self.assertEqual(sanitize_csv_cell("\t=1+1"), '"\'\t=1+1"')

    def test_fisher_real_return_exact_compounding(self):
        # (1 + 0.1025) / (1 + 0.05) - 1 = 0.05 exact (whereas naive subtraction gives 0.0525)
        self.assertAlmostEqual(real_return(0.1025, 0.05), 0.05, places=9)
        self.assertAlmostEqual(real_return_pct(10.25, 5.0), 5.0, places=4)
        # Deflation (-2% CPI): real return exceeds nominal return
        self.assertGreater(real_return_pct(6.0, -2.0), 8.0)
        with self.assertRaises(ValueError):
            real_return_pct(8.0, -100.0)

    def test_positive_convexity_and_active_share_clamping(self):
        self.assertTrue(requires_positive_convexity(is_option_free=True))
        self.assertFalse(requires_positive_convexity(is_option_free=False))
        self.assertFalse(requires_positive_convexity(is_option_free=True, is_perpetual=True))
        self.assertFalse(requires_positive_convexity(is_option_free=True, has_floating_reset=True))

        disjoint = compute_active_share({"HDFCBANK": 60.0, "INFY": 40.0}, {"RELIANCE": 50.0, "TCS": 50.0})
        self.assertEqual(disjoint.active_share_pct, 100.0)
        identical = compute_active_share({"HDFCBANK": 60.0, "INFY": 40.0}, {"HDFCBANK": 60.0, "INFY": 40.0})
        self.assertEqual(identical.active_share_pct, 0.0)
        clamped = compute_active_share({"HDFCBANK": 120.0}, {"RELIANCE": 120.0})
        self.assertEqual(clamped.active_share_pct, 100.0)

    def test_domestic_ticker_eligibility_and_fund_coverage_denominators(self):
        self.assertTrue(is_synthesizable_domestic_ticker("RELIANCE", "EQUITY"))
        self.assertTrue(is_synthesizable_domestic_ticker("M&M", "EQUITY"))
        self.assertTrue(is_synthesizable_domestic_ticker("BAJAJ-AUTO", "EQUITY"))
        self.assertFalse(is_synthesizable_domestic_ticker("GOOGL", "FOREIGN_EQUITY"))
        self.assertFalse(is_synthesizable_domestic_ticker("GOOGL", "EQUITY"))
        self.assertFalse(is_synthesizable_domestic_ticker("META", "EQUITY"))
        self.assertFalse(is_synthesizable_domestic_ticker("INE009A01021", "EQUITY"))
        self.assertFalse(is_synthesizable_domestic_ticker("US02079K3059", "EQUITY"))

        # Fund with 65% covered equity + 27% uncovered equity + 8% cash (92% equity sleeve, 65% full NAV)
        holdings = [
            {"identifier": "HDFCBANK", "holding_type": "EQUITY", "weight_pct": 40.0},
            {"identifier": "INFY", "holding_type": "EQUITY", "weight_pct": 25.0},
            {"identifier": "UNCOV1", "holding_type": "EQUITY", "weight_pct": 9.0},
            {"identifier": "UNCOV2", "holding_type": "EQUITY", "weight_pct": 9.0},
            {"identifier": "UNCOV3", "holding_type": "EQUITY", "weight_pct": 9.0},
            {"identifier": "TREPS", "holding_type": "CASH_EQUIVALENT", "weight_pct": 8.0},
        ]
        summary = evaluate_fund_coverage(holdings, {"HDFCBANK", "INFY"}, threshold_pct=70.0)
        self.assertEqual(summary.full_nav_eligible_pct, 65.0)
        self.assertAlmostEqual(summary.eligible_equity_pct, round(65.0 / 92.0 * 100.0, 2), places=2)
        self.assertTrue(summary.meets_aggregate_gate)

        # Single uncovered holding >= 10% blocks aggregate gate even when >= 70% covered
        concentrated_gap = [
            {"identifier": "HDFCBANK", "holding_type": "EQUITY", "weight_pct": 75.0},
            {"identifier": "BIGGAP", "holding_type": "EQUITY", "weight_pct": 12.0},
            {"identifier": "TREPS", "holding_type": "CASH_EQUIVALENT", "weight_pct": 13.0},
        ]
        blocked = evaluate_fund_coverage(concentrated_gap, {"HDFCBANK"}, threshold_pct=70.0)
        self.assertFalse(blocked.meets_aggregate_gate)


if __name__ == "__main__":
    unittest.main()
