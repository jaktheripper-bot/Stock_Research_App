"""Interactive Institutional Investor Copilot powered by Google Antigravity SDK.

Configured with `AgentBehavior.INTERACTIVE`:
- Answers deep structural research questions about any stock or fund
- Incorporates the Pre-Mortem Inversion Engine to counter behavioral biases
- Enforces strict SEBI Safe Harbor non-advisory guardrails
- Records all conversational turns and tool traces into `agent_conversations`
"""

import json
import logging
import asyncio
from typing import Dict, Any, List, Optional

try:
    from google.antigravity import types
    ANTIGRAVITY_AVAILABLE = True
except ImportError:
    ANTIGRAVITY_AVAILABLE = False

from core.agents.config import (
    SEBI_SAFE_HARBOR_DIRECTIVE,
    get_tier_budget_config
)
from core.agents.tools_base import (
    tool_get_equity_fundamentals,
    tool_get_recent_bse_disclosures,
    tool_calculate_reverse_dcf
)
from core.db.agent_sessions import (
    create_or_get_agent_conversation,
    append_conversation_turn,
    get_conversation_turns
)
from core.config import get_secret

logger = logging.getLogger("equity_research.core.agents.copilot")


# Forbidden retail advisory terms to intercept
FORBIDDEN_QUERY_PATTERNS = [
    "should i buy", "should i sell", "is this a buy", "target price",
    "will it double", "price prediction", "multibagger", "tip",
    "strong buy", "strong sell", "buy rating", "sell rating",
    "buy or sell", "investment recommendation"
]


def check_non_advisory_compliance(message: str) -> Optional[str]:
    """Intercepts retail advisory queries and returns mandatory regulatory deflection."""
    lowered = (message or "").lower()
    for pat in FORBIDDEN_QUERY_PATTERNS:
        if pat in lowered:
            return (
                "**SEBI Regulatory Non-Advisory Notice:**\n\n"
                "Under SEBI Research Analyst Regulations 2014 Section 2(u), this research copilot operates "
                "strictly as a software diagnostic utility and is prohibited from providing personalized investment advice, "
                "price targets, or Buy/Sell/Hold verdicts.\n\n"
                "I can, however, provide an objective **Pre-Mortem Inversion Analysis** or break down the company's "
                "Margin of Safety, Balance Sheet Solvency, and Reverse DCF implied growth rates. Which diagnostic area would you like to explore?"
            )
    return None


async def process_copilot_turn(
    conversation_id: str,
    user_message: str,
    ticker: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Processes a user dialogue turn with conversational memory and tools."""
    # 1. Ensure conversation exists in DB
    create_or_get_agent_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
        agent_type="equity_copilot",
        context_ticker=ticker
    )

    # 2. Record incoming user turn
    append_conversation_turn(conversation_id, "user", user_message)

    # 3. Fast regulatory compliance filter
    deflection = check_non_advisory_compliance(user_message)
    if deflection:
        append_conversation_turn(conversation_id, "agent", deflection)
        return {
            "conversation_id": conversation_id,
            "response": deflection,
            "status": "REGULATORY_DEFLECTED"
        }

    # 4. Context Grounding with Multi-Asset Dispatch
    context_data = {}
    clean_ticker = (ticker or "").strip().upper()

    if clean_ticker:
        # Check A: Mutual Fund Scheme
        from core.db.mutual_funds import get_mutual_fund_scheme, get_fund_forensic_dossier
        scheme = get_mutual_fund_scheme(clean_ticker)
        if scheme:
            dossier = get_fund_forensic_dossier(clean_ticker) or {}
            context_data = {
                "asset_class": "MUTUAL_FUND",
                "scheme_code": clean_ticker,
                "scheme_name": scheme.get("scheme_name"),
                "category": scheme.get("category"),
                "aum_cr": scheme.get("aum_cr"),
                "composite_health_score": dossier.get("composite_health_score", 70.0),
                "weighted_moat_score": dossier.get("weighted_moat_score", 65.0),
                "accounting_risk_index": dossier.get("accounting_risk_index", 15.0),
                "margin_of_safety_pct": dossier.get("margin_of_safety_pct", 0.0),
                "active_share_pct": dossier.get("active_share_pct", 75.0),
                "top_risky_holdings": dossier.get("top_risky_holdings", []),
                "top_quality_holdings": dossier.get("top_quality_holdings", [])
            }
        else:
            # Check B: Corporate Debt / SDI Security
            from core.db.debt import get_debt_security_by_isin, get_active_debt_securities
            from core.analysis.debt_engine import evaluate_5_pillar_credit_posture
            sec = None
            if clean_ticker.startswith("IN") or len(clean_ticker) == 12:
                sec = get_debt_security_by_isin(clean_ticker)
            if not sec:
                for s in get_active_debt_securities():
                    if s.get("ticker") == clean_ticker or s.get("isin") == clean_ticker:
                        sec = s
                        break
            if sec:
                posture = evaluate_5_pillar_credit_posture(sec)
                radar = posture.get("credit_contagion_radar", {})
                context_data = {
                    "asset_class": "CORPORATE_DEBT",
                    "isin": sec.get("isin"),
                    "ticker": sec.get("ticker"),
                    "instrument_name": sec.get("instrument_name"),
                    "credit_rating": sec.get("credit_rating"),
                    "ytm_pct": posture.get("ytm_pct"),
                    "coupon_rate_pct": posture.get("coupon_rate_pct"),
                    "macaulay_duration_years": posture.get("macaulay_duration_years"),
                    "seniority_tier": posture.get("seniority_tier"),
                    "credit_score": posture.get("composite_score"),
                    "posture_badge": posture.get("posture_badge"),
                    "contagion_radar_status": radar.get("radar_status"),
                    "contagion_risk_level": radar.get("risk_level"),
                    "radar_summary": radar.get("radar_summary")
                }
            else:
                # Check C: Fundamental Equity
                try:
                    fund_raw = await asyncio.to_thread(tool_get_equity_fundamentals, clean_ticker)
                    dcf_raw = await asyncio.to_thread(tool_calculate_reverse_dcf, clean_ticker)
                    context_data = {
                        "asset_class": "EQUITY",
                        "ticker": clean_ticker,
                        "fundamentals": json.loads(fund_raw),
                        "reverse_dcf": json.loads(dcf_raw)
                    }
                except Exception as e:
                    logger.warning(f"Error grounding context for {clean_ticker}: {e}")

    # 5. Cognitive AI Response Synthesis
    history = get_conversation_turns(conversation_id, limit=6)
    history_str = "\n".join([f"{t['sender_role'].upper()}: {t['content']}" for t in history[:-1]])

    from google.genai import Client
    api_key = get_secret("GEMINI_API_KEY")

    if not api_key:
        asset_cls = context_data.get("asset_class", "EQUITY")
        if asset_cls == "MUTUAL_FUND":
            fallback_msg = (
                f"**Forensic Look-Through Summary for {context_data.get('scheme_name', clean_ticker)}:**\n\n"
                f"- Composite Health Score: {context_data.get('composite_health_score', 'N/A')}/100\n"
                f"- Weighted Moat Score: {context_data.get('weighted_moat_score', 'N/A')}/100\n"
                f"- Accounting Risk Index: {context_data.get('accounting_risk_index', 'N/A')}%\n"
                f"- Margin of Safety: {context_data.get('margin_of_safety_pct', 'N/A')}%\n"
                f"- Active Share: {context_data.get('active_share_pct', 'N/A')}%\n\n"
                "What specific constituent holding or style drift area would you like to investigate?"
            )
        elif asset_cls == "CORPORATE_DEBT":
            fallback_msg = (
                f"**Credit & Solvency Summary for {context_data.get('instrument_name', clean_ticker)}:**\n\n"
                f"- Credit Rating: {context_data.get('credit_rating', 'N/A')}\n"
                f"- YTM: {context_data.get('ytm_pct', 'N/A')}%\n"
                f"- Duration: {context_data.get('macaulay_duration_years', 'N/A')} yrs\n"
                f"- Seniority: {context_data.get('seniority_tier', 'N/A')}\n"
                f"- Credit Contagion Radar: {context_data.get('contagion_radar_status', 'N/A')} ({context_data.get('contagion_risk_level', 'N/A')})\n\n"
                f"> {context_data.get('radar_summary', '')}\n\n"
                "What specific solvency or capital hierarchy pillar would you like to drill into?"
            )
        else:
            fallback_msg = (
                f"**Diagnostic Summary for {clean_ticker or 'Security'}:**\n\n"
                f"- P/E Ratio: {context_data.get('fundamentals', {}).get('pe_ratio', 'N/A')}\n"
                f"- ROCE: {context_data.get('fundamentals', {}).get('roce_pct', 'N/A')}%\n"
                f"- Debt to Equity: {context_data.get('fundamentals', {}).get('debt_to_equity', 'N/A')}\n"
                f"- Implied Growth (Reverse DCF): {context_data.get('reverse_dcf', {}).get('implied_growth_priced_in_pct', 'N/A')}%\n\n"
                "What specific forensic pillar would you like to drill into?"
            )
        append_conversation_turn(conversation_id, "agent", fallback_msg)
        return {"conversation_id": conversation_id, "response": fallback_msg, "status": "DETERMINISTIC_FALLBACK"}

    system_prompt = f"""{SEBI_SAFE_HARBOR_DIRECTIVE}
You are the Institutional Investor Copilot on Stock Research App.
You assist allocators and research analysts in stress-testing investment theses across Equities, Mutual Funds, and Corporate Debt using our multi-asset forensic frameworks.
When discussing potential risks, actively employ Pre-Mortem Inversion (identifying what could break the thesis).

Active Security Context:
{json.dumps(context_data, indent=2)}

Recent Conversation History:
{history_str}
"""
    try:
        client = Client(api_key=api_key)
        resp = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=f"{system_prompt}\n\nUSER: {user_message}\nCOPILOT:"
        )
        agent_reply = resp.text or "Unable to formulate response."
    except Exception as e:
        logger.error(f"Copilot model invocation error: {e}")
        agent_reply = f"Error processing cognitive analysis: {str(e)}"

    # 6. Save agent turn to database
    append_conversation_turn(conversation_id, "agent", agent_reply)

    return {
        "conversation_id": conversation_id,
        "response": agent_reply,
        "status": "COMPLETED"
    }
