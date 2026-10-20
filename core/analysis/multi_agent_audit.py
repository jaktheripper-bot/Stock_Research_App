"""
Proof-of-Concept Multi-Agent Accounting Check Module.
Consolidated into canonical core.agents.equity.forensic_squad.
Maintains full backward compatibility for legacy imports.
"""

from core.analysis.fundamentals import get_stock_fundamentals, fetch_latest_bse_announcement
from core.agents.equity.forensic_squad import (
    ForensicAuditResult,
    ANTIGRAVITY_AVAILABLE,
    tool_get_fundamentals,
    tool_get_bse_disclosures,
    tool_compute_forensic_signals,
    run_deterministic_forensic_fallback,
    run_multi_agent_forensic_audit,
    run_multi_agent_forensic_audit_sync,
)

__all__ = [
    "ForensicAuditResult",
    "ANTIGRAVITY_AVAILABLE",
    "get_stock_fundamentals",
    "fetch_latest_bse_announcement",
    "tool_get_fundamentals",
    "tool_get_bse_disclosures",
    "tool_compute_forensic_signals",
    "run_deterministic_forensic_fallback",
    "run_multi_agent_forensic_audit",
    "run_multi_agent_forensic_audit_sync",
]
