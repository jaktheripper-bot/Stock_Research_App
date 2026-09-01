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
            return sym if sym.endswith((".NS", ".BO")) else f"{sym}.NS"
    except Exception as e:
        print(f"Ticker resolution fallback: {e}")
        
    fallback = clean.upper().replace(" ", "")
    return f"{fallback}.NS"

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

REPORT_SYSTEM_PROMPT = """
You are an equity research analyst. Generate a comprehensive stock research report based on the provided metrics using strict Markdown. 
All financial figures provided are in Indian Rupees (INR) unless explicitly stated otherwise. Express market values in Crores (Cr).

You must explicitly include a section titled "Values & Beliefs Impact Scorecard" that scores the company out of 10 across three dimensions:
1. **Corporate Governance & Transparency:** Board independence, minority shareholder treatment, and financial disclosures.
2. **Socio-Economic Impact:** Job creation, local supply chain development, and accessibility of products/services.
3. **Environmental & Sustainability Alignment:** Carbon footprint mitigation, waste management, and transition readiness.
"""

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

def call_genai_with_fallback(client, prompt: str) -> str:
    models_to_try = ["gemini-3.6-flash", "gemini-3.5-flash"]
    last_error = None
    
    for model_name in models_to_try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=REPORT_SYSTEM_PROMPT
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
def generate_stock_report(ticker: str) -> str:
    stock_data = get_stock_fundamentals(ticker)
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    user_prompt = f"Generate the research report for: {stock_data.get('short_name')} ({stock_data.get('ticker')})\nData: {stock_data}"
    
    report_text = call_genai_with_fallback(client, user_prompt)
    passed, discrepancies = verify_stock_report(stock_data, report_text)
    
    if not passed:
        correction_prompt = f"{user_prompt}\n\nPREVIOUS DRAFT FAILED AUDIT. Fix these exact discrepancies: {discrepancies}"
        report_text = call_genai_with_fallback(client, correction_prompt)
        passed, discrepancies = verify_stock_report(stock_data, report_text)
        if not passed:
            report_text += f"\n\n> **Audit Warning:** Report published with unresolved verification flags: {discrepancies}"

    try:
        save_report_to_archive(stock_data, report_text)
    except Exception as e:
        print(f"Warning: Failed to save to archive: {e}")
        
    return report_text
