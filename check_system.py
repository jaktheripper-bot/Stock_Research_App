import os
import sys
import time
import logging
from datetime import datetime, timezone

# Suppress bare-mode Streamlit log noise
os.environ["STREAMLIT_LOG_LEVEL"] = "error"
logging.getLogger("streamlit").setLevel(logging.ERROR)

def run_suite():
    issues = []
    print("\n=======================================================")
    print(f"   SYSTEM INTEGRITY & CONTRACT AUDIT - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=======================================================")

    # 1. Environment & Exact Version Integrity
    print("1. Auditing Installed Packages & Version Integrity...")
    modules = [
        ("streamlit", "streamlit"),
        ("bsedata", "bsedata"),
        ("google.genai", "google-genai"),
        ("markdown_pdf", "markdown-pdf"),
        ("psycopg2", "psycopg2-binary"),
        ("requests", "requests"),
        ("toml", "toml"),
        ("yfinance", "yfinance"),
        ("analyzer", "analyzer.py"),
        ("bse_master", "bse_master.py"),
        ("checker", "checker.py"),
        ("db", "db.py"),
        ("screener", "screener.py")
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
    gemini_key = os.environ.get("GEMINI_API_KEY")
    secrets_path = ".streamlit/secrets.toml"
    if os.path.exists(secrets_path):
        try:
            import toml
            secrets_dict = toml.load(secrets_path)
            if not gemini_key:
                gemini_key = secrets_dict.get("GEMINI_API_KEY")
        except Exception as e:
            issues.append(("Configuration", f"Failed to parse {secrets_path}: {e}", "Fix syntax in .streamlit/secrets.toml."))

    if not gemini_key:
        issues.append((
            "Credentials",
            "GEMINI_API_KEY missing",
            "Add GEMINI_API_KEY to .streamlit/secrets.toml or export as an environment variable."
        ))
        print("   ❌ GEMINI_API_KEY not found.")
    else:
        print("   ✅ GEMINI_API_KEY is configured.")

    # 4. BSE Scrip Resolution Logic
    print("\n4. Testing BSE Scrip Resolution Engine...")
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

    # 6. Streamlit 1.63 Headless UI Mount Audit
    print("\n6. Executing Headless UI Smoke Test (AppTest)...")
    try:
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("app.py", default_timeout=15)
        at.run()
        if at.exception:
            issues.append((
                "Headless UI",
                f"Streamlit app crashed on launch: {at.exception}",
                "Inspect traceback in app.py to resolve startup exception."
            ))
            print(f"   ❌ App crashed on startup: {at.exception}")
        else:
            text_inputs = list(at.text_input)
            if not text_inputs:
                issues.append((
                    "Headless UI",
                    "No text_input widget found in app.py",
                    "Verify search form widgets in app.py."
                ))
                print("   ❌ Search input widget missing.")
            else:
                print(f"   ✅ App mounted cleanly with {len(text_inputs)} input field(s) verified.")
    except Exception as e:
        issues.append((
            "Headless UI",
            f"Headless runner encountered an exception: {e}",
            "Verify streamlit testing setup and dependencies."
        ))
        print(f"   ❌ Headless UI test failed: {e}")

    # 7. Project Health Ledger Update (PROJECT_STATUS.md)
    timestamp_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
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
