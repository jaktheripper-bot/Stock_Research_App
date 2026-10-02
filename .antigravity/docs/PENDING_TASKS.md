# Project Backlog & Pending Tasks Checklist

> Comprehensive master checklist tracking architectural hardening, operational optimizations, behavioral features, and strategic roadmap milestones for the Stock Research App.

---

## 🛠️ Tier 1: Immediate Script Optimization & Code Cleanliness (From Script Audit)
*Goal: Prune leftover code, eliminate memory/descriptor leaks, and optimize request latency.*

- [x] **Purge Dead / Unused Imports**
  - [`alerts.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/alerts.py): Removed unused imports (`os`, `re`, `timezone`, unused `db` functions).
  - [`analyzer.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/analyzer.py): Removed unused imports (`sys`, `normalize_stock_data`).
  - [`app.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/app.py): Cleaned up unused imports (`sys`, `timezone`, `timedelta`, modularized chart/formatter helpers, inline redundant imports).
  - [`check_system.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/check_system.py), [`test_ui_headless.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/test_ui_headless.py): Cleaned up unused imports.
- [x] **Prune Dead Functions**
  - [`bse_master.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/bse_master.py#L55-L74): Removed `find_fuzzy_scrip_match()` (unreferenced dead function).
  - [`screener.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/screener.py): Wired `pass_pre_screening_gates()` into [`analyzer.py:stream_stock_report()`](file:///Users/lyndonpinto/Documents/Stock_Research_App/analyzer.py#L685-L690) to enforce real trading/liquidity gating and reject inactive/suspended securities.
- [x] **External BSE Announcement Exchange Caching**
  - In [`analyzer.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/analyzer.py#L294) and [`alerts.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/alerts.py#L20): Decorated `fetch_latest_bse_announcement()` and `fetch_bse_announcements()` with `@st.cache_data(ttl=300)` to eliminate duplicate 200–600ms HTTP requests during report rendering and alert sweeps.
- [x] **Fix Process Descriptor Leak in P/E Resolver**
  - [`analyzer.py:262`](file:///Users/lyndonpinto/Documents/Stock_Research_App/analyzer.py#L262): Replaced `open(os.devnull, "w")` file handle allocation with in-memory `contextlib.redirect_stderr(io.StringIO())`.
- [x] **In-Memory Ticker Suggestion Cache**
  - [`bse_master.py:237`](file:///Users/lyndonpinto/Documents/Stock_Research_App/bse_master.py#L237): Implemented `_get_cached_candidates()` to cache the deduplicated search candidate list in memory rather than reconstructing sets across thousands of records on every keystroke.
- [x] **SEBI Disclaimer Standardization**
  - Verified and synchronized canonical [`MANDATORY_SEBI_DISCLAIMER`](file:///Users/lyndonpinto/Documents/Stock_Research_App/db.py#L14-L23) across [`ui/pdf.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/ui/pdf.py#L13) and [`app.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/app.py#L1244).
- [x] **Peer Comparison Progress Loading Bar**
  - In [`ui/comparison.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/ui/comparison.py#L52): Replaced static `st.spinner()` with structured multi-phase `st.progress` loading bar and `progress_callback` in [`analyzer.py:compare_two_companies()`](file:///Users/lyndonpinto/Documents/Stock_Research_App/analyzer.py#L1135-L1170) reporting quote resolution for Company A & B, disparity evaluation, and 7-pillar matrix alignment.

---

## 🏗️ Architectural Modularization Roadmap (Separation of Concerns)
*Goal: Decompose oversized scripts (>1,000 lines) into cohesive, single-responsibility modules with zero-breaking-change facades.*

- [x] **Phase 1: Modularize `db.py` (1,666 lines) into `core/db/`**
  - [x] Created `core/db/connection.py`: Connection pooling, dual-engine PostgreSQL/SQLite migrations (`v001_initial_schema` to `v006_report_citations`).
  - [x] Created `core/db/compliance.py`: `MANDATORY_SEBI_DISCLAIMER`, audit logging, compliance history queries.
  - [x] Created `core/db/reports.py`: Snapshot archiving, time-series differential revisions, full dossier retrieval.
  - [x] Created `core/db/watchlist.py`: Watched scrips, automated surveillance scan timestamps, tracking state.
  - [x] Created `core/db/alerts.py`: Surveillance event ledger, unread counts, user dismissals.
  - [x] Created `core/db/telemetry.py`: User actions, session journeys, demographics, API credit cost savings.
  - [x] Created `core/db/settings.py`: Dynamic system configuration key-value storage.
  - [x] Created `core/db/__init__.py`: Aggregated re-exports of all 38 public symbols with explicit `__all__`.
  - [x] Refactored root `db.py`: Transformed 1,666-line monolith into a 56-line backward-compatible facade.
  - [x] Verification: 100% pre-flight test pass (`./run.sh preflight`: linter, system check, headless UI, and 2.4x speed benchmark).
- [x] **Phase 2: Modularize `analyzer.py` (1,375 lines) into `core/analysis/`**
  - [x] `core/analysis/exceptions.py`: Robust pipeline exception taxonomy (`PipelineError`, `TickerResolutionError`, `ExchangeDataFetchError`).
  - [x] `core/analysis/parser.py`: 7-pillar health matrix extraction, regulatory sanitization, citations footnotes formatting, and differential comparison.
  - [x] `core/analysis/fundamentals.py`: Direct BSE scrip resolution, quotes, valuation ratios, 50-DMA precomputation, and corporate announcements feed.
  - [x] `core/analysis/engine.py`: Flash cascade failover, Perplexity `sonar-pro` router, prompt templates, and streaming citations ingestion.
  - [x] `core/analysis/delta.py`: 4-gate material change evaluation, self-healing cache checks, pillar splicing, and zero-grounding surgical refresh.
  - [x] `core/analysis/comparator.py`: Side-by-side peer comparison, disparity detection, 7-pillar alignment.
  - [x] `core/analysis/__init__.py`: Aggregated re-exports of all 29 public symbols with explicit `__all__`.
  - [x] Refactored root `analyzer.py`: Transformed 1,375-line monolith into a 43-line backward-compatible facade.
  - [x] Verification: 100% pre-flight test pass (`./run.sh preflight`: linter across 38 files, system check, headless UI, and speed benchmark).
- [x] **Phase 3: Modularize `app.py` (1,275 lines) into `ui/views/`**
  - [x] `ui/views/state.py`: Session state synchronization, deep linking URL persistence, and 5-phase research pipeline execution.
  - [x] `ui/views/sidebar.py`: Stock lookup search, archive selectbox, multi-quarter revision diffing, and revision timelines.
  - [x] `ui/views/alerts_view.py`: Granular event alerting hub, unread badge counters, triage actions, and watchlist management.
  - [x] `ui/views/dossier_view.py`: Search input, language selection, active dossier metrics, streaming synthesis progress, scorecard, and PDF export.
  - [x] `ui/views/__init__.py`: Aggregated re-exports of view components and state utilities.
  - [x] Refactored `app.py`: Transformed 1,275-line monolith into a 170-line coordinator.
  - [x] Verification: 100% pre-flight test pass (`./run.sh preflight`: linter across 43 files, system check, headless UI, and 3.4x speed benchmark).

---

## 🔌 Tier 2: Commercial Fundamental REST Integration (EODHD)
*Goal: Harden fundamental metrics against `yfinance` throttling and foreign IP blocks using European vendor EODHD with comprehensive BSE/NSE coverage.*

- [ ] **EODHD REST Integration & Resilient Fallback Adapter**
  - Vendor: EODHD (EOD Historical Data, France/EU) providing comprehensive Indian coverage across BSE and NSE.
  - Implement structured fallback in [`core/analysis/fundamentals.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/analysis/fundamentals.py):  
    `BSE Direct API` ➔ `EODHD REST API` ➔ `yfinance` ➔ `'N/A'`.
  - Configured via optional `EODHD_API_KEY` in [`.streamlit/secrets.toml`](file:///Users/lyndonpinto/Documents/Stock_Research_App/.streamlit/secrets.toml).
  - Supplies verified P/E, Market Cap, forward valuation multiples, balance sheets, and cash flows.

---

## 🧠 Tier 3: Behavioral Research & Decision Support Features
*Source: [`.antigravity/docs/BEHAVIORAL_RESEARCH_STUDY.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/.antigravity/docs/BEHAVIORAL_RESEARCH_STUDY.md)*

- [x] **P0: Cognitive Ergonomics & Typographic Foundation** *(Completed in `app.py`)*
  - **Tabular Lining Numerals (`tabular-nums`)**: Enforced fixed-width lining typography across all `stMetric`, DataFrames, tables, and KPI metrics to eliminate eye zigzag and cognitive reading fatigue.
  - **Color Scarcity Guidelines**: Monochromatic slate/neutral baseline UI; high-chroma red and green strictly reserved for governance alerts, value traps, and material drift to prevent alert fatigue.
  - **WCAG 2.2 AA Target Sizing**: Enforced 24x24 px minimum touch targets for all buttons, selectboxes, and accordion headers.
- [x] **P1: Normalized Cross-Stock Comparator** *(Completed: ⚖️ Peer Comparison tab with 3-tier Disparity Gates)*.
- [x] **P1.1: Institutional Peer Comparison Information Expansion (Analyst Deep-Dive)** *(Completed: Implemented 3-tab institutional layout in [`ui/comparison.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/ui/comparison.py) with 13 side-by-side financial/efficiency multiples, 7-pillar qualitative matrix with deep-dive expanders, and 3-axis disparity diagnostics)*
  - **Capital Efficiency & Profitability Card**: Side-by-side ROCE %, ROE %, Operating Margin (OPM), and Net Profit Margin (NPM).
  - **Valuation Band & Multiple Disparity**: Trailing P/E, Forward P/E, P/B, EV/EBITDA, Dividend Yield %, and 52-Week Range.
  - **Balance Sheet & Solvency Matrix**: Debt/Equity ratio and Current Ratio liquidity buffer.
  - **Qualitative Moat & 7-Pillar Health Scorecard**: 7-pillar side-by-side posture ratings with interactive methodology drilldowns.
  - **3-Tier Disparity Gate Diagnostic**: Automated cards auditing Sector Mismatch, Lifecycle Divergence, and Scale Divergence (≥100×).
- [x] **P2: The "Inversion Engine" / Charlie Munger Pre-Mortem & 7-Pillar Behavioral Ergonomics** *(Completed: Shneiderman progressive disclosure, WCAG 2.2 AA accessible palette with semantic iconography, anchoring bias guardrails in `core/analysis/metrics.py`, longitudinal drift sparklines in `ui/charts.py`, and Charlie Munger Pre-Mortem expander with immutable decision ledger logging in `ui/scorecard.py`)*
  - **Progressive Disclosure**: Default top 3 strategic pillars (Moat, Capital Allocation, Valuation) vs. All 7 pillars via smooth toggle.
  - **Color-Blind Accessible Palette**: High-contrast WCAG 2.2 AA palette (Teal/Amber/Vermilion) coupled with distinct semantic iconography (`💎`, `🏰`, `🛡️`, `⚠️`, `🚨`, `📉`), ensuring meaning is never encoded by color alone.
  - **Anchoring Bias Guardrail**: Dynamic computation of 52-week price range percentile and historical valuation quartiles (Q1–Q4) in [`core/analysis/metrics.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/analysis/metrics.py) to decouple market price drops from intrinsic worth.
  - **Longitudinal Drift Sparkline**: Altair sparkline in [`ui/charts.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/ui/charts.py) tracking ordinal quality scores across discrete historical snapshots to combat confirmation bias and the disposition effect.
  - **Charlie Munger Pre-Mortem Inversion**: Interactive module with structured failure vectors (Customer Concentration, Regulatory Chokepoint, Margin Squeeze) and immutable audit logging via `track_user_action("PREMORTEM", ...)`.
  - **Automated Regression Suite**: AppTest simulation wired into [`test_ui_headless.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/test_ui_headless.py) with 100% 4-tier pre-flight pass.
- [x] **P3: Differential Analysis & Thesis Drift Surveillance UX Overhaul**
  - *Context:* The differential analysis engine (`compare_revisions`) compares discrete historical snapshots to track qualitative 7-pillar drift and detect value traps. Hoisted directly above Pillar 1 with instant toast, auto-scroll, single-snapshot guidance, and interactive visual diff cards.
  - **Action Items Completed:**
    - [x] **Above-the-Fold Prominence:** Hoisted the Differential Surveillance Card directly below the valuation metrics row (above Pillar 1) whenever a comparison is triggered, eliminating the need to scroll below Pillar 7.
    - [x] **Visual Loading Confirmation:** Triggered an instant confirmation toast (`st.toast("⚖️ Differential comparison active: State A vs State B", icon="📊")`) and auto-scroll anchor directly to `#thesis-drift-anchor`.
    - [x] **Clear Single-Snapshot Explainer:** When a stock has only 1 snapshot, displays clear inline and expander guidance explaining that revision diffing activates automatically upon subsequent quarterly earnings filings or material price shifts (≥5%).
    - [x] **Interactive Visual Diff Cards & Clean Reset:** Rendered side-by-side pillar migration chips (`from ➔ to [🔻/🔺]`), value trap alert banner, quantitative metric delta table, reassuring 0-migration confirmation note, and an instant "✕ Close Differential" reset button that restores the active dossier.
    - [x] **Automated Regression Suite:** Wired interactive AppTest simulation in `test_ui_headless.py` and validated across 4-tier preflight pipeline.
- [ ] **P3.1: Post-Earnings Announcement Drift (PEAD) & SUE Anomaly Tracker**
  - Calculate Standardized Unexpected Earnings (SUE) on quarterly results and visualize 60-day empirical drift bands to combat loss aversion and the disposition effect.
- [ ] **P4: Forensic Cash Flow Quality Card**
  - 3-year variance table comparing Operating Cash Flow vs Net Profit to detect working-capital traps and aggressive revenue recognition.
- [ ] **P5: Promoter & Insider SAST Disparity Tracker**
  - Ingest BSE SAST insider trading and block deal feeds to track management skin-in-the-game.
- [x] **P6: Visual Source Attribution & Footnote Citations Engine** *(Completed: Grounding chunks extraction from Gemini & Perplexity, DB migration v006_report_citations with JSON dual-persistence, header source badge pill, mobile-responsive footnotes expander, and Sell-Side hyperlinked PDF appendix)*
  - Extract `grounding_chunks` (titles + URLs) from Gemini `google-genai` streams and `citations` array from Perplexity `sonar-pro` fallback.
  - Ingest official BSE corporate announcements and disclosures into the citations ledger.
  - Dual-persistence in `reports` and `report_revisions` tables (`citations_json` column via migration `v006_report_citations`).
  - Header Reference Pill: Render `📎 N Verified Primary Sources Grounded` badge in the executive dossier header alongside the material reason badge.
  - Interactive Citations Expander: Render `📚 Verified Regulatory Sources & Footnote Citations` expander with hyperlinked sources, domain classification, and SEBI safe-harbor compliance annotations.
  - Executive PDF Footnote Appendix: Render hyperlinked regulatory sources and filing citations in [`ui/pdf.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/ui/pdf.py) styled cleanly before the mandatory SEBI disclaimer.
- [ ] **P7: SEBI LODR Regulation 30/33 Forensic Red-Flag Sweeper**
  - Real-time ingestion and visual red-flagging of mandatory 24-hour disclosures: mid-term statutory auditor resignations, sudden management departures, and promoter share pledging surges.

---

## 💳 Tier 4: Monetization Architecture & Payment Gateway Integration (Razorpay + Supabase Auth)
*Goal: Implement payment structure and credit gates prior to public discovery, supporting platform development with a hybrid model tailored to Indian payment behavior.*

- [x] **Hybrid Monetization Architecture (Freemium + On-Demand Credits + Pro Membership)** *(Completed: Approved Option 2 +30% Markup)*
  - **Free Tier:** 100% free and open access to existing archived dossiers, live exchange quotes, peer comparison, and institutional PDF report downloads.
  - **Welcome Credits:** 2.0 Free Research Credits granted automatically upon initial sign-up to encourage platform discovery.
  - **On-Demand Credit Packs:**
    - Single Research Pass: ₹299 (1 full research credit)
    - Analyst 3-Pack: ₹699 (3 research credits, ~₹233/stock - Most Popular)
    - Portfolio 10-Pack: ₹1,799 (10 research credits, ~₹180/stock - Best Value)
  - **Institutional Pro Membership:**
    - Pro Monthly: ₹999 / month (40 fresh syntheses/mo, unlimited surgical updates, 50 watched equities in real-time surveillance, unlimited PDF downloads)
    - Pro Annual: ₹8,999 / year (~₹750/mo, 25% annual savings)
  - **Enterprise & B2B Bulk Packs:**
    - Corporate 50-Pack: ₹5,999 (~₹120/stock)
    - Enterprise 150-Pack: ₹16,999 (~₹113/stock)
- [x] **Dual-Bound Database Schema (Migration `v007_user_accounts_and_credits`)**
  - Applied migration `v007_user_accounts_and_credits` in [`core/db/connection.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/connection.py) across Supabase PostgreSQL and SQLite.
  - Built [`core/db/users.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/users.py) managing atomic transactions across `user_accounts`, `credit_transactions`, and `credit_usage_ledger`.
  - Re-exported user methods in [`core/db/__init__.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/__init__.py) and facade [`db.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/db.py).
- [x] **Supabase Auth & Session Module (`core/auth/`)**
  - Built [`core/auth/supabase_auth.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/auth/supabase_auth.py) supporting GoTrue REST endpoints, Google OAuth redirection (`get_google_oauth_url()`), Magic Link dispatch (`send_magic_link()`), and URL callback token handling (`handle_auth_callback()`).
  - Seamless frictionless onboarding: Instant verified email sign-in granting 2 free welcome credits.
- [x] **Billing & Razorpay Integration (`core/billing/`)**
  - Built [`core/billing/pricing.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/billing/pricing.py) with approved pricing tiers and action costs.
  - Built [`core/billing/razorpay.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/billing/razorpay.py) providing order creation via REST API, HMAC-SHA256 signature verification, instant sandbox testing mode, and printable HTML tax invoice generation (SAC 998314).
- [x] **Interactive UI Components (`ui/auth_ui.py` & `ui/billing_modal.py`)**
  - Sidebar user chip: displays profile avatar, email, research credit counter pill (`🪙 X.X Credits`), Pro badge, and 1-click Top-Up / Ledger / Sign-Out triggers.
  - Modal dialogs: `@st.dialog` for Login, Credit Top-Up, and Account Ledger with invoice downloads.
- [x] **Action Gating & Safe Harbor Billing Compliance**
  - Gated fresh live AI synthesis (`LIVE_SYNTHESIS`: 1.0 credit) in [`ui/views/state.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/ui/views/state.py) and surgical updates (`SURGICAL_REFRESH`: 0.25 credits, free for Pro) in [`ui/views/dossier_view.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/ui/views/dossier_view.py).
  - Preserved 100% free access for archived dossier retrieval, live exchange quotes, and PDF downloads.
  - Invoices and checkout screens describe services strictly as *"Financial Research Synthesis Software Utility — Computational Research Credits"*, retaining the mandatory non-advisory disclaimer.
- [x] **Automated Regression Suite**
  - Added module audits and schema verification to [`check_system.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/check_system.py).
  - Added headless UI simulation for guest sign-in and authenticated top-up triggers to [`test_ui_headless.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/test_ui_headless.py).

---

## 🌐 Tier 5: Discovery Architecture: SEO, GEO (Generative Engine Optimization) & Public Dossier Distribution
*Goal: Transform internal database research reports into indexable, high-authority public knowledge assets for traditional search engines (Google, Bing) and AI answer engines (Perplexity, ChatGPT Search, Gemini).*

- [ ] **Static Site Generation (SSG) & Headless Dossier Mirror**
  - Automatically export lightweight, pre-rendered semantic HTML snapshots of verified equity dossiers (`/dossier/<canonical_ticker>.html`).
  - Semantic HTML5 structure (`<h1>`, `<h2>`, `<article>`), `<meta>` tags, and OpenGraph/Twitter Card previews showcasing the 7-Pillar Health Matrix.
  - Embed `Schema.org` JSON-LD structured data (`Article`, `FinancialProduct`) for instant rich snippets and factual indexing by search crawlers.
- [ ] **Automated Dynamic Sitemap (`sitemap.xml`) & Disclosures Ingestion Feed**
  - Expose an automated XML sitemap listing canonical ticker URLs with accurate `<lastmod>` timestamps derived from `report_revisions`.
  - Provide an RSS/Atom corporate filing evaluation feed to notify search bots and AI aggregators within hours of material BSE disclosures.
- [ ] **Deep-Linking & Shareable Direct Dossier Routing**
  - Support direct query routing (e.g., `?ticker=TCS` or `?ticker=TATASTEEL`) so external search results link directly to active institutional dossiers.
- [ ] **SEBI Safe Harbor Static Compliance Enforcer**
  - Guarantee that all crawler-facing HTML mirrors append the immutable [`MANDATORY_SEBI_DISCLAIMER`](file:///Users/lyndonpinto/Documents/Stock_Research_App/db.py#L14-L23), enforce strictly diagnostic terminology, and omit any personalized or speculative investment targets.

---

## 📈 Tier 6: Strategic Multi-Asset Expansion
*Source: [`.antigravity/docs/STRATEGY.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/.antigravity/docs/STRATEGY.md)*

- [ ] **Tier 2: Mutual Fund Look-Through Engine**
  - Ingest mutual fund monthly portfolio disclosures (SEBI CAS / AMFI feeds).
  - Calculate weighted look-through scores for mutual funds based on the 7-pillar qualitative moat scores of their underlying equity holdings.
  - Track Mutual Fund Style Drift (detecting when large-cap funds chase mid-cap momentum or dilute quality).
- [ ] **Tier 3: Fixed Income & Yield Curve Engine**
  - Corporate bonds, Sovereign Gold Bonds (SGB), NCDs, and fixed deposit real-return diagnostics.
- [ ] **Capstone: Unified Qualitative Portfolio Audit**
  - Aggregation engine combining Equities + Mutual Funds + Fixed Income into an institutional-grade risk concentration and diversification audit.

