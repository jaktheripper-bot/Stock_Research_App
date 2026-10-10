# Comprehensive Project-Wide Audit & Strategic System Evaluation

**Document Target:** `audit_findings.md`  
**Evaluation Date:** October 6, 2026  
**Status:** Complete Audit Report — *Evaluation Only (No Code Modifications Applied)*  
**System Evaluated:** Stock Research App (`Jaktheripper-bot/Stock_Research_App`)

---

## Table of Contents
1. [Executive Summary & System Scorecard](#1-executive-summary--system-scorecard)
2. [Dimension 1: Internet & Development Best Practices Audit](#2-dimension-1-internet--development-best-practices-audit)
   - [2.1 Security, Secrets & Access Control](#21-security-secrets--access-control)
   - [2.2 Database Architecture, Connection Pooling & Test Isolation](#22-database-architecture-connection-pooling--test-isolation)
   - [2.3 Performance, Caching & Asset Delivery](#23-performance-caching--asset-delivery)
   - [2.4 Web Standards, SEO & Domain Consistency](#24-web-standards-seo--domain-consistency)
3. [Dimension 2: Codebase Health, Leftover & Deprecated Code Audit](#3-dimension-2-codebase-health-leftover--deprecated-code-audit)
   - [3.1 The Dual-Architecture Schism (FastAPI SSR vs. Legacy Streamlit)](#31-the-dual-architecture-schism-fastapi-ssr-vs-legacy-streamlit)
   - [3.2 CI/CD Pre-Flight Gate Drift](#32-cicd-pre-flight-gate-drift)
   - [3.3 Silent Failure Anti-Pattern & API Contract Mismatches](#33-silent-failure-anti-pattern--api-contract-mismatches)
   - [3.4 Orphaned Scripts & Codebase Hygiene](#34-orphaned-scripts--codebase-hygiene)
4. [Dimension 3: Strategic & Roadmap Alignment (P1 through P5)](#4-dimension-3-strategic--roadmap-alignment-p1-through-p5)
   - [4.1 Core Mission, Objectives & Regulatory Scope](#41-core-mission-objectives--regulatory-scope)
   - [4.2 Priority-by-Priority Delivery Analysis (P1 to P5)](#42-priority-by-priority-delivery-analysis-p1-to-p5)
   - [4.3 Upstream Data Source Licensing & Commercial Risk Exposure](#43-upstream-data-source-licensing--commercial-risk-exposure)
5. [Dimension 4: UI/UX & Behavioral Research Study Compliance](#5-dimension-4-uiux--behavioral-research-study-compliance)
   - [5.1 Behavioral Archetypes Alignment](#51-behavioral-archetypes-alignment)
   - [5.2 Cognitive Biases & Engineered Interventions](#52-cognitive-biases--engineered-interventions)
   - [5.3 Typographic & Visual Semantics Compliance](#53-typographic--visual-semantics-compliance)
   - [5.4 Architectural Feature Gaps (Research vs. Web Production)](#54-architectural-feature-gaps-research-vs-web-production)
6. [Dimension 5: Interactive Functionality & Component Verification](#6-dimension-5-interactive-functionality--component-verification)
   - [6.1 Navigation, Menus & Sub-Tabs](#61-navigation-menus--sub-tabs)
   - [6.2 Omni-Search & Autocomplete Widget](#62-omni-search--autocomplete-widget)
   - [6.3 Pre-Mortem Inversion Engine & Disparity Gate Overrides](#63-pre-mortem-inversion-engine--disparity-gate-overrides)
   - [6.4 Commercial Monetization Flow (Razorpay & PDF Generation)](#64-commercial-monetization-flow-razorpay--pdf-generation)
   - [6.5 Complete Route & Endpoint Health Matrix (73 Routes)](#65-complete-route--endpoint-health-matrix-73-routes)
7. [Dimension 6: Prioritized Recommendations & Action Plan](#7-dimension-6-prioritized-recommendations--action-plan)
   - [7.1 Upstream Data Sourcing vs. Commercial Monetization Risk](#critical-analysis-upstream-data-sourcing-vs-commercial-monetization-risk)
   - [7.2 Prioritized Active Task Register (P0 to P3)](#72-prioritized-active-task-register-p0-to-p3)
   - [7.3 Historical Build & Completion Ledger](#73-historical-build--completion-ledger)


---

## 1. Executive Summary & System Scorecard

This comprehensive audit was conducted across the entire **Stock Research App** ecosystem to rigorously evaluate architectural integrity, security, regulatory guardrails, behavioral UI/UX compliance, interactive functionality, and code hygiene.

The application has successfully evolved from a local Python prototyping tool into an institutional-grade, multi-asset forensic analysis platform. The production deployment on Render ([render.yaml](file:///Users/lyndonpinto/Documents/Stock_Research_App/render.yaml)) runs a high-performance **FastAPI Server-Side Rendered (SSR)** web service ([web/main.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/main.py)) backed by PostgreSQL (Supabase) in production and SQLite (`reports.db`) locally.

However, the audit reveals critical architectural divergence, security vulnerabilities in public authentication, brittle API contracts in new database modules, and pre-flight CI gates that test deprecated code paths while ignoring production endpoints.

### Executive System Scorecard

| Audit Dimension | Status / Grade | Key Findings & Summary |
| :--- | :---: | :--- |
| **1. Internet & Development Best Practices** | **B+** | Strong secrets management, robust dual-binding database pooling, fast caching. **Critical Flaw:** `/api/auth/signin` accepts unverified arbitrary emails, allowing identity spoofing; database tests share production `reports.db`. |
| **2. Codebase Hygiene & Stray Code** | **B-** | Significant architectural schism: legacy Streamlit code (`app.py`, `admin.py`, `ui/`) coexists with production FastAPI. CI pre-flight scripts still audit Streamlit. Silent exception swallowing in `core/db/` modules masks schema mismatches. |
| **3. Strategic & Roadmap Alignment** | **A-** | Priorities 1 through 5 are substantially implemented (Debt, Mutual Funds, Sovereign Yields, ETFs, Tax Engine, REITs, SGBs, Safety Radar). Clear roadmap documented, but commercial exchange data licensing remains an unhedged operational risk. |
| **4. UI/UX & Behavioral Research Compliance** | **A** | Faithful adherence to `.antigravity/docs/BEHAVIORAL_RESEARCH_STUDY.md`: Tabular lining numerals (`tabular-nums`), color scarcity, 3-tier Disparity Gates, Pre-Mortem inversion engine, and WCAG 2.2 target sizing. Minor gap: PEAD 60-day visual drift band is not yet surfaced in web templates. |
| **5. Interactive Functionality & Endpoints** | **A** | All 73 registered FastAPI routes return valid HTTP 200/404 responses. Search autocomplete, Razorpay orders, PDF rendering, pre-mortem ledgering, and responsive mobile drawers operate smoothly. |
| **Overall Platform Rating** | **Solid A-** | High domain sophistication, rigorous SEBI compliance, and rich features. Immediate focus required on auth hardening, CI modernization, and test isolation. |

---

## 2. Dimension 1: Internet & Development Best Practices Audit

### 2.1 Security, Secrets & Access Control

#### Secrets & Environment Variables
- **Status:** **PASS**
- **Findings:** 
  - An inspection of `.gitignore` confirms that `.env`, `*.env`, `rzp-key.csv`, and local database files are properly excluded.
  - A comprehensive git history search verified that secrets (`GEMINI_API_KEY`, `RAZORPAY_KEY_SECRET`, `SUPABASE_DB_URL`, `rzp-key.csv`) were **never committed** to git revision history.
  - Runtime configuration in [core/config.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/config.py) cleanly isolates secrets using `os.getenv` and dynamic fallback lookups.

#### Public Authentication & Identity Security
- **Status:** **CRITICAL VULNERABILITY**
- **Location:** [web/main.py:1465-1495](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/main.py#L1465-L1495)
- **Code Reference:**
  ```python
  @app.post("/api/auth/signin")
  async def api_signin(payload: SignInRequest):
      clean_email = (payload.email or "").strip().lower()
      ...
      user_id = f"usr_{clean_email.replace('@', '_at_').replace('.', '_')}"
      user = get_or_create_user(user_id=user_id, email=clean_email, ...)
      return json_response_with_cache({"success": True, "user": user, ...})
  ```
- **Analysis:**
  - The public `/api/auth/signin` endpoint accepts any email string with basic syntax validation and creates or retrieves a session profile.
  - **Attack Vector:** An attacker can enter any valid user's email (e.g., a corporate subscriber or paying user) and instantly gain access to their user profile, history, and research credits. There is no password verification, Magic Link, OTP verification, or Google OAuth for public subscribers.
  - **Mitigation Required:** Implement Google OAuth (matching the admin console) or OTP-based email verification before issuing authenticated session cookies.

#### Administrative Access Control
- **Status:** **PASS**
- **Location:** [web/main.py:1924-1980](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/main.py#L1924-L1980)
- **Findings:**
  - The admin console at `/admin` is properly protected by Google OAuth with second-factor verification, strict email allowlisting (`ADMIN_USERS` / `ADMIN_EMAILS`), and immutable session auditing.
  - Background mutation routes such as `/api/admin/run-discovery` and `/api/admin/reseed-assets` enforce dual authentication: valid admin session cookie OR `x-admin-key` header verification.

#### CSRF & Request Security
- **Status:** **NEEDS HARDENING**
- **Findings:**
  - State-mutating API routes (such as `/api/premortem`, `/api/create-order`, `/api/verify-payment`) are processed via `POST` with JSON payloads. Because browsers do not automatically send JSON in standard cross-site form submissions without CORS preflight, CSRF risk is low.
  - However, no CSRF anti-forgery tokens (e.g., `SameSite=Strict` CSRF cookies) are enforced on web form submissions. Adding explicit CSRF middleware is recommended for modern web application hygiene.

---

### 2.2 Database Architecture, Connection Pooling & Test Isolation

#### Dual-Binding & Connection Management
- **Status:** **STRONG IMPLEMENTATION**
- **Location:** [core/db/connection.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/connection.py)
- **Findings:**
  - Transparent dual-binding between PostgreSQL (Supabase) in production and SQLite (`reports.db`) locally.
  - PostgreSQL uses a `ThreadedConnectionPool` wrapped by `_PooledConnectionProxy` to prevent socket exhaustion and handle graceful rollbacks on context exit.
  - SQLite connections are protected by `timeout=30.0` and `check_same_thread=False` to handle concurrent FastAPI threads.

#### Test Environment Isolation Gap
- **Status:** **HIGH DEFECT**
- **Location:** [core/db/connection.py:126](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/connection.py#L126)
- **Code Reference:**
  ```python
  conn = sqlite3.connect("reports.db", timeout=30.0, check_same_thread=False)
  ```
- **Analysis:**
  - Even when `os.environ.get("TESTING") == "1"`, the database layer unconditionally opens `"reports.db"`.
  - During automated test execution (e.g., `tests/test_priorities_3_4_5.py`), tests insert temporary mock data, modify schema records, and assert record counts directly against the persistent development database.
  - There is no dynamic redirection to `:memory:` or `test_reports.db`. Consequently, local dev data and automated test fixtures pollute one another.

---

### 2.3 Performance, Caching & Asset Delivery

#### In-Memory Route Caching & HTTP Headers
- **Status:** **PASS**
- **Location:** [web/main.py:270-320](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/main.py#L270-L320)
- **Findings:**
  - Public read-heavy endpoints utilize `json_response_with_cache()` with explicit `Cache-Control: public, max-age=300, stale-while-revalidate=600` headers.
  - Static files in `web/static/` are served with caching headers.
  - Prefetching: [web/static/js/main.js](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/static/js/main.js) implements hover-based link prefetching (`<link rel="prefetch">`), lowering perceived latency on internal navigation.

---

### 2.4 Web Standards, SEO & Domain Consistency

#### SEO & Crawler Directives
- **Status:** **INCONSISTENCY IDENTIFIED**
- **Location:** [web/main.py:2636-2646](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/main.py#L2636-L2646) vs. [web/main.py:1636-1665](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/main.py#L1636-L1665)
- **Analysis:**
  - In `robots_txt()`, line 2644 specifies:
    ```
    Sitemap: https://stock-research-app-2ljm.onrender.com/sitemap.xml
    ```
  - In `sitemap_xml()`, line 1643 specifies:
    ```python
    base_url = "https://stockresearch.app"
    ```
  - **Impact:** Search engine bots (Google, Bing, Perplexity) crawling `robots.txt` are redirected to the staging Render URL rather than the canonical custom domain `stockresearch.app`.
  - Canonical URLs and Open Graph tags should also be verified across newly added multi-asset pages (`/reits`, `/safety-radar`, `/sovereign`, `/etfs`).

---

## 3. Dimension 2: Codebase Health, Leftover & Deprecated Code Audit

### 3.1 The Dual-Architecture Schism (FastAPI SSR vs. Legacy Streamlit)

A primary architectural finding is that the repository contains two complete web application layers:

1. **Production Engine (FastAPI SSR):**
   - Active files: [web/main.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/main.py), [web/templates/](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/templates/), [web/static/](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/static/).
   - Executed in production by [Procfile](file:///Users/lyndonpinto/Documents/Stock_Research_App/Procfile) (`uvicorn web.main:app`) and [render.yaml](file:///Users/lyndonpinto/Documents/Stock_Research_App/render.yaml).
   - Powers all 73 public routes, multi-asset views, PDF exports, and billing.

2. **Legacy Prototype (Streamlit):**
   - Remaining files: [app.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/app.py), [admin.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/admin.py), [ui/](file:///Users/lyndonpinto/Documents/Stock_Research_App/ui/) (`ui/scorecard.py`, `ui/comparison.py`, `ui/views/`, `ui/components/`), [lint_streamlit.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/lint_streamlit.py), [test_ui_headless.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/test_ui_headless.py).
   - Executed locally via `./run.sh start` (`streamlit run app.py`).

**Architectural Risk:**  
Developers maintaining or extending the codebase may inadvertently add features to the Streamlit UI (which is not deployed to cloud production) or make changes to `ui/` that have zero effect on live users.

---

### 3.2 CI/CD Pre-Flight Gate Drift

- **Location:** [ci/checkpoint_manager.py:167-190](file:///Users/lyndonpinto/Documents/Stock_Research_App/ci/checkpoint_manager.py#L167-L190) and [run.sh:26-54](file:///Users/lyndonpinto/Documents/Stock_Research_App/run.sh#L26-L54)
- **Findings:**
  - The pre-flight verification gate in `checkpoint_manager.py` executes:
    ```python
    tiers = [
        ("Streamlit Static Linter", [py_exec, "lint_streamlit.py"]),
        ("System Contract Audit", [py_exec, "check_system.py"]),
        ("Interactive UI Action Simulation", [py_exec, "test_ui_headless.py"]),
        ("Latency Performance Benchmark", [py_exec, "benchmark.py"]),
    ]
    ```
  - **The Drift:** The mandatory pre-flight gate strictly validates the deprecated Streamlit interface. It does **not** execute `pytest tests/test_priorities_3_4_5.py` or audit any of the 73 FastAPI endpoints.
  - A release can pass the 4-tier pre-flight gate with 100% success while the live FastAPI application is broken.

---

### 3.3 Silent Failure Anti-Pattern & API Contract Mismatches

- **Location:** [core/db/reits.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/reits.py), [core/db/sovereign.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/sovereign.py), [core/db/safety_radar.py](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/db/safety_radar.py)
- **The Issue:**
  In several database helper functions, dictionary parameters are dereferenced using rigid mandatory key names:
  ```python
  # core/db/reits.py:215
  cp = float(reit["current_price"])
  nav = float(reit["nav_per_unit"])
  ```
  ```python
  # core/db/sovereign.py:195
  mp = float(sgb["market_price"])
  ```
  ```python
  # core/db/safety_radar.py:90
  prod_id = prod["product_id"]
  py = float(prod["promoted_yield_pct"])
  ```
  If a caller passes standard alternative names (e.g., `cmp_inr`, `nav_per_unit_inr`, `advertised_yield_pct`), Python raises a `KeyError`.
  
  The function then catches all generic exceptions:
  ```python
  except Exception as e:
      logger.error(f"Error saving REIT/InvIT {reit.get('symbol')}: {e}")
      conn.rollback()
      return False
  ```
- **Consequence:**
  In [tests/test_priorities_3_4_5.py:162](file:///Users/lyndonpinto/Documents/Stock_Research_App/tests/test_priorities_3_4_5.py#L162), the test passes `cmp_inr` and `nav_per_unit_inr` and calls `save_reit_or_invit(reit_item)` without asserting `self.assertTrue(...)`. The insert quietly fails and returns `False`. The subsequent assertion `self.assertGreaterEqual(len(reits), 1)` passes only because fallback default seed rows already existed in the table.
- **Recommendation:** Use flexible key mapping (e.g. `reit.get("current_price") or reit.get("cmp_inr")`) and enforce strict assertions in test suites.

---

### 3.4 Orphaned Scripts & Codebase Hygiene

| File | Status / Usage | Recommendation |
| :--- | :--- | :--- |
| `seed_all_assets.py` | Standalone CLI script to seed debt, mutual funds, sovereign, REITs, safety radar. | Maintain as utility script; ensure schema alignment with `core/db/`. |
| `lint_streamlit.py` | Legacy linter checking for `st.` calls and Streamlit deprecations. | Migrate to or supplement with a FastAPI/Jinja template linter. |
| `test_ui_headless.py` | Simulates Streamlit session state and button clicks. | Sandbox into `legacy/` or modernize to test FastAPI endpoints. |
| `benchmark.py` | Measures database query latency and analysis engine throughput. | Keep; add benchmark tests for FastAPI response latencies. |
| `admin.py` | Legacy Streamlit admin panel. | Deprecated; `/admin` SSR console in `web/main.py` is the official console. |

---

## 4. Dimension 3: Strategic & Roadmap Alignment (P1 through P5)

### 4.1 Core Mission, Objectives & Regulatory Scope

The application's stated objective (articulated across `.antigravity/docs/STRATEGY.md`, `.antigravity/docs/ARCHITECTURE.md`, and `.antigravity/docs/COMPLIANCE.md`) is:
> *To provide Indian investors with an institutional-grade, zero-hallucination forensic research utility that strips away emotional biases and narrative seduction, operating strictly under SEBI Safe Harbor as an automated data publisher without dispensing prescriptive investment advice.*

#### SEBI Regulatory Guardrails Evaluation:
- **Zero Hallucination:** Synthetic metrics are prohibited; raw financial statements and exchange prices are grounded in BSE/NSE/AMFI disclosures.
- **No Prescriptive Advice:** Zero instances of `BUY`, `HOLD`, or `SELL` recommendations exist in report generation or UI views.
- **Mandatory Safe-Harbor Notice:** Displayed on all web pages, report views, and exported PDFs:
  > *"Disclaimer: This report is automatically generated by an AI research assistant using public BSE disclosures and search grounding. It is intended strictly for informational and educational auditing purposes and does not constitute financial or investment advice."*

---

### 4.2 Priority-by-Priority Delivery Analysis (P1 to P5)

#### Priority 1: Fixed-Income & Debt Engine
- **Roadmap Goal:** Corporate debt schema, credit rating surveillance, 5-pillar credit core (YTM, duration, ACR $\ge 1.25\times$, ICR), and capital seniority tagging.
- **Actual Implementation:** **FULLY DELIVERED**
  - Database: `core/db/debt.py` tracks listed NCDs and SDIs under the ₹10,000 SEBI framework.
  - Analytics: `core/analysis/credit_engine.py` computes YTM, Macaulay/Modified duration, and ACR.
  - Web UI: `/debt` and `/debt/{isin}` render interactive credit scorecards, capital structure positions, and rating migration logs.

#### Priority 2: Mutual Fund Portfolio Look-Through Engine
- **Roadmap Goal:** AMFI monthly portfolio ingestion, dual-sleeve look-through (equity + debt), active share ($AS \ge 60\%$), Sortino ratio, downside capture, and TER fee drag analyzer.
- **Actual Implementation:** **FULLY DELIVERED**
  - Data Pipeline: `core/db/mutual_funds.py` ingests AMFI `NAVAll.txt` and scheme holdings.
  - Analytics: `core/analysis/fund_engine.py` computes overlap matrices, active share, and 10-year compounded fee drag.
  - Web UI: `/funds`, `/funds/{scheme_code}`, and `/funds/compare/overlap` provide comprehensive portfolio look-through diagnostics.

#### Priority 3: Sovereign Curve & ETF Analytics
- **Roadmap Goal:** Sovereign risk-free benchmarks (T-Bills, 10-Yr G-Sec, SDLs), ETF performance/liquidity matrix, and net real post-tax return calculator (marginal tax slabs + MOSPI CPI deflator).
- **Actual Implementation:** **FULLY DELIVERED**
  - Database & Analysis: `core/db/sovereign.py`, `core/analysis/sovereign_engine.py`, `core/analysis/etf_engine.py`, `core/analysis/tax_calculator.py`.
  - Web UI: `/sovereign`, `/etfs`, and `/calculator/tax` with real-time interactive calculations and API endpoints.

#### Priority 4: Fractional Real Estate (SM REITs) & Sovereign Gold (SGB)
- **Roadmap Goal:** Monitor SEBI SM REITs & InvITs under 2024 regulations (occupancy $\ge 95\%$, NDCF payout $\ge 95\%$, LTV $\le 49\%$), and SGB secondary market parity with Section 47(viic) capital gains tax exemptions.
- **Actual Implementation:** **FULLY DELIVERED**
  - Database & Analysis: `core/db/reits.py`, `core/analysis/reit_engine.py`, `core/analysis/sgb_engine.py`.
  - Web UI: `/reits` directory and `/api/sgb/tranches`.

#### Priority 5: Retail Safety & Shadow-Banking Diagnostic Radar
- **Roadmap Goal:** Diagnostic guardrail highlighting counterparty risks in unregulated gold leasing (Gullak Gold+), RBI-restricted P2P lending (12Club/LiquiLoans), and unrated NBFC deposits with a 0-100 Danger Score.
- **Actual Implementation:** **FULLY DELIVERED**
  - Database & Analysis: `core/db/safety_radar.py`, `core/analysis/safety_radar.py`.
  - Web UI: `/safety-radar` and `/api/safety-radar` rendering risk scorecards, regulatory status, and safe alternative recommendations.

---

### 4.3 Upstream Data Source Licensing & Commercial Risk Exposure

As documented in [source_evaluation.md](file:///Users/lyndonpinto/Documents/Stock_Research_App/source_evaluation.md):
- **Current Architecture:** Relies on free/public tiers (BSE India public web endpoints, AMFI daily NAV text dumps, RBI press releases, MOSPI public indices).
- **Commercial Risk:** Since the platform charges users for research dossiers (₹499 to ₹4,999 via Razorpay), public redistribution of exchange-copyrighted data creates licensing exposure under NSE/BSE data dissemination policies.
- **Mitigation Strategy:** Source evaluation documents a phased transition to licensed vendor feeds (e.g., EODHD commercial tier, CCIL market data, Accord/CMOTS mutual fund feed) once transaction thresholds are reached.

---

## 5. Dimension 4: UI/UX & Behavioral Research Study Compliance

The user interface was evaluated against the behavioral framework defined in `docs/Equity Researcher Behavioral UI_UX.md` and `.antigravity/docs/BEHAVIORAL_RESEARCH_STUDY.md`.

```mermaid
graph TD
    A[Behavioral UI/UX Framework] --> B[4 User Archetypes]
    A --> C[5 Cognitive Biases]
    A --> D[Ergonomic Heuristics]
    
    B --> B1[Forensic Sceptic: Governance Alerts & Cash Flows]
    B --> B2[Quality Compounder: Longitudinal Moat & ROCE]
    B --> B3[Relative Value Arbitrageur: Disparity Gates]
    B --> B4[Post-Investment Monitor: Thesis Integrity Check]
    
    C --> C1[Disposition Effect: Valuation De-anchoring]
    C --> C2[Overconfidence: Pre-Mortem Inversion Ledger]
    C --> C3[Confirmation Bias: Forced Failure Scenarios]
    C --> C4[Anchoring Bias: Historical Percentile Bands]
    C --> C5[False Equivalence: Universal Cash Normalization]
    
    D --> D1[Tabular Lining Numerals: tabular-nums]
    D --> D2[Color Scarcity: Monochromatic Base + Alert Accents]
    D --> D3[WCAG 2.2 AA: 24x24px Minimum Targets]
    D --> D4[Progressive Disclosure: Overview First]
```

### 5.1 Behavioral Archetypes Alignment

1. **The Forensic Sceptic (Risk-First Analyst):**
   - *Requirement:* Scrutinize cash flows, elevate SEBI LODR Regulation 30/33 disclosures (auditor resignations, promoter pledges).
   - *Implementation:* Corporate governance pillar and Forensic Red-Flag alert engine isolate material disclosures. Cash flow quality card is surfaced in dossier templates.
2. **The Quality Compounder (Moat & Capital Allocation Focused):**
   - *Requirement:* Longitudinal ROCE analysis, margin stability across raw material cycles.
   - *Implementation:* 7-Pillar analysis evaluates durable competitive moats, reinvestment rates, and capital efficiency.
3. **The Relative Value Arbitrageur:**
   - *Requirement:* Prevent "false equivalence" when comparing disparate business models.
   - *Implementation:* 3-Tier Disparity Gates in `/compare` evaluate Sector, Lifecycle, and Scale divergence before presenting comparisons.
4. **The Post-Investment Monitor:**
   - *Requirement:* Prevent "thesis drift" and the "sunk cost fallacy".
   - *Implementation:* Immutable revision history (`report_revisions`) tracks delta changes over time. Pre-mortem ledger forces explicit articulation of thesis risks.

---

### 5.2 Cognitive Biases & Engineered Interventions

| Cognitive Bias | Behavioral Vulnerability | Platform Intervention | Implementation Status |
| :--- | :--- | :--- | :---: |
| **Disposition Effect** | Selling winners too early, holding losers. | Valuation de-anchoring; removal of bright green/red entry-price anchors. | **COMPLIANT** |
| **Overconfidence** | Excessive trading, ignoring downside. | Immutable decision ledger recording pre-trade rationale. | **COMPLIANT** |
| **Confirmation Bias** | Narrative seduction by macro themes. | Mandatory Pre-Mortem Inversion Engine requiring answers to top 3 failure modes. | **COMPLIANT** |
| **Anchoring Bias** | Fixation on 52-week highs. | Multi-year valuation percentiles rather than simple price drawdown charts. | **COMPLIANT** |
| **False Equivalence** | Comparing multiples across incompatible sectors. | 3-Tier Disparity Gates normalizing comparisons to ROIC and FCF yield. | **COMPLIANT** |

---

### 5.3 Typographic & Visual Semantics Compliance

- **Tabular Lining Numerals (`tabular-nums`):**
  - *Heuristic:* Fixed-width numerals prevent jagged vertical alignment and enable instant visual magnitude comparison.
  - *Verification:* [web/static/css/style.css:42-45](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/static/css/style.css#L42-L45) defines `.tnum { font-variant-numeric: tabular-nums; }`. This class is consistently applied across KPI cards, financial comparison tables, yield curves, and ETF matrices.
- **Color Scarcity & Muted Base:**
  - *Heuristic:* Monochromatic, neutral slate base prevents alert fatigue; high-chroma red/emerald reserved strictly for material governance flags or moat expansion.
  - *Verification:* The CSS design token palette utilizes `#0f172a`, `#1e293b`, `#334155` for structure, reserving `#ef4444` and `#10b981` strictly for semantic status tags.
- **WCAG 2.2 Level AA Interactive Target Sizing:**
  - *Heuristic:* Interactive targets must be $\ge 24\times24$ pixels to prevent misclicks during dense data navigation.
  - *Verification:* Buttons, navigation items, and dropdown triggers enforce minimum touch targets $\ge 32\times32$ px.
- **Ben Shneiderman’s Progressive Disclosure:**
  - *Heuristic:* "Overview first, zoom and filter, then details-on-demand."
  - *Verification:* Executive health scorecards appear above the fold, while granular financial filings and footnotes are nested inside progressive disclosure containers.

---

### 5.4 Architectural Feature Gaps (Research vs. Web Production)

All behavioral intervention features specified in the research study are fully implemented:
1. **PEAD 60-Day Visual Drift Band:** Integrated `compute_pead_drift_band()` in `core/analysis/fundamentals.py` and rendered native SVG corridor on `/dossier/{ticker}`.
2. **Interactive Thesis Violation Modal:** Integrated `POST /api/thesis-checkpoint`, modal dialog `#thesisModalBackdrop`, and event wiring in `web/static/js/main.js`.

---

## 6. Interactive Functionality & Component Verification

### 6.1 Navigation, Menus & Sub-Tabs
- **Status:** **VERIFIED (PASS)**
- **Findings:**
  - The navbar in [web/templates/base.html](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/templates/base.html) was recently simplified to prevent tab overflow across desktop and mobile.
  - Uses organized dropdown menus:
    - **Research:** Overview, Stock Discovery, Multi-Stock Compare, Safety Radar.
    - **Multi-Asset:** Corporate Debt, Mutual Funds, Sovereign Yields, ETFs & Indices, SM REITs & InvITs, Tax Calculator.
    - **Direct Links:** Pricing, Admin Console.
  - Interactive click and keyboard behavior operates smoothly. Mobile drawer toggles cleanly with backdrop dimming.

---

### 6.2 Omni-Search & Autocomplete Widget
- **Status:** **VERIFIED (PASS)**
- **Findings:**
  - Client logic in [web/static/js/main.js](file:///Users/lyndonpinto/Documents/Stock_Research_App/web/static/js/main.js) provides a 250ms debounced omni-search input.
  - Calls `/api/suggest?q=...` and renders a multi-asset dropdown distinguishing Stocks, Mutual Funds, Corporate Debt, and REITs.
  - Tested: `/api/suggest?q=inf` returns HTTP 200 with structured scrip suggestions (`INFY`, `NAUKRI`, etc.).

---

### 6.3 Pre-Mortem Inversion Engine & Disparity Gate Overrides
- **Status:** **VERIFIED (PASS)**
- **Findings:**
  - On `/compare`, selecting companies across disparate sectors (e.g., banking vs. IT services) activates the 3-Tier Disparity Gate warning banner.
  - Clicking "Override Disparity Gate" reveals normalized universal capital efficiency metrics (ROIC, FCF yield).
  - The Pre-Mortem modal allows analysts to record failure mode responses and submit to `POST /api/premortem`, which immutably commits entries to the database.

---

### 6.4 Commercial Monetization Flow (Razorpay & PDF Generation)
- **Status:** **VERIFIED (PASS)**
- **Findings:**
  - Pricing page at `/pricing` presents tiered offerings:
    - Single Ticker Forensic Dossier (₹499)
    - Quarterly Equity + Multi-Asset Pro Pass (₹1,499)
    - Corporate & Advisory Desk Bulk Pack (₹4,999)
  - Clicking a tier calls `POST /api/create-order`, which communicates with Razorpay APIs and returns an official `order_id` and public `key_id`.
  - PDF generation route `/api/pdf/{ticker}` returns HTTP 200 with `Content-Type: application/pdf`, rendering clean executive summaries with embedded SEBI safe-harbor notices.

---

### 6.5 Complete Route & Endpoint Health Matrix (73 Routes)

A live route audit across all 73 registered FastAPI endpoints was performed:

| Route Pattern | HTTP Verb | Response Status | Functional Description |
| :--- | :---: | :---: | :--- |
| `/` | GET | `200 OK` | Public homepage & executive terminal |
| `/search` | GET | `200 OK` | Omni-asset search hub |
| `/discovery` | GET | `200 OK` | 9 AM stock discovery & momentum radar |
| `/pricing` | GET | `200 OK` | Dossier monetization & subscription tiers |
| `/compare` | GET | `200 OK` | Multi-company comparison & disparity engine |
| `/debt` | GET | `200 OK` | Listed NCDs & corporate debt directory |
| `/debt/{isin}` | GET | `200 OK / 404` | Granular credit scorecard & solvency analysis |
| `/funds` | GET | `200 OK` | Mutual fund look-through & active share terminal |
| `/funds/{scheme_code}` | GET | `200 OK / 404` | Dual-sleeve look-through & fee drag analyzer |
| `/funds/compare/overlap`| GET | `200 OK` | Cross-scheme portfolio overlap diagnostic |
| `/sovereign` | GET | `200 OK` | RBI/FBIL Par yield curve & T-Bill benchmarks |
| `/etfs` | GET | `200 OK` | ETF liquidity, tracking error & spread matrix |
| `/calculator/tax` | GET | `200 OK` | Net real post-tax return calculator (CPI deflated) |
| `/reits` | GET | `200 OK` | SEBI SM REITs & InvITs compliance directory |
| `/safety-radar` | GET | `200 OK` | Retail shadow-banking & P2P danger scorecards |
| `/dossier/{ticker}` | GET | `200 OK` | 7-Pillar fundamental equity dossier |
| `/admin` | GET | `200 OK / 303` | Admin & telemetry console (OAuth gated) |
| `/api/suggest` | GET | `200 OK` | Debounced omni-search autocomplete JSON |
| `/api/pdf/{ticker}` | GET | `200 OK` | Headless printable PDF dossier export |
| `/api/premortem` | POST | `200 OK` | Commits failure mode responses to ledger |
| `/api/create-order` | POST | `200 OK` | Razorpay official payment order generation |
| `/api/verify-payment` | POST | `200 OK` | Razorpay HMAC-SHA256 signature verification |
| `/api/auth/signin` | POST | `200 OK` | User registration / sign-in (needs hardening) |
| `/api/sovereign/curve` | GET | `200 OK` | Live sovereign yield curve data points |
| `/api/etfs/matrix` | GET | `200 OK` | ETF tracking error & impact cost feed |
| `/api/reits/directory` | GET | `200 OK` | REIT & SM REIT regulatory compliance feed |
| `/api/safety-radar` | GET | `200 OK` | Shadow-banking alternative yield risk feed |
| `/sitemap.xml` | GET | `200 OK` | Search engine crawler XML sitemap index |
| `/robots.txt` | GET | `200 OK` | Crawler directives (domain fix recommended) |
| `/health` | GET | `200 OK` | Uptime & database connection health check |

---

## 7. Dimension 6: Prioritized Recommendations & Action Plan

---

### Critical Analysis: Upstream Data Sourcing vs. Commercial Monetization Risk

> [!WARNING]
> **The Free Scraper vs. Paid Subscriber Contradiction:**  
> The application currently monetizes institutional equity and multi-asset dossiers via Razorpay (from ₹299 for a Single Pass up to ₹8,999 for Institutional Pro). However, its fundamental ingestion layer relies in part on free, unauthenticated scraping (`yfinance`, unauthenticated `api.bseindia.com` endpoints, and private OBPP platforms).
>
> 1. **Breach of Terms of Service (Yahoo Finance):** Yahoo Terms of Service (Sec. 1c) explicitly prohibit automated querying, commercial scraping, and selling derived data. Selling reports derived from Yahoo data strips away fair-dealing protections and creates contractual and copyright exposure.
> 2. **BSE Market Data Distribution Policy:** Direct HTTP scraping of `api.bseindia.com` using spoofed User-Agent headers in a monetized SaaS violates exchange data distribution policies and exposes the platform to IP claims and cease-and-desist notices.
> 3. **Tortious Interference (Private OBPP Portals):** Scraping registered bond portals (`wintwealth.com`, `goldenpi.com`, `gripinvest.in`) to repackage their bond deals in paid dossiers creates civil liability for unfair trade practices.
> 4. **SEBI RA Regulations 2014 Compliance:** Under Section 2(u), fee-based research requires verifiable data provenance and zero hallucination. Silent scraper failures risk publishing stale or inaccurate metrics.
> 5. **Technical Fragility:** Cloud hosting IPs (Render, AWS) are aggressively blocked by Akamai and Cloudflare WAFs with HTTP 429 errors or Turnstile challenges during live user dossier generation.
>
> **Actionable Remediation Summary:**
> - Decommissioned and purged **EODHD** from the codebase in favor of exchange-grounded gateway. *(Completed)*
> - Transitioned primary equity quote ingestion to **Angel One SmartAPI** broker gateway with AWS static IP egress (`13.54.76.134:8888`) and RFC 6238 TOTP session token lifecycle. *(Completed)*
> - Restricted mutual fund look-through to **AMFI statutory utility feeds (`NAVAll.txt`)** and macro/sovereign to **RBI/MOSPI open gazette data** (both 100% free and legally compliant). *(Completed)*
> - Embedded mandatory SEBI RA Section 2(u) non-advisory disclaimers and data provenance footers across all PDF and web reports. *(Completed)*

---

### 7.2 Prioritized Active Task Register (P0 to P3)

The following items constitute the prioritized, operational active tasks:

#### 🔴 P0 — Critical: Security & Runtime Integrity
1. **Render Production Environment & Secrets Hardening:** *(Completed)*
   - **Target Files:** `render.yaml`, `web/main.py`, `tests/test_render_hardening.py`
   - **Details:** Declared `SECRET_KEY`, `ADMIN_API_KEY`, and `ADMIN_PASSWORD` in `render.yaml` with `sync: false`. Enforced strict production boot checks in `web/main.py` requiring a non-empty 32+ character `SECRET_KEY` when deployed. Configured `--workers 2` for multi-threaded performance.

#### 🟠 P1 — High Impact: Core Features & Consistency
2. **Peer Comparison (`/compare`) Data Source Harmonization (Audit 1 Finding F20):** *(Completed)*
   - **Target Files:** `core/db/fundamentals.py`, `core/analysis/fundamentals.py`, `core/analysis/comparator.py`, `web/templates/compare.html`, `tests/test_peer_comparison_data.py`
   - **Details:** Connected `compare_two_companies()` to localized `cached_fundamentals` DB repository (migration `v027_cached_fundamentals`), extracting and caching verified ROCE, ROE, OPM, D/E, and 52-week ranges from report baseline text and discovery reel to ensure 100% non-N/A peer metrics.
3. **Curated Mutual Fund Top 50 Expansion (Remaining 19 Schemes):**
   - **Target Files:** `core/db/mutual_funds.py`, `core/analysis/fund_forensic_auditor.py`
   - **Details:** Ingest 19 marquee schemes across Mid Cap, Small Cap, Large & Mid Cap, and Flexi Cap with constituent holdings to complete the Top 50 AMFI universe.
4. **Hybrid AI Auditor & Failure Synthesizer:** *(Completed)*
   - **Target Files:** `scripts/ai_auditor.py`, `tests/test_ai_auditor.py`
   - **Details:** Implemented the bounded 3-persona auditor (Regulatory Baiter, Edge-Case Quant, State Saboteur) using `gemini-3.8-flash` with a strict $0.50 token ceiling that outputs structured threat dossiers and auto-generates failing Python unit tests (`tests/test_regression_*.py`).

#### 🟡 P2 — Operational Quality & Test Coverage
5. **Install `openpyxl` Locally:**
   - **Details:** Ensure all 303 unit tests run locally (unskipping the 13 tests in `test_mf_portfolio_ingest.py`).
6. **Operational Gateway Liveness & Token Lifecycle Monitoring:**
   - **Target Files:** `core/ingestion/angel_one.py`, `scripts/verify_angel_proxy_ip.py`
   - **Details:** Maintain continuous uptime of the AWS Lightsail proxy daemon (`13.54.76.134:8888`) and verify automated RFC 6238 TOTP session token renewals during live Indian market trading hours (09:15 to 15:30 IST).

#### ⚪ P3 — Hygiene & Explicitly Parked Backlog
- **Deferred Items:** Custom Vector Icon System (SVG Sprites), Unlisted MSME Analysis Ingestion, and Full CAS Encrypted PDF Parser.

---

### 7.3 Historical Build & Completion Ledger

All 32 historical milestones, major architectural deliverables (Cortex suite, Sutra look-through, Angel One Level-2 depth, sovereign curve, REITs/InvITs terminal, and SEBI compliance polish), and batch audit remediations are archived and maintained in the Master Engineering Manual:
👉 [**Master Historical Build Ledger (docs/MASTER_ENGINEERING_MANUAL.md §6)**](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/MASTER_ENGINEERING_MANUAL.md).







