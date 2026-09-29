# Project Backlog & Pending Tasks Checklist

> Comprehensive master checklist tracking architectural hardening, operational optimizations, behavioral features, and strategic roadmap milestones for the Stock Research App.

---

## 🛠️ Tier 1: Immediate Script Optimization & Code Cleanliness (From Script Audit)
*Goal: Prune leftover code, eliminate memory/descriptor leaks, and optimize request latency.*

- [ ] **Purge Dead / Unused Imports**
  - [`alerts.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/alerts.py): Remove unused imports (`os`, `re`, `timezone`, unused `db` functions).
  - [`analyzer.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/analyzer.py): Remove unused imports (`sys`, `normalize_stock_data`, `pass_pre_screening_gates`).
  - [`app.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/app.py): Clean up unused imports at lines 1–65 (e.g. `concurrent.futures`, `sys`, `timezone`, modularized chart/formatter helpers).
  - [`check_system.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/check_system.py), [`ci/checkpoint_manager.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/ci/checkpoint_manager.py), [`test_ui_headless.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/test_ui_headless.py).
- [ ] **Prune Dead Functions**
  - [`bse_master.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/bse_master.py#L55-L74): Remove `find_fuzzy_scrip_match()` (unreferenced dead function).
  - [`screener.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/screener.py): Either connect `pass_pre_screening_gates()` to enforce real liquidity/market cap gating, or prune it to eliminate vestigial code.
- [ ] **External BSE Announcement Exchange Caching**
  - In [`analyzer.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/analyzer.py) and [`alerts.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/alerts.py): Decorate `fetch_latest_bse_announcement()` and `fetch_bse_announcements()` with `@st.cache_data(ttl=300)` to eliminate duplicate 200–600ms HTTP requests during report rendering and alert sweeps.
- [ ] **Fix Process Descriptor Leak in P/E Resolver**
  - [`analyzer.py:262`](file:///Users/lyndonpinto/Documents/Stock_Research_App/analyzer.py#L262): Replace `open(os.devnull, "w")` file handle allocation with in-memory `contextlib.redirect_stderr(io.StringIO())`.
- [ ] **In-Memory Ticker Suggestion Cache**
  - [`bse_master.py:237`](file:///Users/lyndonpinto/Documents/Stock_Research_App/bse_master.py#L237): Cache the deduplicated search candidate list in memory rather than reconstructing sets across thousands of records on every keystroke.
- [ ] **SEBI Disclaimer Standardization**
  - Update [`ui/pdf.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/ui/pdf.py) and in-page footer in [`app.py`](file:///Users/lyndonpinto/Documents/Stock_Research_App/app.py) to use the canonical [`MANDATORY_SEBI_DISCLAIMER`](file:///Users/lyndonpinto/Documents/Stock_Research_App/db.py#L14-L23) across all export surfaces.

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
