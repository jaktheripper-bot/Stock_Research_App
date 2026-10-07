"""Central Configuration, Safety Policies & Operational Budgets for Sitewide Agents.

Powered by the Google Antigravity SDK (`google.antigravity`).
Enforces SEBI Safe Harbor, workspace isolation, and token budget ceilings.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from google.antigravity import types
    from google.antigravity.hooks import policy
    ANTIGRAVITY_AVAILABLE = True
except ImportError:
    ANTIGRAVITY_AVAILABLE = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Institutional Guardrails & Non-Advisory System Instructions
# ---------------------------------------------------------------------------

SEBI_SAFE_HARBOR_DIRECTIVE = """
You are an institutional financial research assistant operating strictly under the
SEBI Research Analyst Regulations, 2014 Section 2(u) non-advisory Safe Harbor.

CRITICAL REGULATORY GUARDRAILS:
1. NEVER output explicit buy, sell, hold, accumulate, or reduce recommendations.
2. NEVER predict target prices, guaranteed returns, or short-term trading calls.
3. Frame all assessments as descriptive, factual health scores and risk diagnostics
   (e.g., Moat: Wide/Narrow, Solvency: Clean/Stressed, Valuation: Stretched/Fair).
4. Strictly zero patronizing conversational baby talk, colloquialisms, or fluff.
   Maintain an objective, rigorous, institutional diagnostic tone.
5. All quantitative metrics must ground directly in exchange filings or verified models.
   Never hallucinate or extrapolate synthetic financial numbers.
"""

# ---------------------------------------------------------------------------
# Declarative Safety Policies (Access Control & Sandboxing)
# ---------------------------------------------------------------------------

def get_default_agent_policies():
    """Returns strict declarative policies restricting agent actions to workspace boundaries."""
    if not ANTIGRAVITY_AVAILABLE:
        return []

    return [
        policy.deny_all(),
        policy.allow("view_file"),
        policy.allow("search_directory"),
        policy.allow("read_url_content"),
        policy.workspace_only([str(PROJECT_ROOT)]),
        policy.allow(
            "run_command",
            when=lambda args: "unittest" in args.get("CommandLine", "") or "pytest" in args.get("CommandLine", ""),
            name="allow_test_runner_only"
        ),
        policy.allow("start_subagent"),
        policy.allow("ask_question"),
    ]


# ---------------------------------------------------------------------------
# Operational Ceilings & Token Budgets
# ---------------------------------------------------------------------------

def get_tier_budget_config(tier_name: str = "domain_research"):
    """Returns a BudgetConfig tailored to operational requirements to prevent runaway inference."""
    if not ANTIGRAVITY_AVAILABLE:
        return None

    budgets = {
        "domain_research": types.BudgetConfig(
            max_model_calls=15,
            max_tool_calls=30,
            max_total_tokens=150_000
        ),
        "interactive_copilot": types.BudgetConfig(
            max_model_calls=8,
            max_tool_calls=15,
            max_total_tokens=80_000
        ),
        "background_watcher": types.BudgetConfig(
            max_model_calls=5,
            max_tool_calls=10,
            max_total_tokens=50_000
        ),
        "system_auditor": types.BudgetConfig(
            max_model_calls=10,
            max_tool_calls=25,
            max_total_tokens=120_000
        )
    }
    return budgets.get(tier_name, budgets["domain_research"])
