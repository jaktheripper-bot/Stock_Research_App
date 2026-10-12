# System Architecture & Technical Knowledge Base

## 1. Core Architectural Directives
* **Zero-Hallucination Data Integrity:** Synthetic or AI-estimated financial metrics (P/E, Market Cap, 52-Week Range) are strictly prohibited. The system must enforce hard stops when live exchange quotes fail[cite: 2].
* **Two-Tier Caching & Delta Gating:** Expensive qualitative LLM regenerations trigger only on material events: price moves >= 5%, new BSE filings, or a report age > 14 days[cite: 2].

## 2. Scrip Resolution & Data Ingestion
* **5-Tier BSE Resolution:** Queries map to 6-digit BSE codes via: (1) Direct 6-Digit Code, (2) `dynamic_aliases.json`, (3) Static `PRIMARY_BSE_MAP`, (4) Active Master Universe `bse_scrips_cache.json`, and (5) Just-In-Time Gemini Grounded Search[cite: 2].
* **Ingestion:** Primary data is fetched via Angel One SmartAPI (quotes, daily candles) and direct BSE exchange APIs. Missing valuation fields are filled by a consolidated `yfinance` parser (gap-filler, `YFINANCE_FALLBACK=0` disables), returning "N/A" rather than guessing if data is unavailable[cite: 6].

## 3. Persistence & AI Routing
* **Database Dual-Binding:** Transparent failover between PostgreSQL (Supabase) for production and SQLite (`reports.db`) for local development[cite: 2].
* **Multi-Provider Failover:** Gemini models route through a dynamic Flash cascade (defaulting to the latest compatible Flash model, filtering out single-purpose variants). If Google API exhausts retries, it fails over to Perplexity's `sonar-pro` model[cite: 2].

## 4. Modular Domain Architecture & Persistence Facade
* **Modular `core/db/` Package:** Database operations are modularized into domain-specific modules adhering to Single Responsibility:
  * `core/db/connection.py`: Thread-safe connection pooling (`_PooledConnectionProxy`), SQLite WAL fallback, dual schema migrations (v001–v006).
  * `core/db/compliance.py`: SEBI safe-harbor disclaimer and immutable compliance audit logging.
  * `core/db/reports.py`: Snapshot archiving, time-series differential revisions, and structured query retrieval.
  * `core/db/watchlist.py`: Watched scrips, automated surveillance scan timestamps, and tracking status.
  * `core/db/alerts.py`: BSE material surveillance event ledger, notification counts, and user dismissals.
  * `core/db/telemetry.py`: Privacy-preserving user action journeys, geographic/device demographics, and API credit cost savings.
  * `core/db/settings.py`: Dynamic system configuration key-value storage.
* **Zero-Breaking-Change Root Facade (`db.py`):** The root `db.py` exposes a 100% backwards-compatible facade re-exporting all symbols from `core.db`, ensuring existing scripts, test suites, and preflight checks operate with zero import breakage.

## 5. Modular Analysis & AI Pipeline Architecture
* **Modular `core/analysis/` Package:** Institutional research synthesis, fundamental ingestion, delta triggers, and peer comparisons are decomposed into specialized submodules:
  * `core/analysis/exceptions.py`: Robust pipeline exception taxonomy (`PipelineError`, `TickerResolutionError`, `ExchangeDataFetchError`).
  * `core/analysis/parser.py`: 7-pillar health matrix extraction, regulatory sanitization, citations footnote formatting, and time-series qualitative drift differential comparisons.
  * `core/analysis/fundamentals.py`: Primary BSE exchange quote resolution, consolidated `yfinance` ratio fallback, 50-DMA/technical precomputation, and corporate announcements feed.
  * `core/analysis/exceptions.py`: Robust pipeline exception taxonomy (`PipelineError`, `TickerResolutionError`, `ExchangeDataFetchError`).
  * `core/analysis/parser.py`: 7-pillar health matrix extraction, regulatory sanitization, citations footnote formatting, and time-series qualitative drift differential comparisons.
  * `core/analysis/fundamentals.py`: Primary BSE exchange quote resolution, consolidated `yfinance` ratio fallback, 50-DMA/technical precomputation, and corporate announcements feed.
  * `core/analysis/dossier_report_synthesis.py`: Dynamic Flash model discovery cascade, Perplexity `sonar-pro` failover, SSE stream parsing, and visual citations attribution ingestion.
  * `core/analysis/dossier_bull_bear.py`: 60-second institutional Bull vs Bear thesis synthesis.
  * `core/analysis/delta.py`: 4-gate material change evaluation, self-healing cache checks, pillar markdown splicing, and zero-grounding-fee surgical valuation/technicals refresh.
  * `core/analysis/peer_comparison.py`: Cross-company institutional peer comparison, side-by-side metric alignment, and 3-axis disparity diagnostics (Sector, Lifecycle, Scale).
  * `core/analysis/stock_discovery.py`: 09:00 AM daily pre-market candidate discovery pipeline.
  * `core/analysis/retail_safety_radar.py`: Cross-asset capital hierarchy risk comparator.
  * `core/analysis/net_real_tax_calculator.py`: Post-tax purchasing power deflator.
  * `core/analysis/mutual_funds_engine.py`: AMFI 6-pillar look-through, fee drag, and active share evaluator.
  * `core/analysis/fund_overlap_auditor.py`: Pairwise portfolio overlap matrix and constituent look-through aggregator.
  * `core/analysis/debt_catalogue.py`: Structured catalogue of Indian corporate debt securities and SDIs.
  * `core/analysis/sm_reit_invit_engine.py`: Commercial REIT, InvIT, and SGB distribution yield engine.
* **Zero-Breaking-Change Root Facade (`analyzer.py`):** The root `analyzer.py` exposes a 43-line facade re-exporting all symbols from `core.analysis`, ensuring zero import breakage across UI views, tests, and CLI task runners.

## 6. Server-Side Rendered Presentation & API Architecture
* **FastAPI Application Orchestrator (`web/main.py`):** High-concurrency async ASGI application serving Jinja2 server-side rendered HTML views, rate limiting, and REST API routes.
  * Public Views: `/` (Landing), `/discovery` (Stock Discovery @9AM), `/dossier/{ticker}` (Institutional Equity Dossier), `/opportunities` (Opportunity Terminal), `/funds` & `/funds/compare/overlap` (Mutual Funds & ETFs / Fund Overlap Auditor), `/debt` (Bonds, NCDs & SDIs), `/sovereign` (Sovereign Curve & T-Bills), `/reits` (SM REITs, InvITs & SGBs), `/etfs` (National ETF Matrix), `/calculator/tax` (Net Real Tax Calculator), `/safety-radar` (Retail Safety Radar), `/compare` (Peer Comparison), `/pricing` (Pricing & Billing).
  * REST APIs: `/api/dossier/intel/{ticker}`, `/api/cortex/*`, `/api/copilot/chat`, `/api/funds/overlap`, `/api/tax/compute`, `/api/auth/*`.
  * Deep-Dive Paywalls (1 Credit / Permanent):
    * Equity: `POST /api/dossier/unlock/{ticker}` (Pillars 03/05, Reverse DCF Sandbox).
    * Mutual Funds: `POST /api/funds/unlock/{scheme_code}` (7-Pillar Look-Through Forensics, Weighted Moat, ASRI, Audit Narrative).
    * Corporate Debt: `POST /api/debt/unlock/{isin}` (Credit Contagion Radar, Cash Flow Solvency Pillar 03, Recovery Reality Pillar 05).
    * Server-side redaction across page templates, public JSON APIs, and PDF exports.
  * SEO & Attribution: Canonical `<link rel="canonical">` and `og:url` tags on all views, `CrawlerLogMiddleware` with bot detection, admin SEO visibility dashboard, and `utm_source=share` attribution.
  * Security & Auth: Standard library Email OTP (`core/auth/otp.py`) and Admin 2FA TOTP (`core/auth/totp.py`).
  * Modern Dark-Glassmorphism Design System: `web/static/css/style.css`, Inter typography, 100% viewport zoom lock, strict visual affordance separation (squircle 8px buttons vs. dark matte telemetry badges), decluttered 2-zone 7-pillar accordions with executive lead styling, and interactive slide-drawer Forensic Intelligence Desk (`web/static/js/copilot.js`, shortcut: `⌘K`).

## 7. Deterministic Cortex & Multi-Asset Engines
* **Cortex Forensic & Structural Sieve Package (`core/cortex/`):**
  * `chanakya.py`: 10-Point Deterministic Clean-Room Forensic Filter.
  * `varan.py`: Multi-Year XBRL Delta & 3-Stage DuPont ROE Decomposition Ledger.
  * `setu.py`: Relational Cross-Asset Capital Hierarchy & Inversion Detector.
  * `garuda.py`: BSE Corporate Announcement Regex Classifier & MicroSnapshot Delta Generator.
  * `sutra.py`: Multi-Asset Mutual Fund Look-Through Concentration & Overlap Engine.
* **Institutional Equity Dossier Coordinator (`core/analysis/equity_dossier.py`):**
  * Synthesizes 5 category-native cockpit metrics (`compile_equity_dossier`): Sector Scorecard, Valuation Radar, Institutional Flow, Forensic Sieve, and 60-Second Bull/Bear Thesis.
* **Forensic Intelligence Desk (`core/agents/copilot/forensic_desk.py`):**
  * Multi-asset conversational research agent (`process_forensic_desk_turn`) calibrated across Equities, Mutual Funds, and Corporate Debt.
  * **Input Qualification Layer (`check_input_qualification`):** Rejects keyboard mash, consonant clusters, and symbol noise with high-conviction query guidance; deflects casual greetings into onboarding assistance.
  * **Open-Ended Query Synthesis Engine:** Directly resolves high-conviction questions ("what shocked you?", "summarize the bear thesis", "summarize the bull thesis") synthesized dynamically from active report matrices (`health_matrix`, `reverse_dcf`, `fundamentals`).
  * **Tier & Credit Burn Protection:** Limits Google Gemini LLM API generation (`gemini-3.8-flash` cascade) to Unlocked Deep Dives and Pro Subscribers; Free users receive deterministic rule-based analysis with explicit desk mode badges.
  * Enforces SEBI non-advisory compliance, server-side deep-dive paywall gating, and automated credit unlock prompts.
  * Orchestrates `valuation_radar.py` (2-Stage DCF + EPV + P/E Median), `sector_scoring.py` (BFSI, IT, Infra, Pharma), `institutional_flow.py` (Level-2 Order Imbalance & Circuit Locks), `forensic_sieve.py` (6-point check), and `dossier_bull_bear.py` (60-sec structural thesis).
* **Multi-Asset Analytics (`core/analysis/`):**
  * `net_real_tax_calculator.py`: Post-tax real purchasing power deflator factoring in MOSPI CPI and Sec 50AA/112A/47(viic).
  * `sovereign_engine.py`: RBI FBIL benchmark yield curve & policy wedges.
  * `sm_reit_invit_engine.py`: SEBI Commercial & SM REIT distribution waterfalls under Sec 115UA.
  * `etf_matrix_engine.py`: Low-cost tracking error and exchange liquidity spreads.
  * `retail_safety_radar.py`: Cross-asset liquidation seniority and shadow-banking danger scores.

