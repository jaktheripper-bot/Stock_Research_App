import os
import json
import requests
import toml
from google import genai

CACHE_FILE = "bse_scrips_cache.json"
DYNAMIC_ALIASES_FILE = "dynamic_aliases.json"

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
    "CDSL": "543265",
    "ABB": "500002",
    "TRENT": "500251",
    "HAL": "541154",
    "BEL": "500049"
}

_MASTER_CACHE = None

def get_dynamic_aliases() -> dict:
    if os.path.exists(DYNAMIC_ALIASES_FILE):
        try:
            with open(DYNAMIC_ALIASES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_dynamic_alias(query: str, scrip_code: str):
    aliases = get_dynamic_aliases()
    aliases[query.strip().upper()] = str(scrip_code).strip()
    with open(DYNAMIC_ALIASES_FILE, "w", encoding="utf-8") as f:
        json.dump(aliases, f, indent=2)

def discover_scrip_with_ai(query: str) -> str:
    """Uses Gemini Grounding to locate renamed or unmapped BSE scrip codes, verified against BSE."""
    try:
        secrets_path = ".streamlit/secrets.toml"
        if not os.path.exists(secrets_path):
            return None
        secrets = toml.load(secrets_path)
        api_key = secrets.get("GEMINI_API_KEY")
        if not api_key:
            return None

        client = genai.Client(api_key=api_key)
        prompt = (
            f"What is the official 6-digit BSE (Bombay Stock Exchange) scrip code for '{query}'? "
            "If the company was renamed, merged, or listed under a holding entity, find that new active scrip code. "
            "Respond ONLY with a JSON object: {\"scrip_code\": \"XXXXXX\", \"company_name\": \"...\"}."
        )
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                temperature=0.0
            )
        )
        text = response.text.replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end != 0:
            data = json.loads(text[start:end])
            candidate = str(data.get("scrip_code", "")).strip()
            if candidate.isdigit() and len(candidate) == 6:
                from bsedata.bse import BSE
                b = BSE(update_codes=False)
                quote = b.getQuote(candidate)
                if quote and quote.get("currentValue"):
                    save_dynamic_alias(query, candidate)
                    return candidate
    except Exception as e:
        print(f"JIT discovery error for {query}: {e}")
    return None

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
    return {"symbols": {}, "names": {}}

def resolve_bse_scrip_code(query: str) -> str:
    if not query:
        return None
    clean = query.strip().upper().replace(".NS", "").replace(".BO", "")

    # 1. Direct 6-digit code
    if clean.isdigit() and len(clean) == 6:
        return clean

    # 2. Dynamic Learned Aliases
    dynamic = get_dynamic_aliases()
    if clean in dynamic:
        return dynamic[clean]

    # 3. Static High-Frequency Map
    if clean in PRIMARY_BSE_MAP:
        return PRIMARY_BSE_MAP[clean]

    # 4. Master Universe Cache
    data = _load_master_data()
    symbols = data.get("symbols", {})
    names = data.get("names", {})
    if clean in symbols:
        return symbols[clean]
    if clean in names:
        return names[clean]
    for comp_name, code in names.items():
        if clean in comp_name:
            return code

    # 5. JIT AI Discovery with Exchange Verification
    discovered = discover_scrip_with_ai(query)
    if discovered:
        return discovered

    return None
