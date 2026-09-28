from ui.formatters import format_inr

def clean_ticker(raw: str) -> str:
    """Normalize stock ticker by stripping whitespace, uppercase, and removing exchange suffixes (.NS, .BO)."""
    if not raw:
        return ""
    return str(raw).strip().upper().replace(".NS", "").replace(".BO", "")

def format_indian_currency(val) -> str:
    """Formats numeric INR values using standard Indian numbering system (Lakhs / Crores)."""
    return format_inr(val)

def normalize_stock_data(raw_data: dict, exchange: str = "NSE") -> dict:
    normalized = raw_data.copy()
    raw_mcap = raw_data.get("market_cap")
    
    if exchange in ["NSE", "BSE", "NSEI", "BOM"]:
        normalized["formatted_market_cap"] = format_indian_currency(raw_mcap)
        normalized["currency"] = "INR"
    else:
        try:
            num = float(raw_mcap)
            normalized["formatted_market_cap"] = f"${num/1_000_000_000:,.2f} B"
            normalized["currency"] = "USD"
        except (ValueError, TypeError):
            normalized["formatted_market_cap"] = "N/A"
            normalized["currency"] = "Unknown"

    return normalized