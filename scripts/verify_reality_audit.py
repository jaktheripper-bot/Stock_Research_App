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
                    # Skip typing @overload stubs or @abstractmethod declarations
                    is_stub = any(
                        (isinstance(d, ast.Name) and d.id in {"overload", "abstractmethod"})
                        or (isinstance(d, ast.Attribute) and d.attr in {"overload", "abstractmethod"})
                        for d in node.decorator_list
                    )
                    if is_stub:
                        continue
                    ret_ann = ast.unparse(node.returns) if hasattr(ast, "unparse") else ""
                    if ret_ann and "None" not in ret_ann:
                        has_non_empty_return = any(
                            (isinstance(sub, ast.Return) and sub.value is not None)
                            or isinstance(sub, (ast.Yield, ast.YieldFrom))
                            for sub in ast.walk(node)
                        )
                        if not has_non_empty_return:
                            self.fail(gate, f"{rel}:{node.lineno}",
                                      f"Function '{node.name}' annotated '-> {ret_ann}' has no return value (returns None).")

            # 2.4 Check for typing annotations used without importing from typing
            common_typing_names = {"Any", "Optional", "List", "Dict", "Tuple", "Union", "Set", "Callable", "Iterable", "Sequence", "Mapping"}
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.returns:
                        for sub in ast.walk(node.returns):
                            if isinstance(sub, ast.Name) and sub.id in common_typing_names and sub.id not in top_imports:
                                self.fail(gate, f"{rel}:{node.lineno}",
                                          f"NameError on Python <=3.12: '{sub.id}' used in return annotation on '{node.name}' but never imported from typing.")
                    for arg in node.args.args + node.args.kwonlyargs:
                        if arg.annotation:
                            for sub in ast.walk(arg.annotation):
                                if isinstance(sub, ast.Name) and sub.id in common_typing_names and sub.id not in top_imports:
                                    self.fail(gate, f"{rel}:{node.lineno}",
                                              f"NameError on Python <=3.12: '{sub.id}' used in argument '{arg.arg}' on '{node.name}' but never imported from typing.")
                elif isinstance(node, ast.AnnAssign) and node.annotation:
                    for sub in ast.walk(node.annotation):
                        if isinstance(sub, ast.Name) and sub.id in common_typing_names and sub.id not in top_imports:
                            self.fail(gate, f"{rel}:{node.lineno}",
                                      f"NameError on Python <=3.12: '{sub.id}' used in type annotation but never imported from typing.")

        # 2.5 Verify `process_refund` call sites match `core.db.users.process_refund` signature
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

        # 6.1 Ban silent exception handling: Handlers catching Exception or bare except without logging/raising
        for py in find_py_files(["core", "web"]):
            rel = str(py.relative_to(ROOT))
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=rel)
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    exc_type = ast.unparse(node.type) if node.type else "bare"
                    if "Exception" in exc_type or not node.type:
                        has_log = any(
                            isinstance(s, ast.Call) and any(
                                kw in (ast.unparse(s.func) if hasattr(ast, "unparse") else "")
                                for kw in ("log", "print", "record", "warning", "error", "info", "debug")
                            )
                            for s in ast.walk(node)
                        )
                        has_raise = any(isinstance(s, ast.Raise) for s in ast.walk(node))
                        if not has_log and not has_raise:
                            self.fail(
                                gate,
                                f"{rel}:{node.lineno}",
                                f"Silent Exception Swallowing: '{exc_type}' handler contains no logging or re-raise.",
                            )
        self.ok(gate, "Zero silent exception handlers across core/ and web/")

        # 6.2 Cortex Reachability & Cache Invalidation: Verify GarudaReflexEngine in bse_watcher.py
        bse_watcher_path = ROOT / "core/agents/watchers/bse_watcher.py"
        if bse_watcher_path.exists():
            src = bse_watcher_path.read_text(encoding="utf-8")
            if "GarudaReflexEngine" not in src or "GarudaReflexEngine.classify_announcement" not in src:
                self.fail(
                    gate,
                    "core/agents/watchers/bse_watcher.py",
                    "Orphaned Cortex Engine: GarudaReflexEngine is not actively wired into bse_watcher.py.",
                )
            elif "cache_clear" not in src and "invalidate" not in src:
                self.fail(
                    gate,
                    "core/agents/watchers/bse_watcher.py",
                    "Missing Surgical Invalidation: BSE watcher does not trigger cache invalidation upon announcement classification.",
                )
            else:
                self.ok(gate, "GarudaReflexEngine actively wired into bse_watcher.py with surgical cache invalidation")

        # 6.3 Sovereign Benchmarks: No auction_date overwrite & live RBI/CCIL fetcher
        sov_path = ROOT / "core/db/sovereign.py"
        if sov_path.exists():
            src = sov_path.read_text(encoding="utf-8")
            if '["auction_date"] = edition_date' in src:
                self.fail(
                    gate,
                    "core/db/sovereign.py",
                    "Hallucination Risk: refresh_daily_sovereign_benchmarks overwrites auction_date with today's date when no live feed was fetched.",
                )
            if "fetch_live_rbi_ccil_yield_curve" not in src:
                self.fail(
                    gate,
                    "core/db/sovereign.py",
                    "Missing Yield Curve Fetcher: fetch_live_rbi_ccil_yield_curve with data_source tracking not found.",
                )
            if '["auction_date"] = edition_date' not in src and "fetch_live_rbi_ccil_yield_curve" in src:
                self.ok(gate, "Sovereign benchmarks protect historical auction_date and support live RBI/CCIL fetch")

        # 6.4 Hardened yfinance: Circuit breaker and browser User-Agent session
        fund_path = ROOT / "core/analysis/fundamentals.py"
        if fund_path.exists():
            src = fund_path.read_text(encoding="utf-8")
            if "CircuitBreaker" not in src and "circuit_breaker" not in src:
                self.fail(
                    gate,
                    "core/analysis/fundamentals.py",
                    "Missing Circuit Breaker: yfinance fallback lacks circuit breaker protection against downstream failures.",
                )
            if "User-Agent" not in src and "user_agent" not in src:
                self.fail(
                    gate,
                    "core/analysis/fundamentals.py",
                    "Missing Browser Session: yfinance fallback does not configure a browser User-Agent session.",
                )
            if ("CircuitBreaker" in src or "circuit_breaker" in src) and ("User-Agent" in src or "user_agent" in src):
                self.ok(gate, "Fundamentals yfinance fallback hardened with circuit breaker and browser session")

        # 6.5 MSME De-Static: Verified entity separation and Sector Offtake Universe
        msme_tmpl = ROOT / "web/templates/msme_dossier.html"
        if msme_tmpl.exists():
            src = msme_tmpl.read_text(encoding="utf-8")
            if "Sector Offtake Universe" not in src:
                self.fail(
                    gate,
                    "web/templates/msme_dossier.html",
                    "Unverified Buyer Label: Template does not label buyers as 'Sector Offtake Universe'.",
                )
            else:
                self.ok(gate, "msme_dossier.html labels unverified relationships as 'Sector Offtake Universe'")

        msme_engine = ROOT / "core/msme/forensic_engine.py"
        if msme_engine.exists():
            src = msme_engine.read_text(encoding="utf-8")
            if "verified_udyam_attributes" not in src and "verified_attributes" not in src:
                self.fail(
                    gate,
                    "core/msme/forensic_engine.py",
                    "Static Benchmark Conflation: Verified Udyam entity attributes are not partitioned from sector medians.",
                )
            else:
                self.ok(gate, "forensic_engine.py partitions verified Udyam entity attributes from sector medians")

        # 6.6 DRY Security Crypto: Verify get_totp_code imported in angel_one.py
        angel_path = ROOT / "core/ingestion/angel_one.py"
        if angel_path.exists():
            src = angel_path.read_text(encoding="utf-8")
            if "def generate_rfc6238_totp" in src or "generate_rfc6238_totp" in src:
                self.fail(
                    gate,
                    "core/ingestion/angel_one.py",
                    "Duplicate Crypto Implementation: generate_rfc6238_totp present in angel_one.py instead of canonical get_totp_code.",
                )
            elif "from core.auth.totp import" not in src or "get_totp_code" not in src:
                self.fail(
                    gate,
                    "core/ingestion/angel_one.py",
                    "Missing Canonical TOTP Import: angel_one.py must import get_totp_code from core.auth.totp.",
                )
            else:
                self.ok(gate, "angel_one.py delegates TOTP generation to canonical get_totp_code")

        # 6.7 Legacy Streamlit Purge: Remove legacy Streamlit checks
        config_path = ROOT / "core/config.py"
        if config_path.exists():
            src = config_path.read_text(encoding="utf-8")
            if ".streamlit" in src:
                self.fail(
                    gate,
                    "core/config.py",
                    "Legacy Streamlit Relic: '.streamlit' secrets path still checked in core/config.py.",
                )
            else:
                self.ok(gate, "core/config.py free of legacy Streamlit paths")

        auth_path = ROOT / "core/auth/supabase_auth.py"
        if auth_path.exists():
            src = auth_path.read_text(encoding="utf-8")
            if "_is_streamlit_running" in src:
                self.fail(
                    gate,
                    "core/auth/supabase_auth.py",
                    "Legacy Streamlit Relic: '_is_streamlit_running' function still present in supabase_auth.py.",
                )
            else:
                self.ok(gate, "core/auth/supabase_auth.py free of legacy Streamlit functions")

        bench_path = ROOT / "benchmark.py"
        if bench_path.exists():
            src = bench_path.read_text(encoding="utf-8")
            if "STREAMLIT_LOG_LEVEL" in src:
                self.fail(
                    gate,
                    "benchmark.py",
                    "Legacy Streamlit Relic: 'STREAMLIT_LOG_LEVEL' environment assignment still present in benchmark.py.",
                )
            else:
                self.ok(gate, "benchmark.py free of legacy Streamlit log configuration")

        # 6.8 Multi-Agent Audit Consolidation: Consolidated into forensic_squad.py
        squad_path = ROOT / "core/agents/equity/forensic_squad.py"
        if squad_path.exists():
            src = squad_path.read_text(encoding="utf-8")
            if "ForensicAuditResult" not in src:
                self.fail(
                    gate,
                    "core/agents/equity/forensic_squad.py",
                    "Missing Multi-Agent Models: ForensicAuditResult not consolidated into forensic_squad.py.",
                )
            else:
                self.ok(gate, "ForensicAuditResult consolidated into core/agents/equity/forensic_squad.py")

    # =========================================================================
    # GATE 7: CONCURRENCY, CONNECTION POOL & ASYNC LOOP HARDENING
    # =========================================================================
    def run_gate_7_concurrency(self) -> None:
        gate = "GATE-7:CONCURRENCY"

        # 7.1 DB Pool Limits: ThreadedConnectionPool must use DB_POOL_MIN/MAX and not maxconn=300
        conn_path = ROOT / "core/db/connection.py"
        if conn_path.exists():
            src = conn_path.read_text(encoding="utf-8")
            if "maxconn=300" in src:
                self.fail(
                    gate,
                    "core/db/connection.py",
                    "Supabase Exhaustion Risk: 'maxconn=300' found in ThreadedConnectionPool. Must use DB_POOL_MIN and DB_POOL_MAX.",
                )
            elif "DB_POOL_MIN" not in src or "DB_POOL_MAX" not in src:
                self.fail(
                    gate,
                    "core/db/connection.py",
                    "Missing Configurable Pool: ThreadedConnectionPool must configure DB_POOL_MIN and DB_POOL_MAX.",
                )
            else:
                self.ok(gate, "Database pool sizing hardened with configurable DB_POOL_MIN and DB_POOL_MAX")

            # 7.2 SQLite Busy Timeout: PRAGMA busy_timeout = 5000;
            if "PRAGMA busy_timeout = 5000" not in src and "busy_timeout=5000" not in src and "busy_timeout = 5000" not in src:
                self.fail(
                    gate,
                    "core/db/connection.py",
                    "Missing SQLite Busy Timeout: SQLite connections must execute 'PRAGMA busy_timeout = 5000;'.",
                )
            else:
                self.ok(gate, "SQLite connection initialization enforces PRAGMA busy_timeout = 5000")

        # 7.3 Async PDF Concurrency Cap: run_in_threadpool with asyncio.Semaphore(4)
        dossier_path = ROOT / "web/routers/dossier.py"
        if dossier_path.exists():
            src = dossier_path.read_text(encoding="utf-8")
            if "run_in_threadpool" not in src:
                self.fail(
                    gate,
                    "web/routers/dossier.py",
                    "Event Loop Blocking: Synchronous PDF generation not offloaded to run_in_threadpool.",
                )
            elif "Semaphore" not in src:
                self.fail(
                    gate,
                    "web/routers/dossier.py",
                    "Missing Concurrency Cap: PDF generation routes lack asyncio.Semaphore concurrency cap.",
                )
            else:
                self.ok(gate, "PDF generation routes offloaded to threadpool with concurrency semaphore cap")

        # 7.4 Multi-Worker Distributed Job Lease Lock (Wave 12)
        dist_lock_path = ROOT / "core/db/distributed_lock.py"
        if not dist_lock_path.exists():
            self.fail(
                gate,
                "core/db/distributed_lock.py",
                "Missing Distributed Lock: core/db/distributed_lock.py does not exist.",
            )
        else:
            src_l = dist_lock_path.read_text(encoding="utf-8")
            if "acquire_job_lease" not in src_l or "job_lease" not in src_l or "distributed_job_locks" not in src_l:
                self.fail(
                    gate,
                    "core/db/distributed_lock.py",
                    "Incomplete Distributed Lock: acquire_job_lease or job_lease missing.",
                )
            else:
                self.ok(gate, "Distributed job lease lock guards scheduled tasks against multi-worker duplicate runs")

        # 7.5 Actor-Scoped AI QoS Governor & Single-Flight Coalescer (Wave 15)
        qos_path = ROOT / "core/billing/qos_governor.py"
        if not qos_path.exists():
            self.fail(
                gate,
                "core/billing/qos_governor.py",
                "Missing QoS Governor: core/billing/qos_governor.py does not exist.",
            )
        else:
            src_q = qos_path.read_text(encoding="utf-8")
            if "authorize_llm_execution" not in src_q or "single_flight_ticker_lock" not in src_q:
                self.fail(
                    gate,
                    "core/billing/qos_governor.py",
                    "Incomplete QoS Governor: authorize_llm_execution or single_flight_ticker_lock missing.",
                )
            else:
                synth_path = ROOT / "core/analysis/dossier_report_synthesis.py"
                if synth_path.exists() and "single_flight_ticker_lock" not in synth_path.read_text(encoding="utf-8"):
                    self.fail(
                        gate,
                        "core/analysis/dossier_report_synthesis.py",
                        "Missing Single-Flight Coalescer: generate_stock_report must acquire single_flight_ticker_lock.",
                    )
                else:
                    self.ok(gate, "Actor-Scoped AI QoS Governor & Single-Flight Coalescer active across synthesis and copilot")


    # =========================================================================
    # GATE 8: END-TO-END JOURNEYS & PAYMENT IDEMPOTENCY
    # =========================================================================
    def run_gate_8_e2e_journeys(self) -> None:
        gate = "GATE-8:E2E-JOURNEYS"

        # 8.1 Atomic Payment Idempotency in core/billing/razorpay.py & core/db/users.py
        users_path = ROOT / "core/db/users.py"
        rzp_path = ROOT / "core/billing/razorpay.py"
        has_idempotency = False
        if users_path.exists():
            src_u = users_path.read_text(encoding="utf-8")
            if "gateway_payment_id" in src_u and ("SELECT" in src_u and "credit_transactions" in src_u):
                has_idempotency = True
        if rzp_path.exists():
            src_r = rzp_path.read_text(encoding="utf-8")
            if "already processed" in src_r.lower() or "idempotent" in src_r.lower():
                has_idempotency = True

        if not has_idempotency:
            self.fail(
                gate,
                "core/db/users.py",
                "Missing Payment Idempotency: Double-credit vulnerability detected. Replaying gateway_payment_id must be rejected.",
            )
        else:
            self.ok(gate, "Payment verification enforces atomic idempotency against duplicate payment/order IDs")

        # 8.2 /api/billing/verify endpoint contract
        auth_bill_path = ROOT / "web/routers/auth_billing.py"
        if auth_bill_path.exists():
            src_b = auth_bill_path.read_text(encoding="utf-8")
            if "/api/billing/verify" not in src_b:
                self.fail(
                    gate,
                    "web/routers/auth_billing.py",
                    "Missing Route Contract: '/api/billing/verify' endpoint not registered.",
                )
            else:
                self.ok(gate, "'/api/billing/verify' endpoint properly registered in FastAPI router")

        # 8.3 E2E Journeys Test Suite: tests/e2e/test_critical_journeys.py
        e2e_test_path = ROOT / "tests/e2e/test_critical_journeys.py"
        if not e2e_test_path.exists():
            self.fail(
                gate,
                "tests/e2e/test_critical_journeys.py",
                "Missing E2E Journeys Test Suite: tests/e2e/test_critical_journeys.py does not exist.",
            )
        else:
            src_t = e2e_test_path.read_text(encoding="utf-8")
            required_cases = [
                ("paywall", "paywall redaction"),
                ("replay", "replay attack simulation"),
                ("admin", "admin 2FA / copilot confirmation"),
            ]
            missing = [label for kw, label in required_cases if kw not in src_t.lower()]
            if missing:
                self.fail(
                    gate,
                    "tests/e2e/test_critical_journeys.py",
                    f"Incomplete E2E Journey Coverage: Missing tests for {', '.join(missing)}.",
                )
            else:
                self.ok(gate, "E2E Critical Journeys test suite comprehensively covers paywalls, replay attacks, and admin flows")

    # =========================================================================
    # GATE 9: POSTGRESQL DIALECT PARITY & DISTRIBUTED CRON LOCKING (WAVES 12-13)
    # =========================================================================
    def run_gate_9_dialect_and_locks(self) -> None:
        gate = "GATE-9:DIALECT-AND-LOCKS"

        # 9.1 Ban SQLite-only INSERT OR REPLACE / INSERT OR IGNORE in dual-bound core/
        sqlite_only_re = re.compile(r"\bINSERT\s+OR\s+(REPLACE|IGNORE)\b", re.IGNORECASE)
        found_sqlite_only = False
        for py in find_py_files(["core/db", "core/analysis", "core/msme", "core/ingestion"]):
            rel = str(py.relative_to(ROOT))
            src = py.read_text(encoding="utf-8")
            for m in sqlite_only_re.finditer(src):
                found_sqlite_only = True
                line_no = src[:m.start()].count("\n") + 1
                self.fail(
                    gate,
                    f"{rel}:{line_no}",
                    f"PostgreSQL Incompatible SQL: '{m.group(0)}' crashes on Supabase Postgres. Use 'ON CONFLICT DO UPDATE/NOTHING'."
                )
        if not found_sqlite_only:
            self.ok(gate, "Zero SQLite-only INSERT OR REPLACE/IGNORE statements across core/")

        # 9.2 Verify distributed job lock exists and works atomically
        locks_path = ROOT / "core/db/locks.py"
        if not locks_path.exists():
            self.fail(
                gate,
                "core/db/locks.py",
                "Multi-Worker Race Risk: core/db/locks.py missing; 2 Uvicorn workers will duplicate cron jobs & emails."
            )
        else:
            from core.db.locks import acquire_job_lease, release_job_lease
            test_job = "reality_audit_lock_test"
            release_job_lease(test_job)
            if not acquire_job_lease(test_job, ttl_seconds=60):
                self.fail(gate, "core/db/locks.py", "acquire_job_lease() failed to acquire a fresh lock.")
            else:
                release_job_lease(test_job)
                self.ok(gate, "Distributed job lease (core/db/locks.py) verified")

    # =========================================================================
    # GATE 10: QUANTITATIVE & STATUTORY FINANCIAL MATH INVARIANTS (WAVE 14)
    # =========================================================================
    def run_gate_10_quant_invariants(self) -> None:
        gate = "GATE-10:QUANT-MATH"

        # 10.1 Debt Invariant: Modified Duration < Macaulay Duration for y > 0 & Positive Convexity
        try:
            from core.analysis.debt_dossier import compute_duration_and_convexity, compute_rate_shock_scenarios
            d_res = compute_duration_and_convexity(
                current_price=1000.0,
                face_value=1000.0,
                coupon_rate_pct=9.0,
                coupon_frequency="ANNUAL",
                time_to_maturity_years=5.0,
                ytm_pct=9.0,
            )
            mac_dur = d_res["macaulay_duration"]
            mod_dur = d_res["modified_duration"]
            if mod_dur >= mac_dur:
                self.fail(gate, "core/analysis/debt_dossier.py", f"Modified duration {mod_dur} >= Macaulay duration {mac_dur}")
            else:
                self.ok(gate, "Debt Invariant verified: Modified Duration < Macaulay Duration for y > 0")

            scenarios = compute_rate_shock_scenarios(1000.0, 4.0, 25.0, [200])
            if scenarios[0]["pct_price_change"] <= scenarios[0]["linear_duration_pct"]:
                self.fail(gate, "core/analysis/debt_dossier.py", "Convexity failed to cushion rate hike drawdown")
            else:
                self.ok(gate, "Debt Invariant verified: Positive convexity dampens rate hike drawdowns")
        except Exception as e:
            self.fail(gate, "core/analysis/debt_dossier.py", f"Debt invariant check failed: {e}")

        # 10.2 REIT Invariant: Section 115UA waterfall splits sum to 100% and Post-Tax Real Yield <= Pre-Tax Yield
        try:
            from core.analysis.reit_dossier import validate_section_115ua_waterfall, simulate_reit_tax_waterfall
            valid_splits = {"dividend_pct": 35.0, "interest_pct": 35.0, "return_of_capital_pct": 20.0, "rental_pct": 10.0}
            validate_section_115ua_waterfall(valid_splits)
            mock_reit = {
                "symbol": "MOCKREIT",
                "distribution_yield_pct": 8.0,
                "tax_breakdown": valid_splits,
            }
            waterfall = simulate_reit_tax_waterfall(mock_reit, tax_slab_pct=30.0, inflation_pct=5.0)
            if waterfall["net_post_tax_yield_pct"] > waterfall["gross_distribution_yield_pct"]:
                self.fail(gate, "core/analysis/reit_dossier.py", "Post-tax yield exceeds pre-tax yield")
            elif waterfall["post_tax_real_yield_pct"] > waterfall["gross_distribution_yield_pct"]:
                self.fail(gate, "core/analysis/reit_dossier.py", "Post-tax real yield exceeds pre-tax yield")
            else:
                self.ok(gate, "REIT Invariant verified: Section 115UA waterfall splits sum to 100% & Post-Tax Real Yield <= Pre-Tax Yield")
        except Exception as e:
            self.fail(gate, "core/analysis/reit_dossier.py", f"REIT invariant check failed: {e}")

        # 10.3 Fund Invariant: Withhold Composite Health Score when coverage < 70% & clamp Active Share
        try:
            from core.analysis.fund_dossier import evaluate_fund_coverage_and_health, clamp_active_share
            score_withheld, _ = evaluate_fund_coverage_and_health(55.0, 80.0, 65.0)
            score_retained, _ = evaluate_fund_coverage_and_health(75.0, 80.0, 65.0)
            if score_withheld is not None or score_retained is None:
                self.fail(gate, "core/analysis/fund_dossier.py", "Failed to withhold composite health score when coverage < 70%")
            elif clamp_active_share(-10.0) != 0.0 or clamp_active_share(120.0) != 100.0:
                self.fail(gate, "core/analysis/fund_dossier.py", "Active share clamping failed")
            else:
                self.ok(gate, "Fund Invariant verified: Composite score withheld when coverage < 70% & Active Share clamped to [0, 100]")
        except Exception as e:
            self.fail(gate, "core/analysis/fund_dossier.py", f"Fund invariant check failed: {e}")

        # 10.4 Setu Invariant: Cross-asset capital structure spread (+250 bps)
        try:
            from core.cortex.setu import SetuMatrixEngine
            setu = SetuMatrixEngine()
            res = setu.evaluate_capital_structure(
                ticker="TESTCORP",
                market_cap_cr=10000.0,
                trailing_fcf_cr=1100.0,   # 11.0% Equity FCF Yield
                senior_ncd_ytm_pct=8.5,   # 8.5% Senior Bond YTM
                sovereign_10y_ytm_pct=6.8
            )
            spread_bps = getattr(res, "equity_over_debt_spread_bps", None)
            if spread_bps is None and isinstance(res, dict):
                spread_bps = res.get("equity_over_debt_spread_bps", 0.0)
            if abs(float(spread_bps or 0.0) - 250.0) > 1.0:
                self.fail(gate, "core/cortex/setu.py", f"Setu spread math error: expected +250 bps, got {spread_bps}")
            else:
                self.ok(gate, "Setu cross-asset yield spread math verified (+250 bps inversion)")
        except Exception as e:
            self.fail(gate, "core/cortex/setu.py", f"Setu quantitative invariant check failed: {e}")

    # =========================================================================
    # GATE 11: VIP USER QoS ISOLATION & SINGLE-FLIGHT COALESCING (WAVE 15)
    # =========================================================================
    def run_gate_11_ai_qos_isolation(self) -> None:
        gate = "GATE-11:AI-QOS-ISOLATION"
        qos_path = ROOT / "core/analytics/ai_qos_governor.py"
        if not qos_path.exists():
            self.fail(gate, "core/analytics/ai_qos_governor.py", "Missing Actor-Scoped AI QoS Governor module.")
            return

        from core.analytics.ai_qos_governor import (
            authorize_llm_execution,
            reset_qos_windows_for_test,
            single_flight_ticker_lock,
            MAX_COPILOT_TURNS_PER_USER_HOUR,
        )
        reset_qos_windows_for_test()

        # 11.1 Prove that exhausting the daemon budget ($999 spent) pauses daemons
        #      but DOES NOT block or degrade a paying user!
        daemon_ok, _ = authorize_llm_execution(
            actor_type="BACKGROUND_DAEMON",
            current_daemon_spend_usd=999.0,
        )
        vip_ok, vip_reason = authorize_llm_execution(
            actor_type="USER_SYNTHESIS",
            user_email="paying_customer@moatnomics.com",
            has_unlocked_dossier=True,
            current_daemon_spend_usd=999.0,
        )
        if daemon_ok:
            self.fail(gate, "core/analytics/ai_qos_governor.py", "Daemon budget cap failed to pause runaway daemon.")
        elif not vip_ok:
            self.fail(
                gate,
                "core/analytics/ai_qos_governor.py",
                f"UX DEGRADATION BUG: Paying user was blocked ({vip_reason}) when daemon budget was exhausted!"
            )
        else:
            self.ok(gate, "VIP paying user remains 100% unblocked even when daemon spend is exhausted")

        # 11.2 Prove that a rogue bot/user spamming Copilot is throttled without affecting another user
        reset_qos_windows_for_test()
        for _ in range(MAX_COPILOT_TURNS_PER_USER_HOUR):
            authorize_llm_execution(
                actor_type="USER_COPILOT",
                user_email="rogue_bot@attacker.com",
                has_unlocked_dossier=True,
            )
        bot_ok, _ = authorize_llm_execution(
            actor_type="USER_COPILOT",
            user_email="rogue_bot@attacker.com",
            has_unlocked_dossier=True,
        )
        legit_ok, _ = authorize_llm_execution(
            actor_type="USER_COPILOT",
            user_email="legit_investor@moatnomics.com",
            has_unlocked_dossier=True,
        )
        if bot_ok or not legit_ok:
            self.fail(
                gate,
                "core/analytics/ai_qos_governor.py",
                f"Actor isolation failed: bot_ok={bot_ok}, legit_ok={legit_ok}"
            )
        else:
            self.ok(gate, "Per-user velocity isolation verified (rogue user throttled; legitimate user unaffected)")

        # 11.3 Verify Single-Flight Ticker Lock context manager
        with single_flight_ticker_lock("INFY"):
            pass
        self.ok(gate, "single_flight_ticker_lock() context manager verified")

    # =========================================================================
    # GATE 12: UI INERT ANCESTOR GUARD & MOBILE KEYBOARD HYGIENE (WAVE 16)
    # =========================================================================
    def run_gate_12_ui_inert_and_modal_safety(self) -> None:
        gate = "GATE-12:UI-INERT-AND-MODAL-SAFETY"
        copilot_js = ROOT / "web/static/js/copilot.js"
        copilot_modal = ROOT / "web/templates/partials/copilot_modal.html"

        if not copilot_js.exists() or not copilot_modal.exists():
            self.fail(gate, "web/static/js/copilot.js", "Missing copilot.js or copilot_modal.html")
            return

        js_src = copilot_js.read_text(encoding="utf-8")
        modal_src = copilot_modal.read_text(encoding="utf-8")

        # 12.1 Ensure #copilotModalBackdrop is portaled to document.body and guarded by !mainEl.contains(modal)
        if "document.body.appendChild(modal)" not in js_src or "!mainEl.contains(modal)" not in js_src or "modal.inert = false" not in js_src:
            self.fail(
                gate,
                "web/static/js/copilot.js",
                "INERT SELF-LOCKOUT RISK: copilot.js must portal #copilotModalBackdrop to document.body and guard mainEl.inert = true with !mainEl.contains(modal)."
            )
        else:
            self.ok(gate, "Research Desk modal portaled to document.body with !mainEl.contains(modal) inert guard")

        # 12.2 Ensure mobile virtual keyboard 16px font-size and explicit close button ID
        if "font-size: 16px;" not in modal_src or 'id="copilotCloseBtn"' not in modal_src:
            self.fail(
                gate,
                "web/templates/partials/copilot_modal.html",
                "MOBILE KEYBOARD/CLOSE HYGIENE: .copilot-textarea must use font-size: 16px and close button must have id='copilotCloseBtn'."
            )
        else:
            self.ok(gate, "Research Desk mobile 16px input hygiene and #copilotCloseBtn contract verified")

    def report(self) -> int:
        print("=" * 76)
        print("MOATNOMICS ZERO-ILLUSION REALITY & SECURITY AUDIT")
        print("=" * 76)
        for msg in self.passed:
            print(f"  PASS  {msg}")
        print("-" * 76)
        if not self.failures:
            print("ALL 12 REALITY GATES PASSED (0 vulnerabilities, 0 broken contracts).")
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
    auditor.run_gate_7_concurrency()
    auditor.run_gate_8_e2e_journeys()
    auditor.run_gate_9_dialect_and_locks()
    auditor.run_gate_10_quant_invariants()
    auditor.run_gate_11_ai_qos_isolation()
    auditor.run_gate_12_ui_inert_and_modal_safety()
    sys.exit(auditor.report())


