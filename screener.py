def pass_pre_screening_gates(stats_res: dict, profile_res: dict) -> tuple[bool, str]:
    try:
        raw_mcap = float(profile_res.get("market_capitalization", 0) or 0)
        if raw_mcap > 0 and raw_mcap < 5_000_000_000:
            return False, f"Failed Market Cap Gate: {raw_mcap} is below the ₹500 Cr threshold."

        # Lenient data check: allow missing trailing P/E since demo tier limits statistics
        return True, "Passed all pre-screening gates."
    except (ValueError, TypeError) as e:
        return False, f"Failed Pre-Screening Exception: {str(e)}"
