import os
import sys
import time
import logging
from datetime import datetime
from db import IST

os.environ["TESTING"] = "1"

# Suppress debug log noise
logging.getLogger("uvicorn").setLevel(logging.WARNING)

def run_suite():
    issues = []
    print("\n=======================================================")
    print(f"   SYSTEM INTEGRITY & CONTRACT AUDIT - {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=======================================================")

    # 1. Environment & Exact Version Integrity
    print("1. Auditing Installed Packages & Version Integrity...")
    modules = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("jinja2", "jinja2"),
        ("bsedata", "bsedata"),
        ("google.genai", "google-genai"),
        ("markdown_pdf", "markdown-pdf"),
        ("psycopg2", "psycopg2-binary"),
        ("requests", "requests"),
        ("yfinance", "yfinance"),
        ("pandas", "pandas"),
        ("matplotlib", "matplotlib"),
        ("analyzer", "analyzer.py"),
        ("bse_master", "bse_master.py"),
        ("checker", "checker.py"),
        ("db", "db.py"),
        ("screener", "screener.py"),
        ("normalizer", "normalizer.py"),
        ("alerts", "alerts.py"),
        ("telemetry", "telemetry.py"),
        ("core.formatters", "core/formatters.py"),
        ("core.reporting.pdf", "core/reporting/pdf.py"),
        ("core.auth", "core/auth"),
        ("core.billing", "core/billing"),
        ("core.db.connection", "core/db/connection.py"),
        ("web.main", "web/main.py"),
    ]
    
    for mod_name, pkg_name in modules:
        try:
            mod = __import__(mod_name)
            ver = getattr(mod, "__version__", "local")
            print(f"   ✅ {mod_name} verified ({ver}).")
        except Exception as e:
            issues.append((
                "Syntax/Dependency",
                f"Import failed for '{mod_name}': {e}",
                f"Run `pip install {pkg_name}` or verify syntax."
            ))
            print(f"   ❌ {mod_name} FAILED: {e}")

    # 2. Third-Party Data Contract: yfinance Schema Probe
    print("\n2. Probing yfinance Contract & Multiples Schema...")
    try:
        import yfinance as yf
        ticker = yf.Ticker("INFY.BO")
        info = ticker.info or {}
        pe = info.get("trailingPE")
        mcap = info.get("marketCap")

        if pe is not None and mcap is not None and mcap > 0:
            print(f"   ✅ yfinance contract operational: INFY Trailing P/E={pe}, MCap={mcap:,}")
        else:
            issues.append((
                "Data Contract",
                f"yfinance returned incomplete schema for INFY (PE: {pe}, MCap: {mcap})",
                "Check Yahoo Finance API changes or IP rate-limits."
            ))
            print(f"   ⚠️ yfinance schema gap: PE={pe}, MCap={mcap}")
    except Exception as e:
        issues.append((
            "Data Contract",
            f"yfinance probe failed with exception: {e}",
            "Inspect network access to Yahoo Finance endpoints."
        ))
        print(f"   ❌ yfinance probe FAILED: {e}")

    # 3. Credentials & Secrets Configuration
    print("\n3. Auditing API Credentials & Secrets...")
    from core.config import get_secret
    gemini_key = get_secret("GEMINI_API_KEY")

    if not gemini_key:
        issues.append((
            "Credentials",
            "GEMINI_API_KEY missing",
            "Add GEMINI_API_KEY to .env or export as an environment variable."
        ))
        print("   ❌ GEMINI_API_KEY not found.")
    else:
        print("   ✅ GEMINI_API_KEY verified.")

    # 4. BSE Scrip Resolution Logic & Announcement Delta Engine
    print("\n4. Testing BSE Scrip Resolution & Announcement Ingestion...")
    try:
        from bse_master import resolve_bse_scrip_code
        scrip = resolve_bse_scrip_code("INFY")
        if str(scrip).strip() == "500209":
            print(f"   ✅ INFY resolved correctly to BSE Scrip {scrip}.")
        else:
            issues.append((
                "Resolution",
                f"INFY resolved to unexpected scrip '{scrip}' (expected 500209)",
                "Inspect scrip mapping logic in bse_master.py."
            ))
            print(f"   ❌ INFY resolved to '{scrip}'.")
    except Exception as e:
        issues.append((
            "Resolution Engine",
            f"resolve_bse_scrip_code raised an exception: {e}",
            "Verify bse_master.py implementation."
        ))
        print(f"   ❌ BSE Resolution FAILED: {e}")

    try:
        from analyzer import fetch_latest_bse_announcement
        ann = fetch_latest_bse_announcement("500209")
        print(f"   ✅ BSE Announcement Feed operational (INFY: '{ann[:45]}...' if ann else 'clean').")
    except Exception as e:
        issues.append((
            "Surveillance Engine",
            f"fetch_latest_bse_announcement raised an exception: {e}",
            "Verify analyzer.py announcement fetching and timedelta import."
        ))
        print(f"   ❌ BSE Announcement Fetch FAILED: {e}")

    # 5. Database Connection & Query Latency Probe
    print("\n5. Probing Database Connection & Latency...")
    try:
        from db import get_db_connection
        t0 = time.perf_counter()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.fetchone()
        latency_ms = (time.perf_counter() - t0) * 1000
        cur.close()
        conn.close()
        print(f"   ✅ Database responsive ({latency_ms:.2f}ms roundtrip).")
    except Exception as e:
        issues.append((
            "Database",
            f"Database handshake failed: {e}",
            "Check database availability and connection string."
        ))
        print(f"   ❌ Database probe FAILED: {e}")

    # 5b. Auditing Monetization & User Accounts Schema (v007)
    print("\n5b. Auditing Monetization & User Accounts Schema (v007)...")
    try:
        from core.billing import PRICING_PACKS, B2B_PACKS
        assert len(PRICING_PACKS) >= 5, "Missing core pricing tiers."
        assert PRICING_PACKS["single_pass"]["amount_inr"] == 299, "Single pass must be ₹299."
        assert PRICING_PACKS["analyst_3pack"]["amount_inr"] == 699, "Analyst 3-pack must be ₹699."
        assert PRICING_PACKS["portfolio_10pack"]["amount_inr"] == 1799, "Portfolio 10-pack must be ₹1,799."
        assert PRICING_PACKS["pro_monthly"]["amount_inr"] == 999, "Pro Monthly must be ₹999."
        assert PRICING_PACKS["pro_annual"]["amount_inr"] == 8999, "Pro Annual must be ₹8,999."

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT version FROM schema_migrations WHERE version = 'v007_user_accounts_and_credits';")
        mig_row = cur.fetchone()
        cur.close()
        conn.close()
        assert mig_row is not None, "Migration v007_user_accounts_and_credits not found in schema_migrations."
        print("   ✅ Monetization tiers & schema migration v007 verified.")
    except Exception as e:
        issues.append((
            "Monetization/Auth",
            f"Monetization schema audit failed: {e}",
            "Verify v007 migration and pricing configuration."
        ))
        print(f"   ❌ Monetization audit FAILED: {e}")

    # 6. FastAPI SSR Production Application Mount & Route Smoke Test
    print("\n6. Executing FastAPI SSR Application Smoke Test (TestClient)...")
    try:
        from fastapi.testclient import TestClient
        from web.main import app
        with TestClient(app) as client:
            test_routes = ["/", "/discovery", "/pricing", "/search", "/api/suggest?q=inf"]
            failed_routes = []
            for route in test_routes:
                res = client.get(route)
                if res.status_code != 200:
                    failed_routes.append(f"{route} (Status {res.status_code})")
            
            if failed_routes:
                issues.append((
                    "FastAPI SSR Routes",
                    f"Route checks failed for: {', '.join(failed_routes)}",
                    "Verify templates and route handlers in web/main.py."
                ))
                print(f"   ❌ Route checks failed: {failed_routes}")
            else:
                print(f"   ✅ FastAPI application mounted cleanly with {len(test_routes)} core routes returning HTTP 200 OK.")
    except Exception as e:
        issues.append((
            "FastAPI SSR Mount",
            f"TestClient encountered an exception: {e}",
            "Verify FastAPI installation and web/main.py initialization."
        ))
        print(f"   ❌ FastAPI smoke test failed: {e}")

    # 7. Living Documentation Integrity & Synchronization Audit
    print("\n7. Auditing Living Documentation Integrity & Synchronization...")
    doc_paths = [
        "docs/MASTER_ENGINEERING_MANUAL.md",
        "docs/REPORT_EVALUATION_FRAMEWORKS.md",
        ".antigravity/docs/EVALUATION_FRAMEWORKS.md",
        ".antigravity/docs/ARCHITECTURE.md",
        "AGENTS.md",
    ]
    for dp in doc_paths:
        if not os.path.exists(dp) or os.path.getsize(dp) < 100:
            issues.append((
                "Documentation Sync",
                f"Required documentation file '{dp}' is missing or empty.",
                f"Restore and update '{dp}' per Directive 3 in AGENTS.md."
            ))
            print(f"   ❌ Missing/empty documentation: {dp}")
        else:
            print(f"   ✅ Documentation verified: {dp}")

    try:
        with open(".antigravity/docs/ARCHITECTURE.md", "r", encoding="utf-8") as f:
            arch_content = f.read()
        if "app.py" in arch_content or "ui/views" in arch_content:
            issues.append((
                "Documentation Sync",
                "Legacy Streamlit components (app.py/ui/views) detected in .antigravity/docs/ARCHITECTURE.md.",
                "Synchronize .antigravity/docs/ARCHITECTURE.md with production FastAPI SSR architecture."
            ))
            print("   ❌ Legacy Streamlit references found in .antigravity/docs/ARCHITECTURE.md")
        else:
            print("   ✅ Architecture document verified free of legacy Streamlit components.")
    except Exception as e:
        pass

    # 8. Project Health Ledger Update (PROJECT_STATUS.md)
    timestamp_str = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')
    status_summary = "ALL SYSTEMS OPERATIONAL" if not issues else f"{len(issues)} ISSUE(S) DETECTED"
    
    ledger_content = f"""# Project Health Ledger
**Last Updated:** {timestamp_str}  
**Status:** {status_summary}

---

## Diagnostic Audit Summary
"""
    if not issues:
        ledger_content += "\n🎉 **All systems operational.** Zero blocking issues detected.\n"
    else:
        ledger_content += f"\n⚠️ **{len(issues)} critical issue(s) require action:**\n\n"
        for idx, (cat, desc, fix) in enumerate(issues, 1):
            ledger_content += f"### {idx}. [{cat}] {desc}\n"
            ledger_content += f"- **Immediate Action Required:** `{fix}`\n\n"

    try:
        with open("PROJECT_STATUS.md", "w", encoding="utf-8") as f:
            f.write(ledger_content)
        print("\n✅ Updated PROJECT_STATUS.md successfully.")
    except Exception as e:
        print(f"\n❌ Failed to write PROJECT_STATUS.md: {e}")

    # Executive Output
    print("\n=======================================================")
    print("   EXECUTIVE AUDIT SUMMARY")
    print("=======================================================")
    if not issues:
        print("🎉 ALL SYSTEMS OPERATIONAL. Zero blocking issues detected.\n")
    else:
        print(f"⚠️  {len(issues)} CRITICAL ISSUE(S) DETECTED:\n")
        for idx, (cat, desc, fix) in enumerate(issues, 1):
            print(f"[{idx}] {cat}: {desc}")
            print(f"    👉 Action: {fix}\n")

if __name__ == "__main__":
    run_suite()
