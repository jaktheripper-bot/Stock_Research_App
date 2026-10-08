# Top Mutual Funds: Portfolio Ingestion Report

Source: Nippon India monthly portfolio disclosure as on 2026-08-31; AUM from AMFI average AUM (Jul-Sep 2026). Only funds with real disclosed holdings are listed.

**Status: 30 of the 150 target funds ingested.** All other AMCs need a workbook in `data/amc_portfolios/<amc_key>/` (see `core/ingestion/amc_sources.json`).

Full holdings list: `exports/top_funds_holdings.csv` (2,719 rows).

| AUM rank | Code | Scheme | AUM (Rs Cr) | Holdings | Base score |
|---|---|---|---|---|---|
| 10 | 118701 | Nippon India Liquid Fund | 35,422 | 168 | 90.0 |
| 18 | 118778 | Nippon India Small Cap Fund | 25,810 | 257 | 69.0 |
| 35 | 118632 | Nippon India Large Cap Fund | 18,766 | 68 | 73.7 |
| 73 | 118650 | Nippon India Multi Cap Fund | 11,598 | 121 | 71.8 |
| 78 | 118668 | Nippon India Growth Mid Cap Fund | 11,307 | 103 | 69.0 |
| 82 | 118585 | Nippon India Arbitrage Fund | 10,582 | 180 | 77.2 |
| 105 | 118814 | Nippon India Corporate Bond Fund | 8,026 | 118 | 90.0 |
| 113 | 145810 | Nippon India Overnight Fund | 6,870 | 8 | 90.0 |
| 114 | 118656 | Nippon India Floating Interest Rates Fund | 6,803 | 108 | 90.0 |
| 152 | 118709 | Nippon India Ultra Short to Short Term Fund | 5,063 | 98 | 90.0 |
| 164 | 118796 | Nippon India Short Term Fund | 4,640 | 106 | 90.0 |
| 182 | 148457 | Nippon India Multi Asset Allocation Fund | 3,944 | 171 | 78.6 |
| 234 | 118747 | Nippon India Dynamic Term Fund | 2,556 | 97 | 90.0 |
| 240 | 118759 | Nippon India Pharma Fund | 2,481 | 38 | 68.8 |
| 288 | 118763 | Nippon India Power & Infra Fund | 1,698 | 85 | 70.3 |
| 296 | 118589 | Nippon India Banking & Financial Services Fund | 1,529 | 39 | 72.7 |
| 331 | 118803 | Nippon India ELSS Tax Saver Fund | 1,247 | 63 | 71.9 |
| 343 | 118736 | Nippon India Balanced Advantage Fund | 1,192 | 143 | 77.6 |
| 369 | 118672 | Nippon India Gilt Fund | 1,014 | 41 | 90.0 |
| 372 | 149094 | Nippon India Flexi Cap Fund | 1,011 | 88 | 72.0 |
| 383 | 118784 | Nippon India Value Fund | 950 | 92 | 72.4 |
| 403 | 118780 | Nippon India Credit Risk Fund (Existing Number of Segregated Portfolios - 1) | 834 | 63 | 90.0 |
| 427 | 118678 | Nippon India Vision Large & Mid Cap Fund | 730 | 83 | 71.2 |
| 447 | 118692 | Nippon India Focused Fund | 620 | 33 | 73.2 |
| 594 | 118794 | Nippon India Aggressive Hybrid Fund (Existing Number of Segregated Portfolios - 2) | 279 | 124 | 77.0 |
| 607 | 118726 | Nippon India Conservative Hybrid Fund (Existing number of Segregated Portfolios - 1) | 267 | 93 | 88.2 |
| 610 | 118724 | Nippon India Consumption Fund | 259 | 46 | 68.9 |
| 728 | 118687 | Nippon India Medium to Long Term Fund | 132 | 16 | 90.0 |
| 848 | 130050 | Nippon India Medium Term Fund (Existing Number of Segregated Portfolios - 1) | 72 | 33 | 90.0 |
| 949 | 118769 | Nippon India Quant Fund | 39 | 36 | 72.6 |

## Research coverage of equity holdings (by portfolio weight)

| Status | Share |
|---|---|
| Full 7-pillar stock report | 2.1% |
| Benchmark proxy score only | 23.2% |
| Uncovered (default score 68) | 74.7% |

488 unique equities; only INFY and KAYNES have full reports. Equity-fund scores are therefore mostly placeholders until those stocks are researched.

Debt and liquid funds score 90.0 because the debt sleeve uses rating-based fallback scoring, not issuer-level credit analysis.
