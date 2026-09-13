


class PipelineError(Exception):
    def __init__(self, stage: str, message: str, technical_details: str = ""):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.technical_details = technical_details

class TickerResolutionError(PipelineError):
    def __init__(self, query: str):
        super().__init__(
            stage="Ticker & Scrip Resolution",
            message=f"Could not resolve an official BSE scrip code for '{query}'.",
            technical_details=f"Query '{query}' was evaluated against direct code, static aliases, local master universe, and JIT AI discovery. Zero active quotes confirmed."
        )

class ExchangeDataFetchError(PipelineError):
    def __init__(self, scrip: str, detail: str):
        super().__init__(
            stage="Exchange Data Ingestion",
            message=f"BSE exchange rejected or failed to return quote data for scrip {scrip}.",
            technical_details=detail
        )


import requests
from datetime import datetime, timezone

def fetch_latest_bse_announcement(scrip_code: str) -> str:
    """Fetches the latest official corporate filing headline from BSE India."""
    if not scrip_code or not str(scrip_code).isdigit():
        return ""
    try:
        url = f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate=&strScrip={scrip_code}&strSearch=P&strToDate=&strType=C"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bseindia.com/",
            "Accept": "application/json, text/plain, */*"
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            table = data.get("Table", [])
            if table and len(table) > 0:
                headline = table[0].get("NEWSSUB", "") or table[0].get("HEADLINE", "")
                return headline.strip()
    except Exception:
        pass
    return ""

def evaluate_material_change(cached: dict, live_fund: dict, scrip_code: str) -> tuple:
    """
    Evaluates whether material changes require report regeneration.
    Returns (should_regenerate: bool, reason: str, latest_announcement: str).
    """
    if not cached:
        return True, "Initial analysis", ""

    # 1. Check age (> 14 days)
    raw_ts = cached.get("raw_timestamp")
    if raw_ts:
        try:
            ts = raw_ts if isinstance(raw_ts, datetime) else datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            days_old = (now - ts).total_seconds() / 86400.0
            if days_old > 14:
                return True, f"Report is {int(days_old)} days old (> 14-day cycle)", ""
        except Exception:
            pass

    # 2. Check Corporate Filings on BSE
    latest_ann = fetch_latest_bse_announcement(scrip_code)
    cached_ann = cached.get("latest_announcement", "")
    if latest_ann and cached_ann and latest_ann != cached_ann:
        return True, f"New BSE Corporate Announcement: '{latest_ann[:50]}...'", latest_ann

    # 3. Check Price Volatility (>= 5% move)
    cached_price = cached.get("baseline_price")
    live_price = live_fund.get("current_price") or live_fund.get("currentValue")
    try:
        c_p = float(str(cached_price).replace(",", "").strip())
        l_p = float(str(live_price).replace(",", "").strip())
        if c_p > 0:
            pct_change = abs(l_p - c_p) / c_p
            if pct_change >= 0.05:
                direction = "+" if l_p > c_p else "-"
                return True, f"Price shifted {direction}{pct_change*100:.1f}% since last report", latest_ann
    except Exception:
        pass

    # No material events detected
    return False, "No material price or regulatory changes detected", latest_ann

import os
import re
import time
import requests
import streamlit as st
from google import genai
from normalizer import normalize_stock_data
from db import save_report_to_archive
from checker import verify_stock_report
from screener import pass_pre_screening_gates
from bsedata.bse import BSE
from bse_master import resolve_bse_scrip_code

def fetch_pe_from_google(ticker: str) -> str:
    """Fetches trailing P/E ratio from Google Finance with NSE/BOM fallback."""
    clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for exchange in ["NSE", "BOM"]:
        url = f"https://www.google.com/finance/quote/{clean}:{exchange}"
        try:
            res = requests.get(url, headers=headers, timeout=3)
            if res.status_code == 200:
                match = re.search(r'P/E ratio</div>.*?<div[^>]*>([0-9\.,]+)</div>', res.text, re.DOTALL)
                if match:
                    return match.group(1).strip()
        except Exception:
            continue
    return "N/A"

def fetch_bse_exchange_data(query: str) -> dict:
    """Pulls real-time fundamentals directly from the BSE exchange via scrip lookup."""
    scrip = resolve_bse_scrip_code(query)
    if not scrip:
        raise ValueError(f"Could not resolve an official BSE scrip code for '{query}'.")

    b = BSE()
    q = b.getQuote(scrip)
    if not q or "currentValue" not in q:
        raise ValueError(f"BSE exchange did not return active quote data for scrip {scrip}.")

    mcap_raw = q.get("marketCapFull") or q.get("marketCapFreeFloat") or "0"
    mcap_clean = mcap_raw.replace(" Cr.", "").replace(",", "").strip()
    try:
        mcap_crores = float(mcap_clean)
        mcap_inr = int(mcap_crores * 10000000)
    except ValueError:
        mcap_inr = 0

    clean_ticker = query.strip().upper().replace(".NS", "").replace(".BO", "")
    pe_val = fetch_pe_from_google(clean_ticker)

    return {
        "ticker": clean_ticker,
        "short_name": q.get("companyName", clean_ticker),
        "scrip_code": scrip,
        "current_price": q.get("currentValue", "0.00"),
        "market_cap": mcap_inr,
        "pe_ratio": pe_val,
        "industry": q.get("industry", "Core Industry"),
        "sector": q.get("industry", "Core Industry"),
        "52w_high": q.get("52weekHigh", "N/A"),
        "52w_low": q.get("52weekLow", "N/A"),
        "description": f"BSE Listed Equity under group {q.get('group', 'General')}.",
        "is_fallback": False
    }

def get_stock_fundamentals(query: str) -> dict:
    """Fetches verified exchange data. Raises PipelineError on failure with zero synthetic fallbacks."""
    clean = query.strip().upper().replace(".NS", "").replace(".BO", "")
    scrip = resolve_bse_scrip_code(query)
    if not scrip:
        raise TickerResolutionError(query)

    try:
        raw_data = fetch_bse_exchange_data(query)
    except Exception as bse_err:
        raise ExchangeDataFetchError(scrip, str(bse_err))

    profile_res = {
        "name": raw_data["short_name"],
        "sector": raw_data["sector"],
        "industry": raw_data["industry"],
        "market_capitalization": raw_data["market_cap"],
        "description": raw_data["description"]
    }
    stats_res = {
        "statistics": {
            "valuations_metrics": {
                "trailing_pe": raw_data["pe_ratio"]
            }
        }
    }
    passed_gate, gate_reason = pass_pre_screening_gates(stats_res, profile_res)
    if not passed_gate:
        raise PipelineError("Pre-Screening Gate", f"Stock rejected: {gate_reason}")

    return normalize_stock_data(raw_data, exchange="BSE")


def get_system_prompt(ticker: str, language: str) -> str:
    lang_rule = "The report must be entirely in English (India). Strictly use British/Indian spelling (e.g., analyse, capitalisation, labour)." if language == "English (India)" else f"The report must be fully translated into {language}, including all section headers, analysis, and verdicts without omitting technical detail."

    return f"""You are an expert equity research analyst. Write a comprehensive report for {ticker}.
{lang_rule}

CRITICAL LINGUISTIC RULES:
1. Write at an 8th-grade reading level. Keep sentences short and simple.
2. For any unavoidable financial terminology, include a brief inline definition in parentheses immediately following the term.
3. NEVER use en-dashes or em-dashes in the text. Use colons, commas, or parentheses instead.
4. All financial figures provided are in Indian Rupees (INR) unless explicitly stated otherwise. Express market values in Crores (Cr). Do not use Millions or Billions.

# VERDICT: [BUY / HOLD / SELL]
**Summary:** One concise sentence summarizing the current operational and market standing of the stock.

---

## Pillar 1: Macro-Economic, Geopolitical & Environmental Overlays
* Geopolitics & Supply Chain: Cross-border exposure, trade friction, and sovereign risks.
* Environmental / ESG Factors: Climate vulnerabilities, raw material dependencies, and regulatory compliance.
* Interest Rate & Inflation Cycle: Capital cost sensitivity and pricing power.

## Pillar 2: Industry Dynamics & Competitive Positioning
* Total Addressable Market (TAM): Secular growth horizon and industry expansion rates.
* Porter's Five Forces: Barriers to entry, supplier/buyer power, and competitive intensity.
* Market Share: Dominant sector leader vs. marginal player.

## Pillar 3: Promoter Quality & Fundamental Health
* Profitability Metrics: ROE and ROCE trends.
* Balance Sheet Strength: Debt-to-Equity, cash runway, and dilution risk.
* Revenue Stickiness: High-margin recurring streams vs. lumpy cyclical sales.
* Promoter Governance: Pledging, shareholding trajectory, and alignment with minority holders.

## Pillar 4: The "Structural vs. Temporary" Drop Diagnostic
* Evaluate whether recent price drawdowns are Temporary (accumulation opportunity) or Structural (fundamental thesis damage).

## Pillar 5: Valuation & Margin of Safety
* Multiples: Trailing/Forward P/E, P/B, and EV/EBITDA compared to historic medians and peers.
* Margin of Safety: Estimated discount to intrinsic valuation.

## Pillar 6: Technical & Momentum Overlay
* Moving Averages: 50-day and 200-day DMA positioning.
* Momentum: MACD signals and institutional delivery volume trends.

## Pillar 7: ESG Impact Scorecard
Tabulate the ESG analysis strictly using the following Markdown table format:

| Parameter | Score (0-100) | Evaluation & Key Drivers |
| :--- | :--- | :--- |
| **Environmental** | [Score] | [Key factors, carbon footprint, compliance] |
| **Social** | [Score] | [Labor relations, human capital, community impact] |
| **Governance** | [Score] | [Board independence, transparency, minority rights] |

---

## Conclusion & Actionable Guidance
1. **Verdict:** [BUY / HOLD / SELL] with comprehensive rationale based on the 7 pillars.
2. **Strategy:** Specific, step-by-step portfolio execution roadmap for the investor."""

def extract_response_text(response) -> str:
    text_content = ""
    try:
        if hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, "content") and candidate.content and hasattr(candidate.content, "parts"):
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            text_content += part.text
    except Exception:
        pass
    if not text_content and hasattr(response, "text"):
        text_content = response.text or ""
    return text_content

def call_genai_with_fallback(client, prompt: str, system_prompt: str) -> str:
    models_to_try = ["gemini-3.6-flash", "gemini-flash-latest"]
    last_error = None
    
    for model_name in models_to_try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=system_prompt + """
- Actively verify company developments using Google Search. Ground all qualitative pillars (TAM, competitive moat, governance, ESG) in recent earnings disclosures, quarterly concall commentary, management guidance changes, and regulatory filings from the past 90 to 180 days.
""",
                        tools=[{"google_search": {}}],
                    ),
                )
                return extract_response_text(response)
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "404" in err_str or "NOT_FOUND" in err_str:
                    break
                if any(code in err_str for code in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]):
                    time.sleep(2 ** attempt)
                    continue
                break
            
    raise ValueError(f"API Limit Reached or Model Unavailable. Details: {last_error}")

@st.cache_data(ttl=3600)
def generate_stock_report(ticker: str, language: str = "English (India)") -> str:
    stock_data = get_stock_fundamentals(ticker)
    
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)
    
    system_prompt = get_system_prompt(ticker, language)
    user_prompt = f"Generate the research report for: {stock_data.get('short_name')} ({stock_data.get('ticker')})\nData: {stock_data}"
    
    report_text = call_genai_with_fallback(client, user_prompt, system_prompt)
    passed, discrepancies = verify_stock_report(stock_data, report_text)
    
    if not passed:
        correction_prompt = f"{user_prompt}\n\nPREVIOUS DRAFT FAILED AUDIT. Fix these exact discrepancies: {discrepancies}"
        report_text = call_genai_with_fallback(client, correction_prompt, system_prompt)
        passed, discrepancies = verify_stock_report(stock_data, report_text)
        if not passed:
            report_text += f"\n\n> **Audit Warning:** Report published with unresolved verification flags: {discrepancies}"

    if False:
        report_text = "> ⚠️ **Notice:** Direct exchange data feeds are temporarily restricted by the host network. Analysis and baseline ratios have been synthesized using macroeconomic indicators.\n\n" + report_text

    try:
        save_report_to_archive(stock_data, report_text)
    except Exception as e:
        print(f"Warning: Failed to save to archive: {e}")
        
    return report_text
