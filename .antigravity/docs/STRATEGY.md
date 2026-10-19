# Moatnomics Strategic Positioning, Brand House & Differential Engine

> **Canonical Reference:** [`docs/BRAND_HOUSE_AND_VOICE_GUIDE.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/BRAND_HOUSE_AND_VOICE_GUIDE.md) | **Code Module:** [`core/brand/moatnomics_house.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/brand/moatnomics_house.py)

## 1. Brand House & Core Promise
- **Brand:** Moatnomics
- **Category Descriptor:** Multi-asset investment research
- **Creative Territory:** *Less noise, more nuance.*
- **Operational Dual-Mandate Tagline:** *Audit the Asset. Protect the Allocator.*
- **Core Brand Promise:** *Understand the evidence. Examine the trade-offs. Know what deserves a closer look.*
- **Core Principle:** *Nuance should make a decision clearer, not make the reader work harder.*
- **Voice in One Sentence:** *The mind of a research analyst, the clarity of a good editor, and the restraint of someone who knows markets can make fools of confident people.*
- **Four Brand Behaviours:**
  1. **Investigate deeply:** Go beyond surface metrics to understand business quality, valuation, risk, and underlying exposures.
  2. **Challenge independently:** Examine the countercase, test assumptions, and separate a good story from a sound investment case.
  3. **Trace the evidence:** Make sources, calculations, assumptions, and analytical judgements distinguishable (`VERIFIED FACT`, `CALCULATION`, `INTERPRETATION`, `ASSUMPTION`, `UNCERTAINTY`).
  4. **Monitor what changes:** Track developments that strengthen, weaken, or invalidate the original thesis.
- **Product Journey:** `Discover → Investigate → Evaluate/Compare → Monitor` (and in reverse: monitoring reveals an insight → research update → explainer/short-form).

## 2. Editorial Method & Six-Point Quality Gate
- **Editorial Method:** `Context → Evidence → Implication → Next question`
  1. **Context:** What is the reader seeing, hearing, or assuming?
  2. **Evidence:** What facts, data, calculations, or credible sources support or challenge the interpretation?
  3. **Implication:** What does the evidence change about the assessment? State the conclusion and confidence.
  4. **Next question:** What should the reader investigate, compare, monitor, or verify next?
- **Six-Point Pre-Publication Check:**
  1. *A real insight* (consequential vs. restating a familiar principle)
  2. *A defensible claim* (traceable sources, reproducible calculations)
  3. *Meaningful context* (materially affects interpretation)
  4. *A fair countercase* (contrary evidence and alternative explanations considered)
  5. *A useful implication* (reader understands why it matters)
  6. *Honest boundaries* (uncertainty, data limitations, and fact-vs-interpretation clear)

## 3. Multi-Asset Product Roadmap
- **Tier 1 (Equities Thesis):** Automated qualitative equity engine grounding 7-pillar reports with epistemic separation (`VERIFIED FACT`, `CALCULATED METRIC`, `MODEL INTERPRETATION`, `UNRESOLVED UNCERTAINTY`) and falsification triggers.
- **Tier 2 (Mutual Fund Look-Through & Multi-Asset Matrix):** Ingesting mutual fund disclosures, corporate debt, REITs/InvITs, ETFs, and unlisted MSMEs to score assets based on forward-looking business quality, cash conversion, tax drag, and underlying exposures.
- **Tier 3 (Qualified Institutional Services):** Equipping professional investors, analysts, fund managers, institutional investors, RIAs, and serious individual investors with structured workflows, source traceability, and thesis monitoring.

## 4. Differential Tracking Engine
- **Append-Only Archiving:** Database rows are immutable; material events trigger new entries in `report_revisions`, preserving historical text and timestamps.
- **High-Value Correlations:** Compares historical snapshots to detect "Value Traps" (qualitative downgrades occurring alongside valuation expansions) and tracks Mutual Fund Style Drift over successive quarters.
