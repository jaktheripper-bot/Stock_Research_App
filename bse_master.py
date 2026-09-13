import os
import json
import re
import requests

CACHE_FILE = "bse_scrips_cache.json"

# Fast-path cache for immediate O(1) resolution without disk/network overhead
PRIMARY_BSE_MAP = {
    # Brand to Corporate Entity Aliases
    "ZOMATO": "543320",
    "ETERNAL": "543320",
    "PAYTM": "543396",
    "ONE97": "543396",
    "ONE97 COMMUNICATIONS": "543396",
    "NYKAA": "543384",
    "FSN E-COMMERCE": "543384",
    "DMART": "540376",
    "AVENUE SUPERMARTS": "540376",
    "POLICYBAZAAR": "543390",
    "PB FINTECH": "543390",
    "DELHIVERY": "543529",

    "JIOFIN": "543940",
    "JIO FINANCIAL": "543940",
    "JIO FINANCIAL SERVICES": "543940",
    "RELIANCE": "500325",
    "TCS": "532540",
    "HDFCBANK": "500180",
    "INFY": "500209",
    "ICICIBANK": "532174",
    "HINDUNILVR": "500696",
    "ITC": "500875",
    "SBIN": "500112",
    "BHARTIARTL": "532454",
    "KOTAKBANK": "500247",
    "LT": "500510",
    "TATAMOTORS": "500570",
    "AXISBANK": "532215",
    "ASIANPAINT": "500820",
    "MARUTI": "532500",
    "SUNPHARMA": "524715",
    "TITAN": "500114",
    "BAJFINANCE": "500034",
    "WIPRO": "507685",
    "HCLTECH": "532281",
    "CDSL": "543265"
}

_MASTER_CACHE = None

def sync_bse_master_list() -> dict:
    """Fetches all 5,000+ active equities directly from BSE India and compiles a lookup dictionary."""
    url = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scrip_code=&industry=&segment=Equity&status=Active"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.bseindia.com/"
    }
    
    cache_payload = {
        "symbols": {},  # Strict ticker symbols: e.g. "ABB": "500002", "TRENT": "500251"
        "names": {}     # Company descriptions: e.g. "ABB INDIA LTD": "500002"
    }

    try:
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code == 200:
            records = res.json()
            if isinstance(records, list):
                for item in records:
                    code = str(item.get("SCRIP_CD", "")).strip()
                    if not (code.isdigit() and len(code) == 6):
                        continue

                    # Exact exchange ticker symbol
                    symbol = str(item.get("scrip_id") or "").strip().upper()
                    if symbol:
                        cache_payload["symbols"][symbol] = code

                    # Common display name
                    scrip_name = str(item.get("Scrip_Name") or "").strip().upper()
                    if scrip_name:
                        cache_payload["names"][scrip_name] = code

                    # Full legal issuer name
                    issuer_name = str(item.get("Issuer_Name") or "").strip().upper()
                    if issuer_name and issuer_name != scrip_name:
                        cache_payload["names"][issuer_name] = code

            if cache_payload["symbols"]:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cache_payload, f)
                return cache_payload
    except Exception as e:
        print(f"Warning: Online BSE master sync failed ({e}).")

    return cache_payload

def _load_master_data() -> dict:
    global _MASTER_CACHE
    if _MASTER_CACHE is not None:
        return _MASTER_CACHE

    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _MASTER_CACHE = json.load(f)
                return _MASTER_CACHE
        except Exception:
            pass

    _MASTER_CACHE = sync_bse_master_list()
    return _MASTER_CACHE

def resolve_bse_scrip_code(query: str) -> str:
    """
    Resolves a query (ticker, company name, or 6-digit code) to an official BSE scrip code.
    Evaluates in order: Direct Code -> Static Map -> Exact Symbol -> Exact Name -> Substring.
    """
    if not query:
        return None

    clean = query.strip().upper().replace(".NS", "").replace(".BO", "")

    # 1. Direct 6-digit scrip code
    if clean.isdigit() and len(clean) == 6:
        return clean

    # 2. Fast-path static memory map
    if clean in PRIMARY_BSE_MAP:
        return PRIMARY_BSE_MAP[clean]

    data = _load_master_data()
    symbols = data.get("symbols", {})
    names = data.get("names", {})

    # 3. Exact ticker symbol match (e.g., "ABB", "TRENT", "ZOMATO")
    if clean in symbols:
        return symbols[clean]

    # 4. Exact company name match
    if clean in names:
        return names[clean]

    # 5. Word-boundary or substring search across company names
    for comp_name, code in names.items():
        if clean in comp_name:
            return code

    return None

if __name__ == "__main__":
    print("Testing bse_master.py resolver...")
    test_queries = [
        "ABB", 
        "TRENT", 
        "ZOMATO", 
        "Hindustan Aeronautics", 
        "HAL", 
        "JIOFIN", 
        "500180", 
        "INVALID_XYZ"
    ]
    for q in test_queries:
        print(f"'{q}' -> Scrip: {resolve_bse_scrip_code(q)}")
