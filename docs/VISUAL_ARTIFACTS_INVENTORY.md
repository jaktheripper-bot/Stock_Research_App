# Moatnomics Visual Artifacts Inventory & Production Sheet (Assimilated with Visual Identity v2.0)

> **Reference Authority:** Aligned with [`docs/VISUAL_IDENTITY_AND_MOTION_GUIDE.md`](VISUAL_IDENTITY_AND_MOTION_GUIDE.md) (v2.0, 20 October 2026) and the three embedded reference boards extracted into `web/static/img/brand/references/`:
> - **Reference Board A (`ref_a_concept_and_visual_language.png`):** Approved **Perspective Portal** dimensional split-arch mark, 7-swatch palette, Tiempos Headline + Inter typography, and the 4 portal art plates (`DEPTH`, `PERSPECTIVE`, `CLARITY`, `OPPORTUNITY`).
> - **Reference Board B (`ref_b_logo_system_and_explorations.png`):** Minimum size / clear space mechanics and later explorations (*do not replace the dimensional split-arch with the perfect-semicircle revision*).
> - **Reference Board C (`ref_c_cross_channel_styleboard.png`):** Canonical 12-icon `24×24px` (`1.75–2px` stroke) vector system, mobile/desktop UI applications, report cover, social cards, and video storyboard.

> [!IMPORTANT]
> **Status on `main` @ `9aee965` (verified 20 Oct 2026).** Rows below still read "currently missing" or list emoji placeholders; they were written before commits `2b206e0`, `b413ed6` and `9aee965`. Actual state:
> - **Done, inlined as `<symbol>` sprites in `web/templates/base.html`:** flat/dimensional portal marks, 12 nav icons, 7 pillars, sector icons, 4 pricing tiers, 3 state diagrams (`vault-locked`, `dossier-pending`, `empty-search`), theme and reading-surface icons. The standalone `.svg` files under `img/nav|pillars|sectors|pricing` are not referenced by path.
> - **Files present, not wired into any template or CSS:** the 13 `img/heroes/hero-*.webp` banners, the 4 `img/brand/portal-*.webp` plates, `img/brand/og-default.png`, `img/brand/apple-touch-icon.png`.
> - **Not done:** `og:image` / `twitter:image` meta, `apple-touch-icon` link. Both are scheduled for Copy Wave 3a.
> - **Unreferenced files:** `img/ui/copilot-*.svg`, `img/ui/hud-*.svg` (the Research Desk uses sprite icons and, in `copilot.js`, some raw emojis).
> - **Cleanup pending:** legacy `glyph-castle` symbol (`base.html:110`) is defined but unused.
> - **Naming:** asset names containing off-voice terms (`hud-surveillance-satellite`, `copilot-premortem`, `copilot-bear-thesis`) are renamed with their matching copy wave, if they are ever wired up.

---

## 0. v2.0 Production Guardrails Before Generating Any Visuals

1. **Where Dimensional "Perspective Portal" Art Belongs vs. Where Flat Vector Is Mandatory:**
   - **Use Atmospheric Portal Art (`portal` variant):** Homepage hero, flagship campaign banners, report covers, the 4 brand manifesto plates (`DEPTH`, `PERSPECTIVE`, `CLARITY`, `OPPORTUNITY`), and section openers. These use the **Perspective Portal silhouette** (architectural split-arch with an angled inner perspective plane and a taller central vertical mirror prism) framing calm landscape or architectural photography graded toward **Forest (`#0E3D32`)**, **Ivory (`#F7F5EE`)**, and **Ink Navy (`#0B2337`)**.
   - **Use Flat Precision Vector SVGs (`flat` variant — DO NOT use AI raster scenes):** Logo masters, navigation icons, the 12 core research icons, the 7-pillar badges, the 10 sector badges, and dense UI controls. These must be clean `24×24px` (`1.75–2px` uniform stroke) single-colour vectors with **zero 3D coins, zero neon glows, and zero raw OS emojis**.
2. **Provisional Brand Palette (v2.0 Hex Tokens):**
   - **Forest:** `#0E3D32` (`RGB 14, 61, 50`) — Primary brand anchor, deep editorial header surface, primary light-mode action candidate.
   - **Sage:** `#7DA77A` (`RGB 125, 167, 122`) — Secondary brand tone, calm support accent, chart series.
   - **Lime:** `#C7E268` (`RGB 199, 226, 104`) — Controlled focal accent (`<5%` of viewport), dark-hero primary CTA button fill. *Never use as a large neon wash or automatic "profit" cue.*
   - **Ink Navy:** `#0B2337` (`RGB 11, 35, 55`) — Editorial authority, primary dark-mode canvas, light-mode headline ink, chart axes.
   - **Ivory:** `#F7F5EE` (`RGB 247, 245, 238`) — Warm editorial paper canvas, light-mode background, primary text on dark surfaces.
   - **Mist:** `#D9E3E8` (`RGB 217, 227, 232`) — Hairline dividers, neutral panels, secondary chart series.
   - **Charcoal:** `#282F33` (`RGB 40, 47, 51`) — Sustained reading body ink, dense table text, elevated dark card surface.
   - **White:** `#FFFFFF` (`RGB 255, 255, 255`) — Elevated card surface on Ivory, reverse text on dark surfaces.
3. **Canonical Asset Naming Convention (Section 19.2):**
   - Pattern: `brand_asset-purpose_variant_theme_locale_version_date.ext`
   - Example: `moatnomics_hero-home_portal_dark_en-IN_v01_20261020.webp`

---

## 1. Brand Identity, Perspective Portal Logo System & Social Cards (`web/static/img/brand/`)

> **Important Guardrail (Section 3.2 & 18.1):** Never use raster AI image generation as final logo masters. Produce all logo files as precision vector SVGs using the **approved earlier dimensional Perspective Portal** (split arch with inward-angled planes and taller central vertical mirror prism), plus flat and small-size derivatives.

| # | Artifact Name | Current Implementation | v2.0 Visual Specification | Recommended Specs | Web Drop-In Path & Canonical v2.0 Name |
|---|---|---|---|---|---|
| 1.1 | **Primary Dimensional Symbol ("The Perspective Portal")** | Inline `#glyph-castle` SVG inside a cyan-blue square (`base.html`) | Architectural split-arch with angled inner planes and a taller central vertical mirror prism in Forest (`#0E3D32`), Sage (`#7DA77A`), and Ivory (`#F7F5EE`) / Lime (`#C7E268`) highlight | Vector `.svg` + `512×512` `.webp` (min `36px` digital / `10mm` print) | `web/static/img/brand/logo-mark.svg`<br>`moatnomics_logo-symbol_dimensional_dark_en-IN_v01_20261020.svg` |
| 1.2 | **Flat & Small-Size Symbol Derivative** | *Currently missing* | Simplified flat 1-colour vector of the Perspective Portal with widened negative-space corridor for dense UI chrome (`16px–24px`) | Vector `.svg` (`16×16` / `24×24` optical grid) | `web/static/img/brand/logo-mark-flat.svg`<br>`moatnomics_logo-symbol_flat_mono_en-IN_v01_20261020.svg` |
| 1.3 | **Primary Horizontal Lockup** | HTML text `MOATNOMICS` + subtitle (`base.html`, `core/reporting/pdf.py`) | Symbol left + editorial serif `Moatnomics` wordmark right; include tagline *"Less noise, more nuance."* only at wide hero/cover sizes (`>=140px` digital / `30mm` print; omit tagline in compact nav) | `800×200` (4:1), Vector `.svg` + transparent `.png` (Light & Dark variants) | `web/static/img/brand/logo-wordmark.svg`<br>`moatnomics_logo-horizontal_dimensional_dark_en-IN_v01_20261020.svg` |
| 1.4 | **Stacked Lockup (Covers & Signage)** | *Currently missing* | Perspective Portal symbol centered above `Moatnomics` serif wordmark and *"Less noise, more nuance."* | `600×600` (1:1), Vector `.svg` | `web/static/img/brand/logo-stacked.svg`<br>`moatnomics_logo-stacked_dimensional_light_en-IN_v01_20261020.svg` |
| 1.5 | **Browser Favicon & App Icon** | Inline `data:image/svg+xml` castle path (`base.html`) | Simplified flat Perspective Portal symbol in Ivory (`#F7F5EE`) / Sage (`#7DA77A`) centered on a dark Forest (`#0E3D32`) or Ink Navy (`#0B2337`) rounded square | `64×64` `.ico`, `180×180` `apple-touch-icon.png`, `512×512` `.svg` | `web/static/img/brand/favicon.svg`<br>`web/static/img/brand/apple-touch-icon.png` |
| 1.6 | **Default OpenGraph / Social Share Card** | *Currently missing* (`og:image` absent in `base.html`) | Editorial card on Forest (`#0E3D32`) / Ink Navy (`#0B2337`) with dimensional Perspective Portal at left, Ivory (`#F7F5EE`) serif headline *"Less noise, more nuance."*, and subtitle *"Multi-asset investment research"* | `1200×630` (1.91:1), `.png` / `.webp` | `web/static/img/brand/og-default.png`<br>`moatnomics_social-og_portal_dark_en-IN_v01_20261020.png` |
| 1.7 | **Four Brand Manifesto Portal Plates (`DEPTH`, `PERSPECTIVE`, `CLARITY`, `OPPORTUNITY`)** | Extracted in `Reference Board A` (`ref_a_concept_and_visual_language.png`) | Architectural split-arch silhouette framing: (1) `DEPTH` — misty pine forest in Forest `#0E3D32`; (2) `PERSPECTIVE` — sunlit canyon stone prism; (3) `CLARITY` — calm horizon water in Ink Navy `#0B2337`; (4) `OPPORTUNITY` — cultivated valley ridge in Sage `#7DA77A` & Ivory `#F7F5EE` | `800×1000` (4:5) × 4 plates, `.webp` | `web/static/img/brand/portal-{depth,perspective,clarity,opportunity}.webp` |

---

## 2. Page Hero Banners & Section Openers (`web/static/img/heroes/`)

> **v2.0 Rule (Section 7.1 & 7.2):** Page hero banners and section openers are the **primary home for Perspective Portal artwork** (or restrained architectural photography graded toward `#0E3D32`, `#0B2337`, `#F7F5EE`, and `#7DA77A`). Keep one dominant perspective gesture per hero; never combine portal masks with busy floating 3D widgets or neon trading graphics.

| # | Page / Section | v2.0 Visual Direction (Portal / Editorial Frame) | Template Location | Recommended Specs | Target Filename & Canonical v2.0 Name |
|---|---|---|---|---|---|
| 2.1 | **Homepage Main Hero** | **Perspective Portal Hero:** Split-arch portal with central vertical mirror plane framing a calm, deep architectural/landscape horizon in Forest (`#0E3D32`), Ink Navy (`#0B2337`), and warm Ivory (`#F7F5EE`) light, expressing *"Less noise, more nuance."* | `web/templates/index.html` | `1600×900` (16:9) or `1000×800` portal plate | `web/static/img/heroes/hero-home.webp`<br>`moatnomics_hero-home_portal_dark_en-IN_v01_20261020.webp` |
| 2.2 | **Stock Discovery @9AM** | **Morning Horizon Portal:** Architectural arch framing crisp early-morning daylight breaking across structured geometric terraces in Ivory (`#F7F5EE`), Sage (`#7DA77A`), and Forest (`#0E3D32`) | `index.html`, `discovery.html` | `1200×400` (3:1) or `800×600` | `web/static/img/heroes/hero-discovery-9am.webp`<br>`moatnomics_hero-discovery_portal_dark_en-IN_v01_20261020.webp` |
| 2.3 | **Institutional Equities Directory** | **Equities Perspective Opener:** Clean architectural colonnade / structural perspective corridor in Ink Navy (`#0B2337`) and Mist (`#D9E3E8`) with subtle Sage (`#7DA77A`) depth plane | `equities_directory.html` | `1200×400` (3:1) | `web/static/img/heroes/hero-equities.webp`<br>`moatnomics_hero-equities_portal_dark_en-IN_v01_20261020.webp` |
| 2.4 | **Mutual Funds Look-Through & Overlap** | **Layered Glass / Prism Opener:** Translucent overlapping architectural planes in Forest (`#0E3D32`), Sage (`#7DA77A`), and Ivory (`#F7F5EE`) illustrating portfolio look-through and hidden overlap | `fund_directory.html`, `fund_overlap.html` | `1200×400` (3:1) | `web/static/img/heroes/hero-mutual-funds.webp`<br>`moatnomics_hero-funds_portal_dark_en-IN_v01_20261020.webp` |
| 2.5 | **National ETF Matrix** | **Parallel Corridor Opener:** Dual symmetrical architectural tracks meeting at a crisp horizon line in Ink Navy (`#0B2337`) and Mist (`#D9E3E8`), expressing index-tracking precision | `etf_matrix.html` | `1200×400` (3:1) | `web/static/img/heroes/hero-etf-matrix.webp`<br>`moatnomics_hero-etfs_portal_dark_en-IN_v01_20261020.webp` |
| 2.6 | **Bonds, NCDs & SDIs Directory** | **Structural Foundation Opener:** Monolithic stone/concrete load-bearing arches in Charcoal (`#282F33`), Forest (`#0E3D32`), and warm Ivory (`#F7F5EE`) light, expressing credit seniority and cash-flow coverage | `debt_directory.html` | `1200×400` (3:1) | `web/static/img/heroes/hero-corporate-debt.webp`<br>`moatnomics_hero-debt_portal_dark_en-IN_v01_20261020.webp` |
| 2.7 | **Sovereign Curve & RBI T-Bills** | **Stepped Terrace Horizon:** Calm stepped architectural terraces rising across a quiet horizon in Ink Navy (`#0B2337`), Sage (`#7DA77A`), and Ivory (`#F7F5EE`), expressing term-structure maturity | `sovereign_curve.html` | `1200×400` (3:1) | `web/static/img/heroes/hero-sovereign-curve.webp`<br>`moatnomics_hero-sovereign_portal_dark_en-IN_v01_20261020.webp` |
| 2.8 | **SM REITs, InvITs & Sovereign Gold** | **Real Assets Architecture:** High-contrast daylight across modern commercial structure, power grid geometry, and warm mineral tones graded into Forest (`#0E3D32`) and Ivory (`#F7F5EE`) | `reit_directory.html` | `1200×400` (3:1) | `web/static/img/heroes/hero-reits-gold.webp`<br>`moatnomics_hero-real-assets_portal_dark_en-IN_v01_20261020.webp` |
| 2.9 | **Opportunity Terminal** | **Opportunity Portal (`OPPORTUNITY` plate):** Split-arch portal framing cultivated valley ridges and distant sunlit peaks in Forest (`#0E3D32`), Sage (`#7DA77A`), and subtle Lime (`#C7E268`) focal light | `opportunity_terminal.html` | `1200×400` (3:1) | `web/static/img/heroes/hero-opportunity-terminal.webp`<br>`moatnomics_hero-opportunity_portal_dark_en-IN_v01_20261020.webp` |
| 2.10 | **Unlisted MSMEs & Industrial Clusters** | **Industrial Precision Architecture:** Clean geometric factory skylight bays and precision engineering lines graded in Ink Navy (`#0B2337`), Charcoal (`#282F33`), and Ivory (`#F7F5EE`) | `msme_directory.html` | `1200×400` (3:1) | `web/static/img/heroes/hero-msme-clusters.webp`<br>`moatnomics_hero-msme_portal_dark_en-IN_v01_20261020.webp` |
| 2.11 | **Retail Safety Radar** | **Structural Threshold / Fault-Line Study:** Sharp architectural shadow line separating solid stone foundation from unstable cantilever in Ink Navy (`#0B2337`), Charcoal (`#282F33`), and Mist (`#D9E3E8`) (*no alarmist skulls or sirens*) | `safety_radar.html` | `1200×400` (3:1) | `web/static/img/heroes/hero-safety-radar.webp`<br>`moatnomics_hero-safety-radar_portal_dark_en-IN_v01_20261020.webp` |
| 2.12 | **Peer Comparison Engine** | **Mirrored Dual-Arch Study (`PERSPECTIVE` plate):** Split-arch portal with central vertical mirror plane comparing two distinct architectural surfaces side-by-side | `compare.html` | `1200×400` (3:1) | `web/static/img/heroes/hero-peer-compare.webp`<br>`moatnomics_hero-compare_portal_dark_en-IN_v01_20261020.webp` |
| 2.13 | **Net Real Tax & CPI Deflator Calculator** | **Nominal vs. Real Strata Layering:** Clean horizontal geological/architectural strata showing gross surface height versus net real retained layer in Forest (`#0E3D32`), Sage (`#7DA77A`), and Mist (`#D9E3E8`) | `tax_calculator.html` | `1200×400` (3:1) | `web/static/img/heroes/hero-tax-calculator.webp`<br>`moatnomics_hero-tax-deflator_portal_dark_en-IN_v01_20261020.webp` |

---

## 3. Canonical 12-Icon Research System (`24×24px` Vector Grid — `web/static/img/nav/` & `ui/`)

> **v2.0 Rule (Section 7.5 & Reference Board C):** All functional icons must be built on a **`24×24px` master grid** (`16×16px` compact, `32×32px` feature) with a **`1.75px–2px` uniform stroke**, rounded caps, slightly softened joins, and single-colour fill/stroke in Ink Navy (`#0B2337`), Ivory (`#F7F5EE`), Forest (`#0E3D32`), or Sage (`#7DA77A`). **Replace all raw OS emojis (`📈`, `🌱`, `🏷️`, `🌐`, `🏢`, `🎯`, `🏭`, `🌅`, `🧮`, `🎧`, `📑`, `🔒`).**

| # | Canonical v2.0 Icon Name | Approved Visual Metaphor (Board C) | Where It Maps in the App | Target Vector Path & Canonical Name |
|---|---|---|---|---|
| 3.1 | **Research** | Document page with top-right corner fold and magnifying lens | Dossiers, Research Tools menu, Evidence Register | `web/static/img/nav/icon-research.svg`<br>`moatnomics_icon-research_flat_mono_en-IN_v01_20261020.svg` |
| 3.2 | **Markets** | Three ascending vertical bars on a clean horizontal baseline | Equities Directory, Markets menu (`📈` replacement) | `web/static/img/nav/icon-markets.svg`<br>`moatnomics_icon-markets_flat_mono_en-IN_v01_20261020.svg` |
| 3.3 | **Compare** | Two overlapping Venn circles (or dual calibration sliders) | Peer Comparison (`compare.html`), Fund Overlap (`fund_overlap.html`) | `web/static/img/nav/icon-compare.svg`<br>`moatnomics_icon-compare_flat_mono_en-IN_v01_20261020.svg` |
| 3.4 | **Watchlist** | Clean vertical ribbon bookmark outline | Watchlist buttons, tracked theses, saved screens | `web/static/img/nav/icon-watchlist.svg`<br>`moatnomics_icon-watchlist_flat_mono_en-IN_v01_20261020.svg` |
| 3.5 | **Insights** | Minimalist geometric lightbulb with filament line | Morning Discovery @9AM (`🌅` replacement), Short-Form Insights | `web/static/img/nav/icon-insights.svg`<br>`moatnomics_icon-insights_flat_mono_en-IN_v01_20261020.svg` |
| 3.6 | **Portfolio** | Circular pie chart with clean offset upper-right quadrant | Mutual Funds Directory, Asset Allocation views | `web/static/img/nav/icon-portfolio.svg`<br>`moatnomics_icon-portfolio_flat_mono_en-IN_v01_20261020.svg` |
| 3.7 | **Risk** | Geometric shield outline with internal check or structural line | Retail Safety Radar, Governance & Forensic checks, Risk Pillar | `web/static/img/nav/icon-risk.svg`<br>`moatnomics_icon-risk_flat_mono_en-IN_v01_20261020.svg` |
| 3.8 | **Valuation** | Three horizontal calibration sliders / balance beam | Valuation Pillar (`🏷️` replacement), Reverse DCF, Tax Calculator (`🧮`) | `web/static/img/nav/icon-valuation.svg`<br>`moatnomics_icon-valuation_flat_mono_en-IN_v01_20261020.svg` |
| 3.9 | **Multi-Asset** | Three stacked isometric diamond planes | ETFs (`🌐`), Bonds/NCDs, Sovereign Curve, REITs/InvITs (`🏢`), MSMEs (`🏭`) | `web/static/img/nav/icon-multi-asset.svg`<br>`moatnomics_icon-multi-asset_flat_mono_en-IN_v01_20261020.svg` |
| 3.10 | **Screen** | `2×2` modular square grid | Opportunity Terminal (`🎯` replacement), Multi-pillar screener filters | `web/static/img/nav/icon-screen.svg`<br>`moatnomics_icon-screen_flat_mono_en-IN_v01_20261020.svg` |
| 3.11 | **Alerts** | Clean notification bell / thesis-change pulse | Autonomous Surveillance feed (`🛰️` replacement), Monitoring triggers | `web/static/img/nav/icon-alerts.svg`<br>`moatnomics_icon-alerts_flat_mono_en-IN_v01_20261020.svg` |
| 3.12 | **Download** | Downward arrow into horizontal tray | PDF Dossier export (`core/reporting/pdf.py`), CSV/data export | `web/static/img/nav/icon-download.svg`<br>`moatnomics_icon-download_flat_mono_en-IN_v01_20261020.svg` |

---

## 4. The 7-Pillar Institutional Health Matrix (`web/static/img/pillars/`)

> **v2.0 Rule:** In `index.html` and `dossier.html`, 3 pillars currently use raw emojis (`🌱`, `🏷️`, `📈`). All 7 pillars must use a unified `24×24px` / `32×32px` (`1.75–2px` stroke) architectural vector icon set in Forest (`#0E3D32`) / Sage (`#7DA77A`) / Ivory (`#F7F5EE`).

| Pillar # | Title | Current Placeholder | v2.0 Vector Icon Metaphor (`24×24` / `32×32` SVG) | Target Filename |
|---|---|---|---|---|
| **Pillar 01** | Business Model & Moat | `#glyph-castle` SVG | Architectural split-arch threshold / protective concentric moat rings | `web/static/img/pillars/pillar-01-moat.svg` |
| **Pillar 02** | Capital Allocation | `#glyph-scale` SVG | Precision fulcrum balance beam comparing ROCE vs. cost of capital | `web/static/img/pillars/pillar-02-capital.svg` |
| **Pillar 03** | Financial Health & Solvency | `#glyph-chart` SVG | Structural load-bearing column with cash-flow reserve baseline | `web/static/img/pillars/pillar-03-solvency.svg` |
| **Pillar 04** | Growth Drivers & Industry | `🌱` Emoji | Expanding concentric horizon arcs / ascending structural step line | `web/static/img/pillars/pillar-04-growth.svg` |
| **Pillar 05** | Valuation & Margin of Safety | `🏷️` Emoji | Horizontal valuation range bar with intrinsic value caliper markers (`Valuation` icon) | `web/static/img/pillars/pillar-05-valuation.svg` |
| **Pillar 06** | Technicals & Momentum | `📈` Emoji | Clean price series line crossing a horizontal moving-average reference band | `web/static/img/pillars/pillar-06-technicals.svg` |
| **Pillar 07** | Governance & Forensic Cleanliness | `#glyph-shield` SVG | Document page inspected by a geometric shield / magnifying lens (`Risk` + `Research`) | `web/static/img/pillars/pillar-07-governance.svg` |

---

## 5. Equity Sector Taxonomy Badges (`web/static/img/sectors/`)

> **v2.0 Rule:** Defined in `SECTOR_TAXONOMY` (`core/db/reports.py`) and rendered on every stock card and filter pill in `index.html` and `equities_directory.html`. Currently 100% raw emojis. Replace with `24×24px` (`1.75–2px` stroke) monochrome vector SVGs so dense directory views remain flat, calm, and institutional.

| Sector Key | Label | Current Emoji | v2.0 Vector Icon Metaphor (`24×24` SVG) | Target Filename |
|---|---|---|---|---|
| `IT_TECH` | IT & Technology | `💻` | Circuit node / terminal bracket glyph | `web/static/img/sectors/sector-it-tech.svg` |
| `BFSI` | BFSI & Financials | `🏛️` | Classical institutional lintel & three columns | `web/static/img/sectors/sector-bfsi.svg` |
| `HEALTHCARE_PHARMA` | Healthcare & Pharma | `🔬` | Precision laboratory flask / molecular hexagon | `web/static/img/sectors/sector-healthcare.svg` |
| `CAPITAL_GOODS_INFRA` | Capital Goods & Infra | `⚙️` | Structural truss bridge / precision gear outline | `web/static/img/sectors/sector-capital-goods.svg` |
| `AUTOMOTIVE` | Automotive & Mobility | `🚗` | Streamlined axle / wheel-and-chassis profile | `web/static/img/sectors/sector-automotive.svg` |
| `CONSUMER_FMCG` | Consumer & Retail | `🛍️` | Clean geometric parcel / retail tote outline | `web/static/img/sectors/sector-consumer.svg` |
| `CHEMICALS_MATERIALS` | Chemicals & Materials | `🧪` | Bonded lattice structure / retort vessel | `web/static/img/sectors/sector-chemicals.svg` |
| `COMMODITIES_ENERGY` | Energy & Commodities | `⚡` | High-voltage transmission tower / energy wave | `web/static/img/sectors/sector-energy.svg` |
| `EMS_DEFENCE` | EMS & Defence | `🛡️` | Radar sweep arc inside octagonal shield | `web/static/img/sectors/sector-defence.svg` |
| `DIVERSIFIED` | Diversified Industrials | `🏭` | Modular multi-unit industrial grid (`2×2` / sawtooth roof) | `web/static/img/sectors/sector-diversified.svg` |

---

## 6. Research Desk Modals, Empty States & Editorial Containers (`web/static/img/ui/` & `pricing/`)

> **v2.0 Rule (Section 3.3 & 7.5):** Avoid theatrical skulls (`💀`), cartoon bears (`🐻`), explosions (`💥`), or 3D gold coins (`#glyph-coin`) in the research interface. Use restrained geometric vector glyphs (`24×24px` or `48×48px`) in Ink Navy (`#0B2337`), Forest (`#0E3D32`), Sage (`#7DA77A`), and Ivory (`#F7F5EE`).

| # | Component / State | Current Placeholder | Template / JS Location | v2.0 Visual Treatment | Target Filename |
|---|---|---|---|---|---|
| 6.1 | **Research Desk Header Mark** | `#glyph-shield` inside `.copilot-avatar-ring` | `copilot_modal.html` | Flat **Perspective Portal** symbol (`24×24px` SVG) on Forest (`#0E3D32`) badge | `web/static/img/ui/copilot-avatar.svg` |
| 6.2 | **Countercase / Pre-Mortem Prompt Icon** | `💀` Emoji | `copilot_modal.html`, `copilot.js` | Split-mirror prism icon (representing countercase / inverted assumption, *never a skull*) | `web/static/img/ui/copilot-premortem.svg` |
| 6.3 | **Downside Stress-Test Prompt Icon** | `🐻` / `💥` Emoji | `copilot_modal.html` | Downward sensitivity range bar with threshold line (*never a cartoon bear or explosion*) | `web/static/img/ui/copilot-bear-thesis.svg` |
| 6.4 | **Implied Expectations (Reverse DCF) Icon** | `📉` Emoji | `copilot_modal.html` | Calibration slider / equilibrium fulcrum glyph | `web/static/img/ui/copilot-reverse-dcf.svg` |
| 6.5 | **Governance & Accounting Check Icon** | `🚩` Emoji | `copilot_modal.html` | Document with footnote callout marker | `web/static/img/ui/copilot-governance-flag.svg` |
| 6.6 | **Dossier Synthesis Progress Mark** | Spinning `#glyph-shield` in `#synthesizingOverlay` | `base.html` | **4-Beat Perspective Portal SVG** (outer arch -> inner mirror plane -> calm pulse, `700–1200ms`, respecting `prefers-reduced-motion`) | `web/static/img/ui/hud-synthesizing.svg` |
| 6.7 | **Thesis Monitoring Feed Icon** | `🛰️` Emoji in `#surveillanceModal` | `base.html` | Canonical **Alerts / Watchpoint** vector icon (`24×24px`) | `web/static/img/ui/hud-surveillance-satellite.svg` |
| 6.8 | **Locked Dossier Section Card** | `🔒` Emoji + dashed border box | `asset_unlock_card.html`, `dossier.html` | Minimalist architectural keyhole / portal threshold diagram (`400×240` SVG) in Forest (`#0E3D32`) and Mist (`#D9E3E8`) | `web/static/img/ui/state-vault-locked.svg` |
| 6.9 | **Pending Dossier Compilation State** | `#glyph-zap` / `#glyph-bank` | `dossier_pending.html` | Clean multi-step evidence assembly diagram (`Context -> Evidence -> Implication`) in Sage (`#7DA77A`) and Ivory (`#F7F5EE`) | `web/static/img/ui/state-dossier-pending.svg` |
| 6.10 | **Zero Search / Filter Matches State** | 48px `#glyph-search` SVG | `index.html`, `equities_directory.html`, `search_results.html` | Restrained `48×48px` architectural grid + magnifier outline in Mist (`#D9E3E8`) | `web/static/img/ui/state-empty-search.svg` |
| 6.11 | **Pricing & Access Tier Marks (4 Tiers)** | `#glyph-coin` SVG & `⭐` emoji | `index.html`, `pricing.html` | 4 geometric progression marks (Single arch, Dual arch, Matrix grid, Full Perspective Portal prism — *no 3D coins*) | `web/static/img/pricing/tier-{single,3pack,10pack,pro}.svg` |

---

## 7. Ready-to-Use External Generation Prompts (Aligned with Reference Boards A–C)

### A. Prompt Template for Hero / Section Opener Portal Art (Midjourney / Flux / Image Generators)
> **Use ONLY for Section 1.7 (Manifesto Plates) and Section 2 (Hero Banners / Report Covers).**
>
> *"Minimalist editorial brand artwork for Moatnomics ('Less noise, more nuance'). Central architectural split-arch portal silhouette with inward-angled perspective planes and a taller central vertical mirror prism, inspired by quiet museum architecture. Inside the arch, frame [SUBJECT: e.g., misty deep pine forest valley / sunlit terraced stone canyon / calm horizon water / modern infrastructure geometry]. Colour palette strictly graded to deep Forest green (`#0E3D32`), Ink Navy (`#0B2337`), muted Sage (`#7DA77A`), and warm Ivory paper (`#F7F5EE`), with at most a tiny hairline accent of muted Lime (`#C7E268`). Clean negative space around the portal, calm institutional editorial mood, zero text, zero neon glow, zero 3D coins, zero sci-fi HUD elements."*

### B. Specification for Vector Logo & `24×24px` Icon Production (Figma / Illustrator / SVG Generator)
> **Use for Sections 1.1–1.5 (Perspective Portal Logos) and Sections 3–6 (UI Icons, Pillars, Sectors).**
>
> - **Canvas:** `24×24px` (`2px` live padding), `1.75px` or `2.0px` uniform stroke, `stroke-linecap="round"`, `stroke-linejoin="round"`, `fill="none"`.
> - **Colour:** `currentColor` so CSS can bind `--text-primary` (`#0B2337` on Ivory light mode; `#F7F5EE` on Ink Navy dark mode) or `--brand-sage` (`#7DA77A`).
> - **Prohibitions:** No gradients inside `24×24px` icons, no drop shadows, no rasterized PNGs for UI glyphs, and no replacement of the dimensional split-arch Perspective Portal with a plain semicircle.
