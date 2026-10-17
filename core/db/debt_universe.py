"""Canonical Benchmark Universe for Indian Corporate Debt, NCDs, and SDIs.

Complies with SEBI (Issue and Listing of Non-Convertible Securities) Regulations
and the SEBI ₹10,000 Face Value Democratization Framework (July 2024 Amendments).

Contains 130 benchmark corporate debt instruments spanning 5 essential institutional segments:
1. PSU & Sovereign-Backed Quasi-Gilt Bonds (25 instruments: PFC, REC, NTPC, NHAI, IRFC, IOCL, etc.)
2. Marquee Conglomerates & Corporate Giants (25 instruments: RIL, Tata Motors, L&T, TCS, M&M, etc.)
3. Premier Banking & Financial Institutions (Senior, Tier-II & Infra) (25 instruments: SBI, HDFC, ICICI, etc.)
4. Infrastructure, Energy & Green Concession Bonds (15 instruments: Adani Ports, ReNew, Avaada, etc.)
5. Securitised Debt Instruments (SDIs) & Retail ₹10,000 NCDs (15 instruments: InvoiceX, LoanX, LeaseX, etc.)

Guarantees 100% offline availability on cold boot, during testing, and under restricted network environments.
"""

from typing import List, Dict, Any

CANONICAL_DEBT_UNIVERSE: List[Dict[str, Any]] = [
    {
        "isin": "INE134E08KO1",
        "ticker": "PFC",
        "scrip_code": "936001",
        "series": "N1",
        "instrument_name": "Power Finance Corporation 7.55% Secured NCD 2028",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.55,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-05-15",
        "maturity_date": "2028-05-15",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.25,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10050.0,
        "ytm_pct": 7.42,
        "macaulay_duration_years": 2.35,
        "modified_duration_years": 2.19,
        "metadata": {
            "sector": "Power Sector Financing / Maharatna NBFC",
            "promoter_group": "Government of India (55.99% ownership via REC/GoI)",
            "issuer_overview": "Power Finance Corporation is the nodal development finance institution powering India's energy transition and transmission grid with sovereign-grade balance sheet resilience.",
            "collateral_type": "First pari-passu charge on receivables and project book",
            "interest_coverage": 3.8,
            "dscr": 1.9,
            "debt_to_equity": 6.2,
            "credit_rating_rationale": "Highest safety AAA rating driven by strategic sovereign role and zero historical default.",
            "the_good": [
                        "Quasi-sovereign credit safety",
                        "Zero historical credit loss across public issues",
                        "Excellent secondary market liquidity on BSE/NSE"
            ],
            "the_bad": [
                        "Modest spread over 10Y G-Sec (~35 bps)",
                        "Slab taxation on coupons without indexation"
            ],
            "the_ugly": [
                        "Systemic DISCOM financial stress in weak state distribution companies"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE020B08DF2",
        "ticker": "REC",
        "scrip_code": "936002",
        "series": "N2",
        "instrument_name": "REC Limited 7.62% Secured NCD 2029",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.62,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-22",
        "maturity_date": "2029-01-22",
        "credit_rating": "ICRA AAA",
        "credit_rating_agency": "ICRA",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10075.0,
        "ytm_pct": 7.45,
        "macaulay_duration_years": 2.85,
        "modified_duration_years": 2.65,
        "metadata": {
            "sector": "Power Sector Financing / Maharatna PSU",
            "promoter_group": "PFC / Government of India",
            "issuer_overview": "REC Limited finances renewable energy, rural electrification, and transmission infrastructure across India.",
            "collateral_type": "First pari-passu floating charge on loan assets",
            "interest_coverage": 3.9,
            "dscr": 2.0,
            "debt_to_equity": 6.0,
            "credit_rating_rationale": "Sovereign-equivalent credit backed by central government majority control and Maharatna status.",
            "the_good": [
                        "Pristine AAA safety profile",
                        "High loan recovery rate backed by state guarantees",
                        "Deep liquidity in wholesale and retail debt segments"
            ],
            "the_bad": [
                        "Low real yield after accounting for 30%+ income tax brackets"
            ],
            "the_ugly": [
                        "Macro interest rate spikes reducing secondary bond prices before maturity"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE733E08106",
        "ticker": "NTPC",
        "scrip_code": "936003",
        "series": "N1",
        "instrument_name": "NTPC Limited 7.35% Secured NCD 2030",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.35,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-08-10",
        "maturity_date": "2030-08-10",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 9980.0,
        "ytm_pct": 7.39,
        "macaulay_duration_years": 3.45,
        "modified_duration_years": 3.21,
        "metadata": {
            "sector": "Power Generation / Maharatna Utility",
            "promoter_group": "Government of India (51.10%)",
            "issuer_overview": "India's largest power utility producing over 25% of the national electricity output with long-term take-or-pay PPAs.",
            "collateral_type": "First fixed charge over power generation stations",
            "interest_coverage": 4.5,
            "dscr": 2.2,
            "debt_to_equity": 1.4,
            "credit_rating_rationale": "High operating cash flow from tripartite agreements between GoI, RBI, and State Governments.",
            "the_good": [
                        "Tripartite payment security mechanism ensures zero payment default",
                        "Essential baseload utility status",
                        "Low balance sheet leverage"
            ],
            "the_bad": [
                        "Yield tightly compressed against sovereign benchmarks"
            ],
            "the_ugly": [
                        "Coal supply disruption or severe hydrological deficit impacting generation"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE053F08089",
        "ticker": "IRFC",
        "scrip_code": "936004",
        "series": "N1",
        "instrument_name": "Indian Railway Finance Corporation 7.42% Secured NCD 2031",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.42,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-14",
        "maturity_date": "2031-02-14",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10020.0,
        "ytm_pct": 7.38,
        "macaulay_duration_years": 3.9,
        "modified_duration_years": 3.63,
        "metadata": {
            "sector": "Railway Infrastructure Financing / PSU",
            "promoter_group": "Ministry of Railways / Government of India (86.36%)",
            "issuer_overview": "IRFC is the dedicated financing arm of the Ministry of Railways, funding rolling stock and infrastructure leases under a cost-plus margin lease structure.",
            "collateral_type": "First charge over rolling stock assets leased to Indian Railways",
            "interest_coverage": 5.2,
            "dscr": 2.6,
            "debt_to_equity": 7.1,
            "credit_rating_rationale": "Zero NPA track record across entire corporate history due to Ministry of Railways budget appropriations.",
            "the_good": [
                        "Absolute zero NPA historical record",
                        "Direct sovereign backing from central union budget",
                        "Guaranteed lease margin model"
            ],
            "the_bad": [
                        "Fixed low margin caps upside returns"
            ],
            "the_ugly": [
                        "Structural privatization policy shifts altering Ministry of Railways lease model"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE906B08034",
        "ticker": "NHAI",
        "scrip_code": "936005",
        "series": "N1",
        "instrument_name": "National Highways Authority of India 7.60% Secured NCD 2033",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.6,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-05",
        "maturity_date": "2033-11-05",
        "credit_rating": "CARE AAA",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.5,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10100.0,
        "ytm_pct": 7.46,
        "macaulay_duration_years": 4.8,
        "modified_duration_years": 4.47,
        "metadata": {
            "sector": "Roads & Highways / Statutory Authority",
            "promoter_group": "Ministry of Road Transport and Highways (100% GoI)",
            "issuer_overview": "NHAI is the statutory apex body executing the Bharatmala Pariyojana and National Highway development under central sovereign mandates.",
            "collateral_type": "First charge on National Highway toll collections and cess transfers",
            "interest_coverage": 4.1,
            "dscr": 2.1,
            "debt_to_equity": 4.5,
            "credit_rating_rationale": "Direct sovereign budgetary allocation from Central Road Fund (CRIF) and toll monetization receipts.",
            "the_good": [
                        "100% central government statutory entity",
                        "Long maturity duration for locking in safe yields",
                        "Backed by national highway asset monetization"
            ],
            "the_bad": [
                        "High duration creates mark-to-market sensitivity if interest rates rise"
            ],
            "the_ugly": [
                        "Extended delays in land acquisition slowing project monetization pipelines"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE752E08587",
        "ticker": "POWERGRID",
        "scrip_code": "936006",
        "series": "N1",
        "instrument_name": "Power Grid Corporation 7.30% Secured NCD 2029",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.3,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-03-01",
        "maturity_date": "2029-03-01",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.45,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 9970.0,
        "ytm_pct": 7.37,
        "macaulay_duration_years": 2.9,
        "modified_duration_years": 2.7,
        "metadata": {
            "sector": "Power Transmission / Maharatna Utility",
            "promoter_group": "Government of India (51.34%)",
            "issuer_overview": "Monopoly interstate transmission utility transmitting 85%+ of India's bulk inter-regional electric power.",
            "collateral_type": "First fixed charge on sub-stations and transmission towers",
            "interest_coverage": 5.4,
            "dscr": 2.7,
            "debt_to_equity": 1.7,
            "credit_rating_rationale": "Regulated return-on-equity model (CERC 15.5% post-tax RoE) with Point of Connection (PoC) pooling mechanism.",
            "the_good": [
                        "99.8% statutory system availability factor",
                        "Zero traffic or volume risk (availability annuity)",
                        "Lowest cost of borrowing in the utility sector"
            ],
            "the_bad": [
                        "Tight yields offering thin credit risk premiums over sovereign gilts"
            ],
            "the_ugly": [
                        "Severe regional grid failure or catastrophic storm damage to transmission corridors"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE242A08453",
        "ticker": "IOCL",
        "scrip_code": "936007",
        "series": "N1",
        "instrument_name": "Indian Oil Corporation 7.40% Secured NCD 2028",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.4,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-09-12",
        "maturity_date": "2028-09-12",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10010.0,
        "ytm_pct": 7.38,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.28,
        "metadata": {
            "sector": "Oil Refining & Marketing / Maharatna PSU",
            "promoter_group": "Government of India (51.50%)",
            "issuer_overview": "India's largest commercial oil refiner and fuel retailer with extensive pipelines and refinery assets.",
            "collateral_type": "First pari-passu charge on petroleum pipelines and refining equipment",
            "interest_coverage": 4.8,
            "dscr": 2.3,
            "debt_to_equity": 0.85,
            "credit_rating_rationale": "Critical national energy infrastructure provider backed by sovereign strategic ownership.",
            "the_good": [
                        "Low debt-to-equity ratio of 0.85x",
                        "Dominant 40%+ retail fuel distribution market share",
                        "Strong operating cash flows"
            ],
            "the_bad": [
                        "Coupons fully taxable at investor's marginal slab"
            ],
            "the_ugly": [
                        "Global crude volatility compressing downstream marketing margins"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE121A08234",
        "ticker": "BPCL",
        "scrip_code": "936008",
        "series": "N1",
        "instrument_name": "Bharat Petroleum 7.45% Secured NCD 2027",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.45,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-04-18",
        "maturity_date": "2027-04-18",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10030.0,
        "ytm_pct": 7.33,
        "macaulay_duration_years": 1.85,
        "modified_duration_years": 1.72,
        "metadata": {
            "sector": "Oil Refining & Marketing / Maharatna PSU",
            "promoter_group": "Government of India (52.98%)",
            "issuer_overview": "Leading downstream oil marketing company operating Mumbai and Kochi refineries with nationwide retail reach.",
            "collateral_type": "Pari-passu charge on Kochi refinery assets",
            "interest_coverage": 5.1,
            "dscr": 2.5,
            "debt_to_equity": 0.72,
            "credit_rating_rationale": "High refining complexity and conservative leverage resulting in highest credit rating.",
            "the_good": [
                        "Conservative leverage of 0.72x D/E",
                        "Robust ICR of 5.1x",
                        "Short duration providing price stability"
            ],
            "the_bad": [
                        "Yield premium over G-Sec is modest (~30 bps)"
            ],
            "the_ugly": [
                        "Government price freezes on fuel retail during elevated global oil price regimes"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE213A08190",
        "ticker": "ONGC",
        "scrip_code": "936009",
        "series": "N1",
        "instrument_name": "Oil and Natural Gas Corp 7.35% Secured NCD 2029",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.35,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-10",
        "maturity_date": "2029-01-10",
        "credit_rating": "ICRA AAA",
        "credit_rating_agency": "ICRA",
        "asset_cover_ratio": 1.55,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 9990.0,
        "ytm_pct": 7.37,
        "macaulay_duration_years": 2.8,
        "modified_duration_years": 2.6,
        "metadata": {
            "sector": "Oil & Gas Exploration / Maharatna E&P",
            "promoter_group": "Government of India (58.89%)",
            "issuer_overview": "India's largest upstream crude oil and natural gas producer contributing ~71% to domestic production.",
            "collateral_type": "First charge over offshore and onshore production assets",
            "interest_coverage": 6.9,
            "dscr": 3.1,
            "debt_to_equity": 0.45,
            "credit_rating_rationale": "Massive operating cash flows, strategic national importance, and minimal net debt.",
            "the_good": [
                        "Ultra-strong ICR of 6.9x",
                        "Pristine sovereign ownership",
                        "Low debt-to-equity ratio of 0.45x"
            ],
            "the_bad": [
                        "Benchmark yield compression leaves little credit spread"
            ],
            "the_ugly": [
                        "Depletion of mature offshore fields requiring heavy exploratory capex"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE129A08098",
        "ticker": "GAIL",
        "scrip_code": "936010",
        "series": "N1",
        "instrument_name": "GAIL India Limited 7.48% Secured NCD 2028",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.48,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-20",
        "maturity_date": "2028-11-20",
        "credit_rating": "CARE AAA",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10040.0,
        "ytm_pct": 7.38,
        "macaulay_duration_years": 2.5,
        "modified_duration_years": 2.33,
        "metadata": {
            "sector": "Natural Gas Transmission / Maharatna Utility",
            "promoter_group": "Government of India (51.90%)",
            "issuer_overview": "Monopoly natural gas transmission utility managing over 70% of India's gas pipeline network.",
            "collateral_type": "First charge on natural gas pipeline assets",
            "interest_coverage": 6.2,
            "dscr": 2.8,
            "debt_to_equity": 0.35,
            "credit_rating_rationale": "High-margin transmission network with regulated PNGRB pipeline tariff model.",
            "the_good": [
                        "Low balance sheet leverage of 0.35x D/E",
                        "Regulated pipeline tariff model",
                        "Essential clean energy transition asset"
            ],
            "the_bad": [
                        "Yield tracks G-Sec closely"
            ],
            "the_ugly": [
                        "Geopolitical disruptions to long-term LNG supply contracts"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE556F08017",
        "ticker": "SIDBI",
        "scrip_code": "936011",
        "series": "N1",
        "instrument_name": "Small Industries Development Bank 7.50% Secured NCD 2027",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.5,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-03-15",
        "maturity_date": "2027-03-15",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.2,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10020.0,
        "ytm_pct": 7.42,
        "macaulay_duration_years": 1.75,
        "modified_duration_years": 1.63,
        "metadata": {
            "sector": "Development Financial Institution / MSME Apex",
            "promoter_group": "SBI (20.85%), GoI (20.85%), LIC (14.25%), NABARD",
            "issuer_overview": "Apex development finance institution for micro, small, and medium enterprises (MSME) in India.",
            "collateral_type": "Charge on loan book and MSME refinance portfolio",
            "interest_coverage": 2.9,
            "dscr": 1.8,
            "debt_to_equity": 7.5,
            "credit_rating_rationale": "Statutory financial institution backed by RBI and public financial institutions.",
            "the_good": [
                        "Statutory financial institution safety",
                        "Low duration (1.75y) means minimal price volatility",
                        "Highest AAA safety rating"
            ],
            "the_bad": [
                        "Low interest premium over commercial bank fixed deposits"
            ],
            "the_ugly": [
                        "Widespread default in vulnerable micro enterprise refinancing tranches"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE261F08092",
        "ticker": "NABARD",
        "scrip_code": "936012",
        "series": "N1",
        "instrument_name": "NABARD 7.45% Secured NCD 2028",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.45,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-10-12",
        "maturity_date": "2028-10-12",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.25,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10015.0,
        "ytm_pct": 7.41,
        "macaulay_duration_years": 2.55,
        "modified_duration_years": 2.37,
        "metadata": {
            "sector": "Agriculture & Rural Development / DFI",
            "promoter_group": "Government of India (100% Wholly Owned)",
            "issuer_overview": "National Bank for Agriculture and Rural Development is the apex development bank wholly owned by GoI.",
            "collateral_type": "Charge on rural infrastructure development fund and refinance book",
            "interest_coverage": 3.2,
            "dscr": 1.9,
            "debt_to_equity": 6.8,
            "credit_rating_rationale": "100% Government of India owned statutory body with sovereign status.",
            "the_good": [
                        "100% sovereign GoI ownership",
                        "Impeccable credit standing with zero default risk",
                        "High secondary volume on exchange platforms"
            ],
            "the_bad": [
                        "Coupon income subject to regular income tax slab"
            ],
            "the_ugly": [
                        "Systemic rural farm loan waivers destabilizing state cooperative bank repayments"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE514E08240",
        "ticker": "EXIMBANK",
        "scrip_code": "936013",
        "series": "N1",
        "instrument_name": "Export-Import Bank of India 7.52% Secured NCD 2029",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.52,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-28",
        "maturity_date": "2029-02-28",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.2,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10035.0,
        "ytm_pct": 7.43,
        "macaulay_duration_years": 2.95,
        "modified_duration_years": 2.75,
        "metadata": {
            "sector": "Export-Import Financing / 100% GoI DFI",
            "promoter_group": "Government of India (100%)",
            "issuer_overview": "Specialized financial institution wholly owned by GoI for financing and promoting foreign trade.",
            "collateral_type": "Charge on foreign trade loan assets",
            "interest_coverage": 3.4,
            "dscr": 2.0,
            "debt_to_equity": 6.5,
            "credit_rating_rationale": "Full statutory backing of the Government of India under EXIM Bank Act 1981.",
            "the_good": [
                        "100% sovereign union ownership",
                        "Zero credit risk on principal repayment",
                        "High institutional demand"
            ],
            "the_bad": [
                        "Spread over G-Sec is narrow (~38 bps)"
            ],
            "the_ugly": [
                        "Severe sovereign debt defaults in developing export partner economies"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE557F08081",
        "ticker": "NHB",
        "scrip_code": "936014",
        "series": "N1",
        "instrument_name": "National Housing Bank 7.46% Secured NCD 2030",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.46,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-12-15",
        "maturity_date": "2030-12-15",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.25,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10025.0,
        "ytm_pct": 7.41,
        "macaulay_duration_years": 3.65,
        "modified_duration_years": 3.4,
        "metadata": {
            "sector": "Housing Finance Refinancing / 100% GoI",
            "promoter_group": "Government of India (100%)",
            "issuer_overview": "Apex agency established to promote housing finance institutions and refinance housing loan portfolios.",
            "collateral_type": "Charge on housing refinance receivables",
            "interest_coverage": 3.1,
            "dscr": 1.9,
            "debt_to_equity": 7.2,
            "credit_rating_rationale": "Statutory body wholly owned by GoI with paramount policy importance.",
            "the_good": [
                        "Sovereign pedigree",
                        "Excellent safety score",
                        "Institutional liquidity"
            ],
            "the_bad": [
                        "Post-tax returns heavily clipped by income tax"
            ],
            "the_ugly": [
                        "Systemic stress in non-bank housing finance companies"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE202E08129",
        "ticker": "IREDA",
        "scrip_code": "936015",
        "series": "N1",
        "instrument_name": "Indian Renewable Energy Dev Agency 7.68% Secured NCD 2029",
        "instrument_type": "GREEN_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.68,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-10",
        "maturity_date": "2029-02-10",
        "credit_rating": "ICRA AAA",
        "credit_rating_agency": "ICRA",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10090.0,
        "ytm_pct": 7.45,
        "macaulay_duration_years": 2.8,
        "modified_duration_years": 2.61,
        "metadata": {
            "sector": "Renewable Energy Financing / Navratna PSU",
            "promoter_group": "Ministry of New and Renewable Energy / GoI (75.0%)",
            "issuer_overview": "Pioneering specialized non-banking financial institution promoting, developing and extending financial assistance for renewable energy and energy efficiency projects.",
            "collateral_type": "Charge on solar and wind energy project loan assets",
            "interest_coverage": 3.6,
            "dscr": 2.1,
            "debt_to_equity": 5.8,
            "credit_rating_rationale": "High strategic importance to India's 500 GW non-fossil capacity target by 2030.",
            "the_good": [
                        "Certified Green Bond status",
                        "Backed by rapid solar and wind project growth",
                        "Robust government backing"
            ],
            "the_bad": [
                        "Slightly higher leverage than thermal power utilities"
            ],
            "the_ugly": [
                        "Renegotiation of green power tariffs by state distribution companies"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE031A08643",
        "ticker": "HUDCO",
        "scrip_code": "936016",
        "series": "N1",
        "instrument_name": "Housing & Urban Development Corp 7.58% Secured NCD 2028",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.58,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-28",
        "maturity_date": "2028-11-28",
        "credit_rating": "CARE AAA",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10060.0,
        "ytm_pct": 7.42,
        "macaulay_duration_years": 2.5,
        "modified_duration_years": 2.33,
        "metadata": {
            "sector": "Urban Infrastructure & Social Housing / Navratna PSU",
            "promoter_group": "Ministry of Housing and Urban Affairs / GoI (75.0%)",
            "issuer_overview": "Navratna public sector enterprise financing social housing and urban infrastructure projects across India.",
            "collateral_type": "Charge on urban infra loans and state government guaranteed advances",
            "interest_coverage": 3.7,
            "dscr": 2.0,
            "debt_to_equity": 5.2,
            "credit_rating_rationale": "High proportion of loans guaranteed by State Governments and 100% sovereign oversight.",
            "the_good": [
                        "Navratna status with strong sovereign support",
                        "Zero corporate default history",
                        "Good collateral coverage"
            ],
            "the_bad": [
                        "Concentration in state government sponsored urban schemes"
            ],
            "the_ugly": [
                        "Fiscal deterioration in municipal corporations delaying project payments"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE008A08127",
        "ticker": "NPCIL",
        "scrip_code": "936017",
        "series": "N1",
        "instrument_name": "Nuclear Power Corporation 7.40% Secured NCD 2032",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.4,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-03-25",
        "maturity_date": "2032-03-25",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.5,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10010.0,
        "ytm_pct": 7.38,
        "macaulay_duration_years": 4.2,
        "modified_duration_years": 3.91,
        "metadata": {
            "sector": "Nuclear Energy / 100% Department of Atomic Energy",
            "promoter_group": "Department of Atomic Energy / GoI (100%)",
            "issuer_overview": "Monopoly producer of commercial nuclear energy operating 23 nuclear reactors in India under sovereign strategic control.",
            "collateral_type": "First charge over nuclear power generation stations",
            "interest_coverage": 5.8,
            "dscr": 2.9,
            "debt_to_equity": 1.1,
            "credit_rating_rationale": "100% owned by Central Government with strategic defence and baseload power significance.",
            "the_good": [
                        "Strategic national monopoly in nuclear generation",
                        "Very low leverage of 1.1x D/E",
                        "Robust ICR of 5.8x"
            ],
            "the_bad": [
                        "Long gestation periods for new reactor units"
            ],
            "the_ugly": [
                        "Unplanned reactor outages due to technical or nuclear regulatory inspections"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE528G08394",
        "ticker": "COALINDIA",
        "scrip_code": "936018",
        "series": "N1",
        "instrument_name": "Coal India Limited 7.32% Secured NCD 2028",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.32,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-10-05",
        "maturity_date": "2028-10-05",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.65,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 9995.0,
        "ytm_pct": 7.33,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.29,
        "metadata": {
            "sector": "Mining & Natural Resources / Maharatna PSU",
            "promoter_group": "Government of India (63.13%)",
            "issuer_overview": "World's largest coal mining enterprise accounting for over 80% of total domestic coal output in India.",
            "collateral_type": "Charge on mining equipment, coal washeries, and railway sidings",
            "interest_coverage": 18.5,
            "dscr": 7.2,
            "debt_to_equity": 0.12,
            "credit_rating_rationale": "Net cash balance sheet with virtually zero net debt and astronomical interest coverage.",
            "the_good": [
                        "Astronomical ICR of 18.5x and negligible 0.12x D/E",
                        "Massive cash reserves",
                        "Monopoly domestic position"
            ],
            "the_bad": [
                        "Yield offers minimal risk spread"
            ],
            "the_ugly": [
                        "Global ESG decarbonization mandates over the next 20 years"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE114A08129",
        "ticker": "SAIL",
        "scrip_code": "936019",
        "series": "N1",
        "instrument_name": "Steel Authority of India 7.75% Secured NCD 2029",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.75,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-18",
        "maturity_date": "2029-01-18",
        "credit_rating": "CARE AA+",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10080.0,
        "ytm_pct": 7.55,
        "macaulay_duration_years": 2.75,
        "modified_duration_years": 2.56,
        "metadata": {
            "sector": "Steel & Metals / Maharatna Producer",
            "promoter_group": "Government of India (65.0%)",
            "issuer_overview": "India's largest public sector steelmaker operating 5 integrated steel plants and 3 special steel plants.",
            "collateral_type": "First charge on plant and machinery of Bhilai and Rourkela steel plants",
            "interest_coverage": 3.8,
            "dscr": 1.9,
            "debt_to_equity": 0.82,
            "credit_rating_rationale": "Government majority ownership, captive iron ore mines, and integrated manufacturing.",
            "the_good": [
                        "Captive iron ore mines insulate raw material costs",
                        "Attractive 7.75% coupon offering yield pickup over pure utilities",
                        "High institutional trading depth"
            ],
            "the_bad": [
                        "Cyclical steel price exposure"
            ],
            "the_ugly": [
                        "Chinese steel dumping into Southeast Asian and domestic Indian markets"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE111A08082",
        "ticker": "CONCOR",
        "scrip_code": "936020",
        "series": "N1",
        "instrument_name": "Container Corporation of India 7.42% Secured NCD 2028",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.42,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-08-25",
        "maturity_date": "2028-08-25",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.45,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10020.0,
        "ytm_pct": 7.36,
        "macaulay_duration_years": 2.4,
        "modified_duration_years": 2.24,
        "metadata": {
            "sector": "Logistics & Multimodal Transport / Navratna",
            "promoter_group": "Ministry of Railways / Government of India (54.80%)",
            "issuer_overview": "Market leader in multimodal logistics managing 60+ Inland Container Depots (ICDs) across India.",
            "collateral_type": "First charge on rolling stock and container terminals",
            "interest_coverage": 12.4,
            "dscr": 5.8,
            "debt_to_equity": 0.05,
            "credit_rating_rationale": "Dominant market share in rail container transport with debt-free balance sheet profile.",
            "the_good": [
                        "Virtual debt-free balance sheet (0.05x D/E)",
                        "Dominant rail freight market share",
                        "Strong operating cash flow generation"
            ],
            "the_bad": [
                        "Low secondary trading volume due to institutional buy-and-hold"
            ],
            "the_ugly": [
                        "Global container trade recessions dampening EXIM volumes"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE004A08156",
        "ticker": "SJVN",
        "scrip_code": "936021",
        "series": "N1",
        "instrument_name": "SJVN Limited 7.65% Secured NCD 2029",
        "instrument_type": "GREEN_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.65,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-18",
        "maturity_date": "2029-02-18",
        "credit_rating": "CARE AAA",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10070.0,
        "ytm_pct": 7.48,
        "macaulay_duration_years": 2.8,
        "modified_duration_years": 2.61,
        "metadata": {
            "sector": "Hydroelectric & Solar Energy / Miniratna PSU",
            "promoter_group": "GoI (55.0%) & Government of Himachal Pradesh (26.85%)",
            "issuer_overview": "Major hydroelectric and clean energy utility operating the 1500 MW Nathpa Jhakri power station.",
            "collateral_type": "Charge on hydro generation assets and solar parks",
            "interest_coverage": 4.2,
            "dscr": 2.1,
            "debt_to_equity": 1.3,
            "credit_rating_rationale": "High operating profitability and joint sovereign backing by Centre and State.",
            "the_good": [
                        "Certified clean hydro energy profile",
                        "Long-term take-or-pay PPAs",
                        "Strong credit rating cushion"
            ],
            "the_bad": [
                        "Hydro generation depends on monsoon and glacier melt cycles"
            ],
            "the_ugly": [
                        "Flash floods in Himalayan basins causing turbine siltation and plant shutdowns"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE124B08076",
        "ticker": "NHPC",
        "scrip_code": "936022",
        "series": "N1",
        "instrument_name": "NHPC Limited 7.50% Secured NCD 2030",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.5,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-07-20",
        "maturity_date": "2030-07-20",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10040.0,
        "ytm_pct": 7.42,
        "macaulay_duration_years": 3.4,
        "modified_duration_years": 3.17,
        "metadata": {
            "sector": "Hydroelectric Power / Navratna Utility",
            "promoter_group": "Government of India (70.95%)",
            "issuer_overview": "India's premier hydroelectric power generation company managing over 7000 MW of installed hydro and solar capacity.",
            "collateral_type": "First charge over hydro power stations",
            "interest_coverage": 4.6,
            "dscr": 2.3,
            "debt_to_equity": 0.85,
            "credit_rating_rationale": "Government majority ownership with tripartite payment guarantee mechanism.",
            "the_good": [
                        "Tripartite payment security mechanism",
                        "Low debt-to-equity ratio of 0.85x",
                        "Regulated RoE tariff model"
            ],
            "the_bad": [
                        "Hydro capex carries geological execution risks"
            ],
            "the_ugly": [
                        "Severe regional geopolitical tensions along border river basins"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE248U08018",
        "ticker": "MAZDOCK",
        "scrip_code": "936023",
        "series": "N1",
        "instrument_name": "Mazagon Dock Shipbuilders 7.45% Secured NCD 2028",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.45,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-12-08",
        "maturity_date": "2028-12-08",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.6,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10030.0,
        "ytm_pct": 7.37,
        "macaulay_duration_years": 2.5,
        "modified_duration_years": 2.33,
        "metadata": {
            "sector": "Defence Shipbuilding / Miniratna PSU",
            "promoter_group": "Ministry of Defence / Government of India (84.83%)",
            "issuer_overview": "India's premier shipyard constructing warships and conventional submarines for the Indian Navy.",
            "collateral_type": "Charge on dry dock infrastructure and shipbuilding berths",
            "interest_coverage": 15.0,
            "dscr": 6.5,
            "debt_to_equity": 0.08,
            "credit_rating_rationale": "Strategic national defence shipyard with pristine zero-debt balance sheet and massive order book.",
            "the_good": [
                        "Substantial defence order book visibility",
                        "Near zero balance sheet debt (0.08x D/E)",
                        "Astronomical 15x interest coverage"
            ],
            "the_bad": [
                        "Very rare public bond issuances resulting in low liquidity"
            ],
            "the_ugly": [
                        "Delays in supply of specialized marine propulsion imported components"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE089A08092",
        "ticker": "NIIF",
        "scrip_code": "936024",
        "series": "N1",
        "instrument_name": "NIIF Infrastructure Finance 7.75% Secured NCD 2029",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.75,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-03-10",
        "maturity_date": "2029-03-10",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10090.0,
        "ytm_pct": 7.52,
        "macaulay_duration_years": 2.85,
        "modified_duration_years": 2.65,
        "metadata": {
            "sector": "Infrastructure Refinancing / Sovereign Wealth Co-Investment",
            "promoter_group": "Government of India (49%) & Global Sovereign Funds (ADIA, Temasek)",
            "issuer_overview": "India's quasi-sovereign infrastructure debt fund refinancing operational infrastructure assets.",
            "collateral_type": "Charge on infrastructure project loan book",
            "interest_coverage": 3.5,
            "dscr": 1.9,
            "debt_to_equity": 4.8,
            "credit_rating_rationale": "High pedigree sponsor backing and strictly operational brownfield refinancing focus.",
            "the_good": [
                        "Global sovereign co-investor governance",
                        "Focus strictly on operational revenue-generating infra",
                        "AAA rating with 7.75% coupon"
            ],
            "the_bad": [
                        "Moderate leverage (4.8x D/E)"
            ],
            "the_ugly": [
                        "Toll road traffic drawdowns or concession dispute cancellations"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE038A08104",
        "ticker": "OILINDIA",
        "scrip_code": "936025",
        "series": "N1",
        "instrument_name": "Oil India Limited 7.55% Secured NCD 2028",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.55,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-15",
        "maturity_date": "2028-11-15",
        "credit_rating": "ICRA AAA",
        "credit_rating_agency": "ICRA",
        "asset_cover_ratio": 1.45,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10045.0,
        "ytm_pct": 7.43,
        "macaulay_duration_years": 2.5,
        "modified_duration_years": 2.33,
        "metadata": {
            "sector": "Upstream Oil & Gas / Maharatna E&P",
            "promoter_group": "Government of India (56.66%)",
            "issuer_overview": "Second largest national upstream oil and gas company operating primarily in the northeast basins of India.",
            "collateral_type": "Charge on crude oil and gas processing infrastructure",
            "interest_coverage": 7.5,
            "dscr": 3.4,
            "debt_to_equity": 0.4,
            "credit_rating_rationale": "Strong balance sheet with robust cash flows and low debt obligations.",
            "the_good": [
                        "High ICR of 7.5x and low 0.40x D/E",
                        "Consistent sovereign dividends and support",
                        "Solid domestic gas price realization"
            ],
            "the_bad": [
                        "Geographic concentration in northeast basins"
            ],
            "the_ugly": [
                        "Pipeline sabotage or civil disruption in key extraction fields"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE002A08012",
        "ticker": "RELIANCE",
        "scrip_code": "935001",
        "series": "N1",
        "instrument_name": "Reliance Industries 8.65% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.65,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-04-15",
        "maturity_date": "2028-04-15",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.45,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10150.0,
        "ytm_pct": 8.25,
        "macaulay_duration_years": 2.25,
        "modified_duration_years": 2.08,
        "metadata": {
            "sector": "Diversified Conglomerate / Energy & Telecom",
            "promoter_group": "Reliance Industries (Mukesh Ambani)",
            "issuer_overview": "Reliance Industries Limited is India's largest private sector enterprise spanning petrochemicals, refining, telecom (Jio), and organized retail.",
            "collateral_type": "First charge over manufacturing plants and movable tangible assets",
            "interest_coverage": 6.8,
            "dscr": 2.4,
            "debt_to_equity": 0.42,
            "credit_rating_rationale": "Highest corporate rating driven by extraordinary business diversity and strong cash generation.",
            "the_good": [
                        "Sovereign-equivalent credit safety",
                        "Sturdy collateral cushion of 1.45x",
                        "Robust 6.8x interest coverage"
            ],
            "the_bad": [
                        "Yield compressed vs lower-tier corporate debt"
            ],
            "the_ugly": [
                        "Extreme geopolitical shocks compressing gross refining margins"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE155A08373",
        "ticker": "TATAMOTORS",
        "scrip_code": "935002",
        "series": "N2",
        "instrument_name": "Tata Motors Limited 8.85% Secured NCD 2029",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.85,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-06-20",
        "maturity_date": "2029-06-20",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10120.0,
        "ytm_pct": 8.54,
        "macaulay_duration_years": 2.85,
        "modified_duration_years": 2.63,
        "metadata": {
            "sector": "Automotive & Electric Mobility",
            "promoter_group": "Tata Group (Tata Sons)",
            "issuer_overview": "Global automotive manufacturer with market leadership in Indian commercial vehicles, passenger EVs, and luxury automotive (JLR).",
            "collateral_type": "First pari-passu charge on automotive manufacturing assets at Pune and Pantnagar",
            "interest_coverage": 4.8,
            "dscr": 2.1,
            "debt_to_equity": 0.65,
            "credit_rating_rationale": "Upgraded to AA+ driven by massive deleveraging at Jaguar Land Rover and dominant domestic EV market share.",
            "the_good": [
                        "Dramatic debt reduction across group",
                        "Leadership in commercial vehicles and passenger EVs",
                        "Strong Tata Sons promoter parentage"
            ],
            "the_bad": [
                        "Automotive industry cyclicality"
            ],
            "the_ugly": [
                        "Severe global semiconductor supply bottlenecks disrupting JLR output"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE018A08304",
        "ticker": "LT",
        "scrip_code": "935003",
        "series": "N1",
        "instrument_name": "Larsen & Toubro Limited 7.72% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.72,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-10-10",
        "maturity_date": "2028-10-10",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10040.0,
        "ytm_pct": 7.61,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.28,
        "metadata": {
            "sector": "Engineering & Infrastructure Construction",
            "promoter_group": "Professionally Managed / L&T Employees Trust",
            "issuer_overview": "India's premier engineering, procurement, and construction (EPC) conglomerate with international operations across Middle East and Southeast Asia.",
            "collateral_type": "First charge on manufacturing facilities and engineering complexes",
            "interest_coverage": 6.5,
            "dscr": 2.8,
            "debt_to_equity": 0.55,
            "credit_rating_rationale": "Massive \u20b94,50,000+ Cr order book and extraordinary EPC execution pedigree.",
            "the_good": [
                        "Unmatched multi-year order book visibility",
                        "Conservative debt-to-equity ratio of 0.55x",
                        "Pristine AAA corporate safety"
            ],
            "the_bad": [
                        "Yield tightly compressed vs sovereign paper"
            ],
            "the_ugly": [
                        "Severe geopolitical conflict across Middle Eastern project hubs"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE081A08223",
        "ticker": "TATAPOWER",
        "scrip_code": "935004",
        "series": "N1",
        "instrument_name": "Tata Power Company 8.45% Secured NCD 2029",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.45,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-15",
        "maturity_date": "2029-01-15",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10080.0,
        "ytm_pct": 8.24,
        "macaulay_duration_years": 2.8,
        "modified_duration_years": 2.59,
        "metadata": {
            "sector": "Integrated Power & Renewables Utility",
            "promoter_group": "Tata Group (Tata Sons)",
            "issuer_overview": "Pioneering integrated power utility with generation, transmission, retail distribution (Delhi, Mumbai, Odisha), and renewable manufacturing.",
            "collateral_type": "First pari-passu charge on thermal and hydro generation units",
            "interest_coverage": 3.9,
            "dscr": 1.9,
            "debt_to_equity": 1.5,
            "credit_rating_rationale": "High operating profitability from distribution businesses and accelerated renewable expansion.",
            "the_good": [
                        "High distribution yield pickup (8.45% coupon)",
                        "Strong Tata Sons parentage",
                        "Growing green renewable energy share"
            ],
            "the_bad": [
                        "Moderate leverage of 1.5x D/E due to solar manufacturing capex"
            ],
            "the_ugly": [
                        "Coal import price spikes impacting Mundra UMPP power purchase parity"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE081A08231",
        "ticker": "TATASTEEL",
        "scrip_code": "935005",
        "series": "N1",
        "instrument_name": "Tata Steel Limited 8.05% Secured NCD 2030",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.05,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-07-14",
        "maturity_date": "2030-07-14",
        "credit_rating": "CARE AA+",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10050.0,
        "ytm_pct": 7.94,
        "macaulay_duration_years": 3.35,
        "modified_duration_years": 3.1,
        "metadata": {
            "sector": "Steel & Metallurgy / Primary Producer",
            "promoter_group": "Tata Group (Tata Sons)",
            "issuer_overview": "One of the world's most geographically diversified steelmakers with lowest-cost captive iron ore mines in India.",
            "collateral_type": "Charge on Jamshedpur steel plant and Kalinganagar facilities",
            "interest_coverage": 4.5,
            "dscr": 2.2,
            "debt_to_equity": 0.78,
            "credit_rating_rationale": "Unmatched low-cost domestic operations and substantial UK transition grant support.",
            "the_good": [
                        "Lowest-cost captive iron ore mines in India",
                        "Manageable debt-to-equity ratio of 0.78x",
                        "Strong brand loyalty"
            ],
            "the_bad": [
                        "Global steel cycle downturns impacting European subsidiary cash flows"
            ],
            "the_ugly": [
                        "Severe carbon tax adjustments in UK/European operations"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE101J08018",
        "ticker": "TATACAPITAL",
        "scrip_code": "935006",
        "series": "N1",
        "instrument_name": "Tata Capital Financial Services 8.35% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.35,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-09-05",
        "maturity_date": "2028-09-05",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10100.0,
        "ytm_pct": 8.08,
        "macaulay_duration_years": 2.35,
        "modified_duration_years": 2.17,
        "metadata": {
            "sector": "Diversified NBFC / Retail & Corporate Lending",
            "promoter_group": "Tata Sons (94.5%)",
            "issuer_overview": "Flagship non-banking financial services arm of the Tata Group providing consumer loans, SME financing, and wealth management.",
            "collateral_type": "First pari-passu charge over loan receivables book",
            "interest_coverage": 2.8,
            "dscr": 1.7,
            "debt_to_equity": 5.4,
            "credit_rating_rationale": "Highest AAA rating directly driven by 94.5% direct ownership by parent Tata Sons.",
            "the_good": [
                        "Direct ownership by Tata Sons",
                        "Strong retail asset diversification",
                        "Pristine borrowing access"
            ],
            "the_bad": [
                        "Higher leverage common to NBFC lending structures"
            ],
            "the_ugly": [
                        "Sharp surge in retail unsecured personal loan delinquencies"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE176A08107",
        "ticker": "BAJAJFIN",
        "scrip_code": "935007",
        "series": "N1",
        "instrument_name": "Bajaj Finance Limited 8.10% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.1,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-12",
        "maturity_date": "2028-11-12",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10080.0,
        "ytm_pct": 7.89,
        "macaulay_duration_years": 2.4,
        "modified_duration_years": 2.22,
        "metadata": {
            "sector": "Consumer Finance NBFC / Market Leader",
            "promoter_group": "Bajaj Group (Bajaj Finserv)",
            "issuer_overview": "India's largest non-bank consumer lender with dominant franchise across consumer durables, digital finance, and rural lending.",
            "collateral_type": "Charge on loan book and book debts",
            "interest_coverage": 3.4,
            "dscr": 1.9,
            "debt_to_equity": 4.2,
            "credit_rating_rationale": "Supreme market position, unmatched operational efficiency, and low GNPA levels.",
            "the_good": [
                        "Lowest credit cost in private NBFC sector",
                        "High Tier-1 capital adequacy ratio (> 20%)",
                        "Highest AAA corporate credit rating"
            ],
            "the_bad": [
                        "Compressed yield spread over government debt"
            ],
            "the_ugly": [
                        "Regulatory tightening on unsecured consumer lending risk weights by RBI"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE477A08082",
        "ticker": "LTFINANCE",
        "scrip_code": "935008",
        "series": "N1",
        "instrument_name": "L&T Finance Limited 8.50% Secured NCD 2029",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.5,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-15",
        "maturity_date": "2029-02-15",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10090.0,
        "ytm_pct": 8.28,
        "macaulay_duration_years": 2.85,
        "modified_duration_years": 2.64,
        "metadata": {
            "sector": "Retail NBFC / Rural & Urban Lending",
            "promoter_group": "Larsen & Toubro Limited (66.2%)",
            "issuer_overview": "Leading retail-focused NBFC with 90%+ retail loan book across rural business loans, two-wheelers, and housing finance.",
            "collateral_type": "First charge over retail loan book receivables",
            "interest_coverage": 3.1,
            "dscr": 1.8,
            "debt_to_equity": 4.5,
            "credit_rating_rationale": "Strong parental support from L&T and successful retailization of balance sheet.",
            "the_good": [
                        "Backed by L&T parentage",
                        "90%+ retail portfolio with granular borrower base",
                        "Attractive 8.50% coupon yield"
            ],
            "the_bad": [
                        "Subdued collection efficiency during rural weather events"
            ],
            "the_ugly": [
                        "Severe regional drought impairing rural tractor and micro-loan repayments"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE123A08154",
        "ticker": "MMFSL",
        "scrip_code": "935009",
        "series": "N1",
        "instrument_name": "Mahindra & Mahindra Financial 8.40% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.4,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-08-30",
        "maturity_date": "2028-08-30",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10070.0,
        "ytm_pct": 8.21,
        "macaulay_duration_years": 2.4,
        "modified_duration_years": 2.22,
        "metadata": {
            "sector": "Rural Vehicle Financing / Market Leader",
            "promoter_group": "Mahindra & Mahindra (52.2%)",
            "issuer_overview": "Market leader in rural and semi-urban vehicle financing for tractors, utility vehicles, and commercial vehicles.",
            "collateral_type": "Charge on vehicle loan receivables",
            "interest_coverage": 3.2,
            "dscr": 1.8,
            "debt_to_equity": 4.8,
            "credit_rating_rationale": "High strategic importance to M&M automotive and tractor sales distribution.",
            "the_good": [
                        "Dominant tractor financing network",
                        "M&M parentage guarantee cushion",
                        "AAA rating profile"
            ],
            "the_bad": [
                        "Rural economic cycles introduce seasonal GNPA volatility"
            ],
            "the_ugly": [
                        "Consecutive monsoon failures depressing farm purchasing power"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE481G08129",
        "ticker": "ULTRACEMCO",
        "scrip_code": "935010",
        "series": "N1",
        "instrument_name": "UltraTech Cement 7.80% Secured NCD 2030",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.8,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-03-22",
        "maturity_date": "2030-03-22",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.5,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10030.0,
        "ytm_pct": 7.73,
        "macaulay_duration_years": 3.25,
        "modified_duration_years": 3.02,
        "metadata": {
            "sector": "Cement & Building Materials / Aditya Birla Group",
            "promoter_group": "Aditya Birla Group (Grasim Industries)",
            "issuer_overview": "India's largest cement manufacturing company with over 150 MTPA domestic capacity and nationwide distribution.",
            "collateral_type": "Charge on integrated cement plants and grinding units",
            "interest_coverage": 8.5,
            "dscr": 3.8,
            "debt_to_equity": 0.32,
            "credit_rating_rationale": "Market dominance, pricing power, and ultra-conservative debt-to-equity ratio.",
            "the_good": [
                        "Unmatched 150+ MTPA domestic capacity",
                        "Near debt-free profile (0.32x D/E)",
                        "Exceptional interest coverage of 8.5x"
            ],
            "the_bad": [
                        "Low spread over sovereign yields"
            ],
            "the_ugly": [
                        "Prolonged energy and petcoke input cost inflation"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE047A08229",
        "ticker": "GRASIM",
        "scrip_code": "935011",
        "series": "N1",
        "instrument_name": "Grasim Industries 7.75% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.75,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-18",
        "maturity_date": "2028-11-18",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.45,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10020.0,
        "ytm_pct": 7.69,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.27,
        "metadata": {
            "sector": "Chemicals, Viscose & Paints / Aditya Birla Group",
            "promoter_group": "Aditya Birla Group (Kumar Mangalam Birla)",
            "issuer_overview": "Flagship company of the Aditya Birla Group manufacturing Viscose Staple Fibre (VSF), caustic soda, and Birla Opus decorative paints.",
            "collateral_type": "First charge over VSF and chlor-alkali production assets",
            "interest_coverage": 6.8,
            "dscr": 2.9,
            "debt_to_equity": 0.45,
            "credit_rating_rationale": "Global market leadership in VSF and holding company stakes in UltraTech Cement and Aditya Birla Capital.",
            "the_good": [
                        "Global VSF market leadership",
                        "Valuable listed equity holdings portfolio",
                        "Low debt-to-equity ratio of 0.45x"
            ],
            "the_bad": [
                        "High capex investment into the decorative paints business"
            ],
            "the_ugly": [
                        "Extended price war in the Indian decorative paints industry"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE019A08354",
        "ticker": "JSWSTEEL",
        "scrip_code": "935012",
        "series": "N1",
        "instrument_name": "JSW Steel Limited 8.75% Secured NCD 2029",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.75,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-20",
        "maturity_date": "2029-01-20",
        "credit_rating": "CARE AA+",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10080.0,
        "ytm_pct": 8.52,
        "macaulay_duration_years": 2.8,
        "modified_duration_years": 2.59,
        "metadata": {
            "sector": "Steel & Metallurgy / JSW Group",
            "promoter_group": "JSW Group (Sajjan Jindal)",
            "issuer_overview": "India's leading private steel producer operating state-of-the-art Vijayanagar steel manufacturing complex.",
            "collateral_type": "First charge on Vijayanagar expansion plants and machinery",
            "interest_coverage": 4.1,
            "dscr": 2.0,
            "debt_to_equity": 1.15,
            "credit_rating_rationale": "High operating margins, state-of-the-art technology, and strong domestic steel demand.",
            "the_good": [
                        "High 8.75% coupon offering meaningful yield pickup",
                        "Modern low-cost production facilities",
                        "Strong domestic automotive steel tie-ups"
            ],
            "the_bad": [
                        "Higher debt levels than Tata Steel due to continuous capacity expansion"
            ],
            "the_ugly": [
                        "Global metallurgical coal price spikes and dumping of overseas steel"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE397D08234",
        "ticker": "BHARTIARTL",
        "scrip_code": "935013",
        "series": "N1",
        "instrument_name": "Bharti Airtel Limited 8.25% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.25,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-09-25",
        "maturity_date": "2028-09-25",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10090.0,
        "ytm_pct": 7.98,
        "macaulay_duration_years": 2.35,
        "modified_duration_years": 2.18,
        "metadata": {
            "sector": "Telecommunications & Digital Services",
            "promoter_group": "Bharti Enterprises (Sunil Bharti Mittal)",
            "issuer_overview": "Leading global telecommunications company operating across India and 14 African countries with market-leading ARPU.",
            "collateral_type": "First charge on telecom optical fibre assets and mobile switching equipment",
            "interest_coverage": 5.4,
            "dscr": 2.6,
            "debt_to_equity": 1.25,
            "credit_rating_rationale": "Steadily expanding ARPU (> \u20b9200), high ROCE in Indian wireless business, and strong FCF generation.",
            "the_good": [
                        "Highest ARPU in Indian telecom sector",
                        "Robust operating FCF generation",
                        "AA+ rating with upside upgrade potential"
            ],
            "the_bad": [
                        "High AGR statutory liabilities and spectrum payment obligations"
            ],
            "the_ugly": [
                        "Aggressive tariff disruption by competitors suppressing mobile ARPU"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE154A08154",
        "ticker": "ITC",
        "scrip_code": "935014",
        "series": "N1",
        "instrument_name": "ITC Limited 7.25% Secured NCD 2027",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.25,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-14",
        "maturity_date": "2027-02-14",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.8,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10010.0,
        "ytm_pct": 7.21,
        "macaulay_duration_years": 1.7,
        "modified_duration_years": 1.58,
        "metadata": {
            "sector": "FMCG, Paperboards & Agri-Business",
            "promoter_group": "Diversified Institutional Shareholders / BAT",
            "issuer_overview": "Leading FMCG enterprise in India with dominant market leadership in cigarettes, packaged foods (Aashirvaad, Sunfeast), and paperboards.",
            "collateral_type": "First charge on manufacturing facilities and logistics warehouses",
            "interest_coverage": 45.0,
            "dscr": 18.0,
            "debt_to_equity": 0.01,
            "credit_rating_rationale": "Essentially zero debt company with massive free cash flow generation and supreme liquidity.",
            "the_good": [
                        "Virtually zero debt (0.01x D/E)",
                        "Colossal 45x interest coverage",
                        "Pristine AAA safety profile"
            ],
            "the_bad": [
                        "Very rare bond issuances, tightly held by institutional investors"
            ],
            "the_ugly": [
                        "Sharp excise or tax increases on tobacco products"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE009A08182",
        "ticker": "INFY",
        "scrip_code": "935015",
        "series": "N1",
        "instrument_name": "Infosys Limited 7.15% Secured NCD 2027",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.15,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-20",
        "maturity_date": "2027-01-20",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.75,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 9990.0,
        "ytm_pct": 7.19,
        "macaulay_duration_years": 1.65,
        "modified_duration_years": 1.54,
        "metadata": {
            "sector": "IT & Software Services / Global Bluechip",
            "promoter_group": "Infosys Founders / Institutional",
            "issuer_overview": "Global leader in next-generation digital services and consulting with operations in over 56 countries.",
            "collateral_type": "Charge on SEZ tech parks and corporate campuses",
            "interest_coverage": 50.0,
            "dscr": 22.0,
            "debt_to_equity": 0.02,
            "credit_rating_rationale": "Pristine cash reserves of over \u20b915,000 Cr with zero net debt and AAA rating.",
            "the_good": [
                        "Zero net debt balance sheet",
                        "Massive dollar operating free cash flows",
                        "Top tier corporate governance"
            ],
            "the_bad": [
                        "Yield is minimal over government bonds"
            ],
            "the_ugly": [
                        "Sudden severe contraction in global enterprise IT discretionary spending"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE062A08264",
        "ticker": "SBIN",
        "scrip_code": "937001",
        "series": "N1",
        "instrument_name": "State Bank of India 7.72% Tier-II Subordinated Bond 2033",
        "instrument_type": "TIER2",
        "seniority_tier": "SUBORDINATED_TIER2",
        "face_value": 100000.0,
        "coupon_rate_pct": 7.72,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-09-18",
        "maturity_date": "2033-09-18",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 100500.0,
        "ytm_pct": 7.64,
        "macaulay_duration_years": 4.6,
        "modified_duration_years": 4.27,
        "metadata": {
            "sector": "Public Sector Banking / Domestic Systemically Important Bank (D-SIB)",
            "promoter_group": "Government of India (57.49%)",
            "issuer_overview": "India's largest commercial bank managing over 23% of banking assets and deposits.",
            "collateral_type": "Unsecured Subordinated Tier-II Debt (Senior to equity/AT1, subordinated to depositors)",
            "interest_coverage": 2.5,
            "dscr": 1.6,
            "debt_to_equity": 8.5,
            "credit_rating_rationale": "D-SIB status guarantees 100% sovereign capital and liquidity backstop.",
            "the_good": [
                        "Too-Big-To-Fail sovereign backstop",
                        "AAA rating on Tier-II instruments",
                        "Highest liquidity among Indian bank bonds"
            ],
            "the_bad": [
                        "Subordinated in capital hierarchy to retail depositors"
            ],
            "the_ugly": [
                        "Point of Non-Viability (PONV) write-down triggers if bank experiences solvency failure"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE040A08432",
        "ticker": "HDFCBANK",
        "scrip_code": "937002",
        "series": "N1",
        "instrument_name": "HDFC Bank Limited 7.70% Senior Infrastructure Bond 2034",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_UNSECURED",
        "face_value": 100000.0,
        "coupon_rate_pct": 7.7,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-20",
        "maturity_date": "2034-02-20",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 100400.0,
        "ytm_pct": 7.63,
        "macaulay_duration_years": 4.85,
        "modified_duration_years": 4.51,
        "metadata": {
            "sector": "Private Sector Banking / D-SIB",
            "promoter_group": "Widely Held / Institutional",
            "issuer_overview": "India's largest private sector bank with unparalleled retail franchise and lowest credit losses.",
            "collateral_type": "Senior Unsecured Infrastructure Bond (Exempt from CRR/SLR requirements)",
            "interest_coverage": 3.1,
            "dscr": 1.9,
            "debt_to_equity": 7.2,
            "credit_rating_rationale": "D-SIB status, stellar asset quality, and best-in-class risk management culture.",
            "the_good": [
                        "Exempt from statutory CRR/SLR deductions",
                        "Pristine AAA credit quality",
                        "Deep institutional trading liquidity"
            ],
            "the_bad": [
                        "10-year maturity exposes investor to mark-to-market duration fluctuations"
            ],
            "the_ugly": [
                        "Severe systemic credit contraction across Indian banking"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE090A08UE4",
        "ticker": "ICICIBANK",
        "scrip_code": "937003",
        "series": "N1",
        "instrument_name": "ICICI Bank Limited 7.65% Senior Infrastructure Bond 2033",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_UNSECURED",
        "face_value": 100000.0,
        "coupon_rate_pct": 7.65,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-25",
        "maturity_date": "2033-11-25",
        "credit_rating": "ICRA AAA",
        "credit_rating_agency": "ICRA",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 100250.0,
        "ytm_pct": 7.6,
        "macaulay_duration_years": 4.55,
        "modified_duration_years": 4.23,
        "metadata": {
            "sector": "Private Sector Banking / D-SIB",
            "promoter_group": "Institutional / Widely Held",
            "issuer_overview": "Second largest private sector bank in India with industry-leading RoA (2.3%+) and low net NPAs.",
            "collateral_type": "Senior Unsecured Infrastructure Bond",
            "interest_coverage": 3.2,
            "dscr": 1.9,
            "debt_to_equity": 6.8,
            "credit_rating_rationale": "Outstanding RoA expansion, healthy PCR above 80%, and strong capital adequacy.",
            "the_good": [
                        "Highest asset quality profile in private banking",
                        "Strong D-SIB regulatory buffer",
                        "High recovery seniority"
            ],
            "the_bad": [
                        "Yield offers minimal credit risk spread over G-Sec"
            ],
            "the_ugly": [
                        "Systemic real estate defaults impacting wholesale infrastructure exposures"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE238A08450",
        "ticker": "AXISBANK",
        "scrip_code": "937004",
        "series": "N1",
        "instrument_name": "Axis Bank Limited 7.75% Tier-II Subordinated Bond 2032",
        "instrument_type": "TIER2",
        "seniority_tier": "SUBORDINATED_TIER2",
        "face_value": 100000.0,
        "coupon_rate_pct": 7.75,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-10-18",
        "maturity_date": "2032-10-18",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 100450.0,
        "ytm_pct": 7.67,
        "macaulay_duration_years": 4.2,
        "modified_duration_years": 3.9,
        "metadata": {
            "sector": "Private Sector Banking / Tier-1 Private Bank",
            "promoter_group": "SUUTI, LIC, GIC, Institutional",
            "issuer_overview": "Third largest private sector bank with extensive retail franchise following Citibank India consumer acquisition.",
            "collateral_type": "Unsecured Subordinated Tier-II Debt",
            "interest_coverage": 2.9,
            "dscr": 1.8,
            "debt_to_equity": 7.4,
            "credit_rating_rationale": "High operating profitability, healthy capitalization, and successful integration of Citibank consumer book.",
            "the_good": [
                        "AAA rating on Tier-II capital",
                        "Attractive 7.75% coupon rate",
                        "Broad retail deposit base"
            ],
            "the_bad": [
                        "Subordinated to depositors and senior bondholders in liquidation hierarchy"
            ],
            "the_ugly": [
                        "Macro asset quality deterioration in SME portfolio during economic slowdown"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE237A08234",
        "ticker": "KOTAKBANK",
        "scrip_code": "937005",
        "series": "N1",
        "instrument_name": "Kotak Mahindra Bank 7.60% Senior Infrastructure Bond 2031",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_UNSECURED",
        "face_value": 100000.0,
        "coupon_rate_pct": 7.6,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-12",
        "maturity_date": "2031-01-12",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 100150.0,
        "ytm_pct": 7.57,
        "macaulay_duration_years": 3.85,
        "modified_duration_years": 3.58,
        "metadata": {
            "sector": "Private Sector Banking / High Capital Adequacy",
            "promoter_group": "Uday Kotak / Promoters (25.9%)",
            "issuer_overview": "Premier private bank renowned for conservative risk underwriting, industry-leading CASA ratio, and Tier-1 capital adequacy > 21%.",
            "collateral_type": "Senior Unsecured Infrastructure Bond",
            "interest_coverage": 3.6,
            "dscr": 2.1,
            "debt_to_equity": 5.8,
            "credit_rating_rationale": "Highest capital adequacy ratio among all Indian commercial banks and pristine credit metrics.",
            "the_good": [
                        "Capital Adequacy Ratio > 21% (highest among large banks)",
                        "Senior unsecured recovery status",
                        "Conservative credit culture"
            ],
            "the_bad": [
                        "Low yields reflective of its ultra-safe profile"
            ],
            "the_ugly": [
                        "Regulatory IT restrictions impacting online retail customer acquisitions"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE296A08889",
        "ticker": "BAJAJHOUS",
        "scrip_code": "937006",
        "series": "N1",
        "instrument_name": "Bajaj Housing Finance 8.20% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.2,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-10-25",
        "maturity_date": "2028-10-25",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10085.0,
        "ytm_pct": 7.96,
        "macaulay_duration_years": 2.4,
        "modified_duration_years": 2.22,
        "metadata": {
            "sector": "Housing Finance / Upper Layer HFC",
            "promoter_group": "Bajaj Group (Bajaj Finance)",
            "issuer_overview": "Top-tier housing finance company providing home loans, loan against property, and developer financing with lowest GNPA in the HFC sector.",
            "collateral_type": "Charge over residential mortgage loans and book debts",
            "interest_coverage": 3.5,
            "dscr": 2.0,
            "debt_to_equity": 5.1,
            "credit_rating_rationale": "Lowest NPA in the housing finance sector (GNPA < 0.3%) and strong parentage.",
            "the_good": [
                        "Stellar asset quality with GNPA < 0.3%",
                        "Solid collateralization against prime residential real estate",
                        "AAA rating backing"
            ],
            "the_bad": [
                        "Intense pricing competition from public sector banks in prime home loans"
            ],
            "the_ugly": [
                        "Sharp downturn in metropolitan real estate sales reducing prepayment velocity"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE028A08154",
        "ticker": "BANKBARODA",
        "scrip_code": "937007",
        "series": "N1",
        "instrument_name": "Bank of Baroda 7.75% Tier-II Subordinated Bond 2033",
        "instrument_type": "TIER2",
        "seniority_tier": "SUBORDINATED_TIER2",
        "face_value": 100000.0,
        "coupon_rate_pct": 7.75,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-12-05",
        "maturity_date": "2033-12-05",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 100350.0,
        "ytm_pct": 7.69,
        "macaulay_duration_years": 4.5,
        "modified_duration_years": 4.18,
        "metadata": {
            "sector": "Public Sector Banking / Major PSU Bank",
            "promoter_group": "Government of India (63.97%)",
            "issuer_overview": "Second largest public sector bank in India with expansive domestic network and international presence in 17 countries.",
            "collateral_type": "Unsecured Subordinated Tier-II Debt",
            "interest_coverage": 2.6,
            "dscr": 1.7,
            "debt_to_equity": 8.1,
            "credit_rating_rationale": "Majority sovereign ownership, substantial deposit franchise, and sustained RoA improvement.",
            "the_good": [
                        "Strong sovereign majority ownership",
                        "Healthy PCR above 78%",
                        "Attractive Tier-II yield coupon"
            ],
            "the_bad": [
                        "Subordinated to all senior depositors and creditors"
            ],
            "the_ugly": [
                        "Large corporate slippages in international book"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE160A08234",
        "ticker": "PNB",
        "scrip_code": "937008",
        "series": "N1",
        "instrument_name": "Punjab National Bank 7.82% Tier-II Bond 2032",
        "instrument_type": "TIER2",
        "seniority_tier": "SUBORDINATED_TIER2",
        "face_value": 100000.0,
        "coupon_rate_pct": 7.82,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-08-14",
        "maturity_date": "2032-08-14",
        "credit_rating": "ICRA AA+",
        "credit_rating_agency": "ICRA",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 100500.0,
        "ytm_pct": 7.72,
        "macaulay_duration_years": 4.1,
        "modified_duration_years": 3.81,
        "metadata": {
            "sector": "Public Sector Banking / Major PSU Bank",
            "promoter_group": "Government of India (73.15%)",
            "issuer_overview": "Third largest public sector bank in India with dominant market penetration across Northern India.",
            "collateral_type": "Unsecured Subordinated Tier-II Debt",
            "interest_coverage": 2.4,
            "dscr": 1.6,
            "debt_to_equity": 8.8,
            "credit_rating_rationale": "Sovereign majority ownership (73.15%) and steady recovery in asset quality metrics.",
            "the_good": [
                        "High sovereign ownership (73%)",
                        "Yield pickup over private bank senior bonds",
                        "Strong northern deposit franchise"
            ],
            "the_bad": [
                        "Subordinated tier-2 status with bail-in risk"
            ],
            "the_ugly": [
                        "Fraud or operational governance lapses similar to historical events"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE476A08129",
        "ticker": "CANBK",
        "scrip_code": "937009",
        "series": "N1",
        "instrument_name": "Canara Bank 7.78% Tier-II Subordinated Bond 2033",
        "instrument_type": "TIER2",
        "seniority_tier": "SUBORDINATED_TIER2",
        "face_value": 100000.0,
        "coupon_rate_pct": 7.78,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-18",
        "maturity_date": "2033-02-18",
        "credit_rating": "CARE AAA",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 100380.0,
        "ytm_pct": 7.7,
        "macaulay_duration_years": 4.45,
        "modified_duration_years": 4.13,
        "metadata": {
            "sector": "Public Sector Banking / Southern Franchise",
            "promoter_group": "Government of India (62.93%)",
            "issuer_overview": "Major public sector commercial bank with dominant franchise across Southern India and high credit growth.",
            "collateral_type": "Unsecured Subordinated Tier-II Capital",
            "interest_coverage": 2.6,
            "dscr": 1.7,
            "debt_to_equity": 8.2,
            "credit_rating_rationale": "Strong sovereign ownership and rapid expansion in retail credit book.",
            "the_good": [
                        "Sovereign backing",
                        "Healthy operating profitability",
                        "AAA rating profile on Tier-II"
            ],
            "the_bad": [
                        "Subordinated capital structure position"
            ],
            "the_ugly": [
                        "Rise in slippages in MSME lending portfolios"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE121H08145",
        "ticker": "CHOLAFIN",
        "scrip_code": "937010",
        "series": "N1",
        "instrument_name": "Cholamandalam Investment 8.65% Secured NCD 2029",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.65,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-03-05",
        "maturity_date": "2029-03-05",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10110.0,
        "ytm_pct": 8.35,
        "macaulay_duration_years": 2.8,
        "modified_duration_years": 2.58,
        "metadata": {
            "sector": "Vehicle Finance & Loan Against Property / Murugappa Group",
            "promoter_group": "Murugappa Group (51.5%)",
            "issuer_overview": "Leading non-banking finance company specializing in vehicle finance, home equity, and loan against property.",
            "collateral_type": "First charge on vehicle loan receivables",
            "interest_coverage": 3.1,
            "dscr": 1.8,
            "debt_to_equity": 5.8,
            "credit_rating_rationale": "High management quality, conservative underwriting, and diversified product portfolio.",
            "the_good": [
                        "Murugappa Group parentage",
                        "Strong return on equity (> 20%)",
                        "Robust collateralization"
            ],
            "the_bad": [
                        "Cyclical vulnerability in used commercial vehicle loan portfolios"
            ],
            "the_ugly": [
                        "Fuel price spikes squeezing fleet operator cash flows"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE721A08354",
        "ticker": "SHRIRAMFIN",
        "scrip_code": "937011",
        "series": "N1",
        "instrument_name": "Shriram Finance Limited 8.85% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.85,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-08",
        "maturity_date": "2028-11-08",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10140.0,
        "ytm_pct": 8.42,
        "macaulay_duration_years": 2.35,
        "modified_duration_years": 2.17,
        "metadata": {
            "sector": "Commercial Vehicle & MSME Finance / Shriram Group",
            "promoter_group": "Shriram Group",
            "issuer_overview": "India's largest retail NBFC specializing in pre-owned commercial vehicle financing, MSME loans, and two-wheelers.",
            "collateral_type": "First charge over hypothecated vehicles and loan receivables",
            "interest_coverage": 3.0,
            "dscr": 1.7,
            "debt_to_equity": 4.9,
            "credit_rating_rationale": "Niche expertise in used commercial vehicle financing and strong collection infrastructure.",
            "the_good": [
                        "High coupon of 8.85% providing strong regular cash flow",
                        "Granular loan book across small road transport operators",
                        "High net interest margins (> 8.5%)"
            ],
            "the_bad": [
                        "Borrower base consists of cash-flow sensitive individual transport operators"
            ],
            "the_ugly": [
                        "Severe freight rate collapse causing mass truck loan defaults"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE414G08321",
        "ticker": "MUTHOOTFIN",
        "scrip_code": "937012",
        "series": "N1",
        "instrument_name": "Muthoot Finance Limited 8.75% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.75,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-10-15",
        "maturity_date": "2028-10-15",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.45,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10125.0,
        "ytm_pct": 8.38,
        "macaulay_duration_years": 2.4,
        "modified_duration_years": 2.21,
        "metadata": {
            "sector": "Gold Loan NBFC / Market Leader",
            "promoter_group": "Muthoot Family (George Alexander Muthoot)",
            "issuer_overview": "India's largest gold financing company holding over 180 tonnes of gold jewellery as loan collateral.",
            "collateral_type": "First charge on physical gold jewellery collateral stored in bank-grade vaults",
            "interest_coverage": 3.8,
            "dscr": 2.1,
            "debt_to_equity": 3.2,
            "credit_rating_rationale": "Exceptional collateral liquidability with physical gold jewellery custody.",
            "the_good": [
                        "Physical gold jewellery in vault provides 100%+ tangible collateral backing",
                        "Low debt-to-equity ratio of 3.2x",
                        "Strong return on assets (> 4.8%)"
            ],
            "the_bad": [
                        "Regulatory LTV cap constraints (75% max LTV)"
            ],
            "the_ugly": [
                        "Sudden 30%+ crash in domestic gold prices breaching collateral values"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE522D08145",
        "ticker": "MANAPPURAM",
        "scrip_code": "937013",
        "series": "N1",
        "instrument_name": "Manappuram Finance Limited 9.15% Secured NCD 2027",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.15,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-08",
        "maturity_date": "2027-01-08",
        "credit_rating": "CRISIL AA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10160.0,
        "ytm_pct": 8.45,
        "macaulay_duration_years": 1.65,
        "modified_duration_years": 1.52,
        "metadata": {
            "sector": "Gold Loan & Microfinance / Diversified NBFC",
            "promoter_group": "V.P. Nandakumar & Promoters",
            "issuer_overview": "Prominent gold loan NBFC diversifying into microfinance (Asirvad), housing loans, and commercial vehicles.",
            "collateral_type": "First charge over gold loan receivables and physical jewellery pledged",
            "interest_coverage": 3.2,
            "dscr": 1.8,
            "debt_to_equity": 3.6,
            "credit_rating_rationale": "Liquid gold collateral cushion and strong capital adequacy.",
            "the_good": [
                        "High coupon of 9.15% for retail allocators",
                        "Short duration (1.65y)",
                        "Secured by physical gold collateral"
            ],
            "the_bad": [
                        "Microfinance subsidiary introduces uncollateralized credit risk"
            ],
            "the_ugly": [
                        "Microfinance delinquency wave triggered by regional rural disruptions"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE551W08092",
        "ticker": "POONAWALLA",
        "scrip_code": "937014",
        "series": "N1",
        "instrument_name": "Poonawalla Fincorp Limited 8.55% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.55,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-09-15",
        "maturity_date": "2028-09-15",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10115.0,
        "ytm_pct": 8.22,
        "macaulay_duration_years": 2.4,
        "modified_duration_years": 2.22,
        "metadata": {
            "sector": "Consumer & SME Lending / Cyrus Poonawalla Group",
            "promoter_group": "Poonawalla Group (Serum Institute)",
            "issuer_overview": "Rapidly expanding non-bank lender focused on prime consumer and SME financing with superior digital architecture.",
            "collateral_type": "Charge on consumer and MSME loan assets",
            "interest_coverage": 3.6,
            "dscr": 2.1,
            "debt_to_equity": 2.8,
            "credit_rating_rationale": "Exceptional capital adequacy (> 35%), low leverage, and backing of the Cyrus Poonawalla Group.",
            "the_good": [
                        "Ultra-low leverage of 2.8x D/E",
                        "Pristine capital adequacy ratio (> 35%)",
                        "Highest AAA safety rating"
            ],
            "the_bad": [
                        "Aggressive growth phase requires watchful risk underwriting monitoring"
            ],
            "the_ugly": [
                        "Unsecured personal loan portfolio seasoning with higher credit defaults"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE092T08754",
        "ticker": "IDFCFIRSTB",
        "scrip_code": "937015",
        "series": "N1",
        "instrument_name": "IDFC FIRST Bank 8.40% Tier-II Subordinated Bond 2033",
        "instrument_type": "TIER2",
        "seniority_tier": "SUBORDINATED_TIER2",
        "face_value": 100000.0,
        "coupon_rate_pct": 8.4,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-20",
        "maturity_date": "2033-11-20",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 100650.0,
        "ytm_pct": 8.28,
        "macaulay_duration_years": 4.55,
        "modified_duration_years": 4.21,
        "metadata": {
            "sector": "Private Sector Banking / Fast-Growing Retail Bank",
            "promoter_group": "IDFC Financial Holding / Institutional",
            "issuer_overview": "Fast-growing universal private bank with industry-leading CASA ratio, retail loan granularity, and technological innovation.",
            "collateral_type": "Unsecured Subordinated Tier-II Debt",
            "interest_coverage": 2.8,
            "dscr": 1.7,
            "debt_to_equity": 7.6,
            "credit_rating_rationale": "High CASA ratio (> 47%), strong retail asset diversification, and clean legacy corporate cleanup.",
            "the_good": [
                        "High Tier-II coupon of 8.40%",
                        "Expanding retail franchise with high CASA",
                        "AA+ rating with positive outlook"
            ],
            "the_bad": [
                        "Tier-II subordinated status"
            ],
            "the_ugly": [
                        "Unsecured credit card and micro-loan portfolio stress"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE742F08092",
        "ticker": "ADANIPORTS",
        "scrip_code": "938001",
        "series": "N1",
        "instrument_name": "Adani Ports & SEZ 8.75% Secured NCD 2029",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.75,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-25",
        "maturity_date": "2029-01-25",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.45,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10120.0,
        "ytm_pct": 8.41,
        "macaulay_duration_years": 2.8,
        "modified_duration_years": 2.59,
        "metadata": {
            "sector": "Ports & Multimodal Logistics / Transport Monopoly",
            "promoter_group": "Adani Group (Gautam Adani)",
            "issuer_overview": "India's largest commercial port operator and integrated logistics provider managing 14 ports accounting for ~27% of national cargo.",
            "collateral_type": "First charge on Mundra and Hazira port terminal assets",
            "interest_coverage": 4.8,
            "dscr": 2.3,
            "debt_to_equity": 1.05,
            "credit_rating_rationale": "Unmatched cargo market share, sticky volume agreements, and high EBITDA margins (~70%).",
            "the_good": [
                        "70%+ EBITDA margins in port operations",
                        "27% national cargo market share",
                        "First charge on premier port assets"
            ],
            "the_bad": [
                        "Adani Group conglomerate scrutiny and debt headline noise"
            ],
            "the_ugly": [
                        "Geopolitical trade disruption or major environmental litigation"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE123E08129",
        "ticker": "RENEW",
        "scrip_code": "938002",
        "series": "N1",
        "instrument_name": "ReNew Solar Power 8.95% Secured Green Bond 2028",
        "instrument_type": "GREEN_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.95,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-08-18",
        "maturity_date": "2028-08-18",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10140.0,
        "ytm_pct": 8.52,
        "macaulay_duration_years": 2.4,
        "modified_duration_years": 2.21,
        "metadata": {
            "sector": "Renewable Energy / Solar IPP",
            "promoter_group": "Sumant Sinha / CPPIB / Goldman Sachs",
            "issuer_overview": "Premier utility-scale renewable energy producer with over 13 GW of operational wind and solar assets.",
            "collateral_type": "Trustee-backed first charge over operational solar park assets and SECI PPAs",
            "interest_coverage": 3.2,
            "dscr": 1.6,
            "debt_to_equity": 3.8,
            "credit_rating_rationale": "Long-term 25-year PPAs signed with central sovereign entity Solar Energy Corporation of India (SECI).",
            "the_good": [
                        "High 8.95% coupon yield",
                        "25-year sovereign-backed SECI PPAs",
                        "Strong institutional shareholders (CPPIB)"
            ],
            "the_bad": [
                        "High debt leverage typical of renewable project finance"
            ],
            "the_ugly": [
                        "Severe curtailment or grid interconnection delays by state load dispatch centers"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE123P08056",
        "ticker": "JSWENERGY",
        "scrip_code": "938003",
        "series": "N1",
        "instrument_name": "JSW Energy Limited 8.60% Secured NCD 2029",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.6,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-12",
        "maturity_date": "2029-02-12",
        "credit_rating": "CARE AA+",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10080.0,
        "ytm_pct": 8.36,
        "macaulay_duration_years": 2.8,
        "modified_duration_years": 2.59,
        "metadata": {
            "sector": "Power Generation & Energy Transition / JSW Group",
            "promoter_group": "JSW Group (Sajjan Jindal)",
            "issuer_overview": "Independent power producer transitioning aggressively into renewable energy with operational hydro, thermal, and wind assets.",
            "collateral_type": "Charge on hydro and wind power generation units",
            "interest_coverage": 3.8,
            "dscr": 1.9,
            "debt_to_equity": 1.4,
            "credit_rating_rationale": "High proportion of long-term power purchase agreements ensuring steady cash flows.",
            "the_good": [
                        "Long-term PPAs for over 85% of total capacity",
                        "Conservative leverage (1.4x D/E)",
                        "Strong 8.60% coupon"
            ],
            "the_bad": [
                        "Thermal generation component exposed to imported coal prices"
            ],
            "the_ugly": [
                        "Payment default by distressed State Electricity Boards (SEBs)"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE205A08129",
        "ticker": "TORNTPOWER",
        "scrip_code": "938004",
        "series": "N1",
        "instrument_name": "Torrent Power Limited 8.45% Secured NCD 2028",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.45,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-10-28",
        "maturity_date": "2028-10-28",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10090.0,
        "ytm_pct": 8.18,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.27,
        "metadata": {
            "sector": "Power Generation & Distribution / Torrent Group",
            "promoter_group": "Torrent Group (Samir Mehta & Sudhir Mehta)",
            "issuer_overview": "One of India's most efficient private power utilities with regulated distribution circles in Ahmedabad, Surat, and Agra.",
            "collateral_type": "First charge on gas-based and solar power generation assets",
            "interest_coverage": 4.5,
            "dscr": 2.2,
            "debt_to_equity": 0.85,
            "credit_rating_rationale": "Industry-lowest AT&C transmission losses (< 4%) and strong regulated distribution returns.",
            "the_good": [
                        "Industry-lowest AT&C losses (< 4%)",
                        "Regulated cash flow distribution circles",
                        "Conservative leverage of 0.85x D/E"
            ],
            "the_bad": [
                        "Spot LNG price fluctuations impacting gas plant utilization"
            ],
            "the_ugly": [
                        "Sudden adverse tariff orders by state regulatory commissions"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE123Z08129",
        "ticker": "DIAL",
        "scrip_code": "938005",
        "series": "N1",
        "instrument_name": "Delhi International Airport 9.25% Senior Secured NCD 2030",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.25,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-03-01",
        "maturity_date": "2030-03-01",
        "credit_rating": "CRISIL AA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10150.0,
        "ytm_pct": 8.85,
        "macaulay_duration_years": 3.25,
        "modified_duration_years": 3.01,
        "metadata": {
            "sector": "Aviation Infrastructure / Monopoly Concession",
            "promoter_group": "GMR Airports & Airports Authority of India",
            "issuer_overview": "Operator of Indira Gandhi International Airport (DEL), India's busiest aviation hub serving 70M+ passengers annually.",
            "collateral_type": "First charge on airport duty-free revenues, aeronautical charges, and commercial real estate leases",
            "interest_coverage": 3.1,
            "dscr": 1.7,
            "debt_to_equity": 2.4,
            "credit_rating_rationale": "Monopoly gateway airport with regulated aero tariffs and growing commercial non-aero revenues.",
            "the_good": [
                        "Capital city monopoly airport infrastructure",
                        "High 9.25% coupon yield",
                        "Robust non-aero spending growth"
            ],
            "the_bad": [
                        "Regulatory delays in AERA aeronautical tariff determination"
            ],
            "the_ugly": [
                        "Global pandemic or geopolitical air travel groundings similar to COVID-19"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE00SD07012",
        "ticker": "WINT_INVOICEX_1",
        "scrip_code": "939001",
        "series": "SDI-1",
        "instrument_name": "InvoiceX Tata Anchor Pool Securitised Debt Instrument",
        "instrument_type": "SDI",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 10.75,
        "coupon_frequency": "MONTHLY",
        "issue_date": "2024-03-01",
        "maturity_date": "2025-12-01",
        "credit_rating": "CRISIL A(SO)",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.25,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": True,
        "originator": "KredX Enterprise Trust",
        "fldg_pct": 10.0,
        "last_traded_price": 10000.0,
        "ytm_pct": 10.75,
        "macaulay_duration_years": 0.85,
        "modified_duration_years": 0.77,
        "metadata": {
            "sector": "Supply Chain Trade Finance / SEBI SDI Framework",
            "promoter_group": "Bankruptcy-Remote Trust / SEBI-Registered OBPP (Wint Wealth)",
            "issuer_overview": "Securitised Debt Instrument structured under SEBI (Issue and Listing of Securitised Debt Instruments) Regulations. Backed by corporate anchor-accepted invoices payable by high-rated industrial groups.",
            "collateral_type": "First charge over accepted enterprise trade invoices and dedicated escrow account",
            "interest_coverage": 4.5,
            "dscr": 2.2,
            "debt_to_equity": 0.0,
            "credit_rating_rationale": "Bankruptcy-remote SPV, accepted invoice mandates on AAA/AA rated anchors, and 10% cash FLDG buffer.",
            "the_good": [
                        "High 10.75% YTM paid monthly directly into investor bank accounts",
                        "10% cash First Loss Default Guarantee (FLDG) reserve absorbs vendor default",
                        "Ultra-short 0.85-year duration insulated from interest rate cycles"
            ],
            "the_bad": [
                        "Non-sovereign credit exposure to underlying anchor trade buyers",
                        "Secondary market liquidity is modest; structured for hold-to-maturity"
            ],
            "the_ugly": [
                        "Systemic commercial dispute between buyer anchors and suppliers freezing invoice clearing"
            ],
            "collated_sources": [
                        "Wint Wealth",
                        "BSE Debt"
            ]
        }
    },
    {
        "isin": "INE00SD07020",
        "ticker": "WINT_LOANX_2",
        "scrip_code": "939002",
        "series": "SDI-2",
        "instrument_name": "LoanX Micro-LAP Senior Pool Securitised Debt Instrument",
        "instrument_type": "SDI",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 11.25,
        "coupon_frequency": "MONTHLY",
        "issue_date": "2024-02-15",
        "maturity_date": "2026-02-15",
        "credit_rating": "ICRA A+(SO)",
        "credit_rating_agency": "ICRA",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": True,
        "originator": "Vivriti Capital / Shriram Housing Trust",
        "fldg_pct": 12.0,
        "last_traded_price": 10020.0,
        "ytm_pct": 11.15,
        "macaulay_duration_years": 1.15,
        "modified_duration_years": 1.04,
        "metadata": {
            "sector": "Securitized Retail MSME Loans / Property Backed",
            "promoter_group": "Trustee Protected / Wint Wealth OBPP",
            "issuer_overview": "SEBI-regulated securitized debt instrument backed by a diversified pool of 1,200+ micro loan-against-property (LAP) contracts with average LTV of 48%.",
            "collateral_type": "Registered equitable mortgages over self-occupied residential and commercial property",
            "interest_coverage": 3.8,
            "dscr": 2.0,
            "debt_to_equity": 0.0,
            "credit_rating_rationale": "Senior tranche protection with 12% cash collateral FLDG and conservative 48% property LTV.",
            "the_good": [
                        "11.25% annualized monthly cash flow yield",
                        "Low 48% weighted average property LTV ensures strong recovery",
                        "12% junior subordination absorbs early defaults"
            ],
            "the_bad": [
                        "Granular retail borrower risk across Tier-2/3 geographies"
            ],
            "the_ugly": [
                        "Prolonged legal delays in SARFAESI property enforcement during borrower insolvency"
            ],
            "collated_sources": [
                        "Wint Wealth",
                        "BSE Debt"
            ]
        }
    },
    {
        "isin": "INE00SD07038",
        "ticker": "GRIP_LEASEX_1",
        "scrip_code": "939003",
        "series": "SDI-3",
        "instrument_name": "LeaseX EV Fleet Rental Securitised Debt Instrument",
        "instrument_type": "SDI",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 11.5,
        "coupon_frequency": "MONTHLY",
        "issue_date": "2024-01-10",
        "maturity_date": "2026-07-10",
        "credit_rating": "CRISIL A(SO)",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": True,
        "originator": "Grip Invest / Zypp Electric Mobility Trust",
        "fldg_pct": 15.0,
        "last_traded_price": 10000.0,
        "ytm_pct": 11.5,
        "macaulay_duration_years": 1.35,
        "modified_duration_years": 1.22,
        "metadata": {
            "sector": "Equipment Lease Rental Discounting (LRD) / Green Mobility",
            "promoter_group": "SEBI SDI Special Purpose Vehicle / Grip Invest",
            "issuer_overview": "Structured pass-through securitised debt instrument backed by commercial EV two-wheeler leases to tier-1 quick-commerce operators (Zomato, Swiggy, Zepto).",
            "collateral_type": "Hypothecation of commercial EV fleet and assigned monthly lease rentals",
            "interest_coverage": 3.6,
            "dscr": 1.9,
            "debt_to_equity": 0.0,
            "credit_rating_rationale": "Secured by physical EV fleet assets and 15% originator cash credit enhancement.",
            "the_good": [
                        "High 11.50% YTM for fixed-income alpha",
                        "Strong 15% cash FLDG buffer",
                        "Monthly principal and interest amortization"
            ],
            "the_bad": [
                        "Residual battery degradation risk on end-of-lease EV two-wheelers"
            ],
            "the_ugly": [
                        "Sudden bankruptcy or operational freeze of anchor delivery fleet lessees"
            ],
            "collated_sources": [
                        "Grip Invest",
                        "NSE Debt"
            ]
        }
    },
    {
        "isin": "INE467B08012",
        "ticker": "TCS",
        "scrip_code": "935016",
        "series": "N1",
        "instrument_name": "Tata Consultancy Services 7.10% Secured NCD 2027",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.1,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-03-01",
        "maturity_date": "2027-03-01",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.85,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10005.0,
        "ytm_pct": 7.08,
        "macaulay_duration_years": 1.7,
        "modified_duration_years": 1.59,
        "metadata": {
            "sector": "IT & Technology Services / Tata Group",
            "promoter_group": "Tata Sons (72.3%)",
            "issuer_overview": "India's largest IT software exporter with pristine cash balance sheet exceeding \u20b940,000 Cr and global enterprise delivery footprint.",
            "collateral_type": "Charge on enterprise headquarters and owned campus properties",
            "interest_coverage": 58.0,
            "dscr": 25.0,
            "debt_to_equity": 0.01,
            "credit_rating_rationale": "CRISIL AAA rating underpinned by market-leading operating margin (~25%), zero net debt, and immense dollar operating cash flows.",
            "the_good": [
                        "Virtually zero debt (0.01x D/E)",
                        "Immense 58x interest coverage",
                        "Pristine AAA safety profile with zero credit loss"
            ],
            "the_bad": [
                        "Tight yields offering thin credit risk premiums over sovereign gilts"
            ],
            "the_ugly": [
                        "Severe contraction in global enterprise IT discretionary spending"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE038A08125",
        "ticker": "HINDALCO",
        "scrip_code": "935017",
        "series": "N1",
        "instrument_name": "Hindalco Industries 8.20% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.2,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-09-15",
        "maturity_date": "2028-09-15",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10060.0,
        "ytm_pct": 8.05,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.27,
        "metadata": {
            "sector": "Metals & Mining / Aditya Birla Group",
            "promoter_group": "Aditya Birla Group (Kumar Mangalam Birla)",
            "issuer_overview": "Global aluminium and copper major operating Novelis in North America and integrated low-cost smelters across India.",
            "collateral_type": "First charge on Renukoot aluminium smelting complex",
            "interest_coverage": 4.6,
            "dscr": 2.1,
            "debt_to_equity": 0.65,
            "credit_rating_rationale": "High downstream product mix from Novelis and first-quartile cost position in primary aluminium.",
            "the_good": [
                        "Strong 8.20% coupon with 1.40x asset cover",
                        "De-risked global can sheet portfolio at Novelis",
                        "Prudent 0.65x leverage"
            ],
            "the_bad": [
                        "London Metal Exchange (LME) commodity price cyclicality"
            ],
            "the_ugly": [
                        "Energy cost spikes or prolonged smelter potline outages"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE205A08192",
        "ticker": "VEDL",
        "scrip_code": "935018",
        "series": "N1",
        "instrument_name": "Vedanta Limited 9.85% Secured NCD 2027",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.85,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-10",
        "maturity_date": "2027-01-10",
        "credit_rating": "CRISIL AA-",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10120.0,
        "ytm_pct": 9.35,
        "macaulay_duration_years": 1.65,
        "modified_duration_years": 1.51,
        "metadata": {
            "sector": "Natural Resources & Diversified Metals",
            "promoter_group": "Vedanta Resources (Anil Agarwal)",
            "issuer_overview": "Diversified natural resources major operating zinc (Hindustan Zinc), oil & gas (Cairn India), and aluminium businesses.",
            "collateral_type": "First pari-passu charge on designated industrial plant assets",
            "interest_coverage": 3.2,
            "dscr": 1.6,
            "debt_to_equity": 1.25,
            "credit_rating_rationale": "High operating profitability from low-cost zinc and oil assets balancing parent debt refinancing requirements.",
            "the_good": [
                        "High 9.85% coupon yield offering generous +275 bps credit spread",
                        "Top-tier lowest cost zinc producer globally via HZL",
                        "First charge asset cover of 1.35x"
            ],
            "the_bad": [
                        "High dividend payout requirements to fund parent debt"
            ],
            "the_ugly": [
                        "Parent holding company debt maturity cliffs triggering credit rating downgrades"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE233A08082",
        "ticker": "GODREJIND",
        "scrip_code": "935019",
        "series": "N1",
        "instrument_name": "Godrej Industries 8.15% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.15,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-10-20",
        "maturity_date": "2028-10-20",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10040.0,
        "ytm_pct": 8.04,
        "macaulay_duration_years": 2.55,
        "modified_duration_years": 2.36,
        "metadata": {
            "sector": "Diversified Holding Company / Consumer & Chemicals",
            "promoter_group": "Godrej Family (Adi Godrej Group)",
            "issuer_overview": "Holding company for Godrej Consumer Products, Godrej Properties, and Godrej Agrovet with manufacturing presence in oleochemicals.",
            "collateral_type": "Charge on commercial real estate and listed investments",
            "interest_coverage": 4.2,
            "dscr": 2.0,
            "debt_to_equity": 0.58,
            "credit_rating_rationale": "Strong financial flexibility derived from market value of listed group holdings exceeding \u20b975,000 Cr.",
            "the_good": [
                        "Tremendous market value of listed investments provides pristine credit support",
                        "125-year brand heritage",
                        "Clean AA+ balance sheet"
            ],
            "the_bad": [
                        "Holding company discount in market valuations"
            ],
            "the_ugly": [
                        "Sharp correction across listed equity subsidiaries compressing collateral value"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE423A08112",
        "ticker": "ADANIENT",
        "scrip_code": "935020",
        "series": "N1",
        "instrument_name": "Adani Enterprises 9.15% Secured NCD 2027",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.15,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-05",
        "maturity_date": "2027-02-05",
        "credit_rating": "CARE A+",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.45,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10080.0,
        "ytm_pct": 8.82,
        "macaulay_duration_years": 1.75,
        "modified_duration_years": 1.61,
        "metadata": {
            "sector": "Conglomerate Incubator / Energy & Infrastructure",
            "promoter_group": "Adani Group (Gautam Adani)",
            "issuer_overview": "Flagship incubator of the Adani Group pioneering airports, green hydrogen, roads, and data centers across India.",
            "collateral_type": "First pari-passu charge on mining services equipment and infra cash flows",
            "interest_coverage": 2.9,
            "dscr": 1.5,
            "debt_to_equity": 1.35,
            "credit_rating_rationale": "Proven incubation track record and strategic national importance across infrastructure sectors.",
            "the_good": [
                        "High 9.15% coupon offering high carry",
                        "1.45x tangible asset cover",
                        "Strong access to domestic commercial banks"
            ],
            "the_bad": [
                        "Conglomerate headline noise and elevated incubation leverage"
            ],
            "the_ugly": [
                        "Adverse regulatory inquiries into offshore investor ownership structures"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE280A08015",
        "ticker": "TITAN",
        "scrip_code": "935021",
        "series": "N1",
        "instrument_name": "Titan Company 7.30% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.3,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-12",
        "maturity_date": "2028-11-12",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.6,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10015.0,
        "ytm_pct": 7.26,
        "macaulay_duration_years": 2.6,
        "modified_duration_years": 2.42,
        "metadata": {
            "sector": "Lifestyle Retail & Jewellery / Tata Group",
            "promoter_group": "Tata Group & TIDCO",
            "issuer_overview": "India's premier lifestyle retailer dominating organized jewellery (Tanishq, Mia, Zoya), watches (Titan, Fastrack), and eyewear.",
            "collateral_type": "Charge on central jewellery inventory and corporate logistics hub",
            "interest_coverage": 14.5,
            "dscr": 6.2,
            "debt_to_equity": 0.28,
            "credit_rating_rationale": "CRISIL AAA rating driven by dominant jewellery market share, exceptional working capital management, and robust cash generation.",
            "the_good": [
                        "Unassailable brand trust in consumer retail",
                        "Low balance sheet leverage of 0.28x D/E",
                        "Robust ICR of 14.5x"
            ],
            "the_bad": [
                        "Yield is minimal over government bonds"
            ],
            "the_ugly": [
                        "Sudden mandatory increase in gold import customs tariffs disrupting consumer demand"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE075A08092",
        "ticker": "WIPRO",
        "scrip_code": "935022",
        "series": "N1",
        "instrument_name": "Wipro Limited 7.18% Secured NCD 2027",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.18,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-15",
        "maturity_date": "2027-01-15",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.7,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10005.0,
        "ytm_pct": 7.16,
        "macaulay_duration_years": 1.6,
        "modified_duration_years": 1.49,
        "metadata": {
            "sector": "IT Consulting & Global Tech Services",
            "promoter_group": "Azim Premji / Institutional",
            "issuer_overview": "Global information technology, consulting and business process services company operating in 65+ countries with \u20b985,000+ Cr revenue.",
            "collateral_type": "Charge on Sarjapur corporate tech park campus in Bengaluru",
            "interest_coverage": 28.0,
            "dscr": 12.0,
            "debt_to_equity": 0.08,
            "credit_rating_rationale": "High net cash position, conservative financial policy, and global client diversification.",
            "the_good": [
                        "Pristine net cash balance sheet",
                        "High 28x interest coverage",
                        "Top tier corporate governance"
            ],
            "the_bad": [
                        "Thin credit risk spread over sovereign gilts"
            ],
            "the_ugly": [
                        "Extended loss of market share to Tier-1 global IT competitors"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE021A08045",
        "ticker": "ASIANPAINT",
        "scrip_code": "935023",
        "series": "N1",
        "instrument_name": "Asian Paints 7.25% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.25,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-12-05",
        "maturity_date": "2028-12-05",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.8,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10020.0,
        "ytm_pct": 7.2,
        "macaulay_duration_years": 2.55,
        "modified_duration_years": 2.38,
        "metadata": {
            "sector": "Decorative Coatings & Home Decor",
            "promoter_group": "Danis, Chokseys, Vakils / Institutional",
            "issuer_overview": "India's largest decorative coatings manufacturer controlling over 50% of the domestic paint market with an unmatched tinting network.",
            "collateral_type": "Charge on Rohtak and Mysuru automated manufacturing plants",
            "interest_coverage": 32.0,
            "dscr": 14.0,
            "debt_to_equity": 0.05,
            "credit_rating_rationale": "Unrivalled domestic distribution moat, superior ROCE (>30%), and virtually debt-free balance sheet.",
            "the_good": [
                        "Unmatched distribution moat across 75,000+ retail dealers",
                        "Negligible 0.05x leverage",
                        "CRISIL AAA highest safety"
            ],
            "the_bad": [
                        "Yield is minimal over government bonds"
            ],
            "the_ugly": [
                        "Aggressive price war launched by new mega conglomerate entrants in the coatings sector"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE044A08082",
        "ticker": "SUNPHARMA",
        "scrip_code": "935024",
        "series": "N1",
        "instrument_name": "Sun Pharmaceutical Industries 7.20% Secured NCD 2027",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.2,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-20",
        "maturity_date": "2027-02-20",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.75,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10010.0,
        "ytm_pct": 7.17,
        "macaulay_duration_years": 1.7,
        "modified_duration_years": 1.59,
        "metadata": {
            "sector": "Pharmaceuticals & Specialty Formulations",
            "promoter_group": "Dilip Shanghvi Family",
            "issuer_overview": "India's largest pharmaceutical company and top global generic manufacturer with strong US global specialty portfolio (Ilumya, Cequa).",
            "collateral_type": "Charge on Halol and Baddi formulation facilities",
            "interest_coverage": 24.0,
            "dscr": 10.5,
            "debt_to_equity": 0.06,
            "credit_rating_rationale": "High operating profitability from specialty formulations, global market diversification, and zero net debt.",
            "the_good": [
                        "Dominant #1 Indian pharma market share (>8.5%)",
                        "Substantial global specialty franchise generating dollar EBITDA",
                        "0.06x negligible leverage"
            ],
            "the_bad": [
                        "Tight yields offering thin credit risk premiums over sovereign gilts"
            ],
            "the_ugly": [
                        "US FDA import alerts on key manufacturing facilities"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE089A08023",
        "ticker": "DRREDDY",
        "scrip_code": "935025",
        "series": "N1",
        "instrument_name": "Dr. Reddy's Laboratories 7.22% Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.22,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-10-15",
        "maturity_date": "2028-10-15",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.65,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10005.0,
        "ytm_pct": 7.21,
        "macaulay_duration_years": 2.5,
        "modified_duration_years": 2.33,
        "metadata": {
            "sector": "Global Generics & Biosimilars",
            "promoter_group": "Dr. K. Anji Reddy Family",
            "issuer_overview": "Global pharmaceutical company providing affordable generics, active pharmaceutical ingredients (APIs), and biosimilars worldwide.",
            "collateral_type": "Charge on Bachupally and Miryalaguda API plants",
            "interest_coverage": 21.0,
            "dscr": 9.0,
            "debt_to_equity": 0.09,
            "credit_rating_rationale": "High cash reserves of \u20b96,000+ Cr, robust R&D pipeline in biosimilars, and pristine AAA credit rating.",
            "the_good": [
                        "Global generic scale with diversified geographical presence",
                        "High ICR of 21.0x",
                        "Zero net debt balance sheet"
            ],
            "the_bad": [
                        "Yield premium over G-Sec is modest (~25 bps)"
            ],
            "the_ugly": [
                        "Intense price erosion in US generic oral solids market"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE095A08082",
        "ticker": "INDUSINDBK",
        "scrip_code": "937016",
        "series": "N1",
        "instrument_name": "IndusInd Bank 8.45% Subordinated Tier-II Bond 2031",
        "instrument_type": "TIER2",
        "seniority_tier": "SUBORDINATED_TIER2",
        "face_value": 100000.0,
        "coupon_rate_pct": 8.45,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-18",
        "maturity_date": "2031-01-18",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10020.0,
        "ytm_pct": 8.41,
        "macaulay_duration_years": 4.2,
        "modified_duration_years": 3.87,
        "metadata": {
            "sector": "Private Sector Banking / Commercial Lending",
            "promoter_group": "Hinduja Group (16.5%)",
            "issuer_overview": "Tier-1 private commercial bank with dominant vehicle finance, microfinance, and corporate lending franchises across India.",
            "collateral_type": "Unsecured Subordinated Regulatory Capital (Tier-II)",
            "interest_coverage": 2.4,
            "dscr": 1.6,
            "debt_to_equity": 6.8,
            "credit_rating_rationale": "Comfortable capitalization buffers (CRAR > 17.5%) and resilient retail vehicle finance profitability.",
            "the_good": [
                        "High 8.45% Tier-II coupon yield",
                        "Top market share in commercial vehicle and tractor finance",
                        "Strong 17%+ CRAR cushion"
            ],
            "the_bad": [
                        "Subordinated liquidation status under Basel III regulations"
            ],
            "the_ugly": [
                        "Sudden systemic stress in microfinance (Bharat Financial) borrower segment"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE528G08412",
        "ticker": "YESBANK",
        "scrip_code": "937017",
        "series": "N1",
        "instrument_name": "Yes Bank 8.75% Senior Infrastructure Bond 2029",
        "instrument_type": "INFRA_BOND",
        "seniority_tier": "SENIOR_UNSECURED",
        "face_value": 100000.0,
        "coupon_rate_pct": 8.75,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-15",
        "maturity_date": "2029-02-15",
        "credit_rating": "CARE A",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.1,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10030.0,
        "ytm_pct": 8.68,
        "macaulay_duration_years": 3.1,
        "modified_duration_years": 2.85,
        "metadata": {
            "sector": "Private Sector Banking / Turnaround Franchise",
            "promoter_group": "SBI (26%) / Consortium of Financial Institutions",
            "issuer_overview": "Reconstructed private bank backed by SBI consortium with growing retail asset mix, improving CASA, and clean legacy balance sheet.",
            "collateral_type": "Unsecured senior infrastructure debt exempt from CRR/SLR requirements",
            "interest_coverage": 2.0,
            "dscr": 1.4,
            "debt_to_equity": 7.2,
            "credit_rating_rationale": "Strong institutional ownership by SBI, improved liquidity buffers, and complete write-off of legacy corporate stressed assets.",
            "the_good": [
                        "High 8.75% coupon for a senior banking instrument",
                        "Senior rank above subordinated debt",
                        "Backing of SBI as largest institutional shareholder"
            ],
            "the_bad": [
                        "Operating profitability still stabilizing post-reconstruction"
            ],
            "the_ugly": [
                        "Competitive pressure on deposit mobilization squeezing net interest margins"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE171A08090",
        "ticker": "FEDERALBNK",
        "scrip_code": "937018",
        "series": "N1",
        "instrument_name": "Federal Bank 8.35% Tier-II Subordinated Bond 2032",
        "instrument_type": "TIER2",
        "seniority_tier": "SUBORDINATED_TIER2",
        "face_value": 100000.0,
        "coupon_rate_pct": 8.35,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-20",
        "maturity_date": "2032-11-20",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10050.0,
        "ytm_pct": 8.27,
        "macaulay_duration_years": 4.8,
        "modified_duration_years": 4.43,
        "metadata": {
            "sector": "Private Commercial Banking / South-India Stronghold",
            "promoter_group": "Institutional Shareholders",
            "issuer_overview": "Old private sector bank with pan-India presence, dominant NRI remittance market share (>20%), and strong fintech lending partnerships.",
            "collateral_type": "Unsecured subordinated regulatory capital",
            "interest_coverage": 2.7,
            "dscr": 1.7,
            "debt_to_equity": 7.0,
            "credit_rating_rationale": "High asset quality metrics (Net NPA < 0.65%), strong capital buffers, and conservative management history.",
            "the_good": [
                        "Pristine underwriting with Net NPA below 0.65%",
                        "20%+ national NRI inward remittance market share",
                        "Strong AA+ rating"
            ],
            "the_bad": [
                        "Subordinated Tier-II claim rank in resolution hierarchy"
            ],
            "the_ugly": [
                        "Sharp geopolitical disruption in Middle East impacting NRI deposit inflows"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE949L08045",
        "ticker": "AUFINBANK",
        "scrip_code": "937019",
        "series": "N1",
        "instrument_name": "AU Small Finance Bank 8.65% Tier-II Subordinated Bond 2030",
        "instrument_type": "TIER2",
        "seniority_tier": "SUBORDINATED_TIER2",
        "face_value": 100000.0,
        "coupon_rate_pct": 8.65,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-03-05",
        "maturity_date": "2030-03-05",
        "credit_rating": "CRISIL AA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.0,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10040.0,
        "ytm_pct": 8.57,
        "macaulay_duration_years": 3.75,
        "modified_duration_years": 3.45,
        "metadata": {
            "sector": "Small Finance Bank / Retail Leader",
            "promoter_group": "Sanjay Agarwal / Institutional",
            "issuer_overview": "India's largest small finance bank with over \u20b91,00,000 Cr in balance sheet assets following merger with Fincare SFB, focused on vehicle and MSME loans.",
            "collateral_type": "Unsecured subordinated regulatory capital",
            "interest_coverage": 2.6,
            "dscr": 1.6,
            "debt_to_equity": 6.5,
            "credit_rating_rationale": "Consistent multi-year profitability, robust capital adequacy (CRAR > 20%), and strong retail deposit traction.",
            "the_good": [
                        "High 8.65% yield on AA-rated banking paper",
                        "Dominant market presence in semi-urban and rural vehicle finance",
                        "20%+ CRAR capital buffer"
            ],
            "the_bad": [
                        "Subordinated Tier-II maturity structure"
            ],
            "the_ugly": [
                        "Integration friction or asset quality slippages following large SFB merger"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE140A08125",
        "ticker": "PIRAMAL",
        "scrip_code": "937020",
        "series": "N1",
        "instrument_name": "Piramal Enterprises 9.25% Senior Secured NCD 2027",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.25,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-09-28",
        "maturity_date": "2027-09-28",
        "credit_rating": "CARE AA",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10070.0,
        "ytm_pct": 9.02,
        "macaulay_duration_years": 2.05,
        "modified_duration_years": 1.88,
        "metadata": {
            "sector": "Diversified Financial Services / DHFL Acquirer",
            "promoter_group": "Ajay Piramal Family",
            "issuer_overview": "Diversified retail and wholesale NBFC expanding rapidly into affordable housing finance through integrated DHFL branch network.",
            "collateral_type": "First pari-passu charge on retail housing and loan receivables",
            "interest_coverage": 2.5,
            "dscr": 1.5,
            "debt_to_equity": 2.8,
            "credit_rating_rationale": "Strong net worth (>\u20b925,000 Cr), substantial cash liquidity buffers, and declining wholesale loan concentration.",
            "the_good": [
                        "High 9.25% coupon yield",
                        "Low consolidated leverage (2.8x D/E) compared to pure NBFC peers",
                        "First charge asset cover of 1.35x"
            ],
            "the_bad": [
                        "Run-down of legacy wholesale real estate developer book"
            ],
            "the_ugly": [
                        "Prolonged developer insolvencies in major metro commercial real estate projects"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE660A08092",
        "ticker": "SUNDARMFIN",
        "scrip_code": "937021",
        "series": "N1",
        "instrument_name": "Sundaram Finance 7.95% Senior Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.95,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-22",
        "maturity_date": "2028-02-22",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.45,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10030.0,
        "ytm_pct": 7.87,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.27,
        "metadata": {
            "sector": "Commercial Vehicle Financing / TVS Group Pedigree",
            "promoter_group": "TVS / Sundaram Family",
            "issuer_overview": "Benchmark CV financing institution known for pristine underwriting and conservative risk governance over seven decades.",
            "collateral_type": "Charge on commercial vehicle loan portfolio",
            "interest_coverage": 3.8,
            "dscr": 2.0,
            "debt_to_equity": 4.8,
            "credit_rating_rationale": "CRISIL AAA rating reflects unmatched asset quality across commercial vehicle cycles and pristine reputation.",
            "the_good": [
                        "Gold-standard governance and zero historical default track record",
                        "1.45x collateral cover registered with debenture trustee",
                        "CRISIL AAA highest institutional credit rating"
            ],
            "the_bad": [
                        "Yield is tight over G-Sec benchmark"
            ],
            "the_ugly": [
                        "Extended national freight freight rate collapse impairing truck operator cash flows"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE115A08082",
        "ticker": "LICHSGFIN",
        "scrip_code": "937022",
        "series": "N1",
        "instrument_name": "LIC Housing Finance 7.75% Secured NCD 2029",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.75,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-12-10",
        "maturity_date": "2029-12-10",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10025.0,
        "ytm_pct": 7.7,
        "macaulay_duration_years": 3.2,
        "modified_duration_years": 2.97,
        "metadata": {
            "sector": "Housing Finance / Sovereign Parentage (LIC)",
            "promoter_group": "Life Insurance Corporation of India (45.24%)",
            "issuer_overview": "India's premier housing finance institution backed by sovereign-owned insurance giant LIC with loan book exceeding \u20b92,75,000 Cr.",
            "collateral_type": "First floating charge over retail residential home loans",
            "interest_coverage": 3.1,
            "dscr": 1.8,
            "debt_to_equity": 6.9,
            "credit_rating_rationale": "Strategic sovereign parentage by LIC and rock-solid residential home loan collateral backing.",
            "the_good": [
                        "Pristine LIC parentage provides institutional balance sheet safety",
                        "CRISIL AAA rating with first floating charge on home loans",
                        "High liquidity on BSE/NSE debt platforms"
            ],
            "the_bad": [
                        "Post-tax yields for 30% slab clipped by income tax"
            ],
            "the_ugly": [
                        "Systemic real estate market slump in tier-2 builder project finance loans"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE572E08125",
        "ticker": "PNBHOUSING",
        "scrip_code": "937023",
        "series": "N1",
        "instrument_name": "PNB Housing Finance 8.25% Senior Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.25,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-25",
        "maturity_date": "2028-01-25",
        "credit_rating": "CARE AA+",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10045.0,
        "ytm_pct": 8.12,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.27,
        "metadata": {
            "sector": "Housing Finance / Carlyle & PNB Backed",
            "promoter_group": "Punjab National Bank (28%) & Carlyle Group",
            "issuer_overview": "Upper layer housing finance company focused on prime individual retail home loans and affordable housing (Roshni scheme).",
            "collateral_type": "Charge on retail mortgage loan assets",
            "interest_coverage": 2.9,
            "dscr": 1.7,
            "debt_to_equity": 4.5,
            "credit_rating_rationale": "Successful rights issue turnaround, declining wholesale book, and expanding high-yielding affordable retail loans.",
            "the_good": [
                        "Strong 8.25% coupon yield offering +110 bps spread",
                        "Backed by Carlyle Group and public sector giant PNB",
                        "1.35x asset cover registered with Catalyst Trusteeship"
            ],
            "the_bad": [
                        "Moderate historical wholesale developer NPA provisioning"
            ],
            "the_ugly": [
                        "Sharp rise in residential mortgage defaults in tier-2/3 cities"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE151A08092",
        "ticker": "TATACOMM",
        "scrip_code": "937024",
        "series": "N1",
        "instrument_name": "Tata Communications 7.85% Senior Secured NCD 2028",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 7.85,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-08",
        "maturity_date": "2028-11-08",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.5,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10035.0,
        "ytm_pct": 7.76,
        "macaulay_duration_years": 2.5,
        "modified_duration_years": 2.32,
        "metadata": {
            "sector": "Global Subsea Telecom & Digital Infrastructure",
            "promoter_group": "Tata Sons & Government of India",
            "issuer_overview": "Global digital ecosystem enabler powering internet backbones and subsea cables carrying ~30% of global internet routes.",
            "collateral_type": "Charge on subsea cable landing stations and enterprise data centers",
            "interest_coverage": 6.5,
            "dscr": 3.0,
            "debt_to_equity": 1.1,
            "credit_rating_rationale": "CRISIL AAA rating supported by indispensable global subsea cable moat, Tata brand parentage, and robust free cash flow.",
            "the_good": [
                        "Global monopoly subsea data pipeline moat",
                        "Conservative 1.1x debt-to-equity ratio",
                        "High ICR of 6.5x"
            ],
            "the_bad": [
                        "Relatively narrow credit spread over sovereign bonds"
            ],
            "the_ugly": [
                        "Geopolitical conflict damaging critical subsea fiber optic cables in Red Sea or Malacca Strait"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE530B08125",
        "ticker": "IIFL",
        "scrip_code": "937025",
        "series": "N1",
        "instrument_name": "IIFL Finance 8.95% Senior Secured NCD 2027",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.95,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-08-14",
        "maturity_date": "2027-08-14",
        "credit_rating": "CRISIL AA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10050.0,
        "ytm_pct": 8.78,
        "macaulay_duration_years": 1.95,
        "modified_duration_years": 1.79,
        "metadata": {
            "sector": "Retail Diversified NBFC / Gold & Home Loans",
            "promoter_group": "Nirmal Jain & Fairfax India",
            "issuer_overview": "Diversified retail lender providing gold loans, home loans, microfinance, and business loans with over \u20b975,000 Cr in AUM.",
            "collateral_type": "First pari-passu charge on standard loan receivables",
            "interest_coverage": 2.8,
            "dscr": 1.6,
            "debt_to_equity": 3.6,
            "credit_rating_rationale": "High retail portfolio granularity, strong liquidity backing from Fairfax India, and rapid post-regulatory normalization.",
            "the_good": [
                        "Attractive 8.95% coupon yield",
                        "Fairfax India institutional backing",
                        "1.30x asset cover registered with IDBI Trusteeship"
            ],
            "the_bad": [
                        "Regulatory sensitivity regarding gold loan cash disbursement limits"
            ],
            "the_ugly": [
                        "Sudden RBI regulatory sanctions on specific lending business verticals"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE364U08012",
        "ticker": "ADANIGREEN",
        "scrip_code": "938006",
        "series": "N1",
        "instrument_name": "Adani Green Energy 8.85% Secured Green Bond 2029",
        "instrument_type": "GREEN_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.85,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-03-10",
        "maturity_date": "2029-03-10",
        "credit_rating": "CRISIL AA+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10090.0,
        "ytm_pct": 8.62,
        "macaulay_duration_years": 2.9,
        "modified_duration_years": 2.67,
        "metadata": {
            "sector": "Renewable Power / World's Largest Solar Park Operator",
            "promoter_group": "Adani Group & TotalEnergies",
            "issuer_overview": "World-class renewable utility operating the 30 GW Khavda hybrid renewable park in Gujarat with 11+ GW operational portfolio.",
            "collateral_type": "First charge over solar power generation assets and assigned SECI receivables",
            "interest_coverage": 3.1,
            "dscr": 1.6,
            "debt_to_equity": 3.2,
            "credit_rating_rationale": "Long-term 25-year sovereign-backed PPAs signed with central entity Solar Energy Corporation of India (SECI).",
            "the_good": [
                        "High 8.85% coupon yield",
                        "25-year sovereign-backed SECI PPAs",
                        "Strong strategic partnership with TotalEnergies"
            ],
            "the_bad": [
                        "High debt leverage typical of utility-scale capital expenditures"
            ],
            "the_ugly": [
                        "Systemic grid curtailment during peak afternoon solar generation hours"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE857Q08015",
        "ticker": "TATACLEAN",
        "scrip_code": "938007",
        "series": "N1",
        "instrument_name": "Tata Cleantech Capital 8.25% Green Infrastructure Bond 2028",
        "instrument_type": "GREEN_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.25,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-10-18",
        "maturity_date": "2028-10-18",
        "credit_rating": "CRISIL AAA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10040.0,
        "ytm_pct": 8.14,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.27,
        "metadata": {
            "sector": "Green Infrastructure Financing / Tata & IFC Joint Venture",
            "promoter_group": "Tata Capital (51%) & IFC (49%)",
            "issuer_overview": "Dedicated green finance company funding solar, wind, e-mobility, water management, and energy efficiency projects across India.",
            "collateral_type": "Charge on green infrastructure loan receivables",
            "interest_coverage": 4.1,
            "dscr": 2.2,
            "debt_to_equity": 4.2,
            "credit_rating_rationale": "Pristine AAA credit rating underpinned by Tata Sons ownership and International Finance Corporation (IFC) partnership.",
            "the_good": [
                        "Pristine Tata parentage and IFC co-ownership",
                        "CRISIL AAA highest institutional credit rating",
                        "100% certified Green Bond compliance"
            ],
            "the_bad": [
                        "Yield premium over G-Sec is modest (~85 bps)"
            ],
            "the_ugly": [
                        "Systemic borrower payment defaults in solar rooftop commercial segment"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE622W08012",
        "ticker": "ACMESOLAR",
        "scrip_code": "938008",
        "series": "N1",
        "instrument_name": "ACME Solar Holdings 9.35% Secured Solar Green Bond 2028",
        "instrument_type": "GREEN_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.35,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-28",
        "maturity_date": "2028-02-28",
        "credit_rating": "CRISIL AA-",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10075.0,
        "ytm_pct": 9.12,
        "macaulay_duration_years": 2.4,
        "modified_duration_years": 2.2,
        "metadata": {
            "sector": "Solar IPP & Green Hydrogen Utility",
            "promoter_group": "Manoj Kumar Upadhyay / ACME Group",
            "issuer_overview": "Pioneering solar IPP with over 2.7 GW of operational capacity and integrated green ammonia export projects in Oman and India.",
            "collateral_type": "First fixed charge on Rajasthan and Andhra solar power plants",
            "interest_coverage": 2.8,
            "dscr": 1.5,
            "debt_to_equity": 3.4,
            "credit_rating_rationale": "High proportion of central sovereign-backed off-takers (SECI, NTPC) ensuring uninterrupted cash flows.",
            "the_good": [
                        "High 9.35% coupon yield offering substantial alpha",
                        "SECI and central counterparty off-take contracts",
                        "1.30x asset cover registered with Catalyst Trusteeship"
            ],
            "the_bad": [
                        "High debt leverage typical of renewable project developers"
            ],
            "the_ugly": [
                        "Severe delays in state transmission utility sub-station line connectivity"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE042W08015",
        "ticker": "AVAADA",
        "scrip_code": "938009",
        "series": "N1",
        "instrument_name": "Avaada Energy 9.15% Secured Green Bond 2027",
        "instrument_type": "GREEN_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.15,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-09-05",
        "maturity_date": "2027-09-05",
        "credit_rating": "CRISIL AA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10060.0,
        "ytm_pct": 8.95,
        "macaulay_duration_years": 1.95,
        "modified_duration_years": 1.79,
        "metadata": {
            "sector": "Renewable Power Generation / PTT Group Co-Investment",
            "promoter_group": "Vineet Mittal & PTT Group (Thailand)",
            "issuer_overview": "Leading clean energy platform operating utility-scale solar and wind projects across 11 Indian states with over 4 GW capacity.",
            "collateral_type": "Charge on operational solar park assets and escrow bank accounts",
            "interest_coverage": 3.0,
            "dscr": 1.6,
            "debt_to_equity": 2.9,
            "credit_rating_rationale": "Equity capitalization from Thailand's national energy major PTT Group and long-term contracted PPAs.",
            "the_good": [
                        "High 9.15% coupon yield",
                        "Global sovereign backing via PTT Group of Thailand",
                        "First charge asset cover of 1.35x"
            ],
            "the_bad": [
                        "State electricity distribution board payment cycle delays in older projects"
            ],
            "the_ugly": [
                        "Sudden unilateral state tariff renegotiation attempts"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE110V08012",
        "ticker": "STERLITE",
        "scrip_code": "938010",
        "series": "N1",
        "instrument_name": "Sterlite Power Transmission 9.45% Secured Infrastructure NCD 2028",
        "instrument_type": "INFRA_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.45,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-20",
        "maturity_date": "2028-01-20",
        "credit_rating": "CARE AA-",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10080.0,
        "ytm_pct": 9.21,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.24,
        "metadata": {
            "sector": "Power Transmission Infrastructure & Grid EPC",
            "promoter_group": "Pratik Agarwal / Vedanta Family",
            "issuer_overview": "Leading private power transmission infrastructure developer operating high-voltage inter-state transmission projects across India and Brazil.",
            "collateral_type": "First charge over transmission lines and sub-station concessions",
            "interest_coverage": 2.6,
            "dscr": 1.5,
            "debt_to_equity": 3.8,
            "credit_rating_rationale": "High operating cash flow from Point-of-Connection (PoC) inter-state transmission pooling mechanism.",
            "the_good": [
                        "High 9.45% coupon yield",
                        "PoC central billing pool insulates from individual state discom defaults",
                        "1.30x asset cover with IDBI Trusteeship"
            ],
            "the_bad": [
                        "High debt leverage during active construction phase"
            ],
            "the_ugly": [
                        "Extreme right-of-way (RoW) or forest clearance legal blockades delaying transmission corridor energization"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE023V08015",
        "ticker": "GMRINFRA",
        "scrip_code": "938011",
        "series": "N1",
        "instrument_name": "GMR Goa International Airport 9.20% Secured Concession Bond 2030",
        "instrument_type": "INFRA_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.2,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-15",
        "maturity_date": "2030-11-15",
        "credit_rating": "CRISIL AA-",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10070.0,
        "ytm_pct": 9.04,
        "macaulay_duration_years": 3.45,
        "modified_duration_years": 3.16,
        "metadata": {
            "sector": "Airport Concession Infrastructure / Manohar International Airport (MOPA)",
            "promoter_group": "GMR Airports Infrastructure & Groupe ADP",
            "issuer_overview": "Concessionaire of Goa's new greenfield Manohar International Airport (MOPA) operating under a 40-year concession with rapid passenger growth.",
            "collateral_type": "Charge on aeronautical fee escrows, duty-free retail, and airport land leases",
            "interest_coverage": 2.7,
            "dscr": 1.6,
            "debt_to_equity": 2.6,
            "credit_rating_rationale": "High aeronautical revenue visibility under AERA tariff orders and surging international tourism passenger traffic.",
            "the_good": [
                        "40-year monopoly gateway airport concession in premier tourist destination",
                        "High 9.20% coupon",
                        "Groupe ADP global airport operator backing"
            ],
            "the_bad": [
                        "Competition from existing Dabolim military airport"
            ],
            "the_ugly": [
                        "Severe tourism collapse due to macroeconomic or aviation geopolitical shocks"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE821I08012",
        "ticker": "IRB",
        "scrip_code": "938012",
        "series": "N1",
        "instrument_name": "IRB Infrastructure Developers 8.95% Secured Toll Road NCD 2028",
        "instrument_type": "INFRA_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.95,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-02-18",
        "maturity_date": "2028-02-18",
        "credit_rating": "CARE AA",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10050.0,
        "ytm_pct": 8.8,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.25,
        "metadata": {
            "sector": "Highways & Expressways / Build-Operate-Transfer (BOT)",
            "promoter_group": "Virendra Mhaiskar & Cintra (Ferrovial)",
            "issuer_overview": "India's premier highway developer operating the Mumbai-Pune Expressway and Golden Quadrilateral toll road assets with 14,000+ lane km.",
            "collateral_type": "First pari-passu charge on BOT highway toll receipts and designated escrow accounts",
            "interest_coverage": 3.4,
            "dscr": 1.8,
            "debt_to_equity": 2.1,
            "credit_rating_rationale": "High toll growth across economic freight corridors, strong institutional backing from GIC and Ferrovial, and healthy cash cover.",
            "the_good": [
                        "Toll revenues indexed annually to WPI inflation",
                        "Strong foreign institutional partners (Ferrovial, GIC)",
                        "High 8.95% coupon with 1.40x asset cover"
            ],
            "the_bad": [
                        "Toll collection traffic risk during monsoon road repairs"
            ],
            "the_ugly": [
                        "Government policy changes mandating toll waivers or alternative toll-free expressway construction"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE981T08012",
        "ticker": "MEIL",
        "scrip_code": "938013",
        "series": "N1",
        "instrument_name": "Megha Engineering 9.10% Secured Infrastructure NCD 2028",
        "instrument_type": "INFRA_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.1,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-12-22",
        "maturity_date": "2028-12-22",
        "credit_rating": "CRISIL AA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10065.0,
        "ytm_pct": 8.91,
        "macaulay_duration_years": 2.5,
        "modified_duration_years": 2.3,
        "metadata": {
            "sector": "Water & Irrigation Infrastructure / EPC Giant",
            "promoter_group": "P. P. Reddy & P. V. Krishna Reddy",
            "issuer_overview": "India's top infrastructure conglomerate executing the Kaleshwaram lift irrigation project, strategic highway tunnels (Zojila), and electric buses (Olectra).",
            "collateral_type": "Charge on heavy earthmoving equipment and government department project receivables",
            "interest_coverage": 3.8,
            "dscr": 2.0,
            "debt_to_equity": 0.85,
            "credit_rating_rationale": "Massive unexecuted order book (>\u20b91,50,000 Cr), conservative leverage (0.85x D/E), and robust operating cash flows.",
            "the_good": [
                        "Order book exceeding \u20b91.5 lakh crore provides multi-year revenue visibility",
                        "Low 0.85x balance sheet leverage",
                        "Attractive 9.10% coupon yield"
            ],
            "the_bad": [
                        "High working capital intensity of state government EPC contracts"
            ],
            "the_ugly": [
                        "Extended payment freezes by cash-strapped state irrigation departments"
            ],
            "collated_sources": [
                        "NSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE428R08012",
        "ticker": "GREENKO",
        "scrip_code": "938014",
        "series": "N1",
        "instrument_name": "Greenko Solar Power 8.90% Secured Green Bond 2028",
        "instrument_type": "GREEN_BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.9,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-28",
        "maturity_date": "2028-01-28",
        "credit_rating": "CRISIL AA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10055.0,
        "ytm_pct": 8.74,
        "macaulay_duration_years": 2.45,
        "modified_duration_years": 2.25,
        "metadata": {
            "sector": "Renewable Storage & Pumped Hydro Utility",
            "promoter_group": "Anil Chalamalasetty / GIC Sovereign Wealth / ADIA",
            "issuer_overview": "Pioneering clean energy giant developing world's largest pumped hydro storage project in Pinnapuram, Andhra Pradesh, with 7.5 GW operational portfolio.",
            "collateral_type": "Charge on solar arrays and central utility-scale pumped storage hydro assets",
            "interest_coverage": 3.3,
            "dscr": 1.7,
            "debt_to_equity": 3.1,
            "credit_rating_rationale": "Majority sovereign wealth ownership (GIC Singapore & Abu Dhabi Investment Authority) and innovative round-the-clock (RTC) power contracts.",
            "the_good": [
                        "Pristine sovereign wealth fund ownership (GIC & ADIA)",
                        "Pioneering round-the-clock renewable baseload power moat",
                        "High 8.90% coupon"
            ],
            "the_bad": [
                        "High capital intensity of long-gestation pumped hydro construction"
            ],
            "the_ugly": [
                        "Catastrophic geological faulting or flooding during underground hydro cavern excavation"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE066P08012",
        "ticker": "INOXWIND",
        "scrip_code": "938015",
        "series": "N1",
        "instrument_name": "Inox Wind Limited 9.50% Secured Wind Energy NCD 2027",
        "instrument_type": "BOND",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.5,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-10",
        "maturity_date": "2027-11-10",
        "credit_rating": "CRISIL A+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10070.0,
        "ytm_pct": 9.28,
        "macaulay_duration_years": 1.9,
        "modified_duration_years": 1.74,
        "metadata": {
            "sector": "Wind Turbine Manufacturing & Turnkey Wind Energy EPC",
            "promoter_group": "Inox GFL Group (Devansh Jain)",
            "issuer_overview": "Integrated wind energy solution provider manufacturing advanced 3.3 MW wind turbines with multi-gigawatt order book and turnkey project execution.",
            "collateral_type": "Charge on blade manufacturing units in Gujarat and Madhya Pradesh",
            "interest_coverage": 2.8,
            "dscr": 1.6,
            "debt_to_equity": 0.65,
            "credit_rating_rationale": "Substantial promoter deleveraging, multi-gigawatt order book, and technological upgrade to high-yield 3.3 MW turbines.",
            "the_good": [
                        "High 9.50% coupon yield offering significant fixed-income carry",
                        "Deleveraged balance sheet with 0.65x D/E",
                        "Multi-year wind order pipeline backed by NTPC and private IPPs"
            ],
            "the_bad": [
                        "Cyclical order execution dependent on state land and evacuation infrastructure"
            ],
            "the_ugly": [
                        "Sudden reversal in national wind energy auction bidding frameworks"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE00SD07046",
        "ticker": "WINT_INVOICEX_2",
        "scrip_code": "939004",
        "series": "SDI-4",
        "instrument_name": "Wint InvoiceX Aditya Birla Anchor Pool SDI",
        "instrument_type": "SDI",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 10.65,
        "coupon_frequency": "MONTHLY",
        "issue_date": "2024-03-15",
        "maturity_date": "2025-11-15",
        "credit_rating": "CRISIL A(SO)",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.25,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": True,
        "originator": "KredX / Wint SPV Trust",
        "fldg_pct": 10.0,
        "last_traded_price": 10000.0,
        "ytm_pct": 10.65,
        "macaulay_duration_years": 0.8,
        "modified_duration_years": 0.72,
        "metadata": {
            "sector": "Supply Chain Trade Finance / SEBI SDI Framework",
            "promoter_group": "Bankruptcy-Remote Trust / Wint Wealth OBPP",
            "issuer_overview": "Securitised Debt Instrument backed by anchor-accepted enterprise trade invoices from Aditya Birla group companies (UltraTech, Grasim, Hindalco).",
            "collateral_type": "First charge over accepted corporate invoices and escrow cash reserve",
            "interest_coverage": 4.6,
            "dscr": 2.3,
            "debt_to_equity": 0.0,
            "credit_rating_rationale": "High-quality conglomerate corporate anchors, bankruptcy-remote trust isolation, and 10% cash FLDG buffer.",
            "the_good": [
                        "High 10.65% YTM paid out monthly",
                        "10% cash FLDG reserve protects against vendor disputes",
                        "Short 0.80-year duration limits interest rate exposure"
            ],
            "the_bad": [
                        "Modest secondary market trading; intended for hold-to-maturity"
            ],
            "the_ugly": [
                        "Systemic commercial billing dispute between vendors and anchor buyers"
            ],
            "collated_sources": [
                        "Wint Wealth",
                        "BSE Debt"
            ]
        }
    },
    {
        "isin": "INE00SD07053",
        "ticker": "WINT_POOLX_3",
        "scrip_code": "939005",
        "series": "SDI-5",
        "instrument_name": "Wint PoolX MSME Secured Loan Pool SDI",
        "instrument_type": "SDI",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 11.1,
        "coupon_frequency": "MONTHLY",
        "issue_date": "2024-02-20",
        "maturity_date": "2026-02-20",
        "credit_rating": "ICRA A+(SO)",
        "credit_rating_agency": "ICRA",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": True,
        "originator": "Vivriti Capital / Wint Trust",
        "fldg_pct": 12.0,
        "last_traded_price": 10010.0,
        "ytm_pct": 11.02,
        "macaulay_duration_years": 1.1,
        "modified_duration_years": 0.99,
        "metadata": {
            "sector": "Securitized MSME Equipment & Business Loans",
            "promoter_group": "Trustee Administered / Wint Wealth",
            "issuer_overview": "Pass-through certificates issued by an SPV trust holding a diversified portfolio of 850+ secured MSME business loans with average ticket size of \u20b915 lakhs.",
            "collateral_type": "Hypothecation of industrial plant, machinery, and assigned borrower EMIs",
            "interest_coverage": 3.7,
            "dscr": 2.0,
            "debt_to_equity": 0.0,
            "credit_rating_rationale": "High 12% cash FLDG buffer deposited in escrow and granular geographic diversification across 8 states.",
            "the_good": [
                        "High 11.10% monthly cash flow yield",
                        "12% junior first-loss protection absorbs MSME defaults",
                        "Granular portfolio across 850+ independent business borrowers"
            ],
            "the_bad": [
                        "Semi-urban MSME borrower credit vulnerability during economic slowdowns"
            ],
            "the_ugly": [
                        "Widespread regional flooding or economic disruption paralyzing borrower workshops"
            ],
            "collated_sources": [
                        "Wint Wealth",
                        "BSE Debt"
            ]
        }
    },
    {
        "isin": "INE00SD07061",
        "ticker": "GRIP_SECURX_2",
        "scrip_code": "939006",
        "series": "SDI-6",
        "instrument_name": "Grip SecurX Rooftop Solar Lease SDI",
        "instrument_type": "SDI",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 11.4,
        "coupon_frequency": "MONTHLY",
        "issue_date": "2024-01-25",
        "maturity_date": "2026-07-25",
        "credit_rating": "CRISIL A(SO)",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": True,
        "originator": "Grip Invest / CleanMax Solar Trust",
        "fldg_pct": 14.0,
        "last_traded_price": 10000.0,
        "ytm_pct": 11.4,
        "macaulay_duration_years": 1.25,
        "modified_duration_years": 1.12,
        "metadata": {
            "sector": "Renewable Asset Lease Securitisation / Green SDI",
            "promoter_group": "SEBI SDI SPV / Grip Invest",
            "issuer_overview": "Securitized debt instrument backed by contracted lease payments on commercial rooftop solar installations for Tier-1 corporate commercial lessees.",
            "collateral_type": "First charge on rooftop solar hardware and assigned 15-year lease rental escrow",
            "interest_coverage": 3.5,
            "dscr": 1.9,
            "debt_to_equity": 0.0,
            "credit_rating_rationale": "High counterparty credit quality of commercial lessees, hypothecated solar equipment, and 14% cash credit enhancement.",
            "the_good": [
                        "High 11.40% annualized yield paid monthly",
                        "14% cash FLDG buffer",
                        "Green SDI asset backed by operational clean power generation"
            ],
            "the_bad": [
                        "Equipment repossession logistics if a commercial factory lessee relocates"
            ],
            "the_ugly": [
                        "Simultaneous commercial insolvency of multiple anchor factory lessees"
            ],
            "collated_sources": [
                        "Grip Invest",
                        "NSE Debt"
            ]
        }
    },
    {
        "isin": "INE00SD07079",
        "ticker": "GRIP_AUTOX_3",
        "scrip_code": "939007",
        "series": "SDI-7",
        "instrument_name": "Grip AutoX Commercial Logistics Vehicle SDI",
        "instrument_type": "SDI",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 11.75,
        "coupon_frequency": "MONTHLY",
        "issue_date": "2024-03-05",
        "maturity_date": "2026-09-05",
        "credit_rating": "ICRA A(SO)",
        "credit_rating_agency": "ICRA",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": True,
        "originator": "Grip Invest / Everest Fleet Trust",
        "fldg_pct": 15.0,
        "last_traded_price": 10000.0,
        "ytm_pct": 11.75,
        "macaulay_duration_years": 1.3,
        "modified_duration_years": 1.16,
        "metadata": {
            "sector": "Commercial Fleet Securitised Rentals",
            "promoter_group": "Independent Debenture Trustee / Grip Invest",
            "issuer_overview": "Securitised pass-through certificates backed by commercial CNG and EV fleet vehicles operating on ride-hailing networks (Uber/Ola).",
            "collateral_type": "Hypothecation of registered commercial vehicles and daily ride fare escrows",
            "interest_coverage": 3.4,
            "dscr": 1.8,
            "debt_to_equity": 0.0,
            "credit_rating_rationale": "High 15% cash FLDG buffer deposited in escrow, vehicle GPS tracking, and daily escrow sweep of ride earnings.",
            "the_good": [
                        "High 11.75% YTM for institutional-grade yield",
                        "15% cash FLDG reserve",
                        "Daily revenue sweep into trustee escrow account"
            ],
            "the_bad": [
                        "Fleet vehicle mileage depreciation over 3-year operating lease"
            ],
            "the_ugly": [
                        "Prolonged ride-hailing driver strikes or platform app bans"
            ],
            "collated_sources": [
                        "Grip Invest",
                        "NSE Debt"
            ]
        }
    },
    {
        "isin": "INE00SD07087",
        "ticker": "JIRAF_INVOICEX_1",
        "scrip_code": "939008",
        "series": "SDI-8",
        "instrument_name": "Jiraaf Anchor Invoice Discounting SDI Series I",
        "instrument_type": "SDI",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 10.85,
        "coupon_frequency": "MONTHLY",
        "issue_date": "2024-02-10",
        "maturity_date": "2025-10-10",
        "credit_rating": "CRISIL A(SO)",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.25,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": True,
        "originator": "Jiraaf / AI Growth SPV Trust",
        "fldg_pct": 10.0,
        "last_traded_price": 10000.0,
        "ytm_pct": 10.85,
        "macaulay_duration_years": 0.75,
        "modified_duration_years": 0.68,
        "metadata": {
            "sector": "Corporate Trade Receivables Securitisation",
            "promoter_group": "SEBI Regulated Trust / Jiraaf Platform",
            "issuer_overview": "SEBI-regulated SDI backed by verified trade receivables from blue-chip consumer goods and electronics companies payable within 180 days.",
            "collateral_type": "Irrevocable charge on verified trade invoices and dedicated escrow collections",
            "interest_coverage": 4.2,
            "dscr": 2.1,
            "debt_to_equity": 0.0,
            "credit_rating_rationale": "High credit standing of corporate invoice acceptors, short working capital cycle, and 10% cash credit enhancement.",
            "the_good": [
                        "10.85% monthly yield",
                        "Ultra-short 0.75-year duration",
                        "10% cash FLDG buffer"
            ],
            "the_bad": [
                        "Low secondary trading liquidity"
            ],
            "the_ugly": [
                        "Invoice fraud or duplicate invoice financing across unmonitored supplier accounts"
            ],
            "collated_sources": [
                        "Jiraaf",
                        "BSE Debt"
            ]
        }
    },
    {
        "isin": "INE00SD07095",
        "ticker": "ALT_SDI_REALTY_1",
        "scrip_code": "939009",
        "series": "SDI-9",
        "instrument_name": "AltGraaf LRD Commercial Real Estate Rental SDI",
        "instrument_type": "SDI",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 11.5,
        "coupon_frequency": "MONTHLY",
        "issue_date": "2024-01-15",
        "maturity_date": "2026-07-15",
        "credit_rating": "CARE A+(SO)",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.4,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": True,
        "originator": "AltGraaf / Brickwork Realty Trust",
        "fldg_pct": 12.0,
        "last_traded_price": 10020.0,
        "ytm_pct": 11.38,
        "macaulay_duration_years": 1.35,
        "modified_duration_years": 1.21,
        "metadata": {
            "sector": "Lease Rental Discounting (LRD) Securitisation",
            "promoter_group": "Trustee Administered / AltGraaf Platform",
            "issuer_overview": "Securitised Debt Instrument backed by long-term Grade-A IT park office leases occupied by Fortune 500 multinationals with 9-year lock-in terms.",
            "collateral_type": "Registered mortgage on office units and assigned escrow of tenant lease rentals",
            "interest_coverage": 3.8,
            "dscr": 2.0,
            "debt_to_equity": 0.0,
            "credit_rating_rationale": "High tenant stickiness, institutional Grade-A property location, and 12% cash FLDG reserve.",
            "the_good": [
                        "High 11.50% YTM backed by prime commercial office real estate",
                        "12% cash FLDG buffer",
                        "Monthly rental distributions directly into bank accounts"
            ],
            "the_bad": [
                        "Early lease surrender risk by IT corporate tenants"
            ],
            "the_ugly": [
                        "Structural shift to permanent remote work causing office park vacancy spikes"
            ],
            "collated_sources": [
                        "AltGraaf",
                        "BSE Debt"
            ]
        }
    },
    {
        "isin": "INE00SD07103",
        "ticker": "CRED_SECURX_1",
        "scrip_code": "939010",
        "series": "SDI-10",
        "instrument_name": "CRED Garage Automobile Hypothecated SDI",
        "instrument_type": "SDI",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 10.95,
        "coupon_frequency": "MONTHLY",
        "issue_date": "2024-03-20",
        "maturity_date": "2026-03-20",
        "credit_rating": "CRISIL A+(SO)",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "NSE",
        "is_sdi": True,
        "originator": "CRED / Dreamplug SPV Trust",
        "fldg_pct": 12.0,
        "last_traded_price": 10000.0,
        "ytm_pct": 10.95,
        "macaulay_duration_years": 1.15,
        "modified_duration_years": 1.04,
        "metadata": {
            "sector": "Securitised Automobile Maintenance & Asset Loans",
            "promoter_group": "Kunal Shah / CRED (Dreamplug Technologies)",
            "issuer_overview": "Pass-through securitised debt backed by auto loans to high-credit-score CRED members (credit score 750+) with average LTV of 52%.",
            "collateral_type": "First hypothecation on borrower four-wheelers and auto-debit NACH mandates",
            "interest_coverage": 4.8,
            "dscr": 2.4,
            "debt_to_equity": 0.0,
            "credit_rating_rationale": "High-prime borrower demographic (750+ CIBIL score), 12% cash FLDG buffer, and automated e-NACH collection.",
            "the_good": [
                        "High-prime borrower cohort with historically low default rates (<0.8%)",
                        "High 10.95% annualized yield paid monthly",
                        "12% cash FLDG guarantee reserve"
            ],
            "the_bad": [
                        "Fintech collection platform dependency"
            ],
            "the_ugly": [
                        "Systemic white-collar tech layoffs triggering unexpected personal loan defaults"
            ],
            "collated_sources": [
                        "CRED",
                        "NSE Debt"
            ]
        }
    },
    {
        "isin": "INE945W07012",
        "ticker": "INCRED_RETAIL_1",
        "scrip_code": "939011",
        "series": "N1",
        "instrument_name": "InCred Financial 9.85% Retail ₹10,000 NCD 2026",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.85,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-10-25",
        "maturity_date": "2026-10-25",
        "credit_rating": "CRISIL A+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.3,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10050.0,
        "ytm_pct": 9.64,
        "macaulay_duration_years": 1.55,
        "modified_duration_years": 1.41,
        "metadata": {
            "sector": "Retail NBFC / SEBI \u20b910,000 Public Issue",
            "promoter_group": "Bhupinder Singh & KKR",
            "issuer_overview": "Publicly issued retail NCD under the SEBI democratized framework, financing education loans, MSMEs, and consumer finance.",
            "collateral_type": "First pari-passu charge on standard education and business loan assets",
            "interest_coverage": 2.7,
            "dscr": 1.6,
            "debt_to_equity": 2.8,
            "credit_rating_rationale": "Strong capitalization (CRAR > 30%), marquee institutional backers (KKR, TRS), and seasoned retail loan portfolios.",
            "the_good": [
                        "Democratized \u20b910,000 face value with high 9.85% coupon",
                        "Enormous 30%+ capital adequacy ratio",
                        "Short 2-year duration limits interest rate volatility"
            ],
            "the_bad": [
                        "CRISIL A+ rating reflects moderate credit spread"
            ],
            "the_ugly": [
                        "Unsecured retail borrower stress during national macroeconomic tightening"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE338I07015",
        "ticker": "MOTILAL_NCD_1",
        "scrip_code": "939012",
        "series": "N1",
        "instrument_name": "Motilal Oswal Financial 8.75% Retail ₹10,000 NCD 2027",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 8.75,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-04-10",
        "maturity_date": "2027-04-10",
        "credit_rating": "CRISIL AA",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.35,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10040.0,
        "ytm_pct": 8.58,
        "macaulay_duration_years": 1.85,
        "modified_duration_years": 1.7,
        "metadata": {
            "sector": "Financial Services & Wealth Management / Retail \u20b910,000 Issue",
            "promoter_group": "Motilal Oswal & Raamdeo Agrawal",
            "issuer_overview": "Retail public NCD issued by premier wealth management, asset management, and financial advisory conglomerate managing \u20b91,50,000+ Cr AUM.",
            "collateral_type": "Charge on wealth advisory receivables and capital market loan book",
            "interest_coverage": 4.5,
            "dscr": 2.2,
            "debt_to_equity": 1.2,
            "credit_rating_rationale": "High franchise brand equity, strong treasury book, and robust debt service coverage.",
            "the_good": [
                        "Pristine brand in Indian capital markets and wealth advisory",
                        "Conservative 1.2x debt-to-equity ratio",
                        "1.35x collateral cover registered with Catalyst Trusteeship"
            ],
            "the_bad": [
                        "Revenues correlate with equity capital market trading volumes"
            ],
            "the_ugly": [
                        "Protracted multi-year equity bear market depressing broking and asset management fees"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE532F07025",
        "ticker": "EDELWEISS_NCD_1",
        "scrip_code": "939013",
        "series": "N1",
        "instrument_name": "Edelweiss Financial Services 9.95% Retail ₹10,000 NCD 2026",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.95,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-11-28",
        "maturity_date": "2026-11-28",
        "credit_rating": "CRISIL AA-",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.25,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10080.0,
        "ytm_pct": 9.62,
        "macaulay_duration_years": 1.5,
        "modified_duration_years": 1.37,
        "metadata": {
            "sector": "Diversified Financial Services / Retail Public NCD",
            "promoter_group": "Rashesh Shah & Venkat Ramaswamy",
            "issuer_overview": "Public retail issue by Edelweiss Group with high coupon yields tailored for individual income accumulators.",
            "collateral_type": "Charge on financial assets and group holding investments",
            "interest_coverage": 2.5,
            "dscr": 1.5,
            "debt_to_equity": 3.2,
            "credit_rating_rationale": "Diversified fee-based businesses (mutual funds, ARC, alternatives) balancing NBFC borrowing.",
            "the_good": [
                        "High 9.95% coupon yield offering superior income",
                        "Retail \u20b910,000 accessible denomination",
                        "1.25x asset cover"
            ],
            "the_bad": [
                        "Higher wholesale legacy debt exposure"
            ],
            "the_ugly": [
                        "Credit spread widening during capital market liquidity squeezes"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {
        "isin": "INE046W07018",
        "ticker": "MUTHOOT_MICRO_1",
        "scrip_code": "939014",
        "series": "N1",
        "instrument_name": "Muthoot Microfin 9.60% Retail ₹10,000 NCD 2026",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 9.6,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2024-01-30",
        "maturity_date": "2026-07-30",
        "credit_rating": "CRISIL A+",
        "credit_rating_agency": "CRISIL",
        "asset_cover_ratio": 1.25,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10030.0,
        "ytm_pct": 9.42,
        "macaulay_duration_years": 1.35,
        "modified_duration_years": 1.23,
        "metadata": {
            "sector": "Microfinance Institution / Joint Liability Group (JLG)",
            "promoter_group": "Muthoot Pappachan Group (Thomas John Muthoot)",
            "issuer_overview": "Leading NBFC-MFI providing micro-loans to women entrepreneurs in rural and semi-urban India with loan book exceeding \u20b912,000 Cr.",
            "collateral_type": "First pari-passu charge on qualifying microfinance loan portfolio",
            "interest_coverage": 2.8,
            "dscr": 1.6,
            "debt_to_equity": 3.4,
            "credit_rating_rationale": "Strong brand parentage of Muthoot Blue (MPG) and diversified rural presence across 19 states.",
            "the_good": [
                        "High 9.60% coupon yield",
                        "Muthoot Pappachan Group parentage",
                        "Short 1.5-year duration"
            ],
            "the_bad": [
                        "Unsecured nature of underlying microfinance borrower portfolio"
            ],
            "the_ugly": [
                        "State farm loan waiver rumors or regional political unrest disrupting rural JLG collections"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "IndiaBonds"
            ]
        }
    },
    {
        "isin": "INE234Y07015",
        "ticker": "KANAKADURGA_1",
        "scrip_code": "939015",
        "series": "N1",
        "instrument_name": "Kanakadurga Finance 10.25% Retail ₹10,000 NCD 2026",
        "instrument_type": "NCD",
        "seniority_tier": "SENIOR_SECURED",
        "face_value": 10000.0,
        "coupon_rate_pct": 10.25,
        "coupon_frequency": "ANNUAL",
        "issue_date": "2023-12-15",
        "maturity_date": "2026-12-15",
        "credit_rating": "CARE BBB+",
        "credit_rating_agency": "CARE",
        "asset_cover_ratio": 1.2,
        "is_listed": True,
        "exchange": "BSE",
        "is_sdi": False,
        "originator": None,
        "fldg_pct": 0.0,
        "last_traded_price": 10020.0,
        "ytm_pct": 10.15,
        "macaulay_duration_years": 1.65,
        "modified_duration_years": 1.5,
        "metadata": {
            "sector": "Auto & Commercial Vehicle NBFC / South India",
            "promoter_group": "S. Lakshmi Narayana Family",
            "issuer_overview": "Regional asset financing NBFC specializing in three-wheeler, commercial vehicle, and gold loans across Andhra Pradesh, Telangana, and Karnataka.",
            "collateral_type": "Hypothecation of auto loan receivables",
            "interest_coverage": 2.2,
            "dscr": 1.4,
            "debt_to_equity": 3.8,
            "credit_rating_rationale": "High portfolio yields in 3-wheeler lending and stable collateral cover of 1.20x.",
            "the_good": [
                        "Double-digit 10.25% coupon yield",
                        "Low ticket auto collateral backing",
                        "Democratized \u20b910,000 denomination"
            ],
            "the_bad": [
                        "CARE BBB+ rating carries moderate credit risk"
            ],
            "the_ugly": [
                        "Severe regional transport strike or EV disruption eroding residual vehicle values"
            ],
            "collated_sources": [
                        "BSE Debt",
                        "GoldenPi"
            ]
        }
    },
    {   'asset_cover_ratio': 1.2,
    'coupon_frequency': 'MONTHLY',
    'coupon_rate_pct': 10.25,
    'credit_rating': 'ICRA A+',
    'credit_rating_agency': 'ICRA',
    'exchange': 'NSE',
    'face_value': 10000.0,
    'fldg_pct': 5.0,
    'instrument_name': 'Vivriti Gold Loan Receivables Series I Securitized Debt Instrument',
    'instrument_type': 'SDI',
    'is_listed': True,
    'is_sdi': True,
    'isin': 'IN901SDI0012',
    'issue_date': '2024-01-15',
    'last_traded_price': 10000.0,
    'macaulay_duration_years': 0.72,
    'maturity_date': '2025-07-15',
    'metadata': {   'collated_sources': ['Wint Wealth', 'Grip Invest', 'NSE Debt'],
                    'collateral_type': 'Bankruptcy-remote pool of retail loans held in SPV trust',
                    'credit_rating_rationale': 'ICRA A+(SO) rating reflects the bankruptcy-remote '
                                               'structural isolation of the loan pool and the 5.0% '
                                               'First Loss Default Guarantee (FLDG) deposited in '
                                               'an escrow account with the Trustee.',
                    'fldg_pct': 5.0,
                    'issuer_overview': 'This Securitized Debt Instrument (SDI) represents '
                                       'pass-through units issued by a SEBI-registered SPV Trust '
                                       'managed by Vivriti. The trust holds an isolated pool of '
                                       'retail secured loans originated by KrazyBee Financial '
                                       'Services. Monthly borrower principal and interest '
                                       "collections are remitted directly to unitholders' demat "
                                       'bank accounts.',
                    'pool_size_cr': 45.0,
                    'promoter_group': 'KrazyBee / Vivriti Asset Management',
                    'sector': 'Securitized Retail Debt (SDI)',
                    'the_bad': [   'Zero Secondary Liquidity: SDIs have virtually no exchange '
                                   'trading volume; investors must hold through monthly '
                                   'amortization to maturity.',
                                   'Origination Servicing Risk: If originator operations halt, an '
                                   'alternate backup servicer must step in to manage loan '
                                   'collections.'],
                    'the_good': [   'Bankruptcy Remote: The loan pool is legally ring-fenced in a '
                                    'trust; if the originator goes bankrupt, creditors cannot '
                                    'touch these assets.',
                                    '5% FLDG Protection: First Loss Default Guarantee absorbs the '
                                    'first 5% of borrower defaults before investor principal is '
                                    'impacted.',
                                    'Monthly Cash Flow: Monthly coupon + principal amortization '
                                    'accelerates capital recovery within 18 months.'],
                    'the_ugly': [   'Catastrophic Pool Default Spike: If retail borrower defaults '
                                    'exceed the 5.0% FLDG buffer, investors face direct pro-rata '
                                    'principal haircuts.'],
                    'underlying_loan_type': 'Secured Digital Gold & Consumer Asset Loans'},
    'modified_duration_years': 0.65,
    'originator': 'KrazyBee Financial Services Pvt Ltd',
    'scrip_code': '939900',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'SDI-1',
    'ticker': 'KRAZYSDI',
    'ytm_pct': 10.25},
    {   'asset_cover_ratio': 1.25,
    'coupon_frequency': 'MONTHLY',
    'coupon_rate_pct': 11.2,
    'credit_rating': 'CRISIL A',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'NSE',
    'face_value': 10000.0,
    'fldg_pct': 8.0,
    'instrument_name': 'Grip LeaseX Corporate Equipment Rental Series II SDI',
    'instrument_type': 'SDI',
    'is_listed': True,
    'is_sdi': True,
    'isin': 'IN902SDI0025',
    'issue_date': '2024-02-10',
    'last_traded_price': 10000.0,
    'macaulay_duration_years': 0.98,
    'maturity_date': '2026-02-10',
    'metadata': {   'collated_sources': ['Grip Invest', 'Wint Wealth', 'NSE Debt'],
                    'collateral_type': 'Leased industrial equipment, EV fleet assets, and '
                                       'contracted lease rentals',
                    'credit_rating_rationale': 'CRISIL A(SO) rating supported by strong corporate '
                                               'lessee counterparty credit profiles, hypothecated '
                                               'equipment title, and an 8.0% cash credit '
                                               'enhancement (FLDG).',
                    'fldg_pct': 8.0,
                    'issuer_overview': 'LeaseX is a SEBI-regulated Securitized Debt Instrument '
                                       'backed by corporate equipment and electric vehicle fleet '
                                       'lease agreements entered into with blue-chip and '
                                       'high-growth Indian companies. Lease rental payments flow '
                                       'directly into an escrow account administered by an '
                                       'independent SEBI debenture trustee.',
                    'pool_size_cr': 30.0,
                    'promoter_group': 'Grip Invest Alternative Assets',
                    'sector': 'Equipment Leasing Securitized Debt (SDI)',
                    'the_bad': [   'Corporate Counterparty Concentration: Pool returns rely on a '
                                   'concentrated group of corporate lessees paying monthly rentals '
                                   'on time.',
                                   'Equipment Repossession Friction: If a lessee defaults, '
                                   'reclaiming and liquidating industrial machinery can take '
                                   'several months.'],
                    'the_good': [   'High 11.20% Net YTM: One of the highest institutional yields '
                                    'available under the SEBI ₹10,000 framework.',
                                    'Substantial 8% FLDG: Substantial cash cushion protects '
                                    'against lessee payment delays.',
                                    'Monthly Demat Payouts: Regular monthly interest and principal '
                                    'repayment credited directly via RTGS/NEFT.'],
                    'the_ugly': [   'Lessee Bankruptcy & Equipment Obsolescence: If multiple '
                                    'lessees declare insolvency under NCLT simultaneously, '
                                    'recovered lease equipment salvage values may be heavily '
                                    'discounted.'],
                    'underlying_loan_type': 'Corporate Operating & Financial Leases'},
    'modified_duration_years': 0.89,
    'originator': 'Grip Invest / Virenxia Capital',
    'scrip_code': '939915',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'SDI-2',
    'ticker': 'LEASEXSDI',
    'ytm_pct': 11.2},
    {   'asset_cover_ratio': 1.2,
    'coupon_frequency': 'MONTHLY',
    'coupon_rate_pct': 10.5,
    'credit_rating': 'CRISIL A',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'NSE',
    'face_value': 10000.0,
    'fldg_pct': 10.0,
    'instrument_name': 'Wint Wealth InvoiceX Series II Blue-Chip Vendor SDI',
    'instrument_type': 'SDI',
    'is_listed': True,
    'is_sdi': True,
    'isin': 'INE001A08029',
    'issue_date': '2024-05-01',
    'last_traded_price': 10000.0,
    'macaulay_duration_years': 0.82,
    'maturity_date': '2025-11-01',
    'metadata': {   'collated_sources': ['Wint Wealth', 'NSE Debt'],
                    'collateral_type': 'Accepted supply chain invoices payable by Tier-1 corporate '
                                       'buyers',
                    'credit_rating_rationale': 'CRISIL A(SO) rating underpinned by '
                                               'bankruptcy-remote SPV structure, accepted invoice '
                                               'mandates on high-rated corporate anchors, and 10% '
                                               'cash FLDG reserve.',
                    'fldg_pct': 10.0,
                    'issuer_overview': 'SEBI-regulated Securitized Debt Instrument issued by an '
                                       'independent trust holding accepted supply-chain invoices '
                                       'drawn on Fortune-500 / Nifty-50 corporate buyers with an '
                                       'irrevocable 10% First Loss Default Guarantee.',
                    'pool_size_cr': 45.0,
                    'promoter_group': 'Bankruptcy-Remote Trust (SEBI Regulated SDI)',
                    'sector': 'Securitized Vendor Invoice Discounting',
                    'the_bad': [   'Non-sovereign credit risk on underlying corporate buyer '
                                   'counterparties',
                                   'Modest secondary market liquidity; designed to be held to '
                                   'maturity'],
                    'the_good': [   'High 10.50% YTM paid out monthly directly to investor bank '
                                    'account',
                                    'Substantial 10% cash FLDG buffer absorbs invoice defaults',
                                    'Ultra-short 0.8-year duration with zero equity market '
                                    'correlation'],
                    'the_ugly': [   'Systemic commercial dispute between anchor buyers and vendors '
                                    'freezing invoice settlement'],
                    'underlying_loan_type': 'Corporate Supply Chain Receivables'},
    'modified_duration_years': 0.74,
    'originator': 'Vivriti Capital / KredX Vendor Trust',
    'scrip_code': '939002',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'SDI2',
    'ticker': 'WINT_INVOICEX',
    'ytm_pct': 10.5},
    {   'asset_cover_ratio': 1.35,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 7.65,
    'credit_rating': 'CRISIL AAA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'REC Limited 7.65% Maharatna PSU Bond 2031',
    'instrument_type': 'PSU_BOND',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE020B08898',
    'issue_date': '2023-11-20',
    'last_traded_price': 10020.0,
    'macaulay_duration_years': 5.4,
    'maturity_date': '2031-11-20',
    'metadata': {   'aum_cr': '₹5,10,000+ Cr Loan Book',
                    'collated_sources': ['BSE Debt Market', 'IndiaBonds'],
                    'collateral_type': 'First pari-passu charge on standard project loan assets',
                    'interest_coverage': 2.1,
                    'issuer_overview': 'REC Limited is a central Maharatna public sector '
                                       'enterprise dedicated to financing power generation, '
                                       'transmission, renewable energy, and infrastructure '
                                       'projects across India.',
                    'promoter_group': 'Government of India (PFC Owned / Ministry of Power)',
                    'sector': 'Power Sector Public Financial Institution',
                    'the_bad': [   'High state discom sector concentration risk',
                                   'Duration of 5+ years creates price sensitivity to RBI rate '
                                   'shifts'],
                    'the_good': [   'Quasi-sovereign credit risk with 100% government ownership '
                                    'chain',
                                    'CRISIL AAA highest safety badge',
                                    "Essential strategic financier of India's national power grid"],
                    'the_ugly': [   'Structural delays in state electricity regulatory commission '
                                    'tariff revisions']},
    'modified_duration_years': 5.02,
    'originator': None,
    'scrip_code': '935402',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'P1',
    'ticker': 'REC',
    'ytm_pct': 7.61},
    {   'asset_cover_ratio': 1.0,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 7.95,
    'credit_rating': 'CRISIL AAA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'NSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'HDFC Bank 7.95% Subordinated Tier-II Non-Convertible Bond 2033',
    'instrument_type': 'Subordinated Tier-II',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE040A08377',
    'issue_date': '2023-08-18',
    'last_traded_price': 9980.0,
    'macaulay_duration_years': 5.4,
    'maturity_date': '2033-08-18',
    'metadata': {   'aum_cr': 'Total Balance Sheet ₹36,00,000+ Cr',
                    'collated_sources': ['GoldenPi', 'IndiaBonds', 'NSE Debt'],
                    'collateral_type': 'Unsecured Subordinated Regulatory Capital (Tier-II)',
                    'crar_pct': 19.8,
                    'credit_rating_rationale': 'CRISIL AAA/Stable rating reflects systemically '
                                               'vital franchise, exceptional funding profile, '
                                               'market-leading asset quality, and robust capital '
                                               'buffers.',
                    'gnpa_pct': 1.26,
                    'issuer_overview': "HDFC Bank Limited is India's largest private sector bank "
                                       'and a designated Domestic Systemically Important Bank '
                                       '(D-SIB) by the RBI. Holding over ₹25 lakh crore in '
                                       "deposits, HDFC Bank's balance sheet is universally "
                                       'recognized as the bedrock of the Indian financial '
                                       'ecosystem.',
                    'nnpa_pct': 0.35,
                    'promoter_group': 'HDFC Bank (Institutionally Held D-SIB)',
                    'sector': 'Private Sector Banking (D-SIB)',
                    'the_bad': [   'Subordinated Liquidation Rank: Tier-II bonds rank junior to '
                                   'retail depositors and senior creditors in resolution.',
                                   'High Duration Sensitivity: 5.0-year modified duration implies '
                                   '~5% price volatility for every 100 bps shift in long-term '
                                   'sovereign bond yields.'],
                    'the_good': [   'Too Big To Fail (D-SIB): Designated systemically important '
                                    'bank; sovereign-like regulatory supervision.',
                                    'Rock-Solid Asset Quality: Net NPA of 0.35% with 75% provision '
                                    'coverage ratio.',
                                    'Long-Term Compounding: 10-year locked coupon providing '
                                    'predictable retirement cash flows.'],
                    'the_ugly': [   'Point of Non-Viability (PONV) Risk: While near-impossible for '
                                    'HDFC Bank, Basel III Tier-II debt can be converted or written '
                                    'off under extreme RBI bank failure intervention.']},
    'modified_duration_years': 5.0,
    'originator': None,
    'scrip_code': '938330',
    'seniority_tier': 'SUBORDINATED_TIER_2',
    'series': 'T2',
    'ticker': 'HDFCBANK',
    'ytm_pct': 7.98},
    {   'asset_cover_ratio': 1.1,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 7.84,
    'credit_rating': 'CRISIL AAA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'HDFC Bank 7.84% Basel-III Tier-II Capital Bond 2033',
    'instrument_type': 'TIER_2_BOND',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE040A08472',
    'issue_date': '2023-09-22',
    'last_traded_price': 10060.0,
    'macaulay_duration_years': 6.2,
    'maturity_date': '2033-09-22',
    'metadata': {   'aum_cr': '₹36,00,000+ Cr Balance Sheet',
                    'collated_sources': ['BSE Debt Market', 'GoldenPi'],
                    'collateral_type': 'Unsecured subordinated Tier-II regulatory capital',
                    'interest_coverage': 5.2,
                    'issuer_overview': "HDFC Bank is India's largest private sector bank following "
                                       'the historic merger with parent HDFC Limited, maintaining '
                                       'pristine underwriting discipline and market leadership.',
                    'promoter_group': 'HDFC Bank Institutional Shareholding',
                    'sector': 'Private Sector Banking',
                    'the_bad': [   'Subordinated claim in bankruptcy hierarchy',
                                   'Tax drag on annual coupon payments'],
                    'the_good': [   'Pristine underwriting standards with Gross NPA consistently '
                                    'near 1.2%',
                                    'CRISIL AAA highest institutional credit rating',
                                    'Domestic Systemically Important Bank (D-SIB) status'],
                    'the_ugly': [   'Systemic regulatory invocation of PONV loss absorption '
                                    '(virtually zero historical precedent for HDFC)']},
    'modified_duration_years': 5.75,
    'originator': None,
    'scrip_code': '935502',
    'seniority_tier': 'TIER_2_SUBORDINATED',
    'series': 'T2',
    'ticker': 'HDFCBANK',
    'ytm_pct': 7.74},
    {   'asset_cover_ratio': 1.5,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 7.49,
    'credit_rating': 'CRISIL AAA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Indian Railway Finance Corp 7.49% Sovereign-Guaranteed Bond 2033',
    'instrument_type': 'PSU_BOND',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE053F08082',
    'issue_date': '2023-08-25',
    'last_traded_price': 9980.0,
    'macaulay_duration_years': 6.8,
    'maturity_date': '2033-08-25',
    'metadata': {   'aum_cr': '₹4,60,000+ Cr Assets Under Lease',
                    'collated_sources': ['BSE Debt Market', 'IndiaBonds'],
                    'collateral_type': 'First charge on railway wagons, locomotives, and track '
                                       'infrastructure',
                    'interest_coverage': 3.1,
                    'issuer_overview': 'IRFC is the dedicated market borrowing arm of the Indian '
                                       'Railways. It leases railway rolling stock and '
                                       'infrastructure assets to the Ministry of Railways with '
                                       'guaranteed lease rentals.',
                    'promoter_group': 'Ministry of Railways, Government of India',
                    'sector': 'Railway Rolling Stock Leasing',
                    'the_bad': [   'Long duration of 6+ years entails mark-to-market volatility '
                                   'before maturity',
                                   'Yield is only marginally above G-Sec benchmarks'],
                    'the_good': [   'Zero historical NPA on sovereign railway lease book',
                                    'Direct statutory backing by Ministry of Railways',
                                    'Highest AAA safety rating from all major agencies'],
                    'the_ugly': [   'Adverse revision in bilateral lease terms with Ministry of '
                                    'Railways']},
    'modified_duration_years': 6.32,
    'originator': None,
    'scrip_code': '935404',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'P3',
    'ticker': 'IRFC',
    'ytm_pct': 7.52},
    {   'asset_cover_ratio': 1.1,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 7.75,
    'credit_rating': 'CRISIL AAA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'State Bank of India 7.75% Basel-III Tier-II Capital Bond 2034',
    'instrument_type': 'TIER_2_BOND',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE062A08298',
    'issue_date': '2024-04-12',
    'last_traded_price': 10025.0,
    'macaulay_duration_years': 6.95,
    'maturity_date': '2034-04-12',
    'metadata': {   'aum_cr': '₹60,00,000+ Cr Asset Base',
                    'collated_sources': ['BSE Debt Market', 'IndiaBonds'],
                    'collateral_type': 'Unsecured subordinated Tier-II regulatory capital',
                    'interest_coverage': 4.8,
                    'issuer_overview': "State Bank of India is the nation's largest commercial "
                                       'bank commanding over 22% deposit market share, backed by '
                                       'majority sovereign ownership.',
                    'promoter_group': 'Government of India (57.5% Sovereign Stake)',
                    'sector': 'Public Sector Banking',
                    'the_bad': [   'Subordinated to depositors and senior creditors in liquidation '
                                   'waterfall',
                                   'Long 10-year maturity with 6.45-year modified duration'],
                    'the_good': [   'Sovereign-backed banking giant with systemic importance '
                                    '(D-SIB)',
                                    'Highest CRISIL AAA rating for Tier-II capital',
                                    'High liquidity in secondary exchange RFQ market'],
                    'the_ugly': [   'Statutory Point of Non-Viability (PONV) loss absorption '
                                    'clause under Basel-III framework']},
    'modified_duration_years': 6.45,
    'originator': None,
    'scrip_code': '935501',
    'seniority_tier': 'TIER_2_SUBORDINATED',
    'series': 'T1',
    'ticker': 'SBIN',
    'ytm_pct': 7.71},
    {   'asset_cover_ratio': 1.25,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 9.5,
    'credit_rating': 'CARE AA',
    'credit_rating_agency': 'CARE',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Piramal Capital & Housing 9.50% Senior Secured NCD 2026',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE087H07123',
    'issue_date': '2023-04-20',
    'last_traded_price': 10030.0,
    'macaulay_duration_years': 1.15,
    'maturity_date': '2026-04-20',
    'metadata': {   'aum_cr': '₹68,000+ Cr AUM',
                    'collated_sources': ['BSE Debt Market', 'Wint Wealth', 'GoldenPi'],
                    'collateral_type': 'First pari-passu charge on standard housing loan '
                                       'receivables',
                    'interest_coverage': 2.2,
                    'issuer_overview': 'Piramal Capital & Housing Finance is a major retail '
                                       'housing finance company created through the resolution of '
                                       'erstwhile DHFL, focused on affordable home loans and '
                                       'retail credit.',
                    'promoter_group': 'Piramal Group (Ajay Piramal)',
                    'sector': 'Housing Finance & Wholesale Credit',
                    'the_bad': [   'Legacy wholesale real estate loan book runoff',
                                   'CARE AA rating reflects historical resolution restructuring'],
                    'the_good': [   'High 9.35% yield providing +225 bps premium over G-Sec '
                                    'benchmark',
                                    'Short 1-year duration limits interest rate sensitivity',
                                    'Rapidly expanding affordable retail housing portfolio'],
                    'the_ugly': [   'Protracted legal challenges regarding resolution waterfall '
                                    'distributions']},
    'modified_duration_years': 1.05,
    'originator': None,
    'scrip_code': '936306',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N9',
    'ticker': 'PIRAMAL',
    'ytm_pct': 9.35},
    {   'asset_cover_ratio': 1.0,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 10.5,
    'credit_rating': 'CRISIL AA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'IndusInd Bank 10.50% Additional Tier-1 Perpetual Subordinated Debt',
    'instrument_type': 'Perpetual AT1',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE090A08UD5',
    'issue_date': '2021-03-24',
    'last_traded_price': 9750.0,
    'macaulay_duration_years': 4.1,
    'maturity_date': '2099-12-31',
    'metadata': {   'aum_cr': 'Loan Book ₹3,45,000+ Cr',
                    'collated_sources': ['GoldenPi', 'IndiaBonds', 'BSE Debt Market'],
                    'collateral_type': 'Perpetual Quasi-Equity Loss-Absorbing Instrument',
                    'crar_pct': 17.5,
                    'credit_rating_rationale': 'CRISIL AA/Stable rating on AT1 bonds is lower than '
                                               "bank's senior rating due to inherent "
                                               'loss-absorption triggers under RBI Basel III '
                                               'guidelines.',
                    'gnpa_pct': 1.93,
                    'issuer_overview': 'IndusInd Bank Limited is a mid-to-large private commercial '
                                       'bank with specialized leadership in vehicle financing, '
                                       'microfinance (Bharat Financial Inclusion Ltd), and gem & '
                                       'jewellery financing.',
                    'nnpa_pct': 0.57,
                    'promoter_group': 'Hinduja Group',
                    'sector': 'Private Sector Banking',
                    'the_bad': [   'Perpetual Instrument: No contractual maturity date; repayment '
                                   'relies entirely on bank exercising 5-year or 10-year call '
                                   'option.',
                                   'Coupon Discretion: Bank can skip coupon payment if capital '
                                   'adequacy falls below regulatory limits, with zero catch-up '
                                   '(non-cumulative).'],
                    'the_good': [   'Very High Yield: 10.85% YTM provides superior cash flow for '
                                    'accredited institutional risk capital.',
                                    'Strong Capital Base: CRAR of 17.5% keeps bank well above '
                                    'minimum regulatory trigger levels.'],
                    'the_ugly': [   'Permanent Write-Off at PONV: Under RBI Basel III guidelines, '
                                    'AT1 bonds can be written down to zero without shareholder '
                                    'consent if RBI declares Point of Non-Viability (as witnessed '
                                    'in Yes Bank March 2020).']},
    'modified_duration_years': 3.7,
    'originator': None,
    'scrip_code': '939015',
    'seniority_tier': 'PERPETUAL_AT1',
    'series': 'AT1',
    'ticker': 'INDUSINDBK',
    'ytm_pct': 10.85},
    {   'asset_cover_ratio': 1.4,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 8.1,
    'credit_rating': 'CRISIL AAA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Bajaj Finance 8.10% Senior Secured NCD 2029',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE121A08080',
    'issue_date': '2024-01-10',
    'last_traded_price': 10050.0,
    'macaulay_duration_years': 3.82,
    'maturity_date': '2029-01-10',
    'metadata': {   'aum_cr': '₹3,50,000+ Cr AUM',
                    'collated_sources': ['BSE Debt Market', 'GoldenPi'],
                    'collateral_type': 'First pari-passu charge on consumer and SME loan '
                                       'receivables',
                    'crar_pct': 21.5,
                    'gnpa_pct': 0.95,
                    'interest_coverage': 4.2,
                    'issuer_overview': "Bajaj Finance Limited is India's largest and most "
                                       'diversified consumer finance NBFC with over ₹3,50,000 Cr '
                                       'in AUM and pristine asset quality metrics.',
                    'nnpa_pct': 0.35,
                    'promoter_group': 'Bajaj Group (Sanjiv Bajaj)',
                    'sector': 'Retail NBFC',
                    'the_bad': [   'Tight credit spread of ~88 bps over sovereign G-Sec benchmark',
                                   'Post-tax yield for 30% slab is ~5.49%'],
                    'the_good': [   'Pristine CRISIL AAA credit profile with fortress balance '
                                    'sheet',
                                    'Gross NPA below 1% across economic cycles',
                                    '1.40x asset cover registered with debenture trustee'],
                    'the_ugly': [   'Unforeseen regulatory changes from RBI on unsecured retail '
                                    'lending risk weights']},
    'modified_duration_years': 3.54,
    'originator': None,
    'scrip_code': '936201',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N3',
    'ticker': 'BAJAJFIN',
    'ytm_pct': 7.98},
    {   'asset_cover_ratio': 1.25,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 8.75,
    'credit_rating': 'CRISIL AA+',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Cholamandalam Investment 8.75% NCD 2027',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE121A08999',
    'issue_date': '2026-10-07',
    'last_traded_price': 10000.0,
    'macaulay_duration_years': 2.77,
    'maturity_date': '2029-10-07',
    'metadata': {   'collated_sources': ['User Ingestion Portal', 'BSE Debt Market'],
                    'collateral_type': 'Registered charge on standard assets',
                    'issuer_overview': 'Institutional fixed-income security indexed via on-demand '
                                       'ISIN audit for INE121A08999.',
                    'promoter_group': 'CHOLAFIN Group',
                    'sector': 'Corporate Fixed Income',
                    'the_bad': [   'Requires ongoing surveillance against issuer credit and '
                                   'liquidity cycles.'],
                    'the_good': [   'Listed and tracked under SEBI ₹10,000 face value framework.',
                                    'Contractual coupon rate of 8.75%.'],
                    'the_ugly': [   'Seniority waterfall risk in unexpected restructuring '
                                    'proceedings.']},
    'modified_duration_years': 2.49,
    'originator': None,
    'scrip_code': None,
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N1',
    'ticker': 'CHOLAFIN',
    'ytm_pct': 11.36},
    {   'asset_cover_ratio': 1.3,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 7.72,
    'credit_rating': 'ICRA AAA',
    'credit_rating_agency': 'ICRA',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Power Finance Corporation 7.72% Maharatna PSU Bond 2030',
    'instrument_type': 'PSU_BOND',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE134E08KJ4',
    'issue_date': '2023-10-15',
    'last_traded_price': 10040.0,
    'macaulay_duration_years': 4.65,
    'maturity_date': '2030-10-15',
    'metadata': {   'aum_cr': '₹5,40,000+ Cr AUM',
                    'collated_sources': ['BSE Debt Market', 'GoldenPi'],
                    'collateral_type': 'First pari-passu charge on infrastructure loan receivables',
                    'interest_coverage': 2.2,
                    'issuer_overview': 'PFC is the largest infrastructure finance company in India '
                                       'dedicated exclusively to financing power generation, '
                                       'transmission, distribution, and green hydrogen projects.',
                    'promoter_group': 'Government of India (Ministry of Power)',
                    'sector': 'Power Sector Public Financial Institution',
                    'the_bad': [   'Credit spread is only ~56 bps over 10Y G-Sec',
                                   "Taxable at investor's marginal slab rate"],
                    'the_good': [   'Maharatna PSU backed by strategic sovereign importance',
                                    'Flawless debt repayment track record since inception',
                                    'Sovereign-equivalent CRISIL/ICRA AAA rating'],
                    'the_ugly': [   'Severe systemic fiscal stress at state power distribution '
                                    'companies (Discoms)']},
    'modified_duration_years': 4.32,
    'originator': None,
    'scrip_code': '935403',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'P2',
    'ticker': 'PFC',
    'ytm_pct': 7.66},
    {   'asset_cover_ratio': 1.5,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 7.62,
    'credit_rating': 'CRISIL AAA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'NABARD 7.62% Rural Infrastructure Development Bond 2030',
    'instrument_type': 'PSU_BOND',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE261F08CL8',
    'issue_date': '2023-06-30',
    'last_traded_price': 10015.0,
    'macaulay_duration_years': 4.8,
    'maturity_date': '2030-06-30',
    'metadata': {   'aum_cr': '₹8,00,000+ Cr Asset Base',
                    'collated_sources': ['BSE Debt Market', 'GoldenPi'],
                    'collateral_type': 'Statutory charge on apex refinance loan assets',
                    'interest_coverage': 3.8,
                    'issuer_overview': "NABARD is India's apex statutory development bank for "
                                       'agriculture and rural development, refinancing rural '
                                       'cooperative banks and state infrastructure projects.',
                    'promoter_group': 'Government of India (100% Sovereign Ownership)',
                    'sector': 'Apex Agricultural & Rural Development Finance',
                    'the_bad': [   'Low credit spread over central government bonds (~49 bps)',
                                   'Taxable interest income'],
                    'the_good': [   '100% Government of India owned statutory apex bank',
                                    'Zero historical default probability with CRISIL AAA rating',
                                    'Exempt from RBI lending limits due to sovereign mandate'],
                    'the_ugly': [   'Statutory structural reorganization of rural cooperative '
                                    'banking sector']},
    'modified_duration_years': 4.46,
    'originator': None,
    'scrip_code': '935407',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'P6',
    'ticker': 'NABARD',
    'ytm_pct': 7.59},
    {   'asset_cover_ratio': 1.3,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 8.85,
    'credit_rating': 'CRISIL AAA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Tata Capital Financial Services 8.85% Senior Secured NCD 2027',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE306N07MM3',
    'issue_date': '2023-09-01',
    'last_traded_price': 10080.0,
    'macaulay_duration_years': 1.82,
    'maturity_date': '2027-09-01',
    'metadata': {   'aum_cr': '₹1,45,000+ Cr AUM',
                    'collated_sources': ['BSE Debt Market', 'Wint Wealth', 'GoldenPi'],
                    'collateral_type': 'First pari-passu charge on standard book debts and '
                                       'receivables',
                    'crar_pct': 18.2,
                    'credit_rating_rationale': 'CRISIL AAA rating is anchored by the strategic '
                                               'importance to Tata Sons, proven track record of '
                                               'timely equity infusion, pristine asset quality, '
                                               'and healthy capital adequacy.',
                    'gnpa_pct': 1.45,
                    'interest_coverage': 3.8,
                    'issuer_overview': 'Tata Capital Financial Services Limited is the flagship '
                                       'financial services arm of the Tata Group. The company '
                                       'operates a well-diversified loan book spanning retail '
                                       'consumer finance, commercial auto loans, housing finance, '
                                       'and SME corporate credit across 400+ branches nationwide.',
                    'nnpa_pct': 0.38,
                    'promoter_group': 'Tata Sons (100% Ultimate Parentage)',
                    'roa_pct': 2.3,
                    'sector': 'Diversified NBFC',
                    'the_bad': [   'Moderate Reinvestment Window: 2.5-year maturity requires '
                                   'redeployment planning in late 2027.',
                                   'Subdued Secondary Turnover: Retail lot exits on BSE RFQ '
                                   'typically trade with small discount spreads.'],
                    'the_good': [   'Tata Group Pedigree: Unmatched moral and financial backing '
                                    'from parent Tata Sons.',
                                    'Pristine Asset Quality: Gross NPA of 1.45% and Net NPA of '
                                    '0.38% represent top-decile NBFC asset quality in India.',
                                    'Comfortable Asset Cover: 1.30x registered hypothecation cover '
                                    'with Catalyst Trusteeship Ltd.'],
                    'the_ugly': [   'Systemic NBFC Liquidity Shock: In a sharp systemic liquidity '
                                    'squeeze, credit spreads for non-bank lenders could widen, '
                                    'causing paper drawdowns before maturity.']},
    'modified_duration_years': 1.68,
    'originator': None,
    'scrip_code': '936102',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N2',
    'ticker': 'TATACAP',
    'ytm_pct': 8.52},
    {   'asset_cover_ratio': 1.2,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 10.45,
    'credit_rating': 'CRISIL A',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Navi Finserv 10.45% Senior Secured NCD 2026',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE342T07279',
    'issue_date': '2024-03-05',
    'last_traded_price': 10000.0,
    'macaulay_duration_years': 0.95,
    'maturity_date': '2026-03-05',
    'metadata': {   'aum_cr': '₹11,500+ Cr AUM',
                    'collated_sources': ['Wint Wealth', 'GoldenPi', 'BSE Debt Market'],
                    'collateral_type': 'First charge on personal and housing loan book receivables',
                    'crar_pct': 27.5,
                    'credit_rating_rationale': 'CRISIL A/Stable rating supported by significant '
                                               'equity capitalization from founder Sachin Bansal, '
                                               'comfortable liquidity buffers, and rapid digital '
                                               'scalability, constrained by seasoning of '
                                               'uncollateralized personal loan portfolio.',
                    'gnpa_pct': 3.2,
                    'interest_coverage': 2.6,
                    'issuer_overview': 'Navi Finserv Limited is a technology-first digital NBFC '
                                       'founded by Sachin Bansal. The company originates 100% '
                                       'paperless personal loans and home loans via its '
                                       'proprietary mobile app, relying on automated algorithmic '
                                       'underwriting and UPI e-mandates for collection.',
                    'nnpa_pct': 1.1,
                    'promoter_group': 'Sachin Bansal (Co-founder, Flipkart)',
                    'roa_pct': 2.1,
                    'sector': 'Fintech Digital Lending NBFC',
                    'the_bad': [   'Unsecured Personal Loan Vulnerability: Underwriting algorithms '
                                   'face higher loss rates during retail job cuts or fintech '
                                   'collection friction.',
                                   'CRISIL A Rating: Single-A credit rating carries higher credit '
                                   'spread risk and sensitivity to RBI unsecured lending '
                                   'circulars.'],
                    'the_good': [   'High Double-Digit Yield: 10.45% YTM provides premium yield '
                                    '(+335 bps over G-Secs) popular among retail fixed-income '
                                    'accumulators.',
                                    'Enormous Capital Adequacy: CRAR of 27.5% provides deep equity '
                                    'absorption cushion against unexpected loan write-offs.',
                                    'Short Tenure: 2-year maturity minimizes duration and '
                                    'reinvestment exposure.'],
                    'the_ugly': [   'Regulatory Clampdown on Digital Fintech NBFCs: RBI '
                                    'restrictions on digital originations or surge in digital '
                                    'collection defaults could impair loan recovery.']},
    'modified_duration_years': 0.86,
    'originator': None,
    'scrip_code': '938550',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N1',
    'ticker': 'NAVIFIN',
    'ytm_pct': 10.45},
    {   'asset_cover_ratio': 1.35,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 9.15,
    'credit_rating': 'ICRA AA+',
    'credit_rating_agency': 'ICRA',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Muthoot Finance 9.15% Senior Secured Gold Loan Backed NCD 2026',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE414G07GE7',
    'issue_date': '2023-01-10',
    'last_traded_price': 10040.0,
    'macaulay_duration_years': 0.74,
    'maturity_date': '2026-07-10',
    'metadata': {   'aum_cr': '₹75,000+ Cr AUM',
                    'collated_sources': [   'BSE Debt Market',
                                            'Wint Wealth',
                                            'GoldenPi',
                                            'IndiaBonds'],
                    'collateral_type': 'Hypothecation of physical gold bullion loan portfolio',
                    'crar_pct': 25.4,
                    'credit_rating_rationale': "ICRA AA+/Stable rating reflects Muthoot's "
                                               'unchallenged leadership in gold financing, '
                                               'extraordinary capital adequacy (CRAR 25.4%), '
                                               'stellar profitability (RoA >5%), and strong '
                                               'gold-backed collateral cushions.',
                    'gnpa_pct': 3.8,
                    'interest_coverage': 4.1,
                    'issuer_overview': "Muthoot Finance Limited is India's largest gold loan NBFC, "
                                       'holding over 185 tonnes of physical gold bullion '
                                       'collateral in bank-grade vaults across 5,000+ branches. '
                                       'Gold loans carry ultra-short tenures (under 12 months), '
                                       'low average LTV (65-70%), and immediate liquidity via gold '
                                       'auctions upon borrower default.',
                    'nnpa_pct': 0.9,
                    'promoter_group': 'Muthoot M. George Family',
                    'roa_pct': 5.1,
                    'sector': 'Gold Loan NBFC',
                    'the_bad': [   'Regulatory Surveillance: RBI norms on gold loan cash '
                                   'disbursements and LTV caps introduce operational compliance '
                                   'sensitivity.',
                                   'Gold Price Sensitivity: A sustained crash in global gold '
                                   'bullion prices (>30%) could reduce collateral auction recovery '
                                   'margins.'],
                    'the_good': [   'Liquid Physical Collateral: Every rupee lent is backed by '
                                    'pledged 22-carat gold jewellery stored in branch vaults.',
                                    'High Profitability Buffer: Return on Assets exceeding 5% '
                                    'provides enormous cash flow cushion against operational '
                                    'shocks.',
                                    'High Coupon: 9.15% coupon generates steady, predictable '
                                    'annual income.'],
                    'the_ugly': [   'Severe Multi-Branch Vault Heist or Collateral Fraud: Any '
                                    'systemic breach in vault physical security or localized gold '
                                    'spurious pledge fraud could impact brand trust.']},
    'modified_duration_years': 0.68,
    'originator': None,
    'scrip_code': '937210',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N4',
    'ticker': 'MUTHOOTFIN',
    'ytm_pct': 8.92},
    {   'asset_cover_ratio': 1.35,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 8.9,
    'credit_rating': 'CRISIL AA+',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Muthoot Finance 8.90% Senior Secured NCD 2026',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE414G07HG2',
    'issue_date': '2023-07-15',
    'last_traded_price': 10070.0,
    'macaulay_duration_years': 1.35,
    'maturity_date': '2026-07-15',
    'metadata': {   'aum_cr': '₹80,000+ Cr Gold Loan AUM',
                    'collated_sources': ['BSE Debt Market', 'GoldenPi'],
                    'collateral_type': 'First charge on physical gold jewellery receivables and '
                                       'liquid assets',
                    'crar_pct': 27.5,
                    'gnpa_pct': 3.4,
                    'interest_coverage': 3.4,
                    'issuer_overview': "Muthoot Finance is India's largest gold financing NBFC "
                                       'holding over 180 tonnes of physical gold jewellery '
                                       'collateral securely stored in bank-grade vaults.',
                    'nnpa_pct': 1.1,
                    'promoter_group': 'Muthoot Group (M. G. George Muthoot Family)',
                    'sector': 'Gold Loan NBFC',
                    'the_bad': [   'Sensitivity to sharp domestic gold price drops triggering '
                                   'auction delays',
                                   'Increasing competition from private banks in retail gold '
                                   'loans'],
                    'the_good': [   'Short duration of 1.35 years minimizes interest rate exposure',
                                    'Backed by physical 22k gold collateral held in company vaults',
                                    'Exceptional 27.5% CRAR capital buffer'],
                    'the_ugly': ['Sudden regulatory cap on gold loan LTV ratios from RBI']},
    'modified_duration_years': 1.25,
    'originator': None,
    'scrip_code': '936302',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N5',
    'ticker': 'MUTHOOTFIN',
    'ytm_pct': 8.45},
    {   'asset_cover_ratio': 1.3,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 9.25,
    'credit_rating': 'CRISIL AA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Manappuram Finance 9.25% Senior Secured NCD 2027',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE522D07BG2',
    'issue_date': '2024-03-01',
    'last_traded_price': 10050.0,
    'macaulay_duration_years': 1.85,
    'maturity_date': '2027-03-01',
    'metadata': {   'aum_cr': '₹42,000+ Cr AUM',
                    'collated_sources': ['BSE Debt Market', 'Wint Wealth'],
                    'collateral_type': 'First charge on standard book debts and physical gold loan '
                                       'contracts',
                    'interest_coverage': 2.8,
                    'issuer_overview': 'Manappuram Finance is a leading non-banking financial '
                                       'company offering gold loans, microfinance (Asirvad), '
                                       'housing finance, and commercial vehicle loans.',
                    'promoter_group': 'V.P. Nandakumar Family',
                    'sector': 'Gold Loan & Microfinance NBFC',
                    'the_bad': [   'Microfinance subsidiary (Asirvad) exposes group to regional '
                                   'credit risks',
                                   'Higher funding cost compared to AAA NBFC peers'],
                    'the_good': [   'High 9.05% YTM offering generous credit spread for CRISIL AA '
                                    'rating',
                                    'Strong liquidity buffer and fast turnaround gold loan '
                                    'operations',
                                    '1.30x asset cover registered with Catalyst Trusteeship'],
                    'the_ugly': [   'Regional microfinance political unrest or farm loan waiver '
                                    'disruptions']},
    'modified_duration_years': 1.7,
    'originator': None,
    'scrip_code': '936303',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N6',
    'ticker': 'MANAPPURAM',
    'ytm_pct': 9.05},
    {   'asset_cover_ratio': 1.35,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 8.35,
    'credit_rating': 'CRISIL AAA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Kotak Mahindra Prime 8.35% Senior Secured NCD 2028',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE601U07054',
    'issue_date': '2023-11-05',
    'last_traded_price': 10040.0,
    'macaulay_duration_years': 2.95,
    'maturity_date': '2028-11-05',
    'metadata': {   'aum_cr': '₹34,000+ Cr AUM',
                    'collated_sources': ['BSE Debt Market', 'IndiaBonds'],
                    'collateral_type': 'First charge on hypothecated vehicle loan contracts',
                    'interest_coverage': 4.1,
                    'issuer_overview': 'Kotak Mahindra Prime is the dedicated automobile financing '
                                       'subsidiary of Kotak Mahindra Bank, holding a conservative, '
                                       'high-quality passenger vehicle loan book.',
                    'promoter_group': 'Kotak Mahindra Bank (100% Parentage)',
                    'sector': 'Car Finance & Retail Lending',
                    'the_bad': [   'Modest yield premium (~114 bps) over risk-free G-Sec',
                                   'Passenger vehicle retail sales cyclicality'],
                    'the_good': [   '100% Kotak Bank parentage with impeccable conservative '
                                    'governance',
                                    'CRISIL AAA highest credit safety rating',
                                    'Hypothecated vehicle collateral provides swift legal '
                                    'repossession rights'],
                    'the_ugly': [   'Sudden automotive residual value crash across domestic used '
                                    'car auctions']},
    'modified_duration_years': 2.72,
    'originator': None,
    'scrip_code': '936305',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N8',
    'ticker': 'KOTAKHOME',
    'ytm_pct': 8.24},
    {   'asset_cover_ratio': 1.25,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 9.15,
    'credit_rating': 'IND AA+',
    'credit_rating_agency': 'INDIA RATINGS',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Shriram Finance 9.15% Senior Secured NCD 2027',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE721A07PM9',
    'issue_date': '2023-12-01',
    'last_traded_price': 10090.0,
    'macaulay_duration_years': 2.15,
    'maturity_date': '2027-12-01',
    'metadata': {   'aum_cr': '₹2,20,000+ Cr AUM',
                    'collated_sources': ['BSE Debt Market', 'Wint Wealth', 'GoldenPi'],
                    'collateral_type': 'First pari-passu charge on commercial vehicle and '
                                       'equipment loan receivables',
                    'crar_pct': 20.4,
                    'gnpa_pct': 5.2,
                    'interest_coverage': 2.6,
                    'issuer_overview': "Shriram Finance is India's largest retail asset financing "
                                       'NBFC specializing in pre-owned commercial vehicles, MSME '
                                       'loans, two-wheelers, and gold loans across semi-urban and '
                                       'rural markets.',
                    'nnpa_pct': 2.8,
                    'promoter_group': 'Shriram Group',
                    'sector': 'Commercial Vehicle & MSME NBFC',
                    'the_bad': [   'Higher Gross NPA profile (~5%) typical of rural borrower '
                                   'demographics',
                                   'Vulnerable to diesel price spikes and monsoon agricultural '
                                   'disruptions'],
                    'the_good': [   'Attractive 8.86% YTM offering +176 bps credit spread over '
                                    'G-Sec',
                                    'Market leadership in high-yield used commercial vehicle '
                                    'lending',
                                    'Strong 20%+ capital adequacy ratio'],
                    'the_ugly': [   'Extended national freight freight rate collapse impairing '
                                    'truck operator cash flows']},
    'modified_duration_years': 1.98,
    'originator': None,
    'scrip_code': '936301',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N4',
    'ticker': 'SHRIRAMFIN',
    'ytm_pct': 8.86},
    {   'asset_cover_ratio': 1.25,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 9.1,
    'credit_rating': 'CRISIL AA+',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'Shriram Finance 9.10% Senior Secured NCD 2027',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE721A07RV3',
    'issue_date': '2024-01-09',
    'last_traded_price': 10020.0,
    'macaulay_duration_years': 1.28,
    'maturity_date': '2027-01-09',
    'metadata': {   'aum_cr': '₹2,14,000+ Cr AUM',
                    'collated_sources': ['BSE Debt Market', 'Wint Wealth', 'GoldenPi'],
                    'collateral_type': 'First pari-passu hypothecation on vehicle loan receivables',
                    'crar_pct': 20.8,
                    'credit_rating_rationale': "CRISIL AA+/Stable rating recognizes Shriram's "
                                               'unassailable franchise in used commercial vehicle '
                                               'financing, proven collection mechanisms through '
                                               'economic downturns, and healthy capitalization '
                                               'post-merger.',
                    'gnpa_pct': 5.3,
                    'interest_coverage': 3.2,
                    'issuer_overview': "Shriram Finance Limited is India's largest retail asset "
                                       'financing NBFC, formed via the mega-merger of Shriram '
                                       'Transport Finance and Shriram City Union Finance. The '
                                       'company commands deep entrenched presence in pre-owned '
                                       'commercial vehicle financing, rural two-wheeler loans, '
                                       'MSME micro-enterprise lending, and gold loans across '
                                       '3,000+ branches.',
                    'nnpa_pct': 2.7,
                    'promoter_group': 'Shriram Group',
                    'roa_pct': 3.1,
                    'sector': 'Commercial Vehicle & MSME Finance',
                    'the_bad': [   'High Headline GNPA: Gross NPA of 5.3% reflects informal '
                                   'borrower profiles (though mitigated by high yields and '
                                   'repossession rights).',
                                   'Fuel Price & Freight Cycle Sensitivity: Road transport demand '
                                   'slowdowns directly impact transporter repayment velocity.'],
                    'the_good': [   'Market Leadership: Unrivaled 40-year history underwriting '
                                    "Bharat's informal road logistics and used commercial "
                                    'transport economy.',
                                    'Substantial Yield: 9.02% YTM offers +192 bps over 10Y G-Secs '
                                    'with monthly/annual coupon stability.',
                                    'High Capital Base: CRAR of 20.8% well above regulatory '
                                    'thresholds.'],
                    'the_ugly': [   'Severe Rural Drought / Diesel Price Spiral: Widespread '
                                    'logistics fleet standstills would trigger spike in credit '
                                    'provisioning.']},
    'modified_duration_years': 1.17,
    'originator': None,
    'scrip_code': '937812',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N3',
    'ticker': 'SHRIRAMFIN',
    'ytm_pct': 9.02},
    {   'asset_cover_ratio': 1.35,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 8.45,
    'credit_rating': 'CRISIL AAA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'L&T Finance Holdings 8.45% Senior Secured NCD 2028',
    'instrument_type': 'NCD',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE725H08070',
    'issue_date': '2023-05-18',
    'last_traded_price': 10080.0,
    'macaulay_duration_years': 2.75,
    'maturity_date': '2028-05-18',
    'metadata': {   'aum_cr': '₹90,000+ Cr AUM',
                    'collated_sources': ['BSE Debt Market', 'GoldenPi'],
                    'collateral_type': 'First pari-passu charge on standard retail loan '
                                       'receivables',
                    'interest_coverage': 3.5,
                    'issuer_overview': 'L&T Finance Holdings is a leading retail financial '
                                       "services company backed by India's engineering giant "
                                       'Larsen & Toubro, with focus on farm equipment, rural '
                                       'business loans, and urban consumer finance.',
                    'promoter_group': 'Larsen & Toubro Limited (Parentage)',
                    'sector': 'Diversified Retail NBFC',
                    'the_bad': [   'Modest credit spread over G-Sec benchmark (~111 bps)',
                                   'Cyclical vulnerability in rural tractor financing'],
                    'the_good': [   'Pristine L&T parentage providing unmatched financial backing',
                                    'CRISIL AAA highest institutional credit rating',
                                    'Successful complete transition into a retail-focused lender'],
                    'the_ugly': [   'Severe sequential rural drought impairing farm equipment '
                                    'collection efficiency']},
    'modified_duration_years': 2.54,
    'originator': None,
    'scrip_code': '936304',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'N7',
    'ticker': 'LTFIN',
    'ytm_pct': 8.21},
    {   'asset_cover_ratio': 1.45,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 7.4,
    'credit_rating': 'CRISIL AAA',
    'credit_rating_agency': 'CRISIL',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'NTPC Limited 7.40% Green Energy Transition Bond 2034',
    'instrument_type': 'PSU_BOND',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE733E07KA5',
    'issue_date': '2024-02-10',
    'last_traded_price': 9940.0,
    'macaulay_duration_years': 7.2,
    'maturity_date': '2034-02-10',
    'metadata': {   'aum_cr': '₹4,20,000+ Cr Enterprise Net Worth',
                    'collated_sources': ['BSE Debt Market', 'IndiaBonds'],
                    'collateral_type': 'First charge on solar, wind, and hydro renewable '
                                       'generation assets',
                    'interest_coverage': 4.5,
                    'issuer_overview': "NTPC Limited is India's largest energy conglomerate with "
                                       '76+ GW installed generation capacity and a rapid multi-GW '
                                       'renewable energy expansion program.',
                    'promoter_group': 'Government of India (Ministry of Power)',
                    'sector': 'Power Generation & Clean Energy',
                    'the_bad': [   'Long duration of 7.2 years exposes secondary pricing to yield '
                                   'curve shifts',
                                   'Low credit spread'],
                    'the_good': [   'Dedicated green financing vehicle with certified ESG '
                                    'compliance',
                                    'CRISIL AAA sovereign-equivalent stability',
                                    "Dominant ~24% contribution to India's total power generation"],
                    'the_ugly': [   'Severe coal supply bottlenecks or geopolitical thermal '
                                    'commodity shocks']},
    'modified_duration_years': 6.7,
    'originator': None,
    'scrip_code': '935406',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'P5',
    'ticker': 'NTPC',
    'ytm_pct': 7.49},
    {   'asset_cover_ratio': 1.35,
    'coupon_frequency': 'ANNUAL',
    'coupon_rate_pct': 7.6,
    'credit_rating': 'CARE AAA',
    'credit_rating_agency': 'CARE',
    'exchange': 'BSE',
    'face_value': 10000.0,
    'fldg_pct': 0.0,
    'instrument_name': 'National Highways Authority 7.60% Infrastructure Bond 2032',
    'instrument_type': 'PSU_BOND',
    'is_listed': True,
    'is_sdi': False,
    'isin': 'INE906B07GD8',
    'issue_date': '2022-12-15',
    'last_traded_price': 10010.0,
    'macaulay_duration_years': 5.9,
    'maturity_date': '2032-12-15',
    'metadata': {   'aum_cr': 'Statutory Authority',
                    'collated_sources': ['BSE Debt Market', 'GoldenPi'],
                    'collateral_type': 'Charge on designated national highway toll cash flows and '
                                       'cess receipts',
                    'interest_coverage': 2.5,
                    'issuer_overview': 'NHAI is the statutory authority responsible for the '
                                       'development, maintenance, and toll monetization of the '
                                       'national highways network in India.',
                    'promoter_group': 'Ministry of Road Transport and Highways (MoRTH)',
                    'sector': 'National Highway Infrastructure',
                    'the_bad': [   'High absolute leverage across national highway projects',
                                   'Toll collection volatility during extreme monsoon disruptions'],
                    'the_good': [   'Essential national backbone asset with statutory government '
                                    'backing',
                                    'Highest CARE AAA rating',
                                    'Settled on BSE/NSE exchange debt segment'],
                    'the_ugly': [   'Structural shifts in central fuel cess allocations towards '
                                    'highway construction']},
    'modified_duration_years': 5.48,
    'originator': None,
    'scrip_code': '935405',
    'seniority_tier': 'SENIOR_SECURED',
    'series': 'P4',
    'ticker': 'NHAI',
    'ytm_pct': 7.58}

]

# Helper lookup by ISIN and Ticker
CANONICAL_DEBT_BY_ISIN: Dict[str, Dict[str, Any]] = {
    s["isin"].upper(): s for s in CANONICAL_DEBT_UNIVERSE
}
CANONICAL_DEBT_BY_TICKER: Dict[str, List[Dict[str, Any]]] = {}
for s in CANONICAL_DEBT_UNIVERSE:
    tick = s.get("ticker", "").upper()
    if tick:
        CANONICAL_DEBT_BY_TICKER.setdefault(tick, []).append(s)
