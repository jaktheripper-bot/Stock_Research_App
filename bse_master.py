import os
import re
import json

PRIMARY_BSE_MAP = {
    "ZOMATO": "543320", "ETERNAL": "543320", "PAYTM": "543396", "ONE97": "543396",
    "NYKAA": "543384", "DMART": "540376", "POLICYBAZAAR": "543390", "DELHIVERY": "543529",
    "JIOFIN": "543940", "RELIANCE": "500325", "TCS": "532540", "HDFCBANK": "500180",
    "INFY": "500209", "ICICIBANK": "532174", "ITC": "500875", "SBIN": "500112",
    "TATAMOTORS": "500570", "OLAELEC": "544225", "ATHERENERGY": "544397"
}

def resolve_scrip_from_supabase(query: str) -> str:
    """Queries Supabase bse_scrip_master via resolve_scrip() stored procedure."""
    try:
        from db import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT scrip_code FROM resolve_scrip(%s);", (query.strip(),))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception:
        pass
    return None

def resolve_bse_scrip_code(query: str) -> str:
    """
    Resolution Cascade:
    1. Direct 6-digit numeric check.
    2. Primary in-memory fast path.
    3. Supabase trigram & alias resolution (resolve_scrip RPC).
    4. Local master cache fallback.
    """
    if not query:
        return None

    clean = query.strip().upper().replace(".NS", "").replace(".BO", "")

    # 1. Direct code
    if clean.isdigit() and len(clean) == 6:
        return clean

    # 2. In-memory fast path
    if clean in PRIMARY_BSE_MAP:
        return PRIMARY_BSE_MAP[clean]

    # 3. Supabase Stored Procedure
    scrip_from_db = resolve_scrip_from_supabase(clean)
    if scrip_from_db:
        return scrip_from_db

    # 4. Local master cache fallback (offline mode)
    if os.path.exists("bse_scrips_cache.json"):
        try:
            with open("bse_scrips_cache.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                symbols = data.get("symbols", {})
                names = data.get("names", {})
                if clean in symbols:
                    return symbols[clean]
                if clean in names:
                    return names[clean]
                pattern = re.compile(rf"\b{re.escape(clean)}\b", re.IGNORECASE)
                for comp_name, code in names.items():
                    if pattern.search(comp_name):
                        return code
        except Exception:
            pass

    return None
