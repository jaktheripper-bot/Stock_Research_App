"""Delta evaluation engine: material change gating, self-healing cache checks, and surgical pillar updates."""

import os
import re
import logging
from datetime import datetime, timezone
import streamlit as st
from google import genai

from core.db import save_report_to_archive
from core.analysis.fundamentals import fetch_latest_bse_announcement, compute_deterministic_technical_context
from core.analysis.engine import get_surgical_flash_model

logger = logging.getLogger("equity_research.core.analysis.delta")

def evaluate_material_change(cached: dict, live_fund: dict, scrip_code: str) -> tuple:
    """
    Evaluates whether a cached report requires re-synthesis based on 4 gates:
    1. Poisoned / Incomplete cache self-healing
    2. Exceeded 14-day freshness window
    3. New material BSE filing detected
    4. Price delta >= 5% vs baseline price
    """
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
