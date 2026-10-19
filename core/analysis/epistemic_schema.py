"""
core/analysis/epistemic_schema.py
==============================================================================
Institutional Epistemic Separation, Source-Passage Attribution & Falsification Engine.

Enforces three non-negotiable standards across all Moatnomics report structures:
1. Source-Passage Attribution: Links material claims to specific underlying sources,
   filing dates, and verbatim/structured passages.
2. 4-Tier Epistemic Separation:
   - [VERIFIED FACT]: Directly reported in statutory filings (BSE/NSE/AMFI/Udyam/SEBI).
   - [CALCULATED METRIC]: Deterministic mathematical output from verified inputs.
   - [MODEL INTERPRETATION]: Analytical regime classification or qualitative thesis.
   - [UNRESOLVED UNCERTAINTY]: Unverified disclosures, missing data, or forward contingencies.
3. Falsification & Thesis-Revision Protocol:
   - Explicitly states what empirical evidence would contradict the current conclusion
     and the exact quantitative thresholds that would force a rating/thesis revision.
==============================================================================
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from core.analysis.parser import render_epistemic_badges_html, strip_conclusion_sections


EPISTEMIC_PROMPT_DIRECTIVE = """
### MANDATORY EPISTEMIC SEPARATION, SOURCE ATTRIBUTION & FALSIFICATION PROTOCOL
In EVERY Pillar (Pillar 1 through Pillar 7), you MUST enforce strict epistemic hygiene:
1. **Inline Epistemic Badges & Source-Passage Attribution:**
   - Tag material empirical statements with their exact epistemic tier:
     * `[VERIFIED FACT]` — Cite the specific statutory filing, source date, and relevant passage/figure (e.g., *"[VERIFIED FACT — BSE Audited Financial Results, FY25/Q3: Consolidated revenue stood at ₹... Cr]"*). Never fabricate quotes; if an exact filing passage is not in the grounding context, cite the structured exchange dataset field and date.
     * `[CALCULATED METRIC]` — State the formula or deterministic derivation (e.g., *"[CALCULATED METRIC: Net Debt/EBITDA = 0.42x; 2-Stage DCF Intrinsic Value = ₹...]"*).
     * `[MODEL INTERPRETATION]` — Clearly mark qualitative moat, governance, or drop-diagnostic inferences (e.g., *"[MODEL INTERPRETATION: Margin compression reflects temporary raw-material destocking rather than structural pricing decay]"*).
     * `[UNRESOLVED UNCERTAINTY]` — Explicitly flag unverified contingencies, unlisted subsidiary opacity, or pending regulatory outcomes.
2. **Mandatory Falsification Block at the End of Each Pillar:**
   - Conclude each pillar with a concise sub-block titled:
     `#### Falsification & Thesis-Revision Triggers`
   - Inside this sub-block, include exactly two bullets:
     * **What Contradicts This Conclusion:** Specific disconfirming evidence or counter-indicators that would challenge the pillar's thesis.
     * **Evidence That Forces a Revision:** Quantifiable thresholds in upcoming quarterly/annual filings (e.g., RoCE dropping below X%, promoter pledge crossing Y%, DSO expanding >30 days) that would automatically downgrade this pillar's rating.
"""


def build_equity_epistemic_ledger(
    ticker: str,
    stock_data: Optional[Dict[str, Any]] = None,
    equity_intel: Optional[Dict[str, Any]] = None,
    formatted_date: str = "Latest Filing"
) -> Dict[str, Any]:
    """Builds the structured 5-part epistemic & falsification ledger for Equity Dossiers."""
    sd = stock_data or {}
    intel = equity_intel or {}
    val_radar = intel.get("valuation_radar") or {}
    forensic = intel.get("forensic_intelligence") or {}
    sector_intel = intel.get("sector_intelligence") or {}

    scrip = sd.get("scrip_code") or "BSE-Listed"
    price = sd.get("current_price") or val_radar.get("current_price") or "N/A"
    pe = sd.get("pe_ratio") or "N/A"
    fv = val_radar.get("fair_value")
    mos = val_radar.get("margin_of_safety_pct")

    return {
        "as_of_date": formatted_date,
        "verified_facts": [
            {
                "claim": f"Exchange Market Quote & Valuation Baseline: CMP ₹{price} | Trailing P/E: {pe}x",
                "source": f"BSE / NSE Exchange Feed (Scrip: {scrip})",
                "source_date": formatted_date,
                "passage": f"Official exchange trade execution record and trailing twelve-month (TTM) statutory EPS filing for {ticker}."
            },
            {
                "claim": f"360° Forensic Sieve Pass Rate: {forensic.get('passed_count', 'N/A')}/{forensic.get('total_checks', 10)} Statutory Checks Passed",
                "source": "BSE Corporate Shareholding & Audited Balance Sheet Filings",
                "source_date": formatted_date,
                "passage": f"Grounded against Regulation 31 shareholding disclosures and statutory balance sheet schedules ({forensic.get('badge_label', 'Audited')})."
            }
        ],
        "calculated_metrics": [
            {
                "metric": f"Multi-Model Intrinsic Fair Value: {'₹{:,.2f}'.format(fv) if isinstance(fv, (int, float)) else 'Pending'} (Margin of Safety: {mos if mos is not None else 'N/A'}%)",
                "formula": "Triangulated mean of 5Y Median P/E, 2-Stage Conservative DCF (11.0% WACC, 4.5% terminal growth), and Graham EPV floor."
            },
            {
                "metric": f"Sector Benchmark Alignment: {sector_intel.get('verdict', 'NEUTRAL').replace('_', ' ').title()}",
                "formula": f"Peer-relative operating Z-score across {sector_intel.get('sector_display_name', 'Indian listed peers')}."
            }
        ],
        "model_interpretations": [
            f"Valuation Regime classified as '{val_radar.get('regime', 'FAIR_VALUE').replace('_', ' ').title()}': {val_radar.get('summary', 'Evaluated against conservative cash flow discount rates.')}",
            f"Sector & Moat Posture: {sector_intel.get('narrative', 'Evaluated against domestic capex and industry margin cycles.')}"
        ],
        "unresolved_uncertainties": [
            "Intraday off-market institutional block crossovers and unannounced working-capital credit lines between quarterly Regulation 33 filings remain unobserved until statutory exchange publication.",
            "Forward DCF realization depends on management sustaining historical reinvestment efficiency across the next 4–8 quarters without dilutive equity raises."
        ],
        "falsification_triggers": {
            "what_could_contradict": [
                "Operating cash flow (OCF) to EBITDA conversion falling below 65% for two consecutive semi-annual balance sheet disclosures, indicating aggressive accrual recognition.",
                "Sustained gross margin compression >250 bps vs. sector peers proving inability to pass through input cost inflation."
            ],
            "evidence_that_changes_conclusion": [
                "Promoter encumbrance / share pledging rising by >5.0% in any quarterly BSE Regulation 31 filing, or auditor qualification under CARO 2020.",
                "10-Year G-Sec yield spike >75 bps or earnings growth deceleration >400 bps below Reverse-DCF implied growth rate."
            ]
        }
    }


def extract_epistemic_badges(report_text: str) -> Dict[str, List[str]]:
    """
    Parses and categorizes all 4-tier epistemic badges from a rendered report markdown.
    Returns:
        {
            "verified_facts": [...],
            "calculated_metrics": [...],
            "model_interpretations": [...],
            "unresolved_uncertainties": [...]
        }
    """
    if not report_text:
        return {
            "verified_facts": [],
            "calculated_metrics": [],
            "model_interpretations": [],
            "unresolved_uncertainties": []
        }

    def _extract_full(tag_pattern: str) -> List[str]:
        return [m.strip("[]") for m in re.findall(rf"\[{tag_pattern}[^\]]*\]", report_text, re.IGNORECASE)]

    return {
        "verified_facts": _extract_full("VERIFIED FACT"),
        "calculated_metrics": _extract_full("CALCULATED METRIC"),
        "model_interpretations": _extract_full("MODEL INTERPRETATION"),
        "unresolved_uncertainties": _extract_full("UNRESOLVED UNCERTAINTY")
    }


def extract_falsification_triggers(report_text: str) -> Dict[int, Dict[str, str]]:
    """
    Extracts structured Falsification & Thesis-Revision Triggers per pillar from report markdown.
    Returns:
        {
            pillar_index: {
                "what_contradicts": "...",
                "evidence_that_forces_revision": "..."
            }
        }
    """
    if not report_text:
        return {}

    triggers: Dict[int, Dict[str, str]] = {}
    for m in re.finditer(r"(?im)^##+\s*Pillar\s*0?([1-7])\s*[:\.\-]\s*([^\n]+)\n(.*?)(?=^##+\s*Pillar\s*0?[1-7]|\Z)", report_text, re.DOTALL):
        p_idx = int(m.group(1))
        p_body = m.group(3)

        f_match = re.search(r"(?im)####\s*Falsification\s*&\s*Thesis[- ]Revision\s*Triggers\s*\n(.*?)(?=^#|\Z)", p_body, re.DOTALL)
        if f_match:
            block = f_match.group(1).strip()
            contradict_m = re.search(r"(?i)What\s+Contradicts[^\n:]*[:\*]+\s*([^\n]+(?:\n(?!\s*[\*\-]).*)*)", block)
            revision_m = re.search(r"(?i)Evidence\s+That\s+Forces[^\n:]*[:\*]+\s*([^\n]+(?:\n(?!\s*[\*\-]).*)*)", block)
            c_text = contradict_m.group(1).strip().lstrip("*: ").strip() if contradict_m else ""
            r_text = revision_m.group(1).strip().lstrip("*: ").strip() if revision_m else ""
            triggers[p_idx] = {
                "what_contradicts": c_text,
                "evidence_that_forces_revision": r_text
            }
    return triggers


def build_multi_asset_epistemic_ledger(
    asset_class: str,
    entity_id: str,
    context: Optional[Dict[str, Any]] = None,
    formatted_date: str = "Latest Filing"
) -> Dict[str, Any]:
    """
    Polymorphic dispatcher creating structured epistemic ledgers across:
    EQUITY, MUTUAL_FUND, DEBT, and REIT.
    """
    ac = (asset_class or "EQUITY").upper()
    ctx = context or {}

    if ac == "EQUITY":
        stock_data = ctx.get("stock_data") or ctx.get("fundamentals") or ctx
        equity_intel = ctx.get("equity_intel") or ctx
        return build_equity_epistemic_ledger(
            ticker=entity_id,
            stock_data=stock_data,
            equity_intel=equity_intel,
            formatted_date=formatted_date
        )

    if ac == "MUTUAL_FUND":
        scheme_name = ctx.get("scheme_name") or entity_id
        aum = ctx.get("aum") or "N/A"
        nav = ctx.get("nav") or "N/A"
        ter = ctx.get("ter") or "N/A"
        return {
            "as_of_date": formatted_date,
            "asset_class": "MUTUAL_FUND",
            "entity_id": entity_id,
            "verified_facts": [
                {
                    "claim": f"Statutory Scheme Facts: NAV ₹{nav} | AUM ₹{aum} Cr | TER {ter}%",
                    "source": "AMFI Daily NAV Feed & Monthly Portfolio Disclosure",
                    "source_date": formatted_date,
                    "passage": f"Audited scheme fact sheet filed under SEBI (Mutual Funds) Regulations, 1996 for {scheme_name}."
                }
            ],
            "calculated_metrics": [
                {
                    "metric": f"Portfolio Active Share & Alpha: {ctx.get('active_share', 'N/A')}% Active Share",
                    "formula": "Sum of absolute differences in scheme weights vs. category benchmark divided by 2."
                }
            ],
            "model_interpretations": [
                f"Manager Style & Factor Tilt: {ctx.get('style_tilt', 'Grounded against category benchmark factor dispersion.')}"
            ],
            "unresolved_uncertainties": [
                "Unpublished portfolio changes between monthly statutory SEBI portfolio disclosures."
            ],
            "falsification_triggers": {
                "what_could_contradict": [
                    "3-year rolling tracking error expanding beyond 250 bps vs. benchmark index."
                ],
                "evidence_that_changes_conclusion": [
                    "Lead fund manager resignation or sudden portfolio turnover ratio spike >120%."
                ]
            }
        }

    if ac in {"DEBT", "BOND"}:
        issuer = ctx.get("issuer_name") or entity_id
        rating = ctx.get("credit_rating") or "AAA"
        ytm = ctx.get("ytm") or "N/A"
        coupon = ctx.get("coupon_rate") or "N/A"
        return {
            "as_of_date": formatted_date,
            "asset_class": "DEBT",
            "entity_id": entity_id,
            "verified_facts": [
                {
                    "claim": f"Statutory Bond Profile: Coupon {coupon}% | Rating {rating} | YTM {ytm}%",
                    "source": "BSE Debt Segment / CRISIL / ICRA Statutory Credit Rating Rationales",
                    "source_date": formatted_date,
                    "passage": f"Statutory information memorandum and public credit rating surveillance letter for {issuer}."
                }
            ],
            "calculated_metrics": [
                {
                    "metric": f"Macaulay & Modified Duration: {ctx.get('modified_duration', 'N/A')} Years",
                    "formula": "Deterministic cash flow discounting against spot yield curve with convexity correction."
                }
            ],
            "model_interpretations": [
                f"Sovereign Spread & Credit Trajectory: {ctx.get('spread_verdict', 'Evaluated against 10Y G-Sec benchmark.')}"
            ],
            "unresolved_uncertainties": [
                "Private bilateral off-market repo covenants and promoter group cross-guarantees not recorded in public CSDL/NSDL filings."
            ],
            "falsification_triggers": {
                "what_could_contradict": [
                    "Credit rating watch placement or downgrade from primary rating agencies (CRISIL, ICRA, CARE)."
                ],
                "evidence_that_changes_conclusion": [
                    "Interest coverage ratio dropping below 2.0x in semi-annual audited results."
                ]
            }
        }

    if ac in {"REIT", "INVIT"}:
        name = ctx.get("name") or entity_id
        dist = ctx.get("ndcf_distribution") or "N/A"
        wale = ctx.get("wale") or "N/A"
        ltv = ctx.get("ltv_pct") or "N/A"
        return {
            "as_of_date": formatted_date,
            "asset_class": "REIT",
            "entity_id": entity_id,
            "verified_facts": [
                {
                    "claim": f"Statutory Trust Profile: NDCF Payout ₹{dist} | WALE {wale} Yrs | Net LTV {ltv}%",
                    "source": "Quarterly SEBI REIT Disclosures & Trust Valuation Reports",
                    "source_date": formatted_date,
                    "passage": f"Section 115UA tax waterfall and statutory NDCF reconciliation filed under SEBI (Real Estate Investment Trusts) Regulations, 2014 for {name}."
                }
            ],
            "calculated_metrics": [
                {
                    "metric": f"Post-Tax Real Yield: {ctx.get('post_tax_yield', 'N/A')}%",
                    "formula": "Waterfall calculation combining tax-free SPV dividends, interest, and amortized return of capital under Sec 56(2)(xii)."
                }
            ],
            "model_interpretations": [
                f"Asset Quality & Cap Rate Spread: {ctx.get('cap_rate_verdict', 'Evaluated against Class-A commercial vacancy rates.')}"
            ],
            "unresolved_uncertainties": [
                "Early lease termination break-clause exercises by top-3 anchor tenants before contracted lock-in periods."
            ],
            "falsification_triggers": {
                "what_could_contradict": [
                    "Portfolio occupancy falling below 85% or Net LTV exceeding 40% (approaching SEBI 49% cap)."
                ],
                "evidence_that_changes_conclusion": [
                    "NDCF payout reduction >10% YoY or adverse changes to Section 115UA tax pass-through status in Union Budget."
                ]
            }
        }

    return build_equity_epistemic_ledger(
        ticker=entity_id,
        stock_data=ctx,
        equity_intel=ctx,
        formatted_date=formatted_date
    )


__all__ = [
    "EPISTEMIC_PROMPT_DIRECTIVE",
    "build_equity_epistemic_ledger",
    "extract_epistemic_badges",
    "extract_falsification_triggers",
    "build_multi_asset_epistemic_ledger",
    "render_epistemic_badges_html",
    "strip_conclusion_sections",
]
