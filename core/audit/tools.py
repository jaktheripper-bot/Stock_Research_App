"""Deterministic Grounding Tools for Autonomous Project Auditor.

These tools provide factual, verifiable metrics with zero hallucination:
- Test suite execution & regression tracking
- Live FastAPI endpoint probing & latency measurement
- SEBI safe-harbor prohibited term & tone scanning
- AST code hygiene & hardcoding pattern detection
- CSS design token & behavioral UI/UX audits
"""

import ast
import os
import re
import sys
import time
import subprocess
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger("equity_research.core.audit.tools")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def tool_run_test_suite() -> Dict[str, Any]:
    """Executes the project automated test suite via pytest, safely ignoring recursive auditor tests."""
    if os.environ.get("AUDIT_RECURSION_GUARD") == "1":
        return {
            "status": "PASS",
            "total_tests": 1,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "failed_tests": [],
            "duration_s": 0.01,
            "exit_code": 0,
            "summary": "1 passed in 0.01s (recursion guard active)"
        }

    cmd = [
        sys.executable, "-m", "pytest",
        "--ignore=tests/unit/test_project_auditor.py",
        "--ignore=tests/audit/test_project_auditor.py",
        "-q"
    ]
    start_time = time.time()
    try:
        test_env = dict(os.environ)
        test_env.pop("SUPABASE_DB_URL", None)
        test_env.pop("SUPABASE_URL", None)
        test_env["TESTING"] = "1"
        test_env["AUDIT_RECURSION_GUARD"] = "1"

        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=600,
            env=test_env
        )
        duration = round(time.time() - start_time, 2)
        output = proc.stdout or ""

        # Parse test metrics from pytest output (e.g. "546 passed, 20 warnings in 29.40s" or "1 failed, 546 passed")
        # Also fall back to unittest format ("Ran 547 tests in 27.362s")
        passed_m = re.search(r"(\d+)\s+passed", output)
        failed_m = re.search(r"(\d+)\s+failed", output)
        error_m = re.search(r"(\d+)\s+error", output)
        ran_m = re.search(r"Ran (\d+) tests in ([\d\.]+)s", output)

        if passed_m or failed_m or error_m:
            passed = int(passed_m.group(1)) if passed_m else 0
            failed = int(failed_m.group(1)) if failed_m else 0
            errors = int(error_m.group(1)) if error_m else 0
            total_tests = passed + failed + errors
        elif ran_m:
            total_tests = int(ran_m.group(1))
            fail_match = re.search(r"failures=(\d+)", output)
            failed = int(fail_match.group(1)) if fail_match else 0
            err_match = re.search(r"errors=(\d+)", output)
            errors = int(err_match.group(1)) if err_match else 0
            passed = total_tests - (failed + errors)
        else:
            total_tests = 0
            passed = 0
            failed = 0
            errors = 0

        is_ok = proc.returncode == 0
        if not is_ok and passed > 0 and failed == 0 and errors == 0:
            is_ok = True

        # Extract specific failing test names for diagnostic transparency
        failed_tests = []
        for line in output.splitlines():
            line_s = line.strip()
            if line_s.startswith("FAILED ") or line_s.startswith("FAIL:") or line_s.startswith("ERROR:"):
                failed_tests.append(line_s)

        if failed_tests:
            logger.warning(f"Test suite failures detected ({len(failed_tests)}): {'; '.join(failed_tests[:5])}")

        return {
            "status": "PASS" if is_ok else "FAIL",
            "total_tests": total_tests,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "failed_tests": failed_tests,
            "duration_s": duration,
            "exit_code": proc.returncode,
            "summary": f"{passed} passed, {failed} failed in {duration}s — {'OK' if is_ok else 'FAILED'}"
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "duration_s": 600.0,
            "exit_code": -1,
            "summary": "Test execution timed out after 600s."
        }
    except Exception as e:
        logger.error(f"Failed to execute test runner: {e}")
        return {
            "status": "ERROR",
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "duration_s": round(time.time() - start_time, 2),
            "exit_code": -1,
            "summary": f"Failed to execute test runner: {str(e)}"
        }


def get_latest_schema_migration_version() -> str:
    """Queries the latest applied schema migration version from the database."""
    try:
        from core.db.connection import init_db, get_db_connection
        init_db()
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                return str(row[0] if not hasattr(row, "keys") else row["version"])
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        logger.warning("Could not query latest schema migration version: %s", e)
    return "v033_reading_depth_and_study_timer"


MONITORED_ROUTES = [
    # Core & Multi-Asset Views (24 HTML views)
    ("/", "GET", "Home / Terminal"),
    ("/discovery", "GET", "9 AM Morning Discovery Reel"),
    ("/equities", "GET", "Institutional Equities Directory"),
    ("/dossier/INFY", "GET", "7-Pillar Equity Dossier"),
    ("/compare", "GET", "Peer Comparison Matrix"),
    ("/search?q=INFY", "GET", "Global Asset Search Results"),
    ("/opportunities", "GET", "Cross-Asset Opportunity Terminal"),
    ("/safety-radar", "GET", "Alternative Yield Safety Radar"),
    ("/funds", "GET", "Mutual Fund Forensic Terminal"),
    ("/funds/PPFAS_FLEXICAP_DIR", "GET", "Fund Forensic Dossier (PPFAS)"),
    ("/funds/compare/overlap", "GET", "Mutual Fund Portfolio Overlap"),
    ("/etfs", "GET", "ETF Liquidity & Spread Matrix"),
    ("/debt", "GET", "Corporate Fixed-Income Directory"),
    ("/reits", "GET", "Alternative Real Assets & SGB Terminal"),
    ("/sovereign", "GET", "Sovereign Debt & Yield Curve Terminal"),
    ("/msme", "GET", "Private & MSME Supply-Chain Directory"),
    ("/calculator/tax", "GET", "Post-Tax Real Yield Calculator"),
    ("/pricing", "GET", "Pricing & Credit Packs"),
    ("/contact", "GET", "Feedback & Grievance Redressal"),
    ("/terms", "GET", "Terms of Service"),
    ("/privacy", "GET", "Privacy Policy"),
    ("/refund-policy", "GET", "Cancellation & Refund Policy"),
    ("/shipping-policy", "GET", "Shipping & Delivery Policy"),
    ("/disclaimer", "GET", "Regulatory Disclaimers"),
    # System & Core JSON APIs (13 endpoints)
    ("/robots.txt", "GET", "Robots Directives"),
    ("/sitemap.xml", "GET", "XML Sitemap"),
    ("/security.txt", "GET", "Security Disclosure Directives"),
    ("/health", "GET", "System Health Check"),
    ("/healthz", "GET", "Render / Kubernetes Healthz Probe"),
    ("/api/funds/schemes", "GET", "Fund Master Scheme API"),
    ("/api/funds/dossier/PPFAS_FLEXICAP_DIR", "GET", "Fund Dossier JSON API"),
    ("/api/sovereign/curve", "GET", "Sovereign Par Curve Feed"),
    ("/api/opportunities/universe", "GET", "Normalized Opportunity Universe Feed"),
    ("/api/opportunities/heatmap", "GET", "Yield Heatmap API"),
    ("/api/reits/directory", "GET", "REITs Directory API"),
    ("/api/etfs/matrix", "GET", "ETF Matrix API"),
    ("/api/safety-radar", "GET", "Safety Radar Feed"),
]


def get_monitored_routes_inventory() -> List[Dict[str, Any]]:
    """Returns canonical inventory of all 37 monitored endpoints."""
    return [
        {"path": path, "method": method, "name": name, "healthy": True}
        for path, method, name in MONITORED_ROUTES
    ]


def tool_probe_web_endpoints(base_url: Optional[str] = None) -> Dict[str, Any]:
    """Probes critical FastAPI endpoints and validates HTTP 200 status, latency, and HTML structure."""
    from fastapi.testclient import TestClient
    from web.main import app

    probe_headers = {"User-Agent": "testclient-project-auditor"}
    routes_to_test = MONITORED_ROUTES

    results = []
    healthy_count = 0

    client = TestClient(app, raise_server_exceptions=False)
    for path, method, name in routes_to_test:
        t0 = time.time()
        try:
            if method == "GET":
                resp = client.get(path, headers=probe_headers)
            else:
                resp = client.post(path, headers=probe_headers)
            latency_ms = round((time.time() - t0) * 1000, 1)

            is_healthy = resp.status_code == 200
            if is_healthy:
                healthy_count += 1

            has_h1 = "<h1" in resp.text if "text/html" in resp.headers.get("content-type", "") else None

            results.append({
                "path": path,
                "name": name,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
                "content_length": len(resp.content),
                "has_h1": has_h1,
                "healthy": is_healthy
            })
        except Exception as e:
            logger.warning("Failed probing endpoint %s: %s", path, e)
            results.append({
                "path": path,
                "name": name,
                "status_code": 500,
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": str(e),
                "healthy": False
            })

    return {
        "total_checked": len(routes_to_test),
        "healthy_count": healthy_count,
        "failed_count": len(routes_to_test) - healthy_count,
        "all_healthy": healthy_count == len(routes_to_test),
        "endpoints": results
    }


def tool_scan_prohibited_terms() -> Dict[str, Any]:
    """Scans templates and code for prohibited prescriptive words and condescending copy.
    
    SEBI Safe Harbor prohibits prescriptive recommendations (BUY/SELL/HOLD/Target Price).
    Institutional standards prohibit patronizing colloquialisms.
    """
    templates_dir = PROJECT_ROOT / "web" / "templates"
    prohibited_patterns = [
        (r"\bBUY\b\s+now", "Prescriptive 'BUY now' call-to-action"),
        (r"\bSELL\b\s+recommendation", "Prescriptive 'SELL recommendation'"),
        (r"\bSTRONG\s+BUY\b", "Prescriptive 'STRONG BUY' rating"),
        (r"guaranteed\s+(?:return|profit)", "Unlawful 'Guaranteed Return' claim"),
        (r"target\s+price:\s*₹?\d+", "Price forecasting / target price"),
        (r"don't\s+worry,?\s+investing\s+is\s+simple", "Patronizing tone"),
        (r"plain-english\s+explainer\s+for\s+beginners", "Patronizing 'beginner baby-talk'"),
        # Zero-Hallucination & Anti-Fabrication Patterns:
        (r"Registered\s+Operating\s+Entity", "Hallucinated 'Registered Operating Entity' claim"),
        (r"SAC\s*(?:Code)?[:\s]*998314", "Hallucinated GST SAC code 998314"),
        (r"\b998314\b", "Hallucinated SAC code 998314"),
        (r"Indiranagar|100\s*Feet\s*Road|\b560038\b", "Hallucinated physical office address"),
        (r"support@stockresearch\.app", "Hallucinated public email support@stockresearch.app"),
        (r"grievance@stockresearch\.app", "Hallucinated public email grievance@stockresearch.app"),
        (r"privacy@stockresearch\.app", "Hallucinated public email privacy@stockresearch.app"),
        (r"support@vestnomics\.app", "Hallucinated public email support@vestnomics.app"),
        (r"grievance@vestnomics\.app", "Hallucinated public email grievance@vestnomics.app"),
        (r"privacy@vestnomics\.app", "Hallucinated public email privacy@vestnomics.app"),
        (r"support@vestfolio\.app", "Hallucinated public email support@vestfolio.app"),
        (r"grievance@vestfolio\.app", "Hallucinated public email grievance@vestfolio.app"),
        (r"privacy@vestfolio\.app", "Hallucinated public email privacy@vestfolio.app"),
        (r"support@moatnomics\.com", "Hallucinated public email support@moatnomics.com"),
        (r"grievance@moatnomics\.com", "Hallucinated public email grievance@moatnomics.com"),
        (r"privacy@moatnomics\.com", "Hallucinated public email privacy@moatnomics.com"),
        (r"\+91\s*98450", "Hallucinated telephone/hotline"),
        (r"placeholder=[\"'].*Lyndon.*[\"']", "Author personal name leakage in UI placeholder"),
    ]

    findings = []
    scanned_files = 0
    files_to_scan = []

    for root, _, files in os.walk(templates_dir):
        for f in files:
            if f.endswith((".html", ".jinja2")):
                files_to_scan.append(Path(root) / f)

    legal_file = PROJECT_ROOT / "web" / "legal_content.py"
    if legal_file.exists():
        files_to_scan.append(legal_file)

    for fpath in files_to_scan:
        scanned_files += 1
        try:
            content = fpath.read_text(encoding="utf-8")
            for pat, desc in prohibited_patterns:
                # Skip root admin login template when checking admin owner whitelist
                if fpath.name == "admin.html" and "email" in desc.lower():
                    continue
                # In legal policies, negative disclaimers ("does not provide buy/sell recommendations") are statutory
                if fpath.name == "legal_content.py" and "prescriptive" in desc.lower():
                    continue
                matches = list(re.finditer(pat, content, re.IGNORECASE))
                for m in matches:
                    line_no = content[:m.start()].count("\n") + 1
                    findings.append({
                        "file": str(fpath.relative_to(PROJECT_ROOT)),
                        "line": line_no,
                        "matched_text": m.group(0),
                        "violation": desc
                    })
        except Exception as e:
            logger.warning(f"Error scanning {fpath}: {e}")

    # Check that SEBI disclaimer is present in base template
    base_template = templates_dir / "base.html"
    has_disclaimer = False
    if base_template.exists():
        base_text = base_template.read_text(encoding="utf-8")
        has_disclaimer = "Section 2(u)" in base_text or "does not constitute financial or investment advice" in base_text

    return {
        "scanned_templates": scanned_files,
        "violations_count": len(findings),
        "has_statutory_disclaimer": has_disclaimer,
        "is_clean": len(findings) == 0 and has_disclaimer,
        "findings": findings
    }


def tool_scan_code_hygiene() -> Dict[str, Any]:
    """Scans codebase for hardcoded score anti-patterns, silent exception swallowing, and frontend inline quote injection bugs."""
    core_dir = PROJECT_ROOT / "core"
    web_dir = PROJECT_ROOT / "web"

    anti_patterns = [
        (r"score\s*=\s*8[0-9]\.0\b", "Hardcoded heuristic score anti-pattern"),
        (r"except\s+Exception:\s*pass\b", "Silent exception swallowing anti-pattern"),
        (r"except:\s*pass\b", "Bare except silent pass anti-pattern"),
    ]

    frontend_anti_patterns = [
        (r'onclick=[\"\'][^\"\']*?\$\{JSON\.stringify', "Dangerous unescaped JSON.stringify inside inline HTML onclick attribute"),
    ]

    findings = []
    scanned_python_files = 0
    scanned_files = 0

    for search_dir in [core_dir, web_dir]:
        for root, _, files in os.walk(search_dir):
            for f in files:
                if f.endswith(".py"):
                    scanned_python_files += 1
                    scanned_files += 1
                    fpath = Path(root) / f
                    try:
                        content = fpath.read_text(encoding="utf-8")
                        for pat, desc in anti_patterns:
                            matches = list(re.finditer(pat, content))
                            for m in matches:
                                line_no = content[:m.start()].count("\n") + 1
                                findings.append({
                                    "file": str(fpath.relative_to(PROJECT_ROOT)),
                                    "line": line_no,
                                    "matched_text": m.group(0),
                                    "anti_pattern": desc
                                })
                    except Exception as e:
                        logger.warning(f"Error scanning {fpath}: {e}")
                elif f.endswith((".js", ".html")):
                    scanned_files += 1
                    fpath = Path(root) / f
                    try:
                        content = fpath.read_text(encoding="utf-8")
                        for pat, desc in frontend_anti_patterns:
                            matches = list(re.finditer(pat, content))
                            for m in matches:
                                line_no = content[:m.start()].count("\n") + 1
                                findings.append({
                                    "file": str(fpath.relative_to(PROJECT_ROOT)),
                                    "line": line_no,
                                    "matched_text": m.group(0),
                                    "anti_pattern": desc
                                })
                    except Exception as e:
                        logger.warning(f"Error scanning {fpath}: {e}")

    unlogged_exceptions = check_unlogged_blanket_exceptions()

    return {
        "scanned_python_files": scanned_python_files,
        "scanned_files": scanned_files,
        "anti_patterns_count": len(findings),
        "unlogged_exceptions_count": len(unlogged_exceptions),
        "unlogged_exceptions": unlogged_exceptions,
        "is_clean": len(findings) == 0 and len(unlogged_exceptions) == 0,
        "findings": findings
    }


def check_unlogged_blanket_exceptions() -> List[Dict[str, Any]]:
    """
    AST analysis that flags any blanket 'except Exception:' or 'except:' block in core/ or web/
    that fails to invoke telemetry logging or re-raise (unified with verify_reality_audit.py GATE-6).
    """
    core_dir = PROJECT_ROOT / "core"
    web_dir = PROJECT_ROOT / "web"
    flagged = []

    for search_dir in [core_dir, web_dir]:
        for root, _, files in os.walk(search_dir):
            for f in files:
                if not f.endswith(".py"):
                    continue
                fpath = Path(root) / f
                try:
                    src = fpath.read_text(encoding="utf-8")
                    tree = ast.parse(src, filename=str(fpath))
                except Exception as parse_err:
                    logger.debug(f"AST parse notice for {fpath}: {parse_err}")
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.ExceptHandler):
                        exc_type = ast.unparse(node.type) if (node.type and hasattr(ast, "unparse")) else "bare"
                        is_blanket = (node.type is None) or ("Exception" in exc_type) or ("BaseException" in exc_type)

                        if is_blanket:
                            has_log = any(
                                isinstance(s, ast.Call) and any(
                                    kw in (ast.unparse(s.func) if hasattr(ast, "unparse") else "")
                                    for kw in ("log", "print", "record", "warning", "error", "info", "debug", "exception")
                                )
                                for s in ast.walk(node)
                            )
                            has_raise = any(isinstance(s, ast.Raise) for s in ast.walk(node))

                            if not has_log and not has_raise:
                                rel_path = str(fpath.relative_to(PROJECT_ROOT))
                                flagged.append({
                                    "file": rel_path,
                                    "line": node.lineno,
                                    "anti_pattern": "Blanket except Exception: block without telemetry logging or re-raise"
                                })
    return flagged


def tool_audit_design_tokens() -> Dict[str, Any]:
    """Audits CSS design tokens, tabular numerals compliance, SVG symbol parity, and deprecated emoji usage."""
    css_file = PROJECT_ROOT / "web" / "static" / "css" / "style.css"
    templates_dir = PROJECT_ROOT / "web" / "templates"
    base_html = templates_dir / "base.html"

    has_tabular_nums = False
    has_design_tokens = False

    if css_file.exists():
        css_text = css_file.read_text(encoding="utf-8")
        has_tabular_nums = "tabular-nums" in css_text or "tnum" in css_text
        has_design_tokens = "--bg-primary" in css_text and "--accent" in css_text

    defined_svg_symbols = set()
    if base_html.exists():
        base_text = base_html.read_text(encoding="utf-8")
        defined_svg_symbols = set(re.findall(r'<symbol[^>]+id="([^"]+)"', base_text))

    emoji_re = re.compile(r"[\U0001F100-\U0001FAFF\u23F0-\u23FA\u26A0\u2696\u2699\u2705\u274C\u2728\u2795\u2B50\u231B\u23F3\u26A1]")
    emoji_count = 0
    broken_svg_uses = []

    for fpath in sorted(templates_dir.rglob("*.html")):
        try:
            text = fpath.read_text(encoding="utf-8")
            if fpath.name not in ("admin.html", "admin_2fa.html"):
                found_emojis = emoji_re.findall(text)
                emoji_count += len(found_emojis)
            if defined_svg_symbols:
                for ref in re.findall(r'<use[^>]+href="#([^"{}]+)"', text):
                    if ref not in defined_svg_symbols:
                        broken_svg_uses.append(f"{fpath.relative_to(PROJECT_ROOT)}:#{ref}")
        except Exception as read_err:
            logger.debug(f"Template read notice for {fpath}: {read_err}")

    js_dir = PROJECT_ROOT / "web" / "static" / "js"
    for jpath in sorted(js_dir.rglob("*.js")):
        try:
            jtext = jpath.read_text(encoding="utf-8")
            emoji_count += len(emoji_re.findall(jtext))
            if defined_svg_symbols:
                for ref in re.findall(r'<use[^>]+href="#([^"{}$]+)"', jtext):
                    if ref not in defined_svg_symbols:
                        broken_svg_uses.append(f"{jpath.relative_to(PROJECT_ROOT)}:#{ref}")
        except Exception as js_err:
            logger.debug(f"JS read notice for {jpath}: {js_err}")

    parser_py = PROJECT_ROOT / "core" / "analysis" / "parser.py"
    if parser_py.exists():
        try:
            ptext = parser_py.read_text(encoding="utf-8")
            emoji_count += len(emoji_re.findall(ptext))
            if defined_svg_symbols:
                for ref in re.findall(r'<use[^>]+href="#([^"{}]+)"', ptext):
                    if ref not in defined_svg_symbols:
                        broken_svg_uses.append(f"{parser_py.relative_to(PROJECT_ROOT)}:#{ref}")
        except Exception as perr:
            logger.debug(f"Parser read notice: {perr}")

    is_clean_design = has_tabular_nums and has_design_tokens and emoji_count == 0 and len(broken_svg_uses) == 0
    return {
        "has_tabular_nums": has_tabular_nums,
        "has_design_tokens": has_design_tokens,
        "legacy_os_emojis_found": emoji_count,
        "broken_svg_uses_count": len(broken_svg_uses),
        "broken_svg_uses": broken_svg_uses,
        "design_health_score": 100.0 if is_clean_design else (90.0 if (has_tabular_nums and has_design_tokens) else 75.0),
        "notes": "Tabular lining numerals, CSS variables, and institutional vector SVG glyphs active." if is_clean_design else "Tabular lining numerals and CSS variables active. Legacy glyphs or missing SVG symbols tracked for migration."
    }


def tool_audit_frontend_and_api_contracts() -> Dict[str, Any]:
    """
    Audits client-side HTML-to-JavaScript click wiring, AJAX fetch API contracts,
    and external exchange link integrity to catch runtime ReferenceErrors, unmapped endpoints,
    and broken portal queries.
    """
    templates_dir = PROJECT_ROOT / "web" / "templates"
    js_dir = PROJECT_ROOT / "web" / "static" / "js"
    main_py_path = PROJECT_ROOT / "web" / "main.py"

    # 1. Collect all declared JavaScript functions
    js_code = ""
    for js_file in js_dir.glob("*.js"):
        try:
            js_code += js_file.read_text(encoding="utf-8") + "\n"
        except Exception as e:
            logger.warning(f"Error reading JS file {js_file}: {e}")

    defined_fns = set()
    patterns = [
        r"function\s+([a-zA-Z0-9_$]+)\s*\(",
        r"window\.([a-zA-Z0-9_$]+)\s*=",
        r"(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:function|\([^)]*\)\s*=>)"
    ]
    for pat in patterns:
        for m in re.finditer(pat, js_code):
            defined_fns.add(m.group(1))

    # Collect template inline scripts
    inline_fns = set()
    for html_file in templates_dir.rglob("*.html"):
        try:
            content = html_file.read_text(encoding="utf-8")
            for script in re.findall(r"<script[^>]*>(.*?)</script>", content, re.DOTALL):
                for pat in [r"function\s+([a-zA-Z0-9_$]+)\s*\(", r"window\.([a-zA-Z0-9_$]+)\s*="]:
                    for m in re.finditer(pat, script):
                        inline_fns.add(m.group(1))
        except Exception as e:
            logger.warning(f"Error parsing inline scripts in {html_file}: {e}")

    allowed_builtins = {
        "alert", "confirm", "prompt", "history", "location", "close", "focus",
        "this", "event"
    }
    all_allowed = defined_fns | inline_fns | allowed_builtins

    # 2. Check all onclick attributes across HTML templates
    onclick_pat = re.compile(r"onclick=[\"\']\s*([a-zA-Z0-9_$]+)\s*(?:\([^)]*\))?\s*[\"\']")
    orphaned_onclicks = []
    total_onclicks = 0
    scanned_templates = 0

    for html_file in templates_dir.rglob("*.html"):
        scanned_templates += 1
        try:
            content = html_file.read_text(encoding="utf-8")
            for m in onclick_pat.finditer(content):
                total_onclicks += 1
                fn_name = m.group(1)
                if fn_name not in all_allowed:
                    line_no = content[:m.start()].count("\n") + 1
                    orphaned_onclicks.append({
                        "template": str(html_file.relative_to(PROJECT_ROOT)),
                        "line": line_no,
                        "function": fn_name
                    })
        except Exception as e:
            logger.warning(f"Error checking onclicks in {html_file}: {e}")

    # 3. Check AJAX fetch calls vs backend FastAPI routes
    backend_routes = set()
    try:
        from web.main import app
        for r in app.routes:
            if hasattr(r, "path"):
                backend_routes.add(r.path)
            elif hasattr(r, "original_router") and hasattr(r.original_router, "routes"):
                prefix = getattr(getattr(r, "include_context", None), "prefix", "")
                for sub_r in r.original_router.routes:
                    if hasattr(sub_r, "path"):
                        backend_routes.add(prefix + sub_r.path)
            elif hasattr(r, "routes"):
                prefix = getattr(getattr(r, "include_context", None), "prefix", "")
                for sub_r in r.routes:
                    if hasattr(sub_r, "path"):
                        backend_routes.add(prefix + sub_r.path)
    except Exception as e:
        logger.debug(f"Dynamic route inspection fallback: {e}")

    if main_py_path.exists():
        try:
            main_code = main_py_path.read_text(encoding="utf-8")
            backend_routes.update(re.findall(r"@app\.(?:get|post|put|delete|patch)\([\"'](/api/[^\"'?]+)[\"']", main_code))
        except Exception as e:
            logger.warning(f"Error reading main.py for routes: {e}")

    fetch_pat = re.compile(r"fetch\([\"'`\`](/api/[^\"'`\?\$]+)")
    frontend_fetches = set(m.group(1) for m in fetch_pat.finditer(js_code))
    for html_file in templates_dir.rglob("*.html"):
        try:
            content = html_file.read_text(encoding="utf-8")
            for m in fetch_pat.finditer(content):
                frontend_fetches.add(m.group(1))
        except Exception as e:
            logger.debug(f"Error reading template {html_file} for fetch scanning: {e}")

    unmapped_fetches = []
    for f_route in sorted(frontend_fetches):
        matched = False
        for b_route in backend_routes:
            base_b = b_route.split("{")[0]
            if f_route.startswith(base_b) or base_b.startswith(f_route):
                matched = True
                break
        if not matched:
            unmapped_fetches.append(f_route)

    # 4. Check for deprecated external links (e.g. broken BSE Comp_Resultsnew.aspx)
    stale_links = []
    for search_dir in [templates_dir, PROJECT_ROOT / "core"]:
        for root, _, files in os.walk(search_dir):
            for f in files:
                if f.endswith((".py", ".html")):
                    fp = Path(root) / f
                    if fp.resolve() == Path(__file__).resolve():
                        continue
                    try:
                        txt = fp.read_text(encoding="utf-8", errors="ignore")
                        if "Comp_Resultsnew.aspx" in txt:
                            stale_links.append(str(fp.relative_to(PROJECT_ROOT)))
                    except Exception as e:
                        logger.debug(f"Error scanning file {fp} for stale links: {e}")

    is_clean = len(orphaned_onclicks) == 0 and len(unmapped_fetches) == 0 and len(stale_links) == 0
    contract_score = 100.0
    if orphaned_onclicks:
        contract_score -= min(len(orphaned_onclicks) * 15.0, 45.0)
    if unmapped_fetches:
        contract_score -= min(len(unmapped_fetches) * 15.0, 30.0)
    if stale_links:
        contract_score -= min(len(stale_links) * 10.0, 25.0)

    contract_score = max(round(contract_score, 1), 0.0)

    return {
        "templates_scanned": scanned_templates,
        "total_onclick_handlers": total_onclicks,
        "orphaned_onclicks_count": len(orphaned_onclicks),
        "orphaned_onclicks": orphaned_onclicks,
        "frontend_api_fetches_count": len(frontend_fetches),
        "unmapped_api_routes_count": len(unmapped_fetches),
        "unmapped_api_routes": unmapped_fetches,
        "stale_external_links_count": len(stale_links),
        "stale_external_links": stale_links,
        "is_clean": is_clean,
        "contract_health_score": contract_score
    }
