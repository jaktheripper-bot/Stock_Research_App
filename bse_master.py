import os
import csv
import io
import requests

BSE_CSV_PATH = "bse_equity_master.csv"

# Pre-compiled high-frequency scrip map for immediate fallback
PRIMARY_BSE_MAP = {
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

def update_bse_master_csv() -> bool:
    """Fetches the official BSE Equity master list and saves it locally."""
    url = "https://www.bseindia.com/corporates/List_Scrips.aspx"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    try:
        # BSE endpoint serving the active equity CSV
        download_url = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scrip_code=&industry=&segment=Equity&status=Active"
        res = requests.get(download_url, headers=headers, timeout=10)
        if res.status_code == 200 and len(res.content) > 1000:
            with open(BSE_CSV_PATH, "wb") as f:
                f.write(res.content)
            return True
    except Exception as e:
        print(f"Warning: Online BSE master fetch failed ({e}). Using local lookup.")
    return False

def resolve_bse_scrip_code(query: str) -> str:
    """
    Resolves a ticker symbol or company name into a valid 6-digit BSE scrip code.
    Returns the code as a string, or None if unresolved.
    """
    clean = query.strip().upper().replace(".NS", "").replace(".BO", "")
    
    # Direct numeric code check
    if clean.isdigit() and len(clean) == 6:
        return clean
        
    # Check static fast cache
    if clean in PRIMARY_BSE_MAP:
        return PRIMARY_BSE_MAP[clean]
        
    # Check local CSV if present
    if os.path.exists(BSE_CSV_PATH):
        try:
            with open(BSE_CSV_PATH, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row.get("Scrip Id", "").strip().upper()
                    name = row.get("Scrip Name", "").strip().upper()
                    code = row.get("Scrip Code", "").strip()
                    if clean == symbol or clean in name:
                        return code
        except Exception:
            pass
            
    return None

if __name__ == "__main__":
    test_queries = ["TATAMOTORS", "500325", "INFY", "CDSL", "INVALID_STOCK"]
    for q in test_queries:
        print(f"Query: {q} -> Scrip Code: {resolve_bse_scrip_code(q)}")
