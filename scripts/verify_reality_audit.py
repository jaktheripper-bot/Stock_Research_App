#!/usr/bin/env python3
"""
Zero-Illusion Reality Auditor & Security Gate for Moatnomics.
Detects unauthenticated bypasses, broken import/call contracts, SQL schema mismatches,
silent exception masking, and Potemkin/unwired engines on the first run.
"""
import ast
import importlib
import inspect
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

find_py_files = lambda dirs: [
    p for d in dirs for p in (ROOT / d).rglob("*.py")
    if "__pycache__" not in str(p)
]


class AuditFailure(Exception):
    pass


class RealityAuditor:
    def __init__(self) -> None:
        self.failures: List[Tuple[str, str, str]] = []  # (Gate, Location, Message)
        self.passed: List[str] = []

    def fail(self, gate: str, location: str, msg: str) -> None:
        self.failures.append((gate, location, msg))

    def ok(self, gate: str, msg: str) -> None:
        self.passed.append(f"[{gate}] {msg}")

    # =========================================================================
    # GATE 1: SECURITY & EXPLOIT SURFACE (AST + STATIC)
    # =========================================================================
    def run_gate_1_security(self) -> None:
        gate = "GATE-1:SECURITY"
        # 1.1 Check supabase_auth.py for unauthenticated fallback & global session state
        sa_path = ROOT / "core/auth/supabase_auth.py"
        if sa_path.exists():
            src = sa_path.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(sa_path))
            func_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
            if "_complete_direct_signin" in func_names or "_complete_direct_signin" in src:
                self.fail(gate, "core/auth/supabase_auth.py",
                          "CRITICAL: _complete_direct_signin fallback still exists (unauthenticated account takeover).")
            else:
                self.ok(gate, "No _complete_direct_signin bypass in supabase_auth.py")

            for banned_global in ("_BARE_USER_SESSION", "_BARE_AUTH_TOKEN"):
                if banned_global in src:
                    self.fail(gate, "core/auth/supabase_auth.py",
                              f"HIGH: Thread-unsafe global session state '{banned_global}' still present.")

        # 1.2 Check OTP static salt fallback
        otp_path = ROOT / "core/auth/otp.py"
        if otp_path.exists():
            otp_src = otp_path.read_text(encoding="utf-8")
            if "stock_research_otp_salt_2026" in otp_src:
                self.fail(gate, "core/auth/otp.py",
                          "MEDIUM: Hardcoded fallback salt 'stock_research_otp_salt_2026' still present.")
            else:
                self.ok(gate, "OTP hashing uses non-static secret")

        # 1.3 Check for unverified SSL context across entire repo
        for py in find_py_files(["core", "web"]):
            src = py.read_text(encoding="utf-8")
            if "_create_unverified_context" in src:
                self.fail(gate, str(py.relative_to(ROOT)),
                          "MEDIUM: ssl._create_unverified_context() disables TLS verification (MITM risk).")

        # 1.4 Check for f-string SQL LIMIT / OFFSET interpolation
        sql_limit_re = re.compile(r'f["\'][^"\']*LIMIT\s*\{[^p\}]', re.IGNORECASE)
        for py in find_py_files(["core", "web"]):
            src = py.read_text(encoding="utf-8")
            for m in sql_limit_re.finditer(src):
                line_no = src[:m.start()].count("\n") + 1
                self.fail(gate, f"{py.relative_to(ROOT)}:{line_no}",
                          "MEDIUM: Unparameterized f-string interpolation in SQL LIMIT/OFFSET clause.")

        # 1.5 Check for hardcoded personal email in code
        for py in find_py_files(["core", "web"]):
            src = py.read_text(encoding="utf-8")
            if "lyndnpnto@gmail.com" in src:
                self.fail(gate, str(py.relative_to(ROOT)),
                          "LOW: Hardcoded personal email 'lyndnpnto@gmail.com' found in source code.")

    # =========================================================================
    # GATE 2: AST SYMBOL RESOLUTION, SIGNATURES & RETURN PATHS
    # =========================================================================
    def run_gate_2_ast_contracts(self) -> None:
        gate = "GATE-2:CONTRACTS"
        for py in find_py_files(["core", "web"]):
            rel = str(py.relative_to(ROOT))
            src = py.read_text(encoding="utf-8")
            try:
                tree = ast.parse(src, filename=rel)
            except SyntaxError as e:
                self.fail(gate, f"{rel}:{e.lineno}", f"SyntaxError: {e.msg}")
                continue

            # 2.1 Verify all internal `from core... import X` actually exist!
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(("core", "web")):
                    try:
                        mod = importlib.import_module(node.module)
                        for alias in node.names:
                            if alias.name != "*" and not hasattr(mod, alias.name):
                                self.fail(gate, f"{rel}:{node.lineno}",
                                          f"Broken Import: '{alias.name}' does not exist in '{node.module}'")
                    except Exception as e:
                        self.fail(gate, f"{rel}:{node.lineno}",
                                  f"Failed to import '{node.module}': {e}")

            # 2.2 Check for `json.loads` / `json.dumps` without importing `json`
            top_imports: Set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        top_imports.add(a.asname or a.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    for a in node.names:
                        top_imports.add(a.asname or a.name)

            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    if node.value.id == "json" and "json" not in top_imports:
                        self.fail(gate, f"{rel}:{node.lineno}",
                                  "NameError at runtime: 'json' used but never imported in module.")

            # 2.3 Check functions annotated with `-> str` or `-> List` that have NO return statement
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.returns is not None:
                    ret_ann = ast.unparse(node.returns) if hasattr(ast, "unparse") else ""
                    if ret_ann and "None" not in ret_ann:
                        has_non_empty_return = any(
                            isinstance(sub, ast.Return) and sub.value is not None
                            for sub in ast.walk(node)
                        )
                        if not has_non_empty_return:
                            self.fail(gate, f"{rel}:{node.lineno}",
                                      f"Function '{node.name}' annotated '-> {ret_ann}' has no return value (returns None).")

        # 2.4 Verify `process_refund` call sites match `core.db.users.process_refund` signature
        from core.db.users import process_refund
        sig = inspect.signature(process_refund)
        valid_params = set(sig.parameters.keys())
        ac_path = ROOT / "core/agents/copilot/admin_copilot.py"
        if ac_path.exists():
            tree = ast.parse(ac_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "process_refund":
                    call_kwargs = {kw.arg for kw in node.keywords if kw.arg}
                    invalid_kw = call_kwargs - valid_params
                    if invalid_kw:
                        self.fail(gate, f"core/agents/copilot/admin_copilot.py:{node.lineno}",
                                  f"process_refund() called with invalid kwargs {invalid_kw}; valid={valid_params}")
                    else:
                        self.ok(gate, "process_refund() signature matches admin_copilot.py call site")

    # =========================================================================
    # GATE 3: LIVE SQL-TO-SCHEMA INTROSPECTION
    # =========================================================================
    def run_gate_3_sql_schema(self) -> None:
        gate = "GATE-3:SQL-SCHEMA"
        from core.db.connection import init_db, get_connection
        init_db()
        conn = get_connection()
        cur = conn.cursor()

        # Introspect all actual columns in admin_audit_log
        cur.execute("PRAGMA table_info(admin_audit_log)")
        audit_cols = {row[1] for row in cur.fetchall()}

        ai_spends_path = ROOT / "core/analytics/ai_spends.py"
        if ai_spends_path.exists():
            src = ai_spends_path.read_text(encoding="utf-8")
            if "action_type" in src and "action_type" not in audit_cols:
                self.fail(gate, "core/analytics/ai_spends.py",
                          f"SQL queries non-existent column 'action_type' on admin_audit_log (actual columns: {sorted(audit_cols)})")
            else:
                self.ok(gate, "ai_spends.py queries valid columns on admin_audit_log")

    # =========================================================================
    # GATE 4: ANTI-POTEMKIN, AUDIT INTEGRITY & TAX COMPLIANCE
    # =========================================================================
    def run_gate_4_anti_potemkin(self) -> None:
        gate = "GATE-4:ANTI-POTEMKIN"

        # 4.1 Ensure audit recursion guard does NOT return fake "Ran 129 tests"
        audit_tools = ROOT / "core/audit/tools.py"
        if audit_tools.exists():
            src = audit_tools.read_text(encoding="utf-8")
            if "Ran 129 tests" in src:
                self.fail(gate, "core/audit/tools.py",
                          "Audit Gaming Detected: Hardcoded 'Ran 129 tests in 0.05s' bypass still in tool_run_test_suite().")
            else:
                self.ok(gate, "No hardcoded fake test results in core/audit/tools.py")

        # 4.2 Ensure unregistered entity does not compute 18% GST splits in invoices/credits
        for rel in ("core/billing/razorpay.py", "core/db/users.py"):
            p = ROOT / rel
            if p.exists():
                src = p.read_text(encoding="utf-8")
                if "1.18" in src or "18% GST" in src:
                    self.fail(gate, rel,
                              "Tax Compliance Contradiction: 18% GST calculation ('1.18' / '18% GST') present in unregistered tool.")

        # 4.3 Check for prompt leakage in deterministic stock reports
        dsi = ROOT / "core/analysis/daily_stock_ingestion.py"
        if dsi.exists():
            src = dsi.read_text(encoding="utf-8")
            if "You are an institutional equity research analyst. Write a comprehensive" in src:
                self.fail(gate, "core/analysis/daily_stock_ingestion.py",
                          "Prompt Leakage: Raw LLM system instructions are embedded inside deterministic fallback report output.")

        # 4.4 Check for procedural fake MSME fabrication
        msme_ingest = ROOT / "core/msme/daily_ingest.py"
        if msme_ingest.exists():
            src = msme_ingest.read_text(encoding="utf-8")
            if "UDYAM-MH-26-" in src or "generate_cluster_cohort_for_date" in src:
                self.fail(gate, "core/msme/daily_ingest.py",
                          "Synthetic Data Violation: Procedural fake MSME name/Udyam generator still active.")

    # =========================================================================
    # GATE 5: BEHAVIORAL NEGATIVE-PATH TESTS
    # =========================================================================
    def run_gate_5_behavioral(self) -> None:
        gate = "GATE-5:BEHAVIORAL"

        # 5.1 Verify send_magic_link does NOT log a user in when Supabase is unconfigured
        from core.auth import supabase_auth
        os.environ.pop("SUPABASE_ANON_KEY", None)
        res = supabase_auth.send_magic_link("audit_victim@example.com")
        current = supabase_auth.get_current_user()
        if (isinstance(res, dict) and res.get("user")) or (current and current.get("email") == "audit_victim@example.com"):
            self.fail(gate, "core/auth/supabase_auth.py:send_magic_link",
                      "EXPLOIT CONFIRMED: send_magic_link('audit_victim@example.com') logged the user in without verification!")
        else:
            self.ok(gate, "send_magic_link() properly rejects unverified login on gateway failure")

        # 5.2 Verify format_citations_section actually returns a non-empty string
        from core.analysis.parser import format_citations_section
        sample_cite = format_citations_section([{"title": "BSE Filing", "url": "https://bseindia.com"}])
        if not isinstance(sample_cite, str) or "BSE Filing" not in sample_cite:
            self.fail(gate, "core/analysis/parser.py:format_citations_section",
                      f"format_citations_section() returned {sample_cite!r} instead of formatted markdown string.")
        else:
            self.ok(gate, "format_citations_section() returns valid markdown citations")

    # =========================================================================
    # GATE 6: ZERO SILENT EXCEPTION SWALLOWING & CORTEX REACHABILITY
    # =========================================================================
    def run_gate_6_observability_and_wiring(self) -> None:
        gate = "GATE-6:OBSERVABILITY"

        # 6.1 Ban `except Exception:` blocks that simply `pass` or `continue` without logging
        for py in find_py_files(["core", "web"]):
            rel = str(py.relative_to(ROOT))
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=rel)
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    # Flag bare `except: pass` or `except Exception: pass`
                    if len(node.body) == 1 and isinstance(node.body[0], (ast.Pass, ast.Continue)):
                        self.fail(
                            gate,
                            f"{rel}:{node.lineno}",
                            "Silent Exception Swallowing: Handler contains only pass/continue without logging telemetry.",
                        )
        self.ok(gate, "Zero silent exception handlers (pass/continue) across core/ and web/")

        # 6.2 Cortex Reachability: Verify GarudaReflexEngine is imported and wired in bse_watcher.py
        bse_watcher_path = ROOT / "core/agents/watchers/bse_watcher.py"
        if bse_watcher_path.exists():
            src = bse_watcher_path.read_text(encoding="utf-8")
            if "GarudaReflexEngine" not in src or "GarudaReflexEngine.classify_announcement" not in src:
                self.fail(
                    gate,
                    "core/agents/watchers/bse_watcher.py",
                    "Orphaned Cortex Engine: GarudaReflexEngine is not actively wired into bse_watcher.py.",
                )
            else:
                self.ok(gate, "GarudaReflexEngine actively wired into bse_watcher.py")

        # 6.3 DRY Security Crypto: Verify duplicate generate_rfc6238_totp removed from angel_one.py
        angel_path = ROOT / "core/ingestion/angel_one.py"
        if angel_path.exists():
            src = angel_path.read_text(encoding="utf-8")
            if "def generate_rfc6238_totp" in src:
                self.fail(
                    gate,
                    "core/ingestion/angel_one.py",
                    "Duplicate Crypto Implementation: generate_rfc6238_totp duplicated in angel_one.py instead of importing canonical core.auth.totp.",
                )
            elif "from core.auth.totp import" not in src:
                self.fail(
                    gate,
                    "core/ingestion/angel_one.py",
                    "Missing Canonical TOTP Import: angel_one.py must import canonical TOTP generator from core.auth.totp.",
                )
            else:
                self.ok(gate, "angel_one.py delegates TOTP generation to canonical core.auth.totp")

    def report(self) -> int:
        print("=" * 76)
        print("MOATNOMICS ZERO-ILLUSION REALITY & SECURITY AUDIT")
        print("=" * 76)
        for msg in self.passed:
            print(f"  PASS  {msg}")
        print("-" * 76)
        if not self.failures:
            print("ALL 6 REALITY GATES PASSED (0 vulnerabilities, 0 broken contracts).")
            return 0

        print(f"AUDIT FAILED: {len(self.failures)} REAL ISSUE(S) DETECTED:\n")
        for idx, (gate, loc, msg) in enumerate(self.failures, 1):
            print(f"  {idx:02d}. [{gate}] {loc}\n      -> {msg}")
        print("=" * 76)
        return 1


if __name__ == "__main__":
    auditor = RealityAuditor()
    auditor.run_gate_1_security()
    auditor.run_gate_2_ast_contracts()
    auditor.run_gate_3_sql_schema()
    auditor.run_gate_4_anti_potemkin()
    auditor.run_gate_5_behavioral()
    auditor.run_gate_6_observability_and_wiring()
    sys.exit(auditor.report())

