"""Unit tests for SEBI Mutual Fund Universe Ranking, Collision-Proof Sheet Matching, and Legacy Twin Resolution (L2, L3, L4)."""
import io
import unittest
import zipfile

import openpyxl

from core.db.mutual_funds import canonical_twin_stem, resolve_legacy_slug_twins
from core.ingestion.mf_portfolio_parser import (
    extract_formerly_aliases,
    match_scheme_name,
    match_schemes_to_workbook_sheets,
    parse_workbook,
    sniff_format,
)
from core.ingestion.mf_universe import rank_funds_by_aum


def _build_xlsx_bytes(sheets: dict) -> bytes:
    wb = openpyxl.Workbook()
    first = True
    for title, rows in sheets.items():
        if first:
            ws = wb.active
            ws.title = title
            first = False
        else:
            ws = wb.create_sheet(title=title)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestMFPortfolioParserAndUniverseGuards(unittest.TestCase):
    def test_rank_funds_retains_dividend_yield_direct_growth(self):
        """L2 Guard: Dividend Yield Direct-Growth schemes must NOT be dropped by non-growth payout filter."""
        sample_aaum = [
            {
                "SchemeCat_Desc": "Open Ended Schemes(Equity Scheme - Dividend Yield Fund)",
                "schemes": [
                    {
                        "AMFI_Code": "120590",
                        "SchemeNAVName": "ICICI Prudential Dividend Yield Equity Fund - Direct Plan - Growth",
                        "MF_Name": "ICICI Prudential Mutual Fund",
                        "AverageAumForTheMonth": {
                            "ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas": 485000.0
                        },
                    },
                    {
                        "AMFI_Code": "120591",
                        "SchemeNAVName": "ICICI Prudential Dividend Yield Equity Fund - Direct Plan - IDCW Payout",
                        "MF_Name": "ICICI Prudential Mutual Fund",
                        "AverageAumForTheMonth": {
                            "ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas": 485000.0
                        },
                    },
                    {
                        "AMFI_Code": "120592",
                        "SchemeNAVName": "Templeton India Equity Income Fund - Direct - Dividend Option",
                        "MF_Name": "Franklin Templeton Mutual Fund",
                        "AverageAumForTheMonth": {
                            "ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas": 220000.0
                        },
                    },
                ],
            },
            {
                "SchemeCat_Desc": "Open Ended Schemes(Equity Scheme - Focused Fund)",
                "schemes": [
                    {
                        "AMFI_Code": "119727",
                        "SchemeNAVName": "SBI Focused Fund - Direct Plan - Growth",
                        "MF_Name": "SBI Mutual Fund",
                        "AverageAumForTheMonth": {
                            "ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas": 3460000.0
                        },
                    }
                ],
            },
        ]

        ranked = rank_funds_by_aum(aaum_data=sample_aaum)
        codes = [r["scheme_code"] for r in ranked]
        self.assertIn("120590", codes, "Direct-Growth Dividend Yield fund must be retained!")
        self.assertIn("119727", codes)
        self.assertNotIn("120591", codes, "IDCW Payout option must be excluded!")
        self.assertNotIn("120592", codes, "Dividend Option payout scheme must be excluded!")

    def test_numeric_and_qualifier_collision_guard_across_corpus(self):
        """L3 Guard: Nifty 50 vs Nifty 500, Midcap 150 vs Midcap 50, Large Cap vs Large & Mid Cap must NEVER cross-match."""
        candidates = [
            "UTI Nifty 500 Value 50 Index Fund",
            "Motilal Oswal Nifty Midcap 50 Index Fund",
            "Aditya Birla Sun Life Large & Mid Cap Fund",
            "SBI Short Term Debt Fund",
        ]

        # Numeric collision attempts -> must return None rather than fuzzy-colliding!
        self.assertIsNone(match_scheme_name("UTI Nifty 50 Index Fund - Direct Plan - Growth", candidates))
        self.assertIsNone(match_scheme_name("Motilal Oswal Nifty Midcap 150 Index Fund - Direct Plan - Growth", candidates))

        # Qualifier collision attempts -> Large Cap must NOT match Large & Mid Cap; Ultra Short must NOT match Short Term
        self.assertIsNone(match_scheme_name("Aditya Birla Sun Life Large Cap Fund - Direct Plan - Growth", candidates))
        self.assertIsNone(match_scheme_name("SBI Ultra Short Duration Fund - Direct Plan - Growth", candidates))

        # Exact counterparts -> must match cleanly!
        self.assertEqual(
            match_scheme_name("Aditya Birla Sun Life Large & Mid Cap Fund - Direct Plan - Growth", candidates),
            "Aditya Birla Sun Life Large & Mid Cap Fund",
        )
        self.assertEqual(
            match_scheme_name("UTI Nifty 500 Value 50 Index Fund - Direct Plan - Growth", candidates),
            "UTI Nifty 500 Value 50 Index Fund",
        )

    def test_bipartite_workbook_matching_and_zip_index_formerly_aliases(self):
        """L3 Guard: ZIP multi-workbook bundles, Index shortcode sheets, and (Formerly known as ...) aliases parse cleanly."""
        wb1 = _build_xlsx_bytes({
            "Index": [
                ["Sr No", "Short Code", "Scheme Name"],
                [1, "ABSL01", "Aditya Birla Sun Life Large & Mid Cap Fund (Formerly known as Aditya Birla Sun Life Equity Advantage Fund)"],
            ],
            "ABSL01": [
                ["Aditya Birla Sun Life Mutual Fund"],
                ["Monthly Portfolio Statement as on October 31, 2026"],
                ["Name of the Instrument", "ISIN", "Industry", "Quantity", "Market Value", "% to NAV"],
                ["Equity & Equity related"],
                ["HDFC Bank Limited", "INE040A01034", "Banks", 100000, 1750.0, 52.5],
                ["Infosys Limited", "INE009A01021", "IT - Software", 80000, 1450.0, 43.5],
                ["TREPS / Reverse Repo", "", "CASH", 0, 133.0, 4.0],
            ],
        })
        wb2 = _build_xlsx_bytes({
            "GILT": [
                ["Franklin India Gilt Fund - Monthly Portfolio as on 31-Oct-2026"],
                ["ISIN", "Name of the Instrument", "Rating", "Quantity", "Market Value", "% to Net Assets"],
                ["Government Securities"],
                ["IN0020230085", "7.18% GOI 2033", "SOVEREIGN", 500000, 5100.0, 96.0],
                ["", "Net Current Assets", "CASH", 0, 212.5, 4.0],
            ],
        })

        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("equity_schemes.xlsx", wb1)
            zf.writestr("debt_schemes.xlsx", wb2)
        zip_bytes = zbuf.getvalue()

        self.assertEqual(sniff_format(wb1), "xlsx")
        self.assertEqual(sniff_format(zip_bytes), "zip")
        self.assertEqual(
            extract_formerly_aliases("ABSL Large & Mid Cap Fund (Formerly known as Aditya Birla Sun Life Equity Advantage Fund)"),
            ["Aditya Birla Sun Life Equity Advantage Fund"],
        )

        parsed = parse_workbook(zip_bytes)
        self.assertEqual(len(parsed), 2)

        schemes = [
            {"scheme_code": "119436", "scheme_name": "Aditya Birla Sun Life Equity Advantage Fund - Direct Plan - Growth"},
            {"scheme_code": "118498", "scheme_name": "Franklin India Gilt Fund - Direct - Growth"},
        ]
        matched = match_schemes_to_workbook_sheets(schemes, parsed)
        self.assertIn("119436", matched)
        self.assertIn("118498", matched)
        self.assertNotEqual(matched["119436"], matched["118498"])

    def test_legacy_slug_sebi_rename_twin_resolution(self):
        """L4 Guard: Legacy 200 slug schemes resolve to their renamed 6-digit AMFI twin without collapsing distinct numeric schemes."""
        schemes = [
            {
                "scheme_code": "SBI_FOCUSED_DIR",
                "scheme_name": "SBI Focused Equity Fund - Direct Plan - Growth",
                "fund_house": "SBI Mutual Fund",
                "category": "Equity - Focused",
                "aum_crores": 32000.0,
                "metadata": {},
            },
            {
                "scheme_code": "119727",
                "scheme_name": "SBI Focused Fund - Direct Plan - Growth",
                "fund_house": "SBI Mutual Fund",
                "category": "Equity Scheme - Focused Fund",
                "aum_crores": 34600.0,
                "metadata": {"holdings_source": "sebi_monthly_disclosure"},
            },
            {
                "scheme_code": "ABSL_FRONTLINE_DIR",
                "scheme_name": "Aditya Birla Sun Life Frontline Equity Fund - Direct Plan - Growth",
                "fund_house": "Aditya Birla Sun Life Mutual Fund",
                "category": "Equity - Large Cap",
                "aum_crores": 26000.0,
                "metadata": {},
            },
            {
                "scheme_code": "119598",
                "scheme_name": "Aditya Birla Sun Life Large Cap Fund - Direct Plan - Growth",
                "fund_house": "Aditya Birla Sun Life Mutual Fund",
                "category": "Equity Scheme - Large Cap Fund",
                "aum_crores": 29500.0,
                "metadata": {"holdings_source": "sebi_monthly_disclosure"},
            },
        ]
        self.assertEqual(
            canonical_twin_stem("Aditya Birla Sun Life Frontline Equity Fund - Direct Plan - Growth"),
            canonical_twin_stem("Aditya Birla Sun Life Large Cap Fund - Direct Plan - Growth"),
        )
        twins = resolve_legacy_slug_twins(schemes)
        self.assertEqual(twins.get("SBI_FOCUSED_DIR"), "119727")
        self.assertEqual(twins.get("ABSL_FRONTLINE_DIR"), "119598")


if __name__ == "__main__":
    unittest.main()
