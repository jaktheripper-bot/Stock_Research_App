# Stock Research App — Production Release Ledger & Engineering Backlog

This document tracks all changes deployed to production and active engineering roadmap items.

---

## Part 1: Production Deployment Ledger (Live Features)

| Release Date | Git Commit | Scope / Feature | Production Route(s) | Status |
| :--- | :--- | :--- | :--- | :--- |
| **03-Oct-2026** | *Pending* | **The Morning Discovery Reel (Option B: Full Grounded Synthesis)**<br>• Nightly screening of 10–15 under-the-radar equities across diverse sectors<br>• Rigorous financial health gates (ROCE >= 15%, D/E <= 0.6, Micro/Small-Cap)<br>• Option B full institutional-grade 7-pillar grounded report generation with historical filings<br>• Dedicated discovery hub with interactive sector filtering (`/discovery`)<br>• Homepage highlights reel integration & BSE filing catalyst links<br>• Database migration `v008_discovery_reel` (PostgreSQL / SQLite dual-bound)<br>• Automated batch worker (`scripts/run_discovery_worker.py`) & admin trigger API | `/discovery`<br>`/`<br>`/api/admin/run-discovery` | **LIVE** |
| **03-Oct-2026** | `35e15f8` | **Dossier Ergonomics & Technical Chart Restoration**<br>• Stripped redundant markdown Health Matrix bullet list<br>• Restored interactive 6-month Price Momentum & 50-DMA trendline chart<br>• Automated trend inference and Chart.js integration<br>• Permanent FastAPI Web Portal test suite (`test_fastapi_web.py`) | `/dossier/{ticker}` | **LIVE** |
| **03-Oct-2026** | `ad6dbd8` | **Modern Web Portal & Complete Feature Port**<br>• Institutional Peer Comparator & 3-Tier Disparity Gates<br>• Charlie Munger Pre-Mortem Inversion Module<br>• Multi-Quarter Thesis Drift Surveillance & Value Trap Banner<br>• Anchoring Bias Guardrail & 7-Pillar Scorecard Strip<br>• Razorpay Live Checkout with Guaranteed Account Crediting<br>• Statutory Compliance & Policy Disclosures | `/`<br>`/compare`<br>`/dossier/{ticker}`<br>`/pricing`<br>`/terms`, `/privacy`, `/refund-policy` | **LIVE** |
| **03-Oct-2026** | `6629ddc` | **Monetization & Credit Gating Engine**<br>• User accounts & 2.0 welcome credit allocation<br>• Credit-gated live synthesis with auto-refund on failure<br>• Dual-bound PostgreSQL/SQLite user schema (`v007`) | `/api/auth/signin`<br>`/api/synthesize`<br>`/api/user/{id}` | **LIVE** |
| **02-Oct-2026** | `9b3a0c2` | **Verified Citations & Footnote Engine**<br>• Primary BSE filing & regulatory source grounding<br>• Footnote citations persistence (`v006`)<br>• Institutional PDF generation with hyperlinked appendix | `/dossier/{ticker}`<br>`/api/pdf/{ticker}` | **LIVE** |
| **01-Oct-2026** | `5b497f1` | **Behavioral Ergonomics & Disparity Diagnostics**<br>• 13 side-by-side financial multiples & ratios<br>• Sector, Lifecycle, and Scale Disparity Gates (>=100x)<br>• Tabular lining typography (`tabular-nums`) | Core Analysis Engine | **LIVE** |
| **30-Sep-2026** | `4a18f2d` | **Three-Phase Architectural Modularization**<br>• `core/db/`: connection pooling, migrations, queries<br>• `core/analysis/`: fundamentals, engine, delta, parser<br>• `ui/views/`: modular views and state coordinator | Internal Core Architecture | **LIVE** |
| **29-Sep-2026** | `1c890e4` | **Foundation: 7-Pillar Synthesis & Exchange Ingestion**<br>• BSE scrip master resolution (5,000+ equities)<br>• Zero-hallucination exchange metrics ingestion<br>• Dual PostgreSQL/SQLite persistence (`v001`–`v005`) | Core Analysis Engine | **LIVE** |

### Verified Live Capabilities (Current Production Environment)
1. **Public Web Portal (`web/`):** Full Server-Side Rendered (SSR) portal running on FastAPI with sub-50ms TTFB.
2. **Peer Comparison Engine (`/compare`):** Side-by-side analysis of any two BSE/NSE stocks with 3 automated disparity gates (Sector, Lifecycle, Scale >= 100x) and 13 financial multiples.
3. **Behavioral Inversion Module (`/dossier/{ticker}`):** Charlie Munger Pre-Mortem counter-thesis capture committing to an immutable audit decision ledger.
4. **Drift Surveillance (`/dossier/{ticker}`):** Multi-quarter differential tracking detecting pillar migrations and flagging potential value traps.
5. **Anchoring Bias Guardrail (`/dossier/{ticker}`):** 52-week position percentile and historical P/E valuation quartiles (Q1–Q4).
6. **Regulatory Footnotes & Citations:** Primary source attributions hyperlinked and rendered across web dossiers and PDF report exports.
7. **Razorpay Payments & Credit Allocation (`/pricing`):** Seamless checkout supporting UPI (GPay, PhonePe), Cards, and NetBanking with authenticated account linking and automated tax receipts (SAC 998314).
8. **Statutory Safe-Harbor Disclosures:** Dedicated legal policy suite (`/terms`, `/privacy`, `/refund-policy`, `/shipping-policy`, `/contact`, `/disclaimer`).

---

## Part 2: Engineering Roadmap & Pending Backlog (Queued)

Tasks below represent planned feature expansions and architectural optimizations. Each task is classified by priority, target phase, and functional scope.

### Priority 1: Architectural Unification (Non-Urgent)
*Target: Complete transition away from dual-runtime to a single FastAPI stack.*

* [ ] **Phase 4: Full Platform Unification onto FastAPI (Retire Streamlit)**
  * **Operator Control Room Port (`/admin`):** Build a secure, password-protected `/admin` route in `web/main.py` (authenticated via `ADMIN_PASSCODE`) supporting database migration inspection, Gemini quota/spend monitoring, batch runs, and credit ledger audits.
  * **Core Caching Decoupling:** Replace `@st.cache_data` in `core/analysis/fundamentals.py`, `alerts.py`, and `bse_master.py` with standard Python in-memory TTL caching (e.g. `cachetools.TTLCache`), eliminating `MemoryCacheStorageManager` runtime warnings.
  * **Test Suite Modernization:** Replace Streamlit `test_ui_headless.py` (`AppTest`) with an automated FastAPI `TestClient` suite covering all SSR routes, APIs, and billing transactions.
  * **Dependency Purge:** Remove `streamlit` and transitive packages (`tornado`, `pydeck`, `protobuf`, `altair`) from `requirements.txt`, archive `app.py` and `admin.py`, and reduce Docker container size from ~1.3 GB to ~350 MB.

---

### Priority 2: Ingestion & Commercial Data Hardening
*Target: Increase resilience against exchange throttling and upstream rate limits.*

* [ ] **Tier 2: Commercial Fundamental REST Integration (EODHD)**
  * Implement structured fallback in `core/analysis/fundamentals.py`:  
    `BSE Direct API` ➔ `EODHD REST API` ➔ `yfinance` ➔ `'N/A'`.
  * Protect fundamental metrics against foreign IP blocks and rate limits.
  * Wire optional `EODHD_API_KEY` configuration.

---

### Priority 3: Forensic & Behavioral Analytical Depth
*Target: Advanced accounting fraud detection and cognitive bias mitigation.*

* [ ] **P3.1: Post-Earnings Announcement Drift (PEAD) & SUE Anomaly Tracker**
  * Calculate Standardized Unexpected Earnings (SUE) on quarterly earnings releases.
  * Visualize 60-day post-earnings empirical drift bands to combat loss aversion and disposition effect.
* [ ] **P4: Forensic Cash Flow Quality Card**
  * 3-year comparative variance analysis: Operating Cash Flow (OCF) vs. Net Profit.
  * Automated detection of working-capital traps and aggressive revenue recognition.
* [ ] **P5: Promoter & Insider SAST Disparity Tracker**
  * Ingest BSE SAST insider trading and block deal feeds to track management skin-in-the-game.
* [ ] **P7: SEBI LODR Regulation 30/33 Forensic Red-Flag Sweeper**
  * Real-time automated ingestion of mandatory 24-hour disclosures: auditor resignations, management turnover, and promoter share pledging surges.

---

### Priority 4: Search Discovery & Headless Distribution
*Target: Indexability across traditional search (Google, Bing) and AI answer engines (Perplexity, ChatGPT).*

* [ ] **Static Site Generation (SSG) & Headless Mirror**
  * Automatically export lightweight, pre-rendered semantic HTML snapshots (`/dossier/<canonical_ticker>.html`).
  * Embed `Schema.org` JSON-LD structured data (`Article`, `FinancialProduct`) for rich search snippet indexing.
* [ ] **Automated Dynamic Sitemap (`sitemap.xml`) & Disclosures Feed**
  * Expose an automated XML sitemap listing canonical ticker URLs with accurate `<lastmod>` timestamps derived from `report_revisions`.
  * Expose an RSS/Atom corporate filing evaluation feed to alert search crawlers within hours of material BSE disclosures.

---

### Priority 5: Strategic Multi-Asset Expansion
*Target: Extend 7-pillar methodology across investment classes.*

* [ ] **Tier 2: Mutual Fund Look-Through Engine**
  * Ingest monthly mutual fund portfolio disclosures (SEBI CAS / AMFI feeds).
  * Calculate portfolio-weighted quality scores based on the 7-pillar qualitative moat scores of underlying holdings.
  * Detect Mutual Fund Style Drift (e.g. large-cap funds chasing momentum in mid/small caps).
* [ ] **Tier 3: Fixed Income & Yield Curve Engine**
  * Real-return diagnostics for Corporate Bonds, Sovereign Gold Bonds (SGB), NCDs, and fixed deposits.
* [ ] **Capstone: Unified Qualitative Portfolio Audit**
  * Comprehensive risk concentration audit aggregating Equities + Mutual Funds + Fixed Income into an institutional-grade governance report.
