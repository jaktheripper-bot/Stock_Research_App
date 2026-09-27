import os
import re
import sys
import json
import time
import random
import contextlib
import requests
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from google import genai
from normalizer import normalize_stock_data
from db import save_report_to_archive
from checker import verify_stock_report
from screener import pass_pre_screening_gates
from bsedata.bse import BSE
from bse_master import resolve_bse_scrip_code

def enrich_fundamentals(ticker: str, data: dict) -> dict:
    """Secondary enrichment: uses yfinance strictly to backfill trailing P/E, Market Cap, and Sector."""
    try:
        import yfinance as yf
        clean_sym = str(ticker).strip().upper().replace(".NS", "").replace(".BO", "")
        yf_ticker = f"{clean_sym}.BO" if clean_sym.isdigit() else f"{clean_sym}.NS"
        info = yf.Ticker(yf_ticker).info or {}

        # Trailing P/E
        if data.get("pe_ratio") in [None, "N/A", "-", "", 0, "0"]:
            pe = info.get("trailingPE")
            if pe is not None and isinstance(pe, (int, float)):
                data["pe_ratio"] = round(pe, 2) if pe > 0 else "N/A (Loss-Making)"

        # Market Cap
        if data.get("market_cap") in [None, "N/A", 0, "-", "", "0"]:
            mcap = info.get("marketCap")
            if mcap and isinstance(mcap, (int, float)):
                data["market_cap"] = int(mcap)

        # Sector & Industry
        if data.get("sector") in [None, "N/A", "-", "", "Core Industry", "Diversified / Core Industry"]:
            sec = info.get("sector")
            if sec:
                data["sector"] = sec
        if data.get("industry") in [None, "N/A", "-", "", "General Corporate"]:
            ind = info.get("industry")
            if ind:
                data["industry"] = ind
    except Exception as e:
        print(f"Background fundamental enrichment notice: {e}")
    return data

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
        "Diagnostic": "N/A", "Valuation": "Fair", "BalanceSheet": "Resilient", "CapitalAllocation": "Disciplined"
    }

    patterns = {
        "Macro": r"(?i)(?:[-*•]|\d+\.)?\s*Macro\s*[:\-]?\s*\[?\s*(Stable|Headwinds|Neutral)\s*\]?",
        "Moat": r"(?i)(?:[-*•]|\d+\.)?\s*Moat\s*[:\-]?\s*\[?\s*(Wide|Moderate|Narrow)\s*\]?",
        "Governance": r"(?i)(?:[-*•]|\d+\.)?\s*Governance\s*[:\-]?\s*\[?\s*(Clean|Caution|High Risk)\s*\]?",
        "Diagnostic": r"(?i)(?:[-*•]|\d+\.)?\s*Diagnostic\s*[:\-]?\s*\[?\s*(Temporary|Structural|Neutral|N/A)\s*\]?",
        "Valuation": r"(?i)(?:[-*•]|\d+\.)?\s*Valuation\s*[:\-]?\s*\[?\s*(Undervalued|Fair|Stretched|Loss-Making)\s*\]?",
        "BalanceSheet": r"(?i)(?:[-*•]|\d+\.)?\s*Balance\s*Sheet\s*[:\-]?\s*\[?\s*(Debt-Free|Moderate Debt|High Debt|Resilient)\s*\]?",
        "CapitalAllocation": r"(?i)(?:[-*•]|\d+\.)?\s*Capital\s*Allocation\s*[:\-]?\s*\[?\s*(Disciplined|Moderate|Strained)\s*\]?"
    }

    for key, pat in patterns.items():
        match = re.search(pat, clean)
        if match:
            matrix[key] = match.group(1).strip().title()

    if matrix.get("CapitalAllocation") == "Disciplined":
        ca_match = re.search(r"(?i)Capital\s*Allocation\s*[:\-]?\s*\[?\s*(Disciplined|Moderate|Strained)\s*\]?", clean)
        if ca_match:
            matrix["CapitalAllocation"] = ca_match.group(1).strip().title()

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

def strip_conclusion_sections(text: str) -> str:
    """
    Strips conclusion, monitorables, recommendations, and actionable guidance sections
    for strict SEBI Safe Harbor compliance.
    """
    if not text or not isinstance(text, str):
        return ""
    conclusion_pattern = r'(?im)^\s*#*\s*(?:\d+[\.:\)]\s*)?(?:Conclusion|Key Monitorables|Actionable Guidance|Diagnostic Synthesis|Recommendation|Target Price|Investment Summary\b|Outlook & Recommendation|Strategic Portfolio Roadmap|निष्कर्ष|कार्रवाई योग्य मार्गदर्शन)'
    parts = re.split(conclusion_pattern, text)
    cleaned = parts[0] if len(parts) > 1 else text
    cleaned = re.sub(r'(?im)^\s*(?:#+|\*\*|__)?\s*VERDICT\s*:\s*(?:BUY|HOLD|SELL|AVOID)\b[^\n]*\n*', '', cleaned)
    cleaned = re.sub(r'(?im)^[ \t]*[-*•]\s*(?:Verdict|Rating|Recommendation)\s*:\s*(?:BUY|HOLD|SELL|AVOID)\b[^\n]*\n*', '', cleaned)
    cleaned = re.sub(r'\n*---\s*$', '', cleaned.rstrip())
    return cleaned.strip()


def compare_revisions(rev_a: dict, rev_b: dict) -> dict:
    """
    Standalone differential engine: compares two discrete report states (State A vs State B).
    State A is the older revision, State B is the newer revision.
    Returns a structured diff dict with pillar migrations, metric deltas,
    value trap detection, and trigger provenance — all purely descriptive diagnostics.

    Designed to be decoupled: accepts any two revision dicts, enabling
    "Current vs Previous", "Current vs 1 Year Ago", or "Current vs Pre-COVID" comparisons.
    """
    matrix_a = extract_health_matrix(rev_a.get("report_text", ""))
    matrix_b = extract_health_matrix(rev_b.get("report_text", ""))

    # Pillar quality rankings: index 0 = strongest, higher index = weaker
    PILLAR_RANKS = {
        "Macro": ["Stable", "Neutral", "Headwinds"],
        "Moat": ["Wide", "Moderate", "Narrow"],
        "Governance": ["Clean", "Caution", "High Risk"],
        "Diagnostic": ["Temporary", "Neutral", "Structural", "N/A"],
        "Valuation": ["Undervalued", "Fair", "Stretched", "Loss-Making"],
        "BalanceSheet": ["Debt-Free", "Resilient", "Moderate Debt", "High Debt"],
        "CapitalAllocation": ["Disciplined", "Moderate", "Strained"],
    }

    PILLAR_LABELS = {
        "Macro": "Macro Environment",
        "Moat": "Competitive Moat",
        "Governance": "Governance & Promoters",
        "Diagnostic": "Drop Diagnostic",
        "Valuation": "Valuation Multiple",
        "BalanceSheet": "Balance Sheet Leverage",
        "CapitalAllocation": "Capital Allocation",
    }

    pillar_migrations = []
    downgrade_count = 0
    upgrade_count = 0

    for pillar, ranks in PILLAR_RANKS.items():
        val_a = matrix_a.get(pillar, "N/A")
        val_b = matrix_b.get(pillar, "N/A")
        if val_a == val_b:
            continue

        rank_a = ranks.index(val_a) if val_a in ranks else -1
        rank_b = ranks.index(val_b) if val_b in ranks else -1

        if rank_a == -1 or rank_b == -1:
            direction = "changed"
        elif rank_b > rank_a:
            direction = "downgrade"
            downgrade_count += 1
        else:
            direction = "upgrade"
            upgrade_count += 1

        pillar_migrations.append({
            "pillar": pillar,
            "label": PILLAR_LABELS.get(pillar, pillar),
            "from": val_a,
            "to": val_b,
            "direction": direction,
        })

    # Quantitative metric deltas
    metric_deltas = {}
    for key, label in [("baseline_price", "Price (₹)"), ("baseline_pe", "Trailing P/E"), ("baseline_mcap", "Market Cap")]:
        raw_a = rev_a.get(key)
        raw_b = rev_b.get(key)
        try:
            num_a = float(str(raw_a).replace(",", "").replace("N/A", "0").replace("Loss-Making", "0").strip() or "0")
            num_b = float(str(raw_b).replace(",", "").replace("N/A", "0").replace("Loss-Making", "0").strip() or "0")
        except (ValueError, TypeError):
            num_a, num_b = 0.0, 0.0

        pct_change = ((num_b - num_a) / num_a * 100.0) if num_a > 0 else 0.0
        metric_deltas[key] = {
            "label": label,
            "state_a": raw_a,
            "state_b": raw_b,
            "num_a": num_a,
            "num_b": num_b,
            "pct_change": round(pct_change, 1),
        }

    # Value Trap Detection: qualitative downgrade + valuation expansion (price or P/E rise)
    price_delta = metric_deltas.get("baseline_price", {}).get("pct_change", 0.0)
    pe_delta = metric_deltas.get("baseline_pe", {}).get("pct_change", 0.0)
    value_trap_detected = downgrade_count > 0 and (price_delta > 5.0 or pe_delta > 10.0)

    # Trigger provenance
    trigger_b = rev_b.get("revision_trigger", "Unknown")

    return {
        "state_a_date": rev_a.get("formatted_date", "Unknown"),
        "state_b_date": rev_b.get("formatted_date", "Unknown"),
        "pillar_migrations": pillar_migrations,
        "migration_count": len(pillar_migrations),
        "upgrades": upgrade_count,
        "downgrades": downgrade_count,
        "metric_deltas": metric_deltas,
        "value_trap_detected": value_trap_detected,
        "value_trap_detail": (
            f"{downgrade_count} qualitative downgrade(s) alongside "
            f"{'+' if price_delta > 0 else ''}{price_delta:.1f}% price shift"
        ) if value_trap_detected else "",
        "revision_trigger": trigger_b,
        "matrix_a": matrix_a,
        "matrix_b": matrix_b,
    }


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
        now_dt = datetime.now()
        str_to_date = now_dt.strftime("%Y%m%d")
        str_prev_date = (now_dt - timedelta(days=60)).strftime("%Y%m%d")
        url = f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate={str_prev_date}&strScrip={scrip_code}&strSearch=P&strToDate={str_to_date}&strType=C"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bseindia.com/"
        }
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
        return True, "⚡ Fresh Analysis: Initial dossier synthesis", ""
    raw_ts = cached.get("raw_timestamp")
    if raw_ts:
        try:
            ts = raw_ts if isinstance(raw_ts, datetime) else datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if (now - ts).total_seconds() / 86400.0 > 14:
                return True, "⚡ Regenerated: Report exceeded 14-day freshness window", ""
        except Exception:
            pass

    latest_ann = fetch_latest_bse_announcement(scrip_code)
    cached_ann = cached.get("latest_announcement", "")
    if latest_ann and cached_ann and latest_ann != cached_ann:
        return True, f"⚡ Regenerated: New BSE Filing ({latest_ann[:35]}...)", latest_ann

    cached_price = cached.get("baseline_price")
    live_price = live_fund.get("current_price") or live_fund.get("currentValue")
    try:
        c_p = float(str(cached_price).replace(",", "").strip())
        l_p = float(str(live_price).replace(",", "").strip())
        if c_p > 0 and (abs(l_p - c_p) / c_p) >= 0.05:
            d = "+" if l_p > c_p else "-"
            return True, f"⚡ Regenerated: Price shifted {d}{(abs(l_p - c_p) / c_p)*100:.1f}% vs baseline", latest_ann
    except Exception:
        pass
    return False, "🛡️ Verified Cache: No material events detected (Live quote updated)", latest_ann

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
    """
    Primary entry point: Fetches verified exchange data from BSE.
    If BSE direct fails or reports inactive, falls back gracefully to Yahoo Finance.
    """
    import yfinance as yf
    clean = query.strip().upper().replace(".NS", "").replace(".BO", "")
    
    # Try primary BSE ingestion
    try:
        raw_data = fetch_bse_exchange_data(query)
        if raw_data and not raw_data.get("is_fallback", False):
            return raw_data
    except Exception as bse_err:
        print(f"[WARN] BSE direct quote failed for {query} ({bse_err}). Attempting yfinance fallback...")

    # Secondary Resilience Fallback via yfinance
    try:
        for sym in [f"{clean}.NS", f"{clean}.BO"]:
            t = yf.Ticker(sym)
            fast = getattr(t, "fast_info", None)
            info = {}
            try:
                info = t.info or {}
            except Exception:
                pass

            price = None
            if fast and hasattr(fast, "last_price") and fast.last_price:
                price = fast.last_price
            elif info.get("currentPrice"):
                price = info.get("currentPrice")
            elif info.get("regularMarketPrice"):
                price = info.get("regularMarketPrice")

            if price:
                mcap = getattr(fast, "market_cap", None) or info.get("marketCap") or "N/A"
                pe = info.get("trailingPE") or info.get("forwardPE") or "N/A"
                if isinstance(pe, (int, float)) and pe <= 0:
                    pe = "N/A"

                return {
                    "ticker": clean,
                    "short_name": info.get("shortName") or info.get("longName") or clean,
                    "sector": info.get("sector") or "General Industry",
                    "industry": info.get("industry") or "Diversified",
                    "market_cap": mcap,
                    "pe_ratio": f"{pe:.2f}" if isinstance(pe, (int, float)) else str(pe),
                    "current_price": round(price, 2),
                    "52w_high": getattr(fast, "year_high", None) or info.get("fiftyTwoWeekHigh") or "N/A",
                    "52w_low": getattr(fast, "year_low", None) or info.get("fiftyTwoWeekLow") or "N/A",
                    "description": info.get("longBusinessSummary") or f"Exchange data synthesized for {clean}.",
                    "exchange_status": "Active / Secondary (yfinance Fallback)",
                    "is_fallback": True
                }
    except Exception as yf_err:
        print(f"[WARN] yfinance fallback also failed for {query}: {yf_err}")

    # If both fail, raise clean error
    raise ExchangeDataFetchError(clean, "Both primary BSE and secondary market gateways failed to return live quotes.")

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
- Capital Allocation: [Disciplined | Moderate | Strained]

CRITICAL LINGUISTIC RULES:
1. Write at an 8th-grade reading level. Keep sentences short and simple.
2. ABBREVIATION MANDATE: On first mention of any abbreviation or acronym (e.g., P/E, ROCE, ROE, EPS, CAGR, DCF, EBITDA, CAPEX, TAM, 50-DMA), immediately provide its full form in brackets [e.g., P/E [Price-to-Earnings Ratio], ROCE [Return on Capital Employed], CAGR [Compound Annual Growth Rate]]. Subsequent mentions should use the acronym alone. Do NOT expand abbreviations inside the `### Health Matrix` block or Markdown table cells/headers.
3. Express all Indian corporate metrics in Crores (Cr) and Indian Rupees (INR).

# DIAGNOSTIC SUMMARY & KEY TAKEAWAYS
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


CRITICAL COMPLIANCE DIRECTIVE: Strictly avoid providing any conclusions, forward-looking advice, actionable investment guidance, Buy/Sell/Hold verdicts, investment recommendations, portfolio allocation advice, target prices, trade execution signals, or portfolio roadmaps. The research report concludes strictly after Pillar 7. All analysis must remain purely descriptive, factual, and diagnostic under SEBI Safe Harbor principles."""

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

    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }
    payload = {
        "model": "sonar-pro",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "stream": True,
        "temperature": 0.2
    }

    res = requests.post(url, headers=headers, json=payload, stream=True, timeout=30)
    if res.status_code != 200:
        raise RuntimeError(f"Perplexity sonar-pro API HTTP {res.status_code}: {res.text}")

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
                choices = event.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "") if isinstance(delta, dict) else str(delta)
                    if content:
                        yield content
                elif "delta" in event:
                    delta_val = event.get("delta")
                    text = delta_val.get("content", "") if isinstance(delta_val, dict) else str(delta_val)
                    if text:
                        yield text
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

def stream_stock_report(ticker: str, language: str = "English (India)", stock_data: dict = None, on_status=None, revision_trigger: str = ""):
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
        notice_p = "\n\n> ⚠️ **Gemini Grounding Unavailable. Rerouting to Perplexity sonar-pro...**\n\n"
        report_accumulator.append(notice_p)
        yield notice_p
        try:
            if on_status:
                on_status("🔄 Failover: Querying Perplexity sonar-pro with search grounding...")
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
            formatted_disc = "; ".join(disc) if isinstance(disc, list) else str(disc)
            note = f"\n\n> ⚠️ **Verification Audit Note:** {formatted_disc}"
            complete_text += note
            yield note
    except Exception:
        pass

    try:
        scrip = stock_data.get("scrip_code", "")
        ann = fetch_latest_bse_announcement(scrip)
        save_report_to_archive(stock_data, complete_text, announcement=ann, revision_trigger=revision_trigger)
    except Exception:
        pass

def generate_stock_report(ticker: str, language: str = "English (India)") -> str:
    chunks = []
    for c in stream_stock_report(ticker, language):
        chunks.append(c)
    return "".join(chunks)




def get_historical_prices(ticker: str, period: str = "6mo"):
    """
    Fetches trailing daily historical prices via yfinance, attempting BSE (.BO)
    first with NSE (.NS) fallback. Computes 50-day Simple Moving Average (50-DMA).
    Auto-resolves 6-digit BSE scrip codes to alphanumeric ticker symbols.
    """
    import os
    import json
    import pandas as pd
    import yfinance as yf

    if not ticker or not isinstance(ticker, str):
        return None

    clean = ticker.strip().upper().replace(".BO", "").replace(".NS", "")

    # Reverse-lookup numeric scrip code to ticker symbol for yfinance
    if clean.isdigit():
        try:
            from bse_master import PRIMARY_BSE_MAP
            rev_map = {str(v).strip(): k for k, v in PRIMARY_BSE_MAP.items()}
            if clean in rev_map:
                clean = rev_map[clean]
        except Exception:
            pass

    df = pd.DataFrame()
    for suffix in [".BO", ".NS"]:
        try:
            sym = f"{clean}{suffix}"
            t = yf.Ticker(sym)
            hist = t.history(period=period)
            if hist is not None and not hist.empty and len(hist) > 5:
                df = hist
                break
        except Exception:
            continue

    if df.empty:
        return None

    df = df.reset_index()
    if "Date" not in df.columns or "Close" not in df.columns:
        return None

    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["Volume"] = pd.to_numeric(df.get("Volume", 0), errors="coerce").fillna(0)
    df = df.dropna(subset=["Close"])

    if len(df) < 5:
        return None

    window = min(50, len(df))
    df["SMA50"] = df["Close"].rolling(window=window, min_periods=5).mean()

    return df[["Date", "Close", "SMA50", "Volume"]]
