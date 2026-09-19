import os
import re
import sys
import json
import time
import random
import contextlib
import requests
from datetime import datetime, timezone
import streamlit as st
from google import genai
from normalizer import normalize_stock_data
from db import save_report_to_archive
from checker import verify_stock_report
from screener import pass_pre_screening_gates
from bsedata.bse import BSE
from bse_master import resolve_bse_scrip_code

def extract_health_matrix(report_text: str) -> dict:
    """
    Parses the 7-Pillar Health Matrix from report text.
    Resilient to asterisks (*), hyphens (-), brackets, and casing.
    """
    if not report_text or not isinstance(report_text, str):
        return {}

    clean = report_text.replace("\xa0", " ").replace("–", "-").replace("—", "-")

    matrix = {
        "Macro": "Neutral", "Moat": "Moderate", "Governance": "Clean",
        "Diagnostic": "N/A", "Valuation": "Fair", "BalanceSheet": "Resilient", "Verdict": "Watchlist"
    }

    patterns = {
        "Macro": r"(?:[-*•]|\d+\.)?\s*Macro\s*:\s*\[?\s*(Stable\vert{}Headwinds\vert{}Neutral)\s*\]?",
        "Moat": r"(?:[-*•]|\d+\.)?\s*Moat\s*:\s*\[?\s*(Wide\vert{}Moderate\vert{}Narrow)\s*\]?",
        "Governance": r"(?:[-*•]|\d+\.)?\s*Governance\s*:\s*\[?\s*(Clean\vert{}Caution\vert{}High Risk)\s*\]?",
        "Diagnostic": r"(?:[-*•]|\d+\.)?\s*Diagnostic\s*:\s*\[?\s*(Temporary\vert{}Structural\vert{}Neutral\vert{}N/A)\s*\]?",
        "Valuation": r"(?:[-*•]|\d+\.)?\s*Valuation\s*:\s*\[?\s*(Undervalued\vert{}Fair\vert{}Stretched\vert{}Loss-Making)\s*\]?",
        "BalanceSheet": r"(?:[-*•]|\d+\.)?\s*Balance\s*Sheet\s*:\s*\[?\s*(Debt-Free\vert{}Moderate Debt\vert{}High Debt\vert{}Resilient)\s*\]?",
        "Verdict": r"(?:[-*•]|\d+\.)?\s*Verdict\s*:\s*\[?\s*(BUY\vert{}WATCHLIST\vert{}AVOID\vert{}Buy\vert{}Watchlist\vert{}Avoid)\s*\]?"
    }

    found_any = False
    for key, pat in patterns.items():
        match = re.search(pat, clean, re.IGNORECASE)
        if match:
            matrix[key] = match.group(1).strip().title()
            found_any = True

    if not found_any:
        v_match = re.search(r"#+\s*VERDICT:\s*\[?\s*(BUY\vert{}WATCHLIST\vert{}AVOID)\s*\]?", clean, re.IGNORECASE)
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

class PipelineError(Exception):
    def __init__(self, stage: str, message: str, technical_details: str = ""):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.technical_details = technical_details

class TickerResolutionError(PipelineError):
    def __init__(self, query: str):
        super().__init__(
            stage="Ticker Resolution",
            message=f"Could not resolve an official BSE scrip code for '{query}'.",
            technical_details="Evaluated static map, Supabase master universe, and JIT AI discovery. Zero active quotes confirmed."
        )

class ExchangeDataFetchError(PipelineError):
    def __init__(self, scrip: str, detail: str):
        super().__init__(
            stage="Exchange Data Ingestion",
            message=f"BSE exchange rejected or failed to return quote data for scrip {scrip}.",
            technical_details=detail
        )

def resolve_pe_with_failsafes(ticker: str, scrip: str = "") -> str:
    clean = ticker.strip().upper().replace(".NS", "").replace(".BO", "").replace(" ", "")
    # Tier 1: Consolidated yfinance
    try:
        import yfinance as yf
        symbols = [f"{clean}.NS", f"{clean}.BO"]
        if scrip and str(scrip).isdigit():
            symbols.append(f"{scrip}.BO")
        with open(os.devnull, "w") as devnull:
            with contextlib.redirect_stderr(devnull):
                for s in symbols:
                    try:
                        tk = yf.Ticker(s)
                        info = tk.info or {}
                        trailing_eps = info.get("trailingEps")
                        trailing_pe = info.get("trailingPE")
                        if trailing_eps is not None and float(trailing_eps) <= 0:
                            return "N/A (Loss-Making)"
                        if trailing_pe and float(trailing_pe) > 0:
                            return f"{float(trailing_pe):.2f}"
                    except Exception:
                        continue
    except Exception:
        pass

    # Tier 2: BSE ComHeader Direct
    if scrip and str(scrip).isdigit():
        try:
            url = f"https://api.bseindia.com/BseIndiaAPI/api/ComHeader/w?quotetype=EQ&scripcode={scrip}&seriesid="
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"}
            res = requests.get(url, headers=headers, timeout=3)
            if res.status_code == 200:
                raw_pe = res.json().get("PE")
                if raw_pe and str(raw_pe).strip() not in ["", "-", "None", "0", "0.00"]:
                    val = float(str(raw_pe).replace(",", "").strip())
                    return f"{val:.2f}" if val > 0 else "N/A (Loss-Making)"
        except Exception:
            pass
    return "N/A"

def fetch_latest_bse_announcement(scrip_code: str) -> str:
    if not scrip_code or not str(scrip_code).isdigit():
        return ""
    try:
        url = f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate=&strScrip={scrip_code}&strSearch=P&strToDate=&strType=C"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            table = res.json().get("Table", [])
            if table:
                return (table[0].get("NEWSSUB") or table[0].get("HEADLINE") or "").strip()
    except Exception:
        pass
    return ""

def evaluate_material_change(cached: dict, live_fund: dict, scrip_code: str) -> tuple:
    if not cached:
        return True, "Initial analysis", ""
    raw_ts = cached.get("raw_timestamp")
    if raw_ts:
        try:
            ts = raw_ts if isinstance(raw_ts, datetime) else datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if (now - ts).total_seconds() / 86400.0 > 14:
                return True, "Report is > 14 days old", ""
        except Exception:
            pass

    latest_ann = fetch_latest_bse_announcement(scrip_code)
    cached_ann = cached.get("latest_announcement", "")
    if latest_ann and cached_ann and latest_ann != cached_ann:
        return True, f"New BSE Filing: {latest_ann[:40]}...", latest_ann

    cached_price = cached.get("baseline_price")
    live_price = live_fund.get("current_price") or live_fund.get("currentValue")
    try:
        c_p = float(str(cached_price).replace(",", "").strip())
        l_p = float(str(live_price).replace(",", "").strip())
        if c_p > 0 and (abs(l_p - c_p) / c_p) >= 0.05:
            d = "+" if l_p > c_p else "-"
            return True, f"Price shifted {d}{(abs(l_p - c_p) / c_p)*100:.1f}%", latest_ann
    except Exception:
        pass
    return False, "No material price or regulatory change", latest_ann

def fetch_bse_exchange_data(query: str) -> dict:
    scrip = resolve_bse_scrip_code(query)
    if not scrip:
        raise ValueError(f"Could not resolve an official BSE scrip code for '{query}'.")

    b = BSE()
    q = b.getQuote(scrip)
    if not q or "currentValue" not in q:
        raise ValueError(f"BSE exchange did not return quote data for scrip {scrip}.")

    mcap_raw = q.get("marketCapFull") or q.get("marketCapFreeFloat") or "0"
    mcap_clean = mcap_raw.replace(" Cr.", "").replace(",", "").strip()
    try:
        mcap_inr = int(float(mcap_clean) * 10_000_000)
    except Exception:
        mcap_inr = 0

    clean_ticker = query.strip().upper().replace(".NS", "").replace(".BO", "")
    resolved_pe = resolve_pe_with_failsafes(q.get("scrip_id") or clean_ticker, scrip)

    return {
        "ticker": clean_ticker,
        "short_name": q.get("companyName", clean_ticker),
        "scrip_code": scrip,
        "current_price": q.get("currentValue", "0.00"),
        "market_cap": mcap_inr,
        "pe_ratio": resolved_pe,
        "industry": q.get("industry", "Core Industry"),
        "sector": q.get("industry", "Core Industry"),
        "52w_high": q.get("52weekHigh", "N/A"),
        "52w_low": q.get("52weekLow", "N/A"),
        "description": f"BSE Listed Equity under group {q.get('group', 'General')}.",
        "is_fallback": False
    }

def get_stock_fundamentals(query: str) -> dict:
    clean = query.strip().upper().replace(".NS", "").replace(".BO", "")
    scrip = resolve_bse_scrip_code(query)
    if not scrip:
        raise TickerResolutionError(query)
    try:
        raw_data = fetch_bse_exchange_data(query)
    except Exception as bse_err:
        raise ExchangeDataFetchError(scrip, str(bse_err))

    profile_res = {
        "name": raw_data["short_name"], "sector": raw_data["sector"],
        "industry": raw_data["industry"], "market_capitalization": raw_data["market_cap"],
        "description": raw_data["description"]
    }
    stats_res = {"statistics": {"valuations_metrics": {"trailing_pe": raw_data["pe_ratio"]}}}
    passed, reason = pass_pre_screening_gates(stats_res, profile_res)
    if not passed:
        raise PipelineError("Pre-Screening Gate", f"Stock rejected: {reason}")
    return normalize_stock_data(raw_data, exchange="BSE")

def get_system_prompt(ticker: str, language: str) -> str:
    lang_rule = "The report must be entirely in English (India) using British/Indian spelling." if language == "English (India)" else f"The report must be fully translated into {language} without omitting technical rigor."
    return f"""You are an institutional equity research analyst. Write a comprehensive research report for {ticker}.
{lang_rule}

### Health Matrix
- Macro: [Stable | Headwinds | Neutral]
- Moat: [Wide | Moderate | Narrow]
- Governance: [Clean | Caution | High Risk]
- Diagnostic: [Temporary | Structural | Neutral | N/A]
- Valuation: [Undervalued | Fair | Stretched | Loss-Making]
- Balance Sheet: [Debt-Free | Moderate Debt | High Debt]
- Verdict: [BUY | WATCHLIST | AVOID]

CRITICAL LINGUISTIC RULES:
1. Write at an 8th-grade reading level. Keep sentences short and simple.
2. For financial terms, provide a brief definition in parentheses.
3. Express all Indian corporate metrics in Crores (Cr) and Indian Rupees (INR).

# VERDICT: [BUY / WATCHLIST / AVOID]
**Summary:** One concise sentence summarizing the operational standing.

---
## Pillar 1: Macro-Economic, Geopolitical & Environmental Overlays
## Pillar 2: Industry Dynamics & Competitive Positioning
## Pillar 3: Promoter Quality & Fundamental Health
## Pillar 4: The "Structural vs. Temporary" Drop Diagnostic
## Pillar 5: Valuation & Margin of Safety
## Pillar 6: Technical & Momentum Overlay
## Pillar 7: ESG Impact Scorecard
Tabulate the ESG analysis strictly using the following Markdown table format:
| Parameter | Score (0-100) | Evaluation & Key Drivers |
| :--- | :--- | :--- |
| **Environmental** | [Score] | [Key factors] |
| **Social** | [Score] | [Labor, community impact] |
| **Governance** | [Score] | [Board independence, transparency] |

---
## Conclusion & Actionable Guidance
1. **Verdict:** [BUY / WATCHLIST / AVOID]
2. **Strategy:** Portfolio execution roadmap."""

_DISCOVERED_MODELS_CACHE = {"models": [], "timestamp": 0}

def get_latest_flash_models(client) -> list:
    now = time.time()
    if _DISCOVERED_MODELS_CACHE["models"] and (now - _DISCOVERED_MODELS_CACHE["timestamp"]) < 86400:
        return _DISCOVERED_MODELS_CACHE["models"]
    fallback = ["gemini-3.6-flash", "gemini-2.0-flash"]
    try:
        discovered = []
        for m in client.models.list():
            model_id = m.name.replace("models/", "") if hasattr(m, "name") else ""
            if "gemini" in model_id and "flash" in model_id and "preview" not in model_id:
                if not any(k in model_id for k in ["image", "tts", "audio", "embed"]):
                    match = re.search(r"gemini-(\d+(?:\.\d+)?)", model_id)
                    if match:
                        discovered.append((float(match.group(1)), model_id))
        if discovered:
            discovered.sort(key=lambda x: x[0], reverse=True)
            ordered = [x[1] for x in discovered]
            _DISCOVERED_MODELS_CACHE["models"] = ordered
            _DISCOVERED_MODELS_CACHE["timestamp"] = now
            return ordered
    except Exception:
        pass
    return fallback

def stream_genai_with_fallback(client, prompt: str, system_prompt: str, on_status=None):
    models_to_try = get_latest_flash_models(client)[:2]
    last_error = None
    for model_name in models_to_try:
        if on_status:
            on_status(f"⚡ Connected to model `{model_name}`...")
        for attempt in range(2):
            try:
                chat = client.chats.create(
                    model=model_name,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=system_prompt + "\n- Search recent BSE/NSE disclosures and concalls from the past 90-180 days.",
                        tools=[{"google_search": {}}],
                    )
                )
                if on_status:
                    on_status("🔍 Grounding against official filings...")
                for chunk in chat.send_message_stream(prompt):
                    extracted_text = None
                    if hasattr(chunk, "candidates") and chunk.candidates:
                        for cand in chunk.candidates:
                            content_obj = getattr(cand, "content", None)
                            if content_obj and hasattr(content_obj, "parts"):
                                for part in content_obj.parts:
                                    t = getattr(part, "text", None)
                                    if t:
                                        extracted_text = t
                                        break
                    if not extracted_text:
                        try:
                            extracted_text = chunk.text
                        except Exception:
                            pass
                    if extracted_text:
                        yield extracted_text
                return
            except Exception as e:
                last_error = e
                err_str = str(e)
                if any(code in err_str for code in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]):
                    time.sleep(1.0 + random.uniform(0.2, 1.0))
                    continue
                break
    raise ValueError(f"Gemini grounded search exhausted: {last_error}")

def stream_perplexity_fallback(prompt: str, system_prompt: str):
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("PERPLEXITY_API_KEY")
        except Exception:
            pass
    if not api_key:
        raise ValueError("PERPLEXITY_API_KEY missing from secrets/environment.")

    url = "https://api.perplexity.ai/v1/responses"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "text/event-stream"}
    payload = {"preset": "low", "input": prompt, "instructions": system_prompt, "stream": True}

    res = requests.post(url, headers=headers, json=payload, stream=True, timeout=20)
    if res.status_code != 200:
        raise RuntimeError(f"Perplexity Agent API HTTP {res.status_code}: {res.text}")

    for raw_line in res.iter_lines(decode_unicode=False):
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="replace")
        if line.startswith("data: "):
            data_str = line[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                event = json.loads(data_str)
                delta = event.get("delta") or (event.get("type") == "response.output_text.delta" and event.get("delta"))
                if delta:
                    yield delta
            except Exception:
                continue

def stream_gemini_ungrounded_bypass(client, prompt: str, system_prompt: str):
    model_name = get_latest_flash_models(client)[0]
    chat = client.chats.create(
        model=model_name,
        config=genai.types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.2)
    )
    for chunk in chat.send_message_stream(prompt):
        t = getattr(chunk, "text", None)
        if t:
            yield t

def stream_stock_report(ticker: str, language: str = "English (India)", stock_data: dict = None, on_status=None):
    if stock_data is None:
        stock_data = get_stock_fundamentals(ticker)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            pass
    client = genai.Client(api_key=api_key)
    system_prompt = get_system_prompt(ticker, language)
    user_prompt = f"Generate research report for: {stock_data.get('short_name')} ({stock_data.get('ticker')})\nData: {stock_data}"

    report_accumulator = []
    try:
        for chunk in stream_genai_with_fallback(client, user_prompt, system_prompt, on_status=on_status):
            report_accumulator.append(chunk)
            yield chunk
    except Exception:
        notice_p = "\n\n> ⚠️ **Gemini Grounding Unavailable. Rerouting to Perplexity Agent API...**\n\n"
        report_accumulator.append(notice_p)
        yield notice_p
        try:
            for chunk in stream_perplexity_fallback(user_prompt, system_prompt):
                report_accumulator.append(chunk)
                yield chunk
        except Exception:
            notice_u = (
                "\n\n> ⚠️ **Notice: Live Web Grounding Offline.**\n"
                "> Synthesizing thesis from core parametric intelligence.\n"
                "> *Note:* Exchange metrics are verified, but recent disclosures may be omitted.\n\n"
            )
            report_accumulator.append(notice_u)
            yield notice_u
            try:
                for chunk in stream_gemini_ungrounded_bypass(client, user_prompt, system_prompt):
                    report_accumulator.append(chunk)
                    yield chunk
            except Exception as final_err:
                err_msg = f"\n\n> ❌ **Live Synthesis Failed:** {final_err}"
                report_accumulator.append(err_msg)
                yield err_msg

    complete_text = "".join(report_accumulator)
    try:
        passed, disc = verify_stock_report(stock_data, complete_text)
        if not passed:
            note = f"\n\n> ⚠️ **Verification Audit Note:** {disc}"
            complete_text += note
            yield note
    except Exception:
        pass

    try:
        scrip = stock_data.get("scrip_code", "")
        ann = fetch_latest_bse_announcement(scrip)
        save_report_to_archive(stock_data, complete_text, announcement=ann)
    except Exception:
        pass

def generate_stock_report(ticker: str, language: str = "English (India)") -> str:
    chunks = []
    for c in stream_stock_report(ticker, language):
        chunks.append(c)
    return "".join(chunks)
