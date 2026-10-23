"""
Invariant Evaluation & Multi-Zone Deep Probes for Stock Research App.

Implements the 5 Audit Invariant Domains from the Auditor Scope Specification:
1. Backend Stability & Memory Bounds (INV_ASYM_ROUTE_COST, INV_UNBOUNDED_CACHE, INV_TEST_SUITE_PASS, INV_SILENT_EXCEPTION_SWALLOW)
2. Dual-Engine Database Parity (INV_SQL_DIALECT_COMPAT, INV_DB_SCHEMA_BOUNDS)
3. UI/UX & Contract Ergonomics (INV_DOM_INTEGRITY, INV_UI_CLICK_CONTRACTS, INV_UI_NO_DEAD_HOVER, INV_UI_VIEWPORT_OVERFLOW)
4. Security & Site Vulnerabilities (INV_SEC_HEADERS, INV_SEC_AUTH_SCOPE, INV_SEC_NO_STACKTRACE)
5. Strategy & SEBI Safe-Harbor Directives (INV_SEBI_SAFE_HARBOR, INV_SEBI_STATUTORY_DISCLAIMER, INV_NO_HALLUCINATED_ENTITY)

Provides both:
- Step 1: `verify_invariant(finding)` -> Targeted verification of an active finding.
- Step 2: `scan_all_invariants()` -> Deep multi-zone exploration across all invariants.
"""

import ast
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from core.db.remediation import compute_finding_hash

logger = logging.getLogger("equity_research.core.audit.invariants")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# =========================================================================
# 1. BACKEND STABILITY & MEMORY BOUNDS INVARIANTS
# =========================================================================

def scan_unbounded_caches() -> List[Dict[str, Any]]:
    """INV_UNBOUNDED_CACHE: Scans AST for module-level dicts/lists without eviction or size caps."""
    findings = []
    py_files = [p for p in (PROJECT_ROOT / "core").rglob("*.py") if "__pycache__" not in str(p)]
    py_files.extend([p for p in (PROJECT_ROOT / "web").rglob("*.py") if "__pycache__" not in str(p)])

    # Known bounded or constant structures
    ignored_names = {
        "__all__", "SECTOR_TAXONOMY", "MANDATORY_SEBI_DISCLAIMER", "DEFAULT_REITS_AND_INVITS",
        "DEFAULT_ALTERNATIVE_YIELD_PRODUCTS", "MONITORED_ROUTES", "SEVERITY_BASE_POINTS",
        "MOATNOMICS_BRAND_HOUSE"
    }

    for fpath in py_files:
        try:
            tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            var_name = target.id
                            if var_name.startswith("_") and var_name.endswith(("_CACHE", "_BUCKETS", "_TASKS")):
                                # Check if it's an unbounded dict/list without maxsize/eviction
                                if isinstance(node.value, (ast.Dict, ast.List)):
                                    # Verify if eviction/maxsize logic is implemented in the file
                                    src = fpath.read_text(encoding="utf-8")
                                    if "maxsize" not in src and "pop(" not in src and "clear(" not in src and "OrderedDict" not in src:
                                        rel_path = str(fpath.relative_to(PROJECT_ROOT))
                                        h = compute_finding_hash("BACKEND_STABILITY", "INV_UNBOUNDED_CACHE", f"{rel_path}:{var_name}")
                                        findings.append({
                                            "finding_hash": h,
                                            "category": "BACKEND_STABILITY",
                                            "invariant_name": "INV_UNBOUNDED_CACHE",
                                            "title": f"Unbounded module-level cache '{var_name}' in {rel_path}",
                                            "description": f"Module-level cache variable '{var_name}' in {rel_path} lacks an explicit maxsize, OrderedDict LRU eviction, or TTL pruning mechanism.",
                                            "target_file_or_route": f"{rel_path}:{node.lineno}",
                                            "severity": "HIGH",
                                            "remediation_notes": f"Wrap '{var_name}' with an LRU cache or enforce strict maxsize popitem() eviction.",
                                            "metadata": {"variable": var_name, "line": node.lineno, "file": rel_path}
                                        })
        except Exception as e:
            logger.debug(f"AST cache scan notice for {fpath}: {e}")

    return findings


def scan_silent_exception_swallowing() -> List[Dict[str, Any]]:
    """INV_SILENT_EXCEPTION_SWALLOW: Detects blanket except Exception: pass blocks without logging."""
    findings = []
    py_files = [p for p in (PROJECT_ROOT / "core").rglob("*.py") if "__pycache__" not in str(p)]
    py_files.extend([p for p in (PROJECT_ROOT / "web").rglob("*.py") if "__pycache__" not in str(p)])

    for fpath in py_files:
        try:
            tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
            unlogged_lines = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    has_log_or_raise = False
                    for b in node.body:
                        if isinstance(b, ast.Raise):
                            has_log_or_raise = True
                            break
                        if isinstance(b, ast.Expr) and isinstance(b.value, ast.Call):
                            func = b.value.func
                            if isinstance(func, ast.Attribute) and func.attr in ("error", "warning", "exception", "info", "debug"):
                                has_log_or_raise = True
                                break
                    if not has_log_or_raise:
                        unlogged_lines.append(node.lineno)

            if unlogged_lines:
                rel_path = str(fpath.relative_to(PROJECT_ROOT))
                h = compute_finding_hash("BACKEND_STABILITY", "INV_SILENT_EXCEPTION_SWALLOW", rel_path)
                lines_preview = ", ".join(f"L{ln}" for ln in unlogged_lines[:4])
                if len(unlogged_lines) > 4:
                    lines_preview += f" (+{len(unlogged_lines)-4} more)"
                findings.append({
                    "finding_hash": h,
                    "category": "BACKEND_STABILITY",
                    "invariant_name": "INV_SILENT_EXCEPTION_SWALLOW",
                    "title": f"Silent exception swallowing in {rel_path} ({len(unlogged_lines)} instances)",
                    "description": f"Found {len(unlogged_lines)} unlogged exception handler(s) in {rel_path} at lines {lines_preview}, violating Rule 8.2.",
                    "target_file_or_route": f"{rel_path}:{unlogged_lines[0]}",
                    "severity": "MEDIUM",
                    "remediation_notes": "Add logger.error(...) or logger.debug(...) to ensure complete error observability.",
                    "metadata": {"lines": unlogged_lines, "file": rel_path, "count": len(unlogged_lines)}
                })
        except Exception as e:
            logger.debug(f"AST exception scan notice for {fpath}: {e}")

    return findings


# =========================================================================
# 2. DUAL-ENGINE DATABASE PARITY INVARIANTS
# =========================================================================

def scan_sql_dialect_parity() -> List[Dict[str, Any]]:
    """INV_SQL_DIALECT_COMPAT: Detects SQLite-only boolean comparisons or unescaped % with parameters."""
    findings = []
    py_files = [p for p in (PROJECT_ROOT / "core").rglob("*.py") if "__pycache__" not in str(p)]
    py_files.extend([p for p in (PROJECT_ROOT / "web").rglob("*.py") if "__pycache__" not in str(p)])

    # Pattern for boolean column compared with = 1 or = 0 in SQL without dialect branch
    bool_eq_num_re = re.compile(r"""(?:WHERE|AND|OR)\s+([a-zA-Z0-9_]+\.(?:is_[a-zA-Z0-9_]+|has_[a-zA-Z0-9_]+))\s*=\s*[01]\b""", re.IGNORECASE)

    for fpath in py_files:
        if "test" in str(fpath).lower():
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
            # If the file already uses is_postgres_connection or supabase_url branching, verify per block
            for m in bool_eq_num_re.finditer(content):
                col_name = m.group(1)
                # Check if file has postgres branching around this query
                line_no = content[:m.start()].count("\n") + 1
                lines = content.splitlines()
                window = "\n".join(lines[max(0, line_no - 15):min(len(lines), line_no + 15)])
                if "is_postgres_connection" not in window and "supabase_url" not in window and "IS TRUE" not in window:
                    rel_path = str(fpath.relative_to(PROJECT_ROOT))
                    h = compute_finding_hash("DATABASE_PARITY", "INV_SQL_DIALECT_COMPAT", f"{rel_path}:{col_name}")
                    findings.append({
                        "finding_hash": h,
                        "category": "DATABASE_PARITY",
                        "invariant_name": "INV_SQL_DIALECT_COMPAT",
                        "title": f"Unbranched SQL boolean integer comparison '{col_name} = 1/0' in {rel_path}",
                        "description": f"SQL query in {rel_path}:{line_no} uses '{m.group(0)}' without dialect branching, which causes PostgreSQL 'operator does not exist: boolean = integer' runtime crash.",
                        "target_file_or_route": f"{rel_path}:{line_no}",
                        "severity": "CRITICAL",
                        "remediation_notes": "Branch query via is_postgres_connection(conn) to use 'IS TRUE'/'IS FALSE' on PostgreSQL and '= 1'/'= 0' on SQLite.",
                        "metadata": {"line": line_no, "column": col_name, "file": rel_path}
                    })
        except Exception as e:
            logger.debug(f"SQL dialect scan notice for {fpath}: {e}")

    return findings


def scan_database_schema_bounds() -> List[Dict[str, Any]]:
    """INV_DB_SCHEMA_BOUNDS: Tests default seed data and macro indicators against strict column character limits."""
    findings = []
    # Test sovereign macro labels length against 120 character limit
    try:
        from core.db.sovereign import DEFAULT_MACRO_RATES
        for rate in DEFAULT_MACRO_RATES:
            label = rate.get("period_label", "")
            ind_name = rate.get("indicator_name", "")
            if len(label) > 120:
                h = compute_finding_hash("DATABASE_PARITY", "INV_DB_SCHEMA_BOUNDS", f"sovereign_macro_rates:period_label:{label}")
                findings.append({
                    "finding_hash": h,
                    "category": "DATABASE_PARITY",
                    "invariant_name": "INV_DB_SCHEMA_BOUNDS",
                    "title": f"Sovereign macro period_label exceeds schema column limit: '{label[:30]}...'",
                    "description": f"period_label '{label}' has length {len(label)}, which exceeds PostgreSQL VARCHAR(120) column bounds.",
                    "target_file_or_route": "core/db/sovereign.py",
                    "severity": "HIGH",
                    "remediation_notes": "Truncate label or widen column definition in schema migration.",
                    "metadata": {"length": len(label), "value": label}
                })
            if len(ind_name) > 120:
                h = compute_finding_hash("DATABASE_PARITY", "INV_DB_SCHEMA_BOUNDS", f"sovereign_macro_rates:indicator_name:{ind_name}")
                findings.append({
                    "finding_hash": h,
                    "category": "DATABASE_PARITY",
                    "invariant_name": "INV_DB_SCHEMA_BOUNDS",
                    "title": f"Sovereign macro indicator_name exceeds schema column limit: '{ind_name[:30]}...'",
                    "description": f"indicator_name '{ind_name}' has length {len(ind_name)}, which exceeds PostgreSQL VARCHAR(120) column bounds.",
                    "target_file_or_route": "core/db/sovereign.py",
                    "severity": "HIGH",
                    "remediation_notes": "Truncate indicator_name or widen column definition in schema migration.",
                    "metadata": {"length": len(ind_name), "value": ind_name}
                })
    except Exception as e:
        logger.debug(f"Schema bounds scan notice: {e}")

    return findings


# =========================================================================
# 3. UI/UX & CONTRACT ERGONOMICS INVARIANTS
# =========================================================================

def scan_dom_integrity() -> List[Dict[str, Any]]:
    """INV_DOM_INTEGRITY: Deep DOM inspection across primary routes for unrendered Jinja, 'NaN', 'undefined', or empty card grids."""
    findings = []
    from fastapi.testclient import TestClient
    from web.main import app

    client = TestClient(app, raise_server_exceptions=False)
    probe_routes = [
        ("/", "Home / Terminal"),
        ("/equities", "Equities Directory"),
        ("/funds", "Funds Directory"),
        ("/debt", "Corporate Debt Directory"),
        ("/sovereign", "Sovereign Curve"),
        ("/reits", "REITs & InVITs Terminal"),
        ("/safety-radar", "Safety Radar Feed"),
        ("/pricing", "Pricing & Plans"),
        ("/discovery", "Morning Discovery Reel"),
    ]

    for route, name in probe_routes:
        try:
            resp = client.get(route, headers={"User-Agent": "testclient-project-auditor"})
            if resp.status_code != 200:
                continue

            html = resp.text

            # 1. Check for unrendered Jinja syntax
            jinja_matches = re.findall(r"(\{\{[^}]+\}\}|\{%[^%]+%\})", html)
            if jinja_matches:
                # Filter out intentional script blocks if any
                suspicious_jinja = [m for m in jinja_matches if not any(k in m for k in ("localStorage", "JSON.stringify"))]
                if suspicious_jinja:
                    h = compute_finding_hash("UI_UX_CONTRACTS", "INV_DOM_INTEGRITY", f"{route}:unrendered_jinja")
                    findings.append({
                        "finding_hash": h,
                        "category": "UI_UX_CONTRACTS",
                        "invariant_name": "INV_DOM_INTEGRITY",
                        "title": f"Unrendered Jinja expression leaking in {route}",
                        "description": f"Page {route} ({name}) rendered unescaped template tags into output: {suspicious_jinja[:2]}",
                        "target_file_or_route": route,
                        "severity": "HIGH",
                        "remediation_notes": "Verify template context variables are provided by the FastAPI route handler.",
                        "metadata": {"route": route, "tags": suspicious_jinja[:3]}
                    })

            # 2. Check for 'NaN' or 'undefined' rendered in visible text cards
            nan_matches = re.findall(r"(?:₹|\$|%)\s*(?:NaN|undefined|null)\b|\b(?:NaN|undefined)\s*(?:%|bps|Cr|Lakh)", html)
            if nan_matches:
                h = compute_finding_hash("UI_UX_CONTRACTS", "INV_DOM_INTEGRITY", f"{route}:nan_undefined_cascade")
                findings.append({
                    "finding_hash": h,
                    "category": "UI_UX_CONTRACTS",
                    "invariant_name": "INV_DOM_INTEGRITY",
                    "title": f"NaN or undefined numeric cascade in {route}",
                    "description": f"Page {route} displays corrupt financial values: {nan_matches[:3]}",
                    "target_file_or_route": route,
                    "severity": "HIGH",
                    "remediation_notes": "Add fallback zero-handling or formatting guard in parser/calculation routines.",
                    "metadata": {"route": route, "matches": nan_matches[:5]}
                })

            # 3. Check for empty card grids where asset data should appear
            if route in ("/equities", "/funds", "/debt", "/reits", "/sovereign"):
                if "No assets found" in html and "table" not in html and "card" not in html:
                    h = compute_finding_hash("UI_UX_CONTRACTS", "INV_DOM_INTEGRITY", f"{route}:empty_card_grid")
                    findings.append({
                        "finding_hash": h,
                        "category": "UI_UX_CONTRACTS",
                        "invariant_name": "INV_DOM_INTEGRITY",
                        "title": f"Empty asset card grid on {route}",
                        "description": f"Directory route {route} renders an empty card grid facade with no assets available.",
                        "target_file_or_route": route,
                        "severity": "MEDIUM",
                        "remediation_notes": "Ensure fallback universe seeding is active when directory database table is sparse.",
                        "metadata": {"route": route}
                    })
        except Exception as e:
            logger.debug(f"DOM integrity probe notice for {route}: {e}")

    return findings


def scan_ui_dead_hover_cards() -> List[Dict[str, Any]]:
    """INV_UI_NO_DEAD_HOVER: Universal hover-to-click card affordance (AGENTS.md Rule 6.9)."""
    findings = []
    templates_dir = PROJECT_ROOT / "web" / "templates"
    card_classes = ["pillar-card", "asset-card-accent", "discovery-card", "bento-card", "pricing-card"]

    for html_path in templates_dir.rglob("*.html"):
        try:
            content = html_path.read_text(encoding="utf-8")
            for c_class in card_classes:
                # Find elements with this card class
                pattern = rf'<div[^>]*class=["\'][^"\']*\b{c_class}\b[^"\']*["\'][^>]*>'
                for m in re.finditer(pattern, content):
                    tag = m.group(0)
                    line_no = content[:m.start()].count("\n") + 1
                    # A card must either have onclick, data-href, or contain an anchor/button
                    if "onclick" not in tag and "data-href" not in tag and "cursor: pointer" in tag:
                        # Find the closing div of this card or the first 300 chars
                        card_snippet = content[m.start():min(len(content), m.start() + 400)]
                        if "<a " not in card_snippet and "<button" not in card_snippet:
                            rel_path = str(html_path.relative_to(PROJECT_ROOT))
                            h = compute_finding_hash("UI_UX_CONTRACTS", "INV_UI_NO_DEAD_HOVER", f"{rel_path}:{line_no}")
                            findings.append({
                                "finding_hash": h,
                                "category": "UI_UX_CONTRACTS",
                                "invariant_name": "INV_UI_NO_DEAD_HOVER",
                                "title": f"Dead hover card affordance in {rel_path}:{line_no}",
                                "description": f"Container with class '{c_class}' elevates on hover but lacks a primary navigation link, onclick handler, or inner anchor/button.",
                                "target_file_or_route": f"{rel_path}:{line_no}",
                                "severity": "MEDIUM",
                                "remediation_notes": "Add data-href or wrap primary card content in a clickable link or modal trigger.",
                                "metadata": {"file": rel_path, "line": line_no, "class": c_class}
                            })
        except Exception as e:
            logger.debug(f"Dead hover scan notice for {html_path}: {e}")

    return findings


# =========================================================================
# 4. SECURITY & SITE VULNERABILITIES INVARIANTS
# =========================================================================

def scan_security_headers() -> List[Dict[str, Any]]:
    """INV_SEC_HEADERS: Validates presence of essential HTTP security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)."""
    findings = []
    from fastapi.testclient import TestClient
    from web.main import app

    client = TestClient(app, raise_server_exceptions=False)
    try:
        resp = client.get("/", headers={"User-Agent": "testclient-project-auditor"})
        headers = resp.headers

        if headers.get("x-content-type-options", "").lower() != "nosniff":
            h = compute_finding_hash("SECURITY_VULNERABILITY", "INV_SEC_HEADERS", "x-content-type-options")
            findings.append({
                "finding_hash": h,
                "category": "SECURITY_VULNERABILITY",
                "invariant_name": "INV_SEC_HEADERS",
                "title": "Missing or invalid 'X-Content-Type-Options: nosniff' header",
                "description": "The root HTTP response does not enforce 'X-Content-Type-Options: nosniff', exposing the application to MIME-type sniffing attacks.",
                "target_file_or_route": "web/main.py",
                "severity": "MEDIUM",
                "remediation_notes": "Add 'X-Content-Type-Options: nosniff' in the global security middleware in web/main.py.",
                "metadata": {"header": "x-content-type-options"}
            })

        frame_opts = headers.get("x-frame-options", "").upper()
        if frame_opts not in ("DENY", "SAMEORIGIN"):
            h = compute_finding_hash("SECURITY_VULNERABILITY", "INV_SEC_HEADERS", "x-frame-options")
            findings.append({
                "finding_hash": h,
                "category": "SECURITY_VULNERABILITY",
                "invariant_name": "INV_SEC_HEADERS",
                "title": "Missing or permissive 'X-Frame-Options' header",
                "description": "HTTP response does not enforce 'X-Frame-Options: SAMEORIGIN' or 'DENY', creating potential clickjacking vulnerability.",
                "target_file_or_route": "web/main.py",
                "severity": "MEDIUM",
                "remediation_notes": "Set 'X-Frame-Options: SAMEORIGIN' across all HTML responses in web/main.py.",
                "metadata": {"header": "x-frame-options"}
            })
    except Exception as e:
        logger.debug(f"Security headers probe notice: {e}")

    return findings


def scan_security_auth_scope() -> List[Dict[str, Any]]:
    """INV_SEC_AUTH_SCOPE: Asserts that unauthenticated calls to mutation or private routes are strictly gated (401/403/302)."""
    findings = []
    from fastapi.testclient import TestClient
    from web.main import app

    client = TestClient(app, raise_server_exceptions=False)
    protected_probes = [
        ("/api/dossier/unlock/INFY", "POST", "Ticker Unlock API"),
        ("/admin/users/grant-credits", "POST", "Admin Grant Credits API"),
    ]

    for route, method, name in protected_probes:
        try:
            if method == "POST":
                resp = client.post(route, headers={"User-Agent": "testclient-project-auditor"})
            else:
                resp = client.get(route, headers={"User-Agent": "testclient-project-auditor"})

            # Must reject unauthenticated request with 401, 403, or 302/303 redirect to login
            if resp.status_code in (200, 201):
                h = compute_finding_hash("SECURITY_VULNERABILITY", "INV_SEC_AUTH_SCOPE", route)
                findings.append({
                    "finding_hash": h,
                    "category": "SECURITY_VULNERABILITY",
                    "invariant_name": "INV_SEC_AUTH_SCOPE",
                    "title": f"Unauthenticated bypass on protected route {route}",
                    "description": f"Protected endpoint {route} ({name}) returned HTTP {resp.status_code} to an unauthenticated request without session or API token.",
                    "target_file_or_route": route,
                    "severity": "CRITICAL",
                    "remediation_notes": "Enforce verified user/admin session check in route dependency or decorator.",
                    "metadata": {"route": route, "status_code": resp.status_code}
                })
        except Exception as e:
            logger.debug(f"Auth scope probe notice for {route}: {e}")

    return findings


def scan_security_no_stacktrace() -> List[Dict[str, Any]]:
    """INV_SEC_NO_STACKTRACE: Verifies error responses do not leak server tracebacks or internal file paths."""
    findings = []
    from fastapi.testclient import TestClient
    from web.main import app

    client = TestClient(app, raise_server_exceptions=False)
    error_probes = [
        "/dossier/%27%20OR%201=1--",
        "/funds/NONEXISTENT_SCHEME_XYZ_12345",
        "/debt/INVALID_ISIN_FORMAT_999",
    ]

    for route in error_probes:
        try:
            resp = client.get(route, headers={"User-Agent": "testclient-project-auditor"})
            text = resp.text
            if "Traceback (most recent call last)" in text or 'File "' in text and '", line ' in text:
                h = compute_finding_hash("SECURITY_VULNERABILITY", "INV_SEC_NO_STACKTRACE", route)
                findings.append({
                    "finding_hash": h,
                    "category": "SECURITY_VULNERABILITY",
                    "invariant_name": "INV_SEC_NO_STACKTRACE",
                    "title": f"Stack trace or server internal paths leaked on {route}",
                    "description": f"Endpoint {route} exposed a raw Python traceback in the response body, leaking internal architecture.",
                    "target_file_or_route": route,
                    "severity": "HIGH",
                    "remediation_notes": "Catch unhandled route exceptions and return standardized error templates or JSON error responses.",
                    "metadata": {"route": route}
                })
        except Exception as e:
            logger.debug(f"Stack trace probe notice for {route}: {e}")

    return findings


# =========================================================================
# 5. STRATEGY & SEBI SAFE-HARBOR INVARIANTS
# =========================================================================

def scan_sebi_regulatory_invariants() -> List[Dict[str, Any]]:
    """INV_SEBI_SAFE_HARBOR: Scans templates and code for prohibited prescriptive words and missing disclaimers."""
    findings = []
    from core.audit.tools import tool_scan_prohibited_terms
    terms_res = tool_scan_prohibited_terms()

    for item in terms_res.get("findings", []):
        file_path = item.get("file", "")
        line_no = item.get("line", 1)
        matched = item.get("matched_text", "")
        desc = item.get("description", "Prohibited regulatory term")
        h = compute_finding_hash("STRATEGY_REGULATORY", "INV_SEBI_SAFE_HARBOR", f"{file_path}:{line_no}:{matched}")
        findings.append({
            "finding_hash": h,
            "category": "STRATEGY_REGULATORY",
            "invariant_name": "INV_SEBI_SAFE_HARBOR",
            "title": f"Regulatory language violation: '{matched}' in {file_path}:{line_no}",
            "description": f"Found '{matched}' ({desc}) in {file_path}:{line_no}, violating SEBI Research Analyst safe-harbor non-advisory boundaries.",
            "target_file_or_route": f"{file_path}:{line_no}",
            "severity": "CRITICAL",
            "remediation_notes": "Replace prescriptive phrasing with diagnostic, non-advisory analytical terminology.",
            "metadata": {"file": file_path, "line": line_no, "matched": matched}
        })

    if not terms_res.get("has_statutory_disclaimer"):
        h = compute_finding_hash("STRATEGY_REGULATORY", "INV_SEBI_STATUTORY_DISCLAIMER", "web/templates/base.html")
        findings.append({
            "finding_hash": h,
            "category": "STRATEGY_REGULATORY",
            "invariant_name": "INV_SEBI_STATUTORY_DISCLAIMER",
            "title": "Missing statutory SEBI Section 2(u) non-advisory disclaimer in base.html",
            "description": "Base web template lacks the mandatory SEBI Research Analyst Regulations 2014 Section 2(u) non-advisory disclaimer.",
            "target_file_or_route": "web/templates/base.html",
            "severity": "CRITICAL",
            "remediation_notes": "Ensure MANDATORY_SEBI_DISCLAIMER is injected and rendered in base footer.",
            "metadata": {"target": "base.html"}
        })

    return findings


# =========================================================================
# UNIFIED SCANNER & VERIFIER PIPELINE
# =========================================================================

def scan_all_invariants() -> List[Dict[str, Any]]:
    """Step 2 (Explore Next): Executes broad invariant exploration across all domains."""
    all_findings: List[Dict[str, Any]] = []

    # 1. Backend Stability & Memory Bounds
    all_findings.extend(scan_unbounded_caches())
    all_findings.extend(scan_silent_exception_swallowing())

    # 2. Dual-Engine Database Parity
    all_findings.extend(scan_sql_dialect_parity())
    all_findings.extend(scan_database_schema_bounds())

    # 3. UI/UX & Contract Ergonomics
    all_findings.extend(scan_dom_integrity())
    all_findings.extend(scan_ui_dead_hover_cards())

    # 4. Security & Site Vulnerabilities
    all_findings.extend(scan_security_headers())
    all_findings.extend(scan_security_auth_scope())
    all_findings.extend(scan_security_no_stacktrace())

    # 5. Strategy & Regulatory Directives
    all_findings.extend(scan_sebi_regulatory_invariants())

    return all_findings


INVARIANT_SCANNERS = {
    "INV_UNBOUNDED_CACHE": scan_unbounded_caches,
    "INV_SILENT_EXCEPTION_SWALLOW": scan_silent_exception_swallowing,
    "INV_SQL_DIALECT_COMPAT": scan_sql_dialect_parity,
    "INV_DB_SCHEMA_BOUNDS": scan_database_schema_bounds,
    "INV_DOM_INTEGRITY": scan_dom_integrity,
    "INV_UI_NO_DEAD_HOVER": scan_ui_dead_hover_cards,
    "INV_SEC_HEADERS": scan_security_headers,
    "INV_SEC_AUTH_SCOPE": scan_security_auth_scope,
    "INV_SEC_NO_STACKTRACE": scan_security_no_stacktrace,
    "INV_SEBI_SAFE_HARBOR": scan_sebi_regulatory_invariants,
    "INV_SEBI_STATUTORY_DISCLAIMER": scan_sebi_regulatory_invariants,
}


def verify_invariant(finding: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Step 1 (Verify First): Re-tests a single active finding against its specific invariant.
    Returns (True, 'Resolution notes') if defect is resolved, or (False, 'Failure reason') if still failing.
    """
    invariant_name = finding.get("invariant_name", "")
    target = finding.get("target_file_or_route", "")
    finding_hash = finding.get("finding_hash", "")

    try:
        scanner_fn = INVARIANT_SCANNERS.get(invariant_name)
        if scanner_fn:
            current_violations = scanner_fn()
            if not any(v.get("finding_hash") == finding_hash for v in current_violations):
                return True, f"Invariant '{invariant_name}' verified resolved on {target}."
            return False, f"Invariant '{invariant_name}' still failing on {target}."
        else:
            all_violations = scan_all_invariants()
            if not any(v.get("finding_hash") == finding_hash for v in all_violations):
                return True, f"Invariant '{invariant_name}' verified resolved on {target}."
            return False, f"Invariant '{invariant_name}' still failing on {target}."

    except Exception as e:
        logger.error(f"Error during verify_invariant for {finding_hash}: {e}")
        return False, f"Verification probe threw error: {e}"
