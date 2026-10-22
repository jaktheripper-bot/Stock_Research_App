"""Forensic Desk interactive research module.

Provides backwards-compatible re-exports and alias bindings for research_desk.py,
ensuring all SEBI Safe Harbor directives, prompt boundary guardrails, and output
scrubbing utilities are natively accessible via core.agents.copilot.forensic_desk.
"""

from core.agents.copilot.research_desk import (
    SEBI_SAFE_HARBOR_DIRECTIVE,
    SEBI_SYSTEM_BOUNDARY_DIRECTIVE,
    SEBI_PRESCRIPTIVE_TOKENS_RE,
    scrub_prescriptive_tokens,
    scrub_streaming_yield,
    check_non_advisory_compliance,
    check_input_qualification,
    is_input_qualified,
    detect_forbidden_intent,
    process_research_desk_turn,
    build_equity_deterministic_response,
    build_mutual_fund_deterministic_response,
    build_debt_deterministic_response,
    build_etf_deterministic_response,
    build_reit_deterministic_response,
    redact_gated_pillars,
    detect_gated_topic,
    build_unlock_notice,
)

# Canonical aliases for Forensic Desk
process_forensic_desk_turn = process_research_desk_turn
