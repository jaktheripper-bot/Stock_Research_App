import os
import time
import requests
import yfinance as yf
import streamlit as st
from google import genai
from normalizer import normalize_stock_data
from db import save_report_to_archive
from checker import verify_stock_report
from screener import pass_pre_screening_gates
from bsedata.bse import BSE

def correct_ticker_with_ai(query: str) -> str:
    """Fallback fuzzy corrector for misspelled company names using Gemini."""
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(f"Could not identify a valid stock ticker for '{query}'.")
    
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"Identify the official NSE ticker symbol for '{query}'. Return ONLY the ticker symbol ending in .NS or .BO (e.g., TATAMOTORS.NS). If unknown, reply 'UNKNOWN'."
        res = client.models.generate_content(model="gemini-3.5-flash", contents=prompt)
        
        text_content = ""
        if hasattr(res, "text") and res.text:
            text_content = res.text
        elif hasattr(res, "candidates") and res.candidates:
            for candidate in res.candidates:
                if hasattr(candidate, "content") and candidate.content and hasattr(candidate.content, "parts"):
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            text_content += part.text
                            
        text_content = text_content.strip().upper()
        if "UNKNOWN" in text_content or not text_content:
            raise ValueError(f"Could not identify a valid stock ticker for '{query}'. Please check the spelling.")
            
        return text_content if text_content.endswith((".NS", ".BO")) else f"{text_content}.NS"
    except Exception as e:
        raise ValueError(f"Could not identify a valid stock ticker for '{query}': {e}")

def resolve_ticker(query: str) -> str:
    clean = query.strip()
    if clean.upper().endswith((".NS", ".BO")):
        return clean.upper()
        
    headers = {"User-Agent": "Mozilla/5.0"}
    search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={requests.utils.quote(clean)}&quotesCount=10"
    
    try:
        res = requests.get(search_url, headers=headers, timeout=5).json()
        quotes = res.get("quotes", [])
        for q in quotes:
            sym = q.get("symbol", "")
            if sym.endswith((".NS", ".BO")):
                return sym
        if quotes:
            sym = quotes[0].get("symbol", "")
            if sym.endswith((".NS", ".BO")):
                return sym
    except Exception as e:
        print(f"Ticker resolution fallback: {e}")
        
    return correct_ticker_with_ai(clean)

def fetch_fundamentals_with_fallback(query: str, ticker_symbol: str) -> dict:
    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        if info and len(info) >= 5 and (info.get("regularMarketPrice") is not None or info.get("currentPrice") is not None or info.get("marketCap") is not None):
            return info
    except Exception as e:
        print(f"Primary source (yfinance) failed: {e}. Trying secondary fallback...")

    try:
        b = BSE()
        clean_code = ticker_symbol.split(".")[0]
        if clean_code.isdigit():
            q = b.getQuote(clean_code)
            if q and "currentValue" in q:
                market_cap_val = 0
                try:
                    market_cap_val = float(q.get("mCap", "0").replace(",", "")) * 10000000
                except Exception:
                    pass
                return {
                    "longName": q.get("companyName", clean_code),
                    "sector": "General Industry",
                    "industry": "General Industry",
                    "marketCap": market_cap_val,
                    "trailingPE": "N/A"
                }
    except Exception as e:
        print(f"Secondary source (bsedata) failed: {e}")

    raise ValueError(f"Fatal Data Error: Both primary (yfinance) and secondary (bsedata) sources failed for query: '{query}' (Resolved: '{ticker_symbol}'). Report generation aborted.")

@st.cache_data(ttl=3600)
def get_stock_fundamentals(query: str):
    ticker_symbol = resolve_ticker(query)
    info = fetch_fundamentals_with_fallback(query, ticker_symbol)

    market_cap_raw = info.get("marketCap") or info.get("mCap") or 0
    if market_cap_raw == 0:
        raise ValueError(f"Fatal Data Error: Market capitalization is zero or missing for '{ticker_symbol}'. Report generation aborted.")

    pe_ratio_raw = info.get("trailingPE") or info.get("forwardPE") or "N/A"
    clean_ticker = ticker_symbol.split(".")[0]
    
    profile_res = {
        "name": info.get("longName", clean_ticker),
        "sector": info.get("sector", "Financial Services"),
        "industry": info.get("industry", "General Industry"),
        "market_capitalization": market_cap_raw,
        "description": info.get("businessSummary", f"Equity asset profile for {clean_ticker}.")
    }
    stats_res = {
        "statistics": {
            "valuations_metrics": {
                "trailing_pe": pe_ratio_raw
            }
        }
    }
    
    passed_gate, gate_reason = pass_pre_screening_gates(stats_res, profile_res)
    if not passed_gate:
        raise ValueError(f"Stock Pre-Screening Rejected: {gate_reason}")
    
    raw_data = {
        "ticker": clean_ticker,
        "short_name": profile_res["name"],
        "sector": profile_res["sector"],
        "industry": profile_res["industry"],
        "market_cap": market_cap_raw,
        "pe_ratio": pe_ratio_raw,
        "description": profile_res["description"]
    }
    
    return normalize_stock_data(raw_data, exchange="NSE" if ticker_symbol.endswith(".NS") else "BSE")

def get_system_prompt(ticker: str, language: str) -> str:
    lang_rule = "The report must be entirely in English (India). Strictly use British/Indian spelling (e.g., analyse, capitalisation, labour)." if language == "English (India)" else f"The report must be fully translated into {language}, including all section headers, analysis, and verdicts without omitting technical detail."

    return f"""You are an expert equity research analyst. Write a comprehensive report for {ticker}.
{lang_rule}

CRITICAL LINGUISTIC RULES:
1. Write at an 8th-grade reading level. Keep sentences short and simple.
2. For any unavoidable financial terminology, include a brief inline definition in parentheses immediately following the term.
3. NEVER use en-dashes (-) or em-dashes (—) in the text. Use colons, commas, or parentheses instead.
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
* Porter’s Five Forces: Barriers to entry, supplier/buyer power, and competitive intensity.
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
    models_to_try = ["gemini-3.6-flash", "gemini-3.5-flash"]
    last_error = None
    
    for model_name in models_to_try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=system_prompt
                    ),
                )
                return extract_response_text(response)
            except Exception as e:
                last_error = e
                err_str = str(e)
                if any(code in err_str for code in ["429", "RESOURCE_EXHAUSTED", "404", "503", "UNAVAILABLE"]):
                    time.sleep(2 ** attempt)
                    continue
                raise e
            
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

    try:
        save_report_to_archive(stock_data, report_text)
    except Exception as e:
        print(f"Warning: Failed to save to archive: {e}")
        
    return report_text