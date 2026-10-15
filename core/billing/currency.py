"""
Multi-Currency Exchange Rate Engine & Location-Aware Billing Adapter.
Provides:
- Benchmark foreign exchange rates against INR (INR, USD, EUR, GBP, AED, SGD, CAD, AUD)
- Cross-border card buffer (3.5%) modeling interchange and banking spreads
- Location detection via request headers (Cloudflare CF-IPCountry) and client fallbacks
- Transparent dual-currency formatting and compliance disclosures
"""

from typing import Dict, Any, Optional
from fastapi import Request


# Supported display currencies with benchmark FX rates vs INR
SUPPORTED_CURRENCIES: Dict[str, Dict[str, Any]] = {
    "INR": {
        "code": "INR",
        "symbol": "₹",
        "name": "Indian Rupee",
        "flag": "🇮🇳",
        "rate_vs_inr": 1.0,
        "is_base": True,
        "buffer_pct": 0.0,
        "symbol_position": "prefix",
    },
    "USD": {
        "code": "USD",
        "symbol": "$",
        "name": "US Dollar",
        "flag": "🇺🇸",
        "rate_vs_inr": 88.50,
        "is_base": False,
        "buffer_pct": 0.035,
        "symbol_position": "prefix",
    },
    "EUR": {
        "code": "EUR",
        "symbol": "€",
        "name": "Euro",
        "flag": "🇪🇺",
        "rate_vs_inr": 96.50,
        "is_base": False,
        "buffer_pct": 0.035,
        "symbol_position": "prefix",
    },
    "GBP": {
        "code": "GBP",
        "symbol": "£",
        "name": "British Pound",
        "flag": "🇬🇧",
        "rate_vs_inr": 115.00,
        "is_base": False,
        "buffer_pct": 0.035,
        "symbol_position": "prefix",
    },
    "AED": {
        "code": "AED",
        "symbol": "AED ",
        "name": "UAE Dirham",
        "flag": "🇦🇪",
        "rate_vs_inr": 24.10,
        "is_base": False,
        "buffer_pct": 0.035,
        "symbol_position": "prefix",
    },
    "SGD": {
        "code": "SGD",
        "symbol": "S$ ",
        "name": "Singapore Dollar",
        "flag": "🇸🇬",
        "rate_vs_inr": 68.00,
        "is_base": False,
        "buffer_pct": 0.035,
        "symbol_position": "prefix",
    },
    "CAD": {
        "code": "CAD",
        "symbol": "CA$ ",
        "name": "Canadian Dollar",
        "flag": "🇨🇦",
        "rate_vs_inr": 64.00,
        "is_base": False,
        "buffer_pct": 0.035,
        "symbol_position": "prefix",
    },
    "AUD": {
        "code": "AUD",
        "symbol": "A$ ",
        "name": "Australian Dollar",
        "flag": "🇦🇺",
        "rate_vs_inr": 58.00,
        "is_base": False,
        "buffer_pct": 0.035,
        "symbol_position": "prefix",
    },
}

# Country code to default currency mapping
COUNTRY_TO_CURRENCY_MAP: Dict[str, str] = {
    "IN": "INR",
    "US": "USD",
    "PR": "USD",
    "GU": "USD",
    "VI": "USD",
    "GB": "GBP",
    "UK": "GBP",
    "AE": "AED",
    "SG": "SGD",
    "CA": "CAD",
    "AU": "AUD",
    # Eurozone
    "DE": "EUR",
    "FR": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "NL": "EUR",
    "BE": "EUR",
    "AT": "EUR",
    "PT": "EUR",
    "FI": "EUR",
    "GR": "EUR",
    "IE": "EUR",
    "LU": "EUR",
    "CY": "EUR",
    "MT": "EUR",
    "SK": "EUR",
    "SI": "EUR",
    "EE": "EUR",
    "LV": "EUR",
    "LT": "EUR",
}


def convert_inr_to_currency(amount_inr: float, currency_code: str = "INR") -> Dict[str, Any]:
    """
    Converts an INR base amount into the target currency.
    Applies the 3.5% cross-border buffer for international transactions.
    """
    clean_code = (currency_code or "INR").strip().upper()
    curr = SUPPORTED_CURRENCIES.get(clean_code, SUPPORTED_CURRENCIES["INR"])

    rate = curr.get("rate_vs_inr", 1.0)
    buffer_pct = curr.get("buffer_pct", 0.0)
    symbol = curr.get("symbol", "₹")

    if curr.get("is_base"):
        effective_amount = round(amount_inr, 2)
        formatted = f"{symbol}{int(effective_amount):,}" if effective_amount.is_integer() else f"{symbol}{effective_amount:,.2f}"
    else:
        # Cost in foreign currency with international cross-border buffer
        raw_foreign = amount_inr / rate
        effective_amount = round(raw_foreign * (1.0 + buffer_pct), 2)
        formatted = f"{symbol}{effective_amount:,.2f}"

    return {
        "amount_inr": amount_inr,
        "currency": clean_code,
        "symbol": symbol,
        "flag": curr.get("flag", "🌐"),
        "name": curr.get("name", clean_code),
        "rate_vs_inr": rate,
        "buffer_pct": buffer_pct,
        "effective_amount": effective_amount,
        "formatted": formatted,
        "is_base": curr.get("is_base", False),
        "notice": (
            f"Prices shown in {clean_code} include an estimated ~{int(buffer_pct*100)}.{int((buffer_pct*1000)%10)}% "
            f"cross-border & banking forex buffer. Final checkout is processed in INR (₹) via secure Razorpay checkout."
            if not curr.get("is_base")
            else "All plans are billed in Indian Rupees (INR) with instant electronic receipts."
        ),
    }


def resolve_currency_for_request(request: Request) -> str:
    """
    Detects the user's currency from cookies, query parameters, or Cloudflare/Proxy IP headers.
    Falls back to 'INR' for domestic or undetectable requests.
    """
    # 1. Explicit query parameter override (e.g. ?currency=USD)
    query_curr = request.query_params.get("currency")
    if query_curr and query_curr.upper() in SUPPORTED_CURRENCIES:
        return query_curr.upper()

    # 2. Cookie preference
    cookie_curr = request.cookies.get("preferred_currency")
    if cookie_curr and cookie_curr.upper() in SUPPORTED_CURRENCIES:
        return cookie_curr.upper()

    # 3. Location detection from headers (Cloudflare, AWS CloudFront, Fastly)
    country = (
        request.headers.get("cf-ipcountry")
        or request.headers.get("x-country-code")
        or request.headers.get("cloudfront-viewer-country")
        or ""
    ).strip().upper()

    if country and country in COUNTRY_TO_CURRENCY_MAP:
        return COUNTRY_TO_CURRENCY_MAP[country]

    return "INR"
