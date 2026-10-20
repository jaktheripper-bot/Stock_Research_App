"""Audit module for Moatnomics.
Exposes autonomous project auditor and deterministic evaluation tools.
"""

from core.audit.project_auditor import (
    audit_project_full,
    ProjectAuditResult,
    compute_deterministic_audit_metrics,
    moatnomics_strategy_subagent
)
from core.audit.tools import (
    tool_run_test_suite,
    tool_probe_web_endpoints,
    tool_scan_prohibited_terms,
    tool_scan_code_hygiene,
    tool_audit_design_tokens
)

__all__ = [
    "audit_project_full",
    "ProjectAuditResult",
    "compute_deterministic_audit_metrics",
    "moatnomics_strategy_subagent",
    "tool_run_test_suite",
    "tool_probe_web_endpoints",
    "tool_scan_prohibited_terms",
    "tool_scan_code_hygiene",
    "tool_audit_design_tokens"
]
