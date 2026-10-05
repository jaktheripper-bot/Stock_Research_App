- [ ] Build a public API endpoint for report access so external developers can consume reports programmatically.
- [ ] Add PDF export styling with embedded SEBI safe‑harbor disclaimer.
- [x] Implement archived report differential tracker (immutable report_revisions history).
- [x] Implement granular event alert system with material event categories and digest options.
- [x] Implement cross-company comparison with disparity warning and override workflow.
- [x] Add unit and integration tests for alerting and comparison features.
- [x] Decouple core database, analysis, billing, and auth stack from Streamlit runtime; build native SSR Admin & Telemetry Console.
- [ ] Add a way for the reports to be customised under the pro-desk & corporate & advisory bulk packs.
- [ ] Add research to be done on API ingestion for MSME analysis.
- [x] Keep backup step synchronized with future deployment changes (pre & post commit backups).

## Multi-Asset & Mutual Fund Look-Through Roadmap

### Priority 1: Fixed-Income & Debt Engine (Direct Foundation for Mutual Funds)
- [x] Build Corporate Debt & Debenture Schema: Ingest listed NCDs and Securitized Debt Instruments (SDIs) from BSE/NSE under the ₹10,000 SEBI framework.
- [x] Implement Credit Rating Surveillance Engine: Track CRA rating actions (CRISIL, ICRA, CARE), downgrade watches, and default probability metrics.
- [x] Build 5-Pillar Credit & Solvency Core: Compute Yield-to-Maturity (YTM), Macaulay Duration, Modified Duration, Asset Cover Ratio (ACR $\ge 1.25\times$), and Interest Coverage Ratio (ICR).
- [x] Tag Capital Hierarchy: Enforce seniority classification (Senior Secured vs. Unsecured vs. Subordinated vs. Perpetual AT1 write-down risk).

### Priority 2: Mutual Fund Portfolio Ingestion & Look-Through Engine
- [x] Develop AMFI Monthly Mutual Fund Portfolio Ingestion Pipeline: Ingest standardized monthly AMC portfolio disclosures across equity, debt, and hybrid schemes.
- [x] Implement Dual-Sleeve Mutual Fund Look-Through Engine:
      - Equity sleeve routed through verified 7-Pillar Stock Engine.
      - Debt/Debenture sleeve routed through 5-Pillar Credit & Duration Engine.
- [x] Implement True Diversification & Overlap Diagnostic: Compute Active Share ($AS \ge 60\%$) to expose closet indexing, Top 10 concentration, and cross-scheme duplicate holdings.
- [x] Build Risk-Adjusted Alpha & Downside Capture Calculator: Compute Sortino Ratio, Rolling 3Y/5Y Consistency, Hurst Exponent ($H > 0.5$), and Downside Capture Ratio ($DCR \le 75\%$).
- [x] Build Intermediary Fee Drag & Churn Analyzer: Quantify 10-year compounded wealth loss in Direct vs. Regular TER, and track Portfolio Turnover Ratio (PTR).

### Priority 3: Sovereign Curve & ETF Analytics
- [ ] Ingest Sovereign Risk-Free Benchmarks: Ingest RBI/FBIL T-Bills (91/182/364-day), 10-Yr G-Sec, and SDL yield curves.
- [ ] Build ETF Performance & Liquidity Matrix: Track Tracking Error, Impact Cost, and Exchange Liquidity spreads for Index, Debt (Bharat Bond), and Commodity ETFs.
- [ ] Implement Net Real Post-Tax Return Calculator: Model net purchasing power across FDs, Sovereign Bonds, and Corporate Debt across marginal tax slabs.

### Priority 4: Fractional Real Estate (SM REITs) & Sovereign Gold
- [ ] Build SEBI SM REIT & InvIT Tracking Module: Monitor completed asset occupancy ($\ge 95\%$), NDCF distribution upstreaming purity, and leverage ratios ($LTV \le 49\%$).
- [ ] Build SGB Secondary Market Discount & Yield Analyzer: Calculate annualized yields and tax-adjusted parity against Gold ETFs and physical gold.

### Priority 5: Retail Safety & Shadow-Banking Diagnostic Radar
- [ ] Build Alternative Yield Risk Scorecard: Diagnostic guardrail highlighting counterparty risks in unregulated gold leasing (Gullak Gold+) and RBI-restricted P2P lending.
