"""
Nifty 100 Index Constituents Registry.

Provides the canonical universe of India's top 100 large-cap and upper mid-cap equities,
complete with BSE scrip codes, official sector categorizations, and lookup utilities.
"""

from typing import List, Dict, Any, Optional

NIFTY_100_CONSTITUENTS: List[Dict[str, Any]] = [
    {"symbol": "RELIANCE", "company_name": "Reliance Industries Ltd", "sector": "Oil Gas & Consumable Fuels", "bse_scrip": "500325"},
    {"symbol": "TCS", "company_name": "Tata Consultancy Services Ltd", "sector": "Information Technology", "bse_scrip": "532540"},
    {"symbol": "HDFCBANK", "company_name": "HDFC Bank Ltd", "sector": "Financial Services", "bse_scrip": "500180"},
    {"symbol": "ICICIBANK", "company_name": "ICICI Bank Ltd", "sector": "Financial Services", "bse_scrip": "532174"},
    {"symbol": "BHARTIARTL", "company_name": "Bharti Airtel Ltd", "sector": "Telecommunication", "bse_scrip": "532454"},
    {"symbol": "SBIN", "company_name": "State Bank of India", "sector": "Financial Services", "bse_scrip": "500112"},
    {"symbol": "INFY", "company_name": "Infosys Ltd", "sector": "Information Technology", "bse_scrip": "500209"},
    {"symbol": "ITC", "company_name": "ITC Ltd", "sector": "Fast Moving Consumer Goods", "bse_scrip": "500875"},
    {"symbol": "LT", "company_name": "Larsen & Toubro Ltd", "sector": "Construction", "bse_scrip": "500510"},
    {"symbol": "HINDUNILVR", "company_name": "Hindustan Unilever Ltd", "sector": "Fast Moving Consumer Goods", "bse_scrip": "500696"},
    {"symbol": "BAJFINANCE", "company_name": "Bajaj Finance Ltd", "sector": "Financial Services", "bse_scrip": "500034"},
    {"symbol": "MARUTI", "company_name": "Maruti Suzuki India Ltd", "sector": "Automobile and Auto Components", "bse_scrip": "532500"},
    {"symbol": "HCLTECH", "company_name": "HCL Technologies Ltd", "sector": "Information Technology", "bse_scrip": "532281"},
    {"symbol": "SUNPHARMA", "company_name": "Sun Pharmaceutical Industries Ltd", "sector": "Healthcare", "bse_scrip": "524715"},
    {"symbol": "M&M", "company_name": "Mahindra & Mahindra Ltd", "sector": "Automobile and Auto Components", "bse_scrip": "500520"},
    {"symbol": "TATAMOTORS", "company_name": "Tata Motors Ltd", "sector": "Automobile and Auto Components", "bse_scrip": "500570"},
    {"symbol": "KOTAKBANK", "company_name": "Kotak Mahindra Bank Ltd", "sector": "Financial Services", "bse_scrip": "500247"},
    {"symbol": "AXISBANK", "company_name": "Axis Bank Ltd", "sector": "Financial Services", "bse_scrip": "532215"},
    {"symbol": "NTPC", "company_name": "NTPC Ltd", "sector": "Power", "bse_scrip": "532555"},
    {"symbol": "TITAN", "company_name": "Titan Company Ltd", "sector": "Consumer Durables", "bse_scrip": "500114"},
    {"symbol": "ONGC", "company_name": "Oil & Natural Gas Corporation Ltd", "sector": "Oil Gas & Consumable Fuels", "bse_scrip": "500312"},
    {"symbol": "POWERGRID", "company_name": "Power Grid Corporation of India Ltd", "sector": "Power", "bse_scrip": "532898"},
    {"symbol": "ADANIENT", "company_name": "Adani Enterprises Ltd", "sector": "Metals & Mining", "bse_scrip": "512599"},
    {"symbol": "ADANIPORTS", "company_name": "Adani Ports and Special Economic Zone Ltd", "sector": "Services", "bse_scrip": "532921"},
    {"symbol": "COALINDIA", "company_name": "Coal India Ltd", "sector": "Oil Gas & Consumable Fuels", "bse_scrip": "533278"},
    {"symbol": "BAJAJFINSV", "company_name": "Bajaj Finserv Ltd", "sector": "Financial Services", "bse_scrip": "532978"},
    {"symbol": "ASIANPAINT", "company_name": "Asian Paints Ltd", "sector": "Consumer Durables", "bse_scrip": "500820"},
    {"symbol": "ULTRACEMCO", "company_name": "UltraTech Cement Ltd", "sector": "Construction Materials", "bse_scrip": "532538"},
    {"symbol": "TATASTEEL", "company_name": "Tata Steel Ltd", "sector": "Metals & Mining", "bse_scrip": "500470"},
    {"symbol": "SIEMENS", "company_name": "Siemens Ltd", "sector": "Capital Goods", "bse_scrip": "500550"},
    {"symbol": "JSWSTEEL", "company_name": "JSW Steel Ltd", "sector": "Metals & Mining", "bse_scrip": "500228"},
    {"symbol": "GRASIM", "company_name": "Grasim Industries Ltd", "sector": "Construction Materials", "bse_scrip": "500300"},
    {"symbol": "BEL", "company_name": "Bharat Electronics Ltd", "sector": "Capital Goods", "bse_scrip": "500049"},
    {"symbol": "VBL", "company_name": "Varun Beverages Ltd", "sector": "Fast Moving Consumer Goods", "bse_scrip": "540180"},
    {"symbol": "HAL", "company_name": "Hindustan Aeronautics Ltd", "sector": "Capital Goods", "bse_scrip": "541154"},
    {"symbol": "NESTLEIND", "company_name": "Nestle India Ltd", "sector": "Fast Moving Consumer Goods", "bse_scrip": "500790"},
    {"symbol": "TRENT", "company_name": "Trent Ltd", "sector": "Consumer Services", "bse_scrip": "500251"},
    {"symbol": "DLF", "company_name": "DLF Ltd", "sector": "Realty", "bse_scrip": "532868"},
    {"symbol": "ZOMATO", "company_name": "Zomato Ltd", "sector": "Consumer Services", "bse_scrip": "543320"},
    {"symbol": "IOC", "company_name": "Indian Oil Corporation Ltd", "sector": "Oil Gas & Consumable Fuels", "bse_scrip": "530965"},
    {"symbol": "TECHM", "company_name": "Tech Mahindra Ltd", "sector": "Information Technology", "bse_scrip": "532755"},
    {"symbol": "INDUSINDBK", "company_name": "IndusInd Bank Ltd", "sector": "Financial Services", "bse_scrip": "532187"},
    {"symbol": "HINDALCO", "company_name": "Hindalco Industries Ltd", "sector": "Metals & Mining", "bse_scrip": "500440"},
    {"symbol": "BRITANNIA", "company_name": "Britannia Industries Ltd", "sector": "Fast Moving Consumer Goods", "bse_scrip": "500825"},
    {"symbol": "CIPLA", "company_name": "Cipla Ltd", "sector": "Healthcare", "bse_scrip": "500087"},
    {"symbol": "BPCL", "company_name": "Bharat Petroleum Corporation Ltd", "sector": "Oil Gas & Consumable Fuels", "bse_scrip": "500547"},
    {"symbol": "APOLLOHOSP", "company_name": "Apollo Hospitals Enterprise Ltd", "sector": "Healthcare", "bse_scrip": "508869"},
    {"symbol": "EICHERMOT", "company_name": "Eicher Motors Ltd", "sector": "Automobile and Auto Components", "bse_scrip": "505200"},
    {"symbol": "DRREDDY", "company_name": "Dr. Reddy's Laboratories Ltd", "sector": "Healthcare", "bse_scrip": "500124"},
    {"symbol": "TATACONSUM", "company_name": "Tata Consumer Products Ltd", "sector": "Fast Moving Consumer Goods", "bse_scrip": "500800"},
    {"symbol": "DIVISLAB", "company_name": "Divi's Laboratories Ltd", "sector": "Healthcare", "bse_scrip": "532488"},
    {"symbol": "CHOLAFIN", "company_name": "Cholamandalam Investment and Finance Company Ltd", "sector": "Financial Services", "bse_scrip": "511243"},
    {"symbol": "TVSMOTOR", "company_name": "TVS Motor Company Ltd", "sector": "Automobile and Auto Components", "bse_scrip": "532343"},
    {"symbol": "SHREECEM", "company_name": "Shree Cement Ltd", "sector": "Construction Materials", "bse_scrip": "500387"},
    {"symbol": "HAVELLS", "company_name": "Havells India Ltd", "sector": "Consumer Durables", "bse_scrip": "517354"},
    {"symbol": "PIDILITIND", "company_name": "Pidilite Industries Ltd", "sector": "Chemicals", "bse_scrip": "500331"},
    {"symbol": "GAIL", "company_name": "GAIL (India) Ltd", "sector": "Oil Gas & Consumable Fuels", "bse_scrip": "532155"},
    {"symbol": "AMBUJACEM", "company_name": "Ambuja Cements Ltd", "sector": "Construction Materials", "bse_scrip": "500425"},
    {"symbol": "ABB", "company_name": "ABB India Ltd", "sector": "Capital Goods", "bse_scrip": "500002"},
    {"symbol": "BANKBARODA", "company_name": "Bank of Baroda", "sector": "Financial Services", "bse_scrip": "532134"},
    {"symbol": "PNB", "company_name": "Punjab National Bank", "sector": "Financial Services", "bse_scrip": "532461"},
    {"symbol": "CANBK", "company_name": "Canara Bank", "sector": "Financial Services", "bse_scrip": "532483"},
    {"symbol": "UNIONBANK", "company_name": "Union Bank of India", "sector": "Financial Services", "bse_scrip": "532477"},
    {"symbol": "JIOFIN", "company_name": "Jio Financial Services Ltd", "sector": "Financial Services", "bse_scrip": "543940"},
    {"symbol": "RECLTD", "company_name": "REC Ltd", "sector": "Financial Services", "bse_scrip": "532955"},
    {"symbol": "PFC", "company_name": "Power Finance Corporation Ltd", "sector": "Financial Services", "bse_scrip": "532810"},
    {"symbol": "CGPOWER", "company_name": "CG Power and Industrial Solutions Ltd", "sector": "Capital Goods", "bse_scrip": "500093"},
    {"symbol": "BDL", "company_name": "Bharat Dynamics Ltd", "sector": "Capital Goods", "bse_scrip": "541143"},
    {"symbol": "POLYCAB", "company_name": "Polycab India Ltd", "sector": "Consumer Durables", "bse_scrip": "542652"},
    {"symbol": "PERSISTENT", "company_name": "Persistent Systems Ltd", "sector": "Information Technology", "bse_scrip": "533179"},
    {"symbol": "COFORGE", "company_name": "Coforge Ltd", "sector": "Information Technology", "bse_scrip": "532541"},
    {"symbol": "MPHASIS", "company_name": "Mphasis Ltd", "sector": "Information Technology", "bse_scrip": "526299"},
    {"symbol": "LTIM", "company_name": "LTIMindtree Ltd", "sector": "Information Technology", "bse_scrip": "540005"},
    {"symbol": "MAXHEALTH", "company_name": "Max Healthcare Institute Ltd", "sector": "Healthcare", "bse_scrip": "543220"},
    {"symbol": "MANKIND", "company_name": "Mankind Pharma Ltd", "sector": "Healthcare", "bse_scrip": "543904"},
    {"symbol": "TORNTPHARM", "company_name": "Torrent Pharmaceuticals Ltd", "sector": "Healthcare", "bse_scrip": "500420"},
    {"symbol": "LUPIN", "company_name": "Lupin Ltd", "sector": "Healthcare", "bse_scrip": "500257"},
    {"symbol": "AUROPHARMA", "company_name": "Aurobindo Pharma Ltd", "sector": "Healthcare", "bse_scrip": "524804"},
    {"symbol": "ALKEM", "company_name": "Alkem Laboratories Ltd", "sector": "Healthcare", "bse_scrip": "539523"},
    {"symbol": "BHARATFORG", "company_name": "Bharat Forge Ltd", "sector": "Automobile and Auto Components", "bse_scrip": "500493"},
    {"symbol": "CUMMINSIND", "company_name": "Cummins India Ltd", "sector": "Capital Goods", "bse_scrip": "500480"},
    {"symbol": "BOSCHLTD", "company_name": "Bosch Ltd", "sector": "Automobile and Auto Components", "bse_scrip": "500530"},
    {"symbol": "MOTHERSON", "company_name": "Samvardhana Motherson International Ltd", "sector": "Automobile and Auto Components", "bse_scrip": "517334"},
    {"symbol": "HEROMOTOCO", "company_name": "Hero MotoCorp Ltd", "sector": "Automobile and Auto Components", "bse_scrip": "500182"},
    {"symbol": "BALKRISIND", "company_name": "Balkrishna Industries Ltd", "sector": "Automobile and Auto Components", "bse_scrip": "502355"},
    {"symbol": "GODREJCP", "company_name": "Godrej Consumer Products Ltd", "sector": "Fast Moving Consumer Goods", "bse_scrip": "532424"},
    {"symbol": "DABUR", "company_name": "Dabur India Ltd", "sector": "Fast Moving Consumer Goods", "bse_scrip": "500096"},
    {"symbol": "MARICO", "company_name": "Marico Ltd", "sector": "Fast Moving Consumer Goods", "bse_scrip": "531642"},
    {"symbol": "COLPAL", "company_name": "Colgate-Palmolive (India) Ltd", "sector": "Fast Moving Consumer Goods", "bse_scrip": "500830"},
    {"symbol": "BERGEPAINT", "company_name": "Berger Paints India Ltd", "sector": "Consumer Durables", "bse_scrip": "509480"},
    {"symbol": "SRF", "company_name": "SRF Ltd", "sector": "Chemicals", "bse_scrip": "503806"},
    {"symbol": "PIIND", "company_name": "PI Industries Ltd", "sector": "Chemicals", "bse_scrip": "523642"},
    {"symbol": "DEEPAKNTR", "company_name": "Deepak Nitrite Ltd", "sector": "Chemicals", "bse_scrip": "506401"},
    {"symbol": "TATACOMM", "company_name": "Tata Communications Ltd", "sector": "Telecommunication", "bse_scrip": "500483"},
    {"symbol": "INDIGO", "company_name": "InterGlobe Aviation Ltd", "sector": "Services", "bse_scrip": "539448"},
    {"symbol": "DMART", "company_name": "Avenue Supermarts Ltd", "sector": "Consumer Services", "bse_scrip": "540376"},
    {"symbol": "NAUKRI", "company_name": "Info Edge (India) Ltd", "sector": "Consumer Services", "bse_scrip": "532777"},
    {"symbol": "MUTHOOTFIN", "company_name": "Muthoot Finance Ltd", "sector": "Financial Services", "bse_scrip": "533398"},
    {"symbol": "FEDERALBNK", "company_name": "The Federal Bank Ltd", "sector": "Financial Services", "bse_scrip": "500469"},
    {"symbol": "VOLTAS", "company_name": "Voltas Ltd", "sector": "Consumer Durables", "bse_scrip": "500575"}
]

_LOOKUP_BY_SYMBOL = {item["symbol"]: item for item in NIFTY_100_CONSTITUENTS}

def get_nifty100_symbols() -> List[str]:
    """Returns list of canonical symbols for all 100 constituent equities."""
    return [item["symbol"] for item in NIFTY_100_CONSTITUENTS]

def get_nifty100_constituent(symbol: str) -> Optional[Dict[str, Any]]:
    """Returns metadata dictionary for a specific Nifty 100 constituent."""
    return _LOOKUP_BY_SYMBOL.get(symbol.strip().upper())

def is_nifty100_stock(symbol: str) -> bool:
    """Checks whether a given ticker belongs to the Nifty 100 universe."""
    return symbol.strip().upper() in _LOOKUP_BY_SYMBOL
