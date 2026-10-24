#!/usr/bin/env python3
"""CLI Utility for Autonomous Project-Wide Auditing.

Usage:
    python3 scripts/run_project_audit.py --full
    python3 scripts/run_project_audit.py --quick
    python3 scripts/run_project_audit.py --history
    python3 scripts/run_project_audit.py --id AUD-20261007-085700
"""

import os
import sys
import argparse
import asyncio
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.audit.project_auditor import audit_project_full
from core.db.audit_logs import (
    get_project_audit_history,
    get_project_audit_by_id,
    sync_remote_audits_to_local,
)


async def main_async():
    parser = argparse.ArgumentParser(description="Autonomous Project-Wide Auditor (Strategy, Code & UI/UX)")
    parser.add_argument("--full", action="store_true", help="Execute complete audit with AI cognitive synthesis")
    parser.add_argument("--quick", action="store_true", help="Execute deterministic-only audit (skips LLM generation)")
    parser.add_argument("--sync", action="store_true", help="Pull remote Supabase audit logs and remediation ledger into local DB and audits/")
    parser.add_argument("--history", action="store_true", help="List recent project audit history from database")
    parser.add_argument("--id", type=str, help="View full markdown dossier of a specific audit by ID")
    parser.add_argument("--plan", action="store_true", help="View current Remediation Action Plan (audits/REMEDIATION_ACTION_PLAN.md)")
    parser.add_argument("--output", type=str, help="Custom markdown output path")

    args = parser.parse_args()

    if args.sync:
        res = sync_remote_audits_to_local(limit=50, force=True)
        print("\n=========================================================================")
        print("          MOATNOMICS — CLOUD-TO-LOCAL AUDIT SYNC COMPLETE                ")
        print("=========================================================================")
        print(f"Synced Status:         {res.get('synced')}")
        print(f"Audit Logs Pulled:     {res.get('synced_audits', 0)}")
        print(f"Markdown Files Saved:  {res.get('synced_files', 0)} (in audits/)")
        print(f"Remediation Items:     {res.get('synced_findings', 0)}")
        print(f"Latest Cloud Audit ID: {res.get('latest_audit_id') or 'N/A'}")
        print("=========================================================================\n")
        return

    if args.plan:
        sync_remote_audits_to_local(limit=30)
        plan_path = PROJECT_ROOT / "audits" / "REMEDIATION_ACTION_PLAN.md"
        if not plan_path.exists():
            print("No active remediation plan found at audits/REMEDIATION_ACTION_PLAN.md. Run an audit to generate one.")
            sys.exit(1)
        print(plan_path.read_text(encoding="utf-8"))
        return

    if args.history:
        history = get_project_audit_history(limit=10)
        print("\n=========================================================================")
        print("          MOATNOMICS — RECENT SYSTEM AUDIT HISTORY               ")
        print("=========================================================================")
        if not history:
            print("No audit history found in database.")
            return

        print(f"{'Audit ID':<26} | {'Score':<7} | {'Status':<15} | {'Tests':<10} | {'Date':<19}")
        print("-" * 85)
        for h in history:
            audit_id = h.get("audit_id", "N/A")
            score = f"{h.get('overall_score', 0.0):.1f}"
            status = h.get("status", "N/A")
            tests = f"{h.get('tests_passed', 0)}/{h.get('tests_total', 0)}"
            created = str(h.get("created_at", ""))[:19]
            print(f"{audit_id:<26} | {score:<7} | {status:<15} | {tests:<10} | {created:<19}")
        print("=" * 85 + "\n")
        return

    if args.id:
        record = get_project_audit_by_id(args.id.strip())
        if not record:
            print(f"Audit ID '{args.id}' not found.")
            sys.exit(1)
        print(record.get("full_markdown_report", "No markdown report found."))
        return

    use_ai = not args.quick
    sync_remote_audits_to_local(limit=30)
    print("\n🔍 Initiating Autonomous Project Audit across Strategy, Code & UI/UX...")
    print(f"   Engine: Autonomous Multi-Agent Auditor | Mode: {'AI Synthesis' if use_ai else 'Deterministic Fast-Path'}")
    print("   Evaluating test suite, live endpoints, SEBI compliance, and AST code hygiene...\n")

    result = await audit_project_full(use_ai=use_ai, quick=args.quick)

    remediation_stats = result.pillar_breakdown.get("remediation_stats", {})
    total_open = remediation_stats.get("total_open", 0)
    aging_3d = remediation_stats.get("aging_over_3d", 0)
    resolved_total = remediation_stats.get("resolved_total", 0)
    total_penalty = remediation_stats.get("total_penalty", 0.0)

    print("=========================================================================")
    print("                 PROJECT AUDIT EXECUTION COMPLETE                        ")
    print("=========================================================================")
    print(f"Audit ID:              {result.audit_id}")
    print(f"Overall System Score:  {result.overall_score}/100 ({result.status})")
    print(f"  • Strategy Pillar:   {result.strategy_score}/100")
    print(f"  • Code Pillar:       {result.implementation_score}/100")
    print(f"  • UI/UX Pillar:      {result.uiux_score}/100")
    print(f"Tests Evaluated:       {result.tests_passed}/{result.tests_total} Passing")
    print(f"Endpoints Checked:     {result.endpoints_healthy}/{result.endpoints_checked} Healthy (HTTP 200)")
    print(f"Remediation Ledger:    {total_open} Open Items ({aging_3d} Aging >=3d, -{total_penalty:.1f} pts) | {resolved_total} Resolved")
    print(f"Action Plan:           audits/REMEDIATION_ACTION_PLAN.md")
    print(f"Critical Violations:   {len(result.critical_violations)}")
    print(f"Active Recommendations:{len(result.recommendations)}")
    print("=========================================================================\n")

    if result.critical_violations:
        print("⚠️ CRITICAL VIOLATIONS DETECTED:")
        for v in result.critical_violations:
            print(f"  - {v}")
        print()

    if result.recommendations:
        print("📋 ACTIONABLE RECOMMENDATIONS:")
        for r in result.recommendations:
            print(f"  - {r}")
        print()

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result.full_markdown_report, encoding="utf-8")
        print(f"Exported dossier to: {out_path}\n")

    # Exit code: 0 if healthy/compliant, 1 if critical/action required
    if result.status == "CRITICAL":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main_async())
