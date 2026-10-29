"""
Sector-Native Equity Scoring Engine
====================================
Tailors financial health, operating efficiency, and valuation scoring to 
industry-specific operational dynamics (BFSI, IT, Capital Goods, Healthcare, Consumer).
Replaces generic one-size-fits-all scoring with domain-appropriate financial sieves.
"""

from typing import Dict, Any, List, Optional, Tuple
import math
import logging
import re

logger = logging.getLogger("equity_research.core.analysis.sector_scoring")


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        if math.isnan(v) or math.isinf(v):
            return default
        return float(v)
    try:
        clean = str(v).strip().replace(",", "").replace("%", "")
        f = float(clean)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return default


def _parse_optional_float(v: Any) -> Optional[float]:
    """Parses a float if present, valid, and not an empty/N/A placeholder; otherwise returns None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if math.isnan(v) or math.isinf(v):
            return None
        return float(v)
    s = str(v).strip().replace(",", "").replace("%", "")
    if not s or s.upper() in ("N/A", "NONE", "NAN", "-", ""):
        return None
    try:
        f = float(s)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


# Sector taxonomy classification keyword map
SECTOR_DISPLAY_NAMES = {
    "BFSI": "BFSI & Financial Services",
    "IT_TECH": "IT & Technology Services",
    "HEALTHCARE_PHARMA": "Healthcare & Pharmaceuticals",
    "CAPITAL_GOODS_INFRA": "Capital Goods & Infrastructure",
    "AUTOMOTIVE": "Automotive & Ancillaries",
    "CONSUMER_FMCG": "Consumer & FMCG",
    "CHEMICALS_MATERIALS": "Chemicals & Specialty Materials",
    "COMMODITIES_ENERGY": "Commodities, Metals & Energy",
}

# Ordered from domain-specific sectors first so compound labels ("Capital Goods") classify accurately
SECTOR_KEYWORDS = {
    "HEALTHCARE_PHARMA": [
        "PHARMA", "PHARMACEUTICAL", "PHARMACEUTICALS", "HEALTHCARE", "HOSPITAL", "HOSPITALS",
        "DIAGNOSTICS", "DIAGNOSTIC", "BIOTECH", "BIOTECHNOLOGY", "LIFE SCIENCES", "LIFESCIENCE",
        "LIFESCIENCES", "DRUGS", "MEDICINE", "LABORATORIES", "LABS", "API", "CRAMS", "CDMO",
        "ORGANICS", "FORMULATIONS",
    ],
    "AUTOMOTIVE": [
        "AUTOMOBILE", "AUTOMOTIVE", "AUTO COMPONENTS", "AUTO ANCILLARY", "AUTO ANCILLARIES",
        "AUTO", "MOTOR", "MOTORS", "VEHICLE", "VEHICLES", "MOBILITY", "TYRE", "TYRES",
        "ANCILLARY", "TRANSMISSION", "FORGING", "FORGE", "TRACTOR", "TRACTORS", "EV",
    ],
    "CHEMICALS_MATERIALS": [
        "SPECIALTY CHEMICAL", "SPECIALTY CHEMICALS", "CHEMICAL", "CHEMICALS", "AGROCHEMICAL",
        "AGROCHEMICALS", "RASAYAN", "FERTILIZER", "FERTILIZERS", "FERTILISERS", "POLYMER",
        "POLYMERS", "PIGMENT", "PIGMENTS", "PETROCHEMICAL", "PETROCHEMICALS", "FLUORO",
        "AMINES", "ALKYL", "ADHESIVES",
    ],
    "COMMODITIES_ENERGY": [
        "STEEL", "METALS", "METAL", "MINING", "MINERALS", "OIL", "GAS", "PETROLEUM",
        "REFINERY", "ENERGY", "SOLAR", "RENEWABLE", "HYDRO", "COAL", "ALUMINIUM",
        "ALUMINUM", "COPPER", "ZINC", "POWER",
    ],
    "CAPITAL_GOODS_INFRA": [
        "CAPITAL GOODS", "ENGINEERING", "INFRASTRUCTURE", "INFRA", "MACHINERY", "CONSTRUCTION",
        "ELECTRICAL", "ELECTRICALS", "DEFENCE", "DEFENSE", "AEROSPACE", "DYNAMICS", "TURBINE",
        "CEMENT", "CEMENTS", "INDUSTRIAL", "LOGISTICS", "PORTS", "PORT", "SHIPPING", "RAIL",
        "RAILWAYS", "AVIATION", "AIRLINES", "REALTY", "PROPERTIES", "DEVELOPERS", "HOUSING",
        "BEARINGS", "ABRASIVES", "CABLES", "WIRES", "PIPES", "TUBES",
    ],
    "IT_TECH": [
        "INFORMATION TECHNOLOGY", "SOFTWARE", "IT SERVICES", "IT", "TECHNOLOGY", "TECHNOLOGIES",
        "TECH", "DIGITAL", "CONSULTING", "CONSULTANCY", "TELECOM", "TELECOMMUNICATIONS",
        "TELEPHONE", "COMMUNICATIONS", "HEXACOM", "CLOUD", "PLATFORM", "SEMICONDUCTOR", "INFOTECH",
    ],
    "BFSI": [
        "BANK", "BANKING", "FINANCE", "FINANCIAL", "FINSERV", "FINTECH", "NBFC", "INSURANCE",
        "INSURANCE BROKING", "ASSURANCE", "HOUSING FINANCE", "SECURITIES", "CAPITAL MARKETS",
        "CAPITAL MARKET", "INVESTMENT", "INVESTMENTS", "ASSET MANAGEMENT", "AMC", "LENDING",
        "BROKING", "WEALTH", "EXCHANGE", "DEPOSITORY", "CREDIT", "MICROFINANCE", "MUTUAL FUND",
        "REGISTRAR",
    ],
    "CONSUMER_FMCG": [
        "CONSUMER ELECTRICALS", "CONSUMER DURABLES", "HOME APPLIANCES",
        "CONSUMER", "FMCG", "FOOD", "FOODS", "FOODWORLD", "BEVERAGE", "BEVERAGES",
        "BREWERIES", "SPIRITS", "DISTILLERIES", "RETAIL", "MART", "TEXTILE", "TEXTILES",
        "APPAREL", "GARMENTS", "FOOTWEAR", "PACKAGING", "SANITARYWARE", "CERAMICS",
        "PAINTS", "PAINT", "JEWELLERY", "LIFESTYLE", "HOME", "APPLIANCES",
        "DURABLES", "HOTELS", "HOSPITALITY", "LEISURE", "MEDIA", "MUSIC", "AGRI",
    ],
}

_COMPILED_SECTOR_PATTERNS = {
    sec: [re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in kws]
    for sec, kws in SECTOR_KEYWORDS.items()
}

_CORP_NOISE_RE = re.compile(
    r"\b(?:LIMITED|LTD|PVT|PRIVATE|PUBLIC|COMPANY|CO|CORPORATION|CORP|INDIA|ENTERPRISES|ENTERPRISE|INDUSTRIES|HOLDINGS|GROUP|INTERNATIONAL)\b",
    re.IGNORECASE,
)

_GENERIC_SECTOR_LABELS = {"", "DIVERSIFIED", "GENERAL INDUSTRY", "GENERAL", "N/A", "NONE", "UNKNOWN"}


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
    "COFORGE": "IT_TECH",
    "PERSISTENT": "IT_TECH",
    "MPHASIS": "IT_TECH",
    "OFSS": "IT_TECH",
    "BHARTIARTL": "IT_TECH",
    "BHARTI AIRTEL": "IT_TECH",
    "AVANTEL": "IT_TECH",
    "INDUSINDBK": "BFSI",
    "HDFCBANK": "BFSI",
    "ICICIBANK": "BFSI",
    "SBIN": "BFSI",
    "SBILIFE": "BFSI",
    "SBICARD": "BFSI",
    "LICI": "BFSI",
    "KOTAKBANK": "BFSI",
    "AXISBANK": "BFSI",
    "BAJFINANCE": "BFSI",
    "BAJAJFINSV": "BFSI",
    "JIOFIN": "BFSI",
    "BSE": "BFSI",
    "MCX": "BFSI",
    "CDSL": "BFSI",
    "ANGELONE": "BFSI",
    "CHOLAFIN": "BFSI",
    "SHRIRAMFIN": "BFSI",
    "MUTHOOTFIN": "BFSI",
    "PFC": "BFSI",
    "RECLTD": "BFSI",
    "IRFC": "BFSI",
    "RELIANCE": "COMMODITIES_ENERGY",
    "TATASTEEL": "COMMODITIES_ENERGY",
    "TATA STEEL": "COMMODITIES_ENERGY",
    "JSWSTEEL": "COMMODITIES_ENERGY",
    "HINDALCO": "COMMODITIES_ENERGY",
    "VEDL": "COMMODITIES_ENERGY",
    "COALINDIA": "COMMODITIES_ENERGY",
    "ONGC": "COMMODITIES_ENERGY",
    "IOC": "COMMODITIES_ENERGY",
    "BPCL": "COMMODITIES_ENERGY",
    "HPCL": "COMMODITIES_ENERGY",
    "HINDPETRO": "COMMODITIES_ENERGY",
    "GAIL": "COMMODITIES_ENERGY",
    "NTPC": "COMMODITIES_ENERGY",
    "POWERGRID": "COMMODITIES_ENERGY",
    "TATAPOWER": "COMMODITIES_ENERGY",
    "CESC": "COMMODITIES_ENERGY",
    "SUNPHARMA": "HEALTHCARE_PHARMA",
    "DRREDDY": "HEALTHCARE_PHARMA",
    "CIPLA": "HEALTHCARE_PHARMA",
    "DIVISLAB": "HEALTHCARE_PHARMA",
    "LUPIN": "HEALTHCARE_PHARMA",
    "BIOCON": "HEALTHCARE_PHARMA",
    "SYNGENE": "HEALTHCARE_PHARMA",
    "APOLLOHOSP": "HEALTHCARE_PHARMA",
    "MAXHEALTH": "HEALTHCARE_PHARMA",
    "MANKIND": "HEALTHCARE_PHARMA",
    "TATAMOTORS": "AUTOMOTIVE",
    "TATA MOTORS": "AUTOMOTIVE",
    "TMCV": "AUTOMOTIVE",
    "TMPV": "AUTOMOTIVE",
    "M&M": "AUTOMOTIVE",
    "MARUTI": "AUTOMOTIVE",
    "BAJAJ-AUTO": "AUTOMOTIVE",
    "BAJAJ AUTO": "AUTOMOTIVE",
    "HEROMOTOCO": "AUTOMOTIVE",
    "EICHERMOT": "AUTOMOTIVE",
    "TVSMOTOR": "AUTOMOTIVE",
    "TVS": "AUTOMOTIVE",
    "BOSCHLTD": "AUTOMOTIVE",
    "MOTHERSON": "AUTOMOTIVE",
    "ATHER": "AUTOMOTIVE",
    "ATHER ENERGY LTD": "AUTOMOTIVE",
    "OLA": "AUTOMOTIVE",
    "OLAELECTRIC": "AUTOMOTIVE",
    "LT": "CAPITAL_GOODS_INFRA",
    "L&T": "CAPITAL_GOODS_INFRA",
    "SIEMENS": "CAPITAL_GOODS_INFRA",
    "ABB": "CAPITAL_GOODS_INFRA",
    "BHEL": "CAPITAL_GOODS_INFRA",
    "BEL": "CAPITAL_GOODS_INFRA",
    "HAL": "CAPITAL_GOODS_INFRA",
    "BDL": "CAPITAL_GOODS_INFRA",
    "3MINDIA": "CAPITAL_GOODS_INFRA",
    "HONAUT": "CAPITAL_GOODS_INFRA",
    "CUMMINSIND": "CAPITAL_GOODS_INFRA",
    "THERMAX": "CAPITAL_GOODS_INFRA",
    "AEQUS": "CAPITAL_GOODS_INFRA",
    "ADANIENT": "CAPITAL_GOODS_INFRA",
    "ADANIPORTS": "CAPITAL_GOODS_INFRA",
    "INDIGO": "CAPITAL_GOODS_INFRA",
    "INTERGLOBE": "CAPITAL_GOODS_INFRA",
    "DLF": "CAPITAL_GOODS_INFRA",
    "POLYCAB": "CAPITAL_GOODS_INFRA",
    "KEI": "CAPITAL_GOODS_INFRA",
    "HAVELLS": "CAPITAL_GOODS_INFRA",
    "PIDILITIND": "CHEMICALS_MATERIALS",
    "SRF": "CHEMICALS_MATERIALS",
    "PIIND": "CHEMICALS_MATERIALS",
    "UPL": "CHEMICALS_MATERIALS",
    "DEEPAKNTR": "CHEMICALS_MATERIALS",
    "NAVINFLUOR": "CHEMICALS_MATERIALS",
    "AETHER": "CHEMICALS_MATERIALS",
    "HINDUNILVR": "CONSUMER_FMCG",
    "ITC": "CONSUMER_FMCG",
    "NESTLEIND": "CONSUMER_FMCG",
    "BRITANNIA": "CONSUMER_FMCG",
    "TITAN": "CONSUMER_FMCG",
    "TRENT": "CONSUMER_FMCG",
    "ZOMATO": "CONSUMER_FMCG",
    "ETERNAL": "CONSUMER_FMCG",
    "SWIGGY": "CONSUMER_FMCG",
    "DMART": "CONSUMER_FMCG",
    "MTNL": "IT_TECH",
    "TATACOMM": "IT_TECH",
    "INDUSTOWER": "IT_TECH",
    "HFCL": "IT_TECH",
    "TEJASNET": "IT_TECH",
    "ROUTE": "IT_TECH",
    "TANLA": "IT_TECH",
    "POLICYBZR": "BFSI",
    "PAYTM": "BFSI",
    "CAMS": "BFSI",
    "KFINTECH": "BFSI",
    "IEX": "BFSI",
    "ICICIAMC": "BFSI",
    "CROMPTON": "CONSUMER_FMCG",
    "VOLTAS": "CONSUMER_FMCG",
    "BLUESTARCO": "CONSUMER_FMCG",
    "WHIRLPOOL": "CONSUMER_FMCG",
    "VGUARD": "CONSUMER_FMCG",
    "BAJAJELEC": "CONSUMER_FMCG",
    "ORIENTELEC": "CONSUMER_FMCG",
    "SYMPHONY": "CONSUMER_FMCG",
    "ELECON": "CAPITAL_GOODS_INFRA",
}

_CONSUMER_ELECTRICALS_RE = re.compile(
    r"\b(?:CONSUMER\s+ELECTRICALS?|CONSUMER\s+DURABLES?|HOME\s+APPLIANCES?)\b",
    re.IGNORECASE,
)


def detect_sector(
    ticker: str,
    industry_str: str = "",
    company_name: str = ""
) -> str:
    """
    Infers high-level sector classification using symbol, industry metadata, and stripped
    company name with strict regex word boundaries.
    """
    clean_sym = str(ticker or "").upper().replace("-EQ", "").strip()
    if not clean_sym or clean_sym == "NONE":
        return "CONSUMER_FMCG"

    if clean_sym in KNOWN_TICKER_SECTORS:
        return KNOWN_TICKER_SECTORS[clean_sym]

    if any(b in clean_sym for b in ("BANK", "HDFC", "ICICI", "KOTAK", "AXIS", "SBIN", "PNB", "INDUSIND")):
        return "BFSI"

    clean_ind = str(industry_str or "").strip()
    if _CONSUMER_ELECTRICALS_RE.search(clean_ind):
        return "CONSUMER_FMCG"
    if clean_ind.upper() not in _GENERIC_SECTOR_LABELS:
        for sector, patterns in _COMPILED_SECTOR_PATTERNS.items():
            if any(p.search(clean_ind) for p in patterns):
                return sector

    stripped_name = _CORP_NOISE_RE.sub(" ", str(company_name or ""))
    name_and_sym = f"{clean_sym} {stripped_name}"
    if _CONSUMER_ELECTRICALS_RE.search(name_and_sym):
        return "CONSUMER_FMCG"
    for sector, patterns in _COMPILED_SECTOR_PATTERNS.items():
        if any(p.search(name_and_sym) for p in patterns):
            return sector

    if clean_ind.upper() in _GENERIC_SECTOR_LABELS and not clean_sym.isdigit():
        try:
            from core.db.fundamentals import get_cached_fundamentals
            cf = get_cached_fundamentals(clean_sym)
            if isinstance(cf, dict):
                cf_meta = f"{cf.get('sector') or ''} {cf.get('industry') or ''}".strip()
                if cf_meta and cf_meta.upper() not in _GENERIC_SECTOR_LABELS:
                    if _CONSUMER_ELECTRICALS_RE.search(cf_meta):
                        return "CONSUMER_FMCG"
                    for sector, patterns in _COMPILED_SECTOR_PATTERNS.items():
                        if any(p.search(cf_meta) for p in patterns):
                            return sector
        except Exception as cf_err:
            logger.debug("Cached sector lookup notice for %s: %s", clean_sym, cf_err)

    return "CONSUMER_FMCG"


def evaluate_sector_fundamentals(
    ticker: str,
    fundamentals: Optional[Dict[str, Any]],
    industry_str: str = "",
    company_name: str = ""
) -> Dict[str, Any]:
    """
    Computes a tailored sector scorecard, highlighting native operational metrics.
    Hardened against null fundamentals, strings with commas, and NaN ratios.
    """
    sector = detect_sector(ticker, industry_str, company_name)
    benchmarks = SECTOR_BENCHMARKS.get(sector, SECTOR_BENCHMARKS["CONSUMER_FMCG"])

    fund = fundamentals if isinstance(fundamentals, dict) else {}

    # Extract base fundamentals safely without synthetic fallback values
    roce = _parse_optional_float(fund.get("roce") or fund.get("return_on_capital"))
    roe = _parse_optional_float(fund.get("roe") or fund.get("return_on_equity"))
    debt_equity = _parse_optional_float(fund.get("debt_to_equity") or fund.get("debt_equity"))
    pe_ratio = _parse_optional_float(fund.get("pe_ratio"))
    pb_ratio = _parse_optional_float(fund.get("pb_ratio") or fund.get("price_to_book"))
    sales_growth = _parse_optional_float(fund.get("sales_growth_3y") or fund.get("revenue_growth"))
    fcf_raw = _parse_optional_float(fund.get("fcf_conversion") or fund.get("fcf_conversion_ratio") or fund.get("fcf_margin"))

    score_components = []
    kpis = []
    narrative_points = []

    if sector == "BFSI":
        # Specialized Banking / Lending Model
        # 1. RoA Quality (Target > 1.2%)
        roa_direct = _parse_optional_float(fund.get("roa") or fund.get("return_on_assets"))
        if roa_direct is not None:
            roa_score = min(30.0, (roa_direct / benchmarks["roa_floor"]) * 25.0)
            score_components.append(("Return on Assets (RoA)", roa_score, 30.0))
            kpis.append({"name": "Return on Assets (RoA)", "val": f"{roa_direct:.2f}%", "benchmark": f"> {benchmarks['roa_floor']}%", "status": "PASS" if roa_direct >= benchmarks["roa_floor"] else "WATCH"})
            narrative_points.append(f"RoA of {roa_direct:.2f}%")
        elif roe is not None:
            roa_est = round(roe * 0.08, 2)
            roa_score = min(30.0, (roa_est / benchmarks["roa_floor"]) * 25.0)
            score_components.append(("Return on Assets (RoA)", roa_score, 30.0))
            kpis.append({"name": "Est. Return on Assets (RoA)", "val": f"{roa_est:.2f}%", "benchmark": f"> {benchmarks['roa_floor']}%", "status": "PASS" if roa_est >= benchmarks["roa_floor"] else "WATCH"})
            narrative_points.append(f"est. RoA of {roa_est:.2f}%")
        else:
            kpis.append({"name": "Return on Assets (RoA)", "val": "Not disclosed", "benchmark": f"> {benchmarks['roa_floor']}%", "status": "NEUTRAL"})

        # 2. Capital Multiplier / PBV Valuation
        if pb_ratio is not None:
            pb_score = 30.0 if pb_ratio <= benchmarks["pb_median"] else max(10.0, 30.0 - (pb_ratio - benchmarks["pb_median"]) * 8.0)
            score_components.append(("P/BV Multiple", pb_score, 30.0))
            kpis.append({"name": "Price-to-Book (P/BV)", "val": f"{pb_ratio:.2f}x", "benchmark": f"< {benchmarks['pb_median']}x", "status": "PASS" if pb_ratio <= benchmarks["pb_median"] else "ELEVATED"})
            narrative_points.append(f"P/BV multiple of {pb_ratio:.2f}x")
        else:
            kpis.append({"name": "Price-to-Book (P/BV)", "val": "Not disclosed", "benchmark": f"< {benchmarks['pb_median']}x", "status": "NEUTRAL"})

        # 3. Credit Cycle Resilience
        gnpa = _parse_optional_float(fund.get("gnpa_pct") or fund.get("gnpa"))
        if gnpa is not None:
            credit_score = 25.0 if gnpa <= benchmarks["gnpa_ceiling"] else 12.0
            score_components.append(("Asset Quality Buffer", credit_score, 25.0))
            kpis.append({"name": "Gross NPA (GNPA)", "val": f"{gnpa:.2f}%", "benchmark": f"< {benchmarks['gnpa_ceiling']}%", "status": "PASS" if gnpa <= benchmarks["gnpa_ceiling"] else "WATCH"})
            narrative_points.append(f"GNPA of {gnpa:.2f}%")
        else:
            kpis.append({"name": "Gross NPA (GNPA)", "val": "Not disclosed", "benchmark": f"< {benchmarks['gnpa_ceiling']}%", "status": "NEUTRAL"})

        # 4. Long-Term Franchise Compounding (ROE)
        if roe is not None:
            roe_score = min(15.0, (roe / 14.0) * 15.0)
            score_components.append(("Return on Equity (ROE)", roe_score, 15.0))
            kpis.append({"name": "Return on Equity (ROE)", "val": f"{roe:.1f}%", "benchmark": "> 14.0%", "status": "PASS" if roe >= 14.0 else "WATCH"})
            narrative_points.append(f"ROE of {roe:.1f}%")
        else:
            kpis.append({"name": "Return on Equity (ROE)", "val": "Not disclosed", "benchmark": "> 14.0%", "status": "NEUTRAL"})

        if narrative_points:
            diagnostic_narrative = f"Evaluated on BFSI capital adequacy & underwriting standards with verified {', '.join(narrative_points)}."
        else:
            diagnostic_narrative = "BFSI banking franchise evaluated; awaiting additional statutory balance sheet disclosures."

    elif sector == "IT_TECH":
        # Specialized Technology & SaaS Model
        # 1. Capital Productivity (ROCE)
        if roce is not None:
            roce_score = min(35.0, (roce / benchmarks["roce_floor"]) * 30.0)
            score_components.append(("ROCE Productivity", roce_score, 35.0))
            kpis.append({"name": "ROCE", "val": f"{roce:.1f}%", "benchmark": f"> {benchmarks['roce_floor']}%", "status": "PASS" if roce >= benchmarks["roce_floor"] else "WATCH"})
            narrative_points.append(f"ROCE of {roce:.1f}%")
        else:
            kpis.append({"name": "ROCE", "val": "Not disclosed", "benchmark": f"> {benchmarks['roce_floor']}%", "status": "NEUTRAL"})

        # 2. Solvency & Balance Sheet Cash Cushions
        if debt_equity is not None:
            de_score = 30.0 if debt_equity <= benchmarks["debt_equity_ceiling"] else max(5.0, 30.0 - debt_equity * 40.0)
            score_components.append(("Debt-to-Equity", de_score, 30.0))
            kpis.append({"name": "Debt-to-Equity", "val": f"{debt_equity:.2f}", "benchmark": f"< {benchmarks['debt_equity_ceiling']}", "status": "PASS" if debt_equity <= benchmarks["debt_equity_ceiling"] else "ELEVATED"})
            narrative_points.append(f"D/E of {debt_equity:.2f}")
        else:
            kpis.append({"name": "Debt-to-Equity", "val": "Not disclosed", "benchmark": f"< {benchmarks['debt_equity_ceiling']}", "status": "NEUTRAL"})

        # 3. Free Cash Flow Generation (No hard-coded fallback)
        if fcf_raw is not None:
            fcf_score = 20.0 if fcf_raw >= benchmarks["fcf_conversion_floor"] else 10.0
            score_components.append(("Cash Flow Conversion", fcf_score, 20.0))
            kpis.append({"name": "FCF Conversion Ratio", "val": f"{fcf_raw:.0f}%", "benchmark": f"> {benchmarks['fcf_conversion_floor']}%", "status": "PASS" if fcf_raw >= benchmarks["fcf_conversion_floor"] else "WATCH"})
            narrative_points.append(f"FCF conversion at {fcf_raw:.0f}%")
        else:
            kpis.append({"name": "FCF Conversion Ratio", "val": "Not disclosed", "benchmark": f"> {benchmarks['fcf_conversion_floor']}%", "status": "NEUTRAL"})

        # 4. Growth Visibility
        if sales_growth is not None:
            growth_score = min(15.0, (sales_growth / 12.0) * 15.0)
            score_components.append(("Revenue Momentum", growth_score, 15.0))
            kpis.append({"name": "3-Year Revenue CAGR", "val": f"{sales_growth:.1f}%", "benchmark": "> 12.0%", "status": "PASS" if sales_growth >= 12.0 else "MODERATE"})
            narrative_points.append(f"3-year sales growth of {sales_growth:.1f}%")
        else:
            kpis.append({"name": "3-Year Revenue CAGR", "val": "Not disclosed", "benchmark": "> 12.0%", "status": "NEUTRAL"})

        if narrative_points:
            diagnostic_narrative = f"Evaluated on IT capital efficiency and cash flow metrics with {', '.join(narrative_points)}."
        else:
            diagnostic_narrative = "Evaluated on IT capital efficiency; awaiting additional statutory reporting disclosures."

    elif sector == "CAPITAL_GOODS_INFRA":
        # Capital Goods, Engineering & Manufacturing
        if roce is not None:
            roce_score = min(30.0, (roce / benchmarks["roce_floor"]) * 25.0)
            score_components.append(("ROCE Threshold", roce_score, 30.0))
            kpis.append({"name": "Capital Efficiency (ROCE)", "val": f"{roce:.1f}%", "benchmark": f"> {benchmarks['roce_floor']}%", "status": "PASS" if roce >= benchmarks["roce_floor"] else "WATCH"})
            narrative_points.append(f"ROCE of {roce:.1f}%")
        else:
            kpis.append({"name": "Capital Efficiency (ROCE)", "val": "Not disclosed", "benchmark": f"> {benchmarks['roce_floor']}%", "status": "NEUTRAL"})

        if debt_equity is not None:
            de_score = 30.0 if debt_equity <= benchmarks["debt_equity_ceiling"] else max(5.0, 30.0 - (debt_equity - benchmarks["debt_equity_ceiling"]) * 35.0)
            score_components.append(("Solvency Resilience", de_score, 30.0))
            kpis.append({"name": "Debt-to-Equity", "val": f"{debt_equity:.2f}", "benchmark": f"< {benchmarks['debt_equity_ceiling']}", "status": "PASS" if debt_equity <= benchmarks["debt_equity_ceiling"] else "CAUTION"})
            narrative_points.append(f"D/E of {debt_equity:.2f}")
        else:
            kpis.append({"name": "Debt-to-Equity", "val": "Not disclosed", "benchmark": f"< {benchmarks['debt_equity_ceiling']}", "status": "NEUTRAL"})

        if sales_growth is not None:
            growth_score = min(25.0, (sales_growth / 15.0) * 20.0)
            score_components.append(("Order-Book Execution", growth_score, 25.0))
            kpis.append({"name": "3Y Revenue Growth", "val": f"{sales_growth:.1f}%", "benchmark": "> 15.0%", "status": "PASS" if sales_growth >= 15.0 else "MODERATE"})
            narrative_points.append(f"sales growth of {sales_growth:.1f}%")
        else:
            kpis.append({"name": "3Y Revenue Growth", "val": "Not disclosed", "benchmark": "> 15.0%", "status": "NEUTRAL"})

        if pe_ratio is not None:
            pe_score = 15.0 if pe_ratio <= benchmarks["pe_median"] else max(5.0, 15.0 - (pe_ratio - benchmarks["pe_median"]) * 0.5)
            score_components.append(("Capex Cycle Valuation", pe_score, 15.0))
            kpis.append({"name": "Trailing P/E Multiple", "val": f"{pe_ratio:.1f}x", "benchmark": f"< {benchmarks['pe_median']}x", "status": "PASS" if pe_ratio <= benchmarks["pe_median"] else "ELEVATED"})
            narrative_points.append(f"trailing P/E of {pe_ratio:.1f}x")
        else:
            kpis.append({"name": "Trailing P/E Multiple", "val": "Not disclosed", "benchmark": f"< {benchmarks['pe_median']}x", "status": "NEUTRAL"})

        if narrative_points:
            diagnostic_narrative = f"Assessed on infrastructure and capex upcycle criteria with {', '.join(narrative_points)}."
        else:
            diagnostic_narrative = "Assessed on infrastructure criteria; awaiting statutory segment disclosures."

    else:
        # General Manufacturing / Consumer / Chemicals
        if roce is not None:
            roce_score = min(35.0, (roce / benchmarks["roce_floor"]) * 30.0)
            score_components.append(("ROCE Margin", roce_score, 35.0))
            kpis.append({"name": "ROCE Productivity", "val": f"{roce:.1f}%", "benchmark": f"> {benchmarks['roce_floor']}%", "status": "PASS" if roce >= benchmarks["roce_floor"] else "WATCH"})
            narrative_points.append(f"ROCE of {roce:.1f}%")
        else:
            kpis.append({"name": "ROCE Productivity", "val": "Not disclosed", "benchmark": f"> {benchmarks['roce_floor']}%", "status": "NEUTRAL"})

        if debt_equity is not None:
            de_score = 30.0 if debt_equity <= benchmarks["debt_equity_ceiling"] else max(5.0, 30.0 - debt_equity * 35.0)
            score_components.append(("Debt Burden", de_score, 30.0))
            kpis.append({"name": "Debt-to-Equity", "val": f"{debt_equity:.2f}", "benchmark": f"< {benchmarks['debt_equity_ceiling']}", "status": "PASS" if debt_equity <= benchmarks["debt_equity_ceiling"] else "ELEVATED"})
            narrative_points.append(f"D/E of {debt_equity:.2f}")
        else:
            kpis.append({"name": "Debt-to-Equity", "val": "Not disclosed", "benchmark": f"< {benchmarks['debt_equity_ceiling']}", "status": "NEUTRAL"})

        if sales_growth is not None:
            growth_score = min(20.0, (sales_growth / 12.0) * 18.0)
            score_components.append(("Volume Compounding", growth_score, 20.0))
            kpis.append({"name": "Sales Expansion (3Y)", "val": f"{sales_growth:.1f}%", "benchmark": "> 12.0%", "status": "PASS" if sales_growth >= 12.0 else "MODERATE"})
            narrative_points.append(f"sales growth of {sales_growth:.1f}%")
        else:
            kpis.append({"name": "Sales Expansion (3Y)", "val": "Not disclosed", "benchmark": "> 12.0%", "status": "NEUTRAL"})

        if pe_ratio is not None:
            pe_score = 15.0 if pe_ratio <= benchmarks["pe_median"] else max(5.0, 15.0 - (pe_ratio - benchmarks["pe_median"]) * 0.4)
            score_components.append(("Relative Multiple", pe_score, 15.0))
            kpis.append({"name": "Trailing P/E", "val": f"{pe_ratio:.1f}x", "benchmark": f"< {benchmarks['pe_median']}x", "status": "PASS" if pe_ratio <= benchmarks["pe_median"] else "ELEVATED"})
            narrative_points.append(f"trailing P/E of {pe_ratio:.1f}x")
        else:
            kpis.append({"name": "Trailing P/E", "val": "Not disclosed", "benchmark": f"< {benchmarks['pe_median']}x", "status": "NEUTRAL"})

        if narrative_points:
            diagnostic_narrative = f"Evaluated against peer benchmarks with verified {', '.join(narrative_points)}."
        else:
            diagnostic_narrative = "Evaluated against industry benchmarks; awaiting additional statutory accounting filings."

    # Compute normalized score strictly based on available components
    # If some components are missing, scale proportionally to 100 base without penalizing
    total_earned = sum(s[1] for s in score_components)
    total_max = sum(s[2] for s in score_components)

    if total_max > 0:
        normalized_score = round(max(0.0, min(100.0, (total_earned / total_max) * 100.0)), 1)
    else:
        normalized_score = 50.0  # Neutral baseline when completely unpopulated

    disclosed_count = len(score_components)
    total_kpis = len(kpis)

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
        "sector_display_name": SECTOR_DISPLAY_NAMES.get(sector, sector.replace("_", " ").title()),
        "score": normalized_score,
        "verdict": verdict,
        "badge_color": badge_color,
        "kpis": kpis,
        "narrative": diagnostic_narrative,
        "benchmarks": benchmarks,
        "coverage": f"Based on {disclosed_count} of {total_kpis} metrics",
        "disclosed_count": disclosed_count,
        "total_kpi_count": total_kpis,
    }

