- [x] Build a public API endpoint for report access so external developers can consume reports programmatically (`/api/v1/reports/{ticker}`).
- [x] Add PDF export styling with embedded SEBI safe‑harbor disclaimer and document receipt tracking (`core/reporting/pdf.py`).
- [x] Implement archived report differential tracker (immutable report_revisions history).
- [x] Implement granular event alert system with material event categories and digest options.
- [x] Implement cross-company comparison with disparity warning and override workflow.
- [x] Add unit and integration tests for alerting and comparison features.
- [x] Decouple core database, analysis, billing, and auth stack from Streamlit runtime; build native SSR Admin & Telemetry Console.
- [x] Add a way for the reports to be customised under the pro-desk & corporate & advisory bulk packs (firm logo, advisory reg. no, client name, custom disclosures).
- [x] Add a way for users to search for specific investment products as well (omni-search across stocks, debt/NCDs, and mutual funds via `/search` & `/api/search/products`).
- [ ] Add research to be done on API ingestion for MSME analysis.
- [x] Keep backup step synchronized with future deployment changes (pre & post commit backups).

## Security & Access Control (Blocking)
- [x] Replace admin password gate with Google sign-in + second factor, admin allowlist (roles), and per-admin audit trail of every console action.
- [x] Fix public site sign-in: `/api/auth/signin` accepts any email with no verification. Hardened with verified Google OAuth + 6-digit Email OTP (`core/auth/otp.py`, `/api/auth/send-otp`, `/api/auth/verify-otp`, signed session cookie).
- [x] Protect `/api/admin/run-discovery` (requires `x_admin_key` or authenticated admin session cookie).
- [x] Review BSE/NSE display licensing and risk exposures for monetized dossiers (detailed evaluation & migration plan in [source_evaluation.md](file:///Users/lyndonpinto/Documents/Stock_Research_App/source_evaluation.md)).

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
- [x] **P2 Remediation:** Replace hand-typed seed data (`seed_default_mutual_funds`) with live AMFI `NAVAll.txt` ingestion + scheme master; unresearched stocks strictly marked as `N/A` with coverage pending and zero-hallucination compliance.
- [x] **P2 Remediation:** Add `ALWAYS_ON_ASSET_SCAN` rule + scheduled MF/debt surveillance engine: daily diff → NEW / CHANGED / CLOSED-MERGED → ARCHIVED (append-only), logged to immutable `asset_scan_runs` ledger and surfaced in `/admin?tab=assets` console.

### Priority 3: Sovereign Curve & ETF Analytics
- [x] Ingest Sovereign Risk-Free Benchmarks: Ingest RBI/FBIL T-Bills (91/182/364-day), 10-Yr G-Sec, and SDL yield curves (`core/db/sovereign.py`, `core/analysis/sovereign_engine.py`, `/sovereign`, `/api/sovereign/curve`).
- [x] Build ETF Performance & Liquidity Matrix: Track Tracking Error, Impact Cost, and Exchange Liquidity spreads for Index, Debt (Bharat Bond), and Commodity ETFs (`core/analysis/etf_engine.py`, `/etfs`, `/api/etfs/matrix`).
- [x] Implement Net Real Post-Tax Return Calculator: Model net purchasing power across FDs, Sovereign Bonds, and Corporate Debt across marginal tax slabs using MOSPI CPI inflation deflator (`core/analysis/tax_calculator.py`, `/calculator/tax`, `/api/calculator/tax-return`).
- Free sources (Tier A): AMFI NAVAll + Tracking Error disclosures, RBI auction press releases (T-Bill/G-Sec/SDL), RBI DBIE, MOSPI CPI API, SEBI NFO filings, FY-versioned tax rules.
- Paid / licensed sources to evaluate (add value, required for public display):
  - [ ] NSE Data & Analytics licence: EOD / delayed display of ETF prices, volumes, index levels (delayed data ~₹1.4L/yr per medium; EOD on quote).
  - [ ] FBIL redistribution licence: official T-Bill / G-Sec par yield / SDL curves (fallback: public RBI auction cut-offs).
  - [ ] CCIL market data: NDS-OM secondary G-Sec trade yields & liquidity.
  - [ ] ACE MF (Accord Fintech) or CMOTS feed: normalised AMC portfolios, TER, TE across all AMCs (replaces ~45 AMC scrapers).
  - [ ] EODHD commercial licence: confirm whether existing key can be upgraded to cover public NSE display.
  - [ ] CRISIL / ICRA bond valuation feed: debt-ETF underlying bond pricing.

### Priority 4: Fractional Real Estate (SM REITs) & Sovereign Gold
- [x] Build SEBI SM REIT & InvIT Tracking Module: Monitor completed asset occupancy ($\ge 95\%$), NDCF distribution upstreaming purity, and leverage ratios ($LTV \le 49\%$) under SEBI (REIT) (Amendment) Regulations 2024 (`core/db/reits.py`, `core/analysis/reit_engine.py`, `/reits`, `/api/reits/directory`).
- [x] Build SGB Secondary Market Discount & Yield Analyzer: Calculate annualized yields and tax-adjusted parity against Gold ETFs and physical gold with Section 47(viic) capital gains tax exemption (`core/analysis/sgb_engine.py`, `/api/sgb/tranches`).

### Priority 5: Retail Safety & Shadow-Banking Diagnostic Radar
- [x] Build Alternative Yield Risk Scorecard: Diagnostic guardrail highlighting counterparty risks in unregulated gold leasing (Gullak Gold+), RBI-restricted P2P lending (12Club/LiquiLoans), and unrated NBFC deposits with 0-100 Danger Score (`core/db/safety_radar.py`, `core/analysis/safety_radar.py`, `/safety-radar`, `/api/safety-radar`).
