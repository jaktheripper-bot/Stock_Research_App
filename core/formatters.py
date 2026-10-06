"""Currency, numerical, and date formatting utilities for Indian Equities."""

def group_inr(num) -> str:
    """Formats float into Indian numbering system (Lakhs and Crores grouping)."""
    parts = f"{num:.2f}".split(".")
    int_p, dec_p = parts[0], parts[1]
    if len(int_p) <= 3:
        return f"{int_p}.{dec_p}"
    last_three = int_p[-3:]
    remaining = int_p[:-3]
    groups = []
    while remaining:
        groups.append(remaining[-2:])
        remaining = remaining[:-2]
    groups.reverse()
    return f"{','.join(groups)},{last_three}.{dec_p}"

def format_inr(number) -> str:
    """Formats large numeric INR values into Lakh / Cr denominations."""
    if number is None or str(number).strip() in ["", "0", "N/A", "None"]:
        return "N/A"
    try:
        clean_num = str(number).replace(",", "").strip()
        val = float(clean_num)
    except (ValueError, TypeError):
        return str(number)

    if val >= 1e7:
        return f"₹{group_inr(val / 1e7)} Cr"
    elif val >= 1e5:
        return f"₹{group_inr(val / 1e5)} Lakh"
    return f"₹{group_inr(val)}"
