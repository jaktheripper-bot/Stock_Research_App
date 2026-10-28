"""
Remediation Action Plan Generator for Autonomous Project Auditor.

Synthesizes the stateful remediation ledger into the dedicated markdown deliverable:
`audits/REMEDIATION_ACTION_PLAN.md`

Includes:
- Executive Triage Scorecard (Counts, Base Points, Aging Multipliers, Effective Penalty).
- Critical Aging Alerts (Highlighting items >=3 days at 1.5x and >=7 days at 2.0x).
- Prioritized Active Remediation Queue (Actionable steps, exact file lines, invariant names).
- Closed-Loop Resolution Log (Empirically verified fixes with timestamps).
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from core.db.connection import IST

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ACTION_PLAN_PATH = PROJECT_ROOT / "audits" / "REMEDIATION_ACTION_PLAN.md"


def generate_remediation_action_plan(
    audit_id: str,
    composite_score: float,
    open_findings: List[Dict[str, Any]],
    summary_stats: Dict[str, Any],
    resolved_in_cycle: List[Dict[str, Any]]
) -> str:
    """Generates the full markdown content for audits/REMEDIATION_ACTION_PLAN.md."""
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    # Determine health grade
    if composite_score >= 90.0:
        grade = "Grade A (Institutional Exemplary)"
        badge = "🟢"
    elif composite_score >= 80.0:
        grade = "Grade B (Compliant)"
        badge = "🟡"
    elif composite_score >= 65.0:
        grade = "Grade C (Action Required)"
        badge = "🟠"
    else:
        grade = "Grade D (Critical Intervention Required)"
        badge = "🔴"

    total_open = summary_stats.get("total_open", len(open_findings))
    crit_count = summary_stats.get("critical_open", 0)
    high_count = summary_stats.get("high_open", 0)
    med_count = summary_stats.get("medium_open", 0)
    low_count = summary_stats.get("low_open", 0)
    aging_3d = summary_stats.get("aging_over_3d", 0)
    aging_7d = summary_stats.get("aging_over_7d", 0)
    resolved_total = summary_stats.get("resolved_total", 0)
    total_penalty = summary_stats.get("total_penalty", 0.0)

    # 1. Header
    md = f"""# System Remediation Action Plan
**Generated At:** {now_ist}  
**Latest Audit Run:** `{audit_id}`  
**Composite Health Score:** {badge} **{composite_score:.1f}/100** — *{grade}*  
**Active Ledger Status:** `{total_open}` Open Items | `{resolved_total}` Resolved Total | **Total Aging Penalty:** `-{total_penalty:.1f} pts`  

---

## 1. Executive Triage Scorecard

| Invariant Severity | Active Count | Base Deduction / Item | Aging Multiplier | Subtotal Penalty |
| :--- | :---: | :---: | :---: | :---: |
| 🔴 **CRITICAL** | **{crit_count}** | 15.0 pts | 1.0x – 2.0x | -{sum(f.get('effective_penalty', 0.0) for f in open_findings if f.get('severity') == 'CRITICAL'):.1f} pts |
| 🟠 **HIGH** | **{high_count}** | 8.0 pts | 1.0x – 2.0x | -{sum(f.get('effective_penalty', 0.0) for f in open_findings if f.get('severity') == 'HIGH'):.1f} pts |
| 🟡 **MEDIUM** | **{med_count}** | 4.0 pts | 1.0x – 2.0x | -{sum(f.get('effective_penalty', 0.0) for f in open_findings if f.get('severity') == 'MEDIUM'):.1f} pts |
| ⚪ **LOW** | **{low_count}** | 1.0 pts | 1.0x – 2.0x | -{sum(f.get('effective_penalty', 0.0) for f in open_findings if f.get('severity') == 'LOW'):.1f} pts |
| **Composite Penalty** | **{total_open}** | — | — | **-{total_penalty:.1f} pts** |

---

## 2. 🚨 Aging Technical Debt & Compounding Penalty Alerts

> *Progressive Aging Invariant: Un-remediated findings compound their score penalty at **1.5x** after 3 days and **2.0x** after 7 days to aggressively deter technical debt accumulation.*
"""

    aging_items = [f for f in open_findings if f.get("age_in_days", 0.0) >= 3.0]
    if aging_items:
        md += "\n| Invariant | Severity | Age | Multiplier | Target | Description |\n"
        md += "| :--- | :---: | :---: | :---: | :--- | :--- |\n"
        for item in aging_items:
            sev = item.get("severity", "MEDIUM")
            age = item.get("age_in_days", 0.0)
            mult = item.get("aging_multiplier", 1.0)
            tgt = item.get("target_file_or_route", "")
            desc = item.get("title", "")
            md += f"| `{item.get('invariant_name')}` | **{sev}** | {age:.1f}d | **{mult}x** | `{tgt}` | {desc} |\n"
    else:
        md += "\n> 🟢 **Zero Aging Items:** No open findings have exceeded the 3-day aging threshold. All active defects are within fresh discovery or evaluation cycles.\n"

    # 3. Prioritized Active Remediation Queue
    md += f"""
---

## 3. Prioritized Active Remediation Queue ({total_open} Open)

Findings are sorted in descending order of effective penalty impact and age. Each item specifies concrete remediation steps to restore compliance.
"""

    if not open_findings:
        md += "\n> 🟢 **All Invariants Clean:** No open remediation findings exist in the ledger. System exhibits institutional stability.\n"
    else:
        for idx, finding in enumerate(open_findings, 1):
            severity = finding.get("severity", "MEDIUM")
            badge_icon = "🔴" if severity == "CRITICAL" else ("🟠" if severity == "HIGH" else ("🟡" if severity == "MEDIUM" else "⚪"))
            title = finding.get("title", "Invariant Defect")
            h = finding.get("finding_hash", "")
            invariant = finding.get("invariant_name", "")
            category = finding.get("category", "")
            target = finding.get("target_file_or_route", "")
            age = finding.get("age_in_days", 0.0)
            attempts = finding.get("verification_attempts", 1)
            consec_fails = finding.get("consecutive_failures", 1)
            base_ded = finding.get("base_deduction", 4.0)
            mult = finding.get("aging_multiplier", 1.0)
            effective_pen = finding.get("effective_penalty", base_ded)
            desc = finding.get("description", "")
            notes = finding.get("remediation_notes", "Remediate code to satisfy invariant contract.")

            md += f"""
### {idx}. {badge_icon} [{severity}] {title}
- **Finding Identifier:** `{h}`
- **Invariant:** `{invariant}` | **Category:** `{category}`
- **Target File / Route:** `{target}`
- **Lifecycle Metric:** Age: `{age:.1f} days` | Verification Attempts: `{attempts}` | Consecutive Failures: `{consec_fails}`
- **Score Deduction:** `-{effective_pen:.1f} pts` (Base: `{base_ded:.1f} pts` × `{mult:.1f}x` Aging Multiplier)
- **Problem Statement:** {desc}
- **Required Action:** {notes}

```bash
# Verify fix locally via targeted audit:
python3 scripts/run_project_audit.py --quick
```
"""

    # 4. Closed-Loop Verification & Resolution Log
    md += """
---

## 4. Closed-Loop Verification Log & Recent Resolutions

Records items successfully re-tested in Step 1 (Verify First) and verified as RESOLVED.
"""

    if resolved_in_cycle:
        md += "\n| Resolution Time | Invariant | Target | Verification Evidence |\n"
        md += "| :--- | :--- | :--- | :--- |\n"
        for r in resolved_in_cycle:
            h = r.get("finding_hash", "")[:8]
            inv = r.get("invariant_name", "")
            tgt = r.get("target_file_or_route", "")
            res_notes = r.get("notes") or r.get("remediation_notes") or "Empirically verified resolved in Verify-First pass."
            md += f"| `{now_ist}` | `{inv}` (`{h}`) | `{tgt}` | {res_notes} |\n"
    else:
        md += "\n> *No open findings were marked resolved during this execution pass.*\n"

    md += """
---
*Confidential — Automatically generated by the Autonomous Project Auditor under SEBI Safe Harbor guidelines for continuous engineering resilience.*
"""
    return md.strip()


def write_remediation_action_plan(
    audit_id: str,
    composite_score: float,
    open_findings: List[Dict[str, Any]],
    summary_stats: Dict[str, Any],
    resolved_in_cycle: List[Dict[str, Any]]
) -> Path:
    """Generates and writes the action plan directly to audits/REMEDIATION_ACTION_PLAN.md."""
    content = generate_remediation_action_plan(
        audit_id=audit_id,
        composite_score=composite_score,
        open_findings=open_findings,
        summary_stats=summary_stats,
        resolved_in_cycle=resolved_in_cycle
    )
    ACTION_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTION_PLAN_PATH.write_text(content, encoding="utf-8")
    return ACTION_PLAN_PATH
