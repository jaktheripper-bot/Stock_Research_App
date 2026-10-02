"""AI research synthesis engine: model discovery, Gemini Flash cascade, Perplexity failover, and grounding stream."""

import os
import re
import json
import time
import random
import logging
import requests
from google import genai

from core.db import save_report_to_archive
from core.analysis.exceptions import PipelineError
from core.analysis.parser import format_citations_section
from core.analysis.fundamentals import get_stock_fundamentals, fetch_latest_bse_announcement
from screener import pass_pre_screening_gates
from checker import verify_stock_report

logger = logging.getLogger("equity_research.core.analysis.engine")

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

def stream_genai_with_fallback(client, prompt: str, system_prompt: str, on_status=None, use_grounding: bool = True, collected_citations: list = None):
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
                            # Visual Source Attribution: Extract grounding metadata chunks
                            if collected_citations is not None:
                                gm = getattr(cand, "grounding_metadata", None)
                                if gm:
                                    gc = getattr(gm, "grounding_chunks", None)
                                    if gc:
                                        for c in gc:
                                            w = getattr(c, "web", None)
                                            if w:
                                                u = (getattr(w, "uri", None) or "").strip()
                                                t = (getattr(w, "title", None) or "").strip()
                                                if u and not any(existing.get("uri") == u for existing in collected_citations):
                                                    stype = "Verified Web Grounding"
                                                    low_u = u.lower()
                                                    low_t = t.lower()
                                                    if "bseindia.com" in low_u or "bse" in low_t:
                                                        stype = "BSE Regulatory Filing"
                                                    elif "nseindia.com" in low_u or "nse" in low_t:
                                                        stype = "NSE Exchange Filing"
                                                    elif "mca.gov.in" in low_u:
                                                        stype = "MCA Registry Record"
                                                    elif "sebi.gov.in" in low_u:
                                                        stype = "SEBI Statutory Disclosure"
                                                    elif any(k in low_u for k in ["investor", "annualreport", "concall", "transcript"]):
                                                        stype = "Corporate Investor Relations"
                                                    collected_citations.append({
                                                        "title": t or "Exchange / Web Grounding Source",
                                                        "uri": u,
                                                        "source_type": stype
                                                    })
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

def stream_perplexity_fallback(prompt: str, system_prompt: str, collected_citations: list = None):
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
                if collected_citations is not None and "citations" in data:
                    for c_url in data.get("citations", []):
                        if isinstance(c_url, str) and c_url.startswith("http") and not any(e.get("uri") == c_url for e in collected_citations):
                            collected_citations.append({
                                "title": c_url.split("//")[-1].split("/")[0],
                                "uri": c_url,
                                "source_type": "Perplexity Search Grounding"
                            })
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
            if collected_citations is not None and "citations" in d2:
                for c_url in d2.get("citations", []):
                    if isinstance(c_url, str) and c_url.startswith("http") and not any(e.get("uri") == c_url for e in collected_citations):
                        collected_citations.append({
                            "title": c_url.split("//")[-1].split("/")[0],
                            "uri": c_url,
                            "source_type": "Perplexity Search Grounding"
                        })

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

    collected_citations = []
    scrip = str(stock_data.get("scrip_code") or "").strip()
    clean_sym = stock_data.get("ticker", ticker)
    if scrip and scrip.isdigit():
        collected_citations.append({
            "title": f"BSE Corporate Announcements & Disclosures ({clean_sym})",
            "uri": f"https://www.bseindia.com/stock-share-price/-/{scrip}/corporate-announcements/",
            "source_type": "BSE Official Regulatory Filing"
        })

    report_accumulator = []
    try:
        for chunk in stream_genai_with_fallback(client, user_prompt, system_prompt, on_status=on_status, use_grounding=use_grounding, collected_citations=collected_citations):
            report_accumulator.append(chunk)
            yield chunk
    except Exception as gemini_err:
        notice_p = "\n\n> ⚠️ **Gemini Grounding Unavailable. Rerouting to Perplexity Agent API...**\n\n"
        report_accumulator.append(notice_p)
        yield notice_p
        try:
            if on_status:
                on_status("🔄 Failover: Querying Perplexity Agent API with search grounding...")
            for chunk in stream_perplexity_fallback(user_prompt, system_prompt, collected_citations=collected_citations):
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

    current_text = "".join(report_accumulator)
    # Append structured source citations block if not already present and synthesis was structurally productive
    if collected_citations and len(current_text.strip()) >= 500 and "Verified Regulatory Sources" not in current_text:
        citations_block = format_citations_section(collected_citations, stock_data)
        if citations_block:
            report_accumulator.append(citations_block)
            yield citations_block

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
            save_report_to_archive(stock_data, complete_text, announcement=ann, revision_trigger=revision_trigger, citations=collected_citations)
        except Exception as e:
            logger.error(f"Error archiving report for {stock_data.get('ticker')}: {e}")

def generate_stock_report(ticker: str, language: str = "English (India)", use_grounding: bool = True) -> str:
    chunks = []
    for c in stream_stock_report(ticker, language, use_grounding=use_grounding):
        chunks.append(c)
    return "".join(chunks)
