#!/usr/bin/env python3
"""
Antigravity Remediation & Zero-Illusion Verification Squad.
Executes Wave 0 -> Wave 5 sequentially with hard AST, SQL, and Behavioral tool barriers.
"""
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List

try:
    from google_antigravity import Agent, SubAgent, Tool
except ImportError:
    # Fallback shim if running outside the Antigravity runtime container
    class Tool:
        def __init__(self, func, name=None, description=None):
            self.func = func
            self.name = name or func.__name__
            self.description = description or func.__doc__

    class SubAgent:
        def __init__(self, name: str, system_prompt: str, tools: List[Any]):
            self.name = name
            self.system_prompt = system_prompt
            self.tools = tools

    class Agent:
        def __init__(self, name: str, model: str, system_prompt: str, subagents: List["SubAgent"], tools: List[Any]):
            self.name = name
            self.model = model
            self.system_prompt = system_prompt
            self.subagents = subagents
            self.tools = tools

ROOT = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "scripts" else Path(__file__).resolve().parent


# =============================================================================
# DETERMINISTIC ANTIGRAVITY TOOLS (CANNOT BE HALLUCINATED BY SUBAGENTS)
# =============================================================================

def tool_run_reality_gate(gate_filter: str = "ALL") -> Dict[str, Any]:
    """
    Executes scripts/verify_reality_audit.py and returns the exact exit code and failure trace.
    Subagents MUST call this tool and achieve exit_code == 0 before completing their wave.
    """
    script_path = ROOT / "scripts" / "verify_reality_audit.py"
    if not script_path.exists():
        return {
            "exit_code": 127,
            "status": "BLOCKED",
            "output": "CRITICAL: scripts/verify_reality_audit.py does not exist yet. Run Wave 0 first."
        }

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")

    # If filtering by a specific gate during intermediate waves, check if that gate has failures
    if gate_filter != "ALL":
        gate_failures = [
            line for line in output.splitlines()
            if f"[{gate_filter}]" in line and "PASS" not in line
        ]
        passed = len(gate_failures) == 0
        return {
            "exit_code": 0 if passed else 1,
            "gate_filter": gate_filter,
            "status": "PASS" if passed else "FAIL",
            "gate_failures": gate_failures,
            "raw_output": output,
        }

    return {
        "exit_code": proc.returncode,
        "gate_filter": "ALL",
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "raw_output": output,
    }


def tool_run_unspoofed_pytest(target_path: str = "tests/unit") -> Dict[str, Any]:
    """
    Runs pytest with AUDIT_RECURSION_GUARD explicitly unset and ignores test_project_auditor.py
    so the agent cannot fake 'Ran 129 tests in 0.05s'.
    """
    env = dict(os.environ)
    env.pop("AUDIT_RECURSION_GUARD", None)

    cmd = [
        sys.executable, "-m", "pytest",
        target_path,
        "--ignore=tests/unit/test_project_auditor.py",
        "-q", "--tb=short"
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=180)
    return {
        "exit_code": proc.returncode,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "output": (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else ""),
    }


# =============================================================================
# SUBAGENT DEFINITIONS (SCOPED BY WAVE)
# =============================================================================

secops_lockdown_agent = SubAgent(
    name="secops_lockdown_agent",
    system_prompt="""You are the Tier-0 Security & Exploit Remediation Subagent for Moatnomics.
Your strict file scope is:
- core/auth/supabase_auth.py
- core/auth/otp.py
- core/ingestion/amfi.py, core/ingestion/etf_ingest.py, core/ingestion/http_client.py
- core/db/users.py, core/db/agent_sessions.py, core/db/debt.py, core/analysis/asset_scanner.py
- core/config.py, core/db/admin.py, core/db/telemetry.py, core/notify.py

MANDATORY TASKS:
1. Delete `_complete_direct_signin()` and module-level globals `_BARE_USER_SESSION` and `_BARE_AUTH_TOKEN` from `core/auth/supabase_auth.py`. Ensure `send_magic_link()` fails closed (returns `{"success": False, "error": ...}`) when `SUPABASE_ANON_KEY` is missing or Supabase returns non-200. Replace global session state with a request-scoped `contextvars.ContextVar`.
2. In `core/auth/otp.py`, remove `"stock_research_otp_salt_2026"`. Use `hmac.new(OTP_HMAC_SECRET, f"{email}:{otp}", hashlib.sha256)`.
3. Remove `ssl._create_unverified_context()` from `amfi.py` and `etf_ingest.py`; use `ssl.create_default_context(cafile=certifi.where())`.
4. Parameterize all `LIMIT {limit} OFFSET {offset}` SQL queries using `{p}` placeholders and integer clamping.
5. Replace hardcoded `lyndnpnto@gmail.com` references with `ADMIN_EMAILS` from `core/config.py`.

EXIT CONDITION:
Call `tool_run_reality_gate("GATE-1:SECURITY")` and `tool_run_reality_gate("GATE-5:BEHAVIORAL")`. Do not yield back to the Coordinator until both return `status == "PASS"`.""",
    tools=[Tool(tool_run_reality_gate), Tool(tool_run_unspoofed_pytest)],
)

fintech_ledger_agent = SubAgent(
    name="fintech_ledger_agent",
    system_prompt="""You are the Tier-1 Financial, Billing & Tax Compliance Subagent.
Your strict file scope is:
- core/billing/razorpay.py
- core/db/users.py
- core/agents/copilot/admin_copilot.py

MANDATORY TASKS:
1. In `core/db/users.py` (`add_user_credits`, `get_all_billables`) and `core/billing/razorpay.py` (`generate_invoice_html`), eliminate the `1.18` (18% GST) calculation and `"18% GST"` column. Render `"PAYMENT RECEIPT"` with `tax_amount = 0.0` and a clear unregistered-entity receipt footnote.
2. In `core/agents/copilot/admin_copilot.py`, fix `execute_confirmed_admin_action()` for `ISSUE_REFUND` so it calls `ok, msg = process_refund(transaction_id=str(order_id), reason=reason, admin_notes=...)` matching `core/db/users.py:process_refund`.

EXIT CONDITION:
Call `tool_run_reality_gate("GATE-4:ANTI-POTEMKIN")` and `tool_run_reality_gate("GATE-2:CONTRACTS")`. Both must return `status == "PASS"`.""",
    tools=[Tool(tool_run_reality_gate), Tool(tool_run_unspoofed_pytest)],
)

runtime_surgeon_agent = SubAgent(
    name="runtime_surgeon_agent",
    system_prompt="""You are the Tier-2 Runtime Bug & Broken Contract Surgeon Subagent.
Your strict file scope is:
- core/analysis/research_bouquet.py
- core/agents/watchers/bse_watcher.py
- core/analysis/parser.py
- core/reporting/pdf.py
- core/analytics/ai_spends.py
- core/analysis/daily_stock_ingestion.py
- core/agents/copilot/forensic_desk.py
- core/cortex/chanakya.py

MANDATORY TASKS:
1. `research_bouquet.py`: Replace broken import `get_daily_discovery_picks` with `from core.db.discovery import get_active_discovery_reel`.
2. `bse_watcher.py`: Resolve the 6-digit numeric BSE `scrip_code` before calling `fetch_latest_bse_announcement(scrip_code)`.
3. `parser.py`: Add `return "\\n".join(lines)` at the end of `format_citations_section()`.
4. `pdf.py`: Add `import json` at top of module.
5. `ai_spends.py`: Fix SQL query on `admin_audit_log` from `action_type` to `action`.
6. `daily_stock_ingestion.py` & `forensic_desk.py`: Strip leaked system prompt instructions (`"You are an institutional equity research analyst..."`) and hardcoded fake ESG/pledge scores from fallback strings.
7. `chanakya.py`: Fix `evaluate_from_dict` return annotation to `ChanakyaVerdict` and default `mode="STRICT"`.

EXIT CONDITION:
Call `tool_run_reality_gate("GATE-2:CONTRACTS")`, `tool_run_reality_gate("GATE-3:SQL-SCHEMA")`, and `tool_run_reality_gate("GATE-5:BEHAVIORAL")`. All three must return `status == "PASS"`.""",
    tools=[Tool(tool_run_reality_gate), Tool(tool_run_unspoofed_pytest)],
)

cortex_integrator_agent = SubAgent(
    name="cortex_integrator_agent",
    system_prompt="""You are the Tier-3 Quantitative Engine Integrator & Anti-Synthetic Data Subagent.
Your strict file scope is:
- core/msme/daily_ingest.py, core/msme/forensic_engine.py
- core/cortex/engine.py, core/cortex/varan.py, core/cortex/setu.py, core/cortex/sutra.py
- core/analysis/equity_dossier.py
- core/audit/tools.py

MANDATORY TASKS:
1. Disable procedural fake company name generation (`generate_cluster_cohort_for_date` / `UDYAM-MH-26-`) in `core/msme/daily_ingest.py`.
2. Wire `VaranEngine().compile_delta_packet()` and `SetuMatrixEngine()` into `core/analysis/equity_dossier.py`.
3. Wire `SutraLookThroughEngine` in `core/cortex/sutra.py` to query `mutual_fund_holdings` from SQLite/Postgres instead of the static 4-fund `SCHEME_TOP_HOLDINGS_REGISTRY` dictionary.
4. Remove the `AUDIT_RECURSION_GUARD == "1"` fake `"Ran 129 tests in 0.05s"` block from `core/audit/tools.py`.

EXIT CONDITION:
Call `tool_run_reality_gate("ALL")` and `tool_run_unspoofed_pytest()`. Both must return `exit_code == 0`.""",
    tools=[Tool(tool_run_reality_gate), Tool(tool_run_unspoofed_pytest)],
)


# =============================================================================
# COORDINATOR AGENT DEFINITION & RUNNER
# =============================================================================

remediation_coordinator = Agent(
    name="moatnomics_remediation_coordinator",
    model="gemini-3.8-flash",
    system_prompt="""You are the Principal Antigravity Remediation Coordinator for Moatnomics.
You enforce a strict Red-to-Green wave rollout:
1. First, run `tool_run_reality_gate("ALL")` to log the exact baseline failures.
2. Dispatch `secops_lockdown_agent` (Wave 1). Verify `GATE-1:SECURITY` is PASS before proceeding.
3. Dispatch `fintech_ledger_agent` (Wave 2). Verify GST and refund contract gates pass.
4. Dispatch `runtime_surgeon_agent` (Wave 3). Verify all AST Symbol, Signature, and SQL Schema gates pass.
5. Dispatch `cortex_integrator_agent` (Wave 4). Verify `tool_run_reality_gate("ALL")` returns `exit_code == 0` and `tool_run_unspoofed_pytest()` passes all real tests.
NEVER accept a subagent's natural-language claim that a bug is fixed without verifying `exit_code == 0` from `tool_run_reality_gate`.""",
    subagents=[
        secops_lockdown_agent,
        fintech_ledger_agent,
        runtime_surgeon_agent,
        cortex_integrator_agent,
    ],
    tools=[Tool(tool_run_reality_gate), Tool(tool_run_unspoofed_pytest)],
)


def execute_squad_rollout() -> int:
    """
    Executes sequential verification of Wave 0 -> Wave 5 barriers deterministically.
    """
    print("=" * 80)
    print("ANTIGRAVITY REMEDIATION & ZERO-ILLUSION SQUAD ROLLOUT")
    print("=" * 80)

    # Wave 0: Baseline Reality Check
    print("\n[WAVE 0] Running baseline reality audit check...")
    baseline = tool_run_reality_gate("ALL")
    print(f"  Wave 0 Reality Gate: {baseline['status']} (Exit {baseline['exit_code']})")

    # Wave 1: SecOps Lockdown Gate
    print("\n[WAVE 1: SECOPS] Verifying GATE-1:SECURITY and GATE-5:BEHAVIORAL...")
    w1_sec = tool_run_reality_gate("GATE-1:SECURITY")
    w1_beh = tool_run_reality_gate("GATE-5:BEHAVIORAL")
    w1_pass = w1_sec["status"] == "PASS" and w1_beh["status"] == "PASS"
    print(f"  GATE-1:SECURITY  -> {w1_sec['status']}")
    print(f"  GATE-5:BEHAVIORAL -> {w1_beh['status']}")
    if not w1_pass:
        print("  CRITICAL: Wave 1 SecOps verification failed.")
        return 1

    # Wave 2: FinTech & Ledger Compliance Gate
    print("\n[WAVE 2: FINTECH] Verifying GATE-4:ANTI-POTEMKIN and GATE-2:CONTRACTS...")
    w2_pot = tool_run_reality_gate("GATE-4:ANTI-POTEMKIN")
    w2_con = tool_run_reality_gate("GATE-2:CONTRACTS")
    w2_pass = w2_pot["status"] == "PASS" and w2_con["status"] == "PASS"
    print(f"  GATE-4:ANTI-POTEMKIN -> {w2_pot['status']}")
    print(f"  GATE-2:CONTRACTS     -> {w2_con['status']}")
    if not w2_pass:
        print("  CRITICAL: Wave 2 FinTech verification failed.")
        return 1

    # Wave 3: Runtime Surgeon Gate
    print("\n[WAVE 3: RUNTIME] Verifying CONTRACTS, SQL-SCHEMA, and BEHAVIORAL...")
    w3_con = tool_run_reality_gate("GATE-2:CONTRACTS")
    w3_sql = tool_run_reality_gate("GATE-3:SQL-SCHEMA")
    w3_beh = tool_run_reality_gate("GATE-5:BEHAVIORAL")
    w3_pass = w3_con["status"] == "PASS" and w3_sql["status"] == "PASS" and w3_beh["status"] == "PASS"
    print(f"  GATE-2:CONTRACTS  -> {w3_con['status']}")
    print(f"  GATE-3:SQL-SCHEMA -> {w3_sql['status']}")
    print(f"  GATE-5:BEHAVIORAL -> {w3_beh['status']}")
    if not w3_pass:
        print("  CRITICAL: Wave 3 Runtime Surgeon verification failed.")
        return 1

    # Wave 4: Cortex Integrator Gate & Unspoofed Tests
    print("\n[WAVE 4: CORTEX] Verifying ALL Reality Gates & Unspoofed PyTest...")
    w4_all = tool_run_reality_gate("ALL")
    print(f"  Reality Gate (ALL) -> {w4_all['status']} (Exit {w4_all['exit_code']})")
    if w4_all["exit_code"] != 0:
        print("  CRITICAL: Reality gate failed in Wave 4:")
        print(w4_all["raw_output"])
        return 1

    w4_test = tool_run_unspoofed_pytest("tests/unit")
    print(f"  Unspoofed PyTest  -> {w4_test['status']} (Exit {w4_test['exit_code']})")
    if w4_test["exit_code"] != 0:
        print("  CRITICAL: Unspoofed PyTest failed in Wave 4:")
        print(w4_test["output"])
        return 1

    # Wave 5: Final Coordinator Green Check
    print("\n" + "=" * 80)
    print("ALL 5 REMEDIATION SQUAD WAVES PASSED CLEANLY (RED-TO-GREEN CERTIFIED)")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(execute_squad_rollout())
