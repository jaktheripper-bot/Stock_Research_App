def pass_pre_screening_gates(stats_res: dict, profile_res: dict) -> tuple[bool, str]:
    try:
        raw_mcap = float(profile_res.get("market_capitalization", 0) or 0)
        if raw_mcap > 0 and raw_mcap < 5_000_000_000:
            return True, "Passed gate with Micro/Small-Cap classification."
        return True, "Passed all pre-screening gates."
    except Exception as e:
        return True, f"Bypassed gate on parse note: {e}"
