# Multi-Asset & Mutual Fund Evaluation Framework Specification
**Document Version:** 1.0.0  
**Effective Date:** 2026-10-05  
**Compliance Standard:** SEBI (Mutual Funds) Regulations, 1996 | SEBI (Issue and Listing of Non-Convertible Securities) Regulations, 2021 | SEBI (SM REITs Amendment) Regulations, 2024 | RBI NBFC-P2P Master Directions 2024  

---

## 1. Executive Mandate & Architectural Inversion

In equity analysis, the investor evaluates business compounding, competitive moats, and residual cash flows:
$$\text{Equity Total Return} = \text{Dividend Yield} + \text{Earnings Growth} \pm \Delta(\text{Valuation Multiple})$$

In fixed income and non-equity assets, the mathematical relationship is **strictly inverted**. The maximum upside is contractually capped at the stated coupon/yield, while the downside is **100% loss of principal**:
$$\text{Fixed-Income Net Real Return} = \text{Yield-to-Maturity (YTM)} - \text{Credit Loss Probability} - \text{Duration Drag} - \text{Tax Friction}$$

Applying equity metrics (P/E ratios, earnings momentum, price charts) to debt instruments or mutual fund portfolios creates severe analytical failure. Furthermore, conventional wealth-tech applications (e.g., Groww, Zerodha Coin) rely on past 1Y/3Y/5Y CAGR returns—inducing the classic behavioral bias of **performance chasing**, where retail investors enter funds and high-yield instruments at the cyclical peak of credit risk or interest rate cycles.

This document formalizes the **Institutional Evaluation Frameworks** across all non-equity asset classes, establishing unambiguous mathematical definitions, data sources, thresholds, and zero-hallucination guardrails.

---

## 2. Framework 1: The 5-Pillar Credit & Solvency Matrix
*Target Universe: Listed Corporate Bonds, Non-Convertible Debentures (NCDs), and Securitized Debt Instruments (SDIs) under the SEBI ₹10,000 face value framework, as well as the debt sleeves of mutual funds.*

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        5-PILLAR CREDIT & SOLVENCY MATRIX                               │
└────────────────────────────────────────────────────────────────────────────────────────┘
          │                                                               │
  [PILLAR 1: QUALITY]                                             [PILLAR 2: SENIORITY]
  Credit Agency Rating & Drift                                    Capital Hierarchy & Asset Cover
          │                                                               │
  [PILLAR 3: SOLVENCY]                                            [PILLAR 4: DURATION]
  Cash Coverage (ICR, DSCR, Net Debt/EBITDA)                      Macaulay, Mod Duration & Curve
          │                                                               │
  └───────────────────────────────► [PILLAR 5: RECOVERY] ◄────────────────┘
                                  Liquidity, RFQ Volumes & Pool Health
```

### Pillar 1: Credit Quality & Rating Drift
* **Regulatory Agency Mapping**: Standardized 8-tier internal scale mapped across CRISIL, ICRA, CARE, India Ratings, and Acuité:
  $$\text{AAA} \succ \text{AA+} \succ \text{AA} \succ \text{AA-} \succ \text{A+} \succ \text{A} \succ \text{BBB} \succ \text{Below Investment Grade / D}$$
* **Rating Trajectory Score**: Evaluates credit momentum over a rolling 24-month horizon:
  * *Positive Outlook / Upgrade*: Score $+1$
  * *Stable*: Score $0$
  * *Negative Outlook / Credit Watch with Negative Implications*: Score $-2$
  * *Multi-Notch Downgrade*: Automatic High-Risk Flag.
* **Credit Spread over Risk-Free Sovereign ($\text{CS}$)**:
  $$\text{CS} = \text{YTM}_{\text{Instrument}} - Y_{\text{G-Sec}(T)}$$
  Where $Y_{\text{G-Sec}(T)}$ is the sovereign yield interpolated to matching maturity $T$. A spread $< 100\text{ bps}$ on non-AAA paper indicates uncompensated credit risk; a spread $> 500\text{ bps}$ triggers mandatory insolvency stress checks.

### Pillar 2: Capital Hierarchy & Seniority Cover
* **Seniority Classification & Waterfall**:
  1. *Senior Secured*: Pledged specific tangible assets with registered charge with MCA/Depository.
  2. *Senior Unsecured*: General corporate claim ahead of equity and subordinated debt.
  3. *Subordinated Tier-II Debt*: Regulatory capital absorbing losses ahead of depositors/senior debt.
  4. *Additional Tier-1 (AT1) Perpetual Bonds*: Loss-absorption write-down risk (flagged with **Maximum Risk Alert** to prevent repeats of the Yes Bank AT1 write-off crisis).
* **Asset Cover Ratio ($\text{ACR}$)**:
  $$\text{ACR} = \frac{\text{Market Value of Pledged Tangible Assets}}{\text{Total Secured Debt Outstanding}}$$
  * *Pillar Benchmark*: $\text{ACR} \ge 1.25\times$ for manufacturing/infra; $\ge 1.10\times$ for NBFC loan collateral. $\text{ACR} < 1.00\times$ triggers a **Breach of Covenants Alert**.

### Pillar 3: Cash Flow Solvency & Coverage
* **Interest Coverage Ratio ($\text{ICR}$)**:
  $$\text{ICR} = \frac{\text{EBIT}}{\text{Total Interest Expense}}$$
  * *Robust*: $\text{ICR} > 3.0\times$ | *Acceptable*: $1.8\times \le \text{ICR} \le 3.0\times$ | *Distressed*: $\text{ICR} < 1.5\times$
* **Debt Service Coverage Ratio ($\text{DSCR}$)**:
  $$\text{DSCR} = \frac{\text{Free Cash Flow to Firm (FCFF)} + \text{Cash Reserves}}{\text{Interest Due} + \text{Principal Maturing in 12M}}$$
  * *Mandatory Safe Threshold*: $\text{DSCR} \ge 1.20\times$.
* **Leverage Multiplier ($\text{Net Debt} / \text{EBITDA}$)**:
  $$\text{Leverage} = \frac{\text{Total Debt} - \text{Cash \& Liquid Equivalents}}{\text{TTM EBITDA}}$$
  * High-Risk threshold: $> 4.0\times$ (excluding regulated financial institutions).

### Pillar 4: Duration & Interest Rate Sensitivity
* **Macaulay Duration ($D_{\text{mac}}$)**:
  $$D_{\text{mac}} = \frac{\sum_{t=1}^n \frac{t \cdot CF_t}{(1 + y)^t}}{\sum_{t=1}^n \frac{CF_t}{(1 + y)^t}}$$
* **Modified Duration ($D_{\text{mod}}$)**:
  $$D_{\text{mod}} = \frac{D_{\text{mac}}}{1 + \frac{y}{k}}$$
* **Estimated Capital Loss from Rate Shock**:
  $$\frac{\Delta P}{P} \approx -D_{\text{mod}} \cdot \Delta y + \frac{1}{2} C (\Delta y)^2$$
  Where $C$ is bond convexity. Enables real-time modeling of how a $50\text{ bps}$ RBI repo rate shift impacts bond principal.

### Pillar 5: Recovery Reality & Securitization Pool Quality
* **For Corporate Bonds**: Secondary market RFQ trading frequency on BSE/NSE, bid-ask spread, and historical recovery rate under the Insolvency and Bankruptcy Code (IBC) for that issuer's sector.
* **For Securitized Debt Instruments (SDIs)**:
  * **First Loss Default Guarantee (FLDG) / Cash Collateral**: $\%$ of pool value funded as subordinate cash buffer by the originating NBFC.
  * **Pool Diversification (HHI Index)**: Herfindahl-Hirschman Index across underlying borrowers.
  * **Collection Efficiency Ratio ($\text{CER}$)**: Minimum rolling 6-month collection rate $> 95\%$.

---

## 3. Framework 2: The 6-Pillar Look-Through & Fiduciary Matrix
*Target Universe: Equity Mutual Funds, Debt Mutual Funds, Balanced Advantage/Hybrid Funds, and Solution-Oriented Schemes.*

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        6-PILLAR MUTUAL FUND LOOK-THROUGH MATRIX                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
          │                                                               │
  [PILLAR 1: ASSET DECOMPOSITION]                                 [PILLAR 2: TRUE OVERLAP]
  Equity 7-Pillar + Debt 5-Pillar                                 Active Share & Cross-Scheme Dupes
          │                                                               │
  [PILLAR 3: RISK-ADJUSTED ALPHA]                                 [PILLAR 4: DOWNSIDE RESILIENCE]
  Sharpe, Sortino, Hurst Exponent                                 Downside Capture & Max Drawdown
          │                                                               │
  └───────────────────────────────► [PILLAR 5: COST & CHURN] ◄────────────┘
                                  Direct vs. Regular TER & Turnover Ratio
                                                  │
                                  [PILLAR 6: FIDUCIARY DRIFT]
                                  AUM Capacity Trap & Mandate Creep
```

### Pillar 1: Underlying Asset Look-Through
Instead of analyzing the fund as an opaque black box, the portfolio is decomposed into its exact constituent securities using monthly SEBI portfolio filings:
$$\text{Fund Health Score} = W_E \sum_{i=1}^{N_E} w_i \cdot S_{\text{Equity}, i} + W_D \sum_{j=1}^{N_D} w_j \cdot S_{\text{Debt}, j} + W_C \cdot S_{\text{Cash}}$$
* $W_E, W_D, W_C$: Weights of Equity, Debt, and Cash/Derivatives.
* $S_{\text{Equity}, i}$: The stock's score derived from our verified **7-Pillar Stock Engine**.
* $S_{\text{Debt}, j}$: The bond's score derived from our **5-Pillar Credit Engine**.
* *Unrated / High-Risk Debt Penalty*: Any unrated or below-investment-grade paper held is penalized with a zero score.

### Pillar 2: True Diversification & Overlap Diagnostic
* **Active Share ($\text{AS}$)**:
  $$\text{AS} = \frac{1}{2} \sum_{i=1}^N |w_{\text{Fund}, i} - w_{\text{Benchmark}, i}|$$
  * *Genuine Active Fund*: $\text{AS} \ge 60\%$
  * *Closet Index Fund*: $\text{AS} < 40\%$ (Flagged: Investors paying active management fees for an index fund).
* **Cross-Scheme Portfolio Overlap Metric**:
  $$\text{Overlap}(A, B) = \sum_{k} \min(w_{A, k}, w_{B, k})$$
  Evaluates portfolio duplication across a user's multi-fund basket to eliminate illusory diversification.
* **Top 10 Concentration Risk**: Combined weight of the top 10 holdings. $> 60\%$ in a multi-cap fund triggers a concentration warning.

### Pillar 3: Risk-Adjusted Alpha & Consistency
* **Sortino Ratio ($\text{Downside Risk Only}$)**:
  $$\text{Sortino} = \frac{R_p - R_f}{\sigma_{\text{down}}}, \quad \text{where } \sigma_{\text{down}} = \sqrt{\frac{1}{T}\sum_{t=1}^T \min(0, R_t - \tau)^2}$$
  *Evaluates outperformance without penalizing upside volatility.*
* **Rolling Return Outperformance Consistency**:
  $$\text{Consistency Score} = \frac{\text{Count of Rolling 3-Year Windows Outperforming Category Benchmark}}{\text{Total Rolling Windows Evaluated}} \times 100\%$$
  *Target*: $\ge 70\%$ rolling consistency across a 5-year evaluation history.
* **Hurst Exponent ($H$)**:
  * $H > 0.5$: Persistent compounding momentum (trend-following efficiency).
  * $H = 0.5$: Random walk (luck-driven).
  * $H < 0.5$: Mean-reverting churn (poor stock selection).

### Pillar 4: Downside Capture & Crash Resilience
* **Downside Capture Ratio ($\text{DCR}$)**:
  $$\text{DCR} = \frac{R_{\text{Fund, Down Periods}}}{R_{\text{Benchmark, Down Periods}}} \times 100\%$$
  * *Institutional Benchmark*: $\text{DCR} \le 75\%$ (Fund falls no more than 75% of the market drop during corrections).
* **Upside Capture Ratio ($\text{UCR}$)**:
  $$\text{UCR} = \frac{R_{\text{Fund, Up Periods}}}{R_{\text{Benchmark, Up Periods}}} \times 100\%$$
  *Target*: $\text{UCR} \ge 100\%$. The capture spread $\text{UCR} - \text{DCR}$ must be strictly positive.
* **Historical Maximum Drawdown ($\text{MDD}$)**: Depth and recovery duration during market crises (March 2020 COVID crash, 2022 rate hike cycles).

### Pillar 5: Expense Drag & Intermediary Friction
* **Direct vs. Regular Plan Compounded Wealth Loss**:
  $$\text{Loss}_{\text{Friction}}(t) = A_0 \left[ (1 + r - \text{TER}_{\text{Regular}})^t - (1 + r - \text{TER}_{\text{Direct}})^t \right]$$
  Computes the exact rupee amount lost over 10- and 20-year horizons to broker/distributor commissions.
* **Portfolio Turnover Ratio ($\text{PTR}$)**:
  $$\text{PTR} = \frac{\min(\text{Total Purchases}, \text{Total Sales})}{\text{Average Monthly AUM}}$$
  $\text{PTR} > 100\%$ indicates speculative churning, resulting in hidden brokerage/STT costs inside the NAV.

### Pillar 6: Scale & Style Drift Surveillance
* **AUM Scalability Warning**:
  * Small-Cap Fund $\text{AUM} > ₹25,000\text{ Crores}$: High risk of illiquidity during market corrections.
  * Mid-Cap Fund $\text{AUM} > ₹40,000\text{ Crores}$: Forces the fund manager to buy large-caps, diluting the mandate.
* **SEBI Categorization Compliance**:
  * Large-Cap funds must maintain $\ge 80\%$ in top 100 stocks.
  * Multi-Cap funds must maintain $\ge 25\%$ each in Large, Mid, and Small caps. Any deviation is flagged as **Mandate Drift**.

---

## 4. Framework 3: The 5-Pillar Commercial Real Estate Matrix (SM REITs & InvITs)
*Target Universe: Small and Medium Real Estate Investment Trusts under the SEBI March 2024 Framework and publicly traded REITs/InvITs.*

| Pillar | Metric / Ratio | Regulatory / Analytical Threshold | Diagnostic Significance |
| :--- | :--- | :--- | :--- |
| **1. Asset Completion & Occupancy** | Completed Revenue Property % | $\ge 95\%$ completed property (SEBI Mandate) | Eliminates execution and construction delays completely. |
| **2. Payout Purity (NDCF)** | Distribution Yield & Upstreaming Ratio | $95\%$ SPV to Scheme; $100\%$ Scheme to Investor | Guarantees contractual quarterly rental cash flows to demat. |
| **3. Tenant Moat & WALE** | Weighted Average Lease Expiry (WALE) | $\text{WALE} \ge 4.5\text{ Years}$; Top 3 Tenants $< 40\%$ | Assesses vacancy shock and counterparty credit rating. |
| **4. Leverage & Solvency Headroom** | Debt-to-Asset Ratio ($\text{LTV}$) | $\text{LTV} \le 49\%$ (SEBI ceiling); Credit Rating if $> 25\%$ | Protects equity unitholders from interest rate escalation. |
| **5. Cap Rate & Micro-Market Spread** | Net Capitalization Rate vs. 10Y G-Sec | $\text{Cap Rate} \ge Y_{\text{G-Sec}} + 150\text{ bps}$ | Ensures adequate risk premium over sovereign risk-free rate. |

---

## 5. Framework 4: Safe Havens & Alternative Behavioral Radar
*Target Universe: Sovereign Gold Bonds (SGB), Gold ETFs, Digital Gold, Gold Leasing, P2P Lending, and SNBL.*

### Sovereign Gold Bond (SGB) vs. Alternatives Formula
$$\text{Net Realized Yield}_{\text{Gold}} = \Delta P_{\text{Spot}} + \text{Coupon} - \text{GST} - \text{Spread} - \text{TER} - \text{Capital Gains Tax}$$

* **SGB**: $\Delta P_{\text{Spot}} + 2.5\% \text{ sovereign coupon} - 0\% \text{ GST} - 0\% \text{ Spread} - 0\% \text{ CGT (at maturity)}$. *(Benchmark Standard)*.
* **Digital Gold (Jar/SafeGold)**: $\Delta P_{\text{Spot}} + 0\% - 3.0\% \text{ GST} - 2.5\% \text{ Spread} - \text{Slab Tax}$. *(Immediate $\approx 5.5\%$ structural capital drag)*.
* **Gold Leasing (Gullak Gold+)**: High-Risk Flag: Advertised $16\%$ return carries **unsecured jeweler credit risk** outside SEBI/RBI regulations.

### Shadow-Banking Warning Radar
* **P2P Lending Scorecard (RBI 2024 Compliance)**:
  * Strict prohibition of credit enhancement or liquidity guarantees.
  * Direct exposure to unsecured retail borrowers without platform loss-absorption.
  * Score: Classified as **Speculative Unsecured Debt**.
* **Save Now, Buy Later (SNBL) Spendvesting Diagnostic**:
  * $\text{Effective Yield} = \text{Liquid Mutual Fund Yield} + \text{Brand Subvention Discount (2–5\%)}$.
  * Classified as **High-Utility Consumption Hedging**.

---

## 6. Data Ingestion & Zero-Hallucination Grounding Schema

All metrics in these frameworks must be grounded in cryptographically verified primary filings:
1. **Debt & Bonds**: BSE Debt Reporting Platform, NSE RFQ logs, MCA Charge Filings, and SEBI-registered Credit Rating Agency (CRA) press releases.
2. **Mutual Funds**: Association of Mutual Funds in India (AMFI) monthly portfolio disclosures (Scheme-wise Full Portfolio in standardized `.xls` / `.csv` format), SID/KIM regulatory documents.
3. **SM REITs**: SEBI Offer Documents, semi-annual Registered Valuer reports, and exchange distribution announcements.
4. **Sovereign Benchmarks**: Reserve Bank of India (RBI) Daily Financial Benchmarks (FBIL) for G-Sec and T-Bill yield curves.
