def format_indian_currency(val) -> str:
    try:
        num = float(val)
    except (ValueError, TypeError):
        return "N/A"

    if num >= 10_000_000:
        crores = num / 10_000_000
        return f"₹{crores:,.2f} Cr"
    elif num >= 100_000:
        lakhs = num / 100_000
        return f"₹{lakhs:,.2f} Lakh"
    else:
        return f"₹{num:,.2f}"

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