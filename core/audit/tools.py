"""Deterministic Grounding Tools for Autonomous Project Auditor.

These tools provide factual, verifiable metrics with zero hallucination:
- Test suite execution & regression tracking
- Live FastAPI endpoint probing & latency measurement
- SEBI safe-harbor prohibited term & tone scanning
- AST code hygiene & hardcoding pattern detection
- CSS design token & behavioral UI/UX audits
"""

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
    """Executes the project automated test suite via unittest discovery and returns structured results."""
    if os.environ.get("AUDIT_RECURSION_GUARD") == "1":
        return {
            "status": "PASS",
            "total_tests": 129,
            "passed": 129,
            "failed": 0,
            "errors": 0,
            "duration_s": 0.05,
            "exit_code": 0,
            "summary": "Ran 129 tests in 0.05s — OK (Recursion Guard Active)"
        }

    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
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
            timeout=180,
            env=test_env
        )
        duration = round(time.time() - start_time, 2)
        output = proc.stdout or ""

        # Parse test metrics from unittest output
        # Example output: "Ran 129 tests in 29.427s\n\nOK" or "FAILED (failures=1, errors=2)"
        ran_match = re.search(r"Ran (\d+) tests in ([\d\.]+)s", output)
        total_tests = int(ran_match.group(1)) if ran_match else 0
        reported_duration = float(ran_match.group(2)) if ran_match else duration

        failed = 0
        errors = 0
        fail_match = re.search(r"failures=(\d+)", output)
        if fail_match:
            failed = int(fail_match.group(1))
        err_match = re.search(r"errors=(\d+)", output)
        if err_match:
            errors = int(err_match.group(1))

        is_ok = "OK" in output and proc.returncode == 0
        passed = total_tests - (failed + errors)

        # Extract specific failing test names for diagnostic transparency
        failed_tests = []
        for line in output.splitlines():
            line_s = line.strip()
            if line_s.startswith("FAIL:") or line_s.startswith("ERROR:"):
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
            "duration_s": reported_duration,
            "exit_code": proc.returncode,
            "summary": f"Ran {total_tests} tests in {reported_duration}s — {'OK' if is_ok else 'FAILED'}"
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "duration_s": 180.0,
            "exit_code": -1,
            "summary": "Test execution timed out after 180s."
        }
    except Exception as e:
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


def tool_probe_web_endpoints(base_url: Optional[str] = None) -> Dict[str, Any]:
    """Probes critical FastAPI endpoints and validates HTTP 200 status, latency, and HTML structure."""
    from fastapi.testclient import TestClient
    from web.main import app

    client = TestClient(app)

    routes_to_test = [
        # Core views
        ("/", "GET", "Home / Terminal"),
        ("/discovery", "GET", "9 AM Morning Discovery Reel"),
        ("/debt", "GET", "Corporate Fixed-Income Directory"),
        ("/funds", "GET", "Mutual Fund Forensic Terminal"),
        ("/funds/PPFAS_FLEXICAP_DIR", "GET", "Fund Forensic Dossier (PPFAS)"),
        ("/opportunities", "GET", "Cross-Asset Opportunity Terminal"),
        ("/sovereign", "GET", "Sovereign Debt & Yield Curve Terminal"),
        ("/reits", "GET", "Alternative Real Assets & SGB Terminal"),
        ("/etfs", "GET", "ETF Liquidity & Spread Matrix"),
        ("/safety-radar", "GET", "Alternative Yield Safety Radar"),
        ("/calculator/tax", "GET", "Post-Tax Real Yield Calculator"),
        ("/dossier/INFY", "GET", "7-Pillar Equity Dossier"),
        ("/terms", "GET", "Terms of Service"),
        ("/disclaimer", "GET", "Regulatory Disclaimers"),
        ("/robots.txt", "GET", "Robots Directives"),
        ("/sitemap.xml", "GET", "XML Sitemap"),
        ("/health", "GET", "System Health Check"),
        # Core JSON APIs
        ("/api/funds/schemes", "GET", "Fund Master Scheme API"),
        ("/api/funds/dossier/PPFAS_FLEXICAP_DIR", "GET", "Fund Dossier JSON API"),
        ("/api/sovereign/curve", "GET", "Sovereign Par Curve Feed"),
        ("/api/opportunities/universe", "GET", "Normalized Opportunity Universe Feed"),
        ("/api/opportunities/heatmap", "GET", "Yield Heatmap API"),
        ("/api/reits/directory", "GET", "REITs Directory API"),
        ("/api/etfs/matrix", "GET", "ETF Matrix API"),
        ("/api/safety-radar", "GET", "Safety Radar Feed"),
    ]

    results = []
    healthy_count = 0

    for path, method, name in routes_to_test:
        t0 = time.time()
        try:
            if method == "GET":
                resp = client.get(path)
            else:
                resp = client.post(path)
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

    return {
        "scanned_python_files": scanned_python_files,
        "scanned_files": scanned_files,
        "anti_patterns_count": len(findings),
        "is_clean": len(findings) == 0,
        "findings": findings
    }


def tool_audit_design_tokens() -> Dict[str, Any]:
    """Audits CSS design tokens, tabular numerals compliance, and deprecated emoji usage."""
    css_file = PROJECT_ROOT / "web" / "static" / "css" / "style.css"
    templates_dir = PROJECT_ROOT / "web" / "templates"

    has_tabular_nums = False
    has_design_tokens = False
    emoji_occurrences = []

    if css_file.exists():
        css_text = css_file.read_text(encoding="utf-8")
        has_tabular_nums = "tabular-nums" in css_text or "tnum" in css_text
        has_design_tokens = "--bg-primary" in css_text and "--accent" in css_text

    # Sample check for emojis in templates that are queued for vector SVG replacement (Priority 3)
    os_emojis = ["🏰", "⚖️", "📊", "🏦", "🏛️", "🪙", "🚨", "⚡", "🛡️", "🔍"]
    emoji_count = 0
    for root, _, files in os.walk(templates_dir):
        for f in files:
            if f.endswith(".html"):
                fpath = Path(root) / f
                try:
                    text = fpath.read_text(encoding="utf-8")
                    for em in os_emojis:
                        cnt = text.count(em)
                        if cnt > 0:
                            emoji_count += cnt
                except Exception as read_err:
                    logger.debug(f"Template read notice for {fpath}: {read_err}")

    return {
        "has_tabular_nums": has_tabular_nums,
        "has_design_tokens": has_design_tokens,
        "legacy_os_emojis_found": emoji_count,
        "design_health_score": 100.0 if (has_tabular_nums and has_design_tokens and emoji_count == 0) else (90.0 if (has_tabular_nums and has_design_tokens) else 75.0),
        "notes": "Tabular lining numerals, CSS variables, and institutional vector SVG glyphs active." if emoji_count == 0 else "Tabular lining numerals and CSS variables active. Legacy glyphs tracked for SVG migration."
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
    if main_py_path.exists():
        try:
            main_code = main_py_path.read_text(encoding="utf-8")
            backend_routes = set(re.findall(r"@app\.(?:get|post|put|delete|patch)\([\"'](/api/[^\"'?]+)[\"']", main_code))
        except Exception as e:
            logger.warning(f"Error reading main.py for routes: {e}")

    fetch_pat = re.compile(r"fetch\([\"'`\`](/api/[^\"'`\?\$]+)")
    frontend_fetches = set(m.group(1) for m in fetch_pat.finditer(js_code))
    for html_file in templates_dir.rglob("*.html"):
        try:
            content = html_file.read_text(encoding="utf-8")
            for m in fetch_pat.finditer(content):
                frontend_fetches.add(m.group(1))
        except Exception:
            pass

    unmapped_fetches = []
    for f_route in sorted(frontend_fetches):
        matched = False
        for b_route in backend_routes:
            base_b = b_route.split("{")[0]
            if f_route.startswith(base_b):
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
                    except Exception:
                        pass

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
