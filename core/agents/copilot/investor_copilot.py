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


def check_non_advisory_compliance(message: str, asset_class: str = "EQUITY") -> Optional[str]:
    """Intercepts retail advisory queries and returns mandatory regulatory deflection tailored to asset class."""
    lowered = (message or "").lower()
    for pat in FORBIDDEN_QUERY_PATTERNS:
        if pat in lowered:
            if asset_class == "MUTUAL_FUND":
                return (
                    "**SEBI Regulatory Non-Advisory Notice:**\n\n"
                    "Under SEBI Research Analyst Regulations 2014 Section 2(u), this research copilot operates "
                    "strictly as an institutional software diagnostic utility and is prohibited from providing personalized investment advice, "
                    "fund recommendations, or Buy/Sell/Switch calls.\n\n"
                    "I can, however, provide an objective **Look-Through Forensic Breakdown** of the fund's Weighted Moat Index, "
                    "Look-Through ASRI Accounting Risk, Active Share vs Benchmark, and Direct vs Regular Distributor Fee Drag. "
                    "Which diagnostic area would you like to explore?"
                )
            elif asset_class == "CORPORATE_DEBT":
                return (
                    "**SEBI Regulatory Non-Advisory Notice:**\n\n"
                    "Under SEBI Research Analyst Regulations 2014 Section 2(u), this research copilot operates "
                    "strictly as an institutional software diagnostic utility and is prohibited from providing personalized investment advice, "
                    "credit buy/sell ratings, or investment calls.\n\n"
                    "I can, however, provide an objective evaluation of the issuer's **Asset Coverage Ratio (ACR)**, "
                    "Recovery Seniority in liquidation, DSCR covenant headroom, and Credit Contagion Radar posture. "
                    "Which diagnostic area would you like to explore?"
                )
            else:
                return (
                    "**SEBI Regulatory Non-Advisory Notice:**\n\n"
                    "Under SEBI Research Analyst Regulations 2014 Section 2(u), this research copilot operates "
                    "strictly as a software diagnostic utility and is prohibited from providing personalized investment advice, "
                    "price targets, or Buy/Sell/Hold verdicts.\n\n"
                    "I can, however, provide an objective **Pre-Mortem Inversion Analysis** or break down the company's "
                    "Margin of Safety, Balance Sheet Solvency, and Reverse DCF implied growth rates. Which diagnostic area would you like to explore?"
                )
    return None


def build_mutual_fund_deterministic_response(
    context_data: Dict[str, Any],
    section: Optional[str],
    ticker: str
) -> str:
    """Builds a section-anchored deterministic fallback response for mutual funds."""
    name = context_data.get("scheme_name") or ticker or "Mutual Fund Scheme"
    sec = (section or "").lower().strip()

    if sec == "fee_drag":
        ter_dir = context_data.get("ter_direct_pct", "N/A")
        ter_reg = context_data.get("ter_regular_pct", "N/A")
        spread_bps = "N/A"
        try:
            if ter_dir != "N/A" and ter_reg != "N/A":
                spread_bps = f"{round((float(ter_reg) - float(ter_dir)) * 100, 1)} bps/yr"
        except Exception:
            pass
        return (
            f"**Intermediary Fee Drag & Wealth Destruction Audit for {name}:**\n\n"
            f"- Direct Plan TER: {ter_dir}%\n"
            f"- Regular Plan TER: {ter_reg}%\n"
            f"- Distributor Commission Spread: {spread_bps}\n\n"
            "**Fiduciary Impact:** Over a 15–25 year compounding horizon, this distributor spread extracts "
            "between 15% and 25% of the total ending corpus value in non-value-add commissions. "
            "Switching to the Direct plan preserves 100% of compounding power without altering portfolio risk.\n\n"
            "Would you like to examine look-through constituent quality or active share next?"
        )
    elif sec in ["active_share", "diversification"]:
        as_pct = context_data.get("active_share_pct", "N/A")
        benchmark = context_data.get("benchmark_index", "Benchmark")
        verdict = "High-Conviction Active Management" if isinstance(as_pct, (int, float)) and as_pct >= 60 else "Potential Closet Indexer / Benchmark Hugger"
        return (
            f"**Active Share & Closet Indexing Diagnostic for {name}:**\n\n"
            f"- Active Share: {as_pct}%\n"
            f"- Benchmark Index: {benchmark}\n"
            f"- Diagnostic Assessment: **{verdict}**\n\n"
            "**Fiduciary Impact:** Active Share measures the percentage of portfolio holdings that differ from the benchmark index. "
            "A fund with Active Share below 60% is essentially charging active management fees while hugging the benchmark, "
            "which mathematically guarantees long-term net-of-fee underperformance.\n\n"
            "Would you like to drill into the top constituent holdings or portfolio concentration?"
        )
    elif sec in ["asri_solvency", "accounting_risk"]:
        asri = context_data.get("accounting_risk_index", "N/A")
        pledge = context_data.get("promoter_pledge_exposure_pct", 0.0)
        risky = context_data.get("top_risky_holdings", [])
        risky_str = ", ".join([f"{h.get('name', h.get('identifier', 'Unknown'))} ({h.get('weight_pct', 0)}%)" for h in risky]) if risky else "Zero elevated leverage or governance red flags"
        return (
            f"**Look-Through Accounting Risk (ASRI) Diagnostic for {name}:**\n\n"
            f"- Portfolio Accounting Risk Index (ASRI): {asri}%\n"
            f"- Promoter Pledge Exposure: {pledge}%\n"
            f"- Constituents on Solvency Watchlist: {risky_str}\n\n"
            "**Fiduciary Impact:** Look-through ASRI computes the capital-weighted accounting stress across underlying companies, "
            "screening for aggressive revenue recognition, Beneish M-score flags, and high promoter pledge encumbrances.\n\n"
            "Which underlying holding would you like to inspect in detail?"
        )
    elif sec in ["moat_index", "quality"]:
        moat = context_data.get("weighted_moat_score", "N/A")
        comp = context_data.get("composite_health_score", "N/A")
        quality = context_data.get("top_quality_holdings", [])
        qual_str = ", ".join([f"{h.get('name', h.get('identifier', 'Unknown'))} ({h.get('weight_pct', 0)}%)" for h in quality]) if quality else "Diversified core compounders"
        return (
            f"**Weighted Moat & Quality Diagnostic for {name}:**\n\n"
            f"- Weighted Moat Score: {moat}/100\n"
            f"- Composite Health Score: {comp}/100\n"
            f"- Core Fortress Moat Allocations: {qual_str}\n\n"
            "**Fiduciary Impact:** The Weighted Moat Index measures structural pricing power, high ROIC persistence, "
            "and market share protection across the underlying constituent companies.\n\n"
            "Would you like to examine valuation margins or downside capture next?"
        )
    elif sec == "margin_of_safety":
        mos = context_data.get("margin_of_safety_pct", "N/A")
        return (
            f"**Weighted Margin of Safety (DCF) Diagnostic for {name}:**\n\n"
            f"- Weighted Portfolio Margin of Safety: {mos}%\n"
            f"- Category: {context_data.get('category', 'Equity Scheme')}\n\n"
            "**Fiduciary Impact:** This metric aggregates the intrinsic value discounts/premiums across all underlying "
            "equity constituents based on verified institutional DCF models in reports.db.\n\n"
            "Would you like to examine constituent holdings or fee drag next?"
        )
    elif sec in ["holdings", "dual_sleeve"]:
        risky = context_data.get("top_risky_holdings", [])
        quality = context_data.get("top_quality_holdings", [])
        aum = context_data.get("aum_crores", "N/A")
        return (
            f"**Constituent Holdings & Asset Allocation for {name}:**\n\n"
            f"- Category: {context_data.get('category', 'Equity Scheme')}\n"
            f"- AUM: ₹{aum} Cr\n"
            f"- Fortress Moat Allocations: {len(quality)} tracked core holdings\n"
            f"- Solvency Watchlist Allocations: {len(risky)} flagged holdings\n\n"
            "**Look-Through Framework:** Each constituent stock is individually evaluated via our 7-Pillar Equity Forensic Engine.\n\n"
            "Would you like to analyze a specific holding or check active share?"
        )
    elif sec == "downside_capture":
        return (
            f"**Risk-Adjusted Alpha & Downside Capture Diagnostic for {name}:**\n\n"
            f"- Composite Health Score: {context_data.get('composite_health_score', 'N/A')}/100\n"
            f"- Category: {context_data.get('category', 'Equity Scheme')}\n"
            f"- Benchmark: {context_data.get('benchmark_index', 'Benchmark')}\n\n"
            "**Fiduciary Impact:** Asymmetrical compounding relies on low downside capture (≤ 75% of benchmark drawdowns) "
            "combined with healthy upside participation to produce superior risk-adjusted alpha over full market cycles.\n\n"
            "Would you like to inspect active share or fee drag next?"
        )
    elif sec == "dossier_narrative":
        dossier_text = context_data.get("dossier_text", "")
        summary_snip = (dossier_text[:350] + "...") if len(dossier_text) > 350 else dossier_text
        return (
            f"**Qualitative Forensic Audit Summary for {name}:**\n\n"
            f"{summary_snip or 'Comprehensive 7-pillar institutional look-through audit completed.'}\n\n"
            f"- Composite Health Score: {context_data.get('composite_health_score', 'N/A')}/100\n"
            f"- Weighted Moat Score: {context_data.get('weighted_moat_score', 'N/A')}/100\n\n"
            "Which qualitative audit finding would you like to explore?"
        )
    else:
        # Default Mutual Fund Look-Through Summary
        aum = context_data.get("aum_crores", "N/A")
        return (
            f"**Forensic Look-Through Summary for {name}:**\n\n"
            f"- Composite Health Score: {context_data.get('composite_health_score', 'N/A')}/100\n"
            f"- Weighted Moat Score: {context_data.get('weighted_moat_score', 'N/A')}/100\n"
            f"- Look-Through Accounting Risk Index (ASRI): {context_data.get('accounting_risk_index', 'N/A')}%\n"
            f"- Weighted Margin of Safety: {context_data.get('margin_of_safety_pct', 'N/A')}%\n"
            f"- Active Share: {context_data.get('active_share_pct', 'N/A')}%\n"
            f"- AUM: ₹{aum} Cr\n\n"
            "What specific look-through metric, constituent holding, or fee drag area would you like to investigate?"
        )


def build_debt_deterministic_response(
    context_data: Dict[str, Any],
    section: Optional[str],
    ticker: str
) -> str:
    """Builds a section-anchored deterministic fallback response for debt securities."""
    name = context_data.get("instrument_name") or ticker or "Debt Security"
    sec = (section or "").lower().strip()

    if sec in ["covenants", "asset_coverage"]:
        return (
            f"**Asset Coverage & Covenant Headroom for {name}:**\n\n"
            f"- Credit Rating: {context_data.get('credit_rating', 'N/A')}\n"
            f"- Seniority Tier: {context_data.get('seniority_tier', 'N/A')}\n"
            f"- Posture Badge: {context_data.get('posture_badge', 'N/A')}\n\n"
            "**Solvency Assessment:** Evaluates underlying asset encumbrance, security charge, and DSCR headroom against covenant thresholds.\n\n"
            "Would you like to examine the Credit Contagion Radar or duration profile?"
        )
    elif sec in ["contagion", "radar"]:
        return (
            f"**Credit Contagion Radar Analysis for {name}:**\n\n"
            f"- Status: {context_data.get('contagion_radar_status', 'N/A')} ({context_data.get('contagion_risk_level', 'N/A')})\n"
            f"- Issuer/Group Summary: {context_data.get('radar_summary', 'N/A')}\n\n"
            "**Fiduciary Impact:** Monitors cross-default triggers, parent-subsidiary guarantees, and systemic group leverage.\n\n"
            "Would you like to review recovery seniority or YTM profile?"
        )
    else:
        return (
            f"**Credit & Solvency Summary for {name}:**\n\n"
            f"- Credit Rating: {context_data.get('credit_rating', 'N/A')}\n"
            f"- YTM: {context_data.get('ytm_pct', 'N/A')}%\n"
            f"- Duration: {context_data.get('macaulay_duration_years', 'N/A')} yrs\n"
            f"- Seniority: {context_data.get('seniority_tier', 'N/A')}\n"
            f"- Credit Contagion Radar: {context_data.get('contagion_radar_status', 'N/A')} ({context_data.get('contagion_risk_level', 'N/A')})\n\n"
            f"> {context_data.get('radar_summary', '')}\n\n"
            "What specific solvency or capital hierarchy pillar would you like to drill into?"
        )


def build_equity_deterministic_response(
    context_data: Dict[str, Any],
    section: Optional[str],
    ticker: str
) -> str:
    """Builds a section-anchored deterministic fallback response for equities."""
    name = ticker or "Equity Security"
    sec = (section or "").lower().strip()
    fund = context_data.get("fundamentals", {})
    dcf = context_data.get("reverse_dcf", {})

    if sec in ["reverse_dcf", "valuation"]:
        return (
            f"**Reverse DCF Valuation Analysis for {name}:**\n\n"
            f"- CMP: ₹{fund.get('cmp', 'N/A')}\n"
            f"- Implied FCF Growth Priced In: {dcf.get('implied_growth_priced_in_pct', 'N/A')}%\n"
            f"- Benchmark Hurdle Rate: {dcf.get('hurdle_rate_pct', '12.0')}%\n\n"
            "**Inversion Takeaway:** Reverse DCF unpacks market expectations. Compare this priced-in growth rate against "
            "historical 5-year median growth to determine if current valuation offers adequate Margin of Safety.\n\n"
            "Would you like to run a Pre-Mortem Inversion or inspect balance sheet solvency?"
        )
    elif sec in ["pre_mortem", "risks"]:
        return (
            f"**Pre-Mortem Inversion Diagnostic for {name}:**\n\n"
            f"- Solvency Posture: Debt/Equity {fund.get('debt_to_equity', 'N/A')}, ROCE {fund.get('roce_pct', 'N/A')}%\n"
            f"- Key Thesis Vulnerabilities: Terminal growth compression, capital misallocation, and valuation de-rating.\n\n"
            "What specific operating headwind or structural risk would you like to stress-test?"
        )
    else:
        return (
            f"**Diagnostic Summary for {name}:**\n\n"
            f"- P/E Ratio: {fund.get('pe_ratio', 'N/A')}\n"
            f"- ROCE: {fund.get('roce_pct', 'N/A')}%\n"
            f"- Debt to Equity: {fund.get('debt_to_equity', 'N/A')}\n"
            f"- Implied Growth (Reverse DCF): {dcf.get('implied_growth_priced_in_pct', 'N/A')}%\n\n"
            "What specific forensic pillar would you like to drill into?"
        )


async def process_copilot_turn(
    conversation_id: str,
    user_message: str,
    ticker: Optional[str] = None,
    user_id: Optional[str] = None,
    asset_type: Optional[str] = None,
    section: Optional[str] = None,
    section_label: Optional[str] = None,
    section_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Processes a user dialogue turn with conversational memory, multi-asset grounding, and section awareness."""
    # 1. Ensure conversation exists in DB
    create_or_get_agent_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
        agent_type="equity_copilot",
        context_ticker=ticker
    )

    # 2. Record incoming user turn
    append_conversation_turn(conversation_id, "user", user_message)

    clean_ticker = (ticker or "").strip().upper()

    # 3. Resolve Target Asset Class
    norm_asset = (asset_type or "").lower().strip()
    if norm_asset in ["mutual_fund", "fund", "mf"]:
        resolved_asset_class = "MUTUAL_FUND"
    elif norm_asset in ["corporate_debt", "debt", "bond", "sdi", "ncd"]:
        resolved_asset_class = "CORPORATE_DEBT"
    elif norm_asset in ["equity", "stock"]:
        resolved_asset_class = "EQUITY"
    else:
        # Auto-detect from ticker pattern
        if clean_ticker.startswith("IN") or clean_ticker.endswith("BOND") or "SDI" in clean_ticker or "NCD" in clean_ticker:
            resolved_asset_class = "CORPORATE_DEBT"
        elif clean_ticker.isdigit() or clean_ticker.endswith("_DIR") or clean_ticker.endswith("_REG") or any(kw in clean_ticker for kw in ["FLEXICAP", "MIDCAP", "SMALLCAP", "NIFTY", "FUND"]):
            resolved_asset_class = "MUTUAL_FUND"
        else:
            resolved_asset_class = "EQUITY"

    # 4. Regulatory Compliance Filter with Asset-Class Precision
    deflection = check_non_advisory_compliance(user_message, asset_class=resolved_asset_class)
    if deflection:
        append_conversation_turn(conversation_id, "agent", deflection)
        return {
            "conversation_id": conversation_id,
            "response": deflection,
            "status": "REGULATORY_DEFLECTED"
        }

    # 5. Context Grounding with Strict Multi-Asset Isolation
    context_data: Dict[str, Any] = {
        "asset_class": resolved_asset_class,
        "active_section": section,
        "active_section_label": section_label,
        "section_data": section_data or {}
    }

    if clean_ticker:
        if resolved_asset_class == "MUTUAL_FUND":
            # Mutual Fund Scheme Forensic Look-Through Grounding
            from core.db.mutual_funds import get_mutual_fund_scheme, get_fund_forensic_dossier
            scheme = get_mutual_fund_scheme(clean_ticker)
            canonical_code = scheme.get("scheme_code") if scheme else clean_ticker
            dossier = get_fund_forensic_dossier(canonical_code) or {}

            context_data.update({
                "scheme_code": canonical_code,
                "scheme_name": scheme.get("scheme_name", clean_ticker) if scheme else clean_ticker,
                "category": scheme.get("category", "") if scheme else "",
                "fund_house": scheme.get("fund_house", "") if scheme else "",
                "benchmark_index": scheme.get("benchmark_index", "NIFTY 500 TRI") if scheme else "NIFTY 500 TRI",
                "fund_manager": scheme.get("fund_manager", "") if scheme else "",
                "aum_crores": (scheme.get("aum_crores") or scheme.get("aum_cr", 0.0)) if scheme else 0.0,
                "ter_direct_pct": scheme.get("ter_direct_pct", 0.0) if scheme else 0.0,
                "ter_regular_pct": scheme.get("ter_regular_pct", 0.0) if scheme else 0.0,
                "composite_health_score": dossier.get("composite_health_score", 70.0),
                "weighted_moat_score": dossier.get("weighted_moat_score", 65.0),
                "accounting_risk_index": dossier.get("accounting_risk_index", 15.0),
                "margin_of_safety_pct": dossier.get("margin_of_safety_pct", 0.0),
                "active_share_pct": dossier.get("active_share_pct") or (scheme.get("active_share_pct", 75.0) if scheme else 75.0),
                "promoter_pledge_exposure_pct": dossier.get("promoter_pledge_exposure_pct", 0.0),
                "top_risky_holdings": dossier.get("top_risky_holdings", []),
                "top_quality_holdings": dossier.get("top_quality_holdings", []),
                "dossier_text": dossier.get("dossier_text", "")
            })

        elif resolved_asset_class == "CORPORATE_DEBT":
            # Corporate Debt / SDI Security Grounding
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
                context_data.update({
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
                })

        else:
            # Fundamental Equity Grounding
            try:
                fund_raw = await asyncio.to_thread(tool_get_equity_fundamentals, clean_ticker)
                dcf_raw = await asyncio.to_thread(tool_calculate_reverse_dcf, clean_ticker)
                context_data.update({
                    "ticker": clean_ticker,
                    "fundamentals": json.loads(fund_raw),
                    "reverse_dcf": json.loads(dcf_raw)
                })
            except Exception as e:
                logger.warning(f"Error grounding equity context for {clean_ticker}: {e}")

    # 6. Cognitive AI Response Synthesis
    history = get_conversation_turns(conversation_id, limit=6)
    history_str = "\n".join([f"{t['sender_role'].upper()}: {t['content']}" for t in history[:-1]])

    from google.genai import Client
    api_key = get_secret("GEMINI_API_KEY")

    if not api_key:
        asset_cls = context_data.get("asset_class", "EQUITY")
        if asset_cls == "MUTUAL_FUND":
            fallback_msg = build_mutual_fund_deterministic_response(context_data, section, clean_ticker)
        elif asset_cls == "CORPORATE_DEBT":
            fallback_msg = build_debt_deterministic_response(context_data, section, clean_ticker)
        else:
            fallback_msg = build_equity_deterministic_response(context_data, section, clean_ticker)

        append_conversation_turn(conversation_id, "agent", fallback_msg)
        return {"conversation_id": conversation_id, "response": fallback_msg, "status": "DETERMINISTIC_FALLBACK"}

    # Construct Asset-Aware and Section-Aware System Prompt
    asset_instructions = ""
    if resolved_asset_class == "MUTUAL_FUND":
        asset_instructions = (
            "================================================================================\n"
            "CRITICAL ASSET DIRECTIVE: THIS IS A MUTUAL FUND SCHEME, NOT AN INDIVIDUAL COMPANY OR STOCK.\n"
            "- NEVER cite company quarterly filings, BSE disclosures, board meetings, or earnings transcripts for this scheme.\n"
            "- NEVER refer to the fund as a company, corporation, or single operating business.\n"
            "- Strictly evaluate fund portfolio forensics:\n"
            "  1. Constituent Look-Through Quality & Weighted Moat Index\n"
            "  2. Look-Through Accounting Risk (ASRI) and promoter pledge exposure across constituent holdings\n"
            "  3. Active Share vs Benchmark, Closet Indexing, and Style Drift\n"
            "  4. Downside Capture vs Upside Capture spread & Sortino risk-adjusted alpha\n"
            "  5. Dual-sleeve asset allocation (Equity, Debt, Cash/TREPS) and portfolio concentration\n"
            "  6. Intermediary Fee Drag (Direct vs Regular plan TER spread & compounded wealth destruction)\n"
            "- If the user asks about individual stocks, evaluate them as underlying constituent holdings held by this fund.\n"
        )
    elif resolved_asset_class == "CORPORATE_DEBT":
        asset_instructions = (
            "================================================================================\n"
            "CRITICAL ASSET DIRECTIVE: THIS IS A FIXED INCOME / CORPORATE DEBT / SDI SECURITY.\n"
            "- Focus strictly on credit solvency, capital structure seniority, recovery rights, and covenant headroom.\n"
            "- Evaluate the Credit Contagion Radar, group financial leverage, and systemic spillover risks.\n"
        )
    else:
        asset_instructions = (
            "================================================================================\n"
            "CRITICAL ASSET DIRECTIVE: THIS IS A FUNDAMENTAL EQUITY SECURITY.\n"
            "- Evaluate company fundamentals, Reverse DCF implied growth rates, and forensic accounting solvency.\n"
            "- When discussing risks, actively employ Pre-Mortem Inversion (identifying thesis failure modes).\n"
        )

    section_instructions = ""
    if section:
        section_instructions = (
            f"================================================================================\n"
            f"ACTIVE WORKSPACE SECTION FOCUS: {section} ({section_label or section})\n"
            f"The user clicked into Copilot directly from the '{section_label or section}' section of this dossier.\n"
            f"Directly anchor your response to the metrics, findings, and diagnostic significance of this section.\n"
        )

    system_prompt = f"""{SEBI_SAFE_HARBOR_DIRECTIVE}
You are the Institutional Investor Copilot on Stock Research App.
You assist allocators and research analysts in stress-testing investment theses across Equities, Mutual Funds, and Corporate Debt using our multi-asset forensic frameworks.

{asset_instructions}
{section_instructions}

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
        status = "COMPLETED"
    except Exception as e:
        logger.warning(f"Copilot model invocation error: {e}. Falling back to deterministic response.")
        asset_cls = context_data.get("asset_class", "EQUITY")
        if asset_cls == "MUTUAL_FUND":
            agent_reply = build_mutual_fund_deterministic_response(context_data, section, clean_ticker)
        elif asset_cls == "CORPORATE_DEBT":
            agent_reply = build_debt_deterministic_response(context_data, section, clean_ticker)
        else:
            agent_reply = build_equity_deterministic_response(context_data, section, clean_ticker)
        status = "DETERMINISTIC_FALLBACK"

    # 7. Save agent turn to database
    append_conversation_turn(conversation_id, "agent", agent_reply)

    return {
        "conversation_id": conversation_id,
        "response": agent_reply,
        "status": status
    }
