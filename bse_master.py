import os
import re
import json
import difflib
from normalizer import clean_ticker

PRIMARY_BSE_MAP = {
    "ONIDA": "500279",
    "MIRC": "500279",
    "MIRC ELECTRONICS": "500279",
    "ZOMATO": "543320", "ETERNAL": "543320", "PAYTM": "543396", "ONE97": "543396",
    "NYKAA": "543384", "DMART": "540376", "POLICYBAZAAR": "543390", "DELHIVERY": "543529",
    "JIOFIN": "543940", "RELIANCE": "500325", "TCS": "532540", "HDFCBANK": "500180",
    "INFY": "500209", "ICICIBANK": "532174", "ITC": "500875", "SBIN": "500112",
    "TATAMOTORS": "500570", "OLAELEC": "544225", "ATHERENERGY": "544397",
    "WIPRO": "507685", "HCL": "532281", "HCLTECH": "532281", "HCL TECHNOLOGIES": "532281",
    "BHARTIARTL": "532454", "AIRTEL": "532454", "LT": "500510", "LARSEN": "500510",
    "KOTAKBANK": "500247", "KOTAK": "500247", "AXISBANK": "532215", "MARUTI": "532500",
    "TITAN": "500114", "SUNPHARMA": "524715", "TATASTEEL": "500470"
}

_ALIASES_CACHE = {"data": None, "mtime": 0}
_SCRIPS_CACHE = {"data": None, "mtime": 0}
_SUGGESTION_CANDIDATES = {"list": [], "scrips_mtime": -1, "alias_mtime": -1}

def get_dynamic_aliases() -> dict:
    """Loads and caches dynamic_aliases.json in-memory with file mtime validation."""
    path = "dynamic_aliases.json"
    if not os.path.exists(path):
        return {}
    try:
        mtime = os.path.getmtime(path)
        if _ALIASES_CACHE["data"] is not None and _ALIASES_CACHE["mtime"] == mtime:
            return _ALIASES_CACHE["data"]
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            _ALIASES_CACHE["data"] = data
            _ALIASES_CACHE["mtime"] = mtime
            return data
    except Exception:
        return _ALIASES_CACHE["data"] or {}

def get_bse_scrips_cache() -> dict:
    """Loads and caches bse_scrips_cache.json in-memory with file mtime validation."""
    path = "bse_scrips_cache.json"
    if not os.path.exists(path):
        return {}
    try:
        mtime = os.path.getmtime(path)
        if _SCRIPS_CACHE["data"] is not None and _SCRIPS_CACHE["mtime"] == mtime:
            return _SCRIPS_CACHE["data"]
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            _SCRIPS_CACHE["data"] = data
            _SCRIPS_CACHE["mtime"] = mtime
            return data
    except Exception:
        return _SCRIPS_CACHE["data"] or {}


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

def _get_active_flash_model(client) -> str:
    """Discovers active Gemini Flash model with graceful fallback."""
    try:
        from analyzer import get_latest_flash_models
        models = get_latest_flash_models(client)
        if models:
            return models[0]
    except Exception:
        pass
    return "gemini-2.5-flash"

def resolve_scrip_via_gemini_jit(query: str) -> str:
    """
    Tier 5: Just-In-Time Gemini Grounded Search.
    Discovers official 6-digit BSE scrip codes for newly listed IPOs or unindexed companies.
    """
    try:
        from google import genai
        from core.config import get_secret
        api_key = get_secret("GEMINI_API_KEY")
        if not api_key:
            return None

        client = genai.Client(api_key=api_key)
        prompt = (
            f"What is the official 6-digit BSE (Bombay Stock Exchange) security/scrip code for '{query}'? "
            "Reply strictly with only the 6-digit number. If not found, reply N/A."
        )
        model_name = _get_active_flash_model(client)
        chat = client.chats.create(
            model=model_name,
            config=genai.types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                temperature=0.0
            )
        )
        response = chat.send_message(prompt)
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
                aliases[clean_ticker(query)] = code
                with open("dynamic_aliases.json", "w", encoding="utf-8") as f:
                    json.dump(aliases, f, indent=2)
                _ALIASES_CACHE["mtime"] = 0
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

    clean = clean_ticker(query)

    # 1. Direct 6-digit code
    if clean.isdigit() and len(clean) == 6:
        return clean

    # 2. Dynamic aliases
    dyn = get_dynamic_aliases()
    if clean in dyn:
        return str(dyn[clean]).strip()

    # 3. In-memory fast path
    if clean in PRIMARY_BSE_MAP:
        return PRIMARY_BSE_MAP[clean]

    # Supabase Stored Procedure
    scrip_from_db = resolve_scrip_from_supabase(clean)
    if scrip_from_db:
        return scrip_from_db

    # 4. Local master cache fallback (offline universe)
    cached = get_bse_scrips_cache()
    if cached:
        symbols = cached.get("symbols", {})
        names = cached.get("names", {})
        if clean in symbols:
            return symbols[clean]
        if clean in names:
            return names[clean]
        pattern = re.compile(rf"\b{re.escape(clean)}\b", re.IGNORECASE)
        for comp_name, code in names.items():
            if pattern.search(comp_name):
                return code

    # 5. Just-In-Time Gemini Grounded Search
    jit_code = resolve_scrip_via_gemini_jit(clean)
    if jit_code:
        return jit_code

    return None

def resolve_canonical_symbol(query: str) -> str:
    """Resolves an alias or scrip code to its canonical exchange ticker symbol (e.g. 'HCL' or '532281' -> 'HCLTECH')."""
    if not query:
        return ""
    clean = clean_ticker(query)
    scrip = resolve_bse_scrip_code(clean)
    if not scrip:
        return clean
    cached = get_bse_scrips_cache()
    if cached:
        symbols = cached.get("symbols", {})
        for sym, code in symbols.items():
            if str(code).strip() == str(scrip).strip():
                return sym
    return clean

def _get_cached_candidates() -> list:
    scrips_mtime = _SCRIPS_CACHE.get("mtime", 0)
    alias_mtime = _ALIASES_CACHE.get("mtime", 0)
    if (
        _SUGGESTION_CANDIDATES["list"]
        and _SUGGESTION_CANDIDATES["scrips_mtime"] == scrips_mtime
        and _SUGGESTION_CANDIDATES["alias_mtime"] == alias_mtime
    ):
        return _SUGGESTION_CANDIDATES["list"]

    candidates = set(PRIMARY_BSE_MAP.keys())
    dyn = get_dynamic_aliases()
    if dyn:
        candidates.update(dyn.keys())

    cached = get_bse_scrips_cache()
    if cached:
        symbols = cached.get("symbols", {})
        names = cached.get("names", {})
        candidates.update(symbols.keys())
        candidates.update(names.keys())

    cand_list = list(candidates)
    _SUGGESTION_CANDIDATES["list"] = cand_list
    _SUGGESTION_CANDIDATES["scrips_mtime"] = _SCRIPS_CACHE.get("mtime", 0)
    _SUGGESTION_CANDIDATES["alias_mtime"] = _ALIASES_CACHE.get("mtime", 0)
    return cand_list

def get_ticker_suggestions(query: str, n: int = 3) -> list:
    """Finds closest matching ticker symbols or company names using fuzzy string matching."""
    if not query:
        return []
    clean = clean_ticker(query)
    candidates = _get_cached_candidates()
    return difflib.get_close_matches(clean, candidates, n=n, cutoff=0.5)
