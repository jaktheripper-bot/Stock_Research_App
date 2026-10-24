# System Architecture & Technical Knowledge Base

## 1. Core Architectural Directives
* **Zero-Hallucination Data Integrity:** Synthetic or AI-estimated financial metrics (P/E, Market Cap, 52-Week Range) are strictly prohibited. The system must enforce hard stops when live exchange quotes fail[cite: 2].
* **Two-Tier Caching & Delta Gating:** Expensive qualitative LLM regenerations trigger only on material events: price moves >= 5%, new BSE filings, or a report age > 14 days[cite: 2].

## 2. Scrip Resolution & Data Ingestion
* **5-Tier BSE Resolution:** Queries map to 6-digit BSE codes via: (1) Direct 6-Digit Code, (2) `dynamic_aliases.json`, (3) Static `PRIMARY_BSE_MAP`, (4) Active Master Universe `bse_scrips_cache.json`, and (5) Just-In-Time Gemini Grounded Search[cite: 2].
* **Ingestion & SmartAPI EOD Routing:** Primary data is fetched via Angel One SmartAPI (live quotes, Level-2 depth, dynamic scrip search via `search_scrip_token`, and 1-year `ONE_DAY` historical EOD candles via `get_eod_summary` computing EOD price, 52W High/Low, 50-DMA, and 200-DMA) and direct BSE exchange APIs. Missing valuation fields are filled by a consolidated `yfinance` parser (gap-filler, `YFINANCE_FALLBACK=0` disables), returning "N/A" rather than guessing if data is unavailable[cite: 6].

## 3. Persistence & AI Routing
* **Database Dual-Binding:** Transparent failover between PostgreSQL (Supabase) for production and SQLite (`reports.db`) for local development[cite: 2].
* **Multi-Provider Failover & Batch/Flex Discount Tier:** Gemini models route through a dynamic Flash cascade (defaulting to the latest compatible Flash model, filtering out single-purpose variants), while the daily 08:30 AM 15-stock cohort ingestion executes via the Gemini Batch API (`client.batches.create`, 50% discount) with Gemini Flex Inference (`service_tier="flex"`, 50% discount) fallback. If Google API exhausts retries, it fails over to Perplexity's `sonar-pro` (`/v1/responses`) and `sonar` (`/chat/completions`) models[cite: 2].

## 4. Modular Domain Architecture & Persistence Facade
* **Modular `core/db/` Package:** Database operations are modularized into domain-specific modules adhering to Single Responsibility:
  * `core/db/connection.py`: Thread-safe connection pooling (`_PooledConnectionProxy`, hardened default `DB_POOL_MAX = 10`), SQLite WAL fallback, dual schema migrations (`v001–v036`, including `v031_widen_sovereign_macro_columns` widening `sovereign_macro_rates` text columns to `VARCHAR(120)` in PostgreSQL).
  * `core/db/users.py`: User accounts, welcome grants, credit usage ledgers, dossier unlocks, and confidential user-scoped Countercase & Thesis Checkpoint persistence (`user_thesis_ledger`).
  * `core/db/digest.py`: Dialect-branched daily digest subscriber querying (`get_active_digest_subscribers`) enforcing PostgreSQL strict boolean comparison (`IS TRUE`, `NOW()`) and SQLite compatibility (`= 1`, `datetime('now')`).
  * `core/db/compliance.py`: SEBI safe-harbor disclaimer and immutable compliance audit logging.
  * `core/db/reports.py`: Snapshot archiving, time-series differential revisions, bounded LRU caches (`get_report_by_ticker` maxsize=48, `get_archived_reports` maxsize=16, `get_report_revisions` maxsize=32 with `include_text: bool = False`), and bounded TTL caching on equities directory queries.
  * `core/db/watchlist.py`: Watched scrips, automated surveillance scan timestamps, and tracking status.
  * `core/db/alerts.py`: BSE material surveillance event ledger, notification counts, and user dismissals.
  * `core/db/support.py`: Support tickets, customer inquiry threads (`ticket_responses`), and status tracking.
  * `core/db/telemetry.py`: Privacy-preserving user action journeys, geographic/device demographics, and API credit cost savings.
  * `core/db/settings.py`: Dynamic system configuration key-value storage.
* **Zero-Breaking-Change Root Facade (`db.py`):** The root `db.py` exposes a 100% backwards-compatible facade re-exporting all symbols from `core.db`, ensuring existing scripts, test suites, and preflight checks operate with zero import breakage.

## 5. Modular Analysis & AI Pipeline Architecture
* **Modular `core/analysis/` Package:** Institutional research synthesis, fundamental ingestion, delta triggers, and peer comparisons are decomposed into specialized submodules:
  * `core/analysis/exceptions.py`: Robust pipeline exception taxonomy (`PipelineError`, `TickerResolutionError`, `ExchangeDataFetchError`).
  * `core/analysis/parser.py`: 7-pillar health matrix extraction, regulatory sanitization, citations footnote formatting, and time-series qualitative drift differential comparisons.
  * `core/analysis/fundamentals.py`: Primary BSE exchange quote resolution, Angel One SmartAPI EOD candle summary enrichment (`get_eod_summary`), `fast_db_first` SSR database-first lookup (`get_stock_fundamentals(..., fast_db_first=True)`) and `fast_only` non-blocking historical trend resolution (`get_historical_prices(..., fast_only=True)`), conditional `yfinance` ratio backfill (`enrich_fundamentals` skipping network calls when `cached_fundamentals` already holds core ratios), thread-safe bounded LRU/TTL cache (`_BoundedFundamentalsCache(maxsize=64, ttl=900)`), 50-DMA/technical precomputation, and corporate announcements feed.
  * `core/analysis/dossier_report_synthesis.py`: Dynamic Flash model discovery cascade, Gemini Batch API (`synthesize_batch_stock_reports`) & Flex Inference (`service_tier="flex"`) 50% discount synthesis, Perplexity `sonar-pro` / `sonar` dual-endpoint failover, SSE stream parsing, and visual citations attribution ingestion.
  * `core/analysis/dossier_bull_bear.py`: 60-second institutional Bull vs Bear thesis synthesis.
  * `core/analysis/delta.py`: 4-gate material change evaluation, self-healing cache checks, pillar markdown splicing, and zero-grounding-fee surgical valuation/technicals refresh.
  * `core/analysis/peer_comparison.py`: Cross-company institutional peer comparison, lazy peer fundamentals resolution, side-by-side metric alignment, and 3-axis disparity diagnostics (Sector, Lifecycle, Scale).
  * `core/analysis/stock_discovery.py`: 09:00 AM daily pre-market candidate discovery pipeline.
  * `core/analysis/daily_stock_ingestion.py`: Pre-market 08:30 AM 15-stock ingestion pipeline, uncovered mutual fund constituent queue prioritization (`scheme_count DESC, total_weight_pct DESC`), Gemini Batch/Flex 50% cohort synthesis (`synthesize_batch_stock_reports`) with 7-check health matrix, and incremental mutual fund look-through recalculation.
  * `core/analysis/retail_safety_radar.py`: Cross-asset capital hierarchy risk comparator.
  * `core/analysis/net_real_tax_calculator.py`: Post-tax purchasing power deflator.
  * `core/analysis/mutual_funds_engine.py`: AMFI 6-pillar look-through, fee drag, and active share evaluator across 200 canonical mutual fund schemes, with single-query batch constituent preloading (`get_holdings_for_schemes_batch`, `get_researched_tickers_set`, `get_debt_securities_map`) powering sub-50ms `/api/funds/schemes` responses.
  * `core/analysis/fund_overlap_auditor.py`: Pairwise portfolio overlap matrix, constituent look-through aggregator across 200 canonical schemes, bounded asynchronous task registry (`MAX_FUND_AUDIT_TASKS = 64`) with eviction prioritizing completed tasks, and on-demand constituent deep-dive audit synthesizer/archiver with staged progress tracking.
  * `core/analysis/debt_catalogue.py`: Structured catalogue of Indian corporate debt securities and SDIs.
  * `core/analysis/sm_reit_invit_engine.py`: Commercial REIT, InvIT, and SGB distribution yield engine.
* **Zero-Breaking-Change Root Facade (`analyzer.py`):** The root `analyzer.py` exposes a 43-line facade re-exporting all symbols from `core.analysis`, ensuring zero import breakage across UI views, tests, and CLI task runners.

## 6. Server-Side Rendered Presentation & API Architecture
* **FastAPI Application Orchestrator (`web/main.py`):** High-concurrency async ASGI application serving Jinja2 server-side rendered HTML views, single-worker execution (`--workers 1 --limit-concurrency 60 --timeout-keep-alive 5`), glibc arena trimming (`MALLOC_TRIM_THRESHOLD_=65536`, `PYTHONMALLOC=malloc`), distributed boot-time scheduler lease guards (`job_lease`), rate limiting, and REST API routes.
  * Public Views: `/` (Landing), `/discovery` (Stock Discovery @9AM), `/equities` (Institutional Equities Directory with `market_cap=RECENT` Recently Inducted filter), `/dossier/{ticker}` (Institutional Equity Dossier), `/opportunities` (Opportunity Terminal), `/funds` & `/funds/compare/overlap` (Mutual Funds & ETFs / Fund Overlap Auditor with crawler LLM defense preventing synchronous external synthesis on GET), `/debt` (Bonds, NCDs & SDIs), `/sovereign` (Sovereign Curve & T-Bills), `/reits` (SM REITs, InvITs & SGBs), `/etfs` (National ETF Matrix), `/calculator/tax` (Net Real Tax Calculator), `/safety-radar` (Retail Safety Radar), `/compare` (Peer Comparison), `/m` & `/m/{asset_type}/{asset_id}` (Mobile Brief Mode: deterministic, zero-LLM 30-second briefs compiled by `core/analysis/mobile_brief.py` from stored records; missing fields render `N/A`), `/pricing` (Pricing & Billing with Location-Aware Multi-Currency Engine & Forex Buffer).
  * REST APIs: `/api/dossier/intel/{ticker}`, `/api/mobile-brief/{asset_type}/{asset_id}`, `/api/cortex/*`, `/api/copilot/chat`, `/api/funds/overlap`, `/api/tax/compute`, `/api/auth/*`, `/api/billing/currencies`, `/api/admin/stocks/run-daily-ingest`, `/api/admin/stocks/ingestion-queue`, `/api/admin/ai-spends`.
  * Deep-Dive Paywalls (1 Credit / Permanent):
    * Equity: `POST /api/dossier/unlock/{ticker}` (Pillars 03/05, Reverse DCF Sandbox).
    * Mutual Funds: `POST /api/funds/unlock/{scheme_code}` (7-Pillar Look-Through Forensics, Weighted Moat, ASRI, Audit Narrative).
    * Corporate Debt: `POST /api/debt/unlock/{isin}` (Credit Contagion Radar, Cash Flow Solvency Pillar 03, Recovery Reality Pillar 05).
    * Server-side redaction across page templates, public JSON APIs, and PDF exports.
  * SEO & Attribution: Canonical `<link rel="canonical">` and `og:url` tags on all views, `CrawlerLogMiddleware` with bot detection, admin SEO visibility dashboard, and `utm_source=share` attribution.
  * Security & Auth: Standardized Supabase GoTrue Auth (`core/auth/supabase_auth.py:send_magic_link`, `verify_supabase_otp_token`, `verify_supabase_access_token`) with local HMAC Email OTP fallback (`core/auth/otp.py`) and Admin 2FA TOTP (`core/auth/totp.py`) with ±120s drift tolerance (`window=4`), instantaneous QR re-scan (`/admin/setup-2fa?reset=1`), localhost bypass code `000000`, 1-click local dev fast track (`POST /admin/auth/dev-login`), and `next_url` destination preservation.
  * Admin Service Inbox, AI Spends & Telemetry: `/admin?tab=tickets`, `/admin?tab=ai-spends`, `GET /api/admin/ai-spends`, `core/analytics/ai_spends.py` (aggregating live Gemini Flash spend, token distributions, and ~92.4% pre-compression savings), `/api/admin/tickets/{ticket_id}/thread`, `POST /admin/tickets/{ticket_id}/reply`, two-way email notification engine (`core/notify.py:send_ticket_reply_email`) with standard SMTP dispatch, test/dev mock fallback, and executive copilot resolution.
  * Moatnomics Visual Identity v2.0 Design System: `core/brand/visual_identity.py`, `web/static/css/style.css`, Dual-Theme Dark (`#0B2337` Deep Ink Navy / `#0E3D32` Moatnomics Forest) and Warm Ivory (`#F7F5EE` `[data-theme="light"]` & `.dossier-ivory-surface`) surfaces, `Playfair Display` + `Inter` (`font-variant-numeric: tabular-nums`) + `JetBrains Mono` typography, "The Perspective Portal" SVG mark (`#logo-perspective-portal`), canonical `24×24px` (`1.85px` stroke) vector icon library (`web/static/img/`), 7 `[data-asset-class]` color scopes, and interactive slide-drawer Research Desk (`web/static/js/copilot.js`, shortcut: `⌘K`).

## 7. Deterministic Cortex & Multi-Asset Engines
* **Cortex Forensic & Structural Sieve Package (`core/cortex/`):**
  * `chanakya.py`: 10-Point Deterministic Clean-Room Forensic Filter.
  * `varan.py`: Multi-Year XBRL Delta & 3-Stage DuPont ROE Decomposition Ledger.
  * `setu.py`: Relational Cross-Asset Capital Hierarchy & Inversion Detector.
  * `garuda.py`: BSE Corporate Announcement Regex Classifier & MicroSnapshot Delta Generator.
  * `sutra.py`: Multi-Asset Mutual Fund Look-Through Concentration & Overlap Engine.
* **Institutional Equity Dossier Coordinator (`core/analysis/equity_dossier.py`):**
  * Synthesizes 5 category-native cockpit metrics (`compile_equity_dossier`): Sector Scorecard, Valuation Radar, Institutional Flow, Forensic Sieve, and 60-Second Bull/Bear Thesis.
* **Research Desk (`core/agents/copilot/research_desk.py`):**
  * Multi-asset conversational research agent (`process_research_desk_turn`) calibrated across Equities, Mutual Funds, and Corporate Debt.
  * **Input Qualification Layer (`check_input_qualification`):** Rejects keyboard mash, consonant clusters, and symbol noise with high-conviction query guidance; deflects casual greetings into onboarding assistance.
  * **Open-Ended Query Synthesis Engine:** Directly resolves high-conviction questions ("what shocked you?", "summarize the bear thesis", "summarize the bull thesis") synthesized dynamically from active report matrices (`health_matrix`, `reverse_dcf`, `fundamentals`).
  * **Tier & Credit Burn Protection:** Limits Google Gemini LLM API generation (modernized cascade `gemini-3.8-flash` -> `gemini-3.5-flash-lite` -> `gemini-3.1-flash-lite` -> `gemini-2.5-flash`, AFC disabled) to Unlocked Deep Dives and Pro Subscribers; Free users receive deterministic rule-based analysis with explicit desk mode badges. Test mode is isolated via execution environment variables (`TESTING=1`, `PYTEST_CURRENT_TEST`) preventing `sys.modules` pollution.
  * Enforces SEBI non-advisory compliance, server-side deep-dive paywall gating, and automated credit unlock prompts.
  * Orchestrates `valuation_radar.py` (2-Stage DCF + EPV + P/E Median), `sector_scoring.py` (BFSI, IT, Infra, Pharma), `institutional_flow.py` (Level-2 Order Imbalance & Circuit Locks), `forensic_sieve.py` (6-point check), and `dossier_bull_bear.py` (60-sec structural thesis).
* **Multi-Asset Analytics (`core/analysis/`):**
  * `net_real_tax_calculator.py`: Post-tax real purchasing power deflator factoring in MOSPI CPI and Sec 50AA/112A/47(viic).
  * `sovereign_engine.py`: RBI FBIL benchmark yield curve & policy wedges.
  * `sm_reit_invit_engine.py`: SEBI Commercial & SM REIT distribution waterfalls under Sec 115UA.
  * `etf_matrix_engine.py`: Low-cost tracking error and exchange liquidity spreads.
  * `retail_safety_radar.py`: Cross-asset liquidation seniority and shadow-banking danger scores.

## 8. Autonomous Tri-Pillar Project Auditor & Zero-Illusion Reality Gate Parity
* **Tri-Pillar Project Auditor (`core/audit/project_auditor.py`, `core/audit/tools.py`, `web/templates/admin_audit.html`):**
  * Evaluates platform health across **Pillar 1 (Business Strategy & Regulatory Compliance)**, **Pillar 2 (Code Architecture & Runtime Stability — 800+ unit tests, AST static analysis, schema migration `v037`)**, and **Pillar 3 (UI/UX & Frontend Integrity — 37 live web endpoints, DOM/JS contract verification, 100% template SVG `<use href="#...">` symbol parity, and zero legacy OS emojis)**.
  * Enforces strict AST parity with `scripts/verify_reality_audit.py` (`[GATE-1]` through `[GATE-12]`), strips production environment flags (`RENDER`, `ENVIRONMENT`, `RAZORPAY_KEY_*`, `CANONICAL_DOMAIN`) inside `tool_run_test_suite()` subprocesses for 100% hermetic Render test execution, and ensures every computed metric (`unlogged_exceptions_count`, `broken_svg_uses_count`, `legacy_os_emojis_found`) is wired into both pillar scores and the persisted `project_audit_logs` Markdown report without polluting live `site_usage_events` telemetry.
  * **Bidirectional Cloud-to-Local PostgREST Sync (`core/db/audit_logs.py`, `core/db/remediation.py`, `scripts/run_project_audit.py --sync`):** Automatically synchronizes `project_audit_logs`, `audit_remediation_ledger`, `audits/project_audit_*.md`, and `audits/REMEDIATION_ACTION_PLAN.md` between Supabase (`SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` over IPv4 HTTPS with `certifi` TLS verification) and local SQLite (`reports.db`), ensuring identical Admin Console and local CLI audit telemetry even on IPv4-only networks where direct PostgreSQL (`db.<project>.supabase.co`) is unreachable.
* **Stateful Remediation Ledger & Closed-Loop Auditing Cycle (`audit_remediation_ledger`, migration `v037`, `core/db/remediation.py`, `core/audit/invariants.py`, `core/audit/remediation_plan.py`):**
  * **Persistent Ledger (`audit_remediation_ledger`):** Backed by dual-binding PostgreSQL & SQLite schema tracking finding lifecycle (`OPEN` -> `RE_EVALUATING` -> `RESOLVED`), category, invariant name, target file/symbol, deterministic SHA256 finding hash (`compute_finding_hash`), baseline/effective penalties, age in days, consecutive failures, and audit pass counts.
  * **Closed-Loop Execution Cycle (`execute_closed_loop_remediation_cycle()`):**
    * *Step 1 (Verify First):* Fast, targeted re-verification of all currently `OPEN` findings against their specific invariants via `verify_invariant()`. Passing checks are immediately transitioned to `RESOLVED`, restoring pillar score deductions and archiving the finding. Failing checks increment consecutive failure counters and verification pass metrics.
    * *Step 2 (Explore Next):* Executes broad multi-domain invariant scans across Backend Stability (`INV_UNBOUNDED_CACHE`, `INV_SILENT_EXCEPTION_SWALLOW`), UI/UX Contracts (`INV_DOM_INTEGRITY`, `INV_UI_NO_DEAD_HOVER`), Database Parity (`INV_SQL_DIALECT_COMPAT`, `INV_DB_SCHEMA_BOUNDS`), Security Vulnerabilities (`INV_SEC_HEADERS`, `INV_SEC_AUTH_SCOPE`, `INV_SEC_NO_STACKTRACE`), and Regulatory Safeguards (`INV_SEBI_SAFE_HARBOR`).
    * *Step 3 (Publish Score & Report):* Records composite health score factoring progressive aging penalties (1.0x multiplier for <3 days, 1.5x for 3–6 days, 2.0x compounding penalty for >=7 days with status capped at `ACTION_REQUIRED`). Generates Section 6 in the system audit report and automatically overwrites `audits/REMEDIATION_ACTION_PLAN.md` with an Executive Triage Scorecard, Aging Debt Alerts, Prioritized Active Queue (with copy-paste local bash commands), and Closed-Loop Verification Log.

## 9. Observability & Centralized Telemetry Pipeline (Better Stack)
* **Standard Library Log Ingestion Engine (`core/logging_config.py`):**
  * Seamlessly routes Python standard library `logging` output to Better Stack (Logtail) via `logtail.LogtailHandler`.
  * **Ingesting Host:** Configured to `s2808842.us-west-2a.betterstackdata.com` (or configurable via `BETTER_STACK_INGESTING_HOST` / `LOGTAIL_INGESTING_HOST`).
  * **Source Token:** Secured via `n9BuFhtn6SwGdLrRd4A8wFn6` (or configurable via `BETTER_STACK_SOURCE_TOKEN` / `LOGTAIL_SOURCE_TOKEN`).
  * **Namespace Routing:** Attached to the `equity_research` namespace and the root logger, automatically transmitting events from web routes, background schedulers, multi-asset engines, and admin copilots.
  * **Structured Logging Context:** Full support for `logger.info("...", extra={"key": "value"})` conforming to the official Better Stack integration guide.
  * **FastAPI Lifespan Integration:** Initialized on startup in `web/main.py`; synchronous flush on shutdown (`flush_betterstack_logs`) prevents in-flight log drops on container restarts.
  * **Automated Test Isolation:** `is_test_environment()` suppresses remote HTTP logtail dispatches during test and CI executions, protecting bandwidth and logging quotas.

## 10. Autonomous Scheduled Daemon & Data Archival Invariants
* **Mutual Fund Look-Through Narrative Archival Guard (`core/analysis/daily_stock_ingestion.py`, `core/db/mutual_funds.py`):**
  * **Synthesis Fallback & Narrative Retention:** During daily 15-stock look-through recalculation (`recalculate_affected_mutual_funds`), `new_dossier` retains existing `old_text` or synthesizes updated narrative via `synthesize_fund_forensic_narrative(new_dossier, scheme)`.
  * **Dual-Layer Database Archival Guard:** In `save_fund_forensic_dossier`, checks existing database text if incoming is empty and enforces SQL `ON CONFLICT (scheme_code) DO UPDATE SET dossier_text = CASE WHEN excluded.dossier_text IS NOT NULL AND TRIM(excluded.dossier_text) != '' THEN excluded.dossier_text ELSE fund_forensic_dossiers.dossier_text END`, preventing quantitative recalibrations from wiping qualitative research dossiers.
* **Sovereign Yield Curve Term-Structure History (`core/db/sovereign.py`):**
  * **Daily Snapshot Archival:** `save_sovereign_curve_snapshot(edition_date)` records all 16 statutory yield curve tenors into `sovereign_curve_history` with `UNIQUE(snapshot_key, tenor_label)`.
  * **Automated Nightly Synchronization:** Integrated directly into `refresh_daily_sovereign_benchmarks` (returning `curve_snapshots_saved: 16`) and callable via `get_sovereign_curve_history(snapshot_key)`.
* **Python 3.14 Autonomous Pipeline Daemon (`launchd/com.moatnomics.pipeline.plist`):**
  * **Runtime Alignment:** ProgramArguments targets active Python 3.14 (`/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`), eliminating PEP 604 type-union compatibility crashes on outdated macOS system Python 3.9.
  * **Autonomous Cadence:** Registered in `launchctl` (`com.moatnomics.pipeline`) with explicit `PATH` and `PYTHONPATH` environment variables, executing 08:30 IST morning ingestion and 23:15 IST nightly multi-asset synchronization independent of interactive web server lifespan.





