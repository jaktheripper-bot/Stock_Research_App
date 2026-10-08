# Institutional Data Provenance Audit & Comprehensive Indian Savings/Investment Universe Blueprint

**Document ID:** `AUD-PROVENANCE-SAVINGS-2026-Q4`  
**Compliance Standard:** SEBI (Research Analysts) Regulations 2014 Sec. 2(u) / Zero-Hallucination Directive  
**Review Status:** Verified & Synchronized with Repository Architecture

---

## Executive Summary

This document presents a rigorous institutional audit across two core dimensions requested by leadership:
1. **The 6-Asset Class Data Provenance & Pipeline Integrity Matrix:** An unvarnished analysis of what is **Live & Statutory**, what is **Secondary Gateway**, and what is **Mocked/Synthetic** across Equities, Mutual Funds, Corporate Debt, Sovereign Curve, REITs/InvITs, and Macroeconomic Indicators.
2. **The Comprehensive Indian Savings & Investment Universe Gap Analysis:** A granular taxonomy of all retail, HNI, and corporate savings/investment objects currently missing from our analytics platform—specifically short-term debt, liquid cash proxies, statutory sovereign schemes, and tax-advantaged fixed income.

---

## Part 1: 6-Asset Class Data Provenance Matrix (Live vs. Hollow)

| Asset Class | Primary Data Gateway | Secondary Fallback | Current Status | Pipeline Integrity & SEBI Compliance Assessment |
| :--- | :--- | :--- | :--- | :--- |
| **1. Equities (Nifty 100 / NSE / BSE)** | **BSE Direct Exchange API** (`bse_master.py`, Scrip 500xxx) | Yahoo Finance / Google Finance | 🟢 **LIVE & RESILIENT** | Live quotes, tick data, corporate filings & announcements pulled from BSE. 7-pillar synthesis powered by Gemini 2.5 Flash + dynamic citations. 14-day TTL caching with auto-invalidation on material corporate actions. |
| **2. Mutual Funds** | **AMFI Daily NAV API** (`NAVAll.txt` statutory feed) | AMC Monthly Portfolio Disclosures (SEBI mandated) | 🟡 **HYBRID (SCOPED PAUSE)** | Static master metadata seeded with top funds (PPFAS, HDFC, Mirae, Parag Parikh, Nippon, Quant). Look-Through Forensic Score has been **strictly paused** with statutory Sec. 2(u) disclaimer until underlying constituent equity coverage reaches **≥ 70.0%**. Fee Drag, Overlap Matrix, and AUM liquidity remain **100% live**. |
| **3. Corporate Debt / Bonds** | BSE / NSE Debt Reporting Platform | Private OBPP Scraping (Wint, GoldenPi, Grip) | 🔴 **ELEVATED REVISION NEEDED** | Scrapers currently in `core/analysis/debt_crawler.py` face Cloudflare/Akamai blocks and present IP liability. Yields, credit ratings, and spread calculations are deterministic but require migrating to official BSE debt feeds or licensed Tier-1 EODHD feeds. |
| **4. Sovereign Yield Curve** | **CCIL (Clearing Corp of India)** & RBI Market Data | Hardcoded 1Y–30Y Benchmark Points | 🟡 **FUNCTIONAL BUT STATIC-SEEDED** | Nelson-Siegel curve interpolation and duration risk models are mathematically complete and render interactive SVG curves (`/sovereign`). However, benchmark points (91D to 30Y) currently rely on scheduled daily seeds rather than sub-second WebSocket ticks. |
| **5. REITs & InvITs (incl. SM-REITs)** | BSE Listed Equities & Exchange Disclosures | AMC Annual / Quarterly NDCF Filings | 🟢 **LIVE & DETERMINISTIC** | Complete coverage of Embassy, Mindspace, Brookfield, Nexus, PowerGrid InvIT, and newly seeded SM-REITs (Mini-REITs under SEBI SM-REIT Regs 2024). Full NDCF tax-breakdown calculator (Interest vs. Dividend vs. Return of Capital vs. Rental). |
| **6. Macroeconomic Indicators** | **RBI DBIE** (Database on Indian Economy) & **MOSPI Gazette** | IMF / TradingEconomics public aggregates | 🟢 **STATUTORY SEEDED** | CPI Inflation (3.65%), GDP Growth (6.7%), Repo Rate (6.50%), 10Y Yield (6.78%), Forex Reserves ($704B), and 10Y US-India Spread (278 bps) are deterministic and power sitewide macro radars and Copilot context. |

---

## Part 2: Comprehensive Gap Analysis of Untracked Indian Investment & Savings Objects

To become the definitive multi-asset wealth and risk intelligence platform in India, we must expand beyond pure equities and long-term funds to track the complete spectrum of **capital preservation, liquidity management, and fixed-income assets**.

```
                           INDIAN SAVINGS & INVESTMENT UNIVERSE
                                             │
      ┌──────────────────┬───────────────────┼───────────────────┬──────────────────┐
      ▼                  ▼                   ▼                   ▼                  ▼
1. Ultra-Short/     2. Bank & NBFC      3. Sovereign        4. Statutory        5. Retirement
   Liquid Proxies      Term Deposits       Direct Debt         Govt Schemes        & Pension
  - Overnight Funds   - Bank FDs          - T-Bills (91/182/  - PPF (7.1% EEE)    - NPS Tier I & II
  - Liquid Funds      - SFB High-Yield      364 Days)         - Sukanya Samriddhi - EPF / VPF (8.25%)
  - Arbitrage Funds     FDs (up to 9.0%)  - RBI Floating Rate - SCSS (8.2%)       - Annuities
  - High-Yield Savings - Corporate FDs      Savings Bonds     - Mahila Samman
  - TREPS / T-Bills     (Bajaj, Shriram)  - Bharat Bond ETFs  - Post Office MIS
```

### Detailed Breakdown of Missed Instruments

#### Category A: Ultra-Short Cash & Liquid Investment Proxies
1. **Liquid Funds & Overnight Funds:**
   - *Maturity:* 1 day (Overnight) to 91 days (Liquid).
   - *Yield Profile:* ~6.40% – 6.85% annualized.
   - *Risk:* Negligible duration risk; zero mark-to-market risk in overnight funds (collateralized via TREPS).
   - *Target Audience:* Corporate treasury, emergency funds, parking cash between equity allocations.
2. **Arbitrage Funds (The Supreme Post-Tax Liquid Hedge):**
   - *Mechanism:* Fully hedged cash-futures arbitrage (0% net equity exposure).
   - *Yield Profile:* ~6.75% – 7.25% annualized.
   - *Tax Superpower:* Taxed as **Equity Mutual Funds** (12.5% LTCG after 12 months, 20% STCG) rather than investor's personal income tax slab (which can be up to 39% for HNIs in debt funds).
   - *Platform Value:* Critical addition for our Tax Optimization & Allocation engine.
3. **High-Yield Savings Accounts:**
   - *Yield Profile:* 6.00% – 7.25% (IDFC First Bank, AU Small Finance, Equitas, Suryoday).
   - *Feature:* Instant liquidity, daily interest compounding, DICGC insurance up to ₹5,00,000 per depositor.

#### Category B: Term Deposits & Fixed Yield Vehicles
4. **Small Finance Bank Fixed Deposits (SFB FDs):**
   - *Yield Profile:* 8.25% – 9.10% (Suryoday, Unity, Equitas, Ujjivan).
   - *Safety Mechanism:* 100% insured up to ₹5,00,000 principal + interest under RBI's DICGC guarantee.
   - *Audit Utility:* Laddering calculator showing split deposits under ₹5 lakh threshold across multiple SFBs for maximum yield with zero credit risk.
5. **High-Rated Corporate Fixed Deposits (NBFC FDs):**
   - *Yield Profile:* 7.75% – 8.60% (Bajaj Finance AAA, Mahindra Finance AAA, Shriram Finance AA+).
   - *Risk Factors:* Unsecured debt (not covered by DICGC); requires credit rating watch and Altman Z-Score forensic tracking.

#### Category C: Sovereign Direct & Guaranteed Debt
6. **Treasury Bills (T-Bills via RBI Retail Direct):**
   - *Maturity:* 91-Day, 182-Day, and 364-Day zero-coupon sovereign notes.
   - *Yield Profile:* ~6.65% – 6.90%.
   - *Safety:* Absolute sovereign backing of the Government of India. No default risk.
7. **RBI Floating Rate Savings Bonds (FRSB 2020):**
   - *Coupon:* Pegged at **National Savings Certificate (NSC) Rate + 35 bps** (currently yielding **8.05%** semi-annual payout).
   - *Tenure:* 7 years (early redemption for senior citizens).
   - *Safety:* Direct sovereign obligation; 100% risk-free fixed income for retirees.
8. **Target Maturity Debt Index Funds & Bharat Bond ETFs:**
   - *Mechanism:* Roll-down maturity investing strictly in AAA PSU bonds and Central G-Secs with predetermined maturity dates (e.g., Bharat Bond 2030, 2032).
   - *Platform Advantage:* Locks in yield to maturity (YTM) without active fund manager duration risk.

#### Category D: Government Statutory Small Savings Schemes
9. **Public Provident Fund (PPF):**
   - *Yield:* 7.10% compounded annually.
   - *Status:* Exempt-Exempt-Exempt (EEE tax status). 15-year tenure with partial withdrawal from Year 7.
10. **Sukanya Samriddhi Yojana (SSY):**
    - *Yield:* 8.20% tax-free EEE for girl child. Unbeatable risk-adjusted return.
11. **Senior Citizens Savings Scheme (SCSS):**
    - *Yield:* 8.20% quarterly payout, 5-year tenure, max limit ₹30,00,000 per individual.
12. **Post Office Monthly Income Scheme (POMIS):**
    - *Yield:* 7.40% monthly payout for predictable income streams.

#### Category E: Structured Retirement & Pension Vehicles
13. **National Pension System (NPS Tier I & Tier II):**
    - *Tax Benefit:* Exclusive additional ₹50,000 deduction under Section 80CCD(1B) beyond the standard 80C limit.
    - *Structure:* Low-cost asset choice (Active / Auto choice across Equity E, Corporate Debt C, and Government Debt G).

---

## Part 3: Architecture for Nifty 100 Reports & Supabase Persistence

### 1. Dual-Persistence Mechanism
When reports are generated via `generate_stock_report(symbol)`:
- **Local Primary Persistence:** Written to `reports.db` in WAL mode via `save_report_to_archive()`.
- **Supabase Cloud Persistence:**
  - If `SUPABASE_DB_URL` is set: `get_db_connection()` routes all writes directly to Supabase PostgreSQL with automated schema migrations.
  - If `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are present: `scripts/sync_to_supabase.py` pushes reports via Supabase PostgREST (`/rest/v1/reports`).
  - Storage Backups: Database snapshots are compressed and uploaded to Supabase Storage bucket `backups`.

### 2. Execution Command
```bash
# Check status of Nifty 100 universe coverage:
./run.sh nifty100 --status

# Run generation for Nifty 100 stocks:
./run.sh nifty100

# Sync all generated reports to Supabase:
./run.sh sync-supabase
```
