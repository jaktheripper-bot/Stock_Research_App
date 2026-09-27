# **Refining Alerts and Comparison Features**

[https://gemini.google.com/app/1e05f5f86e1993ea](https://gemini.google.com/app/1e05f5f86e1993ea)

*User prompt: 2 more features i think will add value, one is setting an alert for a company of there are any changes to the company and the next is comparing companies \- users should be given a warning if companies are too disparate to be compared (based on fundamental data), but offered the option to do so anyway.*

Response: Both features add value, but their execution has a critical flaw: defining "any changes" will cause alert fatigue, and defining "too disparate" requires strict heuristic boundaries so it doesn't degrade user trust.

Here is the breakdown of how to build both features effectively:

### **1\. Company Alert System**

"Any change" is an anti-pattern in stock apps \[Certain\]. If a user receives a notification for every minor SEC filing, minor price fluctuation, or routine press release, they will mute or uninstall the app within a week.

**Refinement:**

> * **Granular Trigger Categorization:** Do not build a catch-all toggle. Allow users to subscribe by event type:  
  * **Material Events:** 8-K filings, C-suite changes, earnings release dates, dividend declarations/cuts \[Certain\].  
  * **Fundamental Shifts:** Guidance revisions, quarterly revenue/EPS misses or beats outside a ±5% band \[Certain\].  
  * **Valuation/Technical:** Significant price movements (±5% in a single session) or 52-week highs/lows.  
> * **Digest Option:** Default non-critical updates (e.g., routine insider transaction forms like Form 4\) to an end-of-week or end-of-day digest rather than push notifications.

### **2\. Cross-Company Comparison with Disparity Warning**

A rigid comparison block frustrates power users, so an overrideable soft warning is the correct UX decision \[Certain\]. However, disparity cannot simply mean different market caps or different sectors.

**Heuristics for "Too Disparate":** To trigger the warning accurately, evaluate disparities across three specific axes:

> 1. **Sector/Business Model Disparity:** Comparing a capital-intensive bank (financials) against an asset-light SaaS company (tech) using standard multiples like EV/EBITDA or P/E produces invalid conclusions \[Certain\].  
   * *Trigger:* When GICS/sector classifications do not match.  
   * *Copy:* *"These companies operate in fundamentally different sectors. Multiples like EV/EBITDA or gross margin cannot be compared 1:1."*  
> 2. **Lifecycle/Maturity Stage:** Comparing an early-stage unprofitable growth company (*P*/*E*\<0, heavy burn) to a mature dividend-paying blue chip.  
   * *Trigger:* When one company has consistently negative net income/operating cash flow and the other is a mature cash-flow positive firm.  
   * *Copy:* *"One of these companies is an early-stage growth asset while the other is a mature dividend payer. Growth metrics and valuation multiples are not directly equivalent."*  
> 3. **Scale/Capital Structure Divergence:** Comparing a micro-cap (\<\$300M) to a mega-cap (\>\$200B).  
   * *Trigger:* A 100x or greater divergence in market capitalization or enterprise value.

**Alternative Workflow:** When the user clicks "Compare Anyway," automatically adjust the comparison table to normalize the metrics:

> * Suppress or grey out non-comparable ratios (e.g., P/B for asset-light software or EV/EBITDA for commercial banks).  
> * Highlight universal fundamentals instead: ROIC, Free Cash Flow Yield, and 3-Year Revenue CAGR \[Certain\].

The risk in your approach is that vague alerts and purely metric-based disparity checks will trigger false alarms and alienate users who know exactly why they are comparing two different assets.

What specific fundamental metrics are you planning to use as the primary baseline for the disparity check?

---

*User prompt: I agree with your refinement system for now, let's add it to the task list and deep dive later.*

Response: The updated backlog is organized below, incorporating the refined alerting and disparity warning specifications:

### **Priority Implementation & Feature Backlog**

#### **1\. Core Platform Stabilization & UI (Immediate)**

> * **Priority 2 (7-Pillar Visual Health Card):** Embed a color-coded status badge grid (Macro, Moat, Governance, Drop Diagnostic, Valuation, Balance Sheet, Verdict) directly above streamed reports in app.py.  
> * **Fundamental Valuation Data (FMP / Reliable REST Integration):** Replace fragile scraping fallbacks with structured fundamental REST endpoints to ensure valid P/E, EPS, and Market Cap ingestion.  
> * **PDF Export Styling:** Standardize report downloads with embedded safe-harbor compliance disclaimers.

#### **2\. Surveillance & Workflow Automation (Next Phase)**

##### **Feature A: Granular Event Alerting Engine**

> * **Material Disclosures & Regulatory Filings:** Trigger instant notifications on BSE corporate announcements, 8-K equivalents, insider/SAST trades, and board appointments/resignations.  
> * **Fundamental & Financial Shifts:** Alert on quarterly earnings beats/misses outside a ±5% threshold or official guidance updates.  
> * **Valuation & Volatility Shocks:** Monitor price swings exceeding ±5% within a single trading session or breaches of 52-week highs/lows.  
> * **Notification Routing & Aggregation:** Enable toggleable channels (push vs. daily/weekly digest) to filter non-urgent filings (e.g., routine insider disclosures) and eliminate notification fatigue.

##### **Feature B: Normalized Cross-Company Comparison**

> * **Three-Tier Disparity Gate:** Trigger soft, overrideable warnings when comparing entities across divergent baselines:  
  1. *Sector/Business Model Disparity:* GICS/sector mismatch (e.g., Banks/NBFCs vs. asset-light SaaS) where multiples like EV/EBITDA or gross margins do not align.  
  2. *Lifecycle/Maturity Disparity:* Unprofitable high-growth assets (*P*/*E*\<0, negative operating cash flow) vs. mature dividend-paying blue chips.  
  3. *Scale & Capital Structure Disparity:* Greater than a 100x divergence in enterprise value or market capitalization.  
> * **Fallback & Normalization Workflow:** When users select *"Compare Anyway,"* suppress or grey out non-transferable metrics (e.g., P/B for tech, EV/EBITDA for banking) and emphasize universal operational indicators (ROIC, FCF yield, 3-year revenue CAGR).

#### **3\. Deep Analytical Capabilities (Downstream Milestones)**

> * **Archived Report Differential Tracker:** Implement immutable, append-only snapshot archiving (report\_revisions table) to track quarterly thesis shifts and decouple qualitative rating drift from valuation expansion.  
> * **Tier 2 Mutual Fund Look-Through Engine:** Ingest fund portfolio disclosures and evaluate aggregate fund quality by propagating underlying holdings through the 7-pillar engine.

When we return to Feature B, do you prefer configuring the disparity gate with hard-coded GICS industry tags or evaluating sector differences dynamically using exchange API metadata?

---

