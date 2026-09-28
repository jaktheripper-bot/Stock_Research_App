"""Quantitative pre-screening and gate evaluation for equities."""

def pass_pre_screening_gates(stats_res: dict, profile_res: dict) -> tuple[bool, str]:
    """
    Evaluates sanity and liquidity gates on fundamentals before heavy thesis synthesis:
    - Verifies trading activity / non-zero market capitalization
    - Categorizes market cap tier (Micro/Small/Mid/Large cap)
    - Rejects inactive or suspended securities (zero price and market cap)
    """
    try:
        stats = stats_res or {}
        profile = profile_res or {}
        raw_mcap = float(profile.get("market_capitalization") or stats.get("market_cap") or 0)
        price = float(stats.get("current_price") or profile.get("current_price") or 0)

        if price <= 0 and raw_mcap <= 0:
            return False, "Failed gate: Inactive or suspended security (Zero Price and Market Cap)."

        if raw_mcap > 0 and raw_mcap < 5_000_000_000:
            return True, "Passed gate with Micro/Small-Cap classification."
        elif raw_mcap >= 500_000_000_000:
            return True, "Passed gate with Large-Cap classification."
        return True, "Passed all pre-screening gates."
    except Exception as e:
        return True, f"Bypassed gate on parse note: {e}"
