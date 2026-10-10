# Competitive Landscape Analysis: Industry Baselines vs. Stock Research App
**Document Type:** Strategic Research & Competitive Analysis Blueprint  
**Target Storage:** `docs/competitive_analysis_baseline_and_action_plan.md`  
**Status:** Review Draft (Execution Deferred Pending User Sign-Off)  
**Governing Standard:** SEBI Research Analysts Regulations, 2014 Section 2(u) (Non-Advisory Analytical Diagnostic)

---

## 1. Executive Summary & Research Scope

Retail and institutional investors in India navigate an increasingly fragmented wealth ecosystem. Over ₹35 lakh crore sits in equity mutual funds, trillions in corporate debentures, and millions of households participate in sovereign gold bonds, REITs, and bank fixed deposits.

However, the platforms tracking and reporting on these investment options suffer from a **systemic analytical plateau**:
1. **The Backward-Looking Ratio Trap:** 95% of platforms report lagging trailing returns (1Y/3Y/5Y CAGR) and historical accounting ratios (P/E, ROCE, Sharpe Ratio).
2. **The Distribution Channel Conflict:** Major aggregators (Groww, Zerodha, INDmoney, Wint Wealth) monetize via brokerage flow, mutual fund distribution commissions, or debt placement fees. Consequently, they cannot deliver objective, harsh audits of popular funds or debt offerings.
3. **The Silo Problem:** Equities, mutual funds, debt, real estate, and sovereign macro are segregated into isolated tools with zero cross-asset intelligence.

### The Purpose of This Document
This research establishes:
- **The Baseline:** What existing market leaders provide today across each asset class.
- **Our Offering Over & Above:** How our exchange-grounded, multi-asset forensic architecture and autonomous intelligence squads deliver unmatched analytical rigor.
- **Action Plan:** A prioritized, step-by-step roadmap to solidify our moat before taking new features live.

---

## 2. Competitive Landscape Deep Dive by Asset Class

### Category A: Direct Indian Equities

| Platform | Primary Model | Data Sourcing | Core Features | Critical Analytical Blind Spot |
| :--- | :--- | :--- | :--- | :--- |
| **Screener.in** | Free / Subscription DIY Terminal | C-MOTS / Exchange PDFs | 15-year financial statements, customizable query screeners, concall transcripts, export to Excel. | **Zero Qualitative Synthesis:** Completely unopinionated. Does not evaluate business moats, promoter integrity, TAM runway, or why a stock dropped 30%. |
| **Trendlyne** | Freemium Analytics | Exchange feeds, Sell-Side Broker Feeds | DVM Scores (Durability, Valuation, Momentum), broker consensus price targets, earnings call transcripts, superstar portfolios. | **Conflicted Consensus:** Relies heavily on sell-side broker targets (historically biased to 'Buy'); DVM factor scoring is generic algorithmic box-ticking without concall context. |
| **Tijori Finance** | Freemium Fundamental Terminal | Primary Filings, Customs, Industry Reports | Product-level revenue splits, operational capacity utilization, raw material input cost tracking, market share. | **Data Density without Verdict:** Rich operational metrics, but lacks automated forensic auditing, capital allocation stress-testing, or multi-asset look-through. |
| **Tickertape** | Retail B2C Portal | CMIE / Exchanges | Visual scorecards (Profitability, Entry Point, Red Flags), basic DCF fair value, peer comparison. | **Shallow Depth:** Geared for beginners; treats companies as tickers rather than complex operating businesses; lacks deep balance sheet forensics. |
| **Simply Wall St** | Global Visual Platform | S&P Capital IQ | Snowflake graphic (Value, Future, Past, Health, Dividend), visual DCF gauge, competitor comparisons. | **Algorithmic Hallucination:** Generic programmatic models frequently miscalculate intrinsic value for cyclical Indian sectors (metals, NBFCs, holding co discounts). |

---

### Category B: Mutual Funds & ETFs

| Platform | Primary Model | Data Sourcing | Core Features | Critical Analytical Blind Spot |
| :--- | :--- | :--- | :--- | :--- |
| **Value Research** | Advisory / Aggregator | AMFI / AMC Factsheets | 1–5 Star ratings based on trailing risk-adjusted returns, portfolio overlap tool, category returns, asset allocation splits. | **Chasing Past Performance:** Star ratings are purely backward-looking. A 5-star fund whose manager is buying low-quality, overvalued stocks remains rated 5 stars until NAV collapses. |
| **Morningstar India** | Institutional Research | Proprietary Institutional DB | Style Box (Growth/Value/Blend), Medalist qualitative analyst ratings, Portfolio X-Ray, sector allocations. | **Enterprise Cost & Slow Refresh:** Top features locked behind Morningstar Direct ($10k+/yr); retail coverage is slow and misses Indian mid/small-cap corporate governance subtleties. |
| **Rupeevest / Advisorkhoj** | Distributor / B2B | AMFI / NSE | Rolling returns calculators, SIP performance matrices, portfolio overlap, category quartiles. | **Pure Mathematics:** Zero look-through qualitative analysis. They report *what* happened to the NAV, never *why* the underlying businesses succeeded or failed. |

---

### Category C: Corporate Debt, NCDs & SDIs

| Platform | Primary Model | Data Sourcing | Core Features | Critical Analytical Blind Spot |
| :--- | :--- | :--- | :--- | :--- |
| **Wint Wealth** | Registered OBPP Broker | NBFCs, Trustees, Exchanges | Listed Senior Secured Bonds, Securitized Debt Instruments (SDIs) from ₹1,000–₹10,000, 9–11% yield, 2% skin-in-the-game. | **Origination Conflict:** Platform acts as distributor/arranger; cannot provide unvarnished downside stress-testing or audit issuer equity balance sheets against default risks. |
| **Grip Invest** | Registered OBPP Broker | Issuers, Exchanges | Listed SDIs, Bond Baskets (sectoral diversification), 8–14% target IRR. | **Credit Risk Understatement:** Historical retail defaults in specific SDI tranches demonstrate that rating agency grades (CRISIL/ICRA) fail to capture sudden cash flow halts. |
| **GoldenPi / IndiaBonds** | OBPP Aggregators | Primary Debt Feeds | Directory of thousands of corporate bonds, search by YTM, rating, and maturity. | **Raw Directory:** Zero automated balance sheet or covenant audit; DIY retail users must read 200-page Information Memorandums themselves. |

---

### Category D: Real Assets, SM REITs & Commodities

| Platform | Primary Model | Data Sourcing | Core Features | Critical Analytical Blind Spot |
| :--- | :--- | :--- | :--- | :--- |
| **Property Share / Strata** | Fractional / SM REIT Manager | In-house syndication | Grade-A commercial asset syndication, projected 8–9% rental yields, projected 13–15% IRR. | **Syndication Bias:** Marketing materials emphasize optimistic exit valuations; opaque management fee structures and illiquid secondary trading. |
| **Jar / Gullak** | Gamified Micro-Savings | SafeGold / Augmont | UPI round-ups into digital gold (Jar); Gold leasing for +5% extra yield (Gullak Gold+). | **Hidden Costs & Counterparty Risk:** Digital gold incurs 3% GST + 2–3% buy-sell spread (investor starts 5% down); gold leasing exposes user to uncollateralized jeweler default risk. |
| **Zerodha / Groww (REITs/SGBs)** | Discount Broker | BSE/NSE Feeds | Basic trading quotes, historical distribution yield table. | **Zero Structural Analytics:** No Weighted Average Lease Expiry (WALE), no LTV ratio monitoring, no Section 115UA 4-part post-tax waterfall, no secondary SGB discount scanner. |

---

### Category E: Macro, Sovereign Yields & Wealth Aggregators

| Platform | Primary Model | Data Sourcing | Core Features | Critical Analytical Blind Spot |
| :--- | :--- | :--- | :--- | :--- |
| **CCIL / FBIL / RBI Retail Direct** | Sovereign Infrastructure | RBI / Clearing Corp | Primary G-Sec/T-Bill auctions, secondary market trade data, tabular yield curves. | **Brutal Usability:** Clunky government interfaces; no visual term premium slope analysis, no real yield vs CPI inflation curves, no SDL fiscal rankings. |
| **INDmoney / Dezerv / Kuvera** | Wealth Management / AA | Account Aggregators / CAS | Net worth tracking, asset allocation pie charts, goal tracking, automated rebalancing suggestions. | **Accounting, Not Analysis:** Aggregates asset balances, but performs zero qualitative thesis interrogation. If a user holds a ticking time-bomb stock, the app simply records its CMP. |

---

## 3. The Baseline: What Incumbents Offer Today

Across the entire Indian landscape, the existing baseline can be summarized by three industry standards:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      THE INDUSTRY BASELINE PARADIGM                    │
│                                                                        │
│   1. DATA GRANULARITY:   Purely numerical, backward-looking (CAGR, PE) │
│   2. RESEARCH METHOD:    Manual human reading or simplistic factors   │
│   3. REVENUE ALIGNMENT:  Brokering / Distribution commissions          │
│   4. ASSET SEGREGATION:  Siloed apps (Stocks vs Funds vs Bonds)       │
│   5. OUTPUT NATURE:      Unopinionated tables OR conflicted Buy tips   │
└────────────────────────────────────────────────────────────────────────┘
```

### The 4 Major Structural Deficits of the Baseline
1. **Trailing NAV Fallacy:** Mutual funds are rated on the last 36 months of NAV. A fund manager whose high-conviction bet is currently deteriorating will still boast a 5-star rating until the loss materializes.
2. **Missing Qualitative Dimensions:** No platform tracks whether an underlying company's moat is eroding, whether promoters are quietly pledging shares to shadow lenders, or whether growth is organic vs capital-destroying.
3. **The Pre-Tax Illusion:** Debt, REITs, and fixed-income yields are universally marketed on a pre-tax basis, misleading retail investors in the 30% tax slab who earn negative real returns after inflation.
4. **Absence of Pre-Mortem Stress-Testing:** No existing tool asks: *"If this investment fails over the next 3 years, what specific structural flaw will cause it?"*

---

## 4. What We Are Offering Over and Above Them

Stock Research App does not attempt to be a faster data table or a discount brokerage. Our offering fundamentally departs from the baseline across **five proprietary analytical pillars**:

```
                                  ┌─────────────────────────────────────────┐
                                  │       CAPSTONE: MULTI-ASSET AUDIT       │
                                  │  • Cross-Asset Intrinsic Allocation     │
                                  │  • Unified Post-Tax Real Yield Engine   │
                                  └────────────────────▲────────────────────┘
                                                       │
                  ┌────────────────────────────────────┼────────────────────────────────────┐
                  │                                    │                                    │
┌─────────────────┴───────────────┐  ┌─────────────────┴───────────────┐  ┌─────────────────┴───────────────┐
│     TIER 1: EQUITIES THESIS     │  │   TIER 2: FUND LOOK-THROUGH     │  │   TIER 3: REAL ASSETS & DEBT    │
│ • 7-Pillar Qualitative Engine   │  │ • 7-Pillar Constituent Scoring  │  │ • Asset Coverage Ratio (ACR)    │
│ • Reverse DCF Implied Growth    │  │ • Weighted Moat Index           │  │ • Sec. 115UA 4-Part Post-Tax    │
│ • Structural Drop Diagnostics   │  │ • Accounting Risk Index (ASRI)  │  │ • SEBI 2024 REIT Compliance     │
│ • Pre-Mortem Inversion Analysis │  │ • Style Drift Tracking          │  │ • SGB Parity Discount Scanner   │
└─────────────────────────────────┘  └─────────────────────────────────┘  └─────────────────────────────────┘
```

---

### Detailed Comparison: Baseline vs. Stock Research App

### 1. Equities Analysis
- **Industry Baseline (Screener / Trendlyne):**
  - Raw 10-15 year P&L / Balance Sheet tables.
  - Generic Piotroski or DVM scores.
  - Conflicted sell-side broker targets.
- **Stock Research App (Our Moat):**
  - **7-Pillar Grounded Synthesis:** TAM Runway, Moat Durability, Promoter Governance & Pledging, Drop Diagnostics, Valuation Multiples, Solvency, and Capital Allocation.
  - **Structural Drop Diagnostics:** When a stock plummets 30%, our engine classifies whether it is an industry-wide temporary drawdown or a structural thesis break (e.g. auditor resignation, fraud, margin collapse).
  - **Reverse DCF Sensitivity:** Instead of predicting future prices, it answers: *"What annual cash flow growth rate is the market currently pricing in at CMP?"*
  - **Pre-Mortem Inversion:** Explicitly maps out the top 3 existential failure modes of the business before capital is committed.

### 2. Mutual Funds & ETFs Analysis
- **Industry Baseline (Value Research / Morningstar):**
  - Star ratings based on trailing 3Y/5Y Sharpe and Alpha.
  - Superficial overlap percentages and Large/Mid/Small cap breakdown.
- **Stock Research App (Our Moat):**
  - **Upward Qualitative Propagation (Forensic Look-Through):** We unpack 40–65 underlying stock holdings and score them using our Tier 1 qualitative engine.
  - **Weighted Economic Moat Score:** Computes what percentage of the fund is invested in Wide, Narrow, or Zero-Moat businesses.
  - **Accounting & Solvency Risk Index (ASRI):** Measures portfolio weight in companies flagged for accounting red flags or promoter pledging.
  - **Portfolio Margin of Safety:** Measures the weighted discount/premium of the fund's constituent equities against intrinsic Reverse DCF valuations.
  - **Style Drift Tracking:** Alerts when a "Quality" fund starts buying low-quality, overleveraged momentum cyclical stocks to pump short-term returns.

### 3. Corporate Debt, SDIs & Fixed Income
- **Industry Baseline (Wint Wealth / Grip Invest / IndiaBonds):**
  - Lists YTM and rating agency grade (e.g. "CRISIL AA").
  - Platform earns commissions from issuers.
- **Stock Research App (Our Moat):**
  - **Zero-Commission Independent Credit Audit:** No origination bias.
  - **Asset Coverage Ratio (ACR) Verification:** Audits whether pledged collateral is liquid or illiquid machinery/land.
  - **Equity Cross-Contagion Guard:** Cross-references the corporate debt issuer against our equities database to detect promoter distress or equity leverage deterioration before rating agencies downgrade.
  - **Recovery Seniority Audit:** Clarifies exact payout hierarchy (Senior Secured vs Unsecured vs Subordinated).

### 4. Real Assets, REITs, InvITs & SGBs
- **Industry Baseline (Groww / Zerodha / Property Share):**
  - Basic dividend yield %; marketing IRR for fractional commercial real estate.
- **Stock Research App (Our Moat):**
  - **Statutory SEBI 2024 Compliance Gates:** Enforces automated auditing of occupancy (>=90%), NDCF distribution (>=90%), and LTV leverage (<=49%).
  - **Section 115UA Post-Tax Waterfall:** Breaks distributions into 4 distinct tax buckets (Interest, Dividend, Rental Income, Capital Repayment) to calculate true in-hand yield for 10%, 20%, and 30% tax brackets.
  - **SGB Parity Discount Scanner:** Ranks all active secondary Sovereign Gold Bond tranches by annualized YTM and spot gold discounts (yielding up to 2.5% coupon + capital gains 100% tax-free under IT Act Sec. 47(viic)).

### 5. Macro, Sovereign Yields & Multi-Asset Synthesis
- **Industry Baseline (RBI Retail Direct / CCIL):**
  - Static raw auction cut-off tables.
- **Stock Research App (Our Moat):**
  - **Interactive Sovereign Yield Curve:** FBIL benchmark curve slope (10Y G-Sec minus 91D T-Bill) with real-yield inflation spreads.
  - **State Development Loan (SDL) Disparity Matrix:** Evaluates 10-year SDL spreads across states against Debt-to-GSDP ratios and fiscal deficits.
  - **Opportunity Terminal Heatmap:** Unified cross-asset ranking scoring Equities, Funds, Corporate NCDs, REITs, SGBs, and T-Bills on a standardized Risk-Adjusted Real Return scale.

### 6. Interactive Investor Copilot & Surveillance
- **Industry Baseline:**
  - Either silent (afraid of SEBI liability) or generic chatbots that hallucinate financial data.
- **Stock Research App (Our Moat):**
  - **Autonomous Forensic Intelligence Squads:** Specialized forensic modules (Equity Chief, Credit Auditor, Governance Detective) coordinated with declarative safety policies and command sandboxes.
  - **SEBI Section 2(u) Mandatory Deflection:** Intercepts retail buy/sell inquiries instantly without token cost, deflecting into rigorous Pre-Mortem inversion diagnostics.
  - **Proactive Watchers:** Continuous 5-minute BSE filing scanner and daily AMFI NAV synchronization recording events into an immutable ledger (`autonomous_event_ledger`).

---

## 5. Comprehensive Feature Comparison Matrix

| Analytical Feature | Screener | Trendlyne | Value Research | Wint Wealth | Morningstar | **Stock Research App** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Exchange-Grounded 7-Pillar Thesis** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ Full Narrative** |
| **Structural Drop Diagnostics** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ Automated** |
| **Reverse DCF Implied Growth Rate** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ Live Sensitivity** |
| **Pre-Mortem Inversion Stress-Testing** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ Built-In** |
| **Fund 7-Pillar Stock Look-Through** | ❌ | ❌ | ❌ | ❌ | Partial ($) | **✅ Comprehensive** |
| **Fund Moat & Accounting Risk Index** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ Weighted Index** |
| **Independent Debt Collateral & ACR** | ❌ | ❌ | ❌ | Partial | ❌ | **✅ Unconflicted** |
| **REIT SEBI 2024 Regulatory Gates** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ Occupancy/LTV** |
| **Sec. 115UA Post-Tax Waterfall** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ 4-Bucket Tax** |
| **Secondary SGB Discount Parity Scan** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ Live Ranking** |
| **Sovereign Curve & SDL Matrix** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ Real-Yield Spreads** |
| **Unified Cross-Asset Opportunity Radar** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ Multi-Asset** |
| **Autonomous Proactive Event Ledger** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ 5-Min BSE Watcher** |
| **Interactive Copilot with SEBI Guard** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ Multi-Asset Copilot** |

---

## 6. Strategic Action Plan: Phased Implementation Roadmap

The implementation roadmap reconciles the platform's multi-asset competitive objectives, security/licensing requirements, and behavioral research mandates.

```
┌────────────────────────────────────────────────────────────────────────┐
│                   IMPLEMENTATION ROADMAP ARCHITECTURE                  │
│                                                                        │
│  [ACTIVE]    Task 1: Angel One SmartAPI Broker Gateway Integration    │
│  [ACTIVE]    Task 2: Custom Website Vector Icon System (SVG Sprites)  │
│  [ACTIVE]    Task 3: Upload AMC Portfolio Disclosures (CSV/XLSX)       │
│  [ACTIVE]    Task 4: Mutual Fund 50-Scheme Expansion & Style Drift     │
│  [ACTIVE]    Task 5: Capstone Multi-Asset Portfolio Audit Engine       │
│  [ACTIVE]    Task 6: Research MSME Analysis Ingestion                  │
│  ────────────────────────────────────────────────────────────────────  │
│  [COMPLETED] Phase 1 (Core): 7-Pillar Look-Through & Daily Fund Auditor│
│  [COMPLETED] Phase 2: Equity-to-Debt Contagion Bridge                  │
│  [COMPLETED] Phase 3: Cross-Asset Opportunity Terminal & Tax Engine    │
│  [COMPLETED] Phase 4: Proactive Thesis Drift & Real-Time Surveillance  │
│  [COMPLETED] Phase 5: Institutional PDF Export & Approachable Polish   │
└────────────────────────────────────────────────────────────────────────┘
```

---

### 6.1 Active Pending Tasks (Actually Pending)

The following items constitute the truly active, operational tasks remaining:

1. **Curated Mutual Fund Look-Through Expansion (Remaining 19 Schemes to Reach Top 50 Target):**
   - **Target Files:** `core/db/mutual_funds.py`, `core/analysis/fund_forensic_auditor.py`
   - **Status:** In Progress (31 marquee schemes currently active; 19 remaining to reach top 50 AMFI target)
   - **Details:** Expand curated portfolio holdings from 31 to 50 marquee schemes across Flexi Cap, Large & Mid Cap, Mid Cap, and Small Cap categories. Record historical quarterly look-through scores in `mutual_fund_schemes` to detect fund manager style drift over time.

2. **Operational Gateway Liveness & Token Lifecycle Monitoring:**
   - **Target Files:** `core/ingestion/angel_one.py`, `scripts/verify_angel_proxy_ip.py`
   - **Status:** Operational / Active Monitoring
   - **Details:** Maintain continuous uptime of the AWS Lightsail proxy daemon (`13.54.76.134:8888`) and verify automated RFC 6238 TOTP session token renewals during live Indian market trading hours (09:15 to 15:30 IST).

---

### 6.2 Completed & Non-Relevant Implementation Tasks (Archived & Struck Through)

All roadmap tasks that have been implemented, tested, and verified, as well as tasks that are non-relevant or do not need to be implemented right now, are struck through below:

#### A. Recently Implemented Production Features (Struck Through)
- ~~**Exchange Gateway & Level-2 Order Depth Integration:** Built `core/ingestion/angel_one.py` with AWS static IP forward proxy egress (`13.54.76.134:8888`), pure Python RFC 6238 TOTP generator, Level-2 5-tier order book depth, and historical candle parser. Integrated into `core/analysis/fundamentals.py` and `scripts/update_all_reports.py`. Refreshed all 143 company dossiers with live quotes and order depth and synchronized to Supabase Cloud PostgreSQL.~~
- ~~**Category 1 Institutional Equity Cockpit:** Implemented `core/analysis/sector_scoring.py` (BFSI, IT, Capital Goods, Pharma, FMCG), `core/analysis/valuation_radar.py` (2-stage DCF, Graham EPV, Historical PE, Margin of Safety), `core/analysis/institutional_flow.py` (Order Imbalance, Spread bps, Circuit Buffer), `core/analysis/forensic_sieve.py`, and `core/analysis/bull_bear.py` (60-second structural thesis). Wired `GET /api/dossier/intel/{ticker}` into executive cockpit UI (`web/templates/dossier.html`).~~
- ~~**5 Institutional Analytical Engines (Cortex Suite):** Implemented 10-Point Deterministic Forensic Screening Sieve (`core/cortex/chanakya.py`), Multi-Year Financial & DuPont Ledger (`core/cortex/varan.py`), Cross-Asset Capital Structure Matrix (`core/cortex/setu.py`), Event-Driven Corporate Announcement Classifier (`core/cortex/garuda.py`), and Multi-Asset Portfolio Look-Through Engine (`core/cortex/sutra.py`). Exposed via `/api/cortex/*` and hardened against 80 adversarial stress tests.~~
- ~~**Multi-Asset Portfolio Look-Through Calculation Engine:** Implemented `SutraLookThroughEngine` in `core/cortex/sutra.py` and route `/api/cortex/portfolio-look-through` for consolidated multi-asset portfolio de-risking and single-stock concentration detection.~~
- ~~**Admin 2FA Gate & Security Authentication:** Implemented zero-dependency RFC 6238 TOTP 2FA gate (`core/auth/totp.py`, `/admin/setup-2fa`, `/admin/verify-2fa`) and Email OTP authentication (`core/auth/otp.py`).~~
- ~~**Full Database Batch Refresh & Supabase Cloud Synchronization:** Ingested and refreshed all 143 company reports in `reports.db` with live exchange quotes and Level-2 depth via `scripts/update_all_reports.py`. Synchronized all 143 records to Supabase Cloud PostgreSQL.~~
- ~~**Master Engineering Documentation & Evaluation Frameworks:** Authored comprehensive Master Engineering Manual (`docs/MASTER_ENGINEERING_MANUAL.md`) and Multi-Asset Report Evaluation Frameworks (`docs/REPORT_EVALUATION_FRAMEWORKS.md` & `.antigravity/docs/EVALUATION_FRAMEWORKS.md`).~~
- ~~**Descriptive Title Harmonization & Brand Sanitization:** Removed all user-facing mentions of broker brands in favor of 'Official Exchange Live Feed' / 'Exchange Level-2 Depth'. Replaced proprietary engine codenames with simple, intuitive descriptive titles across UI templates, summaries, and API routes.~~

#### B. Non-Relevant / Deferred Tasks (Do Not Need Implementation Right Now - Struck Through)
- ~~**[NOT NEEDED RIGHT NOW / DEFERRED] Custom Website Vector Icon System (SVG Sprites):** Purely cosmetic asset task. Existing modern glassmorphism tokens, curated status badges, and typography provide a polished UI without custom SVG icon replacement.~~
- ~~**[NOT NEEDED RIGHT NOW / DEFERRED] Research MSME Analysis Ingestion:** Pre-development research for unlisted MSME supplier risk via SIDBI/MCA21. Zero relevance to active listed equity/fixed-income/MF research platform.~~
- ~~**[NOT NEEDED RIGHT NOW / DEFERRED] Upload Monthly Portfolio Disclosures (CSVs/Excel) for Top 150 Funds:** AMFI statutory daily NAV ingestion (`NAVAll.txt`) and 31 marquee curated funds are already operational. Manual parsing of 150 proprietary AMC monthly workbooks is deferred as out of scope.~~
- ~~**[NOT NEEDED RIGHT NOW / DEFERRED] Full CAS PDF Parser with Password Unlocking:** Encrypted third-party PDF parsing across CAMS/KFintech is deferred enterprise tooling. Core look-through calculation engine is already operational.~~

#### C. Historical Completed Tasks (Archived)

- ~~**Phase 1 (Completed Core Components): 7-Pillar Fund Forensic Look-Through Engine & Autonomous Daily Auditor:** Built `core/analysis/fund_forensic_auditor.py` computing Weighted Economic Moat Index, Accounting & Solvency Risk Index (ASRI), Margin of Safety vs DCF, and Promoter Pledging weight. Built `scripts/run_daily_fund_audit.py` and scheduled nightly background daemon `run_daily_fund_audit_scheduler()` at 23:30 IST in `web/main.py`. Surfaced interactive fund dossier pages at `/funds/{scheme_code}` with hero daily feature banner on `/funds`.~~
- ~~**Phase 2: Equity-to-Debt Contagion Bridge (Cross-Asset Risk Detection):** Built automated bidirectional parent-subsidiary mapping (`get_debt_securities_for_equity`) linking listed equities (`RELIANCE`, `TATAMOTORS`, `LT`, `BAJFINANCE`, `PEL`, `HDFCBANK`, etc.) directly to their listed NCDs. Evaluates parent governance posture, promoter pledge ratio, and Piotroski F-score to compute the `Credit Contagion Radar` (`ACTIVE_CONTAGION_ALERT`, `MONITORED_EQUITY_DRIFT`, `INSULATED_EQUITY_MOAT`). Live "Credit Contagion Radar" badge on debt dossiers and "Capital Structure & Listed NCDs" card on equity dossiers.~~
- ~~**Phase 3: Opportunity Terminal Enhancement (Unified Real Returns):** Connected 7 asset sleeves (Fundamental Equities, Mutual Funds, Corporate NCDs/SDIs, SM REITs/InvITs, Sovereign Gold Bonds, Sovereign G-Secs/T-Bills, National ETFs). Implemented statutory tax waterfalls calculating post-tax real yields net of MOSPI CPI inflation across tax brackets (0%, 10% New Tax Regime, 20%, 30%, 39% HNI Surcharge) under Sec 47(viic), Sec 115UA, Sec 112A, Sec 50AA. Built 4 discovery views (Bento Cards, 2D Heatmap Matrix, Risk-Return Scatter Frontier, Dense Table) and persistent 4-item Arbitrage Docket.~~
- ~~**Phase 4: Proactive Thesis Drift & Autonomous Event Syndication:** Continuous 5-minute BSE watcher (`core/agents/watchers/bse_watcher.py`) scanning watchlist scrips for official regulatory disclosures (auditor resignations, promoter pledge changes, disputes, M&A). Dispatches background thesis re-checks (`auto_reaudit_dispatched`) and logs updated risk posture summaries (`thesis_impact_summarized`) into `autonomous_event_ledger`. Live navbar Agent Radar modal feed and public API `/api/autonomous/events`.~~
- ~~**Phase 5: Institutional Export & SEBI Compliance Safe-Harbor Polish:** One-click institutional PDF generation across all 4 asset classes (`/api/pdf/{ticker}`, `/api/pdf/fund/{scheme_code}`, `/api/pdf/debt/{isin}`, `/api/pdf/reit/{symbol}`). Approachable, plain-English clarity with zero condescension while strictly embedding SEBI RA Section 2(u) non-advisory educational disclaimers across all dossiers, primers, and exports.~~
- ~~**Gate 1–3 Architectural Deliverables:** Prioritization of Cross-Asset Opportunity Terminal, automated 23:30 IST daily fund auditor daemon, and multi-asset Copilot expansion across Equities, Mutual Funds, and Corporate Debt/SDIs.~~
- ~~**Zero-Hallucination & Anti-Fabrication Test Suite:** Built `tests/test_zero_hallucination_and_grounding.py` (8 automated tests) verifying elimination of all corporate entity claims, fake SAC codes (998314), office addresses, fake support emails (`support@stockresearch.app`), and personal name placeholders. Mandated strictly on-site `/contact` grievance review by admin console.~~
- ~~**Admin Panel Direct Remedial Credit Granting:** Built atomic DB function `admin_grant_user_credits` in `core/db/admin.py`, `POST /admin/users/grant-credits` in `web/main.py`, `#adminGrantCreditsModal` in `web/templates/admin.html`, zero-revenue ledger isolation (`amount_inr = 0.0`, `nature = FREE_GRANT`), support ticket auto-resolution, and automated test suite in `tests/test_admin_credit_grant.py`.~~
- ~~**Gate 4: Formal Rejection of Sitewide Autonomous Agents:** Preserved deterministic Python pipelines + single-pass structured Gemini synthesis. Shelved and archived sitewide autonomous agent execution loops to guarantee SEBI audit immunity, avoid the 10x–20x compounding context tax, and preserve sub-3s response latency.~~

---

## 7. Review and Decision Gates: Architectural Decisions & Status

The user evaluated and authorized the following architectural resolutions:

1. **Gate 1: Asset Priority Alignment**  
   - **Resolution:** **Phase 3 (Cross-Asset Opportunity Terminal)** prioritized to give users an instant comparative view across Equities, Debt, REITs, SGBs, T-Bills, and Funds.  
   - **Implementation Status:** **Completed & Verified.** Connects all asset classes, applies statutory tax waterfalls (Sec 47(viic), Sec 115UA, Sec 112A, Sec 50AA) including the 10% New Tax Regime bracket, supports scenario filters ("Capital Preservation (Real Return > 0%)", "Maximum Cash Flow", "Asymmetric Upside"), and embeds side-by-side Arbitrage Docket pinning.

2. **Gate 2: Autonomous Re-Audit Frequency**  
   - **Resolution:** **Auto** — Daily fund re-audits run automatically at 23:30 IST following AMFI NAV publication.  
   - **Implementation Status:** **Active.** The background daemon `run_daily_fund_audit_scheduler()` runs nightly at 23:30 IST in `web/main.py`, executing `audit_single_fund_daily` and logging rotation events to `autonomous_event_ledger`. Admin console on-demand re-audit remains accessible as a manual trigger backup.

3. **Gate 3: Copilot Visibility**  
   - **Resolution:** **Yes** — Expand the Institutional Forensic Copilot to Mutual Funds and Debt dossiers in addition to existing Equity dossiers.  
   - **Implementation Status:** **Completed & Verified.** Multi-asset grounding active across all 3 asset classes in `core/agents/copilot/investor_copilot.py`. Frontend `copilot_modal.html` and `copilot.js` now dynamically configure headers, badges, intro messages, and diagnostic prompt chips tailored to Equities, Mutual Funds, and Corporate Debt/SDIs with strict SEBI RA Sec. 2(u) non-advisory guardrails.

4. **Gate 4: Site Architecture & Autonomous Agent Policy (October 8, 2026)**  
   - **Resolution:** **Strict Deterministic Architecture (Sitewide Autonomous Agents Prohibited)** — Confirmed decision to NOT implement autonomous agent loops across public site surfaces.  
   - **Rationale:**  
     1. **SEBI Audit & Non-Advisory Protection:** Autonomous agent loops produce open-ended, non-deterministic reasoning that risks drifting into advisory language, exposing the platform under SEBI (Research Analysts) Regulations, 2014. Deterministic code guarantees auditable exchange grounding.  
     2. **Token Economics:** Avoids the 10x–20x compounding context tax of ReAct loops (25k–60k tokens vs. 2.5k deterministic tokens per report).  
     3. **Latency & Reliability:** Preserves sub-3s response times and 99.9% uptime over fragile multi-step tool iterations.  
   - **Implementation Status:** **Enforced.** The site retains deterministic Python data ingestion + single-pass structured Gemini synthesis + constrained Copilot RAG.

---
*Status: Architecture aligned, hardened, and deployed with 179/179 passing tests.*
