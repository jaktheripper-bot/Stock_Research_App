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
from core.analysis.epistemic_schema import EPISTEMIC_PROMPT_DIRECTIVE
from core.brand.moatnomics_house import get_system_prompt_context
from screener import pass_pre_screening_gates
from checker import verify_stock_report

logger = logging.getLogger("equity_research.core.analysis.dossier_report_synthesis")

def get_system_prompt(ticker: str, language: str) -> str:
    lang_rule = (
        "The report must be entirely in English (India) using British/Indian spelling "
        "(e.g., capitalisation, specialisation, prioritise, analyse, labour, behaviour, defence, signalling, colour, programme, centre)."
        if language == "English (India)"
        else f"The report must be fully translated into {language} without omitting technical rigor."
    )
    base_prompt = f"""You are a senior fundamental equity research analyst. Write a rigorous, mechanism-level 7-Pillar research dossier for {ticker}.
{lang_rule}

### Health Matrix
- Macro: [Stable | Headwinds | Neutral]
- Moat: [Wide | Moderate | Narrow]
- Governance: [Clean | Caution | High Risk]
- Diagnostic: [Temporary | Structural | Neutral | N/A]
- Valuation: [Undervalued | Fair | Stretched | Loss-Making]
- Balance Sheet: [Debt-Free | Moderate Debt | High Debt]
- Capital Allocation: [Disciplined | Moderate | Strained]

CRITICAL ANALYTICAL & LINGUISTIC RULES:
1. Write clear, approachable prose (8th-to-10th grade readability) without sacrificing analytical depth.
2. ANALYSE CAUSES, NOT MERE OBSERVATIONS: Never merely restate headline ratios. For every pillar, explain the underlying business mechanism—unit economics, gross/operating margin drivers, pricing power vs raw-material pass-through, working-capital cash conversion (CFO vs EBITDA, receivable/inventory cycles), ROCE vs cost of capital (WACC) spread, and named competitive threats.
3. FINANCIAL UNIT & ACRONYM HYGIENE: Write standard financial denominations and ratios (INR, Cr, FY, YoY, QoQ, P/E, ROCE, ROE, EBITDA, 50-DMA) cleanly without robotic bracket expansions like [Indian Rupee] or [Crore]. Do NOT expand abbreviations inside `### Health Matrix` or Markdown tables.
4. Express all Indian corporate metrics in Crores (Cr) and Indian Rupees (INR), grounded strictly in the provided exchange data and verified regulatory filings.

# DIAGNOSTIC SUMMARY & KEY TAKEAWAYS
**Summary:** One concise, causal sentence explaining what drives the company's current operational standing and capital efficiency.

---
## Pillar 1: Macro-Economic, Geopolitical & Environmental Overlays
## Pillar 2: Industry Dynamics & Competitive Positioning
Where statutory Ind AS 108 / BSE Regulation 33 multi-segment revenue splits are disclosed, include a concise Markdown table (`| Operating Segment | Revenue Share (%) | Key Unit-Economic Driver |`); for capital-goods, defence, EPC, EMS, or IT engineering entities with disclosed backlog, state the verified order book in `INR ... Cr`. Skip segment tables cleanly for single-segment enterprises rather than estimating splits.
## Pillar 3: Promoter Quality & Fundamental Health
## Pillar 4: The "Structural vs. Temporary" Drop Diagnostic
## Pillar 5: Valuation & Margin of Safety
## Pillar 6: Technical & Momentum Overlay
## Pillar 7: ESG Impact Scorecard
Tabulate the ESG analysis strictly using the following Markdown table format:
| Parameter | Score (0-100) | Evaluation & Key Drivers |
| :--- | :--- | :--- |
| **Environmental** | [Score] | [Company-specific operational & resource drivers] |
| **Social** | [Score] | [Workforce, safety, and supply-chain drivers] |
| **Governance** | [Score] | [Board independence, related-party & audit quality] |

CRITICAL COMPLIANCE DIRECTIVE: Strictly avoid Buy/Sell/Hold verdicts, target prices, trade execution signals, portfolio allocation advice, or personalised investment recommendations. Conclude strictly after Pillar 7. Deliver deep causal business and accounting analysis while remaining non-advisory under SEBI Safe Harbor principles."""

    brand_context = get_system_prompt_context(content_type="research_dossiers").strip()
    return base_prompt + "\n\n" + brand_context + "\n\n" + EPISTEMIC_PROMPT_DIRECTIVE

_DISCOVERED_MODELS_CACHE = {"models": [], "timestamp": 0}
_MAX_DISCOVERED_MODELS_CACHE_SIZE = 10

def get_latest_flash_models(client) -> list:
    now = time.time()
    is_vertex = getattr(client, "vertexai", False) is True
    if is_vertex:
        return ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash"]
    if _DISCOVERED_MODELS_CACHE.get("models") and (now - _DISCOVERED_MODELS_CACHE.get("timestamp", 0)) < 86400:
        return _DISCOVERED_MODELS_CACHE["models"]
    fallback = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash"]
    try:
        discovered = []
        for m in client.models.list():
            model_id = m.name.split("/")[-1] if hasattr(m, "name") and m.name else ""
            if "gemini" in model_id and "flash" in model_id and "preview" not in model_id:
                if not any(k in model_id for k in ["image", "tts", "audio", "embed"]):
                    match = re.search(r"gemini-(\d+(?:\.\d+)?)", model_id)
                    if match:
                        discovered.append((float(match.group(1)), model_id))
        if discovered:
            discovered.sort(key=lambda x: x[0], reverse=True)
            ordered = [x[1] for x in discovered][:_MAX_DISCOVERED_MODELS_CACHE_SIZE]
            _DISCOVERED_MODELS_CACHE.clear()
            _DISCOVERED_MODELS_CACHE["models"] = ordered
            _DISCOVERED_MODELS_CACHE["timestamp"] = now
            return ordered
    except Exception as disc_err:
        logger.debug("Model discovery notice: %s", disc_err)
    return fallback

def get_light_flash_model(client) -> str:
    """Returns the most cost-efficient flash model (e.g., flash-lite if available, else standard flash)."""
    if getattr(client, "vertexai", False) is True:
        return "gemini-3.5-flash-lite"
    try:
        discovered = get_latest_flash_models(client)
        for m in discovered:
            if "lite" in m:
                return m
        for m in client.models.list():
            model_id = m.name.split("/")[-1] if hasattr(m, "name") and m.name else ""
            if "flash-lite" in model_id and "preview" not in model_id:
                return model_id
        if discovered:
            return discovered[0]
    except Exception as surg_err:
        logger.debug("Light model selection notice: %s", surg_err)
    return "gemini-3.5-flash-lite"

def stream_genai_with_fallback(client, prompt: str, system_prompt: str, on_status=None, use_grounding: bool = True, collected_citations: list = None):
    models_to_try = get_latest_flash_models(client)[:2]
    last_error = None
    for model_name in models_to_try:
        if on_status:
            on_status("Initializing institutional synthesis engine...")
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
                        on_status("Grounding against official filings...")
                    else:
                        on_status("Generating with verified exchange metrics (Fast / Zero Search Fee)...")

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
                        except Exception as text_err:
                            logger.debug("Chunk text extraction notice: %s", text_err)
                    if extracted_text:
                        yield extracted_text
                return
            except Exception as e:
                logger.warning(f"Gemini grounded search attempt notice: {e}")
                last_error = e
                err_str = str(e)
                if any(code in err_str for code in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]):
                    time.sleep(1.0 + random.uniform(0.2, 1.0))
                    continue
                break
    raise ValueError(f"Gemini grounded search exhausted: {last_error}")

def stream_perplexity_fallback(prompt: str, system_prompt: str, collected_citations: list = None):
    from core.config import get_secret
    api_key = get_secret("PERPLEXITY_API_KEY")
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

    yielded = False
    res = requests.post(url, headers=headers, json=payload, stream=True, timeout=60)
    if res.status_code == 200:
        current_event = None
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
                                    "source_type": "Verified Web Grounding"
                                })
                except Exception as stream_err:
                    logger.debug(f"Perplexity streaming parse notice: {stream_err}")
                    continue

    if not yielded:
        # Non-streaming fallback via /v1/responses if SSE streaming yielded no tokens
        try:
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
                                    yielded = True
                                    yield txt
                if collected_citations is not None and "citations" in d2:
                    for c_url in d2.get("citations", []):
                        if isinstance(c_url, str) and c_url.startswith("http") and not any(e.get("uri") == c_url for e in collected_citations):
                            collected_citations.append({
                                "title": c_url.split("//")[-1].split("/")[0],
                                "uri": c_url,
                                "source_type": "Verified Web Grounding"
                            })
        except Exception as r2_err:
            logger.debug(f"Perplexity /v1/responses fallback notice: {r2_err}")

    if not yielded:
        # Standard Perplexity Sonar /chat/completions endpoint fallback
        sonar_url = "https://api.perplexity.ai/chat/completions"
        r3 = requests.post(
            sonar_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            },
            timeout=60,
        )
        if r3.status_code != 200:
            raise RuntimeError(f"Perplexity Sonar API HTTP {r3.status_code}: {r3.text}")
        d3 = r3.json()
        choices = d3.get("choices") or []
        if choices:
            msg_content = (choices[0].get("message") or {}).get("content") or ""
            if msg_content:
                yielded = True
                yield msg_content
        if collected_citations is not None and "citations" in d3:
            for c_url in d3.get("citations", []):
                if isinstance(c_url, str) and c_url.startswith("http") and not any(e.get("uri") == c_url for e in collected_citations):
                    collected_citations.append({
                        "title": c_url.split("//")[-1].split("/")[0],
                        "uri": c_url,
                        "source_type": "Verified Web Grounding",
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

    from core.config import get_secret
    api_key = get_secret("GEMINI_API_KEY")
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
        logger.warning(f"Primary streaming synthesis failed: {gemini_err}")
        try:
            if on_status:
                on_status("Switching to secondary search grounding channel...")
            for chunk in stream_perplexity_fallback(user_prompt, system_prompt, collected_citations=collected_citations):
                report_accumulator.append(chunk)
                yield chunk
        except Exception as p_err:
            logger.warning(f"Secondary fallback synthesis failed: {p_err}")
            gem_err_msg = str(gemini_err)
            is_spend_cap = any(phrase in gem_err_msg for phrase in ["Spend cap breached", "PERMISSION_DENIED", "403", "quota"])
            if is_spend_cap:
                err_msg = (
                    "\n\n> **Live Synthesis Failed:** Grounded synthesis channels are temporarily unavailable. "
                    "Please retry shortly.\n"
                )
                report_accumulator.append(err_msg)
                yield err_msg
            else:
                notice_u = (
                    "\n\n> **Notice: Live Web Grounding Offline.**\n"
                    "> Generating thesis from core parametric intelligence.\n"
                    "> *Note:* Exchange metrics are verified, but recent disclosures may be omitted.\n\n"
                )
                report_accumulator.append(notice_u)
                yield notice_u
                try:
                    for chunk in stream_gemini_ungrounded_bypass(client, user_prompt, system_prompt):
                        report_accumulator.append(chunk)
                        yield chunk
                except Exception as final_err:
                    logger.error(f"Ungrounded synthesis fallback failed: {final_err}")
                    err_msg = "\n\n> **Live Synthesis Failed:** Unable to complete research synthesis at this time. Please retry shortly."
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
    try:
        from core.analysis.language_filter import enforce_indian_english
        complete_text = enforce_indian_english(complete_text)
    except Exception as lang_err:
        logger.debug("Language filter normalization notice in stream_stock_report: %s", lang_err)

    passed = False
    try:
        passed, disc = verify_stock_report(stock_data, complete_text)
        if not passed:
            formatted_disc = "; ".join(disc) if isinstance(disc, list) else str(disc)
            note = f"\n\n> **Verification Audit Note:** {formatted_disc}"
            complete_text += note
            yield note
    except Exception as verif_err:
        logger.warning(f"Report verification audit notice: {verif_err}")
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
    from core.billing.qos_governor import (
        single_flight_ticker_lock,
        is_live_generation_allowed,
        record_live_generation,
    )
    from core.db.reports import get_report_by_ticker

    clean_ticker = (ticker or "UNKNOWN").strip().upper()
    with single_flight_ticker_lock(clean_ticker):
        # Coalescing check: if a concurrent synthesis for this ticker just completed,
        # return the freshly cached report immediately to prevent duplicate LLM spend.
        cached = get_report_by_ticker(clean_ticker)
        if cached and cached.get("report_text"):
            cached_text = cached.get("report_text", "")
            if len(cached_text.strip()) >= 500 and "Live Synthesis Failed" not in cached_text:
                # Denial-of-Wallet Shield: If live generation velocity cap is hit, or coalesced, serve cached data
                if not is_live_generation_allowed():
                    logger.warning(f"Live generation velocity cap hit. Serving existing cached report for {clean_ticker}.")
                    return cached_text
                logger.info(f"Single-flight coalescer: Reusing freshly compiled cached report for {clean_ticker}")
                return cached_text

        # If live generation cap is hit but we have any cached text, serve it
        if cached and cached.get("report_text") and not is_live_generation_allowed():
            logger.warning(f"Live generation velocity limit reached. Serving cached historical report for {clean_ticker}.")
            return cached.get("report_text", "")

        chunks = []
        for c in stream_stock_report(clean_ticker, language, use_grounding=use_grounding):
            chunks.append(c)
        full_text = "".join(chunks)
        try:
            from core.analysis.language_filter import enforce_indian_english
            full_text = enforce_indian_english(full_text)
        except Exception as lang_err:
            logger.debug("Language filter normalization notice in generate_stock_report: %s", lang_err)
        if len(full_text.strip()) >= 800 and "Live Synthesis Failed" not in full_text:
            record_live_generation()
        return full_text


def synthesize_batch_stock_reports(
    items: list,
    language: str = "English (India)",
    use_grounding: bool = True,
    poll_timeout_seconds: int = 120,
    poll_interval_seconds: int = 5,
    edition_label: str = "daily-ingestion",
) -> dict:
    """
    Submits a cohort of stock synthesis requests via the Gemini Batch API (client.batches.create)
    at a 50% cost discount. Polls for inline batch completion up to poll_timeout_seconds, and
    seamlessly falls back to Gemini Flex tier (service_tier='flex', also 50% discount) for any
    items still pending so the 08:30 AM Morning Discovery run finishes reliably at half cost.

    Args:
        items: List of dicts, each containing {"ticker": str, "stock_data": dict}
    Returns:
        Dict mapping uppercase ticker -> {"report_text": str, "citations": list, "tier": str, "batch_job_name": str}
    """
    from core.config import get_secret
    api_key = get_secret("GEMINI_API_KEY")
    if not api_key or len(api_key.strip()) <= 10 or not items:
        return {}

    client = genai.Client(api_key=api_key)
    model_name = get_latest_flash_models(client)[0]

    valid_items = []
    inline_requests = []
    for entry in items:
        ticker = (entry.get("ticker") or "").strip().upper()
        stock_data = entry.get("stock_data") or {}
        if not ticker:
            continue
        passed, _ = pass_pre_screening_gates(stock_data, stock_data)
        if not passed:
            continue
        sys_inst = get_system_prompt(ticker, language)
        req_cfg = {
            "system_instruction": {"parts": [{"text": sys_inst}]},
            "temperature": 0.2,
        }
        if use_grounding:
            req_cfg["system_instruction"]["parts"][0]["text"] += (
                "\n- Search recent BSE/NSE disclosures and concalls from the past 90-180 days."
            )
            req_cfg["tools"] = [{"google_search": {}}]

        user_prompt = (
            f"Generate research report for: {stock_data.get('short_name') or ticker} ({ticker})\n"
            f"Data: {stock_data}"
        )
        inline_requests.append({
            "contents": [{
                "parts": [{"text": user_prompt}],
                "role": "user",
            }],
            "config": req_cfg,
        })
        valid_items.append((ticker, stock_data, user_prompt, sys_inst))

    if not valid_items:
        return {}

    results: dict = {}
    batch_job_name = ""
    is_vertex = getattr(client, "vertexai", False) is True

    # 1. Submit cohort via Gemini Batch API (AI Studio inline batch; Vertex AI requires GCS URIs so routes directly to Step 2)
    if not is_vertex:
        try:
            batch_job = client.batches.create(
                model=model_name,
                src=inline_requests,
                config={"display_name": f"moatnomics-{edition_label}"},
            )
            batch_job_name = getattr(batch_job, "name", "") or ""
            logger.info(
                "Submitted Gemini Batch API job '%s' for %d stocks (model=%s)",
                batch_job_name,
                len(valid_items),
                model_name,
            )

            deadline = time.monotonic() + max(0, poll_timeout_seconds)
            while batch_job_name:
                state_obj = getattr(batch_job, "state", None)
                state_name = getattr(state_obj, "name", None) or str(state_obj or "")
                if state_name == "JOB_STATE_SUCCEEDED":
                    dest = getattr(batch_job, "dest", None)
                    inlined = getattr(dest, "inlined_responses", None) or []
                    for idx, inline_resp in enumerate(inlined):
                        if idx >= len(valid_items):
                            break
                        t_sym, s_data, _, _ = valid_items[idx]
                        resp_obj = getattr(inline_resp, "response", None)
                        txt = getattr(resp_obj, "text", None) if resp_obj else None
                        if txt and len(str(txt).strip()) >= 500:
                            clean_txt = str(txt).strip()
                            try:
                                from core.analysis.language_filter import enforce_indian_english
                                clean_txt = enforce_indian_english(clean_txt)
                            except Exception as lang_err:
                                logger.debug("Language filter normalization notice in batch inline: %s", lang_err)
                            scrip = str(s_data.get("scrip_code") or "").strip()
                            cites = []
                            if scrip and scrip.isdigit():
                                cites.append({
                                    "title": f"BSE Corporate Announcements & Disclosures ({t_sym})",
                                    "uri": f"https://www.bseindia.com/stock-share-price/-/{scrip}/corporate-announcements/",
                                    "source_type": "BSE Official Regulatory Filing",
                                })
                            results[t_sym] = {
                                "report_text": clean_txt,
                                "citations": cites,
                                "tier": "GEMINI_BATCH_API_50PCT_DISCOUNT",
                                "batch_job_name": batch_job_name,
                            }
                    break
                if state_name in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"):
                    logger.warning("Gemini Batch job '%s' ended with state %s", batch_job_name, state_name)
                    break
                if time.monotonic() >= deadline:
                    logger.info(
                        "Gemini Batch job '%s' still %s after %ds poll window; completing remaining via Flex 50%% tier.",
                        batch_job_name,
                        state_name,
                        poll_timeout_seconds,
                    )
                    break
                time.sleep(max(1, poll_interval_seconds))
                batch_job = client.batches.get(name=batch_job_name)
        except Exception as batch_err:
            logger.warning("Gemini Batch API submission/polling notice: %s. Falling back to Flex 50%% tier.", batch_err)

    # 2. Complete remaining stocks via Vertex AI Postpay Grounded or AI Studio Flex Inference
    for t_sym, s_data, u_prompt, s_inst in valid_items:
        if t_sym in results:
            continue
        try:
            tools_list = [{"google_search": {}}] if use_grounding else None
            sys_full = (
                s_inst + "\n- Search recent BSE/NSE disclosures and concalls from the past 90-180 days."
                if use_grounding
                else s_inst
            )
            cfg_kwargs = {
                "system_instruction": sys_full,
                "tools": tools_list,
                "temperature": 0.2,
            }
            if not is_vertex:
                cfg_kwargs["service_tier"] = "flex"
            resp = client.models.generate_content(
                model=model_name,
                contents=u_prompt,
                config=genai.types.GenerateContentConfig(**cfg_kwargs),
            )
            txt = getattr(resp, "text", None) or ""
            if len(txt.strip()) >= 500:
                clean_flex_txt = txt.strip()
                try:
                    from core.analysis.language_filter import enforce_indian_english
                    clean_flex_txt = enforce_indian_english(clean_flex_txt)
                except Exception as lang_err:
                    logger.debug("Language filter normalization notice in batch flex: %s", lang_err)
                scrip = str(s_data.get("scrip_code") or "").strip()
                cites = []
                if scrip and scrip.isdigit():
                    cites.append({
                        "title": f"BSE Corporate Announcements & Disclosures ({t_sym})",
                        "uri": f"https://www.bseindia.com/stock-share-price/-/{scrip}/corporate-announcements/",
                        "source_type": "BSE Official Regulatory Filing",
                    })
                results[t_sym] = {
                    "report_text": clean_flex_txt,
                    "citations": cites,
                    "tier": "VERTEX_AI_POSTPAY_GROUNDED" if is_vertex else "GEMINI_FLEX_50PCT_DISCOUNT",
                    "batch_job_name": batch_job_name,
                }
        except Exception as flex_err:
            logger.debug("Gemini Flex tier notice for %s: %s", t_sym, flex_err)

    return results


