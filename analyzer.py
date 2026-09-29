import io
import os
import re
import json
import time
import random
import contextlib
import logging
import requests
from datetime import datetime, timezone, timedelta
import pandas as pd
import streamlit as st
import yfinance as yf
from google import genai
from normalizer import clean_ticker
from db import save_report_to_archive, get_report_by_ticker
from checker import verify_stock_report
from screener import pass_pre_screening_gates
from bsedata.bse import BSE
from bse_master import resolve_bse_scrip_code

logger = logging.getLogger("equity_research.analyzer")

def enrich_fundamentals(ticker: str, data: dict) -> dict:
    """Secondary enrichment: uses yfinance strictly to backfill trailing P/E, Market Cap, and Sector."""
    try:
        clean_sym = clean_ticker(ticker)
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
        logger.warning(f"Background fundamental enrichment notice: {e}")
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
    clean = clean_ticker(ticker).replace(" ", "")
    # Tier 1: Consolidated yfinance
    try:
        symbols = [f"{clean}.NS", f"{clean}.BO"]
        if scrip and str(scrip).isdigit():
            symbols.append(f"{scrip}.BO")
        with contextlib.redirect_stderr(io.StringIO()):
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
                except Exception as err:
                    logger.debug(f"yfinance Ticker probe notice for {s}: {err}")
                    continue
    except Exception as e:
        logger.debug(f"P/E resolution via yfinance failed: {e}")

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
        except Exception as e:
            logger.debug(f"BSE ComHeader direct P/E fetch notice: {e}")
    return "N/A"

@st.cache_data(ttl=300, show_spinner=False)
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
    except Exception as e:
        logger.debug(f"BSE announcement fetch notice for scrip {scrip_code}: {e}")
    return ""

def evaluate_material_change(cached: dict, live_fund: dict, scrip_code: str) -> tuple:
    if not cached:
        return True, "⚡ Fresh Analysis: Initial dossier synthesis", "", "INITIAL"

    # Self-Healing Cache Gate: Invalidate and force re-synthesis if cached text was poisoned by an error or is incomplete
    cached_text = str(cached.get("report_text") or "").strip()
    poison_signatures = [
        "Live Synthesis Failed",
        "Spend cap breached",
        "PERMISSION_DENIED",
        "403 PERMISSION_DENIED",
        "chat_completions_not_available",
        "Verification Audit Note: Missing required section",
    ]
    if (
        not cached_text
        or len(cached_text) < 800
        or any(sig in cached_text for sig in poison_signatures)
        or ("Pillar 1" not in cached_text and "DIAGNOSTIC SUMMARY" not in cached_text)
    ):
        return True, "⚡ Self-Healing Recovery: Cached report contained failed synthesis error or incomplete data", "", "POISONED_CACHE"

    raw_ts = cached.get("raw_timestamp")
    if raw_ts:
        try:
            ts = raw_ts if isinstance(raw_ts, datetime) else datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if (now - ts).total_seconds() / 86400.0 > 14:
                return True, "⚡ Regenerated: Report exceeded 14-day freshness window", "", "EXPIRED"
        except Exception as e:
            logger.debug(f"Timestamp freshness check notice: {e}")

    latest_ann = fetch_latest_bse_announcement(scrip_code)
    cached_ann = cached.get("latest_announcement", "")
    if latest_ann and cached_ann and latest_ann != cached_ann:
        return True, f"⚡ Regenerated: New BSE Filing ({latest_ann[:35]}...)", latest_ann, "NEW_FILING"

    cached_price = cached.get("baseline_price")
    live_price = live_fund.get("current_price") or live_fund.get("currentValue")
    try:
        c_p = float(str(cached_price).replace(",", "").strip())
        l_p = float(str(live_price).replace(",", "").strip())
        if c_p > 0 and (abs(l_p - c_p) / c_p) >= 0.05:
            d = "+" if l_p > c_p else "-"
            shift_pct = (abs(l_p - c_p) / c_p) * 100
            return True, f"⚡ Price shifted {d}{shift_pct:.1f}% vs baseline (₹{l_p:.2f} vs ₹{c_p:.2f})", latest_ann, "PRICE_DELTA"
    except Exception as e:
        logger.debug(f"Price delta computation notice: {e}")
    return False, "🛡️ Verified Cache: No material events detected (Live quote updated)", latest_ann, "NONE"


def fetch_bse_exchange_data(query: str) -> dict:
    scrip = resolve_bse_scrip_code(query)
    if not scrip:
        raise ValueError(f"Could not resolve an official BSE scrip code for '{query}'.")

    b = BSE()
    q = b.getQuote(scrip)
    if not q or "currentValue" not in q:
        raise ValueError(f"BSE exchange did not return quote data for scrip {scrip}.")

    mcap_raw = q.get("marketCapFull") or q.get("marketCapFreeFloat") or "0"
    mcap_clean = str(mcap_raw).replace(" Cr.", "").replace(",", "").strip()
    try:
        mcap_inr = int(float(mcap_clean) * 10_000_000)
    except Exception as e:
        logger.debug(f"BSE MCap parsing note: {e}")
        mcap_inr = 0

    clean_ticker_val = clean_ticker(query)
    sec_id = str(q.get("securityID") or q.get("scrip_id") or "").strip().upper()
    canonical_ticker = sec_id if (sec_id and " " not in sec_id) else (clean_ticker_val if " " not in clean_ticker_val else (sec_id or clean_ticker_val.replace(" ", "")))
    resolved_pe = resolve_pe_with_failsafes(canonical_ticker, scrip)

    return {
        "ticker": canonical_ticker,
        "short_name": q.get("companyName", clean_ticker_val),
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
    clean = clean_ticker(query)
    
    # Try primary BSE ingestion
    try:
        raw_data = fetch_bse_exchange_data(query)
        if raw_data and not raw_data.get("is_fallback", False):
            return raw_data
    except Exception as bse_err:
        logger.warning(f"BSE direct quote failed for {query} ({bse_err}). Attempting yfinance fallback...")

    # Secondary Resilience Fallback via yfinance
    try:
        for sym in [f"{clean}.NS", f"{clean}.BO"]:
            t = yf.Ticker(sym)
            fast = getattr(t, "fast_info", None)
            info = {}
            try:
                info = t.info or {}
            except Exception as err:
                logger.debug(f"yfinance info notice for {sym}: {err}")

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
        logger.error(f"yfinance fallback also failed for {query}: {yf_err}")

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
    fallback = ["gemini-3.8-flash", "gemini-3.7-flash"]
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

def get_surgical_flash_model(client) -> str:
    """Returns the most cost-efficient flash model (e.g., flash-lite if available, else standard flash)."""
    try:
        discovered = get_latest_flash_models(client)
        for m in discovered:
            if "lite" in m:
                return m
        for m in client.models.list():
            model_id = m.name.replace("models/", "") if hasattr(m, "name") else ""
            if "flash-lite" in model_id and "preview" not in model_id:
                return model_id
        if discovered:
            return discovered[0]
    except Exception:
        pass
    return "gemini-3.8-flash"

def stream_genai_with_fallback(client, prompt: str, system_prompt: str, on_status=None, use_grounding: bool = True):
    models_to_try = get_latest_flash_models(client)[:2]
    last_error = None
    for model_name in models_to_try:
        if on_status:
            on_status(f"⚡ Connected to model `{model_name}`...")
        for attempt in range(2):
            try:
                sys_inst = system_prompt
                tools_list = None
                if use_grounding:
                    sys_inst += "\n- Search recent BSE/NSE disclosures and concalls from the past 90-180 days."
                    tools_list = [{"google_search": {}}]

                chat = client.chats.create(
                    model=model_name,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=sys_inst,
                        tools=tools_list,
                        temperature=0.2,
                    )
                )
                if on_status:
                    if use_grounding:
                        on_status("🔍 Grounding against official filings...")
                    else:
                        on_status("⚡ Synthesizing with verified exchange metrics (Fast / Zero Search Fee)...")

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
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }
    payload = {
        "input": prompt,
        "instructions": system_prompt,
        "preset": "fast",
        "stream": True
    }

    res = requests.post(url, headers=headers, json=payload, stream=True, timeout=60)
    if res.status_code != 200:
        raise RuntimeError(f"Perplexity Agent API HTTP {res.status_code}: {res.text}")

    current_event = None
    yielded = False
    for raw_line in res.iter_lines(decode_unicode=False):
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="replace")
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            data_str = line[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                if current_event == "response.output_text.delta" or "delta" in data:
                    delta = data.get("delta")
                    if isinstance(delta, str) and delta:
                        yielded = True
                        yield delta
            except Exception:
                continue

    if not yielded:
        # Non-streaming fallback if SSE streaming yielded no tokens
        r2 = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"input": prompt, "instructions": system_prompt, "preset": "fast"},
            timeout=60
        )
        if r2.status_code == 200:
            d2 = r2.json()
            for item in d2.get("output", []):
                if isinstance(item, dict) and item.get("type") == "message":
                    for c in item.get("content", []):
                        if c.get("type") == "output_text":
                            txt = c.get("text", "")
                            if txt:
                                yield txt

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

def stream_stock_report(ticker: str, language: str = "English (India)", stock_data: dict = None, on_status=None, revision_trigger: str = "", use_grounding: bool = True):
    if stock_data is None:
        stock_data = get_stock_fundamentals(ticker)

    passed, gate_msg = pass_pre_screening_gates(stock_data, stock_data)
    if not passed:
        raise PipelineError(stage="Pre-Screening Gate", message=gate_msg)

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
        for chunk in stream_genai_with_fallback(client, user_prompt, system_prompt, on_status=on_status, use_grounding=use_grounding):
            report_accumulator.append(chunk)
            yield chunk
    except Exception as gemini_err:
        notice_p = "\n\n> ⚠️ **Gemini Grounding Unavailable. Rerouting to Perplexity Agent API...**\n\n"
        report_accumulator.append(notice_p)
        yield notice_p
        try:
            if on_status:
                on_status("🔄 Failover: Querying Perplexity Agent API with search grounding...")
            for chunk in stream_perplexity_fallback(user_prompt, system_prompt):
                report_accumulator.append(chunk)
                yield chunk
        except Exception as p_err:
            gem_err_msg = str(gemini_err)
            is_spend_cap = any(phrase in gem_err_msg for phrase in ["Spend cap breached", "PERMISSION_DENIED", "403", "quota"])
            if is_spend_cap:
                err_msg = (
                    f"\n\n> ❌ **Live Synthesis Failed:** Both primary and failover providers encountered errors.\n"
                    f"> • **Gemini (Primary):** Google Cloud spend cap breached or permission denied.\n"
                    f"> • **Perplexity (Failover):** {p_err}\n"
                )
                report_accumulator.append(err_msg)
                yield err_msg
            else:
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
    passed = False
    try:
        passed, disc = verify_stock_report(stock_data, complete_text)
        if not passed:
            formatted_disc = "; ".join(disc) if isinstance(disc, list) else str(disc)
            note = f"\n\n> ⚠️ **Verification Audit Note:** {formatted_disc}"
            complete_text += note
            yield note
    except Exception:
        passed = False

    # Check for failure indicators
    error_signatures = [
        "Live Synthesis Failed",
        "Spend cap breached",
        "PERMISSION_DENIED",
        "403 PERMISSION_DENIED",
        "chat_completions_not_available",
    ]
    has_error_signature = any(err in complete_text for err in error_signatures)
    is_structurally_valid = len(complete_text.strip()) >= 800 and ("Pillar 1" in complete_text or "DIAGNOSTIC SUMMARY" in complete_text)

    # STRICT INTEGRITY GATE: Never archive failed or poisoned syntheses
    if has_error_signature or not is_structurally_valid:
        logger.warning(
            f"Report synthesis failed or incomplete for {stock_data.get('ticker')}. "
            "Skipping save_report_to_archive to prevent database cache poisoning."
        )
    else:
        try:
            scrip = stock_data.get("scrip_code", "")
            ann = fetch_latest_bse_announcement(scrip)
            save_report_to_archive(stock_data, complete_text, announcement=ann, revision_trigger=revision_trigger)
        except Exception as e:
            logger.error(f"Error archiving report for {stock_data.get('ticker')}: {e}")

def generate_stock_report(ticker: str, language: str = "English (India)", use_grounding: bool = True) -> str:
    chunks = []
    for c in stream_stock_report(ticker, language, use_grounding=use_grounding):
        chunks.append(c)
    return "".join(chunks)


def splice_report_pillars(original_text: str, updated_pillars: dict) -> str:
    """
    Surgically replaces specified pillar sections in an institutional report.
    updated_pillars: e.g. {5: "## Pillar 5: ...", 6: "## Pillar 6: ..."}
    Preserves all other pillars, headings, and formatting exactly.
    """
    if not original_text or not updated_pillars:
        return original_text or ""
    sections = re.split(r"(?m)(?=^#{1,3}\s+)", original_text)
    new_sections = []
    for s in sections:
        matched_pillar = None
        for p_num in updated_pillars:
            if re.search(rf"(?i)\bPillars?\s*{p_num}\b", s):
                matched_pillar = p_num
                break
        if matched_pillar is not None:
            new_sections.append(updated_pillars[matched_pillar].strip() + "\n\n")
        else:
            new_sections.append(s)
    return "".join(new_sections).strip()


def compute_deterministic_technical_context(stock_data: dict, hist_df=None) -> dict:
    """
    Extracts and computes exact mathematical indicators (50-DMA, % from high/low)
    directly in Python to eliminate hallucinations and token waste.
    """
    price = 0.0
    try:
        raw_p = stock_data.get("current_price") or stock_data.get("currentValue") or 0.0
        price = float(str(raw_p).replace(",", "").strip())
    except Exception:
        pass

    high_52 = None
    low_52 = None
    try:
        high_52 = float(str(stock_data.get("52w_high", "")).replace(",", "").strip())
    except Exception:
        pass
    try:
        low_52 = float(str(stock_data.get("52w_low", "")).replace(",", "").strip())
    except Exception:
        pass

    dma_50 = None
    pct_from_dma50 = None
    if hist_df is not None and not getattr(hist_df, "empty", True) and "Close" in hist_df.columns:
        closes = hist_df["Close"].dropna()
        if len(closes) >= 10:
            dma_50 = float(closes.tail(50).mean())
            if dma_50 > 0 and price > 0:
                pct_from_dma50 = ((price - dma_50) / dma_50) * 100

    pct_from_high = ((price - high_52) / high_52 * 100) if (high_52 and price and high_52 > 0) else None
    pct_from_low = ((price - low_52) / low_52 * 100) if (low_52 and price and low_52 > 0) else None

    pe_ratio = stock_data.get("pe_ratio", "N/A")
    mcap = stock_data.get("market_cap", 0)
    mcap_cr = (mcap / 10_000_000) if isinstance(mcap, (int, float)) and mcap > 0 else 0.0

    return {
        "price": price,
        "pe_ratio": pe_ratio,
        "mcap": mcap,
        "mcap_cr": mcap_cr,
        "52w_high": high_52,
        "52w_low": low_52,
        "dma_50": dma_50,
        "pct_from_dma50": pct_from_dma50,
        "pct_from_high": pct_from_high,
        "pct_from_low": pct_from_low,
    }


def execute_surgical_pillar_update(
    ticker: str,
    cached_report: dict,
    stock_data: dict,
    hist_df=None,
    language: str = "English (India)",
    on_status=None
) -> str:
    """
    Surgically updates ONLY Pillar 5 (Valuation) and Pillar 6 (Technicals)
    for a cached report whose stock price shifted >= 5%.

    Credit & Cost Optimization:
      1. ZERO Google Search Grounding: saves $0.035 search fee per invocation.
      2. Deterministic Technical Precomputation: 50-DMA and price bands passed directly.
      3. Minimal Token Burn: ~350-500 output tokens instead of 3,000+ (85%+ token reduction).
      4. Antifragile Fallback: Deterministic Python fallback if LLM spend cap is reached.
    """
    metrics = compute_deterministic_technical_context(stock_data, hist_df)
    short_name = stock_data.get("short_name", ticker)
    price = metrics["price"]
    pe = metrics["pe_ratio"]
    dma = f"₹{metrics['dma_50']:.2f}" if metrics["dma_50"] else "N/A"
    dma_rel = f" ({metrics['pct_from_dma50']:+.1f}% vs 50-DMA)" if metrics["pct_from_dma50"] is not None else ""
    high_str = f"₹{metrics['52w_high']}" if metrics["52w_high"] else "N/A"
    low_str = f"₹{metrics['52w_low']}" if metrics["52w_low"] else "N/A"
    mcap_str = f"₹{metrics['mcap_cr']:,.2f} Cr" if metrics['mcap_cr'] > 0 else "N/A"

    lang_rule = "Write entirely in English (India)." if language == "English (India)" else f"Write in {language}."

    sys_prompt = f"""You are an institutional equity research analyst operating under strict SEBI Safe Harbor guidelines.
{lang_rule}
Your task is to write updated, fact-based evaluations for ONLY Pillar 5 and Pillar 6 for {ticker}.
Pillars 1 to 4 and Pillar 7 remain fundamentally valid and must NOT be reproduced.

CRITICAL RULES:
1. Write at an 8th-grade reading level. Keep sentences short and clear.
2. ABBREVIATION MANDATE: On first mention of any acronym (e.g. P/E [Price-to-Earnings Ratio], 50-DMA [50-Day Simple Moving Average]), expand in brackets.
3. Express metrics strictly in INR and Crores.
4. Strictly NO BUY/HOLD/SELL verdicts, target prices, or portfolio roadmaps under SEBI regulations.

OUTPUT FORMAT:
Return strictly the two markdown sections:
## Pillar 5: Valuation & Margin of Safety
[Valuation analysis based on verified P/E and market cap]

## Pillar 6: Technical & Momentum Overlay
[Technical analysis based on price relative to 50-DMA and 52-week range]"""

    user_prompt = f"""Company: {short_name} ({ticker})
Verified Live Exchange Metrics:
- Current Market Price: ₹{price}
- Trailing P/E Multiple: {pe}
- Market Capitalization: {mcap_str}
- 52-Week Range: High {high_str} | Low {low_str}
- 50-Day Moving Average: {dma}{dma_rel}"""

    p5_text = ""
    p6_text = ""

    # Attempt Gemini Flash with zero grounding fee
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("GEMINI_API_KEY")
            except Exception:
                pass
        if api_key:
            client = genai.Client(api_key=api_key)
            model_name = get_surgical_flash_model(client)
            if on_status:
                on_status(f"⚡ Executing surgical Pillar 5 & 6 refresh via `{model_name}` (Zero Grounding Fee)...")
            chat = client.chats.create(
                model=model_name,
                config=genai.types.GenerateContentConfig(
                    system_instruction=sys_prompt,
                    temperature=0.2,
                )
            )
            resp = chat.send_message(user_prompt)
            gen_text = resp.text or ""
            sections = re.split(r"(?m)(?=^##\s+Pillars?\s*[56])", gen_text)
            for sec in sections:
                if re.search(r"(?i)\bPillars?\s*5\b", sec):
                    p5_text = sec.strip()
                elif re.search(r"(?i)\bPillars?\s*6\b", sec):
                    p6_text = sec.strip()
    except Exception as e:
        logger.warning(f"Gemini surgical generation notice ({e}). Falling back to deterministic Python synthesis.")

    # High-Reliability Deterministic Python Fallback if LLM unavailable
    if not p5_text:
        pe_desc = f"trades at a trailing P/E [Price-to-Earnings Ratio] of {pe}" if pe != "N/A" else "operates with unlisted trailing P/E metrics"
        p5_text = (
            f"## Pillar 5: Valuation & Margin of Safety\n\n"
            f"At the current market price of ₹{price:.2f}, {short_name} {pe_desc} with an exchange market capitalization of {mcap_str}. "
            f"Compared to its 52-week peak of {high_str} and trough of {low_str}, the current multiple reflects recent market adjustments. "
            f"Investors should evaluate current valuation against broader industry peer benchmarks and historical cash-flow yield multiples."
        )

    if not p6_text:
        dma_note = ""
        if metrics["pct_from_dma50"] is not None:
            pos = "above" if metrics["pct_from_dma50"] >= 0 else "below"
            dma_note = f" The equity is currently trading {abs(metrics['pct_from_dma50']):.1f}% {pos} its 50-DMA [50-Day Simple Moving Average] of {dma}."
        p6_text = (
            f"## Pillar 6: Technical & Momentum Overlay\n\n"
            f"The stock exhibits trailing price action at ₹{price:.2f} within a 52-week corridor of {low_str} to {high_str}.{dma_note} "
            f"Short-term volume and moving average trends indicate ongoing price discovery following recent exchange trade cycles."
        )

    updated_dict = {5: p5_text, 6: p6_text}
    original_report_text = cached_report.get("report_text", "")
    spliced_text = splice_report_pillars(original_report_text, updated_dict)

    # Save updated snapshot and record historical revision in database
    try:
        scrip = stock_data.get("scrip_code", "")
        ann = fetch_latest_bse_announcement(scrip)
        save_report_to_archive(
            stock_data,
            spliced_text,
            announcement=ann,
            revision_trigger=f"Surgical Valuation & Technicals Update (Live price ₹{price:.2f})"
        )
    except Exception as err:
        logger.error(f"Error persisting surgical report update: {err}")

    return spliced_text





@st.cache_data(ttl="15m", max_entries=50)
def get_historical_prices(ticker: str, period: str = "6mo"):
    """
    Fetches trailing daily historical prices via yfinance, attempting BSE (.BO)
    first with NSE (.NS) fallback. Computes 50-day Simple Moving Average (50-DMA).
    Auto-resolves 6-digit BSE scrip codes to alphanumeric ticker symbols.
    """
    if not ticker or not isinstance(ticker, str):
        return None

    clean = clean_ticker(ticker)

    # Sanitize multi-word queries with spaces to their canonical security ID
    if " " in clean:
        scrip = resolve_bse_scrip_code(clean)
        if scrip:
            try:
                b = BSE()
                q = b.getQuote(scrip)
                sec_id = str(q.get("securityID") or "").strip().upper()
                if sec_id and " " not in sec_id:
                    clean = sec_id
                else:
                    clean = clean.replace(" ", "")
            except Exception as e:
                logger.debug(f"BSE quote lookup notice for {scrip}: {e}")
                clean = clean.replace(" ", "")
        else:
            clean = clean.replace(" ", "")

    # Reverse-lookup numeric scrip code to ticker symbol for yfinance
    if clean.isdigit():
        try:
            from bse_master import PRIMARY_BSE_MAP
            rev_map = {str(v).strip(): k for k, v in PRIMARY_BSE_MAP.items()}
            if clean in rev_map:
                clean = rev_map[clean]
        except Exception as e:
            logger.debug(f"Reverse lookup notice for scrip {clean}: {e}")

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


def evaluate_company_disparity(fund_a: dict, fund_b: dict) -> dict:
    """
    Evaluates cross-company disparity across the 3 institutional axes defined in docs/Refining Alerts and Comparison Features.md:
    1. Sector / Business Model Disparity (e.g. Banks/NBFC vs SaaS)
    2. Lifecycle / Maturity Disparity (unprofitable/loss-making vs mature profitable)
    3. Scale & Capital Structure Divergence (>= 100x market cap divergence)
    """
    warnings = []
    
    # 1. Sector / Business Model Disparity
    sec_a = str(fund_a.get("sector") or "").strip()
    sec_b = str(fund_b.get("sector") or "").strip()
    generic = {"N/A", "General Industry", "Core Industry", "Diversified / Core Industry", ""}
    sector_mismatch = False
    if sec_a and sec_b and sec_a not in generic and sec_b not in generic and sec_a.lower() != sec_b.lower():
        sector_mismatch = True
        warnings.append(
            f"Sector Disparity ({sec_a} vs. {sec_b}): These companies operate in fundamentally different sectors. "
            "Multiples like EV/EBITDA, gross margins, or P/B cannot be compared 1:1."
        )

    # 2. Lifecycle / Maturity Disparity
    pe_a = str(fund_a.get("pe_ratio", "N/A"))
    pe_b = str(fund_b.get("pe_ratio", "N/A"))
    loss_a = "Loss-Making" in pe_a or "Negative" in pe_a
    loss_b = "Loss-Making" in pe_b or "Negative" in pe_b
    lifecycle_mismatch = False
    if (loss_a and not loss_b and pe_b != "N/A") or (loss_b and not loss_a and pe_a != "N/A"):
        lifecycle_mismatch = True
        warnings.append(
            "Lifecycle Disparity: One of these companies is an early-stage or loss-making asset while the other is a mature, "
            "profitable firm. Growth metrics and valuation multiples are not directly equivalent."
        )

    # 3. Scale / Capital Structure Disparity
    mcap_a = 0.0
    mcap_b = 0.0
    try:
        mcap_a = float(str(fund_a.get("market_cap") or 0).replace(",", "").strip())
        mcap_b = float(str(fund_b.get("market_cap") or 0).replace(",", "").strip())
    except Exception:
        pass
    
    scale_mismatch = False
    if mcap_a > 0 and mcap_b > 0:
        ratio = max(mcap_a, mcap_b) / min(mcap_a, mcap_b)
        if ratio >= 100.0:
            scale_mismatch = True
            warnings.append(
                f"Scale Disparity: Greater than {int(ratio)}x divergence in market capitalization. "
                "Institutional float, liquidity dynamics, and capital structures are not directly comparable."
            )

    return {
        "is_disparate": len(warnings) > 0,
        "warnings": warnings,
        "sector_mismatch": sector_mismatch,
        "lifecycle_mismatch": lifecycle_mismatch,
        "scale_mismatch": scale_mismatch,
        "sec_a": sec_a or "N/A",
        "sec_b": sec_b or "N/A",
    }


def compare_two_companies(ticker_a: str, ticker_b: str, progress_callback=None) -> dict:
    """
    Executes cross-company peer comparison with 3-tier disparity evaluation,
    extracting side-by-side fundamentals, 7-pillar health matrices, and normalized indicators.
    """
    clean_a = clean_ticker(ticker_a)
    clean_b = clean_ticker(ticker_b)
    
    if progress_callback:
        progress_callback(0.20, f"Auditing verified BSE quotes & fundamentals for {clean_a}...")
    fund_a = get_stock_fundamentals(clean_a)

    if progress_callback:
        progress_callback(0.50, f"Auditing verified BSE quotes & fundamentals for {clean_b}...")
    fund_b = get_stock_fundamentals(clean_b)
    
    resolved_a = fund_a.get("ticker", clean_a)
    resolved_b = fund_b.get("ticker", clean_b)
    
    if progress_callback:
        progress_callback(0.70, "Loading verified 7-pillar health dossiers...")
    rep_a = get_report_by_ticker(resolved_a)
    rep_b = get_report_by_ticker(resolved_b)
    
    matrix_a = extract_health_matrix(rep_a.get("report_text", "") if rep_a else "")
    matrix_b = extract_health_matrix(rep_b.get("report_text", "") if rep_b else "")
    
    if progress_callback:
        progress_callback(0.85, "Evaluating 3-tier heuristic disparity (Sector, Lifecycle, Scale)...")
    disparity = evaluate_company_disparity(fund_a, fund_b)

    if progress_callback:
        progress_callback(1.0, "Synthesizing normalized side-by-side comparison matrix...")
    
    return {
        "ticker_a": resolved_a,
        "ticker_b": resolved_b,
        "fund_a": fund_a,
        "fund_b": fund_b,
        "rep_a": rep_a,
        "rep_b": rep_b,
        "matrix_a": matrix_a,
        "matrix_b": matrix_b,
        "disparity": disparity,
    }

