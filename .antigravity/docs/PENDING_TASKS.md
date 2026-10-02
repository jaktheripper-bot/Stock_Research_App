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
- [ ] **Phase 2: Modularize `analyzer.py` (1,375 lines) into `core/analysis/`**
  - [ ] `core/analysis/fundamentals.py`: Direct BSE scrip resolution, quotes, valuation ratios, and balance sheet metrics.
  - [ ] `core/analysis/engine.py`: Flash cascade failover, Perplexity `sonar-pro` router, prompt templates, structured output parsing.
  - [ ] `core/analysis/delta.py`: 2-tier caching, delta gating (>=5% price move, filings, >14 days), surgical refreshes.
  - [ ] `core/analysis/comparator.py`: Side-by-side peer comparison, disparity detection, 7-pillar alignment.
  - [ ] Root `analyzer.py` facade maintaining existing signatures.
- [ ] **Phase 3: Modularize `app.py` (1,275 lines) into `ui/views/`**
  - [ ] `ui/views/dossier_view.py`: Main stock search, report synthesis, 7-pillar scorecard, citations expander.
  - [ ] `ui/views/comparison_view.py`: Peer comparison container and disparity alerts.
  - [ ] `ui/views/archive_view.py`: Browse existing 80+ reports, revision history, and full downloads.
  - [ ] `ui/views/alerts_view.py`: Surveillance notifications and triage dashboard.
  - [ ] `ui/views/admin_view.py`: Telemetry, demographics, user journeys, and cost savings analytics.

---

## 🔌 Tier 2: Commercial Fundamental REST Integration (FMP / TwelveData)
*Goal: Harden fundamental metrics against `yfinance` throttling and foreign IP blocks.*

- [ ] **Wire Configured API Keys to Ingestion Hierarchy**
  - Credentials already present in [`.streamlit/secrets.toml`](file:///Users/lyndonpinto/Documents/Stock_Research_App/.streamlit/secrets.toml):
    - `FMP_API_KEY` (Financial Modeling Prep)
    - `TWELVE_DATA_API_KEY`
  - Implement structured fallback in [`analyzer.py:get_stock_fundamentals()`](file:///Users/lyndonpinto/Documents/Stock_Research_App/analyzer.py):  
    `BSE Direct API` ➔ `FMP REST API` ➔ `Twelve Data API` ➔ `yfinance` ➔ `'N/A'`.

---

## 🧠 Tier 3: Behavioral Research & Decision Support Features
*Source: [`.antigravity/docs/BEHAVIORAL_RESEARCH_STUDY.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/.antigravity/docs/BEHAVIORAL_RESEARCH_STUDY.md)*

- [x] **P1: Normalized Cross-Stock Comparator** *(Completed: ⚖️ Peer Comparison tab with 3-tier Disparity Gates)*.
- [x] **P1.1: Institutional Peer Comparison Information Expansion (Analyst Deep-Dive)** *(Completed: Implemented 3-tab institutional layout in [`ui/comparison.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/ui/comparison.py) with 13 side-by-side financial/efficiency multiples, 7-pillar qualitative matrix with deep-dive expanders, and 3-axis disparity diagnostics)*
  - **Capital Efficiency & Profitability Card**: Side-by-side ROCE %, ROE %, Operating Margin (OPM), and Net Profit Margin (NPM).
  - **Valuation Band & Multiple Disparity**: Trailing P/E, Forward P/E, P/B, EV/EBITDA, Dividend Yield %, and 52-Week Range.
  - **Balance Sheet & Solvency Matrix**: Debt/Equity ratio and Current Ratio liquidity buffer.
  - **Qualitative Moat & 7-Pillar Health Scorecard**: 7-pillar side-by-side posture ratings with interactive methodology drilldowns.
  - **3-Tier Disparity Gate Diagnostic**: Automated cards auditing Sector Mismatch, Lifecycle Divergence, and Scale Divergence (≥100×).
- [ ] **P2: The "Inversion Engine" / Charlie Munger Pre-Mortem**
  - Integrate a mandatory counter-thesis section modeling the Top 3 Failure Modes (Customer Concentration, Regulatory/Policy Vulnerability, Balance Sheet Sensitivity) to prevent narrative seduction.
- [ ] **P3: Sunk-Cost & Thesis Drift Prompter**
  - Automated alert comparing the current quarter against historical baseline snapshots in `report_revisions` to prompt: *"Your baseline thesis was [High Moat / Low Debt]. Current metrics show [Moat Compression]. Would you buy at today's price?"*
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

---

## 💳 Tier 4: Monetization Architecture & Payment Gateway Integration (Razorpay + Supabase Auth)
*Goal: Implement payment structure and credit gates prior to public discovery, supporting platform development with a hybrid model tailored to Indian payment behavior.*

- [ ] **Hybrid Monetization Architecture (Freemium + On-Demand Credits + Pro Membership)**
  - Free Tier: Public access to existing archived dossiers, live exchange quotes, and basic 2-stock comparison.
  - On-Demand Credit Packs (Micropayments via UPI): ₹199 for 1 fresh live AI synthesis + PDF export (or ₹499 for 3) via frictionless UPI QR / GPay / PhonePe checkout.
  - Pro Institutional Membership: ₹799 / month or ₹5,999 / year for unlimited report syntheses, full peer comparison engine, live watchlist surveillance alerts, and custom PDF export branding.
- [ ] **Supabase User Accounts & Credit Ledger**
  - Implement Supabase Auth (Google OAuth & Magic Link login) in Streamlit.
  - Create `user_accounts` table: `id`, `email`, `credits_remaining`, `subscription_tier` (`free`, `pro_monthly`, `pro_annual`), `expires_at`.
- [ ] **Razorpay Payment Gateway Integration**
  - Integrate Razorpay Python SDK server-side order generation (`orders.create`).
  - Streamlit checkout modal via `components.v1.html` or Razorpay hosted payment links.
  - Webhook listener to handle `payment.captured` and automatically credit user balances in real time.
- [ ] **Gated Execution & Safe Harbor Billing Compliance**
  - Gate "⚡ Synthesize Report" and "📄 Download Executive PDF" actions behind active credits or Pro subscription.
  - SEBI Safe Harbor Compliance: Invoice line-items and checkout screens bill strictly for *"Financial Research Synthesis Software Utility"*, retaining the mandatory non-advisory disclaimer.

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

