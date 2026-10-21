# Moatnomics Visual Artifacts Inventory, Accent Palette & External Production Blueprint

> **Document Status:** Revised & Synchronized with Active Production (`f5d7606`, 21 October 2026).  
> **Master Reference Authority:** [`docs/MASTER_ENGINEERING_MANUAL.md`](MASTER_ENGINEERING_MANUAL.md) & [`core/brand/visual_identity.py`](../core/brand/visual_identity.py).  
> **Target Production Workflow:** External design generation (Figma / Illustrator / Midjourney / Flux) -> Direct folder placement (`web/static/img/brand/`, `web/static/img/nav/`, `web/static/img/pillars/`, `web/static/img/sectors/`, `web/static/img/heroes/`, `web/static/img/pricing/`, `web/static/img/ui/`).

---

## 1. Executive Summary & Brand Foundation

The Moatnomics platform operates as a quiet, authoritative, institutional research instrument. The visual identity rejects speculative retail aesthetics (no neon gradients, no cartoon icons, no 3D gold coins, no floating hype badges). Every asset must adhere to the **Moatnomics Dimensional Perspective Portal** visual system and the **9-Asset-Class Curated Palette**.

### 1.1 Canonical Brand Palette

| Token | Role / Placement | Light / Warm Ivory Mode | Dark / Carbon Mode |
|---|---|---|---|
| **Canvas Background** | Page background | `#F7F5EE` (Warm Ivory) | `#09090B` (True Carbon Black) |
| **Card Surface** | Snapshot Biscuit Cards, Tables | `#FFFFFF` (Pure Crisp White) | `#141418` (Carbon Slate) |
| **Elevated Surface** | Popovers, Hover states, Drawers | `#FFFFFF` | `#1C1C22` (High Carbon) |
| **Primary Ink** | Headings, Titles, Hero Copy | `#0B2337` (Deep Ink Navy) | `#FAFAFA` (Pure White) |
| **Body Ink** | Sustained analysis prose | `#282F33` (Charcoal Slate) | `#D4D4D8` (Muted Zinc) |
| **Brand Anchor** | Primary buttons, headers, borders | `#0E3D32` (Moatnomics Forest) | `#0E3D32` / `#86EFAC` |
| **Brand Support** | Calming accents, chart series | `#7DA77A` (Sage Green) | `#7DA77A` (Sage) |
| **Hairline Dividers** | Card borders, structural rules | `#DCD6C6` (Ivory Border) | `#27272A` (Dark Border) |

---

## 2. The 9 Multi-Asset Section Accent Color System

Every asset class has a dedicated **Editorial Light Accent** (for the Warm Ivory `#F7F5EE` canvas) and a corresponding **Luminous Dark Accent** (tested for $\ge 4.5:1$ contrast against Carbon `#09090B`).

When icons are generated with hardcoded accent strokes (or layered two-tone fills), they **MUST** use these exact color values matching their asset domain:

| Asset Class / Domain | Key Directory / Route | Light Mode Accent (`--asset-accent`) | Dark Mode Luminous Accent | Visual Metaphor / Theme |
|---|---|---|---|---|
| **1. Listed Equities** | `/equities`, `/dossier/{ticker}` | `#0E3D32` (Moatnomics Forest) | `#86EFAC` (Luminous Sage) | Institutional Colonnade, Growth & Moats |
| **2. Mutual Funds** | `/funds`, `/funds/{code}` | `#1B5678` (Deep Blue Sapphire) | `#7DD3FC` (Cyan Sky) | Portfolio Overlap, Prismatic Look-Through |
| **3. National ETFs** | `/etfs`, `/etfs/{symbol}` | `#14635F` (Deep Emerald Teal) | `#5EEAD4` (Luminous Mint) | Parallel Index Corridors, Zero Drag |
| **4. Corporate Debt & SDIs** | `/debt`, `/debt/{isin}` | `#9A5812` (Amber Bronze) | `#FCD34D` (Luminous Gold) | Structural Beams, Seniority & Recourse |
| **5. Sovereign Curve & T-Bills** | `/sovereign` | `#3B407A` (Imperial Indigo) | `#A5B4FC` (Luminous Lavender)| Term Structure Terraces, Sovereign Faith |
| **6. REITs, InvITs & SGBs** | `/reits`, `/reits/{symbol}` | `#964325` (Terracotta Rust) | `#FDBA74` (Luminous Peach)| Real Assets, Grid Pylons & Gold Bullion |
| **7. Opportunity Terminal** | `/opportunities` | `#682A63` (Amethyst Plum) | `#E879F9` (Luminous Violet) | Cross-Asset Mispricing & Dispersion |
| **8. Unlisted MSMEs** | `/msme`, `/msme/{uin}` | `#6B442A` (Industrial Bronze) | `#F472B6` (Luminous Rose)| Industrial Engineering, Balance Sheets |
| **9. Retail Safety Radar** | `/safety-radar` | `#9F1239` (Crimson Carmine) | `#FDA4AF` (Luminous Coral) | Structural Fault Lines, Asymmetric Risk |

---

## 3. Directory Placement & Production Specifications

When generating files externally, save them directly to the corresponding folders with the exact filenames listed below. The application server will serve them immediately upon replacement.

### 3.1 Folder Structure Overview
```
web/static/img/
├── brand/        <- Logo system, brand manifesto plates, favicons, OG social cards
├── nav/          <- Canonical 12-icon navigation and action system (24x24 vector SVGs)
├── pillars/      <- The 7-Pillar Health Matrix badges (24x24 / 32x32 vector SVGs)
├── sectors/      <- 10 Equity Sector Taxonomy badges (24x24 vector SVGs)
├── pricing/      <- 4 Access / Subscription Tier marks (32x32 vector SVGs)
├── ui/           <- Empty states, locked vault, modal illustrations (vector SVGs)
└── heroes/       <- Editorial banners and perspective plates (WebP format)
```

---

## 4. Section-by-Section Production Specifications

### 4.1 Brand Identity & Perspective Portal Logo System (`web/static/img/brand/`)

> **Metaphor:** The **Perspective Portal** is an architectural split-arch featuring inward-angled planes that converge on a taller central vertical mirror prism.
> **Coloring:** Primary left arch in Forest (`#0E3D32`), right arch in Sage (`#7DA77A`), with inner faceted planes in Mist/Ivory (`#D9E3E8` / `#F7F5EE`).

| File Path | Dimensions | Format | Requirements |
|---|---|---|---|
| `web/static/img/brand/logo-mark.svg` | `512×512` | SVG | Canonical 3D dimensional split-arch Perspective Portal symbol. Crisp vector paths. |
| `web/static/img/brand/logo-mark-flat.svg` | `24×24` & `48×48` | SVG | Simplified 1-color flat silhouette with widened corridor for dense UI placement. |
| `web/static/img/brand/logo-wordmark.svg` | `800×200` (4:1) | SVG | Perspective Portal symbol at left + editorial serif `Moatnomics` wordmark in Deep Ink Navy (`#0B2337`). |
| `web/static/img/brand/logo-stacked.svg` | `600×600` (1:1) | SVG | Centered Perspective Portal symbol above `Moatnomics` wordmark and tagline *"Less noise, more nuance."*. |
| `web/static/img/brand/favicon.svg` | `32×32` / `64×64` | SVG | Simplified flat Portal mark with high-contrast Ivory/Sage geometry for browser tabs. |
| `web/static/img/brand/favicon-32x32.png` | `32×32` | PNG | 32-bit transparent PNG, 4x super-sampled. |
| `web/static/img/brand/favicon-64x64.png` | `64×64` | PNG | 32-bit transparent PNG, 4x super-sampled. |
| `web/static/img/brand/apple-touch-icon.png` | `180×180` | PNG | Perspective Portal symbol centered on Forest (`#0E3D32`) rounded background. |
| `web/static/img/brand/og-default.png` | `1200×630` | PNG | Editorial social share card. Warm Ivory canvas with Forest/Sage portal artwork, serif typography. |
| `web/static/img/brand/portal-depth.webp` | `800×1000` (4:5) | WebP | Brand Manifesto Plate 1 (`DEPTH`): Misty pine forest valley framed through split arch. |
| `web/static/img/brand/portal-perspective.webp` | `800×1000` (4:5) | WebP | Brand Manifesto Plate 2 (`PERSPECTIVE`): Sunlit terraced stone canyon with vertical mirror prism. |
| `web/static/img/brand/portal-clarity.webp` | `800×1000` (4:5) | WebP | Brand Manifesto Plate 3 (`CLARITY`): Calm horizon water in deep Ink Navy and warm daylight. |
| `web/static/img/brand/portal-opportunity.webp` | `800×1000` (4:5) | WebP | Brand Manifesto Plate 4 (`OPPORTUNITY`): Cultivated valley ridges under Sage Green and Ivory light. |

---

### 4.2 Canonical 12-Icon Research System (`web/static/img/nav/`)

> **Master Grid:** `24×24px` viewport with `2px` live boundary padding (`20×20px` active artboard).  
> **Stroke Weight:** `1.85px` uniform stroke, `stroke-linecap="round"`, `stroke-linejoin="round"`, `fill="none"`.  
> **Color:** Master files should use `stroke="currentColor"` so CSS dynamically applies `--asset-accent`. If generating colored editions, use the specified Accent Colors below.

| File Path | Icon Key | Applied Accent Color (Light Mode) | Approved Visual Metaphor |
|---|---|---|---|
| `web/static/img/nav/icon-research.svg` | `research` | `#0E3D32` (Moatnomics Forest) | Dossier document with folded corner and precision lens. |
| `web/static/img/nav/icon-markets.svg` | `markets` | `#0E3D32` (Moatnomics Forest) | Three ascending analytical columns on a grounded horizontal baseline. |
| `web/static/img/nav/icon-portfolio.svg` | `portfolio` | `#1B5678` (Deep Blue Sapphire) | Circular pie chart with offset top-right quadrant (Mutual Funds look-through). |
| `web/static/img/nav/icon-multi-asset.svg`| `multi-asset` | `#14635F` (Emerald Teal) | Three stacked isometric diamond planes (ETFs, Cross-Asset Setu). |
| `web/static/img/nav/icon-risk.svg` | `risk` | `#9A5812` (Amber Bronze) | Geometric shield outline with internal structural load-bearing bar (Debt/Credit). |
| `web/static/img/nav/icon-valuation.svg` | `valuation` | `#3B407A` (Imperial Indigo) | Precision calibration sliders / fulcrum balance beam (Sovereign & Reverse DCF). |
| `web/static/img/nav/icon-compare.svg` | `compare` | `#682A63` (Amethyst Plum) | Two overlapping intersecting elliptical rings (Pairwise & Overlap engine). |
| `web/static/img/nav/icon-screen.svg` | `screen` | `#682A63` (Amethyst Plum) | Clean 2x2 modular matrix grid with active crosshair marker. |
| `web/static/img/nav/icon-insights.svg` | `insights` | `#6B442A` (Industrial Bronze) | Geometric filament beacon / morning horizon lightbulb (MSME & 9AM Discovery). |
| `web/static/img/nav/icon-alerts.svg` | `alerts` | `#9F1239` (Crimson Carmine) | Notification bell with dynamic thesis-change wave (Safety Radar & Watchpoints). |
| `web/static/img/nav/icon-watchlist.svg`| `watchlist` | `#7DA77A` (Sage Green) | Crisp vertical bookmark ribbon with notched lower edge. |
| `web/static/img/nav/icon-download.svg` | `download` | `#0B2337` (Deep Ink Navy) | Downward directional arrow docking into an institutional horizontal tray. |

---

### 4.3 The 7-Pillar Institutional Health Matrix (`web/static/img/pillars/`)

> **Master Grid:** `24×24px` and `32×32px`. Uniform `1.85px–2.0px` stroke.  
> **Application:** Embedded on equity dossiers, homepage methodology showcases, and PDF reports.

| File Path | Pillar Domain | Accent Color | Visual Metaphor |
|---|---|---|---|
| `web/static/img/pillars/pillar-01-moat.svg` | **P1: Business Model & Moat** | `#0E3D32` (Forest) | Concentric protective moat rings surrounding a fortified portal threshold. |
| `web/static/img/pillars/pillar-02-capital.svg` | **P2: Capital Allocation & ROCE** | `#1B5678` (Blue) | Precision fulcrum balance comparing ROCE against WACC hurdle rate. |
| `web/static/img/pillars/pillar-03-solvency.svg` | **P3: Financial Health & Solvency**| `#9A5812` (Amber) | Load-bearing classical column with structural cash reserve base. |
| `web/static/img/pillars/pillar-04-growth.svg` | **P4: Growth Drivers & Industry** | `#7DA77A` (Sage) | Expanding concentric horizon arcs with an upward trajectory vector. |
| `web/static/img/pillars/pillar-05-valuation.svg` | **P5: Valuation & Margin of Safety**| `#3B407A` (Indigo) | Intrinsic value caliper brackets measuring CMP vs Fair Value band. |
| `web/static/img/pillars/pillar-06-technicals.svg`| **P6: Technicals & Momentum** | `#14635F` (Teal) | Clean price series line intersecting a 50-DMA horizontal reference band. |
| `web/static/img/pillars/pillar-07-governance.svg`| **P7: Forensic & Accounting Health**| `#9F1239` (Carmine) | Audited financial ledger inspected by a forensic magnifying shield. |

---

### 4.4 Equity Sector Taxonomy Badges (`web/static/img/sectors/`)

> **Master Grid:** `24×24px` vector SVG, single-color stroke with `1.85px` line weight.  
> **Requirement:** Replaces all legacy OS emojis (`💻`, `🏛️`, `🔬`, `⚙️`, `🚗`, `🛍️`, `🧪`, `⚡`, `🛡️`, `🏭`).

| File Path | Sector Key | Assigned Domain Color | Visual Metaphor |
|---|---|---|---|
| `web/static/img/sectors/sector-it-tech.svg` | `IT_TECH` | `#1B5678` (Deep Blue) | Circuit node with binary terminal brackets. |
| `web/static/img/sectors/sector-bfsi.svg` | `BFSI` | `#0E3D32` (Forest) | Institutional lintel with three classical ionic columns. |
| `web/static/img/sectors/sector-healthcare.svg` | `HEALTHCARE_PHARMA` | `#14635F` (Teal) | Laboratory beaker with a bonded molecular hexagon. |
| `web/static/img/sectors/sector-capital-goods.svg`| `CAPITAL_GOODS_INFRA` | `#9A5812` (Bronze) | Heavy industrial bridge truss with precision gear teeth. |
| `web/static/img/sectors/sector-automotive.svg` | `AUTOMOTIVE` | `#6B442A` (Steel Bronze) | Streamlined vehicle aerodynamic profile and wheel hub. |
| `web/static/img/sectors/sector-consumer.svg` | `CONSUMER_FMCG` | `#964325` (Terracotta) | Geometric packaged goods silhouette with clean seal ribbon. |
| `web/static/img/sectors/sector-chemicals.svg` | `CHEMICALS_MATERIALS` | `#682A63` (Plum) | Bonded crystal lattice structure and retort flask. |
| `web/static/img/sectors/sector-energy.svg` | `COMMODITIES_ENERGY` | `#3B407A` (Indigo) | High-voltage transmission pylon with energy impulse wave. |
| `web/static/img/sectors/sector-defence.svg` | `EMS_DEFENCE` | `#0B2337` (Ink Navy) | Octagonal shield featuring radar sweep crosshair lines. |
| `web/static/img/sectors/sector-diversified.svg` | `DIVERSIFIED` | `#282F33` (Charcoal) | Multi-bay industrial sawtooth facility with twin chimneys. |

---

### 4.5 Subscription & Access Tier Badges (`web/static/img/pricing/`)

> **Master Grid:** `32×32px` SVG vector glyphs. Clean geometric progressions, zero 3D gold coins.

| File Path | Tier | Color | Visual Metaphor |
|---|---|---|---|
| `web/static/img/pricing/tier-single.svg` | **Single Dossier** | `#1B5678` | Minimalist monolithic single archway. |
| `web/static/img/pricing/tier-3pack.svg` | **3-Dossier Pack** | `#14635F` | Dual interlocking geometric perspective arches. |
| `web/static/img/pricing/tier-10pack.svg` | **10-Dossier Pack** | `#9A5812` | Expanded 3x3 matrix grid with highlighted focal cell. |
| `web/static/img/pricing/tier-pro.svg` | **Annual Pro Allocator** | `#0E3D32` / `#7DA77A` | Full Perspective Portal architectural prism with central reflective axis. |

---

### 4.6 UI States & Editorial Empty Illustrations (`web/static/img/ui/`)

> **Dimensions:** `400×240px` (or `240×240px` square). Clean architectural line work.

| File Path | State / Feature | Palette | Visual Metaphor |
|---|---|---|---|
| `web/static/img/ui/state-vault-locked.svg` | **Locked Deep-Dive Section** | `#0E3D32` + `#DCD6C6` | Perspective Portal gateway with subtle geometric lock tumbler. |
| `web/static/img/ui/state-dossier-pending.svg` | **Synthesis in Progress** | `#1B5678` + `#7DA77A` | Multi-step evidence assembly diagram (`Context → Evidence → Implication`). |
| `web/static/img/ui/state-empty-search.svg` | **Zero Matching Filters** | `#282F33` + `#D9E3E8` | Architectural quadrant grid under an offset magnifying aperture. |

---

### 4.7 Page Hero Banners & Section Openers (`web/static/img/heroes/`)

> **Format:** WebP, `1600×540px` (3:1 aspect ratio) or `1200×400px`.  
> **Art Direction:** Quiet architectural and geological photography framed within the Perspective Portal split-arch. Natural light, subtle mist, graded strictly into the asset class accent colors.

| File Path | Route | Domain Color | Visual Art Brief |
|---|---|---|---|
| `web/static/img/heroes/hero-home.webp` | `/` (Home) | `#0E3D32` & `#F7F5EE` | Split-arch Perspective Portal framing a deep dawn pine horizon with quiet morning light. |
| `web/static/img/heroes/hero-equities.webp` | `/equities` | `#0E3D32` (Forest) | Minimalist colonnade corridor extending into a calm perspective horizon. |
| `web/static/img/heroes/hero-mutual-funds.webp` | `/funds` | `#1B5678` (Blue) | Overlapping translucent glass planes capturing morning light (portfolio look-through). |
| `web/static/img/heroes/hero-etf-matrix.webp` | `/etfs` | `#14635F` (Teal) | Symmetrical geometric railway corridor meeting at an exact optical vanishing point. |
| `web/static/img/heroes/hero-corporate-debt.webp`| `/debt` | `#9A5812` (Amber) | Heavy stone load-bearing arches and cantilevered bridge foundations. |
| `web/static/img/heroes/hero-sovereign-curve.webp`| `/sovereign`| `#3B407A` (Indigo) | Stepped granite terraces rising across a quiet mist horizon (yield curve term structure). |
| `web/static/img/heroes/hero-reits-gold.webp` | `/reits` | `#964325` (Terracotta) | Modern commercial facade geometry paired with warm mineral gold textures. |
| `web/static/img/heroes/hero-opportunity-terminal.webp` | `/opportunities` | `#682A63` (Plum) | Distant sunlit mountain ridges framed through an inward-angled portal arch. |
| `web/static/img/heroes/hero-msme-clusters.webp` | `/msme` | `#6B442A` (Bronze) | Precision factory skylights and industrial machining geometry. |
| `web/static/img/heroes/hero-safety-radar.webp` | `/safety-radar` | `#9F1239` (Carmine) | Clear architectural shadow line between a solid foundation and an ungrounded ledge. |
| `web/static/img/heroes/hero-peer-compare.webp` | `/compare` | `#682A63` (Plum) | Mirrored dual arches comparing two distinct architectural stone surfaces side-by-side. |
| `web/static/img/heroes/hero-tax-calculator.webp`| `/calculator/tax` | `#0E3D32` & `#7DA77A` | Horizontal layered geological strata comparing gross height vs. net preserved layer. |
| `web/static/img/heroes/hero-discovery-9am.webp` | `/discovery` | `#7DA77A` (Sage) | Early morning sunlight breaking over structured agricultural terraces. |

---

## 5. Generator Prompts for External Production

### 5.1 Flux / Midjourney Prompt (Hero Banners & Portal Plates)
```text
Minimalist architectural photography and editorial artwork for Moatnomics ("Less noise, more nuance").
A central split-arch Perspective Portal with inward-angled planes and a central vertical mirror prism, inspired by quiet museum architecture.
Inside the portal archway, frame [INSERT SUBJECT: e.g., misty pine valley / stepped granite terraces / industrial factory skylights].
Color grade strictly limited to [INSERT HEX CODE: e.g., Forest #0E3D32 and Sage #7DA77A] on a warm paper background (#F7F5EE).
Clean negative space, zero text, zero neon glows, zero cartoon elements, high editorial dignity, cinematic natural lighting. --ar 16:9 --style raw
```

### 5.2 Figma / Illustrator SVG Production Rules (Vector Icons & Badges)
1. **Grid:** Create artboards at `24×24px`. Set grid lines to `1px` with subdivisions of `0.5px`. Leave `2px` exterior margin padding.
2. **Pathing:** All strokes must be unified to `1.85px`. Ensure `stroke-linecap="round"` and `stroke-linejoin="round"`.
3. **Fills:** Set all fills to `none` (except where solid contrast dots or calibrated indicators are intentionally designed).
4. **Color Binding:** Default to `stroke="currentColor"`. When exporting colored section sets, use the exact hex codes from Section 2.
5. **SVG Optimization:** Run SVGO or optimize paths to ensure zero extraneous inline `<style>` tags, zero base64 bitmaps, and clean relative paths.

---

## 6. Verification & Drop-In Checklist

After generating and dropping the files into `web/static/img/`, run the following validation:

1. **Verify File Placement:**
   ```bash
   ls -la web/static/img/nav/ web/static/img/pillars/ web/static/img/sectors/ web/static/img/heroes/
   ```
2. **Execute Outside-In Test Suite:**
   ```bash
   python3 -m unittest tests/outside_in/test_interactive_ui_and_contracts.py
   ```
3. **Execute Reality Audit Gate:**
   ```bash
   python3 scripts/verify_reality_audit.py
   ```
4. **Verify Live Rendering in Headless Chrome:**
   Ensure no broken SVG sprites, no clipped viewBox dimensions, and full contrast compliance across both Light (`#F7F5EE`) and Dark (`#09090B`) themes.


---

## 7. Generated Asset Deployment & Production Integration — 21 October 2026

All 62 named inventory files from the approved external delivery packages (`Moatnomics-Pending-Visual-Assets-v1.0` and `Moatnomics-Brand-Assets-Final-v1.0`) have been deployed into active production directories under `web/static/img/` and synchronized with inline SVG symbols in `web/templates/base.html`.

| Group | Deployment Status | Count | Production Directory |
|---|---|---|---|
| Hero banners | Active (1200 × 400 WebP Indian architectural & landscape scenes) | 13 | `web/static/img/heroes/` |
| Manifesto plates | Active (800 × 1000 WebP Depth, Perspective, Clarity, Opportunity) | 4 | `web/static/img/brand/` |
| Social card & Logos | Active (Ivory card with approved pointed mirror, dimensional SVGs/PNGs) | 11 | `web/static/img/brand/` |
| Navigation icons | Active (Refined 24px SVG masters + base.html inline `<symbol>` sprite) | 12 | `web/static/img/nav/` & `base.html` |
| Pillar badges | Active (Refined 24px SVG masters + base.html inline `<symbol>` sprite) | 7 | `web/static/img/pillars/` & `base.html` |
| Sector badges | Active (Refined 24px SVG masters + base.html inline `<symbol>` sprite) | 10 | `web/static/img/sectors/` & `base.html` |
| Pricing tiers | Active (True 32px SVG masters + base.html inline `<symbol>` sprite) | 4 | `web/static/img/pricing/` & `base.html` |
| UI state illustrations | Active (Full 400 × 240 architectural SVGs) | 3 | `web/static/img/ui/` |
| Favicon formats | Active (SVG, PNG-32, PNG-64, Apple Touch Icon, ICO) | 5 | `web/static/img/brand/` & `web/static/favicon.ico` |

**Verification & Validation:**
- **Reality Verification Audit (`verify_reality_audit.py`):** Passed with 0 errors across all 12 Gates.
- **Outside-In Contract Suite (`test_interactive_ui_and_contracts.py`):** 46 tests executed and passing with 0 failures.
- **Cache-Busting:** Version stamp bumped across `web/templates/base.html` (`?v=20261021_1430`).
