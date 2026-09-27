# Stock Research App - Project Directives & Compliance

Refer to the complete specifications in `.antigravity/docs/` and `.agents/rules/`.

## Mandatory Directives
1. **Zero-Hallucination Data Integrity:** Synthetic or AI-estimated financial metrics (P/E, Market Cap, 52-Week Range, Price) are strictly prohibited. Hard stop on live exchange quote failures. Return `'N/A'` or raise clean exceptions if API fetches fail.
2. **SEBI Safe Harbor Compliance:** Strictly no `BUY`, `HOLD`, or `SELL` recommendations or badges. Use descriptive diagnostic classifications only (e.g., 'Watchlist', 'Clean', 'Wide'). Never collect user personal finance data for personalized advice. Append the mandatory disclaimer to all views and exports.
3. **Data Ingestion & Resolution:** 5-tier BSE resolution hierarchy. Fetch direct from BSE exchange APIs; fallback to consolidated `yfinance` returning `'N/A'`.
4. **Caching & Dual Persistence:** Dual-binding for PostgreSQL (production) and SQLite (`reports.db`, local). 2-tier caching with delta gating (>=5% price move, new filing, or >14 days). Gemini Flash cascade failover to Perplexity `sonar-pro`.
5. **Multi-Asset Strategic Roadmap:** Build on Tier 1 (Equities Thesis Engine) with qualitative time-series surveillance (`report_revisions` tracking 7-pillar drift and "value traps") to enable future Tier 2 (Mutual Fund Look-Through & Style Drift), Tier 3 (Fixed Income), and Capstone (Portfolio Audit).
6. **Deployment & Runtime Hygiene:** Enforce 3-tier pre-flight validation (`check_system.py`, `PROJECT_STATUS.md`, `test_ui_headless.py`) before production pushes. Enforce IST timestamps across all views and `[CANONICAL_TICKER]_[DD-MM-YYYY]_Research_Report.pdf` export naming.
