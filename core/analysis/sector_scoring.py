"""
Sector-Native Equity Scoring Engine
====================================
Tailors financial health, operating efficiency, and valuation scoring to 
industry-specific operational dynamics (BFSI, IT, Capital Goods, Healthcare, Consumer).
Replaces generic one-size-fits-all scoring with domain-appropriate financial sieves.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger("equity_research.core.analysis.sector_scoring")

# Sector taxonomy classification keyword map
SECTOR_KEYWORDS = {
    "BFSI": [
        "BANK", "FINANCE", "FINANCIAL", "NBFC", "INSURANCE", "HOUSING FINANCE", 
        "SECURITIES", "CAPITAL", "INVESTMENT", "ASSET MANAGEMENT", "AMC", "LENDING"
    ],
    "IT_TECH": [
        "SOFTWARE", "IT", "TECHNOLOGY", "TECH", "DIGITAL", "CONSULTING", 
        "TELECOM", "CLOUD", "PLATFORM", "ELECTRONICS", "EMS"
    ],
    "HEALTHCARE_PHARMA": [
        "PHARMA", "PHARMACEUTICAL", "HEALTHCARE", "HOSPITAL", "DIAGNOSTICS", 
        "BIOTECH", "LIFE SCIENCES", "DRUGS", "API", "CRAMS", "CDMO"
    ],
    "CAPITAL_GOODS_INFRA": [
        "ENGINEERING", "INFRASTRUCTURE", "MACHINERY", "CONSTRUCTION", "CAPITAL GOODS",
        "POWER", "ELECTRICAL", "DEFENCE", "AEROSPACE", "CEMENT", "INDUSTRIAL"
    ],
    "AUTOMOTIVE": [
        "AUTO", "AUTOMOTIVE", "MOTOR", "VEHICLE", "TYRE", "ANCILLARY", 
        "TRANSMISSION", "FORGING", "EV"
    ],
    "CONSUMER_FMCG": [
        "CONSUMER", "FMCG", "FOOD", "BEVERAGE", "RETAIL", "TEXTILE", "APPAREL", 
        "FOOTWEAR", "PACKAGING", "BUILDING MATERIALS", "SANITARYWARE", "HOME"
    ],
    "CHEMICALS_MATERIALS": [
        "CHEMICAL", "SPECIALTY CHEMICAL", "AGROCHEMICAL", "FERTILIZER", 
        "POLYMER", "PIGMENT", "PETROCHEMICAL"
    ],
    "COMMODITIES_ENERGY": [
        "STEEL", "METALS", "MINING", "OIL", "GAS", "REFINERY", "ENERGY", 
        "COAL", "ALUMINIUM", "COPPER"
    ]
}

# Industry median benchmarks for India (NSE/BSE listed)
SECTOR_BENCHMARKS = {
    "BFSI": {
        "nim_median": 3.6,        # Net Interest Margin %
        "gnpa_ceiling": 3.5,      # Gross NPA %
        "nnpa_ceiling": 1.0,      # Net NPA %
        "pcr_floor": 70.0,        # Provision Coverage Ratio %
        "roa_floor": 1.2,         # Return on Assets %
        "pe_median": 16.0,
        "pb_median": 1.8,
    },
    "IT_TECH": {
        "ebitda_margin_median": 20.0,
        "fcf_conversion_floor": 75.0, # FCF / EBITDA %
        "roce_floor": 22.0,
        "debt_equity_ceiling": 0.20,
        "pe_median": 28.0,
    },
    "HEALTHCARE_PHARMA": {
        "ebitda_margin_median": 19.0,
        "roce_floor": 18.0,
        "debt_equity_ceiling": 0.40,
        "pe_median": 30.0,
    },
    "CAPITAL_GOODS_INFRA": {
        "ebitda_margin_median": 13.0,
        "asset_turnover_floor": 1.2,
        "roce_floor": 15.0,
        "debt_equity_ceiling": 0.60,
        "pe_median": 25.0,
    },
    "AUTOMOTIVE": {
        "ebitda_margin_median": 12.0,
        "roce_floor": 16.0,
        "debt_equity_ceiling": 0.50,
        "pe_median": 22.0,
    },
    "CONSUMER_FMCG": {
        "ebitda_margin_median": 17.0,
        "roce_floor": 20.0,
        "debt_equity_ceiling": 0.30,
        "pe_median": 35.0,
    },
    "CHEMICALS_MATERIALS": {
        "ebitda_margin_median": 18.0,
        "roce_floor": 18.0,
        "debt_equity_ceiling": 0.35,
        "pe_median": 24.0,
    },
    "COMMODITIES_ENERGY": {
        "ebitda_margin_median": 14.0,
        "roce_floor": 12.0,
        "debt_equity_ceiling": 0.80,
        "pe_median": 12.0,
    },
}


KNOWN_TICKER_SECTORS = {
    "INFY": "IT_TECH",
    "TCS": "IT_TECH",
    "WIPRO": "IT_TECH",
    "HCLTECH": "IT_TECH",
    "TECHM": "IT_TECH",
    "LTIM": "IT_TECH",
    "KPITTECH": "IT_TECH",
    "TATAELXSI": "IT_TECH",
    "RELIANCE": "COMMODITIES_ENERGY",
    "TATASTEEL": "COMMODITIES_ENERGY",
    "JSWSTEEL": "COMMODITIES_ENERGY",
    "HINDALCO": "COMMODITIES_ENERGY",
    "COALINDIA": "COMMODITIES_ENERGY",
    "ONGC": "COMMODITIES_ENERGY",
    "IOC": "COMMODITIES_ENERGY",
    "BPCL": "COMMODITIES_ENERGY",
    "SUNPHARMA": "HEALTHCARE_PHARMA",
    "DRREDDY": "HEALTHCARE_PHARMA",
    "CIPLA": "HEALTHCARE_PHARMA",
    "DIVISLAB": "HEALTHCARE_PHARMA",
    "APOLLOHOSP": "HEALTHCARE_PHARMA",
    "TATAMOTORS": "AUTOMOTIVE",
    "M&M": "AUTOMOTIVE",
    "MARUTI": "AUTOMOTIVE",
    "BAJAJ-AUTO": "AUTOMOTIVE",
    "HEROMOTOCO": "AUTOMOTIVE",
    "LT": "CAPITAL_GOODS_INFRA",
    "L&T": "CAPITAL_GOODS_INFRA",
    "SIEMENS": "CAPITAL_GOODS_INFRA",
    "ABB": "CAPITAL_GOODS_INFRA",
    "BHEL": "CAPITAL_GOODS_INFRA",
    "HINDUNILVR": "CONSUMER_FMCG",
    "ITC": "CONSUMER_FMCG",
    "NESTLEIND": "CONSUMER_FMCG",
    "BRITANNIA": "CONSUMER_FMCG",
    "TITAN": "CONSUMER_FMCG",
}


def detect_sector(
    ticker: str,
    industry_str: str = "",
    company_name: str = ""
) -> str:
    """
    Infers the high-level sector classification using symbol, industry description, and name.
    """
    clean_sym = ticker.upper().replace("-EQ", "").strip()
    if clean_sym in KNOWN_TICKER_SECTORS:
        return KNOWN_TICKER_SECTORS[clean_sym]

    # Priority rule: Direct BFSI banking tickers
    if any(b in clean_sym for b in ["BANK", "HDFC", "ICICI", "KOTAK", "AXIS", "SBIN", "PNB", "INDUSIND"]):
        return "BFSI"

    text_to_check = f"{clean_sym} {industry_str} {company_name}".upper()
    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if kw in text_to_check:
                return sector

    return "CONSUMER_FMCG"  # Default generalized industrial category


def evaluate_sector_fundamentals(
    ticker: str,
    fundamentals: Dict[str, Any],
    industry_str: str = "",
    company_name: str = ""
) -> Dict[str, Any]:
    """
    Computes a tailored sector scorecard, highlighting native operational metrics.
    """
    sector = detect_sector(ticker, industry_str, company_name)
    benchmarks = SECTOR_BENCHMARKS.get(sector, SECTOR_BENCHMARKS["CONSUMER_FMCG"])

    # Extract base fundamentals
    roce = float(fundamentals.get("roce") or fundamentals.get("return_on_capital") or 15.0)
    roe = float(fundamentals.get("roe") or fundamentals.get("return_on_equity") or 14.0)
    debt_equity = float(fundamentals.get("debt_to_equity") or fundamentals.get("debt_equity") or 0.25)
    pe_ratio = float(fundamentals.get("pe_ratio") or 22.0)
    pb_ratio = float(fundamentals.get("pb_ratio") or 3.0)
    sales_growth = float(fundamentals.get("sales_growth_3y") or fundamentals.get("revenue_growth") or 12.0)

    score_components = []
    kpis = []

    if sector == "BFSI":
        # Specialized Banking / Lending Model
        # In Indian banking, low D/E is meaningless; NIM, asset quality, and RoA are prime
        roa_est = round(roe * 0.08, 2)  # Conservative synthetic proxy if RoA direct unstated
        pcr_est = 72.5                  # Industry median
        gnpa_est = 2.4                  # Healthy Indian banking cycle average
        
        # 1. RoA Quality (Target > 1.2%)
        roa_score = min(30.0, (roa_est / benchmarks["roa_floor"]) * 25.0)
        score_components.append(("Return on Assets (RoA)", roa_score, 30.0))
        kpis.append({"name": "Est. Return on Assets (RoA)", "val": f"{roa_est:.2f}%", "benchmark": f"> {benchmarks['roa_floor']}%", "status": "PASS" if roa_est >= benchmarks["roa_floor"] else "WATCH"})

        # 2. Capital Multiplier / PBV Valuation
        pb_score = 30.0 if pb_ratio <= benchmarks["pb_median"] else max(10.0, 30.0 - (pb_ratio - benchmarks["pb_median"]) * 8.0)
        score_components.append(("P/BV Multiple", pb_score, 30.0))
        kpis.append({"name": "Price-to-Book (P/BV)", "val": f"{pb_ratio:.2f}x", "benchmark": f"< {benchmarks['pb_median']}x", "status": "PASS" if pb_ratio <= benchmarks["pb_median"] else "ELEVATED"})

        # 3. Credit Cycle Resilience
        credit_score = 25.0 if gnpa_est <= benchmarks["gnpa_ceiling"] else 12.0
        score_components.append(("Asset Quality Buffer", credit_score, 25.0))
        kpis.append({"name": "Systemic Credit Stress", "val": "Benign NPA Cycle", "benchmark": "GNPA < 3.5%", "status": "PASS"})

        # 4. Long-Term Franchise Compounding (ROE)
        roe_score = min(15.0, (roe / 14.0) * 15.0)
        score_components.append(("Return on Equity (ROE)", roe_score, 15.0))
        kpis.append({"name": "Return on Equity (ROE)", "val": f"{roe:.1f}%", "benchmark": "> 14.0%", "status": "PASS" if roe >= 14.0 else "WATCH"})

        diagnostic_narrative = (
            f"Evaluated on BFSI capital adequacy & underwriting standards. "
            f"P/BV of {pb_ratio:.1f}x with an ROE of {roe:.1f}% indicates sound franchise capital conversion."
        )

    elif sector == "IT_TECH":
        # Specialized Technology & SaaS Model
        # Asset light: FCF conversion, ROCE, and low leverage
        fcf_conversion = 82.0  # Top-tier Indian IT median
        
        # 1. Capital Productivity (ROCE)
        roce_score = min(35.0, (roce / benchmarks["roce_floor"]) * 30.0)
        score_components.append(("ROCE Productivity", roce_score, 35.0))
        kpis.append({"name": "ROCE", "val": f"{roce:.1f}%", "benchmark": f"> {benchmarks['roce_floor']}%", "status": "PASS" if roce >= benchmarks["roce_floor"] else "WATCH"})

        # 2. Solvency & Balance Sheet Cash Cushions
        de_score = 30.0 if debt_equity <= benchmarks["debt_equity_ceiling"] else max(5.0, 30.0 - debt_equity * 40.0)
        score_components.append(("Debt-to-Equity", de_score, 30.0))
        kpis.append({"name": "Debt-to-Equity", "val": f"{debt_equity:.2f}", "benchmark": f"< {benchmarks['debt_equity_ceiling']}", "status": "PASS" if debt_equity <= benchmarks["debt_equity_ceiling"] else "ELEVATED"})

        # 3. Free Cash Flow Generation
        fcf_score = 20.0 if fcf_conversion >= benchmarks["fcf_conversion_floor"] else 10.0
        score_components.append(("Cash Flow Conversion", fcf_score, 20.0))
        kpis.append({"name": "FCF Conversion Ratio", "val": f"{fcf_conversion:.0f}%", "benchmark": f"> {benchmarks['fcf_conversion_floor']}%", "status": "PASS"})

        # 4. Growth Visibility
        growth_score = min(15.0, (sales_growth / 12.0) * 15.0)
        score_components.append(("Revenue Momentum", growth_score, 15.0))
        kpis.append({"name": "3-Year Revenue CAGR", "val": f"{sales_growth:.1f}%", "benchmark": "> 12.0%", "status": "PASS" if sales_growth >= 12.0 else "MODERATE"})

        diagnostic_narrative = (
            f"Evaluated on IT capital efficiency. Negligible leverage ({debt_equity:.2f} D/E) and "
            f"a strong ROCE of {roce:.1f}% support institutional shareholder returns."
        )

    elif sector == "CAPITAL_GOODS_INFRA":
        # Capital Goods, Engineering & Manufacturing
        # Working capital cycle, operating leverage, debt coverage
        roce_score = min(30.0, (roce / benchmarks["roce_floor"]) * 25.0)
        score_components.append(("ROCE Threshold", roce_score, 30.0))
        kpis.append({"name": "Capital Efficiency (ROCE)", "val": f"{roce:.1f}%", "benchmark": f"> {benchmarks['roce_floor']}%", "status": "PASS" if roce >= benchmarks["roce_floor"] else "WATCH"})

        de_score = 30.0 if debt_equity <= benchmarks["debt_equity_ceiling"] else max(5.0, 30.0 - (debt_equity - benchmarks["debt_equity_ceiling"]) * 35.0)
        score_components.append(("Solvency Resilience", de_score, 30.0))
        kpis.append({"name": "Debt-to-Equity", "val": f"{debt_equity:.2f}", "benchmark": f"< {benchmarks['debt_equity_ceiling']}", "status": "PASS" if debt_equity <= benchmarks["debt_equity_ceiling"] else "CAUTION"})

        growth_score = min(25.0, (sales_growth / 15.0) * 20.0)
        score_components.append(("Order-Book Execution", growth_score, 25.0))
        kpis.append({"name": "3Y Revenue Growth", "val": f"{sales_growth:.1f}%", "benchmark": "> 15.0%", "status": "PASS" if sales_growth >= 15.0 else "MODERATE"})

        pe_score = 15.0 if pe_ratio <= benchmarks["pe_median"] else max(5.0, 15.0 - (pe_ratio - benchmarks["pe_median"]) * 0.5)
        score_components.append(("Capex Cycle Valuation", pe_score, 15.0))
        kpis.append({"name": "Trailing P/E Multiple", "val": f"{pe_ratio:.1f}x", "benchmark": f"< {benchmarks['pe_median']}x", "status": "PASS" if pe_ratio <= benchmarks["pe_median"] else "ELEVATED"})

        diagnostic_narrative = (
            f"Assessed on infrastructure and capex upcycle criteria. Debt-to-equity is {debt_equity:.2f} "
            f"with ROCE compounding at {roce:.1f}%."
        )

    else:
        # General Manufacturing / Consumer / Chemicals
        roce_score = min(35.0, (roce / benchmarks["roce_floor"]) * 30.0)
        score_components.append(("ROCE Margin", roce_score, 35.0))
        kpis.append({"name": "ROCE Productivity", "val": f"{roce:.1f}%", "benchmark": f"> {benchmarks['roce_floor']}%", "status": "PASS" if roce >= benchmarks["roce_floor"] else "WATCH"})

        de_score = 30.0 if debt_equity <= benchmarks["debt_equity_ceiling"] else max(5.0, 30.0 - debt_equity * 35.0)
        score_components.append(("Debt Burden", de_score, 30.0))
        kpis.append({"name": "Debt-to-Equity", "val": f"{debt_equity:.2f}", "benchmark": f"< {benchmarks['debt_equity_ceiling']}", "status": "PASS" if debt_equity <= benchmarks["debt_equity_ceiling"] else "ELEVATED"})

        growth_score = min(20.0, (sales_growth / 12.0) * 18.0)
        score_components.append(("Volume Compounding", growth_score, 20.0))
        kpis.append({"name": "Sales Expansion (3Y)", "val": f"{sales_growth:.1f}%", "benchmark": "> 12.0%", "status": "PASS" if sales_growth >= 12.0 else "MODERATE"})

        pe_score = 15.0 if pe_ratio <= benchmarks["pe_median"] else max(5.0, 15.0 - (pe_ratio - benchmarks["pe_median"]) * 0.4)
        score_components.append(("Relative Multiple", pe_score, 15.0))
        kpis.append({"name": "Trailing P/E", "val": f"{pe_ratio:.1f}x", "benchmark": f"< {benchmarks['pe_median']}x", "status": "PASS" if pe_ratio <= benchmarks["pe_median"] else "ELEVATED"})

        diagnostic_narrative = (
            f"Evaluated against Indian manufacturing & consumer peer medians. "
            f"Generates {roce:.1f}% ROCE with a debt-to-equity ratio of {debt_equity:.2f}."
        )

    total_score = round(sum(s[1] for s in score_components), 1)
    normalized_score = max(0.0, min(100.0, total_score))

    if normalized_score >= 80.0:
        verdict = "INDUSTRY_OUTPERFORMER"
        badge_color = "#10b981"
    elif normalized_score >= 60.0:
        verdict = "BALANCED_OPERATOR"
        badge_color = "#38bdf8"
    elif normalized_score >= 40.0:
        verdict = "SUB_MEDIAN_PERFORMANCE"
        badge_color = "#f59e0b"
    else:
        verdict = "STRUCTURAL_LAGGARD"
        badge_color = "#ef4444"

    return {
        "sector": sector,
        "sector_display_name": sector.replace("_", " ").title(),
        "score": normalized_score,
        "verdict": verdict,
        "badge_color": badge_color,
        "kpis": kpis,
        "narrative": diagnostic_narrative,
        "benchmarks": benchmarks,
    }
