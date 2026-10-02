# System Architecture & Technical Knowledge Base

## 1. Core Architectural Directives
* **Zero-Hallucination Data Integrity:** Synthetic or AI-estimated financial metrics (P/E, Market Cap, 52-Week Range) are strictly prohibited. The system must enforce hard stops when live exchange quotes fail[cite: 2].
* **Two-Tier Caching & Delta Gating:** Expensive qualitative LLM regenerations trigger only on material events: price moves >= 5%, new BSE filings, or a report age > 14 days[cite: 2].

## 2. Scrip Resolution & Data Ingestion
* **5-Tier BSE Resolution:** Queries map to 6-digit BSE codes via: (1) Direct 6-Digit Code, (2) `dynamic_aliases.json`, (3) Static `PRIMARY_BSE_MAP`, (4) Active Master Universe `bse_scrips_cache.json`, and (5) Just-In-Time Gemini Grounded Search[cite: 2].
* **Ingestion:** Primary data is fetched via direct BSE exchange APIs. Missing valuation fields fall back to a consolidated `yfinance` parser, returning "N/A" rather than guessing if data is unavailable[cite: 6].

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
  * `core/analysis/engine.py`: Dynamic Flash model discovery cascade, Perplexity `sonar-pro` failover, SSE stream parsing, and visual citations attribution ingestion.
  * `core/analysis/delta.py`: 4-gate material change evaluation, self-healing cache checks, pillar markdown splicing, and zero-grounding-fee surgical valuation/technicals refresh.
  * `core/analysis/comparator.py`: Cross-company institutional peer comparison, side-by-side metric alignment, and 3-axis disparity diagnostics (Sector, Lifecycle, Scale).
* **Zero-Breaking-Change Root Facade (`analyzer.py`):** The root `analyzer.py` exposes a 43-line facade re-exporting all symbols from `core.analysis`, ensuring zero import breakage across UI views, tests, and CLI task runners.

## 6. Modular Presentation & View Controller Architecture
* **Modular `ui/views/` Package:** The public user interface is cleanly separated into focused view controllers:
  * `ui/views/state.py`: Session state synchronization, deep linking URL persistence, and 5-phase research pipeline execution.
  * `ui/views/sidebar.py`: Stock lookup search, archive selectbox, multi-quarter revision diffing, and revision timelines.
  * `ui/views/alerts_view.py`: Granular event alerting hub, unread badge counters, triage actions, and watchlist management.
  * `ui/views/dossier_view.py`: Search input, language selection, active dossier metrics, streaming synthesis progress, scorecard, and PDF export.
* **Lean Top-Level Application Orchestrator (`app.py`):** Reduced from 1,276 lines to 170 lines, coordinating page configuration, GA4 telemetry, CSS styling, sidebar rendering, and clean route dispatch.
