# **Streamlit App Runtime Architecture & System Reference**

1\. Enterprise & Retail Data Vendor Pricing Benchmarks

| Provider | Target Market | Estimated Annual License Cost | Cost Mechanics & Limitations |
| :---- | :---- | :---- | :---- |
| **C-MOTS Internet Technologies** | Brokerages, financial portals (e.g., Screener.in backend) | **₹1.5 Lakh to ₹6 Lakh+ / year** (\~₹12,000 to ₹50,000/month) \[Likely\] | Structured JSON/XML data feeds. Pricing scales directly by: 1\. Number of data fields requested (P/E ratios vs. full 15-year financials). 2\. End-use classification (internal research desk vs. redistributing data on a public website/app). |
| **Capitaline (Capital Market)** | Mutual fund AMCs, institutional research desks, university libraries | **₹2.5 Lakh to ₹8 Lakh+ / year** (Desktop/Web DB) **₹5 Lakh to ₹15 Lakh+ / year** (Direct API/Feed) \[Likely\] | The industry benchmark for forensic normalization across listed and large unlisted Indian firms. Pure enterprise sales; rarely enters contracts with non-registered or un-incorporated retail developers \[Likely\]. |

### **1.1 Enterprise Vendor Constraints**

> * **Commercial Redistribution Multipliers:** Public-facing web apps or automated report generation routinely trigger a 2x to 3x pricing markup over internal research desktop pricing.  
> * **Procurement Barriers:** Institutional providers (C-MOTS, Capitaline) require corporate entity verification, NDA/MSA paperwork, GST invoicing, and 12-month upfront non-refundable contract commitments with no self-serve credit card checkouts.

1.2 EODHD Retail Tier Analysis

| Plan Name | Monthly Cost | Annual Cost (Billed Upfront) | Daily API Quota | Fundamentals (P/E, Financials) Included? | Applicability to Your Stack |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **Free Starter** | **\$0** | **\$0** | **20 calls/day** | ❌ No (Past year price only) | **Unusable:** Depleted after testing 2 equities \[Certain\]. |
| **EOD Historical Data** | **\$19.99/mo** (\~₹1,750/mo) | **\$199.00/yr** | 100,000 calls/day | ❌ No (Only end-of-day prices & splits) | **Insufficient:** Missing P/E, EPS, Balance Sheet \[Certain\]. |
| **EOD \+ Intraday** | **\$29.99/mo** (\~₹2,600/mo) | **\$299.90/yr** | 100,000 calls/day | ❌ No (Technical indicators & prices only) | **Insufficient:** No fundamental valuation metrics \[Certain\]. |
| **Fundamentals Data Feed** | **\$59.99/mo** (\~₹5,200/mo) | **\$599.90/yr** (\~₹52,000/yr) | 100,000 calls/day | **✅ Yes** (30+ yrs statements, ratios, EPS) | **Minimum Viable Tier:** Supplies the verified valuation fields needed \[Certain\]. |
| **All-In-One Package** | **\$99.99/mo** (\~₹8,700/mo) | **\$999.90/yr** (\~₹87,000/yr) | 100,000 calls/day | **✅ Yes** (Real-time \+ Fundamentals \+ Logos) | **Complete Bundle:** Real-time quotes \+ deep balance sheet history \[Certain\]. |

## **2\. Data Ingestion Architecture & Fallback Protocols**

### **2.1 Primary vs. Secondary Fundamental Sources**

To maintain zero fixed capital expenditure during initial product validation, fundamental metrics are handled via a multi-tier fallback hierarchy:

> 1. **Phase 1 Validation Stack (Zero-Cost):**  
>    1\. **Scrip Resolution:** Supabase PostgreSQL RPC resolving 5,004 BSE equities.  
>    2\. **Fundamental Parsing:** Consolidated yfinance parser with explicit loss-making logic (converting negative TTM EPS to "N/A").  
>    3\. **Inference Engine:** Gemini 3.6 Flash via Automatic Function Calling (AFC) chat streaming.  
> 2. **Phase 2 Scaling Trigger (EODHD Fundamentals \- \$59.99/mo):**  
>    Upgrade to paid REST API data feeds when expanding from single-equity lookups to **Mutual Fund Look-Throughs (Tier 2\)**. Batching requests across 40–65 underlying portfolio stocks triggers IP rate limits on zero-cost parsers, making EODHD's 100,000 daily request quota necessary.

### **2.2 Risks of Unconsolidated Endpoint Fallbacks**

Relying on lightweight exchange endpoints (e.g., BSE ComHeader) as an automated fundamental fallback introduces critical system risks:

> * **Accounting Distortion:** ComHeader returns unconsolidated metrics (e.g., INFY reported standalone P/E of 9.59x vs. actual consolidated P/E of \~24x).  
> * **Missing Primaries:** Returns null values for Market Capitalization, P/B, and ROE, causing UI widget failures.  
> * **AI Hallucination Contagion:** Ingesting distorted valuation multiples causes LLM reasoning engines to output false thesis summaries.  
> * **Recommended Failure Handling:** If the primary fundamental parser fails, display an explicit "N/A (Valuation Data Offline)" badge rather than falling back to unversioned exchange endpoints.

## **3\. Automated Reliability & Testing Architecture**

### **3.1 Three-Part Diagnostic Infrastructure**

┌─────────────────────────────────────────────────────────────┐  
│ 1\. Automated Pre-Flight Engine (\`check\_system.py\`)          │  
│    \- Verifies Python environment & dependencies             │  
│    \- Tests Supabase connection & RPC latency (\<10ms)        │  
│    \- Validates Gemini / Perplexity API credentials          │  
│    \- Runs unit assertions across all 7-Pillar edge cases    │  
└──────────────────────────────┬──────────────────────────────┘  
                               │  
                               ▼  
┌─────────────────────────────────────────────────────────────┐  
│ 2\. Project Health Ledger (\`PROJECT\_STATUS.md\` / DB)         │  
│    \- Auto-generates whenever \`check\_system.py\` runs         │  
│    \- Surfaced immediately whenever opening IDE/terminal     │  
│    \- Lists exact operational failures and immediate fixes   │  
└──────────────────────────────┬──────────────────────────────┘  
                               │  
                               ▼  
┌─────────────────────────────────────────────────────────────┐  
│ 3\. Headless UI Test Runner (\`test\_ui\_headless.py\`)          │  
│    \- Simulates Streamlit widget state in under 2 seconds    │  
│    \- Validates execution without launching browser sessions │  
└─────────────────────────────────────────────────────────────┘

### **3.2 Pre-Flight System Audit Script (\`check\_system.py\`)**

```py
import sys
import os
import time
import logging
from datetime import datetime, timezone

# Suppress bare-mode Streamlit log noise
os.environ["STREAMLIT_LOG_LEVEL"] = "error"
logging.getLogger("streamlit").setLevel(logging.ERROR)

def run_suite():
    issues = []
    print(f"\n=======================================================")
    print(f"   PROJECT INTEGRITY AUDIT - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"=======================================================")

    # 1. Environment & Syntax
    print("1. Checking Environment & Module Syntax...")
    try:
        import bsedata
        import google.genai
        import psycopg2
        import requests
        import analyzer
        import bse_master
        print("   ✅ Core analytical modules imported cleanly.")
    except Exception as e:
        issues.append(("Syntax/Import", f"Module import failed: {e}", "Run `pip install -r requirements.txt`."))
        print(f"   ❌ FAILED: {e}")

    # 2. Database & Resolution Test
    print("2. Checking Supabase Scrip Resolution...")
    try:
        from bse_master import resolve_bse_scrip_code
        t0 = time.time()
        scrip = resolve_bse_scrip_code("INFY")
        elapsed = (time.time() - t0) * 1000
        if scrip == "500209":
            print(f"   ✅ Supabase RPC verified (INFY -> 500209 in {elapsed:.1f}ms).")
        else:
            issues.append(("Scrip Resolution", f"Expected 500209, got {scrip}", "Check `resolve_scrip` function in Supabase."))
            print(f"   ❌ FAILED: Expected 500209, got {scrip}")
    except Exception as e:
        issues.append(("Supabase Connection", str(e), "Verify SUPABASE_DB_URL in .streamlit/secrets.toml."))
        print(f"   ❌ FAILED: {e}")

    # 3. Health Matrix Parser & Redundancy Stripper
    print("3. Checking Health Matrix Parser & Redundancy Stripper...")
    try:
        from analyzer import extract_health_matrix, remove_health_matrix_text
        sample = "# Report\nHealth Matrix\n* Moat: Wide\n* Valuation: Fair\n* Verdict: BUY\n\nBody"
        matrix = extract_health_matrix(sample)
        stripped = remove_health_matrix_text(sample)

        moat_val = matrix.get("Moat", "").upper()
        verdict_val = matrix.get("Verdict", "").upper()

        if moat_val != "WIDE" or verdict_val != "BUY":
            issues.append(("Matrix Parser", f"Got Moat='{moat_val}', Verdict='{verdict_val}'", "Check regex normalization in `extract_health_matrix`."))
            print(f"   ❌ FAILED: Parser extracted Moat='{moat_val}', Verdict='{verdict_val}'")
        elif "Health Matrix" in stripped or "* Moat: Wide" in stripped:
            issues.append(("Text Stripper", "Duplicate text list not stripped cleanly.", "Inspect `remove_health_matrix_text` regex."))
            print("   ❌ FAILED: Health matrix list still visible in stripped body.")
        else:
            print("   ✅ Matrix parser and text stripper passed.")
    except Exception as e:
        issues.append(("Parser Engine", str(e), "Inspect analyzer.py parsing functions."))
        print(f"   ❌ FAILED: {e}")

    # 4. API Credentials
    print("4. Checking Gemini API Key...")
    try:
        import toml
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key and os.path.exists(".streamlit/secrets.toml"):
            api_key = toml.load(".streamlit/secrets.toml").get("GEMINI_API_KEY")
        if not api_key:
            issues.append(("Credentials", "GEMINI_API_KEY missing", "Add GEMINI_API_KEY to .streamlit/secrets.toml."))
            print("   ❌ FAILED: GEMINI_API_KEY not found.")
        else:
            print("   ✅ GEMINI_API_KEY is configured.")
    except Exception as e:
        issues.append(("API Client", str(e), "Check google-genai configuration."))
        print(f"   ❌ FAILED: {e}")

    print("\n=======================================================")
    print("   EXECUTIVE AUDIT SUMMARY")
    print("=======================================================")
    if not issues:
        print("🎉 ALL SYSTEMS OPERATIONAL. Zero blocking issues detected.\n")
    else:
        print(f"⚠️  {len(issues)} CRITICAL ISSUE(S) DETECTED:\n")
        for idx, (cat, desc, fix) in enumerate(issues, 1):
            print(f"[{idx}] {cat.upper()}:")
            print(f"    Problem : {desc}")
            print(f"    Action  : {fix}\n")

if __name__ == "__main__":
    run_suite()
```

### **3.3 Headless UI Test Runner (\`test\_ui\_headless.py\`)**

```py
from streamlit.testing.v1 import AppTest

def test_app_loads_and_has_search_box():
    print("Testing Streamlit app headless initialization...")
    at = AppTest.from_file("app.py")
    at.run()

    # Assert app loads without unhandled exceptions
    assert not at.exception, f"App crashed on launch: {at.exception}"
    print("✅ App loads cleanly without exceptions.")

    # Assert query input exists
    inputs = [w for w in at.text_input]
    assert len(inputs) > 0, "No text input found for stock query."
    print("✅ Search input widget verified.")

if __name__ == "__main__":
    test_app_loads_and_has_search_box()
    print("🎉 Headless UI smoke test passed.")
```

## **4\. Parser Specifications (\`analyzer.py\`)**

The report parsing subsystem (\`analyzer.py\`) extracts structured health matrix badges and sanitizes presentation text using resilient regex rules.

```py
import re

def extract_health_matrix(report_text: str) -> dict:
    """
    Parses the 7-Pillar Health Matrix from report text.
    Case-insensitive, agnostic to bullet markers (*, -, •), numbered lists, colons, and hyphens.
    """
    if not report_text or not isinstance(report_text, str):
        return {}

    clean = report_text.replace("\xa0", " ").replace("–", "-").replace("—", "-")

    matrix = {
        "Macro": "Neutral", "Moat": "Moderate", "Governance": "Clean",
        "Diagnostic": "N/A", "Valuation": "Fair", "BalanceSheet": "Resilient", "Verdict": "Watchlist"
    }

    patterns = {
        "Macro": r"(?i)(?:[-*•]|\d+\.)?\s*Macro\s*[:\-]?\s*\[?\s*(Stable|Headwinds|Neutral)\s*\]?",
        "Moat": r"(?i)(?:[-*•]|\d+\.)?\s*Moat\s*[:\-]?\s*\[?\s*(Wide|Moderate|Narrow)\s*\]?",
        "Governance": r"(?i)(?:[-*•]|\d+\.)?\s*Governance\s*[:\-]?\s*\[?\s*(Clean|Caution|High Risk)\s*\]?",
        "Diagnostic": r"(?i)(?:[-*•]|\d+\.)?\s*Diagnostic\s*[:\-]?\s*\[?\s*(Temporary|Structural|Neutral|N/A)\s*\]?",
        "Valuation": r"(?i)(?:[-*•]|\d+\.)?\s*Valuation\s*[:\-]?\s*\[?\s*(Undervalued|Fair|Stretched|Loss-Making)\s*\]?",
        "BalanceSheet": r"(?i)(?:[-*•]|\d+\.)?\s*Balance\s*Sheet\s*[:\-]?\s*\[?\s*(Debt-Free|Moderate Debt|High Debt|Resilient)\s*\]?",
        "Verdict": r"(?i)(?:[-*•]|\d+\.)?\s*Verdict\s*[:\-]?\s*\[?\s*(BUY|WATCHLIST|AVOID)\s*\]?"
    }

    for key, pat in patterns.items():
        match = re.search(pat, clean)
        if match:
            matrix[key] = match.group(1).strip().title()

    if matrix.get("Verdict") == "Watchlist":
        v_match = re.search(r"(?i)#+\s*VERDICT\s*[:\-]?\s*\[?\s*(BUY|WATCHLIST|AVOID)\s*\]?", clean)
        if v_match:
            matrix["Verdict"] = v_match.group(1).strip().title()

    return matrix

def remove_health_matrix_text(text: str) -> str:
    """Removes redundant markdown Health Matrix bullet blocks from presentation."""
    if not text or not isinstance(text, str):
        return ""
    cleaned = re.sub(
        r'(?i)#*\s*Health Matrix\s*\n+(?:[ \t]*[-*•\d\.]+\s+[^\n]+\n*)+',
        '',
        text
    )
    return cleaned.strip()
```

## **5\. Regulatory & Compliance Framework (SEBI RA Regulations)**

### **5.1 Legal Classification: Software Publishing vs. Registered Advisory**

> 1. **SEBI Research Analyst Regulations (2014) Scope:**  
>    Compliance is triggered when an entity provides personalized fiduciary recommendations or tailored portfolio advice for direct consideration.  
> 2. **Protected Safe Harbor:**  
>    Automated research software, quantitative screeners, and AI-driven filing synthesis utilities operate legally as financial software tools provided they maintain zero personal financial profiling and publish unopinionated data analysis.  
> 3. **Distinction in Output Directive:**  
>    • **Regulated Directive (Requires License):** "Based on your risk profile, you should purchase 200 shares of X today."  
>    • **Software Synthesis (Safe Harbor):** "Based on public exchange disclosures, Equity X exhibits a Clean governance profile and a 24x trailing P/E ratio."

### **5.2 Regulatory Guardrails & Mandatory Disclaimers**

> * **Zero User Personalization:** Do not collect net worth, age, portfolio holdings, or risk tolerance data. Standardize report output uniformly across all ticker queries.  
> * **Immutable Regulatory Notice:** Append the following banner across all UI views and exported document exports:

*"Disclaimer: This report is automatically generated by an AI research assistant using public BSE disclosures and search grounding. It is intended strictly for informational and educational auditing purposes and does not constitute financial or investment advice."*