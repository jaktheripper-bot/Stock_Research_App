import os
import re
import json
import difflib

PRIMARY_BSE_MAP = {
    "ONIDA": "500279",
    "MIRC": "500279",
    "MIRC ELECTRONICS": "500279",
    "ZOMATO": "543320", "ETERNAL": "543320", "PAYTM": "543396", "ONE97": "543396",
    "NYKAA": "543384", "DMART": "540376", "POLICYBAZAAR": "543390", "DELHIVERY": "543529",
    "JIOFIN": "543940", "RELIANCE": "500325", "TCS": "532540", "HDFCBANK": "500180",
    "INFY": "500209", "ICICIBANK": "532174", "ITC": "500875", "SBIN": "500112",
    "TATAMOTORS": "500570", "OLAELEC": "544225", "ATHERENERGY": "544397"
}

def find_fuzzy_scrip_match(query: str, cutoff: float = 0.72) -> str:
    """Matches typographical errors against known scrips and aliases using Levenshtein similarity."""
    if not query:
        return None
    clean_q = query.strip().upper()
    
    # Check similarity against PRIMARY_BSE_MAP keys
    candidates = list(PRIMARY_BSE_MAP.keys())
    matches = difflib.get_close_matches(clean_q, candidates, n=1, cutoff=cutoff)
    if matches:
        return PRIMARY_BSE_MAP[matches[0]]
        
    # Check similarity against dynamic aliases if file exists
    if os.path.exists("dynamic_aliases.json"):
        try:
            with open("dynamic_aliases.json", "r", encoding="utf-8") as f:
                dyn = json.load(f)
                dyn_matches = difflib.get_close_matches(clean_q, list(dyn.keys()), n=1, cutoff=cutoff)
                if dyn_matches:
                    return dyn[dyn_matches[0]]
        except Exception:
            pass
        
    return None

def resolve_scrip_from_supabase(query: str) -> str:
    """Queries Supabase bse_scrip_master via resolve_scrip() stored procedure."""
    conn = None
    cur = None
    try:
        from db import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT scrip_code FROM resolve_scrip(%s);", (query.strip(),))
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception:
        pass
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return None

def resolve_scrip_via_gemini_jit(query: str) -> str:
    """
    Tier 5: Just-In-Time Gemini Grounded Search.
    Discovers official 6-digit BSE scrip codes for newly listed IPOs or unindexed companies.
    """
    try:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("GEMINI_API_KEY")
            except Exception:
                pass
        if not api_key:
            return None

        client = genai.Client(api_key=api_key)
        prompt = (
            f"What is the official 6-digit BSE (Bombay Stock Exchange) security/scrip code for '{query}'? "
            "Reply strictly with only the 6-digit number. If not found, reply N/A."
        )
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                temperature=0.0
            )
        )
        text = response.text if hasattr(response, "text") and response.text else ""
        match = re.search(r"\b(5\d{5})\b", text)
        if match:
            code = match.group(1)
            # Persist to dynamic_aliases.json for fast Tier-2 resolution on subsequent queries
            try:
                aliases = {}
                if os.path.exists("dynamic_aliases.json"):
                    with open("dynamic_aliases.json", "r", encoding="utf-8") as f:
                        aliases = json.load(f)
                aliases[query.strip().upper()] = code
                with open("dynamic_aliases.json", "w", encoding="utf-8") as f:
                    json.dump(aliases, f, indent=2)
            except Exception:
                pass
            return code
    except Exception:
        pass
    return None

def resolve_bse_scrip_code(query: str) -> str:
    """
    5-Tier BSE Resolution Hierarchy:
    1. Direct 6-digit numeric check.
    2. Dynamic aliases (dynamic_aliases.json).
    3. Static PRIMARY_BSE_MAP and Supabase master universe (resolve_scrip RPC).
    4. Active Master Universe local cache (bse_scrips_cache.json).
    5. Just-In-Time Gemini Grounded Search.
    """
    if not query:
        return None

    clean = query.strip().upper().replace(".NS", "").replace(".BO", "")

    # 1. Direct 6-digit code
    if clean.isdigit() and len(clean) == 6:
        return clean

    # 2. Dynamic aliases
    if os.path.exists("dynamic_aliases.json"):
        try:
            with open("dynamic_aliases.json", "r", encoding="utf-8") as f:
                dyn = json.load(f)
                if clean in dyn:
                    return str(dyn[clean]).strip()
        except Exception:
            pass

    # 3. In-memory fast path
    if clean in PRIMARY_BSE_MAP:
        return PRIMARY_BSE_MAP[clean]

    # Supabase Stored Procedure
    scrip_from_db = resolve_scrip_from_supabase(clean)
    if scrip_from_db:
        return scrip_from_db

    # 4. Local master cache fallback (offline universe)
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

    # 5. Just-In-Time Gemini Grounded Search
    jit_code = resolve_scrip_via_gemini_jit(clean)
    if jit_code:
        return jit_code

    return None

def get_ticker_suggestions(query: str, n: int = 3) -> list:
    """Finds closest matching ticker symbols or company names using fuzzy string matching."""
    if not query:
        return []
    clean = query.strip().upper()
    candidates = list(PRIMARY_BSE_MAP.keys())

    if os.path.exists("dynamic_aliases.json"):
        try:
            with open("dynamic_aliases.json", "r", encoding="utf-8") as f:
                dyn = json.load(f)
                candidates.extend(list(dyn.keys()))
        except Exception:
            pass

    if os.path.exists("bse_scrips_cache.json"):
        try:
            with open("bse_scrips_cache.json", "r", encoding="utf-8") as f:
                cached = json.load(f)
                symbols = cached.get("symbols", {})
                names = cached.get("names", {})
                candidates.extend(list(symbols.keys()))
                candidates.extend(list(names.keys()))
        except Exception:
            pass

    matches = difflib.get_close_matches(clean, list(set(candidates)), n=n, cutoff=0.5)
    return matches
