# Moatnomics Strategic Positioning, Brand House, Visual Identity & Differential Engine

> **Canonical References:**
> - [`docs/BRAND_HOUSE_AND_VOICE_GUIDE.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/BRAND_HOUSE_AND_VOICE_GUIDE.md) | [`core/brand/moatnomics_house.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/brand/moatnomics_house.py)
> - [`docs/VISUAL_IDENTITY_AND_MOTION_GUIDE.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/VISUAL_IDENTITY_AND_MOTION_GUIDE.md) | [`core/brand/visual_identity.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/brand/visual_identity.py)
> - [`docs/VISUAL_ARTIFACTS_INVENTORY.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/VISUAL_ARTIFACTS_INVENTORY.md) | [`docs/BRAND_COPY_INVENTORY.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/BRAND_COPY_INVENTORY.md)

## 1. Brand House & Core Promise
- **Brand:** Moatnomics
- **Category Descriptor:** Multi-asset investment research
- **Creative Territory:** *Less noise, more nuance.*
- **Operational Dual-Mandate Tagline:** *Audit the Asset. Protect the Allocator.*
- **Core Brand Promise:** *Understand the evidence. Examine the trade-offs. Know what deserves a closer look.*
- **Core Principle:** *Nuance should make a decision clearer, not make the reader work harder.*
- **Final Operating Rule (Visual & Editorial):** *Make the evidence easier to understand, not easier to believe.*
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

## 3. Visual Identity & Motion System (v2.0 — 20 October 2026)
- **Logo System ("The Perspective Portal"):**
  - **Approved Master Direction:** The earlier, more sophisticated dimensional split-arch with inward-angled perspective planes and a taller central vertical mirrored prism (`Reference Boards A & C`). Do **not** replace with the later simplified perfect-semicircle exploration (`Reference Board B`).
  - **Derivatives:** Flat vector and simplified small-size (`16px–24px` digital / `6mm` print) derivatives are mandatory for dense UI chrome, favicons, and monochrome uses.
- **Provisional Colour Palette & Dual First-Class Themes (Light & Dark):**
  - `Forest` (`#0E3D32`), `Sage` (`#7DA77A`), `Lime` (`#C7E268` — rare focal accent `<5%` area, never automatic profit green), `Ink Navy` (`#0B2337`), `Ivory` (`#F7F5EE`), `Mist` (`#D9E3E8`), `Charcoal` (`#282F33`), and `White` (`#FFFFFF`).
- **Typography & Numeric Discipline:**
  - Editorial display serif (`Tiempos Headline` / `Playfair Display` direction) paired with neutral product sans (`Inter` direction) and mandatory tabular numerals (`font-variant-numeric: tabular-nums`) across all financial metrics, tables, yields, and dates.
- **Portal Art vs. Flat UI Boundary:**
  - Architectural portal framing (`DEPTH`, `PERSPECTIVE`, `CLARITY`, `OPPORTUNITY`) belongs **only** on campaign heroes, homepage hero, flagship report covers, and section openers. Dense product screens, directories, comparison tables, and report interiors must remain strictly flat.
- **Iconography & Charts:**
  - Canonical 12-icon `24×24px` (`1.75–2px` stroke) vector grid (`Research`, `Markets`, `Compare`, `Watchlist`, `Insights`, `Portfolio`, `Risk`, `Valuation`, `Multi-asset`, `Screen`, `Alerts`, `Download`) with zero raw OS emojis.
  - 6-part chart anatomy requiring title, unit/currency/period subtitle, plot area, direct labels, source + as-of date + epistemic tier, and caveat line.
- **Motion & Asset Governance:**
  - 4-beat logo reveal (`700–1,200ms`), 8-step video narrative (`Question → Context → Evidence → Interpretation → Counterpoint → Implication → Watchpoint → Source & brand close`), and canonical asset naming (`brand_asset-purpose_variant_theme_locale_version_date.ext`).

## 4. Multi-Asset Product Roadmap
- **Tier 1 (Equities Thesis):** Automated qualitative equity engine grounding 7-pillar reports with epistemic separation (`VERIFIED FACT`, `CALCULATED METRIC`, `MODEL INTERPRETATION`, `UNRESOLVED UNCERTAINTY`) and falsification triggers.
- **Tier 2 (Mutual Fund Look-Through & Multi-Asset Matrix):** Ingesting mutual fund disclosures, corporate debt, REITs/InvITs, ETFs, and unlisted MSMEs to score assets based on forward-looking business quality, cash conversion, tax drag, and underlying exposures.
- **Tier 3 (Qualified Institutional Services):** Equipping professional investors, analysts, fund managers, institutional investors, RIAs, and serious individual investors with structured workflows, source traceability, and thesis monitoring.

## 5. Differential Tracking Engine
- **Append-Only Archiving:** Database rows are immutable; material events trigger new entries in `report_revisions`, preserving historical text and timestamps.
- **High-Value Correlations:** Compares historical snapshots to detect "Value Traps" (qualitative downgrades occurring alongside valuation expansions) and tracks Mutual Fund Style Drift over successive quarters.
