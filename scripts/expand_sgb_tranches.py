"""Expands DEFAULT_SGB_TRANCHES in core/db/reits.py to all 36 active RBI Sovereign Gold Bond series."""

from pathlib import Path

FULL_SGB_TRANCHES = [
    {
        "symbol": "SGBNOV25",
        "series_name": "Sovereign Gold Bond 2017-18 Series VII",
        "issue_price": 2961.0,
        "market_price": 7380.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -0.94,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2025-11-27",
        "ytm_annualized_pct": 8.65,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 1.85
    },
    {
        "symbol": "SGBDEC25",
        "series_name": "Sovereign Gold Bond 2017-18 Series IX",
        "issue_price": 2890.0,
        "market_price": 7350.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -1.34,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2025-12-04",
        "ytm_annualized_pct": 8.72,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 1.88
    },
    {
        "symbol": "SGBJAN26",
        "series_name": "Sovereign Gold Bond 2017-18 Series XII",
        "issue_price": 2881.0,
        "market_price": 7310.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -1.88,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2026-01-22",
        "ytm_annualized_pct": 8.78,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 1.90
    },
    {
        "symbol": "SGBFEB26",
        "series_name": "Sovereign Gold Bond 2017-18 Series XIV",
        "issue_price": 2906.0,
        "market_price": 7290.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -2.15,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2026-02-26",
        "ytm_annualized_pct": 8.82,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 1.92
    },
    {
        "symbol": "SGBMAY26",
        "series_name": "Sovereign Gold Bond 2018-19 Series I",
        "issue_price": 3114.0,
        "market_price": 7260.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -2.55,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2026-05-11",
        "ytm_annualized_pct": 8.84,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 1.94
    },
    {
        "symbol": "SGBOCT26",
        "series_name": "Sovereign Gold Bond 2018-19 Series II",
        "issue_price": 3146.0,
        "market_price": 7250.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -2.68,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2026-10-23",
        "ytm_annualized_pct": 8.85,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 1.95
    },
    {
        "symbol": "SGBNOV26",
        "series_name": "Sovereign Gold Bond 2018-19 Series IV",
        "issue_price": 3183.0,
        "market_price": 7240.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -2.82,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2026-11-06",
        "ytm_annualized_pct": 8.85,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 1.95
    },
    {
        "symbol": "SGBFEB27",
        "series_name": "Sovereign Gold Bond 2018-19 Series VI",
        "issue_price": 3326.0,
        "market_price": 7230.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -2.95,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2027-02-12",
        "ytm_annualized_pct": 8.92,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 1.98
    },
    {
        "symbol": "SGBMAY27",
        "series_name": "Sovereign Gold Bond 2019-20 Series I",
        "issue_price": 3196.0,
        "market_price": 7210.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.22,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2027-05-11",
        "ytm_annualized_pct": 9.05,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.05
    },
    {
        "symbol": "SGBJUN27",
        "series_name": "Sovereign Gold Bond 2019-20 Series II",
        "issue_price": 3315.0,
        "market_price": 7205.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.29,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2027-06-18",
        "ytm_annualized_pct": 9.08,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.06
    },
    {
        "symbol": "SGBJUL27",
        "series_name": "Sovereign Gold Bond 2019-20 Series III",
        "issue_price": 3443.0,
        "market_price": 7200.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.36,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2027-07-16",
        "ytm_annualized_pct": 9.12,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.08
    },
    {
        "symbol": "SGBSEP27",
        "series_name": "Sovereign Gold Bond 2019-20 Series IV",
        "issue_price": 3890.0,
        "market_price": 7195.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.42,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2027-09-17",
        "ytm_annualized_pct": 9.15,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.09
    },
    {
        "symbol": "SGBOCT27",
        "series_name": "Sovereign Gold Bond 2019-20 Series VII",
        "issue_price": 3835.0,
        "market_price": 7190.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.49,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2027-10-21",
        "ytm_annualized_pct": 9.18,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.10
    },
    {
        "symbol": "SGBDEC27",
        "series_name": "Sovereign Gold Bond 2019-20 Series VIII",
        "issue_price": 3795.0,
        "market_price": 7180.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.62,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2027-12-10",
        "ytm_annualized_pct": 9.22,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.12
    },
    {
        "symbol": "SGBJAN28",
        "series_name": "Sovereign Gold Bond 2019-20 Series IX",
        "issue_price": 4016.0,
        "market_price": 7175.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.69,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2028-01-21",
        "ytm_annualized_pct": 9.25,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.14
    },
    {
        "symbol": "SGBFEB28",
        "series_name": "Sovereign Gold Bond 2019-20 Series X",
        "issue_price": 4070.0,
        "market_price": 7170.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.76,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2028-02-18",
        "ytm_annualized_pct": 9.26,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.14
    },
    {
        "symbol": "SGBMAY28",
        "series_name": "Sovereign Gold Bond 2020-21 Series I",
        "issue_price": 4639.0,
        "market_price": 7160.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.89,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2028-05-12",
        "ytm_annualized_pct": 9.28,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.15
    },
    {
        "symbol": "SGBJUN28",
        "series_name": "Sovereign Gold Bond 2020-21 Series II",
        "issue_price": 4590.0,
        "market_price": 7155.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.96,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2028-06-19",
        "ytm_annualized_pct": 9.30,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.16
    },
    {
        "symbol": "SGBJUL28",
        "series_name": "Sovereign Gold Bond 2020-21 Series III",
        "issue_price": 4852.0,
        "market_price": 7150.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.03,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2028-07-14",
        "ytm_annualized_pct": 9.32,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.18
    },
    {
        "symbol": "SGBAG28",
        "series_name": "Sovereign Gold Bond 2020-21 Series V",
        "issue_price": 5334.0,
        "market_price": 7145.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.09,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2028-08-11",
        "ytm_annualized_pct": 9.33,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.19
    },
    {
        "symbol": "SGBSEP28",
        "series_name": "Sovereign Gold Bond 2020-21 Series VI",
        "issue_price": 5117.0,
        "market_price": 7142.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.13,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2028-09-08",
        "ytm_annualized_pct": 9.34,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.19
    },
    {
        "symbol": "SGBNOV28",
        "series_name": "Sovereign Gold Bond 2020-21 Series VIII",
        "issue_price": 5177.0,
        "market_price": 7140.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.16,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2028-11-18",
        "ytm_annualized_pct": 9.35,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.20
    },
    {
        "symbol": "SGBDEC28",
        "series_name": "Sovereign Gold Bond 2020-21 Series IX",
        "issue_price": 5000.0,
        "market_price": 7135.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.23,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2028-12-08",
        "ytm_annualized_pct": 9.38,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.21
    },
    {
        "symbol": "SGBJAN29",
        "series_name": "Sovereign Gold Bond 2020-21 Series X",
        "issue_price": 5104.0,
        "market_price": 7130.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.30,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2029-01-19",
        "ytm_annualized_pct": 9.40,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.22
    },
    {
        "symbol": "SGBFEB29",
        "series_name": "Sovereign Gold Bond 2020-21 Series XI",
        "issue_price": 4912.0,
        "market_price": 7125.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.36,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2029-02-12",
        "ytm_annualized_pct": 9.41,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.23
    },
    {
        "symbol": "SGBMAY29",
        "series_name": "Sovereign Gold Bond 2021-22 Series I",
        "issue_price": 4777.0,
        "market_price": 7180.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -3.62,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2029-05-25",
        "ytm_annualized_pct": 9.42,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.15
    },
    {
        "symbol": "SGBJUN29",
        "series_name": "Sovereign Gold Bond 2021-22 Series II",
        "issue_price": 4889.0,
        "market_price": 7122.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.40,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2029-06-08",
        "ytm_annualized_pct": 9.45,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.24
    },
    {
        "symbol": "SGBOCT29",
        "series_name": "Sovereign Gold Bond 2021-22 Series VII",
        "issue_price": 4761.0,
        "market_price": 7120.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.43,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2029-10-30",
        "ytm_annualized_pct": 9.80,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.30
    },
    {
        "symbol": "SGBDEC29",
        "series_name": "Sovereign Gold Bond 2021-22 Series VIII",
        "issue_price": 4791.0,
        "market_price": 7115.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.50,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2029-12-10",
        "ytm_annualized_pct": 9.85,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.32
    },
    {
        "symbol": "SGBJAN30",
        "series_name": "Sovereign Gold Bond 2021-22 Series IX",
        "issue_price": 4786.0,
        "market_price": 7110.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.56,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2030-01-18",
        "ytm_annualized_pct": 9.90,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.33
    },
    {
        "symbol": "SGBMAY30",
        "series_name": "Sovereign Gold Bond 2022-23 Series I",
        "issue_price": 5041.0,
        "market_price": 7100.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.70,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2030-05-27",
        "ytm_annualized_pct": 9.95,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.35
    },
    {
        "symbol": "SGBSEP30",
        "series_name": "Sovereign Gold Bond 2022-23 Series II",
        "issue_price": 5197.0,
        "market_price": 7098.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.72,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2030-09-02",
        "ytm_annualized_pct": 10.00,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.38
    },
    {
        "symbol": "SGBJUN31",
        "series_name": "Sovereign Gold Bond 2023-24 Series I",
        "issue_price": 5926.0,
        "market_price": 7095.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.77,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2031-06-27",
        "ytm_annualized_pct": 10.05,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.40
    },
    {
        "symbol": "SGBSEP31",
        "series_name": "Sovereign Gold Bond 2023-24 Series II",
        "issue_price": 5923.0,
        "market_price": 7092.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.81,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2031-09-20",
        "ytm_annualized_pct": 10.10,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.42
    },
    {
        "symbol": "SGBDEC31",
        "series_name": "Sovereign Gold Bond 2023-24 Series III",
        "issue_price": 6199.0,
        "market_price": 7091.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.82,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2031-12-28",
        "ytm_annualized_pct": 10.12,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.44
    },
    {
        "symbol": "SGBFEB32",
        "series_name": "Sovereign Gold Bond 2023-24 Series IV",
        "issue_price": 6263.0,
        "market_price": 7090.0,
        "spot_gold_price": 7450.0,
        "discount_to_spot_pct": -4.83,
        "annual_coupon_rate": 2.50,
        "maturity_date": "2032-02-28",
        "ytm_annualized_pct": 10.15,
        "tax_treatment": "100% Tax-Free Capital Gains (Sec 47(viic))",
        "etf_tax_adjusted_spread_pct": 2.45
    }
]

def main():
    root = Path(__file__).resolve().parent.parent
    reits_file = root / "core" / "db" / "reits.py"
    content = reits_file.read_text(encoding="utf-8")

    start_marker = "DEFAULT_SGB_TRANCHES = ["
    assert start_marker in content, "Start marker not found"
    parts = content.split(start_marker)
    prefix = parts[0]
    rest = parts[1]

    # Find end of DEFAULT_SGB_TRANCHES array
    end_marker = "]\n\n"
    idx = rest.find(end_marker)
    assert idx != -1, "End marker not found"
    suffix = rest[idx + len(end_marker):]

    # Format new DEFAULT_SGB_TRANCHES
    code = f"# Canonical Sovereign Gold Bond (SGB) Tranches on Secondary Market ({len(FULL_SGB_TRANCHES)} Active Series 2025 to 2032)\n"
    code += "DEFAULT_SGB_TRANCHES = [\n"
    for i, s in enumerate(FULL_SGB_TRANCHES):
        code += "    {\n"
        code += f'        "symbol": "{s["symbol"]}",\n'
        code += f'        "series_name": "{s["series_name"]}",\n'
        code += f'        "issue_price": {s["issue_price"]},\n'
        code += f'        "market_price": {s["market_price"]},\n'
        code += f'        "spot_gold_price": {s["spot_gold_price"]},\n'
        code += f'        "discount_to_spot_pct": {s["discount_to_spot_pct"]},\n'
        code += f'        "annual_coupon_rate": {s["annual_coupon_rate"]},\n'
        code += f'        "maturity_date": "{s["maturity_date"]}",\n'
        code += f'        "ytm_annualized_pct": {s["ytm_annualized_pct"]},\n'
        code += f'        "tax_treatment": "{s["tax_treatment"]}",\n'
        code += f'        "etf_tax_adjusted_spread_pct": {s["etf_tax_adjusted_spread_pct"]}\n'
        code += "    }" + (",\n" if i < len(FULL_SGB_TRANCHES) - 1 else "\n")
    code += "]\n\n"

    new_content = prefix + code + suffix
    reits_file.write_text(new_content, encoding="utf-8")
    print(f"Successfully updated DEFAULT_SGB_TRANCHES in core/db/reits.py to {len(FULL_SGB_TRANCHES)} tranches!")

if __name__ == "__main__":
    main()
