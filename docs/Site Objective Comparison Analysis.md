# **Site Objective Comparison Analysis**

[https://gemini.google.com/app/2c53589d98493ac1](https://gemini.google.com/app/2c53589d98493ac1)

*User prompt: Based on the analysis of screener, I'd like to understand the following. Do the objectives of this site and mine match?*

Response: Screener.in and your platform share a common philosophy regarding fundamental rigor in the Indian equities market, but your ultimate product objectives and functional scopes diverge significantly.

**Where Your Objectives Align**

> * **Grounded Indian Equity Fundamentals:** Both platforms focus on Indian listed equities (BSE/NSE), prioritizing fundamental business health—such as balance sheet leverage, capital allocation metrics (ROCE/ROE), and promoter governance—over short-term technical trading indicators.  
> * **Workflow Automation:** Screener was created to automate the manual compilation of corporate earnings and financial ratios; your platform automates qualitative equity synthesis into standardized 7-pillar reports.  
> * **Regulatory Ground Truth:** Both systems anchor themselves directly in primary exchange filings, board disclosures, and corporate announcements to eliminate unreliable secondary noise and hallucinations.

**Where Your Objectives Diverge**

| Strategic Dimension | Screener.in | Your Stock Research Platform |
| :---- | :---- | :---- |
| **Asset Universe** | **Equities Only:** Strictly confines itself to \~4,000+ listed BSE/NSE companies. | **Multi-Asset Architecture:** Extends from stocks (Tier 1\) to Mutual Fund look-throughs (Tier 2\) and Fixed Income/FDs (Tier 3). |
| **End-State Goal** | **Research Workbench:** Serves as a data terminal and query engine for active stock-pickers. | **Holistic Portfolio Audit:** Unifies multi-asset holdings to evaluate user allocation, risk, and rebalancing (Capstone). |
| **Core Functionality** | **Top-Down Discovery:** Uses a quantitative, SQL-like query engine to filter the entire market into shortlists. | **Bottom-Up Synthesis:** Evaluates specific tickers across 7 qualitative pillars (TAM, Moat, ESG, Drop Diagnostic). |
| **Analytical Output** | **Raw Tabular Data:** Provides unopinionated 10–15 year financial statements and Excel template automation. | **Actionable Verdicts:** Generates synthesized Buy/Hold/Sell guidance, health cards, and narrative reports. |

**Strategic Relationship**

Screener.in's objective is to be the **foundational data operating system** for fundamental equity screening. It intentionally avoids technical charting, mutual funds, fixed income, and automated portfolio management.

In contrast, your platform’s Tier 1 equities engine replicates Screener's focus on fundamental health, but your true objective is an **automated multi-asset intelligence and portfolio audit engine**. Screener serves as an architectural benchmark for how to standardize Indian corporate filings, but your roadmap reaches into portfolio-level evaluation that Screener deliberately leaves untouched.

---

*User prompt: are there other sites offering information at the scale and accuracy as screener?*

Response: In the Indian equity ecosystem, no single retail platform completely mirrors Screener.in’s exact architecture—specifically its 15-year standardized financial statements, unopinionated raw PDF regulatory links, and bidirectional Excel modeling sync. However, several platforms match or exceed its data scale and accuracy in specialized areas.

| Platform | Scale & Market Coverage | Primary Data Sourcing | Analytical Niche vs. Screener |
| :---- | :---- | :---- | :---- |
| **Tijori Finance** | \~4,000+ Indian listed equities | Exchange filings, export-import data, company presentations | **Operational & Segment Depth:** Excels at product-wise revenue splits, market share, and raw material cost tracking rather than 15-year raw accounting statements. |
| **Trendlyne** | NSE, BSE, and Mutual Funds | Primary exchange feeds, institutional broker research | **Broker Consensus & Factor Scoring:** Tracks forward price targets, earnings-per-share (EPS) upgrades/downgrades, and proprietary forensic/DVM scores. |
| **Capitaline / CMIE Prowess** | Entire Indian public & large private corporate universe | Primary audited annual reports with manual forensic normalization | **Institutional Ground Truth:** The enterprise database standard used by domestic mutual funds and research desks; vastly deeper than retail tools, but clunky and enterprise-priced. |
| **TIKR Terminal / QuickFS** | 50,000+ equities globally (including NSE/BSE) | S\&P Capital IQ institutional feeds | **Global Fundamental Reach:** Offers 15-year standardized financial statements, segment data, and valuation multiples globally, mirroring Screener’s clean data density internationally. |
| **Tickertape** | NSE/BSE equities, ETFs, Mutual Funds, Gold | CMIE / Exchange feeds | **Visual Discovery:** Accessible visual screening and red-flag alerts tailored to retail investors, though it offers less historical balance sheet depth and lacks custom Excel injection. |

**Primary Contenders by Research Category**

> * **Operational Reality (Tijori Finance):** If your goal is to analyze *why* a company's margins shifted, Tijori provides the operational breakdown that accounting statements omit—such as manufacturing capacity utilization, customer concentration, and global commodity price dependencies.  
> * **Forward Estimates (Trendlyne):** While Screener relies almost entirely on historical backward-looking results, Trendlyne aggregates institutional sell-side consensus to show forward earnings estimates and broker ratings.  
> * **Institutional Lineage (Capitaline & C-MOTS):** Screener’s underlying fundamental data engine is sourced from C-MOTS Internet Technologies. Platforms subscribing directly to Capitaline or C-MOTS data feeds achieve identical institutional accounting accuracy.

**What Keeps Screener Distinct**

Screener retains a unique moat by refusing to add technical charting clutter, brokerage trading integration, or algorithmic buy/sell ratings. By pairing standardized historical tables directly with original exchange PDFs alongside automated master Excel template injection, it remains the standard workbench for independent financial modeling in India.

---

*User prompt: My objective is to understand if there are any sites (institutional or individual) who offer a similar structure and outcome as the one we're building.*

Response: No single platform across the retail or institutional landscape currently offers your exact end-to-end architecture: an **automated qualitative AI equity thesis engine (Tier 1\)** whose outputs propagate upward to evaluate **mutual fund holdings (Tier 2\)**, alongside **fixed income real returns (Tier 3\)**, unified into a **holistic portfolio audit (Capstone)**.

Instead, the market is fragmented into platforms that solve isolated layers of your stack.

| Platform | Tier 1: Equities Thesis | Tier 2: MF Look-Through | Tier 3: Fixed Income | Capstone: Holistic Audit | Architecture & Workflow Parallels |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **Value Research** *(Premium / Portfolio Doctor)* | Quantitative / Curated | **Strong** (Overlap & equity style) | **Strong** (FDs, PPF, Bonds, NPS) | **High** (Asset allocation & risk audits) | **Closest to your Capstone:** Ingests multi-asset portfolios via CAS, calculates fund overlap, and evaluates asset splits. **Gap:** Equities rely on backward-looking ratios; lacks automated 7-pillar qualitative synthesis or drop diagnostics. |
| **Morningstar Direct / Advisor Workstation** | Institutional Analyst Coverage | **Gold Standard** (Instant X-Ray) | **Strong** (Effective duration & credit) | **High** (Institutional portfolio health) | **Closest to your Tier 2 Look-Through:** Deconstructs funds into underlying company fundamentals, style boxes, and credit profiles. **Gap:** Enterprise-priced (\$10k+/yr), quantitative factor-driven, and lacks automated LLM-driven business evaluations for broader Indian small/mid-caps. |
| **INDmoney** | Basic (Broker targets & generic scores) | **Moderate** (Stock overlap alerts) | **Moderate** (Tracks FDs, EPF, NPS) | **Moderate** (Net worth tracking & basic health) | **Retail Capstone Aggregator:** Consolidates all Indian asset classes via account aggregators and CAS files. **Gap:** Analytical depth is shallow; treats stocks as price tickers rather than evaluating business moats or governance. |
| **Altys.ai / Screener AI** | **Strong** (Concall RAG & filing summarization) | **None** | **None** | **None** | **Closest to your Tier 1 Focus:** Focuses on extracting qualitative insights from exchange filings and concalls. **Gap:** Pure equity terminals that do not touch mutual funds, fixed income, or user portfolio audits. |
| **PrimeInvestor.in** | Curated SEBI RA Theses | Curated Fund Lists | Recommended FDs & Bonds | Static Portfolio Reviews | **Methodological Alignment:** A boutique advisory covering stocks, funds, and safe debt with holistic portfolio guidance. **Gap:** Entirely human-researched by analysts rather than powered by an automated, self-updating data engine. |

**Your Core Structural Wedge**

The fundamental differentiator of your roadmap is the **upward propagation of qualitative equity health**:

> * **The Industry Standard Approach:** Platforms like Morningstar, Value Research, and INDmoney evaluate mutual funds using trailing quantitative metrics—Sharpe ratios, Alpha, Beta, standard deviation, and past NAV returns. When they perform a "look-through," they only report basic market cap splits (large/mid/small) or sector weights.  
> * **Your Architectural Approach:** You plan to ingest mutual fund portfolio disclosures and feed the underlying company holdings directly through your **Tier 1 7-pillar engine**. This allows your system to score a mutual fund based on the *forward-looking business quality, governance, and competitive moats* of the actual companies it holds, rather than relying on lagging NAV performance.

While platforms like Value Research and Morningstar have perfected the mechanical math of portfolio look-throughs, none have combined that capability with an automated, exchange-grounded qualitative equity audit engine.

---

*User prompt: What's interesting is that should any of these established entities want to build out something that replicates my offering, because of how close they are to it already, they could just market it or replicate it easily. Challenge my assumption.*

Response: The assumption that incumbents can easily replicate your platform mistakes **technical feasibility** for **strategic willingness**. While platforms like Screener, Trendlyne, Value Research, or Morningstar have the financial engineering muscle to build your stack, deep organizational, regulatory, and economic friction actively prevents them from doing so.

**1\. The SEBI Regulatory & Liability Firewall**

> * **The "Advice" Boundary:** The moment your engine issues explicit qualitative verdicts (Buy/Avoid, Moat ratings, Structural Drop Diagnostics) and audits portfolio health, it crosses the line from *data aggregation* to *financial advice*.  
> * **Incumbent Paralysis:** Large institutions with millions of users avoid automated, LLM-generated verdicts because SEBI Research Analyst (RA) and Investment Adviser (RIA) compliance carries severe regulatory risk for unverified AI output. Incumbents stick to neutral ratios or human-authored reports to protect their corporate licenses.

**2\. Channel Conflict and Distribution Economics**

> * **Monetization Clash:** Platforms like INDmoney, Groww, and retail portals generate substantial revenue from brokerage commissions, mutual fund distribution, or institutional partnerships.  
> * **The Look-Through Threat:** Your Tier 2 look-through engine evaluates mutual funds by auditing the fundamental quality of their underlying stock holdings rather than marketing past returns. Telling a user that a top-selling fund is stuffed with low-moat or overvalued equities directly undermines fund distribution pipelines and asset manager relationships.

**3\. Brand Orthodoxy and the Innovator's Dilemma**

> * **Screener’s Dogma:** Screener.in's multi-decade brand equity rests entirely on being an unopinionated, un-gamified fundamental workbench. Adding generative AI summaries, automated buy/sell badges, or mutual fund audits alienates their core audience of DIY value investors and violates their minimalist ethos.  
> * **Morningstar’s Sunk Capital:** Institutional incumbents have invested decades and millions of dollars into trailing NAV metrics, style boxes, and backward-looking factor math. Validating a qualitative, forward-looking stock look-through methodology cannibalizes their own proprietary legacy frameworks.

**4\. The Unit Economics of Inference vs. SQL**

> * **Compute Asymmetry:** Calculating a Sharpe ratio, PE ratio, or asset-allocation split across a portfolio requires microseconds of cheap relational database queries.  
> * **Inference Overhead:** Running 40 to 60 underlying equities in a mutual fund portfolio through an LLM search-grounding and qualitative reasoning pipeline introduces latency and recurring token expenses. Incumbents built on low-overhead server models cannot justify replacing microsecond math with heavy LLM inference loops across millions of free users.

Incumbents are bound by their revenue streams, regulatory footprints, and existing brand promises. Your structural wedge is not that they *cannot* write the code; it is that their business models actively penalize them if they do.

Given these institutional barriers, do you intend to position your platform primarily as an independent, subscription-based auditor (pure software) or pursue a registered advisory model (SEBI RA/RIA)?

---

*User prompt: Even as a subscription based auditor, I would still have to submit to regulatory requirements, and if using LLMs to arrive at reporting isn't legal, then what we're doing won't see the light of day. Challenge my assumption.*

Response: Using LLMs to generate financial research reports is entirely legal in India. SEBI does not ban generative AI; rather, under its regulatory framework for Research Analysts (RAs) and Investment Advisers (IAs), SEBI explicitly permits AI/ML tools provided the entity adheres to strict disclosure and accountability norms.

Your assumption conflates **algorithmic assistance** with **unregulated advisory**. The regulatory viability of your platform hinges not on whether you use an LLM, but on the nature of the output you deliver to end-users.

**The Legal Reality of AI in Indian Capital Markets**

> * **The Accountability Mandate:** SEBI rules stipulate that registered entities can utilize third-party AI and LLMs for research, concall synthesis, and data extraction. However, the human entity remains 100% legally liable for data security, accuracy, and any misleading claims. A platform cannot cite "model hallucination" as a legal defense.  
> * **Mandatory AI Disclosure:** Registered entities deploying AI models must explicitly disclose the extent of AI usage, data sources, and model limitations in client agreements and research disclaimers.  
> * **The "Zero-Hallucination" Moat:** Your engineering choices—grounding models against exchange-direct APIs, using deterministic BSE announcement gates, and building post-generation verification auditors—align with SEBI’s technical expectations for AI risk management.

**The Two Operating Paths for Your Platform**

The regulatory boundary is determined by whether your software provides **prescriptive advice** or **descriptive diagnostics**.

| Regulatory Dimension | Path A: Software Tool / Analytics Utility | Path B: Registered Research Analyst (SEBI RA) |
| :---- | :---- | :---- |
| **Legal Classification** | Data publisher / Software provider (Unregulated) | Registered Market Intermediary (SEBI Regulated) |
| **Monetization** | Subscription paywall (SaaS) allowed | Advisory/research subscription fee allowed |
| **Permissible Output** | 7-Pillar diagnostics, moat metrics, fund look-throughs, ratio health cards | Explicit **BUY / HOLD / SELL** verdicts, price targets, entry/exit bands |
| **LLM Role** | Summarizes filings, contextualizes concalls, calculates exposure | Drafts research notes under human RA oversight and sign-off |
| **Industry Benchmarks** | **Screener.in, Tijori Finance, Trendlyne** | **Univest, PrimeInvestor, Brokerage Desks** |

**What You Must Adjust to Launch**

If your prompt generates explicit \# VERDICT: \[BUY / HOLD / SELL\] tags and execution instructions, SEBI considers that a regulated research report regardless of whether you charge a subscription.

To operate purely as a software platform without submitting to an RA license:

> * **Deprecate Prescriptive Verdicts:** Refactor the system prompt in analyzer.py to remove binary Buy/Hold/Sell labels.  
> * **Pivot to Diagnostic Scoring:** Present findings as structured health scores, moat checklists, and drop diagnostics (e.g., "Pillar 3 Governance: 85/100", "Capital Allocation: Improving").  
> * **Empower Self-Directed Analysis:** Frame the output as an automated factual synthesis designed for investor education and independent evaluation, mirroring Screener’s algorithmic "Pros & Cons" engine.

If you instead choose to retain explicit Buy/Sell ratings, the legal path requires registering as an individual or corporate Research Analyst under the SEBI (Research Analysts) Regulations, filing the required AI disclosures, and using your verification pipeline as proof of rigorous due diligence.

---

