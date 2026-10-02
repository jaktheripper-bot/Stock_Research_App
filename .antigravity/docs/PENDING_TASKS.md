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
- [ ] **P1.1: Institutional Peer Comparison Information Expansion (Analyst Deep-Dive)**
  *Evaluation of essential diagnostic dimensions to elevate comparison beyond basic multiples:*
  - **Capital Efficiency & Profitability Card**: Side-by-side ROCE %, ROE %, Operating Margin %, and OCF/EBITDA cash conversion.
  - **Valuation Band & Multiple Disparity**: EV/EBITDA, P/B, Dividend Yield, and historical 5-year P/E percentile comparison.
  - **Balance Sheet & Solvency Matrix**: Debt/Equity ratio, Interest Coverage, and Net Debt/EBITDA.
  - **Shareholding & Promoter Alignment**: Promoter Holding %, Promoter Pledge % (critical Indian risk metric), and FII/DII institutional trend.
  - **Head-to-Head Comparative Radar Chart**: Interactive spider/radar chart comparing Company A vs Company B across the 7 institutional pillars and return ratios.
  - **Qualitative Moat & Divergence Diagnostic**: Side-by-side narrative contrasting competitive advantages, pricing power, and primary operational risks.
- [ ] **P2: The "Inversion Engine" / Charlie Munger Pre-Mortem**
  - Integrate a mandatory counter-thesis section modeling the Top 3 Failure Modes (Customer Concentration, Regulatory/Policy Vulnerability, Balance Sheet Sensitivity) to prevent narrative seduction.
- [ ] **P3: Sunk-Cost & Thesis Drift Prompter**
  - Automated alert comparing the current quarter against historical baseline snapshots in `report_revisions` to prompt: *"Your baseline thesis was [High Moat / Low Debt]. Current metrics show [Moat Compression]. Would you buy at today's price?"*
- [ ] **P4: Forensic Cash Flow Quality Card**
  - 3-year variance table comparing Operating Cash Flow vs Net Profit to detect working-capital traps and aggressive revenue recognition.
- [ ] **P5: Promoter & Insider SAST Disparity Tracker**
  - Ingest BSE SAST insider trading and block deal feeds to track management skin-in-the-game.

---

## 📈 Tier 4: Strategic Multi-Asset Expansion
*Source: [`.antigravity/docs/STRATEGY.md`](file:///Users/lyndonpinto/Documents/Stock_Research_App/.antigravity/docs/STRATEGY.md)*

- [ ] **Tier 2: Mutual Fund Look-Through Engine**
  - Ingest mutual fund monthly portfolio disclosures (SEBI CAS / AMFI feeds).
  - Calculate weighted look-through scores for mutual funds based on the 7-pillar qualitative moat scores of their underlying equity holdings.
  - Track Mutual Fund Style Drift (detecting when large-cap funds chase mid-cap momentum or dilute quality).
- [ ] **Tier 3: Fixed Income & Yield Curve Engine**
  - Corporate bonds, Sovereign Gold Bonds (SGB), NCDs, and fixed deposit real-return diagnostics.
- [ ] **Capstone: Unified Qualitative Portfolio Audit**
  - Aggregation engine combining Equities + Mutual Funds + Fixed Income into an institutional-grade risk concentration and diversification audit.

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
