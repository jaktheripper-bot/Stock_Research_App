# Codebase Navigation Index & Architectural Anchors

**Document Identifier:** `docs/CODEBASE_INDEX.md`  
**Purpose:** Compact, authoritative index mapping system components to exact file paths and primary code regions to eliminate exploratory file hunting and minimize AI token consumption.

---

## 1. Web Application & Router Layers (`web/`)

### `web/main.py` (~3,035 lines)
- **Lines 1–150:** Imports, Global Configuration, Logging Setup, Schedulers Initialization.
- **Lines 151–450:** Lifespan Management (`lifespan`), Background Daemons, Database Pool Warming, Distributed Lease Handlers.
- **Lines 451–750:** Public Directory Routes:
  - `GET /` (`home_page`), `GET /equities` (`equities_directory_page`), `GET /discovery` (`discovery_page`).
  - `GET /funds` (`fund_directory_page`), `GET /etfs` (`etf_matrix_page`), `GET /debt` (`debt_directory_page`).
  - `GET /sovereign` (`sovereign_curve_page`), `GET /reits` (`reits_directory_page`), `GET /msme` (`msme_directory_page`).
  - `GET /safety-radar` (`safety_radar_page`), `GET /pricing` (`pricing_page`), `GET /contact` (`contact_page`).
- **Lines 751–1250:** Asset Dossier View Controllers:
  - `GET /dossier/{ticker}` (`dossier_page` — Equity Intelligence Cockpit, 3-part provenance, drift, health matrix).
  - `GET /funds/{scheme_code}` (`fund_dossier_page`), `GET /debt/{isin}` (`debt_dossier_page`).
  - `GET /reits/{symbol}` (`reit_dossier_page`), `GET /etfs/{symbol}` (`etf_dossier_page`), `GET /msme/{uin}` (`msme_dossier_page`).
  - `GET /m` & `GET /m/{asset_type}/{asset_id}` (`mobile_brief_page` — Deterministic Mobile Brief Mode).
- **Lines 1251–1800:** Search & Comparative Tools:
  - `GET /search` (`search_page`), `GET /api/search/products` (`api_search_products` — 7-Asset Omni-Search).
  - `GET /compare` (`compare_page` — Peer Comparison Engine), `GET /calculator/tax` (`tax_calculator_page`).
- **Lines 1801–2300:** Research Synthesis & Unlock API Endpoints:
  - `POST /api/synthesize` (`synthesize_report_endpoint` — Live 7-Pillar Equity Report Generator).
  - `POST /api/dossier/unlock/{ticker}` (`unlock_dossier_endpoint` — Credit Deduction & Report Decryption).
  - `POST /api/funds/deep-dive-quote/{scheme_code}`, `POST /api/funds/unlock/{scheme_code}`.
- **Lines 2301–2700:** Telemetry & System Utilities:
  - `POST /api/telemetry/event` (`record_client_event`), `POST /api/telemetry/dwell` (`record_page_dwell`).
  - `GET /health` (`health_check`), `GET /robots.txt`, `GET /llms.txt`, `GET /sitemap.xml`.
- **Lines 2701–3035:** Error Handlers (`404`, `500`, CSRF, Validation Exceptions).

---

## 2. Client Scripts & Design System (`web/static/`)

### `web/static/js/main.js` (~4,003 lines)
- **Lines 1–350:** Core Initialization, Theme Toggling (`initThemeToggle`, `toggleSiteTheme`), User Session Cache (`getStoredUser`).
- **Lines 351–800:** Two-Tier Navigation & Evaluation HUD Engine:
  - `initTwoTierNavigation`, `showEvaluationHUD`, `hideEvaluationHUD`, `startEvaluationProgressBar`, 32-card trust carousel.
  - Background route pre-fetching (`X-Moatnomics-Prefetch`), `markButtonProgressReady`.
- **Lines 801–1500:** 7-Asset Omni-Search Modal & Keybindings:
  - `openOmniSearchModal`, `closeOmniSearchModal`, `handleOmniSearchInput` (with `AbortController`), keyboard arrows/enter.
- **Lines 1501–2200:** Credit Checkout, Pre-Flight Modal & Razorpay Integration:
  - `openGenerateModal`, `synthesizeReport`, `unlockDeepDive`, `handleRazorpayCheckout`, credit balance syncing.
- **Lines 2201–3000:** Interactive Calculators & Sandboxes:
  - `recalcDcfSandbox` (Reverse-DCF slider solver), `recalcMfFeeDrag` (20Y mutual fund fee drag).
  - `recalcReitCorpusWaterfall` (Section 115UA waterfall), `recalcTaxImpact`.
- **Lines 3001–4003:** Telemetry Trackers, Active Dwell Beacon (`initDwellAndTransitionTelemetry`), Toasts & Light Dismiss.

### `web/static/css/style.css` (~5,778 lines)
- **Lines 1–400:** Design Tokens, Typography (`Playfair Display`, `Inter`, `JetBrains Mono`), Canonical Palette.
- **Lines 401–850:** Theme Scopes (`:root`, `html[data-theme="light"]`, `html[data-theme="dark"]`, `.dossier-ivory-surface`).
- **Lines 851–1400:** 9 Multi-Asset Color Cues (`[data-asset-class="equities|funds|etfs|debt|sovereign|reits|opportunities|msme|safety"]`).
- **Lines 1401–2500:** Grid Systems, Biscuit Cards (`.card.asset-card-accent`), Responsive Grids, Sticky Navigation.
- **Lines 2501–3800:** Dossier Presentation, 3-Part Provenance Bar (`.dossier-provenance-bar`), Masthead, Epistemic Badges.
- **Lines 3801–4800:** Modals & Overlays (`.modal-backdrop`, `.modal-dialog`, `#omniSearchModal`, `#synthesizingOverlay`).
- **Lines 4801–5778:** Utility Classes, Badges, Tables (`.table-sticky-wrap`), Responsive Media Queries.

---

## 3. Core Analytical & Presentation Engines (`core/`)

- **`core/presentation/formatters.py`:** Standardized financial sentinels (`—`, `NM`, `BFSI`, `0.00x`), P/E and D/E formatters.
- **`core/search/product_search.py`:** Multi-asset cross-sectional query engine across all 7 asset classes with BSE resolution.
- **`core/analysis/fundamentals.py`:** SmartAPI + Official BSE JSON equity ingestion, technical indicators, and caching.
- **`core/analysis/parser.py`:** Dossier Markdown processor, 3-part provenance bar, statutory vs secondary citation classification.
- **`core/analysis/dossier_report_synthesis.py`:** Grounded 7-Pillar synthesis orchestrator, Gemini batch/flex inference, failovers.
- **`core/analysis/epistemic_schema.py`:** 4-tier epistemic taxonomy (`VERIFIED FACT`, `CALCULATED METRIC`, etc.) & falsification ledger.
- **`core/analysis/valuation_radar.py`:** 32-iteration bisection Reverse-DCF solver & multi-model intrinsic value triangulation.
- **`core/analysis/mutual_funds_engine.py`:** Look-through active share, factor tilts, 20Y TER fee-drag simulator.
- **`core/db/`:**
  - `connection.py`: PostgreSQL (`psycopg2`) & SQLite dual-dialect connection pool and migration runner.
  - `reports.py`: Equity report storage, revision history, and directory queries.
  - `fundamentals.py`: Cached financial metrics and EOD price records.
  - `mutual_funds.py`: AMFI master schemes, NAV feeds, and forensic portfolio look-through dossiers.
  - `debt.py`: Corporate bond and SDI master records, credit ratings, cashflows.
  - `reits.py`: REITs, SM REITs, and InvIT asset portfolios, distribution waterfalls.
  - `sovereign.py`: G-Sec yield curves, T-Bill rates, and state development loan spreads.
  - `discovery.py`: Algorithmic Morning Discovery @9AM stock reel persistence.
  - `users.py`: User accounts, subscription tiers, research credit balances, thesis ledgers.
  - `telemetry.py`: Dwell times, route journeys, bot classifiers, and traffic analytics.

---

## 4. Workstream CLI & Verification Scripts (`scripts/`)

- **`scripts/remediate_equity_metrics.py` (WS1):** Equity metric validation, unit normalization (`D/E` `% -> x`), BFSI classification, and synthetic placeholder purge.
- **`scripts/remediate_dossier_provenance.py` (WS2):** Dossier provenance bar audit, live vs. baseline price drift detection, and BSE statutory citations backfill.
- **`scripts/validate_omni_search_coverage.py` (WS3):** 7-asset omni-search coverage, 6-digit BSE scrip resolution, latency benchmark, and string P/E resilience.
- **`scripts/audit_commercial_trust_and_catalog.py` (WS4 & WS5):** Commercial trust invariants, credit ledger non-negativity, homepage flagship sample audit, and template hygiene.
- **`scripts/verify_reality_audit.py`:** Pre-completion Zero-Illusion Reality Audit gate (Gates 1–12 AST validator).
- **`scripts/run_project_audit.py`:** Autonomous Tri-Pillar project auditor runner.
